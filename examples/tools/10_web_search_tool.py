"""10 — WebSearch Tool Demo

The WebSearch tool lets Claude search the web for current information.
Results include titles, URLs, and snippets.

Tool input schema:
    query: str  — The search query

Usage: python examples/tools/10_web_search_tool.py
Requires: ANTHROPIC_API_KEY environment variable
"""

from __future__ import annotations

import asyncio

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock, ToolResultBlock


async def main() -> None:
    options = ClaudeAgentOptions(
        model="haiku",
        allowed_tools=["WebSearch"],
        permission_mode="bypassPermissions",
        max_turns=2,
        system_prompt="You are a research assistant. Search the web and summarize findings concisely.",
    )

    prompt = "Search for the latest PySpark release version and its key new features."

    print("--- WebSearch Tool Demo ---")
    print(f"Prompt: {prompt}\n")

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    print(f"[TOOL CALL] {block.name}")
                    print(f"  query: {block.input.get('query')}")

                elif isinstance(block, ToolResultBlock):
                    output = block.content or ""
                    print(f"[TOOL RESULT] ({len(output)} chars)")
                    print(f"  {output[:300]}...")

                elif isinstance(block, TextBlock):
                    print(f"\n[CLAUDE] {block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n--- Result ---")
            print(f"Cost: ${message.total_cost_usd or 0:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
