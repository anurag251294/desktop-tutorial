"""Polish formatting across both pages of HR_demo_report:

  Page 1 (Summary Report)  — OVERLAY ONLY (do not move existing 20 visuals):
    - Add an orange accent divider above the first content band
    - Add a thin divider between top and bottom bands
    - Add a footer band with date + 'Powered by hr_demo + HR_data_agent'

  Page 2 (Copilot Showcase) — FULL REBUILD with formatting:
    - Hero header band (title + subtitle + 4px orange accent stripe)
    - Section labels above each row of visuals
    - 26 content visuals (KPIs, gauges, sparklines, matrix, narratives, bars, callout)
    - Thin orange dividers between sections
    - Footer band with date + tagline
    - Page height bumped to 1720 to fit the additional formatting rows

Backs up the report definition first.

Run:
    py format_both_pages.py
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
REPORT = "d28c79f7-5088-4d95-a3c6-c4a0dae093d9"

VISUAL_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.10.0/schema.json"
PAGE_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"

NAVY = "#1B2C5C"
ORANGE = "#F58220"
GOLD = "#FFC72C"
GREY = "#5A6B82"
LIGHT_GREY = "#F0F2F7"
ALMOST_WHITE = "#FAFBFD"

FACT = "fact_headcount_snapshot"
DDATE = "dim_date"
DDEPT = "dim_department"

TODAY = datetime.now().strftime("%Y-%m-%d")


# ---- API plumbing -----------------------------------------------------------

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
            print(f"  FAILED: {b[:800]}")
            return False, None
    return False, None


def b64_obj(o) -> str:
    return base64.b64encode(json.dumps(o, indent=2, ensure_ascii=False).encode("utf-8")).decode("ascii")


# ---- Generic visual builders ------------------------------------------------

def header_off():
    return {"visualHeader": [
        {"properties": {
            "showCopyVisualImageButton": {"expr": {"Literal": {"Value": "false"}}},
            "showFilterRestatementButton": {"expr": {"Literal": {"Value": "false"}}},
            "showFocusModeButton":       {"expr": {"Literal": {"Value": "false"}}},
            "showPinButton":             {"expr": {"Literal": {"Value": "false"}}},
        }}
    ]}


def textbox(name, x, y, w, h, runs, *, bg=None, border=None, z=100):
    paragraphs = [{"textRuns": [
        {"value": r["text"], "textStyle": {
            "fontSize": f"{r.get('size', 10)}pt",
            "fontWeight": r.get("weight", "normal"),
            "color": r.get("color", NAVY)}}
        for r in runs]}]
    objects = {"general": [{"properties": {"paragraphs": paragraphs}}]}
    if bg is not None:
        objects["background"] = [{"properties": {
            "color": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{bg}'"}}}}},
            "show":  {"expr": {"Literal": {"Value": "true"}}},
            "transparency": {"expr": {"Literal": {"Value": "0"}}},
        }}]
    if border is not None:
        objects["border"] = [{"properties": {
            "color": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{border}'"}}}}},
            "show":  {"expr": {"Literal": {"Value": "true"}}},
        }}]
    return {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z},
        "visual": {
            "visualType": "textbox", "drillFilterOtherVisuals": True,
            "objects": objects,
            "visualContainerObjects": header_off(),
        },
    }


def band(name, x, y, w, h, color, z=10):
    """Plain colored rectangle (empty textbox with background)."""
    return textbox(name, x, y, w, h, [{"text": " ", "size": 1, "color": color}], bg=color, z=z)


def divider(name, x, y, w, color=ORANGE, thickness=3):
    """Thin horizontal accent line."""
    return band(name, x, y, w, thickness, color, z=50)


def section_label(name, x, y, w, label_text, *, accent=ORANGE):
    """Compact section header: orange accent bar + navy bold label."""
    return textbox(name, x, y, w, 24, [
        {"text": "▎ ", "size": 12, "weight": "bold", "color": accent},
        {"text": label_text, "size": 12, "weight": "bold", "color": NAVY},
    ], z=200)


def footer_band(name_prefix, x, y, w, h, text_value):
    """Returns 2 visuals: a light-grey background band + a textbox with credit text."""
    return [
        (f"{name_prefix}_bg", band(f"{name_prefix}_bg", x, y, w, h, LIGHT_GREY, z=10)),
        (f"{name_prefix}_txt", textbox(f"{name_prefix}_txt", x + 16, y + 8, w - 32, h - 16, [
            {"text": text_value, "size": 9, "color": GREY},
        ], z=300)),
    ]


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


def kpi(name, x, y, w, h, ind_meas, goal_meas):
    return {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": x, "y": y, "z": 1500, "height": h, "width": w, "tabOrder": 1500},
        "visual": {
            "visualType": "kpi", "drillFilterOtherVisuals": True,
            "query": {"queryState": {
                "Indicator": {"projections": [{**measure_field(*ind_meas), "active": True}]},
                "TrendLine": {"projections": [{**column_field(DDATE, "year_month"), "active": True}]},
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
                    "expr": {"Literal": {"Value": f"'{NAVY}'"}}}}}}}],
                "labels": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}}}],
            },
            "visualContainerObjects": header_off(),
        },
    }


def sparkline(name, x, y, w, h, val_meas, title, color=ORANGE):
    return {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": x, "y": y, "z": 1800, "height": h, "width": w, "tabOrder": 1800},
        "visual": {
            "visualType": "lineChart", "drillFilterOtherVisuals": True,
            "query": {"queryState": {
                "Category": {"projections": [{**column_field(DDATE, "year_month"), "active": True}]},
                "Y": {"projections": [{**measure_field(*val_meas, display=title), "active": True}]},
            }},
            "objects": {
                "title": [{"properties": {
                    "show": {"expr": {"Literal": {"Value": "true"}}},
                    "text": {"expr": {"Literal": {"Value": f"'{title}'"}}},
                    "fontSize": {"expr": {"Literal": {"Value": "11"}}},
                    "fontColor": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{NAVY}'"}}}}}}}],
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
            "query": {"queryState": {"Values": {"projections": projections}}},
            "objects": {
                "grid": [{"properties": {
                    "gridVertical": {"expr": {"Literal": {"Value": "true"}}},
                    "gridHorizontal": {"expr": {"Literal": {"Value": "true"}}},
                    "rowPadding": {"expr": {"Literal": {"Value": "4"}}}}}],
                "values": [{"properties": {
                    "fontSize": {"expr": {"Literal": {"Value": "10"}}},
                    "alternateBackground": {"expr": {"Literal": {"Value": "true"}}}}}],
                "columnHeaders": [{"properties": {
                    "fontColor": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{NAVY}'"}}}}},
                    "backColor": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{LIGHT_GREY}'"}}}}},
                    "bold": {"expr": {"Literal": {"Value": "true"}}}}}],
            },
            "visualContainerObjects": header_off(),
        },
    }


def smart_narrative(name, x, y, w, h, fields):
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


def bar(name, x, y, w, h, cat_col, val_meas, title):
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
                    "expr": {"Literal": {"Value": f"'{ORANGE}'"}}}}}}}],
                "title": [{"properties": {
                    "show": {"expr": {"Literal": {"Value": "true"}}},
                    "text": {"expr": {"Literal": {"Value": f"'{title}'"}}},
                    "fontSize": {"expr": {"Literal": {"Value": "11"}}}}}],
            },
            "visualContainerObjects": header_off(),
        },
    }


def callout_box(name, x, y, w, h, title, lines, accent=ORANGE, bg="#FFF6EC"):
    paragraphs = [{"textRuns": [{"value": title, "textStyle": {
        "fontSize": "12pt", "fontWeight": "bold", "color": accent}}]}]
    for ln in lines:
        paragraphs.append({"textRuns": [{"value": ln, "textStyle": {
            "fontSize": "10pt", "color": NAVY}}]})
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


# ---- Page 2 (Copilot Showcase) — full rebuild with formatting ------------

PAGE_W = 1280
MARGIN = 20
COL_W4 = (PAGE_W - 2 * MARGIN - 3 * 15) // 4    # 4-col with 15px gaps  -> 295
COL_W3 = (PAGE_W - 2 * MARGIN - 2 * 20) // 3    # 3-col with 20px gaps  -> 400
COL_X4 = [MARGIN + i * (COL_W4 + 15) for i in range(4)]   # 20, 330, 640, 950
COL_X3 = [MARGIN + i * (COL_W3 + 20) for i in range(3)]   # 20, 440, 860


def build_page2_visuals():
    items = []

    # ---- Hero header band (y=0-86) ----
    items.append(("hero_title", textbox("hero_title", MARGIN, 14, PAGE_W - 2 * MARGIN, 38, [
        {"text": "Interac HR · Copilot Showcase", "size": 22, "weight": "bold", "color": NAVY},
    ])))
    items.append(("hero_sub", textbox("hero_sub", MARGIN, 50, PAGE_W - 2 * MARGIN, 22, [
        {"text": "Workforce · Attrition · Compliance · Recruiting · AI-powered insights",
         "size": 11, "color": GREY},
    ])))
    items.append(("hero_accent", divider("hero_accent", MARGIN, 80, PAGE_W - 2 * MARGIN, ORANGE, thickness=4)))

    # ---- Section 1: Hero KPIs (label y=98, content y=120-390) ----
    items.append(("lbl1", section_label("lbl1", MARGIN, 98, 800, "Hero KPIs · Compliance Watch")))

    row1_kpis = [
        ("kpi_hc",   "Headcount vs Target",          "Headcount Target"),
        ("kpi_attr", "Attrition Rate vs Threshold",  "Attrition Target"),
        ("kpi_fin",  "FINTRAC Training Compliance",  "FINTRAC Training Target"),
        ("kpi_coi",  "COI Attestation Risk",         "COI Overdue Target"),
    ]
    for (n, base, target), x in zip(row1_kpis, COL_X4):
        items.append((n, kpi(n, x, 128, COL_W4, 130, (FACT, base), (FACT, target))))

    row2_kpis = [
        ("kpi_open", "Open Reqs Pipeline Health",    "Open Reqs Capacity"),
        ("kpi_ttf",  "Time to Fill SLA",             "Time to Fill Target"),
        ("kpi_comp", "Market Comp Competitiveness",  "Comp Ratio Target"),
        ("kpi_reg",  "Regrettable Attrition Risk",   "Regrettable Target"),
    ]
    for (n, base, target), x in zip(row2_kpis, COL_X4):
        items.append((n, kpi(n, x, 268, COL_W4, 130, (FACT, base), (FACT, target))))

    # ---- Section 2: Gauges (label y=418, content y=445-635) ----
    items.append(("lbl2", section_label("lbl2", MARGIN, 418, 800, "Compliance & Capacity Gauges")))
    gauges = [
        ("gauge_hc",   ("Active Employees",),               ("Headcount Target",),        "Headcount vs Target"),
        ("gauge_attr", ("Attrition Rate LTM",),             ("Attrition Target",),        "Attrition vs Threshold"),
        ("gauge_fin",  ("FINTRAC Training Completion %",),  ("FINTRAC Training Target",), "FINTRAC Compliance"),
    ]
    for (n, val, tgt, title), x in zip(gauges, COL_X3):
        items.append((n, gauge(n, x, 445, COL_W3, 190, (FACT, val[0]), (FACT, tgt[0]), title)))

    # ---- Section 3: Trends (label y=658, content y=685-875) ----
    items.append(("lbl3", section_label("lbl3", MARGIN, 658, 800, "12-Month Trends")))
    sparks = [
        ("spark_active",  "Active Employees",              "Headcount Trend",     NAVY),
        ("spark_attr",    "Attrition Rate LTM",            "Attrition Trend",     ORANGE),
        ("spark_fin",     "FINTRAC Training Completion %", "FINTRAC Trend",       GOLD),
        ("spark_open",    "Open Reqs",                     "Open Reqs Trend",     GREY),
    ]
    for (n, base, title, color), x in zip(sparks, COL_X4):
        items.append((n, sparkline(n, x, 685, COL_W4, 190, (FACT, base), title, color)))

    # ---- Section 4: Department × KPI Matrix + Summary Narrative ----
    items.append(("lbl4", section_label("lbl4", MARGIN, 898, 900,
                                        "Department × KPI Matrix · Executive Narrative")))
    items.append(("matrix_kpi", kpi_matrix("matrix_kpi", MARGIN, 925,
                                           COL_X4[2] + COL_W4 - MARGIN, 260)))
    narr_x = COL_X4[2] + COL_W4 - MARGIN + 15
    narr_w = PAGE_W - MARGIN - narr_x
    items.append(("narr_summary", smart_narrative("narr_summary", narr_x, 925, narr_w, 260, [
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

    # ---- Section 5: Per-KPI mini narratives ----
    items.append(("lbl5", section_label("lbl5", MARGIN, 1208, 800, "AI Narrative per KPI")))
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
    for (n, fields), x in zip(mini_narrs, COL_X4):
        items.append((n, smart_narrative(n, x, 1235, COL_W4, 210, fields)))

    # ---- Section 6: Spotlight (bars + Copilot callout) ----
    items.append(("lbl6", section_label("lbl6", MARGIN, 1468, 800, "Spotlight · Try Copilot")))
    items.append(("bar_attr_dept", bar("bar_attr_dept", MARGIN, 1495, 415, 175,
        (DDEPT, "department_name"),
        (FACT, "Regrettable Attrition LTM"),
        "Regrettable Attrition by Department")))
    items.append(("bar_fin_func", bar("bar_fin_func", MARGIN + 415 + 15, 1495, 415, 175,
        (DDEPT, "function"),
        (FACT, "FINTRAC Training Completion %"),
        "FINTRAC Completion by Function")))
    callout_x = MARGIN + 2 * (415 + 15)
    callout_w = PAGE_W - MARGIN - callout_x
    items.append(("callout_copilot", callout_box("callout_copilot", callout_x, 1495,
                                                 callout_w, 175,
        "🤖  Try Copilot live",
        [
            "• Click the Copilot button (top ribbon)",
            "• Summarize this page",
            "• Which functions have FINTRAC < 90%?",
            "• Top 3 risks for my CHRO this week",
            "",
            "💬  Continue in Teams via HR_data_agent",
        ])))

    # ---- Footer (y=1685-1720) ----
    footer_text = (f"HR_demo_report  ·  Powered by hr_demo + HR_data_agent  ·  "
                   f"Generated {TODAY}")
    items.extend(footer_band("footer", 0, 1685, PAGE_W, 35, footer_text))

    return items


# ---- Page 1 (Summary Report) — overlay only, do not move existing ----------

def build_page1_overlays():
    """Return overlay-only visuals to add ON TOP of the existing Page 1
    layout. Existing 20 visuals are preserved untouched.
    """
    items = []
    # Orange accent stripe just below the title row (Page 1 existing header
    # textboxes are at y=2 and y=33, content begins at y=84).
    items.append(("ov_accent", divider("ov_accent", 12, 78, PAGE_W - 24, ORANGE, thickness=3)))
    # Subtle divider between top content band (y<=380) and bottom band (y>=402)
    items.append(("ov_mid_div", divider("ov_mid_div", 12, 395, PAGE_W - 24, LIGHT_GREY, thickness=2)))
    # Footer band (page height = 720)
    footer_text = (f"HR_demo_report  ·  Powered by hr_demo + HR_data_agent  ·  "
                   f"Generated {TODAY}")
    items.extend(footer_band("ov_footer", 0, 680, PAGE_W, 35, footer_text))
    return items


# ---- Page slug discovery ---------------------------------------------------

def find_slug(parts: dict, display_name: str) -> str:
    for path, b64 in parts.items():
        if path.endswith("/page.json") and path.startswith("definition/pages/"):
            meta = json.loads(base64.b64decode(b64))
            if meta.get("displayName") == display_name:
                return path.split("/")[-2]
    raise RuntimeError(f"No page with displayName {display_name!r}")


# ---- Main ------------------------------------------------------------------

def main():
    print("Fetching HR_demo_report definition...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/reports/{REPORT}/getDefinition",
                   body={})
    if s == 202:
        ok, result_url = poll(h.get("Location") or h.get("location"))
        if not ok: return
        payload = json.loads(call("GET", result_url)[2])
    else:
        payload = json.loads(b)
    parts = {p["path"]: p["payload"] for p in payload["definition"]["parts"]}
    fmt = payload["definition"].get("format", "PBIR")
    print(f"  Loaded {len(parts)} parts (format={fmt})")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"backup_hr_report_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"  Backup -> {backup_path}")

    # ----- Clean up broken customTheme reference (apply_interac_theme.py
    # registered an InteracBrand customTheme that Fabric can't resolve;
    # remove it and let per-visual colors handle branding instead).
    rj_path = "definition/report.json"
    rj = json.loads(base64.b64decode(parts[rj_path]).decode("utf-8"))
    tc = rj.get("themeCollection", {})
    if "customTheme" in tc:
        del tc["customTheme"]
        print("  Removed broken customTheme reference from report.json")
    pkgs = rj.get("resourcePackages", [])
    pkgs = [p for p in pkgs if p.get("name") != "RegisteredResources"]
    rj["resourcePackages"] = pkgs
    parts[rj_path] = b64_obj(rj)
    # Also drop the orphan theme file part (harmless but tidy)
    for p in list(parts):
        if p.startswith("StaticResources/RegisteredResources/"):
            del parts[p]
            print(f"  Removed orphan part: {p}")

    # ----- Page 2: wipe and rebuild with formatting -----
    slug2 = find_slug(parts, "Copilot Showcase")
    print(f"  Page 2 (Copilot Showcase) slug: {slug2}")
    visual_prefix2 = f"definition/pages/{slug2}/visuals/"
    wiped = [p for p in parts if p.startswith(visual_prefix2)]
    for p in wiped:
        del parts[p]
    page2_json = {
        "$schema": PAGE_SCHEMA, "name": slug2,
        "displayName": "Copilot Showcase",
        "displayOption": "FitToPage",
        "height": 1720, "width": PAGE_W,
    }
    parts[f"definition/pages/{slug2}/page.json"] = b64_obj(page2_json)
    page2_visuals = build_page2_visuals()
    for name, vj in page2_visuals:
        parts[f"{visual_prefix2}{name}/visual.json"] = b64_obj(vj)
    print(f"  Page 2: wiped {len(wiped)} old visuals, added {len(page2_visuals)} new")

    # ----- Page 1: append overlays only -----
    slug1 = find_slug(parts, "Summary Report")
    print(f"  Page 1 (Summary Report) slug: {slug1}")
    visual_prefix1 = f"definition/pages/{slug1}/visuals/"
    page1_overlays = build_page1_overlays()
    for name, vj in page1_overlays:
        path = f"{visual_prefix1}{name}/visual.json"
        # Skip if same overlay name already exists from prior run — replace
        parts[path] = b64_obj(vj)
    print(f"  Page 1: added {len(page1_overlays)} overlay visuals (existing visuals untouched)")

    # ----- Push -----
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
            print("  update failed — restore from backup if needed")
    elif s in (200, 201):
        print(f"\n  OK -> https://msit.powerbi.com/groups/{WS}/reports/{REPORT}")
    else:
        print(f"  ERROR: {b[:1200]}")


if __name__ == "__main__":
    main()
