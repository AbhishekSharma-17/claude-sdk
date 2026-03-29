"""Pipeline orchestrator: Phase 1 → 2 → 3 → 4 → 5.

Wires all phases together, manages cost tracking, checkpointing, and reporting.
Phase 4 receives the ConversionPlan for cross-file dependency validation.
Phase 5 auto-fixes HIGH/ERROR issues and builds developer action items.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from agents.options import OptionsFactory
from config import ConverterConfig
from models import (
    AutoFixResult,
    ConversionPlan,
    ConversionReport,
    ConversionResult,
    ConversionStatus,
    CostBreakdown,
    DeveloperActionItems,
    FileInventory,
)
from phases import auto_fix, conversion, discovery, planning, validation

logger = logging.getLogger(__name__)


async def run_pipeline(config: ConverterConfig) -> ConversionReport:
    """Run the full sql2spark conversion pipeline.

    Phase 1: Discovery — identify objects, detect dialect, score complexity
    Phase 2: Planning — dependency graph, conversion order, targeted instructions
    Phase 3: Conversion — convert each object to PySpark
    Phase 4: Validation — context-aware syntax check + Claude cross-file review
    Phase 5: Auto-Fix — fix HIGH/ERROR issues, build developer action items
    """
    start_time = time.monotonic()
    cost = CostBreakdown()
    options_factory = OptionsFactory(config)

    config.output_path.mkdir(parents=True, exist_ok=True)

    # ── Find SQL files ────────────────────────────────────────────────────
    sql_files = sorted(config.input_path.glob("*.sql"))
    if not sql_files:
        logger.error("No .sql files found in %s", config.input_path)
        return ConversionReport(file_complexity="No files found")

    logger.info("Found %d SQL files in %s", len(sql_files), config.input_path)
    for f in sql_files:
        logger.info("  - %s", f.name)

    # ── Phase 1: Discovery ────────────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("PHASE 1: DISCOVERY & COMPLEXITY ANALYSIS")
    logger.info("=" * 60)

    inventories: list[FileInventory] = []
    discovery_options = options_factory.discovery()

    for sql_file in sql_files:
        inv, inv_cost = await discovery.discover_file(sql_file, discovery_options, config)
        inventories.append(inv)
        cost.discovery += inv_cost

    total_objects = sum(len(inv.objects) for inv in inventories)
    logger.info(
        "\nDiscovery complete: %d objects across %d files (cost: $%.4f)",
        total_objects, len(inventories), cost.discovery,
    )
    for inv in inventories:
        logger.info(
            "  %s [%s] — %s (score: %.1f) — %d objects",
            inv.file_path, inv.dialect, inv.file_complexity, inv.file_complexity_score,
            len(inv.objects),
        )
        for obj in inv.objects:
            logger.info(
                "    - %s (%s, %d lines, %s %.1f)",
                obj.name, obj.type, obj.line_count, obj.complexity_level, obj.complexity_score,
            )

    if total_objects == 0:
        logger.error("No SQL objects discovered. Check your input files.")
        return ConversionReport(file_complexity="No objects found", cost_breakdown=cost)

    # ── Phase 2: Dependency Analysis & Planning ───────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("PHASE 2: DEPENDENCY ANALYSIS & CONVERSION PLANNING")
    logger.info("=" * 60)

    planning_options = options_factory.planning()
    plan, plan_cost = await planning.build_conversion_plan(inventories, planning_options, config)
    cost.planning += plan_cost

    logger.info(
        "\nPlanning complete: %d levels, %d objects planned (cost: $%.4f)",
        len(plan.conversion_levels), plan.total_objects, cost.planning,
    )
    for level in plan.conversion_levels:
        logger.info("  Level %d: %s — %s", level.level, level.strategy, ", ".join(level.objects))

    if config.dry_run:
        logger.info("\n[DRY RUN] Stopping after Phase 2. No conversion performed.")
        _save_dry_run_output(config, inventories, plan, cost)
        return ConversionReport(
            total_objects=total_objects,
            file_complexity=inventories[0].file_complexity if inventories else "",
            cost_breakdown=cost,
        )

    estimated_conversion_cost = total_objects * 1.75
    remaining_budget = config.total_budget_usd - cost.discovery - cost.planning
    if estimated_conversion_cost > remaining_budget * 1.5:
        logger.warning(
            "Estimated conversion cost ($%.2f) may exceed remaining budget ($%.2f)",
            estimated_conversion_cost, remaining_budget,
        )

    # ── Phase 3: Conversion ───────────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("PHASE 3: SQL-TO-PYSPARK CONVERSION")
    logger.info("=" * 60)

    conversion_options = options_factory.conversion()
    interactive_options = options_factory.conversion_interactive() if config.interactive else None

    checkpoint = _load_checkpoint(config)
    if checkpoint:
        logger.info("Resuming from checkpoint: %d objects already converted", len(checkpoint))

    conversion_results = await conversion.convert_all(
        inventories=inventories,
        plan=plan,
        options=conversion_options,
        interactive_options=interactive_options,
        config=config,
    )

    for result in conversion_results:
        cost.conversion += result.cost_usd

    converted_count = sum(1 for r in conversion_results if r.status == ConversionStatus.CONVERTED)
    failed_count = sum(1 for r in conversion_results if r.status == ConversionStatus.FAILED)
    logger.info(
        "\nConversion complete: %d converted, %d failed (cost: $%.4f)",
        converted_count, failed_count, cost.conversion,
    )

    _save_checkpoint(config, conversion_results)

    # ── Phase 4: Validation (context-aware) ──────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("PHASE 4: VALIDATION & REPORT")
    logger.info("=" * 60)

    output_files = sorted(config.output_path.glob("*.py"))
    validation_options = options_factory.validation()

    validation_results, dep_context_by_file = await validation.validate_all(
        output_files=output_files,
        options=validation_options,
        config=config,
        plan=plan,            # ← enables cross-file dependency context injection
        inventories=inventories,
    )

    for vr in validation_results:
        cost.validation += vr.cost_usd

    valid_count = sum(1 for vr in validation_results if vr.syntax_valid and vr.pyspark_correct)
    issue_count = sum(len(vr.issues) for vr in validation_results)
    logger.info(
        "\nValidation complete: %d valid, %d issues (cost: $%.4f)",
        valid_count, issue_count, cost.validation,
    )

    # ── Phase 5: Auto-Fix ─────────────────────────────────────────────────
    auto_fix_results: list[AutoFixResult] = []
    developer_action_items: DeveloperActionItems = DeveloperActionItems()

    if not config.skip_auto_fix:
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 5: AUTO-FIX")
        logger.info("=" * 60)

        auto_fix_options = options_factory.auto_fix()
        auto_fix_results = await auto_fix.fix_all(
            validation_results=validation_results,
            options=auto_fix_options,
            config=config,
            dep_context_by_file=dep_context_by_file,
        )

        for afr in auto_fix_results:
            cost.auto_fix += afr.cost_usd

        fixed_count = sum(
            1 for afr in auto_fix_results
            if afr.status.value in ("fixed", "partial")
        )
        reverted_count = sum(1 for afr in auto_fix_results if afr.was_reverted)
        logger.info(
            "\nAuto-fix complete: %d fixed, %d reverted (cost: $%.4f)",
            fixed_count, reverted_count, cost.auto_fix,
        )
    else:
        logger.info("\n[SKIP] Phase 5: Auto-Fix skipped (--skip-autofix flag)")

    # ── Collect TODOs from generated files ────────────────────────────────
    todos_in_code = _collect_todos(config.output_path)

    # ── Build Developer Action Items ──────────────────────────────────────
    developer_action_items = auto_fix.build_developer_action_items(
        validation_results=validation_results,
        auto_fix_results=auto_fix_results,
        todos_in_code=todos_in_code,
    )

    # ── Generate & Save Report ────────────────────────────────────────────
    file_complexity = inventories[0].file_complexity if inventories else ""
    report = validation.generate_report(
        conversion_results=conversion_results,
        validation_results=validation_results,
        cost_breakdown=cost,
        file_complexity=file_complexity,
        auto_fix_results=auto_fix_results,
        developer_action_items=developer_action_items,
    )

    report_json = report.model_dump_json(indent=2)
    config.report_path.write_text(report_json, encoding="utf-8")

    elapsed = time.monotonic() - start_time
    ai = developer_action_items

    logger.info("\n" + "=" * 60)
    logger.info("CONVERSION COMPLETE")
    logger.info("=" * 60)
    logger.info(
        "  Objects: %d converted, %d failed, %d skipped",
        report.converted, report.failed, report.skipped,
    )
    logger.info(
        "  Cost: $%.4f  (discovery: $%.4f | planning: $%.4f | conversion: $%.4f"
        " | validation: $%.4f | auto_fix: $%.4f)",
        cost.total, cost.discovery, cost.planning, cost.conversion,
        cost.validation, cost.auto_fix,
    )
    logger.info("  Time: %.1fs", elapsed)
    if ai.auto_fixed:
        logger.info("  Auto-fixed: %d issues", len(ai.auto_fixed))
    if ai.requires_manual:
        logger.info("  Manual fixes needed: %d  (see developer_action_items.requires_manual)", len(ai.requires_manual))
    if ai.infrastructure_setup:
        logger.info("  Infrastructure setup: %d items", len(ai.infrastructure_setup))
    if ai.summary:
        logger.info("  Summary: %s", ai.summary)
    logger.info("  Report: %s", config.report_path)

    return report


# ── Helpers ───────────────────────────────────────────────────────────────────


def _collect_todos(output_path: Path) -> list[str]:
    """Scan all generated .py files for TODO comment lines."""
    todos: list[str] = []
    for py_file in sorted(output_path.glob("*.py")):
        try:
            for line in py_file.read_text(encoding="utf-8").splitlines():
                if "TODO" in line:
                    todos.append(f"{py_file.name}: {line.strip()}")
        except OSError:
            pass
    return todos


# ── Checkpoint Management ─────────────────────────────────────────────────────


def _save_checkpoint(config: ConverterConfig, results: list[ConversionResult]) -> None:
    """Save conversion progress for resume capability."""
    checkpoint = {
        r.object_name: {
            "status": r.status,
            "output_file": r.output_file,
            "cost_usd": r.cost_usd,
            "session_id": r.session_id,
        }
        for r in results
        if r.status == ConversionStatus.CONVERTED
    }
    config.checkpoint_path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")


def _load_checkpoint(config: ConverterConfig) -> dict | None:
    """Load checkpoint if it exists."""
    if config.checkpoint_path.exists():
        try:
            return json.loads(config.checkpoint_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _save_dry_run_output(
    config: ConverterConfig,
    inventories: list[FileInventory],
    plan: ConversionPlan,
    cost: CostBreakdown,
) -> None:
    """Save discovery and planning results for dry run inspection."""
    output = {
        "mode": "dry_run",
        "inventories": [inv.model_dump() for inv in inventories],
        "conversion_plan": plan.model_dump(),
        "cost_so_far": cost.model_dump(),
    }
    dry_run_path = config.output_path / "dry_run_analysis.json"
    dry_run_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    logger.info("Dry run output saved to: %s", dry_run_path)
