"""Load each CSV in Files/csv/ into a Delta table via the Lakehouse Load API.

Uses POST /v1/workspaces/{ws}/lakehouses/{lh}/tables/{tableName}/load.
Async - returns a 202 with a Location header; we poll until Succeeded.
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.request
import urllib.error
import uuid

WORKSPACE_ID = "2690ef29-1370-476c-b28c-58a505fea2bd"
LAKEHOUSE_ID = "454b4c50-e93e-4ce6-9c17-1d03a6ed9d6a"
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"

# (csv filename, target Delta table name)
TABLES = [
    ("dim_date.csv",                 "dim_date"),
    ("dim_department.csv",           "dim_department"),
    ("dim_role.csv",                 "dim_role"),
    ("dim_location.csv",             "dim_location"),
    ("dim_employee.csv",             "dim_employee"),
    ("fact_headcount_snapshot.csv",  "fact_headcount_snapshot"),
    ("fact_attrition.csv",           "fact_attrition"),
    ("fact_compensation.csv",        "fact_compensation"),
    ("fact_recruitment.csv",         "fact_recruitment"),
    ("fact_training_completion.csv", "fact_training_completion"),
    ("fact_attestation.csv",         "fact_attestation"),
]


def token() -> str:
    return subprocess.check_output(
        [AZ, "account", "get-access-token",
         "--resource", "https://api.fabric.microsoft.com",
         "--query", "accessToken", "-o", "tsv"]
    ).decode().strip()


def call(method: str, url: str, body=None, extra_headers=None):
    headers = {"Authorization": f"Bearer {token()}",
               "ActivityId": str(uuid.uuid4()),
               "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, headers=headers, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def load_table(csv_name: str, table_name: str) -> bool:
    url = (f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE_ID}"
           f"/lakehouses/{LAKEHOUSE_ID}/tables/{table_name}/load")
    body = {
        "relativePath": f"Files/csv/{csv_name}",
        "pathType": "File",
        "mode": "Overwrite",
        "recursive": False,
        "formatOptions": {
            "format": "Csv",
            "header": True,
            "delimiter": ",",
        },
    }
    status, headers, content = call("POST", url, body=body)
    print(f"  {table_name:<30s} -> {status}", end="")
    if status not in (200, 201, 202):
        print(f"  body: {content[:300]}")
        return False
    loc = headers.get("Location") or headers.get("location")
    if not loc:
        print(f"  (sync ok)")
        return True
    # Poll
    for i in range(60):
        time.sleep(2)
        s, h, b = call("GET", loc)
        try:
            op = json.loads(b)
            st = op.get("status")
        except Exception:
            st = None
        if st == "Succeeded":
            print(f"  Succeeded after {(i+1)*2}s")
            return True
        if st == "Failed":
            print(f"  FAILED: {b[:400]}")
            return False
    print("  TIMEOUT")
    return False


def main():
    print(f"Loading {len(TABLES)} tables into InteracHR_Lakehouse...")
    ok = 0
    for csv_name, table_name in TABLES:
        if load_table(csv_name, table_name):
            ok += 1
    print(f"\n{ok}/{len(TABLES)} tables loaded successfully.")


if __name__ == "__main__":
    main()
