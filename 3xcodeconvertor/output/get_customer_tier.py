from __future__ import annotations

from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql import functions as F


# === Section 1: Customer Tier Classification (SQL lines 65-89) ===

# TODO: Original SQL was a scalar UDF (dbo.fn_GetCustomerTier).
#       Inlined as a Column expression to avoid Python UDF overhead (50-100x slower).
#       Use via .withColumn("tier", fn_get_customer_tier(F.col("total_spend"), ...))


def fn_get_customer_tier(
    total_spend: Column,
    order_count: Column,
    account_age_days: Column,
) -> Column:
    """Classify a customer into a loyalty tier based on spend, orders, and tenure.

    Converted from: dbo.fn_GetCustomerTier (SQL lines 65-89)
    Returns a PySpark Column expression — NOT a Python UDF.

    Args:
        total_spend: Customer lifetime spend (DECIMAL(19,4)).
        order_count: Total number of orders (INT).
        account_age_days: Days since account creation (INT).

    Returns:
        Column of StringType with one of:
        'Platinum', 'Gold', 'Silver', 'Bronze', 'Standard'.
    """
    # Gotcha #5: comparison thresholds are integer literals; no precision loss
    # since we compare >= against whole numbers, but callers should ensure
    # total_spend is DecimalType(19,4) to preserve upstream precision.
    return (
        F.when(
            (total_spend >= 10000) & (order_count >= 50) & (account_age_days >= 730),
            F.lit("Platinum"),
        )
        .when(
            (total_spend >= 5000) & (order_count >= 25) & (account_age_days >= 365),
            F.lit("Gold"),
        )
        .when(
            (total_spend >= 1000) & (order_count >= 10),
            F.lit("Silver"),
        )
        .when(
            (total_spend >= 100) | (order_count >= 3),
            F.lit("Bronze"),
        )
        .otherwise(F.lit("Standard"))
    )


# ---------------------------------------------------------------------------
# Pipeline entry-point
# ---------------------------------------------------------------------------


def run_pipeline(spark: SparkSession, params: dict | None = None) -> DataFrame:
    """Demo entry-point that applies fn_get_customer_tier to a sample table.

    Args:
        spark: Active SparkSession.
        params: Optional dict with key ``input_table`` (default
                ``"customers"``).

    Returns:
        DataFrame with an added ``customer_tier`` column.
    """
    table_name: str = (params or {}).get("input_table", "customers")
    df: DataFrame = spark.table(table_name)

    result: DataFrame = df.withColumn(
        "customer_tier",
        fn_get_customer_tier(
            F.col("total_spend"),
            F.col("order_count"),
            F.col("account_age_days"),
        ),
    )
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Thin CLI wrapper for ``run_pipeline``."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Compute customer loyalty tiers (PySpark)."
    )
    parser.add_argument(
        "--input-table",
        default="customers",
        help="Fully-qualified Spark table name (default: customers)",
    )
    parser.add_argument(
        "--output-path",
        default=None,
        help="Optional path to write parquet output",
    )
    args = parser.parse_args()

    spark = SparkSession.builder.appName("get_customer_tier").getOrCreate()

    result = run_pipeline(spark, {"input_table": args.input_table})

    if args.output_path:
        result.write.mode("overwrite").parquet(args.output_path)
    else:
        result.show(truncate=False)

    spark.stop()


if __name__ == "__main__":
    main()
