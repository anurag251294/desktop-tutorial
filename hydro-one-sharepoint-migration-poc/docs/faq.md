# Hydro One SharePoint Migration - Frequently Asked Questions

This document answers the most common questions about the SharePoint Online to ADLS Gen2
migration solution. It is organized by category for quick reference.

---

## General

### What does this solution do?

It migrates document libraries from SharePoint Online to Azure Data Lake Storage Gen2.
Files are copied as-is (binary copy) from SharePoint into a structured folder hierarchy
in ADLS, preserving the original folder structure. The migration is driven by Azure Data
Factory pipelines that use the Microsoft Graph API to enumerate and download files.

### How much data are we migrating?

The scope is defined by the `MigrationControl` SQL table, which lists every site and
document library to be migrated. The POC validated approximately 5,000 files across three
libraries. Production volume will depend on the final library inventory from Hydro One.

### How long will the migration take?

The estimated timeline is approximately 10 weeks end-to-end:

- **Weeks 1-2**: Environment setup, app registration, Key Vault configuration, control
  table population.
- **Weeks 3-6**: Bulk migration (~10-14 days of active pipeline execution, depending on
  total data volume and Graph API throttling).
- **Weeks 7-8**: Incremental sync to capture changes made during the bulk migration window.
- **Weeks 9-10**: Post-migration validation, remediation of failed files, final sign-off.

Actual bulk migration throughput depends on file sizes, Graph API throttling, and ADF
integration runtime capacity.

### What file types are supported?

All file types are supported. The solution performs a binary copy — it reads the file bytes
from SharePoint via the Graph `/content` endpoint and writes them directly to ADLS. The
file content is never parsed, transformed, or interpreted. DOCX, XLSX, PDF, images, ZIP
archives, CAD files, and any other format will transfer correctly.

### Is the source data modified during migration?

No. The service principal has read-only permissions (`Sites.Read.All`, `Files.Read.All`).
The solution does not write to, delete from, or modify any content in SharePoint. Source
document libraries remain fully accessible to users throughout the migration.

---

## During Migration

### What happens if a file is checked out in SharePoint?

If a file is exclusively locked (checked out), the Graph API `/content` endpoint may return
a `423 Locked` or `409 Conflict` error. The Copy activity will fail for that specific file.
The error is logged to the `MigrationAuditLog` SQL table with the file path and error
details. The file will be retried in the next incremental sync batch. If it remains locked,
it will appear in the remediation report for manual follow-up.

### What happens if someone deletes a file during migration?

If a file is deleted between the enumeration (delta query) and the download attempt, the
Graph API will return a `404 Not Found` error. The pipeline logs this to the audit table
and skips the file. The file will not be re-created in ADLS. If the file was already
copied in a previous batch, the existing copy in ADLS is not affected.

### What happens if someone adds a file during migration?

New files added after the initial delta enumeration will be captured by the incremental
sync pipeline (`PL_Incremental_Sync`). This pipeline uses the `deltaLink` persisted from
the initial enumeration to request only items that have changed since the last sync. New
files appear as "created" items in the delta response and are copied to ADLS.

### What happens if the migration fails mid-batch?

Files that were successfully copied before the failure are already in ADLS and do not need
to be re-copied. The failed file and any remaining files in the batch are logged with error
details in the `MigrationAuditLog`. The library's status is set to `Failed` in the
`MigrationControl` table. To retry, reset the library status to `Pending` and re-trigger
the master pipeline — the delta query will pick up where it left off.

### How do I pause the migration?

1. **Stop triggers**: In ADF, navigate to Manage > Triggers and disable the migration
   trigger.
2. **Cancel running pipelines**: In ADF Monitor, select any running pipeline instances and
   click Cancel. Child pipelines (`PL_Copy_File_Batch`) will also be cancelled.
3. Files already copied to ADLS are safe and will not be affected.

### How do I resume after a pause?

1. In the `MigrationControl` SQL table, update any libraries with `Status = 'Failed'`
   back to `Status = 'Pending'` and reset `RetryCount = 0`.
2. Libraries with `Status = 'Completed'` will be skipped automatically.
3. Re-enable the ADF trigger, or manually trigger `PL_Master_Migration_Orchestrator`.
4. The pipeline reads the control table and processes only `Pending` libraries.

### What does a normal pipeline run look like in ADF Monitor?

A typical run of `PL_Master_Migration_Orchestrator` shows:

1. **Lookup** activity: Reads the control table for libraries with `Pending` status.
2. **ForEach** activity: Iterates over each library.
3. Inside ForEach, **ExecutePipeline** calls `PL_Migrate_Single_Library` for each library.
4. Inside the child pipeline, you will see an **Until** loop with multiple iterations:
   - `Refresh_AccessToken` (WebActivity) — runs every iteration, this is normal.
   - `Get_Delta_Page` (WebActivity) — calls the Graph delta endpoint.
   - `Set_HasMorePages` (SetVariable) — determines if pagination continues.
   - `Execute_PL_Copy_File_Batch` (ExecutePipeline) — copies the current page of files.
5. Each `PL_Copy_File_Batch` run shows a **ForEach** iterating over individual files, with
   a **Copy** activity and **Stored Procedure** call (audit log) for each file.

---

## Operations

### How do I add a new site or library to migrate?

Option A: Insert directly into the `MigrationControl` SQL table:

```sql
INSERT INTO dbo.MigrationControl (SiteUrl, LibraryName, DriveId, Status)
VALUES ('https://tenant.sharepoint.com/sites/NewSite', 'Documents', '<driveId>', 'Pending');
```

Option B: Re-run the `Populate-ControlTable.ps1` script, which enumerates all sites and
libraries via PnP PowerShell and upserts any that are not already in the table:

```powershell
.\scripts\Populate-ControlTable.ps1 `
    -SharePointTenantUrl "https://hydroone.sharepoint.com" `
    -ClientId "<your-app-client-id>" `
    -SpecificSites @("/sites/NewSite") `
    -SqlServerName "sql-hydroone-migration-dev" `
    -SqlDatabaseName "MigrationControl" `
    -SqlUsername "sqladmin" `
    -SqlPassword (ConvertTo-SecureString "YourPassword" -AsPlainText -Force)
```

For full parameter reference, see `docs/scripts-reference.md` Section 4 or `README.md` Step 8.

### How do I re-run a failed library?

```sql
UPDATE dbo.MigrationControl
SET Status = 'Pending', RetryCount = 0, LastError = NULL
WHERE LibraryName = 'FailedLibraryName' AND SiteUrl = 'https://...';
```

Then re-trigger `PL_Master_Migration_Orchestrator`. It will pick up the library because its
status is now `Pending`.

### How do I skip a library?

```sql
UPDATE dbo.MigrationControl
SET Status = 'Skipped'
WHERE LibraryName = 'LibraryToSkip' AND SiteUrl = 'https://...';
```

The master pipeline only processes libraries with `Status = 'Pending'`, so skipped libraries
are ignored.

### How do I check migration progress?

- **ADF Monitor**: Navigate to Monitor > Pipeline runs. Filter by pipeline name to see
  active, succeeded, and failed runs.
- **PowerShell**: Run `Monitor-Migration.ps1`, which queries the control table and displays
  a summary of Pending, InProgress, Completed, Failed, and Skipped libraries.
- **SQL**: Use the queries in `migration_progress_queries.sql` for detailed breakdowns,
  such as files per library, total bytes transferred, and error summaries.

### How do I check if a specific file was migrated?

Query the `MigrationAuditLog` table:

```sql
SELECT *
FROM dbo.MigrationAuditLog
WHERE FileName = 'example.docx'
   OR SourcePath LIKE '%/path/to/file%'
ORDER BY CopyTimestamp DESC;
```

The audit log records every file copy attempt, including the source path, destination path,
status (Success/Failed), file size, and any error message.

### What does incremental sync look like when there are no changes?

The `PL_Incremental_Sync` pipeline calls the delta endpoint with the stored `deltaLink`.
If no files have changed since the last sync, Graph returns an empty `value` array with a
new `deltaLink`. The Until loop completes after one iteration with 0 files processed. The
pipeline succeeds with all activities showing green. This is completely normal behavior.

---

## Security & Access

### What permissions does the Service Principal need?

The app registration requires the following Microsoft Graph **Application** permissions
(not Delegated):

| Permission | Type | Purpose |
|------------|------|---------|
| `Sites.Read.All` | Application | Enumerate sites and document libraries |
| `Files.Read.All` | Application | Read and download file content |

These are read-only permissions. The service principal cannot modify, delete, or create
content in SharePoint.

### Who needs to grant admin consent?

A **Global Administrator** (or Application Administrator) in the SharePoint tenant must
grant admin consent for the application permissions. This is a one-time action performed
in the Azure portal under Enterprise Applications > the app > Permissions > Grant admin
consent.

### Can the migration access OneDrive files?

Not in the current scope. The migration targets SharePoint Online document libraries only.
OneDrive for Business (personal sites under `/personal/`) are excluded by the control table
filter. The service principal permissions would technically allow access to OneDrive files,
but the pipeline only processes entries in the `MigrationControl` table.

### What if the client secret expires?

1. Generate a new client secret in the app registration (SharePoint tenant Azure portal).
2. Update the secret value in Azure Key Vault (`kv-hydroone-test2`) in the MCAPS tenant.
3. No pipeline changes are needed — ADF retrieves the secret from Key Vault at runtime.
4. Verify by triggering a test pipeline run.

Secret expiration dates should be monitored. Set a Key Vault expiration alert or calendar
reminder at least 30 days before expiry.

---

## Troubleshooting

### Where do I find error details?

Errors are available in two places:

1. **ADF Monitor**: Navigate to Monitor > Pipeline runs > click the failed run > Activity
   runs. Click the error icon on the failed activity to see the full error output, including
   HTTP status codes and response bodies from Graph API.
2. **SQL audit table**: Query `dbo.MigrationAuditLog` for rows where `Status = 'Failed'`.
   The `ErrorMessage` column contains the error details captured by the pipeline.

### Why do I see Refresh_AccessToken running on every loop iteration?

This is expected behavior. See ADR-4 (Always-Refresh Token Strategy) in
`architecture-decisions.md`. ADF's Until loop cannot contain an IfCondition activity to
conditionally refresh the token, so the pipeline refreshes on every iteration. AAD caches
tokens server-side, so the overhead is approximately 500ms per call. This eliminates any
risk of token expiration during long-running migrations.

### Why is PL_Copy_File_Batch a separate pipeline?

This is a workaround for an ADF platform limitation. ADF's Until activity cannot contain
container activities (ForEach, IfCondition, Switch) as direct children. The only way to
execute a ForEach inside an Until loop is to wrap it in a child pipeline and invoke it via
ExecutePipeline. See ADR-3 (Child Pipeline Pattern) in `architecture-decisions.md` for full
details.

### Why do some files show as Failed but the library shows as Completed?

The library status is set to `Completed` when the pagination loop finishes without a fatal
pipeline error. Individual file failures (e.g., 404, 423, or transient network errors) are
logged to the audit table but do not halt the pipeline. Review the `MigrationAuditLog` for
failed files and decide whether to retry (re-run incremental sync) or handle them manually.

### Where can I find more detailed error patterns and resolutions?

See `debugging.md` in the `docs/` directory for a comprehensive catalog of error patterns
encountered during the POC, including HTTP status codes, ADF error messages, and
step-by-step resolution procedures.

### Populate-ControlTable.ps1 fails with "Failed to authenticate NT Authority\Anonymous Logon"

This happens in ADFS/federated authentication environments where Azure AD Integrated SQL auth
is not supported. Use SQL authentication instead by adding `-SqlUsername` and `-SqlPassword`:

```powershell
-SqlUsername "sqladmin" -SqlPassword (ConvertTo-SecureString "YourPassword" -AsPlainText -Force)
```

### Populate-ControlTable.ps1 fails with "Client with IP address is not allowed"

Your client machine's IP is not in the Azure SQL Server firewall rules. Add it:

```bash
az sql server firewall-rule create \
    --name "AllowMyIP" --server <sql-server-name> --resource-group <rg-name> \
    --start-ip-address <YOUR_IP> --end-ip-address <YOUR_IP>
```

### Populate-ControlTable.ps1 fails with "(404) Not Found"

This usually means a full site URL (e.g. `https://tenant.sharepoint.com/sites/MySite`) was
passed as `-SharePointTenantUrl`. Only pass the tenant root URL. Use `-SpecificSites` for
site paths:

```powershell
-SharePointTenantUrl "https://hydroone.sharepoint.com" `
-SpecificSites @("/sites/MySite")
```

### Where is the Populate-ControlTable.ps1 log file?

Every run writes a timestamped log in the script directory: `Populate-ControlTable_YYYYMMDD_HHmmss.log`.
The log includes full environment diagnostics, SQL pre-flight results, per-site/library details,
and exception stack traces. Always include this log when reporting issues.

---

## Additional Resources

- `architecture-decisions.md` — Detailed ADRs for all key technical decisions
- `pipeline-documentation.md` — Pipeline-by-pipeline documentation with parameters
- `deployment-guide.md` — Step-by-step environment setup instructions
- `runbook.md` — Operational procedures for running and monitoring the migration
- `debugging.md` — Error patterns and resolution procedures
- `migration-plan.md` — High-level project plan and timeline
