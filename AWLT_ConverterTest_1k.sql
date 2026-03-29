
USE AdventureWorksLT2022;
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

/* ---------------------------------------------------------------------
   Run log (lightweight)
   --------------------------------------------------------------------- */
IF OBJECT_ID('dbo.AWLT_Converter_RunLog','U') IS NULL
BEGIN
    CREATE TABLE dbo.AWLT_Converter_RunLog
    (
          RunId uniqueidentifier NOT NULL
        , ProcName sysname NOT NULL
        , StepName nvarchar(200) NOT NULL
        , StepStatus nvarchar(30) NOT NULL
        , Message nvarchar(2000) NULL
        , StartedUtc datetime2(3) NOT NULL DEFAULT SYSUTCDATETIME()
        , CompletedUtc datetime2(3) NULL
        , CONSTRAINT PK_AWLT_Converter_RunLog PRIMARY KEY (RunId, StepName, StartedUtc)
    );
END;
GO

CREATE OR ALTER PROCEDURE dbo.usp_AWLT_Converter_Log
    @RunId uniqueidentifier,
    @ProcName sysname,
    @StepName nvarchar(200),
    @StepStatus nvarchar(30),
    @Message nvarchar(2000) = NULL,
    @Complete bit = 0
AS
BEGIN
    SET NOCOUNT ON;

    INSERT dbo.AWLT_Converter_RunLog(RunId, ProcName, StepName, StepStatus, Message, CompletedUtc)
    VALUES (@RunId, @ProcName, @StepName, @StepStatus, @Message, CASE WHEN @Complete=1 THEN SYSUTCDATETIME() ELSE NULL END);
END;
GO

/* ---------------------------------------------------------------------
   Helper TVF: split CSV list to ints
   --------------------------------------------------------------------- */
CREATE OR ALTER FUNCTION dbo.ufn_SplitCsvInt(@csv nvarchar(max))
RETURNS @t TABLE (ItemInt int NOT NULL)
AS
BEGIN
    DECLARE @x nvarchar(max) = COALESCE(@csv, N'');
    DECLARE @pos int = 1, @next int, @token nvarchar(100);

    SET @x = REPLACE(REPLACE(REPLACE(@x, CHAR(10), N','), CHAR(13), N','), N';', N',');
    WHILE LEN(@x) > 0 AND RIGHT(@x,1) = N',' SET @x = LEFT(@x, LEN(@x)-1);

    WHILE @pos <= LEN(@x) + 1
    BEGIN
        SET @next = CHARINDEX(N',', @x, @pos);
        IF @next = 0 SET @next = LEN(@x) + 1;

        SET @token = LTRIM(RTRIM(SUBSTRING(@x, @pos, @next - @pos)));
        IF @token <> N'' AND TRY_CONVERT(int, @token) IS NOT NULL
            INSERT @t(ItemInt) VALUES (CONVERT(int, @token));

        SET @pos = @next + 1;
    END
    RETURN;
END;
GO

-- QC rules (explicit inserts; executable lines)
IF OBJECT_ID('dbo.AWLT_QC_Definition','U') IS NULL
BEGIN
    CREATE TABLE dbo.AWLT_QC_Definition(
        QCId int IDENTITY(1,1) PRIMARY KEY,
        CheckGroup varchar(50) NOT NULL,
        CheckName varchar(120) NOT NULL,
        Severity tinyint NOT NULL,
        SqlPredicate nvarchar(4000) NOT NULL,
        CreatedUtc datetime2(3) NOT NULL DEFAULT SYSUTCDATETIME()
    );
END;
GO

TRUNCATE TABLE dbo.AWLT_QC_Definition;
GO

INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0001', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0002', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0003', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0004', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0005', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0006', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0007', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0008', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0009', 2, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0010', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0011', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0012', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0013', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0014', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0015', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0016', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0017', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0018', 2, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0019', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0020', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0021', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0022', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0023', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0024', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0025', 1, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0026', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0027', 2, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0028', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0029', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0030', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0031', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0032', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0033', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0034', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0035', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0036', 2, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0037', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0038', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0039', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0040', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0041', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0042', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0043', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0044', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0045', 2, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0046', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0047', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0048', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0049', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0050', 1, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0051', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0052', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0053', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0054', 2, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0055', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0056', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0057', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0058', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0059', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0060', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0061', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0062', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0063', 2, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0064', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0065', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0066', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0067', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0068', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0069', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0070', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0071', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0072', 2, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0073', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0074', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0075', 1, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0076', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0077', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0078', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0079', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0080', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0081', 2, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0082', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0083', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0084', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0085', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0086', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0087', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0088', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0089', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0090', 2, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0091', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0092', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0093', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0094', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0095', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0096', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0097', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0098', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0099', 2, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Nulls', 'QC_0100', 1, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE CustomerID IS NULL)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0101', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0102', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0103', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0104', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0105', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0106', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0107', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0108', 2, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0109', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0110', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0111', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0112', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0113', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0114', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0115', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0116', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0117', 2, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0118', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0119', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0120', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0121', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0122', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0123', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0124', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0125', 1, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0126', 2, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0127', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0128', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0129', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0130', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0131', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0132', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0133', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0134', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0135', 2, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0136', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0137', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0138', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0139', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0140', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0141', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0142', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0143', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0144', 2, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0145', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0146', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0147', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0148', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0149', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0150', 1, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0151', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0152', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0153', 2, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0154', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0155', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0156', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0157', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0158', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0159', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0160', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0161', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0162', 2, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0163', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0164', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0165', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0166', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0167', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0168', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0169', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0170', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0171', 2, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0172', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0173', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0174', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0175', 1, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0176', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0177', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0178', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0179', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0180', 2, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0181', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0182', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0183', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0184', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0185', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0186', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0187', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0188', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0189', 2, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0190', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0191', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0192', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0193', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0194', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0195', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0196', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0197', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0198', 2, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0199', 3, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Ranges', 'QC_0200', 1, N'EXISTS(SELECT 1 FROM #CustomerFacts WHERE TotalRevenue < 0 OR AvgOrderValue < 0)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0201', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0202', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0203', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0204', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0205', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0206', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0207', 2, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0208', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0209', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0210', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0211', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0212', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0213', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0214', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0215', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0216', 2, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0217', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0218', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0219', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0220', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0221', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0222', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0223', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0224', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0225', 1, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0226', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0227', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0228', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0229', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0230', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0231', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0232', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0233', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0234', 2, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0235', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0236', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0237', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0238', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0239', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0240', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0241', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0242', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0243', 2, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0244', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0245', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0246', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0247', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0248', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0249', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0250', 1, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0251', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0252', 2, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0253', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0254', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0255', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0256', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0257', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0258', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0259', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
INSERT dbo.AWLT_QC_Definition(CheckGroup, CheckName, Severity, SqlPredicate)
VALUES ('Reconcile', 'QC_0260', 3, N'ABS(ISNULL(TotalRevenue_PathA,0)-ISNULL(TotalRevenue_PathB,0)) > (ISNULL(TotalRevenue_PathA,0)*0.01)');
GO

/* ---------------------------------------------------------------------
   Main procedure: outputs ONE result set only
   --------------------------------------------------------------------- */
CREATE OR ALTER PROCEDURE dbo.usp_AWLT_OneCSV_ConverterTest_1k
(
      @StartDate date = NULL,
      @EndDate   date = NULL,
      @AsOfDate  date = NULL,
      @CustomerIdsCsv nvarchar(max) = NULL,
      @RegionFilter nvarchar(100) = NULL,
      @RecentMonthsWindow int = 6,
      @RevenueTolerancePct decimal(9,4) = 0.0100,
      @EmitDebug bit = 0
)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @RunId uniqueidentifier = NEWID();
    DECLARE @ProcName sysname = 'dbo.usp_AWLT_OneCSV_ConverterTest_1k';

    DECLARE @StartMsg nvarchar(2000);
    SET @StartMsg = N'Params: Region=' + COALESCE(@RegionFilter, N'(all)');

    EXEC dbo.usp_AWLT_Converter_Log @RunId=@RunId, @ProcName=@ProcName, @StepName=N'START', @StepStatus=N'START', @Message=@StartMsg, @Complete=0;

    -- Normalize date window
    IF @StartDate IS NULL OR @EndDate IS NULL
    BEGIN
        SELECT
              @StartDate = COALESCE(@StartDate, MIN(CAST(OrderDate AS date)))
            , @EndDate   = COALESCE(@EndDate  , MAX(CAST(OrderDate AS date)))
        FROM SalesLT.SalesOrderHeader;
    END;

    IF @AsOfDate IS NULL SET @AsOfDate = @EndDate;

    BEGIN TRY
        /* =============================================================
           1) Customer filter
           ============================================================= */
        IF OBJECT_ID('tempdb..#CustomerFilter') IS NOT NULL DROP TABLE #CustomerFilter;

        SELECT DISTINCT ItemInt AS CustomerID
        INTO #CustomerFilter
        FROM dbo.ufn_SplitCsvInt(@CustomerIdsCsv);

        DECLARE @HasCustomerFilter bit = CASE WHEN EXISTS(SELECT 1 FROM #CustomerFilter) THEN 1 ELSE 0 END;

        /* =============================================================
           2) Base orders in date range
           ============================================================= */
        IF OBJECT_ID('tempdb..#Orders') IS NOT NULL DROP TABLE #Orders;

        SELECT
              h.SalesOrderID
            , h.CustomerID
            , CAST(h.OrderDate AS date) AS OrderDate
            , h.TotalDue
            , h.SubTotal
            , h.TaxAmt
            , h.Freight
            , h.OnlineOrderFlag
            , COALESCE(a.StateProvince, a.CountryRegion, 'Unknown Region') AS RegionName
        INTO #Orders
        FROM SalesLT.SalesOrderHeader h
        LEFT JOIN SalesLT.Address a
            ON a.AddressID = h.ShipToAddressID
        WHERE CAST(h.OrderDate AS date) BETWEEN @StartDate AND @EndDate
          AND (@HasCustomerFilter = 0 OR EXISTS (SELECT 1 FROM #CustomerFilter f WHERE f.CustomerID = h.CustomerID))
          AND (@RegionFilter IS NULL OR COALESCE(a.StateProvince, a.CountryRegion, 'Unknown Region') = @RegionFilter);

        CREATE CLUSTERED INDEX CX_Orders ON #Orders(CustomerID, OrderDate, SalesOrderID);
        CREATE INDEX IX_Orders_Order ON #Orders(SalesOrderID) INCLUDE (TotalDue, OnlineOrderFlag, RegionName);

        /* =============================================================
           3) Line details + product/category enrichment
           ============================================================= */
        IF OBJECT_ID('tempdb..#Lines') IS NOT NULL DROP TABLE #Lines;

        SELECT
              d.SalesOrderID
            , d.SalesOrderDetailID
            , d.ProductID
            , d.OrderQty
            , d.UnitPrice
            , d.UnitPriceDiscount
            , d.LineTotal
            , p.ProductNumber
            , p.Name AS ProductName
            , pc.Name AS CategoryName
            , pm.Name AS ModelName
            , p.Color
        INTO #Lines
        FROM SalesLT.SalesOrderDetail d
        JOIN #Orders o
            ON o.SalesOrderID = d.SalesOrderID
        JOIN SalesLT.Product p
            ON p.ProductID = d.ProductID
        LEFT JOIN SalesLT.ProductCategory pc
            ON pc.ProductCategoryID = p.ProductCategoryID
        LEFT JOIN SalesLT.ProductModel pm
            ON pm.ProductModelID = p.ProductModelID;

        CREATE INDEX IX_Lines_Order ON #Lines(SalesOrderID) INCLUDE (LineTotal, OrderQty, CategoryName, ModelName, Color);

        /* =============================================================
           4) Path A aggregates (order header totals)
           ============================================================= */
        IF OBJECT_ID('tempdb..#AggA') IS NOT NULL DROP TABLE #AggA;

        SELECT
              CustomerID
            , COUNT_BIG(*) AS OrderCount
            , SUM(TotalDue) AS TotalRevenue_PathA
            , SUM(SubTotal) AS SubTotal_PathA
            , SUM(TaxAmt) AS Tax_PathA
            , SUM(Freight) AS Freight_PathA
            , SUM(CASE WHEN OnlineOrderFlag=1 THEN 1 ELSE 0 END) AS OnlineOrderCount
            , SUM(CASE WHEN OnlineOrderFlag=0 THEN 1 ELSE 0 END) AS OfflineOrderCount
            , MIN(OrderDate) AS FirstOrderDate
            , MAX(OrderDate) AS LastOrderDate
            , MAX(RegionName) AS PrimaryRegionName
        INTO #AggA
        FROM #Orders
        GROUP BY CustomerID;

        CREATE CLUSTERED INDEX CX_AggA ON #AggA(CustomerID);

        /* =============================================================
           5) Path B aggregates (sum of line totals w/ discount)
           ============================================================= */
        IF OBJECT_ID('tempdb..#AggB') IS NOT NULL DROP TABLE #AggB;

        ;WITH L AS
        (
            SELECT
                  o.CustomerID
                , o.SalesOrderID
                , SUM(l.LineTotal) AS LineTotalSum
                , SUM(l.UnitPrice * l.OrderQty * l.UnitPriceDiscount) AS DiscountAmount
                , COUNT_BIG(*) AS LineCount
                , SUM(l.OrderQty) AS TotalQty
                , COUNT(DISTINCT l.ProductID) AS DistinctProducts
                , COUNT(DISTINCT l.CategoryName) AS DistinctCategories
            FROM #Orders o
            JOIN #Lines l
                ON l.SalesOrderID = o.SalesOrderID
            GROUP BY o.CustomerID, o.SalesOrderID
        )
        SELECT
              CustomerID
            , SUM(LineTotalSum) AS TotalRevenue_PathB
            , SUM(DiscountAmount) AS TotalDiscount_PathB
            , SUM(LineCount) AS TotalLines
            , SUM(TotalQty) AS TotalQty
            , SUM(DistinctProducts) AS DistinctProducts
            , SUM(DistinctCategories) AS DistinctCategories
        INTO #AggB
        FROM L
        GROUP BY CustomerID;

        CREATE CLUSTERED INDEX CX_AggB ON #AggB(CustomerID);

        /* =============================================================
           6) Customer facts (merged)
           ============================================================= */
        IF OBJECT_ID('tempdb..#CustomerFacts') IS NOT NULL DROP TABLE #CustomerFacts;

        SELECT
              a.CustomerID
            , c.FirstName + ' ' + c.LastName AS CustomerName
            , a.PrimaryRegionName AS RegionName
            , a.FirstOrderDate
            , a.LastOrderDate
            , a.OrderCount
            , a.OnlineOrderCount
            , a.OfflineOrderCount
            , a.TotalRevenue_PathA
            , b.TotalRevenue_PathB
            , a.Freight_PathA AS TotalFreight
            , a.Tax_PathA AS TotalTax
            , CASE WHEN a.OrderCount > 0 THEN (a.TotalRevenue_PathA / CONVERT(decimal(19,4), a.OrderCount)) ELSE 0 END AS AvgOrderValue
            , b.TotalDiscount_PathB
            , b.TotalLines
            , b.TotalQty
            , b.DistinctProducts
            , b.DistinctCategories
            , DATEDIFF(day, a.LastOrderDate, @AsOfDate) AS RecencyDays
            , DATEDIFF(day, a.FirstOrderDate, a.LastOrderDate) AS CustomerTenureDays
            , ABS(ISNULL(a.TotalRevenue_PathA,0) - ISNULL(b.TotalRevenue_PathB,0)) AS RevenueDelta_AB
            , CASE
                  WHEN ISNULL(a.TotalRevenue_PathA,0) = 0 THEN NULL
                  ELSE ABS(ISNULL(a.TotalRevenue_PathA,0) - ISNULL(b.TotalRevenue_PathB,0)) / NULLIF(CONVERT(decimal(19,6), a.TotalRevenue_PathA),0)
              END AS RevenuePctDelta_AB
        INTO #CustomerFacts
        FROM #AggA a
        JOIN SalesLT.Customer c
            ON c.CustomerID = a.CustomerID
        LEFT JOIN #AggB b
            ON b.CustomerID = a.CustomerID;

        CREATE CLUSTERED INDEX CX_CustFacts ON #CustomerFacts(CustomerID);
        CREATE INDEX IX_CustFacts_Region ON #CustomerFacts(RegionName) INCLUDE (TotalRevenue_PathA, OrderCount, RecencyDays);

        /* =============================================================
           7) RFM scoring (NTILE + bands)
           ============================================================= */
        IF OBJECT_ID('tempdb..#RFM') IS NOT NULL DROP TABLE #RFM;

        SELECT
              cf.*
            , NTILE(5) OVER (ORDER BY cf.RecencyDays ASC) AS R_Score
            , NTILE(5) OVER (ORDER BY cf.OrderCount DESC) AS F_Score
            , NTILE(5) OVER (ORDER BY cf.TotalRevenue_PathA DESC) AS M_Score
        INTO #RFM
        FROM #CustomerFacts cf;

        CREATE CLUSTERED INDEX CX_RFM ON #RFM(CustomerID);

        /* =============================================================
           8) Region benchmarks + QC deltas
           ============================================================= */
        IF OBJECT_ID('tempdb..#RegionAgg') IS NOT NULL DROP TABLE #RegionAgg;

        SELECT
              RegionName
            , AVG(CONVERT(decimal(19,4), TotalRevenue_PathA)) AS RegionAvgRevenue
            , AVG(CONVERT(decimal(19,4), OrderCount)) AS RegionAvgOrderCount
            , AVG(CONVERT(decimal(19,4), RecencyDays)) AS RegionAvgRecency
            , AVG(CONVERT(decimal(19,4), (R_Score + F_Score + M_Score))) AS RegionAvgRFM
        INTO #RegionAgg
        FROM #RFM
        GROUP BY RegionName;

        CREATE CLUSTERED INDEX CX_RegionAgg ON #RegionAgg(RegionName);

        /* =============================================================
           9) JSON payload per customer + parse back a few fields
           ============================================================= */
        IF OBJECT_ID('tempdb..#Json') IS NOT NULL DROP TABLE #Json;

        SELECT
              r.CustomerID
            , (
                SELECT
                      r.CustomerID AS customerId
                    , r.CustomerName AS customerName
                    , r.RegionName AS region
                    , r.TotalRevenue_PathA AS revenueA
                    , r.TotalRevenue_PathB AS revenueB
                    , r.OrderCount AS orders
                    , r.RecencyDays AS recencyDays
                    , (r.R_Score + r.F_Score + r.M_Score) AS rfmScore
                    , (SELECT TOP (5)
                            l.CategoryName AS category,
                            SUM(l.LineTotal) AS revenue
                       FROM #Orders o
                       JOIN #Lines l ON l.SalesOrderID=o.SalesOrderID
                       WHERE o.CustomerID=r.CustomerID
                       GROUP BY l.CategoryName
                       ORDER BY SUM(l.LineTotal) DESC
                       FOR JSON PATH) AS topCategories
                FOR JSON PATH, WITHOUT_ARRAY_WRAPPER
              ) AS PayloadJson
        INTO #Json
        FROM #RFM r;

        CREATE CLUSTERED INDEX CX_Json ON #Json(CustomerID);

        IF OBJECT_ID('tempdb..#JsonParsed') IS NOT NULL DROP TABLE #JsonParsed;

        SELECT
              j.CustomerID
            , TRY_CONVERT(decimal(19,4), p.revenueA) AS revenueA_json
            , TRY_CONVERT(decimal(19,4), p.revenueB) AS revenueB_json
            , TRY_CONVERT(int, p.orders) AS orders_json
            , TRY_CONVERT(int, p.rfmScore) AS rfmScore_json
        INTO #JsonParsed
        FROM #Json j
        CROSS APPLY OPENJSON(j.PayloadJson)
        WITH (
            revenueA nvarchar(50) '$.revenueA',
            revenueB nvarchar(50) '$.revenueB',
            orders nvarchar(50) '$.orders',
            rfmScore nvarchar(50) '$.rfmScore'
        ) p;

        CREATE CLUSTERED INDEX CX_JsonParsed ON #JsonParsed(CustomerID);

        /* =============================================================
           10) Evaluate a subset of QC rules (dynamic predicate checks)
               - to keep runtime reasonable, we sample QC definitions
           ============================================================= */
        IF OBJECT_ID('tempdb..#QCFail') IS NOT NULL DROP TABLE #QCFail;

        CREATE TABLE #QCFail
        (
              CheckGroup varchar(50) NOT NULL
            , CheckName varchar(120) NOT NULL
            , Severity tinyint NOT NULL
            , Failed bit NOT NULL
        );

        DECLARE @QCId int, @CheckGroup varchar(50), @CheckName varchar(120), @Severity tinyint, @SqlPredicate nvarchar(4000);
        DECLARE @sql nvarchar(max), @failed bit;

        DECLARE qc CURSOR LOCAL FAST_FORWARD FOR
        SELECT TOP (60) QCId, CheckGroup, CheckName, Severity, SqlPredicate
        FROM dbo.AWLT_QC_Definition
        ORDER BY QCId;

        OPEN qc;
        FETCH NEXT FROM qc INTO @QCId, @CheckGroup, @CheckName, @Severity, @SqlPredicate;

        WHILE @@FETCH_STATUS = 0
        BEGIN
            SET @failed = 0;

            -- Run predicate in dynamic SQL; if it returns a row => failed
            SET @sql = N'SET NOCOUNT ON; IF (' + @SqlPredicate + N') SELECT 1 AS FailFlag;';            -- Use safer pattern:
            DECLARE @tmp TABLE(FailFlag int);
            INSERT @tmp(FailFlag) EXEC sp_executesql @sql;
            SET @failed = CASE WHEN EXISTS(SELECT 1 FROM @tmp) THEN 1 ELSE 0 END;

            INSERT #QCFail(CheckGroup, CheckName, Severity, Failed)
            VALUES (@CheckGroup, @CheckName, @Severity, @failed);

            FETCH NEXT FROM qc INTO @QCId, @CheckGroup, @CheckName, @Severity, @SqlPredicate;
        END

        CLOSE qc;
        DEALLOCATE qc;

        /* =============================================================
           11) Final ONE result set (single CSV)
           ============================================================= */
        EXEC dbo.usp_AWLT_Converter_Log @RunId, @ProcName, N'END', N'SUCCESS', N'Completed', 1;

        SELECT
              r.CustomerID
            , r.CustomerName
            , r.RegionName
            , r.FirstOrderDate
            , r.LastOrderDate
            , r.OrderCount
            , r.OnlineOrderCount
            , r.OfflineOrderCount
            , r.TotalRevenue_PathA
            , r.TotalRevenue_PathB
            , r.RevenueDelta_AB
            , r.RevenuePctDelta_AB
            , r.TotalFreight
            , r.TotalTax
            , r.AvgOrderValue
            , r.TotalDiscount_PathB
            , r.TotalLines
            , r.TotalQty
            , r.DistinctProducts
            , r.DistinctCategories
            , r.RecencyDays
            , r.CustomerTenureDays
            , r.R_Score
            , r.F_Score
            , r.M_Score
            , (r.R_Score + r.F_Score + r.M_Score) AS RFM_Score
            , CASE WHEN r.RevenuePctDelta_AB IS NULL THEN 0
                   WHEN r.RevenuePctDelta_AB <= @RevenueTolerancePct THEN 1 ELSE 0 END AS QC_Pass_Revenue_AB
            , ra.RegionAvgRevenue
            , ra.RegionAvgOrderCount
            , ra.RegionAvgRecency
            , ra.RegionAvgRFM
            , CASE WHEN ra.RegionAvgRevenue = 0 THEN NULL ELSE (r.TotalRevenue_PathA - ra.RegionAvgRevenue) / NULLIF(ra.RegionAvgRevenue,0) END AS RevenueVsRegionPctDelta
            , CASE WHEN ra.RegionAvgRFM = 0 THEN NULL ELSE ((r.R_Score + r.F_Score + r.M_Score) - ra.RegionAvgRFM) / NULLIF(ra.RegionAvgRFM,0) END AS RFMVsRegionPctDelta
            , jp.revenueA_json
            , jp.revenueB_json
            , jp.orders_json
            , jp.rfmScore_json
            , j.PayloadJson
            , (SELECT COUNT_BIG(*) FROM #QCFail q WHERE q.Failed=1 AND q.Severity=3) AS QC_FailCount_Severity3
            , (SELECT COUNT_BIG(*) FROM #QCFail q WHERE q.Failed=1 AND q.Severity=2) AS QC_FailCount_Severity2
            , @StartDate AS SnapshotStartDate
            , @EndDate AS SnapshotEndDate
            , @AsOfDate AS SnapshotAsOfDate
            , @RevenueTolerancePct AS RevenueTolerancePctUsed
            , @RecentMonthsWindow AS RecentMonthsWindowUsed
            , @RunId AS RunId
        FROM #RFM r
        JOIN #RegionAgg ra ON ra.RegionName = r.RegionName
        JOIN #Json j ON j.CustomerID = r.CustomerID
        JOIN #JsonParsed jp ON jp.CustomerID = r.CustomerID
        ORDER BY
              r.RegionName,
              (r.R_Score + r.F_Score + r.M_Score) DESC,
              r.TotalRevenue_PathA DESC,
              r.CustomerName;

    END TRY
    BEGIN CATCH
        DECLARE @msg nvarchar(2000) =
            CONCAT('Error ', ERROR_NUMBER(), ' at line ', ERROR_LINE(), ': ', ERROR_MESSAGE());
        EXEC dbo.usp_AWLT_Converter_Log @RunId, @ProcName, N'END', N'FAIL', @msg, 1;
        THROW;
    END CATCH
END;
GO

