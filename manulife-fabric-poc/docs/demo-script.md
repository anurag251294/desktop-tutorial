# Manulife Fabric POC - Demo Script

**Duration**: 30 minutes
**Audience**: Manulife stakeholders (business and technical)
**Last Updated**: 2026-04-24

---

## 1. Demo Setup

### 1.1 Pre-Demo Checklist

| # | Item | Status |
|---|------|--------|
| 1 | Fabric workspace is accessible and all artifacts are visible | [ ] |
| 2 | Lakehouse tables are populated (Bronze, Silver, Gold layers) | [ ] |
| 3 | Semantic model is deployed and refreshed with latest data | [ ] |
| 4 | Power BI report is published and loads correctly | [ ] |
| 5 | Data Agent is configured and responding to queries | [ ] |
| 6 | Azure AI Search index is populated with policy documents | [ ] |
| 7 | Orchestration endpoint (Prompt Flow) is running and reachable | [ ] |
| 8 | Backup screenshots are saved locally in case of service issues | [ ] |
| 9 | Screen resolution set to 1920x1080 or higher | [ ] |
| 10 | Browser zoom set to 100% | [ ] |
| 11 | Notifications and popups disabled | [ ] |
| 12 | Demo environment has been tested end-to-end within 2 hours of demo | [ ] |

### 1.2 Browser Tabs to Have Open

Open the following tabs in order (left to right):

1. **Fabric Workspace** - Overview page showing all artifacts
2. **Lakehouse Explorer** - Showing the Gold layer tables
3. **Notebook 01** - Bronze ingestion notebook (01_bronze_ingestion.py)
4. **Semantic Model** - Model view showing relationships
5. **Power BI Report** - Executive dashboard
6. **Data Agent** - Chat interface ready for queries
7. **Architecture Diagram** - Reference architecture image (full screen)
8. **Azure Portal** - AI Search index (optional, for deep-dive questions)

### 1.3 Data Freshness Verification

Before the demo, confirm:
- Run `SELECT COUNT(*) FROM gold_customers` and verify expected row count
- Run `SELECT MAX(_ingestion_timestamp) FROM bronze_customers` and confirm it is recent
- Open the Power BI report and verify KPI tiles show non-zero values
- Send a test query to the Data Agent: "How many active customers do we have?"

---

## 2. Demo Flow (30 Minutes)

### Section 1: Opening (3 minutes)

**What to show**: Title slide or architecture diagram tab

**Script**:

> "Thank you for joining. Today we are going to walk through the Manulife Fabric Proof of Concept. The goal of this POC is to demonstrate how Microsoft Fabric can serve as the unified data foundation for Manulife's insurance and investment analytics.
>
> We set out to answer three questions:
> 1. Can we build a trusted, governed data foundation on OneLake with Bronze, Silver, and Gold layers?
> 2. Can we create a semantic model that provides consistent, trusted KPIs across the organization?
> 3. Can we enable business users to query this data using natural language through a Fabric Data Agent?
>
> The answer to all three is yes, and I will show you how."

**Key message**: Frame the demo around business outcomes, not technology.

**Transition**: "Let me start by showing you the architecture."

---

### Section 2: Architecture Overview (5 minutes)

**What to show**: Architecture diagram tab

**Script**:

> "Here is the reference architecture for the POC. Let me walk through the key layers.
>
> At the foundation, we have OneLake -- Microsoft's unified data lake. All data lives in one place, in open Delta format. There is no data duplication, no separate storage accounts to manage.
>
> The data flows through three layers:
> - **Bronze**: Raw data ingested as-is from source systems. We preserve the original data for auditability.
> - **Silver**: Cleaned, validated, and standardized. Data quality rules are applied here -- null checks, type validation, business rule enforcement.
> - **Gold**: Business-ready tables optimized for analytics. This is what the semantic model and reports consume.
>
> On top of the Gold layer, we have a Power BI semantic model that defines the business measures -- claims ratio, premium revenue, AUM, customer lifetime value. These measures are defined once and used everywhere.
>
> Finally, the Fabric Data Agent sits on top of the semantic model and the lakehouse, allowing business users to ask questions in plain English and get answers grounded in the actual data."

**Talking points**:
- OneLake eliminates data silos -- one copy of data, many consumers
- Delta format provides ACID transactions, time travel, and schema evolution
- The semantic model is the "single source of truth" for business metrics
- Security is enforced at every layer through Fabric's workspace model

**Anticipated questions**:
- *"How does this compare to our current Snowflake/Databricks setup?"* -- Fabric unifies compute and storage; OneLake acts as a single namespace. Direct Lake mode avoids data duplication between lake and BI.
- *"What about data sovereignty?"* -- Fabric workspaces can be pinned to specific regions. OneLake respects data residency policies.

**Transition**: "Now let me show you the data itself."

---

### Section 3: Data Foundation (5 minutes)

**What to show**: Lakehouse Explorer tab, then Notebook tab

**Script**:

> "Here is the Fabric Lakehouse. You can see the three layers -- Bronze, Silver, and Gold -- as Delta tables.
>
> [Click into gold_customers table]
>
> This is the Gold customers table. It has been cleaned, deduplicated, and enriched. Each record has a customer ID, name, region, segment, and acquisition date. Let me show you the row count -- we have [X] customer records in the Gold layer.
>
> [Switch to notebook tab]
>
> Here is the ingestion notebook. This is a PySpark notebook that reads raw CSV files from the lakehouse, adds ingestion metadata -- a timestamp, source file path, and batch ID -- and writes to Bronze Delta tables. This is fully automated and runs on a schedule.
>
> The key point here is governance. Every record has a lineage trail -- we know when it was ingested, from what source, and in which batch. This is critical for audit and compliance."

**Talking points**:
- Bronze layer preserves raw data for replay and audit
- Silver layer applies 15+ data quality rules (nulls, types, ranges, referential integrity)
- Gold layer is denormalized and optimized for query performance
- All tables are Delta format with full ACID guarantees
- Data quality metrics are captured and can be surfaced in a data quality dashboard

**Anticipated questions**:
- *"How often does the data refresh?"* -- Configurable per pipeline. For the POC, daily batch. Production can support near-real-time with Fabric's streaming capabilities.
- *"What happens if a source file is corrupt?"* -- The ingestion notebook logs errors per table. Failed tables don't block others. The Bronze layer always preserves the raw input.

**Transition**: "Now let me show you how this data becomes business-ready through the semantic model."

---

### Section 4: Semantic Model (5 minutes)

**What to show**: Semantic Model tab, then Power BI Report tab

**Script**:

> "Here is the Power BI semantic model. This is the business logic layer.
>
> [Show model diagram]
>
> You can see the relationships between customers, policies, claims, products, investments, and advisors. These relationships enable cross-table analysis -- for example, claims by customer region, or premium revenue by product category.
>
> [Show measures list]
>
> Here are the business measures we have defined. Claims Ratio, Total Premium Revenue, Active Customer Count, AUM, Average Claims Processing Time. These are defined in DAX and are consistent regardless of who queries them or from which report.
>
> [Switch to Power BI report]
>
> Here is a sample executive dashboard built on this semantic model. You can see:
> - Total premium revenue and trend
> - Claims ratio with target threshold
> - Active customer count by region
> - AUM breakdown by fund
>
> This is a traditional BI experience. But what if a business user wants to ask a question that is not on this dashboard?"

**Talking points**:
- Semantic model defines measures once, used across all reports and the Data Agent
- Direct Lake mode means the model queries Delta tables directly -- no data import or duplication
- DAX measures encode business logic (e.g., claims ratio = paid claims / earned premium, not just any division)
- Row-level security can be applied to control who sees what data

**Anticipated questions**:
- *"Can we add more measures?"* -- Absolutely. The model is extensible. New measures can be added without changing the underlying data.
- *"Does this replace existing Power BI reports?"* -- It can serve as the foundation for them. Existing reports can be re-pointed to this semantic model for consistency.

**Transition**: "Now here is where it gets interesting. Let me show you the Data Agent."

---

### Section 5: Data Agent Interaction (7 minutes)

**What to show**: Data Agent chat interface

**Script**:

> "This is the Fabric Data Agent. It is a natural language interface that is grounded on our semantic model and lakehouse data. Business users can ask questions in plain English and get answers backed by the actual data.
>
> Let me start with a simple question."

**Query 1 -- Simple KPI (1 min)**:
> Type: "How many active customers do we have?"
>
> "You can see it returns the count directly from the semantic model. No need to know SQL or DAX. No need to find the right report."

**Query 2 -- Aggregation (1.5 min)**:
> Type: "Show me total premium revenue by product category"
>
> "Now it is breaking down premium revenue by product category. This uses the DAX measures in the semantic model to ensure the calculation is consistent with what the finance team expects."

**Query 3 -- Trend Analysis (1.5 min)**:
> Type: "What is the claims ratio trend over the last 6 months?"
>
> "Here it is generating a time series analysis. The agent understands that 'trend' means it should group by time period and show the progression."

**Query 4 -- Row-Level Detail (1.5 min)**:
> Type: "Show me all policies expiring in the next 30 days"
>
> "Now it is querying the lakehouse SQL endpoint directly to pull row-level detail. This is not a pre-built report -- it is an ad-hoc query generated from the natural language question."

**Query 5 -- Document Enrichment (1.5 min)**:
> Type: "What does the policy say about the contestability period?"
>
> "This answer comes from our unstructured data layer. The agent searched through the indexed policy documents and retrieved the relevant section. This is the power of combining structured analytics with document context."

**Talking points**:
- The agent is grounded in the actual data, not a general-purpose LLM
- It respects the semantic model's measure definitions for consistency
- It can switch between aggregated KPIs and row-level detail based on the question
- Document enrichment adds context that pure data analysis cannot provide

**Anticipated questions**:
- *"How accurate is it?"* -- For queries that map to defined measures, accuracy is high because the agent uses pre-defined DAX. For ad-hoc SQL, accuracy depends on question clarity. We recommend few-shot examples for common query patterns.
- *"Can it handle French?"* -- Not in the current preview. French language support is on the roadmap.
- *"Who controls what data it can access?"* -- Fabric workspace security and semantic model RLS apply. The agent can only access data the user is authorized to see.

**Transition**: "Let me step back and talk about why this matters."

---

### Section 6: Architecture Positioning (3 minutes)

**What to show**: Architecture diagram

**Script**:

> "What we have demonstrated today is more than a set of features. It is an architecture pattern.
>
> OneLake as the unified data foundation eliminates data silos. One copy of data, governed centrally, accessible by all consumers -- notebooks, reports, agents, APIs.
>
> The semantic model is the trust layer. Business measures are defined once by the people who understand them, and every consumer -- whether it is a Power BI report, a Data Agent, or an API call -- gets the same answer.
>
> The Data Agent is the access layer. It democratizes data access. A claims adjuster does not need to learn SQL. A regional VP does not need to wait for a report to be built. They ask a question and get an answer.
>
> This is what Fabric enables that a collection of point solutions cannot: a unified, governed, accessible data platform."

**Key messages**:
- OneLake is the foundation -- data gravity matters
- Semantic model is the trust layer -- consistent KPIs across all consumers
- Data Agent is the access layer -- natural language democratizes data
- This is an architecture, not a tool -- it scales with the organization

**Transition**: "I would like to open it up for questions."

---

### Section 7: Q&A (2 minutes)

**Facilitation notes**:
- If no questions, prompt: "A common question we hear is about production readiness. Let me address that..."
- Have the risks-and-blockers document ready to reference for detailed technical questions
- For questions you cannot answer live, note them and commit to follow-up

---

## 3. Talking Points per Section

### Opening
- This POC was scoped to demonstrate feasibility, not build a production system
- We focused on the most common data domains: customers, policies, claims, products, investments
- The architecture is designed to scale to additional data domains without rearchitecting

### Architecture
- OneLake is not just a data lake -- it is a unified namespace that all Fabric workloads share
- Delta format is open source and avoids vendor lock-in
- The medallion architecture (Bronze/Silver/Gold) is an industry-standard pattern used by leading financial institutions

### Data Foundation
- 7 core tables ingested: customers, policies, claims, products, investments, advisors, transactions
- Data quality rules are applied at the Silver layer with measurable pass rates
- All data has full lineage through ingestion metadata

### Semantic Model
- Direct Lake mode is a Fabric differentiator -- no data movement between lake and BI
- DAX measures encode business rules, not just formulas
- The model can serve as the foundation for all downstream reporting and analytics

### Data Agent
- Currently in preview -- feature set is evolving rapidly
- Grounded in actual data, not trained on data -- no data leaves the Fabric boundary
- Best suited for exploratory analytics and self-service BI

### Architecture Positioning
- Competitors require stitching together 5-7 separate services
- Fabric provides one platform with unified security, governance, and administration
- OneLake is the strategic investment -- everything else builds on top

---

## 4. Backup Queries and Pre-Prepared Results

In the event of a live demo failure, use the following pre-prepared results:

### Backup 1: Active Customer Count

**Query**: "How many active customers do we have?"

**Pre-prepared response**:
> Based on the semantic model, Manulife currently has **12,456** active customers with at least one active policy.
>
> Breakdown by region:
> | Region | Active Customers |
> |--------|-----------------|
> | Ontario | 4,892 |
> | Quebec | 2,834 |
> | British Columbia | 1,956 |
> | Alberta | 1,623 |
> | Other Provinces | 1,151 |

### Backup 2: Premium Revenue by Product

**Query**: "Show me total premium revenue by product category"

**Pre-prepared response**:
> | Product Category | Premium Revenue (CAD) | Policy Count | Avg Premium |
> |-----------------|----------------------|--------------|-------------|
> | Term Life | $45,230,000 | 5,210 | $8,681 |
> | Whole Life | $38,120,000 | 2,890 | $13,190 |
> | Universal Life | $22,670,000 | 1,340 | $16,917 |
> | Health & Benefits | $18,450,000 | 3,780 | $4,881 |
> | Investment-Linked | $12,890,000 | 1,560 | $8,263 |

### Backup 3: Claims Ratio Trend

**Query**: "What is the claims ratio trend over the last 6 months?"

**Pre-prepared response**:
> | Month | Claims Ratio | Total Claims | Total Premium |
> |-------|-------------|-------------|---------------|
> | Nov 2025 | 62.3% | $7,480,000 | $12,010,000 |
> | Dec 2025 | 64.1% | $7,890,000 | $12,310,000 |
> | Jan 2026 | 61.8% | $7,620,000 | $12,330,000 |
> | Feb 2026 | 63.5% | $7,710,000 | $12,140,000 |
> | Mar 2026 | 60.9% | $7,440,000 | $12,210,000 |
> | Apr 2026 | 62.7% | $7,580,000 | $12,090,000 |
>
> The claims ratio has remained within the target range of 55-65% over the past 6 months, with a slight improvement trend.

### Backup 4: Policies Expiring

**Query**: "Show me all policies expiring in the next 30 days"

**Pre-prepared response**:
> | Policy ID | Customer | Product | Premium (CAD) | End Date |
> |-----------|----------|---------|---------------|----------|
> | POL-2025-1042 | Sarah Chen | Term Life T10 | $12,400 | 2026-05-01 |
> | POL-2025-0987 | James Williams | Whole Life | $18,200 | 2026-05-08 |
> | POL-2025-1156 | Priya Patel | Term Life T20 | $8,600 | 2026-05-12 |
> | POL-2025-0834 | Robert Martin | Universal Life | $22,100 | 2026-05-15 |
> | POL-2025-1203 | Lisa Thompson | Term Life T10 | $9,800 | 2026-05-22 |
>
> *Showing 5 of 23 policies expiring in the next 30 days. Full list available on request.*

### Backup 5: Document Query

**Query**: "What does the policy say about the contestability period?"

**Pre-prepared response**:
> According to the Manulife Individual Life Insurance Policy Terms (ML-LI-2025-ON), **Section 8.2 - Incontestability**:
>
> *"After this policy has been in force during the lifetime of the Insured Person for a period of two years from the Policy Date, it shall be incontestable except for non-payment of premiums or fraud."*
>
> Additionally, **Section 3.2 - Material Misrepresentation** states:
>
> *"During the Contestability Period, Manulife may rescind this policy if the application contained a material misrepresentation that influenced the acceptance of the risk or the terms of coverage."*
>
> **Source**: Azure AI Search (policy_terms_life_insurance.md)
> **Note**: Please verify with the legal team for authoritative interpretation.

---

## 5. Demo Recovery Procedures

| Issue | Recovery |
|-------|----------|
| Fabric workspace not loading | Switch to backup screenshots; narrate the experience |
| Data Agent not responding | Use backup queries above; explain the expected behavior |
| Semantic model refresh failed | Use the last successful report view; note that data may be from prior refresh |
| Network issues | Use locally saved screenshots and screen recordings |
| Unexpected error in live query | Acknowledge it ("preview software -- this is why we test"), move to next query |
| Audience asks to see something not prepared | Note the request and commit to follow-up; do not improvise in unfamiliar areas |

---

*This document is confidential and intended for internal use by Microsoft and Manulife project stakeholders.*
