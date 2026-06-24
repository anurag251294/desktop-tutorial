"""Verify the model, report, and data agent items still exist + are reachable
from the API perspective. Prints the open URLs for sharing."""
import json, subprocess, urllib.request
from pathlib import Path

STACK = json.loads((Path(__file__).parent / "stack_finance.json").read_text())
WS = STACK["workspace_id"]
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"


def tok():
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", API,
         "--query", "accessToken", "-o", "tsv"]).decode().strip()


def get(url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok()}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read())


def check(kind, item_id):
    try:
        s, b = get(f"{API}/v1/workspaces/{WS}/items/{item_id}")
        print(f"  [OK] {kind:<15s} {item_id}  '{b.get('displayName')}'")
        return True
    except Exception as e:
        print(f"  [FAIL] {kind:<15s} {item_id}  {e}")
        return False


print("Reachability check:")
check("Lakehouse", STACK["lakehouse_id"])
check("SemanticModel", STACK["model_id"])
check("Report", STACK["report_id"])
check("DataAgent", STACK["data_agent_id"])

print("\nWorkspace items:")
s, b = get(f"{API}/v1/workspaces/{WS}/items")
for it in sorted(b.get("value", []), key=lambda x: (x["type"], x["displayName"])):
    print(f"  {it['type']:<18s} {it['displayName']}")

print("\nReport pages:")
s, b = get(f"{API}/v1/workspaces/{WS}/reports/{STACK['report_id']}/pages")
for p in b.get("value", []):
    print(f"  {p.get('displayName')}  ({p.get('name')})")

print("\nShareable URLs:")
print(f"  Workspace:  https://msit.powerbi.com/groups/{WS}/list")
print(f"  Report:     https://msit.powerbi.com/groups/{WS}/reports/{STACK['report_id']}")
print(f"  Model:      https://msit.powerbi.com/groups/{WS}/datasets/{STACK['model_id']}")
print(f"  Data Agent: https://msit.powerbi.com/groups/{WS}/datagents/{STACK['data_agent_id']}")
