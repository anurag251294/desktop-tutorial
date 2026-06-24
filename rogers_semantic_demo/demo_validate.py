"""Demo-readiness validation.

Runs every DAX query that will land behind the visuals in
Rogers_Finance_ARPU_Demo, so the presenter walks in knowing the exact
numbers each card / chart / table will show.

Output is a single block of text you can paste into the demo runbook.
"""
from __future__ import annotations

import json, subprocess, urllib.request, urllib.error
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
        return {"_error": e.code, "_body": e.read().decode(errors="replace")[:1500]}


def section(title):
    print(f"\n{'=' * 80}\n{title}\n{'=' * 80}")


def query(label, dax, max_rows=20):
    print(f"\n--- {label} ---")
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
    pretty = [c.split("[")[-1].rstrip("]") for c in cols]
    print("  " + " | ".join(pretty))
    for row in rows[:max_rows]:
        vals = []
        for c in cols:
            v = row.get(c)
            if isinstance(v, float):
                if abs(v) > 1e6:
                    vals.append(f"{v:,.0f}")
                elif abs(v) > 1:
                    vals.append(f"{v:,.2f}")
                else:
                    vals.append(f"{v:.4f}")
            else:
                vals.append(str(v))
        print("  " + " | ".join(vals))


# ---- Latest-month context filter -----------------------------------------
LATEST_FILTER = "FILTER(ALL(dim_date), dim_date[month_start] = MAX(dim_date[month_start]))"


# =========================================================================
# Page 1 - Finance Executive View
# =========================================================================
section("PAGE 1: Finance Executive View")

query("Header cards (all 24 months, no filter)",
      """EVALUATE ROW(
    "ARPU", [ARPU],
    "Revenue (M)", [Revenue (Millions)],
    "End-of-Period Subscribers", [End-of-Period Subscribers],
    "Net Adds (MoM)", [Net Adds (MoM)])""")

query("Header cards (Jun 2026 only - what they'll likely show)",
      """EVALUATE
CALCULATETABLE(
    ROW(
        "ARPU", [ARPU],
        "Revenue (M)", [Revenue (Millions)],
        "End-of-Period Subscribers", [End-of-Period Subscribers],
        "Net Adds (MoM)", [Net Adds (MoM)]),
    dim_date[month_start] = DATE(2026, 6, 1))""")

query("Revenue ($M) by Business Unit (Jun 2026)",
      """EVALUATE
CALCULATETABLE(
    SUMMARIZECOLUMNS(
        dim_business_unit[bu_name],
        "Revenue (M)", [Revenue (Millions)],
        "ARPU", [ARPU]),
    dim_date[month_start] = DATE(2026, 6, 1))
ORDER BY [Revenue (M)] DESC""")

query("ARPU trend line - last 12 months",
      """EVALUATE
TOPN(12,
    SUMMARIZECOLUMNS(
        dim_date[month_label], dim_date[month_start],
        "ARPU", [ARPU]),
    dim_date[month_start], DESC)
ORDER BY dim_date[month_start] ASC""")


# =========================================================================
# Page 2 - ARPU Deep-Dive
# =========================================================================
section("PAGE 2: ARPU Deep-Dive")

query("Per-LOB ARPU cards (Jun 2026)",
      """EVALUATE
CALCULATETABLE(
    ROW(
        "Wireless", [ARPU - Wireless],
        "Cable & Home", [ARPU - Cable & Home],
        "Media", [ARPU - Media],
        "Enterprise", [ARPU - Enterprise]),
    dim_date[month_start] = DATE(2026, 6, 1))""")

query("ARPU by region (Jun 2026, Wireless only)",
      """EVALUATE
CALCULATETABLE(
    SUMMARIZECOLUMNS(
        dim_region[region_name],
        "ARPU", [ARPU]),
    dim_date[month_start] = DATE(2026, 6, 1),
    dim_business_unit[bu_name] = "Wireless")
ORDER BY [ARPU] DESC""")

query("Top 5 products by revenue (Jun 2026)",
      """EVALUATE
TOPN(5,
    CALCULATETABLE(
        SUMMARIZECOLUMNS(
            dim_product[product_name],
            dim_business_unit[bu_name],
            "Revenue (M)", [Revenue (Millions)],
            "ARPU", [ARPU],
            "Churn %", [Churn Rate %],
            "GM %", [Gross Margin %]),
        dim_date[month_start] = DATE(2026, 6, 1)),
    [Revenue (M)], DESC)
ORDER BY [Revenue (M)] DESC""")

query("Wireless Prepaid promo-glitch - the killer demo query",
      """EVALUATE
CALCULATETABLE(
    SUMMARIZECOLUMNS(
        dim_date[month_label], dim_date[month_start],
        "ARPU", [ARPU],
        "Avg Subs", [Average Subscribers],
        "Revenue (M)", [Revenue (Millions)]),
    dim_product[product_id] = "P004",
    dim_date[month_start] >= DATE(2026, 1, 1))
ORDER BY dim_date[month_start] ASC""")


# =========================================================================
# Page 3 - One Measure, Many Surfaces
# =========================================================================
section("PAGE 3: One Measure, Many Surfaces")

query("The hero ARPU number (Jun 2026, all up)",
      """EVALUATE
CALCULATETABLE(
    ROW("ARPU (certified)", [ARPU]),
    dim_date[month_start] = DATE(2026, 6, 1))""")

query("Same ARPU broken down by BU - the parity demo",
      """EVALUATE
CALCULATETABLE(
    SUMMARIZECOLUMNS(
        dim_business_unit[bu_name],
        "Revenue", [Revenue],
        "Avg Subs", [Average Subscribers],
        "ARPU", [ARPU],
        "ARPU MoM", [ARPU MoM %],
        "ARPU YoY", [ARPU YoY %]),
    dim_date[month_start] = DATE(2026, 6, 1))
ORDER BY [Revenue] DESC""")


# =========================================================================
# Sanity / reconciliation checks
# =========================================================================
section("RECONCILIATION CHECKS - what you can defend on stage")

query("ARPU formula sanity: Revenue / Avg Subs at the BU level matches the measure",
      """EVALUATE
CALCULATETABLE(
    SUMMARIZECOLUMNS(
        dim_business_unit[bu_name],
        "Revenue", [Revenue],
        "Avg Subs", [Average Subscribers],
        "ARPU measure", [ARPU],
        "ARPU manual (rev/avgsubs)", DIVIDE([Revenue], [Average Subscribers]),
        "Delta", [ARPU] - DIVIDE([Revenue], [Average Subscribers])),
    dim_date[month_start] = DATE(2026, 6, 1))""")

query("Total subscribers should be ~16M (Wireless dominates)",
      """EVALUATE
CALCULATETABLE(
    ROW(
        "Avg Subs (Jun 2026)", [Average Subscribers],
        "End Subs (Jun 2026)", [End-of-Period Subscribers]),
    dim_date[month_start] = DATE(2026, 6, 1))""")

print(f"\n{'=' * 80}\nValidation complete.\n{'=' * 80}")
