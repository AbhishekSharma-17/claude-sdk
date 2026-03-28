"""AWS Bedrock — Code Reviewer Agent

The SAME code reviewer agent as anthropic_direct_agent.py, but routed through
AWS Bedrock instead of the direct Anthropic API.

This demonstrates how easy it is to switch auth providers — only the
environment variables change. The code is identical.

Setup:
    export CLAUDE_CODE_USE_BEDROCK=1
    export AWS_PROFILE=my-profile
    # OR
    export AWS_ACCESS_KEY_ID="AKIA..."
    export AWS_SECRET_ACCESS_KEY="..."
    export AWS_REGION="us-east-1"   # or us-west-2, eu-west-1

Usage:
    CLAUDE_CODE_USE_BEDROCK=1 python examples/auth/bedrock_agent.py

When to use Bedrock:
    - Enterprise AWS deployments with VPC isolation
    - Cost optimization through reserved capacity or committed throughput
    - Compliance requirements (data stays in your AWS account)
    - Unified billing through AWS
    - AWS PrivateLink for no-internet connectivity

Differences from direct API:
    - Requests routed through your AWS account
    - Model names may differ (Bedrock uses ARN-based model IDs)
    - Rate limits governed by your Bedrock provisioned throughput
    - Pricing may differ (Bedrock has on-demand + provisioned)
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

SYSTEM_PROMPT = """\
You are an expert Python code reviewer. When given a file to review:

1. Read the file using the Read tool
2. Search for common issues using Grep:
   - Hardcoded values (magic numbers, hardcoded IDs)
   - Missing error handling
   - Type hint gaps
3. Provide a structured review with:
   - **Bugs**: Actual errors or logic problems
   - **Style**: PEP 8, naming, docstring issues
   - **Improvements**: Specific, actionable suggestions
   - **Score**: Rate the code 1-10

Be concise. Focus on the most impactful issues.
"""


async def main() -> None:
    # ── Verify Bedrock is configured ──────────────────────────────────────
    if not os.environ.get("CLAUDE_CODE_USE_BEDROCK"):
        print("ERROR: Bedrock mode not enabled.")
        print("  export CLAUDE_CODE_USE_BEDROCK=1")
        print("  export AWS_PROFILE=my-profile  (or AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY)")
        print()
        print("To run with direct API instead:")
        print("  python examples/auth/anthropic_direct_agent.py")
        sys.exit(1)

    aws_profile = os.environ.get("AWS_PROFILE", "(default)")
    aws_region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))

    target_file = SAMPLE_DIR / "sample.py"

    # ── Configure the agent ───────────────────────────────────────────────
    # NOTE: The options are IDENTICAL to the direct API version.
    # The SDK detects CLAUDE_CODE_USE_BEDROCK=1 and routes automatically.
    options = ClaudeAgentOptions(
        model="sonnet",                          # SDK maps to Bedrock model ARN
        system_prompt=SYSTEM_PROMPT,
        allowed_tools=["Read", "Glob", "Grep"],
        permission_mode="bypassPermissions",
        max_turns=5,
        max_budget_usd=1.0,
        include_partial_messages=True,

        # Optional: pass AWS-specific env vars to the CLI subprocess
        env={
            "AWS_REGION": aws_region,
        },
    )

    prompt = f"Review the Python file at {target_file}. Give me a thorough code review."

    # ── Run the agent ─────────────────────────────────────────────────────
    print("=" * 60)
    print("  AWS Bedrock — Code Reviewer Agent")
    print("=" * 60)
    print(f"Auth: AWS Bedrock (CLAUDE_CODE_USE_BEDROCK=1)")
    print(f"AWS Profile: {aws_profile}")
    print(f"AWS Region: {aws_region}")
    print(f"Model: sonnet (routed via Bedrock)")
    print(f"Target: {target_file}")
    print(f"Tools: Read, Glob, Grep")
    print(f"Budget: $1.00 max")
    print("-" * 60)

    tool_calls = []
    input_tokens = 0
    output_tokens = 0

    async for message in query(prompt=prompt, options=options):

        if isinstance(message, StreamEvent):
            event = message.event
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                print(delta["text"], end="", flush=True)

        elif isinstance(message, AssistantMessage):
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
                    else:
                        print()

                elif isinstance(block, ToolResultBlock):
                    size = len(block.content or "")
                    print(f"[RESULT] {size} chars")

        elif isinstance(message, ResultMessage):
            print(f"\n\n{'=' * 60}")
            print("  Bedrock Agent Complete")
            print("=" * 60)
            print(f"Provider: AWS Bedrock")
            print(f"Status: {'error' if message.is_error else 'success'}")
            print(f"Cost: ${message.total_cost_usd or 0:.4f}")
            print(f"Input tokens: {input_tokens:,}")
            print(f"Output tokens: {output_tokens:,}")
            print(f"Turns: {message.num_turns}")
            print(f"Duration: {message.duration_ms:,}ms")
            print(f"Tool calls: {' → '.join(tool_calls)}")
            print(f"Session ID: {message.session_id}")

            if message.result:
                print(f"\n--- Review Output ---")
                print(message.result[:1500])


# ── Comparison: What changes between Direct vs Bedrock ────────────────────────
#
#   DIRECT API                          BEDROCK
#   ──────────────────────────────────  ──────────────────────────────────
#   ANTHROPIC_API_KEY=sk-ant-...        CLAUDE_CODE_USE_BEDROCK=1
#                                       AWS_PROFILE=my-profile (or keys)
#   model="sonnet"                      model="sonnet" (same!)
#   Everything else: IDENTICAL           Everything else: IDENTICAL
#
#   The SDK handles the routing. Your code doesn't change.
# ──────────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    asyncio.run(main())
