from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql.types import DecimalType

# ---------------------------------------------------------------------------
# NOTE: The following stub imports represent the already-converted (or
# yet-to-be-converted) companion modules.  Update the import paths once those
# modules are available.
# ---------------------------------------------------------------------------
# from stage_sales_data import usp_stage_sales_data, StageSalesDataParams
# from build_customer_profile import usp_build_customer_profile, BuildCustomerProfileParams
# from calculate_revenue import usp_calculate_revenue, CalculateRevenueParams

logger = logging.getLogger(__name__)


# === Dataclasses ===========================================================

@dataclass
class GenerateReportParams:
    """Parameters for usp_GenerateReport (SQL lines 394-396)."""

    start_date: date
    end_date: date
    report_type: str = "Full"


# === Helper utilities ======================================================

def _nullif_zero(col_expr):
    """Return *col_expr* replaced with NULL when equal to zero.

    Mirrors SQL ``NULLIF(expr, 0)`` and guards against division-by-zero.
    GOTCHA #5: Use DecimalType(19, 4) downstream for precision.
    """
    return F.when(col_expr != F.lit(0), col_expr)


# === Pipeline steps (SQL lines 393-483) ====================================

def _step1_call_upstream_procedures(
    spark: SparkSession,
    params: GenerateReportParams,
) -> tuple[DataFrame, DataFrame, DataFrame, Optional[DataFrame]]:
    """Call upstream stored-procedure equivalents (SQL lines 404-405).

    ARCHITECTURAL REFACTOR:
        In the original SQL, both ``usp_BuildCustomerProfile`` and
        ``usp_CalculateRevenue`` internally call ``usp_StageSalesData``,
        which populates ``#SalesStaging``.  In PySpark we call
        ``usp_stage_sales_data`` **once** and pass the resulting DataFrame
        to both downstream functions to avoid redundant computation.

    Returns:
        (sales_staging_df, customer_profile_df, revenue_calc_df, projections_df)
    """
    # TODO: Uncomment and wire up once companion modules are converted.
    # ---------------------------------------------------------------
    # sales_staging_df = usp_stage_sales_data(
    #     spark,
    #     StageSalesDataParams(
    #         start_date=params.start_date,
    #         end_date=params.end_date,
    #     ),
    # )
    # sales_staging_df = sales_staging_df.cache()
    # sales_staging_df.count()  # materialize
    #
    # customer_profile_df = usp_build_customer_profile(
    #     spark,
    #     BuildCustomerProfileParams(
    #         start_date=params.start_date,
    #         end_date=params.end_date,
    #     ),
    #     sales_staging_df=sales_staging_df,   # <-- pass pre-built staging
    # )
    # customer_profile_df = customer_profile_df.cache()
    # customer_profile_df.count()
    #
    # revenue_calc_df, monthly_summary_df, projections_df = usp_calculate_revenue(
    #     spark,
    #     CalculateRevenueParams(
    #         start_date=params.start_date,
    #         end_date=params.end_date,
    #         include_projections=True,
    #     ),
    #     sales_staging_df=sales_staging_df,   # <-- pass pre-built staging
    # )
    # revenue_calc_df = revenue_calc_df.cache()
    # revenue_calc_df.count()

    # --- Placeholder: read from existing tables / temp views until modules are ready ---
    sales_staging_df = spark.table("sales_staging").cache()
    sales_staging_df.count()

    customer_profile_df = spark.table("customer_profile").cache()
    customer_profile_df.count()

    revenue_calc_df = spark.table("revenue_calc").cache()
    revenue_calc_df.count()

    projections_df: Optional[DataFrame] = None
    if spark.catalog.tableExists("projections"):
        projections_df = spark.table("projections")

    return sales_staging_df, customer_profile_df, revenue_calc_df, projections_df


def _step2_summary_report(
    spark: SparkSession,
    params: GenerateReportParams,
    sales_staging_df: DataFrame,
    revenue_calc_df: DataFrame,
) -> DataFrame:
    """Build executive summary report (SQL lines 407-421).

    Uses single-row aggregations on cached DataFrames (.collect() is
    acceptable here since the result is always one row).

    GOTCHA #1: DATEDIFF argument order is reversed in PySpark.
    GOTCHA #9: COUNT(*) vs COUNT(col) — use countDistinct for columns.
    """
    # Pre-compute scalar aggregations --------------------------------
    # SQL line 412: DATEDIFF(day, @StartDate, @EndDate)
    report_days = (params.end_date - params.start_date).days

    staging_agg = (
        sales_staging_df.agg(
            F.countDistinct("CustomerID").alias("TotalCustomers"),       # line 413
            F.countDistinct("OrderID").alias("TotalOrders"),             # line 414
            F.sum("LineTotal").cast(DecimalType(19, 4)).alias("GrossRevenue"),  # line 415
            F.avg("LineTotal").cast(DecimalType(19, 4)).alias("AvgOrderValue"),  # line 419
            F.countDistinct("CategoryName").alias("CategoriesActive"),   # line 420
        )
        .collect()[0]
    )

    revenue_agg = (
        revenue_calc_df.agg(
            F.sum("LineTotal").cast(DecimalType(19, 4)).alias("GrossRevenueCalc"),  # line 416
            F.sum("NetRevenue").cast(DecimalType(19, 4)).alias("NetRevenue"),        # line 417
            F.sum("Profit").cast(DecimalType(19, 4)).alias("TotalProfit"),            # line 418
        )
        .collect()[0]
    )

    summary_df = spark.createDataFrame(
        [
            (
                params.start_date,
                params.end_date,
                report_days,
                staging_agg["TotalCustomers"],
                staging_agg["TotalOrders"],
                staging_agg["GrossRevenue"],
                revenue_agg["GrossRevenueCalc"],
                revenue_agg["NetRevenue"],
                revenue_agg["TotalProfit"],
                staging_agg["AvgOrderValue"],
                staging_agg["CategoriesActive"],
            )
        ],
        schema=[
            "ReportStartDate",
            "ReportEndDate",
            "ReportDays",
            "TotalCustomers",
            "TotalOrders",
            "GrossRevenue",
            "GrossRevenueCalc",
            "NetRevenue",
            "TotalProfit",
            "AvgOrderValue",
            "CategoriesActive",
        ],
    )
    return summary_df


def _step3_customer_report(
    customer_profile_df: DataFrame,
) -> DataFrame:
    """Top-20 customer report with action recommendations (SQL lines 423-444).

    GOTCHA #2: String comparisons are case-sensitive in PySpark — the
              ReportType check is handled by the caller.
    GOTCHA #3: NULL ordering — use desc_nulls_last() to match SQL Server.
    """
    customer_report_df = (
        customer_profile_df.select(
            F.col("CustomerID"),
            F.col("CustomerName"),
            F.col("Region"),
            F.col("TotalOrders"),
            F.col("TotalSpend"),
            F.col("AvgOrderValue"),
            F.col("EngagementStatus"),
            F.col("SpendRank"),
            F.col("SpendPercentile"),
            F.col("DaysSinceLastOrder"),
            # SQL lines 436-442: CASE ActionRecommendation
            F.when(
                (F.col("DaysSinceLastOrder") <= 30) & (F.col("TotalSpend") > 1000),
                F.lit("Retain (VIP Active)"),
            )
            .when(
                (F.col("DaysSinceLastOrder") <= 90) & (F.col("TotalSpend") > 500),
                F.lit("Engage (High Potential)"),
            )
            .when(
                (F.col("DaysSinceLastOrder") > 180) & (F.col("TotalSpend") > 1000),
                F.lit("Win Back (Lapsed VIP)"),
            )
            .when(
                F.col("DaysSinceLastOrder") > 90,
                F.lit("Re-engage"),
            )
            .otherwise(F.lit("Monitor"))
            .alias("ActionRecommendation"),
        )
        # GOTCHA #3: desc_nulls_last to match SQL Server default NULL ordering
        .orderBy(F.col("TotalSpend").desc_nulls_last())
        .limit(20)
    )
    return customer_report_df


def _step4_category_analysis(
    sales_staging_df: DataFrame,
    revenue_calc_df: DataFrame,
) -> DataFrame:
    """Category-level analysis with revenue share and margin (SQL lines 447-462).

    GOTCHA #3: NULL ordering for ROW_NUMBER window.
    GOTCHA #5: Decimal precision — cast to DecimalType(19, 4).

    NOTE (SQL line 460): The original SQL joins ``#SalesStaging`` to
    ``#RevenueCalc`` on ``OrderID AND ProductID``.  If ``#RevenueCalc``
    does not contain ``ProductID``, the join must be on ``OrderID`` only.
    TODO: Verify that revenue_calc contains ProductID; if not, join on
    OrderID alone or add ProductID to the upstream calculation.
    """
    # SQL line 460: LEFT JOIN #RevenueCalc r ON s.OrderID = r.OrderID AND s.ProductID = r.ProductID
    joined_df = sales_staging_df.alias("s").join(
        revenue_calc_df.alias("r"),
        on=[
            F.col("s.OrderID") == F.col("r.OrderID"),
            F.col("s.ProductID") == F.col("r.ProductID"),
        ],
        how="left",
    )

    # Aggregate by CategoryName
    category_agg_df = (
        joined_df.groupBy(F.col("s.CategoryName").alias("CategoryName"))
        .agg(
            F.countDistinct(F.col("s.OrderID")).alias("Orders"),            # line 451
            F.countDistinct(F.col("s.CustomerID")).alias("UniqueCustomers"),  # line 452
            F.sum(F.col("s.LineTotal")).cast(DecimalType(19, 4)).alias("Revenue"),  # line 453
            F.avg(F.col("s.LineTotal")).cast(DecimalType(19, 4)).alias("AvgOrderValue"),  # line 454
            F.sum(F.col("r.Profit")).cast(DecimalType(19, 4)).alias("CategoryProfit"),  # line 457
        )
    )

    # SQL line 455: Revenue share = Revenue * 100.0 / NULLIF(SUM(Revenue) OVER (), 0)
    total_revenue_window = Window.orderBy(F.lit(1)).rowsBetween(
        Window.unboundedPreceding, Window.unboundedFollowing
    )

    # SQL line 456: ROW_NUMBER() OVER (ORDER BY SUM(s.LineTotal) DESC)
    # GOTCHA #3: desc_nulls_last for NULL ordering
    rank_window = Window.orderBy(F.col("Revenue").desc_nulls_last())

    category_df = (
        category_agg_df
        .withColumn(
            "RevenueSharePct",
            (
                F.col("Revenue").cast(DecimalType(19, 4))
                * F.lit(100.0).cast(DecimalType(19, 4))
                / _nullif_zero(
                    F.sum("Revenue").over(total_revenue_window).cast(DecimalType(19, 4))
                )
            ).cast(DecimalType(19, 4)),
        )
        .withColumn(
            "RevenueRank",
            F.row_number().over(rank_window),
        )
        .withColumn(
            # SQL line 458: CAST(SUM(r.Profit) AS DECIMAL(19,4)) / NULLIF(SUM(s.LineTotal), 0) * 100
            "MarginPct",
            (
                F.col("CategoryProfit").cast(DecimalType(19, 4))
                / _nullif_zero(F.col("Revenue"))
                * F.lit(100).cast(DecimalType(19, 4))
            ).cast(DecimalType(19, 4)),
        )
        .select(
            "CategoryName",
            "Orders",
            "UniqueCustomers",
            "Revenue",
            "AvgOrderValue",
            "RevenueSharePct",
            "RevenueRank",
            "CategoryProfit",
            "MarginPct",
        )
        # GOTCHA #3: desc_nulls_last for final ordering
        .orderBy(F.col("Revenue").desc_nulls_last())
    )
    return category_df


def _step5_log_report(
    spark: SparkSession,
    params: GenerateReportParams,
) -> None:
    """Log report generation metadata (SQL lines 465-466).

    TODO: Implement as Delta Lake append or external logging mechanism.
    SYSTEM_USER → spark.sparkContext.sparkUser() or pass as parameter.
    """
    # TODO: Replace with Delta Lake write once dbo.ReportLog is converted.
    generated_by = spark.sparkContext.sparkUser()
    log_row = spark.createDataFrame(
        [
            (
                params.report_type,
                params.start_date,
                params.end_date,
                datetime.now(),
                generated_by,
            )
        ],
        schema=["ReportType", "StartDate", "EndDate", "GeneratedAt", "GeneratedBy"],
    )
    logger.info(
        "Report generated: type=%s, start=%s, end=%s, by=%s",
        params.report_type,
        params.start_date,
        params.end_date,
        generated_by,
    )
    # TODO: Uncomment when Delta table is available:
    # log_row.write.format("delta").mode("append").saveAsTable("dbo.ReportLog")
    return log_row


# === Entry point ===========================================================

def run_pipeline(
    spark: SparkSession,
    params: GenerateReportParams,
) -> dict[str, DataFrame]:
    """Execute the report-generation pipeline (SQL lines 393-483).

    Converts ``dbo.usp_GenerateReport`` to PySpark.  Returns a dictionary
    of named result DataFrames whose keys depend on ``params.report_type``.

    Args:
        spark: Active SparkSession.
        params: Report parameters (start_date, end_date, report_type).

    Returns:
        Dictionary with keys like ``"summary"``, ``"customers"``,
        ``"categories"``, ``"report_log"`` mapped to their DataFrames.

    Raises:
        RuntimeError: On any processing failure (mirrors RAISERROR).
    """
    results: dict[str, DataFrame] = {}

    # TODO: Consider Delta Lake ACID transactions for atomicity (SQL lines 401-402, 468).
    try:
        # === Section 1: Call upstream procedures (SQL lines 404-405) ===
        (
            sales_staging_df,
            customer_profile_df,
            revenue_calc_df,
            projections_df,
        ) = _step1_call_upstream_procedures(spark, params)

        if projections_df is not None:
            results["projections"] = projections_df

        # === Section 2: Summary report (SQL lines 407-421) ===
        # GOTCHA #2: Case-sensitive comparison — ensure report_type matches case
        if params.report_type in ("Full", "Summary"):
            results["summary"] = _step2_summary_report(
                spark, params, sales_staging_df, revenue_calc_df
            )

        # === Section 3: Customer report (SQL lines 423-445) ===
        if params.report_type in ("Full", "Customers"):
            results["customers"] = _step3_customer_report(customer_profile_df)

        # === Section 4: Category analysis (SQL lines 447-463) ===
        if params.report_type in ("Full", "Categories"):
            results["categories"] = _step4_category_analysis(
                sales_staging_df, revenue_calc_df
            )

        # === Section 5: Report logging (SQL lines 465-466) ===
        # TODO: Implement as Delta Lake append once dbo.ReportLog table is available.
        results["report_log"] = _step5_log_report(spark, params)

        # Unpersist cached DataFrames to free memory
        sales_staging_df.unpersist()
        customer_profile_df.unpersist()
        revenue_calc_df.unpersist()

    except Exception as e:
        # === Error handling (SQL lines 470-482) ===
        # SQL lines 471-472: @@TRANCOUNT / ROLLBACK → skip (no transaction semantics)
        # SQL lines 474-476: ERROR_MESSAGE / ERROR_SEVERITY / ERROR_LINE
        error_message = str(e)
        logger.error("Report generation failed: %s", error_message)

        # TODO: Implement error logging to Delta table or external system
        # (SQL lines 478-479: INSERT INTO dbo.ErrorLog)
        try:
            error_log_df = spark.createDataFrame(
                [
                    (
                        error_message,
                        None,  # ErrorSeverity — no PySpark equivalent
                        None,  # ErrorLine — no PySpark equivalent
                        datetime.now(),
                    )
                ],
                schema=["ErrorMessage", "ErrorSeverity", "ErrorLine", "OccurredAt"],
            )
            # TODO: Uncomment when Delta table is available:
            # error_log_df.write.format("delta").mode("append").saveAsTable("dbo.ErrorLog")
            logger.error("Error log entry created (not persisted — Delta table TODO)")
        except Exception as log_err:
            logger.warning("Failed to create error log entry: %s", log_err)

        # SQL line 481: RAISERROR → raise RuntimeError
        raise RuntimeError(error_message) from e

    return results


# === CLI entry point =======================================================

def main() -> None:
    """Command-line interface for the report-generation pipeline."""
    parser = argparse.ArgumentParser(
        description="Generate ecommerce analytics report (PySpark)."
    )
    parser.add_argument(
        "--start-date",
        required=True,
        type=date.fromisoformat,
        help="Report start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        type=date.fromisoformat,
        help="Report end date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--report-type",
        default="Full",
        choices=["Full", "Summary", "Customers", "Categories"],
        help="Report type (default: Full). Case-sensitive.",
    )
    parser.add_argument(
        "--app-name",
        default="GenerateReport",
        help="Spark application name",
    )
    args = parser.parse_args()

    spark = (
        SparkSession.builder
        .appName(args.app_name)
        .getOrCreate()
    )

    try:
        params = GenerateReportParams(
            start_date=args.start_date,
            end_date=args.end_date,
            report_type=args.report_type,
        )
        results = run_pipeline(spark, params)

        for name, df in results.items():
            print(f"\n{'=' * 60}")
            print(f"  Result: {name}")
            print(f"{'=' * 60}")
            df.show(truncate=False)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
