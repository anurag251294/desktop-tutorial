"""Apply an Interac brand theme to HR_demo_report so both pages share a
consistent color palette (navy / orange / gold / grey) on top of the existing
base theme. Backs up the report definition before pushing.

  - Registers StaticResources/RegisteredResources/InteracBrand.json
  - Adds a 'customTheme' entry under themeCollection in definition/report.json
  - Adds a RegisteredResources package alongside SharedResources

Run once:
    py apply_interac_theme.py
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
WS = "de6a7e47-474b-4354-87e7-26b8d741f015"
REPORT = "d28c79f7-5088-4d95-a3c6-c4a0dae093d9"

THEME_NAME = "InteracBrand"
THEME_FILE = "InteracBrand.json"

# Interac brand palette
NAVY = "#1B2C5C"
ORANGE = "#F58220"
GOLD = "#FFC72C"
GREY = "#5A6B82"
GREEN = "#3E7C46"
RED = "#D14D52"

INTERAC_THEME = {
    "name": THEME_NAME,
    "dataColors": [
        NAVY, ORANGE, GOLD, GREY, GREEN, "#00A3B5", "#7A8FA8", RED,
        "#C7E0F4", "#E7B5B5", "#9B6BCC", "#F4A261",
    ],
    "background": "#FFFFFF",
    "foreground": NAVY,
    "foregroundNeutralSecondary": GREY,
    "foregroundNeutralTertiary": "#A6B2C2",
    "backgroundLight": "#F7F8FB",
    "backgroundNeutral": "#E5E9F0",
    "tableAccent": ORANGE,
    "good": GREEN,
    "neutral": GOLD,
    "bad": RED,
    "maximum": NAVY,
    "center": GOLD,
    "minimum": ORANGE,
    "null": "#E5E5E5",
    "hyperlink": NAVY,
    "visitedHyperlink": NAVY,
    "textClasses": {
        "title":   {"fontSize": 14, "fontFace": "Segoe UI Semibold", "color": NAVY},
        "header":  {"fontSize": 12, "fontFace": "Segoe UI Semibold", "color": NAVY},
        "label":   {"fontSize": 10, "fontFace": "Segoe UI",          "color": GREY},
        "callout": {"fontSize": 24, "fontFace": "Segoe UI",          "color": NAVY},
    },
    "visualStyles": {
        "*": {
            "*": {
                "title": [{
                    "fontColor": {"solid": {"color": NAVY}},
                    "fontSize": 11, "bold": True, "alignment": "left",
                }],
                "border": [{
                    "color": {"solid": {"color": "#E5E9F0"}},
                    "radius": 4, "show": True,
                }],
                "background": [{
                    "color": {"solid": {"color": "#FFFFFF"}},
                    "show": True, "transparency": 0,
                }],
            }
        },
        "kpi": {
            "*": {
                "indicator": [{"color": {"solid": {"color": NAVY}}, "fontSize": 24}],
                "trendline": [{"color": {"solid": {"color": ORANGE}}}],
                "goals":     [{"color": {"solid": {"color": GREY}}}],
            }
        },
        "gauge": {
            "*": {
                "dataPoint": [{"fill": {"solid": {"color": NAVY}}}],
                "target":    [{"color": {"solid": {"color": ORANGE}}}],
                "calloutValue": [{"color": {"solid": {"color": NAVY}}, "fontSize": 22}],
            }
        },
        "barChart": {
            "*": {
                "dataPoint": [{"fill": {"solid": {"color": ORANGE}}}],
            }
        },
        "clusteredBarChart": {
            "*": {
                "dataPoint": [{"fill": {"solid": {"color": ORANGE}}}],
            }
        },
        "columnChart": {
            "*": {
                "dataPoint": [{"fill": {"solid": {"color": ORANGE}}}],
            }
        },
        "lineChart": {
            "*": {
                "lineStyles": [{"strokeWidth": 3, "showMarker": True}],
                "dataPoint":  [{"defaultColor": {"solid": {"color": ORANGE}}}],
            }
        },
        "areaChart": {
            "*": {
                "dataPoint": [{"defaultColor": {"solid": {"color": ORANGE}}}],
                "lineStyles": [{"strokeWidth": 2}],
            }
        },
        "multiRowCard": {
            "*": {
                "dataLabels": [{"color": {"solid": {"color": NAVY}}, "fontSize": 18, "bold": True}],
                "categoryLabels": [{"color": {"solid": {"color": GREY}}, "fontSize": 9}],
                "cardTitle": [{"color": {"solid": {"color": NAVY}}, "fontSize": 11, "bold": True}],
                "card": [{
                    "outline": "BottomOnly",
                    "outlineColor": {"solid": {"color": ORANGE}},
                    "outlineWeight": 2,
                }],
            }
        },
        "card": {
            "*": {
                "labels": [{"color": {"solid": {"color": NAVY}}, "fontSize": 28, "bold": True}],
                "categoryLabels": [{"color": {"solid": {"color": GREY}}, "fontSize": 10}],
            }
        },
        "tableEx": {
            "*": {
                "columnHeaders": [{
                    "fontColor": {"solid": {"color": NAVY}},
                    "backColor": {"solid": {"color": "#F7F8FB"}},
                    "bold": True, "fontSize": 10,
                }],
                "values": [{"fontSize": 10, "alternateBackground": True}],
            }
        },
        "matrix": {
            "*": {
                "columnHeaders": [{
                    "fontColor": {"solid": {"color": NAVY}},
                    "backColor": {"solid": {"color": "#F7F8FB"}},
                    "bold": True,
                }],
            }
        },
        "aiNarratives": {
            "*": {
                "general": [{
                    "fontFamily": "Segoe UI",
                    "fontColor": {"solid": {"color": NAVY}},
                }],
            }
        },
        "textbox": {
            "*": {
                "general": [{"fontColor": {"solid": {"color": NAVY}}}],
            }
        },
        "page": {
            "*": {
                "background": [{
                    "color": {"solid": {"color": "#FFFFFF"}},
                    "transparency": 0,
                }],
                "outspace": [{
                    "color": {"solid": {"color": "#F7F8FB"}},
                }],
            }
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
            print(f"  FAILED: {b[:800]}")
            return False, None
    return False, None


def b64_obj(o) -> str:
    return base64.b64encode(json.dumps(o, indent=2, ensure_ascii=False).encode("utf-8")).decode("ascii")


def main():
    print("Fetching HR_demo_report definition...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/reports/{REPORT}/getDefinition",
                   body={})
    if s == 202:
        ok, result_url = poll(h.get("Location") or h.get("location"))
        if not ok: return
        payload = json.loads(call("GET", result_url)[2])
    else:
        payload = json.loads(b)
    parts = {p["path"]: p["payload"] for p in payload["definition"]["parts"]}
    fmt = payload["definition"].get("format", "PBIR")
    print(f"  Loaded {len(parts)} parts (format={fmt})")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"backup_hr_report_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"  Backup -> {backup_path}")

    # 1. Add theme file as a registered resource
    theme_path = f"StaticResources/RegisteredResources/{THEME_FILE}"
    parts[theme_path] = b64_obj(INTERAC_THEME)
    print(f"  Registered theme at {theme_path}")

    # 2. Update report.json: add customTheme + RegisteredResources package
    rj_path = "definition/report.json"
    rj = json.loads(base64.b64decode(parts[rj_path]).decode("utf-8"))
    # Mirror reportVersionAtImport from baseTheme so the schema validates
    base_versions = (rj.get("themeCollection", {})
                       .get("baseTheme", {})
                       .get("reportVersionAtImport", {"visual": "2.9.0", "report": "3.3.0", "page": "2.3.1"}))
    rj.setdefault("themeCollection", {})["customTheme"] = {
        "name": THEME_NAME,
        "type": "RegisteredResources",
        "reportVersionAtImport": base_versions,
    }
    pkgs = rj.get("resourcePackages", [])
    # Idempotent: replace existing RegisteredResources package if present
    pkgs = [p for p in pkgs if p.get("name") != "RegisteredResources"]
    pkgs.append({
        "name": "RegisteredResources",
        "type": "RegisteredResources",
        "items": [
            {"name": THEME_NAME, "path": THEME_FILE, "type": "CustomTheme"}
        ],
    })
    rj["resourcePackages"] = pkgs
    parts[rj_path] = b64_obj(rj)
    print(f"  Updated report.json with customTheme={THEME_NAME}")

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
            print("  Open and check that both pages now use navy/orange/gold palette.")
        else:
            print("  update failed — revert with backup if needed")
    elif s in (200, 201):
        print(f"\n  OK -> https://msit.powerbi.com/groups/{WS}/reports/{REPORT}")
    else:
        print(f"  ERROR: {b[:1200]}")


if __name__ == "__main__":
    main()
