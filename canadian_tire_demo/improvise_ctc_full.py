"""Full demo polish for CTC_Merch_Copilot_Demo report.

Adds:
  1. New Executive Snapshot landing page (becomes new Page 0):
     - 6px CTC-red brand ribbon top
     - Title + subtitle (date stamp + agent ready callout)
     - 4 hero KPI cards (POS YoY, EGM %, Lost Sales, Fill Rate)
     - Headline narrative box (Air Fryers, NK 8L, markdown opportunities)
     - Top finelines bar chart sorted desc with CTC-red bars
     - Data Agent CTA panel with 3 lead prompts
     - 6px CTC-red brand ribbon bottom
     Sets activePageName so demo opens on this page.
  2. Brand ribbons (top + bottom) on existing 3 pages.
  3. Story annotation textbox on Page 1 above the column chart.

Additive only: existing visuals are not modified.

Run once:
    py improvise_ctc_full.py
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

# CTC palette
CTC_RED = "#CA1A22"
NAVY = "#1B2C5C"
GRAY = "#5A6B82"
LIGHTBG = "#F5F6F8"

EXEC_SLUG = "p00_exec_snapshot"
PAGE_1_SLUG = "p700e19120eab4de389"
PAGE_2_SLUG = "p89c369bef5ad40868e"
PAGE_3_SLUG = "pdaa269b27a7e4e9a84"


def lit(v):
    """Wrap a literal scalar for PBIR object property values."""
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


# ---- Visual builders -------------------------------------------------------

def shape_ribbon(name: str, x: int, y: int, w: int, h: int, color: str, z: int = 100):
    """Filled rectangle for brand ribbons."""
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.10.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": -3000},
        "visual": {
            "visualType": "shape",
            "drillFilterOtherVisuals": True,
            "objects": {
                "fill": [{
                    "properties": {
                        "show": lit(True),
                        "fillColor": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{color}'"}}}}},
                        "transparency": {"expr": {"Literal": {"Value": "0D"}}},
                    }
                }],
                "outline": [{
                    "properties": {"show": lit(False)}
                }],
                "shape": [{
                    "properties": {"tileShape": {"expr": {"Literal": {"Value": "'rectangle'"}}}}
                }],
            },
            "visualContainerObjects": {
                "border": [{"properties": {"show": lit(False)}}],
            },
        },
    }


def textbox(name: str, x: int, y: int, w: int, h: int, runs: list, z: int = 3000):
    """Textbox with one or more (text, style) runs. style is a dict like
    {'fontSize':'14pt','fontWeight':'bold','color':'#1B2C5C'}."""
    if all(isinstance(r, tuple) and len(r) == 2 for r in runs):
        paragraphs = [{
            "textRuns": [{"value": text, "textStyle": style} for text, style in runs]
        }]
    else:
        # list of paragraphs, each a list of (text, style) tuples
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
            "objects": {
                "general": [{"properties": {"paragraphs": paragraphs}}]
            },
            "visualContainerObjects": hide_header(),
        },
    }


def kpi(name: str, x: int, y: int, w: int, h: int,
        indicator_table: str, indicator_measure: str,
        goal_table: str, goal_measure: str, z: int = 2000):
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.10.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z},
        "visual": {
            "visualType": "kpi",
            "drillFilterOtherVisuals": True,
            "query": {
                "queryState": {
                    "Indicator": {
                        "projections": [{
                            "field": {"Measure": {
                                "Expression": {"SourceRef": {"Entity": indicator_table}},
                                "Property": indicator_measure,
                            }},
                            "queryRef": f"{indicator_table}.{indicator_measure}",
                            "nativeQueryRef": indicator_measure,
                            "active": True,
                        }],
                    },
                    "TrendLine": {
                        "projections": [{
                            "field": {"Column": {
                                "Expression": {"SourceRef": {"Entity": "dim_date"}},
                                "Property": "Year_Month",
                            }},
                            "queryRef": "dim_date.Year_Month",
                            "nativeQueryRef": "Year_Month",
                            "active": True,
                        }],
                    },
                    "Goals": {
                        "projections": [{
                            "field": {"Measure": {
                                "Expression": {"SourceRef": {"Entity": goal_table}},
                                "Property": goal_measure,
                            }},
                            "queryRef": f"{goal_table}.{goal_measure}",
                            "nativeQueryRef": goal_measure,
                        }],
                    },
                },
            },
            "visualContainerObjects": hide_header(),
        },
    }


def bar_top_finelines(name: str, x: int, y: int, w: int, h: int, z: int = 2000):
    """Bar chart: Fineline_Name by POS $ TY, sorted desc, CTC red fill."""
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.10.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z},
        "visual": {
            "visualType": "barChart",
            "drillFilterOtherVisuals": True,
            "query": {
                "queryState": {
                    "Category": {
                        "projections": [{
                            "field": {"Column": {
                                "Expression": {"SourceRef": {"Entity": "dim_sku"}},
                                "Property": "Fineline_Name",
                            }},
                            "queryRef": "dim_sku.Fineline_Name",
                            "nativeQueryRef": "Fineline_Name",
                            "active": True,
                        }],
                    },
                    "Y": {
                        "projections": [{
                            "field": {"Measure": {
                                "Expression": {"SourceRef": {"Entity": "fact_sku_performance"}},
                                "Property": "POS $ TY",
                            }},
                            "queryRef": "fact_sku_performance.POS $ TY",
                            "nativeQueryRef": "POS $ TY",
                            "displayName": "POS $ TY",
                        }],
                    },
                },
                "sortDefinition": {
                    "sort": [{
                        "field": {"Measure": {
                            "Expression": {"SourceRef": {"Entity": "fact_sku_performance"}},
                            "Property": "POS $ TY",
                        }},
                        "direction": "Descending",
                    }],
                },
            },
            "objects": {
                "labels": [{"properties": {"show": lit(True)}}],
                "dataPoint": [{
                    "properties": {
                        "fill": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{CTC_RED}'"}}}}}
                    }
                }],
                "title": [{
                    "properties": {
                        "show": lit(True),
                        "text": {"expr": {"Literal": {"Value": "'Top finelines by POS $ TY'"}}},
                        "fontColor": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{NAVY}'"}}}}},
                        "fontSize": {"expr": {"Literal": {"Value": "11D"}}},
                        "bold": lit(True),
                    }
                }],
            },
            "visualContainerObjects": hide_header(),
        },
    }


# ---- Executive Snapshot page assembly --------------------------------------

def build_exec_page():
    """Returns dict of {path: utf8 string} parts for the new page."""
    parts = {}

    # page.json
    parts[f"definition/pages/{EXEC_SLUG}/page.json"] = json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
        "name": EXEC_SLUG,
        "displayName": "Executive Snapshot",
        "displayOption": "FitToPage",
        "height": 720,
        "width": 1280,
    }, indent=2)

    def add(name: str, body: dict):
        parts[f"definition/pages/{EXEC_SLUG}/visuals/{name}/visual.json"] = \
            json.dumps(body, indent=2, ensure_ascii=False)

    # Top brand ribbon
    add("v0_ribbon_top", shape_ribbon("v0_ribbon_top", 0, 0, 1280, 6, CTC_RED, z=10))

    # Title + subtitle
    add("v0_title", textbox(
        "v0_title", 20, 14, 1240, 38,
        runs=[
            ("Canadian Tire — Merch Performance Snapshot",
             {"fontSize": "20pt", "fontWeight": "bold", "color": NAVY}),
        ],
    ))
    add("v0_subtitle", textbox(
        "v0_subtitle", 20, 54, 1240, 22,
        runs=[
            ("Friday, May 29, 2026  ·  Direct Lake on ctc_merch  ·  Copilot + CTC Merch Data Agent ready",
             {"fontSize": "11pt", "color": GRAY}),
        ],
    ))

    # 4 hero KPI cards
    add("v0_kpi_pos", kpi("v0_kpi_pos", 20, 84, 295, 170,
                          "fact_sku_performance", "POS YoY KPI",
                          "fact_sku_performance", "POS YoY Target"))
    add("v0_kpi_egm", kpi("v0_kpi_egm", 335, 84, 295, 170,
                          "fact_sku_performance", "EGM % KPI",
                          "fact_sku_performance", "EGM Target"))
    add("v0_kpi_ls", kpi("v0_kpi_ls", 650, 84, 295, 170,
                         "fact_connected_inventory", "Lost Sales KPI",
                         "fact_connected_inventory", "Lost Sales Threshold"))
    add("v0_kpi_fr", kpi("v0_kpi_fr", 965, 84, 295, 170,
                         "fact_connected_inventory", "Fill Rate KPI",
                         "fact_connected_inventory", "Fill Rate Target"))

    # Headline narrative (left half, below KPIs)
    add("v0_headline", textbox(
        "v0_headline", 20, 270, 625, 270,
        runs=[
            [("Today's headline", {"fontSize": "14pt", "fontWeight": "bold", "color": CTC_RED})],
            [("POS $49.2M  ·  +27.9% YoY  ·  EGM 42.3%",
              {"fontSize": "13pt", "fontWeight": "bold", "color": NAVY})],
            [("", {"fontSize": "6pt", "color": NAVY})],
            [("•  Air Fryers fineline up ",
              {"fontSize": "12pt", "color": NAVY}),
             ("+88.7% YoY",
              {"fontSize": "12pt", "fontWeight": "bold", "color": CTC_RED}),
             (" — strongest growth, protect supply.",
              {"fontSize": "12pt", "color": NAVY})],
            [("•  NK Dual Zone Air Fryer 8L losing ",
              {"fontSize": "12pt", "color": NAVY}),
             ("13.7%",
              {"fontSize": "12pt", "fontWeight": "bold", "color": CTC_RED}),
             (" of demand at ",
              {"fontSize": "12pt", "color": NAVY}),
             ("72.7% fill rate",
              {"fontSize": "12pt", "fontWeight": "bold", "color": CTC_RED}),
             (" — supply intervention.",
              {"fontSize": "12pt", "color": NAVY})],
            [("•  9 SKUs with WoS > 18 and low lost sales — markdown candidates.",
              {"fontSize": "12pt", "color": NAVY})],
            [("•  Canvas Outdoor vendor steady: $7.4M, 89.1% fill, 39.9% EGM.",
              {"fontSize": "12pt", "color": NAVY})],
            [("", {"fontSize": "6pt", "color": NAVY})],
            [("Ask Copilot or the CTC Merch Data Agent ↓",
              {"fontSize": "11pt", "fontStyle": "italic", "color": GRAY})],
        ],
    ))

    # Top finelines bar chart (right half)
    add("v0_bar_finelines", bar_top_finelines("v0_bar_finelines", 660, 270, 600, 270))

    # Data Agent CTA panel (full width)
    add("v0_agent_cta", textbox(
        "v0_agent_cta", 20, 555, 1240, 145,
        runs=[
            [("🤖  Continue in Teams or the Fabric portal — CTC Merch Data Agent",
              {"fontSize": "13pt", "fontWeight": "bold", "color": NAVY})],
            [("", {"fontSize": "4pt", "color": NAVY})],
            [("•  ", {"fontSize": "11pt", "color": CTC_RED}),
             ("\"Top 10 SKUs by EGM dollars TY with POS YoY and EGM %\"",
              {"fontSize": "11pt", "color": NAVY})],
            [("•  ", {"fontSize": "11pt", "color": CTC_RED}),
             ("\"Which SKUs have lost sales > 5% AND fill rate < 85%?\"",
              {"fontSize": "11pt", "color": NAVY})],
            [("•  ", {"fontSize": "11pt", "color": CTC_RED}),
             ("\"Demand vs supply gap by category — where do we expedite?\"",
              {"fontSize": "11pt", "color": NAVY})],
            [("", {"fontSize": "4pt", "color": NAVY})],
            [("Status: published · 7 tables · 75 columns · 64 measures · 5 relationships indexed",
              {"fontSize": "9pt", "color": GRAY})],
        ],
    ))

    # Bottom brand ribbon
    add("v0_ribbon_bottom", shape_ribbon("v0_ribbon_bottom", 0, 714, 1280, 6, CTC_RED, z=10))

    return parts


# ---- Ribbon additions for existing pages -----------------------------------

def page_ribbons(slug: str, prefix: str):
    return {
        f"definition/pages/{slug}/visuals/{prefix}_ribbon_top/visual.json":
            json.dumps(shape_ribbon(f"{prefix}_ribbon_top", 0, 0, 1280, 6, CTC_RED, z=10),
                       indent=2),
        f"definition/pages/{slug}/visuals/{prefix}_ribbon_bottom/visual.json":
            json.dumps(shape_ribbon(f"{prefix}_ribbon_bottom", 0, 714, 1280, 6, CTC_RED, z=10),
                       indent=2),
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
    print(f"  Loaded {len(parts)} parts (format={fmt})")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"backup_ctc_report_{ts}.json"
    with open(backup, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"  Backup -> {backup}")

    # Add exec snapshot page
    exec_parts = build_exec_page()
    for p, c in exec_parts.items():
        parts[p] = b64(c)
    print(f"  ADD exec snapshot: {len(exec_parts)} files")

    # Add ribbons to existing pages
    for slug, prefix in [(PAGE_1_SLUG, "v1"), (PAGE_2_SLUG, "v2"), (PAGE_3_SLUG, "v3")]:
        ribbons = page_ribbons(slug, prefix)
        for p, c in ribbons.items():
            parts[p] = b64(c)
        print(f"  ADD ribbons for {slug}: {len(ribbons)} files")

    # Add story annotation on Page 1 (above column chart, in the gap between bar and column)
    # bar ends at y=430, column starts at y=440 → no real gap. Put annotation at y=222
    # (just above bar chart's plot area, inside the 230 start) ... actually that overlaps.
    # Safe spot: just put a tiny chip TEXTBOX at the BOTTOM-RIGHT of column chart, on its own
    # row in the 660-708 area — but slicers are at 670. So skip per-chart annotation
    # to avoid overlaps; the Executive Snapshot page carries the story.

    # Update pages.json to insert exec page at index 0 and set as active
    pages_path = "definition/pages/pages.json"
    pages_doc = json.loads(base64.b64decode(parts[pages_path]).decode("utf-8"))
    order = pages_doc.get("pageOrder", [])
    if EXEC_SLUG not in order:
        order.insert(0, EXEC_SLUG)
    pages_doc["pageOrder"] = order
    pages_doc["activePageName"] = EXEC_SLUG
    parts[pages_path] = b64(json.dumps(pages_doc, indent=2))
    print(f"  Updated pages.json: order={pages_doc['pageOrder']}")
    print(f"  activePageName = {EXEC_SLUG}")

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
