import json, subprocess, urllib.request
STACK = json.loads(open(__file__.replace('check_tables.py', 'stack_rogers.json')).read())
WS, LH = STACK['workspace_id'], STACK['lakehouse_id']
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
tok = subprocess.check_output([AZ, "account", "get-access-token", "--resource",
    "https://api.fabric.microsoft.com", "--query", "accessToken", "-o", "tsv"]).decode().strip()
url = f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/lakehouses/{LH}/tables"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
r = urllib.request.urlopen(req, timeout=30)
d = json.loads(r.read())
print(f"{len(d.get('data', []))} tables:")
for t in d.get('data', []):
    print(f"  {t.get('name')}  {t.get('type')}  {t.get('format')}")
