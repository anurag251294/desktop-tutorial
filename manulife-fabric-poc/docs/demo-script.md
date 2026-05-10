# Manulife Fabric POC — Demo Script

**Duration**: 30 minutes (slides + live demo + Q&A buffer)
**Audience**: Manulife data & IT leadership (technical)
**Aligned to**: Reference Architecture (Slide 3) and Demo Walkthrough (Slide 9)
**Last Updated**: 2026-05-10

---

## 1. Architecture-to-demo mapping

The five demo queries are not arbitrary — each one exercises a specific layer of the reference architecture on Slide 3. This is what makes the demo a stress-test of the architecture, not a feature parade.

| # | Query | Architecture layers exercised |
|---|-------|-------------------------------|
| 1 | "How many active customers do we have?" | Surfaces → Data Agent → Semantic Model → DirectLake → Gold |
| 2 | "Show claims by policy type and region" | Multi-dim slice via star schema (dim_product × dim_advisor) |
| 3 | "Which advisors have the highest AUM?" | TopN ranking via dim_advisor + fact_investments |
| 4 | "What's the monthly premium trend?" | Time intelligence via dim_date |
| 5 | "Summarize Health claims and the relevant policy guideline" | **Both paths converge** at the orchestration layer: Data Agent (structured) + Azure AI Search RAG (unstructured) |

Query 5 is the architecture's defining moment — a single question that traverses the structured and unstructured paths and merges them through orchestration into one cited response.

---

## 2. Pre-demo checklist (T-2 hours)

| # | Item | Pass criterion |
|---|------|----------------|
| 1 | Lakehouse SQL endpoint reachable | `SELECT COUNT(*) FROM gold_customers` returns 200 |
| 2 | Bronze freshness | `SELECT MAX(_ingestion_timestamp) FROM bronze_customers` is recent |
| 3 | Semantic model refresh successful | Green check, no errors |
| 4 | Power BI report renders | All KPI tiles non-zero |
| 5 | Data Agent answers test query | "How many active customers" returns 200 |
| 6 | Azure AI Search index hit | Search "contestability" returns chunks from claims_handbook |
| 7 | All 5 demo queries pre-tested | Screenshots saved to backup folder |
| 8 | Browser zoom 100%, DND on | — |

If any check fails, fix it now or fall back to slides + screenshots mode.

---

## 3. Tabs to open (left → right)

1. Slide deck (presenter view)
2. Fabric workspace overview
3. Lakehouse Explorer (Gold layer expanded)
4. Notebook `03_gold_curated_layer` (pre-scrolled to fact_claims build)
5. Semantic Model (model view, Claim Approval Rate measure pinned)
6. Power BI Executive Dashboard
7. Data Agent chat (signed in, ready)
8. Backup screenshots folder (recovery only)

---

## 4. Demo flow (30 minutes)

### Section 1 — Opening (3 min)

**Slide 1 → Slide 2.**

Three takeaways the audience should leave with:

1. **OneLake + semantic model** is a GA, production-ready foundation
2. **Fabric Data Agent** is preview — we're showing the interaction pattern, not a prod deployment
3. Every answer is **grounded in the actual data** — semantic model measures or document chunks, not LLM training data

> *"Three things to take away today. One — OneLake plus the semantic model is the durable, GA foundation. Two — the Data Agent is preview, so we're showing you the pattern, not a production deployment. Three — every answer you'll see is grounded in the actual data, not an LLM hallucinating."*

### Section 2 — Reference Architecture (5 min)

**Slide 3 — the most important slide for this audience.**

Walk top-down, calling out each layer:

> *"Read this top-down — data flows up. At the base, the source systems: 7 structured tables, 8 documents. Above that, ingestion via Fabric Pipelines and 5 PySpark notebooks. Then OneLake — bronze, silver, gold, plus a docs table — all open Delta Parquet. Above that, the semantic model in DirectLake mode — zero-copy reads of the gold layer, 14 DAX measures, RLS-aware. The access layer splits into two paths: structured Q&A through the Data Agent, unstructured Q&A through Azure AI Search and GPT-4o. Both paths converge at the orchestration layer — Azure OpenAI as the intent router and merger. Surfaces on top: standalone chat, Power BI dashboards. And on the right, governance — Entra ID, RLS, Purview, audit logs, DLP — touches every layer. It's not a layer; it's a vertical rail."*

**Anticipated questions and ready answers:**
- *"How is OneLake different from ADLS Gen2?"* — "Same storage substrate, but Fabric adds the unified namespace and cross-workload governance. The differentiator is the namespace, not the bytes."
- *"When does DirectLake fall back to Import?"* — "Capacity pressure or unsupported features. We model capacity in Phase 2."
- *"Is the access layer all preview?"* — "No — only the Fabric Data Agent. Azure AI Search and GPT-4o are GA."

### Section 3 — Data Foundation (3 min)

**Slide 5 → switch to Tab 3 (Lakehouse).**

> *"This is the lakehouse. Bronze, silver, gold, and docs — exactly the structure on Slide 3."*

**Click `gold_customers`.**

> *"200 customer records, deduplicated, in Delta. The customer_key column is a surrogate key generated in the gold notebook."*

**(Optional) Switch to Tab 4 (notebook). Scroll to the fact_claims build.**

> *"This is the notebook that builds fact_claims. Pure PySpark, idempotent, runs in Fabric. The five notebooks pictured on Slide 3 — bronze, silver, gold, docs, validate — are exactly what's in the repo."*

**Back to slides.**

### Section 4 — Semantic Layer (3 min)

**Slide 6 → switch to Tab 5 (Semantic Model).**

> *"4 facts, 6 dimensions. Single-direction filtering from dimensions to facts — no ambiguity. This is the trust layer Slide 3 calls out."*

**Click on the `Claim Approval Rate` measure → properties pane.**

> *"One DAX expression. Power BI uses it. Excel uses it. The Data Agent uses it. Same answer everywhere — that's the whole point. The agent never queries raw tables; it queries measures. Consistency is by construction, not by hope."*

**(Optional) Quick switch to Tab 6 (Power BI report) for ~20 seconds.**

> *"Same measure powers this dashboard. But not every question fits a dashboard."*

### Section 5 — AI Access modes (2 min)

**Slide 8.**

> *"Two query modes over one governed model. Left side — structured: natural language resolves to a measure, generates DAX, returns a table and chart. Right side — unstructured: question gets embedded, hits Azure AI Search, top chunks reranked with GPT-4o, returns a cited answer. Both inherit RLS, RBAC, and audit from the layers below. That's how we keep this governable."*

**Transition to Slide 9.**

### Section 6 — Live Demo (7 min) — the main event

**Slide 9 → switch to Tab 7 (Data Agent).**

> *"Five queries, increasing complexity. I'll narrate what's happening underneath each one — because the point isn't that it answered, it's how it answered."*

#### Query 1 — Simple (60 sec)

**Type:** `How many active customers do we have?`

**While processing:**
> *"This is the agent resolving 'active customers' to the [Active Customer Count] measure. No SQL generated. No DAX hallucinated. It's calling a pre-defined measure from the semantic model."*

**On answer:**
> *"That's the baseline. One measure, no slicing. Notice the source attribution — the agent tells us it queried the semantic model, not raw SQL."*

#### Query 2 — Analytical (90 sec)

**Type:** `Show claims by policy type and region`

**While processing:**
> *"Two-dimensional slice. The agent has to pick a measure plus two dimensions — `dim_product.line` for policy type, `dim_advisor.region` for region. That mapping works because the dimensions have AI-friendly synonyms in the semantic model."*

**On answer:**
> *"Auto-generated chart, two-dim breakdown. This would have taken a Power BI developer 20 minutes."*

#### Query 3 — Comparative (90 sec)

**Type:** `Which advisors have the highest AUM?`

**While processing:**
> *"Top-N pattern. Implicit ranking, implicit aggregation. The agent figures out it should sort by `[Total AUM]` descending and limit to the top N."*

**On answer:**
> *"Five advisors, ranked. This is the kind of ad-hoc question that doesn't live on any dashboard."*

#### Query 4 — Trend (90 sec)

**Type:** `What's the monthly premium trend?`

**While processing:**
> *"Time intelligence. The agent recognizes 'monthly trend' means group by `dim_date.year_month` and order chronologically. This is where DAX generation gets harder — and where pre-defined measures keep us safe."*

**On answer:**
> *"Six-month trend, line chart. The model didn't fabricate dates — it pulled from the actual date dimension."*

#### Query 5 — Hybrid (90 sec) — the punchline

**Type:** `Summarize Health claims and the relevant policy guideline`

**While processing — and this is the line to nail:**
> *"This one runs both paths from Slide 3. The structured side hits `[Claim Approval Rate]` filtered to Health. The unstructured side embeds the question, hits Azure AI Search, finds the relevant section in claims_handbook.pdf, reranks with GPT-4o. The orchestration layer merges them into one cited response."*

**On answer:**
> *"Numbers from the model. Citation from the document. One answer. This is the architecture stress-test — and this is what you couldn't do with Power BI alone, or a chatbot alone."*

### Section 7 — Why Fabric (2 min)

**Slide 10.** Read the four numbered points cleanly. Don't elaborate — the audience just saw the proof.

### Section 8 — Recap & Q&A (5 min)

**Slide 11.** Recap the five sections. Open for questions.

> *"Happy to take questions. We've documented 12 known limitations and the open questions for both Microsoft and Manulife — those are in the risks-and-blockers doc, available after the session."*

---

## 5. Backup pre-prepared results (in case of failure)

### Backup 1 — Active Customer Count
| Metric | Value |
|--------|-------|
| Active customers | **200** |
| With ≥ 1 active policy | **187** |

### Backup 2 — Claims by Policy Type and Region
| Policy Type | Ontario | Quebec | BC | Alberta | Other |
|-------------|---------|--------|-----|---------|-------|
| Life | $4.2M | $2.8M | $1.9M | $1.6M | $1.1M |
| Health | $3.1M | $2.2M | $1.5M | $1.2M | $0.8M |
| Auto | $2.8M | $1.9M | $1.3M | $1.0M | $0.7M |
| Home | $1.5M | $1.0M | $0.7M | $0.5M | $0.4M |
| Travel | $0.4M | $0.3M | $0.2M | $0.2M | $0.1M |

### Backup 3 — Top 5 Advisors by AUM
| Rank | Advisor | Region | Total AUM (CAD) |
|------|---------|--------|-----------------|
| 1 | Sarah Chen | Ontario | $48.2M |
| 2 | James Williams | BC | $42.7M |
| 3 | Priya Patel | Quebec | $38.9M |
| 4 | Robert Martin | Alberta | $35.4M |
| 5 | Lisa Thompson | Ontario | $32.1M |

### Backup 4 — Monthly Premium Trend
| Month | Premium Revenue |
|-------|-----------------|
| Nov 2025 | $12.01M |
| Dec 2025 | $12.31M |
| Jan 2026 | $12.33M |
| Feb 2026 | $12.14M |
| Mar 2026 | $12.21M |
| Apr 2026 | $12.09M |

### Backup 5 — Hybrid: Health claims + guideline
> Health insurance claim approval rate is **68.4%** over the trailing six months (vs. 71.2% for life, 64.8% for auto).
>
> According to the Manulife Claims Processing Guideline (`claims_handbook.pdf`, Section 4.2 — Health Claims SLA):
>
> *"Health insurance claims must be acknowledged within 2 business days of receipt. Initial decision (approve, deny, or request additional information) is required within 10 business days for non-complex claims and 30 business days for complex claims requiring medical review."*
>
> **Sources**: Semantic Model — `[Claim Approval Rate]`; Azure AI Search — `claims_handbook.pdf` p.12.

---

## 6. Failure recovery cheatsheet

| Failure | Recovery |
|---------|----------|
| Data Agent slow (>20 sec) | "Preview can be slow under load — here's the verified result" → backup screenshot |
| Wrong answer | Don't argue live. "Let me show you the verified result" → backup |
| Agent panel errors | Drive Slide 9 with backup screenshots, narrate each query |
| Lakehouse won't load | Skip section 3, keep slides 5-6 from deck |
| WiFi drops | Phone hotspot (pre-tested) |
| Hard mid-demo question | "Great question — let me hold it until after the demo so we don't lose the flow." Park visibly. |

---

## 7. Lines worth memorizing

1. *"Five queries, increasing complexity. The point isn't that it answered, it's how it answered."*
2. *"This is preview software — exactly why we test it before we bet on it."*
3. *"Numbers from the model. Citation from the document. One cited answer. That's the architecture working."*

---

*Confidential — Microsoft and Manulife project stakeholders only.*
