import asyncio
import os
from dotenv import load_dotenv
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

# load_dotenv() reads .env file and puts values into os.environ
# In production (Docker/K8s/Lambda) this line does nothing —
# the platform already injects env vars, so os.getenv() just works.
load_dotenv()

# ── Step 1: fetch from .env into variables ────────────────────────────────────

PROVIDER          = os.getenv("PROVIDER", "anthropic")

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# AWS Bedrock
AWS_ACCESS_KEY_ID     = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION            = os.getenv("AWS_REGION", "us-east-1")

def mask(value: str | None) -> str:
    """Show first 6 chars only — enough to confirm the right key loaded, never exposes the secret."""
    if not value:
        return "NOT SET"
    return value[:6] + "..." + f" ({len(value)} chars)"


# ── Step 2: validate, then build options ──────────────────────────────────────

if PROVIDER == "anthropic":
    if not ANTHROPIC_API_KEY:
        raise ValueError("Missing ANTHROPIC_API_KEY in .env")

    print(f"PROVIDER          : {PROVIDER}")
    print(f"ANTHROPIC_API_KEY : {mask(ANTHROPIC_API_KEY)}")

    options = ClaudeAgentOptions(
        model="sonnet",
        env={"ANTHROPIC_API_KEY": ANTHROPIC_API_KEY},
    )

elif PROVIDER == "bedrock":
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        raise ValueError("Missing AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY in .env")

    print(f"PROVIDER              : {PROVIDER}")
    print(f"AWS_ACCESS_KEY_ID     : {mask(AWS_ACCESS_KEY_ID)}")
    print(f"AWS_SECRET_ACCESS_KEY : {mask(AWS_SECRET_ACCESS_KEY)}")
    print(f"AWS_REGION            : {AWS_REGION}")

    options = ClaudeAgentOptions(
        model="anthropic.claude-3-5-sonnet-20241022-v2:0",
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_ACCESS_KEY_ID":     AWS_ACCESS_KEY_ID,
            "AWS_SECRET_ACCESS_KEY": AWS_SECRET_ACCESS_KEY,
            "AWS_REGION":            AWS_REGION,
        },
    )

else:
    raise ValueError(f"Unknown PROVIDER={PROVIDER}")

# ── Step 3: run ───────────────────────────────────────────────────────────────

async def main():
    print(f"Provider: {PROVIDER}")

    async for message in query(prompt="What is Ai", options=options):
        if isinstance(message, ResultMessage):
            print(f"Answer : {message.result}")
            print(f"Cost   : ${message.total_cost_usd:.4f}")

asyncio.run(main())
