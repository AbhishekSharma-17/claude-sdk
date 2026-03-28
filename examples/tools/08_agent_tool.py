"""08 — Agent (Subagent) Tool Demo

The Agent tool lets Claude spawn subagents — independent Claude instances with
their own tools, model, and system prompt. Subagents get a fresh context (no
parent conversation history) and return their result to the parent.

To use subagents, you must:
1. Include "Agent" in allowed_tools
2. Define agents via the `agents` option (AgentDefinition)

Tool input schema (what Claude sends to invoke a subagent):
    description: str       — Short description of the task (3-5 words)
    prompt: str            — The task for the subagent
    subagent_type: str     — Which defined agent to use

Usage: python examples/tools/08_agent_tool.py
Requires: ANTHROPIC_API_KEY environment variable
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, SystemMessage, TextBlock, ToolUseBlock

SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"


async def main() -> None:
    options = ClaudeAgentOptions(
        model="haiku",
        allowed_tools=["Read", "Glob", "Grep", "Agent"],
        permission_mode="bypassPermissions",
        max_turns=5,
        system_prompt=(
            "You are a tech lead. Delegate specialized tasks to your subagents. "
            "Use the 'sql-analyst' agent for SQL analysis and the 'python-reviewer' "
            "agent for Python code review."
        ),
        agents={
            "sql-analyst": AgentDefinition(
                description="Analyzes SQL files for complexity and patterns",
                prompt=(
                    "You are a SQL analyst. When given a SQL file, identify: "
                    "1) All SQL constructs used (SELECT, JOIN, CTE, etc.), "
                    "2) Complexity level (simple/medium/complex), "
                    "3) Any potential performance concerns. Be concise."
                ),
                tools=["Read"],
                model="haiku",
            ),
            "python-reviewer": AgentDefinition(
                description="Reviews Python code for bugs and improvements",
                prompt=(
                    "You are a Python code reviewer. When given a file, find: "
                    "1) Bugs or logic errors, "
                    "2) Missing type hints, "
                    "3) One improvement suggestion. Be concise."
                ),
                tools=["Read"],
                model="haiku",
            ),
        },
    )

    prompt = (
        f"I have two files in {SAMPLE_DIR}: sample.sql and sample.py. "
        "Delegate the SQL file to the sql-analyst and the Python file to the python-reviewer. "
        "Then give me a combined summary of their findings."
    )

    print("--- Agent (Subagent) Tool Demo ---")
    print(f"Prompt: {prompt[:80]}...\n")

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            # Check if this is from a subagent
            if message.parent_tool_use_id:
                print(f"[SUBAGENT RESPONSE] (parent: {message.parent_tool_use_id})")

            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    if block.name == "Agent":
                        print(f"[TOOL CALL] Agent (subagent)")
                        print(f"  subagent_type: {block.input.get('subagent_type')}")
                        print(f"  description: {block.input.get('description')}")
                        prompt_preview = block.input.get("prompt", "")[:100]
                        print(f"  prompt: {prompt_preview}...")
                    else:
                        print(f"[TOOL CALL] {block.name}: {block.input}")

                elif isinstance(block, TextBlock):
                    print(f"\n[CLAUDE] {block.text[:300]}")

        elif isinstance(message, SystemMessage):
            if message.subtype in ("task_started", "task_notification"):
                print(f"[SYSTEM] {message.subtype}: {message.data}")

        elif isinstance(message, ResultMessage):
            print(f"\n--- Result ---")
            print(f"Cost: ${message.total_cost_usd or 0:.4f}")
            print(f"Turns: {message.num_turns}")
            print(f"Duration: {message.duration_ms}ms")


if __name__ == "__main__":
    asyncio.run(main())
