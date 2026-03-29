"""Phase 2: Dependency Analysis & Conversion Planning.

Builds dependency graph, determines conversion order, generates per-object
conversion instructions. This is the "thinking" phase that reads the full
knowledge base once and produces targeted instructions for Phase 3.
"""

from __future__ import annotations

import json
import logging

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from config import ConverterConfig
from models import ConversionPlan, FileInventory

logger = logging.getLogger(__name__)


async def build_conversion_plan(
    inventories: list[FileInventory],
    options: ClaudeAgentOptions,
    config: ConverterConfig,
) -> tuple[ConversionPlan, float]:
    """Analyze dependencies and create a conversion plan for all objects.

    Args:
        inventories: All FileInventory results from Phase 1.
        options: ClaudeAgentOptions for planning phase.
        config: Converter configuration.

    Returns:
        Tuple of (ConversionPlan, cost_usd).
    """
    # Compile all objects into a summary for the prompt
    all_objects_summary = []
    for inv in inventories:
        for obj in inv.objects:
            all_objects_summary.append({
                "name": obj.name,
                "type": obj.type,
                "file": inv.file_path,
                "dialect": inv.dialect,
                "start_line": obj.start_line,
                "end_line": obj.end_line,
                "line_count": obj.line_count,
                "parameters": [p.model_dump() for p in obj.parameters],
                "references": obj.references,
                "temp_tables_created": obj.temp_tables_created,
                "temp_tables_used": obj.temp_tables_used,
                "has_cursor": obj.has_cursor,
                "has_dynamic_sql": obj.has_dynamic_sql,
                "has_transaction": obj.has_transaction,
                "window_function_count": obj.window_function_count,
                "complexity_score": obj.complexity_score,
                "complexity_level": obj.complexity_level,
                "known_limitations": obj.known_limitations,
                "constructs_used": obj.constructs_used,
            })

    total_objects = len(all_objects_summary)
    logger.info("Planning conversion for %d objects across %d files", total_objects, len(inventories))

    prompt = f"""Analyze these {total_objects} SQL objects and create a comprehensive conversion plan.

## DISCOVERED OBJECTS

{json.dumps(all_objects_summary, indent=2)}

## INSTRUCTIONS

1. Build the dependency graph — map every cross-reference between objects
2. Topological sort into conversion levels:
   - Level 0: Views and standalone functions (no dependencies)
   - Level 1+: Objects depending only on lower levels
   - Precedence: Views → Functions → Procedures → Triggers
3. For EACH object, write SPECIFIC conversion instructions:
   - Reference exact SQL line numbers
   - Name the exact PySpark function/pattern to use for each construct
   - Flag specific gotchas by number (e.g., "#1 DATEDIFF reversed")
   - Note limitations needing TODO comments
   - Specify the dependency signatures needed
4. Set strategy per complexity level

Use the Grep tool to verify cross-file references if needed.

Return the complete conversion plan as JSON."""

    cost_usd = 0.0
    plan_data: dict | None = None

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            if config.verbose:
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        logger.debug("  Tool: %s", block.name)
                    elif isinstance(block, TextBlock):
                        logger.debug("  Text: %s", block.text[:200])

        elif isinstance(message, ResultMessage):
            cost_usd = message.total_cost_usd
            logger.info(
                "  Planning complete: $%.4f | %d turns | %dms",
                cost_usd, message.num_turns, message.duration_ms,
            )
            result_text = message.result or ""
            plan_data = _extract_json(result_text)

    if not plan_data:
        logger.error("  Failed to get conversion plan")
        return ConversionPlan(total_objects=total_objects), cost_usd

    try:
        plan = ConversionPlan.model_validate(plan_data)
    except Exception as e:
        logger.error("  Failed to parse conversion plan: %s", e)
        # Fallback: simple sequential plan
        plan = _build_fallback_plan(inventories)

    return plan, cost_usd


def _build_fallback_plan(inventories: list[FileInventory]) -> ConversionPlan:
    """Build a simple sequential conversion plan as fallback."""
    from models import ConversionLevel, ObjectPlan

    all_objects = []
    for inv in inventories:
        for obj in inv.objects:
            all_objects.append(obj)

    plan = ConversionPlan(
        total_objects=len(all_objects),
        conversion_levels=[
            ConversionLevel(
                level=0,
                description="All objects (fallback sequential plan)",
                objects=[obj.name for obj in all_objects],
                strategy="Sequential conversion",
            ),
        ],
        object_plans={
            obj.name: ObjectPlan(
                conversion_order=i,
                complexity=f"{obj.complexity_level} ({obj.complexity_score})",
                conversion_instructions=[
                    f"Convert {obj.type} '{obj.name}' (lines {obj.start_line}-{obj.end_line})",
                    "Follow standard conversion patterns from knowledge base",
                ],
                strategy="Standard conversion",
            )
            for i, obj in enumerate(all_objects)
        },
    )
    return plan


def _extract_json(text: str) -> dict | None:
    """Extract JSON from response text."""
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

    if "```" in text:
        try:
            start = text.index("```") + 3
            newline = text.index("\n", start)
            end = text.index("```", newline)
            return json.loads(text[newline:end].strip())
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
