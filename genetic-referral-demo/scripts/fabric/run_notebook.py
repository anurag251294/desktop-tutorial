"""Run one notebook by display name and wait for it.

Three notebooks sit outside `pl_genetic_referral` on purpose -- `gold_signal_latency`,
`gold_graph_dimensions` and `gold_cohort_summary` are re-run independently of a cohort
rebuild. Before this they were run by hand in the portal, which is fine until you are
mid-rebuild and need four of them in order.

    python scripts/fabric/run_notebook.py --output cicd/fabric-setup.output.json \
        --notebook gold_signal_latency gold_graph_dimensions gold_cohort_summary

Notes on the job API, both learned the hard way:

  * The run is queued with an empty body. Passing `{}` is fine; passing
    `executionData` without a valid payload gets a 400 that names no field.
  * A failed notebook still returns HTTP 200 on the poll. The outcome is in
    `status`, and `failureReason` is null for a notebook that raised -- you have to
    open the run to see the traceback, so this prints the run URL on failure.
"""
import argparse
import json
import subprocess
import sys
import time

import requests

BASE = "https://api.fabric.microsoft.com/v1"
TERMINAL = {"Completed", "Failed", "Cancelled", "Deduped"}


def token(resource="https://api.fabric.microsoft.com"):
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"],
        # shell=True on Windows: az is az.cmd, which CreateProcess will not
        # find from a bare "az". Matches provision_fabric_demo.py.
        capture_output=True, text=True, shell=(sys.platform == "win32"))
    if out.returncode:
        sys.exit(f"az account get-access-token failed: {out.stderr.strip()}")
    return out.stdout.strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", required=True, help="cicd/fabric-setup.output.json")
    ap.add_argument("--notebook", nargs="+", required=True,
                    help="display names, run in the order given")
    ap.add_argument("--poll-seconds", type=int, default=20)
    ap.add_argument("--timeout-minutes", type=int, default=45)
    args = ap.parse_args()

    setup = json.loads(open(args.output, encoding="utf-8").read())
    workspace = setup["workspace"]["id"]
    by_name = {n["displayName"]: n["id"] for n in setup["notebooks"]}

    missing = [n for n in args.notebook if n not in by_name]
    if missing:
        sys.exit(f"not in {args.output}: {missing}\navailable: {sorted(by_name)}")

    headers = {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}
    failed = []

    for name in args.notebook:
        item = by_name[name]
        started = time.time()
        response = requests.post(
            f"{BASE}/workspaces/{workspace}/items/{item}/jobs/instances"
            f"?jobType=RunNotebook", headers=headers, data="{}", timeout=180)
        if response.status_code not in (200, 202):
            sys.exit(f"{name}: queue failed {response.status_code} {response.text[:400]}")

        location = response.headers.get("Location", "")
        instance = location.rstrip("/").rsplit("/", 1)[-1] if location else None
        if not instance:
            sys.exit(f"{name}: no Location header on the queued job")

        print(f"{name:26} queued  {instance}")
        status = "NotStarted"
        while status not in TERMINAL:
            if time.time() - started > args.timeout_minutes * 60:
                sys.exit(f"{name}: still {status} after {args.timeout_minutes} min")
            time.sleep(args.poll_seconds)
            poll = requests.get(
                f"{BASE}/workspaces/{workspace}/items/{item}/jobs/instances/{instance}",
                headers=headers, timeout=120)
            status = poll.json().get("status", "Unknown")
            print(f"  {int(time.time() - started):>4}s  {status}")

        if status != "Completed":
            # failureReason is null for a notebook that raised, so point at the run.
            print(f"  FAILED -- open the run for the traceback:\n"
                  f"  https://app.fabric.microsoft.com/groups/{workspace}"
                  f"/synapsenotebooks/{item}")
            failed.append(name)
        else:
            print(f"  {name} completed in {int(time.time() - started)}s")

    if failed:
        sys.exit(f"\nfailed: {failed}")
    print(f"\nall {len(args.notebook)} notebooks completed")


if __name__ == "__main__":
    main()
