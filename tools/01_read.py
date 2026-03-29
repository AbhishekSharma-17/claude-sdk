"""
Tool 1: Read
=============
Lets Claude read a file and use its content to answer.

allowed_tools=["Read"] means Claude CAN read files, auto-approved.
Without it, Claude would have to ask permission first.
"""

import asyncio
import os
from dotenv import load_dotenv
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, AssistantMessage, ToolUseBlock, TextBlock

load_dotenv()

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY")},

    # Give Claude permission to read files
    allowed_tools=["Read"],

    permission_mode="bypassPermissions",
    max_turns=3,
)


async def main():
    print("=== Tool: Read ===\n")
    print("Asking Claude to find bugs in app.py\n")

    async for message in query(
        prompt="Read the file sample_data/app.py and list all the bugs you find.",
        options=options,
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    # Shows Claude actually calling the Read tool
                    print(f"[Claude called] Read({block.input})")
                elif isinstance(block, TextBlock):
                    print(f"[Claude says]\n{block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n[Cost: ${message.total_cost_usd:.4f} | Turns: {message.num_turns}]")


asyncio.run(main())
