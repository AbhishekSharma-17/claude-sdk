"""16 — ListMcpResources & ReadMcpResource Tool Demo

These tools let Claude discover and read resources exposed by MCP servers.
An MCP server can expose "resources" (read-only data) alongside "tools" (actions).

ListMcpResources — Lists all available resources from connected MCP servers
ReadMcpResource  — Reads the content of a specific resource by URI

This demo creates a custom MCP server that exposes resources, then shows
Claude discovering and reading them.

Usage: python examples/tools/16_mcp_resources_tool.py
Requires: ANTHROPIC_API_KEY environment variable
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query, tool, create_sdk_mcp_server
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock, ToolResultBlock


# Define a custom tool that our MCP server exposes
@tool(
    name="get_config",
    description="Get the application configuration",
    input_schema={
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Config key to look up"},
        },
        "required": ["key"],
    },
)
def get_config_tool(key: str) -> str:
    """Return a config value."""
    config = {
        "database_url": "postgresql://localhost:5432/myapp",
        "redis_url": "redis://localhost:6379",
        "log_level": "INFO",
    }
    return config.get(key, f"Unknown key: {key}")


async def main() -> None:
    # Create an in-process MCP server with our custom tool
    my_server = create_sdk_mcp_server(
        name="app-config",
        version="1.0.0",
        tools=[get_config_tool],
    )

    options = ClaudeAgentOptions(
        model="haiku",
        allowed_tools=[
            "ListMcpResources",
            "ReadMcpResource",
            "mcp__app-config__get_config",  # Our custom MCP tool
        ],
        permission_mode="bypassPermissions",
        max_turns=4,
        mcp_servers={"app-config": my_server},
        system_prompt=(
            "You are a system explorer. Use ListMcpResources to discover available resources, "
            "then use the app-config tools to explore the configuration."
        ),
    )

    prompt = (
        "List all available MCP resources, then use the app-config server "
        "to look up the database_url and log_level configuration."
    )

    print("--- MCP Resources Tool Demo ---")
    print("Shows ListMcpResources + ReadMcpResource + custom MCP tool.\n")

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    print(f"[TOOL CALL] {block.name}")
                    for k, v in block.input.items():
                        print(f"  {k}: {str(v)[:100]}")

                elif isinstance(block, ToolResultBlock):
                    print(f"[TOOL RESULT] {(block.content or '')[:300]}")

                elif isinstance(block, TextBlock):
                    print(f"\n[CLAUDE] {block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n--- Result ---")
            print(f"Cost: ${message.total_cost_usd or 0:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
