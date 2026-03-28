"""04 — Bash Tool Demo

The Bash tool lets Claude execute shell commands. It runs in a sandboxed subprocess
with configurable timeout and working directory.

Tool input schema:
    command: str     — The shell command to execute
    timeout: int     — Optional timeout in milliseconds (max 600000)

Usage: python examples/tools/04_bash_tool.py
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
        allowed_tools=["Bash"],
        permission_mode="bypassPermissions",
        max_turns=3,
        cwd=str(SAMPLE_DIR),
        system_prompt=(
            "You are a system administrator. Use bash commands to answer questions. "
            "Be concise. Only run safe, read-only commands."
        ),
    )

    prompt = (
        "Using bash commands: "
        "1) Count how many lines are in each file in the current directory, "
        "2) Show the Python version installed, "
        "3) Show disk usage of the current directory."
    )

    print("--- Bash Tool Demo ---")
    print(f"Working directory: {SAMPLE_DIR}")
    print(f"Prompt: {prompt[:80]}...\n")

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    print(f"[TOOL CALL] {block.name}")
                    print(f"  command: {block.input.get('command')}")

                elif isinstance(block, ToolResultBlock):
                    output = block.content or ""
                    print(f"[TOOL RESULT]\n{output[:300]}")

                elif isinstance(block, TextBlock):
                    print(f"\n[CLAUDE] {block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n--- Result ---")
            print(f"Cost: ${message.total_cost_usd or 0:.4f}")
            print(f"Turns: {message.num_turns}")


if __name__ == "__main__":
    asyncio.run(main())
