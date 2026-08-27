"""Attach the semantic model to the data agent and write its instructions.

The agent auto-attached the gold lakehouse. That is the wrong source for this domain:
closing_balance is a monthly snapshot, so an agent free to SUM it across months reports
about $119M of arrears instead of $9M. The semantic model carries the semi-additive
measure that already handles this, which is the whole reason to point at the model.

The lakehouse source is removed rather than left alongside -- leaving both lets the agent
choose, and one of the choices is wrong.
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
MODEL = "3d97a02f-7659-481e-ac34-279a9d9e3fd1"
MODEL_NAME = "TCHC_Arrears_Vacancy"
B = "https://api.fabric.microsoft.com/v1"
SCHEMA = ("https://developer.microsoft.com/json-schemas/fabric/item/dataAgent"
          "/definition/dataSource/1.0.0/schema.json")

INSTRUCTIONS = """You answer questions about Toronto Community Housing arrears and vacancy from the TCHC_Arrears_Vacancy semantic model. All data is synthetic and for demonstration only.

Always answer using the model's measures. Never sum a column yourself. The measures carry definitions that have been agreed, and a raw column sum will disagree with the report.

This matters most for arrears. Total Arrears is a BALANCE, not a flow. It adds up across wards, buildings and tenures, and it does NOT add up across time. Asked about a quarter or a year, report the position at the end of that period, never the sum of the months within it.

Measures available:
- Total Arrears, Households in Arrears, Households Charged, Arrears Rate
- Average Arrears per Household, Arrears Over 90 Days, Over 90 Day Share
- Rent Charged, Rent Collected, Collection Rate (these are flows and are additive across time)
- Arrears MoM Change
- Units, Units Vacant, Units Occupied, Vacancy Rate, Revenue Forgone
- Turnarounds Completed, Turnarounds Open, Average Turnaround Days

Slice by: ward_name, region, tenure_type (RGI or Market), unit_size, income_band, building_name, and month_name or period_start on the Date table.

If asked how arrears is calculated: receipts are applied to the oldest outstanding charge first, and the aging bucket follows the oldest charge still carrying a balance. It is not this month's charge minus this month's payment.

Average Turnaround Days covers completed work orders only. An unfinished turnaround has an unknown duration, not a zero one, and Turnarounds Open reports those separately.

Reporting rules:
- State the period the answer covers. If none was given, use the latest period and say which it is.
- Give units: dollars for balances, percentages for rates, days for turnaround.
- Distinguish a measured zero from missing data. A ward with no arrears is not the same as a ward with no records.
- If the question cannot be answered from these measures, say so plainly. Do not approximate or estimate.

Boundaries:
- This is portfolio management information, not advice about any individual household and not a recommendation to act on any tenancy.
- Do not rank, list or identify households for collections, enforcement or eviction, and do not suggest who should be contacted. Arrears affects somebody's housing, and that judgement belongs to staff working from the full case rather than to a model working from a balance.
- If asked for that, offer what you can give instead: where balances concentrate, how they are trending, and which parts of the portfolio carry the most aged debt."""


def token():
    return subprocess.run(
        ["az", "account", "get-access-token", "--resource",
         "https://api.fabric.microsoft.com", "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True).stdout.strip()


subprocess.run(["az", "account", "set", "--subscription",
                "671b1321-4407-420b-b877-97cd40ba898a"], capture_output=True, shell=True)
H = {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}


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
print("parts before:")
for part in definition["parts"]:
    print("  ", part["path"])

# Build the semantic-model datasource, mirroring the lakehouse one's envelope.
datasource = {
    "$schema": SCHEMA,
    "artifactId": MODEL,
    "workspaceId": WS,
    "dataSourceInstructions": (
        "Answer with these measures rather than by aggregating columns. Total Arrears is "
        "a balance and must not be summed across time."),
    "displayName": MODEL_NAME,
    "type": "semantic_model",
    "userDescription": "Arrears and vacancy measures agreed with the business.",
    "metadata": None,
    "elements": [],
}
encoded = base64.b64encode(json.dumps(datasource, indent=1).encode()).decode()

stage = {
    "$schema": ("https://developer.microsoft.com/json-schemas/fabric/item/dataAgent"
                "/definition/stageConfiguration/1.0.0/schema.json"),
    "aiInstructions": INSTRUCTIONS,
}
stage_encoded = base64.b64encode(json.dumps(stage, indent=1).encode()).decode()

parts = []
for part in definition["parts"]:
    path = part["path"]
    # Drop the auto-attached lakehouse source in both stages.
    if "lakehouse-tables-" in path:
        print("  dropping", path)
        continue
    if path.endswith("stage_config.json"):
        parts.append({"path": path, "payload": stage_encoded,
                      "payloadType": "InlineBase64"})
        continue
    parts.append(part)

for stage_name in ("draft", "published"):
    parts.append({"path": f"Files/Config/{stage_name}/semantic-model-{MODEL_NAME}"
                          "/datasource.json",
                  "payload": encoded, "payloadType": "InlineBase64"})
    if not any(p["path"] == f"Files/Config/{stage_name}/stage_config.json"
               for p in parts):
        parts.append({"path": f"Files/Config/{stage_name}/stage_config.json",
                      "payload": stage_encoded, "payloadType": "InlineBase64"})

print("\nparts after:")
for part in parts:
    print("  ", part["path"])

update = requests.post(f"{B}/workspaces/{WS}/items/{AGENT}/updateDefinition",
                       headers=H, data=json.dumps({"definition": {"parts": parts}}),
                       timeout=600)
print("\nupdateDefinition:", update.status_code, update.text[:300])
if update.status_code == 202:
    location = update.headers["Location"]
    for _ in range(60):
        time.sleep(5)
        state = requests.get(location, headers=H, timeout=120).json()
        if state.get("status") in ("Succeeded", "Failed"):
            print("result:", state.get("status"))
            if state.get("status") == "Failed":
                print(json.dumps(state)[:500])
            break

after = get_definition()
print("\nverified parts:")
for part in after["parts"]:
    print("  ", part["path"])
