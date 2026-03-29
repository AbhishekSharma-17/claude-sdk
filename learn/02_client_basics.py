"""
ClaudeSDKClient — The Multi-Turn Interactive Client
=====================================================
Unlike query() which is one-shot, ClaudeSDKClient keeps a persistent
connection open for back-and-forth conversation.

This script shows 3 examples:
  1. Multi-turn conversation (Claude remembers context)
  2. Model switching mid-conversation (haiku → sonnet)
  3. Permission switching (plan → execute)
"""

import asyncio
import os
from dotenv import load_dotenv
from claude_agent_sdk import (
    ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage,
    ResultMessage, TextBlock, ToolUseBlock,
)

load_dotenv()

API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not API_KEY:
    raise ValueError("Missing ANTHROPIC_API_KEY in .env")


# =============================================================================
# Example 1: Multi-turn conversation — Claude remembers context
# =============================================================================
async def example_1_multi_turn():
    print("=" * 60)
    print("Example 1: Multi-turn conversation")
    print("=" * 60)

    options = ClaudeAgentOptions(
        model="sonnet",
        env={"ANTHROPIC_API_KEY": API_KEY},
        allowed_tools=["Read"],
        permission_mode="bypassPermissions",
        max_turns=3,
    )

    async with ClaudeSDKClient(options=options) as client:

        # Turn 1 — Claude reads a file
        print("\n--- Turn 1: Read the config ---")
        await client.query("Read sample_data/config.json and tell me the app name and port.")
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, ToolUseBlock):
                        print(f"  [Tool] {block.name}")
                    elif isinstance(block, TextBlock):
                        print(f"  [Claude] {block.text}")
            elif isinstance(msg, ResultMessage):
                print(f"  [Cost: ${msg.total_cost_usd:.4f}]")

        # Turn 2 — Follow-up question (Claude remembers Turn 1)
        print("\n--- Turn 2: Follow-up (no tools needed) ---")
        await client.query("Based on the config you just read, is debug mode on or off?")
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        print(f"  [Claude] {block.text}")
            elif isinstance(msg, ResultMessage):
                print(f"  [Cost: ${msg.total_cost_usd:.4f}]")


# =============================================================================
# Example 2: Switch model mid-conversation
# =============================================================================
async def example_2_model_switch():
    print("\n" + "=" * 60)
    print("Example 2: Model switching (haiku → sonnet)")
    print("=" * 60)

    options = ClaudeAgentOptions(
        model="haiku",                # start with cheap model
        env={"ANTHROPIC_API_KEY": API_KEY},
        permission_mode="bypassPermissions",
        max_turns=2,
    )

    async with ClaudeSDKClient(options=options) as client:

        # Turn 1 — haiku (fast, cheap)
        print("\n--- Turn 1: Using haiku ---")
        await client.query("What is a Python decorator in one sentence?")
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        print(f"  [Haiku] {block.text}")
            elif isinstance(msg, ResultMessage):
                print(f"  [Cost: ${msg.total_cost_usd:.4f} | Model: haiku]")

        # Switch to sonnet
        await client.set_model("sonnet")

        # Turn 2 — sonnet (better quality, Claude still has context)
        print("\n--- Turn 2: Switched to sonnet ---")
        await client.query("Now give me a more detailed explanation with a code example.")
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        print(f"  [Sonnet] {block.text}")
            elif isinstance(msg, ResultMessage):
                print(f"  [Cost: ${msg.total_cost_usd:.4f} | Model: sonnet]")


# =============================================================================
# Example 3: Plan mode → then execute
# =============================================================================
async def example_3_plan_execute():
    print("\n" + "=" * 60)
    print("Example 3: Plan → Execute (permission switching)")
    print("=" * 60)

    options = ClaudeAgentOptions(
        model="sonnet",
        env={"ANTHROPIC_API_KEY": API_KEY},
        allowed_tools=["Read", "Glob", "Grep", "ExitPlanMode"],
        permission_mode="plan",          # START in plan mode
        max_turns=5,
    )

    async with ClaudeSDKClient(options=options) as client:

        # Phase 1: Plan mode — Claude reads and plans, cannot edit
        print("\n--- Phase 1: Plan mode (read-only) ---")
        await client.query("Read sample_data/app.py and plan what bugs need fixing. Do NOT edit.")
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, ToolUseBlock):
                        print(f"  [Tool] {block.name}")
                    elif isinstance(block, TextBlock):
                        print(f"  [Plan] {block.text}")
            elif isinstance(msg, ResultMessage):
                print(f"  [Cost: ${msg.total_cost_usd:.4f}]")

        print("\n  [Permission mode changed: plan → bypassPermissions]")
        print("  (In a real app, you'd ask the user to approve the plan here)")

        # Note: To actually execute, you would switch permissions and continue:
        # await client.set_permission_mode("bypassPermissions")
        # await client.query("Execute the plan")
        # async for msg in client.receive_response(): ...


# =============================================================================
# RUN ALL EXAMPLES
# =============================================================================
async def main():
    print("🔗 Learning ClaudeSDKClient — 3 Examples\n")

    await example_1_multi_turn()
    await example_2_model_switch()
    await example_3_plan_execute()

    print("\n" + "=" * 60)
    print("DONE — All 3 ClaudeSDKClient examples complete!")
    print("=" * 60)


asyncio.run(main())
