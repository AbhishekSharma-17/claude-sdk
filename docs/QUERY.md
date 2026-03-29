# query() — Complete Reference

> The simplest way to use Claude Agent SDK. One-shot, stateless, fire-and-forget.

---

## Table of Contents

1. [What is query()?](#1-what-is-query)
2. [Function Signature](#2-function-signature)
3. [query() Parameters](#3-query-parameters)
4. [ClaudeAgentOptions — Every Parameter](#4-claudeagentoptions--every-parameter)
   - [Core Parameters](#41-core-parameters)
   - [Tool Control](#42-tool-control)
   - [Cost & Safety Limits](#43-cost--safety-limits)
   - [System Prompt](#44-system-prompt)
   - [MCP Servers (Custom Tools)](#45-mcp-servers-custom-tools)
   - [Session & Conversation](#46-session--conversation)
   - [Model & Provider](#47-model--provider)
   - [Working Directory & Paths](#48-working-directory--paths)
   - [Thinking & Effort](#49-thinking--effort)
   - [Structured Output](#410-structured-output)
   - [Permissions & Hooks](#411-permissions--hooks)
   - [Sandbox](#412-sandbox)
   - [Agents (Sub-agents)](#413-agents-sub-agents)
   - [Streaming & Debugging](#414-streaming--debugging)
   - [Plugins & Settings](#415-plugins--settings)
   - [Token Budget](#416-token-budget)
5. [Message Types (What Comes Back)](#5-message-types-what-comes-back)
   - [AssistantMessage](#51-assistantmessage)
   - [ResultMessage](#52-resultmessage)
   - [Other Message Types](#53-other-message-types)
6. [query() vs ClaudeSDKClient](#6-query-vs-claudesdkclient)
7. [Common Patterns](#7-common-patterns)
8. [Quick Reference Table](#8-quick-reference-table)

---

## 1. What is query()?

`query()` is a **one-shot async function** for talking to Claude. You send a prompt, Claude processes it (optionally using tools), and you get the response back. That's it.

```
You send a prompt → Claude works (may call tools) → You get messages → Done.
```

**Key characteristics:**
- **Stateless** — each call is independent, no memory between calls
- **Unidirectional** — you send everything upfront, then receive
- **No follow-ups** — you can't send additional messages after the query starts
- **No interrupts** — you can't stop Claude mid-execution
- **Simple** — no connection management, no session handling

**Think of it as:** sending an email vs having a phone call. `query()` is the email.

---

## 2. Function Signature

```python
async def query(
    *,
    prompt: str | AsyncIterable[dict[str, Any]],
    options: ClaudeAgentOptions | None = None,
    transport: Transport | None = None,
) -> AsyncIterator[Message]
```

- `*` means all parameters are **keyword-only** (must use `prompt=`, `options=`)
- Returns an **async iterator** — you loop over it with `async for`
- If `options` is not provided, defaults to `ClaudeAgentOptions()` (all defaults)

---

## 3. query() Parameters

### `prompt` (required)

What you want Claude to do. Two forms:

**Simple string (99% of the time):**
```python
async for msg in query(prompt="Explain Python decorators"):
    ...
```

**AsyncIterable (advanced — streaming input):**
```python
async def prompts():
    yield {"type": "user", "message": {"role": "user", "content": "Hello"}}
    yield {"type": "user", "message": {"role": "user", "content": "How are you?"}}

async for msg in query(prompt=prompts()):
    ...
```

> You will almost always use a simple string. The AsyncIterable form is for advanced streaming pipelines.

### `options` (optional)

A `ClaudeAgentOptions` instance that controls everything: model, tools, permissions, cost limits, etc.

```python
options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": "sk-..."},
    allowed_tools=["Read", "Bash"],
    permission_mode="bypassPermissions",
    max_turns=5,
)
async for msg in query(prompt="...", options=options):
    ...
```

If omitted, uses all defaults (no tools, default model, default permissions).

### `transport` (optional — ignore for now)

Custom transport implementation. Only needed if you're building a custom communication layer between the SDK and Claude Code CLI. You won't need this for learning or normal usage.

---

## 4. ClaudeAgentOptions — Every Parameter

`ClaudeAgentOptions` is a Python dataclass with **35+ parameters**. Here's every single one, grouped by purpose.

### 4.1 Core Parameters

#### `model`
**Type:** `str | None`
**Default:** `None` (uses Claude Code's default)

Which Claude model to use.

```python
# Short aliases
model="haiku"      # fastest, cheapest
model="sonnet"     # balanced (recommended)
model="opus"       # most capable, most expensive

# Full model IDs (for Bedrock/Vertex)
model="anthropic.claude-sonnet-4-6"     # AWS Bedrock
model="claude-sonnet-4-6@20250514"       # Google Vertex
```

**When to use:** Always set this explicitly. Don't rely on defaults.

#### `env`
**Type:** `dict[str, str]`
**Default:** `{}` (empty dict)

Environment variables passed to the Claude Code CLI subprocess. This is how you select providers and pass credentials.

```python
# Anthropic Direct API
env={"ANTHROPIC_API_KEY": "sk-ant-..."}

# AWS Bedrock
env={
    "CLAUDE_CODE_USE_BEDROCK": "1",
    "AWS_ACCESS_KEY_ID": "AKIA...",
    "AWS_SECRET_ACCESS_KEY": "wJal...",
    "AWS_REGION": "us-east-1",
}

# Google Vertex
env={
    "CLAUDE_CODE_USE_VERTEX": "1",
    "CLOUD_ML_REGION": "us-east5",
    "ANTHROPIC_VERTEX_PROJECT_ID": "my-project",
}

# Azure (via third-party proxy)
env={
    "ANTHROPIC_BASE_URL": "https://my-azure-proxy.com",
    "ANTHROPIC_API_KEY": "my-azure-key",
}
```

**When to use:** Always. This is how the SDK knows which provider to use.
**Important:** There is NO `provider=` parameter. Provider selection is purely through env vars.

#### `permission_mode`
**Type:** `Literal["default", "acceptEdits", "plan", "bypassPermissions", "dontAsk"] | None`
**Default:** `None` (falls back to `"default"`)

Controls what Claude is allowed to do without asking permission.

| Mode | Reads | Edits | Bash | Description |
|------|-------|-------|------|-------------|
| `"default"` | Auto | Ask | Ask | CLI prompts for dangerous tools |
| `"acceptEdits"` | Auto | Auto | Ask | Auto-accept file edits, ask for bash |
| `"plan"` | Auto | Block | Block | Plan only — Claude can read but not modify |
| `"bypassPermissions"` | Auto | Auto | Auto | Allow everything (scripts/CI) |
| `"dontAsk"` | Auto | Auto | Auto | Same as bypass, allow all without prompting |

```python
# For learning/testing scripts
permission_mode="bypassPermissions"

# For production with human oversight
permission_mode="default"

# For "preview before commit" workflow
permission_mode="plan"
```

**When to use:** Always set this. For scripts, use `"bypassPermissions"`. For production apps with users, use `"default"` or a custom `can_use_tool` callback.

**When NOT to use `"bypassPermissions"`:** When untrusted input could cause Claude to run dangerous bash commands or modify critical files.

---

### 4.2 Tool Control

#### `allowed_tools`
**Type:** `list[str]`
**Default:** `[]` (empty — no tools auto-approved)

Tools that Claude can use **without asking permission**. These are auto-approved.

```python
# Specific built-in tools
allowed_tools=["Read", "Glob", "Grep"]

# Custom MCP tools
allowed_tools=["mcp__utils__validate_email", "mcp__utils__calculate_cost"]

# Wildcard — all tools from an MCP server
allowed_tools=["mcp__utils__*"]

# Mix of built-in and custom
allowed_tools=["Read", "Bash", "mcp__utils__*"]
```

**The 17 built-in tool names:**
`Read`, `Glob`, `Grep`, `Write`, `Edit`, `Bash`, `NotebookEdit`, `WebSearch`, `WebFetch`, `TodoWrite`, `BashOutput`, `KillBash`, `Agent`, `AskUserQuestion`, `ExitPlanMode`, `ListMcpResources`, `ReadMcpResource`

**When to use:** Always. If you don't set this and `permission_mode` is `"default"`, Claude will ask permission for every tool call (which doesn't work in scripts).

#### `disallowed_tools`
**Type:** `list[str]`
**Default:** `[]` (empty — nothing blocked)

Tools Claude is **never** allowed to use. **Overrides everything** — even `allowed_tools` and `bypassPermissions`.

```python
# Block bash for safety
disallowed_tools=["Bash"]

# Block all write operations
disallowed_tools=["Write", "Edit", "Bash"]

# Block a specific MCP tool
disallowed_tools=["mcp__utils__delete_user"]
```

**When to use:** When you want hard safety limits regardless of permission mode. If a tool is in both `allowed_tools` and `disallowed_tools`, it's **blocked**.

**Priority order:** `disallowed_tools` > `allowed_tools` > `permission_mode`

#### `tools`
**Type:** `list[str] | ToolsPreset | None`
**Default:** `None`

Controls which tools are **available** (not just allowed). This is different from `allowed_tools`:
- `tools` = what tools exist (visibility)
- `allowed_tools` = what tools are auto-approved (permission)

```python
# Only make these tools visible to Claude
tools=["Read", "Glob", "Grep"]

# Use the default Claude Code tool preset
tools={"type": "preset", "preset": "claude_code"}
```

**When to use:** Rarely. Most of the time you just use `allowed_tools`. Use `tools` when you want to **hide** tools from Claude entirely (not just deny permission, but make them invisible).

---

### 4.3 Cost & Safety Limits

#### `max_turns`
**Type:** `int | None`
**Default:** `None` (unlimited)

Maximum number of tool-use loops. Each "turn" is one cycle of: Claude thinks → calls a tool → gets result → thinks again.

```python
max_turns=1    # just answer, no tool loops
max_turns=5    # allow up to 5 tool calls
max_turns=10   # allow up to 10 tool calls
max_turns=50   # complex tasks that need many steps
```

**When to use:** Always set this to prevent runaway loops. A simple task needs 1-5 turns. Complex file editing might need 10-20.

**What happens when exceeded:** Claude stops and returns what it has. `ResultMessage.stop_reason` will indicate max turns was hit.

#### `max_budget_usd`
**Type:** `float | None`
**Default:** `None` (unlimited)

Maximum cost in USD for this query. If the cost exceeds this, Claude stops.

```python
max_budget_usd=0.01    # 1 cent — for testing
max_budget_usd=0.10    # 10 cents — for small tasks
max_budget_usd=1.00    # $1 — for larger tasks
max_budget_usd=5.00    # $5 — for complex multi-step work
```

**When to use:** In production, always set a budget. Prevents accidental cost spikes from infinite tool loops.

**When NOT to use:** During development/testing where you want Claude to complete the task regardless of cost (but still set `max_turns`).

---

### 4.4 System Prompt

#### `system_prompt`
**Type:** `str | SystemPromptPreset | SystemPromptFile | None`
**Default:** `None` (uses Claude Code's default system prompt)

Custom instructions that shape Claude's behavior. Three forms:

**Simple string (most common):**
```python
system_prompt="You are a senior Python developer. Be concise. Use type hints."
```

**Preset with append (keep default + add your own):**
```python
system_prompt={
    "type": "preset",
    "preset": "claude_code",
    "append": "Always use async/await. Never use print() in production."
}
```

**Load from file:**
```python
system_prompt={
    "type": "file",
    "path": "/path/to/system_prompt.txt"
}
```

**When to use:** When you want Claude to follow specific rules, adopt a persona, or focus on a particular domain.

**When NOT to use:** For simple factual questions where default behavior is fine.

**Tip:** The preset with `append` is the best approach — you keep Claude Code's built-in capabilities and add your own rules on top.

---

### 4.5 MCP Servers (Custom Tools)

#### `mcp_servers`
**Type:** `dict[str, McpServerConfig] | str | Path`
**Default:** `{}` (no custom servers)

Connect custom tool servers. Four types of MCP servers:

**SDK server (in-process, recommended for custom tools):**
```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool(name="greet", description="Greet someone", input_schema={"name": str})
async def greet(args):
    return {"content": [{"type": "text", "text": f"Hello {args['name']}!"}]}

server = create_sdk_mcp_server(name="my_tools", tools=[greet])

mcp_servers={"my_tools": server}
```

**Stdio server (external process):**
```python
mcp_servers={
    "my_db": {
        "type": "stdio",
        "command": "python",
        "args": ["-m", "my_db_server"],
        "env": {"DB_URL": "postgres://..."},
    }
}
```

**SSE server (remote, Server-Sent Events):**
```python
mcp_servers={
    "remote_api": {
        "type": "sse",
        "url": "https://my-server.com/mcp/sse",
        "headers": {"Authorization": "Bearer token"},
    }
}
```

**HTTP server (remote, HTTP):**
```python
mcp_servers={
    "remote_api": {
        "type": "http",
        "url": "https://my-server.com/mcp",
        "headers": {"Authorization": "Bearer token"},
    }
}
```

**When to use:** When Claude needs to call your custom business logic (validate data, query your DB, call your APIs, etc.).

**Remember:** After connecting, you must also add tool names to `allowed_tools`:
```python
allowed_tools=["mcp__my_tools__greet"]
# or wildcard:
allowed_tools=["mcp__my_tools__*"]
```

---

### 4.6 Session & Conversation

#### `resume`
**Type:** `str | None`
**Default:** `None`

Resume a previous session by its ID. The session ID comes from `ResultMessage.session_id`.

```python
# First query
async for msg in query(prompt="Read app.py", options=options):
    if isinstance(msg, ResultMessage):
        session_id = msg.session_id  # save this

# Resume later
options_resume = ClaudeAgentOptions(
    ...
    resume=session_id,
)
async for msg in query(prompt="Now fix the bugs you found", options=options_resume):
    ...
```

**When to use:** When you want to continue a previous conversation's context (Claude remembers what it read/did before).

#### `continue_conversation`
**Type:** `bool`
**Default:** `False`

When `True`, continues the most recent conversation in the working directory.

```python
continue_conversation=True
```

**When to use:** Quick way to continue without tracking session IDs. Less precise than `resume`.

#### `fork_session`
**Type:** `bool`
**Default:** `False`

When resuming a session, create a new session ID instead of continuing the old one. The new session gets the old context but diverges from that point.

```python
fork_session=True
```

**When to use:** When you want to branch a conversation — try different approaches from the same starting point without affecting the original session.

---

### 4.7 Model & Provider

#### `model`
See [Core Parameters](#41-core-parameters) above.

#### `fallback_model`
**Type:** `str | None`
**Default:** `None`

Model to use if the primary model fails (rate limit, unavailable, etc.).

```python
model="opus",
fallback_model="sonnet"     # fall back to sonnet if opus is unavailable
```

**When to use:** In production, to handle model unavailability gracefully.

#### `env`
See [Core Parameters](#41-core-parameters) above.

---

### 4.8 Working Directory & Paths

#### `cwd`
**Type:** `str | Path | None`
**Default:** `None` (current working directory)

Working directory for Claude's file operations. All relative paths in Read, Write, Glob, etc. are relative to this.

```python
cwd="/Users/abhishek/projects/my-app"
```

**When to use:** When your script runs from a different directory than the project you want Claude to work on.

#### `add_dirs`
**Type:** `list[str | Path]`
**Default:** `[]`

Additional directories Claude can access beyond `cwd`.

```python
add_dirs=["/shared/configs", "/data/datasets"]
```

**When to use:** When Claude needs to read files outside the main project directory.

#### `cli_path`
**Type:** `str | Path | None`
**Default:** `None` (auto-detected)

Path to the Claude Code CLI binary. Only needed if it's not in your PATH.

```python
cli_path="/usr/local/bin/claude"
```

**When to use:** Almost never. Only if auto-detection fails.

#### `settings`
**Type:** `str | None`
**Default:** `None`

Path to a Claude Code settings file to load.

```python
settings="/path/to/custom-settings.json"
```

**When to use:** When you have project-specific Claude Code settings you want to apply.

---

### 4.9 Thinking & Effort

#### `thinking`
**Type:** `ThinkingConfig | None`
**Default:** `None`

Controls extended thinking — Claude "thinks out loud" before responding.

```python
# Adaptive — Claude decides when to think
thinking={"type": "adaptive"}

# Enabled with token budget
thinking={"type": "enabled", "budget_tokens": 10000}

# Disabled
thinking={"type": "disabled"}
```

**When to use:** For complex reasoning tasks (math, logic, code architecture). Improves quality but costs more tokens.

**When NOT to use:** For simple factual questions — wastes tokens.

#### `effort`
**Type:** `Literal["low", "medium", "high", "max"] | None`
**Default:** `None`

Controls how much effort Claude puts into thinking.

```python
effort="low"       # quick, minimal thinking
effort="medium"    # balanced (default behavior)
effort="high"      # deeper reasoning
effort="max"       # maximum reasoning depth
```

**When to use:** `"high"` or `"max"` for complex tasks. `"low"` for simple tasks where speed matters.

#### `max_thinking_tokens` (DEPRECATED)
**Type:** `int | None`
**Default:** `None`

> **Deprecated.** Use `thinking` instead.

```python
# Old way (deprecated)
max_thinking_tokens=10000

# New way
thinking={"type": "enabled", "budget_tokens": 10000}
```

---

### 4.10 Structured Output

#### `output_format`
**Type:** `dict[str, Any] | None`
**Default:** `None` (normal text response)

Force Claude to respond in a specific JSON schema. The response will be in `ResultMessage.structured_output`.

```python
output_format={
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "score": {"type": "integer", "minimum": 1, "maximum": 10},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary", "score"],
    }
}
```

**When to use:** When you need machine-readable output — parsing Claude's text into structured data.

**Access the result:**
```python
if isinstance(msg, ResultMessage):
    data = msg.structured_output  # parsed JSON matching your schema
```

---

### 4.11 Permissions & Hooks

#### `can_use_tool`
**Type:** `CanUseTool | None`
**Default:** `None`

Custom async callback for tool permission decisions. Called whenever Claude wants to use a tool (if not already in `allowed_tools`).

```python
async def my_permission_handler(
    tool_name: str,
    tool_input: dict[str, Any],
    context: ToolPermissionContext,
) -> PermissionResult:
    # Allow reads, deny everything else
    if tool_name == "Read":
        return PermissionResultAllow()
    if tool_name == "Bash" and "rm " in tool_input.get("command", ""):
        return PermissionResultDeny(message="No delete commands allowed")
    return PermissionResultAllow()

can_use_tool=my_permission_handler
```

**When to use:** When you need fine-grained, dynamic permission control. For example: allow bash but block `rm`, allow writes but only to certain directories.

**When NOT to use:** For simple allow/deny — just use `allowed_tools` and `disallowed_tools`.

#### `permission_prompt_tool_name`
**Type:** `str | None`
**Default:** `None`

Name of a custom tool that handles permission prompts. Advanced use case for building custom permission UIs.

**When to use:** Almost never. Only for custom permission prompt implementations.

#### `hooks`
**Type:** `dict[HookEvent, list[HookMatcher]] | None`
**Default:** `None`

Intercept and modify Claude's behavior at specific points. Hook events:

| Event | When it fires |
|-------|--------------|
| `"PreToolUse"` | Before Claude calls any tool |
| `"PostToolUse"` | After a tool returns a result |
| `"PostToolUseFailure"` | After a tool call fails |
| `"UserPromptSubmit"` | When a user prompt is submitted |
| `"Stop"` | When Claude is about to stop |
| `"SubagentStop"` | When a sub-agent stops |
| `"PreCompact"` | Before context compaction |
| `"Notification"` | On notification events |
| `"SubagentStart"` | When a sub-agent starts |
| `"PermissionRequest"` | When permission is requested |

```python
from claude_agent_sdk import HookMatcher

async def log_bash_commands(input_data, tool_use_id, context):
    """Log every bash command before execution."""
    if input_data.get("tool_name") == "Bash":
        print(f"AUDIT: Bash command: {input_data['tool_input'].get('command')}")
    return {}  # empty = allow

hooks={
    "PreToolUse": [
        HookMatcher(matcher="Bash", hooks=[log_bash_commands])
    ]
}
```

**When to use:** Auditing, logging, modifying tool inputs, blocking specific operations dynamically.

**When NOT to use:** For simple permission control — use `allowed_tools`/`disallowed_tools` instead.

---

### 4.12 Sandbox

#### `sandbox`
**Type:** `SandboxSettings | None`
**Default:** `None` (no sandboxing)

Isolate bash commands in a sandbox for security. Restricts file system and network access.

```python
sandbox={
    "enabled": True,
    "autoAllowBashIfSandboxed": True,     # auto-approve bash when sandboxed
    "excludedCommands": ["git", "docker"],  # these run outside sandbox
    "allowUnsandboxedCommands": False,      # force all commands through sandbox
    "network": {
        "allowUnixSockets": ["/var/run/docker.sock"],
        "allowLocalBinding": True,
    },
}
```

**SandboxSettings fields:**

| Field | Type | Default | What it does |
|-------|------|---------|-------------|
| `enabled` | `bool` | `False` | Enable sandbox (macOS/Linux only) |
| `autoAllowBashIfSandboxed` | `bool` | `True` | Auto-approve sandboxed bash |
| `excludedCommands` | `list[str]` | `[]` | Commands that bypass sandbox |
| `allowUnsandboxedCommands` | `bool` | `True` | Allow `dangerouslyDisableSandbox` |
| `network` | `SandboxNetworkConfig` | - | Network access rules |
| `ignoreViolations` | `SandboxIgnoreViolations` | - | Violations to ignore |
| `enableWeakerNestedSandbox` | `bool` | `False` | For Docker (Linux only) |

**When to use:** In production when running untrusted prompts or when Claude has bash access.

**When NOT to use:** During development/learning — adds complexity without benefit.

---

### 4.13 Agents (Sub-agents)

#### `agents`
**Type:** `dict[str, AgentDefinition] | None`
**Default:** `None`

Define custom sub-agents that Claude can spawn using the `Agent` tool.

```python
from claude_agent_sdk import AgentDefinition

agents={
    "code-reviewer": AgentDefinition(
        description="Reviews code for bugs and best practices",
        prompt="You are a senior code reviewer. Focus on security and performance.",
        tools=["Read", "Glob", "Grep"],
        model="sonnet",
        maxTurns=5,
    ),
    "test-writer": AgentDefinition(
        description="Writes pytest test suites",
        prompt="You are a test engineer. Write comprehensive pytest tests.",
        tools=["Read", "Write", "Bash"],
        model="sonnet",
        maxTurns=10,
    ),
}
```

**AgentDefinition fields:**

| Field | Type | What it does |
|-------|------|-------------|
| `description` | `str` | What the agent does (shown to Claude) |
| `prompt` | `str` | System prompt for the sub-agent |
| `tools` | `list[str] | None` | Tools the sub-agent can use |
| `disallowedTools` | `list[str] | None` | Tools blocked for sub-agent |
| `model` | `str | None` | Model for sub-agent |
| `skills` | `list[str] | None` | Skills available to sub-agent |
| `maxTurns` | `int | None` | Max turns for sub-agent |
| `mcpServers` | `list | None` | MCP servers for sub-agent |
| `initialPrompt` | `str | None` | Initial prompt override |

**When to use:** When you want Claude to delegate subtasks to specialized agents with different tools/prompts.

---

### 4.14 Streaming & Debugging

#### `include_partial_messages`
**Type:** `bool`
**Default:** `False`

When `True`, yields `StreamEvent` messages with partial tokens as they arrive (like ChatGPT's typing effect).

```python
include_partial_messages=True
```

```python
from claude_agent_sdk import StreamEvent

async for msg in query(prompt="...", options=options):
    if isinstance(msg, StreamEvent):
        # Raw Anthropic API stream event
        event = msg.event
        # Handle partial text deltas here
```

**When to use:** Building a chat UI where you want to show tokens as they stream in.

**When NOT to use:** Scripts, batch jobs, CI/CD — you just want the final result.

#### `stderr`
**Type:** `Callable[[str], None] | None`
**Default:** `None`

Callback function that receives stderr output from the Claude Code CLI process. Useful for debugging.

```python
stderr=lambda line: print(f"[DEBUG] {line}")
```

**When to use:** Debugging when things aren't working as expected.

#### `debug_stderr` (DEPRECATED)
**Type:** `Any`
**Default:** `sys.stderr`

> **Deprecated.** Use `stderr` callback instead.

#### `max_buffer_size`
**Type:** `int | None`
**Default:** `None`

Maximum bytes when buffering CLI stdout. Only needed if you're dealing with very large responses.

**When to use:** Almost never. Only if you're getting buffer overflow errors with huge outputs.

#### `extra_args`
**Type:** `dict[str, str | None]`
**Default:** `{}`

Pass arbitrary CLI flags to the Claude Code subprocess.

```python
extra_args={"--verbose": None, "--timeout": "30"}
```

**When to use:** When you need a CLI feature not exposed through ClaudeAgentOptions.

---

### 4.15 Plugins & Settings

#### `plugins`
**Type:** `list[SdkPluginConfig]`
**Default:** `[]`

Load custom plugins.

```python
plugins=[
    {"type": "local", "path": "/path/to/my-plugin"},
]
```

**When to use:** When you have a local Claude Code plugin to load.

#### `setting_sources`
**Type:** `list[SettingSource] | None`
**Default:** `None` (loads all)

Which settings files to load. Options: `"user"`, `"project"`, `"local"`.

```python
# Only load project settings, ignore user/local
setting_sources=["project"]

# Load nothing — pure programmatic config
setting_sources=[]
```

**When to use:** When you want to control which `.claude/settings.json` files are loaded.

#### `user`
**Type:** `str | None`
**Default:** `None`

User identifier for audit/tracking purposes.

```python
user="abhishek@genaiprotos.com"
```

**When to use:** In multi-user systems where you need to track who made which query.

#### `betas`
**Type:** `list[SdkBeta]`
**Default:** `[]`

Enable beta features.

```python
betas=["context-1m-2025-08-07"]  # 1M context window beta
```

**When to use:** When you want to opt in to Anthropic beta features.

---

### 4.16 Token Budget

#### `task_budget`
**Type:** `TaskBudget | None`
**Default:** `None`

API-side token budget. When set, the model is aware of its remaining budget and paces itself.

```python
task_budget={"total": 50000}  # 50K token budget
```

**When to use:** When you want Claude to wrap up within a token limit (different from cost limit — this is tokens, not dollars).

#### `enable_file_checkpointing`
**Type:** `bool`
**Default:** `False`

Track file changes during the session. When enabled, files can be rewound to their state at any point.

```python
enable_file_checkpointing=True
```

**When to use:** When you want undo capability — rewind files if Claude's changes aren't good. Only works with `ClaudeSDKClient.rewind_files()`.

---

## 5. Message Types (What Comes Back)

`query()` yields different message types as Claude works. Here's what you'll receive:

### 5.1 AssistantMessage

Claude's response — text and/or tool calls.

```python
@dataclass
class AssistantMessage:
    content: list[ContentBlock]           # text, tool calls, thinking
    model: str                            # which model was used
    parent_tool_use_id: str | None        # for sub-agent responses
    error: str | None                     # error type if failed
    usage: dict | None                    # token counts for this message
    message_id: str | None                # unique message ID
    stop_reason: str | None               # why this message ended
    session_id: str | None                # session ID
```

**Content blocks inside AssistantMessage:**

```python
for block in message.content:
    if isinstance(block, TextBlock):
        print(block.text)                 # Claude's words

    elif isinstance(block, ToolUseBlock):
        print(block.name)                 # tool name: "Read", "Bash", etc.
        print(block.input)                # tool arguments: {"file_path": "..."}
        print(block.id)                   # unique tool call ID

    elif isinstance(block, ThinkingBlock):
        print(block.thinking)             # Claude's internal reasoning
        print(block.signature)            # thinking block signature
```

### 5.2 ResultMessage

Final summary — always the **last message** from `query()`.

```python
@dataclass
class ResultMessage:
    subtype: str                          # "result"
    duration_ms: int                      # total wall time in milliseconds
    duration_api_ms: int                  # time spent on API calls
    is_error: bool                        # did the query fail?
    num_turns: int                        # how many tool-use turns
    session_id: str                       # session ID (save for resume)
    stop_reason: str | None               # "end_turn", "max_turns", etc.
    total_cost_usd: float | None          # total cost in USD
    usage: dict | None                    # aggregate token counts
    result: str | None                    # final text result
    structured_output: Any                # if output_format was set
    model_usage: dict | None              # per-model token breakdown
    permission_denials: list | None       # tools that were denied
    errors: list[str] | None             # error messages
```

**Common pattern:**
```python
async for msg in query(prompt="...", options=options):
    if isinstance(msg, ResultMessage):
        print(f"Cost: ${msg.total_cost_usd:.4f}")
        print(f"Turns: {msg.num_turns}")
        print(f"Time: {msg.duration_ms}ms")
        print(f"Session: {msg.session_id}")
        if msg.is_error:
            print(f"ERRORS: {msg.errors}")
```

### 5.3 Other Message Types

| Type | When you see it | Should you handle it? |
|------|----------------|----------------------|
| `UserMessage` | User's own messages (in streaming mode) | Rarely |
| `SystemMessage` | Internal SDK events (task started, progress) | Usually ignore |
| `TaskStartedMessage` | Sub-agent task started (subclass of SystemMessage) | If using agents |
| `TaskProgressMessage` | Sub-agent progress update | If using agents |
| `TaskNotificationMessage` | Sub-agent completed/failed | If using agents |
| `StreamEvent` | Partial tokens (if `include_partial_messages=True`) | For streaming UIs |
| `RateLimitEvent` | Rate limit warning/rejection | In production |

**Minimal message handling (covers 99% of cases):**
```python
async for msg in query(prompt="...", options=options):
    if isinstance(msg, AssistantMessage):
        for block in msg.content:
            if isinstance(block, TextBlock):
                print(block.text)
            elif isinstance(block, ToolUseBlock):
                print(f"[Tool] {block.name}({block.input})")
    elif isinstance(msg, ResultMessage):
        print(f"[Done] ${msg.total_cost_usd:.4f} | {msg.num_turns} turns")
```

---

## 6. query() vs ClaudeSDKClient

| Feature | `query()` | `ClaudeSDKClient` |
|---------|-----------|-------------------|
| **Style** | One-shot function | Stateful class (async context manager) |
| **State** | Stateless — each call is independent | Stateful — remembers conversation |
| **Follow-ups** | Cannot send follow-up messages | Can send multiple messages |
| **Interrupt** | Cannot interrupt mid-execution | Can interrupt with `client.interrupt()` |
| **AskUserQuestion** | Does NOT work (no way to reply) | Works (human-in-the-loop) |
| **Connection** | Auto-managed per call | You manage with `async with` |
| **Best for** | Scripts, CI/CD, batch jobs, simple tasks | Chat apps, interactive agents, complex workflows |
| **Complexity** | Simple | More setup needed |

**Use `query()` when:**
- You know all inputs upfront
- No back-and-forth needed
- Automated scripts and pipelines
- One-off tasks

**Use `ClaudeSDKClient` when:**
- Interactive conversation needed
- Need to ask user questions (AskUserQuestion tool)
- Need to interrupt/cancel mid-execution
- Building a chat application
- Multi-turn workflows with context

---

## 7. Common Patterns

### Pattern 1: Simple Question (no tools)
```python
options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
    max_turns=1,
    permission_mode="bypassPermissions",
)

async for msg in query(prompt="What is Python's GIL?", options=options):
    if isinstance(msg, AssistantMessage):
        for block in msg.content:
            if isinstance(block, TextBlock):
                print(block.text)
```

### Pattern 2: File Analysis
```python
options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
    allowed_tools=["Read", "Glob", "Grep"],
    permission_mode="bypassPermissions",
    max_turns=10,
    cwd="/path/to/project",
)

async for msg in query(
    prompt="Find all TODO comments in the codebase and summarize them.",
    options=options,
):
    ...
```

### Pattern 3: Code Generation with Budget
```python
options = ClaudeAgentOptions(
    model="opus",
    env={"ANTHROPIC_API_KEY": API_KEY},
    allowed_tools=["Read", "Write", "Bash"],
    permission_mode="bypassPermissions",
    max_turns=20,
    max_budget_usd=2.00,
    system_prompt="You are a senior Python developer. Follow PEP 8. Use type hints.",
    cwd="/path/to/project",
)

async for msg in query(
    prompt="Create a FastAPI CRUD API for a user management system.",
    options=options,
):
    ...
```

### Pattern 4: Read-Only Analysis (safe)
```python
options = ClaudeAgentOptions(
    model="haiku",
    env={"ANTHROPIC_API_KEY": API_KEY},
    allowed_tools=["Read", "Glob", "Grep"],
    disallowed_tools=["Write", "Edit", "Bash"],    # hard block writes
    permission_mode="bypassPermissions",
    max_turns=10,
    max_budget_usd=0.10,
)

async for msg in query(
    prompt="Analyze this codebase and list potential security issues.",
    options=options,
):
    ...
```

### Pattern 5: Structured Output
```python
options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
    max_turns=1,
    permission_mode="bypassPermissions",
    output_format={
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {
                "language": {"type": "string"},
                "frameworks": {"type": "array", "items": {"type": "string"}},
                "complexity": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "required": ["language", "frameworks", "complexity"],
        },
    },
)

async for msg in query(
    prompt="Analyze this code: def app(): return FastAPI()",
    options=options,
):
    if isinstance(msg, ResultMessage):
        data = msg.structured_output
        # {"language": "Python", "frameworks": ["FastAPI"], "complexity": "low"}
```

### Pattern 6: Resume a Previous Session
```python
# First query
session_id = None
async for msg in query(prompt="Read all files in src/", options=options):
    if isinstance(msg, ResultMessage):
        session_id = msg.session_id

# Later — resume with context
resume_options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
    allowed_tools=["Read", "Write", "Edit"],
    permission_mode="bypassPermissions",
    resume=session_id,
    max_turns=10,
)

async for msg in query(
    prompt="Now refactor the utils.py file you read earlier.",
    options=resume_options,
):
    ...
```

### Pattern 7: With Custom Tools
```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool(name="get_user", description="Get user by ID", input_schema={"user_id": int})
async def get_user(args):
    user = {"id": args["user_id"], "name": "Abhishek", "role": "Lead"}
    return {"content": [{"type": "text", "text": json.dumps(user)}]}

server = create_sdk_mcp_server(name="api", tools=[get_user])

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
    mcp_servers={"api": server},
    allowed_tools=["mcp__api__get_user"],
    permission_mode="bypassPermissions",
    max_turns=5,
)

async for msg in query(prompt="Get user #42 and describe them.", options=options):
    ...
```

---

## 8. Quick Reference Table

### All ClaudeAgentOptions Parameters

| # | Parameter | Type | Default | Category |
|---|-----------|------|---------|----------|
| 1 | `model` | `str \| None` | `None` | Core |
| 2 | `env` | `dict[str, str]` | `{}` | Core |
| 3 | `permission_mode` | `PermissionMode \| None` | `None` | Core |
| 4 | `allowed_tools` | `list[str]` | `[]` | Tools |
| 5 | `disallowed_tools` | `list[str]` | `[]` | Tools |
| 6 | `tools` | `list[str] \| ToolsPreset \| None` | `None` | Tools |
| 7 | `max_turns` | `int \| None` | `None` | Limits |
| 8 | `max_budget_usd` | `float \| None` | `None` | Limits |
| 9 | `system_prompt` | `str \| Preset \| File \| None` | `None` | Prompt |
| 10 | `mcp_servers` | `dict \| str \| Path` | `{}` | MCP |
| 11 | `resume` | `str \| None` | `None` | Session |
| 12 | `continue_conversation` | `bool` | `False` | Session |
| 13 | `fork_session` | `bool` | `False` | Session |
| 14 | `fallback_model` | `str \| None` | `None` | Model |
| 15 | `cwd` | `str \| Path \| None` | `None` | Paths |
| 16 | `add_dirs` | `list[str \| Path]` | `[]` | Paths |
| 17 | `cli_path` | `str \| Path \| None` | `None` | Paths |
| 18 | `settings` | `str \| None` | `None` | Settings |
| 19 | `thinking` | `ThinkingConfig \| None` | `None` | Thinking |
| 20 | `effort` | `"low" \| "medium" \| "high" \| "max" \| None` | `None` | Thinking |
| 21 | `max_thinking_tokens` | `int \| None` (deprecated) | `None` | Thinking |
| 22 | `output_format` | `dict \| None` | `None` | Output |
| 23 | `can_use_tool` | `CanUseTool \| None` | `None` | Permissions |
| 24 | `permission_prompt_tool_name` | `str \| None` | `None` | Permissions |
| 25 | `hooks` | `dict[HookEvent, list[HookMatcher]] \| None` | `None` | Hooks |
| 26 | `sandbox` | `SandboxSettings \| None` | `None` | Security |
| 27 | `agents` | `dict[str, AgentDefinition] \| None` | `None` | Agents |
| 28 | `include_partial_messages` | `bool` | `False` | Streaming |
| 29 | `stderr` | `Callable \| None` | `None` | Debug |
| 30 | `debug_stderr` | `Any` (deprecated) | `sys.stderr` | Debug |
| 31 | `max_buffer_size` | `int \| None` | `None` | Advanced |
| 32 | `extra_args` | `dict[str, str \| None]` | `{}` | Advanced |
| 33 | `plugins` | `list[SdkPluginConfig]` | `[]` | Plugins |
| 34 | `setting_sources` | `list[SettingSource] \| None` | `None` | Settings |
| 35 | `user` | `str \| None` | `None` | Tracking |
| 36 | `betas` | `list[SdkBeta]` | `[]` | Beta |
| 37 | `task_budget` | `TaskBudget \| None` | `None` | Limits |
| 38 | `enable_file_checkpointing` | `bool` | `False` | Session |

### Permission Priority

```
disallowed_tools  →  ALWAYS BLOCKED (highest priority)
       ↓
allowed_tools     →  AUTO-APPROVED
       ↓
can_use_tool      →  CUSTOM CALLBACK
       ↓
permission_mode   →  FALLBACK BEHAVIOR (lowest priority)
```

### Minimum Viable Options

```python
# Absolute minimum — just answer a question
ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
)

# With tools — the typical setup
ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
    allowed_tools=["Read", "Glob", "Grep"],
    permission_mode="bypassPermissions",
    max_turns=5,
)

# Production — with safety limits
ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
    allowed_tools=["Read", "Glob", "Grep"],
    disallowed_tools=["Bash"],
    permission_mode="default",
    max_turns=10,
    max_budget_usd=1.00,
    cwd="/path/to/project",
)
```
