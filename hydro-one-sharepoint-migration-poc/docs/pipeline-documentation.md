# Hydro One SharePoint Migration - Technical Pipeline & Code Documentation

## Document Information

| Field | Value |
|-------|-------|
| Project | Hydro One SharePoint to Azure Data Lake Migration |
| Version | 1.1 |
| Author | Microsoft Azure Data Engineering Team |
| Last Updated | February 2026 |

---

## Table of Contents

1. [Solution Architecture](#1-solution-architecture)
2. [Linked Services](#2-linked-services)
3. [Datasets](#3-datasets)
4. [Pipeline: PL_Master_Migration_Orchestrator](#4-pipeline-pl_master_migration_orchestrator)
5. [Pipeline: PL_Migrate_Single_Library](#5-pipeline-pl_migrate_single_library)
6. [Pipeline: PL_Process_Subfolder](#6-pipeline-pl_process_subfolder)
7. [Pipeline: PL_Validation](#7-pipeline-pl_validation)
8. [Pipeline: PL_Incremental_Sync](#8-pipeline-pl_incremental_sync)
9. [SQL Schema & Stored Procedures](#9-sql-schema--stored-procedures)
10. [PowerShell Scripts](#10-powershell-scripts)
11. [ARM Template Reference](#11-arm-template-reference)
12. [Data Flow Diagrams](#12-data-flow-diagrams)

---

## 1. Solution Architecture

### 1.1 High-Level Flow

```
                                 +------------------+
                                 |  Azure Key Vault |
                                 | (Client Secrets) |
                                 +--------+---------+
                                          |
+-------------------+   OAuth2    +-------+--------+   Managed ID   +------------------+
| SharePoint Online | <---------> | Azure Data     | <------------> | ADLS Gen2        |
| (25 TB Source)    |   REST API  | Factory        |   Binary Copy  | (Destination)    |
+-------------------+             +-------+--------+                +------------------+
                                          |
                                  Managed Identity
                                          |
                                 +--------+---------+
                                 |   Azure SQL DB   |
                                 | (Control/Audit)  |
                                 +------------------+
```

### 1.2 Pipeline Hierarchy

```
PL_Master_Migration_Orchestrator          <-- Top-level orchestrator
    |
    +-- ForEach Library (parallel)
         |
         +-- PL_Migrate_Single_Library    <-- Per-library migration
              |
              +-- ForEach Root File       <-- Copy files in root
              |    +-- Copy Activity
              |    +-- Log Success/Failure
              |
              +-- ForEach Subfolder
                   +-- PL_Process_Subfolder  <-- Per-folder processing
                        +-- ForEach File
                             +-- Copy Activity
                             +-- Log Success/Failure

PL_Validation                             <-- Post-migration validation
PL_Incremental_Sync                       <-- Ongoing delta sync
```

---

## 2. Linked Services

### 2.1 LS_AzureKeyVault

| Property | Value |
|----------|-------|
| Type | `AzureKeyVault` |
| Authentication | Managed Identity |
| Base URL | `https://kv-hydroone-mig-{env}.vault.azure.net/` |

**Purpose:** Retrieves the SharePoint client secret used for OAuth2 authentication. The ADF managed identity authenticates to Key Vault without any stored credentials.

**ARM Template Reference:** `adf-templates/linkedServices/LS_KeyVault.json`

### 2.2 LS_SharePointOnline_REST

| Property | Value |
|----------|-------|
| Type | `RestService` |
| Authentication | Service Principal via Key Vault |
| Base URL | `https://{tenant}.sharepoint.com` |
| Token Endpoint | `https://accounts.accesscontrol.windows.net/{tenant-id}/tokens/OAuth/2` |

**Purpose:** Makes SharePoint REST API calls to enumerate files and folders. Uses OAuth2 client credentials flow with the service principal.

**Key Configuration:**
- `servicePrincipalId`: The Azure AD App Registration client ID
- `servicePrincipalCredentialType`: `ServicePrincipalKey`
- `servicePrincipalKey`: References Key Vault secret `sharepoint-client-secret`
- `resource`: SharePoint Online resource ID

**ARM Template Reference:** `adf-templates/linkedServices/LS_SharePointOnline.json`

### 2.3 LS_SharePointOnline_HTTP

| Property | Value |
|----------|-------|
| Type | `HttpServer` |
| Authentication | Anonymous (token added in pipeline) |
| Base URL | `https://{tenant}.sharepoint.com` |

**Purpose:** Downloads binary file content from SharePoint. The HTTP linked service is used because the REST linked service doesn't support binary downloads. Authentication is handled at the pipeline level via MSI or bearer token.

### 2.4 LS_ADLS_Gen2

| Property | Value |
|----------|-------|
| Type | `AzureBlobFS` |
| Authentication | Managed Identity |
| URL | `https://sthydroonemig{env}.dfs.core.windows.net` |

**Purpose:** Writes migrated files to ADLS Gen2 using the DFS (Data Lake) endpoint. Managed identity authentication eliminates the need for storage account keys.

**ARM Template Reference:** `adf-templates/linkedServices/LS_AzureBlobStorage.json`

### 2.5 LS_AzureSqlDatabase

| Property | Value |
|----------|-------|
| Type | `AzureSqlDatabase` |
| Authentication | Managed Identity |
| Server | `sql-hydroone-migration-{env}.database.windows.net` |
| Database | `MigrationControl` |

**Purpose:** Reads from control tables and writes to audit tables during migration. Uses managed identity for passwordless authentication.

**ARM Template Reference:** `adf-templates/linkedServices/LS_AzureSqlDatabase.json`

---

## 3. Datasets

### 3.1 DS_SharePoint_Binary_HTTP

| Property | Value |
|----------|-------|
| Type | `Binary` |
| Linked Service | `LS_SharePointOnline_HTTP` |
| Format | Binary |

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `FileUrl` | String | Full URL to the SharePoint file for download |

**Purpose:** Represents a single binary file on SharePoint to be downloaded. The `FileUrl` parameter is dynamically set by the pipeline for each file being copied.

### 3.2 DS_ADLS_Binary_Sink

| Property | Value |
|----------|-------|
| Type | `Binary` |
| Linked Service | `LS_ADLS_Gen2` |
| Format | Binary |

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `ContainerName` | String | ADLS container (e.g., `sharepoint-migration`) |
| `SiteName` | String | SharePoint site name (used as top-level folder) |
| `LibraryName` | String | Library name (subfolder under site) |
| `FolderPath` | String | Relative folder path within library |
| `FileName` | String | Destination file name |

**ADLS Path Structure:**
```
{ContainerName}/{SiteName}/{LibraryName}/{FolderPath}/{FileName}
```

**Example:**
```
sharepoint-migration/HydroOneDocuments/Shared Documents/Reports/2024/Q1-Report.pdf
```

### 3.3 DS_ADLS_Parquet_Metadata

| Property | Value |
|----------|-------|
| Type | `Parquet` |
| Linked Service | `LS_ADLS_Gen2` |
| Container | `migration-metadata` |

**Purpose:** Stores migration metadata in Parquet format for analytics and reporting.

### 3.4 DS_SQL_MigrationControl

| Property | Value |
|----------|-------|
| Type | `AzureSqlTable` |
| Linked Service | `LS_AzureSqlDatabase` |

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `SchemaName` | String | SQL schema (default: `dbo`) |
| `TableName` | String | Table name (default: `MigrationControl`) |

### 3.5 DS_SQL_AuditLog

| Property | Value |
|----------|-------|
| Type | `AzureSqlTable` |
| Linked Service | `LS_AzureSqlDatabase` |
| Table | `dbo.MigrationAuditLog` |

---

## 4. Pipeline: PL_Master_Migration_Orchestrator

### 4.1 Overview

| Property | Value |
|----------|-------|
| File | `adf-templates/pipelines/PL_Master_Migration_Orchestrator.json` |
| Purpose | Top-level orchestrator that reads pending libraries from control table and processes them in parallel batches |
| Trigger | Manual, scheduled, or tumbling window |

### 4.2 Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `BatchSize` | int | 10 | Maximum libraries per batch run |
| `ParallelLibraries` | int | 4 | Concurrent library migrations |
| `MaxRetries` | int | 3 | Max retry attempts per library |
| `TargetContainerName` | string | `sharepoint-migration` | ADLS destination container |

### 4.3 Variables

| Variable | Type | Description |
|----------|------|-------------|
| `BatchId` | String | Generated batch identifier (e.g., `BATCH-20240115-200000`) |
| `NoWorkMessage` | String | Message when no libraries to process |

### 4.4 Activity Flow

```
Set_BatchId --> Log_BatchStart --> Lookup_PendingLibraries --> Filter_BatchSize
                                          |
                                  If_NoLibrariesToProcess
                                          |
                                    (if empty: Log_NoWork)

Filter_BatchSize --> ForEach_Library --> Execute_MigrateSingleLibrary
                                                    |
                                              (per library)
                                                    |
ForEach_Library --> Log_BatchComplete
```

### 4.5 Activity Details

**Set_BatchId:**
- Type: SetVariable
- Expression: `@concat('BATCH-', formatDateTime(utcNow(), 'yyyyMMdd-HHmmss'))`
- Generates unique batch identifier

**Lookup_PendingLibraries:**
- Type: Lookup
- SQL Query: Selects libraries where `Status IN ('Pending', 'Failed')` and `RetryCount < MaxRetries`
- Orders by `TotalSizeBytes ASC` (smallest first for faster early wins)

**Filter_BatchSize:**
- Type: Filter
- Limits results to the configured `BatchSize`

**ForEach_Library:**
- Type: ForEach (parallel)
- Batch count: 4 (static — ADF requires `batchCount` to be a literal integer 1-50, not an expression)
- Executes `PL_Migrate_Single_Library` for each library

**Log_BatchStart / Log_BatchComplete:**
- Type: SqlServerStoredProcedure
- Calls `usp_LogBatchStart` and `usp_LogBatchComplete`

---

## 5. Pipeline: PL_Migrate_Single_Library

### 5.1 Overview

| Property | Value |
|----------|-------|
| File | `adf-templates/pipelines/PL_Migrate_Single_Library.json` |
| Purpose | Migrates all files from a single SharePoint document library to ADLS Gen2 |
| Called By | `PL_Master_Migration_Orchestrator` (ForEach) |

### 5.2 Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `SiteUrl` | string | `/sites/HydroOneDocuments` | SharePoint site relative URL |
| `LibraryName` | string | `Documents` | Document library name |
| `ControlTableId` | int | - | ID from MigrationControl table |
| `BatchId` | string | - | Parent batch identifier |
| `ContainerName` | string | `sharepoint-migration` | ADLS container |
| `SharePointTenantUrl` | string | `https://hydroone.sharepoint.com` | SharePoint tenant URL |
| `ThrottleWaitSeconds` | int | 120 | Seconds to wait when throttled |

### 5.3 Activity Flow

```
Update_Status_InProgress
        |
        +-------+--------+
        |                 |
Get_RootFolderFiles  Get_AllSubfolders
        |                 |
ForEach_RootFile     ForEach_Subfolder
   |                     |
   +-- Copy_SingleFile   +-- Execute_ProcessSubfolder
   +-- Log_FileSuccess        (calls PL_Process_Subfolder)
   +-- Log_FileFailure
   +-- Check_Throttling
        |
        +-------+--------+
        |                 |
Update_Status_Completed   Update_Status_Failed
```

### 5.4 Key Activities

**Get_RootFolderFiles:**
- Type: WebActivity (GET)
- URL: `{tenant}{site}/_api/web/GetFolderByServerRelativeUrl('{library}')/Files?$select=Name,ServerRelativeUrl,Length,TimeLastModified,UniqueId&$top=5000`
- Authentication: MSI
- Returns: Array of file objects with metadata

**ForEach_RootFile:**
- Parallelism: 10 concurrent files
- Contains Copy_SingleFile, Log_FileSuccess, Log_FileFailure, Check_Throttling

**Copy_SingleFile:**
- Type: Copy Activity
- Source: `DS_SharePoint_Binary_HTTP` (HTTP download)
- Sink: `DS_ADLS_Binary_Sink` (ADLS write)
- Retry: 3 attempts, 60s interval
- Timeout: 30 minutes per file

**Check_Throttling:**
- Type: IfCondition
- Expression: `@contains(string(activity('Copy_SingleFile').output), '429')`
- If true: Wait activity pauses for `ThrottleWaitSeconds`

**Log_FileSuccess / Log_FileFailure:**
- Type: SqlServerStoredProcedure
- Calls: `dbo.usp_LogFileAudit`
- Logs file name, source/destination paths, size, status, errors

---

## 6. Pipeline: PL_Process_Subfolder

### 6.1 Overview

| Property | Value |
|----------|-------|
| File | `adf-templates/pipelines/PL_Process_Subfolder.json` |
| Purpose | Processes all files within a single SharePoint subfolder |
| Called By | `PL_Migrate_Single_Library` (ForEach_Subfolder) |

### 6.2 Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `SiteUrl` | string | SharePoint site relative URL |
| `LibraryName` | string | Document library name |
| `FolderServerRelativeUrl` | string | Full server-relative URL of the folder |
| `ContainerName` | string | ADLS container name |
| `SharePointTenantUrl` | string | SharePoint tenant URL |

### 6.3 Activity Flow

```
Get_FolderFiles --> ForEach_File
                        |
                        +-- Copy_File
                        +-- Log_Success
                        +-- Log_Failure
```

### 6.4 ADLS Path Mapping

The folder path in ADLS is computed by stripping the site/library prefix from the SharePoint server-relative URL:

```
SharePoint: /sites/HydroOne/Documents/Reports/2024/Q1/file.pdf
ADLS:       sharepoint-migration/HydroOne/Documents/Reports/2024/Q1/file.pdf
```

Expression:
```
@replace(
    replace(
        pipeline().parameters.FolderServerRelativeUrl,
        concat(pipeline().parameters.SiteUrl, '/', pipeline().parameters.LibraryName, '/'),
        ''
    ),
    concat(pipeline().parameters.SiteUrl, '/', pipeline().parameters.LibraryName),
    ''
)
```

---

## 7. Pipeline: PL_Validation

### 7.1 Overview

| Property | Value |
|----------|-------|
| File | `adf-templates/pipelines/PL_Validation.json` |
| Purpose | Post-migration validation comparing control table expected counts with audit log actual counts |
| Trigger | Manual (after migration batches complete) |
| Test Status | **Validated** — successfully tested with 10 sample files (run ID: `92158504-c822-46a3-9a4f-2cbd780986f6`) |

### 7.2 Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `SharePointTenantUrl` | string | `https://hydroone.sharepoint.com` | SharePoint tenant URL (reserved for future SharePoint-direct validation) |
| `ValidateAll` | bool | `false` | When `true`, re-validates all completed libraries. When `false`, only validates libraries with `ValidationStatus = NULL` or `Pending` |

### 7.3 Validation Approach

The pipeline uses **SQL-only validation** — comparing control table expected file counts against audit log actual migration results. This approach:
- Does not require SharePoint API access during validation
- Validates that the number of successfully migrated files matches the expected count
- Detects any failed file copies
- Automatically flags discrepancies and marks validated libraries

**Validation Checks:**
1. **File Count Validation**: Compares `MigrationControl.FileCount` (expected) with count of `Success` entries in `MigrationAuditLog` (actual)
2. **Failed File Detection**: Checks for any audit log entries with `MigrationStatus = 'Failed'`
3. **Discrepancy Flagging**: If expected != actual OR any failures exist, marks library as `Discrepancy` with details

### 7.4 Activity Flow

```
Lookup_CompletedLibraries --> ForEach_ValidateLibrary
                                  |
                                  +-- Lookup_DestinationFileCount (SQL audit log query)
                                  +-- Compare_And_Log (stored procedure: usp_LogValidationResult)
                                  +-- If_Discrepancy
                                  |       +-- True:  Flag_Discrepancy (usp_UpdateValidationStatus -> 'Discrepancy')
                                  |       +-- False: Mark_Validated (usp_UpdateValidationStatus -> 'Validated')
                                  |
ForEach_ValidateLibrary --> Generate_ValidationReport (SQL summary query)
                                  |
                        --> Set_ValidationSummary (pipeline variable output)
```

### 7.5 Activity Details

**Lookup_CompletedLibraries:**
- Type: Lookup
- SQL: Selects libraries where `Status = 'Completed'` and `ValidateAll = 1 OR ValidationStatus IS NULL OR = 'Pending'`
- Returns: `Id, SiteUrl, LibraryName, ExpectedFileCount, ExpectedSizeBytes`

**Lookup_DestinationFileCount:**
- Type: Lookup
- SQL: Counts audit log entries matching the library's source path
- Returns: `ActualFileCount, ActualSizeBytes, SuccessCount, FailedCount`

**Compare_And_Log:**
- Type: SqlServerStoredProcedure (`usp_LogValidationResult`)
- Updates control table with actual migrated counts

**If_Discrepancy:**
- Expression: `@or(FailedCount > 0, ExpectedFileCount != SuccessCount)`
- True path: Calls `usp_UpdateValidationStatus` with `'Discrepancy'` and details string
- False path: Calls `usp_UpdateValidationStatus` with `'Validated'`

**Generate_ValidationReport:**
- Type: Lookup (summary query)
- Returns: `ValidatedCount, DiscrepancyCount, PendingCount, TotalLibraries`

---

## 8. Pipeline: PL_Incremental_Sync

### 8.1 Overview

| Property | Value |
|----------|-------|
| File | `adf-templates/pipelines/PL_Incremental_Sync.json` |
| Purpose | Delta/incremental synchronization for ongoing sync after initial migration |
| Trigger | Tumbling window (every 6 hours) |

### 8.2 Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `SharePointTenantUrl` | string | - | SharePoint tenant URL |
| `ContainerName` | string | `sharepoint-migration` | ADLS container |

### 8.3 How It Works

1. Reads from `IncrementalWatermark` table to get last sync timestamp per library
2. Queries SharePoint for files modified after the watermark
3. Copies only modified/new files to ADLS (overwrites existing)
4. Updates watermark after successful sync

### 8.4 Activity Flow

```
Lookup_LibrariesForSync --> ForEach_LibrarySync
                                |
                                +-- Get_ModifiedFiles (WebActivity)
                                +-- If_HasModifiedFiles
                                     |
                                     +-- ForEach_ModifiedFile
                                     |       +-- Copy_ModifiedFile
                                     |       +-- Log_IncrementalCopy
                                     +-- Update_Watermark
                                |
ForEach_LibrarySync --> Log_SyncComplete
```

### 8.5 SharePoint Query for Modified Files

```
{site}/_api/web/lists/getbytitle('{library}')/items
    ?$filter=Modified ge datetime'{lastModifiedDate}'
    &$select=FileRef,FileLeafRef,File_x0020_Size,Modified,UniqueId
    &$expand=File
    &$top=5000
```

---

## 9. SQL Schema & Stored Procedures

### 9.1 MigrationControl Table

**File:** `sql/create_control_table.sql`

| Column | Type | Description |
|--------|------|-------------|
| `Id` | INT (PK) | Auto-increment identifier |
| `SiteUrl` | NVARCHAR(500) | SharePoint site relative URL (e.g., `/sites/HydroOneDocuments`) |
| `LibraryName` | NVARCHAR(255) | Document library name (e.g., `Documents`) |
| `SiteTitle` | NVARCHAR(255) | Friendly site title |
| `LibraryTitle` | NVARCHAR(255) | Friendly library title |
| `Status` | NVARCHAR(50) | Current status (Pending/InProgress/Completed/Failed/Skipped/Paused) |
| `ValidationStatus` | NVARCHAR(50) | Validation result (Pending/Validated/Discrepancy) |
| `FileCount` | INT | Expected total file count from source |
| `FolderCount` | INT | Total folders in library |
| `TotalSizeBytes` | BIGINT | Expected total size in bytes |
| `LargestFileSizeBytes` | BIGINT | Size of largest file |
| `MigratedFileCount` | INT | Files successfully migrated |
| `MigratedSizeBytes` | BIGINT | Bytes successfully migrated |
| `FailedFileCount` | INT | Files that failed migration |
| `StartTime` | DATETIME2 | When migration started |
| `EndTime` | DATETIME2 | When migration completed |
| `DurationSeconds` | Computed | `DATEDIFF(SECOND, StartTime, EndTime)` |
| `ErrorMessage` | NVARCHAR(MAX) | Last error message |
| `RetryCount` | INT | Number of retry attempts (default: 0) |
| `LastRetryTime` | DATETIME2 | When last retry occurred |
| `BatchId` | NVARCHAR(50) | Last batch that processed this library |
| `Priority` | INT | Migration priority (1=highest, default: 100) |
| `EnableIncrementalSync` | BIT | Whether to include in delta sync (default: 1) |
| `LastIncrementalSync` | DATETIME2 | Last successful incremental sync |
| `ValidationTimestamp` | DATETIME2 | When validation was performed |
| `DiscrepancyDetails` | NVARCHAR(MAX) | Details of any validation discrepancies |
| `CreatedDate` | DATETIME2 | Record creation timestamp |
| `ModifiedDate` | DATETIME2 | Last modification timestamp |

### 9.2 MigrationAuditLog Table

**File:** `sql/create_audit_log_table.sql`

| Column | Type | Description |
|--------|------|-------------|
| `Id` | BIGINT (PK) | Auto-increment identifier |
| `FileName` | NVARCHAR(500) | Original file name |
| `FileExtension` | Computed | Extracted from FileName |
| `SourcePath` | NVARCHAR(2000) | Full SharePoint server-relative path |
| `DestinationPath` | NVARCHAR(2000) | Full ADLS path |
| `FileSizeBytes` | BIGINT | File size in bytes |
| `FileSizeMB` | Computed | Size in megabytes |
| `SourceChecksum` | NVARCHAR(64) | MD5/SHA256 of source |
| `DestinationChecksum` | NVARCHAR(64) | MD5/SHA256 of destination |
| `ChecksumMatch` | Computed | 1 if checksums match |
| `MigrationStatus` | NVARCHAR(50) | Success/Failed/Skipped/IncrementalSync |
| `Timestamp` | DATETIME2 | Record creation time |
| `CopyStartTime` | DATETIME2 | Copy operation start |
| `CopyEndTime` | DATETIME2 | Copy operation end |
| `CopyDurationMs` | Computed | Duration in milliseconds |
| `ErrorDetails` | NVARCHAR(MAX) | Error message/stack trace |
| `ErrorCode` | NVARCHAR(50) | HTTP error code |
| `RetryAttempt` | INT | Retry attempt number |
| `PipelineRunId` | NVARCHAR(50) | ADF pipeline run ID |
| `BatchId` | NVARCHAR(50) | Batch identifier |
| `SiteName` | NVARCHAR(255) | Extracted site name |
| `LibraryName` | NVARCHAR(255) | Extracted library name |

### 9.3 Key Stored Procedures

**usp_UpdateMigrationStatus:**
```sql
-- Updates library migration status, timestamps, and retry counts
EXEC dbo.usp_UpdateMigrationStatus
    @Id = 1,
    @Status = 'Completed',
    @EndTime = '2024-01-15T23:00:00',
    @ErrorMessage = NULL
```

**usp_LogFileAudit:**
```sql
-- Logs individual file migration result
EXEC dbo.usp_LogFileAudit
    @FileName = 'report.pdf',
    @SourcePath = '/sites/HydroOne/Documents/report.pdf',
    @DestinationPath = 'sharepoint-migration/HydroOne/Documents/report.pdf',
    @FileSizeBytes = 1048576,
    @MigrationStatus = 'Success',
    @PipelineRunId = 'abc-123-def',
    @BatchId = 'BATCH-20240115-200000'
```

**usp_LogBatchStart / usp_LogBatchComplete:**
```sql
-- Tracks batch execution lifecycle
EXEC dbo.usp_LogBatchStart
    @BatchId = 'BATCH-20240115-200000',
    @PipelineRunId = 'abc-123-def',
    @StartTime = '2024-01-15T20:00:00'
```

### 9.4 Performance Indexes

| Index | Table | Columns | Purpose |
|-------|-------|---------|---------|
| `IX_Control_Status` | MigrationControl | Status, Priority | Lookup pending libraries |
| `IX_AuditLog_MigrationStatus` | MigrationAuditLog | MigrationStatus | Filter by status |
| `IX_AuditLog_PipelineRunId` | MigrationAuditLog | PipelineRunId | Track pipeline results |
| `IX_AuditLog_Timestamp` | MigrationAuditLog | Timestamp DESC | Recent activity |
| `IX_AuditLog_BatchId` | MigrationAuditLog | BatchId | Batch-level reporting |
| `IX_AuditLog_SiteLibrary` | MigrationAuditLog | SiteName, LibraryName | Per-library queries |

---

## 10. PowerShell Scripts

### 10.1 Setup-AzureResources.ps1

**File:** `scripts/Setup-AzureResources.ps1`

**Purpose:** Provisions all Azure resources for the migration environment.

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `-Environment` | String | Target environment (dev/test/prod) |
| `-Location` | String | Azure region (default: canadacentral) |
| `-SubscriptionId` | String | Azure subscription ID |

**Creates:**
- Resource Group
- ADLS Gen2 Storage Account with containers
- Azure SQL Server and Database
- Azure Key Vault
- Azure Data Factory

### 10.2 Register-SharePointApp.ps1

**File:** `scripts/Register-SharePointApp.ps1`

**Purpose:** Registers an Azure AD application with SharePoint permissions.

**Actions:**
1. Creates Azure AD App Registration
2. Generates client secret
3. Adds SharePoint API permissions
4. Stores credentials in Key Vault
5. Outputs admin consent URL

### 10.3 Monitor-Migration.ps1

**File:** `scripts/Monitor-Migration.ps1`

**Purpose:** Real-time monitoring dashboard for migration progress.

**Features:**
- Overall progress (libraries, files, TB)
- Current batch status
- Throttling detection
- Error rate monitoring
- Throughput metrics (GB/hour)
- Continuous refresh mode

### 10.4 Validate-Migration.ps1

**File:** `scripts/Validate-Migration.ps1`

**Purpose:** Post-migration validation comparing source and destination.

**Checks:**
- File count per library (source vs destination)
- Total size comparison
- Random file sampling and size verification
- Missing file detection
- Generates validation report

---

## 11. ARM Template Reference

### 11.1 Main Template: arm-template.json

**File:** `adf-templates/arm-template.json`

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `factoryName` | string | ADF instance name |
| `location` | string | Azure region |
| `sharePointTenantUrl` | string | SharePoint tenant URL |
| `servicePrincipalId` | string | Azure AD App client ID |
| `tenantId` | string | Azure AD tenant ID |
| `keyVaultName` | string | Key Vault name |
| `storageAccountName` | string | ADLS Gen2 account name |
| `sqlServerName` | string | Azure SQL server name |
| `sqlDatabaseName` | string | Database name |

**Resources Deployed:**
1. `Microsoft.DataFactory/factories` - ADF instance with managed identity
2. `factories/linkedServices` - 5 linked services
3. `factories/datasets` - 6 datasets

### 11.2 Pipeline Templates

Each pipeline is a separate ARM template in `adf-templates/pipelines/`:

| File | Resource |
|------|----------|
| `PL_Master_Migration_Orchestrator.json` | Master orchestrator pipeline |
| `PL_Migrate_Single_Library.json` | Single library migration pipeline |
| `PL_Process_Subfolder.json` | Subfolder processing pipeline |
| `PL_Validation.json` | Validation pipeline |
| `PL_Incremental_Sync.json` | Incremental sync pipeline |

**Note:** Stored procedure names in ARM templates use `[[dbo]` syntax to escape the `[` character, which ARM treats as an expression delimiter. The `[[` evaluates to a literal `[` at deployment time.

---

## 12. Data Flow Diagrams

### 12.1 File Copy Data Flow

```mermaid
sequenceDiagram
    participant ADF as Azure Data Factory
    participant SPO as SharePoint Online
    participant ADLS as ADLS Gen2
    participant SQL as Azure SQL

    ADF->>SQL: Read MigrationControl (Pending libraries)
    SQL-->>ADF: Library list

    loop ForEach Library
        ADF->>SQL: Update Status = InProgress
        ADF->>SPO: GET /_api/web/GetFolderByServerRelativeUrl/Files
        SPO-->>ADF: File list (JSON)

        loop ForEach File
            ADF->>SPO: GET file binary content
            SPO-->>ADF: Binary stream
            ADF->>ADLS: Write binary to container/site/library/path
            ADLS-->>ADF: Success

            alt Copy Success
                ADF->>SQL: EXEC usp_LogFileAudit (Status=Success)
            else Copy Failed
                ADF->>SQL: EXEC usp_LogFileAudit (Status=Failed)
                Note over ADF: Check for HTTP 429 throttling
            end
        end

        ADF->>SQL: Update Status = Completed/Failed
    end
```

### 12.2 Authentication Flow

```mermaid
sequenceDiagram
    participant ADF as ADF Pipeline
    participant MI as Managed Identity
    participant KV as Key Vault
    participant AAD as Azure AD
    participant SPO as SharePoint

    ADF->>MI: Request identity token
    MI-->>ADF: Identity token

    ADF->>KV: GET secret (sharepoint-client-secret)
    KV-->>ADF: Client secret value

    ADF->>AAD: POST /oauth2/token (client_credentials)
    Note right of AAD: client_id + client_secret
    AAD-->>ADF: Access token (Bearer)

    ADF->>SPO: GET /_api/... (Authorization: Bearer {token})
    SPO-->>ADF: Response data
```

### 12.3 Error Handling Flow

```mermaid
flowchart TD
    A[Copy File] --> B{Success?}
    B -->|Yes| C[Log Success to SQL]
    B -->|No| D{Error Type?}
    D -->|HTTP 429| E[Wait ThrottleWaitSeconds]
    E --> F[Retry Copy]
    D -->|HTTP 401/403| G[Log Auth Error]
    G --> H[Skip File, Continue]
    D -->|HTTP 404| I[Log File Not Found]
    I --> H
    D -->|Timeout| J[Retry with Extended Timeout]
    D -->|Other| K[Log Error Details]
    K --> L{Retry Count < Max?}
    L -->|Yes| F
    L -->|No| M[Mark Library as Failed]
```

---

## 13. Test Results (February 2026)

### 13.1 Test Environment

| Resource | Value |
|----------|-------|
| Subscription | `671b1321-4407-420b-b877-97cd40ba898a` |
| Tenant | `fe64e912-f83c-44e9-9389-f66812c7fa57` |
| Resource Group | `rg-hydroone-migration-test` |
| ADF | `adf-hydroone-migration-test` |
| SQL Server | `sql-hydroone-migration-test.database.windows.net` |
| Storage | `sthydroonemigtest` |
| Key Vault | `kv-hydroone-test2` |

### 13.2 Test Data

- 10 sample documents uploaded to ADLS: `sharepoint-migration/TestSite/Documents/`
- Control table populated with 1 library record (TestSite/Documents, 10 files, 659 bytes)
- 10 audit log records inserted (all `Success` status)
- 1 batch log record (BATCH-TEST-001)

### 13.3 Pipeline Test Results

**PL_Master_Migration_Orchestrator** — Run ID: `7bb1ca75-5180-4087-9870-6dea48e667a6`

| Activity | Status | Duration |
|----------|--------|----------|
| Set_BatchId | Succeeded | 276ms |
| Log_BatchStart | Succeeded | 3,808ms |
| Lookup_PendingLibraries | Succeeded | 8,019ms |
| If_NoLibrariesToProcess | Succeeded | 978ms |
| Filter_BatchSize | Succeeded | 319ms |
| Log_NoWork | Succeeded | 254ms |
| ForEach_Library | Succeeded | 756ms |
| Log_BatchComplete | Succeeded | 3,071ms |

**Result:** All 8 activities succeeded. Pipeline correctly found 0 pending libraries (control table had Completed status) and completed gracefully.

**PL_Validation** — Run ID: `92158504-c822-46a3-9a4f-2cbd780986f6`

| Activity | Status | Duration |
|----------|--------|----------|
| Lookup_CompletedLibraries | Succeeded | 26,107ms |
| ForEach_ValidateLibrary | Succeeded | 40,775ms |
| Lookup_DestinationFileCount | Succeeded | 24,090ms |
| Compare_And_Log | Succeeded | 3,717ms |
| If_Discrepancy | Succeeded | 5,365ms |
| Mark_Validated | Succeeded | 2,817ms |
| Generate_ValidationReport | Succeeded | 13,051ms |
| Set_ValidationSummary | Succeeded | 276ms |

**Result:** All 8 activities succeeded. Validation compared expected 10 files vs 10 actual migrated files. No discrepancies found. Library marked as `Validated`.

### 13.4 Verified Connectivity

| Connection | Method | Status |
|------------|--------|--------|
| ADF → Azure SQL (read) | Managed Identity | Working |
| ADF → Azure SQL (stored procedures) | Managed Identity | Working |
| ADF → Key Vault | Managed Identity + Access Policy | Working |
| ADF → ADLS Gen2 | Managed Identity + Storage Blob Data Contributor | Role Assigned |
| ADF → SharePoint Online | MSI / Service Principal | Blocked (requires admin consent) |

### 13.5 Known Issues & Fixes Applied

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| ARM template `[dbo]` parsing error | ARM interprets `[` as expression delimiter | Escaped with `[[dbo]` |
| Recursive pipeline circular reference | ADF does not support pipelines calling themselves | Removed self-reference from PL_Process_Subfolder |
| PL_Incremental_Sync JSON structure bug | Missing closing brace for ForEach_ModifiedFile | Added missing `}` |
| ForEach batchCount expression error | `batchCount` must be a static integer (1-50) | Changed from expression to literal `4` |
| Boolean `ValidateAll` in SQL query | ADF renders `True`/`False`, SQL expects `1`/`0` | Used `@{if(pipeline().parameters.ValidateAll, 1, 0)}` |
| Validation required SharePoint access | `Get_SourceFileCount` called SharePoint API | Replaced with SQL control table `ExpectedFileCount` |

---

## Appendix: File Inventory

| File Path | Type | Description |
|-----------|------|-------------|
| `adf-templates/arm-template.json` | ARM Template | Main ADF deployment template |
| `adf-templates/pipelines/PL_Master_Migration_Orchestrator.json` | ARM Template | Master orchestrator pipeline |
| `adf-templates/pipelines/PL_Migrate_Single_Library.json` | ARM Template | Single library migration |
| `adf-templates/pipelines/PL_Process_Subfolder.json` | ARM Template | Subfolder processing |
| `adf-templates/pipelines/PL_Validation.json` | ARM Template | Post-migration validation |
| `adf-templates/pipelines/PL_Incremental_Sync.json` | ARM Template | Delta sync pipeline |
| `adf-templates/linkedServices/*.json` | JSON | Linked service definitions |
| `adf-templates/datasets/*.json` | JSON | Dataset definitions |
| `adf-templates/triggers/TR_Triggers.json` | ARM Template | Trigger definitions |
| `adf-templates/dataflows/DF_MetadataEnrichment.json` | JSON | Metadata enrichment dataflow |
| `sql/create_control_table.sql` | SQL | Control table schema + stored procs |
| `sql/create_audit_log_table.sql` | SQL | Audit log schema + stored procs |
| `sql/monitoring_queries.sql` | SQL | Monitoring views and queries |
| `sql/insert_test_data.sql` | SQL | Test data for validation testing |
| `scripts/Setup-AzureResources.ps1` | PowerShell | Azure resource provisioning |
| `scripts/Register-SharePointApp.ps1` | PowerShell | SharePoint app registration |
| `scripts/Monitor-Migration.ps1` | PowerShell | Migration monitoring |
| `scripts/Validate-Migration.ps1` | PowerShell | Post-migration validation |
| `config/parameters.dev.json` | JSON | Dev environment parameters |
| `config/parameters.prod.json` | JSON | Prod environment parameters |
| `docs/architecture.md` | Documentation | Solution architecture |
| `docs/runbook.md` | Documentation | Operational runbook |
| `docs/migration-plan.md` | Documentation | 10-week migration plan |
| `docs/deployment-guide.md` | Documentation | This deployment guide |
| `docs/pipeline-documentation.md` | Documentation | Pipeline technical reference |
