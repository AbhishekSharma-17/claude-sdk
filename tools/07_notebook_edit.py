"""
Tool 7: NotebookEdit
=====================
Lets Claude edit Jupyter notebook cells directly.
Understands notebook structure — no raw JSON manipulation needed.

Operations:
  - Edit existing cell   → provide cell_number + new_source
  - Add new cell         → provide insert_after (cell number to insert after)
  - Delete a cell        → provide cell_number + new_source="" OR use delete mode

Cell types: "code" or "markdown"
"""

import asyncio
import os
import json
from dotenv import load_dotenv
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, AssistantMessage, ToolUseBlock, TextBlock

load_dotenv()

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY")},
    allowed_tools=["Read", "NotebookEdit"],
    permission_mode="bypassPermissions",
    max_turns=5,
)


def show_notebook(path: str, label: str):
    """Print all cells in a notebook in a readable way."""
    print(f"\n--- {label} ---")
    with open(path) as f:
        nb = json.load(f)
    for i, cell in enumerate(nb["cells"]):
        cell_type = cell["cell_type"].upper()
        source = "".join(cell["source"])
        print(f"\n  Cell {i} [{cell_type}]:\n    {source}")
    print()


async def main():
    print("=== Tool: NotebookEdit ===\n")

    nb_path = "sample_data/analysis.ipynb"

    show_notebook(nb_path, "BEFORE")

    async for message in query(
        prompt="""
        Read sample_data/analysis.ipynb and do these changes:
        1. Fix the divide by zero bug in the last code cell (change /0 to /2)
        2. Update the markdown cell that says "TODO: add charts here"
           → change it to "## Results - Analysis Complete"
        3. Add a new markdown cell at the end saying:
           "## Notebook reviewed and fixed by Claude"
        """,
        options=options,
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    if block.name == "NotebookEdit":
                        print(f"[Claude called] NotebookEdit(")
                        print(f"  notebook  : {block.input.get('notebook_path')}")
                        print(f"  cell      : {block.input.get('cell_number')}")
                        print(f"  type      : {block.input.get('cell_type')}")
                        print(f"  new source: {repr(block.input.get('new_source'))}")
                        print(f")")
                    else:
                        print(f"[Claude called] {block.name}({block.input})")
                elif isinstance(block, TextBlock):
                    print(f"[Claude says] {block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n[Cost: ${message.total_cost_usd:.4f} | Turns: {message.num_turns}]")

    show_notebook(nb_path, "AFTER")


asyncio.run(main())
