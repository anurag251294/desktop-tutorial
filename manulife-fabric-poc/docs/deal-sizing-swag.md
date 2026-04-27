# Manulife Fabric Opportunity — Deal Sizing (SWAG)

> **Status**: Rough estimate — not validated with customer or Microsoft  
> **Date**: April 2026  
> **Prepared by**: POC delivery team  
> **Classification**: Internal use only — do not share externally without review

---

## 1. Opportunity Summary

Manulife is evaluating Microsoft Fabric as the data foundation for a Copilot-style natural-language analytics experience across insurance and investment lines of business. The POC demonstrates structured + unstructured data integration through OneLake, a semantic model for trusted KPIs, and Fabric Data Agent as the governed query layer.

**Customer profile**:
- ~38,000 employees globally
- $900B+ assets under management
- Operations across Canada, US, and Asia
- Business lines: Group Benefits, Individual Insurance, Wealth & Asset Management, Retirement

**Initial use case**: Claims and policy analytics with natural-language access for service reps and business analysts.

---

## 2. POC / Pilot Phase (3-4 Months)

| Component | Monthly | Total (4 mo) | Notes |
|-----------|---------|--------------|-------|
| Fabric capacity (F64) | $6K-$8K | $24K-$32K | Minimum viable for POC with notebooks, pipelines, semantic model |
| Azure AI Search (Basic) | $1K | $3K-$5K | Single index, low query volume |
| Azure OpenAI (S0) | $1K-$3K | $5K-$10K | Embeddings + GPT-4o for orchestration, low throughput |
| Power BI Pro licenses (10 seats) | $1K | $4K | For semantic model development and testing |
| **Azure consumption subtotal** | | **$36K-$51K** | |
| Consulting — architecture & implementation | | $75K-$150K | Depends on partner vs internal delivery |
| **POC Total** | | **$110K-$200K** | |

**Target landing deal**: $150K-$200K

---

## 3. Year 1 — Production Deployment

Assumes successful POC leading to a production rollout for the initial business unit (e.g., Group Benefits or Individual Insurance claims analytics).

| Component | Annual Estimate | Notes |
|-----------|----------------|-------|
| Fabric capacity (F128-F256) | $200K-$500K | Production workloads, concurrent users, data volume |
| Power BI Premium (P1-P2 or PPU) | $60K-$250K | Depends on seat count vs capacity model |
| Azure OpenAI | $100K-$250K | Production query volume, multiple use cases |
| Azure AI Search (Standard S1-S2) | $50K-$120K | Vector search, multiple indexes, replicas |
| Azure Key Vault, Storage, Monitoring | $10K-$30K | Supporting infrastructure |
| **Azure + licensing subtotal** | **$420K-$1,150K** | |
| Implementation & build-out | $300K-$800K | Production hardening, security, testing, rollout |
| **Year 1 Total** | **$720K-$1.95M** | |

**Target Year 1 deal**: $1M-$2M

---

## 4. Steady-State Annual Run Rate (Year 2+)

| Component | Annual Estimate | Notes |
|-----------|----------------|-------|
| Fabric capacity | $250K-$600K | May grow with data volume and user concurrency |
| Power BI licensing | $60K-$250K | Stable unless seat count expands |
| Azure AI services (OpenAI + Search) | $150K-$350K | Scales with query volume and index size |
| Managed services / ongoing support | $150K-$400K | L2/L3 support, model tuning, enhancements |
| **Annual Run Rate** | **$610K-$1.6M** | |

---

## 5. Expansion Potential

The initial use case is a wedge into a much larger opportunity. Manulife has multiple business units that could adopt the same pattern.

### Expansion vectors

| Vector | Description | Revenue multiplier |
|--------|-------------|-------------------|
| **Additional business units** | Group Benefits, Individual Insurance, Wealth & Asset Management, Retirement — each could replicate the Fabric + Data Agent pattern | 2x-4x |
| **Additional data domains** | Actuarial, risk, compliance, finance, operations | 1.5x-2x |
| **Copilot seat expansion** | From pilot group (50-100 users) to enterprise rollout (1,000-5,000+ seats) | Significant licensing uplift |
| **Data volume growth** | More sources, more history, real-time streams — drives capacity upgrades | 1.3x-2x on Fabric capacity |
| **Geographic expansion** | US and Asia operations adopting the same platform | 1.5x-2x |
| **Advanced AI use cases** | Agentic workflows, automated claims triage, advisor copilot, customer-facing bots | Incremental Azure AI spend |

### 3-Year total contract value scenarios

| Scenario | Assumptions | 3-Year TCV |
|----------|-------------|------------|
| **Conservative** | Single BU, contained scope, no major expansion | $1.5M-$3M |
| **Base case** | 2-3 BUs adopt, moderate seat expansion, steady growth | $3M-$6M |
| **Upside** | Enterprise-wide adoption, Copilot at scale, multiple AI use cases | $6M-$12M+ |

---

## 6. Key Assumptions and Risks

### Assumptions

- Manulife does **not** already have significant Fabric / Power BI Premium licensing in place (if they do, incremental Azure spend is lower but consulting opportunity remains)
- Fabric Data Agent reaches GA in a timeframe compatible with Manulife's production requirements
- The POC successfully demonstrates value to business stakeholders
- Partner-delivered consulting (our engagement) is the preferred delivery model
- No existing competing platform commitment (e.g., Databricks, Snowflake) that would block Fabric adoption

### Risks to deal size

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Manulife has existing ELA with Microsoft that covers Fabric | Reduces net-new licensing — consulting opportunity remains | Medium | Validate current licensing posture early |
| Data Agent stays in preview longer than expected | Delays production commitment, reduces Year 1 | Medium | Position POC as architecture validation; pivot to Power BI Copilot if needed |
| Competing platform already entrenched | May limit to specific BUs or use cases | Low-Medium | Position Fabric as complementary or replacement for specific workloads |
| Budget freeze / procurement delays | Extends sales cycle | Low | Align to existing budget cycles; position POC as low-cost validation |
| Internal build preference | Manulife builds internally rather than using partner | Medium | Demonstrate velocity and expertise in POC; propose hybrid model |

### Upside drivers

- Microsoft co-sell / co-invest interest (Manulife is a strategic account)
- Regulatory or compliance mandate to modernize data platform
- Competitive pressure from peers adopting AI-driven analytics
- Executive sponsor with transformation mandate

---

## 7. Competitive Landscape

| Competitor | Threat | Our positioning |
|------------|--------|-----------------|
| Databricks + Unity Catalog | Strong in data engineering; weaker in BI and Copilot | Fabric offers unified platform — no BI/AI stitching required |
| Snowflake + Cortex | Growing AI/ML capabilities | Fabric's Power BI integration and Copilot experience are differentiated |
| AWS (Bedrock + Redshift) | Enterprise alternative | Manulife likely has Azure affinity given Microsoft relationship |
| Internal / custom build | Always a risk | Our POC demonstrates speed-to-value that internal teams can't match |

---

## 8. Recommended Next Steps

| # | Action | Owner | Timeline |
|---|--------|-------|----------|
| 1 | Validate Manulife's current Microsoft licensing posture (ELA, Fabric, Power BI) | Account team | Week 1 |
| 2 | Identify executive sponsor and budget holder | Account team | Week 1-2 |
| 3 | Present POC results and reference architecture | Delivery team | Week 2 |
| 4 | Scope production pilot (single BU, defined user group) | Joint | Week 3-4 |
| 5 | Develop SOW for production phase | Delivery team | Week 4-5 |
| 6 | Engage Microsoft co-sell / FastTrack team | Account team | Week 2-3 |
| 7 | Align on success criteria and go/no-go for enterprise expansion | Joint | Month 3-4 |

---

## 9. Deal Summary

| Metric | Estimate |
|--------|----------|
| **POC deal** | $150K-$200K |
| **Year 1 production** | $1M-$2M |
| **Annual run rate (Year 2+)** | $600K-$1.5M |
| **3-Year TCV (base case)** | $3M-$6M |
| **3-Year TCV (upside)** | $6M-$12M+ |

> **Bottom line**: Land with a $150K-$200K POC, convert to a $1M-$2M Year 1 production deal, and expand to $3M-$6M over 3 years across multiple business units. Microsoft co-sell alignment and Fabric Data Agent GA timing are the two biggest swing factors.
