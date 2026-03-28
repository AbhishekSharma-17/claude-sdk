"""03 — Edit Tool Demo

The Edit tool lets Claude do precise find-and-replace edits in existing files.
Unlike Write (which overwrites the whole file), Edit modifies only the matched section.

Tool input schema:
    file_path: str   — Absolute path to the file
    old_string: str  — Exact text to find (must be unique in the file)
    new_string: str  — Replacement text

Usage: python examples/tools/03_edit_tool.py
Requires: ANTHROPIC_API_KEY environment variable
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"


async def main() -> None:
    # Copy sample.py to a temp dir so we don't modify the original
    with tempfile.TemporaryDirectory() as tmp:
        work_file = Path(tmp) / "sample.py"
        shutil.copy(SAMPLE_DIR / "sample.py", work_file)

        print("--- Edit Tool Demo ---")
        print(f"Working on copy: {work_file}")
        print(f"Before edit (line 24): {work_file.read_text().splitlines()[23]}\n")

        options = ClaudeAgentOptions(
            model="haiku",
            allowed_tools=["Read", "Edit"],  # Read first, then Edit
            permission_mode="bypassPermissions",
            max_turns=3,
            system_prompt="You are a bug fixer. Read the file, find bugs, and fix them using the Edit tool.",
        )

        prompt = (
            f"Read {work_file} and fix the bug in create_user() where the ID is hardcoded to 1. "
            "Use a random int instead. Use the Edit tool to make the fix."
        )

        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        print(f"[TOOL CALL] {block.name}")
                        if block.name == "Edit":
                            print(f"  old_string: {block.input.get('old_string', '')!r}")
                            print(f"  new_string: {block.input.get('new_string', '')!r}")
                        elif block.name == "Read":
                            print(f"  file_path: {block.input.get('file_path')}")

                    elif isinstance(block, TextBlock):
                        print(f"\n[CLAUDE] {block.text}")

            elif isinstance(message, ResultMessage):
                print(f"\n--- Result ---")
                print(f"Cost: ${message.total_cost_usd or 0:.4f}")
                print(f"\nAfter edit (create_user function):")
                for i, line in enumerate(work_file.read_text().splitlines()):
                    if "def create_user" in line or "User(id=" in line or "randint" in line.lower():
                        print(f"  L{i+1}: {line}")


if __name__ == "__main__":
    asyncio.run(main())
