"""
Tool 10: TodoWrite
===================
Lets Claude maintain a task list during complex multi-step work.
Claude uses it to track its own progress — pending → in_progress → completed.

Each todo item has:
  id       → unique identifier
  content  → description of the task
  status   → "pending" | "in_progress" | "completed"
  priority → "high" | "medium" | "low"

WHY IT MATTERS:
  Without TodoWrite → Claude might skip steps or repeat work across turns
  With TodoWrite    → Claude has a persistent checklist it updates as it works
  You also get visibility into exactly what Claude is doing and in what order
"""

import asyncio
import os
from dotenv import load_dotenv
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, AssistantMessage, ToolUseBlock, TextBlock

load_dotenv()

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY")},
    allowed_tools=["Read", "Glob", "TodoWrite"],
    permission_mode="bypassPermissions",
    max_turns=10,
)


async def main():
    print("=== Tool: TodoWrite ===\n")

    async for message in query(
        prompt="""
        Do a full audit of all files in sample_data/ directory.
        For each file:
          - Create a todo item for it first
          - Read the file
          - Mark it complete with a one-line finding
        At the end summarize all findings in a table. do all of it parallely
        """,
        options=options,
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    if block.name == "TodoWrite":
                        # Show each todo item and its status
                        todos = block.input.get("todos", [])
                        print(f"[Claude called] TodoWrite — {len(todos)} items:")
                        for t in todos:
                            status = t.get("status", "")
                            icon = {"pending": "○", "in_progress": "◉", "completed": "✓"}.get(status, "?")
                            print(f"  {icon} [{t.get('id')}] {t.get('content')} ({status})")
                    else:
                        print(f"[Claude called] {block.name}({block.input.get('file_path') or block.input.get('pattern', '')})")
                elif isinstance(block, TextBlock):
                    print(f"[Claude says]\n{block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n[Cost: ${message.total_cost_usd:.4f} | Turns: {message.num_turns}]")


asyncio.run(main())
