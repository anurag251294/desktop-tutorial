# Manulife Fabric POC - Risks, Blockers, and Mitigations

**Version**: 1.1
**Last Updated**: 2026-05-10
**Status**: Phase 4 Deliverable

> **For demo Q&A**: see `live-demo-prep.md` §"Tough Q&A bank" for the audience-tailored short list.
> This document is the full risk register and remains the authoritative source for follow-up answers.

---

## Table of Contents

1. [Potential First-Adopter Blockers](#1-potential-first-adopter-blockers)
2. [Known Limitations and Preview Dependencies](#2-known-limitations-and-preview-dependencies)
3. [Risk Register](#3-risk-register)
4. [Open Questions for Microsoft](#4-open-questions-for-microsoft)
5. [Open Questions for Manulife](#5-open-questions-for-manulife)
6. [Recommended Risk Mitigations](#6-recommended-risk-mitigations)

---

## 1. Potential First-Adopter Blockers

### 1.1 Data Agent is in Public Preview

**Description**: The Fabric Data Agent is a public preview feature as of April 2026. Preview features are not covered by production SLAs, may change without notice, and are not recommended for production workloads by Microsoft.

**Impact on Manulife**:
- Cannot be deployed as a production tool for end users until GA
- Feature behavior, API surface, and configuration options may change between preview and GA
- Preview environments may experience downtime or performance degradation without notice
- Microsoft support for preview features is best-effort, not covered under Premier/Unified support agreements

**Mitigation**:
- Use the POC to validate the interaction pattern and gather user feedback, not to deploy a production system
- Build the data foundation (OneLake, semantic model) on GA components that deliver value independently of the Data Agent
- Maintain an orchestration layer that can adapt to API changes at GA
- Track the Data Agent roadmap through Microsoft's Fabric release notes and monthly updates

### 1.2 Multi-Source Grounding Not Yet Available

**Description**: The Data Agent currently supports grounding on a single data source per agent configuration (either a semantic model or a SQL endpoint, but not both simultaneously in a single query with native routing). Multi-source grounding with automatic intent classification is on the roadmap but not yet available.

**Impact on Manulife**:
- Hybrid queries (structured + unstructured) require external orchestration
- Users cannot seamlessly ask a question that requires both KPI data and document context in a single agent interaction without middleware
- Adds architectural complexity and additional components to maintain

**Mitigation**:
- Implement a Prompt Flow orchestration layer that handles intent classification and multi-source routing
- Design the orchestration layer as a thin wrapper that can be removed when native multi-source grounding is available
- For the demo and pilot, pre-configure the agent to default to the semantic model and provide document context via a separate workflow

### 1.3 No Native RAG Integration in Data Agent

**Description**: The Data Agent does not natively integrate with Azure AI Search or other RAG (Retrieval-Augmented Generation) document stores. Unstructured document queries must be handled outside the Data Agent.

**Impact on Manulife**:
- The unified "ask anything" experience requires additional infrastructure (Azure AI Search, embedding model, orchestration endpoint)
- Document-sourced answers cannot be seamlessly combined with structured data answers in a single agent response
- Additional cost and operational overhead for the RAG infrastructure

**Mitigation**:
- Build the Azure AI Search index and orchestration layer as a parallel workstream
- Position the RAG capability as an "enrichment" layer rather than a core requirement for Phase 1
- Monitor Microsoft announcements for native RAG integration in Data Agent (expected H2 2026)

### 1.4 DAX Generation Accuracy

**Description**: The Data Agent generates DAX queries from natural language. For complex queries involving multiple measures, time intelligence, or calculated columns, the generated DAX may be incorrect or suboptimal.

**Impact on Manulife**:
- Users may receive incorrect answers for complex analytical questions
- Requires validation of agent responses against known-correct results
- May erode user trust if inaccurate answers are not caught

**Mitigation**:
- Include comprehensive few-shot examples in the agent configuration for known query patterns
- Define and validate all critical business measures as explicit DAX measures in the semantic model (rather than relying on the agent to generate them from scratch)
- Implement a feedback mechanism for users to flag suspected inaccuracies
- Include a disclaimer in the agent response for complex queries: "This answer was generated from your data. Please verify critical business decisions with the source report."

### 1.5 French Language Support

**Description**: The Data Agent preview does not support French language queries or responses. Manulife operates across Canada and has regulatory and business requirements for bilingual support.

**Impact on Manulife**:
- Cannot deploy to French-speaking users or regions until French is supported
- Regulatory compliance may require French accessibility for certain use cases
- Limits the addressable user base for a Canada-wide deployment

**Mitigation**:
- Plan for French support as a Phase 2 requirement
- Validate that the underlying data model supports French labels and metadata
- Track Microsoft's language expansion roadmap for Data Agent
- Consider a translation layer as an interim workaround if needed before native support

### 1.6 Fabric Capacity and Cost Model

**Description**: Microsoft Fabric uses a capacity-based pricing model (CU-hours). The Data Agent, Direct Lake queries, and notebook execution all consume capacity. Cost predictability for Manulife at production scale is not yet validated.

**Impact on Manulife**:
- Production costs may differ significantly from POC costs
- Data Agent query costs are not well documented for preview features
- Unpredictable capacity consumption could lead to throttling or unexpected costs

**Mitigation**:
- Monitor capacity consumption during the POC using Fabric Capacity Metrics app
- Establish baseline consumption profiles for each workload type (ingestion, transformation, BI, agent)
- Work with the Microsoft account team to model production costs before Phase 2 commitment
- Implement capacity alerting and auto-pause policies

---

## 2. Known Limitations and Preview Dependencies

| # | Limitation | Status | Impact | Dependencies |
|---|-----------|--------|--------|--------------|
| 1 | Data Agent is public preview | Preview | No production SLA, features may change | GA release (timeline TBD) |
| 2 | Single grounding source per agent | Preview limitation | Cannot natively combine semantic model + SQL endpoint queries | Multi-source grounding (expected H2 2026) |
| 3 | No native RAG/document grounding | Not available | Unstructured queries require external orchestration | Native RAG integration (expected H2 2026) |
| 4 | French language not supported | Not available | Cannot serve French-speaking users | Language expansion (2026-2027) |
| 5 | Row-level security pass-through | Limited | Agent may not enforce per-user RLS | RLS in Data Agent (GA timeline TBD) |
| 6 | No write-back / action triggers | Not available | Agent is read-only, cannot trigger workflows | Custom skills/plugins (expected H2 2026) |
| 7 | Limited query complexity | Preview | Complex multi-measure or time-intelligence queries may produce incorrect results | Improved DAX generation at GA |
| 8 | No query audit logging | Limited | Cannot track what users asked or how accurate responses were | Agent analytics (GA timeline TBD) |
| 9 | Response latency variability | Preview | Query response times may be inconsistent | Performance optimization at GA |
| 10 | No custom branding | Not available | Agent interface cannot be branded for Manulife | Customization options (timeline TBD) |
| 11 | Direct Lake fallback to import | GA with caveats | Under heavy load, Direct Lake may fall back to import mode, requiring data refresh | Capacity sizing |
| 12 | Notebook scheduling reliability | GA | Occasional missed schedules under high workspace load | Monitoring and alerting |

---

## 3. Risk Register

| # | Risk | Likelihood | Impact | Severity | Mitigation |
|---|------|-----------|--------|----------|------------|
| R1 | Data Agent GA timeline slips beyond H2 2026 | Medium | High | **High** | Build value on GA components (OneLake, semantic model, Power BI). Position Data Agent as additive, not foundational. |
| R2 | DAX generation produces incorrect results for critical KPIs | Medium | High | **High** | Pre-define all critical measures as explicit DAX in the semantic model. Use few-shot examples. Implement user feedback loop. |
| R3 | Preview service outage during demo or pilot | Medium | Medium | **Medium** | Prepare backup screenshots and pre-cached results. Test within 2 hours of any demo. |
| R4 | Manulife data governance requirements exceed Fabric capabilities | Low | High | **Medium** | Validate sensitivity labels, RLS, and audit capabilities against Manulife's data governance framework early in Phase 2. |
| R5 | Capacity costs exceed budget at production scale | Medium | Medium | **Medium** | Model costs during POC. Use Fabric Capacity Metrics app. Engage Microsoft account team for cost optimization. |
| R6 | French language support not available by production deployment | Medium | Medium | **Medium** | Plan bilingual support as Phase 2. Explore translation layer as interim. Track Microsoft roadmap. |
| R7 | User adoption challenges - business users do not trust agent answers | Medium | Medium | **Medium** | Include source attribution in every response. Allow users to verify against Power BI reports. Implement feedback mechanism. |
| R8 | Integration with Manulife source systems is more complex than estimated | Medium | Medium | **Medium** | Conduct a detailed source system assessment early in Phase 2. Allocate buffer for integration complexity. |
| R9 | Multi-source grounding does not deliver expected accuracy at GA | Low | High | **Medium** | Maintain the orchestration layer as a fallback. Design for source-routing flexibility. |
| R10 | Azure AI Search index quality degrades answer relevance | Medium | Medium | **Medium** | Invest in chunking strategy, metadata enrichment, and relevance testing. Iterate on search configuration. |
| R11 | Fabric workspace security model does not align with Manulife's org structure | Low | Medium | **Low** | Map Manulife's security requirements to Fabric workspace/item-level security early. Validate with the security team. |
| R12 | POC data does not adequately represent production complexity | Low | Medium | **Low** | Expand data volume and variety in Phase 2. Include edge cases and production-representative scenarios. |

---

## 4. Open Questions for Microsoft

| # | Question | Context | Priority | Status |
|---|----------|---------|----------|--------|
| Q-MS-1 | What is the expected GA timeline for Data Agent? | Manulife needs GA for production deployment. Preview is not acceptable for regulated financial services. | **Critical** | Open |
| Q-MS-2 | Will multi-source grounding support semantic model + SQL endpoint + Azure AI Search simultaneously? | Current limitation requires external orchestration. Manulife needs native multi-source for production. | **Critical** | Open |
| Q-MS-3 | How will row-level security be enforced in Data Agent queries? | Manulife has strict data access policies. RLS pass-through is required for production. | **Critical** | Open |
| Q-MS-4 | What is the roadmap for French language support in Data Agent? | Regulatory requirement for Canadian financial services. | **High** | Open |
| Q-MS-5 | How is Data Agent usage metered against Fabric capacity? | Cost predictability is required for budget planning. | **High** | Open |
| Q-MS-6 | Will there be an API for Data Agent to enable embedding in custom applications? | Manulife may want to embed agent capabilities in internal portals. | **Medium** | Open |
| Q-MS-7 | What audit logging is available for Data Agent queries and responses? | Regulatory audit requirements for financial services. | **High** | Open |
| Q-MS-8 | Is there a mechanism for Data Agent response validation or confidence scoring? | Manulife needs to know when the agent is uncertain. | **Medium** | Open |
| Q-MS-9 | Can custom guardrails be applied (e.g., block PII in responses, restrict query scope)? | Data privacy requirements. | **High** | Open |
| Q-MS-10 | What is the support model for Data Agent issues in production? | Need to understand escalation path for regulated workloads. | **Medium** | Open |
| Q-MS-11 | Will Direct Lake mode support incremental refresh from OneLake? | Large datasets may require incremental refresh for performance. | **Medium** | Open |
| Q-MS-12 | What is the maximum number of grounding sources per agent? | Architecture planning for multi-domain deployment. | **Medium** | Open |

---

## 5. Open Questions for Manulife

| # | Question | Context | Priority | Status |
|---|----------|---------|----------|--------|
| Q-ML-1 | Which source systems will feed the production OneLake? | Need to assess integration complexity (Guidewire, SAP, investment management systems, etc.). | **Critical** | Open |
| Q-ML-2 | What are the data governance and classification requirements for OneLake? | Sensitivity labels, retention policies, and data residency requirements. | **Critical** | Open |
| Q-ML-3 | Who owns the semantic model measure definitions? | Business ownership is required for trusted KPIs. Need to identify the governance process. | **High** | Open |
| Q-ML-4 | What is the target user group for the Data Agent pilot? | Scope, size, and role of the initial user group. | **High** | Open |
| Q-ML-5 | Are there existing KPI definitions we should align with? | Avoid redefining measures that already have agreed definitions. | **High** | Open |
| Q-ML-6 | What is the French language requirement for Phase 1 vs. Phase 2? | Determines whether French is a blocker for initial deployment. | **High** | Open |
| Q-ML-7 | What data refresh latency is acceptable? | Real-time vs. near-real-time vs. daily batch. Drives architecture decisions. | **Medium** | Open |
| Q-ML-8 | Are there regulatory constraints on using AI/LLM for data analysis in financial services? | OSFI, provincial regulators may have guidance on AI-generated analytics. | **High** | Open |
| Q-ML-9 | What is the approval process for new technology platforms? | Understand the procurement and security review process for Fabric. | **Medium** | Open |
| Q-ML-10 | Which business domains beyond insurance should be included in Phase 2? | Group Benefits, Wealth Management, Asset Management. | **Medium** | Open |
| Q-ML-11 | What is the existing Power BI footprint? | Understand migration/coexistence requirements. | **Medium** | Open |
| Q-ML-12 | Are there data residency requirements (Canada-only)? | Fabric region selection and OneLake configuration. | **High** | Open |

---

## 6. Recommended Risk Mitigations

### 6.1 Build on GA Components First

The highest-risk element of this architecture is the Data Agent (preview). The lowest-risk elements are OneLake, notebooks, pipelines, the semantic model, and Power BI reporting (all GA). The recommended approach is:

1. **Phase 1**: Deploy the data foundation (OneLake, Bronze/Silver/Gold, semantic model, Power BI reports) on GA components. This delivers immediate value regardless of Data Agent timeline.
2. **Phase 2**: Pilot the Data Agent with a controlled user group. Gather feedback and validate accuracy. Maintain the Prompt Flow orchestration layer as a bridge.
3. **Phase 3**: At Data Agent GA, evaluate native capabilities against the orchestration layer. Migrate if native capabilities meet requirements; retain the orchestration layer if gaps remain.

### 6.2 Invest in the Semantic Model

The semantic model is the most durable asset in this architecture. Regardless of how the access layer evolves (Data Agent, APIs, embedded analytics), well-defined measures and relationships will remain the foundation. Recommended actions:

- Assign business ownership for each measure category (claims, premium, investment, customer)
- Document measure definitions, business rules, and calculation logic
- Implement automated testing for measure accuracy (compare DAX output against SQL baseline)
- Establish a change management process for measure modifications

### 6.3 Design for Orchestration Layer Swap-Out

The Prompt Flow orchestration layer is a bridge to native capabilities. Design it for easy replacement:

- Use a clean API contract between the orchestration layer and consumers
- Avoid embedding business logic in the orchestration layer -- keep it in the semantic model and Azure AI Search index
- Document the orchestration layer's responsibilities so they can be mapped to native features at GA
- Use feature flags to toggle between orchestration-mediated and native Data Agent queries

### 6.4 Establish a Feedback and Validation Loop

During the pilot phase, implement:

- **User feedback collection**: A simple mechanism (thumbs up/down + optional comment) for users to rate Data Agent responses
- **Accuracy validation**: Weekly comparison of top-20 most-asked queries against manually verified results
- **Usage analytics**: Track query volume, categories, response times, and failure rates
- **Iteration cycle**: Weekly review of feedback with monthly agent configuration updates (few-shot examples, system prompt tuning)

### 6.5 Engage Microsoft Early on Blockers

For the critical open questions (Q-MS-1 through Q-MS-4), engage the Microsoft account team and Fabric product group proactively:

- Request a roadmap briefing under NDA for Data Agent GA timeline and feature scope
- Request early access to private preview features if available (multi-source grounding, RLS pass-through)
- Establish a direct engineering contact for escalation of preview issues during the pilot
- Participate in Fabric Insiders or Customer Advisory Board programs for influence on the roadmap

### 6.6 Plan for Regulatory Review

Financial services regulators (OSFI, provincial regulators) are increasing scrutiny of AI-generated analytics. Recommended actions:

- Consult Manulife's regulatory affairs team on requirements for AI-assisted data analysis
- Ensure all Data Agent responses include source attribution (which data, which measure, which document)
- Maintain audit logs of agent queries and responses (implement custom logging if native audit is not available)
- Include a disclaimer framework for agent-generated answers used in decision-making

### 6.7 Cost Management Strategy

- Establish capacity consumption baselines during the POC for each workload type
- Model production costs using the Fabric pricing calculator with realistic assumptions (query volume, data volume, refresh frequency)
- Implement capacity alerting at 70% and 90% utilization thresholds
- Use auto-pause for development and test workspaces
- Evaluate reserved capacity pricing for production workloads
- Review consumption monthly and optimize high-cost queries

---

## Summary

The Manulife Fabric POC validates a compelling architecture for unified data analytics. The primary risks center on the Data Agent's preview status and the timeline to GA maturity. The recommended strategy is to build durable value on GA components (OneLake, semantic model, Power BI) while using the preview period to gather user feedback and validate the natural language interaction pattern. This approach ensures Manulife derives value from the investment regardless of the Data Agent's GA timeline.

---

*This document is confidential and intended for internal use by Microsoft and Manulife project stakeholders.*
