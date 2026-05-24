"""Add 3 RLS roles to InteracHR_Model via Fabric API.

Roles:
  1. HR Business Partner   — read all (no filter)
  2. People Manager        — sees self + direct reports
  3. Compliance Officer    — sees only employees in Risk & Compliance function

Strategy: fetch current TMDL, add roles/*.tmdl parts, add ref role lines
to model.tmdl, push back via updateDefinition.
"""
from __future__ import annotations

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
API = "https://api.fabric.microsoft.com"
ROOT = Path(__file__).parent


def token() -> str:
    return subprocess.check_output(
        [AZ, "account", "get-access-token",
         "--resource", API,
         "--query", "accessToken", "-o", "tsv"]
    ).decode().strip()


def call(method, url, body=None):
    headers = {"Authorization": f"Bearer {token()}",
               "ActivityId": str(uuid.uuid4()),
               "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, headers=headers, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def poll(loc):
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
            return True, loc.rstrip("/") + "/result"
        if st == "Failed":
            print(f"  FAILED: {bp}")
            return False, None
    return False, None


def get_definition():
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WORKSPACE_ID}"
                   f"/semanticModels/{MODEL_ID}/getDefinition?format=TMDL",
                   body={})
    if s == 202:
        loc = h.get("Location") or h.get("location")
        print(f"  polling getDefinition: {loc}")
        ok, result_url = poll(loc)
        if not ok:
            raise RuntimeError("getDefinition failed")
        s2, h2, b2 = call("GET", result_url)
        return json.loads(b2)
    return json.loads(b)


# -------- Role TMDL templates --------

ROLES = [
    {
        "name": "HR Business Partner",
        "file_name": "HR Business Partner.tmdl",
        "tmdl": """role 'HR Business Partner'
\tmodelPermission: read

\tannotation PBI_Id = {uid}
""".format(uid=str(uuid.uuid4())),
    },
    {
        "name": "People Manager",
        "file_name": "People Manager.tmdl",
        # USERPRINCIPALNAME() returns the UPN of the user querying the model.
        # For demo: in "View as role", set Other user = an employee_id (e.g.
        # EMP-00007) and the filter activates, restricting to that manager's
        # direct reports + themselves.
        "tmdl": """role 'People Manager'
\tmodelPermission: read

\ttablePermission dim_employee = [manager_id] = USERPRINCIPALNAME() || [employee_id] = USERPRINCIPALNAME()

\tannotation PBI_Id = {uid}
""".format(uid=str(uuid.uuid4())),
    },
    {
        "name": "Compliance Officer",
        "file_name": "Compliance Officer.tmdl",
        # Compliance officer sees employees only within the Risk & Compliance
        # function (for org-internal conflict review), but has full visibility
        # of compliance facts (training + attestations).
        "tmdl": """role 'Compliance Officer'
\tmodelPermission: read

\ttablePermission dim_employee = RELATED(dim_department[function]) = "Risk & Compliance"

\tannotation PBI_Id = {uid}
""".format(uid=str(uuid.uuid4())),
    },
]


def main():
    print("Fetching current TMDL definition...")
    payload = get_definition()
    parts_list = payload.get("definition", {}).get("parts", [])
    parts = {}
    for p in parts_list:
        parts[p["path"]] = base64.b64decode(p["payload"]).decode("utf-8", errors="replace")
    print(f"  Loaded {len(parts)} existing parts")

    # 1. Add role parts
    for r in ROLES:
        path = f"definition/roles/{r['file_name']}"
        parts[path] = r["tmdl"]
        print(f"  Added role: {r['name']}")

    # 2. Add ref role lines to model.tmdl (if not already present)
    model_path = "definition/model.tmdl"
    model_tmdl = parts[model_path]
    if "ref role " not in model_tmdl:
        # Append after the last ref table line
        lines = model_tmdl.rstrip("\n").split("\n")
        # Find the last ref table line index
        last_table_idx = max(i for i, ln in enumerate(lines) if ln.startswith("ref table"))
        # Insert role refs after it
        role_refs = [""] + [f"ref role '{r['name']}'" for r in ROLES] + [""]
        new_lines = lines[:last_table_idx + 1] + role_refs + lines[last_table_idx + 1:]
        parts[model_path] = "\n".join(new_lines) + "\n"
        print(f"  Added {len(ROLES)} ref role lines to model.tmdl")
    else:
        print("  model.tmdl already references roles (skipping)")

    # 3. Build payload
    payload_parts = []
    for path, content in parts.items():
        payload_parts.append({
            "path": path,
            "payload": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "payloadType": "InlineBase64",
        })
    update_payload = {
        "definition": {"format": "TMDL", "parts": payload_parts}
    }

    # 4. POST updateDefinition
    print("\nPOSTing updateDefinition with roles...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WORKSPACE_ID}"
                   f"/semanticModels/{MODEL_ID}/updateDefinition",
                   body=update_payload)
    print(f"  status={s}")
    if s == 202:
        loc = h.get("Location") or h.get("location")
        print(f"  polling {loc}")
        ok, _ = poll(loc)
        if ok:
            print("\n  Roles added successfully.")
            return
        print("\n  Update failed.")
    elif s in (200, 201):
        print("  OK (sync)")
    else:
        print(f"  ERROR body: {b[:800]}")


if __name__ == "__main__":
    main()
