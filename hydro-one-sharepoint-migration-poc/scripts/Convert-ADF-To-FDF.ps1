<#
.SYNOPSIS
    Converts ADF ARM pipeline templates into Microsoft Fabric Data Factory
    DataPipeline item-definition folders.

.DESCRIPTION
    Fabric Data Factory (FDF) does not deploy through Azure Resource Manager.
    Pipelines are Fabric workspace items whose definitions are uploaded through
    the Fabric REST API. This script extracts the pipeline resources from the
    repo's ADF ARM templates and writes Fabric-compatible item folders:

        fdf-templates\pipelines\<pipeline>.DataPipeline\
            pipeline-content.json
            .platform

    Dataset references are inlined into activity datasetSettings where Fabric
    expects them. If a connection map is supplied, ADF linked-service references
    are replaced with Fabric connection externalReferences.

.PARAMETER SourceTemplateDir
    Path to the ADF template folder. Defaults to adf-templates.

.PARAMETER OutputDir
    Path for generated Fabric item-definition folders. Defaults to fdf-templates.

.PARAMETER ConnectionMapPath
    Optional JSON file mapping ADF linked service names to Fabric connection IDs.
    Example:
      {
        "LS_AzureSqlDatabase": "<fabric-sql-connection-guid>",
        "LS_ADLS_Gen2": "<fabric-adls-connection-guid>",
        "LS_HTTP_Graph_Download": "<fabric-http-connection-guid>"
      }

.PARAMETER Clean
    Deletes the existing output directory before conversion.

.EXAMPLE
    .\scripts\Convert-ADF-To-FDF.ps1 -Clean

.EXAMPLE
    .\scripts\Convert-ADF-To-FDF.ps1 -ConnectionMapPath .\config\fdf-connections.sample.json -Clean
#>
[CmdletBinding()]
param(
    [string]$SourceTemplateDir = "adf-templates",
    [string]$OutputDir = "fdf-templates",
    [string]$ConnectionMapPath,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

function Read-JsonFile {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path $Path)) {
        throw "File not found: $Path"
    }
    # Note: ConvertFrom-Json has no -Depth parameter on Windows PowerShell 5.1
    # (only PowerShell 7+). 5.1 parses arbitrarily deep JSON by default, so we
    # omit it here to stay compatible with the stock client environment.
    return Get-Content -Raw -Path $Path | ConvertFrom-Json
}

function Write-JsonFile {
    param(
        [Parameter(Mandatory = $true)]$InputObject,
        [Parameter(Mandatory = $true)][string]$Path,
        [switch]$UnescapeArm
    )
    $json = $InputObject | ConvertTo-Json -Depth 100
    if ($UnescapeArm) {
        # ARM templates escape a literal leading '[' as '[[' (e.g. a stored
        # procedure name "[[dbo].[usp_X]" deploys to the literal "[dbo].[usp_X]").
        # Fabric pipeline definitions are NOT ARM, so the escaping must be undone.
        # A JSON string value that opens with "[[ is always such an escape: an
        # embedded double-quote would be backslash-escaped, so the sequence "[[
        # can only mark start-of-value followed by an ARM-escaped bracket.
        $json = $json -replace '"\[\[', '"['
    }
    Set-Content -Path $Path -Value $json -Encoding UTF8
}

function Copy-JsonObject {
    param([Parameter(Mandatory = $true)]$InputObject)
    return ($InputObject | ConvertTo-Json -Depth 100 | ConvertFrom-Json)
}

function Get-ObjectPropertyValue {
    param($Object, [string]$Name)
    if ($null -eq $Object -or -not ($Object.PSObject.Properties.Name -contains $Name)) {
        return $null
    }
    return $Object.$Name
}

function Remove-ObjectProperty {
    param($Object, [string]$Name)
    if ($null -ne $Object -and ($Object.PSObject.Properties.Name -contains $Name)) {
        $Object.PSObject.Properties.Remove($Name)
    }
}

function Add-OrReplaceProperty {
    param($Object, [string]$Name, $Value)
    Remove-ObjectProperty -Object $Object -Name $Name
    $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
}

function New-StableGuid {
    param([Parameter(Mandatory = $true)][string]$Value)

    $md5 = [System.Security.Cryptography.MD5]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes("hydro-one-sharepoint-migration-poc:fdf:$Value")
        $hash = $md5.ComputeHash($bytes)
        $hash[6] = ($hash[6] -band 0x0f) -bor 0x30
        $hash[8] = ($hash[8] -band 0x3f) -bor 0x80
        return ([guid]::new($hash)).ToString()
    }
    finally {
        $md5.Dispose()
    }
}

function Get-ResourceName {
    param([Parameter(Mandatory = $true)]$Resource)

    $name = [string]$Resource.name
    $match = [regex]::Match($name, "'/([^']+)'\)\]$")
    if ($match.Success) {
        return $match.Groups[1].Value
    }

    if ($name.Contains("/")) {
        return ($name -split "/")[-1]
    }

    return $name
}

function Get-ResourceMap {
    param([Parameter(Mandatory = $true)][string]$Directory)

    $map = @{}
    if (-not (Test-Path $Directory)) {
        return $map
    }

    Get-ChildItem -Path $Directory -Filter "*.json" | ForEach-Object {
        $template = Read-JsonFile -Path $_.FullName
        foreach ($resource in @($template.resources)) {
            $resourceName = Get-ResourceName -Resource $resource
            $map[$resourceName] = $resource.properties
        }
    }
    return $map
}

function Resolve-ConnectionId {
    param([string]$LinkedServiceName)

    if ([string]::IsNullOrWhiteSpace($LinkedServiceName) -or -not $script:ConnectionMap) {
        return $null
    }

    $property = $script:ConnectionMap.PSObject.Properties[$LinkedServiceName]
    if ($property -and -not [string]::IsNullOrWhiteSpace([string]$property.Value)) {
        return [string]$property.Value
    }
    return $null
}

function Convert-LinkedServiceReference {
    param($Object)

    $linkedServiceName = Get-ObjectPropertyValue -Object $Object -Name "linkedServiceName"
    if ($null -eq $linkedServiceName) {
        return
    }

    $referenceName = Get-ObjectPropertyValue -Object $linkedServiceName -Name "referenceName"
    $connectionId = Resolve-ConnectionId -LinkedServiceName $referenceName
    if ($connectionId) {
        Remove-ObjectProperty -Object $Object -Name "linkedServiceName"
        Add-OrReplaceProperty -Object $Object -Name "externalReferences" -Value @{
            connection = $connectionId
        }
    }
    else {
        $script:Warnings.Add("No Fabric connection mapping supplied for linked service '$referenceName'. The generated definition keeps the ADF linkedServiceName reference.")
    }
}

function Convert-DatasetReference {
    param($DatasetReference)

    if ($null -eq $DatasetReference) {
        return $null
    }

    $referenceName = Get-ObjectPropertyValue -Object $DatasetReference -Name "referenceName"
    if ([string]::IsNullOrWhiteSpace($referenceName) -or -not $script:DatasetMap.ContainsKey($referenceName)) {
        $script:Warnings.Add("Dataset '$referenceName' was referenced but not found in $SourceTemplateDir\datasets.")
        return $DatasetReference
    }

    $datasetSettings = Copy-JsonObject -InputObject $script:DatasetMap[$referenceName]
    $parameters = Get-ObjectPropertyValue -Object $DatasetReference -Name "parameters"
    if ($null -ne $parameters) {
        Add-OrReplaceProperty -Object $datasetSettings -Name "parameters" -Value $parameters
    }

    Convert-LinkedServiceReference -Object $datasetSettings
    return $datasetSettings
}

function Convert-Activity {
    param([Parameter(Mandatory = $true)]$Activity)

    Convert-LinkedServiceReference -Object $Activity

    $typeProperties = Get-ObjectPropertyValue -Object $Activity -Name "typeProperties"
    if ($null -eq $typeProperties) {
        return
    }

    switch ([string]$Activity.type) {
        "Lookup" {
            $dataset = Get-ObjectPropertyValue -Object $typeProperties -Name "dataset"
            if ($null -ne $dataset) {
                Add-OrReplaceProperty -Object $typeProperties -Name "datasetSettings" -Value (Convert-DatasetReference -DatasetReference $dataset)
                Remove-ObjectProperty -Object $typeProperties -Name "dataset"
            }
        }
        "Copy" {
            $inputs = @(Get-ObjectPropertyValue -Object $Activity -Name "inputs")
            $outputs = @(Get-ObjectPropertyValue -Object $Activity -Name "outputs")
            $source = Get-ObjectPropertyValue -Object $typeProperties -Name "source"
            $sink = Get-ObjectPropertyValue -Object $typeProperties -Name "sink"
            $destination = Get-ObjectPropertyValue -Object $typeProperties -Name "destination"

            if ($inputs.Count -gt 0 -and $null -ne $source) {
                Add-OrReplaceProperty -Object $source -Name "datasetSettings" -Value (Convert-DatasetReference -DatasetReference $inputs[0])
            }
            if ($outputs.Count -gt 0) {
                if ($null -ne $sink) {
                    Add-OrReplaceProperty -Object $sink -Name "datasetSettings" -Value (Convert-DatasetReference -DatasetReference $outputs[0])
                }
                elseif ($null -ne $destination) {
                    Add-OrReplaceProperty -Object $destination -Name "datasetSettings" -Value (Convert-DatasetReference -DatasetReference $outputs[0])
                }
            }

            Remove-ObjectProperty -Object $Activity -Name "inputs"
            Remove-ObjectProperty -Object $Activity -Name "outputs"
        }
    }

    foreach ($propertyName in @("activities", "ifTrueActivities", "ifFalseActivities", "cases", "defaultActivities")) {
        $value = Get-ObjectPropertyValue -Object $typeProperties -Name $propertyName
        if ($null -eq $value) {
            continue
        }

        if ($propertyName -eq "cases") {
            foreach ($case in @($value)) {
                foreach ($nestedActivity in @(Get-ObjectPropertyValue -Object $case -Name "activities")) {
                    Convert-Activity -Activity $nestedActivity
                }
            }
        }
        else {
            foreach ($nestedActivity in @($value)) {
                Convert-Activity -Activity $nestedActivity
            }
        }
    }
}

function Convert-PipelineTemplate {
    param(
        [Parameter(Mandatory = $true)][string]$TemplatePath,
        [Parameter(Mandatory = $true)][string]$PipelinesOutputDir
    )

    $template = Read-JsonFile -Path $TemplatePath
    $pipelineResources = @($template.resources | Where-Object { $_.type -like "*pipelines" })
    if ($pipelineResources.Count -eq 0) {
        throw "No pipeline resource found in $TemplatePath"
    }

    foreach ($resource in $pipelineResources) {
        $pipelineName = Get-ResourceName -Resource $resource
        $pipelineProperties = Copy-JsonObject -InputObject $resource.properties
        foreach ($activity in @(Get-ObjectPropertyValue -Object $pipelineProperties -Name "activities")) {
            Convert-Activity -Activity $activity
        }

        $itemDir = Join-Path $PipelinesOutputDir "$pipelineName.DataPipeline"
        New-Item -ItemType Directory -Path $itemDir -Force | Out-Null

        $content = @{
            properties = $pipelineProperties
        }
        Write-JsonFile -InputObject $content -Path (Join-Path $itemDir "pipeline-content.json") -UnescapeArm

        $platform = @{
            version = "2.0"
            '$schema' = "https://developer.microsoft.com/json-schemas/fabric/platform/platformProperties.json"
            config = @{
                logicalId = New-StableGuid -Value $pipelineName
            }
            metadata = @{
                type = "DataPipeline"
                displayName = $pipelineName
                description = [string](Get-ObjectPropertyValue -Object $pipelineProperties -Name "description")
            }
        }
        Write-JsonFile -InputObject $platform -Path (Join-Path $itemDir ".platform")

        Write-Host "Converted $pipelineName -> $itemDir" -ForegroundColor Green
    }
}

$SourceTemplateDir = (Resolve-Path $SourceTemplateDir).Path
$OutputDirFull = if (Test-Path $OutputDir) { (Resolve-Path $OutputDir).Path } else { $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDir) }

if ($ConnectionMapPath) {
    $script:ConnectionMap = Read-JsonFile -Path $ConnectionMapPath
}
else {
    $script:ConnectionMap = $null
}

$script:Warnings = [System.Collections.Generic.List[string]]::new()
$script:DatasetMap = Get-ResourceMap -Directory (Join-Path $SourceTemplateDir "datasets")

if ($Clean -and (Test-Path $OutputDirFull)) {
    Remove-Item -Path $OutputDirFull -Recurse -Force
}

$pipelinesOutputDir = Join-Path $OutputDirFull "pipelines"
New-Item -ItemType Directory -Path $pipelinesOutputDir -Force | Out-Null

Get-ChildItem -Path (Join-Path $SourceTemplateDir "pipelines") -Filter "*.json" |
    Sort-Object Name |
    ForEach-Object { Convert-PipelineTemplate -TemplatePath $_.FullName -PipelinesOutputDir $pipelinesOutputDir }

$report = [ordered]@{
    sourceTemplateDir = $SourceTemplateDir
    outputDir = $OutputDirFull
    generatedAtUtc = (Get-Date).ToUniversalTime().ToString("o")
    pipelineCount = (Get-ChildItem -Path $pipelinesOutputDir -Directory -Filter "*.DataPipeline").Count
    warnings = @($script:Warnings | Sort-Object -Unique)
}
Write-JsonFile -InputObject $report -Path (Join-Path $OutputDirFull "conversion-report.json")

if ($script:Warnings.Count -gt 0) {
    Write-Host ""
    Write-Host "Conversion completed with warnings. Review fdf-templates\conversion-report.json." -ForegroundColor Yellow
}
else {
    Write-Host ""
    Write-Host "Conversion completed with no warnings." -ForegroundColor Green
}
