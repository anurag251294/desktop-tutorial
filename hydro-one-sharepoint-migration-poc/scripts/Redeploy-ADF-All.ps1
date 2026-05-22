<#
.SYNOPSIS
    Clean redeploy of every ADF object in this repo for the Hydro One SharePoint
    migration POC. Use this when the deployed factory has drift, debug mode is
    broken, or you want to normalize the factory back to repo state.

.DESCRIPTION
    Deploys in dependency order:
      1. 4 linked services (Key Vault, ADLS/Blob, SQL, HTTP Graph Download)
      2. 3 dataset templates (which create 7 datasets)
      3. 6 pipelines (children before parents)

    Idempotent — re-running OVERWRITES the existing objects with the repo
    versions. Pipelines and datasets keep their data (control table is in SQL,
    not in ADF) but in-flight runs may be affected. Run during a quiet window.

    Includes commit b90f74d's LS_HTTP_Graph_Download fix automatically.

.PARAMETER Factory
    Name of the Azure Data Factory instance.

.PARAMETER ResourceGroup
    Resource group containing the factory.

.PARAMETER StorageAccount
    ADLS Gen2 storage account name (used by LS_AzureBlobStorage).

.PARAMETER SqlServer
    Azure SQL server name (without .database.windows.net).

.PARAMETER SqlDatabase
    SQL database name (typically "MigrationControl").

.PARAMETER KeyVault
    Key Vault name (used by LS_KeyVault).

.PARAMETER SubscriptionId
    Azure subscription containing all of the above.

.PARAMETER SkipPipelines
    Skip the pipeline deployment step (only redeploys linked services + datasets).

.EXAMPLE
    .\Redeploy-ADF-All.ps1 `
        -Factory "adf-hydroone-migration-prd" `
        -ResourceGroup "rg-hydroone-migration-prd" `
        -StorageAccount "sthydroonemigprd" `
        -SqlServer "sql-hydroone-migration-prd" `
        -SqlDatabase "MigrationControl" `
        -KeyVault "kv-hydroone-prd" `
        -SubscriptionId "<sub-guid>"

.NOTES
    Requires: Azure CLI logged in (az login) with Contributor on the factory.
    Runs from the repo root (cd to hydro-one-sharepoint-migration-poc first).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Factory,
    [Parameter(Mandatory=$true)][string]$ResourceGroup,
    [Parameter(Mandatory=$true)][string]$StorageAccount,
    [Parameter(Mandatory=$true)][string]$SqlServer,
    [Parameter(Mandatory=$true)][string]$SqlDatabase,
    [Parameter(Mandatory=$true)][string]$KeyVault,
    [Parameter(Mandatory=$true)][string]$SubscriptionId,
    [switch]$SkipPipelines
)

$ErrorActionPreference = "Stop"
$templateDir = "adf-templates"

function Deploy-Template {
    param([string]$Name, [string]$TemplateFile, [hashtable]$Params)
    Write-Host "  [$Name] " -NoNewline -ForegroundColor Cyan

    $paramArgs = @()
    foreach ($k in $Params.Keys) { $paramArgs += "$k=$($Params[$k])" }

    $depName = "redeploy-$($Name.ToLower().Replace('_','-'))-$(Get-Date -Format 'HHmmss')"
    & az deployment group create `
        --resource-group $ResourceGroup `
        --template-file $TemplateFile `
        --parameters $paramArgs `
        --name $depName `
        -o none

    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED" -ForegroundColor Red
        throw "Deployment failed for $Name"
    }
    Write-Host "OK" -ForegroundColor Green
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Yellow
Write-Host "ADF FULL REDEPLOY"                              -ForegroundColor Yellow
Write-Host "============================================" -ForegroundColor Yellow
Write-Host "  Factory:        $Factory"
Write-Host "  Resource Group: $ResourceGroup"
Write-Host "  Subscription:   $SubscriptionId"
Write-Host ""

# Ensure CLI is targeting the right subscription
& az account set --subscription $SubscriptionId
if ($LASTEXITCODE -ne 0) { throw "az account set failed" }

# ---------- STEP 1: Linked Services ----------
Write-Host "=== STEP 1/3: Linked Services ===" -ForegroundColor Yellow

Deploy-Template -Name "LS_KeyVault" `
    -TemplateFile "$templateDir\linkedServices\LS_KeyVault.json" `
    -Params @{
        factoryName           = $Factory
        keyVaultName          = $KeyVault
        keyVaultResourceGroup = $ResourceGroup
        subscriptionId        = $SubscriptionId
    }

Deploy-Template -Name "LS_AzureBlobStorage_and_ADLS_Gen2" `
    -TemplateFile "$templateDir\linkedServices\LS_AzureBlobStorage.json" `
    -Params @{
        factoryName        = $Factory
        storageAccountName = $StorageAccount
    }

Deploy-Template -Name "LS_AzureSqlDatabase" `
    -TemplateFile "$templateDir\linkedServices\LS_AzureSqlDatabase.json" `
    -Params @{
        factoryName     = $Factory
        sqlServerName   = $SqlServer
        sqlDatabaseName = $SqlDatabase
    }

# This is the one with the b90f74d fix (defaultValue on downloadUrl)
Deploy-Template -Name "LS_HTTP_Graph_Download" `
    -TemplateFile "$templateDir\linkedServices\LS_HTTP_Graph_Download.json" `
    -Params @{ factoryName = $Factory }

# ---------- STEP 2: Datasets ----------
Write-Host ""
Write-Host "=== STEP 2/3: Datasets ===" -ForegroundColor Yellow

Deploy-Template -Name "DS_SQL_ControlTables" `
    -TemplateFile "$templateDir\datasets\DS_SQL_ControlTables.json" `
    -Params @{ factoryName = $Factory }

Deploy-Template -Name "DS_ADLS_Sink" `
    -TemplateFile "$templateDir\datasets\DS_ADLS_Sink.json" `
    -Params @{ factoryName = $Factory }

Deploy-Template -Name "DS_Graph_Content_Download" `
    -TemplateFile "$templateDir\datasets\DS_Graph_Content_Download.json" `
    -Params @{ factoryName = $Factory }

# ---------- STEP 3: Pipelines (children before parents) ----------
if ($SkipPipelines) {
    Write-Host ""
    Write-Host "=== STEP 3/3: Pipelines (SKIPPED via -SkipPipelines) ===" -ForegroundColor DarkGray
}
else {
    Write-Host ""
    Write-Host "=== STEP 3/3: Pipelines ===" -ForegroundColor Yellow

    $pipelines = @(
        "PL_Copy_File_Batch",                  # child, no pipeline deps
        "PL_Process_Subfolder",                # used by Single_Library
        "PL_Migrate_Single_Library",           # calls Copy_File_Batch
        "PL_Incremental_Sync",                 # calls Copy_File_Batch
        "PL_Validation",                       # leaf
        "PL_Master_Migration_Orchestrator"     # calls Migrate_Single_Library
    )
    foreach ($pl in $pipelines) {
        Deploy-Template -Name $pl `
            -TemplateFile "$templateDir\pipelines\$pl.json" `
            -Params @{ factoryName = $Factory }
    }
}

# ---------- Verify ----------
Write-Host ""
Write-Host "============================================" -ForegroundColor Yellow
Write-Host "POST-DEPLOY VERIFICATION"                      -ForegroundColor Yellow
Write-Host "============================================" -ForegroundColor Yellow

Write-Host ""
Write-Host "Linked services with required parameters lacking defaults (should be empty):"
$lsList = & az datafactory linked-service list --resource-group $ResourceGroup --factory-name $Factory -o json | ConvertFrom-Json
$bad = @()
foreach ($ls in $lsList) {
    if ($ls.properties.parameters) {
        foreach ($pName in $ls.properties.parameters.PSObject.Properties.Name) {
            $p = $ls.properties.parameters.$pName
            if (-not $p.defaultValue) {
                $bad += "  - $($ls.name).$pName ($($p.type))"
            }
        }
    }
}
if ($bad.Count -eq 0) {
    Write-Host "  None - all linked-service parameters have defaults." -ForegroundColor Green
} else {
    Write-Host "  Found offenders (will likely break Debug mode):" -ForegroundColor Yellow
    $bad | ForEach-Object { Write-Host $_ -ForegroundColor Yellow }
}

Write-Host ""
Write-Host "Triggering a trigger-mode smoke test of PL_Master_Migration_Orchestrator..."
$runId = & az datafactory pipeline create-run `
    --resource-group $ResourceGroup `
    --factory-name $Factory `
    --name "PL_Master_Migration_Orchestrator" `
    --query runId -o tsv
Write-Host "  RunId: $runId" -ForegroundColor Cyan
Write-Host "  Watch in ADF Studio -> Monitor, or:"
Write-Host "    az datafactory pipeline-run show --resource-group $ResourceGroup --factory-name $Factory --run-id $runId" -ForegroundColor DarkGray

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "REDEPLOY COMPLETE"                              -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next:"
Write-Host "  1. Hard-refresh ADF Studio (Ctrl+F5)."
Write-Host "  2. Open PL_Master_Migration_Orchestrator and click Debug -"
Write-Host "     a sandbox should now start (was the original ticket symptom)."
Write-Host "  3. Watch the trigger-mode smoke test runId above to completion."
Write-Host ""
