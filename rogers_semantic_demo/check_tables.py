"""List Delta tables in the Rogers Finance lakehouse."""
import json, subprocess, urllib.request
from pathlib import Path

STACK = json.loads((Path(__file__).parent / "stack_finance.json").read_text())
WS, LH = STACK["workspace_id"], STACK["lakehouse_id"]
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"

tok = subprocess.check_output(
    [AZ, "account", "get-access-token", "--resource",
     "https://api.fabric.microsoft.com",
     "--query", "accessToken", "-o", "tsv"]).decode().strip()

url = f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/lakehouses/{LH}/tables"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
data = json.loads(urllib.request.urlopen(req, timeout=30).read())
rows = data.get("data", [])
print(f"{len(rows)} tables:")
for t in rows:
    print(f"  {t.get('name'):<32s} {t.get('type')}  {t.get('format')}")
