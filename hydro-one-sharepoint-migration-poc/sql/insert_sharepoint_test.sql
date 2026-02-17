/*
================================================================================
Insert SharePoint SalesAndMarketing site for migration testing
================================================================================
Run this in Azure Portal Query Editor against MigrationControl database
Server: sql-hydroone-migration-test.database.windows.net
================================================================================
*/

-- Clean up any previous test data
DELETE FROM dbo.MigrationAuditLog;
DELETE FROM dbo.BatchLog;
DELETE FROM dbo.MigrationControl;

-- Insert the real SharePoint library
INSERT INTO dbo.MigrationControl (
    SiteUrl,
    LibraryName,
    SiteTitle,
    LibraryTitle,
    Status,
    Priority,
    EnableIncrementalSync,
    CreatedBy
)
VALUES (
    '/sites/SalesAndMarketing',
    'Shared Documents',
    'Sales And Marketing',
    'Documents',
    'Pending',
    1,
    1,
    'anuragdhuria'
);

-- Verify
SELECT * FROM dbo.MigrationControl;
