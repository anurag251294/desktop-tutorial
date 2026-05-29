"""Re-fetch SQL endpoint info for the Rogers lakehouse and update stack_rogers.json,
then call refreshMetadata so the freshly-loaded Delta tables show up."""
import json, subprocess, time, urllib.request, urllib.error, uuid
from pathlib import Path

ROOT = Path(__file__).parent
STACK_PATH = ROOT / "stack_rogers.json"
STACK = json.loads(STACK_PATH.read_text())
WS = STACK["workspace_id"]
LH = STACK["lakehouse_id"]
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


for i in range(30):
    s, h, b = call("GET", f"{API}/v1/workspaces/{WS}/lakehouses/{LH}")
    d = json.loads(b)
    sqlep = d.get("properties", {}).get("sqlEndpointProperties", {})
    cs = sqlep.get("connectionString")
    sid = sqlep.get("id")
    if cs and sid:
        STACK["sql_endpoint_cs"] = cs
        STACK["sql_endpoint_id"] = sid
        STACK_PATH.write_text(json.dumps(STACK, indent=2))
        print(f"SQL endpoint ready: id={sid}")
        print(f"  cs={cs}")
        break
    print(f"  poll {i+1}: not ready")
    time.sleep(5)

if not STACK.get("sql_endpoint_id"):
    print("SQL endpoint still not ready after polling; re-run later.")
    raise SystemExit(1)

print("\nCalling refreshMetadata so Delta tables become queryable...")
s, h, b = call("POST",
               f"{API}/v1/workspaces/{WS}/sqlEndpoints/{STACK['sql_endpoint_id']}/refreshMetadata?preview=true",
               body={})
print(f"  status={s}  body[:200]={b[:200]}")
if s == 202:
    loc = h.get("Location") or h.get("location")
    for i in range(30):
        time.sleep(2)
        sp, hp, bp = call("GET", loc)
        try:
            st = json.loads(bp).get("status")
        except Exception:
            st = None
        if st == "Succeeded":
            print("  refreshMetadata OK")
            break
        if st == "Failed":
            print(f"  refreshMetadata FAILED: {bp[:300]}")
            break
