"""Push relationships + 22 measures + 3 RLS roles into the hr_demo model
that Anurag created in the portal.

  workspace = de6a7e47-474b-4354-87e7-26b8d741f015 (InteracHRDemo, corp)
  model     = 89782e0a-276b-4b86-a2d0-e8238d3c8791 (hr_demo)
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

WS = "de6a7e47-474b-4354-87e7-26b8d741f015"
MODEL = "89782e0a-276b-4b86-a2d0-e8238d3c8791"
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"
ROOT = Path(__file__).parent


def tok(resource=API):
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"]).decode().strip()


def call(method, url, body=None, resource=None):
    h = {"Authorization": f"Bearer {tok(resource or API)}",
         "Content-Type": "application/json",
         "ActivityId": str(uuid.uuid4())}
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    req = urllib.request.Request(url, headers=h, method=method, data=data)
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
            st = json.loads(b).get("status")
        except Exception:
            st = None
        if st == "Succeeded":
            return True, loc.rstrip("/") + "/result"
        if st == "Failed":
            print(f"   FAILED: {b[:500]}")
            return False, None
    return False, None


# ---- Relationships ----
RELS = [
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


def make_relationships_tmdl():
    lines = []
    for fr, to, active in RELS:
        rid = str(uuid.uuid4())
        lines.append(f"relationship {rid}")
        if not active:
            lines.append("\tisActive: false")
        lines.append(f"\tfromColumn: {fr}")
        lines.append(f"\ttoColumn: {to}")
        lines.append("")
    return "\n".join(lines)


# ---- Measures (22) ----
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
    return "\n".join([
        f"\tmeasure {name_q} = {dax}",
        f"\t\tformatString: {fmt}",
        f"\t\tlineageTag: {uuid.uuid4()}",
        f"\t\tdisplayFolder: {folder}",
        "",
    ])


# ---- RLS roles ----
ROLES = [
    ("HR Business Partner.tmdl",
     f"role 'HR Business Partner'\n\tmodelPermission: read\n\n"
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


def main():
    # 1) Fetch current definition
    print("Fetching hr_demo current TMDL...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/semanticModels/{MODEL}/getDefinition?format=TMDL",
                   body={})
    if s == 202:
        loc = h.get("Location") or h.get("location")
        ok, result_url = poll(loc)
        if not ok:
            print("getDefinition failed")
            return
        s2, h2, b2 = call("GET", result_url)
        payload = json.loads(b2)
    else:
        payload = json.loads(b)
    parts = {}
    for p in payload["definition"]["parts"]:
        parts[p["path"]] = base64.b64decode(p["payload"]).decode("utf-8", errors="replace")
    print(f"  Loaded {len(parts)} parts:")
    table_count = sum(1 for k in parts if k.startswith("definition/tables/"))
    print(f"  Tables: {table_count}")
    if table_count < 11:
        print("  WARNING: model has fewer than 11 tables — make sure all lakehouse tables")
        print("           are added to the model before proceeding")
        for k in parts:
            if k.startswith("definition/tables/"):
                print(f"    found: {k}")
        return

    # 2) Add relationships
    parts["definition/relationships.tmdl"] = make_relationships_tmdl()
    print(f"  Added {len(RELS)} relationships")

    # 3) Inject measures into fact_headcount_snapshot
    fhs_path = "definition/tables/fact_headcount_snapshot.tmdl"
    if fhs_path not in parts:
        print(f"  ERROR: {fhs_path} not found - can't add measures")
        return
    fhs = parts[fhs_path]
    block = "".join(measure_block(*m) for m in MEASURES)
    idx = fhs.find("\tpartition ")
    parts[fhs_path] = fhs[:idx] + block + fhs[idx:]
    print(f"  Injected {len(MEASURES)} measures")

    # 4) Mark dim_date[date] as key
    dd_path = "definition/tables/dim_date.tmdl"
    if dd_path in parts:
        dd = parts[dd_path]
        post = dd.split("column date", 1)[1].split("column ", 1)[0] if "column date" in dd else ""
        if "isKey" not in post:
            dd = dd.replace("column date\n\t\tdataType: dateTime",
                            "column date\n\t\tisKey\n\t\tdataType: dateTime", 1)
            parts[dd_path] = dd
            print("  Marked dim_date[date] as key")

    # 5) Add RLS roles
    for fn, content in ROLES:
        parts[f"definition/roles/{fn}"] = content
    # Update model.tmdl with ref role lines
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
    print("  Added 3 RLS roles")

    # 6) Push
    print("\nPOSTing updateDefinition...")
    payload_parts = [{"path": p,
                      "payload": base64.b64encode(c.encode("utf-8")).decode("ascii"),
                      "payloadType": "InlineBase64"} for p, c in parts.items()]
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/semanticModels/{MODEL}/updateDefinition",
                   body={"definition": {"format": "TMDL", "parts": payload_parts}})
    print(f"  status={s}")
    if s == 202:
        loc = h.get("Location") or h.get("location")
        ok, _ = poll(loc)
        if ok:
            print("\n  hr_demo updated successfully.")
        else:
            print("  Update failed.")
    elif s not in (200, 201):
        print(f"  ERROR: {b[:800]}")

    # 7) Verify
    print("\nVerifying measures via DAX:")
    pbi_tok = tok("https://analysis.windows.net/powerbi/api")
    hh = {"Authorization": f"Bearer {pbi_tok}", "Content-Type": "application/json"}
    url = (f"https://api.powerbi.com/v1.0/myorg/groups/{WS}"
           f"/datasets/{MODEL}/executeQueries")
    for m in ["Active Employees", "Attrition Rate LTM", "% Regrettable LTM",
              "COI Overdue 90+ Days", "Open Reqs", "Avg Base Salary"]:
        body = json.dumps({"queries": [{"query": f"EVALUATE ROW(\"v\", [{m}])"}]}).encode()
        req = urllib.request.Request(url, headers=hh, method="POST", data=body)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read().decode())
                v = list(d["results"][0]["tables"][0]["rows"][0].values())[0]
                print(f"  {m:32s} = {v}")
        except urllib.error.HTTPError as e:
            b = e.read().decode()
            print(f"  {m:32s} ERR {e.code}: {b[:140]}")


if __name__ == "__main__":
    main()
