"""Create the MLJ Real-Time Dashboard with 6 tiles + count verification."""
import subprocess, json, urllib.request, time, sys, io, base64
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def sh(c): return subprocess.check_output(c, shell=True).decode().strip()

with open(r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_ctx.json") as f:
    C = json.load(f)
WS = C["workspace_id"]; EH = C["eventhouse_id"]; DB = C["kql_db_name"]; DBID = C["kql_db_id"]
QURI = C["kql_query_uri"]
TOKEN = sh("az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv")
KTOKEN = sh(f"az account get-access-token --resource {QURI} --query accessToken -o tsv")

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

def kusto(query, mgmt=False):
    url = QURI + ("/v1/rest/mgmt" if mgmt else "/v2/rest/query")
    body = json.dumps({"db": DB, "csl": query}).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                  headers={"Authorization": f"Bearer {KTOKEN}",
                                           "Content-Type":"application/json; charset=utf-8",
                                           "Accept":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

# --- 1. Verify count ---
print("== Verifying transaction_events_rt count ==")
s, b = kusto("transaction_events_rt | count")
# Parse "PrimaryResult" rows
try:
    data = json.loads(b)
    # Find DataTable with TableKind=PrimaryResult
    for tbl in data:
        if tbl.get("TableKind") == "PrimaryResult" or (tbl.get("FrameType")=="DataTable" and tbl.get("TableName")=="PrimaryResult"):
            rows = tbl.get("Rows", [])
            if rows: print(f"  Total events: {rows[0][0]:,}")
            break
except Exception as e:
    print(f"  parse: {b[:300]}")

# Quick aggregations
for label, q in [
    ("Alert level distribution", "transaction_events_rt | summarize Count=count() by AlertLevel | order by Count desc"),
    ("Last 1h events", "transaction_events_rt | where EventTime > ago(1h) | count"),
    ("Top 5 branches by amount", "transaction_events_rt | where Amount > 0 | summarize Total=sum(Amount) by BranchOffice | top 5 by Total desc"),
]:
    s, b = kusto(q)
    try:
        d = json.loads(b)
        for tbl in d:
            if tbl.get("TableKind") == "PrimaryResult":
                print(f"\n  {label}:")
                for col, row in zip([tbl.get("Columns",[])], tbl.get("Rows",[])):
                    pass
                cols = [c["ColumnName"] for c in tbl.get("Columns",[])]
                for r in tbl.get("Rows",[])[:10]:
                    print(f"    {dict(zip(cols, r))}")
                break
    except Exception as e:
        print(f"  err: {e}")

# --- 2. Build Real-Time Dashboard ---
# Dashboard JSON schema for Fabric Real-Time Dashboards
print("\n\n== Building Real-Time Dashboard JSON ==")
TILES = [
    ("Events per minute (last 1h)",
     "transaction_events_rt | where EventTime > ago(1h) | summarize Events = count() by bin(EventTime, 1m) | render timechart",
     "Line"),
    ("Alert level distribution (24h)",
     "transaction_events_rt | where EventTime > ago(24h) | summarize Count = count() by AlertLevel",
     "Pie"),
    ("Top 10 review-level events (latest)",
     "transaction_events_rt | where AlertLevel == 'REVIEW' | top 10 by EventTime desc | project EventTime, EventType, CustomerId, BranchOffice, Amount, Notes",
     "Table"),
    ("Transaction value by branch (24h)",
     "transaction_events_rt | where EventTime > ago(24h) and Amount > 0 | summarize TotalAmount = sum(Amount) by BranchOffice | top 10 by TotalAmount desc",
     "Column"),
    ("Events by prefecture (24h)",
     "transaction_events_rt | where EventTime > ago(24h) | summarize Events = count() by Prefecture",
     "Column"),
    ("Failed logins last hour",
     "transaction_events_rt | where EventTime > ago(1h) and EventType == 'FailedLogin' | summarize FailedLogins = count() by CustomerId | top 20 by FailedLogins desc",
     "Table"),
]

# Real-Time Dashboard "RTDashboard" payload schema
# Each tile needs: id, title, query, visualType, dataSource id reference
# Data source = the eventhouse / KQL database
ds_id = "ds-mlj-rt-1"
data_sources = [{
    "id": ds_id,
    "name": DB,
    "clusterUri": QURI,
    "database": DB,
    "kind": "Kusto",
    "scopeId": "kusto"
}]

import uuid
def tile(pid, title, query, vis, x, y, w, h):
    return {
        "id": str(uuid.uuid4()),
        "title": title,
        "pageId": pid,
        "layout": {"x": x, "y": y, "width": w, "height": h},
        "visualType": vis,
        "query": {
            "text": query,
            "dataSource": {"dataSourceId": ds_id, "kind": "inline"}
        },
        "visualOptions": {},
        "usedVariables": []
    }

page_id = str(uuid.uuid4())
tiles = []
# Layout grid: 12 cols, 20 rows
# Row 1: time chart (8 wide), pie (4 wide)
tiles.append(tile(page_id, TILES[0][0], TILES[0][1], "Line",   x=0, y=0, w=8, h=5))
tiles.append(tile(page_id, TILES[1][0], TILES[1][1], "Pie",    x=8, y=0, w=4, h=5))
# Row 2: review table (12 wide)
tiles.append(tile(page_id, TILES[2][0], TILES[2][1], "Table",  x=0, y=5, w=12, h=5))
# Row 3: bar by branch (6), column by prefecture (6)
tiles.append(tile(page_id, TILES[3][0], TILES[3][1], "Column", x=0, y=10, w=6, h=5))
tiles.append(tile(page_id, TILES[4][0], TILES[4][1], "Column", x=6, y=10, w=6, h=5))
# Row 4: failed logins (12 wide)
tiles.append(tile(page_id, TILES[5][0], TILES[5][1], "Table",  x=0, y=15, w=12, h=5))

dashboard_def = {
    "$schema": "https://kusto.azurewebsites.net/RTD/Schemas/dashboard/v3.0.0/schema.json",
    "id": str(uuid.uuid4()),
    "title": "MLJ Real-Time Operations",
    "schema_version": "55",
    "dataSources": data_sources,
    "pages": [{
        "id": page_id,
        "name": "Live AML & Activity",
        "displayName": "Live AML & Activity"
    }],
    "baseQueries": [],
    "tiles": tiles,
    "parameters": [],
    "autoRefresh": {"enabled": True, "defaultInterval": "1m", "minInterval": "30s"}
}

# Create dashboard via items API
print(f"\n== Creating Real-Time Dashboard 'MLJ Real-Time Operations' ==")
# First try the dedicated kqlDashboards endpoint
parts = [
    {"path": "RealTimeDashboard.json",
     "payload": base64.b64encode(json.dumps(dashboard_def, indent=2).encode("utf-8")).decode(),
     "payloadType": "InlineBase64"}
]
body = {
    "displayName": "MLJ_Real_Time_Operations",
    "description": "Real-time AML / portal activity dashboard for the MLJ POC. Auto-refresh every minute.",
    "definition": {"parts": parts}
}
s, h, b = fab("POST", f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/kqlDashboards", body)
print(f"  HTTP {s}: {b[:400]}")
if s == 202:
    op = h.get("x-ms-operation-id")
    res = wait_op(op)
    print(f"  status: {res.get('status')}")
    if res.get("status") == "Succeeded":
        _, _, rb = fab("GET", f"https://api.fabric.microsoft.com/v1/operations/{op}/result")
        info = json.loads(rb)
        dash_id = info.get("id")
        C["rt_dashboard_id"] = dash_id
        with open(r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_ctx.json","w") as f:
            json.dump(C, f, indent=2)
        print(f"  Dashboard ID: {dash_id}")
        print(f"  URL: https://app.fabric.microsoft.com/groups/{WS}/kqlDashboards/{dash_id}")
elif s == 201:
    info = json.loads(b)
    dash_id = info.get("id")
    C["rt_dashboard_id"] = dash_id
    with open(r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_ctx.json","w") as f:
        json.dump(C, f, indent=2)
    print(f"  Dashboard ID: {dash_id}")
    print(f"  URL: https://app.fabric.microsoft.com/groups/{WS}/kqlDashboards/{dash_id}")
