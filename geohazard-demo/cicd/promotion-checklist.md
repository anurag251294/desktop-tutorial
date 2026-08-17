# Fabric Promotion Checklist (Single Workspace Demo)

## 1. Workspace setup

- Create or open a Fabric workspace for the demo.
- Create a Lakehouse and attach it to the notebook.
- Import `fabric/notebooks/bronze_planetary_ingestion.ipynb`.
- Run with the values from `cicd/parameters.dev.json`.
- Validate that `bronze_satellite_stac_items` is created and populated.

## 2. Git integration

- Connect the workspace to a Git repo/branch.
- Commit notebook and supporting assets.
- Open PR and merge into your main branch.

## 3. Deployment pipeline

- Create a Fabric Deployment Pipeline.
- Assign the demo workspace to stage 0.
- Show the promotion path in the UI and explain that additional stage workspaces can be attached later when moving beyond the single-workspace demo.

## 4. Parameter controls

- Keep notebook code stable.
- Change only parameter values (date window, item limit, output table).

## 5. Demo talking points

- Same notebook logic stays repeatable and source-controlled.
- Source control captures exact notebook version and parameter intent.
- Deployment pipeline shows the governed promotion path even in single-workspace demo mode.
- Bronze layer remains raw/lightweight for downstream Silver transformations.
