"""
Tool 14: AskUserQuestion
==========================
Lets Claude pause and ask the user a question during execution.
Claude waits for your reply before continuing.

ONLY works with ClaudeSDKClient (multi-turn) — not with query().
With query() there's no way to send a reply back.

This is how interactive agents work:
  Claude: "Which file should I refactor?"  ← AskUserQuestion
  You:    "app.py"                          ← your reply
  Claude: proceeds to refactor app.py

NOTE:
  In batch/non-interactive pipelines → don't use this tool
  In interactive apps → this is how you get human-in-the-loop
"""

import asyncio
import os
from dotenv import load_dotenv
from claude_agent_sdk import (
    ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage,
    ResultMessage, TextBlock, ToolUseBlock,
)

load_dotenv()

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY")},
    allowed_tools=["Read", "Glob", "AskUserQuestion"],
    permission_mode="bypassPermissions",
    max_turns=10,
)


async def main():
    print("=== Tool: AskUserQuestion ===\n")
    print("Claude will ask YOU a question. Type your answer when prompted.\n")

    async with ClaudeSDKClient(options=options) as client:

        # First turn — give Claude a task that requires user input
        await client.query(
            "List the files in sample_data/ and ask the user which file "
            "they want you to analyze. Then read and summarize that file."
        )

        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        if block.name == "AskUserQuestion":
                            question = block.input.get("question", "")
                            options_list = block.input.get("options", [])
                            print(f"\n[Claude asks] {question}")
                            if options_list:
                                for i, opt in enumerate(options_list, 1):
                                    print(f"  {i}. {opt}")

                            # Get user input from terminal
                            answer = input("\n→ Your answer: ").strip()

                            # Send the answer back to Claude
                            await client.query(answer)
                        else:
                            print(f"[Claude called] {block.name}({block.input})")
                    elif isinstance(block, TextBlock):
                        print(f"[Claude says] {block.text}")

            elif isinstance(message, ResultMessage):
                print(f"\n[Result] {message.result}")
                print(f"[Cost: ${message.total_cost_usd:.4f} | Turns: {message.num_turns}]")

        # Second turn — receive the response after user's answer
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(f"[Claude says] {block.text}")
                    elif isinstance(block, ToolUseBlock):
                        print(f"[Claude called] {block.name}({block.input})")

            elif isinstance(message, ResultMessage):
                print(f"\n[Cost: ${message.total_cost_usd:.4f} | Turns: {message.num_turns}]")


asyncio.run(main())
