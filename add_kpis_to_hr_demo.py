"""Add 8 proper KPI definitions to hr_demo via TMDL updateDefinition.

Each KPI has:
  - A target measure (constant)
  - A KPI base measure (alias of existing) with `kpi` block attached:
      targetExpression  - the goal
      statusGraphic     - 'Traffic Light - Single'
      statusExpression  - SWITCH returning -1 (red) / 0 (yellow) / 1 (green)

Once pushed, drag the KPI base measure onto a report canvas:
  - Power BI shows a KPI icon next to it in the field list
  - Default visual is the KPI visual with status indicator
"""
from __future__ import annotations

import base64
import json
import subprocess
import time
import urllib.request
import urllib.error
import uuid

WS = "de6a7e47-474b-4354-87e7-26b8d741f015"
MODEL = "89782e0a-276b-4b86-a2d0-e8238d3c8791"
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"


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


def poll(loc):
    for i in range(60):
        time.sleep(2)
        s, h, b = call("GET", loc)
        try:
            st = json.loads(b).get("status")
        except Exception:
            st = None
        if st == "Succeeded":
            return True, loc.rstrip("/") + "/result"
        if st == "Failed":
            print(f"   FAILED: {b[:600]}")
            return False, None
    return False, None


# (kpi_name, base_measure, target_name, target_value, format,
#  direction, green_threshold_expr, yellow_threshold_expr)
# direction: "higher" or "lower" relative to thresholds
#   - higher: green if base >= green_t, yellow if >= yellow_t, else red
#   - lower:  green if base <= green_t, yellow if <= yellow_t, else red
KPI_SPECS = [
    ("Headcount vs Target",          "Active Employees",                "Headcount Target",        "1000",  "#,##0",  "higher", "950",   "850"),
    ("Attrition Rate vs Threshold",  "Attrition Rate LTM",              "Attrition Target",        "0.12",  "0.0%",   "lower",  "0.12",  "0.18"),
    ("Regrettable Attrition Risk",   "% Regrettable LTM",               "Regrettable Target",      "0.15",  "0.0%",   "lower",  "0.15",  "0.25"),
    ("Open Reqs Pipeline Health",    "Open Reqs",                       "Open Reqs Capacity",      "100",   "#,##0",  "lower",  "60",    "100"),
    ("Time to Fill SLA",             "Avg Time to Fill (days)",         "Time to Fill Target",     "60",    "#,##0.0","lower",  "60",    "90"),
    ("Market Comp Competitiveness",  "Comp Ratio vs Market",            "Comp Ratio Target",       "1.00",  "0.00",   "higher", "1.00",  "0.95"),
    ("FINTRAC Training Compliance",  "FINTRAC Training Completion %",   "FINTRAC Training Target", "0.95",  "0.0%",   "higher", "0.95",  "0.90"),
    ("COI Attestation Risk",         "COI Overdue 90+ Days",            "COI Overdue Target",      "0",     "#,##0",  "lower",  "0",     "3"),
]


def strip_measures(tmdl: str, names: list[str]) -> str:
    """Remove existing `measure <name> = ...` blocks (and their property lines)
    so we can re-add cleanly.

    A measure block starts with '\tmeasure <name>' and runs until the next
    top-level token at the same indentation level (next '\tmeasure', '\tcolumn',
    '\tpartition', or end of file).
    """
    out_lines = []
    lines = tmdl.split("\n")
    i = 0
    while i < len(lines):
        ln = lines[i]
        match = False
        stripped = ln.lstrip("\t")
        if stripped.startswith("measure "):
            # Extract measure name. Format: "measure <name> = ..." or "measure '<name>' = ..."
            rest = stripped[len("measure "):].strip()
            if rest.startswith("'"):
                end = rest.find("'", 1)
                mname = rest[1:end] if end > 0 else ""
            else:
                # Name ends at space or '='
                m = ""
                for ch in rest:
                    if ch in (" ", "="):
                        break
                    m += ch
                mname = m
            if mname in names:
                match = True
                # Skip until next sibling: line that starts with '\t' followed by a known sibling keyword
                i += 1
                while i < len(lines):
                    nxt = lines[i]
                    nstripped = nxt.lstrip("\t")
                    # Stop at next measure/column/partition/annotation at table-level (1 tab indent)
                    if nxt.startswith("\t") and not nxt.startswith("\t\t"):
                        if (nstripped.startswith("measure ") or
                                nstripped.startswith("column ") or
                                nstripped.startswith("partition ") or
                                nstripped.startswith("annotation ") or
                                nstripped.startswith("hierarchy ")):
                            break
                    # Stop at unindented lines too (defensive)
                    if not nxt.startswith("\t") and nxt.strip():
                        break
                    i += 1
                continue
        if not match:
            out_lines.append(ln)
            i += 1
    return "\n".join(out_lines)


def render_target_measure(name, value, fmt):
    name_q = f"'{name}'" if any(c in name for c in " %()/+-") else name
    return "\n".join([
        f"\tmeasure {name_q} = {value}",
        f"\t\tformatString: {fmt}",
        f"\t\tlineageTag: {uuid.uuid4()}",
        f"\t\tdisplayFolder: KPIs",
        "",
    ])


def render_kpi_measure(kpi_name, base_name, target_name, fmt,
                       direction, green_t, yellow_t):
    """Render a KPI measure: base measure + kpi block.
    Status returns 1 (green), 0 (yellow), -1 (red).
    """
    base_q = f"[{base_name}]"
    if direction == "higher":
        op_g, op_y = ">=", ">="
    else:
        op_g, op_y = "<=", "<="
    # statusExpression body must be indented MORE than 'statusExpression =' itself.
    # kpi is at 2 tabs, statusExpression at 3 tabs, body at 4 tabs.
    status_dax_body = (
        f"\t\t\t\tVAR _v = {base_q}\n"
        f"\t\t\t\tRETURN SWITCH ( TRUE (), _v {op_g} {green_t}, 1, "
        f"_v {op_y} {yellow_t}, 0, -1 )"
    )
    kpi_q = f"'{kpi_name}'" if any(c in kpi_name for c in " %()/+-") else kpi_name
    target_q = f"[{target_name}]"
    return "\n".join([
        f"\tmeasure {kpi_q} = {base_q}",
        f"\t\tformatString: {fmt}",
        f"\t\tlineageTag: {uuid.uuid4()}",
        f"\t\tdisplayFolder: KPIs",
        "",
        f"\t\tkpi",
        f"\t\t\ttargetExpression: {target_q}",
        f"\t\t\tstatusGraphic: \"Traffic Light - Single\"",
        f"\t\t\tstatusExpression =",
        f"{status_dax_body}",
        "",
    ])


def main():
    # 1. Fetch current TMDL
    print("Fetching hr_demo TMDL...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/semanticModels/{MODEL}"
                   f"/getDefinition?format=TMDL", body={})
    if s == 202:
        loc = h.get("Location") or h.get("location")
        ok, result_url = poll(loc)
        if not ok:
            return
        s2, h2, b2 = call("GET", result_url)
        payload = json.loads(b2)
    else:
        payload = json.loads(b)
    parts = {p["path"]: base64.b64decode(p["payload"]).decode("utf-8", errors="replace")
             for p in payload["definition"]["parts"]}
    print(f"  Loaded {len(parts)} parts")

    # 2. Build the block of new measures (targets + KPI base measures)
    block_lines = []
    for (kpi, base, tgt, val, fmt, dr, gt, yt) in KPI_SPECS:
        block_lines.append(render_target_measure(tgt, val, fmt))
        block_lines.append(render_kpi_measure(kpi, base, tgt, fmt, dr, gt, yt))
    new_block = "".join(block_lines)

    # 3. Inject into fact_headcount_snapshot.tmdl, before the partition.
    # First strip ANY existing measure blocks for KPI/target names we want to add
    # (Copilot may have created bare target measures already; we replace cleanly).
    fhs_path = "definition/tables/fact_headcount_snapshot.tmdl"
    fhs = parts[fhs_path]
    names_to_strip = []
    for (kpi, base, tgt, val, fmt, dr, gt, yt) in KPI_SPECS:
        names_to_strip.extend([kpi, tgt])
    fhs = strip_measures(fhs, names_to_strip)
    print(f"  Stripped {len(names_to_strip)} pre-existing measure entries (if any)")
    idx = fhs.find("\tpartition ")
    parts[fhs_path] = fhs[:idx] + new_block + fhs[idx:]
    print(f"  Injected {len(KPI_SPECS)} KPI definitions + targets ({len(KPI_SPECS)*2} measures)")

    # 4. Push
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
        if not ok:
            return
    elif s not in (200, 201):
        print(f"  ERROR: {b[:800]}")
        return

    print("\n  KPIs pushed successfully.")

    # 5. Verify with DAX
    print("\nVerifying KPI measures via DAX:")
    pbi_tok = tok("https://analysis.windows.net/powerbi/api")
    hh = {"Authorization": f"Bearer {pbi_tok}", "Content-Type": "application/json"}
    url = (f"https://api.powerbi.com/v1.0/myorg/groups/{WS}"
           f"/datasets/{MODEL}/executeQueries")
    for spec in KPI_SPECS:
        kpi, base, tgt, val, fmt, dr, gt, yt = spec
        body = json.dumps({"queries": [{"query":
            f"EVALUATE ROW ( \"value\", [{kpi}], \"target\", [{tgt}] )"
        }]}).encode()
        req = urllib.request.Request(url, headers=hh, method="POST", data=body)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read().decode())
                row = d["results"][0]["tables"][0]["rows"][0]
                v = list(row.values())[0]
                t = list(row.values())[1]
                # Compute expected status emoji for visibility
                v_num = float(v) if v is not None else 0
                gt_num = float(gt)
                yt_num = float(yt)
                if dr == "higher":
                    icon = "GREEN" if v_num >= gt_num else ("YELLOW" if v_num >= yt_num else "RED")
                else:
                    icon = "GREEN" if v_num <= gt_num else ("YELLOW" if v_num <= yt_num else "RED")
                print(f"  {kpi:30s} value={str(v)[:10]:>10s}  target={t}  -> {icon}")
        except urllib.error.HTTPError as e:
            b = e.read().decode()
            print(f"  {kpi:30s} ERR {e.code}: {b[:200]}")


if __name__ == "__main__":
    main()
