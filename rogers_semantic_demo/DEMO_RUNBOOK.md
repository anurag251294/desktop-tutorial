# Rogers Enterprise Semantic Layer — Demo Runbook

Use this on the day of the pitch. Backs **slide 6** of `Rogers_Semantic_Layer_Branded_v2.pptx`: *"Define ARPU once in the certified model, then prove the same number flows to every surface."*

**Validated end-to-end against corp Fabric (`microsoft.com` tenant) on 2026-06-24. All numbers in this runbook are live.**

---

## URLs you'll need

| Surface | URL |
| --- | --- |
| Workspace | https://msit.powerbi.com/groups/22aedf4e-5696-43c9-92c8-9133d00ad6bc/list |
| Semantic model (`rogers_finance`) | https://msit.powerbi.com/groups/22aedf4e-5696-43c9-92c8-9133d00ad6bc/datasets/27273c8c-9f89-4850-9ac9-83504ed4646d |
| Report (`Rogers_Finance_ARPU_Demo`) | https://msit.powerbi.com/groups/22aedf4e-5696-43c9-92c8-9133d00ad6bc/reports/a1ba01cf-734e-49e4-9016-619f27f636c3 |
| Data Agent (`Rogers Finance Data Agent`) | https://msit.powerbi.com/groups/22aedf4e-5696-43c9-92c8-9133d00ad6bc/datagents/65e0a738-731b-4a93-b7e8-84641a44932e |

---

## 5-minute pre-demo checklist (do once, day of)

1. **Open all 4 URLs in separate tabs** in Edge profile signed in as `anuragdhuria@microsoft.com`.
2. **Power BI report** — open Page 1. Confirm the ARPU card shows **$166.25** (Jun 2026). If the slicers reset to "All", it's fine.
3. **Excel pivot** — open Excel → *Data → Get Data → From Power Platform → From Power BI*. Find `rogers_finance` in `Rogers_Semantic_Layer_Demo`. Insert a connected PivotTable. Drag `Average Subscribers`, `Revenue`, and `ARPU` into Values; `bu_name` into Rows. Confirm ARPU = **$166.25** at the grand total (matches the report card to the cent). **Save the file** so the connection is warm.
4. **Data Agent** — open the agent URL. The AI instructions are already there. **You need to add the data source manually** (5 clicks):
   - Click `+ Data source` → `Power BI semantic model`
   - Pick workspace `Rogers_Semantic_Layer_Demo` → model `rogers_finance` → **Add**
   - In the per-source settings panel that opens, paste the **data-source instructions** from the bottom of this runbook
   - Click **Publish** (top right)
   - Test: ask *"Give me a Finance briefing for the latest month"* — should return a 3-bullet response
5. **Teams** — open Teams chat with yourself, paste the agent URL once so it's pinned in recent chats.

---

## The numbers you'll speak to (Jun 2026)

| Headline | Value | Where it appears |
| --- | --- | --- |
| **ARPU (certified)** | **$166.25** | Page 1 hero card, Page 3 hero card, Excel pivot total |
| Revenue | $2,656.6M | Page 1 hero card |
| End-of-month Subscribers | 15.97M | Page 1 hero card |
| Net Adds (MoM) | +93,161 | Page 1 hero card |

**Per-LOB ARPU** (Jun 2026):

| BU | Revenue | ARPU | Note for stage |
| --- | --- | --- | --- |
| Wireless | $741.1M | **$58.75** | The number everyone in telecom knows |
| Cable, Internet & Home | $337.9M | $127.55 | Bundle revenue per home |
| Media | $6.5M | $10.26 | Sportsnet streaming subs |
| Enterprise & Business | $1,571.1M | $19,784.92 | Per-contract not per-consumer — get ahead of the "why so high?" question |

**ARPU trend** (last 12 months) — steady upward drift:
$157.28 (Jul 2025) → $159.45 (Nov) → $162.85 (Dec) → $164.77 (Apr 2026) → **$166.25 (Jun 2026)**

---

## The 5-minute demo flow

### 1. Define the measure (30 sec)

Open the **semantic model** tab. Show the model view. Point at the measures pane → **`[ARPU]`**.

> *"Here's where ARPU lives. One definition. `DIVIDE([Revenue], [Average Subscribers])`. Certified, governed, lineage-tracked. This is the only place this metric is defined in the enterprise."*

### 2. Query in Excel (60 sec)

Switch to **Excel**. Pivot already showing ARPU by BU.

> *"Finance lives in Excel. They don't want to learn a new tool. With a Power BI connected pivot, ARPU shows up as a measure they can drag onto rows and columns. The number is **$166.25**, sourced directly from OneLake — no copy, no refresh, no reconciliation meeting."*

### 3. Query in Power BI (60 sec)

Switch to the **Power BI report**, Page 1. Hero card shows **$166.25**.

> *"Same number on a different surface. ARPU at the top is **$166.25** — exactly what Excel just showed. Wireless **$58.75**, Cable & Home **$127.55**. Page 2 lets us drill — by region, by segment, by product."*

Click Page 2. Hover the Wireless Prepaid line in the product table.

### 4. Ask an agent (90 sec) — the killer moment

Switch to **Teams** → Rogers Finance Data Agent.

**Prompt 1:** *"Give me a Finance briefing for the latest month."*
> Expected: headline ARPU $166.25, Wireless dominant by subs, Enterprise dominant by revenue.

**Prompt 2 (the closer):** *"What happened to Wireless Prepaid ARPU in April 2026?"*
> Expected: agent surfaces the dip — Mar **$29.39** → Apr **$24.71** (-16%) → May $26.81 → Jun $29.12. Frame as: *"Notice the agent didn't have access to a separate data source — it used the certified ARPU measure to find this. If we redefined ARPU tomorrow, the agent's answer to this question would update tomorrow."*

### 5. Change & re-query (60 sec) — optional, big moment if pulled off

Open the model in Power BI web. Edit `[ARPU]` → change denominator from `[Average Subscribers]` to `[End-of-Period Subscribers]`. Save.

Switch to Excel → **Refresh** the pivot. Number updates.
Re-ask the agent — number updates.

> *"One definition change. Two surfaces updated. No code changes anywhere. **Define once, trust everywhere.** That is the enterprise semantic layer."*

---

## Failure modes & fallbacks

| If… | Do this |
| --- | --- |
| Excel pivot fails to connect | Refresh the model in Power BI web first, then retry Excel. If still failing, screen-share Page 1 of the report instead — the same number is on the card. |
| Data Agent says "no data source" | You skipped pre-demo step 4. Open the agent URL, add `rogers_finance` as a source, publish. Takes ~30 seconds — apologize and do it live. |
| Agent answer is vague/wrong | Re-ask with the exact measure name in quotes: *"Show me [ARPU - Wireless] by region for Jun 2026."* The certified measure name forces grounding. |
| Slicers stuck on wrong month | Click "Clear all" in the filter pane on the right. The dim_date slicer defaults to "All" — that's fine, page totals are aggregate. |
| Live edit step fails | Skip step 5. Pivot the close to: *"And because the measure is in one place, the change propagates with zero engineering effort. We don't need to live-edit for you to see it."* |

---

## Copy-paste blocks

### AI instructions (already pre-loaded on the agent)

```
You are the Rogers Finance Data Agent. Lead with the headline number, then one
'where' bullet (BU / region / segment) and one 'so what' bullet. Round dollars
for exec readability. Always use the certified [ARPU] measure - do not invent
variants. Flag the Wireless Prepaid ARPU dip in Apr 2026 if relevant.
```

### Data-source instructions (paste in portal during pre-demo step 4)

```
Use this certified Rogers Finance semantic model as the SINGLE SOURCE OF TRUTH
for revenue, subscribers, ARPU, churn, costs, and margin across Wireless,
Cable & Home, Media, and Enterprise & Business. Always use the certified
measures - [Revenue], [ARPU], [ARPU - Wireless], [ARPU - Cable & Home],
[ARPU - Media], [ARPU - Enterprise], [Average Subscribers], [Net Adds (MoM)],
[Churn Rate %], [Gross Margin %]. Never re-derive ARPU; it is always
Revenue / Average Subscribers. Use dim_date[month_start] for time intelligence.
```

### Suggested Copilot prompts (if you want a wider Q&A)

- *Give me a Finance briefing for the latest month.*
- *Compare ARPU across Wireless, Cable, Media, and Enterprise for the last quarter.*
- *Which business unit grew ARPU the most year over year?*
- *Show me ARPU by region for Wireless — which provinces are above the national average?*
- *What happened to Wireless Prepaid ARPU in April 2026?* ⭐
- *Top 5 products by revenue last month, with their ARPU and gross margin.*
- *Trend gross margin % for Cable, Internet & Home over the past 12 months.*

---

## Reconciliation defense (in case someone challenges the numbers on stage)

The same ARPU shows up everywhere because the math is identical. Verified live:

```
BU                          Revenue            Avg Subs     ARPU measure   Rev/AvgSubs   Delta
Wireless                    $741,108,515       12,615,216   $58.75         $58.75        0.0000
Cable, Internet & Home      $337,913,871       2,649,352    $127.55        $127.55       0.0000
Media                       $6,520,807         635,285      $10.26         $10.26        0.0000
Enterprise & Business       $1,571,081,220     79,408       $19,784.92     $19,784.92    0.0000
```

The certified [ARPU] measure and the manual `Revenue / Average Subscribers` calculation reconcile to **zero delta** across every BU. That's the whole point.

---

## Re-run the validation any time

```powershell
cd C:\Users\anuragdhuria\rogers_semantic_demo
& 'C:\Users\anuragdhuria\AppData\Local\Python\bin\python.exe' demo_validate.py
```

Prints all the numbers in this runbook, live from the model.
