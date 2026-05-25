"""Full measure verification across all 3 fact tables."""
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


def q(query):
    body = json.dumps({"queries": [{"query": query}]}).encode()
    req = urllib.request.Request(url, headers=h, method="POST", data=body)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
            return d["results"][0]["tables"][0]["rows"]
    except urllib.error.HTTPError as e:
        return [{"ERR": e.read().decode()[:300]}]


print("== Sales / Profitability ==")
for row in q("EVALUATE ROW(\"POS TY\", [POS $ TY], \"POS LY\", [POS $ LY], \"YoY %\", [POS YoY %], \"RVS TY\", [RVS TY], \"EGM TY\", [EGM $ TY], \"EGM %\", [EGM % TY])"):
    print(f"  {row}")

print("\n== Counts ==")
for row in q("EVALUATE ROW(\"# SKUs\", [# SKUs], \"# Active\", [# Active SKUs], \"# New\", [# New SKUs])"):
    print(f"  {row}")

print("\n== Execution ==")
for row in q("EVALUATE ROW(\"Lost Sales %\", [Avg Lost Sales %], \"Fill Rate %\", [Avg Vendor Fill Rate %], \"R8 YoY %\", [R8 POS YoY %])"):
    print(f"  {row}")

print("\n== WoS ==")
for row in q("EVALUATE ROW(\"Avg WoS\", [Avg Weeks of Supply], \"Over18\", [# SKUs Overstock (WoS>18)], \"Under4\", [# SKUs Understock (WoS<4)])"):
    print(f"  {row}")

print("\n== Top 5 categories by EGM TY ==")
for row in q("EVALUATE TOPN(5, SUMMARIZECOLUMNS(dim_sku[Category], \"EGM\", [EGM $ TY], \"POS\", [POS $ TY]), [EGM], DESC)"):
    print(f"  {row}")

print("\n== Top 5 finelines by POS YoY % (sorted desc) ==")
for row in q("EVALUATE TOPN(5, SUMMARIZECOLUMNS(dim_sku[Fineline_Name], \"YoY\", [POS YoY %], \"POS\", [POS $ TY]), [YoY], DESC)"):
    print(f"  {row}")

print("\n== Air Fryers vs Cookware Sets (from question set) ==")
for row in q("""EVALUATE
FILTER(
  SUMMARIZECOLUMNS(dim_sku[Fineline_Name],
    "POS TY", [POS $ TY], "RVS TY", [RVS TY], "EGM %", [EGM % TY]),
  dim_sku[Fineline_Name] IN {"Air Fryers", "Cookware Sets"}
)"""):
    print(f"  {row}")
