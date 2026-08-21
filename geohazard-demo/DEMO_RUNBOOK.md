# Demo Runbook — Geohazard Screening on Microsoft Fabric

A 15–20 minute walkthrough of the deployed demo. The story is three moves: **public APIs
in → medallion engineering → a report agent that can actually answer spatial questions.**

## Deployed environment

| | |
| --- | --- |
| Workspace | `Geohazard_Demo` |
| Workspace URL | <https://app.fabric.microsoft.com/groups/dcfeb6a8-515b-43d5-be76-f7c56788abd6> |
| Capacity | `fabdemo85829` (F64, Canada Central) |
| Pipeline | `pl_bronze_ingestion` |
| Lakehouses | `bronze_lakehouse`, `silver_lakehouse`, `gold_lakehouse` |
| Default AOI | Maple Ridge, BC — `49.2193, -122.5984`, 20 km catalog / 3 km analysis |

Resolved item IDs are in `cicd/fabric-setup.output.demo.json`.

> **Cost:** the F64 bills at roughly **$11.52/hour** while Active. Resume before the
> demo, suspend **immediately** after — this is the single easiest way to burn money on
> this project.
>
> ```bash
> SUB=<your-subscription-id>
> CAP="/subscriptions/$SUB/resourceGroups/rg-fabric-demo/providers/Microsoft.Fabric/capacities/fabdemo85829"
>
> az resource invoke-action --action resume  --ids "$CAP"
> az resource invoke-action --action suspend --ids "$CAP"
> az resource show --ids "$CAP" --query "properties.state" -o tsv
> ```

Set `SUB` to the subscription holding `fabdemo85829`.

---

## Before you start

Verified end to end on **2026-08-21**: the pipeline re-ran clean in 14m48s and reproduced
the canonical run to four decimal places, the data agent answered every demo question
through its portal chat, and the Foundry agent produced a report passing both citation
and schema validation.

### Resume the capacity 30 minutes before you present — not 5

This is the one that will actually bite you.

The capacity reports **Active** within a minute, and the Fabric API, lakehouses, and SQL
endpoints all come back within a few minutes. **The data agent editor does not.** After a
resume it shows

```text
Couldn't load the data agent
Try refreshing, or wait a little while and try again.
```

for roughly **20–25 minutes**, while every backend check passes: the tables API responds,
`getDefinition` succeeds, and `refreshMetadata` reports the SQL endpoints already in sync.
There is nothing to fix and nothing to retry faster. It simply needs the time.

Measured on 2026-08-21: agent working at 16:05, paused 16:10, resumed 16:15, editor
failing 16:20 through 16:30, healthy again by ~16:40.

```bash
CAP="/subscriptions/<sub>/resourceGroups/rg-fabric-demo/providers/Microsoft.Fabric/capacities/fabdemo85829"
az resource invoke-action --action resume  --ids "$CAP"
az resource show --ids "$CAP" --query "properties.state" -o tsv
```

**Do not pause between a rehearsal and the real thing.** Leave it Active and suspend once,
afterwards.

### Warm it up with one throwaway question

Before anyone is watching, open the data agent and ask anything. First response after a
resume is slower; later ones land in 4–15 seconds.

### Keep two things on the Desktop

Both work with the capacity **paused**, so they are your fallback if Fabric is having a
bad day:

* `risk-webmap.html` — the full interactive risk map with hotspot popups
* `report-output.json` — a validated grounded report

Fetch them from OneLake with `Files/gold_rf1_webmap/runs/<run-id>/gold_rf1_webmap.html`
and `Files/agent-handoff/<run-id>/report-input.json`; the committed
`cicd/report-*.sample.json` serve the same purpose.

### Tab order

Open these left to right and never alt-tab out of the browser:

| # | Tab | Used in |
| --- | --- | --- |
| 1 | Workspace item list | Opening |
| 2 | `bronze_data_overview` | Act 1 |
| 3 | `bronze_lakehouse` → `bronze_bc_soil_survey_polygons` | Act 1 |
| 4 | `silver_source_features` | Act 2 |
| 5 | `gold_rf1_risk_matrix` | Act 2 |
| 6 | `risk-webmap.html` | Act 2 |
| 7 | `agent_handoff_publisher` | Act 3 |
| 8 | `geohazard_data_agent` | Act 3 |
| 9 | `report-output.json` | Act 4 |
| 10 | Foundry project | Act 4 |
| 11 | GitHub repo | Close |

### Run scoping is handled — and it is worth a sentence

Gold holds five runs. Only the canonical one is post-SIFT-fix, and the agent is pinned to
it by name. It used to be told to "use the most recent run", which is unimplementable —
run IDs are UUIDs and carry no ordering — and on an open-ended question it picked a
superseded run, reported its inflated figures as current, and called the good run "an
older run". Fixed by `scripts/fabric/harden_data_agent.py`.

Worth showing rather than hiding: ask *"talk to me about my data"* and it names the run it
used, unprompted.

---

## Act 1 — Everything comes from public APIs (3 min)

**Open `bronze_data_overview` and scroll the rendered maps.**

> The maps are saved in the notebook as of 2026-08-21 and survive a cold reload. Note
> **a pipeline run does not put them there** — pipeline output goes to a run snapshot,
> not back into the notebook item, so a notebook that has only ever been run by the
> pipeline opens as code with no outputs. If you need them refreshed, open the notebook
> and **Run all** once (about 2.5 minutes); AutoSave persists the result.

Talking points:

* No files were uploaded and no credentials are configured. Bronze is built entirely
  from two public APIs: the **Microsoft Planetary Computer STAC API** and the **DataBC
  WFS** (BC Geographic Warehouse), including the soils behind the **Soil Information
  Finder Tool**.
* Bronze stores **metadata only** — STAC item records and GeoJSON features. Rasters are
  never downloaded here; pixels are pulled on demand in silver.
* Every source anchors on the same AOI, so the satellite, elevation, geology, and soil
  layers describe the same ground.

**Then open `bronze_lakehouse` → `bronze_bc_soil_survey_polygons` and show a row.**

This is the setup for Act 2. Point at `geometry_json` and `properties_json`:

> "This is raw fidelity, exactly what the API returned — and it's completely useless to
> SQL or to an AI agent. Nothing can parse a GeoJSON string. This is where most
> geospatial demos stop."

---

## Act 2 — The medallion makes it answerable (6 min)

**Open `silver_source_features`, run the last cell, or show its output.**

* Flattens every WFS feature **once** into typed columns: `drainage_class`,
  `parent_material`, `texture`, `rock_type`, `fault_type`, plus `centroid_lat/lon`,
  `area_km2`, and `distance_from_aoi_km`.
* Attribute names differ between DataBC layers, so they're resolved by token-boundary
  matching against the real property keys — a schema change degrades to nulls rather
  than breaking the pipeline.
* `silver_source_coverage` records, per source, whether it returned data. **An empty
  source is a data gap, not a measured zero** — a distinction that survives all the way
  into the report.

**Open `silver_rf1_soil_susceptibility`, show the grid and S/C sections.**

* A deterministic 10 m grid in the local UTM zone. Every raster — Sentinel-2, Sentinel-1
  radar, Copernicus DEM, ESA WorldCover — is loaded onto the *same* GeoBox, so they
  co-register pixel-for-pixel with no manual alignment.
* Susceptibility blends indirect remote-sensing proxies with the **surveyed soil
  polygons**, which carry the largest single weight because they're the only direct
  ground truth.
* The same step burns **feature identity** onto the grid: each pixel records which soil
  polygon and which surficial-geology polygon it sits on.

**Open `gold_rf1_risk_matrix` and show the map at the end.**

* `risk_score = S × C`, banded Low / Moderate / High / Extreme.
* Scroll to **`gold_rf1_risk_hotspots`**: contiguous High/Extreme pixels clustered into
  ranked features with stable `hs-001`-style IDs — each carrying its dominant soil unit
  and drainage class, surficial geology, land cover, mean slope, and the exact distance
  to the nearest mapped fault.
* The interactive map at the bottom has the risk bands *and* the ranked hotspot markers.
  Click one — the popup is the evidence, not a guess.

> **Show the standalone map instead of the notebook cell.** Gold publishes a
> self-contained 2.8 MB HTML map to OneLake, which opens in any browser with the capacity
> paused and is far steadier than scrolling a notebook. Grab it once and keep it locally:
>
> ```text
> Files/gold_rf1_webmap/runs/<run-id>/gold_rf1_webmap.html
> ```
>
> Verified 2026-08-21: OpenStreetMap basemap, 29 risk-band polygons, 25 numbered hotspot
> pins, a layer toggle, and a legend. The `hs-001` popup reads: *Extreme — score 25,
> 0.2512 km² over 2,512 px, Soil: ALBION, Drainage: poorly drained, Land cover: Built-up,
> Nearest mapped fault: 5.26 km.* The same folder holds the GeoJSON, Shapefile, and the
> manifest, which carries a per-layer `queryHash` for provenance.

> "The dissolved bands tell you *how much*. The hotspots tell you *where* and *why*.
> That second part is what a report actually needs."

---

## Act 3 — Grounding the agent (5 min)

**Open `agent_handoff_publisher` and show the final preview cell.**

* Packages one run into `report-input.json` against a versioned JSON Schema.
* Every number carries an **`evidenceId`**. The report agent is required to cite one for
  each quantitative claim, so nothing it says is unattributable.
* Validation runs before *and after* the write, and `_SUCCESS` is written last. If the
  gold tables disagree on totals, the run is **quarantined and nothing is published**.
* Note what does *not* cross the boundary: no pixel rows, no geometry, no raw bronze
  property JSON. The model gets a compact, bounded evidence envelope.

**Then show the limitations block in the output.**

These are derived from what the run actually saw — which sources came back empty, what
share of the grid the soil survey actually covers — not boilerplate.

**Close on the questions this now supports** (via a published Fabric data agent over
`gold_rf1_risk_hotspots`, `gold_rf1_band_summary`, `gold_rf1_risk_matrix`, and
`silver_source_features`):

* *For run `b538ce7e-69bb-4fd1-8f00-7ba7e7fc0a0a`, which soil units underlie
  the Extreme risk area, and how are they drained?*
* *What is the highest-ranked hotspot in that run, and what is it sitting on?*
* *How far is the nearest mapped fault from hotspot `hs-003`?*
* *Which configured sources returned no records for that run?*
* *What surficial materials are mapped within 2 km of the AOI centre?*

Answers are attributed from `gold_rf1_risk_hotspots`, whose columns are `soil_name`,
`soil_drainage_class`, `parent_material`, `worldcover_class`, `mean_slope_deg`,
`mean_elevation_m`, and `nearest_fault_km`.

Scope for `agent-architecture/fabric-data-agent.md` is already written to match these
tables.

---

## Optional — run it live for a different AOI

The whole pipeline is parameterized. From the repo root:

```bash
python scripts/fabric/run_pipeline.py \
  --output cicd/fabric-setup.output.demo.json \
  --latitude 49.1042 --longitude -122.6604 \
  --radius-km 20 --analysis-radius-km 3
```

Or run `pl_bronze_ingestion` from the portal and supply the four parameters.

Expect roughly 25–45 minutes end to end; the silver COG extraction dominates. Each run
gets its own `run_id` and writes to its own partition, so previous runs stay intact and
comparable.

**Caveat worth saying out loud:** Planetary Computer coverage is global, but the DataBC
geology and soil layers are **British Columbia only**. Point the AOI outside BC and
those sources correctly return empty — which the pipeline reports as a data gap. That's
a feature of the design, but it will look like a failure if you don't call it first.

---

## Reset

```bash
python scripts/fabric/provision_fabric_demo.py \
  --config cicd/fabric-setup.config.demo.json \
  --output cicd/fabric-setup.output.demo.json
```

Idempotent — it updates the existing workspace items in place rather than duplicating
them. Use it to push notebook edits from the repo into the workspace.

## Act 4 — The grounded report (3 min)

Two agents exist, deliberately serving different jobs.

**`geohazard_data_agent` (Fabric)** — published over the six curated tables. Ask it live:

* *"What soil unit and drainage class underlie the top three hotspots?"*
* *"Which configured sources returned no records for this run?"*

**`geohazard-report-agent` (Foundry)** — writes the screening report from the handoff
contract. Show `cicd/report-output.sample.json`, generated against run
`b538ce7e-69bb-4fd1-8f00-7ba7e7fc0a0a`:

* Risk distribution matches the gold tables exactly — the model copied evidence rather
  than computing anything.
* The document is the shape the contract demands: `title`, a cited `executiveSummary`,
  `keyFindings` graded *information* / *watch* / *priority-review*, `sections`,
  `limitations`, `dataGaps`, and `mapReferences` that tie narrative back to `hs-NNN`
  feature IDs on the web map.
* The hotspots section names each hotspot's soil unit, drainage class, parent material,
  land cover, slope, elevation, and distance to the nearest mapped fault.
* **Every evidence citation resolves, and the document validates against
  `geohazard-report-output.schema.json`.** Both checks run automatically and the script
  exits non-zero if either fails — so a malformed report never reaches a renderer.
* Data gaps are reported honestly: Sentinel-1 GRD unavailable, *and* the Fabric tool
  itself unavailable for that request.

Regenerate live with:

```bash
python scripts/foundry/create_report_agent.py \
  --foundry cicd/foundry-setup.output.json \
  --report-input cicd/report-input.sample.json
```

> The report agent runs the **unattended path**: the handoff JSON goes straight to the
> model. The Fabric data-agent *tool inside Foundry* is not wired, and it cannot be on
> this project. The connection exists and attaches to the agent fine, but every run
> fails with `AML connections are required for Fabric tool` — the runtime resolves those
> connections through an Azure ML workspace store that a Foundry project does not have.
> A hub-based project would be required. The system prompt already treats a missing tool
> as a data gap, which is why the report is complete without it.

## Question crib sheet

Every question below was run through the portal chat on 2026-08-21 and answered from the
canonical run. Response times were 4–18 seconds. Ask them roughly in this order — it
builds from "it can read the data" to "it knows what the data means".

| Ask | You should hear |
| --- | --- |
| *Talk to me about my data* | Names the canonical run unprompted, gives the full band breakdown, the top hotspot, the soil units, the Sentinel-1 gap, and the ground-truth caveat |
| *How much of the area is at High or Extreme risk?* | 13.28 km², 36.88% |
| *What is the highest-ranked hotspot and what is it sitting on?* | `hs-001`, Extreme, 0.2512 km², ALBION, poorly drained, Built-up, slope 3.1°, fault 5.26 km |
| *Which soil units underlie the Extreme risk area, and how are they drained?* | ALBION, CARVOLTH, SCAT, HAZELWOOD, CLOVERDALE, PAGE, TRIGGS, GRAVEL PIT — mostly poorly or very poorly drained |
| *How far is the nearest mapped fault from hotspot hs-003?* | 4.98 km |
| *Which configured sources returned no records for this run?* | Sentinel-1 GRD, status `unavailable` — described as absent data, not zero hazard |
| *What surficial materials are mapped within 2 km of the AOI centre?* | Glaciomarine, eolian, fluvial, marine, open water, intrusive rock, with named soil units |

Two worth landing deliberately:

* **The Sentinel-1 question** demonstrates the distinction the whole design rests on —
  *missing coverage is not a measured zero*. The agent says the data is absent.
* **"Talk to me about my data"** is the open-ended one that used to fail. Now it names the
  run it used and refuses to blend runs.

## If something goes wrong

| Symptom | Cause | What to do |
| --- | --- | --- |
| "Couldn't load the data agent" | Capacity resumed under ~25 minutes ago | Nothing. It resolves itself. Show the web map and the report JSON meanwhile — neither needs capacity |
| Agent quotes ~72% High/Extreme | It resolved to a superseded run | Name the canonical run in the question. Re-run `harden_data_agent.py` afterwards |
| Notebook opens with no maps | It has only ever been run by the pipeline | Run all once (~2.5 min). Pipeline runs never populate the notebook item |
| Notebook cell fails on `Affine` | `affine` not pinned to 2.3.1 in the Environment | Republish `geohazard_env` (~20 min) — do not attempt during a demo |
| Report generation exits non-zero | Citation or schema validation failed | That is the control working. Show `cicd/report-output.sample.json` instead |
| Fabric portal is slow or erroring | — | Fall back to the Desktop copies; the whole Act 4 story works from them |

**The safest demo path if the capacity is misbehaving:** Acts 1 and 2 from the web map and
the committed samples, Act 4 from `report-output.json`. Only the live agent Q&A genuinely
needs Fabric to be healthy.

## Known gaps

* The **browser report experience is not built**. The report JSON and web-map manifest
  it would consume are both published and validated.
* The Fabric data-agent **tool binding inside Foundry** is not possible on this project
  type (see above). The Fabric data agent itself works standalone, and was driven
  through its portal chat on 2026-08-21.
* The reference architecture names `gpt-4.1-mini`; this deployment uses **`gpt-5.4-mini`**
  because gpt-4.1-mini is not deployable in Canada Central on this subscription under
  any SKU.
* `bronze_pc_sentinel1` is deployed but not in the pipeline DAG: it isn't parameterized
  and its `sentinel-1-rtc` output duplicates `bronze_pc_collections`. This is why
  `bronze_sentinel_1_grd` shows as a data gap in the report — correctly.
