"""
Tool 2: Glob
=============
Lets Claude find files by pattern (like a file search).

Pattern syntax:
  *.py          → all .py files in current dir only
  **/*.py       → all .py files in all subdirectories (recursive)
  sample_data/* → all files inside sample_data/
  **/*config*   → any file with "config" in the name, anywhere
"""

import asyncio
import os
from dotenv import load_dotenv
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, AssistantMessage, ToolUseBlock, TextBlock

load_dotenv()

options = ClaudeAgentOptions(
    model="haiku",
    env={"ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY")},
    allowed_tools=["Glob", "Read"],
    permission_mode="bypassPermissions",
    max_turns=5,
)


async def main():
    print("=== Tool: Glob ===\n")

    async for message in query(
        prompt="""
        Look inside the sample_data/ directory and:
        1. Find all files
        2. Group them by file type (extension)
        3. Tell me how many files of each type exist
        4. Read utils file and explain the content
        """,
        options=options,
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    print(f"[Claude called] Glob({block.input})")
                elif isinstance(block, TextBlock):
                    print(f"[Claude says]\n{block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n[Cost: ${message.total_cost_usd:.4f} | Turns: {message.num_turns}]")


asyncio.run(main())
