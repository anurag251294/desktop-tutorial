"""Pin the data agent to a canonical run and deselect unbounded geometry/JSON columns.

    python scripts/fabric/harden_data_agent.py --canonical <run-id> \
        --superseded <run-id> --superseded <run-id>

Two defects this fixes, both found by driving the published agent through its portal
chat rather than through the SDK:

1. The stock instruction "if the caller has not supplied a run_id, use the most recent
   one" is unimplementable. Run IDs are UUIDs and carry no ordering, so the agent
   guessed -- and on an open-ended question ("what are the historical trends across all
   my data?") it picked a superseded pre-fix run, reported its inflated risk figures as
   current, and described the canonical run as "an older run". Naming the canonical run
   is the only reliable fix short of deleting the stale partitions.

2. `FabricDataAgentDatasource.select()` selects a whole table, columns included. The
   configure notebook documented `geometry_wkt` / `properties_json` / `geometry_json`
   as excluded, but nothing excluded them, so a SELECT * could return a wall of
   coordinates. There is no per-column SDK call; the selection flags live in the item
   definition, so patch that.

Both stages are written to the draft AND published configs, because the published copy
is what answers questions -- patching only the draft changes nothing until someone
clicks Publish in the portal.

The original definition is saved next to the output first, so this is revertible.
"""
import argparse
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

BASE = "https://api.fabric.microsoft.com/v1"

# Columns that hold unbounded geometry or raw source JSON. Useful in the lakehouse,
# useless in a chat answer, and expensive in tokens.
DROP_COLUMNS = {
    "silver_source_features": {"geometry_wkt", "properties_json"},
    "gold_rf1_risk_hotspots": {"geometry_json"},
    "gold_rf1_risk_areas": {"geometry_json"},
}

OLD_RULE = """Filter every query by run_id. If the caller has not supplied one, use the most recent
run_id present in the tables and state clearly which run you used. Never mix runs in a
single answer."""


def new_rule(canonical, superseded):
    listed = "\n".join("  " + run for run in superseded) or "  (none)"
    return f"""Filter every query by run_id and state clearly which run you used. Never mix runs in a
single answer.

If asked about trends, history, or "all my data", do not compare runs. Answer for the
canonical run and add one sentence explaining that cross-run comparison is not
meaningful here because the other runs are superseded. Never refuse outright.

The canonical run is {canonical}. Use it whenever the
caller has not named a run, including for any open-ended question about "the data",
"the latest results", or "trends". Run IDs are UUIDs and carry no ordering, so never
infer which run is newest by sorting them.

These runs are SUPERSEDED and must never be used or reported:
{listed}
They were produced before a soil-attribute decoding fix and overstate risk severely. If
a caller names one, say it is superseded and answer for the canonical run instead."""


def token():
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource", "https://api.fabric.microsoft.com",
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=(sys.platform == "win32"))
    if result.returncode != 0:
        raise SystemExit(f"token acquisition failed:\n{result.stderr}")
    return result.stdout.strip()


def poll(location, headers):
    """updateDefinition and getDefinition are long-running; follow the Location header."""
    for _ in range(60):
        time.sleep(5)
        state = requests.get(location, headers=headers, timeout=120).json()
        if state.get("status") in ("Succeeded", "Failed"):
            return state
    raise SystemExit("long-running operation did not settle")


def deselect(node, dropped, table=None):
    if isinstance(node, dict):
        if node.get("type") == "lakehouse_tables.table":
            table = node.get("display_name")
        if (node.get("type") == "lakehouse_tables.column"
                and node.get("display_name") in DROP_COLUMNS.get(table, ())
                and node.get("is_selected")):
            node["is_selected"] = False
            dropped.append(f"{table}.{node['display_name']}")
        for value in node.values():
            deselect(value, dropped, table)
    elif isinstance(node, list):
        for value in node:
            deselect(value, dropped, table)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="cicd/fabric-setup.output.demo.json")
    parser.add_argument("--workspace-id")
    parser.add_argument("--agent-id")
    parser.add_argument("--canonical", required=True)
    parser.add_argument("--superseded", action="append", default=[])
    parser.add_argument("--backup", default="cicd/data-agent-definition.backup.json")
    args = parser.parse_args()

    workspace_id, agent_id = args.workspace_id, args.agent_id
    if not (workspace_id and agent_id):
        config = json.loads(Path(args.output).read_text(encoding="utf-8"))
        workspace_id = workspace_id or config.get("workspaceId")
        agent_id = agent_id or (config.get("dataAgents") or {}).get("geohazard_data_agent")
    if not (workspace_id and agent_id):
        raise SystemExit("workspace id / agent id not resolved; pass them explicitly")

    headers = {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}

    response = requests.post(f"{BASE}/workspaces/{workspace_id}/items/{agent_id}/getDefinition",
                             headers=headers, timeout=300)
    if response.status_code == 202:
        poll(response.headers["Location"], headers)
        response = requests.get(response.headers["Location"].rstrip("/") + "/result",
                                headers=headers, timeout=120)
    if not response.ok:
        raise SystemExit(f"getDefinition failed {response.status_code}: {response.text[:400]}")

    definition = response.json()["definition"]
    Path(args.backup).write_text(json.dumps(definition), encoding="utf-8")
    print(f"backed up original definition -> {args.backup}")

    rewritten, dropped = 0, []
    for part in definition["parts"]:
        path = part["path"]
        if not path.endswith(".json"):
            continue
        parsed = json.loads(base64.b64decode(part["payload"]).decode("utf-8"))
        before = json.dumps(parsed, sort_keys=True)

        if path.endswith("stage_config.json"):
            text = parsed.get("aiInstructions", "")
            if OLD_RULE in text:
                parsed["aiInstructions"] = text.replace(
                    OLD_RULE, new_rule(args.canonical, args.superseded))
                rewritten += 1
            elif args.canonical not in text:
                print(f"  WARNING: run-scoping anchor not found in {path}")

        if path.endswith("datasource.json"):
            deselect(parsed, dropped)

        if json.dumps(parsed, sort_keys=True) != before:
            part["payload"] = base64.b64encode(
                json.dumps(parsed, ensure_ascii=False).encode("utf-8")).decode()
            print(f"  patched {path}")

    print(f"instruction blocks rewritten: {rewritten}")
    print(f"columns deselected: {len(dropped)}"
          + (f" ({', '.join(sorted(set(dropped)))})" if dropped else ""))
    if not rewritten and not dropped:
        print("nothing to change - already hardened")
        return

    update = requests.post(f"{BASE}/workspaces/{workspace_id}/items/{agent_id}/updateDefinition",
                           headers=headers, data=json.dumps({"definition": definition}),
                           timeout=600)
    if update.status_code == 202:
        state = poll(update.headers["Location"], headers)
        print("updateDefinition:", state.get("status"))
        if state.get("status") != "Succeeded":
            raise SystemExit(json.dumps(state)[:600])
    elif update.ok:
        print("updateDefinition: ok")
    else:
        raise SystemExit(f"updateDefinition failed {update.status_code}: {update.text[:400]}")


if __name__ == "__main__":
    main()
