"""Patch the MLJ Data Agent:
1. Add a richer description
2. Add dataSourceInstructions for both lakehouse and semantic model
3. Copy draft -> published so the patches go live
"""
import subprocess, json, base64, urllib.request, time, sys, io
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def sh(c): return subprocess.check_output(c, shell=True).decode().strip()

with open(r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_ctx.json") as f:
    C = json.load(f)
WS = C["workspace_id"]
DA = "f766cc67-3f10-4f73-a774-0c2036c75bc1"

TOKEN = sh("az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv")

def fab(method, url, body=None, timeout=180):
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    req = urllib.request.Request(url, data=data, method=method,
                                  headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            hdrs = {k.lower(): v for k, v in r.headers.items()}
            return r.status, hdrs, r.read().decode() if r.status != 202 else ""
    except urllib.error.HTTPError as e:
        hdrs = {k.lower(): v for k, v in (e.headers.items() if e.headers else [])}
        return e.code, hdrs, e.read().decode()

def wait_op(op):
    for _ in range(40):
        time.sleep(2)
        _, _, b = fab("GET", f"https://api.fabric.microsoft.com/v1/operations/{op}")
        s = json.loads(b)
        if s.get("status") in ("Succeeded","Failed"): return s
    return {"status":"Timeout"}

LH_INSTR = """When using the lakehouse for MLJ:

- ALWAYS prefer gold_* tables for star-schema queries (gold_dim_customer, gold_dim_product, gold_dim_advisor, gold_dim_policy, gold_dim_date, gold_dim_fund, gold_fact_claims, gold_fact_investments, gold_fact_policy_premiums, gold_fact_transactions).
- For MLJ-specific marts:
  - griffin_dq_summary - silver-table DQ pass/fail counts (System domain).
  - mart_aml_alerts - AML watchlist rows; columns: transaction_id, customer_id, amount, alert_reason, opened_date, status.
  - mart_ifrs17_premium - premium by cohort_year/cohort_month/policy_type (Finance).
  - mart_cdp_customer_360 - customer 360 with policy_count, claim_count, total_aum_jpy, ltv_proxy_jpy.
  - mart_voice_complaints - synthetic complaint feed (small).
- For document/policy questions use document_chunks; filter by document_name then text LIKE on chunk_text. Return document_name, section_header, chunk_text.
- All currency columns are JPY (yen) - no decimals; display with the yen sign and thousands separators.
- Date columns are DATE/TIMESTAMP.
- The province column on dim_customer holds the Japanese prefecture name.
- Skip validation_results (DQ output, not for end-users).
"""

SM_INSTR = """When using the semantic model for MLJ:

- Prefer DAX measures over raw column aggregation.
- All currency measures return JPY. Display as the yen sign + thousands separators + no decimals.
- Use SUMMARIZECOLUMNS for grouped queries with measures.
- Date relationships are live (fact tables -> dim_date via effective_date / claim_date / transaction_date / inception_date). Slice by dim_date[year_month], dim_date[year_quarter], dim_date[fiscal_year].
- Relationships from dim_product and dim_advisor are direct to fact_policy_premiums and fact_investments, but NOT to fact_claims. For 'claims by product' use a lakehouse SQL join via dim_policy.
- For approval rate or claims ratio, the measure already handles the math; do not recompute.
- For prefecture breakdowns, group by dim_customer[province].
"""

DESCRIPTION = ("Manulife Japan POC Data Agent - natural-language analytics over the MLJ insurance, "
               "investment, and document corpus (JPY). Grounded on the ManulifeJapanPOC semantic model, "
               "the MLJ_Lakehouse gold + curated marts (Griffin / AML / IFRS 17 / CDP / VOICE), and the "
               "document_chunks RAG table (8 JP policy and guideline documents).")

# 1) PATCH item description
print("== Updating description ==")
s, h, b = fab("PATCH", f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/items/{DA}",
              {"displayName": "da_manulife_japan_poc", "description": DESCRIPTION})
print(f"  HTTP {s}")

# 2) Fetch current definition
print("\n== Fetching current definition ==")
s, h, _ = fab("POST", f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/items/{DA}/getDefinition")
op = h.get("x-ms-operation-id")
res = wait_op(op)
if res.get("status") != "Succeeded":
    print(f"  getDef failed: {res}"); sys.exit(1)
_, _, body = fab("GET", f"https://api.fabric.microsoft.com/v1/operations/{op}/result")
defn = json.loads(body)
parts = defn["definition"]["parts"]
print(f"  parts: {len(parts)}")

# 3) Modify lakehouse + semantic model datasource.json, both draft and published
new_parts = []
for p in parts:
    path = p["path"]
    payload_text = base64.b64decode(p["payload"]).decode("utf-8", errors="replace")
    modified = False
    if "lakehouse-tables-MLJ_Lakehouse/datasource.json" in path:
        obj = json.loads(payload_text)
        obj["dataSourceInstructions"] = LH_INSTR
        payload_text = json.dumps(obj, indent=2)
        modified = True
    elif "semantic-model-ManulifeJapanPOC_SemanticModel/datasource.json" in path:
        obj = json.loads(payload_text)
        obj["dataSourceInstructions"] = SM_INSTR
        payload_text = json.dumps(obj, indent=2)
        modified = True
    elif "publish_info.json" in path:
        obj = json.loads(payload_text)
        obj["description"] = "Published Manulife Japan POC Data Agent. Grounded on ManulifeJapanPOC semantic model, MLJ_Lakehouse gold + curated marts, and document_chunks (8 JP docs)."
        payload_text = json.dumps(obj, indent=2)
        modified = True
    if modified:
        print(f"  patched: {path}")
    new_parts.append({
        "path": path,
        "payload": base64.b64encode(payload_text.encode("utf-8")).decode("ascii"),
        "payloadType": "InlineBase64"
    })

# 4) Push back
print("\n== updateDefinition ==")
s, h, b = fab("POST", f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/items/{DA}/updateDefinition",
              {"definition": {"parts": new_parts}})
print(f"  HTTP {s}")
if s == 202:
    op = h.get("x-ms-operation-id")
    res = wait_op(op)
    print(f"  status: {res.get('status')}")

print("\n== Verifying ==")
s, h, _ = fab("POST", f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/items/{DA}/getDefinition")
op = h.get("x-ms-operation-id"); wait_op(op)
_, _, body = fab("GET", f"https://api.fabric.microsoft.com/v1/operations/{op}/result")
parts = json.loads(body)["definition"]["parts"]
for p in parts:
    path = p["path"]
    if "datasource.json" in path and "published" in path:
        obj = json.loads(base64.b64decode(p["payload"]).decode("utf-8", errors="replace"))
        dsi = obj.get("dataSourceInstructions","")
        kind = "lakehouse" if "lakehouse" in path else "semantic model"
        print(f"  {kind} dataSourceInstructions: {len(dsi)} chars")
print("\n== DONE ==")
