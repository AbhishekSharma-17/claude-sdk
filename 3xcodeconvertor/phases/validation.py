"""Phase 4: Validation & Report Generation.

Context-aware validation: each file is validated with the content of its
dependency files injected so Claude can cross-check function signatures,
return types, and import chains across the whole generated codebase.

Local ast.parse() runs first (free). Claude review with Sonnet runs second.
"""

from __future__ import annotations

import ast
import json
import logging
import re
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
    AutoFixResult,
    ConversionPlan,
    ConversionReport,
    ConversionResult,
    ConversionStatus,
    CostBreakdown,
    DeveloperActionItems,
    FileInventory,
    ValidationIssue,
    ValidationResult,
)

logger = logging.getLogger(__name__)


# ── Public API ────────────────────────────────────────────────────────────────


async def validate_all(
    output_files: list[Path],
    options: ClaudeAgentOptions,
    config: ConverterConfig,
    plan: ConversionPlan | None = None,
    inventories: list[FileInventory] | None = None,
) -> list[ValidationResult]:
    """Validate all generated PySpark files.

    Step 1: Local ast.parse() — free, catches syntax errors and common patterns.
    Step 2: Claude review (Sonnet) — catches logic/gotcha issues.
             When plan is provided, dependency file signatures are injected into
             the prompt so Claude can cross-validate call sites and signatures.

    Args:
        output_files: List of generated .py file paths to validate.
        options: ClaudeAgentOptions for the validation agent.
        config: Converter configuration.
        plan: Optional ConversionPlan — enables cross-file dependency injection.
        inventories: Optional list of FileInventory — reserved for future use.

    Returns:
        List of ValidationResult, one per file.
    """
    results: list[ValidationResult] = []

    # Build object-name → output-file lookup for dependency injection
    obj_to_file = _build_object_file_map(output_files) if plan else {}

    for file_path in output_files:
        logger.info("Validating: %s", file_path.name)

        # Step 1: Local syntax check (free)
        syntax_result = _check_syntax_local(file_path)

        if not syntax_result.syntax_valid:
            logger.warning(
                "  Syntax error: %s",
                syntax_result.issues[0].message if syntax_result.issues else "unknown",
            )
            results.append(syntax_result)
            continue

        # Step 2: Build cross-file dependency context
        dep_context = ""
        if plan:
            dep_context = _build_dep_context(file_path, plan, obj_to_file)
            if dep_context:
                logger.info(
                    "  Injecting dependency context for %s (%d chars)",
                    file_path.name, len(dep_context),
                )

        # Step 3: Claude review (costs API tokens)
        claude_result = await _validate_with_claude(file_path, dep_context, options, config)

        # Merge results
        merged = ValidationResult(
            file_path=str(file_path),
            syntax_valid=True,
            pyspark_correct=claude_result.pyspark_correct,
            dependencies_resolved=claude_result.dependencies_resolved,
            issues=syntax_result.issues + claude_result.issues,
            todos_found=claude_result.todos_found,
            cost_usd=claude_result.cost_usd,
        )
        results.append(merged)

    return results


def generate_report(
    conversion_results: list[ConversionResult],
    validation_results: list[ValidationResult],
    cost_breakdown: CostBreakdown,
    file_complexity: str,
    auto_fix_results: list[AutoFixResult] | None = None,
    developer_action_items: DeveloperActionItems | None = None,
) -> ConversionReport:
    """Generate the final conversion report.

    Args:
        conversion_results: Results from Phase 3 conversion.
        validation_results: Results from Phase 4 validation.
        cost_breakdown: Cost per phase (including auto_fix if run).
        file_complexity: File complexity label from Phase 1.
        auto_fix_results: Optional results from Phase 5 auto-fix.
        developer_action_items: Optional categorised action items.

    Returns:
        ConversionReport with all fields populated.
    """
    converted = sum(1 for r in conversion_results if r.status == ConversionStatus.CONVERTED)
    failed = sum(1 for r in conversion_results if r.status == ConversionStatus.FAILED)
    skipped = sum(1 for r in conversion_results if r.status == ConversionStatus.SKIPPED)
    needs_review = sum(1 for r in conversion_results if r.status == ConversionStatus.NEEDS_REVIEW)

    all_issues: list[ValidationIssue] = []
    for vr in validation_results:
        all_issues.extend(vr.issues)

    total_duration = sum(r.duration_ms for r in conversion_results)

    return ConversionReport(
        total_objects=len(conversion_results),
        converted=converted,
        failed=failed,
        skipped=skipped,
        needs_review=needs_review,
        total_cost_usd=cost_breakdown.total,
        total_duration_ms=total_duration,
        file_complexity=file_complexity,
        cost_breakdown=cost_breakdown,
        objects=conversion_results,
        validation_issues=all_issues,
        todos=[],  # populated by orchestrator via _collect_todos()
        auto_fix_results=auto_fix_results or [],
        developer_action_items=developer_action_items or DeveloperActionItems(),
    )


# ── Dependency Context Builder ────────────────────────────────────────────────


def _build_object_file_map(output_files: list[Path]) -> dict[str, Path]:
    """Build a lookup from normalised SQL object name → output .py file path.

    Normalisation: strip underscores, lowercase. This lets us match
    "usp_BuildCustomerProfile" → key "buildcustomerprofile" → "build_customer_profile.py".
    """
    obj_map: dict[str, Path] = {}
    for f in output_files:
        key = f.stem.replace("_", "").lower()
        obj_map[key] = f
    return obj_map


def _resolve_object_to_file(obj_name: str, obj_to_file: dict[str, Path]) -> Path | None:
    """Resolve a SQL object name to its generated .py file path."""
    name = obj_name
    for prefix in ("usp_", "sp_", "fn_", "vw_", "trg_", "dbo."):
        if name.lower().startswith(prefix):
            name = name[len(prefix):]
            break
    key = name.replace("_", "").lower()
    return obj_to_file.get(key)


def _extract_signatures(content: str) -> str:
    """Extract function/class signatures and first docstring line from Python source.

    Returns a compact multi-line string — enough for cross-signature validation
    without injecting the entire file.
    """
    lines = content.splitlines()
    sigs: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^(def |class |\s{0,4}def )", line):
            sig = line.rstrip()
            doc_line = ""
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                stripped = lines[j].strip()
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    doc_content = stripped.lstrip('"""').lstrip("'''").strip()
                    if doc_content:
                        doc_line = f"  # {doc_content[:80]}"
            sigs.append(f"{sig}{doc_line}")
        i += 1
    return "\n".join(sigs)


def _build_dep_context(
    file_path: Path,
    plan: ConversionPlan,
    obj_to_file: dict[str, Path],
) -> str:
    """Build a dependency context block for the validation prompt.

    For the file being validated, finds all objects it depends on via
    plan.dependency_edges and plan.object_plans.dependencies_resolved,
    then extracts function signatures from those files and formats them
    for injection into the Claude validation prompt.

    Args:
        file_path: The output .py file being validated.
        plan: ConversionPlan with dependency_edges and object_plans.
        obj_to_file: Normalised object name → Path lookup.

    Returns:
        Formatted dependency context string, or "" if no dependencies found.
    """
    # Normalise this file's stem to match against dependency edge sources
    stem_key = file_path.stem.replace("_", "").lower()

    dep_object_names: list[str] = []

    # Source 1: dependency_edges (source → target)
    for edge in plan.dependency_edges:
        src = edge.source
        for prefix in ("usp_", "sp_", "fn_", "vw_", "trg_", "dbo."):
            if src.lower().startswith(prefix):
                src = src[len(prefix):]
                break
        src_key = src.replace("_", "").lower()
        if src_key == stem_key:
            dep_object_names.append(edge.target)

    # Source 2: object_plans.dependencies_resolved
    for obj_name, obj_plan in plan.object_plans.items():
        name = obj_name
        for prefix in ("usp_", "sp_", "fn_", "vw_", "trg_", "dbo."):
            if name.lower().startswith(prefix):
                name = name[len(prefix):]
                break
        obj_key = name.replace("_", "").lower()
        if obj_key == stem_key:
            dep_object_names.extend(obj_plan.dependencies_resolved)
            break

    # Deduplicate preserving order
    seen: set[str] = set()
    unique_deps: list[str] = []
    for d in dep_object_names:
        if d not in seen:
            seen.add(d)
            unique_deps.append(d)

    if not unique_deps:
        return ""

    parts: list[str] = [
        "## Dependency Files — cross-validate every call site against these signatures\n"
    ]
    found_any = False

    for dep_name in unique_deps:
        dep_file = _resolve_object_to_file(dep_name, obj_to_file)
        if dep_file is None or not dep_file.exists():
            parts.append(
                f"### ⚠️  {dep_name}\n"
                f"Output file not found — any import or call to this object will fail at runtime.\n"
            )
            found_any = True
            continue

        try:
            content = dep_file.read_text(encoding="utf-8")
            sigs = _extract_signatures(content)
            parts.append(
                f"### {dep_file.name}  (SQL object: {dep_name})\n"
                f"```python\n{sigs}\n```\n"
            )
            found_any = True
        except OSError as e:
            logger.debug("Could not read dep file %s: %s", dep_file, e)

    return "\n".join(parts) if found_any else ""


# ── Local Syntax Check ────────────────────────────────────────────────────────


def _check_syntax_local(file_path: Path) -> ValidationResult:
    """Check Python syntax using ast.parse(). Zero API cost."""
    result = ValidationResult(file_path=str(file_path))

    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError as e:
        result.issues.append(ValidationIssue(
            file=file_path.name, severity="error", message=f"Cannot read file: {e}",
        ))
        return result

    try:
        ast.parse(content)
        result.syntax_valid = True
    except SyntaxError as e:
        result.syntax_valid = False
        result.issues.append(ValidationIssue(
            file=file_path.name,
            severity="error",
            message=f"Syntax error: {e.msg}",
            line=e.lineno,
        ))
        return result

    # Quick pattern checks (free, no API)
    lines = content.splitlines()
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            if "TODO" in stripped:
                result.todos_found += 1
            continue

        # Bare col() without F. prefix
        if "col(" in stripped and "F.col(" not in stripped and "from_col(" not in stripped:
            if not stripped.startswith('"'):
                result.issues.append(ValidationIssue(
                    file=file_path.name, severity="warning",
                    message="Possible bare col() without F. prefix", line=i,
                ))

        # .collect() risk
        if ".collect()" in stripped:
            result.issues.append(ValidationIssue(
                file=file_path.name, severity="warning",
                message=".collect() found — may cause OOM on large datasets", line=i,
            ))

        # Count TODOs in non-comment lines too
        if "TODO" in stripped:
            result.todos_found += 1

    return result


# ── Claude Review ─────────────────────────────────────────────────────────────


async def _validate_with_claude(
    file_path: Path,
    dep_context: str,
    options: ClaudeAgentOptions,
    config: ConverterConfig,
) -> ValidationResult:
    """Validate PySpark code with Claude for correctness.

    Injects dep_context (dependency file signatures) when available so Claude
    can cross-check that called functions exist with the correct signatures.
    """
    abs_path = file_path.resolve()

    dep_section = f"\n\n{dep_context}\n" if dep_context else ""
    cross_check_item = (
        "\n8. Cross-file: every function called that appears in the dependency files above "
        "must exist with a matching signature and argument count."
        if dep_context else ""
    )

    prompt = f"""Read and validate the PySpark file at {abs_path}.
{dep_section}
Check against the validation checklist in your system prompt. Pay special attention to:
1. DATEDIFF argument order (PySpark: end, start — reversed vs SQL Server)
2. Case-sensitive string comparisons (use F.lower() or .ilike())
3. NULL ordering — be explicit: asc_nulls_first() / desc_nulls_last()
4. Window frame defaults (running totals need rowsBetween, not RANGE)
5. Python UDFs where native F.xxx functions exist
6. SparkSession missing .config("spark.sql.decimalOperations.allowPrecisionLoss", False)
7. Deprecated methods: .unionAll() → .union(), .registerTempTable() → .createOrReplaceTempView(){cross_check_item}

Return ONLY valid JSON:
{{
  "syntax_valid": true,
  "pyspark_correct": false,
  "dependencies_resolved": true,
  "issues": [
    {{"file": "filename.py", "severity": "HIGH", "message": "...", "line": 42}}
  ],
  "todos_found": 3
}}"""

    result = ValidationResult(file_path=str(file_path), syntax_valid=True)
    collected_text: list[str] = []

    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        collected_text.append(block.text)

            elif isinstance(message, ResultMessage):
                result.cost_usd = message.total_cost_usd

                review_data = None
                for text_source in [
                    collected_text[-1] if collected_text else "",
                    "\n".join(collected_text),
                    message.result or "",
                ]:
                    if text_source:
                        review_data = _extract_json(text_source)
                        if review_data:
                            break

                if review_data:
                    result.pyspark_correct = review_data.get("pyspark_correct", True)
                    result.dependencies_resolved = review_data.get("dependencies_resolved", True)
                    result.todos_found = review_data.get("todos_found", 0)

                    for issue in review_data.get("issues", []):
                        result.issues.append(ValidationIssue(
                            file=issue.get("file", file_path.name),
                            severity=issue.get("severity", "warning"),
                            message=issue.get("message", ""),
                            line=issue.get("line"),
                        ))

                dep_flag = " [+dep-ctx]" if dep_context else ""
                logger.info(
                    "  Review%s: $%.4f | correct=%s | deps=%s | issues=%d",
                    dep_flag, result.cost_usd, result.pyspark_correct,
                    result.dependencies_resolved, len(result.issues),
                )

    except Exception as e:
        logger.error("  Validation failed: %s", e)
        result.issues.append(ValidationIssue(
            file=file_path.name, severity="error", message=f"Validation error: {e}",
        ))

    return result


def _extract_json(text: str) -> dict | None:
    """Extract JSON object from response text."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    if "```json" in text:
        try:
            start = text.index("```json") + len("```json")
            end = text.index("```", start)
            return json.loads(text[start:end].strip())
        except (ValueError, json.JSONDecodeError):
            pass

    brace_start = text.find("{")
    if brace_start != -1:
        brace_end = text.rfind("}")
        if brace_end > brace_start:
            try:
                return json.loads(text[brace_start: brace_end + 1])
            except json.JSONDecodeError:
                pass

    return None
