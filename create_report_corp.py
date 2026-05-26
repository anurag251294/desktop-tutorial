"""Create InteracHR_Report bound to the hr_demo semantic model in corp tenant."""
from __future__ import annotations

import base64
import json
import subprocess
import time
import urllib.request
import urllib.error
import uuid

WORKSPACE_ID = "de6a7e47-474b-4354-87e7-26b8d741f015"
MODEL_ID     = "89782e0a-276b-4b86-a2d0-e8238d3c8791"   # hr_demo
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"


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


# --- PBIR parts ---
PLATFORM = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
    "metadata": {"type": "Report",
                 "displayName": "InteracHR_Report",
                 "description": "Interac HR demo report (corp)"},
    "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
}
DEFINITION_PBIR = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
    "version": "4.0",
    "datasetReference": {"byConnection": {"connectionString": f"semanticmodelid={MODEL_ID}"}},
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
    "pageOrder": ["exec_overview"],
    "activePageName": "exec_overview",
}
PAGE_JSON = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/1.0.0/schema.json",
    "name": "exec_overview",
    "displayName": "Exec Overview",
    "displayOption": "FitToPage",
    "height": 720, "width": 1280,
}


def card(name, measure, x, y):
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/1.0.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": 0, "height": 130, "width": 290, "tabOrder": 0},
        "visual": {
            "visualType": "card",
            "query": {"queryState": {"Values": {"projections": [{
                "field": {"Measure": {
                    "Expression": {"SourceRef": {"Entity": "fact_headcount_snapshot"}},
                    "Property": measure}},
                "queryRef": f"fact_headcount_snapshot.{measure}",
                "active": True}]}}}
        }
    }


CARDS = [
    ("card_active",      "Active Employees",   40,  40),
    ("card_attrition",   "Attrition Rate LTM", 340, 40),
    ("card_regrettable", "% Regrettable LTM",  640, 40),
    ("card_open_reqs",   "Open Reqs",          940, 40),
    ("card_tech",        "Tech Employees",     40,  200),
    ("card_pct_tech",    "% Tech",             340, 200),
    ("card_female",      "% Female",           640, 200),
    ("card_female_tech", "% Female (Tech)",    940, 200),
    ("card_avg_salary",  "Avg Base Salary",    40,  360),
    ("card_comp_ratio",  "Comp Ratio vs Market",340, 360),
    ("card_fintrac",     "FINTRAC Training Completion %", 640, 360),
    ("card_coi",         "COI Overdue 90+ Days",          940, 360),
]


def b64(obj):
    return base64.b64encode(json.dumps(obj, indent=2).encode("utf-8")).decode("ascii")


def main():
    parts = [
        {"path": ".platform",                                "payload": b64(PLATFORM),       "payloadType": "InlineBase64"},
        {"path": "definition.pbir",                          "payload": b64(DEFINITION_PBIR),"payloadType": "InlineBase64"},
        {"path": "definition/version.json",                  "payload": b64(VERSION_JSON),   "payloadType": "InlineBase64"},
        {"path": "definition/report.json",                   "payload": b64(REPORT_JSON),    "payloadType": "InlineBase64"},
        {"path": "definition/pages/pages.json",              "payload": b64(PAGES_JSON),     "payloadType": "InlineBase64"},
        {"path": "definition/pages/exec_overview/page.json", "payload": b64(PAGE_JSON),      "payloadType": "InlineBase64"},
    ]
    for nm, mz, x, y in CARDS:
        parts.append({"path": f"definition/pages/exec_overview/visuals/{nm}/visual.json",
                      "payload": b64(card(nm, mz, x, y)),
                      "payloadType": "InlineBase64"})

    print(f"Built {len(parts)} parts ({len(CARDS)} KPI cards)")
    body = {"displayName": "InteracHR_Report",
            "description": "Interac HR demo report",
            "type": "Report",
            "definition": {"format": "PBIR", "parts": parts}}

    print("POSTing /v1/workspaces/{ws}/items...")
    s, h, b = call("POST", f"{API}/v1/workspaces/{WORKSPACE_ID}/items", body=body)
    print(f"  status={s}")
    if s == 202:
        loc = h.get("Location") or h.get("location")
        ok, result_url = poll(loc)
        if ok:
            s2, h2, b2 = call("GET", result_url)
            item = json.loads(b2)
            print(f"\nReport created: id={item['id']}")
            print(f"Open: https://msit.powerbi.com/groups/{WORKSPACE_ID}/reports/{item['id']}")
        else:
            print("  creation FAILED")
    elif s in (200, 201):
        item = json.loads(b)
        print(f"\nReport (sync): id={item.get('id')}")
    else:
        print(f"  ERROR: {b[:800]}")


if __name__ == "__main__":
    main()
