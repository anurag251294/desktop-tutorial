# Manulife Fabric POC - Executive Summary

**Prepared for**: Manulife Financial - Data & Analytics Leadership
**Prepared by**: Microsoft Advisory Team
**Date**: April 2026
**Classification**: Confidential

---

## What This POC Demonstrates

The Manulife Fabric Proof of Concept demonstrates that Microsoft Fabric can serve as a unified, governed data foundation for insurance and investment analytics -- from raw data ingestion through to natural language access by business users.

In four weeks, the POC delivered:

- **A complete data pipeline** ingesting seven core data domains (customers, policies, claims, products, investments, advisors, transactions) through Bronze, Silver, and Gold layers with full data quality enforcement and lineage tracking
- **A semantic model** with 10+ business measures (claims ratio, premium revenue, AUM, customer lifetime value, policy retention rate) that provides a single source of truth for KPIs across all consumers
- **A natural language interface** via Fabric Data Agent that allows business users to query structured data and retrieve policy document context without SQL or BI tool expertise
- **An unstructured data integration** pattern that combines Manulife policy documents with structured analytics through Azure AI Search

The POC validates that Fabric can deliver the core capabilities Manulife needs for a modern analytics platform, with clear paths from proof of concept to production.

---

## Why OneLake Matters as the Data Foundation

Today, Manulife's data landscape involves multiple storage systems, ETL platforms, and analytics tools. Data moves between systems, creating copies, inconsistencies, and governance gaps. OneLake changes this equation.

**OneLake is a single, unified data lake** that all Fabric workloads share. Data is stored once in open Delta format and accessed by notebooks, pipelines, reports, and AI agents without duplication. This delivers three critical benefits:

1. **One copy of data**: Eliminates inconsistencies between systems. When the claims table is updated, every consumer -- from the Power BI dashboard to the Data Agent -- sees the same data immediately.

2. **Open format, no lock-in**: Delta (Parquet-based) is an open standard. Data in OneLake can be accessed by non-Microsoft tools if needed, protecting Manulife's investment.

3. **Unified governance**: Security, access control, sensitivity labels, and lineage are managed centrally across all data and all consumers. This is critical for regulatory compliance (OSFI, PIPEDA, provincial regulators).

For Manulife, OneLake represents a strategic consolidation point -- a single namespace for all analytical data, governed consistently and accessible to all authorized users and applications.

---

## The Role of the Semantic Model

The semantic model is the **trust layer** between raw data and business users. It defines what "claims ratio" means, how "premium revenue" is calculated, and how tables relate to each other. This matters because:

- **Consistency**: Every report, dashboard, and Data Agent query uses the same measure definitions. When the CFO sees a claims ratio of 62.3%, the regional VP sees the same number.
- **Business logic preservation**: Calculations that encode business rules (e.g., earned premium vs. written premium, net vs. gross claims) are defined once by domain experts and reused everywhere.
- **Performance**: Fabric's Direct Lake mode allows the semantic model to query Delta tables directly without importing data, eliminating refresh delays and data duplication.

The POC semantic model includes 10+ measures across claims, premium, investment, and customer domains, with a relationship model connecting all seven data tables.

---

## How the Fabric Data Agent Enables Natural Language Access

The Fabric Data Agent is an AI-powered interface that allows business users to ask questions in plain English and receive answers grounded in the actual data. This is not a general-purpose chatbot -- it is constrained to the data in the semantic model and lakehouse.

**What it enables today**:
- "What is our total premium revenue?" -- Returns the exact figure from the semantic model
- "Show me claims by policy type and region" -- Generates the appropriate aggregation
- "List all policies expiring this month" -- Queries the lakehouse for row-level detail
- "What does the policy say about the contestability period?" -- Retrieves relevant document sections (via orchestration)

**Why this matters for Manulife**:
- A claims adjuster can check claim history without submitting a report request
- A regional VP can get portfolio metrics during a client meeting without opening Power BI
- A product manager can explore customer segments without waiting for the analytics team
- An executive can verify a KPI before a board presentation in seconds

The Data Agent is currently in public preview. The POC validates the interaction patterns and identifies the areas where the preview delivers well today and where GA maturity is needed.

---

## What is Feasible Now vs. Roadmap Dependent

| Capability | Status | Notes |
|-----------|--------|-------|
| OneLake data foundation (Bronze/Silver/Gold) | **Production-ready** | GA since November 2023. Proven at scale. |
| Data pipelines and notebooks | **Production-ready** | GA. Full PySpark support. Scheduling, monitoring, alerting available. |
| Semantic model with Direct Lake | **Production-ready** | GA. Recommended for all new deployments. |
| Power BI reporting | **Production-ready** | GA. Industry-leading BI platform. |
| Data Agent (structured queries) | **Preview** | Functional for single-source queries. Query accuracy improves with few-shot examples. |
| Data Agent (multi-source grounding) | **Preview / Limited** | Single grounding source per agent today. Multi-source expected H2 2026. |
| Native RAG in Data Agent | **Roadmap** | Not yet available. Currently requires external orchestration (Prompt Flow). |
| French language support | **Roadmap** | Required for Canadian market. Expected 2026-2027. |

**Bottom line**: The data foundation, semantic model, and reporting layers are production-ready today. The Data Agent delivers meaningful value in preview but will require GA maturity for enterprise deployment.

---

## Key Outcomes

1. **Feasibility confirmed**: End-to-end flow from raw data to natural language query is working and demonstrable
2. **Architecture validated**: The medallion architecture on OneLake with a semantic model and Data Agent is a viable pattern for Manulife's analytics modernization
3. **Data quality enforced**: 15+ quality rules applied at the Silver layer with measurable pass rates
4. **Semantic model operational**: 10+ business measures defined and validated against expected results
5. **Natural language access demonstrated**: Data Agent successfully answers structured queries, row-level lookups, and document-context questions
6. **Gaps identified**: Multi-source grounding, French language, and production-grade security controls require GA maturity or additional engineering

---

## Recommendations

### Immediate (Next 30 Days)

1. **Approve Phase 2 scope** focusing on production data integration with Manulife's actual source systems (Guidewire, Manulife Investment Management systems, SAP)
2. **Establish a semantic model governance process** with business stakeholders owning measure definitions
3. **Begin Azure AI Search index curation** for the document corpus that will support production RAG queries

### Medium-Term (60-90 Days)

4. **Pilot the Data Agent** with a controlled user group (e.g., 10-15 claims analysts) to collect real-world feedback
5. **Implement row-level security** in the semantic model aligned with Manulife's access control policies
6. **Expand the data model** to include Group Benefits and Wealth Management domains

### Strategic

7. **Position OneLake as the enterprise data foundation** for all analytical workloads, replacing fragmented storage
8. **Adopt the semantic model as the enterprise metric layer** to ensure KPI consistency across business lines
9. **Plan for GA readiness** of the Data Agent by maintaining the orchestration layer as a bridge to native capabilities

---

## Next Steps

| Action | Owner | Target Date |
|--------|-------|-------------|
| Review POC outcomes and approve Phase 2 | Manulife Data Leadership | May 2026 |
| Define Phase 2 scope and data sources | Joint Microsoft/Manulife | May 2026 |
| Begin production data integration design | Microsoft Advisory | June 2026 |
| Pilot Data Agent with controlled user group | Joint | June 2026 |
| Semantic model governance workshop | Joint | May 2026 |

---

*This document is confidential and prepared for Manulife Financial leadership. Distribution outside the intended audience requires written approval.*
