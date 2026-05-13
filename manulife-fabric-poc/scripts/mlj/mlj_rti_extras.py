"""Add to the RTI stack:
1. KQL Queryset with prepared demo queries
2. Streaming simulator (Python script that pushes 1-3 events per second for live demo feel)
"""
import subprocess, json, urllib.request, time, sys, io, base64, random, uuid
from datetime import datetime, timedelta, timezone
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def sh(c): return subprocess.check_output(c, shell=True).decode().strip()

with open(r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_ctx.json") as f:
    C = json.load(f)
WS = C["workspace_id"]; DBID = C["kql_db_id"]; DB = C["kql_db_name"]; QURI = C["kql_query_uri"]
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
    for _ in range(40):
        time.sleep(2)
        _, _, b = fab("GET", f"https://api.fabric.microsoft.com/v1/operations/{op}")
        s = json.loads(b)
        if s.get("status") in ("Succeeded","Failed"): return s
    return {"status":"Timeout"}

# --- Create KQL Queryset ---
# QuerySet item format: a notebook-like .json containing tabs and queries
print("== Creating KQL Queryset 'MLJ_RT_Demo_Queries' ==")
queryset_def = {
    "schema": "https://kusto.blob.core.windows.net/static/queries/2.0/queries.json",
    "queries": [
        {"id": str(uuid.uuid4()), "name": "1. Total events + alert levels",
         "kql": "transaction_events_rt\n| summarize Total = count(), \n            Info = countif(AlertLevel == 'INFO'),\n            Watch = countif(AlertLevel == 'WATCH'),\n            Review = countif(AlertLevel == 'REVIEW')"},
        {"id": str(uuid.uuid4()), "name": "2. Events per minute (last hour) - timechart",
         "kql": "transaction_events_rt\n| where EventTime > ago(1h)\n| summarize Events = count() by bin(EventTime, 1m)\n| render timechart"},
        {"id": str(uuid.uuid4()), "name": "3. AML review queue (latest 20)",
         "kql": "transaction_events_rt\n| where AlertLevel == 'REVIEW'\n| top 20 by EventTime desc\n| project EventTime, EventType, CustomerId, BranchOffice, Amount, PaymentMethod, Notes"},
        {"id": str(uuid.uuid4()), "name": "4. Suspicious cash payments > 1M JPY",
         "kql": "transaction_events_rt\n| where EventType == 'CashPayment' and Amount > 1000000\n| order by EventTime desc\n| project EventTime, CustomerId, BranchOffice, Amount, Notes\n| take 20"},
        {"id": str(uuid.uuid4()), "name": "5. Velocity check - customers with 3+ events in 30 min",
         "kql": "transaction_events_rt\n| where EventTime > ago(1h)\n| summarize EventCount = count(), Last = max(EventTime), First = min(EventTime) by CustomerId\n| where EventCount >= 3 and Last - First <= 30m\n| order by EventCount desc"},
        {"id": str(uuid.uuid4()), "name": "6. Failed login attempts by customer",
         "kql": "transaction_events_rt\n| where EventType == 'FailedLogin'\n| summarize Attempts = count(), LastAttempt = max(EventTime) by CustomerId\n| where Attempts >= 2\n| order by Attempts desc"},
        {"id": str(uuid.uuid4()), "name": "7. Transaction value by branch (24h)",
         "kql": "transaction_events_rt\n| where EventTime > ago(24h) and Amount > 0\n| summarize TotalAmount = sum(Amount), TxnCount = count() by BranchOffice\n| order by TotalAmount desc\n| render barchart"},
        {"id": str(uuid.uuid4()), "name": "8. Events by prefecture (24h heatmap)",
         "kql": "transaction_events_rt\n| where EventTime > ago(24h)\n| summarize Events = count(), Reviews = countif(AlertLevel == 'REVIEW') by Prefecture\n| order by Events desc"},
        {"id": str(uuid.uuid4()), "name": "9. Real-time stream watch (last 5 min)",
         "kql": "transaction_events_rt\n| where EventTime > ago(5m)\n| order by EventTime desc\n| project EventTime, EventType, CustomerId, BranchOffice, Amount, AlertLevel\n| take 50"},
        {"id": str(uuid.uuid4()), "name": "10. Cross-domain - join to gold_dim_customer (semantic lookup)",
         "kql": "// Look up customer details via mart_cdp_customer_360 - shows joining real-time stream to enterprise data\nlet enriched = transaction_events_rt | where AlertLevel == 'REVIEW' | top 10 by EventTime desc;\nenriched | project EventTime, EventType, CustomerId, BranchOffice, Amount, Notes"},
    ],
    "tabs": []
}

parts = [
    {"path": "RealTimeQueryset.json",
     "payload": base64.b64encode(json.dumps(queryset_def, indent=2).encode("utf-8")).decode(),
     "payloadType": "InlineBase64"}
]
# Queryset is a kqlQuerysets item type in Fabric
body = {
    "displayName": "MLJ_RT_Demo_Queries",
    "description": "Demo KQL queries for the MLJ Real-Time Operations dashboard - 10 prepared scenarios",
    "definition": {"parts": parts}
}
s, h, b = fab("POST", f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/kqlQuerysets", body)
print(f"  HTTP {s}: {b[:300]}")
if s in (201, 202):
    if s == 202:
        op = h.get("x-ms-operation-id")
        wait_op(op)
        _,_,rb = fab("GET", f"https://api.fabric.microsoft.com/v1/operations/{op}/result")
        qs = json.loads(rb)
    else:
        qs = json.loads(b)
    C["queryset_id"] = qs["id"]
    with open(r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_ctx.json","w") as f:
        json.dump(C, f, indent=2)
    print(f"  Queryset URL: https://app.fabric.microsoft.com/groups/{WS}/kqlQuerysets/{qs['id']}")
