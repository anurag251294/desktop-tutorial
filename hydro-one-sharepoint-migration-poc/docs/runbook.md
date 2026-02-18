# Hydro One SharePoint Migration - Operational Runbook

## Table of Contents
1. [Critical Prerequisites for Hydro One](#critical-prerequisites-for-hydro-one)
2. [Pre-Migration](#pre-migration)
3. [Migration Execution](#migration-execution)
4. [Throttling Management](#throttling-management)
5. [Error Handling & Recovery](#error-handling--recovery)
6. [Post-Migration](#post-migration)
7. [Rollback Plan](#rollback-plan)

---

## Environment Details

| Resource | Name | Region |
|----------|------|--------|
| Resource Group | rg-hydroone-migration-test | Canada Central |
| SharePoint Tenant | https://m365x52073746.sharepoint.com | - |
| Azure Data Factory | adf-hydroone-migration-test | Canada Central |
| Storage Account (ADLS Gen2) | sthydroonemigtest | Canada Central |
| SQL Server | sql-hydroone-migration-test | Canada Central |
| Key Vault | kv-hydroone-test2 | Canada Central |

---

## Critical Prerequisites for Hydro One

> **These items MUST be completed before migration testing or execution can begin.**

### 1. Grant Admin Consent for Microsoft Graph API Permissions (BLOCKER)

A **Global Administrator** in the Azure AD tenant must grant admin consent for the registered application's **Microsoft Graph API** permissions. Without this, the Azure Data Factory pipelines **cannot access SharePoint Online** and the entire migration is blocked.

> **IMPORTANT:** The migration uses the **Microsoft Graph API** -- NOT the SharePoint REST API. App-only tokens with SharePoint REST API will return "Unsupported app only token" errors. All file access must go through Graph API endpoints.

**Steps for Global Admin:**
1. Sign in to [Azure Portal](https://portal.azure.com) as Global Administrator
2. Navigate to **Azure Active Directory** > **App registrations**
3. Select the migration app (e.g., `HydroOne-SPO-Migration`)
4. Click **API permissions**
5. Click **Grant admin consent**
6. Confirm by clicking **Yes**
7. Verify all permissions show green checkmark: **"Granted"**

**Required Permissions:**

| API | Permission | Type |
|-----|-----------|------|
| Microsoft Graph | Sites.Read.All | Application |
| Microsoft Graph | Files.Read.All | Application |

**Token Acquisition:**
- Token endpoint: `https://login.microsoftonline.com/{tenant-id}/oauth2/v2.0/token`
- Scope: `https://graph.microsoft.com/.default`
- Grant type: `client_credentials`
- Client ID and Client Secret stored in Key Vault

### 2. Enable Public Network Access on Azure Resources (BLOCKER)

The following resources **must** have public network access enabled (or have private endpoints configured):

- **Key Vault (`kv-hydroone-test2`):** ADF must be able to retrieve secrets (Client ID, Client Secret, Tenant ID). Enable public network access or configure a private endpoint.
- **Storage Account (`sthydroonemigtest`):** ADF must be able to write files to ADLS Gen2. Enable public network access or configure a private endpoint.
- **SQL Server (`sql-hydroone-migration-test`):** ADF must be able to read/write the control table and audit log. Enable public network access and add ADF's outbound IPs to the firewall, or configure a private endpoint.

### 3. Grant ADF Managed Identity RBAC Permissions

The ADF Managed Identity (`adf-hydroone-migration-test`) requires the following role assignments:

| Resource | Role | Purpose |
|----------|------|---------|
| Storage Account (`sthydroonemigtest`) | Storage Blob Data Contributor | Read/write files to ADLS Gen2 containers |
| Key Vault (`kv-hydroone-test2`) | Key Vault Secrets User | Retrieve Client ID, Client Secret, and Tenant ID |

**To assign roles:**
```bash
# Storage Blob Data Contributor on storage account
az role assignment create \
    --role "Storage Blob Data Contributor" \
    --assignee "<adf-managed-identity-object-id>" \
    --scope "/subscriptions/<sub-id>/resourceGroups/rg-hydroone-migration-test/providers/Microsoft.Storage/storageAccounts/sthydroonemigtest"

# Key Vault Secrets User on Key Vault
az role assignment create \
    --role "Key Vault Secrets User" \
    --assignee "<adf-managed-identity-object-id>" \
    --scope "/subscriptions/<sub-id>/resourceGroups/rg-hydroone-migration-test/providers/Microsoft.KeyVault/vaults/kv-hydroone-test2"
```

### 4. Grant ADF Managed Identity Access to SQL Database

Run this SQL command in the `MigrationControl` database:

```sql
CREATE USER [adf-hydroone-migration-test] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [adf-hydroone-migration-test];
ALTER ROLE db_datawriter ADD MEMBER [adf-hydroone-migration-test];
GRANT EXECUTE ON SCHEMA::dbo TO [adf-hydroone-migration-test];
```

### 5. Provide SharePoint Site Collection Inventory

Provide a complete list of:
- All site collection URLs to be migrated
- Document libraries within each site
- Estimated file counts and sizes per library
- Any libraries or files to exclude

---

## Pre-Migration

### Azure Prerequisites Checklist

- [ ] **Azure Subscription**
  - [ ] Subscription with sufficient quota for:
    - [ ] Storage: 30 TB capacity (25 TB + 20% overhead)
    - [ ] SQL Database: S1 or higher
    - [ ] Data Factory: Pay-as-you-go
  - [ ] Contributor access for deployment team

- [ ] **Resource Providers Registered**
  ```bash
  az provider register --namespace Microsoft.DataFactory
  az provider register --namespace Microsoft.Storage
  az provider register --namespace Microsoft.Sql
  az provider register --namespace Microsoft.KeyVault
  ```

- [ ] **Azure AD Permissions**
  - [ ] Application Administrator or Global Administrator (for app registration)
  - [ ] **CRITICAL: Global Administrator or Privileged Role Administrator** required to grant admin consent for Microsoft Graph API permissions
  - [ ] Without admin consent, the migration **cannot proceed** -- all Graph API calls will return HTTP 401/403

- [ ] **Network / Access Requirements**
  - [ ] Outbound HTTPS (443) to Microsoft Graph API (`graph.microsoft.com`)
  - [ ] Outbound HTTPS (443) to Azure AD (`login.microsoftonline.com`)
  - [ ] Outbound HTTPS (443) to Azure services
  - [ ] Key Vault public network access **enabled** (or private endpoint configured)
  - [ ] Storage account public network access **enabled** (or private endpoint configured)
  - [ ] SQL Server public network access **enabled** (or private endpoint configured)
  - [ ] ADF Managed Identity has **Storage Blob Data Contributor** on the storage account
  - [ ] ADF Managed Identity has **Key Vault Secrets User** on the Key Vault

### SharePoint Prerequisites

- [ ] **App Registration**
  - [ ] Azure AD App registered with **Microsoft Graph** permissions:
    - `Sites.Read.All` (Application) -- required to resolve sites and drives
    - `Files.Read.All` (Application) -- required to enumerate and download files
  - [ ] **Admin consent granted** for all above permissions (must show green "Granted" status)
  - [ ] Client ID stored in Key Vault (`SPO-ClientId`)
  - [ ] Client Secret stored in Key Vault (`SPO-ClientSecret`)
  - [ ] Tenant ID stored in Key Vault (`SPO-TenantId`)

- [ ] **Site Collection Inventory**
  - [ ] List of all site collections to migrate
  - [ ] Document libraries identified per site
  - [ ] Estimated file counts and sizes per library

- [ ] **Exclusions Identified**
  - [ ] System libraries excluded (Style Library, Site Assets, etc.)
  - [ ] Personal sites (OneDrive) excluded if applicable
  - [ ] Large files (>100 GB) identified for special handling

### Storage Capacity Planning

| Item | Calculation | Value |
|------|-------------|-------|
| Source Data | Actual SharePoint usage | ~25 TB |
| ADLS Capacity | Source + 20% overhead | ~30 TB |
| SQL Database | Control/audit tables | ~10 GB |
| Temporary Storage | Staging during copy | Minimal (streaming) |

**Cost Estimation (Monthly):**
- ADLS Gen2 (Hot tier): ~$500-600/month for 25 TB
- SQL Database (S1): ~$30/month
- Data Factory: ~$50-200/month (depending on activity)
- Key Vault: ~$5/month

### Network Bandwidth Estimation

| Metric | Assumption | Calculation |
|--------|------------|-------------|
| Total Data | 25 TB | |
| Available Bandwidth | 1 Gbps | Corporate network |
| Theoretical Time | 25 TB / 125 MB/s | ~55 hours |
| Throttling Factor | 50% efficiency | Due to API limits |
| Realistic Time | 55 hours * 2 | ~110 hours (5 days) |
| Safety Buffer | 2x | **10-14 days** |

### Microsoft Throttling Limit Increase Request

**Email Template to Microsoft Account Team:**

```
Subject: Microsoft Graph API Throttling Limit Increase Request - Hydro One Migration

Dear Microsoft Account Team,

We are planning a large-scale data migration from SharePoint Online to Azure Data Lake Storage Gen2 for Hydro One. We request a temporary increase in Microsoft Graph API throttling limits to facilitate this migration.

Migration Details:
- Tenant: m365x52073746.sharepoint.com
- Data Volume: ~25 TB
- Timeline: [INSERT DATES]
- Migration Tool: Azure Data Factory with Microsoft Graph API
- Service Principal App ID: [INSERT APP ID]

Current Limits We're Experiencing:
- HTTP 429 responses after ~600 requests/minute
- File download throttling during peak hours

Requested Adjustments:
1. Increase API call limit to 2,000 requests/minute (temporary)
2. Increase concurrent connection limit
3. Preferential treatment during off-peak hours (8 PM - 6 AM EST)

Migration Window:
- Start Date: [INSERT]
- End Date: [INSERT]
- Primary Migration Hours: 8 PM - 6 AM EST (weekdays), All day (weekends)

We can provide additional details about our migration architecture and approach if needed.

Best regards,
[Your Name]
[Microsoft / Hydro One Contact Information]
```

---

## Migration Execution

### Pipeline Architecture (Graph API Flow)

The migration pipelines follow this flow:

1. **Token Acquisition:** ADF retrieves Client ID, Client Secret, and Tenant ID from Key Vault (`kv-hydroone-test2`), then acquires an OAuth2 app-only token from Azure AD with scope `https://graph.microsoft.com/.default`.

2. **Drive Resolution:** Using the token, ADF calls the Graph API to resolve the SharePoint site and document library to a Drive ID:
   - `GET https://graph.microsoft.com/v1.0/sites/{host}:{site-path}` to get the Site ID
   - `GET https://graph.microsoft.com/v1.0/sites/{site-id}/drives` to get the Drive ID for the library

3. **File Enumeration:** ADF uses the Graph delta query to enumerate ALL files at ALL folder depths in a single paginated call:
   - `GET https://graph.microsoft.com/v1.0/drives/{drive-id}/root/delta?$top=200` returns files from all levels
   - Pagination follows `@odata.nextLink` in an Until loop with configurable throttle delay
   - `parentReference.path` on each item is used to reconstruct ADLS folder paths

4. **File Copy:** ADF downloads each file using the Graph `/content` endpoint with a Bearer token in the Authorization header:
   - `GET https://graph.microsoft.com/v1.0/drives/{drive-id}/items/{item-id}/content`
   - The file is streamed directly to ADLS Gen2 (`sthydroonemigtest`) via a Copy activity

5. **Subfolder Processing:** With the delta-based approach, `PL_Process_Subfolder` is no longer called from `PL_Migrate_Single_Library`. The delta query returns all files at all depths, eliminating the need for separate subfolder processing. `PL_Process_Subfolder` remains available as a standalone utility.

6. **Token Refresh:** If the pipeline runs for more than 45 minutes, the OAuth2 token is automatically refreshed to prevent 401 errors on long-running libraries.

7. **DeltaLink Storage:** After processing all delta pages, the `@odata.deltaLink` URL is stored in the IncrementalWatermark SQL table for use by subsequent incremental sync runs.

### Step 1: Deploy Azure Resources

```bash
# Login to Azure
az login

# Set subscription
az account set --subscription "<subscription-id>"

# Deploy resources using PowerShell script
.\scripts\Setup-AzureResources.ps1 -Environment "test" -Location "canadacentral"
```

### Step 2: Register App and Configure Key Vault

```powershell
# Register app and store credentials in Key Vault
.\scripts\Register-SharePointApp.ps1 `
    -TenantId "<tenant-id>" `
    -KeyVaultName "kv-hydroone-test2"

# IMPORTANT: Grant admin consent in Azure Portal
# Go to: Azure AD > App Registrations > HydroOne-SPO-Migration > API Permissions > Grant admin consent
# Required: Sites.Read.All and Files.Read.All (Microsoft Graph, Application)
```

### Step 3: Deploy ADF ARM Templates

```bash
# Deploy ADF resources
az deployment group create \
    --resource-group rg-hydroone-migration-test \
    --template-file adf-templates/arm-template.json \
    --parameters @config/parameters.test.json
```

### Step 4: Initialize SQL Database

```bash
# Connect to SQL and run scripts
sqlcmd -S sql-hydroone-migration-test.database.windows.net \
    -d MigrationControl \
    -i sql/create_control_table.sql

sqlcmd -S sql-hydroone-migration-test.database.windows.net \
    -d MigrationControl \
    -i sql/create_audit_log_table.sql

# Run production schema updates (adds DeltaLink and DriveId columns)
sqlcmd -S sql-hydroone-migration-test.database.windows.net \
    -d MigrationControl \
    -i sql/03_production_schema_updates.sql
```

### Step 5: Populate Control Table

Insert test data to validate the pipeline. The following example uses the working SQL insert format:

```sql
INSERT INTO dbo.MigrationControl (SiteUrl, LibraryName, SiteTitle, LibraryTitle, Status, Priority, EnableIncrementalSync, CreatedBy)
VALUES ('/sites/SalesAndMarketing', 'Shared Documents', 'Sales And Marketing', 'Documents', 'Pending', 1, 1, 'anuragdhuria');
```

**Key fields:**
- `SiteUrl`: The relative site path (e.g., `/sites/SalesAndMarketing`). Combined with the tenant URL (`https://m365x52073746.sharepoint.com`) during pipeline execution.
- `LibraryName`: The internal library name in SharePoint (e.g., `Shared Documents`).
- `SiteTitle`: Human-readable site name, used for ADLS folder structure.
- `LibraryTitle`: Human-readable library name, used for ADLS folder structure.

### Step 6: Run Pilot Migration

**Start with a single small library to validate:**

1. In Azure Portal, go to ADF (`adf-hydroone-migration-test`) > Author > Pipelines
2. Select `PL_Master_Migration_Orchestrator`
3. Click "Debug" or "Add Trigger" > "Trigger Now"
4. Set parameters:
   - BatchSize: 1
   - ParallelLibraries: 1
   - MaxRetries: 3

5. Monitor in ADF Monitor tab
6. Verify files in ADLS container (`sthydroonemigtest`)
7. Check audit log in SQL database

### Step 7: Batch Migration

**Recommended Batch Sizes:**

| Phase | Batch Size | Parallel Libraries | DIU | Time of Day |
|-------|------------|-------------------|-----|-------------|
| Pilot | 1 | 1 | 4 | Any |
| Small Batch | 5 | 2 | 4 | Business hours |
| Medium Batch | 10 | 4 | 8 | Off-peak |
| Large Batch | 20 | 8 | 16 | Evenings/Weekends |

**Execute batch migration:**

1. Enable the evening trigger:
   ```powershell
   Start-AzDataFactoryV2Trigger `
       -ResourceGroupName "rg-hydroone-migration-test" `
       -DataFactoryName "adf-hydroone-migration-test" `
       -Name "TR_Evening_BulkMigration"
   ```

2. Or trigger manually:
   ```powershell
   Invoke-AzDataFactoryV2Pipeline `
       -ResourceGroupName "rg-hydroone-migration-test" `
       -DataFactoryName "adf-hydroone-migration-test" `
       -PipelineName "PL_Master_Migration_Orchestrator" `
       -Parameter @{
           BatchSize = 20
           ParallelLibraries = 4
           MaxRetries = 3
       }
   ```

### Monitoring Pipeline Runs

**In Azure Portal:**
1. Go to Data Factory (`adf-hydroone-migration-test`) > Monitor
2. View Pipeline Runs
3. Click on run for details
4. Check Activity Runs for per-file status

**Using PowerShell:**
```powershell
.\scripts\Monitor-Migration.ps1 `
    -ResourceGroupName "rg-hydroone-migration-test" `
    -DataFactoryName "adf-hydroone-migration-test" `
    -SqlServerName "sql-hydroone-migration-test" `
    -SqlDatabaseName "MigrationControl" `
    -ContinuousMonitor
```

### Pause/Resume Migration

**To Pause:**
1. Stop any running triggers:
   ```powershell
   Stop-AzDataFactoryV2Trigger `
       -ResourceGroupName "rg-hydroone-migration-test" `
       -DataFactoryName "adf-hydroone-migration-test" `
       -Name "TR_Evening_BulkMigration"
   ```

2. Cancel running pipelines (if needed):
   - In ADF Monitor, select running pipeline
   - Click "Cancel"

**To Resume:**
1. Update control table to reset failed items:
   ```sql
   UPDATE dbo.MigrationControl
   SET Status = 'Pending', RetryCount = 0
   WHERE Status = 'Failed' AND RetryCount >= 3
   ```

2. Re-enable trigger or manually trigger pipeline

---

## Throttling Management

### Microsoft Graph API Throttling Limits

| Limit Type | Threshold | Response |
|------------|-----------|----------|
| Requests/minute | ~600 | HTTP 429 |
| Concurrent connections | ~10-15 | Connection refused |
| Large file downloads | Variable | Slower throughput |
| Inter-page delay | Configurable (default 2s) | Prevents burst throttling during pagination |

### Identifying Throttling

**Signs of throttling:**
- Increased HTTP 429 errors in audit log
- Slower than expected throughput
- Pipeline activities taking longer
- Retry-After headers in responses

**Query to check throttling:**
```sql
SELECT
    CAST([Timestamp] AS DATE) AS [Date],
    DATEPART(HOUR, [Timestamp]) AS [Hour],
    COUNT(*) AS ThrottleCount
FROM dbo.MigrationAuditLog
WHERE ErrorCode = '429'
GROUP BY CAST([Timestamp] AS DATE), DATEPART(HOUR, [Timestamp])
ORDER BY [Date] DESC, [Hour]
```

### Adjusting for Throttling

**Reduce parallelism:**
```powershell
# Update pipeline parameters
Invoke-AzDataFactoryV2Pipeline `
    -PipelineName "PL_Master_Migration_Orchestrator" `
    -Parameter @{
        BatchSize = 5          # Reduce from 20
        ParallelLibraries = 2  # Reduce from 4
    }
```

**Adjust pagination settings:**
```powershell
# Reduce page size and increase throttle delay
Invoke-AzDataFactoryV2Pipeline `
    -PipelineName "PL_Master_Migration_Orchestrator" `
    -Parameter @{
        BatchSize = 5
        ParallelLibraries = 2
        PageSize = 100           # Reduce from 200
        ThrottleDelaySeconds = 5 # Increase from 2
    }
```

**ADF DIU settings:**
| Scenario | DIU Setting |
|----------|-------------|
| Heavy throttling | 2-4 |
| Moderate throttling | 4-8 |
| Low throttling | 8-16 |

### Time-of-Day Scheduling

| Time Window (EST) | Activity | Parallelism |
|-------------------|----------|-------------|
| 6 AM - 6 PM | Minimal/None | 1-2 |
| 6 PM - 10 PM | Moderate | 4 |
| 10 PM - 6 AM | Maximum | 8 |
| Weekends | Maximum | 8 |

---

## Error Handling & Recovery

### Common Errors and Resolutions

#### "Unsupported app only token" from SharePoint REST API
**Cause:** The pipeline is calling the SharePoint REST API (`_api/web/...`) with an app-only (client credentials) token. SharePoint REST API does not support app-only tokens for most operations.
**Resolution:**
1. Switch all SharePoint data access to use the **Microsoft Graph API** instead
2. Acquire tokens with scope `https://graph.microsoft.com/.default`
3. Use Graph endpoints: `/v1.0/sites/...`, `/v1.0/drives/...`
4. Do NOT use SharePoint REST endpoints (`_api/web/GetFolderByServerRelativeUrl`, etc.)

#### Doubled URL in HTTP file downloads
**Cause:** The ADF HTTP source is constructing a URL like `https://m365x52073746.sharepoint.com/https://m365x52073746.sharepoint.com/...` by concatenating a base URL with a full URL returned from SharePoint.
**Resolution:**
1. Use the Graph API `/content` endpoint instead: `GET https://graph.microsoft.com/v1.0/drives/{drive-id}/items/{item-id}/content`
2. Pass the Bearer token in the Authorization header
3. Do NOT use the `@microsoft.graph.downloadUrl` directly (it is a pre-authenticated URL that expires and may cause URL doubling in ADF)

#### ADLS Forbidden (403) when writing files
**Cause:** The storage account (`sthydroonemigtest`) has public network access disabled, or the ADF Managed Identity lacks the required RBAC role.
**Resolution:**
1. Enable **public network access** on the storage account (Networking > Firewalls and virtual networks > Allow access from all networks), or configure a private endpoint
2. Assign the **Storage Blob Data Contributor** role to the ADF Managed Identity on the storage account
3. Verify the linked service in ADF uses Managed Identity authentication (not account key)

#### SQL Server "Deny Public Network Access" error
**Cause:** The SQL Server (`sql-hydroone-migration-test`) has public network access disabled.
**Resolution:**
1. In Azure Portal, go to SQL Server > Networking
2. Set **Public network access** to **Selected networks** or **All networks**
3. Add the ADF outbound IP addresses to the firewall rules, or check "Allow Azure services and resources to access this server"

#### Key Vault access denied (403)
**Cause:** The Key Vault (`kv-hydroone-test2`) has public network access disabled, or the ADF Managed Identity does not have the Key Vault Secrets User role.
**Resolution:**
1. Enable **public network access** on the Key Vault (Networking > Allow public access from all networks), or configure a private endpoint
2. Assign the **Key Vault Secrets User** role to the ADF Managed Identity
3. If the Key Vault uses access policies (not RBAC), add an access policy granting Get and List for Secrets to the ADF Managed Identity

#### ADF circular reference error in pipeline
**Cause:** `PL_Process_Subfolder` was configured to call itself recursively, which ADF does not allow (circular/self-referencing pipeline invocation).
**Resolution:**
1. `PL_Process_Subfolder` must NOT call itself via Execute Pipeline
2. Instead, have `PL_Migrate_Library` handle recursive traversal by calling `PL_Process_Subfolder` for each subfolder discovered
3. `PL_Process_Subfolder` enumerates items in a single folder and calls back to `PL_Migrate_Library` (or a wrapper) for any sub-subfolders

#### HTTP 401 - Unauthorized
**Cause:** Token expired or invalid credentials
**Resolution:**
1. Check Key Vault secrets (`SPO-ClientId`, `SPO-ClientSecret`, `SPO-TenantId`) have not expired
2. Regenerate client secret if needed
3. Update secret in Key Vault
4. Verify token scope is `https://graph.microsoft.com/.default`
5. Re-run failed items

#### Token Expiration During Long-Running Migration
**Cause:** Libraries with thousands of files take >60 minutes to process, causing the OAuth2 token to expire mid-run.
**Resolution:** The production pipelines include automatic token refresh every 45 minutes. If you still see 401 errors:
1. Verify the `If_TokenExpiring` activity is present in the pipeline
2. Check that Key Vault access is still working (the refresh flow re-reads the client secret)
3. Verify the client secret has not expired on the Azure AD app registration

#### HTTP 403 - Forbidden (Graph API)
**Cause:** Insufficient Graph API permissions or admin consent not granted
**Resolution:**
1. Verify app has `Sites.Read.All` and `Files.Read.All` permissions (Microsoft Graph, Application)
2. Verify admin consent has been granted (green checkmark in Azure Portal)
3. Check if the site has conditional access policies blocking app access
4. Mark library as "Skipped" if access cannot be granted

#### HTTP 404 - Not Found
**Cause:** File or library deleted after enumeration, or incorrect site/drive path
**Resolution:**
1. Verify the `SiteUrl` in the control table matches the actual SharePoint site path
2. Verify the `LibraryName` matches the internal name of the document library
3. If file was deleted at source, log as expected and skip
4. Re-enumerate library if many 404s occur

#### HTTP 429 - Throttled
**Cause:** Microsoft Graph API rate limit exceeded
**Resolution:**
1. Wait activity pauses for configured time
2. Retry automatically
3. If persistent, reduce parallelism
4. Contact Microsoft for limit increase

#### HTTP 503 - Service Unavailable
**Cause:** Microsoft Graph or SharePoint service temporarily unavailable
**Resolution:**
1. Automatic retry after delay
2. Check Microsoft 365 service health dashboard
3. Resume later if service is down

### Retry Failed Files

**Identify failed files:**
```sql
SELECT SourcePath, FileName, ErrorCode, ErrorDetails
FROM dbo.MigrationAuditLog
WHERE MigrationStatus = 'Failed'
ORDER BY [Timestamp] DESC
```

**Reset for retry:**
```sql
-- Reset library for retry
UPDATE dbo.MigrationControl
SET Status = 'Pending',
    RetryCount = 0,
    ErrorMessage = NULL
WHERE LibraryName = 'Shared Documents'
AND SiteUrl = '/sites/SalesAndMarketing'

-- Clear failed audit entries for re-processing
DELETE FROM dbo.MigrationAuditLog
WHERE SourcePath LIKE '%Shared Documents%'
AND MigrationStatus = 'Failed'
```

### Restart a Failed Batch

1. Identify the failed batch:
   ```sql
   SELECT * FROM dbo.BatchLog WHERE Status = 'Failed' ORDER BY StartTime DESC
   ```

2. Reset libraries in that batch:
   ```sql
   UPDATE dbo.MigrationControl
   SET Status = 'Pending', RetryCount = 0
   WHERE BatchId = 'BATCH-20240115-200000'
   AND Status = 'Failed'
   ```

3. Re-trigger the pipeline

### Escalation Path

| Issue | First Contact | Escalation |
|-------|--------------|------------|
| ADF Pipeline Errors | Microsoft Azure Team | Microsoft Support |
| SharePoint Access Issues | Hydro One SharePoint Admin | Microsoft Support |
| Persistent Throttling | Microsoft Account Team | FastTrack |
| Data Discrepancies | Microsoft Data Team | Hydro One Business Owner |

---

## Post-Migration

### Validation Steps

1. **File Count Reconciliation:**
   ```powershell
   .\scripts\Validate-Migration.ps1 `
       -SharePointTenantUrl "https://m365x52073746.sharepoint.com" `
       -StorageAccountName "sthydroonemigtest" `
       -ContainerName "sharepoint-migration" `
       -SqlServerName "sql-hydroone-migration-test" `
       -SqlDatabaseName "MigrationControl"
   ```

2. **Run Validation Pipeline:**
   - Trigger `PL_Validation` pipeline
   - Review results in control table

3. **Size Comparison:**
   ```sql
   SELECT
       SUM(TotalSizeBytes) / 1099511627776.0 AS SourceTB,
       SUM(MigratedSizeBytes) / 1099511627776.0 AS MigratedTB,
       (SUM(MigratedSizeBytes) * 100.0 / NULLIF(SUM(TotalSizeBytes), 0)) AS PercentComplete
   FROM dbo.MigrationControl
   WHERE Status = 'Completed'
   ```

4. **Spot-Check Files:**
   - Randomly select 10-20 files per library
   - Compare file sizes
   - Verify file opens correctly

5. **Production Feature Validation:**

   **a. Pagination Verification:**
   Re-run migration with `PageSize = 3` on a small library:
   ```powershell
   # Trigger with small PageSize to verify Until loop pagination
   $params = @{
       SiteUrl = "/sites/SalesAndMarketing"
       LibraryName = "Shared Documents"
       ControlTableId = "1"
       BatchId = "TEST-PAGINATION"
       ContainerName = "sharepoint-migration"
       SharePointTenantUrl = "https://m365x52073746.sharepoint.com"
       PageSize = 3
       CopyBatchCount = 2
       ThrottleDelaySeconds = 1
   }
   Invoke-AzDataFactoryV2Pipeline `
       -ResourceGroupName "rg-hydroone-migration-test" `
       -DataFactoryName "adf-hydroone-migration-test" `
       -PipelineName "PL_Migrate_Single_Library" `
       -Parameter $params
   ```
   Verify in ADF Monitor that `Until_AllPagesProcessed` ran multiple iterations.

   **b. Deep Folder Verification:**
   ```sql
   -- Check that files from all folder depths were migrated
   SELECT DestinationPath, FileSizeBytes, MigrationStatus
   FROM dbo.MigrationAuditLog
   WHERE DestinationPath LIKE '%/%/%/%'  -- 3+ path segments = subfolder depth >1
   ORDER BY DestinationPath;
   ```

   **c. DeltaLink Verification:**
   ```sql
   -- Verify deltaLink stored after migration
   SELECT SiteUrl, LibraryName, DriveId,
       LEN(DeltaLink) AS DeltaLinkLength,
       CASE WHEN DeltaLink IS NOT NULL THEN 'PASS' ELSE 'FAIL' END AS DeltaLinkStatus,
       LastSyncTime
   FROM dbo.IncrementalWatermark;
   ```

   **d. Incremental Sync Verification:**
   - Add a new file to the SharePoint library
   - Run `PL_Incremental_Sync`
   - Verify only the new file was copied:
   ```sql
   SELECT FileName, MigrationStatus, [Timestamp]
   FROM dbo.MigrationAuditLog
   WHERE MigrationStatus = 'IncrementalSync'
   ORDER BY [Timestamp] DESC;
   ```
   - Run again with no changes — should process 0 files

### Sign-Off Checklist

- [ ] All libraries migrated (Status = 'Completed')
- [ ] File count matches within 1% tolerance
- [ ] Total size matches within 5% tolerance
- [ ] No critical files missing (verified by business)
- [ ] Spot-check samples pass verification
- [ ] Validation pipeline shows "Validated" status
- [ ] Audit log reviewed for errors
- [ ] Business stakeholder sign-off obtained
- [ ] DeltaLink stored for all completed libraries (IncrementalWatermark)
- [ ] Pagination verified with small PageSize (Until loop ran multiple iterations)
- [ ] Deep folder files migrated correctly (depth >2 verified in ADLS)
- [ ] Token refresh verified for long-running migrations
- [ ] Incremental sync tested (only changed files copied)

### Cutover to Incremental Sync

1. **Enable incremental sync for all libraries:**
   ```sql
   UPDATE dbo.MigrationControl
   SET EnableIncrementalSync = 1
   WHERE Status = 'Completed' AND ValidationStatus = 'Validated'
   ```

2. **Start incremental sync trigger:**
   ```powershell
   Start-AzDataFactoryV2Trigger `
       -ResourceGroupName "rg-hydroone-migration-test" `
       -DataFactoryName "adf-hydroone-migration-test" `
       -Name "TR_TumblingWindow_IncrementalSync"
   ```

3. **Monitor incremental syncs:**
   ```sql
   SELECT * FROM dbo.SyncLog ORDER BY StartTime DESC
   ```

4. **Verify deltaLink persistence:**
   ```sql
   -- After first incremental sync run, verify deltaLinks are stored
   SELECT SiteUrl, LibraryName, DriveId,
       CASE WHEN DeltaLink IS NOT NULL THEN 'Stored' ELSE 'Not yet' END AS DeltaLinkStatus,
       LastSyncTime
   FROM dbo.IncrementalWatermark
   ORDER BY LastSyncTime DESC
   ```

### Decommission Source Content

**After validation period (recommended: 30-90 days):**

1. **Archive SharePoint Libraries:**
   - Set libraries to read-only
   - Add banner indicating migration complete
   - Update links to point to new ADLS location

2. **Delete Source Content (Optional):**
   - Only after business sign-off
   - Start with oldest/least critical content
   - Keep audit trail of deletions

---

## Rollback Plan

### Scenarios Requiring Rollback

| Scenario | Rollback Action |
|----------|-----------------|
| Critical data corruption | Restore from SharePoint (source unchanged) |
| Major migration failure | Stop migration, use SharePoint as primary |
| Business decision | Stop incremental sync, revert to SharePoint |

### Rollback Procedure

1. **Stop all migration activities:**
   ```powershell
   # Stop all triggers
   Get-AzDataFactoryV2Trigger -ResourceGroupName "rg-hydroone-migration-test" `
       -DataFactoryName "adf-hydroone-migration-test" |
       Stop-AzDataFactoryV2Trigger

   # Cancel running pipelines
   # (Manual in Azure Portal)
   ```

2. **Notify stakeholders:**
   - Immediate notification to business owners
   - Update project status

3. **Document issues:**
   - Export audit logs
   - Capture error messages
   - Record timeline of events

4. **Source data intact:**
   - SharePoint data is READ during migration
   - No modifications made to source
   - Full rollback = continue using SharePoint

5. **Cleanup (if needed):**
   - Delete migrated files from ADLS (if corrupted)
   - Reset control table
   - Address root cause before retry

### Data Retention During Migration

| Location | Retention | Notes |
|----------|-----------|-------|
| SharePoint (Source) | Unchanged | Read-only access during migration |
| ADLS (Destination) | Permanent | Primary storage post-migration |
| Audit Logs | 1 year | Compliance and troubleshooting |
| Control Table | Permanent | Migration history |

---

## Contact Information

| Role | Contact | Responsibility |
|------|---------|----------------|
| Microsoft Lead | [Name/Email] | Technical delivery |
| Hydro One PM | [Name/Email] | Business decisions |
| Hydro One SharePoint Admin | [Name/Email] | SharePoint access |
| Microsoft TAM | [Name/Email] | Throttling escalations |
| Azure Support | Portal | Technical issues |
