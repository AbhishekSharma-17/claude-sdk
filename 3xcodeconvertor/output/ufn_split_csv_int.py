from __future__ import annotations

# =============================================================================
# Converted from: dbo.ufn_SplitCsvInt  (SQL lines 47-69)
# Source dialect: T-SQL  |  Complexity: Simple (score 1.25)
# Conversion date: 2026-03-30
#
# Original intent:
#   Table-valued function that accepts a CSV string of integers (comma, semi-
#   colon, CR, or LF separated) and returns each valid integer as a row.
#
# Conversion strategy:
#   • TABLE RETURN TYPE  → pure Python function returning list[int].
#     No PySpark UDF is used (Gotcha #8: UDFs are 50-100× slower than native).
#   • Scalar helper _is_int() replaces TRY_CONVERT(int, @token) (SQL line 63).
#   • A second, DataFrame-native overload split_csv_int_df() is provided for
#     inline use inside Spark pipelines (e.g. main proc lines 654-656).
# =============================================================================

import argparse
from typing import TYPE_CHECKING

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import ArrayType, IntegerType


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _is_int(s: str) -> bool:
    """Return True if *s* can be parsed as a Python int.

    Replaces T-SQL ``TRY_CONVERT(int, @token) IS NOT NULL`` (SQL line 63).

    Args:
        s: Stripped token string to test.

    Returns:
        True when ``int(s)`` succeeds, False on ValueError.
    """
    try:
        int(s)
        return True
    except ValueError:
        return False


# === Section 1: Scalar Python conversion (SQL lines 47-68) ===

def ufn_split_csv_int(csv: str | None) -> list[int]:
    """Parse a CSV string and return a list of valid integers.

    Pure Python equivalent of ``dbo.ufn_SplitCsvInt(@csv)``.  Called once
    with a scalar string — no UDF overhead, no Spark serialisation cost.

    Conversion notes:
        - SQL line 51: ``COALESCE(@csv, N'')``  →  ``csv_val = csv or ''``
        - SQL line 54: nested ``REPLACE(… CHAR(10) … CHAR(13) … ';' …)``
          → three chained ``str.replace()`` calls.
        - SQL line 55: trailing-comma ``WHILE`` loop  →  ``str.rstrip(',')``.
        - SQL lines 57-67: ``WHILE @pos <= LEN(@x)+1`` parse loop with
          ``CHARINDEX`` / ``SUBSTRING``  →  single list comprehension.

    Args:
        csv: Raw CSV string, e.g. ``"1,2;3\\n4"``.  May be None.

    Returns:
        Ordered list of integers parsed from *csv*; empty list if none found.

    Example:
        >>> ufn_split_csv_int("1, 2;3\\n 4\\r5,")
        [1, 2, 3, 4, 5]
    """
    # SQL line 51: COALESCE(@csv, N'')
    csv_val: str = csv or ""

    # SQL line 54: REPLACE(REPLACE(REPLACE(@x, CHAR(10), ','), CHAR(13), ','), ';', ',')
    x: str = (
        csv_val
        .replace("\n", ",")
        .replace("\r", ",")
        .replace(";", ",")
    )

    # SQL line 55: WHILE LEN(@x)>0 AND RIGHT(@x,1)=',' SET @x=LEFT(@x,LEN(@x)-1)
    x = x.rstrip(",")

    # SQL lines 57-67: WHILE loop with CHARINDEX/SUBSTRING + TRY_CONVERT guard
    # Replaced entirely by a list comprehension — no manual pointer arithmetic.
    return [
        int(tok.strip())
        for tok in x.split(",")
        if tok.strip() and _is_int(tok.strip())
    ]


# === Section 2: DataFrame-native overload (for Spark pipeline inline use) ===

def split_csv_int_df(
    spark: SparkSession,
    df: DataFrame,
    csv_col: str,
    output_col: str = "ItemInt",
) -> DataFrame:
    """Explode a CSV integer column into one integer row per value.

    DataFrame-native alternative to ``ufn_split_csv_int`` for use inside Spark
    pipelines (e.g. main proc lines 654-656).  Uses only native ``F.*``
    functions — no Python UDF, no ``collect()``.

    Pipeline:
        1. ``F.split()``    — tokenise on ``,``, ``\\n``, ``\\r``, or ``;``
        2. ``F.explode()``  — one row per token
        3. ``F.trim()``     — strip whitespace (matches SQL ``LTRIM/RTRIM``)
        4. ``.cast('int')`` — silently returns NULL for non-numeric tokens
        5. ``isNotNull()``  — filter out NULLs (matches ``TRY_CONVERT IS NOT NULL``)

    Args:
        spark:      Active SparkSession.
        df:         Input DataFrame containing *csv_col*.
        csv_col:    Name of the column holding the raw CSV string.
        output_col: Name for the resulting integer column (default: ``ItemInt``).

    Returns:
        DataFrame with all original columns replaced by *output_col* as ``IntegerType``.
    """
    return (
        df
        # Tokenise: split on comma, newline, carriage-return, or semicolon
        .withColumn(
            output_col,
            F.explode(
                F.split(F.col(csv_col), r"[,\n\r;]+")
            ),
        )
        # Trim whitespace, then cast to int (non-numeric → NULL)
        .withColumn(output_col, F.trim(F.col(output_col)).cast(IntegerType()))
        # Drop NULLs — mirrors TRY_CONVERT(int, @token) IS NOT NULL (SQL line 63)
        .filter(F.col(output_col).isNotNull())
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_pipeline(spark: SparkSession, params: dict) -> DataFrame:
    """Entry point for pipeline orchestration.

    Args:
        spark:  Active SparkSession.
        params: Runtime parameters.  Expected keys:
                  ``csv_col``    – column name holding raw CSV strings.
                  ``input_view`` – registered temp-view name to read from.

    Returns:
        DataFrame of parsed integers in column ``ItemInt``.
    """
    input_view: str = params["input_view"]
    csv_col: str = params.get("csv_col", "csv")

    df = spark.table(input_view)
    return split_csv_int_df(spark, df, csv_col=csv_col)


def main() -> None:
    """CLI entry point — parse arguments and run the pipeline."""
    parser = argparse.ArgumentParser(
        description="Split CSV-integer strings into individual integer rows."
    )
    parser.add_argument(
        "--input-view",
        required=True,
        help="Spark temporary view name containing the CSV column.",
    )
    parser.add_argument(
        "--csv-col",
        default="csv",
        help="Name of the CSV string column (default: csv).",
    )
    parser.add_argument(
        "--output-view",
        default="ufn_split_csv_int_out",
        help="Name to register the output DataFrame as a temp view.",
    )
    args = parser.parse_args()

    spark: SparkSession = (
        SparkSession.builder
        .appName("ufn_split_csv_int")
        .getOrCreate()
    )

    result: DataFrame = run_pipeline(
        spark,
        {"input_view": args.input_view, "csv_col": args.csv_col},
    )
    result.createOrReplaceTempView(args.output_view)
    result.show(truncate=False)


if __name__ == "__main__":
    main()
