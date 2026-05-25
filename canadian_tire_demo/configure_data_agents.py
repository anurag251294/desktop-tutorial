"""Configure both Data Agents: bind to semantic model + seed prompts + AI instructions."""
import base64, json, subprocess, time, urllib.request, urllib.error, uuid
from pathlib import Path

AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"

DA = json.loads((Path(__file__).parent / "data_agents.json").read_text())

INSTRUCTIONS = {
    "ctc_merch_agent": (
        "You are a Merch analytics assistant for Canadian Tire. "
        "Answer questions about SKU performance, in-season demand vs supply, and connected inventory. "
        "Key metrics: POS (Point of Sale dollars), RVS (Retail Value of Shipments), "
        "EGM (Enterprise Gross Margin), WoS (Weeks of Supply), Lost Sales %, Vendor Fill Rate %, "
        "R8 (Rolling 8-week POS), R12 (Rolling 12 months). "
        "When the user asks about an SKU, fineline, category, or vendor, include POS YoY %, EGM %, "
        "WoS, fill rate, and lost sales for context. Use Canadian Tire merch vocabulary."
    ),
    "interac_hr_agent": (
        "You are an HR analytics assistant for Interac. "
        "Answer questions about active headcount, attrition (including regrettable), FINTRAC training "
        "completion, COI (Conflict of Interest) attestations, time to fill, comp ratio vs market, "
        "and headcount vs target. "
        "Highlight regulator-sensitive findings (COI overdue 90+ days, FINTRAC training gaps) when "
        "relevant. Use Canadian financial-services HR vocabulary."
    ),
}


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
        with urllib.request.urlopen(req, timeout=120) as r:
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
            return False, b
    return False, "timeout"


def b64_obj(o):
    return base64.b64encode(json.dumps(o, indent=2).encode("utf-8")).decode("ascii")


def attempt_update(ws, aid, parts):
    """Try updateDefinition with given parts list."""
    payload = {"definition": {"parts": parts}}
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{ws}/items/{aid}/updateDefinition",
                   body=payload)
    print(f"    updateDefinition status={s}")
    if s == 202:
        loc = h.get("Location") or h.get("location")
        ok, result = poll(loc)
        if ok:
            return True
        print(f"    poll: {str(result)[:500]}")
        return False
    if s in (200, 201):
        return True
    print(f"    body: {b[:500]}")
    return False


for cfg in DA:
    if not cfg.get("created_id"):
        continue
    print(f"\n=== {cfg['display']} ===")
    ws = cfg["ws"]
    aid = cfg["created_id"]

    # Build the data-agent definition with semantic-model binding
    data_agent_def = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/definition/dataAgent/2.1.0/schema.json",
        "dataSources": [
            {
                "type": "SemanticModel",
                "workspaceId": ws,
                "itemId": cfg["model_id"],
                "displayName": cfg["model_name"],
            }
        ],
        "exampleQuestions": cfg["prompts"],
    }
    stage_cfg = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/definition/stageConfiguration/1.0.0/schema.json",
        "aiInstructions": INSTRUCTIONS[cfg["name"]],
        "dataSources": [
            {
                "type": "SemanticModel",
                "workspaceId": ws,
                "itemId": cfg["model_id"],
                "displayName": cfg["model_name"],
                "exampleQuestions": cfg["prompts"],
            }
        ],
    }
    platform = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "DataAgent",
                     "displayName": cfg["display"],
                     "description": cfg["description"]},
        "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
    }

    parts = [
        {"path": ".platform",
         "payload": b64_obj(platform), "payloadType": "InlineBase64"},
        {"path": "Files/Config/data_agent.json",
         "payload": b64_obj(data_agent_def), "payloadType": "InlineBase64"},
        {"path": "Files/Config/draft/stage_config.json",
         "payload": b64_obj(stage_cfg), "payloadType": "InlineBase64"},
    ]

    ok = attempt_update(ws, aid, parts)
    if ok:
        print(f"  Configured OK -> https://msit.powerbi.com/groups/{ws}/items/{aid}")
    else:
        print("  Update failed - definition shape may need adjustment.")
