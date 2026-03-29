from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql.types import DecimalType

# ---------------------------------------------------------------------------
# Dependency stubs — replace with actual imports once converted
# ---------------------------------------------------------------------------
# from stage_sales_data import usp_stage_sales_data, StageSalesDataParams
# from fn_get_customer_tier import fn_get_customer_tier


@dataclass
class BuildCustomerProfileParams:
    """Parameters for usp_build_customer_profile.

    Attributes:
        start_date: Inclusive start of the reporting window.
        end_date: Inclusive end of the reporting window.
        recalculate_tiers: Whether to compute and append customer tiers.
            Maps to SQL @RecalculateTiers BIT = 1.  GOTCHA #10: BIT/bool
            NULL filtering — always treat as bool, default True.
    """

    start_date: date
    end_date: date
    recalculate_tiers: bool = True


# ---------------------------------------------------------------------------
# Dependency stub: dbo.fn_GetCustomerTier  (SQL line 264)
# TODO: Replace with the real Column-expression implementation once
#       fn_get_customer_tier is converted.  GOTCHA #8 — must remain a native
#       Column expression, never a Python UDF.
# ---------------------------------------------------------------------------
def fn_get_customer_tier(
    total_spend: F.Column,
    total_orders: F.Column,
    account_age_days: F.Column,
) -> F.Column:
    """Placeholder tier logic — mirrors typical SQL scalar function.

    Returns:
        A Column expression producing the tier string.
    """
    return (
        F.when(
            (total_spend >= F.lit(10000)) & (total_orders >= F.lit(20)),
            F.lit("Platinum"),
        )
        .when(
            (total_spend >= F.lit(5000)) & (total_orders >= F.lit(10)),
            F.lit("Gold"),
        )
        .when(
            (total_spend >= F.lit(1000)) & (total_orders >= F.lit(5)),
            F.lit("Silver"),
        )
        .otherwise(F.lit("Bronze"))
    )


# ---------------------------------------------------------------------------
# Dependency stub: dbo.usp_StageSalesData  (SQL line 215)
# TODO: Replace with the real implementation once converted.
# ---------------------------------------------------------------------------
def usp_stage_sales_data(
    spark: SparkSession,
    start_date: date,
    end_date: date,
) -> DataFrame:
    """Placeholder — returns the pre-existing SalesStaging table.

    In production, call the converted usp_stage_sales_data pipeline instead.
    """
    return spark.table("sales_staging")


# === Section 1: Build base customer profile (SQL lines 220-248) ===


def _step1_build_customer_profile(
    spark: SparkSession,
    sales_staging: DataFrame,
    params: BuildCustomerProfileParams,
) -> DataFrame:
    """Join Customers ⟕ SalesStaging, aggregate per customer.

    Args:
        spark: Active SparkSession.
        sales_staging: Output of usp_stage_sales_data (SQL #SalesStaging).
        params: Pipeline parameters.

    Returns:
        DataFrame equivalent to SQL #CustomerProfile (lines 220-248).
    """
    customers: DataFrame = spark.table("customers")  # dbo.Customers

    # SQL line 232: DaysSinceLastOrder is derived from MAX(OrderDate).
    # We compute it as an intermediate column, then build the CASE (lines 236-241).
    # GOTCHA #1: DATEDIFF arg order is REVERSED in PySpark —
    #   SQL: DATEDIFF(day, earlier, later)  →  PySpark: F.datediff(later, earlier)

    profile_df: DataFrame = (
        customers.alias("c")
        .join(
            sales_staging.alias("s"),
            on=F.col("c.CustomerID") == F.col("s.CustomerID"),
            how="left",
        )
        .where(F.col("c.IsActive") == F.lit(1))  # SQL line 245
        .groupBy(
            F.col("c.CustomerID").alias("CustomerID"),
            F.col("c.CustomerName").alias("CustomerName"),
            F.col("c.Email").alias("Email"),
            # SQL line 224: ISNULL(c.Region, 'Unknown')
            F.coalesce(F.col("c.Region"), F.lit("Unknown")).alias("Region"),
            F.col("c.RegistrationDate").alias("RegistrationDate"),
        )
        .agg(
            # SQL line 226  GOTCHA #1: reversed datediff args
            F.datediff(F.current_timestamp(), F.col("RegistrationDate"))
            .alias("AccountAgeDays"),
            # SQL line 227
            F.countDistinct("s.OrderID").alias("TotalOrders"),
            # SQL line 228
            F.coalesce(F.sum("s.LineTotal"), F.lit(0)).alias("TotalSpend"),
            # SQL line 229
            F.coalesce(F.avg("s.LineTotal"), F.lit(0)).alias("AvgOrderValue"),
            # SQL line 230
            F.min("s.OrderDate").alias("FirstOrderDate"),
            # SQL line 231
            F.max("s.OrderDate").alias("LastOrderDate"),
            # SQL line 232  GOTCHA #1: reversed datediff args
            F.datediff(F.current_timestamp(), F.max("s.OrderDate"))
            .alias("DaysSinceLastOrder"),
            # SQL line 233
            F.coalesce(
                F.avg(F.col("s.DaysToShip").cast(DecimalType(10, 2))),
                F.lit(0),
            ).alias("AvgDaysToShip"),
            # SQL line 234
            F.countDistinct("s.CategoryName").alias("UniqueCategoriesPurchased"),
            # SQL line 235
            F.max("s.RunningCustomerTotal").alias("LifetimeValue"),
        )
    )

    # SQL lines 236-241: CASE on DaysSinceLastOrder → EngagementStatus
    profile_df = profile_df.withColumn(
        "EngagementStatus",
        F.when(F.col("DaysSinceLastOrder") <= 30, F.lit("Active"))
        .when(F.col("DaysSinceLastOrder") <= 90, F.lit("Warm"))
        .when(F.col("DaysSinceLastOrder") <= 180, F.lit("Cooling"))
        .otherwise(F.lit("Dormant")),
    )

    return profile_df


# === Section 2: Recalculate tiers — vectorized (SQL lines 250-274) ===


def _step2_apply_customer_tiers(profile_df: DataFrame) -> DataFrame:
    """Vectorized replacement for the CURSOR at SQL lines 255-274.

    The original SQL opens a cursor over #CustomerProfile, calls
    dbo.fn_GetCustomerTier per row, and appends the tier to
    EngagementStatus.  We replace this with two .withColumn() calls.

    GOTCHA #8: fn_get_customer_tier MUST be a native Column expression,
    NOT a Python UDF (50-100× slower).

    Args:
        profile_df: #CustomerProfile DataFrame from step 1.

    Returns:
        DataFrame with CustomerTier and updated EngagementStatus.
    """
    # TODO: Cursor at lines 255-274 — rewritten as vectorized .withColumn()
    #       with fn_get_customer_tier Column expression.

    # SQL line 264: dbo.fn_GetCustomerTier(@Spend, @Orders, @AgeDays)
    profile_df = profile_df.withColumn(
        "CustomerTier",
        fn_get_customer_tier(
            F.col("TotalSpend"),
            F.col("TotalOrders"),
            F.col("AccountAgeDays"),
        ),
    )

    # SQL line 267: EngagementStatus + ' (' + @NewTier + ')'
    profile_df = profile_df.withColumn(
        "EngagementStatus",
        F.concat(
            F.col("EngagementStatus"),
            F.lit(" ("),
            F.col("CustomerTier"),
            F.lit(")"),
        ),
    )

    return profile_df


# === Section 3: Final output with window functions (SQL lines 277-285) ===


def _step3_add_window_rankings(profile_df: DataFrame) -> DataFrame:
    """Add spend-rank and regional-rank window columns.

    GOTCHA #3: NULL ordering is OPPOSITE between SQL Server and PySpark.
    SQL Server sorts NULLs first for ASC / last for DESC by default.
    We explicitly specify asc_nulls_first / desc_nulls_last to match.

    Args:
        profile_df: DataFrame after tier calculation.

    Returns:
        Final DataFrame with ranking columns (SQL lines 277-285).
    """
    # SQL line 279: ROW_NUMBER() OVER (ORDER BY TotalSpend DESC)
    spend_desc_window = Window.orderBy(F.col("TotalSpend").desc_nulls_last())

    # SQL line 280: PERCENT_RANK() OVER (ORDER BY TotalSpend)
    spend_asc_window = Window.orderBy(F.col("TotalSpend").asc_nulls_first())

    # SQL lines 281-283: windows partitioned by Region
    regional_window = Window.partitionBy("Region").orderBy(
        F.col("TotalSpend").desc_nulls_last()
    )

    result_df: DataFrame = (
        profile_df
        # SQL line 279
        .withColumn("SpendRank", F.row_number().over(spend_desc_window))
        # SQL line 280
        .withColumn("SpendPercentile", F.percent_rank().over(spend_asc_window))
        # SQL line 281
        .withColumn("RegionalRank", F.dense_rank().over(regional_window))
        # SQL line 282
        .withColumn(
            "PrevCustomerSpend", F.lag("TotalSpend").over(regional_window)
        )
        # SQL line 283
        .withColumn(
            "NextCustomerSpend", F.lead("TotalSpend").over(regional_window)
        )
        .orderBy(F.col("TotalSpend").desc_nulls_last())  # SQL line 285
    )

    return result_df


# === Pipeline entry point ===


def run_pipeline(
    spark: SparkSession,
    params: BuildCustomerProfileParams,
) -> DataFrame:
    """Execute the usp_BuildCustomerProfile pipeline.

    Converts SQL procedure dbo.usp_BuildCustomerProfile (lines 207-286).

    Args:
        spark: Active SparkSession.
        params: Typed parameters (start_date, end_date, recalculate_tiers).

    Returns:
        Final ranked customer-profile DataFrame.
    """
    # SQL line 215: EXEC dbo.usp_StageSalesData @StartDate, @EndDate
    sales_staging: DataFrame = usp_stage_sales_data(
        spark, params.start_date, params.end_date
    )

    # SQL lines 217-218: OBJECT_ID check — skip (not needed in PySpark)

    # Step 1: Build base customer profile (SQL lines 220-248)
    profile_df: DataFrame = _step1_build_customer_profile(
        spark, sales_staging, params
    )
    # Materialise like temp table — SQL: SELECT … INTO #CustomerProfile
    profile_df = profile_df.cache()
    profile_df.count()

    # Step 2: Optionally recalculate tiers (SQL lines 250-274)
    if params.recalculate_tiers:
        profile_df = _step2_apply_customer_tiers(profile_df)

    # Step 3: Add window rankings (SQL lines 277-285)
    result_df: DataFrame = _step3_add_window_rankings(profile_df)

    return result_df


# === CLI entry point ===


def main() -> None:
    """CLI wrapper for run_pipeline with argparse."""
    parser = argparse.ArgumentParser(
        description="Build customer profile pipeline (converted from "
        "dbo.usp_BuildCustomerProfile)."
    )
    parser.add_argument(
        "--start-date",
        type=date.fromisoformat,
        required=True,
        help="Reporting window start (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        required=True,
        help="Reporting window end (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--no-recalculate-tiers",
        action="store_true",
        default=False,
        help="Skip tier recalculation (default: recalculate).",
    )
    args = parser.parse_args()

    spark = SparkSession.builder.appName(
        "build_customer_profile"
    ).getOrCreate()

    params = BuildCustomerProfileParams(
        start_date=args.start_date,
        end_date=args.end_date,
        recalculate_tiers=not args.no_recalculate_tiers,
    )

    result = run_pipeline(spark, params)
    result.show(truncate=False)

    spark.stop()


if __name__ == "__main__":
    main()
