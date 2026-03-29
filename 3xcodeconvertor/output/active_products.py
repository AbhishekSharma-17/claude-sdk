from __future__ import annotations

import argparse

from pyspark.sql import DataFrame, SparkSession
import pyspark.sql.functions as F


# === Section 1: View — vw_ActiveProducts (SQL lines 6-27) ===


def vw_active_products(spark: SparkSession) -> DataFrame:
    """Return active, in-stock products joined with their category.

    Replicates ``dbo.vw_ActiveProducts`` which inner-joins Products to
    Categories and filters to rows that are active, not deleted, and have
    stock on hand.

    Source: ecommerce_analytics.sql lines 6-27

    Args:
        spark: Active SparkSession.

    Returns:
        DataFrame with columns ProductID, ProductName, CategoryID,
        CategoryName, UnitPrice, UnitsInStock, Description, PriceTier,
        DaysSinceListed.
    """
    products_df: DataFrame = spark.table("products")
    categories_df: DataFrame = spark.table("categories")

    # --- JOIN (SQL line 24) ---
    joined_df: DataFrame = products_df.join(
        categories_df,
        on="CategoryID",
        how="inner",
    )

    # --- WHERE filters (SQL lines 25-27) ---
    # GOTCHA #10: BIT/BooleanType — compare explicitly with == True / == False
    # to avoid silent NULL exclusion when the column is BooleanType.
    filtered_df: DataFrame = (
        joined_df
        .where(F.col("IsActive") == True)   # noqa: E712  — intentional for BooleanType safety
        .where(F.col("IsDeleted") == False)  # noqa: E712
        .where(F.col("UnitsInStock") > 0)
    )

    # --- SELECT / computed columns (SQL lines 8-22) ---
    result_df: DataFrame = filtered_df.select(
        F.col("ProductID"),
        F.col("ProductName"),
        F.col("CategoryID"),
        F.col("CategoryName"),
        F.col("UnitPrice"),
        F.col("UnitsInStock"),
        # Line 15: ISNULL → F.coalesce
        F.coalesce(F.col("Description"), F.lit("No description")).alias("Description"),
        # Lines 16-21: CASE on UnitPrice → chained F.when
        (
            F.when(F.col("UnitPrice") > 100, F.lit("Premium"))
            .when(F.col("UnitPrice") > 50, F.lit("Standard"))
            .when(F.col("UnitPrice") > 10, F.lit("Budget"))
            .otherwise(F.lit("Clearance"))
        ).alias("PriceTier"),
        # Line 22: DATEDIFF(day, CreatedDate, GETDATE())
        # GOTCHA #1: PySpark arg order is (end, start) — reversed vs SQL Server
        F.datediff(F.current_timestamp(), F.col("CreatedDate")).alias("DaysSinceListed"),
    )

    return result_df


# === Entry point ===


def run_pipeline(spark: SparkSession, params: argparse.Namespace | None = None) -> DataFrame:
    """Execute the active-products pipeline.

    Args:
        spark: Active SparkSession.
        params: Optional CLI arguments (unused for this simple view).

    Returns:
        Resulting DataFrame.
    """
    return vw_active_products(spark)


def main() -> None:
    """CLI entry point with argparse."""
    parser = argparse.ArgumentParser(
        description="PySpark conversion of dbo.vw_ActiveProducts",
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default=None,
        help="Optional path to write the result as Parquet.",
    )
    args = parser.parse_args()

    spark = (
        SparkSession.builder
        .appName("vw_ActiveProducts")
        .getOrCreate()
    )

    df = run_pipeline(spark, args)

    if args.output_path:
        df.write.mode("overwrite").parquet(args.output_path)
    else:
        df.show(truncate=False)

    spark.stop()


if __name__ == "__main__":
    main()
