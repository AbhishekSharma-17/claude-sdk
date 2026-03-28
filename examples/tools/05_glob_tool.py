"""05 — Glob Tool Demo

The Glob tool lets Claude find files by pattern matching (like shell globbing).
Supports ** for recursive matching. Results are sorted by modification time.

Tool input schema:
    pattern: str     — Glob pattern (e.g., "**/*.py", "src/**/*.ts")
    path: str | None — Directory to search in (defaults to cwd)

Usage: python examples/tools/05_glob_tool.py
Requires: ANTHROPIC_API_KEY environment variable
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock, ToolResultBlock

PROJECT_DIR = Path(__file__).parent.parent.parent  # Claude agent sdk/


async def main() -> None:
    options = ClaudeAgentOptions(
        model="haiku",
        allowed_tools=["Glob"],
        permission_mode="bypassPermissions",
        max_turns=3,
        system_prompt="You are a file explorer. Use Glob to find files and report what you find.",
    )

    prompt = (
        f"Use the Glob tool to find all Python files (**/*.py) and all SQL files (**/*.sql) "
        f"in the directory {PROJECT_DIR}. List what you find."
    )

    print("--- Glob Tool Demo ---")
    print(f"Searching in: {PROJECT_DIR}\n")

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    print(f"[TOOL CALL] {block.name}")
                    print(f"  pattern: {block.input.get('pattern')}")
                    print(f"  path: {block.input.get('path', '(default)')}")

                elif isinstance(block, ToolResultBlock):
                    output = block.content or ""
                    print(f"[TOOL RESULT]\n{output[:500]}")

                elif isinstance(block, TextBlock):
                    print(f"\n[CLAUDE] {block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n--- Result ---")
            print(f"Cost: ${message.total_cost_usd or 0:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
