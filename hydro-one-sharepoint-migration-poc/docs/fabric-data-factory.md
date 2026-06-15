# Fabric Data Factory deployment

This repo keeps the original ADF ARM templates under `adf-templates` and adds a Fabric Data Factory (FDF) conversion/deployment path under `fdf-templates`.

ADF deploys factories, linked services, datasets, and pipelines as ARM resources under `Microsoft.DataFactory`. Fabric Data Factory deploys data pipelines as Fabric workspace items through the Fabric REST API. The conversion therefore creates one Fabric `DataPipeline` item folder per ADF pipeline:

```text
fdf-templates/
  pipelines/
    PL_Copy_File_Batch.DataPipeline/
      pipeline-content.json
      .platform
```

## Requirements

Both scripts run on **Windows PowerShell 5.1** (the stock Windows shell) as well as PowerShell 7+. No `pwsh` install is required. `Convert-ADF-To-FDF.ps1` needs no Azure sign-in; `Deploy-FDF-Templates.ps1` uses Azure CLI (`az`) for its access token unless you pass `-AccessToken`.

## Convert ADF templates to FDF item definitions

From the project root:

```powershell
.\scripts\Convert-ADF-To-FDF.ps1 -Clean
```

If you already created Fabric connections, copy `config\fdf-connections.sample.json`, replace the placeholders with connection GUIDs, and pass it to the converter:

```powershell
Copy-Item .\config\fdf-connections.sample.json .\config\fdf-connections.json
# edit config\fdf-connections.json
.\scripts\Convert-ADF-To-FDF.ps1 -ConnectionMapPath .\config\fdf-connections.json -Clean
```

The converter writes `fdf-templates\conversion-report.json`. Review warnings before deployment, especially missing connection mappings.

> **Important:** Templates generated **without** a connection map import into Fabric but every Copy / Lookup / stored-procedure activity stays unbound and fails at run time. For a functional deployment you must create the Fabric connections first and re-run the converter with `-ConnectionMapPath`. `Deploy-FDF-Templates.ps1` warns when it detects unmapped `linkedServiceName` references.

## Deploy to a Fabric workspace

Sign in with Azure CLI using an account that has Contributor access to the Fabric workspace:

```powershell
az login
.\scripts\Deploy-FDF-Templates.ps1 -WorkspaceId "<fabric-workspace-guid>"
```

`-WhatIf` is a fully offline dry-run: it acquires no token and makes no Fabric calls, so the client can validate the generated templates locally before touching the workspace:

```powershell
.\scripts\Deploy-FDF-Templates.ps1 -WorkspaceId "<fabric-workspace-guid>" -WhatIf
```

Real create / `updateDefinition` calls are asynchronous (HTTP 202); the script polls each operation to completion and fails loudly if Fabric reports the operation failed.

## What the converter changes

- Extracts ADF pipeline `properties` into Fabric `pipeline-content.json`.
- Generates Fabric `.platform` metadata with item type `DataPipeline`.
- Inlines ADF dataset references into Fabric activity `datasetSettings`.
- Replaces mapped ADF linked services with Fabric `externalReferences.connection`.
- Keeps unmapped linked service references and records them in `conversion-report.json`.

## Manual Fabric prerequisites

Fabric connections are workspace-level objects, not ADF linked services. Create Fabric connections for SQL, ADLS/Blob, HTTP/Graph, and Key Vault before deployment, then map their connection GUIDs in `config\fdf-connections.json`.

The SQL schema scripts and SharePoint inventory scripts are unchanged. They still create and populate the migration control tables used by the pipelines.
