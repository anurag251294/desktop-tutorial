"""Remove all RLS roles from hr_demo via Fabric API.

Strategy:
  1. Fetch current TMDL
  2. Drop every part under `definition/roles/`
  3. Strip every `ref role '...'` line out of model.tmdl
  4. Push back via updateDefinition
"""
from __future__ import annotations

import base64
import json
import subprocess
import time
import urllib.request
import urllib.error
import uuid

WS = "de6a7e47-474b-4354-87e7-26b8d741f015"
MODEL = "89782e0a-276b-4b86-a2d0-e8238d3c8791"
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"


def tok():
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", API,
         "--query", "accessToken", "-o", "tsv"]).decode().strip()


def call(method, url, body=None):
    h = {"Authorization": f"Bearer {tok()}",
         "Content-Type": "application/json",
         "ActivityId": str(uuid.uuid4())}
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    req = urllib.request.Request(url, headers=h, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def poll(loc):
    for i in range(60):
        time.sleep(2)
        s, h, b = call("GET", loc)
        try:
            st = json.loads(b).get("status")
        except Exception:
            st = None
        print(f"  poll {i+1}: status={st}")
        if st == "Succeeded":
            return True, loc.rstrip("/") + "/result"
        if st == "Failed":
            print(f"  FAILED: {b[:600]}")
            return False, None
    return False, None


def main():
    print("Fetching hr_demo TMDL...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/semanticModels/{MODEL}"
                   f"/getDefinition?format=TMDL", body={})
    if s == 202:
        loc = h.get("Location") or h.get("location")
        ok, result_url = poll(loc)
        if not ok:
            return
        s2, h2, b2 = call("GET", result_url)
        payload = json.loads(b2)
    else:
        payload = json.loads(b)

    parts = {p["path"]: base64.b64decode(p["payload"]).decode("utf-8", errors="replace")
             for p in payload["definition"]["parts"]}
    print(f"  Loaded {len(parts)} parts")

    role_parts = [p for p in parts if p.startswith("definition/roles/")]
    if not role_parts:
        print("  No role parts found.")
    else:
        for rp in role_parts:
            print(f"  Dropping {rp}")
            del parts[rp]

    model_path = "definition/model.tmdl"
    if model_path in parts:
        before = parts[model_path]
        new_lines = [ln for ln in before.split("\n")
                     if not ln.lstrip().startswith("ref role ")]
        after = "\n".join(new_lines)
        if before != after:
            removed = before.count("\nref role ") + (1 if before.startswith("ref role ") else 0)
            print(f"  Removed {removed} 'ref role' line(s) from model.tmdl")
            parts[model_path] = after
        else:
            print("  No 'ref role' lines in model.tmdl")

    if not role_parts and parts.get(model_path) == before:
        print("\nNothing to remove. Exiting.")
        return

    payload_parts = [{"path": p,
                      "payload": base64.b64encode(c.encode("utf-8")).decode("ascii"),
                      "payloadType": "InlineBase64"} for p, c in parts.items()]

    print("\nPOSTing updateDefinition (RLS removed)...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/semanticModels/{MODEL}/updateDefinition",
                   body={"definition": {"format": "TMDL", "parts": payload_parts}})
    print(f"  status={s}")
    if s == 202:
        loc = h.get("Location") or h.get("location")
        ok, _ = poll(loc)
        if ok:
            print("\n  RLS removed from hr_demo.")
        else:
            print("\n  Update failed.")
    elif s in (200, 201):
        print("  OK (sync). RLS removed from hr_demo.")
    else:
        print(f"  ERROR: {b[:800]}")


if __name__ == "__main__":
    main()
