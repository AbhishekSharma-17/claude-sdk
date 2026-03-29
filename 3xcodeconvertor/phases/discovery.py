"""Phase 1: Discovery & Complexity Analysis.

Reads SQL files, identifies all objects, detects dialect, scores complexity.
Uses query() per file with structured output.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from config import ConverterConfig
from models import FileInventory

logger = logging.getLogger(__name__)


async def discover_file(
    file_path: Path,
    options: ClaudeAgentOptions,
    config: ConverterConfig,
) -> tuple[FileInventory, float]:
    """Discover all SQL objects in a single file.

    Args:
        file_path: Path to the SQL file.
        options: ClaudeAgentOptions for discovery phase.
        config: Converter configuration.

    Returns:
        Tuple of (FileInventory, cost_usd).
    """
    abs_path = file_path.resolve()
    line_count = _count_lines(abs_path)

    # Build prompt based on file size
    if line_count <= config.large_file_threshold:
        read_instruction = f"Read the file at {abs_path} completely."
    else:
        chunk1_limit = config.chunk_size
        chunk2_offset = config.chunk_size
        chunk2_limit = line_count - config.chunk_size
        read_instruction = (
            f"Read the file at {abs_path} in two chunks:\n"
            f"  - First: offset=0, limit={chunk1_limit}\n"
            f"  - Then: offset={chunk2_offset}, limit={chunk2_limit}\n"
            f"Combine both reads into a single complete inventory."
        )

    prompt = f"""Analyze this SQL file and return a structured inventory.

File: {abs_path}
Total lines: {line_count}

{read_instruction}

First, use the sql_prescan tool to get a quick scan of the file, then read the actual SQL to build the full inventory. Return the complete JSON inventory with all objects, their line ranges, parameters, references, complexity scores, and constructs used."""

    logger.info("Discovering: %s (%d lines)", file_path.name, line_count)

    cost_usd = 0.0
    inventory_data: dict | None = None
    collected_text: list[str] = []  # Collect ALL text from assistant messages

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    collected_text.append(block.text)
                    if config.verbose:
                        logger.debug("  Text: %s", block.text[:300])
                elif isinstance(block, ToolUseBlock):
                    if config.verbose:
                        logger.debug("  Tool: %s", block.name)

        elif isinstance(message, ResultMessage):
            cost_usd = message.total_cost_usd
            logger.info(
                "  Discovery complete: $%.4f | %d turns | %dms",
                cost_usd, message.num_turns, message.duration_ms,
            )

    # Try extracting JSON from multiple sources (in priority order)
    # 1. The last assistant text block (most likely to contain the final JSON)
    # 2. All collected text concatenated
    # 3. ResultMessage.result (sometimes empty)
    for text_source in [
        collected_text[-1] if collected_text else "",
        "\n".join(collected_text),
    ]:
        if text_source:
            inventory_data = _extract_json(text_source)
            if inventory_data:
                logger.debug("  Parsed inventory JSON from assistant text (%d chars)", len(text_source))
                break

    if not inventory_data:
        logger.error("  Failed to get inventory for %s", file_path.name)
        if collected_text:
            # Log what we got so we can debug
            last_text = collected_text[-1][:500] if collected_text else "(empty)"
            logger.error("  Last assistant text: %s", last_text)
        return FileInventory(
            file_path=str(file_path),
            total_lines=line_count,
            dialect="unknown",
        ), cost_usd

    try:
        inventory = FileInventory.model_validate(inventory_data)
    except Exception as e:
        logger.error("  Failed to parse inventory: %s", e)
        inventory = FileInventory(
            file_path=str(file_path),
            total_lines=line_count,
            dialect="unknown",
        )

    return inventory, cost_usd


def _count_lines(file_path: Path) -> int:
    """Count lines in a file efficiently."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def _extract_json(text: str) -> dict | None:
    """Extract JSON from Claude's response, handling markdown code blocks."""
    text = text.strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from ```json ... ``` block
    if "```json" in text:
        try:
            start = text.index("```json") + len("```json")
            end = text.index("```", start)
            return json.loads(text[start:end].strip())
        except (ValueError, json.JSONDecodeError):
            pass

    # Try extracting from ``` ... ``` block
    if "```" in text:
        try:
            start = text.index("```") + 3
            # Skip language identifier if present
            newline = text.index("\n", start)
            end = text.index("```", newline)
            return json.loads(text[newline:end].strip())
        except (ValueError, json.JSONDecodeError):
            pass

    # Try finding first { to last }
    brace_start = text.find("{")
    if brace_start != -1:
        brace_end = text.rfind("}")
        if brace_end > brace_start:
            try:
                return json.loads(text[brace_start : brace_end + 1])
            except json.JSONDecodeError:
                pass

    return None
