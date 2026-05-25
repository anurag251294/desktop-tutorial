"""Refresh the lakehouse SQL endpoint metadata and re-verify measures."""
import json
import subprocess
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path

ROOT = Path(__file__).parent
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"

stack = json.loads((ROOT / "stack_corp.json").read_text())
WS = stack["workspace_id"]
LH = stack["lakehouse_id"]
SQL_EP = stack["sql_endpoint_id"]
MODEL = stack["model_id"]


def tok(resource=API):
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"]).decode().strip()


def call(method, url, body=None, resource=None):
    h = {"Authorization": f"Bearer {tok(resource or API)}",
         "Content-Type": "application/json",
         "ActivityId": str(uuid.uuid4())}
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    req = urllib.request.Request(url, headers=h, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


# 1) Try the SQL endpoint metadata refresh
print("Refreshing SQL endpoint metadata...")
url = f"{API}/v1/workspaces/{WS}/sqlEndpoints/{SQL_EP}/refreshMetadata?preview=true"
s, h, b = call("POST", url, body={})
print(f"  refreshMetadata -> {s}")
if s == 202:
    loc = h.get("Location") or h.get("location")
    print(f"  polling {loc}")
    for i in range(30):
        time.sleep(2)
        sp, hp, bp = call("GET", loc)
        try:
            st = json.loads(bp).get("status")
        except Exception:
            st = None
        print(f"  poll {i+1}: {st}")
        if st == "Succeeded":
            break
        if st == "Failed":
            print(f"   FAILED: {bp[:300]}")
            break
elif s in (200, 201):
    print("  sync OK")
elif s == 404:
    # Try alternate endpoint
    print("  refreshMetadata not found, trying items endpoint...")
    url2 = (f"{API}/v1/workspaces/{WS}/items/{SQL_EP}/jobs/instances"
            f"?jobType=RefreshLakehouseMetadata")
    s, h, b = call("POST", url2, body={})
    print(f"  -> {s}")
else:
    print(f"  ERR: {b[:300]}")

# 2) Wait a bit then re-verify
print("\nWaiting 15s for sync to propagate...")
time.sleep(15)

print("\nVerifying measures via DAX:")
pbi_tok = tok("https://analysis.windows.net/powerbi/api")
h = {"Authorization": f"Bearer {pbi_tok}", "Content-Type": "application/json"}
url = (f"https://api.powerbi.com/v1.0/myorg/groups/{WS}"
       f"/datasets/{MODEL}/executeQueries")

QUERIES = [
    "Active Employees", "Tech Employees", "% Tech",
    "% Female", "% Female (Tech)",
    "Terminations LTM", "Attrition Rate LTM", "% Regrettable LTM",
    "Open Reqs", "Hires LTM",
    "Avg Base Salary", "Comp Ratio vs Market",
    "FINTRAC Training Completion %", "COI Overdue 90+ Days",
]
for m in QUERIES:
    body = json.dumps({"queries": [{"query": f"EVALUATE ROW(\"v\", [{m}])"}]}).encode()
    req = urllib.request.Request(url, headers=h, method="POST", data=body)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
            v = list(d["results"][0]["tables"][0]["rows"][0].values())[0]
            if isinstance(v, float):
                if 0 < abs(v) < 1:
                    s = f"{v:.4f}"
                else:
                    s = f"{v:,.2f}"
            else:
                s = str(v)
            print(f"  {m:32s} = {s}")
    except urllib.error.HTTPError as e:
        b = e.read().decode()
        try:
            err = json.loads(b)
            msg = (err.get("error", {}).get("pbi.error", {}).get("details", [{}])[0]
                      .get("detail", {}).get("value", b[:200]))
        except Exception:
            msg = b[:200]
        print(f"  {m:32s} ERR {e.code}: {msg[:150]}")
