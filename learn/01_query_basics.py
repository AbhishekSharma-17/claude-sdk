"""
query() — The Simple One-Shot Function
========================================
query() is the simplest way to use Claude Agent SDK.

  You send a prompt → Claude works → You get the response → Done.

No connection management, no state, no sessions.

This script shows 4 examples:
  1. Minimal query (just a prompt)
  2. With tools (Claude reads files)
  3. With cost limit (max_budget_usd)
  4. With system prompt (custom behavior)
"""

import asyncio
import os
from dotenv import load_dotenv
from claude_agent_sdk import (
    query, ClaudeAgentOptions, ResultMessage, AssistantMessage,
    TextBlock, ToolUseBlock,
)

load_dotenv()

API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not API_KEY:
    raise ValueError("Missing ANTHROPIC_API_KEY in .env")


# =============================================================================
# Example 1: Minimal query — just a prompt, nothing else
# =============================================================================
async def example_1_minimal():
    print("=" * 60)
    print("Example 1: Minimal query (no tools, no config)")
    print("=" * 60)

    options = ClaudeAgentOptions(
        model="sonnet",
        env={"ANTHROPIC_API_KEY": API_KEY},
        max_turns=1,                          # just answer, no tool loops
        permission_mode="bypassPermissions",
    )

    async for msg in query(prompt="What is the Claude Agent SDK in one sentence?", options=options):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    print(f"[Claude] {block.text}")

        elif isinstance(msg, ResultMessage):
            print(f"\n[Cost: ${msg.total_cost_usd:.4f} | Turns: {msg.num_turns}]")


# =============================================================================
# Example 2: With tools — Claude reads a file
# =============================================================================
async def example_2_with_tools():
    print("\n" + "=" * 60)
    print("Example 2: With tools (Claude reads a file)")
    print("=" * 60)

    options = ClaudeAgentOptions(
        model="sonnet",
        env={"ANTHROPIC_API_KEY": API_KEY},
        allowed_tools=["Read"],               # only allow Read tool
        permission_mode="bypassPermissions",
        max_turns=3,
    )

    async for msg in query(
        prompt="Read sample_data/config.json and tell me what port the app runs on.",
        options=options,
    ):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, ToolUseBlock):
                    print(f"[Tool] {block.name}({block.input})")
                elif isinstance(block, TextBlock):
                    print(f"[Claude] {block.text}")

        elif isinstance(msg, ResultMessage):
            print(f"\n[Cost: ${msg.total_cost_usd:.4f} | Turns: {msg.num_turns}]")


# =============================================================================
# Example 3: With cost limit — stops if too expensive
# =============================================================================
async def example_3_cost_limit():
    print("\n" + "=" * 60)
    print("Example 3: With cost limit (max_budget_usd)")
    print("=" * 60)

    options = ClaudeAgentOptions(
        model="sonnet",
        env={"ANTHROPIC_API_KEY": API_KEY},
        max_turns=1,
        max_budget_usd=0.01,                  # max 1 cent
        permission_mode="bypassPermissions",
    )

    async for msg in query(
        prompt="Explain Python decorators briefly.",
        options=options,
    ):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    print(f"[Claude] {block.text}")

        elif isinstance(msg, ResultMessage):
            print(f"\n[Cost: ${msg.total_cost_usd:.4f} | Budget was: $0.01]")
            print(f"[Turns: {msg.num_turns} | Error: {msg.is_error}]")


# =============================================================================
# Example 4: With system prompt — custom personality
# =============================================================================
async def example_4_system_prompt():
    print("\n" + "=" * 60)
    print("Example 4: With system prompt (custom behavior)")
    print("=" * 60)

    options = ClaudeAgentOptions(
        model="sonnet",
        env={"ANTHROPIC_API_KEY": API_KEY},
        system_prompt="You are a senior Python developer. Answer in exactly 3 bullet points. Be concise.",
        max_turns=1,
        permission_mode="bypassPermissions",
    )

    async for msg in query(
        prompt="What are the best practices for async Python?",
        options=options,
    ):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    print(f"[Claude] {block.text}")

        elif isinstance(msg, ResultMessage):
            print(f"\n[Cost: ${msg.total_cost_usd:.4f} | Turns: {msg.num_turns}]")


# =============================================================================
# RUN ALL EXAMPLES
# =============================================================================
async def main():
    print("🔍 Learning query() — 4 Examples\n")

    await example_1_minimal()
    await example_2_with_tools()
    await example_3_cost_limit()
    await example_4_system_prompt()

    print("\n" + "=" * 60)
    print("DONE — All 4 query() examples complete!")
    print("=" * 60)


asyncio.run(main())
