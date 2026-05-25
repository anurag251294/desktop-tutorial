"""Build CTC_Merch_Copilot_Demo report via Fabric API using the proven
PBIR schema versions from the working HR_demo_report.

Pattern: copy the EXACT structural files (definition.pbir, report.json,
version.json, page.json, theme.json) from the working HR_demo_report dump,
then drop in CTC-flavored visuals on a single page.
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

PAGE_ID = "p" + uuid.uuid4().hex[:18]
HR_DUMP = Path(r"C:\Users\anuragdhuria\interac_demo\report_current")


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


# ---- Schema templates (versions copied from the working HR_demo_report) -----

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
    "pageOrder": [PAGE_ID],
    "activePageName": PAGE_ID,
}

PAGE_JSON = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
    "name": PAGE_ID,
    "displayName": "Merch Overview",
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


# ---- Visual builders --------------------------------------------------------

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


def title_visual(name, x, y, w, h, text, font_pt=20, bold=True, color="#1B2C5C"):
    return {
        "$schema": VISUAL_SCHEMA,
        "name": name,
        "position": {"x": x, "y": y, "z": 0, "height": h, "width": w, "tabOrder": 0},
        "visual": {
            "visualType": "textbox",
            "drillFilterOtherVisuals": True,
            "objects": {
                "general": [{
                    "properties": {
                        "paragraphs": [{
                            "textRuns": [{
                                "value": text,
                                "textStyle": {
                                    "fontSize": f"{font_pt}pt",
                                    "fontWeight": "bold" if bold else "normal",
                                    "color": color,
                                },
                            }],
                        }],
                    },
                }],
            },
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
            "query": {
                "queryState": {
                    "Values": {
                        "projections": [{
                            "field": {
                                "Measure": {
                                    "Expression": {"SourceRef": {"Entity": entity}},
                                    "Property": measure_prop,
                                }
                            },
                            "queryRef": f"{entity}.{measure_prop}",
                            "nativeQueryRef": measure_prop,
                            "displayName": display_name,
                            "active": True,
                        }],
                    },
                },
            },
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


def bar_chart(name, x, y, w, h, cat_entity, cat_prop, meas_entity, meas_prop, meas_label, sort_desc=True):
    return {
        "$schema": VISUAL_SCHEMA,
        "name": name,
        "position": {"x": x, "y": y, "z": 2000, "height": h, "width": w, "tabOrder": 2000},
        "visual": {
            "visualType": "barChart",
            "drillFilterOtherVisuals": True,
            "query": {
                "queryState": {
                    "Category": {"projections": [{
                        "field": {"Column": {
                            "Expression": {"SourceRef": {"Entity": cat_entity}},
                            "Property": cat_prop}},
                        "queryRef": f"{cat_entity}.{cat_prop}",
                        "nativeQueryRef": cat_prop,
                        "active": True,
                    }]},
                    "Y": {"projections": [{
                        "field": {"Measure": {
                            "Expression": {"SourceRef": {"Entity": meas_entity}},
                            "Property": meas_prop}},
                        "queryRef": f"{meas_entity}.{meas_prop}",
                        "nativeQueryRef": meas_prop,
                        "displayName": meas_label,
                    }]},
                },
                "sortDefinition": {"sort": [{
                    "field": {"Measure": {
                        "Expression": {"SourceRef": {"Entity": meas_entity}},
                        "Property": meas_prop}},
                    "direction": "Descending" if sort_desc else "Ascending",
                }]},
            },
            "objects": {
                "labels": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}}}],
                "dataPoint": [{"properties": {"fill": {"solid": {"color": {
                    "expr": {"ThemeDataColor": {"ColorId": 1, "Percent": 0}}}}}}}],
            },
            "visualContainerObjects": visual_header_off(),
        },
    }


def column_chart(name, x, y, w, h, cat_entity, cat_prop, meas_entity, meas_prop, meas_label):
    v = bar_chart(name, x, y, w, h, cat_entity, cat_prop, meas_entity, meas_prop, meas_label)
    v["visual"]["visualType"] = "columnChart"
    v["visual"]["objects"]["dataPoint"] = [{"properties": {"fill": {"solid": {"color": {
        "expr": {"ThemeDataColor": {"ColorId": 2, "Percent": 0}}}}}}}]
    return v


def table_visual(name, x, y, w, h, fields):
    """fields: list of {entity, property, type=column|measure, label?}"""
    projections = []
    for f in fields:
        if f["type"] == "measure":
            field_ref = {"Measure": {
                "Expression": {"SourceRef": {"Entity": f["entity"]}},
                "Property": f["property"]}}
            qref = f"{f['entity']}.{f['property']}"
        else:
            field_ref = {"Column": {
                "Expression": {"SourceRef": {"Entity": f["entity"]}},
                "Property": f["property"]}}
            qref = f"{f['entity']}.{f['property']}"
        proj = {"field": field_ref, "queryRef": qref,
                "nativeQueryRef": f["property"]}
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
            "objects": {
                "values": [{"properties": {"fontSize": {"expr": {"Literal": {"Value": "9D"}}}}}],
            },
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
                "active": True,
            }]}}},
            "visualContainerObjects": visual_header_off(),
        },
    }


# ---- Page layout ------------------------------------------------------------

def build_visuals():
    """Return list of (visual_name, visual_json)."""
    items = []

    # Title bar
    items.append(("v_title", title_visual(
        "v_title", 20, 14, 1240, 56,
        "Canadian Tire - Merch Performance | Copilot in Power BI Demo",
        font_pt=18)))
    items.append(("v_subtitle", title_visual(
        "v_subtitle", 20, 56, 1240, 32,
        "Direct Lake on OneLake | SKU Performance, In-Season Demand, Connected Inventory",
        font_pt=10, bold=False, color="#5A6B82")))

    # KPI row: 4 cards
    items.append(("v_kpi_pos",   card_visual("v_kpi_pos",   20, 100, 295, 130,
                                              "fact_sku_performance", "POS $ TY",          "POS $ TY")))
    items.append(("v_kpi_egm",   card_visual("v_kpi_egm",  335, 100, 295, 130,
                                              "fact_sku_performance", "EGM $ TY",          "EGM $ TY")))
    items.append(("v_kpi_ls",    card_visual("v_kpi_ls",   650, 100, 295, 130,
                                              "fact_connected_inventory", "Avg Lost Sales %", "Lost Sales %")))
    items.append(("v_kpi_fr",    card_visual("v_kpi_fr",   965, 100, 295, 130,
                                              "fact_connected_inventory", "Avg Vendor Fill Rate %", "Vendor Fill Rate %")))

    # Bar: Top categories by POS $ TY
    items.append(("v_bar_cat", bar_chart(
        "v_bar_cat", 20, 250, 605, 220,
        "dim_sku", "Category",
        "fact_sku_performance", "POS $ TY", "POS $ TY")))

    # Column: Top finelines by EGM $ TY
    items.append(("v_col_fineline", column_chart(
        "v_col_fineline", 645, 250, 615, 220,
        "dim_sku", "Fineline_Name",
        "fact_sku_performance", "EGM $ TY", "EGM $ TY")))

    # Slicer: Category
    items.append(("v_slicer", slicer(
        "v_slicer", 20, 490, 230, 200,
        "dim_sku", "Category")))

    # Table: Top SKUs by POS, with margin/WoS/Fill Rate context
    items.append(("v_tbl", table_visual(
        "v_tbl", 270, 490, 990, 200,
        [
            {"entity": "dim_sku",                "property": "SKU_Name",        "type": "column", "label": "SKU Name"},
            {"entity": "dim_sku",                "property": "Fineline_Name",   "type": "column", "label": "Fineline"},
            {"entity": "fact_sku_performance",   "property": "POS $ TY",        "type": "measure", "label": "POS $ TY"},
            {"entity": "fact_sku_performance",   "property": "POS YoY %",       "type": "measure", "label": "POS YoY %"},
            {"entity": "fact_sku_performance",   "property": "EGM % TY",        "type": "measure", "label": "EGM %"},
            {"entity": "fact_in_season",         "property": "Avg Weeks of Supply", "type": "measure", "label": "WoS"},
            {"entity": "fact_connected_inventory", "property": "Avg Vendor Fill Rate %", "type": "measure", "label": "Fill Rate"},
        ])))

    return items


# ---- Theme ------------------------------------------------------------------

def theme_payload_b64():
    theme_src = HR_DUMP / "StaticResources__SharedResources__BaseThemes__CY26SU05.json"
    return base64.b64encode(theme_src.read_bytes()).decode("ascii")


def b64(obj):
    return base64.b64encode(json.dumps(obj, indent=2).encode("utf-8")).decode("ascii")


def build_parts():
    parts = {
        ".platform":                                                                                b64(PLATFORM),
        "definition.pbir":                                                                          b64(DEFINITION_PBIR),
        "definition/version.json":                                                                  b64(VERSION_JSON),
        "definition/report.json":                                                                   b64(REPORT_JSON),
        "definition/pages/pages.json":                                                              b64(PAGES_JSON),
        f"definition/pages/{PAGE_ID}/page.json":                                                    b64(PAGE_JSON),
        "StaticResources/SharedResources/BaseThemes/CY26SU05.json":                                 theme_payload_b64(),
    }
    for name, vj in build_visuals():
        parts[f"definition/pages/{PAGE_ID}/visuals/{name}/visual.json"] = b64(vj)
    return [{"path": p, "payload": pl, "payloadType": "InlineBase64"} for p, pl in parts.items()]


def main():
    parts = build_parts()
    print(f"Built {len(parts)} parts")
    for p in parts:
        decoded_len = len(base64.b64decode(p["payload"]))
        print(f"  {p['path']:<70s} ({decoded_len} bytes)")

    existing = find_report(REPORT_NAME)
    if existing:
        print(f"\nReport {REPORT_NAME} exists ({existing}) - updateDefinition...")
        s, h, b = call("POST",
                       f"{API}/v1/workspaces/{WS}/reports/{existing}/updateDefinition",
                       body={"definition": {"format": "PBIR", "parts": parts}})
    else:
        print(f"\nCreating report '{REPORT_NAME}'...")
        body = {"displayName": REPORT_NAME,
                "description": "CTC Merch Copilot demo report",
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
            print(f"Open: https://msit.powerbi.com/groups/{WS}/reports/{item['id']}")
    elif s in (200, 201):
        if not existing:
            try:
                item = json.loads(b)
                STACK["report_id"] = item.get("id")
                STACK["report_name"] = REPORT_NAME
                (ROOT / "stack_ctc.json").write_text(json.dumps(STACK, indent=2))
                print(f"\nReport id: {item.get('id')}")
            except Exception:
                pass
        else:
            print("  Update OK")
    else:
        print(f"  ERROR: {b[:1000]}")


if __name__ == "__main__":
    main()
