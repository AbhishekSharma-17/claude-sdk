from __future__ import annotations

# =============================================================================
# aw19_audit_pricing_violations.py
#
# PySpark translation of dbo.usp_AW19_AuditPricingViolations (SQL lines 643-723)
# Source dialect : T-SQL (SQL Server)
# Complexity     : Moderate (score 3.25)
# =============================================================================

import argparse
from datetime import date
from decimal import Decimal

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DecimalType

# =============================================================================
# Module-level constants  (SQL lines 652-654)
# =============================================================================
PROC_NAME: str = "usp_AW19_AuditPricingViolations"


# =============================================================================
# Helper: logging stub  (SQL lines 709-714)
# =============================================================================
def log_step(
    spark: SparkSession,
    run_id: str,
    proc_name: str,
    step: str,
    status: str,
    message: str,
    complete: bool = False,
) -> None:
    """Placeholder for dbo.usp_AW19_Log — replace once that procedure is converted.

    Args:
        spark: Active SparkSession.
        run_id: Pipeline run identifier.
        proc_name: Stored-procedure / module name.
        step: Step label, e.g. ``'AUDIT_VIOLATIONS'``.
        status: ``'OK'`` or ``'WARN'``.
        message: Human-readable audit message.
        complete: ``True`` when this is the final log entry for the step.
    """
    # TODO: Replace with actual call to converted usp_AW19_Log PySpark function
    print(
        f"[LOG] run_id={run_id} proc={proc_name} step={step} "
        f"status={status} msg={message} complete={complete}"
    )


# === Section 1: Load Source Tables and Build Multi-Table Join (SQL lines 684-695) ===
def _step1_load_and_join(
    spark: SparkSession,
    start_date: date,
    end_date: date,
) -> DataFrame:
    """Load source tables, chain all joins, and apply the OrderDate range filter.

    Replicates the FROM / JOIN chain and WHERE date condition (SQL lines 684-695).
    Columns from each table are pre-aliased with unique prefixes so that no name
    collision survives into downstream steps.

    Args:
        spark: Active SparkSession.
        start_date: Inclusive start bound for OrderDate (``@StartDate``, SQL line 645).
        end_date: Inclusive end bound for OrderDate (``@EndDate``, SQL line 646).

    Returns:
        Joined DataFrame restricted to the requested date range, with all raw
        columns still present so the violation filter can reference them.
    """
    # ------------------------------------------------------------------ #
    # Load source tables  (SQL lines 684-694)                             #
    # ------------------------------------------------------------------ #
    detail = spark.table("Sales.SalesOrderDetail")
    header = spark.table("Sales.SalesOrderHeader")
    territory = spark.table("Sales.SalesTerritory")
    product = spark.table("Production.Product")
    subcategory = spark.table("Production.ProductSubcategory")
    category = spark.table("Production.ProductCategory")
    pricing_rules = spark.table("dbo.AW19_PricingRules")

    # Pre-select and rename to prevent ambiguity across the join chain
    detail_sel = detail.select(
        F.col("SalesOrderID"),
        F.col("SalesOrderDetailID"),
        F.col("ProductID").alias("d_ProductID"),
        F.col("UnitPriceDiscount"),
        F.col("UnitPrice"),
        F.col("LineTotal"),
        F.col("OrderQty"),
    )

    header_sel = header.select(
        F.col("SalesOrderID").alias("h_SalesOrderID"),
        F.col("TerritoryID").alias("h_TerritoryID"),
        # SQL line 682: CAST(h.OrderDate AS DATE) AS OrderDate
        F.col("OrderDate").cast("date").alias("OrderDate"),
    )

    territory_sel = territory.select(
        F.col("TerritoryID").alias("st_TerritoryID"),
        F.col("Group").alias("TerritoryGroup"),
    )

    product_sel = product.select(
        F.col("ProductID").alias("p_ProductID"),
        F.col("ProductSubcategoryID").alias("p_ProductSubcategoryID"),
    )

    subcategory_sel = subcategory.select(
        F.col("ProductSubcategoryID").alias("ps_ProductSubcategoryID"),
        F.col("ProductCategoryID").alias("ps_ProductCategoryID"),
    )

    category_sel = category.select(
        F.col("ProductCategoryID").alias("pc_ProductCategoryID"),
        F.col("Name").alias("CategoryName"),
    )

    pricing_rules_sel = pricing_rules.select(
        F.col("CategoryName").alias("pr_CategoryName"),
        F.col("TerritoryGroup").alias("pr_TerritoryGroup"),
        F.col("EffectiveDate").alias("pr_EffectiveDate"),
        F.col("ExpiryDate").alias("pr_ExpiryDate"),
        F.col("DiscountPct").alias("pr_DiscountPct"),
    )

    # ------------------------------------------------------------------ #
    # Chain joins                                                          #
    # ------------------------------------------------------------------ #

    # SQL line 685: JOIN Sales.SalesOrderHeader ON SalesOrderID
    joined = detail_sel.join(
        header_sel,
        on=detail_sel["SalesOrderID"] == header_sel["h_SalesOrderID"],
        how="inner",
    ).drop("h_SalesOrderID")

    # SQL line 686: JOIN Sales.SalesTerritory ON TerritoryID
    joined = joined.join(
        territory_sel,
        on=joined["h_TerritoryID"] == territory_sel["st_TerritoryID"],
        how="inner",
    ).drop("h_TerritoryID", "st_TerritoryID")

    # SQL line 687: JOIN Production.Product ON ProductID
    joined = joined.join(
        product_sel,
        on=joined["d_ProductID"] == product_sel["p_ProductID"],
        how="inner",
    ).drop("p_ProductID")

    # SQL line 688: LEFT JOIN Production.ProductSubcategory ON ProductSubcategoryID
    joined = joined.join(
        subcategory_sel,
        on=joined["p_ProductSubcategoryID"] == subcategory_sel["ps_ProductSubcategoryID"],
        how="left",
    ).drop("p_ProductSubcategoryID", "ps_ProductSubcategoryID")

    # SQL line 689: LEFT JOIN Production.ProductCategory ON ProductCategoryID
    joined = joined.join(
        category_sel,
        on=joined["ps_ProductCategoryID"] == category_sel["pc_ProductCategoryID"],
        how="left",
    ).drop("ps_ProductCategoryID", "pc_ProductCategoryID")

    # SQL lines 690-694: LEFT JOIN dbo.AW19_PricingRules — date-range overlap condition
    #
    # CRITICAL — ExpiryDate IS NULL (SQL line 694):
    #   SQL Server evaluates  (NULL OR expr)  as NULL in a WHERE, but this is a JOIN
    #   ON clause where a NULL result means "no match". We must express the IS NULL
    #   guard explicitly so that rows with no expiry date are treated as open-ended.
    pr_join_cond = (
        (pricing_rules_sel["pr_CategoryName"] == joined["CategoryName"])
        & (pricing_rules_sel["pr_TerritoryGroup"] == joined["TerritoryGroup"])
        & (pricing_rules_sel["pr_EffectiveDate"] <= joined["OrderDate"])
        & (
            pricing_rules_sel["pr_ExpiryDate"].isNull()
            | (pricing_rules_sel["pr_ExpiryDate"] >= joined["OrderDate"])
        )
    )

    joined = joined.join(pricing_rules_sel, on=pr_join_cond, how="left")

    # TODO: Constraint — LEFT JOIN to AW19_PricingRules (SQL lines 690-694) may match
    # multiple rules per order line (no DISTINCT on RuleId in the join predicate).
    # SQL Server returns one row per matching rule. If multiple rules can match the same
    # (CategoryName, TerritoryGroup, date) combination, add
    #   .dropDuplicates(['SalesOrderDetailID'])
    # after this join, or pre-filter pricing_rules to the most-specific rule before
    # joining.

    # SQL line 695: WHERE CAST(h.OrderDate AS DATE) BETWEEN @StartDate AND @EndDate
    joined = joined.where(
        F.col("OrderDate").between(F.lit(start_date), F.lit(end_date))
    )

    return joined


# === Section 2: Violation Filter and Column Projection (SQL lines 658-702) ===
def _step2_compute_and_filter(joined: DataFrame) -> DataFrame:
    """Apply violation predicates, compute CASE columns, and project the output schema.

    The violation WHERE filter (SQL lines 696-702) is applied *before* the SELECT
    projection (SQL lines 658-682) so that ``UnitPrice``, ``LineTotal``, and
    ``OrderQty`` — which are not in the final output — remain in scope.

    Args:
        joined: Date-filtered, fully-joined DataFrame from ``_step1_load_and_join``.

    Returns:
        DataFrame of violating rows with the final output schema.
        Equivalent to the ``#Violations`` temp table (SQL line 683).
    """
    # ------------------------------------------------------------------
    # Decimal expressions for COALESCE(pr.DiscountPct, 0) + 0.02
    #
    # Gotcha #5 — Decimal precision loss:
    #   SQL line 665/673: "COALESCE(pr.DiscountPct, 0) + 0.02" mixes DECIMAL(5,4)
    #   with a float literal in SQL Server. In PySpark, Python float literals cause
    #   silent precision loss. Use Decimal strings + explicit DecimalType cast.
    # ------------------------------------------------------------------
    max_discount = F.coalesce(
        F.col("pr_DiscountPct"),
        F.lit(Decimal("0")).cast(DecimalType(5, 4)),
    )
    threshold = max_discount + F.lit(Decimal("0.02")).cast(DecimalType(5, 4))

    # SQL lines 696-702: Violation WHERE filter
    violations = joined.where(
        (F.col("UnitPriceDiscount") > threshold)
        | (F.col("UnitPriceDiscount") < F.lit(0))
        | (F.col("UnitPrice") <= F.lit(0))
        | (F.col("LineTotal") < F.lit(0))
        | (F.col("OrderQty") <= F.lit(0))
    )

    # SQL lines 664-671: ViolationType CASE
    # Order of WHEN clauses is preserved from SQL (matters for overlapping conditions:
    # e.g. OVER_DISCOUNT is tested before NEGATIVE_DISCOUNT).
    violation_type_col = (
        F.when(F.col("UnitPriceDiscount") > threshold, F.lit("OVER_DISCOUNT"))
        .when(F.col("UnitPriceDiscount") < F.lit(0), F.lit("NEGATIVE_DISCOUNT"))
        .when(F.col("UnitPrice") <= F.lit(0), F.lit("ZERO_PRICE"))
        .when(F.col("LineTotal") < F.lit(0), F.lit("NEGATIVE_LINE_TOTAL"))
        .when(F.col("OrderQty") <= F.lit(0), F.lit("ZERO_QTY"))
        .otherwise(F.lit("OK"))
    )

    # SQL lines 672-679: Severity CASE  (integer: 3 = critical, 2 = warning, 0 = ok)
    severity_col = (
        F.when(F.col("UnitPriceDiscount") > threshold, F.lit(3))
        .when(F.col("UnitPriceDiscount") < F.lit(0), F.lit(3))
        .when(F.col("UnitPrice") <= F.lit(0), F.lit(3))
        .when(F.col("LineTotal") < F.lit(0), F.lit(2))
        .when(F.col("OrderQty") <= F.lit(0), F.lit(2))
        .otherwise(F.lit(0))
    )

    # SQL lines 658-682: Final projection  (mirrors INTO #Violations, SQL line 683)
    result = violations.select(
        F.col("SalesOrderID"),
        F.col("SalesOrderDetailID"),
        F.col("d_ProductID").alias("ProductID"),
        F.col("UnitPriceDiscount").alias("AppliedDiscountOnRecord"),
        max_discount.alias("MaxAllowedDiscount"),
        violation_type_col.alias("ViolationType"),
        severity_col.alias("Severity"),
        F.col("CategoryName"),
        F.col("TerritoryGroup"),
        F.col("OrderDate"),
    )

    return result


# =============================================================================
# Public API
# =============================================================================
def audit_pricing_violations(
    spark: SparkSession,
    run_id: str,
    start_date: date,
    end_date: date,
) -> tuple[DataFrame, int]:
    """Audit sales order lines for pricing rule violations.

    Direct PySpark translation of ``dbo.usp_AW19_AuditPricingViolations``
    (SQL lines 643-723).

    Args:
        spark: Active SparkSession.
        run_id: Pipeline run UUID (``@RunId UNIQUEIDENTIFIER``, SQL line 644).
        start_date: Inclusive start of OrderDate range (``@StartDate``, SQL line 645).
        end_date: Inclusive end of OrderDate range (``@EndDate``, SQL line 646).

    Returns:
        A two-element tuple ``(violations_df, violation_count)`` where:

        * ``violations_df`` — DataFrame of violating rows ordered by
          ``Severity DESC, OrderDate DESC`` (SQL lines 716-721).
        * ``violation_count`` — total number of violations
          (maps to ``@ViolationCount OUTPUT``, SQL lines 647 / 704).

    Note:
        ``@ViolationCount OUTPUT`` (SQL line 647) is returned as the second tuple
        element.  Callers must unpack::

            violations_df, count = audit_pricing_violations(spark, run_id, sd, ed)
    """
    # Enable strict decimal precision to match SQL Server DECIMAL arithmetic
    spark.conf.set("spark.sql.decimalOperations.allowPrecisionLoss", "false")

    # SQL lines 652-654 → Python variables
    proc_name: str = PROC_NAME

    # --- Step 1: joins + date filter (SQL lines 684-695) ---
    joined = _step1_load_and_join(spark, start_date, end_date)

    # --- Step 2: violation filter + projection (SQL lines 658-702) ---
    # SQL line 683: INTO #Violations → .cache() + .count() for eager materialization
    violations_df: DataFrame = _step2_compute_and_filter(joined).cache()

    # SQL line 704: SELECT @ViolationCount = COUNT(*) FROM #Violations
    # Single .count() call both materialises the cache and captures the count.
    violation_count: int = violations_df.count()

    # SQL lines 706-707: derive audit status / message
    audit_status: str = "WARN" if violation_count > 0 else "OK"
    audit_message: str = f"Violations found: {violation_count}"

    # SQL lines 709-714: EXEC dbo.usp_AW19_Log
    log_step(
        spark,
        run_id,
        proc_name,
        "AUDIT_VIOLATIONS",
        audit_status,
        audit_message,
        complete=True,
    )

    # SQL lines 716-721: SELECT … ORDER BY Severity DESC, OrderDate DESC
    #
    # Gotcha #3 — NULL ordering:
    #   SQL Server places NULLs LAST in DESC order.
    #   PySpark default for DESC is NULLs FIRST.
    #   Use .desc_nulls_last() on both sort columns to match SQL Server behaviour.
    ordered_df: DataFrame = violations_df.orderBy(
        F.col("Severity").desc_nulls_last(),
        F.col("OrderDate").desc_nulls_last(),
    )

    # Release the cached DataFrame now that violation_count is captured and
    # ordered_df has been materialised — prevents a memory resource leak.
    violations_df.unpersist()

    return ordered_df, violation_count


def run_pipeline(spark: SparkSession, params: dict) -> DataFrame:
    """Orchestration entry point — wraps ``audit_pricing_violations``.

    Args:
        spark: Active SparkSession.
        params: Dictionary with keys:

            * ``run_id`` (``str``) — pipeline run UUID.
            * ``start_date`` (``date``) — inclusive start date.
            * ``end_date`` (``date``) — inclusive end date.

    Returns:
        Ordered violations DataFrame.
    """
    violations_df, _violation_count = audit_pricing_violations(
        spark=spark,
        run_id=params["run_id"],
        start_date=params["start_date"],
        end_date=params["end_date"],
    )
    return violations_df


# =============================================================================
# CLI entry point
# =============================================================================
def main() -> None:
    """Argparse CLI for running the audit pipeline as a standalone script."""
    parser = argparse.ArgumentParser(
        description="Audit pricing violations in AdventureWorks sales orders."
    )
    parser.add_argument("--run-id", required=True, help="Pipeline run UUID")
    parser.add_argument(
        "--start-date",
        required=True,
        metavar="YYYY-MM-DD",
        help="Inclusive start date for OrderDate filter",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        metavar="YYYY-MM-DD",
        help="Inclusive end date for OrderDate filter",
    )
    parser.add_argument(
        "--output-path",
        default=None,
        help="Optional path to write violations as Parquet (omit to print to stdout)",
    )
    args = parser.parse_args()

    spark = (
        SparkSession.builder.appName("aw19_audit_pricing_violations").getOrCreate()
    )

    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)

    violations_df, violation_count = audit_pricing_violations(
        spark=spark,
        run_id=args.run_id,
        start_date=start,
        end_date=end,
    )

    print(f"Violation count: {violation_count}")

    if args.output_path:
        violations_df.write.mode("overwrite").parquet(args.output_path)
        print(f"Violations written to: {args.output_path}")
    else:
        violations_df.show(truncate=False)

    spark.stop()


if __name__ == "__main__":
    main()