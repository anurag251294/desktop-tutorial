<#
.SYNOPSIS
    Populates the migration control table with SharePoint site collections and document libraries.

.DESCRIPTION
    This script:
    - Connects to SharePoint Online using PnP PowerShell
    - Enumerates all site collections (or specific ones)
    - Gets all document libraries in each site
    - Calculates file counts and sizes
    - Populates the SQL control table

.PARAMETER SharePointTenantUrl
    SharePoint Online tenant URL (e.g., https://hydroone.sharepoint.com)

.PARAMETER SqlServerName
    Azure SQL Server name

.PARAMETER SqlDatabaseName
    Database name containing the control table

.PARAMETER SiteFilter
    Optional filter to limit which sites to enumerate (e.g., "*Documents*")

.EXAMPLE
    .\Populate-ControlTable.ps1 -SharePointTenantUrl "https://hydroone.sharepoint.com" `
        -SqlServerName "sql-hydroone-migration-dev" -SqlDatabaseName "MigrationControl"

.NOTES
    Author: Microsoft Azure Data Engineering Team
    Project: Hydro One SharePoint Migration POC
    Requires: PnP.PowerShell module, SqlServer module
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SharePointTenantUrl,

    [Parameter(Mandatory = $true)]
    [string]$SqlServerName,

    [Parameter(Mandatory = $true)]
    [string]$SqlDatabaseName,

    [Parameter(Mandatory = $false)]
    [string]$SiteFilter = "*",

    [Parameter(Mandatory = $false)]
    [string[]]$ExcludeSites = @(),

    [Parameter(Mandatory = $false)]
    [string[]]$SpecificSites = @(),

    [Parameter(Mandatory = $false)]
    [switch]$UseInteractiveAuth,

    [Parameter(Mandatory = $false)]
    [string]$ClientId,

    [Parameter(Mandatory = $false)]
    [string]$CertificateThumbprint
)

#region Configuration
$ErrorActionPreference = "Stop"
$ProgressPreference = "Continue"

# Libraries to exclude (system libraries)
$excludeLibraries = @(
    "Style Library",
    "Site Assets",
    "Site Pages",
    "Form Templates",
    "Preservation Hold Library",
    "_catalogs",
    "appdata",
    "Customized Reports",
    "Web Part Gallery",
    "Master Page Gallery"
)
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

function Get-LibraryStats {
    param(
        [string]$SiteUrl,
        [string]$LibraryName
    )

    try {
        $items = Get-PnPListItem -List $LibraryName -PageSize 5000 -Fields "FileLeafRef", "File_x0020_Size", "FSObjType"
        $files = $items | Where-Object { $_["FSObjType"] -eq 0 }
        $folders = $items | Where-Object { $_["FSObjType"] -eq 1 }

        $stats = @{
            FileCount   = ($files | Measure-Object).Count
            FolderCount = ($folders | Measure-Object).Count
            TotalSize   = ($files | ForEach-Object { [long]$_["File_x0020_Size"] } | Measure-Object -Sum).Sum
            LargestFile = ($files | ForEach-Object { [long]$_["File_x0020_Size"] } | Measure-Object -Maximum).Maximum
        }

        return $stats
    }
    catch {
        Write-Log "Error getting stats for $LibraryName : $_" -Level "WARNING"
        return @{
            FileCount   = 0
            FolderCount = 0
            TotalSize   = 0
            LargestFile = 0
        }
    }
}

function Insert-ControlTableRecord {
    param(
        [string]$ConnectionString,
        [hashtable]$Record
    )

    $query = @"
    IF NOT EXISTS (
        SELECT 1 FROM dbo.MigrationControl
        WHERE SiteUrl = @SiteUrl AND LibraryName = @LibraryName
    )
    BEGIN
        INSERT INTO dbo.MigrationControl (
            SiteUrl, LibraryName, SiteTitle, LibraryTitle,
            Status, FileCount, FolderCount, TotalSizeBytes, LargestFileSizeBytes,
            Priority, CreatedDate, CreatedBy
        ) VALUES (
            @SiteUrl, @LibraryName, @SiteTitle, @LibraryTitle,
            'Pending', @FileCount, @FolderCount, @TotalSizeBytes, @LargestFileSizeBytes,
            @Priority, GETUTCDATE(), @CreatedBy
        )
    END
    ELSE
    BEGIN
        UPDATE dbo.MigrationControl
        SET FileCount = @FileCount,
            FolderCount = @FolderCount,
            TotalSizeBytes = @TotalSizeBytes,
            LargestFileSizeBytes = @LargestFileSizeBytes,
            ModifiedDate = GETUTCDATE(),
            ModifiedBy = @CreatedBy
        WHERE SiteUrl = @SiteUrl AND LibraryName = @LibraryName
    END
"@

    $params = @{
        SiteUrl             = $Record.SiteUrl
        LibraryName         = $Record.LibraryName
        SiteTitle           = $Record.SiteTitle
        LibraryTitle        = $Record.LibraryTitle
        FileCount           = $Record.FileCount
        FolderCount         = $Record.FolderCount
        TotalSizeBytes      = $Record.TotalSizeBytes
        LargestFileSizeBytes = $Record.LargestFileSizeBytes
        Priority            = $Record.Priority
        CreatedBy           = $env:USERNAME
    }

    Invoke-Sqlcmd -ConnectionString $ConnectionString -Query $query -Variable @(
        "SiteUrl=$($params.SiteUrl)",
        "LibraryName=$($params.LibraryName)",
        "SiteTitle=$($params.SiteTitle)",
        "LibraryTitle=$($params.LibraryTitle)",
        "FileCount=$($params.FileCount)",
        "FolderCount=$($params.FolderCount)",
        "TotalSizeBytes=$($params.TotalSizeBytes)",
        "LargestFileSizeBytes=$($params.LargestFileSizeBytes)",
        "Priority=$($params.Priority)",
        "CreatedBy=$($params.CreatedBy)"
    )
}
#endregion

#region Main Script
Write-Log "========================================" -Level "INFO"
Write-Log "SharePoint Site Enumeration and Control Table Population" -Level "INFO"
Write-Log "SharePoint Tenant: $SharePointTenantUrl" -Level "INFO"
Write-Log "SQL Server: $SqlServerName" -Level "INFO"
Write-Log "========================================" -Level "INFO"

# Check for required modules
$requiredModules = @("PnP.PowerShell", "SqlServer")
foreach ($module in $requiredModules) {
    if (-not (Get-Module -ListAvailable -Name $module)) {
        Write-Log "Installing module: $module" -Level "WARNING"
        Install-Module -Name $module -Force -AllowClobber -Scope CurrentUser
    }
    Import-Module $module
}

# Build SQL connection string (using Azure AD authentication)
$sqlConnectionString = "Server=tcp:$SqlServerName.database.windows.net,1433;Initial Catalog=$SqlDatabaseName;Authentication=Active Directory Integrated;Encrypt=True;TrustServerCertificate=False;Connection Timeout=30;"

try {
    # Connect to SharePoint Admin Center
    $adminUrl = $SharePointTenantUrl -replace ".sharepoint.com", "-admin.sharepoint.com"
    Write-Log "Connecting to SharePoint Admin Center: $adminUrl" -Level "INFO"

    if ($UseInteractiveAuth) {
        Connect-PnPOnline -Url $adminUrl -Interactive
    }
    elseif ($ClientId -and $CertificateThumbprint) {
        $tenantId = (Invoke-RestMethod "https://login.microsoftonline.com/$($SharePointTenantUrl.Split('/')[2].Split('.')[0]).onmicrosoft.com/.well-known/openid_configuration").token_endpoint.Split('/')[3]
        Connect-PnPOnline -Url $adminUrl -ClientId $ClientId -Thumbprint $CertificateThumbprint -Tenant $tenantId
    }
    else {
        Connect-PnPOnline -Url $adminUrl -Interactive
    }

    Write-Log "Connected to SharePoint Admin Center" -Level "SUCCESS"

    # Get all site collections
    Write-Log "Enumerating site collections..." -Level "INFO"

    if ($SpecificSites.Count -gt 0) {
        $sites = $SpecificSites | ForEach-Object {
            Get-PnPTenantSite -Url "$SharePointTenantUrl$_"
        }
    }
    else {
        $sites = Get-PnPTenantSite -Filter "Url -like '$SiteFilter'" | Where-Object {
            $_.Template -notlike "SRCHCEN*" -and
            $_.Template -notlike "SPSMSITEHOST*" -and
            $_.Template -notlike "APPCATALOG*" -and
            $_.Template -notlike "POINTPUBLISHINGHUB*" -and
            $_.Template -notlike "EDISC*" -and
            $_.Url -notlike "*-my.sharepoint.com*"
        }
    }

    # Apply exclusions
    if ($ExcludeSites.Count -gt 0) {
        $sites = $sites | Where-Object {
            $siteUrl = $_.Url
            -not ($ExcludeSites | Where-Object { $siteUrl -like "*$_*" })
        }
    }

    $siteCount = ($sites | Measure-Object).Count
    Write-Log "Found $siteCount site collections to process" -Level "INFO"

    $totalLibraries = 0
    $totalFiles = 0
    $totalSizeGB = 0

    # Process each site
    $siteIndex = 0
    foreach ($site in $sites) {
        $siteIndex++
        $siteUrl = $site.Url
        $siteRelativeUrl = $siteUrl.Replace($SharePointTenantUrl, "")

        Write-Log "[$siteIndex/$siteCount] Processing site: $siteRelativeUrl" -Level "INFO"

        try {
            # Connect to the site
            Disconnect-PnPOnline -ErrorAction SilentlyContinue
            Connect-PnPOnline -Url $siteUrl -Interactive

            # Get all document libraries
            $libraries = Get-PnPList | Where-Object {
                $_.BaseTemplate -eq 101 -and  # Document Library
                $_.Hidden -eq $false -and
                $_.Title -notin $excludeLibraries -and
                $_.Title -notlike "Preservation*"
            }

            foreach ($library in $libraries) {
                Write-Log "  Processing library: $($library.Title)" -Level "INFO"

                # Get library statistics
                $stats = Get-LibraryStats -SiteUrl $siteUrl -LibraryName $library.Title

                if ($stats.FileCount -gt 0) {
                    # Calculate priority based on size (smaller = higher priority for faster initial results)
                    $priority = switch ($stats.TotalSize) {
                        { $_ -lt 104857600 } { 10 }      # < 100 MB
                        { $_ -lt 1073741824 } { 50 }    # < 1 GB
                        { $_ -lt 10737418240 } { 100 }  # < 10 GB
                        default { 200 }                  # > 10 GB
                    }

                    # Create record
                    $record = @{
                        SiteUrl              = $siteRelativeUrl
                        LibraryName          = $library.Title
                        SiteTitle            = $site.Title
                        LibraryTitle         = $library.Title
                        FileCount            = $stats.FileCount
                        FolderCount          = $stats.FolderCount
                        TotalSizeBytes       = if ($stats.TotalSize) { $stats.TotalSize } else { 0 }
                        LargestFileSizeBytes = if ($stats.LargestFile) { $stats.LargestFile } else { 0 }
                        Priority             = $priority
                    }

                    # Insert into SQL
                    try {
                        Insert-ControlTableRecord -ConnectionString $sqlConnectionString -Record $record
                        $totalLibraries++
                        $totalFiles += $stats.FileCount
                        $totalSizeGB += ($stats.TotalSize / 1GB)

                        Write-Log "    Files: $($stats.FileCount), Size: $([math]::Round($stats.TotalSize / 1GB, 2)) GB" -Level "SUCCESS"
                    }
                    catch {
                        Write-Log "    Error inserting record: $_" -Level "ERROR"
                    }
                }
                else {
                    Write-Log "    Empty library, skipping" -Level "INFO"
                }
            }
        }
        catch {
            Write-Log "Error processing site $siteUrl : $_" -Level "ERROR"
            continue
        }
    }

    # Summary
    Write-Log "========================================" -Level "INFO"
    Write-Log "ENUMERATION SUMMARY" -Level "SUCCESS"
    Write-Log "========================================" -Level "INFO"
    Write-Log "Sites Processed:     $siteCount" -Level "INFO"
    Write-Log "Libraries Added:     $totalLibraries" -Level "INFO"
    Write-Log "Total Files:         $totalFiles" -Level "INFO"
    Write-Log "Total Size:          $([math]::Round($totalSizeGB, 2)) GB ($([math]::Round($totalSizeGB / 1024, 2)) TB)" -Level "INFO"
    Write-Log "========================================" -Level "INFO"

    Write-Log "Control table population completed!" -Level "SUCCESS"
}
catch {
    Write-Log "Error: $_" -Level "ERROR"
    Write-Log $_.Exception.Message -Level "ERROR"
    exit 1
}
finally {
    Disconnect-PnPOnline -ErrorAction SilentlyContinue
}
#endregion
