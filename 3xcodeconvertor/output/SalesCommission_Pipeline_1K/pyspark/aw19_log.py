from __future__ import annotations

# =============================================================================
# aw19_log.py
#
# Converted from: dbo.usp_AW19_Log  (SQL lines 28-42)
# Source dialect: T-SQL
# Target:         PySpark / Delta Lake
#
# Original procedure wrote a single audit row to dbo.AW19_RunLog.
# This module provides:
#   - _ensure_log_table(spark)  – idempotent DDL bootstrap
#   - log_step(...)             – standalone function (single call-site use)
#   - RunLogger                 – class that holds (spark, run_id, proc_name)
#                                 so the 12 call-sites in the main pipeline
#                                 don't repeat those args on every call
# =============================================================================

import argparse
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from pyspark.sql import SparkSession
from pyspark.sql.types import BooleanType, StringType, StructField, StructType, TimestampType


# ---------------------------------------------------------------------------
# Schema for dbo.AW19_RunLog
# ---------------------------------------------------------------------------

_LOG_TABLE = "dbo.AW19_RunLog"

_LOG_SCHEMA = StructType(
    [
        StructField("RunId", StringType(), nullable=False),       # UNIQUEIDENTIFIER → str
        StructField("ProcName", StringType(), nullable=False),    # SYSNAME → str (no length enforced)
        StructField("StepName", StringType(), nullable=False),    # NVARCHAR(200)
        StructField("StepStatus", StringType(), nullable=False),  # NVARCHAR(30)
        StructField("Message", StringType(), nullable=True),      # NVARCHAR(2000), default NULL
        StructField("StartedUtc", TimestampType(), nullable=False),
        StructField("CompletedUtc", TimestampType(), nullable=True),
        # TODO: Add any additional columns defined in dbo.AW19_RunLog DDL (lines 10-22)
        #       once that table is pre-created as a Delta table.
    ]
)


# ---------------------------------------------------------------------------
# Bootstrap helper
# ---------------------------------------------------------------------------

def _ensure_log_table(spark: SparkSession) -> None:
    """Create dbo.AW19_RunLog as a Delta table if it does not yet exist.

    Args:
        spark: Active SparkSession.

    Note:
        The original DDL (SQL lines 10-22) must be reviewed and any extra
        columns / constraints added here before running the pipeline for the
        first time.

        TODO: Verify the full DDL from SQL lines 10-22 and extend the
              CREATE TABLE statement below to match all columns/constraints.
    """
    spark.sql(
        f"""
        CREATE TABLE IF NOT EXISTS {_LOG_TABLE} (
            RunId        STRING    NOT NULL,
            ProcName     STRING    NOT NULL,
            StepName     STRING    NOT NULL,
            StepStatus   STRING    NOT NULL,
            Message      STRING,
            StartedUtc   TIMESTAMP NOT NULL,
            CompletedUtc TIMESTAMP
        )
        USING DELTA
        """
    )


# ---------------------------------------------------------------------------
# Dataclass (mirrors procedure signature, SQL lines 28-34)
# ---------------------------------------------------------------------------

@dataclass
class RunLogEntry:
    """Mirrors the parameter list of dbo.usp_AW19_Log (SQL lines 29-34).

    Attributes:
        run_id:      UUID string for the pipeline run (SQL: @RunId UNIQUEIDENTIFIER).
                     Generate at pipeline start with ``str(uuid.uuid4())``.
        proc_name:   Calling procedure name (SQL: @ProcName SYSNAME → plain str;
                     no length constraint enforced in PySpark).
        step_name:   Human-readable step label (SQL: @StepName NVARCHAR(200)).
        step_status: Status token, e.g. "START" / "END" (SQL: @StepStatus NVARCHAR(30)).
        message:     Optional detail message (SQL: @Message NVARCHAR(2000) = NULL).
        complete:    Whether this row marks step completion
                     (SQL: @Complete BIT = 0 → Python bool, default False).

    Note on BIT / NULL (Gotcha #10):
        @Complete BIT defaults to 0 (not NULL) in T-SQL, so mapping directly to
        Python bool is safe here.  If a NULL could ever be passed by a caller,
        normalise with: ``complete = bool(complete) if complete is not None else False``
    """

    run_id: str
    proc_name: str
    step_name: str
    step_status: str
    message: Optional[str] = None
    complete: bool = False


# ---------------------------------------------------------------------------
# === Section 1: Log-step writer (SQL lines 38-40) ===
# ---------------------------------------------------------------------------

def log_step(
    spark: SparkSession,
    run_id: str,
    proc_name: str,
    step_name: str,
    step_status: str,
    message: Optional[str] = None,
    complete: bool = False,
) -> None:
    """Append a single audit row to dbo.AW19_RunLog.

    Converts the T-SQL ``INSERT dbo.AW19_RunLog (...)  VALUES (...)`` at
    SQL lines 38-40 into a single-row DataFrame append to the Delta table.

    Args:
        spark:       Active SparkSession.
        run_id:      Pipeline run UUID (SQL: @RunId UNIQUEIDENTIFIER).
        proc_name:   Calling procedure name (SQL: @ProcName SYSNAME).
        step_name:   Step label (SQL: @StepName NVARCHAR(200)).
        step_status: Status token (SQL: @StepStatus NVARCHAR(30)).
        message:     Optional detail (SQL: @Message NVARCHAR(2000) = NULL).
        complete:    Marks step completion (SQL: @Complete BIT = 0).

    Note:
        ``StartedUtc`` always uses ``datetime.now(timezone.utc)`` — equivalent
        to T-SQL ``SYSUTCDATETIME()``.  This runs in driver context so we use
        Python stdlib, not ``F.current_timestamp()``.

        ``CompletedUtc`` mirrors the CASE expression at SQL line 40:
        ``CASE WHEN @Complete = 1 THEN SYSUTCDATETIME() ELSE NULL END``
        → Python ternary: ``datetime.now(timezone.utc) if complete else None``
    """
    now_utc: datetime = datetime.now(timezone.utc)

    # SQL line 39: StartedUtc = SYSUTCDATETIME()
    started_utc: datetime = now_utc

    # SQL line 40: CASE WHEN @Complete = 1 THEN SYSUTCDATETIME() ELSE NULL END
    completed_utc: Optional[datetime] = now_utc if complete else None

    row_dict = {
        "RunId": run_id,          # SQL line 38 col 1
        "ProcName": proc_name,    # SQL line 38 col 2
        "StepName": step_name,    # SQL line 38 col 3
        "StepStatus": step_status,# SQL line 38 col 4
        "Message": message,       # SQL line 38 col 5
        "StartedUtc": started_utc,
        "CompletedUtc": completed_utc,
    }

    # Single-row DataFrame → Delta append (replaces T-SQL INSERT at lines 38-40)
    (
        spark.createDataFrame([row_dict], schema=_LOG_SCHEMA)
        .write.format("delta")
        .mode("append")
        .saveAsTable(_LOG_TABLE)
    )


# ---------------------------------------------------------------------------
# RunLogger convenience class
# ---------------------------------------------------------------------------

class RunLogger:
    """Convenience wrapper around log_step() for the main pipeline.

    Holds (spark, run_id, proc_name) so that the 12 call-sites in the main
    pipeline only need to supply (step_name, step_status, ...).

    Example::

        logger = RunLogger(spark, run_id=str(uuid.uuid4()), proc_name="usp_Main")
        logger.log("ExtractSales", "START")
        ...
        logger.log("ExtractSales", "END", complete=True)
    """

    def __init__(self, spark: SparkSession, run_id: str, proc_name: str) -> None:
        """Initialise the logger.

        Args:
            spark:     Active SparkSession.
            run_id:    Pipeline run UUID; generate with ``str(uuid.uuid4())``.
            proc_name: Name of the owning procedure / pipeline.
        """
        self.spark = spark
        self.run_id = run_id
        self.proc_name = proc_name

    def log(
        self,
        step_name: str,
        step_status: str,
        message: Optional[str] = None,
        complete: bool = False,
    ) -> None:
        """Append one audit row for this run.

        Args:
            step_name:   Step label.
            step_status: Status token, e.g. ``"START"`` / ``"END"`` / ``"ERROR"``.
            message:     Optional detail message.
            complete:    Pass ``True`` to set CompletedUtc (mirrors @Complete BIT).
        """
        log_step(
            spark=self.spark,
            run_id=self.run_id,
            proc_name=self.proc_name,
            step_name=step_name,
            step_status=step_status,
            message=message,
            complete=complete,
        )


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def run_pipeline(spark: SparkSession, params: argparse.Namespace) -> None:
    """Bootstrap the log table and emit a test entry.

    Args:
        spark:  Active SparkSession.
        params: Parsed CLI args (run_id, proc_name, step_name, step_status,
                message, complete).
    """
    _ensure_log_table(spark)

    run_id: str = params.run_id or str(uuid.uuid4())
    logger = RunLogger(spark=spark, run_id=run_id, proc_name=params.proc_name)
    logger.log(
        step_name=params.step_name,
        step_status=params.step_status,
        message=params.message or None,
        complete=params.complete,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Command-line entry point for standalone execution / testing."""
    parser = argparse.ArgumentParser(
        description="Write a single audit row to dbo.AW19_RunLog (Delta)."
    )
    parser.add_argument("--run-id", dest="run_id", default="",
                        help="Pipeline run UUID (auto-generated if omitted).")
    parser.add_argument("--proc-name", dest="proc_name", required=True,
                        help="Owning procedure/pipeline name.")
    parser.add_argument("--step-name", dest="step_name", required=True,
                        help="Step label.")
    parser.add_argument("--step-status", dest="step_status", required=True,
                        help="Status token, e.g. START / END / ERROR.")
    parser.add_argument("--message", dest="message", default="",
                        help="Optional detail message.")
    parser.add_argument("--complete", dest="complete", action="store_true",
                        default=False,
                        help="Set CompletedUtc (mirrors @Complete BIT = 1).")
    args = parser.parse_args()

    spark = (
        SparkSession.builder
        .appName("aw19_log")
        .getOrCreate()
    )
    run_pipeline(spark, args)
    spark.stop()


if __name__ == "__main__":
    main()
