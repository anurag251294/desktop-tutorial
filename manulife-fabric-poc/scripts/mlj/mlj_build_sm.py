"""Clone the CA POC semantic model into MLJ workspace, retargeted to the MLJ lakehouse,
with JPY currency formatting.

Strategy:
1. Fetch CA POC semantic model definition (TMDL parts).
2. Replace lakehouse/workspace ID references in expressions.tmdl.
3. Replace currency format strings $#,##0 -> ¥#,##0.
4. Rename model to ManulifeJapanPOC_SemanticModel.
5. Create new semantic model in MLJ workspace + push parts.
"""
import subprocess, json, base64, urllib.request, time, sys

def sh(cmd): return subprocess.check_output(cmd, shell=True).decode().strip()

with open(r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_ctx.json") as f:
    CTX = json.load(f)
MLJ_WS = CTX["workspace_id"]; MLJ_LH = CTX["lakehouse_id"]

CA_WS = "c41860d5-3e88-4f9d-bfa8-e2dc68d50a8e"
CA_SM = "b9468ca3-bcd6-4976-846a-f62c7f37cde6"
CA_LH = "09f8932b-7c05-4bce-8bfd-a4ebfd26020b"

TOKEN = sh("az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv")

def fab(method, url, body=None, timeout=180):
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    req = urllib.request.Request(url, data=data, method=method,
                                  headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            hdrs = {k.lower(): v for k, v in r.headers.items()}
            return r.status, hdrs, r.read().decode() if r.status != 202 else ""
    except urllib.error.HTTPError as e:
        hdrs = {k.lower(): v for k, v in (e.headers.items() if e.headers else [])}
        return e.code, hdrs, e.read().decode()

def wait_op(op):
    for _ in range(80):
        time.sleep(3)
        _, _, b = fab("GET", f"https://api.fabric.microsoft.com/v1/operations/{op}")
        s = json.loads(b)
        if s.get("status") in ("Succeeded","Failed"): return s
    return {"status":"Timeout"}

# Step 1: get fresh SQL endpoint info for the MLJ lakehouse
print("== Fetching MLJ lakehouse SQL endpoint ==")
for _ in range(20):
    s, h, b = fab("GET", f"https://api.fabric.microsoft.com/v1/workspaces/{MLJ_WS}/lakehouses/{MLJ_LH}")
    info = json.loads(b)
    sep = info.get("properties", {}).get("sqlEndpointProperties", {})
    if sep.get("id"):
        MLJ_SQL_ID = sep["id"]
        MLJ_SQL_SERVER = sep["connectionString"]
        print(f"  SQL endpoint id: {MLJ_SQL_ID}")
        print(f"  SQL server: {MLJ_SQL_SERVER}")
        break
    time.sleep(5)
else:
    print("  SQL endpoint still provisioning; will retry"); sys.exit(1)

CTX["sql_endpoint_id"] = MLJ_SQL_ID; CTX["sql_endpoint_server"] = MLJ_SQL_SERVER
with open(r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_ctx.json","w") as f:
    json.dump(CTX, f, indent=2)

# Step 2: fetch CA POC SM definition
print("== Fetching CA POC SM definition ==")
s, h, _ = fab("POST", f"https://api.fabric.microsoft.com/v1/workspaces/{CA_WS}/semanticModels/{CA_SM}/getDefinition")
op = h.get("x-ms-operation-id")
res = wait_op(op)
if res.get("status") != "Succeeded":
    print(f"  getDefinition failed: {res}"); sys.exit(2)
_, _, body = fab("GET", f"https://api.fabric.microsoft.com/v1/operations/{op}/result")
ca_def = json.loads(body)
print(f"  parts: {len(ca_def['definition']['parts'])}")

# Step 3: get CA lakehouse SQL endpoint to find old server string to swap
print("== Fetching CA POC lakehouse SQL endpoint ==")
s, h, b = fab("GET", f"https://api.fabric.microsoft.com/v1/workspaces/{CA_WS}/lakehouses/{CA_LH}")
ca_info = json.loads(b)
ca_sep = ca_info.get("properties", {}).get("sqlEndpointProperties", {})
CA_SQL_ID = ca_sep.get("id")
CA_SQL_SERVER = ca_sep.get("connectionString")
print(f"  CA SQL endpoint id: {CA_SQL_ID}")
print(f"  CA SQL server: {CA_SQL_SERVER}")

# Step 4: transform parts
print("== Transforming TMDL parts ==")
new_parts = []
for p in ca_def["definition"]["parts"]:
    path = p["path"]
    payload = base64.b64decode(p["payload"]).decode("utf-8")
    orig = payload
    # Swap workspace + lakehouse IDs
    payload = payload.replace(CA_WS, MLJ_WS)
    payload = payload.replace(CA_LH, MLJ_LH)
    if CA_SQL_ID:
        payload = payload.replace(CA_SQL_ID, MLJ_SQL_ID)
    if CA_SQL_SERVER:
        payload = payload.replace(CA_SQL_SERVER, MLJ_SQL_SERVER)
    # Convert currency format strings to JPY
    payload = payload.replace('$#,##0', '\\"¥\\"#,##0')
    payload = payload.replace('"$#,##0"', '"\\"¥\\"#,##0"')
    payload = payload.replace("formatString: $#,##0", "formatString: \"\\\"¥\\\"#,##0\"")
    payload = payload.replace("formatString: \"$#,##0\"", "formatString: \"\\\"¥\\\"#,##0\"")
    # Rename model in model.tmdl
    payload = payload.replace("ManulifePOC_SemanticModel", "ManulifeJapanPOC_SemanticModel")
    payload = payload.replace("ManulifePOC", "ManulifeJapanPOC")
    new_parts.append({"path": path, "payload": base64.b64encode(payload.encode("utf-8")).decode(), "payloadType":"InlineBase64"})

# Step 5: create empty semantic model in MLJ
print("== Creating empty SM in MLJ workspace ==")
s, h, b = fab("POST", f"https://api.fabric.microsoft.com/v1/workspaces/{MLJ_WS}/semanticModels",
              {"displayName": "ManulifeJapanPOC_SemanticModel",
               "description": "Direct Lake semantic model for the Manulife Japan POC (JPY)",
               "definition": {"format":"TMDL","parts": new_parts}})
print(f"  HTTP {s}")
if s == 201:
    sm_id = json.loads(b)["id"]
elif s == 202:
    op = h.get("x-ms-operation-id")
    res = wait_op(op)
    if res.get("status") != "Succeeded":
        print(f"  create failed: {res}"); sys.exit(3)
    _, _, rb = fab("GET", f"https://api.fabric.microsoft.com/v1/operations/{op}/result")
    sm_id = json.loads(rb)["id"]
else:
    print(f"  body: {b[:1500]}"); sys.exit(4)
print(f"  SM ID: {sm_id}")

CTX["semantic_model_id"] = sm_id
with open(r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_ctx.json","w") as f:
    json.dump(CTX, f, indent=2)
print(f"== Saved SM ID to context ==")
