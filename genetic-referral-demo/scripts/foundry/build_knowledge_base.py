"""Build the Foundry IQ knowledge base: clinical vocabulary, and nothing else.

    python scripts/foundry/build_knowledge_base.py --index
    python scripts/foundry/build_knowledge_base.py --knowledge-base

What goes in, and what deliberately does not:

    IN   HPO term definitions -- what "developmental regression" actually means
    IN   the six criteria, their tiers, and their placeholder status
    IN   what each of the three referral states does and does not mean

    OUT  every patient, every observation, every encounter, every contract

That split is the point. The vocabulary agent may retrieve freely, because there is
nothing here that identifies anybody. The referral agent that writes about a patient has
no retrieval at all and can only speak from the evidence contract it was handed.

A knowledge layer answers "what does this word mean". It must not become a way to ask
"who is this child".
"""
import argparse
import json
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import requests

SEARCH = "https://referral-kb-search.search.windows.net"
INDEX = "referral-vocabulary"
KNOWLEDGE_SOURCE = "referral-vocabulary-source"
KNOWLEDGE_BASE = "referral-vocabulary-kb"
API = "2026-05-01-preview"
HPO_API = "https://ontology.jax.org/api/hp/terms/"

BODY_SYSTEM = {
    "HP:0001263": "neurodevelopment", "HP:0001249": "neurodevelopment",
    "HP:0000750": "neurodevelopment", "HP:0002376": "neurodevelopment",
    "HP:0001252": "neurology", "HP:0001250": "neurology",
    "HP:0004322": "growth", "HP:0001518": "growth", "HP:0011968": "growth",
    "HP:0000252": "craniofacial", "HP:0000175": "craniofacial",
    "HP:0001999": "craniofacial",
    "HP:0001627": "cardiac",
    "HP:0000365": "sensory", "HP:0000505": "sensory",
    "HP:0002650": "skeletal",
}

CRITERIA = [
    ("MULTI_SYSTEM", "sufficient",
     "Features recorded in three or more body systems. Surfaces a child on its own. "
     "Features spread across several body systems is the single strongest reason a "
     "paediatrician refers to genetics."),
    ("REGRESSION", "sufficient",
     "Developmental regression recorded (HP:0002376). Surfaces a child on its own. "
     "Loss of previously acquired skills is a red flag that warrants a look by itself."),
    ("NEURODEV_PLUS", "contributory",
     "A neurodevelopmental feature alongside a feature in another body system. Counts "
     "only in combination with another contributory criterion."),
    ("DIAGNOSTIC_ODYSSEY", "contributory",
     "Seen by four or more specialties over twelve or more months, with a diagnosis "
     "recorded at fewer than half of encounters. This is the diagnostic odyssey made "
     "measurable. Counts only in combination."),
    ("REPEAT_UNDIAGNOSED_ADMISSION", "contributory",
     "Two or more admissions with no diagnosis recorded. Counts only in combination."),
    ("FAMILY_HISTORY", "contributory",
     "An affected first-degree relative, recorded consanguinity, or recurrent pregnancy "
     "loss. Only counts where a family history was actually taken. Counts only in "
     "combination."),
]

STATES = [
    ("indicators_present",
     "One or more criteria fired on this child's record. This is NOT a diagnosis and "
     "NOT a referral decision. It means a clinician may wish to look at the record."),
    ("no_indicators_recorded",
     "The record was read and no criterion fired. This does NOT mean the child has no "
     "indication for genetics. It means nothing was found IN THE RECORD. A child whose "
     "features were never observed, never coded or never asked about is indistinguishable "
     "from a child who does not have them."),
    ("not_screened",
     "There was too little record to read -- fewer than 180 days. This is NOT a clear "
     "screen. Nothing was assessed."),
]

CONCEPTS = [
    ("tiers", "Sufficient and contributory criteria",
     "Criteria come in two tiers. A sufficient criterion surfaces a child on its own. A "
     "contributory criterion counts only in combination -- two or more are needed. The "
     "criteria are not equally decisive, and weighting them equally surfaces roughly a "
     "fifth of the clinic, which is a list nobody reads."),
    ("no-score", "Why there is no risk score",
     "The pipeline reports named criteria rather than a single score. A clinician "
     "reading 'surfaced because features span four body systems' can disagree with the "
     "threshold and say why. A clinician reading 'risk 0.81' can only defer to it or "
     "ignore it."),
    ("thresholds", "Threshold status",
     "Every threshold in the criteria is a PLACEHOLDER pending sign-off by the genetics "
     "service. They were set to produce a demonstrable cohort, not to be clinically "
     "correct. None of them has been reviewed by a clinician."),
    ("history-taken", "Family history recorded versus never taken",
     "A missing family history means nobody asked. It is not a negative answer. The "
     "pipeline keeps 'history taken' as its own field, and the three family-history "
     "flags stay unknown rather than false where the question was never put."),
    ("equity", "Why the screen is measured for equity",
     "Case-finding built from what was written down inherits whatever bias was in the "
     "writing. Children whose families need an interpreter have the same underlying "
     "rate of clustered presentation, but fewer of their features reach the record. The "
     "screen therefore finds a smaller share of them. A flag can be blind to a "
     "protected attribute and still reproduce the inequity attached to it, which is why "
     "the outcome is measured rather than the input merely excluded."),
    ("scope", "What the knowledge base contains",
     "This knowledge base holds clinical vocabulary only: phenotype term definitions, "
     "criteria definitions, and what the referral states mean. It contains no patient "
     "data of any kind -- no children, no observations, no encounters. Questions about "
     "a specific patient cannot be answered from it."),
]


def admin_key():
    result = subprocess.run(
        ["az", "search", "admin-key", "show", "--service-name", "referral-kb-search",
         "--resource-group", "rg-fabric-demo", "--query", "primaryKey", "-o", "tsv"],
        capture_output=True, text=True, shell=(sys.platform == "win32"))
    if result.returncode != 0:
        raise SystemExit(f"could not read the admin key:\n{result.stderr}")
    return result.stdout.strip()


def fetch_hpo():
    """Definitions come from the ontology, not from us -- an agent citing HP:0001263
    should be citing something a clinician can look up."""
    documents, missing = [], []
    for term, system in BODY_SYSTEM.items():
        try:
            request = urllib.request.Request(
                HPO_API + urllib.parse.quote(term, safe=""),
                headers={"Accept": "application/json", "User-Agent": "fabric-demo/1.0"})
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            missing.append((term, f"{type(exc).__name__}: {exc}"))
            continue
        documents.append({
            "id": term.replace(":", "_"),
            "kind": "phenotype-term",
            "title": f"{payload.get('name')} ({term})",
            "content": (f"{payload.get('name')} ({term}) is a clinical feature in the "
                        f"{system} body system. Definition from the Human Phenotype "
                        f"Ontology: {payload.get('definition') or 'no definition '
                        'published'}"),
            "source": "Human Phenotype Ontology",
        })
    return documents, missing


def build_documents():
    documents, missing = fetch_hpo()
    for name, tier, description in CRITERIA:
        documents.append({
            "id": f"criterion_{name}",
            "kind": "criterion",
            "title": f"Criterion {name} ({tier})",
            "content": f"{name} is a {tier} referral criterion. {description}",
            "source": "gold_criteria_definitions",
        })
    for name, description in STATES:
        documents.append({
            "id": f"state_{name}",
            "kind": "referral-state",
            "title": f"Referral state {name}",
            "content": f"{name}: {description}",
            "source": "pipeline definition",
        })
    for key, title, description in CONCEPTS:
        documents.append({
            "id": f"concept_{key}",
            "kind": "concept",
            "title": title,
            "content": description,
            "source": "design documentation",
        })
    return documents, missing


def create_index(key):
    schema = {
        "name": INDEX,
        "fields": [
            {"name": "id", "type": "Edm.String", "key": True, "filterable": True},
            {"name": "kind", "type": "Edm.String", "filterable": True,
             "facetable": True},
            {"name": "title", "type": "Edm.String", "searchable": True},
            {"name": "content", "type": "Edm.String", "searchable": True},
            {"name": "source", "type": "Edm.String", "filterable": True,
             "searchable": True},
        ],
        "semantic": {
            "configurations": [{
                "name": "default",
                "prioritizedFields": {
                    "titleField": {"fieldName": "title"},
                    "prioritizedContentFields": [{"fieldName": "content"}],
                },
            }],
        },
    }
    headers = {"api-key": key, "Content-Type": "application/json"}
    response = requests.put(f"{SEARCH}/indexes/{INDEX}?api-version={API}",
                            headers=headers, data=json.dumps(schema), timeout=120)
    print(f"index {INDEX}: {response.status_code}")
    if response.status_code >= 400:
        print(response.text[:400])
        raise SystemExit(1)

    documents, missing = build_documents()
    for term, reason in missing:
        print(f"  HPO MISSED {term}: {reason}")
    if missing:
        raise SystemExit(
            f"{len(missing)} phenotype terms did not resolve. The knowledge base cites "
            f"ontology definitions, so shipping without them means citing labels we "
            f"never fetched.")

    upload = {"value": [dict(d, **{"@search.action": "mergeOrUpload"})
                        for d in documents]}
    response = requests.post(f"{SEARCH}/indexes/{INDEX}/docs/index?api-version={API}",
                             headers=headers, data=json.dumps(upload), timeout=180)
    print(f"upload {len(documents)} docs: {response.status_code}")
    if response.status_code >= 400:
        print(response.text[:400])
        raise SystemExit(1)
    counts = {}
    for d in documents:
        counts[d["kind"]] = counts.get(d["kind"], 0) + 1
    for kind, n in sorted(counts.items()):
        print(f"    {kind:18} {n}")

    # A patient identifier reaching this index would break the whole separation.
    blob = json.dumps(documents)
    for marker in ("SYN-", "patient_id", "OBS:", "ENC:", "FHX:"):
        if marker in blob:
            raise SystemExit(
                f"REFUSING to publish: {marker!r} appears in the vocabulary corpus. "
                f"This knowledge base must contain no patient data.")
    print("    scope check: no patient identifiers in the corpus")


def create_knowledge_base(key):
    headers = {"api-key": key, "Content-Type": "application/json"}
    source = {
        "name": KNOWLEDGE_SOURCE,
        "kind": "searchIndex",
        "description": ("Clinical vocabulary for genetic referral case-finding: "
                        "phenotype terms, criteria, referral states. No patient data."),
        # sourceDataSelect is not a property of SearchIndexKnowledgeSourceParameters
        # at this api-version, despite appearing in some examples.
        "searchIndexParameters": {"searchIndexName": INDEX},
    }
    response = requests.put(
        f"{SEARCH}/knowledgeSources/{KNOWLEDGE_SOURCE}?api-version={API}",
        headers=headers, data=json.dumps(source), timeout=120)
    print(f"knowledge source: {response.status_code}")
    if response.status_code >= 400:
        print(response.text[:600])
        raise SystemExit(1)

    # A knowledge base needs a model attached before it will retrieve at all:
    # without one, /retrieve fails with "A Knowledge Base model must be specified to use
    # any reasoning effort other than 'Minimal'", and retrievalReasoningEffort turns out
    # not to be a plain string so it cannot simply be set to Minimal instead. The
    # model's identity is the SEARCH service's managed identity, which therefore needs
    # Cognitive Services User on the Foundry account.
    # includeReferences / includeReferenceSourceData are likewise not properties of
    # AgentKnowledgeSourceReference at this api-version.
    base = {
        "name": KNOWLEDGE_BASE,
        "description": ("Answers what a clinical term, criterion or referral state "
                        "means. Contains no patient data."),
        "models": [{
            "kind": "azureOpenAI",
            "azureOpenAIParameters": {
                "resourceUri": "https://referral-foundry-mcap.openai.azure.com",
                "deploymentId": "gpt-5-4-mini",
                "modelName": "gpt-5.4-mini",
            },
        }],
        "knowledgeSources": [{"name": KNOWLEDGE_SOURCE}],
    }
    response = requests.put(
        f"{SEARCH}/knowledgeBases/{KNOWLEDGE_BASE}?api-version={API}",
        headers=headers, data=json.dumps(base), timeout=120)
    print(f"knowledge base  : {response.status_code}")
    if response.status_code >= 400:
        print(response.text[:600])
        raise SystemExit(1)
    print(f"\nMCP endpoint:\n  {SEARCH}/knowledgebases/{KNOWLEDGE_BASE}"
          f"/mcp?api-version={API}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", action="store_true", help="create and fill the index")
    parser.add_argument("--knowledge-base", action="store_true",
                        help="create the knowledge source and knowledge base")
    args = parser.parse_args()
    if not (args.index or args.knowledge_base):
        parser.error("pass --index and/or --knowledge-base")
    key = admin_key()
    if args.index:
        create_index(key)
    if args.knowledge_base:
        create_knowledge_base(key)


if __name__ == "__main__":
    main()
