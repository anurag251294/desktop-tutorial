/*
================================================================================
Hydro One SharePoint Migration - Fake Data Seed (Synthetic E2E Test)
================================================================================
Purpose:     Inserts 5 synthetic library rows into dbo.MigrationControl so the
             migration pipelines can be exercised without a real SharePoint
             tenant or Graph API consent. Use alongside PL_FakeData_E2E_Test
             (created via scripts/Deploy-FakeData-Pipeline.py / hydroone_fake_e2e.py).

When to run: Smoke-testing the SQL <-> ADF <-> ADLS plumbing on a fresh
             environment, or when SharePoint credentials are not yet wired up.

How to run:  Either from a VNet-attached jumpbox (SQL has publicNetworkAccess
             disabled in test/prod), OR via the PL_FakeData_E2E_Test pipeline
             which runs the same INSERT inside ADF.

Cleanup:     See bottom of file for the DELETE statement.
================================================================================
*/

-- Remove any prior fake rows
DELETE FROM dbo.MigrationControl WHERE LibraryName LIKE 'FAKE_%';

-- Seed 5 fake libraries spanning different "sites" + sizes
INSERT INTO dbo.MigrationControl
    (SiteUrl, LibraryName, SiteTitle, LibraryTitle, Status, FileCount, FolderCount,
     TotalSizeBytes, LargestFileSizeBytes, RetryCount, Priority, EnableIncrementalSync)
VALUES
    ('https://m365x52073746.sharepoint.com/sites/FakeSite1', 'FAKE_Documents',
     'Fake Site 1 - Engineering', 'Documents Library', 'Pending', 5, 1, 524288, 102400, 0, 100, 1),
    ('https://m365x52073746.sharepoint.com/sites/FakeSite2', 'FAKE_Reports',
     'Fake Site 2 - Finance', 'Reports', 'Pending', 3, 0, 262144, 92160, 0, 100, 1),
    ('https://m365x52073746.sharepoint.com/sites/FakeSite3', 'FAKE_Archive',
     'Fake Site 3 - Legal', 'Archive', 'Pending', 8, 2, 1048576, 524288, 0, 100, 1),
    ('https://m365x52073746.sharepoint.com/sites/FakeSite4', 'FAKE_HR_Policies',
     'HR Portal', 'HR Policies', 'Pending', 12, 3, 786432, 81920, 0, 50, 1),
    ('https://m365x52073746.sharepoint.com/sites/FakeSite5', 'FAKE_Project_Specs',
     'Project Portal', 'Specs', 'Pending', 4, 0, 131072, 65536, 0, 100, 1);

-- Verify
SELECT Id, SiteUrl, LibraryName, Status, FileCount, TotalSizeBytes, Priority
FROM dbo.MigrationControl
WHERE LibraryName LIKE 'FAKE_%'
ORDER BY Id;

/*
================================================================================
Cleanup (run after the synthetic test)
================================================================================

DELETE FROM dbo.MigrationControl WHERE LibraryName LIKE 'FAKE_%';

-- And if PL_FakeData_E2E_Test wrote audit rows:
-- DELETE FROM dbo.MigrationAuditLog WHERE BatchId LIKE 'FAKE-BATCH-%';

-- Files in ADLS can be removed via:
-- az storage fs directory delete --account-name sthydroonemigtest \
--     --file-system sharepoint-migration --name FAKE_Documents
-- (and similar for FAKE_Reports, FAKE_Archive, FAKE_HR_Policies, FAKE_Project_Specs)
*/
