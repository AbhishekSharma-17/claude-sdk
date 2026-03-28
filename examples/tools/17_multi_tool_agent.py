"""17 — Multi-Tool Agent Demo

A practical agent that combines multiple tools to perform a real task:
analyzing a codebase and generating a summary report.

Tools used: Glob, Grep, Read, TodoWrite, Write

This demonstrates how Claude orchestrates multiple tools together —
the same way it works in the Claude Code app.

Usage: python examples/tools/17_multi_tool_agent.py
Requires: ANTHROPIC_API_KEY environment variable
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import (
    AssistantMessage, ResultMessage, TextBlock,
    ToolUseBlock, ToolResultBlock,
)

PROJECT_DIR = Path(__file__).parent.parent  # examples/


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        report_path = Path(tmp) / "analysis_report.md"

        options = ClaudeAgentOptions(
            model="sonnet",
            allowed_tools=["Glob", "Grep", "Read", "TodoWrite", "Write"],
            permission_mode="bypassPermissions",
            max_turns=10,
            system_prompt=(
                "You are a senior code analyst. Your job is to analyze a project directory "
                "and produce a structured markdown report. Use TodoWrite to track your progress. "
                "Work methodically: discover files, read key ones, search for patterns, "
                "then write a comprehensive report."
            ),
        )

        prompt = (
            f"Analyze the project at {PROJECT_DIR}. "
            "1) Use Glob to discover all Python files, "
            "2) Use Grep to find all function definitions, "
            "3) Read a few interesting files to understand what they do, "
            "4) Write a markdown analysis report to {report_path} with: "
            "   - File inventory (what files exist), "
            "   - Key functions found, "
            "   - Architecture observations, "
            "   - One recommendation for improvement. "
            "Track your progress with TodoWrite."
        ).format(report_path=report_path)

        print("--- Multi-Tool Agent Demo ---")
        print(f"Analyzing: {PROJECT_DIR}")
        print(f"Report will be written to: {report_path}\n")

        tool_call_count = 0

        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        tool_call_count += 1

                        if block.name == "TodoWrite":
                            todos = block.input.get("todos", [])
                            print(f"\n[TODO UPDATE #{tool_call_count}]")
                            for todo in todos:
                                icon = {"pending": "○", "in_progress": "●", "completed": "✓"}.get(todo["status"], "?")
                                print(f"  {icon} {todo['content']}")
                        else:
                            print(f"[{tool_call_count}] {block.name}", end="")
                            if block.name == "Glob":
                                print(f" — pattern: {block.input.get('pattern')}")
                            elif block.name == "Grep":
                                print(f" — pattern: {block.input.get('pattern')}")
                            elif block.name == "Read":
                                print(f" — {block.input.get('file_path', '?')}")
                            elif block.name == "Write":
                                content = block.input.get("content", "")
                                print(f" — {block.input.get('file_path')} ({len(content)} chars)")
                            else:
                                print()

                    elif isinstance(block, TextBlock) and len(block.text.strip()) > 20:
                        print(f"\n[CLAUDE] {block.text[:200]}...")

            elif isinstance(message, ResultMessage):
                print(f"\n{'='*50}")
                print(f"--- Multi-Tool Agent Complete ---")
                print(f"Total tool calls: {tool_call_count}")
                print(f"Cost: ${message.total_cost_usd or 0:.4f}")
                print(f"Turns: {message.num_turns}")
                print(f"Duration: {message.duration_ms}ms")

                if report_path.exists():
                    report = report_path.read_text()
                    print(f"\n--- Generated Report ({len(report)} chars) ---")
                    print(report[:1000])
                    if len(report) > 1000:
                        print(f"\n... ({len(report) - 1000} more chars)")
                else:
                    print("\nReport was not written to disk (may be in Claude's response).")


if __name__ == "__main__":
    asyncio.run(main())
