"""Build the InteracHR_Model semantic model via Fabric REST API.

What this does:
  1. Fetches the current TMDL definition (auto-created from lakehouse).
  2. Generates a relationships.tmdl file with star/snowflake relationships.
  3. Adds measures inline to fact_headcount_snapshot.tmdl (~20 DAX measures).
  4. Marks dim_date as the date table.
  5. PUSHes the updated definition via POST updateDefinition.

Design choice: snowflake via dim_employee for dim_dept/role/location
(unambiguous), star for dim_date.
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

WORKSPACE_ID = "2690ef29-1370-476c-b28c-58a505fea2bd"
MODEL_ID = "00bb5cc7-20c0-4030-ae35-25a2ec02bc87"
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"

ROOT = Path(__file__).parent
MODEL_DIR = ROOT / "model_current"

API = "https://api.fabric.microsoft.com"


def token() -> str:
    return subprocess.check_output(
        [AZ, "account", "get-access-token",
         "--resource", f"{API}",
         "--query", "accessToken", "-o", "tsv"]
    ).decode().strip()


def call(method, url, body=None):
    headers = {"Authorization": f"Bearer {token()}",
               "ActivityId": str(uuid.uuid4()),
               "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, headers=headers, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


# -------- Build relationships --------

def make_relationships_tmdl() -> str:
    """Snowflake from dim_employee for dim_dept/role/location, star for dim_date.

    Format:
      relationship <uuid>
          fromColumn: <table>.<col>
          toColumn:   <table>.<col>
          [isActive: false]
    """
    rels = [
        # dim_department -> dim_employee
        ("dim_employee.department_id", "dim_department.department_id", True),
        # dim_role -> dim_employee
        ("dim_employee.role_id", "dim_role.role_id", True),
        # dim_location -> dim_employee
        ("dim_employee.location_id", "dim_location.location_id", True),
        # dim_employee -> all facts via employee_id
        ("fact_headcount_snapshot.employee_id", "dim_employee.employee_id", True),
        ("fact_attrition.employee_id",          "dim_employee.employee_id", True),
        ("fact_compensation.employee_id",       "dim_employee.employee_id", True),
        ("fact_training_completion.employee_id","dim_employee.employee_id", True),
        ("fact_attestation.employee_id",        "dim_employee.employee_id", True),
        ("fact_recruitment.hired_employee_id",  "dim_employee.employee_id", False),  # inactive
        # dim_date -> facts (star, direct via date column)
        ("fact_headcount_snapshot.snapshot_date", "dim_date.date", True),
        ("fact_attrition.termination_date",       "dim_date.date", True),
        ("fact_compensation.effective_date",      "dim_date.date", True),
        ("fact_recruitment.hire_date",            "dim_date.date", True),
        ("fact_recruitment.posting_date",         "dim_date.date", False),  # inactive
        ("fact_training_completion.due_date",     "dim_date.date", True),
        ("fact_attestation.due_date",             "dim_date.date", True),
        # dim_role -> fact_recruitment (for "open reqs by role" without going through dim_employee)
        ("fact_recruitment.role_id", "dim_role.role_id", True),
        # dim_department -> fact_recruitment
        ("fact_recruitment.department_id", "dim_department.department_id", True),
        # dim_location -> fact_recruitment
        ("fact_recruitment.location_id", "dim_location.location_id", True),
    ]

    lines = []
    for from_col, to_col, active in rels:
        rid = str(uuid.uuid4())
        lines.append(f"relationship {rid}")
        if not active:
            lines.append("\tisActive: false")
        lines.append(f"\tfromColumn: {from_col}")
        lines.append(f"\ttoColumn: {to_col}")
        lines.append("")
    return "\n".join(lines)


# -------- Build measures --------

MEASURES = [
    # (name, dax, formatString, displayFolder)
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
     "VAR _f = CALCULATE ( [Active Employees], dim_employee[gender] = \"F\", dim_role[is_tech_role] = \"Yes\" ) "
     "RETURN DIVIDE ( _f, [Tech Employees] )",
     "0.0%", "Diversity"),

    ("Terminations (Period)",
     "COUNTROWS ( fact_attrition )",
     "#,##0", "Attrition"),

    ("Terminations LTM",
     "CALCULATE ( [Terminations (Period)], DATESINPERIOD ( dim_date[date], TODAY(), -12, MONTH ) )",
     "#,##0", "Attrition"),

    ("Avg Headcount LTM",
     "VAR _snapshots = "
     "  FILTER ( "
     "    VALUES ( fact_headcount_snapshot[snapshot_date] ), "
     "    fact_headcount_snapshot[snapshot_date] >= EDATE ( TODAY(), -12 ) "
     "    && fact_headcount_snapshot[snapshot_date] <= TODAY() "
     "  ) "
     "RETURN AVERAGEX ( _snapshots, CALCULATE ( DISTINCTCOUNT ( fact_headcount_snapshot[employee_id] ) ) )",
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
     "CALCULATE ( DISTINCTCOUNT ( fact_recruitment[req_id] ), fact_recruitment[status] = \"Open\" )",
     "#,##0", "Recruitment"),

    ("Hires LTM",
     "CALCULATE ( "
     "  DISTINCTCOUNT ( fact_recruitment[req_id] ), "
     "  fact_recruitment[status] = \"Filled\", "
     "  USERELATIONSHIP ( fact_recruitment[hire_date], dim_date[date] ), "
     "  DATESINPERIOD ( dim_date[date], TODAY(), -12, MONTH ) "
     ")",
     "#,##0", "Recruitment"),

    ("Avg Time to Fill (days)",
     "CALCULATE ( AVERAGE ( fact_recruitment[time_to_fill_days] ), fact_recruitment[status] = \"Filled\" )",
     "#,##0.0", "Recruitment"),

    ("Pipeline Conversion",
     "DIVIDE ( SUM ( fact_recruitment[offers_accepted] ), SUM ( fact_recruitment[applicants] ) )",
     "0.00%", "Recruitment"),

    ("Avg Base Salary",
     "CALCULATE ( AVERAGE ( dim_employee[current_base_salary_cad] ), dim_employee[status] = \"Active\" )",
     "$#,##0", "Compensation"),

    ("Comp Ratio vs Market",
     "VAR _empAvg = "
     "  CALCULATE ( AVERAGE ( dim_employee[current_base_salary_cad] ), dim_employee[status] = \"Active\" ) "
     "VAR _mktAvg = "
     "  CALCULATE ( "
     "    AVERAGEX ( "
     "      FILTER ( dim_employee, dim_employee[status] = \"Active\" ), "
     "      RELATED ( dim_role[market_median_salary] ) "
     "    ) "
     "  ) "
     "RETURN DIVIDE ( _empAvg, _mktAvg )",
     "0.00", "Compensation"),

    ("Mandatory Training Completion %",
     "VAR _total = CALCULATE ( COUNTROWS ( fact_training_completion ), fact_training_completion[is_mandatory] = \"Yes\" ) "
     "VAR _done  = CALCULATE ( COUNTROWS ( fact_training_completion ), fact_training_completion[is_mandatory] = \"Yes\", "
     "                          fact_training_completion[status] = \"Completed\" ) "
     "RETURN DIVIDE ( _done, _total )",
     "0.0%", "Compliance"),

    ("FINTRAC Training Completion %",
     "VAR _t = CALCULATE ( COUNTROWS ( fact_training_completion ), fact_training_completion[regulator] = \"FINTRAC\" ) "
     "VAR _c = CALCULATE ( COUNTROWS ( fact_training_completion ), fact_training_completion[regulator] = \"FINTRAC\", "
     "                      fact_training_completion[status] = \"Completed\" ) "
     "RETURN DIVIDE ( _c, _t )",
     "0.0%", "Compliance"),

    ("Overdue Mandatory Training",
     "CALCULATE ( COUNTROWS ( fact_training_completion ), "
     "  fact_training_completion[is_mandatory] = \"Yes\", "
     "  fact_training_completion[status] = \"Overdue\" )",
     "#,##0", "Compliance"),

    ("COI Overdue 90+ Days",
     "CALCULATE ( COUNTROWS ( fact_attestation ), "
     "  fact_attestation[attestation_type] = \"ATT-COI\", "
     "  fact_attestation[status] = \"Overdue\", "
     "  fact_attestation[days_overdue] >= 90 )",
     "#,##0", "Compliance"),
]


def measure_block(name, dax, fmt, folder) -> str:
    """Render a single TMDL measure block (tab-indented, sits inside a table)."""
    # Quote name if it has spaces/specials
    if any(c in name for c in " %()/+-"):
        name_q = f"'{name}'"
    else:
        name_q = name
    # DAX value goes on its own indented line. We use a single-line DAX for simplicity.
    lines = [
        f"\tmeasure {name_q} = {dax}",
        f"\t\tformatString: {fmt}",
        f"\t\tlineageTag: {uuid.uuid4()}",
        f"\t\tdisplayFolder: {folder}",
        "",
    ]
    return "\n".join(lines)


def inject_measures(tmdl: str, measures: list) -> str:
    """Insert measures into a table tmdl, right before the partition block."""
    block = "".join(measure_block(*m) for m in measures)
    # Find the line starting with "\tpartition " (tab + partition)
    idx = tmdl.find("\tpartition ")
    if idx < 0:
        raise RuntimeError("Could not find partition block in tmdl")
    return tmdl[:idx] + block + tmdl[idx:]


def mark_date_table(tmdl: str) -> str:
    """Add dataCategory: Time + isKey to the 'date' column in dim_date.tmdl."""
    # Add isKey to column 'date'
    needle = "column date\n\t\tdataType: dateTime"
    repl = "column date\n\t\tisKey\n\t\tdataType: dateTime"
    if needle in tmdl and "isKey" not in tmdl.split("column date", 1)[1].split("column ", 1)[0]:
        tmdl = tmdl.replace(needle, repl, 1)
    return tmdl


# -------- Main --------

def main():
    print("Loading current TMDL parts...")
    parts = {}
    for f in MODEL_DIR.iterdir():
        if f.is_file():
            # Reconstruct path: 'definition__tables__x.tmdl' -> 'definition/tables/x.tmdl'
            path = f.name.replace("__", "/")
            parts[path] = f.read_text(encoding="utf-8")
    print(f"  Loaded {len(parts)} parts")

    # 1. Add relationships file
    parts["definition/relationships.tmdl"] = make_relationships_tmdl()
    print(f"  Added relationships ({len(parts['definition/relationships.tmdl'])} chars, "
          f"{parts['definition/relationships.tmdl'].count('relationship ')} relationships)")

    # 2. Inject all measures into fact_headcount_snapshot
    fhs_path = "definition/tables/fact_headcount_snapshot.tmdl"
    parts[fhs_path] = inject_measures(parts[fhs_path], MEASURES)
    print(f"  Injected {len(MEASURES)} measures into fact_headcount_snapshot.tmdl")

    # 3. Mark dim_date
    dd_path = "definition/tables/dim_date.tmdl"
    parts[dd_path] = mark_date_table(parts[dd_path])
    print(f"  Marked dim_date[date] as key column")

    # 4. Build the updateDefinition payload
    payload_parts = []
    for path, content in parts.items():
        payload_parts.append({
            "path": path,
            "payload": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "payloadType": "InlineBase64",
        })
    payload = {
        "definition": {
            "format": "TMDL",
            "parts": payload_parts,
        }
    }

    # Save a local copy for debugging
    out = ROOT / "model_updated.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"  Saved payload to {out.name}")

    # 5. POST updateDefinition
    print("\nPOSTing updateDefinition...")
    url = (f"{API}/v1/workspaces/{WORKSPACE_ID}"
           f"/semanticModels/{MODEL_ID}/updateDefinition")
    s, h, b = call("POST", url, body=payload)
    print(f"  status={s}")
    if s == 202:
        loc = h.get("Location") or h.get("location")
        print(f"  polling {loc}")
        for i in range(60):
            time.sleep(2)
            sp, hp, bp = call("GET", loc)
            try:
                op = json.loads(bp)
                st = op.get("status")
            except Exception:
                st = None
            print(f"  poll {i+1}: status={st}")
            if st == "Succeeded":
                print("\n  Model updated successfully.")
                return
            if st == "Failed":
                print(f"\n  FAILED: {bp}")
                return
        print("  TIMEOUT")
    elif s in (200, 201):
        print("  OK (sync)")
    else:
        print(f"  ERROR body: {b[:600]}")


if __name__ == "__main__":
    main()
