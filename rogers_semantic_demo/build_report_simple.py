"""Simplified single-page Rogers Finance ARPU demo report.

Layout (1280x720, fit-to-page):
  - Rogers-red header band (full width)
  - Row of 4 KPI cards (ARPU, Revenue, Avg Subs, ARPU YoY %)
  - One big visual (ARPU trend by month, Rogers red line, 12 months)
  - AI narrative on the right
  - Two slicers below (Product, Month)

Replaces the existing Rogers_Finance_ARPU_Demo report in-place.
"""
from __future__ import annotations

import base64, json, subprocess, time, urllib.request, urllib.error, uuid
from pathlib import Path

ROOT = Path(__file__).parent
STACK = json.loads((ROOT / "stack_finance.json").read_text())
WS = STACK["workspace_id"]
MODEL = STACK["model_id"]
WS_NAME = STACK["workspace_name"]
MODEL_NAME = STACK.get("model_name", "rogers_finance")
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"
REPORT_NAME = "Rogers_Finance_ARPU_Demo"
PAGE = "p" + uuid.uuid4().hex[:18]

# ---- Rogers brand palette -----------------------------------------------
ROGERS_RED = "#DA291C"
ROGERS_RED_DARK = "#A8221A"
NAVY = "#1B2C5C"
GRAY = "#5A6B82"
LIGHT_GRAY = "#E5E7EB"
WHITE = "#FFFFFF"


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


# ---- Rogers theme -------------------------------------------------------

ROGERS_THEME = {
    "name": "RogersBranded",
    "dataColors": [ROGERS_RED, NAVY, "#22A06B", ROGERS_RED_DARK,
                   "#F5A623", "#7C3AED", "#0EA5E9", "#6B7280"],
    "background": WHITE,
    "foreground": NAVY,
    "tableAccent": ROGERS_RED,
    "good": "#22A06B", "neutral": "#F5A623", "bad": ROGERS_RED,
    "maximum": ROGERS_RED, "center": "#F5A623", "minimum": "#22A06B",
    "null": "#9CA3AF",
    "textClasses": {
        "title":   {"fontSize": 20, "color": NAVY, "fontFace": "Segoe UI Semibold"},
        "header":  {"fontSize": 13, "color": NAVY, "fontFace": "Segoe UI Semibold"},
        "label":   {"fontSize": 11, "color": NAVY, "fontFace": "Segoe UI"},
        "callout": {"fontSize": 36, "color": ROGERS_RED, "fontFace": "Segoe UI Semibold"},
    },
}

# ---- Top-level files ----------------------------------------------------

DEFINITION_PBIR = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
    "version": "4.0",
    "datasetReference": {"byConnection": {
        "connectionString": (
            f"Data Source=powerbi://api.powerbi.com/v1.0/myorg/{WS_NAME};"
            f"initial catalog={MODEL_NAME};integrated security=ClaimsToken;"
            f"semanticmodelid={MODEL}"
        )
    }},
}

VERSION_JSON = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
    "version": "2.0.0",
}

REPORT_JSON = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.3.0/schema.json",
    "themeCollection": {"baseTheme": {
        "name": "RogersBranded",
        "reportVersionAtImport": {"visual": "2.9.0", "report": "3.3.0", "page": "2.3.1"},
        "type": "RegisteredResources",
    }},
    "objects": {
        "section":      [{"properties": {"verticalAlignment": {"expr": {"Literal": {"Value": "'Top'"}}}}}],
        "outspacePane": [{"properties": {"expanded": {"expr": {"Literal": {"Value": "false"}}}}}],
    },
    "reportSource": "QuickCreate",
    "resourcePackages": [{
        "name": "RegisteredResources", "type": "RegisteredResources",
        "items": [{"name": "RogersBranded", "path": "RogersBranded.json", "type": "BaseTheme"}],
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
    "pageOrder": [PAGE],
    "activePageName": PAGE,
}

PAGE_JSON = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
    "name": PAGE, "displayName": "Finance ARPU",
    "displayOption": "FitToPage", "height": 720, "width": 1280,
}

PLATFORM = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
    "metadata": {"type": "Report", "displayName": REPORT_NAME,
                 "description": "Rogers Enterprise Semantic Layer - Finance ARPU one-page demo"},
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


def color_expr(hex_color):
    return {"solid": {"color": {"expr": {"Literal": {"Value": f"'{hex_color}'"}}}}}


def textbox(name, x, y, w, h, text, font_pt=14, bold=False, color=None, bg=None):
    color = color or NAVY
    para = {"textRuns": [{"value": text, "textStyle": {
        "fontSize": f"{font_pt}pt",
        "fontWeight": "bold" if bold else "normal",
        "color": color}}]}
    obj = {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": x, "y": y, "z": 0, "height": h, "width": w, "tabOrder": 0},
        "visual": {
            "visualType": "textbox", "drillFilterOtherVisuals": True,
            "objects": {"general": [{"properties": {"paragraphs": [para]}}]},
            "visualContainerObjects": visual_header_off(),
        },
    }
    if bg:
        obj["visual"]["objects"].setdefault("background", []).append(
            {"properties": {"color": color_expr(bg),
                            "show": {"expr": {"Literal": {"Value": "true"}}}}})
    return obj


def card(name, x, y, w, h, entity, measure, label):
    return {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": x, "y": y, "z": 1000, "height": h, "width": w, "tabOrder": 1000},
        "visual": {
            "visualType": "card", "drillFilterOtherVisuals": True,
            "query": {"queryState": {"Values": {"projections": [{
                "field": {"Measure": {
                    "Expression": {"SourceRef": {"Entity": entity}},
                    "Property": measure}},
                "queryRef": f"{entity}.{measure}",
                "nativeQueryRef": measure,
                "displayName": label, "active": True}]}}},
            "objects": {
                "labels": [{"properties": {
                    "fontSize": {"expr": {"Literal": {"Value": "36D"}}},
                    "color":    color_expr(ROGERS_RED),
                    "fontFamily": {"expr": {"Literal": {"Value": "'Segoe UI Semibold'"}}},
                }}],
                "categoryLabels": [{"properties": {
                    "fontSize": {"expr": {"Literal": {"Value": "12D"}}},
                    "color":    color_expr(GRAY),
                }}],
                "background": [{"properties": {
                    "color": color_expr(WHITE),
                    "show":  {"expr": {"Literal": {"Value": "true"}}},
                }}],
                "border": [{"properties": {
                    "color": color_expr(LIGHT_GRAY),
                    "show":  {"expr": {"Literal": {"Value": "true"}}},
                    "radius": {"expr": {"Literal": {"Value": "4D"}}},
                }}],
            },
            "visualContainerObjects": visual_header_off(),
        },
    }


def line_visual(name, x, y, w, h, cat_entity, cat_prop, meas_entity, meas_prop, label):
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
                "title": [{"properties": {
                    "show": {"expr": {"Literal": {"Value": "true"}}},
                    "text": {"expr": {"Literal": {"Value": f"'{label}'"}}},
                    "fontColor": color_expr(NAVY),
                    "fontSize": {"expr": {"Literal": {"Value": "14D"}}},
                }}],
                "labels": [{"properties": {
                    "show": {"expr": {"Literal": {"Value": "true"}}},
                    "color": color_expr(NAVY)}}],
                "dataPoint": [{"properties": {"fill": {"solid": {"color": {
                    "expr": {"Literal": {"Value": f"'{ROGERS_RED}'"}}}}}}}],
                "lineStyles": [{"properties": {
                    "strokeWidth": {"expr": {"Literal": {"Value": "3D"}}},
                    "showMarker": {"expr": {"Literal": {"Value": "true"}}}}}],
                "markers": [{"properties": {
                    "show": {"expr": {"Literal": {"Value": "true"}}},
                    "size": {"expr": {"Literal": {"Value": "6D"}}}}}],
                "background": [{"properties": {
                    "color": color_expr(WHITE),
                    "show":  {"expr": {"Literal": {"Value": "true"}}},
                }}],
                "border": [{"properties": {
                    "color": color_expr(LIGHT_GRAY),
                    "show":  {"expr": {"Literal": {"Value": "true"}}},
                    "radius": {"expr": {"Literal": {"Value": "4D"}}},
                }}],
            },
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
            "objects": {
                "background": [{"properties": {
                    "color": color_expr(WHITE),
                    "show":  {"expr": {"Literal": {"Value": "true"}}},
                }}],
                "border": [{"properties": {
                    "color": color_expr(ROGERS_RED),
                    "show":  {"expr": {"Literal": {"Value": "true"}}},
                    "radius": {"expr": {"Literal": {"Value": "4D"}}},
                }}],
            },
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


# ---- Page layout --------------------------------------------------------

def page_visuals():
    items = []

    # Rogers-red header band
    items.append(("v_band", textbox(
        "v_band", 0, 0, 1280, 60, " ", bg=ROGERS_RED)))
    items.append(("v_title", textbox(
        "v_title", 24, 12, 800, 32,
        "Rogers Finance  -  Certified ARPU",
        font_pt=18, bold=True, color=WHITE)))
    items.append(("v_subtitle", textbox(
        "v_subtitle", 24, 36, 800, 22,
        "One semantic model. Same number everywhere.",
        font_pt=10, color="#FFD9D5")))

    # 4 KPI cards (y=80, height=140, total width 1232, gap 16)
    cw, gap = 296, 16
    x0 = 24
    items.append(("v_card_arpu",
        card("v_card_arpu", x0,                   80, cw, 140, "Revenue", "ARPU",                "ARPU (certified)")))
    items.append(("v_card_rev",
        card("v_card_rev",  x0 + (cw + gap),      80, cw, 140, "Revenue", "Revenue (Millions)",  "Revenue (M)")))
    items.append(("v_card_subs",
        card("v_card_subs", x0 + 2 * (cw + gap),  80, cw, 140, "Revenue", "Average Subscribers", "Avg Subscribers")))
    items.append(("v_card_yoy",
        card("v_card_yoy",  x0 + 3 * (cw + gap),  80, cw, 140, "Revenue", "ARPU YoY %",          "ARPU YoY")))

    # Big visual: ARPU trend line (left 2/3) - y=240, height=380
    items.append(("v_line", line_visual(
        "v_line", 24, 240, 820, 380,
        "Date", "Month", "Revenue", "ARPU",
        "ARPU trend - last 24 months")))

    # AI narrative (right 1/3)
    items.append(("v_narr", smart_narrative(
        "v_narr", 860, 240, 396, 380,
        [
            {"entity": "Revenue", "property": "ARPU",                "type": "measure"},
            {"entity": "Revenue", "property": "Revenue",             "type": "measure"},
            {"entity": "Revenue", "property": "ARPU YoY %",          "type": "measure"},
            {"entity": "Revenue", "property": "Revenue YoY %",       "type": "measure"},
            {"entity": "Revenue", "property": "Average Subscribers", "type": "measure"},
            {"entity": "Date",    "property": "Month",               "type": "column"},
            {"entity": "Product", "property": "Product Name",        "type": "column"},
            {"entity": "Region",  "property": "Region Name",         "type": "column"},
        ])))

    # Slicers - product (left) and month (right), bottom row
    items.append(("v_sl_prod",  slicer("v_sl_prod",  24,  640, 600, 56, "Product", "Product Name")))
    items.append(("v_sl_month", slicer("v_sl_month", 640, 640, 616, 56, "Date",    "Month")))

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
        f"definition/pages/{PAGE}/page.json":                         b64(PAGE_JSON),
        "StaticResources/RegisteredResources/RogersBranded.json":     b64(ROGERS_THEME),
    }
    for name, vj in page_visuals():
        parts[f"definition/pages/{PAGE}/visuals/{name}/visual.json"] = b64(vj)
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
                "description": "Rogers Enterprise Semantic Layer - simplified ARPU demo",
                "type": "Report",
                "definition": {"format": "PBIR", "parts": parts}}
        s, h, b = call("POST", f"{API}/v1/workspaces/{WS}/items", body=body)
    print(f"  status={s}")
    if s == 202:
        loc = h.get("Location") or h.get("location")
        ok, _ = poll(loc)
        if not ok:
            return
        rid = existing or find_report(REPORT_NAME)
        print(f"Open: https://msit.powerbi.com/groups/{WS}/reports/{rid}")
    elif s in (200, 201):
        print("  OK (sync)")
    else:
        print(f"  ERROR: {b[:1000]}")


if __name__ == "__main__":
    main()
