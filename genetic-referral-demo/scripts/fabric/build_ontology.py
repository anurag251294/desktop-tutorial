"""Build the Fabric IQ ontology over the referral gold tables.

    python scripts/fabric/build_ontology.py --output cicd/fabric-setup.output.json

The ontology is the semantic layer: it declares what the things in this domain *are*
and how they relate, and binds each of those declarations to a real column in a real
gold table. The graph (scripts/fabric/build_graph_model.py) declares the same six
entities and five relationships and makes them traversable in GQL. Microsoft's own
framing is that ontology works together with graph, and that is how both are used here
-- declare the meaning once, walk it when a question is shaped like a traversal.

    Patient  -[hasFeature]->        Feature  -[inBodySystem]-> BodySystem
    Patient  -[surfacedBy]->        Criterion
    Patient  -[attendedEncounter]-> Encounter -[encounterWithSpecialty]-> Specialty

What the ontology does NOT do is decide who gets surfaced. The named criteria in
gold_referral_signals do that, deterministically and reviewably. Keeping the semantics
and the decision apart is the whole point of the design; do not let the ontology blur it.

Four things about this API cost real time, and none are obvious from the documentation:

1. **Creating an ontology item auto-provisions three more items** -- a lakehouse
   `<name>_lh_<guid>`, its SQL analytics endpoint, and a graph `<name>_graph_<guid>`.
   The graph is what actually answers queries about ontology instances. Deleting the
   ontology cleans up the lakehouse but can leave the graph behind; delete it explicitly.
   Do not mistake the companion graph for a stray and delete it -- without it the
   ontology cannot load, and the only way back is to rebuild the item.

2. **The companion graph fires its one automatic Refresh about a second after the item
   is created** -- which is *before* you have pushed any definition. That refresh fails
   with `GraphNotRefreshable` ("Graph doesn't have valid content"), and nothing retries
   it. Pushing the definition afterwards is what queues a real refresh, so the order
   create -> updateDefinition is required, and a freshly created item left alone will
   report `GraphNotQueryable` forever while looking like it is merely still loading.

3. **There is no manual refresh route.** Every job type -- Refresh, RefreshOntology,
   Ingest, ApplyChanges -- returns `InvalidJobType` on both the ontology and its
   companion graph. Ingestion is only ever a side effect of a definition write or a
   save in the editor. Re-running this script is therefore the supported way to reload.

4. **`403 FeatureNotAvailable` is usually propagation, not permissions.** After the
   `OntologyPreview` tenant setting is switched on, creates keep failing for roughly ten
   minutes. Region is rarely the cause (the only region without ontology is South
   Central US), and `delegateToCapacity: true` does not mean the capacity is blocking
   it -- check `/admin/capacities/delegatedTenantSettingOverrides` for an actual
   override before going down that road.

Property value types are String, Boolean, DateTime, Object, BigInt and Double. The
graph's INT becomes BigInt here; dates are left out for the same reason as in the graph.
"""
import argparse
import base64
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

import requests

BASE = "https://api.fabric.microsoft.com/v1"

# A fixed namespace so data-binding and contextualization IDs are stable across runs;
# a rerun then updates the same bindings instead of orphaning the previous ones.
NAMESPACE = uuid.UUID("6f1a2b3c-4d5e-6f70-8192-a3b4c5d6e7f8")

# entity type -> (gold table, key property, display property,
#                 [(property, source column, value type), ...])
ENTITY_TYPES = {
    "Patient": ("gold_referral_state", "PatientId", "PatientId", [
        ("PatientId", "patient_id", "String"),
        ("ReferralState", "referral_state", "String"),
        ("AgeYears", "age_years", "BigInt"),
        ("InterpreterRequired", "interpreter_required", "Boolean"),
        ("CriteriaFired", "criteria_fired", "BigInt"),
    ]),
    "Feature": ("gold_hpo_terms", "HpoId", "HpoLabel", [
        ("HpoId", "hpo_id", "String"),
        ("HpoLabel", "hpo_label", "String"),
    ]),
    "BodySystem": ("gold_body_systems", "BodySystem", "BodySystem", [
        ("BodySystem", "body_system", "String"),
        ("TermCount", "term_count", "BigInt"),
    ]),
    "Criterion": ("gold_criteria_definitions", "Criterion", "Criterion", [
        ("Criterion", "criterion", "String"),
        ("Tier", "tier", "String"),
        ("Description", "description", "String"),
    ]),
    "Encounter": ("gold_encounters", "EncounterId", "EncounterId", [
        ("EncounterId", "encounter_id", "String"),
        ("Specialty", "specialty", "String"),
        ("Admitted", "admitted", "Boolean"),
        ("DiagnosisRecorded", "diagnosis_recorded", "Boolean"),
    ]),
    "Specialty": ("gold_specialties", "Specialty", "Specialty", [
        ("Specialty", "specialty", "String"),
        ("EncounterCount", "encounter_count", "BigInt"),
        ("PatientCount", "patient_count", "BigInt"),
    ]),
}

# (name, source entity, target entity, mapping table, source key column, target key column)
# The mapping table must contain identifying columns for BOTH ends -- that is what makes
# it able to link them. gold_encounters serves two relationships for exactly that reason.
RELATIONSHIP_TYPES = [
    ("hasFeature", "Patient", "Feature", "gold_observations", "patient_id", "hpo_id"),
    ("inBodySystem", "Feature", "BodySystem", "gold_hpo_terms", "hpo_id", "body_system"),
    ("surfacedBy", "Patient", "Criterion", "gold_criteria_hits", "patient_id", "criterion"),
    ("attendedEncounter", "Patient", "Encounter", "gold_encounters",
     "patient_id", "encounter_id"),
    ("encounterWithSpecialty", "Encounter", "Specialty", "gold_encounters",
     "encounter_id", "specialty"),
]


def token():
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource",
         "https://api.fabric.microsoft.com", "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True)
    value = result.stdout.strip()
    if not value:
        raise SystemExit(f"could not get a Fabric token: {result.stderr.strip()[:300]}")
    return value


def encode(obj):
    return base64.b64encode(json.dumps(obj, indent=2).encode("utf-8")).decode("ascii")


def part(path, obj):
    return {"path": path, "payload": encode(obj), "payloadType": "InlineBase64"}


def build_parts(workspace_id, gold_id, name, description):
    """Every entity type, its data binding, and every relationship with its mapping."""
    entity_ids, property_ids = {}, {}
    for index, (entity, (_table, _key, _display, properties)) in enumerate(
            ENTITY_TYPES.items()):
        entity_ids[entity] = str(1000000000001 + index)
        for offset, (prop, _column, _type) in enumerate(properties):
            property_ids[(entity, prop)] = str(2000000000000 + index * 1000 + offset)

    def lakehouse_table(table):
        return {"sourceType": "LakehouseTable", "workspaceId": workspace_id,
                "itemId": gold_id, "sourceTableName": table}

    parts = [
        part(".platform", {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric"
                       "/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": "Ontology", "displayName": name,
                         "description": description},
            "config": {"version": "2.0",
                       "logicalId": "00000000-0000-0000-0000-000000000000"}}),
        part("definition.json", {}),
    ]

    for entity, (table, key, display, properties) in ENTITY_TYPES.items():
        entity_id = entity_ids[entity]
        parts.append(part(f"EntityTypes/{entity_id}/definition.json", {
            "id": entity_id,
            "namespace": "usertypes",
            "baseEntityTypeId": None,
            "name": entity,
            "entityIdParts": [property_ids[(entity, key)]],
            "displayNamePropertyId": property_ids[(entity, display)],
            "namespaceType": "Custom",
            "visibility": "Visible",
            "properties": [{"id": property_ids[(entity, prop)], "name": prop,
                            "redefines": None, "baseTypeNamespaceType": None,
                            "valueType": value_type}
                           for prop, _column, value_type in properties],
            "timeseriesProperties": [],
        }))
        binding_id = str(uuid.uuid5(NAMESPACE, f"binding:{entity}"))
        parts.append(part(
            f"EntityTypes/{entity_id}/DataBindings/{binding_id}.json", {
                "id": binding_id,
                "dataBindingConfiguration": {
                    "dataBindingType": "NonTimeSeries",
                    "propertyBindings": [
                        {"sourceColumnName": column,
                         "targetPropertyId": property_ids[(entity, prop)]}
                        for prop, column, _type in properties],
                    "sourceTableProperties": lakehouse_table(table)}}))

    for index, (name_, source, target, table, source_column, target_column) in enumerate(
            RELATIONSHIP_TYPES):
        relationship_id = str(3000000000001 + index)
        parts.append(part(f"RelationshipTypes/{relationship_id}/definition.json", {
            "namespace": "usertypes",
            "id": relationship_id,
            "name": name_,
            "namespaceType": "Custom",
            "source": {"entityTypeId": entity_ids[source]},
            "target": {"entityTypeId": entity_ids[target]},
        }))
        context_id = str(uuid.uuid5(NAMESPACE, f"ctx:{name_}"))
        parts.append(part(
            f"RelationshipTypes/{relationship_id}/Contextualizations/{context_id}.json", {
                "id": context_id,
                "dataBindingTable": {"workspaceId": workspace_id, "itemId": gold_id,
                                     "sourceTableName": table,
                                     "sourceType": "LakehouseTable"},
                "sourceKeyRefBindings": [{
                    "sourceColumnName": source_column,
                    "targetPropertyId": property_ids[
                        (source, ENTITY_TYPES[source][1])]}],
                "targetKeyRefBindings": [{
                    "sourceColumnName": target_column,
                    "targetPropertyId": property_ids[
                        (target, ENTITY_TYPES[target][1])]}]}))

    return parts


def wait(headers, response, what):
    """Fabric returns 202 plus a Location for most ontology writes."""
    if response.status_code != 202 or not response.headers.get("Location"):
        return response
    location = response.headers["Location"]
    for _ in range(60):
        time.sleep(4)
        state = requests.get(location, headers=headers, timeout=90).json()
        if state.get("status") == "Succeeded":
            return requests.get(location.rstrip("/") + "/result",
                                headers=headers, timeout=120)
        if state.get("status") == "Failed":
            raise SystemExit(f"{what} failed: {json.dumps(state.get('error'))[:400]}")
    raise SystemExit(f"{what} did not finish within four minutes")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="cicd/fabric-setup.output.json")
    parser.add_argument("--name", default="referral_ontology")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would be built and exit")
    args = parser.parse_args()

    config = json.loads(Path(args.output).read_text(encoding="utf-8"))
    workspace_id = config["workspace"]["id"]
    gold_id = next(l["id"] for l in config["lakehouses"]
                   if l["displayName"] == "gold_lakehouse")
    description = ("Genetic referral case-finding. Synthetic data, no genomic data.")

    parts = build_parts(workspace_id, gold_id, args.name, description)
    bound = sum(len(p) for _t, _k, _d, p in ENTITY_TYPES.values())
    print(f"ontology: {args.name}")
    print(f"  entity types       : {len(ENTITY_TYPES)}")
    print(f"  bound properties   : {bound}")
    print(f"  relationship types : {len(RELATIONSHIP_TYPES)}")
    for entity, (table, _k, _d, properties) in ENTITY_TYPES.items():
        print(f"    {entity:<12} -> {table} ({len(properties)} properties)")
    for name_, source, target, table, _s, _t in RELATIONSHIP_TYPES:
        print(f"    {source} -[{name_}]-> {target}  via {table}")
    if args.dry_run:
        return

    headers = {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}

    existing = requests.get(f"{BASE}/workspaces/{workspace_id}/ontologies",
                            headers=headers, timeout=120).json().get("value", [])
    ontology_id = next((o["id"] for o in existing
                        if o["displayName"] == args.name), None)

    if ontology_id:
        print(f"updating existing ontology {ontology_id}")
    else:
        created = wait(headers, requests.post(
            f"{BASE}/workspaces/{workspace_id}/ontologies", headers=headers, timeout=300,
            data=json.dumps({"displayName": args.name, "description": description})),
            "create").json()
        ontology_id = created.get("id")
        if not ontology_id:
            for _ in range(12):
                listed = requests.get(f"{BASE}/workspaces/{workspace_id}/ontologies",
                                      headers=headers, timeout=120).json().get("value", [])
                match = next((o for o in listed if o["displayName"] == args.name), None)
                if match:
                    ontology_id = match["id"]
                    break
                time.sleep(10)
            else:
                raise SystemExit(f"no ontology named {args.name!r} appeared after create")
        print(f"created ontology {ontology_id}")

    # This write is also what queues the companion graph's refresh -- see note 2 above.
    response = requests.post(
        f"{BASE}/workspaces/{workspace_id}/ontologies/{ontology_id}/updateDefinition"
        f"?updateMetadata=true",
        headers=headers, timeout=600, data=json.dumps({"definition": {"parts": parts}}))
    wait(headers, response, "updateDefinition")
    if response.status_code >= 400:
        raise SystemExit(f"updateDefinition failed: {response.status_code} "
                         f"{response.text[:400]}")
    print(f"pushed {len(parts)} definition parts")

    print(f"https://app.fabric.microsoft.com/groups/{workspace_id}"
          f"/ontologies/{ontology_id}")
    print("the companion graph reloads in the background; "
          "verify with scripts/fabric/query_ontology.py")

    config["ontology"] = {"displayName": args.name, "id": ontology_id}
    Path(args.output).write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"recorded in {args.output}")


if __name__ == "__main__":
    main()
