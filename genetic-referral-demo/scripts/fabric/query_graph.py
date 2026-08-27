"""Run GQL against the referral graph: verification first, then the demo queries.

    python scripts/fabric/query_graph.py --output cicd/fabric-setup.output.json
    python scripts/fabric/query_graph.py --query "MATCH (n:Patient) RETURN COUNT(*) AS n"

Three things about this API that cost time:

* It returns **HTTP 200 for application errors** and puts the real outcome in
  status.code. Checking the HTTP status alone reports success on a failed query. Codes
  beginning 00/01/02/03 are success; anything else is an error.
* `label`, `edges` and friends are **reserved keywords** and cannot be used as bare
  aliases. Backtick them or, as here, pick another name.
* Aggregations need an explicit `GROUP BY`, and it must name the **alias**, not the
  dotted property path: `RETURN b.bodySystem AS system ... GROUP BY system`.
  `GROUP BY b.bodySystem` is a syntax error.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

BASE = "https://api.fabric.microsoft.com/v1"

# (title, why it is worth showing, query)
QUERIES = [
    ("node counts by label",
     "Sanity: did every node type load, and at the volumes the pipeline reported?",
     "MATCH (n) RETURN labels(n) AS nodeLabel, COUNT(*) AS n "
     "GROUP BY nodeLabel ORDER BY n DESC"),

    ("edge counts by label",
     "Same for relationships. An edge type at zero means a key mismatch, not an "
     "empty relationship.",
     "MATCH ()-[e]->() RETURN labels(e) AS edgeLabel, COUNT(*) AS n "
     "GROUP BY edgeLabel ORDER BY n DESC"),

    ("the MULTI_SYSTEM traversal",
     "THE demo query. Why a specific child surfaced, walked rather than asserted: "
     "the features recorded, and the body systems they belong to.",
     """MATCH (p:Patient)-[:hasFeature]->(f:Feature)-[:inBodySystem]->(b:BodySystem)
        WHERE p.patientId = 'SYN-00017'
        RETURN f.hpoLabel AS feature, b.bodySystem AS system
        ORDER BY system, feature"""),

    ("body systems that co-occur in surfaced children",
     "A genuine graph question. In SQL this is a self-join over a bridge table; here "
     "it is one pattern.",
     """MATCH (p:Patient)-[:hasFeature]->(:Feature)-[:inBodySystem]->(b:BodySystem)
        WHERE p.referralState = 'indicators_present'
        RETURN b.bodySystem AS system, COUNT(DISTINCT p) AS children
        GROUP BY system ORDER BY children DESC"""),

    ("which criteria surfaced the most children",
     "The criteria are nodes, so the flag itself is inspectable rather than a column "
     "of strings.",
     """MATCH (p:Patient)-[s:surfacedBy]->(c:Criterion)
        RETURN c.criterion AS criterion, c.tier AS tier, COUNT(p) AS children
        GROUP BY criterion, tier ORDER BY children DESC"""),

    ("specialties seeing children who were NOT surfaced",
     "The equity question as a traversal: where do the children the screen never "
     "flagged actually turn up?",
     """MATCH (p:Patient)-[:attendedEncounter]->(:Encounter)
              -[:encounterWithSpecialty]->(s:Specialty)
        WHERE p.referralState = 'no_indicators_recorded'
        RETURN s.specialty AS specialty, COUNT(DISTINCT p) AS children
        GROUP BY specialty ORDER BY children DESC LIMIT 10"""),

    ("features recorded, by interpreter need",
     "The documentation gap, straight from the graph. Same underlying prevalence, "
     "fewer features reaching the record.",
     """MATCH (p:Patient)-[:hasFeature]->(f:Feature)
        RETURN p.interpreterRequired AS interpreterRequired,
               COUNT(DISTINCT p) AS children, COUNT(f) AS featuresRecorded
        GROUP BY interpreterRequired ORDER BY interpreterRequired"""),
]


def token():
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource",
         "https://api.fabric.microsoft.com", "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=(sys.platform == "win32"))
    if result.returncode != 0:
        raise SystemExit(f"token acquisition failed:\n{result.stderr}")
    return result.stdout.strip()


def run(url, headers, query, retries=3):
    for attempt in range(retries):
        response = requests.post(url, headers=headers,
                                 data=json.dumps({"query": " ".join(query.split())}),
                                 timeout=300)
        if response.status_code != 200:
            if attempt < retries - 1:
                time.sleep(15)
                continue
            return None, f"HTTP {response.status_code}: {response.text[:220]}"
        payload = response.json()
        status = payload.get("status", {})
        code = status.get("code", "?????")
        # Success codes begin 00, 01, 02 or 03. Everything else is an error, even
        # though the HTTP status was 200.
        if code[:2] in ("00", "01", "02", "03"):
            return payload.get("result", {}), None
        detail = status.get("description", "")
        cause = (status.get("cause") or {}).get("description", "")
        return None, f"GQL {code}: {detail} {cause}".strip()
    return None, "exhausted retries"


def show(result):
    if not result or result.get("kind") != "TABLE":
        print("    (no tabular result)")
        return
    columns = [c["name"] for c in result.get("columns", [])]
    rows = result.get("data", [])
    if not rows:
        print("    (no rows)")
        return
    widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in rows))
              for c in columns}
    print("    " + "  ".join(c.ljust(widths[c]) for c in columns))
    print("    " + "  ".join("-" * widths[c] for c in columns))
    for row in rows[:25]:
        print("    " + "  ".join(str(row.get(c, "")).ljust(widths[c])
                                 for c in columns))
    if len(rows) > 25:
        print(f"    ... {len(rows) - 25} more")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="cicd/fabric-setup.output.json")
    parser.add_argument("--query", help="run one ad-hoc GQL query instead")
    args = parser.parse_args()

    config = json.loads(Path(args.output).read_text(encoding="utf-8"))
    workspace_id = config["workspace"]["id"]
    graph = config.get("graphModel")
    if not graph:
        raise SystemExit("no graphModel in the output file; run build_graph_model.py")

    url = (f"{BASE}/workspaces/{workspace_id}/GraphModels/{graph['id']}"
           f"/executeQuery?preview=true")
    headers = {"Authorization": f"Bearer {token()}",
               "Content-Type": "application/json", "Accept": "application/json"}

    if args.query:
        result, error = run(url, headers, args.query)
        print(error or "")
        show(result)
        return

    failures = 0
    for title, why, query in QUERIES:
        print(f"\n{'=' * 74}\n{title}\n  {why}\n{'-' * 74}")
        result, error = run(url, headers, query)
        if error:
            print(f"    FAILED  {error}")
            failures += 1
            continue
        show(result)

    print(f"\n{len(QUERIES) - failures}/{len(QUERIES)} queries succeeded")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
