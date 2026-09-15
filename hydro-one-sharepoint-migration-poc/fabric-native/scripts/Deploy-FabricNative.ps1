<#
.SYNOPSIS
    Deploys the Fabric-native SharePoint -> OneLake migration stack end to end.

.DESCRIPTION
    Provisions, idempotently, in a Fabric workspace:
      * a Lakehouse (OneLake sink for migrated files + Delta state tables),
      * the Spark notebook that streams SharePoint content into OneLake,
      * the SharePoint-connector inventory pipeline, and
      * the master orchestration pipeline.

    The notebook .ipynb is assembled from notebooks\<name>\notebook.py at deploy
    time so the source stays readable and reviewable. Cross-item references are
    resolved after every item exists (two passes), so pipeline/notebook/Lakehouse
    GUIDs never need to be hand-copied.

    Runs on Windows PowerShell 5.1 and PowerShell 7+. Convert-ADF-To-FDF.ps1 is
    NOT used by this path.

.PARAMETER WorkspaceId
    Target Fabric workspace ID (GUID).

.PARAMETER ConfigPath
    JSON config (see config\fabric-native.sample.json) with the Lakehouse name,
    item names, Graph/SharePoint settings, and the SharePoint connection ID.

.PARAMETER SourceDir
    Path to the fabric-native folder. Defaults to fabric-native.

.PARAMETER AccessToken
    Optional Fabric bearer token. If omitted, obtained from Azure CLI.

.PARAMETER WhatIf
    Offline dry-run: no token, no Fabric calls. Assembles the notebook and resolves
    every pipeline against stand-in GUIDs, failing on anything that would not deploy.

.EXAMPLE
    .\scripts\Deploy-FabricNative.ps1 -WorkspaceId "<guid>" -ConfigPath .\config\fabric-native.json
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][guid]$WorkspaceId,
    [string]$ConfigPath,
    # Defaults to the fabric-native folder this script lives in, so it works
    # regardless of the current directory.
    [string]$SourceDir = (Join-Path $PSScriptRoot ".."),
    [string]$AccessToken,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$FabricApiRoot = "https://api.fabric.microsoft.com/v1"

function Write-Step {
    param([string]$Message, [string]$Level = "INFO")
    $color = switch ($Level) { "SUCCESS" { "Green" } "WARNING" { "Yellow" } "ERROR" { "Red" } default { "White" } }
    Write-Host $Message -ForegroundColor $color
}

function ConvertTo-Base64Utf8 {
    param([Parameter(Mandatory = $true)][string]$Text)
    return [Convert]::ToBase64String((New-Object System.Text.UTF8Encoding($false)).GetBytes($Text))
}

function Read-Utf8 {
    # Windows PowerShell 5.1 reads BOM-less files with Get-Content as the ANSI code
    # page, which corrupts any non-ASCII character in notebook.py or a description.
    param([Parameter(Mandatory = $true)][string]$Path)
    return [System.IO.File]::ReadAllText((Resolve-Path -LiteralPath $Path).Path, (New-Object System.Text.UTF8Encoding($false)))
}

function Invoke-FabricRequest {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("GET", "POST")] [string]$Method,
        [Parameter(Mandatory = $true)][string]$Path,
        $Body
    )
    $headers = @{ Authorization = "Bearer $script:AccessToken"; "Content-Type" = "application/json" }
    $uri = "$FabricApiRoot$Path"
    $bodyJson = if ($null -ne $Body) { $Body | ConvertTo-Json -Depth 50 } else { $null }
    try {
        $params = @{ Method = $Method; Uri = $uri; Headers = $headers; UseBasicParsing = $true; ErrorAction = "Stop" }
        if ($bodyJson) { $params["Body"] = $bodyJson }
        $response = Invoke-WebRequest @params
        $data = $null
        if ($response.Content) { try { $data = $response.Content | ConvertFrom-Json } catch { $data = $null } }
        return [pscustomobject]@{ StatusCode = [int]$response.StatusCode; Headers = $response.Headers; Data = $data }
    }
    catch {
        $status = $null
        $detail = $null
        $r = $_.Exception.Response
        if ($r) { try { $status = [int]$r.StatusCode } catch { $status = $null } }
        # PowerShell 7 puts the response body in ErrorDetails, and its Response is an
        # HttpResponseMessage with no GetResponseStream(). Calling that here used to
        # throw inside this handler and hide the real Fabric error message.
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
            $detail = $_.ErrorDetails.Message
        }
        elseif ($r -and ($r | Get-Member -Name GetResponseStream -MemberType Method)) {
            try { $detail = ([System.IO.StreamReader]::new($r.GetResponseStream())).ReadToEnd() } catch { $detail = $null }
        }
        if ($status -or $detail) { throw "Fabric API $Method $Path failed with HTTP ${status}: $detail" }
        throw
    }
}

function Wait-FabricOperation {
    param([Parameter(Mandatory = $true)]$Response, [int]$TimeoutSeconds = 1800)
    if ($Response.StatusCode -ne 202) { return }
    $operationUrl = @($Response.Headers["Operation-Location"])[0]
    if (-not $operationUrl) { $operationUrl = @($Response.Headers["Location"])[0] }
    if (-not $operationUrl) { return }
    $headers = @{ Authorization = "Bearer $script:AccessToken" }
    $retryAfter = @($Response.Headers["Retry-After"])[0]
    # A deadline, because a status that never turns terminal (or a response that is
    # not JSON) used to keep this loop polling forever.
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ($true) {
        if ((Get-Date) -gt $deadline) { throw "Fabric operation did not finish within $TimeoutSeconds seconds: $operationUrl" }
        Start-Sleep -Seconds ([int]$(if ($retryAfter) { $retryAfter } else { 5 }))
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

function Get-FabricWorkspaceItems {
    $items = @()
    $path = "/workspaces/$WorkspaceId/items"
    do {
        $response = (Invoke-FabricRequest -Method GET -Path $path).Data
        $items += @($response.value)
        $continuationToken = $response.continuationToken
        if ($continuationToken) { $path = "/workspaces/$WorkspaceId/items?continuationToken=$([uri]::EscapeDataString($continuationToken))" }
    } while ($continuationToken)
    return $items
}

function Set-NotebookDefault {
    # Set the default of one parameter assignment in notebook.py, e.g. workspace_id = "".
    # Whitespace-tolerant, and the value is inserted literally. The previous -replace
    # needed the exact column alignment of the '=' signs (so reformatting the file
    # silently skipped the injection) and treated '$' in a value as a regex group.
    param([string]$Text, [string]$Name, [string]$Value)
    $regex = [regex]('(?m)^(' + [regex]::Escape($Name) + '\s*=\s*)"[^"\r\n]*"')
    if (-not $regex.IsMatch($Text)) {
        throw "notebook.py has no '$Name = ""...""' assignment for the deploy to set."
    }
    $literal = $Value.Replace('\', '\\').Replace('"', '\"')
    $evaluator = [System.Text.RegularExpressions.MatchEvaluator] { param($m) $m.Groups[1].Value + '"' + $literal + '"' }.GetNewClosure()
    return $regex.Replace($Text, $evaluator, 1)
}

function Build-NotebookIpynb {
    # Assemble an .ipynb from notebook.py: split on the "# CELL" markers, inject
    # the default-lakehouse metadata, and set the workspace/lakehouse parameter
    # defaults so the notebook is runnable on its own and from the pipeline.
    param(
        [Parameter(Mandatory = $true)][string]$NotebookPyPath,
        [string]$LakehouseId,
        [string]$LakehouseName,
        $Graph
    )
    $raw = Read-Utf8 $NotebookPyPath
    $raw = Set-NotebookDefault -Text $raw -Name "workspace_id" -Value "$WorkspaceId"
    if ($LakehouseId) { $raw = Set-NotebookDefault -Text $raw -Name "lakehouse_id" -Value $LakehouseId }

    # Bake the Graph identity from config into the notebook defaults so the
    # deployed notebook can authenticate on its own (run from the pipeline, a
    # schedule, or az rest) without re-supplying tenant/client/vault every time.
    # The client secret is NEVER baked in -- it is read from Key Vault at run time.
    if ($Graph) {
        if ($Graph.tenantId)         { $raw = Set-NotebookDefault -Text $raw -Name "tenant_id" -Value ([string]$Graph.tenantId) }
        if ($Graph.clientId)         { $raw = Set-NotebookDefault -Text $raw -Name "client_id" -Value ([string]$Graph.clientId) }
        if ($Graph.keyVaultUri)      { $raw = Set-NotebookDefault -Text $raw -Name "key_vault_uri" -Value ([string]$Graph.keyVaultUri) }
        if ($Graph.clientSecretName) { $raw = Set-NotebookDefault -Text $raw -Name "client_secret_name" -Value ([string]$Graph.clientSecretName) }
    }

    # Split into cells on the marker; drop the file header before the first marker.
    $parts = [regex]::Split($raw, '(?m)^# CELL .*$')
    $cellTexts = @($parts | Select-Object -Skip 1)
    if ($cellTexts.Count -eq 0) { throw "$NotebookPyPath has no '# CELL' markers, so there is nothing to deploy." }
    $cellIndex = 0
    $cells = foreach ($text in $cellTexts) {
        $body = $text.Trim("`r", "`n")
        $lines = $body -split "`n"
        # nbformat wants each source line to retain its trailing newline except the last
        $src = for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($i -lt $lines.Count - 1) { ($lines[$i] -replace "`r$", "") + "`n" } else { ($lines[$i] -replace "`r$", "") }
        }
        # The FIRST cell is the parameters cell -- it MUST be tagged "parameters"
        # so Fabric injects pipeline/job parameter overrides AFTER it. Without the
        # tag, Fabric injects the overrides before this cell and the defaults here
        # clobber them (e.g. site_url back to "" -> the notebook runs smoke mode).
        $meta = if ($cellIndex -eq 0) { @{ tags = @("parameters") } } else { @{} }
        $cellIndex++
        [ordered]@{ cell_type = "code"; source = @($src); metadata = $meta; outputs = @(); execution_count = $null }
    }

    $dependencies = @{}
    if ($LakehouseId) {
        $dependencies["lakehouse"] = [ordered]@{
            default_lakehouse = $LakehouseId
            default_lakehouse_name = $LakehouseName
            default_lakehouse_workspace_id = "$WorkspaceId"
            known_lakehouses = @(@{ id = $LakehouseId })
        }
    }
    $nb = [ordered]@{
        cells = @($cells)
        metadata = [ordered]@{
            language_info = @{ name = "python" }
            kernelspec = @{ name = "synapse_pyspark"; display_name = "Synapse PySpark" }
            dependencies = $dependencies
        }
        nbformat = 4
        nbformat_minor = 5
    }
    return ($nb | ConvertTo-Json -Depth 30)
}

function Resolve-Placeholders {
    # Text-level substitution of deploy-time placeholders in pipeline content.
    param([string]$Text, [hashtable]$NameToId, [string]$LakehouseId, [string]$SharePointConnectionId)
    $Text = $Text.Replace("__WORKSPACE_ID__", "$WorkspaceId")
    if ($LakehouseId) { $Text = $Text.Replace("__LAKEHOUSE_ID__", $LakehouseId) }
    if ($SharePointConnectionId) { $Text = $Text.Replace("__SHAREPOINT_CONNECTION__", $SharePointConnectionId) }
    foreach ($name in $NameToId.Keys) {
        # ${name} braces are required: "$name__" would be parsed as a variable
        # named 'name__' (underscores are valid in PowerShell identifiers).
        $Text = $Text.Replace("__ITEM:${name}__", $NameToId[$name])
    }
    return $Text
}

function Resolve-ExecutePipelineRefs {
    # Rewrite ExecutePipeline pipeline.referenceName (ADF/display name) -> Fabric
    # item GUID. Fabric rejects name-based pipeline references.
    param($Activities, [hashtable]$NameToId, [System.Collections.Generic.List[string]]$Unresolved)
    foreach ($a in @($Activities)) {
        if ([string]$a.type -eq "ExecutePipeline") {
            $ref = [string]$a.typeProperties.pipeline.referenceName
            if ($NameToId.ContainsKey($ref)) { $a.typeProperties.pipeline.referenceName = $NameToId[$ref] }
            elseif ($ref -notmatch '^[0-9a-fA-F-]{36}$') { $Unresolved.Add($ref) }
        }
        $tp = $a.typeProperties
        if ($null -ne $tp) {
            foreach ($k in "activities", "ifTrueActivities", "ifFalseActivities", "defaultActivities") {
                if ($tp.$k) { Resolve-ExecutePipelineRefs -Activities $tp.$k -NameToId $NameToId -Unresolved $Unresolved }
            }
            if ($tp.cases) { foreach ($c in $tp.cases) { Resolve-ExecutePipelineRefs -Activities $c.activities -NameToId $NameToId -Unresolved $Unresolved } }
        }
    }
}

function Test-PipelineAssembly {
    # Offline check for -WhatIf: resolve every placeholder against stand-in GUIDs,
    # confirm the result parses, and fail on anything left unresolved. -WhatIf used to
    # stop after the notebook and never looked at the pipelines at all.
    param([Parameter(Mandatory = $true)]$PipelineFolder, [hashtable]$NameToId, [string]$SharePointConnectionId)
    $pName = $PipelineFolder.Name -replace '\.DataPipeline$', ''
    $text = Read-Utf8 (Join-Path $PipelineFolder.FullName "pipeline-content.json")
    $text = Resolve-Placeholders -Text $text -NameToId $NameToId -LakehouseId ([guid]::NewGuid().ToString()) -SharePointConnectionId $SharePointConnectionId
    try { $parsed = $text | ConvertFrom-Json }
    catch { throw "[WhatIf] '$pName' pipeline-content.json does not parse: $($_.Exception.Message)" }
    try { $null = (Read-Utf8 (Join-Path $PipelineFolder.FullName ".platform")) | ConvertFrom-Json }
    catch { throw "[WhatIf] '$pName' .platform is missing or does not parse: $($_.Exception.Message)" }
    # Only the activities are checked: a description is free text and may mention a
    # placeholder by name without using one.
    $activityText = @($parsed.properties.activities) | ConvertTo-Json -Depth 50
    $leftover = @([regex]::Matches("$activityText", '__(?:WORKSPACE_ID|LAKEHOUSE_ID|ITEM:[^"]*?)__') | ForEach-Object { $_.Value } | Sort-Object -Unique)
    if ($leftover.Count -gt 0) { throw "[WhatIf] '$pName' has unresolved placeholders: $($leftover -join ', ')" }
    $unresolved = [System.Collections.Generic.List[string]]::new()
    Resolve-ExecutePipelineRefs -Activities $parsed.properties.activities -NameToId $NameToId -Unresolved $unresolved
    if ($unresolved.Count -gt 0) { throw "[WhatIf] '$pName' calls pipelines that are not part of this deployment: $(($unresolved | Sort-Object -Unique) -join ', ')" }
    $count = @($parsed.properties.activities).Count
    if ($text -match '__SHAREPOINT_CONNECTION__') {
        Write-Step "[WhatIf] pipeline '$pName' is valid; it deploys as a skeleton until sharePointConnectionId is set ($count activities defined)." "WARNING"
    }
    else {
        Write-Step "[WhatIf] pipeline '$pName' is valid and fully resolvable ($count activities)."
    }
}

# --- Load config --------------------------------------------------------------
$config = $null
if ($ConfigPath) {
    if (-not (Test-Path $ConfigPath)) { throw "Config file '$ConfigPath' not found." }
    $config = Read-Utf8 $ConfigPath | ConvertFrom-Json
}
$lakehouseName = if ($config -and $config.lakehouseName) { [string]$config.lakehouseName } else { "HydroOneMigration" }
$sharePointConnectionId = if ($config -and $config.sharePointConnectionId) { [string]$config.sharePointConnectionId } else { "" }

$SourceDir = (Resolve-Path $SourceDir).Path
$notebookDir = Join-Path $SourceDir "notebooks"
$pipelineRoot = Join-Path $SourceDir "pipelines"

# --- Token --------------------------------------------------------------------
if (-not $WhatIf) {
    if (-not $AccessToken) {
        Write-Step "Getting Fabric access token from Azure CLI..."
        $AccessToken = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($AccessToken)) {
            throw "Unable to get Fabric access token. Run 'az login' with Fabric workspace Contributor access."
        }
    }
    $script:AccessToken = $AccessToken
}

# --- Ensure Lakehouse ---------------------------------------------------------
$lakehouseId = ""
if (-not $WhatIf) {
    $existing = @(Get-FabricWorkspaceItems)
    $lh = $existing | Where-Object { $_.type -eq "Lakehouse" -and $_.displayName -eq $lakehouseName } | Select-Object -First 1
    if ($lh) {
        $lakehouseId = $lh.id
        Write-Step "Lakehouse '$lakehouseName' exists ($lakehouseId)."
    }
    else {
        Write-Step "Creating Lakehouse '$lakehouseName'..."
        $resp = Invoke-FabricRequest -Method POST -Path "/workspaces/$WorkspaceId/items" -Body @{
            displayName = $lakehouseName; type = "Lakehouse"; description = "OneLake sink for SharePoint migration"
        }
        if ($resp.Data -and $resp.Data.id) { $lakehouseId = [string]$resp.Data.id }
        Wait-FabricOperation -Response $resp
        # The item list lags a newly created item. Without a resolved id the notebook
        # deployed with no default Lakehouse and the pipeline kept the literal
        # __LAKEHOUSE_ID__, which only failed later, at run time.
        for ($attempt = 0; -not $lakehouseId -and $attempt -lt 12; $attempt++) {
            Start-Sleep -Seconds 5
            $lakehouseId = (@(Get-FabricWorkspaceItems) | Where-Object { $_.type -eq "Lakehouse" -and $_.displayName -eq $lakehouseName } | Select-Object -First 1).id
        }
        if (-not $lakehouseId) { throw "Lakehouse '$lakehouseName' was created but its id could not be resolved. Re-run the deploy; it will find the existing Lakehouse." }
        Write-Step "Created Lakehouse ($lakehouseId)." "SUCCESS"
    }
}
else {
    Write-Step "[WhatIf] would ensure Lakehouse '$lakehouseName'."
}

# --- Pass 1: create/ensure notebook + pipelines (allocate GUIDs) --------------
$notebookFolders = @(Get-ChildItem -Path $notebookDir -Directory -ErrorAction SilentlyContinue)
$pipelineFiles = @(Get-ChildItem -Path $pipelineRoot -Directory -Filter "*.DataPipeline" -ErrorAction SilentlyContinue)

$existingByName = @{}
if (-not $WhatIf) { foreach ($i in @(Get-FabricWorkspaceItems)) { $existingByName["$($i.type)/$($i.displayName)"] = $i } }

# Notebook(s): assembled fully now (no cross-item refs beyond ws/lakehouse).
foreach ($nbFolder in $notebookFolders) {
    $nbName = $nbFolder.Name
    $nbPy = Join-Path $nbFolder.FullName "notebook.py"
    if (-not (Test-Path $nbPy)) { continue }
    $ipynb = Build-NotebookIpynb -NotebookPyPath $nbPy -LakehouseId $lakehouseId -LakehouseName $lakehouseName -Graph $(if ($config) { $config.graph } else { $null })
    if ($WhatIf) {
        $check = $ipynb | ConvertFrom-Json
        $first = @($check.cells)[0]
        if (-not $first -or (@($first.metadata.tags) -notcontains "parameters")) { throw "[WhatIf] Notebook '$nbName' has no parameters cell; pipeline parameters would be ignored." }
        Write-Step "[WhatIf] would deploy Notebook '$nbName' ($(@($check.cells).Count) cells, $([math]::Round($ipynb.Length/1KB)) KB ipynb)."
        continue
    }
    $definition = @{ format = "ipynb"; parts = @(@{ path = "notebook-content.ipynb"; payload = (ConvertTo-Base64Utf8 -Text $ipynb); payloadType = "InlineBase64" }) }
    $key = "Notebook/$nbName"
    if ($existingByName.ContainsKey($key)) {
        Write-Step "Updating Notebook '$nbName'..."
        # No updateMetadata here: the notebook definition has no .platform part and
        # Fabric rejects updateMetadata=true without one. The display name is fixed,
        # so a definition-only update is all that's needed.
        $resp = Invoke-FabricRequest -Method POST -Path "/workspaces/$WorkspaceId/items/$($existingByName[$key].id)/updateDefinition" -Body @{ definition = $definition }
    }
    else {
        Write-Step "Creating Notebook '$nbName'..."
        $resp = Invoke-FabricRequest -Method POST -Path "/workspaces/$WorkspaceId/items" -Body @{ displayName = $nbName; type = "Notebook"; definition = $definition }
    }
    Wait-FabricOperation -Response $resp
}

# Pipelines: create empty skeletons first so they all have GUIDs.
$emptyPipeline = @{ properties = @{ activities = @() } } | ConvertTo-Json -Depth 5
foreach ($pf in $pipelineFiles) {
    $pName = $pf.Name -replace '\.DataPipeline$', ''
    $key = "DataPipeline/$pName"
    if ($WhatIf) { Write-Step "[WhatIf] would ensure pipeline '$pName'."; continue }
    if ($existingByName.ContainsKey($key)) { continue }
    Write-Step "Creating pipeline skeleton '$pName'..."
    $platformText = Read-Utf8 (Join-Path $pf.FullName ".platform")
    $platform = $platformText | ConvertFrom-Json
    $def = @{ parts = @(
        @{ path = "pipeline-content.json"; payload = (ConvertTo-Base64Utf8 -Text $emptyPipeline); payloadType = "InlineBase64" },
        @{ path = ".platform"; payload = (ConvertTo-Base64Utf8 -Text $platformText); payloadType = "InlineBase64" }
    ) }
    $resp = Invoke-FabricRequest -Method POST -Path "/workspaces/$WorkspaceId/items" -Body @{ displayName = $pName; type = "DataPipeline"; description = [string]$platform.metadata.description; definition = $def }
    Wait-FabricOperation -Response $resp
}

if ($WhatIf) {
    $standIns = @{}
    foreach ($nbFolder in $notebookFolders) { $standIns[$nbFolder.Name] = [guid]::NewGuid().ToString() }
    foreach ($pf in $pipelineFiles) { $standIns[($pf.Name -replace '\.DataPipeline$', '')] = [guid]::NewGuid().ToString() }
    foreach ($pf in $pipelineFiles) {
        Test-PipelineAssembly -PipelineFolder $pf -NameToId $standIns -SharePointConnectionId $sharePointConnectionId
    }
    Write-Step "[WhatIf] assembly validated. No Fabric changes made." "SUCCESS"
    return
}

# --- Build complete name -> GUID map ------------------------------------------
Start-Sleep -Seconds 2
$nameToId = @{}
foreach ($i in @(Get-FabricWorkspaceItems)) {
    if ($i.type -in @("DataPipeline", "Notebook", "Lakehouse")) { $nameToId[$i.displayName] = $i.id }
}

# --- Pass 2: resolve references and push full pipeline definitions -------------
foreach ($pf in $pipelineFiles) {
    $pName = $pf.Name -replace '\.DataPipeline$', ''
    $itemId = $nameToId[$pName]
    if (-not $itemId) { throw "Pipeline '$pName' was created but is not in the workspace item list yet. Re-run the deploy." }
    Write-Step "Finalizing pipeline '$pName'..."
    $platformText = Read-Utf8 (Join-Path $pf.FullName ".platform")

    $contentText = Read-Utf8 (Join-Path $pf.FullName "pipeline-content.json")
    $contentText = Resolve-Placeholders -Text $contentText -NameToId $nameToId -LakehouseId $lakehouseId -SharePointConnectionId $sharePointConnectionId

    if ($contentText -match '__SHAREPOINT_CONNECTION__') {
        # Fabric rejects a pipeline that references a non-existent connection, so this
        # one stays activity-free until a real connection GUID is configured. It still
        # declares its real parameters, because PL_Migrate_Master passes SiteUrl and
        # LibraryName to it; declaring them keeps that call valid rather than relying
        # on undeclared parameters being ignored.
        $declared = ($contentText | ConvertFrom-Json).properties.parameters
        $skeleton = @{ properties = @{ activities = @(); parameters = $declared } } | ConvertTo-Json -Depth 20
        $def = @{ parts = @(
            @{ path = "pipeline-content.json"; payload = (ConvertTo-Base64Utf8 -Text $skeleton); payloadType = "InlineBase64" },
            @{ path = ".platform"; payload = (ConvertTo-Base64Utf8 -Text $platformText); payloadType = "InlineBase64" }
        ) }
        $resp = Invoke-FabricRequest -Method POST -Path "/workspaces/$WorkspaceId/items/$itemId/updateDefinition?updateMetadata=true" -Body @{ definition = $def }
        Wait-FabricOperation -Response $resp
        Write-Step "  SKIP: '$pName' needs a SharePoint connection; left as a skeleton with its parameters." "WARNING"
        Write-Step "        Set 'sharePointConnectionId' in the config and re-run to bind it." "WARNING"
        continue
    }

    $content = $contentText | ConvertFrom-Json
    $unresolved = [System.Collections.Generic.List[string]]::new()
    Resolve-ExecutePipelineRefs -Activities $content.properties.activities -NameToId $nameToId -Unresolved $unresolved
    foreach ($u in ($unresolved | Sort-Object -Unique)) { Write-Step "  WARNING: unresolved pipeline reference '$u'." "WARNING" }

    $finalText = $content | ConvertTo-Json -Depth 50
    $def = @{ parts = @(
        @{ path = "pipeline-content.json"; payload = (ConvertTo-Base64Utf8 -Text $finalText); payloadType = "InlineBase64" },
        @{ path = ".platform"; payload = (ConvertTo-Base64Utf8 -Text $platformText); payloadType = "InlineBase64" }
    ) }
    $resp = Invoke-FabricRequest -Method POST -Path "/workspaces/$WorkspaceId/items/$itemId/updateDefinition?updateMetadata=true" -Body @{ definition = $def }
    Wait-FabricOperation -Response $resp
}

Write-Step "Fabric-native migration stack deployed." "SUCCESS"
Write-Step "  Lakehouse:  $lakehouseName ($lakehouseId)" "SUCCESS"
foreach ($n in ($nameToId.Keys | Sort-Object)) { Write-Step "  $n -> $($nameToId[$n])" }
