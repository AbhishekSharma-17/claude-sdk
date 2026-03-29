# Middleware & Proxy — Complete Reference

> Intercept, inspect, modify, and control everything flowing between your code and Claude.

---

## Table of Contents

1. [What is Middleware in Claude Agent SDK?](#1-what-is-middleware-in-claude-agent-sdk)
2. [The 3 Middleware Layers](#2-the-3-middleware-layers)
3. [Layer 1: Transport Wrappers (Wire Level)](#3-layer-1-transport-wrappers-wire-level)
4. [Layer 2: Hooks (Lifecycle Level)](#4-layer-2-hooks-lifecycle-level)
5. [Layer 3: can_use_tool (Permission Level)](#5-layer-3-can_use_tool-permission-level)
6. [Which Layer to Use?](#6-which-layer-to-use)
7. [Use Case: Audit Logging (Compliance)](#7-use-case-audit-logging-compliance)
8. [Use Case: Content Filtering (Security)](#8-use-case-content-filtering-security)
9. [Use Case: Cost Tracking & Budgeting](#9-use-case-cost-tracking--budgeting)
10. [Use Case: Metrics & Monitoring](#10-use-case-metrics--monitoring)
11. [Use Case: Rate Limiting](#11-use-case-rate-limiting)
12. [Use Case: Caching](#12-use-case-caching)
13. [Use Case: Input Transformation](#13-use-case-input-transformation)
14. [Use Case: Authentication & Multi-Tenancy](#14-use-case-authentication--multi-tenancy)
15. [Use Case: Load Balancing](#15-use-case-load-balancing)
16. [Use Case: Token Counting](#16-use-case-token-counting)
17. [Composing Multiple Middlewares](#17-composing-multiple-middlewares)
18. [Hooks Deep Dive — All 10 Events](#18-hooks-deep-dive--all-10-events)
19. [can_use_tool Deep Dive](#19-can_use_tool-deep-dive)
20. [Quick Reference](#20-quick-reference)

---

## 1. What is Middleware in Claude Agent SDK?

Middleware is **code that sits between your application and Claude**, intercepting messages as they flow back and forth. It can:

- **Log** every tool call for compliance/audit
- **Block** dangerous commands before they execute
- **Modify** tool inputs or outputs
- **Track** costs, tokens, and usage metrics
- **Cache** repeated queries to save money
- **Rate limit** to prevent abuse
- **Authenticate** and route requests in multi-tenant systems

```
Your App → [Middleware] → Claude Code CLI → Claude API
Your App ← [Middleware] ← Claude Code CLI ← Claude API
```

Unlike web frameworks (FastAPI, Express) where middleware is a first-class concept, Claude Agent SDK provides **three different interception points** at different levels of abstraction.

---

## 2. The 3 Middleware Layers

```
Your Application
        |
   ┌────┴──────────────────────────────────┐
   │  Layer 3: can_use_tool                │  ← Permission decisions
   │  (called when tool needs permission)   │     allow / deny / modify input
   ├───────────────────────────────────────┤
   │  Layer 2: Hooks                       │  ← Lifecycle events
   │  (PreToolUse, PostToolUse, etc.)      │     10 events, pattern matching
   ├───────────────────────────────────────┤
   │  Layer 1: Transport Wrapper           │  ← Raw JSON messages
   │  (wraps the stdin/stdout pipe)        │     full message interception
   └────┬──────────────────────────────────┘
        |
   Claude Code CLI → Claude API
```

| Layer | Level | What You See | Stability | Power |
|-------|-------|-------------|-----------|-------|
| **Transport** | Wire (raw JSON) | Every message, raw format | Unstable (internal API) | Highest |
| **Hooks** | Lifecycle (structured) | Tool calls, prompts, stops | Stable (first-class) | High |
| **can_use_tool** | Permission (semantic) | Tool permission requests | Stable (first-class) | Focused |

---

## 3. Layer 1: Transport Wrappers (Wire Level)

Transport wrappers use the **decorator pattern** — wrap an existing transport, intercept all messages.

### The Pattern

```python
from claude_agent_sdk import Transport

class MyMiddleware(Transport):
    """Wraps an inner transport to add behavior."""

    def __init__(self, inner: Transport):
        self._inner = inner       # the real transport

    async def connect(self) -> None:
        # Add behavior before/after connecting
        await self._inner.connect()

    async def write(self, data: str) -> None:
        # Intercept OUTBOUND messages (your code → Claude)
        await self._inner.write(data)

    async def read_messages(self):
        # Intercept INBOUND messages (Claude → your code)
        async for msg in self._inner.read_messages():
            yield msg

    async def close(self) -> None:
        await self._inner.close()

    def is_ready(self) -> bool:
        return self._inner.is_ready()

    async def end_input(self) -> None:
        await self._inner.end_input()
```

### How to Use It

```python
from claude_agent_sdk import query, ClaudeAgentOptions, ClaudeSDKClient
from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
    permission_mode="bypassPermissions",
)

# Create the real transport
inner = SubprocessCLITransport(prompt="Hello", options=options)

# Wrap it with middleware
transport = MyMiddleware(inner)

# Use with query()
async for msg in query(prompt="Hello", options=options, transport=transport):
    ...

# Or with ClaudeSDKClient
client = ClaudeSDKClient(options=options, transport=transport)
```

### Example: Logging Transport

```python
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import Transport

logger = logging.getLogger("claude.audit")


class LoggingTransport(Transport):
    """Logs every message flowing through the transport."""

    def __init__(self, inner: Transport) -> None:
        self._inner = inner

    async def connect(self) -> None:
        logger.info("CONNECT: Transport connecting")
        await self._inner.connect()
        logger.info("CONNECT: Transport ready")

    async def write(self, data: str) -> None:
        # Log outbound messages (truncate for readability)
        logger.debug("SEND >>> %s", data.strip()[:500])
        await self._inner.write(data)

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        async for message in self._inner.read_messages():
            # Log inbound messages
            msg_type = message.get("type", "unknown")
            logger.debug("RECV <<< [%s] %s", msg_type, json.dumps(message)[:500])
            yield message

    async def close(self) -> None:
        logger.info("CLOSE: Transport disconnecting")
        await self._inner.close()

    def is_ready(self) -> bool:
        return self._inner.is_ready()

    async def end_input(self) -> None:
        await self._inner.end_input()
```

### When to Use Transport Wrappers

- You need to see EVERY message (including control protocol messages)
- You want to cache, rate limit, or transform at the raw JSON level
- You're building a proxy that forwards messages to a remote CLI
- You need metrics on raw message counts, sizes, timing

### When NOT to Use

- You only care about tool calls → use Hooks instead
- You only care about permissions → use `can_use_tool` instead
- The Transport API is **unstable** — may break on SDK upgrades

---

## 4. Layer 2: Hooks (Lifecycle Level)

Hooks are the SDK's **first-class middleware system**. They fire at specific points in Claude's execution lifecycle and receive structured, typed data.

### How Hooks Work

1. You register hooks in `ClaudeAgentOptions.hooks`
2. The SDK sends hook configuration to the CLI during initialization
3. When an event fires, the CLI sends a control request to the SDK
4. The SDK invokes your callback with structured input
5. Your callback returns a response (allow, deny, modify, add context)
6. The SDK sends the response back to the CLI

### Basic Structure

```python
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

# Hook callback signature
async def my_hook(
    input_data: dict,          # structured event data
    tool_use_id: str | None,   # tool call ID (if applicable)
    context: dict,             # hook context (signal for future abort support)
) -> dict:                     # your response
    return {}                  # empty = allow, no modifications

options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [
            HookMatcher(
                matcher="Bash",                  # only match Bash tool (regex)
                hooks=[my_hook],                 # list of callbacks
                timeout=30.0,                    # timeout in seconds
            ),
            HookMatcher(
                matcher=None,                    # match ALL tools
                hooks=[another_hook],
            ),
        ],
        "PostToolUse": [
            HookMatcher(hooks=[post_hook]),      # all tools
        ],
    }
)
```

### HookMatcher Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `matcher` | `str \| None` | `None` | Regex pattern for tool names. `None` = match all. `"Bash\|Write"` = match Bash or Write. |
| `hooks` | `list[HookCallback]` | `[]` | List of async callbacks to invoke |
| `timeout` | `float \| None` | `None` (60s default) | Timeout per hook in seconds |

### What Hooks Receive (input_data)

**PreToolUse:**
```python
{
    "hook_event_name": "PreToolUse",
    "session_id": "abc-123",
    "transcript_path": "/path/to/transcript",
    "cwd": "/path/to/project",
    "tool_name": "Bash",
    "tool_input": {"command": "ls -la"},
    "tool_use_id": "tu_001",
    "agent_id": "...",        # if inside a sub-agent
    "agent_type": "...",       # agent type name
}
```

**PostToolUse:**
```python
{
    "hook_event_name": "PostToolUse",
    "tool_name": "Bash",
    "tool_input": {"command": "ls -la"},
    "tool_response": "file1.py\nfile2.py\n...",
    "tool_use_id": "tu_001",
    ...
}
```

**UserPromptSubmit:**
```python
{
    "hook_event_name": "UserPromptSubmit",
    "prompt": "Delete all test files",
    ...
}
```

### What Hooks Can Return

**Allow (do nothing):**
```python
return {}
```

**Block a tool call (PreToolUse):**
```python
return {
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": "Blocked by security policy",
    }
}
```

**Modify tool input (PreToolUse):**
```python
return {
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "updatedInput": {"command": "ls -la --color=never"},
    }
}
```

**Add context for Claude (any hook):**
```python
return {
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": "WARNING: This file is in a production directory.",
    }
}
```

**Block a user prompt (UserPromptSubmit):**
```python
return {
    "decision": "block",
    "reason": "Prompt contains injection attempt",
}
```

**Stop the entire session:**
```python
return {
    "continue_": False,
    "stopReason": "Budget exceeded",
}
```

**Run asynchronously (don't block Claude):**
```python
return {
    "async_": True,
    "asyncTimeout": 5000,  # ms
}
```

---

## 5. Layer 3: can_use_tool (Permission Level)

`can_use_tool` is a **single async callback** that the CLI invokes whenever a tool needs permission (not already in `allowed_tools` or `disallowed_tools`).

### How It Works

```
Claude wants to use "Bash" tool
    ↓
Is "Bash" in disallowed_tools? → YES → BLOCKED (callback never called)
    ↓ NO
Is "Bash" in allowed_tools? → YES → AUTO-APPROVED (callback never called)
    ↓ NO
Call can_use_tool("Bash", {...}, context) → your callback decides
```

### Signature

```python
from claude_agent_sdk import (
    PermissionResultAllow, PermissionResultDeny,
    ToolPermissionContext, PermissionUpdate,
)

async def my_permission_handler(
    tool_name: str,                      # "Bash", "Read", "Write", etc.
    tool_input: dict[str, Any],          # {"command": "ls -la", ...}
    context: ToolPermissionContext,       # {signal: None, suggestions: [...]}
) -> PermissionResultAllow | PermissionResultDeny:
    ...
```

### What You Can Return

**Allow:**
```python
return PermissionResultAllow()
```

**Allow with modified input:**
```python
return PermissionResultAllow(
    updated_input={"command": "ls -la --safe-mode"}
)
```

**Allow and update permission rules dynamically:**
```python
return PermissionResultAllow(
    updated_permissions=[
        PermissionUpdate(
            type="addRules",
            behavior="allow",
            rules=[PermissionRuleValue(tool_name="Bash", rule_content="ls *")],
            destination="session",
        )
    ]
)
```

**Deny:**
```python
return PermissionResultDeny(message="Not allowed by policy")
```

**Deny and stop the entire agent:**
```python
return PermissionResultDeny(
    message="Security violation detected",
    interrupt=True,     # stops the agent loop entirely
)
```

### Important Constraint

`can_use_tool` **requires streaming mode** (ClaudeSDKClient). It does NOT work with `query()` using a string prompt:

```python
# WORKS — ClaudeSDKClient is always streaming mode
client = ClaudeSDKClient(options=ClaudeAgentOptions(can_use_tool=handler))

# DOES NOT WORK — query() with string prompt
query(prompt="Hello", options=ClaudeAgentOptions(can_use_tool=handler))
# Raises: ValueError("can_use_tool callback requires streaming mode")
```

---

## 6. Which Layer to Use?

### Decision Table

| I want to... | Use |
|---|---|
| Log every tool call | Hooks (`PreToolUse` + `PostToolUse`) |
| Block dangerous bash commands | Hooks (`PreToolUse` matcher `"Bash"`) |
| Modify tool inputs before execution | Hooks (`PreToolUse` + `updatedInput`) or `can_use_tool` + `updated_input` |
| Filter user prompts for injection | Hooks (`UserPromptSubmit`) |
| Track costs and token usage | Transport wrapper or `ResultMessage` parsing |
| Cache repeated queries | Transport wrapper |
| Rate limit outbound messages | Transport wrapper |
| Dynamic permission decisions | `can_use_tool` |
| Add auth tokens to remote proxy | Transport wrapper |
| Monitor tool durations | Hooks (`PreToolUse` + `PostToolUse` with timing) |
| Load balance across CLI instances | Transport wrapper |
| Block specific file paths | `can_use_tool` |
| Count raw messages/bytes | Transport wrapper |

### Comparison

| Feature | Transport | Hooks | can_use_tool |
|---------|-----------|-------|-------------|
| **Sees all messages** | Yes | No (only hook events) | No (only permission requests) |
| **Can block tools** | Yes (drop messages) | Yes (deny) | Yes (deny) |
| **Can modify inputs** | Yes (rewrite JSON) | Yes (updatedInput) | Yes (updated_input) |
| **Can modify outputs** | Yes (rewrite JSON) | Limited (additionalContext) | No |
| **Pattern matching** | Manual | Built-in regex | Manual |
| **Multiple callbacks** | Manual composition | Built-in (list of hooks) | Single callback |
| **Works with query()** | Yes | Yes | No (streaming only) |
| **Works with Client** | Yes | Yes | Yes |
| **API stability** | Unstable (internal) | Stable (first-class) | Stable (first-class) |
| **Typed input** | Raw `dict` | Typed `HookInput` | `(str, dict, context)` |

### Rule of Thumb

```
Start with Hooks (they cover 80% of use cases)
    ↓ Not enough?
Use can_use_tool (for dynamic permission logic)
    ↓ Still not enough?
Use Transport wrappers (for full message interception)
```

---

## 7. Use Case: Audit Logging (Compliance)

Every tool call logged to a JSONL file for compliance audit.

```python
import json
import time
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, HookMatcher


class AuditLogger:
    """Compliance-grade audit logging — logs every tool call."""

    def __init__(self, log_path: str = "./audit.jsonl") -> None:
        self._log_path = Path(log_path)

    def _write(self, entry: dict[str, Any]) -> None:
        with self._log_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    async def on_tool_start(self, input_data, tool_use_id, context):
        """Log before every tool execution."""
        self._write({
            "event": "tool_start",
            "timestamp": time.time(),
            "tool": input_data.get("tool_name"),
            "input": input_data.get("tool_input"),
            "tool_use_id": tool_use_id,
            "session_id": input_data.get("session_id"),
            "cwd": input_data.get("cwd"),
            "agent_id": input_data.get("agent_id"),
        })
        return {}  # allow everything, just log

    async def on_tool_done(self, input_data, tool_use_id, context):
        """Log after every tool execution."""
        self._write({
            "event": "tool_done",
            "timestamp": time.time(),
            "tool": input_data.get("tool_name"),
            "tool_use_id": tool_use_id,
            "response_preview": str(input_data.get("tool_response", ""))[:500],
        })
        return {}

    async def on_tool_error(self, input_data, tool_use_id, context):
        """Log tool failures."""
        self._write({
            "event": "tool_error",
            "timestamp": time.time(),
            "tool": input_data.get("tool_name"),
            "tool_use_id": tool_use_id,
            "error": input_data.get("error"),
        })
        return {}

    async def on_prompt(self, input_data, tool_use_id, context):
        """Log every user prompt."""
        self._write({
            "event": "user_prompt",
            "timestamp": time.time(),
            "prompt": input_data.get("prompt"),
            "session_id": input_data.get("session_id"),
        })
        return {}


# ── Usage ──

audit = AuditLogger(log_path="./logs/audit.jsonl")

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
    allowed_tools=["Read", "Glob", "Grep", "Bash"],
    permission_mode="bypassPermissions",
    hooks={
        "PreToolUse": [HookMatcher(hooks=[audit.on_tool_start])],
        "PostToolUse": [HookMatcher(hooks=[audit.on_tool_done])],
        "PostToolUseFailure": [HookMatcher(hooks=[audit.on_tool_error])],
        "UserPromptSubmit": [HookMatcher(hooks=[audit.on_prompt])],
    },
)
```

**Output (`audit.jsonl`):**
```json
{"event": "user_prompt", "timestamp": 1711720000.0, "prompt": "Read app.py", "session_id": "abc-123"}
{"event": "tool_start", "timestamp": 1711720001.0, "tool": "Read", "input": {"file_path": "/app.py"}, "tool_use_id": "tu_001"}
{"event": "tool_done", "timestamp": 1711720002.0, "tool": "Read", "tool_use_id": "tu_001", "response_preview": "from flask import Flask..."}
```

---

## 8. Use Case: Content Filtering (Security)

Block dangerous commands and prompt injection attempts.

```python
import re

from claude_agent_sdk import ClaudeAgentOptions, HookMatcher


# ── Dangerous command patterns ──
BLOCKED_BASH_PATTERNS = [
    r"rm\s+-rf\s+/",               # rm -rf /
    r"rm\s+-rf\s+~",               # rm -rf ~
    r"DROP\s+TABLE",               # SQL injection
    r"DELETE\s+FROM.*WHERE\s+1",   # mass delete
    r"chmod\s+777",                # insecure permissions
    r"curl.*\|\s*(sh|bash)",       # pipe to shell
    r"eval\s*\(",                  # eval injection
    r"mkfs\.",                     # format disk
    r"dd\s+if=",                   # disk overwrite
    r">\s*/dev/sd",                # write to disk device
]

# ── Prompt injection patterns ──
INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous",
    "system prompt:",
    "you are now",
    "disregard your instructions",
    "override your rules",
]


async def bash_security_filter(input_data, tool_use_id, context):
    """Block dangerous bash commands."""
    command = input_data.get("tool_input", {}).get("command", "")

    for pattern in BLOCKED_BASH_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"BLOCKED: matches dangerous pattern '{pattern}'",
                }
            }
    return {}


async def write_path_filter(input_data, tool_use_id, context):
    """Block writes to sensitive directories."""
    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "") or tool_input.get("path", "")

    blocked_dirs = ["/etc", "/usr", "/System", "/var", ".env", ".ssh", "credentials"]
    for blocked in blocked_dirs:
        if blocked in file_path:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"BLOCKED: write to sensitive path '{blocked}'",
                }
            }
    return {}


async def prompt_injection_filter(input_data, tool_use_id, context):
    """Block prompt injection attempts."""
    prompt = input_data.get("prompt", "")

    for marker in INJECTION_PATTERNS:
        if marker.lower() in prompt.lower():
            return {
                "decision": "block",
                "reason": f"BLOCKED: potential injection attempt ({marker})",
            }
    return {}


# ── Usage ──

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
    allowed_tools=["Read", "Write", "Edit", "Bash", "Glob"],
    permission_mode="bypassPermissions",
    hooks={
        "PreToolUse": [
            HookMatcher(matcher="Bash", hooks=[bash_security_filter]),
            HookMatcher(matcher="Write|Edit", hooks=[write_path_filter]),
        ],
        "UserPromptSubmit": [
            HookMatcher(hooks=[prompt_injection_filter]),
        ],
    },
)
```

---

## 9. Use Case: Cost Tracking & Budgeting

Track cumulative costs across multiple queries and stop when budget is exceeded.

```python
from claude_agent_sdk import (
    ClaudeSDKClient, ClaudeAgentOptions, ResultMessage, AssistantMessage, TextBlock,
)


class CostTracker:
    """Tracks cumulative cost across multiple queries."""

    def __init__(self, budget_usd: float = 10.0) -> None:
        self.budget_usd = budget_usd
        self.total_cost_usd: float = 0.0
        self.query_count: int = 0
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0

    def track(self, result: ResultMessage) -> None:
        self.query_count += 1
        if result.total_cost_usd:
            self.total_cost_usd += result.total_cost_usd
        if result.usage:
            self.total_input_tokens += result.usage.get("input_tokens", 0)
            self.total_output_tokens += result.usage.get("output_tokens", 0)

    @property
    def remaining(self) -> float:
        return max(0, self.budget_usd - self.total_cost_usd)

    @property
    def over_budget(self) -> bool:
        return self.total_cost_usd >= self.budget_usd

    def report(self) -> str:
        return (
            f"Queries: {self.query_count} | "
            f"Cost: ${self.total_cost_usd:.4f} / ${self.budget_usd:.2f} | "
            f"Remaining: ${self.remaining:.4f} | "
            f"Tokens: {self.total_input_tokens:,} in / {self.total_output_tokens:,} out"
        )


# ── Usage ──

async def main():
    tracker = CostTracker(budget_usd=1.00)

    options = ClaudeAgentOptions(
        model="sonnet",
        env={"ANTHROPIC_API_KEY": API_KEY},
        allowed_tools=["Read", "Glob"],
        permission_mode="bypassPermissions",
        max_turns=5,
    )

    async with ClaudeSDKClient(options=options) as client:
        queries = [
            "List all Python files in the project",
            "Read the main app file and summarize it",
            "What dependencies does this project use?",
        ]

        for q in queries:
            if tracker.over_budget:
                print(f"BUDGET EXCEEDED — stopping")
                break

            await client.query(q)
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            print(block.text[:200])
                elif isinstance(msg, ResultMessage):
                    tracker.track(msg)
                    print(f"  [{tracker.report()}]\n")

    print(f"\nFinal: {tracker.report()}")
```

---

## 10. Use Case: Metrics & Monitoring

Collect tool usage metrics for dashboards (Grafana, DataDog, etc.).

```python
import time
from collections import defaultdict
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, HookMatcher


class MetricsCollector:
    """Collects tool usage metrics for monitoring."""

    def __init__(self) -> None:
        self.tool_counts: dict[str, int] = defaultdict(int)
        self.tool_durations: dict[str, list[float]] = defaultdict(list)
        self.tool_errors: dict[str, int] = defaultdict(int)
        self._start_times: dict[str, float] = {}

    async def on_pre_tool(self, input_data, tool_use_id, context):
        tool = input_data.get("tool_name", "unknown")
        self.tool_counts[tool] += 1
        if tool_use_id:
            self._start_times[tool_use_id] = time.monotonic()
        return {}

    async def on_post_tool(self, input_data, tool_use_id, context):
        tool = input_data.get("tool_name", "unknown")
        if tool_use_id and tool_use_id in self._start_times:
            duration = time.monotonic() - self._start_times.pop(tool_use_id)
            self.tool_durations[tool].append(duration)
        return {}

    async def on_tool_error(self, input_data, tool_use_id, context):
        tool = input_data.get("tool_name", "unknown")
        self.tool_errors[tool] += 1
        self._start_times.pop(tool_use_id, None)
        return {}

    def report(self) -> dict[str, Any]:
        return {
            "total_calls": sum(self.tool_counts.values()),
            "total_errors": sum(self.tool_errors.values()),
            "calls_by_tool": dict(self.tool_counts),
            "errors_by_tool": dict(self.tool_errors),
            "avg_duration_ms": {
                tool: round(sum(d) / len(d) * 1000, 1)
                for tool, d in self.tool_durations.items()
                if d
            },
        }


# ── Usage ──

metrics = MetricsCollector()

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
    allowed_tools=["Read", "Glob", "Grep", "Bash"],
    permission_mode="bypassPermissions",
    hooks={
        "PreToolUse": [HookMatcher(hooks=[metrics.on_pre_tool])],
        "PostToolUse": [HookMatcher(hooks=[metrics.on_post_tool])],
        "PostToolUseFailure": [HookMatcher(hooks=[metrics.on_tool_error])],
    },
)

# After session:
# print(json.dumps(metrics.report(), indent=2))
# {
#   "total_calls": 12,
#   "total_errors": 1,
#   "calls_by_tool": {"Read": 5, "Grep": 4, "Bash": 3},
#   "errors_by_tool": {"Bash": 1},
#   "avg_duration_ms": {"Read": 45.2, "Grep": 120.5, "Bash": 890.3}
# }
```

---

## 11. Use Case: Rate Limiting

Prevent too many messages in a short time (transport wrapper).

```python
import time
from collections.abc import AsyncIterator
from typing import Any

import anyio

from claude_agent_sdk import Transport


class RateLimitingTransport(Transport):
    """Enforces minimum interval between write() calls."""

    def __init__(self, inner: Transport, min_interval_sec: float = 0.5) -> None:
        self._inner = inner
        self._min_interval = min_interval_sec
        self._last_write: float = 0.0

    async def connect(self) -> None:
        await self._inner.connect()

    async def write(self, data: str) -> None:
        now = time.monotonic()
        elapsed = now - self._last_write
        if elapsed < self._min_interval:
            await anyio.sleep(self._min_interval - elapsed)
        self._last_write = time.monotonic()
        await self._inner.write(data)

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        async for msg in self._inner.read_messages():
            yield msg

    async def close(self) -> None:
        await self._inner.close()

    def is_ready(self) -> bool:
        return self._inner.is_ready()

    async def end_input(self) -> None:
        await self._inner.end_input()
```

---

## 12. Use Case: Caching

Cache responses to avoid repeat API calls for identical prompts.

```python
import hashlib
import json
from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import Transport


class CachingTransport(Transport):
    """Caches query responses keyed by prompt hash."""

    def __init__(self, inner: Transport) -> None:
        self._inner = inner
        self._cache: dict[str, list[dict[str, Any]]] = {}
        self._current_key: str | None = None
        self._cached_hit: list[dict[str, Any]] | None = None

    async def connect(self) -> None:
        await self._inner.connect()

    async def write(self, data: str) -> None:
        key = hashlib.sha256(data.encode()).hexdigest()
        if key in self._cache:
            self._cached_hit = self._cache[key]
            return  # skip real write — serve from cache
        self._current_key = key
        self._cached_hit = None
        await self._inner.write(data)

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        # Serve from cache if available
        if self._cached_hit is not None:
            for msg in self._cached_hit:
                yield msg
            return

        # Otherwise, read from real transport and cache
        collected: list[dict[str, Any]] = []
        async for msg in self._inner.read_messages():
            collected.append(msg)
            yield msg

        if self._current_key:
            self._cache[self._current_key] = collected

    async def close(self) -> None:
        await self._inner.close()

    def is_ready(self) -> bool:
        return self._inner.is_ready()

    async def end_input(self) -> None:
        await self._inner.end_input()

    @property
    def cache_size(self) -> int:
        return len(self._cache)
```

---

## 13. Use Case: Input Transformation

Automatically modify tool inputs before execution.

```python
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher


async def enforce_dry_run(input_data, tool_use_id, context):
    """Add --dry-run to destructive bash commands."""
    command = input_data.get("tool_input", {}).get("command", "")

    destructive_cmds = ["rm ", "mv ", "cp ", "chmod ", "chown "]
    for cmd in destructive_cmds:
        if command.startswith(cmd) and "--dry-run" not in command:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "updatedInput": {"command": f"{command} --dry-run"},
                    "additionalContext": "Dry-run enforced by middleware.",
                }
            }
    return {}


async def enforce_read_only_paths(input_data, tool_use_id, context):
    """Force Read tool to only access project directory."""
    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    project_dir = input_data.get("cwd", "")
    if file_path and not file_path.startswith(project_dir):
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"Read restricted to {project_dir}",
            }
        }
    return {}


async def add_warning_context(input_data, tool_use_id, context):
    """Add warning when tool response contains errors."""
    response = str(input_data.get("tool_response", ""))
    if "error" in response.lower() or "traceback" in response.lower():
        return {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": (
                    "WARNING: The previous command may have produced errors. "
                    "Check output carefully before proceeding."
                ),
            }
        }
    return {}


# ── Usage ──

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
    allowed_tools=["Read", "Bash", "Write"],
    permission_mode="bypassPermissions",
    hooks={
        "PreToolUse": [
            HookMatcher(matcher="Bash", hooks=[enforce_dry_run]),
            HookMatcher(matcher="Read", hooks=[enforce_read_only_paths]),
        ],
        "PostToolUse": [
            HookMatcher(matcher="Bash", hooks=[add_warning_context]),
        ],
    },
)
```

---

## 14. Use Case: Authentication & Multi-Tenancy

Add auth tokens and route by organization in a multi-tenant system.

```python
import json
from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import Transport


class AuthenticatedTransport(Transport):
    """Injects auth metadata into outbound messages for multi-tenant proxy."""

    def __init__(self, inner: Transport, user_id: str, org_id: str, auth_token: str) -> None:
        self._inner = inner
        self._user_id = user_id
        self._org_id = org_id
        self._auth_token = auth_token

    async def connect(self) -> None:
        await self._inner.connect()

    async def write(self, data: str) -> None:
        # Inject auth metadata into every outbound message
        try:
            parsed = json.loads(data.strip())
            parsed["_auth"] = {
                "user_id": self._user_id,
                "org_id": self._org_id,
                "token": self._auth_token,
            }
            data = json.dumps(parsed) + "\n"
        except json.JSONDecodeError:
            pass
        await self._inner.write(data)

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        async for msg in self._inner.read_messages():
            # Strip any auth metadata from inbound messages
            msg.pop("_auth", None)
            yield msg

    async def close(self) -> None:
        await self._inner.close()

    def is_ready(self) -> bool:
        return self._inner.is_ready()

    async def end_input(self) -> None:
        await self._inner.end_input()
```

---

## 15. Use Case: Load Balancing

Round-robin across multiple Claude Code CLI instances.

```python
import itertools
from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import Transport


class LoadBalancingTransport(Transport):
    """Round-robin load balancer across multiple transport backends."""

    def __init__(self, transports: list[Transport]) -> None:
        if not transports:
            raise ValueError("Need at least one transport")
        self._transports = transports
        self._cycle = itertools.cycle(range(len(transports)))
        self._active: Transport | None = None

    async def connect(self) -> None:
        for t in self._transports:
            await t.connect()
        self._active = self._transports[next(self._cycle)]

    async def write(self, data: str) -> None:
        if not self._active:
            raise RuntimeError("Not connected")
        await self._active.write(data)

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        if not self._active:
            raise RuntimeError("Not connected")
        async for msg in self._active.read_messages():
            yield msg

    async def close(self) -> None:
        for t in self._transports:
            await t.close()

    def is_ready(self) -> bool:
        return any(t.is_ready() for t in self._transports)

    async def end_input(self) -> None:
        if self._active:
            await self._active.end_input()
        # Rotate to next backend for next use
        idx = next(self._cycle)
        self._active = self._transports[idx]
```

---

## 16. Use Case: Token Counting

Track exact token usage at the transport level.

```python
import json
from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import Transport


class TokenCountingTransport(Transport):
    """Counts tokens from assistant message usage fields."""

    def __init__(self, inner: Transport) -> None:
        self._inner = inner
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.message_count: int = 0

    async def connect(self) -> None:
        await self._inner.connect()

    async def write(self, data: str) -> None:
        await self._inner.write(data)

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        async for msg in self._inner.read_messages():
            msg_type = msg.get("type")

            if msg_type == "assistant":
                usage = msg.get("message", {}).get("usage", {})
                self.input_tokens += usage.get("input_tokens", 0)
                self.output_tokens += usage.get("output_tokens", 0)
                self.message_count += 1

            elif msg_type == "result":
                usage = msg.get("usage", {})
                self.input_tokens += usage.get("input_tokens", 0)
                self.output_tokens += usage.get("output_tokens", 0)

            yield msg

    async def close(self) -> None:
        await self._inner.close()

    def is_ready(self) -> bool:
        return self._inner.is_ready()

    async def end_input(self) -> None:
        await self._inner.end_input()

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def report(self) -> str:
        return (
            f"Messages: {self.message_count} | "
            f"Input: {self.input_tokens:,} | "
            f"Output: {self.output_tokens:,} | "
            f"Total: {self.total_tokens:,}"
        )
```

---

## 17. Composing Multiple Middlewares

### Transport Stacking (Decorator Pattern)

Transport wrappers compose by nesting:

```python
# Stack: Logging → Rate Limiting → Token Counting → Real Transport
inner = SubprocessCLITransport(prompt="Hello", options=options)
token_counter = TokenCountingTransport(inner)
rate_limiter = RateLimitingTransport(token_counter, min_interval_sec=0.5)
transport = LoggingTransport(rate_limiter)

# Order matters! Messages flow:
# write():  Logging → Rate Limiting → Token Counting → Real
# read():   Real → Token Counting → Rate Limiting → Logging
```

### Hook Stacking (Built-in)

Hooks compose naturally — multiple matchers, multiple callbacks:

```python
options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [
            # Matcher 1: Security filter on Bash
            HookMatcher(matcher="Bash", hooks=[bash_security_filter, enforce_dry_run]),
            # Matcher 2: Path filter on Write/Edit
            HookMatcher(matcher="Write|Edit", hooks=[write_path_filter]),
            # Matcher 3: Audit log on ALL tools
            HookMatcher(hooks=[audit.on_tool_start]),
        ],
        "PostToolUse": [
            HookMatcher(hooks=[audit.on_tool_done, metrics.on_post_tool]),
        ],
        "PostToolUseFailure": [
            HookMatcher(hooks=[audit.on_tool_error, metrics.on_tool_error]),
        ],
        "UserPromptSubmit": [
            HookMatcher(hooks=[prompt_injection_filter]),
        ],
    }
)
```

### Full Production Stack

```python
# Transport layer
inner = SubprocessCLITransport(prompt="...", options=options)
transport = LoggingTransport(TokenCountingTransport(inner))

# Hook layer
audit = AuditLogger()
metrics = MetricsCollector()

options = ClaudeAgentOptions(
    model="sonnet",
    env={"ANTHROPIC_API_KEY": API_KEY},
    allowed_tools=["Read", "Glob", "Grep"],
    disallowed_tools=["Bash"],          # hard block bash
    permission_mode="bypassPermissions",
    max_turns=10,
    max_budget_usd=1.00,
    hooks={
        "PreToolUse": [
            HookMatcher(hooks=[audit.on_tool_start, metrics.on_pre_tool]),
        ],
        "PostToolUse": [
            HookMatcher(hooks=[audit.on_tool_done, metrics.on_post_tool]),
        ],
        "PostToolUseFailure": [
            HookMatcher(hooks=[audit.on_tool_error, metrics.on_tool_error]),
        ],
        "UserPromptSubmit": [
            HookMatcher(hooks=[prompt_injection_filter]),
        ],
    },
)
```

---

## 18. Hooks Deep Dive — All 10 Events

| # | Event | When | Can Block? | Can Modify Input? | Can Add Context? |
|---|-------|------|-----------|------------------|-----------------|
| 1 | `PreToolUse` | Before tool execution | Yes (`permissionDecision: "deny"`) | Yes (`updatedInput`) | Yes |
| 2 | `PostToolUse` | After tool success | No | No | Yes (`additionalContext`) |
| 3 | `PostToolUseFailure` | After tool failure | No | No | Yes (`additionalContext`) |
| 4 | `UserPromptSubmit` | User sends a prompt | Yes (`decision: "block"`) | No | Yes |
| 5 | `Stop` | Agent is stopping | No | No | No |
| 6 | `SubagentStart` | Sub-agent spawned | No | No | Yes |
| 7 | `SubagentStop` | Sub-agent finished | No | No | No |
| 8 | `PreCompact` | Before context compaction | No | No | No |
| 9 | `Notification` | Notification event | No | No | Yes |
| 10 | `PermissionRequest` | Permission needed | Yes (via `decision`) | No | No |

### Most Useful for Middleware

| Event | Use Case |
|-------|----------|
| `PreToolUse` | Security filtering, input validation, audit logging, dry-run enforcement |
| `PostToolUse` | Metrics collection, response logging, warning injection |
| `PostToolUseFailure` | Error tracking, alerting |
| `UserPromptSubmit` | Prompt injection filtering, input sanitization |

---

## 19. can_use_tool Deep Dive

### When It's Called

```
Priority: disallowed_tools > allowed_tools > can_use_tool > permission_mode

Tool "Bash" requested:
  1. In disallowed_tools? → BLOCKED (can_use_tool NOT called)
  2. In allowed_tools?    → APPROVED (can_use_tool NOT called)
  3. can_use_tool set?    → CALL IT (your callback decides)
  4. permission_mode?     → FALLBACK (default behavior)
```

### Unique Powers (Only can_use_tool Has These)

**1. Dynamic permission rules:**
```python
async def handler(tool_name, tool_input, context):
    # After first allow, auto-approve future Bash calls
    return PermissionResultAllow(
        updated_permissions=[
            PermissionUpdate(
                type="addRules",
                behavior="allow",
                rules=[PermissionRuleValue(tool_name="Bash")],
                destination="session",
            )
        ]
    )
```

**2. Interrupt the agent loop:**
```python
async def handler(tool_name, tool_input, context):
    if is_dangerous(tool_input):
        return PermissionResultDeny(
            message="Critical security violation",
            interrupt=True,   # STOPS THE ENTIRE AGENT
        )
    return PermissionResultAllow()
```

**3. Access to permission suggestions from CLI:**
```python
async def handler(tool_name, tool_input, context):
    # The CLI sends its own suggestions about what to allow
    suggestions = context.suggestions
    for suggestion in suggestions:
        print(f"CLI suggests: {suggestion}")
    return PermissionResultAllow()
```

---

## 20. Quick Reference

### Middleware Decision Matrix

| Need | Layer | Example |
|------|-------|---------|
| Block dangerous bash | Hooks (PreToolUse) | `permissionDecision: "deny"` |
| Log all tool calls | Hooks (Pre + Post) | Write to JSONL |
| Filter user prompts | Hooks (UserPromptSubmit) | `decision: "block"` |
| Modify tool inputs | Hooks (PreToolUse) | `updatedInput: {...}` |
| Track costs | ResultMessage parsing | `msg.total_cost_usd` |
| Count tokens | Transport wrapper | Parse usage from messages |
| Cache responses | Transport wrapper | Hash prompt → cache response |
| Rate limit | Transport wrapper | Sleep between writes |
| Auth / multi-tenant | Transport wrapper | Inject auth metadata |
| Load balance | Transport wrapper | Round-robin backends |
| Dynamic permissions | can_use_tool | Allow/deny based on context |
| Stop on security violation | can_use_tool | `interrupt=True` |

### Hook Return Cheat Sheet

```python
# Do nothing (allow)
return {}

# Block tool (PreToolUse only)
return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "why"}}

# Modify input (PreToolUse only)
return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": {new input dict}}}

# Add context (any hook)
return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "extra info for Claude"}}

# Block prompt (UserPromptSubmit only)
return {"decision": "block", "reason": "why"}

# Stop session
return {"continue_": False, "stopReason": "why stopping"}

# Async (don't block Claude)
return {"async_": True, "asyncTimeout": 5000}
```

### Transport Wrapper Template

```python
from claude_agent_sdk import Transport

class MyMiddleware(Transport):
    def __init__(self, inner: Transport):
        self._inner = inner

    async def connect(self):          await self._inner.connect()
    async def write(self, data):      await self._inner.write(data)      # intercept outbound
    async def read_messages(self):                                        # intercept inbound
        async for msg in self._inner.read_messages():
            yield msg
    async def close(self):            await self._inner.close()
    def is_ready(self):               return self._inner.is_ready()
    async def end_input(self):        await self._inner.end_input()
```
