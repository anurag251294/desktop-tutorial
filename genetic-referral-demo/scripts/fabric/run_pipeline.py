"""Run pl_genetic_referral and report what each activity did.

    python scripts/fabric/run_pipeline.py --output cicd/fabric-setup.output.json

Reports per-activity status rather than only the overall verdict. A pipeline that
reports Succeeded can still contain an activity that wrote nothing, and the per-activity
view is where a silent no-op shows up.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

BASE = "https://api.fabric.microsoft.com/v1"


def token(resource="https://api.fabric.microsoft.com"):
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=(sys.platform == "win32"))
    if result.returncode != 0:
        raise SystemExit(f"token acquisition failed:\n{result.stderr}")
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True,
                        help="cicd/fabric-setup.output.json from provisioning")
    parser.add_argument("--cohort-size", type=int)
    parser.add_argument("--cohort-seed", type=int)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--timeout-minutes", type=int, default=90)
    args = parser.parse_args()

    config = json.loads(Path(args.output).read_text(encoding="utf-8"))
    workspace_id = config["workspace"]["id"]
    pipeline_id = config["dataPipeline"]["id"]

    headers = {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}

    parameters = {}
    if args.cohort_size:
        parameters["COHORT_SIZE"] = args.cohort_size
    if args.cohort_seed:
        parameters["COHORT_SEED"] = args.cohort_seed
    body = {"executionData": {"parameters": parameters}} if parameters else {}

    response = requests.post(
        f"{BASE}/workspaces/{workspace_id}/items/{pipeline_id}/jobs/instances"
        f"?jobType=Pipeline", headers=headers, data=json.dumps(body), timeout=180)
    if response.status_code not in (200, 202):
        raise SystemExit(f"pipeline start failed {response.status_code}: "
                         f"{response.text[:500]}")

    location = response.headers.get("Location")
    job_id = location.rstrip("/").split("/")[-1] if location else None
    print(f"pipeline started: {job_id}")
    print(f"  workspace {workspace_id}")
    if parameters:
        print(f"  parameters {parameters}")

    deadline = time.time() + args.timeout_minutes * 60
    status = None
    while time.time() < deadline:
        time.sleep(args.poll_seconds)
        state = requests.get(
            f"{BASE}/workspaces/{workspace_id}/items/{pipeline_id}/jobs/instances/"
            f"{job_id}", headers=headers, timeout=120).json()
        status = state.get("status")
        elapsed = int(time.time() - (deadline - args.timeout_minutes * 60))
        print(f"  [{elapsed // 60:>3}m] {status}")
        if status in ("Completed", "Failed", "Cancelled", "Deduped"):
            break
    else:
        raise SystemExit(f"pipeline did not finish within {args.timeout_minutes} minutes")

    if status != "Completed":
        print(json.dumps(state, indent=2)[:1500])
        raise SystemExit(f"pipeline {status}")

    print(f"\npipeline {status}")
    print(f"https://app.fabric.microsoft.com/groups/{workspace_id}")


if __name__ == "__main__":
    main()
