"""Build the rogers_net Direct Lake semantic model.

Direct Lake on OneLake against the Rogers lakehouse. Every column and measure
gets a TMDL `/// description` for Copilot quality. examplePrompts seeded with
NOC + exec briefing question set.

Tables: dim_date, dim_hour, dim_site, dim_cell, dim_alarm_type, dim_customer_segment,
        fact_cell_kpi, fact_alarms, fact_traffic, fact_customer_impact
"""
from __future__ import annotations

import base64
import json
import subprocess
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path

ROOT = Path(__file__).parent
STACK = json.loads((ROOT / "stack_rogers.json").read_text())
WS = STACK["workspace_id"]
LH = STACK["lakehouse_id"]
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"
MODEL_NAME = "rogers_net"


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
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def poll(loc):
    for _ in range(90):
        time.sleep(2)
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


def uid():
    return str(uuid.uuid4())


# ---- COLUMNS / MEASURES ---------------------------------------------------

def col(name, dtype, desc=None, fmt=None, is_key=False, summarize="none", source=None):
    source = source or name
    lines = []
    if desc:
        lines.append(f"\t/// {desc}")
    lines.append(f"\tcolumn '{name}'")
    lines.append(f"\t\tdataType: {dtype}")
    if is_key:
        lines.append(f"\t\tisKey")
    if fmt:
        lines.append(f"\t\tformatString: {fmt}")
    lines.append(f"\t\tlineageTag: {uid()}")
    lines.append(f"\t\tsourceLineageTag: {source}")
    lines.append(f"\t\tsummarizeBy: {summarize}")
    lines.append(f"\t\tsourceColumn: {source}")
    lines.append("")
    lines.append(f"\t\tannotation SummarizationSetBy = Automatic")
    lines.append("")
    return "\n".join(lines)


def measure(name, expr, desc=None, fmt="#,##0", folder=None):
    lines = []
    if desc:
        lines.append(f"\t/// {desc}")
    lines.append(f"\tmeasure '{name}' = {expr}")
    lines.append(f"\t\tformatString: {fmt}")
    if folder:
        lines.append(f"\t\tdisplayFolder: {folder}")
    lines.append(f"\t\tlineageTag: {uid()}")
    lines.append("")
    return "\n".join(lines)


def partition(table_name, expr_name):
    return (
        f"\tpartition {table_name} = entity\n"
        f"\t\tmode: directLake\n"
        f"\t\tsource\n"
        f"\t\t\tentityName: {table_name}\n"
        f"\t\t\texpressionSource: '{expr_name}'\n"
    )


EXPR_NAME = f"DirectLake - {STACK['lakehouse_name']}"


def table_header(name):
    return f"table {name}\n\tlineageTag: {uid()}\n\tsourceLineageTag: [dbo].[{name}]\n\n"


# ---- TABLES ---------------------------------------------------------------

def tmdl_dim_date():
    cols = [
        col("date_key", "string", "Calendar date in YYYY-MM-DD form. Join key for all fact tables. Synonyms: date, day.", is_key=True),
        col("year", "int64", "Calendar year.", fmt="0"),
        col("month", "int64", "Calendar month 1-12.", fmt="0"),
        col("year_month", "string", "Year-month label, e.g. '2026-05'. Use as trend axis."),
        col("week_number", "int64", "ISO week number 1-53.", fmt="0"),
        col("day_name", "string", "Day of week name (Monday..Sunday)."),
        col("is_weekend", "string", "True if Saturday or Sunday. Synonyms: weekend."),
    ]
    return table_header("dim_date") + "\n".join(cols) + "\n" + partition("dim_date", EXPR_NAME)


def tmdl_dim_hour():
    cols = [
        col("hour", "int64", "Hour of day 0-23. Synonyms: hour-of-day.", is_key=True, fmt="0"),
        col("hour_label", "string", "Formatted hour, e.g. '18:00'. Use as axis label."),
        col("daypart", "string", "Daypart bucket: Late Night / Morning / Business / Peak / Evening."),
        col("is_peak", "string", "True for 09:00-21:00 peak window."),
    ]
    return table_header("dim_hour") + "\n".join(cols) + "\n" + partition("dim_hour", EXPR_NAME)


def tmdl_dim_site():
    cols = [
        col("site_id", "string", "Unique site identifier (e.g. S-TOR-007). Joins to dim_cell.site_id. Synonyms: tower, cell site.", is_key=True),
        col("site_name", "string", "Friendly site name including city + sequence."),
        col("region", "string", "Province code (ON, QC, BC, AB, MB, SK, NS, NB, NL, PE). Synonyms: province."),
        col("region_name", "string", "Full province name."),
        col("city", "string", "City the site is located in."),
        col("latitude", "double", "Latitude in decimal degrees.", fmt="0.00000"),
        col("longitude", "double", "Longitude in decimal degrees.", fmt="0.00000"),
        col("primary_technology", "string", "Predominant air-interface technology at the site: 4G or 5G."),
        col("primary_vendor", "string", "Primary RAN equipment vendor: Ericsson, Nokia, or Samsung."),
        col("commissioned_date", "string", "Date site was first commissioned (YYYY-MM-DD)."),
        col("site_type", "string", "Macro / SmallCell / Rooftop deployment type."),
    ]
    return table_header("dim_site") + "\n".join(cols) + "\n" + partition("dim_site", EXPR_NAME)


def tmdl_dim_cell():
    cols = [
        col("cell_id", "string", "Unique cell (sector) identifier (e.g. C-TOR-007-001). Synonyms: sector, cell.", is_key=True),
        col("site_id", "string", "Parent site. Foreign key to dim_site."),
        col("sector", "int64", "Sector number 1-3 within the site.", fmt="0"),
        col("technology", "string", "Air-interface technology of this cell: 4G or 5G."),
        col("band", "string", "Frequency band, e.g. 'n78-3500', 'B7-2600'. Synonyms: spectrum, carrier."),
        col("vendor", "string", "RAN equipment vendor for this cell: Ericsson, Nokia, or Samsung."),
        col("azimuth_deg", "int64", "Antenna azimuth in degrees (0/120/240).", fmt="0"),
        col("max_throughput_dl_mbps", "int64", "Theoretical maximum DL throughput (Mbps) the cell can deliver.", fmt="#,##0"),
    ]
    return table_header("dim_cell") + "\n".join(cols) + "\n" + partition("dim_cell", EXPR_NAME)


def tmdl_dim_alarm_type():
    cols = [
        col("alarm_type_id", "string", "Alarm catalog code, e.g. AT01.", is_key=True),
        col("alarm_name", "string", "Human-readable alarm name, e.g. 'Cell Down', 'Backhaul Congestion'."),
        col("severity", "string", "Alarm severity: Critical, Major, or Minor. Synonyms: priority."),
        col("category", "string", "Domain: RAN, Transport, Core, or Power."),
    ]
    return table_header("dim_alarm_type") + "\n".join(cols) + "\n" + partition("dim_alarm_type", EXPR_NAME)


def tmdl_dim_customer_segment():
    cols = [
        col("segment_id", "string", "Segment code (CS01..CS04).", is_key=True),
        col("segment_name", "string", "Segment name: Consumer-Prepaid, Consumer-Postpaid, SMB, Enterprise."),
        col("segment_class", "string", "Consumer or Business."),
        col("subscriber_count", "int64", "Approximate Canada-wide subscriber count for this segment.", fmt="#,##0"),
    ]
    return table_header("dim_customer_segment") + "\n".join(cols) + "\n" + partition("dim_customer_segment", EXPR_NAME)


# ---- FACT: cell KPI -------------------------------------------------------

def tmdl_fact_cell_kpi():
    cols = [
        col("date_key", "string", "Calendar date. FK to dim_date.", is_key=False),
        col("hour", "int64", "Hour of day 0-23. FK to dim_hour.", fmt="0"),
        col("cell_id", "string", "Cell. FK to dim_cell."),
        col("availability_pct", "double", "Cell availability in percent (0-100). 100 = fully up for the hour. Synonyms: avail, uptime.", fmt="0.00", summarize="none"),
        col("throughput_dl_mbps", "double", "Average downlink user throughput (Mbps) in the hour. Synonyms: DL throughput.", fmt="#,##0.00", summarize="none"),
        col("throughput_ul_mbps", "double", "Average uplink user throughput (Mbps) in the hour. Synonyms: UL throughput.", fmt="#,##0.00", summarize="none"),
        col("latency_ms", "double", "Average round-trip latency (RTT) in milliseconds. Synonyms: RTT, ping.", fmt="0.00", summarize="none"),
        col("prb_utilization_pct", "double", "PRB (Physical Resource Block) utilization percent. >85% indicates congestion. Synonyms: PRB load, cell load.", fmt="0.00", summarize="none"),
        col("attached_users", "int64", "Average number of users attached to the cell during the hour.", fmt="#,##0", summarize="none"),
        col("drop_rate_pct", "double", "Call/session drop rate in percent.", fmt="0.000", summarize="none"),
    ]
    measures = [
        measure("Avg Availability %", "DIVIDE(AVERAGE(fact_cell_kpi[availability_pct]), 100)",
                "Average cell availability across the current filter (returns 0-1 decimal so 0.0% formatting renders correctly). Synonyms: uptime.",
                fmt="0.00%", folder="Availability"),
        measure("Min Availability %", "DIVIDE(MIN(fact_cell_kpi[availability_pct]), 100)",
                "Worst-hour availability in the current filter. Useful for finding outage windows.",
                fmt="0.00%", folder="Availability"),
        measure("# Cells Below 99% Avail",
                "COUNTROWS(FILTER(VALUES(fact_cell_kpi[cell_id]), CALCULATE(AVERAGE(fact_cell_kpi[availability_pct])) < 99))",
                "Count of distinct cells whose average availability fell below 99% in the current filter. Anomaly headline.",
                fmt="#,##0", folder="Availability"),
        measure("Outage Hours (Avail<50%)",
                "CALCULATE(COUNTROWS(fact_cell_kpi), fact_cell_kpi[availability_pct] < 50)",
                "Cell-hours where availability dropped below 50% (hard outage threshold).",
                fmt="#,##0", folder="Availability"),
        measure("Avg DL Throughput (Mbps)", "AVERAGE(fact_cell_kpi[throughput_dl_mbps])",
                "Average downlink user throughput in Mbps. Synonyms: DL speed.",
                fmt="#,##0.0", folder="Throughput"),
        measure("Avg UL Throughput (Mbps)", "AVERAGE(fact_cell_kpi[throughput_ul_mbps])",
                "Average uplink user throughput in Mbps.",
                fmt="#,##0.0", folder="Throughput"),
        measure("Median DL Throughput (Mbps)",
                "MEDIANX(VALUES(fact_cell_kpi[cell_id]), CALCULATE(AVERAGE(fact_cell_kpi[throughput_dl_mbps])))",
                "Median per-cell downlink throughput. Less sensitive to outliers than the average.",
                fmt="#,##0.0", folder="Throughput"),
        measure("DL Throughput Baseline (7d)",
                "CALCULATE(AVERAGE(fact_cell_kpi[throughput_dl_mbps]), DATESINPERIOD(dim_date[date_key], MAX(dim_date[date_key]), -7, DAY))",
                "Rolling 7-day baseline of downlink throughput. Compare current vs baseline to spot anomalies.",
                fmt="#,##0.0", folder="Throughput"),
        measure("Avg Latency (ms)", "AVERAGE(fact_cell_kpi[latency_ms])",
                "Average round-trip latency in milliseconds. Synonyms: RTT.",
                fmt="0.0\" ms\"", folder="Latency"),
        measure("Max Latency (ms)", "MAX(fact_cell_kpi[latency_ms])",
                "Worst-observed latency in the current filter.",
                fmt="0.0\" ms\"", folder="Latency"),
        measure("# Cells High Latency (>60ms)",
                "COUNTROWS(FILTER(VALUES(fact_cell_kpi[cell_id]), CALCULATE(AVERAGE(fact_cell_kpi[latency_ms])) > 60))",
                "Count of cells whose average latency exceeded 60 ms.",
                fmt="#,##0", folder="Latency"),
        measure("Avg PRB Utilization %", "DIVIDE(AVERAGE(fact_cell_kpi[prb_utilization_pct]), 100)",
                "Average PRB (Physical Resource Block) utilization. >85% signals congestion.",
                fmt="0.0%", folder="Congestion"),
        measure("# Cell-Hours Congested (PRB>85%)",
                "CALCULATE(COUNTROWS(fact_cell_kpi), fact_cell_kpi[prb_utilization_pct] > 85)",
                "Cell-hours where PRB utilization exceeded 85% (congestion threshold).",
                fmt="#,##0", folder="Congestion"),
        measure("# Cells Congested",
                "COUNTROWS(FILTER(VALUES(fact_cell_kpi[cell_id]), CALCULATE(MAX(fact_cell_kpi[prb_utilization_pct])) > 85))",
                "Distinct cells that hit >85% PRB utilization in at least one hour.",
                fmt="#,##0", folder="Congestion"),
        measure("Attached Users (avg)", "AVERAGE(fact_cell_kpi[attached_users])",
                "Average attached users per cell-hour.",
                fmt="#,##0", folder="Load"),
        measure("Attached Users (peak)", "MAX(fact_cell_kpi[attached_users])",
                "Peak attached users per cell-hour in the filter.",
                fmt="#,##0", folder="Load"),
        measure("Avg Drop Rate %", "DIVIDE(AVERAGE(fact_cell_kpi[drop_rate_pct]), 100)",
                "Average call / session drop rate.",
                fmt="0.00%", folder="Quality"),
        measure("Network Health Score",
                "VAR a = [Avg Availability %] VAR p = 1 - [Avg PRB Utilization %] / 0.85 "
                "VAR d = 1 - [Avg Drop Rate %] / 0.05 "
                "RETURN ROUND(CLAMP(0, 1, (a * 0.5 + CLAMP(0, 1, p) * 0.25 + CLAMP(0, 1, d) * 0.25)) * 100, 0)",
                "Composite Network Health Score 0-100. Weights: availability 50%, PRB headroom 25%, drop-rate quality 25%. Note: uses CLAMP / VAR.",
                fmt="0\" /100\"", folder="Composite"),
    ]
    return table_header("fact_cell_kpi") + "\n".join(cols) + "\n" + "".join(measures) + partition("fact_cell_kpi", EXPR_NAME)


# ---- FACT: alarms ---------------------------------------------------------

def tmdl_fact_alarms():
    cols = [
        col("alarm_id", "string", "Unique alarm event id (A000001..).", is_key=True),
        col("cell_id", "string", "Cell that raised the alarm. FK to dim_cell."),
        col("date_key", "string", "Date alarm raised. FK to dim_date."),
        col("hour", "int64", "Hour alarm raised.", fmt="0"),
        col("alarm_type_id", "string", "FK to dim_alarm_type."),
        col("severity", "string", "Severity at raise time (Critical / Major / Minor)."),
        col("duration_minutes", "int64", "How long the alarm was active before resolution.", fmt="#,##0", summarize="sum"),
        col("resolved_flag", "int64", "1 if resolved, 0 if still open.", fmt="0"),
        col("mttr_minutes", "int64", "Mean Time To Resolve in minutes (0 when still open).", fmt="#,##0"),
    ]
    measures = [
        measure("# Alarms", "COUNTROWS(fact_alarms)",
                "Total alarm events in current filter.", folder="Alarms"),
        measure("# Critical Alarms",
                "CALCULATE([# Alarms], fact_alarms[severity] = \"Critical\")",
                "Critical-severity alarms.", folder="Alarms"),
        measure("# Major Alarms",
                "CALCULATE([# Alarms], fact_alarms[severity] = \"Major\")",
                "Major-severity alarms.", folder="Alarms"),
        measure("# Open Alarms",
                "CALCULATE([# Alarms], fact_alarms[resolved_flag] = 0)",
                "Alarms still open (not yet resolved).", folder="Alarms"),
        measure("Avg MTTR (min)",
                "AVERAGEX(FILTER(fact_alarms, fact_alarms[resolved_flag] = 1), fact_alarms[mttr_minutes])",
                "Average Mean-Time-To-Resolve across resolved alarms. Synonyms: MTTR.",
                fmt="#,##0\" min\"", folder="Alarms"),
        measure("Max Alarm Duration (min)", "MAX(fact_alarms[duration_minutes])",
                "Longest alarm duration in the filter.",
                fmt="#,##0\" min\"", folder="Alarms"),
        measure("# Cells With Critical Alarm",
                "CALCULATE(DISTINCTCOUNT(fact_alarms[cell_id]), fact_alarms[severity] = \"Critical\")",
                "Cells that raised at least one critical alarm.",
                folder="Alarms"),
    ]
    return table_header("fact_alarms") + "\n".join(cols) + "\n" + "".join(measures) + partition("fact_alarms", EXPR_NAME)


# ---- FACT: traffic --------------------------------------------------------

def tmdl_fact_traffic():
    cols = [
        col("date_key", "string", "Date of traffic measurement. FK to dim_date."),
        col("cell_id", "string", "Cell. FK to dim_cell."),
        col("voice_minutes", "double", "Total voice call minutes carried that day.", fmt="#,##0.0", summarize="sum"),
        col("data_gb", "double", "Total data volume in gigabytes carried that day.", fmt="#,##0.00", summarize="sum"),
        col("sms_count", "int64", "Total SMS messages handled that day.", fmt="#,##0", summarize="sum"),
    ]
    measures = [
        measure("Voice Minutes", "SUM(fact_traffic[voice_minutes])",
                "Total voice minutes carried.", fmt="#,##0", folder="Traffic"),
        measure("Data Volume (GB)", "SUM(fact_traffic[data_gb])",
                "Total data volume in GB.", fmt="#,##0", folder="Traffic"),
        measure("Data Volume (TB)", "DIVIDE(SUM(fact_traffic[data_gb]), 1024)",
                "Total data volume in TB.", fmt="#,##0.00\" TB\"", folder="Traffic"),
        measure("SMS Count", "SUM(fact_traffic[sms_count])",
                "Total SMS sent + received.", fmt="#,##0", folder="Traffic"),
        measure("Data per User (GB)",
                "DIVIDE([Data Volume (GB)], [Attached Users (avg)])",
                "Average data volume per attached user.",
                fmt="#,##0.0\" GB\"", folder="Traffic"),
    ]
    return table_header("fact_traffic") + "\n".join(cols) + "\n" + "".join(measures) + partition("fact_traffic", EXPR_NAME)


# ---- FACT: customer impact ------------------------------------------------

def tmdl_fact_customer_impact():
    cols = [
        col("date_key", "string", "Date. FK to dim_date."),
        col("cell_id", "string", "Cell. FK to dim_cell."),
        col("segment_id", "string", "Customer segment. FK to dim_customer_segment."),
        col("tickets_opened", "int64", "Care tickets opened by customers attached to this cell, this segment, this day.", fmt="#,##0", summarize="sum"),
        col("repeat_caller_count", "int64", "How many of the above tickets came from repeat callers (poor first-call resolution signal).", fmt="#,##0", summarize="sum"),
        col("sentiment_score", "double", "Average sentiment score 0-1 derived from contact-center transcripts. Lower = worse.", fmt="0.00", summarize="none"),
        col("affected_customers", "int64", "Estimated number of customers materially impacted by network conditions.", fmt="#,##0", summarize="sum"),
    ]
    measures = [
        measure("Tickets Opened", "SUM(fact_customer_impact[tickets_opened])",
                "Total customer-care tickets opened in the current filter.", folder="Care"),
        measure("Repeat Callers", "SUM(fact_customer_impact[repeat_caller_count])",
                "Tickets coming from repeat callers.", folder="Care"),
        measure("Repeat Caller Rate",
                "DIVIDE([Repeat Callers], [Tickets Opened])",
                "Share of tickets that came from repeat callers (lower is better).",
                fmt="0.0%", folder="Care"),
        measure("Avg Sentiment", "AVERAGE(fact_customer_impact[sentiment_score])",
                "Average contact-center sentiment score 0-1 (higher is better).",
                fmt="0.00", folder="Sentiment"),
        measure("Affected Customers", "SUM(fact_customer_impact[affected_customers])",
                "Estimated customers materially impacted.", folder="Impact"),
        measure("# Cells With Customer Impact",
                "DISTINCTCOUNT(fact_customer_impact[cell_id])",
                "Distinct cells that triggered customer-impact records.",
                folder="Impact"),
    ]
    return table_header("fact_customer_impact") + "\n".join(cols) + "\n" + "".join(measures) + partition("fact_customer_impact", EXPR_NAME)


# ---- RELATIONSHIPS --------------------------------------------------------

RELATIONSHIPS = [
    # many-to-one fact -> dim
    ("fact_cell_kpi.date_key",         "dim_date.date_key",            True),
    ("fact_cell_kpi.hour",             "dim_hour.hour",                True),
    ("fact_cell_kpi.cell_id",          "dim_cell.cell_id",             True),
    ("dim_cell.site_id",               "dim_site.site_id",             True),
    ("fact_alarms.date_key",           "dim_date.date_key",            True),
    ("fact_alarms.cell_id",            "dim_cell.cell_id",             True),
    ("fact_alarms.alarm_type_id",      "dim_alarm_type.alarm_type_id", True),
    ("fact_traffic.date_key",          "dim_date.date_key",            True),
    ("fact_traffic.cell_id",           "dim_cell.cell_id",             True),
    ("fact_customer_impact.date_key",  "dim_date.date_key",            True),
    ("fact_customer_impact.cell_id",   "dim_cell.cell_id",             True),
    ("fact_customer_impact.segment_id","dim_customer_segment.segment_id", True),
]


def tmdl_relationships():
    lines = []
    for fc, tc, active in RELATIONSHIPS:
        lines.append(f"relationship {uid()}")
        if not active:
            lines.append("\tisActive: false")
        lines.append(f"\tfromColumn: {fc}")
        lines.append(f"\ttoColumn: {tc}")
        lines.append("")
    return "\n".join(lines)


def tmdl_model():
    tables = ["dim_date", "dim_hour", "dim_site", "dim_cell", "dim_alarm_type",
              "dim_customer_segment", "fact_cell_kpi", "fact_alarms",
              "fact_traffic", "fact_customer_impact"]
    parts = [
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tsourceQueryCulture: en-US",
        "\tdataAccessOptions",
        "\t\tlegacyRedirects",
        "\t\treturnErrorValuesAsNull",
        "",
        f"annotation PBI_QueryOrder = [\"{EXPR_NAME}\"]",
        "",
        "annotation __PBI_TimeIntelligenceEnabled = 1",
        "",
        "annotation PBI_ProTooling = [\"DirectLakeOnOneLakeInWeb\",\"MCP-PBIModeling\",\"WebModelingEdit\"]",
        "",
    ]
    for t in tables:
        parts.append(f"ref table {t}")
    parts.append("")
    parts.append("ref cultureInfo en-US")
    parts.append("")
    return "\n".join(parts)


def tmdl_expressions():
    onelake_path = f"https://onelake.dfs.fabric.microsoft.com/{WS}/{LH}"
    return (
        f"expression '{EXPR_NAME}' =\n"
        f"\t\tlet\n"
        f"\t\t    Source = AzureStorage.DataLake(\"{onelake_path}\", [HierarchicalNavigation=true])\n"
        f"\t\tin\n"
        f"\t\t    Source\n"
        f"\tlineageTag: {uid()}\n"
        f"\n"
        f"\tannotation PBI_IncludeFutureArtifacts = False\n"
    )


CULTURE = "cultureInfo en-US\n"


def example_prompts():
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/copilot/examplePrompts/1.0.0/schema.json",
        "prompts": [
            "Give me a network health briefing for the last 7 days: availability, throughput, congestion, customer tickets — call out the biggest anomaly.",
            "Which sites had availability drop below 95% in the last week? Include outage hours and how many customers were impacted.",
            "Compare average downlink throughput by vendor (Ericsson vs Nokia vs Samsung) for the last 7 days, broken out by province.",
            "Which cells had average latency above 60ms? Are any vendors or provinces over-represented?",
            "Show the top 10 most congested cells (PRB > 85%) and the hours they were congested.",
            "For the site outage on 2026-05-25, summarize the alarms raised, MTTR, and the spike in customer tickets the next day.",
            "Which segments (Enterprise vs Consumer-Postpaid vs SMB) opened the most tickets per impacted cell, and how did sentiment shift?",
            "Find cells whose availability declined steadily over the period — possible chronic degradation candidates.",
            "Tonight's peak (18:00-22:00): which cells are at risk of congestion based on the last 7 days?",
            "Summarize total data volume (TB), voice minutes, and SMS by province and technology (4G vs 5G).",
        ],
    }


COPILOT_SCHEMA = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/copilot/schema/1.0.0/schema.json",
    "tables": [],
}

COPILOT_SETTINGS = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/copilot/settings/1.0.0/schema.json",
    "indexingEnabled": True,
}

COPILOT_VERSION = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/version/1.0.0/schema.json",
    "version": "1.0.0",
}

PLATFORM = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
    "metadata": {"type": "SemanticModel", "displayName": MODEL_NAME,
                 "description": "Rogers Network Anomaly Detection demo - cell KPIs, alarms, traffic, customer impact"},
    "config": {"version": "2.0", "logicalId": "00000000-0000-0000-0000-000000000000"},
}

DEFINITION_PBISM = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
    "version": "6.0",
    "settings": {"qnaEnabled": False},
}


def b64_str(s):
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def b64_obj(o):
    return b64_str(json.dumps(o, indent=2))


def build_parts():
    parts = {
        ".platform":                       b64_obj(PLATFORM),
        "definition.pbism":                b64_obj(DEFINITION_PBISM),
        "definition/database.tmdl":        b64_str("database\n\tcompatibilityLevel: 1604\n\n"),
        "definition/model.tmdl":           b64_str(tmdl_model()),
        "definition/expressions.tmdl":     b64_str(tmdl_expressions()),
        "definition/relationships.tmdl":   b64_str(tmdl_relationships()),
        "definition/cultures/en-US.tmdl":  b64_str(CULTURE),
        "definition/tables/dim_date.tmdl":            b64_str(tmdl_dim_date()),
        "definition/tables/dim_hour.tmdl":            b64_str(tmdl_dim_hour()),
        "definition/tables/dim_site.tmdl":            b64_str(tmdl_dim_site()),
        "definition/tables/dim_cell.tmdl":            b64_str(tmdl_dim_cell()),
        "definition/tables/dim_alarm_type.tmdl":      b64_str(tmdl_dim_alarm_type()),
        "definition/tables/dim_customer_segment.tmdl":b64_str(tmdl_dim_customer_segment()),
        "definition/tables/fact_cell_kpi.tmdl":            b64_str(tmdl_fact_cell_kpi()),
        "definition/tables/fact_alarms.tmdl":              b64_str(tmdl_fact_alarms()),
        "definition/tables/fact_traffic.tmdl":             b64_str(tmdl_fact_traffic()),
        "definition/tables/fact_customer_impact.tmdl":     b64_str(tmdl_fact_customer_impact()),
        "Copilot/examplePrompts.json":     b64_obj(example_prompts()),
        "Copilot/schema.json":             b64_obj(COPILOT_SCHEMA),
        "Copilot/settings.json":           b64_obj(COPILOT_SETTINGS),
        "Copilot/version.json":            b64_obj(COPILOT_VERSION),
        "Copilot/Instructions/version.json": b64_obj(COPILOT_VERSION),
    }
    return [{"path": p, "payload": d, "payloadType": "InlineBase64"} for p, d in parts.items()]


def find_model(name):
    s, h, b = call("GET", f"{API}/v1/workspaces/{WS}/semanticModels")
    for it in json.loads(b).get("value", []):
        if it.get("displayName") == name:
            return it.get("id")
    return None


def main():
    parts = build_parts()
    print(f"Built {len(parts)} parts")
    for p in parts:
        decoded_len = len(base64.b64decode(p["payload"]))
        print(f"  {p['path']:<55s} ({decoded_len} bytes)")

    existing = find_model(MODEL_NAME)
    if existing:
        print(f"\nModel {MODEL_NAME} exists ({existing}) - updating...")
        s, h, b = call("POST",
                       f"{API}/v1/workspaces/{WS}/semanticModels/{existing}/updateDefinition",
                       body={"definition": {"parts": parts}})
    else:
        print(f"\nCreating new semantic model '{MODEL_NAME}'...")
        body = {
            "displayName": MODEL_NAME,
            "description": "Rogers Network Anomaly Detection demo dataset",
            "definition": {"parts": parts},
        }
        s, h, b = call("POST", f"{API}/v1/workspaces/{WS}/semanticModels", body=body)
    print(f"  status={s}")
    if s == 202:
        loc = h.get("Location") or h.get("location")
        ok, result_url = poll(loc)
        if not ok:
            print("  failed")
            return
        if not existing:
            sr, hr, br = call("GET", result_url)
            item = json.loads(br)
            STACK["model_id"] = item["id"]
            STACK["model_name"] = MODEL_NAME
            (ROOT / "stack_rogers.json").write_text(json.dumps(STACK, indent=2))
            print(f"  Model id: {item['id']}")
            print(f"  Open: https://msit.powerbi.com/groups/{WS}/datasets/{item['id']}/details")
    elif s in (200, 201):
        if not existing:
            try:
                item = json.loads(b)
                STACK["model_id"] = item.get("id")
                STACK["model_name"] = MODEL_NAME
                (ROOT / "stack_rogers.json").write_text(json.dumps(STACK, indent=2))
                print(f"  Model id: {item.get('id')}")
            except Exception:
                pass
        else:
            print("  Update OK")
    else:
        print(f"  ERROR: {b[:1000]}")


if __name__ == "__main__":
    main()
