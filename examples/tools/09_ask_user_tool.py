"""09 — AskUserQuestion Tool Demo

The AskUserQuestion tool lets Claude ask the user a multiple-choice question
during execution. This is for INTERACTIVE mode only — in batch processing
with bypassPermissions, this tool won't be useful.

Tool input schema:
    questions: list[dict]  — List of questions, each with:
        question: str      — The question text
        options: list[dict] — 2-4 choices, each with label + description
        multiSelect: bool  — Allow multiple selections

NOTE: This demo uses "default" permission mode so the interactive prompt works.
      In a real batch pipeline, you would NOT include this tool.

Usage: python examples/tools/09_ask_user_tool.py
Requires: ANTHROPIC_API_KEY environment variable
Note: This script is interactive — it will pause for user input in the terminal.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"


async def main() -> None:
    # NOTE: Using "default" permission mode makes this interactive
    options = ClaudeAgentOptions(
        model="haiku",
        allowed_tools=["Read", "AskUserQuestion"],
        permission_mode="default",  # Interactive — will prompt in terminal
        max_turns=4,
        system_prompt=(
            "You are a code migration assistant. Read a SQL file, then ask the user "
            "which target language they want to convert it to using AskUserQuestion."
        ),
    )

    prompt = (
        f"Read {SAMPLE_DIR / 'sample.sql'} and then ask me which language "
        "I want to convert it to (PySpark, Pandas, or dbt). "
        "After I choose, give a brief plan for the conversion."
    )

    print("--- AskUserQuestion Tool Demo ---")
    print("NOTE: This is interactive. You'll be prompted to choose an option.\n")
    print(f"Prompt: {prompt[:80]}...\n")

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    print(f"[TOOL CALL] {block.name}")
                    if block.name == "AskUserQuestion":
                        questions = block.input.get("questions", [])
                        for q in questions:
                            print(f"  Q: {q.get('question')}")
                            for opt in q.get("options", []):
                                print(f"    - {opt.get('label')}: {opt.get('description')}")

                elif isinstance(block, TextBlock):
                    print(f"\n[CLAUDE] {block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n--- Result ---")
            print(f"Cost: ${message.total_cost_usd or 0:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
