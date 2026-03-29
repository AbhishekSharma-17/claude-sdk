"""
Tool 3: Grep
=============
Lets Claude search for text patterns inside files (like ctrl+F across all files).

Supports full regex patterns:
  "TODO"              → exact word match
  "ERROR|FIXME|BUG"   → multiple words (OR)
  "def \\w+"          → regex: any function definition
  "\\d{4}-\\d{2}-\\d{2}" → regex: date pattern YYYY-MM-DD

output_mode options:
  "content"           → show matching lines (default)
  "files_with_matches" → show only filenames that matched
  "count"             → show match count per file
"""

import asyncio
import os
from dotenv import load_dotenv
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, AssistantMessage, ToolUseBlock, TextBlock

load_dotenv()

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY")},
    allowed_tools=["Grep"],
    permission_mode="bypassPermissions",
    max_turns=3,
)


async def main():
    print("=== Tool: Grep ===\n")

    async for message in query(
        prompt="""
        Search inside the sample_data/ folder and find:
        1. All lines containing TODO or FIXME or BUG or ERROR
        2. Tell me which file each one is in and what line number
        3. Summarize what needs to be fixed
        """,
        options=options,
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    print(f"[Claude called] Grep({block.input})")
                elif isinstance(block, TextBlock):
                    print(f"[Claude says]\n{block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n[Cost: ${message.total_cost_usd:.4f} | Turns: {message.num_turns}]")


asyncio.run(main())
