/*
================================================================================
Hydro One SharePoint to ADLS Migration - Progress Monitoring Queries
================================================================================
Description: Collection of useful queries for monitoring migration progress,
             identifying failed files, tracking size migrated per day, and
             estimating completion time.

Author:      Microsoft Azure Data Engineering Team
Created:     2024
Project:     Hydro One SharePoint Migration POC

TABLE OF CONTENTS
=================
Line   Section
----   -------
 19    DASHBOARD QUERIES
         - Overall Migration Progress Summary
         - Overall File Migration Progress
 49    PROGRESS TRACKING QUERIES
         - Migration Progress by Site
         - Size Migrated Per Day
         - Hourly Migration Rate
 93    ESTIMATED COMPLETION TIME
         - Calculate estimated completion based on average rate
133    FAILED FILES QUERIES
         - Summary of Failed Files by Error Code
         - Failed Files Detail (top 100)
         - Failed Libraries with Retry Count
         - Files That Failed Multiple Times
194    THROTTLING ANALYSIS
         - 429 Errors by Hour
209    VALIDATION QUERIES
         - Libraries with Validation Discrepancies
         - Checksum Mismatches
244    BATCH ANALYSIS
         - Batch Performance Summary
265    FILE SIZE DISTRIBUTION
         - File Size Distribution Analysis
         - Large Files (top 50)
305    INCREMENTAL SYNC MONITORING
         - Recent Incremental Sync Activity
         - Incremental Sync Summary by Day
================================================================================
*/

-- ============================================================================
-- DASHBOARD QUERIES
-- ============================================================================

-- Overall Migration Progress Summary
SELECT
    'Migration Progress Summary' AS ReportName,
    (SELECT COUNT(*) FROM dbo.MigrationControl) AS TotalLibraries,
    (SELECT COUNT(*) FROM dbo.MigrationControl WHERE Status = 'Completed') AS CompletedLibraries,
    (SELECT COUNT(*) FROM dbo.MigrationControl WHERE Status = 'InProgress') AS InProgressLibraries,
    (SELECT COUNT(*) FROM dbo.MigrationControl WHERE Status = 'Failed') AS FailedLibraries,
    (SELECT COUNT(*) FROM dbo.MigrationControl WHERE Status = 'Pending') AS PendingLibraries,
    CAST(
        (SELECT COUNT(*) FROM dbo.MigrationControl WHERE Status = 'Completed') * 100.0 /
        NULLIF((SELECT COUNT(*) FROM dbo.MigrationControl), 0)
    AS DECIMAL(5,2)) AS ProgressPercentage
GO

-- Overall File Migration Progress
SELECT
    'File Migration Progress' AS ReportName,
    COUNT(*) AS TotalFilesProcessed,
    SUM(CASE WHEN MigrationStatus = 'Success' THEN 1 ELSE 0 END) AS SuccessfulFiles,
    SUM(CASE WHEN MigrationStatus = 'Failed' THEN 1 ELSE 0 END) AS FailedFiles,
    SUM(CASE WHEN MigrationStatus = 'IncrementalSync' THEN 1 ELSE 0 END) AS IncrementalSyncFiles,
    CAST(SUM(FileSizeBytes) / 1073741824.0 AS DECIMAL(18,2)) AS TotalSizeGB,
    CAST(SUM(CASE WHEN MigrationStatus = 'Success' THEN FileSizeBytes ELSE 0 END) / 1073741824.0 AS DECIMAL(18,2)) AS SuccessfulSizeGB,
    CAST(
        SUM(CASE WHEN MigrationStatus = 'Success' THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(COUNT(*), 0)
    AS DECIMAL(5,2)) AS SuccessRatePercentage
FROM dbo.MigrationAuditLog
GO

-- ============================================================================
-- PROGRESS TRACKING QUERIES
-- ============================================================================

-- Migration Progress by Site
SELECT
    mc.SiteUrl,
    COUNT(*) AS TotalLibraries,
    SUM(CASE WHEN mc.Status = 'Completed' THEN 1 ELSE 0 END) AS CompletedLibraries,
    SUM(CASE WHEN mc.Status = 'Failed' THEN 1 ELSE 0 END) AS FailedLibraries,
    CAST(SUM(mc.TotalSizeBytes) / 1073741824.0 AS DECIMAL(18,2)) AS TotalSizeGB,
    CAST(SUM(mc.MigratedSizeBytes) / 1073741824.0 AS DECIMAL(18,2)) AS MigratedSizeGB
FROM dbo.MigrationControl mc
GROUP BY mc.SiteUrl
ORDER BY TotalSizeGB DESC
GO

-- Size Migrated Per Day
SELECT
    CAST([Timestamp] AS DATE) AS MigrationDate,
    COUNT(*) AS FilesCount,
    CAST(SUM(FileSizeBytes) / 1073741824.0 AS DECIMAL(18,2)) AS SizeGB,
    CAST(SUM(FileSizeBytes) / 1099511627776.0 AS DECIMAL(18,3)) AS SizeTB,
    COUNT(DISTINCT PipelineRunId) AS PipelineRuns,
    SUM(CASE WHEN MigrationStatus = 'Success' THEN 1 ELSE 0 END) AS SuccessfulFiles,
    SUM(CASE WHEN MigrationStatus = 'Failed' THEN 1 ELSE 0 END) AS FailedFiles
FROM dbo.MigrationAuditLog
GROUP BY CAST([Timestamp] AS DATE)
ORDER BY MigrationDate DESC
GO

-- Hourly Migration Rate (for performance analysis)
SELECT
    CAST([Timestamp] AS DATE) AS MigrationDate,
    DATEPART(HOUR, [Timestamp]) AS MigrationHour,
    COUNT(*) AS FilesCount,
    CAST(SUM(FileSizeBytes) / 1073741824.0 AS DECIMAL(18,2)) AS SizeGB,
    AVG(FileSizeBytes / 1048576.0) AS AvgFileSizeMB
FROM dbo.MigrationAuditLog
WHERE MigrationStatus = 'Success'
GROUP BY CAST([Timestamp] AS DATE), DATEPART(HOUR, [Timestamp])
ORDER BY MigrationDate DESC, MigrationHour DESC
GO

-- ============================================================================
-- ESTIMATED COMPLETION TIME
-- ============================================================================

-- Calculate estimated completion time based on average migration rate
WITH MigrationRate AS (
    SELECT
        CAST(SUM(FileSizeBytes) AS FLOAT) / 1099511627776.0 AS TotalMigratedTB,
        DATEDIFF(HOUR, MIN([Timestamp]), MAX([Timestamp])) AS TotalHours,
        COUNT(*) AS TotalFiles
    FROM dbo.MigrationAuditLog
    WHERE MigrationStatus = 'Success'
),
RemainingWork AS (
    SELECT
        CAST(SUM(TotalSizeBytes) AS FLOAT) / 1099511627776.0 AS RemainingTB,
        SUM(FileCount) AS RemainingFiles
    FROM dbo.MigrationControl
    WHERE Status IN ('Pending', 'Failed')
)
SELECT
    'Estimated Completion' AS ReportName,
    mr.TotalMigratedTB AS MigratedTB,
    rw.RemainingTB AS RemainingTB,
    mr.TotalHours AS HoursElapsed,
    CASE WHEN mr.TotalHours > 0 THEN mr.TotalMigratedTB / mr.TotalHours ELSE 0 END AS TBPerHour,
    CASE
        WHEN mr.TotalHours > 0 AND mr.TotalMigratedTB > 0
        THEN CAST(rw.RemainingTB / (mr.TotalMigratedTB / mr.TotalHours) AS DECIMAL(10,1))
        ELSE NULL
    END AS EstimatedRemainingHours,
    CASE
        WHEN mr.TotalHours > 0 AND mr.TotalMigratedTB > 0
        THEN DATEADD(HOUR, CAST(rw.RemainingTB / (mr.TotalMigratedTB / mr.TotalHours) AS INT), GETUTCDATE())
        ELSE NULL
    END AS EstimatedCompletionTime
FROM MigrationRate mr
CROSS JOIN RemainingWork rw
GO

-- ============================================================================
-- FAILED FILES QUERIES
-- ============================================================================

-- Summary of Failed Files by Error Code
SELECT
    ErrorCode,
    COUNT(*) AS FailedCount,
    CAST(SUM(FileSizeBytes) / 1073741824.0 AS DECIMAL(18,2)) AS TotalSizeGB,
    MIN([Timestamp]) AS FirstFailure,
    MAX([Timestamp]) AS LastFailure
FROM dbo.MigrationAuditLog
WHERE MigrationStatus = 'Failed'
GROUP BY ErrorCode
ORDER BY FailedCount DESC
GO

-- Failed Files Detail
SELECT TOP 100
    FileName,
    SourcePath,
    FileSizeMB,
    ErrorCode,
    LEFT(ErrorDetails, 500) AS ErrorSummary,
    [Timestamp],
    PipelineRunId
FROM dbo.MigrationAuditLog
WHERE MigrationStatus = 'Failed'
ORDER BY [Timestamp] DESC
GO

-- Failed Libraries with Retry Count
SELECT
    mc.SiteUrl,
    mc.LibraryName,
    mc.Status,
    mc.RetryCount,
    mc.ErrorMessage,
    mc.FileCount,
    CAST(mc.TotalSizeBytes / 1073741824.0 AS DECIMAL(18,2)) AS SizeGB,
    mc.LastRetryTime
FROM dbo.MigrationControl mc
WHERE mc.Status = 'Failed'
ORDER BY mc.RetryCount DESC, mc.TotalSizeBytes DESC
GO

-- Files That Failed Multiple Times (needs retry)
SELECT
    SourcePath,
    FileName,
    COUNT(*) AS FailureCount,
    MAX(ErrorCode) AS LastErrorCode,
    MAX([Timestamp]) AS LastAttempt,
    MAX(FileSizeBytes) AS FileSizeBytes
FROM dbo.MigrationAuditLog
WHERE MigrationStatus = 'Failed'
GROUP BY SourcePath, FileName
HAVING COUNT(*) > 1
ORDER BY FailureCount DESC
GO

-- ============================================================================
-- THROTTLING ANALYSIS
-- ============================================================================

-- 429 Errors by Hour (to identify throttling patterns)
SELECT
    CAST([Timestamp] AS DATE) AS [Date],
    DATEPART(HOUR, [Timestamp]) AS [Hour],
    COUNT(*) AS ThrottleCount
FROM dbo.MigrationAuditLog
WHERE ErrorCode = '429'
GROUP BY CAST([Timestamp] AS DATE), DATEPART(HOUR, [Timestamp])
ORDER BY [Date] DESC, [Hour]
GO

-- ============================================================================
-- VALIDATION QUERIES
-- ============================================================================

-- Libraries with Validation Discrepancies
SELECT
    SiteUrl,
    LibraryName,
    FileCount AS ExpectedFiles,
    MigratedFileCount AS ActualFiles,
    FailedFileCount AS FailedFiles,
    ValidationStatus,
    DiscrepancyDetails,
    ValidationTimestamp
FROM dbo.MigrationControl
WHERE ValidationStatus = 'Discrepancy'
ORDER BY FileCount DESC
GO

-- Checksum Mismatches (if checksums are captured)
SELECT
    FileName,
    SourcePath,
    DestinationPath,
    SourceChecksum,
    DestinationChecksum,
    FileSizeMB,
    [Timestamp]
FROM dbo.MigrationAuditLog
WHERE SourceChecksum IS NOT NULL
  AND DestinationChecksum IS NOT NULL
  AND SourceChecksum != DestinationChecksum
ORDER BY [Timestamp] DESC
GO

-- ============================================================================
-- BATCH ANALYSIS
-- ============================================================================

-- Batch Performance Summary
SELECT
    bl.BatchId,
    bl.Status,
    bl.StartTime,
    bl.EndTime,
    DATEDIFF(MINUTE, bl.StartTime, bl.EndTime) AS DurationMinutes,
    bl.LibrariesCompleted,
    bl.LibrariesFailed,
    COUNT(mal.Id) AS TotalFiles,
    CAST(SUM(mal.FileSizeBytes) / 1073741824.0 AS DECIMAL(18,2)) AS SizeGB
FROM dbo.BatchLog bl
LEFT JOIN dbo.MigrationAuditLog mal ON bl.BatchId = mal.BatchId
GROUP BY bl.BatchId, bl.Status, bl.StartTime, bl.EndTime, bl.LibrariesCompleted, bl.LibrariesFailed
ORDER BY bl.StartTime DESC
GO

-- ============================================================================
-- FILE SIZE DISTRIBUTION
-- ============================================================================

-- File Size Distribution Analysis
SELECT
    CASE
        WHEN FileSizeBytes < 1048576 THEN '< 1 MB'
        WHEN FileSizeBytes < 10485760 THEN '1-10 MB'
        WHEN FileSizeBytes < 104857600 THEN '10-100 MB'
        WHEN FileSizeBytes < 1073741824 THEN '100 MB - 1 GB'
        ELSE '> 1 GB'
    END AS SizeCategory,
    COUNT(*) AS FileCount,
    CAST(SUM(FileSizeBytes) / 1073741824.0 AS DECIMAL(18,2)) AS TotalSizeGB,
    CAST(AVG(FileSizeBytes) / 1048576.0 AS DECIMAL(18,2)) AS AvgSizeMB
FROM dbo.MigrationAuditLog
GROUP BY
    CASE
        WHEN FileSizeBytes < 1048576 THEN '< 1 MB'
        WHEN FileSizeBytes < 10485760 THEN '1-10 MB'
        WHEN FileSizeBytes < 104857600 THEN '10-100 MB'
        WHEN FileSizeBytes < 1073741824 THEN '100 MB - 1 GB'
        ELSE '> 1 GB'
    END
ORDER BY MIN(FileSizeBytes)
GO

-- Large Files (potential issues)
SELECT TOP 50
    FileName,
    SourcePath,
    FileSizeMB,
    MigrationStatus,
    ErrorDetails,
    [Timestamp]
FROM dbo.MigrationAuditLog
ORDER BY FileSizeBytes DESC
GO

-- ============================================================================
-- INCREMENTAL SYNC MONITORING
-- ============================================================================

-- Recent Incremental Sync Activity
SELECT
    SiteUrl,
    LibraryName,
    LastModifiedDate,
    LastSyncTime,
    FilesProcessed,
    DATEDIFF(HOUR, LastSyncTime, GETUTCDATE()) AS HoursSinceLastSync
FROM dbo.IncrementalWatermark
ORDER BY LastSyncTime DESC
GO

-- Incremental Sync Summary by Day
SELECT
    CAST([Timestamp] AS DATE) AS SyncDate,
    COUNT(*) AS FilesSync,
    CAST(SUM(FileSizeBytes) / 1073741824.0 AS DECIMAL(18,2)) AS SizeGB
FROM dbo.MigrationAuditLog
WHERE MigrationStatus = 'IncrementalSync'
GROUP BY CAST([Timestamp] AS DATE)
ORDER BY SyncDate DESC
GO

PRINT 'Migration progress queries created successfully.'
GO
