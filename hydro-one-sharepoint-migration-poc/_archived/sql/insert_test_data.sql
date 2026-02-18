-- =============================================
-- Insert Test Data for End-to-End Validation
-- Run this in Azure Portal Query Editor
-- =============================================

-- 1. Insert control table record for the test library
INSERT INTO dbo.MigrationControl (
    SiteUrl, LibraryName, SiteTitle, LibraryTitle,
    FileCount, TotalSizeBytes,
    Status, Priority,
    StartTime, EndTime,
    MigratedFileCount, MigratedSizeBytes,
    ValidationStatus, EnableIncrementalSync
)
VALUES (
    '/sites/TestSite',
    'Documents',
    'TestSite',
    'Documents',
    10,                     -- 10 test files
    659,                    -- Total bytes of all 10 files
    'Completed',            -- Mark as completed (simulating finished migration)
    1,
    DATEADD(HOUR, -1, GETUTCDATE()),   -- Started 1 hour ago
    GETUTCDATE(),                       -- Completed now
    10,                                 -- All 10 files migrated
    659,                                -- All bytes migrated
    'Pending',                          -- Validation pending
    1                                   -- Enable incremental sync
);

-- 2. Insert audit log records for each migrated file
INSERT INTO dbo.MigrationAuditLog (FileName, SourcePath, DestinationPath, FileSizeBytes, MigrationStatus, PipelineRunId, BatchId, SiteName, LibraryName)
VALUES
('Q1_2026_Report.txt', '/sites/TestSite/Documents/Q1_2026_Report.txt', 'sharepoint-migration/TestSite/Documents/Q1_2026_Report.txt', 68, 'Success', 'TEST-RUN-001', 'BATCH-TEST-001', 'TestSite', 'Documents'),
('Budget_Plan_2026.txt', '/sites/TestSite/Documents/Budget_Plan_2026.txt', 'sharepoint-migration/TestSite/Documents/Budget_Plan_2026.txt', 66, 'Success', 'TEST-RUN-001', 'BATCH-TEST-001', 'TestSite', 'Documents'),
('Safety_Inspection_Checklist.txt', '/sites/TestSite/Documents/Safety_Inspection_Checklist.txt', 'sharepoint-migration/TestSite/Documents/Safety_Inspection_Checklist.txt', 61, 'Success', 'TEST-RUN-001', 'BATCH-TEST-001', 'TestSite', 'Documents'),
('Environmental_Assessment.txt', '/sites/TestSite/Documents/Environmental_Assessment.txt', 'sharepoint-migration/TestSite/Documents/Environmental_Assessment.txt', 69, 'Success', 'TEST-RUN-001', 'BATCH-TEST-001', 'TestSite', 'Documents'),
('Training_Schedule.txt', '/sites/TestSite/Documents/Training_Schedule.txt', 'sharepoint-migration/TestSite/Documents/Training_Schedule.txt', 72, 'Success', 'TEST-RUN-001', 'BATCH-TEST-001', 'TestSite', 'Documents'),
('Asset_Inventory_North.txt', '/sites/TestSite/Documents/Asset_Inventory_North.txt', 'sharepoint-migration/TestSite/Documents/Asset_Inventory_North.txt', 71, 'Success', 'TEST-RUN-001', 'BATCH-TEST-001', 'TestSite', 'Documents'),
('Customer_Metrics_2026.txt', '/sites/TestSite/Documents/Customer_Metrics_2026.txt', 'sharepoint-migration/TestSite/Documents/Customer_Metrics_2026.txt', 60, 'Success', 'TEST-RUN-001', 'BATCH-TEST-001', 'TestSite', 'Documents'),
('OEB_Regulatory_Filing.txt', '/sites/TestSite/Documents/OEB_Regulatory_Filing.txt', 'sharepoint-migration/TestSite/Documents/OEB_Regulatory_Filing.txt', 69, 'Success', 'TEST-RUN-001', 'BATCH-TEST-001', 'TestSite', 'Documents'),
('SmartGrid_Phase2_Update.txt', '/sites/TestSite/Documents/SmartGrid_Phase2_Update.txt', 'sharepoint-migration/TestSite/Documents/SmartGrid_Phase2_Update.txt', 61, 'Success', 'TEST-RUN-001', 'BATCH-TEST-001', 'TestSite', 'Documents'),
('Procurement_Specs_HV.txt', '/sites/TestSite/Documents/Procurement_Specs_HV.txt', 'sharepoint-migration/TestSite/Documents/Procurement_Specs_HV.txt', 62, 'Success', 'TEST-RUN-001', 'BATCH-TEST-001', 'TestSite', 'Documents');

-- 3. Insert batch log record
INSERT INTO dbo.BatchLog (BatchId, PipelineRunId, StartTime, EndTime, Status, LibrariesCompleted)
VALUES (
    'BATCH-TEST-001',
    'TEST-RUN-001',
    DATEADD(HOUR, -1, GETUTCDATE()),
    GETUTCDATE(),
    'Completed',
    1
);

-- 4. Verify inserted data
SELECT 'MigrationControl' AS [Table], COUNT(*) AS [Rows] FROM dbo.MigrationControl
UNION ALL
SELECT 'MigrationAuditLog', COUNT(*) FROM dbo.MigrationAuditLog
UNION ALL
SELECT 'BatchLog', COUNT(*) FROM dbo.BatchLog;

-- 5. Show migration summary
SELECT
    mc.SiteTitle,
    mc.LibraryName,
    mc.FileCount AS ExpectedFiles,
    mc.MigratedFileCount AS MigratedFiles,
    mc.Status,
    mc.ValidationStatus,
    COUNT(al.Id) AS AuditLogEntries
FROM dbo.MigrationControl mc
LEFT JOIN dbo.MigrationAuditLog al
    ON al.SiteName = mc.SiteTitle AND al.LibraryName = mc.LibraryName
GROUP BY mc.SiteTitle, mc.LibraryName, mc.FileCount,
    mc.MigratedFileCount, mc.Status, mc.ValidationStatus;
