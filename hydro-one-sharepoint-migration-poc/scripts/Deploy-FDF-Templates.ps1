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
        if ($bodyJson) {
            return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -Body $bodyJson
        }
        return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers
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

    return @{
        format = "Default"
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
        $response = Invoke-FabricRequest -Method GET -Path $path
        $items += @($response.value)
        $continuationToken = $response.continuationToken
        if ($continuationToken) {
            $path = "/workspaces/$WorkspaceId/items?continuationToken=$([uri]::EscapeDataString($continuationToken))"
        }
    } while ($continuationToken)

    return $items
}

if (-not $AccessToken) {
    Write-Step "Getting Fabric access token from Azure CLI..."
    $AccessToken = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($AccessToken)) {
        throw "Unable to get Fabric access token. Run 'az login' and ensure the account has Fabric workspace Contributor access."
    }
}
$script:AccessToken = $AccessToken

$TemplateDir = (Resolve-Path $TemplateDir).Path
$pipelineRoot = Join-Path $TemplateDir "pipelines"
if (-not (Test-Path $pipelineRoot)) {
    throw "Pipeline template folder not found: $pipelineRoot. Run Convert-ADF-To-FDF.ps1 first."
}

Write-Step "Reading existing Fabric workspace items..."
$existingByName = @{}
foreach ($item in @(Get-FabricWorkspaceItems -WorkspaceId $WorkspaceId)) {
    if ($item.type -eq "DataPipeline") {
        $existingByName[$item.displayName] = $item
    }
}

$pipelineDirs = Get-ChildItem -Path $pipelineRoot -Directory -Filter "*.DataPipeline" | Sort-Object Name
foreach ($dir in $pipelineDirs) {
    $platform = Get-Content -Raw -Path (Join-Path $dir.FullName ".platform") | ConvertFrom-Json -Depth 100
    $displayName = [string]$platform.metadata.displayName
    $definition = Get-ItemDefinitionPayload -ItemDirectory $dir.FullName

    if ($existingByName.ContainsKey($displayName)) {
        $itemId = $existingByName[$displayName].id
        Write-Step "Updating DataPipeline '$displayName' ($itemId)..."
        if (-not $WhatIf) {
            Invoke-FabricRequest -Method POST -Path "/workspaces/$WorkspaceId/items/$itemId/updateDefinition?updateMetadata=true" -Body @{
                definition = $definition
            } | Out-Null
        }
    }
    else {
        Write-Step "Creating DataPipeline '$displayName'..."
        if (-not $WhatIf) {
            Invoke-FabricRequest -Method POST -Path "/workspaces/$WorkspaceId/items" -Body @{
                displayName = $displayName
                type = "DataPipeline"
                description = [string]$platform.metadata.description
                definition = $definition
            } | Out-Null
        }
    }
}

Write-Step "Fabric Data Factory deployment request completed." "SUCCESS"
