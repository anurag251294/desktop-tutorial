<#
.SYNOPSIS
    Monitors Azure Data Factory pipeline runs and reports migration progress.

.DESCRIPTION
    This script:
    - Queries ADF pipeline run status
    - Reports overall migration progress from control table
    - Identifies failed runs and files
    - Sends alerts on failures (optional)
    - Generates progress report

.PARAMETER ResourceGroupName
    Azure Resource Group containing ADF

.PARAMETER DataFactoryName
    Name of the Azure Data Factory

.PARAMETER SqlServerName
    Azure SQL Server name

.PARAMETER SqlDatabaseName
    Database name

.PARAMETER HoursBack
    How many hours back to check for pipeline runs (default: 24)

.EXAMPLE
    .\Monitor-Migration.ps1 -ResourceGroupName "rg-hydroone-migration-dev" `
        -DataFactoryName "adf-hydroone-migration-dev" `
        -SqlServerName "sql-hydroone-migration-dev" `
        -SqlDatabaseName "MigrationControl"

.NOTES
    Author: PwC Azure Data Engineering Team
    Project: Hydro One SharePoint Migration POC
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroupName,

    [Parameter(Mandatory = $true)]
    [string]$DataFactoryName,

    [Parameter(Mandatory = $true)]
    [string]$SqlServerName,

    [Parameter(Mandatory = $true)]
    [string]$SqlDatabaseName,

    [Parameter(Mandatory = $false)]
    [int]$HoursBack = 24,

    [Parameter(Mandatory = $false)]
    [string]$AlertEmailTo,

    [Parameter(Mandatory = $false)]
    [switch]$ContinuousMonitor,

    [Parameter(Mandatory = $false)]
    [int]$RefreshIntervalSeconds = 60
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
        "HEADER"  { "Cyan" }
        default   { "White" }
    }
    Write-Host "[$timestamp] [$Level] $Message" -ForegroundColor $color
}

function Get-ProgressBar {
    param([int]$Percent, [int]$Width = 40)
    $filled = [math]::Round($Width * $Percent / 100)
    $empty = $Width - $filled
    return "[" + ("=" * $filled) + ("." * $empty) + "] $Percent%"
}

function Get-PipelineRunSummary {
    param(
        [string]$ResourceGroupName,
        [string]$DataFactoryName,
        [datetime]$StartTime
    )

    $runs = Get-AzDataFactoryV2PipelineRun `
        -ResourceGroupName $ResourceGroupName `
        -DataFactoryName $DataFactoryName `
        -LastUpdatedAfter $StartTime `
        -LastUpdatedBefore (Get-Date)

    $summary = @{
        Total       = ($runs | Measure-Object).Count
        Succeeded   = ($runs | Where-Object { $_.Status -eq "Succeeded" } | Measure-Object).Count
        Failed      = ($runs | Where-Object { $_.Status -eq "Failed" } | Measure-Object).Count
        InProgress  = ($runs | Where-Object { $_.Status -eq "InProgress" } | Measure-Object).Count
        Queued      = ($runs | Where-Object { $_.Status -eq "Queued" } | Measure-Object).Count
        Cancelled   = ($runs | Where-Object { $_.Status -eq "Cancelled" } | Measure-Object).Count
        Runs        = $runs
    }

    return $summary
}

function Get-MigrationProgress {
    param([string]$ConnectionString)

    $query = @"
SELECT
    (SELECT COUNT(*) FROM dbo.MigrationControl) AS TotalLibraries,
    (SELECT COUNT(*) FROM dbo.MigrationControl WHERE Status = 'Completed') AS CompletedLibraries,
    (SELECT COUNT(*) FROM dbo.MigrationControl WHERE Status = 'InProgress') AS InProgressLibraries,
    (SELECT COUNT(*) FROM dbo.MigrationControl WHERE Status = 'Failed') AS FailedLibraries,
    (SELECT COUNT(*) FROM dbo.MigrationControl WHERE Status = 'Pending') AS PendingLibraries,
    (SELECT ISNULL(SUM(TotalSizeBytes), 0) FROM dbo.MigrationControl) AS TotalSizeBytes,
    (SELECT ISNULL(SUM(MigratedSizeBytes), 0) FROM dbo.MigrationControl WHERE Status = 'Completed') AS MigratedSizeBytes,
    (SELECT COUNT(*) FROM dbo.MigrationAuditLog WHERE MigrationStatus = 'Success') AS SuccessfulFiles,
    (SELECT COUNT(*) FROM dbo.MigrationAuditLog WHERE MigrationStatus = 'Failed') AS FailedFiles,
    (SELECT ISNULL(SUM(FileSizeBytes), 0) FROM dbo.MigrationAuditLog WHERE MigrationStatus = 'Success') AS MigratedFileSizeBytes
"@

    $result = Invoke-Sqlcmd -ConnectionString $ConnectionString -Query $query
    return $result
}

function Get-RecentFailures {
    param(
        [string]$ConnectionString,
        [int]$TopN = 10
    )

    $query = @"
SELECT TOP $TopN
    mc.SiteUrl,
    mc.LibraryName,
    mc.ErrorMessage,
    mc.RetryCount,
    mc.EndTime
FROM dbo.MigrationControl mc
WHERE mc.Status = 'Failed'
ORDER BY mc.EndTime DESC
"@

    $result = Invoke-Sqlcmd -ConnectionString $ConnectionString -Query $query
    return $result
}

function Show-Dashboard {
    param($Progress, $PipelineRuns, $Failures)

    Clear-Host

    Write-Host ""
    Write-Host "╔══════════════════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║              HYDRO ONE SHAREPOINT MIGRATION - LIVE DASHBOARD                ║" -ForegroundColor Cyan
    Write-Host "║                         $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')                           ║" -ForegroundColor Cyan
    Write-Host "╚══════════════════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""

    # Library Progress
    $totalLibraries = $Progress.TotalLibraries
    $completedLibraries = $Progress.CompletedLibraries
    $libraryPercent = if ($totalLibraries -gt 0) { [math]::Round(($completedLibraries / $totalLibraries) * 100, 1) } else { 0 }

    Write-Host "📚 LIBRARY MIGRATION PROGRESS" -ForegroundColor Yellow
    Write-Host "   $(Get-ProgressBar -Percent $libraryPercent -Width 50)"
    Write-Host "   Completed: $completedLibraries / $totalLibraries | In Progress: $($Progress.InProgressLibraries) | Failed: $($Progress.FailedLibraries) | Pending: $($Progress.PendingLibraries)"
    Write-Host ""

    # Size Progress
    $totalSizeTB = [math]::Round($Progress.TotalSizeBytes / 1TB, 2)
    $migratedSizeTB = [math]::Round($Progress.MigratedFileSizeBytes / 1TB, 2)
    $sizePercent = if ($Progress.TotalSizeBytes -gt 0) { [math]::Round(($Progress.MigratedFileSizeBytes / $Progress.TotalSizeBytes) * 100, 1) } else { 0 }

    Write-Host "💾 DATA MIGRATION PROGRESS" -ForegroundColor Yellow
    Write-Host "   $(Get-ProgressBar -Percent $sizePercent -Width 50)"
    Write-Host "   Migrated: $migratedSizeTB TB / $totalSizeTB TB"
    Write-Host ""

    # File Statistics
    Write-Host "📄 FILE STATISTICS" -ForegroundColor Yellow
    Write-Host "   ✅ Successful: $($Progress.SuccessfulFiles)"
    Write-Host "   ❌ Failed: $($Progress.FailedFiles)"
    $fileSuccessRate = if (($Progress.SuccessfulFiles + $Progress.FailedFiles) -gt 0) {
        [math]::Round(($Progress.SuccessfulFiles / ($Progress.SuccessfulFiles + $Progress.FailedFiles)) * 100, 2)
    } else { 0 }
    Write-Host "   📊 Success Rate: $fileSuccessRate%"
    Write-Host ""

    # Pipeline Runs
    Write-Host "🔄 PIPELINE RUNS (Last $HoursBack hours)" -ForegroundColor Yellow
    Write-Host "   Total: $($PipelineRuns.Total) | ✅ Succeeded: $($PipelineRuns.Succeeded) | ❌ Failed: $($PipelineRuns.Failed) | ⏳ In Progress: $($PipelineRuns.InProgress)"
    Write-Host ""

    # Recent Failures
    if ($Failures -and $Failures.Count -gt 0) {
        Write-Host "⚠️  RECENT FAILURES" -ForegroundColor Red
        foreach ($failure in $Failures | Select-Object -First 5) {
            Write-Host "   • $($failure.SiteUrl)/$($failure.LibraryName)" -ForegroundColor Red
            Write-Host "     Retries: $($failure.RetryCount) | Error: $($failure.ErrorMessage.Substring(0, [Math]::Min(50, $failure.ErrorMessage.Length)))..." -ForegroundColor DarkRed
        }
    }
    else {
        Write-Host "✅ NO RECENT FAILURES" -ForegroundColor Green
    }

    Write-Host ""
    Write-Host "─────────────────────────────────────────────────────────────────────────────────" -ForegroundColor DarkGray
    Write-Host "Press Ctrl+C to exit monitoring" -ForegroundColor DarkGray
}
#endregion

#region Main Script
Write-Log "Starting Migration Monitor..." -Level "HEADER"

# Build SQL connection string
$sqlConnectionString = "Server=tcp:$SqlServerName.database.windows.net,1433;Initial Catalog=$SqlDatabaseName;Authentication=Active Directory Integrated;Encrypt=True;"

$startTime = (Get-Date).AddHours(-$HoursBack)

try {
    do {
        # Get pipeline run summary
        $pipelineRuns = Get-PipelineRunSummary `
            -ResourceGroupName $ResourceGroupName `
            -DataFactoryName $DataFactoryName `
            -StartTime $startTime

        # Get migration progress from SQL
        $progress = Get-MigrationProgress -ConnectionString $sqlConnectionString

        # Get recent failures
        $failures = Get-RecentFailures -ConnectionString $sqlConnectionString -TopN 10

        if ($ContinuousMonitor) {
            Show-Dashboard -Progress $progress -PipelineRuns $pipelineRuns -Failures $failures
            Start-Sleep -Seconds $RefreshIntervalSeconds
        }
        else {
            # One-time report
            Write-Log "========================================" -Level "HEADER"
            Write-Log "MIGRATION PROGRESS REPORT" -Level "HEADER"
            Write-Log "========================================" -Level "HEADER"

            Write-Log "Library Progress:" -Level "INFO"
            Write-Log "  Total Libraries: $($progress.TotalLibraries)" -Level "INFO"
            Write-Log "  Completed: $($progress.CompletedLibraries)" -Level "SUCCESS"
            Write-Log "  In Progress: $($progress.InProgressLibraries)" -Level "INFO"
            Write-Log "  Failed: $($progress.FailedLibraries)" -Level $(if ($progress.FailedLibraries -gt 0) { "ERROR" } else { "INFO" })
            Write-Log "  Pending: $($progress.PendingLibraries)" -Level "INFO"

            Write-Log "" -Level "INFO"
            Write-Log "File Progress:" -Level "INFO"
            Write-Log "  Successful Files: $($progress.SuccessfulFiles)" -Level "SUCCESS"
            Write-Log "  Failed Files: $($progress.FailedFiles)" -Level $(if ($progress.FailedFiles -gt 0) { "ERROR" } else { "INFO" })
            Write-Log "  Migrated Size: $([math]::Round($progress.MigratedFileSizeBytes / 1GB, 2)) GB" -Level "INFO"

            Write-Log "" -Level "INFO"
            Write-Log "Pipeline Runs (Last $HoursBack hours):" -Level "INFO"
            Write-Log "  Total: $($pipelineRuns.Total)" -Level "INFO"
            Write-Log "  Succeeded: $($pipelineRuns.Succeeded)" -Level "SUCCESS"
            Write-Log "  Failed: $($pipelineRuns.Failed)" -Level $(if ($pipelineRuns.Failed -gt 0) { "ERROR" } else { "INFO" })
            Write-Log "  In Progress: $($pipelineRuns.InProgress)" -Level "INFO"

            if ($failures -and $failures.Count -gt 0) {
                Write-Log "" -Level "INFO"
                Write-Log "Recent Failures:" -Level "ERROR"
                foreach ($failure in $failures) {
                    Write-Log "  $($failure.SiteUrl)/$($failure.LibraryName) - Retries: $($failure.RetryCount)" -Level "ERROR"
                }
            }
        }
    } while ($ContinuousMonitor)
}
catch {
    Write-Log "Error: $_" -Level "ERROR"
    exit 1
}
#endregion
