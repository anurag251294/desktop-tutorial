# Manulife Japan Fabric POC — Demo Runbook

Step-by-step workshop flow. Times assume an audience of 6-10 with light interaction. Total demo ~45 minutes.

## Pre-demo (15 min before start)

1. **Resume the capacity** (no-op if already active):
   ```
   az resource invoke-action --resource-group rg-fabric-demo --name fabdemo85829 --resource-type Microsoft.Fabric/capacities --action resume
   ```
2. **Warm caches** (run `scripts/mlj/mlj_post_nb.py` or these two REST calls):
   - `POST /workspaces/{ws}/sqlEndpoints/{id}/refreshMetadata?preview=true`
   - `POST /datasets/{id}/refreshes` body `{"type":"Full"}`
3. **Open these tabs in advance** (browser):
   - Workspace: https://app.fabric.microsoft.com/groups/ca416fea-52c1-4e06-82c6-509440817a11
   - Lakehouse: https://app.fabric.microsoft.com/groups/ca416fea-52c1-4e06-82c6-509440817a11/lakehouses/4b1fe0a9-e407-4ac5-b776-c8523533bb67
   - Semantic model: https://app.fabric.microsoft.com/groups/ca416fea-52c1-4e06-82c6-509440817a11/datasets/81d455be-f812-4021-b79a-1f37c6dde90e
4. **Verify the Data Agent exists** — if not, follow the "Data Agent creation" section below first.

---

## Workshop flow (~45 min)

### 1. Opening: where MLJ is today (5 min) — slides 1-4

Show slides 1 (cover), 3 (current architecture), 4 (why Fabric one-pager). Don't dwell — set context, move on.

### 2. The side-by-side comparison (8 min) — slides 5-7

This is the centrepiece. Walk through:
- Slide 5: the table — emphasise the **Governance** row (Unity Catalog refresh → OneLake+Purview)
- Slide 6: today's diagram with friction points highlighted
- Slide 7: target diagram — point out *same domains, one platform*

**Talking point:** "Same domain model. One platform. The 2026 governance work moves under the same umbrella as the AI self-service work."

### 3. OneLake foundation deep-dive (5 min) — slide 8

Slide 8 sells OneLake. Then **switch to the live workspace**:
- Open the Lakehouse `MLJ_Lakehouse`
- Show the table list in the left pane — point out bronze_/silver_/gold_/mart_ tables
- Click `gold_dim_customer` → show JP prefectures in the Data preview
- Click `document_chunks` → show the 8 JP policy docs already chunked for RAG

**Talking point:** "One copy. Same Delta tables that Power BI reads, that the Data Agent reads, that Spark notebooks read. No copy/refresh dance."

### 4. Live SQL exploration (3 min)

In the Lakehouse, click **SQL endpoint** (top right). Run these queries — copy-paste:

```sql
-- Q1: top 5 prefectures by customer count
SELECT province, COUNT(*) AS customers
FROM gold_dim_customer
GROUP BY province
ORDER BY customers DESC
LIMIT 5;

-- Q2: AML alerts by reason
SELECT alert_reason, status, COUNT(*) AS alerts
FROM mart_aml_alerts
GROUP BY alert_reason, status;

-- Q3: IFRS 17 premium by cohort and product line
SELECT cohort_year, policy_type,
       SUM(total_premium_jpy) AS premium_jpy,
       COUNT(DISTINCT policy_count) AS policies
FROM mart_ifrs17_premium
WHERE cohort_year >= 2023
GROUP BY cohort_year, policy_type
ORDER BY cohort_year, policy_type;

-- Q4: customer 360 — top 5 by LTV proxy
SELECT customer_id, first_name, last_name, province,
       policy_count, claim_count, total_aum_jpy, ltv_proxy_jpy
FROM mart_cdp_customer_360
ORDER BY ltv_proxy_jpy DESC
LIMIT 5;
```

**Talking point:** "These five MLJ-specific marts — Griffin, AML, IFRS 17, CDP, VOICE — sit on the same OneLake the bronze tables sit on. Same governance. No copies."

### 5. Semantic model + Direct Lake (5 min)

Open the semantic model `ManulifeJapanPOC_SemanticModel`. Click **Model view** to show the star schema (4 facts + 6 dims + dim_date with active relationships).

Click **Explore data** (top right). Build a quick visual:
- Drag `dim_customer[province]` to rows
- Drag `[Total Premium Revenue]` to values
- Drag `[Total AUM]` to values

Show that this runs in <2 seconds without any refresh. Then change the slicer to filter `dim_advisor[region] = "Kanto"` and watch it update instantly.

**Talking point:** "Direct Lake. No data was imported. The semantic model is a thin layer over the Delta tables. Same data Power BI sees, the Data Agent sees, the API sees."

### 6. AI use cases — slides 13-19 (10 min)

Walk through the 5 theme slides briefly (don't read every card — call out 1-2 per slide). End on slide 19 (top 3 to showcase live).

### 7. Live Data Agent demo (8 min)

Open the Data Agent `da_manulife_japan_poc` (or create it now — see below if not done).

Ask these questions in order:

1. **"What is our total premium revenue?"**
   - Expected: ¥17,462,299 JPY (or similar). Shows the agent grounds on the semantic model.

2. **"Top 5 advisors by AUM"**
   - Expected: table with 5 JP names (Maeda, Goto, Nakamura, etc.) + JPY values.

3. **"Premium revenue by Japanese prefecture, top 5"**
   - Expected: Tokyo, Aichi, Hiroshima, etc. Shows JP localisation.

4. **"What does the policy say about the cancer waiting period?"** ← THE WIN MOMENT
   - Expected: 90-day waiting period, cited from `policy_terms_cancer_insurance_jp.md`. This is the claims clerk Copilot story made real.

5. **"What's the IFRS 17 premium by cohort year, 2024 onwards?"**
   - Expected: aggregated table by cohort year + product line. Demonstrates the curated mart pattern.

6. **"How many open AML alerts do we have?"**
   - Expected: row count from `mart_aml_alerts` where status='Open'.

7. (If feeling lucky) **"東京の顧客の総保険料は？"** *(Total premium for Tokyo customers in Japanese)*
   - Expected: yen amount, response in Japanese.

### 8. Migration phasing + next steps (5 min) — slides 20-21

Show the phasing diagram. Emphasise Phase 1 = single domain proof (recommend Customer). Wrap with "questions?"

---

## Data Agent creation (if not already done)

**REST creation is blocked by tenant cross-geo settings** — must create in the Fabric UI. ~10 minutes.

1. Open the workspace: https://app.fabric.microsoft.com/groups/ca416fea-52c1-4e06-82c6-509440817a11
2. Click **+ New item** → search **"Data Agent"** (it's in preview, may be under AI Skills)
3. Name: `da_manulife_japan_poc`
4. Description: `Manulife Japan POC Data Agent - natural-language analytics over the MLJ insurance, investment, and document corpus (JPY).`
5. Click **Create**.

**Add data sources:**

a) Click **+ Add data source** → **Semantic model** → pick `ManulifeJapanPOC_SemanticModel` → **Add**.

b) Click **+ Add data source** → **Lakehouse** → pick `MLJ_Lakehouse` → **Add**. In the table picker, check:
- All `gold_*` tables
- `document_chunks`
- `mart_aml_alerts`, `mart_ifrs17_premium`, `mart_cdp_customer_360`, `mart_voice_complaints`
- `griffin_dq_summary`
- (Uncheck `validation_results` and any `bronze_*` / `silver_*` to keep the scope clean.)

**Paste AI instructions:**

Open `agent-config/mlj-data-agent-instructions.md`. Copy the full block under "Paste this into the agent's AI instructions field" — paste into the **AI instructions** text area in the agent settings panel.

**Per-source instructions:**
- On the **Lakehouse data source**, paste the "Lakehouse data source instructions" block.
- On the **Semantic model data source**, paste the "Semantic model data source instructions" block.

**Save + Publish.** Click **Save** → **Publish** (top right).

The agent is now live. Test with the 7 demo questions above.

---

## Recovery playbook

**If a query is slow on first try after resume** — the SQL endpoint or semantic model is still warming. Wait 10 seconds and re-run.

**If the Data Agent gives a vague answer** — it's grounding correctly but may need a sharper prompt. Add specifics: "using the semantic model", "from mart_aml_alerts", etc.

**If a measure returns the wrong number** — flag it with the audience as demo data (loss ratio is unrealistically high because claims and premiums were generated independently).

---

## Post-demo

Pause the capacity:
```
az resource invoke-action --resource-group rg-fabric-demo --name fabdemo85829 --resource-type Microsoft.Fabric/capacities --action suspend
```
