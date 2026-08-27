"""Copy the populated draft datasource into the published stage, with everything selected.

Fabric filled in the draft's element tree once the semantic model was attached, but the
published stage kept the empty one this script originally wrote. The published stage is
what answers questions, so an empty tree there means an agent that can see nothing.
"""
import base64
import json
import subprocess
import sys
import time

import requests

sys.stdout.reconfigure(encoding="utf-8")
WS = "9d111efc-fae6-4cb0-8cf7-708ac4944cee"
AGENT = "0f9d798f-04b0-4023-90db-9a7c97ebd87f"
B = "https://api.fabric.microsoft.com/v1"

subprocess.run(["az", "account", "set", "--subscription",
                "671b1321-4407-420b-b877-97cd40ba898a"], capture_output=True, shell=True)
token = subprocess.run(
    ["az", "account", "get-access-token", "--resource", "https://api.fabric.microsoft.com",
     "--query", "accessToken", "-o", "tsv"],
    capture_output=True, text=True, shell=True).stdout.strip()
H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def get_definition():
    response = requests.post(f"{B}/workspaces/{WS}/items/{AGENT}/getDefinition",
                             headers=H, timeout=300)
    if response.status_code == 202:
        location = response.headers["Location"]
        for _ in range(40):
            time.sleep(4)
            if requests.get(location, headers=H, timeout=120).json().get("status") == "Succeeded":
                response = requests.get(location.rstrip("/") + "/result",
                                        headers=H, timeout=120)
                break
    return response.json()["definition"]


definition = get_definition()
draft = next(p for p in definition["parts"]
             if p["path"].startswith("Files/Config/draft/semantic-model-"))
source = json.loads(base64.b64decode(draft["payload"]).decode("utf-8"))

selected = 0


def select_all(node):
    """Everything the model exposes is in scope; nothing here is sensitive at the
    household grain that the report does not already show."""
    global selected
    if isinstance(node, dict):
        if node.get("type", "").startswith("semantic_model."):
            node["is_selected"] = True
            selected += 1
        for value in node.values():
            select_all(value)
    elif isinstance(node, list):
        for value in node:
            select_all(value)


select_all(source["elements"])
tables = [e.get("display_name") for e in source["elements"]
          if e.get("type") == "semantic_model.table"]
print(f"tables in the model: {tables}")
print(f"elements selected  : {selected}")

encoded = base64.b64encode(json.dumps(source, indent=1).encode()).decode()
draft_path = draft["path"]
published_path = draft_path.replace("/draft/", "/published/")

parts = []
for part in definition["parts"]:
    if part["path"] in (draft_path, published_path):
        continue
    parts.append(part)
parts.append({"path": draft_path, "payload": encoded, "payloadType": "InlineBase64"})
parts.append({"path": published_path, "payload": encoded, "payloadType": "InlineBase64"})

update = requests.post(f"{B}/workspaces/{WS}/items/{AGENT}/updateDefinition",
                       headers=H, data=json.dumps({"definition": {"parts": parts}}),
                       timeout=600)
print("\nupdateDefinition:", update.status_code)
if update.status_code == 202:
    location = update.headers["Location"]
    for _ in range(60):
        time.sleep(5)
        state = requests.get(location, headers=H, timeout=120).json()
        if state.get("status") in ("Succeeded", "Failed"):
            print("result:", state.get("status"))
            break

after = get_definition()
for part in after["parts"]:
    if "semantic-model" in part["path"]:
        payload = json.loads(base64.b64decode(part["payload"]).decode("utf-8"))
        stage = "draft" if "/draft/" in part["path"] else "published"
        count = len(payload.get("elements", []))
        print(f"  {stage:10} tables={count}")
