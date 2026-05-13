"""Upload JP CSV + MD files to the MLJ lakehouse Files/raw area via OneLake REST.

Uses az CLI to get a storage-scope token, then PUT/POST to onelake.dfs.fabric.microsoft.com.
"""
import subprocess, json, os, urllib.request

def sh(cmd): return subprocess.check_output(cmd, shell=True).decode().strip()

with open(r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_ctx.json") as f:
    CTX = json.load(f)
WS = CTX["workspace_id"]; LH = CTX["lakehouse_id"]

TOKEN = sh("az account get-access-token --resource https://storage.azure.com/ --query accessToken -o tsv")
BASE = f"https://onelake.dfs.fabric.microsoft.com/{WS}/{LH}"

def req(method, url, body=None, headers=None):
    hdrs = {"Authorization": f"Bearer {TOKEN}"}
    if headers: hdrs.update(headers)
    data = body if body is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

def mkdir(path):
    # ?resource=directory on path
    url = f"{BASE}/{path}?resource=directory"
    s, b = req("PUT", url, b"")
    return s

def upload_file(local_path, remote_path):
    with open(local_path, "rb") as f:
        content = f.read()
    # 1. Create file (PUT with ?resource=file)
    s1, _ = req("PUT", f"{BASE}/{remote_path}?resource=file", b"", {"Content-Length":"0"})
    # 2. Append (PATCH with ?action=append&position=0)
    s2, _ = req("PATCH", f"{BASE}/{remote_path}?action=append&position=0",
                content, {"Content-Type":"application/octet-stream","Content-Length": str(len(content))})
    # 3. Flush (PATCH with ?action=flush&position=<len>)
    s3, _ = req("PATCH", f"{BASE}/{remote_path}?action=flush&position={len(content)}",
                b"", {"Content-Length":"0"})
    return s1, s2, s3, len(content)

# 1. Make directories
for d in ["Files/raw","Files/raw/structured","Files/raw/unstructured"]:
    s = mkdir(d)
    print(f"mkdir {d} -> {s}")

# 2. Upload structured CSVs (JP data)
src_struct = r"C:\Users\anuragdhuria\OneDrive - Microsoft\Documents\GitHub\desktop-tutorial\manulife-fabric-poc\data\raw\structured_jp"
for fn in os.listdir(src_struct):
    if not fn.endswith(".csv"): continue
    local = os.path.join(src_struct, fn)
    remote = f"Files/raw/structured/{fn}"
    s = upload_file(local, remote)
    print(f"  {fn}: {s[:3]} ({s[3]} bytes)")

# 3. Upload unstructured MD files (JP)
src_unstr = r"C:\Users\anuragdhuria\OneDrive - Microsoft\Documents\GitHub\desktop-tutorial\manulife-fabric-poc\data\raw\unstructured_jp"
for fn in os.listdir(src_unstr):
    if not fn.endswith(".md"): continue
    local = os.path.join(src_unstr, fn)
    remote = f"Files/raw/unstructured/{fn}"
    s = upload_file(local, remote)
    print(f"  {fn}: {s[:3]} ({s[3]} bytes)")

print("\nUpload complete.")
