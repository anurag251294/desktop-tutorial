/*
================================================================================
Hydro One SharePoint to ADLS Migration - Production Schema Updates
================================================================================
Description: Adds DeltaLink and DriveId columns to IncrementalWatermark table
             for true incremental sync support. Updates the usp_UpdateWatermark
             stored procedure to accept and persist these new fields.

             Run AFTER the initial schema (create_control_table.sql) has been
             deployed. Safe to run multiple times (uses IF NOT EXISTS checks).

Author:      Microsoft Azure Data Engineering Team
Created:     2026-02-17
Project:     Hydro One SharePoint Migration - Production Readiness
================================================================================
*/

-- ============================================================================
-- Step 1: Add DeltaLink column to IncrementalWatermark
-- Stores the Graph API @odata.deltaLink for true incremental delta queries.
-- On subsequent sync runs, this URL is used instead of a fresh /root/delta call,
-- so the API returns only items changed since the last sync.
-- ============================================================================
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.IncrementalWatermark')
    AND name = 'DeltaLink'
)
BEGIN
    ALTER TABLE dbo.IncrementalWatermark ADD DeltaLink NVARCHAR(2000) NULL;
    PRINT 'Added DeltaLink column to IncrementalWatermark table.'
END
ELSE
BEGIN
    PRINT 'DeltaLink column already exists on IncrementalWatermark table. Skipping.'
END
GO

-- ============================================================================
-- Step 2: Add DriveId column to IncrementalWatermark
-- Caches the Graph API drive ID for each library, avoiding a redundant
-- GET /sites/{host}:{siteUrl}:/drive call on every incremental sync run.
-- ============================================================================
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.IncrementalWatermark')
    AND name = 'DriveId'
)
BEGIN
    ALTER TABLE dbo.IncrementalWatermark ADD DriveId NVARCHAR(100) NULL;
    PRINT 'Added DriveId column to IncrementalWatermark table.'
END
ELSE
BEGIN
    PRINT 'DriveId column already exists on IncrementalWatermark table. Skipping.'
END
GO

-- ============================================================================
-- Step 3: Update usp_UpdateWatermark to accept DeltaLink and DriveId
-- Uses the same MERGE pattern as the original stored procedure but now
-- persists DeltaLink and DriveId alongside the watermark timestamps.
-- ============================================================================
IF OBJECT_ID('dbo.usp_UpdateWatermark', 'P') IS NOT NULL
    DROP PROCEDURE dbo.usp_UpdateWatermark
GO

CREATE PROCEDURE dbo.usp_UpdateWatermark
    @SiteUrl NVARCHAR(500),
    @LibraryName NVARCHAR(255),
    @LastModifiedDate DATETIME2,
    @LastSyncTime DATETIME2,
    @DeltaLink NVARCHAR(2000) = NULL,
    @DriveId NVARCHAR(100) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    MERGE dbo.IncrementalWatermark AS target
    USING (SELECT @SiteUrl AS SiteUrl, @LibraryName AS LibraryName) AS source
    ON target.SiteUrl = source.SiteUrl AND target.LibraryName = source.LibraryName
    WHEN MATCHED THEN
        UPDATE SET
            LastModifiedDate = @LastModifiedDate,
            LastSyncTime = @LastSyncTime,
            DeltaLink = ISNULL(@DeltaLink, DeltaLink),
            DriveId = ISNULL(@DriveId, DriveId)
    WHEN NOT MATCHED THEN
        INSERT (SiteUrl, LibraryName, LastModifiedDate, LastSyncTime, DeltaLink, DriveId)
        VALUES (@SiteUrl, @LibraryName, @LastModifiedDate, @LastSyncTime, @DeltaLink, @DriveId);
END
GO

PRINT 'Production schema updates completed successfully.'
PRINT '  - IncrementalWatermark.DeltaLink (NVARCHAR 2000, nullable)'
PRINT '  - IncrementalWatermark.DriveId (NVARCHAR 100, nullable)'
PRINT '  - usp_UpdateWatermark updated to accept @DeltaLink and @DriveId'
GO
