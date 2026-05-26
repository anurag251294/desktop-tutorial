# Interac Power BI Demo — Runbook

**Audience:** Interac evaluation team (analytics/BI leadership + HR sponsor)
**Format:** Discovery + capabilities + live demo + licensing + next steps
**Length:** ~60 minutes (15 discovery / 15 capabilities / 20 demo / 10 licensing & next steps)
**Demo environment:** Microsoft Fabric on Canada Central (workspace `InteracHRDemo`)

---

## Why Power BI is the right Q for Interac (one-liner)

> *"Power BI is the only BI tool that runs natively inside the same data platform you'll consolidate on (Fabric), the same productivity layer your people already live in (M365 + Teams), and the same governance layer your compliance team already trusts (Purview). Everyone else bolts on. Microsoft is bolted in."*

That's the through-line. Every page of the demo reinforces one of those three.

---

## Discovery questions (open the meeting with these)

Lead with these in the first 10 minutes. Capture answers — they reshape the demo emphasis on the fly.

### Strategic context
1. **What's the trigger for evaluating BI right now?** Cost consolidation, end-of-contract renewal, a specific failure of the current tool, or a new use case the current tool can't serve?
2. **Are you replacing an incumbent or adding capability?** If replacing — Tableau, Qlik, Cognos, Looker, MicroStrategy? If adding — what gap?
3. **How does this fit your broader data strategy?** Is Fabric / OneLake on the roadmap, or is BI an isolated decision?

### Current state
4. **Where does the analytics data live today?** Synapse, Snowflake, on-prem SQL, Databricks, OneLake?
5. **Who builds reports today — central team, embedded analysts, end users?** What's the ratio of self-service vs. centrally-built?
6. **What's the analyst-to-business-user ratio?** And the report backlog problem?
7. **What is the regulator scrutiny posture?** OSFI E-21 operational resilience, FINTRAC AML reporting, PIPEDA — which is most active right now?

### Success criteria
8. **What does "Power BI is the right answer" look like to you in 90 days?** Specifically — a pilot delivered? Cost savings? Self-service adoption? A regulator-ready report?
9. **What are the must-have capabilities — and what are the killers?** (e.g., "if it can't do X, we're out")
10. **Who needs to be convinced beyond this room?** CISO, procurement, the existing BI team, business sponsors?

### HR scenario (since it's the demo)
11. **Who owns workforce analytics today inside Interac?** HR Business Partners? A People Analytics team? Finance?
12. **What HR question are you not able to answer today that frustrates the CHRO or CEO most?**
13. **What systems is the HR data spread across?** Workday, SuccessFactors, ADP, custom? Refresh cadence?

### Killer follow-up
> *"If we showed you the HR scenario delivered in a Fabric + Power BI environment in production, would Interac realistically want the same architecture for finance, risk, customer, and operations analytics — or are those separate decisions?"*

(This forces them to admit if Power BI is being evaluated **for the tool** or **for the platform**. Most enterprises think they're doing the former; the right answer is the latter.)

---

## Capabilities — talk track (15 min)

Don't tour features. Land 4 differentiators that map to Interac's reality.

### 1. **Native to Microsoft Fabric & OneLake** — "one copy of data"

The pitch:
> *"Today, when an analyst wants to build a report, the data gets copied — from your warehouse to a BI cube, then refreshed nightly, then maybe again to a Tableau extract. Three copies, three refresh windows, three places it can go stale or get exfiltrated. Power BI on Fabric uses **Direct Lake mode** — the report reads Delta tables in OneLake directly, in-memory speed, no copy, no extract refresh. One source of truth, governed once."*

Why Interac cares: payments-network data has strict residency (Canada) and lineage requirements. Fewer copies = smaller compliance surface.

### 2. **Copilot in Power BI** — "every business user is now an analyst"

The pitch:
> *"Every BI tool now claims AI. Most ship a chatbot that hits the report metadata. Microsoft is the only vendor whose AI is built on the same model your CIO is already buying through M365 Copilot — so the security boundary, the data residency, the prompt logging, all of it is the agreement you've already signed."*

Demo it: in the report, click Copilot → *"Summarize the attrition story for last 12 months"* → live answer with citations. Then *"Create a measure for YoY headcount change"* → DAX written for you.

### 3. **M365-native distribution** — "report lives where people work"

The pitch:
> *"A report nobody opens has zero value. Power BI lives inside Teams, Excel, Outlook, PowerPoint — so the report doesn't compete for attention, it shows up in the chat thread, the email, the deck. Tableau and Qlik live in browser tabs."*

Show: Power BI tab inside a Teams channel. Pinned report in an Outlook email. PPT export with live data refresh on open.

### 4. **Purview governance** — "label once, enforced everywhere"

The pitch:
> *"Your HR data is Confidential. Your AML data is Restricted. With Microsoft Purview, the sensitivity label travels from the lakehouse → semantic model → report → PowerPoint export → email attachment. DLP policy stops a user from emailing a Restricted report outside Interac, or pasting it into a public Teams channel. That governance chain doesn't exist with Tableau or Qlik — they stop at the report border."*

Show: applying `Confidential \ HR` to the semantic model and watching it propagate to a PPT export.

---

## Live demo flow (20 min)

### Setup before they walk in (do all of this in advance)

1. **Resume capacity:** `az resource invoke-action --action resume -g rg-fabric-demo -n fabdemo85829 --resource-type Microsoft.Fabric/capacities`
2. **Verify lakehouse loads:** open `InteracHRDemo` workspace → `InteracHR_Lakehouse` → SQL endpoint → `SELECT TOP 5 * FROM dim_employee`
3. **Open browser tabs in this order:**
   - Tab 1: OneLake Explorer view of the lakehouse
   - Tab 2: The semantic model (Model view, so the star schema is visible)
   - Tab 3: The published report on Page 1 (Exec Overview)
   - Tab 4: Teams channel with the report pinned
4. **Log in as the HR Business Partner persona** for RLS demo
5. **Have a second window** with the People Manager view ready

### Flow

**(0:00 — 1:30) The architecture in 90 seconds**

> *"Before we go to the report, I want to show you what's behind it — because that's the differentiator. This is OneLake — Microsoft's data lake. Every Delta table here is the single copy of HR data for this demo. The report you'll see in a moment reads directly from this lake, in-memory, no refresh."*

→ Click into Files/csv/ to show the raw uploads, then Tables/ to show the Delta tables.

**(1:30 — 3:00) Star schema in the semantic model**

> *"This is the semantic model. Six dimensions, five facts, classic Kimball. The point isn't the model — it's that **business users will never see this**. Analysts maintain it once. Everyone else asks questions in plain English."*

**(3:00 — 8:00) Page 1 — Exec Overview**

Open the published report. Land four KPI numbers:
- **898 active employees** ("our Interac analog has 900 — comparable scale")
- **14.2% LTM attrition** ("blended — typical for fintech")
- **23% regrettable rate** ("but watch this number when we drill")
- **80 open reqs** ("recruiting throughput")

→ Filter the line chart to last 24 months. Point out the **Q4-2025 spike**. *"Something happened in October '25 — let's find it."*

**(8:00 — 12:00) Page 3 — Attrition Deep Dive**

Click the Q4 spike. Cross-filter highlights **Payments Platform** in the treemap.

→ Open the **Decomposition Tree** visual on `[Regrettable Attrition LTM]`. Split by department → role_level → location. Land on: **Senior IC engineers (IC4-IC5) in Toronto, Payments Platform = the largest segment of regrettable attrition.**

→ Open the **Key Influencers** visual. Show: "When `role_level` is `IC4`, the likelihood of regrettable attrition increases by 2.4x."

> *"This is the question your CHRO can't answer today. Who is leaving, why, and what's the predictor? Power BI's Key Influencers ran a regression behind the scenes — no data scientist required."*

**(12:00 — 14:30) Page 6 — Compliance & Risk**

> *"Now imagine an OSFI examiner asks: how many of your employees are overdue on their Conflict of Interest attestation by more than 90 days?"*

→ Show the **7** card. Click it to drill to the employee list.

> *"This question isn't theoretical. OSFI E-21 has explicit expectations around personnel conduct attestations. You need this view in 5 seconds, not 5 days."*

**(14:30 — 17:00) Copilot live**

→ Click Copilot. Type:
1. *"Which manager has the highest regrettable attrition this year?"*
2. *"Build me a page for our compliance officer."*
3. *"Create a measure for time-to-fill by role family."*

Acknowledge: *"In production on F64+ capacity, this Copilot also writes DAX, builds visuals, and summarizes report pages. Today we're on a demo SKU."*

**(17:00 — 19:00) Governance & RLS**

→ Switch to **View as → People Manager** role. The report filters automatically to one person's reports. *"This is enforced at the semantic model layer — every downstream consumer, every Excel export, every Teams pin, inherits this filter. No tool sees the unfiltered data unless they have permission."*

→ Show **Sensitivity label `Confidential \ HR`** on the semantic model. *"Now I export this to PPT — watch."* → Open the export → label is on every slide → if I try to email it externally, DLP blocks it.

**(19:00 — 20:00) Teams handoff**

→ Switch to Teams tab. The same report is pinned in the HR Leadership channel. *"Where do your business stakeholders live? Email and Teams. The report shows up where the conversation is."*

---

## Licensing & deployment (10 min)

Have this slide ready. Don't over-explain — Interac's procurement will go through this in detail in a separate session.

| SKU | Price (USD/user/mo) | Who it's for | Notes |
|---|---|---|---|
| **Power BI Pro** | $14 | Individual report authors & viewers | Min viable; viewers also need Pro unless on Premium capacity |
| **Power BI Premium Per User (PPU)** | $24 | Authors who need Premium features without a capacity | Includes paginated reports, AI, deployment pipelines |
| **Fabric F2 capacity** | ~$262/mo (CAD) | Smallest Fabric SKU — what we demo on | Viewers don't need a per-user license to consume reports stored on capacity |
| **Fabric F64 capacity** | ~$8,400/mo (CAD) | Production unit for mid-size enterprises | Unlocks Copilot in Power BI, autoscale, free viewer licenses |
| **Microsoft 365 E5** | (bundle) | Most likely the right SKU for Interac | Includes Power BI Pro for every user + Purview Information Protection + Defender for Cloud Apps for DLP |

### Deployment options

| Mode | When | Trade-off |
|---|---|---|
| **Power BI Service (multi-tenant cloud)** | Default — what we just demo'd | Microsoft-hosted, Canada Central region |
| **Fabric capacity (dedicated)** | When you want predictable performance + Copilot + DirectLake | One bill, no per-user math for consumers |
| **Power BI Embedded** | Customer-facing reports inside Interac's apps | Pay-as-you-go, A SKUs |
| **Power BI Report Server (on-prem)** | Only if hard data-residency-bound to a specific datacenter | Trade-off: no Copilot, no Fabric integration — last resort |

### Roadmap items to flag to Interac

- **Copilot in Power BI** — GA on F64+; "Copilot Studio" agents over data are landing rapidly
- **Direct Lake on OneLake shortcuts** — read directly from Snowflake / S3 / ADLS without copy (preview → GA path 2026)
- **Translytical Task Flows** — write-back from Power BI to Fabric for hybrid analytical/operational workflows
- **Real-time Intelligence on Fabric** — for fraud / payments network monitoring; relevant to Interac's core business

---

## Q&A cheat sheet (anticipated)

**Q: "We're a Tableau shop. What's the migration story?"**
A: Microsoft FastTrack + Microsoft Partner programs offer paid migration accelerators. The semantic model is the migration artifact — once that's right, reports are 60-70% auto-translatable. Realistic target: 60-90 day pilot per business unit.

**Q: "Our data is in Snowflake. Do we have to move it?"**
A: No. Fabric has a **OneLake shortcut to Snowflake** — Power BI reads it as if it were native. No movement, no duplication. Or you stage curated layers in Fabric and shortcut from there.

**Q: "What about cost?"**
A: For Interac scale, the F64 + M365 E5 combination is typically lower TCO than Tableau Server + Tableau Cloud + a separate AI platform + a separate DLP tool. We'll model it side-by-side in a follow-up.

**Q: "We're worried about data residency."**
A: Fabric capacity is provisioned per-region. Canada Central is GA. The capacity in this demo is Canada Central. Data never leaves the region by default — including Copilot inference, which routes through the regional endpoint.

**Q: "We have OSFI examination this year. Can you support that?"**
A: Three artifacts you'd want: (1) Purview Data Map = lineage of every data movement; (2) Microsoft Compliance Manager = pre-built OSFI E-21 control templates; (3) the compliance page in this very demo as the operational reporting layer. Want a walkthrough with our OSFI-specialized FSI architect?

**Q: "How is this different from Microsoft Fabric? Aren't they the same thing?"**
A: Power BI is the consumption / reporting layer. Fabric is the platform — storage (OneLake), compute (Spark, SQL, KQL), engineering (Data Factory), data science, real-time. Power BI **is** the BI experience of Fabric. You can buy Power BI standalone; you cannot fully exploit Fabric without it.

**Q: "What if Copilot returns wrong answers?"**
A: Copilot in Power BI is grounded — it only uses your semantic model and DAX. It doesn't make up data. Every answer is traceable to the visual / measure / table it pulled from. We can show that trace live.

**Q: "Can you run this in our tenant for a pilot?"**
A: Yes. Suggested 60-day path: workspace in your tenant, OneLake on Canada Central, your real HR extract (with Microsoft signing the appropriate confidentiality terms), 3 report pages + one Copilot scenario. We can scope at the end of this session.

---

## Recommended next steps to propose

1. **Half-day technical workshop** with Interac's BI team + Fabric architect (3 weeks out)
2. **HR scenario POC in Interac's tenant** using a real subset of HR data (60 days, jointly scoped)
3. **Parallel licensing/commercial conversation** between procurement and Microsoft account team
4. **Reference call** with a comparable Canadian FI (we have several Fabric customer references — TD, Scotia, CIBC have public stories)

End the meeting with: *"What would have to be true for Interac to move from evaluation to pilot in the next 60 days?"*

---

## Post-demo

- **Pause the capacity** to stop the meter:
  ```powershell
  az resource invoke-action --action suspend -g rg-fabric-demo -n fabdemo85829 --resource-type Microsoft.Fabric/capacities
  ```
- Send a 1-page follow-up email within 24h with: discovery answers captured, demo recording link (if any), proposed next steps, named owners on both sides.
