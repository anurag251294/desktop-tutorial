"""Create the Direct Lake semantic model over the TCHC gold layer.

    python scripts/fabric/create_semantic_model.py --output cicd/fabric-setup.output.json

Direct Lake reads the Delta files directly through the lakehouse SQL analytics endpoint —
no import, no scheduled refresh, no second copy of the data. Two consequences worth
knowing before the demo:

  * The SQL endpoint must have synced its metadata after Spark writes new tables, or the
    model is created against tables the endpoint cannot see yet. This script forces that
    sync and waits.
  * Direct Lake does not allow calculated columns. Anything that would have been a
    calculated column belongs in the Gold notebook instead, which is why the star schema
    carries denormalised grain columns.
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
MODEL_NAME = "TCHC_Arrears_Vacancy"


def token(resource="https://api.fabric.microsoft.com"):
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=(sys.platform == "win32"))
    if result.returncode != 0:
        raise SystemExit(f"token acquisition failed:\n{result.stderr}")
    return result.stdout.strip()


def column(name, data_type, summarize="none", source=None, fmt=None, hidden=False):
    entry = {"name": name, "dataType": data_type,
             "sourceColumn": source or name, "summarizeBy": summarize}
    if fmt:
        entry["formatString"] = fmt
    if hidden:
        entry["isHidden"] = True
    return entry


def table(name, entity, columns, measures=None):
    return {
        "name": name,
        "columns": columns,
        "partitions": [{
            "name": f"{name}_partition",
            "mode": "directLake",
            "source": {"type": "entity", "entityName": entity, "schemaName": "dbo",
                       "expressionSource": "DatabaseQuery"},
        }],
        **({"measures": measures} if measures else {}),
    }


def build_model(sql_endpoint, endpoint_database_id):
    """TMSL for the arrears and vacancy model."""
    return {
        "compatibilityLevel": 1604,
        "model": {
            "name": MODEL_NAME,
            "culture": "en-CA",
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "expressions": [{
                "name": "DatabaseQuery",
                "kind": "m",
                "expression": [
                    "let",
                    f'    database = Sql.Database("{sql_endpoint}", "{endpoint_database_id}")',
                    "in",
                    "    database",
                ],
            }],
            "tables": [
                table("Date", "gold_dim_date", [
                    column("date", "dateTime", source="date", fmt="Short Date"),
                    column("date_key", "int64", hidden=True),
                    column("year", "int64"),
                    column("quarter", "int64"),
                    column("month_number", "int64", hidden=True),
                    column("month_name", "string"),
                    column("period_start", "dateTime", fmt="Short Date"),
                    column("fiscal_year", "string"),
                ]),
                table("Building", "gold_dim_building", [
                    column("building_id", "string"),
                    column("building_name", "string"),
                    column("ward_name", "string"),
                    column("region", "string"),
                    column("property_type", "string"),
                    column("year_built", "int64"),
                    column("total_units", "int64", summarize="sum"),
                ]),
                table("Unit", "gold_dim_unit", [
                    column("unit_id", "string"),
                    column("building_id", "string", hidden=True),
                    column("building_name", "string"),
                    column("ward_name", "string"),
                    column("region", "string"),
                    column("property_type", "string"),
                    column("unit_number", "string"),
                    column("bedroom_count", "int64"),
                    column("unit_size", "string"),
                    column("tenure_type", "string"),
                    column("is_accessible", "boolean"),
                ]),
                table("Household", "gold_dim_household", [
                    column("household_key", "string"),
                    column("unit_id", "string", hidden=True),
                    column("household_size", "int64"),
                    column("income_band", "string"),
                    column("tenure_type", "string"),
                    column("move_in_date", "dateTime", fmt="Short Date"),
                    column("move_out_date", "dateTime", fmt="Short Date"),
                    column("tenancy_status", "string"),
                ]),
                table("Arrears", "gold_fact_arrears_snapshot", [
                    column("household_key", "string", hidden=True),
                    column("unit_id", "string", hidden=True),
                    column("building_id", "string", hidden=True),
                    column("date_key", "int64", hidden=True),
                    column("period_start", "dateTime", fmt="Short Date"),
                    column("ward_name", "string"),
                    column("region", "string"),
                    column("tenure_type", "string"),
                    column("unit_size", "string"),
                    column("charge_raised", "decimal", summarize="sum", fmt="\\$#,##0"),
                    column("receipts_applied", "decimal", summarize="sum", fmt="\\$#,##0"),
                    column("closing_balance", "decimal", summarize="sum", fmt="\\$#,##0"),
                    column("arrears_bucket", "string"),
                    column("months_in_arrears", "int64"),
                    column("is_in_arrears", "boolean"),
                ], measures=[
                    {"name": "Total Arrears",
                     "expression": "CALCULATE(SUM(Arrears[closing_balance]), LASTNONBLANK(Arrears[period_start], CALCULATE(COUNTROWS(Arrears))))",
                     "formatString": "\\$#,##0",
                     "description": "Closing balance owed at the selected period end. Semi-additive: a balance is not summed across time, so this takes the last snapshot in the current date filter."},
                    {"name": "Households in Arrears",
                     "expression": "CALCULATE(DISTINCTCOUNT(Arrears[household_key]), "
                                   "Arrears[is_in_arrears] = TRUE(), "
                                   "LASTNONBLANK(Arrears[period_start], CALCULATE(COUNTROWS(Arrears))))",
                     "formatString": "#,##0"},
                    {"name": "Households Charged",
                     "expression": "CALCULATE(DISTINCTCOUNT(Arrears[household_key]), "
                                   "LASTNONBLANK(Arrears[period_start], CALCULATE(COUNTROWS(Arrears))))",
                     "formatString": "#,##0"},
                    {"name": "Arrears Rate",
                     "expression": "DIVIDE([Households in Arrears], [Households Charged])",
                     "formatString": "0.0%",
                     "description": "Share of charged households carrying any balance."},
                    {"name": "Average Arrears per Household",
                     "expression": "DIVIDE([Total Arrears], [Households in Arrears])",
                     "formatString": "\\$#,##0"},
                    {"name": "Arrears Over 90 Days",
                     "expression": "CALCULATE([Total Arrears], "
                                   "Arrears[arrears_bucket] = \"Over 90 days\")",
                     "formatString": "\\$#,##0",
                     "description": "The balance least likely to be recovered."},
                    {"name": "Over 90 Day Share",
                     "expression": "DIVIDE([Arrears Over 90 Days], [Total Arrears])",
                     "formatString": "0.0%"},
                    {"name": "Rent Charged",
                     "expression": "SUM(Arrears[charge_raised])",
                     "formatString": "\\$#,##0"},
                    {"name": "Rent Collected",
                     "expression": "SUM(Arrears[receipts_applied])",
                     "formatString": "\\$#,##0"},
                    {"name": "Collection Rate",
                     "expression": "DIVIDE([Rent Collected], [Rent Charged])",
                     "formatString": "0.0%",
                     "description": "Receipts applied against charges raised in period. A flow, so unlike the balance measures this one is additive across time."},
                    {"name": "Arrears MoM Change",
                     "expression": "VAR Prior = CALCULATE([Total Arrears], "
                                   "DATEADD('Date'[date], -1, MONTH)) "
                                   "RETURN [Total Arrears] - Prior",
                     "formatString": "\\$#,##0;(\\$#,##0)"},
                ]),
                table("UnitMonth", "gold_fact_unit_month", [
                    column("unit_id", "string", hidden=True),
                    column("building_id", "string", hidden=True),
                    column("date_key", "int64", hidden=True),
                    column("period_start", "dateTime", fmt="Short Date"),
                    column("ward_name", "string"),
                    column("region", "string"),
                    column("tenure_type", "string"),
                    column("unit_size", "string"),
                    column("occupied_flag", "int64", summarize="sum"),
                    column("vacant_flag", "int64", summarize="sum"),
                    column("revenue_forgone", "decimal", summarize="sum",
                           fmt="\\$#,##0"),
                ], measures=[
                    {"name": "Units", "expression": "CALCULATE(DISTINCTCOUNT(UnitMonth[unit_id]), "
                                   "LASTNONBLANK(UnitMonth[period_start], CALCULATE(COUNTROWS(UnitMonth))))",
                     "formatString": "#,##0"},
                    {"name": "Units Vacant",
                     "expression": "CALCULATE(SUM(UnitMonth[vacant_flag]), LASTNONBLANK(UnitMonth[period_start], CALCULATE(COUNTROWS(UnitMonth))))",
                     "formatString": "#,##0"},
                    {"name": "Units Occupied",
                     "expression": "CALCULATE(SUM(UnitMonth[occupied_flag]), LASTNONBLANK(UnitMonth[period_start], CALCULATE(COUNTROWS(UnitMonth))))",
                     "formatString": "#,##0"},
                    {"name": "Vacancy Rate",
                     "expression": "DIVIDE([Units Vacant], "
                                   "[Units Vacant] + [Units Occupied])",
                     "formatString": "0.0%"},
                    {"name": "Revenue Forgone",
                     "expression": "SUM(UnitMonth[revenue_forgone])",
                     "formatString": "\\$#,##0",
                     "description": "Expected rent on units that were vacant."},
                ]),
                table("Turnaround", "gold_fact_turnaround", [
                    column("work_order_id", "string", hidden=True),
                    column("unit_id", "string", hidden=True),
                    column("building_id", "string", hidden=True),
                    column("date_key", "int64", hidden=True),
                    column("ward_name", "string"),
                    column("region", "string"),
                    column("tenure_type", "string"),
                    column("unit_size", "string"),
                    column("vacated_date", "dateTime", fmt="Short Date"),
                    column("ready_to_rent_date", "dateTime", fmt="Short Date"),
                    column("turnaround_category", "string"),
                    column("turnaround_days", "int64", summarize="sum"),
                    column("is_complete", "boolean"),
                ], measures=[
                    {"name": "Turnarounds Completed",
                     "expression": "CALCULATE(COUNTROWS(Turnaround), "
                                   "Turnaround[is_complete] = TRUE())",
                     "formatString": "#,##0"},
                    {"name": "Average Turnaround Days",
                     "expression": "CALCULATE(AVERAGE(Turnaround[turnaround_days]), "
                                   "Turnaround[is_complete] = TRUE())",
                     "formatString": "#,##0.0",
                     "description": "Vacate to ready-to-rent. Open work orders are "
                                    "excluded rather than counted as zero."},
                    {"name": "Turnarounds Open",
                     "expression": "CALCULATE(COUNTROWS(Turnaround), "
                                   "Turnaround[is_complete] = FALSE())",
                     "formatString": "#,##0"},
                ]),
            ],
            "relationships": [
                {"name": "Arrears_Date", "fromTable": "Arrears",
                 "fromColumn": "period_start", "toTable": "Date", "toColumn": "date"},
                {"name": "Arrears_Household", "fromTable": "Arrears",
                 "fromColumn": "household_key", "toTable": "Household",
                 "toColumn": "household_key"},
                {"name": "Arrears_Unit", "fromTable": "Arrears", "fromColumn": "unit_id",
                 "toTable": "Unit", "toColumn": "unit_id"},
                {"name": "UnitMonth_Date", "fromTable": "UnitMonth",
                 "fromColumn": "period_start", "toTable": "Date", "toColumn": "date"},
                {"name": "UnitMonth_Unit", "fromTable": "UnitMonth",
                 "fromColumn": "unit_id", "toTable": "Unit", "toColumn": "unit_id"},
                {"name": "Turnaround_Unit", "fromTable": "Turnaround",
                 "fromColumn": "unit_id", "toTable": "Unit", "toColumn": "unit_id"},
                {"name": "Turnaround_Date", "fromTable": "Turnaround",
                 "fromColumn": "vacated_date", "toTable": "Date", "toColumn": "date"},
                {"name": "Unit_Building", "fromTable": "Unit",
                 "fromColumn": "building_id", "toTable": "Building",
                 "toColumn": "building_id"},
            ],
        },
    }


def refresh_sql_endpoint(workspace_id, endpoint_id, headers):
    """Spark writes are invisible to the SQL endpoint until it syncs its metadata."""
    response = requests.post(
        f"{BASE}/workspaces/{workspace_id}/sqlEndpoints/{endpoint_id}"
        f"/refreshMetadata?preview=true",
        headers=headers, data=json.dumps({"timeout": {"timeUnit": "Seconds",
                                                      "value": 180}}), timeout=300)
    print(f"  refreshMetadata: {response.status_code}")
    if response.status_code == 202:
        location = response.headers.get("Location")
        for _ in range(45):
            time.sleep(5)
            state = requests.get(location, headers=headers, timeout=120).json()
            if state.get("status") in ("Succeeded", "Failed"):
                print(f"    -> {state.get('status')}")
                return
    elif response.ok:
        synced = [row for row in response.json()
                  if row.get("status") not in ("Success", "NotRun")]
        print(f"    tables reporting an issue: {len(synced)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="cicd/fabric-setup.output.json")
    parser.add_argument("--name", default=MODEL_NAME)
    args = parser.parse_args()

    deployment = json.loads(Path(args.output).read_text(encoding="utf-8"))
    workspace_id = deployment["workspace"]["id"]
    headers = {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}

    items = requests.get(f"{BASE}/workspaces/{workspace_id}/items",
                         headers=headers, timeout=180).json()["value"]
    gold = next(i for i in items
                if i["type"] == "Lakehouse" and i["displayName"] == "gold_lakehouse")
    endpoint_item = next(i for i in items
                         if i["type"] == "SQLEndpoint"
                         and i["displayName"] == "gold_lakehouse")

    detail = requests.get(
        f"{BASE}/workspaces/{workspace_id}/lakehouses/{gold['id']}",
        headers=headers, timeout=180).json()
    properties = detail.get("properties", {}).get("sqlEndpointProperties", {})
    sql_endpoint = properties.get("connectionString")
    if not sql_endpoint:
        raise SystemExit("lakehouse has no SQL endpoint connection string yet")

    print(f"gold lakehouse : {gold['id']}")
    print(f"sql endpoint   : {sql_endpoint}")

    print("\nsyncing SQL endpoint metadata so Direct Lake can see the Delta tables")
    refresh_sql_endpoint(workspace_id, endpoint_item["id"], headers)

    # The database argument is the SQL endpoint id. Passing the lakehouse item id
    # creates a model that queries with DM_InvalidRequest_DatamartNotFound.
    endpoint_database_id = properties.get("id") or endpoint_item["id"]
    print(f"endpoint db id : {endpoint_database_id}")
    model = build_model(sql_endpoint, endpoint_database_id)
    parts = [
        {"path": "model.bim",
         "payload": base64.b64encode(json.dumps(model).encode()).decode(),
         "payloadType": "InlineBase64"},
        {"path": "definition.pbism",
         "payload": base64.b64encode(json.dumps({"version": "1.0"}).encode()).decode(),
         "payloadType": "InlineBase64"},
    ]

    existing = next((i for i in items if i["type"] == "SemanticModel"
                     and i["displayName"] == args.name), None)
    if existing:
        response = requests.post(
            f"{BASE}/workspaces/{workspace_id}/semanticModels/{existing['id']}"
            "/updateDefinition",
            headers=headers,
            data=json.dumps({"definition": {"parts": parts}}), timeout=600)
        model_id = existing["id"]
        print(f"\nupdated semantic model: {model_id} ({response.status_code})")
    else:
        response = requests.post(
            f"{BASE}/workspaces/{workspace_id}/semanticModels", headers=headers,
            data=json.dumps({"displayName": args.name,
                             "description": "Arrears and vacancy over the TCHC gold "
                                            "layer. Direct Lake, no import, no refresh "
                                            "schedule.",
                             "definition": {"parts": parts}}), timeout=600)
        print(f"\ncreate: {response.status_code}")
        if response.status_code == 202:
            location = response.headers.get("Location")
            for _ in range(60):
                time.sleep(5)
                state = requests.get(location, headers=headers, timeout=120)
                payload = state.json()
                if payload.get("status") == "Succeeded":
                    model_id = requests.get(location.rstrip("/") + "/result",
                                            headers=headers, timeout=120).json()["id"]
                    break
                if payload.get("status") == "Failed":
                    raise SystemExit(json.dumps(payload)[:600])
            else:
                raise SystemExit("create did not settle")
        elif response.ok:
            model_id = response.json()["id"]
        else:
            raise SystemExit(f"{response.status_code}: {response.text[:600]}")
        print(f"semantic model: {model_id}")

    deployment["semanticModel"] = {"id": model_id, "name": args.name,
                                   "sqlEndpoint": sql_endpoint}
    Path(args.output).write_text(json.dumps(deployment, indent=2), encoding="utf-8")

    tables = model["model"]["tables"]
    measures = sum(len(t.get("measures", [])) for t in tables)
    print(f"\n{len(tables)} tables, {measures} measures, "
          f"{len(model['model']['relationships'])} relationships")
    print(f"open: https://app.fabric.microsoft.com/groups/{workspace_id}")


if __name__ == "__main__":
    main()
