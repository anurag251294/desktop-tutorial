"""Layout + look-and-feel polish for CTC_Merch_Copilot_Demo.

Adds:
  - Soft page background tint (#FAFBFC) on all 4 pages
  - White card panels with 1px border + subtle drop shadow BEHIND every KPI,
    chart, narrative, and callout textbox — material-card feel
  - Section labels with CTC-red bullet dot on the Executive Snapshot page
  - Small brand footer textbox in the bottom-right of every page
    ("Microsoft Canada · ctc_merch · 2026-05-29 demo")

Additive only: existing visuals are not modified. Card panels go at z=50
(behind existing content), section labels and footers at z=3500 (above).

Run once:
    py polish_layout_v2.py
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

CTC_RED = "#CA1A22"
NAVY = "#1B2C5C"
GRAY = "#5A6B82"
BG_TINT = "#FAFBFC"
PANEL_BG = "#FFFFFF"
BORDER = "#E5E7EB"

EXEC_SLUG = "p00_exec_snapshot"
PAGE_1_SLUG = "p700e19120eab4de389"
PAGE_2_SLUG = "p89c369bef5ad40868e"
PAGE_3_SLUG = "pdaa269b27a7e4e9a84"


# ---- PBIR helpers ----------------------------------------------------------

def lit(v):
    if isinstance(v, bool):
        return {"expr": {"Literal": {"Value": "true" if v else "false"}}}
    if isinstance(v, (int, float)):
        return {"expr": {"Literal": {"Value": f"{v}D"}}}
    if isinstance(v, str):
        return {"expr": {"Literal": {"Value": f"'{v}'"}}}
    raise ValueError(v)


def hide_header():
    return {
        "visualHeader": [{
            "properties": {
                k: lit(False) for k in (
                    "showCopyVisualImageButton",
                    "showFilterRestatementButton",
                    "showFocusModeButton",
                    "showPinButton",
                )
            }
        }]
    }


def card_panel(name: str, x: int, y: int, w: int, h: int, pad: int = 6, z: int = 50,
               left_accent: str | None = None):
    """White card with light border + subtle drop shadow, sized to wrap a visual.

    If left_accent is provided, draws a 3px colored stripe on the left edge
    (using fillColor on a child shape — easier: caller can add a separate small
    shape for the accent).
    """
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.10.0/schema.json",
        "name": name,
        "position": {
            "x": x - pad, "y": y - pad,
            "z": z,
            "height": h + 2 * pad, "width": w + 2 * pad,
            "tabOrder": -1000,
        },
        "visual": {
            "visualType": "shape",
            "drillFilterOtherVisuals": True,
            "objects": {
                "fill": [{
                    "properties": {
                        "show": lit(True),
                        "fillColor": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{PANEL_BG}'"}}}}},
                        "transparency": {"expr": {"Literal": {"Value": "0D"}}},
                    }
                }],
                "outline": [{"properties": {"show": lit(False)}}],
                "shape": [{
                    "properties": {
                        "tileShape": {"expr": {"Literal": {"Value": "'rectangle'"}}}
                    }
                }],
            },
            "visualContainerObjects": {
                "border": [{
                    "properties": {
                        "show": lit(True),
                        "radius": {"expr": {"Literal": {"Value": "6M"}}},
                        "color": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{BORDER}'"}}}}},
                    }
                }],
                "dropShadow": [{
                    "properties": {
                        "show": lit(True),
                        "preset": {"expr": {"Literal": {"Value": "'Custom'"}}},
                        "shadowBlur": {"expr": {"Literal": {"Value": "5M"}}},
                        "shadowDistance": {"expr": {"Literal": {"Value": "1M"}}},
                        "shadowSpread": {"expr": {"Literal": {"Value": "0M"}}},
                        "transparency": {"expr": {"Literal": {"Value": "90M"}}},
                    }
                }],
            },
        },
    }


def red_dot(name: str, x: int, y: int, size: int = 8, z: int = 3500):
    """Small CTC red dot (used as section-label bullet)."""
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.10.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": z, "height": size, "width": size, "tabOrder": z},
        "visual": {
            "visualType": "shape",
            "drillFilterOtherVisuals": True,
            "objects": {
                "fill": [{
                    "properties": {
                        "show": lit(True),
                        "fillColor": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{CTC_RED}'"}}}}},
                    }
                }],
                "outline": [{"properties": {"show": lit(False)}}],
                "shape": [{
                    "properties": {"tileShape": {"expr": {"Literal": {"Value": "'oval'"}}}}
                }],
            },
            "visualContainerObjects": {
                "border": [{"properties": {"show": lit(False)}}],
            },
        },
    }


def textbox(name: str, x: int, y: int, w: int, h: int, runs: list, z: int = 3500):
    if all(isinstance(r, tuple) and len(r) == 2 for r in runs):
        paragraphs = [{"textRuns": [{"value": t, "textStyle": s} for t, s in runs]}]
    else:
        paragraphs = [
            {"textRuns": [{"value": t, "textStyle": s} for t, s in para]}
            for para in runs
        ]
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.10.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z},
        "visual": {
            "visualType": "textbox",
            "drillFilterOtherVisuals": True,
            "objects": {"general": [{"properties": {"paragraphs": paragraphs}}]},
            "visualContainerObjects": hide_header(),
        },
    }


# ---- Card-panel positions per page -----------------------------------------
# (Tuples of (name_suffix, x, y, w, h) for each existing visual that should
# get a card panel behind it.)

PANEL_POSITIONS = {
    EXEC_SLUG: [
        # Row 1: 4 hero KPIs
        ("p_kpi_1", 20, 84, 295, 170),
        ("p_kpi_2", 335, 84, 295, 170),
        ("p_kpi_3", 650, 84, 295, 170),
        ("p_kpi_4", 965, 84, 295, 170),
        # Row 2: narrative + bar chart
        ("p_narrative", 20, 270, 625, 270),
        ("p_bar", 660, 270, 600, 270),
        # Row 3: Data Agent CTA
        ("p_agent_cta", 20, 555, 1240, 145),
    ],
    PAGE_1_SLUG: [
        ("p_kpi_1", 20, 84, 295, 130),
        ("p_kpi_2", 335, 84, 295, 130),
        ("p_kpi_3", 650, 84, 295, 130),
        ("p_kpi_4", 965, 84, 295, 130),
        ("p_narrative", 20, 230, 295, 200),
        ("p_bar", 445, 230, 815, 200),
        ("p_callout", 20, 440, 415, 220),
        ("p_col", 445, 440, 815, 220),
    ],
    PAGE_2_SLUG: [
        ("p_kpi_1", 20, 84, 295, 130),
        ("p_kpi_2", 335, 84, 295, 130),
        ("p_kpi_3", 650, 84, 295, 130),
        ("p_kpi_4", 965, 84, 295, 130),
        ("p_narrative", 20, 230, 295, 250),
        ("p_scatter", 445, 230, 815, 250),
        ("p_callout", 20, 490, 415, 170),
        ("p_col_inv", 445, 490, 815, 170),
    ],
    PAGE_3_SLUG: [
        ("p_kpi_1", 20, 84, 295, 130),
        ("p_kpi_2", 335, 84, 295, 130),
        ("p_kpi_3", 650, 84, 295, 130),
        ("p_kpi_4", 965, 84, 295, 130),
        ("p_narrative", 20, 230, 295, 250),
        ("p_bar_fr", 445, 230, 815, 250),
        ("p_callout", 20, 490, 415, 170),
        ("p_col_r8", 445, 490, 815, 170),
    ],
}


# ---- Section labels on Executive Snapshot ----------------------------------

EXEC_SECTION_LABELS = [
    # (y, text)
    (74, "HERO METRICS"),
    (260, "TODAY'S STORY"),
    (545, "CONTINUE WITH THE CTC MERCH DATA AGENT"),
]


# ---- Brand footer (bottom-right of every page) -----------------------------

FOOTER_TEXT = "Microsoft Canada  ·  ctc_merch  ·  2026-05-29 demo"


# ---- Page background -------------------------------------------------------

def set_page_background(page_doc: dict):
    """Add a soft background tint to the page via page.json objects.background."""
    objs = page_doc.setdefault("objects", {})
    objs["background"] = [{
        "properties": {
            "color": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{BG_TINT}'"}}}}},
            "transparency": {"expr": {"Literal": {"Value": "0D"}}},
        }
    }]
    return page_doc


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
    for _ in range(120):
        time.sleep(2)
        s, h, b = call("GET", loc)
        try:
            st = json.loads(b).get("status")
        except Exception:
            st = None
        if st == "Succeeded":
            return True, loc.rstrip("/") + "/result"
        if st == "Failed":
            print(f"  FAILED: {b[:1500]}")
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
    print(f"  Loaded {len(parts)} parts")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"backup_ctc_report_{ts}.json"
    with open(backup, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"  Backup -> {backup}")

    added = 0

    # 1. Card panels behind each existing visual on each page
    for slug, panels in PANEL_POSITIONS.items():
        for name_suffix, x, y, w, hh in panels:
            name = f"{slug[:8]}_{name_suffix}"
            path = f"definition/pages/{slug}/visuals/{name}/visual.json"
            if path in parts:
                continue
            parts[path] = b64(json.dumps(card_panel(name, x, y, w, hh),
                                         indent=2, ensure_ascii=False))
            added += 1
    print(f"  Added {added} card panels")

    # 2. Page background tint on all 4 pages
    for slug in (EXEC_SLUG, PAGE_1_SLUG, PAGE_2_SLUG, PAGE_3_SLUG):
        page_path = f"definition/pages/{slug}/page.json"
        page_doc = json.loads(base64.b64decode(parts[page_path]).decode("utf-8"))
        page_doc = set_page_background(page_doc)
        parts[page_path] = b64(json.dumps(page_doc, indent=2))
    print(f"  Set page background tint on 4 pages")

    # 3. Section labels on Executive Snapshot (red dot + small uppercase text)
    for i, (y, label) in enumerate(EXEC_SECTION_LABELS, 1):
        # red dot
        dot_path = f"definition/pages/{EXEC_SLUG}/visuals/v0_sect_dot_{i}/visual.json"
        parts[dot_path] = b64(json.dumps(red_dot(f"v0_sect_dot_{i}", 20, y, 8),
                                         indent=2))
        # label
        lab_path = f"definition/pages/{EXEC_SLUG}/visuals/v0_sect_lbl_{i}/visual.json"
        parts[lab_path] = b64(json.dumps(textbox(
            f"v0_sect_lbl_{i}", 36, y - 4, 1200, 18,
            runs=[(label, {"fontSize": "9pt", "fontWeight": "bold", "color": GRAY})],
        ), indent=2, ensure_ascii=False))
    print(f"  Added {len(EXEC_SECTION_LABELS)} section labels on Exec Snapshot")

    # 4. Brand footer textbox bottom-right of every page (above the bottom ribbon)
    for slug, prefix in [(EXEC_SLUG, "v0"), (PAGE_1_SLUG, "v1"),
                         (PAGE_2_SLUG, "v2"), (PAGE_3_SLUG, "v3")]:
        name = f"{prefix}_footer_brand"
        path = f"definition/pages/{slug}/visuals/{name}/visual.json"
        if path in parts:
            continue
        parts[path] = b64(json.dumps(textbox(
            name, 760, 695, 500, 16,
            runs=[(FOOTER_TEXT, {"fontSize": "8pt", "color": GRAY})],
            z=3500,
        ), indent=2, ensure_ascii=False))
    print(f"  Added brand footer on 4 pages")

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
        print(f"  ERROR: {b[:2000]}")


if __name__ == "__main__":
    main()
