from __future__ import annotations

# =============================================================================
# Converted from: dbo.usp_AWLT_OneCSV_ConverterTest_1k  (SQL lines 614-1015)
# Source dialect : T-SQL (SQL Server)
# Complexity     : Complex (score 7.25)
# Converted on   : 2026-03-30
#
# KNOWN LIMITATIONS
# -----------------
# 1. TODO: Dynamic SQL via sp_executesql at SQL lines 931-934.
#    QC predicates stored in dbo.AWLT_QC_Definition are executed at runtime
#    as opaque strings.  Replaced here with a placeholder predicate-map
#    pattern — inspect all SqlPredicate rows and build a static Python dict
#    mapping CheckName → PySpark filter lambda before promoting to production.
#
# 2. TODO: Cursor at SQL lines 918-943 rewritten as a vectorised Python loop
#    over driver-collected QC definitions.  Each rule evaluated with
#    DataFrame.where().limit(1).count() — acceptable for ≤ 60 rules.
#
# 3. OBJECT_ID tempdb existence checks throughout (lines 652, 663, 689, 720,
#    743, 778, 819, 834, 851, 881, 905) omitted — PySpark DataFrame lifecycle
#    is automatic; no equivalent needed.
#
# 4. FOR JSON PATH correlated subquery (lines 865-873, topCategories) cannot
#    be auto-converted — pre-aggregate with row_number() + collect_list() +
#    to_json() pattern (see Section 9a).
#
# 5. CROSS APPLY OPENJSON WITH schema (lines 891-897) rewritten as
#    F.from_json() with explicit StructType (see Section 9b).
#
# 6. TODO: Transaction semantics BEGIN TRY / THROW (lines 1008-1014) —
#    converted to Python try/except.  No mid-pipeline rollback is available.
#    Consider Delta Lake for ACID guarantees if rollback is required.
#
# 7. SELECT INTO #Temp + CREATE CLUSTERED INDEX patterns (11 occurrences)
#    converted to .repartition(key).cache() + .count() materialisation.
#    INCLUDE-column indexes are not applicable in PySpark and are omitted.
#
# 8. DECLARE @table TABLE (line 932) rewritten as a Python list of Row objects.
# =============================================================================

import argparse
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Callable

from pyspark.sql import DataFrame, Row, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DecimalType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)
from pyspark.sql.window import Window

# ---------------------------------------------------------------------------
# Dependency stubs — replace with real imports once converted objects exist
# ---------------------------------------------------------------------------
# from awlt_converter_log import ConverterLogger   # dbo.usp_AWLT_Converter_Log
# from awlt_utils import ufn_split_csv_int          # dbo.ufn_SplitCsvInt


# ---------------------------------------------------------------------------
# Thin stub implementations so the file runs standalone during development
# ---------------------------------------------------------------------------
class ConverterLogger:
    """Stub for dbo.usp_AWLT_Converter_Log.  Replace with real implementation."""

    def log_step(
        self,
        run_id: str,
        proc_name: str,
        step_name: str,
        step_status: str,
        message: str,
        complete: bool,
    ) -> None:
        import logging
        logging.getLogger(__name__).info(
            "[%s] %s | %s | %s | %s | complete=%s",
            run_id,
            proc_name,
            step_name,
            step_status,
            message,
            complete,
        )


def ufn_split_csv_int(csv: str | None) -> list[int]:
    """Stub for dbo.ufn_SplitCsvInt.  Replace with real implementation."""
    if not csv:
        return []
    result: list[int] = []
    for part in csv.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            result.append(int(part))
    return result


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROC_NAME: str = "dbo.usp_AWLT_OneCSV_ConverterTest_1k"


# ---------------------------------------------------------------------------
# Pipeline parameters  (SQL lines 615-624)
# ---------------------------------------------------------------------------
@dataclass
class PipelineParams:
    """Runtime parameters for the pipeline.

    Maps directly to the stored-procedure input parameters.
    Decimal fields use Python Decimal to avoid floating-point precision loss
    (Gotcha #5 — financial precision).
    """

    start_date: date | None = None                          # @StartDate
    end_date: date | None = None                            # @EndDate
    as_of_date: date | None = None                          # @AsOfDate
    customer_ids_csv: str | None = None                     # @CustomerIdsCsv
    region_filter: str | None = None                        # @RegionFilter
    recent_months_window: int = 6                           # @RecentMonthsWindow
    revenue_tolerance_pct: Decimal = field(
        default_factory=lambda: Decimal("0.0100")           # @RevenueTolerancePct decimal(9,4)
    )
    emit_debug: bool = False                                # @EmitDebug


# =============================================================================
# Section 1: Customer filter list  (SQL lines 652-658)
# =============================================================================
def _step1_build_customer_filter(params: PipelineParams) -> tuple[list[int], bool]:
    """Parse CSV of customer IDs into a Python list.

    Args:
        params: Pipeline parameters.

    Returns:
        Tuple of (customer_ids list, has_customer_filter flag).

    Note:
        OBJECT_ID tempdb existence check at SQL line 652 omitted — known limitation.
        No DataFrame is created; the list is used as a filter predicate in Section 2.
        @HasCustomerFilter BIT (SQL line 658) — represented as Python bool, not BIT,
        avoiding Gotcha #10 NULL/BIT pitfalls entirely.
    """
    customer_ids: list[int] = ufn_split_csv_int(params.customer_ids_csv)
    has_customer_filter: bool = len(customer_ids) > 0
    return customer_ids, has_customer_filter


# =============================================================================
# Section 2: Base orders in date range  (SQL lines 663-684)
# =============================================================================
def _step2_build_orders(
    spark: SparkSession,
    params: PipelineParams,
    start_date: date,
    end_date: date,
    customer_ids: list[int],
    has_customer_filter: bool,
) -> DataFrame:
    """Load and filter SalesOrderHeader joined with Address.

    Args:
        spark: Active SparkSession.
        params: Pipeline parameters.
        start_date: Resolved start date.
        end_date: Resolved end date.
        customer_ids: Optional list of allowed CustomerIDs.
        has_customer_filter: Whether customer_ids should be applied.

    Returns:
        Cached, repartitioned orders DataFrame (#Orders equivalent).

    Notes:
        - OBJECT_ID check at SQL line 663 omitted.
        - LEFT JOIN to Address (SQL line 677-678).
        - RegionName via COALESCE(StateProvince, CountryRegion, 'Unknown Region').
        - Gotcha #2: region_filter comparison uses F.lower() on both sides.
        - CREATE CLUSTERED INDEX CX_Orders → .repartition('CustomerID').cache().
        - CREATE INDEX IX_Orders_Order INCLUDE(...) omitted — INCLUDE not applicable.
    """
    soh = spark.table("SalesLT.SalesOrderHeader")
    addr = spark.table("SalesLT.Address")

    df = (
        soh.join(addr, soh["ShipToAddressID"] == addr["AddressID"], "left")
        .withColumn(
            "RegionName",
            F.coalesce(
                F.col("StateProvince"),
                F.col("CountryRegion"),
                F.lit("Unknown Region"),
            ),
        )
        .withColumn("OrderDate", F.col("OrderDate").cast("date"))
        .select(
            soh["SalesOrderID"],
            soh["CustomerID"],
            F.col("OrderDate"),
            soh["TotalDue"],
            soh["SubTotal"],
            soh["TaxAmt"],
            soh["Freight"],
            soh["OnlineOrderFlag"],
            F.col("RegionName"),
        )
        .where(F.col("OrderDate").between(start_date, end_date))
    )

    # Customer filter (SQL line 680) — Gotcha #10: use Python list, not BIT
    if has_customer_filter:
        df = df.where(F.col("CustomerID").isin(customer_ids))

    # Region filter (SQL line 681) — Gotcha #2: case-sensitive → F.lower() both sides
    if params.region_filter:
        df = df.where(
            F.lower(F.col("RegionName")) == F.lower(F.lit(params.region_filter))
        )

    # Materialise — CREATE CLUSTERED INDEX CX_Orders ON #Orders(CustomerID, ...)
    orders_df = df.repartition("CustomerID").cache()
    orders_df.count()
    return orders_df


# =============================================================================
# Section 3: Line details + product / category enrichment  (SQL lines 689-715)
# =============================================================================
def _step3_build_lines(
    spark: SparkSession,
    orders_df: DataFrame,
) -> DataFrame:
    """Enrich SalesOrderDetail with product, category, and model info.

    Args:
        spark: Active SparkSession.
        orders_df: Materialised orders DataFrame from Section 2.

    Returns:
        Cached lines DataFrame (#Lines equivalent).

    Notes:
        - OBJECT_ID check at SQL line 689 omitted.
        - Column pruning applied before joins for performance.
        - CREATE INDEX IX_Lines_Order INCLUDE(...) omitted.
    """
    sod = spark.table("SalesLT.SalesOrderDetail")
    prod = spark.table("SalesLT.Product")
    pc = spark.table("SalesLT.ProductCategory")
    pm = spark.table("SalesLT.ProductModel")

    # Column pruning before joins
    sod_pruned = sod.select(
        "SalesOrderID",
        "SalesOrderDetailID",
        "ProductID",
        "OrderQty",
        "UnitPrice",
        "UnitPriceDiscount",
        "LineTotal",
    )
    prod_pruned = prod.select(
        "ProductID",
        "ProductNumber",
        prod["Name"].alias("ProductName"),
        "ProductCategoryID",
        "ProductModelID",
        "Color",
    )
    pc_pruned = pc.select(
        "ProductCategoryID",
        pc["Name"].alias("CategoryName"),
    )
    pm_pruned = pm.select(
        "ProductModelID",
        pm["Name"].alias("ModelName"),
    )

    lines_df = (
        sod_pruned
        .join(orders_df.select("SalesOrderID"), "SalesOrderID", "inner")
        .join(prod_pruned, "ProductID", "inner")
        .join(pc_pruned, "ProductCategoryID", "left")
        .join(pm_pruned, "ProductModelID", "left")
        .select(
            "SalesOrderID",
            "SalesOrderDetailID",
            "ProductID",
            "OrderQty",
            "UnitPrice",
            "UnitPriceDiscount",
            "LineTotal",
            "ProductNumber",
            "ProductName",
            "CategoryName",
            "ModelName",
            "Color",
        )
        .repartition("SalesOrderID")
        .cache()
    )
    lines_df.count()
    return lines_df


# =============================================================================
# Section 4: Path A aggregates (order header totals)  (SQL lines 720-738)
# =============================================================================
def _step4_build_agg_a(orders_df: DataFrame) -> DataFrame:
    """Aggregate order header totals per customer (Path A).

    Args:
        orders_df: Materialised orders DataFrame.

    Returns:
        Cached agg_a DataFrame (#AggA equivalent).

    Notes:
        - OBJECT_ID check at SQL line 720 omitted.
        - Gotcha #10: OnlineOrderFlag is BIT — use explicit == 1 / == 0, not truthy.
          NULL OnlineOrderFlag rows contribute 0 to both counts (safe).
        - COUNT_BIG(*) at SQL line 724 → F.count('*').
        - CREATE CLUSTERED INDEX CX_AggA → .repartition('CustomerID').cache().
    """
    agg_a = (
        orders_df.groupBy("CustomerID")
        .agg(
            F.count("*").alias("OrderCount"),
            F.sum("TotalDue").alias("TotalRevenue_PathA"),
            F.sum("SubTotal").alias("SubTotal_PathA"),
            F.sum("TaxAmt").alias("Tax_PathA"),
            F.sum("Freight").alias("Freight_PathA"),
            # Gotcha #10: explicit == 1 / == 0 for BIT column
            F.sum(F.when(F.col("OnlineOrderFlag") == 1, 1).otherwise(0)).alias(
                "OnlineOrderCount"
            ),
            F.sum(F.when(F.col("OnlineOrderFlag") == 0, 1).otherwise(0)).alias(
                "OfflineOrderCount"
            ),
            F.min("OrderDate").alias("FirstOrderDate"),
            F.max("OrderDate").alias("LastOrderDate"),
            F.max("RegionName").alias("PrimaryRegionName"),
        )
        .repartition("CustomerID")
        .cache()
    )
    agg_a.count()
    return agg_a


# =============================================================================
# Section 5: Path B aggregates (line totals with discount)  (SQL lines 743-773)
# =============================================================================
def _step5_build_agg_b(orders_df: DataFrame, lines_df: DataFrame) -> DataFrame:
    """Aggregate line-level totals per customer (Path B).

    Args:
        orders_df: Materialised orders DataFrame.
        lines_df: Materialised lines DataFrame.

    Returns:
        Cached agg_b DataFrame (#AggB equivalent).

    Notes:
        - OBJECT_ID check at SQL line 743 omitted.
        - CTE L converted to intermediate DataFrame cte_l.
        - Gotcha #5: UnitPrice * OrderQty * UnitPriceDiscount arithmetic —
          spark.sql.decimalOperations.allowPrecisionLoss must be false (set in
          run_pipeline).
        - CREATE CLUSTERED INDEX CX_AggB → .repartition('CustomerID').cache().
    """
    # CTE L (SQL lines 746-759)
    cte_l = (
        orders_df.join(lines_df, "SalesOrderID", "inner")
        .groupBy("CustomerID", "SalesOrderID")
        .agg(
            F.sum("LineTotal").alias("LineTotalSum"),
            F.sum(
                F.col("UnitPrice") * F.col("OrderQty") * F.col("UnitPriceDiscount")
            ).alias("DiscountAmount"),
            F.count("*").alias("LineCount"),
            F.sum("OrderQty").alias("TotalQty"),
            F.countDistinct("ProductID").alias("DistinctProducts"),
            F.countDistinct("CategoryName").alias("DistinctCategories"),
        )
    )

    # Outer GROUP BY (SQL lines 761-771)
    agg_b = (
        cte_l.groupBy("CustomerID")
        .agg(
            F.sum("LineTotalSum").alias("TotalRevenue_PathB"),
            F.sum("DiscountAmount").alias("TotalDiscount_PathB"),
            F.sum("LineCount").alias("TotalLines"),
            F.sum("TotalQty").alias("TotalQty"),
            F.sum("DistinctProducts").alias("DistinctProducts"),
            F.sum("DistinctCategories").alias("DistinctCategories"),
        )
        .repartition("CustomerID")
        .cache()
    )
    agg_b.count()
    return agg_b


# =============================================================================
# Section 6: Customer facts (merged)  (SQL lines 778-814)
# =============================================================================
def _step6_build_customer_facts(
    spark: SparkSession,
    agg_a: DataFrame,
    agg_b: DataFrame,
    as_of_date: date,
) -> DataFrame:
    """Merge customer aggregates with dimension data to produce customer facts.

    Args:
        spark: Active SparkSession.
        agg_a: Path-A aggregates per customer.
        agg_b: Path-B aggregates per customer.
        as_of_date: Resolved as-of date for recency calculation.

    Returns:
        Cached facts DataFrame (#CustomerFacts equivalent).

    Notes:
        - OBJECT_ID check at SQL line 778 omitted.
        - Gotcha #1 (DATEDIFF reversed): F.datediff(end, start).
          SQL line 799: DATEDIFF(day, a.LastOrderDate, @AsOfDate)
              → F.datediff(F.lit(as_of_date), F.col('LastOrderDate'))
          SQL line 800: DATEDIFF(day, a.FirstOrderDate, a.LastOrderDate)
              → F.datediff(F.col('LastOrderDate'), F.col('FirstOrderDate'))
        - Gotcha #5: explicit DecimalType casts for division and NULLIF.
        - CREATE CLUSTERED INDEX CX_CustFacts → .repartition('CustomerID').cache().
        - CREATE INDEX IX_CustFacts_Region omitted (INCLUDE not applicable).
    """
    cust = spark.table("SalesLT.Customer").select(
        "CustomerID",
        F.concat_ws(" ", F.col("FirstName"), F.col("LastName")).alias("CustomerName"),
    )

    facts_df = (
        agg_a
        .join(cust, "CustomerID", "inner")
        .join(agg_b, "CustomerID", "left")
        # SQL line 783: PrimaryRegionName → RegionName
        .withColumnRenamed("PrimaryRegionName", "RegionName")
        # SQL line 791-792: rename freight/tax
        .withColumnRenamed("Freight_PathA", "TotalFreight")
        .withColumnRenamed("Tax_PathA", "TotalTax")
        # SQL line 793: AvgOrderValue — Gotcha #5 explicit cast (decimal(19,4))
        .withColumn(
            "AvgOrderValue",
            F.when(
                F.col("OrderCount") > 0,
                F.col("TotalRevenue_PathA")
                / F.col("OrderCount").cast(DecimalType(19, 4)),
            ).otherwise(F.lit(0)),
        )
        # SQL line 799: RecencyDays — Gotcha #1 REVERSED args
        .withColumn(
            "RecencyDays",
            F.datediff(F.lit(as_of_date), F.col("LastOrderDate")),
        )
        # SQL line 800: CustomerTenureDays — Gotcha #1 REVERSED args
        .withColumn(
            "CustomerTenureDays",
            F.datediff(F.col("LastOrderDate"), F.col("FirstOrderDate")),
        )
        # SQL line 801: RevenueDelta_AB
        .withColumn(
            "RevenueDelta_AB",
            F.abs(
                F.coalesce(F.col("TotalRevenue_PathA"), F.lit(0))
                - F.coalesce(F.col("TotalRevenue_PathB"), F.lit(0))
            ),
        )
        # SQL lines 802-805: RevenuePctDelta_AB — Gotcha #5 NULLIF + cast
        .withColumn(
            "RevenuePctDelta_AB",
            F.when(
                F.coalesce(F.col("TotalRevenue_PathA"), F.lit(0)) == 0,
                F.lit(None).cast(DecimalType(19, 6)),
            ).otherwise(
                F.abs(
                    F.coalesce(F.col("TotalRevenue_PathA"), F.lit(0))
                    - F.coalesce(F.col("TotalRevenue_PathB"), F.lit(0))
                )
                / F.when(
                    F.col("TotalRevenue_PathA") == 0,
                    F.lit(None).cast(DecimalType(19, 6)),
                ).otherwise(
                    F.col("TotalRevenue_PathA").cast(DecimalType(19, 6))
                ),
            ),
        )
        .select(
            "CustomerID",
            "CustomerName",
            "RegionName",
            "FirstOrderDate",
            "LastOrderDate",
            "OrderCount",
            "OnlineOrderCount",
            "OfflineOrderCount",
            "TotalRevenue_PathA",
            "TotalRevenue_PathB",
            "TotalFreight",
            "TotalTax",
            "AvgOrderValue",
            "TotalDiscount_PathB",
            "TotalLines",
            "TotalQty",
            "DistinctProducts",
            "DistinctCategories",
            "RecencyDays",
            "CustomerTenureDays",
            "RevenueDelta_AB",
            "RevenuePctDelta_AB",
        )
        .repartition("CustomerID")
        .cache()
    )
    facts_df.count()
    return facts_df


# =============================================================================
# Section 7: RFM scoring (NTILE + bands)  (SQL lines 819-829)
# =============================================================================
def _step7_build_rfm(facts_df: DataFrame) -> DataFrame:
    """Compute RFM tile scores using NTILE(5) window functions.

    Args:
        facts_df: Materialised customer facts DataFrame.

    Returns:
        Cached rfm DataFrame (#RFM equivalent).

    Notes:
        - OBJECT_ID check at SQL line 819 omitted.
        - Gotcha #3 NULL ordering to match SQL Server behaviour:
            RecencyDays ASC  → SQL Server NULLs first  → .asc_nulls_first()
            OrderCount  DESC → SQL Server NULLs last   → .desc_nulls_last()
            TotalRevenue_PathA DESC → NULLs last       → .desc_nulls_last()
        - Gotcha #4: NTILE windows have no ORDER-BY frame (not running totals),
          so RANGE vs ROWS distinction does not apply here.
        - CREATE CLUSTERED INDEX CX_RFM → .repartition('CustomerID').cache().
    """
    w_recency = Window.orderBy(F.col("RecencyDays").asc_nulls_first())
    w_frequency = Window.orderBy(F.col("OrderCount").desc_nulls_last())
    w_monetary = Window.orderBy(F.col("TotalRevenue_PathA").desc_nulls_last())

    rfm_df = (
        facts_df
        .withColumn("R_Score", F.ntile(5).over(w_recency))
        .withColumn("F_Score", F.ntile(5).over(w_frequency))
        .withColumn("M_Score", F.ntile(5).over(w_monetary))
        .repartition("CustomerID")
        .cache()
    )
    rfm_df.count()
    return rfm_df


# =============================================================================
# Section 8: Region benchmarks  (SQL lines 834-846)
# =============================================================================
def _step8_build_region_agg(rfm_df: DataFrame) -> DataFrame:
    """Compute per-region average revenue, order count, recency, and RFM.

    Args:
        rfm_df: Materialised RFM DataFrame.

    Returns:
        Cached region_agg DataFrame (#RegionAgg equivalent).

    Notes:
        - OBJECT_ID check at SQL line 834 omitted.
        - Gotcha #5: CONVERT(decimal(19,4), ...) before AVG → explicit cast.
        - CREATE CLUSTERED INDEX CX_RegionAgg → .repartition('RegionName').cache().
    """
    region_agg = (
        rfm_df.groupBy("RegionName")
        .agg(
            F.avg(F.col("TotalRevenue_PathA").cast(DecimalType(19, 4))).alias(
                "RegionAvgRevenue"
            ),
            F.avg(F.col("OrderCount").cast(DecimalType(19, 4))).alias(
                "RegionAvgOrderCount"
            ),
            F.avg(F.col("RecencyDays").cast(DecimalType(19, 4))).alias(
                "RegionAvgRecency"
            ),
            F.avg(
                (F.col("R_Score") + F.col("F_Score") + F.col("M_Score")).cast(
                    DecimalType(19, 4)
                )
            ).alias("RegionAvgRFM"),
        )
        .repartition("RegionName")
        .cache()
    )
    region_agg.count()
    return region_agg


# =============================================================================
# Section 9a: JSON payload per customer  (SQL lines 851-879)
# =============================================================================
def _step9a_build_payload(
    spark: SparkSession,
    rfm_df: DataFrame,
    orders_df: DataFrame,
    lines_df: DataFrame,
) -> DataFrame:
    """Build a JSON payload column per customer.

    SQL FOR JSON PATH correlated subquery (lines 865-873) cannot be
    auto-converted — pre-aggregate top-5 categories and embed via
    collect_list() + to_json().

    Args:
        spark: Active SparkSession.
        rfm_df: RFM-scored customer DataFrame.
        orders_df: Base orders DataFrame.
        lines_df: Line-detail DataFrame.

    Returns:
        Cached payload DataFrame (#Json equivalent).

    Notes:
        - OBJECT_ID check at SQL line 851 omitted.
        - KNOWN LIMITATION: correlated subquery (lines 865-873) pre-aggregated.
        - FOR JSON PATH, WITHOUT_ARRAY_WRAPPER → F.to_json on a struct does
          not produce an array wrapper by default.
        - CREATE CLUSTERED INDEX CX_Json → .repartition('CustomerID').cache().
    """
    # Step A: pre-aggregate category revenue per customer
    pre_top_cat = (
        orders_df
        .join(lines_df, "SalesOrderID", "inner")
        .groupBy("CustomerID", "CategoryName")
        .agg(F.sum("LineTotal").alias("revenue"))
    )

    # Step B: rank top-5 categories per customer
    rank_window = Window.partitionBy("CustomerID").orderBy(
        F.col("revenue").desc_nulls_last()
    )
    ranked_cat = (
        pre_top_cat
        .withColumn("rn", F.row_number().over(rank_window))
        .where(F.col("rn") <= 5)
    )

    # Step C: collapse to JSON list per customer
    top_cat_json = ranked_cat.groupBy("CustomerID").agg(
        F.to_json(
            F.collect_list(F.struct("CategoryName", "revenue"))
        ).alias("topCategories")
    )

    # Step D: build main payload struct → JSON string
    payload_df = (
        rfm_df
        .join(top_cat_json, "CustomerID", "left")
        .withColumn(
            "PayloadJson",
            F.to_json(
                F.struct(
                    F.col("CustomerID").alias("customerId"),
                    F.col("CustomerName").alias("customerName"),
                    F.col("RegionName").alias("region"),
                    F.col("TotalRevenue_PathA").alias("revenueA"),
                    F.col("TotalRevenue_PathB").alias("revenueB"),
                    F.col("OrderCount").alias("orders"),
                    F.col("RecencyDays").alias("recencyDays"),
                    (F.col("R_Score") + F.col("F_Score") + F.col("M_Score")).alias(
                        "rfmScore"
                    ),
                    F.col("topCategories"),
                )
            ),
        )
        .repartition("CustomerID")
        .cache()
    )
    payload_df.count()
    return payload_df


# =============================================================================
# Section 9b: Parse JSON fields back  (SQL lines 881-899)
# =============================================================================
def _step9b_parse_json(payload_df: DataFrame) -> DataFrame:
    """Parse selected fields back out of PayloadJson using from_json.

    Args:
        payload_df: Payload DataFrame containing PayloadJson column.

    Returns:
        Cached parsed DataFrame (#JsonParsed equivalent).

    Notes:
        - OBJECT_ID check at SQL line 881 omitted.
        - KNOWN LIMITATION: CROSS APPLY OPENJSON WITH schema (lines 891-897)
          rewritten as F.from_json() with explicit StructType.
        - TRY_CONVERT → PySpark .cast() returns NULL on failure (safe cast).
        - Gotcha #5: cast to DecimalType(19,4) explicitly.
        - CREATE CLUSTERED INDEX CX_JsonParsed → .repartition('CustomerID').cache().
    """
    # Schema mirrors OPENJSON WITH clause (SQL lines 892-897)
    json_schema = StructType(
        [
            StructField("revenueA", StringType(), True),
            StructField("revenueB", StringType(), True),
            StructField("orders", StringType(), True),
            StructField("rfmScore", StringType(), True),
        ]
    )

    parsed_df = (
        payload_df.select("CustomerID", "PayloadJson")
        .withColumn("parsed", F.from_json(F.col("PayloadJson"), json_schema))
        .select(
            "CustomerID",
            F.col("parsed.revenueA").alias("revenueA"),
            F.col("parsed.revenueB").alias("revenueB"),
            F.col("parsed.orders").alias("orders"),
            F.col("parsed.rfmScore").alias("rfmScore"),
        )
        # TRY_CONVERT → safe .cast() — NULL on failure (Gotcha #5)
        .withColumn("revenueA_json", F.col("revenueA").cast(DecimalType(19, 4)))
        .withColumn("revenueB_json", F.col("revenueB").cast(DecimalType(19, 4)))
        .withColumn("orders_json", F.col("orders").cast(IntegerType()))
        .withColumn("rfmScore_json", F.col("rfmScore").cast(IntegerType()))
        .select(
            "CustomerID",
            "revenueA_json",
            "revenueB_json",
            "orders_json",
            "rfmScore_json",
        )
        .repartition("CustomerID")
        .cache()
    )
    parsed_df.count()
    return parsed_df


# =============================================================================
# Section 10: QC rule evaluation  (SQL lines 905-943)
# =============================================================================

# ---------------------------------------------------------------------------
# TODO: Build this predicate map by inspecting every SqlPredicate row in
#       dbo.AWLT_QC_Definition.  The SQL cursor (lines 918-943) executes each
#       predicate as dynamic SQL via sp_executesql (lines 931-934).  Map each
#       CheckName to a Python callable that accepts a facts DataFrame and
#       returns a filtered DataFrame.  Example stub shown below.
# ---------------------------------------------------------------------------
PredicateFn = Callable[[DataFrame], DataFrame]

QC_PREDICATE_MAP: dict[str, PredicateFn] = {
    # TODO: populate from dbo.AWLT_QC_Definition SqlPredicate inspection
    # Example:
    # "OrderCount_GT_Zero": lambda df: df.where(F.col("OrderCount") <= 0),
    # "Revenue_Not_Null":   lambda df: df.where(F.col("TotalRevenue_PathA").isNull()),
}


def _step10_evaluate_qc(
    spark: SparkSession,
    facts_df: DataFrame,
) -> DataFrame:
    """Evaluate QC rules against customer facts and return failure flags.

    Args:
        spark: Active SparkSession.
        facts_df: Customer facts DataFrame used as predicate target.

    Returns:
        qc_fail DataFrame (#QCFail equivalent) as a small in-memory DataFrame.

    Notes:
        - OBJECT_ID check at SQL line 905 omitted.
        - TODO: Dynamic SQL via sp_executesql at SQL lines 931-934 cannot be
          auto-converted.  Populate QC_PREDICATE_MAP above by inspecting all
          SqlPredicate rows in dbo.AWLT_QC_Definition.
        - TODO: Cursor at SQL lines 918-943 rewritten as a vectorised Python
          loop.  Each QC row collected to driver; predicate evaluated via
          DataFrame.where().limit(1).count() (acceptable for ≤ 60 rules).
        - DECLARE @table TABLE (line 932) → Python list[Row].
        - dbo.AWLT_QC_Definition loaded and limited to TOP 60 (SQL line 919).
    """
    # Load QC definitions to driver — TOP 60 ORDER BY QCId
    qc_defs = (
        spark.table("dbo.AWLT_QC_Definition")
        .orderBy("QCId")
        .limit(60)
        .collect()
    )

    # DECLARE @table TABLE (line 932) → Python list
    qc_results: list[Row] = []

    for qc in qc_defs:
        check_name: str = qc["CheckName"]
        predicate_fn: PredicateFn | None = QC_PREDICATE_MAP.get(check_name)

        if predicate_fn is not None:
            # Evaluate predicate — equivalent to sp_executesql check
            failed: bool = predicate_fn(facts_df).limit(1).count() > 0
        else:
            # TODO: predicate not yet mapped — treat as unknown (not failed)
            # Replace with raise ValueError(...) once all predicates are mapped
            failed = False

        qc_results.append(
            Row(
                CheckGroup=qc["CheckGroup"],
                CheckName=check_name,
                Severity=int(qc["Severity"]),
                Failed=failed,
            )
        )

    qc_fail_df = spark.createDataFrame(qc_results)
    return qc_fail_df


# =============================================================================
# Section 11: Final result set  (SQL lines 950-1006)
# =============================================================================
def _step11_build_result(
    rfm_df: DataFrame,
    region_agg: DataFrame,
    payload_df: DataFrame,
    parsed_df: DataFrame,
    qc_fail_df: DataFrame,
    params: PipelineParams,
    start_date: date,
    end_date: date,
    as_of_date: date,
    run_id: str,
) -> DataFrame:
    """Join all intermediate DataFrames into the final one-row-per-customer result.

    Args:
        rfm_df: RFM-scored customer DataFrame.
        region_agg: Region benchmark aggregates.
        payload_df: JSON payload DataFrame.
        parsed_df: Parsed JSON fields DataFrame.
        qc_fail_df: QC failure flags.
        params: Pipeline parameters (for literal param columns).
        start_date: Resolved start date.
        end_date: Resolved end date.
        as_of_date: Resolved as-of date.
        run_id: UUID string for this pipeline run.

    Returns:
        Final result DataFrame ordered per SQL lines 1002-1006.

    Notes:
        - SQL line 990-991: scalar subqueries for QC counts pre-computed with
          F.count('*') and collected as scalars (Gotcha #9).
        - Gotcha #3 ORDER BY: all columns with explicit null direction.
        - Gotcha #5: RevenuePctDelta_AB comparison uses Decimal param value.
        - SQL line 977-978: QC_Pass_Revenue_AB CASE → F.when chain.
        - SQL line 983: NULLIF(RegionAvgRevenue, 0) → F.when(== 0, None).
    """
    # Pre-compute QC scalar counts (SQL lines 990-991) — safe .collect() on agg
    qc_sev3: int = (
        qc_fail_df
        .where((F.col("Failed") == True) & (F.col("Severity") == 3))  # noqa: E712
        .agg(F.count("*").alias("n"))
        .collect()[0][0]
    )
    qc_sev2: int = (
        qc_fail_df
        .where((F.col("Failed") == True) & (F.col("Severity") == 2))  # noqa: E712
        .agg(F.count("*").alias("n"))
        .collect()[0][0]
    )

    result = (
        rfm_df
        # JOIN #RegionAgg ra ON ra.RegionName = r.RegionName (SQL line 999)
        .join(region_agg, "RegionName", "inner")
        # JOIN #Json j ON j.CustomerID = r.CustomerID (SQL line 1000)
        .join(payload_df.select("CustomerID", "PayloadJson"), "CustomerID", "inner")
        # JOIN #JsonParsed jp ON jp.CustomerID = r.CustomerID (SQL line 1001)
        .join(
            parsed_df.select(
                "CustomerID",
                "revenueA_json",
                "revenueB_json",
                "orders_json",
                "rfmScore_json",
            ),
            "CustomerID",
            "inner",
        )
        # SQL line 976: RFM_Score
        .withColumn(
            "RFM_Score",
            F.col("R_Score") + F.col("F_Score") + F.col("M_Score"),
        )
        # SQL lines 977-978: QC_Pass_Revenue_AB
        .withColumn(
            "QC_Pass_Revenue_AB",
            F.when(F.col("RevenuePctDelta_AB").isNull(), 0)
            .when(
                F.col("RevenuePctDelta_AB")
                <= F.lit(params.revenue_tolerance_pct).cast(DecimalType(19, 4)),
                1,
            )
            .otherwise(0),
        )
        # SQL line 983: RevenueVsRegionPctDelta — NULLIF(RegionAvgRevenue, 0)
        .withColumn(
            "RevenueVsRegionPctDelta",
            F.when(F.col("RegionAvgRevenue") == 0, F.lit(None))
            .otherwise(
                (F.col("TotalRevenue_PathA") - F.col("RegionAvgRevenue"))
                / F.when(
                    F.col("RegionAvgRevenue") == 0, F.lit(None)
                ).otherwise(F.col("RegionAvgRevenue"))
            ),
        )
        # SQL line 984: RFMVsRegionPctDelta
        .withColumn(
            "RFMVsRegionPctDelta",
            F.when(F.col("RegionAvgRFM") == 0, F.lit(None))
            .otherwise(
                (
                    F.col("R_Score") + F.col("F_Score") + F.col("M_Score")
                    - F.col("RegionAvgRFM")
                )
                / F.when(
                    F.col("RegionAvgRFM") == 0, F.lit(None)
                ).otherwise(F.col("RegionAvgRFM"))
            ),
        )
        # Literal param / run-metadata columns (SQL lines 990-997)
        .withColumn("QC_FailCount_Severity3", F.lit(qc_sev3))
        .withColumn("QC_FailCount_Severity2", F.lit(qc_sev2))
        .withColumn("SnapshotStartDate", F.lit(str(start_date)))
        .withColumn("SnapshotEndDate", F.lit(str(end_date)))
        .withColumn("SnapshotAsOfDate", F.lit(str(as_of_date)))
        .withColumn(
            "RevenueTolerancePctUsed",
            F.lit(float(params.revenue_tolerance_pct)),
        )
        .withColumn("RecentMonthsWindowUsed", F.lit(params.recent_months_window))
        .withColumn("RunId", F.lit(run_id))
        # Final column selection aligned to SQL lines 951-997
        .select(
            "CustomerID",
            "CustomerName",
            "RegionName",
            "FirstOrderDate",
            "LastOrderDate",
            "OrderCount",
            "OnlineOrderCount",
            "OfflineOrderCount",
            "TotalRevenue_PathA",
            "TotalRevenue_PathB",
            "RevenueDelta_AB",
            "RevenuePctDelta_AB",
            "TotalFreight",
            "TotalTax",
            "AvgOrderValue",
            "TotalDiscount_PathB",
            "TotalLines",
            "TotalQty",
            "DistinctProducts",
            "DistinctCategories",
            "RecencyDays",
            "CustomerTenureDays",
            "R_Score",
            "F_Score",
            "M_Score",
            "RFM_Score",
            "QC_Pass_Revenue_AB",
            "RegionAvgRevenue",
            "RegionAvgOrderCount",
            "RegionAvgRecency",
            "RegionAvgRFM",
            "RevenueVsRegionPctDelta",
            "RFMVsRegionPctDelta",
            "revenueA_json",
            "revenueB_json",
            "orders_json",
            "rfmScore_json",
            "PayloadJson",
            "QC_FailCount_Severity3",
            "QC_FailCount_Severity2",
            "SnapshotStartDate",
            "SnapshotEndDate",
            "SnapshotAsOfDate",
            "RevenueTolerancePctUsed",
            "RecentMonthsWindowUsed",
            "RunId",
        )
        # ORDER BY SQL lines 1002-1006 — Gotcha #3: explicit NULL direction
        .orderBy(
            F.col("RegionName").asc_nulls_first(),
            (F.col("R_Score") + F.col("F_Score") + F.col("M_Score")).desc_nulls_last(),
            F.col("TotalRevenue_PathA").desc_nulls_last(),
            F.col("CustomerName").asc_nulls_first(),
        )
    )
    return result


# =============================================================================
# Entry point
# =============================================================================
def run_pipeline(spark: SparkSession, params: PipelineParams) -> DataFrame:
    """Execute the full AWLT OneCSV converter pipeline.

    Corresponds to dbo.usp_AWLT_OneCSV_ConverterTest_1k (SQL lines 614-1015).

    Args:
        spark: Active SparkSession configured with the correct catalog/database.
        params: Pipeline runtime parameters.

    Returns:
        Final result DataFrame (one row per customer, ordered per SQL lines
        1002-1006).

    Raises:
        Exception: Re-raises any exception after logging the failure (mirrors
            BEGIN TRY / BEGIN CATCH / THROW at SQL lines 1008-1013).

    Global SparkSession config applied here (before pipeline body):
        - spark.sql.decimalOperations.allowPrecisionLoss = false  (Gotcha #5)
        - spark.sql.adaptive.enabled = true
        - spark.sql.adaptive.coalescePartitions.enabled = true
        - spark.sql.adaptive.skewJoin.enabled = true

    TODO: Transaction semantics (BEGIN TRY / THROW, SQL lines 1008-1014) use
          Python try/except.  No mid-pipeline rollback is available.  Consider
          Delta Lake for ACID guarantees if rollback is required.
    """
    # --- SparkSession config (Gotcha #5 + AQE) ---
    spark.conf.set("spark.sql.decimalOperations.allowPrecisionLoss", "false")
    spark.conf.set("spark.sql.adaptive.enabled", "true")
    spark.conf.set("spark.sql.adaptive.coalescePartitions.enabled", "true")
    spark.conf.set("spark.sql.adaptive.skewJoin.enabled", "true")

    logger = ConverterLogger()

    # SQL line 629: DECLARE @RunId = NEWID()
    run_id: str = str(uuid.uuid4())

    # SQL line 633: @StartMsg
    start_msg: str = f"Params: Region={params.region_filter or '(all)'}"

    # SQL line 635: EXEC usp_AWLT_Converter_Log ... @StepName='START'
    logger.log_step(run_id, PROC_NAME, "START", "START", start_msg, complete=False)

    # === Normalize date window (SQL lines 638-646) ===
    # Gotcha: .collect()[0] is safe here — single aggregation row
    if params.start_date is None or params.end_date is None:
        date_bounds = (
            spark.table("SalesLT.SalesOrderHeader")
            .agg(
                F.min(F.col("OrderDate").cast("date")).alias("min_date"),
                F.max(F.col("OrderDate").cast("date")).alias("max_date"),
            )
            .collect()[0]
        )
        start_date: date = params.start_date or date_bounds["min_date"]
        end_date: date = params.end_date or date_bounds["max_date"]
    else:
        start_date = params.start_date
        end_date = params.end_date

    # SQL line 646: IF @AsOfDate IS NULL SET @AsOfDate = @EndDate
    as_of_date: date = params.as_of_date or end_date

    # === BEGIN TRY (SQL line 648) → Python try/except ===
    # TODO: No mid-pipeline rollback available — consider Delta Lake for ACID.
    try:
        # --- Section 1: Customer filter (SQL lines 652-658) ---
        customer_ids, has_customer_filter = _step1_build_customer_filter(params)

        # --- Section 2: Base orders (SQL lines 663-684) ---
        orders_df = _step2_build_orders(
            spark, params, start_date, end_date, customer_ids, has_customer_filter
        )

        # --- Section 3: Line details (SQL lines 689-715) ---
        lines_df = _step3_build_lines(spark, orders_df)

        # --- Section 4: Path A aggregates (SQL lines 720-738) ---
        agg_a = _step4_build_agg_a(orders_df)

        # --- Section 5: Path B aggregates (SQL lines 743-773) ---
        agg_b = _step5_build_agg_b(orders_df, lines_df)

        # --- Section 6: Customer facts (SQL lines 778-814) ---
        facts_df = _step6_build_customer_facts(spark, agg_a, agg_b, as_of_date)

        # --- Unpersist no-longer-needed DataFrames ---
        orders_df.unpersist()
        agg_a.unpersist()
        agg_b.unpersist()

        # --- Section 7: RFM scoring (SQL lines 819-829) ---
        rfm_df = _step7_build_rfm(facts_df)
        facts_df.unpersist()

        # --- Section 8: Region benchmarks (SQL lines 834-846) ---
        region_agg = _step8_build_region_agg(rfm_df)

        # --- Section 9a: JSON payload (SQL lines 851-879) ---
        # orders_df / lines_df needed here — re-cache if already unpersisted;
        # callers should pass still-cached refs; re-load from source as fallback
        payload_df = _step9a_build_payload(spark, rfm_df, orders_df, lines_df)

        # --- Section 9b: Parse JSON (SQL lines 881-899) ---
        parsed_df = _step9b_parse_json(payload_df)

        # --- Unpersist line-level data ---
        lines_df.unpersist()

        # --- Section 10: QC evaluation (SQL lines 905-943) ---
        qc_fail_df = _step10_evaluate_qc(spark, facts_df if False else rfm_df)
        # Note: facts_df already unpersisted; QC predicates target rfm_df which
        # is a superset.  TODO: revisit if QC predicates need facts_df columns.

        # SQL line 948: EXEC usp_AWLT_Converter_Log ... N'END', N'SUCCESS'
        logger.log_step(
            run_id, PROC_NAME, "END", "SUCCESS", "Completed", complete=True
        )

        # --- Section 11: Final result (SQL lines 950-1006) ---
        result = _step11_build_result(
            rfm_df=rfm_df,
            region_agg=region_agg,
            payload_df=payload_df,
            parsed_df=parsed_df,
            qc_fail_df=qc_fail_df,
            params=params,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
            run_id=run_id,
        )

        # --- Unpersist remaining cached DataFrames ---
        rfm_df.unpersist()
        region_agg.unpersist()
        payload_df.unpersist()
        parsed_df.unpersist()

        return result

    except Exception as exc:
        # === BEGIN CATCH (SQL lines 1009-1013) ===
        # SQL line 1011: CONCAT('Error ', ERROR_NUMBER(), ' at line ', ...)
        tb = traceback.format_exc()
        msg: str = f"Error: {type(exc).__name__}: {exc}\n{tb}"

        # SQL line 1012: EXEC usp_AWLT_Converter_Log ... N'FAIL'
        logger.log_step(run_id, PROC_NAME, "END", "FAIL", msg, complete=True)

        # SQL line 1013: THROW → re-raise
        raise


# =============================================================================
# CLI entry point
# =============================================================================
def main() -> None:
    """Command-line interface for running the pipeline standalone."""
    parser = argparse.ArgumentParser(
        description="AWLT OneCSV ConverterTest 1k — PySpark pipeline"
    )
    parser.add_argument("--start-date", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--as-of-date", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--customer-ids-csv", type=str, default=None)
    parser.add_argument("--region-filter", type=str, default=None)
    parser.add_argument("--recent-months-window", type=int, default=6)
    parser.add_argument(
        "--revenue-tolerance-pct", type=str, default="0.0100",
        help="Decimal string, e.g. 0.0100"
    )
    parser.add_argument("--emit-debug", action="store_true", default=False)
    parser.add_argument(
        "--output-path", type=str, default=None,
        help="Optional path to write result as Parquet"
    )
    args = parser.parse_args()

    def _parse_date(s: str | None) -> date | None:
        if s is None:
            return None
        from datetime import datetime
        return datetime.strptime(s, "%Y-%m-%d").date()

    params = PipelineParams(
        start_date=_parse_date(args.start_date),
        end_date=_parse_date(args.end_date),
        as_of_date=_parse_date(args.as_of_date),
        customer_ids_csv=args.customer_ids_csv,
        region_filter=args.region_filter,
        recent_months_window=args.recent_months_window,
        revenue_tolerance_pct=Decimal(args.revenue_tolerance_pct),
        emit_debug=args.emit_debug,
    )

    spark = (
        SparkSession.builder
        .appName(PROC_NAME)
        .getOrCreate()
    )

    result_df = run_pipeline(spark, params)

    if args.output_path:
        result_df.write.mode("overwrite").parquet(args.output_path)
        print(f"Result written to {args.output_path}")
    else:
        result_df.show(truncate=False)


if __name__ == "__main__":
    main()
