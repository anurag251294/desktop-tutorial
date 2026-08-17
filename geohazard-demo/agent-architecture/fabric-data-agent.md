---
title: Fabric Data Agent Design
description: Scope and operating instructions for the Fabric data agent connected to the Foundry geohazard report agent
ms.date: 2026-07-25
ms.topic: concept
---

## Scope

Create and publish one Fabric data agent for interactive report follow-up. Expose only
the minimum analytical objects:

| Object | Allowed use |
| --- | --- |
| `gold_rf1_band_summary` | Risk-band area, pixel count, and percentage |
| `gold_rf1_risk_matrix` | S-by-C matrix counts and mean risk |
| `gold_rf1_risk_hotspots` | Ranked hotspots with spatial attribution; the primary object for "where" and "why" questions |
| `gold_rf1_risk_pixels` | Bounded aggregate and AOI queries only |
| `silver_source_features` | Curated per-feature source attributes and location; excludes `geometry_wkt` and `properties_json` |
| `silver_source_coverage` | Bronze lineage, record counts, and data gaps |

Do not expose unrestricted bronze property JSON to the report agent. `silver_source_features`
is the sanctioned path to source detail: it exposes typed, bounded columns
(`name`, `unit_code`, `drainage_class`, `parent_material`, `texture`, `rock_type`,
`fault_type`, centroid, area, distance) while the two free-text columns that carry
unbounded upstream content — `geometry_wkt` and `properties_json` — stay outside agent
scope. That keeps prompt-injection surface and data volume bounded without leaving the
agent unable to reason about the ground.

Every object above is partitioned by `run_id`, so the run-scoping instruction below is
enforceable rather than advisory.

## Data-agent instructions

Use the following instructions when configuring the Fabric data agent:

```text
You answer questions about one completed RF-1 geohazard screening run at a time.

Use gold_rf1_band_summary for distribution questions and gold_rf1_risk_matrix for
S-by-C questions. Use gold_rf1_risk_pixels only for bounded aggregates or a deterministic
top-N result. Never return the full pixel table.

Filter every query by the run identifier or immutable run partition supplied by the
caller. If no run identifier is available, ask for it and do not query across runs.

Return source table names, filters, row counts, and units with every answer. Distinguish
missing coverage from a measured zero. Do not provide engineering conclusions or
invent unavailable source coverage.
```

## Approved question patterns

Distribution and method:

* What percentage and area fall in each risk band for run `<run-id>`?
* Which S and C combinations contain the most pixels for run `<run-id>`?
* Which configured source layers returned no records for run `<run-id>`?
* What AOI, analysis radius, resolution, and CRS were used for run `<run-id>`?

Spatial questions, answered from `gold_rf1_risk_hotspots` and `silver_source_features`:

* What are the top 10 ranked hotspots for run `<run-id>`, and where are they?
* What soil unit and drainage class underlie hotspot `<feature-id>`?
* Which surficial-geology units appear under the Extreme risk band?
* How far is the nearest mapped fault from hotspot `<feature-id>`?
* Which soil survey polygons within `<n>` km of the AOI centre are poorly drained?
* What is the dominant land cover across the High and Extreme hotspots?

Queries must include deterministic ordering. Hotspots are pre-ranked by mean risk
descending, then pixel count descending, then latitude and longitude ascending, and
carry stable `hs-NNN` identifiers; prefer `rank` over re-deriving an ordering. Feature
queries order by `distance_from_aoi_km` ascending, then `feature_id`. Results use a
fixed maximum row count.

Answer from the ranked hotspot table rather than from `gold_rf1_risk_pixels` wherever
possible — it is bounded, pre-attributed, and stable across repeated questions about the
same run.

## Identity and permissions

The current Foundry integration uses identity passthrough. Each user needs:

* At least the `Foundry User` role in the Foundry project
* Read access to the published Fabric data agent
* Read access to the lakehouse and relevant tables
* Membership in the same tenant as the Foundry project

Service principals are not supported by the Fabric data-agent tool. Use the direct
handoff contract for unattended pipeline-triggered report generation.

## Connection values

The implementation resolves these values from deployment configuration:

* `FOUNDRY_PROJECT_ENDPOINT`
* `FOUNDRY_MODEL_DEPLOYMENT_NAME`
* `FABRIC_PROJECT_CONNECTION_ID`

Do not commit connection IDs, tokens, or endpoints into prompts or browser assets.