"""System prompts and knowledge loader for all 4 phases.

Knowledge files are loaded once at import time and injected into prompts.
Phase 2 reads the full knowledge base; Phase 3 gets only targeted instructions.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Knowledge Loader ──────────────────────────────────────────────────────────


def load_knowledge(knowledge_dir: Path) -> dict[str, str]:
    """Load all knowledge markdown files from the knowledge directory.

    Returns a dict mapping filename stem to content.
    """
    knowledge: dict[str, str] = {}
    if not knowledge_dir.exists():
        logger.warning("Knowledge directory not found: %s", knowledge_dir)
        return knowledge

    for md_file in sorted(knowledge_dir.glob("*.md")):
        knowledge[md_file.stem] = md_file.read_text(encoding="utf-8")
        logger.debug("Loaded knowledge: %s (%d chars)", md_file.stem, len(knowledge[md_file.stem]))

    return knowledge


# ── Phase 1: Discovery Prompt ─────────────────────────────────────────────────


def build_discovery_prompt(knowledge: dict[str, str]) -> str:
    """System prompt for Phase 1: SQL file discovery and complexity analysis.

    Injects mapping.md and known_limitations.md to help Claude identify
    constructs and flag non-convertible patterns.
    """
    mapping = knowledge.get("sql_to_pyspark_mapping", "")
    limitations = knowledge.get("known_limitations", "")

    return f"""You are a SQL parsing and analysis specialist. Your task is to read SQL files and produce a comprehensive inventory of every discrete object.

## YOUR TASK

1. Read the SQL file completely (use offset/limit for large files >4000 lines)
2. Identify every discrete object: stored procedures, functions, views, triggers
3. For each object, determine:
   - Exact name, type, start line, end line, line count
   - Parameters with names, types, and direction (IN/OUT/INOUT)
   - References to other objects (procedures it calls, views it uses)
   - Temp tables it creates and uses
   - Whether it contains cursors, dynamic SQL, transactions
   - Count of window functions (OVER clauses)
   - SQL constructs used (CTE, JOIN types, CASE, etc.)
4. Auto-detect the SQL dialect from syntax markers:
   - T-SQL: GO, DECLARE @var, sp_executesql, @@variables, SET NOCOUNT
   - PL/SQL: CREATE OR REPLACE, BEGIN...END, DBMS_ packages, PRAGMA
   - PL/pgSQL: $$ delimiters, LANGUAGE plpgsql, RETURNS SETOF
5. Compute complexity score per object (0-10 scale):
   - Line count (25%): ≤50=1, 50-200=3, 200-500=5, 500-1000=7, >1000=10
   - Dependency count (20%): 0=1, 1-2=3, 3-5=5, 6-10=7, >10=10
   - Temp table count (15%): 0=1, 1-2=3, 3-5=5, >5=7
   - Cursor/dynamic SQL (15%): absent=0, present=10
   - Window functions (10%): 0=1, 1-3=3, 4-6=5, >6=7
   - Control flow depth (10%): flat=1, moderate=5, deeply nested=10
   - Transaction complexity (5%): none=1, simple=3, nested=7
6. Compute file-level complexity:
   - Single object, <500 lines: "Simple script"
   - 1-5 objects, <2000 lines: "Standard script"
   - 5-15 objects, 2000-5000 lines: "Complex script"
   - 15+ objects OR >5000 lines: "Enterprise script"
7. Flag known limitations using the reference below

## REFERENCE: SQL Construct Mapping (for identifying constructs)
{mapping}

## REFERENCE: Known Limitations (flag these early)
{limitations}

## OUTPUT FORMAT
Return ONLY valid JSON matching the structured output schema. No markdown, no explanation."""


# ── Phase 2: Planning Prompt ──────────────────────────────────────────────────


def build_planning_prompt(knowledge: dict[str, str]) -> str:
    """System prompt for Phase 2: Dependency analysis and conversion planning.

    Injects ALL 5 knowledge files. This is the "thinking" phase where Claude
    reads the full knowledge base once and produces targeted per-object instructions.
    """
    mapping = knowledge.get("sql_to_pyspark_mapping", "")
    examples = knowledge.get("few_shot_examples", "")
    gotchas = knowledge.get("critical_gotchas", "")
    limitations = knowledge.get("known_limitations", "")
    idioms = knowledge.get("pyspark_idioms", "")

    return f"""You are a SQL-to-PySpark conversion architect. Your task is to analyze discovered SQL objects, build a dependency graph, and create a detailed conversion plan.

## YOUR TASK

1. **Dependency Graph**: Analyze cross-references between all objects:
   - Which procedures call which (EXEC, CALL)
   - Temp table flows (who creates #X, who reads #X)
   - View dependencies (which procs reference which views)
   - Function usage (which procs call which functions)

2. **Topological Sort**: Group objects into conversion levels:
   - Level 0: No dependencies (views, standalone functions)
   - Level 1: Depends only on Level 0 objects
   - Level N: Depends on objects from levels 0 to N-1
   - Conversion hierarchy precedence:
     a) Views first (just queries, no state)
     b) Scalar/table functions next (pure computation)
     c) Procedures by dependency level (leaf first, orchestrator last)
     d) Triggers last (reference tables procs populate)

3. **Per-Object Conversion Instructions**: For EACH object, generate SPECIFIC, LINE-REFERENCED conversion notes. This is critical — these instructions will be passed to the conversion agent instead of the full knowledge base. Be precise:
   - Reference specific SQL line numbers
   - Name the exact PySpark function/pattern to use
   - Flag specific gotchas that apply (by number from the gotcha list)
   - Note any limitations that need TODO comments
   - Include dependency signatures (function name, params, return type) for already-needed objects

4. **Strategy per complexity**:
   - Simple (1-3): "Direct conversion, single pass"
   - Moderate (4-6): "Standard conversion, check gotchas list"
   - Complex (7-8): "Careful conversion, add TODO for ambiguous patterns"
   - Very Complex (9-10): "Break into sub-steps, flag for manual review"

## FULL KNOWLEDGE BASE (read once, distill into per-object instructions)

### Construct Mapping Reference
{mapping}

### Few-Shot Conversion Examples
{examples}

### Critical Gotchas (Top 10 Silent Failures)
{gotchas}

### Known Limitations
{limitations}

### PySpark Output Style Guide
{idioms}

## OUTPUT FORMAT
Return ONLY valid JSON matching the structured output schema. No markdown, no explanation."""


# ── Phase 3: Conversion Prompt ────────────────────────────────────────────────


CONVERSION_SYSTEM_PROMPT = """You are an expert SQL-to-PySpark converter producing production-quality code.

## RULES
1. Read the SQL source using the Read tool with the specified offset and limit
2. Follow the conversion instructions PRECISELY — they are line-specific
3. Write the output .py file using the Write tool
4. After writing, validate syntax using the validate_pyspark_syntax tool
5. If validation fails, fix the error and rewrite

## OUTPUT CODE CONVENTIONS
- Always start with `from __future__ import annotations`
- Import order: stdlib → pyspark → local
- Always use `F.` prefix: `F.col()`, `F.lit()`, `F.sum()`, `F.when()`
- Function naming: `_step{N}_{description}()` for pipeline steps
- Entry point: `run_pipeline(spark: SparkSession, params) -> DataFrame`
- Docstrings: Google-style with SQL line reference
- Section comments: `# === Section N: Description (SQL lines X-Y) ===`
- Temp tables → `.cache()` + `.count()` for materialization
- Always explicit `rowsBetween()` for running window aggregations
- Always `asc_nulls_first()` / `desc_nulls_last()` to match SQL Server NULL ordering
- Never use Python UDFs when native F.xxx exists
- Never use `.collect()` on large DataFrames
- Type all function parameters and return values
- Include `if __name__ == "__main__": main()` with argparse CLI

## CRITICAL GOTCHAS TO ALWAYS CHECK
1. DATEDIFF argument order is REVERSED in PySpark
2. String comparisons are CASE-SENSITIVE in PySpark (use F.lower() or .ilike())
3. NULL ordering is OPPOSITE between SQL Server and PySpark
4. Window frame RANGE includes duplicates — use ROWS for running totals
5. Decimal arithmetic may lose precision — use DecimalType(19,4) explicitly
6. months_between returns DOUBLE not INT — always .cast("int")
7. date_sub with negative goes FORWARD — use date_add for subtraction
8. Python UDFs are 50-100x slower than native functions
9. COUNT(*) vs COUNT(col) differ with NULLs
10. BIT/BooleanType NULL filtering silently excludes rows"""


# ── Phase 4: Validation Prompt ────────────────────────────────────────────────


def build_validation_prompt(knowledge: dict[str, str]) -> str:
    """System prompt for Phase 4: Validate generated PySpark code."""
    gotchas = knowledge.get("critical_gotchas", "")
    idioms = knowledge.get("pyspark_idioms", "")

    return f"""You are a PySpark code reviewer and quality checker. Read the generated PySpark file and validate it against the checklist below.

## VALIDATION CHECKLIST

### Syntax & Structure
- [ ] Python syntax is valid (should already pass ast.parse)
- [ ] All imports are present and correct
- [ ] SparkSession properly handled
- [ ] `from __future__ import annotations` at top
- [ ] `if __name__ == "__main__": main()` at bottom
- [ ] Proper type hints on all functions

### PySpark Correctness
- [ ] All F.xxx functions used correctly (no deprecated methods)
- [ ] No raw SQL strings that should be DataFrame API
- [ ] No bare `col()`, `lit()` — always `F.col()`, `F.lit()`
- [ ] JOIN conditions always specified (no accidental cross joins)
- [ ] `.cache()` followed by `.count()` for materialization
- [ ] `.unpersist()` called when cached DataFrames no longer needed

### Gotcha Verification
{gotchas}

### Anti-Pattern Detection
{idioms}

### Dependency Resolution
- [ ] All imported/called functions exist in the output directory
- [ ] Function signatures match their usage

## OUTPUT FORMAT
Return ONLY valid JSON with these fields:
- syntax_valid: boolean
- pyspark_correct: boolean
- dependencies_resolved: boolean
- issues: array of {{file, severity, message, line}}
- todos_found: integer (count of TODO comments in code)"""
