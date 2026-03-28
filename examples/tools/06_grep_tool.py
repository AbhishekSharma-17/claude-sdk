"""06 — Grep Tool Demo

The Grep tool lets Claude search file contents using regex patterns (powered by ripgrep).
Supports filtering by file type, glob, and multiple output modes.

Tool input schema:
    pattern: str            — Regex pattern to search for
    path: str | None        — File or directory to search in
    output_mode: str        — "files_with_matches" | "content" | "count"
    type: str | None        — File type filter (e.g., "py", "sql", "js")
    glob: str | None        — Glob pattern filter (e.g., "*.py")
    -A/-B/-C: int           — Context lines (after/before/both)
    -i: bool                — Case insensitive search

Usage: python examples/tools/06_grep_tool.py
Requires: ANTHROPIC_API_KEY environment variable
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock, ToolResultBlock

SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"


async def main() -> None:
    options = ClaudeAgentOptions(
        model="haiku",
        allowed_tools=["Grep"],
        permission_mode="bypassPermissions",
        max_turns=4,
        system_prompt=(
            "You are a code analyst. Use Grep to search for patterns in code. "
            "Use different output modes (content, count, files_with_matches) to show "
            "the tool's capabilities."
        ),
    )

    prompt = (
        f"In the directory {SAMPLE_DIR}, use Grep to: "
        "1) Find all SQL keywords like SELECT, JOIN, WHERE (case insensitive) in .sql files — show matching lines, "
        "2) Count how many functions (def ...) are in the .py file, "
        "3) Find which files contain the word 'TODO'."
    )

    print("--- Grep Tool Demo ---")
    print(f"Searching in: {SAMPLE_DIR}\n")

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    print(f"[TOOL CALL] {block.name}")
                    print(f"  pattern: {block.input.get('pattern')}")
                    print(f"  path: {block.input.get('path', '(default)')}")
                    print(f"  output_mode: {block.input.get('output_mode', 'files_with_matches')}")
                    if block.input.get("-i"):
                        print(f"  case_insensitive: True")
                    if block.input.get("type"):
                        print(f"  type: {block.input['type']}")

                elif isinstance(block, ToolResultBlock):
                    output = block.content or ""
                    print(f"[TOOL RESULT]\n{output[:500]}")

                elif isinstance(block, TextBlock):
                    print(f"\n[CLAUDE] {block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n--- Result ---")
            print(f"Cost: ${message.total_cost_usd or 0:.4f}")
            print(f"Turns: {message.num_turns}")


if __name__ == "__main__":
    asyncio.run(main())
