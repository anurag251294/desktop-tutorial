"""Reload a graph model, and the ontology's companion graph, from their source tables.

    python scripts/fabric/refresh_graph.py --output cicd/fabric-setup.output.json

**The job type is `RefreshGraph`, not `Refresh`.** `Refresh` returns
`InvalidJobType`, as do `Reload`, `Ingest` and `ApplyChanges`; none of this is in the
docs, and there is no hint in the item payload either -- `GET /items/{id}` returns only
id, type, displayName and description.

Why this script has to exist at all: re-pushing the graph definition only queues a
reload when the definition actually **changed**. Rebuild the gold tables underneath an
unchanged schema and `build_graph_model.py` reports "updating", exits 0, and the graph
keeps serving the previous snapshot. The failure is silent and it looks like success --
every query still works, the counts are simply stale. That cost a full verification
pass before it was noticed: `hasFeature` still read 1,705 after gold_observations had
grown to 3,559.

The ontology is queried through the companion graph Fabric provisions for it
(`<name>_graph_<ontology id without dashes>`), so refreshing the ontology item is not
a thing you can do -- you refresh that graph.

Two behaviours observed on 2026-08-31 that this script cannot paper over:

  * **It took several RefreshGraph runs before the graph served the new rows.** Runs
    reported `Completed` while queries still returned the previous snapshot. The root
    cause was never established -- a SQL analytics endpoint metadata sync in between
    is the suspect, but a refresh after that sync also failed to take. Treat a green
    refresh as necessary and not sufficient, and always re-run query_graph.py.
  * **Refreshing an already-current companion graph can return `Failed` with a bare
    HTTP 500 `UnknownError`.** That is not evidence the graph is broken; verify with
    query_ontology.py before acting on it.

Because of both, this script's exit status is a hint, not a verdict. Note that piping
it (`| tail`) replaces its exit code with the pipe's, so a failure looks like success.
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
        capture_output=True, text=True, shell=(sys.platform == "win32"))
    if out.returncode:
        sys.exit(f"az account get-access-token failed: {out.stderr.strip()}")
    return out.stdout.strip()


def refresh(headers, workspace, item_id, label, poll, timeout_minutes):
    response = requests.post(
        f"{BASE}/workspaces/{workspace}/items/{item_id}/jobs/instances"
        f"?jobType=RefreshGraph", headers=headers, data="{}", timeout=120)
    if response.status_code not in (200, 202):
        print(f"  {label}: queue failed {response.status_code} {response.text[:300]}")
        return False

    instance = response.headers.get("Location", "").rstrip("/").rsplit("/", 1)[-1]
    print(f"  {label}: queued {instance}")
    started, status = time.time(), "NotStarted"
    while status not in TERMINAL:
        if time.time() - started > timeout_minutes * 60:
            print(f"  {label}: still {status} after {timeout_minutes} min")
            return False
        time.sleep(poll)
        poll_response = requests.get(
            f"{BASE}/workspaces/{workspace}/items/{item_id}/jobs/instances/{instance}",
            headers=headers, timeout=120)
        status = poll_response.json().get("status", "Unknown")
    print(f"  {label}: {status} in {int(time.time() - started)}s")
    # A graph reload reports Completed even when an edge type was dropped, so a green
    # result here is necessary and not sufficient -- verify with query_graph.py.
    return status == "Completed"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", default="cicd/fabric-setup.output.json")
    ap.add_argument("--poll-seconds", type=int, default=15)
    ap.add_argument("--timeout-minutes", type=int, default=30)
    args = ap.parse_args()

    setup = json.loads(open(args.output, encoding="utf-8").read())
    workspace = setup["workspace"]["id"]
    headers = {"Authorization": f"Bearer {token()}",
               "Content-Type": "application/json"}

    targets = []
    if "graphModel" in setup:
        targets.append((setup["graphModel"]["id"], setup["graphModel"]["displayName"]))

    if "ontology" in setup:
        suffix = setup["ontology"]["id"].replace("-", "")
        items = requests.get(f"{BASE}/workspaces/{workspace}/items?type=GraphModel",
                             headers=headers, timeout=120).json().get("value", [])
        companion = next((i for i in items if i["displayName"].endswith(suffix)), None)
        if companion:
            targets.append((companion["id"],
                            f"{companion['displayName']} (ontology companion)"))
        else:
            print(f"warning: no companion graph ending {suffix}; ontology not refreshed")

    if not targets:
        sys.exit("nothing to refresh: no graphModel or ontology in the output file")

    print(f"refreshing {len(targets)} graph(s)")
    ok = [refresh(headers, workspace, item_id, label,
                  args.poll_seconds, args.timeout_minutes)
          for item_id, label in targets]

    if not all(ok):
        sys.exit("\none or more refreshes did not complete")
    print("\nall refreshes completed -- now verify counts with query_graph.py "
          "and query_ontology.py; a reload reports Completed even when it dropped rows")


if __name__ == "__main__":
    main()
