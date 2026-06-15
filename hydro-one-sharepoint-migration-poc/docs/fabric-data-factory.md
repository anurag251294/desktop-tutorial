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

## Deploy to a Fabric workspace

Sign in with Azure CLI using an account that has Contributor access to the Fabric workspace:

```powershell
az login
.\scripts\Deploy-FDF-Templates.ps1 -WorkspaceId "<fabric-workspace-guid>"
```

To preview create/update actions without calling Fabric:

```powershell
.\scripts\Deploy-FDF-Templates.ps1 -WorkspaceId "<fabric-workspace-guid>" -WhatIf
```

## What the converter changes

- Extracts ADF pipeline `properties` into Fabric `pipeline-content.json`.
- Generates Fabric `.platform` metadata with item type `DataPipeline`.
- Inlines ADF dataset references into Fabric activity `datasetSettings`.
- Replaces mapped ADF linked services with Fabric `externalReferences.connection`.
- Keeps unmapped linked service references and records them in `conversion-report.json`.

## Manual Fabric prerequisites

Fabric connections are workspace-level objects, not ADF linked services. Create Fabric connections for SQL, ADLS/Blob, HTTP/Graph, and Key Vault before deployment, then map their connection GUIDs in `config\fdf-connections.json`.

The SQL schema scripts and SharePoint inventory scripts are unchanged. They still create and populate the migration control tables used by the pipelines.
