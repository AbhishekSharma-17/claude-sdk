"""01 — Read Tool Demo

The Read tool lets Claude read file contents, images, PDFs, and Jupyter notebooks.
It supports offset/limit for large files (Claude reads in chunks of ~200 lines).

Tool input schema:
    file_path: str      — Absolute path to the file
    offset: int | None  — Line number to start from (0-indexed)
    limit: int | None   — Max lines to read (default ~2000)

Usage: python examples/tools/01_read_tool.py
Requires: ANTHROPIC_API_KEY environment variable
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock, ToolResultBlock

SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"


async def main() -> None:
    sql_file = SAMPLE_DIR / "sample.sql"

    options = ClaudeAgentOptions(
        model="haiku",
        allowed_tools=["Read"],
        permission_mode="bypassPermissions",
        max_turns=3,
        system_prompt="You are a SQL analyst. Read the file and summarize its contents concisely.",
    )

    prompt = f"Read the file at {sql_file} and tell me what SQL constructs it uses."

    print(f"--- Read Tool Demo ---")
    print(f"Prompt: {prompt}\n")

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    print(f"[TOOL CALL] {block.name}")
                    print(f"  file_path: {block.input.get('file_path')}")
                    if block.input.get("offset"):
                        print(f"  offset: {block.input['offset']}, limit: {block.input.get('limit')}")

                elif isinstance(block, ToolResultBlock):
                    preview = (block.content or "")[:100]
                    print(f"[TOOL RESULT] ({len(block.content or '')} chars) {preview}...")

                elif isinstance(block, TextBlock):
                    print(f"\n[CLAUDE] {block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n--- Result ---")
            print(f"Cost: ${message.total_cost_usd or 0:.4f}")
            print(f"Turns: {message.num_turns}")
            print(f"Duration: {message.duration_ms}ms")


if __name__ == "__main__":
    asyncio.run(main())
