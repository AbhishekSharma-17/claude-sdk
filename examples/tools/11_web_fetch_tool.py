"""11 — WebFetch Tool Demo

The WebFetch tool lets Claude fetch and extract content from a specific URL.
It converts HTML to markdown and can process the content with a prompt.

Tool input schema:
    url: str     — The URL to fetch (must be fully-formed)
    prompt: str  — What to extract from the page content

Usage: python examples/tools/11_web_fetch_tool.py
Requires: ANTHROPIC_API_KEY environment variable
"""

from __future__ import annotations

import asyncio

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock, ToolResultBlock


async def main() -> None:
    options = ClaudeAgentOptions(
        model="haiku",
        allowed_tools=["WebFetch"],
        permission_mode="bypassPermissions",
        max_turns=2,
        system_prompt="You are a documentation reader. Fetch web pages and extract key information.",
    )

    prompt = (
        "Fetch the Python official documentation page at https://docs.python.org/3/whatsnew/3.12.html "
        "and summarize the top 3 new features in Python 3.12."
    )

    print("--- WebFetch Tool Demo ---")
    print(f"Prompt: {prompt[:80]}...\n")

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    print(f"[TOOL CALL] {block.name}")
                    print(f"  url: {block.input.get('url')}")
                    print(f"  prompt: {block.input.get('prompt', '')[:100]}")

                elif isinstance(block, ToolResultBlock):
                    output = block.content or ""
                    print(f"[TOOL RESULT] ({len(output)} chars)")

                elif isinstance(block, TextBlock):
                    print(f"\n[CLAUDE] {block.text[:500]}")

        elif isinstance(message, ResultMessage):
            print(f"\n--- Result ---")
            print(f"Cost: ${message.total_cost_usd or 0:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
