"""Probe each Fabric capacity to find one Anurag can actually create on."""
import json
import subprocess
import urllib.request
import urllib.error
import uuid

AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"


def tok(resource):
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"]).decode().strip()


def call(method, url, body=None):
    h = {"Authorization": f"Bearer {tok('https://api.fabric.microsoft.com')}",
         "Content-Type": "application/json",
         "ActivityId": str(uuid.uuid4())}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, headers=h, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


# List capacities
s, b = call("GET", "https://api.fabric.microsoft.com/v1/capacities")
caps = json.loads(b)["value"]

# Filter to Fabric SKUs (FT1 / FTL* / F* are real Fabric; PP* is PPU; A* is embedded)
fabric_caps = [c for c in caps if c["sku"].startswith(("FT", "F1", "F2", "F4", "F6"))]
print(f"Found {len(fabric_caps)} Fabric capacities to probe")

# Try creating a throwaway workspace on each
WORKING = []
for c in fabric_caps:
    name = f"probe-{uuid.uuid4().hex[:6]}"
    body = {"displayName": name, "capacityId": c["id"]}
    s, b = call("POST", "https://api.fabric.microsoft.com/v1/workspaces", body=body)
    if s in (200, 201):
        ws = json.loads(b)
        print(f"  OK: {c['displayName']} ({c['sku']}) - workspace {ws['id']}")
        WORKING.append((c, ws["id"]))
        # Delete the throwaway
        call("DELETE", f"https://api.fabric.microsoft.com/v1/workspaces/{ws['id']}")
        print(f"     -> deleted probe workspace")
    elif s == 403:
        pass  # No access, expected for most
    else:
        # Print non-403 errors (might be useful)
        print(f"  ? {c['displayName']} ({c['sku']}) -> {s}: {b[:120]}")

print(f"\n=== Capacities you can create on: {len(WORKING)} ===")
for c, _ in WORKING:
    print(f"  {c['displayName']}")
    print(f"    id:     {c['id']}")
    print(f"    sku:    {c['sku']}")
    print(f"    region: {c['region']}")
