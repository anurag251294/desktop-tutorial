<#
.SYNOPSIS
    Deploys generated Fabric Data Factory DataPipeline item definitions.

.DESCRIPTION
    Creates or updates Microsoft Fabric DataPipeline items in a workspace using
    the Fabric REST API. Run Convert-ADF-To-FDF.ps1 first to generate the
    fdf-templates folder.

.PARAMETER WorkspaceId
    Fabric workspace ID (GUID).

.PARAMETER TemplateDir
    Path to generated Fabric templates. Defaults to fdf-templates.

.PARAMETER AccessToken
    Optional Fabric API bearer token. If omitted, the script obtains one from
    Azure CLI with resource https://api.fabric.microsoft.com.

.PARAMETER WhatIf
    Shows create/update actions without calling Fabric.

.EXAMPLE
    .\scripts\Deploy-FDF-Templates.ps1 -WorkspaceId "<workspace-guid>"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [guid]$WorkspaceId,

    [string]$TemplateDir = "fdf-templates",

    [string]$AccessToken,

    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$FabricApiRoot = "https://api.fabric.microsoft.com/v1"

function Write-Step {
    param([string]$Message, [string]$Level = "INFO")
    $color = switch ($Level) {
        "SUCCESS" { "Green" }
        "WARNING" { "Yellow" }
        "ERROR" { "Red" }
        default { "White" }
    }
    Write-Host $Message -ForegroundColor $color
}

function ConvertTo-Base64Payload {
    param([Parameter(Mandatory = $true)][string]$Path)
    $bytes = [System.IO.File]::ReadAllBytes((Resolve-Path $Path).Path)
    return [Convert]::ToBase64String($bytes)
}

function Invoke-FabricRequest {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("GET", "POST")] [string]$Method,
        [Parameter(Mandatory = $true)][string]$Path,
        $Body
    )

    $headers = @{
        Authorization = "Bearer $script:AccessToken"
        "Content-Type" = "application/json"
    }
    $uri = "$FabricApiRoot$Path"
    $bodyJson = if ($null -ne $Body) { $Body | ConvertTo-Json -Depth 100 } else { $null }

    try {
        # Invoke-WebRequest (not Invoke-RestMethod) so we can inspect the status
        # code and headers — Fabric item create/updateDefinition are asynchronous
        # and return HTTP 202 + an Operation-Location header we must poll.
        $params = @{
            Method          = $Method
            Uri             = $uri
            Headers         = $headers
            UseBasicParsing = $true
            ErrorAction     = "Stop"
        }
        if ($bodyJson) { $params["Body"] = $bodyJson }
        $response = Invoke-WebRequest @params

        $data = $null
        if ($response.Content) {
            try { $data = $response.Content | ConvertFrom-Json } catch { $data = $null }
        }
        return [pscustomobject]@{
            StatusCode = [int]$response.StatusCode
            Headers    = $response.Headers
            Data       = $data
        }
    }
    catch {
        $response = $_.Exception.Response
        if ($response) {
            $reader = [System.IO.StreamReader]::new($response.GetResponseStream())
            $details = $reader.ReadToEnd()
            throw "Fabric API $Method $Path failed with HTTP $([int]$response.StatusCode): $details"
        }
        throw
    }
}

function Wait-FabricOperation {
    # Polls a Fabric long-running operation (HTTP 202) to completion. No-op for
    # synchronous 200/201 responses so callers can wrap every mutating request.
    param([Parameter(Mandatory = $true)]$Response)

    if ($Response.StatusCode -ne 202) { return }

    $operationUrl = @($Response.Headers["Operation-Location"])[0]
    if (-not $operationUrl) { $operationUrl = @($Response.Headers["Location"])[0] }
    if (-not $operationUrl) { return }

    $headers = @{ Authorization = "Bearer $script:AccessToken" }
    $retryAfter = @($Response.Headers["Retry-After"])[0]
    while ($true) {
        $delay = if ($retryAfter) { [int]$retryAfter } else { 5 }
        Start-Sleep -Seconds $delay

        $op = Invoke-WebRequest -Method GET -Uri $operationUrl -Headers $headers -UseBasicParsing -ErrorAction Stop
        $status = $null
        if ($op.Content) { try { $status = ($op.Content | ConvertFrom-Json).status } catch { $status = $null } }
        $retryAfter = @($op.Headers["Retry-After"])[0]

        switch ("$status") {
            "Succeeded" { return }
            "Completed" { return }
            "Failed"    { throw "Fabric operation failed: $($op.Content)" }
            "Cancelled" { throw "Fabric operation cancelled: $($op.Content)" }
        }
    }
}

function Get-ItemDefinitionPayload {
    param([Parameter(Mandatory = $true)][string]$ItemDirectory)

    $contentPath = Join-Path $ItemDirectory "pipeline-content.json"
    $platformPath = Join-Path $ItemDirectory ".platform"
    if (-not (Test-Path $contentPath)) {
        throw "Missing pipeline-content.json in $ItemDirectory"
    }
    if (-not (Test-Path $platformPath)) {
        throw "Missing .platform in $ItemDirectory"
    }

    # DataPipeline definitions take NO 'format' field — that property is only for
    # typed formats such as Notebook ("ipynb"). Sending format = "Default" is
    # rejected with InvalidDefinitionFormat. The definition is just the parts:
    # the pipeline body plus the .platform metadata file.
    return @{
        parts = @(
            @{
                path = "pipeline-content.json"
                payload = ConvertTo-Base64Payload -Path $contentPath
                payloadType = "InlineBase64"
            },
            @{
                path = ".platform"
                payload = ConvertTo-Base64Payload -Path $platformPath
                payloadType = "InlineBase64"
            }
        )
    }
}

function Get-FabricWorkspaceItems {
    param([Parameter(Mandatory = $true)][guid]$WorkspaceId)

    $items = @()
    $path = "/workspaces/$WorkspaceId/items"
    do {
        $response = (Invoke-FabricRequest -Method GET -Path $path).Data
        $items += @($response.value)
        $continuationToken = $response.continuationToken
        if ($continuationToken) {
            $path = "/workspaces/$WorkspaceId/items?continuationToken=$([uri]::EscapeDataString($continuationToken))"
        }
    } while ($continuationToken)

    return $items
}

# -WhatIf is a fully offline dry-run: no token, no Fabric calls. This lets the
# client validate the generated templates locally before touching the workspace.
if (-not $WhatIf) {
    if (-not $AccessToken) {
        Write-Step "Getting Fabric access token from Azure CLI..."
        $AccessToken = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($AccessToken)) {
            throw "Unable to get Fabric access token. Run 'az login' and ensure the account has Fabric workspace Contributor access."
        }
    }
    $script:AccessToken = $AccessToken
}

$TemplateDir = (Resolve-Path $TemplateDir).Path
$pipelineRoot = Join-Path $TemplateDir "pipelines"
if (-not (Test-Path $pipelineRoot)) {
    throw "Pipeline template folder not found: $pipelineRoot. Run Convert-ADF-To-FDF.ps1 first."
}

$pipelineDirs = Get-ChildItem -Path $pipelineRoot -Directory -Filter "*.DataPipeline" | Sort-Object Name

# Guard: templates generated without a connection map still carry ADF-style
# "linkedServiceName" references. They will import into Fabric but every Copy /
# Lookup / stored-procedure activity will be unbound and fail at run time.
$unmapped = @($pipelineDirs | Where-Object {
    (Get-Content -Raw -Path (Join-Path $_.FullName "pipeline-content.json")) -match '"linkedServiceName"'
})
if ($unmapped.Count -gt 0) {
    Write-Step "WARNING: $($unmapped.Count) pipeline(s) still contain unmapped ADF 'linkedServiceName' references:" "WARNING"
    foreach ($u in $unmapped) { Write-Step "  - $($u.Name)" "WARNING" }
    Write-Step "These activities will not bind to Fabric connections. Re-run Convert-ADF-To-FDF.ps1" "WARNING"
    Write-Step "with -ConnectionMapPath <connections.json> (real Fabric connection GUIDs) before a production deploy." "WARNING"
}

Write-Step "Reading existing Fabric workspace items..."
$existingByName = @{}
if (-not $WhatIf) {
    foreach ($item in @(Get-FabricWorkspaceItems -WorkspaceId $WorkspaceId)) {
        if ($item.type -eq "DataPipeline") {
            $existingByName[$item.displayName] = $item
        }
    }
}

foreach ($dir in $pipelineDirs) {
    $platform = Get-Content -Raw -Path (Join-Path $dir.FullName ".platform") | ConvertFrom-Json
    $displayName = [string]$platform.metadata.displayName
    $definition = Get-ItemDefinitionPayload -ItemDirectory $dir.FullName

    # The Fabric item 'description' on the create request is capped at 256 chars
    # (InvalidParameter otherwise). The full pipeline description still lives in
    # the .platform metadata inside the definition; this only trims the workspace
    # item's catalog description.
    $description = [string]$platform.metadata.description
    if ($description.Length -gt 256) {
        $description = $description.Substring(0, 253) + "..."
    }

    if ($existingByName.ContainsKey($displayName)) {
        $itemId = $existingByName[$displayName].id
        Write-Step "Updating DataPipeline '$displayName' ($itemId)..."
        if (-not $WhatIf) {
            $response = Invoke-FabricRequest -Method POST -Path "/workspaces/$WorkspaceId/items/$itemId/updateDefinition?updateMetadata=true" -Body @{
                definition = $definition
            }
            Wait-FabricOperation -Response $response
        }
        else {
            Write-Step "  [WhatIf] would update '$displayName'."
        }
    }
    else {
        Write-Step "Creating DataPipeline '$displayName'..."
        if (-not $WhatIf) {
            $response = Invoke-FabricRequest -Method POST -Path "/workspaces/$WorkspaceId/items" -Body @{
                displayName = $displayName
                type = "DataPipeline"
                description = $description
                definition = $definition
            }
            Wait-FabricOperation -Response $response
        }
        else {
            Write-Step "  [WhatIf] would create '$displayName'."
        }
    }
}

Write-Step "Fabric Data Factory deployment request completed." "SUCCESS"
