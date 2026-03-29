"""
Tool 15: ExitPlanMode
======================
When permission_mode="plan", Claude ONLY plans — no execution.
Claude calls ExitPlanMode when it's ready to execute.

This gives you a "preview before commit" workflow:
  Step 1: Claude plans (reads files, thinks, proposes changes)
  Step 2: Claude calls ExitPlanMode → "here's what I'd do, approve?"
  Step 3: You decide — approve or reject

PLAN MODE RULES:
  - Claude CAN read files (Read, Glob, Grep)
  - Claude CANNOT modify anything (no Write, Edit, Bash)
  - Claude calls ExitPlanMode when planning is done
  - Until approved, nothing gets changed on disk

Compare two runs:
  Run 1: permission_mode="plan"    → Claude plans only, calls ExitPlanMode
  Run 2: permission_mode="bypassPermissions" → Claude just does it
"""

import asyncio
import os
from dotenv import load_dotenv
from claude_agent_sdk import (
    query, ClaudeAgentOptions, ResultMessage, AssistantMessage,
    ToolUseBlock, TextBlock,
)

load_dotenv()

# ── PLAN MODE — Claude plans but doesn't execute ─────────────────────────────
plan_options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY")},
    allowed_tools=["Read", "Glob", "Grep", "Edit", "ExitPlanMode"],
    permission_mode="plan",   # ← THIS is the key — plan only, no execution
    max_turns=5,
)


async def main():
    print("=== Tool: ExitPlanMode ===\n")
    print("Running in PLAN mode — Claude will plan but NOT execute.\n")

    async for message in query(
        prompt="""
        I want to fix all the bugs in sample_data/app.py.
        Plan what changes you would make — do NOT execute yet.
        """,
        options=plan_options,
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    if block.name == "ExitPlanMode":
                        print(f"\n[Claude called] ExitPlanMode!")
                        print(f"  → Claude is asking: 'Can I start executing now?'")
                        print(f"  → In a real app, you'd approve/reject here.\n")
                    else:
                        print(f"[Claude called] {block.name}({block.input})")
                elif isinstance(block, TextBlock):
                    print(f"[Claude says]\n{block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n[Cost: ${message.total_cost_usd:.4f} | Turns: {message.num_turns}]")

    # Verify nothing was changed
    print("\n--- Checking app.py was NOT modified ---")
    with open("sample_data/app.py") as f:
        content = f.read()
    if "hardcoded_password_123" in content:
        print("CONFIRMED: app.py is unchanged — plan mode worked, no edits applied.")
    else:
        print("WARNING: app.py was modified!")


asyncio.run(main())
