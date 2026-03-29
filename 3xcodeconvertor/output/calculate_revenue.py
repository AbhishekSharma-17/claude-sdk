from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from typing import Optional

from pyspark.sql import DataFrame, SparkSession, Window
import pyspark.sql.functions as F
from pyspark.sql.types import DecimalType

# ---------------------------------------------------------------------------
# Dependency stubs — replace with actual imports once converted
# ---------------------------------------------------------------------------
# from stage_sales_data import usp_stage_sales_data
# from calculate_discount import fn_calculate_discount


def usp_stage_sales_data(
    spark: SparkSession, start_date: date, end_date: date
) -> tuple[DataFrame, None]:
    """Stub for dbo.usp_StageSalesData — replace with real implementation."""
    raise NotImplementedError(
        "usp_stage_sales_data has not been converted yet. "
        "Provide the converted module and update the import."
    )


def fn_calculate_discount(
    line_total: F.Column, price_tier: F.Column, is_holiday: F.Column
) -> F.Column:
    """Stub for dbo.fn_CalculateDiscount — must return a Column expression.

    GOTCHA #8: This MUST be a native Column expression, NOT a Python UDF,
    to avoid the 50-100x performance penalty.
    """
    raise NotImplementedError(
        "fn_calculate_discount has not been converted yet. "
        "Provide the converted module and update the import."
    )


# ---------------------------------------------------------------------------
# Parameter dataclass (SQL lines 290-292)
# ---------------------------------------------------------------------------
@dataclass
class CalculateRevenueParams:
    """Parameters for usp_calculate_revenue.

    Attributes:
        start_date: Inclusive start date for the revenue window.
        end_date: Inclusive end date for the revenue window.
        include_projections: If True, compute next-quarter projection.
    """

    start_date: date
    end_date: date
    include_projections: bool = False


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _nullif_zero(col: F.Column) -> F.Column:
    """Return NULL when *col* equals zero, mirroring T-SQL NULLIF(expr, 0).

    Uses DecimalType(19,4) to preserve precision (GOTCHA #5).
    """
    return F.when(col == 0, F.lit(None).cast(DecimalType(19, 4))).otherwise(col)


# === Section 1: Revenue Calculation (SQL lines 302-327) ===================
def _step1_revenue_calc(
    sales_staging: DataFrame, params: CalculateRevenueParams
) -> DataFrame:
    """Build the #RevenueCalc temp-table equivalent.

    Args:
        sales_staging: Output of usp_stage_sales_data (#SalesStaging).
        params: Pipeline parameters.

    Returns:
        DataFrame with per-line revenue metrics.

    Notes:
        * fn_CalculateDiscount is called once and reused for NetRevenue and
          Profit (LIMITATION: original SQL called it 3× on same inputs).
        * GOTCHA #1: DATEDIFF arg order is reversed in PySpark.
        * GOTCHA #6: months_between returns DOUBLE — cast to int.
    """
    # Holiday flag column (SQL lines 308-310)
    is_holiday_col = (
        F.when(F.month(F.col("OrderDate")).isin([11, 12]), F.lit(1))
        .otherwise(F.lit(0))
    )

    # Compute discount ONCE, reuse (SQL lines 308-317)
    # TODO: fn_CalculateDiscount called 3x on same inputs in SQL — computed once here
    discount_col = fn_calculate_discount(
        F.col("LineTotal"), F.col("PriceTier"), is_holiday_col
    )

    # OrderValueSegment CASE (SQL lines 318-322)
    order_value_segment_col = (
        F.when(F.col("LineTotal") > 500, F.lit("High Value"))
        .when(F.col("LineTotal") > 100, F.lit("Medium Value"))
        .otherwise(F.lit("Low Value"))
    )

    # GOTCHA #6: months_between returns DOUBLE, must cast to int
    # GOTCHA #1: PySpark months_between arg order is (end, start) — reversed vs SQL DATEDIFF
    months_from_start_col = (
        F.months_between(F.col("OrderDate"), F.lit(params.start_date))
        .cast("int")
    )

    revenue_calc = sales_staging.select(
        F.col("OrderID"),
        F.col("CustomerID"),
        F.col("OrderDate"),
        F.col("CategoryName"),
        F.col("LineTotal").alias("GrossRevenue"),
        discount_col.alias("CalculatedDiscount"),
        (F.col("LineTotal") - discount_col).alias("NetRevenue"),
        F.col("ShippingCost"),
        (F.col("LineTotal") - discount_col - F.col("ShippingCost")).alias("Profit"),
        order_value_segment_col.alias("OrderValueSegment"),
        F.col("OrderYear"),
        F.col("OrderMonth"),
        months_from_start_col.alias("MonthsFromStart"),
    )

    # Materialize — equivalent to SELECT INTO #RevenueCalc
    revenue_calc = revenue_calc.cache()
    revenue_calc.count()

    return revenue_calc


# === Section 2: Monthly Summary with Window Functions (SQL lines 329-349) ==
def _step2_monthly_summary(revenue_calc: DataFrame) -> DataFrame:
    """Produce the monthly summary result set with running/rolling windows.

    Args:
        revenue_calc: Output of _step1_revenue_calc.

    Returns:
        Monthly summary DataFrame ordered by (OrderYear, OrderMonth).

    Notes:
        * GOTCHA #4: Explicit rowsBetween for running totals.
        * GOTCHA #5: DecimalType(19,4) for profit margin division.
    """
    # --- First: grouped aggregation (base metrics) ---
    monthly_agg = revenue_calc.groupBy("OrderYear", "OrderMonth").agg(
        F.countDistinct("OrderID").alias("Orders"),
        F.sum("GrossRevenue").alias("TotalGross"),
        F.sum("CalculatedDiscount").alias("TotalDiscounts"),
        F.sum("NetRevenue").alias("TotalNet"),
        F.sum("Profit").alias("TotalProfit"),
    )

    # ProfitMarginPct — NULLIF(SUM(GrossRevenue), 0) (SQL line 337)
    monthly_agg = monthly_agg.withColumn(
        "ProfitMarginPct",
        (
            F.col("TotalProfit").cast(DecimalType(19, 4))
            / _nullif_zero(F.col("TotalGross"))
            * 100
        ),
    )

    # --- Window definitions (GOTCHA #4: explicit rowsBetween) ---
    running_window = (
        Window.orderBy(
            F.col("OrderYear").asc_nulls_first(),
            F.col("OrderMonth").asc_nulls_first(),
        )
        .rowsBetween(Window.unboundedPreceding, Window.currentRow)
    )

    rolling_3m_window = (
        Window.orderBy(
            F.col("OrderYear").asc_nulls_first(),
            F.col("OrderMonth").asc_nulls_first(),
        )
        .rowsBetween(-2, 0)
    )

    lag_window = Window.orderBy(
        F.col("OrderYear").asc_nulls_first(),
        F.col("OrderMonth").asc_nulls_first(),
    )

    # Cumulative revenue (SQL lines 338-341)
    monthly_agg = monthly_agg.withColumn(
        "CumulativeRevenue",
        F.sum("TotalNet").over(running_window),
    )

    # Three-month rolling average (SQL lines 342-345)
    monthly_agg = monthly_agg.withColumn(
        "ThreeMonthAvg",
        F.avg("TotalNet").over(rolling_3m_window),
    )

    # Month-over-month growth (SQL line 346)
    monthly_agg = monthly_agg.withColumn(
        "MoMGrowth",
        F.col("TotalNet") - F.lag("TotalNet").over(lag_window),
    )

    monthly_summary = monthly_agg.orderBy(
        F.col("OrderYear").asc_nulls_first(),
        F.col("OrderMonth").asc_nulls_first(),
    )

    return monthly_summary


# === Section 3: Pivot — Revenue by Category × Month (SQL lines 351-360) ===
def _step3_category_pivot(revenue_calc: DataFrame) -> DataFrame:
    """Pivot net revenue by category and month.

    Args:
        revenue_calc: Output of _step1_revenue_calc.

    Returns:
        Pivoted DataFrame with columns [CategoryName, 1, 2, …, 12].

    Notes:
        TODO: PIVOT at SQL lines 351-360 — uses .groupBy().pivot() with
        explicit value list [1..12].
    """
    pivoted = (
        revenue_calc.select("CategoryName", "OrderMonth", "NetRevenue")
        .groupBy("CategoryName")
        .pivot("OrderMonth", list(range(1, 13)))
        .agg(F.sum("NetRevenue"))
        .orderBy(F.col("CategoryName").asc_nulls_first())
    )

    return pivoted


# === Section 4: Projections — Linear Regression (SQL lines 362-389) =======
def _step4_projections(revenue_calc: DataFrame) -> DataFrame:
    """Compute next-quarter revenue projection via linear trend.

    Args:
        revenue_calc: Output of _step1_revenue_calc.

    Returns:
        Single-row DataFrame with projection metrics.

    Notes:
        * Linear regression slope (SQL lines 377-379):
          slope = (N·Σ(xy) − Σx·Σy) / (N·Σ(x²) − (Σx)²)
        * ISNULL(TrendSlope, 0) → F.coalesce (SQL line 384).
    """
    # MonthlyTrend CTE (SQL lines 364-371)
    month_order_window = Window.orderBy(
        F.col("OrderYear").asc_nulls_first(),
        F.col("OrderMonth").asc_nulls_first(),
    )

    monthly_trend = (
        revenue_calc.groupBy("OrderYear", "OrderMonth")
        .agg(F.sum("NetRevenue").alias("MonthlyRevenue"))
        .withColumn("MonthSeq", F.row_number().over(month_order_window))
    )

    # TrendCalc CTE (SQL lines 373-381)
    # Pre-compute cross-product columns for the linear regression formula
    monthly_trend = monthly_trend.withColumn(
        "SeqTimesRevenue", F.col("MonthSeq") * F.col("MonthlyRevenue")
    ).withColumn(
        "SeqSquared", F.col("MonthSeq") * F.col("MonthSeq")
    )

    trend_calc = monthly_trend.agg(
        F.avg("MonthlyRevenue").alias("AvgMonthly"),
        F.count("*").alias("DataPoints"),
        F.sum("SeqTimesRevenue").alias("SumXY"),
        F.sum("MonthSeq").alias("SumX"),
        F.sum("MonthlyRevenue").alias("SumY"),
        F.sum("SeqSquared").alias("SumX2"),
    )

    # TrendSlope = (N*SumXY - SumX*SumY) / NULLIF(N*SumX2 - SumX*SumX, 0)
    trend_calc = trend_calc.withColumn(
        "TrendSlope",
        (F.col("DataPoints") * F.col("SumXY") - F.col("SumX") * F.col("SumY"))
        / _nullif_zero(
            F.col("DataPoints") * F.col("SumX2") - F.col("SumX") * F.col("SumX")
        ),
    )

    # Final projection (SQL lines 382-388)
    # ISNULL(TrendSlope, 0) → F.coalesce
    projections = trend_calc.select(
        F.lit("Next Quarter Projection").alias("Label"),
        (
            F.col("AvgMonthly") * 3
            + F.coalesce(F.col("TrendSlope"), F.lit(0))
            * (F.col("DataPoints") + F.lit(1.5))
            * 3
        ).alias("ProjectedRevenue"),
        F.col("AvgMonthly").alias("BaselineMonthly"),
        F.col("TrendSlope").alias("MonthlyTrend"),
        F.col("DataPoints").alias("MonthsAnalyzed"),
    )

    return projections


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
def run_pipeline(
    spark: SparkSession, params: CalculateRevenueParams
) -> tuple[DataFrame, DataFrame, Optional[DataFrame]]:
    """Convert dbo.usp_CalculateRevenue (SQL lines 289-390).

    Pipeline:
        1. Stage sales data via usp_stage_sales_data.
        2. Compute per-line revenue metrics (#RevenueCalc).
        3. Aggregate monthly summary with running/rolling windows.
        4. Pivot net revenue by category × month.
        5. Optionally compute next-quarter projection.

    Args:
        spark: Active SparkSession.
        params: Pipeline parameters (start_date, end_date, include_projections).

    Returns:
        Tuple of (revenue_calc, monthly_summary, projections_or_none).
        *projections_or_none* is None when include_projections is False.
    """
    # SQL line 297: EXEC dbo.usp_StageSalesData
    sales_staging, _ = usp_stage_sales_data(spark, params.start_date, params.end_date)

    # TODO: OBJECT_ID checks at SQL lines 299-300 — skipped (not applicable in Spark)

    # Step 1 — #RevenueCalc (SQL lines 302-327)
    revenue_calc = _step1_revenue_calc(sales_staging, params)

    # Step 2 — Monthly summary (SQL lines 329-349)
    monthly_summary = _step2_monthly_summary(revenue_calc)

    # Step 3 — Category × Month pivot (SQL lines 351-360)
    category_pivot = _step3_category_pivot(revenue_calc)

    # Step 4 — Projections (SQL lines 362-389)
    projections: Optional[DataFrame] = None
    if params.include_projections:
        projections = _step4_projections(revenue_calc)

    return revenue_calc, monthly_summary, projections


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    """Command-line interface for usp_calculate_revenue."""
    parser = argparse.ArgumentParser(
        description="Calculate e-commerce revenue metrics (PySpark)."
    )
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--include-projections",
        action="store_true",
        default=False,
        help="Include next-quarter revenue projections",
    )
    args = parser.parse_args()

    spark = SparkSession.builder.appName("calculate_revenue").getOrCreate()

    params = CalculateRevenueParams(
        start_date=date.fromisoformat(args.start_date),
        end_date=date.fromisoformat(args.end_date),
        include_projections=args.include_projections,
    )

    revenue_calc, monthly_summary, projections = run_pipeline(spark, params)

    print("=== Monthly Summary ===")
    monthly_summary.show(truncate=False)

    print("=== Category Pivot ===")
    _step3_category_pivot(revenue_calc).show(truncate=False)

    if projections is not None:
        print("=== Projections ===")
        projections.show(truncate=False)

    spark.stop()


if __name__ == "__main__":
    main()
