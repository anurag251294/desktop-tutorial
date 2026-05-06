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

**Control Table Population** — Successfully validated on May 5, 2026 against Hydro One's SharePoint environment (`/sites/JSTestCommunicationSite`). The `Populate-ControlTable.ps1` script successfully enumerated sites, collected library statistics, and upserted records into Azure SQL using SQL authentication.

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
│   ├── pipeline-documentation.md   # Technical reference for all pipelines, datasets, and scripts
│   ├── debugging.md                # Troubleshooting guide organized by error code
│   ├── scripts-reference.md        # Central reference for all automation scripts
│   ├── terraform-private-endpoints.md  # Private endpoints deployment guide
│   ├── architecture-decisions.md   # Architecture Decision Records (ADRs)
│   ├── sql-schema.md               # SQL database schema with ER diagram
│   ├── faq.md                      # Frequently asked questions
│   └── changelog.md                # Version history
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

#### 1a. Prerequisites

```bash
# Login to Azure CLI
az login

# Set the target subscription
az account set --subscription "<subscription-id>"

# Verify you have Contributor access
az role assignment list --assignee $(az ad signed-in-user show --query id -o tsv) --scope /subscriptions/<subscription-id> --query "[].roleDefinitionName" -o tsv

# Register required resource providers (run once)
az provider register --namespace Microsoft.DataFactory
az provider register --namespace Microsoft.Storage
az provider register --namespace Microsoft.Sql
az provider register --namespace Microsoft.KeyVault
```

#### 1b. Run the Setup Script

```powershell
.\scripts\Setup-AzureResources.ps1 -Environment "dev" -Location "canadacentral"
```

**Parameters:**
| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `-Environment` | Yes | — | Target environment: `dev`, `test`, or `prod` |
| `-Location` | No | `canadacentral` | Azure region (must be Canada Central for data residency) |
| `-SubscriptionId` | No | Current context | Azure subscription ID |
| `-SqlAdminUsername` | No | `sqladmin` | SQL Server admin login |
| `-SqlAdminPassword` | No | Auto-generated | SQL Server admin password (stored in Key Vault) |

**Resources created:**
| Resource | Name | Notes |
|----------|------|-------|
| Resource Group | `rg-hydroone-migration-dev` | Container for all resources |
| Azure Data Factory | `adf-hydroone-migration-dev` | System-Assigned Managed Identity enabled |
| ADLS Gen2 Storage | `sthydroonemigdev` | Hierarchical namespace enabled, `sharepoint-migration` container created |
| Azure SQL Server | `sql-hydroone-migration-dev` | With database `MigrationControl` |
| Azure Key Vault | `kv-hydroone-mig-dev` | Stores SQL password and SP client secret |

#### 1c. Verify Resources

```bash
# List all resources in the group
az resource list --resource-group rg-hydroone-migration-dev -o table

# Verify ADF has a managed identity
az datafactory show --resource-group rg-hydroone-migration-dev \
    --name adf-hydroone-migration-dev --query "identity" -o json

# Verify ADLS has hierarchical namespace
az storage account show --name sthydroonemigdev \
    --query "isHnsEnabled" -o tsv
# Expected: true
```

> **Save these values** — you will need the resource names in subsequent steps. Note the SQL admin password if auto-generated (stored in Key Vault as `sql-admin-password`).

### Step 2: Register the SharePoint App and Store Credentials

#### 2a. Prerequisites

- You must have **Application Administrator** or **Global Administrator** role in the **SharePoint tenant** (not the MCAPS/Azure tenant)
- The Key Vault from Step 1 must exist

#### 2b. Run the Registration Script

```powershell
.\scripts\Register-SharePointApp.ps1 `
    -TenantId "<sharepoint-tenant-id>" `
    -KeyVaultName "kv-hydroone-mig-dev"
```

**Parameters:**
| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `-TenantId` | Yes | — | Azure AD Tenant ID of the **SharePoint tenant** |
| `-KeyVaultName` | Yes | — | Key Vault name (from Step 1) |
| `-AppDisplayName` | No | `HydroOne-SPO-Migration` | Display name for the app registration |
| `-SecretValidityYears` | No | `2` | Client secret expiry in years |

**What this creates:**
1. Azure AD App Registration (`HydroOne-SPO-Migration`) in the SharePoint tenant
2. Client secret (stored in Key Vault as `sharepoint-client-secret`)
3. API permission requests: `Sites.Read.All` and `Files.Read.All` on Microsoft Graph

#### 2c. Verify and Record

```bash
# Verify secrets are in Key Vault
az keyvault secret list --vault-name kv-hydroone-mig-dev -o table

# Record the Client ID — you will need it for Steps 3, 7, and 8
az ad app list --display-name "HydroOne-SPO-Migration" --query "[0].appId" -o tsv
```

> **IMPORTANT:** Write down the **Client ID** (Application ID). You will need it for:
> - Step 7 (`servicePrincipalId` in parameters.dev.json)
> - Step 8 (`-ClientId` for Populate-ControlTable.ps1)

### Step 3: Grant Admin Consent (CRITICAL — Requires Global Administrator)

> **HARD BLOCKER:** Without admin consent, all Graph API calls return HTTP 401/403. No migration pipeline will work. This step **cannot be automated** — it requires a Global Administrator to click a button in the Azure Portal.

#### 3a. Grant Consent

1. Sign in to [Azure Portal](https://portal.azure.com) as **Global Administrator** (in the **SharePoint tenant**)
2. Navigate to **Azure Active Directory** → **App registrations**
3. Select the migration app (e.g., `HydroOne-SPO-Migration`)
4. Click **API permissions** in the left menu
5. You should see `Sites.Read.All` and `Files.Read.All` with orange warning icons (⚠ "Not granted")
6. Click **Grant admin consent for [tenant name]**
7. Confirm by clicking **Yes**

#### 3b. Verify Consent

After granting, verify:
- Both permissions show a **green checkmark** ✅
- Status column shows **"Granted for [tenant name]"**
- If the checkmark is missing, consent was not granted — try again or check you are signed in as Global Admin

#### 3c. Test Graph API Access (optional)

```bash
# Get a token for the app
TOKEN=$(curl -s -X POST "https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/token" \
    -d "client_id=<client-id>&client_secret=<client-secret>&scope=https://graph.microsoft.com/.default&grant_type=client_credentials" \
    | jq -r '.access_token')

# Test listing sites (should return 200 with site data)
curl -s -H "Authorization: Bearer $TOKEN" \
    "https://graph.microsoft.com/v1.0/sites?search=*&\$top=5" | jq '.value[].displayName'
```

If this returns site names, consent is confirmed.

### Step 4: Enable Network Access

Ensure ADF can reach all resources. For the POC environment, enable public network access.

#### 4a. Enable Public Access on All Resources

```bash
# Storage Account — allow public access
az storage account update \
    --name sthydroonemigdev \
    --resource-group rg-hydroone-migration-dev \
    --public-network-access Enabled

# SQL Server — enable public network access
az sql server update \
    --name sql-hydroone-migration-dev \
    --resource-group rg-hydroone-migration-dev \
    --enable-public-network true

# SQL Server — allow Azure services (required for ADF Managed Identity connections)
az sql server firewall-rule create \
    --name "AllowAzureServices" \
    --server sql-hydroone-migration-dev \
    --resource-group rg-hydroone-migration-dev \
    --start-ip-address 0.0.0.0 \
    --end-ip-address 0.0.0.0

# SQL Server — allow YOUR client IP (required for running scripts locally)
# Replace <YOUR_IP> with your actual IP (check at https://whatismyip.com)
az sql server firewall-rule create \
    --name "AllowMyIP" \
    --server sql-hydroone-migration-dev \
    --resource-group rg-hydroone-migration-dev \
    --start-ip-address <YOUR_IP> \
    --end-ip-address <YOUR_IP>

# Key Vault — allow public access
az keyvault update \
    --name kv-hydroone-mig-dev \
    --resource-group rg-hydroone-migration-dev \
    --public-network-access Enabled
```

#### 4b. Verify Connectivity

```bash
# Test DNS resolution for SQL
nslookup sql-hydroone-migration-dev.database.windows.net

# Test Key Vault access
az keyvault secret list --vault-name kv-hydroone-mig-dev -o table

# Test Storage access
az storage container list --account-name sthydroonemigdev --auth-mode login -o table
```

> **For production:** Use the Terraform configurations in `terraform/` to set up private endpoints and VNet integration instead of public network access. See `docs/terraform-private-endpoints.md`.

### Step 5: Initialize the SQL Database

Create the control tables, audit tables, and stored procedures in Azure SQL.

#### 5a. Run DDL Scripts

**Using Azure AD auth (`-G` flag):**

```bash
# 1. Create control tables (MigrationControl, IncrementalWatermark, BatchLog, SyncLog)
sqlcmd -S sql-hydroone-migration-dev.database.windows.net -d MigrationControl \
    -i sql/create_control_table.sql -G

# 2. Create audit tables (MigrationAuditLog, ValidationLog) and stored procedures
sqlcmd -S sql-hydroone-migration-dev.database.windows.net -d MigrationControl \
    -i sql/create_audit_log_table.sql -G
```

**Using SQL auth (if Azure AD / ADFS auth fails):**

```bash
# Use -U and -P instead of -G
sqlcmd -S sql-hydroone-migration-dev.database.windows.net -d MigrationControl \
    -U sqladmin -P "<password>" \
    -i sql/create_control_table.sql

sqlcmd -S sql-hydroone-migration-dev.database.windows.net -d MigrationControl \
    -U sqladmin -P "<password>" \
    -i sql/create_audit_log_table.sql
```

> **Note:** The SQL admin password was either set manually in Step 1 or auto-generated and stored in Key Vault. Retrieve it with:
> ```bash
> az keyvault secret show --vault-name kv-hydroone-mig-dev --name sql-admin-password --query value -o tsv
> ```

#### 5b. Verify Tables Were Created

```bash
sqlcmd -S sql-hydroone-migration-dev.database.windows.net -d MigrationControl \
    -U sqladmin -P "<password>" \
    -Q "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES ORDER BY TABLE_NAME"
```

**Expected output (6 tables):**
```
TABLE_SCHEMA  TABLE_NAME
------------- ----------------------
dbo           BatchLog
dbo           IncrementalWatermark
dbo           MigrationAuditLog
dbo           MigrationControl
dbo           SyncLog
dbo           ValidationLog
```

If any tables are missing, re-run the DDL scripts.

### Step 6: Grant ADF Managed Identity Access to SQL

The ADF Managed Identity needs database permissions to read/write the control and audit tables during pipeline execution.

#### 6a. Get the ADF Managed Identity Name

The managed identity name matches the ADF name (e.g., `adf-hydroone-migration-dev`). Verify:

```bash
az datafactory show --resource-group rg-hydroone-migration-dev \
    --name adf-hydroone-migration-dev \
    --query "identity.principalId" -o tsv
```

#### 6b. Create the Database User and Assign Roles

Connect to the `MigrationControl` database and run:

```sql
-- Create the ADF user from the managed identity
CREATE USER [adf-hydroone-migration-dev] FROM EXTERNAL PROVIDER;

-- Grant read/write access to all tables
ALTER ROLE db_datareader ADD MEMBER [adf-hydroone-migration-dev];
ALTER ROLE db_datawriter ADD MEMBER [adf-hydroone-migration-dev];

-- Grant execute permission for stored procedures
GRANT EXECUTE ON SCHEMA::dbo TO [adf-hydroone-migration-dev];
```

> **Note:** The `CREATE USER ... FROM EXTERNAL PROVIDER` command requires you to be connected as an **Azure AD admin** on the SQL server. If you get an error, verify the AD admin is set:
> ```bash
> az sql server ad-admin list --server sql-hydroone-migration-dev --resource-group rg-hydroone-migration-dev
> ```

#### 6c. Verify Permissions

```sql
-- Verify the user exists and has correct roles
SELECT dp.name, dp.type_desc, r.name AS role_name
FROM sys.database_principals dp
LEFT JOIN sys.database_role_members rm ON dp.principal_id = rm.member_principal_id
LEFT JOIN sys.database_principals r ON rm.role_principal_id = r.principal_id
WHERE dp.name = 'adf-hydroone-migration-dev';
```

**Expected output:**
```
name                          type_desc        role_name
----------------------------- ---------------- ---------------
adf-hydroone-migration-dev    EXTERNAL_USER    db_datareader
adf-hydroone-migration-dev    EXTERNAL_USER    db_datawriter
```

### Step 7: Deploy ADF ARM Templates

Deploy linked services, datasets, and pipelines to Azure Data Factory.

> **IMPORTANT:** The `arm-template.json` only deploys the ADF instance, linked services, and **some** datasets. **It does NOT deploy all datasets or any pipelines.** The dataset `DS_Graph_Content_Download` and all 6 pipelines are in separate ARM templates and must be deployed individually. Use the deployment script below which handles everything in the correct order.

**Option A: Automated deployment script (recommended)**

```bash
./scripts/Deploy-ADF-Templates.sh \
    --factory "adf-hydroone-migration-dev" \
    --resource-group "rg-hydroone-migration-dev" \
    --storage-account "sthydroonemigdev" \
    --sql-server "sql-hydroone-migration-dev" \
    --sql-database "MigrationControl" \
    --key-vault "kv-hydroone-mig-dev" \
    --subscription "<subscription-id>"
```

This deploys all resources in dependency order: 4 Linked Services → 5 Datasets → 6 Pipelines.

**Option B: Manual deployment (if bash is not available)**

Deploy in this exact order. Each step depends on the previous one.

**Step B1: Deploy ADF instance + core linked services + some datasets**

```bash
az deployment group create \
    --resource-group rg-hydroone-migration-dev \
    --template-file adf-templates/arm-template.json \
    --parameters @config/parameters.dev.json
```

**Step B2: Deploy remaining datasets (NOT included in arm-template.json)**

> **CRITICAL:** The `DS_Graph_Content_Download` dataset is required by the pipelines but is NOT included in `arm-template.json`. You MUST deploy it separately before deploying pipelines, or you will get: `"invalid reference 'ds_graph_content_download'"`.

```bash
# Deploy all 3 dataset templates (safe to re-run — idempotent)
az deployment group create --resource-group rg-hydroone-migration-dev \
    --template-file adf-templates/datasets/DS_SQL_ControlTables.json \
    --parameters factoryName="adf-hydroone-migration-dev"

az deployment group create --resource-group rg-hydroone-migration-dev \
    --template-file adf-templates/datasets/DS_ADLS_Sink.json \
    --parameters factoryName="adf-hydroone-migration-dev"

az deployment group create --resource-group rg-hydroone-migration-dev \
    --template-file adf-templates/datasets/DS_Graph_Content_Download.json \
    --parameters factoryName="adf-hydroone-migration-dev"
```

**Step B3: Deploy pipelines (child pipelines before parents)**

```bash
# 1. PL_Copy_File_Batch (no deps — deploy FIRST)
az deployment group create --resource-group rg-hydroone-migration-dev \
    --template-file adf-templates/pipelines/PL_Copy_File_Batch.json \
    --parameters factoryName="adf-hydroone-migration-dev"

# 2. PL_Process_Subfolder (depends on PL_Copy_File_Batch)
az deployment group create --resource-group rg-hydroone-migration-dev \
    --template-file adf-templates/pipelines/PL_Process_Subfolder.json \
    --parameters factoryName="adf-hydroone-migration-dev"

# 3. PL_Migrate_Single_Library (depends on PL_Copy_File_Batch)
az deployment group create --resource-group rg-hydroone-migration-dev \
    --template-file adf-templates/pipelines/PL_Migrate_Single_Library.json \
    --parameters factoryName="adf-hydroone-migration-dev"

# 4. PL_Incremental_Sync (depends on PL_Copy_File_Batch)
az deployment group create --resource-group rg-hydroone-migration-dev \
    --template-file adf-templates/pipelines/PL_Incremental_Sync.json \
    --parameters factoryName="adf-hydroone-migration-dev"

# 5. PL_Validation (standalone)
az deployment group create --resource-group rg-hydroone-migration-dev \
    --template-file adf-templates/pipelines/PL_Validation.json \
    --parameters factoryName="adf-hydroone-migration-dev"

# 6. PL_Master_Migration_Orchestrator (depends on PL_Migrate_Single_Library — deploy LAST)
az deployment group create --resource-group rg-hydroone-migration-dev \
    --template-file adf-templates/pipelines/PL_Master_Migration_Orchestrator.json \
    --parameters factoryName="adf-hydroone-migration-dev"
```

#### 7c. Verify Deployment

After deployment, verify in ADF Studio:

```bash
# List all datasets (expect 5+)
az datafactory dataset list --resource-group rg-hydroone-migration-dev \
    --factory-name adf-hydroone-migration-dev --query "[].name" -o tsv

# List all pipelines (expect 6)
az datafactory pipeline list --resource-group rg-hydroone-migration-dev \
    --factory-name adf-hydroone-migration-dev --query "[].name" -o tsv
```

**Expected datasets:** `DS_SQL_MigrationControl`, `DS_SQL_AuditLog`, `DS_ADLS_Binary_Sink`, `DS_SharePoint_Binary_HTTP`, `DS_ADLS_Parquet_Metadata`, `DS_Graph_Content_Download` (and any from the separate dataset templates)

**Expected pipelines:** `PL_Copy_File_Batch`, `PL_Process_Subfolder`, `PL_Migrate_Single_Library`, `PL_Incremental_Sync`, `PL_Validation`, `PL_Master_Migration_Orchestrator`

If any are missing, re-run the corresponding deployment command above.

> **Note:** The `config/parameters.dev.json` file ships with **test environment values** (POC tenant). You must update all parameter values to match your actual Azure resource names before deploying. See the parameter descriptions in `adf-templates/arm-template.json` for what each value represents.

### Step 8: Populate the Control Table

Enumerate SharePoint sites and document libraries, and populate the SQL control table.

#### 8a. Prerequisites

Before running the script, ensure the following are installed and available:

```powershell
# Install required PowerShell modules (run once)
Install-Module -Name PnP.PowerShell -Scope CurrentUser -Force
Install-Module -Name SqlServer    -Scope CurrentUser -Force

# Verify modules are available
Get-Module -ListAvailable PnP.PowerShell, SqlServer
```

You also need:
- The **Azure AD App Registration Client ID** (from Step 2) with `Sites.Read.All` permission and admin consent granted
- A **certificate** installed in your local certificate store (for certificate-based PnP auth), **or** use `-Interactive` for browser-based login
- The SQL server must have a **firewall rule** allowing your client IP (check the error message for your IP if blocked)

#### 8b. Add SQL Server Firewall Rule for Your Client IP

If you see an error like `Client with IP address 'x.x.x.x' is not allowed to access the server`, add your IP:

```bash
az sql server firewall-rule create \
    --name "AllowMyIP" \
    --server sql-hydroone-migration-dev \
    --resource-group rg-hydroone-migration-dev \
    --start-ip-address <YOUR_IP> \
    --end-ip-address <YOUR_IP>
```

#### 8c. Run the Script — Choose Your Authentication Options

**Option A: Specific site(s) + SQL Authentication (recommended for initial testing)**

Use this when you want to target specific sites and your environment uses ADFS/federated authentication (which prevents AD Integrated SQL auth):

```powershell
.\scripts\Populate-ControlTable.ps1 `
    -SharePointTenantUrl "https://hydroone.sharepoint.com" `
    -ClientId "<your-app-client-id>" `
    -SpecificSites @("/sites/MySite1", "/sites/MySite2") `
    -SqlServerName "sql-hydroone-migration-dev" `
    -SqlDatabaseName "MigrationControl" `
    -SqlUsername "sqladmin" `
    -SqlPassword (ConvertTo-SecureString "YourPassword" -AsPlainText -Force)
```

**Option B: All sites + Azure AD Integrated SQL auth**

Use this when you want to enumerate all sites and your Azure AD account has direct SQL access:

```powershell
.\scripts\Populate-ControlTable.ps1 `
    -SharePointTenantUrl "https://hydroone.sharepoint.com" `
    -ClientId "<your-app-client-id>" `
    -SqlServerName "sql-hydroone-migration-dev" `
    -SqlDatabaseName "MigrationControl"
```

**Option C: Certificate-based PnP auth (non-interactive / automation)**

```powershell
.\scripts\Populate-ControlTable.ps1 `
    -SharePointTenantUrl "https://hydroone.sharepoint.com" `
    -ClientId "<your-app-client-id>" `
    -CertificateThumbprint "<thumbprint>" `
    -TenantId "<sharepoint-tenant-id>" `
    -SpecificSites @("/sites/MySite1") `
    -SqlServerName "sql-hydroone-migration-dev" `
    -SqlDatabaseName "MigrationControl" `
    -SqlUsername "sqladmin" `
    -SqlPassword (ConvertTo-SecureString "YourPassword" -AsPlainText -Force)
```

#### 8d. Script Parameters Reference

| Parameter | Required | Description |
|-----------|----------|-------------|
| `-SharePointTenantUrl` | Yes | Tenant root URL, e.g. `https://hydroone.sharepoint.com`. Do **not** include `/sites/...` — use `-SpecificSites` for that. |
| `-ClientId` | Yes | Azure AD App Registration Client ID with `Sites.Read.All` permission |
| `-SqlServerName` | Yes | Azure SQL server name (without `.database.windows.net`) |
| `-SqlDatabaseName` | Yes | SQL database name (e.g. `MigrationControl`) |
| `-SpecificSites` | No | Array of site paths to target, e.g. `@("/sites/MySite")`. If omitted, enumerates all sites via the admin center. |
| `-ExcludeSites` | No | Array of site paths to skip |
| `-CertificateThumbprint` | No | Certificate thumbprint for non-interactive PnP auth |
| `-TenantId` | No | Azure AD tenant ID (required with `-CertificateThumbprint`) |
| `-SqlUsername` | No | SQL login username. Use this instead of AD Integrated auth when running in ADFS/federated environments. |
| `-SqlPassword` | No | SQL login password (SecureString). If `-SqlUsername` is provided without this, you will be prompted. |

#### 8e. What the Script Does

1. **Pre-flight diagnostics** — Tests network connectivity (DNS, TCP port 1433), SQL authentication, table existence, permissions, and a dry-run INSERT/ROLLBACK
2. **SharePoint enumeration** — Connects via PnP PowerShell, lists site collections (or uses `-SpecificSites`), enumerates document libraries per site
3. **Statistics collection** — Counts files, folders, total size, and largest file per library
4. **Priority assignment** — Assigns priority based on library size (smaller libraries get higher priority for faster initial results): <100 MB → P10, <1 GB → P50, <10 GB → P100, >10 GB → P200
5. **SQL upsert** — Inserts new records or updates existing ones in `dbo.MigrationControl` using IF NOT EXISTS / ELSE pattern

#### 8f. Output and Logging

Every run produces a timestamped log file in the script directory:

```
Populate-ControlTable_20260505_171200.log
```

The log includes:
- Full environment diagnostics (OS, PowerShell version, modules, network connectivity)
- SQL pre-flight check results (6-step validation)
- Per-site and per-library enumeration details
- SQL upsert payloads and results
- Summary statistics (sites processed, libraries found, total files, total size)
- Full exception details with stack traces on any error

#### 8g. Common Errors and Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| `Client with IP address 'x.x.x.x' is not allowed` | SQL firewall blocking your IP | Add firewall rule (see Step 8b) |
| `Failed to authenticate NT Authority\Anonymous Logon` | ADFS/federated environment incompatible with AD Integrated auth | Use `-SqlUsername` and `-SqlPassword` for SQL auth |
| `The remote server returned an error: (403) Forbidden` | App lacks admin consent or `Sites.Read.All` permission | Grant admin consent (see Step 3) |
| `The remote server returned an error: (404) Not Found` | Wrong tenant URL or site doesn't exist | Verify `-SharePointTenantUrl` is the tenant root (not a site URL). Use `-SpecificSites` for site paths. |
| `No such host is known` | Wrong SQL server name | Verify server name: `nslookup <server>.database.windows.net` |
| `MigrationControl table does not exist` | DDL scripts not run yet | Run Step 5 first |
| `Cannot convert System.Object[] to System.Int32` | Outdated script version | Pull the latest version from this repository |

### Step 9: Run a Pilot Migration

Start with a single small library to validate the end-to-end flow before running the full migration.

#### 9a. Select a Pilot Library

Choose the smallest library from your control table:

```sql
-- Find the smallest library for piloting
SELECT TOP 5 SiteUrl, LibraryName, FileCount,
    CAST(TotalSizeBytes / 1048576.0 AS DECIMAL(10,2)) AS SizeMB, Status
FROM dbo.MigrationControl
WHERE Status = 'Pending'
ORDER BY TotalSizeBytes ASC;
```

#### 9b. Isolate the Pilot Library

Set all libraries to `Excluded` except the one you want to pilot:

```sql
-- Exclude everything first
UPDATE dbo.MigrationControl SET Status = 'Excluded' WHERE Status = 'Pending';

-- Enable only the pilot library
UPDATE dbo.MigrationControl SET Status = 'Pending'
WHERE SiteUrl = '/sites/JSTestCommunicationSite' AND LibraryName = 'Shared Documents';

-- Verify only 1 library is pending
SELECT SiteUrl, LibraryName, FileCount, Status
FROM dbo.MigrationControl WHERE Status = 'Pending';
```

#### 9c. Verify ADF Linked Service Connections

Before running the pipeline, test all linked service connections in ADF:

1. Go to **Azure Portal** → **Data Factory** → **Manage** tab → **Linked services**
2. Click each linked service and click **Test connection**:
   - `LS_AzureKeyVault` → Should connect via Managed Identity
   - `LS_AzureBlobStorage` → Should connect to ADLS Gen2 via Managed Identity
   - `LS_AzureSqlDatabase` → Should connect to SQL via Managed Identity
   - `LS_HTTP_Graph_Download` → May show "Anonymous" (this is expected — auth is handled in the pipeline via Bearer token)

If any connection fails, check:
- Managed Identity RBAC roles (Step 1)
- Network access / firewall rules (Step 4)
- SQL user creation (Step 6)

#### 9d. Trigger the Pipeline

1. Go to **Azure Portal** → **Data Factory** → **Author** tab
2. Expand **Pipelines** in the left tree
3. Select **`PL_Master_Migration_Orchestrator`**
4. Click **Debug** (for testing) or **Add Trigger → Trigger Now** (for a tracked run)
5. If prompted for parameters, use defaults or set:
   - `BatchSize`: `1` (process 1 library at a time for the pilot)
   - `ParallelLibraries`: `1` (no parallelism for the pilot)

#### 9e. Monitor the Pipeline

1. Go to the **Monitor** tab in ADF
2. Click on the running pipeline to see activity-level details
3. Each activity shows its status (In Progress, Succeeded, Failed)
4. The flow should be: `PL_Master_Migration_Orchestrator` → `PL_Migrate_Single_Library` → `PL_Copy_File_Batch` (multiple iterations)

**What to watch for:**
- **Token acquisition** — First activity acquires an OAuth2 token from Key Vault + Azure AD
- **Drive resolution** — Resolves the SharePoint library to a Graph API drive ID
- **Delta query pagination** — The Until loop pages through all files in the library
- **File copy** — Each page triggers `PL_Copy_File_Batch` which copies files in parallel

#### 9f. Troubleshoot Failures

If the pipeline fails, click the **failed activity** → **Output** or **Error** to see details.

| Error | Likely Cause | Fix |
|-------|-------------|-----|
| HTTP 401 on token request | Client secret expired or wrong in Key Vault | Re-register the app (Step 2) |
| HTTP 403 on Graph API call | Admin consent not granted | Complete Step 3 |
| HTTP 404 on Graph API call | Wrong site URL in control table, or library doesn't exist | Verify SiteUrl in `MigrationControl` table |
| ADLS write failure (403) | ADF Managed Identity lacks Storage Blob Data Contributor role | Check RBAC (Step 1) |
| SQL write failure | ADF Managed Identity lacks db_datawriter role | Check Step 6 |
| Key Vault access denied | ADF Managed Identity lacks Key Vault Secrets User role | Check RBAC (Step 1) |

### Step 10: Validate Migration Results

After the pilot completes, validate that all files were migrated correctly.

#### 10a. Check Pipeline Run Summary

In ADF **Monitor** tab, verify:
- Pipeline status: **Succeeded**
- Activity run count matches expected (1 library → 1 `PL_Migrate_Single_Library` + N `PL_Copy_File_Batch` runs)

#### 10b. Check Control Table Status

```sql
-- Library-level status
SELECT SiteUrl, LibraryName, Status, FileCount, TotalSizeBytes,
    CAST(TotalSizeBytes / 1048576.0 AS DECIMAL(10,2)) AS SizeMB
FROM dbo.MigrationControl
ORDER BY Status, SiteUrl;
-- Status should be 'Completed' for the pilot library
```

#### 10c. Check Audit Log (Per-File Details)

```sql
-- File-level migration results
SELECT FileName, SourcePath, DestinationPath, MigrationStatus,
    FileSize, ErrorMessage, [Timestamp]
FROM dbo.MigrationAuditLog
ORDER BY [Timestamp] DESC;

-- Count successes vs failures
SELECT MigrationStatus, COUNT(*) AS FileCount
FROM dbo.MigrationAuditLog
GROUP BY MigrationStatus;
-- Expected: all 'Succeeded', 0 'Failed'
```

#### 10d. Verify Files in ADLS

```bash
# List migrated files in ADLS
az storage fs file list \
    --account-name sthydroonemigdev \
    --file-system sharepoint-migration \
    --path "JSTestCommunicationSite/Shared Documents" \
    --auth-mode login -o table

# Count files
az storage fs file list \
    --account-name sthydroonemigdev \
    --file-system sharepoint-migration \
    --path "JSTestCommunicationSite/Shared Documents" \
    --auth-mode login --query "length(@)"
```

Compare the count with the `FileCount` in the `MigrationControl` table.

#### 10e. Verify DeltaLink (for Incremental Sync)

```sql
-- Verify deltaLink was stored
SELECT SiteUrl, LibraryName, DriveId,
    CASE WHEN DeltaLink IS NOT NULL THEN 'Stored' ELSE 'MISSING' END AS DeltaLinkStatus,
    LEN(DeltaLink) AS DeltaLinkLength,
    LastSyncTime
FROM dbo.IncrementalWatermark;
-- DeltaLinkStatus should be 'Stored' — this enables incremental sync
```

#### 10f. Run the Validation Script (Optional)

```powershell
.\scripts\Validate-Migration.ps1 `
    -SharePointTenantUrl "https://hydroone.sharepoint.com" `
    -SqlServerName "sql-hydroone-migration-dev" `
    -SqlDatabaseName "MigrationControl" `
    -StorageAccountName "sthydroonemigdev" `
    -OutputCsv "./pilot-validation-report.csv"
```

This compares file counts and sizes between SharePoint (source) and ADLS (destination) per library and generates a validation report.

#### 10g. Next Steps After Successful Pilot

Once the pilot is validated:

1. **Re-enable remaining libraries** for migration:
   ```sql
   UPDATE dbo.MigrationControl SET Status = 'Pending' WHERE Status = 'Excluded';
   ```
2. **Run in batches** — Increase `ParallelLibraries` to 4 and run the master pipeline again
3. **Monitor throughput** — Use `scripts/Monitor-Migration.ps1` for real-time progress
4. **Set up incremental sync** — After initial migration completes, schedule `PL_Incremental_Sync` for daily delta syncs (see the [Incremental Sync](#incremental-sync) section below)

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

### Core Documentation

| Document | Description |
|----------|-------------|
| [Architecture Overview](docs/architecture.md) | Solution architecture with Mermaid diagrams, authentication flows, data flows, throttling strategy, and verified test results |
| [Deployment Guide](docs/deployment-guide.md) | 10-phase step-by-step deployment guide with CLI commands, checklists, and network configuration |
| [Operational Runbook](docs/runbook.md) | Day-to-day operational procedures, prerequisites checklist, throttling management, error handling, and rollback plan |
| [Migration Plan](docs/migration-plan.md) | Phased 10-week migration plan with timeline, risk register, RACI matrix, and communication plan |
| [Pipeline Documentation](docs/pipeline-documentation.md) | Technical reference for all 6 pipelines, linked services, datasets, SQL schema, scripts, and ARM templates |

### Reference Documentation

| Document | Description |
|----------|-------------|
| [Troubleshooting Guide](docs/debugging.md) | Error-code-indexed troubleshooting guide with symptoms, root causes, resolution steps, and diagnostic queries |
| [Scripts Reference](docs/scripts-reference.md) | Central reference for all 6 automation scripts with execution order, parameters, and prerequisites |
| [Private Endpoints (Terraform)](docs/terraform-private-endpoints.md) | Guide for adding private networking to production using the Terraform configurations |
| [Architecture Decision Records](docs/architecture-decisions.md) | Records of key technical decisions (Graph API, delta query, child pipeline pattern, etc.) with rationale |
| [SQL Schema Reference](docs/sql-schema.md) | ER diagram, table descriptions, stored procedures, computed columns, and indexes |
| [FAQ](docs/faq.md) | Frequently asked questions covering migration operations, troubleshooting, and security |
| [Changelog](docs/changelog.md) | Version history documenting the evolution from v1.0 to the current production-ready POC |

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
