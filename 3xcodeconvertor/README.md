# sql2spark -- Production-Grade SQL-to-PySpark Converter

An AI-powered CLI tool that converts large, production-grade SQL scripts (500-5000+ lines) into equivalent PySpark code using the **Claude Agent SDK**. Handles stored procedures, views, triggers, functions across multiple SQL dialects (T-SQL, PL/SQL, PL/pgSQL) with heavy cross-dependencies.

Supports both **Anthropic API** and **AWS Bedrock** as LLM providers.

---

## Table of Contents

- [Why This Exists](#why-this-exists)
- [Architecture Overview](#architecture-overview)
- [The 5-Phase Pipeline](#the-5-phase-pipeline)
  - [Phase 1: Discovery & Complexity Analysis](#phase-1-discovery--complexity-analysis)
  - [Phase 2: Dependency Analysis & Conversion Planning](#phase-2-dependency-analysis--conversion-planning)
  - [Phase 3: SQL-to-PySpark Conversion](#phase-3-sql-to-pyspark-conversion)
  - [Phase 4: Context-Aware Validation](#phase-4-context-aware-validation)
  - [Phase 5: Auto-Fix & Developer Action Items](#phase-5-auto-fix--developer-action-items)
- [Complexity Scoring System](#complexity-scoring-system)
- [Knowledge-Driven Conversion](#knowledge-driven-conversion)
- [Agent Orchestration Strategy](#agent-orchestration-strategy)
- [Token Efficiency & Cost Optimization](#token-efficiency--cost-optimization)
- [Project Structure](#project-structure)
- [Usage](#usage)
- [Configuration](#configuration)
- [Provider Setup (Anthropic vs Bedrock)](#provider-setup-anthropic-vs-bedrock)
- [How It Handles Large Files](#how-it-handles-large-files)
- [Error Handling & Resilience](#error-handling--resilience)
- [Output Format](#output-format)
- [Real-World Example](#real-world-example)

---

## Why This Exists

Migrating SQL stored procedures to PySpark is one of the most painful data engineering tasks. A 3000-line T-SQL stored procedure with 15 temp tables, 8 CTEs, cursor loops, and cross-procedure dependencies cannot be converted with simple regex find-and-replace. The semantics differ in subtle, silent ways:

- **DATEDIFF argument order** is reversed between SQL Server and PySpark
- **String comparisons** flip from case-insensitive to case-sensitive
- **NULL sort ordering** is opposite (SQL Server: NULLs first in ASC; PySpark: NULLs last in ASC)
- **Window frame defaults** behave differently with duplicate values (RANGE vs ROWS)
- **Decimal arithmetic** silently loses precision without explicit configuration

This tool uses Claude as the conversion engine, orchestrated through a **5-phase pipeline** that first understands the SQL, maps dependencies, plans the conversion with specific per-line instructions, converts each object with targeted guidance, validates across the full generated codebase with dependency context, and auto-fixes common issues -- producing production-quality PySpark code that avoids the top 10 silent failure patterns.

---

## Architecture Overview

```
                          sql2spark Architecture (5-Phase Pipeline)
 ========================================================================================

 INPUT               PHASE 1              PHASE 2                PHASE 3
 -----               -------              -------                -------
 input/*.sql ---> DISCOVERY ---------> PLANNING -----------> CONVERSION
                  |                    |                      |
                  +- Object inventory  +- Dependency graph    +- PySpark .py files
                  +- Dialect detection +- Topological sort    |  (one per object)
                  +- Complexity score  +- Per-object          +- Parallel by
                  +- Line ranges         instructions        |  dependency level
                  +- Construct IDs     +- Gotcha flags        +- Self-correcting
                                       +- Strategy per obj

 PHASE 4                          PHASE 5
 -------                          -------
 CONTEXT-AWARE VALIDATION ---> AUTO-FIX & ACTION ITEMS
 |                              |
 +- ast.parse() (free)          +- Blacklist-based: try fix ALL
 +- Claude review (Sonnet)      |  HIGH/ERROR unless cursor/
 +- Cross-file dependency       |  dynamic SQL/MERGE
 |  context injection      .--> +- Same dep context from Phase 4
 +- Signature matching    /     |  (cross-file signature fixes)
 +- Gotcha verification  /      +- Safety: ast.parse() + truncation
 +- dep_context_by_file /       +- Developer action items:
    (reused by Phase 5)         |  - auto_fixed
                                |  - requires_manual
                                |  - infrastructure_setup
                                |  - recommended_review
                                +- TODO collection

 OUTPUT
 ------
 output/*.py            <-- One PySpark file per SQL object
 output/report.json     <-- Full report with costs + developer action items
```

### Core Design Principles

1. **Phase separation**: Each phase has a single responsibility and runs independently
2. **Knowledge distillation**: Phase 2 reads the full knowledge base once, then produces targeted instructions for Phase 3 -- saving 60-80% on input tokens
3. **Fresh context per object**: Each conversion gets a clean context window via `query()`, preventing context exhaustion on large scripts
4. **Parallel by dependency level**: Objects with no mutual dependencies convert concurrently
5. **Self-correcting**: Phase 3 validates its own output and fixes syntax errors within the same query
6. **Context-aware validation**: Phase 4 injects dependency file signatures so Claude can cross-validate function calls, argument counts, and return types across the whole generated codebase
7. **Safe auto-fix**: Phase 5 fixes mechanical issues (deprecated APIs, missing configs) with an `ast.parse()` safety net -- if the fix breaks syntax, the original is restored immediately
8. **Checkpoint/resume**: Progress is saved after each conversion for resilience

---

## The 5-Phase Pipeline

### Phase 1: Discovery & Complexity Analysis

**What it does**: Reads each SQL file, identifies every discrete object (procedure, function, view, trigger), detects the SQL dialect, and computes a complexity score.

**Model**: Configurable (default: Opus) | **Budget**: $1.00/file | **Max turns**: 15

**How it works**:

1. **Pre-scan** (local regex, zero API cost): The `sql_prescan` MCP tool counts lines, finds CREATE/ALTER statements, detects dialect hints via regex patterns
2. **Claude reads the file**: Uses the `Read` tool with `offset`/`limit` for files over 4000 lines (reads in 2 chunks)
3. **Object identification**: Finds exact line ranges, parameters, references to other objects, temp tables created/used, cursor presence, window function count
4. **Dialect auto-detection**: Matches syntax markers:
   - **T-SQL**: `GO`, `DECLARE @`, `sp_executesql`, `SET NOCOUNT ON`, `@@ROWCOUNT`
   - **PL/SQL**: `CREATE OR REPLACE`, `DBMS_`, `NVL()`, `SYSDATE`
   - **PL/pgSQL**: `$$` delimiters, `LANGUAGE plpgsql`, `RAISE NOTICE`
5. **Complexity scoring**: Weighted formula producing a 1-10 score per object (see [Complexity Scoring](#complexity-scoring-system))

**Tools available**: `Read`, `Glob`, `Grep`, `mcp__sql2spark__sql_prescan`

**Knowledge injected**: `sql_to_pyspark_mapping.md` (to identify constructs) + `known_limitations.md` (to flag non-convertible patterns early)

**Example output** (from a 1017-line T-SQL file):

```json
{
  "file_path": "input/AWLT_ConverterTest_1k.sql",
  "total_lines": 1017,
  "dialect": "tsql",
  "file_complexity": "Standard script",
  "file_complexity_score": 6.1,
  "objects": [
    {
      "name": "usp_AWLT_Converter_Log",
      "type": "procedure",
      "start_line": 28,
      "end_line": 42,
      "line_count": 15,
      "parameters": [
        {"name": "@RunId", "data_type": "uniqueidentifier", "direction": "IN"},
        {"name": "@StepName", "data_type": "nvarchar(200)", "direction": "IN"},
        {"name": "@Message", "data_type": "nvarchar(2000)", "direction": "IN", "default_value": "NULL"}
      ],
      "references": ["dbo.AWLT_Converter_RunLog"],
      "temp_tables_created": [],
      "has_cursor": false,
      "has_dynamic_sql": false,
      "complexity_score": 1.3,
      "complexity_level": "Simple"
    },
    {
      "name": "ufn_SplitCsvInt",
      "type": "function",
      "start_line": 47,
      "end_line": 70,
      "line_count": 24,
      "constructs_used": ["RETURNS TABLE", "WHILE", "CHARINDEX", "SUBSTRING", "TRY_CONVERT"],
      "complexity_score": 1.3,
      "complexity_level": "Simple"
    },
    {
      "name": "usp_AWLT_OneCSV_ConverterTest_1k",
      "type": "procedure",
      "start_line": 614,
      "end_line": 1016,
      "line_count": 403,
      "parameters": [
        {"name": "@StartDate", "data_type": "date", "direction": "IN", "default_value": "NULL"},
        {"name": "@EndDate", "data_type": "date", "direction": "IN", "default_value": "NULL"},
        {"name": "@CustomerIdsCsv", "data_type": "nvarchar(max)", "direction": "IN", "default_value": "NULL"}
      ],
      "references": [
        "dbo.usp_AWLT_Converter_Log", "dbo.ufn_SplitCsvInt",
        "SalesLT.SalesOrderHeader", "SalesLT.Customer"
      ],
      "temp_tables_created": [
        "#CustomerFilter", "#Orders", "#Lines", "#AggA", "#AggB",
        "#CustomerFacts", "#RFM", "#RegionAgg", "#Json", "#JsonParsed", "#QCFail"
      ],
      "has_cursor": true,
      "has_dynamic_sql": true,
      "window_function_count": 3,
      "complexity_score": 6.6,
      "complexity_level": "Complex",
      "known_limitations": [
        "Cursor-based row-by-row processing -- rewrite as vectorized operation",
        "Dynamic SQL (sp_executesql) with runtime predicates -- cannot auto-convert",
        "FOR JSON PATH -- convert to F.to_json(F.struct(...))"
      ]
    }
  ]
}
```

**Enum normalization**: Claude sometimes returns non-canonical values like `"scalar_function"`, `"Moderate-High"`, or `"stored_procedure"`. All model fields use `@field_validator(mode="before")` to normalize these:

- `"scalar_function"` / `"table_function"` / `"udf"` --> `"function"`
- `"stored_procedure"` / `"usp"` --> `"procedure"`
- `"Moderate-High"` / `"Medium"` --> `"Complex"` or `"Moderate"` (fuzzy keyword fallback)
- `"mssql"` / `"sql server"` / `"t-sql"` --> `"tsql"`

---

### Phase 2: Dependency Analysis & Conversion Planning

**What it does**: This is the "thinking" phase. It builds a dependency graph, determines conversion order, and generates **per-object, line-specific conversion instructions** that Phase 3 will use.

**Model**: Configurable (default: Opus) | **Budget**: $1.50 | **Max turns**: 15

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
4. **Per-object conversion instructions**: For EACH object, generates specific, line-by-line guidance

**Tools available**: `Read`, `Grep`

**Knowledge injected**: ALL 5 files (mapping, examples, gotchas, limitations, idioms) -- read once, distilled into per-object instructions

**Why this matters**: Instead of giving Phase 3 the full 15K-token knowledge base for every conversion, Phase 2 distills it into 2-5K tokens of targeted instructions per object. This saves 60-80% on input tokens and produces better results because Claude gets SPECIFIC guidance rather than searching through a 319-line mapping table.

**Example output** (conversion plan):

```json
{
  "total_objects": 3,
  "conversion_levels": [
    {
      "level": 0,
      "description": "No dependencies -- standalone utility objects",
      "objects": ["usp_AWLT_Converter_Log", "ufn_SplitCsvInt"],
      "strategy": "Parallel conversion, direct single-pass each"
    },
    {
      "level": 1,
      "description": "Depends on Level 0 objects (logging proc + CSV splitter)",
      "objects": ["usp_AWLT_OneCSV_ConverterTest_1k"],
      "strategy": "Sequential multi-step conversion, flag cursor/dynamic SQL for manual review"
    }
  ],
  "dependency_edges": [
    {
      "source": "usp_AWLT_OneCSV_ConverterTest_1k",
      "target": "usp_AWLT_Converter_Log",
      "relationship": "calls (EXEC at lines 635, 948, 1012)"
    },
    {
      "source": "usp_AWLT_OneCSV_ConverterTest_1k",
      "target": "ufn_SplitCsvInt",
      "relationship": "calls (SELECT FROM at line 656)"
    }
  ],
  "object_plans": {
    "usp_AWLT_OneCSV_ConverterTest_1k": {
      "conversion_order": 3,
      "complexity": "Complex (6.6)",
      "estimated_tokens": 55000,
      "dependencies_resolved": ["usp_AWLT_Converter_Log", "ufn_SplitCsvInt"],
      "dependency_signatures": "class RunLogger: def log_step(...); def split_csv_int(csv_str) -> list[int]",
      "conversion_instructions": [
        "STRUCTURE: Create @dataclass PipelineParams with 8 fields",
        "STRUCTURE: Main function def run_pipeline(spark, params) -> DataFrame with 11 steps",
        "Line 654-656: CROSS APPLY ufn_SplitCsvInt -> split_csv_int_df(spark, csv_str)",
        "GOTCHA #1: Line 799: DATEDIFF(day, start, end) -> F.datediff(end, start) REVERSED",
        "GOTCHA #2: Line 681: Case-insensitive comparison -> F.lower() on both sides",
        "GOTCHA #3: Lines 823-825: NTILE ORDER BY -> use .asc_nulls_first()/.desc_nulls_last()",
        "Lines 918-943: CURSOR + sp_executesql -> TODO: manual rewrite, predicate-map pattern",
        "Lines 865-874: FOR JSON PATH -> F.to_json(F.struct(...))",
        "Lines 891-897: OPENJSON CROSS APPLY -> F.from_json() with StructType schema"
      ],
      "gotchas_relevant": [
        "#1 DATEDIFF argument order reversed (lines 799, 800)",
        "#2 Case-sensitive string comparison (line 681)",
        "#3 NULL ordering in ORDER BY (lines 823-825, 1002-1006)",
        "#5 Decimal arithmetic precision loss (lines 793, 804)"
      ],
      "limitations_found": [
        "Cursor-based dynamic SQL QC evaluation -- cannot auto-convert sp_executesql",
        "FOR JSON PATH with nested correlated subquery"
      ],
      "strategy": "Break into 11 sub-steps. Convert steps 1-9 and 11 directly. Step 10 (QC cursor) requires TODO."
    }
  }
}
```

---

### Phase 3: SQL-to-PySpark Conversion

**What it does**: Converts each SQL object to a production-quality PySpark `.py` file.

**Model**: Configurable (default: Opus) | **Budget**: $2.50/object | **Max turns**: 25

**How it works**:

1. For each object (in the planned conversion order), spawns a fresh `query()` call
2. Claude reads the specific line range from the SQL file using `Read(offset, limit)`
3. Receives the **targeted conversion instructions** from Phase 2 (not the full knowledge base)
4. Receives **dependency context**: compressed signatures of already-converted objects (function name, params, return type -- typically 5-20 lines per dependency)
5. Writes the `.py` file to `output/` using the `Write` tool
6. Validates its own output using the `validate_pyspark_syntax` MCP tool
7. If validation fails, self-corrects within the same query (has 25 turns budget)

**Tools available**: `Read`, `Write`, `Bash`, `mcp__sql2spark__validate_pyspark_syntax`

**Parallel execution**: Objects at the same dependency level run via `asyncio.gather` with configurable concurrency (default 3, `--parallel` flag).

**Interactive mode** (`--interactive`): Uses `ClaudeSDKClient` instead of `query()`. Claude can use `AskUserQuestion` for ambiguous SQL patterns. User approves/revises/skips each conversion.

**Knowledge injected**: Only the abbreviated style guide in system prompt (~2K tokens) + targeted instructions from Phase 2 in the user prompt

**Example**: Converting `ufn_SplitCsvInt` (T-SQL table-valued function):

SQL input:
```sql
CREATE OR ALTER FUNCTION dbo.ufn_SplitCsvInt (@csv NVARCHAR(MAX))
RETURNS @Out TABLE (Value INT)
AS BEGIN
    DECLARE @pos INT, @token NVARCHAR(20)
    WHILE CHARINDEX(',', @csv) > 0 BEGIN
        SET @pos = CHARINDEX(',', @csv)
        SET @token = LTRIM(RTRIM(SUBSTRING(@csv, 1, @pos - 1)))
        IF TRY_CONVERT(INT, @token) IS NOT NULL
            INSERT @Out VALUES (CONVERT(INT, @token))
        SET @csv = SUBSTRING(@csv, @pos + 1, LEN(@csv))
    END
    -- handle last token
    SET @token = LTRIM(RTRIM(@csv))
    IF TRY_CONVERT(INT, @token) IS NOT NULL
        INSERT @Out VALUES (CONVERT(INT, @token))
    RETURN
END
```

PySpark output:
```python
"""PySpark conversion of AWLT_ConverterTest_1k.sql -- ufn_SplitCsvInt.

Source:  input/AWLT_ConverterTest_1k.sql (lines 47-70)
Target:  Split CSV string of integers into a list or single-column DataFrame.

SQL construct mapping:
  RETURNS @TABLE -> list[int] / DataFrame
  WHILE + CHARINDEX + SUBSTRING -> str.split(',')
  TRY_CONVERT(INT, ...) -> int() with try/except
"""
from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.types import IntegerType, StructField, StructType


def split_csv_int(csv_str: str | None) -> list[int]:
    """Split a comma-separated string into a list of integers.

    Replaces the T-SQL table-valued function dbo.ufn_SplitCsvInt.
    Handles: commas, semicolons, newlines as delimiters.
    Skips non-integer tokens silently (matches TRY_CONVERT behavior).
    """
    if not csv_str:
        return []

    # Normalize delimiters (matches SQL: REPLACE(CHAR(10),','), REPLACE(';',','))
    normalized = csv_str.replace("\n", ",").replace("\r", ",").replace(";", ",")
    normalized = normalized.rstrip(",")

    result: list[int] = []
    for token in normalized.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            result.append(int(token))
        except ValueError:
            pass  # TRY_CONVERT returns NULL for non-integers; we skip
    return result


def split_csv_int_df(spark: SparkSession, csv_str: str | None) -> DataFrame:
    """Return a single-column DataFrame matching the original TVF schema.

    Schema: StructType([StructField('CustomerID', IntegerType(), False)])
    Use this variant when joining with other DataFrames.
    """
    values = split_csv_int(csv_str)
    schema = StructType([StructField("CustomerID", IntegerType(), False)])
    return spark.createDataFrame([(v,) for v in values], schema=schema)
```

---

### Phase 4: Context-Aware Validation

**What it does**: Validates every generated PySpark file with **cross-file dependency context**, catching issues that file-in-isolation validation misses.

**Model**: Sonnet (cheaper, sufficient for review) | **Budget**: $0.30/file | **Max turns**: 10

**The problem with naive validation**: When validating `build_customer_profile.py` in isolation, Claude cannot see that it calls `fn_calculate_discount()` from `calculate_discount.py`. It cannot verify the signature matches, the return type is correct, or that the import chain is wired properly.

**The fix -- cross-file dependency context injection**: For each file being validated, the validator:
1. Looks up the file's dependencies from the Phase 2 `ConversionPlan`
2. Reads each dependency file and extracts function/class signatures
3. Injects those signatures into the validation prompt

**How it works**:

1. **Local syntax check** (zero API cost): `ast.parse()` on each `.py` file, plus pattern checks:
   - Bare `col()` without `F.` prefix
   - `.collect()` usage (OOM risk)
   - TODO comment counting
2. **Dependency context building**: For each file:
   - Resolve SQL object name --> output `.py` file via normalized name lookup
   - Extract function signatures + first docstring line from each dependency file
   - Format as a context block injected into the Claude prompt
3. **Claude review** (Sonnet): Reads the file WITH dependency signatures and checks:
   - DATEDIFF argument order (PySpark: end, start -- reversed vs SQL Server)
   - Case-sensitive string comparisons (need `F.lower()` or `.ilike()`)
   - NULL ordering (explicit `asc_nulls_first()` / `desc_nulls_last()`)
   - Window frame defaults (running totals need `rowsBetween`, not RANGE)
   - Python UDFs where native `F.xxx` functions exist
   - SparkSession missing `.config("spark.sql.decimalOperations.allowPrecisionLoss", False)`
   - Deprecated methods: `.unionAll()` --> `.union()`
   - **Cross-file**: Every function called must exist in dependency files with matching signature
4. **Report generation**: Produces `report.json` with per-object status, cost breakdown, validation issues

**Tools available**: `Read`, `Bash`, `mcp__sql2spark__validate_pyspark_syntax`

**What cross-file validation catches that isolation misses**:
- `stage_sales_data.py` creates a temp DataFrame that `build_customer_profile.py` expects -- **shape mismatch**
- `generate_report.py` calls `calculate_revenue(spark, params)` but the function was generated as `calculate_revenue(spark, start_date, end_date)` -- **argument mismatch**
- `audit_changes.py` imports `from active_products import run_pipeline` but the function is actually `def get_active_products(spark)` -- **wrong function name**

**Example validation prompt** (with dependency context injected):

```
Read and validate: output/awlt_one_csv_converter_test_1k.py

## Dependency Files -- cross-validate every call site against these signatures

### awlt_converter_log.py  (SQL object: usp_AWLT_Converter_Log)
```python
class RunLogger:
    def __init__(self, run_id: str, proc_name: str)
    def log_step(self, step_name: str, step_status: str, message: str | None = None, complete: bool = False) -> None
```

### split_csv_int.py  (SQL object: ufn_SplitCsvInt)
```python
def split_csv_int(csv_str: str | None) -> list[int]
def split_csv_int_df(spark: SparkSession, csv_str: str | None) -> DataFrame
```

Check:
1. Every function called from this file exists in the dependency files above
2. Argument counts and types match
3. Return types are compatible with how the result is used
4. Import statements reference the correct module names
[... existing checklist ...]
```

---

### Phase 5: Auto-Fix & Developer Action Items

**What it does**: Automatically fixes HIGH/ERROR issues in generated code using the validator's exact diagnostics, and produces a categorized developer action items report for everything that needs human attention.

**Model**: Sonnet | **Budget**: $0.50/file | **Max turns**: 10

**Skip with**: `--skip-autofix` flag (issues are still reported, just not fixed)

**Design philosophy -- optimistic auto-fix with safety net**:

The validator (Phase 4) already does the hard work: it identifies the exact issue, the exact line number, and often states the exact fix ("move `orders_df.unpersist()` to AFTER `_step9a_build_payload()` completes"). Phase 5 hands this to Claude and says "apply these fixes."

Instead of whitelisting known fixable patterns (which misses novel issues), we use a **blacklist approach**: try to auto-fix ALL HIGH/ERROR issues **except** those matching known manual patterns (cursor rewrites, dynamic SQL, MERGE logic). The safety net catches bad fixes:
- `ast.parse()` -- reverts immediately if the fix introduces a SyntaxError
- Truncation guard -- reverts if the fixed file is >50% shorter than the original

**How it works**:

1. **Issue classification** (blacklist-based, optimistic):

   | Category | Criteria | Auto-fixable? | Examples |
   |----------|----------|---------------|----------|
   | `infrastructure` | Message matches infra pattern | No | Delta table missing, saveAsTable to non-existent table, JDBC, HDFS/S3, streaming, Kafka |
   | `requires_manual` | HIGH/ERROR + matches manual pattern | No | Cursor rewrite, dynamic SQL, sp_executesql, MERGE, transaction rollback, recursive CTE |
   | `auto_fix` | **HIGH/ERROR + NOT infra + NOT manual** | **Yes** | Everything else -- unpersist ordering, constructor mismatch, deprecated API, missing config, wrong return type, bare `col()` |
   | `recommended_review` | MEDIUM/WARNING/LOW/INFO | No | Null ordering, case sensitivity, OOM risk, style guide items |

   Key insight: **any HIGH/ERROR issue the validator can describe precisely enough for a human to fix, Claude can also fix** -- as long as it has the file content, the issue description, and the dependency context.

2. **Context-aware auto-fix**: Phase 5 receives the **same dependency context** that Phase 4 used for validation (function signatures, class constructors from dependency files). This enables Claude to fix cross-file issues:

   ```
   ## DEPENDENCY FILES (real signatures)
   ### usp_awlt_converter_log.py
   class RunLogger:
       def __init__(self, spark: SparkSession, run_id: str, proc_name: str) -> None
       def log_step(self, step_name: str, step_status: str, ...) -> None
   ```

   With this context, Claude can fix "ConverterLogger() takes 0 args but RunLogger needs 3" by updating the constructor call to match the real signature.

3. **Auto-fix per file**: For files with auto-fixable issues:
   - Read original file content (save as backup)
   - Build prompt with: file content + numbered issue list + dependency signatures
   - Claude fixes ONLY the listed issues (no refactoring)
   - Parse response: JSON summary + complete Python code block
   - **Safety check**: `ast.parse(fixed_content)` -- if SyntaxError, restore original immediately
   - **Truncation guard**: If fixed file is >50% shorter than original, revert (Claude truncated)
   - Status: `FIXED`, `PARTIAL`, `REVERTED`, or `SKIPPED`

4. **Developer action items**: Every issue is classified into one of 4 buckets with prescriptive `how_to_fix` instructions:

**Prescriptive `how_to_fix` lookup** (built-in patterns):

| Issue Pattern | `how_to_fix` Instruction |
|---|---|
| `.unionAll()` | Replace `.unionAll(df2)` with `.union(df2)` |
| SparkSession config | Add `.config('spark.sql.decimalOperations.allowPrecisionLoss', False)` to builder |
| `DecimalType` cast | Wrap with `.cast(DecimalType(precision, scale))` matching original SQL definition |
| Return type annotation | Change `-> None` to `-> DataFrame` on the function signature |
| Case-insensitive | Use `F.lower(col) == F.lower(F.lit(val))` or `.ilike()` for LIKE |
| Bare `col()` | Add `F.` prefix: `col(...)` --> `F.col(...)` |
| `.collect()` | Use `.first()[col]` or `.agg(F.max(...)).collect()[0][0]` for single values |
| Delta table / saveAsTable | Infrastructure: create Delta/Hive table or register in Spark catalog |
| Cursor | Rewrite as `F.lag/F.lead` window function or `groupBy().agg()` |
| Dynamic SQL | Enumerate values and use `F.when()` chain or dict-dispatch pattern |
| MERGE | Use Delta Lake `MERGE INTO` or delete-then-union pattern |

**What Phase 5 can fix that a whitelist approach would miss**:

| Issue | Old (whitelist) | New (blacklist) |
|---|---|---|
| `orders_df.unpersist()` called before it's used | `requires_manual` | **`auto_fix`** -- Claude moves the line |
| Constructor args mismatch (0 vs 3 args) | `requires_manual` | **`auto_fix`** -- Claude updates call with dep context |
| Wrong column name in join condition | `requires_manual` | **`auto_fix`** -- Claude corrects the column name |
| Missing import for a used class | `requires_manual` | **`auto_fix`** -- Claude adds the import |
| Delta table doesn't exist | `requires_manual` | **`infrastructure`** -- correctly classified now |

**Example `developer_action_items` in report.json**:

```json
{
  "developer_action_items": {
    "auto_fixed": [
      {
        "category": "auto_fixed",
        "priority": "high",
        "file": "usp_awlt_one_csv_converter_test_1k.py",
        "description": "orders_df.unpersist() at line 1120 called before _step9a_build_payload() uses it at line 1134",
        "how_to_fix": "Moved orders_df.unpersist() to after _step9a_build_payload() completes."
      },
      {
        "category": "auto_fixed",
        "priority": "high",
        "file": "usp_awlt_one_csv_converter_test_1k.py",
        "description": "ConverterLogger() stub takes 0 args but real RunLogger needs (spark, run_id, proc_name)",
        "how_to_fix": "Updated constructor call to RunLogger(spark, run_id, proc_name) using dependency signatures."
      }
    ],
    "requires_manual": [
      {
        "category": "requires_manual",
        "priority": "high",
        "file": "awlt_one_csv_converter_test_1k.py",
        "description": "CURSOR at lines 918-943 -- no direct PySpark equivalent",
        "how_to_fix": "Rewrite as F.lag/F.lead window function or groupBy().agg(). The QC predicates stored in AWLT_QC_Definition must be translated to PySpark SQL or DataFrame API."
      }
    ],
    "infrastructure_setup": [
      {
        "category": "infrastructure",
        "priority": "high",
        "file": "usp_awlt_converter_log.py",
        "description": "Writes to Delta table 'dbo.AWLT_Converter_RunLog' but table does not exist in Spark catalog",
        "how_to_fix": "Create the Delta table in the Spark metastore or register via spark.sql('CREATE TABLE IF NOT EXISTS ...')"
      }
    ],
    "recommended_review": [
      {
        "category": "recommended_review",
        "priority": "medium",
        "file": "usp_awlt_one_csv_converter_test_1k.py",
        "description": ".collect() found -- may cause OOM on large datasets",
        "how_to_fix": "Use .first()[col] or .agg(F.max(...)).collect()[0][0] for single values.",
        "line": 813
      }
    ],
    "todos_in_code": [
      "usp_awlt_one_csv_converter_test_1k.py: # TODO: Dynamic SQL via sp_executesql at SQL lines 931-934",
      "usp_awlt_one_csv_converter_test_1k.py: # TODO: Cursor at SQL lines 918-943 needs manual rewrite"
    ],
    "summary": "2 issues auto-fixed. 1 requires manual rewrite. 1 needs infrastructure setup. 18 flagged for review. 11 TODOs remain."
  }
}
```

---

## Complexity Scoring System

Every SQL object gets a complexity score (1-10) computed from 7 weighted factors:

| Factor | Weight | Scoring |
|--------|--------|---------|
| **Line count** | 25% | <=50 lines --> 1, 50-200 --> 3, 200-500 --> 5, 500-1000 --> 7, >1000 --> 10 |
| **Dependency count** | 20% | 0 refs --> 1, 1-2 --> 3, 3-5 --> 5, 6-10 --> 7, >10 --> 10 |
| **Temp table count** | 15% | 0 --> 1, 1-2 --> 3, 3-5 --> 5, >5 --> 7 |
| **Cursor / dynamic SQL** | 15% | Absent --> 0, Present --> 10 |
| **Window function count** | 10% | 0 --> 1, 1-3 --> 3, 4-6 --> 5, >6 --> 7 |
| **Control flow depth** | 10% | Flat --> 1, Moderate nesting --> 5, Deeply nested --> 10 |
| **Transaction complexity** | 5% | None --> 1, Simple --> 3, Nested/savepoints --> 7 |

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
Phase 1             Phase 2              Phase 3            Phase 4         Phase 5
-------             -------              -------            -------         -------
mapping.md -->      ALL 5 files -->      Abbreviated        gotchas.md      Issues from
  identify            distill into         style guide        idioms.md       Phase 4
  constructs          per-object           (2K tokens)        (7K tokens)     classified
limitations.md -->    instructions         + targeted         + cross-file    into 4
  flag issues         (2-5K per obj)       instructions       dep context     categories
                                           from Phase 2                       with
                                           (2-5K per obj)                     how_to_fix
```

---

## Agent Orchestration Strategy

### Why `query()` per object, not `ClaudeSDKClient` for all conversions?

Each procedure conversion consumes 40-80K tokens of context (SQL source + system prompt + instructions + response). After converting 3-4 procedures in a stateful session, the context is exhausted and older conversation is compressed, losing critical details.

Using `query()` per object gives each conversion a **clean context window**. The trade-off is no cross-conversion context, which we compensate for by passing compressed dependency signatures (5-20 lines per dependency).

### Why Python `asyncio.gather`, not SDK sub-agents?

The SDK's Agent tool spawns sub-agents that Claude controls. For our use case, the Python orchestrator already knows the dependency graph and which objects can parallelize. Using `asyncio.gather` on multiple `query()` calls gives us:
- Explicit control over concurrency limits (semaphore-bounded)
- Per-object error handling and retry
- Per-object cost tracking
- No reliance on Claude deciding when to parallelize

### SDK features used:

| Feature | Where | Why |
|---------|-------|-----|
| `query()` | Phases 1-4 (automated) | Stateless one-shot for independent tasks |
| `ClaudeSDKClient` | Phase 3 (interactive) | Multi-turn for human-in-the-loop |
| `output_format` | Phases 1, 2 | Guaranteed structured JSON responses |
| `allowed_tools` | All phases | Per-phase tool restriction |
| `mcp_servers` | Phases 1, 3, 4 | Custom tools (sql_prescan, validate_pyspark_syntax) |
| `env` | All phases | Provider switching (Anthropic/Bedrock) |
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

**Without Phase 2** (naive approach -- full knowledge per conversion):
```
Each conversion: ~15K tokens (knowledge) + ~40K tokens (SQL source + prompt)
20 objects: 15K x 20 = 300K tokens on knowledge alone
```

**With Phase 2** (our approach -- targeted instructions):
```
Phase 2: ~15K tokens (knowledge, read once)
Each conversion: ~3K tokens (targeted instructions) + ~40K tokens (SQL source + prompt)
20 objects: 3K x 20 = 60K tokens on instructions
Net savings: ~225K input tokens = ~$3.37 on Opus pricing
```

### Prompt caching amplifies savings:

The Claude Agent SDK automatically caches repeated system prompts. Phase 3's system prompt is identical across all conversion calls (~2K tokens). After the first call, subsequent calls read from cache at 10% cost -- effectively making the system prompt free.

### Cost estimate for a typical 5K-line file with 20 procedures:

| Phase | Calls | Model | Est. Cost |
|-------|-------|-------|-----------|
| Discovery | 1 | Opus | ~$1.50 |
| Planning | 1 | Opus | ~$1.20 |
| Conversion | 20 | Opus | ~$35.00 |
| Validation | 20 | Sonnet | ~$1.00 |
| Auto-Fix | ~5 | Sonnet | ~$1.50 |
| **Total** | | | **~$40.20** |

---

## Project Structure

```
3xcodeconvertor/
  input/                          <-- Drop SQL files here
  output/                         <-- Converted PySpark files + report.json
  knowledge/                      <-- 5 curated reference documents
    sql_to_pyspark_mapping.md       319 lines -- construct mapping
    few_shot_examples.md            199 lines -- before/after examples
    critical_gotchas.md             193 lines -- top 10 silent failures
    known_limitations.md            130 lines -- non-convertible patterns
    pyspark_idioms.md               296 lines -- output style guide

  converter.py                    <-- CLI entry point (argparse)
  orchestrator.py                 <-- Pipeline: Phase 1 -> 2 -> 3 -> 4 -> 5
  config.py                       <-- ConverterConfig dataclass
  models.py                       <-- Pydantic schemas + JSON output schemas
  tools.py                        <-- 2 custom MCP tools
  .env                            <-- API keys, provider, model settings

  agents/
    prompts.py                    <-- Knowledge loader + 5 system prompts
    options.py                    <-- ClaudeAgentOptions factory (6 builders)

  phases/
    discovery.py                  <-- Phase 1: Object inventory + complexity
    planning.py                   <-- Phase 2: Dependency graph + conversion plan
    conversion.py                 <-- Phase 3: Parallel + interactive conversion
    validation.py                 <-- Phase 4: Context-aware validation + report
    auto_fix.py                   <-- Phase 5: Auto-fix + developer action items
```

---

## Usage

### Prerequisites

- Python 3.12+
- Claude Agent SDK (`claude-agent-sdk>=0.1.51`)
- Claude CLI installed (`curl -fsSL https://claude.ai/install.sh | bash`)
- API credentials: either `ANTHROPIC_API_KEY` or AWS Bedrock credentials

### Quick start

```bash
cd 3xcodeconvertor

# Drop your SQL files in input/
cp /path/to/your/scripts/*.sql input/

# Run full 5-phase pipeline
uv run converter.py

# Dry run -- discovery + planning only, no conversion
uv run converter.py --dry-run

# Interactive mode -- approve each conversion
uv run converter.py --interactive

# Skip auto-fix (Phase 5) -- still get action items in report
uv run converter.py --skip-autofix

# With options
uv run converter.py --budget 25.0 --parallel 5 --verbose
```

### CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--interactive` | off | Approve each conversion (human-in-the-loop) |
| `--budget FLOAT` | 50.0 | Total cost cap in USD |
| `--parallel INT` | 3 | Max concurrent conversions |
| `--dry-run` | off | Phase 1 + 2 only (no conversion) |
| `--skip-autofix` | off | Skip Phase 5 auto-fix (issues still reported) |
| `--output-dir PATH` | `./output` | Custom output directory |
| `--model MODEL` | from .env | Conversion model: `opus`, `sonnet`, `haiku` |
| `--provider PROVIDER` | from .env | LLM provider: `anthropic`, `bedrock` |
| `--verbose` / `-v` | off | Show all tool calls and intermediate outputs |

### Example banner output

```
============================================================
  sql2spark -- SQL to PySpark Converter
  Powered by Claude Agent SDK
============================================================
  Workspace:  /path/to/3xcodeconvertor
  Input:      /path/to/input (3 files)
  Output:     /path/to/output
  Provider:   AWS Bedrock (us-east-1)
  Model:      sonnet -> us.anthropic.claude-sonnet-4-6
  Validation: sonnet
  Auto-fix:   sonnet
  Budget:     $50.00
  Parallel:   3
  Mode:       Automated
  Phase 5:    Enabled  ($0.50/file budget)
============================================================
```

---

## Configuration

### Environment variables (`.env` file)

All settings can be configured via `.env` -- no CLI args needed for the normal flow:

```env
# === Provider (choose one) ===

# Option 1: Anthropic API (default)
SQL2SPARK_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Option 2: AWS Bedrock
# SQL2SPARK_PROVIDER=bedrock
# AWS_ACCESS_KEY_ID=AKIA...
# AWS_SECRET_ACCESS_KEY=...
# AWS_REGION=us-east-1

# === Models ===
SQL2SPARK_MODEL=opus                    # Phase 1-3 (default: opus)
SQL2SPARK_VALIDATION_MODEL=sonnet       # Phase 4 (default: sonnet)
SQL2SPARK_AUTOFIX_MODEL=sonnet          # Phase 5 (default: sonnet)
SQL2SPARK_FALLBACK_MODEL=sonnet         # Fallback if primary unavailable
```

### Config settings (`config.py`)

| Setting | Default | Env var | Description |
|---------|---------|---------|-------------|
| `provider` | `"anthropic"` | `SQL2SPARK_PROVIDER` | `"anthropic"` or `"bedrock"` |
| `conversion_model` | `"opus"` | `SQL2SPARK_MODEL` | Model for Phases 1-3 |
| `validation_model` | `"sonnet"` | `SQL2SPARK_VALIDATION_MODEL` | Model for Phase 4 |
| `auto_fix_model` | `"sonnet"` | `SQL2SPARK_AUTOFIX_MODEL` | Model for Phase 5 |
| `fallback_model` | `"sonnet"` | `SQL2SPARK_FALLBACK_MODEL` | Fallback model |
| `total_budget_usd` | `50.0` | -- | Pipeline-wide cost cap |
| `discovery_budget_per_file` | `1.00` | -- | Phase 1 per-file cap |
| `planning_budget` | `1.50` | -- | Phase 2 cap |
| `conversion_budget_per_object` | `2.50` | -- | Phase 3 per-object cap |
| `validation_budget_per_file` | `0.30` | -- | Phase 4 per-file cap |
| `auto_fix_budget_per_file` | `0.50` | -- | Phase 5 per-file cap |
| `max_parallel_conversions` | `3` | -- | Concurrency limit |
| `large_file_threshold` | `4000` | -- | Lines above which files are chunked |

---

## Provider Setup (Anthropic vs Bedrock)

### Anthropic API (default)

```env
# .env
SQL2SPARK_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-api03-...
SQL2SPARK_MODEL=opus
```

```bash
uv run converter.py
```

### AWS Bedrock

```env
# .env
SQL2SPARK_PROVIDER=bedrock
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
SQL2SPARK_MODEL=sonnet
```

```bash
uv run converter.py
```

**Bedrock model mapping** (automatic):

| Shorthand | Bedrock Model ID |
|-----------|-----------------|
| `opus` | `us.anthropic.claude-opus-4-6-v1` |
| `sonnet` | `us.anthropic.claude-sonnet-4-6` |
| `haiku` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |

The banner shows the resolved model ID when using Bedrock:
```
  Provider:   AWS Bedrock (us-east-1)
  Model:      sonnet -> us.anthropic.claude-sonnet-4-6
```

### Switching providers

Just change your `.env` file -- no code changes needed. CLI args (`--provider`, `--model`) override `.env` for one-off runs:

```bash
# Override .env for a single run
uv run converter.py --provider anthropic --model haiku
```

---

## How It Handles Large Files

SQL files vary dramatically in size. The pipeline adapts:

| File Size | Strategy |
|-----------|----------|
| <500 lines | Single `Read()` call, simple script classification |
| 500-2000 lines | Single `Read()` call, standard complexity analysis |
| 2000-4000 lines | Single `Read()` call (fits in context), detailed analysis |
| 4000-8000 lines | Two-chunk reading: `Read(offset=0, limit=2500)` + `Read(offset=2500)` |
| >8000 lines | Two-chunk reading, enterprise script classification |

Individual objects (procedures, functions) are typically 50-500 lines. Phase 3 reads only the relevant line range using `Read(offset=start_line-1, limit=line_count)`, so even a 5000-line file doesn't flood the context -- Claude reads only the 200-line procedure it's converting.

---

## Error Handling & Resilience

| Scenario | Handling |
|----------|---------|
| API rate limit | 3 retries with exponential backoff (2s, 4s, 8s) |
| Opus unavailable | Falls back to Sonnet with warning |
| Budget exceeded | Halts gracefully, reports what was completed |
| Syntax error in Phase 3 output | Self-corrects (validate + rewrite within same query) |
| Syntax error after Phase 5 fix | **Reverts to original** -- safety guarantee via `ast.parse()` |
| Phase 5 fix truncates file | **Reverts** -- truncation guard (>50% shorter = revert) |
| Phase 5 cross-file mismatch | Fixed using dependency context (same signatures from Phase 4) |
| Phase 3 object failure | Marks as failed, continues with next object |
| Phase 4 critical issue | Logged in report, Phase 5 attempts auto-fix (blacklist-based: tries all HIGH/ERROR unless cursor/dynamic SQL/MERGE) |
| Interrupted mid-run | Checkpoint saved after each conversion; re-running skips completed |
| Claude returns invalid JSON | 4-level fallback: direct parse --> code block extraction --> brace matching --> skip |
| Non-canonical enum values | `@field_validator(mode="before")` with fuzzy keyword fallback |
| AWS credentials missing | `ValueError` with clear message at startup |

---

## Output Format

### Per-object PySpark files

Each generated `.py` file follows the style guide from `pyspark_idioms.md`:

```python
"""PySpark conversion of sales_etl.sql -- usp_LoadCustomers.

Source:  input/sales_etl.sql (lines 15-280)
Target:  Load and transform customer data with region mapping

SQL construct mapping:
  CTE -> DataFrame variable, LEFT JOIN, ROW_NUMBER -> Window + F.row_number(),
  ISNULL -> F.coalesce, SELECT INTO #temp -> .cache()
"""
from __future__ import annotations

from dataclasses import dataclass
from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql.types import DecimalType


@dataclass
class PipelineParams:
    start_date: str = "2024-01-01"
    region_filter: str | None = None


def _step1_customer_staging(spark: SparkSession, params: PipelineParams) -> DataFrame:
    """Step 1 -- customer staging with region mapping (SQL lines 30-120)."""
    ...


def run_pipeline(spark: SparkSession, params: PipelineParams) -> DataFrame:
    """Entry point for the converted pipeline."""
    ...
```

### Conversion report (`output/report.json`)

```json
{
  "total_objects": 3,
  "converted": 3,
  "failed": 0,
  "needs_review": 0,
  "total_cost_usd": 3.87,
  "total_duration_ms": 225000,
  "file_complexity": "Standard script",
  "cost_breakdown": {
    "discovery": 0.48,
    "planning": 0.39,
    "conversion": 2.10,
    "validation": 0.55,
    "auto_fix": 0.35
  },
  "objects": [
    {
      "object_name": "usp_AWLT_Converter_Log",
      "status": "converted",
      "output_file": "output/awlt_converter_log.py",
      "cost_usd": 0.25,
      "turns_used": 4
    }
  ],
  "validation_issues": [
    {
      "file": "awlt_one_csv_converter_test_1k.py",
      "severity": "HIGH",
      "message": "Cursor-based QC evaluation cannot be auto-converted",
      "line": 245
    }
  ],
  "auto_fix_results": [
    {
      "file_path": "output/awlt_converter_log.py",
      "status": "fixed",
      "issues_attempted": 1,
      "issues_fixed": 1,
      "was_reverted": false,
      "cost_usd": 0.08
    }
  ],
  "developer_action_items": {
    "auto_fixed": [...],
    "requires_manual": [...],
    "infrastructure_setup": [...],
    "recommended_review": [...],
    "todos_in_code": [...],
    "summary": "1 issue auto-fixed. 1 requires manual rewrite. 1 needs infra setup. 5 for review."
  }
}
```

---

## Real-World Example

### Input: `AWLT_ConverterTest_1k.sql` (1017 lines, T-SQL)

A real AdventureWorksLT2022 analytics script with:
- 3 objects (1 logging proc, 1 CSV splitter function, 1 main analytics pipeline)
- 11 temp tables, 3 window functions, cursor, dynamic SQL, FOR JSON PATH
- Cross-object dependencies: main proc calls both helper objects

### Dry run output:

```
PHASE 1: DISCOVERY & COMPLEXITY ANALYSIS
  Discovery complete: $0.4843 | 10 turns | 92720ms
  3 objects across 1 files
    - usp_AWLT_Converter_Log (procedure, 15 lines, Simple 1.3)
    - ufn_SplitCsvInt (function, 24 lines, Simple 1.3)
    - usp_AWLT_OneCSV_ConverterTest_1k (procedure, 403 lines, Complex 6.6)

PHASE 2: DEPENDENCY ANALYSIS & CONVERSION PLANNING
  Planning complete: $0.3863 | 5 turns | 130632ms
  2 levels, 3 objects planned
    Level 0: Parallel -- usp_AWLT_Converter_Log, ufn_SplitCsvInt
    Level 1: Sequential -- usp_AWLT_OneCSV_ConverterTest_1k

Total cost: $0.87 (discovery + planning only)
```

### What the converter handles vs what needs manual attention:

| SQL Construct | Auto-converted? | How |
|---|---|---|
| 11 temp tables | Yes | --> DataFrame variables with `.cache()` |
| CTEs (WITH...AS) | Yes | --> intermediate DataFrame variables |
| 3 NTILE window functions | Yes | --> `F.ntile(5).over(Window.orderBy(...))` |
| CROSS APPLY ufn_SplitCsvInt | Yes | --> `split_csv_int_df(spark, csv_str)` |
| DATEDIFF (reversed args) | Yes | --> `F.datediff(end, start)` (gotcha flagged) |
| FOR JSON PATH | Yes | --> `F.to_json(F.struct(...))` |
| OPENJSON + CROSS APPLY | Yes | --> `F.from_json()` with StructType schema |
| TRY/CATCH | Yes | --> `try/except` |
| CURSOR + dynamic SQL | No | --> TODO with predicate-map pattern suggestion |
| 260 QC rule INSERTs | No | --> Infrastructure: load from CSV/Parquet |
| CREATE TABLE (permanent) | No | --> Infrastructure: Delta/Hive DDL |
