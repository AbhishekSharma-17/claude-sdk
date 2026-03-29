"""
Skills Demo — How to pass skills to agents and sub-agents
==========================================================

Skills are markdown instruction packages that give Claude specialized knowledge.
This script shows:
  1. Creating a sub-agent WITH skills
  2. Creating a sub-agent WITHOUT skills (for comparison)
  3. How skills affect agent behavior
"""

import asyncio
import os
from dotenv import load_dotenv
from claude_agent_sdk import (
    query, ClaudeAgentOptions, AgentDefinition,
    AssistantMessage, ResultMessage, TextBlock, ToolUseBlock,
)

load_dotenv()

API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not API_KEY:
    raise ValueError("Missing ANTHROPIC_API_KEY in .env")


# =============================================================================
# Example 1: Agent WITH python-patterns skill
# =============================================================================
async def example_1_with_skills():
    print("=" * 60)
    print("Example 1: Agent with skills (python-patterns + clean-code)")
    print("=" * 60)

    options = ClaudeAgentOptions(
        model="sonnet",
        env={"ANTHROPIC_API_KEY": API_KEY},
        allowed_tools=["Agent"],
        permission_mode="bypassPermissions",
        max_turns=5,
        agents={
            "python-expert": AgentDefinition(
                description="Python development expert with best practices knowledge",
                prompt="You are a senior Python developer. Use your skills knowledge.",
                tools=["Read", "Glob"],
                skills=["python-patterns", "clean-code"],  # ← skills loaded
                model="sonnet",
                maxTurns=3,
            ),
        },
    )

    async for msg in query(
        prompt=(
            "Use the python-expert agent to recommend the best Python web framework "
            "for a real-time chat application. Ask it to explain its reasoning."
        ),
        options=options,
    ):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, ToolUseBlock):
                    print(f"  [Tool] {block.name}: {block.input.get('description', '')}")
                elif isinstance(block, TextBlock):
                    print(f"  [Claude] {block.text[:500]}")
        elif isinstance(msg, ResultMessage):
            print(f"\n  [Cost: ${msg.total_cost_usd:.4f} | Turns: {msg.num_turns}]")


# =============================================================================
# Example 2: Multiple agents with DIFFERENT skills
# =============================================================================
async def example_2_different_skills():
    print("\n" + "=" * 60)
    print("Example 2: Two agents with different skills")
    print("=" * 60)

    options = ClaudeAgentOptions(
        model="sonnet",
        env={"ANTHROPIC_API_KEY": API_KEY},
        allowed_tools=["Read", "Agent"],
        permission_mode="bypassPermissions",
        max_turns=5,
        agents={
            # Agent 1: Backend specialist
            "backend-dev": AgentDefinition(
                description="Backend API developer",
                prompt="You are a backend developer specializing in APIs.",
                tools=["Read", "Glob"],
                skills=["python-patterns", "api-patterns", "database-design"],
                model="sonnet",
                maxTurns=3,
            ),
            # Agent 2: Frontend specialist
            "frontend-dev": AgentDefinition(
                description="Frontend React developer",
                prompt="You are a frontend developer specializing in React.",
                tools=["Read", "Glob"],
                skills=["nextjs-react-expert", "tailwind-patterns"],
                model="sonnet",
                maxTurns=3,
            ),
        },
    )

    async for msg in query(
        prompt=(
            "I'm building a dashboard app. Use the backend-dev agent to recommend "
            "the backend stack, and use the frontend-dev agent to recommend the "
            "frontend stack. Each should give a brief 2-3 sentence answer."
        ),
        options=options,
    ):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, ToolUseBlock):
                    agent_type = block.input.get("subagent_type", "")
                    desc = block.input.get("description", "")
                    print(f"  [Spawning] {agent_type}: {desc}")
                elif isinstance(block, TextBlock):
                    print(f"  [Claude] {block.text[:500]}")
        elif isinstance(msg, ResultMessage):
            print(f"\n  [Cost: ${msg.total_cost_usd:.4f} | Turns: {msg.num_turns}]")


# =============================================================================
# RUN EXAMPLES
# =============================================================================
async def main():
    print("📚 Skills Demo — Passing skills to agents\n")

    await example_1_with_skills()
    await example_2_different_skills()

    print("\n" + "=" * 60)
    print("DONE!")
    print("=" * 60)


asyncio.run(main())
