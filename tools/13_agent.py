"""
Tool 13: Agent (Subagents)
===========================
Lets Claude spawn child agents that work independently.

KEY BEHAVIORS:
  - Each subagent gets FRESH context (no parent conversation history)
  - Multiple subagents can run in PARALLEL
  - Subagents CANNOT spawn their own subagents
  - Parent receives each subagent's final result as a tool result
  - You can define specialized agents with different tools/models

TWO WAYS TO USE:
  1. Built-in general-purpose agent → always available, inherits tools
  2. Custom agents via agents={} → you define name, prompt, tools, model
"""

import asyncio
import os
from dotenv import load_dotenv
from claude_agent_sdk import (
    query, ClaudeAgentOptions, ResultMessage, AssistantMessage,
    ToolUseBlock, TextBlock, AgentDefinition,
)

load_dotenv()

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY")},

    # "Agent" in allowed_tools is REQUIRED for subagent spawning
    allowed_tools=["Read", "Glob", "Grep", "Agent","WebSearch","WebFetch"],
    permission_mode="bypassPermissions",
    max_turns=10,

    # Define specialized subagents — each gets its own role + tools + model
    agents={
        "bug-finder": AgentDefinition(
            description="Finds logic bugs and runtime errors in code",
            prompt="You are a bug-finding specialist. Read the file and find all logic bugs, runtime errors, and edge cases. Be thorough.",
            tools=["Read"],        # only needs to read
            model="sonnet",
        ),
        "security-scanner": AgentDefinition(
            description="Finds security vulnerabilities in code",
            prompt="You are a security specialist. Read the file and find hardcoded secrets, injection risks, missing input validation, and unsafe patterns.",
            tools=["Read", "Grep"],  # can read + search patterns
            model="sonnet",
        ),
    }
)


async def main():
    print("=== Tool: Agent (Subagents) ===\n")

    async for message in query(
        prompt="""
        Create a research agent and do resaerch on genaiprotos.com
        """,
        options=options,
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    if block.name == "Agent":
                        print(f"[Claude spawned] Agent:")
                        print(f"  type   : {block.input.get('subagent_type', 'general')}")
                        print(f"  prompt : {block.input.get('prompt', '')[:80]}...")
                    else:
                        print(f"[Claude called] {block.name}({block.input})")
                elif isinstance(block, TextBlock):
                    print(f"[Claude says]\n{block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n[Cost: ${message.total_cost_usd:.4f} | Turns: {message.num_turns}]")


asyncio.run(main())
