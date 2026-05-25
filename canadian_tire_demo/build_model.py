"""Build the ctc_merch Direct Lake semantic model.

Direct Lake on OneLake against the CTC lakehouse. Every column and measure
gets a TMDL `/// description` for Copilot quality. examplePrompts.json is
seeded with the customer's actual question set.

Tables: dim_date, dim_sku, dim_vendor, dim_season,
        fact_sku_performance, fact_in_season, fact_connected_inventory
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
STACK = json.loads((ROOT / "stack_ctc.json").read_text())
WS = STACK["workspace_id"]
LH = STACK["lakehouse_id"]
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"
MODEL_NAME = "ctc_merch"


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
    for i in range(90):
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


# ---- COLUMNS ----------------------------------------------------------------

def col(name, dtype, desc=None, fmt=None, is_key=False,
        summarize="none", source=None):
    """Render a TMDL column block. dtype: 'string','int64','double','dateTime'."""
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


# ---- TABLE TMDLs ------------------------------------------------------------

def tmdl_dim_date():
    cols = [
        col("Week_End_Date", "string", "Week-ending Sunday date in YYYY-MM-DD form. Used to align POS, shipment and inventory weekly trends.", is_key=True),
        col("Year", "int64", "Calendar year. Use for YoY (year-over-year) comparisons.", fmt="0", summarize="none"),
        col("Quarter", "string", "Calendar quarter label (Q1-Q4). Used for QTD (quarter-to-date) views."),
        col("Year_Quarter", "string", "Year and quarter together, e.g. '2026-Q2'. Used for trend axis."),
        col("Year_Month", "string", "Year-month label, e.g. '2026-05'. Used for monthly POS, RVS, EGM trend visuals."),
        col("Week_Number", "int64", "ISO week number 1-53.", fmt="0"),
        col("Fiscal_Year_Label", "string", "Fiscal year label like FY26. Synonyms: fiscal year, FY."),
    ]
    return table_header("dim_date") + "\n".join(cols) + "\n" + partition("dim_date", EXPR_NAME)


def tmdl_dim_sku():
    cols = [
        col("SKU", "string", "Stock Keeping Unit. Unique alphanumeric product identifier (e.g. AL-LED-001). Synonyms: item, product, article.", is_key=True),
        col("SKU_Name", "string", "Descriptive product name including brand, type, and pack size. Synonyms: product name, item name."),
        col("Category", "string", "Top-level product classification, e.g. Auto Lighting, Kitchen & Small Appliances, Canvas Outdoor, Tools. Synonyms: department, category."),
        col("Subcategory", "string", "Secondary product classification within a category, e.g. Automotive, Cookware, Outdoor Living."),
        col("Fineline", "string", "Fineline code - finest level of product hierarchy."),
        col("Fineline_Name", "string", "Full fineline name, e.g. 'Air Fryers', 'LED Bulbs', 'Cookware Sets'. The granular product grouping merchants plan against."),
        col("Vendor", "string", "Supplier or manufacturer name. Synonyms: supplier, manufacturer."),
        col("Brand", "string", "Consumer-facing brand name."),
        col("New_SKU_Flag", "string", "Y if the SKU is new this season, N otherwise. Synonyms: new product, newness, NPI."),
        col("Status", "string", "Lifecycle status: ACT (active), DCT (discontinued), PND (pending). Synonyms: lifecycle, item status."),
        col("Retail_Price", "double", "Selling price in CAD.", fmt="\"\\$\"#,0.00;-\"\\$\"#,0.00;\"\\$\"#,0.00"),
        col("Cost", "double", "Unit cost (COGS) in CAD.", fmt="\"\\$\"#,0.00;-\"\\$\"#,0.00;\"\\$\"#,0.00"),
        col("Store_Count", "int64", "Number of stores currently stocking this SKU.", fmt="#,##0"),
        col("Margin_Per_Unit", "double", "Retail price minus cost, in CAD per unit.", fmt="\"\\$\"#,0.00;-\"\\$\"#,0.00;\"\\$\"#,0.00"),
    ]
    return table_header("dim_sku") + "\n".join(cols) + "\n" + partition("dim_sku", EXPR_NAME)


def tmdl_dim_vendor():
    cols = [
        col("Vendor", "string", "Vendor / supplier name. Joins to dim_sku.Vendor.", is_key=True),
        col("Vendor_Country", "string", "Country where the vendor is based. Synonyms: country of origin."),
        col("Lead_Time_Weeks", "int64", "Typical replenishment lead time in weeks. Use when assessing fill-rate risk.", fmt="#,##0"),
        col("Scorecard_Tier", "string", "Vendor scorecard tier: Gold, Silver, or Bronze."),
        col("Onboarding_Year", "int64", "Year vendor was first onboarded.", fmt="0"),
        col("Sustainability_Index", "double", "Composite sustainability score 0-1 (higher is better).", fmt="0.00"),
    ]
    return table_header("dim_vendor") + "\n".join(cols) + "\n" + partition("dim_vendor", EXPR_NAME)


def tmdl_dim_season():
    cols = [
        col("Season_Code", "string", "Season code like 'S3 Spring'. Joins to fact_in_season.Season.", is_key=True),
        col("Season_Name", "string", "Friendly season name (Spring, Summer, Fall, Winter)."),
        col("Season_Start", "string", "Season start date."),
        col("Season_End", "string", "Season end date."),
        col("Display_Order", "int64", "Sort order for season axis.", fmt="0"),
    ]
    return table_header("dim_season") + "\n".join(cols) + "\n" + partition("dim_season", EXPR_NAME)


def tmdl_fact_sku_performance():
    cols = [
        col("SKU", "string", "Foreign key to dim_sku.", is_key=True),
        col("TY_POS_Units", "int64", "This-year point-of-sale units sold.", fmt="#,##0", summarize="sum"),
        col("LY_POS_Units", "int64", "Last-year point-of-sale units sold.", fmt="#,##0", summarize="sum"),
        col("TY_POS_Dollars", "double", "This-year POS (Point-of-Sale) sales in CAD = units sold x retail price.", fmt="\"\\$\"#,0;-\"\\$\"#,0;\"\\$\"#,0", summarize="sum"),
        col("LY_POS_Dollars", "double", "Last-year POS sales in CAD.", fmt="\"\\$\"#,0;-\"\\$\"#,0;\"\\$\"#,0", summarize="sum"),
        col("TY_RVS", "double", "This-year RVS (Retail Value of Shipments) = units shipped x retail price, in CAD.", fmt="\"\\$\"#,0;-\"\\$\"#,0;\"\\$\"#,0", summarize="sum"),
        col("LY_RVS", "double", "Last-year RVS in CAD.", fmt="\"\\$\"#,0;-\"\\$\"#,0;\"\\$\"#,0", summarize="sum"),
        col("TY_EGM_Dollars", "double", "This-year EGM (Enterprise Gross Margin dollars) = RVS - COGS, in CAD.", fmt="\"\\$\"#,0;-\"\\$\"#,0;\"\\$\"#,0", summarize="sum"),
        col("LY_EGM_Dollars", "double", "Last-year EGM dollars in CAD.", fmt="\"\\$\"#,0;-\"\\$\"#,0;\"\\$\"#,0", summarize="sum"),
        col("TY_EGM_Pct", "double", "This-year EGM % = EGM $ / RVS (stored as raw points e.g. 43.5).", fmt="0.0\"%\"", summarize="none"),
        col("LY_EGM_Pct", "double", "Last-year EGM % (stored as raw points).", fmt="0.0\"%\"", summarize="none"),
        col("QTD_POS_Dollars", "double", "Quarter-to-date POS dollars (CAD).", fmt="\"\\$\"#,0;-\"\\$\"#,0;\"\\$\"#,0", summarize="sum"),
        col("YTD_POS_Dollars", "double", "Year-to-date POS dollars (CAD).", fmt="\"\\$\"#,0;-\"\\$\"#,0;\"\\$\"#,0", summarize="sum"),
        col("R12_POS_Dollars", "double", "Rolling 12-month POS dollars (CAD). Synonyms: R12, trailing twelve months.", fmt="\"\\$\"#,0;-\"\\$\"#,0;\"\\$\"#,0", summarize="sum"),
    ]
    measures = [
        measure("POS $ TY", "SUM(fact_sku_performance[TY_POS_Dollars])",
                "This-year POS (Point-of-Sale) dollars across the current filter context.",
                fmt="\"\\$\"#,0;-\"\\$\"#,0;\"\\$\"#,0", folder="Sales"),
        measure("POS $ LY", "SUM(fact_sku_performance[LY_POS_Dollars])",
                "Last-year POS dollars.",
                fmt="\"\\$\"#,0;-\"\\$\"#,0;\"\\$\"#,0", folder="Sales"),
        measure("POS YoY $", "[POS $ TY] - [POS $ LY]",
                "POS YoY change in dollars: TY minus LY POS $.",
                fmt="\"\\$\"#,0;-\"\\$\"#,0;\"\\$\"#,0", folder="Sales"),
        measure("POS YoY %", "DIVIDE([POS $ TY] - [POS $ LY], [POS $ LY])",
                "POS year-over-year percent change. Negative = decline.",
                fmt="0.0%", folder="Sales"),
        measure("POS Units TY", "SUM(fact_sku_performance[TY_POS_Units])",
                "This-year POS units sold.", fmt="#,##0", folder="Sales"),
        measure("POS Units LY", "SUM(fact_sku_performance[LY_POS_Units])",
                "Last-year POS units sold.", fmt="#,##0", folder="Sales"),
        measure("RVS TY", "SUM(fact_sku_performance[TY_RVS])",
                "This-year Retail Value of Shipments (units shipped x retail price).",
                fmt="\"\\$\"#,0;-\"\\$\"#,0;\"\\$\"#,0", folder="Shipments"),
        measure("RVS LY", "SUM(fact_sku_performance[LY_RVS])",
                "Last-year RVS in CAD.",
                fmt="\"\\$\"#,0;-\"\\$\"#,0;\"\\$\"#,0", folder="Shipments"),
        measure("RVS YoY %", "DIVIDE([RVS TY] - [RVS LY], [RVS LY])",
                "RVS year-over-year percent change.", fmt="0.0%", folder="Shipments"),
        measure("EGM $ TY", "SUM(fact_sku_performance[TY_EGM_Dollars])",
                "This-year Enterprise Gross Margin (RVS minus COGS).",
                fmt="\"\\$\"#,0;-\"\\$\"#,0;\"\\$\"#,0", folder="Profitability"),
        measure("EGM $ LY", "SUM(fact_sku_performance[LY_EGM_Dollars])",
                "Last-year EGM dollars.",
                fmt="\"\\$\"#,0;-\"\\$\"#,0;\"\\$\"#,0", folder="Profitability"),
        measure("EGM YoY $", "[EGM $ TY] - [EGM $ LY]",
                "EGM YoY change in dollars.",
                fmt="\"\\$\"#,0;-\"\\$\"#,0;\"\\$\"#,0", folder="Profitability"),
        measure("EGM YoY %", "DIVIDE([EGM $ TY] - [EGM $ LY], [EGM $ LY])",
                "EGM year-over-year percent change.", fmt="0.0%", folder="Profitability"),
        measure("EGM % TY", "DIVIDE(SUM(fact_sku_performance[TY_EGM_Dollars]), SUM(fact_sku_performance[TY_RVS]))",
                "This-year EGM % (margin rate) = EGM $ / RVS.",
                fmt="0.0%", folder="Profitability"),
        measure("EGM % LY", "DIVIDE(SUM(fact_sku_performance[LY_EGM_Dollars]), SUM(fact_sku_performance[LY_RVS]))",
                "Last-year EGM % (margin rate).",
                fmt="0.0%", folder="Profitability"),
        measure("EGM Margin Bps Change", "([EGM % TY] - [EGM % LY]) * 10000",
                "EGM margin rate change in basis points (positive = margin expansion).",
                fmt="#,##0\" bps\"", folder="Profitability"),
        measure("POS $ QTD", "SUM(fact_sku_performance[QTD_POS_Dollars])",
                "Quarter-to-date POS dollars.",
                fmt="\"\\$\"#,0;-\"\\$\"#,0;\"\\$\"#,0", folder="Timeframes"),
        measure("POS $ YTD", "SUM(fact_sku_performance[YTD_POS_Dollars])",
                "Year-to-date POS dollars.",
                fmt="\"\\$\"#,0;-\"\\$\"#,0;\"\\$\"#,0", folder="Timeframes"),
        measure("POS $ R12", "SUM(fact_sku_performance[R12_POS_Dollars])",
                "Rolling 12 months POS dollars (R12). Synonyms: R12, trailing 12 months.",
                fmt="\"\\$\"#,0;-\"\\$\"#,0;\"\\$\"#,0", folder="Timeframes"),
        measure("# SKUs", "DISTINCTCOUNT(dim_sku[SKU])",
                "Distinct count of SKUs in the current filter.",
                fmt="#,##0", folder="Counts"),
        measure("# Active SKUs", "CALCULATE([# SKUs], dim_sku[Status] = \"ACT\")",
                "Count of SKUs in ACT (Active) lifecycle status.",
                fmt="#,##0", folder="Counts"),
        measure("# New SKUs", "CALCULATE([# SKUs], dim_sku[New_SKU_Flag] = \"Y\")",
                "Count of SKUs flagged as new this season. Synonyms: NPI count.",
                fmt="#,##0", folder="Counts"),
        measure("New SKU POS $ TY", "CALCULATE([POS $ TY], dim_sku[New_SKU_Flag] = \"Y\")",
                "This-year POS dollars driven by new (first-season) SKUs only.",
                fmt="\"\\$\"#,0;-\"\\$\"#,0;\"\\$\"#,0", folder="Newness"),
        measure("New SKU EGM $ TY", "CALCULATE([EGM $ TY], dim_sku[New_SKU_Flag] = \"Y\")",
                "This-year EGM dollars from new SKUs.",
                fmt="\"\\$\"#,0;-\"\\$\"#,0;\"\\$\"#,0", folder="Newness"),
        measure("% POS $ from New SKUs", "DIVIDE([New SKU POS $ TY], [POS $ TY])",
                "Share of TY POS dollars coming from new SKUs.",
                fmt="0.0%", folder="Newness"),
    ]
    return table_header("fact_sku_performance") + "\n".join(cols) + "\n" + "".join(measures) + partition("fact_sku_performance", EXPR_NAME)


def tmdl_fact_in_season():
    cols = [
        col("SKU", "string", "Foreign key to dim_sku.", is_key=True),
        col("Season", "string", "Season code, joins to dim_season.Season_Code."),
        col("YTD_TY_POS", "int64", "Year-to-date this-year POS units (in-season).", fmt="#,##0", summarize="sum"),
        col("YTD_LY_POS", "int64", "Year-to-date last-year POS units.", fmt="#,##0", summarize="sum"),
        col("YTD_TY_Ship", "int64", "Year-to-date this-year shipment units.", fmt="#,##0", summarize="sum"),
        col("YTD_LY_Ship", "int64", "Year-to-date last-year shipment units.", fmt="#,##0", summarize="sum"),
        col("Retail_Inv_TY", "int64", "Current units of inventory in retail stores.", fmt="#,##0", summarize="sum"),
        col("Corp_Inv_TY", "int64", "Current units in corporate / distribution-center inventory.", fmt="#,##0", summarize="sum"),
        col("Current_POS_Forecast", "int64", "Forecasted remaining-season POS units (demand forecast).", fmt="#,##0", summarize="sum"),
        col("Current_Ship_Forecast", "int64", "Forecasted remaining-season shipment units (supply forecast).", fmt="#,##0", summarize="sum"),
        col("Open_PO_Qty", "int64", "Units on open purchase orders awaiting receipt.", fmt="#,##0", summarize="sum"),
        col("Planned_Purchase_Qty", "int64", "Units in the planned-purchase pipeline.", fmt="#,##0", summarize="sum"),
        col("Weeks_of_Supply", "double", "Weeks of Supply (WoS) = inventory / weekly POS run-rate. High WoS = overstock risk.", fmt="#,##0.0", summarize="none"),
    ]
    measures = [
        measure("POS Units YTD TY", "SUM(fact_in_season[YTD_TY_POS])",
                "In-season YTD POS units this year.", folder="In-Season Demand"),
        measure("POS Units YTD LY", "SUM(fact_in_season[YTD_LY_POS])",
                "In-season YTD POS units last year.", folder="In-Season Demand"),
        measure("POS YoY % (In-Season)", "DIVIDE([POS Units YTD TY] - [POS Units YTD LY], [POS Units YTD LY])",
                "YoY change in in-season POS units.", fmt="0.0%", folder="In-Season Demand"),
        measure("Ship Units YTD TY", "SUM(fact_in_season[YTD_TY_Ship])",
                "In-season YTD shipment units this year.", folder="In-Season Supply"),
        measure("Ship Units YTD LY", "SUM(fact_in_season[YTD_LY_Ship])",
                "In-season YTD shipment units last year.", folder="In-Season Supply"),
        measure("Demand vs Supply Gap", "[Ship Units YTD TY] - [POS Units YTD TY]",
                "Shipment units minus POS units. Positive = supply ahead of demand, negative = demand outrunning supply.",
                folder="In-Season Supply"),
        measure("Retail Inventory (units)", "SUM(fact_in_season[Retail_Inv_TY])",
                "Total in-store retail inventory units.", folder="Inventory"),
        measure("Corp Inventory (units)", "SUM(fact_in_season[Corp_Inv_TY])",
                "Total corporate / distribution-center inventory units.", folder="Inventory"),
        measure("Total Inventory (units)", "[Retail Inventory (units)] + [Corp Inventory (units)]",
                "Retail + corporate inventory combined.", folder="Inventory"),
        measure("Open PO Units", "SUM(fact_in_season[Open_PO_Qty])",
                "Units on open purchase orders.", folder="Pipeline"),
        measure("Planned Purchase Units", "SUM(fact_in_season[Planned_Purchase_Qty])",
                "Units in planned-purchase plan.", folder="Pipeline"),
        measure("POS Forecast Units", "SUM(fact_in_season[Current_POS_Forecast])",
                "Remaining-season POS forecast.", folder="Pipeline"),
        measure("Ship Forecast Units", "SUM(fact_in_season[Current_Ship_Forecast])",
                "Remaining-season shipment forecast.", folder="Pipeline"),
        measure("Avg Weeks of Supply", "AVERAGE(fact_in_season[Weeks_of_Supply])",
                "Average Weeks of Supply (WoS) across the filter. Higher = more risk of overstock; very high (>18) is a markdown candidate.",
                fmt="#,##0.0", folder="WoS"),
        measure("# SKUs Overstock (WoS>18)",
                "COUNTROWS(FILTER(VALUES(dim_sku[SKU]), CALCULATE(MAX(fact_in_season[Weeks_of_Supply])) > 18))",
                "Count of SKUs with weeks-of-supply above 18 - classic overstock signal.", folder="WoS"),
        measure("# SKUs Understock (WoS<4)",
                "COUNTROWS(FILTER(VALUES(dim_sku[SKU]), CALCULATE(MAX(fact_in_season[Weeks_of_Supply])) < 4))",
                "Count of SKUs with weeks-of-supply below 4 - replenishment-needed signal.", folder="WoS"),
    ]
    return table_header("fact_in_season") + "\n".join(cols) + "\n" + "".join(measures) + partition("fact_in_season", EXPR_NAME)


def tmdl_fact_connected_inventory():
    cols = [
        col("SKU", "string", "Foreign key to dim_sku.", is_key=True),
        col("Corp_Inv_Units_TY", "int64", "Corporate inventory units this year.", fmt="#,##0", summarize="sum"),
        col("Corp_Inv_Units_LY", "int64", "Corporate inventory units last year.", fmt="#,##0", summarize="sum"),
        col("Retail_Inv_Units_TY", "int64", "Retail-store inventory units this year.", fmt="#,##0", summarize="sum"),
        col("Retail_Inv_Units_LY", "int64", "Retail-store inventory units last year.", fmt="#,##0", summarize="sum"),
        col("YTD_POS_TY", "int64", "Year-to-date POS units this year.", fmt="#,##0", summarize="sum"),
        col("YTD_POS_LY", "int64", "Year-to-date POS units last year.", fmt="#,##0", summarize="sum"),
        col("YTD_POS_Change_Pct", "double", "YTD POS % change YoY (stored as raw points e.g. 3.7).", fmt="0.0\"%\"", summarize="none"),
        col("R8_POS_TY", "int64", "Rolling-8-week POS units this year (R8 sales velocity).", fmt="#,##0", summarize="sum"),
        col("R8_POS_LY", "int64", "Rolling-8-week POS units last year.", fmt="#,##0", summarize="sum"),
        col("R8_POS_Change_Pct", "double", "R8 POS % change YoY (stored as raw points). Short-term momentum signal.", fmt="0.0\"%\"", summarize="none"),
        col("YTD_Lost_Sales_Pct", "double", "Lost Sales % - percent of demand unfilled due to stockouts (stored as raw points). Synonyms: stockout rate.", fmt="0.0\"%\"", summarize="none"),
        col("Vendor_Fill_Rate_Pct", "double", "Vendor Fill Rate % - percent of vendor PO units received on time (stored as raw points).", fmt="0.0\"%\"", summarize="none"),
        col("Ship_Units_TY", "int64", "Shipment units this year.", fmt="#,##0", summarize="sum"),
        col("Ship_Units_LY", "int64", "Shipment units last year.", fmt="#,##0", summarize="sum"),
        col("DDF_Units", "int64", "Distribution-driven fill units.", fmt="#,##0", summarize="sum"),
    ]
    measures = [
        measure("Corp Inv TY", "SUM(fact_connected_inventory[Corp_Inv_Units_TY])",
                "Corporate inventory units (DC) this year.", folder="Inventory Health"),
        measure("Retail Inv TY", "SUM(fact_connected_inventory[Retail_Inv_Units_TY])",
                "Retail-store inventory units this year.", folder="Inventory Health"),
        measure("Total Inv TY", "[Corp Inv TY] + [Retail Inv TY]",
                "Total inventory units (corp + retail) this year.", folder="Inventory Health"),
        measure("Inv YoY Units", "([Corp Inv TY] + [Retail Inv TY]) - (SUM(fact_connected_inventory[Corp_Inv_Units_LY]) + SUM(fact_connected_inventory[Retail_Inv_Units_LY]))",
                "Total inventory change YoY in units.", folder="Inventory Health"),
        measure("R8 POS TY", "SUM(fact_connected_inventory[R8_POS_TY])",
                "Rolling 8-week POS units this year.", folder="Sales Velocity"),
        measure("R8 POS LY", "SUM(fact_connected_inventory[R8_POS_LY])",
                "Rolling 8-week POS units last year.", folder="Sales Velocity"),
        measure("R8 POS YoY %", "DIVIDE([R8 POS TY] - [R8 POS LY], [R8 POS LY])",
                "R8 POS YoY % - 8-week sales-velocity momentum.", fmt="0.0%", folder="Sales Velocity"),
        measure("Avg Lost Sales %", "DIVIDE(AVERAGE(fact_connected_inventory[YTD_Lost_Sales_Pct]), 100)",
                "Average Lost Sales % - share of demand unfilled because of stockouts. Returns a decimal so 0.0% formatting renders correctly.",
                fmt="0.0%", folder="Execution"),
        measure("Avg Vendor Fill Rate %", "DIVIDE(AVERAGE(fact_connected_inventory[Vendor_Fill_Rate_Pct]), 100)",
                "Average Vendor Fill Rate % - share of vendor PO units delivered as ordered.",
                fmt="0.0%", folder="Execution"),
        measure("# SKUs Lost Sales >5%",
                "COUNTROWS(FILTER(VALUES(dim_sku[SKU]), CALCULATE(MAX(fact_connected_inventory[YTD_Lost_Sales_Pct])) > 5))",
                "SKUs with elevated lost-sales (>5%).", folder="Execution"),
        measure("# SKUs Fill Rate <85%",
                "COUNTROWS(FILTER(VALUES(dim_sku[SKU]), CALCULATE(MAX(fact_connected_inventory[Vendor_Fill_Rate_Pct])) < 85))",
                "SKUs supplied by vendors with fill rate below 85% - supply-risk SKUs.", folder="Execution"),
        measure("Ship Units TY (Conn)", "SUM(fact_connected_inventory[Ship_Units_TY])",
                "Shipment units this year (Connected Inventory view).", folder="Inventory Health"),
        measure("DDF Units", "SUM(fact_connected_inventory[DDF_Units])",
                "Distribution-driven fill units.", folder="Inventory Health"),
    ]
    return table_header("fact_connected_inventory") + "\n".join(cols) + "\n" + "".join(measures) + partition("fact_connected_inventory", EXPR_NAME)


# ---- RELATIONSHIPS / MODEL --------------------------------------------------

RELATIONSHIPS = [
    ("fact_sku_performance.SKU",      "dim_sku.SKU",          True),
    ("fact_in_season.SKU",            "dim_sku.SKU",          True),
    ("fact_connected_inventory.SKU",  "dim_sku.SKU",          True),
    ("fact_in_season.Season",         "dim_season.Season_Code", True),
    ("dim_sku.Vendor",                "dim_vendor.Vendor",    True),
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
    tables = ["dim_date", "dim_season", "dim_sku", "dim_vendor",
              "fact_sku_performance", "fact_in_season", "fact_connected_inventory"]
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
    """Customer's question set seeded directly into the model."""
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/copilot/examplePrompts/1.0.0/schema.json",
        "prompts": [
            "Create a summary of POS, RVS, and EGM for the Kitchen & Small Appliances category across QTD, YTD, and R12.",
            "Show the top 10 SKUs by EGM dollars and include YoY change and margin %.",
            "Compare YoY performance for Air Fryers vs Cookware Sets - include POS, RVS, and EGM %.",
            "Find SKUs with high weeks of supply (>18) but low lost sales (<2%). Include inventory levels and fill rate.",
            "Which SKUs have high lost sales (>5%) and low vendor fill rate (<85%)? Include sales and inventory context.",
            "Show the bottom 5 SKUs by YoY POS decline. Include EGM %, weeks of supply, fill rate, and lost sales %.",
            "Which new SKUs are driving growth and do they have supply constraints (low fill rate or high lost sales)?",
            "Summarize overall business performance for Canvas Outdoor including POS, RVS, EGM, inventory levels, fill rate, and lost sales %. Identify key drivers, risks, and recommended actions.",
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
                 "description": "Canadian Tire Merch Copilot demo - SKU performance, in-season demand vs supply, connected inventory"},
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
        "definition/tables/dim_sku.tmdl":             b64_str(tmdl_dim_sku()),
        "definition/tables/dim_vendor.tmdl":          b64_str(tmdl_dim_vendor()),
        "definition/tables/dim_season.tmdl":          b64_str(tmdl_dim_season()),
        "definition/tables/fact_sku_performance.tmdl":     b64_str(tmdl_fact_sku_performance()),
        "definition/tables/fact_in_season.tmdl":           b64_str(tmdl_fact_in_season()),
        "definition/tables/fact_connected_inventory.tmdl": b64_str(tmdl_fact_connected_inventory()),
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
            "description": "Canadian Tire Merch Copilot demo dataset",
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
            (ROOT / "stack_ctc.json").write_text(json.dumps(STACK, indent=2))
            print(f"  Model id: {item['id']}")
            print(f"  Open: https://msit.powerbi.com/groups/{WS}/datasets/{item['id']}/details")
    elif s in (200, 201):
        if not existing:
            try:
                item = json.loads(b)
                STACK["model_id"] = item.get("id")
                STACK["model_name"] = MODEL_NAME
                (ROOT / "stack_ctc.json").write_text(json.dumps(STACK, indent=2))
                print(f"  Model id: {item.get('id')}")
            except Exception:
                pass
        else:
            print("  Update OK")
    else:
        print(f"  ERROR: {b[:1000]}")


if __name__ == "__main__":
    main()
