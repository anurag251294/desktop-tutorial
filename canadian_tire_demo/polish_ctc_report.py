"""Demo polish for CTC_Merch_Copilot_Demo report.

Pages 2 and 3 lack the title + subtitle band that Page 1 has, which makes them
look bare during the demo. This script adds matching v_hdr_* and v_sub_*
textbox visuals at x=20, y=14 (header) and x=20, y=50 (subtitle) with the
same Segoe UI Semibold 16pt navy styling.

Additive only: existing visuals are NOT touched. KPI/card rows start at y=84
on all 3 pages, so headers slot above without overlap.

Run once:
    py polish_ctc_report.py
"""
from __future__ import annotations

import base64
import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime

AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"
WS = "9e29a8fd-9462-4c18-b691-f77a631e89ea"
REPORT = "b41bcf36-87e4-4834-818c-c6b266f3d5bb"

NAVY = "#1B2C5C"
GRAY = "#5A6B82"

PAGE_2_SLUG = "p89c369bef5ad40868e"
PAGE_3_SLUG = "pdaa269b27a7e4e9a84"

ADDITIONS = [
    (PAGE_2_SLUG, "v_hdr_InSeason", "Canadian Tire — Merch Performance | In-Season Demand vs Supply", True),
    (PAGE_2_SLUG, "v_sub_InSeason", "Spring/Summer S1 — Where is forecast running ahead of supply? Where do we expedite?", False),
    (PAGE_3_SLUG, "v_hdr_Connected", "Canadian Tire — Merch Performance | Connected Inventory Health", True),
    (PAGE_3_SLUG, "v_sub_Connected", "Consumer-side supply chain — lost sales, vendor fill rate, R8 demand velocity", False),
]


def textbox_visual(name: str, text: str, is_header: bool):
    """Mirror the v_hdr_Overview / v_sub_Overview shape exactly."""
    if is_header:
        y = 14
        h = 38
        style = {"fontSize": "16pt", "fontWeight": "bold", "color": NAVY}
    else:
        y = 50
        h = 24
        style = {"fontSize": "11pt", "color": GRAY}

    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.10.0/schema.json",
        "name": name,
        "position": {"x": 20, "y": y, "z": 0, "height": h, "width": 1240, "tabOrder": 0},
        "visual": {
            "visualType": "textbox",
            "drillFilterOtherVisuals": True,
            "objects": {
                "general": [{
                    "properties": {
                        "paragraphs": [{
                            "textRuns": [{"value": text, "textStyle": style}],
                        }]
                    }
                }]
            },
            "visualContainerObjects": {
                "visualHeader": [{
                    "properties": {
                        "showCopyVisualImageButton": {"expr": {"Literal": {"Value": "false"}}},
                        "showFilterRestatementButton": {"expr": {"Literal": {"Value": "false"}}},
                        "showFocusModeButton": {"expr": {"Literal": {"Value": "false"}}},
                        "showPinButton": {"expr": {"Literal": {"Value": "false"}}},
                    }
                }]
            },
        },
    }


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
            print(f"  FAILED: {b[:1200]}")
            return False, None
    return False, None


def b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def main():
    print("Fetching CTC report definition...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/reports/{REPORT}/getDefinition",
                   body={})
    if s == 202:
        ok, result_url = poll(h.get("Location") or h.get("location"))
        if not ok:
            return
        payload = json.loads(call("GET", result_url)[2])
    else:
        payload = json.loads(b)
    parts = {p["path"]: p["payload"] for p in payload["definition"]["parts"]}
    fmt = payload["definition"].get("format", "PBIR")
    print(f"  Loaded {len(parts)} parts (format={fmt})")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"backup_ctc_report_{ts}.json"
    with open(backup, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"  Backup -> {backup}")

    # Add textbox visuals
    for slug, name, text, is_header in ADDITIONS:
        path = f"definition/pages/{slug}/visuals/{name}/visual.json"
        if path in parts:
            print(f"  SKIP {path} (already exists)")
            continue
        body = textbox_visual(name, text, is_header)
        parts[path] = b64(json.dumps(body, indent=2, ensure_ascii=False))
        print(f"  ADD  {path}")

    # Push
    payload_parts = [{"path": p, "payload": pl, "payloadType": "InlineBase64"}
                     for p, pl in parts.items()]
    print(f"\nPOSTing updateDefinition with {len(payload_parts)} parts...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/reports/{REPORT}/updateDefinition",
                   body={"definition": {"format": fmt, "parts": payload_parts}})
    print(f"  status={s}")
    if s == 202:
        ok, _ = poll(h.get("Location") or h.get("location"))
        if ok:
            print(f"\n  OK -> https://msit.powerbi.com/groups/{WS}/reports/{REPORT}")
        else:
            print("  update failed; restore with backup")
    elif s in (200, 201):
        print(f"\n  OK -> https://msit.powerbi.com/groups/{WS}/reports/{REPORT}")
    else:
        print(f"  ERROR: {b[:1500]}")


if __name__ == "__main__":
    main()
