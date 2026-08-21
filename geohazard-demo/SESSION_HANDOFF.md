# Session Handoff — Geohazard Demo

State as of **2026-08-21 14:20 UTC**, re-verified live on demo day.

Capacity `fabdemo85829` is **Paused**. Nothing is running or billing.

---

## What works, verified against live data

| Component | State |
|---|---|
| `pl_bronze_ingestion`, all 9 activities | Green, ~13 min end to end |
| 22 Delta tables (bronze 13 / silver 4 / gold 5) | Populated |
| Map artifacts (GeoJSON, hotspots, Shapefile, manifest, HTML) | Published |
| Handoff contract `report-input.json` | Validated, 64 evidence records |
| **Fabric data agent** `geohazard_data_agent` | Published, answering |
| **Foundry report agent** `geohazard-report-agent` | Generates grounded reports |

Verified run: **`b538ce7e-69bb-4fd1-8f00-7ba7e7fc0a0a`**

Risk distribution: Low 40.90% · Moderate 22.23% · High 33.03% · Extreme 3.84%
(360,000 px over 36 km², 25 ranked hotspots, largest 0.25 km²)

Report agent output on that run: every evidence citation resolves, the document
**validates against `geohazard-report-output.schema.json`**, risk figures are identical
to the gold tables, and both data gaps are reported (Sentinel-1 GRD unavailable, and the
Fabric tool unavailable for that request).

### Re-verified 2026-08-21

* All 22 Delta tables intact and queryable; `gold_rf1_risk_pixels` holds 1.44 M rows.
* Fabric data agent answered live through `FabricOpenAI` in the SDK: 25 hotspots for the
  canonical run, top hotspot on **ALBION / poorly drained**, and it named the run it used.
* Foundry report agent regenerated `cicd/report-output.sample.json` end to end.

Three fixes went in on demo day, all in the report contract path:

1. The report was **not conforming to its own schema** — the model was emitting ad-hoc
   keys (`riskDistribution`, `hotspots`, `methodology`) and omitting every required one
   (`title`, `keyFindings`, `sections`, `dataGaps`). Citation checking was the only
   validation, so this went unnoticed. The OUTPUT RULES now enumerate the exact contract.
2. `create_report_agent.py` now validates the document against the JSON Schema and exits
   non-zero on any violation, so the shape cannot silently drift again.
3. The disclaimer is a schema `const`; the prompt wrapped it across three lines and the
   model paraphrased it. It is now given as one exact literal that must be copied.

Sample input and output are committed under `cicd/`, so the report can be demoed
**without resuming capacity**.

---

## Identifiers

| | |
|---|---|
| Subscription | `671b1321-4407-420b-b877-97cd40ba898a` (MngEnvMCAP tenant `fe64e912-…`) |
| Capacity | `fabdemo85829` (F64, Canada Central, `rg-fabric-demo`) — ~$11.52/hr |
| Fabric workspace | `Geohazard_Demo` = `dcfeb6a8-515b-43d5-be76-f7c56788abd6` |
| Lakehouses | bronze `73586c5b…` · silver `cb318f38…` · gold `f63ee308…` |
| Pipeline | `pl_bronze_ingestion` = `fee776a5-33f8-48da-a6b5-c6bd2c2a51f0` |
| Environment | `geohazard_env` = `8782d53b-e684-4563-b19d-2679cda41a00` |
| Fabric data agent | `geohazard_data_agent` = `ca0561cd-c396-44ef-b913-6fb601f29a75` |
| Foundry account | `geohazard-foundry-mcap` |
| Foundry project | `geohazard-project` |
| Project endpoint | `https://geohazard-foundry-mcap.services.ai.azure.com/api/projects/geohazard-project` |
| Model deployment | `gpt-5-4-mini` (GlobalStandard, 50K TPM) |
| Foundry agent | `geohazard-report-agent` = `asst_4jWK0XXj4k2Khweh6QCUgAdH` |

---

## Open items

**1. Bind the Fabric tool inside Foundry — portal only.**
The ARM connections API rejects every Fabric category (`FabricDataAgent`, `Fabric`,
`MicrosoftFabric`, `FabricAISkill`) across four preview API versions; only generic
categories like `ApiKey` are accepted. Create the connection in
[ai.azure.com](https://ai.azure.com) → project → Management center → Connected
resources → **Microsoft Fabric**, name it `fabric_geohazard`, then attach it to
`geohazard-report-agent`. Resume capacity first or the connection test fails.

Not a blocker: the report agent runs the unattended handoff path, and the Fabric data
agent answers standalone.

**2. Deselect four columns on the data agent.**
All columns are currently selected. Remove `geometry_wkt` and `properties_json` on
`silver_source_features`, and `geometry_json` on `gold_rf1_risk_hotspots` and
`gold_rf1_risk_areas`. A `SELECT *` on a soil query otherwise returns a wall of
coordinates.

**3. Four runs live in gold; only one is good.**
`b538ce7e-69bb-4fd1-8f00-7ba7e7fc0a0a` is the only run produced after the SIFT decoding
fix. `0da6944e-…`, `777d9049-…`, and `b50e84ae-…` predate it and each report 71.9% of
the AOI in one band. The agent resolved to the correct run under test and the good run
happens to sort last, but that is luck, not design. Either name the run when asking, or
delete the three stale runs — they are pure pre-fix output:

```sql
DELETE FROM gold_rf1_band_summary WHERE run_id <> 'b538ce7e-69bb-4fd1-8f00-7ba7e7fc0a0a'
```

...and the same for `gold_rf1_risk_hotspots`, `gold_rf1_risk_matrix`,
`gold_rf1_risk_areas`, `gold_rf1_risk_pixels`, and the silver tables.

**4. Browser report UI** — not built. The report JSON and web-map manifest it would
consume are both published and validated.

---

## Tell upstream

`yus-git/geohazard-demo` still has the **SIFT decoding bug**. SIFT stores coded
attributes (`DRAIN_1=W`, `MDEP_1=COLL`, `TEXTURE_1=SL`); the keyword scorer matches none
of them, so surveyed soil contributes a flat `0.4` constant. Consequences there today:
risk reports as ~92% High/Extreme, hotspots merge into two blobs covering ~78% of the
AOI, and all soil attribution is null. The README claim that surveyed soil carries the
largest single weight is false in practice. Fix is in this fork (`6c8a834`).

---

## Environment gotchas, all encoded in the scripts

* Inline `%pip` is disabled in this tenant; `_inlineInstallationEnabled` does **not**
  override it. Libraries come from the `geohazard_env` Environment.
* The Environment API accepts `environment.yml`, not `requirements.txt`, and validates
  on filename.
* `affine` must stay pinned to `2.3.1` or silver dies at GeoBox construction.
* Delta rejects `overwriteSchema` in dynamic partition overwrite mode — the schema-change
  fallback switches to static and back.
* The Fabric endpoint intermittently resets connections mid-provision; the provisioner
  retries with backoff. Always confirm the deploy succeeded before blaming a fix.
* Foundry agents data plane needs `AIServices/agents/*` at **project** scope; account
  scope returns 401 indefinitely and looks like propagation delay.
* The built-in `Azure AI User` role does not exist in this tenant. Only `Defender CSPM`
  carries the agents data actions, so a custom role is required (needs Owner).
* `gpt-4.1-mini` is not deployable in Canada Central on this subscription under any SKU,
  despite the catalogue claiming GlobalStandard support.

---

## Resume / pause

```bash
CAP="/subscriptions/671b1321-4407-420b-b877-97cd40ba898a/resourceGroups/rg-fabric-demo/providers/Microsoft.Fabric/capacities/fabdemo85829"
az resource invoke-action --action resume  --ids "$CAP"
az resource invoke-action --action suspend --ids "$CAP"
az resource show --ids "$CAP" --query "properties.state" -o tsv
```

Re-run the pipeline (notebook-only changes skip the ~20 min Environment republish):

```bash
python scripts/fabric/provision_fabric_demo.py --config cicd/fabric-setup.config.demo.json \
    --output cicd/fabric-setup.output.demo.json --skip-environment
python scripts/fabric/run_pipeline.py --output cicd/fabric-setup.output.demo.json
```

Regenerate the report (no capacity needed):

```bash
python scripts/foundry/create_report_agent.py --foundry cicd/foundry-setup.output.json \
    --report-input cicd/report-input.sample.json
```
