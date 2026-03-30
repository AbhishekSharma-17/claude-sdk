"""Phase 3: SQL-to-PySpark Conversion.

Converts each SQL object to PySpark code using targeted instructions from Phase 2.
Supports both automated (parallel query()) and interactive (ClaudeSDKClient) modes.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from config import ConverterConfig
from models import (
    ConversionPlan,
    ConversionResult,
    ConversionStatus,
    FileInventory,
    ObjectPlan,
    OutputGroup,
    SQLObject,
)

logger = logging.getLogger(__name__)


# ── Public API ────────────────────────────────────────────────────────────────


async def convert_all(
    inventories: list[FileInventory],
    plan: ConversionPlan,
    options: ClaudeAgentOptions,
    interactive_options: ClaudeAgentOptions | None,
    config: ConverterConfig,
) -> list[ConversionResult]:
    """Convert all objects according to the conversion plan.

    Processes objects level-by-level. Within each level, objects are converted
    in parallel (automated mode) or sequentially (interactive mode).

    Returns list of ConversionResult for each object.
    """
    # Build lookup: object_name -> (SQLObject, FileInventory)
    obj_lookup: dict[str, tuple[SQLObject, FileInventory]] = {}
    for inv in inventories:
        for obj in inv.objects:
            obj_lookup[obj.name] = (obj, inv)

    results: list[ConversionResult] = []
    registry: dict[str, str] = {}  # object_name -> signature
    total_cost = 0.0

    for level in plan.conversion_levels:
        logger.info("Converting level %d: %s (%d objects)", level.level, level.description, len(level.objects))

        level_objects = [
            (name, obj_lookup.get(name), plan.object_plans.get(name))
            for name in level.objects
            if name in obj_lookup
        ]

        if config.interactive and interactive_options:
            level_results = await _convert_level_interactive(
                level_objects, registry, interactive_options, config,
            )
        else:
            level_results = await _convert_level_parallel(
                level_objects, registry, options, config,
            )

        # Update registry with successful conversions
        for result in level_results:
            results.append(result)
            total_cost += result.cost_usd
            if result.status == ConversionStatus.CONVERTED and result.signature:
                registry[result.object_name] = result.signature

            # Budget check
            if total_cost >= config.total_budget_usd:
                logger.warning("Budget limit reached ($%.2f). Stopping conversion.", total_cost)
                return results

    return results


async def convert_all_grouped(
    inventories: list[FileInventory],
    plan: ConversionPlan,
    output_groups: list[OutputGroup],
    options: ClaudeAgentOptions,
    interactive_options: ClaudeAgentOptions | None,
    config: ConverterConfig,
) -> list[ConversionResult]:
    """Convert SQL objects grouped into production-style output modules.

    Each OutputGroup becomes a single .py file. Groups are converted in
    dependency order: utilities first, then standalone, then main pipeline.
    """
    # Build lookup: object_name -> (SQLObject, FileInventory)
    obj_lookup: dict[str, tuple[SQLObject, FileInventory]] = {}
    for inv in inventories:
        for obj in inv.objects:
            obj_lookup[obj.name] = (obj, inv)

    results: list[ConversionResult] = []
    registry: dict[str, str] = {}  # group_name -> exported signatures
    total_cost = 0.0

    # Sort groups: utilities first, standalone next, main_pipeline last
    group_order = {"utilities": 0, "standalone": 1, "main_pipeline": 2}
    sorted_groups = sorted(output_groups, key=lambda g: group_order.get(g.group_type, 1))

    for group in sorted_groups:
        # Collect objects for this group
        group_objects: list[tuple[str, SQLObject, FileInventory, ObjectPlan | None]] = []
        for name in group.objects:
            if name in obj_lookup:
                obj, inv = obj_lookup[name]
                obj_plan = plan.object_plans.get(name)
                group_objects.append((name, obj, inv, obj_plan))

        if not group_objects:
            continue

        result = await _convert_group(
            group=group,
            objects=group_objects,
            registry=registry,
            options=options,
            config=config,
        )

        results.append(result)
        total_cost += result.cost_usd

        if result.status == ConversionStatus.CONVERTED and result.signature:
            registry[group.group_name] = result.signature

        if total_cost >= config.total_budget_usd:
            logger.warning("Budget limit reached ($%.2f). Stopping conversion.", total_cost)
            return results

    return results


async def _convert_group(
    group: OutputGroup,
    objects: list[tuple[str, SQLObject, FileInventory, ObjectPlan | None]],
    registry: dict[str, str],
    options: ClaudeAgentOptions,
    config: ConverterConfig,
) -> ConversionResult:
    """Convert a group of related SQL objects into a single .py module."""
    output_path = config.pyspark_output_dir / group.output_filename

    # Build the multi-object source section
    source_sections: list[str] = []
    instructions_sections: list[str] = []
    all_references: list[str] = []

    for name, obj, inv, obj_plan in objects:
        source_sections.append(
            f"### {name} ({obj.type}, lines {obj.start_line}-{obj.end_line}, "
            f"{obj.line_count} lines, {obj.complexity_level})\n"
            f"Read using: Read tool with file_path=\"{Path(inv.file_path).resolve()}\", "
            f"offset={obj.start_line - 1}, limit={obj.line_count}"
        )

        if obj_plan:
            instr = "\n".join(f"    - {inst}" for inst in obj_plan.conversion_instructions)
            gotchas = "\n".join(f"    - {g}" for g in obj_plan.gotchas_relevant)
            section = f"  **{name}**:\n{instr}"
            if gotchas:
                section += f"\n  Gotchas:\n{gotchas}"
            if obj_plan.limitations_found:
                lims = "\n".join(f"    - {lim}" for lim in obj_plan.limitations_found)
                section += f"\n  LIMITATIONS (add TODO comments):\n{lims}"
            instructions_sections.append(section)

        all_references.extend(obj.references)

    # Build dependency context from previously converted groups
    dep_context = _build_dependency_context(
        list(set(all_references) - {name for name, *_ in objects}),
        registry,
    )

    dialect = objects[0][2].dialect if objects else "unknown"
    object_names = ", ".join(name for name, *_ in objects)

    # Determine module description based on group type
    if group.group_type == "utilities":
        module_guidance = (
            "This is a **utilities module**. Organize as:\n"
            "  - Shared imports at top\n"
            "  - Pure functions first (no SparkSession dependency)\n"
            "  - Utility classes/helpers next\n"
            "  - No CLI entry point needed — this is imported by other modules"
        )
    elif group.group_type == "main_pipeline":
        module_guidance = (
            "This is the **main pipeline module**. Organize as:\n"
            "  - Imports at top (including from utils if applicable)\n"
            "  - Private helper functions (_step_*, _helper_*)\n"
            "  - Main `run_pipeline(spark, params)` function that orchestrates all steps\n"
            "  - CLI entry point with `if __name__ == '__main__':`"
        )
    else:
        module_guidance = (
            "This is a **standalone module** (independently schedulable job). Include:\n"
            "  - `run_pipeline(spark, params)` entry point\n"
            "  - CLI with `if __name__ == '__main__':`"
        )

    prompt = f"""Convert these related SQL objects into a single production-quality PySpark module.

## OUTPUT FILE
Write to: {output_path.resolve()}
Module: {group.output_filename} ({group.group_type})

## MODULE STRUCTURE
{module_guidance}

## SQL OBJECTS TO CONVERT ({len(objects)} objects)
Dialect: {dialect}
Objects: {object_names}

{chr(10).join(source_sections)}

Read ALL source sections above before starting conversion.

## CONVERSION INSTRUCTIONS (from analysis phase)
{chr(10).join(instructions_sections) or "Follow standard conversion patterns for all objects."}

## DEPENDENCY CONTEXT (other modules you may reference)
{dep_context or "No external dependencies — this group is self-contained."}

## RULES
- Combine all objects into ONE cohesive .py file
- Objects within this module should call each other directly (no imports needed)
- Use `from pyspark.sql import functions as F` — always use F. prefix
- If this module imports from utils.py, use `from utils import <function_name>`
- After writing, use the validate_pyspark_syntax tool to check the output file
- If validation fails, fix the error and rewrite"""

    logger.info(
        "  Converting group [%s]: %s → %s (%d objects)",
        group.group_type, group.group_name, group.output_filename, len(objects),
    )

    result = ConversionResult(
        object_name=group.group_name,
        output_file=str(output_path),
    )

    for attempt in range(config.max_retries):
        try:
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    if config.verbose:
                        for block in message.content:
                            if isinstance(block, ToolUseBlock):
                                logger.debug("    Tool: %s", block.name)

                elif isinstance(message, ResultMessage):
                    result.cost_usd = message.total_cost_usd
                    result.turns_used = message.num_turns
                    result.duration_ms = message.duration_ms
                    result.session_id = message.session_id

                    if output_path.exists():
                        result.status = ConversionStatus.CONVERTED
                        result.signature = _extract_group_signatures(output_path)
                        logger.info(
                            "    Converted [%s]: $%.4f | %d turns | %dms",
                            group.output_filename,
                            result.cost_usd, result.turns_used, result.duration_ms,
                        )
                    else:
                        result.status = ConversionStatus.FAILED
                        result.error = "Output file was not created"
                        logger.warning("    Failed: output file not created")

            break  # Success, no retry needed

        except Exception as e:
            logger.warning("    Attempt %d failed: %s", attempt + 1, e)
            if attempt < config.max_retries - 1:
                wait = config.retry_backoff_base ** attempt
                logger.info("    Retrying in %.1fs...", wait)
                await asyncio.sleep(wait)
            else:
                result.status = ConversionStatus.FAILED
                result.error = str(e)

    return result


def _extract_group_signatures(file_path: Path) -> str:
    """Extract all public function signatures from a grouped module."""
    try:
        content = file_path.read_text(encoding="utf-8")
        sigs: list[str] = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("def ") and not stripped.startswith("def _"):
                sigs.append(stripped.rstrip(":"))
        return "; ".join(sigs) if sigs else ""
    except OSError:
        return ""


# ── Parallel Conversion (Automated Mode) ──────────────────────────────────────


async def _convert_level_parallel(
    objects: list[tuple[str, tuple[SQLObject, FileInventory] | None, ObjectPlan | None]],
    registry: dict[str, str],
    options: ClaudeAgentOptions,
    config: ConverterConfig,
) -> list[ConversionResult]:
    """Convert objects at one dependency level in parallel."""
    semaphore = asyncio.Semaphore(config.max_parallel_conversions)

    async def _bounded_convert(
        name: str,
        obj_info: tuple[SQLObject, FileInventory] | None,
        obj_plan: ObjectPlan | None,
    ) -> ConversionResult:
        async with semaphore:
            return await _convert_single_object(name, obj_info, obj_plan, registry, options, config)

    tasks = [
        _bounded_convert(name, obj_info, obj_plan)
        for name, obj_info, obj_plan in objects
    ]
    return list(await asyncio.gather(*tasks, return_exceptions=False))


async def _convert_single_object(
    name: str,
    obj_info: tuple[SQLObject, FileInventory] | None,
    obj_plan: ObjectPlan | None,
    registry: dict[str, str],
    options: ClaudeAgentOptions,
    config: ConverterConfig,
) -> ConversionResult:
    """Convert a single SQL object to PySpark via query()."""
    if not obj_info:
        return ConversionResult(
            object_name=name,
            status=ConversionStatus.FAILED,
            error=f"Object '{name}' not found in inventory",
        )

    obj, inv = obj_info
    output_filename = _to_snake_case(name) + ".py"
    output_path = config.pyspark_output_dir / output_filename

    # Build dependency context
    dep_context = _build_dependency_context(obj.references, registry)

    # Build conversion instructions from plan
    instructions = ""
    gotchas = ""
    if obj_plan:
        instructions = "\n".join(f"  - {inst}" for inst in obj_plan.conversion_instructions)
        gotchas = "\n".join(f"  - {g}" for g in obj_plan.gotchas_relevant)
        if obj_plan.limitations_found:
            instructions += "\n\n  LIMITATIONS (add TODO comments):\n"
            instructions += "\n".join(f"  - {lim}" for lim in obj_plan.limitations_found)

    prompt = f"""Convert this SQL {obj.type} to production-quality PySpark.

## SOURCE
File: {inv.file_path} (lines {obj.start_line}-{obj.end_line}, {obj.line_count} lines)
Dialect: {inv.dialect}
Complexity: {obj.complexity_level} (score: {obj.complexity_score})

Read the source using: Read tool with file_path="{Path(inv.file_path).resolve()}", offset={obj.start_line - 1}, limit={obj.line_count}

## CONVERSION INSTRUCTIONS (from analysis phase)
{instructions or "Follow standard conversion patterns."}

## RELEVANT GOTCHAS TO CHECK
{gotchas or "Check all 10 critical gotchas."}

## DEPENDENCY CONTEXT (already-converted objects you may reference)
{dep_context or "No dependencies — this object is standalone."}

## OUTPUT
Write the converted PySpark code to: {output_path.resolve()}

After writing, use the validate_pyspark_syntax tool to check the output file.
If validation fails, fix the error and rewrite."""

    logger.info("  Converting: %s (%s, %d lines, complexity: %s)",
                name, obj.type, obj.line_count, obj.complexity_level)

    result = ConversionResult(object_name=name, output_file=str(output_path))

    for attempt in range(config.max_retries):
        try:
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    if config.verbose:
                        for block in message.content:
                            if isinstance(block, ToolUseBlock):
                                logger.debug("    Tool: %s", block.name)

                elif isinstance(message, ResultMessage):
                    result.cost_usd = message.total_cost_usd
                    result.turns_used = message.num_turns
                    result.duration_ms = message.duration_ms
                    result.session_id = message.session_id

                    if output_path.exists():
                        result.status = ConversionStatus.CONVERTED
                        result.signature = _extract_signature(output_path, name)
                        logger.info(
                            "    Converted: $%.4f | %d turns | %dms",
                            result.cost_usd, result.turns_used, result.duration_ms,
                        )
                    else:
                        result.status = ConversionStatus.FAILED
                        result.error = "Output file was not created"
                        logger.warning("    Failed: output file not created")

            break  # Success, no retry needed

        except Exception as e:
            logger.warning("    Attempt %d failed: %s", attempt + 1, e)
            if attempt < config.max_retries - 1:
                wait = config.retry_backoff_base ** attempt
                logger.info("    Retrying in %.1fs...", wait)
                await asyncio.sleep(wait)
            else:
                result.status = ConversionStatus.FAILED
                result.error = str(e)

    return result


# ── Interactive Conversion ────────────────────────────────────────────────────


async def _convert_level_interactive(
    objects: list[tuple[str, tuple[SQLObject, FileInventory] | None, ObjectPlan | None]],
    registry: dict[str, str],
    options: ClaudeAgentOptions,
    config: ConverterConfig,
) -> list[ConversionResult]:
    """Convert objects interactively with human-in-the-loop."""
    results: list[ConversionResult] = []

    for name, obj_info, obj_plan in objects:
        if not obj_info:
            results.append(ConversionResult(
                object_name=name,
                status=ConversionStatus.FAILED,
                error=f"Object '{name}' not found",
            ))
            continue

        obj, inv = obj_info
        output_filename = _to_snake_case(name) + ".py"
        output_path = config.pyspark_output_dir / output_filename
        dep_context = _build_dependency_context(obj.references, registry)

        instructions = ""
        if obj_plan:
            instructions = "\n".join(f"  - {inst}" for inst in obj_plan.conversion_instructions)

        prompt = f"""Convert this SQL {obj.type} to PySpark.

File: {inv.file_path} (lines {obj.start_line}-{obj.end_line})
Dialect: {inv.dialect} | Complexity: {obj.complexity_level}

Read the source: Read tool, file_path="{Path(inv.file_path).resolve()}", offset={obj.start_line - 1}, limit={obj.line_count}

Conversion instructions:
{instructions or "Follow standard patterns."}

Dependencies:
{dep_context or "None."}

Write output to: {output_path.resolve()}

If you encounter ambiguous SQL patterns, use AskUserQuestion to clarify.
After writing, validate syntax with validate_pyspark_syntax tool."""

        logger.info("  [Interactive] Converting: %s", name)
        result = ConversionResult(object_name=name, output_file=str(output_path))

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(prompt)

                async for message in client.receive_response():
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                print(block.text)
                            elif isinstance(block, ToolUseBlock):
                                if block.name == "AskUserQuestion":
                                    questions = block.input.get("questions", [])
                                    for q in questions:
                                        question_text = q.get("question", "")
                                        print(f"\n[Claude asks]: {question_text}")
                                        answer = input("> ")
                                        await client.query(answer)

                    elif isinstance(message, ResultMessage):
                        result.cost_usd = message.total_cost_usd
                        result.turns_used = message.num_turns
                        result.duration_ms = message.duration_ms

                # Check if file was created
                if output_path.exists():
                    print(f"\n  Output written to: {output_path}")
                    user_action = input("  [A]pprove / [R]evise / [S]kip? ").strip().lower()

                    if user_action.startswith("r"):
                        feedback = input("  Feedback: ")
                        await client.query(f"Please revise the conversion: {feedback}")
                        async for msg in client.receive_response():
                            if isinstance(msg, AssistantMessage):
                                for block in msg.content:
                                    if isinstance(block, TextBlock):
                                        print(block.text)
                            elif isinstance(msg, ResultMessage):
                                result.cost_usd += msg.total_cost_usd

                    if user_action.startswith("s"):
                        result.status = ConversionStatus.SKIPPED
                    else:
                        result.status = ConversionStatus.CONVERTED
                        result.signature = _extract_signature(output_path, name)
                else:
                    result.status = ConversionStatus.FAILED
                    result.error = "Output file not created"

        except Exception as e:
            result.status = ConversionStatus.FAILED
            result.error = str(e)
            logger.error("    Interactive conversion failed: %s", e)

        results.append(result)
        if result.status == ConversionStatus.CONVERTED and result.signature:
            registry[result.object_name] = result.signature

    return results


# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_dependency_context(references: list[str], registry: dict[str, str]) -> str:
    """Build compressed dependency context from already-converted objects."""
    if not references:
        return ""

    lines: list[str] = []
    for ref in references:
        if ref in registry:
            lines.append(f"  {ref}: {registry[ref]}")
        else:
            lines.append(f"  {ref}: (not yet converted)")

    return "\n".join(lines)


def _extract_signature(file_path: Path, object_name: str) -> str:
    """Extract the function signature from a generated PySpark file.

    Looks for the run_pipeline or main step function definition.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("def run_pipeline(") or stripped.startswith("def _step"):
                return stripped.rstrip(":")
            if stripped.startswith(f"def {_to_snake_case(object_name)}("):
                return stripped.rstrip(":")
        # Fallback: return the first def line
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("def ") and not stripped.startswith("def main("):
                return stripped.rstrip(":")
    except OSError:
        pass

    return f"def {_to_snake_case(object_name)}(spark: SparkSession) -> DataFrame"


def _to_snake_case(name: str) -> str:
    """Convert a SQL object name to snake_case Python filename."""
    import re
    # Remove common prefixes
    name = re.sub(r"^(usp_|sp_|fn_|vw_|trg_|dbo\.)", "", name, flags=re.IGNORECASE)
    # Convert CamelCase to snake_case
    name = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
    # Replace non-alphanumeric with underscore
    name = re.sub(r"[^a-zA-Z0-9]", "_", name)
    # Collapse multiple underscores and strip
    name = re.sub(r"_+", "_", name).strip("_").lower()
    return name or "unnamed"
