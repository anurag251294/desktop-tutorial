"""Attach `kpi` TMDL blocks to key measures in ctc_merch so the report can
render traffic-light KPI visuals (the "narrative KPI" look the demo wants).
Also adds a few target measures (constants the KPI status compares against).
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

STACK = json.loads((Path(__file__).parent / "stack_ctc.json").read_text())
WS = STACK["workspace_id"]
MODEL = STACK["model_id"]
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"


def tok():
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", API,
         "--query", "accessToken", "-o", "tsv"]).decode().strip()


def call(method, url, body=None):
    h = {"Authorization": f"Bearer {tok()}", "Content-Type": "application/json",
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
            print(f"  FAILED: {b[:600]}")
            return False, None
    return False, None


# (kpi_name, base_measure_ref, target_name, target_value, fmt, direction,
#  green_threshold, yellow_threshold, host_table)
# direction: "higher" => green if base >= green_t
#            "lower"  => green if base <= green_t
KPI_SPECS = [
    ("POS YoY KPI",          "[POS YoY %]",                "POS YoY Target",       "0.05",  "0.0%",    "higher", "0.05",  "0.0",
     "fact_sku_performance"),
    ("EGM % KPI",            "[EGM % TY]",                 "EGM Target",           "0.40",  "0.0%",    "higher", "0.40",  "0.35",
     "fact_sku_performance"),
    ("Lost Sales KPI",       "[Avg Lost Sales %]",          "Lost Sales Threshold", "0.03",  "0.0%",    "lower",  "0.03",  "0.05",
     "fact_connected_inventory"),
    ("Fill Rate KPI",        "[Avg Vendor Fill Rate %]",    "Fill Rate Target",     "0.92",  "0.0%",    "higher", "0.92",  "0.85",
     "fact_connected_inventory"),
    ("WoS KPI",              "[Avg Weeks of Supply]",       "WoS Target",           "12",    "#,##0.0", "lower",  "12",    "18",
     "fact_in_season"),
]


def strip_measures(tmdl: str, names: list[str]) -> str:
    """Remove existing `measure '<name>'` blocks so re-pushing is idempotent."""
    out, lines = [], tmdl.split("\n")
    i = 0
    while i < len(lines):
        ln = lines[i]
        stripped = ln.lstrip("\t")
        if stripped.startswith("measure "):
            rest = stripped[len("measure "):].strip()
            if rest.startswith("'"):
                end = rest.find("'", 1)
                mname = rest[1:end] if end > 0 else ""
            else:
                mname = ""
                for ch in rest:
                    if ch in (" ", "="):
                        break
                    mname += ch
            if mname in names:
                i += 1
                while i < len(lines):
                    nxt = lines[i]
                    n_strip = nxt.lstrip("\t")
                    if nxt.startswith("\t") and not nxt.startswith("\t\t"):
                        if (n_strip.startswith("measure ") or n_strip.startswith("column ")
                                or n_strip.startswith("partition ") or n_strip.startswith("annotation ")
                                or n_strip.startswith("hierarchy ")):
                            break
                    if not nxt.startswith("\t") and nxt.strip():
                        break
                    i += 1
                continue
        out.append(ln)
        i += 1
    return "\n".join(out)


def render_target(name, value, fmt):
    nm = f"'{name}'" if any(c in name for c in " %()/+-") else name
    return "\n".join([
        f"\tmeasure {nm} = {value}",
        f"\t\tformatString: {fmt}",
        f"\t\tlineageTag: {uuid.uuid4()}",
        f"\t\tdisplayFolder: KPI Targets",
        "",
    ])


def render_kpi(kpi_name, base_ref, target_name, fmt, direction, green_t, yellow_t):
    op_g = ">=" if direction == "higher" else "<="
    op_y = ">=" if direction == "higher" else "<="
    body = (
        f"\t\t\t\tVAR _v = {base_ref}\n"
        f"\t\t\t\tRETURN SWITCH ( TRUE (), _v {op_g} {green_t}, 1, "
        f"_v {op_y} {yellow_t}, 0, -1 )"
    )
    kn = f"'{kpi_name}'" if any(c in kpi_name for c in " %()/+-") else kpi_name
    tn = f"'{target_name}'" if any(c in target_name for c in " %()/+-") else target_name
    return "\n".join([
        f"\tmeasure {kn} = {base_ref}",
        f"\t\tformatString: {fmt}",
        f"\t\tlineageTag: {uuid.uuid4()}",
        f"\t\tdisplayFolder: KPIs",
        "",
        f"\t\tkpi",
        f"\t\t\ttargetExpression: [{target_name}]",
        f"\t\t\tstatusGraphic: \"Traffic Light - Single\"",
        f"\t\t\tstatusExpression =",
        body,
        "",
    ])


def main():
    print("Fetching ctc_merch TMDL...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/semanticModels/{MODEL}/getDefinition?format=TMDL",
                   body={})
    if s == 202:
        loc = h.get("Location") or h.get("location")
        ok, result_url = poll(loc)
        if not ok:
            return
        sr, hr, br = call("GET", result_url)
        payload = json.loads(br)
    else:
        payload = json.loads(b)
    parts = {p["path"]: base64.b64decode(p["payload"]).decode("utf-8", errors="replace")
             for p in payload["definition"]["parts"]}
    print(f"  Loaded {len(parts)} parts")

    # Group new measures by host table
    by_table: dict[str, list[str]] = {}
    names_to_strip: list[str] = []
    for spec in KPI_SPECS:
        kpi_n, base_ref, tgt_n, tgt_v, fmt, dr, gt, yt, host = spec
        names_to_strip.extend([kpi_n, tgt_n])
        by_table.setdefault(host, []).append(spec)

    for host, specs in by_table.items():
        path = f"definition/tables/{host}.tmdl"
        if path not in parts:
            print(f"  WARNING: {path} not in TMDL parts; skipping {host}")
            continue
        tmdl = strip_measures(parts[path], names_to_strip)
        block = ""
        for spec in specs:
            kpi_n, base_ref, tgt_n, tgt_v, fmt, dr, gt, yt, _ = spec
            block += render_target(tgt_n, tgt_v, fmt)
            block += render_kpi(kpi_n, base_ref, tgt_n, fmt, dr, gt, yt)
        idx = tmdl.find("\tpartition ")
        if idx < 0:
            print(f"  WARNING: no partition found in {host}, skipping")
            continue
        parts[path] = tmdl[:idx] + block + tmdl[idx:]
        print(f"  Injected {len(specs)} KPI definitions into {host}")

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
    print("\n  KPIs pushed.")


if __name__ == "__main__":
    main()
