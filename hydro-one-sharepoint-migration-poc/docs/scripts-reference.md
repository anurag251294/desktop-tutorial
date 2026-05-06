# Hydro One SharePoint Migration - Scripts Reference

Central reference for all 6 automation scripts used in the SharePoint Online to ADLS Gen2 migration.

---

## Execution Order

Run the scripts in this order. Steps marked **[Manual]** require human action outside the scripts.

1. **`Setup-AzureResources.ps1`** -- Provisions all Azure resources (RG, ADF, ADLS, SQL, Key Vault)
2. **`Register-SharePointApp.ps1`** -- Creates the Service Principal and stores its secret in Key Vault
3. **[Manual]** Grant admin consent to the app registration in Azure Portal > Enterprise Applications
4. **`Deploy-ADF-Templates.sh`** -- Deploys ADF ARM templates (linked services, datasets, pipelines)
5. **`Populate-ControlTable.ps1`** -- Enumerates SharePoint sites/libraries into the SQL control table
6. **[Manual]** Trigger migration pipelines in ADF (PL_Master_Migration_Orchestrator)
7. **`Monitor-Migration.ps1`** -- Real-time progress dashboard (run during migration)
8. **`Validate-Migration.ps1`** -- Post-migration file count and size validation

> Steps 1-4 are one-time setup. Steps 5-8 are repeated per migration batch.

---

## Script Categories

| Category        | Scripts                                              | When to Run                        |
|-----------------|------------------------------------------------------|------------------------------------|
| One-time setup  | Setup-AzureResources, Register-SharePointApp, Deploy-ADF-Templates | Once per environment / tenant      |
| Repeatable      | Populate-ControlTable, Validate-Migration            | Before and after each migration batch |
| Ongoing         | Monitor-Migration                                    | During every active migration run  |

---

## Detailed Script Reference

### 1. Setup-AzureResources.ps1

**Purpose:** Provisions the complete Azure resource set -- Resource Group, Azure Data Factory, ADLS Gen2 (with hierarchical namespace enabled), Azure SQL Database, Key Vault, and RBAC role assignments.

**When:** One-time per environment (dev / test / prod).

**Auth:** Requires Azure CLI login (`az login`) with **Contributor** access on the target subscription.

**Parameters:**

| Parameter         | Required | Default          | Description                              |
|-------------------|----------|------------------|------------------------------------------|
| `Environment`     | Yes      | --               | Target environment: `dev`, `test`, `prod` |
| `Location`        | No       | `canadacentral`  | Azure region for all resources           |
| `SubscriptionId`  | No       | Current context  | Azure subscription to deploy into        |
| `SqlAdminUsername` | No       | `sqladmin`       | SQL Server admin login                   |
| `SqlAdminPassword` | No      | Auto-generated   | SQL Server admin password (stored in KV) |

**Example:**

```powershell
./Setup-AzureResources.ps1 -Environment prod -Location canadacentral
```

**Resources created:**

| Resource                | Naming Convention                | Notes                          |
|-------------------------|----------------------------------|--------------------------------|
| Resource Group          | `rg-hydroone-migration-{env}`    |                                |
| Azure Data Factory      | `adf-hydroone-migration-{env}`   | System-assigned managed identity |
| ADLS Gen2 Storage       | `sthydroonemig{env}`             | Hierarchical namespace enabled |
| Azure SQL Server + DB   | `sql-hydroone-migration-{env}`   | MigrationControl + AuditLog tables |
| Key Vault               | `kv-hydroone-{env}`              | Stores SQL password + SP secret |

---

### 2. Register-SharePointApp.ps1

**Purpose:** Creates an Azure AD app registration in the SharePoint tenant with Microsoft Graph API permissions (`Sites.Read.All`, `Files.Read.All`), generates a client secret, and stores it in Key Vault.

**When:** One-time per SharePoint tenant.

**Auth:** Requires **Application Administrator** or **Global Admin** in the SharePoint tenant.

**Parameters:**

| Parameter            | Required | Default                              | Description                              |
|----------------------|----------|--------------------------------------|------------------------------------------|
| `TenantId`           | Yes      | --                                   | SharePoint Azure AD tenant ID            |
| `KeyVaultName`       | Yes      | --                                   | Key Vault to store the client secret     |
| `AppDisplayName`     | No       | `HydroOne-SPO-Migration`             | Display name for the app registration    |
| `SharePointTenantUrl`| No       | `https://hydroone.sharepoint.com`    | SharePoint Online root URL               |
| `SecretValidityYears`| No       | `2`                                  | Client secret expiry in years            |

**Example:**

```powershell
./Register-SharePointApp.ps1 -TenantId "5447cfcd-3af1-439a-8157-760bd52b12df" `
                              -KeyVaultName "kv-hydroone-prod"
```

**Important:** After this script completes, a **Global Admin** must grant admin consent in Azure Portal:
Azure Portal > Azure Active Directory > App registrations > HydroOne-SPO-Migration > API permissions > Grant admin consent.

---

### 3. Deploy-ADF-Templates.sh

**Purpose:** Deploys ADF ARM templates in the correct dependency order -- linked services first, then datasets, then pipelines. Handles idempotent re-deployment.

**When:** One-time per environment, or after any ARM template changes.

**Auth:** Azure CLI login (`az login`).

**Note:** This is a **Bash** script (not PowerShell). Run it in WSL, Git Bash, or a Linux/macOS terminal.

**Parameters:**

| Parameter            | Required | Default                              | Description                              |
|----------------------|----------|--------------------------------------|------------------------------------------|
| `RESOURCE_GROUP`     | Yes      | --                                   | Target resource group (env variable)     |
| `FACTORY_NAME`      | Yes      | --                                   | ADF instance name (env variable)         |
| `TEMPLATE_DIR`       | No       | `./arm-templates`                    | Path to ARM template directory           |

**Example:**

```bash
export RESOURCE_GROUP="rg-hydroone-migration-prod"
export FACTORY_NAME="adf-hydroone-migration-prod"
./Deploy-ADF-Templates.sh
```

**Deployment order:** Linked Services > Datasets > Pipelines (PL_Copy_File_Batch > PL_Process_Subfolder > PL_Migrate_Single_Library > PL_Incremental_Sync > PL_Post_Migration_Validation > PL_Master_Migration_Orchestrator).

---

### 4. Populate-ControlTable.ps1

**Purpose:** Connects to SharePoint via PnP PowerShell, enumerates all sites and document libraries, calculates file counts and total sizes, and upserts rows into the `MigrationControl` SQL table. Includes comprehensive pre-flight diagnostics, detailed logging, and support for both Azure AD Integrated and SQL authentication.

**When:** Before each migration batch, or to refresh the site inventory.

**Auth:**
- **SharePoint:** Interactive browser login (default) or certificate-based auth via `-ClientId` + `-CertificateThumbprint` + `-TenantId`
- **SQL:** Azure AD Integrated (default) or SQL authentication via `-SqlUsername` + `-SqlPassword`. Use SQL auth in ADFS/federated environments where AD Integrated fails.

**Parameters:**

| Parameter               | Required | Default | Description                                      |
|-------------------------|----------|---------|--------------------------------------------------|
| `SharePointTenantUrl`   | Yes      | --      | Tenant root URL (e.g. `https://hydroone.sharepoint.com`). Do **not** include `/sites/...` — use `-SpecificSites` for that. |
| `ClientId`              | Yes      | --      | Azure AD App Registration Client ID with `Sites.Read.All` permission |
| `SqlServerName`         | Yes      | --      | Azure SQL server name (without `.database.windows.net`) |
| `SqlDatabaseName`       | Yes      | --      | Database containing MigrationControl table       |
| `SpecificSites`         | No       | --      | Array of site paths to target, e.g. `@("/sites/MySite")`. If omitted, enumerates all sites via the admin center. |
| `ExcludeSites`          | No       | --      | Array of site paths to skip                      |
| `CertificateThumbprint` | No      | --      | Certificate thumbprint for non-interactive PnP auth |
| `TenantId`              | No       | --      | Azure AD tenant ID (required with `-CertificateThumbprint`) |
| `SqlUsername`            | No       | --      | SQL login username for SQL authentication        |
| `SqlPassword`           | No       | --      | SQL login password (SecureString). If `-SqlUsername` is provided without this, you will be prompted. |

**Example (specific sites + SQL auth — recommended for initial testing):**

```powershell
./Populate-ControlTable.ps1 -SharePointTenantUrl "https://hydroone.sharepoint.com" `
                             -ClientId "<your-app-client-id>" `
                             -SpecificSites @("/sites/MySite1", "/sites/MySite2") `
                             -SqlServerName "sql-hydroone-migration-dev" `
                             -SqlDatabaseName "MigrationControl" `
                             -SqlUsername "sqladmin" `
                             -SqlPassword (ConvertTo-SecureString "YourPassword" -AsPlainText -Force)
```

**Example (all sites + AD Integrated SQL auth):**

```powershell
./Populate-ControlTable.ps1 -SharePointTenantUrl "https://hydroone.sharepoint.com" `
                             -ClientId "<your-app-client-id>" `
                             -SqlServerName "sql-hydroone-migration-dev" `
                             -SqlDatabaseName "MigrationControl"
```

**Example (certificate-based PnP auth — non-interactive / automation):**

```powershell
./Populate-ControlTable.ps1 -SharePointTenantUrl "https://hydroone.sharepoint.com" `
                             -ClientId "<your-app-client-id>" `
                             -CertificateThumbprint "<thumbprint>" `
                             -TenantId "<sharepoint-tenant-id>" `
                             -SpecificSites @("/sites/MySite1") `
                             -SqlServerName "sql-hydroone-migration-dev" `
                             -SqlDatabaseName "MigrationControl" `
                             -SqlUsername "sqladmin" `
                             -SqlPassword (ConvertTo-SecureString "YourPassword" -AsPlainText -Force)
```

**Key behaviors:**
- **6-step SQL pre-flight check** -- DNS resolution, TCP connectivity, authentication, table existence, permissions, and INSERT dry-run (with ROLLBACK).
- **Network diagnostics** -- Tests connectivity to `login.microsoftonline.com`, `graph.microsoft.com`, and SharePoint Online.
- **Upserts** -- safe to re-run without duplicating rows (IF NOT EXISTS / ELSE pattern).
- Skips empty libraries (0 files) and system libraries.
- Assigns migration priority based on library size (<100 MB → P10, <1 GB → P50, <10 GB → P100, >10 GB → P200).
- **Timestamped log file** -- every run writes to `Populate-ControlTable_YYYYMMDD_HHmmss.log` with full environment diagnostics, per-site/library details, and exception stack traces.
- Auto-detects if a site URL was passed as `-SharePointTenantUrl` and extracts the site path to `-SpecificSites`.

**Common errors:**

| Error | Cause | Solution |
|-------|-------|----------|
| `Client with IP address 'x.x.x.x' is not allowed` | SQL firewall | Add your IP: `az sql server firewall-rule create` |
| `Failed to authenticate NT Authority\Anonymous Logon` | ADFS/federated environment | Use `-SqlUsername` and `-SqlPassword` |
| `(403) Forbidden` on SharePoint | Missing admin consent | Grant admin consent (Step 3 in README) |
| `(404) Not Found` | Site URL in tenant URL parameter | Use `-SpecificSites` for site paths |
| `No such host is known` | Wrong SQL server name | Verify: `nslookup <server>.database.windows.net` |

---

### 5. Monitor-Migration.ps1

**Purpose:** Real-time migration progress dashboard. Queries ADF pipeline run status and the SQL audit log to display live metrics.

**When:** During active migration runs. Run as often as needed -- it is read-only.

**Auth:** Azure CLI login + SQL read access.

**Parameters:**

| Parameter          | Required | Default | Description                              |
|--------------------|----------|---------|------------------------------------------|
| `SqlServerName`    | Yes      | --      | Azure SQL server FQDN                   |
| `SqlDatabaseName`  | Yes      | --      | Migration database name                  |
| `AdfName`          | Yes      | --      | ADF instance name                        |
| `ResourceGroup`    | Yes      | --      | Resource group containing ADF            |
| `RefreshInterval`  | No       | `30`    | Dashboard refresh interval in seconds    |

**Example:**

```powershell
./Monitor-Migration.ps1 -SqlServerName "sql-hydroone-migration-prod.database.windows.net" `
                         -SqlDatabaseName "MigrationDB" `
                         -AdfName "adf-hydroone-migration-prod" `
                         -ResourceGroup "rg-hydroone-migration-prod"
```

**Dashboard metrics:**
- Libraries completed / total (with progress bar)
- Files migrated (count)
- Bytes transferred (human-readable)
- Error count (color-coded: green = 0, yellow = <10, red = 10+)
- Current pipeline run status
- Estimated time remaining

---

### 6. Validate-Migration.ps1

**Purpose:** Post-migration validation. Compares file counts and total sizes between the SharePoint source and the ADLS destination. Flags mismatches.

**When:** After a migration batch completes. Safe to re-run.

**Auth:** Azure CLI login + SharePoint read access + SQL read access.

**Parameters:**

| Parameter             | Required | Default | Description                              |
|-----------------------|----------|---------|------------------------------------------|
| `SharePointTenantUrl` | Yes      | --      | Root SharePoint URL                      |
| `SqlServerName`       | Yes      | --      | Azure SQL server FQDN                   |
| `SqlDatabaseName`     | Yes      | --      | Migration database name                  |
| `StorageAccountName`  | Yes      | --      | ADLS Gen2 storage account name           |
| `LibraryId`           | No       | --      | Validate a single library (default: all) |
| `OutputCsv`           | No       | --      | Export results to CSV file               |

**Example:**

```powershell
./Validate-Migration.ps1 -SharePointTenantUrl "https://hydroone.sharepoint.com" `
                          -SqlServerName "sql-hydroone-migration-prod.database.windows.net" `
                          -SqlDatabaseName "MigrationDB" `
                          -StorageAccountName "sthydroonemigprod" `
                          -OutputCsv "./validation-report.csv"
```

**Validation checks:**
- File count match (source vs destination per library)
- Total size match (with configurable tolerance for metadata differences)
- Missing files list
- Summary pass/fail per library

---

## Prerequisites Matrix

| Prerequisite       | Setup-AzureResources | Register-SharePointApp | Deploy-ADF-Templates | Populate-ControlTable | Monitor-Migration | Validate-Migration |
|--------------------|:--------------------:|:----------------------:|:--------------------:|:---------------------:|:-----------------:|:------------------:|
| Az PowerShell module |         Yes        |          Yes           |         --           |          --           |        Yes        |        Yes         |
| PnP.PowerShell     |         --           |          --            |         --           |         Yes           |        --         |        Yes         |
| SqlServer module   |         --           |          --            |         --           |         Yes           |        Yes        |        Yes         |
| Azure CLI          |         Yes          |          --            |        Yes           |          --           |        --         |        --          |
| AzureAD module     |         --           |          Yes           |         --           |          --           |        --         |        --          |

---

## Interactive vs Unattended Execution

| Script                   | Interactive | Unattended (Certificate/SPN) | Notes                                              |
|--------------------------|:-----------:|:----------------------------:|------------------------------------------------------|
| Setup-AzureResources     | Yes         | Yes (SPN login via `az login --service-principal`) | All params can be passed on command line  |
| Register-SharePointApp   | Yes         | No                           | Requires admin consent grant in portal               |
| Deploy-ADF-Templates     | Yes         | Yes (SPN login via `az login --service-principal`) | Fully scriptable in CI/CD                |
| Populate-ControlTable    | Yes         | Yes (ClientId + CertificateThumbprint)             | Certificate auth for scheduled refreshes |
| Monitor-Migration        | Yes         | Yes                          | Can pipe output to log file for unattended runs      |
| Validate-Migration       | Yes         | Yes                          | Use `-OutputCsv` for unattended report generation    |

---

## Troubleshooting Quick Reference

| Symptom                                  | Likely cause                        | Fix                                            |
|------------------------------------------|-------------------------------------|-------------------------------------------------|
| `Unsupported app only token`             | Using SharePoint REST API           | Use Graph API endpoints instead                 |
| `Circular reference not allowed` in ADF  | Self-referencing pipeline           | Use separate child pipelines                    |
| Admin consent not granted                | Step 3 skipped                      | Azure Portal > App registrations > Grant consent |
| SQL connection timeout                   | Firewall rule missing               | Add client IP to SQL Server firewall            |
| PnP.PowerShell not found                 | Module not installed                | `Install-Module PnP.PowerShell -Scope CurrentUser` |
| `Failed to authenticate NT Authority\Anonymous Logon` | ADFS/federated environment breaks AD Integrated SQL auth | Use `-SqlUsername` and `-SqlPassword` for SQL auth |
| `Client with IP address 'x.x.x.x' is not allowed` | SQL firewall blocking client IP | `az sql server firewall-rule create --start-ip-address <IP> --end-ip-address <IP>` |
| `(404) Not Found` on SharePoint admin URL | Site URL passed as tenant URL, or app lacks admin center access | Use `-SpecificSites` to bypass admin center enumeration |
| `No such host is known` for SQL server   | Wrong SQL server name               | Verify with `nslookup <server>.database.windows.net` |
| `Cannot convert System.Object[] to System.Int32` | Outdated Populate-ControlTable.ps1 | Pull the latest version from the repository |

---

*Last updated: 2026-05-06*
