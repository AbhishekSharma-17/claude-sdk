"""12 — TodoWrite Tool Demo

The TodoWrite tool lets Claude create and manage a structured task list.
Claude uses it to track progress on multi-step tasks. Each todo has:
  - content: What needs to be done (imperative form)
  - activeForm: Present continuous form shown during execution
  - status: "pending" | "in_progress" | "completed"

Tool input schema:
    todos: list[dict]  — The full updated todo list, each item with:
        content: str
        activeForm: str
        status: "pending" | "in_progress" | "completed"

Usage: python examples/tools/12_todo_write_tool.py
Requires: ANTHROPIC_API_KEY environment variable
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"


async def main() -> None:
    options = ClaudeAgentOptions(
        model="haiku",
        allowed_tools=["Read", "Grep", "TodoWrite"],
        permission_mode="bypassPermissions",
        max_turns=6,
        system_prompt=(
            "You are a code auditor. Use TodoWrite to track your progress as you "
            "analyze files. Create a todo list at the start, mark items in_progress "
            "as you work on them, and completed when done."
        ),
    )

    prompt = (
        f"Audit the files in {SAMPLE_DIR}. Your tasks: "
        "1) Check sample.py for bugs, "
        "2) Check sample.sql for performance issues, "
        "3) Write a brief summary. "
        "Use TodoWrite to track your progress through each step."
    )

    print("--- TodoWrite Tool Demo ---")
    print(f"Prompt: {prompt[:80]}...\n")

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    if block.name == "TodoWrite":
                        print(f"\n[TODO UPDATE]")
                        todos = block.input.get("todos", [])
                        for todo in todos:
                            status_icon = {
                                "pending": "○",
                                "in_progress": "●",
                                "completed": "✓",
                            }.get(todo["status"], "?")
                            print(f"  {status_icon} {todo['content']} [{todo['status']}]")
                    else:
                        print(f"[TOOL CALL] {block.name}: {list(block.input.values())[:2]}")

                elif isinstance(block, TextBlock):
                    print(f"\n[CLAUDE] {block.text[:300]}")

        elif isinstance(message, ResultMessage):
            print(f"\n--- Result ---")
            print(f"Cost: ${message.total_cost_usd or 0:.4f}")
            print(f"Turns: {message.num_turns}")


if __name__ == "__main__":
    asyncio.run(main())
