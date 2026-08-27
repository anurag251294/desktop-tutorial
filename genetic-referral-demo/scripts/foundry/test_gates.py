"""Prove the four gates reject what they claim to reject.

    python scripts/foundry/test_gates.py

No Azure, no model, no capacity. Each case is a brief hand-built to break exactly one
rule, and the test asserts that the corresponding gate catches it. A gate nobody has
watched fail is a gate nobody knows works -- three of these were written against
mistakes an agent had already made in this repository, and the fourth against one it
had not made yet.
"""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from create_referral_agent import clinical_gate, limitation_gate  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads(
    (ROOT / "agent-architecture/contracts/referral-brief.schema.json")
    .read_text(encoding="utf-8"))

ENVELOPE = {
    "patient": {
        "patient_id": "SYN-00417",
        "referral_state": "indicators_present",
        "age_years": 6,
        "family_history_status": "taken",
    },
    "criteria": [
        {"criterion": "MULTI_SYSTEM", "tier": "sufficient",
         "description": "Features recorded in 3 or more body systems"},
        {"criterion": "NEURODEV_PLUS", "tier": "contributory",
         "description": "A neurodevelopmental feature alongside another system"},
    ],
    "evidence": [
        {"evidence_id": "OBS:OBS-0001234", "evidence_type": "observation",
         "evidence_date": "2025-03-11",
         "evidence_text": "Global developmental delay (HP:0001263) - "
                          "system: neurodevelopment"},
        {"evidence_id": "OBS:OBS-0001901", "evidence_type": "observation",
         "evidence_date": "2025-06-02",
         "evidence_text": "Hypotonia (HP:0001252) - system: neurology"},
        {"evidence_id": "OBS:OBS-0002233", "evidence_type": "observation",
         "evidence_date": "2025-09-18",
         "evidence_text": "Short stature (HP:0004322) - system: growth"},
        {"evidence_id": "ENC:ENC-0009911", "evidence_type": "encounter",
         "evidence_date": "2025-09-18",
         "evidence_text": "Neurology (outpatient) - no diagnosis recorded"},
    ],
    "provenance": {"run_id": "test", "reference_source": "HPO"},
}

GOOD = {
    "patient_id": "SYN-00417",
    "referral_state": "indicators_present",
    "family_history_status": "taken",
    "summary": (
        "Features are recorded across three body systems for this six-year-old: "
        "developmental delay, hypotonia and short stature. No unifying diagnosis has "
        "been recorded at the encounters reviewed. This reflects only what is in the "
        "chart."),
    "reasons": [
        {"criterion": "MULTI_SYSTEM", "tier": "sufficient",
         "statement": "Features span neurodevelopment, neurology and growth.",
         "evidence_ids": ["OBS:OBS-0001234", "OBS:OBS-0001901", "OBS:OBS-0002233"]},
        {"criterion": "NEURODEV_PLUS", "tier": "contributory",
         "statement": "Developmental delay is recorded alongside hypotonia.",
         "evidence_ids": ["OBS:OBS-0001234", "OBS:OBS-0001901"]},
    ],
    "limitations": [
        "This brief reflects only what was recorded in the chart; features that were "
        "never documented cannot be seen by the pipeline.",
        "No genetic testing has been performed and no conclusion about cause is drawn.",
    ],
    "recommended_action": "clinician_review",
}


def mutate(**changes):
    document = copy.deepcopy(GOOD)
    document.update(changes)
    return document


def schema_errors(document):
    import jsonschema
    return list(jsonschema.Draft202012Validator(SCHEMA).iter_errors(document))


def citation_failures(document, envelope):
    declared = {r["evidence_id"] for r in envelope["evidence"]}
    problems = []
    for reason in document.get("reasons", []) or []:
        ids = reason.get("evidence_ids") or []
        if not ids:
            problems.append(f"{reason.get('criterion')} has no citation")
        for identifier in ids:
            if identifier not in declared:
                problems.append(f"unknown evidence id {identifier}")
    return problems


CASES = []


def case(name, gate, document, envelope=None, should_fail=True):
    CASES.append((name, gate, document, envelope or ENVELOPE, should_fail))


case("clean brief passes every gate", "all", GOOD, should_fail=False)

case("invented evidence id", "citation",
     mutate(reasons=[{**GOOD["reasons"][0],
                      "evidence_ids": ["OBS:OBS-9999999"]},
                     GOOD["reasons"][1]]))

case("a reason with no citation at all", "citation",
     mutate(reasons=[{**GOOD["reasons"][0], "evidence_ids": []},
                     GOOD["reasons"][1]]))

case("reassuring language about an absence", "clinical",
     mutate(summary="Findings are unremarkable and the picture is reassuring. "
                    "This reflects only what was recorded in the chart."))

case("states a diagnosis", "clinical",
     mutate(summary="The pattern is diagnostic of a syndromic condition. This "
                    "reflects only what was recorded in the chart."))

case("recommends a referral", "clinical",
     mutate(summary="This child should be referred to genetics. This reflects only "
                    "what was recorded in the chart."))

case("changes the referral state", "clinical",
     mutate(referral_state="no_indicators_recorded"))

case("reports a criterion that did not fire", "clinical",
     mutate(reasons=GOOD["reasons"] + [
         {"criterion": "REGRESSION", "tier": "sufficient",
          "statement": "Developmental regression was recorded for this patient.",
          "evidence_ids": ["OBS:OBS-0001234"]}]))

case("omits a criterion that did fire", "clinical",
     mutate(reasons=[GOOD["reasons"][0]]))

case("recommended_action other than clinician_review", "schema",
     mutate(recommended_action="refer_to_genetics"))

case("drops the limitation statement", "limitation",
     mutate(limitations=["No genetic testing has been performed.",
                         "Ages are approximate."],
            summary="Features span three body systems for this six-year-old."))

# Family history never taken: the brief must say so rather than imply it was clear.
NO_HISTORY_ENV = copy.deepcopy(ENVELOPE)
NO_HISTORY_ENV["patient"]["family_history_status"] = "never_taken"

case("treats an untaken family history as an answer", "clinical",
     mutate(family_history_status="taken",
            summary="Family history is clear. Features span three body systems. "
                    "This reflects only what was recorded in the chart."),
     envelope=NO_HISTORY_ENV)

case("says plainly the family history was never taken", "clinical",
     mutate(family_history_status="never_taken",
            summary="Features span three body systems. No family history was "
                    "recorded, so nothing is known about it. This reflects only what "
                    "was recorded in the chart."),
     envelope=NO_HISTORY_ENV,
     should_fail=False)


def run():
    failures = []
    for name, gate, document, envelope, should_fail in CASES:
        caught = {
            "schema": [e.message for e in schema_errors(document)],
            "citation": citation_failures(document, envelope),
            "clinical": clinical_gate(document, envelope),
            "limitation": limitation_gate(document),
        }
        if gate == "all":
            hit = [g for g, problems in caught.items() if problems]
            ok = not hit
            detail = f"unexpectedly caught by {hit}" if hit else "clean"
        else:
            hit = bool(caught[gate])
            ok = hit == should_fail
            detail = (caught[gate][0][:88] if caught[gate]
                      else f"NOT caught by the {gate} gate")

        verdict = "ok  " if ok else "FAIL"
        expectation = "rejected" if should_fail else "accepted"
        print(f"  {verdict} {name:48} expect {expectation:8} {detail}")
        if not ok:
            failures.append(name)

    print(f"\n{len(CASES) - len(failures)}/{len(CASES)} cases behaved as specified")
    if failures:
        print("gates that did not behave as specified:")
        for name in failures:
            print("   ", name)
        raise SystemExit(1)
    print("every gate rejects what it claims to reject")


if __name__ == "__main__":
    run()
