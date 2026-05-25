"""Try to activate a Fabric trial via internal Power BI APIs."""
import json
import subprocess
import urllib.request
import urllib.error

AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"


def tok(resource):
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"]).decode().strip()


def call(method, url, headers, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, headers=headers, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return -1, str(e)


pbi_tok = tok("https://analysis.windows.net/powerbi/api")
cluster = "https://DF-MSIT-SCUS-redirect.analysis.windows.net"
h = {"Authorization": f"Bearer {pbi_tok}",
     "Content-Type": "application/json",
     "Accept": "application/json"}

attempts = [
    ("POST", f"{cluster}/metadata/UserTrials/Microsoft.PowerBI.Trials.FabricTrial"),
    ("POST", f"{cluster}/metadata/UserTrials"),
    ("POST", f"{cluster}/metadata/v201901/myorg/UserTrials/Microsoft.PowerBI.Trials.FabricTrial"),
    ("POST", f"{cluster}/metadata/v201901/myorg/UserTrials"),
    ("POST", f"{cluster}/v1.0/myorg/UserTrials"),
    ("GET",  f"{cluster}/metadata/UserTrials"),
    ("GET",  f"{cluster}/metadata/v201901/myorg/UserTrials"),
    ("GET",  f"{cluster}/metadata/Tenant"),
    ("GET",  f"{cluster}/metadata/myorg/Premium"),
]

for method, url in attempts:
    print(f"\n{method} {url}")
    s, b = call(method, url, h, body={} if method == "POST" else None)
    print(f"  status={s}")
    if b:
        print(f"  body[:300]: {b[:300]}")
