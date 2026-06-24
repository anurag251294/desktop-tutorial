"""Build the Rogers Finance certified semantic model (rogers_finance).

Direct Lake on the rogers_finance_lh lakehouse. Hero measure: ARPU.
Defined ONCE in this certified model and consumed everywhere (Excel
connected PivotTable, Power BI report, Copilot data agent) - the
slide-6 'one measure, queried everywhere' demo.

Mirrors rogers_demo/build_model.py.
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
STACK_PATH = ROOT / "stack_finance.json"
STACK = json.loads(STACK_PATH.read_text())
WS = STACK["workspace_id"]
LH = STACK["lakehouse_id"]
LH_NAME = STACK["lakehouse_name"]
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


# ---- TMDL --------------------------------------------------------------

DATABASE_TMDL = "database\n\tcompatibilityLevel: 1604\n"

MODEL_TMDL = f"""model Model
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


def t_table(name, columns, measures=None, description=""):
    """Build TMDL table block for Direct Lake.

    columns: list of (col_name, data_type, summarize_by, format_string, desc, [hidden])
    measures: list of (name, expression, format_string, desc, [display_folder])
    """
    measures = measures or []
    parts = [f"table {name}"]
    parts.append("\tlineageTag: " + str(uuid.uuid4()))

    for col in columns:
        cname, dtype, summ, fmt, desc, *rest = col
        hidden = rest[0] if rest else False
        # Optional 7th element: explicit sourceColumn (when display name differs).
        source_col = rest[1] if len(rest) > 1 else cname
        parts.append("")  # blank line before block
        if desc:
            for line in desc.splitlines():
                parts.append(f"\t/// {line}")
        parts.append(f"\tcolumn '{cname}'")
        parts.append(f"\t\tdataType: {dtype}")
        if hidden:
            parts.append(f"\t\tisHidden")
        if fmt:
            parts.append(f"\t\tformatString: {fmt}")
        parts.append(f"\t\tsourceColumn: {source_col}")
        parts.append(f"\t\tlineageTag: " + str(uuid.uuid4()))
        parts.append(f"\t\tsummarizeBy: {summ or 'none'}")

    for m in measures:
        mname, expr, fmt, desc, *rest = m
        folder = rest[0] if rest else None
        parts.append("")
        if desc:
            for line in desc.splitlines():
                parts.append(f"\t/// {line}")
        parts.append(f"\tmeasure '{mname}' = {expr}")
        if fmt:
            parts.append(f"\t\tformatString: {fmt}")
        if folder:
            parts.append(f"\t\tdisplayFolder: {folder}")
        parts.append(f"\t\tlineageTag: " + str(uuid.uuid4()))

    parts.append("\n\tpartition Partition = entity")
    parts.append("\t\tmode: directLake")
    parts.append(f"\t\tsource\n\t\t\tentityName: {name}\n\t\t\texpressionSource: DatabaseQuery")
    parts.append("\n\tannotation PBI_ResultType = Table")
    return "\n".join(parts) + "\n"


# ---- Dimension tables --------------------------------------------------

DIM_DATE = t_table(
    "dim_date",
    [
        ("date_key",       "string",   "none", None,                "Year-month key (YYYY-MM). Use for all monthly time intelligence.",         False),
        ("month_start",    "dateTime", "none", "\"yyyy-mm-dd\"",     "First calendar day of the month.",                                       False),
        ("fiscal_year",    "int64",    "none", "0",                  "Fiscal year (calendar-aligned).",                                        False),
        ("fiscal_quarter", "string",   "none", None,                 "Fiscal quarter label (Q1-Q4).",                                          False),
        ("year_quarter",   "string",   "none", None,                 "Year + quarter, e.g. 2026-Q1.",                                          False),
        ("month_number",   "int64",    "none", "0",                  "1-12 for sorting.",                                                      False),
        ("month_name",     "string",   "none", None,                 "Full month name.",                                                       False),
        ("month_label",    "string",   "none", None,                 "Short label e.g. 'Jun 2026' for axes.",                                  False),
    ],
    description="Monthly calendar. Pivot every Finance fact on date_key for ARPU, revenue, and churn trending."
)

DIM_BU = t_table(
    "dim_business_unit",
    [
        ("bu_id",   "string", "none", None, "Business unit key.", True),
        ("bu_name", "string", "none", None, "Wireless / Cable, Internet & Home / Media / Enterprise & Business.", False),
        ("bu_type", "string", "none", None, "Connectivity / Media & Sports / B2B.", False),
    ],
    description="Rogers operating segments used in external reporting. Wireless and Cable dominate revenue and ARPU narratives."
)

DIM_PRODUCT = t_table(
    "dim_product",
    [
        ("product_id",   "string", "none",  None, "Product key.", True),
        ("product_name", "string", "none",  None, "Product or plan name.", False),
        ("bu_id",        "string", "none",  None, "Owning business unit (joins to dim_business_unit).", True),
        ("revenue_type", "string", "none",  None, "Subscription / Advertising / Tickets / Project.", False),
        ("list_price",   "double", "sum",   "\"\\$#,0.00\"", "Indicative list price (for reference only - actual ARPU comes from facts).", False),
    ],
    description="Products and plans across all four BUs. Subscription products drive ARPU; ad/tickets/project revenue uses revenue-only measures."
)

DIM_REGION = t_table(
    "dim_region",
    [
        ("region_id",         "string", "none", None,        "Region key.", True),
        ("region_name",       "string", "none", None,        "Rogers reporting region.", False),
        ("province_code",     "string", "none", None,        "Two-letter Canadian province code.", False),
        ("population_weight", "double", "sum",  "\"0.00%\"", "Approx share of Canadian population - used to weight regional facts.", False),
    ],
    description="Rogers regional / provincial segmentation. Use for province- or region-level ARPU breakouts."
)

DIM_SEG = t_table(
    "dim_customer_segment",
    [
        ("segment_id",   "string", "none", None, "Segment key.", True),
        ("segment_name", "string", "none", None, "Consumer Postpaid/Prepaid/Premium, Small Business, Mid-Market, Large Enterprise, Public Sector.", False),
        ("segment_type", "string", "none", None, "Consumer / SMB / Enterprise.", False),
    ],
    description="Customer segmentation. Premium and Enterprise segments anchor the highest ARPU."
)

DIM_CHANNEL = t_table(
    "dim_channel",
    [
        ("channel_id",   "string", "none", None, "Channel key.", True),
        ("channel_name", "string", "none", None, "Retail / Online / Call Centre / Dealer / Enterprise Account Team.", False),
    ],
    description="Acquisition channel. Use for channel-level CAC and acquisition mix - not directly joined to revenue."
)


# ---- Fact tables -------------------------------------------------------

FACT_REVENUE = t_table(
    "fact_revenue_monthly",
    [
        ("date_key",   "string", "none", None,                "Joins dim_date.",                          True),
        ("bu_id",      "string", "none", None,                "Joins dim_business_unit.",                 True),
        ("product_id", "string", "none", None,                "Joins dim_product.",                       True),
        ("region_id",  "string", "none", None,                "Joins dim_region.",                        True),
        ("revenue_amount", "double", "sum",  "\"\\$#,0;-\\$#,0\"","Net monthly revenue in CAD (use the [Revenue] measure instead).", True, "revenue"),
        ("list_arpu",      "double", "average", "\"\\$#,0.00\"",  "Weighted avg list-price ARPU (analytic only).", True),
    ],
    measures=[
        # The hero - defined ONCE.
        ("Revenue",                  "SUM(fact_revenue_monthly[revenue_amount])",
         "\"\\$#,0;-\\$#,0\"",      "Total monthly revenue in CAD across all business units.",
         "01 Revenue"),
        ("Revenue (Millions)",
         "DIVIDE([Revenue], 1000000)",
         "\"\\$#,0.0\"",  "Revenue scaled to millions for executive views (so $1,234.5 = $1.23B).",
         "01 Revenue"),
        ("Revenue MoM %",
         "DIVIDE([Revenue] - CALCULATE([Revenue], DATEADD(dim_date[month_start], -1, MONTH)), CALCULATE([Revenue], DATEADD(dim_date[month_start], -1, MONTH)))",
         "\"0.0%;-0.0%\"",          "Month-over-month revenue change.",
         "01 Revenue"),
        ("Revenue YoY %",
         "DIVIDE([Revenue] - CALCULATE([Revenue], DATEADD(dim_date[month_start], -12, MONTH)), CALCULATE([Revenue], DATEADD(dim_date[month_start], -12, MONTH)))",
         "\"0.0%;-0.0%\"",          "Year-over-year revenue change.",
         "01 Revenue"),

        # ARPU - the certified measure the demo revolves around.
        ("ARPU",
         "DIVIDE([Revenue], [Average Subscribers])",
         "\"\\$#,0.00\"",
         "Average Revenue Per User = Total Revenue / Average Subscribers. This is the CERTIFIED enterprise ARPU - defined once here and used everywhere (Power BI, Excel pivot, Copilot, downstream tools).",
         "02 ARPU"),
        ("ARPU - Wireless",
         "CALCULATE([ARPU], dim_business_unit[bu_name] = \"Wireless\")",
         "\"\\$#,0.00\"",
         "ARPU filtered to Wireless. Use in summary tiles and IR-style reporting.",
         "02 ARPU"),
        ("ARPU - Cable & Home",
         "CALCULATE([ARPU], dim_business_unit[bu_name] = \"Cable, Internet & Home\")",
         "\"\\$#,0.00\"",
         "ARPU filtered to Cable, Internet & Home.",
         "02 ARPU"),
        ("ARPU - Media",
         "CALCULATE([ARPU], dim_business_unit[bu_name] = \"Media\")",
         "\"\\$#,0.00\"",
         "ARPU filtered to Media (subscription products only).",
         "02 ARPU"),
        ("ARPU - Enterprise",
         "CALCULATE([ARPU], dim_business_unit[bu_name] = \"Enterprise & Business\")",
         "\"\\$#,0.00\"",
         "ARPU filtered to Enterprise & Business.",
         "02 ARPU"),
        ("ARPU MoM %",
         "DIVIDE([ARPU] - CALCULATE([ARPU], DATEADD(dim_date[month_start], -1, MONTH)), CALCULATE([ARPU], DATEADD(dim_date[month_start], -1, MONTH)))",
         "\"0.0%;-0.0%\"",          "Month-over-month ARPU drift.",
         "02 ARPU"),
        ("ARPU YoY %",
         "DIVIDE([ARPU] - CALCULATE([ARPU], DATEADD(dim_date[month_start], -12, MONTH)), CALCULATE([ARPU], DATEADD(dim_date[month_start], -12, MONTH)))",
         "\"0.0%;-0.0%\"",          "Year-over-year ARPU drift.",
         "02 ARPU"),
    ],
    description="Monthly revenue at BU x product x region grain. Anchor of Finance reporting. Combine with fact_subscribers_monthly to compute the certified ARPU measure."
)

FACT_SUBS = t_table(
    "fact_subscribers_monthly",
    [
        ("date_key",          "string", "none",    None, "Joins dim_date.",            True),
        ("bu_id",             "string", "none",    None, "Joins dim_business_unit.",   True),
        ("product_id",        "string", "none",    None, "Joins dim_product.",         True),
        ("region_id",         "string", "none",    None, "Joins dim_region.",          True),
        ("segment_id",        "string", "none",    None, "Joins dim_customer_segment.",True),
        ("avg_subscribers",   "int64",  "sum",     "\"#,0\"", "Average subscriber count during the month (denominator for ARPU).", False),
        ("end_subscribers",   "int64",  "sum",     "\"#,0\"", "End-of-month subscriber count (used for net-add calculations).",    False),
    ],
    measures=[
        ("Average Subscribers",
         "SUM(fact_subscribers_monthly[avg_subscribers])",
         "\"#,0\"",
         "Avg in-period subscribers across all BUs / segments. Denominator for the certified ARPU measure.",
         "03 Subscribers"),
        ("End-of-Period Subscribers",
         "SUM(fact_subscribers_monthly[end_subscribers])",
         "\"#,0\"",
         "End-of-month subscribers. Use for net-add and subscriber-balance views.",
         "03 Subscribers"),
        ("Net Adds (MoM)",
         "[End-of-Period Subscribers] - CALCULATE([End-of-Period Subscribers], DATEADD(dim_date[month_start], -1, MONTH))",
         "\"#,0;-#,0\"",
         "Subscriber net adds month-over-month.",
         "03 Subscribers"),
    ],
    description="Monthly subscriber counts at BU x product x region x segment grain. ARPU denominator lives here."
)

FACT_CHURN = t_table(
    "fact_churn_monthly",
    [
        ("date_key",            "string", "none", None,       "Joins dim_date.",          True),
        ("bu_id",               "string", "none", None,       "Joins dim_business_unit.", True),
        ("product_id",          "string", "none", None,       "Joins dim_product.",       True),
        ("region_id",           "string", "none", None,       "Joins dim_region.",        True),
        ("gross_adds",          "int64",  "sum",  "\"#,0\"",  "Subscribers added in the month.", False),
        ("voluntary_churn",     "int64",  "sum",  "\"#,0\"",  "Subscribers who left voluntarily.", False),
        ("involuntary_churn",   "int64",  "sum",  "\"#,0\"",  "Subscribers disconnected for non-payment.", False),
    ],
    measures=[
        ("Gross Adds",          "SUM(fact_churn_monthly[gross_adds])",
         "\"#,0\"",             "Total subscriber gross adds in the month.",          "04 Churn"),
        ("Voluntary Churn",     "SUM(fact_churn_monthly[voluntary_churn])",
         "\"#,0\"",             "Subscribers who left voluntarily.",                  "04 Churn"),
        ("Involuntary Churn",   "SUM(fact_churn_monthly[involuntary_churn])",
         "\"#,0\"",             "Subscribers disconnected non-pay.",                  "04 Churn"),
        ("Churn Rate %",
         "DIVIDE([Voluntary Churn] + [Involuntary Churn], [Average Subscribers])",
         "\"0.00%;-0.00%\"",
         "Total churn / average subscribers, monthly.",                                "04 Churn"),
    ],
    description="Monthly subscriber adds and churn at BU x product x region grain. Pairs with fact_subscribers_monthly to compute churn rate."
)

FACT_COSTS = t_table(
    "fact_costs_monthly",
    [
        ("date_key",                    "string", "none", None,        "Joins dim_date.",          True),
        ("bu_id",                       "string", "none", None,        "Joins dim_business_unit.", True),
        ("product_id",                  "string", "none", None,        "Joins dim_product.",       True),
        ("region_id",                   "string", "none", None,        "Joins dim_region.",        True),
        ("cogs",                        "double", "sum", "\"\\$#,0\"", "Cost of goods sold.", False),
        ("network_opex",                "double", "sum", "\"\\$#,0\"", "Network operating cost allocation.", False),
        ("customer_acquisition_cost",   "double", "sum", "\"\\$#,0\"", "CAC for the month.", False),
    ],
    measures=[
        ("Total Cost",
         "SUM(fact_costs_monthly[cogs]) + SUM(fact_costs_monthly[network_opex]) + SUM(fact_costs_monthly[customer_acquisition_cost])",
         "\"\\$#,0;-\\$#,0\"",     "COGS + network opex + CAC.",                       "05 Cost & Margin"),
        ("Gross Margin",
         "[Revenue] - SUM(fact_costs_monthly[cogs])",
         "\"\\$#,0;-\\$#,0\"",     "Revenue - COGS.",                                  "05 Cost & Margin"),
        ("Gross Margin %",
         "DIVIDE([Gross Margin], [Revenue])",
         "\"0.0%;-0.0%\"",          "Gross margin as a % of revenue.",                  "05 Cost & Margin"),
        ("EBITDA (proxy)",
         "[Revenue] - [Total Cost]",
         "\"\\$#,0;-\\$#,0\"",     "Revenue minus all modeled costs (not GAAP EBITDA).", "05 Cost & Margin"),
        ("CAC per Gross Add",
         "DIVIDE(SUM(fact_costs_monthly[customer_acquisition_cost]), [Gross Adds])",
         "\"\\$#,0.00\"",          "Customer acquisition cost per gross add.",         "05 Cost & Margin"),
    ],
    description="Monthly cost allocation by BU x product x region. Feeds margin, EBITDA proxy, and CAC measures."
)


RELATIONSHIPS_TMDL = """relationship rel_revenue_date
\tfromColumn: fact_revenue_monthly.date_key
\ttoColumn: dim_date.date_key

relationship rel_revenue_bu
\tfromColumn: fact_revenue_monthly.bu_id
\ttoColumn: dim_business_unit.bu_id

relationship rel_revenue_product
\tfromColumn: fact_revenue_monthly.product_id
\ttoColumn: dim_product.product_id

relationship rel_revenue_region
\tfromColumn: fact_revenue_monthly.region_id
\ttoColumn: dim_region.region_id

relationship rel_subs_date
\tfromColumn: fact_subscribers_monthly.date_key
\ttoColumn: dim_date.date_key

relationship rel_subs_bu
\tfromColumn: fact_subscribers_monthly.bu_id
\ttoColumn: dim_business_unit.bu_id

relationship rel_subs_product
\tfromColumn: fact_subscribers_monthly.product_id
\ttoColumn: dim_product.product_id

relationship rel_subs_region
\tfromColumn: fact_subscribers_monthly.region_id
\ttoColumn: dim_region.region_id

relationship rel_subs_segment
\tfromColumn: fact_subscribers_monthly.segment_id
\ttoColumn: dim_customer_segment.segment_id

relationship rel_churn_date
\tfromColumn: fact_churn_monthly.date_key
\ttoColumn: dim_date.date_key

relationship rel_churn_bu
\tfromColumn: fact_churn_monthly.bu_id
\ttoColumn: dim_business_unit.bu_id

relationship rel_churn_product
\tfromColumn: fact_churn_monthly.product_id
\ttoColumn: dim_product.product_id

relationship rel_churn_region
\tfromColumn: fact_churn_monthly.region_id
\ttoColumn: dim_region.region_id

relationship rel_costs_date
\tfromColumn: fact_costs_monthly.date_key
\ttoColumn: dim_date.date_key

relationship rel_costs_bu
\tfromColumn: fact_costs_monthly.bu_id
\ttoColumn: dim_business_unit.bu_id

relationship rel_costs_product
\tfromColumn: fact_costs_monthly.product_id
\ttoColumn: dim_product.product_id

relationship rel_costs_region
\tfromColumn: fact_costs_monthly.region_id
\ttoColumn: dim_region.region_id
"""

CULTURES_TMDL = "cultureInfo en-US\n"


# ---- Example prompts (saved on the model for Copilot) ------------------

EXAMPLE_PROMPTS = [
    "Give me a Finance briefing for the latest month: revenue, ARPU, net adds.",
    "Compare ARPU across Wireless, Cable, Media, and Enterprise for the last quarter.",
    "Which business unit grew ARPU the most year over year?",
    "Show me ARPU by region for Wireless Postpaid - which provinces are above the national average?",
    "What happened to Wireless Prepaid ARPU in April 2026?",
    "Top 5 products by revenue last month, with their ARPU and gross margin.",
    "Trend gross margin % for Cable, Internet & Home over the past 12 months.",
    "Which segment opened the most subscribers last quarter, and what is their blended ARPU?",
    "How does the certified ARPU here reconcile to the ARPU we report externally?",
    "Show me CAC per gross add by channel for the latest month.",
]


# ---- Build / patch -----------------------------------------------------

def b64(s):
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


PLATFORM = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
    "metadata": {"type": "SemanticModel", "displayName": MODEL_NAME,
                 "description": "Rogers Enterprise Semantic Layer - certified Finance model. ARPU defined once and consumed everywhere (Power BI, Excel, Copilot)."},
    "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
}

DEFINITION_PBISM = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
    "version": "4.0",
}


def build_parts():
    tables = {
        "dim_date":                 DIM_DATE,
        "dim_business_unit":        DIM_BU,
        "dim_product":              DIM_PRODUCT,
        "dim_region":               DIM_REGION,
        "dim_customer_segment":     DIM_SEG,
        "dim_channel":              DIM_CHANNEL,
        "fact_revenue_monthly":     FACT_REVENUE,
        "fact_subscribers_monthly": FACT_SUBS,
        "fact_churn_monthly":       FACT_CHURN,
        "fact_costs_monthly":       FACT_COSTS,
    }
    parts = {
        ".platform":                                  b64(json.dumps(PLATFORM, indent=2)),
        "definition.pbism":                           b64(json.dumps(DEFINITION_PBISM, indent=2)),
        "definition/database.tmdl":                   b64(DATABASE_TMDL),
        "definition/model.tmdl":                      b64(MODEL_TMDL),
        "definition/expressions.tmdl":                b64(EXPRESSIONS_TMDL),
        "definition/relationships.tmdl":              b64(RELATIONSHIPS_TMDL),
        "definition/cultures/en-US.tmdl":             b64(CULTURES_TMDL),
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
                "description": "Rogers Enterprise Semantic Layer - certified Finance model with ARPU",
                "type": "SemanticModel",
                "definition": {"format": "TMDL", "parts": parts}}
        s, h, b = call("POST", f"{API}/v1/workspaces/{WS}/items", body=body)
    print(f"  status={s}")
    model_id = existing
    if s == 202:
        loc = h.get("Location") or h.get("location")
        ok, result_url = poll(loc)
        if not ok:
            return
        if not existing:
            sr, hr, br = call("GET", result_url)
            item = json.loads(br)
            model_id = item["id"]
    elif s in (200, 201) and not existing:
        try:
            model_id = json.loads(b)["id"]
        except Exception:
            pass
    elif s not in (200, 201, 202):
        print(f"  ERROR: {b[:1000]}")
        return

    if model_id:
        STACK["model_id"] = model_id
        STACK["model_name"] = MODEL_NAME
        STACK["example_prompts"] = EXAMPLE_PROMPTS
        STACK_PATH.write_text(json.dumps(STACK, indent=2))
        print(f"\nModel id: {model_id}")
        print(f"Open: https://msit.powerbi.com/groups/{WS}/datasets/{model_id}")


if __name__ == "__main__":
    main()
