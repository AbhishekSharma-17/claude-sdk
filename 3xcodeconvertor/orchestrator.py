"""Pipeline orchestrator: Phase 1 -> 2 -> 3 -> 4 -> 5.

Wires all phases together, manages cost tracking, checkpointing, and reporting.
Phase 4 receives the ConversionPlan for cross-file dependency validation.
Phase 5 auto-fixes HIGH/ERROR issues and builds developer action items.

Output structure (per SQL file):
    output/<script_name>/
        pyspark/          <- Converted PySpark .py files
        reports/
            discovery.json        <- Phase 1: object inventory + complexity
            conversion_plan.json  <- Phase 2: dependency graph + instructions
            report.json           <- Final conversion report
            .checkpoint.json      <- Resume state
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
    PhaseTimings,
)
from phases import auto_fix, conversion, discovery, planning, validation

logger = logging.getLogger(__name__)


async def run_pipeline(config: ConverterConfig) -> ConversionReport:
    """Run the full sql2spark conversion pipeline.

    Phase 1: Discovery -- identify objects, detect dialect, score complexity
    Phase 2: Planning -- dependency graph, conversion order, targeted instructions
    Phase 3: Conversion -- convert each object to PySpark
    Phase 4: Validation -- context-aware syntax check + Claude cross-file review
    Phase 5: Auto-Fix -- fix HIGH/ERROR issues, build developer action items
    """
    start_time = time.monotonic()
    cost = CostBreakdown()
    timings = PhaseTimings()
    options_factory = OptionsFactory(config)

    config.output_path.mkdir(parents=True, exist_ok=True)

    # -- Find SQL files ---------------------------------------------------------
    sql_files = sorted(config.input_path.glob("*.sql"))
    if not sql_files:
        logger.error("No .sql files found in %s", config.input_path)
        return ConversionReport(file_complexity="No files found")

    logger.info("Found %d SQL files in %s", len(sql_files), config.input_path)
    for f in sql_files:
        logger.info("  - %s", f.name)

    # Determine the script name for output folder structure
    # For single file: use the filename stem; for multi-file: use first file
    primary_script = sql_files[0].stem
    pyspark_dir = config.pyspark_dir(sql_files[0].name)
    reports_dir = config.reports_dir(sql_files[0].name)
    pyspark_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    # -- Phase 1: Discovery -----------------------------------------------------
    logger.info("\n" + "=" * 60)
    logger.info("PHASE 1: DISCOVERY & COMPLEXITY ANALYSIS")
    logger.info("=" * 60)

    inventories: list[FileInventory] = []
    discovery_options = options_factory.discovery()
    phase_start = time.monotonic()

    for sql_file in sql_files:
        inv, inv_cost = await discovery.discover_file(sql_file, discovery_options, config)
        inventories.append(inv)
        cost.discovery += inv_cost

    timings.discovery_seconds = round(time.monotonic() - phase_start, 1)
    total_objects = sum(len(inv.objects) for inv in inventories)
    logger.info(
        "\nDiscovery complete: %d objects across %d files (cost: $%.4f, %.1fs)",
        total_objects, len(inventories), cost.discovery, timings.discovery_seconds,
    )
    for inv in inventories:
        logger.info(
            "  %s [%s] -- %s (score: %.1f) -- %d objects",
            inv.file_path, inv.dialect, inv.file_complexity, inv.file_complexity_score,
            len(inv.objects),
        )
        for obj in inv.objects:
            logger.info(
                "    - %s (%s, %d lines, %s %.1f)",
                obj.name, obj.type, obj.line_count, obj.complexity_level, obj.complexity_score,
            )

    # Save Phase 1 discovery report
    _save_discovery_report(config, inventories, cost, timings, sql_files[0].name)

    if total_objects == 0:
        logger.error("No SQL objects discovered. Check your input files.")
        return ConversionReport(file_complexity="No objects found", cost_breakdown=cost)

    # -- Phase 2: Dependency Analysis & Planning --------------------------------
    logger.info("\n" + "=" * 60)
    logger.info("PHASE 2: DEPENDENCY ANALYSIS & CONVERSION PLANNING")
    logger.info("=" * 60)

    planning_options = options_factory.planning()
    phase_start = time.monotonic()
    plan, plan_cost = await planning.build_conversion_plan(inventories, planning_options, config)
    cost.planning += plan_cost
    timings.planning_seconds = round(time.monotonic() - phase_start, 1)

    logger.info(
        "\nPlanning complete: %d levels, %d objects planned (cost: $%.4f, %.1fs)",
        len(plan.conversion_levels), plan.total_objects, cost.planning, timings.planning_seconds,
    )
    for level in plan.conversion_levels:
        logger.info("  Level %d: %s -- %s", level.level, level.strategy, ", ".join(level.objects))

    # Save Phase 2 conversion plan report
    _save_conversion_plan_report(config, plan, cost, timings, sql_files[0].name)

    if config.dry_run:
        logger.info("\n[DRY RUN] Stopping after Phase 2. No conversion performed.")
        # Also save combined dry_run_analysis.json for backwards compatibility
        _save_dry_run_output(config, inventories, plan, cost, sql_files[0].name)
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

    # -- Phase 3: Conversion ----------------------------------------------------
    logger.info("\n" + "=" * 60)
    logger.info("PHASE 3: SQL-TO-PYSPARK CONVERSION")
    logger.info("=" * 60)

    # Override output_path for conversion to write into pyspark/ subfolder
    original_output_path = config.output_path
    config._pyspark_output_dir = pyspark_dir

    conversion_options = options_factory.conversion()
    interactive_options = options_factory.conversion_interactive() if config.interactive else None
    phase_start = time.monotonic()

    checkpoint = _load_checkpoint(config, sql_files[0].name)
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

    timings.conversion_seconds = round(time.monotonic() - phase_start, 1)
    converted_count = sum(1 for r in conversion_results if r.status == ConversionStatus.CONVERTED)
    failed_count = sum(1 for r in conversion_results if r.status == ConversionStatus.FAILED)
    logger.info(
        "\nConversion complete: %d converted, %d failed (cost: $%.4f, %.1fs)",
        converted_count, failed_count, cost.conversion, timings.conversion_seconds,
    )

    _save_checkpoint(config, conversion_results, sql_files[0].name)

    # -- Phase 4: Validation (context-aware) ------------------------------------
    logger.info("\n" + "=" * 60)
    logger.info("PHASE 4: VALIDATION & REPORT")
    logger.info("=" * 60)

    output_files = sorted(pyspark_dir.glob("*.py"))
    validation_options = options_factory.validation()
    phase_start = time.monotonic()

    validation_results, dep_context_by_file = await validation.validate_all(
        output_files=output_files,
        options=validation_options,
        config=config,
        plan=plan,
        inventories=inventories,
    )

    for vr in validation_results:
        cost.validation += vr.cost_usd

    timings.validation_seconds = round(time.monotonic() - phase_start, 1)
    valid_count = sum(1 for vr in validation_results if vr.syntax_valid and vr.pyspark_correct)
    issue_count = sum(len(vr.issues) for vr in validation_results)
    logger.info(
        "\nValidation complete: %d valid, %d issues (cost: $%.4f, %.1fs)",
        valid_count, issue_count, cost.validation, timings.validation_seconds,
    )

    # -- Phase 5: Auto-Fix -------------------------------------------------------
    auto_fix_results: list[AutoFixResult] = []
    developer_action_items: DeveloperActionItems = DeveloperActionItems()

    if not config.skip_auto_fix:
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 5: AUTO-FIX")
        logger.info("=" * 60)

        auto_fix_options = options_factory.auto_fix()
        phase_start = time.monotonic()
        auto_fix_results = await auto_fix.fix_all(
            validation_results=validation_results,
            options=auto_fix_options,
            config=config,
            dep_context_by_file=dep_context_by_file,
        )

        for afr in auto_fix_results:
            cost.auto_fix += afr.cost_usd

        timings.auto_fix_seconds = round(time.monotonic() - phase_start, 1)
        fixed_count = sum(
            1 for afr in auto_fix_results
            if afr.status.value in ("fixed", "partial")
        )
        reverted_count = sum(1 for afr in auto_fix_results if afr.was_reverted)
        logger.info(
            "\nAuto-fix complete: %d fixed, %d reverted (cost: $%.4f, %.1fs)",
            fixed_count, reverted_count, cost.auto_fix, timings.auto_fix_seconds,
        )
    else:
        logger.info("\n[SKIP] Phase 5: Auto-Fix skipped (--skip-autofix flag)")

    # -- Collect TODOs from generated files -------------------------------------
    todos_in_code = _collect_todos(pyspark_dir)

    # -- Build Developer Action Items -------------------------------------------
    developer_action_items = auto_fix.build_developer_action_items(
        validation_results=validation_results,
        auto_fix_results=auto_fix_results,
        todos_in_code=todos_in_code,
    )

    # -- Generate & Save Report -------------------------------------------------
    timings.total_seconds = round(time.monotonic() - start_time, 1)
    file_complexity = inventories[0].file_complexity if inventories else ""
    report = validation.generate_report(
        conversion_results=conversion_results,
        validation_results=validation_results,
        cost_breakdown=cost,
        file_complexity=file_complexity,
        auto_fix_results=auto_fix_results,
        developer_action_items=developer_action_items,
        phase_timings=timings,
    )

    report_json = report.model_dump_json(indent=2)
    report_path = config.report_file(sql_files[0].name)
    report_path.write_text(report_json, encoding="utf-8")

    ai = developer_action_items

    script_dir = config.script_output_dir(sql_files[0].name)
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
    logger.info(
        "  Time: %.1fs  (discovery: %.1fs | planning: %.1fs | conversion: %.1fs"
        " | validation: %.1fs | auto_fix: %.1fs)",
        timings.total_seconds, timings.discovery_seconds, timings.planning_seconds,
        timings.conversion_seconds, timings.validation_seconds, timings.auto_fix_seconds,
    )
    if ai.auto_fixed:
        logger.info("  Auto-fixed: %d issues", len(ai.auto_fixed))
    if ai.requires_manual:
        logger.info("  Manual fixes needed: %d  (see developer_action_items.requires_manual)", len(ai.requires_manual))
    if ai.infrastructure_setup:
        logger.info("  Infrastructure setup: %d items", len(ai.infrastructure_setup))
    if ai.summary:
        logger.info("  Summary: %s", ai.summary)
    logger.info("  Output:  %s", script_dir)
    logger.info("    PySpark: %s", pyspark_dir)
    logger.info("    Reports: %s", reports_dir)
    logger.info("    Report:  %s", report_path)

    return report


# -- Helpers -------------------------------------------------------------------


def _collect_todos(pyspark_dir: Path) -> list[str]:
    """Scan all generated .py files for TODO comment lines."""
    todos: list[str] = []
    for py_file in sorted(pyspark_dir.glob("*.py")):
        try:
            for line in py_file.read_text(encoding="utf-8").splitlines():
                if "TODO" in line:
                    todos.append(f"{py_file.name}: {line.strip()}")
        except OSError:
            pass
    return todos


# -- Phase Report Saving -------------------------------------------------------


def _save_discovery_report(
    config: ConverterConfig,
    inventories: list[FileInventory],
    cost: CostBreakdown,
    timings: PhaseTimings,
    sql_filename: str,
) -> None:
    """Save Phase 1 discovery results as a standalone JSON report."""
    output = {
        "phase": "discovery",
        "description": "Phase 1: Object inventory, dialect detection, complexity scoring",
        "inventories": [inv.model_dump() for inv in inventories],
        "summary": {
            "total_files": len(inventories),
            "total_objects": sum(len(inv.objects) for inv in inventories),
            "dialect": inventories[0].dialect if inventories else "unknown",
            "file_complexity": inventories[0].file_complexity if inventories else "",
            "file_complexity_score": inventories[0].file_complexity_score if inventories else 0,
            "objects": [
                {
                    "name": obj.name,
                    "type": obj.type,
                    "line_count": obj.line_count,
                    "complexity_level": obj.complexity_level,
                    "complexity_score": obj.complexity_score,
                    "has_cursor": obj.has_cursor,
                    "has_dynamic_sql": obj.has_dynamic_sql,
                    "temp_tables_created": obj.temp_tables_created,
                    "known_limitations": obj.known_limitations,
                }
                for inv in inventories
                for obj in inv.objects
            ],
        },
        "cost_usd": cost.discovery,
        "duration_seconds": timings.discovery_seconds,
    }
    discovery_path = config.discovery_file(sql_filename)
    discovery_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    logger.info("Discovery report saved to: %s", discovery_path)


def _save_conversion_plan_report(
    config: ConverterConfig,
    plan: ConversionPlan,
    cost: CostBreakdown,
    timings: PhaseTimings,
    sql_filename: str,
) -> None:
    """Save Phase 2 conversion plan as a standalone JSON report."""
    output = {
        "phase": "planning",
        "description": "Phase 2: Dependency analysis, topological sort, per-object conversion instructions",
        "conversion_plan": plan.model_dump(),
        "summary": {
            "total_objects": plan.total_objects,
            "conversion_levels": len(plan.conversion_levels),
            "levels": [
                {
                    "level": lvl.level,
                    "objects": lvl.objects,
                    "strategy": lvl.strategy,
                }
                for lvl in plan.conversion_levels
            ],
            "dependency_count": len(plan.dependency_edges),
            "dependency_edges": [
                {"source": e.source, "target": e.target, "relationship": e.relationship}
                for e in plan.dependency_edges
            ],
        },
        "cost_usd": cost.planning,
        "duration_seconds": timings.planning_seconds,
        "cumulative_cost_usd": cost.discovery + cost.planning,
        "cumulative_duration_seconds": timings.discovery_seconds + timings.planning_seconds,
    }
    plan_path = config.conversion_plan_file(sql_filename)
    plan_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    logger.info("Conversion plan saved to: %s", plan_path)


def _save_dry_run_output(
    config: ConverterConfig,
    inventories: list[FileInventory],
    plan: ConversionPlan,
    cost: CostBreakdown,
    sql_filename: str,
) -> None:
    """Save combined dry-run analysis (backwards compatible + into reports/)."""
    output = {
        "mode": "dry_run",
        "inventories": [inv.model_dump() for inv in inventories],
        "conversion_plan": plan.model_dump(),
        "cost_so_far": cost.model_dump(),
    }
    # Save into reports/ subfolder
    dry_run_path = config.reports_dir(sql_filename) / "dry_run_analysis.json"
    dry_run_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    logger.info("Dry run output saved to: %s", dry_run_path)


# -- Checkpoint Management -----------------------------------------------------


def _save_checkpoint(
    config: ConverterConfig,
    results: list[ConversionResult],
    sql_filename: str,
) -> None:
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
    checkpoint_path = config.checkpoint_file(sql_filename)
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")


def _load_checkpoint(config: ConverterConfig, sql_filename: str) -> dict | None:
    """Load checkpoint if it exists."""
    checkpoint_path = config.checkpoint_file(sql_filename)
    if checkpoint_path.exists():
        try:
            return json.loads(checkpoint_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return None
