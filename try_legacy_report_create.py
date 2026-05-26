"""Try the Power BI legacy Reports API to create a blank report bound to hr_demo.

Hypothesis: the portal 'Create blank report' button calls an endpoint that
produces a fully-valid PBIR with all the boilerplate the renderer expects.
The Fabric Items API + our hand-rolled JSON is missing some property.

Tries multiple endpoint patterns and picks the first that yields a
useable report ID.
"""
import json
import subprocess
import urllib.request
import urllib.error
import uuid

WS = "de6a7e47-474b-4354-87e7-26b8d741f015"
MODEL = "89782e0a-276b-4b86-a2d0-e8238d3c8791"
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"


def tok(resource):
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"]).decode().strip()


def call(method, url, headers, body=None):
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    req = urllib.request.Request(url, headers=headers, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


pbi_h = {"Authorization": f"Bearer {tok('https://analysis.windows.net/powerbi/api')}",
         "Content-Type": "application/json",
         "ActivityId": str(uuid.uuid4())}

cluster = "https://DF-MSIT-SCUS-redirect.analysis.windows.net"

attempts = [
    # 1. Legacy Power BI Reports API - direct create
    ("POST", "https://api.powerbi.com/v1.0/myorg/groups/" + WS + "/reports",
     {"displayName": "InteracHR_Auto", "datasetId": MODEL}),
    # 2. Clone a report (no source - try to see if API auto-creates blank)
    ("POST", "https://api.powerbi.com/v1.0/myorg/groups/" + WS + "/reports/Clone",
     {"name": "InteracHR_Auto", "targetModelId": MODEL,
      "targetWorkspaceId": WS}),
    # 3. Power BI metadata create
    ("POST", f"{cluster}/metadata/reports",
     {"displayName": "InteracHR_Auto", "datasetId": MODEL, "groupId": WS}),
    # 4. Auto-create from dataset
    ("POST", f"{cluster}/metadata/datasets/{MODEL}/createAutoReport",
     {"groupId": WS, "displayName": "InteracHR_Auto"}),
    # 5. Newer pattern with explicit type
    ("POST", "https://api.powerbi.com/v1.0/myorg/groups/" + WS + "/reports",
     {"name": "InteracHR_Auto", "datasetId": MODEL}),
]

for method, url, body in attempts:
    print(f"\n{method} {url}")
    print(f"  body: {body}")
    s, h, b = call(method, url, pbi_h, body=body)
    print(f"  status={s}")
    print(f"  body[:300]: {b[:300]}")
    if s in (200, 201):
        # Try to extract a report id from the response
        try:
            payload = json.loads(b)
            rid = payload.get("id") or payload.get("reportId")
            if rid:
                print(f"\n*** SUCCESS: report id = {rid}")
                print(f"Open: https://msit.powerbi.com/groups/{WS}/reports/{rid}")
                break
        except Exception:
            pass
