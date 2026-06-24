"""Load Rogers Finance CSVs to Delta via a Fabric Spark notebook.

The lakehouse `tables/{name}/load` LRO often sits in NotStarted on busy
trial capacity. A Spark notebook reliably gets a session in 3-5 min and
writes Delta. Mirrors rogers_demo/load_via_notebook.py.

Two-step Fabric pattern:
  1) POST /workspaces/{ws}/notebooks  with displayName only -> empty item
  2) POST /notebooks/{id}/updateDefinition -> attach the .ipynb + .platform

Then runOnDemand, poll, refreshMetadata so the SQL endpoint sees the new tables.
"""
from __future__ import annotations

import base64
import json
import subprocess
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path

ROOT = Path(__file__).parent
STACK = json.loads((ROOT / "stack_finance.json").read_text())
WS = STACK["workspace_id"]
LH = STACK["lakehouse_id"]
LH_NAME = STACK["lakehouse_name"]
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
API = "https://api.fabric.microsoft.com"
NB_NAME = "load_rogers_finance_to_delta"

TABLES = [
    "dim_date", "dim_business_unit", "dim_product", "dim_region",
    "dim_customer_segment", "dim_channel",
    "fact_revenue_monthly", "fact_subscribers_monthly",
    "fact_churn_monthly", "fact_costs_monthly",
]


def tok():
    return subprocess.check_output(
        [AZ, "account", "get-access-token", "--resource", API,
         "--query", "accessToken", "-o", "tsv"]).decode().strip()


def call(method, url, body=None):
    h = {"Authorization": f"Bearer {tok()}",
         "Content-Type": "application/json",
         "ActivityId": str(uuid.uuid4())}
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    req = urllib.request.Request(url, headers=h, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            hdrs = {k.lower(): v for k, v in r.headers.items()}
            return r.status, hdrs, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        hdrs = {k.lower(): v for k, v in e.headers.items()}
        return e.code, hdrs, e.read().decode(errors="replace")


def poll_lro(loc, label="op", attempts=180, delay=5):
    for i in range(attempts):
        time.sleep(delay)
        try:
            s, h, b = call("GET", loc)
            d = json.loads(b)
            st = d.get("status")
        except Exception as e:
            print(f"  [{label}] poll err: {e}", flush=True)
            continue
        if st == "Succeeded":
            print(f"  [{label}] OK after ~{(i+1)*delay}s", flush=True)
            return True
        if st == "Failed":
            print(f"  [{label}] FAILED: {b[:600]}", flush=True)
            return False
    print(f"  [{label}] TIMEOUT after {attempts*delay}s", flush=True)
    return False


def build_ipynb():
    code_lines = [
        "from pyspark.sql import functions as F",
        "",
        f"TABLES = {json.dumps(TABLES)}",
        "",
        "for t in TABLES:",
        "    src = f'Files/csv/{t}.csv'",
        "    print(f'Loading {t} <- {src}')",
        "    df = (spark.read",
        "          .option('header','true')",
        "          .option('inferSchema','true')",
        "          .csv(src))",
        "    (df.write.format('delta').mode('overwrite').save(f'Tables/{t}'))",
        "    print(f'  wrote Tables/{t}  rows={df.count()}')",
        "",
        "print('ALL FINANCE TABLES LOADED')",
    ]
    cell = {
        "cell_type": "code",
        "execution_count": None,
        "id": str(uuid.uuid4()),
        "metadata": {"jupyter": {"source_hidden": False, "outputs_hidden": False},
                     "microsoft": {"language": "python"},
                     "nteract": {"transient": {"deleting": False}}},
        "outputs": [],
        "source": "\n".join(code_lines) + "\n",
    }
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "cells": [cell],
        "metadata": {
            "kernel_info": {"name": "synapse_pyspark"},
            "kernelspec": {"name": "synapse_pyspark", "language": "Python",
                           "display_name": "Synapse PySpark"},
            "language_info": {"name": "python"},
            "microsoft": {"language": "python", "language_group": "synapse_pyspark"},
            "nteract": {"version": "nteract-front-end@1.0.0"},
            "spark_compute": {"compute_id": "/trident/default", "session_options": {}},
            "synapse_widget": {"version": "0.1", "state": {}},
            "trident": {"lakehouse": {
                "default_lakehouse": LH,
                "default_lakehouse_name": LH_NAME,
                "default_lakehouse_workspace_id": WS,
                "known_lakehouses": [{"id": LH}],
            }},
        },
    }


PLATFORM = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
    "metadata": {"type": "Notebook", "displayName": NB_NAME,
                 "description": "Loads Rogers Finance CSVs from Files/csv into Delta tables"},
    "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
}


def b64(s):
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def find_notebook(name):
    s, h, b = call("GET", f"{API}/v1/workspaces/{WS}/notebooks")
    for it in json.loads(b).get("value", []):
        if it.get("displayName") == name:
            return it.get("id")
    return None


def create_notebook():
    nb_id = find_notebook(NB_NAME)
    if nb_id:
        print(f"  Found existing notebook {NB_NAME} -> {nb_id}")
        return nb_id
    print(f"  Creating empty notebook {NB_NAME}...")
    s, h, b = call("POST", f"{API}/v1/workspaces/{WS}/notebooks",
                   body={"displayName": NB_NAME,
                         "description": "Loads Rogers Finance CSVs to Delta"})
    if s == 202:
        loc = h.get("location")
        if not poll_lro(loc, "create-nb"):
            return None
        sr, hr, br = call("GET", loc.rstrip("/") + "/result")
        nb_id = json.loads(br)["id"]
    elif s in (200, 201):
        nb_id = json.loads(b)["id"]
    else:
        print(f"  ERROR {s}: {b[:600]}")
        return None
    print(f"  Created {nb_id}")
    return nb_id


def push_definition(nb_id):
    ipynb = build_ipynb()
    parts = [
        {"path": "notebook-content.ipynb",
         "payload": b64(json.dumps(ipynb, indent=1)),
         "payloadType": "InlineBase64"},
        {"path": ".platform",
         "payload": b64(json.dumps(PLATFORM, indent=2)),
         "payloadType": "InlineBase64"},
    ]
    print("  POST updateDefinition...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/notebooks/{nb_id}/updateDefinition?updateMetadata=true",
                   body={"definition": {"format": "ipynb", "parts": parts}})
    if s == 202:
        return poll_lro(h.get("location"), "update-def")
    if s in (200, 201):
        return True
    print(f"  ERROR {s}: {b[:600]}")
    return False


def run_notebook(nb_id):
    print("  POST runOnDemand...")
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/items/{nb_id}/jobs/instances?jobType=RunNotebook")
    if s == 202:
        loc = h.get("location")
        for i in range(180):
            time.sleep(10)
            try:
                sp, hp, bp = call("GET", loc)
                d = json.loads(bp)
                st = d.get("status")
            except Exception as e:
                print(f"  job poll err: {e}", flush=True)
                continue
            print(f"  job status: {st}  (elapsed ~{(i+1)*10}s)", flush=True)
            if st == "Completed":
                return True
            if st in ("Failed", "Cancelled", "Deduped"):
                print(f"  job ended {st}: {bp[:600]}")
                return False
        print("  job poll TIMEOUT")
        return False
    print(f"  runOnDemand status={s}: {b[:600]}")
    return False


def refresh_sql_metadata():
    print("  refreshMetadata so SQL endpoint sees new Delta tables...")
    sqlep = STACK.get("sql_endpoint_id")
    if not sqlep:
        print("  (no sql endpoint id, skipping)")
        return
    s, h, b = call("POST",
                   f"{API}/v1/workspaces/{WS}/sqlEndpoints/{sqlep}/refreshMetadata?preview=true",
                   body={})
    print(f"  refreshMetadata status={s}")


def main():
    print("== Loading Rogers Finance data via Spark notebook ==")
    nb_id = create_notebook()
    if not nb_id:
        return
    if not push_definition(nb_id):
        return
    if not run_notebook(nb_id):
        return
    refresh_sql_metadata()
    s, h, b = call("GET", f"{API}/v1/workspaces/{WS}/lakehouses/{LH}/tables")
    tables = [t["name"] for t in json.loads(b).get("data", [])]
    print(f"\nLakehouse now has {len(tables)} tables: {tables}")


if __name__ == "__main__":
    main()
