<#
.SYNOPSIS
    Adds delegated SharePoint and Microsoft Graph permissions to the Entra ID app
    used by Populate-ControlTable.ps1, then grants admin consent.

.DESCRIPTION
    The migration app was originally registered with Application permissions for ADF
    (Sites.Read.All, Files.Read.All as Role). Those work for ADF's app-only flow but
    do nothing for the interactive PowerShell flow used by Populate-ControlTable.ps1.

    This script adds the matching Delegated permissions (Scope) and grants admin
    consent so PnP PowerShell can enumerate sites and lists when a user signs in
    interactively.

    Existing Application permissions are preserved - this script only ADDS new
    Delegated permissions.

.PARAMETER AppId
    Object ID or App (client) ID of the Entra app to update.
    Default: aa1cf16f-29fb-4f44-bd68-8522910afffb (HydroOne-SPO-Migration)

.PARAMETER TenantId
    Tenant ID where the app is registered (Hydro One SharePoint tenant).
    If not provided, uses the currently signed-in tenant.

.PARAMETER SkipLogin
    Skip the az login step (use the already-authenticated session).

.PARAMETER SkipConsent
    Add the permissions but don't grant admin consent.
    Use this if your account doesn't have Global Admin and someone else
    will run the consent step.

.EXAMPLE
    .\Grant-DelegatedPermissions.ps1 -TenantId "<hydro-one-tenant-id>"

.EXAMPLE
    .\Grant-DelegatedPermissions.ps1 -AppId "aa1cf16f-29fb-4f44-bd68-8522910afffb" -SkipLogin

.NOTES
    Requires:
      - Azure CLI 2.50+
      - Application Administrator (or higher) to add permissions
      - Global Administrator or Privileged Role Administrator to grant consent
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$AppId = "aa1cf16f-29fb-4f44-bd68-8522910afffb",

    [Parameter(Mandatory = $false)]
    [string]$TenantId,

    [Parameter(Mandatory = $false)]
    [switch]$SkipLogin,

    [Parameter(Mandatory = $false)]
    [switch]$SkipConsent
)

$ErrorActionPreference = "Stop"

# === Well-known resource and permission GUIDs (stable across all tenants) ===

# Microsoft Graph
$GraphResourceId    = "00000003-0000-0000-c000-000000000000"
$GraphSitesReadAll  = "205e70e5-aba6-4c52-a976-6d2d46c48043"  # Sites.Read.All  (Delegated)
$GraphUserRead      = "e1fe6dd8-ba31-4d61-89e7-88639da4683d"  # User.Read        (Delegated)

# SharePoint Online
$SpoResourceId      = "00000003-0000-0ff1-ce00-000000000000"
$SpoAllSitesRead    = "4e0d77b0-96ba-4398-af14-3baa780278f4"  # AllSites.Read    (Delegated)

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "================================================================" -ForegroundColor Cyan
    Write-Host " $Title" -ForegroundColor Cyan
    Write-Host "================================================================" -ForegroundColor Cyan
}

function Invoke-Az {
    param([string[]]$AzArgs, [string]$Description)
    Write-Host "[$Description]" -ForegroundColor Yellow
    Write-Host "  > az $($AzArgs -join ' ')" -ForegroundColor DarkGray
    & az @AzArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed (exit $LASTEXITCODE): az $($AzArgs -join ' ')"
    }
}

# ---------------------------------------------------------------------------
Write-Section "Hydro One Migration App - Delegated Permissions Setup"
Write-Host "App ID:      $AppId"
Write-Host "Tenant ID:   $(if ($TenantId) { $TenantId } else { '(use current az session)' })"
Write-Host "Skip login:  $SkipLogin"
Write-Host "Skip consent:$SkipConsent"

# ---------------------------------------------------------------------------
if (-not $SkipLogin) {
    Write-Section "Step 1: Sign in to Azure"
    if ($TenantId) {
        Invoke-Az -AzArgs @("login", "--tenant", $TenantId) -Description "az login --tenant $TenantId"
    }
    else {
        Invoke-Az -AzArgs @("login") -Description "az login (interactive)"
    }
}
else {
    Write-Host "[Skipping login - using existing az session]" -ForegroundColor Yellow
}

# Confirm tenant
Write-Section "Step 2: Verify active tenant"
$accountJson = az account show --output json 2>$null
if ($LASTEXITCODE -ne 0 -or -not $accountJson) {
    throw "Not signed in to Azure CLI. Run 'az login' first."
}
$account = $accountJson | ConvertFrom-Json
Write-Host "Signed in as: $($account.user.name)"
Write-Host "Tenant ID:    $($account.tenantId)"
Write-Host "Tenant name:  $($account.user.name -replace '.*@','')"

if ($TenantId -and $account.tenantId -ne $TenantId) {
    Write-Warning "Expected tenant $TenantId but signed in to $($account.tenantId)."
    $confirm = Read-Host "Continue anyway? (y/N)"
    if ($confirm -ne "y") { exit 1 }
}

# Confirm app exists
Write-Section "Step 3: Verify app exists"
$app = az ad app show --id $AppId --output json 2>$null | ConvertFrom-Json
if (-not $app) {
    throw "App '$AppId' not found in tenant $($account.tenantId). Are you signed in to the right tenant?"
}
Write-Host "Found app: $($app.displayName) (AppId: $($app.appId), ObjectId: $($app.id))"

# ---------------------------------------------------------------------------
Write-Section "Step 4: Add Microsoft Graph delegated permissions"

Invoke-Az -AzArgs @(
    "ad", "app", "permission", "add",
    "--id", $AppId,
    "--api", $GraphResourceId,
    "--api-permissions", "$GraphSitesReadAll=Scope"
) -Description "Add Microsoft Graph: Sites.Read.All (Delegated)"

Invoke-Az -AzArgs @(
    "ad", "app", "permission", "add",
    "--id", $AppId,
    "--api", $GraphResourceId,
    "--api-permissions", "$GraphUserRead=Scope"
) -Description "Add Microsoft Graph: User.Read (Delegated)"

# ---------------------------------------------------------------------------
Write-Section "Step 5: Add SharePoint delegated permission"

Invoke-Az -AzArgs @(
    "ad", "app", "permission", "add",
    "--id", $AppId,
    "--api", $SpoResourceId,
    "--api-permissions", "$SpoAllSitesRead=Scope"
) -Description "Add SharePoint: AllSites.Read (Delegated)"

# ---------------------------------------------------------------------------
if (-not $SkipConsent) {
    Write-Section "Step 6: Grant admin consent (requires Global Admin)"
    try {
        Invoke-Az -AzArgs @("ad", "app", "permission", "admin-consent", "--id", $AppId) `
            -Description "Grant admin consent for tenant"
        Write-Host ""
        Write-Host "[OK] Admin consent granted." -ForegroundColor Green
    }
    catch {
        Write-Warning "Admin consent failed. Likely your account does not have Global Admin or Privileged Role Admin."
        Write-Warning "Ask someone with the right role to run:"
        Write-Warning "  az ad app permission admin-consent --id $AppId"
    }
}
else {
    Write-Host ""
    Write-Host "[Skipping admin consent as requested]" -ForegroundColor Yellow
    Write-Host "Have a Global Admin run:" -ForegroundColor Yellow
    Write-Host "  az ad app permission admin-consent --id $AppId" -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
Write-Section "Step 7: Verify final permission state"
Write-Host "Permissions configured on app:" -ForegroundColor Yellow
az ad app permission list --id $AppId --output table

Write-Host ""
Write-Host "Granted scopes (delegated consent):" -ForegroundColor Yellow
try {
    az ad app permission list-grants --id $AppId --output table 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  (Could not retrieve grant list — verify in Azure Portal)" -ForegroundColor DarkGray
    }
}
catch {
    Write-Host "  (Could not retrieve grant list — verify in Azure Portal)" -ForegroundColor DarkGray
}

Write-Section "Done"
Write-Host "Wait 1-2 minutes for token caches to refresh, then test with:" -ForegroundColor Green
Write-Host ""
Write-Host '  Connect-PnPOnline -Url "https://hydroone.sharepoint.com/teams/PLN-X-DPT-VAI-24" -Interactive -ClientId "' -NoNewline -ForegroundColor Green
Write-Host $AppId -NoNewline -ForegroundColor Green
Write-Host '"' -ForegroundColor Green
Write-Host '  Get-PnPList | Select-Object Title, BaseTemplate, Hidden, ItemCount | Format-Table -AutoSize' -ForegroundColor Green
Write-Host ""
Write-Host "You should now see multiple rows including a Document Library (BaseTemplate=101)." -ForegroundColor Green
