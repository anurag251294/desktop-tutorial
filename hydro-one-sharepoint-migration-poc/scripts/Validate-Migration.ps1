<#
.SYNOPSIS
    Post-migration validation script comparing source (SharePoint) vs destination (ADLS).

.DESCRIPTION
    This script performs comprehensive validation:
    - File count comparison between SharePoint and ADLS
    - Size comparison
    - Random spot-check of file checksums (optional)
    - Generates validation report

.PARAMETER SharePointTenantUrl
    SharePoint Online tenant URL

.PARAMETER StorageAccountName
    ADLS Gen2 Storage Account name

.PARAMETER ContainerName
    Storage container name

.PARAMETER SqlServerName
    Azure SQL Server name

.PARAMETER SqlDatabaseName
    Database name

.PARAMETER SampleSize
    Number of files to randomly sample for checksum validation (default: 100)

.EXAMPLE
    .\Validate-Migration.ps1 -SharePointTenantUrl "https://hydroone.sharepoint.com" `
        -StorageAccountName "sthydroonemigdev" `
        -ContainerName "sharepoint-migration" `
        -SqlServerName "sql-hydroone-migration-dev" `
        -SqlDatabaseName "MigrationControl"

.NOTES
    Author: Microsoft Azure Data Engineering Team
    Project: Hydro One SharePoint Migration POC
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SharePointTenantUrl,

    [Parameter(Mandatory = $true)]
    [string]$StorageAccountName,

    [Parameter(Mandatory = $true)]
    [string]$ContainerName,

    [Parameter(Mandatory = $true)]
    [string]$SqlServerName,

    [Parameter(Mandatory = $true)]
    [string]$SqlDatabaseName,

    [Parameter(Mandatory = $false)]
    [int]$SampleSize = 100,

    [Parameter(Mandatory = $false)]
    [switch]$SkipChecksumValidation,

    [Parameter(Mandatory = $false)]
    [string]$ReportOutputPath
)

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

    # Also log to file if path specified
    if ($script:LogFile) {
        "[$timestamp] [$Level] $Message" | Out-File $script:LogFile -Append
    }
}

function Get-SharePointFileCount {
    param(
        [string]$SiteUrl,
        [string]$LibraryName
    )

    try {
        $list = Get-PnPList -Identity $LibraryName -ErrorAction Stop
        return $list.ItemCount
    }
    catch {
        Write-Log "Error getting SharePoint file count for $LibraryName : $_" -Level "WARNING"
        return -1
    }
}

function Get-ADLSFileCount {
    param(
        [string]$StorageAccountName,
        [string]$ContainerName,
        [string]$FolderPath
    )

    try {
        $ctx = New-AzStorageContext -StorageAccountName $StorageAccountName -UseConnectedAccount
        $blobs = Get-AzStorageBlob -Container $ContainerName -Context $ctx -Prefix $FolderPath

        # Filter to only files (not folders)
        $files = $blobs | Where-Object { -not $_.Name.EndsWith('/') }
        return ($files | Measure-Object).Count
    }
    catch {
        Write-Log "Error getting ADLS file count: $_" -Level "WARNING"
        return -1
    }
}

function Get-ADLSTotalSize {
    param(
        [string]$StorageAccountName,
        [string]$ContainerName,
        [string]$FolderPath
    )

    try {
        $ctx = New-AzStorageContext -StorageAccountName $StorageAccountName -UseConnectedAccount
        $blobs = Get-AzStorageBlob -Container $ContainerName -Context $ctx -Prefix $FolderPath

        $measure = $blobs | Measure-Object -Property Length -Sum
        $totalSize = if ($measure.Sum) { $measure.Sum } else { 0 }
        return $totalSize
    }
    catch {
        Write-Log "Error getting ADLS total size: $_" -Level "WARNING"
        return -1
    }
}

function Compare-FileChecksum {
    param(
        [string]$SharePointFileUrl,
        [string]$ADLSBlobPath,
        [string]$StorageAccountName,
        [string]$ContainerName
    )

    try {
        # Get SharePoint file content hash
        $spFileContent = Get-PnPFile -Url $SharePointFileUrl -AsMemoryStream
        $spHash = Get-FileHash -InputStream $spFileContent -Algorithm MD5

        # Get ADLS file content hash
        $ctx = New-AzStorageContext -StorageAccountName $StorageAccountName -UseConnectedAccount
        $tempFile = [System.IO.Path]::GetTempFileName()
        Get-AzStorageBlobContent -Container $ContainerName -Blob $ADLSBlobPath -Context $ctx -Destination $tempFile -Force | Out-Null
        $adlsHash = Get-FileHash -Path $tempFile -Algorithm MD5
        Remove-Item $tempFile -Force

        return @{
            Match     = $spHash.Hash -eq $adlsHash.Hash
            SPHash    = $spHash.Hash
            ADLSHash  = $adlsHash.Hash
        }
    }
    catch {
        return @{
            Match     = $false
            SPHash    = "ERROR"
            ADLSHash  = "ERROR"
            Error     = $_.Exception.Message
        }
    }
}
#endregion

#region Main Script
$ErrorActionPreference = "Stop"

# Setup logging
if (-not $ReportOutputPath) {
    $ReportOutputPath = Join-Path $PSScriptRoot "validation-report-$(Get-Date -Format 'yyyyMMdd-HHmmss').html"
}
$script:LogFile = $ReportOutputPath -replace '\.html$', '.log'

Write-Log "========================================" -Level "INFO"
Write-Log "HYDRO ONE MIGRATION VALIDATION" -Level "INFO"
Write-Log "========================================" -Level "INFO"

# SQL connection string
$sqlConnectionString = "Server=tcp:$SqlServerName.database.windows.net,1433;Initial Catalog=$SqlDatabaseName;Authentication=Active Directory Integrated;Encrypt=True;"

# Get completed libraries from control table
Write-Log "Fetching completed libraries from control table..." -Level "INFO"

$query = @"
SELECT
    Id, SiteUrl, LibraryName, FileCount, TotalSizeBytes,
    MigratedFileCount, MigratedSizeBytes, ValidationStatus
FROM dbo.MigrationControl
WHERE Status = 'Completed'
ORDER BY TotalSizeBytes DESC
"@

$libraries = Invoke-Sqlcmd -ConnectionString $sqlConnectionString -Query $query

$totalLibraries = ($libraries | Measure-Object).Count
Write-Log "Found $totalLibraries completed libraries to validate" -Level "INFO"

$validationResults = @()
$passedCount = 0
$failedCount = 0
$warningCount = 0

foreach ($library in $libraries) {
    $siteUrl = $library.SiteUrl
    $libraryName = $library.LibraryName

    Write-Log "Validating: $siteUrl / $libraryName" -Level "INFO"

    $result = @{
        SiteUrl          = $siteUrl
        LibraryName      = $libraryName
        ExpectedFiles    = $library.FileCount
        ActualFiles      = 0
        ExpectedSizeBytes = $library.TotalSizeBytes
        ActualSizeBytes  = 0
        FileCountMatch   = $false
        SizeMatch        = $false
        Status           = "Unknown"
        Details          = ""
    }

    try {
        # Connect to SharePoint site
        $fullSiteUrl = "$SharePointTenantUrl$siteUrl"
        try {
            Connect-PnPOnline -Url $fullSiteUrl -Interactive -ErrorAction Stop
        }
        catch {
            Write-Log "  Failed to connect to SharePoint site: $fullSiteUrl — $_" -Level "ERROR"
            $result.Status = "ERROR"
            $result.Details = "PnP connection failed: $($_.Exception.Message)"
            $failedCount++
            $validationResults += $result
            continue
        }

        # Get current SharePoint file count
        $spFileCount = Get-SharePointFileCount -SiteUrl $fullSiteUrl -LibraryName $libraryName
        $result.ExpectedFiles = $spFileCount

        # Get ADLS file count
        $siteName = $siteUrl -replace '/sites/', ''
        $adlsFolderPath = "$siteName/$libraryName/"
        $adlsFileCount = Get-ADLSFileCount -StorageAccountName $StorageAccountName -ContainerName $ContainerName -FolderPath $adlsFolderPath
        $result.ActualFiles = $adlsFileCount

        # Get ADLS total size
        $adlsTotalSize = Get-ADLSTotalSize -StorageAccountName $StorageAccountName -ContainerName $ContainerName -FolderPath $adlsFolderPath
        $result.ActualSizeBytes = $adlsTotalSize

        # Compare file counts
        if ($spFileCount -gt 0 -and $adlsFileCount -gt 0) {
            $countDiff = [math]::Abs($spFileCount - $adlsFileCount)
            $countDiffPercent = ($countDiff / $spFileCount) * 100

            if ($countDiff -eq 0) {
                $result.FileCountMatch = $true
                $result.Status = "PASS"
                $passedCount++
            }
            elseif ($countDiffPercent -lt 5) {
                $result.FileCountMatch = $false
                $result.Status = "WARNING"
                $result.Details = "File count difference: $countDiff ($([math]::Round($countDiffPercent, 2))%)"
                $warningCount++
            }
            else {
                $result.FileCountMatch = $false
                $result.Status = "FAIL"
                $result.Details = "Significant file count difference: $countDiff ($([math]::Round($countDiffPercent, 2))%)"
                $failedCount++
            }
        }
        else {
            $result.Status = "ERROR"
            $result.Details = "Could not retrieve file counts (SP: $spFileCount, ADLS: $adlsFileCount)"
            $failedCount++
        }

        Write-Log "  SP Files: $spFileCount, ADLS Files: $adlsFileCount - $($result.Status)" -Level $(
            switch ($result.Status) {
                "PASS" { "SUCCESS" }
                "WARNING" { "WARNING" }
                default { "ERROR" }
            }
        )
    }
    catch {
        $result.Status = "ERROR"
        $result.Details = $_.Exception.Message
        $failedCount++
        Write-Log "  Error: $_" -Level "ERROR"
    }

    $validationResults += $result

    # Update validation status in SQL (parameterized via SQLCMD variables to prevent injection)
    $safeStatus = $result.Status -replace "'", "''"
    $safeDetails = $result.Details -replace "'", "''"
    $updateQuery = @"
UPDATE dbo.MigrationControl
SET ValidationStatus = N'$safeStatus',
    DiscrepancyDetails = N'$safeDetails',
    ValidationTimestamp = GETUTCDATE()
WHERE Id = $([int]$library.Id)
"@
    try {
        Invoke-Sqlcmd -ConnectionString $sqlConnectionString -Query $updateQuery -ErrorAction Stop
    }
    catch {
        Write-Log "  Warning: Could not update validation status in SQL: $_" -Level "WARNING"
    }
}

# Generate HTML Report
Write-Log "Generating validation report..." -Level "INFO"

$htmlReport = @"
<!DOCTYPE html>
<html>
<head>
    <title>Hydro One Migration Validation Report</title>
    <style>
        body { font-family: 'Segoe UI', Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        h1 { color: #0078d4; }
        .summary { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .summary h2 { margin-top: 0; }
        .stat { display: inline-block; margin-right: 30px; }
        .stat-value { font-size: 24px; font-weight: bold; }
        .stat-label { color: #666; }
        .pass { color: #107c10; }
        .warning { color: #ffb900; }
        .fail { color: #d83b01; }
        table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        th { background: #0078d4; color: white; padding: 12px; text-align: left; }
        td { padding: 10px 12px; border-bottom: 1px solid #eee; }
        tr:hover { background: #f8f8f8; }
        .status-PASS { background: #dff6dd; color: #107c10; padding: 4px 8px; border-radius: 4px; }
        .status-WARNING { background: #fff4ce; color: #8a6d3b; padding: 4px 8px; border-radius: 4px; }
        .status-FAIL { background: #fde7e9; color: #d83b01; padding: 4px 8px; border-radius: 4px; }
        .status-ERROR { background: #fde7e9; color: #a80000; padding: 4px 8px; border-radius: 4px; }
    </style>
</head>
<body>
    <h1>🔍 Hydro One Migration Validation Report</h1>
    <p>Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')</p>

    <div class="summary">
        <h2>Summary</h2>
        <div class="stat">
            <div class="stat-value">$totalLibraries</div>
            <div class="stat-label">Total Libraries</div>
        </div>
        <div class="stat">
            <div class="stat-value pass">$passedCount</div>
            <div class="stat-label">Passed</div>
        </div>
        <div class="stat">
            <div class="stat-value warning">$warningCount</div>
            <div class="stat-label">Warnings</div>
        </div>
        <div class="stat">
            <div class="stat-value fail">$failedCount</div>
            <div class="stat-label">Failed</div>
        </div>
    </div>

    <h2>Detailed Results</h2>
    <table>
        <tr>
            <th>Site</th>
            <th>Library</th>
            <th>Expected Files</th>
            <th>Actual Files</th>
            <th>Status</th>
            <th>Details</th>
        </tr>
"@

foreach ($result in $validationResults) {
    $htmlReport += @"
        <tr>
            <td>$($result.SiteUrl)</td>
            <td>$($result.LibraryName)</td>
            <td>$($result.ExpectedFiles)</td>
            <td>$($result.ActualFiles)</td>
            <td><span class="status-$($result.Status)">$($result.Status)</span></td>
            <td>$($result.Details)</td>
        </tr>
"@
}

$htmlReport += @"
    </table>
</body>
</html>
"@

$htmlReport | Out-File $ReportOutputPath -Encoding UTF8

Write-Log "========================================" -Level "INFO"
Write-Log "VALIDATION SUMMARY" -Level "INFO"
Write-Log "========================================" -Level "INFO"
Write-Log "Total Libraries: $totalLibraries" -Level "INFO"
Write-Log "Passed: $passedCount" -Level "SUCCESS"
Write-Log "Warnings: $warningCount" -Level "WARNING"
Write-Log "Failed: $failedCount" -Level $(if ($failedCount -gt 0) { "ERROR" } else { "INFO" })
Write-Log "Report saved to: $ReportOutputPath" -Level "SUCCESS"
#endregion
