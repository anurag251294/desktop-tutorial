"""Run a couple of DAX queries against the InteracHR_Model to verify measures.

Uses the Power BI DAX execute endpoint:
  POST /v1.0/myorg/groups/{ws}/datasets/{model}/executeQueries
"""
import json
import subprocess
import urllib.request
import urllib.error
import uuid

WORKSPACE_ID = "2690ef29-1370-476c-b28c-58a505fea2bd"
MODEL_ID = "00bb5cc7-20c0-4030-ae35-25a2ec02bc87"
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"


def token() -> str:
    return subprocess.check_output(
        [AZ, "account", "get-access-token",
         "--resource", "https://analysis.windows.net/powerbi/api",
         "--query", "accessToken", "-o", "tsv"]
    ).decode().strip()


def run_dax(query: str):
    url = (f"https://api.powerbi.com/v1.0/myorg/groups/{WORKSPACE_ID}"
           f"/datasets/{MODEL_ID}/executeQueries")
    body = {
        "queries": [{"query": query}],
        "serializerSettings": {"includeNulls": True},
    }
    headers = {"Authorization": f"Bearer {token()}",
               "Content-Type": "application/json",
               "ActivityId": str(uuid.uuid4())}
    req = urllib.request.Request(url, headers=headers, method="POST",
                                 data=json.dumps(body).encode())
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


QUERIES = [
    ("Active Employees",  "EVALUATE ROW(\"v\", [Active Employees])"),
    ("Tech Employees",    "EVALUATE ROW(\"v\", [Tech Employees])"),
    ("% Tech",            "EVALUATE ROW(\"v\", [% Tech])"),
    ("% Female",          "EVALUATE ROW(\"v\", [% Female])"),
    ("% Female (Tech)",   "EVALUATE ROW(\"v\", [% Female (Tech)])"),
    ("Terminations LTM",  "EVALUATE ROW(\"v\", [Terminations LTM])"),
    ("Attrition Rate LTM","EVALUATE ROW(\"v\", [Attrition Rate LTM])"),
    ("% Regrettable LTM", "EVALUATE ROW(\"v\", [% Regrettable LTM])"),
    ("Open Reqs",         "EVALUATE ROW(\"v\", [Open Reqs])"),
    ("Hires LTM",         "EVALUATE ROW(\"v\", [Hires LTM])"),
    ("Avg Base Salary",   "EVALUATE ROW(\"v\", [Avg Base Salary])"),
    ("Comp Ratio vs Market", "EVALUATE ROW(\"v\", [Comp Ratio vs Market])"),
    ("FINTRAC Training %","EVALUATE ROW(\"v\", [FINTRAC Training Completion %])"),
    ("COI Overdue 90+",   "EVALUATE ROW(\"v\", [COI Overdue 90+ Days])"),
]

print(f"{'Measure':<30s} {'Status':<6s} Result")
print("-" * 70)
for name, q in QUERIES:
    s, b = run_dax(q)
    if s == 200:
        try:
            data = json.loads(b)
            val = list(data["results"][0]["tables"][0]["rows"][0].values())[0]
            if isinstance(val, float):
                if abs(val) < 1 and val != 0:
                    val_str = f"{val:.4f}"
                else:
                    val_str = f"{val:,.2f}"
            else:
                val_str = str(val)
        except Exception as e:
            val_str = f"parse err: {e} | {b[:150]}"
        print(f"{name:<30s} {s:<6d} {val_str}")
    else:
        # Truncate error
        try:
            err = json.loads(b)
            msg = err.get("error", {}).get("pbi.error", {}).get("details", [{}])[0].get("detail", {}).get("value", "")
            if not msg:
                msg = err.get("error", {}).get("message", b[:150])
        except Exception:
            msg = b[:150]
        print(f"{name:<30s} {s:<6d} {msg[:200]}")
