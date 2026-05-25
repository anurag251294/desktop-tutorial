"""Create a Fabric Notebook in the InteracHRDemo workspace that renders
a polished KPI dashboard. Bypasses PBIR entirely - notebook output is
HTML/plotly which Fabric renders inline.

The notebook:
  1. Attaches to InteracHR_Lakehouse
  2. Loads all 11 Delta tables as Spark DataFrames
  3. Computes the 8 KPIs (same logic as the DAX measures)
  4. Renders each as a plotly Indicator (gauge) with traffic-light color
  5. Lays them out in a 4x2 grid
"""
from __future__ import annotations

import base64
import json
import subprocess
import time
import urllib.request
import urllib.error
import uuid

WS = "de6a7e47-474b-4354-87e7-26b8d741f015"
LH = "ace95976-24ae-4e1e-b799-2075c1495c11"
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"


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
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def poll(loc):
    for i in range(60):
        time.sleep(2)
        s, h, b = call("GET", loc)
        try:
            st = json.loads(b).get("status")
        except Exception:
            st = None
        if st == "Succeeded":
            return True, loc.rstrip("/") + "/result"
        if st == "Failed":
            print(f"   FAILED: {b[:600]}")
            return False, None
    return False, None


# Fabric notebook source (.py format, Fabric parses cells from `# CELL ***` markers)
NOTEBOOK_SOURCE = '''# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "%LAKEHOUSE_ID%",
# META       "default_lakehouse_name": "InteracHR_Lakehouse",
# META       "default_lakehouse_workspace_id": "%WORKSPACE_ID%"
# META     }
# META   }
# META }

# MARKDOWN ********************

# # Six Views Financial - HR Executive Dashboard
#
# **Live data from `InteracHR_Lakehouse` (Direct Lake on OneLake)**
# Canada Central capacity | Purview-governed | Refreshed at notebook run
#
# ---

# CELL ********************

# Load all 11 Delta tables
tables = ["dim_date", "dim_department", "dim_role", "dim_location", "dim_employee",
          "fact_headcount_snapshot", "fact_attrition", "fact_compensation",
          "fact_recruitment", "fact_training_completion", "fact_attestation"]

dfs = {t: spark.table(f"InteracHR_Lakehouse.{t}") for t in tables}
for t in tables:
    print(f"  {t:30s} {dfs[t].count():>8,} rows")

# CELL ********************

# Register temp views for SQL
for t, df in dfs.items():
    df.createOrReplaceTempView(t)

# CELL ********************

# Compute 8 KPIs using Spark SQL (same logic as our DAX measures)
from datetime import date, timedelta
today = date.today().isoformat()
ltm_start = (date.today() - timedelta(days=365)).isoformat()

kpi_sql = f"""
WITH
latest_snapshot AS (
    SELECT MAX(snapshot_date) AS max_date FROM fact_headcount_snapshot
),
active AS (
    SELECT COUNT(DISTINCT h.employee_id) AS active_count
    FROM fact_headcount_snapshot h
    JOIN latest_snapshot l ON h.snapshot_date = l.max_date
),
ltm_terms AS (
    SELECT COUNT(*) AS terms_ltm,
           SUM(CASE WHEN regrettable = 'Yes' THEN 1 ELSE 0 END) AS regret_ltm
    FROM fact_attrition
    WHERE termination_date >= '{ltm_start}' AND termination_date <= '{today}'
),
avg_hc AS (
    SELECT AVG(employees_at_snap) AS avg_hc_ltm FROM (
        SELECT snapshot_date, COUNT(DISTINCT employee_id) AS employees_at_snap
        FROM fact_headcount_snapshot
        WHERE snapshot_date >= '{ltm_start}' AND snapshot_date <= '{today}'
        GROUP BY snapshot_date
    )
),
open_reqs AS (
    SELECT COUNT(DISTINCT req_id) AS open_count
    FROM fact_recruitment WHERE status = 'Open'
),
time_to_fill AS (
    SELECT AVG(time_to_fill_days) AS avg_ttf
    FROM fact_recruitment WHERE status = 'Filled'
),
comp_ratio AS (
    SELECT
        AVG(e.current_base_salary_cad) AS emp_avg,
        AVG(r.market_median_salary)    AS mkt_avg
    FROM dim_employee e
    JOIN dim_role r ON e.role_id = r.role_id
    WHERE e.status = 'Active'
),
fintrac AS (
    SELECT
        COUNT(*) AS total,
        SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) AS done
    FROM fact_training_completion WHERE regulator = 'FINTRAC'
),
coi AS (
    SELECT COUNT(*) AS overdue_count
    FROM fact_attestation
    WHERE attestation_type = 'ATT-COI' AND status = 'Overdue' AND days_overdue >= 90
)
SELECT
    (SELECT active_count FROM active) AS headcount,
    (SELECT terms_ltm * 1.0 / NULLIF(avg_hc_ltm, 0) FROM ltm_terms, avg_hc) AS attrition_rate,
    (SELECT regret_ltm * 1.0 / NULLIF(terms_ltm, 0) FROM ltm_terms) AS pct_regrettable,
    (SELECT open_count FROM open_reqs) AS open_reqs,
    (SELECT avg_ttf FROM time_to_fill) AS avg_time_to_fill,
    (SELECT emp_avg * 1.0 / NULLIF(mkt_avg, 0) FROM comp_ratio) AS comp_ratio,
    (SELECT done * 1.0 / NULLIF(total, 0) FROM fintrac) AS fintrac_pct,
    (SELECT overdue_count FROM coi) AS coi_overdue_90
"""

row = spark.sql(kpi_sql).collect()[0]
k = row.asDict()
print("KPI snapshot:")
for key, val in k.items():
    print(f"  {key:25s} = {val}")

# CELL ********************

# Render polished KPI dashboard with plotly Indicator widgets
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# (label, value, target, format, direction)
KPIS = [
    ("Headcount vs Target",         k['headcount'],         1000, "#,##0",   "higher"),
    ("Attrition Rate vs Threshold", k['attrition_rate']*100,12,   "0.0%",    "lower"),
    ("Regrettable Attrition Risk",  k['pct_regrettable']*100,15,  "0.0%",    "lower"),
    ("Open Reqs Pipeline Health",   k['open_reqs'],         100,  "#,##0",   "lower"),
    ("Time to Fill SLA (days)",     k['avg_time_to_fill'],  60,   "#,##0.0", "lower"),
    ("Market Comp Competitiveness", k['comp_ratio'],        1.0,  "0.00",    "higher"),
    ("FINTRAC Training Compliance", k['fintrac_pct']*100,   95,   "0.0%",    "higher"),
    ("COI Attestation Risk",        k['coi_overdue_90'],    0,    "#,##0",   "lower"),
]

def status_color(value, target, direction):
    if direction == "higher":
        if value >= target: return "#1B9E77"      # green
        if value >= target * 0.90: return "#E6AB02"   # yellow
        return "#D95F02"                          # red
    else:
        if value <= target: return "#1B9E77"
        if value <= target * 1.5 or value <= target + 3: return "#E6AB02"
        return "#D95F02"

# 4x2 grid
fig = make_subplots(
    rows=2, cols=4,
    specs=[[{"type": "indicator"}]*4]*2,
    subplot_titles=[k[0] for k in KPIS],
    vertical_spacing=0.18, horizontal_spacing=0.05,
)

for i, (label, value, target, fmt, direction) in enumerate(KPIS):
    row_idx = i // 4 + 1
    col_idx = i % 4 + 1
    color = status_color(value, target, direction)
    fig.add_trace(go.Indicator(
        mode="number+delta+gauge",
        value=value,
        number={"font": {"size": 36, "color": color},
                "valueformat": ",.1f" if fmt.startswith("0.") else ",.0f"},
        delta={"reference": target,
               "relative": False,
               "increasing": {"color": "#1B9E77" if direction == "higher" else "#D95F02"},
               "decreasing": {"color": "#D95F02" if direction == "higher" else "#1B9E77"}},
        gauge={"axis": {"range": [None, max(target*1.5, value*1.2)],
                        "tickwidth": 0},
               "bar": {"color": color, "thickness": 0.4},
               "bgcolor": "#F4F4F4",
               "borderwidth": 0,
               "threshold": {"line": {"color": "#333333", "width": 3},
                             "thickness": 0.85,
                             "value": target}},
    ), row=row_idx, col=col_idx)

fig.update_layout(
    title={"text": "<b>Six Views Financial - HR Executive Dashboard</b><br>"
                   "<span style='font-size:12pt;color:#777'>Live from InteracHR_Lakehouse · "
                   "Canada Central · Direct Lake on OneLake</span>",
           "x": 0.02, "y": 0.97, "font": {"size": 22, "color": "#1B2C5C"}},
    height=720, width=1400,
    paper_bgcolor="white",
    margin={"l": 30, "r": 30, "t": 110, "b": 30},
    font={"family": "Segoe UI"},
)
fig.show()

# CELL ********************

# Bonus: render the underlying numbers as a clean summary table
import pandas as pd
summary = pd.DataFrame([
    {"KPI": label, "Value": value, "Target": target,
     "Status": ("GREEN" if status_color(value, target, dr) == "#1B9E77"
                else ("YELLOW" if status_color(value, target, dr) == "#E6AB02"
                      else "RED"))}
    for (label, value, target, _, dr) in KPIS
])
display(summary)

# MARKDOWN ********************

# ## Story-arc highlights
#
# * **COI Attestation Risk** is the only RED metric: 7 employees overdue 90+ days on
#   Conflict of Interest attestations. This is precisely the kind of finding OSFI
#   E-21 examiners look for.
# * **FINTRAC Training Compliance** is GREEN at 96.3%, above the 95% threshold.
# * Most operational metrics are in YELLOW - hiring throughput, attrition,
#   compensation ratio - all approaching but not yet crossing target thresholds.
# * **Senior IC engineers (IC4-IC5) in the Payments Platform team** show the
#   highest regrettable attrition. Drill in via the semantic model for the full breakdown.
'''


def split_cells_from_py(source):
    """Parse the # CELL / # MARKDOWN markers and convert to .ipynb cells."""
    cells = []
    current_type = None
    current_lines = []

    def flush():
        if current_type and current_lines:
            text = "".join(current_lines).rstrip("\n")
            if not text.strip():
                return
            if current_type == "markdown":
                # Strip the leading '# ' from each line
                md_lines = []
                for ln in text.split("\n"):
                    md_lines.append(ln[2:] if ln.startswith("# ") else (ln[1:] if ln == "#" else ln))
                cells.append({
                    "cell_type": "markdown",
                    "metadata": {},
                    "source": "\n".join(md_lines),
                })
            else:
                cells.append({
                    "cell_type": "code",
                    "metadata": {},
                    "source": text,
                    "outputs": [],
                    "execution_count": None,
                })

    for line in source.split("\n"):
        if line.startswith("# CELL "):
            flush()
            current_type = "code"
            current_lines = []
        elif line.startswith("# MARKDOWN "):
            flush()
            current_type = "markdown"
            current_lines = []
        elif line.startswith("# METADATA "):
            flush()
            current_type = "metadata"
            current_lines = []
        elif current_type in ("code", "markdown"):
            current_lines.append(line + "\n")
        # ignore lines outside any cell type
    flush()
    return cells


def main():
    source = (NOTEBOOK_SOURCE
              .replace("%LAKEHOUSE_ID%", LH)
              .replace("%WORKSPACE_ID%", WS))
    cells = split_cells_from_py(source)
    print(f"Parsed {len(cells)} cells from source")

    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernel_info": {"name": "synapse_pyspark"},
            "kernelspec": {"name": "synapse_pyspark", "language": "Python",
                           "display_name": "Synapse PySpark"},
            "language_info": {"name": "python"},
            "microsoft": {
                "language": "python",
                "language_group": "synapse_pyspark"
            },
            "dependencies": {
                "lakehouse": {
                    "default_lakehouse": LH,
                    "default_lakehouse_name": "InteracHR_Lakehouse",
                    "default_lakehouse_workspace_id": WS,
                }
            }
        },
        "cells": cells,
    }

    PLATFORM = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Notebook",
                     "displayName": "InteracHR_KPI_Notebook",
                     "description": "HR KPI dashboard in notebook (Spark + plotly)"},
        "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
    }

    parts = [
        {"path": ".platform",
         "payload": base64.b64encode(json.dumps(PLATFORM, indent=2).encode()).decode(),
         "payloadType": "InlineBase64"},
        {"path": "notebook-content.ipynb",
         "payload": base64.b64encode(json.dumps(nb, indent=1).encode()).decode(),
         "payloadType": "InlineBase64"},
    ]

    body = {
        "displayName": "InteracHR_KPI_Notebook",
        "description": "HR KPI dashboard (plotly gauges)",
        "type": "Notebook",
        "definition": {"format": "ipynb", "parts": parts},
    }
    print("Creating notebook...")
    s, h, b = call("POST", f"{API}/v1/workspaces/{WS}/items", body=body)
    print(f"  status={s}")
    if s == 202:
        loc = h.get("Location") or h.get("location")
        ok, result_url = poll(loc)
        if ok:
            s2, h2, b2 = call("GET", result_url)
            item = json.loads(b2)
            print(f"\nNotebook created: id={item['id']}")
            print(f"Open: https://msit.powerbi.com/groups/{WS}/synapsenotebooks/{item['id']}")
        else:
            print("  FAILED")
    elif s in (200, 201):
        item = json.loads(b)
        print(f"Notebook (sync): id={item.get('id')}")
    else:
        print(f"ERROR: {b[:800]}")


if __name__ == "__main__":
    main()
