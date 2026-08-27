"""Build the Fabric graph model over the referral gold and silver tables.

    python scripts/fabric/build_graph_model.py --output cicd/fabric-setup.output.json

Six node types and five edge types, so that "surfaced because features span three body
systems" stops being a number in a cell and becomes a traversal you can walk on screen.

    Patient  -[hasFeature]->        Feature  -[inBodySystem]-> BodySystem
    Patient  -[surfacedBy]->        Criterion
    Patient  -[attendedEncounter]-> Encounter -[encounterWithSpecialty]-> Specialty

Two constraints shape every decision below, both from the Fabric graph limitations:

1. **No schema evolution.** Adding a property or changing a key means building a new
   graph model and reloading everything. So properties are kept to what the demo
   queries actually need, and nothing speculative is included.
2. **Only Boolean, Double, Integer, String, Zoned DateTime and Duration are supported.**
   Dates are deliberately left out rather than guessed at: the example schema writes
   DATETIME while the limitations page says Zoned DateTime, and no traversal here needs
   a date. Getting it wrong costs a full rebuild; omitting it costs nothing.

And one behaviour that is not in the documentation at all: **an edge whose two endpoint
tables and own source table are not all in the same lakehouse is silently dropped at
load.** The refresh still reports Completed with a null failureReason, and the stored
definition still lists the edge type, so the only symptom is a query failing with "does
not match any edge type in the graph" -- which reads like a query problem rather than a
load one. Four of five edge types were lost to this before every source was moved into
gold. That is also the right architecture: gold is the serving layer, and a serving
artefact reaching back into silver is the medallion leaking.
"""
import argparse
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

BASE = "https://api.fabric.microsoft.com/v1"

SCHEMA = ("https://developer.microsoft.com/json-schemas/fabric/item/graphIndex"
          "/definition/{part}/{version}/schema.json")

# ---------------------------------------------------------------- the schema
# (alias, label, lakehouse, table, key column, [(property, column, type), ...])
NODE_TYPES = [
    ("patientNode", "Patient", "gold", "gold_referral_state", "patient_id", [
        ("patientId", "patient_id", "STRING"),
        ("referralState", "referral_state", "STRING"),
        ("ageYears", "age_years", "INT"),
        ("interpreterRequired", "interpreter_required", "BOOLEAN"),
        ("criteriaFired", "criteria_fired", "INT"),
    ]),
    ("featureNode", "Feature", "gold", "gold_hpo_terms", "hpo_id", [
        ("hpoId", "hpo_id", "STRING"),
        ("hpoLabel", "hpo_label", "STRING"),
    ]),
    ("bodySystemNode", "BodySystem", "gold", "gold_body_systems", "body_system", [
        ("bodySystem", "body_system", "STRING"),
        ("termCount", "term_count", "INT"),
    ]),
    ("criterionNode", "Criterion", "gold", "gold_criteria_definitions", "criterion", [
        ("criterion", "criterion", "STRING"),
        ("tier", "tier", "STRING"),
        ("description", "description", "STRING"),
    ]),
    ("encounterNode", "Encounter", "gold", "gold_encounters", "encounter_id", [
        ("encounterId", "encounter_id", "STRING"),
        ("specialty", "specialty", "STRING"),
        ("admitted", "admitted", "BOOLEAN"),
        ("diagnosisRecorded", "diagnosis_recorded", "BOOLEAN"),
    ]),
    ("specialtyNode", "Specialty", "gold", "gold_specialties", "specialty", [
        ("specialty", "specialty", "STRING"),
        ("encounterCount", "encounter_count", "INT"),
        ("patientCount", "patient_count", "INT"),
    ]),
]

# (alias, label, source node alias, target node alias, lakehouse, table,
#  [source key columns], [target key columns], [(property, column, type), ...])
# Edge labels are all distinct -- Fabric rejects reusing one label across different
# node-type pairs.
EDGE_TYPES = [
    ("hasFeatureEdge", "hasFeature", "patientNode", "featureNode",
     "gold", "gold_observations", ["patient_id"], ["hpo_id"], [
         ("recordedBy", "recorded_by", "STRING"),
     ]),
    ("inBodySystemEdge", "inBodySystem", "featureNode", "bodySystemNode",
     "gold", "gold_hpo_terms", ["hpo_id"], ["body_system"], []),
    ("surfacedByEdge", "surfacedBy", "patientNode", "criterionNode",
     "gold", "gold_criteria_hits", ["patient_id"], ["criterion"], [
         ("tier", "tier", "STRING"),
     ]),
    ("attendedEncounterEdge", "attendedEncounter", "patientNode", "encounterNode",
     "gold", "gold_encounters", ["patient_id"], ["encounter_id"], []),
    ("encounterSpecialtyEdge", "encounterWithSpecialty", "encounterNode",
     "specialtyNode", "gold", "gold_encounters", ["encounter_id"],
     ["specialty"], []),
]


def token():
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource",
         "https://api.fabric.microsoft.com", "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=(sys.platform == "win32"))
    if result.returncode != 0:
        raise SystemExit(f"token acquisition failed:\n{result.stderr}")
    return result.stdout.strip()


def poll(response, headers, want_result=True):
    if response.status_code != 202:
        return response.json() if response.content else {}
    location = response.headers["Location"]
    for _ in range(90):
        time.sleep(5)
        state = requests.get(location, headers=headers, timeout=60).json()
        if state.get("status") == "Succeeded":
            if not want_result:
                return {}
            result = requests.get(location.rstrip("/") + "/result",
                                  headers=headers, timeout=120)
            return result.json() if result.content else {}
        if state.get("status") == "Failed":
            raise SystemExit("operation failed: " + json.dumps(state)[:600])
    raise SystemExit("operation did not finish in time")


def build_definition(workspace_id, lakehouse_ids):
    """Assemble the five definition parts.

    dataSources 1.1.0 binds tables through named *item references* rather than raw
    ABFSS URLs: each lakehouse is declared once under `itemReferences`, and every table
    names it via `properties.referenceName` with a path relative to that item. The
    published example in the REST docs shows the older 1.0.0 shape with a full abfss://
    path and no referenceName, which the service rejects.
    """
    # One data source per distinct table. Several node and edge types share a table --
    # silver_encounters backs a node type and two edge types -- and a table may only be
    # declared once.
    seen = {}
    for node in NODE_TYPES:
        seen.setdefault(node[3], node[2])
    for edge in EDGE_TYPES:
        seen.setdefault(edge[5], edge[4])

    item_references = [
        {"name": f"{short}Lakehouse",
         "item": {"workspaceId": workspace_id, "itemId": item_id}}
        for short, item_id in sorted(lakehouse_ids.items())
        if short in {lh for lh in seen.values()}
    ]

    sources = []
    for table, lakehouse in sorted(seen.items()):
        sources.append({
            "name": f"{table}_source",
            "type": "DeltaTable",
            "properties": {"referenceName": f"{lakehouse}Lakehouse",
                           "path": f"Tables/{table}"}})

    data_sources = {"$schema": SCHEMA.format(part="dataSources", version="1.1.0"),
                    "itemReferences": item_references,
                    "dataSources": sources}

    node_types, node_tables = [], []
    for alias, label, _, table, key, properties in NODE_TYPES:
        key_property = next(p for p, column, _ in properties if column == key)
        node_types.append({
            "alias": alias, "labels": [label],
            "primaryKeyProperties": [key_property],
            "properties": [{"name": p, "type": t} for p, _, t in properties]})
        node_tables.append({
            "id": f"{alias}Mapping", "nodeTypeAlias": alias,
            "dataSourceName": f"{table}_source",
            "propertyMappings": [{"propertyName": p, "sourceColumn": c}
                                 for p, c, _ in properties]})

    edge_types, edge_tables = [], []
    for (alias, label, source, target, _, table, source_keys, target_keys,
         properties) in EDGE_TYPES:
        edge_types.append({
            "alias": alias, "labels": [label],
            "sourceNodeType": {"alias": source},
            "destinationNodeType": {"alias": target},
            "properties": [{"name": p, "type": t} for p, _, t in properties]})
        edge_tables.append({
            "id": f"{alias}Mapping", "edgeTypeAlias": alias,
            "dataSourceName": f"{table}_source",
            "sourceNodeKeyColumns": source_keys,
            "destinationNodeKeyColumns": target_keys,
            "propertyMappings": [{"propertyName": p, "sourceColumn": c}
                                 for p, c, _ in properties]})

    graph_type = {"$schema": SCHEMA.format(part="graphType", version="1.0.0"),
                  "nodeTypes": node_types, "edgeTypes": edge_types}
    graph_definition = {
        "$schema": SCHEMA.format(part="graphDefinition", version="1.0.0"),
        "nodeTables": node_tables, "edgeTables": edge_tables}

    # Laid out left to right along the story the demo tells: the patient in the middle,
    # what was observed to the left, what it triggered to the right.
    positions = {
        "featureNode": {"x": -600, "y": -150}, "bodySystemNode": {"x": -1000, "y": -150},
        "patientNode": {"x": 0, "y": 0},
        "criterionNode": {"x": 600, "y": -150},
        "encounterNode": {"x": 300, "y": 350}, "specialtyNode": {"x": 800, "y": 350},
    }
    styles = {alias: {"size": 40} for alias, *_ in NODE_TYPES}
    styles.update({alias: {"size": 30} for alias, *_ in EDGE_TYPES})
    styling = {"$schema": SCHEMA.format(part="stylingConfiguration", version="1.0.0"),
               "modelLayout": {"positions": positions, "styles": styles,
                               "pan": {"x": 0, "y": 0}, "zoomLevel": 1},
               "visualFormat": None}

    # A fifth part the definition docs do not list. An empty graph model carries it, so
    # it is sent back even though it holds nothing but its schema reference.
    graph_settings = {"$schema": SCHEMA.format(part="graphSettings",
                                               version="1.0.0")}

    parts = []
    for name, payload in [("dataSources", data_sources),
                          ("graphDefinition", graph_definition),
                          ("graphType", graph_type),
                          ("stylingConfiguration", styling),
                          ("graphSettings", graph_settings)]:
        parts.append({
            "path": f"{name}.json",
            "payload": base64.b64encode(
                json.dumps(payload, indent=2).encode("utf-8")).decode(),
            "payloadType": "InlineBase64"})
    return {"parts": parts}, data_sources, graph_type


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="cicd/fabric-setup.output.json")
    parser.add_argument("--name", default="referral_graph")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the definition without deploying")
    args = parser.parse_args()

    config = json.loads(Path(args.output).read_text(encoding="utf-8"))
    workspace_id = config["workspace"]["id"]
    lakehouse_ids = {}
    for lakehouse in config["lakehouses"]:
        short = lakehouse["displayName"].replace("_lakehouse", "")
        lakehouse_ids[short] = lakehouse["id"]

    definition, sources, graph_type = build_definition(workspace_id, lakehouse_ids)

    print(f"graph model: {args.name}")
    print(f"  data sources : {len(sources['dataSources'])}")
    for source in sources["dataSources"]:
        print(f"      {source['name']:36} {source['properties']['referenceName']:18} {source['properties']['path']}")
    print(f"  node types   : {len(graph_type['nodeTypes'])}")
    for node in graph_type["nodeTypes"]:
        print(f"      {node['labels'][0]:14} key={node['primaryKeyProperties'][0]:14}"
              f" props={len(node['properties'])}")
    print(f"  edge types   : {len(graph_type['edgeTypes'])}")
    for edge in graph_type["edgeTypes"]:
        print(f"      {edge['labels'][0]:24} "
              f"{edge['sourceNodeType']['alias']} -> "
              f"{edge['destinationNodeType']['alias']}")

    if args.dry_run:
        Path("cicd/graph-model.definition.json").write_text(
            json.dumps(definition, indent=1), encoding="utf-8")
        print("\ndry run: wrote cicd/graph-model.definition.json, deployed nothing")
        return

    headers = {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}
    items = requests.get(f"{BASE}/workspaces/{workspace_id}/items",
                         headers=headers, timeout=120).json()["value"]
    existing = next((i for i in items
                     if i["displayName"] == args.name and i["type"] == "GraphModel"),
                    None)

    if existing:
        print(f"\nupdating {existing['id']}")
        poll(requests.post(
            f"{BASE}/workspaces/{workspace_id}/graphModels/{existing['id']}"
            f"/updateDefinition", headers=headers,
            data=json.dumps({"definition": definition}), timeout=600),
            headers, want_result=False)
        graph_id = existing["id"]
    else:
        print("\ncreating")
        created = poll(requests.post(
            f"{BASE}/workspaces/{workspace_id}/graphModels", headers=headers,
            data=json.dumps({"displayName": args.name,
                             "description": ("Referral case-finding graph: patients, "
                                             "observed features, body systems, "
                                             "encounters, specialties and the criteria "
                                             "that surfaced each child. Synthetic "
                                             "data. No genomic data."),
                             "definition": definition}), timeout=600), headers)
        graph_id = created.get("id")
        if not graph_id:
            items = requests.get(f"{BASE}/workspaces/{workspace_id}/items",
                                 headers=headers, timeout=120).json()["value"]
            graph_id = next(i["id"] for i in items
                            if i["displayName"] == args.name)
    print(f"graph model id: {graph_id}")
    print(f"https://app.fabric.microsoft.com/groups/{workspace_id}")

    config["graphModel"] = {"displayName": args.name, "id": graph_id}
    Path(args.output).write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"recorded in {args.output}")


if __name__ == "__main__":
    main()
