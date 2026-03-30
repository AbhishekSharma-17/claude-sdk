"""Pydantic models for the sql2spark converter pipeline."""

from __future__ import annotations

from dataclasses import field
from enum import StrEnum
from pydantic import BaseModel, Field, field_validator


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

    @field_validator("complexity_level", mode="before")
    @classmethod
    def normalize_complexity_level(cls, v: object) -> object:
        """Normalize LLM-returned complexity labels to canonical enum values."""
        if not isinstance(v, str):
            return v
        _MAP = {
            # Simple tier
            "trivial": "Simple",
            "very simple": "Simple",
            "low": "Simple",
            "simple": "Simple",
            "easy": "Simple",
            "basic": "Simple",
            "low complexity": "Simple",
            # Moderate tier
            "medium": "Moderate",
            "moderate": "Moderate",
            "medium complexity": "Moderate",
            "low-medium": "Moderate",
            "low-moderate": "Moderate",
            # Complex tier
            "high": "Complex",
            "complex": "Complex",
            "hard": "Complex",
            "difficult": "Complex",
            "medium-high": "Complex",
            "moderate-high": "Complex",
            "high complexity": "Complex",
            # Very Complex tier
            "very high": "Very Complex",
            "very complex": "Very Complex",
            "critical": "Very Complex",
            "extreme": "Very Complex",
            "very high complexity": "Very Complex",
            "extremely complex": "Very Complex",
        }
        normalized = v.strip().lower()
        if normalized in _MAP:
            return _MAP[normalized]
        # Fuzzy fallback: scan for the first recognisable keyword in the string
        for keyword, canonical in (
            ("very", "Very Complex"),
            ("extreme", "Very Complex"),
            ("critical", "Very Complex"),
            ("high", "Complex"),
            ("complex", "Complex"),
            ("difficult", "Complex"),
            ("medium", "Moderate"),
            ("moderate", "Moderate"),
            ("low", "Simple"),
            ("simple", "Simple"),
            ("easy", "Simple"),
            ("basic", "Simple"),
        ):
            if keyword in normalized:
                return canonical
        return v  # pass through unchanged; Pydantic will surface the error

    @field_validator("type", mode="before")
    @classmethod
    def normalize_object_type(cls, v: object) -> object:
        """Normalize object type variants to canonical enum values."""
        if not isinstance(v, str):
            return v
        _MAP = {
            # procedure variants
            "procedure": "procedure",
            "stored_procedure": "procedure",
            "stored procedure": "procedure",
            "usp": "procedure",
            "sp": "procedure",
            # function variants
            "function": "function",
            "scalar_function": "function",
            "scalar function": "function",
            "table_function": "function",
            "table function": "function",
            "table-valued function": "function",
            "inline_function": "function",
            "inline function": "function",
            "fn": "function",
            "udf": "function",
            # view variants
            "view": "view",
            "vw": "view",
            "indexed_view": "view",
            "materialized_view": "view",
            "materialized view": "view",
            # trigger variants
            "trigger": "trigger",
            "trg": "trigger",
            "dml_trigger": "trigger",
            "dml trigger": "trigger",
            "ddl_trigger": "trigger",
        }
        return _MAP.get(v.strip().lower(), v.strip().lower())

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

    @field_validator("dialect", mode="before")
    @classmethod
    def normalize_dialect(cls, v: object) -> object:
        """Normalize SQL dialect variants to canonical values."""
        if not isinstance(v, str):
            return v
        _MAP = {
            "t-sql": "tsql",
            "tsql": "tsql",
            "mssql": "tsql",
            "sql server": "tsql",
            "transact-sql": "tsql",
            "pl/sql": "plsql",
            "plsql": "plsql",
            "oracle": "plsql",
            "pl/pgsql": "plpgsql",
            "plpgsql": "plpgsql",
            "postgresql": "plpgsql",
            "postgres": "plpgsql",
        }
        return _MAP.get(v.strip().lower(), v.strip().lower())

    @field_validator("file_complexity", mode="before")
    @classmethod
    def normalize_file_complexity(cls, v: object) -> object:
        """Normalize file complexity labels to canonical values."""
        if not isinstance(v, str):
            return v
        _MAP = {
            "simple script": "Simple script",
            "simple": "Simple script",
            "standard script": "Standard script",
            "standard": "Standard script",
            "moderate script": "Standard script",
            "complex script": "Complex script",
            "complex": "Complex script",
            "enterprise script": "Enterprise script",
            "enterprise": "Enterprise script",
            "very complex script": "Enterprise script",
        }
        return _MAP.get(v.strip().lower(), v)


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
    auto_fix: float = 0.0

    @property
    def total(self) -> float:
        return self.discovery + self.planning + self.conversion + self.validation + self.auto_fix


class PhaseTimings(BaseModel):
    discovery_seconds: float = 0.0
    planning_seconds: float = 0.0
    conversion_seconds: float = 0.0
    validation_seconds: float = 0.0
    auto_fix_seconds: float = 0.0
    total_seconds: float = 0.0


# ── Phase 5: Auto-Fix Models ──────────────────────────────────────────────────


class AutoFixStatus(StrEnum):
    FIXED    = "fixed"
    PARTIAL  = "partial"
    REVERTED = "reverted"  # ast.parse failed after fix — original restored
    SKIPPED  = "skipped"   # no auto-fixable issues
    FAILED   = "failed"    # Claude call or file I/O error


class AutoFixResult(BaseModel):
    file_path: str
    status: AutoFixStatus = AutoFixStatus.SKIPPED
    issues_attempted: int = 0
    issues_fixed: int = 0
    issues_remaining: list[ValidationIssue] = Field(default_factory=list)
    was_reverted: bool = False
    revert_reason: str = ""
    cost_usd: float = 0.0


# ── Developer Action Items ────────────────────────────────────────────────────


class ActionItem(BaseModel):
    category: str   # "auto_fixed" | "requires_manual" | "recommended_review" | "infrastructure"
    priority: str   # "critical" | "high" | "medium" | "low"
    file: str
    description: str
    how_to_fix: str
    line: int | None = None

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, v: object) -> object:
        """Normalize priority labels to canonical values."""
        if not isinstance(v, str):
            return v
        _MAP = {
            "critical": "critical", "error": "critical",
            "high": "high",
            "medium": "medium", "moderate": "medium", "warning": "medium",
            "low": "low", "info": "low",
        }
        return _MAP.get(v.strip().lower(), v.strip().lower())


class DeveloperActionItems(BaseModel):
    auto_fixed: list[ActionItem] = Field(default_factory=list)
    requires_manual: list[ActionItem] = Field(default_factory=list)
    recommended_review: list[ActionItem] = Field(default_factory=list)
    infrastructure_setup: list[ActionItem] = Field(default_factory=list)
    todos_in_code: list[str] = Field(default_factory=list)
    summary: str = ""

    @property
    def total_open_items(self) -> int:
        return (
            len(self.requires_manual)
            + len(self.recommended_review)
            + len(self.infrastructure_setup)
        )


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
    phase_timings: PhaseTimings = Field(default_factory=PhaseTimings)
    objects: list[ConversionResult] = Field(default_factory=list)
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    todos: list[str] = Field(default_factory=list)
    auto_fix_results: list[AutoFixResult] = Field(default_factory=list)
    developer_action_items: DeveloperActionItems = Field(default_factory=DeveloperActionItems)
