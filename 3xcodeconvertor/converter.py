"""sql2spark CLI — Convert SQL scripts to PySpark using Claude Agent SDK.

Usage:
    uv run converter.py                          # full 5-phase pipeline
    uv run converter.py --skip-autofix          # skip Phase 5 (still get action items)
    uv run converter.py --interactive            # approve each conversion
    uv run converter.py --budget 50.0            # cost cap (default: $50)
    uv run converter.py --parallel 5             # concurrent conversions (default: 3)
    uv run converter.py --dry-run                # Phase 1 + 2 only
    uv run converter.py --verbose                # show all tool calls
    uv run converter.py --output-dir ./custom    # custom output directory
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from config import ConverterConfig
from orchestrator import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sql2spark",
        description="Convert SQL scripts to PySpark using Claude Agent SDK (Opus 4.6)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive mode: approve each conversion",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=50.0,
        help="Total budget cap in USD (default: $50.00)",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=3,
        help="Max concurrent conversions (default: 3)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run Phase 1 + 2 only (discovery + planning, no conversion)",
    )
    parser.add_argument(
        "--skip-autofix",
        action="store_true",
        help="Skip Phase 5 auto-fix (issues are reported but not fixed)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Custom output directory (default: ./output)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show all tool calls and intermediate outputs",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        choices=["opus", "sonnet", "haiku"],
        help="Model for conversion (default: from .env SQL2SPARK_MODEL or opus)",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        choices=["anthropic", "bedrock"],
        help="LLM provider (default: from .env SQL2SPARK_PROVIDER or anthropic)",
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    workspace = Path(__file__).parent.resolve()

    config = ConverterConfig(
        workspace=workspace,
        interactive=args.interactive,
        dry_run=args.dry_run,
        verbose=args.verbose,
        total_budget_usd=args.budget,
        max_parallel_conversions=args.parallel,
        skip_auto_fix=args.skip_autofix,
    )

    # CLI args override .env values (only when explicitly passed)
    if args.provider:
        config.provider = args.provider
    if args.model:
        config.conversion_model = args.model
    if args.output_dir:
        config.output_dir = args.output_dir

    if not config.input_path.exists():
        print(f"Error: Input directory not found: {config.input_path}")
        print(f"Create it and add .sql files: mkdir -p {config.input_path}")
        sys.exit(1)

    sql_files = list(config.input_path.glob("*.sql"))
    if not sql_files:
        print(f"Error: No .sql files found in {config.input_path}")
        sys.exit(1)

    # ── Banner ────────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  sql2spark — SQL to PySpark Converter")
    print("  Powered by Claude Agent SDK")
    print("=" * 60)
    print(f"  Workspace:  {workspace}")
    print(f"  Input:      {config.input_path} ({len(sql_files)} files)")
    print(f"  Output:     {config.output_path}")
    print(f"  Provider:   {config.provider_display}")
    print(f"  Model:      {config.model_display}")
    print(f"  Validation: {config.validation_model}")
    print(f"  Auto-fix:   {config.auto_fix_model}")
    print(f"  Budget:     ${config.total_budget_usd:.2f}")
    print(f"  Parallel:   {config.max_parallel_conversions}")
    print(f"  Mode:       {'Interactive' if config.interactive else 'Automated'}")
    if config.dry_run:
        print(f"  Dry run:    Yes (Phase 1 + 2 only)")
    if config.skip_auto_fix:
        print(f"  Auto-fix:   Disabled (--skip-autofix)")
    else:
        print(f"  Phase 5:    Enabled  (${config.auto_fix_budget_per_file:.2f}/file budget)")
    print("=" * 60)
    print()

    # ── Run pipeline ──────────────────────────────────────────────────────
    try:
        report = asyncio.run(run_pipeline(config))
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(130)
    except ValueError as e:
        print(f"Configuration error: {e}")
        sys.exit(1)

    # ── Final summary ─────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"  Objects converted: {report.converted}/{report.total_objects}")
    if report.failed:
        print(f"  Failed:            {report.failed}")
    if report.needs_review:
        print(f"  Needs review:      {report.needs_review}")
    print(f"  Total cost:        ${report.total_cost_usd:.4f}")

    cb = report.cost_breakdown
    pt = report.phase_timings
    print(
        f"  Cost breakdown:    discovery ${cb.discovery:.4f} | "
        f"planning ${cb.planning:.4f} | "
        f"conversion ${cb.conversion:.4f} | "
        f"validation ${cb.validation:.4f}"
        + (f" | auto_fix ${cb.auto_fix:.4f}" if cb.auto_fix else "")
    )
    print(
        f"  Time breakdown:    discovery {pt.discovery_seconds:.1f}s | "
        f"planning {pt.planning_seconds:.1f}s | "
        f"conversion {pt.conversion_seconds:.1f}s | "
        f"validation {pt.validation_seconds:.1f}s"
        + (f" | auto_fix {pt.auto_fix_seconds:.1f}s" if pt.auto_fix_seconds else "")
    )
    print(f"  Total time:        {pt.total_seconds:.1f}s")

    if report.validation_issues:
        print(f"  Validation issues: {len(report.validation_issues)}")

    # Confidence scores
    if report.confidence_scores:
        print(f"\n  Confidence:        {report.overall_confidence:.0f}% overall")
        for cs in report.confidence_scores:
            print(f"    {cs.file}: {cs.score:.0f}% [{cs.grade}]")

    ai = report.developer_action_items
    if ai.auto_fixed:
        print(f"  Auto-fixed:        {len(ai.auto_fixed)} issue(s)")
    if ai.requires_manual:
        print(f"  Manual fixes:      {len(ai.requires_manual)} issue(s) — see developer_action_items.requires_manual")
    if ai.infrastructure_setup:
        print(f"  Infrastructure:    {len(ai.infrastructure_setup)} item(s) — see developer_action_items.infrastructure_setup")
    if ai.recommended_review:
        print(f"  Review items:      {len(ai.recommended_review)} — see developer_action_items.recommended_review")
    if ai.todos_in_code:
        print(f"  TODOs in code:     {len(ai.todos_in_code)}")
    if ai.summary:
        print(f"\n  Action summary: {ai.summary}")

    # Show per-script output paths
    primary_sql = sql_files[0]
    script_dir = config.script_output_dir(primary_sql.name)
    report_file = config.report_file(primary_sql.name)
    print(f"\n  Output:  {script_dir}")
    print(f"    PySpark: {config.pyspark_dir(primary_sql.name)}")
    print(f"    Reports: {config.reports_dir(primary_sql.name)}")
    print(f"    Report:  {report_file}")
    print("=" * 60)

    if report.failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
