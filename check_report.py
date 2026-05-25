"""Check the report's stored definition vs what we sent."""
import base64
import json
import subprocess
import time
import urllib.request
import urllib.error
import uuid

WORKSPACE_ID = "2690ef29-1370-476c-b28c-58a505fea2bd"
REPORT_ID = "8b29f18e-6263-4964-b3ec-8083cf5cffea"
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"


def token():
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", API,
         "--query", "accessToken", "-o", "tsv"]).decode().strip()


def call(method, url, body=None):
    h = {"Authorization": f"Bearer {token()}",
         "ActivityId": str(uuid.uuid4()),
         "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, headers=h, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


s, h, b = call("POST", f"{API}/v1/workspaces/{WORKSPACE_ID}/reports/{REPORT_ID}/getDefinition", body={})
print(f"getDefinition -> {s}")
if s == 202:
    loc = h.get("Location") or h.get("location")
    print(f"  polling {loc}")
    for i in range(30):
        time.sleep(2)
        sp, hp, bp = call("GET", loc)
        try:
            op = json.loads(bp)
            st = op.get("status")
        except Exception:
            st = None
        print(f"  poll {i+1}: status={st}")
        if st == "Succeeded":
            sr, hr, br = call("GET", loc.rstrip("/") + "/result")
            payload = json.loads(br)
            parts = payload.get("definition", {}).get("parts", [])
            print(f"\nReport has {len(parts)} parts:")
            for p in parts:
                decoded = base64.b64decode(p["payload"]).decode("utf-8", errors="replace")
                print(f"\n=== {p['path']} ({len(decoded)} chars) ===")
                print(decoded[:600])
            break
        if st == "Failed":
            print(f"  FAILED: {bp[:600]}")
            break
else:
    print(f"  body: {b[:400]}")
