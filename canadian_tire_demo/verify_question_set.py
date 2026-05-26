"""Run the Copilot question-set prompts through DAX to confirm the model
can answer each one cleanly. These are the same prompts the customer
prepared - Copilot in PBI will ask the model the same shape of questions.
"""
import json, subprocess, urllib.request, urllib.error
from pathlib import Path

STACK = json.loads((Path(__file__).parent / "stack_ctc.json").read_text())
WS = STACK["workspace_id"]
MODEL = STACK["model_id"]
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"

tok = subprocess.check_output(
    [AZ, "account", "get-access-token",
     "--resource", "https://analysis.windows.net/powerbi/api",
     "--query", "accessToken", "-o", "tsv"]).decode().strip()
url = f"https://api.powerbi.com/v1.0/myorg/groups/{WS}/datasets/{MODEL}/executeQueries"
h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def q(query, label):
    body = json.dumps({"queries": [{"query": query}]}).encode()
    req = urllib.request.Request(url, headers=h, method="POST", data=body)
    print(f"\n=== {label} ===")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
            rows = d["results"][0]["tables"][0]["rows"]
            for row in rows[:10]:
                print(f"  {row}")
            if len(rows) > 10:
                print(f"  ... ({len(rows)} total)")
    except urllib.error.HTTPError as e:
        print(f"  ERR {e.code}: {e.read().decode()[:300]}")


# Q1: "Summary of POS, RVS, EGM for Kitchen & Small Appliances across QTD, YTD, R12"
q("""EVALUATE
CALCULATETABLE(
  ROW(
    "POS_QTD", [POS $ QTD],
    "POS_YTD", [POS $ YTD],
    "POS_R12", [POS $ R12],
    "RVS_TY",  [RVS TY],
    "EGM_$_TY", [EGM $ TY],
    "EGM_%_TY", [EGM % TY]
  ),
  dim_sku[Category] = "Kitchen & Small Appliances"
)""", "Q1a: Kitchen & Small Appliances summary across timeframes")

# Q1b: Top 10 SKUs by EGM
q("""EVALUATE
TOPN(10,
  SUMMARIZECOLUMNS(dim_sku[SKU], dim_sku[SKU_Name],
    "EGM_TY", [EGM $ TY], "POS_YoY_%", [POS YoY %], "EGM_%", [EGM % TY]),
  [EGM_TY], DESC)""", "Q1b: Top 10 SKUs by EGM with YoY and margin %")

# Q1c: Air Fryers vs Cookware
q("""EVALUATE
FILTER(SUMMARIZECOLUMNS(dim_sku[Fineline_Name],
    "POS_TY", [POS $ TY], "POS_LY", [POS $ LY],
    "RVS_TY", [RVS TY], "EGM_%_TY", [EGM % TY], "POS_YoY_%", [POS YoY %]),
  dim_sku[Fineline_Name] IN {"Air Fryers", "Cookware Sets"})""",
  "Q1c: Air Fryers vs Cookware YoY comparison")

# Q2a: WoS>18 AND Lost Sales<2%
q("""EVALUATE
FILTER(
  SUMMARIZECOLUMNS(dim_sku[SKU], dim_sku[SKU_Name],
    "WoS", [Avg Weeks of Supply],
    "Lost_Sales_%", [Avg Lost Sales %],
    "Retail_Inv", [Retail Inv TY],
    "Corp_Inv", [Corp Inv TY],
    "Fill_Rate_%", [Avg Vendor Fill Rate %]),
  [WoS] > 18 && [Lost_Sales_%] < 0.02)""",
  "Q2a: SKUs with high WoS (>18) but low lost sales (<2%)")

# Q2b: Lost Sales>5% AND Fill Rate<85%
q("""EVALUATE
FILTER(
  SUMMARIZECOLUMNS(dim_sku[SKU], dim_sku[SKU_Name], dim_sku[Vendor],
    "Lost_Sales_%", [Avg Lost Sales %],
    "Fill_Rate_%", [Avg Vendor Fill Rate %],
    "POS_TY", [POS $ TY],
    "Total_Inv", [Total Inv TY]),
  [Lost_Sales_%] > 0.05 && [Fill_Rate_%] < 0.85)""",
  "Q2b: SKUs with lost sales >5% AND fill rate <85%")

# Q3a: Bottom 5 by YoY POS decline
q("""EVALUATE
TOPN(5,
  SUMMARIZECOLUMNS(dim_sku[SKU], dim_sku[SKU_Name],
    "POS_YoY_%", [POS YoY %],
    "EGM_%", [EGM % TY],
    "WoS", [Avg Weeks of Supply],
    "Fill_Rate_%", [Avg Vendor Fill Rate %],
    "Lost_Sales_%", [Avg Lost Sales %]),
  [POS_YoY_%], ASC)""",
  "Q3a: Bottom 5 SKUs by YoY POS decline")

# Q3b: New SKUs driving growth with supply constraints
q("""EVALUATE
CALCULATETABLE(
  SUMMARIZECOLUMNS(dim_sku[SKU], dim_sku[SKU_Name], dim_sku[Fineline_Name],
    "POS_YoY_%", [POS YoY %],
    "Fill_Rate_%", [Avg Vendor Fill Rate %],
    "Lost_Sales_%", [Avg Lost Sales %],
    "WoS", [Avg Weeks of Supply]),
  dim_sku[New_SKU_Flag] = "Y")""",
  "Q3b: New SKUs - POS growth and supply context")

# Q3c: Canvas Outdoor exec summary
q("""EVALUATE
CALCULATETABLE(
  ROW(
    "POS_$_TY",     [POS $ TY],
    "POS_$_LY",     [POS $ LY],
    "POS_YoY_%",    [POS YoY %],
    "RVS_TY",       [RVS TY],
    "EGM_$_TY",     [EGM $ TY],
    "EGM_%_TY",     [EGM % TY],
    "Total_Inv",    [Total Inv TY],
    "Lost_Sales_%", [Avg Lost Sales %],
    "Fill_Rate_%",  [Avg Vendor Fill Rate %]
  ),
  dim_sku[Vendor] = "Canvas Outdoor")""",
  "Q3c: Canvas Outdoor (vendor) executive summary")
