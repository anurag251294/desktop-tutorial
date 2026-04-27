"""Create a Fabric semantic model from Gold layer tables via API."""
import os, json, urllib.request, urllib.error, base64, time

ws_id = "c41860d5-3e88-4f9d-bfa8-e2dc68d50a8e"
lh_id = "09f8932b-7c05-4bce-8bfd-a4ebfd26020b"
token = os.environ["FABRIC_TOKEN"]

# TMSL / BIM model definition for DirectLake semantic model
model_bim = {
    "compatibilityLevel": 1604,
    "model": {
        "name": "ManulifePOC_SemanticModel",
        "culture": "en-US",
        "defaultPowerBIDataSourceVersion": "powerBI_V3",
        "expressions": [
            {
                "name": "DatabaseQuery",
                "kind": "m",
                "expression": [
                    "let",
                    "    database = Sql.Database(\"cluwj7r47duuje4j6zubfr72k4-2vqbrreih2ou7p5i4logrvikry.datawarehouse.fabric.microsoft.com\", \"" + lh_id + "\")",
                    "in",
                    "    database"
                ]
            }
        ],
        "tables": [
            {
                "name": "dim_customer",
                "columns": [
                    {"name": "customer_id", "dataType": "string", "sourceColumn": "customer_id", "summarizeBy": "none"},
                    {"name": "first_name", "dataType": "string", "sourceColumn": "first_name", "summarizeBy": "none"},
                    {"name": "last_name", "dataType": "string", "sourceColumn": "last_name", "summarizeBy": "none"},
                    {"name": "city", "dataType": "string", "sourceColumn": "city", "summarizeBy": "none"},
                    {"name": "province", "dataType": "string", "sourceColumn": "province", "summarizeBy": "none"},
                    {"name": "customer_segment", "dataType": "string", "sourceColumn": "customer_segment", "summarizeBy": "none"},
                    {"name": "age", "dataType": "int64", "sourceColumn": "age", "summarizeBy": "none"},
                    {"name": "age_band", "dataType": "string", "sourceColumn": "age_band", "summarizeBy": "none"},
                    {"name": "gender", "dataType": "string", "sourceColumn": "gender", "summarizeBy": "none"},
                ],
                "partitions": [{
                    "name": "partition",
                    "mode": "directLake",
                    "source": {"type": "entity", "entityName": "gold_dim_customer", "schemaName": "dbo", "expressionSource": "DatabaseQuery"}
                }]
            },
            {
                "name": "dim_product",
                "columns": [
                    {"name": "product_id", "dataType": "string", "sourceColumn": "product_id", "summarizeBy": "none"},
                    {"name": "product_name", "dataType": "string", "sourceColumn": "product_name", "summarizeBy": "none"},
                    {"name": "product_category", "dataType": "string", "sourceColumn": "product_category", "summarizeBy": "none"},
                    {"name": "product_line", "dataType": "string", "sourceColumn": "product_line", "summarizeBy": "none"},
                    {"name": "risk_tier", "dataType": "string", "sourceColumn": "risk_tier", "summarizeBy": "none"},
                ],
                "partitions": [{
                    "name": "partition",
                    "mode": "directLake",
                    "source": {"type": "entity", "entityName": "gold_dim_product", "schemaName": "dbo", "expressionSource": "DatabaseQuery"}
                }]
            },
            {
                "name": "dim_advisor",
                "columns": [
                    {"name": "advisor_id", "dataType": "string", "sourceColumn": "advisor_id", "summarizeBy": "none"},
                    {"name": "first_name", "dataType": "string", "sourceColumn": "first_name", "summarizeBy": "none"},
                    {"name": "last_name", "dataType": "string", "sourceColumn": "last_name", "summarizeBy": "none"},
                    {"name": "region", "dataType": "string", "sourceColumn": "region", "summarizeBy": "none"},
                    {"name": "branch_office", "dataType": "string", "sourceColumn": "branch_office", "summarizeBy": "none"},
                    {"name": "certification_level", "dataType": "string", "sourceColumn": "certification_level", "summarizeBy": "none"},
                    {"name": "specialization", "dataType": "string", "sourceColumn": "specialization", "summarizeBy": "none"},
                ],
                "partitions": [{
                    "name": "partition",
                    "mode": "directLake",
                    "source": {"type": "entity", "entityName": "gold_dim_advisor", "schemaName": "dbo", "expressionSource": "DatabaseQuery"}
                }]
            },
            {
                "name": "dim_policy",
                "columns": [
                    {"name": "policy_id", "dataType": "string", "sourceColumn": "policy_id", "summarizeBy": "none"},
                    {"name": "customer_id", "dataType": "string", "sourceColumn": "customer_id", "summarizeBy": "none"},
                    {"name": "policy_type", "dataType": "string", "sourceColumn": "policy_type", "summarizeBy": "none"},
                    {"name": "status", "dataType": "string", "sourceColumn": "status", "summarizeBy": "none"},
                    {"name": "payment_frequency", "dataType": "string", "sourceColumn": "payment_frequency", "summarizeBy": "none"},
                    {"name": "risk_category", "dataType": "string", "sourceColumn": "risk_category", "summarizeBy": "none"},
                ],
                "partitions": [{
                    "name": "partition",
                    "mode": "directLake",
                    "source": {"type": "entity", "entityName": "gold_dim_policy", "schemaName": "dbo", "expressionSource": "DatabaseQuery"}
                }]
            },
            {
                "name": "fact_claims",
                "columns": [
                    {"name": "claim_id", "dataType": "string", "sourceColumn": "claim_id", "summarizeBy": "none"},
                    {"name": "policy_id", "dataType": "string", "sourceColumn": "policy_id", "summarizeBy": "none"},
                    {"name": "customer_id", "dataType": "string", "sourceColumn": "customer_id", "summarizeBy": "none"},
                    {"name": "claim_amount", "dataType": "double", "sourceColumn": "claim_amount", "summarizeBy": "sum"},
                    {"name": "approved_amount", "dataType": "double", "sourceColumn": "approved_amount", "summarizeBy": "sum"},
                    {"name": "claim_type", "dataType": "string", "sourceColumn": "claim_type", "summarizeBy": "none"},
                    {"name": "status", "dataType": "string", "sourceColumn": "status", "summarizeBy": "none"},
                    {"name": "processing_days", "dataType": "int64", "sourceColumn": "processing_days", "summarizeBy": "average"},
                ],
                "partitions": [{
                    "name": "partition",
                    "mode": "directLake",
                    "source": {"type": "entity", "entityName": "gold_fact_claims", "schemaName": "dbo", "expressionSource": "DatabaseQuery"}
                }],
                "measures": [
                    {"name": "Total Claims Amount", "expression": "SUM(fact_claims[claim_amount])", "formatString": "$#,##0"},
                    {"name": "Total Approved Amount", "expression": "SUM(fact_claims[approved_amount])", "formatString": "$#,##0"},
                    {"name": "Claim Count", "expression": "COUNTROWS(fact_claims)", "formatString": "#,##0"},
                    {"name": "Average Processing Days", "expression": "AVERAGE(fact_claims[processing_days])", "formatString": "#,##0.0"},
                ]
            },
            {
                "name": "fact_transactions",
                "columns": [
                    {"name": "transaction_id", "dataType": "string", "sourceColumn": "transaction_id", "summarizeBy": "none"},
                    {"name": "customer_id", "dataType": "string", "sourceColumn": "customer_id", "summarizeBy": "none"},
                    {"name": "amount", "dataType": "double", "sourceColumn": "amount", "summarizeBy": "sum"},
                    {"name": "transaction_type", "dataType": "string", "sourceColumn": "transaction_type", "summarizeBy": "none"},
                    {"name": "payment_method", "dataType": "string", "sourceColumn": "payment_method", "summarizeBy": "none"},
                ],
                "partitions": [{
                    "name": "partition",
                    "mode": "directLake",
                    "source": {"type": "entity", "entityName": "gold_fact_transactions", "schemaName": "dbo", "expressionSource": "DatabaseQuery"}
                }],
                "measures": [
                    {"name": "Total Transaction Amount", "expression": "SUM(fact_transactions[amount])", "formatString": "$#,##0"},
                    {"name": "Transaction Count", "expression": "COUNTROWS(fact_transactions)", "formatString": "#,##0"},
                ]
            },
            {
                "name": "fact_investments",
                "columns": [
                    {"name": "investment_id", "dataType": "string", "sourceColumn": "investment_id", "summarizeBy": "none"},
                    {"name": "customer_id", "dataType": "string", "sourceColumn": "customer_id", "summarizeBy": "none"},
                    {"name": "investment_amount", "dataType": "double", "sourceColumn": "investment_amount", "summarizeBy": "sum"},
                    {"name": "current_value", "dataType": "double", "sourceColumn": "current_value", "summarizeBy": "sum"},
                    {"name": "fund_name", "dataType": "string", "sourceColumn": "fund_name", "summarizeBy": "none"},
                    {"name": "fund_type", "dataType": "string", "sourceColumn": "fund_type", "summarizeBy": "none"},
                    {"name": "region", "dataType": "string", "sourceColumn": "region", "summarizeBy": "none"},
                    {"name": "return_ytd_pct", "dataType": "double", "sourceColumn": "return_ytd_pct", "summarizeBy": "average"},
                ],
                "partitions": [{
                    "name": "partition",
                    "mode": "directLake",
                    "source": {"type": "entity", "entityName": "gold_fact_investments", "schemaName": "dbo", "expressionSource": "DatabaseQuery"}
                }],
                "measures": [
                    {"name": "Total AUM", "expression": "SUM(fact_investments[current_value])", "formatString": "$#,##0"},
                    {"name": "Total Investment Inflows", "expression": "SUM(fact_investments[investment_amount])", "formatString": "$#,##0"},
                    {"name": "Average Return YTD", "expression": "AVERAGE(fact_investments[return_ytd_pct])", "formatString": "0.00%"},
                ]
            },
            {
                "name": "fact_policy_premiums",
                "columns": [
                    {"name": "policy_id", "dataType": "string", "sourceColumn": "policy_id", "summarizeBy": "none"},
                    {"name": "customer_id", "dataType": "string", "sourceColumn": "customer_id", "summarizeBy": "none"},
                    {"name": "premium_amount", "dataType": "double", "sourceColumn": "premium_amount", "summarizeBy": "sum"},
                    {"name": "coverage_amount", "dataType": "double", "sourceColumn": "coverage_amount", "summarizeBy": "sum"},
                    {"name": "policy_type", "dataType": "string", "sourceColumn": "policy_type", "summarizeBy": "none"},
                    {"name": "status", "dataType": "string", "sourceColumn": "status", "summarizeBy": "none"},
                ],
                "partitions": [{
                    "name": "partition",
                    "mode": "directLake",
                    "source": {"type": "entity", "entityName": "gold_fact_policy_premiums", "schemaName": "dbo", "expressionSource": "DatabaseQuery"}
                }],
                "measures": [
                    {"name": "Total Premium Revenue", "expression": "SUM(fact_policy_premiums[premium_amount])", "formatString": "$#,##0"},
                    {"name": "Total Coverage", "expression": "SUM(fact_policy_premiums[coverage_amount])", "formatString": "$#,##0"},
                    {"name": "Policy Count", "expression": "COUNTROWS(fact_policy_premiums)", "formatString": "#,##0"},
                ]
            },
        ],
        "relationships": [
            {"name": "r1", "fromTable": "fact_claims", "fromColumn": "customer_id", "toTable": "dim_customer", "toColumn": "customer_id"},
            {"name": "r2", "fromTable": "fact_transactions", "fromColumn": "customer_id", "toTable": "dim_customer", "toColumn": "customer_id"},
            {"name": "r3", "fromTable": "fact_investments", "fromColumn": "customer_id", "toTable": "dim_customer", "toColumn": "customer_id"},
            {"name": "r4", "fromTable": "fact_policy_premiums", "fromColumn": "customer_id", "toTable": "dim_customer", "toColumn": "customer_id"},
            {"name": "r5", "fromTable": "fact_claims", "fromColumn": "policy_id", "toTable": "dim_policy", "toColumn": "policy_id"},
            {"name": "r6", "fromTable": "fact_policy_premiums", "fromColumn": "policy_id", "toTable": "dim_policy", "toColumn": "policy_id"},
        ],
    }
}

model_b64 = base64.b64encode(json.dumps(model_bim).encode()).decode()

# PBISM file - minimal Fabric format
pbism_content = {
    "version": "1.0"
}
pbism_b64 = base64.b64encode(json.dumps(pbism_content).encode()).decode()

payload = {
    "displayName": "ManulifePOC_SemanticModel",
    "description": "Semantic model for Manulife POC with DAX measures for claims, premiums, investments, and transactions",
    "definition": {
        "parts": [
            {
                "path": "model.bim",
                "payload": model_b64,
                "payloadType": "InlineBase64"
            },
            {
                "path": "definition.pbism",
                "payload": pbism_b64,
                "payloadType": "InlineBase64"
            }
        ]
    }
}

url = f"https://api.fabric.microsoft.com/v1/workspaces/{ws_id}/semanticModels"
data = json.dumps(payload).encode()
req = urllib.request.Request(url, data=data, method="POST")
req.add_header("Authorization", f"Bearer {token}")
req.add_header("Content-Type", "application/json")

try:
    resp = urllib.request.urlopen(req)
    body = resp.read().decode()
    location = resp.headers.get("Location", "")
    print(f"Status: {resp.status}")
    try:
        if body and body.strip() and body.strip() != "null":
            result = json.loads(body)
            if result:
                print(f"Semantic Model ID: {result.get('id')}")
                print(f"Name: {result.get('displayName')}")
            else:
                print("Empty response body (async creation)")
        else:
            print("No body (async creation)")
    except (json.JSONDecodeError, TypeError):
        print(f"Non-JSON response: {body[:100]}")

    if resp.status == 202 and location:
        print("Polling for completion...")
        for i in range(20):
            time.sleep(10)
            req2 = urllib.request.Request(location)
            req2.add_header("Authorization", f"Bearer {token}")
            try:
                resp2 = urllib.request.urlopen(req2)
                pdata = json.loads(resp2.read().decode())
                status = pdata.get("status", "?")
                print(f"  [{i}] {status}")
                if status in ("Succeeded", "Failed"):
                    if status == "Failed":
                        print(f"  Error: {json.dumps(pdata.get('error', {}))}")
                    break
            except urllib.error.HTTPError as e:
                if e.code == 202:
                    continue
                print(f"  Poll error: {e.code}")

except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"Error {e.code}: {body[:500]}")
