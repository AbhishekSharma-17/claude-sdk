"""Custom MCP tools for the sql2spark converter.

Two tools packaged into a single MCP server:
  1. sql_prescan — regex pre-scan of SQL files (no API cost)
  2. validate_pyspark_syntax — ast.parse() on generated code
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server, tool


# ── Tool 1: SQL Pre-scan ─────────────────────────────────────────────────────


_CREATE_PATTERNS = [
    (r"CREATE\s+(OR\s+REPLACE\s+)?PROCEDURE", "procedure"),
    (r"CREATE\s+(OR\s+REPLACE\s+)?FUNCTION", "function"),
    (r"CREATE\s+(OR\s+REPLACE\s+)?VIEW", "view"),
    (r"CREATE\s+(OR\s+REPLACE\s+)?TRIGGER", "trigger"),
    (r"ALTER\s+PROCEDURE", "procedure"),
    (r"ALTER\s+FUNCTION", "function"),
]

_DIALECT_HINTS = {
    "tsql": [r"\bGO\b", r"DECLARE\s+@", r"sp_executesql", r"SET\s+NOCOUNT", r"@@\w+"],
    "plsql": [r"CREATE\s+OR\s+REPLACE", r"\bBEGIN\b.*\bEND\b", r"DBMS_\w+", r"PRAGMA\b"],
    "plpgsql": [r"\$\$", r"LANGUAGE\s+plpgsql", r"RETURNS\s+SETOF"],
}


@tool(
    name="sql_prescan",
    description=(
        "Pre-scan a SQL file using regex to count lines, detect object boundaries, "
        "and identify dialect hints. Runs locally with zero API cost. "
        "Use this BEFORE reading the file with Claude to get a head start."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the SQL file to pre-scan",
            },
        },
        "required": ["file_path"],
    },
)
async def sql_prescan(args: dict) -> dict:
    """Pre-scan a SQL file for object boundaries and dialect hints."""
    file_path = args["file_path"]
    path = Path(file_path)

    if not path.exists():
        return _text_result(json.dumps({"error": f"File not found: {file_path}"}))

    content = path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    total_lines = len(lines)

    # Find object boundaries
    objects_found: list[dict] = []
    for i, line in enumerate(lines, start=1):
        upper_line = line.upper().strip()
        for pattern, obj_type in _CREATE_PATTERNS:
            if re.search(pattern, upper_line, re.IGNORECASE):
                # Extract name (rough: next non-keyword token)
                name_match = re.search(
                    r"(?:PROCEDURE|FUNCTION|VIEW|TRIGGER)\s+(?:\[?\w+\]?\.)?(\[?\w+\]?)",
                    line,
                    re.IGNORECASE,
                )
                name = name_match.group(1).strip("[]") if name_match else f"unknown_{i}"
                objects_found.append({
                    "name": name,
                    "type": obj_type,
                    "start_line": i,
                    "pattern_matched": pattern,
                })
                break

    # Detect dialect
    dialect_scores: dict[str, int] = {d: 0 for d in _DIALECT_HINTS}
    for dialect, patterns in _DIALECT_HINTS.items():
        for pattern in patterns:
            matches = len(re.findall(pattern, content, re.IGNORECASE | re.MULTILINE))
            dialect_scores[dialect] += matches

    detected_dialect = max(dialect_scores, key=lambda d: dialect_scores[d])
    if dialect_scores[detected_dialect] == 0:
        detected_dialect = "unknown"

    # Complexity hints
    cursor_count = len(re.findall(r"\bCURSOR\b", content, re.IGNORECASE))
    dynamic_sql = len(re.findall(r"\bsp_executesql\b|\bEXEC\s*\(", content, re.IGNORECASE))
    window_funcs = len(re.findall(r"\bOVER\s*\(", content, re.IGNORECASE))
    temp_tables = len(re.findall(r"#\w+", content))
    transactions = len(re.findall(r"\bBEGIN\s+TRAN", content, re.IGNORECASE))

    result = {
        "file_path": file_path,
        "total_lines": total_lines,
        "detected_dialect": detected_dialect,
        "dialect_scores": dialect_scores,
        "objects_found": objects_found,
        "object_count": len(objects_found),
        "hints": {
            "cursor_count": cursor_count,
            "dynamic_sql_count": dynamic_sql,
            "window_function_count": window_funcs,
            "temp_table_references": temp_tables,
            "transaction_count": transactions,
        },
    }
    return _text_result(json.dumps(result, indent=2))


# ── Tool 2: PySpark Syntax Validator ──────────────────────────────────────────


@tool(
    name="validate_pyspark_syntax",
    description=(
        "Validate generated PySpark code for Python syntax correctness using ast.parse(). "
        "Returns pass/fail with error details if syntax is invalid. "
        "Use this after writing a .py file to catch syntax errors immediately."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python/PySpark code string to validate",
            },
            "file_path": {
                "type": "string",
                "description": "Optional file path — if provided, reads from file instead of code param",
            },
        },
    },
)
async def validate_pyspark_syntax(args: dict) -> dict:
    """Validate Python syntax of generated PySpark code."""
    code = args.get("code")
    file_path = args.get("file_path")

    if file_path:
        path = Path(file_path)
        if not path.exists():
            return _text_result(json.dumps({"valid": False, "error": f"File not found: {file_path}"}))
        code = path.read_text(encoding="utf-8")

    if not code:
        return _text_result(json.dumps({"valid": False, "error": "No code or file_path provided"}))

    try:
        ast.parse(code)
        # Additional checks
        warnings: list[str] = []
        if "from pyspark" not in code and "import pyspark" not in code:
            warnings.append("No PySpark imports found")
        if "F.udf" in code or "@udf" in code:
            warnings.append("Python UDF detected — consider using native PySpark functions instead")
        if ".collect()" in code:
            warnings.append(".collect() found — may cause OOM on large datasets")
        if "coalesce(1)" in code:
            warnings.append("coalesce(1) found — kills parallelism on large data")

        return _text_result(json.dumps({
            "valid": True,
            "message": "Syntax is correct",
            "warnings": warnings,
            "line_count": len(code.splitlines()),
        }))
    except SyntaxError as e:
        return _text_result(json.dumps({
            "valid": False,
            "error": e.msg,
            "line": e.lineno,
            "offset": e.offset,
            "text": e.text.strip() if e.text else None,
        }))


# ── MCP Server Assembly ──────────────────────────────────────────────────────


def create_sql2spark_server():
    """Create the sql2spark MCP server with both tools."""
    return create_sdk_mcp_server(
        name="sql2spark",
        version="1.0.0",
        tools=[sql_prescan, validate_pyspark_syntax],
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _text_result(text: str) -> dict:
    """MCP standard response format."""
    return {"content": [{"type": "text", "text": text}]}
