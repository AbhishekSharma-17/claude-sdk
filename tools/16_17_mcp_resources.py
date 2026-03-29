"""
Tools 16 & 17: ListMcpResources + ReadMcpResource
===================================================
These tools let Claude browse and read "resources" from MCP servers.

WHAT ARE MCP RESOURCES?
  MCP servers can expose data as named resources — like a virtual filesystem.
  Think of it as: MCP tools = functions Claude can call
                   MCP resources = data Claude can browse and read

  ListMcpResources  → list available resources (like "ls")
  ReadMcpResource   → read a specific resource (like "cat")

WHEN TO USE:
  - Database browser: list tables → read table schema
  - Config store: list configs → read specific config
  - API catalog: list endpoints → read endpoint docs
  - Knowledge base: list articles → read one article

NOTE:
  These tools ONLY work when an MCP server is connected that exposes resources.
  Without an MCP server → these tools do nothing.

  Since setting up a real MCP server is complex, this script demonstrates
  the concept using @tool() + create_sdk_mcp_server() which is Tool 18
  (custom tools). We'll see the full custom tool example next.

  For now, here's how these tools WOULD work with a real MCP server:
"""

# ── This is a CONCEPTUAL example — showing how the tools would be used ──

EXAMPLE = """

# If you had an MCP server connected (e.g., a database browser):

options = ClaudeAgentOptions(
    mcp_servers={
        "my_db": {
            "type": "stdio",
            "command": "python",
            "args": ["-m", "my_db_mcp_server"],
        }
    },
    allowed_tools=["ListMcpResources", "ReadMcpResource"],
)

# Claude's flow would be:

# Step 1: Claude calls ListMcpResources()
# Response:
#   [
#     {"uri": "db://tables/users",     "name": "Users Table",     "description": "User accounts"},
#     {"uri": "db://tables/orders",    "name": "Orders Table",    "description": "Order history"},
#     {"uri": "db://tables/products",  "name": "Products Table",  "description": "Product catalog"},
#   ]

# Step 2: Claude calls ReadMcpResource(uri="db://tables/users")
# Response:
#   {
#     "columns": ["id", "name", "email", "created_at"],
#     "row_count": 1500,
#     "sample_rows": [
#       {"id": 1, "name": "Abhishek", "email": "a@b.com", "created_at": "2024-01-15"},
#       ...
#     ]
#   }

# Step 3: Claude uses this data to answer your question

"""


# ── Live demo: create a minimal MCP server with resources ──

import asyncio
import os
import json
from dotenv import load_dotenv
from claude_agent_sdk import (
    query, ClaudeAgentOptions, ResultMessage, AssistantMessage,
    ToolUseBlock, TextBlock, tool, create_sdk_mcp_server,
)

load_dotenv()


# Create custom tools that ACT like resources (since SDK MCP resources
# require a full MCP server implementation, we simulate with tools)
@tool(
    name="list_knowledge_base",
    description="List all available documents in the knowledge base",
    input_schema={"type": "object", "properties": {}, "required": []},
)
async def list_knowledge_base(args: dict) -> dict:
    """Simulates ListMcpResources — returns available resources."""
    docs = [
        {"id": "team", "title": "Team Directory", "type": "json"},
        {"id": "stack", "title": "Tech Stack", "type": "json"},
        {"id": "roadmap", "title": "Q2 Roadmap", "type": "text"},
    ]
    return {"content": [{"type": "text", "text": json.dumps(docs, indent=2)}]}


@tool(
    name="read_knowledge_doc",
    description="Read a specific document from the knowledge base by its ID",
    input_schema={
        "type": "object",
        "properties": {
            "doc_id": {"type": "string", "description": "Document ID to read"},
        },
        "required": ["doc_id"],
    },
)
async def read_knowledge_doc(args: dict) -> dict:
    """Simulates ReadMcpResource — returns content of a specific resource."""
    docs = {
        "team": {
            "members": [
                {"name": "Abhishek", "role": "Lead", "skills": ["Python", "FastAPI", "LLM"]},
                {"name": "Rahul", "role": "Senior", "skills": ["PySpark", "AWS"]},
                {"name": "Priya", "role": "Frontend", "skills": ["React", "TypeScript"]},
            ]
        },
        "stack": {
            "backend": "FastAPI + Python 3.12",
            "database": "PostgreSQL + Redis",
            "ai": "Claude Agent SDK",
            "cloud": "AWS (Bedrock, Lambda, S3)",
            "ci_cd": "GitHub Actions",
        },
        "roadmap": "Q2 2026 Roadmap:\n1. Migrate CI/CD pipeline (April)\n2. Auth module refactor (April-May)\n3. Add observability - OpenTelemetry (May)\n4. Launch v2.0 (June)",
    }
    doc_id = args.get("doc_id", "")
    if doc_id in docs:
        content = docs[doc_id]
        text = json.dumps(content, indent=2) if isinstance(content, dict) else content
        return {"content": [{"type": "text", "text": text}]}
    return {"content": [{"type": "text", "text": f"Document '{doc_id}' not found"}]}


# Package tools into an MCP server
server = create_sdk_mcp_server(
    name="knowledge_base",
    version="1.0.0",
    tools=[list_knowledge_base, read_knowledge_doc],
)

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY")},
    mcp_servers={"kb": server},
    allowed_tools=[
        "mcp__kb__list_knowledge_base",    # list resources
        "mcp__kb__read_knowledge_doc",     # read a resource
    ],
    permission_mode="bypassPermissions",
    max_turns=5,
)


async def main():
    print("=== Tools: ListMcpResources + ReadMcpResource ===")
    print("(simulated via custom MCP server with @tool)\n")

    async for message in query(
        prompt="""
        1. List all available documents in the knowledge base
        2. Read ALL of them
        3. Give me a team summary: who does what, what tech we use, what's planned
        """,
        options=options,
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    print(f"[Claude called] {block.name}({block.input})")
                elif isinstance(block, TextBlock):
                    print(f"[Claude says]\n{block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n[Cost: ${message.total_cost_usd:.4f} | Turns: {message.num_turns}]")


asyncio.run(main())
