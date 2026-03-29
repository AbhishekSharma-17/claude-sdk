# FastAPI + Claude Agent SDK — Complete Integration Guide

> Build production agent backends using FastAPI as the API layer and Claude Agent SDK as the AI engine.

---

## Table of Contents

1. [Why FastAPI + Claude Agent SDK?](#1-why-fastapi--claude-agent-sdk)
2. [How They Connect — Architecture](#2-how-they-connect--architecture)
3. [Critical SDK Internals You Must Know](#3-critical-sdk-internals-you-must-know)
4. [Recommended Directory Structure](#4-recommended-directory-structure)
5. [Agent Definitions — Where & How](#5-agent-definitions--where--how)
6. [API Pattern 1: REST Endpoint (One-Shot)](#6-api-pattern-1-rest-endpoint-one-shot)
7. [API Pattern 2: SSE Streaming](#7-api-pattern-2-sse-streaming)
8. [API Pattern 3: WebSocket Multi-Turn Chat](#8-api-pattern-3-websocket-multi-turn-chat)
9. [API Pattern 4: Background Task Processing](#9-api-pattern-4-background-task-processing)
10. [Middleware & Production Concerns](#10-middleware--production-concerns)
11. [Concurrency & Resource Management](#11-concurrency--resource-management)
12. [Cost Tracking & Rate Limiting](#12-cost-tracking--rate-limiting)
13. [Error Handling Patterns](#13-error-handling-patterns)
14. [Health Checks & Monitoring](#14-health-checks--monitoring)
15. [Complete Example: Full Agent API Server](#15-complete-example-full-agent-api-server)
16. [Quick Reference](#16-quick-reference)

---

## 1. Why FastAPI + Claude Agent SDK?

| Concern | FastAPI Handles | Claude Agent SDK Handles |
|---------|----------------|--------------------------|
| HTTP/WebSocket routing | Yes | No |
| Request validation | Pydantic models | No |
| Authentication/Authorization | Depends() DI | No |
| Rate limiting | Middleware | No |
| AI agent execution | No | Yes — spawns Claude Code subprocess |
| Tool execution (Read, Write, Bash, etc.) | No | Yes — 20+ built-in tools |
| Multi-turn conversation | No | Yes — ClaudeSDKClient |
| Sub-agent orchestration | No | Yes — AgentDefinition |
| Streaming responses | SSE/WebSocket | AsyncIterator yields |

**The combination**: FastAPI is the HTTP interface your apps talk to. Claude Agent SDK is the AI engine that runs behind it. FastAPI handles everything about the request/response lifecycle. The SDK handles everything about Claude's reasoning, tool use, and agent orchestration.

---

## 2. How They Connect — Architecture

```
                    ┌─────────────────────────────────────────┐
                    │              Your FastAPI App            │
                    │                                         │
  HTTP Request ────>│  Router ──> Endpoint ──> Agent Service  │
                    │                              │          │
                    │                              v          │
                    │                     ┌──────────────┐    │
                    │                     │ query() or   │    │
                    │                     │ ClaudeSDK    │    │
                    │                     │ Client       │    │
                    │                     └──────┬───────┘    │
                    │                            │            │
                    └────────────────────────────┼────────────┘
                                                 │
                                    stdin/stdout (JSON-lines)
                                                 │
                                                 v
                                    ┌────────────────────────┐
                                    │   Claude Code CLI      │
                                    │   (subprocess)         │
                                    │                        │
                                    │  Claude API ←→ Tools   │
                                    └────────────────────────┘
```

**Data flow**:
1. Client sends HTTP request to FastAPI
2. FastAPI validates request (Pydantic), authenticates, rate-limits
3. Endpoint calls agent service layer
4. Agent service calls `query()` or uses `ClaudeSDKClient`
5. SDK spawns a Claude Code subprocess (or reuses one for ClaudeSDKClient)
6. Claude reasons, uses tools, returns results via JSON-lines over stdin/stdout
7. SDK parses messages, yields them back to your endpoint
8. FastAPI serializes response (JSON, SSE, or WebSocket frame)

---

## 3. Critical SDK Internals You Must Know

### Each `query()` call spawns a NEW subprocess

```python
# EVERY call to query() does this internally:
#   subprocess.Popen(["claude", ...], stdin=PIPE, stdout=PIPE)
#
# This means:
#   - 50-100MB RAM per concurrent query
#   - Process startup overhead (~200-500ms)
#   - No connection pooling exists
#   - No way to share a query() across requests
```

### ClaudeSDKClient cannot be shared across requests

```python
# WRONG — will cause race conditions
client = None  # shared global

@app.on_event("startup")
async def startup():
    global client
    client = ClaudeSDKClient(options=options)
    await client.connect()

@app.post("/chat")  # Two concurrent requests = broken
async def chat(msg: str):
    await client.query(msg)  # Race condition!
```

```python
# RIGHT — one client per WebSocket connection
@app.websocket("/chat")
async def chat(websocket: WebSocket):
    async with ClaudeSDKClient(options=options) as client:
        # This client belongs to THIS connection only
        await client.query(msg)
```

### Permission mode MUST be `bypassPermissions` for servers

```python
# If you use "default", Claude will try to prompt on stdin
# for tool permissions — but there's no human at the terminal.
# Result: deadlock. The subprocess hangs forever.

options = ClaudeAgentOptions(
    permission_mode="bypassPermissions",  # REQUIRED for server use
)
```

### Subprocess environment isolation

```python
# The subprocess inherits NOTHING from your FastAPI process env.
# You must explicitly pass everything via env={}

options = ClaudeAgentOptions(
    env={
        "ANTHROPIC_API_KEY": settings.anthropic_api_key,
        "HOME": "/tmp/agent-workdir",  # if needed
    },
)
```

---

## 4. Recommended Directory Structure

```
src/
├── agent_api/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app factory, lifespan
│   ├── config.py                # Settings (Pydantic BaseSettings)
│   │
│   ├── routers/                 # API endpoints
│   │   ├── __init__.py
│   │   ├── agents.py            # POST /agents/query, /agents/stream
│   │   ├── chat.py              # WebSocket /chat/{session_id}
│   │   ├── tasks.py             # POST /tasks, GET /tasks/{id}
│   │   └── health.py            # GET /health
│   │
│   ├── agents/                  # Agent configurations
│   │   ├── __init__.py
│   │   ├── registry.py          # Central agent registry
│   │   ├── base.py              # Base options factory
│   │   ├── code_reviewer.py     # Code review agent config
│   │   ├── backend_dev.py       # Backend development agent
│   │   └── planner.py           # Planning agent config
│   │
│   ├── services/                # Business logic layer
│   │   ├── __init__.py
│   │   ├── agent_service.py     # Wraps query()/ClaudeSDKClient
│   │   ├── session_service.py   # WebSocket session management
│   │   └── task_service.py      # Background task management
│   │
│   ├── models/                  # Pydantic request/response models
│   │   ├── __init__.py
│   │   ├── requests.py          # AgentQueryRequest, ChatMessage
│   │   ├── responses.py         # AgentResponse, StreamEvent
│   │   └── tasks.py             # TaskStatus, TaskResult
│   │
│   ├── middleware/               # FastAPI middleware
│   │   ├── __init__.py
│   │   ├── auth.py              # API key / JWT auth
│   │   ├── rate_limit.py        # Request rate limiting
│   │   ├── cost_tracker.py      # Per-user cost tracking
│   │   └── logging.py           # Request/response logging
│   │
│   ├── prompts/                 # System prompts (text files)
│   │   ├── code_reviewer.txt
│   │   ├── backend_dev.txt
│   │   └── planner.txt
│   │
│   └── skills/                  # Custom skills (markdown)
│       ├── python-patterns/
│       │   └── SKILL.md
│       └── api-design/
│           └── SKILL.md
│
├── tests/
│   ├── test_agents.py
│   ├── test_chat.py
│   └── test_tasks.py
│
├── pyproject.toml
├── .env
└── .env.example
```

**Why this structure?**

| Directory | Purpose |
|-----------|---------|
| `routers/` | Thin HTTP layer — validates input, calls services, returns responses |
| `agents/` | Agent configuration ONLY — ClaudeAgentOptions + AgentDefinition factories |
| `services/` | Business logic — wraps SDK calls, manages sessions, handles errors |
| `models/` | Pydantic models for API request/response validation |
| `middleware/` | Cross-cutting concerns — auth, rate limiting, cost tracking |
| `prompts/` | System prompts as text files — easy to edit without code changes |
| `skills/` | Custom skill markdown files for specialized agent behavior |

---

## 5. Agent Definitions — Where & How

### The Agent Registry Pattern

```python
# src/agent_api/agents/registry.py
"""Central registry for all agent configurations."""

from claude_agent_sdk import ClaudeAgentOptions, AgentDefinition
from agent_api.config import settings


def _base_options(**overrides) -> ClaudeAgentOptions:
    """Base options shared by all agents."""
    defaults = dict(
        env={"ANTHROPIC_API_KEY": settings.anthropic_api_key},
        permission_mode="bypassPermissions",
        max_budget_usd=settings.default_max_budget,
    )
    defaults.update(overrides)
    return ClaudeAgentOptions(**defaults)


# ── Agent Configurations ──────────────────────────────────────

AGENTS: dict[str, dict] = {
    "code-reviewer": {
        "description": "Reviews code for bugs, security, and best practices",
        "options_factory": lambda: _base_options(
            model="sonnet",
            system_prompt=_load_prompt("code_reviewer.txt"),
            allowed_tools=["Read", "Glob", "Grep"],
            max_turns=5,
        ),
    },
    "backend-dev": {
        "description": "Builds backend features with FastAPI",
        "options_factory": lambda: _base_options(
            model="sonnet",
            system_prompt=_load_prompt("backend_dev.txt"),
            allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
            max_turns=10,
            agents={
                "test-writer": AgentDefinition(
                    description="Writes pytest tests for new code",
                    prompt="Write comprehensive pytest tests.",
                    tools=["Read", "Write", "Bash"],
                    model="sonnet",
                    maxTurns=5,
                ),
            },
        ),
    },
    "planner": {
        "description": "Plans implementation without writing code",
        "options_factory": lambda: _base_options(
            model="sonnet",
            system_prompt=_load_prompt("planner.txt"),
            allowed_tools=["Read", "Glob", "Grep"],
            permission_mode="plan",
            max_turns=5,
        ),
    },
    "quick-answer": {
        "description": "Fast answers with no tools",
        "options_factory": lambda: _base_options(
            model="haiku",
            max_turns=1,
        ),
    },
}


def _load_prompt(filename: str) -> str:
    """Load a system prompt from the prompts directory."""
    from pathlib import Path
    prompt_dir = Path(__file__).parent.parent / "prompts"
    return (prompt_dir / filename).read_text()


def get_agent_options(agent_name: str) -> ClaudeAgentOptions:
    """Get options for a named agent. Raises KeyError if not found."""
    agent = AGENTS[agent_name]
    return agent["options_factory"]()


def list_agents() -> list[dict[str, str]]:
    """List all available agents with descriptions."""
    return [
        {"name": name, "description": cfg["description"]}
        for name, cfg in AGENTS.items()
    ]
```

### Why Factories (not instances)?

```python
# WRONG — shared mutable state
OPTIONS = ClaudeAgentOptions(model="sonnet", ...)  # Created once at import

# If two requests modify this object, they corrupt each other.
# Also, query() may mutate internal state.

# RIGHT — factory creates fresh instance per request
def get_options() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(model="sonnet", ...)  # New object each time
```

---

## 6. API Pattern 1: REST Endpoint (One-Shot)

**Use when**: Client sends a question, waits for complete answer, gets JSON back.

### Request/Response Models

```python
# src/agent_api/models/requests.py
from pydantic import BaseModel, Field


class AgentQueryRequest(BaseModel):
    """Request to query an agent."""
    agent: str = Field(..., description="Agent name from registry")
    prompt: str = Field(..., min_length=1, max_length=10000)
    max_budget_usd: float | None = Field(None, ge=0.001, le=10.0)
    model_override: str | None = Field(None, pattern="^(haiku|sonnet|opus)$")
    cwd: str | None = Field(None, description="Working directory for file tools")
```

```python
# src/agent_api/models/responses.py
from pydantic import BaseModel


class ToolCall(BaseModel):
    name: str
    input: dict


class AgentResponse(BaseModel):
    """Response from an agent query."""
    text: str
    tool_calls: list[ToolCall]
    cost_usd: float
    num_turns: int
    is_error: bool
    duration_seconds: float
```

### Router

```python
# src/agent_api/routers/agents.py
import time

from fastapi import APIRouter, HTTPException
from claude_agent_sdk import (
    query, AssistantMessage, ResultMessage, TextBlock, ToolUseBlock,
)

from agent_api.agents.registry import get_agent_options, list_agents
from agent_api.models.requests import AgentQueryRequest
from agent_api.models.responses import AgentResponse, ToolCall

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/")
async def get_available_agents():
    """List all available agents."""
    return list_agents()


@router.post("/query", response_model=AgentResponse)
async def query_agent(request: AgentQueryRequest):
    """Send a one-shot query to an agent and get the complete response."""
    try:
        options = get_agent_options(request.agent)
    except KeyError:
        raise HTTPException(404, f"Agent '{request.agent}' not found")

    # Apply per-request overrides
    if request.max_budget_usd:
        options.max_budget_usd = request.max_budget_usd
    if request.model_override:
        options.model = request.model_override
    if request.cwd:
        options.cwd = request.cwd

    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    cost = 0.0
    turns = 0
    is_error = False
    start = time.monotonic()

    async for msg in query(prompt=request.prompt, options=options):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    tool_calls.append(ToolCall(
                        name=block.name,
                        input=block.input,
                    ))

        elif isinstance(msg, ResultMessage):
            cost = msg.total_cost_usd
            turns = msg.num_turns
            is_error = msg.is_error

    return AgentResponse(
        text="\n".join(text_parts),
        tool_calls=tool_calls,
        cost_usd=cost,
        num_turns=turns,
        is_error=is_error,
        duration_seconds=round(time.monotonic() - start, 2),
    )
```

### How the client calls it

```bash
curl -X POST http://localhost:8000/agents/query \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "code-reviewer",
    "prompt": "Review the file src/main.py for security issues",
    "cwd": "/home/user/project"
  }'
```

```json
{
  "text": "I found 3 security issues in src/main.py:\n1. SQL injection...",
  "tool_calls": [
    {"name": "Read", "input": {"file_path": "/home/user/project/src/main.py"}}
  ],
  "cost_usd": 0.0034,
  "num_turns": 3,
  "is_error": false,
  "duration_seconds": 4.82
}
```

---

## 7. API Pattern 2: SSE Streaming

**Use when**: Client wants to see Claude's response as it's generated, token by token. Good for web UIs with typewriter effect.

### Router

```python
# src/agent_api/routers/agents.py (add to same router)
import json
from fastapi.responses import StreamingResponse
from claude_agent_sdk import query, AssistantMessage, ResultMessage, TextBlock, ToolUseBlock


@router.post("/stream")
async def stream_agent(request: AgentQueryRequest):
    """Stream agent response as Server-Sent Events."""
    try:
        options = get_agent_options(request.agent)
    except KeyError:
        raise HTTPException(404, f"Agent '{request.agent}' not found")

    if request.max_budget_usd:
        options.max_budget_usd = request.max_budget_usd
    if request.cwd:
        options.cwd = request.cwd

    async def event_generator():
        async for msg in query(prompt=request.prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        event = {"type": "text", "content": block.text}
                        yield f"data: {json.dumps(event)}\n\n"
                    elif isinstance(block, ToolUseBlock):
                        event = {
                            "type": "tool_call",
                            "name": block.name,
                            "input": block.input,
                        }
                        yield f"data: {json.dumps(event)}\n\n"

            elif isinstance(msg, ResultMessage):
                event = {
                    "type": "result",
                    "cost_usd": msg.total_cost_usd,
                    "num_turns": msg.num_turns,
                    "is_error": msg.is_error,
                }
                yield f"data: {json.dumps(event)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
```

### JavaScript client

```javascript
const eventSource = new EventSource('/agents/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    agent: 'backend-dev',
    prompt: 'Create a user registration endpoint',
  }),
});

// Note: EventSource only supports GET. For POST, use fetch with ReadableStream:
const response = await fetch('/agents/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ agent: 'backend-dev', prompt: '...' }),
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  const text = decoder.decode(value);
  for (const line of text.split('\n')) {
    if (line.startsWith('data: ')) {
      const data = line.slice(6);
      if (data === '[DONE]') return;
      const event = JSON.parse(data);
      if (event.type === 'text') {
        appendToChat(event.content);  // Typewriter effect
      }
    }
  }
}
```

---

## 8. API Pattern 3: WebSocket Multi-Turn Chat

**Use when**: Interactive conversation — user sends messages, Claude responds, user follows up. Like a chat interface.

### Session Management

```python
# src/agent_api/services/session_service.py
"""Manages ClaudeSDKClient sessions for WebSocket connections."""

import asyncio
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions


class SessionManager:
    """One ClaudeSDKClient per WebSocket connection."""

    def __init__(self):
        self._sessions: dict[str, ClaudeSDKClient] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def create_session(
        self, session_id: str, options: ClaudeAgentOptions
    ) -> ClaudeSDKClient:
        """Create and connect a new session."""
        client = ClaudeSDKClient(options=options)
        await client.connect()
        self._sessions[session_id] = client
        self._locks[session_id] = asyncio.Lock()
        return client

    def get_session(self, session_id: str) -> ClaudeSDKClient | None:
        return self._sessions.get(session_id)

    def get_lock(self, session_id: str) -> asyncio.Lock:
        return self._locks[session_id]

    async def destroy_session(self, session_id: str):
        """Disconnect and clean up a session."""
        client = self._sessions.pop(session_id, None)
        self._locks.pop(session_id, None)
        if client:
            await client.disconnect()

    @property
    def active_count(self) -> int:
        return len(self._sessions)


# Singleton — created in lifespan
session_manager = SessionManager()
```

### WebSocket Router

```python
# src/agent_api/routers/chat.py
import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from claude_agent_sdk import (
    AssistantMessage, ResultMessage, TextBlock, ToolUseBlock,
)

from agent_api.agents.registry import get_agent_options
from agent_api.services.session_service import session_manager

router = APIRouter(tags=["chat"])


@router.websocket("/chat/{agent_name}")
async def websocket_chat(websocket: WebSocket, agent_name: str):
    """Multi-turn chat over WebSocket. One ClaudeSDKClient per connection."""
    await websocket.accept()

    # Create a session for this connection
    session_id = str(uuid.uuid4())
    try:
        options = get_agent_options(agent_name)
    except KeyError:
        await websocket.send_json({"error": f"Agent '{agent_name}' not found"})
        await websocket.close()
        return

    client = await session_manager.create_session(session_id, options)

    await websocket.send_json({
        "type": "connected",
        "session_id": session_id,
        "agent": agent_name,
    })

    try:
        while True:
            # Wait for user message
            data = await websocket.receive_json()
            user_message = data.get("message", "")

            if not user_message:
                await websocket.send_json({"type": "error", "message": "Empty message"})
                continue

            # Handle special commands
            if data.get("action") == "interrupt":
                await client.interrupt()
                await websocket.send_json({"type": "interrupted"})
                continue

            if data.get("action") == "switch_model":
                new_model = data.get("model", "sonnet")
                await client.set_model(new_model)
                await websocket.send_json({
                    "type": "model_switched",
                    "model": new_model,
                })
                continue

            # Send message to Claude and stream response
            lock = session_manager.get_lock(session_id)
            async with lock:  # Prevent concurrent queries on same session
                await client.query(user_message)

                async for msg in client.receive_response():
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                await websocket.send_json({
                                    "type": "text",
                                    "content": block.text,
                                })
                            elif isinstance(block, ToolUseBlock):
                                await websocket.send_json({
                                    "type": "tool_call",
                                    "name": block.name,
                                    "input": block.input,
                                })

                    elif isinstance(msg, ResultMessage):
                        await websocket.send_json({
                            "type": "turn_complete",
                            "cost_usd": msg.total_cost_usd,
                            "num_turns": msg.num_turns,
                        })

    except WebSocketDisconnect:
        pass
    finally:
        await session_manager.destroy_session(session_id)
```

### JavaScript WebSocket client

```javascript
const ws = new WebSocket('ws://localhost:8000/chat/backend-dev');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  switch (data.type) {
    case 'connected':
      console.log(`Session: ${data.session_id}`);
      break;
    case 'text':
      appendToChat(data.content);
      break;
    case 'tool_call':
      showToolIndicator(data.name);
      break;
    case 'turn_complete':
      showCost(data.cost_usd);
      break;
  }
};

// Send a message
ws.send(JSON.stringify({ message: "Create a user model with email validation" }));

// Follow up (Claude remembers context!)
ws.send(JSON.stringify({ message: "Now add password hashing to it" }));

// Switch model mid-conversation
ws.send(JSON.stringify({ action: "switch_model", model: "opus" }));

// Interrupt current generation
ws.send(JSON.stringify({ action: "interrupt" }));
```

---

## 9. API Pattern 4: Background Task Processing

**Use when**: Long-running agent tasks (code generation, refactoring, analysis). Client submits task, polls for status, gets result later.

### Task Models

```python
# src/agent_api/models/tasks.py
from enum import Enum
from pydantic import BaseModel


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskCreate(BaseModel):
    agent: str
    prompt: str
    max_budget_usd: float = 1.0
    cwd: str | None = None


class TaskResult(BaseModel):
    task_id: str
    status: TaskStatus
    text: str | None = None
    cost_usd: float | None = None
    num_turns: int | None = None
    error: str | None = None
```

### Task Service

```python
# src/agent_api/services/task_service.py
import asyncio
import uuid

from claude_agent_sdk import query, AssistantMessage, ResultMessage, TextBlock

from agent_api.agents.registry import get_agent_options
from agent_api.models.tasks import TaskStatus, TaskResult


class TaskService:
    """Manages background agent tasks."""

    def __init__(self):
        self._tasks: dict[str, TaskResult] = {}
        self._semaphore = asyncio.Semaphore(5)  # Max 5 concurrent tasks

    def create_task(self, agent: str, prompt: str, **kwargs) -> str:
        task_id = str(uuid.uuid4())
        self._tasks[task_id] = TaskResult(
            task_id=task_id,
            status=TaskStatus.PENDING,
        )
        asyncio.create_task(self._run_task(task_id, agent, prompt, **kwargs))
        return task_id

    def get_task(self, task_id: str) -> TaskResult | None:
        return self._tasks.get(task_id)

    async def _run_task(
        self, task_id: str, agent: str, prompt: str, **kwargs
    ):
        self._tasks[task_id].status = TaskStatus.RUNNING

        async with self._semaphore:  # Limit concurrent subprocesses
            try:
                options = get_agent_options(agent)
                if kwargs.get("max_budget_usd"):
                    options.max_budget_usd = kwargs["max_budget_usd"]
                if kwargs.get("cwd"):
                    options.cwd = kwargs["cwd"]

                text_parts: list[str] = []
                cost = 0.0
                turns = 0

                async for msg in query(prompt=prompt, options=options):
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                text_parts.append(block.text)

                    elif isinstance(msg, ResultMessage):
                        cost = msg.total_cost_usd
                        turns = msg.num_turns

                self._tasks[task_id] = TaskResult(
                    task_id=task_id,
                    status=TaskStatus.COMPLETED,
                    text="\n".join(text_parts),
                    cost_usd=cost,
                    num_turns=turns,
                )

            except Exception as e:
                self._tasks[task_id] = TaskResult(
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    error=str(e),
                )


# Singleton
task_service = TaskService()
```

### Task Router

```python
# src/agent_api/routers/tasks.py
from fastapi import APIRouter, HTTPException

from agent_api.models.tasks import TaskCreate, TaskResult
from agent_api.services.task_service import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("/", response_model=dict)
async def create_task(request: TaskCreate):
    """Submit a background agent task. Returns task_id for polling."""
    task_id = task_service.create_task(
        agent=request.agent,
        prompt=request.prompt,
        max_budget_usd=request.max_budget_usd,
        cwd=request.cwd,
    )
    return {"task_id": task_id, "status": "pending"}


@router.get("/{task_id}", response_model=TaskResult)
async def get_task(task_id: str):
    """Check the status of a background task."""
    result = task_service.get_task(task_id)
    if not result:
        raise HTTPException(404, "Task not found")
    return result
```

### Client usage

```bash
# Submit task
curl -X POST http://localhost:8000/tasks/ \
  -H "Content-Type: application/json" \
  -d '{"agent": "backend-dev", "prompt": "Refactor the user module"}'
# Response: {"task_id": "abc-123", "status": "pending"}

# Poll for completion
curl http://localhost:8000/tasks/abc-123
# Response: {"task_id": "abc-123", "status": "running", ...}

# Later...
curl http://localhost:8000/tasks/abc-123
# Response: {"task_id": "abc-123", "status": "completed", "text": "...", "cost_usd": 0.05}
```

---

## 10. Middleware & Production Concerns

### Authentication

```python
# src/agent_api/middleware/auth.py
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from agent_api.config import settings

api_key_header = APIKeyHeader(name="X-API-Key")


async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """Verify API key and return the associated user/tenant ID."""
    # In production: look up in database
    if api_key not in settings.valid_api_keys:
        raise HTTPException(403, "Invalid API key")
    return settings.valid_api_keys[api_key]  # Returns user_id


# Use in routes:
# @router.post("/query")
# async def query_agent(request: ..., user_id: str = Depends(verify_api_key)):
```

### Request Logging Middleware

```python
# src/agent_api/middleware/logging.py
import time
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = structlog.get_logger()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - start

        await logger.ainfo(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(duration * 1000),
        )
        return response
```

### Timeout Wrapper

```python
# src/agent_api/services/agent_service.py
import asyncio
from fastapi import HTTPException
from claude_agent_sdk import query, ClaudeAgentOptions, Message


async def query_with_timeout(
    prompt: str,
    options: ClaudeAgentOptions,
    timeout_seconds: float = 120.0,
) -> list[Message]:
    """Run query() with a timeout. Raises 504 if exceeded."""
    messages: list[Message] = []

    async def _collect():
        async for msg in query(prompt=prompt, options=options):
            messages.append(msg)

    try:
        await asyncio.wait_for(_collect(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        raise HTTPException(504, f"Agent timed out after {timeout_seconds}s")

    return messages
```

---

## 11. Concurrency & Resource Management

### The Problem

Each `query()` spawns a subprocess using **50-100MB RAM**. If 100 users hit your API simultaneously, that's **5-10GB RAM** just for Claude subprocesses.

### Solution: Semaphore-Based Concurrency Limiting

```python
# src/agent_api/services/agent_service.py
import asyncio
from contextlib import asynccontextmanager

from agent_api.config import settings

# Global semaphore — limits concurrent Claude subprocesses
_agent_semaphore = asyncio.Semaphore(settings.max_concurrent_agents)  # e.g., 10


@asynccontextmanager
async def acquire_agent_slot():
    """Acquire a slot to run an agent. Blocks if at capacity."""
    try:
        await asyncio.wait_for(
            _agent_semaphore.acquire(),
            timeout=30.0,  # Wait max 30s for a slot
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            503,
            "Server at capacity. Try again later.",
            headers={"Retry-After": "30"},
        )
    try:
        yield
    finally:
        _agent_semaphore.release()


# Use in endpoints:
@router.post("/query")
async def query_agent(request: AgentQueryRequest):
    options = get_agent_options(request.agent)

    async with acquire_agent_slot():
        # Only N agents run simultaneously
        async for msg in query(prompt=request.prompt, options=options):
            ...
```

### Resource Budget Table

| Server RAM | Max Concurrent Agents | Recommended Semaphore |
|-----------|----------------------|----------------------|
| 2 GB | 10-15 | `Semaphore(10)` |
| 4 GB | 20-30 | `Semaphore(20)` |
| 8 GB | 40-60 | `Semaphore(40)` |
| 16 GB | 80-120 | `Semaphore(80)` |

---

## 12. Cost Tracking & Rate Limiting

### Per-User Cost Tracking

```python
# src/agent_api/middleware/cost_tracker.py
"""Track per-user API costs and enforce budgets."""

from datetime import datetime, timedelta
from collections import defaultdict


class CostTracker:
    """In-memory cost tracker. Use Redis/DB in production."""

    def __init__(self, daily_limit_usd: float = 5.0):
        self.daily_limit = daily_limit_usd
        self._costs: dict[str, list[tuple[datetime, float]]] = defaultdict(list)

    def record(self, user_id: str, cost_usd: float):
        self._costs[user_id].append((datetime.utcnow(), cost_usd))

    def get_daily_spend(self, user_id: str) -> float:
        cutoff = datetime.utcnow() - timedelta(days=1)
        return sum(
            cost for ts, cost in self._costs[user_id]
            if ts > cutoff
        )

    def check_budget(self, user_id: str) -> bool:
        """Returns True if user is within budget."""
        return self.get_daily_spend(user_id) < self.daily_limit


cost_tracker = CostTracker()


# Use in endpoints:
# After query completes and you have ResultMessage:
# cost_tracker.record(user_id, result_msg.total_cost_usd)
# if not cost_tracker.check_budget(user_id):
#     raise HTTPException(429, "Daily cost limit exceeded")
```

### Rate Limiting with slowapi

```python
# src/agent_api/middleware/rate_limit.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Use in routes:
# @router.post("/query")
# @limiter.limit("10/minute")
# async def query_agent(request: Request, body: AgentQueryRequest):
#     ...
```

---

## 13. Error Handling Patterns

```python
# src/agent_api/main.py — Global error handlers

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


app = FastAPI()


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled errors from agent execution."""

    # Claude subprocess errors
    if "claude" in str(exc).lower() or "subprocess" in str(exc).lower():
        return JSONResponse(
            status_code=502,
            content={
                "error": "agent_error",
                "message": "Agent execution failed. Please try again.",
                "detail": str(exc) if settings.debug else None,
            },
        )

    # API key errors
    if "ANTHROPIC_API_KEY" in str(exc):
        return JSONResponse(
            status_code=500,
            content={
                "error": "configuration_error",
                "message": "Agent service misconfigured.",
            },
        )

    # Default
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "message": "An unexpected error occurred."},
    )
```

### Per-Query Error Handling

```python
async def safe_query(prompt: str, options: ClaudeAgentOptions):
    """Query with comprehensive error handling."""
    try:
        results = []
        async for msg in query(prompt=prompt, options=options):
            results.append(msg)

            # Check for SDK-reported errors
            if isinstance(msg, ResultMessage) and msg.is_error:
                raise AgentExecutionError(
                    f"Agent reported error after {msg.num_turns} turns"
                )

        return results

    except asyncio.TimeoutError:
        raise HTTPException(504, "Agent execution timed out")
    except FileNotFoundError:
        raise HTTPException(500, "Claude CLI not found. Is it installed?")
    except PermissionError:
        raise HTTPException(500, "Cannot execute Claude CLI")
    except Exception as e:
        raise HTTPException(502, f"Agent failed: {type(e).__name__}")
```

---

## 14. Health Checks & Monitoring

```python
# src/agent_api/routers/health.py
import shutil
import asyncio

from fastapi import APIRouter
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

from agent_api.config import settings
from agent_api.services.session_service import session_manager
from agent_api.services.task_service import task_service

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Basic health check."""
    return {
        "status": "healthy",
        "active_sessions": session_manager.active_count,
        "pending_tasks": sum(
            1 for t in task_service._tasks.values()
            if t.status in ("pending", "running")
        ),
    }


@router.get("/health/deep")
async def deep_health_check():
    """Deep check — verifies Claude CLI works."""
    checks = {}

    # 1. CLI binary exists
    checks["cli_installed"] = shutil.which("claude") is not None

    # 2. API key configured
    checks["api_key_set"] = bool(settings.anthropic_api_key)

    # 3. Quick test query
    if checks["cli_installed"] and checks["api_key_set"]:
        try:
            options = ClaudeAgentOptions(
                model="haiku",
                env={"ANTHROPIC_API_KEY": settings.anthropic_api_key},
                max_turns=1,
                max_budget_usd=0.001,
                permission_mode="bypassPermissions",
            )
            async for msg in query(prompt="Say ok", options=options):
                if isinstance(msg, ResultMessage):
                    checks["claude_responding"] = not msg.is_error
        except Exception as e:
            checks["claude_responding"] = False
            checks["claude_error"] = str(e)
    else:
        checks["claude_responding"] = False

    all_ok = all(v is True for v in checks.values() if isinstance(v, bool))
    return {"status": "healthy" if all_ok else "degraded", "checks": checks}
```

---

## 15. Complete Example: Full Agent API Server

### App Factory with Lifespan

```python
# src/agent_api/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_api.routers import agents, chat, tasks, health
from agent_api.middleware.logging import RequestLoggingMiddleware
from agent_api.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    # Startup
    print(f"Agent API starting | Max concurrent: {settings.max_concurrent_agents}")
    yield
    # Shutdown — clean up all WebSocket sessions
    from agent_api.services.session_service import session_manager
    # Disconnect all active sessions
    for sid in list(session_manager._sessions.keys()):
        await session_manager.destroy_session(sid)
    print("All sessions cleaned up")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agent API",
        description="Production agent backend powered by Claude Agent SDK",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)

    # Routers
    app.include_router(agents.router)
    app.include_router(chat.router)
    app.include_router(tasks.router)
    app.include_router(health.router)

    return app


app = create_app()
```

### Settings

```python
# src/agent_api/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """App configuration from environment variables."""

    # Claude
    anthropic_api_key: str
    default_max_budget: float = 1.0
    max_concurrent_agents: int = 10

    # Server
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]

    # Auth
    valid_api_keys: dict[str, str] = {}  # key -> user_id mapping

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

### Run command

```bash
# Development
uv run uvicorn agent_api.main:app --reload --port 8000

# Production
uv run uvicorn agent_api.main:app --host 0.0.0.0 --port 8000 --workers 1
#                                                                 ^^^^^^^^
# IMPORTANT: Use workers=1 because agent state (sessions, tasks) is in-memory.
# For multi-worker, use Redis for session/task storage.
```

---

## 16. Quick Reference

### Which API Pattern to Use?

| Pattern | SDK Function | When to Use | Latency | Complexity |
|---------|-------------|-------------|---------|------------|
| REST | `query()` | One-shot questions, code review, analysis | High (wait for full response) | Low |
| SSE Streaming | `query()` | Web UIs, typewriter effect, progress | Low (first token fast) | Medium |
| WebSocket | `ClaudeSDKClient` | Chat, multi-turn, interactive sessions | Low (persistent connection) | High |
| Background Task | `query()` | Refactoring, long generation, batch jobs | N/A (async polling) | Medium |

### Decision Matrix

```
Need multi-turn conversation?
  YES → WebSocket + ClaudeSDKClient
  NO  → Need streaming?
          YES → SSE + query()
          NO  → Will it take > 30 seconds?
                  YES → Background Task + query()
                  NO  → REST + query()
```

### Key Rules

| Rule | Why |
|------|-----|
| Always `permission_mode="bypassPermissions"` | Prevents stdin deadlock on tool permission prompts |
| Use factory functions for options | Each request needs fresh ClaudeAgentOptions |
| Semaphore for concurrency | Each query() = subprocess = 50-100MB RAM |
| One ClaudeSDKClient per WebSocket | Client is NOT thread/task safe |
| Timeout all queries | Subprocess can hang; use `asyncio.wait_for()` |
| Track costs per user | `ResultMessage.total_cost_usd` for billing |
| Use `workers=1` or external state store | In-memory state lost with multiple workers |
| Pass API key via `env={}` | Subprocess inherits nothing from parent |

### Dependencies

```toml
# pyproject.toml
[project]
dependencies = [
    "claude-agent-sdk",
    "fastapi>=0.115",
    "uvicorn[standard]",
    "pydantic-settings>=2.0",
    "python-dotenv",
    "structlog",
    "slowapi",          # rate limiting (optional)
]
```

---

*This guide covers FastAPI + Claude Agent SDK integration from the SDK source (`query.py`, `client.py`, `types.py`, `transport/`) and production patterns. Each `query()` call spawns an isolated Claude Code subprocess — there is no connection pooling, shared state, or persistent process pool in the current SDK.*
