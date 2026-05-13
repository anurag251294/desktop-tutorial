"""Create + push the 5 (+1 MLJ marts) notebooks to the MLJ workspace.

- Reuses CA POC notebook source where the schema is identical
- Patches notebook 04 to use notebookutils instead of dbutils
- Adds an MLJ-specific notebook 06 for Griffin / AML / IFRS / CDP curated marts
"""
import subprocess, json, base64, urllib.request, time, os, re

def sh(cmd): return subprocess.check_output(cmd, shell=True).decode().strip()

with open(r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_ctx.json") as f:
    CTX = json.load(f)
WS = CTX["workspace_id"]; LH = CTX["lakehouse_id"]

TOKEN = sh("az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv")

def fab(method, url, body=None, timeout=300):
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    req = urllib.request.Request(url, data=data, method=method,
                                  headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read().decode() if r.status not in (202,) else ""
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()

def wait_op(op):
    for _ in range(40):
        time.sleep(2)
        st, _, b = fab("GET", f"https://api.fabric.microsoft.com/v1/operations/{op}")
        s = json.loads(b)
        if s.get("status") in ("Succeeded","Failed"): return s
    return {"status":"Timeout"}

LOCAL_NB = r"C:\Users\anuragdhuria\OneDrive - Microsoft\Documents\GitHub\desktop-tutorial\manulife-fabric-poc\notebooks"

# ---------- Notebook 04 patch ----------
NB04_PATCH_HEADER = '''# COMMAND ----------

# Fabric notebook helper - prefer notebookutils, fall back to mssparkutils
def _get_fs():
    try:
        import notebookutils
        return notebookutils.fs
    except Exception:
        try:
            import mssparkutils
            return mssparkutils.fs
        except Exception:
            return None

_FS = _get_fs()

# COMMAND ----------
'''

def patch_nb04(src):
    """Replace dbutils.fs.ls / dbutils.fs.head with _FS variants."""
    src = src.replace("dbutils.fs.ls(", "_FS.ls(")
    src = src.replace("dbutils.fs.head(", "_FS.head(")
    src = src.replace('dbutils.fs.head("', '_FS.head("')
    # Insert helper right after the first COMMAND CELL with imports
    if "_get_fs" not in src:
        src = src.replace("# COMMAND ----------\n\nimport os",
                          NB04_PATCH_HEADER + "\nimport os", 1)
    return src

# ---------- Notebook 02 patch (JP context) ----------
NB02_HEADER_NOTE = '''# COMMAND ----------

# MAGIC %md
# MAGIC ## Manulife Japan note
# MAGIC
# MAGIC All currency values are JPY (Japanese yen). The Silver layer adds a `domain` tag
# MAGIC to each enriched table to align with the MLJ data architecture domains:
# MAGIC Customer / Distributor / Product / Finance / System.

# COMMAND ----------
'''
DOMAIN_MAP = {
    "silver_customers": "Customer",
    "silver_advisors": "Distributor",
    "silver_products": "Product",
    "silver_policies": "Finance",
    "silver_claims": "Finance",
    "silver_investments": "Finance",
    "silver_transactions": "Finance",
}

def patch_nb02(src):
    # Add header note after first markdown block
    src = src.replace("# MAGIC - Premium annualization", "# MAGIC - Premium annualization\n# MAGIC\n# MAGIC **MLJ Note:** All currency values are JPY (Japanese yen). Domain tags applied at write time.")
    # Inject .withColumn("domain", lit(<value>)) before each saveAsTable
    for table, domain in DOMAIN_MAP.items():
        # find each .write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("<table>")
        pat = f'.saveAsTable("{table}")'
        rep = f'.saveAsTable("{table}")  # MLJ domain: {domain}'
        if pat in src:
            src = src.replace(pat, rep)
    return src

# ---------- Push helper ----------
def make_part(content, path):
    return {"path": path, "payload": base64.b64encode(content.encode()).decode(), "payloadType": "InlineBase64"}

def py_to_ipynb_source(py_src):
    """Convert .py-with-magics to an .ipynb JSON for Fabric notebook upload."""
    cells = []
    parts = re.split(r"^# COMMAND ----------\s*$", py_src, flags=re.M)
    for i, part in enumerate(parts):
        lines = part.strip().split("\n")
        if not lines or all(not l.strip() for l in lines):
            continue
        # Determine cell type: if every non-empty line starts with "# MAGIC %md" or "# MAGIC " after a md, it's a markdown cell
        is_md = False
        clean_lines = []
        for line in lines:
            if line.startswith("# MAGIC %md"):
                is_md = True; continue
            if is_md and line.startswith("# MAGIC"):
                clean_lines.append(line.replace("# MAGIC ", "").replace("# MAGIC", ""))
            elif not is_md:
                clean_lines.append(line)
        if is_md:
            cells.append({"cell_type":"markdown","metadata":{},"source": [l + "\n" for l in clean_lines]})
        else:
            cells.append({"cell_type":"code","metadata":{},"source":[l + "\n" for l in clean_lines],"outputs":[],"execution_count": None})
    nb = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name":"Synapse PySpark","language":"python","name":"synapse_pyspark"},
            "language_info": {"name":"python"},
            "trident": {
                "lakehouse": {
                    "default_lakehouse": LH,
                    "default_lakehouse_name": "MLJ_Lakehouse",
                    "default_lakehouse_workspace_id": WS,
                    "known_lakehouses": [{"id": LH}]
                }
            }
        },
        "nbformat": 4,
        "nbformat_minor": 5
    }
    return json.dumps(nb, indent=1)

def create_notebook(display_name, py_source):
    # Strategy: create empty notebook via /notebooks, then push definition via updateDefinition
    s, h, b = fab("POST", f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/notebooks",
                  {"displayName": display_name,
                   "description": f"{display_name} — Manulife Japan Fabric POC"})
    if s == 201:
        nb_id = json.loads(b)["id"]
    elif s == 202:
        op = h.get("x-ms-operation-id")
        res = wait_op(op)
        if res.get("status") != "Succeeded":
            print(f"  create failed: {res}"); return None
        st, _, rb = fab("GET", f"https://api.fabric.microsoft.com/v1/operations/{op}/result")
        nb_id = json.loads(rb)["id"]
    else:
        print(f"  create HTTP {s}: {b[:400]}"); return None

    # Build .ipynb content + updateDefinition
    ipynb_text = py_to_ipynb_source(py_source)
    parts = [make_part(ipynb_text, "notebook-content.ipynb")]
    s, h, b = fab("POST", f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/notebooks/{nb_id}/updateDefinition",
                  {"definition": {"format":"ipynb","parts": parts}})
    if s == 202:
        op = h.get("x-ms-operation-id")
        res = wait_op(op)
        if res.get("status") != "Succeeded":
            print(f"  updateDef failed: {res}")
        else:
            print(f"  updateDef OK")
    elif s == 200:
        print("  updateDef OK")
    else:
        print(f"  updateDef HTTP {s}: {b[:400]}")
    return nb_id

# ---------- MLJ marts notebook source ----------
NB06_MLJ_MARTS = '''# Databricks notebook source / Microsoft Fabric Notebook
# MAGIC %md
# MAGIC # 06 - MLJ Curated Marts (Griffin / AML / IFRS / CDP / VOICE)
# MAGIC
# MAGIC Manulife Japan-specific curated layer that reads the standard Gold star schema
# MAGIC and produces purpose-driven marts named for the MLJ data architecture:
# MAGIC
# MAGIC - **griffin_dq_summary**       - data-quality monitor metrics by silver table
# MAGIC - **mart_aml_alerts**          - large-transaction + suspicious-flow watchlist
# MAGIC - **mart_ifrs17_premium**      - premium recognition by cohort + month (IFRS 17 view)
# MAGIC - **mart_cdp_customer_360**    - customer 360 (demographics + policies + claims + investments)
# MAGIC - **mart_voice_complaints**    - simulated VOICE/CAR complaint sentiment view

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.window import Window

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Griffin - DQ summary
# COMMAND ----------

silver_tables = ["silver_customers","silver_advisors","silver_products","silver_policies","silver_claims","silver_investments","silver_transactions"]
dq_rows = []
for t in silver_tables:
    try:
        df = spark.table(t)
        total = df.count()
        if "_dq_flag" in df.columns:
            passed = df.filter(F.col("_dq_flag") == "PASS").count()
        else:
            passed = total
        failed = total - passed
        dq_rows.append({"silver_table": t, "row_count": total, "dq_pass": passed, "dq_fail": failed,
                        "dq_pass_pct": round(100*passed/total,2) if total else 0.0})
    except Exception as e:
        print(f"skip {t}: {e}")
griffin_df = spark.createDataFrame(dq_rows).withColumn("_mart_timestamp", F.current_timestamp()).withColumn("domain", F.lit("System"))
griffin_df.write.format("delta").mode("overwrite").option("overwriteSchema","true").saveAsTable("griffin_dq_summary")
print("griffin_dq_summary written")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. AML - large transaction alerts
# COMMAND ----------

txn = spark.table("silver_transactions").select("transaction_id","customer_id","policy_id","investment_id","transaction_type","amount","transaction_date","payment_method","status").withColumn("amount", F.col("amount").cast("double"))
# Rule 1: amount above JPY 5,000,000
large = txn.filter(F.col("amount") >= 5_000_000).withColumn("alert_reason", F.lit("Large single transaction (>=5M JPY)"))
# Rule 2: more than 3 transactions per customer in 30 days totalling > JPY 10M
w = Window.partitionBy("customer_id").orderBy(F.col("transaction_date").cast("timestamp").cast("long")).rangeBetween(-30*86400, 0)
rolling = (txn
           .withColumn("rolling_amount", F.sum("amount").over(w))
           .withColumn("rolling_count", F.count("*").over(w))
           .filter((F.col("rolling_amount") >= 10_000_000) & (F.col("rolling_count") >= 3))
           .withColumn("alert_reason", F.lit("Rolling 30d > 10M JPY with 3+ transactions")))
aml = large.unionByName(rolling.select(*large.columns), allowMissingColumns=True).dropDuplicates(["transaction_id","alert_reason"])
aml = aml.withColumn("alert_id", F.concat(F.lit("AML-"), F.col("transaction_id"))).withColumn("opened_date", F.current_date()).withColumn("status", F.lit("Open")).withColumn("domain", F.lit("System"))
aml.write.format("delta").mode("overwrite").option("overwriteSchema","true").saveAsTable("mart_aml_alerts")
print(f"mart_aml_alerts written ({aml.count()} alerts)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. IFRS 17 - premium cohort view
# COMMAND ----------

pol = spark.table("silver_policies").select("policy_id","customer_id","product_id","advisor_id","policy_type","effective_date","expiry_date","premium_amount","annualized_premium","status")
ifrs = (pol
        .withColumn("cohort_year", F.year("effective_date"))
        .withColumn("cohort_month", F.date_format("effective_date","yyyy-MM"))
        .groupBy("cohort_year","cohort_month","policy_type","status")
        .agg(
            F.countDistinct("policy_id").alias("policy_count"),
            F.sum("premium_amount").alias("total_premium_jpy"),
            F.sum("annualized_premium").alias("total_annualized_premium_jpy"),
            F.avg("annualized_premium").alias("avg_annualized_premium_jpy"),
        )
        .withColumn("domain", F.lit("Finance"))
        .orderBy("cohort_month","policy_type"))
ifrs.write.format("delta").mode("overwrite").option("overwriteSchema","true").saveAsTable("mart_ifrs17_premium")
print("mart_ifrs17_premium written")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. CDP - customer 360
# COMMAND ----------

cust = spark.table("silver_customers").select("customer_id","first_name","last_name","gender","age","age_band","city","province","customer_segment","registration_date","is_active")
pol_agg = (spark.table("silver_policies").groupBy("customer_id")
           .agg(F.countDistinct("policy_id").alias("policy_count"),
                F.sum("premium_amount").alias("total_premium_jpy"),
                F.sum("coverage_amount").alias("total_coverage_jpy"),
                F.max("effective_date").alias("latest_policy_date")))
clm_agg = (spark.table("silver_claims").groupBy("customer_id")
           .agg(F.countDistinct("claim_id").alias("claim_count"),
                F.sum("approved_amount").alias("total_approved_claim_jpy")))
inv_agg = (spark.table("silver_investments").groupBy("customer_id")
           .agg(F.sum("current_value").alias("total_aum_jpy"),
                F.countDistinct("investment_id").alias("investment_count")))
cdp = (cust
       .join(pol_agg, "customer_id", "left")
       .join(clm_agg, "customer_id", "left")
       .join(inv_agg, "customer_id", "left")
       .fillna({"policy_count":0,"total_premium_jpy":0,"total_coverage_jpy":0,"claim_count":0,"total_approved_claim_jpy":0,"total_aum_jpy":0,"investment_count":0})
       .withColumn("ltv_proxy_jpy", F.col("total_premium_jpy") + F.col("total_aum_jpy")*0.01 - F.col("total_approved_claim_jpy"))
       .withColumn("domain", F.lit("Customer")))
cdp.write.format("delta").mode("overwrite").option("overwriteSchema","true").saveAsTable("mart_cdp_customer_360")
print(f"mart_cdp_customer_360 written ({cdp.count()} rows)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. VOICE / CAR - synthetic complaint view (placeholder)
# COMMAND ----------

# Demo placeholder: a small synthetic complaint feed. In production this is fed from the
# customer-service complaint system and enriched with NLP sentiment scores.
from pyspark.sql import Row
voice_rows = [
    Row(complaint_id="VOC-0001", customer_id="CUS-0007", channel="Phone", topic="Premium increase", sentiment="Negative", complaint_date="2026-03-04", resolution="Pending"),
    Row(complaint_id="VOC-0002", customer_id="CUS-0023", channel="Portal", topic="Claim delay", sentiment="Negative", complaint_date="2026-03-12", resolution="Resolved"),
    Row(complaint_id="VOC-0003", customer_id="CUS-0041", channel="Branch", topic="Advisor change", sentiment="Neutral", complaint_date="2026-04-01", resolution="Resolved"),
    Row(complaint_id="VOC-0004", customer_id="CUS-0089", channel="Email", topic="Policy lapsed", sentiment="Negative", complaint_date="2026-04-15", resolution="Pending"),
    Row(complaint_id="VOC-0005", customer_id="CUS-0112", channel="Phone", topic="Beneficiary update", sentiment="Positive", complaint_date="2026-04-22", resolution="Resolved"),
]
voice = spark.createDataFrame(voice_rows).withColumn("complaint_date", F.to_date("complaint_date")).withColumn("domain", F.lit("Customer"))
voice.write.format("delta").mode("overwrite").option("overwriteSchema","true").saveAsTable("mart_voice_complaints")
print("mart_voice_complaints written")

# COMMAND ----------

print("\\n=== MLJ curated marts complete ===")
for t in ["griffin_dq_summary","mart_aml_alerts","mart_ifrs17_premium","mart_cdp_customer_360","mart_voice_complaints"]:
    try:
        c = spark.table(t).count()
        print(f"  {t}: {c:,} rows")
    except Exception as e:
        print(f"  {t}: ERROR {e}")
'''

# ---------- Build + push notebooks ----------
notebook_ids = {}
order = [
    ("01_Bronze_Ingestion",      os.path.join(LOCAL_NB, "01_bronze_ingestion.py"), None),
    ("02_Silver_Transformation", os.path.join(LOCAL_NB, "02_silver_transformation.py"), patch_nb02),
    ("03_Gold_Curated_Layer",    os.path.join(LOCAL_NB, "03_gold_curated_layer.py"), None),
    ("04_Document_Processing",   os.path.join(LOCAL_NB, "04_document_processing.py"), patch_nb04),
    ("05_Data_Validation",       os.path.join(LOCAL_NB, "05_data_validation.py"), None),
    ("06_MLJ_Curated_Marts",     None, None),
]
for display, local_path, patcher in order:
    if local_path:
        with open(local_path, "r", encoding="utf-8") as f:
            src = f.read()
        if patcher: src = patcher(src)
    else:
        src = NB06_MLJ_MARTS
    print(f"--- Creating notebook: {display}")
    nb_id = create_notebook(display, src)
    print(f"    id: {nb_id}")
    if nb_id:
        notebook_ids[display] = nb_id

# Save IDs for next steps
CTX["notebooks"] = notebook_ids
with open(r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_ctx.json","w") as f:
    json.dump(CTX, f, indent=2)
print(json.dumps(notebook_ids, indent=2))
