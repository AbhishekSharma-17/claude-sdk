"""
Tool 9: WebFetch
=================
Lets Claude fetch and read the full content of a specific URL.

Use when you already KNOW the URL you want to read.
Use WebSearch first if you need to FIND the URL.

Common pattern:
  WebSearch → finds the URL
  WebFetch  → reads that URL fully for details
"""

import asyncio
import os
from dotenv import load_dotenv
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, AssistantMessage, ToolUseBlock, TextBlock

load_dotenv()

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY")},
    # Both together — Search to find, Fetch to read in detail
    allowed_tools=["WebSearch", "WebFetch"],
    permission_mode="bypassPermissions",
    max_turns=20,
)


async def main():
    print("=== Tool: WebFetch ===\n")

    async for message in query(
        prompt="""
        Fetch services from genaiprotos.com , also get contact information and who the CTO and CEO are do extensive research
        """,
        options=options,
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    if block.name == "WebFetch":
                        print(f"[Claude called] WebFetch:")
                        print(f"  url: {block.input.get('url')}")
                    else:
                        print(f"[Claude called] {block.name}({block.input})")
                elif isinstance(block, TextBlock):
                    print(f"[Claude says]\n{block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n[Cost: ${message.total_cost_usd:.4f} | Turns: {message.num_turns}]")


asyncio.run(main())
