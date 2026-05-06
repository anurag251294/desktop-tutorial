<#
.SYNOPSIS
    Registers an Azure AD application with SharePoint Online permissions for the migration.

.DESCRIPTION
    This script:
    - Creates an Azure AD App Registration
    - Configures SharePoint Sites.Read.All permissions
    - Creates a client secret
    - Stores credentials in Azure Key Vault
    - Outputs configuration needed for ADF linked service

.PARAMETER TenantId
    Azure AD Tenant ID

.PARAMETER KeyVaultName
    Name of the Azure Key Vault to store the client secret

.PARAMETER AppDisplayName
    Display name for the App Registration (default: HydroOne-SPO-Migration)

.EXAMPLE
    .\Register-SharePointApp.ps1 -TenantId "your-tenant-id" -KeyVaultName "kv-hydroone-mig-dev"

.NOTES
    Author: Microsoft Azure Data Engineering Team
    Project: Hydro One SharePoint Migration POC
    Requires: Az PowerShell module, Azure AD admin permissions
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$TenantId,

    [Parameter(Mandatory = $true)]
    [string]$KeyVaultName,

    [Parameter(Mandatory = $false)]
    [string]$AppDisplayName = "HydroOne-SPO-Migration",

    [Parameter(Mandatory = $false)]
    [string]$SharePointTenantUrl = "https://hydroone.sharepoint.com",

    [Parameter(Mandatory = $false)]
    [int]$SecretValidityYears = 2
)

#region Configuration
$ErrorActionPreference = "Stop"

# SharePoint API permissions
$sharePointApiId = "00000003-0000-0ff1-ce00-000000000000"  # SharePoint Online
$graphApiId = "00000003-0000-0000-c000-000000000000"       # Microsoft Graph

# Permission IDs
$permissions = @{
    # SharePoint permissions
    "Sites.Read.All"        = "4e0d77b0-96ba-4398-af14-3c495f19a6a9"  # SharePoint Sites.Read.All
    "Sites.ReadWrite.All"   = "9492366f-7969-46a4-8d15-ed1a20078fff"  # SharePoint Sites.ReadWrite.All

    # Graph permissions (for user context operations)
    "Files.Read.All"        = "01d4889c-1287-42c6-ac1f-5d1e02578ef6"  # Graph Files.Read.All
    "Sites.Read.All.Graph"  = "332a536c-c7ef-4017-ab91-336970924f0d"  # Graph Sites.Read.All
}
#endregion

#region Functions
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $color = switch ($Level) {
        "INFO"    { "White" }
        "SUCCESS" { "Green" }
        "WARNING" { "Yellow" }
        "ERROR"   { "Red" }
        default   { "White" }
    }
    Write-Host "[$timestamp] [$Level] $Message" -ForegroundColor $color
}

function New-SecurePassword {
    param([int]$Length = 32)
    $chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*'
    $password = -join ((1..$Length) | ForEach-Object { $chars[(Get-Random -Maximum $chars.Length)] })
    return $password
}
#endregion

#region Main Script
Write-Log "========================================" -Level "INFO"
Write-Log "SharePoint App Registration Setup" -Level "INFO"
Write-Log "Tenant ID: $TenantId" -Level "INFO"
Write-Log "App Name: $AppDisplayName" -Level "INFO"
Write-Log "========================================" -Level "INFO"

try {
    # Check Azure login
    $context = Get-AzContext
    if (-not $context) {
        Write-Log "Not logged in to Azure. Running Connect-AzAccount..." -Level "WARNING"
        Connect-AzAccount -TenantId $TenantId
    }

    # Check if app already exists (filter for exact match — Get-AzADApplication does startsWith)
    Write-Log "Checking for existing app registration..." -Level "INFO"
    $existingApps = @(Get-AzADApplication -DisplayName $AppDisplayName -ErrorAction SilentlyContinue)
    $existingApp = $existingApps | Where-Object { $_.DisplayName -eq $AppDisplayName } | Select-Object -First 1

    if ($existingApp) {
        Write-Log "App registration '$AppDisplayName' already exists. AppId: $($existingApp.AppId)" -Level "WARNING"
        $useExisting = Read-Host "Do you want to use the existing app and create a new secret? (Y/N)"
        if ($useExisting -ne "Y") {
            Write-Log "Exiting without changes." -Level "INFO"
            exit 0
        }
        $app = $existingApp
    }
    else {
        # Create App Registration
        Write-Log "Creating App Registration: $AppDisplayName..." -Level "INFO"

        $app = New-AzADApplication `
            -DisplayName $AppDisplayName `
            -SignInAudience "AzureADMyOrg" `
            -IdentifierUris "api://$AppDisplayName"

        Write-Log "App Registration created. AppId: $($app.AppId)" -Level "SUCCESS"

        # Create Service Principal
        Write-Log "Creating Service Principal..." -Level "INFO"
        $sp = New-AzADServicePrincipal -ApplicationId $app.AppId
        Write-Log "Service Principal created. ObjectId: $($sp.Id)" -Level "SUCCESS"

        # Add API Permissions
        Write-Log "Adding API permissions..." -Level "INFO"

        # Note: Adding permissions programmatically requires specific setup
        # The permissions need to be granted admin consent via Azure Portal
        Write-Log "IMPORTANT: Admin consent required for the following permissions:" -Level "WARNING"
        Write-Log "  - SharePoint: Sites.Read.All (Application)" -Level "WARNING"
        Write-Log "  - Microsoft Graph: Sites.Read.All (Application)" -Level "WARNING"
        Write-Log "Please grant admin consent in Azure Portal: Enterprise Applications > $AppDisplayName > Permissions" -Level "WARNING"
    }

    # Create Client Secret
    Write-Log "Creating client secret (valid for $SecretValidityYears years)..." -Level "INFO"
    $endDate = (Get-Date).AddYears($SecretValidityYears)

    $secret = New-AzADAppCredential `
        -ObjectId $app.Id `
        -EndDate $endDate

    $clientSecret = $secret.SecretText
    if (-not $clientSecret) {
        throw "Failed to retrieve client secret text. This can happen with older Az module versions. Please update the Az.Resources module (Update-Module Az.Resources) and retry."
    }
    Write-Log "Client secret created. Expires: $endDate" -Level "SUCCESS"

    # Store in Key Vault
    Write-Log "Storing credentials in Key Vault: $KeyVaultName..." -Level "INFO"

    # Store client secret
    $secretValue = ConvertTo-SecureString -String $clientSecret -AsPlainText -Force
    Set-AzKeyVaultSecret `
        -VaultName $KeyVaultName `
        -Name "sharepoint-client-secret" `
        -SecretValue $secretValue `
        -ContentType "application/x-sharepoint-client-secret" `
        -Tag @{
            "AppName"     = $AppDisplayName
            "AppId"       = $app.AppId
            "CreatedDate" = (Get-Date -Format "yyyy-MM-dd")
            "ExpiryDate"  = $endDate.ToString("yyyy-MM-dd")
        } | Out-Null
    Write-Log "Client secret stored as 'sharepoint-client-secret'" -Level "SUCCESS"

    # Store tenant ID
    $tenantSecretValue = ConvertTo-SecureString -String $TenantId -AsPlainText -Force
    Set-AzKeyVaultSecret `
        -VaultName $KeyVaultName `
        -Name "sharepoint-tenant-id" `
        -SecretValue $tenantSecretValue `
        -ContentType "application/x-tenant-id" | Out-Null
    Write-Log "Tenant ID stored as 'sharepoint-tenant-id'" -Level "SUCCESS"

    # Store client ID
    $clientIdSecretValue = ConvertTo-SecureString -String $app.AppId -AsPlainText -Force
    Set-AzKeyVaultSecret `
        -VaultName $KeyVaultName `
        -Name "sharepoint-client-id" `
        -SecretValue $clientIdSecretValue `
        -ContentType "application/x-client-id" | Out-Null
    Write-Log "Client ID stored as 'sharepoint-client-id'" -Level "SUCCESS"

    # Output summary
    Write-Log "========================================" -Level "INFO"
    Write-Log "APP REGISTRATION SUMMARY" -Level "SUCCESS"
    Write-Log "========================================" -Level "INFO"
    Write-Log "Application Name:    $AppDisplayName" -Level "INFO"
    Write-Log "Application ID:      $($app.AppId)" -Level "INFO"
    Write-Log "Object ID:           $($app.Id)" -Level "INFO"
    Write-Log "Tenant ID:           $TenantId" -Level "INFO"
    Write-Log "Secret Expiry:       $endDate" -Level "INFO"
    Write-Log "Key Vault:           $KeyVaultName" -Level "INFO"
    Write-Log "========================================" -Level "INFO"

    Write-Log "" -Level "INFO"
    Write-Log "NEXT STEPS:" -Level "WARNING"
    Write-Log "1. Go to Azure Portal > Azure Active Directory > App Registrations" -Level "INFO"
    Write-Log "2. Find '$AppDisplayName' and click on it" -Level "INFO"
    Write-Log "3. Go to 'API permissions'" -Level "INFO"
    Write-Log "4. Click 'Add a permission' > 'SharePoint' > 'Application permissions'" -Level "INFO"
    Write-Log "5. Select 'Sites.Read.All' (or Sites.ReadWrite.All if write access needed)" -Level "INFO"
    Write-Log "6. Click 'Grant admin consent for [Tenant]'" -Level "INFO"
    Write-Log "" -Level "INFO"

    # For ADF configuration
    Write-Log "ADF LINKED SERVICE CONFIGURATION:" -Level "INFO"
    Write-Log "  Service Principal ID: $($app.AppId)" -Level "INFO"
    Write-Log "  Tenant ID: $TenantId" -Level "INFO"
    Write-Log "  SharePoint URL: $SharePointTenantUrl" -Level "INFO"
    Write-Log "  Key Vault Secret Name: sharepoint-client-secret" -Level "INFO"

    # Save configuration to file
    $configPath = Join-Path $PSScriptRoot "sharepoint-app-config.json"
    @{
        appDisplayName       = $AppDisplayName
        applicationId        = $app.AppId
        objectId             = $app.Id
        tenantId             = $TenantId
        sharePointTenantUrl  = $SharePointTenantUrl
        keyVaultName         = $KeyVaultName
        secretName           = "sharepoint-client-secret"
        secretExpiry         = $endDate.ToString("yyyy-MM-ddTHH:mm:ssZ")
        createdAt            = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
    } | ConvertTo-Json | Out-File $configPath -Encoding UTF8

    Write-Log "Configuration saved to: $configPath" -Level "SUCCESS"
    Write-Log "Setup completed successfully!" -Level "SUCCESS"

}
catch {
    Write-Log "Error during setup: $_" -Level "ERROR"
    Write-Log $_.Exception.Message -Level "ERROR"
    exit 1
}
#endregion
