"""Shared configuration for all Claude Agent SDK examples.

Loads API keys and settings from .env file in this directory.
Every example script imports this module to get consistent configuration.

Usage in scripts:
    from config import get_api_key, get_model, get_budget, SAMPLE_DIR
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Load .env from the examples/ directory
ENV_FILE = Path(__file__).parent / ".env"


def _load_dotenv() -> None:
    """Load .env file manually (no third-party dependency needed)."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        # Don't overwrite existing env vars
        if key not in os.environ:
            os.environ[key] = value


# Load on import
_load_dotenv()

# ── Paths ─────────────────────────────────────────────────────────────────────

EXAMPLES_DIR = Path(__file__).parent
SAMPLE_DIR = EXAMPLES_DIR / "sample_data"
TOOLS_DIR = EXAMPLES_DIR / "tools"


# ── Getters ───────────────────────────────────────────────────────────────────

def get_api_key() -> str:
    """Get the Anthropic API key from env. Exits if not set."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key or key == "sk-ant-your-key-here":
        # Check if using Bedrock/Vertex/Foundry instead
        if any(os.environ.get(v) for v in [
            "CLAUDE_CODE_USE_BEDROCK",
            "CLAUDE_CODE_USE_VERTEX",
            "CLAUDE_CODE_USE_FOUNDRY",
        ]):
            return ""  # Auth handled by cloud provider
        print("ERROR: No API key configured.")
        print(f"  1. Copy .env.example to .env:  cp {ENV_FILE.parent}/.env.example {ENV_FILE}")
        print(f"  2. Set ANTHROPIC_API_KEY in {ENV_FILE}")
        print(f"  Or set it directly:  export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)
    return key


def get_model() -> str:
    """Get the model name from env or default to 'sonnet'."""
    return os.environ.get("CLAUDE_MODEL", "sonnet")


def get_budget() -> float:
    """Get the max budget from env or default to 1.0."""
    return float(os.environ.get("MAX_BUDGET_USD", "1.0"))


def get_auth_info() -> str:
    """Return a human-readable auth method description."""
    if os.environ.get("CLAUDE_CODE_USE_BEDROCK"):
        profile = os.environ.get("AWS_PROFILE", "default")
        region = os.environ.get("AWS_REGION", "us-east-1")
        return f"AWS Bedrock (profile={profile}, region={region})"
    elif os.environ.get("CLAUDE_CODE_USE_VERTEX"):
        project = os.environ.get("GOOGLE_CLOUD_PROJECT", "?")
        return f"Google Vertex AI (project={project})"
    elif os.environ.get("CLAUDE_CODE_USE_FOUNDRY"):
        return "Azure AI Foundry"
    elif os.environ.get("ANTHROPIC_API_KEY"):
        key = os.environ["ANTHROPIC_API_KEY"]
        masked = key[:10] + "..." + key[-4:] if len(key) > 14 else "***"
        return f"Anthropic Direct API (key={masked})"
    return "Unknown"


def print_header(title: str, **kwargs: str) -> None:
    """Print a consistent header for demo scripts."""
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)
    print(f"Auth: {get_auth_info()}")
    print(f"Model: {get_model()}")
    print(f"Budget: ${get_budget():.2f}")
    for k, v in kwargs.items():
        print(f"{k}: {v}")
    print("-" * 60)
