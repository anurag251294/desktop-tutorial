/*
================================================================================
Hydro One SharePoint to ADLS Migration - Audit Log Table Schema
================================================================================
Description: Creates the MigrationAuditLog table that tracks per-file migration
             status, including source/destination paths, checksums, errors,
             and timing information.

Author:      PwC Azure Data Engineering Team
Created:     2024
Project:     Hydro One SharePoint Migration POC
================================================================================
*/

-- Drop table if exists (for clean deployment)
IF OBJECT_ID('dbo.MigrationAuditLog', 'U') IS NOT NULL
BEGIN
    DROP TABLE dbo.MigrationAuditLog
END
GO

-- Create MigrationAuditLog table
CREATE TABLE dbo.MigrationAuditLog
(
    -- Primary Key
    Id                      BIGINT IDENTITY(1,1) PRIMARY KEY,

    -- File Information
    FileName                NVARCHAR(500) NOT NULL,              -- Original file name
    FileExtension           AS RIGHT(FileName, CHARINDEX('.', REVERSE(FileName)) - 1) PERSISTED,  -- Computed extension
    SourcePath              NVARCHAR(2000) NOT NULL,             -- Full SharePoint server-relative path
    DestinationPath         NVARCHAR(2000) NOT NULL,             -- Full ADLS path

    -- Size Information
    FileSizeBytes           BIGINT NULL,                         -- File size in bytes
    FileSizeMB              AS CAST(FileSizeBytes / 1048576.0 AS DECIMAL(18,2)) PERSISTED,  -- Size in MB

    -- Integrity
    SourceChecksum          NVARCHAR(64) NULL,                   -- MD5/SHA256 of source file
    DestinationChecksum     NVARCHAR(64) NULL,                   -- MD5/SHA256 of destination file
    ChecksumMatch           AS CASE WHEN SourceChecksum = DestinationChecksum THEN 1 ELSE 0 END,

    -- Migration Status
    MigrationStatus         NVARCHAR(50) NOT NULL,               -- Success, Failed, Skipped, IncrementalSync

    -- Timing
    Timestamp               DATETIME2 NOT NULL DEFAULT GETUTCDATE(),  -- When this record was created
    CopyStartTime           DATETIME2 NULL,                      -- When copy operation started
    CopyEndTime             DATETIME2 NULL,                      -- When copy operation ended
    CopyDurationMs          AS DATEDIFF(MILLISECOND, CopyStartTime, CopyEndTime),  -- Duration

    -- Error Details
    ErrorDetails            NVARCHAR(MAX) NULL,                  -- Full error message/stack trace
    ErrorCode               NVARCHAR(50) NULL,                   -- Error code (e.g., 401, 404, 429)
    RetryAttempt            INT NOT NULL DEFAULT 1,              -- Which retry attempt this was

    -- Pipeline Tracking
    PipelineRunId           NVARCHAR(50) NOT NULL,               -- ADF pipeline run ID
    ActivityRunId           NVARCHAR(50) NULL,                   -- ADF activity run ID
    BatchId                 NVARCHAR(50) NULL,                   -- Batch identifier

    -- SharePoint Metadata
    SharePointItemId        NVARCHAR(50) NULL,                   -- SharePoint unique item ID
    SharePointModifiedDate  DATETIME2 NULL,                      -- Last modified date in SharePoint
    SharePointCreatedDate   DATETIME2 NULL,                      -- Created date in SharePoint
    ContentType             NVARCHAR(255) NULL,                  -- SharePoint content type

    -- Indexing columns
    SiteName                NVARCHAR(255) NULL,                  -- Extracted site name
    LibraryName             NVARCHAR(255) NULL,                  -- Extracted library name

    -- Constraints
    CONSTRAINT CK_AuditLog_MigrationStatus CHECK (MigrationStatus IN ('Success', 'Failed', 'Skipped', 'IncrementalSync', 'Pending', 'InProgress'))
)
GO

-- Create indexes for common query patterns
CREATE NONCLUSTERED INDEX IX_AuditLog_MigrationStatus
ON dbo.MigrationAuditLog (MigrationStatus)
INCLUDE (FileName, FileSizeBytes, Timestamp)
GO

CREATE NONCLUSTERED INDEX IX_AuditLog_PipelineRunId
ON dbo.MigrationAuditLog (PipelineRunId)
INCLUDE (MigrationStatus, FileSizeBytes)
GO

CREATE NONCLUSTERED INDEX IX_AuditLog_Timestamp
ON dbo.MigrationAuditLog (Timestamp DESC)
INCLUDE (MigrationStatus, FileSizeBytes)
GO

CREATE NONCLUSTERED INDEX IX_AuditLog_SourcePath
ON dbo.MigrationAuditLog (SourcePath)
INCLUDE (MigrationStatus)
GO

CREATE NONCLUSTERED INDEX IX_AuditLog_BatchId
ON dbo.MigrationAuditLog (BatchId)
INCLUDE (MigrationStatus, FileSizeBytes, Timestamp)
GO

CREATE NONCLUSTERED INDEX IX_AuditLog_SiteLibrary
ON dbo.MigrationAuditLog (SiteName, LibraryName)
INCLUDE (MigrationStatus, FileSizeBytes)
GO

-- Create ValidationLog table for detailed validation results
IF OBJECT_ID('dbo.ValidationLog', 'U') IS NOT NULL
BEGIN
    DROP TABLE dbo.ValidationLog
END
GO

CREATE TABLE dbo.ValidationLog
(
    Id                      BIGINT IDENTITY(1,1) PRIMARY KEY,
    ValidationRunId         NVARCHAR(50) NOT NULL,
    SiteUrl                 NVARCHAR(500) NOT NULL,
    LibraryName             NVARCHAR(255) NOT NULL,
    ValidationType          NVARCHAR(50) NOT NULL,               -- FileCount, Size, Checksum
    ExpectedValue           NVARCHAR(100) NOT NULL,
    ActualValue             NVARCHAR(100) NOT NULL,
    IsMatch                 BIT NOT NULL,
    DiscrepancyDetails      NVARCHAR(MAX) NULL,
    Timestamp               DATETIME2 NOT NULL DEFAULT GETUTCDATE()
)
GO

-- ============================================================================
-- Stored Procedure for Logging File Audit
-- ============================================================================

IF OBJECT_ID('dbo.usp_LogFileAudit', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_LogFileAudit
GO

CREATE PROCEDURE dbo.usp_LogFileAudit
    @FileName NVARCHAR(500),
    @SourcePath NVARCHAR(2000),
    @DestinationPath NVARCHAR(2000),
    @FileSizeBytes BIGINT = NULL,
    @MigrationStatus NVARCHAR(50),
    @PipelineRunId NVARCHAR(50),
    @ErrorDetails NVARCHAR(MAX) = NULL,
    @SourceChecksum NVARCHAR(64) = NULL,
    @SharePointItemId NVARCHAR(50) = NULL,
    @BatchId NVARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    -- Extract site and library from source path
    DECLARE @SiteName NVARCHAR(255)
    DECLARE @LibraryName NVARCHAR(255)

    -- Parse path: /sites/SiteName/LibraryName/...
    IF @SourcePath LIKE '/sites/%'
    BEGIN
        SET @SiteName = SUBSTRING(@SourcePath, 8, CHARINDEX('/', @SourcePath, 8) - 8)
        DECLARE @AfterSite INT = CHARINDEX('/', @SourcePath, 8) + 1
        DECLARE @NextSlash INT = CHARINDEX('/', @SourcePath, @AfterSite)
        IF @NextSlash > 0
            SET @LibraryName = SUBSTRING(@SourcePath, @AfterSite, @NextSlash - @AfterSite)
        ELSE
            SET @LibraryName = SUBSTRING(@SourcePath, @AfterSite, LEN(@SourcePath) - @AfterSite + 1)
    END

    INSERT INTO dbo.MigrationAuditLog (
        FileName,
        SourcePath,
        DestinationPath,
        FileSizeBytes,
        MigrationStatus,
        PipelineRunId,
        ErrorDetails,
        SourceChecksum,
        SharePointItemId,
        BatchId,
        SiteName,
        LibraryName,
        Timestamp,
        ErrorCode
    )
    VALUES (
        @FileName,
        @SourcePath,
        @DestinationPath,
        @FileSizeBytes,
        @MigrationStatus,
        @PipelineRunId,
        @ErrorDetails,
        @SourceChecksum,
        @SharePointItemId,
        @BatchId,
        @SiteName,
        @LibraryName,
        GETUTCDATE(),
        CASE
            WHEN @ErrorDetails LIKE '%401%' THEN '401'
            WHEN @ErrorDetails LIKE '%403%' THEN '403'
            WHEN @ErrorDetails LIKE '%404%' THEN '404'
            WHEN @ErrorDetails LIKE '%429%' THEN '429'
            WHEN @ErrorDetails LIKE '%503%' THEN '503'
            WHEN @ErrorDetails LIKE '%timeout%' THEN 'TIMEOUT'
            ELSE NULL
        END
    )
END
GO

-- ============================================================================
-- Stored Procedure for Bulk Insert (for efficiency)
-- ============================================================================

IF OBJECT_ID('dbo.usp_BulkLogFileAudit', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_BulkLogFileAudit
GO

CREATE PROCEDURE dbo.usp_BulkLogFileAudit
    @AuditData NVARCHAR(MAX)  -- JSON array of audit records
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO dbo.MigrationAuditLog (
        FileName, SourcePath, DestinationPath, FileSizeBytes,
        MigrationStatus, PipelineRunId, ErrorDetails, Timestamp
    )
    SELECT
        JSON_VALUE(value, '$.FileName'),
        JSON_VALUE(value, '$.SourcePath'),
        JSON_VALUE(value, '$.DestinationPath'),
        CAST(JSON_VALUE(value, '$.FileSizeBytes') AS BIGINT),
        JSON_VALUE(value, '$.MigrationStatus'),
        JSON_VALUE(value, '$.PipelineRunId'),
        JSON_VALUE(value, '$.ErrorDetails'),
        GETUTCDATE()
    FROM OPENJSON(@AuditData)
END
GO

PRINT 'Migration audit log table and stored procedures created successfully.'
GO
