"""End-to-end smoke test for the rogers_finance semantic model.

Runs DAX EXECUTEQUERIES against the model via the Power BI REST API and
prints the results so we can verify:
  - the model is queryable (Direct Lake plumbing works)
  - [Revenue] and [ARPU] return sensible numbers
  - the Wireless Prepaid promo-glitch anomaly is visible in Apr 2026

Mirrors verify_model.py in the other demos.
"""
from __future__ import annotations

import json, subprocess, urllib.request, urllib.error, uuid
from pathlib import Path

STACK = json.loads((Path(__file__).parent / "stack_finance.json").read_text())
WS = STACK["workspace_id"]
MODEL = STACK["model_id"]
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
PBI = "https://analysis.windows.net/powerbi/api"


def tok():
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", PBI,
         "--query", "accessToken", "-o", "tsv"]).decode().strip()


def execute_dax(dax):
    url = f"https://api.powerbi.com/v1.0/myorg/groups/{WS}/datasets/{MODEL}/executeQueries"
    body = json.dumps({"queries": [{"query": dax}],
                       "serializerSettings": {"includeNulls": True}}).encode()
    hdr = {"Authorization": f"Bearer {tok()}",
           "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=body, headers=hdr, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode(errors="replace")[:1000]}


def run(label, dax):
    print(f"\n=== {label} ===")
    print(dax.strip())
    r = execute_dax(dax)
    if "_error" in r:
        print(f"  HTTP {r['_error']}: {r['_body']}")
        return
    try:
        rows = r["results"][0]["tables"][0]["rows"]
    except Exception:
        print(f"  unexpected response: {json.dumps(r)[:600]}")
        return
    if not rows:
        print("  (empty)")
        return
    cols = list(rows[0].keys())
    print("  " + " | ".join(cols))
    for row in rows[:25]:
        print("  " + " | ".join(str(row.get(c)) for c in cols))


QUERIES = [
    ("Headline KPIs for latest month",
     "EVALUATE ROW(\"Revenue\", [Revenue], \"ARPU\", [ARPU], \"Avg Subs\", [Average Subscribers])"),

    ("ARPU by Business Unit (latest)",
     """EVALUATE
SUMMARIZECOLUMNS(
    dim_business_unit[bu_name],
    \"Revenue\", [Revenue],
    \"Avg Subs\", [Average Subscribers],
    \"ARPU\", [ARPU])
ORDER BY [Revenue] DESC"""),

    ("ARPU trend (last 6 months)",
     """EVALUATE
TOPN(
    6,
    SUMMARIZECOLUMNS(
        dim_date[month_label], dim_date[month_start],
        \"ARPU\", [ARPU], \"Revenue\", [Revenue]),
    dim_date[month_start], DESC)
ORDER BY dim_date[month_start] ASC"""),

    ("Wireless Prepaid ARPU - promo glitch check (Mar-Jun 2026)",
     """EVALUATE
CALCULATETABLE(
    SUMMARIZECOLUMNS(
        dim_date[month_label], dim_date[month_start],
        dim_product[product_name],
        \"ARPU\", [ARPU], \"Revenue\", [Revenue]),
    dim_product[product_id] = \"P004\",
    dim_date[month_start] >= DATE(2026, 3, 1))
ORDER BY dim_date[month_start] ASC"""),
]

if __name__ == "__main__":
    print(f"Verifying model {MODEL} in workspace {WS}")
    for label, dax in QUERIES:
        run(label, dax)
