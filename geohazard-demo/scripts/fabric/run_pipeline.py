"""Start pl_bronze_ingestion and poll it to completion, reporting per-activity status.

    python scripts/fabric/run_pipeline.py --output cicd/fabric-setup.output.demo.json \
        [--latitude 49.2193 --longitude -122.5984 --radius-km 20 --analysis-radius-km 3]
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://api.fabric.microsoft.com/v1"


def get_token():
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource",
         "https://api.fabric.microsoft.com", "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=(sys.platform == "win32"),
    )
    if result.returncode != 0:
        raise SystemExit(f"az account get-access-token failed:\n{result.stderr}")
    return result.stdout.strip()


def stamp():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--latitude", type=float)
    parser.add_argument("--longitude", type=float)
    parser.add_argument("--radius-km", type=float)
    parser.add_argument("--analysis-radius-km", type=float)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--timeout-minutes", type=int, default=120)
    args = parser.parse_args()

    deployment = json.loads(Path(args.output).read_text(encoding="utf-8"))
    workspace_id = deployment["workspace"]["id"]
    pipeline_id = deployment["dataPipeline"]["id"]

    headers = {"Authorization": f"Bearer {get_token()}", "Content-Type": "application/json"}

    parameters = {}
    if args.latitude is not None:
        parameters["LATITUDE"] = args.latitude
    if args.longitude is not None:
        parameters["LONGITUDE"] = args.longitude
    if args.radius_km is not None:
        parameters["RADIUS_KM"] = int(args.radius_km)
    if args.analysis_radius_km is not None:
        parameters["ANALYSIS_RADIUS_KM"] = args.analysis_radius_km
    body = {"executionData": {"parameters": parameters}} if parameters else {}

    url = f"{BASE}/workspaces/{workspace_id}/items/{pipeline_id}/jobs/instances?jobType=Pipeline"
    response = requests.post(url, headers=headers, data=json.dumps(body), timeout=120)
    if not response.ok:
        raise SystemExit(f"Failed to start pipeline: {response.status_code}\n{response.text[:600]}")
    location = response.headers.get("Location")
    if not location:
        raise SystemExit("Pipeline start returned no Location header")
    print(f"[{stamp()}] pipeline started  params={parameters or 'defaults'}")
    print(f"[{stamp()}] job: {location}")

    deadline = time.time() + args.timeout_minutes * 60
    last_state = None
    while time.time() < deadline:
        time.sleep(args.poll_seconds)
        try:
            job = requests.get(location, headers=headers, timeout=120).json()
        except Exception as error:
            print(f"[{stamp()}] poll error: {error}")
            continue
        state = job.get("status")
        if state != last_state:
            print(f"[{stamp()}] status: {state}")
            last_state = state
        if state in ("Completed", "Failed", "Cancelled", "Deduped"):
            print(f"\n[{stamp()}] FINAL: {state}")
            if state != "Completed":
                print(json.dumps(job.get("failureReason") or job, indent=2)[:2000])
            # Per-notebook outcome from the Spark session list.
            try:
                sessions = requests.get(
                    f"{BASE}/workspaces/{workspace_id}/spark/livySessions",
                    headers=headers, timeout=120).json().get("value", [])
                sessions.sort(key=lambda s: s.get("submittedDateTime") or "", reverse=True)
                print("\nRecent Spark sessions:")
                for session in sessions[:12]:
                    print(f"  {str(session.get('itemName')):<34} {session.get('state')}")
            except Exception as error:
                print(f"  (could not list Spark sessions: {error})")
            return 0 if state == "Completed" else 1
    print(f"[{stamp()}] timed out after {args.timeout_minutes} minutes")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
