<#
.SYNOPSIS
    Runs PL_Migrate_Master once for every document library listed in the config's "sites".

.DESCRIPTION
    A pipeline run migrates exactly one library. This script reads "sites" from the
    config and starts one run per entry, one after another, waiting for each to
    finish before starting the next. Runs are sequential on purpose: concurrent runs
    would all write the same Delta audit and inventory tables at the same time.

    Runs on Windows PowerShell 5.1 or PowerShell 7+. Uses the Azure CLI for the token
    (az login as a user, or az login --service-principal).

    Token handling (support case 2611050040004903, HTTP 401 TokenExpired while polling):
      * The token is renewed from its real expiry time, not from when this script last
        asked for it. az returns a cached token that can be close to expiry, so "renew
        every N minutes" could still send an expired token.
      * A 401 gets a fresh token and the same request is retried once.
      * A failed status check (401, throttling, a network blip) never stops the script
        and never starts a second run: it keeps polling the SAME job instance.

.PARAMETER WorkspaceId
    Fabric workspace GUID the stack was deployed to.

.PARAMETER ConfigPath
    The same config used by Deploy-FabricNative.ps1.

.PARAMETER PipelineName
    Defaults to PL_Migrate_Master.

.PARAMETER TimeoutMinutes
    How long to wait for EACH run. Defaults to 2880 (2 days), matching the notebook
    activity timeout. A run that is still going when this expires is left running, not
    cancelled.

.PARAMETER ContinueOnError
    Carry on with the remaining libraries after a run fails. The script still exits
    with an error at the end if any run failed.

.PARAMETER WhatIf
    Offline: validate the config and print the runs that would start. No token, no calls.

.EXAMPLE
    .\scripts\Start-FabricMigration.ps1 -WorkspaceId "<guid>" -ConfigPath .\config\fabric-native.json
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][guid]$WorkspaceId,
    [Parameter(Mandatory = $true)][string]$ConfigPath,
    [string]$PipelineName = "PL_Migrate_Master",
    [int]$TimeoutMinutes = 2880,
    [int]$PollSeconds = 30,
    [switch]$ContinueOnError,
    [switch]$WhatIf,
    # Testing only: point at a mock Fabric API.
    [Parameter(DontShow = $true)][string]$ApiRoot = "https://api.fabric.microsoft.com/v1"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$api = $ApiRoot.TrimEnd("/")

function Read-Utf8 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return [System.IO.File]::ReadAllText((Resolve-Path -LiteralPath $Path).Path, (New-Object System.Text.UTF8Encoding($false)))
}

# --- Build and validate the plan before touching Fabric --------------------------
if (-not (Test-Path $ConfigPath)) { throw "Config file '$ConfigPath' not found." }
$config = Read-Utf8 $ConfigPath | ConvertFrom-Json
$sites = @($config.sites | Where-Object { $_ })
if ($sites.Count -eq 0) { throw "No 'sites' in $ConfigPath. Add one entry per document library to migrate." }

$plan = @()
for ($i = 0; $i -lt $sites.Count; $i++) {
    $s = $sites[$i]
    $url = [string]$s.siteUrl
    $library = if ($s.libraryName) { [string]$s.libraryName } else { "Documents" }
    $mode = if ($s.mode) { [string]$s.mode } else { "incremental" }
    if ([string]::IsNullOrWhiteSpace($url) -or $url.Contains("<")) {
        throw "sites[$i] has no real siteUrl ('$url'). A run without one only executes the smoke test."
    }
    if ($mode -notin @("full", "incremental")) { throw "sites[$i] mode must be 'full' or 'incremental', not '$mode'." }
    $plan += [pscustomobject]@{ Run = $i + 1; SiteUrl = $url; LibraryName = $library; Mode = $mode }
}

Write-Host "$($plan.Count) run(s) of '$PipelineName', one after another:" -ForegroundColor Cyan
$plan | Format-Table -AutoSize | Out-String | Write-Host
if ($WhatIf) { Write-Host "[WhatIf] config is valid. No runs started." -ForegroundColor Green; return }

# --- Fabric helpers ------------------------------------------------------------------
# Renew this long before the token's own expiry time. az hands back its cached token
# until that is about 5 minutes from expiry, so the age of OUR copy says nothing about
# how long the token has left; only its expiry does.
$RenewBeforeExpiryMinutes = 10
$MaxPollFailures = 20

$script:Token = $null
$script:TokenExpires = [datetime]::MinValue
function Get-Token {
    param([switch]$Force)
    if ($Force -or -not $script:Token -or (Get-Date).AddMinutes($RenewBeforeExpiryMinutes) -ge $script:TokenExpires) {
        $json = az account get-access-token --resource "https://api.fabric.microsoft.com" -o json
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace("$json")) { throw "Could not get a Fabric token. Run 'az login' first." }
        $t = ($json | Out-String) | ConvertFrom-Json
        if ([string]::IsNullOrWhiteSpace($t.accessToken)) { throw "az returned no Fabric access token. Run 'az login' again." }
        $script:Token = [string]$t.accessToken
        # expires_on (Unix seconds) is unambiguous; older az versions only have
        # expiresOn, in local time.
        if ($t.expires_on) { $script:TokenExpires = [DateTimeOffset]::FromUnixTimeSeconds([long]$t.expires_on).LocalDateTime }
        elseif ($t.expiresOn) { $script:TokenExpires = [datetime]$t.expiresOn }
        else { $script:TokenExpires = (Get-Date).AddMinutes(30) }
    }
    return $script:Token
}

function Invoke-Fabric {
    param([Parameter(Mandatory = $true)][string]$Method, [Parameter(Mandatory = $true)][string]$Uri, [string]$Body)
    for ($attempt = 1; ; $attempt++) {
        $params = @{ Method = $Method; Uri = $Uri; UseBasicParsing = $true
            Headers = @{ Authorization = "Bearer $(Get-Token -Force:($attempt -gt 1))"; "Content-Type" = "application/json" } }
        if ($Body) { $params["Body"] = $Body }
        try { return Invoke-WebRequest @params }
        catch {
            $status = $null; $detail = $null
            $r = $_.Exception.Response
            if ($r) { try { $status = [int]$r.StatusCode } catch { $status = $null } }
            if ($_.ErrorDetails -and $_.ErrorDetails.Message) { $detail = $_.ErrorDetails.Message }
            elseif ($r -and ($r | Get-Member -Name GetResponseStream -MemberType Method)) {
                try { $detail = ([System.IO.StreamReader]::new($r.GetResponseStream())).ReadToEnd() } catch { $detail = $null }
            }
            # 401 TokenExpired: get a new token and send the same request once more.
            # This has to come BEFORE the throw below, or it never runs.
            if ($status -eq 401 -and $attempt -eq 1) {
                Write-Host "  Token rejected (HTTP 401); getting a new one and retrying." -ForegroundColor Yellow
                continue
            }
            if ($status -or $detail) { throw "Fabric API $Method $Uri failed with HTTP ${status}: $detail" }
            throw
        }
    }
}

function Get-PipelineId {
    $base = "$api/workspaces/$WorkspaceId/items?type=DataPipeline"
    $next = $base
    while ($next) {
        $page = (Invoke-Fabric -Method GET -Uri $next).Content | ConvertFrom-Json
        $hit = @($page.value | Where-Object { $_.displayName -eq $PipelineName }) | Select-Object -First 1
        if ($hit) { return $hit.id }
        if ($page.continuationUri) { $next = $page.continuationUri }
        elseif ($page.continuationToken) { $next = "$base&continuationToken=$([uri]::EscapeDataString($page.continuationToken))" }
        else { $next = $null }
    }
    throw "Pipeline '$PipelineName' not found in workspace $WorkspaceId. Run Deploy-FabricNative.ps1 first."
}

# --- Run each library in turn --------------------------------------------------------
$pipelineId = Get-PipelineId
$results = @()
foreach ($p in $plan) {
    Write-Host ""
    Write-Host "Run $($p.Run)/$($plan.Count): $($p.SiteUrl) / $($p.LibraryName) ($($p.Mode))" -ForegroundColor Cyan
    # The job scheduler API takes plain name/value pairs for pipeline parameters.
    $body = @{ executionData = @{ parameters = @{
        SiteUrl     = [string]$p.SiteUrl
        LibraryName = [string]$p.LibraryName
        Mode        = [string]$p.Mode
    } } } | ConvertTo-Json -Depth 10

    $started = Get-Date
    $resp = Invoke-Fabric -Method POST -Uri "$api/workspaces/$WorkspaceId/items/$pipelineId/jobs/instances?jobType=Pipeline" -Body $body
    $location = @($resp.Headers["Location"])[0]
    if (-not $location) { throw "Fabric accepted the run but returned no job Location to poll." }
    Write-Host "  Job instance: $location"

    $status = "NotStarted"
    $failure = $null
    $pollFailures = 0
    $deadline = $started.AddMinutes($TimeoutMinutes)
    while ($status -in @("NotStarted", "InProgress", "")) {
        if ((Get-Date) -gt $deadline) { $status = "TimedOut"; break }
        Start-Sleep -Seconds $PollSeconds
        try {
            $job = (Invoke-Fabric -Method GET -Uri $location).Content | ConvertFrom-Json
        }
        catch {
            # A failed status check says nothing about the run itself, which keeps going
            # in Fabric. Keep polling the same job; never start it again.
            $pollFailures++
            Write-Host ("  {0}  status check failed ({1}/{2}): {3}" -f (Get-Date -Format "HH:mm:ss"), $pollFailures, $MaxPollFailures, $_.Exception.Message) -ForegroundColor Yellow
            if ($pollFailures -ge $MaxPollFailures) { $status = "Unknown"; break }
            continue
        }
        $pollFailures = 0
        $status = [string]$job.status
        if ($job.failureReason) { $failure = ($job.failureReason | ConvertTo-Json -Compress -Depth 5) }
        Write-Host ("  {0}  {1}" -f (Get-Date -Format "HH:mm:ss"), $status)
    }

    $minutes = [math]::Round(((Get-Date) - $started).TotalMinutes, 1)
    $results += [pscustomobject]@{ Run = $p.Run; Library = "$($p.SiteUrl) / $($p.LibraryName)"; Status = $status; Minutes = $minutes }

    if ($status -eq "Completed") { continue }
    if ($status -in @("TimedOut", "Unknown")) {
        Write-Host "  Stopped watching; the run was NOT cancelled. Check its status in the Monitor hub before starting it again:" -ForegroundColor Yellow
        Write-Host "  $location" -ForegroundColor Yellow
        # Don't start the next library while this one may still be writing the same tables.
        break
    }
    elseif ($failure) { Write-Host "  $failure" -ForegroundColor Red }
    if (-not $ContinueOnError) { break }
}

Write-Host ""
$results | Format-Table -AutoSize | Out-String | Write-Host
$notDone = @($results | Where-Object { $_.Status -ne "Completed" })
$skipped = $plan.Count - $results.Count
if ($notDone.Count -gt 0 -or $skipped -gt 0) {
    throw "$($notDone.Count) run(s) did not complete and $skipped were not started. See the Monitor hub and migration_audit for details."
}
Write-Host "All $($plan.Count) library run(s) completed." -ForegroundColor Green
