from __future__ import annotations

# =============================================================================
# aw19_sales_commission_pricing_pipeline.py
#
# Converted from: dbo.usp_AW19_SalesCommissionPricingPipeline  (T-SQL)
# Source lines:   135-603
# Dialect:        tsql → PySpark 3.x
#
# TODO: Transaction semantics at lines 160/594 — consider Delta Lake for ACID
#       rollback if pipeline partial-write atomicity is required.
# =============================================================================

# --- stdlib -------------------------------------------------------------------
import argparse
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

# --- pyspark ------------------------------------------------------------------
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql import Window
from pyspark.sql.types import DecimalType, DoubleType, IntegerType


# =============================================================================
# Pipeline parameters  (SQL lines 135-143)
# =============================================================================

@dataclass
class PipelineParams:
    """Parameters mirroring the T-SQL procedure signature.

    Attributes:
        start_date: Filter orders on or after this date (NULL → MIN OrderDate).
        end_date: Filter orders on or before this date (NULL → MAX OrderDate).
        territory_group_filter: Optional territory group name to restrict scope.
        customer_ids_csv: Comma-separated integer customer IDs to restrict scope.
        min_order_amt: Minimum TotalDue for an order to be included.
        top_n_sales_person: How many top salespersons to return.
        emit_debug: Whether to emit verbose debug output.
    """
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    territory_group_filter: Optional[str] = None
    customer_ids_csv: Optional[str] = None
    min_order_amt: Decimal = Decimal("0")
    top_n_sales_person: int = 10
    emit_debug: bool = False


# =============================================================================
# Helpers
# =============================================================================

PROC_NAME = "usp_AW19_SalesCommissionPricingPipeline"


def ufn_split_csv_int(csv: Optional[str]) -> List[int]:
    """Mimic dbo.ufn_AW19_SplitCsvInt — parse comma-separated ints.

    Args:
        csv: Comma-separated integer string, e.g. '1,2,3' or None.

    Returns:
        List of parsed integers; empty list if csv is None/blank.
    """
    if not csv:
        return []
    return [int(x.strip()) for x in csv.split(",") if x.strip().lstrip("-").isdigit()]


class RunLogger:
    """Lightweight replacement for dbo.usp_AW19_Log (not yet converted).

    Logs pipeline step events to stdout and optionally to a Delta table when
    the table ``dbo.usp_AW19_Log`` becomes available.

    Args:
        spark: Active SparkSession.
        run_id: UUID string identifying this pipeline run.
        proc_name: Stored procedure / pipeline name.
    """

    def __init__(self, spark: SparkSession, run_id: str, proc_name: str) -> None:
        self._spark = spark
        self._run_id = run_id
        self._proc_name = proc_name

    def log_step(
        self,
        step: str,
        status: str,
        message: str = "",
        complete: bool = False,
    ) -> None:
        """Emit a log record.

        Args:
            step: Step identifier, e.g. 'STEP1_CustomerFilter'.
            status: 'OK', 'START', 'SUCCESS', or 'FAIL'.
            message: Optional detail message.
            complete: Whether this is the terminal log entry for the run.
        """
        ts = datetime.now(timezone.utc).isoformat()
        print(
            f"[{ts}] run={self._run_id} proc={self._proc_name} "
            f"step={step} status={status} complete={complete} msg={message!r}"
        )


# =============================================================================
# Step functions
# =============================================================================

def _step1_customer_filter(params: PipelineParams) -> List[int]:
    """STEP 1 — Parse customer CSV filter.

    SQL lines 163-170: #CustomerFilter temp table + @HasCustFilter flag.

    Args:
        params: Pipeline parameters.

    Returns:
        List of integer customer IDs; empty if no filter.
    """
    # OBJECT_ID tempdb checks (lines 163, 174, …) → skip entirely
    return ufn_split_csv_int(params.customer_ids_csv)


def _step2_base_orders(
    spark: SparkSession,
    start_date: date,
    end_date: date,
    params: PipelineParams,
    customer_ids: List[int],
) -> DataFrame:
    """STEP 2 — Build base orders DataFrame.

    SQL lines 176-214: SELECT … INTO #BaseOrders with multi-table JOINs.

    Args:
        spark: Active SparkSession.
        start_date: Resolved start date.
        end_date: Resolved end date.
        params: Pipeline parameters.
        customer_ids: Pre-parsed customer ID list from STEP 1.

    Returns:
        Cached and materialised base orders DataFrame.
    """
    has_cust_filter = len(customer_ids) > 0  # line 168

    # Sub-query: SalesPersonQuotaHistory aggregated over date range (lines 200-205)
    sqa = (
        spark.table("Sales.SalesPersonQuotaHistory")
        .where(F.col("QuotaDate").cast("date").between(F.lit(start_date), F.lit(end_date)))
        .groupBy("BusinessEntityID")
        .agg(F.sum("SalesQuota").alias("SalesQuota"))
    )

    soh = spark.table("Sales.SalesOrderHeader")
    st  = spark.table("Sales.SalesTerritory")
    # sp2 alias is joined for SalesPerson entity but person name comes from Person.Person
    sp  = spark.table("Person.Person")
    e   = spark.table("HumanResources.Employee")

    base = (
        soh
        .join(st,  soh["TerritoryID"]    == st["TerritoryID"],    "inner")
        .join(
            spark.table("Sales.SalesPerson").alias("sp2"),
            soh["SalesPersonID"] == F.col("sp2.BusinessEntityID"),
            "left",
        )
        .join(
            sp.alias("sp"),
            soh["SalesPersonID"] == F.col("sp.BusinessEntityID"),
            "left",
        )
        .join(
            e.alias("e"),
            soh["SalesPersonID"] == F.col("e.BusinessEntityID"),
            "left",
        )
        .join(
            sqa.alias("sqa"),
            soh["SalesPersonID"] == F.col("sqa.BusinessEntityID"),
            "left",
        )
        .select(
            soh["SalesOrderID"],
            soh["CustomerID"],
            soh["SalesPersonID"],
            soh["OrderDate"].cast("date").alias("OrderDate"),       # line 180
            soh["ShipDate"].cast("date").alias("ShipDate"),         # line 181
            soh["SubTotal"],
            soh["TaxAmt"],
            soh["Freight"],
            soh["TotalDue"],
            soh["OnlineOrderFlag"],
            soh["RevisionNumber"],
            st["Name"].alias("TerritoryName"),
            st["CountryRegionCode"],
            st["Group"].alias("TerritoryGroup"),
            # line 191 — COALESCE(sp.FirstName + ' ' + sp.LastName, 'Online/Unknown')
            F.coalesce(
                F.concat_ws(" ", F.col("sp.FirstName"), F.col("sp.LastName")),
                F.lit("Online/Unknown"),
            ).alias("SalesPersonName"),
            F.col("e.JobTitle").alias("SalesPersonTitle"),
            # line 193 — COALESCE(sqa.SalesQuota, 0) with explicit Decimal precision
            F.coalesce(
                F.col("sqa.SalesQuota"),
                F.lit(Decimal("0")).cast(DecimalType(19, 4)),
            ).alias("SalesQuota"),
        )
        # line 206
        .where(soh["OrderDate"].cast("date").between(F.lit(start_date), F.lit(end_date)))
        .where(soh["TotalDue"] >= float(params.min_order_amt))
    )

    # line 208 — optional territory filter (case-sensitive — gotcha #2)
    if params.territory_group_filter:
        base = base.where(F.col("TerritoryGroup") == params.territory_group_filter)

    # lines 209-210 — optional customer filter
    if has_cust_filter:
        base = base.where(F.col("CustomerID").isin(customer_ids))

    # lines 212-214 — Indexes CX_BaseOrders / IX_BaseOrders_Cust / IX_BaseOrders_SP:
    # no B-tree indexes in Spark; repartition simulates data locality.
    # TODO: Constraint — INCLUDE columns on indexes not enforced; repartition
    #       provides data locality only.
    base = base.repartition(F.col("SalesOrderID")).cache()
    base.count()  # force materialization
    return base


def _step3_lines(
    spark: SparkSession,
    base_orders: DataFrame,
) -> DataFrame:
    """STEP 3 — Line-level detail.

    SQL lines 221-257: JOIN SalesOrderDetail → #BaseOrders → Production tables.

    Args:
        spark: Active SparkSession.
        base_orders: Materialised base orders DataFrame from STEP 2.

    Returns:
        Cached and materialised lines DataFrame.
    """
    d  = spark.table("Sales.SalesOrderDetail")
    p  = spark.table("Production.Product")
    ps = spark.table("Production.ProductSubcategory")
    pc = spark.table("Production.ProductCategory")
    pm = spark.table("Production.ProductModel")

    lines = (
        d
        .join(base_orders, d["SalesOrderID"] == base_orders["SalesOrderID"], "inner")
        .join(p,  d["ProductID"] == p["ProductID"],                          "inner")
        .join(ps, p["ProductSubcategoryID"] == ps["ProductSubcategoryID"],   "left")
        .join(pc, ps["ProductCategoryID"]   == pc["ProductCategoryID"],      "left")
        .join(pm, p["ProductModelID"]        == pm["ProductModelID"],         "left")
        .select(
            d["SalesOrderID"],
            d["SalesOrderDetailID"],
            d["ProductID"],
            d["OrderQty"],
            d["UnitPrice"],
            d["UnitPriceDiscount"],
            d["LineTotal"],
            p["Name"].alias("ProductName"),
            p["ProductNumber"],
            p["Color"],
            p["ListPrice"],
            p["StandardCost"],
            # line 234
            (p["ListPrice"] - p["StandardCost"]).alias("GrossMarginUnit"),
            ps["Name"].alias("SubCategoryName"),
            pc["Name"].alias("CategoryName"),
            pm["Name"].alias("ModelName"),
            base_orders["OrderDate"],
            base_orders["TerritoryGroup"],
            base_orders["TerritoryName"],
            base_orders["CountryRegionCode"],
            base_orders["CustomerID"],
            base_orders["SalesPersonID"],
            base_orders["SalesPersonName"],
            base_orders["OnlineOrderFlag"],
        )
    )

    # lines 254-257 — indexes: no B-tree in Spark; repartition simulates locality.
    # TODO: Constraint — INCLUDE columns on indexes not enforced; repartition
    #       provides data locality only.
    lines = lines.repartition(F.col("SalesOrderID"), F.col("SalesOrderDetailID")).cache()
    lines.count()  # force materialization
    return lines


def _step4_customer_tier(lines: DataFrame) -> DataFrame:
    """STEP 4 — Customer tier classification.

    SQL lines 264-309: CTE CustRevenue + 3-level nested CASE for CustomerTier.

    Args:
        lines: Lines DataFrame from STEP 3.

    Returns:
        Customer tier DataFrame (CustomerID, TerritoryGroup, …, CustomerTier).
    """
    # CTE CustRevenue (lines 264-276)
    cust_revenue = lines.groupBy("CustomerID", "TerritoryGroup").agg(
        F.sum("LineTotal").alias("TotalRevenue"),
        F.sum(
            F.when(F.col("CategoryName") == "Bikes",       F.col("LineTotal")).otherwise(F.lit(0))
        ).alias("BikeRevenue"),
        F.sum(
            F.when(F.col("CategoryName") == "Components",  F.col("LineTotal")).otherwise(F.lit(0))
        ).alias("CompRevenue"),
        F.sum(
            F.when(F.col("CategoryName") == "Clothing",    F.col("LineTotal")).otherwise(F.lit(0))
        ).alias("ClothingRevenue"),
        F.sum(
            F.when(F.col("CategoryName") == "Accessories", F.col("LineTotal")).otherwise(F.lit(0))
        ).alias("AccessRevenue"),
        F.countDistinct("SalesOrderID").alias("OrderCount"),
    )

    # 3-level nested CASE for CustomerTier (lines 286-307)
    # Gotcha #2: string comparisons are case-sensitive in PySpark; source data
    # is expected to carry title-cased TerritoryGroup values ('North America',
    # 'Europe', 'Pacific'). Add F.lower() normalization if that assumption fails.
    customer_tier_col = (
        F.when(
            F.col("TerritoryGroup") == "North America",
            F.when(F.col("TotalRevenue") >= 50000, F.lit("Gold"))
             .when(F.col("TotalRevenue") >= 20000, F.lit("Silver"))
             .when(F.col("TotalRevenue") >= 5000,  F.lit("Bronze"))
             .otherwise(F.lit("Standard")),
        )
        .when(
            F.col("TerritoryGroup") == "Europe",
            F.when(F.col("TotalRevenue") >= 45000, F.lit("Gold"))
             .when(F.col("TotalRevenue") >= 18000, F.lit("Silver"))
             .when(F.col("TotalRevenue") >= 4500,  F.lit("Bronze"))
             .otherwise(F.lit("Standard")),
        )
        .when(
            F.col("TerritoryGroup") == "Pacific",
            F.when(F.col("TotalRevenue") >= 40000, F.lit("Gold"))
             .when(F.col("TotalRevenue") >= 15000, F.lit("Silver"))
             .when(F.col("TotalRevenue") >= 4000,  F.lit("Bronze"))
             .otherwise(F.lit("Standard")),
        )
        .otherwise(
            F.when(F.col("TotalRevenue") >= 50000, F.lit("Gold"))
             .when(F.col("TotalRevenue") >= 20000, F.lit("Silver"))
             .when(F.col("TotalRevenue") >= 5000,  F.lit("Bronze"))
             .otherwise(F.lit("Standard")),
        )
    )

    return cust_revenue.withColumn("CustomerTier", customer_tier_col)


def _build_discount_pct_col() -> F.Column:
    """Build CASE Block A — AppliedDiscountPct (SQL lines 323-360).

    Returns DecimalType(5,4)-cast column expression.

    Gotcha #2: All CategoryName / SubCategoryName / TerritoryGroup / CustomerTier
    comparisons are case-sensitive. Source data must produce exact-match strings.
    """
    def _disc(na: float, eu: float, pa: float, els: float = 0.0) -> F.Column:
        """Helper: territory dispatch returning DecimalType literal."""
        return (
            F.when(F.col("TerritoryGroup") == "North America",
                   F.lit(na).cast(DecimalType(5, 4)))
             .when(F.col("TerritoryGroup") == "Europe",
                   F.lit(eu).cast(DecimalType(5, 4)))
             .when(F.col("TerritoryGroup") == "Pacific",
                   F.lit(pa).cast(DecimalType(5, 4)))
             .otherwise(F.lit(els).cast(DecimalType(5, 4)))
        )

    def _tier_disc(na_g, na_s, na_b, na_e,
                   eu_g, eu_s, eu_b, eu_e,
                   pa_g, pa_s, pa_b, pa_e,
                   else_val=0.0) -> F.Column:
        """3-level dispatch: territory → customer tier."""
        return (
            F.when(
                F.col("TerritoryGroup") == "North America",
                F.when(F.col("CustomerTier") == "Gold",   F.lit(na_g).cast(DecimalType(5, 4)))
                 .when(F.col("CustomerTier") == "Silver", F.lit(na_s).cast(DecimalType(5, 4)))
                 .when(F.col("CustomerTier") == "Bronze", F.lit(na_b).cast(DecimalType(5, 4)))
                 .otherwise(F.lit(na_e).cast(DecimalType(5, 4))),
            )
            .when(
                F.col("TerritoryGroup") == "Europe",
                F.when(F.col("CustomerTier") == "Gold",   F.lit(eu_g).cast(DecimalType(5, 4)))
                 .when(F.col("CustomerTier") == "Silver", F.lit(eu_s).cast(DecimalType(5, 4)))
                 .when(F.col("CustomerTier") == "Bronze", F.lit(eu_b).cast(DecimalType(5, 4)))
                 .otherwise(F.lit(eu_e).cast(DecimalType(5, 4))),
            )
            .when(
                F.col("TerritoryGroup") == "Pacific",
                F.when(F.col("CustomerTier") == "Gold",   F.lit(pa_g).cast(DecimalType(5, 4)))
                 .when(F.col("CustomerTier") == "Silver", F.lit(pa_s).cast(DecimalType(5, 4)))
                 .when(F.col("CustomerTier") == "Bronze", F.lit(pa_b).cast(DecimalType(5, 4)))
                 .otherwise(F.lit(pa_e).cast(DecimalType(5, 4))),
            )
            .otherwise(F.lit(else_val).cast(DecimalType(5, 4)))
        )

    # Mountain Bikes (lines 324-329)
    mtn = _tier_disc(
        0.1200, 0.0800, 0.0500, 0.0000,
        0.1300, 0.0900, 0.0600, 0.0100,
        0.1100, 0.0750, 0.0500, 0.0000,
    )
    # Road Bikes (lines 330-335)
    road = _tier_disc(
        0.1150, 0.0780, 0.0480, 0.0000,
        0.1250, 0.0850, 0.0600, 0.0100,
        0.1050, 0.0720, 0.0470, 0.0000,
    )
    # Touring Bikes (lines 336-340) — no Pacific branch; else fallback
    touring = (
        F.when(
            F.col("TerritoryGroup") == "North America",
            F.when(F.col("CustomerTier") == "Gold",   F.lit(0.1100).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Silver", F.lit(0.0750).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Bronze", F.lit(0.0460).cast(DecimalType(5, 4)))
             .otherwise(F.lit(0.0000).cast(DecimalType(5, 4))),
        )
        .when(
            F.col("TerritoryGroup") == "Europe",
            F.when(F.col("CustomerTier") == "Gold",   F.lit(0.1200).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Silver", F.lit(0.0830).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Bronze", F.lit(0.0560).cast(DecimalType(5, 4)))
             .otherwise(F.lit(0.0080).cast(DecimalType(5, 4))),
        )
        .otherwise(
            F.when(F.col("CustomerTier") == "Gold",   F.lit(0.1000).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Silver", F.lit(0.0700).cast(DecimalType(5, 4)))
             .otherwise(F.lit(0.0000).cast(DecimalType(5, 4))),
        )
    )
    # Components (lines 341-346)
    comp = _tier_disc(
        0.0800, 0.0600, 0.0400, 0.0000,
        0.0850, 0.0650, 0.0430, 0.0050,
        0.0780, 0.0580, 0.0380, 0.0000,
    )
    # Clothing (lines 347-352) — else branch has only Gold/Silver explicit
    clothing = (
        F.when(
            F.col("TerritoryGroup") == "North America",
            F.when(F.col("CustomerTier") == "Gold",   F.lit(0.1500).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Silver", F.lit(0.1000).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Bronze", F.lit(0.0700).cast(DecimalType(5, 4)))
             .otherwise(F.lit(0.0200).cast(DecimalType(5, 4))),
        )
        .when(
            F.col("TerritoryGroup") == "Europe",
            F.when(F.col("CustomerTier") == "Gold",   F.lit(0.1600).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Silver", F.lit(0.1100).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Bronze", F.lit(0.0780).cast(DecimalType(5, 4)))
             .otherwise(F.lit(0.0250).cast(DecimalType(5, 4))),
        )
        .when(
            F.col("TerritoryGroup") == "Pacific",
            F.when(F.col("CustomerTier") == "Gold",   F.lit(0.1400).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Silver", F.lit(0.0950).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Bronze", F.lit(0.0660).cast(DecimalType(5, 4)))
             .otherwise(F.lit(0.0180).cast(DecimalType(5, 4))),
        )
        .otherwise(
            F.when(F.col("CustomerTier") == "Gold",   F.lit(0.1300).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Silver", F.lit(0.0900).cast(DecimalType(5, 4)))
             .otherwise(F.lit(0.0150).cast(DecimalType(5, 4))),
        )
    )
    # Accessories (lines 353-358)
    acc = _tier_disc(
        0.1000, 0.0700, 0.0500, 0.0000,
        0.1050, 0.0730, 0.0520, 0.0000,
        0.0950, 0.0680, 0.0480, 0.0000,
    )

    return (
        F.when(
            (F.col("CategoryName") == "Bikes") & (F.col("SubCategoryName") == "Mountain Bikes"),
            mtn,
        )
        .when(
            (F.col("CategoryName") == "Bikes") & (F.col("SubCategoryName") == "Road Bikes"),
            road,
        )
        .when(
            (F.col("CategoryName") == "Bikes") & (F.col("SubCategoryName") == "Touring Bikes"),
            touring,
        )
        .when(F.col("CategoryName") == "Components", comp)
        .when(F.col("CategoryName") == "Clothing",   clothing)
        .when(F.col("CategoryName") == "Accessories", acc)
        .otherwise(F.lit(0.0000).cast(DecimalType(5, 4)))
    )


def _build_commission_pct_col() -> F.Column:
    """Build CASE Block B — AppliedCommissionPct (SQL lines 362-386).

    Returns DecimalType(5,4)-cast column expression.
    """
    def _tier3(na_g, na_s, na_b, na_e,
                eu_g, eu_s, eu_b, eu_e,
                else_g, else_e) -> F.Column:
        return (
            F.when(
                F.col("TerritoryGroup") == "North America",
                F.when(F.col("CustomerTier") == "Gold",   F.lit(na_g).cast(DecimalType(5, 4)))
                 .when(F.col("CustomerTier") == "Silver", F.lit(na_s).cast(DecimalType(5, 4)))
                 .when(F.col("CustomerTier") == "Bronze", F.lit(na_b).cast(DecimalType(5, 4)))
                 .otherwise(F.lit(na_e).cast(DecimalType(5, 4))),
            )
            .when(
                F.col("TerritoryGroup") == "Europe",
                F.when(F.col("CustomerTier") == "Gold",   F.lit(eu_g).cast(DecimalType(5, 4)))
                 .when(F.col("CustomerTier") == "Silver", F.lit(eu_s).cast(DecimalType(5, 4)))
                 .when(F.col("CustomerTier") == "Bronze", F.lit(eu_b).cast(DecimalType(5, 4)))
                 .otherwise(F.lit(eu_e).cast(DecimalType(5, 4))),
            )
            .otherwise(
                F.when(F.col("CustomerTier") == "Gold",   F.lit(else_g).cast(DecimalType(5, 4)))
                 .otherwise(F.lit(else_e).cast(DecimalType(5, 4))),
            )
        )

    # Bikes — all three territories explicit (lines 364-369)
    bikes_comm = (
        F.when(
            F.col("TerritoryGroup") == "North America",
            F.when(F.col("CustomerTier") == "Gold",   F.lit(0.0500).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Silver", F.lit(0.0450).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Bronze", F.lit(0.0400).cast(DecimalType(5, 4)))
             .otherwise(F.lit(0.0350).cast(DecimalType(5, 4))),
        )
        .when(
            F.col("TerritoryGroup") == "Europe",
            F.when(F.col("CustomerTier") == "Gold",   F.lit(0.0520).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Silver", F.lit(0.0470).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Bronze", F.lit(0.0420).cast(DecimalType(5, 4)))
             .otherwise(F.lit(0.0370).cast(DecimalType(5, 4))),
        )
        .when(
            F.col("TerritoryGroup") == "Pacific",
            F.when(F.col("CustomerTier") == "Gold",   F.lit(0.0480).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Silver", F.lit(0.0430).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Bronze", F.lit(0.0380).cast(DecimalType(5, 4)))
             .otherwise(F.lit(0.0330).cast(DecimalType(5, 4))),
        )
        .otherwise(F.lit(0.0350).cast(DecimalType(5, 4)))
    )

    # Components (lines 370-374)
    comp_comm = (
        F.when(
            F.col("TerritoryGroup") == "North America",
            F.when(F.col("CustomerTier") == "Gold",   F.lit(0.0300).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Silver", F.lit(0.0280).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Bronze", F.lit(0.0260).cast(DecimalType(5, 4)))
             .otherwise(F.lit(0.0240).cast(DecimalType(5, 4))),
        )
        .when(
            F.col("TerritoryGroup") == "Europe",
            F.when(F.col("CustomerTier") == "Gold",   F.lit(0.0320).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Silver", F.lit(0.0300).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Bronze", F.lit(0.0278).cast(DecimalType(5, 4)))
             .otherwise(F.lit(0.0255).cast(DecimalType(5, 4))),
        )
        .otherwise(
            F.when(F.col("CustomerTier") == "Gold", F.lit(0.0290).cast(DecimalType(5, 4)))
             .otherwise(F.lit(0.0235).cast(DecimalType(5, 4))),
        )
    )

    # Clothing (lines 375-379)
    clothing_comm = (
        F.when(
            F.col("TerritoryGroup") == "North America",
            F.when(F.col("CustomerTier") == "Gold",   F.lit(0.0200).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Silver", F.lit(0.0180).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Bronze", F.lit(0.0160).cast(DecimalType(5, 4)))
             .otherwise(F.lit(0.0140).cast(DecimalType(5, 4))),
        )
        .when(
            F.col("TerritoryGroup") == "Europe",
            F.when(F.col("CustomerTier") == "Gold",   F.lit(0.0220).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Silver", F.lit(0.0200).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Bronze", F.lit(0.0175).cast(DecimalType(5, 4)))
             .otherwise(F.lit(0.0150).cast(DecimalType(5, 4))),
        )
        .otherwise(
            F.when(F.col("CustomerTier") == "Gold", F.lit(0.0195).cast(DecimalType(5, 4)))
             .otherwise(F.lit(0.0130).cast(DecimalType(5, 4))),
        )
    )

    # Accessories (lines 380-384)
    acc_comm = (
        F.when(
            F.col("TerritoryGroup") == "North America",
            F.when(F.col("CustomerTier") == "Gold",   F.lit(0.0250).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Silver", F.lit(0.0230).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Bronze", F.lit(0.0210).cast(DecimalType(5, 4)))
             .otherwise(F.lit(0.0190).cast(DecimalType(5, 4))),
        )
        .when(
            F.col("TerritoryGroup") == "Europe",
            F.when(F.col("CustomerTier") == "Gold",   F.lit(0.0270).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Silver", F.lit(0.0248).cast(DecimalType(5, 4)))
             .when(F.col("CustomerTier") == "Bronze", F.lit(0.0225).cast(DecimalType(5, 4)))
             .otherwise(F.lit(0.0200).cast(DecimalType(5, 4))),
        )
        .otherwise(
            F.when(F.col("CustomerTier") == "Gold", F.lit(0.0240).cast(DecimalType(5, 4)))
             .otherwise(F.lit(0.0185).cast(DecimalType(5, 4))),
        )
    )

    return (
        F.when(F.col("CategoryName") == "Bikes",       bikes_comm)
         .when(F.col("CategoryName") == "Components",  comp_comm)
         .when(F.col("CategoryName") == "Clothing",    clothing_comm)
         .when(F.col("CategoryName") == "Accessories", acc_comm)
         .otherwise(F.lit(0.0200).cast(DecimalType(5, 4)))
    )


def _build_tax_override_col() -> F.Column:
    """Build CASE Block C — TaxOverridePct (SQL lines 388-395).

    Returns DecimalType(5,4) or null column expression.
    """
    return (
        F.when(F.col("TerritoryGroup")    == "Europe",  F.lit(0.2000).cast(DecimalType(5, 4)))
         .when(F.col("TerritoryGroup")    == "Pacific", F.lit(0.1000).cast(DecimalType(5, 4)))
         .when(F.col("CountryRegionCode") == "CA",      F.lit(0.0500).cast(DecimalType(5, 4)))
         .when(F.col("CountryRegionCode") == "US",      F.lit(None).cast(DecimalType(5, 4)))
         .otherwise(F.lit(None).cast(DecimalType(5, 4)))
    )


def _step5_priced_lines(lines: DataFrame, customer_tier: DataFrame) -> DataFrame:
    """STEP 5 — Pricing engine: discount, commission, tax.

    SQL lines 318-404: SELECT l.*, ct.CustomerTier, Block A, Block B, Block C
    INTO #PricedLines FROM #Lines l LEFT JOIN #CustomerTier ct.

    Args:
        lines: Lines DataFrame from STEP 3.
        customer_tier: Customer tier DataFrame from STEP 4.

    Returns:
        Cached and materialised priced lines DataFrame.
    """
    priced = (
        lines
        .join(
            customer_tier.select("CustomerID", "TerritoryGroup", "CustomerTier"),
            on=["CustomerID", "TerritoryGroup"],
            how="left",
        )
        .withColumn("AppliedDiscountPct",   _build_discount_pct_col())
        .withColumn("AppliedCommissionPct", _build_commission_pct_col())
        .withColumn("TaxOverridePct",       _build_tax_override_col())
    )

    # lines 402-404 — Indexes CX_PricedLines / IX_PricedLines_SP:
    # no B-tree indexes in Spark; repartition simulates data locality.
    # TODO: Constraint — INCLUDE columns on indexes not enforced; repartition
    #       provides data locality only.
    priced = priced.repartition(F.col("SalesOrderID"), F.col("SalesOrderDetailID")).cache()
    priced.count()  # force materialization
    return priced


def _step6_line_finals(priced_lines: DataFrame) -> DataFrame:
    """STEP 6 — Compute adjusted revenue, commission, margin.

    SQL lines 411-450.
    Gotcha #5: Decimal precision — spark.sql.decimalOperations.allowPrecisionLoss
    should be set to false at SparkSession level.

    Args:
        priced_lines: Priced lines DataFrame from STEP 5.

    Returns:
        Cached and materialised line finals DataFrame.
    """
    # AdjustedRevenue computed once and referenced (lines 432, 434, 436, 439-442)
    adj_rev_expr = (
        F.col("LineTotal") * (F.lit(1.0) - F.col("AppliedDiscountPct"))
    ).cast(DecimalType(19, 4))

    line_finals = (
        priced_lines
        .select(
            "SalesOrderID",
            "SalesOrderDetailID",
            "CustomerID",
            "SalesPersonID",
            "SalesPersonName",
            "OrderDate",
            "TerritoryGroup",
            "TerritoryName",
            "CategoryName",
            "SubCategoryName",
            "ProductName",
            "CustomerTier",
            "OrderQty",
            "UnitPrice",
            "ListPrice",
            "StandardCost",
            F.col("LineTotal").alias("OriginalLineTotal"),  # line 428
            "AppliedDiscountPct",
            "AppliedCommissionPct",
            "TaxOverridePct",
        )
        # Compute AdjustedRevenue first so subsequent columns can reference it
        .withColumn("AdjustedRevenue", adj_rev_expr)
        .withColumn(
            "DiscountAmount",
            (F.col("LineTotal") * F.col("AppliedDiscountPct")).cast(DecimalType(19, 4)),
        )
        .withColumn(
            "CommissionEarned",
            (F.col("AdjustedRevenue") * F.col("AppliedCommissionPct")).cast(DecimalType(19, 4)),
        )
        .withColumn(
            "GrossMargin",
            (F.col("AdjustedRevenue") - (F.col("StandardCost") * F.col("OrderQty"))).cast(DecimalType(19, 4)),
        )
        # GrossMarginPct: guard against AdjustedRevenue == 0 (lines 438-443)
        .withColumn(
            "GrossMarginPct",
            F.when(
                F.col("AdjustedRevenue") == F.lit(0).cast(DecimalType(19, 4)),
                F.lit(None).cast(DecimalType(19, 4)),
            ).otherwise(
                (
                    (F.col("AdjustedRevenue") - (F.col("StandardCost") * F.col("OrderQty")))
                    / F.col("AdjustedRevenue")
                ).cast(DecimalType(19, 4))
            ),
        )
        # EstimatedTax: only when TaxOverridePct is not null (lines 444-448)
        .withColumn(
            "EstimatedTax",
            F.when(
                F.col("TaxOverridePct").isNotNull(),
                (F.col("AdjustedRevenue") * F.col("TaxOverridePct")).cast(DecimalType(19, 4)),
            ).otherwise(F.lit(None).cast(DecimalType(19, 4))),
        )
    )

    # Clustered index CX_LineFinals on (SalesPersonID, SalesOrderID) → repartition
    line_finals = line_finals.repartition(F.col("SalesPersonID"), F.col("SalesOrderID")).cache()
    line_finals.count()  # force materialization
    return line_finals


def _step7_sp_summary(line_finals: DataFrame, base_orders: DataFrame) -> DataFrame:
    """STEP 7 — Salesperson commission summary + quota attainment.

    SQL lines 459-489.
    Gotcha #3: NTILE ORDER BY TotalAdjustedRevenue DESC — NULLs last in SQL
    Server, FIRST in PySpark without explicit direction. Use desc_nulls_last().

    Args:
        line_finals: Line finals DataFrame from STEP 6.
        base_orders: Base orders DataFrame from STEP 2 (for SalesQuota).

    Returns:
        Salesperson summary DataFrame with RevenueQuartile.
    """
    # Bring SalesQuota in from base_orders (line 475: MAX(bo.SalesQuota))
    quota_df = base_orders.select("SalesOrderID", "SalesQuota")

    lf_with_quota = line_finals.join(quota_df, on="SalesOrderID", how="left")

    agg_df = (
        lf_with_quota
        .where(F.col("SalesPersonID").isNotNull())
        .groupBy("SalesPersonID", "SalesPersonName", "TerritoryGroup", "TerritoryName")
        .agg(
            F.countDistinct("SalesOrderID").alias("TotalOrders"),
            F.sum("OriginalLineTotal").alias("TotalOriginalRevenue"),
            F.sum("AdjustedRevenue").alias("TotalAdjustedRevenue"),
            F.sum("DiscountAmount").alias("TotalDiscountGiven"),
            F.sum("CommissionEarned").alias("TotalCommissionEarned"),
            F.sum("GrossMargin").alias("TotalGrossMargin"),
            F.avg("GrossMarginPct").alias("AvgGrossMarginPct"),
            F.sum(
                F.when(F.col("CategoryName") == "Bikes",       F.col("AdjustedRevenue")).otherwise(F.lit(0))
            ).alias("BikeRevenue"),
            F.sum(
                F.when(F.col("CategoryName") == "Components",  F.col("AdjustedRevenue")).otherwise(F.lit(0))
            ).alias("CompRevenue"),
            F.sum(
                F.when(F.col("CategoryName") == "Clothing",    F.col("AdjustedRevenue")).otherwise(F.lit(0))
            ).alias("ClothingRevenue"),
            F.sum(
                F.when(F.col("CategoryName") == "Accessories", F.col("AdjustedRevenue")).otherwise(F.lit(0))
            ).alias("AccessRevenue"),
            F.max("SalesQuota").alias("SalesQuota"),
        )
    )

    # QuotaAttainmentBand (lines 476-483)
    quota_col   = F.coalesce(F.col("SalesQuota"), F.lit(Decimal("0")).cast(DecimalType(19, 4)))
    quota_denom = F.when(quota_col == F.lit(0).cast(DecimalType(19, 4)), F.lit(None)).otherwise(quota_col)
    attainment  = F.col("TotalAdjustedRevenue") / quota_denom

    attainment_band = (
        F.when(quota_col == F.lit(0).cast(DecimalType(19, 4)), F.lit("No Quota"))
         .when(attainment >= 1.20, F.lit("Overachiever"))
         .when(attainment >= 1.00, F.lit("On Target"))
         .when(attainment >= 0.80, F.lit("Near Target"))
         .when(attainment >= 0.60, F.lit("Below Target"))
         .otherwise(F.lit("At Risk"))
    )

    agg_df = agg_df.withColumn("QuotaAttainmentBand", attainment_band)

    # NTILE(4) applied after GROUP BY — gotcha #3: use desc_nulls_last()
    ntile_window = Window.orderBy(F.col("TotalAdjustedRevenue").desc_nulls_last())
    sp_summary   = agg_df.withColumn("RevenueQuartile", F.ntile(4).over(ntile_window))

    return sp_summary


def _step8_customer_summary(
    spark: SparkSession,
    line_finals: DataFrame,
    end_date: date,
) -> DataFrame:
    """STEP 8 — Customer RFM scoring.

    SQL lines 496-520.
    Gotcha #1: DATEDIFF(DAY, MAX(lf.OrderDate), @EndDate) → F.datediff(end, start).
    Gotcha #3: NTILE ORDER BY windows need explicit null direction.

    Args:
        spark: Active SparkSession.
        line_finals: Line finals DataFrame from STEP 6.
        end_date: Resolved pipeline end date.

    Returns:
        Customer summary DataFrame with RFM scores.
    """
    # CTE CustAgg (lines 497-510)
    cust_agg = (
        line_finals
        .groupBy("CustomerID")
        .agg(
            F.countDistinct("SalesOrderID").alias("OrderCount"),
            F.sum("AdjustedRevenue").alias("TotalRevenue"),
            F.avg("AdjustedRevenue").alias("AvgLineRevenue"),
            F.max("OrderDate").alias("LastOrderDate"),
            F.min("OrderDate").alias("FirstOrderDate"),
            # Gotcha #1: args reversed vs SQL Server — F.datediff(end, start)
            F.datediff(F.lit(end_date), F.max("OrderDate")).alias("RecencyDays"),
            F.sum("DiscountAmount").alias("TotalDiscount"),
            F.sum("CommissionEarned").alias("TotalCommission"),
            F.max("CustomerTier").alias("CustomerTier"),
            F.max("TerritoryGroup").alias("TerritoryGroup"),
        )
    )

    # JOIN Person.Person (line 520)
    person = spark.table("Person.Person").select(
        F.col("BusinessEntityID"),
        F.col("FirstName"),
        F.col("LastName"),
    )
    cust_agg = (
        cust_agg
        .join(
            person,
            on=cust_agg["CustomerID"] == person["BusinessEntityID"],
            how="inner",
        )
        .withColumn("CustomerName", F.concat_ws(" ", F.col("FirstName"), F.col("LastName")))
        .drop("BusinessEntityID", "FirstName", "LastName")
    )

    # NTILE(5) windows — gotcha #3: explicit null direction
    recency_w  = Window.orderBy(F.col("RecencyDays").asc_nulls_last())
    freq_w     = Window.orderBy(F.col("OrderCount").desc_nulls_last())
    monetary_w = Window.orderBy(F.col("TotalRevenue").desc_nulls_last())

    cust_summary = (
        cust_agg
        .withColumn("RScore", F.ntile(5).over(recency_w))
        .withColumn("FScore", F.ntile(5).over(freq_w))
        .withColumn("MScore", F.ntile(5).over(monetary_w))
    )

    # Clustered index CX_CustSummary on CustomerID → repartition
    cust_summary = cust_summary.repartition(F.col("CustomerID")).cache()
    cust_summary.count()  # force materialization
    return cust_summary


def _step9_territory_benchmarks(sp_summary: DataFrame) -> DataFrame:
    """STEP 9 — Territory benchmarks.

    SQL lines 529-542: simple GROUP BY on #SPSummary.

    Args:
        sp_summary: Salesperson summary DataFrame from STEP 7.

    Returns:
        Territory benchmarks DataFrame.
    """
    territory_benchmarks = sp_summary.groupBy("TerritoryGroup").agg(
        F.countDistinct("SalesPersonID").alias("SalesPersonCount"),
        F.sum("TotalAdjustedRevenue").alias("TerritoryTotalRevenue"),
        F.avg("TotalAdjustedRevenue").alias("TerritoryAvgRevSP"),
        F.avg("TotalCommissionEarned").alias("TerritoryAvgCommission"),
        F.avg("AvgGrossMarginPct").alias("TerritoryAvgMarginPct"),
        F.sum("BikeRevenue").alias("TerritoryBikeRevenue"),
        F.sum("CompRevenue").alias("TerritoryCompRevenue"),
        F.sum("ClothingRevenue").alias("TerritoryClothingRevenue"),
        F.sum("AccessRevenue").alias("TerritoryAccessRevenue"),
    )

    # Clustered index CX_TerritoryBench on TerritoryGroup → repartition
    territory_benchmarks = territory_benchmarks.repartition(F.col("TerritoryGroup")).cache()
    territory_benchmarks.count()  # force materialization
    return territory_benchmarks


def _step10_final_output(
    sp_summary: DataFrame,
    territory_benchmarks: DataFrame,
    line_finals: DataFrame,
    customer_summary: DataFrame,
    start_date: date,
    end_date: date,
    run_id: str,
    params: PipelineParams,
) -> DataFrame:
    """STEP 10 — Final output with TOP N salespersons.

    SQL lines 551-592.
    Correlated subqueries (lines 579-586) are pre-aggregated and flattened to
    LEFT JOINs — see TODO below.
    # TODO: Correlated scalar subqueries at lines 579-586 (UniqueCustomers,
    #       AvgCustomerRFMScore) — cannot auto-convert from correlated form;
    #       pre-aggregated and flattened to LEFT JOINs here as the correct
    #       PySpark equivalent.

    Args:
        sp_summary: Salesperson summary DataFrame from STEP 7.
        territory_benchmarks: Territory benchmarks DataFrame from STEP 9.
        line_finals: Line finals DataFrame from STEP 6.
        customer_summary: Customer summary DataFrame from STEP 8.
        start_date: Resolved pipeline start date.
        end_date: Resolved pipeline end date.
        run_id: UUID string for this run.
        params: Pipeline parameters (for top_n_sales_person).

    Returns:
        Final result DataFrame ordered by TotalAdjustedRevenue DESC, limited to
        top_n_sales_person rows.
    """
    # Pre-aggregate correlated subqueries (lines 579-586)
    # UniqueCustomers per SalesPersonID
    cust_per_sp = (
        line_finals
        .join(customer_summary.select("CustomerID"), on="CustomerID", how="inner")
        .groupBy("SalesPersonID")
        .agg(F.countDistinct("CustomerID").alias("UniqueCustomers"))
    )

    # AvgCustomerRFMScore per SalesPersonID
    rfm_per_sp = (
        line_finals
        .join(
            customer_summary.select("CustomerID", "RScore", "FScore", "MScore"),
            on="CustomerID",
            how="inner",
        )
        .groupBy("SalesPersonID")
        .agg(
            F.avg(
                (F.col("RScore") + F.col("FScore") + F.col("MScore")).cast(DoubleType())
            ).alias("AvgCustomerRFMScore")
        )
    )

    # RevenueVsTerritoryPctDelta: NULLIF denominator guard (lines 571-575)
    pct_delta_col = F.when(
        F.col("TerritoryAvgRevSP") == F.lit(0),
        F.lit(None).cast(DoubleType()),
    ).otherwise(
        (
            (F.col("TotalAdjustedRevenue") - F.col("TerritoryAvgRevSP"))
            / F.col("TerritoryAvgRevSP")
        ).cast(DoubleType())
    )

    final_df = (
        sp_summary
        .join(territory_benchmarks, on="TerritoryGroup", how="inner")
        .join(cust_per_sp,  on="SalesPersonID", how="left")
        .join(rfm_per_sp,   on="SalesPersonID", how="left")
        .select(
            "SalesPersonID",
            "SalesPersonName",
            "TerritoryGroup",
            "TerritoryName",
            "TotalOrders",
            "TotalOriginalRevenue",
            "TotalAdjustedRevenue",
            "TotalDiscountGiven",
            "TotalCommissionEarned",
            "TotalGrossMargin",
            "AvgGrossMarginPct",
            "BikeRevenue",
            "CompRevenue",
            "ClothingRevenue",
            "AccessRevenue",
            "SalesQuota",
            "QuotaAttainmentBand",
            "RevenueQuartile",
            # line 570
            (F.col("TotalAdjustedRevenue") - F.col("TerritoryAvgRevSP")).alias("RevenueVsTerritoryAvg"),
            # lines 571-575
            pct_delta_col.alias("RevenueVsTerritoryPctDelta"),
            # line 576
            (F.col("TotalCommissionEarned") - F.col("TerritoryAvgCommission")).alias("CommissionVsTerritoryAvg"),
            "TerritoryTotalRevenue",
            "TerritoryAvgMarginPct",
            # pre-aggregated correlated subqueries
            "UniqueCustomers",
            "AvgCustomerRFMScore",
            # lines 587-589
            F.lit(start_date).alias("SnapshotStartDate"),
            F.lit(end_date).alias("SnapshotEndDate"),
            F.lit(run_id).alias("RunId"),
        )
        # lines 551-552: TOP N ORDER BY TotalAdjustedRevenue DESC
        .orderBy(F.col("TotalAdjustedRevenue").desc_nulls_last())
        .limit(params.top_n_sales_person)
    )

    return final_df


# =============================================================================
# Pipeline entry point
# =============================================================================

def run_pipeline(spark: SparkSession, params: PipelineParams) -> DataFrame:
    """Run the full AW19 Sales Commission Pricing Pipeline.

    Mirrors dbo.usp_AW19_SalesCommissionPricingPipeline (SQL lines 135-603).

    Decimal precision note (gotcha #5): caller should set
        spark.conf.set("spark.sql.decimalOperations.allowPrecisionLoss", "false")
    before invoking this function.

    Args:
        spark: Active SparkSession.
        params: Pipeline parameters.

    Returns:
        Final DataFrame of top-N salespersons with commission metrics.

    Raises:
        Exception: Re-raises any exception after logging FAIL status.
    """
    # --- line 147: run identity -------------------------------------------------
    run_id = str(uuid.uuid4())

    # --- line 148: constant -----------------------------------------------------
    # PROC_NAME already defined at module level

    # --- line 150: start log ----------------------------------------------------
    logger = RunLogger(spark, run_id, PROC_NAME)
    logger.log_step("START", "START", "Pipeline initiated")

    # === Section 0: Resolve date bounds (SQL lines 152-158) ===
    start_date = params.start_date
    end_date   = params.end_date
    if start_date is None or end_date is None:
        bounds     = (
            spark.table("Sales.SalesOrderHeader")
            .agg(
                F.min("OrderDate").alias("min_d"),
                F.max("OrderDate").alias("max_d"),
            )
            .first()
        )
        start_date = params.start_date or bounds["min_d"]
        end_date   = params.end_date   or bounds["max_d"]

    # --- line 160: BEGIN TRY → Python try/except --------------------------------
    # TODO: Transaction semantics at lines 160/594 — consider Delta Lake for
    #       ACID rollback if pipeline partial-write atomicity is required.
    try:

        # === Section 1: Customer filter (SQL lines 163-171) ===
        customer_ids = _step1_customer_filter(params)
        logger.log_step("STEP1_CustomerFilter", "OK")

        # === Section 2: Base orders (SQL lines 176-216) ===
        base_orders = _step2_base_orders(spark, start_date, end_date, params, customer_ids)
        logger.log_step("STEP2_BaseOrders", "OK")

        # === Section 3: Line detail (SQL lines 221-259) ===
        lines = _step3_lines(spark, base_orders)
        logger.log_step("STEP3_Lines", "OK")

        # === Section 4: Customer tier (SQL lines 264-313) ===
        customer_tier = _step4_customer_tier(lines)
        logger.log_step("STEP4_CustomerTier", "OK")

        # === Section 5: Pricing engine (SQL lines 318-406) ===
        priced_lines = _step5_priced_lines(lines, customer_tier)
        logger.log_step("STEP5_PricingEngine", "OK")

        # === Section 6: Line finals (SQL lines 411-454) ===
        line_finals = _step6_line_finals(priced_lines)
        logger.log_step("STEP6_LineFinals", "OK")

        # === Section 7: SP summary (SQL lines 459-491) ===
        sp_summary = _step7_sp_summary(line_finals, base_orders)
        logger.log_step("STEP7_SPSummary", "OK")

        # === Section 8: Customer RFM (SQL lines 496-524) ===
        customer_summary = _step8_customer_summary(spark, line_finals, end_date)
        logger.log_step("STEP8_CustomerSummary", "OK")

        # === Section 9: Territory benchmarks (SQL lines 529-546) ===
        territory_benchmarks = _step9_territory_benchmarks(sp_summary)
        logger.log_step("STEP9_TerritoryBench", "OK")

        # === Section 10: Final output (SQL lines 549-592) ===
        # line 549: success log BEFORE final SELECT
        logger.log_step("END", "SUCCESS", "Completed", complete=True)

        result = _step10_final_output(
            sp_summary,
            territory_benchmarks,
            line_finals,
            customer_summary,
            start_date,
            end_date,
            run_id,
            params,
        )
        return result

    # lines 594-600: END CATCH → Python except
    except Exception as exc:
        err_msg = f"Error {type(exc).__name__} at pipeline: {traceback.format_exc()}"
        logger.log_step("END", "FAIL", err_msg, complete=True)
        raise


# =============================================================================
# CLI entry point
# =============================================================================

def main() -> None:
    """CLI wrapper for run_pipeline.

    Example::

        python aw19_sales_commission_pricing_pipeline.py \\
            --start-date 2013-01-01 \\
            --end-date   2014-12-31 \\
            --top-n      20
    """
    parser = argparse.ArgumentParser(
        description="AW19 Sales Commission Pricing Pipeline"
    )
    parser.add_argument("--start-date",       type=date.fromisoformat, default=None)
    parser.add_argument("--end-date",         type=date.fromisoformat, default=None)
    parser.add_argument("--territory-group",  type=str,  default=None)
    parser.add_argument("--customer-ids-csv", type=str,  default=None)
    parser.add_argument("--min-order-amt",    type=float, default=0.0)
    parser.add_argument("--top-n",            type=int,  default=10)
    parser.add_argument("--emit-debug",       action="store_true")
    args = parser.parse_args()

    params = PipelineParams(
        start_date=args.start_date,
        end_date=args.end_date,
        territory_group_filter=args.territory_group,
        customer_ids_csv=args.customer_ids_csv,
        min_order_amt=Decimal(str(args.min_order_amt)),
        top_n_sales_person=args.top_n,
        emit_debug=args.emit_debug,
    )

    spark = (
        SparkSession.builder
        .appName(PROC_NAME)
        # Gotcha #5: prevent silent decimal precision loss
        .config("spark.sql.decimalOperations.allowPrecisionLoss", "false")
        .getOrCreate()
    )

    result_df = run_pipeline(spark, params)
    result_df.show(truncate=False)


if __name__ == "__main__":
    main()
