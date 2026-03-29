# Few-Shot Examples -- SQL to PySpark Conversion

Three complete before/after examples demonstrating key conversion patterns.

---

## Example 1: SELECT + JOIN + GROUP BY + COALESCE

### SQL (T-SQL)

```sql
-- Create temp table with order summaries
SELECT
    c.CustomerID,
    c.CustomerName,
    ISNULL(c.Region, 'Unknown')           AS Region,
    COUNT(*)                               AS OrderCount,
    SUM(o.TotalAmount)                     AS TotalRevenue,
    AVG(o.TotalAmount)                     AS AvgOrderValue
INTO #CustomerSummary
FROM dbo.Customers c
LEFT JOIN dbo.Orders o
    ON c.CustomerID = o.CustomerID
    AND o.OrderDate >= '2024-01-01'
    AND o.Status <> 'Cancelled'
WHERE c.IsActive = 1
GROUP BY c.CustomerID, c.CustomerName, c.Region
ORDER BY TotalRevenue DESC;

CREATE CLUSTERED INDEX CX ON #CustomerSummary(CustomerID);

SELECT TOP 100 * FROM #CustomerSummary;
```

### PySpark

```python
from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

def _step1_customer_summary(spark: SparkSession) -> DataFrame:
    """Step 1 -- customer order summary (SQL lines 1-18).

    Replaces: SELECT ... INTO #CustomerSummary
    """
    customers = spark.table("customers").where(F.col("IsActive") == 1)
    orders = (
        spark.table("orders")
        .where(F.col("OrderDate") >= "2024-01-01")
        .where(F.col("Status") != "Cancelled")
    )

    summary = (
        customers
        .join(orders, on="CustomerID", how="left")
        .groupBy("CustomerID", "CustomerName", "Region")
        .agg(
            F.count("*").alias("OrderCount"),
            F.sum("TotalAmount").alias("TotalRevenue"),
            F.avg("TotalAmount").alias("AvgOrderValue"),
        )
        .withColumn("Region", F.coalesce(F.col("Region"), F.lit("Unknown")))
        .orderBy(F.col("TotalRevenue").desc_nulls_last())
    ).repartition("CustomerID").cache()
    summary.count()  # force materialization
    return summary

# Usage:
# result = _step1_customer_summary(spark).limit(100)
```

**Key conversions shown**: `INTO #temp` to `.cache()`, `ISNULL` to `F.coalesce`, `LEFT JOIN` with filter, `GROUP BY`, `ORDER BY DESC` with nulls-last, clustered index to `.repartition()`.

---

## Example 2: Window Functions + CTE

### SQL (T-SQL)

```sql
;WITH RankedEmployees AS (
    SELECT
        e.EmployeeID,
        e.DepartmentID,
        e.Salary,
        e.HireDate,
        ROW_NUMBER() OVER (
            PARTITION BY e.DepartmentID
            ORDER BY e.Salary DESC
        ) AS SalaryRank,
        NTILE(4) OVER (
            PARTITION BY e.DepartmentID
            ORDER BY e.Salary DESC
        ) AS SalaryQuartile,
        SUM(e.Salary) OVER (
            PARTITION BY e.DepartmentID
            ORDER BY e.HireDate
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS RunningCost
    FROM dbo.Employees e
    WHERE e.IsTerminated = 0
)
SELECT *
FROM RankedEmployees
WHERE SalaryRank <= 10;
```

### PySpark

```python
def _step2_ranked_employees(spark: SparkSession) -> DataFrame:
    """Step 2 -- ranked employees with window functions (SQL lines 1-22).

    Replaces: CTE RankedEmployees with ROW_NUMBER, NTILE, running SUM.
    """
    employees = spark.table("employees").where(F.col("IsTerminated") == 0)

    salary_window = Window.partitionBy("DepartmentID").orderBy(F.col("Salary").desc())
    running_window = (
        Window.partitionBy("DepartmentID")
        .orderBy("HireDate")
        .rowsBetween(Window.unboundedPreceding, Window.currentRow)
    )

    ranked = (
        employees
        .withColumn("SalaryRank", F.row_number().over(salary_window))
        .withColumn("SalaryQuartile", F.ntile(4).over(salary_window))
        .withColumn("RunningCost", F.sum("Salary").over(running_window))
    )

    return ranked.where(F.col("SalaryRank") <= 10)
```

**Key conversions shown**: CTE to intermediate variable, `ROW_NUMBER` and `NTILE` with explicit window, running `SUM` with explicit `rowsBetween` (not default RANGE), final filter on window result.

---

## Example 3: Cursor to Vectorized Pattern

### SQL (T-SQL)

```sql
DECLARE @StatusID INT, @Label VARCHAR(50);
DECLARE @Results TABLE (OrderID INT, StatusLabel VARCHAR(50));

DECLARE status_cursor CURSOR FOR
    SELECT DISTINCT StatusID FROM dbo.Orders;

OPEN status_cursor;
FETCH NEXT FROM status_cursor INTO @StatusID;

WHILE @@FETCH_STATUS = 0
BEGIN
    SET @Label = CASE @StatusID
        WHEN 1 THEN 'Pending'
        WHEN 2 THEN 'Shipped'
        WHEN 3 THEN 'Delivered'
        WHEN 4 THEN 'Cancelled'
        ELSE 'Unknown'
    END;

    INSERT INTO @Results
    SELECT OrderID, @Label FROM dbo.Orders WHERE StatusID = @StatusID;

    FETCH NEXT FROM status_cursor INTO @StatusID;
END;

CLOSE status_cursor;
DEALLOCATE status_cursor;

SELECT * FROM @Results;
```

### PySpark

```python
def _step3_label_orders(spark: SparkSession) -> DataFrame:
    """Step 3 -- label orders by status (SQL lines 1-25).

    Replaces: Cursor loop over StatusID with CASE label assignment.
    Converted to single vectorized withColumn using F.when chain.
    """
    status_map = {1: "Pending", 2: "Shipped", 3: "Delivered", 4: "Cancelled"}

    label_expr = F.lit("Unknown")
    for status_id, label in status_map.items():
        label_expr = F.when(F.col("StatusID") == status_id, label).otherwise(label_expr)

    return (
        spark.table("orders")
        .select("OrderID", "StatusID")
        .withColumn("StatusLabel", label_expr)
        .drop("StatusID")
    )
```

**Key conversions shown**: `CURSOR` + `FETCH` loop eliminated entirely. `CASE` + per-status INSERT replaced by single `F.when` chain built from a dict. No row-by-row processing -- fully vectorized. Runs 100-1000x faster than a `.collect()` loop equivalent.
