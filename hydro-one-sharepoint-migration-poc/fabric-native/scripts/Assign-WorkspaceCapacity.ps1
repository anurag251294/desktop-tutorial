<#
.SYNOPSIS
    Assigns, switches, or unassigns a Fabric capacity for a Fabric workspace (az CLI driven).

.DESCRIPTION
    Resolves the workspace and capacity (by display name or GUID) and then either:
      * assigns the capacity to the workspace (default),
      * switches the workspace to a different capacity (just pass a different -Capacity), or
      * unassigns the workspace from any capacity (-Unassign).
    Waits for the long-running operation to finish and verifies the result.
    Runs on Windows PowerShell 5.1 or PowerShell 7+.

    Requirements:
      * Azure CLI signed in (`az login`) as a user who is BOTH:
          - an Admin/Member on the target workspace, and
          - a Capacity admin / contributor on the capacity (the person who created
            the capacity has this).
      * For assign/switch, the capacity must be Active (running).

.PARAMETER Workspace
    Workspace display name OR GUID.

.PARAMETER Capacity
    Capacity display name OR GUID. Required unless -Unassign is used.
    To SWITCH capacity, just run again with a different -Capacity.

.PARAMETER Unassign
    Remove the workspace from its current capacity (no -Capacity needed).

.EXAMPLE
    # Assign (or switch to) a capacity
    .\Assign-WorkspaceCapacity.ps1 -Workspace "Hydro_One_Migration" -Capacity "<capacity-name-or-guid>"

.EXAMPLE
    # Unassign from its current capacity
    .\Assign-WorkspaceCapacity.ps1 -Workspace "Hydro_One_Migration" -Unassign
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Workspace,
    [string]$Capacity,
    [switch]$Unassign
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # avoids Invoke-WebRequest hangs on some bodies
$api = "https://api.fabric.microsoft.com/v1"

if (-not $Unassign -and [string]::IsNullOrWhiteSpace($Capacity)) {
    throw "Provide -Capacity to assign/switch, or use -Unassign to remove the workspace from its capacity."
}

function Get-Token {
    $t = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($t)) { throw "Could not get a Fabric token. Run 'az login' first." }
    return $t
}
function Headers { @{ Authorization = "Bearer $(Get-Token)"; "Content-Type" = "application/json" } }
function Is-Guid([string]$s) { [guid]::TryParse($s, [ref]([guid]::Empty)) }

function Wait-Operation($response) {
    if ([int]$response.StatusCode -ne 202) { return }
    $op = @($response.Headers["Operation-Location"])[0]; if (-not $op) { $op = @($response.Headers["Location"])[0] }
    if (-not $op) { return }
    do {
        Start-Sleep -Seconds 5
        $status = (Invoke-RestMethod -Uri $op -Headers (Headers)).status
        Write-Host "  operation: $status"
    } while ($status -notin @("Succeeded", "Completed", "Failed"))
    if ($status -eq "Failed") { throw "Operation failed. Check that you are a capacity admin and have workspace admin rights." }
}

# --- Resolve the workspace ---
if (Is-Guid $Workspace) {
    $wsId = $Workspace
}
else {
    $all = (Invoke-RestMethod -Uri "$api/workspaces" -Headers (Headers)).value
    $match = @($all | Where-Object { $_.displayName -eq $Workspace })
    if ($match.Count -eq 0) { throw "Workspace '$Workspace' not found (or you lack access)." }
    if ($match.Count -gt 1) { throw "Multiple workspaces named '$Workspace' -- pass the GUID instead." }
    $wsId = $match[0].id
}
Write-Host "Workspace: $Workspace -> $wsId" -ForegroundColor Cyan

# --- Unassign mode ---
if ($Unassign) {
    Write-Host "Unassigning workspace from its capacity..."
    $resp = Invoke-WebRequest -Method POST -Uri "$api/workspaces/$wsId/unassignFromCapacity" -Headers (Headers) -UseBasicParsing
    Wait-Operation $resp
    Start-Sleep -Seconds 3
    $ws = Invoke-RestMethod -Uri "$api/workspaces/$wsId" -Headers (Headers)
    if ([string]::IsNullOrWhiteSpace($ws.capacityId)) {
        Write-Host "SUCCESS: '$($ws.displayName)' is no longer assigned to a capacity." -ForegroundColor Green
    }
    else {
        Write-Host "Submitted, but the workspace still reports capacityId '$($ws.capacityId)'. Re-check in a minute." -ForegroundColor Yellow
    }
    return
}

# --- Resolve the capacity (assign / switch) ---
$caps = (Invoke-RestMethod -Uri "$api/capacities" -Headers (Headers)).value
if (Is-Guid $Capacity) {
    $cap = $caps | Where-Object { $_.id -eq $Capacity } | Select-Object -First 1
    if (-not $cap) { throw "Capacity GUID '$Capacity' is not visible to you. Are you a capacity admin and is it Active?" }
}
else {
    $m = @($caps | Where-Object { $_.displayName -eq $Capacity })
    if ($m.Count -eq 0) { throw "Capacity '$Capacity' not found. Visible capacities: " + (($caps | ForEach-Object { $_.displayName }) -join ", ") }
    if ($m.Count -gt 1) { throw "Multiple capacities named '$Capacity' -- pass the GUID instead." }
    $cap = $m[0]
}
Write-Host "Capacity:  $($cap.displayName) -> $($cap.id) (sku $($cap.sku), state $($cap.state))" -ForegroundColor Cyan
if ($cap.state -ne "Active") { Write-Host "WARNING: capacity state is '$($cap.state)', not 'Active'. Resume it first." -ForegroundColor Yellow }

Write-Host "Assigning capacity to workspace..."
$resp = Invoke-WebRequest -Method POST -Uri "$api/workspaces/$wsId/assignToCapacity" `
    -Headers (Headers) -Body (@{ capacityId = $cap.id } | ConvertTo-Json) -UseBasicParsing
Wait-Operation $resp

Start-Sleep -Seconds 3
$ws = Invoke-RestMethod -Uri "$api/workspaces/$wsId" -Headers (Headers)
if ($ws.capacityId -eq $cap.id) {
    Write-Host "SUCCESS: '$($ws.displayName)' is now on capacity '$($cap.displayName)' ($($cap.id))." -ForegroundColor Green
}
else {
    Write-Host "Assignment submitted, but the workspace still reports capacityId '$($ws.capacityId)'. Re-check in a minute." -ForegroundColor Yellow
}
