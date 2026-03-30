USE AdventureWorks2019;
GO

SET NOCOUNT ON;
GO

-- ============================================================
-- OBJECT 1: Run Log Table
-- ============================================================
IF OBJECT_ID('dbo.AW19_RunLog', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.AW19_RunLog (
        RunId           UNIQUEIDENTIFIER NOT NULL,
        ProcName        SYSNAME          NOT NULL,
        StepName        NVARCHAR(200)    NOT NULL,
        StepStatus      NVARCHAR(30)     NOT NULL,
        Message         NVARCHAR(2000)   NULL,
        StartedUtc      DATETIME2(3)     NOT NULL DEFAULT SYSUTCDATETIME(),
        CompletedUtc    DATETIME2(3)     NULL,
        CONSTRAINT PK_AW19_RunLog PRIMARY KEY (RunId, StepName, StartedUtc)
    );
END
GO

-- ============================================================
-- OBJECT 2: Logging Helper Procedure
-- ============================================================
CREATE OR ALTER PROCEDURE dbo.usp_AW19_Log
    @RunId       UNIQUEIDENTIFIER,
    @ProcName    SYSNAME,
    @StepName    NVARCHAR(200),
    @StepStatus  NVARCHAR(30),
    @Message     NVARCHAR(2000) = NULL,
    @Complete    BIT = 0
AS
BEGIN
    SET NOCOUNT ON;
    INSERT dbo.AW19_RunLog (RunId, ProcName, StepName, StepStatus, Message, CompletedUtc)
    VALUES (@RunId, @ProcName, @StepName, @StepStatus, @Message,
            CASE WHEN @Complete = 1 THEN SYSUTCDATETIME() ELSE NULL END);
END
GO

-- ============================================================
-- OBJECT 3: Helper Function - Split CSV to INT
-- ============================================================
CREATE OR ALTER FUNCTION dbo.ufn_AW19_SplitCsvInt (@csv NVARCHAR(MAX))
RETURNS @t TABLE (Item INT NOT NULL)
AS
BEGIN
    DECLARE @x     NVARCHAR(MAX) = COALESCE(@csv, N'');
    DECLARE @pos   INT = 1, @next INT, @token NVARCHAR(100);
    SET @x = REPLACE(REPLACE(@x, CHAR(10), N''), CHAR(13), N'') + N',';
    WHILE @pos <= LEN(@x)
    BEGIN
        SET @next = CHARINDEX(N',', @x, @pos);
        IF @next = 0 BREAK;
        SET @token = LTRIM(RTRIM(SUBSTRING(@x, @pos, @next - @pos)));
        IF @token <> N'' AND TRY_CONVERT(INT, @token) IS NOT NULL
            INSERT @t (Item) VALUES (CONVERT(INT, @token));
        SET @pos = @next + 1;
    END
    RETURN;
END
GO

-- ============================================================
-- OBJECT 4: Pricing Rules Reference Table
-- ============================================================
IF OBJECT_ID('dbo.AW19_PricingRules', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.AW19_PricingRules (
        RuleId          INT IDENTITY(1,1) PRIMARY KEY,
        CategoryName    NVARCHAR(100)    NOT NULL,
        SubCategoryName NVARCHAR(100)    NULL,
        TerritoryGroup  NVARCHAR(50)     NOT NULL,
        CustomerTier    NVARCHAR(30)     NOT NULL,
        DiscountPct     DECIMAL(5,4)     NOT NULL DEFAULT 0,
        CommissionPct   DECIMAL(5,4)     NOT NULL DEFAULT 0,
        TaxOverridePct  DECIMAL(5,4)     NULL,
        EffectiveDate   DATE             NOT NULL,
        ExpiryDate      DATE             NULL
    );
END
GO

TRUNCATE TABLE dbo.AW19_PricingRules;
GO

INSERT dbo.AW19_PricingRules
    (CategoryName, SubCategoryName, TerritoryGroup, CustomerTier, DiscountPct, CommissionPct, TaxOverridePct, EffectiveDate)
VALUES
  ('Bikes','Mountain Bikes','North America','Gold',    0.1200,0.0500,NULL,  '2019-01-01'),
  ('Bikes','Mountain Bikes','North America','Silver',  0.0800,0.0450,NULL,  '2019-01-01'),
  ('Bikes','Mountain Bikes','North America','Bronze',  0.0500,0.0400,NULL,  '2019-01-01'),
  ('Bikes','Mountain Bikes','North America','Standard',0.0000,0.0350,NULL,  '2019-01-01'),
  ('Bikes','Mountain Bikes','Europe',       'Gold',    0.1300,0.0520,0.2000,'2019-01-01'),
  ('Bikes','Mountain Bikes','Europe',       'Silver',  0.0900,0.0470,0.2000,'2019-01-01'),
  ('Bikes','Mountain Bikes','Europe',       'Bronze',  0.0600,0.0420,0.2000,'2019-01-01'),
  ('Bikes','Mountain Bikes','Europe',       'Standard',0.0100,0.0370,0.2000,'2019-01-01'),
  ('Bikes','Mountain Bikes','Pacific',      'Gold',    0.1100,0.0480,0.1000,'2019-01-01'),
  ('Bikes','Mountain Bikes','Pacific',      'Silver',  0.0750,0.0430,0.1000,'2019-01-01'),
  ('Bikes','Road Bikes',    'North America','Gold',    0.1150,0.0510,NULL,  '2019-01-01'),
  ('Bikes','Road Bikes',    'North America','Silver',  0.0780,0.0460,NULL,  '2019-01-01'),
  ('Bikes','Road Bikes',    'North America','Bronze',  0.0480,0.0410,NULL,  '2019-01-01'),
  ('Bikes','Road Bikes',    'North America','Standard',0.0000,0.0360,NULL,  '2019-01-01'),
  ('Bikes','Road Bikes',    'Europe',       'Gold',    0.1250,0.0530,0.2000,'2019-01-01'),
  ('Bikes','Road Bikes',    'Europe',       'Silver',  0.0850,0.0480,0.2000,'2019-01-01'),
  ('Bikes','Road Bikes',    'Pacific',      'Gold',    0.1050,0.0490,0.1000,'2019-01-01'),
  ('Bikes','Touring Bikes', 'North America','Gold',    0.1100,0.0500,NULL,  '2019-01-01'),
  ('Bikes','Touring Bikes', 'Europe',       'Gold',    0.1200,0.0520,0.2000,'2019-01-01'),
  ('Components',NULL,       'North America','Gold',    0.0800,0.0300,NULL,  '2019-01-01'),
  ('Components',NULL,       'North America','Silver',  0.0600,0.0280,NULL,  '2019-01-01'),
  ('Components',NULL,       'North America','Bronze',  0.0400,0.0260,NULL,  '2019-01-01'),
  ('Components',NULL,       'North America','Standard',0.0000,0.0240,NULL,  '2019-01-01'),
  ('Components',NULL,       'Europe',       'Gold',    0.0850,0.0320,0.2000,'2019-01-01'),
  ('Components',NULL,       'Europe',       'Silver',  0.0650,0.0300,0.2000,'2019-01-01'),
  ('Clothing',NULL,         'North America','Gold',    0.1500,0.0200,NULL,  '2019-01-01'),
  ('Clothing',NULL,         'North America','Silver',  0.1000,0.0180,NULL,  '2019-01-01'),
  ('Clothing',NULL,         'North America','Bronze',  0.0700,0.0160,NULL,  '2019-01-01'),
  ('Clothing',NULL,         'North America','Standard',0.0200,0.0140,NULL,  '2019-01-01'),
  ('Clothing',NULL,         'Europe',       'Gold',    0.1600,0.0220,0.2000,'2019-01-01'),
  ('Clothing',NULL,         'Europe',       'Silver',  0.1100,0.0200,0.2000,'2019-01-01'),
  ('Accessories',NULL,      'North America','Gold',    0.1000,0.0250,NULL,  '2019-01-01'),
  ('Accessories',NULL,      'North America','Silver',  0.0700,0.0230,NULL,  '2019-01-01'),
  ('Accessories',NULL,      'North America','Bronze',  0.0500,0.0210,NULL,  '2019-01-01'),
  ('Accessories',NULL,      'North America','Standard',0.0000,0.0190,NULL,  '2019-01-01'),
  ('Accessories',NULL,      'Europe',       'Gold',    0.1050,0.0270,0.2000,'2019-01-01'),
  ('Accessories',NULL,      'Pacific',      'Gold',    0.0950,0.0260,0.1000,'2019-01-01');
GO

-- ============================================================
-- MAIN PROCEDURE: usp_AW19_SalesCommissionPricingPipeline
-- ============================================================
CREATE OR ALTER PROCEDURE dbo.usp_AW19_SalesCommissionPricingPipeline
    @StartDate            DATE          = NULL,
    @EndDate              DATE          = NULL,
    @TerritoryGroupFilter NVARCHAR(50)  = NULL,
    @CustomerIdsCsv       NVARCHAR(MAX) = NULL,
    @MinOrderAmt          DECIMAL(10,2) = 0,
    @TopNSalesPerson      INT           = 10,
    @EmitDebug            BIT           = 0
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @RunId    UNIQUEIDENTIFIER = NEWID();
    DECLARE @ProcName SYSNAME          = N'usp_AW19_SalesCommissionPricingPipeline';

    EXEC dbo.usp_AW19_Log @RunId, @ProcName, N'START', N'START', N'Pipeline initiated', 0;

    IF @StartDate IS NULL OR @EndDate IS NULL
    BEGIN
        SELECT
            @StartDate = COALESCE(@StartDate, CAST(MIN(OrderDate) AS DATE)),
            @EndDate   = COALESCE(@EndDate,   CAST(MAX(OrderDate) AS DATE))
        FROM Sales.SalesOrderHeader;
    END

    BEGIN TRY

    -- STEP 1: Customer filter
    IF OBJECT_ID('tempdb..#CustomerFilter') IS NOT NULL DROP TABLE #CustomerFilter;
    SELECT Item AS CustomerID
    INTO #CustomerFilter
    FROM dbo.ufn_AW19_SplitCsvInt(@CustomerIdsCsv);

    DECLARE @HasCustFilter BIT =
        CASE WHEN EXISTS (SELECT 1 FROM #CustomerFilter) THEN 1 ELSE 0 END;

    EXEC dbo.usp_AW19_Log @RunId, @ProcName, N'STEP1_CustomerFilter', N'OK', NULL, 0;

    -- STEP 2: Base orders
    IF OBJECT_ID('tempdb..#BaseOrders') IS NOT NULL DROP TABLE #BaseOrders;

    SELECT
        h.SalesOrderID,
        h.CustomerID,
        h.SalesPersonID,
        CAST(h.OrderDate AS DATE)                                      AS OrderDate,
        CAST(h.ShipDate  AS DATE)                                      AS ShipDate,
        h.SubTotal,
        h.TaxAmt,
        h.Freight,
        h.TotalDue,
        h.OnlineOrderFlag,
        h.RevisionNumber,
        st.Name                                                        AS TerritoryName,
        st.CountryRegionCode,
        st.[Group]                                                     AS TerritoryGroup,
        COALESCE(sp.FirstName + ' ' + sp.LastName, 'Online/Unknown')  AS SalesPersonName,
        e.JobTitle                                                     AS SalesPersonTitle,
        COALESCE(sqa.SalesQuota, 0)                                    AS SalesQuota
    INTO #BaseOrders
    FROM Sales.SalesOrderHeader           h
    JOIN Sales.SalesTerritory             st  ON st.TerritoryID       = h.TerritoryID
    LEFT JOIN Sales.SalesPerson           sp2 ON sp2.BusinessEntityID = h.SalesPersonID
    LEFT JOIN Person.Person               sp  ON sp.BusinessEntityID  = h.SalesPersonID
    LEFT JOIN HumanResources.Employee     e   ON e.BusinessEntityID   = h.SalesPersonID
    LEFT JOIN (
        SELECT BusinessEntityID, SUM(SalesQuota) AS SalesQuota
        FROM Sales.SalesPersonQuotaHistory
        WHERE CAST(QuotaDate AS DATE) BETWEEN @StartDate AND @EndDate
        GROUP BY BusinessEntityID
    ) sqa ON sqa.BusinessEntityID = h.SalesPersonID
    WHERE CAST(h.OrderDate AS DATE) BETWEEN @StartDate AND @EndDate
      AND h.TotalDue >= @MinOrderAmt
      AND (@TerritoryGroupFilter IS NULL OR st.[Group] = @TerritoryGroupFilter)
      AND (@HasCustFilter = 0
           OR EXISTS (SELECT 1 FROM #CustomerFilter cf WHERE cf.CustomerID = h.CustomerID));

    CREATE CLUSTERED INDEX CX_BaseOrders ON #BaseOrders (SalesOrderID);
    CREATE INDEX IX_BaseOrders_Cust      ON #BaseOrders (CustomerID)    INCLUDE (TotalDue, TerritoryGroup, OrderDate);
    CREATE INDEX IX_BaseOrders_SP        ON #BaseOrders (SalesPersonID) INCLUDE (TotalDue, TerritoryGroup);

    EXEC dbo.usp_AW19_Log @RunId, @ProcName, N'STEP2_BaseOrders', N'OK', NULL, 0;

    -- STEP 3: Line-level detail
    IF OBJECT_ID('tempdb..#Lines') IS NOT NULL DROP TABLE #Lines;

    SELECT
        d.SalesOrderID,
        d.SalesOrderDetailID,
        d.ProductID,
        d.OrderQty,
        d.UnitPrice,
        d.UnitPriceDiscount,
        d.LineTotal,
        p.Name                       AS ProductName,
        p.ProductNumber,
        p.Color,
        p.ListPrice,
        p.StandardCost,
        p.ListPrice - p.StandardCost AS GrossMarginUnit,
        ps.Name                      AS SubCategoryName,
        pc.Name                      AS CategoryName,
        pm.Name                      AS ModelName,
        b.OrderDate,
        b.TerritoryGroup,
        b.TerritoryName,
        b.CountryRegionCode,
        b.CustomerID,
        b.SalesPersonID,
        b.SalesPersonName,
        b.OnlineOrderFlag
    INTO #Lines
    FROM Sales.SalesOrderDetail             d
    JOIN #BaseOrders                        b  ON b.SalesOrderID              = d.SalesOrderID
    JOIN Production.Product                 p  ON p.ProductID                 = d.ProductID
    LEFT JOIN Production.ProductSubcategory ps ON ps.ProductSubcategoryID     = p.ProductSubcategoryID
    LEFT JOIN Production.ProductCategory    pc ON pc.ProductCategoryID        = ps.ProductCategoryID
    LEFT JOIN Production.ProductModel       pm ON pm.ProductModelID           = p.ProductModelID;

    CREATE CLUSTERED INDEX CX_Lines  ON #Lines (SalesOrderID, SalesOrderDetailID);
    CREATE INDEX IX_Lines_Cat        ON #Lines (CategoryName, SubCategoryName, TerritoryGroup)
        INCLUDE (LineTotal, OrderQty, UnitPrice, UnitPriceDiscount);
    CREATE INDEX IX_Lines_SP         ON #Lines (SalesPersonID) INCLUDE (LineTotal, CategoryName);

    EXEC dbo.usp_AW19_Log @RunId, @ProcName, N'STEP3_Lines', N'OK', NULL, 0;

    -- STEP 4: Customer tier classification
    IF OBJECT_ID('tempdb..#CustomerTier') IS NOT NULL DROP TABLE #CustomerTier;

    WITH CustRevenue AS (
        SELECT
            l.CustomerID,
            l.TerritoryGroup,
            SUM(l.LineTotal)                                                   AS TotalRevenue,
            SUM(CASE WHEN l.CategoryName = 'Bikes'       THEN l.LineTotal ELSE 0 END) AS BikeRevenue,
            SUM(CASE WHEN l.CategoryName = 'Components'  THEN l.LineTotal ELSE 0 END) AS CompRevenue,
            SUM(CASE WHEN l.CategoryName = 'Clothing'    THEN l.LineTotal ELSE 0 END) AS ClothingRevenue,
            SUM(CASE WHEN l.CategoryName = 'Accessories' THEN l.LineTotal ELSE 0 END) AS AccessRevenue,
            COUNT(DISTINCT l.SalesOrderID)                                     AS OrderCount
        FROM #Lines l
        GROUP BY l.CustomerID, l.TerritoryGroup
    )
    SELECT
        CustomerID,
        TerritoryGroup,
        TotalRevenue,
        BikeRevenue,
        CompRevenue,
        ClothingRevenue,
        AccessRevenue,
        OrderCount,
        CASE
            WHEN TerritoryGroup = 'North America' THEN
                CASE WHEN TotalRevenue >= 50000 THEN 'Gold'
                     WHEN TotalRevenue >= 20000 THEN 'Silver'
                     WHEN TotalRevenue >= 5000  THEN 'Bronze'
                     ELSE 'Standard' END
            WHEN TerritoryGroup = 'Europe' THEN
                CASE WHEN TotalRevenue >= 45000 THEN 'Gold'
                     WHEN TotalRevenue >= 18000 THEN 'Silver'
                     WHEN TotalRevenue >= 4500  THEN 'Bronze'
                     ELSE 'Standard' END
            WHEN TerritoryGroup = 'Pacific' THEN
                CASE WHEN TotalRevenue >= 40000 THEN 'Gold'
                     WHEN TotalRevenue >= 15000 THEN 'Silver'
                     WHEN TotalRevenue >= 4000  THEN 'Bronze'
                     ELSE 'Standard' END
            ELSE
                CASE WHEN TotalRevenue >= 50000 THEN 'Gold'
                     WHEN TotalRevenue >= 20000 THEN 'Silver'
                     WHEN TotalRevenue >= 5000  THEN 'Bronze'
                     ELSE 'Standard' END
        END AS CustomerTier
    INTO #CustomerTier
    FROM CustRevenue;

    CREATE CLUSTERED INDEX CX_CustTier ON #CustomerTier (CustomerID, TerritoryGroup);

    EXEC dbo.usp_AW19_Log @RunId, @ProcName, N'STEP4_CustomerTier', N'OK', NULL, 0;

    -- STEP 5: Pricing engine - Massive CASE blocks
    IF OBJECT_ID('tempdb..#PricedLines') IS NOT NULL DROP TABLE #PricedLines;

    SELECT
        l.*,
        ct.CustomerTier,

        -- CASE Block A: Discount %
        CASE
          WHEN l.CategoryName = 'Bikes' AND l.SubCategoryName = 'Mountain Bikes' THEN
            CASE l.TerritoryGroup
              WHEN 'North America' THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.1200 WHEN 'Silver' THEN 0.0800 WHEN 'Bronze' THEN 0.0500 ELSE 0.0000 END
              WHEN 'Europe'        THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.1300 WHEN 'Silver' THEN 0.0900 WHEN 'Bronze' THEN 0.0600 ELSE 0.0100 END
              WHEN 'Pacific'       THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.1100 WHEN 'Silver' THEN 0.0750 WHEN 'Bronze' THEN 0.0500 ELSE 0.0000 END
              ELSE 0.0000 END
          WHEN l.CategoryName = 'Bikes' AND l.SubCategoryName = 'Road Bikes' THEN
            CASE l.TerritoryGroup
              WHEN 'North America' THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.1150 WHEN 'Silver' THEN 0.0780 WHEN 'Bronze' THEN 0.0480 ELSE 0.0000 END
              WHEN 'Europe'        THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.1250 WHEN 'Silver' THEN 0.0850 WHEN 'Bronze' THEN 0.0600 ELSE 0.0100 END
              WHEN 'Pacific'       THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.1050 WHEN 'Silver' THEN 0.0720 WHEN 'Bronze' THEN 0.0470 ELSE 0.0000 END
              ELSE 0.0000 END
          WHEN l.CategoryName = 'Bikes' AND l.SubCategoryName = 'Touring Bikes' THEN
            CASE l.TerritoryGroup
              WHEN 'North America' THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.1100 WHEN 'Silver' THEN 0.0750 WHEN 'Bronze' THEN 0.0460 ELSE 0.0000 END
              WHEN 'Europe'        THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.1200 WHEN 'Silver' THEN 0.0830 WHEN 'Bronze' THEN 0.0560 ELSE 0.0080 END
              ELSE CASE ct.CustomerTier WHEN 'Gold' THEN 0.1000 WHEN 'Silver' THEN 0.0700 ELSE 0.0000 END END
          WHEN l.CategoryName = 'Components' THEN
            CASE l.TerritoryGroup
              WHEN 'North America' THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.0800 WHEN 'Silver' THEN 0.0600 WHEN 'Bronze' THEN 0.0400 ELSE 0.0000 END
              WHEN 'Europe'        THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.0850 WHEN 'Silver' THEN 0.0650 WHEN 'Bronze' THEN 0.0430 ELSE 0.0050 END
              WHEN 'Pacific'       THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.0780 WHEN 'Silver' THEN 0.0580 WHEN 'Bronze' THEN 0.0380 ELSE 0.0000 END
              ELSE 0.0000 END
          WHEN l.CategoryName = 'Clothing' THEN
            CASE l.TerritoryGroup
              WHEN 'North America' THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.1500 WHEN 'Silver' THEN 0.1000 WHEN 'Bronze' THEN 0.0700 ELSE 0.0200 END
              WHEN 'Europe'        THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.1600 WHEN 'Silver' THEN 0.1100 WHEN 'Bronze' THEN 0.0780 ELSE 0.0250 END
              WHEN 'Pacific'       THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.1400 WHEN 'Silver' THEN 0.0950 WHEN 'Bronze' THEN 0.0660 ELSE 0.0180 END
              ELSE CASE ct.CustomerTier WHEN 'Gold' THEN 0.1300 WHEN 'Silver' THEN 0.0900 ELSE 0.0150 END END
          WHEN l.CategoryName = 'Accessories' THEN
            CASE l.TerritoryGroup
              WHEN 'North America' THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.1000 WHEN 'Silver' THEN 0.0700 WHEN 'Bronze' THEN 0.0500 ELSE 0.0000 END
              WHEN 'Europe'        THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.1050 WHEN 'Silver' THEN 0.0730 WHEN 'Bronze' THEN 0.0520 ELSE 0.0000 END
              WHEN 'Pacific'       THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.0950 WHEN 'Silver' THEN 0.0680 WHEN 'Bronze' THEN 0.0480 ELSE 0.0000 END
              ELSE 0.0000 END
          ELSE 0.0000
        END AS AppliedDiscountPct,

        -- CASE Block B: Commission %
        CASE
          WHEN l.CategoryName IN ('Bikes') THEN
            CASE l.TerritoryGroup
              WHEN 'North America' THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.0500 WHEN 'Silver' THEN 0.0450 WHEN 'Bronze' THEN 0.0400 ELSE 0.0350 END
              WHEN 'Europe'        THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.0520 WHEN 'Silver' THEN 0.0470 WHEN 'Bronze' THEN 0.0420 ELSE 0.0370 END
              WHEN 'Pacific'       THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.0480 WHEN 'Silver' THEN 0.0430 WHEN 'Bronze' THEN 0.0380 ELSE 0.0330 END
              ELSE 0.0350 END
          WHEN l.CategoryName = 'Components' THEN
            CASE l.TerritoryGroup
              WHEN 'North America' THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.0300 WHEN 'Silver' THEN 0.0280 WHEN 'Bronze' THEN 0.0260 ELSE 0.0240 END
              WHEN 'Europe'        THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.0320 WHEN 'Silver' THEN 0.0300 WHEN 'Bronze' THEN 0.0278 ELSE 0.0255 END
              ELSE CASE ct.CustomerTier WHEN 'Gold' THEN 0.0290 ELSE 0.0235 END END
          WHEN l.CategoryName = 'Clothing' THEN
            CASE l.TerritoryGroup
              WHEN 'North America' THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.0200 WHEN 'Silver' THEN 0.0180 WHEN 'Bronze' THEN 0.0160 ELSE 0.0140 END
              WHEN 'Europe'        THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.0220 WHEN 'Silver' THEN 0.0200 WHEN 'Bronze' THEN 0.0175 ELSE 0.0150 END
              ELSE CASE ct.CustomerTier WHEN 'Gold' THEN 0.0195 ELSE 0.0130 END END
          WHEN l.CategoryName = 'Accessories' THEN
            CASE l.TerritoryGroup
              WHEN 'North America' THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.0250 WHEN 'Silver' THEN 0.0230 WHEN 'Bronze' THEN 0.0210 ELSE 0.0190 END
              WHEN 'Europe'        THEN CASE ct.CustomerTier WHEN 'Gold' THEN 0.0270 WHEN 'Silver' THEN 0.0248 WHEN 'Bronze' THEN 0.0225 ELSE 0.0200 END
              ELSE CASE ct.CustomerTier WHEN 'Gold' THEN 0.0240 ELSE 0.0185 END END
          ELSE 0.0200
        END AS AppliedCommissionPct,

        -- CASE Block C: Tax override
        CASE
          WHEN l.TerritoryGroup = 'Europe'  THEN 0.2000
          WHEN l.TerritoryGroup = 'Pacific' THEN 0.1000
          WHEN l.CountryRegionCode = 'CA'   THEN 0.0500
          WHEN l.CountryRegionCode = 'US'   THEN NULL
          ELSE NULL
        END AS TaxOverridePct

    INTO #PricedLines
    FROM #Lines l
    LEFT JOIN #CustomerTier ct
        ON ct.CustomerID = l.CustomerID AND ct.TerritoryGroup = l.TerritoryGroup;

    CREATE CLUSTERED INDEX CX_PricedLines ON #PricedLines (SalesOrderID, SalesOrderDetailID);
    CREATE INDEX IX_PricedLines_SP ON #PricedLines (SalesPersonID)
        INCLUDE (LineTotal, AppliedDiscountPct, AppliedCommissionPct, CategoryName);

    EXEC dbo.usp_AW19_Log @RunId, @ProcName, N'STEP5_PricingEngine', N'OK', NULL, 0;

    -- STEP 6: Compute adjusted revenue, commission, margin
    IF OBJECT_ID('tempdb..#LineFinals') IS NOT NULL DROP TABLE #LineFinals;

    SELECT
        pl.SalesOrderID,
        pl.SalesOrderDetailID,
        pl.CustomerID,
        pl.SalesPersonID,
        pl.SalesPersonName,
        pl.OrderDate,
        pl.TerritoryGroup,
        pl.TerritoryName,
        pl.CategoryName,
        pl.SubCategoryName,
        pl.ProductName,
        pl.CustomerTier,
        pl.OrderQty,
        pl.UnitPrice,
        pl.ListPrice,
        pl.StandardCost,
        pl.LineTotal                                                    AS OriginalLineTotal,
        pl.AppliedDiscountPct,
        pl.AppliedCommissionPct,
        pl.TaxOverridePct,
        pl.LineTotal * (1.0 - pl.AppliedDiscountPct)                   AS AdjustedRevenue,
        pl.LineTotal * pl.AppliedDiscountPct                           AS DiscountAmount,
        pl.LineTotal * (1.0 - pl.AppliedDiscountPct)
            * pl.AppliedCommissionPct                                  AS CommissionEarned,
        pl.LineTotal * (1.0 - pl.AppliedDiscountPct)
            - (pl.StandardCost * pl.OrderQty)                         AS GrossMargin,
        CASE
            WHEN pl.LineTotal * (1.0 - pl.AppliedDiscountPct) = 0 THEN NULL
            ELSE (pl.LineTotal * (1.0 - pl.AppliedDiscountPct)
                  - (pl.StandardCost * pl.OrderQty))
                 / NULLIF(pl.LineTotal * (1.0 - pl.AppliedDiscountPct), 0)
        END AS GrossMarginPct,
        CASE
            WHEN pl.TaxOverridePct IS NOT NULL
                THEN pl.LineTotal * (1.0 - pl.AppliedDiscountPct) * pl.TaxOverridePct
            ELSE NULL
        END AS EstimatedTax
    INTO #LineFinals
    FROM #PricedLines pl;

    CREATE CLUSTERED INDEX CX_LineFinals ON #LineFinals (SalesPersonID, SalesOrderID);

    EXEC dbo.usp_AW19_Log @RunId, @ProcName, N'STEP6_LineFinals', N'OK', NULL, 0;

    -- STEP 7: Salesperson commission summary + quota attainment
    IF OBJECT_ID('tempdb..#SPSummary') IS NOT NULL DROP TABLE #SPSummary;

    SELECT
        lf.SalesPersonID,
        lf.SalesPersonName,
        lf.TerritoryGroup,
        lf.TerritoryName,
        COUNT(DISTINCT lf.SalesOrderID)                                AS TotalOrders,
        SUM(lf.OriginalLineTotal)                                      AS TotalOriginalRevenue,
        SUM(lf.AdjustedRevenue)                                        AS TotalAdjustedRevenue,
        SUM(lf.DiscountAmount)                                         AS TotalDiscountGiven,
        SUM(lf.CommissionEarned)                                       AS TotalCommissionEarned,
        SUM(lf.GrossMargin)                                            AS TotalGrossMargin,
        AVG(lf.GrossMarginPct)                                         AS AvgGrossMarginPct,
        SUM(CASE WHEN lf.CategoryName = 'Bikes'       THEN lf.AdjustedRevenue ELSE 0 END) AS BikeRevenue,
        SUM(CASE WHEN lf.CategoryName = 'Components'  THEN lf.AdjustedRevenue ELSE 0 END) AS CompRevenue,
        SUM(CASE WHEN lf.CategoryName = 'Clothing'    THEN lf.AdjustedRevenue ELSE 0 END) AS ClothingRevenue,
        SUM(CASE WHEN lf.CategoryName = 'Accessories' THEN lf.AdjustedRevenue ELSE 0 END) AS AccessRevenue,
        MAX(bo.SalesQuota)                                             AS SalesQuota,
        CASE
          WHEN MAX(bo.SalesQuota) = 0 OR MAX(bo.SalesQuota) IS NULL        THEN 'No Quota'
          WHEN SUM(lf.AdjustedRevenue) / NULLIF(MAX(bo.SalesQuota),0) >= 1.20 THEN 'Overachiever'
          WHEN SUM(lf.AdjustedRevenue) / NULLIF(MAX(bo.SalesQuota),0) >= 1.00 THEN 'On Target'
          WHEN SUM(lf.AdjustedRevenue) / NULLIF(MAX(bo.SalesQuota),0) >= 0.80 THEN 'Near Target'
          WHEN SUM(lf.AdjustedRevenue) / NULLIF(MAX(bo.SalesQuota),0) >= 0.60 THEN 'Below Target'
          ELSE 'At Risk'
        END AS QuotaAttainmentBand,
        NTILE(4) OVER (ORDER BY SUM(lf.AdjustedRevenue) DESC)         AS RevenueQuartile
    INTO #SPSummary
    FROM #LineFinals lf
    JOIN #BaseOrders bo ON bo.SalesOrderID = lf.SalesOrderID
    WHERE lf.SalesPersonID IS NOT NULL
    GROUP BY lf.SalesPersonID, lf.SalesPersonName, lf.TerritoryGroup, lf.TerritoryName;

    EXEC dbo.usp_AW19_Log @RunId, @ProcName, N'STEP7_SPSummary', N'OK', NULL, 0;

    -- STEP 8: Customer RFM scoring
    IF OBJECT_ID('tempdb..#CustomerSummary') IS NOT NULL DROP TABLE #CustomerSummary;

    WITH CustAgg AS (
        SELECT
            lf.CustomerID,
            COUNT(DISTINCT lf.SalesOrderID)             AS OrderCount,
            SUM(lf.AdjustedRevenue)                     AS TotalRevenue,
            AVG(lf.AdjustedRevenue)                     AS AvgLineRevenue,
            MAX(lf.OrderDate)                           AS LastOrderDate,
            MIN(lf.OrderDate)                           AS FirstOrderDate,
            DATEDIFF(DAY, MAX(lf.OrderDate), @EndDate)  AS RecencyDays,
            SUM(lf.DiscountAmount)                      AS TotalDiscount,
            SUM(lf.CommissionEarned)                    AS TotalCommission,
            MAX(lf.CustomerTier)                        AS CustomerTier,
            MAX(lf.TerritoryGroup)                      AS TerritoryGroup
        FROM #LineFinals lf
        GROUP BY lf.CustomerID
    )
    SELECT
        ca.*,
        p.FirstName + ' ' + p.LastName                 AS CustomerName,
        NTILE(5) OVER (ORDER BY ca.RecencyDays ASC)    AS RScore,
        NTILE(5) OVER (ORDER BY ca.OrderCount DESC)    AS FScore,
        NTILE(5) OVER (ORDER BY ca.TotalRevenue DESC)  AS MScore
    INTO #CustomerSummary
    FROM CustAgg ca
    JOIN Person.Person p ON p.BusinessEntityID = ca.CustomerID;

    CREATE CLUSTERED INDEX CX_CustSummary ON #CustomerSummary (CustomerID);

    EXEC dbo.usp_AW19_Log @RunId, @ProcName, N'STEP8_CustomerSummary', N'OK', NULL, 0;

    -- STEP 9: Territory benchmarks
    IF OBJECT_ID('tempdb..#TerritoryBenchmarks') IS NOT NULL DROP TABLE #TerritoryBenchmarks;

    SELECT
        TerritoryGroup,
        COUNT(DISTINCT SalesPersonID)   AS SalesPersonCount,
        SUM(TotalAdjustedRevenue)       AS TerritoryTotalRevenue,
        AVG(TotalAdjustedRevenue)       AS TerritoryAvgRevSP,
        AVG(TotalCommissionEarned)      AS TerritoryAvgCommission,
        AVG(AvgGrossMarginPct)          AS TerritoryAvgMarginPct,
        SUM(BikeRevenue)                AS TerritoryBikeRevenue,
        SUM(CompRevenue)                AS TerritoryCompRevenue,
        SUM(ClothingRevenue)            AS TerritoryClothingRevenue,
        SUM(AccessRevenue)              AS TerritoryAccessRevenue
    INTO #TerritoryBenchmarks
    FROM #SPSummary
    GROUP BY TerritoryGroup;

    CREATE CLUSTERED INDEX CX_TerritoryBench ON #TerritoryBenchmarks (TerritoryGroup);

    EXEC dbo.usp_AW19_Log @RunId, @ProcName, N'STEP9_TerritoryBench', N'OK', NULL, 0;

    -- STEP 10: Final output
    EXEC dbo.usp_AW19_Log @RunId, @ProcName, N'END', N'SUCCESS', N'Completed', 1;

    SELECT TOP (@TopNSalesPerson)
        sp.SalesPersonID,
        sp.SalesPersonName,
        sp.TerritoryGroup,
        sp.TerritoryName,
        sp.TotalOrders,
        sp.TotalOriginalRevenue,
        sp.TotalAdjustedRevenue,
        sp.TotalDiscountGiven,
        sp.TotalCommissionEarned,
        sp.TotalGrossMargin,
        sp.AvgGrossMarginPct,
        sp.BikeRevenue,
        sp.CompRevenue,
        sp.ClothingRevenue,
        sp.AccessRevenue,
        sp.SalesQuota,
        sp.QuotaAttainmentBand,
        sp.RevenueQuartile,
        sp.TotalAdjustedRevenue - tb.TerritoryAvgRevSP                AS RevenueVsTerritoryAvg,
        CASE
          WHEN tb.TerritoryAvgRevSP = 0 THEN NULL
          ELSE (sp.TotalAdjustedRevenue - tb.TerritoryAvgRevSP)
               / NULLIF(tb.TerritoryAvgRevSP, 0)
        END                                                            AS RevenueVsTerritoryPctDelta,
        sp.TotalCommissionEarned - tb.TerritoryAvgCommission          AS CommissionVsTerritoryAvg,
        tb.TerritoryTotalRevenue,
        tb.TerritoryAvgMarginPct,
        (SELECT COUNT(DISTINCT cs.CustomerID)
         FROM #CustomerSummary cs
         JOIN #LineFinals lf ON lf.CustomerID = cs.CustomerID
         WHERE lf.SalesPersonID = sp.SalesPersonID)                   AS UniqueCustomers,
        (SELECT AVG(CAST(cs.RScore + cs.FScore + cs.MScore AS FLOAT))
         FROM #CustomerSummary cs
         JOIN #LineFinals lf ON lf.CustomerID = cs.CustomerID
         WHERE lf.SalesPersonID = sp.SalesPersonID)                   AS AvgCustomerRFMScore,
        @StartDate  AS SnapshotStartDate,
        @EndDate    AS SnapshotEndDate,
        @RunId      AS RunId
    FROM #SPSummary sp
    JOIN #TerritoryBenchmarks tb ON tb.TerritoryGroup = sp.TerritoryGroup
    ORDER BY sp.TotalAdjustedRevenue DESC;

    END TRY
    BEGIN CATCH
        DECLARE @msg NVARCHAR(2000) =
            CONCAT(N'Error ', ERROR_NUMBER(), N' at line ', ERROR_LINE(), N': ', ERROR_MESSAGE());
        EXEC dbo.usp_AW19_Log @RunId, @ProcName, N'END', N'FAIL', @msg, 1;
        THROW;
    END CATCH

END
GO

-- ============================================================
-- OBJECT 5: Nested Helper Procedure - Tier Override
-- ============================================================
CREATE OR ALTER PROCEDURE dbo.usp_AW19_ResolveTierOverride
    @CustomerID   INT,
    @CurrentTier  NVARCHAR(30),
    @ResolvedTier NVARCHAR(30) OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @PhoneCount INT;
    DECLARE @EmailCount INT;
    DECLARE @PersonType NCHAR(2);
    DECLARE @Title      NVARCHAR(8);

    SELECT @PersonType = p.PersonType, @Title = p.Title
    FROM Person.Person p
    WHERE p.BusinessEntityID = @CustomerID;

    SELECT @PhoneCount = COUNT(*) FROM Person.PersonPhone  WHERE BusinessEntityID = @CustomerID;
    SELECT @EmailCount = COUNT(*) FROM Person.EmailAddress WHERE BusinessEntityID = @CustomerID;

    SET @ResolvedTier =
        CASE
          WHEN @CurrentTier = 'Standard' AND @PhoneCount >= 3 AND @EmailCount >= 2  THEN 'Bronze'
          WHEN @CurrentTier = 'Bronze'   AND @PersonType = 'SC' AND @PhoneCount >= 2 THEN 'Silver'
          WHEN @CurrentTier = 'Silver'   AND @Title IN ('Mr.','Ms.','Mrs.','Dr.')
               AND @EmailCount >= 3                                                  THEN 'Gold'
          WHEN @CurrentTier = 'Gold'     AND @PhoneCount = 0                         THEN 'Silver'
          ELSE @CurrentTier
        END;
END
GO

-- ============================================================
-- OBJECT 6: Pricing Audit Procedure
-- ============================================================
CREATE OR ALTER PROCEDURE dbo.usp_AW19_AuditPricingViolations
    @RunId          UNIQUEIDENTIFIER,
    @StartDate      DATE,
    @EndDate        DATE,
    @ViolationCount INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @ProcName     SYSNAME        = N'usp_AW19_AuditPricingViolations';
    DECLARE @AuditStatus  NVARCHAR(30);
    DECLARE @AuditMessage NVARCHAR(2000);

    IF OBJECT_ID('tempdb..#Violations') IS NOT NULL DROP TABLE #Violations;

    SELECT
        d.SalesOrderID,
        d.SalesOrderDetailID,
        d.ProductID,
        d.UnitPriceDiscount                      AS AppliedDiscountOnRecord,
        COALESCE(pr.DiscountPct, 0)              AS MaxAllowedDiscount,
        CASE
          WHEN d.UnitPriceDiscount > COALESCE(pr.DiscountPct, 0) + 0.02 THEN 'OVER_DISCOUNT'
          WHEN d.UnitPriceDiscount < 0                                    THEN 'NEGATIVE_DISCOUNT'
          WHEN d.UnitPrice <= 0                                           THEN 'ZERO_PRICE'
          WHEN d.LineTotal < 0                                            THEN 'NEGATIVE_LINE_TOTAL'
          WHEN d.OrderQty <= 0                                            THEN 'ZERO_QTY'
          ELSE 'OK'
        END AS ViolationType,
        CASE
          WHEN d.UnitPriceDiscount > COALESCE(pr.DiscountPct, 0) + 0.02 THEN 3
          WHEN d.UnitPriceDiscount < 0                                    THEN 3
          WHEN d.UnitPrice <= 0                                           THEN 3
          WHEN d.LineTotal < 0                                            THEN 2
          WHEN d.OrderQty <= 0                                            THEN 2
          ELSE 0
        END AS Severity,
        pc.Name                                  AS CategoryName,
        st.[Group]                               AS TerritoryGroup,
        CAST(h.OrderDate AS DATE)                AS OrderDate
    INTO #Violations
    FROM Sales.SalesOrderDetail             d
    JOIN Sales.SalesOrderHeader             h  ON h.SalesOrderID          = d.SalesOrderID
    JOIN Sales.SalesTerritory              st  ON st.TerritoryID          = h.TerritoryID
    JOIN Production.Product                 p  ON p.ProductID             = d.ProductID
    LEFT JOIN Production.ProductSubcategory ps ON ps.ProductSubcategoryID = p.ProductSubcategoryID
    LEFT JOIN Production.ProductCategory    pc ON pc.ProductCategoryID    = ps.ProductCategoryID
    LEFT JOIN dbo.AW19_PricingRules        pr
        ON  pr.CategoryName   = pc.Name
        AND pr.TerritoryGroup = st.[Group]
        AND pr.EffectiveDate <= CAST(h.OrderDate AS DATE)
        AND (pr.ExpiryDate IS NULL OR pr.ExpiryDate >= CAST(h.OrderDate AS DATE))
    WHERE CAST(h.OrderDate AS DATE) BETWEEN @StartDate AND @EndDate
      AND (
            d.UnitPriceDiscount > COALESCE(pr.DiscountPct, 0) + 0.02
         OR d.UnitPriceDiscount < 0
         OR d.UnitPrice <= 0
         OR d.LineTotal < 0
         OR d.OrderQty <= 0
          );

    SELECT @ViolationCount = COUNT(*) FROM #Violations;

    SET @AuditStatus  = CASE WHEN @ViolationCount > 0 THEN N'WARN' ELSE N'OK' END;
    SET @AuditMessage = N'Violations found: ' + CAST(@ViolationCount AS NVARCHAR(10));

    EXEC dbo.usp_AW19_Log
        @RunId, @ProcName,
        N'AUDIT_VIOLATIONS',
        @AuditStatus,
        @AuditMessage,
        1;

    SELECT
        SalesOrderID, SalesOrderDetailID, ProductID,
        AppliedDiscountOnRecord, MaxAllowedDiscount,
        ViolationType, Severity, CategoryName, TerritoryGroup, OrderDate
    FROM #Violations
    ORDER BY Severity DESC, OrderDate DESC;

END
GO