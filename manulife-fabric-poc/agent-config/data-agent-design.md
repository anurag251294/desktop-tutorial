# Fabric Data Agent Design Document

**Project**: Manulife Fabric POC
**Version**: 1.0
**Last Updated**: 2026-04-24
**Status**: Phase 4 Deliverable

---

## Table of Contents

1. [Overview](#1-overview)
2. [What the Data Agent Should Query](#2-what-the-data-agent-should-query)
3. [Data Agent Configuration](#3-data-agent-configuration)
4. [Sample Prompts and Expected Answers](#4-sample-prompts-and-expected-answers)
5. [Orchestration Pattern](#5-orchestration-pattern)
6. [Limitations and Fallback Behavior](#6-limitations-and-fallback-behavior)
7. [Future State](#7-future-state)

---

## 1. Overview

The Fabric Data Agent provides natural language access to Manulife's insurance and investment data hosted in Microsoft Fabric. It enables business users, actuaries, and executives to query structured KPIs via the semantic model, drill into row-level detail via the Lakehouse SQL endpoint, and retrieve context from unstructured documents via Azure AI Search.

This document defines what the agent should query, how it should be configured, the expected behavior for a comprehensive set of sample prompts, and the orchestration pattern for hybrid queries that span multiple data sources.

---

## 2. What the Data Agent Should Query

### 2.1 Semantic Model (Power BI Dataset)

The semantic model is the **primary source** for all business measures, KPIs, and aggregated analytics. The agent should route queries here when the user asks about metrics, trends, comparisons, or summary-level data.

**Measures and KPIs available:**

| Measure | Description | DAX Source |
|---------|-------------|------------|
| Total Premium Revenue | Sum of premium amounts across active policies | `SUM(gold_policies[premium_amount])` |
| Claims Ratio | Total claims paid / total premium revenue | `DIVIDE([Total Claims Paid], [Total Premium Revenue])` |
| Total Claims Paid | Sum of approved claim amounts | `SUM(gold_claims[claim_amount])` |
| Active Customer Count | Distinct count of customers with active policies | `DISTINCTCOUNT(gold_policies[customer_id])` |
| Assets Under Management (AUM) | Total market value of investment holdings | `SUM(gold_investments[market_value])` |
| Investment Return Rate | Weighted average return across investment portfolios | `SUMX(...)` |
| Average Policy Value | Mean premium amount per active policy | `AVERAGE(gold_policies[premium_amount])` |
| Policy Retention Rate | Policies renewed / policies eligible for renewal | `DIVIDE([Renewed Policies], [Eligible Policies])` |
| Claims Processing Time (Avg) | Average days from claim filed to resolution | `AVERAGE(gold_claims[processing_days])` |
| Customer Lifetime Value | Estimated total premium over customer relationship | Calculated measure |

**Query patterns routed to semantic model:**

- "Show me claims by policy type" -- aggregation by dimension
- "What's the premium trend over the last 6 months?" -- time series trend
- "Compare claims ratio across regions" -- comparative analysis
- "What is our total AUM?" -- single KPI retrieval
- "Top 10 products by premium revenue" -- ranked aggregation
- "Year-over-year growth in active customers" -- period comparison

### 2.2 Lakehouse SQL Endpoint (Direct Query)

The SQL endpoint provides access to **row-level detail** in the Gold layer Delta tables. The agent should route queries here when the user asks for specific records, filtered lists, or ad-hoc exploration that goes beyond pre-defined measures.

**Tables available via SQL endpoint:**

| Table | Key Columns | Use Cases |
|-------|-------------|-----------|
| `gold_customers` | customer_id, name, region, segment, acquisition_date | Customer lookup, segmentation |
| `gold_policies` | policy_id, customer_id, product_id, type, status, premium_amount, start_date, end_date | Policy detail, expiration tracking |
| `gold_claims` | claim_id, policy_id, customer_id, claim_type, claim_amount, status, filed_date, resolved_date | Claim detail, investigation |
| `gold_products` | product_id, product_name, category, risk_class | Product catalog |
| `gold_investments` | investment_id, customer_id, fund_name, market_value, return_rate | Investment detail |
| `gold_advisors` | advisor_id, name, region, license_type | Advisor lookup |
| `gold_transactions` | transaction_id, customer_id, type, amount, transaction_date | Transaction history |

**Query patterns routed to SQL endpoint:**

- "List all claims for customer John Smith" -- filtered row retrieval
- "Show me policies expiring this month" -- date-filtered detail
- "Which advisors have the most clients in Ontario?" -- ad-hoc join and aggregation
- "Pull the transaction history for policy POL-2025-0042" -- specific record lookup
- "Show all denied claims over $50,000" -- filtered and sorted detail

### 2.3 Unstructured/RAG (Azure AI Search)

Unstructured data provides **document context, guidelines, and policy terms** that enrich answers from structured data. The agent accesses this via an orchestration layer that calls Azure AI Search with vector and keyword hybrid search.

**Document corpus indexed:**

| Document Type | Examples | Use Cases |
|---------------|----------|-----------|
| Policy terms and conditions | ML-LI-2025-ON, ML-GI-2025-ON | "What does the policy say about..." |
| Claims processing guidelines | Internal claims adjudication manual | "What is the process for..." |
| Investment commentary | Quarterly fund performance reports | "Summarize Q1 investment performance" |
| Regulatory guidelines | OSFI, CLHIA compliance docs | "What are the regulatory requirements for..." |
| Product fact sheets | Product descriptions, eligibility | "What products are available for..." |

**Query patterns routed to Azure AI Search:**

- "What does the claims guideline say about suicide exclusion?" -- document retrieval
- "Summarize the investment commentary for Q1" -- document summarization
- "What are the terms for policy reinstatement?" -- specific clause lookup
- "What riders are available for life insurance?" -- product knowledge
- "What is the contestability period?" -- definition lookup

---

## 3. Data Agent Configuration

### 3.1 System Prompt / Instructions

The following system prompt should be configured in the Fabric Data Agent settings:

```
You are a data assistant for Manulife's insurance and investment analytics platform.
You help business users, actuaries, product managers, and executives understand
Manulife's insurance, claims, investment, and customer data.

GUIDELINES:
1. Always prefer the semantic model for aggregated metrics, KPIs, and trend analysis.
   Use DAX measures when available rather than writing raw SQL for aggregations.
2. Use the Lakehouse SQL endpoint for row-level detail, filtered record lookups,
   and ad-hoc exploration that goes beyond pre-defined measures.
3. When a question involves both a metric AND document context (e.g., "What is our
   claims ratio and what does the guideline say about acceptable thresholds?"),
   clearly separate the structured answer from the document-sourced context.
4. Always specify the time period for trend queries. If the user does not specify,
   default to the most recent 12 months and state the assumption.
5. Present numerical results with appropriate formatting:
   - Currency: CAD with commas (e.g., $1,234,567.89)
   - Percentages: Two decimal places (e.g., 65.42%)
   - Counts: Commas for thousands (e.g., 12,345)
6. When presenting tables, include column headers and limit to the top 20 rows
   unless the user requests more.
7. If you cannot answer a question with the available data, say so clearly and
   suggest what data would be needed.
8. Do not fabricate data. If a measure or table does not exist, inform the user.
9. For questions about policy terms, exclusions, or regulatory requirements,
   indicate that the answer is sourced from document search and may require
   verification with the legal or compliance team.
10. All data is in Canadian dollars unless stated otherwise.

DOMAIN CONTEXT:
- Manulife is a leading Canadian financial services company offering life insurance,
  health insurance, wealth management, and asset management products.
- Key business lines: Individual Insurance, Group Benefits, Wealth & Asset Management.
- Primary regulatory bodies: OSFI (federal), provincial insurance regulators, CLHIA.
- Key metrics: claims ratio (loss ratio), premium revenue, AUM, policy retention rate,
  customer lifetime value, investment returns.
```

### 3.2 Grounding Data Sources

| Source | Type | Connection | Purpose |
|--------|------|------------|---------|
| Manulife Insurance Semantic Model | Power BI Dataset | Direct Lake / Import | KPIs, measures, aggregations |
| Manulife Lakehouse SQL Endpoint | SQL Analytics Endpoint | Fabric SQL | Row-level detail, ad-hoc queries |
| Azure AI Search Index | REST API (via orchestration) | API Key + Endpoint | Unstructured document retrieval |

### 3.3 Few-Shot Examples

The following examples should be included in the agent configuration to improve grounding accuracy:

**Example 1: Simple KPI**
```
User: What is our total premium revenue?
Agent: Based on the semantic model, Manulife's total premium revenue is $X,XXX,XXX.XX CAD
for the current reporting period (YYYY-MM to YYYY-MM). This includes premiums across all
active life insurance, health, and investment-linked policies.
```

**Example 2: Aggregation by Dimension**
```
User: Show me claims by policy type.
Agent: Here is the breakdown of claims by policy type:

| Policy Type | Total Claims | Claim Count | Avg Claim Amount |
|------------|-------------|-------------|-----------------|
| Term Life  | $X,XXX,XXX  | XXX         | $XX,XXX         |
| Whole Life | $X,XXX,XXX  | XXX         | $XX,XXX         |
| Universal  | $X,XXX,XXX  | XXX         | $XX,XXX         |

Source: Semantic model (Claims by Policy Type measure)
```

**Example 3: Row-Level Lookup**
```
User: List all claims for customer John Smith.
Agent: Here are the claims for John Smith (Customer ID: CUST-XXXX):

| Claim ID | Policy | Type | Amount | Status | Filed Date |
|----------|--------|------|--------|--------|------------|
| CLM-001  | POL-XX | Life | $XX,XXX | Approved | 2025-XX-XX |
| CLM-002  | POL-XX | Health | $X,XXX | Pending | 2025-XX-XX |

Source: Lakehouse SQL endpoint (gold_claims joined with gold_customers)
```

**Example 4: Document Context**
```
User: What does the policy say about the contestability period?
Agent: According to the Manulife Individual Life Insurance Policy Terms (ML-LI-2025-ON),
Section 8.2 - Incontestability:

"After this policy has been in force during the lifetime of the Insured Person for a
period of two years from the Policy Date, it shall be incontestable except for
non-payment of premiums or fraud."

This means Manulife may contest the validity of a policy within the first two years
based on material misrepresentation, but after that period, the policy becomes
incontestable.

Source: Azure AI Search (policy_terms_life_insurance.md)
Note: Please verify with the legal team for authoritative interpretation.
```

**Example 5: Hybrid Query**
```
User: What is our claims ratio and what does the guideline say about acceptable thresholds?
Agent: **Structured Data (Semantic Model):**
The current claims ratio is XX.X%, calculated as total claims paid divided by total
premium revenue for the trailing 12 months.

**Document Context (Claims Guidelines):**
According to the claims management guidelines, the target claims ratio for the
Individual Insurance line of business is between 55-65%. Ratios exceeding 70% trigger
a portfolio review process.

Source: Semantic model + Azure AI Search
```

### 3.4 Guardrails and Limitations

| Guardrail | Configuration |
|-----------|--------------|
| Data access scope | Agent can only query the designated semantic model and lakehouse; no cross-workspace access |
| PII handling | Agent must not display full SIN, date of birth, or banking details in responses; mask to last 4 digits |
| Row limit | SQL endpoint queries capped at 1,000 rows in response; prompt user to apply filters if result set is larger |
| No write operations | Agent is read-only; cannot modify data, create tables, or trigger pipelines |
| Timeout | Queries exceeding 30 seconds should return a partial result with a timeout notice |
| Compliance disclaimer | Answers sourced from documents must include a note to verify with legal/compliance |
| Currency assumption | All monetary values assumed CAD unless explicitly stated |
| No financial advice | Agent must not provide investment recommendations or actuarial opinions |

---

## 4. Sample Prompts and Expected Answers

### 4.1 Claims Analytics

| # | Prompt | Expected Data Source | Expected Answer Format | Notes |
|---|--------|---------------------|----------------------|-------|
| 1 | "What is the overall claims ratio?" | Semantic model | Single KPI: "The claims ratio is XX.X% for [period]." | Uses Claims Ratio measure |
| 2 | "Show me claims by policy type for the last year" | Semantic model | Table: Policy Type, Total Claims, Count, Avg Amount | Aggregation by dimension + time filter |
| 3 | "Which region has the highest claims volume?" | Semantic model | Ranked list: Region, Total Claims, Count | TopN with ranking |
| 4 | "List all denied claims over $50,000" | Lakehouse SQL | Table: Claim ID, Customer, Amount, Reason, Date | Row-level filter on gold_claims |
| 5 | "What is the average claims processing time by claim type?" | Semantic model | Table: Claim Type, Avg Days to Resolution | Uses processing time measure |
| 6 | "Show me the trend of claims filed per month over the last 12 months" | Semantic model | Time series table/description: Month, Claim Count, Total Amount | Trend analysis |
| 7 | "What does the policy say about filing a death benefit claim?" | Azure AI Search | Narrative from Section 7.1 of policy terms | Document retrieval, include compliance note |

### 4.2 Investment Analytics

| # | Prompt | Expected Data Source | Expected Answer Format | Notes |
|---|--------|---------------------|----------------------|-------|
| 8 | "What is our total AUM?" | Semantic model | Single KPI: "Total AUM is $X.XB CAD." | Uses AUM measure |
| 9 | "Show investment returns by fund name" | Semantic model | Table: Fund Name, Market Value, Return Rate | Aggregation by dimension |
| 10 | "Which customers have investments over $1M?" | Lakehouse SQL | Table: Customer Name, Total Investment Value | Row-level filter + aggregation |
| 11 | "Compare investment performance this quarter vs last quarter" | Semantic model | Comparison table: Fund, Q Current, Q Previous, Delta | Period-over-period comparison |
| 12 | "What are the top 5 performing funds?" | Semantic model | Ranked table: Fund Name, Return Rate, AUM | TopN ranking |
| 13 | "Show the investment portfolio breakdown for customer ID CUST-0042" | Lakehouse SQL | Table: Fund, Units, Market Value, Return | Specific customer lookup |

### 4.3 Customer Insights

| # | Prompt | Expected Data Source | Expected Answer Format | Notes |
|---|--------|---------------------|----------------------|-------|
| 14 | "How many active customers do we have?" | Semantic model | Single KPI: "There are XX,XXX active customers." | Uses Active Customer Count measure |
| 15 | "Show customer distribution by region" | Semantic model | Table: Region, Customer Count, Percentage | Dimension breakdown |
| 16 | "List all customers acquired in the last 90 days" | Lakehouse SQL | Table: Customer ID, Name, Region, Acquisition Date | Date-filtered row retrieval |
| 17 | "What is the average customer lifetime value by segment?" | Semantic model | Table: Segment, Avg CLV, Customer Count | Aggregation by segment |
| 18 | "Show me the full profile for customer Jane Doe" | Lakehouse SQL | Detail: Name, Policies, Claims, Investments summary | Multi-table join for single customer |

### 4.4 Product and Policy Queries

| # | Prompt | Expected Data Source | Expected Answer Format | Notes |
|---|--------|---------------------|----------------------|-------|
| 19 | "What are our top products by premium revenue?" | Semantic model | Ranked table: Product, Premium Revenue, Policy Count | TopN ranking |
| 20 | "Show all policies expiring in the next 30 days" | Lakehouse SQL | Table: Policy ID, Customer, Product, End Date, Premium | Date-filtered detail |
| 21 | "What is the policy retention rate by product category?" | Semantic model | Table: Category, Retention Rate, Eligible Count | Uses retention measure |
| 22 | "How many Term Life vs Whole Life policies do we have?" | Semantic model | Comparison: Type, Count, Total Premium, Avg Premium | Type comparison |
| 23 | "What riders are available for life insurance policies?" | Azure AI Search | Narrative listing from Section 9 of policy terms | Document retrieval |

### 4.5 Unstructured Enrichment

| # | Prompt | Expected Data Source | Expected Answer Format | Notes |
|---|--------|---------------------|----------------------|-------|
| 24 | "What does the policy say about the suicide exclusion?" | Azure AI Search | Narrative from Section 3.1 of policy terms | Direct document retrieval |
| 25 | "What is our claims ratio and what does the guideline say about acceptable ranges?" | Semantic model + Azure AI Search | Hybrid: KPI + document context | Hybrid query pattern |
| 26 | "Summarize the terms for policy reinstatement" | Azure AI Search | Narrative from Section 5.4 of policy terms | Document summarization |
| 27 | "What are the settlement options for a death benefit?" | Azure AI Search | Structured list from Section 7.5 of policy terms | Document retrieval |
| 28 | "What privacy legislation governs our customer data?" | Azure AI Search | Narrative from Section 8.7 of policy terms | Regulatory context |

---

## 5. Orchestration Pattern

### 5.1 Architecture Overview

```
User Question
     |
     v
[Intent Classifier]
     |
     +---> Structured (KPI/aggregation) ---> Semantic Model ---> Format Response
     |
     +---> Detail (row-level) ------------> SQL Endpoint ----> Format Response
     |
     +---> Unstructured (document) -------> Azure AI Search -> Format Response
     |
     +---> Hybrid (structured + context) --> Both Sources ----> Merge & Format
```

### 5.2 Step-by-Step Flow

**Step 1: Receive User Question**
The Data Agent receives the natural language question from the user.

**Step 2: Classify Intent**
The agent classifies the question into one of four categories:

| Category | Signal Words/Patterns | Target Source |
|----------|----------------------|---------------|
| Structured KPI | "total", "average", "ratio", "trend", "by [dimension]", "top N", "compare" | Semantic Model |
| Row-Level Detail | "list", "show all", "for customer X", "specific", "expiring", "details of" | SQL Endpoint |
| Unstructured | "what does the policy say", "guideline", "terms", "summarize the document" | Azure AI Search |
| Hybrid | Contains both metric request AND document reference | Both sources |

**Step 3: Route to Appropriate Source**

- **Structured**: Generate DAX query or leverage existing semantic model measures. The Data Agent natively handles this via the Power BI dataset connection.
- **Detail**: Generate T-SQL query against the Lakehouse SQL endpoint. The Data Agent natively handles this via the SQL endpoint connection.
- **Unstructured**: Call Azure AI Search via the orchestration API. This requires an external call pattern (see Section 5.3).
- **Hybrid**: Execute both the structured query and the document search, then merge results.

**Step 4: Execute Query**

For semantic model queries:
- The Data Agent generates DAX and executes against the connected dataset
- Results are returned as tabular data

For SQL endpoint queries:
- The Data Agent generates T-SQL and executes against the lakehouse
- Results are returned as tabular data with row limits applied

For Azure AI Search:
- The orchestration layer sends a hybrid search request (vector + keyword)
- Top-K relevant document chunks are returned
- The agent synthesizes a response from the retrieved chunks

**Step 5: Format and Present Response**

- Tabular data is formatted as markdown tables
- KPIs are presented as highlighted single values with context
- Document-sourced content includes source attribution and compliance disclaimers
- Hybrid responses clearly delineate structured vs. document-sourced sections

### 5.3 Azure AI Search Integration (Orchestration Layer)

Since Fabric Data Agent does not natively support Azure AI Search as a grounding source (as of April 2026), unstructured queries require an orchestration layer:

**Option A: Azure Function Middleware**
1. Data Agent detects unstructured intent
2. Calls an Azure Function via HTTP action
3. Azure Function queries Azure AI Search (hybrid search)
4. Returns top-K chunks to the Data Agent
5. Data Agent synthesizes response

**Option B: Prompt Flow Orchestrator**
1. User question is routed to a Prompt Flow endpoint
2. Prompt Flow classifies intent and routes accordingly
3. For unstructured: calls Azure AI Search directly
4. For structured: calls Fabric Data Agent API
5. For hybrid: calls both and merges results

**Recommended Approach**: Option B (Prompt Flow) for the POC, as it provides the most flexibility for hybrid queries and can be demonstrated as part of the Azure AI portfolio.

---

## 6. Limitations and Fallback Behavior

### 6.1 Current Limitations

| Limitation | Impact | Workaround |
|-----------|--------|------------|
| Data Agent cannot natively query Azure AI Search | Unstructured queries require external orchestration | Use Prompt Flow or Azure Function middleware |
| Data Agent supports single grounding source per query | Cannot natively combine semantic model + documents | Orchestration layer handles hybrid routing |
| Preview feature: Data Agent may have intermittent availability | Demo reliability risk | Pre-cache expected results as backup |
| DAX generation accuracy varies with question complexity | Complex multi-measure queries may produce incorrect DAX | Include few-shot examples for complex patterns |
| No write-back capability | Cannot trigger actions (e.g., flag a claim for review) | Inform user; suggest manual process |
| No real-time data | Data freshness depends on pipeline schedule | State data-as-of timestamp in responses |
| Limited to English | French language queries not supported in preview | Future: add French language support |
| Row limit on SQL queries | Large result sets truncated | Prompt user to add filters |

### 6.2 Fallback Strategies

| Scenario | Fallback Behavior |
|----------|------------------|
| Agent cannot understand the question | "I'm not sure how to answer that. Could you rephrase your question? Here are some examples of what I can help with: [list 3-4 sample queries]" |
| Query returns no results | "No data was found matching your criteria. This could mean: (a) the filter is too restrictive, (b) the data hasn't been loaded yet, or (c) the metric isn't available. Try broadening your search." |
| Query times out | "The query is taking longer than expected. Try narrowing your request with specific filters (e.g., a date range or region)." |
| Document search returns no relevant chunks | "I couldn't find relevant information in the available documents. This question may require consultation with the [legal/compliance/product] team." |
| Agent returns incorrect DAX | Pre-validated DAX snippets are included as few-shot examples; for known complex queries, hardcoded DAX templates are used. |
| Service outage | Display pre-prepared screenshots of expected results with a note that the live service is temporarily unavailable. |

### 6.3 User Guidance for Best Results

To get the best results from the Data Agent, users should:

1. **Be specific about time periods**: "claims for Q1 2025" rather than "recent claims"
2. **Name the metric explicitly**: "claims ratio" rather than "how are claims doing"
3. **Specify dimensions when filtering**: "by region and policy type" rather than "broken down"
4. **Use known entity names**: "customer John Smith" rather than "a specific customer"
5. **Ask one question at a time**: Split complex multi-part questions into individual queries
6. **Verify document-sourced answers**: Always confirm policy/regulatory answers with the authoritative team

---

## 7. Future State

### 7.1 When Fabric Data Agent Adds Native RAG

Microsoft has signaled that Fabric Data Agent will add native RAG (Retrieval-Augmented Generation) capabilities, which would allow:

- **Direct Azure AI Search grounding**: Configure an Azure AI Search index as a native data source alongside the semantic model and SQL endpoint
- **Automatic intent routing**: The agent natively classifies and routes to the appropriate source without external orchestration
- **Unified response generation**: The agent combines structured and unstructured answers in a single response without middleware
- **Impact on this POC**: The orchestration layer (Prompt Flow / Azure Function) would be replaced by native configuration, significantly simplifying the architecture

### 7.2 When Multi-Source Grounding is GA

When multi-source grounding reaches General Availability:

- **Single agent, multiple grounding sources**: One Data Agent configuration can ground on semantic model + SQL endpoint + document index simultaneously
- **Improved accuracy**: GA-quality intent classification and query generation
- **Enterprise security**: Full integration with Fabric workspace security, row-level security, and sensitivity labels
- **Audit logging**: Native query logging and usage analytics
- **Impact on this POC**: The POC architecture becomes the production architecture with minimal changes

### 7.3 Expected Roadmap Items

| Feature | Expected Timeline | Impact |
|---------|------------------|--------|
| Native RAG in Data Agent | H2 2026 (estimated) | Eliminates need for external orchestration |
| Multi-source grounding GA | H2 2026 (estimated) | Production-ready hybrid queries |
| French language support | 2026-2027 | Required for Canadian market |
| Write-back actions | 2027+ | Enable agent to trigger workflows |
| Custom skills / plugins | H2 2026 (estimated) | Extend agent with custom logic |
| Data Agent API | H1 2026 (preview) | Programmatic access to agent capabilities |
| Row-level security pass-through | GA timeline TBD | Per-user data access enforcement |

### 7.4 Recommendations for Production Readiness

1. **Build the orchestration layer now** with the expectation that it will be replaced by native capabilities. Design for easy swap-out.
2. **Invest in the semantic model** as the durable asset. Regardless of how the agent evolves, well-defined measures and relationships will remain the foundation.
3. **Curate the document index** for high-quality RAG. Chunking strategy, metadata enrichment, and relevance tuning are portable across implementations.
4. **Capture user feedback** during the POC to identify the most valuable query patterns for production prioritization.
5. **Plan for bilingual support** as a Phase 2 requirement for Canadian regulatory compliance.

---

*This document is confidential and intended for internal use by Microsoft and Manulife project stakeholders.*
