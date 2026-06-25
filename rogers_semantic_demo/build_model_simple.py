"""Simplified semantic model for the demo.

  Tables (business-friendly names; sourceColumn maps to lakehouse names):
    Revenue   <- fact_revenue_monthly  (now has avg_subscribers column too)
    Product   <- dim_product
    Region    <- dim_region
    Date      <- dim_date

  Hero measure: ARPU = SUM(Revenue[Amount]) / SUM(Revenue[Avg Subscribers])

Replaces the existing rogers_finance model in-place via updateDefinition.
"""
from __future__ import annotations

import base64, json, subprocess, time, urllib.request, urllib.error, uuid
from pathlib import Path

ROOT = Path(__file__).parent
STACK_PATH = ROOT / "stack_finance.json"
STACK = json.loads(STACK_PATH.read_text())
WS = STACK["workspace_id"]
SQL_CS = STACK["sql_endpoint_cs"]
SQL_ID = STACK["sql_endpoint_id"]
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"
MODEL_NAME = "rogers_finance"


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
    for _ in range(60):
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


# ---- TMDL emit helpers ---------------------------------------------------

DATABASE_TMDL = "database\n\tcompatibilityLevel: 1604\n"

MODEL_TMDL = """model Model
\tculture: en-US
\tdefaultPowerBIDataSourceVersion: powerBI_V3
\tsourceQueryCulture: en-US
\tdataAccessOptions
\t\tlegacyRedirects
\t\treturnErrorValuesAsNull

\tannotation PBIDesktopVersion = 2.144.0.0
\tannotation __PBI_TimeIntelligenceEnabled = 1
"""

EXPRESSIONS_TMDL = f"""expression DatabaseQuery =
\t\tlet
\t\t\tdatabase = Sql.Database(\"{SQL_CS}\", \"{SQL_ID}\")
\t\tin
\t\t\tdatabase

\tlineageTag: 11111111-1111-1111-1111-111111111111
\tannotation PBI_NavigationStepName = Navigation
"""


def t_table(table_name, source_table, columns, measures=None):
    """columns: list of dicts {name, source, dtype, summ, fmt, hidden, desc}
       measures: list of dicts {name, expr, fmt, folder, desc}"""
    measures = measures or []
    parts = [f"table '{table_name}'"]
    parts.append("\tlineageTag: " + str(uuid.uuid4()))

    for c in columns:
        parts.append("")
        if c.get("desc"):
            for line in c["desc"].splitlines():
                parts.append(f"\t/// {line}")
        parts.append(f"\tcolumn '{c['name']}'")
        parts.append(f"\t\tdataType: {c['dtype']}")
        if c.get("hidden"):
            parts.append("\t\tisHidden")
        if c.get("fmt"):
            parts.append(f"\t\tformatString: {c['fmt']}")
        parts.append(f"\t\tsourceColumn: {c.get('source', c['name'])}")
        parts.append(f"\t\tlineageTag: " + str(uuid.uuid4()))
        parts.append(f"\t\tsummarizeBy: {c.get('summ', 'none')}")

    for m in measures:
        parts.append("")
        if m.get("desc"):
            for line in m["desc"].splitlines():
                parts.append(f"\t/// {line}")
        parts.append(f"\tmeasure '{m['name']}' = {m['expr']}")
        if m.get("fmt"):
            parts.append(f"\t\tformatString: {m['fmt']}")
        if m.get("folder"):
            parts.append(f"\t\tdisplayFolder: {m['folder']}")
        parts.append(f"\t\tlineageTag: " + str(uuid.uuid4()))

    parts.append("\n\tpartition Partition = entity")
    parts.append("\t\tmode: directLake")
    parts.append(f"\t\tsource\n\t\t\tentityName: {source_table}\n\t\t\texpressionSource: DatabaseQuery")
    parts.append("\n\tannotation PBI_ResultType = Table")
    return "\n".join(parts) + "\n"


# ---- Table definitions ---------------------------------------------------

REVENUE = t_table(
    "Revenue", "fact_revenue_monthly",
    columns=[
        {"name": "Date Key",         "source": "date_key",        "dtype": "string", "hidden": True,
         "desc": "Join key to Date (YYYY-MM)."},
        {"name": "BU Id",            "source": "bu_id",           "dtype": "string", "hidden": True},
        {"name": "Product Id",       "source": "product_id",      "dtype": "string", "hidden": True,
         "desc": "Join key to Product."},
        {"name": "Region Id",        "source": "region_id",       "dtype": "string", "hidden": True,
         "desc": "Join key to Region."},
        {"name": "Amount",           "source": "revenue",         "dtype": "double", "hidden": True,
         "fmt": "\"\\$#,0;-\\$#,0\"", "summ": "sum",
         "desc": "Underlying revenue column - use the [Revenue] measure."},
        {"name": "List ARPU",        "source": "list_arpu",       "dtype": "double", "hidden": True,
         "summ": "average"},
        {"name": "Avg Subscribers",  "source": "avg_subscribers", "dtype": "int64", "hidden": True,
         "fmt": "\"#,0\"", "summ": "sum",
         "desc": "Average in-month subscriber count - denominator for [ARPU]."},
    ],
    measures=[
        {"name": "Revenue",
         "expr": "SUM(Revenue[Amount])",
         "fmt": "\"\\$#,0;-\\$#,0\"",
         "folder": "01 Revenue",
         "desc": "Total monthly revenue in CAD. The certified Finance revenue figure."},
        {"name": "Revenue (Millions)",
         "expr": "DIVIDE([Revenue], 1000000)",
         "fmt": "\"\\$#,0.0\"",
         "folder": "01 Revenue",
         "desc": "Revenue in millions for executive views ($1,234.5 = $1.23B)."},
        {"name": "Revenue MoM %",
         "expr": "DIVIDE([Revenue] - CALCULATE([Revenue], DATEADD('Date'[Month Start], -1, MONTH)), CALCULATE([Revenue], DATEADD('Date'[Month Start], -1, MONTH)))",
         "fmt": "\"0.0%;-0.0%\"",
         "folder": "01 Revenue",
         "desc": "Month-over-month revenue change."},
        {"name": "Revenue YoY %",
         "expr": "DIVIDE([Revenue] - CALCULATE([Revenue], DATEADD('Date'[Month Start], -12, MONTH)), CALCULATE([Revenue], DATEADD('Date'[Month Start], -12, MONTH)))",
         "fmt": "\"0.0%;-0.0%\"",
         "folder": "01 Revenue",
         "desc": "Year-over-year revenue change."},

        {"name": "Average Subscribers",
         "expr": "SUM(Revenue[Avg Subscribers])",
         "fmt": "\"#,0\"",
         "folder": "02 Subscribers",
         "desc": "Average in-period subscribers. Denominator for [ARPU]."},

        {"name": "ARPU",
         "expr": "DIVIDE([Revenue], [Average Subscribers])",
         "fmt": "\"\\$#,0.00\"",
         "folder": "03 ARPU",
         "desc": "Average Revenue Per User = Revenue / Average Subscribers. CERTIFIED enterprise ARPU - defined once here, consumed everywhere (Power BI, Excel pivot, Copilot)."},
        {"name": "ARPU MoM %",
         "expr": "DIVIDE([ARPU] - CALCULATE([ARPU], DATEADD('Date'[Month Start], -1, MONTH)), CALCULATE([ARPU], DATEADD('Date'[Month Start], -1, MONTH)))",
         "fmt": "\"0.0%;-0.0%\"",
         "folder": "03 ARPU",
         "desc": "Month-over-month ARPU drift."},
        {"name": "ARPU YoY %",
         "expr": "DIVIDE([ARPU] - CALCULATE([ARPU], DATEADD('Date'[Month Start], -12, MONTH)), CALCULATE([ARPU], DATEADD('Date'[Month Start], -12, MONTH)))",
         "fmt": "\"0.0%;-0.0%\"",
         "folder": "03 ARPU",
         "desc": "Year-over-year ARPU drift."},
    ],
)

PRODUCT = t_table(
    "Product", "dim_product",
    columns=[
        {"name": "Product Id",    "source": "product_id",    "dtype": "string", "hidden": True},
        {"name": "Product Name",  "source": "product_name",  "dtype": "string",
         "desc": "Product or plan name."},
        {"name": "Revenue Type",  "source": "revenue_type",  "dtype": "string",
         "desc": "Subscription / Advertising / Tickets / Project."},
        {"name": "List Price",    "source": "list_price",    "dtype": "double", "hidden": True,
         "fmt": "\"\\$#,0.00\"", "summ": "sum"},
    ],
)

REGION = t_table(
    "Region", "dim_region",
    columns=[
        {"name": "Region Id",         "source": "region_id",         "dtype": "string", "hidden": True},
        {"name": "Region Name",       "source": "region_name",       "dtype": "string",
         "desc": "Rogers reporting region."},
        {"name": "Province",          "source": "province_code",     "dtype": "string",
         "desc": "Two-letter Canadian province code."},
        {"name": "Population Weight", "source": "population_weight", "dtype": "double", "hidden": True,
         "fmt": "\"0.00%\"", "summ": "sum"},
    ],
)

DATE = t_table(
    "Date", "dim_date",
    columns=[
        {"name": "Date Key",       "source": "date_key",       "dtype": "string", "hidden": True,
         "desc": "Join key to Revenue (YYYY-MM)."},
        {"name": "Month Start",    "source": "month_start",    "dtype": "dateTime",
         "fmt": "\"yyyy-mm-dd\"",
         "desc": "First calendar day of the month - use for time intelligence."},
        {"name": "Fiscal Year",    "source": "fiscal_year",    "dtype": "int64",
         "fmt": "\"0\""},
        {"name": "Fiscal Quarter", "source": "fiscal_quarter", "dtype": "string"},
        {"name": "Year-Quarter",   "source": "year_quarter",   "dtype": "string",
         "desc": "Year + quarter, e.g. 2026-Q1."},
        {"name": "Month Number",   "source": "month_number",   "dtype": "int64", "hidden": True,
         "fmt": "\"0\""},
        {"name": "Month Name",     "source": "month_name",     "dtype": "string", "hidden": True},
        {"name": "Month",          "source": "month_label",    "dtype": "string",
         "desc": "Display label e.g. 'Jun 2026' for axes."},
    ],
)

RELATIONSHIPS_TMDL = """relationship rel_rev_date
\tfromColumn: Revenue.'Date Key'
\ttoColumn: Date.'Date Key'

relationship rel_rev_product
\tfromColumn: Revenue.'Product Id'
\ttoColumn: Product.'Product Id'

relationship rel_rev_region
\tfromColumn: Revenue.'Region Id'
\ttoColumn: Region.'Region Id'
"""

CULTURES_TMDL = "cultureInfo en-US\n"


# ---- Build / push --------------------------------------------------------

PLATFORM = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
    "metadata": {"type": "SemanticModel", "displayName": MODEL_NAME,
                 "description": "Rogers Finance certified semantic layer - simplified for demo. Revenue + Product + Region + Date. ARPU is the hero measure."},
    "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
}

DEFINITION_PBISM = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
    "version": "4.0",
}


def b64(s):
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def build_parts():
    tables = {
        "Revenue": REVENUE, "Product": PRODUCT, "Region": REGION, "Date": DATE,
    }
    parts = {
        ".platform": b64(json.dumps(PLATFORM, indent=2)),
        "definition.pbism": b64(json.dumps(DEFINITION_PBISM, indent=2)),
        "definition/database.tmdl": b64(DATABASE_TMDL),
        "definition/model.tmdl": b64(MODEL_TMDL),
        "definition/expressions.tmdl": b64(EXPRESSIONS_TMDL),
        "definition/relationships.tmdl": b64(RELATIONSHIPS_TMDL),
        "definition/cultures/en-US.tmdl": b64(CULTURES_TMDL),
    }
    for name, body in tables.items():
        parts[f"definition/tables/{name}.tmdl"] = b64(body)
    return [{"path": p, "payload": pl, "payloadType": "InlineBase64"} for p, pl in parts.items()]


def main():
    parts = build_parts()
    print(f"Built {len(parts)} parts.")
    for p in parts:
        decoded_len = len(base64.b64decode(p["payload"]))
        print(f"  {p['path']:<60s} ({decoded_len} bytes)")

    existing = find_item("SemanticModel", MODEL_NAME)
    if existing:
        print(f"\nModel '{MODEL_NAME}' exists ({existing}) - updateDefinition...")
        s, h, b = call("POST",
                       f"{API}/v1/workspaces/{WS}/semanticModels/{existing}/updateDefinition",
                       body={"definition": {"format": "TMDL", "parts": parts}})
    else:
        print(f"\nCreating semantic model '{MODEL_NAME}'...")
        body = {"displayName": MODEL_NAME,
                "description": "Rogers Finance certified semantic layer - simplified",
                "type": "SemanticModel",
                "definition": {"format": "TMDL", "parts": parts}}
        s, h, b = call("POST", f"{API}/v1/workspaces/{WS}/items", body=body)
    print(f"  status={s}")
    if s == 202:
        loc = h.get("Location") or h.get("location")
        ok, _ = poll(loc)
        if not ok:
            return
    elif s not in (200, 201):
        print(f"  ERROR: {b[:1000]}")
        return

    if not existing:
        existing = find_item("SemanticModel", MODEL_NAME)
    STACK["model_id"] = existing
    STACK_PATH.write_text(json.dumps(STACK, indent=2))
    print(f"\nModel id: {existing}")
    print(f"Open: https://msit.powerbi.com/groups/{WS}/datasets/{existing}")


if __name__ == "__main__":
    main()
