"""15 — ExitPlanMode Tool Demo

The ExitPlanMode tool is used when Claude is in "plan" permission mode.
In plan mode, Claude designs an implementation plan WITHOUT executing any changes.
When the plan is ready, Claude calls ExitPlanMode to signal for user approval.

This is a CONCEPTUAL demo — in batch processing (bypassPermissions), this tool
isn't used. It's designed for interactive workflows where you want Claude to
plan before executing.

Permission mode flow:
    1. Set permission_mode="plan" in options
    2. Claude explores the codebase (read-only tools work)
    3. Claude writes a plan
    4. Claude calls ExitPlanMode to request approval
    5. User approves → Claude executes the plan

Usage: python examples/tools/15_exit_plan_mode_tool.py
Requires: ANTHROPIC_API_KEY environment variable
Note: This demo runs in plan mode — Claude will only plan, not execute.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"


async def main() -> None:
    # Plan mode: Claude can read but NOT write/edit
    options = ClaudeAgentOptions(
        model="haiku",
        allowed_tools=["Read", "Glob", "Grep", "ExitPlanMode"],
        permission_mode="plan",  # Read-only — Claude plans but doesn't execute
        max_turns=5,
        system_prompt=(
            "You are an architect. Explore the code, then create a plan for improvements. "
            "When your plan is ready, use ExitPlanMode to signal completion."
        ),
    )

    prompt = (
        f"Look at {SAMPLE_DIR / 'sample.py'} and create a plan to: "
        "1) Fix any bugs, "
        "2) Add input validation, "
        "3) Add proper error handling. "
        "Present the plan, then call ExitPlanMode."
    )

    print("--- ExitPlanMode Tool Demo ---")
    print("Claude operates in PLAN mode (read-only). It will plan but not execute.\n")

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    print(f"[TOOL CALL] {block.name}")
                    if block.name == "ExitPlanMode":
                        print("  → Claude is signaling: 'Plan is ready for approval!'")
                    else:
                        for k, v in block.input.items():
                            print(f"  {k}: {str(v)[:100]}")

                elif isinstance(block, TextBlock):
                    print(f"\n[CLAUDE] {block.text[:500]}")

        elif isinstance(message, ResultMessage):
            print(f"\n--- Result ---")
            print(f"Cost: ${message.total_cost_usd or 0:.4f}")
            print(f"Stop reason: {message.stop_reason}")
            if message.result:
                print(f"\nFinal plan:\n{message.result[:500]}...")


if __name__ == "__main__":
    asyncio.run(main())
