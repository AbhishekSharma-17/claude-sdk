# ClaudeSDKClient — Complete Reference

> The stateful, multi-turn, interactive client for Claude Agent SDK.

---

## Table of Contents

1. [What is ClaudeSDKClient?](#1-what-is-claudesdkclient)
2. [query() vs ClaudeSDKClient — When to Use Which](#2-query-vs-claudesdkclient--when-to-use-which)
3. [How It Works](#3-how-it-works)
4. [Constructor](#4-constructor)
5. [Lifecycle — connect, use, disconnect](#5-lifecycle--connect-use-disconnect)
6. [All Methods](#6-all-methods)
   - [connect()](#61-connect)
   - [query()](#62-query)
   - [receive_messages()](#63-receive_messages)
   - [receive_response()](#64-receive_response)
   - [interrupt()](#65-interrupt)
   - [set_permission_mode()](#66-set_permission_mode)
   - [set_model()](#67-set_model)
   - [rewind_files()](#68-rewind_files)
   - [get_mcp_status()](#69-get_mcp_status)
   - [reconnect_mcp_server()](#610-reconnect_mcp_server)
   - [toggle_mcp_server()](#611-toggle_mcp_server)
   - [stop_task()](#612-stop_task)
   - [get_server_info()](#613-get_server_info)
   - [disconnect()](#614-disconnect)
7. [Message Types (What Comes Back)](#7-message-types-what-comes-back)
8. [Common Patterns](#8-common-patterns)
9. [Quick Reference Table](#9-quick-reference-table)

---

## 1. What is ClaudeSDKClient?

`ClaudeSDKClient` is a **stateful, bidirectional client** for multi-turn conversations with Claude. Unlike `query()` which is fire-and-forget, the client keeps a persistent connection open and lets you:

- Send multiple messages back and forth
- React to Claude's responses with follow-ups
- Interrupt Claude mid-execution
- Change model or permission mode mid-conversation
- Use the `AskUserQuestion` tool (human-in-the-loop)
- Manage MCP servers dynamically
- Rewind file changes to a checkpoint

**Think of it as:**
- `query()` = sending an email (one-shot, no back-and-forth)
- `ClaudeSDKClient` = having a phone call (interactive, real-time, multi-turn)

---

## 2. query() vs ClaudeSDKClient — When to Use Which

| Feature | `query()` | `ClaudeSDKClient` |
|---------|-----------|-------------------|
| **Style** | One-shot function | Stateful class |
| **State** | Stateless — each call independent | Stateful — remembers full conversation |
| **Follow-ups** | Cannot send follow-ups | Send as many follow-ups as you want |
| **Interrupt** | Cannot interrupt | `client.interrupt()` stops Claude |
| **AskUserQuestion** | Does NOT work | Works — human-in-the-loop |
| **Change model mid-chat** | No | `client.set_model("opus")` |
| **Change permissions mid-chat** | No | `client.set_permission_mode("plan")` |
| **MCP server management** | Static only | Dynamic — reconnect, toggle, check status |
| **File rewind** | No | `client.rewind_files(checkpoint_id)` |
| **Connection** | Auto-managed | You manage with `async with` or `connect()`/`disconnect()` |
| **Complexity** | Simple | More setup, more power |
| **Best for** | Scripts, CI/CD, batch jobs | Chat apps, interactive agents, complex workflows |

### Use `query()` when:
- You know all inputs upfront
- No back-and-forth needed
- Simple automated scripts and pipelines
- One-off tasks

### Use `ClaudeSDKClient` when:
- Multi-turn conversation needed
- Need to ask user questions (AskUserQuestion tool)
- Need to interrupt/cancel mid-execution
- Building a chat application
- Need to change model/permissions mid-conversation
- Need dynamic MCP server management
- Need file rewind capability

---

## 3. How It Works

### The Flow

```
1. CREATE:     client = ClaudeSDKClient(options=options)
2. CONNECT:    async with client:       (or await client.connect())
3. SEND:       await client.query("your prompt")
4. RECEIVE:    async for msg in client.receive_response():
5. REPEAT:     go to step 3 for follow-ups
6. DISCONNECT: automatic with 'async with' (or await client.disconnect())
```

### What Happens Under the Hood

```
Your Python script ←→ ClaudeSDKClient ←→ Claude Code CLI subprocess ←→ Claude API
                       (persistent connection, bidirectional)
```

The client spawns a Claude Code CLI process and maintains a persistent stdin/stdout pipe. Messages flow both ways:
- **You → Claude**: `client.query("...")` writes to CLI's stdin
- **Claude → You**: `client.receive_response()` reads from CLI's stdout
- **Control**: `client.interrupt()`, `client.set_permission_mode()`, etc. send control messages

---

## 4. Constructor

```python
client = ClaudeSDKClient(
    options: ClaudeAgentOptions | None = None,
    transport: Transport | None = None,
)
```

### Parameters

#### `options`
**Type:** `ClaudeAgentOptions | None`
**Default:** `ClaudeAgentOptions()` (all defaults)

Same `ClaudeAgentOptions` used by `query()`. All 38 parameters work here. See [QUERY.md](QUERY.md) for the full parameter reference.

```python
options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
    allowed_tools=["Read", "Glob", "Grep", "AskUserQuestion"],
    permission_mode="bypassPermissions",
    max_turns=10,
)
client = ClaudeSDKClient(options=options)
```

#### `transport`
**Type:** `Transport | None`
**Default:** `None` (auto-creates subprocess transport)

Custom transport implementation. Ignore this — only for advanced use cases like custom communication layers.

---

## 5. Lifecycle — connect, use, disconnect

### Option A: `async with` (Recommended)

Auto-connects on enter, auto-disconnects on exit. Handles cleanup even if errors occur.

```python
async with ClaudeSDKClient(options=options) as client:
    # client is connected here
    await client.query("Hello!")
    async for msg in client.receive_response():
        ...
    # More queries...
    await client.query("Follow-up question")
    async for msg in client.receive_response():
        ...
# client is automatically disconnected here
```

### Option B: Manual connect/disconnect

More control, but you must handle cleanup yourself.

```python
client = ClaudeSDKClient(options=options)
try:
    await client.connect()
    await client.query("Hello!")
    async for msg in client.receive_response():
        ...
finally:
    await client.disconnect()
```

### What `async with` Does Internally

```python
# This:
async with ClaudeSDKClient(options=options) as client:
    ...

# Is equivalent to:
client = ClaudeSDKClient(options=options)
await client.connect()   # __aenter__: connects with empty stream
try:
    ...
finally:
    await client.disconnect()  # __aexit__: always disconnects
```

### Important: Same Async Context

The client must be used within the same async context where it was created. You cannot pass it between different asyncio tasks or event loops.

```python
# CORRECT — same async context
async def main():
    async with ClaudeSDKClient(options=options) as client:
        await client.query("Hello")
        async for msg in client.receive_response():
            ...

# WRONG — different async contexts
client = ClaudeSDKClient(options=options)
# Don't try to use this client across different tasks/event loops
```

---

## 6. All Methods

### 6.1 `connect()`

```python
await client.connect(prompt: str | AsyncIterable | None = None)
```

Starts the Claude Code CLI subprocess and establishes the bidirectional connection.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | `str \| AsyncIterable \| None` | `None` | Optional initial prompt |

**Usage:**

```python
# Auto-connect (via async with) — most common
async with ClaudeSDKClient(options=options) as client:
    ...  # already connected

# Manual connect — no initial prompt
client = ClaudeSDKClient(options=options)
await client.connect()

# Manual connect — with initial prompt
await client.connect(prompt="Analyze this codebase")
```

**When to use:** Automatically called by `async with`. Only call manually if not using context manager.

**Note:** If you pass `prompt` here, it's equivalent to calling `connect()` then `query(prompt)`.

---

### 6.2 `query()`

```python
await client.query(prompt: str | AsyncIterable, session_id: str = "default")
```

Send a message to Claude. This is **non-blocking** — it sends the message and returns immediately. You must then call `receive_response()` to get Claude's reply.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | `str \| AsyncIterable` | required | Your message to Claude |
| `session_id` | `str` | `"default"` | Session identifier |

**Usage:**

```python
# Simple string message
await client.query("What files are in this project?")

# Follow-up (Claude remembers previous context)
await client.query("Now fix the bug in app.py")

# Another follow-up
await client.query("Run the tests to verify the fix")
```

**Important:** `query()` does NOT return the response. You must call `receive_response()` after it:

```python
await client.query("Hello")                    # sends message
async for msg in client.receive_response():    # receives response
    ...
```

**When to use:** Every time you want to send a message to Claude.

---

### 6.3 `receive_messages()`

```python
async for msg in client.receive_messages():
    ...
```

Low-level method that yields ALL messages from Claude **indefinitely**. Does not stop at `ResultMessage` — keeps listening forever.

**Returns:** `AsyncIterator[Message]` — never ends on its own.

**Usage:**

```python
# Low-level — you must break manually
async for msg in client.receive_messages():
    if isinstance(msg, AssistantMessage):
        ...
    elif isinstance(msg, ResultMessage):
        break  # YOU must break, or it runs forever
```

**When to use:** Advanced use cases where you need to process messages across multiple query/response cycles without stopping.

**When NOT to use:** For normal single-response workflows — use `receive_response()` instead.

---

### 6.4 `receive_response()`

```python
async for msg in client.receive_response():
    ...
```

High-level convenience method. Yields messages until a `ResultMessage` is received, then **automatically stops**.

**Returns:** `AsyncIterator[Message]` — stops after `ResultMessage`.

**Usage:**

```python
await client.query("Explain Python decorators")

async for msg in client.receive_response():
    if isinstance(msg, AssistantMessage):
        for block in msg.content:
            if isinstance(block, TextBlock):
                print(block.text)
            elif isinstance(block, ToolUseBlock):
                print(f"[Tool] {block.name}")
    elif isinstance(msg, ResultMessage):
        print(f"Cost: ${msg.total_cost_usd:.4f}")
        # Iterator automatically stops here
```

**When to use:** Almost always. This is the standard way to receive a response.

**Key difference from `receive_messages()`:**
- `receive_response()` — stops after `ResultMessage` (one response cycle)
- `receive_messages()` — runs forever (you must break manually)

---

### 6.5 `interrupt()`

```python
await client.interrupt()
```

Send an interrupt signal to stop Claude mid-execution. Like pressing Ctrl+C.

**Usage:**

```python
import asyncio

async with ClaudeSDKClient(options=options) as client:
    await client.query("Refactor every file in this large project")

    # After 10 seconds, interrupt
    await asyncio.sleep(10)
    await client.interrupt()

    # Receive whatever Claude completed before interrupt
    async for msg in client.receive_response():
        ...
```

**When to use:**
- User clicks "Stop" in a chat UI
- Task is taking too long
- You got enough information and want to stop early

**What happens after interrupt:**
- Claude stops working
- A `ResultMessage` is emitted with what was completed
- You can still send new queries on the same client

---

### 6.6 `set_permission_mode()`

```python
await client.set_permission_mode(mode: PermissionMode)
```

Change permissions mid-conversation. Useful for workflows where you want Claude to plan first, then execute.

**Parameters:**

| Parameter | Type | Options |
|-----------|------|---------|
| `mode` | `PermissionMode` | `"default"`, `"acceptEdits"`, `"plan"`, `"bypassPermissions"`, `"dontAsk"` |

**Usage:**

```python
async with ClaudeSDKClient(options=plan_options) as client:
    # Phase 1: Plan mode — Claude reads and plans, no edits
    await client.query("Analyze app.py and plan what changes to make")
    async for msg in client.receive_response():
        ...  # Claude proposes changes

    # Phase 2: Switch to execution mode
    await client.set_permission_mode("bypassPermissions")
    await client.query("Now execute the plan you just made")
    async for msg in client.receive_response():
        ...  # Claude makes the actual changes
```

**When to use:** "Preview before commit" workflows, progressive trust escalation.

**Only works with `ClaudeSDKClient`** — cannot do this with `query()`.

---

### 6.7 `set_model()`

```python
await client.set_model(model: str | None = None)
```

Switch to a different model mid-conversation. The conversation context is preserved.

**Usage:**

```python
async with ClaudeSDKClient(options=options) as client:
    # Use haiku for quick analysis (cheap)
    await client.set_model("haiku")
    await client.query("List all files in the project")
    async for msg in client.receive_response():
        ...

    # Switch to opus for complex refactoring (best quality)
    await client.set_model("opus")
    await client.query("Now refactor the authentication module")
    async for msg in client.receive_response():
        ...
```

**When to use:**
- Use cheap model (haiku) for simple tasks, expensive model (opus) for complex ones
- Start with fast model for exploration, switch to better model for execution

**Only works with `ClaudeSDKClient`** — cannot do this with `query()`.

---

### 6.8 `rewind_files()`

```python
await client.rewind_files(user_message_id: str)
```

Rewind all tracked files to their state at a specific point in the conversation. Like "undo" for file changes.

**Requires:**
- `enable_file_checkpointing=True` in options
- `extra_args={"replay-user-messages": None}` to get UserMessage UUIDs

**Usage:**

```python
options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
    allowed_tools=["Read", "Write", "Edit"],
    permission_mode="bypassPermissions",
    enable_file_checkpointing=True,
    extra_args={"replay-user-messages": None},
)

checkpoint_id = None

async with ClaudeSDKClient(options=options) as client:
    await client.query("Add error handling to app.py")
    async for msg in client.receive_response():
        if isinstance(msg, UserMessage) and msg.uuid:
            checkpoint_id = msg.uuid    # save checkpoint

    # Claude made changes, but you don't like them
    # Rewind files to before the changes
    if checkpoint_id:
        await client.rewind_files(checkpoint_id)
        print("Files rewound to checkpoint!")
```

**When to use:** When Claude makes changes you want to undo. Like git reset but within a conversation.

---

### 6.9 `get_mcp_status()`

```python
status = await client.get_mcp_status()
```

Get the connection status of all MCP servers.

**Returns:** `McpStatusResponse` — dict with `mcpServers` list.

**Each server has:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Server name |
| `status` | `str` | `"connected"`, `"pending"`, `"failed"`, `"needs-auth"`, `"disabled"` |
| `serverInfo` | `dict` | Server name/version (when connected) |
| `error` | `str` | Error message (when failed) |
| `tools` | `list` | Available tools (when connected) |

**Usage:**

```python
async with ClaudeSDKClient(options=options) as client:
    status = await client.get_mcp_status()

    for server in status["mcpServers"]:
        print(f"{server['name']}: {server['status']}")
        if server["status"] == "connected":
            tools = server.get("tools", [])
            print(f"  Tools: {[t['name'] for t in tools]}")
        elif server["status"] == "failed":
            print(f"  Error: {server.get('error')}")
```

**When to use:** Debugging MCP server connections, health checks, before using custom tools.

---

### 6.10 `reconnect_mcp_server()`

```python
await client.reconnect_mcp_server(server_name: str)
```

Retry connecting to a failed or disconnected MCP server.

**Usage:**

```python
# Check status first
status = await client.get_mcp_status()
for server in status["mcpServers"]:
    if server["status"] == "failed":
        await client.reconnect_mcp_server(server["name"])
        print(f"Reconnected {server['name']}")
```

**When to use:** When an MCP server fails during a conversation and you want to retry without restarting.

---

### 6.11 `toggle_mcp_server()`

```python
await client.toggle_mcp_server(server_name: str, enabled: bool)
```

Enable or disable an MCP server mid-conversation.

**Usage:**

```python
# Disable a server temporarily
await client.toggle_mcp_server("my-db-server", enabled=False)
await client.query("Do analysis without database access")
async for msg in client.receive_response():
    ...

# Re-enable it
await client.toggle_mcp_server("my-db-server", enabled=True)
await client.query("Now query the database")
async for msg in client.receive_response():
    ...
```

**When to use:** Temporarily restrict tool access during specific phases of a conversation.

---

### 6.12 `stop_task()`

```python
await client.stop_task(task_id: str)
```

Stop a running sub-agent task (spawned by the `Agent` tool).

**Usage:**

```python
from claude_agent_sdk import TaskStartedMessage, TaskNotificationMessage

async with ClaudeSDKClient(options=options) as client:
    await client.query("Run code review on all files")

    async for msg in client.receive_response():
        if isinstance(msg, TaskStartedMessage):
            task_id = msg.task_id
            print(f"Task started: {task_id}")

            # Stop it if taking too long
            await asyncio.sleep(30)
            await client.stop_task(task_id)

        elif isinstance(msg, TaskNotificationMessage):
            if msg.status == "stopped":
                print(f"Task {msg.task_id} was stopped")
```

**When to use:** Cancelling sub-agent tasks that are running too long or are no longer needed.

---

### 6.13 `get_server_info()`

```python
info = await client.get_server_info()
```

Get server initialization info including available commands and output styles.

**Returns:** `dict | None`

**Usage:**

```python
async with ClaudeSDKClient(options=options) as client:
    info = await client.get_server_info()
    if info:
        print(f"Commands: {len(info.get('commands', []))}")
        print(f"Output style: {info.get('output_style', 'default')}")
```

**When to use:** Rarely. For introspecting what the Claude Code CLI supports.

---

### 6.14 `disconnect()`

```python
await client.disconnect()
```

Close the connection and clean up the CLI subprocess.

**Usage:**

```python
# Automatic (recommended)
async with ClaudeSDKClient(options=options) as client:
    ...
# disconnect() called automatically

# Manual
client = ClaudeSDKClient(options=options)
await client.connect()
try:
    ...
finally:
    await client.disconnect()  # always disconnect in finally
```

**When to use:** Only with manual connect. `async with` handles this for you.

---

## 7. Message Types (What Comes Back)

Same message types as `query()`. The full reference is in [QUERY.md](QUERY.md#5-message-types-what-comes-back).

Quick summary:

| Type | What it is | When you see it |
|------|-----------|----------------|
| `AssistantMessage` | Claude's response (text + tool calls) | Every response |
| `ResultMessage` | Final summary (cost, turns, session_id) | End of each response |
| `UserMessage` | Your messages echoed back | When `replay-user-messages` is set |
| `SystemMessage` | Internal events | Task progress, notifications |
| `TaskStartedMessage` | Sub-agent task started | When `Agent` tool is used |
| `TaskProgressMessage` | Sub-agent progress | During sub-agent execution |
| `TaskNotificationMessage` | Sub-agent done/failed/stopped | After sub-agent completes |
| `StreamEvent` | Partial tokens | When `include_partial_messages=True` |
| `RateLimitEvent` | Rate limit warnings | Approaching or hitting limits |

**Standard message handling pattern:**

```python
async for msg in client.receive_response():
    if isinstance(msg, AssistantMessage):
        for block in msg.content:
            if isinstance(block, TextBlock):
                print(f"Claude: {block.text}")
            elif isinstance(block, ToolUseBlock):
                if block.name == "AskUserQuestion":
                    question = block.input.get("question", "")
                    answer = input(f"Claude asks: {question}\n> ")
                    await client.query(answer)
                else:
                    print(f"[Tool] {block.name}({block.input})")
    elif isinstance(msg, ResultMessage):
        print(f"Done: ${msg.total_cost_usd:.4f} | {msg.num_turns} turns")
```

---

## 8. Common Patterns

### Pattern 1: Simple Multi-Turn Conversation

```python
import asyncio
from claude_agent_sdk import (
    ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage,
    ResultMessage, TextBlock, ToolUseBlock,
)

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
    allowed_tools=["Read", "Glob"],
    permission_mode="bypassPermissions",
    max_turns=5,
)

async def main():
    async with ClaudeSDKClient(options=options) as client:
        # Turn 1
        await client.query("List all Python files in this project")
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        print(block.text)

        # Turn 2 — Claude remembers Turn 1
        await client.query("Which of those files has the most lines?")
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        print(block.text)

asyncio.run(main())
```

### Pattern 2: Human-in-the-Loop (AskUserQuestion)

```python
options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
    allowed_tools=["Read", "Glob", "AskUserQuestion"],
    permission_mode="bypassPermissions",
    max_turns=10,
)

async def main():
    async with ClaudeSDKClient(options=options) as client:
        await client.query(
            "List files in sample_data/ and ask the user which one to analyze."
        )

        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, ToolUseBlock):
                        if block.name == "AskUserQuestion":
                            question = block.input.get("question", "")
                            print(f"\nClaude asks: {question}")
                            answer = input("> Your answer: ")
                            await client.query(answer)
                        else:
                            print(f"[Tool] {block.name}")
                    elif isinstance(block, TextBlock):
                        print(block.text)

        # Second receive — get the response after user's answer
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        print(block.text)

asyncio.run(main())
```

### Pattern 3: Plan Then Execute

```python
options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
    allowed_tools=["Read", "Glob", "Grep", "Write", "Edit", "ExitPlanMode"],
    permission_mode="plan",          # start in plan mode
    max_turns=10,
)

async def main():
    async with ClaudeSDKClient(options=options) as client:
        # Phase 1: Plan (Claude can read but NOT write)
        await client.query("Analyze app.py and plan fixes for all bugs")
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        print(f"[PLAN] {block.text}")

        # User approves the plan
        approve = input("\nApprove this plan? (yes/no): ")
        if approve.lower() == "yes":
            # Phase 2: Execute (switch permissions)
            await client.set_permission_mode("bypassPermissions")
            await client.query("Execute the plan you just made")
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            print(f"[EXEC] {block.text}")

asyncio.run(main())
```

### Pattern 4: Model Switching (Cheap Analysis → Quality Execution)

```python
options = ClaudeAgentOptions(
    model="haiku",               # start cheap
    env={"ANTHROPIC_API_KEY": API_KEY},
    allowed_tools=["Read", "Glob", "Grep", "Write", "Edit"],
    permission_mode="bypassPermissions",
    max_turns=15,
)

async def main():
    async with ClaudeSDKClient(options=options) as client:
        # Phase 1: Quick analysis with haiku (fast + cheap)
        await client.query("Scan the codebase for TODO comments and security issues")
        async for msg in client.receive_response():
            ...

        # Phase 2: Switch to opus for complex refactoring
        await client.set_model("opus")
        await client.query("Now fix the critical security issues you found")
        async for msg in client.receive_response():
            ...

asyncio.run(main())
```

### Pattern 5: Interrupt Long-Running Task

```python
import asyncio

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
    allowed_tools=["Read", "Glob", "Grep", "Bash"],
    permission_mode="bypassPermissions",
    max_turns=50,
)

async def main():
    async with ClaudeSDKClient(options=options) as client:
        await client.query("Run comprehensive analysis on every file in the project")

        # Process messages but interrupt after 30 seconds
        start = asyncio.get_event_loop().time()

        async for msg in client.receive_response():
            elapsed = asyncio.get_event_loop().time() - start
            if elapsed > 30:
                print("Taking too long — interrupting!")
                await client.interrupt()
                # Continue receiving to get the final ResultMessage
                continue

            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        print(block.text[:200])  # truncate long text

            elif isinstance(msg, ResultMessage):
                print(f"Done: ${msg.total_cost_usd:.4f}")

asyncio.run(main())
```

### Pattern 6: File Checkpointing (Undo Changes)

```python
from claude_agent_sdk import UserMessage

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
    allowed_tools=["Read", "Write", "Edit"],
    permission_mode="bypassPermissions",
    max_turns=10,
    enable_file_checkpointing=True,
    extra_args={"replay-user-messages": None},
)

async def main():
    checkpoint = None

    async with ClaudeSDKClient(options=options) as client:
        await client.query("Refactor app.py to use async/await everywhere")
        async for msg in client.receive_response():
            if isinstance(msg, UserMessage) and msg.uuid:
                checkpoint = msg.uuid   # save this!
            elif isinstance(msg, AssistantMessage):
                ...
            elif isinstance(msg, ResultMessage):
                ...

        # Review the changes, decide you don't like them
        undo = input("Revert changes? (yes/no): ")
        if undo.lower() == "yes" and checkpoint:
            await client.rewind_files(checkpoint)
            print("Files rewound!")

asyncio.run(main())
```

### Pattern 7: MCP Server Health Check

```python
options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
    mcp_servers={"db": db_server, "api": api_server},
    allowed_tools=["mcp__db__*", "mcp__api__*"],
    permission_mode="bypassPermissions",
    max_turns=10,
)

async def main():
    async with ClaudeSDKClient(options=options) as client:
        # Check server health before using tools
        status = await client.get_mcp_status()
        for server in status["mcpServers"]:
            name = server["name"]
            state = server["status"]
            print(f"{name}: {state}")

            if state == "failed":
                print(f"  Reconnecting {name}...")
                await client.reconnect_mcp_server(name)

        # Now use the tools
        await client.query("Query the database for recent orders")
        async for msg in client.receive_response():
            ...

asyncio.run(main())
```

### Pattern 8: Interactive Chat Loop

```python
options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
    allowed_tools=["Read", "Glob", "Grep", "Write", "Edit", "Bash"],
    permission_mode="bypassPermissions",
    max_turns=10,
)

async def main():
    async with ClaudeSDKClient(options=options) as client:
        print("Chat with Claude (type 'exit' to quit)\n")

        while True:
            user_input = input("You: ").strip()
            if user_input.lower() == "exit":
                break
            if not user_input:
                continue

            await client.query(user_input)
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            print(f"Claude: {block.text}")
                        elif isinstance(block, ToolUseBlock):
                            print(f"  [used {block.name}]")
                elif isinstance(msg, ResultMessage):
                    print(f"  (${msg.total_cost_usd:.4f})\n")

asyncio.run(main())
```

---

## 9. Quick Reference Table

### All ClaudeSDKClient Methods

| # | Method | Returns | Description |
|---|--------|---------|-------------|
| 1 | `connect(prompt?)` | `None` | Start CLI process, establish connection |
| 2 | `query(prompt, session_id?)` | `None` | Send a message to Claude (non-blocking) |
| 3 | `receive_messages()` | `AsyncIterator[Message]` | Yield ALL messages (never stops) |
| 4 | `receive_response()` | `AsyncIterator[Message]` | Yield messages until ResultMessage (then stops) |
| 5 | `interrupt()` | `None` | Stop Claude mid-execution |
| 6 | `set_permission_mode(mode)` | `None` | Change permissions mid-conversation |
| 7 | `set_model(model)` | `None` | Switch model mid-conversation |
| 8 | `rewind_files(msg_id)` | `None` | Undo file changes to a checkpoint |
| 9 | `get_mcp_status()` | `McpStatusResponse` | Check MCP server connection status |
| 10 | `reconnect_mcp_server(name)` | `None` | Retry failed MCP connection |
| 11 | `toggle_mcp_server(name, bool)` | `None` | Enable/disable MCP server |
| 12 | `stop_task(task_id)` | `None` | Cancel a running sub-agent task |
| 13 | `get_server_info()` | `dict \| None` | Get CLI server capabilities |
| 14 | `disconnect()` | `None` | Close connection, cleanup |

### ClaudeSDKClient-Only Features (NOT available in query())

| Feature | Method | Use Case |
|---------|--------|----------|
| Multi-turn chat | `query()` multiple times | Chat apps, interactive workflows |
| Human-in-the-loop | Handle `AskUserQuestion` tool | User provides input mid-execution |
| Interrupt | `interrupt()` | Stop long-running tasks |
| Change model | `set_model()` | Cheap analysis → quality execution |
| Change permissions | `set_permission_mode()` | Plan → review → execute |
| File undo | `rewind_files()` | Revert unwanted changes |
| MCP management | `get_mcp_status()`, `reconnect_mcp_server()`, `toggle_mcp_server()` | Dynamic server control |
| Stop sub-agents | `stop_task()` | Cancel sub-agent tasks |

### Typical Usage Flow

```
1.  Create options         → ClaudeAgentOptions(model=..., env=..., ...)
2.  Create client          → ClaudeSDKClient(options=options)
3.  Connect                → async with client: (or await client.connect())
4.  Send first message     → await client.query("...")
5.  Receive response       → async for msg in client.receive_response(): ...
6.  Handle AskUserQuestion → if block.name == "AskUserQuestion": ... await client.query(answer)
7.  Receive again          → async for msg in client.receive_response(): ...
8.  Send follow-up         → await client.query("follow-up...")
9.  Receive response       → async for msg in client.receive_response(): ...
10. Disconnect             → automatic with async with
```

### Minimum Viable Client

```python
import asyncio
from claude_agent_sdk import (
    ClaudeSDKClient, ClaudeAgentOptions,
    AssistantMessage, ResultMessage, TextBlock,
)

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": "sk-..."},
    permission_mode="bypassPermissions",
    max_turns=5,
)

async def main():
    async with ClaudeSDKClient(options=options) as client:
        await client.query("Hello, Claude!")
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        print(block.text)
            elif isinstance(msg, ResultMessage):
                print(f"Cost: ${msg.total_cost_usd:.4f}")

asyncio.run(main())
```
