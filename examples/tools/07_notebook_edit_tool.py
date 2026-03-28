"""07 — NotebookEdit Tool Demo

The NotebookEdit tool lets Claude edit Jupyter notebook cells by index.
It can replace cell content, insert new cells, or delete cells.

Tool input schema:
    notebook_path: str         — Absolute path to the .ipynb file
    cell_number: int           — 0-indexed cell number (for replace/delete)
    new_source: str            — New cell content
    cell_type: str | None      — "code" or "markdown" (required for insert)
    edit_mode: str             — "replace" | "insert" | "delete"

Usage: python examples/tools/07_notebook_edit_tool.py
Requires: ANTHROPIC_API_KEY environment variable
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        work_nb = Path(tmp) / "sample.ipynb"
        shutil.copy(SAMPLE_DIR / "sample.ipynb", work_nb)

        options = ClaudeAgentOptions(
            model="haiku",
            allowed_tools=["Read", "NotebookEdit"],
            permission_mode="bypassPermissions",
            max_turns=4,
            system_prompt="You are a data scientist. Read and improve Jupyter notebooks.",
        )

        prompt = (
            f"Read the notebook at {work_nb}, then: "
            "1) Add a new markdown cell at the end with a '## Results' heading, "
            "2) Add a new code cell that calls both circle_area(10) and sphere_volume(10) "
            "and prints the results nicely."
        )

        print("--- NotebookEdit Tool Demo ---")
        print(f"Working on: {work_nb}\n")

        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        print(f"[TOOL CALL] {block.name}")
                        if block.name == "NotebookEdit":
                            print(f"  edit_mode: {block.input.get('edit_mode', 'replace')}")
                            print(f"  cell_type: {block.input.get('cell_type')}")
                            src = block.input.get("new_source", "")
                            print(f"  new_source: {src[:100]}...")
                        else:
                            print(f"  path: {block.input.get('file_path')}")

                    elif isinstance(block, TextBlock):
                        print(f"\n[CLAUDE] {block.text}")

            elif isinstance(message, ResultMessage):
                print(f"\n--- Result ---")
                print(f"Cost: ${message.total_cost_usd or 0:.4f}")

                # Show the updated notebook structure
                nb = json.loads(work_nb.read_text())
                print(f"\nNotebook now has {len(nb['cells'])} cells:")
                for i, cell in enumerate(nb["cells"]):
                    src = "".join(cell["source"])[:60]
                    print(f"  [{i}] {cell['cell_type']}: {src}...")


if __name__ == "__main__":
    asyncio.run(main())
