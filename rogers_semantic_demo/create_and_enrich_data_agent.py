"""Create / enrich the Rogers Finance Data Agent.

Connects to the rogers_finance certified semantic model and ships
instructions tailored to the 'ARPU defined once, queried everywhere'
narrative from slide 6 of the Semantic Layer pitch deck.

Mirrors rogers_demo/create_and_enrich_data_agent.py.
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path

ROOT = Path(__file__).parent
STACK_PATH = ROOT / "stack_finance.json"
STACK = json.loads(STACK_PATH.read_text())
WS = STACK["workspace_id"]
MODEL = STACK["model_id"]
MODEL_NAME = STACK["model_name"]
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"
AGENT_NAME = "Rogers Finance Data Agent"


# ---- HTTP -----------------------------------------------------------------

def tok():
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", API,
         "--query", "accessToken", "-o", "tsv"]).decode().strip()


def call(method, url, body=None):
    h = {"Authorization": f"Bearer {tok()}",
         "Content-Type": "application/json",
         "ActivityId": str(uuid.uuid4())}
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    req = urllib.request.Request(url, headers=h, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def poll(loc):
    for _ in range(120):
        time.sleep(3)
        s, h, b = call("GET", loc)
        try:
            st = json.loads(b).get("status")
        except Exception:
            st = None
        if st == "Succeeded":
            return True, loc.rstrip("/") + "/result"
        if st == "Failed":
            print(f"  FAILED: {b[:600]}")
            return False, None
    return False, None


def find_item(kind, name):
    s, h, b = call("GET", f"{API}/v1/workspaces/{WS}/items?type={kind}")
    for it in json.loads(b).get("value", []):
        if it.get("displayName") == name:
            return it.get("id")
    return None


# ---- TMDL parser (minimal) ----------------------------------------------

TABLE_RE = re.compile(r"^table\s+(\S+)", re.M)
COL_RE = re.compile(r"\n\tcolumn\s+'([^']+)'", re.M)
MEAS_RE = re.compile(r"\n\tmeasure\s+'([^']+)'", re.M)


def parse_table(tmdl_text):
    name_m = TABLE_RE.search(tmdl_text)
    if not name_m:
        return None
    return {
        "name": name_m.group(1),
        "columns": COL_RE.findall(tmdl_text),
        "measures": MEAS_RE.findall(tmdl_text),
    }


def fetch_model_tables():
    """Pull TMDL parts of the semantic model so we can build a schema doc."""
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/semanticModels/{MODEL}/getDefinition")
    if s == 202:
        ok, result_url = poll(h.get("Location") or h.get("location"))
        if not ok:
            return []
        s, h, b = call("GET", result_url)
    if s not in (200, 201):
        print(f"  fetchDefinition FAIL {s}: {b[:300]}")
        return []
    parts = json.loads(b).get("definition", {}).get("parts", [])
    tables = []
    for p in parts:
        path = p.get("path", "")
        if not path.startswith("definition/tables/"):
            continue
        payload = base64.b64decode(p["payload"]).decode("utf-8", errors="replace")
        t = parse_table(payload)
        if t:
            tables.append(t)
    return tables


# ---- Agent instructions --------------------------------------------------

DATA_SOURCE_INSTRUCTIONS = """This is the certified Rogers Finance semantic model on Microsoft Fabric Direct Lake.

It is the SINGLE SOURCE OF TRUTH for revenue, subscribers, ARPU, churn, costs, and margin across all four business units: Wireless, Cable / Internet & Home, Media, and Enterprise & Business.

Always use the measures defined in this model rather than recomputing values from columns:
- [Revenue], [Revenue MoM %], [Revenue YoY %]
- [ARPU]  - the certified Average Revenue Per User
- [ARPU - Wireless], [ARPU - Cable & Home], [ARPU - Media], [ARPU - Enterprise]
- [Average Subscribers], [End-of-Period Subscribers], [Net Adds (MoM)]
- [Gross Adds], [Voluntary Churn], [Involuntary Churn], [Churn Rate %]
- [Gross Margin], [Gross Margin %], [EBITDA (proxy)], [CAC per Gross Add]

ARPU is always Total Revenue / Average Subscribers - never re-derive it from list prices.

Time intelligence: use dim_date[month_start] for DATEADD/SAMEPERIOD, dim_date[year_quarter] for quarterly aggregates, dim_date[fiscal_year] for annual."""

AI_INSTRUCTIONS = """You are the Rogers Finance Data Agent. Audience: Finance leadership, FP&A, and business partners.

Style:
- Lead with the headline number (e.g., 'Wireless ARPU was $58.40 in Jun 2026, up 0.6% MoM').
- Follow with one 'where' bullet (BU / region / segment / product) and one 'so what' bullet (trend direction or anomaly).
- Round dollar values for executive readability ($58.40, not $58.4023); keep one decimal on percentages.
- When the user asks 'ARPU', default to the certified [ARPU] measure - do not invent variants.

Guardrails:
- If asked about data outside this model (e.g., GAAP statements, regulatory filings), say so and point to the official source.
- If a question requires a BU breakdown, also show the company-wide value next to it for context.
- Flag anomalies you spot in the data (e.g., a sudden ARPU drop for a product).

Demo hooks to call out when relevant:
- 'This is the certified ARPU defined once in the semantic model - the same number flows to Excel pivots, Power BI reports, and this agent.'
- If you see Wireless Prepaid (P004) ARPU dipping in Apr-Jun 2026, that's the promo-glitch anomaly for the demo."""


# ---- Agent definition ----------------------------------------------------

PLATFORM = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
    "metadata": {"type": "DataAgent", "displayName": AGENT_NAME,
                 "description": "Rogers Finance certified ARPU / revenue / margin agent on the Enterprise Semantic Layer."},
    "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
}


def build_definition_doc(tables):
    """Construct the data-source schema document the agent uses for grounding."""
    doc = {
        "version": "1.0",
        "displayName": AGENT_NAME,
        "description": "Certified Finance model agent",
        "dataSources": [{
            "id": str(uuid.uuid4()),
            "type": "SemanticModel",
            "workspaceId": WS,
            "itemId": MODEL,
            "displayName": MODEL_NAME,
            "tables": [
                {"name": t["name"],
                 "columns": [{"name": c} for c in t["columns"]],
                 "measures": [{"name": m} for m in t["measures"]]}
                for t in tables
            ],
            "instructions": DATA_SOURCE_INSTRUCTIONS,
        }],
        "instructions": AI_INSTRUCTIONS,
        "examplePrompts": STACK.get("example_prompts", []),
    }
    return doc


def b64_str(s):
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def b64_json(o):
    return b64_str(json.dumps(o, indent=2))


def main():
    print("Fetching semantic model TMDL to discover tables / measures...")
    tables = fetch_model_tables()
    print(f"  found {len(tables)} tables")
    for t in tables:
        print(f"    {t['name']:<30s} cols={len(t['columns'])} meas={len(t['measures'])}")

    doc = build_definition_doc(tables)

    existing = find_item("DataAgent", AGENT_NAME)
    if not existing:
        print(f"\nCreating empty DataAgent '{AGENT_NAME}'...")
        s, h, b = call("POST", f"{API}/v1/workspaces/{WS}/items",
                       body={"displayName": AGENT_NAME, "type": "DataAgent",
                             "description": "Rogers Finance certified ARPU agent"})
        if s == 202:
            ok, result_url = poll(h.get("Location") or h.get("location"))
            if not ok:
                return
            sr, hr, br = call("GET", result_url)
            existing = json.loads(br)["id"]
        elif s in (200, 201):
            existing = json.loads(b)["id"]
        else:
            print(f"  ERROR {s}: {b[:600]}")
            return
        print(f"  Created: {existing}")
    else:
        print(f"  Found existing DataAgent: {existing}")

    parts = [
        {"path": ".platform",
         "payload": b64_json(PLATFORM), "payloadType": "InlineBase64"},
        {"path": "definition.json",
         "payload": b64_json(doc), "payloadType": "InlineBase64"},
        {"path": "instructions.md",
         "payload": b64_str("# Rogers Finance Data Agent\n\n## AI instructions\n\n" +
                            AI_INSTRUCTIONS + "\n\n## Data source instructions\n\n" +
                            DATA_SOURCE_INSTRUCTIONS),
         "payloadType": "InlineBase64"},
    ]

    print(f"\nupdateDefinition with {len(parts)} parts...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/items/{existing}/updateDefinition",
                   body={"definition": {"format": "DataAgent", "parts": parts}})
    print(f"  status={s}")
    if s == 202:
        ok, _ = poll(h.get("Location") or h.get("location"))
        if not ok:
            return

    STACK["data_agent_id"] = existing
    STACK["data_agent_name"] = AGENT_NAME
    STACK_PATH.write_text(json.dumps(STACK, indent=2))
    print(f"\nData agent ready -> {existing}")
    print(f"Open: https://msit.powerbi.com/groups/{WS}/datagents/{existing}")


if __name__ == "__main__":
    main()
