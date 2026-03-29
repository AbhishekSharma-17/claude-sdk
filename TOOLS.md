# Claude Agent SDK — Complete Tool Reference

A complete, practical reference for all 17 built-in tools plus custom tools in the Claude Agent SDK. Keep this open while coding.

---

## Quick Reference Table

| # | Tool | Purpose | allowed_tools String | Best For |
|---|------|---------|----------------------|----------|
| 1 | **Read** | Read file/image contents | `"Read"` | Exploring files, reading docs |
| 2 | **Glob** | Find files by glob pattern | `"Glob"` | Discovering files, mass file discovery |
| 3 | **Grep** | Search file contents (regex) | `"Grep"` | Finding patterns, code search |
| 4 | **Write** | Create or overwrite files | `"Write"` | Generating new files, complete replacements |
| 5 | **Edit** | Replace specific text in files | `"Edit"` | Surgical fixes, targeted changes |
| 6 | **Bash** | Execute shell commands | `"Bash"` | Running scripts, system operations |
| 7 | **NotebookEdit** | Edit Jupyter notebook cells | `"NotebookEdit"` | Modifying notebooks in-place |
| 8 | **WebSearch** | Search the web for info | `"WebSearch"` | Research, finding URLs, latest info |
| 9 | **WebFetch** | Fetch and parse web content | `"WebFetch"` | Reading full articles, page content |
| 10 | **TodoWrite** | Manage task lists | `"TodoWrite"` | Multi-step work tracking, progress |
| 11 | **BashOutput** | Read output from background processes | `"BashOutput"` | Long-running tasks, monitoring |
| 12 | **KillBash** | Stop background shell processes | `"KillBash"` | Process cleanup, interrupts |
| 13 | **Agent** | Spawn subagents for parallel work | `"Agent"` | Parallel multi-specialist tasks |
| 14 | **AskUserQuestion** | Prompt user for input | `"AskUserQuestion"` | Interactive workflows, human-in-loop |
| 15 | **ExitPlanMode** | Request approval to execute | `"ExitPlanMode"` | Plan-before-execute workflows |
| 16 | **ListMcpResources** | List MCP server resources | `"ListMcpResources"` | Resource discovery from MCP servers |
| 17 | **ReadMcpResource** | Read MCP resource content | `"ReadMcpResource"` | Accessing MCP resource data |
| — | **Custom Tools** | User-defined via @tool() | `"mcp__<server>__<tool>"` | Domain-specific logic |

---

## Core Tools (7)

### 1. Read

**What it does:** Reads file contents. Supports text files, code, logs, images (PNG/JPG).

**Input Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | `str` | Yes | Absolute or relative path to file |
| `offset` | `int` | No | Start reading from line number (0-indexed) |
| `limit` | `int` | No | Number of lines to read (default: all) |

**When to use:**
- Phase 1: Load SQL files to analyze
- Phase 2: Read knowledge base documents
- Understanding file content before editing
- Reading configuration files
- Analyzing log files
- Examining image files (with full path)

**When NOT to use:**
- Don't use for huge files (>100MB) without offset/limit
- Don't use to write files (use Write instead)
- Don't use for binary files (only text/images supported)

**Configuration:**

```python
allowed_tools=["Read"]
```

**Example Claude call:**

```json
{
  "type": "tool_use",
  "id": "tooluse_123",
  "name": "Read",
  "input": {
    "file_path": "/path/to/file.py",
    "offset": 10,
    "limit": 50
  }
}
```

**Cost/Performance:** Minimal cost (just input tokens for file content). ~1-2ms per MB.

---

### 2. Glob

**What it does:** Find files matching a glob pattern (like shell globbing).

**Input Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pattern` | `str` | Yes | Glob pattern (e.g., `**/*.py`, `src/**/*.test.*`) |
| `path` | `str` | No | Directory to search (default: current directory) |

**Pattern examples:**

```
*.py              → all .py files in current dir only
**/*.py           → all .py files recursively (most common)
src/**/*.test.*   → all test files under src/
data/*            → all files in data/ (non-recursive)
**/*config*       → any file with "config" in name anywhere
```

**When to use:**
- Phase 1: Find all SQL files in a directory
- Discovering project structure
- Finding all files of a specific type
- Mass file discovery before processing
- Building file lists for analysis

**When NOT to use:**
- Don't use to search file CONTENTS (use Grep for that)
- Don't use for exact filename matching if you already know the path
- Avoid on very large directories (millions of files)

**Configuration:**

```python
allowed_tools=["Glob"]
```

**Example Claude call:**

```json
{
  "type": "tool_use",
  "name": "Glob",
  "input": {
    "pattern": "**/*.sql",
    "path": "/data/sql_files"
  }
}
```

**Cost/Performance:** Minimal. ~10-50ms depending on filesystem size.

---

### 3. Grep

**What it does:** Search file contents using regex patterns. Returns matching lines with file/line info.

**Input Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pattern` | `str` | Yes | Regex pattern (e.g., `"TODO\|FIXME"`, `"def \w+"`) |
| `path` | `str` | No | Directory to search (default: current) |
| `output_mode` | `str` | No | `"content"` (lines), `"files_with_matches"`, or `"count"` |
| `-i` | `bool` | No | Case-insensitive search |
| `-B` / `-A` / `-C` | `int` | No | Lines before/after/context |

**When to use:**
- Phase 1: Find all CREATE PROCEDURE patterns in SQL files
- Finding all TODO/FIXME/BUG comments
- Searching for function definitions
- Finding imports or dependencies
- Pattern-based code analysis
- Locating configuration keys

**When NOT to use:**
- Don't use for simple substring matching (Grep is regex-heavy)
- Don't use if you need exact line numbers (use Read instead)
- Don't use for binary file search

**Configuration:**

```python
allowed_tools=["Grep"]
```

**Example Claude call:**

```json
{
  "type": "tool_use",
  "name": "Grep",
  "input": {
    "pattern": "ERROR|WARN|TODO",
    "path": "/var/log",
    "output_mode": "content"
  }
}
```

**Regex syntax:** Full ripgrep regex support. Examples:
- `"def \w+"` → function definitions
- `"^\s*#"` → comments
- `"\d{4}-\d{2}-\d{2}"` → ISO dates
- `"(?:foo|bar)"` → non-capturing groups

**Cost/Performance:** Proportional to file count. ~50-500ms depending on dataset size.

---

### 4. Write

**What it does:** Create a new file OR overwrite an existing file completely.

**Input Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | `str` | Yes | Path where file will be created |
| `content` | `str` | Yes | Entire file content |

**Important:** Write COMPLETELY REPLACES files. No merging, no appending.

**When to use:**
- Phase 2: Generating new Python/PySpark files
- Creating configuration files from scratch
- Generating reports or output documents
- Initializing new files that don't exist
- Complete file regeneration

**When NOT to use:**
- Don't use to modify just one part of a file (use Edit instead)
- Don't use if file might contain user edits (use Edit for safety)
- Don't use for appending to logs (use Bash `>>` instead)

**Configuration:**

```python
allowed_tools=["Write"]
```

**Example Claude call:**

```json
{
  "type": "tool_use",
  "name": "Write",
  "input": {
    "file_path": "/output/generated_code.py",
    "content": "#!/usr/bin/env python3\n\ndef main():\n    print('Hello')\n"
  }
}
```

**Cost/Performance:** Cost = output tokens for file content. ~1-2ms to write.

---

### 5. Edit

**What it does:** Replace specific text in a file. Everything else stays unchanged.

**Input Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | `str` | Yes | Path to existing file |
| `old_string` | `str` | Yes | Exact text to find and replace |
| `new_string` | `str` | Yes | Replacement text |
| `replace_all` | `bool` | No | If True, replace ALL occurrences (default: first only) |

**Critical:** `old_string` must be an EXACT match including indentation, spacing, newlines.

**When to use:**
- Fixing a bug in one function
- Adding a single line to a config
- Updating documentation in code
- Renaming variables in targeted locations
- Adding error handling to specific functions

**When NOT to use:**
- Don't use for complete file rewrites (use Write instead)
- Don't use without reading the file first (need exact match)
- Don't use if `old_string` appears many times and you only want some (be specific!)

**Configuration:**

```python
allowed_tools=["Edit"]
```

**Example Claude call:**

```json
{
  "type": "tool_use",
  "name": "Edit",
  "input": {
    "file_path": "/src/auth.py",
    "old_string": "password = input(\"Enter password: \")\nif not password:\n    return False",
    "new_string": "password = input(\"Enter password: \")\nif not password:\n    logger.warning(\"Empty password attempt\")\n    return False"
  }
}
```

**Best practice:** If `old_string` appears multiple times, include surrounding context:

```json
{
  "old_string": "def login(user, password):\n    if not password:\n        return False",
  "new_string": "def login(user, password):\n    if not password:\n        logger.warning(\"Empty password attempt\")\n        return False"
}
```

**Cost/Performance:** Proportional to file size. ~1-5ms for typical edits.

---

### 6. Bash

**What it does:** Execute arbitrary shell commands on the system.

**Input Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `command` | `str` | Yes | Shell command(s) to execute |
| `run_in_background` | `bool` | No | If True, returns PID and doesn't wait (use BashOutput to poll) |

**POWERFUL AND RISKY** — Claude can run anything: pip install, git, Python, etc.

**When to use:**
- Running test suites
- Building/compiling code
- Starting development servers
- System operations (copying, removing files)
- Running Python scripts
- Git operations
- Package management

**When NOT to use:**
- Don't use in production without restrictions (use sandbox or disallowed_tools)
- Don't give Bash access for untrusted prompts
- Don't use for simple file operations (use Read/Write/Edit instead)
- Avoid on servers with sensitive data

**Configuration:**

```python
# Allow Bash
allowed_tools=["Bash"]

# Restrict to specific commands
sandbox={
    "timeout_seconds": 30,
    "allowed_commands": ["python", "pip", "ls", "cat"]
}

# Block Bash entirely
disallowed_tools=["Bash"]
```

**Example Claude call:**

```json
{
  "type": "tool_use",
  "name": "Bash",
  "input": {
    "command": "python3 -m pytest tests/ -v --tb=short",
    "run_in_background": false
  }
}
```

**Background usage:**

```json
{
  "type": "tool_use",
  "name": "Bash",
  "input": {
    "command": "python3 long_task.py",
    "run_in_background": true
  }
}
```

Returns: `{"pid": 12345, "status": "started"}`

Then use BashOutput and KillBash to manage it.

**Cost/Performance:** Varies wildly. Execution time = token cost. 10-second command = ~30 output tokens.

---

### 7. NotebookEdit

**What it does:** Edit Jupyter notebook cells directly without raw JSON manipulation.

**Input Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `notebook_path` | `str` | Yes | Path to .ipynb file |
| `cell_number` | `int` | Yes | Cell index (0-based) |
| `new_source` | `str` | Yes | New cell content |
| `cell_type` | `str` | No | `"code"` or `"markdown"` (inferred if omitted) |
| `insert_after` | `int` | No | Insert new cell after this cell number |

**When to use:**
- Fixing bugs in notebook code cells
- Updating markdown explanations
- Adding new cells with results
- Cleaning up analysis notebooks
- Automating notebook generation

**When NOT to use:**
- Don't use for massive notebook rewrites (too fragile)
- Don't use if you're not sure of cell structure
- Avoid modifying notebooks with complex cell references

**Configuration:**

```python
allowed_tools=["NotebookEdit"]
```

**Example Claude call (edit existing cell):**

```json
{
  "type": "tool_use",
  "name": "NotebookEdit",
  "input": {
    "notebook_path": "/analysis.ipynb",
    "cell_number": 3,
    "new_source": "result = df.groupby('category').sum()\nprint(result)",
    "cell_type": "code"
  }
}
```

**Example Claude call (add new cell):**

```json
{
  "type": "tool_use",
  "name": "NotebookEdit",
  "input": {
    "notebook_path": "/analysis.ipynb",
    "insert_after": 5,
    "new_source": "## Analysis Complete\nAll data validated and processed.",
    "cell_type": "markdown"
  }
}
```

**Cost/Performance:** ~5-10ms per edit. Minimal token cost.

---

## Extended Tools (10)

### 8. WebSearch

**What it does:** Search the web for live, up-to-date information (not from training data).

**Input Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | `str` | Yes | Search query (e.g., "Claude API pricing 2026") |

**When to use:**
- Finding latest package versions
- Checking current API pricing
- Researching recent news or events
- Looking up information beyond Aug 2025 training cutoff
- Discovering URLs to fetch next

**When NOT to use:**
- Don't use for internal documentation (use Read instead)
- Don't use if you already have the information
- Avoid excessive searches (each search = token cost)

**Configuration:**

```python
allowed_tools=["WebSearch"]
```

**Example Claude call:**

```json
{
  "type": "tool_use",
  "name": "WebSearch",
  "input": {
    "query": "claude-agent-sdk latest version PyPI 2026"
  }
}
```

**Returns:** List of search results with titles, snippets, URLs.

**Cost/Performance:** High token cost. Each search = ~50-100 output tokens per result. ~500ms latency.

**Common pattern:** Use WebSearch to find URLs, then WebFetch to read them.

---

### 9. WebFetch

**What it does:** Fetch the full content of a specific URL you already know.

**Input Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | `str` | Yes | Full HTTP(S) URL to fetch |

**When to use:**
- Reading documentation pages
- Fetching API reference docs
- Reading blog posts or articles
- Scraping specific web pages
- Getting full content after WebSearch found the URL

**When NOT to use:**
- Don't use without a specific URL (use WebSearch first)
- Don't use for large binaries (only text pages)
- Don't use to bypass robots.txt (respect site policies)

**Configuration:**

```python
allowed_tools=["WebFetch"]
```

**Example Claude call:**

```json
{
  "type": "tool_use",
  "name": "WebFetch",
  "input": {
    "url": "https://platform.claude.com/docs/en/agent-sdk/overview"
  }
}
```

**Returns:** Full page content (HTML cleaned to readable text).

**Cost/Performance:** Moderate cost. Page content = input tokens. ~1-2 seconds per fetch.

**Pattern combo:**

```python
allowed_tools=["WebSearch", "WebFetch"]

# Claude flow:
# 1. WebSearch("find documentation") → gets URLs
# 2. WebFetch(url) → reads full content
# 3. Analyze and answer
```

---

### 10. TodoWrite

**What it does:** Manage a task list. Claude updates it as it works (pending → in_progress → completed).

**Input Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `todos` | `list[TodoItem]` | Yes | Array of todo items with id, content, status, priority |

**TodoItem structure:**

```python
{
    "id": "todo-1",                    # unique ID
    "content": "Read database schema",  # task description
    "status": "completed",              # "pending" | "in_progress" | "completed"
    "priority": "high"                  # "high" | "medium" | "low"
}
```

**When to use:**
- Multi-step complex tasks (tracking progress)
- Auditing many files (one todo per file)
- Long workflows where you need visibility
- Coordinating parallel subagent work
- Breaking down large problems

**When NOT to use:**
- Don't use for simple one-turn tasks
- Avoid if you don't need progress tracking
- Don't use for external task management (this is in-memory)

**Configuration:**

```python
allowed_tools=["TodoWrite"]
```

**Example Claude call:**

```json
{
  "type": "tool_use",
  "name": "TodoWrite",
  "input": {
    "todos": [
      {
        "id": "task-1",
        "content": "Analyze schema.sql for stored procedures",
        "status": "completed",
        "priority": "high"
      },
      {
        "id": "task-2",
        "content": "Find all DATEDIFF() calls",
        "status": "in_progress",
        "priority": "high"
      },
      {
        "id": "task-3",
        "content": "Check for window functions",
        "status": "pending",
        "priority": "medium"
      }
    ]
  }
}
```

**Cost/Performance:** Minimal. ~5-10 output tokens per todo item.

---

### 11. BashOutput

**What it does:** Read output from a background Bash process using its PID.

**Input Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pid` | `int` | Yes | Process ID from previous `Bash` call with `run_in_background=true` |

**When to use:**
- Polling long-running background tasks
- Checking progress of background scripts
- Reading partial output before process completes
- Tailing logs from running services
- Monitoring background operations

**When NOT to use:**
- Don't use without first starting a background process
- Don't use on PIDs you don't own
- Don't use to wait for process completion (not reliable)

**Configuration:**

```python
allowed_tools=["Bash", "BashOutput"]
```

**Example workflow:**

```python
# Step 1: Start background task (from Bash tool)
# Claude calls: Bash(command="python long_task.py", run_in_background=true)
# Returns: {"pid": 12345, "status": "started"}

# Step 2: Check progress (from BashOutput tool)
# Claude calls: BashOutput(pid=12345)
# Returns: "Task 1/10 complete...\nTask 2/10 running..."

# Step 3: Check again or kill
# Claude calls: BashOutput(pid=12345) or KillBash(pid=12345)
```

**Cost/Performance:** Minimal. ~10-50ms per call. Returns only accumulated output.

---

### 12. KillBash

**What it does:** Terminate a background shell process by PID.

**Input Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pid` | `int` | Yes | Process ID to kill |

**When to use:**
- Stopping long-running background tasks
- Interrupting stuck processes
- Cleanup after BashOutput polling
- Graceful process shutdown

**When NOT to use:**
- Don't use without a valid PID
- Don't use on system processes
- Avoid if process cleanup is critical (may not complete gracefully)

**Configuration:**

```python
allowed_tools=["Bash", "KillBash"]
```

**Example Claude call:**

```json
{
  "type": "tool_use",
  "name": "KillBash",
  "input": {
    "pid": 12345
  }
}
```

**Returns:** `{"status": "killed", "pid": 12345}`

**Cost/Performance:** Minimal. ~50-100ms.

---

### 13. Agent (Subagents)

**What it does:** Spawn child agents that work independently (can run in parallel).

**Input Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `subagent_type` | `str` | No | Name of custom agent from `agents={}` config, or omit for general-purpose |
| `prompt` | `str` | Yes | Task prompt for the subagent |

**KEY BEHAVIORS:**
- Each subagent starts with FRESH context (no parent history)
- Multiple subagents can run in PARALLEL
- Subagents CANNOT spawn their own subagents (no nesting)
- Parent receives final result as a tool result
- Each subagent has its own model/tools (if defined)

**When to use:**
- Parallel analysis of multiple files
- Specialized sub-tasks (one agent for security, one for bugs)
- Divide-and-conquer for large problems
- Offloading work to faster models while parent waits

**When NOT to use:**
- Don't use for sequential tasks (just use turns)
- Avoid if subagents need parent context/conversation history
- Don't overuse (each subagent = API call + cost)

**Configuration:**

```python
from claude_agent_sdk import AgentDefinition

options = ClaudeAgentOptions(
    allowed_tools=["Agent", "Read", "Glob"],

    # Define custom agents
    agents={
        "bug-finder": AgentDefinition(
            description="Finds bugs in code",
            prompt="Look for logic errors, edge cases, and runtime issues.",
            tools=["Read"],
            model="sonnet",
        ),
        "security-scanner": AgentDefinition(
            description="Finds security issues",
            prompt="Look for hardcoded secrets, injection risks, unsafe patterns.",
            tools=["Read", "Grep"],
            model="sonnet",
        ),
    }
)
```

**Example Claude call (general-purpose):**

```json
{
  "type": "tool_use",
  "name": "Agent",
  "input": {
    "prompt": "Read data/sales.csv and calculate total revenue by region"
  }
}
```

**Example Claude call (custom agent):**

```json
{
  "type": "tool_use",
  "name": "Agent",
  "input": {
    "subagent_type": "bug-finder",
    "prompt": "Analyze src/auth.py for security bugs"
  }
}
```

**Cost/Performance:** High. Each subagent = full API call. 2-3x cost of a single turn.

---

### 14. AskUserQuestion

**What it does:** Pause and ask the user a question. Claude waits for the answer to continue.

**Input Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `question` | `str` | Yes | Question to ask the user |
| `options` | `list[str]` | No | Multiple choice options |

**CRITICAL:** Only works with `ClaudeSDKClient` (multi-turn stateful). Does NOT work with `query()`.

**When to use:**
- Interactive CLI applications
- Human-in-the-loop workflows
- Getting clarification or choices
- Decision points in complex tasks
- User approval gates

**When NOT to use:**
- Don't use with `query()` — no way to send reply back
- Don't use in batch/non-interactive pipelines
- Avoid in server applications expecting instant responses

**Configuration:**

```python
from claude_agent_sdk import ClaudeSDKClient

# MUST use ClaudeSDKClient, NOT query()
async with ClaudeSDKClient(options=options) as client:
    await client.query("Ask which file to analyze")
    async for message in client.receive_response():
        if block.name == "AskUserQuestion":
            answer = input("→ Your answer: ")
            await client.query(answer)  # Send reply back
```

**Example Claude call:**

```json
{
  "type": "tool_use",
  "name": "AskUserQuestion",
  "input": {
    "question": "Which file should I refactor?",
    "options": ["auth.py", "db.py", "api.py"]
  }
}
```

**Cost/Performance:** Blocks execution. Waiting for user input = no token cost.

---

### 15. ExitPlanMode

**What it does:** Request approval to transition from plan mode (read-only) to execution mode (modifications allowed).

**Input Parameters:** None (just a signal)

**How it works:**

```python
# Phase 1: Plan Mode
permission_mode="plan"
# Claude CAN: Read, Glob, Grep, TodoWrite
# Claude CANNOT: Write, Edit, Bash

# When Claude is done planning:
# Claude calls: ExitPlanMode()
# Parent decides: approve or reject
# If approved: move to Phase 2 with permission_mode="bypassPermissions"
```

**When to use:**
- Preview-then-execute workflows
- Getting approval before modifications
- Safety-critical operations (want to see the plan first)
- Multi-step processes with decision points

**When NOT to use:**
- Don't use for simple tasks (just use appropriate permission mode)
- Avoid if you need fast iteration
- Don't use in fully autonomous agents (not meant for human review)

**Configuration:**

```python
# Run 1: Plan only
options1 = ClaudeAgentOptions(
    allowed_tools=["Read", "Glob", "Grep", "Edit", "ExitPlanMode"],
    permission_mode="plan",
)

# Run 2: Execute (if approved)
options2 = ClaudeAgentOptions(
    allowed_tools=["Read", "Glob", "Grep", "Edit"],
    permission_mode="bypassPermissions",
)
```

**Example Claude call:**

```json
{
  "type": "tool_use",
  "name": "ExitPlanMode",
  "input": {}
}
```

**Cost/Performance:** Minimal. Just signals readiness.

---

### 16. ListMcpResources

**What it does:** List available "resources" from connected MCP servers (like browsing a virtual filesystem).

**Input Parameters:** None (or server name if multiple servers)

**MCP Resources vs Tools:**
- **Tools** = functions Claude can call
- **Resources** = data Claude can browse and read

**When to use:**
- Discovering available data sources
- Browsing API documentation
- Listing database tables/schemas
- Finding available knowledge base articles
- Exploring configuration options

**When NOT to use:**
- Don't use without an MCP server providing resources
- Don't use if you already know the resource names

**Configuration:**

```python
options = ClaudeAgentOptions(
    mcp_servers={
        "knowledge_base": {...}
    },
    allowed_tools=["ListMcpResources", "ReadMcpResource"],
)
```

**Example Claude call:**

```json
{
  "type": "tool_use",
  "name": "ListMcpResources",
  "input": {}
}
```

**Returns:** List of available resources with URIs and descriptions.

**Cost/Performance:** Depends on MCP server. Usually ~50-100ms.

---

### 17. ReadMcpResource

**What it does:** Read the full content of a specific MCP resource (identified by URI).

**Input Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `uri` | `str` | Yes | Resource URI from ListMcpResources |

**Common pattern:**

```
Step 1: ListMcpResources()
  → Returns: ["db://tables/users", "db://tables/orders", ...]

Step 2: ReadMcpResource(uri="db://tables/users")
  → Returns: Full schema and sample data
```

**When to use:**
- Reading specific database table schemas
- Accessing specific configuration documents
- Reading individual API endpoint docs
- Fetching knowledge base articles by ID

**When NOT to use:**
- Don't use without calling ListMcpResources first
- Don't use if you don't know the URI format

**Configuration:**

```python
allowed_tools=["ListMcpResources", "ReadMcpResource"]
```

**Example Claude call:**

```json
{
  "type": "tool_use",
  "name": "ReadMcpResource",
  "input": {
    "uri": "db://tables/users"
  }
}
```

**Cost/Performance:** Proportional to resource size. ~1-5 seconds for large resources.

---

## Custom Tools

Create custom tools using the `@tool()` decorator and `create_sdk_mcp_server()`.

### Decorator: @tool()

**What it does:** Registers a Python async function as a tool Claude can call.

**Syntax:**

```python
from claude_agent_sdk import tool

@tool(
    name="tool_name",                    # Used in allowed_tools as mcp__server__tool_name
    description="What it does",          # Shown to Claude
    input_schema={...},                  # JSON Schema defining parameters
)
async def my_tool(args: dict[str, Any]) -> dict[str, Any]:
    """Docstring explaining the tool."""
    # Your Python code
    result = do_something(args["param"])
    return {"content": [{"type": "text", "text": result}]}
```

### Input Schema

**Three formats:**

Simple dict:
```python
input_schema={
    "type": "object",
    "properties": {
        "email": {"type": "string", "description": "Email to validate"},
        "count": {"type": "integer", "description": "How many"}
    },
    "required": ["email"]
}
```

Pydantic (convert to schema):
```python
from pydantic import BaseModel
import json

class ValidateInput(BaseModel):
    email: str
    count: int

input_schema=json.loads(ValidateInput.model_json_schema())
```

Empty (no params):
```python
input_schema={}
```

### Return Format

**REQUIRED:** Always return this structure:

```python
{
    "content": [
        {
            "type": "text",
            "text": "your result as string"
        }
    ]
}
```

If error:
```python
{
    "content": [
        {
            "type": "text",
            "text": "Error: something went wrong"
        }
    ],
    "is_error": True
}
```

### Naming Convention

**For allowed_tools:**

```
mcp__<server_name>__<tool_name>
mcp__utils__validate_email    ← specific tool
mcp__utils__*                 ← all tools from utils server
```

### Complete Example

```python
from claude_agent_sdk import tool, create_sdk_mcp_server, query, ClaudeAgentOptions
import json
import re

@tool(
    name="validate_email",
    description="Validate an email address and extract parts",
    input_schema={
        "type": "object",
        "properties": {
            "email": {
                "type": "string",
                "description": "Email address to check"
            }
        },
        "required": ["email"],
    },
)
async def validate_email(args: dict) -> dict:
    """Check email validity and return parts."""
    email = args["email"]
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    is_valid = bool(re.match(pattern, email))

    if "@" in email:
        username, domain = email.split("@", 1)
    else:
        username, domain = email, None

    result = {
        "email": email,
        "is_valid": is_valid,
        "username": username,
        "domain": domain,
    }
    return {"content": [{"type": "text", "text": json.dumps(result)}]}


@tool(
    name="calculate_hash",
    description="Calculate hash of a string (MD5, SHA256)",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to hash"},
            "algorithm": {
                "type": "string",
                "enum": ["md5", "sha256"],
                "description": "Hash algorithm"
            }
        },
        "required": ["text", "algorithm"],
    },
)
async def calculate_hash(args: dict) -> dict:
    """Hash a string."""
    import hashlib
    text = args["text"]
    algo = args["algorithm"]

    if algo == "md5":
        hash_result = hashlib.md5(text.encode()).hexdigest()
    else:
        hash_result = hashlib.sha256(text.encode()).hexdigest()

    return {"content": [{"type": "text", "text": hash_result}]}


# Package tools into an MCP server
server = create_sdk_mcp_server(
    name="validators",
    version="1.0.0",
    tools=[validate_email, calculate_hash],
)

# Use the tools
options = ClaudeAgentOptions(
    model="sonnet",
    mcp_servers={"validators": server},
    allowed_tools=[
        "mcp__validators__validate_email",
        "mcp__validators__calculate_hash",
    ],
    permission_mode="bypassPermissions",
)

async def main():
    async for message in query(
        prompt="Validate admin@example.com and hash it with SHA256",
        options=options,
    ):
        print(message)

# asyncio.run(main())
```

### Function: create_sdk_mcp_server()

**What it does:** Packages custom `@tool()` functions into an in-process MCP server.

**Syntax:**

```python
from claude_agent_sdk import create_sdk_mcp_server

server = create_sdk_mcp_server(
    name="my_server",           # Used in tool name: mcp__my_server__tool
    version="1.0.0",            # Semantic version
    tools=[tool1, tool2, ...],  # List of @tool()-decorated functions
)
```

**Returns:** An MCP server object that can be passed to `ClaudeAgentOptions(mcp_servers={"key": server})`.

### Tool Annotations (Optional)

**Add metadata about tool behavior:**

```python
from claude_agent_sdk import ToolAnnotations

@tool(
    name="read_cache",
    description="Read from cache (fast, safe)",
    input_schema={...},
    annotations=ToolAnnotations(
        title="Cache Reader",
        readOnlyHint=True,        # Safe for parallel execution
        destructiveHint=False,    # Doesn't modify anything
        idempotentHint=True,      # Same input → same output
        openWorldHint=False,      # No external side effects
    ),
)
async def read_cache(args: dict) -> dict:
    ...
```

**Hints:**
- `readOnlyHint` = Claude can call in parallel with other read operations
- `destructiveHint` = Modifies data (Bash, Edit, Write, Delete operations)
- `idempotentHint` = Safe to retry (same input always produces same output)
- `openWorldHint` = Makes external API calls or has side effects

---

## Tool Configuration

### allowed_tools vs disallowed_tools vs permission_mode

**Three independent layers:**

| Layer | Purpose | Example |
|-------|---------|---------|
| `tools` | Which tools EXIST (base set) | `["Read", "Glob", "Write"]` |
| `allowed_tools` | Which tools are AUTO-APPROVED (no permission prompt) | `["Read"]` |
| `disallowed_tools` | Which tools are PERMANENTLY BLOCKED (highest priority) | `["Bash", "Grep"]` |
| `permission_mode` | Default behavior for tools not in allowed_tools | `"bypassPermissions"` |

### Priority Order

1. **disallowed_tools** (checked FIRST — always blocks)
2. **allowed_tools** (if in list, auto-approve)
3. **permission_mode** (if not in allowed_tools, use this default)

**Example:**

```python
options = ClaudeAgentOptions(
    # Only these tools exist
    tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],

    # Auto-approve these (no permission prompt)
    allowed_tools=["Read", "Glob"],

    # ALWAYS block these (overrides everything)
    disallowed_tools=["Bash"],

    # For others, use this mode
    permission_mode="bypassPermissions",
)

# Result:
# - Read: allowed (in allowed_tools)
# - Glob: allowed (in allowed_tools)
# - Write: allowed (bypassPermissions)
# - Edit: allowed (bypassPermissions)
# - Bash: BLOCKED (in disallowed_tools, highest priority)
# - Grep: allowed (bypassPermissions)
```

### Permission Modes

| Mode | Behavior |
|------|----------|
| `"default"` | Requires `can_use_tool` callback or asks user interactively |
| `"acceptEdits"` | Auto-approve Read/Write/Edit; ask about Bash and destructive ops |
| `"plan"` | Plan mode — allow Read/Glob/Grep only, block modifications |
| `"bypassPermissions"` | Auto-approve everything not in disallowed_tools |
| `"dontAsk"` | Only allow allowed_tools; deny everything else silently (no prompts) |

### Common Configurations

**Phase 1 (Exploration):**

```python
options = ClaudeAgentOptions(
    allowed_tools=["Read", "Glob", "Grep"],
    permission_mode="bypassPermissions",
)
```

**Phase 2 (Generation with reference):**

```python
options = ClaudeAgentOptions(
    allowed_tools=["Read"],
    permission_mode="bypassPermissions",
)
```

**Phase 4 (Pure generation):**

```python
options = ClaudeAgentOptions(
    allowed_tools=[],
    permission_mode="bypassPermissions",
)
```

**Interactive with safety:**

```python
options = ClaudeAgentOptions(
    allowed_tools=["Read"],
    permission_mode="acceptEdits",  # Ask about dangerous ops
)
```

**Plan-then-execute:**

```python
# Phase 1: Plan
options1 = ClaudeAgentOptions(
    allowed_tools=["Read", "Glob", "Grep", "ExitPlanMode"],
    permission_mode="plan",
)

# Phase 2: Execute (after approval)
options2 = ClaudeAgentOptions(
    allowed_tools=["Read", "Write", "Edit", "Bash"],
    permission_mode="bypassPermissions",
)
```

---

## Common Patterns

### Pattern 1: Glob + Read Combo

Find files, then read them.

```python
allowed_tools=["Glob", "Read"]

# Claude flow:
# 1. Glob(pattern="**/*.sql") → finds files
# 2. Read(file_path="...") → reads first file
# 3. Read(file_path="...") → reads second file
# 4. Analyzes all files
```

### Pattern 2: WebSearch + WebFetch Combo

Search for URLs, then read them.

```python
allowed_tools=["WebSearch", "WebFetch"]

# Claude flow:
# 1. WebSearch(query="documentation") → finds URLs
# 2. WebFetch(url="...") → reads first page
# 3. WebFetch(url="...") → reads second page
# 4. Synthesizes information
```

### Pattern 3: Bash Background + BashOutput + KillBash

Start a long task, monitor, optionally kill.

```python
allowed_tools=["Bash", "BashOutput", "KillBash"]

# Claude flow:
# 1. Bash(command="long_task.py", run_in_background=true) → starts, gets PID
# 2. (wait 5s)
# 3. BashOutput(pid=123) → checks progress
# 4. (wait 5s)
# 5. BashOutput(pid=123) → checks again
# 6. KillBash(pid=123) → stops if needed
```

### Pattern 4: Per-Phase Tool Restriction

Different tools for different phases.

```python
# Phase 1: Explore
phase1_tools = ["Read", "Glob", "Grep"]

# Phase 2: Reference
phase2_tools = ["Read"]

# Phase 3: Generate
phase3_tools = []

# Phase 4: Validate
phase4_tools = ["Bash"]  # run tests only

for phase, tools in [
    ("phase1", phase1_tools),
    ("phase2", phase2_tools),
    ("phase3", phase3_tools),
    ("phase4", phase4_tools),
]:
    options = ClaudeAgentOptions(allowed_tools=tools)
    result = await invoke_claude(prompt=phase_prompt, options=options)
```

### Pattern 5: Custom Tool Server

Multiple custom tools packaged together.

```python
@tool(name="tool1", ...)
async def tool1(args): ...

@tool(name="tool2", ...)
async def tool2(args): ...

@tool(name="tool3", ...)
async def tool3(args): ...

# Package all together
server = create_sdk_mcp_server(
    name="my_domain",
    tools=[tool1, tool2, tool3],
)

options = ClaudeAgentOptions(
    mcp_servers={"domain": server},
    allowed_tools=[
        "mcp__domain__tool1",
        "mcp__domain__tool2",
        "mcp__domain__tool3",
    ],
)
```

### Pattern 6: Subagent Divide-and-Conquer

Spawn specialized agents in parallel.

```python
options = ClaudeAgentOptions(
    allowed_tools=["Agent", "Read", "Glob", "Grep"],
    agents={
        "analyzer": AgentDefinition(
            description="Analyzes data",
            tools=["Read"],
            model="sonnet",
        ),
        "reviewer": AgentDefinition(
            description="Reviews output",
            tools=["Read", "Grep"],
            model="haiku",  # cheaper
        ),
    },
)

# Claude can call:
# Agent(subagent_type="analyzer", prompt="analyze this file")
# Agent(subagent_type="reviewer", prompt="review the output")
# Both run in parallel, results merge back to parent
```

---

## Decision Tree: Which Tool?

```
START
├─ Want to READ content?
│  ├─ File on disk? → Read
│  ├─ URL on web? → WebFetch (after WebSearch if needed)
│  └─ MCP resource? → ReadMcpResource (after ListMcpResources)
│
├─ Want to FIND files?
│  ├─ By pattern? → Glob
│  ├─ By content? → Grep
│  └─ On web? → WebSearch
│
├─ Want to MODIFY code?
│  ├─ Complete rewrite? → Write
│  ├─ Targeted fix? → Edit
│  ├─ Notebook cells? → NotebookEdit
│  └─ Shell commands? → Bash
│
├─ Want to RUN something?
│  ├─ Shell command? → Bash
│  ├─ Long task (background)? → Bash(run_in_background=true)
│  ├─ Check progress? → BashOutput
│  └─ Stop it? → KillBash
│
├─ Want to COORDINATE work?
│  ├─ Track progress? → TodoWrite
│  ├─ Parallel specialists? → Agent (with custom agents)
│  └─ Wait for human? → AskUserQuestion (ClaudeSDKClient only)
│
├─ Want custom logic?
│  └─ → @tool() + create_sdk_mcp_server()
│
├─ Want to PLAN first?
│  └─ → permission_mode="plan" + ExitPlanMode
│
└─ Want STRUCTURED data from MCP?
   ├─ List available? → ListMcpResources
   └─ Read one? → ReadMcpResource
```

---

## Cost and Performance Reference

| Tool | Cost | Speed | Notes |
|------|------|-------|-------|
| Read | Low | Fast (1-2ms) | Token cost = file size |
| Glob | Minimal | Fast (10-50ms) | No token cost |
| Grep | Low | Medium (50-500ms) | Token cost = matched lines |
| Write | Low | Very fast (1-2ms) | Token cost = file content |
| Edit | Low | Very fast (1-5ms) | Token cost = change size |
| Bash | Medium-High | Varies | Token cost = execution time |
| NotebookEdit | Minimal | Fast (5-10ms) | No token cost |
| WebSearch | High | Slow (500ms+) | Token cost = 50-100 per result |
| WebFetch | Medium | Medium (1-2s) | Token cost = page content |
| TodoWrite | Minimal | Fast (instant) | Token cost = 5-10 per item |
| BashOutput | Minimal | Fast (10-50ms) | No token cost (just reads) |
| KillBash | Minimal | Fast (50-100ms) | No token cost |
| Agent | Very High | Slow (2-5s) | Full API call per subagent |
| AskUserQuestion | Zero | User wait time | Blocks execution |
| ExitPlanMode | Minimal | Instant | Just a signal |
| ListMcpResources | Medium | 50-100ms | Depends on MCP server |
| ReadMcpResource | Medium | 1-5s | Depends on resource size |

---

## Best Practices

1. **Restrict tools by phase** — Different operations need different permissions
2. **Use disallowed_tools for safety** — Block Bash in user-facing apps
3. **Combine Read + Edit/Write** — Read first, then modify
4. **Use WebSearch → WebFetch** — Don't fetch URLs without finding them first
5. **Package related custom tools** — One MCP server per domain (validators, calculators, etc.)
6. **Consider costs** — WebSearch is expensive; use Read for local docs
7. **Plan before executing** — Use plan mode for safety-critical operations
8. **Monitor background tasks** — Don't fire-and-forget Bash background processes
9. **Use TodoWrite for visibility** — Especially for multi-step tasks
10. **Prefer specific tools over broad permissions** — Better control = safer execution

