from __future__ import annotations

# stdlib
import argparse
import uuid
from datetime import datetime, timezone

# pyspark
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F  # noqa: F401  (available for callers)
from pyspark.sql.types import (
    StringType,
    StructField,
    StructType,
    TimestampType,
)

# =============================================================================
# === Section 1: Schema & Constants (SQL lines 28-40) ===
# =============================================================================

#: Delta table that receives every audit row.
#: Schema mirrors dbo.AWLT_Converter_RunLog with DATETIME2(3) → TimestampType().
RUNLOG_SCHEMA: StructType = StructType(
    [
        StructField("RunId", StringType(), False),        # @RunId uniqueidentifier → str
        StructField("ProcName", StringType(), False),     # @ProcName sysname → str
        StructField("StepName", StringType(), False),     # @StepName nvarchar(200)
        StructField("StepStatus", StringType(), False),   # @StepStatus nvarchar(30)
        StructField("Message", StringType(), True),       # @Message nvarchar(2000) = NULL
        StructField("StartedUtc", TimestampType(), False),  # SYSUTCDATETIME()
        StructField("CompletedUtc", TimestampType(), True), # CASE WHEN @Complete=1 …
    ]
)

RUNLOG_TABLE: str = "dbo.AWLT_Converter_RunLog"


# =============================================================================
# === Section 2: RunLogger class (SQL lines 28-40) ===
# =============================================================================


class RunLogger:
    """Audit logger that appends step records to the AWLT_Converter_RunLog Delta table.

    Mirrors the T-SQL stored procedure ``dbo.usp_AWLT_Converter_Log``
    (SQL lines 28-40).  Any Delta write failure is caught and printed so that
    logging errors **never** crash the main pipeline.

    Args:
        spark: Active ``SparkSession``.
        run_id: UUID string identifying the current pipeline run.
                Maps to ``@RunId uniqueidentifier``; pass ``str(uuid.uuid4())``
                at pipeline startup and reuse throughout.
        proc_name: Name of the calling procedure / pipeline.
                   Maps to ``@ProcName sysname``.

    Example::

        logger = RunLogger(spark, run_id=str(uuid.uuid4()), proc_name="MyProc")
        logger.log_step("ExtractRaw", "Started")
        # … do work …
        logger.log_step("ExtractRaw", "Success", complete=True)
    """

    def __init__(self, spark: SparkSession, run_id: str, proc_name: str) -> None:
        self._spark = spark
        self._run_id = run_id
        self._proc_name = proc_name

    # ------------------------------------------------------------------
    def log_step(
        self,
        step_name: str,
        step_status: str,
        message: str | None = None,
        complete: bool = False,
    ) -> None:
        """Append one audit row to ``dbo.AWLT_Converter_RunLog``.

        SQL lines 39-40::

            INSERT dbo.AWLT_Converter_RunLog(
                RunId, ProcName, StepName, StepStatus, Message, CompletedUtc)
            VALUES (
                @RunId, @ProcName, @StepName, @StepStatus, @Message,
                CASE WHEN @Complete = 1 THEN SYSUTCDATETIME() ELSE NULL END
            );

        Note: ``StartedUtc`` is always populated with the current UTC timestamp
        (``SYSUTCDATETIME()`` equivalent) even though the original INSERT list
        omitted it — the column is non-nullable in the schema.

        Args:
            step_name: Name of the pipeline step being logged (max 200 chars).
                       Maps to ``@StepName nvarchar(200)``.
            step_status: Status of the step, e.g. "Started", "Success", "Failed"
                         (max 30 chars).  Maps to ``@StepStatus nvarchar(30)``.
            message: Optional free-text detail (max 2000 chars).
                     Maps to ``@Message nvarchar(2000) = NULL``.
            complete: ``True`` when the step has finished successfully.
                      Drives ``CompletedUtc``; mirrors ``@Complete bit = 0``.

        Gotcha #10 — BIT is 3-valued in SQL Server (0 / 1 / NULL).
        The default is 0, so NULL is unlikely, but we guard explicitly::

            complete = complete if complete is not None else False
        """
        # Gotcha #10: guard against None being passed explicitly at call site
        complete = complete if complete is not None else False

        # SQL line 40: SYSUTCDATETIME() → datetime.now(timezone.utc)
        started_utc: datetime = datetime.now(timezone.utc)

        # SQL line 40: CASE WHEN @Complete=1 THEN SYSUTCDATETIME() ELSE NULL END
        completed_utc: datetime | None = started_utc if complete else None

        row = [
            {
                "RunId": self._run_id,
                "ProcName": self._proc_name,
                "StepName": step_name,
                "StepStatus": step_status,
                "Message": message,
                "StartedUtc": started_utc,
                "CompletedUtc": completed_utc,
            }
        ]

        # Add try/except: logging must not crash the main pipeline
        try:
            log_df: DataFrame = self._spark.createDataFrame(row, schema=RUNLOG_SCHEMA)
            (
                log_df.write
                .format("delta")
                .mode("append")
                .saveAsTable(RUNLOG_TABLE)
            )
        except Exception as exc:  # noqa: BLE001
            # Intentionally swallowed — audit logging is best-effort
            print(
                f"[RunLogger] WARNING: failed to write audit row to "
                f"'{RUNLOG_TABLE}' — {type(exc).__name__}: {exc}"
            )


# =============================================================================
# === Section 3: Pipeline Entry Point ===
# =============================================================================


def _step1_build_logger(
    spark: SparkSession,
    run_id: str,
    proc_name: str,
) -> RunLogger:
    """Instantiate the audit logger for the current run.

    SQL lines 28-35: parameter mapping.

    Args:
        spark: Active SparkSession.
        run_id: UUID string for this run (maps to ``@RunId uniqueidentifier``).
        proc_name: Calling procedure name (maps to ``@ProcName sysname``).

    Returns:
        Configured ``RunLogger`` ready for ``log_step()`` calls.
    """
    return RunLogger(spark=spark, run_id=run_id, proc_name=proc_name)


def run_pipeline(spark: SparkSession, params: dict) -> DataFrame:
    """Pipeline entry point — writes a single audit row and returns an empty DataFrame.

    This procedure is logging-only; it produces no result set, so the returned
    DataFrame is always empty.

    Args:
        spark: Active ``SparkSession``.
        params: Runtime parameter dict.  Recognised keys:

            * ``run_id`` (str, optional): UUID for this run.
              Defaults to a fresh ``str(uuid.uuid4())``.
            * ``proc_name`` (str, **required**): Calling procedure name.
            * ``step_name`` (str, **required**): Step being logged.
            * ``step_status`` (str, **required**): Step status.
            * ``message`` (str | None, optional): Detail message.
            * ``complete`` (bool, optional): Whether the step is complete.

    Returns:
        Empty ``DataFrame`` (this procedure is logging-only).
    """
    run_id: str = params.get("run_id") or str(uuid.uuid4())
    proc_name: str = params["proc_name"]

    logger = _step1_build_logger(spark=spark, run_id=run_id, proc_name=proc_name)

    # Emit the audit row — mirrors the INSERT at SQL lines 39-40.
    # Called at SQL lines 635, 948, 1012 of the main procedure as well.
    logger.log_step(
        step_name=params.get("step_name", ""),
        step_status=params.get("step_status", ""),
        message=params.get("message"),
        complete=bool(params.get("complete", False)),
    )

    # No result set — return an empty DataFrame
    return spark.createDataFrame([], schema=StructType([]))


# =============================================================================
# === Section 4: CLI Entry Point ===
# =============================================================================


def main() -> None:
    """CLI entry point for standalone invocation of the audit logger."""
    parser = argparse.ArgumentParser(
        prog="usp_awlt_converter_log",
        description=(
            "PySpark equivalent of dbo.usp_AWLT_Converter_Log — "
            "appends one audit row to dbo.AWLT_Converter_RunLog."
        ),
    )
    parser.add_argument(
        "--run-id",
        dest="run_id",
        default=str(uuid.uuid4()),
        help="Pipeline run UUID  (default: new UUID)",
    )
    parser.add_argument(
        "--proc-name",
        dest="proc_name",
        required=True,
        help="Calling procedure / pipeline name  (@ProcName sysname)",
    )
    parser.add_argument(
        "--step-name",
        dest="step_name",
        required=True,
        help="Step name, max 200 chars  (@StepName nvarchar(200))",
    )
    parser.add_argument(
        "--step-status",
        dest="step_status",
        required=True,
        help="Step status, max 30 chars  (@StepStatus nvarchar(30))",
    )
    parser.add_argument(
        "--message",
        dest="message",
        default=None,
        help="Optional detail message, max 2000 chars  (@Message nvarchar(2000))",
    )
    parser.add_argument(
        "--complete",
        dest="complete",
        action="store_true",
        default=False,
        help="Flag: step is complete → sets CompletedUtc  (@Complete bit = 0)",
    )

    args = parser.parse_args()

    spark = (
        SparkSession.builder
        .appName("usp_AWLT_Converter_Log")
        .getOrCreate()
    )
    run_pipeline(spark, vars(args))


if __name__ == "__main__":
    main()
