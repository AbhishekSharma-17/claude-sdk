"""PySpark conversion of dbo.usp_StageSalesData (SQL lines 92-204).

Stages sales order data with customer ranking and daily summaries.

Converted from: ecommerce_analytics.sql lines 92-204
Dialect: T-SQL -> PySpark
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Tuple

from pyspark.sql import DataFrame, SparkSession, Window
import pyspark.sql.functions as F
from pyspark.sql.types import DecimalType


# ---------------------------------------------------------------------------
# Parameters dataclass (SQL lines 93-95)
# ---------------------------------------------------------------------------
@dataclass
class StageSalesDataParams:
    """Parameters for the usp_StageSalesData procedure.

    Attributes:
        start_date: Inclusive start of the order date range.
        end_date: Inclusive end of the order date range.
        min_order_amount: Minimum line total to include (default 0.00).
    """

    start_date: date
    end_date: date
    min_order_amount: Decimal = field(default_factory=lambda: Decimal("0.00"))


# ---------------------------------------------------------------------------
# Dependency stubs — replace with actual table/view readers
# ---------------------------------------------------------------------------
def _read_orders(spark: SparkSession) -> DataFrame:
    """Read dbo.Orders table.

    TODO: Replace with actual table source (e.g. spark.table('dbo.Orders')).
    """
    return spark.table("orders")


def _read_order_details(spark: SparkSession) -> DataFrame:
    """Read dbo.OrderDetails table.

    TODO: Replace with actual table source (e.g. spark.table('dbo.OrderDetails')).
    """
    return spark.table("order_details")


def vw_active_products(spark: SparkSession) -> DataFrame:
    """Read dbo.vw_ActiveProducts view.

    TODO: Replace with actual view/table source or already-converted logic.
    """
    return spark.table("vw_active_products")


# === Section 1: Base Orders CTE (SQL lines 106-128) ===

def _step1_base_orders(
    spark: SparkSession,
    params: StageSalesDataParams,
) -> DataFrame:
    """Build the BaseOrders CTE — joins Orders, OrderDetails, ActiveProducts.

    Args:
        spark: Active SparkSession.
        params: Procedure parameters.

    Returns:
        DataFrame equivalent to the BaseOrders CTE (SQL lines 106-128).
    """
    orders = _read_orders(spark).alias("o")
    order_details = _read_order_details(spark).alias("od")
    active_products = vw_active_products(spark).alias("ap")

    base_orders = (
        orders
        .join(order_details, F.col("o.OrderID") == F.col("od.OrderID"), "inner")
        # SQL line 124: JOIN vw_ActiveProducts
        .join(active_products, F.col("od.ProductID") == F.col("ap.ProductID"), "inner")
        # SQL line 125: WHERE OrderDate BETWEEN @StartDate AND @EndDate
        .where(F.col("o.OrderDate").between(params.start_date, params.end_date))
        # SQL line 126
        .where(F.col("o.OrderStatus") != "Cancelled")
        # SQL line 127
        .where(
            (F.col("od.Quantity") * F.col("od.UnitPrice"))
            >= float(params.min_order_amount)
        )
        .select(
            F.col("o.OrderID").alias("OrderID"),
            F.col("o.CustomerID").alias("CustomerID"),
            F.col("o.OrderDate").alias("OrderDate"),
            F.col("od.ProductID").alias("ProductID"),
            F.col("ap.ProductName").alias("ProductName"),
            F.col("ap.CategoryName").alias("CategoryName"),
            F.col("ap.PriceTier").alias("PriceTier"),
            F.col("od.Quantity").alias("Quantity"),
            # SQL line 116: od.UnitPrice AS OrderUnitPrice
            F.col("od.UnitPrice").alias("OrderUnitPrice"),
            # SQL line 117: od.Quantity * od.UnitPrice AS LineTotal
            (F.col("od.Quantity") * F.col("od.UnitPrice"))
            .cast(DecimalType(19, 4))
            .alias("LineTotal"),
            # SQL line 118: ISNULL(od.Discount, 0) -> F.coalesce
            F.coalesce(F.col("od.Discount"), F.lit(0))
            .cast(DecimalType(19, 4))
            .alias("DiscountApplied"),
            F.col("o.ShippingCost").alias("ShippingCost"),
            F.col("o.OrderStatus").alias("OrderStatus"),
            # SQL line 121: DATEDIFF(day, o.OrderDate, ISNULL(o.ShippedDate, GETDATE()))
            # GOTCHA #1: PySpark datediff arg order is REVERSED (end, start)
            F.datediff(
                F.coalesce(F.col("o.ShippedDate"), F.current_timestamp()),
                F.col("o.OrderDate"),
            ).alias("DaysToShip"),
        )
    )
    return base_orders


# === Section 2: Ranked Orders CTE (SQL lines 129-148) ===

def _step2_ranked_orders(base_orders: DataFrame) -> DataFrame:
    """Add window-function columns from the RankedOrders CTE.

    Args:
        base_orders: Output of _step1_base_orders.

    Returns:
        DataFrame with ranking and running-total columns (SQL lines 129-148).
    """
    # SQL lines 132-135: ROW_NUMBER() OVER (PARTITION BY CustomerID ORDER BY OrderDate DESC)
    # GOTCHA #3: Use desc_nulls_last() to match SQL Server NULL ordering
    w_customer_rank = Window.partitionBy("CustomerID").orderBy(
        F.col("OrderDate").desc_nulls_last()
    )

    # SQL lines 136-140: Running SUM with explicit ROWS frame
    # GOTCHA #4: SQL already specifies ROWS — mirror exactly
    w_running_total = (
        Window.partitionBy("CustomerID")
        .orderBy(F.col("OrderDate").asc_nulls_first())
        .rowsBetween(Window.unboundedPreceding, Window.currentRow)
    )

    # SQL lines 141-143: COUNT(*) OVER (PARTITION BY CategoryName)
    # No ORDER BY → full partition frame is correct
    # GOTCHA #9: COUNT(*) counts all rows including NULLs — use F.count(F.lit(1))
    w_category = Window.partitionBy("CategoryName")

    # SQL lines 144-146: NTILE(4) OVER (ORDER BY LineTotal DESC)
    w_ntile = Window.orderBy(F.col("LineTotal").desc_nulls_last())

    ranked_orders = base_orders.withColumns(
        {
            "CustomerOrderRank": F.row_number().over(w_customer_rank),
            "RunningCustomerTotal": F.sum("LineTotal").over(w_running_total),
            "CategoryOrderCount": F.count(F.lit(1)).over(w_category),
            "RevenueQuartile": F.ntile(4).over(w_ntile),
        }
    )
    return ranked_orders


# === Section 3: Sales Staging — final SELECT + derived columns (SQL lines 149-179) ===

def _step3_sales_staging(ranked_orders: DataFrame) -> DataFrame:
    """Produce the #SalesStaging temp-table equivalent.

    Adds ShippingSpeed, OrderDateOnly, OrderYear, OrderMonth, OrderDayOfWeek.

    Args:
        ranked_orders: Output of _step2_ranked_orders.

    Returns:
        Cached DataFrame equivalent to #SalesStaging (SQL line 178).
    """
    sales_staging = ranked_orders.select(
        "OrderID",
        "CustomerID",
        "OrderDate",
        "ProductID",
        "ProductName",
        "CategoryName",
        "PriceTier",
        "Quantity",
        "OrderUnitPrice",
        "LineTotal",
        "DiscountApplied",
        "ShippingCost",
        "OrderStatus",
        "DaysToShip",
        "CustomerOrderRank",
        "RunningCustomerTotal",
        "CategoryOrderCount",
        "RevenueQuartile",
        # SQL lines 168-173: CASE ShippingSpeed
        F.when(F.col("DaysToShip") <= 2, "Fast")
        .when(F.col("DaysToShip") <= 7, "Normal")
        .when(F.col("DaysToShip") <= 14, "Slow")
        .otherwise("Delayed")
        .alias("ShippingSpeed"),
        # SQL line 174: CAST(OrderDate AS DATE)
        F.col("OrderDate").cast("date").alias("OrderDateOnly"),
        # SQL line 175
        F.year("OrderDate").alias("OrderYear"),
        # SQL line 176
        F.month("OrderDate").alias("OrderMonth"),
        # SQL line 177: DATEPART(weekday, OrderDate) -> dayofweek (1=Sunday)
        F.dayofweek("OrderDate").alias("OrderDayOfWeek"),
    )

    # SQL line 178: SELECT INTO #SalesStaging
    # SQL lines 181-182: CREATE INDEX -> repartition + cache instead
    # TODO: CREATE INDEX replaced with .repartition().cache()
    sales_staging = sales_staging.repartition("CustomerID").cache()
    sales_staging.count()  # materialize the cache
    return sales_staging


# === Section 4: Daily Summary (SQL lines 184-200) ===

def _step4_daily_summary(sales_staging: DataFrame) -> DataFrame:
    """Produce the #DailySummary temp-table equivalent.

    Args:
        sales_staging: Output of _step3_sales_staging.

    Returns:
        DataFrame equivalent to #DailySummary (SQL lines 184-200).
    """
    daily_summary = (
        sales_staging
        .groupBy("OrderDateOnly")
        .agg(
            # SQL line 186: COUNT(DISTINCT OrderID)
            F.countDistinct("OrderID").alias("OrderCount"),
            # SQL line 187
            F.countDistinct("CustomerID").alias("UniqueCustomers"),
            # SQL line 188
            F.sum("LineTotal").alias("DailyRevenue"),
            # SQL line 189
            F.avg("LineTotal").alias("AvgOrderValue"),
            # SQL line 190
            F.min("LineTotal").alias("MinOrderValue"),
            # SQL line 191
            F.max("LineTotal").alias("MaxOrderValue"),
            # SQL lines 192-193: SUM(CASE WHEN ShippingSpeed='Fast' ...)
            F.sum(
                F.when(F.col("ShippingSpeed") == "Fast", 1).otherwise(0)
            ).alias("FastShipCount"),
            F.sum(
                F.when(F.col("ShippingSpeed") == "Delayed", 1).otherwise(0)
            ).alias("DelayedShipCount"),
            # SQL line 194: STRING_AGG(DISTINCT CategoryName, ', ')
            # TODO: STRING_AGG DISTINCT approximated via array_distinct(collect_list()) + concat_ws
            F.concat_ws(
                ", ",
                F.array_distinct(F.collect_list("CategoryName")),
            ).alias("CategoriesSold"),
            # SQL line 195
            F.sum("DiscountApplied").alias("TotalDiscounts"),
            # SQL line 196
            F.sum("ShippingCost").alias("TotalShipping"),
        )
        # SQL line 185: alias OrderDateOnly -> SummaryDate
        .withColumnRenamed("OrderDateOnly", "SummaryDate")
        # SQL line 200: ORDER BY OrderDateOnly
        .orderBy(F.col("SummaryDate").asc_nulls_first())
    )
    return daily_summary


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def run_pipeline(
    spark: SparkSession,
    params: StageSalesDataParams,
) -> Tuple[DataFrame, DataFrame]:
    """Execute the usp_StageSalesData procedure logic.

    Pipeline:
        1. Build BaseOrders (joins + filters).
        2. Add window-function rankings (RankedOrders).
        3. Derive final staging columns and cache (#SalesStaging).
        4. Aggregate daily summary (#DailySummary).

    Args:
        spark: Active SparkSession.
        params: Procedure parameters (start_date, end_date, min_order_amount).

    Returns:
        Tuple of (sales_staging_df, daily_summary_df).
    """
    # TODO: OBJECT_ID temp-table checks skipped (DataFrame GC handles cleanup)
    base_orders = _step1_base_orders(spark, params)
    ranked_orders = _step2_ranked_orders(base_orders)
    sales_staging = _step3_sales_staging(ranked_orders)
    daily_summary = _step4_daily_summary(sales_staging)
    return sales_staging, daily_summary


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Parse arguments and run the sales-staging pipeline."""
    parser = argparse.ArgumentParser(
        description="Stage sales data and produce daily summaries (PySpark)."
    )
    parser.add_argument(
        "--start-date",
        required=True,
        type=date.fromisoformat,
        help="Inclusive start date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        type=date.fromisoformat,
        help="Inclusive end date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--min-order-amount",
        type=Decimal,
        default=Decimal("0.00"),
        help="Minimum line total to include (default: 0.00).",
    )
    args = parser.parse_args()

    params = StageSalesDataParams(
        start_date=args.start_date,
        end_date=args.end_date,
        min_order_amount=args.min_order_amount,
    )

    spark = (
        SparkSession.builder
        .appName("usp_StageSalesData")
        .getOrCreate()
    )

    sales_staging_df, daily_summary_df = run_pipeline(spark, params)

    print(f"Sales Staging rows: {sales_staging_df.count()}")
    print(f"Daily Summary rows: {daily_summary_df.count()}")

    sales_staging_df.show(20, truncate=False)
    daily_summary_df.show(20, truncate=False)

    spark.stop()


if __name__ == "__main__":
    main()
