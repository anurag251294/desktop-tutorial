<#
.SYNOPSIS
  Runs the geohazard bronze notebooks on demand in Fabric and polls each job to completion.

.DESCRIPTION
  Reads the workspace, lakehouse, and notebook IDs from cicd/fabric-setup.output.json
  (produced by setup_fabric_demo.ps1), then submits a "Run on demand Item Job" for each
  notebook with the default lakehouse bound so saveAsTable lands in bronze_lakehouse.
  Polls each job instance until Completed / Failed / Cancelled.

.PARAMETER Notebooks
  Optional subset of notebook display names to run. Defaults to all notebooks in the output file.

.PARAMETER TimeoutMinutes
  Max minutes to wait per notebook before giving up polling. Default 30.
#>
[CmdletBinding()]
param(
    [string[]] $Notebooks,
    [int] $TimeoutMinutes = 30
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$outputPath = Join-Path $root "cicd/fabric-setup.output.json"
if (-not (Test-Path $outputPath)) {
    throw "Cannot find $outputPath. Run scripts/fabric/setup_fabric_demo.ps1 first."
}

$state = Get-Content $outputPath -Raw | ConvertFrom-Json
$workspaceId = $state.workspace.workspaceId
$lakehouses = $state.workspace.lakehouses
$defaultLakehouse = $lakehouses | Select-Object -First 1
if (-not $defaultLakehouse) { throw "No lakehouse found in $outputPath." }

# name -> lakehouse object lookup so each notebook binds to its own medallion-layer lakehouse
$lakehouseByName = @{}
foreach ($lh in $lakehouses) { $lakehouseByName[[string]$lh.displayName] = $lh }

$allNotebooks = $state.workspace.notebooks
if ($Notebooks) {
    $allNotebooks = $allNotebooks | Where-Object { $Notebooks -contains $_.displayName }
}
if (-not $allNotebooks) { throw "No matching notebooks to run." }

Write-Host "Workspace : $($state.workspace.workspaceName) ($workspaceId)"
Write-Host "Lakehouses: $($lakehouses.displayName -join ', ')"
Write-Host "Notebooks : $($allNotebooks.displayName -join ', ')"
Write-Host ""

function Get-FabricToken {
    return (az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv)
}

$token = Get-FabricToken
$base = "https://api.fabric.microsoft.com/v1"

$jobs = @()
foreach ($nb in $allNotebooks) {
    # Resolve this notebook's lakehouse (recorded by setup) or fall back to the primary/bronze lakehouse
    $nbLakehouse = $defaultLakehouse
    if ($nb.PSObject.Properties.Name -contains "lakehouse" -and $nb.lakehouse -and $lakehouseByName.ContainsKey([string]$nb.lakehouse)) {
        $nbLakehouse = $lakehouseByName[[string]$nb.lakehouse]
    }

    $body = @{
        executionData = @{
            configuration = @{
                useStarterPool   = $true
                defaultLakehouse = @{
                    name        = $nbLakehouse.displayName
                    id          = $nbLakehouse.id
                    workspaceId = $workspaceId
                }
            }
        }
    } | ConvertTo-Json -Depth 6

    $uri = "$base/workspaces/$workspaceId/items/$($nb.id)/jobs/RunNotebook/instances"
    Write-Host "Submitting run: $($nb.displayName)  (lakehouse: $($nbLakehouse.displayName)) ..."
    $resp = Invoke-WebRequest -Method Post -Uri $uri -Headers @{ Authorization = "Bearer $token" } -ContentType "application/json" -Body $body
    $location = $resp.Headers["Location"]
    if ($location -is [array]) { $location = $location[0] }
    Write-Host "  Accepted ($($resp.StatusCode)). Job: $location"
    $jobs += [pscustomobject]@{ Name = $nb.displayName; Location = $location; Status = "NotStarted" }
}

Write-Host ""
Write-Host "Polling job status (timeout ${TimeoutMinutes}m per notebook)..."
$deadline = (Get-Date).AddMinutes($TimeoutMinutes)
$terminal = @("Completed", "Failed", "Cancelled", "Deduped")

do {
    Start-Sleep -Seconds 15
    $token = Get-FabricToken
    $pending = $false
    foreach ($job in $jobs) {
        if ($terminal -contains $job.Status) { continue }
        try {
            $info = Invoke-RestMethod -Method Get -Uri $job.Location -Headers @{ Authorization = "Bearer $token" }
            $job.Status = $info.status
            if ($job.Status -eq "Failed" -and $info.failureReason) {
                $job | Add-Member -NotePropertyName FailureReason -NotePropertyValue ($info.failureReason.message) -Force
            }
            if ($info.PSObject.Properties.Name -contains "exitValue" -and $info.exitValue) {
                $job | Add-Member -NotePropertyName ExitValue -NotePropertyValue $info.exitValue -Force
            }
        } catch {
            $job.Status = "PollError: $($_.Exception.Message)"
        }
        Write-Host ("  {0,-34} {1}" -f $job.Name, $job.Status)
        if ($terminal -notcontains $job.Status) { $pending = $true }
    }
    Write-Host "  ---"
} while ($pending -and (Get-Date) -lt $deadline)

Write-Host ""
Write-Host "Final status:"
$jobs | ForEach-Object {
    $line = "  {0,-34} {1}" -f $_.Name, $_.Status
    if ($_.ExitValue) { $line += "  exit=$($_.ExitValue)" }
    if ($_.FailureReason) { $line += "  reason=$($_.FailureReason)" }
    Write-Host $line
}

if ($jobs | Where-Object { $_.Status -ne "Completed" }) { exit 1 }
