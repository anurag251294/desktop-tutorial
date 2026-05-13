"""DAX validation suite for the MLJ semantic model — JPY currency."""
import subprocess, json, urllib.request, time

def sh(cmd): return subprocess.check_output(cmd, shell=True).decode().strip()

with open(r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_ctx.json") as f:
    CTX = json.load(f)
WS = CTX["workspace_id"]; SM = CTX.get("semantic_model_id")

# Use Power BI REST executeQueries endpoint
TOKEN = sh("az account get-access-token --resource https://analysis.windows.net/powerbi/api --query accessToken -o tsv")

def dax(q):
    url = f"https://api.powerbi.com/v1.0/myorg/groups/{WS}/datasets/{SM}/executeQueries"
    body = json.dumps({"queries":[{"query": q}],"serializerSettings":{"includeNulls": False}}).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                  headers={"Authorization": f"Bearer {TOKEN}", "Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return 200, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

QUESTIONS = [
    ("Total Premium Revenue (JPY)",
     "EVALUATE ROW(\"Total Premium\", [Total Premium Revenue])"),
    ("Total Claims Amount (JPY)",
     "EVALUATE ROW(\"Total Claims\", [Total Claims Amount])"),
    ("Total Approved Claims (JPY)",
     "EVALUATE ROW(\"Total Approved\", [Total Approved Amount])"),
    ("Claims Ratio",
     "EVALUATE ROW(\"Claims Ratio\", [Claims Ratio])"),
    ("Approval Rate",
     "EVALUATE ROW(\"Approval Rate\", [Approval Rate])"),
    ("Average Processing Days",
     "EVALUATE ROW(\"Avg Days\", [Average Processing Days])"),
    ("Total AUM (JPY)",
     "EVALUATE ROW(\"Total AUM\", [Total AUM])"),
    ("Active Policy Count",
     "EVALUATE CALCULATETABLE(ROW(\"Active Policies\", [Policy Count]), dim_policy[status] = \"Active\")"),
    ("Top 5 prefectures by premium",
     "EVALUATE TOPN(5, SUMMARIZECOLUMNS(dim_customer[province], \"Premium\", [Total Premium Revenue]), [Premium], DESC)"),
    ("Top 5 advisors by AUM",
     "EVALUATE TOPN(5, SUMMARIZECOLUMNS(dim_advisor[advisor_id], dim_advisor[first_name], dim_advisor[last_name], \"AUM\", [Total AUM]), [AUM], DESC)"),
    ("Premium by product line",
     "EVALUATE SUMMARIZECOLUMNS(dim_product[product_line], \"Premium\", [Total Premium Revenue])"),
    ("Monthly premium 2025",
     "EVALUATE CALCULATETABLE(SUMMARIZECOLUMNS(dim_date[year_month], \"Premium\", [Total Premium Revenue]), dim_date[year] = 2025)"),
    ("Claims by product line",
     "EVALUATE SUMMARIZECOLUMNS(dim_product[product_line], \"Claims\", [Total Claims Amount])"),
]
passed = 0; failed = 0
for label, q in QUESTIONS:
    s, r = dax(q)
    if s == 200:
        try:
            rows = r["results"][0]["tables"][0]["rows"]
            print(f"  OK{label}: {rows[:3]}")
            passed += 1
        except Exception as e:
            print(f"  WARN{label}: result shape weird: {r}")
            failed += 1
    else:
        print(f"  FAIL{label}: HTTP {s} -- {str(r)[:200]}")
        failed += 1
print(f"\n{passed}/{len(QUESTIONS)} passed")
