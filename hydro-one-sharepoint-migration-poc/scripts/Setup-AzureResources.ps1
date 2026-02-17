<#
.SYNOPSIS
    Provisions Azure resources required for the Hydro One SharePoint to ADLS migration.

.DESCRIPTION
    This script creates:
    - Resource Group
    - Azure Data Factory
    - ADLS Gen2 Storage Account (with hierarchical namespace)
    - Azure Key Vault
    - Azure SQL Database (for control tables)
    - Required RBAC role assignments

.PARAMETER Environment
    Target environment (dev, test, prod)

.PARAMETER Location
    Azure region for resources (default: canadacentral)

.PARAMETER SubscriptionId
    Azure subscription ID (optional, uses current context if not specified)

.EXAMPLE
    .\Setup-AzureResources.ps1 -Environment "dev" -Location "canadacentral"

.NOTES
    Author: Microsoft Azure Data Engineering Team
    Project: Hydro One SharePoint Migration POC
    Requires: Az PowerShell module
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("dev", "test", "prod")]
    [string]$Environment,

    [Parameter(Mandatory = $false)]
    [string]$Location = "canadacentral",

    [Parameter(Mandatory = $false)]
    [string]$SubscriptionId,

    [Parameter(Mandatory = $false)]
    [string]$SqlAdminUsername = "sqladmin",

    [Parameter(Mandatory = $false)]
    [SecureString]$SqlAdminPassword
)

#region Configuration
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Naming convention: {service}-{project}-{environment}
$projectName = "hydroone"
$resourceGroupName = "rg-$projectName-migration-$Environment"
$storageAccountName = "st$($projectName)mig$Environment".ToLower() -replace '[^a-z0-9]', ''
$dataFactoryName = "adf-$projectName-migration-$Environment"
$keyVaultName = "kv-$projectName-mig-$Environment"
$sqlServerName = "sql-$projectName-migration-$Environment"
$sqlDatabaseName = "MigrationControl"
$containerName = "sharepoint-migration"
$metadataContainerName = "migration-metadata"

# Tags for resource governance
$tags = @{
    "Project"     = "Hydro One SharePoint Migration"
    "Environment" = $Environment
    "CostCenter"  = "IT-Migration"
    "ManagedBy"   = "Terraform/ARM"
    "CreatedDate" = (Get-Date -Format "yyyy-MM-dd")
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

function Test-AzureLogin {
    try {
        $context = Get-AzContext
        if (-not $context) {
            Write-Log "Not logged in to Azure. Please run 'az login' or 'Connect-AzAccount' first." -Level "ERROR"
            return $false
        }
        Write-Log "Logged in as: $($context.Account.Id)" -Level "INFO"
        Write-Log "Subscription: $($context.Subscription.Name)" -Level "INFO"
        return $true
    }
    catch {
        Write-Log "Error checking Azure login: $_" -Level "ERROR"
        return $false
    }
}
#endregion

#region Main Script
Write-Log "========================================" -Level "INFO"
Write-Log "Hydro One SharePoint Migration - Azure Resource Setup" -Level "INFO"
Write-Log "Environment: $Environment" -Level "INFO"
Write-Log "Location: $Location" -Level "INFO"
Write-Log "========================================" -Level "INFO"

# Check Azure login
if (-not (Test-AzureLogin)) {
    exit 1
}

# Set subscription if specified
if ($SubscriptionId) {
    Write-Log "Setting subscription to: $SubscriptionId" -Level "INFO"
    Set-AzContext -SubscriptionId $SubscriptionId | Out-Null
}

# Prompt for SQL password if not provided
if (-not $SqlAdminPassword) {
    $SqlAdminPassword = Read-Host -Prompt "Enter SQL Admin Password" -AsSecureString
}

try {
    # 1. Create Resource Group
    Write-Log "Creating Resource Group: $resourceGroupName..." -Level "INFO"
    $rg = New-AzResourceGroup -Name $resourceGroupName -Location $Location -Tag $tags -Force
    Write-Log "Resource Group created successfully." -Level "SUCCESS"

    # 2. Create ADLS Gen2 Storage Account
    Write-Log "Creating ADLS Gen2 Storage Account: $storageAccountName..." -Level "INFO"
    $storageAccount = New-AzStorageAccount `
        -ResourceGroupName $resourceGroupName `
        -Name $storageAccountName `
        -Location $Location `
        -SkuName "Standard_LRS" `
        -Kind "StorageV2" `
        -EnableHierarchicalNamespace $true `
        -EnableHttpsTrafficOnly $true `
        -MinimumTlsVersion "TLS1_2" `
        -AllowBlobPublicAccess $false `
        -Tag $tags
    Write-Log "Storage Account created successfully." -Level "SUCCESS"

    # Create containers
    Write-Log "Creating storage containers..." -Level "INFO"
    $ctx = $storageAccount.Context
    New-AzStorageContainer -Name $containerName -Context $ctx -Permission Off | Out-Null
    New-AzStorageContainer -Name $metadataContainerName -Context $ctx -Permission Off | Out-Null
    Write-Log "Storage containers created." -Level "SUCCESS"

    # 3. Create Azure Key Vault
    Write-Log "Creating Azure Key Vault: $keyVaultName..." -Level "INFO"
    $keyVault = New-AzKeyVault `
        -ResourceGroupName $resourceGroupName `
        -VaultName $keyVaultName `
        -Location $Location `
        -EnabledForDeployment `
        -EnabledForTemplateDeployment `
        -EnablePurgeProtection `
        -EnableRbacAuthorization `
        -Sku "Standard" `
        -Tag $tags
    Write-Log "Key Vault created successfully." -Level "SUCCESS"

    # 4. Create Azure Data Factory
    Write-Log "Creating Azure Data Factory: $dataFactoryName..." -Level "INFO"
    $dataFactory = Set-AzDataFactoryV2 `
        -ResourceGroupName $resourceGroupName `
        -Name $dataFactoryName `
        -Location $Location `
        -Tag $tags
    Write-Log "Data Factory created successfully." -Level "SUCCESS"

    # 5. Create Azure SQL Server and Database
    Write-Log "Creating Azure SQL Server: $sqlServerName..." -Level "INFO"
    $sqlServer = New-AzSqlServer `
        -ResourceGroupName $resourceGroupName `
        -ServerName $sqlServerName `
        -Location $Location `
        -SqlAdministratorCredentials (New-Object System.Management.Automation.PSCredential($SqlAdminUsername, $SqlAdminPassword)) `
        -MinimalTlsVersion "1.2" `
        -Tag $tags
    Write-Log "SQL Server created successfully." -Level "SUCCESS"

    # Allow Azure services to access SQL Server
    Write-Log "Configuring SQL Server firewall..." -Level "INFO"
    New-AzSqlServerFirewallRule `
        -ResourceGroupName $resourceGroupName `
        -ServerName $sqlServerName `
        -FirewallRuleName "AllowAzureServices" `
        -StartIpAddress "0.0.0.0" `
        -EndIpAddress "0.0.0.0" | Out-Null

    Write-Log "Creating SQL Database: $sqlDatabaseName..." -Level "INFO"
    $sqlDatabase = New-AzSqlDatabase `
        -ResourceGroupName $resourceGroupName `
        -ServerName $sqlServerName `
        -DatabaseName $sqlDatabaseName `
        -Edition "Standard" `
        -RequestedServiceObjectiveName "S1" `
        -MaxSizeBytes 268435456000 `
        -Tag $tags
    Write-Log "SQL Database created successfully." -Level "SUCCESS"

    # 6. Configure RBAC - Grant ADF Managed Identity access to resources
    Write-Log "Configuring RBAC permissions..." -Level "INFO"

    # Get ADF Managed Identity
    $adfIdentity = (Get-AzDataFactoryV2 -ResourceGroupName $resourceGroupName -Name $dataFactoryName).Identity.PrincipalId

    # Grant ADF Storage Blob Data Contributor on Storage Account
    New-AzRoleAssignment `
        -ObjectId $adfIdentity `
        -RoleDefinitionName "Storage Blob Data Contributor" `
        -Scope $storageAccount.Id `
        -ErrorAction SilentlyContinue | Out-Null
    Write-Log "Granted Storage Blob Data Contributor to ADF." -Level "SUCCESS"

    # Grant ADF Key Vault Secrets User on Key Vault
    New-AzRoleAssignment `
        -ObjectId $adfIdentity `
        -RoleDefinitionName "Key Vault Secrets User" `
        -Scope $keyVault.ResourceId `
        -ErrorAction SilentlyContinue | Out-Null
    Write-Log "Granted Key Vault Secrets User to ADF." -Level "SUCCESS"

    # Enable Azure AD authentication for SQL Database
    Write-Log "Note: Configure Azure AD admin for SQL Server manually in Azure Portal." -Level "WARNING"

    # Output summary
    Write-Log "========================================" -Level "INFO"
    Write-Log "DEPLOYMENT SUMMARY" -Level "SUCCESS"
    Write-Log "========================================" -Level "INFO"
    Write-Log "Resource Group:    $resourceGroupName" -Level "INFO"
    Write-Log "Storage Account:   $storageAccountName" -Level "INFO"
    Write-Log "Data Factory:      $dataFactoryName" -Level "INFO"
    Write-Log "Key Vault:         $keyVaultName" -Level "INFO"
    Write-Log "SQL Server:        $sqlServerName.database.windows.net" -Level "INFO"
    Write-Log "SQL Database:      $sqlDatabaseName" -Level "INFO"
    Write-Log "ADF Identity:      $adfIdentity" -Level "INFO"
    Write-Log "========================================" -Level "INFO"

    # Create output file with resource details
    $outputPath = Join-Path $PSScriptRoot "deployment-output-$Environment.json"
    @{
        resourceGroupName   = $resourceGroupName
        storageAccountName  = $storageAccountName
        dataFactoryName     = $dataFactoryName
        keyVaultName        = $keyVaultName
        sqlServerName       = $sqlServerName
        sqlDatabaseName     = $sqlDatabaseName
        adfPrincipalId      = $adfIdentity
        location            = $Location
        environment         = $Environment
        deployedAt          = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
    } | ConvertTo-Json | Out-File $outputPath

    Write-Log "Deployment details saved to: $outputPath" -Level "SUCCESS"
    Write-Log "Setup completed successfully!" -Level "SUCCESS"

}
catch {
    Write-Log "Error during setup: $_" -Level "ERROR"
    Write-Log $_.Exception.Message -Level "ERROR"
    Write-Log $_.ScriptStackTrace -Level "ERROR"
    exit 1
}
#endregion
