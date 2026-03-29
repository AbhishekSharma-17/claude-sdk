"""
Tool 8: WebSearch
==================
Lets Claude search the web for live, up-to-date information.

Use when you need:
  - Latest versions / changelogs
  - Current pricing
  - Recent news or events
  - Anything beyond Claude's training cutoff (Aug 2025)

WITHOUT WebSearch → Claude answers from training data (may be outdated)
WITH WebSearch    → Claude fetches live results first, then answers
"""

import asyncio
import os
from dotenv import load_dotenv
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, AssistantMessage, ToolUseBlock, TextBlock

load_dotenv()

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY")},
    allowed_tools=["WebSearch"],
    permission_mode="bypassPermissions",
    max_turns=10,
)


async def main():
    print("=== Tool: WebSearch ===\n")

    async for message in query(
        prompt="""
        Search the web and find:
        1. The latest version of claude-agent-sdk on PyPI
        2. What changed in the most recent release
        3. The current price of Claude Sonnet on Anthropic API (per million tokens)
        """,
        options=options,
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    if block.name == "WebSearch":
                        print(f"[Claude called] WebSearch:")
                        print(f"  query: {block.input.get('query')}")
                    else:
                        print(f"[Claude called] {block.name}({block.input})")
                elif isinstance(block, TextBlock):
                    print(f"[Claude says]\n{block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n[Cost: ${message.total_cost_usd:.4f} | Turns: {message.num_turns}]")


asyncio.run(main())
