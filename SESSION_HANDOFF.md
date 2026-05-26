# Session handoff — Interac + Canadian Tire Copilot demos

Resume point for switching machines. **Today: 2026-05-26.** **Demo: Friday 2026-05-29 10:00 AM (CTC).**

---

## Quick resume on a new machine

```powershell
# 1. Prereqs
winget install --id Microsoft.AzureCLI            # if not installed
winget install --id Python.Python.3.14            # or 3.12+
py -m pip install pandas openpyxl python-pptx requests

# 2. Auth - must be Anurag's MSFT identity
az login --tenant microsoft.com

# 3. Clone the repo
mkdir C:\Users\anuragdhuria\
git clone https://github.com/anurag251294/desktop-tutorial.git C:\Users\anuragdhuria\interac_demo
cd C:\Users\anuragdhuria\interac_demo
git checkout interac-demo

# 4. (CTC demo) re-instantiate the local ctc_demo folder if you want it side-by-side
cp -r canadian_tire_demo C:\Users\anuragdhuria\ctc_demo
# Or just work directly in canadian_tire_demo/

# 5. Source data lives only in OneDrive - not in the repo. Sync OneDrive on the new
#    machine before running build_csvs.py / inspect_excel.py for CTC.
#    Path: C:\Users\anuragdhuria\OneDrive - Microsoft\Desktop\OneDrive_2026-05-25\Demo Data\
```

To validate everything works without rebuilding, just run:

```powershell
cd canadian_tire_demo
py verify_model.py            # confirms CTC model returns data
py verify_question_set.py     # walks the 8 customer prompts
```

---

## Live assets (all in the corp `microsoft.com` Fabric tenant — MSIT cluster)

### Canadian Tire (CTC) — demo Friday 2026-05-29 10am

| Asset | ID | Open |
|-------|----|------|
| Workspace `CanadianTire_Demo` | `9e29a8fd-9462-4c18-b691-f77a631e89ea` | [link](https://msit.powerbi.com/groups/9e29a8fd-9462-4c18-b691-f77a631e89ea/list) |
| Lakehouse `ctc_lh` | `9fa33576-531f-43ea-82ea-9e376c8259b1` | — |
| SQL endpoint | `de9db835-7322-4e04-8ae3-c070451d14be` | — |
| Semantic model `ctc_merch` (Direct Lake on OneLake) | `729c30bc-100a-465a-8af6-4200bd6ff70c` | [link](https://msit.powerbi.com/groups/9e29a8fd-9462-4c18-b691-f77a631e89ea/datasets/729c30bc-100a-465a-8af6-4200bd6ff70c/details) |
| Report `CTC_Merch_Copilot_Demo` (3 pages) | `b41bcf36-87e4-4834-818c-c6b266f3d5bb` | [link](https://msit.powerbi.com/groups/9e29a8fd-9462-4c18-b691-f77a631e89ea/reports/b41bcf36-87e4-4834-818c-c6b266f3d5bb) |
| Fabric Data Agent `CTC Merch Data Agent` | `70dba6b9-5a14-4784-8ee1-1c463e58af59` | [link](https://msit.powerbi.com/groups/9e29a8fd-9462-4c18-b691-f77a631e89ea/dataagents/70dba6b9-5a14-4784-8ee1-1c463e58af59) |
| Trial capacity | `fc2a4dac-2edb-4f33-9209-b0dac6a67c5d` (expires ~60 days from activation) | — |

### Interac

| Asset | ID | Open |
|-------|----|------|
| Workspace (corp HR demo) | `de6a7e47-474b-4354-87e7-26b8d741f015` | [link](https://msit.powerbi.com/groups/de6a7e47-474b-4354-87e7-26b8d741f015/list) |
| Semantic model `hr_demo` | `89782e0a-276b-4b86-a2d0-e8238d3c8791` | [link](https://msit.powerbi.com/groups/de6a7e47-474b-4354-87e7-26b8d741f015/datasets/89782e0a-276b-4b86-a2d0-e8238d3c8791/details) |
| Report `HR_demo_report` (portal-created + Copilot Showcase page injected) | `d28c79f7-5088-4d95-a3c6-c4a0dae093d9` | [link](https://msit.powerbi.com/groups/de6a7e47-474b-4354-87e7-26b8d741f015/reports/d28c79f7-5088-4d95-a3c6-c4a0dae093d9) |
| Fabric Data Agent `Interac HR Data Agent` | `5d87b475-310c-4b22-ba4c-592c73207dde` | [link](https://msit.powerbi.com/groups/de6a7e47-474b-4354-87e7-26b8d741f015/dataagents/5d87b475-310c-4b22-ba4c-592c73207dde) |

Stack files with all this captured:
- `canadian_tire_demo/stack_ctc.json`
- `canadian_tire_demo/data_agents.json` (both agents)

---

## Repo layout

```
interac_demo/                 (repo root, branch: interac-demo)
├── SESSION_HANDOFF.md        (this file)
├── Interac_PBI_Fabric_Demo.pptx
├── build_interac_pptx.py
├── enrich_hr_report.py       (adds Copilot Showcase page to HR_demo_report)
├── remove_rls_roles.py
├── copilot_studio_agent_interac.md
├── add_rls_roles.py
├── build_semantic_model.py
├── ... (older Interac scripts)
└── canadian_tire_demo/
    ├── README.md
    ├── CTC_Merch_Copilot_Demo.pptx
    ├── inspect_excel.py
    ├── extract_data_dictionary.py
    ├── data_dict.json
    ├── create_workspace_and_lakehouse.py
    ├── build_csvs.py
    ├── upload_and_load.py
    ├── fetch_sql_endpoint.py
    ├── build_model.py
    ├── add_kpis_to_model.py    (KPI traffic-light blocks for ctc_merch)
    ├── refresh_model.py
    ├── verify_model.py
    ├── verify_question_set.py
    ├── build_report.py         (3-page report + narrative + Copilot callouts)
    ├── create_data_agent.py
    ├── configure_data_agents.py
    ├── data_agents.json
    ├── stack_ctc.json          (all CTC IDs)
    ├── copilot_studio_agent_ctc.md
    ├── dump_template_tmdl.py
    └── csv/                    (synthetic-blended CSVs)
        ├── dim_date.csv
        ├── dim_sku.csv
        ├── dim_vendor.csv
        ├── dim_season.csv
        ├── fact_sku_performance.csv
        ├── fact_in_season.csv
        └── fact_connected_inventory.csv
```

---

## What state we're in (as of last session, 2026-05-26)

**CTC report** — 3 pages deployed via `build_report.py`. Each page has:
- Traffic-light KPI visuals (using new KPI TMDL blocks on ctc_merch)
- Smart Narrative auto-insights
- "Try these Copilot prompts" callout
- "Continue in Teams via CTC Merch Data Agent" cross-surface hint
- Slicers for Category, Vendor, Fineline_Name, New_SKU_Flag

**Interac HR_demo_report** — original Quick Create page untouched + new **Copilot Showcase** page injected via `enrich_hr_report.py`. New page has 4 traffic-light KPIs, Smart Narrative, Copilot callout, two bar charts.

**Data Agents** — both created and bound to their semantic models with example prompts + AI instructions via API. May need a single "Publish" click in the portal to flip from draft to live (open the agent and look for Publish button).

**Slides** — both PPTXs generated:
- `canadian_tire_demo/CTC_Merch_Copilot_Demo.pptx` (11 slides)
- `Interac_PBI_Fabric_Demo.pptx` (13 slides)

**Copilot Studio agent specs** — markdown specs ready to paste in copilotstudio.microsoft.com (knowledge sources, topics, system instructions, governance posture).

---

## Open items / next steps before Friday

1. **Verify both reports render** — open both URLs (above). If the CTC report hangs on "Loading your report" (same hang we hit with API-built reports on Interac earlier), fallback is: open CTC report in portal → save-as new name → re-bind to ctc_merch.
2. **Publish each Data Agent in portal** — open each agent URL, look for "Publish" so it's queryable from Teams / M365 Copilot. (API-set draft config doesn't auto-publish.)
3. **Test Copilot in PBI against ctc_merch** — open the CTC report, click Copilot, walk through the 8 customer prompts seeded in `Copilot/examplePrompts.json`. If any prompt misfires, the fix is in `build_model.py` (measure descriptions / synonyms), then re-run `build_model.py` + `refresh_model.py`.
4. **Refresh OneDrive sync** on new machine to get the source Excel files. Build pipeline only needs them for `inspect_excel.py` / `build_csvs.py`, which you don't need to re-run unless you tweak the source data.
5. **Capacity** — corp Fabric trial expires ~60 days from `2026-05-25`. Monitor — once you're past Friday's demo, decide whether to pause + redo on a paid capacity.
6. **Backup deck for governance** — sketch is in slide 8 of the CTC PPTX (PII handling, data residency, conversation retention, Purview DLP). Expand only if needed.

---

## Demo headline numbers (validated via DAX in `verify_question_set.py`)

| Metric | Value |
|--------|-------|
| Total POS TY | $49.2M |
| POS YoY | +27.9% |
| EGM % TY | 42.3% |
| Avg Lost Sales % | 4.06% |
| Avg Vendor Fill Rate % | 89.0% |
| Air Fryers POS YoY | +88.7% (strongest fineline growth) |
| NK Dual Zone Air Fryer 8L | Lost sales 13.7%, fill rate 72.7% — supply-constrained growth story |
| SKUs WoS>18 with low lost sales | 9 (markdown candidates) |
| SKUs with lost sales >5% AND fill rate <85% | 13 (supply risk) |
| Canvas Outdoor vendor | $7.4M, +2.9% YoY, 39.9% EGM, 89.1% fill |

---

## Auth notes

- All API calls go through `az account get-access-token --resource ...`. Two scopes are used:
  - `https://api.fabric.microsoft.com` — Fabric Items API (workspaces, lakehouses, semantic models, reports, data agents)
  - `https://analysis.windows.net/powerbi/api` — Power BI / executeQueries DAX
  - `https://storage.azure.com` — OneLake DFS for CSV upload
- On Windows the AZ binary path is hardcoded: `C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd`. Update if your install path differs.
- All workspaces are in the corp tenant `microsoft.com`. RLS was REMOVED from `hr_demo` earlier — re-apply via `add_rls_roles.py` before publishing to managers (the People Manager and Compliance Officer roles).

---

## Key past learnings (don't redo these)

- **API-built PBIR reports often hang on "Loading your report"** — the working pattern is *portal-created shell + API enrichment via updateDefinition*. The HR_demo_report was portal-created and works; the CTC report was built via API using its exact schema versions and *might* render — if not, do the portal-shell route.
- **Direct Lake first-query error** — "table is not refreshed, fallback to DirectQuery is disabled" → fix is to call `POST /datasets/{id}/refreshes` after creating the model. See `refresh_model.py`.
- **Direct Lake percent columns** — if source data stores percent as raw points (e.g. 43.5 = 43.5%), use formatString `"0.0\"%\""` on the column. When the measure averages and divides by 100, use `"0.0%"` (decimal).
- **DAX cross-table filter measures** — to count dim rows by a fact predicate, iterate over `VALUES(dim_sku[SKU])` with `CALCULATE(MAX(fact_x[col]))` inside FILTER — don't iterate over `VALUES(fact_x[SKU])`, the filter direction doesn't propagate back to dim.
- **TMDL KPI indentation** — `statusExpression =` is at 3 tabs; the body lines below it are at 4 tabs.
- **MCAPS-managed tenants (`MngEnvMCAP*`)** block Fabric Data Agent publish through external paths. Both demos use the **corp** tenant — agent publish works there.
- **Files under `OneDrive - Microsoft\`** are often co-authored — never overwrite, always side-by-side.

---

## Latest commits on `interac-demo`

```
892581d Improve both demo reports - narrative KPIs, Smart Narrative everywhere, Copilot prompt callouts
6d2603e Add Canadian Tire Merch Copilot demo + Interac PPTX + Data Agents
3c29ee3 Build Fabric Notebook KPI dashboard (bypasses PBIR)
78e08a5 Build KPI dashboard via API with 8 proper KPI visuals
19bf0f7 Add 8 real KPI definitions to hr_demo via TMDL
```
