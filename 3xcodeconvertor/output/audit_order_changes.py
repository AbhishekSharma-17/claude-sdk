from __future__ import annotations

import argparse
from typing import Optional

from pyspark.sql import DataFrame, SparkSession
import pyspark.sql.functions as F


# =============================================================================
# Converted from: dbo.trg_AuditOrderChanges (SQL lines 486-552)
# Source dialect: T-SQL
#
# TODO: Triggers have no direct PySpark equivalent. This function should be
#       called as a post-write audit step after any Orders DataFrame update.
#       For production audit trails, consider Delta Lake Change Data Feed (CDF).
#
# TODO: The SQL trigger uses `inserted` and `deleted` pseudo-tables. Here they
#       are replaced by old_df (before snapshot) and new_df (after snapshot).
#
# TODO: SYSTEM_USER is replaced by spark_user parameter. In production, use
#       spark.sparkContext.sparkUser() or pass the authenticated username.
# =============================================================================


def _step1_audit_order_status(
    old_df: DataFrame,
    new_df: DataFrame,
    spark_user: str,
) -> DataFrame:
    """Detect OrderStatus changes and produce audit records.

    Corresponds to SQL lines 502-511:
        SELECT i.OrderID, 'OrderStatus', d.OrderStatus, i.OrderStatus,
               GETDATE(), SYSTEM_USER
        FROM inserted i INNER JOIN deleted d ON i.OrderID = d.OrderID
        WHERE i.OrderStatus <> d.OrderStatus

    Note – GOTCHA #2: String comparison is case-sensitive in PySpark,
    which matches the SQL Server default collation behaviour here.

    Args:
        old_df: The "deleted" (before-update) snapshot of Orders.
        new_df: The "inserted" (after-update) snapshot of Orders.
        spark_user: Username to record as ChangedBy.

    Returns:
        DataFrame with audit log schema for OrderStatus changes.
    """
    return (
        new_df.alias("i")
        .join(old_df.alias("d"), on=F.col("i.OrderID") == F.col("d.OrderID"), how="inner")
        .where(F.col("i.OrderStatus") != F.col("d.OrderStatus"))
        .select(
            F.col("i.OrderID").alias("OrderID"),
            F.lit("OrderStatus").alias("FieldChanged"),
            F.col("d.OrderStatus").alias("OldValue"),
            F.col("i.OrderStatus").alias("NewValue"),
            F.current_timestamp().alias("ChangedAt"),
            F.lit(spark_user).alias("ChangedBy"),
        )
    )


def _step2_audit_shipped_date(
    old_df: DataFrame,
    new_df: DataFrame,
    spark_user: str,
) -> DataFrame:
    """Detect ShippedDate changes and produce audit records.

    Corresponds to SQL lines 522-531:
        SELECT i.OrderID, 'ShippedDate', CAST(d.ShippedDate AS VARCHAR(30)),
               CAST(i.ShippedDate AS VARCHAR(30)), GETDATE(), SYSTEM_USER
        FROM inserted i INNER JOIN deleted d ON i.OrderID = d.OrderID
        WHERE ISNULL(i.ShippedDate, '1900-01-01') <> ISNULL(d.ShippedDate, '1900-01-01')

    GOTCHA #10: ShippedDate may be NULL. The SQL uses ISNULL with a sentinel
    date for safe comparison. We use eqNullSafe (~) for cleaner NULL handling.

    Args:
        old_df: The "deleted" (before-update) snapshot of Orders.
        new_df: The "inserted" (after-update) snapshot of Orders.
        spark_user: Username to record as ChangedBy.

    Returns:
        DataFrame with audit log schema for ShippedDate changes.
    """
    return (
        new_df.alias("i")
        .join(old_df.alias("d"), on=F.col("i.OrderID") == F.col("d.OrderID"), how="inner")
        .where(~F.col("i.ShippedDate").eqNullSafe(F.col("d.ShippedDate")))
        .select(
            F.col("i.OrderID").alias("OrderID"),
            F.lit("ShippedDate").alias("FieldChanged"),
            F.col("d.ShippedDate").cast("string").alias("OldValue"),
            F.col("i.ShippedDate").cast("string").alias("NewValue"),
            F.current_timestamp().alias("ChangedAt"),
            F.lit(spark_user).alias("ChangedBy"),
        )
    )


def _step3_audit_total_amount(
    old_df: DataFrame,
    new_df: DataFrame,
    spark_user: str,
) -> DataFrame:
    """Detect TotalAmount changes and produce audit records.

    Corresponds to SQL lines 542-551:
        SELECT i.OrderID, 'TotalAmount', CAST(d.TotalAmount AS VARCHAR(30)),
               CAST(i.TotalAmount AS VARCHAR(30)), GETDATE(), SYSTEM_USER
        FROM inserted i INNER JOIN deleted d ON i.OrderID = d.OrderID
        WHERE i.TotalAmount <> d.TotalAmount

    Args:
        old_df: The "deleted" (before-update) snapshot of Orders.
        new_df: The "inserted" (after-update) snapshot of Orders.
        spark_user: Username to record as ChangedBy.

    Returns:
        DataFrame with audit log schema for TotalAmount changes.
    """
    return (
        new_df.alias("i")
        .join(old_df.alias("d"), on=F.col("i.OrderID") == F.col("d.OrderID"), how="inner")
        .where(F.col("i.TotalAmount") != F.col("d.TotalAmount"))
        .select(
            F.col("i.OrderID").alias("OrderID"),
            F.lit("TotalAmount").alias("FieldChanged"),
            F.col("d.TotalAmount").cast("string").alias("OldValue"),
            F.col("i.TotalAmount").cast("string").alias("NewValue"),
            F.current_timestamp().alias("ChangedAt"),
            F.lit(spark_user).alias("ChangedBy"),
        )
    )


def audit_order_changes(
    old_df: DataFrame,
    new_df: DataFrame,
    spark_user: Optional[str] = None,
    spark: Optional[SparkSession] = None,
) -> DataFrame:
    """Compare two Orders snapshots and return a unified audit log DataFrame.

    This is the PySpark equivalent of SQL Server trigger
    ``dbo.trg_AuditOrderChanges`` (SQL lines 486-552). It should be called
    after any update to the Orders table/DataFrame.

    Args:
        old_df: The before-update snapshot of dbo.Orders.
        new_df: The after-update snapshot of dbo.Orders.
        spark_user: Username recorded as ChangedBy. If None, falls back to
            ``spark.sparkContext.sparkUser()``.
        spark: SparkSession, required when *spark_user* is not provided.

    Returns:
        DataFrame matching the dbo.OrderAuditLog schema:
        (OrderID, FieldChanged, OldValue, NewValue, ChangedAt, ChangedBy).
    """
    # Resolve the user identifier (replaces SYSTEM_USER)
    if spark_user is None:
        if spark is None:
            spark = SparkSession.getActiveSession()  # type: ignore[union-attr]
            if spark is None:
                raise ValueError(
                    "spark_user must be provided or an active SparkSession must exist"
                )
        spark_user = spark.sparkContext.sparkUser()

    # === Section 1: OrderStatus changes (SQL lines 502-511) ===
    status_audit = _step1_audit_order_status(old_df, new_df, spark_user)

    # === Section 2: ShippedDate changes (SQL lines 522-531) ===
    shipped_audit = _step2_audit_shipped_date(old_df, new_df, spark_user)

    # === Section 3: TotalAmount changes (SQL lines 542-551) ===
    amount_audit = _step3_audit_total_amount(old_df, new_df, spark_user)

    # Combine all audit records into a single DataFrame
    return status_audit.unionAll(shipped_audit).unionAll(amount_audit)


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def run_pipeline(
    spark: SparkSession,
    params: argparse.Namespace,
) -> DataFrame:
    """Entry point for the audit-order-changes pipeline.

    Reads old and new snapshots of dbo.Orders and produces the audit log.

    Args:
        spark: Active SparkSession.
        params: CLI arguments with ``old_table``, ``new_table``, ``output_table``,
            and optional ``spark_user``.

    Returns:
        The combined audit log DataFrame.
    """
    old_df: DataFrame = spark.table(params.old_table)
    new_df: DataFrame = spark.table(params.new_table)

    audit_df: DataFrame = audit_order_changes(
        old_df=old_df,
        new_df=new_df,
        spark_user=params.spark_user,
        spark=spark,
    )

    if params.output_table:
        audit_df.write.mode("append").saveAsTable(params.output_table)

    return audit_df


def main() -> None:
    """CLI entry point with argparse."""
    parser = argparse.ArgumentParser(
        description="Audit order changes — PySpark equivalent of dbo.trg_AuditOrderChanges"
    )
    parser.add_argument(
        "--old-table",
        required=True,
        help="Fully-qualified name of the before-update Orders snapshot table",
    )
    parser.add_argument(
        "--new-table",
        required=True,
        help="Fully-qualified name of the after-update Orders snapshot table",
    )
    parser.add_argument(
        "--output-table",
        default=None,
        help="Target table name for the audit log (appended). If omitted, results are returned only.",
    )
    parser.add_argument(
        "--spark-user",
        default=None,
        help="Username to record as ChangedBy. Defaults to sparkContext.sparkUser().",
    )
    args = parser.parse_args()

    spark = SparkSession.builder.appName("audit_order_changes").getOrCreate()
    result = run_pipeline(spark, args)
    result.show(truncate=False)


if __name__ == "__main__":
    main()
