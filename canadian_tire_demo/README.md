# Canadian Tire — Copilot in Power BI demo

Merch-team-focused Copilot in Power BI demo for Canadian Tire, scheduled for **Friday 2026-05-29 10:00 AM**.

## Stack (corp Fabric trial)

| Asset | ID |
|-------|----|
| Workspace `CanadianTire_Demo` | `9e29a8fd-9462-4c18-b691-f77a631e89ea` |
| Lakehouse `ctc_lh` | `9fa33576-531f-43ea-82ea-9e376c8259b1` |
| Semantic model `ctc_merch` (Direct Lake on OneLake) | `729c30bc-100a-465a-8af6-4200bd6ff70c` |
| Report `CTC_Merch_Copilot_Demo` | `b41bcf36-87e4-4834-818c-c6b266f3d5bb` |
| Data Agent `CTC Merch Data Agent` | `70dba6b9-5a14-4784-8ee1-1c463e58af59` |
| Trial capacity | `fc2a4dac-2edb-4f33-9209-b0dac6a67c5d` |

## Build order

1. `inspect_excel.py` — sanity-check source schemas
2. `extract_data_dictionary.py` — pull Data Dictionary sheets → `data_dict.json` for Copilot descriptions
3. `create_workspace_and_lakehouse.py` — provisions workspace + lakehouse
4. `build_csvs.py` — Excel → flat CSVs (dim_sku, dim_vendor, dim_season, dim_date, 3 fact tables)
5. `upload_and_load.py` — DFS upload to OneLake `Files/csv/` then `/tables/{name}/load` → Delta
6. `fetch_sql_endpoint.py` — grab SQL endpoint + `refreshMetadata` so Delta is queryable
7. `build_model.py` — build the Direct Lake semantic model with rich measure descriptions + Copilot examplePrompts
8. `refresh_model.py` — frame Direct Lake partitions
9. `verify_model.py` / `verify_question_set.py` — DAX check against all 8 customer prompts
10. `build_report.py` — pre-built Merch report (KPI cards + bar/column + table + slicer)
11. `create_data_agent.py` + `configure_data_agents.py` — provision the Fabric Data Agent and bind it
12. `build_ctc_pptx.py` — generates `CTC_Merch_Copilot_Demo.pptx` deck

## Source data

The 3 customer-prepared Excel files + Read Me + Sample question set live in:
`C:\Users\anuragdhuria\OneDrive - Microsoft\Desktop\OneDrive_2026-05-25\Demo Data\`

These were prepared by Bhargavi Ravishankar (CTC) for this session.

## Demo flow (consumer-experience focus)

The invite explicitly narrows scope to **consumer experience**, not build/modeling. Therefore on the day:
1. Open the polished report — show KPI cards, bar/column, table
2. Press Copilot → "summarize this page" (executive narrative)
3. Run the 8 sample prompts from the customer's question set
4. Demonstrate Smart Narrative and Find Insights
5. Show Data Agent in Teams (consumption outside the report)
6. Governance backup slides only if asked (slides 8 of the PPTX)

## Headline findings the demo can lean on

- Total POS TY = $49.2M (+27.9% YoY), EGM % = 42.3%
- Air Fryers fineline +88.7% YoY — strongest growth
- NK Dual Zone Air Fryer 8L losing 13.7% of demand because vendor fill rate is only 72.7%
- 9 SKUs with WoS > 18 and low lost sales — markdown candidates
- Canvas Outdoor vendor +2.9% YoY, $7.4M POS, 89.1% fill rate — steady anchor

## Copilot Studio agent

See `copilot_studio_agent_ctc.md` for the importable agent spec (knowledge sources, topics, system instructions, governance posture).
