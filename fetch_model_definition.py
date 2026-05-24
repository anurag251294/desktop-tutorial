"""Fetch the current TMDL definition of the InteracHR_Model semantic model.

Saves each part to ./model_current/ so we can see the structure before
generating the modified definition with relationships + measures.
"""
import base64
import json
import subprocess
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path

WORKSPACE_ID = "2690ef29-1370-476c-b28c-58a505fea2bd"
MODEL_ID = "00bb5cc7-20c0-4030-ae35-25a2ec02bc87"
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
OUT = Path(__file__).parent / "model_current"
OUT.mkdir(exist_ok=True)


def token() -> str:
    return subprocess.check_output(
        [AZ, "account", "get-access-token",
         "--resource", "https://api.fabric.microsoft.com",
         "--query", "accessToken", "-o", "tsv"]
    ).decode().strip()


def call(method, url, body=None):
    headers = {"Authorization": f"Bearer {token()}",
               "ActivityId": str(uuid.uuid4()),
               "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, headers=headers, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def main():
    # Request TMDL format explicitly
    url = (f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE_ID}"
           f"/semanticModels/{MODEL_ID}/getDefinition?format=TMDL")
    s, h, b = call("POST", url, body={})
    print(f"getDefinition -> {s}")
    if s == 202:
        loc = h.get("Location") or h.get("location")
        print(f"  polling {loc}")
        for i in range(60):
            time.sleep(2)
            sp, hp, bp = call("GET", loc)
            try:
                op = json.loads(bp)
                st = op.get("status")
            except Exception:
                st = None
            print(f"  poll {i+1}: status={st}")
            if st == "Succeeded":
                # Result at loc + /result
                sr, hr, br = call("GET", loc.rstrip("/") + "/result")
                print(f"  result -> {sr}, {len(br)} chars")
                b = br
                break
            if st == "Failed":
                print(f"  FAILED: {bp}")
                return
    payload = json.loads(b)
    parts = payload.get("definition", {}).get("parts", [])
    print(f"\nDefinition has {len(parts)} parts (format={payload.get('definition', {}).get('format')}):")
    for p in parts:
        path = p["path"]
        decoded = base64.b64decode(p["payload"]).decode("utf-8", errors="replace")
        out_file = OUT / path.replace("/", "__")
        out_file.write_text(decoded, encoding="utf-8")
        print(f"  {path}  ({len(decoded)} chars)  -> {out_file.name}")


if __name__ == "__main__":
    main()
