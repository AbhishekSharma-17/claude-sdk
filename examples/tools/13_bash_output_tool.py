"""13 — BashOutput Tool Demo

The BashOutput tool lets Claude read output from a BACKGROUND bash process.
When Claude runs a long-running command with Bash (run_in_background=True),
it can later check the output using BashOutput.

Tool input schema:
    command: str  — The ID of the background process to read from

Typical flow:
    1. Claude calls Bash with run_in_background=True (e.g., "npm run dev")
    2. Later, Claude calls BashOutput to check if the server started
    3. Claude uses KillBash to stop it when done

Usage: python examples/tools/13_bash_output_tool.py
Requires: ANTHROPIC_API_KEY environment variable
"""

from __future__ import annotations

import asyncio

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock, ToolResultBlock


async def main() -> None:
    options = ClaudeAgentOptions(
        model="haiku",
        allowed_tools=["Bash", "BashOutput"],
        permission_mode="bypassPermissions",
        max_turns=4,
        system_prompt=(
            "You are a DevOps engineer. Start a background process, "
            "then check its output. Use Bash with run_in_background for long processes, "
            "then BashOutput to read the result."
        ),
    )

    prompt = (
        "Start a background bash process that runs 'sleep 1 && echo Server started on port 8080 && sleep 30'. "
        "Then use BashOutput to check if it printed the 'Server started' message. "
        "Report what you find."
    )

    print("--- BashOutput Tool Demo ---")
    print("Shows how to start background processes and read their output.\n")

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    print(f"[TOOL CALL] {block.name}")
                    if block.name == "Bash":
                        print(f"  command: {block.input.get('command')}")
                        print(f"  run_in_background: {block.input.get('run_in_background', False)}")
                    elif block.name == "BashOutput":
                        print(f"  task_id: {block.input}")

                elif isinstance(block, ToolResultBlock):
                    print(f"[TOOL RESULT] {(block.content or '')[:200]}")

                elif isinstance(block, TextBlock):
                    print(f"\n[CLAUDE] {block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n--- Result ---")
            print(f"Cost: ${message.total_cost_usd or 0:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
