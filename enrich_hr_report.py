"""Enrich the working portal-created HR_demo_report by adding a new
'Copilot Showcase' page. Uses updateDefinition with the existing parts plus
the new page's parts.

The original page (created by the user via 'Quick Create' from dataset) is
left untouched - we just append a second page that demos KPI traffic-lights,
Smart Narrative, and Copilot prompt callouts.
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

WS = "de6a7e47-474b-4354-87e7-26b8d741f015"
REPORT_ID = "d28c79f7-5088-4d95-a3c6-c4a0dae093d9"  # HR_demo_report
MODEL_ID = "89782e0a-276b-4b86-a2d0-e8238d3c8791"   # hr_demo
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"

NEW_PAGE = "p" + uuid.uuid4().hex[:18]
VISUAL_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.10.0/schema.json"


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


def kpi_visual(name, x, y, w, h, ind_entity, ind_prop, goal_entity, goal_prop,
               trend_entity, trend_prop):
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
                        "Expression": {"SourceRef": {"Entity": ind_entity}},
                        "Property": ind_prop}},
                    "queryRef": f"{ind_entity}.{ind_prop}",
                    "nativeQueryRef": ind_prop,
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
        projections.append({"field": field_ref,
                            "queryRef": f"{f['entity']}.{f['property']}",
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


def callout(name, x, y, w, h, title, lines, accent="#F58220", bg="#FFF6EC"):
    paragraphs = [
        {"textRuns": [{"value": title, "textStyle": {
            "fontSize": "12pt", "fontWeight": "bold", "color": accent}}]}
    ]
    for ln in lines:
        paragraphs.append({"textRuns": [
            {"value": ln, "textStyle": {"fontSize": "10pt", "color": "#1B2C5C"}}]})
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
                    "show":  {"expr": {"Literal": {"Value": "true"}}}}}],
                "border": [{"properties": {
                    "color": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{accent}'"}}}}},
                    "show":  {"expr": {"Literal": {"Value": "true"}}}}}],
            },
            "visualContainerObjects": visual_header_off(),
        },
    }


def bar_chart(name, x, y, w, h, cat_entity, cat_prop, meas_entity, meas_prop, label,
              chart="barChart", color_id=1):
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
                        "displayName": label}]},
                },
                "sortDefinition": {"sort": [{
                    "field": {"Measure": {
                        "Expression": {"SourceRef": {"Entity": meas_entity}},
                        "Property": meas_prop}},
                    "direction": "Descending"}]},
            },
            "objects": {
                "labels": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}}}],
                "dataPoint": [{"properties": {"fill": {"solid": {"color": {
                    "expr": {"ThemeDataColor": {"ColorId": color_id, "Percent": 0}}}}}}}],
            },
            "visualContainerObjects": visual_header_off(),
        },
    }


# ---- New "Copilot Showcase" page --------------------------------------------

def new_page_visuals():
    items = []
    items.append(("hdr", title_visual("hdr", 20, 14, 1240, 38,
                  "Interac HR - Copilot Showcase", font_pt=18)))
    items.append(("sub", title_visual("sub", 20, 50, 1240, 24,
                  "Traffic-light KPIs | Smart Narrative | Copilot prompts | Data Agent in Teams",
                  font_pt=10, bold=False, color="#5A6B82")))

    # Row 1: 4 KPI visuals
    items.append(("kpi_hc", kpi_visual("kpi_hc", 20, 84, 295, 130,
                  "fact_headcount_snapshot", "Headcount vs Target",
                  "fact_headcount_snapshot", "Headcount Target",
                  "dim_date", "year_month")))
    items.append(("kpi_attr", kpi_visual("kpi_attr", 335, 84, 295, 130,
                  "fact_headcount_snapshot", "Attrition Rate vs Threshold",
                  "fact_headcount_snapshot", "Attrition Target",
                  "dim_date", "year_month")))
    items.append(("kpi_fin", kpi_visual("kpi_fin", 650, 84, 295, 130,
                  "fact_headcount_snapshot", "FINTRAC Training Compliance",
                  "fact_headcount_snapshot", "FINTRAC Training Target",
                  "dim_date", "year_month")))
    items.append(("kpi_coi", kpi_visual("kpi_coi", 965, 84, 295, 130,
                  "fact_headcount_snapshot", "COI Attestation Risk",
                  "fact_headcount_snapshot", "COI Overdue Target",
                  "dim_date", "year_month")))

    # Row 2: Smart Narrative (wide) + Callout
    items.append(("narr", smart_narrative("narr", 20, 230, 815, 250,
        [
            {"entity": "fact_headcount_snapshot", "property": "Active Employees",            "type": "measure"},
            {"entity": "fact_headcount_snapshot", "property": "Attrition Rate LTM",          "type": "measure"},
            {"entity": "fact_headcount_snapshot", "property": "Regrettable Attrition LTM",   "type": "measure"},
            {"entity": "fact_headcount_snapshot", "property": "FINTRAC Training Completion %", "type": "measure"},
            {"entity": "fact_headcount_snapshot", "property": "COI Overdue 90+ Days",        "type": "measure"},
            {"entity": "dim_department",          "property": "department_name",             "type": "column"},
            {"entity": "dim_department",          "property": "function",                    "type": "column"},
        ])))

    items.append(("callout", callout("callout", 845, 230, 415, 250,
        "🤖 Try these Copilot prompts",
        [
            "• Summarize this page",
            "• Which departments have COI overdue 90+ days?",
            "• FINTRAC training completion by function",
            "• Headcount vs target by department",
            "• What is the regrettable attrition rate?",
            "",
            "💬 Continue in Teams via",
            "   Interac HR Data Agent",
        ])))

    # Row 3: Bar chart (attrition by department) + Bar chart (training by function)
    items.append(("bar_attr", bar_chart("bar_attr", 20, 490, 815, 170,
        "dim_department", "department_name",
        "fact_headcount_snapshot", "Regrettable Attrition LTM",
        "Regrettable Attrition LTM", color_id=1)))

    items.append(("bar_fin", bar_chart("bar_fin", 845, 490, 415, 170,
        "dim_department", "function",
        "fact_headcount_snapshot", "FINTRAC Training Completion %",
        "FINTRAC %", color_id=3)))

    return items


def b64_obj(o):
    return base64.b64encode(json.dumps(o, indent=2).encode("utf-8")).decode("ascii")


def b64_str(s):
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def main():
    # 1. Fetch the current report definition (preserve everything we don't touch)
    print("Fetching current HR_demo_report definition...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/reports/{REPORT_ID}/getDefinition",
                   body={})
    if s == 202:
        loc = h.get("Location") or h.get("location")
        ok, result_url = poll(loc)
        if not ok:
            return
        sr, hr, br = call("GET", result_url)
        payload = json.loads(br)
    else:
        payload = json.loads(b)
    existing_parts = {p["path"]: p["payload"]
                      for p in payload.get("definition", {}).get("parts", [])}
    fmt = payload.get("definition", {}).get("format", "PBIR")
    print(f"  Loaded {len(existing_parts)} existing parts; format={fmt}")

    # 2. Update pages.json to append our new page
    pages_path = "definition/pages/pages.json"
    if pages_path in existing_parts:
        pages_meta = json.loads(base64.b64decode(existing_parts[pages_path]).decode("utf-8"))
    else:
        pages_meta = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json",
            "pageOrder": [], "activePageName": NEW_PAGE,
        }
    if NEW_PAGE not in pages_meta.get("pageOrder", []):
        pages_meta["pageOrder"] = pages_meta.get("pageOrder", []) + [NEW_PAGE]
    print(f"  Updated pageOrder: {pages_meta['pageOrder']}")
    existing_parts[pages_path] = b64_obj(pages_meta)

    # 3. Add new page.json
    new_page_json = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
        "name": NEW_PAGE,
        "displayName": "Copilot Showcase",
        "displayOption": "FitToPage",
        "height": 720, "width": 1280,
    }
    existing_parts[f"definition/pages/{NEW_PAGE}/page.json"] = b64_obj(new_page_json)

    # 4. Add new visuals
    for name, vj in new_page_visuals():
        existing_parts[f"definition/pages/{NEW_PAGE}/visuals/{name}/visual.json"] = b64_obj(vj)

    # 5. Push back
    payload_parts = [{"path": p, "payload": pl, "payloadType": "InlineBase64"}
                     for p, pl in existing_parts.items()]
    print(f"\nPOSTing updateDefinition with {len(payload_parts)} parts...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/reports/{REPORT_ID}/updateDefinition",
                   body={"definition": {"format": fmt, "parts": payload_parts}})
    print(f"  status={s}")
    if s == 202:
        loc = h.get("Location") or h.get("location")
        ok, _ = poll(loc)
        if ok:
            print(f"  OK -> https://msit.powerbi.com/groups/{WS}/reports/{REPORT_ID}")
        else:
            print("  update failed")
    elif s in (200, 201):
        print(f"  OK -> https://msit.powerbi.com/groups/{WS}/reports/{REPORT_ID}")
    else:
        print(f"  ERROR: {b[:1000]}")


if __name__ == "__main__":
    main()
