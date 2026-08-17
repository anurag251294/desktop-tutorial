"""Create the Foundry report agent and generate a grounded report for one run.

    python scripts/foundry/create_report_agent.py \
        --foundry cicd/foundry-setup.output.json \
        --report-input <path-or-onelake-uri-to-report-input.json>

This implements the unattended path from agent-architecture/architecture.md: the
deterministic handoff contract is supplied directly to the model. It does not use the
Fabric data-agent tool, which is preview, requires user identity passthrough, and whose
connection category is not creatable through the ARM connections API. The system prompt
already covers that case -- an unavailable tool becomes a listed data gap rather than a
failure.

Auth: the data plane needs the Microsoft.CognitiveServices/accounts/AIServices/agents/*
data action, assigned at PROJECT scope. Account-scope assignment is silently
insufficient. The built-in Azure AI User role may not exist in every tenant; create a
custom role with those data actions if it is missing.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

API_VERSION = "v1"


def token(resource="https://ai.azure.com"):
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=(sys.platform == "win32"),
    )
    if result.returncode != 0:
        raise SystemExit(f"token acquisition failed:\n{result.stderr}")
    return result.stdout.strip()


def extract_system_message(markdown_path):
    """Pull the system message out of the fenced block in the prompt document."""
    text = Path(markdown_path).read_text(encoding="utf-8")
    match = re.search(r"```text\n(.*?)```", text, re.DOTALL)
    if not match:
        raise SystemExit(f"no fenced system message found in {markdown_path}")
    return match.group(1).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundry", default="cicd/foundry-setup.output.json")
    parser.add_argument("--report-input", required=True)
    parser.add_argument("--prompt", default="agent-architecture/prompts/report-agent-system.md")
    parser.add_argument("--agent-name", default="geohazard-report-agent")
    parser.add_argument("--output", default="cicd/report-output.sample.json")
    args = parser.parse_args()

    config = json.loads(Path(args.foundry).read_text(encoding="utf-8"))
    endpoint = config["projectEndpoint"].rstrip("/")
    model = config["modelDeploymentName"]
    headers = {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}

    instructions = extract_system_message(args.prompt)
    report_input = json.loads(Path(args.report_input).read_text(encoding="utf-8"))
    run_id = report_input["run"]["runId"]
    print(f"model={model}  run={run_id}  evidence={len(report_input['evidence'])}")

    # ----------------------------------------------------------------- agent
    listed = requests.get(f"{endpoint}/assistants?api-version={API_VERSION}",
                          headers=headers, timeout=120).json()
    existing = next((a for a in listed.get("data", [])
                     if a.get("name") == args.agent_name), None)
    body = {
        "model": model,
        "name": args.agent_name,
        "instructions": instructions,
        "tools": [],
        "response_format": {"type": "json_object"},
    }
    if existing:
        agent_id = existing["id"]
        requests.post(f"{endpoint}/assistants/{agent_id}?api-version={API_VERSION}",
                      headers=headers, data=json.dumps(body), timeout=120)
        print(f"agent updated: {agent_id}")
    else:
        response = requests.post(f"{endpoint}/assistants?api-version={API_VERSION}",
                                 headers=headers, data=json.dumps(body), timeout=120)
        if not response.ok:
            raise SystemExit(f"agent create failed {response.status_code}: {response.text[:600]}")
        agent_id = response.json()["id"]
        print(f"agent created: {agent_id}")

    # ------------------------------------------------------------ generation
    thread = requests.post(f"{endpoint}/threads?api-version={API_VERSION}",
                           headers=headers, data="{}", timeout=120).json()
    thread_id = thread["id"]

    user_message = (
        "Produce the geohazard screening report for this run. Return ONLY JSON matching "
        "the geohazard-report-output contract. Every numeric or coverage claim must cite "
        "an evidenceId from the input. The Fabric data-agent tool is unavailable for this "
        "request; note any question you could not answer as a data gap.\n\n"
        "geohazard-report-input:\n" + json.dumps(report_input)
    )
    requests.post(f"{endpoint}/threads/{thread_id}/messages?api-version={API_VERSION}",
                  headers=headers,
                  data=json.dumps({"role": "user", "content": user_message}), timeout=180)

    run = requests.post(f"{endpoint}/threads/{thread_id}/runs?api-version={API_VERSION}",
                        headers=headers,
                        data=json.dumps({"assistant_id": agent_id}), timeout=120).json()
    run_ref = run["id"]
    print("generating ...")
    for _ in range(90):
        time.sleep(5)
        state = requests.get(
            f"{endpoint}/threads/{thread_id}/runs/{run_ref}?api-version={API_VERSION}",
            headers=headers, timeout=60).json()
        status = state.get("status")
        if status in ("completed", "failed", "cancelled", "expired", "requires_action"):
            print(f"run status: {status}")
            if status != "completed":
                print(json.dumps(state.get("last_error") or state, indent=2)[:900])
                raise SystemExit(1)
            break
    else:
        raise SystemExit("run did not finish in time")

    messages = requests.get(
        f"{endpoint}/threads/{thread_id}/messages?api-version={API_VERSION}",
        headers=headers, timeout=120).json()
    answer = next(m for m in messages["data"] if m["role"] == "assistant")
    text = "".join(part["text"]["value"] for part in answer["content"]
                   if part.get("type") == "text")

    cleaned = re.sub(r"^```(?:json)?\n|\n```$", "", text.strip())
    try:
        document = json.loads(cleaned)
    except ValueError:
        print("model did not return valid JSON:")
        print(text[:1500])
        raise SystemExit(1)

    Path(args.output).write_text(json.dumps(document, indent=2), encoding="utf-8")
    print(f"\nwrote {args.output}")

    # ------------------------------------------------------------ validation
    declared = {e["id"] for e in report_input["evidence"]}
    cited = set(re.findall(r"\bE[1-9][0-9]*\b", json.dumps(document)))
    unknown = cited - declared
    print(f"evidence cited: {len(cited)}  unknown citations: {sorted(unknown) or 'none'}")
    if unknown:
        print("FAIL: report references evidence IDs that do not exist. Reject before rendering.")
    else:
        print("PASS: every citation resolves to supplied evidence.")
    print(f"top-level keys: {sorted(document.keys())}")


if __name__ == "__main__":
    main()
