"""Create the Foundry referral agent and draft one brief from its evidence contract.

    python scripts/foundry/create_referral_agent.py \
        --foundry cicd/foundry-setup.output.json \
        --evidence cicd/patient-evidence.SYN-00123.json

Four independent gates run on the returned brief, and the script exits non-zero if any
fails. They catch different things and none is sufficient alone:

  1. Schema      -- the document is the shape the contract demands.
  2. Citation    -- every evidence_id cited was actually supplied, and every reason
                    carries at least one.
  3. Clinical    -- rules a valid, well-cited document can still break: a diagnosis, a
                    named condition, a referral recommendation, or reassuring language
                    that turns "nothing was recorded" into "nothing is wrong".
  4. Limitation  -- the brief says out loud that it reflects only what was written down.

Gate 3 exists because gates 1 and 2 both pass a document that is dangerous. A brief can
cite perfectly and validate perfectly while telling a clinician a child is fine.

Gate 4 is separate from gate 3 for a reason: gate 3 catches a bad sentence being
present, gate 4 catches a necessary sentence being absent. Absence is the harder failure
to notice by reading, and the easier one for a model to drift into.
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

# Language asserting a clinical conclusion the pipeline cannot support. Checked against
# the prose the agent composed, not against values it copied from the contract.
FORBIDDEN = [
    "diagnosis of", "diagnosed with", "diagnostic of", "confirms", "confirmed",
    "ruled out", "rules out", "excludes", "excluded",
    "should be referred", "recommend referral", "refer to genetics",
    "does not need", "no referral", "no further action", "can be discharged",
    "genetic testing is indicated", "order testing", "we advise",
]

# Language that would turn "nothing was recorded" into "nothing is wrong". This is the
# single most likely way for the brief to become harmful while remaining accurate.
REASSURING = [
    "no concerns", "no indication", "screen negative", "negative screen",
    "nothing found", "unremarkable", "reassuring", "low risk", "not concerning",
    "no cause for concern", "no evidence of a genetic", "no genetic condition",
    "normal development", "developmentally normal", "can be discounted",
]

# A brief must say this much about its own reach, in whatever words it chooses.
LIMITATION_MARKERS = [
    ("record", "chart", "documented", "recorded"),
    ("not", "never", "cannot", "unable", "invisible", "absent", "missing", "only"),
]


def token(resource="https://ai.azure.com"):
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=(sys.platform == "win32"))
    if result.returncode != 0:
        raise SystemExit(f"token acquisition failed:\n{result.stderr}")
    return result.stdout.strip()


def wait_ready(endpoint, headers, model, attempts=20):
    """Wait until the project accepts a WRITE, and return the host that does.

    A newly created project 404s on the data plane after ARM reports Succeeded, reads
    and writes become available at different moments, and the two published host names
    propagate independently. A GET-based probe will happily pick a host that then
    rejects the create, so probe by creating and deleting a throwaway agent.
    """
    candidates = [endpoint]
    if ".services.ai.azure.com" in endpoint:
        candidates.append(endpoint.replace(".services.ai.azure.com",
                                           ".cognitiveservices.azure.com"))
    elif ".cognitiveservices.azure.com" in endpoint:
        candidates.append(endpoint.replace(".cognitiveservices.azure.com",
                                           ".services.ai.azure.com"))

    probe = {"model": model, "name": "_readiness_probe", "instructions": "probe",
             "tools": []}
    for attempt in range(attempts):
        for candidate in candidates:
            try:
                response = requests.post(
                    f"{candidate}/assistants?api-version={API_VERSION}",
                    headers=headers, data=json.dumps(probe), timeout=90)
            except Exception:
                continue
            if response.ok:
                requests.delete(
                    f"{candidate}/assistants/{response.json()['id']}"
                    f"?api-version={API_VERSION}", headers=headers, timeout=90)
                if candidate != endpoint:
                    print(f"using alternate host: {candidate}")
                return candidate
        if attempt == 0:
            print("project not writable on the data plane yet, waiting ...")
        time.sleep(20)
    raise SystemExit(f"project never became writable: {endpoint}")


def extract_system_message(markdown_path):
    """The fenced block IS the system message. Prose around it is not sent.

    This has been got wrong twice in this codebase by writing a required rule in the
    surrounding prose, where it is silently dropped at runtime.
    """
    text = Path(markdown_path).read_text(encoding="utf-8")
    match = re.search(r"```text\n(.*?)```", text, re.DOTALL)
    if not match:
        raise SystemExit(f"no fenced system message found in {markdown_path}")
    return match.group(1).strip()


def prose_of(document):
    """Only the text the agent composed, not values it copied from the contract."""
    parts = [document.get("summary") or ""]
    parts += [r.get("statement", "") for r in document.get("reasons", []) or []]
    parts += list(document.get("limitations", []) or [])
    return "\n".join(p for p in parts if p)


def clinical_gate(document, envelope):
    """Domain rules a schema-valid, well-cited brief can still break."""
    problems = []
    prose = prose_of(document).lower()

    for phrase in FORBIDDEN:
        if phrase in prose:
            problems.append(f"clinical conclusion or recommendation: {phrase!r}")
    for phrase in REASSURING:
        if phrase in prose:
            problems.append(f"reassuring language about an absence: {phrase!r}")

    if document.get("recommended_action") != "clinician_review":
        problems.append(
            f"recommended_action is {document.get('recommended_action')!r}; the only "
            f"permitted value is 'clinician_review'")

    # The state must be copied, not decided.
    supplied_state = envelope["patient"]["referral_state"]
    if document.get("referral_state") != supplied_state:
        problems.append(
            f"referral_state was changed: contract said {supplied_state!r}, brief says "
            f"{document.get('referral_state')!r}")

    if document.get("patient_id") != envelope["patient"]["patient_id"]:
        problems.append("patient_id does not match the contract")

    # Criteria may not be invented, and may not be dropped.
    supplied = {c["criterion"] for c in envelope["criteria"]}
    claimed = {r.get("criterion") for r in document.get("reasons", []) or []}
    if claimed - supplied:
        problems.append(f"reports criteria that did not fire: {sorted(claimed - supplied)}")
    if supplied - claimed:
        problems.append(f"omits criteria that did fire: {sorted(supplied - claimed)}")

    # Where nobody took a family history, the brief must not treat it as an answer.
    if envelope["patient"].get("family_history_status") == "never_taken":
        if document.get("family_history_status") == "taken":
            problems.append("claims a family history was taken when none was")
        if "family history" in prose and not any(
                marker in prose for marker in
                ("not recorded", "never taken", "was not taken", "not asked",
                 "nobody asked", "no family history was recorded", "not documented")):
            problems.append(
                "discusses family history without saying it was never taken")
    return problems


def limitation_gate(document):
    """The brief must state its own reach. Absence is the failure being caught here."""
    limitations = " ".join(document.get("limitations", []) or []).lower()
    summary = (document.get("summary") or "").lower()
    text = limitations + " " + summary
    missing = [group for group in LIMITATION_MARKERS
               if not any(word in text for word in group)]
    if missing:
        return ["no statement that the brief reflects only what was recorded"]
    return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundry", default="cicd/foundry-setup.output.json")
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--prompt",
                        default="agent-architecture/prompts/referral-agent-system.md")
    parser.add_argument("--schema",
                        default="agent-architecture/contracts/referral-brief.schema.json")
    parser.add_argument("--agent-name", default="genetic-referral-agent")
    parser.add_argument("--output", default="cicd/referral-brief.sample.json")
    args = parser.parse_args()

    # Fail before calling anything if the schema gate cannot run. A gate that silently
    # skips is not a gate, and this one skipping is exactly how an invalid document
    # reached a reviewer during the geohazard build.
    try:
        import jsonschema
    except ImportError:
        raise SystemExit(
            "jsonschema is not installed, so the schema gate cannot run.\n"
            "  pip install jsonschema\n"
            "Refusing to draft a brief that cannot be validated.")

    config = json.loads(Path(args.foundry).read_text(encoding="utf-8"))
    endpoint = config["projectEndpoint"].rstrip("/")
    model = config["modelDeploymentName"]
    headers = {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}
    endpoint = wait_ready(endpoint, headers, model)

    instructions = extract_system_message(args.prompt)
    schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    envelope = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
    patient = envelope["patient"]
    print(f"model={model}  patient={patient['patient_id']}  "
          f"state={patient['referral_state']}  "
          f"criteria={len(envelope['criteria'])}  "
          f"evidence={len(envelope['evidence'])}")

    # ----------------------------------------------------------------- agent
    listed = requests.get(f"{endpoint}/assistants?api-version={API_VERSION}",
                          headers=headers, timeout=120).json()
    existing = next((a for a in listed.get("data", [])
                     if a.get("name") == args.agent_name), None)
    body = {"model": model, "name": args.agent_name, "instructions": instructions,
            "tools": [], "response_format": {"type": "json_object"}}
    if existing:
        agent_id = existing["id"]
        requests.post(f"{endpoint}/assistants/{agent_id}?api-version={API_VERSION}",
                      headers=headers, data=json.dumps(body), timeout=120)
        print(f"agent updated: {agent_id}")
    else:
        response = requests.post(f"{endpoint}/assistants?api-version={API_VERSION}",
                                 headers=headers, data=json.dumps(body), timeout=120)
        if not response.ok:
            raise SystemExit(f"agent create failed {response.status_code}: "
                             f"{response.text[:500]}")
        agent_id = response.json()["id"]
        print(f"agent created: {agent_id}")

    # ------------------------------------------------------------ generation
    thread = requests.post(f"{endpoint}/threads?api-version={API_VERSION}",
                           headers=headers, data="{}", timeout=120).json()
    thread_id = thread["id"]
    # Send the schema, not just its name. The first version told the model to return
    # JSON "matching the referral brief contract" without ever supplying the contract,
    # and it invented a reasonable-looking shape -- reasons[].text in place of
    # criterion/tier/statement. The content was accurate and well cited; it failed the
    # schema gate on a field it had never been shown.
    names = [c["criterion"] for c in envelope["criteria"]]
    message = ("Write the referral brief for this patient. Return ONLY JSON valid "
               "against the schema below. Every reason must cite an evidence_id from "
               "the input. Copy patient_id and referral_state exactly. Produce exactly "
               f"one entry in `reasons` for each of these {len(names)} criteria, naming "
               f"each one: {', '.join(names)}. Do not diagnose, do not name a "
               "condition, and do not recommend referral or against it."
               "\n\nschema:\n" + json.dumps(schema)
               + "\n\npatient-evidence:\n" + json.dumps(envelope))
    requests.post(f"{endpoint}/threads/{thread_id}/messages?api-version={API_VERSION}",
                  headers=headers,
                  data=json.dumps({"role": "user", "content": message}), timeout=180)

    run = requests.post(f"{endpoint}/threads/{thread_id}/runs?api-version={API_VERSION}",
                        headers=headers,
                        data=json.dumps({"assistant_id": agent_id}), timeout=120).json()
    print("drafting ...")
    for _ in range(90):
        time.sleep(5)
        state = requests.get(
            f"{endpoint}/threads/{thread_id}/runs/{run['id']}?api-version={API_VERSION}",
            headers=headers, timeout=60).json()
        if state.get("status") in ("completed", "failed", "cancelled", "expired",
                                   "requires_action"):
            print("run status:", state.get("status"))
            if state.get("status") != "completed":
                print(json.dumps(state.get("last_error") or state, indent=1)[:800])
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
        print("agent did not return valid JSON:")
        print(text[:1200])
        raise SystemExit(1)

    # The lawful escape. Without it, a contract demanding at least one citation leaves
    # no valid document for an empty envelope, and a model with no valid output
    # available will invent one.
    if document.get("error") == "no-evidence":
        print("\nagent declined: no evidence supplied for "
              f"{document.get('patient_id')}")
        if envelope["evidence"]:
            raise SystemExit(
                "REJECTED - agent claimed no evidence, but the contract supplied "
                f"{len(envelope['evidence'])} items")
        raise SystemExit(0)

    Path(args.output).write_text(json.dumps(document, indent=2), encoding="utf-8")
    print(f"\nwrote {args.output}")

    # ------------------------------------------------------------- four gates
    failures = []

    errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(document),
                    key=lambda e: list(e.absolute_path))
    print(f"\n[1] schema:     {'PASS' if not errors else f'{len(errors)} violation(s)'}")
    for error in errors[:8]:
        location = "/".join(str(p) for p in error.absolute_path) or "<root>"
        print(f"      {location}: {error.message[:130]}")
    if errors:
        failures.append(f"{len(errors)} schema violation(s)")

    declared = {record["evidence_id"] for record in envelope["evidence"]}
    cited = set()
    uncited_reasons = []
    for reason in document.get("reasons", []) or []:
        ids = reason.get("evidence_ids") or []
        cited |= set(ids)
        if not ids:
            uncited_reasons.append(reason.get("criterion", "<unnamed>"))
    unknown = cited - declared
    print(f"[2] citations:  {len(cited)} cited, "
          f"unknown: {sorted(unknown) or 'none'}, "
          f"uncited reasons: {uncited_reasons or 'none'}")
    if unknown:
        failures.append(f"cites {len(unknown)} evidence ID(s) that were not supplied")
    if uncited_reasons:
        failures.append(f"{len(uncited_reasons)} reason(s) with no citation")

    problems = clinical_gate(document, envelope)
    print(f"[3] clinical:   {'PASS' if not problems else f'{len(problems)} problem(s)'}")
    for problem in problems:
        print(f"      {problem}")
    if problems:
        failures.append(f"{len(problems)} clinical safety problem(s)")

    absent = limitation_gate(document)
    print(f"[4] limitation: {'PASS' if not absent else 'MISSING'}")
    for item in absent:
        print(f"      {item}")
    if absent:
        failures.append("no limitation statement")

    if failures:
        raise SystemExit("\nREJECTED - not fit to show a clinician: "
                         + "; ".join(failures))
    print("\nAll four gates passed.")


if __name__ == "__main__":
    main()
