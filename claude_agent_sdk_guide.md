# Claude Agent SDK -- Comprehensive Guide for 3XCode Convertor

A complete reference for the Claude Agent SDK (v0.1.51, bundling CLI v2.1.85) as used in the SQL-to-PySpark converter pipeline. This guide covers installation, authentication, the `query()` API, `ClaudeSDKClient`, all configuration options (37 parameters), tool systems (17 built-in tools), custom MCP tools, hooks, subagents, cost tracking, and practical patterns from the 3XCode Convertor project.

> **Package History:** The SDK was originally published as `claude-code-sdk` (`ClaudeCodeOptions`) and renamed to `claude-agent-sdk` (`ClaudeAgentOptions`) in v0.1.0 (Sep 28, 2025). There have been 53 releases to date (v0.0.23 through v0.1.51).

## Table of Contents

1. [Overview](#1-overview)
2. [Installation & Setup](#2-installation--setup)
3. [Breaking Changes & Migration](#3-breaking-changes--migration)
4. [Authentication](#4-authentication)
5. [The query() API -- Our Primary Interface](#5-the-query-api----our-primary-interface)
6. [ClaudeSDKClient -- Stateful Multi-Turn API](#6-claudesdkclient----stateful-multi-turn-api)
7. [ClaudeAgentOptions -- Complete Reference (37 Parameters)](#7-claudeagentoptions----complete-reference-37-parameters)
8. [Tool System (17 Built-in Tools)](#8-tool-system-17-built-in-tools)
9. [Custom MCP Tools](#9-custom-mcp-tools)
10. [MCP Server Integration](#10-mcp-server-integration)
11. [Message Types](#11-message-types)
12. [Hooks System](#12-hooks-system)
13. [Subagent System](#13-subagent-system)
14. [Structured Output](#14-structured-output)
15. [Extended Thinking](#15-extended-thinking)
16. [Session Management](#16-session-management)
17. [Permission System & can_use_tool](#17-permission-system--can_use_tool)
18. [Plugin System](#18-plugin-system)
19. [Cost Tracking](#19-cost-tracking)
20. [Rate Limiting](#20-rate-limiting)
21. [Streaming](#21-streaming)
22. [Error Handling](#22-error-handling)
23. [Transport Layer](#23-transport-layer)
24. [Our Implementation Patterns](#24-our-implementation-patterns)
25. [Future Enhancements](#25-future-enhancements)
26. [Quick Reference Card](#26-quick-reference-card)

---

## 1. Overview

The Claude Agent SDK (`claude-agent-sdk`) is a Python package that wraps the Claude Code CLI, providing a programmatic interface to Claude's agentic capabilities. It communicates via JSON lines to a local CLI subprocess that handles authentication and model routing.

| Field | Value |
|-------|-------|
| **Python Package** | `claude-agent-sdk` (import: `claude_agent_sdk`) |
| **TypeScript Package** | `@anthropic-ai/claude-agent-sdk` |
| **Latest Version** | 0.1.51 (March 27, 2026) |
| **Bundled CLI** | v2.1.85 |
| **Python Requirement** | >=3.10 (supports 3.10, 3.11, 3.12, 3.13) |
| **License** | MIT |
| **Status** | Alpha |
| **PyPI** | https://pypi.org/project/claude-agent-sdk/ |
| **GitHub (Python)** | https://github.com/anthropics/claude-agent-sdk-python |
| **GitHub (TypeScript)** | https://github.com/anthropics/claude-agent-sdk-typescript |
| **Official Docs** | https://platform.claude.com/docs/en/agent-sdk/overview |
| **Python API Reference** | https://platform.claude.com/docs/en/agent-sdk/python |
| **Migration Guide** | https://platform.claude.com/docs/en/agent-sdk/migration-guide |

### Six Core APIs

**1. `query(prompt, options)` -- Stateless, one-shot invocation (our approach)**
- Async iterator of messages
- Creates a new session per call
- Perfect for batch pipelines where each invocation is independent
- Used in all 4 phases of the 3XCode Convertor

**2. `ClaudeSDKClient` -- Stateful, multi-turn conversation**
- Maintains session history across multiple exchanges
- Supports `interrupt()`, `set_model()`, `set_permission_mode()`, `rewind_files()`
- Dynamic MCP control: `add_mcp_server()`, `remove_mcp_server()`, `toggle_mcp_server()`
- Supports `async with` context manager
- Not used in 3XCode Convertor (our pipeline is stateless by design)

**3. `@tool()` decorator -- Define custom MCP tools**
- Create Python functions that Claude can invoke as tools
- Type-safe input schemas via dict or Pydantic

**4. `create_sdk_mcp_server()` -- Create in-process MCP servers**
- Package custom tools as MCP servers without subprocess overhead

**5. Session management functions** -- `list_sessions()`, `get_session_messages()`, `get_session_info()`, `rename_session()`, `tag_session()`, `fork_session()`, `delete_session()`

**6. `Transport` -- Abstract base class for custom transport implementations**

### `query()` vs `ClaudeSDKClient` Comparison

| Feature | `query()` | `ClaudeSDKClient` |
|---------|-----------|-------------------|
| Session | New each call | Reuses same session |
| Conversation | Single exchange | Multiple exchanges |
| Connection | Automatic | Manual control |
| Streaming Input | Yes | Yes |
| Interrupts | No | Yes (`interrupt()`) |
| Model Switching | No | Yes (`set_model()`) |
| MCP Control | Static only | Dynamic add/remove/toggle |
| Custom Tools | Via options | Via options |
| Hooks | Via options | Via options |
| File Rewinding | No | Yes (`rewind_files()`) |

### Why We Use `query()`

The 3XCode Convertor's 4-phase pipeline is **stateless batch processing**:
- Phase 1 analyzes SQL independently
- Phase 2 uses Phase 1's output but doesn't need session continuity
- Phase 3 is local validation (no LLM)
- Phase 4 audits the results

Each phase is independent; resuming from a previous session adds complexity without benefit. We pass context explicitly via prompts instead.

### SDK Auto-Bundles Claude Code CLI

The SDK includes a bundled Claude Code CLI binary (v2.1.85). No separate CLI installation is needed beyond `pip install claude-agent-sdk`.

> **Important:** Anthropic does NOT allow third-party developers to offer claude.ai login or rate limits for products built on the Agent SDK.

---

## 2. Installation & Setup

### Install the SDK

Using `uv` (our package manager):

```bash
uv add claude-agent-sdk>=0.1.51
```

Using pip:

```bash
pip install claude-agent-sdk>=0.1.51
```

### Python Version

Requires Python 3.10+. We use **Python 3.12+** with modern type hints:

```python
from __future__ import annotations
from typing import Literal

# Python 3.12+ syntax
def my_function(value: str | None = None) -> dict:
    """Use X | None instead of Optional[X]."""
```

### Verify Installation

```bash
python -c "from claude_agent_sdk import query, ClaudeAgentOptions; print('OK')"
```

---

## 3. Breaking Changes & Migration

### v0.1.0 Breaking Changes (Sep 28, 2025)

The SDK was renamed from `claude-code-sdk` to `claude-agent-sdk` with three breaking changes:

#### 3.1 Package and Type Rename

```python
# BEFORE (v0.0.x)
from claude_code_sdk import query, ClaudeCodeOptions
options = ClaudeCodeOptions(model="claude-opus-4-6")

# AFTER (v0.1.0+)
from claude_agent_sdk import query, ClaudeAgentOptions
options = ClaudeAgentOptions(model="claude-opus-4-6")
```

#### 3.2 System Prompt No Longer Defaults to Claude Code Preset

The SDK now uses a minimal system prompt by default. To restore the old behavior:

```python
# Opt in to Claude Code system prompt explicitly
options = ClaudeAgentOptions(
    system_prompt={"type": "preset", "preset": "claude_code"}
)

# Or use a custom system prompt
options = ClaudeAgentOptions(system_prompt="You are a helpful coding assistant")

# Or append to the preset
options = ClaudeAgentOptions(
    system_prompt={
        "type": "preset",
        "preset": "claude_code",
        "append": "Also follow PEP 8 style guidelines"
    }
)
```

#### 3.3 Settings Sources No Longer Loaded by Default

The SDK no longer reads from filesystem settings (CLAUDE.md, settings.json, slash commands) by default:

```python
# To restore old behavior (load all settings)
options = ClaudeAgentOptions(setting_sources=["user", "project", "local"])

# Or load only project settings (CLAUDE.md)
options = ClaudeAgentOptions(setting_sources=["project"])
```

### v0.1.49 to v0.1.51 Changes

| Version | CLI | Key Changes |
|---------|-----|------------|
| **v0.1.51** | 2.1.85 | `fork_session()`, `delete_session()`, `task_budget` option, `SystemPromptFile` support, `AgentDefinition` gains `disallowedTools`/`maxTurns`/`initialPrompt`, `dontAsk` permission mode, forward-compatible preserved fields on messages, 15 bug fixes including Python 3.10 compat, SIGKILL fallback, TypedDict schema fix |
| **v0.1.50** | 2.1.81 | `get_session_info()`, `tag`/`created_at` on `SDKSessionInfo` |
| **v0.1.49** | 2.1.77 | `AgentDefinition` gains `skills`/`memory`/`mcpServers`, per-turn `usage` on `AssistantMessage`, `tag_session()`, `rename_session()`, typed `RateLimitEvent` |

### Notable v0.1.46 Changes (Mar 5, 2026)

- `list_sessions()` and `get_session_messages()` for session history
- `add_mcp_server()`, `remove_mcp_server()`, and typed `McpServerStatus`
- `TaskStarted`, `TaskProgress`, `TaskNotification` message subclasses
- `stop_reason` field on `ResultMessage`
- `agent_id` and `agent_type` fields in tool-lifecycle hooks

---

## 4. Authentication

The SDK supports four authentication methods. **We use Direct Anthropic API** in development and testing.

### 4.1 Direct Anthropic API Key (Our Approach)

Set the `ANTHROPIC_API_KEY` environment variable:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Or add to `.env`:

```env
ANTHROPIC_API_KEY=sk-ant-...
```

The SDK reads this automatically. No further configuration needed.

**When to use:**
- Development and local testing
- CI/CD pipelines with credential management
- Simple deployments on single machines

### 4.2 AWS Bedrock

Set two environment variables:

```bash
export CLAUDE_CODE_USE_BEDROCK=1
export AWS_PROFILE=my-profile  # or AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY
```

The SDK will route all requests through AWS Bedrock.

**When to use:**
- Enterprise AWS deployments with VPC isolation
- Cost optimization through reserved capacity
- Compliance with AWS-only infrastructure

### 4.3 Google Vertex AI

Set one environment variable:

```bash
export CLAUDE_CODE_USE_VERTEX=1
# Google Cloud SDK credentials are detected automatically
```

**When to use:**
- Google Cloud deployments
- Integration with BigQuery or Firestore

### 4.4 Azure AI Foundry

Set one environment variable:

```bash
export CLAUDE_CODE_USE_FOUNDRY=1
```

**When to use:**
- Azure deployments
- Integration with Azure OpenAI or other Azure services

### Authentication Method Comparison

| Provider | Environment Variable(s) | Additional Setup | Default Behavior |
|----------|-------------------------|--------------------|------------------|
| Direct API | `ANTHROPIC_API_KEY` | Set API key | Try Direct API first |
| Bedrock | `CLAUDE_CODE_USE_BEDROCK=1` | AWS credentials | Route via Bedrock |
| Vertex AI | `CLAUDE_CODE_USE_VERTEX=1` | gcloud SDK | Route via Vertex |
| Azure | `CLAUDE_CODE_USE_FOUNDRY=1` | Azure CLI | Route via Azure |

Our implementation in `app/settings.py` reads `ANTHROPIC_API_KEY` but the SDK handles the rest transparently.

---

## 5. The query() API -- Our Primary Interface

The `query()` function is the stateless entry point. It streams messages asynchronously and returns a mix of intermediate messages and a final result.

### Function Signature

```python
async def query(
    *,
    prompt: str | AsyncIterable[dict[str, Any]],
    options: ClaudeAgentOptions | None = None,
    transport: Transport | None = None,
) -> AsyncIterator[
    UserMessage | AssistantMessage | SystemMessage | ResultMessage | StreamEvent | RateLimitEvent
]:
    """
    Invoke Claude Code with a prompt and options.

    Args:
        prompt: Input as string or async iterable for streaming input.
        options: Configuration (defaults to ClaudeAgentOptions()).
        transport: Custom transport for CLI communication (optional).

    Yields messages as they arrive from the CLI.
    The final message is always ResultMessage with the full result + cost.
    """
```

**Key differences from earlier versions:**
- All parameters are keyword-only (`*`)
- `prompt` accepts `AsyncIterable[dict]` for streaming input
- `options` is optional (defaults to `ClaudeAgentOptions()`)
- `transport` parameter for custom transport implementations

### Return Type Explained

**`AsyncIterator[Message]`** -- An async generator yielding messages in order:

1. **SystemMessage** -- Session initialization (contains `session_id`)
2. **AssistantMessage** (0 or more) -- Claude's intermediate responses with tool calls
3. **UserMessage** (0 or more) -- Tool results fed back to Claude
4. **StreamEvent** (0 or more, if `include_partial_messages=True`) -- Raw API events
5. **RateLimitEvent** (optional) -- Rate limit warning/rejection
6. **TaskStarted/TaskProgress/TaskNotification** (optional) -- Subagent task updates
7. **ResultMessage** (final) -- Complete result with cost, tokens, duration

### Minimal Example (5 Lines)

```python
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

options = ClaudeAgentOptions(model="sonnet")
async for message in query(prompt="What is 2 + 2?", options=options):
    if isinstance(message, ResultMessage):
        print(f"Result: {message.result}")
        print(f"Cost: ${message.total_cost_usd:.4f}")
```

### Streaming Input Example

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions

async def stream_prompt():
    """Stream prompt chunks for large inputs."""
    yield {"type": "text", "text": "Analyze this SQL:\n"}
    yield {"type": "text", "text": "SELECT * FROM users WHERE active = 1\n"}
    yield {"type": "text", "text": "GROUP BY department"}

async for message in query(prompt=stream_prompt(), options=ClaudeAgentOptions()):
    print(message)
```

### Our Production Wrapper: `invoke_claude()`

We don't call `query()` directly. Instead, we wrap it in `/Users/abhisheksharma/Documents/Genaiprotos/Developer/3XDE/3XCodeConvertor/sql_to_pyspark/claude_runner.py`:

```python
async def invoke_claude(
    *,
    prompt: str,
    system_prompt: str | None = None,
    model: str | None = None,
    allowed_tools: list[str] | None = None,
    max_turns: int | None = None,
    timeout_seconds: int | None = None,
    cwd: str | None = None,
) -> InvocationResult:
    """
    Invoke Claude Code via the SDK and return a rich result with cost data.

    Returns:
        InvocationResult with text, cost_usd, token counts, duration, num_turns, session_id.

    Raises:
        ConverterTimeoutError: If invocation exceeds timeout.
        ConverterSDKError: If the SDK returns any error.
    """
    settings = get_settings()
    model = model or settings.converter_model
    max_turns = max_turns if max_turns is not None else settings.converter_max_turns
    timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.converter_timeout

    # Build SDK options
    options_kwargs: dict = {
        "allowed_tools": allowed_tools or ["Read", "Glob", "Grep"],
        "permission_mode": settings.converter_permission_mode,
        "max_turns": max_turns,
        "model": model,
    }

    if system_prompt is not None:
        options_kwargs["system_prompt"] = system_prompt

    if cwd is not None:
        options_kwargs["cwd"] = cwd

    # Budget cap
    if settings.cost_tracking_enabled and settings.max_budget_usd > 0:
        options_kwargs["max_budget_usd"] = settings.max_budget_usd

    options = ClaudeAgentOptions(**options_kwargs)

    # Iterate messages, capture tokens and final result
    result_text = ""
    cost_usd = 0.0
    input_tokens = 0
    output_tokens = 0

    try:
        await asyncio.wait_for(_run(), timeout=timeout_seconds)
    except TimeoutError:
        raise ConverterTimeoutError(f"Timed out after {timeout_seconds}s") from None
    except ConverterSDKError as exc:
        logger.error("sdk_error", error=str(exc))
        raise

    return InvocationResult(
        text=result_text,
        cost_usd=cost_usd,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

    async def _run() -> None:
        """Inner generator to capture messages."""
        nonlocal result_text, cost_usd, input_tokens, output_tokens

        async for message in query(prompt=prompt, options=options):
            # Capture tokens from AssistantMessage
            if isinstance(message, AssistantMessage):
                usage = getattr(message, "usage", None)
                if isinstance(usage, dict):
                    input_tokens += usage.get("input_tokens", 0)
                    output_tokens += usage.get("output_tokens", 0)

            # Capture final result with cost from ResultMessage
            if isinstance(message, ResultMessage):
                result_text = message.result or ""
                cost_usd = getattr(message, "total_cost_usd", 0.0) or 0.0
```

### Usage in the Pipeline

Each phase calls `invoke_claude()` or `invoke_claude_json()`:

```python
# Phase 1: SQL Analysis (in orchestrator.py)
system_prompt, user_prompt = build_analysis_prompt(sql_content, file_name)
analysis_json_raw, phase1_result = await invoke_claude_json(
    prompt=user_prompt,
    system_prompt=system_prompt,
    model=model,
    allowed_tools=["Read", "Glob", "Grep"],
)
# phase1_result.cost_usd contains the cost for this phase
```

---

## 6. ClaudeSDKClient -- Stateful Multi-Turn API

`ClaudeSDKClient` maintains a persistent connection to the Claude Code CLI process, enabling multi-turn conversations, dynamic control, and runtime MCP management.

### Full API Reference

```python
class ClaudeSDKClient:
    def __init__(
        self,
        options: ClaudeAgentOptions | None = None,
        transport: Transport | None = None,
    ) -> None: ...

    # --- Lifecycle ---
    async def connect(self, prompt: str | AsyncIterable[dict] | None = None) -> None
    async def disconnect(self) -> None

    # --- Core Conversation ---
    async def query(self, prompt: str | AsyncIterable[dict], session_id: str = "default") -> None
    async def receive_messages(self) -> AsyncIterator[Message]
    async def receive_response(self) -> AsyncIterator[Message]

    # --- Control ---
    async def interrupt(self) -> None
    async def set_permission_mode(self, mode: str) -> None
    async def set_model(self, model: str | None = None) -> None
    async def rewind_files(self, user_message_id: str) -> None
    async def stop_task(self, task_id: str) -> None

    # --- MCP Management ---
    async def get_mcp_status(self) -> McpStatusResponse
    async def reconnect_mcp_server(self, server_name: str) -> None
    async def toggle_mcp_server(self, server_name: str, enabled: bool) -> None
    async def add_mcp_server(self, name: str, config: McpServerConfig) -> None
    async def remove_mcp_server(self, name: str) -> None

    # --- Info ---
    async def get_server_info(self) -> dict[str, Any] | None
```

### Context Manager Usage

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, TextBlock

async def multi_turn_example():
    options = ClaudeAgentOptions(
        allowed_tools=["Read", "Write", "Bash"],
        permission_mode="acceptEdits",
    )

    async with ClaudeSDKClient(options=options) as client:
        # First turn
        await client.query("What files are in the current directory?")
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(f"Claude: {block.text}")

        # Follow-up -- Claude remembers context from first turn
        await client.query("Which of those files is the largest?")
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(f"Claude: {block.text}")
```

### Manual Lifecycle Management

```python
client = ClaudeSDKClient(options=options)
await client.connect()

try:
    await client.query("First question")
    async for message in client.receive_response():
        process(message)

    await client.query("Follow-up question")
    async for message in client.receive_response():
        process(message)
finally:
    await client.disconnect()
```

### receive_messages() vs receive_response()

| Method | Scope | Use Case |
|--------|-------|----------|
| `receive_response()` | Messages from current query only | Standard turn-by-turn conversation |
| `receive_messages()` | All messages, including between queries | Monitoring, background notifications |

### Interrupting and Stopping

```python
async with ClaudeSDKClient(options=options) as client:
    await client.query("Generate a very long report")

    # Interrupt mid-generation
    await client.interrupt()

    # Or stop a specific background task
    await client.stop_task("task-id-123")
```

### Dynamic Model Switching

```python
async with ClaudeSDKClient(options=options) as client:
    # Start with fast model
    await client.set_model("haiku")
    await client.query("Quick analysis of this file")
    async for msg in client.receive_response():
        process(msg)

    # Switch to powerful model for complex task
    await client.set_model("opus")
    await client.query("Now refactor the entire module")
    async for msg in client.receive_response():
        process(msg)
```

### Dynamic MCP Server Control

```python
async with ClaudeSDKClient(options=options) as client:
    # Check MCP server status
    status = await client.get_mcp_status()
    for server in status.servers:
        print(f"{server.name}: {server.status}")

    # Add a new MCP server at runtime
    await client.add_mcp_server("db", {
        "type": "stdio",
        "command": "python",
        "args": ["-m", "my_db_mcp_server"],
    })

    # Toggle server on/off
    await client.toggle_mcp_server("db", enabled=False)
    await client.toggle_mcp_server("db", enabled=True)

    # Reconnect a failed server
    await client.reconnect_mcp_server("db")

    # Remove server
    await client.remove_mcp_server("db")
```

### File Checkpointing and Rewinding

```python
options = ClaudeAgentOptions(
    enable_file_checkpointing=True,
    permission_mode="acceptEdits",
)

checkpoint_id = None

async with ClaudeSDKClient(options=options) as client:
    await client.query("Refactor the auth module")
    async for message in client.receive_response():
        if isinstance(message, UserMessage) and message.uuid and not checkpoint_id:
            checkpoint_id = message.uuid  # Save first user message UUID as checkpoint

    # Later: rewind all file changes back to checkpoint
    if checkpoint_id:
        await client.rewind_files(checkpoint_id)
```

### In 3XCode Convertor

Not used. Our pipeline is stateless -- each phase is an independent `query()` call. `ClaudeSDKClient` would be useful for interactive tools or multi-step workflows that need conversation memory.

---

## 7. ClaudeAgentOptions -- Complete Reference (37 Parameters)

`ClaudeAgentOptions` is the configuration object passed to `query()` or `ClaudeSDKClient`. It supports **37 parameters** (including 2 deprecated), each controlling a specific behavior.

### Complete Parameter Table

| # | Parameter | Type | Default | Description |
|---|-----------|------|---------|-------------|
| 1 | `tools` | `list[str] \| ToolsPreset \| None` | `None` | Base tool set config; preset: `{"type": "preset", "preset": "claude_code"}` |
| 2 | `allowed_tools` | `list[str]` | `[]` | Auto-approve these tools without prompting |
| 3 | `disallowed_tools` | `list[str]` | `[]` | Always deny these tools (checked first, overrides everything) |
| 4 | `system_prompt` | `str \| SystemPromptPreset \| None` | `None` | Custom or preset system prompt |
| 5 | `mcp_servers` | `dict[str, McpServerConfig] \| str \| Path` | `{}` | MCP server configurations or path to config file |
| 6 | `permission_mode` | `PermissionMode \| None` | `None` | `"default"`, `"acceptEdits"`, `"plan"`, `"bypassPermissions"`, `"dontAsk"` |
| 7 | `continue_conversation` | `bool` | `False` | Continue the most recent conversation |
| 8 | `resume` | `str \| None` | `None` | Session ID to resume |
| 9 | `fork_session` | `bool` | `False` | Fork session instead of continuing (creates new session ID) |
| 10 | `max_turns` | `int \| None` | `None` | Maximum agentic turns |
| 11 | `max_budget_usd` | `float \| None` | `None` | Maximum cost in USD per invocation |
| 12 | `model` | `str \| None` | `None` | Claude model alias or full ID |
| 13 | `fallback_model` | `str \| None` | `None` | Fallback model if primary fails |
| 14 | `betas` | `list[SdkBeta]` | `[]` | Beta features; e.g., `"context-1m-2025-08-07"` |
| 15 | `output_format` | `dict[str, Any] \| None` | `None` | Structured output (JSON Schema) |
| 16 | `permission_prompt_tool_name` | `str \| None` | `None` | MCP tool name for permission prompts |
| 17 | `cwd` | `str \| Path \| None` | `None` | Working directory for file operations |
| 18 | `cli_path` | `str \| Path \| None` | `None` | Custom path to Claude Code CLI binary |
| 19 | `settings` | `str \| None` | `None` | Path to settings file |
| 20 | `add_dirs` | `list[str \| Path]` | `[]` | Additional directories Claude can access |
| 21 | `env` | `dict[str, str]` | `{}` | Environment variables for CLI subprocess |
| 22 | `extra_args` | `dict[str, str \| None]` | `{}` | Additional CLI arguments |
| 23 | `max_buffer_size` | `int \| None` | `None` | Max bytes for CLI stdout buffering |
| 24 | `stderr` | `Callable[[str], None] \| None` | `None` | Callback for stderr output |
| 25 | `debug_stderr` | `Any` | `sys.stderr` | **DEPRECATED** -- use `stderr` instead |
| 26 | `can_use_tool` | `CanUseTool \| None` | `None` | Custom tool permission callback |
| 27 | `hooks` | `dict[HookEvent, list[HookMatcher]] \| None` | `None` | Hook configurations keyed by event type |
| 28 | `user` | `str \| None` | `None` | User identifier for tracking |
| 29 | `include_partial_messages` | `bool` | `False` | Include `StreamEvent` messages during streaming |
| 30 | `agents` | `dict[str, AgentDefinition] \| None` | `None` | Programmatic subagent definitions |
| 31 | `setting_sources` | `list[SettingSource] \| None` | `None` | `["user", "project", "local"]` -- controls which settings to load |
| 32 | `sandbox` | `SandboxSettings \| None` | `None` | Sandbox behavior configuration |
| 33 | `plugins` | `list[SdkPluginConfig]` | `[]` | Custom plugins from local paths |
| 34 | `thinking` | `ThinkingConfig \| None` | `None` | Extended thinking configuration |
| 35 | `max_thinking_tokens` | `int \| None` | `None` | **DEPRECATED** -- use `thinking` instead |
| 36 | `effort` | `Literal["low", "medium", "high", "max"] \| None` | `None` | Thinking effort level |
| 37 | `enable_file_checkpointing` | `bool` | `False` | File change tracking for rewinding |

**Total: 37 parameters** (including 2 deprecated ones: `debug_stderr` and `max_thinking_tokens`)

### 7.1 `model` -- Model Selection

**Type:** `str | None`

**Description:** Claude model alias or full model ID.

**Accepted values:**
- `"haiku"` -- Claude Haiku 4.5 (fast, cheap, best for Phase 1)
- `"sonnet"` -- Claude Sonnet 4.6 (balanced, default for Phase 2)
- `"opus"` -- Claude Opus 4.6 (powerful, slower, best for complex Phase 2)
- Full model IDs: `"claude-opus-4-6"`, `"claude-sonnet-4-6"`, `"claude-haiku-4-5-20251001"`, etc.

**Default:** From settings or environment

**Example:**

```python
options = ClaudeAgentOptions(model="sonnet")
# or
options = ClaudeAgentOptions(model="claude-opus-4-6")
```

**In 3XCode Convertor:**
- Phase 1 (analyze): `sonnet` -- good balance for thoroughness
- Phase 2 (convert): `sonnet` or `opus` -- needs accurate code generation
- Phase 4 (audit): `sonnet` -- just formatting, no complexity

### 7.2 `fallback_model` -- Automatic Model Fallback

**Type:** `str | None`

**Description:** If the primary model fails (rate limit, overloaded), the SDK automatically retries with this model.

**Example:**

```python
options = ClaudeAgentOptions(
    model="opus",
    fallback_model="sonnet",  # Fall back to sonnet if opus is unavailable
)
```

**In 3XCode Convertor:** Not used yet. Could be useful for production deployments where opus availability varies.

### 7.3 `system_prompt` -- Instruction Override

**Type:** `str | SystemPromptPreset | None`

**Description:** System prompt instructions for Claude's behavior.

**Three forms:**

Simple string override:

```python
options = ClaudeAgentOptions(
    system_prompt="You are a SQL expert. Be concise. Return valid JSON only."
)
```

Claude Code preset:

```python
options = ClaudeAgentOptions(
    system_prompt={"type": "preset", "preset": "claude_code"}
)
```

Preset with append:

```python
options = ClaudeAgentOptions(
    system_prompt={
        "type": "preset",
        "preset": "claude_code",
        "append": "Also, validate all SQL syntax before responding."
    }
)
```

**In 3XCode Convertor:**

Each phase has a custom system prompt built by `prompts.py`:

```python
system_prompt, user_prompt = build_analysis_prompt(sql_content, file_name)
options = ClaudeAgentOptions(system_prompt=system_prompt)
```

These system prompts are ~500 lines each and contain:
- Step-by-step instructions (e.g., "10-step analysis process")
- Construct taxonomy (e.g., "types of SQL we're looking for")
- Convertibility rules (e.g., "what counts as full vs. partial")
- Critical gotchas (e.g., "DATEDIFF arg order is reversed in PySpark")
- Output schema (e.g., "return this JSON structure")

### 7.4 `tools` -- Base Tool Set

**Type:** `list[str] | ToolsPreset | None`

**Description:** Controls the base set of tools available to Claude. Different from `allowed_tools`.

**Important distinction:**
- `tools` -- Sets *which tools exist* (base tool set)
- `allowed_tools` -- Sets *which tools are auto-approved* (no permission prompt needed)

**Examples:**

Use the Claude Code preset (all built-in tools):
```python
options = ClaudeAgentOptions(
    tools={"type": "preset", "preset": "claude_code"}
)
```

Or restrict to specific tools only:
```python
options = ClaudeAgentOptions(
    tools=["Read", "Glob", "Grep"]  # Only these tools exist
)
```

### 7.5 `allowed_tools` -- Whitelist Tools

**Type:** `list[str]`

**Description:** Auto-approve these tools without prompting. Does NOT restrict Claude to only these tools -- it controls which tools skip the permission prompt.

**Example:**

```python
# Phase 1: Explore the codebase
options = ClaudeAgentOptions(
    allowed_tools=["Read", "Glob", "Grep"]
)

# Phase 2: Read knowledge base only
options = ClaudeAgentOptions(
    allowed_tools=["Read"]
)

# Phase 4: Pure generation, no tools
options = ClaudeAgentOptions(
    allowed_tools=[]
)
```

**In 3XCode Convertor:**

```python
# Phase 1 (analyze)
allowed_tools=["Read", "Glob", "Grep"]  # Explore SQL files

# Phase 2 (convert)
allowed_tools=["Read"]  # Reference knowledge base

# Phase 3 (validate)
# No Claude call, local validation only

# Phase 4 (audit)
allowed_tools=[]  # Pure generation
```

### 7.6 `disallowed_tools` -- Blacklist Tools

**Type:** `list[str]`

**Description:** Always deny these tools. Checked FIRST, overrides `allowed_tools` and `permission_mode` (including `bypassPermissions`).

**Example:**

```python
# Allow all tools except Bash and Write (for safety)
options = ClaudeAgentOptions(
    permission_mode="bypassPermissions",
    disallowed_tools=["Bash", "Write"]  # These are denied even with bypassPermissions
)
```

### 7.7 `permission_mode` -- Auto-Approval Level

**Type:** `PermissionMode | None`

**Description:** How much auto-approval the SDK grants for tool invocations.

**Values:**

| Value | Behavior |
|-------|----------|
| `"default"` | Requires `can_use_tool` callback or asks user (interactive) |
| `"acceptEdits"` | Auto-approve file reads and edits; ask about writes/Bash |
| `"plan"` | Plan only; don't execute tool calls |
| `"bypassPermissions"` | Auto-approve all tool calls without prompting |
| `"dontAsk"` | Denies anything not in `allowed_tools` (no prompting, no callback) |

**In 3XCode Convertor:**

```python
options = ClaudeAgentOptions(
    permission_mode="bypassPermissions"  # Default from settings
)
```

We use `bypassPermissions` because:
- CLI is non-interactive (no user present to approve)
- We trust the prompts (they don't ask for risky operations)
- Batch processing needs to be hands-free

### 7.8 `max_turns` -- Agent Loop Limit

**Type:** `int | None`

**Description:** Maximum number of turns (reasoning -> tool use -> result cycles).

**Default:** From settings (`CONVERTER_MAX_TURNS=3`)

**Example:**

```python
options = ClaudeAgentOptions(max_turns=5)
```

**Why it matters:**

Each turn uses tokens. More turns = higher cost and longer latency, but better problem-solving for complex scenarios.

```
Turn 1: Claude reads SQL files, finds issues
  -> (tool: Glob, Read, Grep)
Turn 2: Claude processes findings, generates code
  -> (tool: none, just generation)
Turn 3: Claude reviews and finalizes
  -> (done)
```

**In 3XCode Convertor:**

- Phase 1: `max_turns=3` -- might need multiple reads to find all constructs
- Phase 2: `max_turns=3` -- might need to refine code generation
- Phase 4: `max_turns=1` -- pure generation, no tool loops

### 7.9 `max_budget_usd` -- Cost Cap

**Type:** `float | None`

**Description:** Hard limit on USD spend for this invocation. SDK stops if exceeded.

**Default:** From settings (`MAX_BUDGET_USD=5.0`)

**Example:**

```python
options = ClaudeAgentOptions(max_budget_usd=2.5)
```

**In 3XCode Convertor:**

```python
if settings.cost_tracking_enabled and settings.max_budget_usd > 0:
    options_kwargs["max_budget_usd"] = settings.max_budget_usd
```

This prevents runaway costs in batch jobs. If a phase would exceed the budget, the SDK raises an error.

### 7.10 `cwd` -- Working Directory

**Type:** `str | Path | None`

**Description:** Set the working directory for file tool operations (Read, Write, Glob, Bash).

**Example:**

```python
from pathlib import Path

options = ClaudeAgentOptions(
    cwd=Path("/path/to/sql/files")
)
```

**In 3XCode Convertor:** Not currently used, since we pass full paths to prompts.

### 7.11 `add_dirs` -- Additional Accessible Directories

**Type:** `list[str | Path]`

**Description:** Additional directories that Claude can access beyond `cwd`.

**Example:**

```python
options = ClaudeAgentOptions(
    cwd="/project/src",
    add_dirs=["/project/docs", "/project/tests"],  # Also accessible
)
```

### 7.12 `env` -- Environment Variables

**Type:** `dict[str, str]`

**Description:** Pass extra environment variables to the CLI subprocess.

**Example:**

```python
options = ClaudeAgentOptions(
    env={"PYSPARK_PYTHON": "/usr/bin/python3.12"}
)
```

### 7.13 `output_format` -- Structured Output

**Type:** `dict[str, Any] | None`

**Description:** Request JSON schema conformance. The SDK will enforce output compliance.

**Example:**

```python
from pydantic import BaseModel
import json

class AnalysisResult(BaseModel):
    constructs: list[str]
    convertibility_pct: float

schema = json.loads(AnalysisResult.model_json_schema())

options = ClaudeAgentOptions(
    output_format={
        "type": "json_schema",
        "schema": schema
    }
)
```

**Important:** The SDK's structured output behavior varies between versions. In 3XCode Convertor, we use this as a hint but also have a fallback parser:

```python
# Try to extract JSON if structured output isn't enforced
def _extract_json(text: str) -> dict:
    """Fallback JSON extraction from text response."""
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try code block
    if "```json" in text:
        start = text.index("```json") + len("```json")
        end = text.index("```", start)
        return json.loads(text[start:end].strip())

    # Try to find first { ... } balanced block
    brace_start = text.find("{")
    if brace_start != -1:
        depth = 0
        for i in range(brace_start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[brace_start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break

    raise ValueError("No valid JSON object found in Claude response")
```

### 7.14 `thinking` -- Extended Thinking Config

**Type:** `ThinkingConfig | None`

**Description:** Enable Claude's extended thinking for harder problems.

**Three modes:**

```python
# Disabled (default)
options = ClaudeAgentOptions(thinking={"type": "disabled"})

# Adaptive (auto-decide)
options = ClaudeAgentOptions(thinking={"type": "adaptive"})

# Enabled with budget
options = ClaudeAgentOptions(thinking={"type": "enabled", "budget_tokens": 10000})
```

**In 3XCode Convertor:**

```python
def _build_thinking_config(settings: Settings) -> dict | None:
    """Build ThinkingConfig dict from settings, or None if disabled."""
    match settings.converter_thinking_mode:
        case "adaptive":
            return {"type": "adaptive"}
        case "enabled":
            return {"type": "enabled", "budget_tokens": settings.converter_thinking_budget}
        case _:
            return None

# Then in invoke_claude():
thinking = _build_thinking_config(settings)
if thinking is not None:
    options_kwargs["thinking"] = thinking
```

### 7.15 `effort` -- Effort Level

**Type:** `Literal["low", "medium", "high", "max"] | None`

**Description:** How hard Claude should try. Related to thinking depth.

| Level | Cost | Speed | Best For |
|-------|------|-------|----------|
| `"low"` | 1x | Fast | Simple tasks, analysis |
| `"medium"` | 1.5x | Medium | Balanced (default) |
| `"high"` | 2x | Slow | Complex conversions |
| `"max"` | 3x | Very Slow | Edge cases, rare errors |

**In 3XCode Convertor:**

```python
if settings.converter_effort is not None:
    options_kwargs["effort"] = settings.converter_effort
```

### 7.16 `mcp_servers` -- External MCP Servers

**Type:** `dict[str, McpServerConfig] | str | Path`

**Description:** Connect to external MCP servers for custom tools. Accepts a dict of configs or a path to an MCP config JSON file.

See [Section 10: MCP Server Integration](#10-mcp-server-integration) for full details.

**In 3XCode Convertor:** Not used yet. Future enhancement: PySpark AST validator as a custom MCP tool.

### 7.17 `hooks` -- Lifecycle Event Hooks

**Type:** `dict[HookEvent, list[HookMatcher]] | None`

**Description:** Register callbacks for SDK lifecycle events using `HookMatcher` objects.

See [Section 12: Hooks System](#12-hooks-system) for full details.

**In 3XCode Convertor:** Not used yet, but planned for DEBUG logging of tool invocations.

### 7.18 `agents` -- Subagent Definitions

**Type:** `dict[str, AgentDefinition] | None`

**Description:** Define and use subagents for parallel or specialized task handling.

See [Section 13: Subagent System](#13-subagent-system) for full details.

**In 3XCode Convertor:** Not used currently.

### 7.19 `betas` -- Feature Flags

**Type:** `list[SdkBeta]`

**Description:** Enable experimental SDK features.

```python
options = ClaudeAgentOptions(
    betas=["context-1m-2025-08-07"]  # Enable 1M context window for Sonnet 4.5 / Sonnet 4
)
```

### 7.20 `resume` -- Resume a Session

**Type:** `str | None`

**Description:** Session ID to resume a previous conversation.

```python
options = ClaudeAgentOptions(resume="session-abc123")
```

### 7.21 `fork_session` -- Fork a Session

**Type:** `bool`

**Description:** When `True` and used with `resume`, creates a new session branched from the resumed session. The original session is unchanged.

```python
options = ClaudeAgentOptions(
    resume="session-abc123",
    fork_session=True,  # Creates a new session ID branched from session-abc123
)
```

**In 3XCode Convertor:** Not used. Our pipeline is stateless. Future: could resume Phase 2 from Phase 1's session on failure.

### 7.22 `continue_conversation` -- Continue Most Recent Session

**Type:** `bool`

**Description:** When `True`, continues the most recently active conversation. Simpler alternative to `resume` when you don't need a specific session ID.

```python
options = ClaudeAgentOptions(continue_conversation=True)
```

### 7.23 `setting_sources` -- Control Settings Loading

**Type:** `list[SettingSource] | None`

**Description:** Controls which filesystem settings are loaded. Since v0.1.0, no settings are loaded by default.

**Values:** `"user"`, `"project"`, `"local"`

```python
# Load project settings (CLAUDE.md) only
options = ClaudeAgentOptions(setting_sources=["project"])

# Load all settings
options = ClaudeAgentOptions(setting_sources=["user", "project", "local"])
```

**Must include `"project"` to load CLAUDE.md files.**

### 7.24 `sandbox` -- Bash Sandboxing

**Type:** `SandboxSettings | None`

**Description:** Configure sandbox behavior for the Bash tool.

```python
options = ClaudeAgentOptions(
    sandbox={
        "timeout_seconds": 30,
        "readonly_paths": ["/etc", "/sys"],
        "allowed_commands": ["python", "pip"]
    }
)
```

### 7.25 `can_use_tool` -- Custom Permission Callback

**Type:** `CanUseTool | None`

**Description:** Custom function that decides whether each tool call is allowed. See [Section 17: Permission System](#17-permission-system--can_use_tool) for full details.

### 7.26 `plugins` -- Custom Plugins

**Type:** `list[SdkPluginConfig]`

**Description:** Load custom plugins from local paths. See [Section 18: Plugin System](#18-plugin-system).

### 7.27 `include_partial_messages` -- Streaming

**Type:** `bool`

**Description:** Yield `StreamEvent` messages as Claude thinks. Useful for progress bars.

```python
options = ClaudeAgentOptions(include_partial_messages=True)
```

**In 3XCode Convertor:** Not used. Batch pipeline doesn't need progress feedback.

### 7.28 `cli_path` -- Custom CLI Path

**Type:** `str | Path | None`

**Description:** Path to a custom Claude Code CLI binary. Overrides the bundled CLI.

```python
options = ClaudeAgentOptions(cli_path="/usr/local/bin/claude")
```

### 7.29 `settings` -- Settings File Path

**Type:** `str | None`

**Description:** Path to a custom settings JSON file.

### 7.30 `extra_args` -- Additional CLI Arguments

**Type:** `dict[str, str | None]`

**Description:** Additional arguments passed to the CLI subprocess. Keys are argument names, values are argument values (or `None` for flags).

```python
options = ClaudeAgentOptions(
    extra_args={"replay-user-messages": None}  # Flag with no value
)
```

### 7.31 `max_buffer_size` -- Buffer Control

**Type:** `int | None`

**Description:** Max bytes to buffer from CLI stdout before processing.

### 7.32 `stderr` -- Stderr Callback

**Type:** `Callable[[str], None] | None`

**Description:** Callback invoked with stderr output from the CLI process.

```python
options = ClaudeAgentOptions(
    stderr=lambda line: logger.debug("cli_stderr", line=line)
)
```

### 7.33 `user` -- User Identifier

**Type:** `str | None`

**Description:** User identifier for tracking and analytics.

### 7.34 `permission_prompt_tool_name` -- Custom Permission Tool

**Type:** `str | None`

**Description:** Name of an MCP tool to use for permission prompts instead of the default behavior.

### 7.35 `enable_file_checkpointing` -- File Change Tracking

**Type:** `bool`

**Description:** Enables file change tracking. Required for `ClaudeSDKClient.rewind_files()`.

### Summary Table -- Which Options We Use

| Option | Used | Value | Why |
|--------|------|-------|-----|
| model | Yes | `"sonnet"` (configurable) | Different model per deployment |
| system_prompt | Yes | Per-phase custom prompts | Different instructions per phase |
| allowed_tools | Yes | Varies by phase | Phase 1: [Read, Glob, Grep], Phase 2: [Read], Phase 4: [] |
| permission_mode | Yes | `"bypassPermissions"` | Non-interactive CLI, batch processing |
| max_turns | Yes | `3` (configurable) | Prevent infinite loops, control cost |
| max_budget_usd | Yes | `5.0` (configurable) | Cost safety cap per phase |
| thinking | No | Disabled by default | Latency penalty not worth it for our use case |
| effort | No | Not set | Balanced default is sufficient |
| output_format | No | Not used | Fallback JSON extraction is more flexible |
| mcp_servers | No | Not needed | SDK built-in tools sufficient |
| hooks | No | Not used (yet) | Future: DEBUG logging |
| agents | No | Not used (yet) | Future: different models per phase |
| betas | No | Not used | No experimental features needed |
| cwd | No | Not used | Use full paths in prompts instead |
| sandbox | No | Not restricted | Trust our prompts |
| include_partial_messages | No | False | Batch pipeline, no streaming needed |
| can_use_tool | No | Not used | bypassPermissions is sufficient |
| plugins | No | Not used | No custom plugins needed |
| fallback_model | No | Not used | Single model sufficient currently |
| setting_sources | No | Not set | No filesystem settings needed |

---

## 8. Tool System (17 Built-in Tools)

The SDK provides 17 built-in tools for Claude to use. Each tool can be whitelisted/blacklisted via `allowed_tools` and `disallowed_tools`.

### 8.1 Core Tools (7)

| Tool | What It Does | Input | When to Use |
|------|-------------|-------|-------------|
| **Read** | Read file contents and images | `{"file_path": str, "offset": int?, "limit": int?}` | Phase 1 (explore SQL), Phase 2 (read knowledge base) |
| **Write** | Create or overwrite files | `{"file_path": str, "content": str}` | Phase 2 (generate .py files) |
| **Edit** | Replace text in files in place | `{"file_path": str, "old_string": str, "new_string": str}` | Not used (we generate complete files) |
| **Bash** | Execute shell commands | `{"command": str}` | Not used (CLI-only, no shell needed) |
| **Glob** | Find files by glob pattern | `{"pattern": str, "path": str?}` | Phase 1 (find all .sql files) |
| **Grep** | Search file contents with regex | `{"pattern": str, "path": str?, "output_mode": str?}` | Phase 1 (search constructs) |
| **NotebookEdit** | Edit Jupyter notebook cells | `{"notebook_path": str, "cell_number": int, ...}` | Not used |

### 8.2 Extended Tools (10)

| Tool | What It Does | When to Use |
|------|-------------|-------------|
| **Agent** (aka Task) | Spawn subagents for parallel work | Multi-agent orchestration |
| **AskUserQuestion** | Get user clarification with multiple choice | Interactive apps only |
| **WebSearch** | Search the web | Research tasks |
| **WebFetch** | Fetch and analyze web content | Content retrieval |
| **TodoWrite** | Manage todo lists | Task tracking during complex work |
| **BashOutput** | Get output from background bash processes | Long-running commands |
| **KillBash** | Kill background shell processes | Cleanup |
| **ExitPlanMode** | Get user approval to exit plan mode | Plan -> execute transitions |
| **ListMcpResources** | List available MCP resources | MCP resource discovery |
| **ReadMcpResource** | Read MCP resource content | MCP resource access |

### 8.3 Tool Name Notes

- The **Agent** tool was renamed from **Task** in CLI v2.1.63. Both names may appear in older documentation.
- When allowing the Agent tool for subagent invocation, use `"Agent"` in `allowed_tools`.
- MCP tools use the naming convention: `mcp__<server_name>__<tool_name>` (e.g., `mcp__utils__calculate`).

### 8.4 Our Tool Configuration Strategy

**Phase 1 (Analyze):**
```python
allowed_tools=["Read", "Glob", "Grep"]
```
- **Read:** Load SQL files
- **Glob:** Find all .sql files in a directory
- **Grep:** Search for specific SQL patterns (e.g., "CREATE PROCEDURE")

**Phase 2 (Convert):**
```python
allowed_tools=["Read"]
```
- **Read:** Access knowledge base files (sql_to_pyspark_mapping.md, etc.)
- No Glob/Grep: we already know what to read
- No Write: we generate the file in the response JSON, not via tool

**Phase 3 (Validate):**
```python
# No LLM call at all -- local Python validation
```

**Phase 4 (Audit):**
```python
allowed_tools=[]
```
- Pure generation task
- No tool use needed

**Why we restrict:**
1. **Cost reduction** -- Each tool call uses tokens
2. **Safety** -- Only allow necessary tools
3. **Behavior focus** -- Force Claude to stick to the task
4. **Faster execution** -- No tool-use overhead

---

## 9. Custom MCP Tools

Create custom tools using the `@tool` decorator and `create_sdk_mcp_server()`.

### 9.1 @tool Decorator

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool(
    name="validate_pyspark",
    description="Validate PySpark code syntax",
    input_schema={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "PySpark Python code to validate"},
        },
        "required": ["code"],
    },
)
async def validate_pyspark_tool(args: dict[str, Any]) -> dict[str, Any]:
    """Validate PySpark code using ast.parse()."""
    import ast
    try:
        ast.parse(args["code"])
        return {"content": [{"type": "text", "text": "Syntax valid"}]}
    except SyntaxError as e:
        return {"content": [{"type": "text", "text": f"Syntax error at line {e.lineno}: {e.msg}"}]}

@tool(
    name="get_time",
    description="Get current time",
    input_schema={},
)
async def get_time(args: dict[str, Any]) -> dict[str, Any]:
    from datetime import datetime
    return {"content": [{"type": "text", "text": f"Time: {datetime.now()}"}]}
```

### 9.2 create_sdk_mcp_server()

Package custom tools into an in-process MCP server:

```python
server = create_sdk_mcp_server(
    name="utilities",
    version="1.0.0",
    tools=[validate_pyspark_tool, get_time],
)

options = ClaudeAgentOptions(
    mcp_servers={"utils": server},
    allowed_tools=[
        "mcp__utils__validate_pyspark",
        "mcp__utils__get_time",
    ],
)
```

### 9.3 Tool Annotations

Add metadata hints for tool behavior:

```python
from claude_agent_sdk import ToolAnnotations

@tool(
    name="read_config",
    description="Read a configuration file",
    input_schema={"file_path": str},
    annotations=ToolAnnotations(
        title="Config Reader",
        readOnlyHint=True,        # Enables parallel execution
        destructiveHint=False,    # Safe to run
        idempotentHint=True,      # Same input = same output
        openWorldHint=False,      # No external side effects
    ),
)
async def read_config(args: dict[str, Any]) -> dict[str, Any]:
    ...
```

### 9.4 Tool Naming Convention

MCP tools follow a strict naming convention:

```
Pattern:  mcp__<server_name>__<tool_name>
Example:  mcp__weather__get_temperature
Wildcard: mcp__weather__*  (all tools from a server)
```

**Examples in allowed_tools:**

```python
allowed_tools=[
    "Read",                          # Built-in tool
    "mcp__utils__calculate",         # Specific MCP tool
    "mcp__weather__*",               # All tools from weather server
]
```

### 9.5 Our Use Case in 3XCode Convertor

Future enhancement -- create a custom PySpark validator MCP tool that runs `ast.parse()` and checks for known PySpark APIs:

```python
@tool(
    name="validate_pyspark_code",
    description="Validate PySpark Python code syntax and PySpark API usage",
    input_schema={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python code to validate"},
        },
        "required": ["code"],
    },
)
async def validate_pyspark_code(args: dict[str, Any]) -> dict[str, Any]:
    """Validate using ast.parse() and PySpark API checker."""
    from sql_to_pyspark.validator import validate_pyspark_code
    result = validate_pyspark_code(args["code"])
    return {"content": [{"type": "text", "text": result.model_dump_json()}]}
```

---

## 10. MCP Server Integration

MCP (Model Context Protocol) servers extend Claude's tool capabilities with external services.

### 10.1 Four Transport Types

```python
from claude_agent_sdk import McpServerConfig

# 1. Stdio -- subprocess communication
mcp_servers={
    "my_tool": {
        "type": "stdio",
        "command": "/path/to/mcp/server",
        "args": ["--config", "file.json"],
        "env": {"API_KEY": "..."},
    }
}

# 2. SSE -- HTTP with Server-Sent Events
mcp_servers={
    "my_tool": {
        "type": "sse",
        "url": "http://localhost:3000/sse",
        "headers": {"Authorization": "Bearer ..."},
    }
}

# 3. HTTP -- Standard HTTP
mcp_servers={
    "my_tool": {
        "type": "http",
        "url": "http://localhost:8000",
        "headers": {"Authorization": "Bearer ..."},
    }
}

# 4. SDK -- In-process (no subprocess overhead)
from claude_agent_sdk import create_sdk_mcp_server
server = create_sdk_mcp_server(name="my_tools", tools=[...])
mcp_servers={
    "my_tool": server,  # McpSdkServerConfig
}
```

### 10.2 MCP Config File Path

Instead of inline config, point to a JSON file:

```python
options = ClaudeAgentOptions(
    mcp_servers="/path/to/mcp-config.json"
)
```

### 10.3 MCP Server Status

```python
class McpServerStatus:
    name: str
    status: Literal["connected", "failed", "needs-auth", "pending", "disabled"]
    serverInfo: dict | None    # {name, version}
    error: str | None
    config: dict | None
    scope: str | None
    tools: list[dict] | None  # [{name, description, annotations}]
```

### 10.4 Dynamic MCP Control (ClaudeSDKClient Only)

```python
async with ClaudeSDKClient(options=options) as client:
    # Check status of all MCP servers
    status = await client.get_mcp_status()
    for server in status.servers:
        print(f"{server.name}: {server.status}")
        if server.tools:
            for tool in server.tools:
                print(f"  - {tool['name']}: {tool['description']}")

    # Add a new server at runtime
    await client.add_mcp_server("db", {"type": "stdio", "command": "db-server"})

    # Remove a server
    await client.remove_mcp_server("db")

    # Toggle on/off
    await client.toggle_mcp_server("weather", enabled=False)

    # Reconnect a failed server
    await client.reconnect_mcp_server("weather")
```

### 10.5 In-Process vs External Servers

| Aspect | In-Process (SDK) | External (stdio/sse/http) |
|--------|-------------------|---------------------------|
| Latency | Lowest (no IPC) | Higher (subprocess/network) |
| Deployment | Single process | Separate processes/services |
| Language | Python only | Any language |
| Type Safety | Full | Via JSON Schema |
| Debugging | Standard Python debugger | Separate debugging |

### 10.6 In 3XCode Convertor

Not used yet. Future enhancement: PySpark AST validator as a custom in-process MCP tool.

---

## 11. Message Types

The `query()` function yields different message types. Here is what each one contains and how we use it.

### 11.1 Message Union Type

```python
Message = UserMessage | AssistantMessage | SystemMessage | ResultMessage | StreamEvent | RateLimitEvent
```

### 11.2 UserMessage

**When it appears:** Tool results fed back to Claude

```python
@dataclass
class UserMessage:
    content: str | list[ContentBlock]
    uuid: str | None = None
    parent_tool_use_id: str | None = None
    tool_use_result: dict[str, Any] | None = None
```

### 11.3 AssistantMessage

**When it appears:** Claude responds (intermediate or final)

```python
@dataclass
class AssistantMessage:
    content: list[ContentBlock]
    model: str                                        # Model that generated this message
    parent_tool_use_id: str | None = None             # Set when from subagent
    error: AssistantMessageError | None = None        # Error type if failed
    usage: dict[str, Any] | None = None               # Per-turn token usage (since v0.1.49)

# Error types:
AssistantMessageError = Literal[
    "authentication_failed",
    "billing_error",
    "rate_limit",
    "invalid_request",
    "server_error",
    "max_output_tokens",
    "unknown",
]
```

**Content block types:**

```python
ContentBlock = TextBlock | ThinkingBlock | ToolUseBlock | ToolResultBlock

# TextBlock -- Plain text response
@dataclass
class TextBlock:
    text: str

# ThinkingBlock -- Extended thinking (if enabled)
@dataclass
class ThinkingBlock:
    thinking: str
    signature: str

# ToolUseBlock -- Claude wants to use a tool
@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]

# ToolResultBlock -- Result from a tool call
@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: str | list[dict] | None
    is_error: bool | None
```

**In 3XCode Convertor:**

```python
if isinstance(message, AssistantMessage):
    usage = getattr(message, "usage", None)
    if isinstance(usage, dict):
        input_tokens += usage.get("input_tokens", 0)
        output_tokens += usage.get("output_tokens", 0)
        cache_read_tokens += usage.get("cache_read_input_tokens", 0)
        cache_creation_tokens += usage.get("cache_creation_input_tokens", 0)
```

### 11.4 SystemMessage

**When it appears:** Session initialization and system events

```python
@dataclass
class SystemMessage:
    subtype: str                   # e.g., "init"
    data: dict[str, Any]           # Contains session_id for "init" subtype
```

### 11.5 ResultMessage (Most Important)

**When it appears:** Final message (always last)

```python
@dataclass
class ResultMessage:
    subtype: str                                # "success" | "error_max_structured_output_retries" | etc.
    duration_ms: int                            # Total time in milliseconds
    duration_api_ms: int                        # API call duration only
    is_error: bool                              # Whether the result is an error
    num_turns: int                              # Number of agent turns executed
    session_id: str                             # Session ID (for resume/fork)
    total_cost_usd: float | None = None         # Cost for entire invocation
    usage: dict[str, Any] | None = None         # Cumulative token counts
    result: str | None = None                   # The final text response
    stop_reason: str | None = None              # "stop", "max_turns", "tool_use", etc.
    structured_output: Any = None               # Validated JSON if output_format was set
    errors: list[dict] | None = None            # Error details (new in v0.1.51)
```

**Usage dictionary keys:**

| Key | Type | Description |
|-----|------|-------------|
| `input_tokens` | `int` | Total input tokens consumed |
| `output_tokens` | `int` | Total output tokens generated |
| `cache_creation_input_tokens` | `int` | Tokens used to create cache entries |
| `cache_read_input_tokens` | `int` | Tokens read from cache |

**In 3XCode Convertor:**

```python
if isinstance(message, ResultMessage):
    result_text = message.result or ""
    cost_usd = getattr(message, "total_cost_usd", 0.0) or 0.0
    duration_ms = getattr(message, "duration_ms", 0) or 0
    num_turns = getattr(message, "num_turns", 0) or 0
    session_id = getattr(message, "session_id", None)
```

This is where we capture **cost and token data** for each phase.

### 11.6 StreamEvent

**When it appears:** If `include_partial_messages=True`, continuously

```python
@dataclass
class StreamEvent:
    uuid: str
    session_id: str
    event: dict[str, Any]                       # Raw Claude API stream event
    parent_tool_use_id: str | None = None
```

Key event types within `event`:
- `content_block_delta` with `delta.type == "text_delta"` for streaming text chunks
- `content_block_delta` with `delta.type == "input_json_delta"` for tool input streaming

**In 3XCode Convertor:** Not used.

### 11.7 RateLimitEvent

**When it appears:** API rate limit warning or rejection

```python
@dataclass
class RateLimitEvent:
    rate_limit_info: RateLimitInfo
    uuid: str
    session_id: str

@dataclass
class RateLimitInfo:
    status: Literal["allowed", "allowed_warning", "rejected"]
    resets_at: int | None = None                        # Unix timestamp
    rate_limit_type: Literal[
        "five_hour", "seven_day", "seven_day_opus",
        "seven_day_sonnet", "overage"
    ] | None = None
    utilization: float | None = None                    # 0.0 to 1.0
    overage_status: Literal["allowed", "allowed_warning", "rejected"] | None = None
    overage_resets_at: int | None = None
    overage_disabled_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)   # Full raw response
```

**Example:**

```python
if isinstance(message, RateLimitEvent):
    info = message.rate_limit_info
    if info.status == "rejected":
        logger.warning("rate_limit_rejected", resets_at=info.resets_at)
        raise RateLimitError(f"Rate limit rejected. Resets at {info.resets_at}")
    elif info.status == "allowed_warning":
        logger.warning("rate_limit_warning", utilization=info.utilization)
```

**In 3XCode Convertor:** Not currently handled, but could be added for bulk processing.

### 11.8 Task Messages (SystemMessage Subtypes)

These appear when subagents or background tasks are running:

```python
# TaskStartedMessage -- task begins
# SystemMessage with subtype containing:
#   task_id: str
#   description: str
#   uuid: str
#   session_id: str
#   tool_use_id: str | None
#   task_type: Literal["local_bash", "local_agent", "remote_agent"] | None

# TaskProgressMessage -- progress update
# SystemMessage with subtype containing:
#   task_id: str
#   description: str
#   usage: TaskUsage  # {total_tokens, tool_uses, duration_ms}
#   uuid: str
#   session_id: str
#   tool_use_id: str | None
#   last_tool_name: str | None

# TaskNotificationMessage -- task completes or fails
# SystemMessage with subtype containing:
#   task_id: str
#   status: Literal["completed", "failed", "stopped"]
#   output_file: str
#   summary: str
#   uuid: str
#   session_id: str
#   tool_use_id: str | None
#   usage: TaskUsage | None
```

---

## 12. Hooks System

Hooks are callbacks invoked at key SDK lifecycle points. They use the `HookMatcher` class for pattern-based matching and receive structured input data.

### 12.1 Hook Events (10 Total)

```python
HookEvent = Literal[
    "PreToolUse",           # Before tool execution
    "PostToolUse",          # After tool execution
    "PostToolUseFailure",   # When tool fails
    "UserPromptSubmit",     # User submits prompt
    "Stop",                 # Execution stops
    "SubagentStop",         # Subagent stops
    "PreCompact",           # Before message compaction
    "Notification",         # Notification events
    "SubagentStart",        # Subagent starts
    "PermissionRequest",    # Permission decision needed
]
```

### 12.2 HookMatcher Class

```python
from claude_agent_sdk import HookMatcher

@dataclass
class HookMatcher:
    matcher: str | None = None    # Tool name or regex pattern (e.g., "Bash", "Write|Edit")
    hooks: list[HookCallback] = []  # List of callback functions
    timeout: float | None = None    # Timeout in seconds (default: 60)
```

### 12.3 Hook Callback Signature

All hook callbacks follow this async signature:

```python
HookCallback = Callable[
    [dict[str, Any], str | None, HookContext],  # input_data, tool_use_id, context
    Awaitable[dict[str, Any]]                    # Return hook output dict
]

async def my_hook(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext,
) -> dict[str, Any]:
    """
    Args:
        input_data: Contains hook_event_name, tool_name, tool_input, etc.
        tool_use_id: The tool use ID (for tool-related hooks).
        context: Hook execution context.

    Returns:
        Dict with optional hookSpecificOutput for the event type.
    """
    return {}
```

### 12.4 Hook Input Fields

All hook inputs include `hook_event_name`. Tool-related hooks add:
- `tool_name` -- Name of the tool
- `tool_input` -- Tool input arguments
- `tool_use_id` -- Tool use identifier
- `agent_id` -- Agent ID (if from subagent, since v0.1.46)
- `agent_type` -- Agent type (if from subagent, since v0.1.46)

PostToolUse adds:
- `tool_response` -- Tool execution result

PostToolUseFailure adds:
- `error` -- Error message
- `is_interrupt` -- Whether it was an interrupt

### 12.5 Hook-Specific Outputs

Each hook event type has specific output fields:

**PreToolUse:**
```python
return {
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow" | "deny" | "ask",
        "permissionDecisionReason": "Optional reason string",
        "updatedInput": {"modified": "input"},      # Optional modified tool input
        "additionalContext": "Extra context for Claude",
    }
}
```

**PostToolUse:**
```python
return {
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": "Context added after tool execution",
        "updatedMCPToolOutput": "Modified MCP tool output",
    }
}
```

**PostToolUseFailure:**
```python
return {
    "hookSpecificOutput": {
        "hookEventName": "PostToolUseFailure",
        "additionalContext": "Error handling context",
    }
}
```

**UserPromptSubmit:**
```python
return {
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": "Context injected with every prompt",
    }
}
```

**SubagentStart / SubagentStop / Notification:**
```python
return {
    "hookSpecificOutput": {
        "hookEventName": "SubagentStop",
        "additionalContext": "...",
    }
}
```

**PermissionRequest:**
```python
return {
    "hookSpecificOutput": {
        "hookEventName": "PermissionRequest",
        "decision": "allow" | "deny",
    }
}
```

### 12.6 Practical Examples

**Protect .env files from modification:**

```python
async def protect_env_files(input_data, tool_use_id, context):
    file_path = input_data.get("tool_input", {}).get("file_path", "")
    if file_path.endswith(".env"):
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "Cannot modify .env files",
            }
        }
    return {}

options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [HookMatcher(matcher="Write|Edit", hooks=[protect_env_files])]
    }
)
```

**Audit logging for file changes:**

```python
from datetime import datetime

async def log_file_change(input_data, tool_use_id, context):
    file_path = input_data.get("tool_input", {}).get("file_path", "unknown")
    with open("./audit.log", "a") as f:
        f.write(f"{datetime.now()}: modified {file_path}\n")
    return {}

options = ClaudeAgentOptions(
    hooks={
        "PostToolUse": [HookMatcher(matcher="Edit|Write", hooks=[log_file_change])]
    }
)
```

**Inject timestamp with every prompt:**

```python
from datetime import datetime

async def add_timestamp(input_data, tool_use_id, context):
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": f"[Timestamp: {datetime.now().isoformat()}]",
        }
    }

options = ClaudeAgentOptions(
    hooks={
        "UserPromptSubmit": [HookMatcher(hooks=[add_timestamp])]
    }
)
```

**Track subagent completion:**

```python
async def subagent_tracker(input_data, tool_use_id, context):
    print(f"[SUBAGENT] Completed: {input_data.get('agent_id')}")
    print(f"  Transcript: {input_data.get('agent_transcript_path')}")
    print(f"  Tool use ID: {tool_use_id}")
    return {}

options = ClaudeAgentOptions(
    hooks={
        "SubagentStop": [HookMatcher(hooks=[subagent_tracker])]
    }
)
```

### 12.7 Multiple Matchers Per Event

```python
options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [
            HookMatcher(matcher="Bash", hooks=[validate_bash_command]),
            HookMatcher(matcher="Write|Edit", hooks=[protect_env_files, log_write]),
            HookMatcher(hooks=[log_all_tools]),  # No matcher = matches all tools
        ]
    }
)
```

### 12.8 Async Hooks

For hooks that need to wait for external operations:

```python
async def slow_validation(input_data, tool_use_id, context):
    # Return async marker -- SDK will poll for result
    return {
        "async": True,
        "asyncTimeout": 30000,  # 30 second timeout in milliseconds
    }
```

### 12.9 Our Approach in 3XCode Convertor

Not used currently (we log at the `invoke_claude()` wrapper level). Future enhancement: add PreToolUse/PostToolUse hooks for DEBUG logging.

---

## 13. Subagent System

Subagents let Claude delegate work to specialized sub-instances. Useful for parallel tasks or switching models mid-session.

### 13.1 AgentDefinition (10 Fields)

```python
from claude_agent_sdk import AgentDefinition

@dataclass
class AgentDefinition:
    description: str                                          # Required -- when to use this agent
    prompt: str                                               # Required -- system prompt/behavior

    # Tool control
    tools: list[str] | None = None                           # Allowed tools (inherits all if None)
    disallowedTools: list[str] | None = None                 # Tools to deny (new in v0.1.51)

    # Model selection
    model: Literal["sonnet", "opus", "haiku", "inherit"] | None = None

    # Capabilities
    skills: list[str] | None = None                          # Available skills (new in v0.1.49)
    memory: Literal["user", "project", "local"] | None = None  # Memory sources (new in v0.1.49)
    mcpServers: list[str | dict[str, Any]] | None = None     # MCP servers (new in v0.1.49)

    # Execution control
    maxTurns: int | None = None                              # Max turns for this agent (new in v0.1.51)
    initialPrompt: str | None = None                         # Initial prompt override (new in v0.1.51)
```

### 13.2 Three Ways to Create Subagents

**1. Programmatic (via `agents` option):**

```python
options = ClaudeAgentOptions(
    allowed_tools=["Agent"],  # Required for subagent invocation
    agents={
        "code_reviewer": AgentDefinition(
            description="Reviews PySpark code for bugs and style",
            prompt="You are a PySpark code reviewer. Check for syntax errors, import completeness, and edge cases.",
            tools=["Read", "Grep"],
            model="opus",
        ),
        "performance_analyzer": AgentDefinition(
            description="Analyzes PySpark performance",
            prompt="Check for shuffle, broadcast, caching opportunities.",
            tools=["Read"],
            model="sonnet",
        ),
    }
)
```

**2. Filesystem-based (`.claude/agents/*.md` files):**

Create markdown files in the project's `.claude/agents/` directory. Each file defines an agent with frontmatter.

**3. Built-in general-purpose agent:**

Always available when `"Agent"` is in `allowed_tools`. Used for ad-hoc delegation.

### 13.3 Key Behaviors

- Subagents get a **fresh context** (no parent conversation history)
- Parent receives subagent's **final message** as tool result
- Subagents **cannot spawn their own subagents** (no `Agent` in subagent tools)
- Multiple subagents can run **concurrently** (parallelization)
- Subagents can be **resumed** with their agent ID
- Messages from subagents include `parent_tool_use_id`
- Tool name: `"Agent"` (renamed from `"Task"` in CLI v2.1.63)

### 13.4 What Subagents Inherit vs Don't Inherit

| Inherits | Does NOT Inherit |
|----------|-----------------|
| Own system prompt + Agent tool prompt | Parent conversation history |
| Project CLAUDE.md (via settingSources) | Parent's system prompt |
| Tool definitions (inherited or subset) | Skills (unless in AgentDefinition.skills) |

### 13.5 Agent Tool Input/Output Schema

```python
# Input (what Claude sends to invoke a subagent)
{
    "description": str,       # 3-5 word task description
    "prompt": str,            # The task to perform
    "subagent_type": str,     # Specialized agent name
}

# Output (what the parent receives back)
{
    "result": str,                    # Final result text
    "usage": dict | None,            # Token usage statistics
    "total_cost_usd": float | None,  # Cost in USD
    "duration_ms": int | None,       # Execution duration
}
```

### 13.6 Capturing Subagent Output

Messages with `parent_tool_use_id` field indicate subagent output:

```python
if hasattr(message, "parent_tool_use_id") and message.parent_tool_use_id:
    print(f"Subagent output: {message.parent_tool_use_id}")
```

### 13.7 Example -- Multi-Agent Code Review

```python
from claude_agent_sdk import ClaudeAgentOptions, AgentDefinition

options = ClaudeAgentOptions(
    allowed_tools=["Read", "Grep", "Glob", "Agent"],
    agents={
        "code-reviewer": AgentDefinition(
            description="Expert code review specialist.",
            prompt="You are a code review specialist. Check for bugs, style issues, and performance problems.",
            tools=["Read", "Grep", "Glob"],
            model="sonnet",
            maxTurns=5,
        ),
        "security-scanner": AgentDefinition(
            description="Scans code for security vulnerabilities.",
            prompt="You are a security specialist. Look for injection, auth issues, and data exposure.",
            tools=["Read", "Grep"],
            model="sonnet",
            disallowedTools=["Bash", "Write"],  # Read-only for safety
        ),
    }
)
```

### 13.8 Our Use Case in 3XCode Convertor

Not used currently. Potential future enhancement:

```python
agents={
    "analyzer": AgentDefinition(
        description="Analyzes SQL",
        model="haiku",  # Cheap analysis
    ),
    "converter": AgentDefinition(
        description="Converts to PySpark",
        model="opus",  # Better code generation
    ),
}
```

---

## 14. Structured Output

JSON Schema structured output enforces Claude's response format. Use when you need guaranteed JSON output.

### 14.1 Basic Example

```python
from pydantic import BaseModel, Field
import json

class AnalysisResult(BaseModel):
    constructs: list[str] = Field(..., description="SQL constructs found")
    convertibility: float = Field(..., description="Percentage convertible", ge=0, le=100)

schema = json.loads(AnalysisResult.model_json_schema())

options = ClaudeAgentOptions(
    output_format={
        "type": "json_schema",
        "schema": schema,
    }
)

async for message in query(prompt=prompt, options=options):
    if isinstance(message, ResultMessage):
        if message.structured_output:
            # Validated JSON matching schema
            data = message.structured_output
            result = AnalysisResult(**data)
        elif message.result:
            # Fallback: parse from text
            data = json.loads(message.result)
```

### 14.2 Error Subtypes

| Subtype | Meaning |
|---------|---------|
| `success` | Valid output generated |
| `error_max_structured_output_retries` | Couldn't produce valid output after retries |

### 14.3 Advantages vs Disadvantages

| Aspect | Structured Output | Prompt-Based Extraction |
|--------|-------------------|------------------------|
| Reliability | Guaranteed JSON | Fallback parser needed |
| Cost | Slight increase | Lower |
| Flexibility | Schema enforced | Any format, extract later |
| Error handling | SDK enforces | Need custom extraction |
| Compatibility | May vary by SDK version | More stable |

### 14.4 Our Approach in 3XCode Convertor

We instruct Claude to return JSON via prompts and use a **fallback extraction function** (`_extract_json()`) because:
1. The SDK's structured output behavior varies between versions
2. Our prompts already ask for JSON explicitly
3. The fallback handles markdown code blocks gracefully

```python
async def invoke_claude_json(
    *,
    prompt: str,
    system_prompt: str | None = None,
    model: str | None = None,
    allowed_tools: list[str] | None = None,
    max_turns: int | None = None,
    timeout_seconds: int | None = None,
    cwd: str | None = None,
) -> tuple[dict, InvocationResult]:
    """Invoke Claude Code and parse the response as JSON.

    Returns:
        Tuple of (parsed JSON dict, InvocationResult with cost data).

    Raises:
        ConverterJSONError: If no valid JSON found in response.
    """
    result = await invoke_claude(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        allowed_tools=allowed_tools,
        max_turns=max_turns,
        timeout_seconds=timeout_seconds,
        cwd=cwd,
    )

    try:
        data = _extract_json(result.text)
    except ValueError as exc:
        raise ConverterJSONError(str(exc)) from exc

    return data, result
```

---

## 15. Extended Thinking

Extended thinking lets Claude reason internally for harder problems. It consumes extra tokens but produces better outputs for complex tasks.

### 15.1 Three Modes

**Disabled (default):**
```python
# No extended thinking, fastest execution
options = ClaudeAgentOptions(thinking={"type": "disabled"})
```

**Adaptive (auto-decide):**
```python
options = ClaudeAgentOptions(
    thinking={"type": "adaptive"}
)
# Claude automatically decides when to think
```

**Enabled with budget:**
```python
options = ClaudeAgentOptions(
    thinking={
        "type": "enabled",
        "budget_tokens": 10000
    }
)
# Claude allocates up to 10k tokens for thinking
```

### 15.2 ThinkingBlock in Messages

When thinking is enabled, `AssistantMessage.content` may include `ThinkingBlock`:

```python
@dataclass
class ThinkingBlock:
    thinking: str      # The thinking content
    signature: str     # Verification signature
```

### 15.3 Effort Level (Related Setting)

The `effort` option controls thinking depth:

```python
options = ClaudeAgentOptions(
    effort="high"  # Implies more thinking/work
)
```

| Effort | Cost Multiplier | Latency | Best For |
|--------|-----------------|---------|----------|
| low | 1x | Fast | Simple tasks |
| medium | 1.5x | Normal | Balanced |
| high | 2x | Slow | Complex SQL, edge cases |
| max | 3x | Very slow | Rare, critical cases |

### 15.4 Deprecated: `max_thinking_tokens`

```python
# DEPRECATED -- use thinking instead:
options = ClaudeAgentOptions(max_thinking_tokens=8192)

# Use this instead:
options = ClaudeAgentOptions(thinking={"type": "enabled", "budget_tokens": 8192})
```

### 15.5 When to Use Extended Thinking

**Good for:**
- Complex multi-CTE SQL scripts with interdependent logic
- Edge case handling (NULL semantics, type coercion)
- Performance optimization analysis

**Not good for:**
- Simple SQL scripts (overkill)
- When latency matters (adds 2-5 seconds)
- When cost is constrained (adds 2-3x tokens)

### 15.6 Our Configuration in 3XCode Convertor

```python
converter_thinking_mode: Literal["disabled", "adaptive", "enabled"] = "disabled"
converter_thinking_budget: int = 10000
converter_effort: Literal["low", "medium", "high"] | None = None
```

Disabled by default. Can be enabled for high-complexity SQL:

```bash
CONVERTER_THINKING_MODE=adaptive python -m sql_to_pyspark my_script.sql
```

---

## 16. Session Management

Sessions allow you to maintain context across multiple invocations. The SDK provides 7 session management functions.

### 16.1 Session Management Functions (7 Total)

```python
from claude_agent_sdk import (
    list_sessions,
    get_session_messages,
    get_session_info,
    rename_session,
    tag_session,
    fork_session,
    delete_session,
)

# List sessions
sessions = list_sessions(
    directory="/path/to/project",   # Optional: project directory
    limit=50,                        # Optional: max results
    include_worktrees=True,          # Optional: include worktree sessions
)

# Get messages from a session
messages = get_session_messages(
    session_id="session-abc123",
    directory="/path/to/project",   # Optional
    limit=100,                       # Optional: max messages
    offset=0,                        # Optional: pagination offset (new in v0.1.51)
)

# Get single session info
info = get_session_info(
    session_id="session-abc123",
    directory="/path/to/project",   # Optional
)

# Rename session
rename_session(
    session_id="session-abc123",
    title="SQL Analysis Run #42",
    directory="/path/to/project",   # Optional
)

# Tag session (with Unicode sanitization)
tag_session(
    session_id="session-abc123",
    tag="production",               # Tag string or None to clear
    directory="/path/to/project",   # Optional
)

# Fork session (new in v0.1.51)
fork_session(
    session_id="session-abc123",
    # Additional params...
)

# Delete session (new in v0.1.51)
delete_session(
    session_id="session-abc123",
    # Additional params...
)
```

### 16.2 SDKSessionInfo Model

```python
@dataclass
class SDKSessionInfo:
    session_id: str
    summary: str
    last_modified: int              # Milliseconds since epoch
    file_size: int | None
    custom_title: str | None
    first_prompt: str | None
    git_branch: str | None
    cwd: str | None
    tag: str | None                 # New in v0.1.50
    created_at: int | None          # Milliseconds since epoch (new in v0.1.50)
```

### 16.3 Capturing Session ID

Every `ResultMessage` contains a `session_id`:

```python
if isinstance(message, ResultMessage):
    session_id = message.session_id
    print(f"Session ID: {session_id}")
```

Or from the init SystemMessage:

```python
if isinstance(message, SystemMessage) and message.subtype == "init":
    session_id = message.data.get("session_id")
```

### 16.4 Resume a Session

Continue from a previous session:

```python
options = ClaudeAgentOptions(resume="session-abc123")

async for message in query(prompt="Continue where we left off", options=options):
    # Messages are added to the previous session
    ...
```

### 16.5 Fork a Session

Branch off without modifying the original:

```python
options = ClaudeAgentOptions(
    resume="session-abc123",
    fork_session=True,  # Creates new session ID, original unchanged
)
```

### 16.6 Continue Most Recent Session

```python
options = ClaudeAgentOptions(continue_conversation=True)
```

### 16.7 Our Approach in 3XCode Convertor

Not used. Our pipeline is stateless:
- Phase 1: fresh invocation, analyzes SQL
- Phase 2: fresh invocation, uses Phase 1's JSON output (not session)
- Phase 3: local validation (no LLM)
- Phase 4: fresh invocation, uses Phase 1-3 outputs

**Future possibility:** If Phase 2 fails, resume from Phase 1's session instead of re-analyzing. This would save cost and time.

---

## 17. Permission System & can_use_tool

The permission system controls which tool calls are allowed, denied, or need user approval.

### 17.1 Permission Modes

```python
PermissionMode = Literal["default", "acceptEdits", "plan", "bypassPermissions", "dontAsk"]
```

| Mode | Behavior |
|------|----------|
| `default` | Requires `can_use_tool` callback or asks user interactively |
| `acceptEdits` | Auto-approves file reads and edits; asks for Bash/Write |
| `plan` | Planning mode, no execution |
| `bypassPermissions` | Runs everything without prompts |
| `dontAsk` | Denies anything not in `allowed_tools` (no prompting, no callback) |

### 17.2 Priority Order

Tool permission checks follow this priority:

1. **`disallowed_tools`** -- Checked FIRST. Always denies. Overrides everything including `bypassPermissions`.
2. **`allowed_tools`** -- Auto-approve these tools without prompting.
3. **`can_use_tool`** callback -- Custom logic for unlisted tools.
4. **`permission_mode`** -- Fallback behavior.

### 17.3 can_use_tool Callback

Custom permission function for fine-grained control:

```python
from claude_agent_sdk import ClaudeAgentOptions

CanUseTool = Callable[
    [str, dict[str, Any], ToolPermissionContext],
    Awaitable[PermissionResult]
]

# PermissionResult is either:
# - PermissionResultAllow (tool call proceeds)
# - PermissionResultDeny (tool call blocked, with reason)
```

**Example -- allow reads but deny writes to /etc:**

```python
async def my_permission_callback(
    tool_name: str,
    tool_input: dict[str, Any],
    context: ToolPermissionContext,
) -> PermissionResult:
    """Custom permission logic."""
    # Allow all reads
    if tool_name in ("Read", "Glob", "Grep"):
        return PermissionResultAllow()

    # Deny writes to /etc
    file_path = tool_input.get("file_path", "")
    if file_path.startswith("/etc"):
        return PermissionResultDeny(reason="Cannot write to /etc")

    # Allow everything else
    return PermissionResultAllow()

options = ClaudeAgentOptions(
    permission_mode="default",
    can_use_tool=my_permission_callback,
)
```

**Example -- require approval for dangerous commands:**

```python
async def bash_safety_check(
    tool_name: str,
    tool_input: dict[str, Any],
    context: ToolPermissionContext,
) -> PermissionResult:
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        dangerous = ["rm -rf", "DROP TABLE", "sudo", "chmod 777"]
        if any(d in command for d in dangerous):
            return PermissionResultDeny(
                reason=f"Dangerous command blocked: {command[:50]}"
            )
    return PermissionResultAllow()

options = ClaudeAgentOptions(
    can_use_tool=bash_safety_check,
)
```

### 17.4 PermissionUpdate (Dynamic)

Permission rules can be updated dynamically:

```python
@dataclass
class PermissionUpdate:
    type: Literal[
        "addRules", "replaceRules", "removeRules",
        "setMode", "addDirectories", "removeDirectories"
    ]
    rules: list[PermissionRuleValue] | None = None
    behavior: Literal["allow", "deny", "ask"] | None = None
    mode: PermissionMode | None = None
    directories: list[str] | None = None
    destination: Literal[
        "userSettings", "projectSettings", "localSettings", "session"
    ] | None = None
```

### 17.5 Dynamic Permission Mode (ClaudeSDKClient)

```python
async with ClaudeSDKClient(options=options) as client:
    # Start with restrictive mode
    await client.set_permission_mode("default")

    # After validation, relax permissions
    await client.set_permission_mode("acceptEdits")
```

### 17.6 Our Approach in 3XCode Convertor

We use `bypassPermissions` because our pipeline is non-interactive and we trust the prompts:

```python
options = ClaudeAgentOptions(
    permission_mode="bypassPermissions"
)
```

For production deployments with higher security requirements, `dontAsk` with explicit `allowed_tools` would be safer:

```python
options = ClaudeAgentOptions(
    permission_mode="dontAsk",
    allowed_tools=["Read", "Glob", "Grep"],  # Only these are allowed
)
```

---

## 18. Plugin System

Plugins extend the SDK's capabilities with custom functionality loaded from local paths.

### 18.1 Plugin Configuration

```python
from claude_agent_sdk import ClaudeAgentOptions, SdkPluginConfig

options = ClaudeAgentOptions(
    plugins=[
        SdkPluginConfig(type="local", path="/path/to/my-plugin"),
    ]
)
```

### 18.2 SdkPluginConfig

```python
class SdkPluginConfig(TypedDict):
    type: Literal["local"]     # Currently only "local" is supported
    path: str                  # Absolute path to plugin directory
```

### 18.3 Plugin Discovery via Claude Code

Claude Code supports plugins through:
- **Programmatic**: `plugins` option in `ClaudeAgentOptions`
- **Settings file**: Configured in `settings.json`

### 18.4 Related: Claude Code Features (via setting_sources)

When `setting_sources` includes `"project"`, the SDK loads:

| Feature | Location |
|---------|----------|
| Skills | `.claude/skills/*/SKILL.md` |
| Slash commands | `.claude/commands/*.md` |
| Memory | `CLAUDE.md` / `.claude/CLAUDE.md` |
| Agent definitions | `.claude/agents/*.md` |

### 18.5 Our Approach in 3XCode Convertor

Not used. We don't need custom plugins for our batch conversion pipeline.

---

## 19. Cost Tracking

This is critical for batch processing. Every invocation's cost is tracked and can be capped.

### 19.1 Per-Invocation Cost

From `ResultMessage`:

```python
if isinstance(message, ResultMessage):
    cost_usd = message.total_cost_usd  # float, e.g., 0.0234
    print(f"Cost: ${cost_usd:.4f}")
```

### 19.2 Token Counts

From `AssistantMessage` and `ResultMessage.usage`:

```python
# Track tokens across all messages
input_tokens = 0
output_tokens = 0
cache_read_tokens = 0
cache_creation_tokens = 0

async for message in query(prompt=prompt, options=options):
    if isinstance(message, AssistantMessage):
        usage = message.usage
        if usage:
            input_tokens += usage.get("input_tokens", 0)
            output_tokens += usage.get("output_tokens", 0)
            cache_read_tokens += usage.get("cache_read_input_tokens", 0)
            cache_creation_tokens += usage.get("cache_creation_input_tokens", 0)
```

### 19.3 Per-Turn Usage (since v0.1.49)

Each `AssistantMessage` now includes its own `usage` dict, enabling per-turn cost tracking:

```python
if isinstance(message, AssistantMessage) and message.usage:
    turn_input = message.usage.get("input_tokens", 0)
    turn_output = message.usage.get("output_tokens", 0)
    logger.debug("turn_usage", input=turn_input, output=turn_output)
```

### 19.4 Task-Level Usage

For subagent tasks, `TaskProgressMessage` includes `TaskUsage`:

```python
# TaskUsage contains:
#   total_tokens: int
#   tool_uses: int
#   duration_ms: int
```

### 19.5 Prompt Caching

The SDK automatically caches repeated prompts (if same system prompt, same initial messages). Cached reads cost 10% of cache-write cost.

```
First call:
  input_tokens: 1000 -> cache_creation_input_tokens: 1000

Second call (same prompt):
  input_tokens: 100 (10% of 1000) -> cache_read_input_tokens: 100

Savings: 900 tokens per reuse
```

### 19.6 Cost Cap (max_budget_usd)

Hard limit per invocation:

```python
options = ClaudeAgentOptions(
    max_budget_usd=2.5  # Stop if this invocation would exceed $2.50
)
```

If exceeded, SDK raises an error. Good for safety in batch jobs.

### 19.7 Our Cost Tracking in 3XCode Convertor

**InvocationResult model:**

```python
class InvocationResult(BaseModel):
    """Result from a single Claude Agent SDK invocation with cost/usage tracking."""

    text: str = Field(description="The text content of Claude's final response")
    cost_usd: float = Field(default=0.0, description="Total cost in USD for this invocation")
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    duration_ms: int = 0
    num_turns: int = 0
    session_id: str | None = None
```

**Accumulation in orchestrator:**

```python
# Cost accumulation
total_cost = 0.0
phase_costs: dict[str, float] = {}

# Phase 1
phase_costs["analysis"] = phase1_result.cost_usd
total_cost += phase1_result.cost_usd

# Phase 2
phase_costs["conversion"] = phase2_result.cost_usd
total_cost += phase2_result.cost_usd

# Phase 4
phase_costs["audit"] = phase4_result.cost_usd
total_cost += phase4_result.cost_usd

# Final report
audit = AuditReport(
    ...
    total_cost_usd=total_cost,
    phase_costs=phase_costs,
)
```

**Logging:**

```python
if settings.cost_tracking_enabled:
    logger.info(
        "claude_result",
        model=model,
        cost_usd=f"${cost_usd:.4f}",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read=cache_read_tokens,
        duration_ms=duration_ms,
        turns=num_turns,
    )
```

---

## 20. Rate Limiting

The Claude API enforces rate limits. The SDK surfaces these as `RateLimitEvent` messages.

### 20.1 Rate Limit Types

| Type | Limit | Duration |
|------|-------|----------|
| `five_hour` | Per-org limit | 5 hours |
| `seven_day` | Per-org limit | 7 days |
| `seven_day_opus` | Opus-specific | 7 days |
| `seven_day_sonnet` | Sonnet-specific | 7 days |
| `overage` | Overage pricing | Varies |

### 20.2 RateLimitEvent Fields

```python
if isinstance(message, RateLimitEvent):
    info = message.rate_limit_info
    status = info.status              # "allowed" | "allowed_warning" | "rejected"
    utilization = info.utilization    # 0.0 to 1.0
    resets_at = info.resets_at        # Unix timestamp
    rate_limit_type = info.rate_limit_type  # e.g. "five_hour"

    # Overage-specific fields
    overage_status = info.overage_status
    overage_resets_at = info.overage_resets_at
    overage_disabled_reason = info.overage_disabled_reason
```

### 20.3 Handling Rate Limits

**Option 1: Soft limit (warning only)**
```python
if info.status == "allowed_warning":
    logger.warning("Rate limit warning", utilization=info.utilization)
    # Continue processing, but add delays
```

**Option 2: Hard limit (stop and wait)**
```python
if info.status == "rejected":
    logger.error("Rate limit rejected", resets_at=info.resets_at)
    import time
    wait_seconds = info.resets_at - time.time()
    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)
    # Retry
```

### 20.4 Our Approach in 3XCode Convertor

Not currently handled (small batch sizes stay under limits). For bulk processing (100+ files), add:

```python
import asyncio

async def convert_sql_batch(sql_files: list[Path], output_dir: Path) -> None:
    """Convert multiple files with rate limit handling."""
    for i, sql_file in enumerate(sql_files):
        if i > 0:
            # Add 2-second delay between invocations to pace requests
            await asyncio.sleep(2.0)

        try:
            await convert_sql_file(sql_file, output_dir)
        except RateLimitError as exc:
            logger.error("Rate limit hit", resets_at=exc.resets_at)
            await asyncio.sleep(60)  # Wait 1 minute before retry
            await convert_sql_file(sql_file, output_dir)
```

---

## 21. Streaming

Enable `include_partial_messages=True` to receive `StreamEvent` messages as Claude thinks.

### 21.1 Basic Streaming Example

```python
from claude_agent_sdk import query, ClaudeAgentOptions, StreamEvent, AssistantMessage, ResultMessage

options = ClaudeAgentOptions(include_partial_messages=True)

async for message in query(prompt="Explain databases", options=options):
    if isinstance(message, StreamEvent):
        event = message.event
        if event.get("type") == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                print(delta.get("text", ""), end="", flush=True)
    elif isinstance(message, ResultMessage):
        print(f"\n\nDone. Cost: ${message.total_cost_usd:.4f}")
```

### 21.2 Streaming with ClaudeSDKClient

```python
async with ClaudeSDKClient(options=options) as client:
    await client.query("Generate a report")
    async for message in client.receive_response():
        process(message)

    # receive_messages() gets ALL messages including between queries
    async for message in client.receive_messages():
        process(message)
```

### 21.3 Streaming Input

The prompt can be an async iterable for large inputs:

```python
async def stream_large_sql():
    """Stream a large SQL file chunk by chunk."""
    with open("huge_query.sql") as f:
        for chunk in iter(lambda: f.read(4096), ""):
            yield {"type": "text", "text": chunk}

async for message in query(prompt=stream_large_sql(), options=options):
    process(message)
```

### 21.4 When to Use

- Interactive web apps with user feedback
- Long-running conversions where users need progress visibility
- Debugging (see Claude's reasoning in real-time)

### 21.5 Our Approach in 3XCode Convertor

Not used. We're a batch pipeline with no interactive UI. The user isn't waiting for real-time feedback; they submit a file and check results later.

---

## 22. Error Handling

The SDK raises specific error types. Handle each to provide meaningful feedback.

### 22.1 SDK Error Types

```python
from claude_agent_sdk import (
    ClaudeSDKError,       # Base error class
    CLINotFoundError,     # Claude Code CLI not installed (has cli_path attribute)
    CLIConnectionError,   # Connection issues
    ProcessError,         # Process failed (has exit_code, stderr attributes)
    CLIJSONDecodeError,   # JSON parsing issues (has line, original_error attributes)
)
```

### 22.2 Error Hierarchy

```
ClaudeSDKError (base)
  |-- CLIConnectionError
  |     |-- CLINotFoundError
  |-- ProcessError
  |-- CLIJSONDecodeError
```

### 22.3 AssistantMessage Error Types

When an `AssistantMessage` has the `error` field set:

```python
AssistantMessageError = Literal[
    "authentication_failed",
    "billing_error",
    "rate_limit",
    "invalid_request",
    "server_error",
    "max_output_tokens",
    "unknown",
]
```

### 22.4 ResultMessage Error Subtypes

```python
# Common subtypes:
"success"                              # Normal completion
"error_max_structured_output_retries"  # Structured output validation failed
"error_max_turns"                      # Hit max_turns limit
"error_budget"                         # Hit max_budget_usd limit
```

### 22.5 Our Error Handling in 3XCode Convertor

In `sql_to_pyspark/claude_runner.py`:

```python
try:
    await asyncio.wait_for(_run(), timeout=timeout_seconds)
except TimeoutError:
    logger.error("claude_timeout", timeout=timeout_seconds, model=model)
    msg = f"Claude Agent SDK timed out after {timeout_seconds}s"
    raise ConverterTimeoutError(msg) from None
except CLINotFoundError as exc:
    msg = "Claude Code CLI not found. Install: curl -fsSL https://claude.ai/install.sh | bash"
    logger.error("cli_not_found")
    raise ConverterSDKError(msg) from exc
except CLIConnectionError as exc:
    msg = f"Cannot connect to Claude Code CLI: {exc}"
    logger.error("cli_connection_error", error=str(exc))
    raise ConverterSDKError(msg) from exc
except ProcessError as exc:
    exit_code = getattr(exc, "exit_code", "unknown")
    stderr = getattr(exc, "stderr", str(exc))
    msg = f"Claude process failed (exit {exit_code}): {stderr}"
    logger.error("process_error", exit_code=exit_code)
    raise ConverterSDKError(msg) from exc
except CLIJSONDecodeError as exc:
    line = getattr(exc, "line", "unknown")
    msg = f"Failed to parse CLI response at line {line}"
    logger.error("json_decode_error", line=line)
    raise ConverterSDKError(msg) from exc
except ClaudeSDKError as exc:
    msg = f"Claude Agent SDK error: {exc}"
    logger.error("sdk_error", error=str(exc))
    raise ConverterSDKError(msg) from exc
```

Custom exceptions in `sql_to_pyspark/exceptions.py`:

```python
class ConverterError(Exception):
    """Base exception for all converter pipeline errors."""

class ConverterTimeoutError(ConverterError):
    """Claude SDK invocation exceeded the configured timeout."""

class ConverterSDKError(ConverterError):
    """Claude Agent SDK returned an error (connection, process, parse)."""

class ConverterJSONError(ConverterError):
    """Failed to extract valid JSON from Claude response."""
```

---

## 23. Transport Layer

The SDK uses a transport abstraction to communicate with the Claude Code CLI.

### 23.1 Transport Abstract Base Class

```python
from abc import ABC

class Transport(ABC):
    async def connect(self) -> None: ...
    async def write(self, data: str) -> None: ...
    def read_messages(self) -> AsyncIterator[dict[str, Any]]: ...
    async def close(self) -> None: ...
    def is_ready(self) -> bool: ...
    async def end_input(self) -> None: ...
```

### 23.2 Default: SubprocessCLITransport

The SDK spawns a CLI subprocess and communicates via JSON lines (newline-delimited JSON):

```
INPUT:  {"type": "invoke", "prompt": "...", "options": {...}}
OUTPUT: {"type": "assistant", "content": [...]}
OUTPUT: {"type": "result", "result": "...", "cost": 0.05}
```

### 23.3 Custom Transport

Both `query()` and `ClaudeSDKClient` accept an optional `transport` parameter:

```python
from claude_agent_sdk.transport import Transport

class MockTransport(Transport):
    """Mock transport for testing."""
    async def connect(self) -> None:
        pass

    async def write(self, data: str) -> None:
        self._input = data

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "result", "result": "mock response"}

    async def close(self) -> None:
        pass

    def is_ready(self) -> bool:
        return True

    async def end_input(self) -> None:
        pass

# Use with query()
async for msg in query(prompt="test", transport=MockTransport()):
    print(msg)

# Use with ClaudeSDKClient
client = ClaudeSDKClient(options=options, transport=MockTransport())
```

### 23.4 Important Note

The transport API is implementation detail and may change between versions. The default subprocess transport works out-of-the-box and is recommended for production use.

---

## 24. Our Implementation Patterns

These are the patterns we use throughout the 3XCode Convertor to leverage the SDK effectively.

### 24.1 The `invoke_claude()` Wrapper

We wrap the raw `query()` API in a helper function for:
- **Timeout handling** -- asyncio.wait_for()
- **Cost capture** -- Extract cost from ResultMessage
- **Error handling** -- Catch SDK errors and wrap in ConverterError
- **Settings integration** -- Use CONVERTER_MODEL, CONVERTER_MAX_TURNS, etc.
- **Type safety** -- Return InvocationResult Pydantic model

Location: `/Users/abhisheksharma/Documents/Genaiprotos/Developer/3XDE/3XCodeConvertor/sql_to_pyspark/claude_runner.py`

```python
async def invoke_claude(
    *,
    prompt: str,
    system_prompt: str | None = None,
    model: str | None = None,
    allowed_tools: list[str] | None = None,
    max_turns: int | None = None,
    timeout_seconds: int | None = None,
    cwd: str | None = None,
) -> InvocationResult:
    """Wrapper around query() with error handling, timeout, and cost tracking."""
    # ... implementation
```

### 24.2 System Prompt + User Prompt Separation

Each phase has **separate system and user prompts**:

- **System prompt:** Instructions for Claude (fixed per phase)
- **User prompt:** The actual task + context (varies per file/phase)

Location: `/Users/abhisheksharma/Documents/Genaiprotos/Developer/3XDE/3XCodeConvertor/sql_to_pyspark/prompts.py`

```python
def build_analysis_prompt(sql_content: str, file_name: str) -> tuple[str, str]:
    """Build system + user prompts for Phase 1 (SQL Analysis)."""
    system_prompt = """You are an expert SQL analyst...
    (500 lines of instructions)
    """

    user_prompt = f"""Analyze this SQL script:

    File: {file_name}

    ```sql
    {sql_content}
    ```"""

    return system_prompt, user_prompt
```

**Benefits:**
- Reusable system prompts across files
- Clear separation of role/instructions vs. task
- Easier to test and iterate on prompts

### 24.3 Knowledge Base Embedding

Instead of RAG (retrieval-augmented generation), we embed knowledge directly in system prompts:

```python
def _load_knowledge(filename: str) -> str:
    """Load a knowledge base file from knowledge/ directory."""
    path = _KNOWLEDGE_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""

# In system prompt:
mapping_ref = _load_knowledge("sql_to_pyspark_mapping.md")
system_prompt = f"""
...
<mapping_reference>
{mapping_ref}
</mapping_reference>
...
"""
```

**Advantages:**
- Deterministic (no retrieval variability)
- No vector DB needed
- Easy to version control and review
- Faster (no retrieval latency)

**Knowledge files embedded:**
- `sql_to_pyspark_mapping.md` -- 70+ construct mappings
- `pyspark_idioms.md` -- Style guide
- `known_limitations.md` -- What can't auto-convert
- `critical_gotchas.md` -- Top 10 silent-failure risks
- `few_shot_examples.md` -- 3 concrete before/after examples

### 24.4 Per-Phase Tool Restriction

Each phase gets only the tools it needs:

| Phase | Tools | Why |
|-------|-------|-----|
| 1 (Analyze) | [Read, Glob, Grep] | Explore SQL files, search patterns |
| 2 (Convert) | [Read] | Access knowledge base for reference |
| 3 (Validate) | (none -- local Python) | No LLM |
| 4 (Audit) | [] | Pure generation, no tool use |

**Benefits:**
- Reduced cost (fewer tool calls)
- Faster execution (no tool overhead)
- Safer (only allow necessary operations)
- Better behavior (Claude stays focused)

### 24.5 InvocationResult Pattern

Wrap SDK messages in a Pydantic model for type safety:

```python
class InvocationResult(BaseModel):
    """Result from a single Claude Agent SDK invocation with cost/usage tracking."""

    text: str
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    duration_ms: int = 0
    num_turns: int = 0
    session_id: str | None = None
```

**Benefits:**
- Type-safe cost tracking
- Easy to log and inspect
- Integrates with Pydantic validation

### 24.6 JSON Extraction with Fallback

Claude often returns JSON wrapped in markdown code blocks. We extract it with a fallback parser:

```python
def _extract_json(text: str) -> dict:
    """Extract the first JSON object from a text response.

    Handles:
      - Pure JSON response
      - JSON wrapped in ```json ... ``` code blocks
      - JSON embedded in prose text
    """
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from ```json code block
    if "```json" in text:
        start = text.index("```json") + len("```json")
        end = text.index("```", start)
        return json.loads(text[start:end].strip())

    # Try extracting from generic ``` code block
    if "```" in text:
        start = text.index("```") + len("```")
        end = text.index("```", start)
        candidate = text[start:end].strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Try to find first { ... } balanced block
    brace_start = text.find("{")
    if brace_start != -1:
        depth = 0
        for i in range(brace_start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[brace_start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break

    raise ValueError("No valid JSON object found in Claude response")
```

### 24.7 Graceful Degradation

Phase 4 (audit report generation) has a template fallback:

```python
try:
    audit_system, audit_user = build_audit_prompt(...)
    phase4_result = await invoke_claude(...)
    audit_markdown = phase4_result.text
except Exception:
    logger.warning("phase4_llm_fallback", reason="LLM failed, using template")
    audit_markdown = ""  # Generate from template below

# Use template if LLM failed or returned empty
if not audit_markdown.strip():
    audit_markdown = generate_audit_markdown(audit)
```

**Benefits:**
- Pipeline completes even if LLM fails
- User still gets a usable output
- Cost-efficient (template is free)

---

## 25. Future Enhancements

Here are planned improvements to leverage the SDK more fully:

### 1. Custom MCP Tool: PySpark AST Validator

Create a tool Claude can invoke to validate PySpark code:

```python
@tool(
    name="validate_pyspark_code",
    description="Validate PySpark Python code syntax and PySpark API usage",
    input_schema={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python code to validate"},
        },
        "required": ["code"],
    },
)
async def validate_pyspark_code(args: dict[str, Any]) -> dict[str, Any]:
    """Validate using ast.parse() and PySpark API checker."""
    from sql_to_pyspark.validator import validate_pyspark_code
    result = validate_pyspark_code(args["code"])
    return {"content": [{"type": "text", "text": result.model_dump_json()}]}
```

**Usage:** Phase 2 could invoke this to validate generated code mid-generation.

### 2. Subagents for Model Selection

Different models per phase:

```python
agents={
    "analyzer": AgentDefinition(
        description="Analyzes SQL",
        model="haiku",  # Fast and cheap
    ),
    "converter": AgentDefinition(
        description="Converts to PySpark",
        model="opus",  # Best code generation
    ),
}
```

**Benefit:** Haiku for cheap analysis, Opus for high-quality conversion.

### 3. Extended Thinking for Complex SQL

Enable for multi-CTE scripts:

```bash
CONVERTER_THINKING_MODE=adaptive python -m sql_to_pyspark complex_script.sql
```

### 4. Session Resume on Phase 2 Failure

Avoid re-analyzing on conversion failure:

```python
# Phase 1 stores session_id
phase1_result = await invoke_claude_json(...)
session_id = phase1_result.session_id

# Phase 2 resumes from Phase 1's session
options = ClaudeAgentOptions(resume=session_id)
phase2_result = await invoke_claude_json(..., options=options)
```

### 5. Streaming for Web Frontend

Enable progress updates for real-time UI:

```python
options = ClaudeAgentOptions(include_partial_messages=True)

async for message in query(prompt=prompt, options=options):
    if isinstance(message, StreamEvent):
        # Send to WebSocket client
        event = message.event
        if event.get("type") == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                await websocket.send_json({
                    "type": "progress",
                    "text": delta.get("text", ""),
                })
```

### 6. Rate Limit Handling for Bulk Processing

Automatic delays for 100+ file batches:

```python
async def convert_sql_batch(files: list[Path]) -> None:
    for i, file in enumerate(files):
        if i > 0:
            await asyncio.sleep(2.0)  # 2 sec between files
        await convert_sql_file(file, ...)
```

### 7. Hooks for Structured Logging

Log all tool invocations:

```python
async def on_tool_use(input_data, tool_use_id, context):
    logger.debug(
        "tool_invoked",
        tool=input_data.get("tool_name"),
        input_size=len(str(input_data.get("tool_input", {}))),
    )
    return {}

options = ClaudeAgentOptions(
    hooks={"PreToolUse": [HookMatcher(hooks=[on_tool_use])]}
)
```

### 8. File Checkpointing for Rollback

Rewind file changes on bad conversions:

```python
options = ClaudeAgentOptions(enable_file_checkpointing=True)

async with ClaudeSDKClient(options=options) as client:
    await client.query("Generate PySpark code")
    checkpoint_id = None
    async for message in client.receive_response():
        if isinstance(message, UserMessage) and message.uuid:
            checkpoint_id = message.uuid

    # Later, if conversion failed:
    if checkpoint_id:
        await client.rewind_files(checkpoint_id)
```

### 9. can_use_tool for Fine-Grained Permissions

Replace `bypassPermissions` with explicit per-tool logic:

```python
async def converter_permissions(tool_name, tool_input, context):
    allowed = {"Read", "Glob", "Grep"}
    if tool_name in allowed:
        return PermissionResultAllow()
    return PermissionResultDeny(reason=f"Tool {tool_name} not allowed in converter")

options = ClaudeAgentOptions(
    permission_mode="default",
    can_use_tool=converter_permissions,
)
```

### 10. Fallback Model for Resilience

```python
options = ClaudeAgentOptions(
    model="opus",
    fallback_model="sonnet",  # Use sonnet if opus is rate-limited
)
```

---

## 26. Quick Reference Card

### Environment Variables

| Variable | Type | Default | Used In | Description |
|----------|------|---------|---------|-------------|
| `ANTHROPIC_API_KEY` | str | (required) | SDK | Anthropic API key for direct auth |
| `CLAUDE_CODE_USE_BEDROCK` | str | - | SDK | Set to `1` for AWS Bedrock |
| `CLAUDE_CODE_USE_VERTEX` | str | - | SDK | Set to `1` for Google Vertex AI |
| `CLAUDE_CODE_USE_FOUNDRY` | str | - | SDK | Set to `1` for Azure AI Foundry |
| `CONVERTER_MODEL` | str | `"sonnet"` | invoke_claude | Claude model alias |
| `CONVERTER_TIMEOUT` | int | `600` | invoke_claude | Timeout in seconds per invocation |
| `CONVERTER_MAX_TURNS` | int | `3` | invoke_claude | Max agent turns per invocation |
| `CONVERTER_PERMISSION_MODE` | str | `"bypassPermissions"` | invoke_claude | SDK permission mode |
| `COST_TRACKING_ENABLED` | bool | `True` | invoke_claude | Enable cost logging |
| `MAX_BUDGET_USD` | float | `5.0` | invoke_claude | Cost cap per invocation |
| `CONVERTER_THINKING_MODE` | str | `"disabled"` | invoke_claude | Extended thinking mode |
| `CONVERTER_THINKING_BUDGET` | int | `10000` | invoke_claude | Thinking token budget |
| `CONVERTER_EFFORT` | str | `None` | invoke_claude | Effort level (low/medium/high/max) |

### Model IDs

| Alias | Full Model ID | Use Case |
|-------|---------------|----------|
| `haiku` | `claude-haiku-4-5-20251001` | Fast, cheap analysis |
| `sonnet` | `claude-sonnet-4-6` | Balanced quality + speed |
| `opus` | `claude-opus-4-6` | Maximum quality |

### All 17 Built-in Tools

| # | Tool | Category | Description |
|---|------|----------|-------------|
| 1 | Read | Core | Read files and images |
| 2 | Write | Core | Create or overwrite files |
| 3 | Edit | Core | Replace text in files |
| 4 | Bash | Core | Execute shell commands |
| 5 | Glob | Core | Find files by pattern |
| 6 | Grep | Core | Search file contents |
| 7 | NotebookEdit | Core | Edit Jupyter notebooks |
| 8 | Agent | Extended | Spawn subagents |
| 9 | AskUserQuestion | Extended | Get user input |
| 10 | WebSearch | Extended | Search the web |
| 11 | WebFetch | Extended | Fetch web content |
| 12 | TodoWrite | Extended | Manage todo lists |
| 13 | BashOutput | Extended | Get background bash output |
| 14 | KillBash | Extended | Kill background shells |
| 15 | ExitPlanMode | Extended | Exit plan mode |
| 16 | ListMcpResources | Extended | List MCP resources |
| 17 | ReadMcpResource | Extended | Read MCP resources |

### All 37 ClaudeAgentOptions Parameters

| # | Parameter | Type | Default |
|---|-----------|------|---------|
| 1 | `tools` | `list[str] \| ToolsPreset \| None` | `None` |
| 2 | `allowed_tools` | `list[str]` | `[]` |
| 3 | `disallowed_tools` | `list[str]` | `[]` |
| 4 | `system_prompt` | `str \| SystemPromptPreset \| None` | `None` |
| 5 | `mcp_servers` | `dict \| str \| Path` | `{}` |
| 6 | `permission_mode` | `PermissionMode \| None` | `None` |
| 7 | `continue_conversation` | `bool` | `False` |
| 8 | `resume` | `str \| None` | `None` |
| 9 | `fork_session` | `bool` | `False` |
| 10 | `max_turns` | `int \| None` | `None` |
| 11 | `max_budget_usd` | `float \| None` | `None` |
| 12 | `model` | `str \| None` | `None` |
| 13 | `fallback_model` | `str \| None` | `None` |
| 14 | `betas` | `list[SdkBeta]` | `[]` |
| 15 | `output_format` | `dict \| None` | `None` |
| 16 | `permission_prompt_tool_name` | `str \| None` | `None` |
| 17 | `cwd` | `str \| Path \| None` | `None` |
| 18 | `cli_path` | `str \| Path \| None` | `None` |
| 19 | `settings` | `str \| None` | `None` |
| 20 | `add_dirs` | `list[str \| Path]` | `[]` |
| 21 | `env` | `dict[str, str]` | `{}` |
| 22 | `extra_args` | `dict[str, str \| None]` | `{}` |
| 23 | `max_buffer_size` | `int \| None` | `None` |
| 24 | `stderr` | `Callable \| None` | `None` |
| 25 | `debug_stderr` | `Any` | `sys.stderr` (DEPRECATED) |
| 26 | `can_use_tool` | `CanUseTool \| None` | `None` |
| 27 | `hooks` | `dict[HookEvent, list[HookMatcher]] \| None` | `None` |
| 28 | `user` | `str \| None` | `None` |
| 29 | `include_partial_messages` | `bool` | `False` |
| 30 | `agents` | `dict[str, AgentDefinition] \| None` | `None` |
| 31 | `setting_sources` | `list[SettingSource] \| None` | `None` |
| 32 | `sandbox` | `SandboxSettings \| None` | `None` |
| 33 | `plugins` | `list[SdkPluginConfig]` | `[]` |
| 34 | `thinking` | `ThinkingConfig \| None` | `None` |
| 35 | `max_thinking_tokens` | `int \| None` | `None` (DEPRECATED) |
| 36 | `effort` | `Literal["low","medium","high","max"] \| None` | `None` |
| 37 | `enable_file_checkpointing` | `bool` | `False` |

### All Message Types

| Type | Final? | Key Fields |
|------|--------|------------|
| `SystemMessage` | No | `subtype`, `data` |
| `UserMessage` | No | `content`, `uuid`, `parent_tool_use_id` |
| `AssistantMessage` | No | `content`, `model`, `usage`, `error` |
| `StreamEvent` | No | `uuid`, `session_id`, `event` |
| `RateLimitEvent` | No | `rate_limit_info` (with `status`, `utilization`, `resets_at`) |
| `ResultMessage` | Yes | `result`, `total_cost_usd`, `usage`, `duration_ms`, `session_id`, `is_error` |

### All 10 Hook Events

| Event | Matcher? | Key Output Fields |
|-------|----------|-------------------|
| `PreToolUse` | Yes (tool name regex) | `permissionDecision`, `updatedInput`, `additionalContext` |
| `PostToolUse` | Yes | `additionalContext`, `updatedMCPToolOutput` |
| `PostToolUseFailure` | Yes | `additionalContext` |
| `UserPromptSubmit` | No | `additionalContext` |
| `Stop` | No | - |
| `SubagentStop` | No | `additionalContext` |
| `SubagentStart` | No | `additionalContext` |
| `PreCompact` | No | - |
| `Notification` | No | `additionalContext` |
| `PermissionRequest` | No | `decision` |

### AgentDefinition (10 Fields)

| Field | Type | Required | Since |
|-------|------|----------|-------|
| `description` | `str` | Yes | v0.1.0 |
| `prompt` | `str` | Yes | v0.1.0 |
| `tools` | `list[str] \| None` | No | v0.1.0 |
| `model` | `"sonnet" \| "opus" \| "haiku" \| "inherit"` | No | v0.1.0 |
| `skills` | `list[str] \| None` | No | v0.1.49 |
| `memory` | `"user" \| "project" \| "local"` | No | v0.1.49 |
| `mcpServers` | `list[str \| dict] \| None` | No | v0.1.49 |
| `disallowedTools` | `list[str] \| None` | No | v0.1.51 |
| `maxTurns` | `int \| None` | No | v0.1.51 |
| `initialPrompt` | `str \| None` | No | v0.1.51 |

### Session Management (7 Functions)

| Function | Since | Description |
|----------|-------|-------------|
| `list_sessions()` | v0.1.46 | List past sessions |
| `get_session_messages()` | v0.1.46 | Get messages from session |
| `get_session_info()` | v0.1.50 | Get single session info |
| `rename_session()` | v0.1.49 | Rename a session |
| `tag_session()` | v0.1.49 | Tag a session |
| `fork_session()` | v0.1.51 | Fork a session |
| `delete_session()` | v0.1.51 | Delete a session |

### 4 MCP Transport Types

| Type | Config Key | Use Case |
|------|-----------|----------|
| `stdio` | `command`, `args`, `env` | Local subprocess servers |
| `sse` | `url`, `headers` | HTTP with Server-Sent Events |
| `http` | `url`, `headers` | Standard HTTP servers |
| `sdk` | `name`, `instance` | In-process Python (no IPC) |

### 5 Permission Modes

| Mode | Behavior |
|------|----------|
| `default` | Requires `can_use_tool` or interactive approval |
| `acceptEdits` | Auto-approve file operations |
| `plan` | Planning only, no execution |
| `bypassPermissions` | Auto-approve everything |
| `dontAsk` | Deny anything not in `allowed_tools` |

### Common Code Patterns

**Basic invocation:**
```python
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

options = ClaudeAgentOptions(model="sonnet")
async for message in query(prompt="Your prompt", options=options):
    if isinstance(message, ResultMessage):
        print(f"Result: {message.result}")
        print(f"Cost: ${message.total_cost_usd:.4f}")
```

**Our wrapper:**
```python
from sql_to_pyspark.claude_runner import invoke_claude

result = await invoke_claude(
    prompt="Analyze this SQL",
    system_prompt="You are a SQL expert",
    model="sonnet",
    allowed_tools=["Read", "Glob", "Grep"],
    max_turns=3,
)
print(f"Result: {result.text}")
print(f"Cost: ${result.cost_usd:.4f}")
```

**JSON extraction:**
```python
from sql_to_pyspark.claude_runner import invoke_claude_json

data, result = await invoke_claude_json(
    prompt="Return analysis as JSON",
    system_prompt="Return valid JSON only",
)
print(f"Parsed: {data}")
print(f"Cost: ${result.cost_usd:.4f}")
```

**Error handling:**
```python
from sql_to_pyspark.claude_runner import invoke_claude
from sql_to_pyspark.exceptions import ConverterTimeoutError, ConverterSDKError

try:
    result = await invoke_claude(...)
except ConverterTimeoutError:
    logger.error("Timeout exceeded")
except ConverterSDKError as exc:
    logger.error(f"SDK error: {exc}")
```

### Release History (Recent)

| Version | Date | CLI | Key Changes |
|---------|------|-----|-------------|
| 0.1.51 | Mar 27 | 2.1.85 | fork/delete session, task_budget, dontAsk mode, AgentDefinition: disallowedTools/maxTurns/initialPrompt |
| 0.1.50 | Mar 20 | 2.1.81 | get_session_info(), tag/created_at on SDKSessionInfo |
| 0.1.49 | Mar 17 | 2.1.77 | AgentDefinition: skills/memory/mcpServers, per-turn usage, tag/rename session, RateLimitEvent |
| 0.1.48 | Mar 7 | 2.1.71 | Fixed include_partial_messages input_json_delta |
| 0.1.46 | Mar 5 | 2.1.69 | list/get sessions, add/remove MCP servers, Task messages, stop_reason |

### Branding Guidelines (for SDK Integrators)

**Allowed:**
- "Claude Agent" (preferred for dropdown menus)
- "Claude" (within agent-labeled menus)
- "{YourAgentName} Powered by Claude"

**Not Permitted:**
- "Claude Code" or "Claude Code Agent"
- Claude Code-branded ASCII art or visual elements
