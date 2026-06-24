"""Build Rogers_Finance_ARPU_Demo report - 3 pages tied to slide 6 of the
'Enterprise Semantic Layer' pitch deck.

  1. Finance Executive View  - ARPU trend, ARPU by BU, revenue, net adds
  2. ARPU Deep-Dive          - by region, segment, product (anomaly drilldown)
  3. One Measure, Many Surfaces - meta page reinforcing the demo narrative
     (the same [ARPU] measure in card, KPI, table, and chart forms)

Mirrors rogers_demo/build_report.py.
"""
from __future__ import annotations

import base64
import json
import subprocess
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path

ROOT = Path(__file__).parent
STACK = json.loads((ROOT / "stack_finance.json").read_text())
WS = STACK["workspace_id"]
MODEL = STACK.get("model_id")
WS_NAME = STACK["workspace_name"]
MODEL_NAME = STACK.get("model_name", "rogers_finance")
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"
REPORT_NAME = "Rogers_Finance_ARPU_Demo"

PAGE1 = "p" + uuid.uuid4().hex[:18]
PAGE2 = "p" + uuid.uuid4().hex[:18]
PAGE3 = "p" + uuid.uuid4().hex[:18]

# Rogers brand palette
ROGERS_RED = "#DA291C"
NAVY = "#1B2C5C"
GRAY = "#5A6B82"


def tok():
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", API,
         "--query", "accessToken", "-o", "tsv"]).decode().strip()


def call(method, url, body=None):
    h = {"Authorization": f"Bearer {tok()}", "Content-Type": "application/json",
         "ActivityId": str(uuid.uuid4())}
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    req = urllib.request.Request(url, headers=h, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def poll(loc):
    for _ in range(180):
        time.sleep(3)
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


def find_report(name):
    s, h, b = call("GET", f"{API}/v1/workspaces/{WS}/reports")
    for it in json.loads(b).get("value", []):
        if it.get("displayName") == name:
            return it.get("id")
    return None


# ---- Theme ---------------------------------------------------------------

ROGERS_THEME = {
    "name": "RogersSemanticLayer",
    "dataColors": [ROGERS_RED, NAVY, "#22A06B", "#F5A623", "#7C3AED",
                   "#0EA5E9", "#EA580C", "#6B7280"],
    "background": "#FFFFFF",
    "foreground": NAVY,
    "tableAccent": ROGERS_RED,
    "good": "#22A06B", "neutral": "#F5A623", "bad": ROGERS_RED,
    "maximum": ROGERS_RED, "center": "#F5A623", "minimum": "#22A06B",
    "null": "#9CA3AF",
    "textClasses": {
        "title":   {"fontSize": 18, "color": NAVY, "fontFace": "Segoe UI Semibold"},
        "header":  {"fontSize": 12, "color": NAVY, "fontFace": "Segoe UI Semibold"},
        "label":   {"fontSize": 10, "color": NAVY, "fontFace": "Segoe UI"},
        "callout": {"fontSize": 28, "color": NAVY, "fontFace": "Segoe UI Semibold"},
    },
}

# ---- Top-level files -----------------------------------------------------

DEFINITION_PBIR = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
    "version": "4.0",
    "datasetReference": {
        "byConnection": {
            "connectionString": (
                f"Data Source=powerbi://api.powerbi.com/v1.0/myorg/{WS_NAME};"
                f"initial catalog={MODEL_NAME};integrated security=ClaimsToken;"
                f"semanticmodelid={MODEL}"
            )
        }
    },
}

VERSION_JSON = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
    "version": "2.0.0",
}

REPORT_JSON = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.3.0/schema.json",
    "themeCollection": {
        "baseTheme": {
            "name": "RogersSemanticLayer",
            "reportVersionAtImport": {"visual": "2.9.0", "report": "3.3.0", "page": "2.3.1"},
            "type": "RegisteredResources",
        }
    },
    "objects": {
        "section":      [{"properties": {"verticalAlignment": {"expr": {"Literal": {"Value": "'Top'"}}}}}],
        "outspacePane": [{"properties": {"expanded": {"expr": {"Literal": {"Value": "false"}}}}}],
    },
    "reportSource": "QuickCreate",
    "resourcePackages": [{
        "name": "RegisteredResources", "type": "RegisteredResources",
        "items": [{"name": "RogersSemanticLayer", "path": "RogersSemanticLayer.json",
                   "type": "BaseTheme"}],
    }],
    "settings": {"useStylableVisualContainerHeader": True,
                 "exportDataMode": "AllowSummarized",
                 "defaultDrillFilterOtherVisuals": True,
                 "allowChangeFilterTypes": True,
                 "allowInlineExploration": True,
                 "useEnhancedTooltips": True,
                 "useDefaultAggregateDisplayName": True},
}

PAGES_JSON = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json",
    "pageOrder": [PAGE1, PAGE2, PAGE3],
    "activePageName": PAGE1,
}


def page_json(page_id, display_name):
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
        "name": page_id, "displayName": display_name,
        "displayOption": "FitToPage", "height": 720, "width": 1280,
    }


PLATFORM = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
    "metadata": {"type": "Report", "displayName": REPORT_NAME,
                 "description": "Rogers Enterprise Semantic Layer - Finance ARPU demo (exec, deep-dive, one measure many surfaces)"},
    "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
}

VISUAL_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.10.0/schema.json"


def visual_header_off():
    return {"visualHeader": [
        {"properties": {
            "showCopyVisualImageButton":  {"expr": {"Literal": {"Value": "false"}}},
            "showFilterRestatementButton":{"expr": {"Literal": {"Value": "false"}}},
            "showFocusModeButton":        {"expr": {"Literal": {"Value": "false"}}},
            "showPinButton":              {"expr": {"Literal": {"Value": "false"}}},
        }}
    ]}


def title_visual(name, x, y, w, h, text, font_pt=20, bold=True, color=None):
    color = color or NAVY
    return {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": x, "y": y, "z": 0, "height": h, "width": w, "tabOrder": 0},
        "visual": {
            "visualType": "textbox", "drillFilterOtherVisuals": True,
            "objects": {"general": [{"properties": {"paragraphs": [{"textRuns": [
                {"value": text, "textStyle": {
                    "fontSize": f"{font_pt}pt",
                    "fontWeight": "bold" if bold else "normal",
                    "color": color}}]}]}}]},
            "visualContainerObjects": visual_header_off(),
        },
    }


def card_visual(name, x, y, w, h, entity, measure_prop, display_name):
    return {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": x, "y": y, "z": 1000, "height": h, "width": w, "tabOrder": 1000},
        "visual": {
            "visualType": "card", "drillFilterOtherVisuals": True,
            "query": {"queryState": {"Values": {"projections": [{
                "field": {"Measure": {
                    "Expression": {"SourceRef": {"Entity": entity}},
                    "Property": measure_prop}},
                "queryRef": f"{entity}.{measure_prop}",
                "nativeQueryRef": measure_prop,
                "displayName": display_name, "active": True}]}}},
            "objects": {
                "labels": [{"properties": {
                    "fontSize": {"expr": {"Literal": {"Value": "26D"}}},
                    "color":    {"solid": {"color": {"expr": {"Literal": {"Value": f"'{NAVY}'"}}}}},
                }}],
                "categoryLabels": [{"properties": {
                    "fontSize": {"expr": {"Literal": {"Value": "11D"}}},
                    "color":    {"solid": {"color": {"expr": {"Literal": {"Value": f"'{GRAY}'"}}}}},
                }}],
            },
            "visualContainerObjects": visual_header_off(),
        },
    }


def bar_chart(name, x, y, w, h, cat_entity, cat_prop, meas_entity, meas_prop, meas_label,
              chart="barChart", color_id=1, sort_desc=True):
    return {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": x, "y": y, "z": 2000, "height": h, "width": w, "tabOrder": 2000},
        "visual": {
            "visualType": chart, "drillFilterOtherVisuals": True,
            "query": {
                "queryState": {
                    "Category": {"projections": [{
                        "field": {"Column": {
                            "Expression": {"SourceRef": {"Entity": cat_entity}},
                            "Property": cat_prop}},
                        "queryRef": f"{cat_entity}.{cat_prop}",
                        "nativeQueryRef": cat_prop, "active": True}]},
                    "Y": {"projections": [{
                        "field": {"Measure": {
                            "Expression": {"SourceRef": {"Entity": meas_entity}},
                            "Property": meas_prop}},
                        "queryRef": f"{meas_entity}.{meas_prop}",
                        "nativeQueryRef": meas_prop, "displayName": meas_label}]},
                },
                "sortDefinition": {"sort": [{
                    "field": {"Measure": {
                        "Expression": {"SourceRef": {"Entity": meas_entity}},
                        "Property": meas_prop}},
                    "direction": "Descending" if sort_desc else "Ascending"}]},
            },
            "objects": {
                "labels": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}}}],
                "dataPoint": [{"properties": {"fill": {"solid": {"color": {
                    "expr": {"ThemeDataColor": {"ColorId": color_id, "Percent": 0}}}}}}}],
            },
            "visualContainerObjects": visual_header_off(),
        },
    }


def column_chart(name, x, y, w, h, cat, cprop, ment, mprop, label, color_id=2):
    return bar_chart(name, x, y, w, h, cat, cprop, ment, mprop, label,
                     chart="columnChart", color_id=color_id)


def line_chart(name, x, y, w, h, cat_entity, cat_prop, meas_entity, meas_prop, label, color_id=1):
    return {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": x, "y": y, "z": 2200, "height": h, "width": w, "tabOrder": 2200},
        "visual": {
            "visualType": "lineChart", "drillFilterOtherVisuals": True,
            "query": {"queryState": {
                "Category": {"projections": [{
                    "field": {"Column": {
                        "Expression": {"SourceRef": {"Entity": cat_entity}},
                        "Property": cat_prop}},
                    "queryRef": f"{cat_entity}.{cat_prop}",
                    "nativeQueryRef": cat_prop, "active": True}]},
                "Y": {"projections": [{
                    "field": {"Measure": {
                        "Expression": {"SourceRef": {"Entity": meas_entity}},
                        "Property": meas_prop}},
                    "queryRef": f"{meas_entity}.{meas_prop}",
                    "nativeQueryRef": meas_prop, "displayName": label}]},
            }},
            "objects": {
                "labels": [{"properties": {"show": {"expr": {"Literal": {"Value": "false"}}}}}],
                "dataPoint": [{"properties": {"fill": {"solid": {"color": {
                    "expr": {"ThemeDataColor": {"ColorId": color_id, "Percent": 0}}}}}}}],
            },
            "visualContainerObjects": visual_header_off(),
        },
    }


def table_visual(name, x, y, w, h, fields):
    projections = []
    for f in fields:
        if f["type"] == "measure":
            field_ref = {"Measure": {
                "Expression": {"SourceRef": {"Entity": f["entity"]}},
                "Property": f["property"]}}
        else:
            field_ref = {"Column": {
                "Expression": {"SourceRef": {"Entity": f["entity"]}},
                "Property": f["property"]}}
        qref = f"{f['entity']}.{f['property']}"
        proj = {"field": field_ref, "queryRef": qref, "nativeQueryRef": f["property"]}
        if f.get("label"):
            proj["displayName"] = f["label"]
        projections.append(proj)
    return {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": x, "y": y, "z": 3000, "height": h, "width": w, "tabOrder": 3000},
        "visual": {
            "visualType": "tableEx", "drillFilterOtherVisuals": True,
            "query": {"queryState": {"Values": {"projections": projections}}},
            "objects": {"values": [{"properties": {"fontSize": {"expr": {"Literal": {"Value": "9D"}}}}}]},
            "visualContainerObjects": visual_header_off(),
        },
    }


def slicer(name, x, y, w, h, entity, prop):
    return {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": x, "y": y, "z": 500, "height": h, "width": w, "tabOrder": 500},
        "visual": {
            "visualType": "slicer", "drillFilterOtherVisuals": True,
            "query": {"queryState": {"Values": {"projections": [{
                "field": {"Column": {
                    "Expression": {"SourceRef": {"Entity": entity}},
                    "Property": prop}},
                "queryRef": f"{entity}.{prop}",
                "nativeQueryRef": prop, "active": True}]}}},
            "visualContainerObjects": visual_header_off(),
        },
    }


def smart_narrative(name, x, y, w, h, fields):
    projections = []
    for f in fields:
        if f["type"] == "measure":
            field_ref = {"Measure": {
                "Expression": {"SourceRef": {"Entity": f["entity"]}},
                "Property": f["property"]}}
        else:
            field_ref = {"Column": {
                "Expression": {"SourceRef": {"Entity": f["entity"]}},
                "Property": f["property"]}}
        qref = f"{f['entity']}.{f['property']}"
        projections.append({"field": field_ref, "queryRef": qref,
                            "nativeQueryRef": f["property"]})
    return {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": x, "y": y, "z": 4000, "height": h, "width": w, "tabOrder": 4000},
        "visual": {
            "visualType": "aiNarratives", "drillFilterOtherVisuals": True,
            "query": {"queryState": {"Values": {"projections": projections}}},
            "visualContainerObjects": visual_header_off(),
        },
    }


def callout(name, x, y, w, h, title, lines, accent=None, bg="#FFF6F6"):
    accent = accent or ROGERS_RED
    paragraphs = [{"textRuns": [{"value": title,
                                  "textStyle": {"fontSize": "12pt", "fontWeight": "bold",
                                                "color": accent}}]}]
    for ln in lines:
        paragraphs.append({"textRuns": [
            {"value": ln, "textStyle": {"fontSize": "10pt", "color": NAVY}}]})
    return {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": x, "y": y, "z": 4500, "height": h, "width": w, "tabOrder": 4500},
        "visual": {
            "visualType": "textbox", "drillFilterOtherVisuals": True,
            "objects": {
                "general": [{"properties": {"paragraphs": paragraphs}}],
                "background": [{"properties": {
                    "color": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{bg}'"}}}}},
                    "show":  {"expr": {"Literal": {"Value": "true"}}},
                }}],
                "border": [{"properties": {
                    "color": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{accent}'"}}}}},
                    "show":  {"expr": {"Literal": {"Value": "true"}}},
                }}],
            },
            "visualContainerObjects": visual_header_off(),
        },
    }


def header_block(slide_visuals, page_label, subtitle):
    safe = page_label.replace(" ", "_").replace(",", "")
    slide_visuals.append((f"v_hdr_{safe}", title_visual(
        f"v_hdr_{safe}", 20, 14, 1240, 38,
        f"Rogers - Enterprise Semantic Layer | {page_label}", font_pt=16)))
    slide_visuals.append((f"v_sub_{safe}", title_visual(
        f"v_sub_{safe}", 20, 50, 1240, 24, subtitle,
        font_pt=10, bold=False, color=GRAY)))


# ---- Page 1: Finance Executive View --------------------------------------

def page1_visuals():
    items = []
    header_block(items, "Finance Executive View",
                 "Certified ARPU x Revenue x Net Adds | Direct Lake on rogers_finance_lh | One semantic model, every surface")

    items.append(("v1_card_arpu", card_visual("v1_card_arpu", 20, 84, 295, 130,
                                               "fact_revenue_monthly", "ARPU",
                                               "ARPU (certified)")))
    items.append(("v1_card_rev",  card_visual("v1_card_rev",  335, 84, 295, 130,
                                               "fact_revenue_monthly", "Revenue (Millions)",
                                               "Revenue")))
    items.append(("v1_card_subs", card_visual("v1_card_subs", 650, 84, 295, 130,
                                               "fact_subscribers_monthly", "End-of-Period Subscribers",
                                               "Subscribers")))
    items.append(("v1_card_na",   card_visual("v1_card_na",   965, 84, 295, 130,
                                               "fact_subscribers_monthly", "Net Adds (MoM)",
                                               "Net Adds")))

    items.append(("v1_narr", smart_narrative(
        "v1_narr", 20, 230, 415, 220,
        [
            {"entity": "fact_revenue_monthly",     "property": "ARPU",                       "type": "measure"},
            {"entity": "fact_revenue_monthly",     "property": "Revenue",                    "type": "measure"},
            {"entity": "fact_revenue_monthly",     "property": "Revenue YoY %",              "type": "measure"},
            {"entity": "fact_revenue_monthly",     "property": "ARPU YoY %",                 "type": "measure"},
            {"entity": "fact_subscribers_monthly", "property": "Net Adds (MoM)",             "type": "measure"},
            {"entity": "dim_business_unit",        "property": "bu_name",                    "type": "column"},
            {"entity": "dim_date",                 "property": "month_label",                "type": "column"},
        ])))

    items.append(("v1_callout", callout(
        "v1_callout", 20, 460, 415, 200,
        "One measure, queried everywhere",
        [
            "ARPU is defined ONCE in this certified model.",
            "",
            "Same measure consumed in:",
            "  - This Power BI report",
            "  - Excel connected PivotTable (Finance's turf)",
            "  - Rogers Finance Data Agent in Teams",
            "",
            "Edit the measure once - everything updates.",
        ])))

    items.append(("v1_line_arpu", line_chart(
        "v1_line_arpu", 445, 230, 815, 220,
        "dim_date", "month_label",
        "fact_revenue_monthly", "ARPU", "ARPU", color_id=1)))

    items.append(("v1_col_rev_bu", column_chart(
        "v1_col_rev_bu", 445, 460, 815, 200,
        "dim_business_unit", "bu_name",
        "fact_revenue_monthly", "Revenue (Millions)", "Revenue ($M)", color_id=2)))

    items.append(("v1_sl_bu",   slicer("v1_sl_bu",   20, 670, 410, 38, "dim_business_unit", "bu_name")))
    items.append(("v1_sl_reg",  slicer("v1_sl_reg",  440, 670, 410, 38, "dim_region", "region_name")))
    items.append(("v1_sl_date", slicer("v1_sl_date", 860, 670, 400, 38, "dim_date", "month_label")))
    return items


# ---- Page 2: ARPU Deep-Dive ----------------------------------------------

def page2_visuals():
    items = []
    header_block(items, "ARPU Deep-Dive",
                 "ARPU by BU x region x segment x product | Find anomalies (Wireless Prepaid Apr-Jun 2026)")

    items.append(("v2_card_w",  card_visual("v2_card_w",  20, 84, 295, 130,
                                             "fact_revenue_monthly", "ARPU - Wireless", "Wireless")))
    items.append(("v2_card_c",  card_visual("v2_card_c", 335, 84, 295, 130,
                                             "fact_revenue_monthly", "ARPU - Cable & Home", "Cable & Home")))
    items.append(("v2_card_m",  card_visual("v2_card_m", 650, 84, 295, 130,
                                             "fact_revenue_monthly", "ARPU - Media", "Media")))
    items.append(("v2_card_e",  card_visual("v2_card_e", 965, 84, 295, 130,
                                             "fact_revenue_monthly", "ARPU - Enterprise", "Enterprise")))

    items.append(("v2_narr", smart_narrative(
        "v2_narr", 20, 230, 415, 250,
        [
            {"entity": "fact_revenue_monthly",     "property": "ARPU",          "type": "measure"},
            {"entity": "fact_revenue_monthly",     "property": "ARPU MoM %",    "type": "measure"},
            {"entity": "fact_subscribers_monthly", "property": "Average Subscribers", "type": "measure"},
            {"entity": "fact_churn_monthly",       "property": "Churn Rate %",  "type": "measure"},
            {"entity": "dim_business_unit",        "property": "bu_name",       "type": "column"},
            {"entity": "dim_product",              "property": "product_name",  "type": "column"},
            {"entity": "dim_region",               "property": "region_name",   "type": "column"},
        ])))

    items.append(("v2_bar_region", bar_chart(
        "v2_bar_region", 445, 230, 815, 250,
        "dim_region", "region_name",
        "fact_revenue_monthly", "ARPU", "ARPU", color_id=1)))

    items.append(("v2_callout", callout(
        "v2_callout", 20, 490, 415, 170,
        "Try these in the Data Agent",
        [
            "- What happened to Wireless Prepaid ARPU in April 2026?",
            "- ARPU by region for Cable & Home, last 6 months",
            "- Which segment has the highest ARPU?",
            "- Top 5 products by revenue, with margin",
        ])))

    items.append(("v2_table_prod", table_visual(
        "v2_table_prod", 445, 490, 815, 170,
        [
            {"entity": "dim_product",          "property": "product_name", "type": "column",  "label": "Product"},
            {"entity": "dim_business_unit",    "property": "bu_name",      "type": "column",  "label": "BU"},
            {"entity": "fact_revenue_monthly", "property": "Revenue",      "type": "measure", "label": "Revenue"},
            {"entity": "fact_revenue_monthly", "property": "ARPU",         "type": "measure", "label": "ARPU"},
            {"entity": "fact_churn_monthly",   "property": "Churn Rate %", "type": "measure", "label": "Churn %"},
            {"entity": "fact_costs_monthly",   "property": "Gross Margin %","type": "measure","label": "GM %"},
        ])))

    items.append(("v2_sl_bu",   slicer("v2_sl_bu",   20, 670, 410, 38, "dim_business_unit", "bu_name")))
    items.append(("v2_sl_seg",  slicer("v2_sl_seg",  440, 670, 410, 38, "dim_customer_segment", "segment_name")))
    items.append(("v2_sl_date", slicer("v2_sl_date", 860, 670, 400, 38, "dim_date", "month_label")))
    return items


# ---- Page 3: One Measure, Many Surfaces ----------------------------------

def page3_visuals():
    items = []
    header_block(items, "One Measure, Many Surfaces",
                 "The SAME certified [ARPU] in card / KPI / table / chart - and queried identically from Excel and the Copilot agent")

    items.append(("v3_card_arpu", card_visual("v3_card_arpu", 20, 84, 295, 200,
                                                "fact_revenue_monthly", "ARPU",
                                                "ARPU (card)")))
    items.append(("v3_card_w", card_visual("v3_card_w", 335, 84, 295, 95,
                                            "fact_revenue_monthly", "ARPU - Wireless",
                                            "Wireless ARPU")))
    items.append(("v3_card_c", card_visual("v3_card_c", 335, 189, 295, 95,
                                            "fact_revenue_monthly", "ARPU - Cable & Home",
                                            "Cable & Home ARPU")))
    items.append(("v3_card_m", card_visual("v3_card_m", 650, 84, 295, 95,
                                            "fact_revenue_monthly", "ARPU - Media",
                                            "Media ARPU")))
    items.append(("v3_card_e", card_visual("v3_card_e", 650, 189, 295, 95,
                                            "fact_revenue_monthly", "ARPU - Enterprise",
                                            "Enterprise ARPU")))

    items.append(("v3_callout_lhs", callout(
        "v3_callout_lhs", 965, 84, 295, 200,
        "Where else is this number?",
        [
            "- Connected PivotTable in Excel",
            "- Power BI reports across Finance",
            "- Teams: 'Rogers Finance Data Agent'",
            "- Any tool with XMLA access",
            "",
            "All sourced from rogers_finance.",
        ])))

    items.append(("v3_line", line_chart(
        "v3_line", 20, 300, 620, 250,
        "dim_date", "month_label",
        "fact_revenue_monthly", "ARPU", "ARPU (line)", color_id=1)))

    items.append(("v3_bar_bu", bar_chart(
        "v3_bar_bu", 650, 300, 610, 250,
        "dim_business_unit", "bu_name",
        "fact_revenue_monthly", "ARPU", "ARPU by BU", color_id=2)))

    items.append(("v3_table", table_visual(
        "v3_table", 20, 560, 1240, 100,
        [
            {"entity": "dim_business_unit",    "property": "bu_name",       "type": "column",  "label": "Business Unit"},
            {"entity": "fact_revenue_monthly", "property": "Revenue",       "type": "measure", "label": "Revenue"},
            {"entity": "fact_subscribers_monthly", "property": "Average Subscribers", "type": "measure", "label": "Avg Subs"},
            {"entity": "fact_revenue_monthly", "property": "ARPU",          "type": "measure", "label": "ARPU"},
            {"entity": "fact_revenue_monthly", "property": "ARPU MoM %",    "type": "measure", "label": "ARPU MoM"},
            {"entity": "fact_revenue_monthly", "property": "ARPU YoY %",    "type": "measure", "label": "ARPU YoY"},
        ])))

    items.append(("v3_sl_date", slicer("v3_sl_date", 20, 670, 1240, 38, "dim_date", "month_label")))
    return items


def b64(obj):
    return base64.b64encode(json.dumps(obj, indent=2).encode("utf-8")).decode("ascii")


def build_parts():
    parts = {
        ".platform":                                                  b64(PLATFORM),
        "definition.pbir":                                            b64(DEFINITION_PBIR),
        "definition/version.json":                                    b64(VERSION_JSON),
        "definition/report.json":                                     b64(REPORT_JSON),
        "definition/pages/pages.json":                                b64(PAGES_JSON),
        f"definition/pages/{PAGE1}/page.json":                        b64(page_json(PAGE1, "Finance Executive View")),
        f"definition/pages/{PAGE2}/page.json":                        b64(page_json(PAGE2, "ARPU Deep-Dive")),
        f"definition/pages/{PAGE3}/page.json":                        b64(page_json(PAGE3, "One Measure, Many Surfaces")),
        "StaticResources/RegisteredResources/RogersSemanticLayer.json": b64(ROGERS_THEME),
    }
    for name, vj in page1_visuals():
        parts[f"definition/pages/{PAGE1}/visuals/{name}/visual.json"] = b64(vj)
    for name, vj in page2_visuals():
        parts[f"definition/pages/{PAGE2}/visuals/{name}/visual.json"] = b64(vj)
    for name, vj in page3_visuals():
        parts[f"definition/pages/{PAGE3}/visuals/{name}/visual.json"] = b64(vj)
    return [{"path": p, "payload": pl, "payloadType": "InlineBase64"} for p, pl in parts.items()]


def main():
    if not MODEL:
        print("ERROR: stack_finance.json is missing model_id - build the semantic model first.")
        return
    parts = build_parts()
    print(f"Built {len(parts)} parts")
    for p in parts:
        decoded_len = len(base64.b64decode(p["payload"]))
        print(f"  {p['path']:<78s} ({decoded_len} bytes)")

    existing = find_report(REPORT_NAME)
    if existing:
        print(f"\nReport {REPORT_NAME} exists ({existing}) - updateDefinition...")
        s, h, b = call("POST",
                       f"{API}/v1/workspaces/{WS}/reports/{existing}/updateDefinition",
                       body={"definition": {"format": "PBIR", "parts": parts}})
    else:
        print(f"\nCreating report '{REPORT_NAME}'...")
        body = {"displayName": REPORT_NAME,
                "description": "Rogers Enterprise Semantic Layer - Finance ARPU 3-page demo",
                "type": "Report",
                "definition": {"format": "PBIR", "parts": parts}}
        s, h, b = call("POST", f"{API}/v1/workspaces/{WS}/items", body=body)
    print(f"  status={s}")
    if s == 202:
        loc = h.get("Location") or h.get("location")
        ok, result_url = poll(loc)
        if not ok:
            return
        if not existing:
            sr, hr, br = call("GET", result_url)
            item = json.loads(br)
            STACK["report_id"] = item["id"]
            STACK["report_name"] = REPORT_NAME
            (ROOT / "stack_finance.json").write_text(json.dumps(STACK, indent=2))
            print(f"\nReport id: {item['id']}")
        print(f"Open: https://msit.powerbi.com/groups/{WS}/reports/{existing or STACK.get('report_id')}")
    elif s in (200, 201):
        print("  OK (sync)")
    else:
        print(f"  ERROR: {b[:1000]}")


if __name__ == "__main__":
    main()
