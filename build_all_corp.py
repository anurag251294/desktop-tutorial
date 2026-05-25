"""Orchestrate the full Interac demo stack rebuild on a Fabric trial capacity.

Runs end-to-end in one shot:
  1. Create workspace on the trial capacity
  2. Create lakehouse (and get its SQL endpoint URL)
  3. Upload all CSVs to OneLake via DFS PATCH
  4. Load each CSV into a Delta table via Lakehouse Load API
  5. Create semantic model from TMDL we already captured, substituting the
     new lakehouse's SQL endpoint into the DatabaseQuery expression
  6. Push 19 relationships + 22 measures via updateDefinition
  7. Push 3 RLS roles via updateDefinition
  8. Create starter report with 4 KPI cards

All IDs land in stack_corp.json at the end so other scripts can read them.
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path

ROOT = Path(__file__).parent
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"

# Newest trial capacity in corp tenant
TRIAL_CAPACITY_ID = "<filled in at runtime>"
TRIAL_CAPACITY_NAME_PREFIX = "Trial-20260525"


def tok(resource="https://api.fabric.microsoft.com"):
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"]).decode().strip()


def call(method, url, body=None, resource=None, extra=None):
    headers = {"Authorization": f"Bearer {tok(resource or API)}",
               "ActivityId": str(uuid.uuid4()),
               "Content-Type": "application/json"}
    if extra:
        headers.update(extra)
    data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
    req = urllib.request.Request(url, headers=headers, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def poll(loc, timeout_polls=60):
    for i in range(timeout_polls):
        time.sleep(2)
        s, h, b = call("GET", loc)
        try:
            op = json.loads(b)
            st = op.get("status")
        except Exception:
            st = None
        if st == "Succeeded":
            return True, loc.rstrip("/") + "/result"
        if st == "Failed":
            print(f"   FAILED: {b[:500]}")
            return False, None
    print(f"   TIMEOUT after {timeout_polls*2}s")
    return False, None


# ============== Step 1: Workspace ==============

def step_workspace(capacity_id):
    print("\n[1/8] Creating workspace InteracHRDemo...")
    s, h, b = call("POST", f"{API}/v1/workspaces",
                   body={"displayName": "InteracHRDemo",
                         "description": "Interac HR demo (corp Fabric trial)",
                         "capacityId": capacity_id})
    if s in (200, 201):
        ws = json.loads(b)
        print(f"   workspace = {ws['id']}")
        return ws["id"]
    raise RuntimeError(f"Workspace create failed: {s} {b[:300]}")


# ============== Step 2: Lakehouse ==============

def step_lakehouse(ws_id):
    print("\n[2/8] Creating lakehouse InteracHR_Lakehouse...")
    s, h, b = call("POST", f"{API}/v1/workspaces/{ws_id}/lakehouses",
                   body={"displayName": "InteracHR_Lakehouse",
                         "description": "HR data for Interac demo"})
    if s == 202:
        loc = h.get("Location") or h.get("location")
        ok, result_url = poll(loc)
        if not ok:
            raise RuntimeError("Lakehouse create failed")
        s2, h2, b2 = call("GET", result_url)
        lh = json.loads(b2)
    elif s in (200, 201):
        lh = json.loads(b)
    else:
        raise RuntimeError(f"Lakehouse create failed: {s} {b[:300]}")
    print(f"   lakehouse = {lh['id']}")
    # Get SQL endpoint - may need a moment to provision
    for attempt in range(15):
        s3, h3, b3 = call("GET", f"{API}/v1/workspaces/{ws_id}/lakehouses/{lh['id']}")
        lh_detail = json.loads(b3)
        sql = lh_detail.get("properties", {}).get("sqlEndpointProperties", {})
        if sql.get("connectionString") and sql.get("id"):
            print(f"   SQL endpoint = {sql['connectionString']}")
            print(f"   SQL endpoint id = {sql['id']}")
            return lh["id"], sql["connectionString"], sql["id"]
        time.sleep(3)
    raise RuntimeError("SQL endpoint never became ready")


# ============== Step 3: Upload CSVs ==============

def step_upload(ws_id, lh_id):
    print("\n[3/8] Uploading CSVs to OneLake...")
    data_dir = ROOT / "data"
    files = sorted(data_dir.glob("*.csv"))
    storage_tok = tok("https://storage.azure.com")
    for fp in files:
        base_url = (f"https://onelake.dfs.fabric.microsoft.com/"
                    f"{ws_id}/{lh_id}/Files/csv/{fp.name}")
        auth = {"Authorization": f"Bearer {storage_tok}"}
        data = fp.read_bytes()
        size = len(data)
        # Create
        req = urllib.request.Request(base_url + "?resource=file",
                                     headers=auth, method="PUT")
        try:
            urllib.request.urlopen(req, timeout=120).close()
        except urllib.error.HTTPError as e:
            if e.code not in (200, 201):
                print(f"   {fp.name}: CREATE {e.code} - {e.read().decode()[:120]}")
                continue
        # Append
        h_append = dict(auth)
        h_append["Content-Length"] = str(size)
        req = urllib.request.Request(base_url + "?action=append&position=0",
                                     headers=h_append, method="PATCH", data=data)
        try:
            urllib.request.urlopen(req, timeout=120).close()
        except urllib.error.HTTPError as e:
            if e.code not in (200, 202):
                print(f"   {fp.name}: APPEND {e.code}")
                continue
        # Flush
        req = urllib.request.Request(base_url + f"?action=flush&position={size}",
                                     headers=auth, method="PATCH")
        try:
            urllib.request.urlopen(req, timeout=60).close()
        except urllib.error.HTTPError as e:
            if e.code not in (200, 201):
                print(f"   {fp.name}: FLUSH {e.code}")
                continue
        print(f"   {fp.name} ({size/1024:.1f} KB)  OK")


# ============== Step 4: Load to Delta ==============

TABLES = [
    ("dim_date.csv",                 "dim_date"),
    ("dim_department.csv",           "dim_department"),
    ("dim_role.csv",                 "dim_role"),
    ("dim_location.csv",             "dim_location"),
    ("dim_employee.csv",             "dim_employee"),
    ("fact_headcount_snapshot.csv",  "fact_headcount_snapshot"),
    ("fact_attrition.csv",           "fact_attrition"),
    ("fact_compensation.csv",        "fact_compensation"),
    ("fact_recruitment.csv",         "fact_recruitment"),
    ("fact_training_completion.csv", "fact_training_completion"),
    ("fact_attestation.csv",         "fact_attestation"),
]


def step_load_delta(ws_id, lh_id):
    print("\n[4/8] Loading CSVs to Delta tables...")
    for csv_name, tname in TABLES:
        url = (f"{API}/v1/workspaces/{ws_id}/lakehouses/{lh_id}"
               f"/tables/{tname}/load")
        body = {"relativePath": f"Files/csv/{csv_name}",
                "pathType": "File", "mode": "Overwrite", "recursive": False,
                "formatOptions": {"format": "Csv", "header": True, "delimiter": ","}}
        s, h, b = call("POST", url, body=body)
        if s == 202:
            loc = h.get("Location") or h.get("location")
            ok, _ = poll(loc)
            print(f"   {tname:30s} {'OK' if ok else 'FAILED'}")
        elif s in (200, 201):
            print(f"   {tname:30s} OK (sync)")
        else:
            print(f"   {tname:30s} ERR {s}: {b[:120]}")


# ============== Step 5: Create semantic model from TMDL ==============

def step_semantic_model(ws_id, sql_endpoint_cs, sql_endpoint_id):
    print("\n[5/8] Creating semantic model from TMDL...")
    model_dir = ROOT / "model_current"
    if not model_dir.exists():
        raise RuntimeError(f"{model_dir} missing - run fetch_model_definition.py first")
    # Load all parts
    parts = {}
    for f in model_dir.iterdir():
        if f.is_file():
            path = f.name.replace("__", "/")
            parts[path] = f.read_text(encoding="utf-8")
    # Patch expressions.tmdl to point at NEW SQL endpoint
    # Original: Sql.Database("<old-cs>", "<old-catalog>")
    expr_path = "definition/expressions.tmdl"
    expr = parts[expr_path]
    expr = re.sub(
        r'Sql\.Database\("[^"]+",\s*"[^"]+"\)',
        f'Sql.Database("{sql_endpoint_cs}", "{sql_endpoint_id}")',
        expr,
    )
    parts[expr_path] = expr
    # Also patch sourceLineageTag in every table file to use the new lakehouse table source
    # (those reference [dbo].[<tablename>] which is the same in the new lakehouse, no change needed)
    # Update .platform metadata for new item
    platform_path = ".platform"
    platform = json.loads(parts[platform_path])
    platform.setdefault("metadata", {})["displayName"] = "InteracHR_Model"
    platform["metadata"]["type"] = "SemanticModel"
    platform.setdefault("config", {})["logicalId"] = str(uuid.uuid4())
    parts[platform_path] = json.dumps(platform, indent=2)

    # Build payload for Items API
    payload_parts = []
    for path, content in parts.items():
        payload_parts.append({
            "path": path,
            "payload": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "payloadType": "InlineBase64",
        })
    body = {
        "displayName": "InteracHR_Model",
        "description": "Interac HR Direct Lake semantic model",
        "type": "SemanticModel",
        "definition": {"format": "TMDL", "parts": payload_parts},
    }
    s, h, b = call("POST", f"{API}/v1/workspaces/{ws_id}/items", body=body)
    if s == 202:
        loc = h.get("Location") or h.get("location")
        ok, result_url = poll(loc)
        if not ok:
            raise RuntimeError("Model create failed")
        s2, h2, b2 = call("GET", result_url)
        m = json.loads(b2)
    elif s in (200, 201):
        m = json.loads(b)
    else:
        raise RuntimeError(f"Model create failed: {s} {b[:600]}")
    print(f"   model = {m['id']}")
    return m["id"]


# ============== Step 6: Push relationships + measures ==============

def make_relationships_tmdl():
    rels = [
        ("dim_employee.department_id", "dim_department.department_id", True),
        ("dim_employee.role_id", "dim_role.role_id", True),
        ("dim_employee.location_id", "dim_location.location_id", True),
        ("fact_headcount_snapshot.employee_id", "dim_employee.employee_id", True),
        ("fact_attrition.employee_id",          "dim_employee.employee_id", True),
        ("fact_compensation.employee_id",       "dim_employee.employee_id", True),
        ("fact_training_completion.employee_id","dim_employee.employee_id", True),
        ("fact_attestation.employee_id",        "dim_employee.employee_id", True),
        ("fact_recruitment.hired_employee_id",  "dim_employee.employee_id", False),
        ("fact_headcount_snapshot.snapshot_date", "dim_date.date", True),
        ("fact_attrition.termination_date",       "dim_date.date", True),
        ("fact_compensation.effective_date",      "dim_date.date", True),
        ("fact_recruitment.hire_date",            "dim_date.date", True),
        ("fact_recruitment.posting_date",         "dim_date.date", False),
        ("fact_training_completion.due_date",     "dim_date.date", True),
        ("fact_attestation.due_date",             "dim_date.date", True),
        ("fact_recruitment.role_id", "dim_role.role_id", True),
        ("fact_recruitment.department_id", "dim_department.department_id", True),
        ("fact_recruitment.location_id", "dim_location.location_id", True),
    ]
    lines = []
    for fr, to, active in rels:
        rid = str(uuid.uuid4())
        lines.append(f"relationship {rid}")
        if not active:
            lines.append("\tisActive: false")
        lines.append(f"\tfromColumn: {fr}")
        lines.append(f"\ttoColumn: {to}")
        lines.append("")
    return "\n".join(lines)


MEASURES = [
    ("Active Employees",
     "CALCULATE ( DISTINCTCOUNT ( fact_headcount_snapshot[employee_id] ), "
     "LASTDATE ( fact_headcount_snapshot[snapshot_date] ) )",
     "#,##0", "Headcount"),
    ("Tech Employees",
     "CALCULATE ( [Active Employees], dim_role[is_tech_role] = \"Yes\" )",
     "#,##0", "Headcount"),
    ("% Tech",
     "DIVIDE ( [Tech Employees], [Active Employees] )",
     "0.0%", "Headcount"),
    ("% Female",
     "VAR _f = CALCULATE ( [Active Employees], dim_employee[gender] = \"F\" ) "
     "RETURN DIVIDE ( _f, [Active Employees] )",
     "0.0%", "Diversity"),
    ("% Female (Tech)",
     "VAR _f = CALCULATE ( [Active Employees], dim_employee[gender] = \"F\", "
     "dim_role[is_tech_role] = \"Yes\" ) RETURN DIVIDE ( _f, [Tech Employees] )",
     "0.0%", "Diversity"),
    ("Terminations (Period)",
     "COUNTROWS ( fact_attrition )", "#,##0", "Attrition"),
    ("Terminations LTM",
     "CALCULATE ( [Terminations (Period)], "
     "DATESINPERIOD ( dim_date[date], TODAY(), -12, MONTH ) )",
     "#,##0", "Attrition"),
    ("Avg Headcount LTM",
     "VAR _snapshots = FILTER ( VALUES ( fact_headcount_snapshot[snapshot_date] ), "
     "fact_headcount_snapshot[snapshot_date] >= EDATE ( TODAY(), -12 ) "
     "&& fact_headcount_snapshot[snapshot_date] <= TODAY() ) "
     "RETURN AVERAGEX ( _snapshots, CALCULATE ( DISTINCTCOUNT ( "
     "fact_headcount_snapshot[employee_id] ) ) )",
     "#,##0", "Attrition"),
    ("Attrition Rate LTM",
     "DIVIDE ( [Terminations LTM], [Avg Headcount LTM] )",
     "0.0%", "Attrition"),
    ("Regrettable Attrition LTM",
     "CALCULATE ( [Terminations LTM], fact_attrition[regrettable] = \"Yes\" )",
     "#,##0", "Attrition"),
    ("% Regrettable LTM",
     "DIVIDE ( [Regrettable Attrition LTM], [Terminations LTM] )",
     "0.0%", "Attrition"),
    ("Voluntary Attrition LTM",
     "CALCULATE ( [Terminations LTM], fact_attrition[termination_type] = \"Voluntary\" )",
     "#,##0", "Attrition"),
    ("Open Reqs",
     "CALCULATE ( DISTINCTCOUNT ( fact_recruitment[req_id] ), "
     "fact_recruitment[status] = \"Open\" )", "#,##0", "Recruitment"),
    ("Hires LTM",
     "CALCULATE ( DISTINCTCOUNT ( fact_recruitment[req_id] ), "
     "fact_recruitment[status] = \"Filled\", "
     "USERELATIONSHIP ( fact_recruitment[hire_date], dim_date[date] ), "
     "DATESINPERIOD ( dim_date[date], TODAY(), -12, MONTH ) )",
     "#,##0", "Recruitment"),
    ("Avg Time to Fill (days)",
     "CALCULATE ( AVERAGE ( fact_recruitment[time_to_fill_days] ), "
     "fact_recruitment[status] = \"Filled\" )", "#,##0.0", "Recruitment"),
    ("Pipeline Conversion",
     "DIVIDE ( SUM ( fact_recruitment[offers_accepted] ), "
     "SUM ( fact_recruitment[applicants] ) )", "0.00%", "Recruitment"),
    ("Avg Base Salary",
     "CALCULATE ( AVERAGE ( dim_employee[current_base_salary_cad] ), "
     "dim_employee[status] = \"Active\" )", "$#,##0", "Compensation"),
    ("Comp Ratio vs Market",
     "VAR _empAvg = CALCULATE ( AVERAGE ( dim_employee[current_base_salary_cad] ), "
     "dim_employee[status] = \"Active\" ) "
     "VAR _mktAvg = CALCULATE ( AVERAGEX ( FILTER ( dim_employee, "
     "dim_employee[status] = \"Active\" ), RELATED ( dim_role[market_median_salary] ) ) ) "
     "RETURN DIVIDE ( _empAvg, _mktAvg )", "0.00", "Compensation"),
    ("Mandatory Training Completion %",
     "VAR _total = CALCULATE ( COUNTROWS ( fact_training_completion ), "
     "fact_training_completion[is_mandatory] = \"Yes\" ) "
     "VAR _done  = CALCULATE ( COUNTROWS ( fact_training_completion ), "
     "fact_training_completion[is_mandatory] = \"Yes\", "
     "fact_training_completion[status] = \"Completed\" ) "
     "RETURN DIVIDE ( _done, _total )", "0.0%", "Compliance"),
    ("FINTRAC Training Completion %",
     "VAR _t = CALCULATE ( COUNTROWS ( fact_training_completion ), "
     "fact_training_completion[regulator] = \"FINTRAC\" ) "
     "VAR _c = CALCULATE ( COUNTROWS ( fact_training_completion ), "
     "fact_training_completion[regulator] = \"FINTRAC\", "
     "fact_training_completion[status] = \"Completed\" ) "
     "RETURN DIVIDE ( _c, _t )", "0.0%", "Compliance"),
    ("Overdue Mandatory Training",
     "CALCULATE ( COUNTROWS ( fact_training_completion ), "
     "fact_training_completion[is_mandatory] = \"Yes\", "
     "fact_training_completion[status] = \"Overdue\" )", "#,##0", "Compliance"),
    ("COI Overdue 90+ Days",
     "CALCULATE ( COUNTROWS ( fact_attestation ), "
     "fact_attestation[attestation_type] = \"ATT-COI\", "
     "fact_attestation[status] = \"Overdue\", "
     "fact_attestation[days_overdue] >= 90 )", "#,##0", "Compliance"),
]


def measure_block(name, dax, fmt, folder):
    name_q = f"'{name}'" if any(c in name for c in " %()/+-") else name
    return ("\n".join([
        f"\tmeasure {name_q} = {dax}",
        f"\t\tformatString: {fmt}",
        f"\t\tlineageTag: {uuid.uuid4()}",
        f"\t\tdisplayFolder: {folder}",
        "",
    ]))


def step_build_model(ws_id, model_id):
    print("\n[6/8] Pushing relationships + 22 measures + RLS roles...")
    # Re-fetch the now-existing model definition
    s, h, b = call("POST", f"{API}/v1/workspaces/{ws_id}/semanticModels"
                            f"/{model_id}/getDefinition?format=TMDL", body={})
    if s == 202:
        loc = h.get("Location") or h.get("location")
        ok, result_url = poll(loc)
        if not ok:
            raise RuntimeError("getDefinition failed")
        s2, h2, b2 = call("GET", result_url)
        payload = json.loads(b2)
    else:
        payload = json.loads(b)
    parts = {}
    for p in payload["definition"]["parts"]:
        parts[p["path"]] = base64.b64decode(p["payload"]).decode("utf-8", errors="replace")
    # Add relationships
    parts["definition/relationships.tmdl"] = make_relationships_tmdl()
    # Inject measures into fact_headcount_snapshot
    fhs = parts["definition/tables/fact_headcount_snapshot.tmdl"]
    block = "".join(measure_block(*m) for m in MEASURES)
    idx = fhs.find("\tpartition ")
    parts["definition/tables/fact_headcount_snapshot.tmdl"] = fhs[:idx] + block + fhs[idx:]
    # Mark dim_date[date] as key
    dd = parts["definition/tables/dim_date.tmdl"]
    if "isKey" not in dd.split("column date", 1)[1].split("column ", 1)[0]:
        dd = dd.replace("column date\n\t\tdataType: dateTime",
                        "column date\n\t\tisKey\n\t\tdataType: dateTime", 1)
        parts["definition/tables/dim_date.tmdl"] = dd
    # RLS roles
    roles = [
        ("HR Business Partner.tmdl",
         "role 'HR Business Partner'\n\tmodelPermission: read\n\n"
         f"\tannotation PBI_Id = {uuid.uuid4()}\n"),
        ("People Manager.tmdl",
         "role 'People Manager'\n\tmodelPermission: read\n\n"
         "\ttablePermission dim_employee = "
         "[manager_id] = USERPRINCIPALNAME() || [employee_id] = USERPRINCIPALNAME()\n\n"
         f"\tannotation PBI_Id = {uuid.uuid4()}\n"),
        ("Compliance Officer.tmdl",
         "role 'Compliance Officer'\n\tmodelPermission: read\n\n"
         "\ttablePermission dim_employee = "
         "RELATED(dim_department[function]) = \"Risk & Compliance\"\n\n"
         f"\tannotation PBI_Id = {uuid.uuid4()}\n"),
    ]
    for fn, content in roles:
        parts[f"definition/roles/{fn}"] = content
    # Update model.tmdl to ref the roles
    mod = parts["definition/model.tmdl"]
    if "ref role " not in mod:
        lines = mod.rstrip("\n").split("\n")
        last_ref = max(i for i, ln in enumerate(lines) if ln.startswith("ref table"))
        role_refs = ["",
                     "ref role 'HR Business Partner'",
                     "ref role 'People Manager'",
                     "ref role 'Compliance Officer'",
                     ""]
        parts["definition/model.tmdl"] = "\n".join(
            lines[:last_ref + 1] + role_refs + lines[last_ref + 1:]) + "\n"

    # Build payload + push
    payload_parts = [{"path": p, "payload": base64.b64encode(c.encode("utf-8")).decode("ascii"),
                      "payloadType": "InlineBase64"} for p, c in parts.items()]
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{ws_id}/semanticModels/{model_id}/updateDefinition",
                   body={"definition": {"format": "TMDL", "parts": payload_parts}})
    if s == 202:
        loc = h.get("Location") or h.get("location")
        ok, _ = poll(loc)
        if not ok:
            raise RuntimeError("Model build failed")
    elif s not in (200, 201):
        raise RuntimeError(f"updateDefinition failed: {s} {b[:500]}")
    print("   model build OK")


# ============== Step 7: Verify with DAX ==============

def step_verify(ws_id, model_id):
    print("\n[7/8] Verifying measures via DAX...")
    pbi_tok = tok("https://analysis.windows.net/powerbi/api")
    h = {"Authorization": f"Bearer {pbi_tok}", "Content-Type": "application/json"}
    url = (f"https://api.powerbi.com/v1.0/myorg/groups/{ws_id}"
           f"/datasets/{model_id}/executeQueries")
    measures_to_check = ["Active Employees", "Attrition Rate LTM",
                         "% Regrettable LTM", "COI Overdue 90+ Days"]
    for m in measures_to_check:
        body = json.dumps({"queries": [{"query": f"EVALUATE ROW(\"v\", [{m}])"}]}).encode()
        req = urllib.request.Request(url, headers=h, method="POST", data=body)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read().decode())
                v = list(d["results"][0]["tables"][0]["rows"][0].values())[0]
                print(f"   {m:30s} = {v}")
        except urllib.error.HTTPError as e:
            print(f"   {m:30s} ERR {e.code}: {e.read().decode()[:200]}")


# ============== Step 8: Report ==============

def step_report(ws_id, model_id):
    print("\n[8/8] Creating starter report (Exec Overview)...")
    PLATFORM = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": "InteracHR_Report",
                     "description": "Interac HR demo report"},
        "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
    }
    DPBIR = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byConnection": {"connectionString": f"semanticmodelid={model_id}"}},
    }
    VJSON = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "4.0.0",
    }
    RJSON = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/1.0.0/schema.json",
        "themeCollection": {"baseTheme": {"name": "CY24SU10",
                                          "reportVersionAtImport": "5.55",
                                          "type": "SharedResources"}},
        "layoutOptimization": "None",
    }
    PGSJSON = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": ["exec_overview"], "activePageName": "exec_overview",
    }
    PGJSON = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/1.0.0/schema.json",
        "name": "exec_overview", "displayName": "Exec Overview",
        "displayOption": "FitToPage", "height": 720, "width": 1280,
    }

    def card(name, measure, x, y):
        return {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/1.0.0/schema.json",
            "name": name,
            "position": {"x": x, "y": y, "z": 0, "height": 120, "width": 280, "tabOrder": 0},
            "visual": {
                "visualType": "card",
                "query": {"queryState": {"Values": {"projections": [{
                    "field": {"Measure": {
                        "Expression": {"SourceRef": {"Entity": "fact_headcount_snapshot"}},
                        "Property": measure}},
                    "queryRef": f"fact_headcount_snapshot.{measure}", "active": True}]}}}
            }
        }

    cards = [
        ("card_active",      "Active Employees",   40, 40),
        ("card_attrition",   "Attrition Rate LTM", 340, 40),
        ("card_regrettable", "% Regrettable LTM",  640, 40),
        ("card_open_reqs",   "Open Reqs",          940, 40),
    ]

    def b64(obj):
        return base64.b64encode(json.dumps(obj, indent=2).encode("utf-8")).decode("ascii")

    parts = [
        {"path": ".platform",                                "payload": b64(PLATFORM),  "payloadType": "InlineBase64"},
        {"path": "definition.pbir",                          "payload": b64(DPBIR),     "payloadType": "InlineBase64"},
        {"path": "definition/version.json",                  "payload": b64(VJSON),     "payloadType": "InlineBase64"},
        {"path": "definition/report.json",                   "payload": b64(RJSON),     "payloadType": "InlineBase64"},
        {"path": "definition/pages/pages.json",              "payload": b64(PGSJSON),   "payloadType": "InlineBase64"},
        {"path": "definition/pages/exec_overview/page.json", "payload": b64(PGJSON),    "payloadType": "InlineBase64"},
    ]
    for nm, mz, x, y in cards:
        parts.append({"path": f"definition/pages/exec_overview/visuals/{nm}/visual.json",
                      "payload": b64(card(nm, mz, x, y)), "payloadType": "InlineBase64"})
    body = {"displayName": "InteracHR_Report", "type": "Report",
            "definition": {"format": "PBIR", "parts": parts}}
    s, h, b = call("POST", f"{API}/v1/workspaces/{ws_id}/items", body=body)
    if s == 202:
        loc = h.get("Location") or h.get("location")
        ok, result_url = poll(loc)
        if not ok:
            raise RuntimeError("Report create failed")
        s2, h2, b2 = call("GET", result_url)
        r = json.loads(b2)
    elif s in (200, 201):
        r = json.loads(b)
    else:
        raise RuntimeError(f"Report create failed: {s} {b[:500]}")
    print(f"   report = {r['id']}")
    return r["id"]


# ============== Main ==============

def main():
    # Find the trial capacity we just activated
    s, h, b = call("GET", f"{API}/v1/capacities")
    caps = json.loads(b)["value"]
    trial = sorted([c for c in caps
                    if c["displayName"].startswith(TRIAL_CAPACITY_NAME_PREFIX)],
                   key=lambda c: c["displayName"], reverse=True)
    if not trial:
        print("ERROR: No matching trial capacity. Look for: " + TRIAL_CAPACITY_NAME_PREFIX)
        sys.exit(1)
    cap = trial[0]
    print(f"Using capacity: {cap['displayName']} ({cap['sku']}) id={cap['id']}")

    ws_id = step_workspace(cap["id"])
    lh_id, sql_cs, sql_id = step_lakehouse(ws_id)
    step_upload(ws_id, lh_id)
    step_load_delta(ws_id, lh_id)
    model_id = step_semantic_model(ws_id, sql_cs, sql_id)
    step_build_model(ws_id, model_id)
    step_verify(ws_id, model_id)
    report_id = step_report(ws_id, model_id)

    out = {
        "tenant": "microsoft.com",
        "capacity_id": cap["id"],
        "capacity_name": cap["displayName"],
        "workspace_id": ws_id,
        "lakehouse_id": lh_id,
        "sql_endpoint_cs": sql_cs,
        "sql_endpoint_id": sql_id,
        "model_id": model_id,
        "report_id": report_id,
    }
    (ROOT / "stack_corp.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nStack IDs saved to stack_corp.json")
    print(f"\nOpen the report:")
    print(f"  https://app.powerbi.com/groups/{ws_id}/reports/{report_id}")


if __name__ == "__main__":
    main()
