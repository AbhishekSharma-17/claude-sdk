-- ============================================================================
-- E-Commerce Analytics ETL Pipeline
-- Database: ECommerceDB
-- Dialect: T-SQL (SQL Server 2019)
--
-- This script contains 8 objects with heavy cross-dependencies:
--   1. vw_ActiveProducts        (view, standalone)
--   2. fn_CalculateDiscount     (scalar function, standalone)
--   3. fn_GetCustomerTier       (scalar function, standalone)
--   4. usp_StageSalesData       (procedure, uses vw_ActiveProducts)
--   5. usp_BuildCustomerProfile (procedure, uses fn_GetCustomerTier, usp_StageSalesData)
--   6. usp_CalculateRevenue     (procedure, uses fn_CalculateDiscount, usp_StageSalesData)
--   7. usp_GenerateReport       (procedure, uses usp_BuildCustomerProfile, usp_CalculateRevenue)
--   8. trg_AuditOrderChanges    (trigger, references Orders table)
--
-- Dependency Graph:
--   vw_ActiveProducts ──→ usp_StageSalesData ──→ usp_BuildCustomerProfile ──→ usp_GenerateReport
--   fn_GetCustomerTier ──→ usp_BuildCustomerProfile ──↗
--   fn_CalculateDiscount ──→ usp_CalculateRevenue ──↗
--   trg_AuditOrderChanges (standalone trigger)
-- ============================================================================

SET NOCOUNT ON;
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

-- ============================================================================
-- OBJECT 1: vw_ActiveProducts (View — standalone, no dependencies)
-- ============================================================================

CREATE VIEW dbo.vw_ActiveProducts
AS
SELECT
    p.ProductID,
    p.ProductName,
    p.CategoryID,
    c.CategoryName,
    p.UnitPrice,
    p.UnitsInStock,
    ISNULL(p.Description, 'No description') AS Description,
    CASE
        WHEN p.UnitPrice > 100 THEN 'Premium'
        WHEN p.UnitPrice > 50 THEN 'Standard'
        WHEN p.UnitPrice > 10 THEN 'Budget'
        ELSE 'Clearance'
    END AS PriceTier,
    DATEDIFF(day, p.CreatedDate, GETDATE()) AS DaysSinceListed
FROM dbo.Products p
INNER JOIN dbo.Categories c ON p.CategoryID = c.CategoryID
WHERE p.IsActive = 1
  AND p.IsDeleted = 0
  AND p.UnitsInStock > 0;
GO

-- ============================================================================
-- OBJECT 2: fn_CalculateDiscount (Scalar Function — standalone)
-- ============================================================================

CREATE FUNCTION dbo.fn_CalculateDiscount
(
    @OrderAmount DECIMAL(19, 4),
    @CustomerTier VARCHAR(20),
    @IsHolidaySeason BIT
)
RETURNS DECIMAL(19, 4)
AS
BEGIN
    DECLARE @DiscountRate DECIMAL(5, 4) = 0.0000;
    DECLARE @FinalDiscount DECIMAL(19, 4);

    -- Base discount by tier
    SET @DiscountRate = CASE @CustomerTier
        WHEN 'Platinum' THEN 0.1500
        WHEN 'Gold'     THEN 0.1000
        WHEN 'Silver'   THEN 0.0500
        WHEN 'Bronze'   THEN 0.0200
        ELSE 0.0000
    END;

    -- Holiday bonus (additional 5%)
    IF @IsHolidaySeason = 1
        SET @DiscountRate = @DiscountRate + 0.0500;

    -- Cap discount at 25%
    IF @DiscountRate > 0.2500
        SET @DiscountRate = 0.2500;

    SET @FinalDiscount = @OrderAmount * @DiscountRate;

    -- Minimum discount floor of $1 for orders over $50
    IF @OrderAmount > 50.0000 AND @FinalDiscount < 1.0000
        SET @FinalDiscount = 1.0000;

    RETURN @FinalDiscount;
END;
GO

-- ============================================================================
-- OBJECT 3: fn_GetCustomerTier (Scalar Function — standalone)
-- ============================================================================

CREATE FUNCTION dbo.fn_GetCustomerTier
(
    @TotalSpend DECIMAL(19, 4),
    @OrderCount INT,
    @AccountAgeDays INT
)
RETURNS VARCHAR(20)
AS
BEGIN
    DECLARE @Tier VARCHAR(20);

    SET @Tier = CASE
        WHEN @TotalSpend >= 10000 AND @OrderCount >= 50 AND @AccountAgeDays >= 730
            THEN 'Platinum'
        WHEN @TotalSpend >= 5000 AND @OrderCount >= 25 AND @AccountAgeDays >= 365
            THEN 'Gold'
        WHEN @TotalSpend >= 1000 AND @OrderCount >= 10
            THEN 'Silver'
        WHEN @TotalSpend >= 100 OR @OrderCount >= 3
            THEN 'Bronze'
        ELSE 'Standard'
    END;

    RETURN @Tier;
END;
GO

-- ============================================================================
-- OBJECT 4: usp_StageSalesData (Procedure — depends on vw_ActiveProducts)
-- Heavy: CTEs, window functions, temp tables, DATEDIFF, ISNULL, CASE
-- ============================================================================

CREATE PROCEDURE dbo.usp_StageSalesData
    @StartDate DATE,
    @EndDate DATE,
    @MinOrderAmount DECIMAL(19, 4) = 0.00
AS
BEGIN
    SET NOCOUNT ON;

    -- Drop temp table if exists
    IF OBJECT_ID('tempdb..#SalesStaging') IS NOT NULL
        DROP TABLE #SalesStaging;

    IF OBJECT_ID('tempdb..#DailySummary') IS NOT NULL
        DROP TABLE #DailySummary;

    -- CTE 1: Base orders with product enrichment
    ;WITH BaseOrders AS (
        SELECT
            o.OrderID,
            o.CustomerID,
            o.OrderDate,
            od.ProductID,
            ap.ProductName,
            ap.CategoryName,
            ap.PriceTier,
            od.Quantity,
            od.UnitPrice AS OrderUnitPrice,
            od.Quantity * od.UnitPrice AS LineTotal,
            ISNULL(od.Discount, 0) AS DiscountApplied,
            o.ShippingCost,
            o.OrderStatus,
            DATEDIFF(day, o.OrderDate, ISNULL(o.ShippedDate, GETDATE())) AS DaysToShip
        FROM dbo.Orders o
        INNER JOIN dbo.OrderDetails od ON o.OrderID = od.OrderID
        INNER JOIN dbo.vw_ActiveProducts ap ON od.ProductID = ap.ProductID
        WHERE o.OrderDate BETWEEN @StartDate AND @EndDate
          AND o.OrderStatus <> 'Cancelled'
          AND od.Quantity * od.UnitPrice >= @MinOrderAmount
    ),
    -- CTE 2: Ranked orders per customer
    RankedOrders AS (
        SELECT
            bo.*,
            ROW_NUMBER() OVER (
                PARTITION BY bo.CustomerID
                ORDER BY bo.OrderDate DESC
            ) AS CustomerOrderRank,
            SUM(bo.LineTotal) OVER (
                PARTITION BY bo.CustomerID
                ORDER BY bo.OrderDate
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS RunningCustomerTotal,
            COUNT(*) OVER (
                PARTITION BY bo.CategoryName
            ) AS CategoryOrderCount,
            NTILE(4) OVER (
                ORDER BY bo.LineTotal DESC
            ) AS RevenueQuartile
        FROM BaseOrders bo
    )
    SELECT
        ro.OrderID,
        ro.CustomerID,
        ro.OrderDate,
        ro.ProductID,
        ro.ProductName,
        ro.CategoryName,
        ro.PriceTier,
        ro.Quantity,
        ro.OrderUnitPrice,
        ro.LineTotal,
        ro.DiscountApplied,
        ro.ShippingCost,
        ro.OrderStatus,
        ro.DaysToShip,
        ro.CustomerOrderRank,
        ro.RunningCustomerTotal,
        ro.CategoryOrderCount,
        ro.RevenueQuartile,
        CASE
            WHEN ro.DaysToShip <= 2 THEN 'Fast'
            WHEN ro.DaysToShip <= 7 THEN 'Normal'
            WHEN ro.DaysToShip <= 14 THEN 'Slow'
            ELSE 'Delayed'
        END AS ShippingSpeed,
        CAST(ro.OrderDate AS DATE) AS OrderDateOnly,
        YEAR(ro.OrderDate) AS OrderYear,
        MONTH(ro.OrderDate) AS OrderMonth,
        DATEPART(weekday, ro.OrderDate) AS OrderDayOfWeek
    INTO #SalesStaging
    FROM RankedOrders ro;

    -- Create index on staging table
    CREATE CLUSTERED INDEX CX_SalesStaging_CustomerID ON #SalesStaging(CustomerID);
    CREATE NONCLUSTERED INDEX IX_SalesStaging_OrderDate ON #SalesStaging(OrderDate) INCLUDE (LineTotal, CategoryName);

    -- Build daily summary from staging
    SELECT
        OrderDateOnly AS SummaryDate,
        COUNT(DISTINCT OrderID) AS OrderCount,
        COUNT(DISTINCT CustomerID) AS UniqueCustomers,
        SUM(LineTotal) AS DailyRevenue,
        AVG(LineTotal) AS AvgOrderValue,
        MIN(LineTotal) AS MinOrderValue,
        MAX(LineTotal) AS MaxOrderValue,
        SUM(CASE WHEN ShippingSpeed = 'Fast' THEN 1 ELSE 0 END) AS FastShipCount,
        SUM(CASE WHEN ShippingSpeed = 'Delayed' THEN 1 ELSE 0 END) AS DelayedShipCount,
        STRING_AGG(DISTINCT CategoryName, ', ') AS CategoriesSold,
        SUM(DiscountApplied) AS TotalDiscounts,
        SUM(ShippingCost) AS TotalShipping
    INTO #DailySummary
    FROM #SalesStaging
    GROUP BY OrderDateOnly
    ORDER BY OrderDateOnly;

    -- Return both result sets
    SELECT * FROM #SalesStaging ORDER BY OrderDate DESC;
    SELECT * FROM #DailySummary ORDER BY SummaryDate;
END;
GO

-- ============================================================================
-- OBJECT 5: usp_BuildCustomerProfile
-- Depends on: fn_GetCustomerTier, usp_StageSalesData (uses its temp tables)
-- Heavy: cursor pattern (for dynamic tier calculation), DATEDIFF, aggregations
-- ============================================================================

CREATE PROCEDURE dbo.usp_BuildCustomerProfile
    @StartDate DATE,
    @EndDate DATE,
    @RecalculateTiers BIT = 1
AS
BEGIN
    SET NOCOUNT ON;

    -- First, stage the sales data
    EXEC dbo.usp_StageSalesData @StartDate, @EndDate;

    IF OBJECT_ID('tempdb..#CustomerProfile') IS NOT NULL
        DROP TABLE #CustomerProfile;

    -- Build customer profiles from staged data
    SELECT
        c.CustomerID,
        c.CustomerName,
        c.Email,
        ISNULL(c.Region, 'Unknown') AS Region,
        c.RegistrationDate,
        DATEDIFF(day, c.RegistrationDate, GETDATE()) AS AccountAgeDays,
        COUNT(DISTINCT s.OrderID) AS TotalOrders,
        ISNULL(SUM(s.LineTotal), 0) AS TotalSpend,
        ISNULL(AVG(s.LineTotal), 0) AS AvgOrderValue,
        MIN(s.OrderDate) AS FirstOrderDate,
        MAX(s.OrderDate) AS LastOrderDate,
        DATEDIFF(day, MAX(s.OrderDate), GETDATE()) AS DaysSinceLastOrder,
        ISNULL(AVG(CAST(s.DaysToShip AS DECIMAL(10, 2))), 0) AS AvgDaysToShip,
        COUNT(DISTINCT s.CategoryName) AS UniqueCategoriesPurchased,
        MAX(s.RunningCustomerTotal) AS LifetimeValue,
        CASE
            WHEN DATEDIFF(day, MAX(s.OrderDate), GETDATE()) <= 30 THEN 'Active'
            WHEN DATEDIFF(day, MAX(s.OrderDate), GETDATE()) <= 90 THEN 'Warm'
            WHEN DATEDIFF(day, MAX(s.OrderDate), GETDATE()) <= 180 THEN 'Cooling'
            ELSE 'Dormant'
        END AS EngagementStatus
    INTO #CustomerProfile
    FROM dbo.Customers c
    LEFT JOIN #SalesStaging s ON c.CustomerID = s.CustomerID
    WHERE c.IsActive = 1
    GROUP BY
        c.CustomerID, c.CustomerName, c.Email,
        c.Region, c.RegistrationDate;

    -- Recalculate tiers if requested
    IF @RecalculateTiers = 1
    BEGIN
        -- Use cursor to calculate tier for each customer
        -- (demonstrates cursor pattern — would be vectorized in PySpark)
        DECLARE @CustID INT, @Spend DECIMAL(19, 4), @Orders INT, @AgeDays INT;
        DECLARE @NewTier VARCHAR(20);

        DECLARE tier_cursor CURSOR LOCAL FAST_FORWARD FOR
            SELECT CustomerID, TotalSpend, TotalOrders, AccountAgeDays
            FROM #CustomerProfile;

        OPEN tier_cursor;
        FETCH NEXT FROM tier_cursor INTO @CustID, @Spend, @Orders, @AgeDays;

        WHILE @@FETCH_STATUS = 0
        BEGIN
            SET @NewTier = dbo.fn_GetCustomerTier(@Spend, @Orders, @AgeDays);

            UPDATE #CustomerProfile
            SET EngagementStatus = EngagementStatus + ' (' + @NewTier + ')'
            WHERE CustomerID = @CustID;

            FETCH NEXT FROM tier_cursor INTO @CustID, @Spend, @Orders, @AgeDays;
        END;

        CLOSE tier_cursor;
        DEALLOCATE tier_cursor;
    END;

    -- Add ranking columns
    SELECT
        cp.*,
        ROW_NUMBER() OVER (ORDER BY cp.TotalSpend DESC) AS SpendRank,
        PERCENT_RANK() OVER (ORDER BY cp.TotalSpend) AS SpendPercentile,
        DENSE_RANK() OVER (PARTITION BY cp.Region ORDER BY cp.TotalSpend DESC) AS RegionalRank,
        LAG(cp.TotalSpend) OVER (PARTITION BY cp.Region ORDER BY cp.TotalSpend DESC) AS PrevCustomerSpend,
        LEAD(cp.TotalSpend) OVER (PARTITION BY cp.Region ORDER BY cp.TotalSpend DESC) AS NextCustomerSpend
    FROM #CustomerProfile cp
    ORDER BY cp.TotalSpend DESC;
END;
GO

-- ============================================================================
-- OBJECT 6: usp_CalculateRevenue
-- Depends on: fn_CalculateDiscount, usp_StageSalesData (uses its temp tables)
-- Heavy: PIVOT, DATEDIFF, complex aggregations, CASE with math
-- ============================================================================

CREATE PROCEDURE dbo.usp_CalculateRevenue
    @StartDate DATE,
    @EndDate DATE,
    @IncludeProjections BIT = 0
AS
BEGIN
    SET NOCOUNT ON;

    -- Stage the base data
    EXEC dbo.usp_StageSalesData @StartDate, @EndDate;

    IF OBJECT_ID('tempdb..#RevenueCalc') IS NOT NULL
        DROP TABLE #RevenueCalc;

    -- Calculate revenue metrics with discount application
    SELECT
        s.OrderID,
        s.CustomerID,
        s.OrderDate,
        s.CategoryName,
        s.LineTotal AS GrossRevenue,
        dbo.fn_CalculateDiscount(s.LineTotal, s.PriceTier,
            CASE WHEN MONTH(s.OrderDate) IN (11, 12) THEN 1 ELSE 0 END
        ) AS CalculatedDiscount,
        s.LineTotal - dbo.fn_CalculateDiscount(s.LineTotal, s.PriceTier,
            CASE WHEN MONTH(s.OrderDate) IN (11, 12) THEN 1 ELSE 0 END
        ) AS NetRevenue,
        s.ShippingCost,
        s.LineTotal - dbo.fn_CalculateDiscount(s.LineTotal, s.PriceTier,
            CASE WHEN MONTH(s.OrderDate) IN (11, 12) THEN 1 ELSE 0 END
        ) - s.ShippingCost AS Profit,
        CASE
            WHEN s.LineTotal > 500 THEN 'High Value'
            WHEN s.LineTotal > 100 THEN 'Medium Value'
            ELSE 'Low Value'
        END AS OrderValueSegment,
        s.OrderYear,
        s.OrderMonth,
        DATEDIFF(month, @StartDate, s.OrderDate) AS MonthsFromStart
    INTO #RevenueCalc
    FROM #SalesStaging s;

    -- Monthly revenue summary
    SELECT
        OrderYear,
        OrderMonth,
        COUNT(DISTINCT OrderID) AS Orders,
        SUM(GrossRevenue) AS TotalGross,
        SUM(CalculatedDiscount) AS TotalDiscounts,
        SUM(NetRevenue) AS TotalNet,
        SUM(Profit) AS TotalProfit,
        CAST(SUM(Profit) AS DECIMAL(19, 4)) / NULLIF(SUM(GrossRevenue), 0) * 100 AS ProfitMarginPct,
        SUM(SUM(NetRevenue)) OVER (
            ORDER BY OrderYear, OrderMonth
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS CumulativeRevenue,
        AVG(SUM(NetRevenue)) OVER (
            ORDER BY OrderYear, OrderMonth
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS ThreeMonthAvg,
        SUM(NetRevenue) - LAG(SUM(NetRevenue)) OVER (ORDER BY OrderYear, OrderMonth) AS MoMGrowth
    FROM #RevenueCalc
    GROUP BY OrderYear, OrderMonth
    ORDER BY OrderYear, OrderMonth;

    -- Category revenue pivot
    SELECT *
    FROM (
        SELECT CategoryName, OrderMonth, NetRevenue
        FROM #RevenueCalc
    ) AS src
    PIVOT (
        SUM(NetRevenue)
        FOR OrderMonth IN ([1],[2],[3],[4],[5],[6],[7],[8],[9],[10],[11],[12])
    ) AS pvt
    ORDER BY CategoryName;

    -- Projections (if requested)
    IF @IncludeProjections = 1
    BEGIN
        ;WITH MonthlyTrend AS (
            SELECT
                OrderYear,
                OrderMonth,
                SUM(NetRevenue) AS MonthlyRevenue,
                ROW_NUMBER() OVER (ORDER BY OrderYear, OrderMonth) AS MonthSeq
            FROM #RevenueCalc
            GROUP BY OrderYear, OrderMonth
        ),
        TrendCalc AS (
            SELECT
                AVG(MonthlyRevenue) AS AvgMonthly,
                COUNT(*) AS DataPoints,
                (COUNT(*) * SUM(MonthSeq * MonthlyRevenue) - SUM(MonthSeq) * SUM(MonthlyRevenue))
                / NULLIF(COUNT(*) * SUM(MonthSeq * MonthSeq) - SUM(MonthSeq) * SUM(MonthSeq), 0)
                AS TrendSlope
            FROM MonthlyTrend
        )
        SELECT
            'Next Quarter Projection' AS Label,
            AvgMonthly * 3 + ISNULL(TrendSlope, 0) * (DataPoints + 1.5) * 3 AS ProjectedRevenue,
            AvgMonthly AS BaselineMonthly,
            TrendSlope AS MonthlyTrend,
            DataPoints AS MonthsAnalyzed
        FROM TrendCalc;
    END;
END;
GO

-- ============================================================================
-- OBJECT 7: usp_GenerateReport
-- Depends on: usp_BuildCustomerProfile, usp_CalculateRevenue
-- Heavy: calls other procs, MERGE pattern, complex aggregations, JSON output
-- ============================================================================

CREATE PROCEDURE dbo.usp_GenerateReport
    @StartDate DATE,
    @EndDate DATE,
    @ReportType VARCHAR(50) = 'Full'
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        BEGIN TRANSACTION;

        -- Run dependent procedures
        EXEC dbo.usp_BuildCustomerProfile @StartDate, @EndDate;
        EXEC dbo.usp_CalculateRevenue @StartDate, @EndDate, @IncludeProjections = 1;

        -- Executive summary
        IF @ReportType IN ('Full', 'Summary')
        BEGIN
            SELECT
                @StartDate AS ReportStartDate,
                @EndDate AS ReportEndDate,
                DATEDIFF(day, @StartDate, @EndDate) AS ReportDays,
                (SELECT COUNT(DISTINCT CustomerID) FROM #SalesStaging) AS TotalCustomers,
                (SELECT COUNT(DISTINCT OrderID) FROM #SalesStaging) AS TotalOrders,
                (SELECT SUM(LineTotal) FROM #SalesStaging) AS GrossRevenue,
                (SELECT SUM(LineTotal) FROM #RevenueCalc) AS GrossRevenueCalc,
                (SELECT SUM(NetRevenue) FROM #RevenueCalc) AS NetRevenue,
                (SELECT SUM(Profit) FROM #RevenueCalc) AS TotalProfit,
                (SELECT AVG(LineTotal) FROM #SalesStaging) AS AvgOrderValue,
                (SELECT COUNT(DISTINCT CategoryName) FROM #SalesStaging) AS CategoriesActive;
        END;

        -- Top customers
        IF @ReportType IN ('Full', 'Customers')
        BEGIN
            SELECT TOP 20
                cp.CustomerID,
                cp.CustomerName,
                cp.Region,
                cp.TotalOrders,
                cp.TotalSpend,
                cp.AvgOrderValue,
                cp.EngagementStatus,
                cp.SpendRank,
                cp.SpendPercentile,
                cp.DaysSinceLastOrder,
                CASE
                    WHEN cp.DaysSinceLastOrder <= 30 AND cp.TotalSpend > 1000 THEN 'Retain (VIP Active)'
                    WHEN cp.DaysSinceLastOrder <= 90 AND cp.TotalSpend > 500 THEN 'Engage (High Potential)'
                    WHEN cp.DaysSinceLastOrder > 180 AND cp.TotalSpend > 1000 THEN 'Win Back (Lapsed VIP)'
                    WHEN cp.DaysSinceLastOrder > 90 THEN 'Re-engage'
                    ELSE 'Monitor'
                END AS ActionRecommendation
            FROM #CustomerProfile cp
            ORDER BY cp.TotalSpend DESC;
        END;

        -- Category performance
        IF @ReportType IN ('Full', 'Categories')
        BEGIN
            SELECT
                s.CategoryName,
                COUNT(DISTINCT s.OrderID) AS Orders,
                COUNT(DISTINCT s.CustomerID) AS UniqueCustomers,
                SUM(s.LineTotal) AS Revenue,
                AVG(s.LineTotal) AS AvgOrderValue,
                SUM(s.LineTotal) * 100.0 / NULLIF(SUM(SUM(s.LineTotal)) OVER (), 0) AS RevenueSharePct,
                ROW_NUMBER() OVER (ORDER BY SUM(s.LineTotal) DESC) AS RevenueRank,
                SUM(r.Profit) AS CategoryProfit,
                CAST(SUM(r.Profit) AS DECIMAL(19, 4)) / NULLIF(SUM(s.LineTotal), 0) * 100 AS MarginPct
            FROM #SalesStaging s
            LEFT JOIN #RevenueCalc r ON s.OrderID = r.OrderID AND s.ProductID = r.ProductID
            GROUP BY s.CategoryName
            ORDER BY Revenue DESC;
        END;

        -- Log report generation
        INSERT INTO dbo.ReportLog (ReportType, StartDate, EndDate, GeneratedAt, GeneratedBy)
        VALUES (@ReportType, @StartDate, @EndDate, GETDATE(), SYSTEM_USER);

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        DECLARE @ErrorMessage NVARCHAR(4000) = ERROR_MESSAGE();
        DECLARE @ErrorSeverity INT = ERROR_SEVERITY();
        DECLARE @ErrorLine INT = ERROR_LINE();

        INSERT INTO dbo.ErrorLog (ErrorMessage, ErrorSeverity, ErrorLine, OccurredAt)
        VALUES (@ErrorMessage, @ErrorSeverity, @ErrorLine, GETDATE());

        RAISERROR(@ErrorMessage, @ErrorSeverity, 1);
    END CATCH;
END;
GO

-- ============================================================================
-- OBJECT 8: trg_AuditOrderChanges (Trigger — standalone, references Orders)
-- Demonstrates: INSERTED/DELETED pseudo-tables, COLUMNS_UPDATED
-- ============================================================================

CREATE TRIGGER dbo.trg_AuditOrderChanges
ON dbo.Orders
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO dbo.OrderAuditLog
    (
        OrderID,
        FieldChanged,
        OldValue,
        NewValue,
        ChangedAt,
        ChangedBy
    )
    SELECT
        i.OrderID,
        'OrderStatus',
        d.OrderStatus,
        i.OrderStatus,
        GETDATE(),
        SYSTEM_USER
    FROM inserted i
    INNER JOIN deleted d ON i.OrderID = d.OrderID
    WHERE i.OrderStatus <> d.OrderStatus;

    -- Track shipping date changes
    INSERT INTO dbo.OrderAuditLog
    (
        OrderID,
        FieldChanged,
        OldValue,
        NewValue,
        ChangedAt,
        ChangedBy
    )
    SELECT
        i.OrderID,
        'ShippedDate',
        CAST(d.ShippedDate AS VARCHAR(30)),
        CAST(i.ShippedDate AS VARCHAR(30)),
        GETDATE(),
        SYSTEM_USER
    FROM inserted i
    INNER JOIN deleted d ON i.OrderID = d.OrderID
    WHERE ISNULL(i.ShippedDate, '1900-01-01') <> ISNULL(d.ShippedDate, '1900-01-01');

    -- Track total amount changes (financial audit)
    INSERT INTO dbo.OrderAuditLog
    (
        OrderID,
        FieldChanged,
        OldValue,
        NewValue,
        ChangedAt,
        ChangedBy
    )
    SELECT
        i.OrderID,
        'TotalAmount',
        CAST(d.TotalAmount AS VARCHAR(30)),
        CAST(i.TotalAmount AS VARCHAR(30)),
        GETDATE(),
        SYSTEM_USER
    FROM inserted i
    INNER JOIN deleted d ON i.OrderID = d.OrderID
    WHERE i.TotalAmount <> d.TotalAmount;
END;
GO
