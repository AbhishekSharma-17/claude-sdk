"""Anthropic Direct API — Code Reviewer Agent

A practical agent that reviews Python code for bugs, style issues, and improvements.
Authenticates using the ANTHROPIC_API_KEY environment variable (direct Anthropic API).

This is the simplest authentication method — just set your API key and go.

Setup:
    export ANTHROPIC_API_KEY="sk-ant-..."

Usage:
    python examples/auth/anthropic_direct_agent.py

Features demonstrated:
    - Direct Anthropic API authentication
    - Multi-tool agent (Read, Glob, Grep)
    - Custom system prompt for focused behavior
    - Cost tracking per invocation
    - Structured message handling with tool call logging
    - Streaming with include_partial_messages
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
)

SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"

# ── System prompt: focused code reviewer ──────────────────────────────────────

SYSTEM_PROMPT = """\
You are an expert Python code reviewer. When given a file to review:

1. Read the file using the Read tool
2. Search for common issues using Grep:
   - Hardcoded values (magic numbers, hardcoded IDs)
   - Missing error handling (bare except, no try/except around I/O)
   - Type hint gaps
3. Provide a structured review with:
   - **Bugs**: Actual errors or logic problems
   - **Style**: PEP 8, naming, docstring issues
   - **Improvements**: Specific, actionable suggestions
   - **Score**: Rate the code 1-10

Be concise. Focus on the most impactful issues.
"""


async def main() -> None:
    # ── Verify API key is set ─────────────────────────────────────────────
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: Set ANTHROPIC_API_KEY environment variable first.")
        print("  export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)

    target_file = SAMPLE_DIR / "sample.py"

    # ── Configure the agent ───────────────────────────────────────────────
    options = ClaudeAgentOptions(
        # Authentication: SDK reads ANTHROPIC_API_KEY automatically
        # No additional auth config needed!

        model="sonnet",                          # Claude Sonnet 4.6
        system_prompt=SYSTEM_PROMPT,
        allowed_tools=["Read", "Glob", "Grep"],  # Read-only tools for review
        permission_mode="bypassPermissions",      # Non-interactive
        max_turns=5,                              # Enough for read + grep + respond
        max_budget_usd=1.0,                       # Cost cap: $1 max
        include_partial_messages=True,            # Stream intermediate events
    )

    prompt = f"Review the Python file at {target_file}. Give me a thorough code review."

    # ── Run the agent ─────────────────────────────────────────────────────
    print("=" * 60)
    print("  Anthropic Direct API — Code Reviewer Agent")
    print("=" * 60)
    print(f"Auth: ANTHROPIC_API_KEY (direct)")
    print(f"Model: sonnet (Claude Sonnet 4.6)")
    print(f"Target: {target_file}")
    print(f"Tools: Read, Glob, Grep")
    print(f"Budget: $1.00 max")
    print("-" * 60)

    tool_calls = []
    input_tokens = 0
    output_tokens = 0

    async for message in query(prompt=prompt, options=options):

        # Track streaming events (real-time text generation)
        if isinstance(message, StreamEvent):
            event = message.event
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                print(delta["text"], end="", flush=True)

        # Track tool calls and text blocks
        elif isinstance(message, AssistantMessage):
            # Accumulate token usage
            usage = getattr(message, "usage", None)
            if isinstance(usage, dict):
                input_tokens += usage.get("input_tokens", 0)
                output_tokens += usage.get("output_tokens", 0)

            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    tool_calls.append(block.name)
                    print(f"\n[TOOL] {block.name}", end="")
                    if block.name == "Read":
                        print(f" → {block.input.get('file_path')}")
                    elif block.name == "Grep":
                        print(f" → pattern='{block.input.get('pattern')}'")
                    elif block.name == "Glob":
                        print(f" → {block.input.get('pattern')}")
                    else:
                        print()

                elif isinstance(block, ToolResultBlock):
                    size = len(block.content or "")
                    status = "error" if block.is_error else "ok"
                    print(f"[RESULT] {size} chars ({status})")

        # Final result with cost data
        elif isinstance(message, ResultMessage):
            print(f"\n\n{'=' * 60}")
            print("  Agent Complete")
            print("=" * 60)
            print(f"Status: {'error' if message.is_error else 'success'}")
            print(f"Cost: ${message.total_cost_usd or 0:.4f}")
            print(f"Input tokens: {input_tokens:,}")
            print(f"Output tokens: {output_tokens:,}")
            print(f"Turns: {message.num_turns}")
            print(f"Duration: {message.duration_ms:,}ms")
            print(f"Tool calls: {' → '.join(tool_calls) if tool_calls else 'none'}")
            print(f"Session ID: {message.session_id}")

            if message.result:
                print(f"\n--- Review Output ---")
                print(message.result[:1500])


if __name__ == "__main__":
    asyncio.run(main())
