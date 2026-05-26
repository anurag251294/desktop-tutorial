"""Tighten Page 2 (Copilot Showcase) after manual edits:

  - Move the orphan footer_bg from y=1685 to y=1135 (just below current content)
  - Restore footer_txt over the relocated band
  - Shrink page height from 1720 to 1180

Preserves all other manual edits (deleted matrix, narratives, section labels, etc.)
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
SHOWCASE_DISPLAY = "Copilot Showcase"

VISUAL_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.10.0/schema.json"
PAGE_SCHEMA   = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"

NAVY = "#1B2C5C"
GREY = "#5A6B82"
LIGHT_GREY = "#F0F2F7"

NEW_PAGE_HEIGHT = 1180
FOOTER_Y = 1135
FOOTER_H = 35
TODAY = datetime.now().strftime("%Y-%m-%d")


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


def b64_obj(o):
    return base64.b64encode(json.dumps(o, indent=2, ensure_ascii=False).encode("utf-8")).decode("ascii")


def header_off():
    return {"visualHeader": [
        {"properties": {
            "showCopyVisualImageButton": {"expr": {"Literal": {"Value": "false"}}},
            "showFilterRestatementButton": {"expr": {"Literal": {"Value": "false"}}},
            "showFocusModeButton":       {"expr": {"Literal": {"Value": "false"}}},
            "showPinButton":             {"expr": {"Literal": {"Value": "false"}}},
        }}
    ]}


def footer_bg_visual():
    """Light grey band stretching full page width."""
    paragraphs = [{"textRuns": [{"value": " ", "textStyle": {
        "fontSize": "1pt", "color": LIGHT_GREY}}]}]
    return {
        "$schema": VISUAL_SCHEMA, "name": "footer_bg",
        "position": {"x": 0, "y": FOOTER_Y, "z": 10,
                     "height": FOOTER_H, "width": 1280, "tabOrder": 10},
        "visual": {
            "visualType": "textbox", "drillFilterOtherVisuals": True,
            "objects": {
                "general": [{"properties": {"paragraphs": paragraphs}}],
                "background": [{"properties": {
                    "color": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{LIGHT_GREY}'"}}}}},
                    "show":  {"expr": {"Literal": {"Value": "true"}}},
                    "transparency": {"expr": {"Literal": {"Value": "0"}}}}}],
            },
            "visualContainerObjects": header_off(),
        },
    }


def footer_txt_visual():
    text = f"HR_demo_report  ·  Powered by hr_demo + HR_data_agent  ·  Generated {TODAY}"
    paragraphs = [{"textRuns": [{"value": text, "textStyle": {
        "fontSize": "9pt", "color": GREY}}]}]
    return {
        "$schema": VISUAL_SCHEMA, "name": "footer_txt",
        "position": {"x": 16, "y": FOOTER_Y + 8, "z": 300,
                     "height": FOOTER_H - 16, "width": 1280 - 32, "tabOrder": 300},
        "visual": {
            "visualType": "textbox", "drillFilterOtherVisuals": True,
            "objects": {
                "general": [{"properties": {"paragraphs": paragraphs}}],
            },
            "visualContainerObjects": header_off(),
        },
    }


def find_slug(parts, display_name):
    for path, b64 in parts.items():
        if path.endswith("/page.json") and path.startswith("definition/pages/"):
            meta = json.loads(base64.b64decode(b64))
            if meta.get("displayName") == display_name:
                return path.split("/")[-2]
    raise RuntimeError(f"No page with displayName {display_name!r}")


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
    print(f"  Loaded {len(parts)} parts")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"backup_hr_report_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"  Backup -> {backup_path}")

    slug = find_slug(parts, SHOWCASE_DISPLAY)
    print(f"  Showcase slug: {slug}")

    # 1. Shrink the page
    page_path = f"definition/pages/{slug}/page.json"
    page = json.loads(base64.b64decode(parts[page_path]).decode("utf-8"))
    old_h = page.get("height")
    page["height"] = NEW_PAGE_HEIGHT
    parts[page_path] = b64_obj(page)
    print(f"  Page height: {old_h} -> {NEW_PAGE_HEIGHT}")

    # 2. Replace footer_bg (move it)
    fbg_path = f"definition/pages/{slug}/visuals/footer_bg/visual.json"
    parts[fbg_path] = b64_obj(footer_bg_visual())
    print(f"  Repositioned footer_bg to y={FOOTER_Y}")

    # 3. (Re-)add footer_txt
    ftx_path = f"definition/pages/{slug}/visuals/footer_txt/visual.json"
    parts[ftx_path] = b64_obj(footer_txt_visual())
    print(f"  Restored footer_txt at y={FOOTER_Y + 8}")

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
            print("  update failed — restore from backup if needed")
    elif s in (200, 201):
        print(f"\n  OK -> https://msit.powerbi.com/groups/{WS}/reports/{REPORT}")
    else:
        print(f"  ERROR: {b[:1200]}")


if __name__ == "__main__":
    main()
