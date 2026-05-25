"""Create a Fabric Data Agent for both Interac (hr_demo) and CTC (ctc_merch)
via the Fabric Items API. Tries multiple item-type names to find what's
accepted on this tenant.
"""
import base64, json, subprocess, time, urllib.request, urllib.error, uuid
from pathlib import Path

ROOT_CTC = Path(__file__).parent
STACK_CTC = json.loads((ROOT_CTC / "stack_ctc.json").read_text())
STACK_INT_PATH = Path(r"C:\Users\anuragdhuria\interac_demo\stack_corp.json")
STACK_INT = json.loads(STACK_INT_PATH.read_text())

CONFIGS = [
    {"name": "ctc_merch_agent",
     "display": "CTC Merch Data Agent",
     "ws": STACK_CTC["workspace_id"],
     "model_id": STACK_CTC["model_id"],
     "model_name": "ctc_merch",
     "description": "Conversational analytics over CTC Merch SKU performance, in-season demand, and connected inventory",
     "prompts": [
         "What are the top 10 SKUs by EGM dollars this year?",
         "Compare Air Fryers vs Cookware Sets POS YoY and EGM %.",
         "Which SKUs have lost sales above 5% and vendor fill rate below 85%?",
         "Show SKUs with weeks of supply above 18 but lost sales below 2%.",
         "Summarize Canvas Outdoor vendor performance.",
     ]},
    {"name": "interac_hr_agent",
     "display": "Interac HR Data Agent",
     "ws": "de6a7e47-474b-4354-87e7-26b8d741f015",
     "model_id": "89782e0a-276b-4b86-a2d0-e8238d3c8791",
     "model_name": "hr_demo",
     "description": "Conversational analytics over Interac HR - attrition, FINTRAC training, COI attestations, headcount vs target",
     "prompts": [
         "What is the current attrition rate compared to the threshold?",
         "Which departments have COI attestations overdue 90+ days?",
         "Show FINTRAC training completion by function.",
         "List managers with the most open requisitions.",
         "Headcount vs target by department.",
     ]},
]

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


def b64_str(s):
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def try_create(cfg):
    ws = cfg["ws"]
    candidates = ["DataAgent", "AISkill", "AIDataAgent"]
    for kind in candidates:
        print(f"\n  Trying type={kind}...")
        # Build platform + minimal definition
        platform = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": kind, "displayName": cfg["display"],
                         "description": cfg["description"]},
            "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
        }
        # Try with definition embedded
        body = {
            "displayName": cfg["display"],
            "description": cfg["description"],
            "type": kind,
        }
        s, h, b = call("POST", f"{API}/v1/workspaces/{ws}/items", body=body)
        print(f"    POST /items type={kind}  status={s}")
        if s in (200, 201):
            item = json.loads(b)
            return kind, item, "sync"
        if s == 202:
            loc = h.get("Location") or h.get("location")
            ok, result = poll(loc)
            if ok:
                sr, hr, br = call("GET", result)
                return kind, json.loads(br), "async"
            print(f"    poll failed: {str(result)[:300]}")
            continue
        print(f"    body: {b[:300]}")
    return None, None, None


for cfg in CONFIGS:
    print(f"\n=== {cfg['display']} ===")
    kind, item, mode = try_create(cfg)
    if item:
        print(f"  Created ({mode}, type={kind}): id={item.get('id')}")
        print(f"  Open: https://msit.powerbi.com/groups/{cfg['ws']}/items/{item.get('id')}")
        cfg["created_id"] = item.get("id")
        cfg["created_type"] = kind
    else:
        print(f"  All item-type candidates failed.")

# Save what we got
(ROOT_CTC / "data_agents.json").write_text(json.dumps(CONFIGS, indent=2))
print("\n-> data_agents.json")
