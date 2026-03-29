# Critical Gotchas -- Top 10 Silent Failures in SQL-to-PySpark Conversion

These issues produce **wrong results without errors**. Every conversion must be checked against this list.

---

## 1. DATEDIFF Argument Order Reversed

- **Gotcha**: Arguments silently swap, producing negative values or wrong magnitudes
- **SQL Server**: `DATEDIFF(day, @start, @end)` -- unit first, then start, then end
- **PySpark**: `F.datediff(end, start)` -- end first, then start (no unit arg; days only)

```python
# BAD: copied SQL argument order
df.withColumn("days", F.datediff(F.col("start_date"), F.col("end_date")))
# Returns NEGATIVE values silently

# GOOD: reversed order
df.withColumn("days", F.datediff(F.col("end_date"), F.col("start_date")))
```

---

## 2. Case-Sensitive String Comparison

- **Gotcha**: WHERE clauses silently return fewer rows than SQL Server
- **SQL Server**: Default `CI_AS` collation -- `'abc' = 'ABC'` is TRUE
- **PySpark**: Always case-sensitive -- `'abc' = 'ABC'` is FALSE

```python
# BAD: direct translation loses case-insensitive matches
df.where(F.col("name") == "Smith")

# GOOD: normalize case
df.where(F.lower(F.col("name")) == "smith")

# GOOD: for LIKE patterns use ilike
df.where(F.col("name").ilike("%smith%"))
```

---

## 3. NULL Ordering in ORDER BY

- **Gotcha**: Sort order differs silently, affecting TOP N, ROW_NUMBER, reports
- **SQL Server**: NULLs sort FIRST in ASC, LAST in DESC
- **PySpark**: NULLs sort LAST in ASC, FIRST in DESC (opposite!)

```python
# BAD: NULLs appear at wrong end
df.orderBy(F.col("score").asc())

# GOOD: match SQL Server behavior
df.orderBy(F.col("score").asc_nulls_first())

# For DESC:
df.orderBy(F.col("score").desc_nulls_last())
```

---

## 4. Window Frame RANGE Includes Duplicates

- **Gotcha**: Running totals jump when ORDER BY has duplicate values
- **SQL Server**: Same default RANGE behavior, but less common due to clustered indexes creating unique order
- **PySpark**: Default `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` groups all rows with same ORDER BY value

```python
# BAD: RANGE default -- if two rows have same date, both get the combined sum
w = Window.partitionBy("dept").orderBy("date")
df.withColumn("running_total", F.sum("amount").over(w))

# GOOD: explicit ROWS frame -- strict positional, no duplicate grouping
w = (Window.partitionBy("dept").orderBy("date")
     .rowsBetween(Window.unboundedPreceding, Window.currentRow))
df.withColumn("running_total", F.sum("amount").over(w))
```

---

## 5. Decimal Arithmetic Precision Loss

- **Gotcha**: Financial calculations silently lose precision, totals drift by small percentages
- **SQL Server**: Deterministic decimal arithmetic with documented precision rules
- **PySpark**: `spark.sql.decimalOperations.allowPrecisionLoss=true` (DEFAULT) silently truncates

```python
# BAD: default Spark config loses precision
revenue = F.col("price") * F.col("quantity")  # intermediate may truncate

# GOOD: disable precision loss + explicit types
# In SparkSession config: .config("spark.sql.decimalOperations.allowPrecisionLoss", "false")
revenue = (
    F.col("price").cast(DecimalType(19, 4))
    * F.col("quantity").cast(DecimalType(19, 4))
)
```

---

## 6. months_between Returns DOUBLE Not INT

- **Gotcha**: Downstream comparisons and joins break on fractional month values
- **SQL Server**: `DATEDIFF(month, start, end)` returns INT (whole months)
- **PySpark**: `F.months_between(end, start)` returns DOUBLE (e.g., 2.96774...)

```python
# BAD: returns 2.967... instead of 3
df.withColumn("months", F.months_between(F.col("end"), F.col("start")))

# GOOD: cast to int to match SQL Server behavior
df.withColumn("months", F.months_between(F.col("end"), F.col("start")).cast("int"))
```

---

## 7. date_sub with Negative Goes FORWARD

- **Gotcha**: Using `date_sub` with a negative number adds days instead of subtracting
- **SQL Server**: `DATEADD(day, -5, date)` clearly subtracts 5 days
- **PySpark**: `F.date_sub(col, -5)` goes FORWARD 5 days (double negative)

```python
# BAD: "subtract negative 5 days" = add 5 days
df.withColumn("past", F.date_sub(F.col("date"), -5))  # goes FORWARD

# GOOD: use date_add for clarity
df.withColumn("past", F.date_add(F.col("date"), -5))   # goes backward as expected
# OR: always use positive values
df.withColumn("past", F.date_sub(F.col("date"), 5))     # subtracts 5 days
```

---

## 8. Python UDF 50-100x Slower Than Native F.xxx

- **Gotcha**: Job completes but takes 10x longer; no error, just slow
- **SQL Server**: Scalar UDFs are slow in SQL too, but inline table-valued functions are fast
- **PySpark**: Python UDFs serialize data to Python, process row-by-row, serialize back

```python
# BAD: Python UDF for something native functions handle
@F.udf(returnType=StringType())
def classify(amount):
    if amount is None: return "unknown"
    return "high" if amount > 1000 else "low"

df.withColumn("tier", classify("amount"))  # 50-100x slower

# GOOD: native F.when chain
df.withColumn("tier",
    F.when(F.col("amount").isNull(), "unknown")
     .when(F.col("amount") > 1000, "high")
     .otherwise("low")
)
```

---

## 9. COUNT(*) vs COUNT(col) with NULLs

- **Gotcha**: Row counts differ silently when column has NULLs
- **SQL Server**: Same behavior (COUNT(col) skips NULLs), but often hidden by ISNULL defaults
- **PySpark**: `F.count("col")` skips NULLs; `F.count("*")` counts all rows

```python
# These return DIFFERENT values when col has NULLs:
df.agg(F.count("*").alias("total_rows"))           # includes NULLs
df.agg(F.count("status").alias("non_null_rows"))    # skips NULLs

# If SQL used COUNT(*), always use F.count("*") -- not F.count("some_col")
# If SQL used COUNT(col), use F.count("col") to preserve NULL-skipping
```

---

## 10. BIT Column NULL Handling

- **Gotcha**: BooleanType filters silently exclude NULL rows
- **SQL Server**: `BIT` column can be 0, 1, or NULL (3-valued logic)
- **PySpark**: `BooleanType` WHERE clause filters out NULLs (NULL is not TRUE and not FALSE)

```python
# BAD: loses NULL rows silently
df.where(~F.col("is_active"))  # only gets FALSE rows, not NULL rows

# GOOD: explicitly include NULLs
df.where(~F.col("is_active") | F.col("is_active").isNull())

# If original SQL had: WHERE is_active <> 1
# This means "FALSE or NULL" in SQL Server
df.where((F.col("is_active") == False) | F.col("is_active").isNull())  # noqa: E712
```
