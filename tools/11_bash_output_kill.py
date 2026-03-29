"""
Tool 11: BashOutput + Tool 12: KillBash
=========================================
Bash can run commands in the BACKGROUND.
BashOutput reads output from background processes.
KillBash stops background processes.

Normal Bash:        runs, waits, returns result (blocking)
Background Bash:    starts, returns immediately with PID
BashOutput:         reads output so far from that PID
KillBash:           kills the process by PID

Use case:
  - Start a dev server in background
  - Run a long task, check progress, then kill if needed
  - Tail logs while doing other work
"""

import asyncio
import os
from dotenv import load_dotenv
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, AssistantMessage, ToolUseBlock, TextBlock

load_dotenv()

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY")},
    allowed_tools=["Bash", "BashOutput", "KillBash"],
    permission_mode="bypassPermissions",
    max_turns=10,
)


async def main():
    print("=== Tools: BashOutput + KillBash ===\n")

    async for message in query(
        prompt="""
        1. Run "python3 sample_data/long_task.py" in the BACKGROUND
        2. Wait 3 seconds (sleep 3)
        3. Check the output so far using BashOutput
        4. Wait 3 more seconds
        5. Check output again
        6. Kill the process using KillBash
        7. Tell me how far it got before being killed
        """,
        options=options,
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    if block.name == "Bash":
                        bg = block.input.get("run_in_background", False)
                        tag = " [BACKGROUND]" if bg else ""
                        print(f"[Claude called] Bash{tag}:")
                        print(f"  $ {block.input.get('command')}")
                    elif block.name == "BashOutput":
                        print(f"[Claude called] BashOutput(pid={block.input.get('pid')})")
                    elif block.name == "KillBash":
                        print(f"[Claude called] KillBash(pid={block.input.get('pid')})")
                    else:
                        print(f"[Claude called] {block.name}({block.input})")
                elif isinstance(block, TextBlock):
                    print(f"[Claude says] {block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n[Cost: ${message.total_cost_usd:.4f} | Turns: {message.num_turns}]")


asyncio.run(main())
