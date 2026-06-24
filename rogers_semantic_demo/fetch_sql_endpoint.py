"""Re-fetch the lakehouse SQL endpoint and trigger refreshMetadata.

Run this after `load_via_notebook.py` if the SQL endpoint hasn't picked up
new Delta tables yet, then re-run before building the semantic model.
"""
import json, subprocess, time, urllib.request, urllib.error, uuid
from pathlib import Path

ROOT = Path(__file__).parent
STACK_PATH = ROOT / "stack_finance.json"
STACK = json.loads(STACK_PATH.read_text())
WS, LH = STACK["workspace_id"], STACK["lakehouse_id"]
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


def main():
    print("Fetching lakehouse SQL endpoint...")
    s, h, b = call("GET", f"{API}/v1/workspaces/{WS}/lakehouses/{LH}")
    sqlep = json.loads(b).get("properties", {}).get("sqlEndpointProperties", {})
    sql_cs = sqlep.get("connectionString")
    sql_id = sqlep.get("id")
    print(f"  sql_cs={sql_cs}")
    print(f"  sql_id={sql_id}")

    STACK["sql_endpoint_cs"] = sql_cs
    STACK["sql_endpoint_id"] = sql_id
    STACK_PATH.write_text(json.dumps(STACK, indent=2))

    if not sql_id:
        print("  No SQL endpoint id - nothing to refresh.")
        return
    print("\nrefreshMetadata...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/sqlEndpoints/{sql_id}/refreshMetadata?preview=true",
                   body={})
    print(f"  status={s}  body={b[:300]}")
    if s == 202:
        loc = h.get("Location") or h.get("location")
        for _ in range(60):
            time.sleep(3)
            sp, _, bp = call("GET", loc)
            try:
                st = json.loads(bp).get("status")
            except Exception:
                st = None
            print(f"  status={st}")
            if st in ("Succeeded", "Failed"):
                break


if __name__ == "__main__":
    main()
