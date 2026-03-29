"""
Tool 6: Bash
=============
Lets Claude run shell commands directly on your machine.

POWERFUL — Claude can run anything: python scripts, pip install,
git commands, file operations, system info, etc.

SAFE USAGE TIPS:
  - Use disallowed_tools=["Bash"] to block it entirely when not needed
  - Use sandbox={"allowed_commands": ["python", "ls"]} to restrict commands
  - Never use bypassPermissions with Bash in production on sensitive systems
"""

import asyncio
import os
from dotenv import load_dotenv
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, AssistantMessage, ToolUseBlock, TextBlock

load_dotenv()

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY")},
    allowed_tools=["Read", "Bash"],
    permission_mode="bypassPermissions",
    max_turns=5,
)


async def main():
    print("=== Tool: Bash ===\n")

    async for message in query(
        prompt="""
        Do the following using shell commands:
        1. Count how many lines are in each file inside sample_data/
        2. Show the 5 largest files in sample_data/ by size
        3. Run this python snippet and show the output:
              python3 -c "from sample_data.utils import calculate_percentage; print(calculate_percentage(45, 200))"
        """,
        options=options,
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    if block.name == "Bash":
                        print(f"[Claude called] Bash:")
                        print(f"  $ {block.input.get('command')}")
                    else:
                        print(f"[Claude called] {block.name}({block.input})")
                elif isinstance(block, TextBlock):
                    print(f"[Claude says]\n{block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n[Cost: ${message.total_cost_usd:.4f} | Turns: {message.num_turns}]")


asyncio.run(main())
