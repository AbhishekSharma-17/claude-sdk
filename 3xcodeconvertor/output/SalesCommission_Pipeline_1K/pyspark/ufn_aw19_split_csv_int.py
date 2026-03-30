from __future__ import annotations

# =============================================================================
# ufn_aw19_split_csv_int.py
#
# Converted from: dbo.ufn_AW19_SplitCsvInt (T-SQL)
# Source lines  : 47-65  (SalesCommission_Pipeline_1K.sql)
# Dialect       : T-SQL → PySpark / plain Python
# Complexity    : Simple (score: 1.25)
#
# Design notes:
#   The original function's sole purpose is to parse a comma-separated string
#   of integers into a rowset.  The only caller (pipeline line 166) uses the
#   result to build a filter set via F.col('CustomerID').isin(...).
#   A plain Python list[int] is therefore sufficient — no DataFrame or UDF
#   is required, which avoids the 50-100x Python-UDF overhead entirely.
#
# TABLE variable @t eliminated — return Python list directly.
# =============================================================================

import argparse
import re
import sys


# === Section 1: CSV-to-integer parser (SQL lines 47-64) ===

def ufn_split_csv_int(csv_str: str | None) -> list[int]:
    """Parse a comma-separated string of integers into a Python list.

    Mirrors the behaviour of ``dbo.ufn_AW19_SplitCsvInt`` exactly:
    * ``NULL`` / ``None`` input is treated as an empty string
      (SQL line 51: ``COALESCE(@csv, N'')``)
    * CR and LF characters are stripped before splitting
      (SQL line 53: ``REPLACE(REPLACE(@x, CHAR(10), …), CHAR(13), …)``)
    * Each token is whitespace-trimmed
      (SQL line 58: ``LTRIM(RTRIM(…))``)
    * Non-numeric tokens are silently discarded — matches the
      ``TRY_CONVERT(INT, @token) IS NOT NULL`` guard on SQL line 59.
    * Negative integers are supported (``-`` prefix allowed).

    Args:
        csv_str: Comma-separated string of integer values, e.g. ``"1,2,3"``.
                 May contain ``\\r`` / ``\\n`` whitespace or be ``None``.

    Returns:
        Ordered list of parsed integers.  Empty list when input is
        ``None``, empty, or contains no valid integer tokens.

    Example — caller usage (pipeline line 166)::

        customer_ids = ufn_split_csv_int(params.customer_ids_csv)
        df_filtered  = df.filter(F.col("CustomerID").isin(customer_ids))
    """
    # SQL line 51: COALESCE(@csv, N'')
    csv_str = csv_str or ""

    # SQL line 53: strip CR / LF before splitting
    csv_str = re.sub(r"[\r\n]", "", csv_str)

    # SQL lines 54-62: WHILE loop replaced wholesale with a list comprehension.
    # TRY_CONVERT(INT, @token) IS NOT NULL  →  try/except ValueError
    # Silently discards non-numeric tokens (matches NULL-on-failure semantics).
    result: list[int] = []
    for token in csv_str.split(","):
        token = token.strip()           # SQL line 58: LTRIM/RTRIM
        if not token:                   # SQL line 59: @token <> N''
            continue
        try:
            result.append(int(token))   # SQL line 60: INSERT @t (Item)
        except ValueError:
            pass                        # TRY_CONVERT returns NULL → skip

    # SQL line 63: RETURN
    return result


# === Section 2: CLI entry-point (standalone testing) ===

def main() -> None:
    """Command-line entry point for ad-hoc testing."""
    parser = argparse.ArgumentParser(
        description="Parse a CSV string of integers (mirrors dbo.ufn_AW19_SplitCsvInt)."
    )
    parser.add_argument(
        "csv_string",
        nargs="?",
        default=None,
        help="Comma-separated integer string, e.g. '1,2,3'",
    )
    args = parser.parse_args()

    parsed = ufn_split_csv_int(args.csv_string)
    print(f"Parsed integers ({len(parsed)}): {parsed}")


if __name__ == "__main__":
    main()
