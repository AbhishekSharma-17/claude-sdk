"""Phase 5: Auto-Fix.

For each file with HIGH or ERROR severity validation issues that can be
mechanically fixed (deprecated APIs, missing SparkSession configs, wrong
return type annotations, etc.), sends the file + issue list to Claude
(Sonnet) and asks for targeted, surgical fixes.

Safety guarantee: if the fixed file fails ast.parse(), the original content
is restored immediately and the result is marked REVERTED.

Also builds the DeveloperActionItems report section by classifying every
validation issue into one of four action categories.
"""

from __future__ import annotations

import ast
import json
import logging
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

from config import ConverterConfig
from models import (
    ActionItem,
    AutoFixResult,
    AutoFixStatus,
    DeveloperActionItems,
    ValidationIssue,
    ValidationResult,
)

logger = logging.getLogger(__name__)


# ── Issue Classification Tables ───────────────────────────────────────────────

# Patterns in issue messages that indicate Claude can fix the file directly
_AUTO_FIXABLE_PATTERNS: tuple[str, ...] = (
    "unionall",
    ".unionall()",
    "registertempTable",
    "deprecated",
    "return type annotation",
    "-> none",
    "sparksession",
    "spark.sql.decimal",
    "decimaltype",
    "cast(decimaltype",
    "case-insensitive",
    "case insensitive",
    "ilike",
    "f.lower",
    "bare col()",
    "without f. prefix",
    "collect()",
    ".collect()",
    "silently discarded",
    "unconditionally returns",
    "annotated",
)

# Infrastructure items — require Spark cluster / Delta Lake / storage changes
_INFRASTRUCTURE_PATTERNS: tuple[str, ...] = (
    "delta lake",
    "delta table",
    "saveastable",
    "table definition file was not found",
    "pre-registered in the spark catalog",
    "cdf",
    "change data feed",
    "change data capture",
    "jdbc",
    "linked server",
    "external table",
    "hdfs",
    "adls",
    "blob storage",
    "kafka",
    "streaming",
    "checkpoint location",
    "cluster config",
    "s3://",
    "abfss://",
)

# Patterns that require understanding business logic or SQL semantics
_MANUAL_PATTERNS: tuple[str, ...] = (
    "cursor",
    "dynamic sql",
    "transaction",
    "merge",
    "upsert",
    "rollback",
    "openrowset",
    "sp_executesql",
    "business logic",
    "ambiguous",
    "pivot columns",
    "recursive",
)

# Prescriptive how_to_fix lookup — keyed on lowercase pattern in issue message
_HOW_TO_FIX: dict[str, str] = {
    "unionall": (
        "Replace every `.unionAll(df)` call with `.union(df)`. "
        "`.unionAll()` was removed in PySpark 3.x."
    ),
    "registertempTable": (
        "Replace `.registerTempTable('name')` with `.createOrReplaceTempView('name')`. "
        "The old method was removed in PySpark 3.0."
    ),
    "sparksession": (
        "Add `.config('spark.sql.decimalOperations.allowPrecisionLoss', False)` "
        "to the SparkSession builder chain before `.getOrCreate()`."
    ),
    "decimaltype": (
        "Wrap the column expression with `.cast(DecimalType(precision, scale))` "
        "where precision/scale match the original SQL DECIMAL definition."
    ),
    "return type annotation": (
        "Correct the function return type annotation — e.g. change `-> None` to `-> DataFrame` "
        "if the function returns a DataFrame."
    ),
    "-> none": (
        "Change `-> None` to `-> DataFrame` on the function signature "
        "if the function actually returns a DataFrame object."
    ),
    "case-insensitive": (
        "Wrap both sides of the comparison in `F.lower()`: "
        "`F.lower(F.col('col')) == 'value'` or use `.ilike()` for LIKE patterns."
    ),
    "ilike": (
        "Use `.ilike()` for case-insensitive LIKE patterns: "
        "`F.col('col').ilike('%pattern%')` instead of raw string comparison."
    ),
    "bare col()": (
        "Add the `F.` prefix: change `col('name')` to `F.col('name')` "
        "to avoid NameError and ensure consistent function resolution."
    ),
    "without f. prefix": (
        "Add `F.` prefix to all pyspark.sql.functions calls: "
        "`col(...)` → `F.col(...)`, `lit(...)` → `F.lit(...)`, etc."
    ),
    "collect()": (
        "Avoid `.collect()` on large DataFrames. "
        "For single values use `.first()[col_name]` or `.agg(F.max(...)).collect()[0][0]`. "
        "For small reference data use `.limit(n).collect()`."
    ),
    "silently discarded": (
        "Assign the computed DataFrame to a variable and either return it, "
        "write it out, or cache it. An unreferenced DataFrame wastes compute."
    ),
    "unconditionally returns": (
        "Fix the return type annotation to match what the function actually returns, "
        "or add an explicit `return None` path if the annotation is correct."
    ),
    # Infrastructure
    "delta lake": (
        "Provision a Delta Lake table: `spark.sql('CREATE TABLE tbl USING DELTA LOCATION ...')`. "
        "Ensure the cluster has the Delta Lake JAR (`delta-core`) configured."
    ),
    "cdf": (
        "Enable Change Data Feed on the Delta table: "
        "`ALTER TABLE tbl SET TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')`."
    ),
    "jdbc": (
        "Configure a JDBC connection: set `spark.jars` to include the JDBC driver JAR, "
        "then use `spark.read.jdbc(url, table, properties={...})`."
    ),
    # Manual
    "cursor": (
        "Rewrite as a window function — `F.lag()`, `F.lead()`, or a cumulative "
        "`F.sum(...).over(window)`. SQL cursors have no direct PySpark equivalent."
    ),
    "dynamic sql": (
        "Enumerate the possible predicate values and use a `F.when()` chain "
        "or a Python dict-dispatch pattern. Truly dynamic SQL requires custom logic."
    ),
    "merge": (
        "Use Delta Lake `MERGE INTO` syntax, or implement as: "
        "(1) filter out rows with matching keys, (2) union with new rows."
    ),
    "transaction": (
        "PySpark has no ACID transactions outside Delta Lake. "
        "Restructure as an atomic Delta write or wrap in a try/except with compensating logic."
    ),
    "pivot columns": (
        "Collect the distinct pivot column values at runtime: "
        "`pivot_vals = [r[0] for r in df.select('col').distinct().collect()]` "
        "then pass to `.pivot('col', pivot_vals)`."
    ),
}


# ── Public API ────────────────────────────────────────────────────────────────


async def fix_all(
    validation_results: list[ValidationResult],
    options: ClaudeAgentOptions,
    config: ConverterConfig,
    dep_context_by_file: dict[str, str] | None = None,
) -> list[AutoFixResult]:
    """Run auto-fix on all files that have HIGH/ERROR auto-fixable issues.

    Processes files sequentially — each fix overwrites a file and we want
    predictable file state before moving to the next.

    Args:
        validation_results: Results from Phase 4.
        options: ClaudeAgentOptions for the auto-fix agent (Sonnet).
        config: Converter configuration.
        dep_context_by_file: Optional dict mapping file basename → dependency
            signatures string (same context Phase 4 used). Injected into the
            fix prompt so Claude can resolve cross-file references (e.g.
            matching constructor signatures between caller and callee).

    Returns:
        List of AutoFixResult, one per file that had fixable issues.
    """
    results: list[AutoFixResult] = []
    total_fix_cost = 0.0
    budget_cap = config.auto_fix_budget_per_file * max(len(validation_results), 1) * 2
    dep_ctx = dep_context_by_file or {}

    for vr in validation_results:
        fixable = [i for i in vr.issues if _classify_issue(i) == "auto_fix"]
        if not fixable:
            continue

        if total_fix_cost >= budget_cap:
            logger.warning(
                "Auto-fix: total budget cap ($%.2f) reached — skipping remaining files.",
                budget_cap,
            )
            break

        file_basename = Path(vr.file_path).name
        file_dep_ctx = dep_ctx.get(file_basename, "")

        logger.info(
            "Auto-fixing: %s  (%d fixable issues%s)",
            file_basename, len(fixable),
            f", +dep-ctx {len(file_dep_ctx)} chars" if file_dep_ctx else "",
        )
        fix_result = await _fix_file(vr, fixable, options, config, file_dep_ctx)
        results.append(fix_result)
        total_fix_cost += fix_result.cost_usd

    fixed = sum(1 for r in results if r.status in (AutoFixStatus.FIXED, AutoFixStatus.PARTIAL))
    reverted = sum(1 for r in results if r.was_reverted)
    skipped = sum(1 for r in results if r.status == AutoFixStatus.SKIPPED)
    logger.info(
        "Auto-fix complete: %d fixed, %d reverted, %d skipped  (cost: $%.4f)",
        fixed, reverted, skipped, total_fix_cost,
    )
    return results


def build_developer_action_items(
    validation_results: list[ValidationResult],
    auto_fix_results: list[AutoFixResult],
    todos_in_code: list[str],
) -> DeveloperActionItems:
    """Classify all validation issues into four developer action categories.

    Called after Phase 5 so auto-fixed items can be separated from what remains.

    Args:
        validation_results: All Phase 4 results.
        auto_fix_results: Phase 5 results (may be empty if --skip-autofix used).
        todos_in_code: TODO lines scanned from output files by orchestrator.

    Returns:
        DeveloperActionItems with all four buckets populated and a summary.
    """
    # Build a lookup: file_path → set of remaining issue messages (not fixed)
    remaining_by_file: dict[str, set[str]] = {}
    fixed_by_file: dict[str, set[str]] = {}

    for afr in auto_fix_results:
        remaining_msgs = {i.message for i in afr.issues_remaining}
        remaining_by_file[afr.file_path] = remaining_msgs
        # Issues attempted - remaining = fixed (approximate, best effort)
        fixed_by_file[afr.file_path] = set()  # will be inferred below

    items = DeveloperActionItems(todos_in_code=todos_in_code)

    for vr in validation_results:
        file_remaining = remaining_by_file.get(vr.file_path)
        file_afr = next((a for a in auto_fix_results if a.file_path == vr.file_path), None)

        for issue in vr.issues:
            category = _classify_issue(issue)
            action = _make_action_item(issue, category)

            if category == "auto_fix":
                # Determine if this specific issue was fixed
                if file_afr and file_afr.status in (AutoFixStatus.FIXED, AutoFixStatus.PARTIAL):
                    if file_remaining is not None and issue.message not in file_remaining:
                        # Issue was fixed — move to auto_fixed bucket
                        action.category = "auto_fixed"
                        items.auto_fixed.append(action)
                        continue
                # Not fixed or reverted — escalate to requires_manual
                action.category = "requires_manual"
                items.requires_manual.append(action)

            elif category == "infrastructure":
                items.infrastructure_setup.append(action)

            elif category == "manual":
                action.category = "requires_manual"
                items.requires_manual.append(action)

            else:  # review
                items.recommended_review.append(action)

    items.summary = _generate_summary(items)
    return items


# ── Per-File Fix ──────────────────────────────────────────────────────────────


async def _fix_file(
    vr: ValidationResult,
    fixable_issues: list[ValidationIssue],
    options: ClaudeAgentOptions,
    config: ConverterConfig,
    dep_context: str = "",
) -> AutoFixResult:
    """Attempt to auto-fix a single file.

    Safety: if the fixed content fails ast.parse(), restores the original.
    """
    file_path = Path(vr.file_path)
    result = AutoFixResult(file_path=str(file_path), issues_attempted=len(fixable_issues))

    # Read original
    try:
        original_content = file_path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("  Auto-fix: cannot read %s: %s", file_path.name, e)
        result.status = AutoFixStatus.FAILED
        result.issues_remaining = fixable_issues
        return result

    prompt = _build_fix_prompt(file_path, original_content, fixable_issues, dep_context)
    collected_text: list[str] = []

    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        collected_text.append(block.text)
            elif isinstance(message, ResultMessage):
                result.cost_usd = message.total_cost_usd
    except Exception as e:
        logger.error("  Auto-fix: Claude call failed for %s: %s", file_path.name, e)
        result.status = AutoFixStatus.FAILED
        result.issues_remaining = fixable_issues
        return result

    full_response = "\n".join(collected_text)
    summary_data, fixed_content = _parse_fix_response(full_response)

    if fixed_content is None:
        logger.warning(
            "  Auto-fix: could not extract fixed content from Claude for %s", file_path.name
        )
        result.status = AutoFixStatus.FAILED
        result.issues_remaining = fixable_issues
        return result

    # Sanity check: fixed file should not be drastically shorter (truncation guard)
    if len(fixed_content.strip()) < len(original_content.strip()) * 0.5:
        logger.warning(
            "  Auto-fix: fixed content for %s is >50%% shorter than original — treating as truncation, reverting",
            file_path.name,
        )
        result.status = AutoFixStatus.REVERTED
        result.was_reverted = True
        result.revert_reason = "Fixed content was >50% shorter than original (likely truncation)"
        result.issues_remaining = fixable_issues
        return result

    # Syntax check on fixed content
    try:
        ast.parse(fixed_content)
    except SyntaxError as e:
        logger.warning(
            "  Auto-fix: SyntaxError in fixed %s at line %s ('%s') — reverting",
            file_path.name, e.lineno, e.msg,
        )
        result.status = AutoFixStatus.REVERTED
        result.was_reverted = True
        result.revert_reason = f"SyntaxError at line {e.lineno}: {e.msg}"
        result.issues_remaining = fixable_issues
        return result

    # Write fixed content
    file_path.write_text(fixed_content, encoding="utf-8")

    fixes_applied: list[str] = summary_data.get("fixes_applied", [])
    fixes_skipped: list[str] = summary_data.get("fixes_skipped", [])

    result.issues_fixed = len(fixes_applied)
    result.issues_remaining = _match_skipped_to_issues(fixes_skipped, fixable_issues)

    result.status = (
        AutoFixStatus.FIXED if not result.issues_remaining else AutoFixStatus.PARTIAL
    )

    logger.info(
        "  Auto-fix %s: %s — %d fixed, %d remaining  ($%.4f)",
        file_path.name, result.status, result.issues_fixed,
        len(result.issues_remaining), result.cost_usd,
    )
    return result


# ── Classification & Action Item Helpers ─────────────────────────────────────


def _classify_issue(issue: ValidationIssue) -> str:
    """Classify a ValidationIssue into action category.

    Returns one of: "auto_fix", "infrastructure", "manual", "review".

    Strategy: for HIGH/ERROR issues, we **try auto-fix by default** unless
    the issue explicitly matches a known manual or infrastructure pattern.
    The safety net (ast.parse + truncation guard) protects against bad fixes.

    This is intentionally optimistic — the validator already provided specific
    fix instructions (line numbers, exact changes), so Claude can usually apply
    them. Only issues requiring business logic understanding (cursor rewrites,
    dynamic SQL predicate translation, MERGE semantics) are excluded.
    """
    msg = issue.message.lower()
    severity_upper = issue.severity.upper()

    # Infrastructure first — these cannot be fixed by editing Python alone
    for pattern in _INFRASTRUCTURE_PATTERNS:
        if pattern in msg:
            return "infrastructure"

    # For ERROR/HIGH: blacklist-based → only skip if known-manual pattern
    if severity_upper in ("ERROR", "HIGH"):
        for pattern in _MANUAL_PATTERNS:
            if pattern in msg:
                return "manual"
        # Everything else: try auto-fix. The validator gave specific fix
        # instructions (line numbers, exact changes). Claude can apply them.
        # Safety net: ast.parse() + truncation guard will revert bad fixes.
        return "auto_fix"

    # MEDIUM/WARNING/LOW/INFO → recommend review
    return "review"


def _make_action_item(issue: ValidationIssue, category: str) -> ActionItem:
    """Convert a ValidationIssue into an ActionItem with prescriptive how_to_fix."""
    msg_lower = issue.message.lower()
    how_to_fix = (
        "Review the issue manually and apply the appropriate PySpark fix. "
        "Refer to the PySpark migration guide for deprecated APIs."
    )

    for pattern, fix_text in _HOW_TO_FIX.items():
        if pattern in msg_lower:
            how_to_fix = fix_text
            break

    _priority_map = {
        "error": "critical",
        "high": "high",
        "medium": "medium",
        "moderate": "medium",
        "warning": "medium",
        "low": "low",
        "info": "low",
    }
    priority = _priority_map.get(issue.severity.lower(), "medium")

    return ActionItem(
        category=category,
        priority=priority,
        file=issue.file,
        description=issue.message,
        how_to_fix=how_to_fix,
        line=issue.line,
    )


def _generate_summary(items: DeveloperActionItems) -> str:
    """Generate a human-readable 2-4 sentence summary paragraph."""
    parts: list[str] = []

    if items.auto_fixed:
        n = len(items.auto_fixed)
        parts.append(
            f"{n} issue{'s' if n != 1 else ''} automatically fixed "
            f"(deprecated APIs, SparkSession configs, annotation mismatches)."
        )

    manual = len(items.requires_manual)
    infra = len(items.infrastructure_setup)
    review = len(items.recommended_review)

    if manual:
        parts.append(
            f"{manual} issue{'s' if manual != 1 else ''} require manual code changes "
            f"(cursor rewrites, dynamic SQL, MERGE logic) — see requires_manual."
        )
    if infra:
        parts.append(
            f"{infra} item{'s' if infra != 1 else ''} need infrastructure setup "
            f"(Delta Lake tables, CDF, JDBC) — see infrastructure_setup."
        )
    if review:
        parts.append(
            f"{review} item{'s' if review != 1 else ''} flagged for recommended review "
            f"(null ordering, case sensitivity, OOM risk) — see recommended_review."
        )
    if items.todos_in_code:
        n = len(items.todos_in_code)
        parts.append(
            f"{n} TODO comment{'s' if n != 1 else ''} remain in generated files "
            f"marking patterns that need manual attention."
        )

    if not parts:
        return "No action items identified. All files passed validation and auto-fix."

    return " ".join(parts)


# ── Fix Prompt & Response Parser ──────────────────────────────────────────────


def _build_fix_prompt(
    file_path: Path,
    content: str,
    issues: list[ValidationIssue],
    dep_context: str = "",
) -> str:
    """Build the targeted fix prompt for a single file."""
    issues_block = "\n".join(
        f"  [{i + 1}] severity={issue.severity}"
        f"{f', line {issue.line}' if issue.line else ''}: {issue.message}"
        for i, issue in enumerate(issues)
    )

    dep_section = ""
    if dep_context:
        dep_section = f"""
## DEPENDENCY FILES (real signatures — use these to fix cross-file mismatches)
{dep_context}
"""

    return f"""Fix the following issues in this PySpark file. The validator has already identified each issue with its exact line number and a description of what's wrong.

## FILE PATH
{file_path.resolve()}

## ISSUES TO FIX (apply ALL of them)
{issues_block}
{dep_section}
## CURRENT FILE CONTENT
```python
{content}
```

## INSTRUCTIONS
- Fix ONLY the numbered issues above. Do not refactor or change anything else.
- For cross-file issues (signature mismatches, wrong constructor args), refer to the DEPENDENCY FILES section above for the correct signatures.
- For ordering issues ("X called after Y is released"), move the relevant lines to the correct position.
- Keep all TODO comments, docstrings, and blank lines exactly as they are.
- If you cannot safely fix an issue (ambiguous business logic, requires infrastructure), skip it and include it in "fixes_skipped".
- Return the COMPLETE fixed file — no truncation, no ellipsis, every line from the original must be present.

Respond with exactly two blocks:
1. A ```json block: {{"fixes_applied": ["issue 1 description", "issue 2 description"], "fixes_skipped": ["issue N description (reason)"]}}
2. A ```python block: the COMPLETE fixed file content"""


def _parse_fix_response(text: str) -> tuple[dict, str | None]:
    """Extract JSON summary dict and fixed Python content from Claude's response.

    Returns:
        Tuple of (summary_dict, fixed_python_or_None).
        summary_dict always has "fixes_applied" and "fixes_skipped" lists.
    """
    summary: dict = {"fixes_applied": [], "fixes_skipped": []}
    fixed_content: str | None = None

    # Extract JSON block
    if "```json" in text:
        try:
            start = text.index("```json") + len("```json")
            end = text.index("```", start)
            summary = json.loads(text[start:end].strip())
        except (ValueError, json.JSONDecodeError):
            pass

    # Extract Python block — take the LAST one (Claude sometimes shows before/after)
    python_blocks: list[str] = []
    pos = 0
    while "```python" in text[pos:]:
        try:
            start = text.index("```python", pos) + len("```python")
            end = text.index("```", start)
            python_blocks.append(text[start:end].strip())
            pos = end + 3
        except ValueError:
            break

    if python_blocks:
        fixed_content = python_blocks[-1]

    return summary, fixed_content


def _match_skipped_to_issues(
    fixes_skipped: list[str],
    original_issues: list[ValidationIssue],
) -> list[ValidationIssue]:
    """Map Claude's fix_skipped strings back to ValidationIssue objects (best effort).

    Claude paraphrases issues in its skip list, so we do fuzzy matching on
    common keywords. Issues that cannot be matched are dropped (assumed fixed).
    """
    if not fixes_skipped:
        return []

    remaining: list[ValidationIssue] = []
    for issue in original_issues:
        msg_lower = issue.message.lower()
        for skipped_str in fixes_skipped:
            # Check if any significant word from the skip message appears in the issue
            skip_words = set(skipped_str.lower().split())
            issue_words = set(msg_lower.split())
            if len(skip_words & issue_words) >= 2:
                remaining.append(issue)
                break

    return remaining
