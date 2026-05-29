"""Build Rogers_Network_Anomaly_Copilot_Demo report - 3 pages:
  1. Network Health Overview - exec snapshot, hero KPIs, narrative, top sites
  2. Anomaly Deep-Dive - availability trend, throughput by vendor, latency, congestion
  3. Customer Impact - tickets by segment, sentiment, affected customers

PBIR format. Inline-defined Rogers-themed colour theme so no external dump
file is required.
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
STACK = json.loads((ROOT / "stack_rogers.json").read_text())
WS = STACK["workspace_id"]
MODEL = STACK.get("model_id")
WS_NAME = STACK["workspace_name"]
MODEL_NAME = STACK.get("model_name", "rogers_net")
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"
REPORT_NAME = "Rogers_Network_Anomaly_Copilot_Demo"

PAGE1 = "p" + uuid.uuid4().hex[:18]
PAGE2 = "p" + uuid.uuid4().hex[:18]
PAGE3 = "p" + uuid.uuid4().hex[:18]

# Rogers brand palette (red anchor)
ROGERS_RED = "#DA291C"
NAVY = "#1B2C5C"
GRAY = "#5A6B82"
BG_TINT = "#FAFBFC"


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


# ---- Theme (inline) -------------------------------------------------------

ROGERS_THEME = {
    "name": "RogersNetwork",
    "dataColors": [ROGERS_RED, NAVY, "#22A06B", "#F5A623", "#7C3AED", "#0EA5E9", "#EA580C", "#6B7280"],
    "background": "#FFFFFF",
    "foreground": NAVY,
    "tableAccent": ROGERS_RED,
    "good": "#22A06B",
    "neutral": "#F5A623",
    "bad": ROGERS_RED,
    "maximum": ROGERS_RED,
    "center": "#F5A623",
    "minimum": "#22A06B",
    "null": "#9CA3AF",
    "textClasses": {
        "title":    {"fontSize": 18, "color": NAVY, "fontFace": "Segoe UI Semibold"},
        "header":   {"fontSize": 12, "color": NAVY, "fontFace": "Segoe UI Semibold"},
        "label":    {"fontSize": 10, "color": NAVY, "fontFace": "Segoe UI"},
        "callout":  {"fontSize": 28, "color": NAVY, "fontFace": "Segoe UI Semibold"},
    },
}


# ---- Top-level files ------------------------------------------------------

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
            "name": "RogersNetwork",
            "reportVersionAtImport": {"visual": "2.9.0", "report": "3.3.0", "page": "2.3.1"},
            "type": "RegisteredResources",
        }
    },
    "objects": {
        "section": [{"properties": {"verticalAlignment": {"expr": {"Literal": {"Value": "'Top'"}}}}}],
        "outspacePane": [{"properties": {"expanded": {"expr": {"Literal": {"Value": "false"}}}}}],
    },
    "reportSource": "QuickCreate",
    "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources",
                          "items": [{"name": "RogersNetwork", "path": "RogersNetwork.json",
                                     "type": "BaseTheme"}]}],
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
        "name": page_id,
        "displayName": display_name,
        "displayOption": "FitToPage",
        "height": 720,
        "width": 1280,
    }


PLATFORM = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
    "metadata": {"type": "Report", "displayName": REPORT_NAME,
                 "description": "Rogers Network Anomaly Detection Copilot demo - exec snapshot + deep-dive + customer impact"},
    "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
}

VISUAL_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.10.0/schema.json"


def visual_header_off():
    return {"visualHeader": [
        {"properties": {
            "showCopyVisualImageButton": {"expr": {"Literal": {"Value": "false"}}},
            "showFilterRestatementButton": {"expr": {"Literal": {"Value": "false"}}},
            "showFocusModeButton":       {"expr": {"Literal": {"Value": "false"}}},
            "showPinButton":             {"expr": {"Literal": {"Value": "false"}}},
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


def scatter(name, x, y, w, h, details_entity, details_prop,
            x_entity, x_prop, x_label, y_entity, y_prop, y_label):
    return {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": x, "y": y, "z": 2500, "height": h, "width": w, "tabOrder": 2500},
        "visual": {
            "visualType": "scatterChart", "drillFilterOtherVisuals": True,
            "query": {"queryState": {
                "Details": {"projections": [{
                    "field": {"Column": {
                        "Expression": {"SourceRef": {"Entity": details_entity}},
                        "Property": details_prop}},
                    "queryRef": f"{details_entity}.{details_prop}",
                    "nativeQueryRef": details_prop, "active": True}]},
                "X": {"projections": [{
                    "field": {"Measure": {
                        "Expression": {"SourceRef": {"Entity": x_entity}},
                        "Property": x_prop}},
                    "queryRef": f"{x_entity}.{x_prop}",
                    "nativeQueryRef": x_prop, "displayName": x_label}]},
                "Y": {"projections": [{
                    "field": {"Measure": {
                        "Expression": {"SourceRef": {"Entity": y_entity}},
                        "Property": y_prop}},
                    "queryRef": f"{y_entity}.{y_prop}",
                    "nativeQueryRef": y_prop, "displayName": y_label}]},
            }},
            "objects": {
                "categoryAxis": [{"properties": {"start": {"expr": {"Literal": {"Value": "0D"}}}}}],
                "valueAxis":    [{"properties": {"start": {"expr": {"Literal": {"Value": "0D"}}}}}],
                "labels":       [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}}}],
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
    paragraphs = [
        {"textRuns": [{"value": title,
                       "textStyle": {"fontSize": "12pt", "fontWeight": "bold",
                                     "color": accent}}]}
    ]
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
    slide_visuals.append((f"v_hdr_{page_label.replace(' ', '_')}", title_visual(
        f"v_hdr_{page_label.replace(' ', '_')}", 20, 14, 1240, 38,
        f"Rogers - Network Anomaly Detection | {page_label}", font_pt=16)))
    slide_visuals.append((f"v_sub_{page_label.replace(' ', '_')}", title_visual(
        f"v_sub_{page_label.replace(' ', '_')}", 20, 50, 1240, 24, subtitle,
        font_pt=10, bold=False, color=GRAY)))


# ---- Page 1: Network Health Overview --------------------------------------

def page1_visuals():
    items = []
    header_block(items, "Overview",
                 "Direct Lake | RAN KPIs x Alarms x Customer Impact | Copilot exec demo")

    # Row 1: 4 cards (avoid KPI visuals which need goal measures we didn't define)
    items.append(("v1_card_avail", card_visual("v1_card_avail", 20, 84, 295, 130,
                                                "fact_cell_kpi", "Avg Availability %",
                                                "Avg Availability %")))
    items.append(("v1_card_dl", card_visual("v1_card_dl", 335, 84, 295, 130,
                                             "fact_cell_kpi", "Avg DL Throughput (Mbps)",
                                             "Avg DL Throughput")))
    items.append(("v1_card_below", card_visual("v1_card_below", 650, 84, 295, 130,
                                                "fact_cell_kpi", "# Cells Below 99% Avail",
                                                "# Cells Below 99% Avail")))
    items.append(("v1_card_tickets", card_visual("v1_card_tickets", 965, 84, 295, 130,
                                                  "fact_customer_impact", "Tickets Opened",
                                                  "Tickets Opened")))

    # Row 2: AI Narrative (left) + bar by Province (right)
    items.append(("v1_narr", smart_narrative(
        "v1_narr", 20, 230, 415, 200,
        [
            {"entity": "fact_cell_kpi", "property": "Avg Availability %", "type": "measure"},
            {"entity": "fact_cell_kpi", "property": "Avg DL Throughput (Mbps)", "type": "measure"},
            {"entity": "fact_cell_kpi", "property": "# Cells Below 99% Avail", "type": "measure"},
            {"entity": "fact_cell_kpi", "property": "# Cells Congested", "type": "measure"},
            {"entity": "fact_alarms",   "property": "# Critical Alarms",       "type": "measure"},
            {"entity": "fact_customer_impact", "property": "Tickets Opened",   "type": "measure"},
            {"entity": "dim_site",      "property": "region",                  "type": "column"},
            {"entity": "dim_cell",      "property": "vendor",                  "type": "column"},
        ])))

    # Copilot prompt callout
    items.append(("v1_callout", callout(
        "v1_callout", 20, 440, 415, 220,
        "Try these Copilot prompts",
        [
            "- Brief me on last 7 days network health",
            "- Sites with availability below 95%",
            "- Throughput by vendor and province",
            "- Top 10 most congested cells",
            "- Which segment opened the most tickets?",
            "",
            "Also available in Teams via",
            "   Rogers Network Data Agent",
        ])))

    # Bar by region (Tickets opened)
    items.append(("v1_bar_region", bar_chart(
        "v1_bar_region", 445, 230, 815, 200,
        "dim_site", "region",
        "fact_customer_impact", "Tickets Opened", "Tickets Opened", color_id=1)))

    # Column - critical alarms by province
    items.append(("v1_col_alarms", column_chart(
        "v1_col_alarms", 445, 440, 815, 220,
        "dim_site", "region",
        "fact_alarms", "# Critical Alarms", "Critical Alarms", color_id=1)))

    # Slicers row at very bottom
    items.append(("v1_sl_region", slicer("v1_sl_region", 20, 670, 410, 38, "dim_site", "region")))
    items.append(("v1_sl_vendor", slicer("v1_sl_vendor", 440, 670, 410, 38, "dim_cell", "vendor")))
    items.append(("v1_sl_tech",   slicer("v1_sl_tech",   860, 670, 400, 38, "dim_cell", "technology")))

    return items


# ---- Page 2: Anomaly Deep-Dive --------------------------------------------

def page2_visuals():
    items = []
    header_block(items, "Anomaly Deep-Dive",
                 "Availability trend x Throughput by vendor x Latency anomalies x Congestion hotspots")

    # Row 1: 4 cards
    items.append(("v2_card_min", card_visual("v2_card_min", 20, 84, 295, 130,
                                              "fact_cell_kpi", "Min Availability %",
                                              "Worst-Hour Availability")))
    items.append(("v2_card_lat", card_visual("v2_card_lat", 335, 84, 295, 130,
                                              "fact_cell_kpi", "Avg Latency (ms)",
                                              "Avg Latency")))
    items.append(("v2_card_prb", card_visual("v2_card_prb", 650, 84, 295, 130,
                                              "fact_cell_kpi", "Avg PRB Utilization %",
                                              "Avg PRB Utilization")))
    items.append(("v2_card_mttr", card_visual("v2_card_mttr", 965, 84, 295, 130,
                                               "fact_alarms", "Avg MTTR (min)",
                                               "Avg MTTR")))

    # Row 2: Narrative + Throughput by vendor
    items.append(("v2_narr", smart_narrative(
        "v2_narr", 20, 230, 415, 250,
        [
            {"entity": "fact_cell_kpi", "property": "Avg DL Throughput (Mbps)", "type": "measure"},
            {"entity": "fact_cell_kpi", "property": "Avg Latency (ms)",         "type": "measure"},
            {"entity": "fact_cell_kpi", "property": "Avg PRB Utilization %",    "type": "measure"},
            {"entity": "fact_cell_kpi", "property": "Outage Hours (Avail<50%)", "type": "measure"},
            {"entity": "fact_alarms",   "property": "# Critical Alarms",        "type": "measure"},
            {"entity": "dim_cell",      "property": "vendor",                   "type": "column"},
            {"entity": "dim_site",      "property": "region",                   "type": "column"},
            {"entity": "dim_cell",      "property": "technology",               "type": "column"},
        ])))

    items.append(("v2_col_dl", column_chart(
        "v2_col_dl", 445, 230, 815, 250,
        "dim_cell", "vendor",
        "fact_cell_kpi", "Avg DL Throughput (Mbps)", "Avg DL Throughput (Mbps)", color_id=2)))

    # Row 3: Callout + Congestion scatter
    items.append(("v2_callout", callout(
        "v2_callout", 20, 490, 415, 170,
        "Ask Copilot",
        [
            "- Which cells had latency above 60ms?",
            "- Vendors with worst throughput?",
            "- Cell-hours at >85% PRB last week?",
            "",
            "Continue in Teams via Rogers Network Data Agent",
        ])))

    items.append(("v2_scatter", scatter(
        "v2_scatter", 445, 490, 815, 170,
        "dim_cell", "cell_id",
        "fact_cell_kpi", "Avg PRB Utilization %", "PRB Utilization",
        "fact_cell_kpi", "Avg Latency (ms)", "Latency (ms)")))

    # Slicers
    items.append(("v2_sl_region", slicer("v2_sl_region", 20, 670, 410, 38, "dim_site", "region")))
    items.append(("v2_sl_vendor", slicer("v2_sl_vendor", 440, 670, 410, 38, "dim_cell", "vendor")))
    items.append(("v2_sl_date",   slicer("v2_sl_date",   860, 670, 400, 38, "dim_date", "date_key")))

    return items


# ---- Page 3: Customer Impact ----------------------------------------------

def page3_visuals():
    items = []
    header_block(items, "Customer Impact",
                 "Tickets by segment x Sentiment x Affected customers x Repeat caller rate")

    # Row 1: 4 cards
    items.append(("v3_card_tickets", card_visual("v3_card_tickets", 20, 84, 295, 130,
                                                  "fact_customer_impact", "Tickets Opened",
                                                  "Tickets Opened")))
    items.append(("v3_card_repeat",  card_visual("v3_card_repeat", 335, 84, 295, 130,
                                                  "fact_customer_impact", "Repeat Caller Rate",
                                                  "Repeat Caller Rate")))
    items.append(("v3_card_sent",    card_visual("v3_card_sent", 650, 84, 295, 130,
                                                  "fact_customer_impact", "Avg Sentiment",
                                                  "Avg Sentiment")))
    items.append(("v3_card_aff",     card_visual("v3_card_aff", 965, 84, 295, 130,
                                                  "fact_customer_impact", "Affected Customers",
                                                  "Affected Customers")))

    # Row 2: Narrative + Tickets by segment
    items.append(("v3_narr", smart_narrative(
        "v3_narr", 20, 230, 415, 250,
        [
            {"entity": "fact_customer_impact", "property": "Tickets Opened",       "type": "measure"},
            {"entity": "fact_customer_impact", "property": "Repeat Caller Rate",   "type": "measure"},
            {"entity": "fact_customer_impact", "property": "Avg Sentiment",        "type": "measure"},
            {"entity": "fact_customer_impact", "property": "Affected Customers",   "type": "measure"},
            {"entity": "dim_customer_segment", "property": "segment_name",         "type": "column"},
            {"entity": "dim_site",             "property": "region",               "type": "column"},
        ])))

    items.append(("v3_bar_seg", bar_chart(
        "v3_bar_seg", 445, 230, 815, 250,
        "dim_customer_segment", "segment_name",
        "fact_customer_impact", "Tickets Opened", "Tickets Opened", color_id=1)))

    # Row 3: Callout + Affected customers column
    items.append(("v3_callout", callout(
        "v3_callout", 20, 490, 415, 170,
        "Ask Copilot",
        [
            "- Which segment opened the most tickets?",
            "- Which provinces had the worst sentiment?",
            "- Where did affected customers spike?",
            "",
            "Continue in Teams via Rogers Network Data Agent",
        ])))

    items.append(("v3_col_aff", column_chart(
        "v3_col_aff", 445, 490, 815, 170,
        "dim_site", "region",
        "fact_customer_impact", "Affected Customers", "Affected Customers", color_id=2)))

    # Slicers
    items.append(("v3_sl_seg",    slicer("v3_sl_seg",    20, 670, 410, 38, "dim_customer_segment", "segment_name")))
    items.append(("v3_sl_region", slicer("v3_sl_region", 440, 670, 410, 38, "dim_site", "region")))
    items.append(("v3_sl_date",   slicer("v3_sl_date",   860, 670, 400, 38, "dim_date", "date_key")))

    return items


def b64(obj):
    return base64.b64encode(json.dumps(obj, indent=2).encode("utf-8")).decode("ascii")


def b64_str(s):
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def build_parts():
    parts = {
        ".platform":                                                  b64(PLATFORM),
        "definition.pbir":                                            b64(DEFINITION_PBIR),
        "definition/version.json":                                    b64(VERSION_JSON),
        "definition/report.json":                                     b64(REPORT_JSON),
        "definition/pages/pages.json":                                b64(PAGES_JSON),
        f"definition/pages/{PAGE1}/page.json":                        b64(page_json(PAGE1, "Network Health Overview")),
        f"definition/pages/{PAGE2}/page.json":                        b64(page_json(PAGE2, "Anomaly Deep-Dive")),
        f"definition/pages/{PAGE3}/page.json":                        b64(page_json(PAGE3, "Customer Impact")),
        "StaticResources/RegisteredResources/RogersNetwork.json":     b64(ROGERS_THEME),
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
        print("ERROR: stack_rogers.json is missing model_id - build the semantic model first.")
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
                "description": "Rogers Network Anomaly Copilot demo - 3 pages",
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
            (ROOT / "stack_rogers.json").write_text(json.dumps(STACK, indent=2))
            print(f"\nReport id: {item['id']}")
        print(f"Open: https://msit.powerbi.com/groups/{WS}/reports/{existing or STACK.get('report_id')}")
    elif s in (200, 201):
        print("  OK (sync)")
    else:
        print(f"  ERROR: {b[:1000]}")


if __name__ == "__main__":
    main()
