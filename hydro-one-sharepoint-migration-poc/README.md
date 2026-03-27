# Hydro One SharePoint to Azure Data Lake Migration

## Overview

This solution migrates approximately **25 TB** of documents and files from **SharePoint Online** to **Azure Data Lake Storage Gen2 (ADLS Gen2)** using **Azure Data Factory (ADF)** as the orchestration engine. The migration is metadata-driven, fully audited, and supports both initial bulk migration and ongoing incremental synchronization.

All file access is handled through the **Microsoft Graph API** with cross-tenant OAuth2 authentication, enabling ADF (running in the MCAPS tenant) to securely read from Hydro One's SharePoint tenant and write to Azure storage.

### Why This Migration?

Hydro One's SharePoint Online environment is at storage capacity. This migration offloads ~25 TB of document library content to ADLS Gen2, providing scalable, cost-effective storage while maintaining full audit trails and the ability to keep data synchronized through incremental delta sync.

### POC Status

The proof-of-concept was **successfully validated on February 18, 2026**:

| Metric | Result |
|--------|--------|
| Files migrated | 30 |
| Data migrated | 7.96 MB |
| Duration | ~2 minutes 5 seconds |
| Failures | 0 |
| Source | SharePoint `/sites/SalesAndMarketing` / `Shared Documents` |
| Destination | ADLS `sharepoint-migration/SalesAndMarketing/Shared Documents/` |
| File formats | `.docx`, `.pptx`, `.xlsx`, `.jpg`, `.png` |

All production features (delta query pagination, deep folder traversal, token refresh, child pipeline pattern, SQL audit logging, incremental sync with deltaLink persistence) were verified in this test.

---

## Solution Architecture

```
SharePoint Online (Source)                Azure Data Factory (Orchestration)
Hydro One Tenant                          MCAPS Tenant
+-------------------+   Graph API    +-------------------------+
| Site Collections  | <-----------> | PL_Master_Orchestrator  |
| Document Libraries|   (HTTPS)     |   PL_Migrate_Library    |
| ~25 TB of Files   |               |   PL_Copy_File_Batch    |
+-------------------+               |   PL_Incremental_Sync   |
                                    |   PL_Validation         |
                                    +-------+-------+---------+
                                            |       |
                          Managed Identity  |       |  Managed Identity
                                            v       v
                                    +-------+--+ +--+----------+
                                    | ADLS Gen2| | Azure SQL   |
                                    | (Dest.)  | | (Control &  |
                                    | 25 TB    | |  Audit)     |
                                    +----------+ +------+------+
                                                        |
                                                 +------+------+
                                                 | Key Vault   |
                                                 | (Secrets)   |
                                                 +-------------+
```

### Cross-Tenant Authentication

This is a **cross-tenant** scenario. ADF runs in the MCAPS tenant, while SharePoint Online resides in a separate Hydro One tenant. Authentication works as follows:

1. **ADF** retrieves the Service Principal's client secret from **Azure Key Vault** (via Managed Identity)
2. **ADF** acquires an OAuth2 access token from the **SharePoint tenant's Azure AD** using the `client_credentials` grant with scope `https://graph.microsoft.com/.default`
3. **ADF** uses the Bearer token to call **Microsoft Graph API** endpoints for file enumeration and download
4. **ADF** writes files to **ADLS Gen2** and logs results to **Azure SQL** using its **Managed Identity**

### Why Microsoft Graph API (Not SharePoint REST API)

During POC development, we discovered that the SharePoint REST API (`/_api/web/...`) **does not accept** access tokens acquired via the Azure AD v2.0 client credentials flow. It returns an "Unsupported app only token" error. The Microsoft Graph API fully supports this modern authentication pattern and provides equivalent functionality for listing drives, enumerating files, and downloading content.

---

## Project Structure

```
hydro-one-sharepoint-migration-poc/
├── adf-templates/                  # Azure Data Factory ARM templates
│   ├── arm-template.json           # Master ARM template entry point
│   ├── linkedServices/             # 4 linked service definitions
│   │   ├── LS_HTTP_Graph_Download.json    # Graph API HTTP connector (Anonymous + Bearer token)
│   │   ├── LS_AzureBlobStorage.json       # ADLS Gen2 sink (Managed Identity)
│   │   ├── LS_AzureSqlDatabase.json       # SQL control/audit tables (Managed Identity)
│   │   └── LS_KeyVault.json               # Key Vault for secrets (Managed Identity)
│   ├── datasets/                   # 3 dataset definitions
│   │   ├── DS_Graph_Content_Download.json # Binary download from Graph /content endpoint
│   │   ├── DS_ADLS_Sink.json              # Binary write to ADLS Gen2
│   │   └── DS_SQL_ControlTables.json      # SQL table access
│   ├── pipelines/                  # 6 pipeline definitions
│   │   ├── PL_Master_Migration_Orchestrator.json
│   │   ├── PL_Migrate_Single_Library.json
│   │   ├── PL_Copy_File_Batch.json
│   │   ├── PL_Process_Subfolder.json
│   │   ├── PL_Incremental_Sync.json
│   │   └── PL_Validation.json
│   └── triggers/
│       └── TR_Triggers.json
├── sql/                            # SQL DDL and operational queries
│   ├── create_control_table.sql    # MigrationControl, IncrementalWatermark, BatchLog, SyncLog tables
│   ├── create_audit_log_table.sql  # MigrationAuditLog, ValidationLog tables + stored procedures
│   └── migration_progress_queries.sql  # 25+ monitoring and dashboard queries
├── scripts/                        # PowerShell and Bash automation
│   ├── Setup-AzureResources.ps1    # Provisions RG, ADF, ADLS, SQL, Key Vault with RBAC
│   ├── Register-SharePointApp.ps1  # Creates Service Principal in SharePoint tenant
│   ├── Populate-ControlTable.ps1   # Enumerates SharePoint sites/libraries into SQL control table
│   ├── Deploy-ADF-Templates.sh     # ARM template deployment via Azure CLI
│   ├── Monitor-Migration.ps1       # Real-time migration progress dashboard
│   └── Validate-Migration.ps1      # Post-migration file count/size validation
├── terraform/                      # Infrastructure-as-Code for private networking
│   ├── main.tf                     # Provider config and data sources
│   ├── variables.tf                # Input variables
│   ├── outputs.tf                  # Output values (private endpoint IPs, DNS)
│   ├── network.tf                  # VNet and subnet definitions
│   ├── adf-managed-vnet.tf         # ADF managed virtual network
│   ├── private-endpoints.tf        # Private endpoints for Storage, SQL, Key Vault
│   ├── dns-zones.tf                # Private DNS zone configuration
│   └── terraform.tfvars            # Environment-specific variable values
├── config/                         # Environment-specific ARM template parameters
│   ├── parameters.dev.json
│   └── parameters.prod.json
├── docs/                           # Detailed technical documentation
│   ├── architecture.md             # Solution architecture deep-dive with Mermaid diagrams
│   ├── deployment-guide.md         # 10-phase step-by-step deployment guide
│   ├── runbook.md                  # Operational runbook with troubleshooting
│   ├── migration-plan.md           # Phased migration plan with timeline and risk register
│   └── pipeline-documentation.md   # Technical reference for all pipelines, datasets, and scripts
├── _archived/                      # Deprecated earlier iterations (for reference only)
└── README.md                       # This file
```

---

## Pipeline Architecture

The migration is orchestrated through **6 ADF pipelines** that work together in a hierarchical pattern:

```
PL_Master_Migration_Orchestrator            (Entry point: reads control table, iterates libraries)
    │
    └── ForEach Library (4 concurrent)
         │
         └── PL_Migrate_Single_Library      (Per-library: delta query, paginated Until loop)
              │
              └── Until_AllPagesProcessed    (Pagination loop with flat activities only)
                   │
                   └── PL_Copy_File_Batch    (Child pipeline: ForEach file copy + audit logging)

PL_Incremental_Sync                         (Delta sync using stored deltaLink)
    │
    └── PL_Copy_File_Batch

PL_Process_Subfolder                        (Standalone subfolder utility)
    │
    └── PL_Copy_File_Batch

PL_Validation                               (Post-migration file count/size comparison)
```

### Pipeline Descriptions

| # | Pipeline | Purpose |
|---|----------|---------|
| 1 | **PL_Master_Migration_Orchestrator** | Entry point. Reads pending libraries from the SQL control table and iterates through them in parallel batches of 4. Calls `PL_Migrate_Single_Library` for each library. |
| 2 | **PL_Migrate_Single_Library** | Core migration pipeline. Acquires an OAuth2 token, resolves the SharePoint library to a Graph API drive ID, then uses a delta query (`/root/delta`) to enumerate ALL files at ALL folder depths. Processes results in a paginated Until loop, calling `PL_Copy_File_Batch` for each page. Stores the `@odata.deltaLink` for incremental sync. |
| 3 | **PL_Copy_File_Batch** | Lightweight child pipeline. Contains a ForEach loop (10 concurrent) that downloads each file via Graph API `/content` endpoint and writes it to ADLS Gen2. Logs success or failure to the SQL audit table. This pipeline exists because ADF's Until activity cannot contain ForEach directly. |
| 4 | **PL_Process_Subfolder** | Processes subfolder children with pagination. Retained as a standalone utility, though the delta query approach in `PL_Migrate_Single_Library` eliminates the need for recursive subfolder traversal. |
| 5 | **PL_Incremental_Sync** | Runs a delta query using the stored `@odata.deltaLink` from the initial migration. Only copies changed or new files. Updates the watermark after completion. |
| 6 | **PL_Validation** | Post-migration validation. Compares file counts and sizes between SharePoint (source) and ADLS Gen2 (destination). Updates validation status in the control table. |

### Deployment Order

Pipelines must be deployed in dependency order (child before parent):

1. `PL_Copy_File_Batch` (no dependencies)
2. `PL_Process_Subfolder` (depends on `PL_Copy_File_Batch`)
3. `PL_Migrate_Single_Library` (depends on `PL_Copy_File_Batch`)
4. `PL_Incremental_Sync` (depends on `PL_Copy_File_Batch`)
5. `PL_Validation` (standalone)
6. `PL_Master_Migration_Orchestrator` (depends on `PL_Migrate_Single_Library`)

### Key Pipeline Parameters

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `PageSize` | 200 | Number of items per Graph API delta page (`$top`) |
| `CopyBatchCount` | 10 | Concurrent file copies within `PL_Copy_File_Batch` ForEach |
| `ThrottleDelaySeconds` | 2 | Wait time between pagination pages to avoid throttling |

---

## Azure Resources

All resources are deployed in **Canada Central** to comply with Canadian data residency requirements.

| Resource | Naming Pattern | Purpose |
|----------|----------------|---------|
| Resource Group | `rg-hydroone-migration-{env}` | Container for all migration resources |
| Azure Data Factory | `adf-hydroone-migration-{env}` | Pipeline orchestration engine |
| ADLS Gen2 Storage | `sthydroonemig{env}` | Destination storage (hierarchical namespace enabled) |
| Azure SQL Database | `sql-hydroone-migration-{env}` | Migration control table, audit logs, watermarks |
| Azure Key Vault | `kv-hydroone-mig-{env}` | Stores SharePoint Service Principal client secret |
| Azure AD App | `HydroOne-SPO-Migration` | Service Principal registered in the SharePoint tenant |

### ADLS Gen2 Folder Structure

Files are organized in ADLS to mirror the SharePoint site/library/folder hierarchy:

```
sharepoint-migration/                      (container)
├── SalesAndMarketing/                     (site name)
│   └── Shared Documents/                  (library name)
│       ├── Q1 Report.docx                 (root-level file)
│       ├── Branding Elements.pptx
│       └── Monthly Reports/               (subfolder preserved)
│           ├── Canada Sales.xlsx
│           └── Germany Sales.xlsx
├── Engineering/
│   └── Technical Docs/
│       └── ...
└── ...
```

### SQL Control and Audit Tables

| Table | Purpose |
|-------|---------|
| `MigrationControl` | Tracks every library to migrate: site URL, library name, status (Pending/InProgress/Completed/Failed), file counts, sizes, retry counts |
| `MigrationAuditLog` | Per-file audit trail: source path, destination path, file size, migration status, error codes, timestamps |
| `IncrementalWatermark` | Stores the `@odata.deltaLink` and last sync time per library for incremental sync |
| `BatchLog` | Batch execution tracking (libraries planned/completed/failed per batch) |
| `SyncLog` | Incremental sync run history |
| `ValidationLog` | Detailed validation results per library |

---

## Prerequisites

### Azure Subscription

- Active Azure subscription with **Contributor** access
- Sufficient quota:
  - Storage: **30 TB** capacity (25 TB data + 20% overhead)
  - SQL Database: **S1 tier** or higher
  - Data Factory: Pay-as-you-go
- Resource providers registered: `Microsoft.DataFactory`, `Microsoft.Storage`, `Microsoft.Sql`, `Microsoft.KeyVault`

### Azure AD Permissions

- **Application Administrator** or **Global Administrator** role in the SharePoint tenant for app registration
- **Global Administrator** or **Privileged Role Administrator** to grant admin consent for Graph API permissions — this is a **hard blocker** without which no migration pipeline will function

### SharePoint Online

- SharePoint Online Administrator role
- Access to all site collections being migrated
- Complete inventory of sites, libraries, and estimated sizes
- Identified exclusions (system libraries, OneDrive, etc.)

### Graph API Permissions (Application)

The Service Principal requires the following **application** permissions on Microsoft Graph, with **admin consent granted**:

| API | Permission | Type | Purpose |
|-----|-----------|------|---------|
| Microsoft Graph | `Sites.Read.All` | Application | Resolve sites and enumerate drives |
| Microsoft Graph | `Files.Read.All` | Application | Enumerate and download files |

> **Note:** SharePoint-specific permissions (e.g., `Sites.FullControl.All`) are **not** required. The Graph API application permissions above are sufficient for read-only migration.

### Managed Identity RBAC

The ADF System-Assigned Managed Identity requires:

| Resource | Role | Purpose |
|----------|------|---------|
| ADLS Gen2 Storage Account | Storage Blob Data Contributor | Read/write files to ADLS containers |
| Azure Key Vault | Key Vault Secrets User | Retrieve client ID, client secret, tenant ID |
| Azure SQL Database | db_datareader + db_datawriter + EXECUTE | Read/write control and audit tables |

### Tools Required

| Tool | Version | Purpose |
|------|---------|---------|
| Azure CLI | 2.50+ | Resource deployment and management |
| PowerShell | 7.0+ | Automation scripts |
| Az PowerShell Module | 10.0+ | Azure resource management |
| PnP.PowerShell | Latest | SharePoint site enumeration |
| SqlServer Module | Latest | SQL operations from PowerShell |
| SQL Server Management Studio | 19+ | Database management and queries |
| Git | 2.40+ | Source control |

### Network Requirements

- Outbound HTTPS (443) to `graph.microsoft.com` (Graph API)
- Outbound HTTPS (443) to `login.microsoftonline.com` (OAuth2 token endpoint)
- Outbound HTTPS (443) to `*.sharepoint.com` (Graph API-initiated downloads)
- Outbound HTTPS (443) to `*.azure.com`, `*.azure.net` (Azure services)
- Public network access enabled on Storage Account, SQL Server, and Key Vault (or private endpoints configured via Terraform)
- SQL Server firewall `AllowAzureServices` rule to permit ADF connections

---

## Deployment Steps

### Step 1: Provision Azure Resources

Run the setup script to create all required Azure resources with RBAC assignments:

```powershell
.\scripts\Setup-AzureResources.ps1 -Environment "dev" -Location "canadacentral"
```

This creates the Resource Group, ADF (with System-Assigned Managed Identity), ADLS Gen2 (with hierarchical namespace), Azure SQL Server and Database, and Key Vault. It also configures RBAC roles for the ADF Managed Identity.

### Step 2: Register the SharePoint App and Store Credentials

Register an Azure AD application in the **SharePoint tenant** and store its credentials in Key Vault:

```powershell
.\scripts\Register-SharePointApp.ps1 `
    -TenantId "<sharepoint-tenant-id>" `
    -KeyVaultName "kv-hydroone-mig-dev"
```

This creates the app registration with `Sites.Read.All` and `Files.Read.All` Graph API permissions, generates a client secret, and stores it in Key Vault.

### Step 3: Grant Admin Consent (CRITICAL -- Requires Global Administrator)

A **Global Administrator** in the SharePoint tenant must grant admin consent for the app's Graph API permissions. Without this, all Graph API calls will return HTTP 401/403 and no migration can proceed.

1. Sign in to [Azure Portal](https://portal.azure.com) as Global Administrator (in the SharePoint tenant)
2. Navigate to **Azure Active Directory** > **App registrations**
3. Select the migration app (e.g., `HydroOne-SPO-Migration`)
4. Click **API permissions**
5. Click **Grant admin consent for [tenant name]**
6. Confirm by clicking **Yes**
7. Verify all permissions show a green checkmark with status **"Granted"**

### Step 4: Enable Network Access

Ensure ADF can reach all resources. For the POC environment, enable public network access:

```bash
# Storage Account
az storage account update \
    --name sthydroonemigdev \
    --resource-group rg-hydroone-migration-dev \
    --public-network-access Enabled

# SQL Server (plus AllowAzureServices firewall rule)
az sql server update \
    --name sql-hydroone-migration-dev \
    --resource-group rg-hydroone-migration-dev \
    --enable-public-network true

az sql server firewall-rule create \
    --name "AllowAzureServices" \
    --server sql-hydroone-migration-dev \
    --resource-group rg-hydroone-migration-dev \
    --start-ip-address 0.0.0.0 \
    --end-ip-address 0.0.0.0

# Key Vault
az keyvault update \
    --name kv-hydroone-mig-dev \
    --resource-group rg-hydroone-migration-dev \
    --public-network-access Enabled
```

> For production, use the Terraform configurations in `terraform/` to set up private endpoints and VNet integration instead of public network access.

### Step 5: Initialize the SQL Database

Run the SQL scripts to create control tables, audit tables, and stored procedures:

```bash
# Connect to Azure SQL and run the DDL scripts in order:
# 1. Create control tables (MigrationControl, IncrementalWatermark, BatchLog, SyncLog)
sqlcmd -S sql-hydroone-migration-dev.database.windows.net -d MigrationControl \
    -i sql/create_control_table.sql -G

# 2. Create audit tables (MigrationAuditLog, ValidationLog) and stored procedures
sqlcmd -S sql-hydroone-migration-dev.database.windows.net -d MigrationControl \
    -i sql/create_audit_log_table.sql -G
```

### Step 6: Grant ADF Managed Identity Access to SQL

Run this SQL command in the `MigrationControl` database:

```sql
CREATE USER [adf-hydroone-migration-dev] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [adf-hydroone-migration-dev];
ALTER ROLE db_datawriter ADD MEMBER [adf-hydroone-migration-dev];
GRANT EXECUTE ON SCHEMA::dbo TO [adf-hydroone-migration-dev];
```

### Step 7: Deploy ADF ARM Templates

Deploy linked services, datasets, and pipelines to Azure Data Factory:

```bash
az deployment group create \
    --resource-group rg-hydroone-migration-dev \
    --template-file adf-templates/arm-template.json \
    --parameters @config/parameters.dev.json
```

Or use the deployment script:

```bash
./scripts/Deploy-ADF-Templates.sh
```

### Step 8: Populate the Control Table

Enumerate SharePoint sites and document libraries, and populate the SQL control table:

```powershell
.\scripts\Populate-ControlTable.ps1 `
    -SharePointTenantUrl "https://hydroone.sharepoint.com" `
    -SqlServerName "sql-hydroone-migration-dev" `
    -SqlDatabaseName "MigrationControl"
```

This script connects to SharePoint Online via PnP PowerShell, enumerates all site collections and document libraries (excluding system libraries), calculates file counts and sizes, assigns migration priority (smaller libraries first), and inserts/updates records in the `MigrationControl` table.

### Step 9: Run a Pilot Migration

Start with a single small library to validate the end-to-end flow:

1. In the Azure Portal, navigate to your Data Factory
2. Open the **Author** tab and select `PL_Master_Migration_Orchestrator`
3. Click **Debug** or **Add Trigger > Trigger Now**
4. Monitor progress in the **Monitor** tab

Alternatively, filter the control table to a single library for the pilot:

```sql
-- Set all libraries to 'Excluded' except the pilot
UPDATE dbo.MigrationControl SET Status = 'Excluded' WHERE Status = 'Pending';

-- Enable only the pilot library
UPDATE dbo.MigrationControl SET Status = 'Pending'
WHERE SiteUrl = '/sites/SalesAndMarketing' AND LibraryName = 'Shared Documents';
```

### Step 10: Validate Migration Results

After the pilot completes, validate the results:

```powershell
.\scripts\Validate-Migration.ps1 `
    -SqlServerName "sql-hydroone-migration-dev" `
    -SqlDatabaseName "MigrationControl"
```

Or run validation queries directly:

```sql
-- Check migration status per library
SELECT SiteUrl, LibraryName, Status, FileCount, TotalSizeBytes
FROM dbo.MigrationControl
ORDER BY Status, SiteUrl;

-- Check per-file audit log
SELECT FileName, SourcePath, DestinationPath, MigrationStatus, ErrorMessage
FROM dbo.MigrationAuditLog
ORDER BY [Timestamp] DESC;

-- Verify deltaLink was stored (for incremental sync)
SELECT SiteUrl, LibraryName, DriveId,
    CASE WHEN DeltaLink IS NOT NULL THEN 'Stored' ELSE 'Missing' END AS DeltaLinkStatus,
    LastSyncTime
FROM dbo.IncrementalWatermark;
```

---

## Incremental Sync

After the initial migration, ongoing synchronization is handled by `PL_Incremental_Sync`. This pipeline uses the `@odata.deltaLink` stored during initial migration to query only changed or new files since the last sync.

### How It Works

1. Reads the stored `@odata.deltaLink` from the `IncrementalWatermark` SQL table
2. Calls the Graph API delta endpoint with the stored link
3. Processes only changed/new files through `PL_Copy_File_Batch`
4. Stores the new `@odata.deltaLink` for the next sync run
5. If no files have changed, the pipeline completes with 0 files processed

### Scheduling

For production, configure a trigger to run incremental sync on a schedule:

| Setting | Recommended Value |
|---------|-------------------|
| Frequency | Daily at 2:00 AM EST |
| Retry | 3 attempts with 30-minute intervals |

---

## Monitoring and Operations

### Real-Time Monitoring

Use the monitoring script for a live dashboard:

```powershell
.\scripts\Monitor-Migration.ps1 `
    -SqlServerName "sql-hydroone-migration-dev" `
    -SqlDatabaseName "MigrationControl" `
    -RefreshInterval 10
```

### SQL Monitoring Queries

The file `sql/migration_progress_queries.sql` contains **25+ ready-to-use queries** for:

- Migration progress by library and site
- File migration counts, sizes, and success rates
- Daily and hourly migration throughput rates
- Estimated completion time based on average throughput
- Failed file details and error summaries
- Throttling analysis (429 errors by hour)
- Validation discrepancies
- Batch performance summaries
- File size distribution analysis
- Incremental sync activity tracking

### Alert Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| Pipeline failure | Any | Email notification, investigate immediately |
| Throttling rate | >10% of requests | Reduce parallelism or increase `ThrottleDelaySeconds` |
| Failed files | >5% of batch | Pause migration and investigate |
| Storage capacity | >90% | Expand ADLS storage |

---

## Throttling Management

Microsoft Graph API enforces per-tenant and per-app throttling limits. The solution includes several mitigation strategies:

| Strategy | Implementation |
|----------|---------------|
| **Inter-page delay** | Configurable `ThrottleDelaySeconds` (default 2s) between pagination pages |
| **Controlled parallelism** | 4 concurrent libraries, 10 concurrent files per library |
| **Off-peak scheduling** | Run bulk migration during 8 PM - 6 AM EST |
| **Exponential backoff** | Wait 30s, 60s, 120s on retry for failed operations |
| **429 handling** | Honor `Retry-After` header from Graph API responses |
| **Throttling limit increase** | Request from Microsoft Account Team for the migration window (template in `docs/runbook.md`) |

---

## ADF Limitations and Workarounds

During development, several Azure Data Factory activity nesting restrictions were discovered that shaped the pipeline architecture:

| Limitation | Impact | Workaround |
|------------|--------|------------|
| **Until cannot contain ForEach** | Cannot iterate over files inside the pagination loop | Extracted ForEach into child pipeline `PL_Copy_File_Batch`, called via ExecutePipeline |
| **Until cannot contain IfCondition** | Cannot use conditional branches inside the pagination loop | Replaced with flat `SetVariable` activities using `@if()` expressions |
| **SetVariable cannot self-reference** | Cannot increment a counter or append to an array in-place | Use separate variables or `''` (empty string) as safe fallback |
| **No recursive pipelines** | A pipeline cannot call itself via ExecutePipeline | Used delta query (`/root/delta`) which returns all files at all depths, eliminating recursion |

These constraints are the reason `PL_Copy_File_Batch` exists as a separate child pipeline rather than having the ForEach file copy logic inline within the Until loop.

---

## Migration Plan (10 Weeks)

The migration follows a phased approach:

```
Week 1  |########| Phase 1: POC Validation             ** VALIDATED 2026-02-18 **
Week 2  |########| Phase 2: Pilot Migration (1 TB)
Week 3  |########| Phase 2: Pilot Migration (continued)
Week 4  |########| Phase 3: Bulk Migration - Batch 1 (5 TB)
Week 5  |########| Phase 3: Bulk Migration - Batch 2 (5 TB)
Week 6  |########| Phase 3: Bulk Migration - Batch 3 (7 TB)
Week 7  |########| Phase 3: Bulk Migration - Batch 4 (7 TB)
Week 8  |########| Phase 3: Bulk Migration - Cleanup
Week 9  |########| Phase 4: Validation & Reconciliation
Week 10 |########| Phase 4: Cutover & Knowledge Transfer
```

| Phase | Scope | Goal |
|-------|-------|------|
| **Phase 1: POC** | 1 library (~30 files) | Validate end-to-end approach |
| **Phase 2: Pilot** | 10-20 libraries (~1 TB) | Validate at scale, tune parameters |
| **Phase 3: Bulk** | All remaining libraries (~24 TB) | Migrate in 5-7 TB weekly batches |
| **Phase 4: Validation** | All data | Reconcile counts/sizes, business sign-off |
| **Phase 5: Ongoing** | Delta changes | Daily incremental sync (automated) |

For the detailed week-by-week plan, task assignments, risk register, and RACI matrix, see [docs/migration-plan.md](docs/migration-plan.md).

---

## Cost Estimation

| Resource | Specification | Monthly Cost (Est.) |
|----------|---------------|---------------------|
| ADLS Gen2 | 30 TB, Hot tier | ~$600 |
| Azure Data Factory | Pay-as-you-go | ~$100-200 |
| Azure SQL Database | S1 Standard | ~$30 |
| Azure Key Vault | Standard | ~$5 |
| **Total** | | **~$800-850/month** |

---

## Security

| Layer | Method |
|-------|--------|
| Data in transit | TLS 1.2+ (all HTTPS) |
| Data at rest (ADLS) | Microsoft-managed keys (CMK optional) |
| Data at rest (SQL) | Transparent Data Encryption (TDE) |
| SharePoint access | Service Principal with read-only Graph API permissions |
| Azure resource access | Managed Identity (no stored credentials) |
| Secret management | Azure Key Vault with RBAC |
| Data residency | Canada Central region |
| Audit trail | Per-file logging to SQL with timestamps, sizes, and error details |

---

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture Overview](docs/architecture.md) | Full architecture deep-dive with Mermaid diagrams, authentication flows, data flows, throttling strategy, error handling, and verified test results |
| [Deployment Guide](docs/deployment-guide.md) | 10-phase step-by-step deployment guide with CLI commands, checklists, and network configuration |
| [Operational Runbook](docs/runbook.md) | Day-to-day operational procedures, prerequisites checklist, throttling management, error handling, and rollback plan |
| [Migration Plan](docs/migration-plan.md) | Phased 10-week migration plan with timeline, risk register, RACI matrix, and communication plan |
| [Pipeline Documentation](docs/pipeline-documentation.md) | Technical reference for all 6 pipelines, linked services, datasets, SQL schema, scripts, and ARM templates |

---

## Key Contacts

| Role | Organization | Contact |
|------|-------------|---------|
| Hydro One IT Team | Hydro One | [internal contact] |
| Microsoft Azure Team | Microsoft | [consultant contact] |
| Microsoft Account Team | Microsoft | [TAM contact] |

---

## License

Proprietary - Hydro One Internal Use Only
