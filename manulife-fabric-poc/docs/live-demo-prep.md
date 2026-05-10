# Manulife Fabric POC — Live Demo Prep

**Use with**: `demo-script.md`
**Audience**: Manulife data & IT leadership
**Demo length**: 30 minutes (5–7 min live demo block)

---

## Environment map (fill before demo)

| Thing | Your value |
|-------|-----------|
| Fabric workspace | `___________________` |
| Lakehouse | `___________________` |
| Semantic model | `___________________` |
| Data Agent | `___________________` |
| Power BI report | `___________________` |
| Backup screenshots folder | `___________________` |

---

## T-2 hours: environment readiness (15 min)

### 1. Lakehouse data freshness (3 min)
Open lakehouse SQL endpoint and run:

```sql
SELECT 'bronze_customers' tbl, COUNT(*) cnt, MAX(_ingestion_timestamp) last_load FROM bronze_customers
UNION ALL SELECT 'gold_customers',   COUNT(*), NULL FROM gold_customers
UNION ALL SELECT 'gold_policies',    COUNT(*), NULL FROM gold_policies
UNION ALL SELECT 'gold_claims',      COUNT(*), NULL FROM gold_claims
UNION ALL SELECT 'fact_premiums',    COUNT(*), NULL FROM fact_premiums
UNION ALL SELECT 'fact_investments', COUNT(*), NULL FROM fact_investments;
```

**Expected:** 200 customers, 391 policies, 300 claims, non-zero premiums and investments. `last_load` should be recent.

### 2. Semantic model refresh (2 min)
Open the model → "Refresh now". Wait for green check. If it fails, investigate before demo.

### 3. Data Agent smoke test (5 min)
Send all five demo queries through and screenshot each response:

1. *"How many active customers do we have?"*
2. *"Show claims by policy type and region"*
3. *"Which advisors have the highest AUM?"*
4. *"What's the monthly premium trend?"*
5. *"Summarize Health claims and the relevant policy guideline"*

Save screenshots as `query1.png` … `query5.png` in your backup folder.

### 4. Power BI report (2 min)
Open the executive dashboard. Confirm tiles render with non-zero values.

### 5. Browser hygiene (3 min)
- One identity in the browser (sign out of personal accounts)
- Disable extensions that inject UI (Grammarly, Loom)
- Zoom 100%, browser maximized
- Windows Do Not Disturb on; close Teams / Slack
- Phone on silent

---

## T-30 min: final go/no-go (5 min)

| Check | Pass condition |
|-------|----------------|
| Tabs open in order | All 8 tabs loaded, no errors |
| One Data Agent test query works | Same answer as 2 hours ago |
| Power BI report loads <10 sec | Render visible |
| Backup folder accessible offline | Screenshots viewable without internet |
| Phone hotspot pre-tested | Working |

If any check fails — **switch to slides + screenshots mode**. Don't troubleshoot live.

---

## Tab order (left → right)

| # | Tab | Purpose | When you go here |
|---|-----|---------|------------------|
| 1 | Slide deck (presenter view) | Narrative spine | Start, end, transitions |
| 2 | Fabric workspace overview | "This is everything" | Slide 3 → 4 transition |
| 3 | Lakehouse Explorer | Bronze/Silver/Gold tables | Slide 5 |
| 4 | Notebook 03_gold_curated_layer | Pre-scrolled view | Slide 5, ~10 sec |
| 5 | Semantic Model (model view) | Star schema + DAX measure open | Slide 6 |
| 6 | Power BI Executive Dashboard | Visual proof | Slide 6 → 8, ~30 sec |
| 7 | Data Agent chat | THE demo | Slide 9, 7 min |
| 8 | Backup screenshots folder | Recovery only | If something breaks |

**Don't open**: email, Teams, anything that pings.

---

## Architecture-to-query map

The five queries are designed to exercise each layer of the reference architecture (Slide 3). Use this as your mental anchor while running the demo:

| Query | Surface | Access path | Semantic | Storage | Key insight to land |
|-------|---------|-------------|----------|---------|---------------------|
| 1 | Standalone chat | Structured | `[Active Customer Count]` | gold_customers | Measure-first, not SQL |
| 2 | Standalone chat | Structured | Multi-dim slice | dim_product × dim_advisor | Star schema joins via the model |
| 3 | Standalone chat | Structured | Top-N pattern | dim_advisor + fact_investments | Implicit ranking |
| 4 | Standalone chat | Structured | Time intelligence | dim_date | Date dimension is real, not auto-generated |
| 5 | Standalone chat | **Both paths** | `[Claim Approval Rate]` + RAG | Gold + AI Search index | **The architecture's defining moment** |

Query 5 is the architecture's stress-test. Spend 90 seconds on it. Land the line:

> *"Numbers from the model. Citation from the document. One cited answer. That's the architecture working."*

---

## Failure recovery — exact moves

| Failure | Move | Time |
|---------|------|------|
| Data Agent shows "thinking" >20 sec | "Preview can be slow under load — here's the verified result" → open Tab 8, show backup screenshot | 10 sec |
| Data Agent returns wrong answer | "Let me show you the verified result" → backup screenshot. Don't argue live. | 5 sec |
| Whole agent panel errors out | "Preview software — exactly why we test." Drive Slide 9 + screenshots through all 5 queries. | 30 sec |
| Lakehouse won't load | Skip Block A (lakehouse walkthrough). Stay on slide 5. | 0 sec |
| Browser tab crashes | Reopen from bookmarks (saved tonight). Don't restore session. | 30 sec |
| WiFi drops | Phone hotspot. Pre-configure tonight. | 60 sec |
| Audience hard question mid-demo | "Great question — let me hold it until after the demo so we don't lose the flow." Park visibly. | 5 sec |

---

## Three lines to memorize

These land in any audience and buy you thinking time:

1. **Opening the demo:**
   *"Five queries, increasing complexity. I'll narrate what's happening underneath each one — because the point isn't that it answered, it's how it answered."*

2. **When something is slow or breaking:**
   *"This is preview software — exactly why we test it before we bet on it."*

3. **Closing the demo (after Query 5):**
   *"Numbers from the model. Citation from the document. One cited answer. That's the architecture working."*

---

## Tonight's checklist

- [ ] Run T-2 hour environment checks (you'll do them again tomorrow)
- [ ] Save 5 backup screenshots (`query1.png` … `query5.png`)
- [ ] Practice live demo aloud, with stopwatch — target 7 min flat
- [ ] Test phone hotspot
- [ ] Confirm Slide 3 PREVIEW tag is on Fabric Data Agent only (not the full access section)
- [ ] Confirm Slide 9 queries match this prep doc
- [ ] Sleep

## Tomorrow morning (final 90 min)

- [ ] Re-run T-2 hour checks
- [ ] Run T-30 min go/no-go
- [ ] One full timed run-through end to end
- [ ] Tabs open in order, laptop charged, phone silent

---

## Tough Q&A bank — data/IT audience

Marked **★** = high likelihood. See `risks-and-blockers.md` for full list.

### Architecture & storage
1. **★** *"How is OneLake different from ADLS Gen2 — isn't it just Gen2 underneath?"*
   → Yes, built on Gen2. Differentiator is the unified namespace and Fabric-managed governance, not the storage substrate.
2. **★** *"When does DirectLake fall back to Import mode?"*
   → Capacity pressure or unsupported features (calculated columns, certain DAX patterns). Capacity sizing matters. See risks doc row #11.
3. *"Delta protocol version — Databricks compatible?"*
   → Yes. Delta is open. Cross-engine reads work. Verify protocol version in the Delta log if writing from both.
4. *"Schema evolution?"*
   → Delta handles additive changes natively. Silver layer enforces schema contract. Breaking changes need a versioned table.

### Governance & security
5. **★** *"Does RLS pass through to the Data Agent?"*
   → Limited in preview. Honest answer: this is open question Q-MS-3 with Microsoft. RLS in the model works today; pass-through to Data Agent improves at GA.
6. **★** *"OSFI audit logging — where do queries land?"*
   → Power BI activity log + Fabric workspace audit. Data Agent query audit is limited in preview. Recommend custom logging via the orchestration layer until GA.
7. *"Microsoft Purview integration?"*
   → Lineage flows to Purview for OneLake. Sensitivity labels propagate from M365.
8. *"Data residency — Canada Central only?"*
   → Yes. Fabric capacity is region-pinned. OneLake respects that.
9. *"Does the LLM see customer PII?"*
   → The Data Agent grounds in semantic model schema and the user question — sends shape, not rows. Aggregated results pass through. Confirm exact data flow with the AE if pressed.

### Performance & cost
10. **★** *"What capacity SKU for production?"*
    → POC ran on F2/F4. Production sizing depends on concurrent users and refresh frequency. Model in Phase 2 with Fabric Capacity Metrics app.
11. **★** *"Data Agent query cost in CUs?"*
    → Not well documented in preview. Open question Q-MS-5.
12. *"DirectLake cold start latency?"*
    → First query warms the column cache (a few seconds). Subsequent queries are sub-second.
13. *"Cost vs Snowflake + Databricks?"*
    → Don't try to win with numbers you don't have. Pivot: "Single capacity model, no cross-service data movement charges. We can do detailed TCO modeling in Phase 2."

### Comparison
14. **★** *"Why Fabric over Databricks + Power BI separately?"*
    → OneLake unifies storage (no copy), one capacity, one governance plane. If you're already deep in Databricks, OneLake shortcuts let both coexist.
15. *"Why semantic model over views in the lakehouse?"*
    → Semantic model encodes business measures (DAX), not just shape. It's the trust layer.
16. *"Isn't this just Power BI Copilot rebranded?"*
    → Different scope. Data Agent is multi-source grounding (semantic model + SQL endpoint + docs via orchestration). PBI Copilot is single-report.

### Operations
17. **★** *"CI/CD — how does this deploy?"*
    → Fabric Git integration (workspace ↔ Azure DevOps/GitHub). Notebooks, pipelines, semantic model definitions all Git-tracked. Deployment pipelines for dev/test/prod.
18. *"How do we test DAX measures?"*
    → Compare DAX output against a SQL baseline. See validation-checklist.md §2.1.
19. *"DR for OneLake?"*
    → Geo-redundancy at the storage layer. Workspace-level DR is your responsibility — design for restore from source.

### AI / Data Agent
20. **★** *"How do you prevent hallucination?"*
    → Three guardrails: grounding to semantic model only, pre-defined DAX measures (not generated from scratch), source attribution in every response.
21. **★** *"Does data leave the Fabric tenant for the LLM?"*
    → The model call is within Microsoft's tenant boundary; data is grounded, not sent for training. Get exact answer from your AE if pushed.
22. *"Can we tune the system prompt?"*
    → Yes. Custom system prompts and few-shot examples are supported.
23. *"Language support?"*
    → English only in preview. French is on the roadmap — important for Manulife (regulatory). risks-and-blockers §1.5.

### Phase 2 / production
24. **★** *"Production integration with Guidewire?"*
    → Open question Q-ML-1. Needs Phase 2 scoping.
25. *"Migration path from existing platform?"*
    → Coexistence first via OneLake shortcuts; phased migration domain by domain.

---

*Confidential — Microsoft and Manulife project stakeholders only.*
