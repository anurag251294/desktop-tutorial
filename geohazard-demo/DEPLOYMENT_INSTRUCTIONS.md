---
title: Fabric Deployment Instructions
description: Provision and run the complete Maple Ridge geohazard medallion pipeline
ms.date: 2026-08-04
ms.topic: how-to
---

Deploy all geohazard notebooks, lakehouses, and the parameterized Fabric pipeline, then
run the bronze, silver, and gold workflow once with the Maple Ridge defaults.

Everything here is idempotent. The setup script
finds-or-creates each item, re-uploads the latest notebook content, and binds every
notebook to its correct medallion lakehouse.

---

## What gets deployed

| Layer | Lakehouse | Notebooks |
| --- | --- | --- |
| Bronze | `bronze_lakehouse` | `bronze_pc_collections`, `bronze_planetary_ingestion`, `bronze_bc_surficial_geology`, `bronze_bc_soil_survey`, `bronze_data_overview` |
| Silver | `silver_lakehouse` | `silver_rf1_soil_susceptibility` |
| Gold | `gold_lakehouse` | `gold_rf1_risk_matrix` |

* Workspace: `Englobecorp_Geohazard`
* Data pipeline: `pl_bronze_ingestion` (complete medallion orchestration)
* Deployment pipeline: `geohazard-demo-single-pipeline`

Each notebook's **default lakehouse binding is injected automatically** at deploy
time, so `saveAsTable` / `spark.read.table` calls land in the right layer even when
the notebooks are run headless.

---

## Prerequisites

1. **Azure CLI** signed in to the correct tenant:

   ```powershell
   az login --tenant 711a9076-1115-4c36-b7b4-82b4f3a05f6f
   az account show
   ```

2. **PowerShell 7+** (`pwsh`). Check with `$PSVersionTable.PSVersion`.

3. **Fabric capacity is running.** The capacity `cpfabric` (resource group
   `rg-fabric`) must be **Active** — a paused capacity will reject jobs.

   ```powershell
   # Resume the capacity (skip if already running)
   az fabric capacity resume --resource-group rg-fabric --capacity-name cpfabric
   ```

4. Run all commands from the **repo root**:

   ```powershell
   cd "c:\Users\chenalex\OneDrive - Microsoft\Documents\Microsoft Scout\OPS Fabric Workspace\geohazard-demo"
   ```

---

## Step 1 - Push All Fabric Items

This provisions the workspace, all three lakehouses, all seven notebooks with their
correct lakehouse bindings, the data pipeline, and the deployment pipeline. It writes
the resulting IDs to `cicd/fabric-setup.output.json`.

```powershell
pwsh ./scripts/fabric/setup_fabric_demo.ps1 `
  -ConfigPath ./cicd/fabric-setup.config.json `
  -OutputPath ./cicd/fabric-setup.output.json
```

**Expected output:** each lakehouse and notebook printed as created/updated, plus a
`Bound default lakehouse: <name> (<id>)` line per notebook confirming the binding.

> [!CAUTION]
> If you want a clean slate, add `-Reset`. This deletes every supported item in the
> workspace before rebuilding it. Use it only for a full re-provision.
>
> ```powershell
> pwsh ./scripts/fabric/setup_fabric_demo.ps1 -Reset
> ```

---

## Step 2 - Run the Complete Pipeline

`pl_bronze_ingestion` runs all seven activities. Four bronze ingestions run in
parallel. Overview and silver start after the ingestions succeed, and gold starts after
silver succeeds.

The setup script deploys these defaults from `cicd/parameters.dev.json`:

| Parameter | Default |
| ---------- | ------- |
| `LATITUDE` | `49.2193` |
| `LONGITUDE` | `-122.5984` |
| `RADIUS_KM` | `20` |
| `ANALYSIS_RADIUS_KM` | `3.0` |

The empty request body uses those Maple Ridge defaults. No additional parameter entry
is required.

```powershell
# Read the provisioned IDs
$state        = Get-Content ./cicd/fabric-setup.output.json -Raw | ConvertFrom-Json
$workspaceId  = $state.workspace.workspaceId
$token        = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv

# Read the hydrated pipeline ID written by the setup script
$pipelineId = [string]$state.dataPipeline.id
if (-not $pipelineId) { throw "The setup output has no data pipeline ID. Re-run Step 1." }

# Start the pipeline run
$runUri = "https://api.fabric.microsoft.com/v1/workspaces/$workspaceId/items/$pipelineId/jobs/instances?jobType=Pipeline"
$resp   = Invoke-WebRequest -Method Post -Uri $runUri -Headers @{ Authorization = "Bearer $token" } -ContentType "application/json" -Body "{}"
$jobUrl = $resp.Headers["Location"]; if ($jobUrl -is [array]) { $jobUrl = $jobUrl[0] }
Write-Host "Pipeline run accepted. Tracking: $jobUrl"

# Poll until terminal
do {
    Start-Sleep 15
    $token = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv
    $info  = Invoke-RestMethod -Uri $jobUrl -Headers @{ Authorization = "Bearer $token" }
    Write-Host "  status: $($info.status)"
} while ($info.status -notin @('Completed','Failed','Cancelled','Deduped'))
if ($info.status -ne 'Completed') {
  throw "Pipeline finished with status $($info.status): $($info.failureReason.message)"
}
Write-Host "PIPELINE FINISHED: Completed"
```

> If `pl_bronze_ingestion` is not found, re-run the setup script. It creates the
> pipeline and resolves its notebook tokens
> automatically. To import by hand instead, open the workspace in the Fabric portal,
> import `fabric/pipelines/pl_bronze_ingestion.json`, and replace the `{{WORKSPACE_ID}}`
> and `{{NOTEBOOK_ID:<name>}}` placeholders using the IDs in
> `cicd/fabric-setup.output.json`.

---

> [!TIP]
> Use `run_notebooks.ps1` only for targeted troubleshooting. For example:
>
> ```powershell
> pwsh ./scripts/fabric/run_notebooks.ps1 -Notebooks gold_rf1_risk_matrix
> ```

## Step 3 - Promote with the Deployment Pipeline

`geohazard-demo-single-pipeline` promotes whatever is currently in the workspace
stage. Because Steps 1 and 2 already pushed and ran the latest Fabric items, the
workspace, the deployment pipeline will pick them up. Trigger or review it in the
Fabric portal under **Workspace > Deployment pipelines**, or via the Power BI
pipelines REST API if you automate promotion between stages.

---

## Step 4 - Validate

* Open each lakehouse and confirm the bronze raw tables, the
  `silver_rf1_soil_susceptibility` table, and all four `gold_rf1_*` tables exist.
* Open any notebook and confirm its **Lakehouses** panel shows the matching medallion
  lakehouse as the default.
* Open **Workspace > Monitor** and confirm the pipeline run is `Completed` and all seven
  activities are `Succeeded`.
* Preview `gold_rf1_risk_pixels` and confirm `aoi_name` is
  `AOI 49.2193, -122.5984` for the default run.
* Open `gold_lakehouse/Files/gold_rf1_webmap/runs/<pipeline-run-id>/` and confirm the
  HTML map, GeoJSON, Shapefile ZIP, manifest, and `_SUCCESS` marker exist.

---

## Step 5 - Pause the Capacity

To stop incurring capacity cost after the demo:

```powershell
az fabric capacity suspend --resource-group rg-fabric --capacity-name cpfabric
```

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `401 / token` errors | Re-run `az login --tenant 711a9076-1115-4c36-b7b4-82b4f3a05f6f`. |
| Jobs rejected / stuck `NotStarted` | Capacity is paused. Run the `az fabric capacity resume` command in Prerequisites. |
| Spark session cancelled, table not found | The notebook lost its lakehouse binding. Re-run Step 1 to inject the correct default lakehouse. |
| Silver/gold wrote to the wrong lakehouse | Confirm the `lakehouse` field for that notebook in `cicd/fabric-setup.config.json`, then re-run Step 1. |
| Pipeline run is `Failed` | Open **Workspace > Monitor**, select the run, and inspect the failed activity and notebook snapshot. |

---

## One-shot sequence (copy/paste)

```powershell
cd "c:\Users\chenalex\OneDrive - Microsoft\Documents\Microsoft Scout\OPS Fabric Workspace\geohazard-demo"
az fabric capacity resume --resource-group rg-fabric --capacity-name cpfabric

# 1. Push everything
pwsh ./scripts/fabric/setup_fabric_demo.ps1 -ConfigPath ./cicd/fabric-setup.config.json -OutputPath ./cicd/fabric-setup.output.json

# 2. Run the complete Maple Ridge pipeline with the polling block from Step 2

# 3. Pause capacity after validation
az fabric capacity suspend --resource-group rg-fabric --capacity-name cpfabric
```
