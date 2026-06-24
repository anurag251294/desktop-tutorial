"""Upload Rogers Finance CSVs to OneLake and load each into a Delta table.

Mirrors rogers_demo/upload_and_load.py. The load LRO is unreliable on busy
trial capacity; if a `*/load` call sits in NotStarted, fall back to
`load_via_notebook.py` which writes Delta from a Spark notebook.
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path

ROOT = Path(__file__).parent
STACK = json.loads((ROOT / "stack_finance.json").read_text())
WS = STACK["workspace_id"]
LH = STACK["lakehouse_id"]
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"
DFS = "https://onelake.dfs.fabric.microsoft.com"
ONELAKE_RES = "https://storage.azure.com"

TABLES = [
    "dim_date", "dim_business_unit", "dim_product", "dim_region",
    "dim_customer_segment", "dim_channel",
    "fact_revenue_monthly", "fact_subscribers_monthly",
    "fact_churn_monthly", "fact_costs_monthly",
]

CHUNK = 3 * 1024 * 1024  # 3 MB write chunks


def tok(res=API):
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", res,
         "--query", "accessToken", "-o", "tsv"]).decode().strip()


def http(method, url, hdr, data=None):
    req = urllib.request.Request(url, headers=hdr, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, dict(r.headers), r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode(errors="replace")


def upload(table):
    src = ROOT / "csv" / f"{table}.csv"
    if not src.exists():
        print(f"  [{table}] MISSING {src}")
        return False
    data = src.read_bytes()
    rel = f"Files/csv/{table}.csv"
    base = f"{DFS}/{WS}/{LH}/{rel}"
    hdr = {"Authorization": f"Bearer {tok(ONELAKE_RES)}",
           "x-ms-version": "2021-12-02"}
    # Create
    s, h, b = http("PUT", base + "?resource=file", hdr)
    if s not in (200, 201):
        print(f"  [{table}] create FAIL {s}: {b[:200]}")
        return False
    # Append (chunked)
    pos = 0
    while pos < len(data):
        chunk = data[pos:pos + CHUNK]
        hdr2 = {**hdr,
                "Content-Length": str(len(chunk)),
                "Content-Type": "application/octet-stream"}
        s, h, b = http("PATCH",
                       f"{base}?action=append&position={pos}", hdr2, chunk)
        if s not in (200, 202):
            print(f"  [{table}] append FAIL {s}: {b[:200]}")
            return False
        pos += len(chunk)
    # Flush
    hdr3 = {**hdr, "Content-Length": "0"}
    s, h, b = http("PATCH",
                   f"{base}?action=flush&position={len(data)}", hdr3)
    if s not in (200, 202):
        print(f"  [{table}] flush FAIL {s}: {b[:200]}")
        return False
    print(f"  [{table}] uploaded {len(data):>9,} bytes")
    return True


def load_to_delta(table):
    hdr = {"Authorization": f"Bearer {tok()}",
           "Content-Type": "application/json",
           "ActivityId": str(uuid.uuid4())}
    url = f"{API}/v1/workspaces/{WS}/lakehouses/{LH}/tables/{table}/load"
    body = json.dumps({
        "relativePath": f"Files/csv/{table}.csv",
        "pathType": "File",
        "mode": "Overwrite",
        "recursive": False,
        "formatOptions": {"format": "Csv", "header": True, "delimiter": ","},
    }).encode()
    s, h, b = http("POST", url, hdr, body)
    if s in (200, 201):
        print(f"  [{table}] loaded synchronously")
        return True
    if s != 202:
        print(f"  [{table}] load submit FAIL {s}: {b[:200]}")
        return False
    loc = h.get("Location") or h.get("location")
    for i in range(180):
        time.sleep(3)
        sp, hp, bp = http("GET", loc, {"Authorization": f"Bearer {tok()}"})
        try:
            st = json.loads(bp).get("status")
        except Exception:
            st = None
        if st == "Succeeded":
            print(f"  [{table}] loaded after ~{(i+1)*3}s")
            return True
        if st == "Failed":
            print(f"  [{table}] LOAD FAILED: {bp[:400]}")
            return False
    print(f"  [{table}] load TIMEOUT (try load_via_notebook.py)")
    return False


def main():
    print("== Upload phase ==")
    uploaded = [t for t in TABLES if upload(t)]
    print(f"\n{len(uploaded)}/{len(TABLES)} uploaded\n")
    print("== Delta load phase ==")
    ok = sum(load_to_delta(t) for t in uploaded)
    print(f"\n{ok}/{len(uploaded)} loaded as Delta")


if __name__ == "__main__":
    main()
