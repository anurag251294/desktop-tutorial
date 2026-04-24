# Manulife Fabric POC — Copilot-Style Experience with Fabric Data Agent

## Overview

This repository contains the end-to-end Proof of Concept (POC) for Manulife's target architecture: a **standalone Copilot-style experience** powered by Microsoft Fabric, with **Fabric Data Agent** as the governed natural-language access layer, a **semantic model** for trusted KPIs and business logic, and **OneLake** as the shared data foundation.

The POC demonstrates how structured insurance/investment data and unstructured content (policy documents, guidelines, investment commentary) work together in a Fabric-oriented architecture for enterprise insight generation.

## Architecture Positioning

| Layer | Role |
|-------|------|
| **OneLake** | Enabling data foundation — single copy of data, open format, governed |
| **Semantic Model** | Business logic, measures, trusted KPIs via Power BI dataset |
| **Fabric Data Agent** | Natural-language query layer over OneLake + semantic model |
| **Copilot / Orchestration** | End-user conversational experience |
| **Unstructured Content** | Enrichment layer (RAG via Azure AI Search) — complements, does not replace, semantic model |

## Repository Structure

```
manulife-fabric-poc/
├── README.md                          # This file
├── architecture/
│   ├── reference-architecture.md      # Full reference architecture document
│   └── architecture-diagram.md        # Mermaid diagram definitions
├── docs/
│   ├── poc-runbook.md                 # Step-by-step implementation guide
│   ├── executive-summary.md           # Stakeholder-ready summary
│   ├── demo-script.md                 # 30-minute demo walkthrough
│   ├── validation-checklist.md        # POC validation criteria
│   └── risks-and-blockers.md          # Risks, blockers, open questions
├── data/
│   ├── raw/
│   │   ├── structured/                # Sample CSV datasets
│   │   │   ├── customers.csv
│   │   │   ├── policies.csv
│   │   │   ├── claims.csv
│   │   │   ├── products.csv
│   │   │   ├── investments.csv
│   │   │   ├── advisors.csv
│   │   │   └── transactions.csv
│   │   └── unstructured/              # Sample documents
│   │       ├── policy_terms_life_insurance.md
│   │       ├── policy_terms_health_insurance.md
│   │       ├── claims_processing_guidelines.md
│   │       ├── product_guide_wealth_management.md
│   │       ├── faq_customer_service.md
│   │       ├── investment_commentary_q1_2026.md
│   │       ├── advisor_handbook_compliance.md
│   │       └── annual_report_highlights_2025.md
│   └── curated/                       # Gold layer schema definitions
├── notebooks/
│   ├── 01_bronze_ingestion.py         # Raw → Bronze delta tables
│   ├── 02_silver_transformation.py    # Bronze → Silver (cleansing, enrichment)
│   ├── 03_gold_curated_layer.py       # Silver → Gold (star schema)
│   ├── 04_document_processing.py      # Unstructured doc chunking
│   └── 05_data_validation.py          # Quality checks and sample queries
├── pipelines/
│   └── pipeline_definitions.json      # Fabric pipeline reference definitions
├── semantic-model/
│   └── semantic-model-spec.md         # Full semantic model specification
├── agent-config/
│   └── data-agent-design.md           # Fabric Data Agent design and prompts
├── scripts/
│   └── setup_azure_resources.sh       # Azure resource provisioning reference
└── tests/
    └── data_quality_tests.py          # Automated data quality test suite
```

## Quick Start

1. **Read the runbook**: Start with `docs/poc-runbook.md` for step-by-step instructions
2. **Review architecture**: See `architecture/reference-architecture.md` for the full design
3. **Provision infrastructure**: Follow the prerequisites in the runbook
4. **Upload data**: Copy `data/raw/structured/*.csv` and `data/raw/unstructured/*.md` to your Fabric lakehouse
5. **Run notebooks**: Execute notebooks 01 through 05 in sequence
6. **Create semantic model**: Follow `semantic-model/semantic-model-spec.md`
7. **Configure Data Agent**: Follow `agent-config/data-agent-design.md`
8. **Validate**: Use `docs/validation-checklist.md`
9. **Demo**: Follow `docs/demo-script.md`

## Sample Business Questions

The POC is designed to answer questions like:

- "Which customers have the highest claim volume by policy type?"
- "Summarize the policy coverage and recent claims trend for customer X"
- "What product guidance should a service rep know before responding?"
- "Show total investment inflows by region and advisor segment"
- "What do the structured numbers show, and what supporting document context exists?"
- "Summarize key insights from both policy data and attached guidance documents"

## Prerequisites

- Microsoft Fabric capacity (F64+ recommended)
- Azure subscription with AI services (Azure OpenAI, Azure AI Search)
- Power BI Pro or Premium Per User license
- Fabric tenant admin settings: Copilot enabled, Data Agent enabled (preview)

## Key Documents

| Document | Audience | Purpose |
|----------|----------|---------|
| Executive Summary | C-level, stakeholders | What the POC proves and next steps |
| Reference Architecture | Architects, technical leads | Full design and component details |
| POC Runbook | Engineers | Step-by-step implementation |
| Semantic Model Spec | Data modelers, BI developers | Star schema and DAX measures |
| Data Agent Design | AI/ML engineers | Agent configuration and prompts |
| Demo Script | Sales engineers, presenters | 30-minute demo walkthrough |
| Risks & Blockers | Project managers, architects | Known limitations and mitigations |

## Status

| Component | Status |
|-----------|--------|
| Sample structured data | Ready |
| Sample unstructured documents | Ready |
| Data ingestion notebooks | Ready |
| Semantic model specification | Ready |
| Data Agent design | Ready |
| Reference architecture | Ready |
| POC runbook | Ready |

## License

Internal use only — Manulife POC engagement.
