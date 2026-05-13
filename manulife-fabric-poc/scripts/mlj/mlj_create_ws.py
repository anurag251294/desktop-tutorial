"""Create the ManulifeJapan-Fabric-POC workspace + lakehouse on existing F64 capacity.

Reuses the same capacity (5d0e6ac2-80d1-4cce-95a4-00ebe8d2681e) so demo costs roll up
to one F64. Saves the resulting IDs to a JSON file for downstream scripts.
"""
import subprocess, json, urllib.request, time, os

def sh(cmd):
    return subprocess.check_output(cmd, shell=True).decode().strip()

TOKEN = sh("az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv")
CAP_ID = "5d0e6ac2-80d1-4cce-95a4-00ebe8d2681e"  # F64 fabdemo85829

def fab(method, url, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    req = urllib.request.Request(url, data=data, method=method,
                                  headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()

# 1. Check if workspace already exists
print("== Listing workspaces ==")
s, h, b = fab("GET", "https://api.fabric.microsoft.com/v1/workspaces")
ws_list = json.loads(b).get("value", [])
existing = next((w for w in ws_list if w["displayName"] == "ManulifeJapan-Fabric-POC"), None)
if existing:
    print(f"  Found existing workspace: {existing['id']}")
    ws_id = existing["id"]
else:
    print("== Creating workspace ManulifeJapan-Fabric-POC ==")
    s, h, b = fab("POST", "https://api.fabric.microsoft.com/v1/workspaces",
                  {"displayName": "ManulifeJapan-Fabric-POC",
                   "description": "Manulife Japan Fabric POC - domain-driven medallion mirroring MLJ data architecture",
                   "capacityId": CAP_ID})
    print(f"  HTTP {s}: {b[:300]}")
    if s != 201:
        raise SystemExit("Workspace creation failed")
    ws_id = json.loads(b)["id"]
print(f"  Workspace ID: {ws_id}")

# 2. Ensure capacity assignment (idempotent)
print("== Assigning capacity ==")
s, h, b = fab("POST", f"https://api.fabric.microsoft.com/v1/workspaces/{ws_id}/assignToCapacity",
              {"capacityId": CAP_ID})
print(f"  HTTP {s}: {b[:200]}")

# 3. Create lakehouse
print("== Creating lakehouse MLJ_Lakehouse ==")
s, h, b = fab("GET", f"https://api.fabric.microsoft.com/v1/workspaces/{ws_id}/items?type=Lakehouse")
items = json.loads(b).get("value", [])
lh = next((i for i in items if i["displayName"] == "MLJ_Lakehouse"), None)
if lh:
    print(f"  Found existing lakehouse: {lh['id']}")
    lh_id = lh["id"]
else:
    s, h, b = fab("POST", f"https://api.fabric.microsoft.com/v1/workspaces/{ws_id}/lakehouses",
                  {"displayName": "MLJ_Lakehouse",
                   "description": "Manulife Japan POC lakehouse - 5 domains (Customer, Distributor, Product, Finance, System)"})
    print(f"  HTTP {s}: {b[:300]}")
    if s not in (200, 201):
        raise SystemExit("Lakehouse creation failed")
    lh_id = json.loads(b)["id"]
print(f"  Lakehouse ID: {lh_id}")

# 4. Get SQL endpoint
print("== Fetching SQL endpoint ==")
time.sleep(3)
s, h, b = fab("GET", f"https://api.fabric.microsoft.com/v1/workspaces/{ws_id}/lakehouses/{lh_id}")
lh_info = json.loads(b)
sql_props = lh_info.get("properties", {}).get("sqlEndpointProperties", {})
print(f"  SQL endpoint id: {sql_props.get('id')}")
print(f"  SQL endpoint server: {sql_props.get('connectionString')}")

ctx = {
    "workspace_id": ws_id,
    "lakehouse_id": lh_id,
    "sql_endpoint_id": sql_props.get("id"),
    "sql_endpoint_server": sql_props.get("connectionString"),
    "capacity_id": CAP_ID,
}
out = r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_ctx.json"
with open(out, "w") as f:
    json.dump(ctx, f, indent=2)
print(f"== Saved context to {out} ==")
print(json.dumps(ctx, indent=2))
