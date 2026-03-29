# Transport — Complete Reference

> The communication layer between your Python code and the Claude Code CLI.

---

## Table of Contents

1. [What is Transport?](#1-what-is-transport)
2. [How It Works (The Big Picture)](#2-how-it-works-the-big-picture)
3. [The Default: SubprocessCLITransport](#3-the-default-subprocessclitransport)
4. [The Transport Abstract Class](#4-the-transport-abstract-class)
5. [The Wire Protocol (JSON-Lines)](#5-the-wire-protocol-json-lines)
6. [Why Custom Transport?](#6-why-custom-transport)
7. [Use Case 1: Remote Agent Execution](#7-use-case-1-remote-agent-execution)
8. [Use Case 2: WebSocket for Web UIs](#8-use-case-2-websocket-for-web-uis)
9. [Use Case 3: Testing / Mocking](#9-use-case-3-testing--mocking)
10. [Use Case 4: Container / Cloud Hosting](#10-use-case-4-container--cloud-hosting)
11. [Use Case 5: SSH Tunnel](#11-use-case-5-ssh-tunnel)
12. [Use Case 6: Message Queue (Enterprise)](#12-use-case-6-message-queue-enterprise)
13. [Building a Custom Transport (Step-by-Step)](#13-building-a-custom-transport-step-by-step)
14. [Full Example: WebSocket Transport](#14-full-example-websocket-transport)
15. [Full Example: Mock Transport for Testing](#15-full-example-mock-transport-for-testing)
16. [Important Warnings](#16-important-warnings)
17. [Quick Reference](#17-quick-reference)

---

## 1. What is Transport?

Transport is the **communication pipe** between your Python code and the Claude Code CLI process. It handles:

- **Sending** your prompts and control messages to Claude
- **Receiving** Claude's responses, tool calls, and result messages
- **Managing** the connection lifecycle (connect, ready, close)

Think of it like a phone line:
- **Transport** = the phone line itself (how signals travel)
- **Your code** = you talking into the phone
- **Claude Code CLI** = the person on the other end

By default, the SDK uses `SubprocessCLITransport` which spawns the `claude` CLI as a local child process and talks to it via stdin/stdout. You never need to touch it.

---

## 2. How It Works (The Big Picture)

### Default Flow (Local — What You're Already Using)

```
Your Python App                     Local Machine
┌─────────────────┐               ┌──────────────────┐
│                  │   stdin       │                  │
│  query() or     │──(JSON)──────→│  claude CLI       │────→ Claude API
│  ClaudeSDKClient│               │  (subprocess)     │
│                  │   stdout      │                  │
│                  │←─(JSON)──────│                  │←──── Claude API
└─────────────────┘               └──────────────────┘
        ↑                                  ↑
        └── Your code                      └── SubprocessCLITransport
                                               (auto-created, you never see this)
```

### Remote Flow (Custom Transport)

```
Your Python App                     Remote Server
┌─────────────────┐               ┌──────────────────┐
│                  │  WebSocket    │                  │
│  query() or     │──(JSON)──────→│  Relay Server     │
│  ClaudeSDKClient│               │       ↓           │
│                  │  WebSocket    │  claude CLI       │────→ Claude API
│                  │←─(JSON)──────│  (subprocess)     │←──── Claude API
└─────────────────┘               └──────────────────┘
        ↑                                  ↑
        └── Your code                      └── Custom WebSocketTransport
                                               (you build this)
```

The key insight: **Transport only moves JSON messages back and forth.** It doesn't understand them. The SDK's `Query` class on top handles the actual protocol logic (initialization, permissions, hooks, MCP routing).

---

## 3. The Default: SubprocessCLITransport

This is what the SDK uses automatically. You never create it yourself.

### What It Does

1. **Finds** the `claude` CLI binary on your system
2. **Spawns** it as a subprocess with `anyio.open_process()`
3. **Writes** JSON messages to the CLI's stdin
4. **Reads** JSON messages from the CLI's stdout
5. **Handles** stderr output (debug logs, errors)
6. **Shuts down** gracefully (wait 5s → SIGTERM → SIGKILL)

### Key Details

| Property | Value |
|----------|-------|
| Communication | stdin/stdout pipes (JSON-lines) |
| Buffer size | 1MB default (`max_buffer_size` in options) |
| Min CLI version | 2.0.0 |
| Thread safety | Writes protected by `anyio.Lock` |
| Shutdown | Graceful: 5s wait → SIGTERM → SIGKILL |
| CLI search path | `~/.npm-global/bin/claude`, `/usr/local/bin/claude`, `~/.local/bin/claude`, `~/.claude/local/claude`, etc. |

### How It's Used Internally

```python
# In query() — auto-creates SubprocessCLITransport
async def query(*, prompt, options=None, transport=None):
    # If you don't pass transport, it creates one:
    client = InternalClient()
    async for message in client.process_query(prompt=prompt, options=options, transport=transport):
        yield message

# Inside InternalClient.process_query():
if transport is not None:
    chosen_transport = transport           # use YOUR custom transport
else:
    chosen_transport = SubprocessCLITransport(prompt=prompt, options=options)  # default
```

---

## 4. The Transport Abstract Class

To build a custom transport, you subclass this:

```python
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class Transport(ABC):
    """Abstract transport for Claude communication.

    WARNING: This internal API is exposed for custom transport implementations
    (e.g., remote Claude Code connections). The Claude Code team may change or
    remove this abstract class in any future release.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Start the connection.

        For subprocess: starts the process.
        For network: establishes the connection (WebSocket, HTTP, SSH).
        """
        pass

    @abstractmethod
    async def write(self, data: str) -> None:
        """Send raw data to Claude.

        Args:
            data: JSON string + newline (e.g., '{"type": "user", ...}\n')
        """
        pass

    @abstractmethod
    def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        """Receive parsed JSON messages from Claude.

        Yields:
            dict — each message is a parsed JSON object
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the connection and clean up."""
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        """Check if the transport is connected and ready.

        Returns:
            True if ready to send/receive messages
        """
        pass

    @abstractmethod
    async def end_input(self) -> None:
        """Signal end of input.

        For subprocess: closes stdin.
        For network: sends an end-of-stream signal.
        """
        pass
```

### The 6 Methods You Must Implement

| # | Method | When Called | What It Does |
|---|--------|-----------|-------------|
| 1 | `connect()` | Once, at startup | Open the connection |
| 2 | `write(data)` | Every message you send | Send JSON string to Claude |
| 3 | `read_messages()` | Continuously | Yield parsed JSON dicts from Claude |
| 4 | `close()` | Once, at shutdown | Clean up everything |
| 5 | `is_ready()` | Checked periodically | Return True if connection is live |
| 6 | `end_input()` | When input stream ends | Signal "no more messages" |

---

## 5. The Wire Protocol (JSON-Lines)

A custom transport doesn't need to understand the protocol — it just relays JSON messages. But here's what flows through it:

### Messages FROM Your Code TO Claude (outbound)

**User message:**
```json
{
  "type": "user",
  "message": {"role": "user", "content": "Read app.py and fix the bugs"},
  "parent_tool_use_id": null,
  "session_id": "default"
}
```

**Control: Initialize (sent once on connect):**
```json
{
  "type": "control_request",
  "request_id": "init-001",
  "request": {
    "subtype": "initialize",
    "hooks": null,
    "agents": null
  }
}
```

**Control: Permission response:**
```json
{
  "type": "control_response",
  "response": {
    "subtype": "success",
    "request_id": "perm-001",
    "response": {"behavior": "allow"}
  }
}
```

### Messages FROM Claude TO Your Code (inbound)

**Assistant message (text):**
```json
{
  "type": "assistant",
  "message": {
    "role": "assistant",
    "content": [{"type": "text", "text": "I'll read the file now."}]
  },
  "session_id": "abc-123"
}
```

**Assistant message (tool call):**
```json
{
  "type": "assistant",
  "message": {
    "role": "assistant",
    "content": [{
      "type": "tool_use",
      "id": "tu_001",
      "name": "Read",
      "input": {"file_path": "/path/to/app.py"}
    }]
  }
}
```

**Result message:**
```json
{
  "type": "result",
  "subtype": "result",
  "duration_ms": 5432,
  "duration_api_ms": 4100,
  "is_error": false,
  "num_turns": 3,
  "session_id": "abc-123",
  "total_cost_usd": 0.0234
}
```

**Control: Permission request (Claude asks to use a tool):**
```json
{
  "type": "control_request",
  "request_id": "perm-001",
  "request": {
    "subtype": "can_use_tool",
    "tool_name": "Bash",
    "input": {"command": "rm -rf /tmp/test"},
    "permission_suggestions": null
  }
}
```

### Format: JSON-Lines

Each message is a single line of JSON, terminated by `\n`. Multiple messages look like:

```
{"type": "user", ...}\n
{"type": "assistant", ...}\n
{"type": "result", ...}\n
```

Your custom transport just needs to:
1. **Send** these JSON strings (from `write()`)
2. **Receive** and **parse** them (in `read_messages()`)

---

## 6. Why Custom Transport?

The default `SubprocessCLITransport` has one limitation: **it requires the `claude` CLI to be installed locally.** Custom transports solve these scenarios:

| # | Use Case | Problem | Solution |
|---|----------|---------|----------|
| 1 | Remote execution | CLI can't run locally (no Node.js, no disk space, ARM device) | WebSocket/HTTP transport to remote server |
| 2 | Web UI | Browser needs to talk to Claude | WebSocket transport from backend to frontend |
| 3 | Testing | Don't want real API calls in tests | Mock transport with canned responses |
| 4 | Cloud/Container | CLI runs in a container, your app is outside | HTTP transport to container endpoint |
| 5 | SSH tunnel | Claude Code on a remote dev box | SSH transport piping stdin/stdout |
| 6 | Enterprise | Must go through message queue (Kafka, RabbitMQ) | Queue-based transport |

---

## 7. Use Case 1: Remote Agent Execution

**Problem:** You have a lightweight Python app (Lambda, edge function, mobile backend) that can't run Claude Code CLI locally. But you have a powerful server with Claude Code installed.

**Solution:** Run the CLI on the remote server, connect to it over WebSocket.

### Architecture

```
┌─────────────────┐         ┌─────────────────────────────┐
│  Your App        │         │  Remote Server (GPU box)     │
│  (Lambda/Edge)   │         │                              │
│                  │  WSS    │  ┌─────────────────────────┐ │
│  Python SDK      │────────→│  │  WebSocket Relay Server │ │
│  + WsTransport   │         │  │         ↓               │ │
│                  │←────────│  │  claude CLI (subprocess) │ │
└─────────────────┘         │  └─────────────────────────┘ │
                             └─────────────────────────────┘
```

### When This Makes Sense

- Your app runs on a platform that can't install `claude` CLI (serverless, containers without Node.js)
- You want to share one powerful machine running Claude Code across multiple clients
- Your codebase is on the remote server (huge repo, fast SSD)

### Related Projects

- [claude-agent-server](https://github.com/dzhng/claude-agent-server) — WebSocket server that wraps Claude Code CLI
- [claude-code-server](https://github.com/Kurogoma4D/claude-code-server) — Remote Claude Code over WebSocket

---

## 8. Use Case 2: WebSocket for Web UIs

**Problem:** You're building a web-based chat interface for Claude Code. The browser can't run the CLI, but your backend can.

**Solution:** Backend runs the SDK with a WebSocket transport that relays messages to/from the browser.

### Architecture

```
┌──────────┐    WebSocket    ┌──────────────┐   stdin/stdout   ┌────────────┐
│  Browser  │───────────────→│  FastAPI      │────────────────→│  claude    │
│  (React)  │               │  Backend      │                 │  CLI       │
│           │←──────────────│  + relay      │←────────────────│            │
└──────────┘                └──────────────┘                  └────────────┘
```

### Conceptual Backend Code

```python
from fastapi import FastAPI, WebSocket
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock

app = FastAPI()

@app.websocket("/chat")
async def chat(ws: WebSocket):
    await ws.accept()

    options = ClaudeAgentOptions(
        model="sonnet",
        env={"ANTHROPIC_API_KEY": API_KEY},
        allowed_tools=["Read", "Glob"],
        permission_mode="bypassPermissions",
        max_turns=5,
    )

    while True:
        # Receive user message from browser
        user_msg = await ws.receive_text()

        # Send to Claude via SDK (local subprocess)
        async for msg in query(prompt=user_msg, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        # Stream to browser
                        await ws.send_json({"type": "text", "text": block.text})
```

> Note: This example uses `query()` with default transport (subprocess). For a true custom transport, you'd build a WebSocket-based transport class instead.

### Related Projects

- [claude-code-web](https://github.com/vultuk/claude-code-web) — Browser-based UI for Claude Code

---

## 9. Use Case 3: Testing / Mocking

**Problem:** You want to unit test code that uses Claude Agent SDK without making real API calls (expensive, slow, non-deterministic).

**Solution:** A mock transport that returns canned responses.

### Why This is the Most Practical Use Case

- **No API costs** during testing
- **Deterministic** — same input = same output every time
- **Fast** — no network latency, no CLI startup
- **CI-friendly** — no API keys needed in CI pipeline

### Implementation

```python
import json
from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import Transport


class MockTransport(Transport):
    """Mock transport that returns pre-configured responses."""

    def __init__(self, responses: list[dict[str, Any]]):
        """
        Args:
            responses: List of JSON message dicts to yield.
                       Must include an init response + your test messages.
        """
        self._responses = responses
        self._ready = False
        self._write_log: list[str] = []   # record what was written

    async def connect(self) -> None:
        self._ready = True

    async def write(self, data: str) -> None:
        self._write_log.append(data)

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        # First, yield the initialization response
        yield {
            "type": "control_response",
            "response": {
                "subtype": "success",
                "request_id": "",
                "response": None,
            },
        }

        # Then yield configured responses
        for response in self._responses:
            yield response

    async def close(self) -> None:
        self._ready = False

    def is_ready(self) -> bool:
        return self._ready

    async def end_input(self) -> None:
        pass
```

### Using It in Tests

```python
import pytest
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage, TextBlock


@pytest.mark.asyncio
async def test_query_returns_expected_text():
    """Test that query() handles a text response correctly."""

    mock_responses = [
        # Assistant message
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "model": "claude-sonnet-4-20250514",
                "content": [{"type": "text", "text": "Hello! The answer is 42."}],
            },
            "session_id": "test-session",
        },
        # Result message (always last)
        {
            "type": "result",
            "subtype": "result",
            "duration_ms": 100,
            "duration_api_ms": 80,
            "is_error": False,
            "num_turns": 1,
            "session_id": "test-session",
            "total_cost_usd": 0.001,
        },
    ]

    transport = MockTransport(responses=mock_responses)
    options = ClaudeAgentOptions(permission_mode="bypassPermissions")

    messages = []
    async for msg in query(prompt="What is the answer?", options=options, transport=transport):
        messages.append(msg)

    # Verify we got the expected messages
    assert len(messages) == 2
    assert isinstance(messages[0], AssistantMessage)
    assert isinstance(messages[1], ResultMessage)

    # Verify content
    text_block = messages[0].content[0]
    assert isinstance(text_block, TextBlock)
    assert "42" in text_block.text

    # Verify result
    assert messages[1].total_cost_usd == 0.001
    assert messages[1].num_turns == 1
```

---

## 10. Use Case 4: Container / Cloud Hosting

**Problem:** You deploy Claude Code in a Docker container. Your application runs outside the container and needs to communicate with it.

**Solution:** Expose an HTTP endpoint from the container, build an HTTP transport.

### Architecture

```
┌─────────────────┐    HTTP/REST    ┌────────────────────────────┐
│  Your App        │───────────────→│  Docker Container           │
│                  │                │  ┌────────────────────────┐ │
│  Python SDK      │                │  │  FastAPI server         │ │
│  + HttpTransport │                │  │       ↓                 │ │
│                  │←──────────────│  │  claude CLI (subprocess)│ │
└─────────────────┘                │  └────────────────────────┘ │
                                    └────────────────────────────┘
```

### Conceptual Transport

```python
import json
import httpx
from claude_agent_sdk import Transport


class HttpTransport(Transport):
    """HTTP transport for container-hosted Claude Code."""

    def __init__(self, base_url: str, auth_token: str | None = None):
        self._base_url = base_url
        self._auth_token = auth_token
        self._client: httpx.AsyncClient | None = None
        self._ready = False
        self._session_id: str | None = None

    async def connect(self) -> None:
        headers = {}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=300.0,
        )
        # Create a session on the server
        resp = await self._client.post("/sessions")
        resp.raise_for_status()
        self._session_id = resp.json()["session_id"]
        self._ready = True

    async def write(self, data: str) -> None:
        await self._client.post(
            f"/sessions/{self._session_id}/messages",
            content=data,
            headers={"Content-Type": "application/json"},
        )

    async def read_messages(self):
        # SSE stream from the server
        async with self._client.stream(
            "GET", f"/sessions/{self._session_id}/stream"
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data:
                        yield json.loads(data)

    async def close(self) -> None:
        self._ready = False
        if self._client:
            if self._session_id:
                await self._client.delete(f"/sessions/{self._session_id}")
            await self._client.aclose()

    def is_ready(self) -> bool:
        return self._ready

    async def end_input(self) -> None:
        await self._client.post(f"/sessions/{self._session_id}/end")
```

### Official Guidance

Anthropic's [hosting docs](https://platform.claude.com/docs/en/agent-sdk/hosting) describe this pattern for containerized deployment. The container runs Claude Code CLI internally, and exposes HTTP/WebSocket endpoints for external consumers.

---

## 11. Use Case 5: SSH Tunnel

**Problem:** Claude Code is installed on a remote dev server. You want to control it from your local machine.

**Solution:** SSH into the remote machine and pipe stdin/stdout over the SSH connection.

### Conceptual Transport

```python
import asyncio
import json
from claude_agent_sdk import Transport


class SSHTransport(Transport):
    """SSH transport — run Claude Code on a remote machine."""

    def __init__(self, host: str, user: str, key_path: str, remote_cwd: str = "~"):
        self._host = host
        self._user = user
        self._key_path = key_path
        self._remote_cwd = remote_cwd
        self._process = None
        self._ready = False

    async def connect(self) -> None:
        # SSH into remote and run claude CLI in streaming mode
        self._process = await asyncio.create_subprocess_exec(
            "ssh",
            "-i", self._key_path,
            "-o", "StrictHostKeyChecking=no",
            f"{self._user}@{self._host}",
            f"cd {self._remote_cwd} && claude --output-format stream-json --verbose -p -",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._ready = True

    async def write(self, data: str) -> None:
        if self._process and self._process.stdin:
            self._process.stdin.write(data.encode())
            await self._process.stdin.drain()

    async def read_messages(self):
        if not self._process or not self._process.stdout:
            return
        buffer = ""
        while True:
            chunk = await self._process.stdout.read(4096)
            if not chunk:
                break
            buffer += chunk.decode()
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        pass  # skip non-JSON lines (SSH banners, etc.)

    async def close(self) -> None:
        self._ready = False
        if self._process:
            self._process.terminate()
            await self._process.wait()

    def is_ready(self) -> bool:
        return self._ready

    async def end_input(self) -> None:
        if self._process and self._process.stdin:
            self._process.stdin.close()
```

### Usage

```python
transport = SSHTransport(
    host="dev-server.example.com",
    user="abhishek",
    key_path="~/.ssh/id_rsa",
    remote_cwd="/home/abhishek/projects/my-app",
)

async for msg in query(prompt="Read app.py and fix bugs", options=options, transport=transport):
    ...
```

---

## 12. Use Case 6: Message Queue (Enterprise)

**Problem:** Enterprise environment requires all communication to go through a message broker (Kafka, RabbitMQ, Redis Streams) for audit, compliance, and reliability.

**Solution:** Transport that publishes/subscribes through the message queue.

### Architecture

```
┌─────────────┐    Publish    ┌───────────┐    Subscribe    ┌─────────────────┐
│  Your App    │─────────────→│  Redis     │───────────────→│  Worker Server   │
│  + QueueTx   │              │  Streams   │                │       ↓          │
│              │    Subscribe  │           │    Publish      │  claude CLI      │
│              │←─────────────│           │←───────────────│  (subprocess)    │
└─────────────┘               └───────────┘                └─────────────────┘
```

### Conceptual Pattern

```python
# Simplified — real implementation needs proper async Redis client

class RedisStreamTransport(Transport):
    def __init__(self, redis_url: str, session_id: str):
        self._redis_url = redis_url
        self._session_id = session_id
        self._inbound = f"claude:{session_id}:in"    # SDK writes here
        self._outbound = f"claude:{session_id}:out"   # Worker writes here

    async def write(self, data: str) -> None:
        await self._redis.xadd(self._inbound, {"data": data})

    async def read_messages(self):
        last_id = "0"
        while True:
            entries = await self._redis.xread(
                {self._outbound: last_id}, block=5000
            )
            for stream, messages in entries:
                for msg_id, fields in messages:
                    last_id = msg_id
                    yield json.loads(fields["data"])
```

### When This Makes Sense

- Compliance requires all AI interactions logged to a queue
- Multiple workers process Claude requests from a shared queue
- Retry logic — failed requests can be replayed from the queue
- Rate limiting at the queue level

---

## 13. Building a Custom Transport (Step-by-Step)

### Step 1: Subclass Transport

```python
from claude_agent_sdk import Transport

class MyTransport(Transport):
    async def connect(self) -> None: ...
    async def write(self, data: str) -> None: ...
    def read_messages(self): ...
    async def close(self) -> None: ...
    def is_ready(self) -> bool: ...
    async def end_input(self) -> None: ...
```

### Step 2: Handle the Init Handshake

The SDK sends an initialization control request immediately after `connect()`. Your transport's `read_messages()` must yield a success response:

```python
async def read_messages(self):
    # The SDK expects an init response first
    yield {
        "type": "control_response",
        "response": {
            "subtype": "success",
            "request_id": "",    # empty for init
            "response": None,
        },
    }
    # Then yield real messages...
```

### Step 3: Relay JSON-Lines Faithfully

Your transport doesn't need to parse or understand the messages. Just:
- `write()` → send the JSON string as-is
- `read_messages()` → parse incoming JSON strings, yield as dicts

### Step 4: Plug It In

```python
# With query()
transport = MyTransport(...)
async for msg in query(prompt="Hello", options=options, transport=transport):
    ...

# With ClaudeSDKClient
client = ClaudeSDKClient(options=options, transport=MyTransport(...))
async with client:
    await client.query("Hello")
    ...
```

### Step 5: Handle Cleanup

```python
async def close(self) -> None:
    self._ready = False
    # Close your connection (WebSocket, HTTP client, SSH process, etc.)
    # Release all resources
```

---

## 14. Full Example: WebSocket Transport

Complete, working example of a WebSocket-based custom transport:

```python
"""
WebSocket Transport for Claude Agent SDK.

Client-side transport that connects to a WebSocket relay server
which has Claude Code CLI running on the other end.

Requirements:
    pip install websockets
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import websockets

from claude_agent_sdk import Transport


class WebSocketTransport(Transport):
    """Connect to Claude Code CLI via a WebSocket relay server."""

    def __init__(self, url: str, auth_token: str | None = None):
        """
        Args:
            url: WebSocket server URL (e.g., "wss://my-server.com/claude")
            auth_token: Optional auth token sent as a header
        """
        self._url = url
        self._auth_token = auth_token
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._ready = False

    async def connect(self) -> None:
        """Open WebSocket connection to the relay server."""
        headers = {}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        self._ws = await websockets.connect(
            self._url,
            additional_headers=headers,
            max_size=10 * 1024 * 1024,   # 10MB max message size
            ping_interval=30,
            ping_timeout=10,
        )
        self._ready = True

    async def write(self, data: str) -> None:
        """Send a JSON-line message to the relay server."""
        if not self._ws:
            raise ConnectionError("Not connected")
        await self._ws.send(data)

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        """Receive and parse JSON messages from the relay server."""
        if not self._ws:
            raise ConnectionError("Not connected")

        try:
            async for raw_message in self._ws:
                # The relay server may send one or more JSON-lines per WebSocket frame
                for line in raw_message.strip().split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        pass  # skip non-JSON lines
        except websockets.ConnectionClosed:
            self._ready = False

    async def close(self) -> None:
        """Close the WebSocket connection."""
        self._ready = False
        if self._ws:
            await self._ws.close()
            self._ws = None

    def is_ready(self) -> bool:
        """Check if connected."""
        return self._ready and self._ws is not None

    async def end_input(self) -> None:
        """Signal end of input to the relay server."""
        if self._ws:
            await self._ws.send(json.dumps({"type": "end_input"}) + "\n")


# ── Usage ──

async def main():
    from claude_agent_sdk import (
        query, ClaudeAgentOptions, AssistantMessage, TextBlock, ResultMessage,
    )

    transport = WebSocketTransport(
        url="wss://my-claude-server.com/ws",
        auth_token="my-secret-token",
    )

    options = ClaudeAgentOptions(
        model="sonnet",
        # No env needed — credentials are on the remote server
        permission_mode="bypassPermissions",
        max_turns=5,
    )

    async for msg in query(prompt="What is 2 + 2?", options=options, transport=transport):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    print(block.text)
        elif isinstance(msg, ResultMessage):
            print(f"Cost: ${msg.total_cost_usd:.4f}")
```

---

## 15. Full Example: Mock Transport for Testing

Complete, working example for unit testing without API calls:

```python
"""
Mock Transport for testing Claude Agent SDK code.

Returns pre-configured responses without spawning CLI or calling APIs.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import Transport


class MockTransport(Transport):
    """Mock transport for unit testing."""

    def __init__(self, responses: list[dict[str, Any]]):
        """
        Args:
            responses: List of message dicts to yield after initialization.
                       Must end with a result message.
        """
        self._responses = responses
        self._ready = False
        self._writes: list[str] = []

    async def connect(self) -> None:
        self._ready = True

    async def write(self, data: str) -> None:
        self._writes.append(data)

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        # Init response (SDK expects this first)
        yield {
            "type": "control_response",
            "response": {
                "subtype": "success",
                "request_id": "",
                "response": None,
            },
        }
        # Your test responses
        for response in self._responses:
            yield response

    async def close(self) -> None:
        self._ready = False

    def is_ready(self) -> bool:
        return self._ready

    async def end_input(self) -> None:
        pass

    @property
    def writes(self) -> list[str]:
        """Access log of all messages sent via write()."""
        return self._writes

    @property
    def parsed_writes(self) -> list[dict[str, Any]]:
        """Access log of all messages, parsed as JSON."""
        return [json.loads(w) for w in self._writes if w.strip()]


# ── Helper: Build Common Responses ──

def make_text_response(text: str, session_id: str = "test") -> dict:
    """Create an assistant message with text content."""
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "model": "claude-sonnet-4-20250514",
            "content": [{"type": "text", "text": text}],
        },
        "session_id": session_id,
    }


def make_tool_call(tool_name: str, tool_input: dict, session_id: str = "test") -> dict:
    """Create an assistant message with a tool call."""
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "model": "claude-sonnet-4-20250514",
            "content": [{
                "type": "tool_use",
                "id": f"tu_{tool_name}_001",
                "name": tool_name,
                "input": tool_input,
            }],
        },
        "session_id": session_id,
    }


def make_result(
    cost: float = 0.001,
    turns: int = 1,
    session_id: str = "test",
    is_error: bool = False,
) -> dict:
    """Create a result message."""
    return {
        "type": "result",
        "subtype": "result",
        "duration_ms": 1000,
        "duration_api_ms": 800,
        "is_error": is_error,
        "num_turns": turns,
        "session_id": session_id,
        "total_cost_usd": cost,
    }


# ── Usage in Tests ──

# pytest test file
import pytest
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage, TextBlock


@pytest.mark.asyncio
async def test_simple_text_response():
    transport = MockTransport(responses=[
        make_text_response("The capital of France is Paris."),
        make_result(cost=0.002, turns=1),
    ])

    options = ClaudeAgentOptions(permission_mode="bypassPermissions")
    messages = []

    async for msg in query(prompt="What is the capital of France?", options=options, transport=transport):
        messages.append(msg)

    assert len(messages) == 2
    assert isinstance(messages[0], AssistantMessage)
    assert isinstance(messages[0].content[0], TextBlock)
    assert "Paris" in messages[0].content[0].text
    assert isinstance(messages[1], ResultMessage)
    assert messages[1].total_cost_usd == 0.002


@pytest.mark.asyncio
async def test_tool_use_response():
    transport = MockTransport(responses=[
        make_tool_call("Read", {"file_path": "/app.py"}),
        make_text_response("The file contains a Flask app."),
        make_result(cost=0.005, turns=2),
    ])

    options = ClaudeAgentOptions(permission_mode="bypassPermissions")
    texts = []

    async for msg in query(prompt="Read app.py", options=options, transport=transport):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    texts.append(block.text)

    assert any("Flask" in t for t in texts)


@pytest.mark.asyncio
async def test_writes_are_logged():
    transport = MockTransport(responses=[
        make_text_response("Hi!"),
        make_result(),
    ])

    options = ClaudeAgentOptions(permission_mode="bypassPermissions")

    async for _ in query(prompt="Hello", options=options, transport=transport):
        pass

    # Verify the prompt was sent
    assert len(transport.writes) > 0
```

---

## 16. Important Warnings

### The Transport API is Unstable

From the source code:

> **WARNING:** This internal API is exposed for custom transport implementations (e.g., remote Claude Code connections). The Claude Code team may change or remove this abstract class in any future release. Custom implementations must be updated to match interface changes.

**What this means:**
- Any custom transport you build may break when you upgrade `claude-agent-sdk`
- Pin your SDK version if you use custom transports: `claude-agent-sdk==0.1.51`
- Check release notes before upgrading

### No Official Remote Transport Exists

As of March 2026, Anthropic provides:
- `SubprocessCLITransport` — the only built-in transport
- `Transport` ABC — the extension point for custom implementations
- No official WebSocket, HTTP, or SSH transport

Community projects exist (claude-agent-server, claude-code-server) but are not maintained by Anthropic.

### Claude Code CLI Must Be On the Other End

Any transport — local or remote — ultimately connects to a Claude Code CLI process. The transport just changes HOW you connect to it, not WHAT you connect to.

```
Always: Your Code → Transport → Claude Code CLI → Claude API
                     ↑
                     This is what you're replacing
```

---

## 17. Quick Reference

### When to Use Which

| Scenario | Transport | Complexity |
|----------|-----------|-----------|
| Normal usage (learning, scripts, production) | Default (don't set it) | None |
| Unit testing without API calls | MockTransport | Low |
| CLI on a remote server | WebSocket / SSH transport | Medium |
| Web UI backend | WebSocket relay | Medium |
| Container/cloud hosting | HTTP transport | Medium |
| Enterprise with message queues | Queue transport | High |

### Decision Tree

```
Do you need a custom transport?

  Is the claude CLI installed locally?
    YES → Use default (don't set transport). DONE.
    NO  → Do you need it on a remote server?
      YES → Build WebSocket or SSH transport
      NO  → Are you writing tests?
        YES → Build MockTransport
        NO  → You probably don't need custom transport
```

### Transport Interface Summary

| Method | Purpose | Called |
|--------|---------|-------|
| `connect()` | Open the connection | Once at start |
| `write(data: str)` | Send JSON-line to Claude | Every outbound message |
| `read_messages()` | Yield JSON dicts from Claude | Continuous stream |
| `close()` | Cleanup resources | Once at end |
| `is_ready()` | Check connection state | Periodically |
| `end_input()` | Signal "no more input" | When input stream ends |

### For 99% of Users

**Ignore transport.** The default works. You only need custom transports for:
1. **Testing** (MockTransport)
2. **Remote execution** (WebSocket/SSH)
3. **Enterprise infrastructure** (queues, proxies)
