# Geohazard workload context (RF-1 to RF-10)

This demo ingests satellite scene metadata into a bronze table to support screening-level geohazard workflows.

## Practical linkage to RF factors

- RF-7 Flooding and RF-8 Debris flow: scene metadata supports event window selection before flood/debris interpretation.
- RF-9 Erosion/scour: repeat acquisitions can be used to track channel migration and active bank zones.
- RF-6 Historical slope activity: historical image catalogs help establish evidence timelines for movement.
- RF-10 Groundwater/seepage: indirect support via wetness indicators and temporal persistence when combined with field data.

## Why this is a good CI/CD demo

- Parameterized ingestion makes behavior explicit and repeatable.
- Bronze write pattern is simple and auditable.
- Same notebook can be promoted across Dev/Test/Prod with only parameter changes.
- Geospatial workloads are realistic but still lightweight at metadata-ingestion level.

## Scope note

This repository demonstrates ingestion engineering patterns, not full hazard modeling. Detailed risk scoring and interpretation remain in downstream analytical layers.
