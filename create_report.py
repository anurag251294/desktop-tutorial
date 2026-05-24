"""Create a Power BI report bound to InteracHR_Model via Fabric API.

Uses the official PBIR enhanced format. Key bits learned from
https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report :
  - definition.pbir schema URL: definitionProperties/2.0.0
  - All other schemas under definition/ use the pattern:
      .../json-schemas/fabric/item/report/definition/<file>/<version>/schema.json
  - For Fabric REST API deployment, byConnection just needs:
      connectionString = "semanticmodelid=<model id>"
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

WORKSPACE_ID = "2690ef29-1370-476c-b28c-58a505fea2bd"
MODEL_ID = "00bb5cc7-20c0-4030-ae35-25a2ec02bc87"
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"


def token() -> str:
    return subprocess.check_output(
        [AZ, "account", "get-access-token",
         "--resource", API,
         "--query", "accessToken", "-o", "tsv"]
    ).decode().strip()


def call(method, url, body=None):
    headers = {"Authorization": f"Bearer {token()}",
               "ActivityId": str(uuid.uuid4()),
               "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, headers=headers, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def poll(loc):
    for i in range(60):
        time.sleep(2)
        sp, hp, bp = call("GET", loc)
        try:
            op = json.loads(bp)
            st = op.get("status")
        except Exception:
            st = None
        print(f"  poll {i+1}: status={st}")
        if st == "Succeeded":
            return True, loc.rstrip("/") + "/result"
        if st == "Failed":
            print(f"  FAILED: {bp[:800]}")
            return False, None
    return False, None


# -------- PBIR parts (correct schemas) --------

PLATFORM_JSON = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
    "metadata": {
        "type": "Report",
        "displayName": "InteracHR_Report",
        "description": "Interac HR Power BI demo report",
    },
    "config": {
        "version": "2.0",
        "logicalId": str(uuid.uuid4()),
    }
}

DEFINITION_PBIR = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
    "version": "4.0",
    "datasetReference": {
        "byConnection": {
            "connectionString": f"semanticmodelid={MODEL_ID}"
        }
    }
}

VERSION_JSON = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
    "version": "4.0.0",
}

REPORT_JSON = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/1.0.0/schema.json",
    "themeCollection": {
        "baseTheme": {
            "name": "CY24SU10",
            "reportVersionAtImport": "5.55",
            "type": "SharedResources",
        }
    },
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
    "height": 720,
    "width": 1280,
}


def make_card_visual(name, display_name, measure_name, x, y):
    """KPI card bound to a measure (measures live on fact_headcount_snapshot)."""
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/1.0.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": 0, "height": 120, "width": 280, "tabOrder": 0},
        "visual": {
            "visualType": "card",
            "query": {
                "queryState": {
                    "Values": {
                        "projections": [{
                            "field": {
                                "Measure": {
                                    "Expression": {"SourceRef": {"Entity": "fact_headcount_snapshot"}},
                                    "Property": measure_name
                                }
                            },
                            "queryRef": f"fact_headcount_snapshot.{measure_name}",
                            "active": True
                        }]
                    }
                }
            }
        }
    }


KPI_CARDS = [
    ("card_active",       "Active Employees",    "Active Employees",   40,  40),
    ("card_attrition",    "Attrition Rate LTM",  "Attrition Rate LTM", 340, 40),
    ("card_regrettable",  "% Regrettable LTM",   "% Regrettable LTM",  640, 40),
    ("card_open_reqs",    "Open Reqs",           "Open Reqs",          940, 40),
]


def b64(obj):
    return base64.b64encode(json.dumps(obj, indent=2).encode("utf-8")).decode("ascii")


def build_parts():
    parts = [
        {"path": ".platform",                                "payload": b64(PLATFORM_JSON),   "payloadType": "InlineBase64"},
        {"path": "definition.pbir",                          "payload": b64(DEFINITION_PBIR), "payloadType": "InlineBase64"},
        {"path": "definition/version.json",                  "payload": b64(VERSION_JSON),    "payloadType": "InlineBase64"},
        {"path": "definition/report.json",                   "payload": b64(REPORT_JSON),     "payloadType": "InlineBase64"},
        {"path": "definition/pages/pages.json",              "payload": b64(PAGES_JSON),      "payloadType": "InlineBase64"},
        {"path": "definition/pages/exec_overview/page.json", "payload": b64(PAGE_JSON),       "payloadType": "InlineBase64"},
    ]
    for name, label, measure, x, y in KPI_CARDS:
        visual = make_card_visual(name, label, measure, x, y)
        parts.append({
            "path": f"definition/pages/exec_overview/visuals/{name}/visual.json",
            "payload": b64(visual),
            "payloadType": "InlineBase64",
        })
    return parts


def main():
    parts = build_parts()
    print(f"Built {len(parts)} parts:")
    for p in parts:
        print(f"  {p['path']}")

    body = {
        "displayName": "InteracHR_Report",
        "description": "Interac HR Power BI demo report (scaffold via API)",
        "type": "Report",
        "definition": {"format": "PBIR", "parts": parts},
    }

    print("\nPOSTing items endpoint...")
    s, h, b = call("POST", f"{API}/v1/workspaces/{WORKSPACE_ID}/items", body=body)
    print(f"  status={s}")
    if s == 202:
        loc = h.get("Location") or h.get("location")
        print(f"  polling {loc}")
        ok, result_url = poll(loc)
        if ok:
            s2, h2, b2 = call("GET", result_url)
            try:
                item = json.loads(b2)
                print(f"\nReport created: id={item.get('id')}")
                print(f"Open at: https://app.powerbi.com/groups/{WORKSPACE_ID}/reports/{item.get('id')}")
            except Exception:
                print(f"  result body: {b2[:500]}")
        else:
            print("  creation FAILED")
    elif s in (200, 201):
        try:
            item = json.loads(b)
            print(f"\nReport (sync): id={item.get('id')}")
        except Exception:
            print(f"  body: {b[:500]}")
    else:
        print(f"  ERROR: {b[:1200]}")


if __name__ == "__main__":
    main()
