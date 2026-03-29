"""Phase 4: Validation & Report Generation.

Validates generated PySpark code for syntax, correctness, and dependency resolution.
Uses local ast.parse() first (free), then Claude review with Sonnet.
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
    ConversionReport,
    ConversionResult,
    ConversionStatus,
    CostBreakdown,
    ValidationIssue,
    ValidationResult,
)

logger = logging.getLogger(__name__)


# ── Public API ────────────────────────────────────────────────────────────────


async def validate_all(
    output_files: list[Path],
    options: ClaudeAgentOptions,
    config: ConverterConfig,
) -> list[ValidationResult]:
    """Validate all generated PySpark files.

    Step 1: Local ast.parse() — free, catches syntax errors
    Step 2: Claude review with Sonnet — catches logic/pattern issues
    """
    results: list[ValidationResult] = []

    for file_path in output_files:
        logger.info("Validating: %s", file_path.name)

        # Step 1: Local syntax check (free)
        syntax_result = _check_syntax_local(file_path)

        if not syntax_result.syntax_valid:
            logger.warning("  Syntax error: %s", syntax_result.issues[0].message if syntax_result.issues else "unknown")
            results.append(syntax_result)
            continue

        # Step 2: Claude review (costs API tokens)
        claude_result = await _validate_with_claude(file_path, options, config)

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
) -> ConversionReport:
    """Generate the final conversion report."""
    converted = sum(1 for r in conversion_results if r.status == ConversionStatus.CONVERTED)
    failed = sum(1 for r in conversion_results if r.status == ConversionStatus.FAILED)
    skipped = sum(1 for r in conversion_results if r.status == ConversionStatus.SKIPPED)
    needs_review = sum(1 for r in conversion_results if r.status == ConversionStatus.NEEDS_REVIEW)

    all_issues: list[ValidationIssue] = []
    all_todos: list[str] = []
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
        todos=all_todos,
    )


# ── Local Syntax Check ────────────────────────────────────────────────────────


def _check_syntax_local(file_path: Path) -> ValidationResult:
    """Check Python syntax using ast.parse(). Zero API cost."""
    result = ValidationResult(file_path=str(file_path))

    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError as e:
        result.issues.append(ValidationIssue(
            file=str(file_path), severity="error", message=f"Cannot read file: {e}",
        ))
        return result

    try:
        ast.parse(content)
        result.syntax_valid = True
    except SyntaxError as e:
        result.syntax_valid = False
        result.issues.append(ValidationIssue(
            file=str(file_path),
            severity="error",
            message=f"Syntax error: {e.msg}",
            line=e.lineno,
        ))
        return result

    # Quick pattern checks (free)
    lines = content.splitlines()
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Check for bare col/lit without F. prefix
        if "col(" in stripped and "F.col(" not in stripped and "from_col(" not in stripped:
            if not stripped.startswith("#") and not stripped.startswith('"'):
                result.issues.append(ValidationIssue(
                    file=str(file_path), severity="warning",
                    message="Possible bare col() without F. prefix", line=i,
                ))

        # Check for .collect() usage
        if ".collect()" in stripped and not stripped.startswith("#"):
            result.issues.append(ValidationIssue(
                file=str(file_path), severity="warning",
                message=".collect() found — may cause OOM on large datasets", line=i,
            ))

        # Count TODOs
        if "TODO" in stripped:
            result.todos_found += 1

    return result


# ── Claude Review ─────────────────────────────────────────────────────────────


async def _validate_with_claude(
    file_path: Path,
    options: ClaudeAgentOptions,
    config: ConverterConfig,
) -> ValidationResult:
    """Validate PySpark code with Claude (Sonnet) for correctness."""
    abs_path = file_path.resolve()

    prompt = f"""Read and validate the PySpark file at {abs_path}.

Check against the validation checklist in your system prompt.
Pay special attention to:
1. DATEDIFF argument order (should be end, start in PySpark)
2. Case-sensitive string comparisons (should use F.lower() or .ilike())
3. NULL ordering (should be explicit asc_nulls_first/desc_nulls_last)
4. Window frame defaults (running totals should use rowsBetween, not RANGE)
5. Python UDFs where native F.xxx functions exist
6. All dependency functions referenced actually exist

Return your findings as JSON with: syntax_valid, pyspark_correct, dependencies_resolved, issues array, todos_found count."""

    result = ValidationResult(file_path=str(file_path), syntax_valid=True)

    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                result.cost_usd = message.total_cost_usd
                result_text = message.result or ""
                review_data = _extract_json(result_text)

                if review_data:
                    result.pyspark_correct = review_data.get("pyspark_correct", True)
                    result.dependencies_resolved = review_data.get("dependencies_resolved", True)
                    result.todos_found = review_data.get("todos_found", 0)

                    for issue in review_data.get("issues", []):
                        result.issues.append(ValidationIssue(
                            file=issue.get("file", str(file_path)),
                            severity=issue.get("severity", "warning"),
                            message=issue.get("message", ""),
                            line=issue.get("line"),
                        ))

                logger.info("  Review: $%.4f | correct=%s | deps=%s | issues=%d",
                            result.cost_usd, result.pyspark_correct,
                            result.dependencies_resolved, len(result.issues))

    except Exception as e:
        logger.error("  Validation failed: %s", e)
        result.issues.append(ValidationIssue(
            file=str(file_path), severity="error", message=f"Validation error: {e}",
        ))

    return result


def _extract_json(text: str) -> dict | None:
    """Extract JSON from response."""
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
                return json.loads(text[brace_start : brace_end + 1])
            except json.JSONDecodeError:
                pass

    return None
