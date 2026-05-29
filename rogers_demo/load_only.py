"""Re-trigger only the Delta loads (CSVs are already in OneLake).
Uses longer poll timeout and concurrent LRO tracking."""
import json, subprocess, time, urllib.request, urllib.error, uuid, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).parent
STACK = json.loads((ROOT / "stack_rogers.json").read_text())
WS = STACK["workspace_id"]
LH = STACK["lakehouse_id"]
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"

TABLES = [
    "dim_date", "dim_hour", "dim_site", "dim_cell",
    "dim_alarm_type", "dim_customer_segment",
    "fact_cell_kpi", "fact_alarms", "fact_traffic", "fact_customer_impact",
]


def tok():
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", API,
         "--query", "accessToken", "-o", "tsv"]).decode().strip()


def http(method, url, hdr, data=None):
    req = urllib.request.Request(url, headers=hdr, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, dict(r.headers), r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode(errors="replace")


def submit(table):
    """Submit a load and return the polling URL (or None on synchronous success)."""
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
    s, hd, b = http("POST", url, hdr, body)
    if s in (200, 201):
        print(f"  [{table}] submitted synchronous {s}", flush=True)
        return "DONE"
    if s == 202:
        loc = hd.get("Location") or hd.get("location")
        print(f"  [{table}] submitted, polling {loc[:80]}...", flush=True)
        return loc
    print(f"  [{table}] SUBMIT FAIL status={s} body={b[:200]}", flush=True)
    return None


def poll_one(table, loc, attempts=300, delay=4):
    if loc == "DONE":
        return True
    for i in range(attempts):
        time.sleep(delay)
        hdr = {"Authorization": f"Bearer {tok()}"}
        try:
            sp, _, bp = http("GET", loc, hdr)
            st = json.loads(bp).get("status")
        except Exception as e:
            print(f"  [{table}] poll error: {e}", flush=True)
            continue
        if st == "Succeeded":
            print(f"  [{table}] OK after {(i+1)*delay}s", flush=True)
            return True
        if st == "Failed":
            print(f"  [{table}] FAILED: {bp[:300]}", flush=True)
            return False
    print(f"  [{table}] timeout after {attempts*delay}s", flush=True)
    return False


def main():
    print(f"Submitting {len(TABLES)} load jobs...", flush=True)
    submissions = {}
    for t in TABLES:
        submissions[t] = submit(t)
        time.sleep(0.5)

    print("\nPolling LROs...", flush=True)
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {t: ex.submit(poll_one, t, loc) for t, loc in submissions.items() if loc}
        results = {t: f.result() for t, f in futs.items()}

    print("\n== Final ==", flush=True)
    ok = 0
    for t in TABLES:
        r = results.get(t, False)
        print(f"  {t:<32s} {'OK' if r else 'FAIL'}", flush=True)
        if r: ok += 1
    print(f"\n{ok}/{len(TABLES)} loaded", flush=True)


if __name__ == "__main__":
    main()
