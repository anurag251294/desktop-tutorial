---
title: Methods for RF-1 Soft-Soil Susceptibility
description: Methodology for the parameterized RF-1 geohazard screening workflow in Microsoft Fabric
ms.date: 2026-07-25
ms.topic: concept
---

## Overview

This document describes the methodology behind the geohazard demo: how the data is
ingested, how it is co-registered onto a common analysis grid, how the RF-1
soft-soil **Susceptibility (S)** and **Consequence (C)** ratings are derived, and how
they combine into a gold **risk matrix** (`risk_score = S × C`). It follows the
medallion architecture implemented across the seven Fabric notebooks
(`fabric/notebooks/`).

---

## 1. Study area (AOI)

| Parameter | Value |
| --- | --- |
| Centre | Pipeline `LATITUDE` and `LONGITUDE`; default `49.2193, -122.5984` |
| Bronze query radius | Pipeline `RADIUS_KM`; default 20 km |
| Silver analysis buffer | Pipeline `ANALYSIS_RADIUS_KM`; default 3 km, maximum 5 km |
| Analysis grid | 10 m in the centre point's local UTM zone |

The bronze layer uses a wider catalog radius for regional context. Silver and gold use
a separate, bounded detailed radius so the 10 m per-pixel workload remains tractable.
The default detailed radius creates a 6 km by 6 km square analysis grid.

---

## 2. Coordinate reference systems and projection handling

Two CRSs are used deliberately, each for the job it is suited to:

- **EPSG:4326 (WGS84 geographic, lat/lon)** — used for all *ingestion* queries: STAC
  bounding-box search against Microsoft Planetary Computer and OGC WFS `GetFeature`
  requests against DataBC. Raw geometries are stored in 4326 in the bronze layer.
- **Dynamic local UTM (metric)** — used for analysis. The silver notebook derives the
  UTM zone from longitude and selects the northern or southern EPSG family from
  latitude. Distances, slopes, and pixel areas remain metric while rasters align on a
  common grid. The supported UTM latitude range is 80°S to 84°N.

### 2.1 AOI bounding box from a radius

`radius_to_bbox(lat, lon, radius_km)` converts a kilometre radius to degree offsets
using an equirectangular approximation:

```text
lat_delta = radius_km / 111.32
lon_delta = radius_km / (111.32 · cos(lat))
bbox = [lon − lon_delta, lat − lat_delta, lon + lon_delta, lat + lat_delta]
       # → [min_lon, min_lat, max_lon, max_lat]
```

The `cos(lat)` term corrects for meridian convergence so the box is roughly square on
the ground. This planar approximation is appropriate for a catalogue-scale bbox.

### 2.2 WFS axis-order handling (the subtle part)

OGC WFS 2.0.0 honours the *authority-defined* axis order. For the URN form
`urn:ogc:def:crs:EPSG::4326`, EPSG defines the axis order as **(latitude, longitude)** —
**not** lon/lat. The DataBC bronze notebooks emit the bbox accordingly:

```python
BBOX_PARAM = f"{BBOX[1]},{BBOX[0]},{BBOX[3]},{BBOX[2]},urn:ogc:def:crs:EPSG::4326"
#             min_lat , min_lon , max_lat , max_lon , CRS-urn
```

`srsName=EPSG:4326` is also requested so returned geometries come back as lat/lon
GeoJSON. Getting this axis order wrong is the most common cause of "empty" or
"off-by-a-continent" WFS results; this is handled explicitly.

### 2.3 Always-XY transforms

All `pyproj.Transformer` instances are created with `always_xy=True`, so every
transform consumes and produces coordinates in **(x=lon/easting, y=lat/northing)**
order regardless of the CRS's native axis convention. This keeps the silver code
free of axis-order ambiguity.

---

## 3. Bronze layer — raw ingestion

The bronze layer stores raw source records (no analytics) as Delta tables in
`bronze_lakehouse`. Two source families:

### 3.1 Microsoft Planetary Computer (STAC metadata)

`bronze_pc_collections.ipynb` catalogues seven collections over the AOI bbox by
POSTing to the Planetary Computer STAC search API. Each row is a STAC **item record**
(id, datetime, asset hrefs, and the item bbox `bbox_minx/miny/maxx/maxy`) — the
pixels themselves are pulled later, on demand, in silver.

| Collection | Role in RF-1 |
| --- | --- |
| `sentinel-2-l2a` | optical surface reflectance → spectral indices |
| `sentinel-1-rtc` | C-band SAR → radar wetness |
| `cop-dem-glo-30` | 30 m DEM → slope, valley-bottom flatness |
| `esa-worldcover` | land cover → wetland/water flags, exposure |
| `io-lulc-9-class` | land use/land cover context |
| `alos-palsar-mosaic` | L-band SAR context |
| `hgb` | above/below-ground biomass context |

Sentinel-2 is filtered to the snow-free growing season (2024-06-01 / 2024-09-30) with
`eo:cloud_cover < 30`. The search retries bbox-only if a property-filtered search
returns nothing, so the demo degrades gracefully.

`bronze_planetary_ingestion.ipynb` is a simpler single-collection, parameterised
variant (Sentinel-2 only, append mode) kept for the CI/CD promotion demo.

### 3.2 DataBC WFS (vector ground truth)

Vector layers are fetched as GeoJSON over plain HTTP from the BC Geographic Warehouse
WFS (`https://openmaps.gov.bc.ca/geo/pub/wfs`), clipped to the AOI bbox, and stored
with `geometry_json` + `properties_json` preserved verbatim.

| Notebook | Bronze tables | Source layers |
| --- | --- | --- |
| `bronze_bc_surficial_geology.ipynb` | `bronze_bc_quaternary_geology`, `bronze_bc_bedrock_geology`, `bronze_bc_geological_faults` | surficial/bedrock geology, fault lines |
| `bronze_bc_soil_survey.ipynb` | `bronze_bc_soil_survey_polygons`, `bronze_bc_soil_project_boundaries` | BC Soil Information Finder Tool (SIFT) |

`bronze_data_overview.ipynb` is a read-only inspector: it lists every bronze table,
reports row/column counts, and renders each layer on its own folium map (live
Planetary Computer raster tiles for STAC tables, real GeoJSON for vector tables) with
click-through "every column" popups. No projection logic — folium consumes WGS84
directly.

---

## 4. Silver layer — RF-1 factor metrics + S/C ratings

`silver_rf1_soil_susceptibility.ipynb` produces one row per 10 m pixel.

### 4.1 Deterministic analysis grid

The centre point is projected to its local UTM zone, buffered by the selected detailed
radius, and snapped to the 10 m grid so the box is reproducible run-to-run:

```python
zone = min(60, max(1, floor((LON + 180) / 6) + 1))
epsg = (32600 if LAT >= 0 else 32700) + zone
UTM_CRS = f"EPSG:{epsg}"
cx, cy = to_utm.transform(LON, LAT)          # always_xy: (easting, northing)
half_m = ANALYSIS_RADIUS_KM * 1000
minx   = floor((cx − half_m) / 10) · 10      # snap origin to the 10 m grid
maxy   = ceil ((cy + half_m) / 10) · 10
W = H  = round(2 · half_m / 10)
GEOBOX = GeoBox((H, W), Affine(10, 0, minx, 0, −10, maxy), UTM_CRS)
```

The affine is standard north-up (positive x-step, negative y-step from the top-left
origin). The WGS84 search bbox is recovered by inverse-transforming the grid corners,
so the STAC search and the grid are guaranteed consistent.

### 4.2 Raster co-registration

Every raster source is searched on Planetary Computer over the selected analysis bbox,
signed, and
loaded with `odc.stac.load(items, geobox=GEOBOX, resampling=…)`. Because all sources
load onto the **same GeoBox**, they are reprojected and resampled to the identical
10 m UTM grid in one step and stack cleanly — no manual alignment. Bilinear resampling
is used for continuous rasters (reflectance, DEM, SAR); nearest for categorical
(WorldCover). Multi-date stacks are reduced with a skipna median.

### 4.3 Factor metrics

| Metric | Definition | Signal |
| --- | --- | --- |
| NDVI | (B08 − B04)/(B08 + B04) | vegetation |
| NDWI | (B03 − B08)/(B03 + B08) | open water (McFeeters) |
| BSI | ((B11+B04) − (B08+B02)) / ((B11+B04) + (B08+B02)) | bare soil |
| organic_idx | B11 / B12 (SWIR1/SWIR2) | organic-soil proxy |
| slope_deg | `degrees(arctan(hypot(∇z)))`, `∇z` from `np.gradient(z, 10, 10)` | steepness (metres → degrees, valid because the grid is metric) |
| vbf_proxy | flatness × lowness (MrVBF-style) | valley-bottom flatness |
| vv_db / vh_db | `10·log10(linear power)` | SAR backscatter / wetness |
| worldcover_class | ESA WorldCover code | land cover |

### 4.4 Soil-survey ground truth (BC SIFT)

The satellite/DEM/radar metrics are *indirect* proxies. The BC soil-survey polygons
are surveyed ground truth, so they get the largest single weight. Each polygon is
reprojected to UTM with `rasterio.warp.transform_geom("EPSG:4326", UTM_CRS, geom)`
and **rasterized onto the same (H, W) grid using `GEOBOX.affine`**. A keyword score maps
drainage/parent-material/texture text to a soft-soil weight (organic / very-poorly-
drained / gley → 1.0; fluvial / lacustrine / clay → ~0.7; mapped-but-unknown → 0.4).
The signal degrades to all-zero if the soil table is absent.

### 4.5 Susceptibility (S) and Consequence (C)

A soft-soil probability `P ∈ [0,1]` is an availability-weighted blend:

```text
P = 0.25·vbf + 0.20·soil + 0.15·(wetland/water) + 0.13·wet_radar
  + 0.12·wet_ndwi + 0.08·bare + 0.07·organic
```

Surveyed organic / very-poorly-drained ground forces `P ≥ 0.85`. `P` is binned to
**S ∈ {1..5}** at thresholds `[0.20, 0.40, 0.60, 0.80]`, with hard overrides: wetland +
VV < −15 dB → 5; open water → 5; surveyed soft soil → at least 4.

**C ∈ {1..5}** is an exposure proxy from WorldCover (built-up → 5, cropland → 4,
grass/shrub → 2–3, water/bare → 1), bumped +1 where slope > 15° (movement matters more
on slopes). Pixel centres are converted back to lon/lat via the inverse UTM transform
and stored alongside `utm_x/utm_y` for downstream mapping.

---

## 5. Gold layer — RF-1 risk matrix

`gold_rf1_risk_matrix.ipynb` reads the silver table and computes:

```text
risk_score = S × C            # 1..25
band: Low 1–4 · Moderate 5–9 · High 10–19 · Extreme 20–25
```

Four Delta tables are written:

| Table | Grain | Contents |
| --- | --- | --- |
| `gold_rf1_risk_pixels` | per 10 m pixel | S, C, risk_score, band, coordinates |
| `gold_rf1_risk_matrix` | per S×C cell (≤ 25 rows) | pixel_count, mean_risk, risk_score, band |
| `gold_rf1_band_summary` | per risk band | pixel_count, area_km² (`pixel_count × 10²/10⁶`), pct |
| `gold_rf1_risk_areas` | per populated risk band | dissolved WGS84 geometry, score range, pixel count, area, share, provenance |

The notebook polygonizes contiguous cells, dissolves them by risk band, and simplifies
the geometry by one grid cell while preserving topology. It writes run-scoped GeoJSON,
Shapefile components and ZIP, a web-map manifest, a self-contained Folium HTML map,
and a `_SUCCESS` marker under `Files/gold_rf1_webmap/runs/<run-id>/`. The notebook then
closes with the 5×5 matrix, 10 m grid view, and area-by-band bars.

---

## 6. Reproducibility notes

- **Determinism** — the UTM grid origin is snapped to the 10 m grid and the STAC bbox is
  derived from the grid corners, so re-runs produce the identical grid and the same
  pixels.
- **Cross-lakehouse reads** — silver and gold read upstream Delta tables by explicit
  `abfss://…/Tables` paths (workspace/lakehouse GUIDs), so each notebook can run with its
  own default lakehouse attached.
- **Season** — indices and radar use the 2024 snow-free window (Jun–Sep) to avoid snow
  and low-sun artefacts.
- **Graceful degradation** — missing optional sources (e.g. the soil table) collapse to a
  zero signal rather than failing the run.
