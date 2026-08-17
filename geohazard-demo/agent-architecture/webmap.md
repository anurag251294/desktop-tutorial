---
title: Geohazard Web Map Specification
description: Deterministic web-map layer, interaction, performance, and provenance design for the geohazard demo
ms.date: 2026-08-04
ms.topic: design
---

## Design rule

The web map renders computed artifacts. It does not ask the report agent to produce
GeoJSON, coordinates, bounds, tiles, legends, or colors. Report text can reference a
known `featureId`; the browser resolves that ID against the map manifest.

## Recommended browser stack

Use MapLibre GL JS with a compact report panel beside the map. Read all source URLs,
viewport values, legends, and feature properties from the validated web-map manifest.
Keep the report and map independently usable when either artifact is unavailable.

## Layer plan

| Order | Layer | Source | Representation | Default |
| --- | --- | --- | --- | --- |
| 1 | Basemap | Approved public or enterprise style | Raster/vector tiles | On |
| 2 | Bronze catalog AOI | Pipeline parameters | Circle plus bounding box | On |
| 3 | Detailed analysis AOI | Silver grid extent | Polygon outline | On |
| 4 | Risk surface | `gold_rf1_risk_pixels` | Raster tiles or image overlay | On |
| 5 | Hotspots | Deterministic top-N gold cells | Bounded GeoJSON points | On |
| 6 | Soil survey | Bronze soil polygons | Simplified vector tiles/GeoJSON | Off |
| 7 | Quaternary geology | Bronze geology polygons | Simplified vector tiles/GeoJSON | Off |
| 8 | Faults | Bronze fault lines | Simplified vector tiles/GeoJSON | Off |
| 9 | STAC footprints | Bronze item bounding boxes | Bounded GeoJSON polygons | Off |

The 10 m risk grid can exceed hundreds of thousands of features. Never send the full
grid as browser GeoJSON. Render it as a raster/image layer or vector tiles. Hotspot
GeoJSON is capped and deterministically ordered.

## Interactions

* Layer visibility and opacity controls
* Risk-band legend with Low, Moderate, High, and Extreme categories
* Click details for deterministic source properties and evidence IDs
* Report links that zoom to known hotspot feature IDs
* Reset-to-AOI control
* Source and generated-at provenance for the active layer
* Empty-coverage state that differs visually and textually from a measured zero

Do not place explanatory help text over the map. Use accessible labels, tooltips for
unfamiliar icons, keyboard-operable controls, and a non-color status label for each
risk band.

## Map adapter

The adapter reads completed, run-specific OneLake artifacts and returns only the
manifest and approved map assets. It verifies the completion marker, schema version,
run ID, content type, file size, and feature cap before serving content.

The gold notebook publishes the first implementation under
`gold_lakehouse/Files/gold_rf1_webmap/runs/<pipeline-run-id>/`. It dissolves the 10 m
grid into at most one MultiPolygon feature per populated risk band and writes GeoJSON,
Shapefile components and ZIP, a manifest, a Folium HTML map, and `_SUCCESS`. The
completion marker is written last, after every artifact is nonempty and the persisted
GeoJSON and manifest pass structural checks. Move to vector/raster tiles when geometry
size or concurrent use warrants a tile service. Keep the manifest contract unchanged.

## Browser validation

Before release, verify desktop and mobile layouts with screenshots and pixel checks.
Confirm that the map is nonblank, all default layers load, report links select the
correct feature, text does not overlap controls, and missing layers produce a clear
state rather than a JavaScript error.
