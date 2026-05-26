"""Dump the working hr_demo TMDL structure as a template."""
import base64, json, subprocess, time, urllib.request, urllib.error, uuid
from pathlib import Path

WS = "de6a7e47-474b-4354-87e7-26b8d741f015"
MODEL = "89782e0a-276b-4b86-a2d0-e8238d3c8791"
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"
OUT = Path(__file__).parent / "template_tmdl"
OUT.mkdir(exist_ok=True)


def tok():
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", API,
         "--query", "accessToken", "-o", "tsv"]).decode().strip()


def call(method, url, body=None):
    h = {"Authorization": f"Bearer {tok()}", "Content-Type": "application/json",
         "ActivityId": str(uuid.uuid4())}
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    req = urllib.request.Request(url, headers=h, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


s, h, b = call("POST",
               f"{API}/v1/workspaces/{WS}/semanticModels/{MODEL}/getDefinition?format=TMDL",
               body={})
if s == 202:
    loc = h.get("Location") or h.get("location")
    for i in range(30):
        time.sleep(2)
        sp, hp, bp = call("GET", loc)
        try:
            st = json.loads(bp).get("status")
        except Exception:
            st = None
        if st == "Succeeded":
            sr, hr, br = call("GET", loc.rstrip("/") + "/result")
            payload = json.loads(br)
            break
else:
    payload = json.loads(b)

for p in payload.get("definition", {}).get("parts", []):
    decoded = base64.b64decode(p["payload"]).decode("utf-8", errors="replace")
    fp = OUT / p["path"].replace("/", "__")
    fp.write_text(decoded, encoding="utf-8")
    print(f"  {p['path']}  ({len(decoded)} chars)")
print(f"\n-> {OUT}")
