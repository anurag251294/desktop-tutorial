---
title: Automated Deployment
description: Scripted deployment and end-to-end execution of the Microsoft Fabric geohazard demo
ms.date: 2026-08-04
ms.topic: tutorial
---

This is the **fast path**. You'll run a few copy-paste commands and the scripts do the
heavy lifting: creating the workspace, lakehouses, notebooks, and pipelines, then
running the data jobs for you.

> **Who this is for:** Someone who has never used Azure CLI, PowerShell, or Microsoft
> Fabric. Every step is spelled out. You do not need to understand the commands — just
> follow them in order.
>
> **Time needed:** about 30–45 minutes (most of it is waiting for jobs to finish).
>
> **Prefer clicking through a website instead of running commands?** Use the companion
> guide [DEPLOY_MANUAL.md](DEPLOY_MANUAL.md) instead.

---

## Vocabulary (read this once)

| Term | Plain-English meaning |
| --- | --- |
| **Microsoft Fabric** | The online data platform where everything runs. You'll see it in your browser. |
| **Workspace** | A folder in Fabric that holds all the demo's pieces. Ours is `Englobecorp_Geohazard`. |
| **Lakehouse** | Where the data tables are stored (bronze = raw, silver = cleaned, gold = final answers). |
| **Notebook** | A document of code cells that processes the data. |
| **Pipeline** | An automation that runs several notebooks in the right order. |
| **Capacity** | The rented compute power that runs the jobs. It costs money while it's **on**, so we turn it off at the end. |
| **Azure CLI / PowerShell** | Two tools you'll install that let you type commands to control Fabric. |

---

## Before you start — fill in YOUR details

The commands below contain a few values that are **different for every person**. Find
your values (ask your Azure/Fabric admin if you're not sure) and write them here so you
can copy them in as you go:

| Placeholder you'll see | Means | Your value (write it here) |
| --- | --- | --- |
| `<YOUR-TENANT-ID>` | Your organization's Azure tenant (directory) ID — looks like `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` | ____________________ |
| `<YOUR-RESOURCE-GROUP>` | The Azure resource group that holds the Fabric capacity | ____________________ |
| `<YOUR-CAPACITY-NAME>` | The name of the Fabric capacity (compute) | ____________________ |
| `<PATH-TO-PROJECT-FOLDER>` | The full folder path where this project lives on your computer | ____________________ |

> **How to use this:** wherever a command shows something in `<ANGLE BRACKETS>`, delete
> the brackets **and** the text inside, and type your own value in its place. For example,
> if your capacity is named `cpfabric`, then `--capacity-name <YOUR-CAPACITY-NAME>`
> becomes `--capacity-name cpfabric`.
>
> **Not sure where the project folder is?** In File Explorer, open the `geohazard-demo`
> folder, click the address bar at the top, and copy the full path shown there.

---

## Part 1 — One-time setup (only needed the first time)

You only do Part 1 once per computer. If you've done it before, skip to Part 2.

### 1.1 Install PowerShell 7

1. Open this page: <https://aka.ms/powershell-release?tag=stable>
2. Download the **`.msi`** installer for Windows (x64).
3. Run it and click **Next → Next → Install** with the default options.
4. When it finishes, open the **Start menu**, type **PowerShell 7**, and open it.
   A dark blue/black window appears. This is your "terminal" — you type commands here.

> Throughout this guide, "open a terminal" means open this **PowerShell 7** window.

### 1.2 Install the Azure CLI

1. Open this page: <https://aka.ms/installazurecliwindows>
2. Download and run the installer. Click **Next → Install** with defaults.
3. **Close and reopen** your PowerShell 7 window (so it picks up the new tool).
4. Check it worked — paste this and press **Enter**:

   ```powershell
   az --version
   ```

   If you see version numbers (not a red error), you're good.

### 1.3 Sign in to Azure

Paste this and press **Enter** (swap in your tenant ID first):

```powershell
az login --tenant <YOUR-TENANT-ID>
```

A browser window pops up. Sign in with your Microsoft work account. When it says you can
close the window, do so and return to the terminal.

> **Got an error or no browser?** Try `az login --tenant <YOUR-TENANT-ID> --use-device-code` and follow the on-screen instructions.

---

## Part 2 — Point the terminal at the project

Every time you open a fresh terminal, you must tell it which folder to work in. Paste
this line (keep the quotes) and press **Enter** — replace the path with your own folder:

```powershell
cd "<PATH-TO-PROJECT-FOLDER>"
```

> **Tip:** Nothing visible happens — that's normal. The text before your cursor should
> now end in `geohazard-demo>`.

---

## Part 3 — Turn the capacity on

The compute power (capacity) is usually left **off** to save money. Turn it on before
deploying (swap in your resource group and capacity name):

```powershell
az fabric capacity resume --resource-group <YOUR-RESOURCE-GROUP> --capacity-name <YOUR-CAPACITY-NAME>
```

Wait until it finishes (you get your cursor back). If it says it's already running,
that's fine — move on.

---

## Part 4 — Deploy everything (one command)

This single command builds the whole demo: the workspace, all three lakehouses, all
seven notebooks, the data pipeline, and the deployment pipeline. It is safe to run
more than once.

```powershell
pwsh ./scripts/fabric/setup_fabric_demo.ps1 -ConfigPath ./cicd/fabric-setup.config.json -OutputPath ./cicd/fabric-setup.output.json
```

**What you should see:** a stream of lines naming each lakehouse and notebook as
*created* or *updated*, and a `Bound default lakehouse: ...` line for each notebook.

**This takes a few minutes.** Wait for your cursor to come back before continuing.

> **Saw red errors mentioning `401` or `token`?** Your sign-in expired. Re-run the
> `az login` command from step 1.3, then run this command again.

---

## Part 5 - Run the Complete Pipeline Once

The `pl_bronze_ingestion` pipeline now runs the complete bronze, silver, and gold
workflow. One run starts all four bronze ingestions, builds the overview, calculates
silver soil susceptibility, and writes the gold risk outputs in dependency order.

The deployed defaults come from `cicd/parameters.dev.json`:

| Parameter | Default |
| ---------- | ------- |
| `LATITUDE` | `49.2193` |
| `LONGITUDE` | `-122.5984` |
| `RADIUS_KM` | `20` |
| `ANALYSIS_RADIUS_KM` | `3.0` |

These values select Maple Ridge, British Columbia. The request body below is empty, so
Fabric uses those defaults without asking you to fill in any run parameters.

Copy this entire block, paste it into the terminal, and press **Enter**. It starts the
full pipeline and checks its progress every 15 seconds until it finishes.

```powershell
$state       = Get-Content ./cicd/fabric-setup.output.json -Raw | ConvertFrom-Json
$workspaceId = [string]$state.workspace.workspaceId
$pipelineId  = [string]$state.dataPipeline.id
if (-not $pipelineId) { throw "The setup output does not contain a data pipeline ID. Run Part 4 again." }

$token  = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv
$runUri = "https://api.fabric.microsoft.com/v1/workspaces/$workspaceId/items/$pipelineId/jobs/instances?jobType=Pipeline"
$resp   = Invoke-WebRequest -Method Post -Uri $runUri -Headers @{ Authorization = "Bearer $token" } -ContentType "application/json" -Body "{}"
$jobUrl = $resp.Headers["Location"]; if ($jobUrl -is [array]) { $jobUrl = $jobUrl[0] }
Write-Host "Pipeline run started. Checking progress..."
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

Keep watching. You'll see `NotStarted` or `InProgress`, then finally
`PIPELINE FINISHED: Completed`. A normal run completes these seven activities:

1. `Ingest_PC_Collections`
2. `Ingest_Planetary`
3. `Ingest_BC_Geology`
4. `Ingest_BC_Soil_Survey`
5. `Build_Overview`
6. `Silver_Soil_Susceptibility`
7. `Gold_Risk_Matrix`

> [!NOTE]
> The first four activities run in parallel. Overview and silver start after all four
> ingestions succeed. Gold starts after silver succeeds.
>
> To test one notebook while troubleshooting, use
> `pwsh ./scripts/fabric/run_notebooks.ps1 -Notebooks <notebook-name>`. A normal demo
> run does not need separate silver or gold commands.

---

## Part 6 — Check your work in the browser

1. Go to <https://app.fabric.microsoft.com> and sign in with the same account.
2. On the left, open the workspace **`Englobecorp_Geohazard`**.
3. Open **`silver_lakehouse`**. Under **Tables**, confirm
   `silver_rf1_soil_susceptibility` exists.
4. Open **`gold_lakehouse`**. Under **Tables**, confirm these four tables exist:
   * `gold_rf1_risk_pixels`
   * `gold_rf1_risk_matrix`
   * `gold_rf1_band_summary`
   * `gold_rf1_risk_areas`
5. Under **Files**, open `gold_rf1_webmap/runs/<pipeline-run-id>/` and confirm the
   HTML map, GeoJSON, Shapefile ZIP, manifest, and `_SUCCESS` marker exist.

Open `gold_rf1_webmap.html` from the run folder to inspect the interactive map.

---

## Part 7 — Turn the capacity off (important — saves money)

When you're done, always turn the compute power back off:

```powershell
az fabric capacity suspend --resource-group <YOUR-RESOURCE-GROUP> --capacity-name <YOUR-CAPACITY-NAME>
```

---

## Repeat-Run Checklist

After the one-time setup, a repeat run uses these steps:

```powershell
cd "<PATH-TO-PROJECT-FOLDER>"
az fabric capacity resume --resource-group <YOUR-RESOURCE-GROUP> --capacity-name <YOUR-CAPACITY-NAME>
pwsh ./scripts/fabric/setup_fabric_demo.ps1 -ConfigPath ./cicd/fabric-setup.config.json -OutputPath ./cicd/fabric-setup.output.json
# Run the complete pipeline with the polling block from Part 5.
az fabric capacity suspend --resource-group <YOUR-RESOURCE-GROUP> --capacity-name <YOUR-CAPACITY-NAME>
```

---

## Troubleshooting

| What you see | What it means | What to do |
| --- | --- | --- |
| Red text with `401` or `token` | Your sign-in expired | Re-run the `az login` command (step 1.3), then retry. |
| `az` is not recognized | Azure CLI isn't installed or the terminal is stale | Finish step 1.2, then **close and reopen** PowerShell. |
| Jobs stuck on `NotStarted` | The capacity is off | Run the `resume` command (Part 3) and wait, then retry. |
| `pl_bronze_ingestion not found` | The pipeline isn't in the workspace yet | Re-run Part 4, then retry Part 5. |
| `Spark session cancelled` / `table not found` | A notebook lost its data binding | Re-run Part 4. It re-attaches the right lakehouse to every notebook. |
| The pipeline says `Failed` | One activity failed | Open **Workspace > Monitor**, select the pipeline run, and inspect the failed activity. |

---

## What's happening behind the scenes (optional reading)

* Part 4 calls a PowerShell script that uses the Fabric REST API to create each item
  if it doesn't already exist, uploads the latest notebook code, and pins the correct
  lakehouse to each notebook so the code knows where to read/write.
* Part 5 triggers one dependency-aware pipeline and repeatedly asks Fabric for its
   status until the complete medallion run reaches a final state.
* The file `cicd/fabric-setup.output.json` is written during Part 4 and remembers all the
  IDs so the later steps know what to run.
