# PySpark Output Style Guide

Follow these conventions when generating PySpark conversion output.

---

## File Structure

```python
"""PySpark conversion of {source_file} ({N} lines T-SQL -> single Python file).

Source:  scripts/input/{source_file}
Target:  {brief description of what the SQL does}

SQL construct mapping:
  {list key construct mappings used}

Usage:
    spark-submit scripts/output/{output_file} [OPTIONS]
"""

from __future__ import annotations         # ALWAYS first import

import argparse                            # stdlib imports
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import IntEnum, StrEnum
from typing import Callable

from pyspark.sql import DataFrame, SparkSession, Window       # PySpark imports
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DecimalType, IntegerType, StringType, StructField, StructType,
)
```

---

## Section Comments

Use section comments to map back to SQL line numbers:

```python
# =============================================================================
# Section N: Description
# Replaces: SQL object name  (SQL lines X-Y)
# =============================================================================
```

---

## Naming Conventions

- Pipeline step functions: `_step{N}_{description}()`
- Helper functions: `_helper_name()`
- Entry point: `run_pipeline(spark, params)`
- CLI: `main()` at bottom with `if __name__ == "__main__": main()`
- Dataclass for params: `PipelineParams`
- Logger: `RunLogger` class pattern

---

## DataFrame Patterns

### Temp Table Simulation
```python
# Mirrors: SELECT ... INTO #TempName (SQL lines X-Y)
# Mirrors: CREATE CLUSTERED INDEX CX ON #TempName(col)
df = (
    source_df
    .select(...)
    .where(...)
).repartition("partition_col").cache()
df.count()  # force materialization
```

### Always use F. prefix
```python
# GOOD
F.col("x"), F.lit(0), F.sum("col"), F.when(...), F.coalesce(...)

# BAD -- never use bare function names
col("x"), lit(0), sum("col")
```

### Safe Division
```python
# Mirrors: NULLIF(x, 0) in denominator
def _nullif_zero(expr: F.Column) -> F.Column:
    return F.when(expr == 0, F.lit(None).cast(DecimalType(19, 4))).otherwise(expr)

result = numerator / _nullif_zero(denominator)
```

### Window Functions
```python
window = Window.partitionBy("group_col").orderBy(F.col("sort_col").desc())
df = df.withColumn("rank", F.row_number().over(window))
```

### Explicit Window Frames for Running Totals
```python
# ALWAYS specify rowsBetween for ordered window aggregations
running_sum_window = (
    Window.partitionBy("group_col")
    .orderBy("date_col")
    .rowsBetween(Window.unboundedPreceding, Window.currentRow)
)
df = df.withColumn("running_total", F.sum("amount").over(running_sum_window))
```

---

## Performance Patterns

### Broadcast Joins
```python
# Use broadcast() for dimension tables under ~100MB
from pyspark.sql.functions import broadcast

result = large_df.join(broadcast(dim_df), on="key", how="left")
```

### Column Pruning (Select Early)
```python
# GOOD: select only needed columns BEFORE join
orders = raw_orders.select("order_id", "customer_id", "amount")
customers = raw_customers.select("customer_id", "name", "region")
result = orders.join(customers, on="customer_id")

# BAD: join full tables, then select
result = raw_orders.join(raw_customers, on="customer_id").select(...)
```

### Predicate Pushdown (Filter Early)
```python
# GOOD: filter BEFORE groupBy/join
filtered = df.where(F.col("status") == "active").where(F.col("date") >= "2024-01-01")
result = filtered.groupBy("region").agg(F.sum("amount").alias("total"))

# BAD: aggregate then filter
result = df.groupBy("region", "status").agg(...).where(F.col("status") == "active")
```

### Caching Strategy
```python
# Cache: reused 2+ times AND fits in memory (<1GB)
base_df = spark.table("orders").where(...).cache()
base_df.count()  # force materialization

summary_a = base_df.groupBy("region").agg(...)
summary_b = base_df.groupBy("product").agg(...)

base_df.unpersist()  # release when done

# Persist to disk: reused 2+ times AND >1GB
from pyspark import StorageLevel
big_df = spark.table("events").where(...).persist(StorageLevel.MEMORY_AND_DISK)
```

### AQE Configuration
```python
# Enable Adaptive Query Execution (Spark 3.0+)
spark = (
    SparkSession.builder
    .appName("pipeline")
    .config("spark.sql.adaptive.enabled", "true")
    .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
    .config("spark.sql.adaptive.skewJoin.enabled", "true")
    .config("spark.sql.decimalOperations.allowPrecisionLoss", "false")
    .getOrCreate()
)
```

---

## Anti-Patterns to Avoid

### Never use Python UDFs when native functions exist
```python
# BAD: 50-100x slower than native functions
@F.udf(returnType=StringType())
def upper_udf(s):
    return s.upper() if s else None
df = df.withColumn("name", upper_udf("name"))

# GOOD: use native F.xxx
df = df.withColumn("name", F.upper("name"))
```

### Never collect() on large DataFrames
```python
# BAD: pulls all data to driver, OOM risk
all_rows = df.collect()
for row in all_rows: ...

# GOOD: use toLocalIterator() if row-by-row needed
for row in df.toLocalIterator(): ...

# BEST: stay in DataFrame API (vectorized)
result = df.withColumn("new_col", F.when(...).otherwise(...))
```

### Never coalesce(1) on large data
```python
# BAD: single-file bottleneck, kills parallelism
df.coalesce(1).write.parquet("output/")

# GOOD: let Spark decide partition count
df.write.parquet("output/")
```

### Never call count() multiple times
```python
# BAD: each .count() triggers full computation
if df.count() > 0:
    total = df.count()

# GOOD: compute once
total = df.count()
if total > 0: ...
```

### Avoid missing join conditions (accidental cross join)
```python
# BAD: this is a cross join in disguise
result = df1.join(df2)

# GOOD: always specify join condition
result = df1.join(df2, on="key", how="inner")
```

---

## Type Hints

- Use Python 3.12+ style: `str | None` not `Optional[str]`
- Use `from __future__ import annotations` at the top
- Type all function parameters and return values
- Use `DataFrame` for PySpark DataFrames

---

## Docstrings

Google-style with SQL line reference:

```python
def _step2_base_orders(spark: SparkSession, ...) -> DataFrame:
    """Step 2 -- base orders in date range (SQL lines 663-684).

    Replaces:  SELECT ... INTO #Orders FROM SalesLT.SalesOrderHeader h
               LEFT JOIN SalesLT.Address a ...
    """
```

---

## Error Handling

```python
try:
    # pipeline steps
    logger.log_step("END", "SUCCESS", "Completed", complete=True)
    return result
except Exception as exc:
    logger.log_step("END", "FAIL", str(exc), complete=True)
    raise
```

---

## CLI Entry Point

```python
def main() -> None:
    parser = argparse.ArgumentParser(description="...")
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    spark = SparkSession.builder.appName("...").getOrCreate()
    result = run_pipeline(spark, params)

    if args.output:
        result.write.mode("overwrite").parquet(args.output)
    if args.show or not args.output:
        result.show(20, truncate=False)
    spark.stop()

if __name__ == "__main__":
    main()
```
