"""Fetch the HR_demo_report definition to understand its structure
before injecting new visuals."""
import base64
import json
import subprocess
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path

WS = "de6a7e47-474b-4354-87e7-26b8d741f015"
REPORT = "d28c79f7-5088-4d95-a3c6-c4a0dae093d9"
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"
OUT = Path(__file__).parent / "report_current"
OUT.mkdir(exist_ok=True)


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
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


s, h, b = call("POST",
               f"{API}/v1/workspaces/{WS}/reports/{REPORT}/getDefinition",
               body={})
print(f"getDefinition -> {s}")
if s == 202:
    loc = h.get("Location") or h.get("location")
    for i in range(30):
        time.sleep(2)
        sp, hp, bp = call("GET", loc)
        try:
            st = json.loads(bp).get("status")
        except Exception:
            st = None
        print(f"  poll {i+1}: {st}")
        if st == "Succeeded":
            sr, hr, br = call("GET", loc.rstrip("/") + "/result")
            payload = json.loads(br)
            break
        if st == "Failed":
            print(f"  FAILED: {bp[:400]}")
            raise SystemExit(1)
else:
    payload = json.loads(b)

parts = payload.get("definition", {}).get("parts", [])
print(f"\nReport has {len(parts)} parts (format={payload.get('definition', {}).get('format')}):")
for p in parts:
    path = p["path"]
    decoded = base64.b64decode(p["payload"]).decode("utf-8", errors="replace")
    out_file = OUT / path.replace("/", "__")
    out_file.write_text(decoded, encoding="utf-8")
    print(f"  {path}  ({len(decoded)} chars)")
print(f"\nParts dumped to {OUT}")
