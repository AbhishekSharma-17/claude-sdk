# Known Limitations -- SQL to PySpark Conversion

These SQL patterns cannot be automatically converted. When encountered, insert a TODO comment in the output and list them in the audit report.

---

## Cannot Auto-Convert

### Dynamic SQL (sp_executesql with runtime predicates)
- **Why**: PySpark cannot construct column expressions from arbitrary strings at runtime
- **Workaround**: If predicates are finite/known, use a predicate-map pattern (dict mapping predicate names to PySpark filter functions). If truly dynamic, mark as manual.
- **TODO pattern**: `# TODO: Manual review -- dynamic SQL at SQL lines {X-Y}. Original predicate: "{sql}"`

### Cursor-Based Row-by-Row Processing
- **Why**: Spark is batch-oriented; row-by-row iteration defeats distributed processing
- **Workaround**: Rewrite as vectorized window functions, groupBy + agg, or collect to driver only for tiny datasets
- **TODO pattern**: `# TODO: Cursor at SQL lines {X-Y} -- rewrite as vectorized operation`

### OBJECT_ID() / System Object Checks
- **Why**: SQL Server metadata functions have no PySpark equivalent
- **Workaround**: Skip entirely. DataFrame lifecycle in PySpark handles cleanup automatically
- **TODO pattern**: (omit -- just skip the check)

### Transaction Semantics (BEGIN TRAN / COMMIT / ROLLBACK)
- **Why**: Spark DataFrames are immutable; no mid-pipeline rollback
- **Workaround**: For ACID needs, use Delta Lake. For simple error handling, use try/except.
- **TODO pattern**: `# TODO: Transaction semantics at SQL lines {X-Y} -- consider Delta Lake for ACID`

### Schema DDL with Constraints (CHECK, FOREIGN KEY, UNIQUE)
- **Why**: Spark does not enforce relational constraints
- **Workaround**: Implement as validation checks in code (DataFrame filters)
- **TODO pattern**: `# TODO: Constraint "{name}" not enforced -- add validation logic`

### SET Options (NOCOUNT, XACT_ABORT, ANSI_NULLS)
- **Why**: SQL Server session-level settings with no Spark equivalent
- **Workaround**: Skip entirely. These control SQL Server behavior, not logic
- **TODO pattern**: (omit -- no action needed)

### USE Database / GO Batch Separators
- **Why**: SQL Server context management, not applicable in Spark
- **Workaround**: Tables referenced as `catalog.schema.table` via `spark.table()`
- **TODO pattern**: (omit -- handled by Spark catalog configuration)

### Temp Table Indexes with INCLUDE Columns
- **Why**: Spark has no B-tree indexes
- **Workaround**: `.repartition(index_col).cache()` provides data locality
- **TODO pattern**: (omit -- repartition is the best proxy)

### MERGE Statements (UPSERT)
- **Why**: Standard DataFrame API has no MERGE
- **Workaround**: Use Delta Lake `MERGE INTO` or implement as delete-then-insert
- **TODO pattern**: `# TODO: MERGE at SQL lines {X-Y} -- use Delta Lake merge or manual upsert logic`

### Linked Server Queries / OPENROWSET
- **Why**: Cross-server queries need explicit data source configuration in Spark
- **Workaround**: Configure as separate Spark data source (JDBC, etc.)
- **TODO pattern**: `# TODO: Linked server query at SQL lines {X-Y} -- configure as Spark JDBC source`

---

## Window Frame Defaults

Both SQL Server and PySpark default to `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` when ORDER BY is present. This is a subtle trap:

| Frame Type | Behavior with Duplicates | When to Use |
|---|---|---|
| `RANGE` (default) | Includes ALL rows with same ORDER BY value in current row's frame | Partition-level aggregates without ORDER BY |
| `ROWS` | Strictly positional, unaffected by duplicates | **Running totals, running counts, cumulative sums** |

**Rule**: Always use `.rowsBetween(Window.unboundedPreceding, Window.currentRow)` for running totals. The RANGE default will give incorrect results when ORDER BY has duplicate values.

```python
# BAD: RANGE default includes duplicates in frame
w = Window.partitionBy("dept").orderBy("date")
df.withColumn("running", F.sum("amt").over(w))  # duplicates cause jumps

# GOOD: explicit ROWS frame
w = Window.partitionBy("dept").orderBy("date").rowsBetween(Window.unboundedPreceding, 0)
df.withColumn("running", F.sum("amt").over(w))
```

---

## Implicit Type Coercion

| Scenario | SQL Server | PySpark (ANSI mode) | Fix |
|---|---|---|---|
| `WHERE salary = '50000'` | Implicit string-to-int: works | Strict mode: **error** | `F.col("salary") == 50000` (use correct type) |
| `SELECT 1 / 2` | Returns `0` (integer division) | Returns `0` (same) | `F.lit(1) / F.lit(2).cast("double")` |
| `INT + DECIMAL` | Auto-promotes to DECIMAL | Auto-promotes | Same behavior, but verify precision |
| `VARCHAR + INT` | Implicit cast to VARCHAR | **Error** in strict mode | Explicit `.cast("string")` |

**Rule**: Always add explicit `.cast()` for any cross-type comparison or arithmetic. Do not rely on implicit coercion.

---

## Partially Convertible (Need Review)

### CASE with Side Effects
- `CASE WHEN ... THEN UPDATE ... END` -- Cannot have DML in CASE; rewrite as conditional logic

### Recursive CTEs
- Spark SQL supports recursive CTEs since 3.4, but PySpark DataFrame API does not
- Workaround: Use `spark.sql()` with recursive CTE syntax, or unroll to iterative loop

### PIVOT / UNPIVOT
- Spark has `.groupBy().pivot()` but syntax differs significantly
- Needs careful column mapping and explicit value list for performance

### STRING_AGG / STUFF + FOR XML PATH
- Use `F.collect_list()` + `F.concat_ws()` pattern
- Not a direct 1:1 but functionally equivalent

### APPLY with Correlated Subquery
- CROSS APPLY / OUTER APPLY with complex correlated logic needs manual flatten
- Simple cases: rewrite as JOIN. Complex: use `F.explode()` + pre-aggregation

---

## Real-World War Stories

### 1. Decimal Precision Loss (Revenue Off by 2.3%)
A financial pipeline migrated `MONEY` columns using default Spark decimal arithmetic. Spark's `allowPrecisionLoss=true` (default) silently rounded intermediate results. Revenue totals diverged by 2.3% over millions of rows. **Fix**: Set `spark.sql.decimalOperations.allowPrecisionLoss=false` and use `DecimalType(19, 4)` consistently.

### 2. Case-Sensitive String Comparison (Product Search Broke)
A product lookup used `WHERE ProductName = @search`. SQL Server's CI_AS collation matched case-insensitively. PySpark's default comparison is case-sensitive, so `'Widget'` no longer matched `'widget'`. Thousands of unmatched records in downstream joins. **Fix**: Use `F.lower()` on both sides or `.ilike()` for LIKE patterns.

### 3. Scalar UDF Made ETL 10x Slower
A developer converted a SQL scalar function to a Python UDF. The function was called per-row on 50M rows. Python UDF serialization overhead made the job 10x slower than the SQL version. **Fix**: Rewrite as native `F.when()` / `F.coalesce()` chain. Always check if a native PySpark function exists before writing a UDF.
