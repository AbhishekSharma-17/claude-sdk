"""
Tool 4: Write
==============
Lets Claude create a new file or overwrite an existing one.

IMPORTANT:
  - Write CREATES or OVERWRITES — no merging, no appending
  - If file exists, it is completely replaced
  - If you want to change just one part of a file → use Edit (Tool 5)
  - Claude needs Read access first to understand what to write
"""

import asyncio
import os
from dotenv import load_dotenv
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, AssistantMessage, ToolUseBlock, TextBlock

load_dotenv()

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY")},
    # Read → to understand the data
    # Write → to create the output file
    allowed_tools=["Read", "Write"],
    permission_mode="bypassPermissions",
    max_turns=5,
)


async def main():
    print("=== Tool: Write ===\n")

    # Make sure output folder exists
    os.makedirs("sample_data/output", exist_ok=True)

    async for message in query(
        prompt="""
        1. Read sample_data/employees.csv
        2. Analyze the data
        3. Write a summary report to sample_data/output/employee_report.md with:
           - Total headcount
           - Average salary overall
           - Highest and lowest paid employee
           - Headcount per department
           - Who joined most recently
        """,
        options=options,
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    # Show which tool Claude is calling
                    print(f"[Claude called] {block.name}({block.input})")
                elif isinstance(block, TextBlock):
                    print(f"[Claude says]\n{block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n[Cost: ${message.total_cost_usd:.4f} | Turns: {message.num_turns}]")

    # Verify the file was actually created
    output_path = "sample_data/output/employee_report.md"
    if os.path.exists(output_path):
        size = os.path.getsize(output_path)
        print(f"\n[File created] {output_path} ({size} bytes)")
    else:
        print("\n[WARNING] File was not created")


asyncio.run(main())
