# SQL to PySpark Construct Mapping Reference

This is the authoritative mapping table used by the converter. When converting SQL to PySpark, use these patterns.

---

## Data Type Mapping with Gotchas

| SQL Server Type | PySpark Type | Notes |
|---|---|---|
| `INT` | `IntegerType()` | Direct mapping |
| `BIGINT` | `LongType()` | Direct mapping |
| `SMALLINT` | `ShortType()` | Direct mapping |
| `TINYINT` | `ByteType()` | SQL Server: 0-255 unsigned; PySpark: -128 to 127 signed |
| `BIT` | `BooleanType()` | **Gotcha**: SQL Server BIT is nullable (3-valued: 0/1/NULL). Handle NULL explicitly |
| `FLOAT` | `DoubleType()` | SQL `FLOAT(53)` = 8 bytes = DoubleType |
| `REAL` | `FloatType()` | SQL `FLOAT(24)` = 4 bytes = FloatType |
| `DECIMAL(p,s)` / `NUMERIC(p,s)` | `DecimalType(p, s)` | **Gotcha**: set `spark.sql.decimalOperations.allowPrecisionLoss=false` to avoid silent precision loss in arithmetic |
| `MONEY` | `DecimalType(19, 4)` | Exact mapping to SQL Server's internal representation |
| `SMALLMONEY` | `DecimalType(10, 4)` | Exact mapping |
| `VARCHAR(n)` / `CHAR(n)` | `StringType()` | No length enforcement in PySpark; add `.substr(1, n)` if truncation matters |
| `VARCHAR(MAX)` / `NVARCHAR(MAX)` | `StringType()` | No length enforcement |
| `NVARCHAR(n)` / `NCHAR(n)` | `StringType()` | PySpark is always UTF-8; N prefix irrelevant |
| `DATE` | `DateType()` | Direct mapping |
| `DATETIME` | `TimestampType()` | Millisecond precision only |
| `DATETIME2(n)` | `TimestampType()` | **Gotcha**: microsecond max (6 digits). DATETIME2(7) loses 100ns digit. Recommend source use DATETIME2(6) |
| `DATETIMEOFFSET` | `TimestampType()` | Offset lost. Use `from_utc_timestamp()` / `to_utc_timestamp()` for TZ handling |
| `TIME` | `StringType()` | No native TIME type. Store as string `HH:mm:ss`, parse with `F.to_timestamp()` if needed |
| `UNIQUEIDENTIFIER` | `StringType()` | Generate with `F.expr("uuid()")` or Python `uuid.uuid4()` |
| `VARBINARY(n)` / `IMAGE` | `BinaryType()` | Direct mapping |
| `XML` | `StringType()` | **Unsupported natively**. Store as string, parse with UDF if needed |
| `sql_variant` | -- | **Unsupported**. Must resolve to concrete type before migration |
| `hierarchyid` | -- | **Unsupported**. Convert to string path (`/1/3/`) in SQL first |
| `geography` / `geometry` | -- | **Unsupported**. Use GeoSpark/Sedona library or WKT string |

---

## NULL Semantics (CRITICAL)

PySpark always operates with ANSI_NULLS ON semantics. These rules apply universally:

| Behavior | SQL Server | PySpark | Fix |
|---|---|---|---|
| `NULL = NULL` | `UNKNOWN` (filtered out in WHERE) | Same | Use `eqNullSafe()` if NULLs should match |
| `NULL <> value` | `UNKNOWN` (filtered out) | Same | Explicitly handle: `col.isNull() \| (col != value)` |
| NULL in JOIN keys | Keys don't match | Same | Use `col.eqNullSafe(other_col)` for NULL-safe joins |
| `IS NOT DISTINCT FROM` | Available in SQL 2022 | `col.eqNullSafe(other_col)` | Direct equivalent |
| NULL in `COUNT(*)` | Counted | Counted | Same behavior |
| NULL in `COUNT(col)` | Skipped | Skipped | Same behavior |
| NULL in `SUM/AVG` | Skipped | Skipped | Same behavior; empty group returns NULL not 0 |
| NULL in `GROUP BY` | NULLs grouped together | Same | Same behavior |
| NULL ordering ASC | **NULLS FIRST** (SQL Server default) | **NULLS LAST** (Spark default) | Use `F.col("x").asc_nulls_first()` |
| NULL ordering DESC | **NULLS LAST** (SQL Server default) | **NULLS FIRST** (Spark default) | Use `F.col("x").desc_nulls_last()` |
| `ISNULL(a, b)` | Returns b if a is NULL | -- | `F.coalesce(a, F.lit(b))` |
| `COALESCE(a, b, c)` | First non-NULL | `F.coalesce(a, b, c)` | Direct mapping |
| `NULLIF(a, b)` | NULL if a == b | -- | `F.when(a == b, F.lit(None)).otherwise(a)` |

---

## String Collation

| Issue | SQL Server | PySpark | Fix |
|---|---|---|---|
| Default comparison | **Case-insensitive** (`CI_AS` collation) | **Case-sensitive** | Use `.ilike()` for CI patterns, or `F.lower()` on both sides |
| `WHERE name = 'John'` matches `'john'` | Yes (CI collation) | **No** | `F.lower("name") == "john"` or `F.col("name").ilike("john")` |
| `N'unicode string'` prefix | Required for NVARCHAR literals | Not needed | PySpark strings are always UTF-8 |
| Accent sensitivity | Depends on collation (`_AI` vs `_AS`) | Always accent-sensitive | No built-in fix; use `F.translate()` or UDF to strip accents |
| Trailing space comparison | `'abc' = 'abc  '` is TRUE | FALSE | Use `F.rtrim()` on both sides if SQL relied on this |

---

## Data Structures

| SQL Construct | PySpark Equivalent | Notes |
|---|---|---|
| `SELECT ... INTO #TempTable` | `df = (...).cache()` then `df.count()` | `.count()` forces materialization |
| `CREATE TABLE #Temp (cols)` | Define DataFrame via `.select()` with `.alias()` | No explicit schema DDL needed |
| `IF OBJECT_ID('tempdb..#X') IS NOT NULL DROP TABLE #X` | Skip | DataFrame GC handles lifecycle. Comment: `# temp table auto-managed` |
| `CREATE CLUSTERED INDEX CX ON #T(col)` | `.repartition("col").cache()` | Simulates data locality |
| `CREATE INDEX IX ON #T(col) INCLUDE (c1,c2)` | `.repartition("col").cache()` | INCLUDE cols not applicable |
| `DECLARE @var type = value` | Python variable: `var: type = value` | Use dataclass for proc params |
| `DECLARE @table TABLE(cols)` | Python list or small DataFrame | Prefer list for small data |
| `TABLE @table INSERT/SELECT` | `list.append()` or `df.union()` | |

---

## Stored Procedures & Functions

| SQL Construct | PySpark Equivalent | Notes |
|---|---|---|
| `CREATE PROCEDURE ... @Param type = default` | `@dataclass class Params` + `def run_pipeline(spark, params)` | One field per parameter |
| `CREATE FUNCTION ... RETURNS TABLE` | `def func_name(args) -> DataFrame` | Table-valued: return DF |
| `CREATE FUNCTION ... RETURNS scalar` | `def func_name(args) -> type` | Scalar: return value |
| `EXEC proc @p1=val, @p2=val` | `result = run_pipeline(spark, Params(p1=val, p2=val))` | |
| `OUTPUT parameters` | Return tuple or dataclass | |

---

## Queries & Filters

| SQL Construct | PySpark Equivalent | Notes |
|---|---|---|
| `SELECT col1, col2 FROM t` | `df.select("col1", "col2")` | Use `F.col()` for expressions |
| `SELECT DISTINCT col` | `df.select("col").distinct()` | |
| `WHERE condition` | `.where(condition)` or `.filter(condition)` | Identical behavior |
| `AND / OR / NOT` | `& / \| / ~` with parentheses | **Must** wrap each condition in `()` |
| `BETWEEN a AND b` | `F.col("x").between(a, b)` | Inclusive on both ends |
| `IN (val1, val2)` | `F.col("x").isin([val1, val2])` | |
| `LIKE '%pattern%'` | `F.col("x").like("%pattern%")` | Case-sensitive. Use `.ilike()` for CI |
| `TOP (N)` | `.limit(N)` | No ORDER BY guarantee without `.orderBy()` |
| `TOP (N) WITH TIES` | Window function + filter | `F.rank().over(w) <= N` |
| `ORDER BY col ASC/DESC` | `.orderBy(F.col("col").asc())` / `.desc()` | See NULL ordering above |
| `OFFSET N ROWS FETCH NEXT M ROWS ONLY` | `.orderBy(...).limit(N + M).tail(M)` | Or use window: `row_number between N+1 and N+M` |

---

## Joins

| SQL Construct | PySpark Equivalent | Notes |
|---|---|---|
| `INNER JOIN t2 ON t1.id = t2.id` | `df1.join(df2, on="id", how="inner")` | |
| `LEFT JOIN t2 ON condition` | `df1.join(df2, condition, "left")` | |
| `RIGHT JOIN` | `how="right"` | |
| `FULL OUTER JOIN` | `how="full"` | |
| `CROSS JOIN` | `df1.crossJoin(df2)` | |
| `CROSS APPLY` | `.join(df2, condition, "inner")` | Flatten lateral subquery first |
| `OUTER APPLY` | `.join(df2, condition, "left")` | |
| Multi-column JOIN | `on=[df1.a == df2.a, df1.b == df2.b]` | Pass list of conditions |
| JOIN with NULL-safe key | `df1.a.eqNullSafe(df2.a)` | Use when NULLs should match |

---

## Aggregations

| SQL Construct | PySpark Equivalent | Notes |
|---|---|---|
| `COUNT(*)` / `COUNT_BIG(*)` | `F.count("*")` | Counts all rows including NULLs |
| `COUNT(col)` | `F.count("col")` | **Skips NULLs** |
| `COUNT(DISTINCT col)` | `F.countDistinct("col")` | |
| `SUM(col)` | `F.sum("col")` | NULLs skipped; empty group returns NULL |
| `AVG(col)` | `F.avg("col")` | NULLs skipped |
| `MIN(col)` / `MAX(col)` | `F.min("col")` / `F.max("col")` | |
| `STDEV(col)` | `F.stddev("col")` | Sample stddev (N-1) |
| `VAR(col)` | `F.variance("col")` | Sample variance |
| `GROUP BY col1, col2` | `.groupBy("col1", "col2")` | |
| `GROUP BY ROLLUP(a, b)` | `.rollup("a", "b").agg(...)` | |
| `GROUP BY CUBE(a, b)` | `.cube("a", "b").agg(...)` | |
| `HAVING condition` | `.where(condition)` after `.agg()` | Chain after aggregation |
| `STRING_AGG(col, ',')` | `F.concat_ws(",", F.collect_list("col"))` | Order not guaranteed; sort first if needed |

---

## Window Functions

| SQL Construct | PySpark Equivalent | Notes |
|---|---|---|
| `ROW_NUMBER() OVER (PARTITION BY p ORDER BY o)` | `F.row_number().over(Window.partitionBy("p").orderBy("o"))` | |
| `RANK() OVER (...)` | `F.rank().over(window)` | |
| `DENSE_RANK() OVER (...)` | `F.dense_rank().over(window)` | |
| `NTILE(n) OVER (ORDER BY o)` | `F.ntile(n).over(Window.orderBy("o"))` | |
| `LAG(col, n) OVER (...)` | `F.lag("col", n).over(window)` | |
| `LEAD(col, n) OVER (...)` | `F.lead("col", n).over(window)` | |
| `FIRST_VALUE(col) OVER (...)` | `F.first("col", ignorenulls=True).over(window)` | `ignorenulls` default is False |
| `LAST_VALUE(col) OVER (...)` | `F.last("col", ignorenulls=True).over(window)` | **Must** set frame to `rowsBetween(Window.unboundedPreceding, Window.unboundedFollowing)` |
| `SUM(col) OVER (ORDER BY o)` | `F.sum("col").over(Window.orderBy("o").rowsBetween(Window.unboundedPreceding, 0))` | **Always** use explicit `rowsBetween()` for running totals |
| `SUM(col) OVER (PARTITION BY ...)` | `F.sum("col").over(Window.partitionBy(...))` | Partition-level aggregate (no ORDER BY = full frame) |
| `PERCENT_RANK()` | `F.percent_rank().over(window)` | |
| `CUME_DIST()` | `F.cume_dist().over(window)` | |

---

## NULL Handling

| SQL Construct | PySpark Equivalent | Notes |
|---|---|---|
| `ISNULL(col, default)` | `F.coalesce(F.col("col"), F.lit(default))` | |
| `COALESCE(a, b, c)` | `F.coalesce(a, b, c)` | Direct mapping |
| `NULLIF(expr, 0)` | `F.when(expr == 0, F.lit(None)).otherwise(expr)` | Returns NULL when equal |
| `IS NULL` | `F.col("x").isNull()` | |
| `IS NOT NULL` | `F.col("x").isNotNull()` | |
| `SET ANSI_NULLS OFF` | No equivalent | PySpark always uses ANSI NULL semantics |

---

## Type Casting

| SQL Construct | PySpark Equivalent | Notes |
|---|---|---|
| `CAST(col AS INT)` | `F.col("col").cast(IntegerType())` | Or `.cast("int")` |
| `CAST(col AS DATE)` | `F.col("col").cast("date")` | |
| `CAST(col AS DECIMAL(19,4))` | `F.col("col").cast(DecimalType(19, 4))` | |
| `TRY_CONVERT(type, col)` | `F.col("col").cast(type)` | PySpark returns NULL on failure (safe by default) |
| `CONVERT(type, col)` | `F.col("col").cast(type)` | Same as CAST |
| `CONVERT(VARCHAR, date, 112)` | `F.date_format(col, "yyyyMMdd")` | Style 112 = `YYYYMMDD` |
| `CONVERT(VARCHAR, date, 120)` | `F.date_format(col, "yyyy-MM-dd HH:mm:ss")` | Style 120 = ODBC canonical |
| `CONVERT(VARCHAR, date, 101)` | `F.date_format(col, "MM/dd/yyyy")` | Style 101 = US format |
| Implicit string-to-int | Not supported in strict mode | Always add explicit `.cast()` |

---

## String Functions

| SQL Construct | PySpark Equivalent | Notes |
|---|---|---|
| `CONCAT(a, b)` | `F.concat(a, b)` | |
| `a + ' ' + b` (string concat) | `F.concat_ws(" ", a, b)` | |
| `LTRIM(RTRIM(col))` | `F.trim(F.col("col"))` | |
| `SUBSTRING(col, start, len)` | `F.substring(F.col("col"), start, len)` | 1-based indexing (same as SQL) |
| `LEFT(col, n)` | `F.substring(F.col("col"), 1, n)` | |
| `RIGHT(col, n)` | `F.substring(F.col("col"), -n, n)` | |
| `LEN(col)` | `F.length(F.col("col"))` | |
| `DATALENGTH(col)` | `F.octet_length(F.col("col"))` | Byte length, not char length |
| `REPLACE(col, old, new)` | `F.regexp_replace(col, F.lit(old), F.lit(new))` | Escape regex chars. Or use `F.translate()` for char-by-char |
| `CHARINDEX(needle, haystack)` | `F.locate(needle, haystack)` | Returns 0 if not found (same as SQL) |
| `PATINDEX('%pattern%', col)` | `F.locate(...)` or regex | Use `F.regexp_extract()` for complex patterns |
| `STUFF(col, start, len, new)` | `F.concat(F.substring(col, 1, start-1), F.lit(new), F.substring(col, start+len, 9999))` | Manual reconstruction |
| `UPPER(col)` / `LOWER(col)` | `F.upper(col)` / `F.lower(col)` | |
| `REVERSE(col)` | `F.reverse(col)` | |
| `REPLICATE(str, n)` | `F.repeat(str, n)` | |
| `FORMAT(num, 'N2')` | `F.format_number(col, 2)` | Returns string |
| `STRING_SPLIT(col, ',')` | `F.split(col, ",")` | Returns array. Use `F.explode()` to get rows |

---

## Date Functions

| SQL Construct | PySpark Equivalent | Notes |
|---|---|---|
| `DATEDIFF(day, start, end)` | `F.datediff(end, start)` | **Argument order REVERSED!** SQL: (unit, start, end). PySpark: (end, start) |
| `DATEDIFF(month, start, end)` | `F.months_between(end, start).cast("int")` | **Returns DOUBLE** not INT. Always `.cast("int")` |
| `DATEDIFF(year, start, end)` | `F.year(end) - F.year(start)` | Simple year diff (same semantics as SQL Server) |
| `DATEADD(day, n, date)` | `F.date_add(date, n)` | **Gotcha**: negative n goes backward. Do NOT use `F.date_sub()` with negative |
| `DATEADD(month, n, date)` | `F.add_months(date, n)` | |
| `DATEADD(year, n, date)` | `F.add_months(date, n * 12)` | No `add_years()` function |
| `DATEADD(hour, n, ts)` | `col + F.expr(f"INTERVAL {n} HOURS")` | Use `F.expr()` for sub-day intervals |
| `GETDATE()` / `SYSDATETIME()` | `F.current_timestamp()` | |
| `SYSUTCDATETIME()` | `F.to_utc_timestamp(F.current_timestamp(), "UTC")` | Or `datetime.now(timezone.utc)` in Python |
| `CAST(col AS DATE)` | `F.col("col").cast("date")` | |
| `YEAR(col)` / `MONTH(col)` / `DAY(col)` | `F.year(col)` / `F.month(col)` / `F.dayofmonth(col)` | |
| `DATEPART(weekday, col)` | `F.dayofweek(col)` | **Gotcha**: SQL Server 1=Sunday (default), PySpark 1=Sunday. Check `@@DATEFIRST` setting |
| `DATENAME(month, col)` | `F.date_format(col, "MMMM")` | Returns full month name |
| `EOMONTH(date)` | `F.last_day(date)` | |
| `EOMONTH(date, n)` | `F.last_day(F.add_months(date, n))` | |
| `DATEFROMPARTS(y, m, d)` | `F.make_date(y, m, d)` | Spark 3.3+ |
| `ISDATE(col)` | `F.to_date(col).isNotNull()` | Returns boolean (valid date check) |
| `AT TIME ZONE 'Eastern'` | `F.from_utc_timestamp(col, "US/Eastern")` | Use IANA timezone IDs |
| `SWITCHOFFSET(col, '+05:30')` | `F.from_utc_timestamp(F.to_utc_timestamp(col, src_tz), tgt_tz)` | Two-step conversion |

---

## JSON Operations

| SQL Construct | PySpark Equivalent | Notes |
|---|---|---|
| `FOR JSON PATH` | `F.to_json(F.struct(...))` | Build struct of columns |
| `FOR JSON PATH, WITHOUT_ARRAY_WRAPPER` | `F.to_json(F.struct(...))` | PySpark doesn't wrap by default |
| `OPENJSON(col) WITH (schema)` | `F.from_json(col, schema)` | Define `StructType` schema |
| `CROSS APPLY OPENJSON(...)` | `F.from_json()` then `.select("parsed.*")` | |
| `JSON_VALUE(col, '$.path')` | `F.get_json_object(col, "$.path")` | Returns string always |
| `JSON_QUERY(col, '$.array')` | `F.get_json_object(col, "$.array")` | Returns JSON string |
| Nested JSON subquery | `F.collect_list(F.struct(...))` + `F.to_json()` | Pre-aggregate then nest |

---

## Control Flow

| SQL Construct | PySpark Equivalent | Notes |
|---|---|---|
| `CASE WHEN c1 THEN v1 WHEN c2 THEN v2 ELSE v3 END` | `F.when(c1, v1).when(c2, v2).otherwise(v3)` | Chain multiple `.when()` |
| `IIF(cond, true_val, false_val)` | `F.when(cond, true_val).otherwise(false_val)` | |
| `BEGIN TRY ... END CATCH` | `try: ... except Exception as e:` | |
| `THROW` | `raise` | |
| `RAISERROR` | `raise RuntimeError(message)` | |
| `@@FETCH_STATUS` / `CURSOR` | Vectorized operations | See known_limitations.md |
| `IF @var = 1 BEGIN ... END` | `if var == 1:` | Python control flow |
| `WHILE @i < @n BEGIN ... END` | `while i < n:` or vectorize | Prefer vectorized approach |

---

## CTE / Subqueries

| SQL Construct | PySpark Equivalent | Notes |
|---|---|---|
| `;WITH cte AS (SELECT ...)` | `cte = df.select(...)` | Assign to variable |
| `WITH cte1 AS (...), cte2 AS (...)` | `cte1 = ...; cte2 = ...` | Chain variables |
| Correlated subquery in SELECT | `.join()` + pre-aggregate | Flatten to join |
| `EXISTS(SELECT 1 FROM t WHERE ...)` | `df.join(subquery, ..., "left_semi")` | Left semi join is most efficient |
| `NOT EXISTS(...)` | `df.join(subquery, ..., "left_anti")` | Left anti join |
| Scalar subquery in SELECT | Pre-compute + `.crossJoin()` or `.join()` | Never use `.collect()` inside transformations |

---

## Cursor Patterns

| SQL Construct | PySpark Equivalent | Notes |
|---|---|---|
| Simple iteration cursor | `for row in df.toLocalIterator():` | Only for small datasets. Never `.collect()` on large data |
| Cursor + dynamic SQL | Predicate map pattern | Map predicates to functions, evaluate once per group |
| Cursor + UPDATE | `.withColumn()` with conditional logic | Vectorize the update |
| `@@FETCH_STATUS` loop | Python `for` loop | |

---

## SET Options (Skip These)

These SQL Server session settings have no PySpark equivalent. Skip them in conversion:

| SQL Setting | Action |
|---|---|
| `SET NOCOUNT ON/OFF` | Skip |
| `SET XACT_ABORT ON/OFF` | Skip |
| `SET ANSI_NULLS ON/OFF` | Skip (PySpark always ANSI) |
| `SET QUOTED_IDENTIFIER ON/OFF` | Skip |
| `SET ARITHABORT ON/OFF` | Skip |
| `SET CONCAT_NULL_YIELDS_NULL ON/OFF` | Skip (PySpark: NULL concat = NULL always) |
| `SET TRANSACTION ISOLATION LEVEL` | Skip |
| `USE [database]` | Skip (use Spark catalog config) |
| `GO` | Skip (batch separator) |
