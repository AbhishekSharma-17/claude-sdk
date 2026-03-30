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
    FileConfidence,
    FileInventory,
    OutputGroup,
    PhaseTimings,
    SQLObject,
    ValidationResult,
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

    # -- Output Grouping (between Phase 2 and Phase 3) ---------------------------
    output_groups = _compute_output_groups(inventories, plan)
    plan.output_groups = output_groups

    logger.info("\nOutput grouping: %d groups from %d objects", len(output_groups), total_objects)
    for grp in output_groups:
        logger.info(
            "  [%s] %s → %s",
            grp.group_type, grp.output_filename, ", ".join(grp.objects),
        )

    if config.dry_run:
        logger.info("\n[DRY RUN] Stopping after Phase 2. No conversion performed.")
        # Also save combined dry_run_analysis.json for backwards compatibility
        _save_dry_run_output(config, inventories, plan, cost, sql_files[0].name)
        return ConversionReport(
            total_objects=total_objects,
            file_complexity=inventories[0].file_complexity if inventories else "",
            cost_breakdown=cost,
        )

    estimated_conversion_cost = len(output_groups) * 2.0
    remaining_budget = config.total_budget_usd - cost.discovery - cost.planning
    if estimated_conversion_cost > remaining_budget * 1.5:
        logger.warning(
            "Estimated conversion cost ($%.2f) may exceed remaining budget ($%.2f)",
            estimated_conversion_cost, remaining_budget,
        )

    # -- Phase 3: Conversion ----------------------------------------------------
    logger.info("\n" + "=" * 60)
    logger.info("PHASE 3: SQL-TO-PYSPARK CONVERSION (grouped)")
    logger.info("=" * 60)

    # Override output_path for conversion to write into pyspark/ subfolder
    original_output_path = config.output_path
    config._pyspark_output_dir = pyspark_dir

    conversion_options = options_factory.conversion()
    interactive_options = options_factory.conversion_interactive() if config.interactive else None
    phase_start = time.monotonic()

    checkpoint = _load_checkpoint(config, sql_files[0].name)
    if checkpoint:
        logger.info("Resuming from checkpoint: %d groups already converted", len(checkpoint))

    conversion_results = await conversion.convert_all_grouped(
        inventories=inventories,
        plan=plan,
        output_groups=output_groups,
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
        "\nConversion complete: %d/%d groups converted, %d failed (cost: $%.4f, %.1fs)",
        converted_count, len(output_groups), failed_count,
        cost.conversion, timings.conversion_seconds,
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

    # -- Confidence Scoring --------------------------------------------------------
    confidence_scores = _compute_confidence_scores(
        validation_results=validation_results,
        auto_fix_results=auto_fix_results,
        inventories=inventories,
        todos_in_code=todos_in_code,
    )
    overall_confidence = (
        round(sum(c.score for c in confidence_scores) / len(confidence_scores), 1)
        if confidence_scores else 0.0
    )

    logger.info("\nConfidence scores:")
    for cs in confidence_scores:
        logger.info("  %s: %.0f%% [%s]", cs.file, cs.score, cs.grade)
    logger.info("  Overall: %.0f%%", overall_confidence)

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
    report.confidence_scores = confidence_scores
    report.overall_confidence = overall_confidence

    report_json = report.model_dump_json(indent=2)
    report_path = config.report_file(sql_files[0].name)
    report_path.write_text(report_json, encoding="utf-8")

    ai = developer_action_items

    script_dir = config.script_output_dir(sql_files[0].name)
    logger.info("\n" + "=" * 60)
    logger.info("CONVERSION COMPLETE")
    logger.info("=" * 60)
    logger.info(
        "  Groups: %d converted, %d failed (%d SQL objects → %d output files)",
        report.converted, report.failed, total_objects, len(output_groups),
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
    logger.info("  Confidence: %.0f%% overall", overall_confidence)
    for cs in confidence_scores:
        logger.info("    %s: %.0f%% [%s]", cs.file, cs.score, cs.grade)
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


# -- Confidence Scoring --------------------------------------------------------


def _score_to_grade(score: float) -> str:
    """Map a 0-100 confidence score to a letter grade."""
    if score >= 95:
        return "A+"
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _compute_confidence_scores(
    validation_results: list[ValidationResult],
    auto_fix_results: list[AutoFixResult],
    inventories: list[FileInventory],
    todos_in_code: list[str],
) -> list[FileConfidence]:
    """Compute a 0-100 confidence score for each output file.

    Scoring:
      Base: 100 points
      Deductions for remaining issues, known limitations, TODOs
      Recovery for auto-fixed issues
    """
    # Build lookup: which SQL objects have cursors / dynamic SQL
    has_cursor: set[str] = set()
    has_dynamic_sql: set[str] = set()
    for inv in inventories:
        for obj in inv.objects:
            name_lower = obj.name.lower()
            if obj.has_cursor:
                has_cursor.add(name_lower)
            if obj.has_dynamic_sql:
                has_dynamic_sql.add(name_lower)

    # Build auto-fix lookup: file -> AutoFixResult
    fix_map: dict[str, AutoFixResult] = {}
    for afr in auto_fix_results:
        basename = Path(afr.file_path).name
        fix_map[basename] = afr

    # Build TODO count per file
    todo_count: dict[str, int] = {}
    for todo_line in todos_in_code:
        fname = todo_line.split(":")[0].strip() if ":" in todo_line else ""
        if fname:
            todo_count[fname] = todo_count.get(fname, 0) + 1

    scores: list[FileConfidence] = []

    for vr in validation_results:
        basename = Path(vr.file_path).name
        score = 100.0
        factors: list[str] = []

        # Syntax check
        if not vr.syntax_valid:
            score -= 30
            factors.append("-30: Python syntax invalid")

        # Remaining validation issues by severity
        error_count = 0
        high_count = 0
        medium_count = 0
        low_count = 0
        infra_count = 0

        for issue in vr.issues:
            sev = issue.severity.upper()
            msg = issue.message.lower()

            # Check if infrastructure issue
            infra_keywords = (
                "delta", "saveastable", "catalog", "jdbc", "hdfs",
                "s3", "adls", "streaming", "kafka", "infrastructure",
            )
            if any(kw in msg for kw in infra_keywords):
                infra_count += 1
                continue

            if sev == "ERROR":
                error_count += 1
            elif sev == "HIGH":
                high_count += 1
            elif sev in ("MEDIUM", "WARNING"):
                medium_count += 1
            else:
                low_count += 1

        if error_count:
            deduct = error_count * 12
            score -= deduct
            factors.append(f"-{deduct}: {error_count} ERROR issue(s) remaining")
        if high_count:
            deduct = high_count * 8
            score -= deduct
            factors.append(f"-{deduct}: {high_count} HIGH issue(s) remaining")
        if medium_count:
            deduct = medium_count * 3
            score -= deduct
            factors.append(f"-{deduct}: {medium_count} MEDIUM issue(s)")
        if low_count:
            deduct = low_count * 1
            score -= deduct
            factors.append(f"-{deduct}: {low_count} LOW/INFO issue(s)")
        if infra_count:
            deduct = infra_count * 5
            score -= deduct
            factors.append(f"-{deduct}: {infra_count} infrastructure setup needed")

        # Known limitations (cursor / dynamic SQL)
        file_lower = basename.lower()
        cursor_hit = any(name in file_lower for name in has_cursor)
        dynamic_hit = any(name in file_lower for name in has_dynamic_sql)

        if cursor_hit:
            score -= 10
            factors.append("-10: contains cursor logic (no Spark equivalent)")
        if dynamic_hit:
            score -= 8
            factors.append("-8: contains dynamic SQL (runtime-dependent)")

        # TODOs in this file
        file_todos = todo_count.get(basename, 0)
        if file_todos:
            deduct = file_todos * 2
            score -= deduct
            factors.append(f"-{deduct}: {file_todos} TODO(s) in generated code")

        # Auto-fix result
        afr = fix_map.get(basename)
        if afr:
            if afr.was_reverted:
                score -= 15
                factors.append("-15: auto-fix attempted but reverted (syntax broke)")
            elif afr.issues_fixed > 0:
                recovery = min(afr.issues_fixed * 5, 20)
                score += recovery
                factors.append(f"+{recovery}: {afr.issues_fixed} issue(s) auto-fixed")

        # Clamp
        score = max(0.0, min(100.0, round(score, 1)))
        grade = _score_to_grade(score)

        if not factors:
            factors.append("No issues found -- full confidence")

        scores.append(FileConfidence(
            file=basename,
            score=score,
            grade=grade,
            factors=factors,
        ))

    return scores


# -- Output Grouping -----------------------------------------------------------


def _compute_output_groups(
    inventories: list[FileInventory],
    plan: ConversionPlan,
) -> list[OutputGroup]:
    """Determine how SQL objects are grouped into output .py files.

    Production-style grouping:
      - utilities: functions + simple utility procs called by 2+ others
      - main_pipeline: highest-complexity proc + its exclusive helpers
      - standalone: independently schedulable procs (moderate+ complexity)
    """
    # Build lookups
    obj_map: dict[str, SQLObject] = {}
    for inv in inventories:
        for obj in inv.objects:
            obj_map[obj.name] = obj

    if not obj_map:
        return []

    # Count how many objects call each object (in-degree from callers)
    called_by: dict[str, set[str]] = {name: set() for name in obj_map}
    for edge in plan.dependency_edges:
        if edge.target in called_by:
            called_by[edge.target].add(edge.source)

    # Find the main pipeline proc (highest complexity score)
    procs = [
        (name, obj) for name, obj in obj_map.items()
        if obj.type in ("procedure", "view", "trigger")
    ]
    main_proc_name = ""
    if procs:
        main_proc_name = max(procs, key=lambda x: x[1].complexity_score)[0]

    # Determine which helpers are exclusively called by the main proc
    main_exclusive_helpers: set[str] = set()
    if main_proc_name:
        main_obj = obj_map[main_proc_name]
        for ref in main_obj.references:
            if ref in obj_map and ref != main_proc_name:
                callers = called_by.get(ref, set())
                # Exclusive if only the main proc calls it (or nobody — orphan helper)
                if callers <= {main_proc_name}:
                    ref_obj = obj_map[ref]
                    # Only club simple/moderate helpers, not complex standalone procs
                    if ref_obj.complexity_score < 5.0:
                        main_exclusive_helpers.add(ref)

    # Classify each object
    utilities: list[str] = []
    main_group: list[str] = []
    standalone: list[str] = []

    for name, obj in obj_map.items():
        if name == main_proc_name:
            main_group.append(name)
        elif name in main_exclusive_helpers:
            main_group.append(name)
        elif obj.type == "function":
            utilities.append(name)
        elif (
            obj.type == "procedure"
            and obj.complexity_score <= 2.0
            and obj.line_count < 50
            and len(called_by.get(name, set())) >= 2
        ):
            # Simple utility proc called by multiple others
            utilities.append(name)
        else:
            standalone.append(name)

    # Build groups
    groups: list[OutputGroup] = []

    if utilities:
        groups.append(OutputGroup(
            group_name="utilities",
            output_filename="utils.py",
            objects=utilities,
            group_type="utilities",
            description="Shared functions and utility procedures used across the pipeline",
        ))

    if main_group:
        main_snake = _to_snake_case(main_proc_name)
        groups.append(OutputGroup(
            group_name=main_proc_name,
            output_filename=f"{main_snake}.py",
            objects=main_group,
            group_type="main_pipeline",
            description=f"Main pipeline procedure with {len(main_group) - 1} exclusive helpers",
        ))

    for name in standalone:
        snake = _to_snake_case(name)
        groups.append(OutputGroup(
            group_name=name,
            output_filename=f"{snake}.py",
            objects=[name],
            group_type="standalone",
            description=f"Independently schedulable: {obj_map[name].type} ({obj_map[name].complexity_level})",
        ))

    return groups


def _to_snake_case(name: str) -> str:
    """Convert a SQL object name to snake_case Python filename."""
    import re
    name = re.sub(r"^(usp_|sp_|fn_|vw_|trg_|dbo\.)", "", name, flags=re.IGNORECASE)
    name = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
    name = re.sub(r"[^a-zA-Z0-9]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_").lower()
    return name or "unnamed"


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
            "output_groups": [
                {
                    "output_filename": grp.output_filename,
                    "group_type": grp.group_type,
                    "objects": grp.objects,
                    "description": grp.description,
                }
                for grp in plan.output_groups
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
