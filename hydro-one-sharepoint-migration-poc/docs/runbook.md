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

## Critical Prerequisites for Hydro One

> **These items MUST be completed by Hydro One IT before migration testing or execution can begin.**

### 1. Grant Admin Consent for SharePoint API Permissions (BLOCKER)

A **Global Administrator** in the Hydro One Azure AD tenant must grant admin consent for the registered application's SharePoint API permissions. Without this, the Azure Data Factory pipelines **cannot access SharePoint Online** and the entire migration is blocked.

**Steps for Hydro One Global Admin:**
1. Sign in to [Azure Portal](https://portal.azure.com) as Global Administrator
2. Navigate to **Azure Active Directory** > **App registrations**
3. Select the migration app (e.g., `HydroOne-SPO-Migration`)
4. Click **API permissions**
5. Click **Grant admin consent for Hydro One**
6. Confirm by clicking **Yes**
7. Verify all permissions show green checkmark: **"Granted for Hydro One"**

**Required Permissions:**

| API | Permission | Type |
|-----|-----------|------|
| SharePoint Online | Sites.FullControl.All | Application |
| SharePoint Online | Sites.ReadWrite.All | Application |
| SharePoint Online | Migration.Read.All | Application |
| SharePoint Online | Migration.ReadWrite.All | Application |
| Microsoft Graph | Sites.ReadWrite.All | Application |

### 2. Grant ADF Managed Identity Access to SQL Database

Run this SQL command in the `MigrationControl` database:

```sql
CREATE USER [adf-hydroone-migration-{env}] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [adf-hydroone-migration-{env}];
ALTER ROLE db_datawriter ADD MEMBER [adf-hydroone-migration-{env}];
GRANT EXECUTE ON SCHEMA::dbo TO [adf-hydroone-migration-{env}];
```

### 3. Provide SharePoint Site Collection Inventory

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
  - [ ] **CRITICAL: Global Administrator or Privileged Role Administrator** required to grant admin consent for SharePoint API permissions
  - [ ] Without admin consent, the migration **cannot proceed** — all SharePoint API calls will return HTTP 401/403

- [ ] **Network Requirements**
  - [ ] Outbound HTTPS (443) to SharePoint Online
  - [ ] Outbound HTTPS (443) to Azure services
  - [ ] No firewall blocking Azure Data Factory IPs

### SharePoint Prerequisites

- [ ] **Admin Access**
  - [ ] SharePoint Online Administrator role
  - [ ] Access to all site collections to be migrated

- [ ] **App Registration**
  - [ ] Azure AD App registered with SharePoint permissions:
    - `Sites.FullControl.All` (Application) — required for full file access
    - `Sites.ReadWrite.All` (Application) — required for file read/write
    - `Migration.Read.All` (Application) — required for migration APIs
    - `Migration.ReadWrite.All` (Application) — required for migration write
  - [ ] **Admin consent granted** for all above permissions (must show green "Granted" status)
  - [ ] Client secret generated and stored in Key Vault

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
Subject: SharePoint Online API Throttling Limit Increase Request - Hydro One Migration

Dear Microsoft Account Team,

We are planning a large-scale data migration from SharePoint Online to Azure Data Lake Storage Gen2 for Hydro One. We request a temporary increase in SharePoint Online API throttling limits to facilitate this migration.

Migration Details:
- Tenant: hydroone.sharepoint.com
- Data Volume: ~25 TB
- Timeline: [INSERT DATES]
- Migration Tool: Azure Data Factory with SharePoint REST API
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

### Step 1: Deploy Azure Resources

```bash
# Login to Azure
az login

# Set subscription
az account set --subscription "<subscription-id>"

# Deploy resources using PowerShell script
.\scripts\Setup-AzureResources.ps1 -Environment "dev" -Location "canadacentral"
```

### Step 2: Register SharePoint App

```powershell
# Register app and store credentials in Key Vault
.\scripts\Register-SharePointApp.ps1 `
    -TenantId "<tenant-id>" `
    -KeyVaultName "kv-hydroone-mig-dev"

# IMPORTANT: Grant admin consent in Azure Portal
# Go to: Azure AD > App Registrations > HydroOne-SPO-Migration > API Permissions > Grant admin consent
```

### Step 3: Deploy ADF ARM Templates

```bash
# Deploy ADF resources
az deployment group create \
    --resource-group rg-hydroone-migration-dev \
    --template-file adf-templates/arm-template.json \
    --parameters @config/parameters.dev.json
```

### Step 4: Initialize SQL Database

```bash
# Connect to SQL and run scripts
sqlcmd -S sql-hydroone-migration-dev.database.windows.net \
    -d MigrationControl \
    -i sql/create_control_table.sql

sqlcmd -S sql-hydroone-migration-dev.database.windows.net \
    -d MigrationControl \
    -i sql/create_audit_log_table.sql
```

### Step 5: Populate Control Table

```powershell
# Enumerate SharePoint and populate control table
.\scripts\Populate-ControlTable.ps1 `
    -SharePointTenantUrl "https://hydroone.sharepoint.com" `
    -SqlServerName "sql-hydroone-migration-dev" `
    -SqlDatabaseName "MigrationControl" `
    -UseInteractiveAuth
```

### Step 6: Run Pilot Migration

**Start with a single small library to validate:**

1. In Azure Portal, go to ADF > Author > Pipelines
2. Select `PL_Master_Migration_Orchestrator`
3. Click "Debug" or "Add Trigger" > "Trigger Now"
4. Set parameters:
   - BatchSize: 1
   - ParallelLibraries: 1
   - MaxRetries: 3

5. Monitor in ADF Monitor tab
6. Verify files in ADLS container
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
       -ResourceGroupName "rg-hydroone-migration-dev" `
       -DataFactoryName "adf-hydroone-migration-dev" `
       -Name "TR_Evening_BulkMigration"
   ```

2. Or trigger manually:
   ```powershell
   Invoke-AzDataFactoryV2Pipeline `
       -ResourceGroupName "rg-hydroone-migration-dev" `
       -DataFactoryName "adf-hydroone-migration-dev" `
       -PipelineName "PL_Master_Migration_Orchestrator" `
       -Parameter @{
           BatchSize = 20
           ParallelLibraries = 4
           MaxRetries = 3
       }
   ```

### Monitoring Pipeline Runs

**In Azure Portal:**
1. Go to Data Factory > Monitor
2. View Pipeline Runs
3. Click on run for details
4. Check Activity Runs for per-file status

**Using PowerShell:**
```powershell
.\scripts\Monitor-Migration.ps1 `
    -ResourceGroupName "rg-hydroone-migration-dev" `
    -DataFactoryName "adf-hydroone-migration-dev" `
    -SqlServerName "sql-hydroone-migration-dev" `
    -SqlDatabaseName "MigrationControl" `
    -ContinuousMonitor
```

### Pause/Resume Migration

**To Pause:**
1. Stop any running triggers:
   ```powershell
   Stop-AzDataFactoryV2Trigger `
       -ResourceGroupName "rg-hydroone-migration-dev" `
       -DataFactoryName "adf-hydroone-migration-dev" `
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

### SharePoint Online Throttling Limits

| Limit Type | Threshold | Response |
|------------|-----------|----------|
| Requests/minute | ~600 | HTTP 429 |
| Concurrent connections | ~10-15 | Connection refused |
| Large file downloads | Variable | Slower throughput |

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

#### HTTP 401 - Unauthorized
**Cause:** Token expired or invalid credentials
**Resolution:**
1. Check Key Vault secret hasn't expired
2. Regenerate client secret if needed
3. Update secret in Key Vault
4. Re-run failed items

#### HTTP 403 - Forbidden
**Cause:** Insufficient permissions or site-level restrictions
**Resolution:**
1. Verify app has Sites.Read.All permission
2. Check if site has custom permissions blocking app
3. Request SharePoint admin to grant access
4. Mark library as "Skipped" if access cannot be granted

#### HTTP 404 - Not Found
**Cause:** File or library deleted after enumeration
**Resolution:**
1. Log as expected (file removed at source)
2. Skip and continue
3. Re-enumerate library if many 404s

#### HTTP 429 - Throttled
**Cause:** SharePoint API rate limit exceeded
**Resolution:**
1. Wait activity pauses for configured time
2. Retry automatically
3. If persistent, reduce parallelism
4. Contact Microsoft for limit increase

#### HTTP 503 - Service Unavailable
**Cause:** SharePoint service temporarily unavailable
**Resolution:**
1. Automatic retry after delay
2. Check SharePoint service health
3. Resume later if service is down

#### File Locked / Checked Out
**Cause:** File is checked out by user
**Resolution:**
1. Log error and continue
2. Retry in next batch
3. Contact file owner to check in
4. For persistent locks, escalate to SharePoint admin

#### File Too Large
**Cause:** File exceeds copy timeout or memory limits
**Resolution:**
1. Increase activity timeout
2. Copy individually with dedicated pipeline
3. For files >10 GB, consider alternative methods

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
WHERE LibraryName = 'YourLibraryName'
AND SiteUrl = '/sites/YourSite'

-- Clear failed audit entries for re-processing
DELETE FROM dbo.MigrationAuditLog
WHERE SourcePath LIKE '%YourLibraryName%'
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
       -SharePointTenantUrl "https://hydroone.sharepoint.com" `
       -StorageAccountName "sthydroonemigdev" `
       -ContainerName "sharepoint-migration" `
       -SqlServerName "sql-hydroone-migration-dev" `
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

### Sign-Off Checklist

- [ ] All libraries migrated (Status = 'Completed')
- [ ] File count matches within 1% tolerance
- [ ] Total size matches within 5% tolerance
- [ ] No critical files missing (verified by business)
- [ ] Spot-check samples pass verification
- [ ] Validation pipeline shows "Validated" status
- [ ] Audit log reviewed for errors
- [ ] Business stakeholder sign-off obtained

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
       -ResourceGroupName "rg-hydroone-migration-prod" `
       -DataFactoryName "adf-hydroone-migration-prod" `
       -Name "TR_TumblingWindow_IncrementalSync"
   ```

3. **Monitor incremental syncs:**
   ```sql
   SELECT * FROM dbo.SyncLog ORDER BY StartTime DESC
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
   Get-AzDataFactoryV2Trigger -ResourceGroupName "rg-hydroone-migration-dev" `
       -DataFactoryName "adf-hydroone-migration-dev" |
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
