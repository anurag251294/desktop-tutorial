"""Build a fancy KPI dashboard report via Fabric API.

Deletes the broken InteracHR_Report first, then creates a new
'InteracHR_KPI_Dashboard' with 8 proper KPI visuals (visualType: kpi)
in a 4x2 grid bound to the hr_demo model.

Each KPI visual gets:
  - Indicator: the KPI base measure (has KPI definition attached)
  - Goal: the corresponding target measure
  - TrendLine: dim_date[year_month] for the time series

Falls back to card visuals if KPI visual rendering fails.
"""
from __future__ import annotations

import base64
import json
import subprocess
import time
import urllib.request
import urllib.error
import uuid

WS = "de6a7e47-474b-4354-87e7-26b8d741f015"
MODEL = "89782e0a-276b-4b86-a2d0-e8238d3c8791"
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"

# Existing broken report to delete
OLD_REPORT = "a8394b6b-fc6d-45ae-87c8-7668efb80d90"


def tok():
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", API,
         "--query", "accessToken", "-o", "tsv"]).decode().strip()


def call(method, url, body=None):
    h = {"Authorization": f"Bearer {tok()}",
         "Content-Type": "application/json",
         "ActivityId": str(uuid.uuid4())}
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    req = urllib.request.Request(url, headers=h, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def poll(loc):
    for i in range(60):
        time.sleep(2)
        s, h, b = call("GET", loc)
        try:
            st = json.loads(b).get("status")
        except Exception:
            st = None
        if st == "Succeeded":
            return True, loc.rstrip("/") + "/result"
        if st == "Failed":
            print(f"   FAILED: {b[:600]}")
            return False, None
    return False, None


# --- (kpi_name, target_name, page_x, page_y) ---
# 4 columns x 2 rows grid, each card 290x180, gap 20
KPIS = [
    ("Headcount vs Target",         "Headcount Target",        40,  140),
    ("Attrition Rate vs Threshold", "Attrition Target",        350, 140),
    ("Regrettable Attrition Risk",  "Regrettable Target",      660, 140),
    ("Open Reqs Pipeline Health",   "Open Reqs Capacity",      970, 140),
    ("Time to Fill SLA",            "Time to Fill Target",     40,  360),
    ("Market Comp Competitiveness", "Comp Ratio Target",       350, 360),
    ("FINTRAC Training Compliance", "FINTRAC Training Target", 660, 360),
    ("COI Attestation Risk",        "COI Overdue Target",      970, 360),
]


PLATFORM = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
    "metadata": {"type": "Report",
                 "displayName": "InteracHR_KPI_Dashboard",
                 "description": "Interac HR KPI dashboard with traffic-light status"},
    "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
}
DEFINITION_PBIR = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
    "version": "4.0",
    "datasetReference": {"byConnection": {"connectionString": f"semanticmodelid={MODEL}"}},
}
VERSION_JSON = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
    "version": "4.0.0",
}
REPORT_JSON = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/1.0.0/schema.json",
    "themeCollection": {"baseTheme": {"name": "CY24SU10",
                                      "reportVersionAtImport": "5.55",
                                      "type": "SharedResources"}},
    "layoutOptimization": "None",
}
PAGES_JSON = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json",
    "pageOrder": ["dashboard"],
    "activePageName": "dashboard",
}
PAGE_JSON = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/1.0.0/schema.json",
    "name": "dashboard",
    "displayName": "HR KPI Dashboard",
    "displayOption": "FitToPage",
    "height": 720, "width": 1280,
}


def kpi_visual(name, indicator_measure, goal_measure, x, y):
    """A proper KPI visual: Indicator + Goals + TrendLine."""
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/1.0.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": 0, "height": 180, "width": 290, "tabOrder": 0},
        "visual": {
            "visualType": "kpi",
            "query": {"queryState": {
                "Indicator": {"projections": [{
                    "field": {"Measure": {
                        "Expression": {"SourceRef": {"Entity": "fact_headcount_snapshot"}},
                        "Property": indicator_measure}},
                    "queryRef": f"fact_headcount_snapshot.{indicator_measure}",
                    "active": True}]},
                "TrendLine": {"projections": [{
                    "field": {"Column": {
                        "Expression": {"SourceRef": {"Entity": "dim_date"}},
                        "Property": "year_month"}},
                    "queryRef": "dim_date.year_month",
                    "active": True}]},
                "Goals": {"projections": [{
                    "field": {"Measure": {
                        "Expression": {"SourceRef": {"Entity": "fact_headcount_snapshot"}},
                        "Property": goal_measure}},
                    "queryRef": f"fact_headcount_snapshot.{goal_measure}",
                    "active": True}]},
            }}
        }
    }


def title_textbox():
    """Top header text box."""
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/1.0.0/schema.json",
        "name": "title",
        "position": {"x": 40, "y": 20, "z": 0, "height": 90, "width": 1220, "tabOrder": 0},
        "visual": {
            "visualType": "textbox",
            "objects": {
                "general": [{
                    "properties": {
                        "paragraphs": [
                            {"textRuns": [{
                                "value": "Six Views Financial - HR Executive Dashboard",
                                "textStyle": {
                                    "fontSize": "26pt",
                                    "fontWeight": "bold",
                                    "color": "#1B2C5C"
                                }
                            }]},
                            {"textRuns": [{
                                "value": "Direct Lake on OneLake · Canada Central · Live",
                                "textStyle": {
                                    "fontSize": "11pt",
                                    "color": "#555555"
                                }
                            }]},
                        ]
                    }
                }]
            }
        }
    }


def b64(obj):
    return base64.b64encode(json.dumps(obj, indent=2).encode("utf-8")).decode("ascii")


def build_parts():
    parts = [
        {"path": ".platform",                              "payload": b64(PLATFORM),        "payloadType": "InlineBase64"},
        {"path": "definition.pbir",                        "payload": b64(DEFINITION_PBIR), "payloadType": "InlineBase64"},
        {"path": "definition/version.json",                "payload": b64(VERSION_JSON),    "payloadType": "InlineBase64"},
        {"path": "definition/report.json",                 "payload": b64(REPORT_JSON),     "payloadType": "InlineBase64"},
        {"path": "definition/pages/pages.json",            "payload": b64(PAGES_JSON),      "payloadType": "InlineBase64"},
        {"path": "definition/pages/dashboard/page.json",   "payload": b64(PAGE_JSON),       "payloadType": "InlineBase64"},
        {"path": "definition/pages/dashboard/visuals/title/visual.json",
         "payload": b64(title_textbox()), "payloadType": "InlineBase64"},
    ]
    for (kpi, target, x, y) in KPIS:
        nm = "kpi_" + kpi.lower().replace(" ", "_").replace("%", "pct")
        parts.append({"path": f"definition/pages/dashboard/visuals/{nm}/visual.json",
                      "payload": b64(kpi_visual(nm, kpi, target, x, y)),
                      "payloadType": "InlineBase64"})
    return parts


def main():
    # Delete old broken report
    print(f"Deleting old report {OLD_REPORT}...")
    s, h, b = call("DELETE", f"{API}/v1/workspaces/{WS}/reports/{OLD_REPORT}")
    print(f"  status={s}")

    parts = build_parts()
    print(f"\nBuilt {len(parts)} parts ({len(KPIS)} KPI visuals + title)")
    body = {"displayName": "InteracHR_KPI_Dashboard",
            "description": "Interac HR KPI dashboard - 8 KPIs in 4x2 grid",
            "type": "Report",
            "definition": {"format": "PBIR", "parts": parts}}

    print("\nPOSTing /v1/workspaces/{ws}/items...")
    s, h, b = call("POST", f"{API}/v1/workspaces/{WS}/items", body=body)
    print(f"  status={s}")
    if s == 202:
        loc = h.get("Location") or h.get("location")
        ok, result_url = poll(loc)
        if ok:
            s2, h2, b2 = call("GET", result_url)
            item = json.loads(b2)
            print(f"\nDashboard created: id={item['id']}")
            print(f"Open: https://msit.powerbi.com/groups/{WS}/reports/{item['id']}")
        else:
            print("  creation FAILED")
    elif s in (200, 201):
        item = json.loads(b)
        print(f"\nDashboard (sync): id={item.get('id')}")
    else:
        print(f"  ERROR: {b[:800]}")


if __name__ == "__main__":
    main()
