"""Create Rogers_Network_Demo workspace on the existing corp Fabric trial capacity,
then a lakehouse inside it. Writes stack_rogers.json with all IDs.

Mirrors canadian_tire_demo/create_workspace_and_lakehouse.py.
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path

AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"

# Reuse the corp Fabric trial capacity (same one CTC + Interac demos used).
CAPACITY_ID = "fc2a4dac-2edb-4f33-9209-b0dac6a67c5d"
WS_NAME = "Rogers_Network_Demo"
LH_NAME = "rogers_lh"
OUT = Path(__file__).parent / "stack_rogers.json"


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
            print(f"  FAILED: {b[:600]}")
            return False, None
    return False, None


def find_workspace(name):
    s, h, b = call("GET", f"{API}/v1/workspaces")
    for ws in json.loads(b).get("value", []):
        if ws.get("displayName") == name:
            return ws.get("id")
    return None


def find_item(ws, kind, name):
    s, h, b = call("GET", f"{API}/v1/workspaces/{ws}/items?type={kind}")
    for it in json.loads(b).get("value", []):
        if it.get("displayName") == name:
            return it.get("id")
    return None


def main():
    print("Looking up existing workspace...")
    ws_id = find_workspace(WS_NAME)
    if ws_id:
        print(f"  Found existing: {ws_id}")
    else:
        print(f"  Creating workspace '{WS_NAME}'...")
        s, h, b = call("POST", f"{API}/v1/workspaces",
                       body={"displayName": WS_NAME,
                             "capacityId": CAPACITY_ID,
                             "description": "Rogers Network Anomaly Detection Copilot demo"})
        if s in (200, 201):
            ws_id = json.loads(b)["id"]
            print(f"  Created: {ws_id}")
        else:
            print(f"  ERROR {s}: {b[:600]}")
            return

    print(f"\nLooking up lakehouse {LH_NAME} in workspace...")
    lh_id = find_item(ws_id, "Lakehouse", LH_NAME)
    sql_cs = sql_id = None
    if lh_id:
        print(f"  Found existing lakehouse: {lh_id}")
    else:
        print(f"  Creating lakehouse '{LH_NAME}'...")
        s, h, b = call("POST", f"{API}/v1/workspaces/{ws_id}/lakehouses",
                       body={"displayName": LH_NAME,
                             "description": "Rogers RAN telemetry, alarms, traffic, customer-impact data"})
        if s == 202:
            loc = h.get("Location") or h.get("location")
            ok, result_url = poll(loc)
            if not ok:
                return
            s2, h2, b2 = call("GET", result_url)
            item = json.loads(b2)
            lh_id = item["id"]
        elif s in (200, 201):
            lh_id = json.loads(b)["id"]
        else:
            print(f"  ERROR {s}: {b[:600]}")
            return
        print(f"  Created: {lh_id}")

    print("\nFetching SQL endpoint...")
    s, h, b = call("GET", f"{API}/v1/workspaces/{ws_id}/lakehouses/{lh_id}")
    data = json.loads(b)
    sqlep = data.get("properties", {}).get("sqlEndpointProperties", {})
    sql_cs = sqlep.get("connectionString")
    sql_id = sqlep.get("id")
    print(f"  sql_cs={sql_cs}")
    print(f"  sql_id={sql_id}")

    stack = {
        "tenant": "microsoft.com",
        "capacity_id": CAPACITY_ID,
        "workspace_id": ws_id,
        "workspace_name": WS_NAME,
        "lakehouse_id": lh_id,
        "lakehouse_name": LH_NAME,
        "sql_endpoint_cs": sql_cs,
        "sql_endpoint_id": sql_id,
    }
    OUT.write_text(json.dumps(stack, indent=2))
    print(f"\nStack -> {OUT}")
    print(json.dumps(stack, indent=2))


if __name__ == "__main__":
    main()
