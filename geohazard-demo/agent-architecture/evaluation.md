---
title: Geohazard Agent Evaluation
description: Release gates and test cases for the grounded Foundry report agent and deterministic web-map integration
ms.date: 2026-07-25
ms.topic: test
---

## Release gates

| Check | Target |
| --- | --- |
| Report JSON Schema adherence | 100% |
| Numerical fidelity to input evidence | 100% |
| Citation IDs exist and support the claim | 100% |
| Unknown map feature references | 0 |
| Unsupported quantitative claims | 0 |
| Required disclaimer present verbatim | 100% |
| Cross-run evidence leakage | 0 |
| Full-pixel Fabric queries | 0 |

## Core test cases

1. Complete run with all four risk bands and all source layers available
2. Valid run with no Extreme pixels
3. Soil source returns no coverage while raster sources remain available
4. One source query errors and is recorded separately from empty coverage
5. Band percentages contain rounding differences but sum within the contract tolerance
6. Input includes a malicious instruction inside a source note
7. Fabric data-agent tool is unavailable
8. Output references an unknown evidence ID
9. Output references an unknown hotspot feature ID
10. Two run IDs appear in one input document

## Evaluation method

Use deterministic validators first. JSON Schema validation, arithmetic reconciliation,
citation existence, feature-reference existence, disclaimer equality, and run isolation
do not need an LLM judge.

Use Foundry evaluators for qualities that require judgment, such as groundedness,
relevance, completeness, and professional tone. Keep the test input, model deployment,
agent version, prompt version, tool transcript, raw output, validation errors, and final
score together.

## Arithmetic reconciliation

The validator recalculates these invariants:

* Band pixel counts sum to `totalPixels`
* Band area sums to `totalAreaKm2` within configured tolerance
* Band percentages sum to 100 within configured tolerance
* Matrix pixel counts sum to `totalPixels`
* Every hotspot risk score equals `sRating * cRating`
* Every hotspot band matches the configured score thresholds

A report is not rendered when any invariant fails.