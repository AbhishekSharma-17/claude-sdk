"""Pydantic models for the sql2spark converter pipeline."""

from __future__ import annotations

from dataclasses import field
from enum import StrEnum
from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────


class SQLDialect(StrEnum):
    TSQL = "tsql"
    PLSQL = "plsql"
    PLPGSQL = "plpgsql"
    UNKNOWN = "unknown"


class ObjectType(StrEnum):
    PROCEDURE = "procedure"
    FUNCTION = "function"
    VIEW = "view"
    TRIGGER = "trigger"


class ComplexityLevel(StrEnum):
    SIMPLE = "Simple"
    MODERATE = "Moderate"
    COMPLEX = "Complex"
    VERY_COMPLEX = "Very Complex"


class FileComplexity(StrEnum):
    SIMPLE_SCRIPT = "Simple script"
    STANDARD_SCRIPT = "Standard script"
    COMPLEX_SCRIPT = "Complex script"
    ENTERPRISE_SCRIPT = "Enterprise script"


class ConversionStatus(StrEnum):
    CONVERTED = "converted"
    FAILED = "failed"
    SKIPPED = "skipped"
    NEEDS_REVIEW = "needs_review"


# ── Phase 1: Discovery Models ────────────────────────────────────────────────


class SQLParameter(BaseModel):
    name: str
    data_type: str
    direction: str = "IN"
    default_value: str | None = None


class SQLObject(BaseModel):
    name: str
    type: ObjectType
    start_line: int
    end_line: int
    line_count: int = 0
    parameters: list[SQLParameter] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    temp_tables_created: list[str] = Field(default_factory=list)
    temp_tables_used: list[str] = Field(default_factory=list)
    has_cursor: bool = False
    has_dynamic_sql: bool = False
    has_transaction: bool = False
    window_function_count: int = 0
    complexity_score: float = 0.0
    complexity_level: ComplexityLevel = ComplexityLevel.SIMPLE
    known_limitations: list[str] = Field(default_factory=list)
    constructs_used: list[str] = Field(default_factory=list)

    def model_post_init(self, __context: object) -> None:
        if self.line_count == 0:
            self.line_count = self.end_line - self.start_line + 1


class FileInventory(BaseModel):
    file_path: str
    total_lines: int
    dialect: SQLDialect
    file_complexity: FileComplexity = FileComplexity.SIMPLE_SCRIPT
    file_complexity_score: float = 0.0
    objects: list[SQLObject] = Field(default_factory=list)


# ── Phase 1: Output Schema (for structured output) ───────────────────────────


INVENTORY_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "file_path": {"type": "string"},
        "total_lines": {"type": "integer"},
        "dialect": {"type": "string", "enum": ["tsql", "plsql", "plpgsql", "unknown"]},
        "file_complexity": {
            "type": "string",
            "enum": ["Simple script", "Standard script", "Complex script", "Enterprise script"],
        },
        "file_complexity_score": {"type": "number"},
        "objects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string", "enum": ["procedure", "function", "view", "trigger"]},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                    "line_count": {"type": "integer"},
                    "parameters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "data_type": {"type": "string"},
                                "direction": {"type": "string", "enum": ["IN", "OUT", "INOUT"]},
                                "default_value": {"type": ["string", "null"]},
                            },
                            "required": ["name", "data_type"],
                        },
                    },
                    "references": {"type": "array", "items": {"type": "string"}},
                    "temp_tables_created": {"type": "array", "items": {"type": "string"}},
                    "temp_tables_used": {"type": "array", "items": {"type": "string"}},
                    "has_cursor": {"type": "boolean"},
                    "has_dynamic_sql": {"type": "boolean"},
                    "has_transaction": {"type": "boolean"},
                    "window_function_count": {"type": "integer"},
                    "complexity_score": {"type": "number"},
                    "complexity_level": {
                        "type": "string",
                        "enum": ["Simple", "Moderate", "Complex", "Very Complex"],
                    },
                    "known_limitations": {"type": "array", "items": {"type": "string"}},
                    "constructs_used": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "name", "type", "start_line", "end_line", "line_count",
                    "complexity_score", "complexity_level",
                ],
            },
        },
    },
    "required": ["file_path", "total_lines", "dialect", "file_complexity", "file_complexity_score", "objects"],
}


# ── Phase 2: Dependency & Planning Models ─────────────────────────────────────


class DependencyEdge(BaseModel):
    source: str
    target: str
    relationship: str  # "calls", "reads_temp_table", "uses_view", etc.


class ConversionLevel(BaseModel):
    level: int
    description: str
    objects: list[str]
    strategy: str  # "Parallel conversion", "Sequential", etc.


class ObjectPlan(BaseModel):
    conversion_order: int
    complexity: str
    estimated_tokens: int = 0
    dependencies_resolved: list[str] = Field(default_factory=list)
    dependency_signatures: str = ""
    conversion_instructions: list[str] = Field(default_factory=list)
    gotchas_relevant: list[str] = Field(default_factory=list)
    limitations_found: list[str] = Field(default_factory=list)
    strategy: str = "Standard conversion"


class ConversionPlan(BaseModel):
    total_objects: int
    conversion_levels: list[ConversionLevel] = Field(default_factory=list)
    dependency_edges: list[DependencyEdge] = Field(default_factory=list)
    object_plans: dict[str, ObjectPlan] = Field(default_factory=dict)


PLAN_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "total_objects": {"type": "integer"},
        "conversion_levels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "level": {"type": "integer"},
                    "description": {"type": "string"},
                    "objects": {"type": "array", "items": {"type": "string"}},
                    "strategy": {"type": "string"},
                },
                "required": ["level", "description", "objects", "strategy"],
            },
        },
        "dependency_edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "relationship": {"type": "string"},
                },
                "required": ["source", "target", "relationship"],
            },
        },
        "object_plans": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "conversion_order": {"type": "integer"},
                    "complexity": {"type": "string"},
                    "estimated_tokens": {"type": "integer"},
                    "dependencies_resolved": {"type": "array", "items": {"type": "string"}},
                    "dependency_signatures": {"type": "string"},
                    "conversion_instructions": {"type": "array", "items": {"type": "string"}},
                    "gotchas_relevant": {"type": "array", "items": {"type": "string"}},
                    "limitations_found": {"type": "array", "items": {"type": "string"}},
                    "strategy": {"type": "string"},
                },
                "required": ["conversion_order", "complexity", "conversion_instructions"],
            },
        },
    },
    "required": ["total_objects", "conversion_levels", "object_plans"],
}


# ── Phase 3 & 4: Conversion & Validation Models ──────────────────────────────


class ConversionResult(BaseModel):
    object_name: str
    status: ConversionStatus = ConversionStatus.FAILED
    output_file: str | None = None
    signature: str = ""
    cost_usd: float = 0.0
    turns_used: int = 0
    duration_ms: int = 0
    session_id: str | None = None
    error: str | None = None


class ValidationIssue(BaseModel):
    file: str
    severity: str  # "error", "warning", "info"
    message: str
    line: int | None = None


class ValidationResult(BaseModel):
    file_path: str
    syntax_valid: bool = False
    pyspark_correct: bool = False
    dependencies_resolved: bool = False
    issues: list[ValidationIssue] = Field(default_factory=list)
    todos_found: int = 0
    cost_usd: float = 0.0


class CostBreakdown(BaseModel):
    discovery: float = 0.0
    planning: float = 0.0
    conversion: float = 0.0
    validation: float = 0.0

    @property
    def total(self) -> float:
        return self.discovery + self.planning + self.conversion + self.validation


class ConversionReport(BaseModel):
    total_objects: int = 0
    converted: int = 0
    failed: int = 0
    skipped: int = 0
    needs_review: int = 0
    total_cost_usd: float = 0.0
    total_duration_ms: int = 0
    file_complexity: str = ""
    cost_breakdown: CostBreakdown = Field(default_factory=CostBreakdown)
    objects: list[ConversionResult] = Field(default_factory=list)
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    todos: list[str] = Field(default_factory=list)
