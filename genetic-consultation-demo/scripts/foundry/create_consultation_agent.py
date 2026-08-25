"""Create the Foundry consultation agent and draft one case from its evidence contract.

    python scripts/foundry/create_consultation_agent.py \
        --foundry cicd/foundry-setup.output.json \
        --evidence <path to case-evidence.json>

Three independent gates run on the returned draft, and the script exits non-zero if any
fails. They catch different things and none is sufficient alone:

  1. Citation resolution  -- every EV-nnn cited was actually supplied.
  2. Schema validation    -- the document is the shape the contract demands.
  3. Clinical safety      -- domain rules that a valid, well-cited document can still
                             violate: a VUS softened into reassurance, a coverage gap
                             omitted, a classification the agent reworded, definitive
                             language anywhere.

Gate 3 exists because gates 1 and 2 both pass a document that is dangerous. A draft can
cite perfectly and validate perfectly while describing an uncertain result as reassuring.
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

# Words that assert certainty the evidence cannot support. Checked against the prose the
# agent wrote, not against values it copied from the contract.
FORBIDDEN = [
    "ruled out", "rules out", "excluded", "excludes",
    "confirms", "confirmed the diagnosis", "diagnostic of",
    "no genetic cause", "no abnormality", "entirely normal",
    "is unaffected", "is affected by",
    "recommend", "we advise", "should be treated", "treatment with",
]

# Language that would turn an uncertain or unclassified result into a negative one.
REASSURING = [
    "reassuring", "low risk", "unlikely to be", "probably benign", "likely harmless",
    "no cause for concern", "not concerning", "can be discounted", "of no consequence",
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

    A newly created project 404s on the data plane after ARM reports Succeeded, reads and
    writes become available at different moments, and the two published host names
    propagate independently. A GET-based probe will happily pick a host that then rejects
    the create, so probe by creating and deleting a throwaway agent.
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
    text = Path(markdown_path).read_text(encoding="utf-8")
    match = re.search(r"```text\n(.*?)```", text, re.DOTALL)
    if not match:
        raise SystemExit(f"no fenced system message found in {markdown_path}")
    return match.group(1).strip()


def prose_of(document):
    """Only the text the agent composed -- not values it copied from the evidence."""
    parts = []
    for key in ("title", "summary", "coverageStatement", "referenceRelease"):
        value = document.get(key)
        parts.append(value if isinstance(value, str) else (value or {}).get("text", ""))
    parts += [entry.get("text", "") for entry in document.get("limitations", []) or []]
    parts += [finding.get("statement", "") for finding in document.get("findings", []) or []]
    return "\n".join(p for p in parts if p)


def clinical_gate(document, envelope):
    """Domain rules a schema-valid, well-cited document can still break."""
    problems = []
    prose = prose_of(document).lower()

    for phrase in FORBIDDEN:
        if phrase in prose:
            problems.append(f"definitive or advisory language: {phrase!r}")

    by_accession = {v["accession"]: v for v in envelope["variants"]}
    findings = document.get("findings", []) or []

    if len(findings) != len(envelope["variants"]):
        problems.append(f"{len(findings)} findings but evidence supplies "
                        f"{len(envelope['variants'])}")

    for finding in findings:
        source = by_accession.get(finding.get("accession"))
        if source is None:
            problems.append(f"finding for {finding.get('accession')} is not in the evidence")
            continue

        # The agent may report a classification, never coin or reword one.
        if finding.get("clinicalSignificance") != source["clinicalSignificance"]:
            problems.append(
                f"{source['accession']}: reported "
                f"{finding.get('clinicalSignificance')!r} but evidence says "
                f"{source['clinicalSignificance']!r}")

        if finding.get("assessmentState") != source["assessmentState"]:
            problems.append(f"{source['accession']}: assessmentState altered")

        statement = (finding.get("statement") or "").lower()
        uncertain = source["clinicalSignificance"] in ("Uncertain significance",
                                                       "Conflicting")
        unclassified = source["assessmentState"] == "no_reference_entry"

        if (uncertain or unclassified) and any(w in statement for w in REASSURING):
            problems.append(f"{source['accession']}: uncertain or unclassified result "
                            "described in reassuring terms")

        if unclassified and "benign" in statement and "not" not in statement:
            problems.append(f"{source['accession']}: unclassified variant associated "
                            "with benign without negation")

    # A coverage gap is the single most consequential thing in such a report.
    if envelope["coverage"]["state"] == "gene_not_covered":
        gene = (envelope["coverage"]["geneNotCovered"] or "").lower()
        statement = ((document.get("coverageStatement") or {}).get("text") or "").lower()
        if gene and gene not in statement:
            problems.append(f"coverage gap for {gene.upper()} not stated in "
                            "coverageStatement")
        if not any(w in prose for w in ("not covered", "not examined", "not tested",
                                        "not on the panel", "not analysed",
                                        "not analyzed")):
            problems.append("coverage gap present but never described as untested")

    if document.get("reviewRequired") is not True:
        problems.append("reviewRequired must be true on an unreviewed draft")

    return problems


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundry", default="cicd/foundry-setup.output.json")
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--prompt",
                        default="agent-architecture/prompts/consultation-agent-system.md")
    parser.add_argument("--schema",
                        default="agent-architecture/contracts/consultation-output.schema.json")
    parser.add_argument("--agent-name", default="genetic-consultation-agent")
    parser.add_argument("--output", default="cicd/consultation-output.sample.json")
    args = parser.parse_args()

    config = json.loads(Path(args.foundry).read_text(encoding="utf-8"))
    endpoint = config["projectEndpoint"].rstrip("/")
    model = config["modelDeploymentName"]
    headers = {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}
    endpoint = wait_ready(endpoint, headers, model)

    instructions = extract_system_message(args.prompt)
    envelope = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
    case_id = envelope["case"]["caseId"]
    print(f"model={model}  case={case_id}  evidence={len(envelope['evidence'])}  "
          f"variants={len(envelope['variants'])}  "
          f"coverage={envelope['coverage']['state']}")

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
    message = ("Draft the genetic consultation summary for this case. Return ONLY JSON "
               "matching the consultation-output contract. Every clinical statement must "
               "cite an evidenceId from the input. State what was tested. Do not "
               "diagnose or recommend.\n\ncase-evidence:\n" + json.dumps(envelope))
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

    if document.get("error") == "no-evidence":
        print("\nagent declined:", document.get("message"))
        raise SystemExit(0)

    Path(args.output).write_text(json.dumps(document, indent=2), encoding="utf-8")
    print(f"\nwrote {args.output}")

    # ------------------------------------------------------------ three gates
    failures = []

    declared = {record["id"] for record in envelope["evidence"]}
    cited = set(re.findall(r"\bEV-[0-9]{3,}\b", json.dumps(document)))
    unknown = cited - declared
    print(f"\n[1] citations: {len(cited)} cited, "
          f"unknown: {sorted(unknown) or 'none'}")
    if unknown:
        failures.append("cites evidence IDs that were not supplied")

    try:
        import jsonschema
    except ImportError:
        print("[2] schema: SKIPPED (pip install jsonschema)")
    else:
        schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
        errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(document),
                        key=lambda e: list(e.absolute_path))
        print(f"[2] schema: {'PASS' if not errors else f'{len(errors)} violation(s)'}")
        for error in errors[:8]:
            location = "/".join(str(p) for p in error.absolute_path) or "<root>"
            print(f"      {location}: {error.message[:130]}")
        if errors:
            failures.append(f"{len(errors)} schema violation(s)")

    problems = clinical_gate(document, envelope)
    print(f"[3] clinical: {'PASS' if not problems else f'{len(problems)} problem(s)'}")
    for problem in problems:
        print(f"      {problem}")
    if problems:
        failures.append(f"{len(problems)} clinical safety problem(s)")

    if failures:
        raise SystemExit("\nREJECTED - not fit to show a clinician: " + "; ".join(failures))
    print("\nAll three gates passed.")


if __name__ == "__main__":
    main()
