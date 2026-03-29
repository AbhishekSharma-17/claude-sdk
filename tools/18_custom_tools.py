"""
Custom Tools: @tool() + create_sdk_mcp_server()
=================================================

3 STEPS TO CREATE A CUSTOM TOOL:

  Step 1: Define your function with @tool() decorator
          → name, description, input_schema

  Step 2: Package into an MCP server with create_sdk_mcp_server()
          → groups tools together under a server name

  Step 3: Pass to ClaudeAgentOptions(mcp_servers={"name": server})
          → Claude can now call your tools

NAMING:
  mcp__<server_name>__<tool_name>
  mcp__utils__validate_email
  mcp__utils__*                  ← wildcard, allow all tools from server

INPUT SCHEMA:
  Defines what parameters the tool accepts.
  Uses JSON Schema format (same as Pydantic .model_json_schema())

RETURN FORMAT:
  Must return: {"content": [{"type": "text", "text": "your result"}]}
  This is the MCP standard response format.
"""

import asyncio
import os
import json
import re
import ast
from datetime import datetime
from dotenv import load_dotenv
from claude_agent_sdk import (
    query, ClaudeAgentOptions, ResultMessage, AssistantMessage,
    ToolUseBlock, TextBlock, tool, create_sdk_mcp_server,
)

load_dotenv()


# =============================================================================
# STEP 1: Define custom tools with @tool()
# =============================================================================

@tool(
    name="validate_email",
    description="Check if an email address is valid and return details",
    input_schema={
        "type": "object",
        "properties": {
            "email": {"type": "string", "description": "Email address to validate"},
        },
        "required": ["email"],
    },
)
async def validate_email(args: dict) -> dict:
    """Your custom Python logic — Claude calls this like any other tool."""
    email = args["email"]
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    is_valid = bool(re.match(pattern, email))

    # Extract parts
    parts = email.split("@") if "@" in email else [email, ""]
    result = {
        "email": email,
        "is_valid": is_valid,
        "username": parts[0],
        "domain": parts[1] if len(parts) > 1 else None,
    }
    return {"content": [{"type": "text", "text": json.dumps(result)}]}


@tool(
    name="validate_python",
    description="Check if Python code has syntax errors. Returns valid or error details.",
    input_schema={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python code to validate"},
        },
        "required": ["code"],
    },
)
async def validate_python(args: dict) -> dict:
    """Validates Python syntax using ast.parse()."""
    code = args["code"]
    try:
        ast.parse(code)
        return {"content": [{"type": "text", "text": json.dumps({
            "valid": True,
            "message": "Syntax is correct",
        })}]}
    except SyntaxError as e:
        return {"content": [{"type": "text", "text": json.dumps({
            "valid": False,
            "error": e.msg,
            "line": e.lineno,
            "offset": e.offset,
        })}]}


@tool(
    name="calculate_cost",
    description="Calculate estimated Claude API cost given input and output token counts",
    input_schema={
        "type": "object",
        "properties": {
            "model": {
                "type": "string",
                "description": "Model name: haiku, sonnet, or opus",
                "enum": ["haiku", "sonnet", "opus"],
            },
            "input_tokens": {"type": "integer", "description": "Number of input tokens"},
            "output_tokens": {"type": "integer", "description": "Number of output tokens"},
        },
        "required": ["model", "input_tokens", "output_tokens"],
    },
)
async def calculate_cost(args: dict) -> dict:
    """Custom pricing calculator — your business logic as a tool."""
    pricing = {
        "haiku":  {"input": 0.80, "output": 4.00},    # per 1M tokens
        "sonnet": {"input": 3.00, "output": 15.00},
        "opus":   {"input": 15.00, "output": 75.00},
    }
    model = args["model"]
    rates = pricing.get(model, pricing["sonnet"])

    input_cost = (args["input_tokens"] / 1_000_000) * rates["input"]
    output_cost = (args["output_tokens"] / 1_000_000) * rates["output"]
    total = input_cost + output_cost

    result = {
        "model": model,
        "input_tokens": args["input_tokens"],
        "output_tokens": args["output_tokens"],
        "input_cost_usd": round(input_cost, 6),
        "output_cost_usd": round(output_cost, 6),
        "total_cost_usd": round(total, 6),
        "calculated_at": datetime.now().isoformat(),
    }
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


# =============================================================================
# STEP 2: Package tools into an MCP server
# =============================================================================

server = create_sdk_mcp_server(
    name="my_utils",
    version="1.0.0",
    tools=[validate_email, validate_python, calculate_cost],
)


# =============================================================================
# STEP 3: Pass to ClaudeAgentOptions
# =============================================================================

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY")},

    # Connect our custom MCP server
    mcp_servers={"utils": server},

    # Allow Claude to call our custom tools
    # Format: mcp__<server_name>__<tool_name>
    allowed_tools=[
        "mcp__utils__validate_email",
        "mcp__utils__validate_python",
        "mcp__utils__calculate_cost",
    ],

    permission_mode="bypassPermissions",
    max_turns=5,
)


# =============================================================================
# RUN — Claude uses our custom tools
# =============================================================================

async def main():
    print("=== Custom Tools: @tool() + create_sdk_mcp_server() ===\n")

    async for message in query(
        prompt="""
        I need you to do 3 things using the available tools:

        1. Validate these emails:
           - abhishek@genaiprotos.com
           - bad-email@@wrong
           - priya.patel@company.co.in

        2. Check if this Python code is valid:
           def greet(name):
               print(f"Hello {name"

        3. Calculate the cost of processing 50,000 input tokens and
           10,000 output tokens on each model (haiku, sonnet, opus)
        """,
        options=options,
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    # Clean up the tool name for display
                    short_name = block.name.replace("mcp__utils__", "")
                    print(f"[Claude called] {short_name}({json.dumps(block.input)})")
                elif isinstance(block, TextBlock):
                    print(f"[Claude says]\n{block.text}")

        elif isinstance(message, ResultMessage):
            print(f"\n[Cost: ${message.total_cost_usd:.4f} | Turns: {message.num_turns}]")


asyncio.run(main())
