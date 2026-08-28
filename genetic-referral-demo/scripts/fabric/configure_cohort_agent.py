"""Point the Fabric data agent at the gold tables and give it its boundaries.

    python scripts/fabric/configure_cohort_agent.py

This is the third agent, and the one that answers questions across the cohort:
"how many children surfaced", "how long has their evidence been sitting there",
"which criteria fire most". It queries Fabric directly, which the other two do not.

The boundary matters more here than anywhere else. This agent CAN reach every child in
the gold tables, so the restraint cannot come from the shape of its input the way it does
for the referral brief agent. It has to come from instructions, and instructions are
weaker. So the instructions are explicit, and the demo says out loud that this is the
agent with the widest reach and therefore the one to scrutinise hardest.
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
GOLD = "473c3fed-2917-43aa-983a-d1854a32fd46"
GOLD_NAME = "gold_lakehouse"
B = "https://api.fabric.microsoft.com/v1"
SCHEMA = ("https://developer.microsoft.com/json-schemas/fabric/item/dataAgent"
          "/definition/dataSource/1.0.0/schema.json")

TABLES = [
    "gold_referral_state", "gold_criteria_hits", "gold_criteria_definitions",
    "gold_signal_latency", "gold_equity_check", "gold_validation_sensitivity",
    "gold_body_systems", "gold_specialties", "gold_patient_signals",
]

INSTRUCTIONS = """You answer questions about a genetic referral case-finding pipeline for a paediatric hospital, from the gold tables in this lakehouse. All data is synthetic. No real child is described, and no genomic data exists anywhere in this system.

WHAT THE PIPELINE DOES

It reads clinical records and applies six named criteria to surface children a clinician may wish to review for possible genetic consultation. It does not diagnose and it does not decide referrals.

THE THREE STATES, WHICH MUST NEVER BE BLURRED

- indicators_present: one or more criteria fired on the record.
- no_indicators_recorded: the record was read and nothing fired. This does NOT mean the child has no indication for genetics. It means nothing was found IN THE RECORD. A child whose features were never observed, never coded or never asked about is indistinguishable from a child who does not have them.
- not_screened: too little record to read. This is NOT a clear screen. Nothing was assessed.

If you report counts by state, say what the middle state does not mean. Never describe no_indicators_recorded as "clear", "negative", "no concerns" or "screened out".

THE CRITERIA

Six, in two tiers. Sufficient criteria (MULTI_SYSTEM, REGRESSION) surface a child alone. Contributory criteria (NEURODEV_PLUS, DIAGNOSTIC_ODYSSEY, REPEAT_UNDIAGNOSED_ADMISSION, FAMILY_HISTORY) count only in combination, two or more. Every threshold is a PLACEHOLDER pending sign-off by the genetics service; say so if asked about them.

LATENCY

gold_signal_latency holds, for each surfaced child, the earliest date their record already satisfied the tier rule, and how long ago that was. Report it as "the evidence has been sufficient since that date". Do NOT say a referral was missed, late, or delayed: the synthetic record contains no referral events at all, so that comparison cannot be made from this data.

EQUITY

gold_validation_sensitivity compares how many affected children the screen surfaced, by interpreter need, against a planted answer key. Both groups carry the same underlying prevalence, so the gap is caused by what reached the record, not by biology. If asked about latency by interpreter need, warn that it looks better for interpreter-needing children only because the screen missed the subtler cases entirely; those children are absent from the latency table and present in the sensitivity gap.

BOUNDARIES

- This is cohort-level information. Do not identify, rank, prioritise or list individual children for referral, testing, or clinical attention, and do not suggest who should be seen first. That judgement belongs to a clinician working from the full record.
- If asked for that, offer what you can instead: how many children surfaced, which criteria fired most, how long evidence has been sitting there, and where the screen performs unevenly.
- Never state or imply that a child does or does not need genetics input.
- Never name a condition, syndrome or gene. No genetic testing has been performed on anyone here.
- Distinguish a measured zero from missing data. A group with no surfaced children is not the same as a group with no records.
- State the units: children, months, percentages. Say which run the numbers come from if asked.
- If a question cannot be answered from these tables, say so plainly rather than estimating."""


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


def main():
    definition = get_definition()
    print("parts before:")
    for part in definition["parts"]:
        print("  ", part["path"])

    datasource = {
        "$schema": SCHEMA,
        "artifactId": GOLD,
        "workspaceId": WS,
        "dataSourceInstructions": (
            "Cohort-level questions only. Never identify or rank individual children. "
            "no_indicators_recorded does not mean the child is clear."),
        "displayName": GOLD_NAME,
        "type": "lakehouse_tables",
        "userDescription": "Referral case-finding output: states, criteria, latency, "
                           "equity checks.",
        "metadata": None,
        "elements": [],
    }
    encoded = base64.b64encode(json.dumps(datasource, indent=1).encode()).decode()

    stage = {"$schema": ("https://developer.microsoft.com/json-schemas/fabric/item"
                         "/dataAgent/definition/stageConfiguration/1.0.0/schema.json"),
             "aiInstructions": INSTRUCTIONS}
    stage_encoded = base64.b64encode(json.dumps(stage, indent=1).encode()).decode()

    parts = []
    for part in definition["parts"]:
        if part["path"].endswith("stage_config.json"):
            parts.append({"path": part["path"], "payload": stage_encoded,
                          "payloadType": "InlineBase64"})
            continue
        parts.append(part)

    for stage_name in ("draft", "published"):
        parts.append({
            "path": f"Files/Config/{stage_name}/lakehouse-tables-{GOLD_NAME}"
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
    print("\nupdateDefinition:", update.status_code, update.text[:200])
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


if __name__ == "__main__":
    main()
