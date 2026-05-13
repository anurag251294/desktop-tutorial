"""Rebuild the MLJ Real-Time Dashboard with the correct v3 schema.

Schema requirements (from the validator):
- dataSources[].kind must be "kusto-trident" for Fabric Eventhouse
- dataSources[] requires: id (UUID), name, scopeId, kind, clusterUri, database, workspace
- Top-level /queries array with each query having {id, text, dataSource}
- /tiles use queryRef (not inline query)
- /pages must not have displayName, only id + name
"""
import subprocess, json, base64, urllib.request, time, sys, io, uuid
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def sh(c): return subprocess.check_output(c, shell=True).decode().strip()

with open(r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_ctx.json") as f:
    C = json.load(f)
WS = C["workspace_id"]
DB = C["kql_db_name"]
DBID = C["kql_db_id"]
QURI = C["kql_query_uri"]
DASH_ID = C.get("rt_dashboard_id")
TOKEN = sh("az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv")

def fab(method, url, body=None, timeout=180):
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    req = urllib.request.Request(url, data=data, method=method,
                                  headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, {k.lower():v for k,v in r.headers.items()}, r.read().decode() if r.status != 202 else ""
    except urllib.error.HTTPError as e:
        return e.code, {k.lower():v for k,v in (e.headers.items() if e.headers else [])}, e.read().decode()

def wait_op(op):
    for _ in range(80):
        time.sleep(3)
        _, _, b = fab("GET", f"https://api.fabric.microsoft.com/v1/operations/{op}")
        s = json.loads(b)
        if s.get("status") in ("Succeeded","Failed"): return s

# Build the dashboard payload
ds_id = str(uuid.uuid4())
page_id = str(uuid.uuid4())

TILE_DEFS = [
    # (title, kql, vis, x, y, w, h)
    ("Events per minute (last 1h)",
     "transaction_events_rt | where EventTime > ago(1h) | summarize Events = count() by bin(EventTime, 1m) | render timechart",
     "line", 0, 0, 8, 5),
    ("Alert level distribution (24h)",
     "transaction_events_rt | where EventTime > ago(24h) | summarize Count = count() by AlertLevel",
     "pie", 8, 0, 4, 5),
    ("AML review queue (latest 20)",
     "transaction_events_rt | where AlertLevel == 'REVIEW' | top 20 by EventTime desc | project EventTime, EventType, CustomerId, BranchOffice, Amount, Notes",
     "table", 0, 5, 12, 6),
    ("Transaction value by branch (24h)",
     "transaction_events_rt | where EventTime > ago(24h) and Amount > 0 | summarize TotalAmount = sum(Amount) by BranchOffice | top 10 by TotalAmount desc",
     "bar", 0, 11, 6, 5),
    ("Events by prefecture (24h)",
     "transaction_events_rt | where EventTime > ago(24h) | summarize Events = count() by Prefecture | order by Events desc",
     "column", 6, 11, 6, 5),
    ("Failed logins last hour",
     "transaction_events_rt | where EventTime > ago(1h) and EventType == 'FailedLogin' | summarize FailedLogins = count() by CustomerId | top 20 by FailedLogins desc",
     "table", 0, 16, 12, 5),
]

queries = []
tiles = []
for title, kql, vis, x, y, w, h in TILE_DEFS:
    qid = str(uuid.uuid4())
    queries.append({
        "id": qid,
        "text": kql,
        "dataSource": {
            "kind": "inline",
            "dataSourceId": ds_id
        },
        "usedVariables": []
    })
    tiles.append({
        "id": str(uuid.uuid4()),
        "title": title,
        "pageId": page_id,
        "layout": {"x": x, "y": y, "width": w, "height": h},
        "queryRef": {"kind": "query", "queryId": qid},
        "visualType": vis,
        "visualOptions": {}
    })

dashboard_def = {
    "$schema": "https://kusto.azurewebsites.net/RTD/Schemas/dashboard/v3.0.0/schema.json",
    "id": str(uuid.uuid4()),
    "schema_version": "55",
    "title": "MLJ Real-Time Operations",
    "autoRefresh": {
        "enabled": True,
        "defaultInterval": "1m",
        "minInterval": "30s"
    },
    "dataSources": [{
        "id": ds_id,
        "name": DB,
        "scopeId": "kusto",
        "kind": "kusto-trident",
        "clusterUri": QURI,
        "database": DBID,
        "workspace": WS
    }],
    "baseQueries": [],
    "parameters": [],
    "pages": [{
        "id": page_id,
        "name": "Live AML & Activity"
    }],
    "queries": queries,
    "tiles": tiles
}

# Push via updateDefinition to the existing dashboard
print(f"== Updating dashboard {DASH_ID} ==")
parts = [{
    "path": "RealTimeDashboard.json",
    "payload": base64.b64encode(json.dumps(dashboard_def, indent=2).encode("utf-8")).decode(),
    "payloadType": "InlineBase64"
}]

s, h, b = fab("POST", f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/kqlDashboards/{DASH_ID}/updateDefinition",
              {"definition": {"parts": parts}})
print(f"  HTTP {s}: {b[:400]}")
if s == 202:
    op = h.get("x-ms-operation-id")
    res = wait_op(op)
    print(f"  status: {res.get('status')}")
    if res.get("status") == "Failed":
        print(f"  err: {res}")
elif s == 200:
    print("  OK")
else:
    print(f"  full body: {b}")

print(f"\n== Dashboard URL ==")
print(f"  https://app.fabric.microsoft.com/groups/{WS}/kqlDashboards/{DASH_ID}")
