# Hydro One SharePoint to Azure Migration - End-to-End Deployment Guide

## Document Information

| Field | Value |
|-------|-------|
| Project | Hydro One SharePoint to Azure Data Lake Migration |
| Version | 2.0 |
| Author | Microsoft Azure Data Engineering Team |
| Last Updated | February 2026 |
| Classification | Confidential |

---

## Table of Contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [Phase 1: Azure Infrastructure Setup](#3-phase-1-azure-infrastructure-setup)
4. [Phase 2: Azure AD & SharePoint Configuration](#4-phase-2-azure-ad--sharepoint-configuration)
5. [Phase 3: Data Factory Deployment](#5-phase-3-data-factory-deployment)
6. [Phase 4: SQL Database Initialization](#6-phase-4-sql-database-initialization)
7. [Phase 5: Permissions & Security Configuration](#7-phase-5-permissions--security-configuration)
8. [Phase 6: Control Table Population](#8-phase-6-control-table-population)
9. [Phase 7: Pilot Migration](#9-phase-7-pilot-migration)
10. [Phase 8: Full Migration Execution](#10-phase-8-full-migration-execution)
11. [Phase 9: Validation & Reconciliation](#11-phase-9-validation--reconciliation)
12. [Phase 10: Incremental Sync Setup](#12-phase-10-incremental-sync-setup)
13. [Monitoring & Operations](#13-monitoring--operations)
14. [Troubleshooting Guide](#14-troubleshooting-guide)
15. [Rollback Procedures](#15-rollback-procedures)
16. [Appendix](#16-appendix)

---

## 1. Overview

### 1.1 Migration Scope

This POC migrates **~25 TB** of documents from SharePoint Online to Azure Data Lake Storage Gen2 (ADLS Gen2) using Azure Data Factory (ADF) as the orchestration engine.

### 1.2 Architecture Summary

```
SharePoint Online (Source) - Tenant: 5447cfcd-3af1-439a-8157-760bd52b12df
        |
        | Microsoft Graph API (HTTPS/OAuth2 client_credentials)
        v
Azure Data Factory (Orchestration) - MCAPS Tenant: fe64e912-f83c-44e9-9389-f66812c7fa57
        |
        |--- Managed Identity ---> ADLS Gen2 (Destination)
        |--- Managed Identity ---> Azure SQL (Control/Audit)
        |--- Managed Identity ---> Key Vault (Secrets)
        |--- Service Principal --> Graph API --> SharePoint Online (cross-tenant)
        |--- HTTP Linked Service -> Graph API /content endpoint (file downloads)
```

### 1.3 Cross-Tenant Authentication Model

This is a **cross-tenant** migration scenario:
- **ADF** runs in the MCAPS tenant (`fe64e912-f83c-44e9-9389-f66812c7fa57`)
- **SharePoint Online** resides in a different tenant (`5447cfcd-3af1-439a-8157-760bd52b12df`)

Authentication uses the **OAuth2 client_credentials flow** against the **SharePoint tenant**:
- The App Registration is created in the SharePoint tenant (`5447cfcd-3af1-439a-8157-760bd52b12df`)
- ADF acquires a token from `https://login.microsoftonline.com/5447cfcd-3af1-439a-8157-760bd52b12df/oauth2/v2.0/token`
- The token scope is `https://graph.microsoft.com/.default`
- The token is used for both Graph API metadata calls and file content downloads

### 1.4 Key Components

| Component | Resource Name | Purpose |
|-----------|---------------|---------|
| Resource Group | `rg-hydroone-migration-{env}` | Container for all resources |
| ADLS Gen2 | `sthydroonemig{env}` | Destination storage with hierarchical namespace |
| Azure SQL | `sql-hydroone-migration-{env}` | Migration control and audit tables |
| Key Vault | `kv-hydroone-mig-{env}` | Stores SharePoint client secret |
| Data Factory | `adf-hydroone-migration-{env}` | Pipeline orchestration engine |
| Azure AD App | `HydroOne-SPO-Migration` | Service principal for Microsoft Graph API access (registered in SharePoint tenant) |

### 1.5 Deployment Environments

| Environment | Region | Purpose |
|-------------|--------|---------|
| dev | Canada Central | Development and testing |
| test | Canada Central | Pre-production validation |
| prod | Canada Central | Production migration |

---

## 2. Prerequisites

### 2.1 Azure Subscription Requirements

- [ ] Active Azure subscription with Contributor access
- [ ] Sufficient quota:
  - Storage: 30 TB capacity (25 TB data + 20% overhead)
  - SQL Database: S1 tier or higher
  - Data Factory: Pay-as-you-go
- [ ] Resource providers registered:
  - `Microsoft.DataFactory`
  - `Microsoft.Storage`
  - `Microsoft.Sql`
  - `Microsoft.KeyVault`

### 2.2 Azure AD Requirements

- [ ] Application Administrator or Global Administrator role in the **SharePoint tenant** (`5447cfcd-3af1-439a-8157-760bd52b12df`) for app registration
- [ ] **CRITICAL: Global Administrator or Privileged Role Administrator** in the SharePoint tenant is required to grant admin consent for Microsoft Graph API permissions. Without admin consent, the service principal **cannot access SharePoint Online via Graph API** and no migration pipelines will function. This is a **hard blocker** that must be resolved before any testing begins.

> **Action Required for Hydro One IT Admin:**
> A Global Administrator in the SharePoint tenant must grant admin consent for the registered application's Microsoft Graph API permissions. See [Section 4.5](#45-grant-admin-consent-critical) for detailed steps.

### 2.3 SharePoint Requirements

- [ ] SharePoint Online Administrator role
- [ ] Access to all site collections being migrated
- [ ] Complete inventory of sites, libraries, and estimated sizes
- [ ] Identified exclusions (system libraries, OneDrive, etc.)

### 2.4 Tools Required

| Tool | Version | Purpose |
|------|---------|---------|
| Azure CLI | 2.50+ | Resource deployment |
| PowerShell | 7.0+ | Automation scripts |
| Az PowerShell Module | 10.0+ | Azure management |
| SQL Server Management Studio | 19+ | Database management |
| Git | 2.40+ | Source control |

### 2.5 Network Requirements

- Outbound HTTPS (443) to `graph.microsoft.com`
- Outbound HTTPS (443) to `*.sharepoint.com` (for Graph API-initiated downloads)
- Outbound HTTPS (443) to `*.azure.com`, `*.azure.net`
- Outbound HTTPS (443) to `login.microsoftonline.com` (OAuth2 token endpoint)
- No firewall blocking Azure Data Factory managed runtime IPs
- **POC Requirement:** Public network access must be enabled on Storage Account, SQL Server, and Key Vault (see [Section 3.7](#37-enable-public-network-access-poc))

---

## 3. Phase 1: Azure Infrastructure Setup

### 3.1 Authenticate to Azure

```bash
# Login to Azure
az login --tenant "<tenant-id>"

# Set the target subscription
az account set --subscription "<subscription-id>"

# Verify context
az account show
```

### 3.2 Register Resource Providers

```bash
az provider register --namespace Microsoft.DataFactory
az provider register --namespace Microsoft.Storage
az provider register --namespace Microsoft.Sql
az provider register --namespace Microsoft.KeyVault

# Verify registration (wait for "Registered" status)
az provider show --namespace Microsoft.Storage --query "registrationState" -o tsv
az provider show --namespace Microsoft.Sql --query "registrationState" -o tsv
az provider show --namespace Microsoft.KeyVault --query "registrationState" -o tsv
```

### 3.3 Create Resource Group

```bash
az group create \
    --name "rg-hydroone-migration-{env}" \
    --location "canadacentral" \
    --tags "Project=HydroOneMigration" "Environment={env}" "Owner=Microsoft"
```

### 3.4 Create ADLS Gen2 Storage Account

```bash
az storage account create \
    --name "sthydroonemig{env}" \
    --resource-group "rg-hydroone-migration-{env}" \
    --location "canadacentral" \
    --sku "Standard_LRS" \
    --kind "StorageV2" \
    --enable-hierarchical-namespace true \
    --min-tls-version "TLS1_2"
```

**Create containers:**

```bash
# Primary migration container
az storage container create \
    --name "sharepoint-migration" \
    --account-name "sthydroonemig{env}" \
    --auth-mode login

# Metadata container
az storage container create \
    --name "migration-metadata" \
    --account-name "sthydroonemig{env}" \
    --auth-mode login
```

### 3.5 Create Azure SQL Server and Database

```bash
# Create SQL Server (with Azure AD only authentication)
az sql server create \
    --name "sql-hydroone-migration-{env}" \
    --resource-group "rg-hydroone-migration-{env}" \
    --location "canadacentral" \
    --enable-ad-only-auth \
    --external-admin-principal-type "User" \
    --external-admin-name "<admin-upn>" \
    --external-admin-sid "<admin-object-id>"

# Create database
az sql db create \
    --name "MigrationControl" \
    --server "sql-hydroone-migration-{env}" \
    --resource-group "rg-hydroone-migration-{env}" \
    --service-objective "S1" \
    --backup-storage-redundancy "Local"
```

**SQL Server Networking (Required for ADF Runtime Access):**

ADF's managed runtime connects to Azure SQL over the public endpoint. Both public network access and the AllowAzureServices firewall rule must be enabled, or ADF pipeline activities (Lookup, StoredProcedure, etc.) will fail with connection errors at runtime.

```bash
# Enable public network access on the SQL Server
az sql server update \
    --name "sql-hydroone-migration-{env}" \
    --resource-group "rg-hydroone-migration-{env}" \
    --set publicNetworkAccess="Enabled"

# Allow Azure services firewall rule
# The 0.0.0.0 range is an Azure-recognized special rule that permits
# only Azure-internal traffic (other Azure services) — it does NOT
# open the server to the entire internet.
az sql server firewall-rule create \
    --name "AllowAzureServices" \
    --server "sql-hydroone-migration-{env}" \
    --resource-group "rg-hydroone-migration-{env}" \
    --start-ip-address 0.0.0.0 \
    --end-ip-address 0.0.0.0

# Allow your client IP (for SQL management via SSMS / Portal Query Editor)
az sql server firewall-rule create \
    --name "AllowClientIP" \
    --server "sql-hydroone-migration-{env}" \
    --resource-group "rg-hydroone-migration-{env}" \
    --start-ip-address "<your-ip>" \
    --end-ip-address "<your-ip>"
```

> **Important:** If public network access is disabled or the AllowAzureServices rule is missing, ADF pipelines will fail at the first SQL activity (typically `Lookup_PendingLibraries`) with a connection timeout. For production environments, consider replacing the public endpoint with a Private Endpoint and VNet integration.

### 3.6 Create Azure Key Vault

```bash
az keyvault create \
    --name "kv-hydroone-mig-{env}" \
    --resource-group "rg-hydroone-migration-{env}" \
    --location "canadacentral" \
    --enable-rbac-authorization false \
    --sku "standard"
```

### 3.7 Enable Public Network Access (POC)

For the POC environment, public network access must be enabled on the Storage Account, SQL Server, and Key Vault so that ADF and portal users can connect without private endpoints.

```bash
# Enable public network access on Storage Account
az storage account update \
    --name sthydroonemigtest \
    --resource-group rg-hydroone-migration-test \
    --public-network-access Enabled

# Enable public network access on SQL Server
az sql server update \
    --name sql-hydroone-migration-test \
    --resource-group rg-hydroone-migration-test \
    --enable-public-network true

# Enable public network access on Key Vault
az keyvault update \
    --name kv-hydroone-test2 \
    --resource-group rg-hydroone-migration-test \
    --public-network-access Enabled
```

> **Note:** For production, replace public network access with Private Endpoints and VNet integration.

---

## 4. Phase 2: Azure AD & SharePoint Configuration

> **Important:** The App Registration must be created in the **SharePoint tenant** (`5447cfcd-3af1-439a-8157-760bd52b12df`), not the MCAPS tenant where ADF runs. This is because the OAuth2 client_credentials token is acquired against the SharePoint tenant to authorize Graph API calls to that tenant's SharePoint data.

### 4.1 Register Azure AD Application

```bash
# Login to the SharePoint tenant
az login --tenant "5447cfcd-3af1-439a-8157-760bd52b12df"

# Create the app registration
az ad app create \
    --display-name "HydroOne-SPO-Migration" \
    --sign-in-audience "AzureADMyOrg"

# Note the appId from the output
# Example: "appId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

### 4.2 Create Client Secret

```bash
# Generate a client secret (valid for 1 year)
az ad app credential reset \
    --id "<app-id>" \
    --years 1

# IMPORTANT: Save the password value immediately - it cannot be retrieved later
```

### 4.3 Create Service Principal

```bash
az ad sp create --id "<app-id>"
```

### 4.4 Add Microsoft Graph API Permissions

The pipeline uses **Microsoft Graph API** (not the SharePoint REST API directly) for both metadata enumeration and file downloads. The required permissions are **application** permissions on Microsoft Graph.

```bash
# Microsoft Graph - Sites.Read.All (Application)
# Allows reading all site collections and their contents via Graph API
az ad app permission add \
    --id "<app-id>" \
    --api "00000003-0000-0000-c000-000000000000" \
    --api-permissions "332a536c-c7ef-4017-ab91-336970924f0d=Role"

# Microsoft Graph - Files.Read.All (Application)
# Allows reading all files across all site collections via Graph API
az ad app permission add \
    --id "<app-id>" \
    --api "00000003-0000-0000-c000-000000000000" \
    --api-permissions "01d4f6ba-6a36-4f35-87f1-3298de13b0a7=Role"
```

### 4.5 Grant Admin Consent (CRITICAL)

> **This step requires a Global Administrator or Privileged Role Administrator in the SharePoint tenant.**
> Without admin consent, all Microsoft Graph API permissions remain in "Not granted" status and the migration pipelines **will not work**. This is a hard blocker.

**Required Permissions to Consent:**

| API | Permission | Type | Purpose |
|-----|-----------|------|---------|
| Microsoft Graph | Sites.Read.All | Application | Read all site collections and document library metadata via Graph API |
| Microsoft Graph | Files.Read.All | Application | Read all files and download content via Graph API `/content` endpoint |

**Option A: Azure Portal (Recommended)**
1. Sign in to [Azure Portal](https://portal.azure.com) as a **Global Administrator** in the SharePoint tenant
2. Navigate to **Azure Active Directory** > **App registrations**
3. Select **HydroOne-SPO-Migration** (or the registered app name)
4. Click **API permissions** in the left menu
5. Verify all permissions listed above are shown
6. Click the **Grant admin consent for {tenant}** button
7. Confirm by clicking **Yes**
8. Verify all permissions now show a green checkmark with **"Granted for {tenant}"**

**Option B: Azure CLI (requires Global Admin session)**
```bash
az ad app permission admin-consent --id "<app-id>"
```

**Option C: Microsoft Graph API (PowerShell)**
```powershell
# Connect as Global Admin in SharePoint tenant
Connect-MgGraph -TenantId "5447cfcd-3af1-439a-8157-760bd52b12df" `
    -Scopes "Application.ReadWrite.All", "AppRoleAssignment.ReadWrite.All"

# Grant consent for the service principal
$spId = "<service-principal-object-id>"

# Get Microsoft Graph service principal
$graphSp = Get-MgServicePrincipal -Filter "appId eq '00000003-0000-0000-c000-000000000000'"

# Sites.Read.All
$sitesReadRole = $graphSp.AppRoles | Where-Object { $_.Value -eq "Sites.Read.All" }
New-MgServicePrincipalAppRoleAssignment -ServicePrincipalId $spId `
    -PrincipalId $spId `
    -ResourceId $graphSp.Id `
    -AppRoleId $sitesReadRole.Id

# Files.Read.All
$filesReadRole = $graphSp.AppRoles | Where-Object { $_.Value -eq "Files.Read.All" }
New-MgServicePrincipalAppRoleAssignment -ServicePrincipalId $spId `
    -PrincipalId $spId `
    -ResourceId $graphSp.Id `
    -AppRoleId $filesReadRole.Id
```

**Verification:**
After granting consent, verify in Azure Portal > App registrations > API permissions that all entries show **"Granted for {tenant}"** (green checkmark), not "Not granted".

### 4.6 Store Secret in Key Vault

```bash
# Switch back to MCAPS tenant where ADF and Key Vault reside
az login --tenant "fe64e912-f83c-44e9-9389-f66812c7fa57"

az keyvault secret set \
    --vault-name "kv-hydroone-mig-{env}" \
    --name "sharepoint-client-secret" \
    --value "<client-secret-value>"

# Store the App ID as well
az keyvault secret set \
    --vault-name "kv-hydroone-mig-{env}" \
    --name "sharepoint-client-id" \
    --value "<app-id>"

# Store the SharePoint Tenant ID (the tenant where SharePoint resides)
az keyvault secret set \
    --vault-name "kv-hydroone-mig-{env}" \
    --name "sharepoint-tenant-id" \
    --value "5447cfcd-3af1-439a-8157-760bd52b12df"
```

### 4.7 Token Acquisition Flow

The pipeline acquires tokens using the **OAuth2 client_credentials** flow against the SharePoint tenant:

**Token Request:**
```
POST https://login.microsoftonline.com/5447cfcd-3af1-439a-8157-760bd52b12df/oauth2/v2.0/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&client_id=<app-id>
&client_secret=<client-secret>
&scope=https://graph.microsoft.com/.default
```

**Token Usage:**
- The returned `access_token` is used as a Bearer token in the `Authorization` header for all Microsoft Graph API calls
- Graph API endpoint for file enumeration: `GET https://graph.microsoft.com/v1.0/sites/{site-id}/drives/{drive-id}/root/children`
- Graph API endpoint for file download: `GET https://graph.microsoft.com/v1.0/sites/{site-id}/drives/{drive-id}/items/{item-id}/content`

---

## 5. Phase 3: Data Factory Deployment

### 5.1 Deploy ADF ARM Template

```bash
az deployment group create \
    --resource-group "rg-hydroone-migration-{env}" \
    --template-file "adf-templates/arm-template.json" \
    --parameters \
        factoryName="adf-hydroone-migration-{env}" \
        location="canadacentral" \
        sharePointTenantUrl="https://{tenant}.sharepoint.com" \
        servicePrincipalId="<app-id>" \
        servicePrincipalTenantId="5447cfcd-3af1-439a-8157-760bd52b12df" \
        keyVaultName="kv-hydroone-mig-{env}" \
        storageAccountName="sthydroonemig{env}" \
        sqlServerName="sql-hydroone-migration-{env}" \
        sqlDatabaseName="MigrationControl"
```

This deploys:
- **ADF instance** with system-assigned managed identity
- **6 Linked Services**: Key Vault, Graph API REST (for metadata), Graph API HTTP (for file downloads), ADLS Gen2, Azure SQL
- **7 Datasets**: Graph Content Download (HTTP binary), ADLS Binary Sink, ADLS Parquet Metadata, SQL MigrationControl, SQL AuditLog

### 5.2 Linked Services Detail

| Linked Service | Type | Base URL / Target | Auth Method | Purpose |
|----------------|------|-------------------|-------------|---------|
| `LS_AzureKeyVault` | AzureKeyVault | `https://kv-hydroone-mig-{env}.vault.azure.net/` | Managed Identity | Retrieve client secret for token acquisition |
| `LS_REST_Graph_API` | REST | `https://graph.microsoft.com` | Anonymous (token passed via headers) | Graph API calls for site/drive/file enumeration |
| `LS_HTTP_Graph_API` | HTTP | `https://graph.microsoft.com` | Anonymous (token passed via headers) | File content downloads via Graph `/content` endpoint |
| `LS_ADLS_Gen2` | AzureBlobFS | `https://sthydroonemig{env}.dfs.core.windows.net` | Managed Identity | Write migrated files to ADLS Gen2 |
| `LS_AzureSqlDatabase` | AzureSqlDatabase | `sql-hydroone-migration-{env}.database.windows.net` | Managed Identity | Read/write migration control and audit tables |

### 5.3 Datasets Detail

| Dataset | Linked Service | Purpose | Parameters |
|---------|---------------|---------|------------|
| `DS_Graph_Content_Download` | `LS_HTTP_Graph_API` | Download file content via Graph API `/content` endpoint | `ContentPath` - the relative URL path for the Graph API item content request |
| `DS_ADLS_Binary_Sink` | `LS_ADLS_Gen2` | Write binary file to ADLS Gen2 | Container, FolderPath, FileName |
| `DS_ADLS_Parquet_Metadata` | `LS_ADLS_Gen2` | Write metadata in Parquet format | Container, FolderPath |
| `DS_SQL_MigrationControl` | `LS_AzureSqlDatabase` | Migration control table operations | None |
| `DS_SQL_AuditLog` | `LS_AzureSqlDatabase` | Audit log table operations | None |

### 5.4 Deploy Pipelines

Deploy each pipeline ARM template. **Deployment order matters** because parent pipelines reference child pipelines via ExecutePipeline activities. Deploy leaf pipelines first (bottom-up):

```bash
# 1. Deploy PL_Copy_File_Batch (leaf child pipeline, no outbound ExecutePipeline references)
az deployment group create \
    --resource-group "rg-hydroone-migration-{env}" \
    --template-file "adf-templates/pipelines/PL_Copy_File_Batch.json" \
    --parameters factoryName="adf-hydroone-migration-{env}" \
    --name "pipeline-copy-file-batch"

# 2. Deploy PL_Process_Subfolder (references PL_Copy_File_Batch)
az deployment group create \
    --resource-group "rg-hydroone-migration-{env}" \
    --template-file "adf-templates/pipelines/PL_Process_Subfolder.json" \
    --parameters factoryName="adf-hydroone-migration-{env}" \
    --name "pipeline-subfolder"

# 3. Deploy PL_Incremental_Sync (references PL_Copy_File_Batch)
az deployment group create \
    --resource-group "rg-hydroone-migration-{env}" \
    --template-file "adf-templates/pipelines/PL_Incremental_Sync.json" \
    --parameters factoryName="adf-hydroone-migration-{env}" \
    --name "pipeline-incremental"

# 4. Deploy PL_Migrate_Single_Library (references PL_Copy_File_Batch)
az deployment group create \
    --resource-group "rg-hydroone-migration-{env}" \
    --template-file "adf-templates/pipelines/PL_Migrate_Single_Library.json" \
    --parameters factoryName="adf-hydroone-migration-{env}" \
    --name "pipeline-single-library"

# 5. Deploy PL_Master_Migration_Orchestrator (references PL_Migrate_Single_Library)
az deployment group create \
    --resource-group "rg-hydroone-migration-{env}" \
    --template-file "adf-templates/pipelines/PL_Master_Migration_Orchestrator.json" \
    --parameters factoryName="adf-hydroone-migration-{env}" \
    --name "pipeline-master"

# 6. Deploy PL_Validation
az deployment group create \
    --resource-group "rg-hydroone-migration-{env}" \
    --template-file "adf-templates/pipelines/PL_Validation.json" \
    --parameters factoryName="adf-hydroone-migration-{env}" \
    --name "pipeline-validation"

# 7. Deploy triggers
az deployment group create \
    --resource-group "rg-hydroone-migration-{env}" \
    --template-file "adf-templates/triggers/TR_Triggers.json" \
    --parameters factoryName="adf-hydroone-migration-{env}" \
    --name "triggers"
```

> **Why this order?** ADF validates ExecutePipeline references at deployment time. If you deploy `PL_Migrate_Single_Library` before `PL_Copy_File_Batch` exists, the deployment will fail with a "referenced pipeline not found" error. Always deploy leaf pipelines first.

**Deployment dependency graph:**
```
PL_Copy_File_Batch          (leaf - deploy first)
    ├── PL_Process_Subfolder
    ├── PL_Incremental_Sync
    └── PL_Migrate_Single_Library
            └── PL_Master_Migration_Orchestrator
```

### 5.5 Verify Deployment

```bash
# List all deployed pipelines
az rest --method GET \
    --url "https://management.azure.com/subscriptions/{sub-id}/resourceGroups/rg-hydroone-migration-{env}/providers/Microsoft.DataFactory/factories/adf-hydroone-migration-{env}/pipelines?api-version=2018-06-01" \
    --query "value[].name" -o table
```

Expected output:
```
PL_Copy_File_Batch
PL_Master_Migration_Orchestrator
PL_Migrate_Single_Library
PL_Process_Subfolder
PL_Validation
PL_Incremental_Sync
```

---

## 6. Phase 4: SQL Database Initialization

### 6.1 Connect to Azure SQL

**Option A: Azure Portal Query Editor**
1. Navigate to SQL database `MigrationControl` in Azure Portal
2. Click **Query editor (preview)**
3. Login with Azure AD authentication

**Option B: SSMS with Azure AD**
1. Open SQL Server Management Studio
2. Server: `sql-hydroone-migration-{env}.database.windows.net`
3. Authentication: **Azure Active Directory - Universal with MFA**

### 6.2 Run Control Table Script

Execute the contents of `sql/create_control_table.sql`. This creates:

| Object | Type | Purpose |
|--------|------|---------|
| `dbo.MigrationControl` | Table | Tracks all libraries to migrate |
| `dbo.IncrementalWatermark` | Table | High watermark for delta sync |
| `dbo.BatchLog` | Table | Batch execution tracking |
| `dbo.usp_UpdateMigrationStatus` | Stored Procedure | Update library migration status |
| `dbo.usp_LogBatchStart` | Stored Procedure | Log batch start |
| `dbo.usp_LogBatchComplete` | Stored Procedure | Log batch completion |

### 6.3 Run Audit Log Script

Execute the contents of `sql/create_audit_log_table.sql`. This creates:

| Object | Type | Purpose |
|--------|------|---------|
| `dbo.MigrationAuditLog` | Table | Per-file migration audit trail |
| `dbo.ValidationLog` | Table | Validation results |
| `dbo.usp_LogFileAudit` | Stored Procedure | Log individual file migration |
| `dbo.usp_BulkLogFileAudit` | Stored Procedure | Bulk insert file audit records |

### 6.4 Run Production Schema Updates

Execute `sql/03_production_schema_updates.sql`. This adds:

| Object | Type | Purpose |
|--------|------|---------|
| `IncrementalWatermark.DeltaLink` | Column (NVARCHAR 2000) | Stores Graph API deltaLink for true incremental sync |
| `IncrementalWatermark.DriveId` | Column (NVARCHAR 100) | Caches Graph drive ID to avoid redundant resolution |
| `dbo.usp_UpdateWatermark` | Updated Stored Proc | Now accepts @DeltaLink and @DriveId parameters |

### 6.5 Run Monitoring Queries Script

Execute the contents of `sql/monitoring_queries.sql`. This creates monitoring views and stored procedures used by the PowerShell monitoring script.

### 6.6 Verify Tables

```sql
SELECT TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'dbo'
ORDER BY TABLE_NAME;
```

Expected tables:
- `BatchLog`
- `IncrementalWatermark`
- `MigrationAuditLog`
- `MigrationControl`
- `ValidationLog`

After running production updates, verify the IncrementalWatermark table has `DeltaLink` and `DriveId` columns:
```sql
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'IncrementalWatermark'
ORDER BY ORDINAL_POSITION;
```

---

## 7. Phase 5: Permissions & Security Configuration

### 7.1 Get ADF Managed Identity

```bash
# Get the ADF managed identity principal ID
az datafactory show \
    --name "adf-hydroone-migration-{env}" \
    --resource-group "rg-hydroone-migration-{env}" \
    --query "identity.principalId" -o tsv
```

### 7.2 Grant ADF Access to Key Vault

```bash
# Set Key Vault access policy for ADF managed identity
az keyvault set-policy \
    --name "kv-hydroone-mig-{env}" \
    --object-id "<adf-principal-id>" \
    --secret-permissions get list
```

### 7.3 Grant ADF Managed Identity Access to Storage Account

The ADF Managed Identity requires **Storage Blob Data Contributor** on the storage account to write migrated files.

```bash
# Grant Storage Blob Data Contributor role to ADF Managed Identity
az role assignment create \
    --role "Storage Blob Data Contributor" \
    --assignee-object-id "<adf-principal-id>" \
    --assignee-principal-type "ServicePrincipal" \
    --scope "/subscriptions/{sub-id}/resourceGroups/rg-hydroone-migration-{env}/providers/Microsoft.Storage/storageAccounts/sthydroonemig{env}"
```

### 7.4 Grant User Access to Storage Account (Portal Browsing)

To browse and verify migrated files in the Azure Portal, the user also needs **Storage Blob Data Contributor** on the storage account.

```bash
# Grant Storage Blob Data Contributor role to the user
az role assignment create \
    --role "Storage Blob Data Contributor" \
    --assignee "<user-email-or-object-id>" \
    --scope "/subscriptions/{sub-id}/resourceGroups/rg-hydroone-migration-{env}/providers/Microsoft.Storage/storageAccounts/sthydroonemig{env}"
```

> **Note:** Without this role assignment, the user will see "You do not have permissions to list data" when trying to browse containers in the Azure Portal, even if they have Contributor on the resource group.

### 7.5 Grant ADF Access to SQL Database

Connect to SQL and run:

```sql
-- Create user for ADF managed identity
CREATE USER [adf-hydroone-migration-{env}] FROM EXTERNAL PROVIDER;

-- Grant read/write permissions
ALTER ROLE db_datareader ADD MEMBER [adf-hydroone-migration-{env}];
ALTER ROLE db_datawriter ADD MEMBER [adf-hydroone-migration-{env}];

-- Grant execute on stored procedures
GRANT EXECUTE ON SCHEMA::dbo TO [adf-hydroone-migration-{env}];
```

### 7.6 Verify Linked Service Connections

In Azure Data Factory Studio:
1. Navigate to **Manage** > **Linked services**
2. Click **Test connection** on each linked service:
   - `LS_AzureKeyVault` - Should connect to Key Vault
   - `LS_ADLS_Gen2` - Should connect to storage account
   - `LS_AzureSqlDatabase` - Should connect to SQL database
   - `LS_REST_Graph_API` - Anonymous auth (token added at runtime); verify base URL is reachable
   - `LS_HTTP_Graph_API` - Anonymous auth (token added at runtime); verify base URL is reachable

### 7.7 Partial Testing (Without SharePoint Access)

If Graph API admin consent in the SharePoint tenant is not yet available, you can still validate the following pipeline components:

**What CAN be tested:**
1. **SQL Connectivity** - Verify ADF can read/write to Azure SQL (Lookup and StoredProcedure activities)
2. **ADLS Connectivity** - Verify ADF can write to ADLS Gen2 storage
3. **Pipeline Orchestration Logic** - Verify ForEach, IfCondition, and pipeline chaining work correctly
4. **Control Table Operations** - Verify Lookup queries, status updates, and audit logging
5. **Key Vault Access** - Verify ADF can retrieve secrets
6. **Token Acquisition** - Verify the WebActivity can POST to the token endpoint (will fail with invalid credentials but confirms network connectivity)

**What CANNOT be tested without Graph API consent:**
1. Graph API file/folder enumeration
2. Actual file download from SharePoint via Graph `/content` endpoint
3. Metadata extraction from SharePoint sites and drives
4. Incremental sync (requires Graph API delta queries)

**Partial Test Steps:**

```sql
-- 1. Insert a test control record
INSERT INTO dbo.MigrationControl (
    SiteUrl, LibraryName, SiteName,
    TotalFileCount, TotalSizeBytes,
    Status, Priority, ContainerName
)
VALUES (
    '/sites/TestSite', 'TestLibrary', 'TestSite',
    0, 0, 'Pending', 1, 'sharepoint-migration'
);
```

In ADF Studio:
1. Open `PL_Master_Migration_Orchestrator` > Click **Debug**
2. The `Lookup_PendingLibraries` activity should **succeed** (proving SQL connectivity)
3. The `ForEach_Library` will attempt Graph API calls and **fail** (expected without consent)
4. Verify in SQL that the control table status was updated to 'InProgress'

```sql
-- 2. Verify the pipeline touched the control table
SELECT Id, SiteUrl, LibraryName, Status, MigrationStartTime
FROM dbo.MigrationControl
WHERE LibraryName = 'TestLibrary';
```

This confirms the infrastructure (ADF -> SQL -> ADLS) is wired correctly. Once admin consent is granted in the SharePoint tenant, the Graph API activities will start working without any code changes.

---

## 8. Phase 6: Control Table Population

### 8.1 Manual Population (Small Scale)

For testing, manually insert a library entry:

```sql
INSERT INTO dbo.MigrationControl (
    SiteUrl, LibraryName, SiteName,
    TotalFileCount, TotalSizeBytes,
    Status, Priority, ContainerName
)
VALUES (
    '/sites/TestSite',           -- SharePoint site relative URL
    'Documents',                  -- Library name
    'TestSite',                   -- Friendly site name
    100,                          -- Estimated file count
    1073741824,                   -- Estimated size in bytes (1 GB)
    'Pending',                    -- Initial status
    1,                            -- Priority (1 = highest)
    'sharepoint-migration'        -- ADLS container name
);
```

### 8.2 Automated Population (Full Scale)

```powershell
.\scripts\Populate-ControlTable.ps1 `
    -SharePointTenantUrl "https://{tenant}.sharepoint.com" `
    -SqlServerName "sql-hydroone-migration-{env}" `
    -SqlDatabaseName "MigrationControl" `
    -UseInteractiveAuth
```

This script:
1. Connects to SharePoint Online
2. Enumerates all site collections
3. Lists all document libraries per site
4. Gets file counts and sizes
5. Inserts records into `MigrationControl` table

### 8.3 Verify Control Table

```sql
SELECT
    SiteUrl,
    LibraryName,
    TotalFileCount,
    CAST(TotalSizeBytes / 1073741824.0 AS DECIMAL(10,2)) AS SizeGB,
    Status,
    Priority
FROM dbo.MigrationControl
ORDER BY Priority, TotalSizeBytes DESC;
```

---

## 9. Phase 7: Pilot Migration

### 9.1 Select Pilot Library

Choose a small library (< 1 GB, < 100 files) for initial testing.

```sql
-- Find smallest library for pilot
SELECT TOP 1 Id, SiteUrl, LibraryName, TotalFileCount,
    CAST(TotalSizeBytes / 1048576.0 AS DECIMAL(10,2)) AS SizeMB
FROM dbo.MigrationControl
WHERE Status = 'Pending'
ORDER BY TotalSizeBytes ASC;
```

### 9.2 Run PL_Migrate_Single_Library

1. Open **Azure Data Factory Studio** > **Author** > **Pipelines**
2. Select `PL_Migrate_Single_Library`
3. Click **Debug**
4. Enter parameters:

| Parameter | Value | Notes |
|-----------|-------|-------|
| SiteUrl | `/sites/TestSite` | SharePoint site relative URL |
| LibraryName | `Documents` | Library name |
| ControlTableId | `1` (from control table) | |
| BatchId | `PILOT-001` | |
| ContainerName | `sharepoint-migration` | |
| SharePointTenantUrl | `https://{tenant}.sharepoint.com` | |
| PageSize | `200` | Items per delta page |
| ThrottleDelaySeconds | `2` | Wait between pages |
| CopyBatchCount | `10` | Concurrent file copies |
| ServicePrincipalId | `3a412ede-620a-4f21-8501-ef62a5161dc2` | App registration client ID (defaults to test env value) |
| ServicePrincipalTenantId | `5447cfcd-3af1-439a-8157-760bd52b12df` | SharePoint tenant ID for token acquisition (defaults to test env value) |
| KeyVaultUrl | `https://kv-hydroone-test2.vault.azure.net/` | Key Vault URL for secret retrieval (defaults to test env value) |

5. Click **OK** to start

### 9.3 Monitor Pilot

**In ADF Monitor:**
1. Go to **Monitor** > **Pipeline runs**
2. Click on the running pipeline
3. View individual activity status

**In SQL:**
```sql
-- Check migration status
SELECT * FROM dbo.MigrationControl WHERE Id = 1;

-- Check file-level audit
SELECT MigrationStatus, COUNT(*) AS FileCount,
    SUM(FileSizeBytes) / 1048576.0 AS TotalMB
FROM dbo.MigrationAuditLog
WHERE BatchId = 'PILOT-001'
GROUP BY MigrationStatus;
```

### 9.4 Validate Pilot Results

```sql
-- Compare source vs destination file count
SELECT
    mc.LibraryName,
    mc.TotalFileCount AS ExpectedFiles,
    COUNT(DISTINCT al.SourcePath) AS MigratedFiles,
    SUM(CASE WHEN al.MigrationStatus = 'Success' THEN 1 ELSE 0 END) AS SuccessCount,
    SUM(CASE WHEN al.MigrationStatus = 'Failed' THEN 1 ELSE 0 END) AS FailedCount
FROM dbo.MigrationControl mc
LEFT JOIN dbo.MigrationAuditLog al ON al.BatchId = 'PILOT-001'
WHERE mc.Id = 1
GROUP BY mc.LibraryName, mc.TotalFileCount;
```

**Verify in ADLS:**
1. Go to Storage Account > Containers > `sharepoint-migration`
2. Navigate to the site/library folder
3. Verify files exist and sizes match

> **Note:** You must have **Storage Blob Data Contributor** role on the storage account to browse files in the Azure Portal (see [Section 7.4](#74-grant-user-access-to-storage-account-portal-browsing)).

### 9.5 Production Feature Testing

After verifying the basic pilot run succeeds, test the four production features individually:

#### Test 1: Pagination (Small PageSize)

Run `PL_Migrate_Single_Library` with `PageSize = 3` to force the Until loop to iterate multiple times:

1. In ADF Studio, Debug `PL_Migrate_Single_Library` with:
   | Parameter | Value | Why |
   |-----------|-------|-----|
   | PageSize | **3** | Forces multiple Until loop iterations |
   | CopyBatchCount | 2 | Low parallelism for easy debugging |
   | ThrottleDelaySeconds | 1 | Short delay for testing |

2. In the **Monitor** tab, drill into `Until_AllPagesProcessed`:
   - Verify it runs **multiple iterations** (at least 2 if library has >3 items)
   - Each iteration: `Get_DeltaPage` → `Filter_PageFiles` → `ForEach_CopyFile`
   - Last iteration: `If_HasNextPage` takes the **False** branch
   - `Set_DeltaLink` captures the `@odata.deltaLink` URL

**Pass criteria:** Until loop completes with multiple iterations; all files copied.

#### Test 2: Deep Folder Traversal

Create a folder structure in SharePoint with depth >2:

```
Shared Documents/
├── RootFile.docx
├── FolderA/
│   └── SubFolderA1/
│       └── DeepFile.pdf           ← depth 2
│           └── SubSubFolder/
│               └── VeryDeepFile.txt  ← depth 3
```

Run migration and verify in ADLS:

```powershell
az storage blob list --account-name sthydroonemigtest `
  --container-name sharepoint-migration `
  --prefix "SalesAndMarketing/Shared Documents/" `
  --output table
```

**Pass criteria:** Files at all folder depths appear in ADLS with correct paths. The old POC would have missed files at depth >1.

#### Test 3: Token Refresh

To test without waiting 45 minutes, temporarily lower the threshold in `PL_Migrate_Single_Library`:

Change the `If_TokenExpiring` expression from `2700` (45 min) to `60` (1 min):
```
@greater(div(sub(ticks(utcNow()), ticks(variables('TokenAcquiredTime'))), 10000000), 60)
```

Run against a library with enough items that pagination takes >1 minute.

**Pass criteria:** `If_TokenExpiring` takes the True branch on later iterations; `Refresh_AccessToken` succeeds; subsequent copies still work.

> **Important:** Revert threshold to `2700` after testing.

#### Test 4: Incremental Sync with DeltaLink

After an initial migration completes:

1. Verify deltaLink was stored:
   ```sql
   SELECT SiteUrl, LibraryName, DeltaLink, DriveId, LastSyncTime
   FROM dbo.IncrementalWatermark;
   ```

2. Add a new file to the SharePoint library

3. Run `PL_Incremental_Sync` with `PageSize = 5`

4. Verify:
   - Pipeline used the stored `DeltaLink` (not a fresh `/root/delta` call)
   - Only the new file was copied
   - `IncrementalWatermark.DeltaLink` was updated
   - `MigrationAuditLog` has new entry with `MigrationStatus = 'IncrementalSync'`

5. Run incremental sync again **without** changing anything:
   - Should complete with 0 files copied

**Pass criteria:** DeltaLink reused; only changed files synced; no-change run is a no-op.

#### Production Feature Test Checklist

| # | Test | Pass Criteria | Status |
|---|------|---------------|--------|
| 1 | Pagination | Until loop runs multiple iterations with PageSize=3 | [ ] |
| 2 | Deep folders | Files at depth >2 appear in ADLS with correct paths | [ ] |
| 3 | Token refresh | If_TokenExpiring fires and refreshes token | [ ] |
| 4 | DeltaLink persistence | IncrementalWatermark.DeltaLink is non-null after migration | [ ] |
| 5 | Incremental sync reuse | Only new/modified files copied on second run | [ ] |
| 6 | No-change run | Incremental sync completes with 0 files when nothing changed | [ ] |
| 7 | Audit trail | All files logged in MigrationAuditLog with correct paths | [ ] |
| 8 | Error handling | Failed files logged with error details, status set to Failed | [ ] |

### 9.6 Database Reset for Fresh End-to-End Testing

When you need to re-run a full end-to-end test from scratch (e.g., after pipeline changes), reset the database to a clean state. This clears all audit/log data, reseeds identity columns, and inserts a fresh `Pending` row for the target library.

```sql
-- =============================================================
-- DATABASE RESET FOR FRESH END-TO-END TESTING
-- WARNING: This deletes ALL migration data. Use only in dev/test.
-- =============================================================

-- 1. Clear all tables (order matters due to potential FK references)
DELETE FROM dbo.MigrationAuditLog;
DELETE FROM dbo.ValidationLog;
DELETE FROM dbo.BatchLog;
DELETE FROM dbo.SyncLog;
DELETE FROM dbo.IncrementalWatermark;
DELETE FROM dbo.MigrationControl;

-- 2. Reseed identity columns back to 0
DBCC CHECKIDENT ('dbo.MigrationAuditLog', RESEED, 0);
DBCC CHECKIDENT ('dbo.ValidationLog', RESEED, 0);
DBCC CHECKIDENT ('dbo.BatchLog', RESEED, 0);
DBCC CHECKIDENT ('dbo.MigrationControl', RESEED, 0);

-- 3. Insert a fresh Pending row for the target library
INSERT INTO dbo.MigrationControl (
    SiteUrl, LibraryName, SiteName,
    TotalFileCount, TotalSizeBytes,
    Status, Priority, ContainerName
)
VALUES (
    '/sites/SalesAndMarketing',       -- SharePoint site relative URL
    'Shared Documents',               -- Library name
    'SalesAndMarketing',              -- Friendly site name
    0, 0,                             -- Counts will be populated by pipeline
    'Pending',                        -- Initial status
    1,                                -- Priority
    'sharepoint-migration'            -- ADLS container name
);

-- 4. Verify clean state
SELECT 'MigrationControl' AS TableName, COUNT(*) AS RowCount FROM dbo.MigrationControl
UNION ALL SELECT 'MigrationAuditLog', COUNT(*) FROM dbo.MigrationAuditLog
UNION ALL SELECT 'ValidationLog', COUNT(*) FROM dbo.ValidationLog
UNION ALL SELECT 'BatchLog', COUNT(*) FROM dbo.BatchLog
UNION ALL SELECT 'IncrementalWatermark', COUNT(*) FROM dbo.IncrementalWatermark;
```

> **Note:** Adjust the `SiteUrl`, `LibraryName`, and `SiteName` values in step 3 to match your target SharePoint library. If `SyncLog` does not have an identity column, skip its `DBCC CHECKIDENT` line.

---

## 10. Phase 8: Full Migration Execution

### 10.1 Trigger Master Pipeline

**Option A: Manual trigger via ADF Studio**
1. Open `PL_Master_Migration_Orchestrator`
2. Click **Add trigger** > **Trigger now**
3. Set parameters:

| Parameter | Value |
|-----------|-------|
| BatchSize | 10 |
| ParallelLibraries | 4 |
| MaxRetries | 3 |
| TargetContainerName | `sharepoint-migration` |
| PageSize | 200 |
| CopyBatchCount | 10 |
| ThrottleDelaySeconds | 2 |

**Option B: PowerShell**
```powershell
$params = @{
    BatchSize = 10
    ParallelLibraries = 4
    MaxRetries = 3
    TargetContainerName = "sharepoint-migration"
    PageSize = 200
    CopyBatchCount = 10
    ThrottleDelaySeconds = 2
}

Invoke-AzDataFactoryV2Pipeline `
    -ResourceGroupName "rg-hydroone-migration-{env}" `
    -DataFactoryName "adf-hydroone-migration-{env}" `
    -PipelineName "PL_Master_Migration_Orchestrator" `
    -Parameter $params
```

### 10.2 Recommended Batch Schedule

| Phase | Days | Time | BatchSize | Parallelism | Data Target |
|-------|------|------|-----------|-------------|-------------|
| Week 1 | Mon-Fri | 8PM-6AM | 5 | 2 | ~2 TB |
| Week 2 | Mon-Fri + Weekend | 8PM-6AM / All day | 10 | 4 | ~5 TB |
| Week 3-4 | Mon-Fri + Weekend | 8PM-6AM / All day | 15 | 6 | ~8 TB |
| Week 5-6 | Mon-Fri + Weekend | 8PM-6AM / All day | 20 | 8 | ~10 TB |

### 10.3 Enable Scheduled Triggers

```powershell
# Enable evening bulk migration trigger
Start-AzDataFactoryV2Trigger `
    -ResourceGroupName "rg-hydroone-migration-{env}" `
    -DataFactoryName "adf-hydroone-migration-{env}" `
    -Name "TR_Evening_BulkMigration"
```

### 10.4 Daily Progress Check

```sql
-- Daily migration progress dashboard
SELECT
    CAST(GETUTCDATE() AS DATE) AS ReportDate,
    COUNT(CASE WHEN Status = 'Completed' THEN 1 END) AS CompletedLibraries,
    COUNT(CASE WHEN Status = 'InProgress' THEN 1 END) AS InProgressLibraries,
    COUNT(CASE WHEN Status = 'Pending' THEN 1 END) AS PendingLibraries,
    COUNT(CASE WHEN Status = 'Failed' THEN 1 END) AS FailedLibraries,
    CAST(SUM(CASE WHEN Status = 'Completed' THEN MigratedSizeBytes ELSE 0 END) / 1099511627776.0 AS DECIMAL(10,2)) AS CompletedTB,
    CAST(SUM(TotalSizeBytes) / 1099511627776.0 AS DECIMAL(10,2)) AS TotalTB,
    CAST(SUM(CASE WHEN Status = 'Completed' THEN MigratedSizeBytes ELSE 0 END) * 100.0 / NULLIF(SUM(TotalSizeBytes), 0) AS DECIMAL(5,1)) AS PercentComplete
FROM dbo.MigrationControl;
```

---

## 11. Phase 9: Validation & Reconciliation

### 11.1 Run Validation Pipeline

1. In ADF Studio, trigger `PL_Validation`
2. Parameters:

| Parameter | Value |
|-----------|-------|
| SharePointTenantUrl | `https://{tenant}.sharepoint.com` |
| ContainerName | `sharepoint-migration` |

### 11.2 File Count Reconciliation

```sql
SELECT
    mc.SiteUrl,
    mc.LibraryName,
    mc.TotalFileCount AS SourceCount,
    COUNT(DISTINCT al.SourcePath) AS MigratedCount,
    mc.TotalFileCount - COUNT(DISTINCT al.SourcePath) AS Difference,
    CASE
        WHEN ABS(mc.TotalFileCount - COUNT(DISTINCT al.SourcePath)) <= mc.TotalFileCount * 0.01
        THEN 'PASS' ELSE 'REVIEW'
    END AS Status
FROM dbo.MigrationControl mc
LEFT JOIN dbo.MigrationAuditLog al
    ON al.SiteName = mc.SiteName
    AND al.LibraryName = mc.LibraryName
    AND al.MigrationStatus = 'Success'
WHERE mc.Status = 'Completed'
GROUP BY mc.SiteUrl, mc.LibraryName, mc.TotalFileCount
ORDER BY Difference DESC;
```

### 11.3 Size Reconciliation

```sql
SELECT
    SUM(TotalSizeBytes) / 1099511627776.0 AS SourceTB,
    SUM(MigratedSizeBytes) / 1099511627776.0 AS MigratedTB,
    (SUM(MigratedSizeBytes) * 100.0 / NULLIF(SUM(TotalSizeBytes), 0)) AS PercentComplete
FROM dbo.MigrationControl
WHERE Status = 'Completed';
```

### 11.4 Error Summary

```sql
SELECT
    ErrorCode,
    COUNT(*) AS ErrorCount,
    COUNT(DISTINCT LibraryName) AS AffectedLibraries,
    MIN([Timestamp]) AS FirstOccurrence,
    MAX([Timestamp]) AS LastOccurrence
FROM dbo.MigrationAuditLog
WHERE MigrationStatus = 'Failed'
GROUP BY ErrorCode
ORDER BY ErrorCount DESC;
```

### 11.5 Sign-Off Checklist

| # | Validation Item | Status | Notes |
|---|----------------|--------|-------|
| 1 | All libraries Status = 'Completed' | [ ] | |
| 2 | File count matches within 1% tolerance | [ ] | |
| 3 | Total size matches within 5% tolerance | [ ] | |
| 4 | No critical files missing | [ ] | |
| 5 | Spot-check samples pass verification | [ ] | |
| 6 | Validation pipeline shows "Validated" | [ ] | |
| 7 | Audit log reviewed for errors | [ ] | |
| 8 | Business stakeholder sign-off | [ ] | |
| 9 | DeltaLink stored for all completed libraries | [ ] | |
| 10 | Pagination tested with small PageSize | [ ] | |
| 11 | Deep folder files migrated correctly | [ ] | |
| 12 | Token refresh verified for long-running libraries | [ ] | |

---

## 12. Phase 10: Incremental Sync Setup

### 12.1 Enable Incremental Sync

```sql
UPDATE dbo.MigrationControl
SET EnableIncrementalSync = 1
WHERE Status = 'Completed'
AND ValidationStatus = 'Validated';
```

### 12.2 Initialize Watermark Table

```sql
INSERT INTO dbo.IncrementalWatermark (SiteUrl, LibraryName, LastModifiedDate, LastSyncTime)
SELECT SiteUrl, LibraryName, MigrationEndTime, GETUTCDATE()
FROM dbo.MigrationControl
WHERE EnableIncrementalSync = 1;
```

### 12.3 Start Incremental Sync Trigger

```powershell
Start-AzDataFactoryV2Trigger `
    -ResourceGroupName "rg-hydroone-migration-{env}" `
    -DataFactoryName "adf-hydroone-migration-{env}" `
    -Name "TR_TumblingWindow_IncrementalSync"
```

---

## 13. Monitoring & Operations

### 13.1 Real-Time Monitoring

```powershell
.\scripts\Monitor-Migration.ps1 `
    -ResourceGroupName "rg-hydroone-migration-{env}" `
    -DataFactoryName "adf-hydroone-migration-{env}" `
    -SqlServerName "sql-hydroone-migration-{env}" `
    -SqlDatabaseName "MigrationControl" `
    -ContinuousMonitor
```

### 13.2 Key SQL Monitoring Queries

**Overall Progress:**
```sql
SELECT Status, COUNT(*) AS Libraries,
    CAST(SUM(TotalSizeBytes) / 1099511627776.0 AS DECIMAL(10,2)) AS TotalTB
FROM dbo.MigrationControl
GROUP BY Status;
```

**Throttling Detection:**
```sql
SELECT
    CAST([Timestamp] AS DATE) AS [Date],
    DATEPART(HOUR, [Timestamp]) AS [Hour],
    COUNT(*) AS ThrottleCount
FROM dbo.MigrationAuditLog
WHERE ErrorCode = '429'
GROUP BY CAST([Timestamp] AS DATE), DATEPART(HOUR, [Timestamp])
ORDER BY [Date] DESC, [Hour];
```

**Current Throughput:**
```sql
SELECT
    CAST([Timestamp] AS DATE) AS [Date],
    COUNT(*) AS FilesCopied,
    CAST(SUM(FileSizeBytes) / 1073741824.0 AS DECIMAL(10,2)) AS GB_Copied,
    CAST(SUM(FileSizeBytes) / 1073741824.0 / 24 AS DECIMAL(10,2)) AS GB_Per_Hour
FROM dbo.MigrationAuditLog
WHERE MigrationStatus = 'Success'
GROUP BY CAST([Timestamp] AS DATE)
ORDER BY [Date] DESC;
```

### 13.3 Pause Migration

```powershell
# Stop triggers
Stop-AzDataFactoryV2Trigger `
    -ResourceGroupName "rg-hydroone-migration-{env}" `
    -DataFactoryName "adf-hydroone-migration-{env}" `
    -Name "TR_Evening_BulkMigration"
```

### 13.4 Resume Migration

```sql
-- Reset failed libraries for retry
UPDATE dbo.MigrationControl
SET Status = 'Pending', RetryCount = 0, ErrorMessage = NULL
WHERE Status = 'Failed' AND RetryCount >= 3;
```

Then re-enable the trigger or manually trigger the master pipeline.

---

## 14. Troubleshooting Guide

### 14.1 Common Errors

| Error | Cause | Resolution |
|-------|-------|------------|
| HTTP 401 | Token expired/invalid or wrong tenant | Regenerate client secret in SharePoint tenant, update Key Vault; verify `ServicePrincipalTenantId` points to SharePoint tenant |
| HTTP 403 | Insufficient Graph API permissions | Verify admin consent granted in SharePoint tenant for Sites.Read.All and Files.Read.All |
| HTTP 404 | File deleted after enumeration or invalid Graph path | Log and skip (expected for deletions); verify site-id and drive-id are correct |
| HTTP 429 | Graph API / SharePoint throttling | Reduce parallelism, wait, contact Microsoft |
| HTTP 503 | Graph API / SharePoint unavailable | Retry automatically, check service health |
| Timeout | Large file or slow network | Increase timeout settings |
| AADSTS700016 | App not found in tenant | Verify app registration exists in the SharePoint tenant, not the MCAPS tenant |
| AADSTS7000215 | Invalid client secret | Regenerate secret in SharePoint tenant app registration and update Key Vault |
| Circular reference | Pipeline self-referencing | Already fixed in templates |

### 14.2 Cross-Tenant Authentication Failures

If token acquisition fails:
1. Verify the app registration exists in the **SharePoint tenant** (`5447cfcd-3af1-439a-8157-760bd52b12df`)
2. Verify the `ServicePrincipalTenantId` pipeline parameter points to the SharePoint tenant
3. Verify the client secret stored in Key Vault matches the current secret on the app registration
4. Verify admin consent was granted in the SharePoint tenant (not the MCAPS tenant)
5. Check the token endpoint URL: `https://login.microsoftonline.com/5447cfcd-3af1-439a-8157-760bd52b12df/oauth2/v2.0/token`
6. Verify the scope is `https://graph.microsoft.com/.default`

### 14.3 Linked Service Connection Failures

**Key Vault:** Verify ADF managed identity has Key Vault access policy (get, list)
**Storage:** Verify ADF managed identity has Storage Blob Data Contributor role
**SQL:** Verify ADF user created in SQL with proper permissions
**Graph API REST/HTTP:** These use Anonymous auth at the linked service level; the Bearer token is injected at runtime by the pipeline. Verify that the token acquisition WebActivity is succeeding.

### 14.4 Pipeline Debug Steps

1. Check ADF Monitor for error messages
2. Click on failed activity for details
3. Check Input/Output tabs for request/response data
4. For token acquisition failures: check the WebActivity output for the OAuth2 error response
5. For Graph API failures: check the HTTP status code and response body for detailed error messages
6. Check SQL audit log for file-level errors
7. Verify linked service connections are working

---

## 15. Rollback Procedures

### 15.1 Key Principle

**SharePoint data is READ-ONLY during migration.** No changes are made to the source. Full rollback = continue using SharePoint as before.

### 15.2 Rollback Steps

1. Stop all triggers and cancel running pipelines
2. Notify stakeholders
3. Document issues and export audit logs
4. If ADLS data is corrupted: delete container contents and re-migrate
5. Reset control table for fresh start if needed

---

## 16. Appendix

### 16.1 Resource Naming Convention

| Resource | Pattern | Example |
|----------|---------|---------|
| Resource Group | `rg-hydroone-migration-{env}` | `rg-hydroone-migration-prod` |
| Storage Account | `sthydroonemig{env}` | `sthydroonemigprod` |
| Data Factory | `adf-hydroone-migration-{env}` | `adf-hydroone-migration-prod` |
| Key Vault | `kv-hydroone-mig-{env}` | `kv-hydroone-mig-prod` |
| SQL Server | `sql-hydroone-migration-{env}` | `sql-hydroone-migration-prod` |

### 16.2 Test Environment Resources (Current Deployment)

| Resource | Value |
|----------|-------|
| Subscription | `671b1321-4407-420b-b877-97cd40ba898a` |
| ADF Tenant (MCAPS) | `fe64e912-f83c-44e9-9389-f66812c7fa57` |
| SharePoint Tenant | `5447cfcd-3af1-439a-8157-760bd52b12df` |
| Resource Group | `rg-hydroone-migration-test` |
| Storage Account | `sthydroonemigtest` |
| SQL Server | `sql-hydroone-migration-test.database.windows.net` |
| Key Vault | `kv-hydroone-test2` |
| Data Factory | `adf-hydroone-migration-test` |
| App Registration (in SharePoint tenant) | `3a412ede-620a-4f21-8501-ef62a5161dc2` |
| ADF Managed Identity | `b509d6d6-4d95-4e74-9de6-952b764556d3` |

### 16.3 PL_Migrate_Single_Library Default Parameters (Test Environment)

| Parameter | Default Value | Description |
|-----------|---------------|-------------|
| ServicePrincipalId | `3a412ede-620a-4f21-8501-ef62a5161dc2` | App registration client ID in SharePoint tenant |
| ServicePrincipalTenantId | `5447cfcd-3af1-439a-8157-760bd52b12df` | SharePoint tenant ID for OAuth2 token acquisition |
| KeyVaultUrl | `https://kv-hydroone-test2.vault.azure.net/` | Key Vault URL for retrieving client secret |

### 16.4 Cost Estimation (Monthly)

| Resource | Tier | Estimated Cost |
|----------|------|----------------|
| ADLS Gen2 (25 TB, Hot) | Standard LRS | ~$500-600 |
| Azure SQL | S1 | ~$30 |
| Data Factory | Pay-as-you-go | ~$50-200 |
| Key Vault | Standard | ~$5 |
| **Total** | | **~$585-835/month** |
