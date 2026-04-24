# Manulife Microsoft Fabric POC -- Reference Architecture

| Field               | Value                                                        |
|---------------------|--------------------------------------------------------------|
| **Document Owner**  | Microsoft Partner / Manulife Data & Analytics                |
| **Version**         | 1.0 -- DRAFT                                                 |
| **Status**          | POC / Pre-Pilot                                              |
| **Last Updated**    | 2026-04-24                                                   |
| **Classification**  | Confidential -- Manulife Internal + Microsoft                |

---

## Table of Contents

1. [Business Objective](#1-business-objective)
2. [Architecture Overview](#2-architecture-overview)
3. [Logical Architecture](#3-logical-architecture)
4. [Component Responsibilities](#4-component-responsibilities)
5. [Data Flow](#5-data-flow)
6. [Assumptions](#6-assumptions)
7. [Dependencies](#7-dependencies)
8. [Platform Prerequisites](#8-platform-prerequisites)
9. [Security and Governance](#9-security-and-governance)
10. [Known Limitations / Preview Dependencies](#10-known-limitations--preview-dependencies)
11. [Potential First-Adopter Blockers](#11-potential-first-adopter-blockers)
12. [Pilot Scope Recommendation](#12-pilot-scope-recommendation)
13. [Customer Follow-Up Questions](#13-customer-follow-up-questions)
14. [Future-State Enhancements](#14-future-state-enhancements)

---

## 1. Business Objective

### 1.1 Strategic Context

Manulife is a leading international financial services group that provides insurance,
wealth and asset management, and banking solutions. The company operates across
Canada, the United States (as John Hancock), and Asia, serving millions of customers
with a portfolio spanning life insurance, group benefits, retirement services,
investment management, and banking products.

Manulife's data estate is large, heterogeneous, and distributed across business
units, geographies, and legacy platforms. Decision-makers -- actuaries, claims
analysts, investment portfolio managers, product owners, and executive leadership --
need timely, trusted, and contextual access to data to drive business outcomes.

### 1.2 POC Objective

This Proof of Concept (POC) demonstrates how **Microsoft Fabric** can serve as
Manulife's unified analytics platform, enabling business users to interact with
trusted data through **natural language** without requiring SQL, DAX, or
report-building expertise.

The POC validates the following hypothesis:

> By layering a **Fabric Data Agent** on top of a curated **semantic model** backed
> by **OneLake**, and enriching the experience with unstructured document retrieval
> via **Azure AI Search** and **Azure OpenAI**, Manulife can deliver a
> conversational analytics experience that is accurate, governed, and extensible.

### 1.3 Key Outcomes

| # | Outcome                                                                 | Measure of Success                                                  |
|---|-------------------------------------------------------------------------|---------------------------------------------------------------------|
| 1 | Business users ask questions in plain English and receive accurate answers | Data Agent returns correct KPIs for 90%+ of test questions          |
| 2 | Answers are grounded in a governed semantic model with trusted measures   | All numeric answers trace to DAX measures in the semantic model     |
| 3 | Unstructured policy/claims documents can be retrieved contextually        | RAG pipeline returns relevant document excerpts for 80%+ of queries |
| 4 | The experience is delivered through a standalone Copilot interface        | End-to-end demo from question to answer in a custom UI              |
| 5 | The platform is production-ready from a governance perspective            | RLS, audit logging, and data classification are demonstrated        |

### 1.4 Design Principles

The architecture is guided by the following principles:

| Principle                        | Description                                                                                                      |
|----------------------------------|------------------------------------------------------------------------------------------------------------------|
| **Semantic model is the brain**  | All business logic, KPI definitions, relationships, and measures live in the Power BI semantic model. The Data Agent queries this model, not raw tables. This ensures a single source of truth for business metrics. |
| **OneLake is the foundation**    | OneLake provides the unified storage layer across bronze, silver, and gold zones. It is the enabling infrastructure, not the headline. Users never interact with OneLake directly. |
| **Conversation is the interface**| The end-user experience is a conversational Copilot. Users ask questions; the system translates, executes, and explains. |
| **Unstructured enriches, not replaces** | Document retrieval (policy PDFs, guidelines, FAQs) supplements the semantic model with context. It does not replace structured KPI answers. |
| **Governance by design**         | Row-level security, data classification, lineage, and audit trails are built into every layer, not bolted on. |
| **Incremental, not monolithic**  | The architecture is designed for a focused pilot scope that can expand to additional business domains without rearchitecting. |

### 1.5 Target Personas

| Persona                    | Role Description                                                     | Primary Questions                                                                                   |
|----------------------------|----------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------|
| **Claims Analyst**         | Reviews and processes insurance claims                               | "What is our average claims processing time this quarter?" / "Show me high-value open claims."      |
| **Product Owner**          | Manages insurance/investment product portfolio                       | "Which products have the highest lapse rate?" / "What is the renewal rate by product category?"     |
| **Investment Analyst**     | Monitors investment portfolio performance                            | "What is the YTD return on our equity portfolio?" / "Show AUM by asset class."                      |
| **Advisor Manager**        | Oversees financial advisor network                                   | "Which advisors have the highest client retention?" / "Show advisor performance by region."         |
| **Actuary**                | Assesses risk and pricing                                            | "What is the loss ratio by product line?" / "Show claims frequency trends."                         |
| **Executive / VP**         | Strategic decision-making                                            | "Give me a summary of Q1 performance." / "What are the top risk indicators?"                        |
| **Compliance Officer**     | Regulatory and policy compliance                                     | "Are there any claims that exceed the auto-approval threshold?" / "Show audit trail for policy X."  |

---

## 2. Architecture Overview

### 2.1 Positioning Statement

The architecture is layered with clear separation of concerns:

```
Layer 5 (Top)     Copilot / Conversational Experience      <-- What users see
Layer 4           Orchestration (Azure OpenAI + routing)    <-- Decides how to answer
Layer 3           Fabric Data Agent + Azure AI Search       <-- Executes queries
Layer 2           Semantic Model (Power BI Dataset)         <-- Business logic & KPIs
Layer 1           OneLake (Lakehouse: Bronze/Silver/Gold)   <-- Data foundation
Layer 0 (Bottom)  Source Systems + Unstructured Content     <-- Raw data
```

**Critical positioning:**

- **OneLake** is the enabling data foundation. It stores, organizes, and governs
  data. It is essential infrastructure but not the user-facing value proposition.
  Users never see or interact with OneLake directly.

- **The Semantic Model** is the business logic layer. It contains DAX measures,
  calculated columns, relationships, hierarchies, and role-level security. When the
  Data Agent answers "What is the loss ratio?", it is executing a DAX measure
  defined in the semantic model -- not running a raw SQL query against lakehouse
  tables.

- **The Fabric Data Agent** is the natural language query layer. It translates
  user questions into DAX queries against the semantic model (for structured data)
  or routes to Azure AI Search (for document retrieval). It is the intelligence
  bridge between human language and governed data.

- **Copilot / Orchestration** is the conversational experience layer. This is what
  Manulife users see and interact with -- a chat interface where they type questions
  and receive answers with charts, tables, and document excerpts.

- **Unstructured content** (policy PDFs, claims guidelines, FAQ documents) is an
  enrichment layer. It provides context, definitions, and supporting documentation.
  It does not replace the semantic model for KPI answers.

### 2.2 Why This Layering Matters

| Anti-Pattern                                              | This Architecture                                                      |
|-----------------------------------------------------------|------------------------------------------------------------------------|
| Users query raw lakehouse tables directly                 | Users query a governed semantic model with trusted KPI definitions      |
| LLM generates arbitrary SQL against raw data              | Data Agent generates DAX against a curated model with guardrails       |
| Unstructured docs are the primary answer source           | Structured KPIs come from the semantic model; docs provide context     |
| OneLake is marketed as the "answer engine"                | OneLake is the storage foundation; the semantic model is the brain     |
| Security is applied at the storage layer only             | Security is layered: storage (OneLake), model (RLS), agent (persona)  |

### 2.3 High-Level Architecture Summary

The architecture consists of the following major components working together:

1. **Data Sources** -- Structured data (CSV/Parquet files representing customers,
   policies, claims, products, investments, advisors, transactions) and unstructured
   content (policy PDFs, claims guidelines, FAQ documents, product notes, investment
   commentary, advisor handbooks).

2. **OneLake (Lakehouse)** -- The unified data foundation organized in three zones:
   - **Bronze**: Raw ingested data, schema-on-read, full fidelity copy of source
   - **Silver**: Cleansed, validated, and conformed data with standard schemas
   - **Gold**: Curated star-schema dimensional model optimized for analytics

3. **Fabric Pipelines** -- Orchestrate data movement from source systems into OneLake
   Bronze zone. Handle scheduling, error handling, and incremental loading.

4. **Fabric Notebooks** -- PySpark/Python notebooks that transform data through the
   medallion architecture (Bronze to Silver to Gold). Implement data quality rules,
   business transformations, and star-schema modeling.

5. **Semantic Model (Power BI Dataset)** -- The business logic layer containing:
   - Dimensional relationships (star schema)
   - DAX measures for all KPIs (loss ratio, claims processing time, AUM, etc.)
   - Hierarchies (time, geography, product)
   - Row-level security (RLS) roles
   - DirectLake mode for real-time query performance

6. **Fabric Data Agent** -- Natural language query layer (currently in preview) that:
   - Accepts plain-English questions from users
   - Translates questions to DAX queries against the semantic model
   - Can also query lakehouse SQL endpoints for ad-hoc exploration
   - Returns formatted answers with optional visualizations

7. **Azure AI Search** -- Indexes unstructured documents (PDFs, Word docs) to enable:
   - Full-text search across policy documents and guidelines
   - Vector search (with Azure OpenAI embeddings) for semantic retrieval
   - RAG (Retrieval-Augmented Generation) for contextual document answers

8. **Azure OpenAI** -- Provides:
   - Text embeddings for vector indexing in Azure AI Search
   - LLM orchestration for combining structured answers (from Data Agent) with
     unstructured context (from Azure AI Search)
   - Response generation and summarization

9. **Standalone Copilot Experience** -- The user-facing interface:
   - Custom web application or Power BI embedded experience
   - Chat-based interaction model
   - Combines structured KPI answers with document context
   - Supports follow-up questions and conversation history

---

## 3. Logical Architecture

### 3.1 Narrative Description

The logical architecture follows a medallion pattern for data processing, a semantic
layer for business logic, and an AI layer for natural language interaction. Each
layer has a distinct responsibility, and data flows upward from sources through
processing to consumption.

**Data Ingestion Layer:**
Source data enters the platform through Fabric Pipelines. Structured data (CSV and
Parquet files representing customers, policies, claims, products, investments,
advisors, and transactions) is landed in the OneLake Bronze zone as-is. The Bronze
zone preserves full fidelity of source data with minimal transformation -- only
adding ingestion metadata (timestamp, source identifier, batch ID). Fabric Pipelines
handle scheduling (daily or event-driven), error handling (retry logic, dead-letter
logging), and incremental loading (watermark-based or change-data-capture patterns).

Unstructured content (policy PDFs, claims guidelines, FAQ documents, product notes,
investment commentary, advisor handbooks) follows a parallel path. Documents are
stored in OneLake for governance and lineage, and simultaneously indexed in Azure AI
Search. The indexing process uses Azure OpenAI to generate text embeddings for
vector search capability, enabling semantic (meaning-based) retrieval in addition to
keyword search.

**Data Transformation Layer:**
Fabric Notebooks (PySpark/Python) process data through the medallion architecture:

- **Bronze to Silver**: Data quality validation (null checks, type casting, range
  validation), deduplication, schema standardization, and business rule application.
  For example, policy status codes from different source systems are mapped to a
  standard enumeration. Date fields are normalized to a consistent format. Customer
  records are deduplicated using fuzzy matching logic.

- **Silver to Gold**: Dimensional modeling to create a star schema optimized for
  analytics. Fact tables (fact_claims, fact_transactions, fact_policy_events) are
  joined with dimension tables (dim_customer, dim_product, dim_advisor, dim_date,
  dim_geography) through surrogate keys. Slowly changing dimensions (SCD Type 2) are
  implemented for customers and products to preserve historical context. Aggregate
  tables are created for common query patterns.

**Semantic Layer:**
The Gold zone tables are surfaced through a Power BI semantic model (dataset) that
serves as the single source of truth for business metrics. The semantic model
contains:

- **Relationships**: Star schema relationships between fact and dimension tables,
  enabling cross-filtering and drill-down.
- **Measures**: DAX measures that encode business logic. For example:
  - `Loss Ratio = DIVIDE([Total Claims Paid], [Total Premiums Earned])`
  - `Avg Claims Processing Days = AVERAGEX(fact_claims, DATEDIFF(...))`
  - `AUM = SUMX(fact_investments, [Units] * [NAV])`
  - `Policy Lapse Rate = DIVIDE([Lapsed Policies], [In-Force Policies])`
- **Hierarchies**: Time (Year > Quarter > Month > Day), Geography (Country >
  Province > City), Product (Category > Line > Product).
- **Row-Level Security**: Dynamic RLS based on user identity, restricting data
  visibility by region, business unit, or advisor assignment.
- **DirectLake Mode**: Connects directly to Delta tables in OneLake for real-time
  query performance without data duplication.

**AI and Query Layer:**
The Fabric Data Agent sits on top of the semantic model and provides natural language
query capability. When a user asks "What is our loss ratio for group benefits this
quarter?", the Data Agent:

1. Interprets the natural language question
2. Maps it to the appropriate DAX measure (`Loss Ratio`) and filters (product
   category = "Group Benefits", time = current quarter)
3. Executes the DAX query against the semantic model
4. Returns the result in a formatted response

For questions that require unstructured context (e.g., "What does our claims
guideline say about auto-approval thresholds?"), the orchestration layer routes
the question to Azure AI Search, retrieves relevant document chunks, and uses
Azure OpenAI to generate a contextual answer.

**Conversational Experience Layer:**
The standalone Copilot experience is the user-facing interface. It is a custom
web application (or Power BI embedded experience) that provides:

- A chat interface for natural language interaction
- Routing logic that determines whether a question should go to the Data Agent
  (for structured data/KPI questions) or to the RAG pipeline (for document/policy
  questions), or both (for hybrid questions)
- Response formatting with tables, charts, and document citations
- Conversation history and follow-up question support
- User authentication and persona-based experience customization

### 3.2 Zone Descriptions

#### 3.2.1 Bronze Zone (Raw / Landing)

| Attribute            | Description                                                         |
|----------------------|---------------------------------------------------------------------|
| **Purpose**          | Full-fidelity copy of source data                                   |
| **Format**           | Delta tables (converted from CSV/Parquet on ingest)                 |
| **Schema**           | Schema-on-read; preserves source column names and types             |
| **Retention**        | 90 days minimum (configurable)                                      |
| **Access**           | Data engineers only                                                 |
| **Transformations**  | Minimal: add ingestion_timestamp, source_system, batch_id           |
| **Quality**          | No quality enforcement; raw data preserved for reprocessing         |

**Bronze tables:**

| Table                     | Source Description                        | Approx. Rows (POC) |
|---------------------------|-------------------------------------------|---------------------|
| `bronze_customers`        | Customer master data                      | 50,000              |
| `bronze_policies`         | Policy records with coverage details      | 100,000             |
| `bronze_claims`           | Claims submissions and adjudications      | 200,000             |
| `bronze_products`         | Product catalog and attributes            | 500                 |
| `bronze_investments`      | Investment holdings and transactions      | 500,000             |
| `bronze_advisors`         | Financial advisor profiles                | 5,000               |
| `bronze_transactions`     | Financial transactions (premiums, payouts)| 1,000,000           |

#### 3.2.2 Silver Zone (Cleansed / Conformed)

| Attribute            | Description                                                         |
|----------------------|---------------------------------------------------------------------|
| **Purpose**          | Cleansed, validated, and standardized data                          |
| **Format**           | Delta tables with enforced schemas                                  |
| **Schema**           | Standardized column names, data types, and enumerations             |
| **Retention**        | Indefinite (with compaction)                                        |
| **Access**           | Data engineers and data analysts                                    |
| **Transformations**  | Deduplication, type casting, null handling, code standardization    |
| **Quality**          | Data quality rules enforced; rejected records logged                |

**Silver tables:**

| Table                     | Key Transformations                                                |
|---------------------------|--------------------------------------------------------------------|
| `silver_customers`        | Deduplicated, address standardized, SCD Type 2 history             |
| `silver_policies`         | Status codes standardized, dates normalized, coverage parsed       |
| `silver_claims`           | Claim types mapped, amounts validated, duplicate claims flagged    |
| `silver_products`         | Product hierarchy enforced, attributes validated                   |
| `silver_investments`      | NAV validated, currency converted to CAD, holdings reconciled      |
| `silver_advisors`         | Credentials validated, territory assignments current               |
| `silver_transactions`     | Transaction types standardized, amounts reconciled                 |

#### 3.2.3 Gold Zone (Curated / Star Schema)

| Attribute            | Description                                                         |
|----------------------|---------------------------------------------------------------------|
| **Purpose**          | Analytics-optimized star schema for semantic model consumption      |
| **Format**           | Delta tables optimized for DirectLake                               |
| **Schema**           | Dimensional model with surrogate keys                               |
| **Retention**        | Indefinite                                                          |
| **Access**           | Semantic model (DirectLake), data analysts, report developers       |
| **Transformations**  | Star schema modeling, surrogate key generation, aggregations        |
| **Quality**          | Business rule validation; referential integrity enforced            |

**Gold tables -- Dimensions:**

| Table                | Description                                    | Key Columns                                                    |
|----------------------|------------------------------------------------|----------------------------------------------------------------|
| `dim_customer`       | Customer dimension (SCD Type 2)                | customer_key, customer_id, name, segment, province, is_current |
| `dim_product`        | Product dimension with hierarchy               | product_key, product_id, name, category, line, type            |
| `dim_advisor`        | Advisor dimension                              | advisor_key, advisor_id, name, region, territory, tier         |
| `dim_date`           | Date dimension (calendar + fiscal)             | date_key, date, year, quarter, month, fiscal_year, fiscal_qtr  |
| `dim_geography`      | Geography dimension                            | geo_key, country, province, city, region                       |
| `dim_claim_type`     | Claim type dimension                           | claim_type_key, claim_type, category, sub_category             |
| `dim_investment_type`| Investment type dimension                      | inv_type_key, asset_class, sub_class, risk_rating              |

**Gold tables -- Facts:**

| Table                  | Description                              | Key Measures                                                     |
|------------------------|------------------------------------------|------------------------------------------------------------------|
| `fact_claims`          | Claims fact table                        | claim_amount, paid_amount, reserved_amount, processing_days      |
| `fact_policies`        | Policy events fact table                 | premium_amount, coverage_amount, policy_count                    |
| `fact_transactions`    | Financial transactions                   | transaction_amount, fee_amount, net_amount                       |
| `fact_investments`     | Investment holdings snapshots            | units, nav_per_unit, market_value, book_value                    |
| `fact_advisor_metrics` | Advisor performance aggregates           | client_count, aum, retention_rate, new_business_volume           |

### 3.3 Unstructured Content Architecture

Unstructured documents follow a parallel path alongside the structured data pipeline:

**Document Sources:**

| Document Type              | Description                                          | Format  | Approx. Count (POC) |
|----------------------------|------------------------------------------------------|---------|----------------------|
| Policy Documents           | Full policy terms, conditions, and riders             | PDF     | 200                  |
| Claims Guidelines          | Internal claims adjudication procedures               | PDF/DOCX| 50                   |
| FAQ Documents              | Customer-facing and internal FAQ compilations          | PDF/DOCX| 30                   |
| Product Notes              | Product feature summaries and comparison sheets        | PDF     | 100                  |
| Investment Commentary      | Monthly/quarterly investment outlook and commentary    | PDF     | 50                   |
| Advisor Handbook           | Advisor onboarding, compliance, and operational guides | PDF     | 20                   |

**Indexing Pipeline:**

1. Documents are uploaded to OneLake (for storage and governance lineage)
2. An Azure Function or Fabric Notebook extracts text from PDFs (using Azure AI
   Document Intelligence or PyPDF)
3. Extracted text is chunked (e.g., 512-token overlapping chunks)
4. Azure OpenAI generates embeddings for each chunk
5. Chunks and embeddings are indexed in Azure AI Search
6. The index supports both keyword search and vector (semantic) search

**Retrieval Flow:**

1. User asks a document-related question
2. The orchestration layer identifies this as a document query
3. Azure AI Search retrieves the top-K relevant chunks
4. Azure OpenAI synthesizes a response grounded in the retrieved chunks
5. The response includes citations (document name, page number, relevance score)

---

## 4. Component Responsibilities

### 4.1 OneLake (Lakehouse)

| Attribute              | Description                                                                                                 |
|------------------------|-------------------------------------------------------------------------------------------------------------|
| **Role**               | Unified data foundation and storage layer                                                                   |
| **Responsibility**     | Store all structured data across bronze, silver, and gold zones in Delta format. Provide ABFSS endpoints for compute engines. Serve as the single copy of data for the entire platform. |
| **What it is NOT**     | OneLake is not a query engine, not a business logic layer, and not a user-facing component. Users never interact with OneLake directly. |
| **Storage Format**     | Delta Lake (Parquet + transaction log)                                                                       |
| **Access Protocols**   | ABFSS (Azure Blob File System), SQL Analytics Endpoint (auto-generated), OneLake file API                   |
| **Governance**         | Microsoft Purview integration for data classification and lineage. OneLake data access roles for fine-grained permissions. |
| **Key Configuration**  | Single Fabric workspace with one lakehouse per zone (or one lakehouse with schema-based zone separation)    |
| **POC Sizing**         | < 10 GB total across all zones (synthetic/sample data)                                                       |
| **DirectLake**         | Gold zone tables are consumed by the semantic model in DirectLake mode -- no data copy into the model       |

### 4.2 Fabric Pipelines

| Attribute              | Description                                                                                                 |
|------------------------|-------------------------------------------------------------------------------------------------------------|
| **Role**               | Data ingestion and orchestration                                                                             |
| **Responsibility**     | Move data from source files (CSV/Parquet in OneLake or external storage) into the Bronze zone. Handle scheduling, retry logic, and ingestion metadata tagging. Orchestrate end-to-end pipeline runs (ingest, transform, refresh). |
| **Key Activities**     | Copy Activity (source to Bronze), scheduling (daily/hourly), parameterization (source paths, watermarks), error handling (retry, dead-letter), orchestration (trigger notebook runs after ingest) |
| **Integration**        | Triggers Fabric Notebooks for Bronze-to-Silver and Silver-to-Gold transformations. Triggers semantic model refresh after Gold zone update. |
| **Monitoring**         | Built-in Fabric monitoring hub for pipeline run history, duration, and error tracking                       |
| **POC Scope**          | 2-3 pipelines: one for initial full load, one for incremental refresh, one for orchestration                |

### 4.3 Fabric Notebooks

| Attribute              | Description                                                                                                 |
|------------------------|-------------------------------------------------------------------------------------------------------------|
| **Role**               | Data transformation and quality enforcement                                                                  |
| **Responsibility**     | Transform data through the medallion architecture. Implement data quality rules, business transformations, deduplication, schema standardization, and star-schema dimensional modeling. |
| **Runtime**            | Apache Spark (PySpark / Python)                                                                              |
| **Key Notebooks**      | `01_bronze_to_silver.py` (cleansing), `02_silver_to_gold.py` (star schema), `03_data_quality_checks.py` (validation), `04_document_processing.py` (PDF text extraction and chunking) |
| **Libraries**          | PySpark, Delta Lake, pandas, PyPDF2 / pdfplumber (for document processing), openai (for embeddings)        |
| **Scheduling**         | Triggered by Fabric Pipelines after data ingestion completes                                                 |
| **Output**             | Delta tables in Silver and Gold zones; document chunks for Azure AI Search indexing                          |

### 4.4 Semantic Model (Power BI Dataset)

| Attribute              | Description                                                                                                 |
|------------------------|-------------------------------------------------------------------------------------------------------------|
| **Role**               | Business logic layer and single source of truth for KPIs                                                    |
| **Responsibility**     | Define all business measures (DAX), dimensional relationships, hierarchies, display formatting, and row-level security. This is the "brain" of the analytics platform -- all KPI answers originate from DAX measures defined here. |
| **Mode**               | DirectLake (preferred) or Import                                                                             |
| **Key Measures**       | See detailed measure catalog below                                                                           |
| **Relationships**      | Star schema: fact tables joined to dimension tables via surrogate keys                                       |
| **RLS**                | Dynamic row-level security based on user principal name (UPN) mapped to region/advisor/business unit         |
| **Refresh**            | DirectLake: automatic (no scheduled refresh needed). Import: triggered after Gold zone pipeline completes.  |
| **Data Agent Compat.** | Semantic model must be published to a Fabric workspace. Data Agent queries the model via DAX.               |

**Key Measures Catalog:**

| Measure Name                    | DAX Logic (Simplified)                                              | Business Definition                                      |
|---------------------------------|---------------------------------------------------------------------|----------------------------------------------------------|
| Total Premiums Earned           | `SUM(fact_policies[premium_amount])`                                | Total premium revenue collected                          |
| Total Claims Paid               | `SUM(fact_claims[paid_amount])`                                     | Total claims payments made                               |
| Loss Ratio                      | `DIVIDE([Total Claims Paid], [Total Premiums Earned])`              | Claims paid as a percentage of premiums earned           |
| Avg Claims Processing Days      | `AVERAGE(fact_claims[processing_days])`                             | Average days from claim submission to resolution         |
| Open Claims Count               | `CALCULATE(COUNT(fact_claims[claim_id]), fact_claims[status]="Open")`| Number of claims currently open                          |
| Policy Count (In-Force)         | `CALCULATE(COUNT(fact_policies[policy_id]), fact_policies[status]="Active")` | Number of currently active policies             |
| Policy Lapse Rate               | `DIVIDE([Lapsed Policies], [Total Policies at Start of Period])`    | Percentage of policies that lapsed in the period         |
| AUM (Assets Under Management)   | `SUM(fact_investments[market_value])`                               | Total market value of investment holdings                 |
| Net New Business                 | `[New Policies] - [Lapsed Policies]`                                | Net change in policy count                               |
| Advisor Retention Rate           | `DIVIDE([Retained Clients], [Total Clients at Start])`              | Percentage of clients retained by advisor                |
| YTD Investment Return            | Complex time-intelligence measure                                   | Year-to-date return on investment portfolio              |
| Claims Frequency                 | `DIVIDE([Total Claims], [Total Policies])`                          | Average number of claims per policy                      |
| Average Policy Value             | `AVERAGE(fact_policies[coverage_amount])`                           | Average coverage amount per policy                       |
| Client Acquisition Cost          | `DIVIDE([Total Acquisition Spend], [New Clients])`                  | Cost to acquire a new client                             |
| Surrender Rate                   | `DIVIDE([Surrendered Policies], [In-Force Policies])`               | Percentage of policies surrendered                       |

### 4.5 Fabric Data Agent

| Attribute              | Description                                                                                                 |
|------------------------|-------------------------------------------------------------------------------------------------------------|
| **Role**               | Natural language query layer                                                                                 |
| **Responsibility**     | Translate user questions from plain English into DAX queries against the semantic model. Optionally query lakehouse SQL analytics endpoints for ad-hoc exploration. Return formatted answers. |
| **Current Status**     | **Public Preview** (as of early 2025). GA timeline not confirmed.                                           |
| **Query Targets**      | Primary: Semantic model (DAX). Secondary: Lakehouse SQL analytics endpoint.                                 |
| **Capabilities**       | Natural language to DAX translation, question disambiguation, follow-up questions, basic visualization      |
| **Limitations**        | Does not natively index or search PDF/unstructured documents. Cannot perform cross-workspace queries in preview. Limited to semantic models in DirectLake or Import mode (not LiveConnect or Composite). |
| **Integration**        | Exposed via Fabric workspace. Can be called programmatically via API (preview).                              |
| **Positioning**        | The Data Agent is the bridge between human language and governed data. It ensures that answers are grounded in the semantic model, not arbitrary SQL. |

### 4.6 Azure AI Search

| Attribute              | Description                                                                                                 |
|------------------------|-------------------------------------------------------------------------------------------------------------|
| **Role**               | Unstructured document retrieval and search                                                                   |
| **Responsibility**     | Index unstructured documents (policy PDFs, claims guidelines, FAQs) for full-text and vector (semantic) search. Serve as the retrieval component in the RAG pattern. |
| **Index Types**        | Full-text index (BM25) + vector index (HNSW with Azure OpenAI embeddings)                                  |
| **Chunking Strategy**  | 512-token chunks with 128-token overlap. Metadata preserved (document name, page number, section title).    |
| **Embedding Model**    | Azure OpenAI `text-embedding-ada-002` or `text-embedding-3-small`                                           |
| **Search Modes**       | Keyword search, vector search, hybrid search (keyword + vector with RRF fusion)                             |
| **Skillsets**          | Optional: Azure AI Document Intelligence for structured extraction from complex PDFs                         |
| **Security**           | Azure RBAC for index management. Document-level security via security filters on search queries.            |
| **POC Sizing**         | Basic or Standard tier. ~450 documents, ~10,000 chunks.                                                     |

### 4.7 Azure OpenAI

| Attribute              | Description                                                                                                 |
|------------------------|-------------------------------------------------------------------------------------------------------------|
| **Role**               | LLM orchestration, embeddings, and response generation                                                       |
| **Responsibility**     | Generate text embeddings for Azure AI Search vector index. Orchestrate multi-source answers (combine structured KPI results from Data Agent with unstructured context from AI Search). Generate natural language responses. |
| **Models**             | `gpt-4o` or `gpt-4-turbo` for orchestration/generation. `text-embedding-3-small` for embeddings.           |
| **Deployment Region**  | Canada East or Canada Central (for Manulife data residency requirements)                                    |
| **Token Limits**       | GPT-4o: 128K context window. Embedding: 8K tokens per request.                                              |
| **System Prompt**      | Custom system prompt defining the agent persona (Manulife analytics assistant), guardrails (only answer from provided context), and response formatting (tables, citations). |
| **Content Safety**     | Azure AI Content Safety enabled. Custom blocklists for sensitive financial terms if needed.                  |
| **Integration**        | Called by the orchestration layer (custom app or Azure Functions) to combine Data Agent results with AI Search results. |

### 4.8 Standalone Copilot Experience

| Attribute              | Description                                                                                                 |
|------------------------|-------------------------------------------------------------------------------------------------------------|
| **Role**               | User-facing conversational interface                                                                         |
| **Responsibility**     | Provide a chat-based experience where Manulife users ask questions and receive answers combining structured KPIs and unstructured document context. Handle conversation history, question routing, response formatting, and user authentication. |
| **Options**            | (a) Custom web app (React/Next.js) with Azure OpenAI backend. (b) Power BI embedded with Copilot. (c) Microsoft Teams bot. (d) Copilot Studio agent. |
| **POC Recommendation** | Custom web app for maximum control, or Copilot Studio for fastest time-to-demo.                             |
| **Routing Logic**      | Classifies each question as: (1) Structured/KPI -- route to Data Agent, (2) Document/Policy -- route to AI Search + OpenAI, (3) Hybrid -- route to both and combine. |
| **Response Format**    | Text answers with optional tables, charts (rendered client-side), and document citations (with page numbers). |
| **Authentication**     | Microsoft Entra ID (Azure AD) SSO. User identity passed through to semantic model for RLS enforcement.      |
| **Conversation History**| Maintained in session (in-memory or Azure Cosmos DB for persistence).                                       |

---

## 5. Data Flow

### 5.1 Structured Data Flow (Source to Answer)

| Step | Component              | Action                                                                                      | Output                          |
|------|------------------------|---------------------------------------------------------------------------------------------|---------------------------------|
| 1    | Source Systems         | Structured data files (CSV/Parquet) are made available                                      | Raw files                       |
| 2    | Fabric Pipelines       | Copy Activity ingests files into OneLake Bronze zone                                        | Bronze Delta tables             |
| 3    | Fabric Notebooks       | PySpark transforms Bronze to Silver (cleanse, validate, standardize)                        | Silver Delta tables             |
| 4    | Fabric Notebooks       | PySpark transforms Silver to Gold (star schema, surrogate keys, aggregations)               | Gold Delta tables               |
| 5    | Semantic Model         | DirectLake mode connects to Gold zone tables. DAX measures, relationships, RLS defined.     | Published semantic model        |
| 6    | Fabric Data Agent      | Configured to query the published semantic model                                            | Data Agent endpoint             |
| 7    | User (Copilot)         | User types a question: "What is our loss ratio for group benefits this quarter?"            | Natural language question       |
| 8    | Orchestration Layer    | Routes question to Data Agent (classified as structured/KPI question)                       | Routing decision                |
| 9    | Fabric Data Agent      | Translates question to DAX: `CALCULATE([Loss Ratio], dim_product[category]="Group Benefits", dim_date[quarter]=CURRENTQUARTER)` | DAX query + result |
| 10   | Copilot Experience     | Formats result: "The loss ratio for Group Benefits this quarter is 67.3%"                   | Formatted response to user      |

### 5.2 Unstructured Data Flow (Document to Answer)

| Step | Component              | Action                                                                                      | Output                          |
|------|------------------------|---------------------------------------------------------------------------------------------|---------------------------------|
| 1    | Document Sources       | Policy PDFs, guidelines, FAQs are uploaded to OneLake (document storage area)               | Raw documents in OneLake        |
| 2    | Fabric Notebooks       | Extract text from PDFs (PyPDF / Document Intelligence)                                      | Extracted text                  |
| 3    | Fabric Notebooks       | Chunk text (512 tokens, 128 overlap) and generate metadata                                  | Text chunks with metadata       |
| 4    | Azure OpenAI           | Generate embeddings for each chunk (`text-embedding-3-small`)                               | Vector embeddings               |
| 5    | Azure AI Search        | Index chunks with text + embeddings + metadata                                              | Searchable index                |
| 6    | User (Copilot)         | User asks: "What does our claims guideline say about auto-approval thresholds?"             | Natural language question       |
| 7    | Orchestration Layer    | Routes question to RAG pipeline (classified as document/policy question)                    | Routing decision                |
| 8    | Azure AI Search        | Hybrid search (keyword + vector) retrieves top-5 relevant chunks                            | Retrieved document chunks       |
| 9    | Azure OpenAI           | Generates answer grounded in retrieved chunks with citations                                | Generated response              |
| 10   | Copilot Experience     | Formats result with answer text and source citations (document, page)                       | Formatted response to user      |

### 5.3 Hybrid Flow (Structured + Unstructured)

| Step | Component              | Action                                                                                      | Output                          |
|------|------------------------|---------------------------------------------------------------------------------------------|---------------------------------|
| 1    | User (Copilot)         | User asks: "What is our current loss ratio, and what factors does the guidelines say drive high loss ratios?" | Natural language question |
| 2    | Orchestration Layer    | Classifies as hybrid question. Splits into: (a) KPI sub-question, (b) document sub-question | Two sub-queries                 |
| 3a   | Fabric Data Agent      | Answers KPI: "Loss ratio is 67.3%"                                                          | Structured answer               |
| 3b   | Azure AI Search + AOAI | Retrieves guidelines content about loss ratio drivers                                       | Document context                |
| 4    | Azure OpenAI           | Combines both results into a unified response                                               | Combined answer                 |
| 5    | Copilot Experience     | Presents: KPI answer + document context + citations                                         | Formatted response to user      |

### 5.4 Data Refresh Cadence

| Data Type                   | Refresh Frequency         | Trigger                                  |
|-----------------------------|---------------------------|------------------------------------------|
| Structured data (Bronze)    | Daily (or on-demand)      | Fabric Pipeline schedule or manual trigger|
| Bronze to Silver            | Immediately after ingest  | Pipeline orchestration                    |
| Silver to Gold              | Immediately after Silver  | Pipeline orchestration                    |
| Semantic model              | Automatic (DirectLake)    | No explicit refresh needed                |
| Document index              | On document upload        | Event-driven or daily batch               |
| Data Agent                  | Real-time                 | Queries semantic model live               |

---

## 6. Assumptions

### 6.1 Data Assumptions

| # | Assumption                                                                                          |
|---|-----------------------------------------------------------------------------------------------------|
| 1 | POC will use synthetic or anonymized data that mimics Manulife's actual data schema and volumes.     |
| 2 | Structured source data will be provided as CSV or Parquet files. No direct connection to Manulife production systems during POC. |
| 3 | Data volumes for POC are modest (< 10 GB total across all zones). Production volumes will be significantly larger. |
| 4 | A minimum of 7 entity types will be represented: customers, policies, claims, products, investments, advisors, transactions. |
| 5 | Unstructured documents will be provided as PDFs. Other formats (DOCX, XLSX) may be supported but are not primary. |
| 6 | Date ranges will cover at least 2 fiscal years to demonstrate time-intelligence measures. |
| 7 | Data will include enough variety in product types, geographies, and claim types to demonstrate filtering and drill-down. |

### 6.2 Platform Assumptions

| # | Assumption                                                                                          |
|---|-----------------------------------------------------------------------------------------------------|
| 1 | A Fabric capacity (F64 or higher) is provisioned in a Canadian Azure region.                         |
| 2 | The Fabric tenant has Copilot and Data Agent preview features enabled by the tenant admin.           |
| 3 | Azure OpenAI is deployed in Canada East or Canada Central with GPT-4o and embedding models available.|
| 4 | Azure AI Search is provisioned in the same region as Azure OpenAI for latency optimization.          |
| 5 | Microsoft Entra ID is configured for user authentication with appropriate group memberships.          |
| 6 | The POC team has Fabric workspace admin, Azure subscription contributor, and Azure OpenAI access.    |

### 6.3 Organizational Assumptions

| # | Assumption                                                                                          |
|---|-----------------------------------------------------------------------------------------------------|
| 1 | Manulife stakeholders will be available for bi-weekly reviews and feedback sessions.                  |
| 2 | Subject matter experts (actuaries, claims analysts) will validate KPI definitions and test questions. |
| 3 | IT security and compliance teams will review the architecture before production deployment.           |
| 4 | The POC is time-boxed to 6-8 weeks.                                                                  |
| 5 | A defined set of 20-30 test questions will be agreed upon for Data Agent accuracy measurement.        |

---

## 7. Dependencies

### 7.1 Microsoft Fabric Dependencies

| Dependency                             | Required For                                  | Risk if Unavailable                                    |
|----------------------------------------|-----------------------------------------------|--------------------------------------------------------|
| Fabric capacity (F64+)                 | All Fabric workloads                          | Cannot proceed with POC                                |
| Fabric Data Agent (Preview)            | Natural language query experience             | Must fall back to Power BI Q&A (less capable)          |
| DirectLake mode                        | Real-time semantic model queries              | Must use Import mode (adds refresh latency)            |
| Copilot tenant setting                 | Copilot features in Fabric                    | Must use API-based Data Agent access only              |
| OneLake data access roles              | Fine-grained lakehouse security               | Must use workspace-level security only                 |

### 7.2 Azure Dependencies

| Dependency                             | Required For                                  | Risk if Unavailable                                    |
|----------------------------------------|-----------------------------------------------|--------------------------------------------------------|
| Azure OpenAI (Canada region)           | Embeddings and LLM orchestration              | Must use US region (data residency concern)            |
| Azure AI Search                        | Document retrieval / RAG                      | No unstructured document answering capability           |
| Azure AI Document Intelligence         | Complex PDF extraction (tables, forms)        | Must use basic PDF text extraction (lower quality)     |
| Microsoft Entra ID                     | Authentication and RLS                        | No personalized security; demo-only mode               |

### 7.3 Data Dependencies

| Dependency                             | Required For                                  | Risk if Unavailable                                    |
|----------------------------------------|-----------------------------------------------|--------------------------------------------------------|
| Synthetic data generation              | POC demonstrations                            | Must use generic sample data (less compelling demo)    |
| KPI definitions from Manulife SMEs     | Accurate DAX measures                         | Measures may not match Manulife business definitions   |
| Sample policy/claims PDFs              | Document retrieval demo                       | Must use generic insurance documents                   |
| Test questions from business users     | Accuracy measurement                          | Cannot validate Data Agent quality                     |

---

## 8. Platform Prerequisites

### 8.1 Fabric Configuration

| Prerequisite                                    | Owner              | Status    |
|-------------------------------------------------|--------------------|-----------|
| Fabric capacity provisioned (F64+ in Canada)    | Manulife IT / MS   | Required  |
| Fabric workspace created with proper licensing  | POC Team           | Required  |
| Copilot enabled at tenant level                 | Fabric Admin       | Required  |
| Data Agent preview enabled                      | Fabric Admin       | Required  |
| OneLake data access roles configured            | POC Team           | Required  |
| Lakehouse created with Bronze/Silver/Gold areas | POC Team           | Required  |

### 8.2 Azure Configuration

| Prerequisite                                    | Owner              | Status    |
|-------------------------------------------------|--------------------|-----------|
| Azure subscription with sufficient quota        | Manulife IT        | Required  |
| Azure OpenAI resource (Canada East/Central)     | POC Team           | Required  |
| GPT-4o deployment with sufficient TPM           | POC Team           | Required  |
| text-embedding-3-small deployment               | POC Team           | Required  |
| Azure AI Search resource (Standard tier)        | POC Team           | Required  |
| Azure AI Document Intelligence (optional)       | POC Team           | Optional  |
| Microsoft Entra ID app registration             | Manulife IT        | Required  |
| Azure Key Vault for secrets                     | POC Team           | Required  |

### 8.3 Development Environment

| Prerequisite                                    | Owner              | Status    |
|-------------------------------------------------|--------------------|-----------|
| Fabric workspace with contributor access        | POC Team           | Required  |
| Git integration configured for Fabric workspace | POC Team           | Recommended|
| VS Code with Fabric extension (optional)        | POC Team           | Optional  |
| Python 3.10+ for local development              | POC Team           | Required  |
| Azure CLI for resource provisioning             | POC Team           | Required  |

---

## 9. Security and Governance

### 9.1 Security Architecture

Security is implemented at every layer of the architecture:

| Layer                    | Security Mechanism                                   | Description                                                  |
|--------------------------|------------------------------------------------------|--------------------------------------------------------------|
| **Authentication**       | Microsoft Entra ID (Azure AD)                        | All users authenticate via Entra ID. SSO across Fabric and Azure services. |
| **Authorization**        | Fabric workspace roles                               | Admin, Member, Contributor, Viewer roles control workspace access. |
| **Data Layer**           | OneLake data access roles                            | Fine-grained read/write permissions on lakehouse tables and folders. |
| **Semantic Layer**       | Row-Level Security (RLS)                             | DAX-based RLS filters data based on user identity and role mappings. |
| **Document Layer**       | Azure AI Search security filters                     | Document-level security trimming on search queries.           |
| **API Layer**            | Azure RBAC + Managed Identity                        | Service-to-service authentication using managed identities.   |
| **Network Layer**        | Private endpoints (production)                       | VNet integration for Fabric, Azure OpenAI, AI Search (production scope). |
| **Data Classification**  | Microsoft Purview sensitivity labels                 | Automatic and manual classification of data assets.           |
| **Audit**                | Fabric audit logs + Azure Monitor                    | All data access, query execution, and admin actions logged.   |
| **Encryption**           | At-rest (platform-managed keys) + in-transit (TLS 1.2+) | All data encrypted at rest and in transit.                |

### 9.2 Row-Level Security Design

The semantic model implements dynamic RLS to ensure users only see data they are
authorized to access:

| RLS Role              | Filter Logic                                         | Applicable Personas                     |
|-----------------------|------------------------------------------------------|-----------------------------------------|
| Regional Filter       | `dim_geography[region] = USERPRINCIPALNAME() mapping`| Regional managers, advisors             |
| Business Unit Filter  | `dim_product[business_unit] = <user BU mapping>`     | Product owners, BU-specific analysts    |
| Advisor Filter        | `dim_advisor[advisor_id] = <user advisor mapping>`   | Individual advisors (see own data only) |
| Full Access           | No filter (all data visible)                         | Executives, actuaries, compliance       |

**RLS Mapping Table:**
A `security_mapping` table in the Gold zone maps Entra ID user principal names (UPNs)
to their authorized regions, business units, and advisor IDs. The RLS rules reference
this mapping table.

### 9.3 Data Residency

| Requirement                                          | Implementation                                                |
|------------------------------------------------------|---------------------------------------------------------------|
| Data must reside in Canada                           | All resources provisioned in Canada Central or Canada East     |
| No data leaves Canadian Azure regions                | Azure OpenAI and AI Search deployed in Canadian regions        |
| PII handling                                         | Synthetic data for POC; production will require PII masking/tokenization |
| Data retention                                       | POC data retained for duration of engagement only              |

### 9.4 Governance Framework

| Governance Area            | Tool / Process                                           |
|----------------------------|----------------------------------------------------------|
| Data Catalog               | Microsoft Purview (discover, classify, govern data assets)|
| Data Lineage               | Fabric lineage view (pipeline to lakehouse to model)     |
| Data Quality               | Custom quality checks in Fabric Notebooks + Purview DQ   |
| Change Management          | Git integration for Fabric artifacts (notebooks, pipelines)|
| Access Reviews             | Entra ID access reviews for workspace and resource access |
| Incident Response          | Azure Monitor alerts for pipeline failures, anomalous queries |
| KPI Governance             | Semantic model as single source of truth; change control on DAX measures |

---

## 10. Known Limitations / Preview Dependencies

### 10.1 Fabric Data Agent Limitations

| Limitation                                                      | Impact                                                    | Mitigation                                              |
|-----------------------------------------------------------------|-----------------------------------------------------------|---------------------------------------------------------|
| **Preview status** (as of early 2025)                           | Features may change, no SLA, potential instability        | Document preview dependencies; plan for GA migration    |
| **No native PDF/document indexing**                             | Data Agent cannot answer questions from PDFs directly     | Sidecar architecture with Azure AI Search + OpenAI      |
| **Semantic model compatibility**                                | Only Import and DirectLake modes supported                | Use DirectLake; avoid LiveConnect and Composite models   |
| **Limited cross-workspace queries**                             | Data Agent cannot query models in other workspaces        | Keep all artifacts in a single workspace for POC         |
| **DAX generation quality**                                      | Complex multi-step DAX may be incorrect                   | Validate with test question suite; provide model descriptions |
| **No conversation memory across sessions**                      | Each session starts fresh                                 | Implement session persistence in the custom Copilot app |
| **Limited visualization**                                       | Data Agent returns text/tables; chart support is basic    | Custom visualization in the Copilot app frontend        |
| **No custom instructions persistence (preview)**                | Agent instructions may reset                              | Re-apply instructions programmatically at session start  |

### 10.2 Fabric Platform Limitations

| Limitation                                                      | Impact                                                    | Mitigation                                              |
|-----------------------------------------------------------------|-----------------------------------------------------------|---------------------------------------------------------|
| **Copilot is tenant-level opt-in**                              | Cannot enable for specific users/groups only              | Coordinate with Fabric admin for tenant-wide enablement  |
| **Cross-workspace lineage limited in preview**                  | Lineage tracking across workspaces incomplete             | Use single workspace for POC; track lineage manually     |
| **DirectLake fallback to DirectQuery**                          | Large or complex queries may fall back, impacting perf    | Optimize Gold zone tables; monitor query plans           |
| **Notebook environment startup time**                           | Spark session cold start can take 30-60 seconds           | Use High Concurrency mode or Starter Pools               |
| **Git integration limitations**                                 | Not all artifact types supported in Git                   | Manual export/backup for unsupported artifacts           |

### 10.3 Azure AI Search Limitations

| Limitation                                                      | Impact                                                    | Mitigation                                              |
|-----------------------------------------------------------------|-----------------------------------------------------------|---------------------------------------------------------|
| **Vector search dimension limits**                              | Max 3072 dimensions per vector field                      | Use text-embedding-3-small (1536 dims) -- well within limit |
| **Document size limits**                                        | Max 16 MB per document for indexing                       | Pre-split large PDFs before indexing                     |
| **Skillset execution costs**                                    | AI enrichment adds cost per document                      | Batch processing; optimize chunk size                    |
| **No real-time index sync with OneLake**                        | Index must be explicitly updated when documents change    | Event-driven indexing pipeline                           |

### 10.4 Azure OpenAI Limitations

| Limitation                                                      | Impact                                                    | Mitigation                                              |
|-----------------------------------------------------------------|-----------------------------------------------------------|---------------------------------------------------------|
| **Regional availability (Canada)**                              | Not all models available in Canada East/Central           | Verify model availability; fall back to US East if needed|
| **Rate limits / TPM quotas**                                    | May throttle during heavy concurrent usage                | Request quota increase; implement retry with backoff     |
| **Context window limits**                                       | Large document contexts may exceed token limits           | Optimize chunk retrieval (top-K selection, summarization)|
| **Hallucination risk**                                          | LLM may generate answers not grounded in context          | Strict grounding prompts; citation enforcement           |

---

## 11. Potential First-Adopter Blockers

These are issues that could significantly impact or block the POC if not addressed
early:

| # | Blocker                                                       | Severity | Owner         | Resolution Path                                            |
|---|---------------------------------------------------------------|----------|---------------|------------------------------------------------------------|
| 1 | **Fabric Data Agent preview not enabled on Manulife tenant**  | Critical | Fabric Admin  | Submit preview enrollment request; allow 2-3 weeks lead time |
| 2 | **Azure OpenAI not available in Canadian region**              | High     | Azure Admin   | Verify region availability; request access if gated         |
| 3 | **Fabric capacity not provisioned or undersized**             | Critical | Manulife IT   | Provision F64+ capacity in Canada Central                    |
| 4 | **Copilot tenant setting disabled / policy-blocked**          | High     | Fabric Admin  | Engage Manulife IT security for tenant setting approval      |
| 5 | **No synthetic data available for POC**                       | Medium   | POC Team      | Generate synthetic data using Faker/Python scripts           |
| 6 | **Manulife security policy blocks Azure OpenAI usage**        | Critical | Infosec       | Engage compliance early; document data residency controls    |
| 7 | **DirectLake mode not supported for the semantic model**      | Medium   | POC Team      | Fall back to Import mode; document performance trade-off     |
| 8 | **Data Agent API not available for custom app integration**   | High     | Microsoft     | Use Fabric UI-based Data Agent; escalate via Microsoft TAM   |
| 9 | **KPI definitions not finalized**                             | Medium   | Manulife SMEs | Start with industry-standard insurance KPIs; iterate        |
| 10| **Network restrictions preventing Azure service communication**| High    | Manulife IT   | Document required endpoints; request firewall exceptions      |

---

## 12. Pilot Scope Recommendation

### 12.1 Recommended Pilot Domain

**Group Benefits Claims Analytics** is the recommended pilot domain because:

- Claims data is transactional, well-structured, and high-volume
- KPIs are well-defined (loss ratio, processing time, claims frequency)
- Business impact is immediate (faster claims insights, fraud detection signals)
- Policy documents provide natural unstructured content for RAG demo
- Multiple personas benefit (claims analysts, product owners, actuaries, executives)

### 12.2 In-Scope for Pilot

| Category                     | Scope                                                                                         |
|------------------------------|-----------------------------------------------------------------------------------------------|
| **Data Entities**            | Customers, Policies (Group Benefits only), Claims, Products (Group Benefits), Advisors        |
| **KPIs (Structured)**        | Loss Ratio, Avg Claims Processing Days, Open Claims Count, Claims Frequency, Policy Count, Lapse Rate |
| **Documents (Unstructured)** | Claims guidelines (10 PDFs), Product notes (20 PDFs), FAQ documents (5 PDFs)                  |
| **Test Questions**           | 25 structured KPI questions + 10 document questions + 5 hybrid questions                      |
| **Users**                    | 5-10 pilot users across claims, product, actuarial, and executive personas                    |
| **Security**                 | RLS by region (Ontario, Quebec, Western Canada, Atlantic) for claims data                     |
| **Copilot Interface**        | Custom web app (basic) or Copilot Studio agent                                                |

### 12.3 Out-of-Scope for Pilot

| Category                     | Reason                                                                              |
|------------------------------|-------------------------------------------------------------------------------------|
| Investment portfolio data    | Separate data domain; adds complexity without validating core hypothesis             |
| Real-time streaming data     | POC focuses on batch/daily refresh; streaming is a future enhancement                |
| Production data integration  | POC uses synthetic data; production connectivity is a separate workstream            |
| Multi-language support       | English only for POC; French Canadian support is a future consideration              |
| Mobile interface             | Web-only for POC; mobile is a future enhancement                                     |
| Cross-tenant federation      | Single-tenant POC; multi-tenant/multi-geography is future state                      |
| Advanced fraud detection ML  | ML models are a future enhancement; POC focuses on analytics and NLQ                 |

### 12.4 Success Criteria

| Criterion                                        | Target                  | Measurement Method                                        |
|--------------------------------------------------|-------------------------|-----------------------------------------------------------|
| Data Agent accuracy on structured questions       | >= 90%                  | Validated against 25 test questions with known answers     |
| RAG accuracy on document questions                | >= 80%                  | Validated against 10 test questions with known answers     |
| End-to-end response time (KPI question)           | < 10 seconds            | Timed from question submission to answer display           |
| End-to-end response time (document question)      | < 15 seconds            | Timed from question submission to answer display           |
| RLS enforcement                                   | 100%                    | Verified: user A cannot see user B's region data           |
| User satisfaction (pilot feedback)                | >= 4/5 rating           | Post-pilot survey from 5-10 pilot users                   |
| Data freshness                                    | < 24 hours              | Gold zone reflects previous day's source data              |

### 12.5 Timeline (6-Week Pilot)

| Week  | Activities                                                                                       |
|-------|--------------------------------------------------------------------------------------------------|
| 1     | Environment setup: Fabric capacity, workspace, Azure resources. Synthetic data generation.       |
| 2     | Data engineering: Pipelines, notebooks (Bronze-Silver-Gold). Lakehouse setup.                    |
| 3     | Semantic model: Star schema, DAX measures, RLS. DirectLake configuration.                        |
| 4     | AI layer: Azure AI Search index, Azure OpenAI integration, Data Agent configuration.             |
| 5     | Copilot experience: Custom app or Copilot Studio. Routing logic. End-to-end integration.         |
| 6     | Testing, validation, demo preparation, stakeholder presentation.                                 |

---

## 13. Customer Follow-Up Questions

The following questions should be discussed with Manulife stakeholders to refine
the architecture:

### 13.1 Data and Business Questions

| # | Question                                                                                              | Why It Matters                                                       |
|---|-------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------|
| 1 | Which business unit should be the pilot? (Group Benefits, Individual Insurance, Wealth Management?)   | Determines data scope and KPI definitions                            |
| 2 | What are the priority KPIs? Can you provide formal KPI definitions with business rules?                | Ensures DAX measures match Manulife's official definitions           |
| 3 | Can you provide sample data schemas or data dictionaries for the pilot entities?                       | Accelerates data modeling and synthetic data generation              |
| 4 | What is the expected data volume in production? (rows per entity, daily delta volume)                  | Informs capacity sizing and pipeline design                          |
| 5 | Are there existing Power BI reports or semantic models we should align with?                           | Avoids creating conflicting KPI definitions                          |
| 6 | What unstructured documents are available for the pilot? Can you provide samples?                      | Determines RAG scope and chunking strategy                           |
| 7 | Are there regulatory requirements for data retention or auditability?                                  | Influences governance design and audit logging                       |

### 13.2 Platform and Technical Questions

| # | Question                                                                                              | Why It Matters                                                       |
|---|-------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------|
| 1 | Is Fabric capacity already provisioned? What SKU? Which region?                                       | Critical path prerequisite                                           |
| 2 | Is Copilot / Data Agent preview enabled on the Manulife Fabric tenant?                                | Critical path prerequisite; may require 2-3 weeks to enable          |
| 3 | Is Azure OpenAI approved for use within Manulife? Any restrictions?                                   | Manulife security policy may restrict LLM usage                      |
| 4 | What Azure region(s) are approved for Manulife workloads?                                             | Data residency requirement for Canadian data                         |
| 5 | Are there existing Azure AI Search or Azure OpenAI deployments we can leverage?                        | Avoid provisioning duplicates; leverage existing infrastructure       |
| 6 | What is the preferred authentication mechanism? (Entra ID, B2C, federated?)                           | Determines SSO and RLS implementation                                |
| 7 | Are there network restrictions (VNet, firewall, private endpoints) we need to plan for?               | May add 1-2 weeks for networking setup                               |
| 8 | Is Git integration available for Fabric workspace?                                                     | Enables CI/CD and version control for Fabric artifacts               |

### 13.3 User Experience Questions

| # | Question                                                                                              | Why It Matters                                                       |
|---|-------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------|
| 1 | What is the preferred Copilot interface? (Custom web app, Power BI embedded, Teams bot, Copilot Studio?)| Determines frontend development effort                             |
| 2 | Who are the pilot users? Can we get 5-10 named users for testing?                                     | Required for RLS configuration and user feedback                     |
| 3 | What devices do users primarily use? (Desktop, tablet, mobile?)                                       | Influences responsive design requirements                            |
| 4 | Are there branding or UI guidelines we should follow?                                                  | Custom app may need to match Manulife design language                |
| 5 | What languages do users need? (English only, or English + French?)                                    | Multi-language support adds complexity to Data Agent and RAG         |

---

## 14. Future-State Enhancements

### 14.1 Short-Term (Post-Pilot, 3-6 Months)

| Enhancement                                        | Description                                                              |
|----------------------------------------------------|--------------------------------------------------------------------------|
| **Expand to additional business units**            | Add Individual Insurance, Wealth Management, Banking data domains        |
| **Production data integration**                    | Connect to Manulife source systems (via Fabric Pipelines or Dataflow Gen2)|
| **Advanced RLS**                                   | Object-level security, column-level security, dynamic data masking       |
| **Copilot in Power BI reports**                    | Enable Copilot in existing Power BI reports for ad-hoc Q&A              |
| **Data Agent GA migration**                        | Migrate from preview to GA when available; adopt new GA features         |
| **Automated data quality monitoring**              | Microsoft Purview Data Quality or Great Expectations integration         |
| **Multi-language support**                         | English + French Canadian for questions and responses                    |

### 14.2 Medium-Term (6-12 Months)

| Enhancement                                        | Description                                                              |
|----------------------------------------------------|--------------------------------------------------------------------------|
| **Real-time data streaming**                       | Fabric Eventstream for real-time claims and transaction data             |
| **ML model integration**                           | Fraud detection, claims triage, churn prediction models in Fabric ML    |
| **Multi-agent architecture**                       | Specialized agents per domain (claims agent, investment agent) with router|
| **Document Intelligence pipeline**                 | Azure AI Document Intelligence for structured extraction from complex PDFs|
| **Cross-workspace federation**                     | Federate semantic models across workspaces for enterprise-wide analytics |
| **Automated testing framework**                    | CI/CD pipeline with automated Data Agent accuracy testing                |
| **User feedback loop**                             | Thumbs up/down on answers feeds back to improve Data Agent instructions  |

### 14.3 Long-Term (12+ Months)

| Enhancement                                        | Description                                                              |
|----------------------------------------------------|--------------------------------------------------------------------------|
| **Enterprise knowledge graph**                     | Build a Manulife knowledge graph linking entities across all domains     |
| **Autonomous agents**                              | Agents that take actions (initiate claims, send notifications) not just answer questions |
| **Advanced analytics copilot**                     | Copilot that can run Python/R analytics on demand (what-if, forecasting)|
| **External data enrichment**                       | Market data, regulatory feeds, economic indicators integrated into OneLake|
| **Multi-geography deployment**                     | Deploy to Asia and US regions for Manulife's global operations           |
| **Custom fine-tuned models**                       | Fine-tune LLM on Manulife-specific terminology and patterns             |
| **Embedded in operational workflows**              | Copilot embedded in claims processing, underwriting, and advisory tools  |

---

## Appendix A: Glossary

| Term                    | Definition                                                                                       |
|-------------------------|--------------------------------------------------------------------------------------------------|
| **AUM**                 | Assets Under Management -- total market value of investments managed on behalf of clients         |
| **Bronze Zone**         | First layer of the medallion architecture; raw data as received from source systems               |
| **Copilot**             | Microsoft's branded AI assistant experience; in this context, the conversational interface        |
| **DAX**                 | Data Analysis Expressions -- the formula language used in Power BI semantic models                |
| **Data Agent**          | Fabric Data Agent -- an AI agent that translates natural language to DAX queries                  |
| **Delta Lake**          | Open-source storage layer that brings ACID transactions to Apache Spark and big data workloads    |
| **DirectLake**          | A Power BI storage mode that reads directly from Delta tables in OneLake without data duplication |
| **Gold Zone**           | Third layer of the medallion architecture; curated star-schema data optimized for analytics       |
| **KPI**                 | Key Performance Indicator -- a measurable value that demonstrates business performance            |
| **Medallion**           | Architecture pattern with Bronze (raw), Silver (cleansed), Gold (curated) data zones              |
| **OneLake**             | Microsoft Fabric's unified data lake -- a single logical data lake for the entire organization    |
| **RAG**                 | Retrieval-Augmented Generation -- pattern that grounds LLM responses in retrieved documents       |
| **RLS**                 | Row-Level Security -- restricts data access at the row level based on user identity               |
| **Semantic Model**      | Power BI dataset containing relationships, measures, hierarchies, and security definitions        |
| **Silver Zone**         | Second layer of the medallion architecture; cleansed and conformed data                           |
| **Star Schema**         | Dimensional modeling pattern with fact tables surrounded by dimension tables                       |

---

## Appendix B: Reference Links

| Resource                                     | URL                                                                                    |
|----------------------------------------------|----------------------------------------------------------------------------------------|
| Microsoft Fabric Documentation               | https://learn.microsoft.com/en-us/fabric/                                              |
| Fabric Data Agent (Preview)                  | https://learn.microsoft.com/en-us/fabric/data-science/data-agent-overview              |
| Power BI Semantic Model                      | https://learn.microsoft.com/en-us/power-bi/connect-data/service-datasets-understand    |
| DirectLake Mode                              | https://learn.microsoft.com/en-us/fabric/get-started/direct-lake-overview              |
| Azure AI Search                              | https://learn.microsoft.com/en-us/azure/search/                                        |
| Azure OpenAI Service                         | https://learn.microsoft.com/en-us/azure/ai-services/openai/                            |
| RAG Pattern with Azure AI Search             | https://learn.microsoft.com/en-us/azure/search/retrieval-augmented-generation-overview  |
| Row-Level Security in Power BI               | https://learn.microsoft.com/en-us/power-bi/enterprise/service-admin-rls                |
| Fabric Notebooks                             | https://learn.microsoft.com/en-us/fabric/data-engineering/how-to-use-notebook          |
| Fabric Pipelines                             | https://learn.microsoft.com/en-us/fabric/data-factory/pipeline-overview                |

---

## Appendix C: Decision Log

| # | Decision                                            | Rationale                                                              | Date       | Status   |
|---|-----------------------------------------------------|------------------------------------------------------------------------|------------|----------|
| 1 | Use DirectLake mode for semantic model              | Best performance, no data duplication, required for Data Agent          | 2026-04-24 | Decided  |
| 2 | Use Azure AI Search (not Fabric-native) for RAG     | Data Agent has no native document indexing; AI Search is proven pattern | 2026-04-24 | Decided  |
| 3 | Use custom web app for Copilot experience           | Maximum control over routing, UX, and multi-source answer combination  | 2026-04-24 | Proposed |
| 4 | Group Benefits Claims as pilot domain               | High business impact, well-defined KPIs, good persona coverage         | 2026-04-24 | Proposed |
| 5 | Synthetic data for POC                              | Avoid production data access complexity during POC phase               | 2026-04-24 | Decided  |
| 6 | Single Fabric workspace for POC                     | Avoid cross-workspace limitations in preview                           | 2026-04-24 | Decided  |
| 7 | Canada Central/East for all resources               | Manulife data residency requirements                                   | 2026-04-24 | Decided  |

---

*End of Reference Architecture Document*
