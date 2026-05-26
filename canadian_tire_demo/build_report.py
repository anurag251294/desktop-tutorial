"""Build the polished CTC_Merch_Copilot_Demo report - 3 pages:
  1. Merch Overview - hero KPIs, Smart Narrative, top categories/finelines, top SKUs
  2. In-Season Demand vs Supply - POS vs Ship, scatter WoS x Lost Sales, inventory
  3. Connected Inventory Health - lost sales, fill rate, vendor performance

Uses the proven PBIR schema versions from the working HR_demo_report dump.
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
STACK = json.loads((ROOT / "stack_ctc.json").read_text())
WS = STACK["workspace_id"]
MODEL = STACK["model_id"]
WS_NAME = STACK["workspace_name"]
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"
REPORT_NAME = "CTC_Merch_Copilot_Demo"
HR_DUMP = Path(r"C:\Users\anuragdhuria\interac_demo\report_current")

PAGE1 = "p" + uuid.uuid4().hex[:18]
PAGE2 = "p" + uuid.uuid4().hex[:18]
PAGE3 = "p" + uuid.uuid4().hex[:18]


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
    for i in range(90):
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


def find_report(name):
    s, h, b = call("GET", f"{API}/v1/workspaces/{WS}/reports")
    for it in json.loads(b).get("value", []):
        if it.get("displayName") == name:
            return it.get("id")
    return None


# ---- Top-level files --------------------------------------------------------

DEFINITION_PBIR = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
    "version": "4.0",
    "datasetReference": {
        "byConnection": {
            "connectionString": (
                f"Data Source=powerbi://api.powerbi.com/v1.0/myorg/{WS_NAME};"
                f"initial catalog=ctc_merch;integrated security=ClaimsToken;"
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
            "name": "CY26SU05",
            "reportVersionAtImport": {"visual": "2.9.0", "report": "3.3.0", "page": "2.3.1"},
            "type": "SharedResources",
        }
    },
    "objects": {
        "section": [{"properties": {"verticalAlignment": {"expr": {"Literal": {"Value": "'Top'"}}}}}],
        "outspacePane": [{"properties": {"expanded": {"expr": {"Literal": {"Value": "false"}}}}}],
    },
    "reportSource": "QuickCreate",
    "resourcePackages": [{"name": "SharedResources", "type": "SharedResources",
                          "items": [{"name": "CY26SU05", "path": "BaseThemes/CY26SU05.json",
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
                 "description": "Canadian Tire Merch Copilot demo - SKU performance, in-season demand, connected inventory"},
    "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
}

VISUAL_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.10.0/schema.json"


# ---- Visual builders --------------------------------------------------------

def visual_header_off():
    return {"visualHeader": [
        {"properties": {
            "showCopyVisualImageButton": {"expr": {"Literal": {"Value": "false"}}},
            "showFilterRestatementButton": {"expr": {"Literal": {"Value": "false"}}},
            "showFocusModeButton":       {"expr": {"Literal": {"Value": "false"}}},
            "showPinButton":             {"expr": {"Literal": {"Value": "false"}}},
        }}
    ]}


def title_visual(name, x, y, w, h, text, font_pt=20, bold=True, color="#1B2C5C"):
    return {
        "$schema": VISUAL_SCHEMA,
        "name": name,
        "position": {"x": x, "y": y, "z": 0, "height": h, "width": w, "tabOrder": 0},
        "visual": {
            "visualType": "textbox",
            "drillFilterOtherVisuals": True,
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
        "$schema": VISUAL_SCHEMA,
        "name": name,
        "position": {"x": x, "y": y, "z": 1000, "height": h, "width": w, "tabOrder": 1000},
        "visual": {
            "visualType": "card",
            "drillFilterOtherVisuals": True,
            "query": {"queryState": {"Values": {"projections": [{
                "field": {"Measure": {
                    "Expression": {"SourceRef": {"Entity": entity}},
                    "Property": measure_prop}},
                "queryRef": f"{entity}.{measure_prop}",
                "nativeQueryRef": measure_prop,
                "displayName": display_name,
                "active": True}]}}},
            "objects": {
                "labels": [{"properties": {
                    "fontSize": {"expr": {"Literal": {"Value": "26D"}}},
                    "color":    {"solid": {"color": {"expr": {"Literal": {"Value": "'#1B2C5C'"}}}}},
                }}],
                "categoryLabels": [{"properties": {
                    "fontSize": {"expr": {"Literal": {"Value": "11D"}}},
                    "color":    {"solid": {"color": {"expr": {"Literal": {"Value": "'#5A6B82'"}}}}},
                }}],
            },
            "visualContainerObjects": visual_header_off(),
        },
    }


def bar_chart(name, x, y, w, h, cat_entity, cat_prop, meas_entity, meas_prop, meas_label,
              chart="barChart", color_id=1, sort_desc=True):
    return {
        "$schema": VISUAL_SCHEMA,
        "name": name,
        "position": {"x": x, "y": y, "z": 2000, "height": h, "width": w, "tabOrder": 2000},
        "visual": {
            "visualType": chart,
            "drillFilterOtherVisuals": True,
            "query": {
                "queryState": {
                    "Category": {"projections": [{
                        "field": {"Column": {
                            "Expression": {"SourceRef": {"Entity": cat_entity}},
                            "Property": cat_prop}},
                        "queryRef": f"{cat_entity}.{cat_prop}",
                        "nativeQueryRef": cat_prop,
                        "active": True}]},
                    "Y": {"projections": [{
                        "field": {"Measure": {
                            "Expression": {"SourceRef": {"Entity": meas_entity}},
                            "Property": meas_prop}},
                        "queryRef": f"{meas_entity}.{meas_prop}",
                        "nativeQueryRef": meas_prop,
                        "displayName": meas_label}]},
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


def scatter(name, x, y, w, h, details_entity, details_prop,
            x_entity, x_prop, x_label, y_entity, y_prop, y_label):
    return {
        "$schema": VISUAL_SCHEMA,
        "name": name,
        "position": {"x": x, "y": y, "z": 2500, "height": h, "width": w, "tabOrder": 2500},
        "visual": {
            "visualType": "scatterChart",
            "drillFilterOtherVisuals": True,
            "query": {"queryState": {
                "Details": {"projections": [{
                    "field": {"Column": {
                        "Expression": {"SourceRef": {"Entity": details_entity}},
                        "Property": details_prop}},
                    "queryRef": f"{details_entity}.{details_prop}",
                    "nativeQueryRef": details_prop,
                    "active": True}]},
                "X": {"projections": [{
                    "field": {"Measure": {
                        "Expression": {"SourceRef": {"Entity": x_entity}},
                        "Property": x_prop}},
                    "queryRef": f"{x_entity}.{x_prop}",
                    "nativeQueryRef": x_prop,
                    "displayName": x_label}]},
                "Y": {"projections": [{
                    "field": {"Measure": {
                        "Expression": {"SourceRef": {"Entity": y_entity}},
                        "Property": y_prop}},
                    "queryRef": f"{y_entity}.{y_prop}",
                    "nativeQueryRef": y_prop,
                    "displayName": y_label}]},
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
        "$schema": VISUAL_SCHEMA,
        "name": name,
        "position": {"x": x, "y": y, "z": 3000, "height": h, "width": w, "tabOrder": 3000},
        "visual": {
            "visualType": "tableEx",
            "drillFilterOtherVisuals": True,
            "query": {"queryState": {"Values": {"projections": projections}}},
            "objects": {"values": [{"properties": {"fontSize": {"expr": {"Literal": {"Value": "9D"}}}}}]},
            "visualContainerObjects": visual_header_off(),
        },
    }


def slicer(name, x, y, w, h, entity, prop):
    return {
        "$schema": VISUAL_SCHEMA,
        "name": name,
        "position": {"x": x, "y": y, "z": 500, "height": h, "width": w, "tabOrder": 500},
        "visual": {
            "visualType": "slicer",
            "drillFilterOtherVisuals": True,
            "query": {"queryState": {"Values": {"projections": [{
                "field": {"Column": {
                    "Expression": {"SourceRef": {"Entity": entity}},
                    "Property": prop}},
                "queryRef": f"{entity}.{prop}",
                "nativeQueryRef": prop,
                "active": True}]}}},
            "visualContainerObjects": visual_header_off(),
        },
    }


def smart_narrative(name, x, y, w, h, fields):
    """Smart Narrative auto-generated text visual (Copilot demo feature)."""
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
        "$schema": VISUAL_SCHEMA,
        "name": name,
        "position": {"x": x, "y": y, "z": 4000, "height": h, "width": w, "tabOrder": 4000},
        "visual": {
            "visualType": "textInsights",
            "drillFilterOtherVisuals": True,
            "query": {"queryState": {"Values": {"projections": projections}}},
            "visualContainerObjects": visual_header_off(),
        },
    }


def kpi_visual(name, x, y, w, h, indicator_entity, indicator_prop,
               goal_entity, goal_prop, trend_entity, trend_prop):
    """Traffic-light KPI visual: Indicator + Goal + TrendLine."""
    return {
        "$schema": VISUAL_SCHEMA,
        "name": name,
        "position": {"x": x, "y": y, "z": 1500, "height": h, "width": w, "tabOrder": 1500},
        "visual": {
            "visualType": "kpi",
            "drillFilterOtherVisuals": True,
            "query": {"queryState": {
                "Indicator": {"projections": [{
                    "field": {"Measure": {
                        "Expression": {"SourceRef": {"Entity": indicator_entity}},
                        "Property": indicator_prop}},
                    "queryRef": f"{indicator_entity}.{indicator_prop}",
                    "nativeQueryRef": indicator_prop,
                    "active": True}]},
                "TrendLine": {"projections": [{
                    "field": {"Column": {
                        "Expression": {"SourceRef": {"Entity": trend_entity}},
                        "Property": trend_prop}},
                    "queryRef": f"{trend_entity}.{trend_prop}",
                    "nativeQueryRef": trend_prop,
                    "active": True}]},
                "Goals": {"projections": [{
                    "field": {"Measure": {
                        "Expression": {"SourceRef": {"Entity": goal_entity}},
                        "Property": goal_prop}},
                    "queryRef": f"{goal_entity}.{goal_prop}",
                    "nativeQueryRef": goal_prop}]},
            }},
            "visualContainerObjects": visual_header_off(),
        },
    }


def callout(name, x, y, w, h, title, lines, accent="#CA1A22", bg="#FFF6F6"):
    """Bordered text callout - used for 'Try these Copilot prompts' style boxes."""
    paragraphs = [
        {"textRuns": [{"value": title,
                       "textStyle": {"fontSize": "12pt", "fontWeight": "bold",
                                     "color": accent}}]}
    ]
    for ln in lines:
        paragraphs.append({"textRuns": [
            {"value": ln,
             "textStyle": {"fontSize": "10pt", "color": "#1B2C5C"}}]})
    return {
        "$schema": VISUAL_SCHEMA,
        "name": name,
        "position": {"x": x, "y": y, "z": 4500, "height": h, "width": w, "tabOrder": 4500},
        "visual": {
            "visualType": "textbox",
            "drillFilterOtherVisuals": True,
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
    """Title row at top of every page."""
    slide_visuals.append((f"v_hdr_{page_label}", title_visual(
        f"v_hdr_{page_label}", 20, 14, 1240, 38,
        f"Canadian Tire - Merch Performance | {page_label}", font_pt=16)))
    slide_visuals.append((f"v_sub_{page_label}", title_visual(
        f"v_sub_{page_label}", 20, 50, 1240, 24, subtitle,
        font_pt=10, bold=False, color="#5A6B82")))


# ---- Page 1: Merch Overview -------------------------------------------------

def page1_visuals():
    items = []
    header_block(items, "Overview",
                 "Direct Lake on OneLake | Sales x Profitability x Inventory | Copilot consumer demo")

    # Row 1: 4 KPI visuals with traffic-light status (using new KPI measures)
    items.append(("v1_kpi_pos", kpi_visual("v1_kpi_pos", 20, 84, 295, 130,
                                            "fact_sku_performance", "POS YoY KPI",
                                            "fact_sku_performance", "POS YoY Target",
                                            "dim_date", "Year_Month")))
    items.append(("v1_kpi_egm", kpi_visual("v1_kpi_egm", 335, 84, 295, 130,
                                            "fact_sku_performance", "EGM % KPI",
                                            "fact_sku_performance", "EGM Target",
                                            "dim_date", "Year_Month")))
    items.append(("v1_kpi_ls",  kpi_visual("v1_kpi_ls", 650, 84, 295, 130,
                                            "fact_connected_inventory", "Lost Sales KPI",
                                            "fact_connected_inventory", "Lost Sales Threshold",
                                            "dim_date", "Year_Month")))
    items.append(("v1_kpi_fr",  kpi_visual("v1_kpi_fr", 965, 84, 295, 130,
                                            "fact_connected_inventory", "Fill Rate KPI",
                                            "fact_connected_inventory", "Fill Rate Target",
                                            "dim_date", "Year_Month")))

    # Row 2 - Smart Narrative (left) + Bar (right)
    items.append(("v1_narr1", smart_narrative(
        "v1_narr1", 20, 230, 415, 200,
        [
            {"entity": "fact_sku_performance",   "property": "POS $ TY",      "type": "measure"},
            {"entity": "fact_sku_performance",   "property": "POS YoY %",     "type": "measure"},
            {"entity": "fact_sku_performance",   "property": "EGM $ TY",      "type": "measure"},
            {"entity": "fact_sku_performance",   "property": "EGM % TY",      "type": "measure"},
            {"entity": "dim_sku",                "property": "Category",      "type": "column"},
            {"entity": "dim_sku",                "property": "Fineline_Name", "type": "column"},
        ])))

    # Copilot prompt callout
    items.append(("v1_callout", callout(
        "v1_callout", 20, 440, 415, 220,
        "🤖 Try these Copilot prompts",
        [
            "• Summarize this page",
            "• Top 10 SKUs by EGM dollars",
            "• Compare Air Fryers vs Cookware Sets",
            "• SKUs with WoS > 18 but lost sales < 2%",
            "• Which new SKUs are growing but supply-constrained?",
            "",
            "💬 Also available in Teams via",
            "   CTC Merch Data Agent",
        ])))

    items.append(("v1_bar_cat", bar_chart(
        "v1_bar_cat", 445, 230, 815, 200,
        "dim_sku", "Category",
        "fact_sku_performance", "POS $ TY", "POS $ TY")))

    items.append(("v1_col_fl", column_chart(
        "v1_col_fl", 445, 440, 815, 220,
        "dim_sku", "Fineline_Name",
        "fact_sku_performance", "EGM $ TY", "EGM $ TY")))

    # Slicers row at very bottom
    items.append(("v1_sl_cat", slicer("v1_sl_cat", 20, 670, 410, 38, "dim_sku", "Category")))
    items.append(("v1_sl_vendor", slicer("v1_sl_vendor", 440, 670, 410, 38, "dim_sku", "Vendor")))
    items.append(("v1_sl_new", slicer("v1_sl_new", 860, 670, 400, 38, "dim_sku", "New_SKU_Flag")))

    return items


# ---- Page 2: In-Season Demand vs Supply ------------------------------------

def page2_visuals():
    items = []
    header_block(items, "In-Season Demand vs Supply",
                 "POS vs Shipments | Weeks of Supply | Overstock and understock signals")

    # Row 1: 1 traffic-light KPI (WoS) + 3 cards
    items.append(("v2_kpi_wos", kpi_visual("v2_kpi_wos", 20, 84, 295, 130,
                                            "fact_in_season", "WoS KPI",
                                            "fact_in_season", "WoS Target",
                                            "dim_date", "Year_Month")))
    items.append(("v2_kpi_pos", card_visual("v2_kpi_pos", 335, 84, 295, 130,
                                            "fact_in_season", "POS Units YTD TY",
                                            "POS Units YTD")))
    items.append(("v2_kpi_ship", card_visual("v2_kpi_ship", 650, 84, 295, 130,
                                             "fact_in_season", "Ship Units YTD TY",
                                             "Ship Units YTD")))
    items.append(("v2_kpi_over", card_visual("v2_kpi_over", 965, 84, 295, 130,
                                             "fact_in_season", "# SKUs Overstock (WoS>18)",
                                             "# SKUs Overstock (WoS>18)")))

    # Row 2: Narrative (left) + scatter (right)
    items.append(("v2_narr", smart_narrative(
        "v2_narr", 20, 230, 415, 250,
        [
            {"entity": "fact_in_season",         "property": "POS Units YTD TY",     "type": "measure"},
            {"entity": "fact_in_season",         "property": "Ship Units YTD TY",    "type": "measure"},
            {"entity": "fact_in_season",         "property": "Demand vs Supply Gap", "type": "measure"},
            {"entity": "fact_in_season",         "property": "Avg Weeks of Supply",  "type": "measure"},
            {"entity": "fact_in_season",         "property": "# SKUs Overstock (WoS>18)", "type": "measure"},
            {"entity": "fact_in_season",         "property": "# SKUs Understock (WoS<4)", "type": "measure"},
            {"entity": "dim_sku",                "property": "Category",       "type": "column"},
        ])))

    items.append(("v2_scatter", scatter(
        "v2_scatter", 445, 230, 815, 250,
        "dim_sku", "SKU_Name",
        "fact_in_season", "Avg Weeks of Supply", "Weeks of Supply",
        "fact_connected_inventory", "Avg Lost Sales %", "Lost Sales %")))

    # Row 3: Callout (left) + Inventory column (right)
    items.append(("v2_callout", callout(
        "v2_callout", 20, 490, 415, 170,
        "🤖 Ask Copilot",
        [
            "• Which SKUs have WoS > 18 but lost sales < 2%?",
            "• Show inventory by category",
            "• Where is supply running ahead of demand?",
            "",
            "💬 Continue in Teams via CTC Merch Data Agent",
        ])))

    items.append(("v2_col_inv", column_chart(
        "v2_col_inv", 445, 490, 815, 170,
        "dim_sku", "Category",
        "fact_in_season", "Total Inventory (units)", "Total Inventory (units)", color_id=3)))

    # Slicers
    items.append(("v2_sl_cat", slicer("v2_sl_cat", 20, 670, 410, 38, "dim_sku", "Category")))
    items.append(("v2_sl_fl",  slicer("v2_sl_fl",  440, 670, 410, 38, "dim_sku", "Fineline_Name")))
    items.append(("v2_sl_v",   slicer("v2_sl_v",   860, 670, 400, 38, "dim_sku", "Vendor")))

    return items


# ---- Page 3: Connected Inventory Health ------------------------------------

def page3_visuals():
    items = []
    header_block(items, "Connected Inventory Health",
                 "Lost Sales | Vendor Fill Rate | R8 sales velocity | Supply-risk SKUs")

    # Row 1: 2 traffic-light KPIs + 2 count cards
    items.append(("v3_kpi_ls",   kpi_visual("v3_kpi_ls", 20, 84, 295, 130,
                                              "fact_connected_inventory", "Lost Sales KPI",
                                              "fact_connected_inventory", "Lost Sales Threshold",
                                              "dim_date", "Year_Month")))
    items.append(("v3_kpi_fr",   kpi_visual("v3_kpi_fr", 335, 84, 295, 130,
                                              "fact_connected_inventory", "Fill Rate KPI",
                                              "fact_connected_inventory", "Fill Rate Target",
                                              "dim_date", "Year_Month")))
    items.append(("v3_kpi_lsc",  card_visual("v3_kpi_lsc", 650, 84, 295, 130,
                                              "fact_connected_inventory", "# SKUs Lost Sales >5%",
                                              "# SKUs Lost Sales >5%")))
    items.append(("v3_kpi_frc",  card_visual("v3_kpi_frc", 965, 84, 295, 130,
                                              "fact_connected_inventory", "# SKUs Fill Rate <85%",
                                              "# SKUs Fill Rate <85%")))

    # Row 2: Narrative (left) + Bar (right)
    items.append(("v3_narr", smart_narrative(
        "v3_narr", 20, 230, 415, 250,
        [
            {"entity": "fact_connected_inventory", "property": "Avg Lost Sales %",       "type": "measure"},
            {"entity": "fact_connected_inventory", "property": "Avg Vendor Fill Rate %", "type": "measure"},
            {"entity": "fact_connected_inventory", "property": "R8 POS YoY %",           "type": "measure"},
            {"entity": "fact_connected_inventory", "property": "# SKUs Lost Sales >5%",  "type": "measure"},
            {"entity": "fact_connected_inventory", "property": "# SKUs Fill Rate <85%",  "type": "measure"},
            {"entity": "dim_sku",                  "property": "Vendor",                 "type": "column"},
            {"entity": "dim_vendor",               "property": "Scorecard_Tier",         "type": "column"},
        ])))

    items.append(("v3_bar_fr", bar_chart(
        "v3_bar_fr", 445, 230, 815, 250,
        "dim_sku", "Vendor",
        "fact_connected_inventory", "Avg Vendor Fill Rate %", "Vendor Fill Rate %",
        sort_desc=False, color_id=4)))

    # Row 3: Callout (left) + Column R8 (right)
    items.append(("v3_callout", callout(
        "v3_callout", 20, 490, 415, 170,
        "🤖 Ask Copilot",
        [
            "• SKUs with lost sales > 5% AND fill rate < 85%",
            "• Which vendors have the worst fill rate?",
            "• Where is R8 sales velocity accelerating?",
            "",
            "💬 Continue in Teams via CTC Merch Data Agent",
        ])))

    items.append(("v3_col_r8", column_chart(
        "v3_col_r8", 445, 490, 815, 170,
        "dim_sku", "Fineline_Name",
        "fact_connected_inventory", "R8 POS YoY %", "R8 POS YoY %", color_id=5)))

    # Slicers
    items.append(("v3_sl_v",   slicer("v3_sl_v",   20, 670, 410, 38, "dim_sku", "Vendor")))
    items.append(("v3_sl_cat", slicer("v3_sl_cat", 440, 670, 410, 38, "dim_sku", "Category")))
    items.append(("v3_sl_new", slicer("v3_sl_new", 860, 670, 400, 38, "dim_sku", "New_SKU_Flag")))

    return items


# ---- Assemble ---------------------------------------------------------------

def theme_payload_b64():
    theme_src = HR_DUMP / "StaticResources__SharedResources__BaseThemes__CY26SU05.json"
    return base64.b64encode(theme_src.read_bytes()).decode("ascii")


def b64(obj):
    return base64.b64encode(json.dumps(obj, indent=2).encode("utf-8")).decode("ascii")


def build_parts():
    parts = {
        ".platform":                                                  b64(PLATFORM),
        "definition.pbir":                                            b64(DEFINITION_PBIR),
        "definition/version.json":                                    b64(VERSION_JSON),
        "definition/report.json":                                     b64(REPORT_JSON),
        "definition/pages/pages.json":                                b64(PAGES_JSON),
        f"definition/pages/{PAGE1}/page.json":                        b64(page_json(PAGE1, "Merch Overview")),
        f"definition/pages/{PAGE2}/page.json":                        b64(page_json(PAGE2, "In-Season Demand vs Supply")),
        f"definition/pages/{PAGE3}/page.json":                        b64(page_json(PAGE3, "Connected Inventory Health")),
        "StaticResources/SharedResources/BaseThemes/CY26SU05.json":   theme_payload_b64(),
    }
    for name, vj in page1_visuals():
        parts[f"definition/pages/{PAGE1}/visuals/{name}/visual.json"] = b64(vj)
    for name, vj in page2_visuals():
        parts[f"definition/pages/{PAGE2}/visuals/{name}/visual.json"] = b64(vj)
    for name, vj in page3_visuals():
        parts[f"definition/pages/{PAGE3}/visuals/{name}/visual.json"] = b64(vj)
    return [{"path": p, "payload": pl, "payloadType": "InlineBase64"} for p, pl in parts.items()]


def main():
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
                "description": "CTC Merch Copilot demo report - 3 pages",
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
            (ROOT / "stack_ctc.json").write_text(json.dumps(STACK, indent=2))
            print(f"\nReport id: {item['id']}")
        print(f"Open: https://msit.powerbi.com/groups/{WS}/reports/{existing or STACK.get('report_id')}")
    elif s in (200, 201):
        print("  OK (sync)")
    else:
        print(f"  ERROR: {b[:1000]}")


if __name__ == "__main__":
    main()
