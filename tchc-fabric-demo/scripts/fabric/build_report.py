"""Build the TCHC arrears and vacancy Power BI report over the Direct Lake model.

    python scripts/fabric/build_report.py --output cicd/fabric-setup.output.json

Three pages, matching how the two use cases are actually governed:

  1. Arrears overview      - portfolio position, trend, aging, and where it concentrates
  2. Arrears deep dive     - by ward, tenure, unit size, and the accounts driving it
  3. Vacancy and turnaround- vacancy rate, revenue forgone, and turnaround performance

Built as PBIR (Enhanced Report Format) through the Fabric REST API. The visual helpers
are carried over from a working build unchanged; they encode PBIR quirks that are painful
to rediscover, notably that a dropdown slicer renders blank below about 48px.
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path

_parser = argparse.ArgumentParser()
_parser.add_argument("--output", default="cicd/fabric-setup.output.json")
_parser.add_argument("--name", default="TCHC_Arrears_and_Vacancy")
_args = _parser.parse_args()

STACK = json.loads(Path(_args.output).read_text(encoding="utf-8"))
WS = STACK["workspace"]["id"]
WS_NAME = STACK["workspace"]["displayName"]
MODEL = STACK["semanticModel"]["id"]
MODEL_NAME = STACK["semanticModel"]["name"]
AZ = "az"
API = "https://api.fabric.microsoft.com"
REPORT_NAME = _args.name

PAGE1 = "p" + uuid.uuid4().hex[:18]
PAGE2 = "p" + uuid.uuid4().hex[:18]
PAGE3 = "p" + uuid.uuid4().hex[:18]

# Civic palette: slate and teal carry the page, amber and red reserved for arrears
# severity so colour means something rather than decorating.
ROGERS_RED = "#B3423A"      # severity / over 90 days
NAVY = "#1F3243"            # primary text and structure
GRAY = "#64748B"
TEAL = "#2F6F6B"


def tok():
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", API,
         "--query", "accessToken", "-o", "tsv"],
        shell=True).decode().strip()


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

TCHC_THEME = {
    "name": "TCHCArrearsVacancy",
    "dataColors": [TEAL, NAVY, "#4E7A9B", "#C08A2E", ROGERS_RED,
                   "#6B8F71", "#8A6FA0", "#94A3B8"],
    "background": "#FFFFFF",
    "foreground": NAVY,
    "tableAccent": TEAL,
    "good": "#2F6F4F", "neutral": "#C08A2E", "bad": ROGERS_RED,
    "maximum": ROGERS_RED, "center": "#C08A2E", "minimum": "#2F6F4F",
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
            "name": "TCHCArrearsVacancy",
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
        "items": [{"name": "TCHCArrearsVacancy", "path": "TCHCArrearsVacancy.json",
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
                 "description": "TCHC arrears and vacancy over a Direct Lake semantic model. Synthetic data."},
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
        f"Toronto Community Housing | {page_label}", font_pt=16)))
    slide_visuals.append((f"v_sub_{safe}", title_visual(
        f"v_sub_{safe}", 20, 50, 1240, 24, subtitle,
        font_pt=10, bold=False, color=GRAY)))


# ---- Page 1: Arrears overview --------------------------------------------

def page1_visuals():
    items = []
    header_block(items, "Arrears overview",
                 "Rent charged against receipts applied, aged oldest-charge-first. "
                 "Synthetic data.")

    items.append(("v1_kpi_total", card_visual(
        "v1_kpi_total", 20, 86, 232, 96, "Arrears", "Total Arrears", "Total arrears")))
    items.append(("v1_kpi_rate", card_visual(
        "v1_kpi_rate", 264, 86, 232, 96, "Arrears", "Arrears Rate",
        "Households in arrears")))
    items.append(("v1_kpi_90", card_visual(
        "v1_kpi_90", 508, 86, 232, 96, "Arrears", "Arrears Over 90 Days",
        "Over 90 days")))
    items.append(("v1_kpi_coll", card_visual(
        "v1_kpi_coll", 752, 86, 232, 96, "Arrears", "Collection Rate",
        "Collection rate")))
    items.append(("v1_kpi_avg", card_visual(
        "v1_kpi_avg", 996, 86, 264, 96, "Arrears", "Average Arrears per Household",
        "Average per household")))

    items.append(("v1_trend", line_chart(
        "v1_trend", 20, 200, 720, 250, "Date", "month_name",
        "Arrears", "Total Arrears", "Total arrears", color_id=1)))

    items.append(("v1_aging", bar_chart(
        "v1_aging", 752, 200, 508, 250, "Arrears", "arrears_bucket",
        "Arrears", "Total Arrears", "Balance", chart="columnChart", color_id=2,
        sort_desc=False)))

    items.append(("v1_ward", bar_chart(
        "v1_ward", 20, 466, 620, 232, "Arrears", "ward_name",
        "Arrears", "Total Arrears", "Total arrears", color_id=1)))

    items.append(("v1_tenure", bar_chart(
        "v1_tenure", 652, 466, 300, 232, "Arrears", "tenure_type",
        "Arrears", "Total Arrears", "Total arrears", chart="columnChart", color_id=3)))

    items.append(("v1_note", callout(
        "v1_note", 964, 466, 296, 232, "How this is calculated",
        ["Receipts are applied to the oldest",
         "outstanding charge first, which is how",
         "a rent account actually settles.",
         "",
         "The aging bucket follows the oldest",
         "charge still carrying a balance, not",
         "the current month's payment."],
        accent=TEAL, bg="#F1F6F5")))
    return items


# ---- Page 2: Arrears deep dive -------------------------------------------

def page2_visuals():
    items = []
    header_block(items, "Arrears deep dive",
                 "Where the balance concentrates, and which accounts carry it.")

    items.append(("v2_slicer_region", slicer(
        "v2_slicer_region", 20, 88, 240, 48, "Arrears", "region")))
    items.append(("v2_slicer_tenure", slicer(
        "v2_slicer_tenure", 272, 88, 240, 48, "Arrears", "tenure_type")))
    items.append(("v2_slicer_size", slicer(
        "v2_slicer_size", 524, 88, 240, 48, "Arrears", "unit_size")))

    items.append(("v2_kpi_total", card_visual(
        "v2_kpi_total", 788, 88, 224, 96, "Arrears", "Total Arrears", "Total arrears")))
    items.append(("v2_kpi_hh", card_visual(
        "v2_kpi_hh", 1024, 88, 236, 96, "Arrears", "Households in Arrears",
        "Households in arrears")))

    items.append(("v2_size", bar_chart(
        "v2_size", 20, 200, 480, 240, "Arrears", "unit_size",
        "Arrears", "Total Arrears", "Total arrears", color_id=1)))

    items.append(("v2_income", bar_chart(
        "v2_income", 512, 200, 480, 240, "Household", "income_band",
        "Arrears", "Total Arrears", "Total arrears", color_id=4)))

    items.append(("v2_share", card_visual(
        "v2_share", 1004, 200, 256, 110, "Arrears", "Over 90 Day Share",
        "Share over 90 days")))
    items.append(("v2_mom", card_visual(
        "v2_mom", 1004, 326, 256, 114, "Arrears", "Arrears MoM Change",
        "Change vs prior month")))

    items.append(("v2_table", table_visual(
        "v2_table", 20, 456, 1240, 244, [
            {"type": "column", "entity": "Arrears", "property": "ward_name",
             "label": "Ward"},
            {"type": "column", "entity": "Arrears", "property": "tenure_type",
             "label": "Tenure"},
            {"type": "column", "entity": "Arrears", "property": "unit_size",
             "label": "Unit size"},
            {"type": "measure", "entity": "Arrears", "property": "Households Charged",
             "label": "Households"},
            {"type": "measure", "entity": "Arrears", "property": "Households in Arrears",
             "label": "In arrears"},
            {"type": "measure", "entity": "Arrears", "property": "Arrears Rate",
             "label": "Arrears rate"},
            {"type": "measure", "entity": "Arrears", "property": "Total Arrears",
             "label": "Balance"},
            {"type": "measure", "entity": "Arrears", "property": "Arrears Over 90 Days",
             "label": "Over 90 days"},
        ])))
    return items


# ---- Page 3: Vacancy and turnaround --------------------------------------

def page3_visuals():
    items = []
    header_block(items, "Vacancy and turnaround",
                 "Units held vacant, the rent that represents, and how long turnaround "
                 "takes.")

    items.append(("v3_kpi_vac", card_visual(
        "v3_kpi_vac", 20, 86, 236, 96, "UnitMonth", "Vacancy Rate", "Vacancy rate")))
    items.append(("v3_kpi_units", card_visual(
        "v3_kpi_units", 268, 86, 236, 96, "UnitMonth", "Units Vacant", "Units vacant")))
    items.append(("v3_kpi_rev", card_visual(
        "v3_kpi_rev", 516, 86, 236, 96, "UnitMonth", "Revenue Forgone",
        "Revenue forgone")))
    items.append(("v3_kpi_turn", card_visual(
        "v3_kpi_turn", 764, 86, 236, 96, "Turnaround", "Average Turnaround Days",
        "Avg turnaround days")))
    items.append(("v3_kpi_open", card_visual(
        "v3_kpi_open", 1012, 86, 248, 96, "Turnaround", "Turnarounds Open",
        "Turnarounds open")))

    items.append(("v3_trend", line_chart(
        "v3_trend", 20, 200, 720, 246, "Date", "month_name",
        "UnitMonth", "Units Vacant", "Units vacant", color_id=1)))

    items.append(("v3_cat", bar_chart(
        "v3_cat", 752, 200, 508, 246, "Turnaround", "turnaround_category",
        "Turnaround", "Average Turnaround Days", "Avg days",
        chart="columnChart", color_id=4)))

    items.append(("v3_region", bar_chart(
        "v3_region", 20, 462, 470, 238, "UnitMonth", "region",
        "UnitMonth", "Revenue Forgone", "Revenue forgone", color_id=2)))

    items.append(("v3_size", bar_chart(
        "v3_size", 502, 462, 458, 238, "UnitMonth", "unit_size",
        "UnitMonth", "Vacancy Rate", "Vacancy rate", chart="columnChart", color_id=3)))

    items.append(("v3_note", callout(
        "v3_note", 972, 462, 288, 238, "Open work orders",
        ["Average turnaround counts only",
         "completed work orders.",
         "",
         "An unfinished turnaround has an",
         "unknown duration, not a zero one,",
         "so it is reported separately rather",
         "than averaged in."],
        accent=TEAL, bg="#F1F6F5")))
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
        f"definition/pages/{PAGE1}/page.json":                        b64(page_json(PAGE1, "Arrears overview")),
        f"definition/pages/{PAGE2}/page.json":                        b64(page_json(PAGE2, "Arrears deep dive")),
        f"definition/pages/{PAGE3}/page.json":                        b64(page_json(PAGE3, "Vacancy and turnaround")),
        "StaticResources/RegisteredResources/TCHCArrearsVacancy.json": b64(TCHC_THEME),
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
                "description": "TCHC arrears and vacancy over a Direct Lake semantic model. Synthetic data.",
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
        print(f"Open: https://app.fabric.microsoft.com/groups/{WS}/reports/{existing or STACK.get('report_id')}")
    elif s in (200, 201):
        print("  OK (sync)")
    else:
        print(f"  ERROR: {b[:1000]}")


if __name__ == "__main__":
    main()
