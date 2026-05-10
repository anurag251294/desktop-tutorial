# Manulife Fabric POC - Validation Checklist

**Version**: 1.0
**Last Updated**: 2026-04-24
**Status**: Phase 4 Deliverable

---

## Instructions

For each check, fill in the **Actual Result** column and mark **Pass/Fail**. All checks should pass before the POC is considered validated. Any failures should be documented in the notes column with a remediation plan.

---

## 1. Data Layer Checks

### 1.1 Bronze Layer - Ingestion Completeness

| # | Check | Expected Result | Actual Result | Pass/Fail | Notes |
|---|-------|----------------|---------------|-----------|-------|
| 1.1.1 | bronze_customers row count | Matches source CSV row count | | | |
| 1.1.2 | bronze_policies row count | Matches source CSV row count | | | |
| 1.1.3 | bronze_claims row count | Matches source CSV row count | | | |
| 1.1.4 | bronze_products row count | Matches source CSV row count | | | |
| 1.1.5 | bronze_investments row count | Matches source CSV row count | | | |
| 1.1.6 | bronze_advisors row count | Matches source CSV row count | | | |
| 1.1.7 | bronze_transactions row count | Matches source CSV row count | | | |
| 1.1.8 | _ingestion_timestamp populated | Non-null for all rows in all tables | | | |
| 1.1.9 | _source_file populated | Non-null for all rows in all tables | | | |
| 1.1.10 | _batch_id populated | Non-null and consistent per run | | | |

### 1.2 Silver Layer - Data Quality

| # | Check | Expected Result | Actual Result | Pass/Fail | Notes |
|---|-------|----------------|---------------|-----------|-------|
| 1.2.1 | Null check: customer_id | 0 nulls in silver_customers | | | |
| 1.2.2 | Null check: policy_id | 0 nulls in silver_policies | | | |
| 1.2.3 | Null check: claim_id | 0 nulls in silver_claims | | | |
| 1.2.4 | Type validation: premium_amount | All values numeric and > 0 | | | |
| 1.2.5 | Type validation: claim_amount | All values numeric and >= 0 | | | |
| 1.2.6 | Date validation: policy start_date | All values valid dates, not in future beyond policy terms | | | |
| 1.2.7 | Date validation: claim filed_date | All values valid dates, not in future | | | |
| 1.2.8 | Referential integrity: policies.customer_id | All values exist in silver_customers | | | |
| 1.2.9 | Referential integrity: claims.policy_id | All values exist in silver_policies | | | |
| 1.2.10 | Referential integrity: claims.customer_id | All values exist in silver_customers | | | |
| 1.2.11 | Referential integrity: investments.customer_id | All values exist in silver_customers | | | |
| 1.2.12 | Referential integrity: transactions.customer_id | All values exist in silver_customers | | | |
| 1.2.13 | Enum validation: policy status | Values in {Active, Expired, Cancelled, Lapsed} | | | |
| 1.2.14 | Enum validation: claim status | Values in {Filed, Approved, Denied, Pending, In Review} | | | |
| 1.2.15 | Deduplication: customer_id | No duplicate customer_id in silver_customers | | | |
| 1.2.16 | Range check: premium_amount | Between $100 and $500,000 | | | |
| 1.2.17 | Range check: claim_amount | Between $0 and $5,000,000 | | | |

### 1.3 Gold Layer - Business Readiness

| # | Check | Expected Result | Actual Result | Pass/Fail | Notes |
|---|-------|----------------|---------------|-----------|-------|
| 1.3.1 | gold_customers row count | Equals silver_customers count (after dedup) | | | |
| 1.3.2 | gold_policies row count | Equals silver_policies count | | | |
| 1.3.3 | gold_claims row count | Equals silver_claims count | | | |
| 1.3.4 | gold_products row count | Equals silver_products count | | | |
| 1.3.5 | gold_investments row count | Equals silver_investments count | | | |
| 1.3.6 | gold_advisors row count | Equals silver_advisors count | | | |
| 1.3.7 | gold_transactions row count | Equals silver_transactions count | | | |
| 1.3.8 | All Gold tables in Delta format | `DESCRIBE DETAIL` shows delta format | | | |
| 1.3.9 | Gold tables have appropriate column names | snake_case, no special characters | | | |
| 1.3.10 | Gold layer query performance | SELECT COUNT(*) completes in < 5 seconds per table | | | |

---

## 2. Semantic Model Checks

### 2.1 Measure Accuracy

| # | Check | Expected Result | Actual Result | Pass/Fail | Notes |
|---|-------|----------------|---------------|-----------|-------|
| 2.1.1 | Total Premium Revenue | Sum of gold_policies.premium_amount (manual calc matches DAX) | | | |
| 2.1.2 | Total Claims Paid | Sum of gold_claims.claim_amount WHERE status = 'Approved' (manual calc matches DAX) | | | |
| 2.1.3 | Claims Ratio | Total Claims Paid / Total Premium Revenue (manual calc matches DAX) | | | |
| 2.1.4 | Active Customer Count | DISTINCT customer_id FROM gold_policies WHERE status = 'Active' (manual calc matches DAX) | | | |
| 2.1.5 | Total AUM | Sum of gold_investments.market_value (manual calc matches DAX) | | | |
| 2.1.6 | Average Policy Value | AVG of gold_policies.premium_amount (manual calc matches DAX) | | | |
| 2.1.7 | Average Claims Processing Time | AVG days between filed_date and resolved_date (manual calc matches DAX) | | | |
| 2.1.8 | Policy Retention Rate | Renewed / Eligible (manual calc matches DAX) | | | |
| 2.1.9 | Investment Return Rate | Weighted average return (manual calc matches DAX) | | | |
| 2.1.10 | Customer Lifetime Value | Calculated measure matches expected formula | | | |

### 2.2 Relationships

| # | Check | Expected Result | Actual Result | Pass/Fail | Notes |
|---|-------|----------------|---------------|-----------|-------|
| 2.2.1 | customers to policies | One-to-many on customer_id, active | | | |
| 2.2.2 | policies to claims | One-to-many on policy_id, active | | | |
| 2.2.3 | customers to claims | One-to-many on customer_id, active | | | |
| 2.2.4 | products to policies | One-to-many on product_id, active | | | |
| 2.2.5 | customers to investments | One-to-many on customer_id, active | | | |
| 2.2.6 | advisors to customers | One-to-many on advisor_id, active (if applicable) | | | |
| 2.2.7 | customers to transactions | One-to-many on customer_id, active | | | |
| 2.2.8 | Cross-filter direction | Single direction (dimension to fact) for all relationships | | | |
| 2.2.9 | No ambiguous relationships | Model loads without relationship ambiguity warnings | | | |

### 2.3 Model Configuration

| # | Check | Expected Result | Actual Result | Pass/Fail | Notes |
|---|-------|----------------|---------------|-----------|-------|
| 2.3.1 | Storage mode | Direct Lake | | | |
| 2.3.2 | Default date table | Auto date/time enabled or explicit date dimension | | | |
| 2.3.3 | Format strings | Currency formatted as $#,##0.00; Percentage as 0.00% | | | |
| 2.3.4 | Column visibility | ID columns hidden from report view | | | |
| 2.3.5 | Table descriptions | All tables have descriptions populated | | | |
| 2.3.6 | Measure descriptions | All measures have descriptions populated | | | |

---

## 3. Data Agent Checks

### 3.1 Query Accuracy

| # | Check | Expected Result | Actual Result | Pass/Fail | Notes |
|---|-------|----------------|---------------|-----------|-------|
| 3.1.1 | "How many active customers?" | Returns value matching Active Customer Count measure | | | |
| 3.1.2 | "Total premium revenue" | Returns value matching Total Premium Revenue measure | | | |
| 3.1.3 | "Claims ratio" | Returns value matching Claims Ratio measure (within 0.1%) | | | |
| 3.1.4 | "Claims by policy type" | Returns correct breakdown matching manual aggregation | | | |
| 3.1.5 | "Premium revenue by region" | Returns correct breakdown matching manual aggregation | | | |
| 3.1.6 | "Top 5 products by premium" | Returns correct ranked list | | | |
| 3.1.7 | "Policies expiring this month" | Returns correct filtered list from SQL endpoint | | | |
| 3.1.8 | "Claims for customer [name]" | Returns correct filtered claims for specified customer | | | |
| 3.1.9 | "AUM total" | Returns value matching AUM measure | | | |
| 3.1.10 | "Investment returns by fund" | Returns correct breakdown | | | |

### 3.2 Response Quality

| # | Check | Expected Result | Actual Result | Pass/Fail | Notes |
|---|-------|----------------|---------------|-----------|-------|
| 3.2.1 | Currency formatting | Values displayed as CAD with commas | | | |
| 3.2.2 | Percentage formatting | Values displayed with 2 decimal places | | | |
| 3.2.3 | Table formatting | Results displayed as formatted tables with headers | | | |
| 3.2.4 | Source attribution | Agent indicates which source was used (model vs SQL) | | | |
| 3.2.5 | Error handling | Unknown query returns helpful guidance, not an error | | | |
| 3.2.6 | No hallucination | Agent does not fabricate data not in the grounding sources | | | |

---

## 4. Unstructured Flow Checks

### 4.1 Document Indexing

| # | Check | Expected Result | Actual Result | Pass/Fail | Notes |
|---|-------|----------------|---------------|-----------|-------|
| 4.1.1 | Policy terms indexed | policy_terms_life_insurance.md indexed in Azure AI Search | | | |
| 4.1.2 | Index document count | Matches number of documents uploaded | | | |
| 4.1.3 | Chunk count per document | Reasonable chunking (e.g., 10-30 chunks for policy terms) | | | |
| 4.1.4 | Vector embeddings present | Each chunk has a vector embedding field populated | | | |
| 4.1.5 | Metadata fields populated | Source file name, section headers captured as metadata | | | |

### 4.2 Search Relevance

| # | Check | Expected Result | Actual Result | Pass/Fail | Notes |
|---|-------|----------------|---------------|-----------|-------|
| 4.2.1 | "contestability period" | Returns Section 8.2 and Section 3.2 content | | | |
| 4.2.2 | "suicide exclusion" | Returns Section 3.1 content | | | |
| 4.2.3 | "how to file a claim" | Returns Section 7.1 content | | | |
| 4.2.4 | "available riders" | Returns Section 9 content | | | |
| 4.2.5 | "premium payment methods" | Returns Section 5.2 content | | | |
| 4.2.6 | "policy reinstatement" | Returns Section 5.4 content | | | |
| 4.2.7 | "cash surrender value" | Returns Section 6.1 content | | | |
| 4.2.8 | Irrelevant query (e.g., "weather forecast") | Returns no results or low-confidence results | | | |

---

## 5. End-to-End Checks

| # | Check | Expected Result | Actual Result | Pass/Fail | Notes |
|---|-------|----------------|---------------|-----------|-------|
| 5.1 | Simple KPI query end-to-end | User asks "total premium" in Data Agent, gets correct answer within 10 seconds | | | |
| 5.2 | Aggregation query end-to-end | User asks "claims by type", gets correct breakdown within 15 seconds | | | |
| 5.3 | Row-level query end-to-end | User asks "policies expiring this month", gets correct list within 15 seconds | | | |
| 5.4 | Document query end-to-end | User asks "what does the policy say about X", gets relevant excerpt within 10 seconds | | | |
| 5.5 | Hybrid query end-to-end | User asks metric + document question, gets combined answer within 20 seconds | | | |
| 5.6 | Power BI report loads | Executive dashboard renders all visuals without errors | | | |
| 5.7 | Report matches agent | KPI values in Power BI report match Data Agent responses | | | |
| 5.8 | Data consistency across layers | Gold table counts match Bronze counts (accounting for quality filters) | | | |

---

## 6. Performance Checks

| # | Check | Expected Result | Actual Result | Pass/Fail | Notes |
|---|-------|----------------|---------------|-----------|-------|
| 6.1 | Bronze ingestion time (all tables) | < 5 minutes for full batch | | | |
| 6.2 | Silver transformation time | < 10 minutes for full batch | | | |
| 6.3 | Gold layer build time | < 5 minutes for full batch | | | |
| 6.4 | Semantic model refresh time | < 2 minutes | | | |
| 6.5 | Simple KPI query (Data Agent) | < 5 seconds response time | | | |
| 6.6 | Aggregation query (Data Agent) | < 10 seconds response time | | | |
| 6.7 | Row-level SQL query (Data Agent) | < 10 seconds response time | | | |
| 6.8 | Document search query | < 5 seconds response time | | | |
| 6.9 | Power BI report initial load | < 10 seconds | | | |
| 6.10 | Power BI report cross-filter | < 3 seconds per interaction | | | |

---

## 7. Validation Summary

| Category | Total Checks | Passed | Failed | Not Tested | Pass Rate |
|----------|-------------|--------|--------|------------|-----------|
| 1. Data Layer | 37 | | | | |
| 2. Semantic Model | 25 | | | | |
| 3. Data Agent | 16 | | | | |
| 4. Unstructured Flow | 13 | | | | |
| 5. End-to-End | 8 | | | | |
| 6. Performance | 10 | | | | |
| **Total** | **109** | | | | |

**Overall Validation Status**: [ ] PASS / [ ] FAIL / [ ] PASS WITH EXCEPTIONS

**Validated by**: _________________________
**Date**: _________________________
**Notes**: _________________________

---

*This document is confidential and intended for internal use by Microsoft and Manulife project stakeholders.*
