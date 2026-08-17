---
title: Geohazard Agent Architecture
description: Architecture package for grounding a Microsoft Foundry report agent in Fabric geohazard results and rendering a deterministic web map
ms.date: 2026-08-04
ms.topic: architecture
---

## Decision

The Fabric pipeline remains the system of record. Microsoft Foundry writes the
screening narrative from compact, versioned evidence. A separate map adapter publishes
deterministic layers from Fabric outputs. The model never creates coordinates,
geometries, risk scores, or map styling values.

The reference report model is `gpt-4.1-mini`, matching the current Microsoft Fabric
tool sample and providing a cost-conscious baseline for structured synthesis. Keep the
deployment name configurable so the implementation can move to a newer approved model
without changing contracts.

## Package contents

* [architecture.md](architecture.md) defines components, trust boundaries, data flow,
  failure behavior, and the recommended implementation sequence
* [fabric-data-agent.md](fabric-data-agent.md) defines the Fabric data agent scope,
  permissions, and allowed analytical questions
* [prompts/report-agent-system.md](prompts/report-agent-system.md) provides the Foundry
  report-agent system instructions
* [webmap.md](webmap.md) specifies map layers, interactions, performance limits, and
  provenance behavior
* [evaluation.md](evaluation.md) defines release gates for numerical fidelity,
  citations, schema adherence, and missing-data behavior
* [contracts/geohazard-report-input.schema.json](contracts/geohazard-report-input.schema.json)
  is the compact evidence envelope supplied to the agent
* [contracts/geohazard-report-output.schema.json](contracts/geohazard-report-output.schema.json)
  is the structured report returned by the model
* [contracts/webmap-manifest.schema.json](contracts/webmap-manifest.schema.json) describes
  map-ready artifacts without coupling the browser to Fabric internals

## Guardrails

* Treat every output as geohazard screening information, not engineering advice
* Require an evidence ID for every numerical or source-coverage statement
* Reject report output that references unknown evidence or map feature IDs
* Keep raw risk pixels out of the model context
* Keep model text out of geometry, layer URLs, bounds, and legends
* Use Microsoft Entra ID and least-privilege RBAC
* Mark the Fabric data agent path as preview and provide a deterministic batch fallback

## Recommended implementation order

1. Use the gold notebook's run-scoped web-map manifest, dissolved risk-area GeoJSON,
  Shapefile bundle, and HTML map under `Files/gold_rf1_webmap/runs/<run-id>/`.
2. Add a Fabric handoff notebook after gold to write the report input and output JSON
  contracts under `Files/agent-handoff/<run-id>/`, referencing the existing map
  manifest URI.
3. Publish a Fabric data agent over the gold tables for interactive follow-up questions.
4. Create the Foundry prompt agent with the supplied system instructions and structured
   report output.
5. Implement a map adapter that validates `_SUCCESS` and serves the bounded assets.
6. Build the browser experience from the report JSON and web-map manifest.
7. Add the evaluation gates before sharing the demo outside the project team.

The architecture is implementation-ready, but this folder intentionally contains no
hosted application or Azure deployment resources.
