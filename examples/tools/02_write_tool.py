"""02 — Write Tool Demo

The Write tool lets Claude create new files or completely overwrite existing ones.
For partial edits, use the Edit tool instead.

Tool input schema:
    file_path: str  — Absolute path to write to
    content: str    — Full file content

Usage: python examples/tools/02_write_tool.py
Requires: ANTHROPIC_API_KEY environment variable
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock, ToolResultBlock


async def main() -> None:
    # Use a temp directory so we don't pollute the project
    with tempfile.TemporaryDirectory() as tmp:
        output_file = Path(tmp) / "generated_utils.py"

        options = ClaudeAgentOptions(
            model="haiku",
            allowed_tools=["Write"],
            permission_mode="bypassPermissions",
            max_turns=2,
            system_prompt="You are a Python developer. Write clean, typed Python code.",
        )

        prompt = (
            f"Create a Python file at {output_file} with a utility module containing: "
            "1) A function `slugify(text: str) -> str` that converts text to URL-safe slugs, "
            "2) A function `truncate(text: str, max_len: int = 100) -> str` that truncates with '...'."
        )

        print(f"--- Write Tool Demo ---")
        print(f"Prompt: {prompt[:100]}...\n")

        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        print(f"[TOOL CALL] {block.name}")
                        print(f"  file_path: {block.input.get('file_path')}")
                        content = block.input.get("content", "")
                        print(f"  content length: {len(content)} chars")
                        print(f"  preview:\n{content[:200]}...")

                    elif isinstance(block, TextBlock):
                        print(f"\n[CLAUDE] {block.text}")

            elif isinstance(message, ResultMessage):
                print(f"\n--- Result ---")
                print(f"Cost: ${message.total_cost_usd or 0:.4f}")

                # Verify the file was created
                if output_file.exists():
                    print(f"File created successfully! ({output_file.stat().st_size} bytes)")
                    print(f"\n--- Generated File Contents ---")
                    print(output_file.read_text())
                else:
                    print("File was NOT created.")


if __name__ == "__main__":
    asyncio.run(main())
