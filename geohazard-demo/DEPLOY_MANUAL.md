---
title: Manual Deployment
description: Simple browser-first steps for running the geohazard demo in Microsoft Fabric
ms.date: 2026-08-04
ms.topic: tutorial
---

## What You Will Create

In one Fabric workspace, create:

* Three lakehouses
* Seven notebooks
* Bronze, silver, and gold geohazard tables

Allow about 30 minutes. The seven notebook runs below are the browser-based equivalent
of the full pipeline and use the default Maple Ridge AOI stored in the notebooks.

> [!NOTE]
> This guide runs the same bronze, silver, and gold workflow one notebook at a time.
> To deploy the reusable pipeline and run all seven activities once, use
> [DEPLOY_AUTOMATED.md](DEPLOY_AUTOMATED.md). The setup script resolves the portable
> workspace and notebook tokens automatically.

## 1. Open Fabric

1. Make sure your Fabric capacity is active. Ask your Fabric administrator if needed.
2. Open <https://app.fabric.microsoft.com>.
3. Select **Workspaces**, then **New workspace**.
4. Name the workspace `Englobecorp_Geohazard`.
5. Assign an active Fabric capacity and select **Apply**.

## 2. Create Three Lakehouses

In the new workspace, select **New item**, then **Lakehouse**. Create these items:

1. `bronze_lakehouse`
2. `silver_lakehouse`
3. `gold_lakehouse`

## 3. Import Seven Notebooks

Select **Import**, then **Notebook**, and upload every `.ipynb` file from
`fabric/notebooks/` except the optional `bronze_pc_sentinel1.ipynb` file.

Import these notebooks:

1. `bronze_pc_collections.ipynb`
2. `bronze_planetary_ingestion.ipynb`
3. `bronze_bc_surficial_geology.ipynb`
4. `bronze_bc_soil_survey.ipynb`
5. `bronze_data_overview.ipynb`
6. `silver_rf1_soil_susceptibility.ipynb`
7. `gold_rf1_risk_matrix.ipynb`

## 4. Attach Each Lakehouse

Open each notebook. In its **Lakehouses** panel, add and pin the matching default
lakehouse:

| Notebook name | Default lakehouse |
| --- | --- |
| Name starts with `bronze_` | `bronze_lakehouse` |
| Name starts with `silver_` | `silver_lakehouse` |
| Name starts with `gold_` | `gold_lakehouse` |

The pinned lakehouse must match the notebook name before you run it.

## 5. Run the Notebooks

Open each notebook and select **Run all**. Wait for it to finish before continuing.

Run them in this order:

1. `bronze_pc_collections`
2. `bronze_planetary_ingestion`
3. `bronze_bc_surficial_geology`
4. `bronze_bc_soil_survey`
5. `bronze_data_overview`
6. `silver_rf1_soil_susceptibility`
7. `gold_rf1_risk_matrix`

The first notebook can take a few minutes while Fabric starts Spark.

This order produces the same outputs as one default `pl_bronze_ingestion` run. The
automated pipeline runs the first four ingestions in parallel, then starts overview and
silver, and finally starts gold after silver succeeds.

## 6. Check the Results

Confirm these tables exist:

| Lakehouse | Expected result |
| --- | --- |
| `bronze_lakehouse` | Several tables beginning with `bronze_` |
| `silver_lakehouse` | `silver_rf1_soil_susceptibility` |
| `gold_lakehouse` | `gold_rf1_risk_pixels` |
| `gold_lakehouse` | `gold_rf1_risk_matrix` |
| `gold_lakehouse` | `gold_rf1_band_summary` |
| `gold_lakehouse` | `gold_rf1_risk_areas` |

Open `bronze_data_overview` and `gold_rf1_risk_matrix` to view the generated maps and
charts.

Under `gold_lakehouse/Files/gold_rf1_webmap/runs/<manual-run-id>/`, confirm the HTML
map, GeoJSON, Shapefile components and ZIP, manifest, and `_SUCCESS` marker exist.

## Custom Location

For the simplest manual demo, keep the default coordinates.

To use another location manually, edit the parameter cell near the top of each bronze
notebook and `bronze_data_overview` so they share the same values:

```python
LATITUDE = 49.2193
LONGITUDE = -122.5984
RADIUS_KM = 20
```

In `silver_rf1_soil_susceptibility`, use the same latitude and longitude, but set
`RADIUS_KM` to the detailed analysis radius. The default is `3.0` km and the maximum is
`5.0` km.

The DataBC geology and soil sources cover British Columbia. Other locations can have
empty DataBC tables even when Planetary Computer data is available.

## Common Problems

| Problem | Fix |
| --- | --- |
| Table not found | Pin the lakehouse that matches the notebook name |
| Spark keeps waiting | Confirm the Fabric capacity is active |
| Silver or gold fails | Run all earlier notebooks again in order |
| DataBC table is empty | Confirm the AOI is inside British Columbia source coverage |

When finished, pause the Fabric capacity through Azure or ask your administrator to
pause it so the demo does not continue consuming capacity.
