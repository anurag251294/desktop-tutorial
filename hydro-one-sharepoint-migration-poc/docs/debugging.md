# Hydro One SharePoint Migration - Troubleshooting Guide

> **Project**: SharePoint Online to ADLS Gen2 migration via Azure Data Factory and Microsoft Graph API
> **Environment**: Test values shown throughout. Production resource names will differ.

---

## How to Use This Guide

This guide is organized **by error code or symptom**. When you encounter an issue:

1. Find the HTTP status code, ADF error message, or symptom in the **Quick Reference** table below.
2. Jump to the corresponding section for root cause analysis and resolution steps.
3. If the issue persists, see [Log Collection](#log-collection) and [Escalation Path](#escalation-path) at the end.

---

## Quick Reference: Error Code Index

| Error Code / Symptom | Section | Likely Component |
|---|---|---|
| HTTP 401 Unauthorized | [Section 1](#1-http-401-unauthorized) | Graph API / Token |
| HTTP 403 Forbidden (Graph) | [Section 2](#2-http-403-forbidden-graph-api) | Graph API / Permissions |
| HTTP 404 Not Found | [Section 3](#3-http-404-not-found) | Graph API / Drive/Item IDs |
| HTTP 429 Too Many Requests | [Section 4](#4-http-429-throttled) | Graph API / Throttling |
| HTTP 503 Service Unavailable | [Section 5](#5-http-503-service-unavailable) | Graph API / SharePoint |
| "Unsupported app only token" | [Section 6](#6-unsupported-app-only-token) | SharePoint REST vs Graph |
| Doubled URL / base URL concatenation | [Section 7](#7-doubled-url--base-url-concatenation) | ADF HTTP connector |
| ADLS 403 Forbidden write error | [Section 8](#8-adls-403-forbidden-write-error) | Storage permissions |
| SQL Server connection denied | [Section 9](#9-sql-server-connection-denied--sqldeniedpublicaccess) | SQL firewall |
| Key Vault access denied (403) | [Section 10](#10-key-vault-access-denied-403) | Key Vault policies |
| ADF "circular reference not allowed" | [Section 11](#11-adf-circular-reference-not-allowed) | ADF pipeline design |
| ADF container inside container | [Section 12](#12-adf-container-activity-cannot-include-another-container-activity) | ADF Until/ForEach |
| ADF ForEach inside IfCondition | [Section 13](#13-adf-foreach-inside-ifcondition) | ADF activity nesting |
| ADF self-referencing variable | [Section 14](#14-adf-self-referencing-variable) | ADF SetVariable |
| Token expiration during migration | [Section 15](#15-token-expiration-during-long-running-migrations) | OAuth token lifetime |
| Pipeline timeout | [Section 16](#16-pipeline-timeout) | ADF timeout settings |
| File locked / checked out | [Section 17](#17-file-locked--checked-out) | SharePoint file locks |
| Populate-ControlTable.ps1 errors (SQL firewall, ADFS auth, 404, DNS) | [Section 18](#18-populate-controltableps1-errors) | PowerShell script |

---

## Error Details

### 1. HTTP 401 Unauthorized

**Symptom**
```json
{
  "error": {
    "code": "InvalidAuthenticationToken",
    "message": "Access token has expired or is not yet valid."
  }
}
```
ADF activity failure in any Web or Copy activity that calls Graph API.

**Root Cause**
- The OAuth client_credentials token has expired (default lifetime: 1 hour).
- The token was issued with an incorrect `resource` or `scope` value.
- The app registration client secret has expired in Azure AD.

**Resolution**
1. Check client secret expiry in Azure Portal:
   ```
   Azure AD > App registrations > bca94bda-c22c-4cd6-a065-72b12ae88c91 > Certificates & secrets
   ```
2. If the secret is expired, generate a new one and update Key Vault:
   ```bash
   az keyvault secret set \
     --vault-name kv-hydroone-test2 \
     --name "sp-client-secret" \
     --value "<new-secret-value>"
   ```
3. Verify the token request uses the correct scope:
   ```
   POST https://login.microsoftonline.com/{tenantId}/oauth2/v2.0/token
   scope=https://graph.microsoft.com/.default
   ```
4. Re-run the failed pipeline from the ADF Monitor.

**Prevention**
- Set a calendar reminder 30 days before client secret expiry.
- Use the pipeline's built-in token refresh (Web activity at the start of each batch) rather than passing tokens across long Until loops.

---

### 2. HTTP 403 Forbidden (Graph API)

**Symptom**
```json
{
  "error": {
    "code": "accessDenied",
    "message": "Access denied. Check credentials and try again."
  }
}
```

**Root Cause**
- The app registration lacks the required Microsoft Graph **application** permissions.
- Admin consent has not been granted for the permissions.
- The app is trying to access a site/drive it does not have `Sites.Selected` access to (if using granular permissions).

**Resolution**
1. Verify API permissions in Azure AD:
   ```
   Azure AD > App registrations > bca94bda-c22c-4cd6-a065-72b12ae88c91 > API permissions
   ```
2. Required application permissions for this project:
   | Permission | Type | Purpose |
   |---|---|---|
   | `Sites.Read.All` | Application | Read SharePoint site/drive metadata |
   | `Files.Read.All` | Application | Download file content via `/content` endpoint |
3. Grant admin consent if the "Grant admin consent" button shows a warning icon.
4. Wait 5-10 minutes for permission propagation, then retry.

**Prevention**
- Document all required permissions in the deployment runbook.
- After granting permissions, verify with a manual token test before running the pipeline.

---

### 3. HTTP 404 Not Found

**Symptom**
```json
{
  "error": {
    "code": "itemNotFound",
    "message": "The resource could not be found."
  }
}
```

**Root Cause**
- The `driveId` or `itemId` used in the Graph API call is stale or incorrect.
- The SharePoint library or file was renamed, moved, or deleted after the control table was populated.
- The site URL was entered incorrectly in the control table.

**Resolution**
1. Verify the drive exists using Graph Explorer or CLI:
   ```bash
   # Get all drives for the site
   az rest --method GET \
     --url "https://graph.microsoft.com/v1.0/sites/m365x52073746.sharepoint.com:/sites/MigrationTest:/drives" \
     --headers "Content-Type=application/json"
   ```
2. Cross-check the `driveId` in the SQL control table:
   ```sql
   SELECT LibraryName, DriveId, SiteUrl
   FROM dbo.MigrationControlTable
   WHERE IsActive = 1;
   ```
3. Update the control table if the drive ID has changed:
   ```sql
   UPDATE dbo.MigrationControlTable
   SET DriveId = '<new-drive-id>'
   WHERE LibraryName = '<library-name>';
   ```

**Prevention**
- Run PL_Post_Migration_Validation before each migration batch to confirm all drives are accessible.
- Add a pre-flight check in PL_Master_Migration_Orchestrator that validates drive IDs.

---

### 4. HTTP 429 Throttled

**Symptom**
```json
{
  "error": {
    "code": "activityLimitReached",
    "message": "Application is over its MailBoxConcurrency limit."
  }
}
```
Or the response header `Retry-After: <seconds>` is present.

**Root Cause**
- Microsoft Graph enforces per-app and per-tenant throttling limits.
- SharePoint Online has a separate throttling layer (resource-specific).
- Concurrent pipeline runs or large ForEach batches exceed the limit.

**Resolution**
1. Check the `Retry-After` header value in the ADF activity output for the required wait time.
2. Reduce ForEach batch concurrency in PL_Copy_File_Batch:
   ```json
   {
     "type": "ForEach",
     "typeProperties": {
       "isSequential": false,
       "batchCount": 5
     }
   }
   ```
   Lower `batchCount` from the default (20) to 5 or less.
3. Review throttling patterns in the audit log:
   ```sql
   SELECT
     CAST(StartTime AS DATE) AS RunDate,
     DATEPART(HOUR, StartTime) AS RunHour,
     COUNT(*) AS ThrottledCount
   FROM dbo.MigrationAuditLog
   WHERE Status = 'Throttled' OR ErrorMessage LIKE '%429%'
   GROUP BY CAST(StartTime AS DATE), DATEPART(HOUR, StartTime)
   ORDER BY RunDate, RunHour;
   ```
4. If throttling is persistent, schedule migrations during off-peak hours (evenings/weekends).

**Prevention**
- Keep ForEach `batchCount` at 5 for production runs.
- Implement exponential backoff in retry policies on Web activities (max 3 retries, interval 60s).
- Stagger library migrations rather than running all at once.

---

### 5. HTTP 503 Service Unavailable

**Symptom**
```
HTTP 503: The service is temporarily unavailable. Please try again later.
```

**Root Cause**
- Transient SharePoint Online service issue.
- Microsoft is performing backend maintenance or experiencing an outage.

**Resolution**
1. Check Microsoft 365 Service Health:
   ```
   https://admin.microsoft.com > Service Health > SharePoint Online
   ```
2. Wait 5-15 minutes and retry.
3. If persistent, check the Microsoft 365 Status Twitter account: `@MSFT365Status`.

**Prevention**
- Configure ADF retry policies on all Graph API Web activities:
  ```json
  {
    "policy": {
      "retry": 3,
      "retryIntervalInSeconds": 60,
      "secureOutput": false,
      "timeout": "00:10:00"
    }
  }
  ```

---

### 6. "Unsupported app only token"

**Symptom**
```json
{
  "error": {
    "code": "-2147024891, System.UnauthorizedAccessException",
    "message": "Unsupported app only token."
  }
}
```
Occurs when calling SharePoint REST API endpoints (`/_api/`) with an Azure AD v2.0 app-only token.

**Root Cause**
SharePoint REST API (`/_api/`) does **not** accept Azure AD v2.0 app-only (client_credentials) tokens. It requires either:
- A delegated token (user context), or
- An Azure ACS app-only token (legacy), or
- A certificate-based Azure AD token with `Sites.Selected` permission.

**Resolution**
**Do not use SharePoint REST API.** Switch all calls to Microsoft Graph API:

| Instead of (SharePoint REST) | Use (Graph API) |
|---|---|
| `/_api/web/lists` | `/v1.0/sites/{siteId}/lists` |
| `/_api/web/GetFolderByServerRelativeUrl` | `/v1.0/drives/{driveId}/root:/path:/children` |
| `/_api/web/GetFileByServerRelativeUrl/\$value` | `/v1.0/drives/{driveId}/items/{itemId}/content` |

**Prevention**
- All pipeline activities must use `https://graph.microsoft.com/v1.0/...` endpoints exclusively.
- This is a hard architectural constraint documented in the project README.

---

### 7. Doubled URL / Base URL Concatenation

**Symptom**
ADF Copy activity or Web activity fails with a URL like:
```
https://graph.microsoft.com/v1.0/https://m365x52073746.sharepoint.com/_api/...
```
The base URL from the linked service is prepended to the full URL from the `@microsoft.graph.downloadUrl` property.

**Root Cause**
When using `@microsoft.graph.downloadUrl` from Graph API metadata responses, the returned URL is an absolute URL (e.g., `https://<tenant>.sharepoint.com/...`). ADF's HTTP connector concatenates this with the linked service base URL, producing a doubled/invalid URL.

**Resolution**
Do not use `@microsoft.graph.downloadUrl`. Instead, use the Graph `/content` endpoint which returns a 302 redirect that ADF handles correctly:
```
GET /v1.0/drives/{driveId}/items/{itemId}/content
Authorization: Bearer {token}
```

In ADF Copy activity or Web activity, set:
- **URL**: `@concat('https://graph.microsoft.com/v1.0/drives/', item().parentReference.driveId, '/items/', item().id, '/content')`
- **Additional headers**: `Authorization: @concat('Bearer ', activity('GetToken').output.access_token)`

**Prevention**
- Never use `@microsoft.graph.downloadUrl` in ADF pipelines.
- Always construct the `/content` URL from the `driveId` and `itemId`.

---

### 8. ADLS 403 Forbidden Write Error

**Symptom**
```
Operation: Copy Data | Status: Failed
ErrorCode: UserErrorFailedFileOperation
"This request is not authorized to perform this operation using this permission."
```
Occurs when the ADF managed identity or linked service tries to write to ADLS Gen2.

**Root Cause**
- The ADF managed identity does not have `Storage Blob Data Contributor` on the storage account `sthydroonemigtest`.
- The container or directory-level ACL is blocking writes.
- The storage account firewall is blocking ADF's IP.

**Resolution**
1. Assign the role via Azure CLI:
   ```bash
   # Get ADF managed identity object ID
   ADF_MI=$(az datafactory show \
     --resource-group rg-hydroone-migration-test \
     --factory-name adf-hydroone-migration-test \
     --query identity.principalId -o tsv)

   # Assign Storage Blob Data Contributor
   az role assignment create \
     --assignee "$ADF_MI" \
     --role "Storage Blob Data Contributor" \
     --scope "/subscriptions/671b1321-4407-420b-b877-97cd40ba898a/resourceGroups/rg-hydroone-migration-test/providers/Microsoft.Storage/storageAccounts/sthydroonemigtest"
   ```
2. If using a storage firewall, add ADF as a trusted service:
   ```bash
   az storage account update \
     --name sthydroonemigtest \
     --resource-group rg-hydroone-migration-test \
     --bypass AzureServices
   ```
3. Wait 5 minutes for RBAC propagation, then retry.

**Prevention**
- Include RBAC assignments in the Terraform/Bicep deployment templates.
- Verify write access with a test file before starting migration runs.

---

### 9. SQL Server Connection Denied / SqlDeniedPublicAccess

**Symptom**
```
ErrorCode: SqlFailedToConnect
"Cannot open server 'sql-hydroone-migration-test' requested by the login.
Client with IP address 'x.x.x.x' is not allowed to access the server."
```

**Root Cause**
- Azure SQL Server firewall does not allow the connecting IP address.
- "Deny public network access" is enabled on the SQL server.
- ADF managed identity is not added as a SQL user.

**Resolution**
1. Add a firewall rule for ADF (or allow Azure services):
   ```bash
   # Allow Azure services
   az sql server firewall-rule create \
     --resource-group rg-hydroone-migration-test \
     --server sql-hydroone-migration-test \
     --name AllowAzureServices \
     --start-ip-address 0.0.0.0 \
     --end-ip-address 0.0.0.0
   ```
2. If using private endpoints, verify the private endpoint connection is approved and the DNS resolves correctly.
3. Create a SQL user for the ADF managed identity:
   ```sql
   CREATE USER [adf-hydroone-migration-test] FROM EXTERNAL PROVIDER;
   ALTER ROLE db_datareader ADD MEMBER [adf-hydroone-migration-test];
   ALTER ROLE db_datawriter ADD MEMBER [adf-hydroone-migration-test];
   ```

**Prevention**
- Include SQL firewall rules and user provisioning in deployment automation.

---

### 10. Key Vault Access Denied (403)

**Symptom**
```
ErrorCode: AzureKeyVaultSecretNotFound
"Access denied. Caller was not found on any access policy."
```

**Root Cause**
- The ADF managed identity is not in the Key Vault access policy for `kv-hydroone-test2`.
- If using RBAC mode, the ADF identity lacks the `Key Vault Secrets User` role.

**Resolution**
1. For access policy model:
   ```bash
   ADF_MI=$(az datafactory show \
     --resource-group rg-hydroone-migration-test \
     --factory-name adf-hydroone-migration-test \
     --query identity.principalId -o tsv)

   az keyvault set-policy \
     --name kv-hydroone-test2 \
     --object-id "$ADF_MI" \
     --secret-permissions get list
   ```
2. For RBAC model:
   ```bash
   az role assignment create \
     --assignee "$ADF_MI" \
     --role "Key Vault Secrets User" \
     --scope "/subscriptions/671b1321-4407-420b-b877-97cd40ba898a/resourceGroups/rg-hydroone-migration-test/providers/Microsoft.KeyVault/vaults/kv-hydroone-test2"
   ```

**Prevention**
- Include Key Vault access in deployment templates alongside ADF provisioning.

---

### 11. ADF "circular reference not allowed"

**Symptom**
```
Pipeline validation error: "Circular reference not allowed in pipeline 'PL_Migrate_Single_Library'."
```

**Root Cause**
ADF does not allow a pipeline to call itself via ExecutePipeline. This happens when attempting recursive folder traversal (a pipeline that lists children and calls itself for subfolders).

**Resolution**
Use separate, purpose-built pipelines instead of recursion:

| Pipeline | Purpose |
|---|---|
| `PL_Migrate_Single_Library` | Top-level library enumeration |
| `PL_Process_Subfolder` | Handles one level of subfolder children |
| `PL_Copy_File_Batch` | Copies a batch of files (called by both above) |

For deep folder structures, `PL_Process_Subfolder` can call itself **only if it is a different pipeline**. If the folder depth exceeds what the pipeline chain supports, flatten the Graph API query:
```
GET /v1.0/drives/{driveId}/root/search(q='*')
```
This returns all items in the drive regardless of depth.

**Prevention**
- Design pipelines with explicit parent-child relationships, never self-referencing.
- Document the maximum supported folder depth in the runbook.

---

### 12. ADF "Container activity cannot include another container activity"

**Symptom**
```
Pipeline validation error: "Container activity 'Until_HasMorePages' cannot include
another container activity 'ForEach_Files'."
```

**Root Cause**
ADF Until loops cannot directly contain ForEach, IfCondition, or Switch activities. Only simple activities (Web, SetVariable, etc.) and ExecutePipeline are allowed inside Until.

**Resolution**
Extract the ForEach into a child pipeline and call it via ExecutePipeline from within the Until loop:

**Before (invalid):**
```
Until (HasMorePages)
  └── Web: GetPage
  └── ForEach: CopyFiles      <-- NOT ALLOWED
  └── SetVariable: NextLink
```

**After (valid):**
```
Until (HasMorePages)
  └── Web: GetPage
  └── ExecutePipeline: PL_Copy_File_Batch   <-- Calls child pipeline
  └── SetVariable: NextLink

PL_Copy_File_Batch (child pipeline):
  └── ForEach: CopyFiles
```

Pass the file list as a pipeline parameter (type: Array) to the child pipeline.

**Prevention**
- Always use ExecutePipeline to wrap container activities inside Until loops.
- This constraint is documented in the ADF architecture notes.

---

### 13. ADF ForEach Inside IfCondition

**Symptom**
```
Pipeline validation error: "ForEach activity is not allowed under an If Condition Activity."
```

**Root Cause**
ADF does not permit ForEach activities nested inside IfCondition True/False branches.

**Resolution**
Remove the IfCondition wrapper. ForEach handles empty arrays gracefully (zero iterations), so the guard condition is unnecessary:

**Before (invalid):**
```
IfCondition: @greater(length(variables('FileList')), 0)
  True:
    └── ForEach: CopyFiles    <-- NOT ALLOWED inside If
```

**After (valid):**
```
ForEach: CopyFiles            <-- Runs 0 times if FileList is empty
  items: @variables('FileList')
```

If you genuinely need conditional logic before a ForEach, use `ExecutePipeline` inside the IfCondition and put the ForEach in the child pipeline.

**Prevention**
- Rely on ForEach's native empty-array handling instead of If guards.

---

### 14. ADF Self-Referencing Variable

**Symptom**
```
Pipeline validation error: "The expression contains self referencing variable 'NextLink'."
```

**Root Cause**
ADF SetVariable cannot reference the same variable it is setting. For example:
```
SetVariable: NextLink
Value: @if(empty(body.nextLink), variables('NextLink'), body.nextLink)
                                 ^^^^^^^^^^^^^^^^^^^^^ SELF-REFERENCE
```

**Resolution**
Replace the self-reference with a safe fallback value. When the Until loop will exit on the same condition, the fallback value does not matter:
```
SetVariable: NextLink
Value: @if(contains(activity('GetPage').output, '@odata.nextLink'),
           activity('GetPage').output['@odata.nextLink'],
           '')
```
Use `''` (empty string) instead of `variables('NextLink')`. The Until loop condition `@not(empty(variables('NextLink')))` will cause the loop to exit when NextLink is empty, so the fallback is never consumed by subsequent iterations.

**Prevention**
- Never reference a variable inside its own SetVariable activity.
- Use empty string or a sentinel value as the else-branch fallback.

---

### 15. Token Expiration During Long-Running Migrations

**Symptom**
- Pipeline succeeds for the first ~45 minutes, then starts returning HTTP 401 errors.
- The token was acquired once at the start but is reused across paginated loops.

**Root Cause**
Azure AD access tokens have a default lifetime of 60-75 minutes. Long-running Until loops that process thousands of files can exceed this window.

**Resolution**
1. Move the token acquisition Web activity **inside** the Until loop so a fresh token is obtained for each page:
   ```
   Until (HasMorePages)
     └── Web: GetToken           <-- Refresh every iteration
     └── Web: GetPage
     └── ExecutePipeline: PL_Copy_File_Batch
     └── SetVariable: NextLink
   ```
2. Azure AD caches tokens server-side, so requesting a new token within the validity window returns the cached token with no extra latency. There is no penalty for refreshing every iteration.

**Prevention**
- Always acquire tokens inside the innermost loop, never at the pipeline level.
- This pattern is already implemented in PL_Migrate_Single_Library and PL_Process_Subfolder.

---

### 16. Pipeline Timeout

**Symptom**
```
ErrorCode: PipelineTimedOut
"Pipeline 'PL_Master_Migration_Orchestrator' exceeded the timeout of '1.00:00:00'."
```

**Root Cause**
- The default ADF pipeline timeout is 1 day (24 hours).
- Very large libraries with hundreds of thousands of files can exceed this.
- Throttling (HTTP 429) can slow processing enough to hit the timeout.

**Resolution**
1. Increase the pipeline timeout (maximum 30 days):
   ```json
   {
     "properties": {
       "timeout": "7.00:00:00"
     }
   }
   ```
2. Break large libraries into smaller batches using the control table:
   ```sql
   -- Split a large library into path-based batches
   UPDATE dbo.MigrationControlTable
   SET BatchGroup = 'Batch1'
   WHERE LibraryName = 'LargeDocLib' AND SubfolderPath LIKE '/A%';

   UPDATE dbo.MigrationControlTable
   SET BatchGroup = 'Batch2'
   WHERE LibraryName = 'LargeDocLib' AND SubfolderPath LIKE '/B%';
   ```
3. Check for throttling as the underlying cause (see [Section 4](#4-http-429-throttled)).

**Prevention**
- Monitor pipeline duration trends; if approaching 20 hours, split the workload.
- Use PL_Incremental_Sync for ongoing sync rather than full re-migration.

---

### 17. File Locked / Checked Out

**Symptom**
```json
{
  "error": {
    "code": "resourceLocked",
    "message": "The file is currently checked out or locked for editing by another user."
  }
}
```
Or the Graph API returns a 423 Locked status.

**Root Cause**
- A user has the file checked out in SharePoint.
- A co-authoring session is active on the file.
- A retention policy or legal hold is preventing access.

**Resolution**
1. Identify the locked file from the audit log:
   ```sql
   SELECT FileName, FilePath, ErrorMessage, LastAttemptTime
   FROM dbo.MigrationAuditLog
   WHERE Status = 'Failed'
     AND ErrorMessage LIKE '%locked%' OR ErrorMessage LIKE '%checked out%'
   ORDER BY LastAttemptTime DESC;
   ```
2. Contact the file owner to check the file back in, or use SharePoint admin to force check-in:
   ```
   SharePoint Admin Center > Sites > [Site] > Content > [Library] > ... > Check In
   ```
3. Re-run the pipeline; PL_Incremental_Sync will pick up previously failed files.

**Prevention**
- Communicate a freeze window to users before migration runs.
- Schedule migrations during off-hours to minimize lock conflicts.

---

## Diagnostic Queries

Run these against the SQL database `sql-hydroone-migration-test` to identify and analyze issues.

### Throttling Analysis

```sql
-- Throttling events by hour (last 7 days)
SELECT
    CAST(StartTime AS DATE) AS RunDate,
    DATEPART(HOUR, StartTime) AS HourOfDay,
    COUNT(*) AS ThrottleCount,
    AVG(RetryCount) AS AvgRetries
FROM dbo.MigrationAuditLog
WHERE (Status = 'Throttled' OR ErrorMessage LIKE '%429%')
  AND StartTime >= DATEADD(DAY, -7, GETUTCDATE())
GROUP BY CAST(StartTime AS DATE), DATEPART(HOUR, StartTime)
ORDER BY RunDate DESC, HourOfDay;
```

### Failed Files Summary

```sql
-- All failed files with error details
SELECT
    LibraryName,
    FilePath,
    FileName,
    FileSize,
    Status,
    ErrorMessage,
    RetryCount,
    LastAttemptTime
FROM dbo.MigrationAuditLog
WHERE Status = 'Failed'
ORDER BY LastAttemptTime DESC;
```

### Retry Count Distribution

```sql
-- Files that required multiple retries
SELECT
    RetryCount,
    COUNT(*) AS FileCount,
    SUM(FileSize) / (1024.0 * 1024.0) AS TotalSizeMB
FROM dbo.MigrationAuditLog
WHERE RetryCount > 0
GROUP BY RetryCount
ORDER BY RetryCount;
```

### Migration Progress by Library

```sql
-- Current migration status per library
SELECT
    LibraryName,
    COUNT(*) AS TotalFiles,
    SUM(CASE WHEN Status = 'Success' THEN 1 ELSE 0 END) AS Succeeded,
    SUM(CASE WHEN Status = 'Failed' THEN 1 ELSE 0 END) AS Failed,
    SUM(CASE WHEN Status = 'InProgress' THEN 1 ELSE 0 END) AS InProgress,
    CAST(100.0 * SUM(CASE WHEN Status = 'Success' THEN 1 ELSE 0 END) / COUNT(*) AS DECIMAL(5,2)) AS PctComplete
FROM dbo.MigrationAuditLog
GROUP BY LibraryName
ORDER BY LibraryName;
```

### Stale / Stuck Files

```sql
-- Files stuck in 'InProgress' for over 2 hours
SELECT FileName, FilePath, LibraryName, StartTime,
       DATEDIFF(MINUTE, StartTime, GETUTCDATE()) AS MinutesElapsed
FROM dbo.MigrationAuditLog
WHERE Status = 'InProgress'
  AND StartTime < DATEADD(HOUR, -2, GETUTCDATE())
ORDER BY StartTime;
```

---

## ADF Monitor Navigation

Follow these steps to locate error details in Azure Data Factory Monitor.

### Finding a Failed Pipeline Run

1. Open **ADF Studio** > **Monitor** > **Pipeline runs**.
2. Filter by:
   - **Pipeline name**: `PL_Master_Migration_Orchestrator` (or the specific pipeline)
   - **Status**: `Failed`
   - **Time range**: Adjust to cover the failure window.
3. Click the pipeline run to open **Activity runs**.

### Drilling Into Activity Errors

1. In the **Activity runs** view, find the failed activity (red icon).
2. Click the **error icon** (exclamation mark) to see the error message.
3. Click the **output icon** (document) to see the full JSON output, including HTTP response bodies.
4. Click the **input icon** (arrow) to see what was sent (useful for verifying URLs and headers).

### Navigating Child Pipeline Runs

For errors in `PL_Copy_File_Batch` (called via ExecutePipeline):

1. In the parent pipeline's Activity runs, find the `ExecutePipeline` activity.
2. Click the **pipeline run link** in the output column (looks like a hyperlink with a run ID).
3. This opens the child pipeline's Activity runs, where you can see the ForEach iterations.
4. Within the ForEach, click individual iterations to find which specific file copy failed.

### Quick Filters

| What you want | Filter |
|---|---|
| All failures today | Status = Failed, Last 24 hours |
| Specific library | Search pipeline parameters for the library name |
| Throttling events | Search activity output for "429" or "Retry-After" |
| Token errors | Search activity output for "401" or "InvalidAuthenticationToken" |

---

## Log Collection

Before escalating an issue, gather the following information.

### Required Information

| Item | How to Get It |
|---|---|
| **ADF Pipeline Run ID** | Monitor > Pipeline runs > copy the Run ID (GUID) |
| **ADF Activity Run ID** | Monitor > Activity runs > copy the Run ID for the failed activity |
| **Timestamp (UTC)** | Note the exact UTC time of the failure |
| **Error message** | Copy the full error JSON from the activity output |
| **HTTP response code** | From the activity output `statusCode` field |
| **HTTP response body** | From the activity output `body` or `error` field |
| **Graph API request URL** | From the activity input `url` field |
| **SQL audit log entries** | Run the Failed Files query above, filtered by timestamp |

### Collecting ADF Run Details via CLI

```bash
# Get failed pipeline runs from the last 24 hours
az datafactory pipeline-run query-by-factory \
  --resource-group rg-hydroone-migration-test \
  --factory-name adf-hydroone-migration-test \
  --last-updated-after "$(date -u -d '-1 day' '+%Y-%m-%dT%H:%M:%SZ')" \
  --last-updated-before "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
  --filters operand="Status" operator="Equals" values="Failed"
```

### Collecting Graph API Error Details

If you can reproduce the error, capture the full request and response:

```bash
# Test Graph API call directly
curl -v -H "Authorization: Bearer <token>" \
  "https://graph.microsoft.com/v1.0/drives/<driveId>/root/children" \
  2>&1 | tee graph-debug.log
```

Include the `request-id` and `Date` response headers in any Microsoft support ticket.

---

### 18. Populate-ControlTable.ps1 Errors

These errors occur when running the `Populate-ControlTable.ps1` script to enumerate SharePoint sites/libraries and populate the SQL control table.

#### 18a. SQL Firewall: "Client with IP address 'x.x.x.x' is not allowed to access the server"

**Symptom:** SQL pre-flight check fails at Step 2 (TCP connectivity) or Step 3 (authentication).

**Root Cause:** Azure SQL Server firewall does not have a rule for your client IP.

**Resolution:**
```bash
az sql server firewall-rule create \
    --name "AllowMyIP" \
    --server <sql-server-name> \
    --resource-group <resource-group> \
    --start-ip-address <YOUR_IP> \
    --end-ip-address <YOUR_IP>
```

#### 18b. ADFS Authentication: "Failed to authenticate the user NT Authority\Anonymous Logon in Active Directory"

**Symptom:** SQL pre-flight Step 3 fails. Error code `0xparsing_wstrust_response_failed`.

**Root Cause:** The environment uses ADFS/federated authentication, which is incompatible with `ActiveDirectoryIntegrated` SQL auth mode.

**Resolution:** Use SQL authentication instead:
```powershell
-SqlUsername "sqladmin" -SqlPassword (ConvertTo-SecureString "YourPassword" -AsPlainText -Force)
```

#### 18c. SharePoint 404: "The remote server returned an error: (404) Not Found"

**Symptom:** PnP connection fails when connecting to the SharePoint admin center.

**Root Cause:** Either:
1. A full site URL (e.g. `https://tenant.sharepoint.com/sites/MySite`) was passed as `-SharePointTenantUrl` instead of just the tenant root
2. The app registration does not have SharePoint admin center access

**Resolution:**
- Pass only the tenant root as `-SharePointTenantUrl` (e.g. `https://hydroone.sharepoint.com`)
- Use `-SpecificSites @("/sites/MySite")` to target specific sites and bypass admin center enumeration

#### 18d. SQL DNS: "No such host is known"

**Symptom:** SQL pre-flight Step 1 (DNS) or Step 2 (TCP) fails.

**Root Cause:** Wrong SQL server name.

**Resolution:**
```bash
nslookup <server-name>.database.windows.net
# If this fails, verify the server name in Azure Portal > SQL servers
```

#### 18e. SharePoint 403: "The remote server returned an error: (403) Forbidden"

**Symptom:** PnP PowerShell connection or site enumeration fails.

**Root Cause:** Admin consent not granted for `Sites.Read.All` on the app registration.

**Resolution:** Follow Step 3 in the README — a Global Administrator must grant admin consent in Azure Portal.

#### 18f. "MigrationControl table does not exist"

**Symptom:** SQL pre-flight Step 4 fails.

**Root Cause:** DDL scripts have not been run against the database.

**Resolution:** Run Step 5 from the README:
```bash
sqlcmd -S <server>.database.windows.net -d MigrationControl -i sql/create_control_table.sql -G
```

#### 18g. Log File Location

Every run of `Populate-ControlTable.ps1` creates a timestamped log file in the script directory:
```
Populate-ControlTable_YYYYMMDD_HHmmss.log
```

The log contains full environment diagnostics, SQL pre-flight results, per-site/library details, and exception stack traces. Always include this log file when reporting issues.

---

## Escalation Path

| Issue Type | First Contact | Escalation |
|---|---|---|
| **Graph API errors (401, 403, 429, 503)** | Check this guide first | Microsoft Support (Graph API category) |
| **SharePoint file access / permissions** | SharePoint admin (Hydro One IT) | Microsoft Support (SharePoint Online) |
| **ADF pipeline design / failures** | This guide + ADF documentation | Microsoft Support (Azure Data Factory) |
| **ADLS storage write errors** | Check RBAC and firewall (this guide) | Microsoft Support (Azure Storage) |
| **SQL connectivity** | Check firewall rules (this guide) | Microsoft Support (Azure SQL) |
| **Key Vault access** | Check access policies (this guide) | Microsoft Support (Azure Key Vault) |
| **Performance / throttling** | Reduce concurrency, off-peak scheduling | Microsoft Support (Graph API + SharePoint) |
| **Data integrity / missing files** | Run PL_Post_Migration_Validation | Project team review |

### When Filing a Microsoft Support Ticket

Include:
1. **Subscription ID**: `671b1321-4407-420b-b877-97cd40ba898a` (test)
2. **Resource group**: `rg-hydroone-migration-test`
3. **Affected resource**: Specific resource name from above
4. **Timestamps**: UTC times of the issue
5. **Request IDs**: Graph API `request-id` headers or ADF Run IDs
6. **Reproduction steps**: Exact API call or pipeline configuration

> **Note**: All resource names, subscription IDs, and tenant information above are for the **test environment**.
> Production values will be provided separately and must be substituted before use in production troubleshooting.
