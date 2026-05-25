"""Upload all CSVs in csv/ to OneLake Files/csv/, then load each to Delta
via /lakehouses/{id}/tables/{name}/load."""
from __future__ import annotations

import json
import subprocess
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path

ROOT = Path(__file__).parent
STACK = json.loads((ROOT / "stack_ctc.json").read_text())
WS = STACK["workspace_id"]
LH = STACK["lakehouse_id"]
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"
ONELAKE = "https://onelake.dfs.fabric.microsoft.com"
TARGET = "csv"
CSV_DIR = ROOT / "csv"

TABLES = [
    "dim_date",
    "dim_sku",
    "dim_vendor",
    "dim_season",
    "fact_sku_performance",
    "fact_in_season",
    "fact_connected_inventory",
]


def tok(resource):
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"]).decode().strip()


def http(method, url, headers, data=None):
    req = urllib.request.Request(url, headers=headers, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, dict(r.headers), r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode(errors="replace")


def upload(local: Path, remote: str) -> bool:
    h = {"Authorization": f"Bearer {tok('https://storage.azure.com')}"}
    base = f"{ONELAKE}/{WS}/{LH}/Files/{TARGET}/{remote}"
    data = local.read_bytes()
    s, _, b = http("PUT", base + "?resource=file", h)
    if s not in (200, 201):
        print(f"    CREATE failed {s}: {b[:300]}")
        return False
    h2 = dict(h, **{"Content-Length": str(len(data))})
    s, _, b = http("PATCH", base + "?action=append&position=0", h2, data)
    if s not in (200, 202):
        print(f"    APPEND failed {s}: {b[:300]}")
        return False
    s, _, b = http("PATCH", base + f"?action=flush&position={len(data)}", h)
    if s not in (200, 201):
        print(f"    FLUSH failed {s}: {b[:300]}")
        return False
    return True


def load_to_delta(table: str) -> bool:
    h = {"Authorization": f"Bearer {tok(API)}",
         "Content-Type": "application/json",
         "ActivityId": str(uuid.uuid4())}
    url = f"{API}/v1/workspaces/{WS}/lakehouses/{LH}/tables/{table}/load"
    body = json.dumps({
        "relativePath": f"Files/{TARGET}/{table}.csv",
        "pathType": "File",
        "mode": "Overwrite",
        "recursive": False,
        "formatOptions": {"format": "Csv", "header": True, "delimiter": ","},
    }).encode()
    s, hd, b = http("POST", url, h, body)
    if s not in (200, 201, 202):
        print(f"    LOAD {table}: status={s} body={b[:300]}")
        return False
    loc = hd.get("Location") or hd.get("location")
    if not loc:
        return True
    for i in range(60):
        time.sleep(2)
        sp, _, bp = http("GET", loc, {"Authorization": f"Bearer {tok(API)}"})
        try:
            st = json.loads(bp).get("status")
        except Exception:
            st = None
        if st == "Succeeded":
            return True
        if st == "Failed":
            print(f"    LOAD {table} FAILED: {bp[:300]}")
            return False
    print(f"    LOAD {table} timeout")
    return False


def main():
    print(f"== Uploading CSVs to Files/{TARGET}/ ==")
    for t in TABLES:
        local = CSV_DIR / f"{t}.csv"
        if not local.exists():
            print(f"  MISSING: {local}")
            continue
        print(f"  {t}.csv  ({local.stat().st_size:,} bytes)", end="  ")
        print("OK" if upload(local, f"{t}.csv") else "FAIL")

    print(f"\n== Loading to Delta tables ==")
    ok = 0
    for t in TABLES:
        if load_to_delta(t):
            print(f"  {t:<32s} OK")
            ok += 1
        else:
            print(f"  {t:<32s} FAIL")
    print(f"\n{ok}/{len(TABLES)} tables loaded")


if __name__ == "__main__":
    main()
