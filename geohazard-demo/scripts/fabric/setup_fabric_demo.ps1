param(
    [string]$ConfigPath = ".\cicd\fabric-setup.config.json",
    [string]$OutputPath = ".\cicd\fabric-setup.output.json",
    [switch]$Reset
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-AzAccessTokenValue {
    param([string]$Resource)

    $tokenObj = az account get-access-token --resource $Resource --output json | ConvertFrom-Json
    if (-not $tokenObj.accessToken) {
        throw "Failed to acquire access token for resource: $Resource"
    }
    return $tokenObj.accessToken
}

function Invoke-RestJson {
    param(
        [string]$Method,
        [string]$Url,
        [string]$AccessToken,
        [object]$Body = $null,
        [int]$TimeoutSec = 120
    )

    $headers = @{ Authorization = "Bearer $AccessToken" }
    $responseHeaders = $null

    if ($null -ne $Body) {
        $jsonBody = $Body | ConvertTo-Json -Depth 50
        $result = Invoke-RestMethod -Method $Method -Uri $Url -Headers $headers -ContentType "application/json" -Body $jsonBody -TimeoutSec $TimeoutSec -ResponseHeadersVariable responseHeaders
    }
    else {
        $result = Invoke-RestMethod -Method $Method -Uri $Url -Headers $headers -TimeoutSec $TimeoutSec -ResponseHeadersVariable responseHeaders
    }

    return @{
        Body = $result
        Headers = $responseHeaders
    }
}

function Wait-LroIfNeeded {
    param(
        [hashtable]$Response,
        [string]$AccessToken,
        [int]$MaxAttempts = 80
    )

    $location = $null
    if ($Response.Headers -and $Response.Headers.ContainsKey("Location")) {
        $location = $Response.Headers["Location"]
    }

    if (-not $location) {
        return $Response.Body
    }

    for ($i = 1; $i -le $MaxAttempts; $i++) {
        Start-Sleep -Seconds 3
        $poll = Invoke-RestJson -Method "GET" -Url $location -AccessToken $AccessToken
        $status = $null
        if ($poll.Body.PSObject.Properties.Name -contains "status") {
            $status = $poll.Body.status
        }

        if (-not $status) {
            if (($poll.Body.PSObject.Properties.Name -contains "id") -or ($poll.Body.PSObject.Properties.Name -contains "displayName")) {
                return $poll.Body
            }
            continue
        }

        if ($status -eq "Succeeded") {
            return $poll.Body
        }
        if ($status -eq "Failed") {
            throw "Long running operation failed. Poll body: $($poll.Body | ConvertTo-Json -Depth 20)"
        }
    }

    throw "Long running operation did not complete within polling limit."
}

function Get-Active-CapacityId {
    param([string]$FabricToken)

    $caps = Invoke-RestJson -Method "GET" -Url "https://api.fabric.microsoft.com/v1/capacities" -AccessToken $FabricToken
    $active = @($caps.Body.value) | Where-Object { $_.state -eq "Active" }
    if (-not $active -or $active.Count -eq 0) {
        return ""
    }

    $preferred = $active | Where-Object { $_.sku -like "F*" } | Select-Object -First 1
    if ($preferred) {
        return [string]$preferred.id
    }

    return [string]($active | Select-Object -First 1).id
}

function Remove-AllWorkspaceItems {
    param(
        [string]$WorkspaceId,
        [string]$FabricToken
    )

    Write-Output "RESET: Wiping all items in workspace $WorkspaceId ..."
    $list = Invoke-RestJson -Method "GET" -Url "https://api.fabric.microsoft.com/v1/workspaces/$WorkspaceId/items" -AccessToken $FabricToken
    $items = @($list.Body.value)

    # SQLEndpoint / MountedDataFactory items are auto-managed and cannot be deleted directly;
    # they are removed automatically when their parent (e.g. Lakehouse) is deleted.
    $skipTypes = @("SQLEndpoint", "MountedDataFactory")

    foreach ($item in $items) {
        if ($skipTypes -contains [string]$item.type) {
            Write-Output "  skip (auto-managed): $($item.type) '$($item.displayName)'"
            continue
        }
        $itemId = [string]$item.id
        try {
            Invoke-RestJson -Method "DELETE" -Url "https://api.fabric.microsoft.com/v1/workspaces/$WorkspaceId/items/$itemId" -AccessToken $FabricToken | Out-Null
            Write-Output "  deleted: $($item.type) '$($item.displayName)' ($itemId)"
        }
        catch {
            Write-Warning "  failed to delete $($item.type) '$($item.displayName)' ($itemId): $($_.Exception.Message)"
        }
    }
    Write-Output "RESET: Workspace wipe complete."
}

function Get-OrCreate-Workspace {
    param(
        [string]$DisplayName,
        [string]$Description,
        [string]$CapacityId,
        [string]$FabricToken
    )
    $list = Invoke-RestJson -Method "GET" -Url "https://api.fabric.microsoft.com/v1/workspaces" -AccessToken $FabricToken
    $existing = @($list.Body.value) | Where-Object { $_.displayName -eq $DisplayName } | Select-Object -First 1

    if ($existing) {
        return $existing
    }

    $payload = @{
        displayName = $DisplayName
        description = $Description
    }

    if ($CapacityId) {
        $payload.capacityId = $CapacityId
    }

    try {
        $created = Invoke-RestJson -Method "POST" -Url "https://api.fabric.microsoft.com/v1/workspaces" -AccessToken $FabricToken -Body $payload
    }
    catch {
        $msg = $_.Exception.Message
        if ($CapacityId -and ($msg -match "CapacityNotInActiveState" -or $msg -match "Target capacity is not in active state")) {
            Write-Warning "CapacityId $CapacityId was rejected as inactive. Retrying workspace creation without explicit capacity assignment."
            $payload.Remove("capacityId")
            $created = Invoke-RestJson -Method "POST" -Url "https://api.fabric.microsoft.com/v1/workspaces" -AccessToken $FabricToken -Body $payload
        }
        else {
            throw
        }
    }

    $result = Wait-LroIfNeeded -Response $created -AccessToken $FabricToken

    if ($result -and ($result.PSObject.Properties.Name -contains "id") -and $result.id) {
        return $result
    }

    # Fallback lookup after async creation.
    $refresh = Invoke-RestJson -Method "GET" -Url "https://api.fabric.microsoft.com/v1/workspaces" -AccessToken $FabricToken
    $found = @($refresh.Body.value) | Where-Object { $_.displayName -eq $DisplayName } | Select-Object -First 1
    if (-not $found) {
        throw "Workspace creation response did not include id and workspace could not be found by name: $DisplayName"
    }
    return $found
}

function Get-OrCreate-Lakehouse {
    param(
        [string]$WorkspaceId,
        [string]$DisplayName,
        [string]$Description,
        [string]$FabricToken
    )

    $items = Invoke-RestJson -Method "GET" -Url "https://api.fabric.microsoft.com/v1/workspaces/$WorkspaceId/items" -AccessToken $FabricToken
    $existing = @($items.Body.value) | Where-Object { $_.type -eq "Lakehouse" -and $_.displayName -eq $DisplayName } | Select-Object -First 1

    if ($existing) {
        return $existing
    }

    $payload = @{
        displayName = $DisplayName
        description = $Description
        type = "Lakehouse"
        creationPayload = @{
            enableSchemas = $false
        }
    }

    $created = Invoke-RestJson -Method "POST" -Url "https://api.fabric.microsoft.com/v1/workspaces/$WorkspaceId/items" -AccessToken $FabricToken -Body $payload
    $result = Wait-LroIfNeeded -Response $created -AccessToken $FabricToken

    if ($result -and ($result.PSObject.Properties.Name -contains "id") -and $result.id) {
        return $result
    }

    $refresh = Invoke-RestJson -Method "GET" -Url "https://api.fabric.microsoft.com/v1/workspaces/$WorkspaceId/items" -AccessToken $FabricToken
    $found = @($refresh.Body.value) | Where-Object { $_.type -eq "Lakehouse" -and $_.displayName -eq $DisplayName } | Select-Object -First 1
    if (-not $found) {
        throw "Lakehouse creation response did not include id and item could not be found by name: $DisplayName"
    }
    return $found
}

function Get-OrCreate-DeploymentPipeline {
    param(
        [string]$DisplayName,
        [string]$Description,
        [string]$PowerBiToken
    )

    $list = Invoke-RestJson -Method "GET" -Url "https://api.powerbi.com/v1.0/myorg/pipelines" -AccessToken $PowerBiToken
    $existing = @($list.Body.value) | Where-Object { $_.displayName -eq $DisplayName } | Select-Object -First 1
    if ($existing) {
        return $existing
    }

    $payload = @{
        displayName = $DisplayName
        description = $Description
    }

    $created = Invoke-RestJson -Method "POST" -Url "https://api.powerbi.com/v1.0/myorg/pipelines" -AccessToken $PowerBiToken -Body $payload
    return $created.Body
}

function Set-WorkspaceToPipelineStage {
    param(
        [string]$PipelineId,
        [int]$StageOrder,
        [string]$WorkspaceId,
        [string]$PowerBiToken
    )

    $stages = Invoke-RestJson -Method "GET" -Url "https://api.powerbi.com/v1.0/myorg/pipelines/$PipelineId/stages" -AccessToken $PowerBiToken
    $targetStage = @($stages.Body.value) | Where-Object { $_.order -eq $StageOrder } | Select-Object -First 1
    if ($targetStage -and ($targetStage.PSObject.Properties.Name -contains "workspaceId") -and $targetStage.workspaceId) {
        if ([string]$targetStage.workspaceId -eq [string]$WorkspaceId) {
            return "already_assigned"
        }
        return "stage_occupied"
    }

    $payload = @{ workspaceId = $WorkspaceId }

    try {
        Invoke-RestJson -Method "POST" -Url "https://api.powerbi.com/v1.0/myorg/pipelines/$PipelineId/stages/$StageOrder/assignWorkspace" -AccessToken $PowerBiToken -Body $payload | Out-Null
        return "assigned"
    }
    catch {
        $msg = $_.Exception.Message
        if ($msg -match "already" -or $msg -match "Conflict" -or $msg -match "409" -or $msg -match "StageAlreadyHasWorkspace" -or $msg -match "Alm_InvalidRequest_StageAlreadyHasWorkspace") {
            return "already_assigned"
        }
        throw
    }
}

function Get-OrCreate-Notebook {
    param(
        [string]$WorkspaceId,
        [string]$LakehouseId,
        [string]$LakehouseName,
        [string]$NotebookPath,
        [string]$NotebookDisplayName,
        [object[]]$KnownLakehouses,
        [string]$FabricToken
    )

    if (-not (Test-Path $NotebookPath)) {
        Write-Warning "Notebook file not found at: $NotebookPath. Skipping notebook creation."
        return $null
    }

    $items = Invoke-RestJson -Method "GET" -Url "https://api.fabric.microsoft.com/v1/workspaces/$WorkspaceId/items" -AccessToken $FabricToken
    $existing = @($items.Body.value) | Where-Object { $_.type -eq "Notebook" -and $_.displayName -eq $NotebookDisplayName } | Select-Object -First 1
    
    $notebookItem = $null
    if ($existing) {
        Write-Host "Notebook already exists: $NotebookDisplayName (ID: $($existing.id))" -ForegroundColor Green
        $notebookItem = $existing
    }
    else {
        $payload = @{
            displayName = $NotebookDisplayName
            description = "Geohazard medallion notebook for Fabric CI/CD demo - Lakehouse: $LakehouseName ($LakehouseId)"
            type = "Notebook"
        }

        $created = Invoke-RestJson -Method "POST" -Url "https://api.fabric.microsoft.com/v1/workspaces/$WorkspaceId/items" -AccessToken $FabricToken -Body $payload
        $notebookItem = $created.Body

        if ($notebookItem -and $notebookItem.id) {
            Write-Host "Notebook created: $($notebookItem.displayName) (ID: $($notebookItem.id))" -ForegroundColor Green
        }
        else {
            Write-Warning "Notebook creation response did not include expected fields."
            return $null
        }
    }

    try {
        $notebookContent = Get-Content $NotebookPath -Raw
        $notebookJson = $notebookContent | ConvertFrom-Json

        # Fabric only overrides notebook values declared in a parameters-tagged cell.
        $parameterCells = @(
            @($notebookJson.cells) | Where-Object {
                $cellSource = $_.source -join "`n"
                $hasAoiParameters =
                    $cellSource -match '(?m)^LATITUDE\s*=' -and
                    $cellSource -match '(?m)^LONGITUDE\s*=' -and
                    $cellSource -match '(?m)^RADIUS_KM\s*='
                $hasRunIdParameter = $cellSource -match '(?m)^PIPELINE_RUN_ID\s*='

                $_.cell_type -eq "code" -and ($hasAoiParameters -or $hasRunIdParameter)
            }
        )

        if ($parameterCells.Count -gt 1) {
            throw "Notebook '$NotebookDisplayName' has multiple AOI parameter cells. Keep exactly one defaults-only cell."
        }

        $parameterCell = $parameterCells | Select-Object -First 1

        if ($parameterCell) {
            if (-not $parameterCell.metadata) {
                $parameterCell | Add-Member -NotePropertyName metadata -NotePropertyValue ([PSCustomObject]@{}) -Force
            }
            $tags = @()
            if ($parameterCell.metadata.PSObject.Properties.Name -contains "tags") {
                $tags = @($parameterCell.metadata.tags)
            }
            if ($tags -notcontains "parameters") {
                $tags += "parameters"
            }
            $parameterCell.metadata | Add-Member -NotePropertyName tags -NotePropertyValue $tags -Force
            Write-Host "  Marked AOI configuration cell as a Fabric parameter cell" -ForegroundColor DarkGray
        }

        # Inject/overwrite the default lakehouse binding so relative saveAsTable / spark.read.table
        # calls resolve to the correct medallion layer (bronze/silver/gold) when run headless.
        if ($LakehouseId) {
            $knownLakehouseRefs = @()
            if ($KnownLakehouses) {
                foreach ($knownLakehouse in $KnownLakehouses) {
                    if ($knownLakehouse.id) {
                        $knownLakehouseRefs += [PSCustomObject]@{ id = [string]$knownLakehouse.id }
                    }
                }
            }
            if ($knownLakehouseRefs.Count -eq 0) {
                $knownLakehouseRefs = @([PSCustomObject]@{ id = $LakehouseId })
            }

            $lakehouseDep = [PSCustomObject]@{
                known_lakehouses               = $knownLakehouseRefs
                default_lakehouse              = $LakehouseId
                default_lakehouse_name         = $LakehouseName
                default_lakehouse_workspace_id = $WorkspaceId
            }
            $dependencies = [PSCustomObject]@{ lakehouse = $lakehouseDep }

            if (-not $notebookJson.metadata) {
                $notebookJson | Add-Member -NotePropertyName metadata -NotePropertyValue ([PSCustomObject]@{}) -Force
            }
            if ($notebookJson.metadata.PSObject.Properties.Name -contains "dependencies") {
                $notebookJson.metadata.dependencies = $dependencies
            }
            else {
                $notebookJson.metadata | Add-Member -NotePropertyName dependencies -NotePropertyValue $dependencies -Force
            }

            Write-Host "  Bound default lakehouse: $LakehouseName ($LakehouseId)" -ForegroundColor DarkGray
        }

        $notebookContent = $notebookJson | ConvertTo-Json -Depth 64

        $updatePayload = @{
            definition = @{
                format = "ipynb"
                parts = @(
                    @{
                        path = "notebook-content.ipynb"
                        payload = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($notebookContent))
                        payloadType = "InlineBase64"
                    }
                )
            }
        }

        $updateUrl = "https://api.fabric.microsoft.com/v1/workspaces/$WorkspaceId/items/$($notebookItem.id)/updateDefinition"
        Invoke-RestJson -Method "POST" -Url $updateUrl -AccessToken $FabricToken -Body $updatePayload | Out-Null
        Write-Host "Notebook content imported successfully" -ForegroundColor Green
    }
    catch {
        throw "Notebook content import failed for '$NotebookDisplayName' from '$NotebookPath': $($_.Exception.Message)"
    }

    return $notebookItem
}

function Get-OrCreate-DataPipeline {
    param(
        [string]$WorkspaceId,
        [string]$PipelinePath,
        [string]$PipelineDisplayName,
        [string]$ParameterPath,
        [hashtable]$NotebookIdByName,
        [string]$FabricToken
    )

    if (-not (Test-Path $PipelinePath)) {
        Write-Warning "Data pipeline file not found at: $PipelinePath. Skipping data pipeline creation."
        return $null
    }

    # Hydrate the portable pipeline template: resolve name-based tokens to the IDs
    # created in THIS workspace so the pipeline deploys unchanged to any tenant.
    $content = Get-Content $PipelinePath -Raw
    $content = $content -replace '\{\{WORKSPACE_ID\}\}', $WorkspaceId
    foreach ($name in $NotebookIdByName.Keys) {
        $token = '\{\{NOTEBOOK_ID:' + [regex]::Escape([string]$name) + '\}\}'
        $content = $content -replace $token, [string]$NotebookIdByName[$name]
    }

    $leftover = @(
        [regex]::Matches($content, '\{\{[^}]+\}\}') |
            ForEach-Object { $_.Value } |
            Sort-Object -Unique
    )
    if ($leftover.Count -gt 0) {
        throw "Data pipeline has unresolved tokens (no matching notebook was created): $($leftover -join ', ')"
    }

    if (-not [string]::IsNullOrWhiteSpace($ParameterPath)) {
        if (-not (Test-Path $ParameterPath)) {
            throw "Data pipeline parameter file not found: $ParameterPath"
        }

        $pipelineJson = $content | ConvertFrom-Json
        $parameterDefaults = Get-Content $ParameterPath -Raw | ConvertFrom-Json

        if ($parameterDefaults.PSObject.Properties.Name -contains "LATITUDE" -and
            (-not ([double]$parameterDefaults.LATITUDE -ge -90.0 -and [double]$parameterDefaults.LATITUDE -le 90.0))) {
            throw "LATITUDE in '$ParameterPath' must be between -90 and 90 degrees."
        }
        if ($parameterDefaults.PSObject.Properties.Name -contains "LONGITUDE" -and
            (-not ([double]$parameterDefaults.LONGITUDE -ge -180.0 -and [double]$parameterDefaults.LONGITUDE -le 180.0))) {
            throw "LONGITUDE in '$ParameterPath' must be between -180 and 180 degrees."
        }
        if ($parameterDefaults.PSObject.Properties.Name -contains "RADIUS_KM" -and
            (-not ([double]$parameterDefaults.RADIUS_KM -gt 0.0 -and [double]$parameterDefaults.RADIUS_KM -le 100.0))) {
            throw "RADIUS_KM in '$ParameterPath' must be greater than 0 and no more than 100 km."
        }
        if ($parameterDefaults.PSObject.Properties.Name -contains "ANALYSIS_RADIUS_KM" -and
            (-not ([double]$parameterDefaults.ANALYSIS_RADIUS_KM -gt 0.0 -and [double]$parameterDefaults.ANALYSIS_RADIUS_KM -le 5.0))) {
            throw "ANALYSIS_RADIUS_KM in '$ParameterPath' must be greater than 0 and no more than 5 km."
        }

        foreach ($parameterName in @($pipelineJson.properties.parameters.PSObject.Properties.Name)) {
            if ($parameterDefaults.PSObject.Properties.Name -contains $parameterName) {
                $pipelineJson.properties.parameters.$parameterName.defaultValue = $parameterDefaults.$parameterName
            }
        }
        $content = $pipelineJson | ConvertTo-Json -Depth 64
        Write-Host "Data pipeline defaults loaded from: $ParameterPath" -ForegroundColor DarkGray
    }

    $definition = @{
        parts = @(
            @{
                path        = "pipeline-content.json"
                payload     = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($content))
                payloadType = "InlineBase64"
            }
        )
    }

    $items = Invoke-RestJson -Method "GET" -Url "https://api.fabric.microsoft.com/v1/workspaces/$WorkspaceId/items" -AccessToken $FabricToken
    $existing = @($items.Body.value) | Where-Object { $_.type -eq "DataPipeline" -and $_.displayName -eq $PipelineDisplayName } | Select-Object -First 1

    if ($existing) {
        $updateUrl = "https://api.fabric.microsoft.com/v1/workspaces/$WorkspaceId/items/$($existing.id)/updateDefinition"
        Invoke-RestJson -Method "POST" -Url $updateUrl -AccessToken $FabricToken -Body @{ definition = $definition } | Out-Null
        Write-Host "Data pipeline updated: $PipelineDisplayName (ID: $($existing.id))" -ForegroundColor Green
        return $existing
    }

    $payload = @{
        displayName = $PipelineDisplayName
        type        = "DataPipeline"
        definition  = $definition
    }
    $created = Invoke-RestJson -Method "POST" -Url "https://api.fabric.microsoft.com/v1/workspaces/$WorkspaceId/items" -AccessToken $FabricToken -Body $payload
    $pipelineItem = $created.Body
    if ($pipelineItem -and $pipelineItem.id) {
        Write-Host "Data pipeline created: $($pipelineItem.displayName) (ID: $($pipelineItem.id))" -ForegroundColor Green
    }
    else {
        Write-Warning "Data pipeline creation response did not include expected fields."
    }
    return $pipelineItem
}

if (-not (Test-Path $ConfigPath)) {
    throw "Config file not found: $ConfigPath"
}

$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
$fabricToken = Get-AzAccessTokenValue -Resource "https://api.fabric.microsoft.com"
$powerBiToken = Get-AzAccessTokenValue -Resource "https://analysis.windows.net/powerbi/api"

$capacityId = [string]$config.capacityId
if ([string]::IsNullOrWhiteSpace($capacityId)) {
    $capacityId = Get-Active-CapacityId -FabricToken $fabricToken
}

if ([string]::IsNullOrWhiteSpace($capacityId)) {
    Write-Warning "No active capacity was auto-detected. Workspace creation will proceed without explicit capacityId."
}
else {
    Write-Output "Using capacityId: $capacityId"
}

$workspaceName = [string]$config.workspaceName
if ([string]::IsNullOrWhiteSpace($workspaceName)) {
    $workspacePrefix = [string]$config.workspacePrefix
    if (-not [string]::IsNullOrWhiteSpace($workspacePrefix)) {
        $workspaceName = "$workspacePrefix-dev"
    }
}

if ([string]::IsNullOrWhiteSpace($workspaceName)) {
    throw "Config must provide workspaceName (or legacy workspacePrefix)."
}

$workspaceDescription = [string]$config.workspaceDescription
$workspace = Get-OrCreate-Workspace -DisplayName $workspaceName -Description $workspaceDescription -CapacityId $capacityId -FabricToken $fabricToken

if ($Reset) {
    Remove-AllWorkspaceItems -WorkspaceId $workspace.id -FabricToken $fabricToken
}

$lakehouseResults = @()
$primaryLakehouseId = ""
foreach ($lh in $config.lakehouses) {
    $lakehouse = Get-OrCreate-Lakehouse -WorkspaceId $workspace.id -DisplayName ([string]$lh.displayName) -Description ([string]$lh.description) -FabricToken $fabricToken
    $lakehouseResults += [PSCustomObject]@{
        displayName = $lakehouse.displayName
        id = $lakehouse.id
        type = $lakehouse.type
    }
    if ([string]::IsNullOrWhiteSpace($primaryLakehouseId)) {
        $primaryLakehouseId = $lakehouse.id
    }
}

$notebookResults = @()
if ($config.PSObject.Properties.Name -contains "notebooks" -and $config.notebooks -and $primaryLakehouseId) {
    # name -> id lookup so each notebook can bind to its own medallion-layer lakehouse
    $lakehouseByName = @{}
    foreach ($lhr in $lakehouseResults) { $lakehouseByName[[string]$lhr.displayName] = [string]$lhr.id }

    foreach ($nb in $config.notebooks) {
        $notebookPath = [string]$nb.localPath
        $notebookName = [string]$nb.displayName
        $absolutePath = Join-Path (Get-Location) $notebookPath

        # Resolve the notebook's default lakehouse (config "lakehouse" name), fall back to the primary (bronze)
        $targetLakehouseName = if ($nb.PSObject.Properties.Name -contains "lakehouse" -and $nb.lakehouse) { [string]$nb.lakehouse } else { "" }
        $targetLakehouseId = if ($targetLakehouseName -and $lakehouseByName.ContainsKey($targetLakehouseName)) { $lakehouseByName[$targetLakehouseName] } else { $primaryLakehouseId }
        if (-not $targetLakehouseName) {
            $targetLakehouseName = ($lakehouseResults | Where-Object { $_.id -eq $targetLakehouseId } | Select-Object -First 1).displayName
        }

        $notebook = Get-OrCreate-Notebook -WorkspaceId $workspace.id -LakehouseId $targetLakehouseId -LakehouseName $targetLakehouseName -NotebookPath $absolutePath -NotebookDisplayName $notebookName -KnownLakehouses $lakehouseResults -FabricToken $fabricToken
        if ($notebook -and ($notebook.PSObject.Properties.Name -contains "displayName")) {
            $notebookResults += [PSCustomObject]@{
                displayName = [string]$notebook.displayName
                id = [string]$notebook.id
                type = [string]$notebook.type
                lakehouse = $targetLakehouseName
            }
        }
    }
}

$workspaceResult = [PSCustomObject]@{
    workspaceName = $workspace.displayName
    workspaceId = $workspace.id
    capacityId = $workspace.capacityId
    lakehouses = $lakehouseResults
    notebooks = $notebookResults
}

# Hydrate + deploy the portable bronze orchestration data pipeline (name-based tokens
# -> IDs created in this workspace). Optional: skipped if no dataPipeline config block.
$dataPipelineResult = $null
if ($config.PSObject.Properties.Name -contains "dataPipeline" -and $config.dataPipeline) {
    $notebookIdByName = @{}
    foreach ($nbr in $notebookResults) { $notebookIdByName[[string]$nbr.displayName] = [string]$nbr.id }

    $dpCfg  = $config.dataPipeline
    $dpPath = Join-Path (Get-Location) ([string]$dpCfg.localPath)
    $parameterPath = ""
    if ($dpCfg.PSObject.Properties.Name -contains "parametersPath" -and $dpCfg.parametersPath) {
        $parameterPath = Join-Path (Get-Location) ([string]$dpCfg.parametersPath)
    }
    $dataPipeline = Get-OrCreate-DataPipeline -WorkspaceId $workspace.id -PipelinePath $dpPath -PipelineDisplayName ([string]$dpCfg.displayName) -ParameterPath $parameterPath -NotebookIdByName $notebookIdByName -FabricToken $fabricToken
    if ($dataPipeline -and $dataPipeline.id) {
        $dataPipelineResult = [PSCustomObject]@{
            displayName = [string]$dataPipeline.displayName
            id = [string]$dataPipeline.id
            type = "DataPipeline"
        }
    }
}

$pipelineCfg = $config.deploymentPipeline
$pipeline = Get-OrCreate-DeploymentPipeline -DisplayName ([string]$pipelineCfg.displayName) -Description ([string]$pipelineCfg.description) -PowerBiToken $powerBiToken

$stage0State = Set-WorkspaceToPipelineStage -PipelineId $pipeline.id -StageOrder 0 -WorkspaceId $workspaceResult.workspaceId -PowerBiToken $powerBiToken

$output = [PSCustomObject]@{
    generatedAtUtc = (Get-Date).ToUniversalTime().ToString("o")
    workspaceName = $workspaceName
    capacityId = $capacityId
    deploymentPipeline = [PSCustomObject]@{
        id = $pipeline.id
        displayName = $pipeline.displayName
    }
    dataPipeline = $dataPipelineResult
    workspace = $workspaceResult
    stage0Assignment = [PSCustomObject]@{
        stageOrder = 0
        workspaceName = $workspaceResult.workspaceName
        workspaceId = $workspaceResult.workspaceId
        status = $stage0State
    }
    note = "Single-workspace demo mode: stage 0 is assigned. To perform actual cross-stage deployment, assign additional workspaces to later stages."
}

$output | ConvertTo-Json -Depth 50 | Set-Content -Path $OutputPath -Encoding utf8
Write-Output "Fabric setup completed. Output saved to: $OutputPath"
Write-Output ($output | ConvertTo-Json -Depth 50)
