"""Enrich the published HR_data_agent (4f740feb-...) with:

  1. 10 sharp example questions covering all 6 capability areas
  2. dataSourceInstructions explaining table semantics + metric conventions
  3. Per-table descriptions on the datasource elements
  4. An 'Example Use Cases' appendix on aiInstructions

Writes to BOTH draft/ and published/ so the changes are live immediately
without a portal Publish click. Preserves existing aiInstructions text.

Run once:
    py enrich_hr_data_agent.py
"""
from __future__ import annotations

import base64
import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid

AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"
WS = "de6a7e47-474b-4354-87e7-26b8d741f015"
AGENT = "4f740feb-736f-4294-9b06-1e8d725f41cd"   # HR_data_agent (the one user published)


# ---- 10 sharp example questions, exec/compliance-led ------------------------
EXAMPLE_QUESTIONS = [
    "Give me a one-paragraph executive HR briefing for this week.",
    "Show headcount vs target by department for the latest month.",
    "What is our attrition rate LTM vs the prior period, broken down by function?",
    "Which departments have the highest regrettable attrition this quarter?",
    "How many open requisitions do we have and what is the average time to fill by department?",
    "What is our overall compa-ratio versus market and where are the biggest gaps?",
    "What is our current FINTRAC training completion rate, and which departments are below 90%?",
    "How many employees have COI attestations overdue 90+ days, and which leaders are most exposed?",
    "Give me a compliance heatmap by business unit combining FINTRAC and COI risk.",
    "What are the top 3 regulator-sensitive HR risks I should brief my CHRO on this week?",
]


# ---- Data source instructions (table semantics + metric conventions) --------
DATA_SOURCE_INSTRUCTIONS = """\
## Tables and Key Measures

The hr_demo semantic model contains five fact tables and five dimensions
covering Interac's workforce, attrition, recruiting, compensation, and
compliance data.

### Fact tables
- fact_headcount_snapshot — monthly snapshot of active employees with target headcount, FINTRAC training completion %, COI overdue days. Primary fact for KPI cards. Measures: [Active Employees], [Headcount vs Target], [FINTRAC Training Completion %], [COI Overdue 90+ Days].
- fact_attrition — termination events with voluntary/involuntary and regrettable flags. Excludes leaves of absence. Measures: [Terminations LTM], [Attrition Rate LTM], [% Regrettable LTM], [Regrettable Attrition LTM].
- fact_recruitment — open requisitions and hires with hire_date and stage timestamps. Measures: [Open Reqs], [Hires LTM], [Avg Time to Fill (days)].
- fact_compensation — effective-dated base salary with market benchmark by role. Measures: [Avg Base Salary], [Comp Ratio vs Market].
- fact_attestation — per-employee FINTRAC and COI attestation records with due_date and completion status.

### Dimension tables
- dim_employee — directory with tenure, leader_id, full_name. Manager hierarchy via leader_id.
- dim_department, dim_role, dim_location — standard descriptive dimensions.
- dim_date — calendar with year, year_month, fiscal periods. Use for all time-series.

### Common metric semantics
- "LTM" measures use a trailing-12-month window from the latest snapshot.
- Headcount questions default to the most recent snapshot_date unless the user asks for a trend.
- For rate questions, surface both numerator and denominator in the answer.
- Regrettable attrition is a SUBSET of voluntary attrition — they are not synonyms.
- Compa-ratio of 1.00 = market median; values < 0.95 are below market, > 1.10 are notably above.
- FINTRAC training is regulator-mandated; < 90% completion in any department is a material gap.
- COI overdue > 90 days is an audit finding; surface counts AND leader names whenever it appears.

### Defaults
- Currency: CAD.
- Fiscal year: calendar year (Jan–Dec).
- "This quarter" = current calendar quarter unless the user specifies fiscal.
"""


# ---- Per-table descriptions to set on datasource elements -------------------
TABLE_DESCRIPTIONS = {
    "dim_date":                "Calendar dimension with year, year_month, fiscal period. Use for all time-series and trend analyses.",
    "dim_department":          "Department / business unit dimension. Standard grouping for workforce, attrition, and compliance metrics.",
    "dim_employee":            "Employee directory including tenure, leader_id, full_name. Manager hierarchy is via leader_id.",
    "dim_role":                "Role / job family dimension. Use for compensation and time-to-fill analyses.",
    "dim_location":            "Office and city dimension.",
    "fact_attestation":        "Per-employee FINTRAC training and COI attestation events with due_date and completion status.",
    "fact_attrition":          "Termination events with voluntary/involuntary and regrettable flags. Excludes leaves of absence.",
    "fact_compensation":       "Effective-dated base salary records with market benchmark by role for compa-ratio analysis.",
    "fact_headcount_snapshot": "Monthly active-headcount snapshot with target headcount, FINTRAC completion %, COI overdue days. Primary fact for KPI cards.",
    "fact_recruitment":        "Open requisitions and hires with sourcing/interview/offer stage timestamps for time-to-fill analysis.",
    "fact_training_completion": "Per-employee mandatory training records (course, regulator, due_date, completion_date, status, days_overdue). Use for FINTRAC and other regulator-required training analyses; join to dim_employee via employee_id.",
}


# ---- Appendix to append onto existing aiInstructions ------------------------
USE_CASES_APPENDIX = """

---

## Example Use Cases

Users frequently ask the following question patterns. When you recognize one,
prefer measures and table groupings called out in the data source instructions:

1. Executive briefing — "Give me a one-paragraph HR briefing for the week."
2. Headcount — "Show headcount vs target by department for the latest month."
3. Attrition — "What is our attrition rate LTM vs the prior period, by function?"
4. Hot spots — "Which departments have the highest regrettable attrition this quarter?"
5. Recruiting — "How many open reqs do we have and what is avg time to fill by department?"
6. Pay equity — "What is our compa-ratio vs market and where are the largest gaps?"
7. FINTRAC — "What is our current FINTRAC completion rate, and which departments are below 90%?"
8. COI — "How many employees have COI attestations overdue 90+ days, and which leaders are most exposed?"
9. Compliance heatmap — "Give me a compliance heatmap by business unit combining FINTRAC and COI risk."
10. CHRO brief — "What are the top 3 regulator-sensitive HR risks I should brief my CHRO on this week?"

When answering an "executive briefing" or "top risks" question, structure the
response with: (1) one-line headline, (2) 2–3 bullet hot spots with the specific
numbers, (3) one explicit recommendation. Aim for under 120 words.
"""


# ---- API plumbing ----------------------------------------------------------

def tok() -> str:
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", API,
         "--query", "accessToken", "-o", "tsv"]).decode().strip()


def call(method: str, url: str, body=None):
    h = {"Authorization": f"Bearer {tok()}", "Content-Type": "application/json",
         "ActivityId": str(uuid.uuid4())}
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    req = urllib.request.Request(url, headers=h, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def poll(loc: str):
    for _ in range(90):
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


def b64_obj(o) -> str:
    return base64.b64encode(json.dumps(o, indent=2, ensure_ascii=False).encode("utf-8")).decode("ascii")


# ---- Main ------------------------------------------------------------------

def main():
    print("Fetching HR_data_agent definition...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/dataagents/{AGENT}/getDefinition",
                   body={})
    if s == 202:
        ok, result_url = poll(h.get("Location") or h.get("location"))
        if not ok:
            return
        payload = json.loads(call("GET", result_url)[2])
    else:
        payload = json.loads(b)
    parts = {p["path"]: base64.b64decode(p["payload"]).decode("utf-8")
             for p in payload["definition"]["parts"]}
    print(f"  Loaded {len(parts)} parts")

    # --- 1. Top-level data_agent.json: add exampleQuestions ----------------
    da_path = "Files/Config/data_agent.json"
    da = json.loads(parts[da_path])
    da["exampleQuestions"] = EXAMPLE_QUESTIONS
    parts[da_path] = json.dumps(da, indent=2, ensure_ascii=False)
    print(f"  Set {len(EXAMPLE_QUESTIONS)} exampleQuestions on {da_path}")

    # --- 2. stage_config.json (draft + published): append use-cases section --
    for stage in ("draft", "published"):
        sc_path = f"Files/Config/{stage}/stage_config.json"
        sc = json.loads(parts[sc_path])
        existing = sc.get("aiInstructions", "") or ""
        # Idempotent: only append if not already appended
        if "## Example Use Cases" not in existing:
            sc["aiInstructions"] = existing.rstrip() + USE_CASES_APPENDIX
        # Also set top-level exampleQuestions for clients that read it here
        sc["exampleQuestions"] = EXAMPLE_QUESTIONS
        parts[sc_path] = json.dumps(sc, indent=2, ensure_ascii=False)
        print(f"  Updated {sc_path} (aiInstructions {len(sc['aiInstructions'])} chars + {len(EXAMPLE_QUESTIONS)} prompts)")

    # --- 3. datasource.json (draft + published): instructions + descriptions
    for stage in ("draft", "published"):
        ds_path = f"Files/Config/{stage}/semantic-model-hr_demo/datasource.json"
        ds = json.loads(parts[ds_path])
        ds["dataSourceInstructions"] = DATA_SOURCE_INSTRUCTIONS
        # Set per-table descriptions
        described = 0
        for el in ds.get("elements", []):
            if el.get("type") == "semantic_model.table":
                name = el.get("display_name")
                if name in TABLE_DESCRIPTIONS:
                    el["description"] = TABLE_DESCRIPTIONS[name]
                    described += 1
        # Also drop the example questions onto the datasource itself (the
        # configure_data_agents.py shape stored them here; harmless if ignored).
        ds["exampleQuestions"] = EXAMPLE_QUESTIONS
        parts[ds_path] = json.dumps(ds, indent=2, ensure_ascii=False)
        print(f"  Updated {ds_path}: dataSourceInstructions set, {described} table descriptions")

    # --- 4. Push everything back via updateDefinition ----------------------
    payload_parts = [{"path": p,
                      "payload": base64.b64encode(c.encode("utf-8")).decode("ascii"),
                      "payloadType": "InlineBase64"}
                     for p, c in parts.items()]
    print(f"\nPOSTing updateDefinition with {len(payload_parts)} parts...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/dataagents/{AGENT}/updateDefinition",
                   body={"definition": {"parts": payload_parts}})
    print(f"  status={s}")
    if s == 202:
        ok, _ = poll(h.get("Location") or h.get("location"))
        if ok:
            print("  OK")
        else:
            print("  update failed")
            return
    elif s in (200, 201):
        print("  OK (sync)")
    else:
        print(f"  ERROR: {b[:1200]}")
        return

    print(f"\n  Agent enriched: https://msit.powerbi.com/groups/{WS}/dataagents/{AGENT}")
    print("  Test by opening the agent and confirming the 10 prompts appear as suggestions.")


if __name__ == "__main__":
    main()
