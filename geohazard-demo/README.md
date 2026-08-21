---
title: Geohazard Medallion Demo on Microsoft Fabric
description: Parameterized Microsoft Fabric geohazard screening demo with a Foundry report-agent and web-map architecture
ms.date: 2026-08-04
ms.topic: overview
---

> **Provenance.** Forked from [`yus-git/geohazard-demo`](https://github.com/yus-git/geohazard-demo)
> at branch `dev-pc-done` (commit `0634161`, 2026-08-05, Yusra Adil and Alex Acar).
>
> Added here: `silver_source_features`, source-feature identity carried through silver,
> `gold_rf1_risk_hotspots`, run scoping on every table, `agent_handoff_publisher`, a
> Fabric Environment replacing inline `%pip`, portable Python provisioning and run
> scripts, a published **Fabric data agent**, an end-to-end **Microsoft Foundry** report
> agent with schema-enforced output, and [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md). See
> [Grounding the report agent in the spatial data](#grounding-the-report-agent-in-the-spatial-data)
> and [The Foundry layer](#the-foundry-layer--turning-evidence-into-a-written-report) for why.
>
> One correctness fix travelled with the fork and is **still open upstream**: BC SIFT
> stores *coded* soil attributes (`DRAIN_1=W`, `MDEP_1=COLL`, `TEXTURE_1=SL`), which the
> original keyword scorer matched none of — so surveyed soil, the only direct ground
> truth, contributed a flat `0.4` constant. Decoding the codes moved the AOI from ~92%
> High/Extreme to Low 41 / Moderate 22 / High 33 / Extreme 3.8%, and split two merged
> blobs into 25 discrete attributed hotspots.

## Overview

An end-to-end **Microsoft Fabric + Microsoft Foundry** demo that ingests public
geospatial data, builds a **bronze → silver → gold** medallion pipeline for a geohazard
screening workflow, and hands the result to two AI agents: one that answers spatial
questions live, and one that writes a cited screening report. It shows realistic
data-engineering patterns (parameterized ingestion, Delta lakehouses, pipeline
orchestration) together with CI/CD controls (Git integration and a Fabric deployment
pipeline).

The point of the AI half is not that a model can write prose about data. It is that
**every number in the report is traceable to a row in a Delta table**, and that two
automated checks reject the document if it is not.

The default worked example is **RF-1 soft-soil susceptibility** over Maple Ridge,
British Columbia. A pipeline run can select another latitude, longitude, catalog
radius, and detailed analysis radius. Planetary Computer sources have broad coverage;
DataBC geology and soil layers are specific to British Columbia and can be empty for
other locations.

## Medallion architecture

| Layer | Notebook | Lakehouse | What it produces |
| --- | --- | --- | --- |
| **Bronze** | `bronze_pc_collections`, `bronze_bc_surficial_geology`, `bronze_bc_soil_survey`, `bronze_data_overview` | `bronze_lakehouse` | STAC item + WFS feature **metadata** (satellite, geology, soil survey) catalogued into Delta tables; folium overview maps |
| **Silver** | `silver_source_features` | `silver_lakehouse` | Bronze GeoJSON flattened to one queryable row per source feature: typed attributes, centroid, bbox, area, distance from AOI, plus per-source coverage status |
| **Silver** | `silver_rf1_soil_susceptibility` | `silver_lakehouse` | AOI pixels clipped to a 10 m grid; RF-1 factor metrics, surveyed soil ground truth, per-pixel S/C ratings, and the **source feature identity** each pixel sits on |
| **Gold** | `gold_rf1_risk_matrix` | `gold_lakehouse` | Risk tables, **ranked hotspots with spatial attribution**, dissolved risk-area polygons, GeoJSON/Shapefile exports, manifest, and interactive web map |
| **Gold** | `agent_handoff_publisher` | `gold_lakehouse` | Validated `report-input.json` evidence envelope for the Foundry report agent |

```text
bronze (catalogue metadata)  ─►  silver (flatten + clip + score)  ─►  gold (risk, hotspots)
                                                                        │
                                        ┌───────────────────────────────┴──────────────┐
                                        ▼                                              ▼
                          Fabric data agent (live Q&A)              handoff contract ─► Foundry report agent
```

Every table is partitioned by `run_id`, so one workspace can hold many screening runs
and every query — including the data agent's — can be scoped to a single run.

`bronze_planetary_ingestion` is a standalone single-collection ingestion demo
(`sentinel-2-l2a` → `bronze_satellite_stac_items`) kept for the simplest possible
parameterized-notebook example.

## Repo structure

```text
fabric/
  notebooks/
    bronze_pc_collections.ipynb          # Planetary Computer STAC → 7 bronze tables
    bronze_bc_surficial_geology.ipynb    # DataBC WFS → 3 bronze geology tables
    bronze_bc_soil_survey.ipynb          # DataBC WFS (SIFT) → bronze soil survey tables
    bronze_data_overview.ipynb           # reads bronze tables, renders folium maps
    bronze_planetary_ingestion.ipynb     # single-collection parameterized demo
    bronze_pc_sentinel1.ipynb            # Sentinel-1 RTC + GRD metadata (standalone)
    silver_source_features.ipynb         # flatten bronze GeoJSON → queryable features
    silver_rf1_soil_susceptibility.ipynb # clip + extract pixels, compute S/C ratings
    gold_rf1_risk_matrix.ipynb           # risk scoring, hotspots, exports, and web map
    agent_handoff_publisher.ipynb        # validated evidence envelope for the agent
  pipelines/
    pl_bronze_ingestion.json             # complete bronze, silver, and gold orchestration
cicd/
  fabric-setup.config.json              # provisioning inputs
  fabric-setup.output.json              # generated provisioning summary (IDs)
  parameters.dev.json / parameters.prod.json
  promotion-checklist.md
docs/
  data-sources.md                       # every external source, endpoint, and table
  workload-context-geohazard.md         # RF-1..RF-10 geohazard linkage
scripts/
  fabric/
    setup_fabric_demo.ps1               # provisions workspace, lakehouses, notebooks, pipelines
    provision_fabric_demo.py            # same provisioning, portable (Python + az CLI)
    run_pipeline.py                     # starts pl_bronze_ingestion and polls to completion
    run_notebooks.ps1                   # runs notebooks on demand
    harden_data_agent.py                # pins the canonical run, deselects geometry columns
  foundry/
    provision_foundry.py                # AI Services account, project, model deployment
    create_report_agent.py              # creates the report agent, generates and validates a report
agent-architecture/
  README.md                             # Foundry report + deterministic web-map design
  contracts/                            # strict report and map JSON Schemas
  prompts/                              # grounded report-agent system instructions
```

## Data sources

All sources are **public and anonymous** (no keys or token signing) and anchor on the
same Area of Interest. Only metadata/pixels are read on demand — underlying rasters are
not downloaded into bronze.

| Source | Protocol | Layers / collections | Notebook |
| --- | --- | --- | --- |
| Microsoft Planetary Computer STAC | `POST /search` | 7 collections (Sentinel-1/2, Copernicus DEM, ESA WorldCover, IO LULC, ALOS PALSAR, HGB) | `bronze_pc_collections` |
| BC DataBC (BC Geographic Warehouse) | WFS 2.0.0 `GetFeature` | Quaternary geology, bedrock, faults | `bronze_bc_surficial_geology` |
| BC DataBC — Soil Information Finder Tool (SIFT) | WFS 2.0.0 `GetFeature` | Soil survey polygons, project boundaries | `bronze_bc_soil_survey` |

Default AOI: Maple Ridge, BC, centre `49.2193, -122.5984`, 20 km bronze
catalog radius, and 3 km detailed analysis radius. Full details are in
`docs/data-sources.md`.

## Grounding the report agent in the spatial data

Bronze deliberately stores each WFS feature as verbatim `geometry_json` /
`properties_json`. That preserves raw fidelity, but neither SQL nor a Fabric data agent
can parse GeoJSON text — so bronze on its own cannot answer a spatial question. Three
things close that gap:

1. **`silver_source_features`** flattens every bronze vector feature once into typed,
   queryable columns — `drainage_class`, `parent_material`, `texture`, `rock_type`,
   `fault_type`, plus `centroid_lat/lon`, `area_km2`, and `distance_from_aoi_km`.
   Attributes are resolved by token-boundary matching against the real property keys, so
   a DataBC schema change degrades to nulls instead of breaking the run.
2. **Feature identity travels with the pixels.** Silver burns the soil and
   surficial-geology polygon indices onto the same 10 m grid as the risk score, so every
   pixel knows which mapped unit it sits on (`soil_poly_id`, `geology_poly_id`, joined
   through `silver_rf1_poly_lookup`).
3. **`gold_rf1_risk_hotspots`** clusters contiguous High/Extreme pixels into ranked,
   stably-identified features (`hs-001`, `hs-002`, …) and attaches the *why*: dominant
   soil unit and drainage class, surficial geology unit, land cover, mean slope, and the
   exact distance to the nearest mapped fault.

Together these let the agent answer questions the gold aggregates alone cannot:

* *Which soil units underlie the Extreme risk area, and how are they drained?*
* *What is the highest-ranked hotspot, and what is it sitting on?*
* *How far is the nearest mapped fault from hotspot `hs-003`?*
* *Which configured sources returned no records for this run?*
* *What surficial materials are mapped within 2 km of the AOI centre?*

`agent_handoff_publisher` then packages one run into the versioned
`report-input.json` contract — every number carrying an `evidenceId` — and refuses to
publish if the gold tables disagree on totals or any reference is malformed.

## The Foundry layer — turning evidence into a written report

Fabric produces the numbers. **Microsoft Foundry** writes the document. They are
deliberately separate, and the boundary between them is a versioned contract rather than
a prompt.

```mermaid
flowchart LR
  G[gold tables<br/>risk, hotspots, coverage] --> H[agent_handoff_publisher]
  H --> C["report-input.json<br/>64 evidence records, each with an evidenceId"]
  C --> F[Foundry<br/>geohazard-report-agent]
  F --> R["report-output.json<br/>cited, schema-validated"]
  G --> D[Fabric<br/>geohazard_data_agent]
  D -. "live questions" .-> U((analyst))
  R --> U
```

### Two agents, two jobs

| | `geohazard_data_agent` (Fabric) | `geohazard-report-agent` (Foundry) |
| --- | --- | --- |
| **Job** | Answer ad-hoc spatial questions, live | Write the screening report for one run |
| **Sees** | Six curated gold/silver tables over the SQL endpoint | Only the handoff contract — no pixels, no geometry, no raw bronze JSON |
| **Output** | Conversational answers with the source table named | One JSON document against a strict schema |
| **Runs on** | Fabric capacity (must be Active) | Foundry `gpt-5.4-mini` (no capacity needed) |

The data agent is scoped by *selection*: a table it has not been given is invisible to
it, so `agent-architecture/fabric-data-agent.md` is enforced rather than merely
documented. `scripts/fabric/harden_data_agent.py` also deselects `geometry_wkt`,
`properties_json`, and `geometry_json`, and names the canonical `run_id` so an
open-ended question cannot silently resolve to a superseded run.

### The handoff contract

`agent_handoff_publisher` packages one run into `report-input.json`. Every quantitative
value carries an **`evidenceId`** (`E1`, `E2`, …), and the publisher validates before
*and* after writing, writing `_SUCCESS` last — if the gold tables disagree on totals, the
run is quarantined and nothing is published.

What deliberately does **not** cross the boundary: pixel rows, geometry, and raw bronze
property JSON. The model receives a compact, bounded evidence envelope, which is what
makes the grounding claim checkable rather than aspirational.

### The report agent

`agent-architecture/prompts/report-agent-system.md` holds the system message. It forbids
the model from calculating risk, inventing geometry, estimating missing measurements, or
offering engineering advice — its only job is to explain supplied evidence. Output must
match `agent-architecture/contracts/geohazard-report-output.schema.json`:

| Field | Contents |
| --- | --- |
| `executiveSummary` | Cited prose |
| `keyFindings` | Graded *information* / *watch* / *priority-review*, each cited |
| `sections` | Methodology, source coverage, risk distribution, hotspots |
| `limitations`, `dataGaps` | Derived from what the run actually saw, not boilerplate |
| `mapReferences` | Ties narrative back to `hs-NNN` features on the web map |
| `disclaimer` | Fixed screening disclaimer, verbatim |

`scripts/foundry/create_report_agent.py` runs **two independent checks** and exits
non-zero if either fails:

1. **Citation resolution** — every `E<n>` referenced in the document was actually
   supplied in the input.
2. **Schema validation** — the document validates against the contract.

The second check exists because the first was not enough. Citation checking alone let a
completely different document shape pass repeatedly: the model was emitting invented
top-level keys and omitting every required one, while every citation resolved perfectly.
Validate the contract, not just the values inside it.

### Provisioning Foundry

```bash
python scripts/foundry/provision_foundry.py          # account, project, model deployment
python scripts/foundry/create_report_agent.py \
    --foundry cicd/foundry-setup.output.json \
    --report-input cicd/report-input.sample.json
```

Both `cicd/report-input.sample.json` and `cicd/report-output.sample.json` are committed,
so **the report half of the demo runs with the Fabric capacity paused**.

Three things that cost real time and are worth knowing before you provision:

* **`gpt-4.1-mini` is not deployable in Canada Central** on this subscription under any
  SKU, despite the catalogue claiming GlobalStandard support. This deployment uses
  `gpt-5.4-mini`.
* **The agents data plane needs its role at *project* scope.** Assigned at account scope
  it returns 401 indefinitely, which reads exactly like propagation delay. The built-in
  `Azure AI User` role does not exist in every tenant — a custom role carrying
  `Microsoft.CognitiveServices/accounts/AIServices/agents/*` may be required.
* **A project must be created with a system-assigned identity in the same request.**
  `az resource create` omits the identity block, and assigning one afterwards does not
  clear the "must enable a managed identity" error; a raw ARM `PUT` works.

### Calling the Fabric data agent *from* Foundry

Not possible on this project type, and the reason is worth stating precisely because the
obvious diagnosis is wrong.

The `MicrosoftFabric` connection can be created (in the portal — the ARM connections API
rejects that category) and **attaches to the agent successfully**. Every *run* then fails:

```text
missing_required_parameter: AML connections are required for Fabric tool.
```

identically for the project-scoped ARM id, the account-scoped id, and the bare connection
name; `tool_resources` rejects every `fabric_*` key as `unknown_parameter`. The runtime
resolves Fabric tool connections through an **Azure ML workspace connection store**,
which a `Microsoft.CognitiveServices/accounts/projects` Foundry project does not have. A
**hub-based** project is required — a re-provisioning decision, not a configuration fix.

This costs the demo nothing. The report agent runs the unattended path by design, and its
system prompt already reports an unavailable tool as a data gap rather than failing.

## Provisioned identifiers

The live demo deployment. Resolved IDs are recorded in
`cicd/fabric-setup.output.demo.json` and `cicd/foundry-setup.output.json`; full state,
including the canonical run and every open item, is in [SESSION_HANDOFF.md](SESSION_HANDOFF.md).

**Fabric** — workspace `Geohazard_Demo` = `dcfeb6a8-515b-43d5-be76-f7c56788abd6`

| Item | Display name | ID |
| --- | --- | --- |
| Lakehouse | `bronze_lakehouse` | `73586c5b-0059-4cd8-862e-4b1d72a473c4` |
| Lakehouse | `silver_lakehouse` | `cb318f38-1019-4757-b0ae-703f22c59d44` |
| Lakehouse | `gold_lakehouse` | `f63ee308-54c5-4ffd-a8c0-f8de1b4345f4` |
| Data pipeline | `pl_bronze_ingestion` | `fee776a5-33f8-48da-a6b5-c6bd2c2a51f0` |
| Environment | `geohazard_env` | `8782d53b-e684-4563-b19d-2679cda41a00` |
| Data agent | `geohazard_data_agent` | `ca0561cd-c396-44ef-b913-6fb601f29a75` |

**Foundry** — account `geohazard-foundry-mcap`, project `geohazard-project`

| Item | Value |
| --- | --- |
| Project endpoint | `https://geohazard-foundry-mcap.services.ai.azure.com/api/projects/geohazard-project` |
| Model deployment | `gpt-5-4-mini` (GlobalStandard) |
| Report agent | `geohazard-report-agent` |

Canonical run: `b538ce7e-69bb-4fd1-8f00-7ba7e7fc0a0a` — Low 40.90% · Moderate 22.23% ·
High 33.03% · Extreme 3.84% over 360,000 pixels, with 25 ranked hotspots.

> Each notebook must have its layer lakehouse set as the **default lakehouse** (stored in
> the notebook's `metadata.dependencies.lakehouse`). Without it, relative `saveAsTable` /
> `spark.read.table` calls fail and the Spark session is cancelled.
>
> Libraries come from the `geohazard_env` Environment, not inline `%pip` — inline
> installation is disabled in this tenant and `_inlineInstallationEnabled` does not
> override it.

## Deploy guides

Two beginner-friendly, step-by-step guides cover the full deployment from scratch:

* [DEPLOY_AUTOMATED.md](DEPLOY_AUTOMATED.md) covers prerequisites, scripted
  provisioning, and one complete default Maple Ridge pipeline run.
* [DEPLOY_MANUAL.md](DEPLOY_MANUAL.md) covers the browser-first equivalent, running
  the seven notebooks in the same bronze, silver, and gold order.

The condensed provisioning and run steps are below; use the guides above for the full
walkthrough with placeholders to fill in for your own tenant.

## Setup — provision the foundation

A PowerShell script provisions the workspace, three lakehouses, seven notebooks, the
complete data pipeline, and the deployment pipeline. It is idempotent: existing items
are updated rather than recreated.

```powershell
.\scripts\fabric\setup_fabric_demo.ps1 -ConfigPath ".\cicd\fabric-setup.config.json" -OutputPath ".\cicd\fabric-setup.output.json"
```

Prerequisites:

* Azure CLI signed in: `az login`.
* The Fabric capacity backing the workspace must be **Active** (not paused). For this
  deployment:

  ```bash
  CAP="/subscriptions/<sub>/resourceGroups/rg-fabric-demo/providers/Microsoft.Fabric/capacities/fabdemo85829"
  az resource invoke-action --action resume --ids "$CAP"
  az resource show --ids "$CAP" --query "properties.state" -o tsv
  ```

  Allow about five minutes: the capacity reports **Active** in under a minute, but the
  lakehouse SQL endpoints need another minute or two before the data agent will answer.

## Run the Complete Medallion Pipeline

`pl_bronze_ingestion` runs the four AOI ingestions in parallel. Overview and silver
then start independently, and gold starts after silver succeeds:

```mermaid
flowchart LR
  PC[Ingest PC collections] --> O[Build overview]
  PI[Ingest Planetary] --> O
  BG[Ingest BC geology] --> O
  BS[Ingest BC soil survey] --> O
  PC --> S[Silver soil susceptibility]
  PI --> S
  BG --> S
  BS --> S
  S --> G[Gold risk matrix]
```

In the Fabric portal, select **Run** without changing any values to execute the full
Maple Ridge workflow. The deployed defaults are `49.2193`, `-122.5984`, a 20 km bronze
catalog radius, and a 3 km silver analysis radius. Fabric passes the catalog AOI to all
four ingestion notebooks and the overview. Silver receives the same centre point plus
the detailed radius, then selects the local UTM zone. Gold starts automatically after
silver succeeds.

Override `LATITUDE`, `LONGITUDE`, `RADIUS_KM`, or `ANALYSIS_RADIUS_KM` only when you
want another AOI. The analysis radius must be greater than 0 and no more than 5 km for
the 10 m demo grid.

Deployment defaults come from the file named by `dataPipeline.parametersPath` in
`cicd/fabric-setup.config.json`. It currently points to `cicd/parameters.dev.json`.
Change that property to `cicd/parameters.prod.json` before provisioning to deploy the
production defaults. Users can still override the deployed defaults for each run.

Run the whole pipeline from PowerShell:

```powershell
$state = Get-Content ./cicd/fabric-setup.output.json -Raw | ConvertFrom-Json
$ws    = [string]$state.workspace.workspaceId
$plid  = [string]$state.dataPipeline.id
$base  = "https://api.fabric.microsoft.com/v1"
$token = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv
$h     = @{ Authorization = "Bearer $token" }

# Start the pipeline
$r   = Invoke-WebRequest -Method Post -Uri "$base/workspaces/$ws/items/$plid/jobs/instances?jobType=Pipeline" -Headers $h -Body '{}' -ContentType 'application/json'
$loc = @($r.Headers['Location'])[0]

# Poll to completion
do {
    Start-Sleep 20
    $token = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv
    $h = @{ Authorization = "Bearer $token" }
    $j = Invoke-RestMethod -Uri $loc -Headers $h
    $j.status
} while ($j.status -in "NotStarted","InProgress","Running")
"FINAL: $($j.status)"   # expect: Completed
```

Validate the run in **Workspace > Monitor**. The parent pipeline must be `Completed`
and all seven activities must be `Succeeded`. Confirm the silver lakehouse contains
`silver_rf1_soil_susceptibility` and the gold lakehouse contains
`gold_rf1_risk_pixels`, `gold_rf1_risk_matrix`, `gold_rf1_band_summary`, and
`gold_rf1_risk_areas`. Preview the risk-pixels table and confirm its default `aoi_name` is
`AOI 49.2193, -122.5984`.

### Run One Notebook for Troubleshooting

```powershell
.\scripts\fabric\run_notebooks.ps1 -Notebooks gold_rf1_risk_matrix
```

Do not use the no-argument helper for a normal end-to-end run. It submits notebooks
without the data pipeline's dependency ordering.

## Silver and Gold Outputs

The complete pipeline runs these analytics notebooks automatically:

1. `silver_rf1_soil_susceptibility` clips the AOI to a 10 m grid in the local UTM
  zone, pulls Planetary Computer COG pixels, computes RF-1 factor metrics, rasterizes
  BC soil-survey polygons as soft-soil ground truth, and writes per-pixel S and C
  ratings. The soil survey carries the largest weight in S.
2. `gold_rf1_risk_matrix` calculates `risk_score = S × C` (1–25) and assigns Low,
  Moderate, High, or Extreme bands.

The gold notebook writes:

* `gold_rf1_risk_pixels`: per-pixel risk score and band with coordinates
* `gold_rf1_risk_matrix`: the 5×5 S×C grid with pixel count, mean risk, and band
* `gold_rf1_band_summary`: area and share per risk band
* `gold_rf1_risk_areas`: one dissolved GeoJSON geometry per populated risk band

Each pipeline run also writes these files under
`gold_lakehouse/Files/gold_rf1_webmap/runs/<pipeline-run-id>/`:

* `gold_rf1_webmap.html`: interactive risk-area map with matching legend and popups
* `gold_rf1_risk_areas.geojson`: bounded risk-area FeatureCollection
* `gold_rf1_risk_areas.shp`, `.shx`, `.dbf`, `.prj`, and `.cpg`: Shapefile components
* `gold_rf1_risk_areas_shapefile.zip`: portable Shapefile bundle
* `gold_rf1_webmap_manifest.json`: viewport, layers, legend, and provenance
* `_SUCCESS`: completion marker written after artifact validation

## Foundry report and web-map architecture

The [agent architecture](agent-architecture/README.md) defines the Microsoft Foundry
report agent, strict evidence and report contracts, the Fabric data agent boundary, and a
deterministic interactive web-map design. Both agents are **deployed and verified** — see
[The Foundry layer](#the-foundry-layer--turning-evidence-into-a-written-report). What is
still not built is the **browser application** that would render the report and web map;
the JSON and the map manifest it would consume are both published and validated.

The division of labour holds throughout: the model explains validated Fabric evidence,
while Spark and the map adapter remain responsible for scores, coordinates, geometry,
bounds, and layers.

## CI/CD path

* **Git integration** — commit notebook and pipeline changes through Fabric's source
  control to version the workspace.
* **Deployment pipeline** — `geohazard-demo-single-pipeline` has the workspace assigned
  to stage 0. Assign additional workspaces to later stages for true cross-stage
  promotion. See `cicd/promotion-checklist.md` and `cicd/parameters.{dev,prod}.json`.

## Cost — pause when finished

An F64 bills at roughly **$11.52/hour** while Active, whether or not anything is running.
Suspending immediately after a demo is the single easiest way to avoid burning money on
this project.

```bash
CAP="/subscriptions/<sub>/resourceGroups/rg-fabric-demo/providers/Microsoft.Fabric/capacities/fabdemo85829"
az resource invoke-action --action suspend --ids "$CAP"
az resource show --ids "$CAP" --query "properties.state" -o tsv
```

Foundry is consumption-priced and costs nothing while idle, so the report agent needs no
pausing — and the committed sample input and output mean the report can be shown with the
Fabric capacity suspended.

## Scope note

This repo demonstrates ingestion and medallion engineering patterns plus a worked RF-1
risk model. The RF-1 ratings use availability-weighted proxies over public data for
illustration; production hazard scoring would extend the silver/gold layers with field
data and calibrated models. Geohazard RF-1..RF-10 context is in
`docs/workload-context-geohazard.md`.
