"""Publish + enrich CTC Merch Data Agent (70dba6b9-...) end-to-end.

The agent was created but never properly bound or published:
  - getDefinition shows only data_agent.json, draft/stage_config.json, .platform
  - /aiassistant returns EntityNotFound
  - No semantic-model datasource binding

This script:
  1. Parses ctc_merch TMDL to enumerate tables, columns, measures, relationships
  2. Constructs draft/ AND published/ semantic-model-ctc_merch/datasource.json
     with merch-specific dataSourceInstructions + per-table descriptions
  3. Constructs draft/ AND published/ stage_config.json with merch aiInstructions
     (POS/EGM/RVS/WoS/fill rate / lost sales vocabulary) + Use Cases appendix
  4. Constructs publish_info.json so Fabric treats published/ as a real stage
  5. POSTs updateDefinition with all 7 parts

Run once:
    py enrich_ctc_data_agent.py
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime

AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"
WS = "9e29a8fd-9462-4c18-b691-f77a631e89ea"
AGENT = "70dba6b9-5a14-4784-8ee1-1c463e58af59"
MODEL = "729c30bc-100a-465a-8af6-4200bd6ff70c"
MODEL_NAME = "ctc_merch"


# ---- 10 sharp merch-team prompts -------------------------------------------
EXAMPLE_QUESTIONS = [
    "Give me a one-paragraph merch briefing — POS YoY, EGM %, top growth, biggest drag.",
    "What are the top 10 SKUs by EGM dollars this year, with POS YoY and EGM %?",
    "Compare Air Fryers vs Cookware Sets fineline POS YoY and EGM %.",
    "Which SKUs have lost sales above 5% AND vendor fill rate below 85%?",
    "Show SKUs with weeks of supply above 18 and lost sales below 2% — markdown candidates.",
    "Summarize Canvas Outdoor vendor performance — POS, fill rate, EGM contribution.",
    "Which new SKUs (New_SKU_Flag = Yes) are driving the most POS growth this year?",
    "By fineline, where is the biggest POS YoY % decline and what is the fill rate there?",
    "Which vendors have the worst fill rate but highest planned purchase quantity going into next season?",
    "What is total demand vs supply gap by category for in-season, and where should I expedite?",
]


# ---- aiInstructions for the merch agent ------------------------------------
AI_INSTRUCTIONS = """\
## Canadian Tire Merch Data Agent

You are a conversational analytics assistant for Canadian Tire merchandising
teams. You answer questions about SKU performance, in-season demand vs supply,
and connected inventory using the ctc_merch semantic model.

### Audience
Merch planners, category managers, and the VP Merch — they think in terms of
fineline / category / vendor / SKU. Use their vocabulary.

### Vocabulary you must use precisely
- POS = Point of Sale dollars (retailer sell-through; always CAD).
- TY / LY = This Year / Last Year (calendar-year basis).
- YTD / QTD / R8 / R12 = Year-to-date / Quarter-to-date / Rolling 8 weeks /
  Rolling 12 months.
- RVS = Retail Value of Shipments (dollars shipped to stores).
- EGM = Enterprise Gross Margin — both an absolute dollar figure and a %.
- WoS = Weeks of Supply (corp + retail inventory / forecast weekly demand).
- Fill rate = Vendor Fill Rate % (units received / units ordered).
- Lost sales % = demand the SKU could not capture due to stockouts.
- Fineline = the finest level of product hierarchy
  (Category > Subcategory > Fineline > SKU).
- New SKU = dim_sku.New_SKU_Flag = "Yes".

### How to answer
1. When asked about an SKU, fineline, category, or vendor, ALWAYS include
   POS YoY %, EGM %, WoS, fill rate, and lost sales % for context.
2. Open with the headline number, then a one-bullet "why" and one-bullet
   "what to do" — merch leaders want decisions, not tables.
3. Currency = CAD. Round POS to thousands ("$49.2M"), EGM % to one decimal.
4. WoS > 18 = overstock signal; WoS < 4 = understock; fill rate < 85% is a
   vendor risk; lost sales > 5% needs an action.

### What to AVOID
- Don't compare to industry averages — you don't have benchmark data.
- Don't quote vendor sustainability index, lead time, or scorecard tier as
  facts — those columns are illustrative for the demo, not actual CTC data.
- Don't conflate Ship Units with POS Units — Ship is what we sent to stores,
  POS is what stores rang at the register.
"""


# ---- dataSourceInstructions (table semantics + metric conventions) ---------
DATA_SOURCE_INSTRUCTIONS = """\
## Tables and Key Measures (ctc_merch)

The ctc_merch Direct Lake semantic model contains three fact tables sharing
the SKU key, plus four dimensions.

### Fact tables
- fact_sku_performance — full-year sell-through with POS, RVS, EGM (dollars
  and %) for TY vs LY, plus QTD/YTD/R12 rollups. Primary fact for executive
  KPI cards. Measures: [POS $ TY], [POS YoY %], [EGM $ TY], [EGM % TY],
  [# Active SKUs], [# New SKUs].
- fact_in_season — in-season inventory and demand for current Spring/Summer
  season. Measures: [POS Units YTD TY], [Ship Units YTD TY], [Avg Weeks of
  Supply], [# SKUs Overstock (WoS>18)], [# SKUs Understock (WoS<4)],
  [Demand vs Supply Gap].
- fact_connected_inventory — rolling-8-week consumer-facing supply chain
  metrics. Measures: [Avg Vendor Fill Rate %], [Avg Lost Sales %],
  [R8 POS TY], [R8 POS YoY %], [# SKUs Fill Rate <85%],
  [# SKUs Lost Sales >5%].

### Dimensions
- dim_sku — SKU master with Category, Subcategory, Fineline, Fineline_Name,
  Vendor, Brand, New_SKU_Flag, Status, Retail_Price, Cost, Store_Count.
  Hierarchy: Category > Subcategory > Fineline > SKU.
- dim_vendor — vendor enrichment (country, lead time, scorecard tier,
  sustainability index). NOTE: vendor enrichment columns are illustrative
  demo data; do not present them as audited CTC vendor facts.
- dim_season — season lookup (e.g. S1 Spring/Summer).
- dim_date — weekly calendar (Week_End_Date, Year_Month, Year_Quarter).

### Metric conventions
- All currency is CAD.
- "This year" vs "last year" is calendar-year, latest available snapshot.
- POS YoY $ = [POS $ TY] - [POS $ LY]; POS YoY % = YoY $ / [POS $ LY].
- EGM % is a ratio, not a count — never sum across SKUs; always weight by
  POS or use the model's [EGM % TY] measure.
- For "growth" questions default to POS YoY %; surface absolute YoY $ too.
- For "in-season" questions, use fact_in_season; for "this week / R8 /
  consumer demand" questions, use fact_connected_inventory.
- "Markdown candidates" pattern: WoS > 18 AND Lost Sales % < 2%.
- "At-risk supply" pattern: Vendor Fill Rate < 85% AND Lost Sales % > 5%.

### Defaults
- Group by Fineline_Name when no grouping is specified.
- Order results by POS $ TY descending unless asked.
- "Top N" defaults to 10 unless the user specifies.
"""


# Per-table descriptions
TABLE_DESCRIPTIONS = {
    "dim_date":      "Weekly calendar (Week_End_Date) with Year, Quarter, Year_Quarter, Year_Month, Week_Number, Fiscal_Year_Label. Use for any time-series or trend analysis.",
    "dim_sku":       "SKU master / product catalog. Hierarchy is Category > Subcategory > Fineline > SKU. Includes Vendor, Brand, New_SKU_Flag, Status, Retail_Price, Cost, Margin_Per_Unit, Store_Count.",
    "dim_vendor":    "Vendor master with Country, Lead_Time_Weeks, Scorecard_Tier, Onboarding_Year, Sustainability_Index. NOTE: enrichment columns are illustrative demo data — do not treat as audited CTC vendor facts.",
    "dim_season":    "Season lookup (Season_Code, Season_Name, Season_Start, Season_End). Currently only S1 Spring/Summer.",
    "fact_sku_performance":   "Full-year SKU sell-through with TY and LY POS Units / POS $ / RVS / EGM $ / EGM %, plus QTD/YTD/R12 POS $ rollups. Primary fact for executive KPI cards and growth analysis.",
    "fact_in_season":         "In-season inventory and demand for the current season. Holds YTD TY/LY POS and Ship, Retail/Corp inventory, Current POS/Ship Forecast, Open PO Qty, Planned Purchase Qty, Weeks_of_Supply. Use for overstock / understock / forecast-vs-actual analysis.",
    "fact_connected_inventory": "Rolling 8-week consumer-facing supply chain view. Holds Corp/Retail Inv TY/LY, YTD POS TY/LY plus YTD_POS_Change_Pct, R8 POS TY/LY plus R8_POS_Change_Pct, YTD_Lost_Sales_Pct, Vendor_Fill_Rate_Pct, Ship Units TY/LY, DDF Units. Use for vendor-risk and demand-capture analysis.",
}


# ---- Use Cases appendix ----------------------------------------------------
USE_CASES_APPENDIX = """

---

## Example Use Cases

The merch team frequently asks the following patterns. When you recognize one,
prefer measures and groupings called out in the data source instructions:

1. Executive merch briefing — POS YoY, EGM %, top growth, biggest drag in one
   paragraph.
2. Top SKUs by EGM dollars — return SKU + fineline + vendor + POS YoY %.
3. Fineline comparison — POS YoY and EGM % side-by-side between two finelines.
4. At-risk SKUs — lost sales > 5% AND vendor fill rate < 85%.
5. Markdown candidates — WoS > 18 AND lost sales < 2%.
6. Vendor summary — for a vendor: POS $ TY, YoY %, EGM $, avg fill rate, avg
   lost sales, top 3 SKUs.
7. New SKU velocity — POS $ TY for SKUs with New_SKU_Flag = "Yes" by fineline.
8. POS YoY decline hotspots — finelines with worst YoY % and their fill rate.
9. Supply risk — vendors with worst fill rate but highest planned purchase.
10. Category demand vs supply — sum gap by category, flag where to expedite.

When answering "executive briefing" or "what should I focus on" questions:
(1) one-line headline with the POS YoY %, (2) 2-3 bullets with specific
fineline / vendor / SKU numbers, (3) one explicit recommendation. Keep it
under 120 words.
"""


# ---- TMDL parser -----------------------------------------------------------
TYPE_MAP = {
    "string":   "String",
    "int64":    "Int64",
    "double":   "Double",
    "decimal":  "Decimal",
    "datetime": "DateTime",
    "boolean":  "Boolean",
}


def parse_table_tmdl(tmdl: str):
    """Return (table_name, [columns], [measures]) from a single table TMDL."""
    m = re.match(r"\s*table\s+(\S+)", tmdl)
    table_name = m.group(1).strip() if m else "?"

    columns, measures = [], []

    # Split on lines starting with 'column' or 'measure' at indent level 1
    # TMDL uses TAB indentation.
    blocks = re.split(r"\n(?=\t(?:column|measure)\s)", "\n" + tmdl)
    for blk in blocks:
        bm = re.match(r"\s*(column|measure)\s+(?:'([^']+)'|(\S+))", blk)
        if not bm:
            continue
        kind = bm.group(1)
        name = bm.group(2) or bm.group(3)
        # description from /// preceding the line, OR description "..." inside block
        desc = None
        # Try /// preceding the block (captured by split? no — find within whole tmdl)
        # We'll do a simpler heuristic: look for `\t\tdataType: <type>` for columns
        dtype = "String"
        dm = re.search(r"\n\t\tdataType:\s*(\S+)", blk)
        if dm:
            dtype = TYPE_MAP.get(dm.group(1).strip().lower(), "String")
        # measure data type is usually returned by Power BI; default Int64 for counts,
        # Decimal for $/%, but here we just mark Double to be safe.
        if kind == "measure":
            dtype = "Double"
        # Description: TMDL stores it as a triple-slash comment ABOVE the column/measure.
        # We split on the column/measure line so the prior block's tail holds the comment.
        item = {"name": name, "dataType": dtype, "description": desc}
        (columns if kind == "column" else measures).append(item)

    # Now grab /// descriptions for columns/measures from the ORIGINAL tmdl
    # by scanning for `/// xxx\n<TAB>column <name>` or `/// xxx\n<TAB>measure <name>`
    desc_re = re.compile(
        r"((?:^|\n)\t///[^\n]*(?:\n\t///[^\n]*)*)\n\t(column|measure)\s+(?:'([^']+)'|(\S+))",
        re.MULTILINE,
    )
    desc_map = {}
    for dm in desc_re.finditer(tmdl):
        comment_block = dm.group(1)
        kind = dm.group(2)
        name = dm.group(3) or dm.group(4)
        # strip leading "\t/// " from each line
        clean = "\n".join(
            re.sub(r"^\t///\s?", "", ln) for ln in comment_block.strip("\n").split("\n")
        ).strip()
        desc_map[(kind, name)] = clean

    for c in columns:
        c["description"] = desc_map.get(("column", c["name"]))
    for m_ in measures:
        m_["description"] = desc_map.get(("measure", m_["name"]))

    return table_name, columns, measures


def parse_relationships_tmdl(tmdl: str):
    """Return list of {FromTable, FromColumn, ToTable, ToColumn, ...} dicts."""
    rels = []
    for m in re.finditer(
        r"relationship\s+\S+\s*\n\s*fromColumn:\s*([^\s\.]+)\.([^\s\n]+)\s*\n\s*toColumn:\s*([^\s\.]+)\.([^\s\n]+)",
        tmdl,
    ):
        ft, fc, tt, tc = m.group(1), m.group(2), m.group(3), m.group(4)
        rels.append({
            "FromTable": ft, "FromColumn": fc,
            "ToTable":   tt, "ToColumn":   tc,
            "IsActive": True,
            "IsBidirectional": False,
            "Cardinality": "ManyToOne",
        })
    return rels


# ---- API plumbing ----------------------------------------------------------

def tok() -> str:
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", API,
         "--query", "accessToken", "-o", "tsv"]).decode().strip()


def call(method: str, url: str, body=None):
    h = {"Authorization": f"Bearer {tok()}", "Content-Type": "application/json",
         "ActivityId": str(uuid.uuid4())}
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    req = urllib.request.Request(url, headers=h, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def poll(loc: str):
    for _ in range(90):
        time.sleep(2)
        s, h, b = call("GET", loc)
        try:
            st = json.loads(b).get("status")
        except Exception:
            st = None
        if st == "Succeeded":
            return True, loc.rstrip("/") + "/result"
        if st == "Failed":
            print(f"  FAILED: {b[:1200]}")
            return False, None
    return False, None


def b64_obj(o) -> str:
    return base64.b64encode(json.dumps(o, indent=2, ensure_ascii=False).encode("utf-8")).decode("ascii")


# ---- Build elements list from TMDL -----------------------------------------

def build_elements(tmdl_files: dict[str, str]):
    """Return (elements_list, csdl_relationships_list)."""
    elements = []
    for path, content in sorted(tmdl_files.items()):
        if not path.startswith("definition/tables/"):
            continue
        table_name, columns, measures = parse_table_tmdl(content)
        children = []
        for c in columns:
            children.append({
                "id": str(uuid.uuid4()),
                "is_selected": True,
                "display_name": c["name"],
                "type": "semantic_model.column",
                "data_type": c["dataType"],
                "description": c["description"],
                "children": [],
            })
        for m in measures:
            children.append({
                "id": str(uuid.uuid4()),
                "is_selected": True,
                "display_name": m["name"],
                "type": "semantic_model.measure",
                "data_type": m["dataType"],
                "description": m["description"],
                "children": [],
            })
        elements.append({
            "id": str(uuid.uuid4()),
            "is_selected": True,
            "display_name": table_name,
            "type": "semantic_model.table",
            "description": TABLE_DESCRIPTIONS.get(table_name),
            "children": children,
        })

    # relationships
    rels = parse_relationships_tmdl(tmdl_files.get("definition/relationships.tmdl", ""))
    return elements, rels


# ---- Main ------------------------------------------------------------------

def main():
    # 1. Pull semantic model TMDL to know tables / columns / measures
    print("Fetching ctc_merch semantic model definition...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/semanticModels/{MODEL}/getDefinition",
                   body={})
    if s == 202:
        ok, result_url = poll(h.get("Location") or h.get("location"))
        if not ok:
            return
        payload = json.loads(call("GET", result_url)[2])
    else:
        payload = json.loads(b)
    tmdl_files = {p["path"]: base64.b64decode(p["payload"]).decode("utf-8")
                  for p in payload["definition"]["parts"]
                  if p["path"].endswith(".tmdl")}
    print(f"  Loaded {len(tmdl_files)} TMDL files")

    elements, rels = build_elements(tmdl_files)
    print(f"  Built {len(elements)} table elements with "
          f"{sum(len(e['children']) for e in elements)} columns/measures total")
    print(f"  Discovered {len(rels)} relationships")

    # 2. Pull existing CTC agent so we know what's there + back it up
    print("\nFetching existing CTC Data Agent definition...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/dataagents/{AGENT}/getDefinition",
                   body={})
    if s == 202:
        ok, result_url = poll(h.get("Location") or h.get("location"))
        if not ok:
            return
        existing = json.loads(call("GET", result_url)[2])
    else:
        existing = json.loads(b)
    parts = {p["path"]: base64.b64decode(p["payload"]).decode("utf-8")
             for p in existing["definition"]["parts"]}
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"backup_ctc_agent_{ts}.json"
    with open(backup, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
    print(f"  Backup -> {backup} ({len(parts)} existing parts)")

    # 3. Build the new parts dict
    datasource_doc = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/definition/dataSource/1.0.0/schema.json",
        "artifactId": MODEL,
        "workspaceId": WS,
        "dataSourceInstructions": DATA_SOURCE_INSTRUCTIONS,
        "displayName": MODEL_NAME,
        "type": "semantic_model",
        "userDescription": None,
        "metadata": {
            "csdl_relationships": json.dumps(rels),
        },
        "elements": elements,
    }
    stage_cfg = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/definition/stageConfiguration/1.0.0/schema.json",
        "aiInstructions": AI_INSTRUCTIONS.rstrip() + USE_CASES_APPENDIX,
    }
    data_agent_doc = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/definition/dataAgent/2.1.0/schema.json",
    }
    publish_info = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/definition/publishInfo/1.0.0/schema.json",
        "description": "",
    }
    platform = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {
            "type": "DataAgent",
            "displayName": "CTC Merch Data Agent",
            "description": "Conversational analytics over CTC Merch SKU performance, in-season demand, and connected inventory",
        },
        "config": {"version": "2.0", "logicalId": "00000000-0000-0000-0000-000000000000"},
    }

    new_parts = {
        ".platform": json.dumps(platform, indent=2),
        "Files/Config/data_agent.json": json.dumps(data_agent_doc, indent=2),
        "Files/Config/publish_info.json": json.dumps(publish_info, indent=2),
        "Files/Config/draft/stage_config.json": json.dumps(stage_cfg, indent=2, ensure_ascii=False),
        "Files/Config/published/stage_config.json": json.dumps(stage_cfg, indent=2, ensure_ascii=False),
        f"Files/Config/draft/semantic-model-{MODEL_NAME}/datasource.json":
            json.dumps(datasource_doc, indent=2, ensure_ascii=False),
        f"Files/Config/published/semantic-model-{MODEL_NAME}/datasource.json":
            json.dumps(datasource_doc, indent=2, ensure_ascii=False),
    }

    payload_parts = [
        {"path": p,
         "payload": base64.b64encode(c.encode("utf-8")).decode("ascii"),
         "payloadType": "InlineBase64"}
        for p, c in new_parts.items()
    ]
    print(f"\nPOSTing updateDefinition with {len(payload_parts)} parts:")
    for p in new_parts:
        print(f"  {p}")

    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/dataagents/{AGENT}/updateDefinition",
                   body={"definition": {"parts": payload_parts}})
    print(f"\n  status={s}")
    if s == 202:
        ok, _ = poll(h.get("Location") or h.get("location"))
        if not ok:
            print("  update failed; restore from backup if needed")
            return
        print("  OK (async)")
    elif s in (200, 201):
        print("  OK (sync)")
    else:
        print(f"  ERROR: {b[:1500]}")
        return

    # Verify
    print("\nVerifying...")
    s, h, b = call("GET", f"{API}/v1/workspaces/{WS}/dataagents/{AGENT}/aiassistant")
    print(f"  /aiassistant status={s}")
    if s == 200:
        info = json.loads(b)
        print(f"  endpoint: {info.get('endpoint','?')}")
    else:
        print(f"  body: {b[:400]}")

    print(f"\n  Open: https://msit.powerbi.com/groups/{WS}/dataagents/{AGENT}")


if __name__ == "__main__":
    main()
