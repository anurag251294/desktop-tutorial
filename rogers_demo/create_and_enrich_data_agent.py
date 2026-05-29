"""Create + enrich the Rogers Network Data Agent end-to-end.

Steps:
  1. Create empty DataAgent item in Rogers_Network_Demo workspace
  2. Pull rogers_net semantic model TMDL to enumerate tables/columns/measures
  3. Build dataSourceInstructions + aiInstructions in NOC + exec briefing vocab
  4. POST updateDefinition with .platform + data_agent.json + publish_info.json +
     draft/ + published/ stage_config + draft/ + published/ semantic-model-rogers_net/
     datasource.json
  5. Verify and write agent id to stack_rogers.json

Run once after build_model.py:
    py create_and_enrich_data_agent.py
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
STACK = json.loads((ROOT / "stack_rogers.json").read_text())
WS = STACK["workspace_id"]
MODEL = STACK.get("model_id")
MODEL_NAME = STACK.get("model_name", "rogers_net")
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"

AGENT_DISPLAY = "Rogers Network Data Agent"
AGENT_DESC = "Conversational analytics over Rogers network telemetry — RAN KPIs, alarms, traffic, customer impact"


# ---- 10 starter prompts ---------------------------------------------------

EXAMPLE_QUESTIONS = [
    "Give me a 7-day network health briefing — availability, throughput, congestion, customer tickets, biggest anomaly.",
    "Which sites had availability drop below 95% last week? Include outage hours and customer impact.",
    "Compare average DL throughput by vendor (Ericsson vs Nokia vs Samsung) for each province.",
    "Which cells had average latency above 60ms in the last 7 days? Are vendors or provinces over-represented?",
    "Top 10 most congested cells (PRB > 85%) with the hours and provinces.",
    "Walk me through the 2026-05-25 site outage — alarms, MTTR, and customer tickets the next day.",
    "Tickets per impacted cell by segment (Consumer-Postpaid / SMB / Enterprise) and how sentiment shifted.",
    "Cells with chronic availability decline over the period — possible hardware degradation candidates.",
    "Tonight 18:00-22:00 risk view — which cells are likely to congest based on the last 7 days?",
    "Total data volume in TB, voice minutes, and SMS by province broken out by 4G vs 5G.",
]


# ---- aiInstructions -------------------------------------------------------

AI_INSTRUCTIONS = """\
## Rogers Network Data Agent

You are a conversational analytics assistant for Rogers network operations
and network engineering leadership. You answer questions about cell-level
KPIs, alarms, traffic, and customer impact using the rogers_net semantic
model.

### Audience
NOC engineers, network engineering managers, and the VP Network — they
think in terms of site / cell / sector / region / vendor / technology
(4G vs 5G). Use telco vocabulary precisely.

### Vocabulary you must use
- RAN = Radio Access Network (4G LTE + 5G NR cells and sites).
- Site = a tower or rooftop deployment (`dim_site`); Cell / Sector =
  individual radio at a site (`dim_cell`); a typical site has 3 cells.
- Availability % = cell uptime, hourly (`fact_cell_kpi.availability_pct`).
  100% = fully up. <99% = degraded; <95% = customer-visible; <50% = hard
  outage hour.
- Throughput = average user data rate (Mbps). DL = downlink, UL = uplink.
- PRB utilization = Physical Resource Block load %. >85% = congestion.
- Latency = round-trip time in ms (RTT). >60ms is a degraded experience.
- Drop rate = call / session drop %.
- MTTR = Mean Time To Resolve alarms in minutes.
- Alarm severity = Critical > Major > Minor; categories = RAN / Transport
  / Core / Power.
- Customer segments: Consumer-Prepaid, Consumer-Postpaid, SMB, Enterprise.
- Sentiment = 0-1 score from care-center transcripts; lower is worse.

### How to answer
1. Lead with the headline number (e.g., "Avg availability 99.3%, 12 cells
   below 99%"). Then one bullet "where" (province / vendor / segment) and
   one bullet "what next" (investigate / dispatch / suppress alarm /
   capex).
2. For trend / anomaly questions, compare to the 7-day rolling baseline
   ([DL Throughput Baseline (7d)] measure).
3. For "anomaly" or "spike" questions, prefer cells where availability
   dropped >2 percentage points OR latency rose >50% OR PRB exceeded 85%.
4. Round throughput to 1 decimal place, latency to whole ms,
   percentages to 1 decimal.
5. Customer-impact questions: link to the cells via `fact_customer_impact`
   joined to `dim_cell` -> `dim_site` -> region.

### What to AVOID
- Do NOT quote subscriber counts in `dim_customer_segment` as live counts
  — they are illustrative for the demo only.
- Do NOT invent thresholds that aren't in this prompt or the data source
  instructions.
- Do NOT confuse PRB utilization (congestion) with availability (uptime)
  — they're different signals.
- Do NOT mix the daily `fact_traffic` rollups with the hourly
  `fact_cell_kpi` — they're different grains.
"""


DATA_SOURCE_INSTRUCTIONS = """\
## Tables and Key Measures (rogers_net)

The rogers_net Direct Lake semantic model has four fact tables sharing the
`cell_id` key, plus six dimensions.

### Fact tables
- fact_cell_kpi — HOURLY per-cell radio KPIs. Grain = (date_key, hour,
  cell_id). Use for availability, throughput, latency, PRB, drop rate,
  attached users. Key measures:
  [Avg Availability %], [Min Availability %], [# Cells Below 99% Avail],
  [Outage Hours (Avail<50%)], [Avg DL Throughput (Mbps)],
  [DL Throughput Baseline (7d)], [Avg Latency (ms)],
  [# Cells High Latency (>60ms)], [Avg PRB Utilization %],
  [# Cell-Hours Congested (PRB>85%)], [# Cells Congested],
  [Network Health Score].
- fact_alarms — discrete alarm events. Grain = alarm event. Key measures:
  [# Alarms], [# Critical Alarms], [# Major Alarms], [# Open Alarms],
  [Avg MTTR (min)], [Max Alarm Duration (min)],
  [# Cells With Critical Alarm].
- fact_traffic — DAILY rollups (voice/data/SMS). Grain = (date_key,
  cell_id). Measures: [Voice Minutes], [Data Volume (GB)],
  [Data Volume (TB)], [SMS Count], [Data per User (GB)].
- fact_customer_impact — DAILY per-cell per-segment care impact. Grain =
  (date_key, cell_id, segment_id). Measures: [Tickets Opened],
  [Repeat Callers], [Repeat Caller Rate], [Avg Sentiment],
  [Affected Customers], [# Cells With Customer Impact].

### Dimensions
- dim_site — sites (site_id, region, region_name, city, latitude,
  longitude, primary_technology, primary_vendor, site_type).
- dim_cell — cells (cell_id -> site_id, sector 1-3, technology, band,
  vendor, azimuth_deg, max_throughput_dl_mbps).
- dim_date — calendar (date_key, year_month, day_name, is_weekend).
- dim_hour — hour of day with daypart (Peak / Business / Late Night /
  Evening / Morning) and is_peak flag (09:00-21:00).
- dim_alarm_type — alarm catalog (alarm_type_id, alarm_name, severity,
  category).
- dim_customer_segment — segments (Consumer-Prepaid / Consumer-Postpaid /
  SMB / Enterprise) with illustrative subscriber counts.

### Conventions
- Geography is by `dim_site.region` (province code) or `region_name`.
- Vendor lives on `dim_cell.vendor` (NOT `dim_site.primary_vendor` — the
  cell vendor is what drives the radio behaviour).
- Technology 4G vs 5G: use `dim_cell.technology`.
- Peak hours = `dim_hour.is_peak = True`.
- "Last 7 days" means `dim_date.date_key >= today - 7 days`.
- Always use [Avg Availability %] (which divides the raw 0-100 column by
  100) rather than averaging `availability_pct` directly.

### Anomaly patterns
- Site outage: `# Cells Below 99% Avail` jumps for a single site
  (multiple cells share a site_id).
- Vendor systemic issue: one vendor's avg DL throughput or latency
  deviates from the others across multiple provinces.
- Stadium / event congestion: spike in `# Cell-Hours Congested (PRB>85%)`
  + spike in `Data Volume (GB)` in a small region/hour window.
- Chronic degradation: a single `cell_id` shows a steady multi-day decline
  in `[Avg Availability %]` without an alarm.
- Customer-impact correlation: when `[Avg Availability %]` is low for a
  cell, `[Tickets Opened]` and `[Affected Customers]` rise on the
  following day; Enterprise + Consumer-Postpaid segments react hardest.
"""


TABLE_DESCRIPTIONS = {
    "dim_date":              "Calendar (date_key, year_month, day_name, is_weekend). Join key for all facts.",
    "dim_hour":              "Hour-of-day lookup (0..23) with daypart and is_peak (09:00-21:00). Join key for hourly facts.",
    "dim_site":              "Site (tower) master. Region = province code. site_type = Macro / SmallCell / Rooftop. primary_technology and primary_vendor describe the predominant config; per-cell tech/vendor lives on dim_cell.",
    "dim_cell":              "Cell (sector) master. cell_id -> site_id. Includes sector (1-3), technology (4G/5G), band, vendor, max_throughput_dl_mbps.",
    "dim_alarm_type":        "Alarm catalog: severity (Critical/Major/Minor) and category (RAN/Transport/Core/Power).",
    "dim_customer_segment":  "Customer segments (Consumer-Prepaid, Consumer-Postpaid, SMB, Enterprise) with illustrative subscriber_count. Use for ticket/segment analytics.",
    "fact_cell_kpi":         "Hourly per-cell radio KPIs: availability, DL/UL throughput, latency, PRB utilization, attached users, drop rate. Use for anomaly detection, outage windows, congestion analysis.",
    "fact_alarms":           "Discrete alarm events with severity, duration_minutes, resolved_flag, mttr_minutes. Use for alarm storms, MTTR trends, vendor or category roll-ups.",
    "fact_traffic":          "Daily per-cell voice/data/SMS rollups. Use for traffic surge / event / capacity analysis. Daily grain — do NOT join to fact_cell_kpi hour.",
    "fact_customer_impact":  "Daily per-cell per-segment customer-care signal: tickets_opened, repeat_caller_count, sentiment_score (0-1), affected_customers. Use for CX correlation against network anomalies.",
}


USE_CASES_APPENDIX = """

---

## Example Use Cases

The network team frequently asks the following patterns. When you recognize
one, prefer the measures and groupings called out in the data source
instructions:

1. Exec network briefing — availability + throughput + congestion + tickets,
   plus the biggest anomaly in one paragraph.
2. Sites with availability <95% — list site_id, region, outage hours,
   affected customers.
3. Throughput by vendor x province — DL throughput grouped by
   `dim_cell.vendor` and `dim_site.region`.
4. High-latency cells — cells where `[Avg Latency (ms)]` > 60 + which
   vendor / region they sit in.
5. Top-congested cells — top 10 by `[# Cell-Hours Congested (PRB>85%)]`.
6. Incident walk-through — alarms + MTTR + tickets for a given date / site.
7. Tickets by segment — `[Tickets Opened]` grouped by `segment_name`,
   plus `[Avg Sentiment]` shift vs last week.
8. Chronic degrade candidates — cells whose 7-day avg availability dropped
   week-over-week without a Critical alarm.
9. Peak-hours risk — filter `dim_hour.is_peak = True`, rank cells by
   PRB utilization over the last 7 days.
10. Traffic mix — `[Data Volume (TB)]`, `[Voice Minutes]`, `[SMS Count]`
    by region x technology.

When answering "executive briefing" or "what should I focus on": (1) one
headline with the network health number, (2) 2-3 bullets with specific
site / cell / vendor names, (3) one explicit recommendation. Keep under
120 words.
"""


# ---- TMDL parser ----------------------------------------------------------

TYPE_MAP = {
    "string": "String", "int64": "Int64", "double": "Double",
    "decimal": "Decimal", "datetime": "DateTime", "boolean": "Boolean",
}


def parse_table_tmdl(tmdl: str):
    m = re.match(r"\s*table\s+(\S+)", tmdl)
    table_name = m.group(1).strip() if m else "?"

    columns, measures = [], []
    blocks = re.split(r"\n(?=\t(?:column|measure)\s)", "\n" + tmdl)
    for blk in blocks:
        bm = re.match(r"\s*(column|measure)\s+(?:'([^']+)'|(\S+))", blk)
        if not bm:
            continue
        kind = bm.group(1)
        name = bm.group(2) or bm.group(3)
        dtype = "String"
        dm = re.search(r"\n\t\tdataType:\s*(\S+)", blk)
        if dm:
            dtype = TYPE_MAP.get(dm.group(1).strip().lower(), "String")
        if kind == "measure":
            dtype = "Double"
        item = {"name": name, "dataType": dtype, "description": None}
        (columns if kind == "column" else measures).append(item)

    desc_re = re.compile(
        r"((?:^|\n)\t///[^\n]*(?:\n\t///[^\n]*)*)\n\t(column|measure)\s+(?:'([^']+)'|(\S+))",
        re.MULTILINE,
    )
    desc_map = {}
    for dm in desc_re.finditer(tmdl):
        comment_block = dm.group(1)
        kind = dm.group(2)
        name = dm.group(3) or dm.group(4)
        clean = "\n".join(
            re.sub(r"^\t///\s?", "", ln) for ln in comment_block.strip("\n").split("\n")
        ).strip()
        desc_map[(kind, name)] = clean

    for c in columns:
        c["description"] = desc_map.get(("column", c["name"]))
    for m_ in measures:
        m_["description"] = desc_map.get(("measure", m_["name"]))

    return table_name, columns, measures


def parse_relationships_tmdl(tmdl: str):
    rels = []
    for m in re.finditer(
        r"relationship\s+\S+\s*\n\s*fromColumn:\s*([^\s\.]+)\.([^\s\n]+)\s*\n\s*toColumn:\s*([^\s\.]+)\.([^\s\n]+)",
        tmdl,
    ):
        ft, fc, tt, tc = m.group(1), m.group(2), m.group(3), m.group(4)
        rels.append({
            "FromTable": ft, "FromColumn": fc,
            "ToTable":   tt, "ToColumn":   tc,
            "IsActive": True,
            "IsBidirectional": False,
            "Cardinality": "ManyToOne",
        })
    return rels


def tok():
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", API,
         "--query", "accessToken", "-o", "tsv"]).decode().strip()


def call(method, url, body=None):
    h = {"Authorization": f"Bearer {tok()}", "Content-Type": "application/json",
         "ActivityId": str(uuid.uuid4())}
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    req = urllib.request.Request(url, headers=h, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            hdrs = {k.lower(): v for k, v in r.headers.items()}
            return r.status, hdrs, r.read().decode()
    except urllib.error.HTTPError as e:
        hdrs = {k.lower(): v for k, v in e.headers.items()}
        return e.code, hdrs, e.read().decode()


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
            print(f"  FAILED: {b[:1200]}")
            return False, None
    return False, None


def find_agent():
    s, h, b = call("GET", f"{API}/v1/workspaces/{WS}/dataagents")
    if s == 200:
        for it in json.loads(b).get("value", []):
            if it.get("displayName") == AGENT_DISPLAY:
                return it.get("id")
    s, h, b = call("GET", f"{API}/v1/workspaces/{WS}/items")
    for it in json.loads(b).get("value", []):
        if it.get("displayName") == AGENT_DISPLAY:
            return it.get("id")
    return None


def create_agent():
    body = {"displayName": AGENT_DISPLAY,
            "description": AGENT_DESC,
            "type": "DataAgent"}
    s, h, b = call("POST", f"{API}/v1/workspaces/{WS}/items", body=body)
    print(f"  Create item status={s}")
    if s in (200, 201):
        return json.loads(b)["id"]
    if s == 202:
        loc = h.get("location")
        ok, result_url = poll(loc)
        if not ok:
            return None
        sr, hr, br = call("GET", result_url)
        return json.loads(br)["id"]
    print(f"  ERR: {b[:600]}")
    return None


def build_elements(tmdl_files):
    elements = []
    for path, content in sorted(tmdl_files.items()):
        if not path.startswith("definition/tables/"):
            continue
        table_name, columns, measures = parse_table_tmdl(content)
        children = []
        for c in columns:
            children.append({
                "id": str(uuid.uuid4()),
                "is_selected": True,
                "display_name": c["name"],
                "type": "semantic_model.column",
                "data_type": c["dataType"],
                "description": c["description"],
                "children": [],
            })
        for m in measures:
            children.append({
                "id": str(uuid.uuid4()),
                "is_selected": True,
                "display_name": m["name"],
                "type": "semantic_model.measure",
                "data_type": m["dataType"],
                "description": m["description"],
                "children": [],
            })
        elements.append({
            "id": str(uuid.uuid4()),
            "is_selected": True,
            "display_name": table_name,
            "type": "semantic_model.table",
            "description": TABLE_DESCRIPTIONS.get(table_name),
            "children": children,
        })
    rels = parse_relationships_tmdl(tmdl_files.get("definition/relationships.tmdl", ""))
    return elements, rels


def main():
    if not MODEL:
        print("ERROR: model_id missing from stack_rogers.json - build the semantic model first.")
        return

    # 1. Find or create the agent
    agent_id = find_agent()
    if agent_id:
        print(f"  Found existing agent {agent_id}")
    else:
        print(f"  Creating new DataAgent '{AGENT_DISPLAY}'...")
        agent_id = create_agent()
        if not agent_id:
            print("  Could not create agent; aborting.")
            return
    print(f"  Agent id: {agent_id}")
    STACK["data_agent_id"] = agent_id
    (ROOT / "stack_rogers.json").write_text(json.dumps(STACK, indent=2))

    # 2. Pull semantic model TMDL
    print("\nFetching rogers_net semantic model definition...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/semanticModels/{MODEL}/getDefinition",
                   body={})
    if s == 202:
        ok, result_url = poll(h.get("location"))
        if not ok:
            return
        payload = json.loads(call("GET", result_url)[2])
    else:
        payload = json.loads(b)
    tmdl_files = {p["path"]: base64.b64decode(p["payload"]).decode("utf-8")
                  for p in payload["definition"]["parts"]
                  if p["path"].endswith(".tmdl")}
    print(f"  Loaded {len(tmdl_files)} TMDL files")

    elements, rels = build_elements(tmdl_files)
    n_cols = sum(len(e["children"]) for e in elements)
    print(f"  Built {len(elements)} tables with {n_cols} columns/measures")
    print(f"  Discovered {len(rels)} relationships")

    # 3. Existing agent backup (best-effort)
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/dataagents/{agent_id}/getDefinition",
                   body={})
    if s == 202:
        ok, result_url = poll(h.get("location"))
        if ok:
            existing = json.loads(call("GET", result_url)[2])
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            (ROOT / f"backup_rogers_agent_{ts}.json").write_text(json.dumps(existing, indent=2))
            print(f"  Backed up existing definition")

    # 4. Build all parts
    datasource_doc = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/definition/dataSource/1.0.0/schema.json",
        "artifactId": MODEL,
        "workspaceId": WS,
        "dataSourceInstructions": DATA_SOURCE_INSTRUCTIONS,
        "displayName": MODEL_NAME,
        "type": "semantic_model",
        "userDescription": None,
        "metadata": {"csdl_relationships": json.dumps(rels)},
        "elements": elements,
    }
    stage_cfg = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/definition/stageConfiguration/1.0.0/schema.json",
        "aiInstructions": AI_INSTRUCTIONS.rstrip() + USE_CASES_APPENDIX,
    }
    data_agent_doc = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/definition/dataAgent/2.1.0/schema.json",
    }
    publish_info = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/definition/publishInfo/1.0.0/schema.json",
        "description": "",
    }
    platform = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "DataAgent", "displayName": AGENT_DISPLAY, "description": AGENT_DESC},
        "config": {"version": "2.0", "logicalId": "00000000-0000-0000-0000-000000000000"},
    }

    new_parts = {
        ".platform": json.dumps(platform, indent=2),
        "Files/Config/data_agent.json": json.dumps(data_agent_doc, indent=2),
        "Files/Config/publish_info.json": json.dumps(publish_info, indent=2),
        "Files/Config/draft/stage_config.json": json.dumps(stage_cfg, indent=2, ensure_ascii=False),
        "Files/Config/published/stage_config.json": json.dumps(stage_cfg, indent=2, ensure_ascii=False),
        f"Files/Config/draft/semantic-model-{MODEL_NAME}/datasource.json":
            json.dumps(datasource_doc, indent=2, ensure_ascii=False),
        f"Files/Config/published/semantic-model-{MODEL_NAME}/datasource.json":
            json.dumps(datasource_doc, indent=2, ensure_ascii=False),
    }
    payload_parts = [
        {"path": p,
         "payload": base64.b64encode(c.encode("utf-8")).decode("ascii"),
         "payloadType": "InlineBase64"}
        for p, c in new_parts.items()
    ]
    print(f"\nPOSTing updateDefinition with {len(payload_parts)} parts:")
    for p in new_parts:
        print(f"  {p}")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/dataagents/{agent_id}/updateDefinition",
                   body={"definition": {"parts": payload_parts}})
    print(f"  status={s}")
    if s == 202:
        ok, _ = poll(h.get("location"))
        if not ok:
            return
    elif s not in (200, 201):
        print(f"  ERR: {b[:1500]}")
        return

    print("\nDone.")
    print(f"  Open: https://msit.powerbi.com/groups/{WS}/dataagents/{agent_id}")
    print("\n10 starter prompts to paste into the portal Starter Questions UI:")
    for i, q in enumerate(EXAMPLE_QUESTIONS, 1):
        print(f"  {i:2d}. {q}")


if __name__ == "__main__":
    main()
