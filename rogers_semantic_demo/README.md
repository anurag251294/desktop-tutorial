# Rogers Enterprise Semantic Layer — Finance / ARPU Demo

Companion build for the *Supporting Rogers Data + AI Strategy: The Enterprise Semantic Layer* pitch deck (`Rogers_Semantic_Layer_Branded_v2.pptx`).

Slide 6 is a "live demo" slide: **define ARPU once in the certified model, then prove the same number flows to every surface** — Excel pivot, Power BI report, Copilot data agent. This folder is the working demo for that slide.

Pattern mirrors `rogers_demo` (the Network Anomaly demo): scripts create the workspace, lakehouse, semantic model, data agent, and report end-to-end on the shared Fabric trial capacity.

## Run order

```powershell
# 1. Synthetic finance data (24 months ending Jun 2026)
python build_csvs.py

# 2. Workspace 'Rogers_Semantic_Layer_Demo' + lakehouse 'rogers_finance_lh'
#    Writes stack_finance.json
python create_workspace_and_lakehouse.py

# 3. Upload CSVs to OneLake and load to Delta
python upload_and_load.py
#    If the load LRO stalls (busy capacity), fall back to:
python load_via_notebook.py

# 4. Make sure the SQL endpoint sees the new Delta tables
python fetch_sql_endpoint.py
python check_tables.py   # should list 10 tables

# 5. Build the certified semantic model 'rogers_finance' (Direct Lake, ARPU)
python build_model.py

# 6. Create / enrich the 'Rogers Finance Data Agent'
python create_and_enrich_data_agent.py

# 7. Build the 3-page report 'Rogers_Finance_ARPU_Demo'
python build_report.py
```

All IDs persist to `stack_finance.json`. Re-runs are idempotent (each script
checks for existing items by name and updates instead of recreating).

## What gets built in Fabric

| Item | Name | Notes |
| --- | --- | --- |
| Workspace | `Rogers_Semantic_Layer_Demo` | Capacity `fc2a4dac` (shared trial) |
| Lakehouse | `rogers_finance_lh` | 6 dim + 4 fact Delta tables |
| Semantic Model | `rogers_finance` | Direct Lake. **`[ARPU]` is the hero measure** |
| Data Agent | `Rogers Finance Data Agent` | Grounded on `rogers_finance` |
| Report | `Rogers_Finance_ARPU_Demo` | 3 pages: Exec / Deep-Dive / One Measure Many Surfaces |

## Data model

**Dimensions (6)** — `dim_date` (24 months), `dim_business_unit` (Wireless / Cable & Home / Media / Enterprise), `dim_product` (20), `dim_region` (12 Canadian regions), `dim_customer_segment` (7), `dim_channel` (5).

**Facts (4)** — `fact_revenue_monthly`, `fact_subscribers_monthly`, `fact_churn_monthly`, `fact_costs_monthly`. All at monthly grain, all reconcilable: `[ARPU] = SUM(revenue) / SUM(avg_subscribers)`.

**Embedded anomaly** — Wireless Prepaid (`P004`) ARPU dips Apr → Jun 2026 due to a "promo glitch" that recovers. Lets the presenter ask the agent: *"What happened to Wireless Prepaid ARPU in April?"* on stage.

## Demo script (slide 6, 5 minutes)

1. **Define the measure** — open `rogers_finance` in Power BI, show `[ARPU]` in the measures pane: `DIVIDE([Revenue], [Average Subscribers])`. Point out: defined ONCE, certified.
2. **Query in Excel** — open Excel → Get Data → Power BI Datasets → `rogers_finance` → connected PivotTable. Drag `ARPU` and `dim_business_unit[bu_name]`. Same numbers as on the report.
3. **Query in Power BI** — switch to `Rogers_Finance_ARPU_Demo`, Page 1 "Finance Executive View". The ARPU card matches the Excel pivot to the cent.
4. **Ask an agent** — in Teams, open *Rogers Finance Data Agent*. Ask: *"Give me a Finance briefing for the latest month."* Then: *"What happened to Wireless Prepaid ARPU in April 2026?"* — agent answers from the same model.
5. **Change & re-query** — back in Power BI, edit `[ARPU]` to (say) `DIVIDE([Revenue], [End-of-Period Subscribers])`. Refresh the Excel pivot and re-ask the agent — both update. **Define once, trust everywhere.**

## Files

| File | Purpose |
| --- | --- |
| `build_csvs.py` | Generate synthetic Finance CSVs into `./csv/` |
| `create_workspace_and_lakehouse.py` | Workspace + lakehouse + SQL endpoint capture |
| `upload_and_load.py` | OneLake upload + Delta load (primary path) |
| `load_via_notebook.py` | Spark notebook fallback for busy capacity |
| `fetch_sql_endpoint.py` | Re-capture SQL endpoint + `refreshMetadata` |
| `check_tables.py` | Smoke test - list Delta tables in lakehouse |
| `build_model.py` | TMDL semantic model `rogers_finance` (Direct Lake) |
| `create_and_enrich_data_agent.py` | Data Agent grounded on the model |
| `build_report.py` | 3-page PBIR report |
| `stack_finance.json` | All IDs (created during run) |

## Notes

- Shared with `rogers_demo` (Network) on the same capacity → opening multiple demo workspaces at once may queue Spark sessions.
- Per your `MngEnvMCAP*` tenants memory: SharePoint-disabled tenants block Fabric Data Agent publish; the in-portal chat works.
- Push to GitHub on its own branch (per the `anurag251294/desktop-tutorial` convention) — don't overwrite `main`.
