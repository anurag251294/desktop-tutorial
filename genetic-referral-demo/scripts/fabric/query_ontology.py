"""Verify the ontology actually loaded: every entity type, every relationship type.

    python scripts/fabric/query_ontology.py --output cicd/fabric-setup.output.json

An ontology can look completely healthy and be empty. The definition round-trips, the
canvas renders all six entity types, and the item reports no error -- while nothing has
been ingested at all. So this counts instances of every entity type and every
relationship type separately and fails loudly on any that come back zero, because a
single silently-empty relationship is the failure mode that matters and it is invisible
from the UI.

Two behaviours to know before reading a result here:

* Ontology instances are queried through the **companion graph** the ontology
  provisions (`<ontology>_graph_<guid>`), not through the ontology item itself. This
  script finds that graph by name rather than requiring its ID to be configured.
* `GraphNotQueryable` means a load is in flight, not that the model is broken. Every
  definition write queues a refresh that takes a couple of minutes, so running this
  immediately after `build_ontology.py` will report a load in progress; that is
  expected, and `--wait` will sit on it until it clears.

Expected on the demo data: 18,731 instances across the six entity types and 35,216
across the five relationship types -- the same totals as the graph, since both declare
the same model over the same gold tables.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

BASE = "https://api.fabric.microsoft.com/v1"

ENTITY_TYPES = ["Patient", "Feature", "BodySystem", "Criterion", "Encounter", "Specialty"]

# (relationship, source entity, target entity)
RELATIONSHIP_TYPES = [
    ("hasFeature", "Patient", "Feature"),
    ("inBodySystem", "Feature", "BodySystem"),
    ("surfacedBy", "Patient", "Criterion"),
    ("attendedEncounter", "Patient", "Encounter"),
    ("encounterWithSpecialty", "Encounter", "Specialty"),
]


def token():
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource",
         "https://api.fabric.microsoft.com", "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True)
    value = result.stdout.strip()
    if not value:
        raise SystemExit(f"could not get a Fabric token: {result.stderr.strip()[:300]}")
    return value


def run(url, headers, query):
    """Returns (count, error). Application errors arrive as HTTP 200 -- see query_graph."""
    response = requests.post(url, headers=headers, timeout=180,
                             data=json.dumps({"query": query}))
    if response.status_code != 200:
        try:
            code = response.json().get("errorCode", "")
        except ValueError:
            code = ""
        return None, f"HTTP {response.status_code} {code}"
    payload = response.json()
    code = payload.get("status", {}).get("code", "?????")
    if code[:2] not in ("00", "01", "02", "03"):
        return None, f"{code} {payload.get('status', {}).get('description', '')[:120]}"
    rows = payload.get("result", {}).get("data", [])
    return (rows[0].get("n") if rows else 0), None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="cicd/fabric-setup.output.json")
    parser.add_argument("--wait", type=int, default=0,
                        help="seconds to keep retrying while a load is in flight")
    args = parser.parse_args()

    config = json.loads(Path(args.output).read_text(encoding="utf-8"))
    workspace_id = config["workspace"]["id"]
    ontology = config.get("ontology")
    if not ontology:
        raise SystemExit("no ontology in the config -- run build_ontology.py first")

    headers = {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}

    # The companion graph is named after the ontology's own ID, without dashes.
    suffix = ontology["id"].replace("-", "")
    items = requests.get(f"{BASE}/workspaces/{workspace_id}/items",
                         headers=headers, timeout=120).json().get("value", [])
    graph = next((i for i in items if i["type"] == "GraphModel"
                  and i["displayName"].endswith(suffix)), None)
    if not graph:
        raise SystemExit(
            f"no companion graph ending {suffix} -- if it was deleted the ontology "
            f"cannot load and the item must be rebuilt")
    url = (f"{BASE}/workspaces/{workspace_id}/GraphModels/{graph['id']}"
           f"/executeQuery?preview=true")

    deadline = time.time() + args.wait
    while True:
        count, error = run(url, headers, "MATCH (n:Patient) RETURN COUNT(n) AS n")
        if error and "GraphNotQueryable" in error and time.time() < deadline:
            print("  load in flight, waiting...")
            time.sleep(30)
            continue
        break
    if error:
        raise SystemExit(f"ontology not queryable: {error}")

    print(f"ontology  : {ontology['displayName']} ({ontology['id']})")
    print(f"graph     : {graph['displayName']}\n")

    failures, nodes, edges = [], 0, 0

    print("  entity types")
    for entity in ENTITY_TYPES:
        count, error = run(url, headers, f"MATCH (n:{entity}) RETURN COUNT(n) AS n")
        flag = ""
        if error:
            flag, failures = f"  ERROR {error}", failures + [entity]
        elif not count:
            flag, failures = "  <-- EMPTY", failures + [entity]
        else:
            nodes += int(count)
        print(f"    {entity:<24} {count if count is not None else '-':>8}{flag}")

    print("\n  relationship types")
    for name, source, target in RELATIONSHIP_TYPES:
        count, error = run(url, headers,
                           f"MATCH (:{source})-[r:{name}]->(:{target}) "
                           f"RETURN COUNT(r) AS n")
        flag = ""
        if error:
            flag, failures = f"  ERROR {error}", failures + [name]
        elif not count:
            flag, failures = "  <-- EMPTY", failures + [name]
        else:
            edges += int(count)
        print(f"    {name:<24} {count if count is not None else '-':>8}{flag}")

    print(f"\n  {nodes:,} instances / {edges:,} relationships")

    if failures:
        print(f"\nFAILED: {len(failures)} empty or erroring -- {', '.join(failures)}")
        sys.exit(1)
    print(f"\nOK: {len(ENTITY_TYPES)}/{len(ENTITY_TYPES)} entity types, "
          f"{len(RELATIONSHIP_TYPES)}/{len(RELATIONSHIP_TYPES)} relationship types")


if __name__ == "__main__":
    main()
