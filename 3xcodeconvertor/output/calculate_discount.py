from __future__ import annotations

import argparse

from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DecimalType


# === Section 1: fn_CalculateDiscount (SQL lines 30-62) ===
# TODO: Scalar UDF — inlined as Column expression, not Python UDF (Gotcha #8)


def fn_calculate_discount(
    order_amount: Column,
    customer_tier: Column,
    is_holiday_season: Column,
) -> Column:
    """Calculate discount amount based on customer tier, holiday season, and order amount.

    Converted from: dbo.fn_CalculateDiscount (SQL lines 30-62)
    Returns a PySpark Column expression (NOT a Python UDF) to avoid
    the 50-100x performance penalty (Gotcha #8).

    Args:
        order_amount: Order amount as DECIMAL(19,4).
        customer_tier: Customer tier string ('Platinum', 'Gold', 'Silver', 'Bronze').
        is_holiday_season: BIT/Boolean flag indicating holiday season.

    Returns:
        Column expression representing the final discount amount as DECIMAL(19,4).
    """
    # --- Discount rate by customer tier (SQL lines 42-48) ---
    # GOTCHA #2: String comparisons are case-sensitive in PySpark.
    # Use F.lower() to match SQL Server's case-insensitive behaviour.
    tier_lower = F.lower(customer_tier)
    discount_rate: Column = (
        F.when(tier_lower == "platinum", 0.15)
        .when(tier_lower == "gold", 0.10)
        .when(tier_lower == "silver", 0.05)
        .when(tier_lower == "bronze", 0.02)
        .otherwise(0.0)
        .cast(DecimalType(5, 4))
    )

    # --- Holiday season bonus (SQL lines 50-51) ---
    # GOTCHA #10: BIT may arrive as BooleanType (True/False) or IntegerType (1/0).
    # Handle both by casting to int before comparison.
    discount_rate = (
        F.when(
            is_holiday_season.cast("int") == 1,
            discount_rate + F.lit(0.05).cast(DecimalType(5, 4)),
        )
        .otherwise(discount_rate)
        .cast(DecimalType(5, 4))
    )

    # --- Cap discount rate at 0.25 (SQL lines 53-54) ---
    discount_rate = F.least(
        discount_rate, F.lit(0.25).cast(DecimalType(5, 4))
    ).cast(DecimalType(5, 4))

    # --- Final discount = order_amount * discount_rate (SQL line 56) ---
    # GOTCHA #5: Use DecimalType(19,4) to preserve precision.
    final_discount: Column = (
        order_amount.cast(DecimalType(19, 4)) * discount_rate
    ).cast(DecimalType(19, 4))

    # --- Minimum discount of 1.0 when order > 50 (SQL lines 58-59) ---
    final_discount = (
        F.when(
            (order_amount > F.lit(50).cast(DecimalType(19, 4)))
            & (final_discount < F.lit(1.0).cast(DecimalType(19, 4))),
            F.lit(1.0).cast(DecimalType(19, 4)),
        )
        .otherwise(final_discount)
        .cast(DecimalType(19, 4))
    )

    return final_discount


# === Section 2: Pipeline entry point ===


def run_pipeline(spark: SparkSession, params: argparse.Namespace) -> DataFrame:
    """Run the discount calculation pipeline.

    Args:
        spark: Active SparkSession.
        params: CLI parameters with input_path and output_path.

    Returns:
        DataFrame with an added 'discount_amount' column.
    """
    df: DataFrame = spark.read.parquet(params.input_path)

    df_result = df.withColumn(
        "discount_amount",
        fn_calculate_discount(
            order_amount=F.col("order_amount"),
            customer_tier=F.col("customer_tier"),
            is_holiday_season=F.col("is_holiday_season"),
        ),
    )

    if params.output_path:
        df_result.write.mode("overwrite").parquet(params.output_path)

    return df_result


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Calculate customer discount amounts from order data."
    )
    parser.add_argument(
        "--input-path",
        required=True,
        help="Path to input Parquet file/directory.",
    )
    parser.add_argument(
        "--output-path",
        default="",
        help="Path to write output Parquet (optional).",
    )
    args = parser.parse_args()

    spark = SparkSession.builder.appName("calculate_discount").getOrCreate()

    try:
        run_pipeline(spark, args)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
