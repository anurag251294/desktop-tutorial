"""Trigger refresh on the ctc_merch Direct Lake model (frame the partitions)."""
import json, subprocess, time, urllib.request, urllib.error, uuid
from pathlib import Path

STACK = json.loads((Path(__file__).parent / "stack_ctc.json").read_text())
WS = STACK["workspace_id"]
MODEL = STACK["model_id"]
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"

tok = subprocess.check_output(
    [AZ, "account", "get-access-token",
     "--resource", "https://analysis.windows.net/powerbi/api",
     "--query", "accessToken", "-o", "tsv"]).decode().strip()
h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
url = f"https://api.powerbi.com/v1.0/myorg/groups/{WS}/datasets/{MODEL}/refreshes"

req = urllib.request.Request(url, headers=h, method="POST",
                             data=json.dumps({"type": "Full"}).encode())
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        print(f"refresh request status={r.status}")
        loc = r.headers.get("Location") or r.headers.get("location")
        print(f"  Location: {loc}")
except urllib.error.HTTPError as e:
    print(f"refresh request ERR {e.code}: {e.read().decode()}")

print("\nPolling refresh status...")
for i in range(30):
    time.sleep(4)
    req2 = urllib.request.Request(url + "?$top=1", headers=h, method="GET")
    with urllib.request.urlopen(req2, timeout=60) as r:
        d = json.loads(r.read().decode())
        v = d.get("value", [])
        if v:
            st = v[0].get("status")
            print(f"  poll {i+1}: status={st}")
            if st in ("Completed", "Succeeded"):
                print("Done.")
                break
            if st in ("Failed", "Disabled"):
                print(f"  details: {v[0]}")
                break
