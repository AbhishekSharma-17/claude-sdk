"""ClaudeAgentOptions factory for each pipeline phase.

Centralizes all SDK configuration — models, tools, permissions, budgets.
"""

from __future__ import annotations

from claude_agent_sdk import ClaudeAgentOptions

from config import ConverterConfig
from tools import create_sql2spark_server
from agents import prompts


class OptionsFactory:
    """Builds ClaudeAgentOptions for each pipeline phase."""

    def __init__(self, config: ConverterConfig) -> None:
        self.config = config
        self.knowledge = prompts.load_knowledge(config.knowledge_path)
        self.mcp_server = create_sql2spark_server()

    def discovery(self) -> ClaudeAgentOptions:
        """Phase 1: Discover SQL objects, detect dialect, score complexity."""
        return ClaudeAgentOptions(
            model=self.config.conversion_model,
            env={"ANTHROPIC_API_KEY": self.config.api_key},
            cwd=str(self.config.workspace),
            system_prompt=prompts.build_discovery_prompt(self.knowledge),
            allowed_tools=[
                "Read",
                "Glob",
                "Grep",
                "mcp__sql2spark__sql_prescan",
            ],
            mcp_servers={"sql2spark": self.mcp_server},
            permission_mode="bypassPermissions",
            max_turns=self.config.discovery_max_turns,
            max_budget_usd=self.config.discovery_budget_per_file,
        )

    def planning(self) -> ClaudeAgentOptions:
        """Phase 2: Dependency analysis, conversion planning."""
        return ClaudeAgentOptions(
            model=self.config.conversion_model,
            env={"ANTHROPIC_API_KEY": self.config.api_key},
            cwd=str(self.config.workspace),
            system_prompt=prompts.build_planning_prompt(self.knowledge),
            allowed_tools=[
                "Read",
                "Grep",
            ],
            permission_mode="bypassPermissions",
            max_turns=self.config.planning_max_turns,
            max_budget_usd=self.config.planning_budget,
        )

    def conversion(self) -> ClaudeAgentOptions:
        """Phase 3: Convert individual SQL objects to PySpark."""
        return ClaudeAgentOptions(
            model=self.config.conversion_model,
            env={"ANTHROPIC_API_KEY": self.config.api_key},
            cwd=str(self.config.workspace),
            system_prompt=prompts.CONVERSION_SYSTEM_PROMPT,
            allowed_tools=[
                "Read",
                "Write",
                "Bash",
                "mcp__sql2spark__validate_pyspark_syntax",
            ],
            mcp_servers={"sql2spark": self.mcp_server},
            permission_mode="bypassPermissions",
            max_turns=self.config.conversion_max_turns,
            max_budget_usd=self.config.conversion_budget_per_object,
            fallback_model=self.config.fallback_model,
        )

    def conversion_interactive(self) -> ClaudeAgentOptions:
        """Phase 3 interactive: Conversion with human-in-the-loop."""
        return ClaudeAgentOptions(
            model=self.config.conversion_model,
            env={"ANTHROPIC_API_KEY": self.config.api_key},
            cwd=str(self.config.workspace),
            system_prompt=prompts.CONVERSION_SYSTEM_PROMPT,
            allowed_tools=[
                "Read",
                "Write",
                "Bash",
                "AskUserQuestion",
                "mcp__sql2spark__validate_pyspark_syntax",
            ],
            mcp_servers={"sql2spark": self.mcp_server},
            permission_mode="bypassPermissions",
            max_turns=self.config.conversion_max_turns + 10,
            max_budget_usd=self.config.conversion_budget_per_object * 2,
            fallback_model=self.config.fallback_model,
        )

    def validation(self) -> ClaudeAgentOptions:
        """Phase 4: Validate generated PySpark code."""
        return ClaudeAgentOptions(
            model=self.config.validation_model,
            env={"ANTHROPIC_API_KEY": self.config.api_key},
            cwd=str(self.config.workspace),
            system_prompt=prompts.build_validation_prompt(self.knowledge),
            allowed_tools=[
                "Read",
                "Bash",
                "mcp__sql2spark__validate_pyspark_syntax",
            ],
            mcp_servers={"sql2spark": self.mcp_server},
            permission_mode="bypassPermissions",
            max_turns=self.config.validation_max_turns,
            max_budget_usd=self.config.validation_budget_per_file,
        )
