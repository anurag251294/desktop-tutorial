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

.PARAMETER TimeoutSeconds
    How long to wait for the assign/unassign operation before giving up. Default 600.

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
    [switch]$Unassign,
    [int]$TimeoutSeconds = 600
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # avoids Invoke-WebRequest hangs on some bodies
$api = "https://api.fabric.microsoft.com/v1"

if (-not $Unassign -and [string]::IsNullOrWhiteSpace($Capacity)) {
    throw "Provide -Capacity to assign/switch, or use -Unassign to remove the workspace from its capacity."
}

# One token for the whole run. Headers used to shell out to `az` on every request,
# including every 5-second poll, which made a simple assign take minutes.
$script:Token = $null
function Get-Token {
    if (-not $script:Token) {
        $t = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($t)) { throw "Could not get a Fabric token. Run 'az login' first." }
        $script:Token = $t
    }
    return $script:Token
}
function Headers { @{ Authorization = "Bearer $(Get-Token)"; "Content-Type" = "application/json" } }
function Is-Guid([string]$s) { [guid]::TryParse($s, [ref]([guid]::Empty)) }

function Get-AllPages([string]$Uri) {
    # List endpoints are paginated. Reading only the first page meant a workspace that
    # was not on it was reported as "not found" in any tenant with many workspaces.
    $items = @()
    $next = $Uri
    while ($next) {
        $page = Invoke-RestMethod -Uri $next -Headers (Headers)
        $items += @($page.value)
        if ($page.continuationUri) { $next = $page.continuationUri }
        elseif ($page.continuationToken) { $next = "$($Uri)?continuationToken=$([uri]::EscapeDataString($page.continuationToken))" }
        else { $next = $null }
    }
    return $items
}

function Wait-Operation($response) {
    if ([int]$response.StatusCode -ne 202) { return }
    $op = @($response.Headers["Operation-Location"])[0]; if (-not $op) { $op = @($response.Headers["Location"])[0] }
    if (-not $op) { return }
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ((Get-Date) -gt $deadline) { throw "Operation did not finish within $TimeoutSeconds seconds. Check the workspace settings in the portal: $op" }
        Start-Sleep -Seconds 5
        $status = (Invoke-RestMethod -Uri $op -Headers (Headers)).status
        Write-Host "  operation: $status"
    } while ($status -notin @("Succeeded", "Completed", "Failed", "Cancelled"))
    if ($status -eq "Failed") { throw "Operation failed. Check that you are a capacity admin and have workspace admin rights." }
    if ($status -eq "Cancelled") { throw "Operation was cancelled." }
}

function Same-Guid([string]$a, [string]$b) {
    if ([string]::IsNullOrWhiteSpace($a) -or [string]::IsNullOrWhiteSpace($b)) { return $false }
    return ([guid]$a) -eq ([guid]$b)
}

# --- Resolve the workspace ---
if (Is-Guid $Workspace) {
    $wsId = $Workspace
}
else {
    $all = Get-AllPages "$api/workspaces"
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
$caps = Get-AllPages "$api/capacities"
if (Is-Guid $Capacity) {
    $cap = $caps | Where-Object { Same-Guid $_.id $Capacity } | Select-Object -First 1
    if (-not $cap) { throw "Capacity GUID '$Capacity' is not visible to you. Are you a capacity admin and is it Active?" }
}
else {
    $m = @($caps | Where-Object { $_.displayName -eq $Capacity })
    if ($m.Count -eq 0) { throw "Capacity '$Capacity' not found. Visible capacities: " + (($caps | ForEach-Object { $_.displayName }) -join ", ") }
    if ($m.Count -gt 1) { throw "Multiple capacities named '$Capacity' -- pass the GUID instead." }
    $cap = $m[0]
}
Write-Host "Capacity:  $($cap.displayName) -> $($cap.id) (sku $($cap.sku), state $($cap.state))" -ForegroundColor Cyan
# Assigning to a paused capacity fails after the wait with a generic error, so stop
# here with the actual reason instead.
if ($cap.state -ne "Active") { throw "Capacity '$($cap.displayName)' is '$($cap.state)', not 'Active'. Resume it first, then re-run." }

Write-Host "Assigning capacity to workspace..."
$resp = Invoke-WebRequest -Method POST -Uri "$api/workspaces/$wsId/assignToCapacity" `
    -Headers (Headers) -Body (@{ capacityId = $cap.id } | ConvertTo-Json) -UseBasicParsing
Wait-Operation $resp

Start-Sleep -Seconds 3
$ws = Invoke-RestMethod -Uri "$api/workspaces/$wsId" -Headers (Headers)
if (Same-Guid $ws.capacityId $cap.id) {
    Write-Host "SUCCESS: '$($ws.displayName)' is now on capacity '$($cap.displayName)' ($($cap.id))." -ForegroundColor Green
}
else {
    Write-Host "Assignment submitted, but the workspace still reports capacityId '$($ws.capacityId)'. Re-check in a minute." -ForegroundColor Yellow
}
