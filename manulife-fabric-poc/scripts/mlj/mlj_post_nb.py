"""Orchestrator that runs AFTER notebooks finish:
1. Refresh SQL endpoint metadata so the warehouse sees the new tables
2. Build the semantic model (clones CA, swaps IDs, JPY)
3. Refresh the semantic model so Direct Lake reads new schemas
4. (Optional) attempt to create the Data Agent via REST
"""
import subprocess, json, urllib.request, time, sys

def sh(cmd): return subprocess.check_output(cmd, shell=True).decode().strip()

with open(r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_ctx.json") as f:
    CTX = json.load(f)
WS = CTX["workspace_id"]; LH = CTX["lakehouse_id"]

TOKEN_FAB = sh("az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv")
TOKEN_PBI = sh("az account get-access-token --resource https://analysis.windows.net/powerbi/api --query accessToken -o tsv")

def fab(method, url, body=None, token=None, timeout=180):
    tk = token or TOKEN_FAB
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    req = urllib.request.Request(url, data=data, method=method,
                                  headers={"Authorization": f"Bearer {tk}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            hdrs = {k.lower(): v for k, v in r.headers.items()}
            return r.status, hdrs, r.read().decode() if r.status != 202 else ""
    except urllib.error.HTTPError as e:
        hdrs = {k.lower(): v for k, v in (e.headers.items() if e.headers else [])}
        return e.code, hdrs, e.read().decode()

# Step 1: re-fetch SQL endpoint id (it should be available by now)
print("== 1. Fetching MLJ SQL endpoint ==")
for _ in range(20):
    s, h, b = fab("GET", f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/lakehouses/{LH}")
    sep = json.loads(b).get("properties", {}).get("sqlEndpointProperties", {})
    if sep.get("id"):
        CTX["sql_endpoint_id"] = sep["id"]
        CTX["sql_endpoint_server"] = sep["connectionString"]
        with open(r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_ctx.json","w") as f:
            json.dump(CTX, f, indent=2)
        print(f"  SQL endpoint: {sep['id']}")
        break
    time.sleep(5)
else:
    print("  SQL endpoint not yet provisioned -- aborting"); sys.exit(1)

# Step 2: refresh SQL endpoint metadata
print("== 2. Refreshing SQL endpoint metadata ==")
s, h, b = fab("POST", f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/sqlEndpoints/{CTX['sql_endpoint_id']}/refreshMetadata?preview=true",
              {"timeout":{"timeUnit":"Seconds","value":120}})
print(f"  HTTP {s}: {b[:300]}")
if s == 202:
    # Wait for completion
    loc = h.get("location")
    for _ in range(40):
        time.sleep(3)
        if not loc: break
        s2, h2, b2 = fab("GET", loc)
        if "Succeeded" in b2 or "Failed" in b2:
            print(f"  status: {b2[:200]}"); break

# Step 3: build semantic model (clone from CA)
print("== 3. Building semantic model ==")
import subprocess
res = subprocess.run(["python", r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_build_sm.py"],
                     capture_output=True, text=True)
print(res.stdout[-1500:])
if res.returncode != 0:
    print("STDERR:", res.stderr[:1500])
    sys.exit(2)

# Re-load context to pick up SM id
with open(r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_ctx.json") as f:
    CTX = json.load(f)
SM = CTX.get("semantic_model_id")
if not SM:
    print("No SM id in context; aborting"); sys.exit(3)

# Step 4: refresh semantic model
print("== 4. Refreshing semantic model ==")
s, h, b = fab("POST", f"https://api.powerbi.com/v1.0/myorg/groups/{WS}/datasets/{SM}/refreshes",
              {"type":"Full"}, token=TOKEN_PBI)
print(f"  HTTP {s}: {b[:300]}")

# Step 5: try Data Agent REST creation (may need UI fallback)
print("== 5. Attempting Data Agent creation via REST ==")
res = subprocess.run(["python", r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_build_agent.py"],
                     capture_output=True, text=True)
print(res.stdout[-1500:])
print("== Post-notebook orchestration complete ==")
