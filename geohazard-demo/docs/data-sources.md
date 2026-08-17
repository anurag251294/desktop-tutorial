# Data Sources

All external data ingested by the geohazard bronze layer. Every source anchors on the same Area of Interest (AOI) so the satellite, elevation, and geology layers describe the same ground.

| | |
|---|---|
| **AOI** | Maple Ridge, British Columbia (south coast) |
| **AOI center** | 49.2193, -122.5984 |
| **AOI radius** | 20 km |
| **Target lakehouse** | `bronze_lakehouse` |
| **Access** | Public, anonymous HTTP — no keys or signing |
| **Pattern** | Metadata bronze (item/feature records; rasters are not downloaded) |

---

## 1. Microsoft Planetary Computer — STAC API

Satellite, radar, elevation, land cover, and biomass scene **metadata** retrieved from the Planetary Computer SpatioTemporal Asset Catalog (STAC).

| | |
|---|---|
| **Search endpoint** | `https://planetarycomputer.microsoft.com/api/stac/v1/search` |
| **Item / tiles endpoint** | `https://planetarycomputer.microsoft.com/api/stac/v1` (`tilejson`, `rendered_preview` assets) |
| **Protocol** | STAC `POST /search` with `bbox`, `datetime`, and `query` extension filters |
| **Auth** | None (public read) |
| **Notebooks** | `bronze_planetary_ingestion.ipynb`, `bronze_pc_collections.ipynb`, `bronze_data_overview.ipynb` (live tiles) |

### Collections

| STAC collection | Bronze table | Theme | Time filter |
|---|---|---|---|
| `io-lulc-9-class` | `bronze_io_lulc_9_class` | Esri 10 m land use / land cover | none (annual) |
| `esa-worldcover` | `bronze_esa_worldcover` | ESA WorldCover 10 m land cover | none (epochs) |
| `cop-dem-glo-30` | `bronze_cop_dem_glo_30` | Copernicus 30 m elevation (DEM) | none (static) |
| `sentinel-2-l2a` | `bronze_sentinel_2_l2a` | Sentinel-2 optical surface reflectance | 2024 summer, cloud < 30% |
| `sentinel-1-rtc` | `bronze_sentinel_1_rtc` | Sentinel-1 radar (terrain corrected) | 2024 summer |
| `alos-palsar-mosaic` | `bronze_alos_palsar_mosaic` | ALOS PALSAR L-band radar mosaic | none (annual) |
| `hgb` | `bronze_hgb` | Harmonized global above/below-ground biomass | none (static) |

> `bronze_planetary_ingestion.ipynb` is a single-collection demo that ingests `sentinel-2-l2a` (2024-06-01 to 2024-09-30) into `bronze_satellite_stac_items`. `bronze_pc_collections.ipynb` ingests all seven collections above.

---

## 2. BC DataBC — WFS (BC Geographic Warehouse)

Province-wide geology vector features fetched as GeoJSON over WFS, clipped to the AOI bounding box. Used in place of the *BC Digital Surficial Geology* dataset, which has no coverage at the coastal Maple Ridge AOI.

| | |
|---|---|
| **Endpoint** | `https://openmaps.gov.bc.ca/geo/pub/wfs` |
| **Protocol** | WFS 2.0.0 `GetFeature`, `outputFormat=application/json`, `srsName=EPSG:4326` |
| **Auth** | None (public read) |
| **Feature cap** | 5000 features per layer |
| **Notebook** | `bronze_bc_surficial_geology.ipynb` |

### Layers

| DataBC layer | Bronze table | Theme |
|---|---|---|
| `pub:WHSE_MINERAL_TENURE.GEOL_QUATERNARY_POLY` | `bronze_bc_quaternary_geology` | Quaternary / surficial geology |
| `pub:WHSE_MINERAL_TENURE.GEOL_BEDROCK_UNIT_POLY_SVW` | `bronze_bc_bedrock_geology` | Bedrock geology |
| `pub:WHSE_MINERAL_TENURE.GEOL_FAULT_LINE` | `bronze_bc_geological_faults` | Geological faults |

---

## 3. BC Soil Information Finder Tool (SIFT) — DataBC WFS

Soils data behind the [BC Soil Information Finder Tool (SIFT)](https://www2.gov.bc.ca/gov/content/environment/air-land-water/land/soil/soil-information-finder), fetched as GeoJSON over WFS from the BC Geographic Warehouse, clipped to the AOI bounding box.

| | |
|---|---|
| **Endpoint** | `https://openmaps.gov.bc.ca/geo/pub/wfs` |
| **Protocol** | WFS 2.0.0 `GetFeature`, `outputFormat=application/json`, `srsName=EPSG:4326` |
| **Auth** | None (public read) |
| **Feature cap** | 5000 features per layer |
| **Notebook** | `bronze_bc_soil_survey.ipynb` |

### Layers

| DataBC layer | Bronze table | Theme |
|---|---|---|
| `pub:WHSE_TERRESTRIAL_ECOLOGY.STE_SOIL_SURVEYS_MVW` | `bronze_bc_soil_survey_polygons` | Soil survey polygons (name, drainage, texture, parent material per component) |
| `pub:WHSE_TERRESTRIAL_ECOLOGY.STE_SOIL_PROJ_BOUNDARIES_SVW` | `bronze_bc_soil_project_boundaries` | Soil survey project boundaries / mapping study areas |

---

## Orchestration

`fabric/pipelines/pl_bronze_ingestion.json` runs both sources in parallel, then builds the overview maps:

```
Ingest_PC_Collections ─┐
                        ├─► Build_Overview
Ingest_BC_Geology ──────┘
```

## Notes

- All endpoints require outbound internet from the Spark host.
- Sources are public and anonymous; no credentials, keys, or token signing are configured.
- Only metadata (STAC item records, GeoJSON geometry + properties) lands in bronze. Downloading the underlying COGs/rasters is an intentional out-of-scope silver/gold concern.
