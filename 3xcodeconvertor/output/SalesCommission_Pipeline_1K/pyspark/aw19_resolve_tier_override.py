from __future__ import annotations

# =============================================================================
# aw19_resolve_tier_override.py
#
# Converted from: dbo.usp_AW19_ResolveTierOverride  (SQL lines 608-637)
# Source dialect: T-SQL (SQL Server)
# Conversion date: 2026-03-30
#
# Original procedure:
#   - Accepted @CustomerID, @CurrentTier, and @ResolvedTier OUTPUT
#   - Looked up PersonType and Title from Person.Person
#   - Counted phone and email records for the customer
#   - Applied a CASE expression to determine the resolved tier
#
# Python equivalent:
#   - OUTPUT parameter @ResolvedTier → Python return value
#   - TODO: Call sites must be updated from
#       EXEC dbo.usp_AW19_ResolveTierOverride @cid, @tier, @resolved OUTPUT
#     to:
#       resolved = resolve_tier_override(spark, cid, tier)
# =============================================================================

import argparse

from pyspark.sql import SparkSession
import pyspark.sql.functions as F  # noqa: F401  (kept for future vectorised refactor)


# === Section 1: Tier-override resolver (SQL lines 608-637) ===

def resolve_tier_override(
    spark: SparkSession,
    customer_id: int,
    current_tier: str,
) -> str:
    """Resolve a customer's commission tier, applying override rules.

    Mirrors ``dbo.usp_AW19_ResolveTierOverride`` (SQL lines 608-637).

    The original procedure used an OUTPUT parameter (@ResolvedTier) to return
    the resolved tier.  In Python that becomes the function's return value.

    Args:
        spark: Active SparkSession used for table lookups.
        customer_id: BusinessEntityID of the customer (SQL: @CustomerID).
        current_tier: The tier currently assigned to the customer
            (SQL: @CurrentTier).  **Assumption**: upstream code always
            produces title-cased values ('Standard', 'Bronze', 'Silver',
            'Gold').  Mixed-case values will fall through to the ELSE branch
            (gotcha #2 — case-sensitive comparison risk).

    Returns:
        The resolved tier string.  If no override rule fires, returns
        ``current_tier`` unchanged.

    Limitations / TODOs:
        - TODO: Per-row Spark table reads (SQL lines 625-626) are efficient
          only for small lookup volumes.  If this function is called in a loop
          over many customers, rewrite as a vectorised join on a customer
          DataFrame to avoid O(N) Spark jobs.
        - OUTPUT parameter @ResolvedTier (SQL line 611) is now the return
          value; all T-SQL call sites using EXEC … @ResolvedTier OUTPUT must
          be updated.
    """

    # Gotcha #2 fix: normalise current_tier at entry so comparisons below are
    # equivalent to SQL Server CI_AS collation ('standard' == 'Standard', etc.).
    current_tier = current_tier.strip().title()

    # --- SQL lines 621-623 -----------------------------------------------
    # SELECT @PersonType = p.PersonType, @Title = p.Title
    # FROM Person.Person p WHERE p.BusinessEntityID = @CustomerID
    #
    # .first() returns None if no row matches — guard against that below.
    row = (
        spark.table("Person.Person")
        .where(F.col("BusinessEntityID") == customer_id)
        .select("PersonType", "Title")
        .first()
    )

    # Null guard: if the customer is not found, return current tier unchanged.
    # SQL Server would leave @PersonType / @Title as NULL and the CASE would
    # fall through to ELSE @CurrentTier anyway.
    if row is None:
        return current_tier

    # SQL lines 618-619: DECLARE @PersonType NCHAR(2); DECLARE @Title NVARCHAR(8)
    person_type: str | None = row["PersonType"]
    title: str | None = row["Title"]

    # --- SQL line 625 -------------------------------------------------------
    # SELECT @PhoneCount = COUNT(*) FROM Person.PersonPhone
    # WHERE BusinessEntityID = @CustomerID
    phone_count: int = (
        spark.table("Person.PersonPhone")
        .where(F.col("BusinessEntityID") == customer_id)
        .count()
    )

    # --- SQL line 626 -------------------------------------------------------
    # SELECT @EmailCount = COUNT(*) FROM Person.EmailAddress
    # WHERE BusinessEntityID = @CustomerID
    email_count: int = (
        spark.table("Person.EmailAddress")
        .where(F.col("BusinessEntityID") == customer_id)
        .count()
    )

    # --- SQL lines 628-636: CASE block on scalar variables ------------------
    # All comparisons operate on plain Python scalars, so we use an
    # if/elif/else chain — NOT F.when(), which is for column expressions.
    #
    # Gotcha #2 mitigations:
    #   - PersonType: normalised with .upper() to handle CI_AS collation
    #     equivalence (SQL Server treats 'sc' == 'SC'; Python does not).
    #   - Title: .strip() applied before set-membership test; titles are
    #     assumed standardised ('Mr.', 'Ms.', 'Mrs.', 'Dr.') — documented
    #     assumption, exact match is safe per conversion instructions.
    #   - current_tier: normalised with .strip().title() at function entry
    #     (see above) to handle CI_AS collation equivalence.

    resolved_tier: str

    if current_tier == "Standard" and phone_count >= 3 and email_count >= 2:
        # SQL line 630: Standard → Bronze when enough contact records exist
        resolved_tier = "Bronze"

    elif (
        current_tier == "Bronze"
        and (person_type or "").upper() == "SC"   # CI_AS normalisation
        and phone_count >= 2
    ):
        # SQL line 631: Bronze → Silver for store-contacts with phones
        resolved_tier = "Silver"

    elif (
        current_tier == "Silver"
        and (title or "").strip() in {"Mr.", "Ms.", "Mrs.", "Dr."}  # SQL line 632
        and email_count >= 3
    ):
        # SQL lines 632-633: Silver → Gold for titled customers with emails
        resolved_tier = "Gold"

    elif current_tier == "Gold" and phone_count == 0:
        # SQL line 634: Gold → Silver when customer has no phone records
        resolved_tier = "Silver"

    else:
        # SQL line 635: ELSE @CurrentTier — no override fires
        resolved_tier = current_tier

    return resolved_tier


# === Entry point ============================================================

def run_pipeline(spark: SparkSession, params: argparse.Namespace) -> str:
    """Entry point wrapper for CLI invocation.

    Args:
        spark: Active SparkSession.
        params: Parsed CLI arguments with ``customer_id`` and ``current_tier``.

    Returns:
        The resolved tier string.
    """
    return resolve_tier_override(
        spark=spark,
        customer_id=params.customer_id,
        current_tier=params.current_tier,
    )


def main() -> None:
    """CLI entry point — invoke the tier-override resolver for a single customer."""
    parser = argparse.ArgumentParser(
        description="Resolve commission tier override for a single customer."
    )
    parser.add_argument(
        "--customer-id",
        dest="customer_id",
        type=int,
        required=True,
        help="BusinessEntityID of the customer (SQL: @CustomerID).",
    )
    parser.add_argument(
        "--current-tier",
        dest="current_tier",
        type=str,
        required=True,
        help="Current tier string, e.g. 'Standard', 'Bronze', 'Silver', 'Gold'.",
    )
    parser.add_argument(
        "--app-name",
        dest="app_name",
        type=str,
        default="aw19_resolve_tier_override",
        help="Spark application name.",
    )
    args = parser.parse_args()

    spark = (
        SparkSession.builder
        .appName(args.app_name)
        .getOrCreate()
    )

    result = run_pipeline(spark, args)
    print(f"Resolved tier for customer {args.customer_id}: {result}")


if __name__ == "__main__":
    main()