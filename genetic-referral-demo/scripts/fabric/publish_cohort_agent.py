"""Select every table and copy the populated draft into the published stage.

    python scripts/fabric/publish_cohort_agent.py

Two things bite here, both silent:

* Fabric fills the datasource element tree only after the agent has been opened in the
  portal once. Attaching a lakehouse over REST leaves `elements` empty, and an agent
  with an empty tree can see nothing while looking perfectly configured.
* The tables arrive with `is_selected: false` even though their columns are selected,
  and the *published* stage keeps whatever empty tree was written at attach time. The
  published stage is what answers questions, so an empty tree there is an agent that
  returns nothing and reports no error.
"""
import base64
import json
import subprocess
import sys
import time

import requests

sys.stdout.reconfigure(encoding="utf-8")
WS = "e69d41bc-cbab-455b-a5d4-bab636b2c5b1"
AGENT = "aa7b0718-b16d-4a22-99e7-46d0bd9c661a"
B = "https://api.fabric.microsoft.com/v1"


def token():
    return subprocess.run(
        ["az", "account", "get-access-token", "--resource",
         "https://api.fabric.microsoft.com", "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=(sys.platform == "win32")).stdout.strip()


H = {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}


def get_definition():
    response = requests.post(f"{B}/workspaces/{WS}/items/{AGENT}/getDefinition",
                             headers=H, timeout=300)
    if response.status_code == 202:
        location = response.headers["Location"]
        for _ in range(40):
            time.sleep(4)
            if requests.get(location, headers=H,
                            timeout=120).json().get("status") == "Succeeded":
                response = requests.get(location.rstrip("/") + "/result",
                                        headers=H, timeout=120)
                break
    return response.json()["definition"]


def select_all(node, counts):
    """Everything in gold is cohort-level output; nothing here is at child grain that
    the agent's instructions do not already forbid it from reporting."""
    if isinstance(node, dict):
        kind = node.get("type", "")
        if kind.startswith("lakehouse_tables."):
            node["is_selected"] = True
            counts[kind] = counts.get(kind, 0) + 1
        for value in node.values():
            select_all(value, counts)
    elif isinstance(node, list):
        for value in node:
            select_all(value, counts)


def main():
    definition = get_definition()
    draft = next((p for p in definition["parts"]
                  if p["path"].startswith("Files/Config/draft/lakehouse-tables-")), None)
    if draft is None:
        raise SystemExit("no draft lakehouse datasource; run configure_cohort_agent.py")

    source = json.loads(base64.b64decode(draft["payload"]).decode("utf-8"))
    if not source.get("elements"):
        raise SystemExit(
            "the draft element tree is empty. Fabric fills it only after the agent has "
            "been opened once in the portal -- open it, then re-run this.")

    counts = {}
    select_all(source["elements"], counts)
    for kind, n in sorted(counts.items()):
        print(f"  selected {kind:28} {n}")

    tables = []

    def collect(node):
        if isinstance(node, dict):
            if node.get("type") == "lakehouse_tables.table":
                tables.append(node.get("display_name"))
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)

    collect(source["elements"])
    print(f"\n  tables ({len(tables)}): {sorted(tables)}")

    encoded = base64.b64encode(json.dumps(source, indent=1).encode()).decode()
    draft_path = draft["path"]
    published_path = draft_path.replace("/draft/", "/published/")

    stage = next((p for p in definition["parts"]
                  if p["path"] == "Files/Config/draft/stage_config.json"), None)

    parts = [p for p in definition["parts"]
             if p["path"] not in (draft_path, published_path,
                                  "Files/Config/published/stage_config.json")]
    parts.append({"path": draft_path, "payload": encoded,
                  "payloadType": "InlineBase64"})
    parts.append({"path": published_path, "payload": encoded,
                  "payloadType": "InlineBase64"})
    if stage:
        parts.append({"path": "Files/Config/published/stage_config.json",
                      "payload": stage["payload"], "payloadType": "InlineBase64"})

    update = requests.post(f"{B}/workspaces/{WS}/items/{AGENT}/updateDefinition",
                           headers=H, data=json.dumps({"definition": {"parts": parts}}),
                           timeout=600)
    print(f"\nupdateDefinition: {update.status_code}")
    if update.status_code == 202:
        location = update.headers["Location"]
        for _ in range(60):
            time.sleep(5)
            state = requests.get(location, headers=H, timeout=120).json()
            if state.get("status") in ("Succeeded", "Failed"):
                print("result:", state.get("status"))
                break

    after = get_definition()
    print("\nverified:")
    for part in after["parts"]:
        if "lakehouse-tables" in part["path"]:
            payload = json.loads(base64.b64decode(part["payload"]).decode("utf-8"))
            selected = json.dumps(payload).count('"is_selected": true')
            stage_name = "draft" if "/draft/" in part["path"] else "published"
            print(f"  {stage_name:10} elements={len(payload.get('elements') or [])}  "
                  f"selected={selected}")


if __name__ == "__main__":
    main()
