"""Rebuild the 'Copilot Showcase' page of HR_demo_report with a fancy KPI layout.

Wipes the page's existing visuals and rebuilds with 26 visuals across 7 rows:

  Row 1 (y=84-214)    8 traffic-light KPI cards (Headcount, Attrition, FINTRAC, COI)
  Row 2 (y=224-354)   Continued: Open Reqs, Time to Fill, Comp Ratio, Regrettable
  Row 3 (y=370-560)   3 gauges (Headcount / Attrition / FINTRAC)
  Row 4 (y=580-770)   4 sparkline line charts (Active, Attrition, FINTRAC, Open Reqs trends)
  Row 5 (y=790-1050)  Conditional KPI matrix (tableEx) + Summary aiNarrative
  Row 6 (y=1070-1280) 4 per-KPI mini aiNarratives (Attrition, Regrettable, FINTRAC, COI)
  Row 7 (y=1300-1470) 2 bar charts + Copilot live callout

Backs up the current report definition to ./backup_hr_report_<ts>.json before
pushing, so the prior state can be restored if needed.

Run once:
    py enrich_hr_showcase_v2.py
"""
from __future__ import annotations

import base64
import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime

AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"
WS = "de6a7e47-474b-4354-87e7-26b8d741f015"
REPORT = "d28c79f7-5088-4d95-a3c6-c4a0dae093d9"   # HR_demo_report
SHOWCASE_DISPLAY = "Copilot Showcase"

VISUAL_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.10.0/schema.json"
PAGE_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"

FACT = "fact_headcount_snapshot"
DDATE = "dim_date"
DDEPT = "dim_department"

# Brand palette (Interac-ish)
INTERAC_NAVY = "#1B2C5C"
INTERAC_ORANGE = "#F58220"
INTERAC_GOLD = "#FFC72C"
INTERAC_GREY = "#5A6B82"
BG_LIGHT = "#F7F8FB"


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
            print(f"  FAILED: {b[:600]}")
            return False, None
    return False, None


def b64_obj(o) -> str:
    return base64.b64encode(json.dumps(o, indent=2, ensure_ascii=False).encode("utf-8")).decode("ascii")


# ---- Visual builders -------------------------------------------------------

def header_off():
    return {"visualHeader": [
        {"properties": {
            "showCopyVisualImageButton": {"expr": {"Literal": {"Value": "false"}}},
            "showFilterRestatementButton": {"expr": {"Literal": {"Value": "false"}}},
            "showFocusModeButton":       {"expr": {"Literal": {"Value": "false"}}},
            "showPinButton":             {"expr": {"Literal": {"Value": "false"}}},
        }}
    ]}


def text(name, x, y, w, h, runs, z=0):
    """runs: list of dicts with keys text, size, weight, color."""
    paragraphs = [{"textRuns": [
        {"value": r["text"], "textStyle": {
            "fontSize": f"{r.get('size', 10)}pt",
            "fontWeight": r.get("weight", "normal"),
            "color": r.get("color", INTERAC_NAVY)}}
        for r in runs]}]
    return {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z},
        "visual": {
            "visualType": "textbox", "drillFilterOtherVisuals": True,
            "objects": {"general": [{"properties": {"paragraphs": paragraphs}}]},
            "visualContainerObjects": header_off(),
        },
    }


def callout_box(name, x, y, w, h, title, lines, accent=INTERAC_ORANGE, bg="#FFF6EC"):
    paragraphs = [
        {"textRuns": [{"value": title, "textStyle": {
            "fontSize": "12pt", "fontWeight": "bold", "color": accent}}]}
    ]
    for ln in lines:
        paragraphs.append({"textRuns": [
            {"value": ln, "textStyle": {"fontSize": "10pt", "color": INTERAC_NAVY}}]})
    return {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": x, "y": y, "z": 4500, "height": h, "width": w, "tabOrder": 4500},
        "visual": {
            "visualType": "textbox", "drillFilterOtherVisuals": True,
            "objects": {
                "general": [{"properties": {"paragraphs": paragraphs}}],
                "background": [{"properties": {
                    "color": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{bg}'"}}}}},
                    "show":  {"expr": {"Literal": {"Value": "true"}}}}}],
                "border": [{"properties": {
                    "color": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{accent}'"}}}}},
                    "show":  {"expr": {"Literal": {"Value": "true"}}}}}],
            },
            "visualContainerObjects": header_off(),
        },
    }


def measure_field(entity, prop, display=None):
    f = {"field": {"Measure": {"Expression": {"SourceRef": {"Entity": entity}},
                               "Property": prop}},
         "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop}
    if display: f["displayName"] = display
    return f


def column_field(entity, prop, display=None):
    f = {"field": {"Column": {"Expression": {"SourceRef": {"Entity": entity}},
                              "Property": prop}},
         "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop}
    if display: f["displayName"] = display
    return f


def kpi(name, x, y, w, h, ind_meas, goal_meas, trend_col=("dim_date", "year_month")):
    return {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": x, "y": y, "z": 1500, "height": h, "width": w, "tabOrder": 1500},
        "visual": {
            "visualType": "kpi", "drillFilterOtherVisuals": True,
            "query": {"queryState": {
                "Indicator": {"projections": [{**measure_field(*ind_meas), "active": True}]},
                "TrendLine": {"projections": [{**column_field(*trend_col), "active": True}]},
                "Goals":     {"projections": [measure_field(*goal_meas)]},
            }},
            "visualContainerObjects": header_off(),
        },
    }


def gauge(name, x, y, w, h, val_meas, target_meas, title):
    return {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": x, "y": y, "z": 1700, "height": h, "width": w, "tabOrder": 1700},
        "visual": {
            "visualType": "gauge", "drillFilterOtherVisuals": True,
            "query": {"queryState": {
                "Y":           {"projections": [{**measure_field(*val_meas, display=title), "active": True}]},
                "TargetValue": {"projections": [measure_field(*target_meas)]},
            }},
            "objects": {
                "dataPoint": [{"properties": {"fill": {"solid": {"color": {
                    "expr": {"Literal": {"Value": f"'{INTERAC_NAVY}'"}}}}}}}],
                "calloutValue": [{"properties": {
                    "fontSize": {"expr": {"Literal": {"Value": "24"}}},
                    "color": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{INTERAC_NAVY}'"}}}}}}}],
                "labels": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}}}],
            },
            "visualContainerObjects": header_off(),
        },
    }


def sparkline(name, x, y, w, h, val_meas, title, color=INTERAC_ORANGE):
    return {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": x, "y": y, "z": 1800, "height": h, "width": w, "tabOrder": 1800},
        "visual": {
            "visualType": "lineChart", "drillFilterOtherVisuals": True,
            "query": {"queryState": {
                "Category": {"projections": [{**column_field("dim_date", "year_month"), "active": True}]},
                "Y": {"projections": [{**measure_field(*val_meas, display=title), "active": True}]},
            }},
            "objects": {
                "title": [{"properties": {
                    "show": {"expr": {"Literal": {"Value": "true"}}},
                    "text": {"expr": {"Literal": {"Value": f"'{title}'"}}},
                    "fontSize": {"expr": {"Literal": {"Value": "11"}}},
                    "fontColor": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{INTERAC_NAVY}'"}}}}}}}],
                "labels": [{"properties": {"show": {"expr": {"Literal": {"Value": "false"}}}}}],
                "categoryAxis": [{"properties": {"show": {"expr": {"Literal": {"Value": "false"}}}}}],
                "valueAxis": [{"properties": {"show": {"expr": {"Literal": {"Value": "false"}}}}}],
                "legend": [{"properties": {"show": {"expr": {"Literal": {"Value": "false"}}}}}],
                "dataPoint": [{"properties": {"defaultColor": {"solid": {"color": {
                    "expr": {"Literal": {"Value": f"'{color}'"}}}}}}}],
                "lineStyles": [{"properties": {
                    "strokeWidth": {"expr": {"Literal": {"Value": "3"}}},
                    "showMarker": {"expr": {"Literal": {"Value": "true"}}}}}],
            },
            "visualContainerObjects": header_off(),
        },
    }


def kpi_matrix(name, x, y, w, h):
    """A tableEx showing department × KPI matrix with conditional formatting."""
    projections = [
        {**column_field(DDEPT, "department_name", "Department"), "active": True},
        measure_field(FACT, "Active Employees", "Headcount"),
        measure_field(FACT, "Attrition Rate LTM", "Attrition %"),
        measure_field(FACT, "% Regrettable LTM", "Regrettable %"),
        measure_field(FACT, "Open Reqs", "Open Reqs"),
        measure_field(FACT, "Avg Time to Fill (days)", "Time to Fill"),
        measure_field(FACT, "Comp Ratio vs Market", "Compa-Ratio"),
        measure_field(FACT, "FINTRAC Training Completion %", "FINTRAC %"),
        measure_field(FACT, "COI Overdue 90+ Days", "COI Overdue"),
    ]
    return {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": x, "y": y, "z": 1900, "height": h, "width": w, "tabOrder": 1900},
        "visual": {
            "visualType": "tableEx", "drillFilterOtherVisuals": True,
            "query": {"queryState": {
                "Values": {"projections": projections},
            }},
            "objects": {
                "grid": [{"properties": {
                    "gridVertical": {"expr": {"Literal": {"Value": "true"}}},
                    "gridHorizontal": {"expr": {"Literal": {"Value": "true"}}},
                    "rowPadding": {"expr": {"Literal": {"Value": "4"}}}}}],
                "values": [{"properties": {
                    "fontSize": {"expr": {"Literal": {"Value": "10"}}},
                    "alternateBackground": {"expr": {"Literal": {"Value": "true"}}}}}],
                "columnHeaders": [{"properties": {
                    "fontColor": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{INTERAC_NAVY}'"}}}}},
                    "backColor": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{BG_LIGHT}'"}}}}},
                    "bold": {"expr": {"Literal": {"Value": "true"}}}}}],
            },
            "visualContainerObjects": header_off(),
        },
    }


def smart_narrative(name, x, y, w, h, fields):
    """fields: list of (entity, property, type) where type in {'measure','column'}."""
    projections = []
    for entity, prop, kind in fields:
        if kind == "measure":
            projections.append(measure_field(entity, prop))
        else:
            projections.append(column_field(entity, prop))
    return {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": x, "y": y, "z": 4000, "height": h, "width": w, "tabOrder": 4000},
        "visual": {
            "visualType": "aiNarratives", "drillFilterOtherVisuals": True,
            "query": {"queryState": {"Values": {"projections": projections}}},
            "visualContainerObjects": header_off(),
        },
    }


def bar(name, x, y, w, h, cat_col, val_meas, title, color_id=1):
    return {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": x, "y": y, "z": 2000, "height": h, "width": w, "tabOrder": 2000},
        "visual": {
            "visualType": "barChart", "drillFilterOtherVisuals": True,
            "query": {"queryState": {
                "Category": {"projections": [{**column_field(*cat_col), "active": True}]},
                "Y": {"projections": [{**measure_field(*val_meas, display=title), "active": True}]},
            }},
            "objects": {
                "labels": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}}}],
                "dataPoint": [{"properties": {"fill": {"solid": {"color": {
                    "expr": {"ThemeDataColor": {"ColorId": color_id, "Percent": 0}}}}}}}],
                "title": [{"properties": {
                    "show": {"expr": {"Literal": {"Value": "true"}}},
                    "text": {"expr": {"Literal": {"Value": f"'{title}'"}}},
                    "fontSize": {"expr": {"Literal": {"Value": "11"}}}}}],
            },
            "visualContainerObjects": header_off(),
        },
    }


# ---- The new page contents -------------------------------------------------

def build_visuals():
    items = []

    # ---- Header band -----------------------------------------------------
    items.append(("hdr", text("hdr", 20, 14, 1240, 36, [
        {"text": "Interac HR – Copilot Showcase", "size": 20, "weight": "bold", "color": INTERAC_NAVY},
    ])))
    items.append(("sub", text("sub", 20, 52, 1240, 20, [
        {"text": "Traffic-light KPIs · Gauges · Trends · KPI Matrix · Smart Narratives · Copilot prompts",
         "size": 10, "weight": "normal", "color": INTERAC_GREY},
    ])))

    # ---- Row 1: 4 KPI cards (Hero metrics) -------------------------------
    kpis_row1 = [
        ("kpi_hc",   "Headcount vs Target",          "Headcount Target"),
        ("kpi_attr", "Attrition Rate vs Threshold",  "Attrition Target"),
        ("kpi_fin",  "FINTRAC Training Compliance",  "FINTRAC Training Target"),
        ("kpi_coi",  "COI Attestation Risk",         "COI Overdue Target"),
    ]
    x_positions = [20, 335, 650, 965]
    for (name, base, target), x in zip(kpis_row1, x_positions):
        items.append((name, kpi(name, x, 84, 295, 130,
                                (FACT, base), (FACT, target))))

    # ---- Row 2: 4 KPI cards (Operational metrics) ------------------------
    kpis_row2 = [
        ("kpi_open", "Open Reqs Pipeline Health",    "Open Reqs Capacity"),
        ("kpi_ttf",  "Time to Fill SLA",             "Time to Fill Target"),
        ("kpi_comp", "Market Comp Competitiveness",  "Comp Ratio Target"),
        ("kpi_reg",  "Regrettable Attrition Risk",   "Regrettable Target"),
    ]
    for (name, base, target), x in zip(kpis_row2, x_positions):
        items.append((name, kpi(name, x, 224, 295, 130,
                                (FACT, base), (FACT, target))))

    # ---- Row 3: 3 gauges -------------------------------------------------
    gauges = [
        ("gauge_hc",   ("Active Employees",),               ("Headcount Target",),        "Headcount vs Target"),
        ("gauge_attr", ("Attrition Rate LTM",),             ("Attrition Target",),        "Attrition vs Threshold"),
        ("gauge_fin",  ("FINTRAC Training Completion %",),  ("FINTRAC Training Target",), "FINTRAC Compliance"),
    ]
    gauge_x = [20, 440, 860]
    for (name, val, tgt, title), x in zip(gauges, gauge_x):
        items.append((name, gauge(name, x, 370, 400, 190,
                                  (FACT, val[0]), (FACT, tgt[0]), title)))

    # ---- Row 4: 4 sparkline trend charts ---------------------------------
    sparks = [
        ("spark_active",  "Active Employees",              "Headcount Trend (12 mo)",   INTERAC_NAVY),
        ("spark_attr",    "Attrition Rate LTM",            "Attrition Rate Trend",      INTERAC_ORANGE),
        ("spark_fin",     "FINTRAC Training Completion %", "FINTRAC Completion Trend",  INTERAC_GOLD),
        ("spark_open",    "Open Reqs",                     "Open Reqs Trend",           INTERAC_GREY),
    ]
    for (name, base, title, color), x in zip(sparks, x_positions):
        items.append((name, sparkline(name, x, 580, 295, 190,
                                      (FACT, base), title, color)))

    # ---- Row 5: KPI matrix (left) + Summary aiNarrative (right) -----------
    items.append(("matrix_kpi", kpi_matrix("matrix_kpi", 20, 790, 815, 260)))
    items.append(("narr_summary", smart_narrative("narr_summary", 845, 790, 415, 260, [
        (FACT, "Active Employees", "measure"),
        (FACT, "Attrition Rate LTM", "measure"),
        (FACT, "% Regrettable LTM", "measure"),
        (FACT, "Open Reqs", "measure"),
        (FACT, "Avg Time to Fill (days)", "measure"),
        (FACT, "Comp Ratio vs Market", "measure"),
        (FACT, "FINTRAC Training Completion %", "measure"),
        (FACT, "COI Overdue 90+ Days", "measure"),
        (DDEPT, "department_name", "column"),
        (DDEPT, "function", "column"),
    ])))

    # ---- Row 6: 4 per-KPI mini Smart Narratives --------------------------
    mini_narrs = [
        ("narr_attr",  [(FACT, "Attrition Rate LTM", "measure"),
                        (FACT, "Terminations LTM", "measure"),
                        (DDEPT, "department_name", "column")]),
        ("narr_reg",   [(FACT, "% Regrettable LTM", "measure"),
                        (FACT, "Regrettable Attrition LTM", "measure"),
                        (DDEPT, "function", "column")]),
        ("narr_fin",   [(FACT, "FINTRAC Training Completion %", "measure"),
                        (DDEPT, "department_name", "column"),
                        (DDEPT, "function", "column")]),
        ("narr_coi",   [(FACT, "COI Overdue 90+ Days", "measure"),
                        (DDEPT, "department_name", "column")]),
    ]
    for (name, fields), x in zip(mini_narrs, x_positions):
        items.append((name, smart_narrative(name, x, 1070, 295, 210, fields)))

    # ---- Row 7: 2 bar charts + Copilot live callout ----------------------
    items.append(("bar_attr_dept", bar("bar_attr_dept", 20, 1300, 415, 170,
        (DDEPT, "department_name"),
        (FACT, "Regrettable Attrition LTM"),
        "Regrettable Attrition by Department", color_id=1)))
    items.append(("bar_fin_func", bar("bar_fin_func", 445, 1300, 415, 170,
        (DDEPT, "function"),
        (FACT, "FINTRAC Training Completion %"),
        "FINTRAC Completion by Function", color_id=3)))
    items.append(("callout_copilot", callout_box("callout_copilot", 870, 1300, 390, 170,
        "🤖  Try Copilot live",
        [
            "• Click the Copilot button in the top ribbon",
            "• Summarize this page",
            "• Which functions have FINTRAC < 90%?",
            "• Top 3 risks I should brief my CHRO on",
            "",
            "💬  Continue in Teams via",
            "    HR_data_agent (10 starter prompts)",
        ])))

    return items


# ---- Main ------------------------------------------------------------------

def find_showcase_slug(parts: dict) -> str:
    """Find the page slug whose page.json has displayName 'Copilot Showcase'."""
    for path, b64 in parts.items():
        if path.endswith("/page.json") and path.startswith("definition/pages/"):
            meta = json.loads(base64.b64decode(b64))
            if meta.get("displayName") == SHOWCASE_DISPLAY:
                slug = path.split("/")[-2]
                return slug
    raise RuntimeError(f"No page with displayName '{SHOWCASE_DISPLAY}' found")


def main():
    print("Fetching HR_demo_report definition...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/reports/{REPORT}/getDefinition",
                   body={})
    if s == 202:
        ok, result_url = poll(h.get("Location") or h.get("location"))
        if not ok:
            return
        payload = json.loads(call("GET", result_url)[2])
    else:
        payload = json.loads(b)
    parts = {p["path"]: p["payload"] for p in payload["definition"]["parts"]}
    fmt = payload["definition"].get("format", "PBIR")
    print(f"  Loaded {len(parts)} parts (format={fmt})")

    # Backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"backup_hr_report_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"  Backup saved -> {backup_path}")

    # Find the Showcase page slug
    slug = find_showcase_slug(parts)
    print(f"  Copilot Showcase slug: {slug}")

    # Wipe all existing visuals on the Showcase page
    visual_prefix = f"definition/pages/{slug}/visuals/"
    wiped = [p for p in parts if p.startswith(visual_prefix)]
    for p in wiped:
        del parts[p]
    print(f"  Wiped {len(wiped)} existing visuals")

    # Update page.json (new dimensions for richer layout)
    page_json = {
        "$schema": PAGE_SCHEMA,
        "name": slug,
        "displayName": "Copilot Showcase",
        "displayOption": "FitToPage",
        "height": 1500, "width": 1280,
    }
    parts[f"definition/pages/{slug}/page.json"] = b64_obj(page_json)

    # Add new visuals
    new_visuals = build_visuals()
    for name, vj in new_visuals:
        parts[f"{visual_prefix}{name}/visual.json"] = b64_obj(vj)
    print(f"  Added {len(new_visuals)} new visuals")

    # Push
    payload_parts = [{"path": p, "payload": pl, "payloadType": "InlineBase64"}
                     for p, pl in parts.items()]
    print(f"\nPOSTing updateDefinition with {len(payload_parts)} parts...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/reports/{REPORT}/updateDefinition",
                   body={"definition": {"format": fmt, "parts": payload_parts}})
    print(f"  status={s}")
    if s == 202:
        ok, _ = poll(h.get("Location") or h.get("location"))
        if ok:
            print(f"\n  OK -> https://msit.powerbi.com/groups/{WS}/reports/{REPORT}")
        else:
            print("  update failed — revert with backup if needed")
    elif s in (200, 201):
        print(f"\n  OK -> https://msit.powerbi.com/groups/{WS}/reports/{REPORT}")
    else:
        print(f"  ERROR: {b[:1200]}")


if __name__ == "__main__":
    main()
