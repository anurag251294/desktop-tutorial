<#
.SYNOPSIS
    Master deployment script — runs all steps (1-9) end-to-end for the Hydro One SharePoint Migration.

.DESCRIPTION
    This script orchestrates the full deployment in the correct order:
      Step 1: Provision Azure resources (Setup-AzureResources.ps1)
      Step 2: Register SharePoint app (Register-SharePointApp.ps1)
      Step 3: Grant admin consent (manual — opens browser)
      Step 4: Enable network access (firewall rules)
      Step 5: Initialize SQL database (DDL scripts)
      Step 6: Grant ADF Managed Identity access to SQL
      Step 7: Deploy ADF ARM templates (linked services, datasets, pipelines)
      Step 8: Populate control table (Populate-ControlTable.ps1)
      Step 9: Verify everything is ready

    Each step can be skipped with -SkipStep parameters if already completed.

.PARAMETER Environment
    Target environment: dev, test, or prod

.PARAMETER Location
    Azure region (default: canadacentral)

.PARAMETER SubscriptionId
    Azure subscription ID

.PARAMETER SharePointTenantId
    Azure AD Tenant ID of the SharePoint tenant

.PARAMETER SharePointTenantUrl
    SharePoint Online tenant root URL (e.g. https://hydroone.sharepoint.com)

.PARAMETER SqlAdminUsername
    SQL Server admin login (default: sqladmin)

.PARAMETER SqlAdminPassword
    SQL Server admin password (SecureString). Auto-generated if not provided.

.PARAMETER ClientId
    Azure AD App Registration Client ID (from Step 2). Required for Steps 7-8.
    If running Step 2, this is auto-detected from the output.

.PARAMETER SpecificSites
    Array of SharePoint site paths to enumerate (e.g. @("/sites/MySite")).
    If omitted, enumerates all sites via admin center.

.PARAMETER SqlUsername
    SQL login username for Populate-ControlTable (use in ADFS/federated environments)

.PARAMETER SqlPassword
    SQL login password (SecureString) for Populate-ControlTable

.PARAMETER StartFromStep
    Start from a specific step number (1-9). Skips all earlier steps. Default: 1.

.PARAMETER StopAfterStep
    Stop after a specific step number (1-9). Default: 9 (run all).

.EXAMPLE
    # Full deployment from scratch
    .\Deploy-All.ps1 -Environment "dev" -SubscriptionId "<sub-id>" `
        -SharePointTenantId "<tenant-id>" `
        -SharePointTenantUrl "https://hydroone.sharepoint.com" `
        -SpecificSites @("/sites/JSTestCommunicationSite") `
        -SqlUsername "sqladmin" -SqlPassword (ConvertTo-SecureString "Pass" -AsPlainText -Force)

.EXAMPLE
    # Resume from Step 5 (SQL setup) onward
    .\Deploy-All.ps1 -Environment "dev" -SubscriptionId "<sub-id>" `
        -SharePointTenantId "<tenant-id>" `
        -SharePointTenantUrl "https://hydroone.sharepoint.com" `
        -ClientId "<app-client-id>" `
        -StartFromStep 5

.EXAMPLE
    # Only run Steps 7-8 (ADF deploy + control table)
    .\Deploy-All.ps1 -Environment "dev" -SubscriptionId "<sub-id>" `
        -SharePointTenantUrl "https://hydroone.sharepoint.com" `
        -ClientId "<app-client-id>" `
        -StartFromStep 7 -StopAfterStep 8 `
        -SqlUsername "sqladmin" -SqlPassword (ConvertTo-SecureString "Pass" -AsPlainText -Force)

.NOTES
    Author: Microsoft Azure Data Engineering Team
    Project: Hydro One SharePoint Migration POC
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("dev", "test", "prod")]
    [string]$Environment,

    [string]$Location = "canadacentral",

    [Parameter(Mandatory = $true)]
    [string]$SubscriptionId,

    [string]$SharePointTenantId,

    [string]$SharePointTenantUrl = "https://hydroone.sharepoint.com",

    [string]$SqlAdminUsername = "sqladmin",

    [SecureString]$SqlAdminPassword,

    [string]$ClientId,

    [string[]]$SpecificSites,

    [string]$SqlUsername,

    [SecureString]$SqlPassword,

    [ValidateRange(1, 9)]
    [int]$StartFromStep = 1,

    [ValidateRange(1, 9)]
    [int]$StopAfterStep = 9
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $scriptDir
$logFile = Join-Path $scriptDir "Deploy-All_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"

#region Logging
function Write-Step {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] [$Level] $Message"
    Write-Host $line -ForegroundColor $(switch ($Level) {
        "SUCCESS" { "Green" }
        "ERROR"   { "Red" }
        "WARNING" { "Yellow" }
        "HEADER"  { "Cyan" }
        default   { "White" }
    })
    Add-Content -Path $logFile -Value $line
}
#endregion

#region Resource Naming
$rgName      = "rg-hydroone-migration-$Environment"
$adfName     = "adf-hydroone-migration-$Environment"
$storageName = "sthydroonemig$Environment"
$sqlServer   = "sql-hydroone-migration-$Environment"
$sqlDatabase = "MigrationControl"
$kvName      = "kv-hydroone-mig-$Environment"
$sqlFqdn     = "$sqlServer.database.windows.net"
#endregion

Write-Step "============================================================" "HEADER"
Write-Step "  HYDRO ONE SHAREPOINT MIGRATION — MASTER DEPLOYMENT" "HEADER"
Write-Step "============================================================" "HEADER"
Write-Step "Environment:    $Environment"
Write-Step "Subscription:   $SubscriptionId"
Write-Step "Location:       $Location"
Write-Step "Resource Group: $rgName"
Write-Step "ADF:            $adfName"
Write-Step "Storage:        $storageName"
Write-Step "SQL Server:     $sqlFqdn"
Write-Step "Key Vault:      $kvName"
Write-Step "SP Tenant URL:  $SharePointTenantUrl"
Write-Step "Steps:          $StartFromStep through $StopAfterStep"
Write-Step "Log file:       $logFile"
Write-Step "============================================================" "HEADER"

$stepResults = @{}
$overallStart = Get-Date

function Should-RunStep([int]$step) {
    return ($step -ge $StartFromStep -and $step -le $StopAfterStep)
}

# ============================================================
# STEP 1: Provision Azure Resources
# ============================================================
if (Should-RunStep 1) {
    Write-Step ""
    Write-Step "========== STEP 1/9: Provision Azure Resources ==========" "HEADER"
    $stepStart = Get-Date
    try {
        Write-Step "Setting Azure subscription to $SubscriptionId..."
        az account set --subscription $SubscriptionId 2>&1 | ForEach-Object { Write-Step "  $_" }

        Write-Step "Running Setup-AzureResources.ps1..."
        $setupParams = @{
            Environment = $Environment
            Location    = $Location
        }
        if ($SubscriptionId) { $setupParams.SubscriptionId = $SubscriptionId }
        if ($SqlAdminPassword) { $setupParams.SqlAdminPassword = $SqlAdminPassword }
        if ($SqlAdminUsername -ne "sqladmin") { $setupParams.SqlAdminUsername = $SqlAdminUsername }

        & "$scriptDir\Setup-AzureResources.ps1" @setupParams

        Write-Step "Step 1 completed in $([math]::Round(((Get-Date) - $stepStart).TotalSeconds))s" "SUCCESS"
        $stepResults[1] = "SUCCESS"
    }
    catch {
        Write-Step "Step 1 FAILED: $_" "ERROR"
        Write-Step $_.ScriptStackTrace "ERROR"
        $stepResults[1] = "FAILED"
        throw "Step 1 failed. Fix the error and re-run with -StartFromStep 1"
    }
}
else {
    Write-Step "STEP 1: SKIPPED (StartFromStep=$StartFromStep)" "WARNING"
    $stepResults[1] = "SKIPPED"
}

# ============================================================
# STEP 2: Register SharePoint App
# ============================================================
if (Should-RunStep 2) {
    Write-Step ""
    Write-Step "========== STEP 2/9: Register SharePoint App ==========" "HEADER"
    $stepStart = Get-Date

    if (-not $SharePointTenantId) {
        Write-Step "ERROR: -SharePointTenantId is required for Step 2" "ERROR"
        throw "Provide -SharePointTenantId (Azure AD Tenant ID of the SharePoint tenant)"
    }

    try {
        Write-Step "Running Register-SharePointApp.ps1..."
        & "$scriptDir\Register-SharePointApp.ps1" `
            -TenantId $SharePointTenantId `
            -KeyVaultName $kvName `
            -SharePointTenantUrl $SharePointTenantUrl

        # Try to auto-detect the Client ID
        if (-not $ClientId) {
            Write-Step "Attempting to auto-detect Client ID from app registration..."
            $app = az ad app list --display-name "HydroOne-SPO-Migration" --query "[0].appId" -o tsv 2>$null
            if ($app) {
                $ClientId = $app
                Write-Step "Auto-detected Client ID: $ClientId" "SUCCESS"
            }
            else {
                Write-Step "Could not auto-detect Client ID. You will need to provide -ClientId for later steps." "WARNING"
            }
        }

        Write-Step "Step 2 completed in $([math]::Round(((Get-Date) - $stepStart).TotalSeconds))s" "SUCCESS"
        $stepResults[2] = "SUCCESS"
    }
    catch {
        Write-Step "Step 2 FAILED: $_" "ERROR"
        Write-Step $_.ScriptStackTrace "ERROR"
        $stepResults[2] = "FAILED"
        throw "Step 2 failed. Fix the error and re-run with -StartFromStep 2"
    }
}
else {
    Write-Step "STEP 2: SKIPPED (StartFromStep=$StartFromStep)" "WARNING"
    $stepResults[2] = "SKIPPED"
}

# ============================================================
# STEP 3: Admin Consent (Manual — opens browser)
# ============================================================
if (Should-RunStep 3) {
    Write-Step ""
    Write-Step "========== STEP 3/9: Admin Consent (MANUAL STEP) ==========" "HEADER"

    if ($ClientId -and $SharePointTenantId) {
        $consentUrl = "https://login.microsoftonline.com/$SharePointTenantId/adminconsent?client_id=$ClientId"
        Write-Step "Opening admin consent page in your browser..." "WARNING"
        Write-Step "URL: $consentUrl"
        Write-Step ""
        Write-Step "  ACTION REQUIRED:" "WARNING"
        Write-Step "  1. Sign in as a Global Administrator in the SharePoint tenant" "WARNING"
        Write-Step "  2. Click 'Accept' to grant admin consent" "WARNING"
        Write-Step "  3. Return here and press ENTER to continue" "WARNING"

        try { Start-Process $consentUrl } catch { Write-Step "Could not open browser. Open this URL manually: $consentUrl" "WARNING" }

        Read-Host "`nPress ENTER after granting admin consent to continue"
        Write-Step "Admin consent acknowledged." "SUCCESS"
        $stepResults[3] = "SUCCESS"
    }
    elseif ($ClientId -and -not $SharePointTenantId) {
        Write-Step "Client ID is available but -SharePointTenantId was not provided." "WARNING"
        Write-Step "Cannot construct consent URL without the tenant ID." "WARNING"
        Write-Step "Grant admin consent manually in Azure Portal:" "WARNING"
        Write-Step "  https://portal.azure.com > Azure AD > App registrations > HydroOne-SPO-Migration > API permissions > Grant admin consent" "WARNING"
        Read-Host "`nPress ENTER after granting admin consent to continue"
        $stepResults[3] = "MANUAL"
    }
    else {
        Write-Step "Client ID not available. Grant admin consent manually:" "WARNING"
        Write-Step "  Azure Portal > Azure AD > App registrations > HydroOne-SPO-Migration > API permissions > Grant admin consent" "WARNING"
        Read-Host "`nPress ENTER after granting admin consent to continue"
        $stepResults[3] = "MANUAL"
    }
}
else {
    Write-Step "STEP 3: SKIPPED (StartFromStep=$StartFromStep)" "WARNING"
    $stepResults[3] = "SKIPPED"
}

# ============================================================
# STEP 4: Enable Network Access
# ============================================================
if (Should-RunStep 4) {
    Write-Step ""
    Write-Step "========== STEP 4/9: Enable Network Access ==========" "HEADER"
    $stepStart = Get-Date
    try {
        Write-Step "Enabling public access on Storage Account..."
        az storage account update --name $storageName --resource-group $rgName --public-network-access Enabled -o none 2>&1 | ForEach-Object { Write-Step "  $_" }

        Write-Step "Enabling public access on SQL Server..."
        az sql server update --name $sqlServer --resource-group $rgName --enable-public-network true -o none 2>&1 | ForEach-Object { Write-Step "  $_" }

        Write-Step "Adding AllowAzureServices firewall rule..."
        az sql server firewall-rule create --name "AllowAzureServices" --server $sqlServer --resource-group $rgName --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0 -o none 2>&1 | ForEach-Object { Write-Step "  $_" }

        # Auto-detect client IP and add firewall rule
        Write-Step "Detecting your public IP address..."
        try {
            $myIp = (Invoke-RestMethod -Uri "https://api.ipify.org" -TimeoutSec 10).Trim()
            Write-Step "Your public IP: $myIp"
            Write-Step "Adding firewall rule for your IP..."
            az sql server firewall-rule create --name "AllowDeploymentIP" --server $sqlServer --resource-group $rgName --start-ip-address $myIp --end-ip-address $myIp -o none 2>&1 | ForEach-Object { Write-Step "  $_" }
            Write-Step "Firewall rule added for $myIp" "SUCCESS"
        }
        catch {
            Write-Step "Could not auto-detect IP. Add your IP manually:" "WARNING"
            Write-Step "  az sql server firewall-rule create --name AllowMyIP --server $sqlServer --resource-group $rgName --start-ip-address <YOUR_IP> --end-ip-address <YOUR_IP>" "WARNING"
        }

        Write-Step "Enabling public access on Key Vault..."
        az keyvault update --name $kvName --resource-group $rgName --public-network-access Enabled -o none 2>&1 | ForEach-Object { Write-Step "  $_" }

        Write-Step "Step 4 completed in $([math]::Round(((Get-Date) - $stepStart).TotalSeconds))s" "SUCCESS"
        $stepResults[4] = "SUCCESS"
    }
    catch {
        Write-Step "Step 4 FAILED: $_" "ERROR"
        $stepResults[4] = "FAILED"
        throw "Step 4 failed. Fix the error and re-run with -StartFromStep 4"
    }
}
else {
    Write-Step "STEP 4: SKIPPED (StartFromStep=$StartFromStep)" "WARNING"
    $stepResults[4] = "SKIPPED"
}

# ============================================================
# STEP 5: Initialize SQL Database
# ============================================================
if (Should-RunStep 5) {
    Write-Step ""
    Write-Step "========== STEP 5/9: Initialize SQL Database ==========" "HEADER"
    $stepStart = Get-Date
    try {
        $sqlDir = Join-Path $projectDir "sql"

        # Determine auth args for sqlcmd
        if ($SqlUsername) {
            $plainPw = if ($SqlPassword) {
                [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
                    [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SqlPassword))
            }
            elseif ($SqlAdminPassword) {
                [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
                    [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SqlAdminPassword))
            }
            else {
                [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
                    [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR(
                        (Read-Host "Enter SQL password for '$SqlUsername'" -AsSecureString)))
            }
            $sqlAuthArgs = @("-U", $SqlUsername, "-P", $plainPw)
            Write-Step "Using SQL authentication (user: $SqlUsername)"
        }
        else {
            $sqlAuthArgs = @("-G")
            Write-Step "Using Azure AD authentication (-G flag)"
        }

        Write-Step "Running create_control_table.sql..."
        $result = & sqlcmd -S $sqlFqdn -d $sqlDatabase @sqlAuthArgs -i "$sqlDir\create_control_table.sql" 2>&1
        $result | ForEach-Object { Write-Step "  $_" }

        Write-Step "Running create_audit_log_table.sql..."
        $result = & sqlcmd -S $sqlFqdn -d $sqlDatabase @sqlAuthArgs -i "$sqlDir\create_audit_log_table.sql" 2>&1
        $result | ForEach-Object { Write-Step "  $_" }

        # Verify tables
        Write-Step "Verifying tables..."
        $tables = & sqlcmd -S $sqlFqdn -d $sqlDatabase @sqlAuthArgs -Q "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES ORDER BY TABLE_NAME" -h -1 -W 2>&1
        $tableCount = ($tables | Where-Object { $_ -and $_.Trim() -and $_ -notmatch "rows affected" -and $_ -notmatch "^-" }).Count
        Write-Step "Found $tableCount tables in database" $(if ($tableCount -ge 6) { "SUCCESS" } else { "WARNING" })

        Write-Step "Step 5 completed in $([math]::Round(((Get-Date) - $stepStart).TotalSeconds))s" "SUCCESS"
        $stepResults[5] = "SUCCESS"
    }
    catch {
        Write-Step "Step 5 FAILED: $_" "ERROR"
        Write-Step $_.ScriptStackTrace "ERROR"
        $stepResults[5] = "FAILED"
        throw "Step 5 failed. Fix the error and re-run with -StartFromStep 5"
    }
}
else {
    Write-Step "STEP 5: SKIPPED (StartFromStep=$StartFromStep)" "WARNING"
    $stepResults[5] = "SKIPPED"
}

# ============================================================
# STEP 6: Grant ADF Managed Identity Access to SQL
# ============================================================
if (Should-RunStep 6) {
    Write-Step ""
    Write-Step "========== STEP 6/9: Grant ADF Managed Identity SQL Access ==========" "HEADER"
    $stepStart = Get-Date
    try {
        $grantQuery = @"
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = '$adfName')
BEGIN
    CREATE USER [$adfName] FROM EXTERNAL PROVIDER;
    ALTER ROLE db_datareader ADD MEMBER [$adfName];
    ALTER ROLE db_datawriter ADD MEMBER [$adfName];
    GRANT EXECUTE ON SCHEMA::dbo TO [$adfName];
    SELECT 'CREATED' AS Result;
END
ELSE
BEGIN
    SELECT 'ALREADY_EXISTS' AS Result;
END
"@
        Write-Step "Creating SQL user for ADF Managed Identity: $adfName"
        Write-Step "NOTE: This requires Azure AD authentication — using -G flag"

        $result = & sqlcmd -S $sqlFqdn -d $sqlDatabase -G -Q $grantQuery 2>&1
        $result | ForEach-Object { Write-Step "  $_" }

        Write-Step "Step 6 completed in $([math]::Round(((Get-Date) - $stepStart).TotalSeconds))s" "SUCCESS"
        $stepResults[6] = "SUCCESS"
    }
    catch {
        Write-Step "Step 6 FAILED: $_" "ERROR"
        Write-Step "This step requires Azure AD authentication. If it fails:" "WARNING"
        Write-Step "  1. Ensure you are logged in as the Azure AD admin of the SQL server" "WARNING"
        Write-Step "  2. Run manually in SSMS:" "WARNING"
        Write-Step "     CREATE USER [$adfName] FROM EXTERNAL PROVIDER;" "WARNING"
        Write-Step "     ALTER ROLE db_datareader ADD MEMBER [$adfName];" "WARNING"
        Write-Step "     ALTER ROLE db_datawriter ADD MEMBER [$adfName];" "WARNING"
        Write-Step "     GRANT EXECUTE ON SCHEMA::dbo TO [$adfName];" "WARNING"
        $stepResults[6] = "FAILED"
        Write-Step "Continuing to next step (Step 6 can be done manually)..." "WARNING"
    }
}
else {
    Write-Step "STEP 6: SKIPPED (StartFromStep=$StartFromStep)" "WARNING"
    $stepResults[6] = "SKIPPED"
}

# ============================================================
# STEP 7: Deploy ADF ARM Templates
# ============================================================
if (Should-RunStep 7) {
    Write-Step ""
    Write-Step "========== STEP 7/9: Deploy ADF ARM Templates ==========" "HEADER"
    $stepStart = Get-Date
    $templateDir = Join-Path $projectDir "adf-templates"

    try {
        # Step 7a: Main ARM template (ADF instance + linked services + some datasets)
        Write-Step "7a. Deploying arm-template.json (ADF + linked services + core datasets)..."

        # Build parameters.json dynamically
        $paramsObj = @{
            "`$schema" = "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#"
            contentVersion = "1.0.0.0"
            parameters = @{
                factoryName         = @{ value = $adfName }
                location            = @{ value = $Location }
                sharePointTenantUrl = @{ value = $SharePointTenantUrl }
                keyVaultName        = @{ value = $kvName }
                storageAccountName  = @{ value = $storageName }
                sqlServerName       = @{ value = $sqlServer }
                sqlDatabaseName     = @{ value = $sqlDatabase }
            }
        }
        if ($ClientId) { $paramsObj.parameters.servicePrincipalId = @{ value = $ClientId } }
        if ($SharePointTenantId) { $paramsObj.parameters.tenantId = @{ value = $SharePointTenantId } }

        $tempParams = Join-Path $env:TEMP "adf-params-$Environment.json"
        $paramsObj | ConvertTo-Json -Depth 5 | Set-Content $tempParams -Encoding UTF8
        Write-Step "  Generated parameters file: $tempParams"

        az deployment group create --resource-group $rgName `
            --template-file "$templateDir\arm-template.json" `
            --parameters "@$tempParams" `
            --name "adf-core-$(Get-Date -Format 'yyyyMMddHHmm')" -o none 2>&1 | ForEach-Object { Write-Step "  $_" }
        Write-Step "  Core ARM template deployed" "SUCCESS"

        # Step 7b: Deploy individual linked services (some are NOT in arm-template.json)
        Write-Step "7b. Deploying individual linked services..."
        $linkedServices = @("LS_KeyVault", "LS_AzureBlobStorage", "LS_AzureSqlDatabase", "LS_HTTP_Graph_Download")
        foreach ($ls in $linkedServices) {
            $lsFile = Join-Path $templateDir "linkedServices\$ls.json"
            if (Test-Path $lsFile) {
                Write-Step "  Deploying $ls..."
                $lsParams = @("--resource-group", $rgName, "--template-file", $lsFile, "--parameters", "factoryName=$adfName")
                # Add extra params for specific linked services
                if ($ls -eq "LS_KeyVault") { $lsParams += @("keyVaultName=$kvName") }
                if ($ls -eq "LS_AzureBlobStorage") { $lsParams += @("storageAccountName=$storageName") }
                if ($ls -eq "LS_AzureSqlDatabase") { $lsParams += @("sqlServerName=$sqlServer", "sqlDatabaseName=$sqlDatabase") }
                az deployment group create @lsParams --name "ls-$(($ls -replace '_','-').ToLower())" -o none 2>&1 | ForEach-Object { Write-Step "    $_" }
            }
            else {
                Write-Step "  SKIP: $lsFile not found" "WARNING"
            }
        }
        Write-Step "  All linked services deployed" "SUCCESS"

        # Step 7c: Deploy remaining datasets
        Write-Step "7c. Deploying datasets..."
        $datasets = @("DS_SQL_ControlTables", "DS_ADLS_Sink", "DS_Graph_Content_Download")
        foreach ($ds in $datasets) {
            $dsFile = Join-Path $templateDir "datasets\$ds.json"
            if (Test-Path $dsFile) {
                Write-Step "  Deploying $ds..."
                az deployment group create --resource-group $rgName `
                    --template-file $dsFile `
                    --parameters factoryName=$adfName `
                    --name "ds-$(($ds -replace '_','-').ToLower())" -o none 2>&1 | ForEach-Object { Write-Step "    $_" }
            }
            else {
                Write-Step "  SKIP: $dsFile not found" "WARNING"
            }
        }
        Write-Step "  All datasets deployed" "SUCCESS"

        # Step 7d: Deploy pipelines in dependency order
        Write-Step "7d. Deploying pipelines (child-first order)..."
        $pipelineOrder = @(
            "PL_Copy_File_Batch",
            "PL_Process_Subfolder",
            "PL_Migrate_Single_Library",
            "PL_Incremental_Sync",
            "PL_Validation",
            "PL_Master_Migration_Orchestrator"
        )
        $plIdx = 0
        foreach ($pl in $pipelineOrder) {
            $plIdx++
            $plFile = Join-Path $templateDir "pipelines\$pl.json"
            if (Test-Path $plFile) {
                Write-Step "  [$plIdx/6] Deploying $pl..."
                az deployment group create --resource-group $rgName `
                    --template-file $plFile `
                    --parameters factoryName=$adfName `
                    --name "pl-$(($pl -replace '_','-').ToLower())" -o none 2>&1 | ForEach-Object { Write-Step "    $_" }
            }
            else {
                Write-Step "  SKIP: $plFile not found" "WARNING"
            }
        }
        Write-Step "  All pipelines deployed" "SUCCESS"

        # Step 7e: Verify
        Write-Step "7e. Verifying ADF deployment..."
        $dsCount = (az datafactory dataset list --resource-group $rgName --factory-name $adfName --query "length(@)" -o tsv 2>$null)
        $plCount = (az datafactory pipeline list --resource-group $rgName --factory-name $adfName --query "length(@)" -o tsv 2>$null)
        if (-not $dsCount) { $dsCount = "0" }
        if (-not $plCount) { $plCount = "0" }
        Write-Step "  Datasets:  $dsCount deployed"
        Write-Step "  Pipelines: $plCount deployed"
        if ([int]$plCount -ge 6) {
            Write-Step "  All 6 pipelines deployed" "SUCCESS"
        }
        else {
            Write-Step "  WARNING: Expected 6 pipelines but found $plCount" "WARNING"
        }

        Write-Step "Step 7 completed in $([math]::Round(((Get-Date) - $stepStart).TotalSeconds))s" "SUCCESS"
        $stepResults[7] = "SUCCESS"
    }
    catch {
        Write-Step "Step 7 FAILED: $_" "ERROR"
        Write-Step $_.ScriptStackTrace "ERROR"
        $stepResults[7] = "FAILED"
        throw "Step 7 failed. Fix the error and re-run with -StartFromStep 7"
    }
}
else {
    Write-Step "STEP 7: SKIPPED (StartFromStep=$StartFromStep)" "WARNING"
    $stepResults[7] = "SKIPPED"
}

# ============================================================
# STEP 8: Populate Control Table
# ============================================================
if (Should-RunStep 8) {
    Write-Step ""
    Write-Step "========== STEP 8/9: Populate Control Table ==========" "HEADER"
    $stepStart = Get-Date

    if (-not $ClientId) {
        Write-Step "ERROR: -ClientId is required for Step 8" "ERROR"
        Write-Step "Provide the Azure AD App Registration Client ID from Step 2" "ERROR"
        $stepResults[8] = "FAILED"
        throw "Step 8 requires -ClientId. Re-run with -StartFromStep 8 -ClientId '<app-id>'"
    }

    try {
        $popParams = @{
            SharePointTenantUrl = $SharePointTenantUrl
            ClientId            = $ClientId
            SqlServerName       = $sqlServer
            SqlDatabaseName     = $sqlDatabase
        }
        if ($SpecificSites) { $popParams.SpecificSites = $SpecificSites }
        if ($SqlUsername) { $popParams.SqlUsername = $SqlUsername }
        if ($SqlPassword) { $popParams.SqlPassword = $SqlPassword }

        Write-Step "Running Populate-ControlTable.ps1..."
        Write-Step "  SharePointTenantUrl: $SharePointTenantUrl"
        Write-Step "  ClientId:            $ClientId"
        Write-Step "  SqlServer:           $sqlServer"
        Write-Step "  SpecificSites:       $(if ($SpecificSites) { $SpecificSites -join ', ' } else { '(all sites)' })"
        Write-Step "  SQL Auth:            $(if ($SqlUsername) { "SQL ($SqlUsername)" } else { 'AD Integrated' })"

        & "$scriptDir\Populate-ControlTable.ps1" @popParams

        Write-Step "Step 8 completed in $([math]::Round(((Get-Date) - $stepStart).TotalSeconds))s" "SUCCESS"
        $stepResults[8] = "SUCCESS"
    }
    catch {
        Write-Step "Step 8 FAILED: $_" "ERROR"
        Write-Step $_.ScriptStackTrace "ERROR"
        $stepResults[8] = "FAILED"
        throw "Step 8 failed. Fix the error and re-run with -StartFromStep 8"
    }
}
else {
    Write-Step "STEP 8: SKIPPED (StartFromStep=$StartFromStep)" "WARNING"
    $stepResults[8] = "SKIPPED"
}

# ============================================================
# STEP 9: Final Verification
# ============================================================
if (Should-RunStep 9) {
    Write-Step ""
    Write-Step "========== STEP 9/9: Final Verification ==========" "HEADER"
    $stepStart = Get-Date

    $checks = @()

    # Check 1: Resource Group exists
    try {
        $rg = az group show --name $rgName --query "name" -o tsv 2>$null
        $checks += @{ Name = "Resource Group"; Status = $(if ($rg) { "PASS" } else { "FAIL" }) }
    }
    catch { $checks += @{ Name = "Resource Group"; Status = "FAIL" } }

    # Check 2: ADF exists with managed identity
    try {
        $mi = az datafactory show --resource-group $rgName --name $adfName --query "identity.type" -o tsv 2>$null
        $checks += @{ Name = "ADF Managed Identity"; Status = $(if ($mi -eq "SystemAssigned") { "PASS" } else { "FAIL" }) }
    }
    catch { $checks += @{ Name = "ADF Managed Identity"; Status = "FAIL" } }

    # Check 3: Pipelines deployed
    try {
        $plCount = az datafactory pipeline list --resource-group $rgName --factory-name $adfName --query "length(@)" -o tsv 2>$null
        if (-not $plCount) { $plCount = "0" }
        $checks += @{ Name = "ADF Pipelines ($plCount/6)"; Status = $(if ([int]$plCount -ge 6) { "PASS" } else { "FAIL" }) }
    }
    catch { $checks += @{ Name = "ADF Pipelines"; Status = "FAIL" } }

    # Check 4: SQL connectivity
    try {
        if ($SqlUsername) {
            $pwToUse = if ($SqlPassword) { $SqlPassword } elseif ($SqlAdminPassword) { $SqlAdminPassword } else { $null }
            if (-not $pwToUse) {
                throw "No SQL password available for verification"
            }
            $plainPw = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
                [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($pwToUse))
            $sqlTest = & sqlcmd -S $sqlFqdn -d $sqlDatabase -U $SqlUsername -P $plainPw -Q "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES" -h -1 -W 2>$null
        }
        else {
            $sqlTest = & sqlcmd -S $sqlFqdn -d $sqlDatabase -G -Q "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES" -h -1 -W 2>$null
        }
        $tableCount = ($sqlTest | Where-Object { $_ -match '^\d+$' } | Select-Object -First 1)
        $checks += @{ Name = "SQL Tables ($tableCount)"; Status = $(if ([int]$tableCount -ge 6) { "PASS" } else { "WARN" }) }
    }
    catch { $checks += @{ Name = "SQL Connectivity"; Status = "FAIL" } }

    # Check 5: Control table has data (reuse $plainPw from Check 4)
    try {
        if ($SqlUsername -and $plainPw) {
            $rowCount = & sqlcmd -S $sqlFqdn -d $sqlDatabase -U $SqlUsername -P $plainPw -Q "SELECT COUNT(*) FROM dbo.MigrationControl" -h -1 -W 2>$null
        }
        else {
            $rowCount = & sqlcmd -S $sqlFqdn -d $sqlDatabase -G -Q "SELECT COUNT(*) FROM dbo.MigrationControl" -h -1 -W 2>$null
        }
        $rows = ($rowCount | Where-Object { $_ -match '^\d+$' } | Select-Object -First 1)
        $checks += @{ Name = "Control Table Rows ($rows)"; Status = $(if ([int]$rows -gt 0) { "PASS" } else { "WARN" }) }
    }
    catch { $checks += @{ Name = "Control Table"; Status = "FAIL" } }

    # Check 6: Storage account
    try {
        $hns = az storage account show --name $storageName --query "isHnsEnabled" -o tsv 2>$null
        $checks += @{ Name = "ADLS Gen2 (HNS=$hns)"; Status = $(if ($hns -eq "true") { "PASS" } else { "FAIL" }) }
    }
    catch { $checks += @{ Name = "ADLS Gen2"; Status = "FAIL" } }

    # Print results
    Write-Step ""
    Write-Step "  Verification Results:" "HEADER"
    Write-Step "  -------------------------------------------"
    foreach ($check in $checks) {
        $icon = switch ($check.Status) { "PASS" { "PASS" } "WARN" { "WARN" } default { "FAIL" } }
        Write-Step "  [$icon] $($check.Name)" $(switch ($check.Status) { "PASS" { "SUCCESS" } "WARN" { "WARNING" } default { "ERROR" } })
    }

    $failCount = ($checks | Where-Object { $_.Status -eq "FAIL" }).Count
    if ($failCount -eq 0) {
        Write-Step "  All checks passed!" "SUCCESS"
    }
    else {
        Write-Step "  $failCount check(s) failed — review above" "WARNING"
    }

    Write-Step "Step 9 completed in $([math]::Round(((Get-Date) - $stepStart).TotalSeconds))s" "SUCCESS"
    $stepResults[9] = "SUCCESS"
}
else {
    Write-Step "STEP 9: SKIPPED (StartFromStep=$StartFromStep)" "WARNING"
    $stepResults[9] = "SKIPPED"
}

# ============================================================
# SUMMARY
# ============================================================
$totalDuration = [math]::Round(((Get-Date) - $overallStart).TotalMinutes, 1)

Write-Step ""
Write-Step "============================================================" "HEADER"
Write-Step "  DEPLOYMENT SUMMARY" "HEADER"
Write-Step "============================================================" "HEADER"
Write-Step "  Duration: $totalDuration minutes"
Write-Step ""
for ($i = 1; $i -le 9; $i++) {
    $stepName = switch ($i) {
        1 { "Provision Azure Resources" }
        2 { "Register SharePoint App" }
        3 { "Admin Consent" }
        4 { "Enable Network Access" }
        5 { "Initialize SQL Database" }
        6 { "Grant ADF MI SQL Access" }
        7 { "Deploy ADF ARM Templates" }
        8 { "Populate Control Table" }
        9 { "Final Verification" }
    }
    $status = if ($stepResults.ContainsKey($i)) { $stepResults[$i] } else { "NOT RUN" }
    $level = switch ($status) { "SUCCESS" { "SUCCESS" } "SKIPPED" { "WARNING" } "MANUAL" { "WARNING" } default { "ERROR" } }
    Write-Step "  Step $i  [$status]  $stepName" $level
}

Write-Step ""
Write-Step "  Log file: $logFile"
Write-Step ""

if ($stepResults.Values -notcontains "FAILED") {
    Write-Step "  DEPLOYMENT COMPLETE — Ready to run pilot migration (Step 9 in README)" "SUCCESS"
    Write-Step ""
    Write-Step "  Next: Go to ADF Studio > Author > PL_Master_Migration_Orchestrator > Debug" "INFO"
}
else {
    Write-Step "  DEPLOYMENT INCOMPLETE — Fix failed steps and re-run with -StartFromStep <N>" "ERROR"
}

Write-Step "============================================================" "HEADER"
