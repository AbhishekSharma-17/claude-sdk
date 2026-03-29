# sql2spark — Production-Grade SQL-to-PySpark Converter

An AI-powered CLI tool that converts large, production-grade SQL scripts (500-5000+ lines) into equivalent PySpark code using the **Claude Agent SDK** with **Opus 4.6**. Handles stored procedures, views, triggers, functions across multiple SQL dialects with heavy cross-dependencies.

---

## Table of Contents

- [Why This Exists](#why-this-exists)
- [Architecture Overview](#architecture-overview)
- [The 4-Phase Pipeline](#the-4-phase-pipeline)
  - [Phase 1: Discovery & Complexity Analysis](#phase-1-discovery--complexity-analysis)
  - [Phase 2: Dependency Analysis & Conversion Planning](#phase-2-dependency-analysis--conversion-planning)
  - [Phase 3: SQL-to-PySpark Conversion](#phase-3-sql-to-pyspark-conversion)
  - [Phase 4: Validation & Reporting](#phase-4-validation--reporting)
- [Complexity Scoring System](#complexity-scoring-system)
- [Knowledge-Driven Conversion](#knowledge-driven-conversion)
- [Agent Orchestration Strategy](#agent-orchestration-strategy)
- [Token Efficiency & Cost Optimization](#token-efficiency--cost-optimization)
- [Project Structure](#project-structure)
- [Usage](#usage)
- [Configuration](#configuration)
- [How It Handles Large Files](#how-it-handles-large-files)
- [Error Handling & Resilience](#error-handling--resilience)
- [Output Format](#output-format)

---

## Why This Exists

Migrating SQL stored procedures to PySpark is one of the most painful data engineering tasks. A 3000-line T-SQL stored procedure with 15 temp tables, 8 CTEs, cursor loops, and cross-procedure dependencies cannot be converted with simple regex find-and-replace. The semantics differ in subtle, silent ways — DATEDIFF argument order is reversed, string comparisons flip from case-insensitive to case-sensitive, NULL sort ordering is opposite, window frame defaults behave differently with duplicate values.

This tool uses Claude Opus 4.6 as the conversion engine, orchestrated through a 4-phase pipeline that first understands the SQL, maps dependencies, plans the conversion with specific per-line instructions, and then converts each object with targeted guidance — producing production-quality PySpark code that follows best practices and avoids the top 10 silent failure patterns.

---

## Architecture Overview

```
                          sql2spark Architecture
 ============================================================================

 INPUT                    PHASE 1              PHASE 2
 ─────                    ───────              ───────
 input/*.sql ──────→  DISCOVERY  ──────→  DEPENDENCY & PLANNING
                      │                   │
                      ├─ Object           ├─ Dependency graph
                      │  inventory        ├─ Topological sort
                      ├─ Dialect          ├─ Conversion plan with
                      │  detection        │  per-object instructions
                      ├─ Complexity       ├─ Targeted gotcha flags
                      │  scoring          └─ Strategy per complexity
                      └─ Line ranges

 PHASE 3                        PHASE 4
 ───────                        ───────
 CONVERSION  ──────────→  VALIDATION & REPORT
 │                         │
 ├─ PySpark .py files      ├─ ast.parse() syntax check (free)
 │  (one per object)       ├─ Claude review (Sonnet)
 ├─ Parallel by            ├─ Dependency completeness
 │  dependency level       ├─ Gotcha verification
 └─ Self-correcting        └─ report.json
    (validates own output)

 OUTPUT
 ──────
 output/*.py            ← One PySpark file per SQL object
 output/report.json     ← Full conversion report with costs
```

### Core Design Principles

1. **Phase separation**: Each phase has a single responsibility and runs independently
2. **Knowledge distillation**: Phase 2 reads the full knowledge base once, then produces targeted instructions for Phase 3 — saving 60-80% on input tokens
3. **Fresh context per object**: Each conversion gets a clean context window via `query()`, preventing context exhaustion on large scripts
4. **Parallel by dependency level**: Objects with no mutual dependencies convert concurrently
5. **Self-correcting**: Phase 3 validates its own output and fixes syntax errors within the same query
6. **Checkpoint/resume**: Progress is saved after each conversion for resilience

---

## The 4-Phase Pipeline

### Phase 1: Discovery & Complexity Analysis

**What it does**: Reads each SQL file, identifies every discrete object (procedure, function, view, trigger), detects the SQL dialect, and computes a complexity score.

**How it works**:
1. **Pre-scan** (local regex, zero API cost): The `sql_prescan` MCP tool counts lines, finds CREATE/ALTER statements, detects dialect hints via regex patterns
2. **Claude reads the file**: Uses the `Read` tool with `offset`/`limit` for files over 4000 lines (reads in 2 chunks)
3. **Object identification**: Finds exact line ranges, parameters, references to other objects, temp tables created/used, cursor presence, window function count
4. **Dialect auto-detection**: Matches syntax markers — `GO`/`DECLARE @`/`sp_executesql` for T-SQL, `CREATE OR REPLACE`/`DBMS_` for PL/SQL, `$$`/`LANGUAGE plpgsql` for PL/pgSQL
5. **Complexity scoring**: Weighted formula producing a 1-10 score per object (details below)

**SDK usage**: `query()` per file with `output_format` for guaranteed JSON structure

**Knowledge injected**: `sql_to_pyspark_mapping.md` (to identify constructs) + `known_limitations.md` (to flag non-convertible patterns early)

**Output**: `FileInventory` JSON with all objects, their metadata, and complexity scores

---

### Phase 2: Dependency Analysis & Conversion Planning

**What it does**: This is the "thinking" phase. It builds a dependency graph, determines conversion order, and generates **per-object, line-specific conversion instructions** that Phase 3 will use.

**How it works**:
1. **Dependency graph**: Maps which procedures call which, temp table flows (who creates `#X`, who reads `#X`), view dependencies, function usage
2. **Topological sort**: Groups objects into conversion levels:
   - Level 0: Views and standalone functions (no dependencies)
   - Level 1: Objects depending only on Level 0
   - Level N: Objects depending on levels 0 through N-1
3. **Conversion hierarchy precedence**:
   - Views first (just queries, no state)
   - Scalar/table functions next (pure computation)
   - Procedures by dependency level (leaf procedures first, orchestrator procedures last)
   - Triggers last (they reference tables that procedures populate)
4. **Per-object conversion instructions**: For EACH object, generates specific guidance like:
   - "Line 85: `ISNULL(Region, 'Unknown')` → `F.coalesce(F.col('Region'), F.lit('Unknown'))`"
   - "Lines 45-80: CURSOR loop → vectorize as `F.when` chain (see Example 3)"
   - "Line 120: DATEDIFF — reverse argument order (Gotcha #1)"
   - "Calls `usp_GetRegion` — signature: `def get_region(spark, region_id: int) -> DataFrame`"

**Why this matters**: Instead of giving Phase 3 the full 15K-token knowledge base for every conversion, Phase 2 distills it into 2-5K tokens of targeted instructions per object. This saves 60-80% on input tokens and produces better results because Claude gets SPECIFIC guidance rather than searching through a 319-line mapping table.

**SDK usage**: `query()` once with all inventories combined, `output_format` for structured JSON

**Knowledge injected**: ALL 5 files (mapping, examples, gotchas, limitations, idioms) — read once, distilled into per-object instructions

**Output**: `ConversionPlan` JSON with dependency graph, conversion levels, and per-object plans

---

### Phase 3: SQL-to-PySpark Conversion

**What it does**: Converts each SQL object to a production-quality PySpark `.py` file.

**How it works**:
1. For each object (in the planned conversion order), spawns a fresh `query()` call
2. Claude reads the specific line range from the SQL file using `Read(offset, limit)`
3. Receives the **targeted conversion instructions** from Phase 2 (not the full knowledge base)
4. Receives **dependency context**: compressed signatures of already-converted objects (function name, params, return type — typically 5-20 lines per dependency)
5. Writes the `.py` file to `output/` using the `Write` tool
6. Validates its own output using the `validate_pyspark_syntax` MCP tool
7. If validation fails, self-corrects within the same query (has 25 turns budget)

**Parallel execution**: Objects at the same dependency level run via `asyncio.gather` with configurable concurrency (default 3, `--parallel` flag).

**Interactive mode** (`--interactive`): Uses `ClaudeSDKClient` instead of `query()`. Claude can use `AskUserQuestion` for ambiguous SQL patterns. User approves/revises/skips each conversion.

**SDK usage**: `query()` per object (automated) or `ClaudeSDKClient` per object (interactive)

**Knowledge injected**: Only the abbreviated style guide in system prompt (~2K tokens) + targeted instructions from Phase 2 in the user prompt

---

### Phase 4: Validation & Reporting

**What it does**: Validates every generated PySpark file and produces a conversion report.

**How it works**:
1. **Local syntax check** (zero API cost): `ast.parse()` on each `.py` file, plus pattern checks for bare `col()` without `F.` prefix, `.collect()` usage, TODO counts
2. **Claude review** (Sonnet — cheaper model, sufficient for review): Reads each file and checks against the gotcha list and anti-pattern catalog
3. **Dependency completeness**: Verifies all referenced functions exist in the output directory
4. **Report generation**: Produces `report.json` with per-object status, cost breakdown, validation issues

**SDK usage**: `query()` per file in parallel

**Knowledge injected**: `critical_gotchas.md` + `pyspark_idioms.md` (review checklists)

---

## Complexity Scoring System

Every SQL object gets a complexity score (1-10) computed from 7 weighted factors:

| Factor | Weight | Scoring |
|--------|--------|---------|
| **Line count** | 25% | ≤50 lines → 1, 50-200 → 3, 200-500 → 5, 500-1000 → 7, >1000 → 10 |
| **Dependency count** | 20% | 0 refs → 1, 1-2 → 3, 3-5 → 5, 6-10 → 7, >10 → 10 |
| **Temp table count** | 15% | 0 → 1, 1-2 → 3, 3-5 → 5, >5 → 7 |
| **Cursor / dynamic SQL** | 15% | Absent → 0, Present → 10 |
| **Window function count** | 10% | 0 → 1, 1-3 → 3, 4-6 → 5, >6 → 7 |
| **Control flow depth** | 10% | Flat → 1, Moderate nesting → 5, Deeply nested → 10 |
| **Transaction complexity** | 5% | None → 1, Simple → 3, Nested/savepoints → 7 |

### Complexity levels:

| Score | Level | Conversion strategy |
|-------|-------|-------------------|
| 1-3 | **Simple** | Direct conversion, single pass, minimal review |
| 4-6 | **Moderate** | Standard conversion with gotcha checklist |
| 7-8 | **Complex** | Careful conversion, add TODO for ambiguous patterns |
| 9-10 | **Very Complex** | Break into sub-steps, flag for interactive review |

### File-level classification:

| Criteria | Classification |
|----------|---------------|
| Single object, <500 lines | Simple script |
| 1-5 objects, <2000 lines | Standard script |
| 5-15 objects, 2000-5000 lines | Complex script |
| 15+ objects OR >5000 lines | Enterprise script |

---

## Knowledge-Driven Conversion

The `knowledge/` directory contains 5 curated reference documents totaling ~1137 lines:

| File | Lines | Purpose | Used in |
|------|-------|---------|---------|
| `sql_to_pyspark_mapping.md` | 319 | Construct-by-construct mapping table (data types, joins, windows, strings, dates, JSON, control flow) | Phase 1 (identify constructs), Phase 2 (generate instructions) |
| `few_shot_examples.md` | 199 | 3 complete before/after examples (SELECT+JOIN+GROUP, window functions+CTE, cursor-to-vectorized) | Phase 2 (reference patterns) |
| `critical_gotchas.md` | 193 | Top 10 silent failures that produce wrong results without errors | Phase 2 (flag per object), Phase 4 (review checklist) |
| `known_limitations.md` | 130 | Patterns that cannot be auto-converted (dynamic SQL, cursors, transactions, MERGE) | Phase 1 (early flagging), Phase 2 (TODO instructions) |
| `pyspark_idioms.md` | 296 | Output style guide (file structure, naming, DataFrame patterns, performance, anti-patterns) | Phase 3 (abbreviated in system prompt), Phase 4 (anti-pattern detection) |

### Knowledge flow through phases:

```
Phase 1                    Phase 2                      Phase 3               Phase 4
─────────                  ─────────                    ─────────             ─────────
mapping.md ──→ identify    ALL 5 files ──→ distill      Abbreviated style     gotchas.md
               constructs  (15K tokens)    into per-    guide (2K tokens)     idioms.md
limitations.md → flag                      object       + targeted            (7K tokens)
               issues                      instructions instructions from
                                          (2-5K tokens  Phase 2
                                           per object)  (2-5K tokens)
```

---

## Agent Orchestration Strategy

### Why `query()` per object, not `ClaudeSDKClient` for all conversions?

Each procedure conversion consumes 40-80K tokens of context (SQL source + system prompt + instructions + response). Opus 4.6 has a 200K token context window. After converting 3-4 procedures in a stateful session, the context is exhausted and older conversation is compressed, losing critical details.

Using `query()` per object gives each conversion a **clean 200K context window**. The trade-off is no cross-conversion context, which we compensate for by passing compressed dependency signatures (5-20 lines per dependency).

### Why Python `asyncio.gather`, not SDK sub-agents?

The SDK's Agent tool spawns sub-agents that Claude controls. For our use case, the Python orchestrator already knows the dependency graph and which objects can parallelize. Using `asyncio.gather` on multiple `query()` calls gives us:
- Explicit control over concurrency limits (semaphore-bounded)
- Per-object error handling and retry
- Per-object cost tracking
- No reliance on Claude deciding when to parallelize

### SDK features used:

| Feature | Where | Why |
|---------|-------|-----|
| `query()` | Phases 1, 2, 3 (automated), 4 | Stateless one-shot for independent tasks |
| `ClaudeSDKClient` | Phase 3 (interactive) | Multi-turn for human-in-the-loop |
| `output_format` | Phases 1, 2 | Guaranteed structured JSON responses |
| `allowed_tools` | All phases | Per-phase tool restriction (Phase 1: Read-only, Phase 3: Read+Write) |
| `mcp_servers` | Phases 1, 3, 4 | Custom tools (sql_prescan, validate_pyspark_syntax) |
| `@tool()` decorator | tools.py | Define custom MCP tools |
| `create_sdk_mcp_server()` | tools.py | Package tools into MCP server |
| `max_turns` | All phases | Prevent runaway tool loops |
| `max_budget_usd` | All phases | Per-phase cost caps |
| `permission_mode="bypassPermissions"` | All phases | Automated mode, no interactive approvals |
| `AskUserQuestion` tool | Phase 3 interactive | Human-in-the-loop for ambiguous patterns |
| `fallback_model` | Phase 3 | Falls back to Sonnet if Opus unavailable |
| `Read` tool offset/limit | Phase 1, 3 | Handle large files without exceeding context |

---

## Token Efficiency & Cost Optimization

### The Phase 2 savings:

**Without Phase 2** (naive approach — full knowledge per conversion):
```
Each conversion: ~15K tokens (knowledge) + ~40K tokens (SQL source + prompt)
20 objects: 15K × 20 = 300K tokens on knowledge alone
```

**With Phase 2** (our approach — targeted instructions):
```
Phase 2: ~15K tokens (knowledge, read once)
Each conversion: ~3K tokens (targeted instructions) + ~40K tokens (SQL source + prompt)
20 objects: 3K × 20 = 60K tokens on instructions
Net savings: ~225K input tokens = ~$3.37 on Opus pricing
```

### Prompt caching amplifies savings:

The Claude Agent SDK automatically caches repeated system prompts. Phase 3's system prompt is identical across all conversion calls (~2K tokens). After the first call, subsequent calls read from cache at 10% cost — effectively making the system prompt free.

### Cost estimate for a typical 5K-line file with 20 procedures:

| Phase | Calls | Model | Est. Cost |
|-------|-------|-------|-----------|
| Discovery | 1 | Opus | ~$1.50 |
| Planning | 1 | Opus | ~$1.20 |
| Conversion | 20 | Opus | ~$35.00 |
| Validation | 20 | Sonnet | ~$1.00 |
| **Total** | | | **~$38.70** |

---

## Project Structure

```
3xcodeconvertor/
  input/                          ← Drop SQL files here
  output/                         ← Converted PySpark files + report.json
  knowledge/                      ← 5 curated reference documents
    sql_to_pyspark_mapping.md       319 lines — construct mapping
    few_shot_examples.md            199 lines — before/after examples
    critical_gotchas.md             193 lines — top 10 silent failures
    known_limitations.md            130 lines — non-convertible patterns
    pyspark_idioms.md               296 lines — output style guide

  converter.py                    ← CLI entry point (argparse)
  orchestrator.py                 ← Pipeline: Phase 1 → 2 → 3 → 4
  config.py                       ← ConverterConfig dataclass
  models.py                       ← Pydantic schemas + JSON output schemas
  tools.py                        ← 2 custom MCP tools

  agents/
    prompts.py                    ← Knowledge loader + 4 system prompts
    options.py                    ← ClaudeAgentOptions factory (6 builders)

  phases/
    discovery.py                  ← Phase 1: Object inventory + complexity
    planning.py                   ← Phase 2: Dependency graph + conversion plan
    conversion.py                 ← Phase 3: Parallel + interactive conversion
    validation.py                 ← Phase 4: Syntax + review + report
```

---

## Usage

### Prerequisites

- Python 3.12+
- Claude Agent SDK (`claude-agent-sdk>=0.1.51`)
- Claude CLI installed (`curl -fsSL https://claude.ai/install.sh | bash`)
- `ANTHROPIC_API_KEY` in `.env` file or environment

### Basic usage

```bash
cd 3xcodeconvertor

# Drop your SQL files in input/
cp /path/to/your/scripts/*.sql input/

# Run full conversion (automated)
python3 converter.py

# Dry run — discovery + planning only, no conversion
python3 converter.py --dry-run

# Interactive mode — approve each conversion
python3 converter.py --interactive

# With options
python3 converter.py --budget 25.0 --parallel 5 --verbose
```

### CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--interactive` | off | Approve each conversion (human-in-the-loop) |
| `--budget FLOAT` | 50.0 | Total cost cap in USD |
| `--parallel INT` | 3 | Max concurrent conversions |
| `--dry-run` | off | Phase 1 + 2 only (no conversion) |
| `--output-dir PATH` | `./output` | Custom output directory |
| `--model MODEL` | `opus` | Conversion model (opus/sonnet/haiku) |
| `--verbose` / `-v` | off | Show all tool calls |

---

## Configuration

All settings are in `config.py` via the `ConverterConfig` dataclass:

| Setting | Default | Description |
|---------|---------|-------------|
| `conversion_model` | `"opus"` | Model for Phases 1-3 |
| `validation_model` | `"sonnet"` | Model for Phase 4 (cheaper) |
| `fallback_model` | `"sonnet"` | Fallback if primary unavailable |
| `total_budget_usd` | `50.0` | Pipeline-wide cost cap |
| `discovery_budget_per_file` | `1.00` | Phase 1 per-file cap |
| `planning_budget` | `1.50` | Phase 2 cap |
| `conversion_budget_per_object` | `2.50` | Phase 3 per-object cap |
| `validation_budget_per_file` | `0.30` | Phase 4 per-file cap |
| `discovery_max_turns` | `15` | Max tool-call cycles for Phase 1 |
| `planning_max_turns` | `15` | Max for Phase 2 |
| `conversion_max_turns` | `25` | Max for Phase 3 |
| `validation_max_turns` | `10` | Max for Phase 4 |
| `max_parallel_conversions` | `3` | Concurrency limit for Phase 3 |
| `max_retries` | `3` | Retry count per failed conversion |
| `large_file_threshold` | `4000` | Lines above which files are chunked |
| `chunk_size` | `2500` | Lines per chunk for large files |

---

## How It Handles Large Files

SQL files vary dramatically in size. The pipeline adapts:

| File Size | Strategy |
|-----------|----------|
| <500 lines | Single `Read()` call, simple script classification |
| 500-2000 lines | Single `Read()` call, standard complexity analysis |
| 2000-4000 lines | Single `Read()` call (fits in context), detailed analysis |
| 4000-8000 lines | Two-chunk reading: `Read(offset=0, limit=2500)` + `Read(offset=2500, limit=rest)` |
| >8000 lines | Two-chunk reading, enterprise script classification |

Individual objects (procedures, functions) are typically 50-500 lines. Phase 3 reads only the relevant line range using `Read(offset=start_line-1, limit=line_count)`, so even a 5000-line file doesn't flood the context — Claude reads only the 200-line procedure it's converting.

---

## Error Handling & Resilience

| Scenario | Handling |
|----------|---------|
| API rate limit | 3 retries with exponential backoff (2s, 4s, 8s) |
| Opus unavailable | Falls back to Sonnet with warning |
| Budget exceeded | Halts gracefully, reports what was completed |
| Syntax error in output | Phase 3 self-corrects (validate + rewrite within same query) |
| Phase 3 object failure | Marks as failed, continues with next object |
| Phase 4 critical issue | Logged in report, optionally re-runs Phase 3 with feedback |
| Interrupted mid-run | Checkpoint saved after each conversion; re-running skips completed objects |
| Claude returns invalid JSON | Fallback JSON extraction (code block, brace matching) |

---

## Output Format

### Per-object PySpark files

Each generated `.py` file follows the style guide from `pyspark_idioms.md`:

```python
"""PySpark conversion of sales_etl.sql — usp_LoadCustomers.

Source:  input/sales_etl.sql (lines 15-280)
Target:  Load and transform customer data with region mapping

SQL construct mapping:
  CTE → DataFrame variable, LEFT JOIN, ROW_NUMBER → Window + F.row_number(),
  ISNULL → F.coalesce, SELECT INTO #temp → .cache()
"""
from __future__ import annotations

from dataclasses import dataclass
from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql.types import DecimalType

# === Section 1: Parameters (SQL lines 15-25) ===

@dataclass
class PipelineParams:
    start_date: str = "2024-01-01"
    region_filter: str | None = None

# === Section 2: Customer staging (SQL lines 30-120) ===

def _step1_customer_staging(spark: SparkSession, params: PipelineParams) -> DataFrame:
    """Step 1 -- customer staging with region mapping (SQL lines 30-120).

    Replaces: SELECT ... INTO #CustomerStaging FROM dbo.Customers c
              LEFT JOIN dbo.RegionMapping r ...
    """
    ...

def run_pipeline(spark: SparkSession, params: PipelineParams) -> DataFrame:
    """Entry point for the converted pipeline."""
    ...

if __name__ == "__main__":
    main()
```

### Conversion report (`output/report.json`)

```json
{
  "total_objects": 8,
  "converted": 7,
  "failed": 0,
  "needs_review": 1,
  "total_cost_usd": 18.45,
  "total_duration_ms": 95000,
  "file_complexity": "Complex script",
  "cost_breakdown": {
    "discovery": 1.50,
    "planning": 1.20,
    "conversion": 14.75,
    "validation": 1.00
  },
  "objects": [
    {
      "object_name": "usp_LoadCustomers",
      "status": "converted",
      "output_file": "output/load_customers.py",
      "cost_usd": 1.85,
      "turns_used": 8,
      "duration_ms": 12000
    }
  ],
  "validation_issues": [],
  "todos": []
}
```
