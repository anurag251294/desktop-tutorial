"""Run the MLJ notebooks sequentially and poll for completion."""
import subprocess, json, urllib.request, time, sys, io, os
# Force UTF-8 on stdout (Windows defaults to cp1252)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def sh(cmd): return subprocess.check_output(cmd, shell=True).decode().strip()

with open(r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_ctx.json") as f:
    CTX = json.load(f)
WS = CTX["workspace_id"]
NBS = CTX["notebooks"]

TOKEN = sh("az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv")

def fab(method, url, body=None, timeout=180):
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    req = urllib.request.Request(url, data=data, method=method,
                                  headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            hdrs = {k.lower(): v for k, v in r.headers.items()}
            return r.status, hdrs, r.read().decode() if r.status not in (202,) else ""
    except urllib.error.HTTPError as e:
        hdrs = {k.lower(): v for k, v in (e.headers.items() if e.headers else [])}
        return e.code, hdrs, e.read().decode()

order = ["02_Silver_Transformation","03_Gold_Curated_Layer","04_Document_Processing","05_Data_Validation","06_MLJ_Curated_Marts"]  # 01 already completed
# Allow re-fresh token periodically
def refresh_token():
    global TOKEN
    TOKEN = sh("az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv")

for nb_name in order:
    nb_id = NBS[nb_name]
    print(f"\n=== Triggering {nb_name} ({nb_id}) ===", flush=True)
    s, h, b = fab("POST", f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/items/{nb_id}/jobs/instances?jobType=RunNotebook")
    if s != 202:
        print(f"  FAIL to trigger HTTP {s}: {b[:400]}", flush=True)
        sys.exit(1)
    loc = h.get("location","")
    print(f"  job location: {loc}", flush=True)
    # Poll status
    start = time.time()
    last = ""
    while True:
        if time.time() - start > 1500:
            print("  TIMEOUT after 25min", flush=True); sys.exit(2)
        time.sleep(20)
        # token may expire after 1hr — refresh if we have been polling long
        if time.time() - start > 1700:
            refresh_token()
        s, h, b = fab("GET", loc)
        try:
            j = json.loads(b)
            status = j.get("status","?")
            if status != last:
                print(f"  status: {status}  (elapsed {int(time.time()-start)}s)", flush=True)
                last = status
            if status == "Completed":
                print(f"  OK{nb_name} succeeded in {int(time.time()-start)}s", flush=True)
                break
            if status == "Failed":
                err = j.get("failureReason", j)
                print(f"  FAIL{nb_name} FAILED: {err}", flush=True)
                sys.exit(3)
        except Exception as e:
            print(f"  poll error: {e} -- body: {b[:200]}", flush=True)

print("\n=== ALL NOTEBOOKS COMPLETED ===", flush=True)
