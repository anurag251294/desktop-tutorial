# Hydro One SharePoint to Azure Migration - End-to-End Deployment Guide

## Document Information

| Field | Value |
|-------|-------|
| Project | Hydro One SharePoint to Azure Data Lake Migration |
| Version | 1.0 |
| Author | PwC Azure Data Engineering Team |
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
SharePoint Online (Source)
        |
        | REST API (HTTPS/OAuth2)
        v
Azure Data Factory (Orchestration)
        |
        |--- Managed Identity ---> ADLS Gen2 (Destination)
        |--- Managed Identity ---> Azure SQL (Control/Audit)
        |--- Managed Identity ---> Key Vault (Secrets)
        |--- Service Principal --> SharePoint Online
```

### 1.3 Key Components

| Component | Resource Name | Purpose |
|-----------|---------------|---------|
| Resource Group | `rg-hydroone-migration-{env}` | Container for all resources |
| ADLS Gen2 | `sthydroonemig{env}` | Destination storage with hierarchical namespace |
| Azure SQL | `sql-hydroone-migration-{env}` | Migration control and audit tables |
| Key Vault | `kv-hydroone-mig-{env}` | Stores SharePoint client secret |
| Data Factory | `adf-hydroone-migration-{env}` | Pipeline orchestration engine |
| Azure AD App | `HydroOne-SPO-Migration` | Service principal for SharePoint access |

### 1.4 Deployment Environments

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

- [ ] Application Administrator or Global Administrator role (for app registration)
- [ ] **CRITICAL: Global Administrator or Privileged Role Administrator** is required to grant admin consent for SharePoint API permissions. Without admin consent, the service principal **cannot access SharePoint Online** and no migration pipelines will function. This is a **hard blocker** that must be resolved before any testing begins.

> **Action Required for Hydro One IT Admin:**
> A Global Administrator must grant admin consent for the registered application's SharePoint API permissions. See [Section 4.5](#45-grant-admin-consent-critical) for detailed steps.

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

- Outbound HTTPS (443) to `*.sharepoint.com`
- Outbound HTTPS (443) to `*.azure.com`, `*.azure.net`
- No firewall blocking Azure Data Factory managed runtime IPs

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
    --tags "Project=HydroOneMigration" "Environment={env}" "Owner=PwC"
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

# Allow Azure services firewall rule
az sql server firewall-rule create \
    --name "AllowAzureServices" \
    --server "sql-hydroone-migration-{env}" \
    --resource-group "rg-hydroone-migration-{env}" \
    --start-ip-address 0.0.0.0 \
    --end-ip-address 0.0.0.0

# Allow your client IP (for SQL management)
az sql server firewall-rule create \
    --name "AllowClientIP" \
    --server "sql-hydroone-migration-{env}" \
    --resource-group "rg-hydroone-migration-{env}" \
    --start-ip-address "<your-ip>" \
    --end-ip-address "<your-ip>"
```

### 3.6 Create Azure Key Vault

```bash
az keyvault create \
    --name "kv-hydroone-mig-{env}" \
    --resource-group "rg-hydroone-migration-{env}" \
    --location "canadacentral" \
    --enable-rbac-authorization false \
    --sku "standard"
```

---

## 4. Phase 2: Azure AD & SharePoint Configuration

### 4.1 Register Azure AD Application

```bash
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

### 4.4 Add SharePoint API Permissions

```bash
# SharePoint Online - Sites.FullControl.All (Application)
az ad app permission add \
    --id "<app-id>" \
    --api "00000003-0000-0ff1-ce00-000000000000" \
    --api-permissions "678536fe-1083-478a-9c59-b99265e6b0d3=Role"

# SharePoint Online - Sites.ReadWrite.All (Application)
az ad app permission add \
    --id "<app-id>" \
    --api "00000003-0000-0ff1-ce00-000000000000" \
    --api-permissions "fbcd29d2-fcca-4405-aded-518d457caae4=Role"

# Microsoft Graph - Sites.ReadWrite.All (Application)
az ad app permission add \
    --id "<app-id>" \
    --api "00000003-0000-0000-c000-000000000000" \
    --api-permissions "9492366f-7969-46a4-8d15-ed1a20078fff=Role"
```

### 4.5 Grant Admin Consent (CRITICAL)

> **This step requires a Global Administrator or Privileged Role Administrator.**
> Without admin consent, all SharePoint API permissions remain in "Not granted" status and the migration pipelines **will not work**. This is a hard blocker.

**Required Permissions to Consent:**

| API | Permission | Type | Purpose |
|-----|-----------|------|---------|
| SharePoint | Sites.FullControl.All | Application | Full read/write access to all site collections |
| SharePoint | Sites.ReadWrite.All | Application | Read/write access to files and lists |
| Microsoft Graph | Sites.ReadWrite.All | Application | Graph API access for metadata operations |

**Option A: Azure Portal (Recommended)**
1. Sign in to [Azure Portal](https://portal.azure.com) as a **Global Administrator**
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
# Connect as Global Admin
Connect-MgGraph -Scopes "Application.ReadWrite.All", "AppRoleAssignment.ReadWrite.All"

# Grant consent for the service principal
$spId = "<service-principal-object-id>"

# SharePoint Sites.FullControl.All
New-MgServicePrincipalAppRoleAssignment -ServicePrincipalId $spId `
    -PrincipalId $spId `
    -ResourceId "<sharepoint-sp-object-id>" `
    -AppRoleId "678536fe-1083-478a-9c59-b99265e6b0d3"
```

**Verification:**
After granting consent, verify in Azure Portal > App registrations > API permissions that all entries show **"Granted for {tenant}"** (green checkmark), not "Not granted".

> **If consent cannot be granted:** See [Section 7.6 - Alternative: ADF Managed Identity for SharePoint](#76-alternative-adf-managed-identity-for-sharepoint) for an alternative authentication approach.

### 4.6 Store Secret in Key Vault

```bash
az keyvault secret set \
    --vault-name "kv-hydroone-mig-{env}" \
    --name "sharepoint-client-secret" \
    --value "<client-secret-value>"

# Store the App ID as well
az keyvault secret set \
    --vault-name "kv-hydroone-mig-{env}" \
    --name "sharepoint-client-id" \
    --value "<app-id>"

# Store the Tenant ID
az keyvault secret set \
    --vault-name "kv-hydroone-mig-{env}" \
    --name "tenant-id" \
    --value "<tenant-id>"
```

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
        tenantId="<tenant-id>" \
        keyVaultName="kv-hydroone-mig-{env}" \
        storageAccountName="sthydroonemig{env}" \
        sqlServerName="sql-hydroone-migration-{env}" \
        sqlDatabaseName="MigrationControl"
```

This deploys:
- **ADF instance** with system-assigned managed identity
- **5 Linked Services**: Key Vault, SharePoint REST, SharePoint HTTP, ADLS Gen2, Azure SQL
- **6 Datasets**: SharePoint Binary HTTP, ADLS Binary Sink, ADLS Parquet Metadata, SQL MigrationControl, SQL AuditLog

### 5.2 Deploy Pipelines

Deploy each pipeline ARM template:

```bash
# 1. Deploy PL_Process_Subfolder (no dependencies)
az deployment group create \
    --resource-group "rg-hydroone-migration-{env}" \
    --template-file "adf-templates/pipelines/PL_Process_Subfolder.json" \
    --parameters factoryName="adf-hydroone-migration-{env}" \
    --name "pipeline-subfolder"

# 2. Deploy PL_Migrate_Single_Library (depends on PL_Process_Subfolder)
az deployment group create \
    --resource-group "rg-hydroone-migration-{env}" \
    --template-file "adf-templates/pipelines/PL_Migrate_Single_Library.json" \
    --parameters factoryName="adf-hydroone-migration-{env}" \
    --name "pipeline-single-library"

# 3. Deploy PL_Validation
az deployment group create \
    --resource-group "rg-hydroone-migration-{env}" \
    --template-file "adf-templates/pipelines/PL_Validation.json" \
    --parameters factoryName="adf-hydroone-migration-{env}" \
    --name "pipeline-validation"

# 4. Deploy PL_Master_Migration_Orchestrator (depends on PL_Migrate_Single_Library)
az deployment group create \
    --resource-group "rg-hydroone-migration-{env}" \
    --template-file "adf-templates/pipelines/PL_Master_Migration_Orchestrator.json" \
    --parameters factoryName="adf-hydroone-migration-{env}" \
    --name "pipeline-master"

# 5. Deploy PL_Incremental_Sync
az deployment group create \
    --resource-group "rg-hydroone-migration-{env}" \
    --template-file "adf-templates/pipelines/PL_Incremental_Sync.json" \
    --parameters factoryName="adf-hydroone-migration-{env}" \
    --name "pipeline-incremental"
```

### 5.3 Verify Deployment

```bash
# List all deployed pipelines
az rest --method GET \
    --url "https://management.azure.com/subscriptions/{sub-id}/resourceGroups/rg-hydroone-migration-{env}/providers/Microsoft.DataFactory/factories/adf-hydroone-migration-{env}/pipelines?api-version=2018-06-01" \
    --query "value[].name" -o table
```

Expected output:
```
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

### 6.4 Run Monitoring Queries Script

Execute the contents of `sql/monitoring_queries.sql`. This creates monitoring views and stored procedures used by the PowerShell monitoring script.

### 6.5 Verify Tables

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

### 7.3 Grant ADF Access to Storage Account

```bash
# Grant Storage Blob Data Contributor role
az role assignment create \
    --role "Storage Blob Data Contributor" \
    --assignee-object-id "<adf-principal-id>" \
    --assignee-principal-type "ServicePrincipal" \
    --scope "/subscriptions/{sub-id}/resourceGroups/rg-hydroone-migration-{env}/providers/Microsoft.Storage/storageAccounts/sthydroonemig{env}"
```

### 7.4 Grant ADF Access to SQL Database

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

### 7.5 Verify Linked Service Connections

In Azure Data Factory Studio:
1. Navigate to **Manage** > **Linked services**
2. Click **Test connection** on each linked service:
   - `LS_AzureKeyVault` - Should connect to Key Vault
   - `LS_ADLS_Gen2` - Should connect to storage account
   - `LS_AzureSqlDatabase` - Should connect to SQL database
   - `LS_SharePointOnline_REST` - Should connect to SharePoint (requires admin consent first)

### 7.6 Alternative: ADF Managed Identity for SharePoint

If service principal admin consent is not available, the ADF Managed Identity can be granted SharePoint access directly using Microsoft Graph PowerShell. This still requires a **Global Administrator** but uses the ADF's own identity rather than a separate app registration.

```powershell
# Connect as Global Admin
Connect-MgGraph -Scopes "AppRoleAssignment.ReadWrite.All"

# Get ADF Managed Identity service principal
$adfMsiId = "<adf-managed-identity-principal-id>"  # From section 7.1

# Get SharePoint Online service principal
$spoSp = Get-MgServicePrincipal -Filter "displayName eq 'Office 365 SharePoint Online'"

# Grant Sites.FullControl.All to ADF MSI
$appRole = $spoSp.AppRoles | Where-Object { $_.Value -eq "Sites.FullControl.All" }
New-MgServicePrincipalAppRoleAssignment `
    -ServicePrincipalId $adfMsiId `
    -PrincipalId $adfMsiId `
    -ResourceId $spoSp.Id `
    -AppRoleId $appRole.Id
```

> **Note:** The ADF pipelines already use MSI authentication for SharePoint WebActivity calls. If this approach is used, the Key Vault linked service for client secret is not needed for SharePoint access.

### 7.7 Partial Testing (Without SharePoint Access)

If SharePoint admin consent is not yet available, you can still validate the following pipeline components:

**What CAN be tested:**
1. **SQL Connectivity** - Verify ADF can read/write to Azure SQL (Lookup and StoredProcedure activities)
2. **ADLS Connectivity** - Verify ADF can write to ADLS Gen2 storage
3. **Pipeline Orchestration Logic** - Verify ForEach, IfCondition, and pipeline chaining work correctly
4. **Control Table Operations** - Verify Lookup queries, status updates, and audit logging
5. **Key Vault Access** - Verify ADF can retrieve secrets

**What CANNOT be tested without SharePoint consent:**
1. SharePoint REST API file enumeration
2. Actual file copy from SharePoint to ADLS
3. Metadata extraction from SharePoint
4. Incremental sync (requires SharePoint Modified date queries)

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
3. The `ForEach_Library` will attempt SharePoint calls and **fail** (expected without consent)
4. Verify in SQL that the control table status was updated to 'InProgress'

```sql
-- 2. Verify the pipeline touched the control table
SELECT Id, SiteUrl, LibraryName, Status, MigrationStartTime
FROM dbo.MigrationControl
WHERE LibraryName = 'TestLibrary';
```

This confirms the infrastructure (ADF -> SQL -> ADLS) is wired correctly. Once admin consent is granted, the SharePoint activities will start working without any code changes.

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

| Parameter | Value |
|-----------|-------|
| SiteUrl | `/sites/TestSite` |
| LibraryName | `Documents` |
| ControlTableId | `1` (from control table) |
| BatchId | `PILOT-001` |
| ContainerName | `sharepoint-migration` |
| SharePointTenantUrl | `https://{tenant}.sharepoint.com` |
| ThrottleWaitSeconds | `120` |

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
    COUNT(al.Id) AS MigratedFiles,
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

**Option B: PowerShell**
```powershell
$params = @{
    BatchSize = 10
    ParallelLibraries = 4
    MaxRetries = 3
    TargetContainerName = "sharepoint-migration"
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
| HTTP 401 | Token expired/invalid | Regenerate client secret, update Key Vault |
| HTTP 403 | Insufficient permissions | Verify admin consent, check site permissions |
| HTTP 404 | File deleted after enumeration | Log and skip (expected) |
| HTTP 429 | SharePoint throttling | Reduce parallelism, wait, contact Microsoft |
| HTTP 503 | SharePoint unavailable | Retry automatically, check service health |
| Timeout | Large file or slow network | Increase timeout settings |
| Circular reference | Pipeline self-referencing | Already fixed in templates |

### 14.2 Linked Service Connection Failures

**Key Vault:** Verify ADF managed identity has Key Vault access policy
**Storage:** Verify ADF has Storage Blob Data Contributor role
**SQL:** Verify ADF user created in SQL with proper permissions
**SharePoint:** Verify admin consent granted and secret is valid

### 14.3 Pipeline Debug Steps

1. Check ADF Monitor for error messages
2. Click on failed activity for details
3. Check Input/Output tabs for request/response data
4. Check SQL audit log for file-level errors
5. Verify linked service connections are working

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
| Tenant | `fe64e912-f83c-44e9-9389-f66812c7fa57` |
| Resource Group | `rg-hydroone-migration-test` |
| Storage Account | `sthydroonemigtest` |
| SQL Server | `sql-hydroone-migration-test.database.windows.net` |
| Key Vault | `kv-hydroone-test2` |
| Data Factory | `adf-hydroone-migration-test` |
| App Registration | `3a412ede-620a-4f21-8501-ef62a5161dc2` |
| ADF Managed Identity | `b509d6d6-4d95-4e74-9de6-952b764556d3` |

### 16.3 Cost Estimation (Monthly)

| Resource | Tier | Estimated Cost |
|----------|------|----------------|
| ADLS Gen2 (25 TB, Hot) | Standard LRS | ~$500-600 |
| Azure SQL | S1 | ~$30 |
| Data Factory | Pay-as-you-go | ~$50-200 |
| Key Vault | Standard | ~$5 |
| **Total** | | **~$585-835/month** |
