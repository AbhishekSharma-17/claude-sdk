"""Configuration for the sql2spark converter."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


_BEDROCK_MODEL_MAP: dict[str, str] = {
    "opus":   "us.anthropic.claude-opus-4-6-v1",
    "sonnet": "us.anthropic.claude-sonnet-4-6",
    "haiku":  "us.anthropic.claude-haiku-4-5-20251001-v1:0",
}


@dataclass
class ConverterConfig:
    """All configurable settings for the converter pipeline."""

    # Paths
    workspace: Path = Path(".")
    input_dir: str = "input"
    output_dir: str = "output"
    knowledge_dir: str = "knowledge"

    # Provider: "anthropic" or "bedrock"
    provider: str = field(default_factory=lambda: os.getenv("SQL2SPARK_PROVIDER", "anthropic"))

    # AWS Bedrock credentials (only required when provider="bedrock")
    aws_access_key_id: str = field(default_factory=lambda: os.getenv("AWS_ACCESS_KEY_ID", ""))
    aws_secret_access_key: str = field(default_factory=lambda: os.getenv("AWS_SECRET_ACCESS_KEY", ""))
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))

    # Models
    conversion_model: str = field(default_factory=lambda: os.getenv("SQL2SPARK_MODEL", "opus"))
    validation_model: str = field(default_factory=lambda: os.getenv("SQL2SPARK_VALIDATION_MODEL", "sonnet"))
    fallback_model: str = field(default_factory=lambda: os.getenv("SQL2SPARK_FALLBACK_MODEL", "sonnet"))

    # Budget & limits
    total_budget_usd: float = 20.0
    discovery_budget_per_file: float = 1.00
    planning_budget: float = 1.50
    conversion_budget_per_object: float = 2.50
    validation_budget_per_file: float = 0.30

    # Turns
    discovery_max_turns: int = 15
    planning_max_turns: int = 15
    conversion_max_turns: int = 25
    validation_max_turns: int = 10

    # Parallelism
    max_parallel_conversions: int = 4

    # Modes
    interactive: bool = False
    dry_run: bool = False
    verbose: bool = False

    # Auto-fix (Phase 5)
    auto_fix_model: str = field(default_factory=lambda: os.getenv("SQL2SPARK_AUTOFIX_MODEL", "sonnet"))
    auto_fix_budget_per_file: float = 0.50
    auto_fix_max_turns: int = 10
    skip_auto_fix: bool = False

    # Retry
    max_retries: int = 3
    retry_backoff_base: float = 2.0

    # Large file threshold (lines)
    large_file_threshold: int = 4000
    chunk_size: int = 2500

    @property
    def input_path(self) -> Path:
        return self.workspace / self.input_dir

    @property
    def output_path(self) -> Path:
        return self.workspace / self.output_dir

    @property
    def knowledge_path(self) -> Path:
        return self.workspace / self.knowledge_dir

    @property
    def checkpoint_path(self) -> Path:
        return self.output_path / ".checkpoint.json"

    @property
    def report_path(self) -> Path:
        return self.output_path / "report.json"

    @property
    def provider_env(self) -> dict[str, str]:
        """Build the env dict for ClaudeAgentOptions based on the active provider."""
        if self.provider == "bedrock":
            if not self.aws_access_key_id or not self.aws_secret_access_key:
                raise ValueError(
                    "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set "
                    "for provider=bedrock. Set in environment or .env file."
                )
            return {
                "CLAUDE_CODE_USE_BEDROCK": "1",
                "AWS_ACCESS_KEY_ID": self.aws_access_key_id,
                "AWS_SECRET_ACCESS_KEY": self.aws_secret_access_key,
                "AWS_REGION": self.aws_region,
            }
        # Default: anthropic
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set in environment or .env")
        return {"ANTHROPIC_API_KEY": key}

    @property
    def provider_display(self) -> str:
        """Human-readable provider label for banner/logging."""
        if self.provider == "bedrock":
            return f"AWS Bedrock ({self.aws_region})"
        return "Anthropic API"

    @property
    def model_display(self) -> str:
        """Human-readable model label showing resolved model ID."""
        resolved = self.resolve_model(self.conversion_model)
        if self.provider == "bedrock" and resolved != self.conversion_model:
            return f"{self.conversion_model} → {resolved}"
        return self.conversion_model

    def resolve_model(self, shorthand: str) -> str:
        """Map shorthand model names to Bedrock model IDs when using Bedrock."""
        if self.provider == "bedrock":
            return _BEDROCK_MODEL_MAP.get(shorthand, shorthand)
        return shorthand
