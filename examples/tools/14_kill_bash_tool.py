"""14 — KillBash Tool Demo

The KillBash tool lets Claude stop a running background bash process.
Used in combination with Bash (run_in_background=True) and BashOutput.

Tool input schema:
    task_id: str  — ID of the background process to kill

Typical flow:
    1. Bash(run_in_background=True) → starts process, returns task_id
    2. BashOutput(task_id) → read the output
    3. KillBash(task_id) → stop the process

Usage: python examples/tools/14_kill_bash_tool.py
Requires: ANTHROPIC_API_KEY environment variable
"""

from __future__ import annotations

import asyncio

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock, ToolResultBlock


async def main() -> None:
    options = ClaudeAgentOptions(
        model="haiku",
        allowed_tools=["Bash", "BashOutput", "KillBash"],
        permission_mode="bypassPermissions",
        max_turns=5,
        system_prompt=(
            "You are a process manager. Start a background process, verify it's running, "
            "then kill it. Use Bash with run_in_background, BashOutput to check, and KillBash to stop."
        ),
    )

    prompt = (
        "1) Start a background bash process: 'while true; do echo tick; sleep 1; done', "
        "2) Wait a moment, then check its output with BashOutput, "
        "3) Kill it with KillBash, "
        "4) Confirm it's stopped."
    )

    print("--- KillBash Tool Demo ---")
    print("Shows the full lifecycle: start → check → kill a background process.\n")

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    print(f"[TOOL CALL] {block.name}")
                    for k, v in block.input.items():
                        val = str(v)[:100]
                        print(f"  {k}: {val}")

                elif isinstance(block, ToolResultBlock):
                    print(f"[TOOL RESULT] {(block.content or '')[:200]}")

                elif isinstance(block, TextBlock):
                    print(f"\n[CLAUDE] {block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n--- Result ---")
            print(f"Cost: ${message.total_cost_usd or 0:.4f}")
            print(f"Turns: {message.num_turns}")


if __name__ == "__main__":
    asyncio.run(main())
