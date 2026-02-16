/*
================================================================================
Hydro One SharePoint to ADLS Migration - Control Table Schema
================================================================================
Description: Creates the MigrationControl table that tracks all SharePoint
             sites and document libraries to be migrated, along with their
             migration status, metrics, and retry information.

Author:      PwC Azure Data Engineering Team
Created:     2024
Project:     Hydro One SharePoint Migration POC
================================================================================
*/

-- Create schema if not exists
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'dbo')
BEGIN
    EXEC('CREATE SCHEMA dbo')
END
GO

-- Drop table if exists (for clean deployment)
IF OBJECT_ID('dbo.MigrationControl', 'U') IS NOT NULL
BEGIN
    DROP TABLE dbo.MigrationControl
END
GO

-- Create MigrationControl table
CREATE TABLE dbo.MigrationControl
(
    -- Primary Key
    Id                      INT IDENTITY(1,1) PRIMARY KEY,

    -- SharePoint Source Information
    SiteUrl                 NVARCHAR(500) NOT NULL,              -- e.g., /sites/HydroOneDocuments
    LibraryName             NVARCHAR(255) NOT NULL,              -- e.g., Documents, Shared Documents
    SiteTitle               NVARCHAR(255) NULL,                  -- Friendly name of the site
    LibraryTitle            NVARCHAR(255) NULL,                  -- Friendly name of the library

    -- Migration Status
    Status                  NVARCHAR(50) NOT NULL DEFAULT 'Pending',  -- Pending, InProgress, Completed, Failed, Skipped
    ValidationStatus        NVARCHAR(50) NULL,                   -- Pending, Validated, Discrepancy

    -- Metrics - Pre-Migration (from enumeration)
    FileCount               INT NULL,                            -- Total files in library
    FolderCount             INT NULL,                            -- Total folders in library
    TotalSizeBytes          BIGINT NULL,                         -- Total size of all files
    LargestFileSizeBytes    BIGINT NULL,                         -- Size of largest file

    -- Metrics - Post-Migration
    MigratedFileCount       INT NULL,                            -- Files successfully migrated
    MigratedSizeBytes       BIGINT NULL,                         -- Total bytes migrated
    FailedFileCount         INT NULL,                            -- Files that failed migration

    -- Timing Information
    StartTime               DATETIME2 NULL,                      -- When migration started
    EndTime                 DATETIME2 NULL,                      -- When migration completed
    DurationSeconds         AS DATEDIFF(SECOND, StartTime, EndTime),  -- Computed duration

    -- Error Handling
    ErrorMessage            NVARCHAR(MAX) NULL,                  -- Last error message
    RetryCount              INT NOT NULL DEFAULT 0,              -- Number of retry attempts
    LastRetryTime           DATETIME2 NULL,                      -- When last retry occurred

    -- Batch Management
    BatchId                 NVARCHAR(50) NULL,                   -- Batch identifier for grouping
    Priority                INT NOT NULL DEFAULT 100,            -- Lower = higher priority

    -- Incremental Sync
    EnableIncrementalSync   BIT NOT NULL DEFAULT 1,              -- Enable delta sync after initial load
    LastIncrementalSync     DATETIME2 NULL,                      -- Last successful incremental sync

    -- Validation Details
    ValidationTimestamp     DATETIME2 NULL,                      -- When validation was performed
    DiscrepancyDetails      NVARCHAR(MAX) NULL,                  -- Details of any discrepancies

    -- Audit Fields
    CreatedDate             DATETIME2 NOT NULL DEFAULT GETUTCDATE(),
    CreatedBy               NVARCHAR(100) NULL,
    ModifiedDate            DATETIME2 NOT NULL DEFAULT GETUTCDATE(),
    ModifiedBy              NVARCHAR(100) NULL,

    -- Constraints
    CONSTRAINT UQ_MigrationControl_SiteLibrary UNIQUE (SiteUrl, LibraryName),
    CONSTRAINT CK_MigrationControl_Status CHECK (Status IN ('Pending', 'InProgress', 'Completed', 'Failed', 'Skipped', 'Paused')),
    CONSTRAINT CK_MigrationControl_ValidationStatus CHECK (ValidationStatus IS NULL OR ValidationStatus IN ('Pending', 'Validated', 'Discrepancy'))
)
GO

-- Create indexes for common query patterns
CREATE NONCLUSTERED INDEX IX_MigrationControl_Status
ON dbo.MigrationControl (Status)
INCLUDE (SiteUrl, LibraryName, RetryCount)
GO

CREATE NONCLUSTERED INDEX IX_MigrationControl_BatchId
ON dbo.MigrationControl (BatchId)
INCLUDE (Status, StartTime, EndTime)
GO

CREATE NONCLUSTERED INDEX IX_MigrationControl_Priority
ON dbo.MigrationControl (Priority, Status)
INCLUDE (SiteUrl, LibraryName)
GO

-- Create IncrementalWatermark table for tracking delta sync
IF OBJECT_ID('dbo.IncrementalWatermark', 'U') IS NOT NULL
BEGIN
    DROP TABLE dbo.IncrementalWatermark
END
GO

CREATE TABLE dbo.IncrementalWatermark
(
    Id                  INT IDENTITY(1,1) PRIMARY KEY,
    SiteUrl             NVARCHAR(500) NOT NULL,
    LibraryName         NVARCHAR(255) NOT NULL,
    LastModifiedDate    DATETIME2 NOT NULL,          -- High watermark for modified date filter
    LastSyncTime        DATETIME2 NOT NULL,          -- When sync was performed
    FilesProcessed      INT NULL,                    -- Files processed in last sync

    CONSTRAINT UQ_IncrementalWatermark_SiteLibrary UNIQUE (SiteUrl, LibraryName)
)
GO

-- Create BatchLog table for batch tracking
IF OBJECT_ID('dbo.BatchLog', 'U') IS NOT NULL
BEGIN
    DROP TABLE dbo.BatchLog
END
GO

CREATE TABLE dbo.BatchLog
(
    Id                  INT IDENTITY(1,1) PRIMARY KEY,
    BatchId             NVARCHAR(50) NOT NULL UNIQUE,
    PipelineRunId       NVARCHAR(50) NULL,
    Status              NVARCHAR(50) NOT NULL DEFAULT 'Started',
    StartTime           DATETIME2 NOT NULL,
    EndTime             DATETIME2 NULL,
    LibrariesPlanned    INT NULL,
    LibrariesCompleted  INT NULL,
    LibrariesFailed     INT NULL,
    TotalFilesMigrated  BIGINT NULL,
    TotalBytesMigrated  BIGINT NULL,
    ErrorSummary        NVARCHAR(MAX) NULL
)
GO

-- Create SyncLog table for incremental sync tracking
IF OBJECT_ID('dbo.SyncLog', 'U') IS NOT NULL
BEGIN
    DROP TABLE dbo.SyncLog
END
GO

CREATE TABLE dbo.SyncLog
(
    Id                  INT IDENTITY(1,1) PRIMARY KEY,
    PipelineRunId       NVARCHAR(50) NOT NULL,
    SyncType            NVARCHAR(50) NOT NULL,       -- 'Initial', 'Incremental'
    LibrariesProcessed  INT NOT NULL,
    FilesProcessed      INT NULL,
    BytesProcessed      BIGINT NULL,
    StartTime           DATETIME2 NOT NULL DEFAULT GETUTCDATE(),
    CompletionTime      DATETIME2 NULL,
    Status              NVARCHAR(50) NOT NULL DEFAULT 'Running'
)
GO

-- ============================================================================
-- Stored Procedures for Pipeline Operations
-- ============================================================================

-- Stored procedure to update migration status
IF OBJECT_ID('dbo.usp_UpdateMigrationStatus', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_UpdateMigrationStatus
GO

CREATE PROCEDURE dbo.usp_UpdateMigrationStatus
    @Id INT,
    @Status NVARCHAR(50),
    @StartTime DATETIME2 = NULL,
    @EndTime DATETIME2 = NULL,
    @ErrorMessage NVARCHAR(MAX) = NULL,
    @BatchId NVARCHAR(50) = NULL,
    @IncrementRetryCount INT = 0
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.MigrationControl
    SET
        Status = @Status,
        StartTime = ISNULL(@StartTime, StartTime),
        EndTime = ISNULL(@EndTime, EndTime),
        ErrorMessage = ISNULL(@ErrorMessage, ErrorMessage),
        BatchId = ISNULL(@BatchId, BatchId),
        RetryCount = RetryCount + @IncrementRetryCount,
        LastRetryTime = CASE WHEN @IncrementRetryCount > 0 THEN GETUTCDATE() ELSE LastRetryTime END,
        ModifiedDate = GETUTCDATE()
    WHERE Id = @Id
END
GO

-- Stored procedure to log batch start
IF OBJECT_ID('dbo.usp_LogBatchStart', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_LogBatchStart
GO

CREATE PROCEDURE dbo.usp_LogBatchStart
    @BatchId NVARCHAR(50),
    @PipelineRunId NVARCHAR(50),
    @StartTime DATETIME2
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO dbo.BatchLog (BatchId, PipelineRunId, Status, StartTime)
    VALUES (@BatchId, @PipelineRunId, 'Started', @StartTime)
END
GO

-- Stored procedure to log batch complete
IF OBJECT_ID('dbo.usp_LogBatchComplete', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_LogBatchComplete
GO

CREATE PROCEDURE dbo.usp_LogBatchComplete
    @BatchId NVARCHAR(50),
    @Status NVARCHAR(50),
    @EndTime DATETIME2
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.BatchLog
    SET
        Status = @Status,
        EndTime = @EndTime,
        LibrariesCompleted = (SELECT COUNT(*) FROM dbo.MigrationControl WHERE BatchId = @BatchId AND Status = 'Completed'),
        LibrariesFailed = (SELECT COUNT(*) FROM dbo.MigrationControl WHERE BatchId = @BatchId AND Status = 'Failed')
    WHERE BatchId = @BatchId
END
GO

-- Stored procedure to update validation status
IF OBJECT_ID('dbo.usp_UpdateValidationStatus', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_UpdateValidationStatus
GO

CREATE PROCEDURE dbo.usp_UpdateValidationStatus
    @Id INT,
    @ValidationStatus NVARCHAR(50),
    @DiscrepancyDetails NVARCHAR(MAX) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.MigrationControl
    SET
        ValidationStatus = @ValidationStatus,
        ValidationTimestamp = GETUTCDATE(),
        DiscrepancyDetails = @DiscrepancyDetails,
        ModifiedDate = GETUTCDATE()
    WHERE Id = @Id
END
GO

-- Stored procedure to log validation result
IF OBJECT_ID('dbo.usp_LogValidationResult', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_LogValidationResult
GO

CREATE PROCEDURE dbo.usp_LogValidationResult
    @ControlTableId INT,
    @ExpectedFileCount INT,
    @ActualFileCount INT,
    @SuccessCount INT,
    @FailedCount INT,
    @ValidationTimestamp DATETIME2,
    @PipelineRunId NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.MigrationControl
    SET
        FileCount = @ExpectedFileCount,
        MigratedFileCount = @SuccessCount,
        FailedFileCount = @FailedCount,
        ValidationTimestamp = @ValidationTimestamp,
        ModifiedDate = GETUTCDATE()
    WHERE Id = @ControlTableId
END
GO

-- Stored procedure to update watermark
IF OBJECT_ID('dbo.usp_UpdateWatermark', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_UpdateWatermark
GO

CREATE PROCEDURE dbo.usp_UpdateWatermark
    @SiteUrl NVARCHAR(500),
    @LibraryName NVARCHAR(255),
    @LastModifiedDate DATETIME2,
    @LastSyncTime DATETIME2
AS
BEGIN
    SET NOCOUNT ON;

    MERGE dbo.IncrementalWatermark AS target
    USING (SELECT @SiteUrl AS SiteUrl, @LibraryName AS LibraryName) AS source
    ON target.SiteUrl = source.SiteUrl AND target.LibraryName = source.LibraryName
    WHEN MATCHED THEN
        UPDATE SET
            LastModifiedDate = @LastModifiedDate,
            LastSyncTime = @LastSyncTime
    WHEN NOT MATCHED THEN
        INSERT (SiteUrl, LibraryName, LastModifiedDate, LastSyncTime)
        VALUES (@SiteUrl, @LibraryName, @LastModifiedDate, @LastSyncTime);
END
GO

-- Stored procedure to log sync run
IF OBJECT_ID('dbo.usp_LogSyncRun', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_LogSyncRun
GO

CREATE PROCEDURE dbo.usp_LogSyncRun
    @PipelineRunId NVARCHAR(50),
    @SyncType NVARCHAR(50),
    @LibrariesProcessed INT,
    @CompletionTime DATETIME2
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO dbo.SyncLog (PipelineRunId, SyncType, LibrariesProcessed, CompletionTime, Status)
    VALUES (@PipelineRunId, @SyncType, @LibrariesProcessed, @CompletionTime, 'Completed')
END
GO

PRINT 'Migration control tables and stored procedures created successfully.'
GO
