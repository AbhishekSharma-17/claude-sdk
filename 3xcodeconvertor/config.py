"""Configuration for the sql2spark converter."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class ConverterConfig:
    """All configurable settings for the converter pipeline."""

    # Paths
    workspace: Path = Path(".")
    input_dir: str = "input"
    output_dir: str = "output"
    knowledge_dir: str = "knowledge"

    # Models
    conversion_model: str = "opus"
    validation_model: str = "sonnet"
    fallback_model: str = "sonnet"

    # Budget & limits
    total_budget_usd: float = 50.0
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
    max_parallel_conversions: int = 3

    # Modes
    interactive: bool = False
    dry_run: bool = False
    verbose: bool = False

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
    def api_key(self) -> str:
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set in environment or .env")
        return key
