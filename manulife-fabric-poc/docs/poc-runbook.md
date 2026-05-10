# Manulife Fabric POC -- Step-by-Step Runbook

**Version:** 1.0
**Last Updated:** 2026-04-24
**Authors:** Anurag Dhuria, Microsoft Partner Engineering
**Status:** Draft -- POC
**Estimated Duration:** 2-3 days for a prepared team

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Step 1: Provision Fabric Workspace](#step-1-provision-fabric-workspace)
3. [Step 2: Create Lakehouse](#step-2-create-lakehouse)
4. [Step 3: Upload Raw Data](#step-3-upload-raw-data)
5. [Step 4: Run Data Transformation Notebooks](#step-4-run-data-transformation-notebooks)
6. [Step 5: Create Semantic Model](#step-5-create-semantic-model)
7. [Step 6: Configure Azure AI Search (Unstructured Data)](#step-6-configure-azure-ai-search-for-unstructured)
8. [Step 7: Configure Fabric Data Agent](#step-7-configure-fabric-data-agent)
9. [Step 8: Set Up Orchestration (Optional)](#step-8-set-up-orchestration-optional)
10. [Step 9: Validate POC](#step-9-validate-poc)
11. [Step 10: Demo Preparation](#step-10-demo-preparation)
12. [Appendix A: Troubleshooting Reference](#appendix-a-troubleshooting-reference)
13. [Appendix B: Resource Naming Conventions](#appendix-b-resource-naming-conventions)

---

## Prerequisites

### Azure Subscription

| Requirement | Details |
|---|---|
| Azure subscription | Active subscription with Contributor access |
| Resource group | Create `rg-manulife-fabric-poc` in **Canada Central** (data residency) |
| Azure AD tenant | Tenant with Power BI Pro or Premium Per User licenses for all participants |
| Spending limit | Ensure subscription has no spending cap or has sufficient budget (~$500-1000/month for POC) |

### Microsoft Fabric Capacity

| Requirement | Details |
|---|---|
| Capacity SKU | **F64 or higher** recommended for POC (F64 = 64 CUs, supports Data Agent, notebooks, Direct Lake) |
| Minimum viable | F32 works for basic scenarios but Data Agent performance may be limited |
| Trial option | Fabric trial capacity (60-day, F64 equivalent) can be activated at `app.fabric.microsoft.com` |
| Region | Canada Central (align with data residency requirements) |

### Fabric Tenant Settings

The following tenant settings must be enabled by a Fabric admin. Navigate to **Fabric Admin Portal > Tenant Settings**.

| Setting | Location | Required Value |
|---|---|---|
| Users can create Fabric items | Fabric settings | Enabled (for POC security group) |
| Users can use Copilot and AI features | Copilot and Azure OpenAI Service | Enabled |
| Data sent to Azure OpenAI can be processed outside your tenant's geographic region | Copilot and Azure OpenAI Service | Enabled (required for Canada Central -- AI services may route through US) |
| Users can create and use Data Agents (preview) | Copilot and Azure OpenAI Service | Enabled |
| Service principals can use Fabric APIs | Developer settings | Enabled (if using automation) |
| Allow XMLA endpoints | Integration settings | Enabled (Read/Write) |
| Users can access data stored in OneLake with apps external to Fabric | OneLake settings | Enabled |

### Azure AI Services (for Unstructured Data)

| Service | SKU | Purpose |
|---|---|---|
| Azure AI Search | Standard (S1) | Document indexing, vector search, semantic ranking |
| Azure OpenAI Service | Standard | Text embeddings (text-embedding-ada-002 or text-embedding-3-large), GPT-4o for orchestration |
| Azure AI Document Intelligence (optional) | S0 | Enhanced document cracking for scanned PDFs |

### Permissions and Roles

| Person/Identity | Required Roles |
|---|---|
| POC Lead | Fabric Admin (or workspace admin), Azure Subscription Contributor |
| Data Engineers | Fabric workspace Contributor role |
| Report Builders | Fabric workspace Member or Contributor |
| Service Principal (if used) | Fabric workspace Contributor, Storage Blob Data Contributor on ADLS |
| All participants | Power BI Pro license (or PPU) |

### Software/Tools

| Tool | Purpose |
|---|---|
| Power BI Desktop | Semantic model authoring (latest version -- download from powerbi.microsoft.com) |
| Azure CLI | Resource provisioning (`az` commands) |
| Azure Storage Explorer (optional) | Inspect OneLake files |
| Browser | Microsoft Edge or Chrome (Fabric portal) |
| VS Code with Fabric extension (optional) | Notebook development |

---

## Step 1: Provision Fabric Workspace

### What To Do

Create a dedicated Fabric workspace for the Manulife POC and assign it to a Fabric capacity.

### How To Do It

1. Navigate to [https://app.fabric.microsoft.com](https://app.fabric.microsoft.com).
2. Sign in with your organizational account.
3. In the left navigation pane, click **Workspaces**.
4. Click **+ New workspace**.
5. Configure the workspace:
   - **Name:** `Manulife-Fabric-POC`
   - **Description:** `Proof of concept for Manulife insurance and investment analytics using Microsoft Fabric, including structured data in Lakehouse, semantic model, and Data Agent.`
6. Expand **Advanced** settings:
   - **License mode:** Select **Fabric capacity** (or **Trial** if using trial capacity).
   - **Capacity:** Select the F64 capacity provisioned for the POC.
   - **Default storage format:** **Delta/Parquet** (leave default).
7. Click **Apply**.
8. After creation, click the **gear icon** (workspace settings) in the top right:
   - Under **General**, verify the capacity assignment.
   - Under **OneLake**, verify "Allow data to be accessed via OneLake" is enabled.
9. Add team members under **Manage access**:
   - Add POC team members as **Contributor** or **Member**.

### Expected Outcome

- Workspace `Manulife-Fabric-POC` appears in the workspace list.
- Workspace is assigned to Fabric capacity (visible in settings).
- All team members can access the workspace.

### Common Issues

| Issue | Resolution |
|---|---|
| "No capacity available" when creating workspace | Verify the Fabric capacity is provisioned and running in Azure portal (Fabric Capacities resource). The capacity may be paused. |
| Workspace created but Data Agent option not visible | Data Agent tenant setting is not enabled. Ask Fabric admin to enable it (see Prerequisites). |
| Team members cannot see workspace | Ensure they have been added via Manage access and have accepted any pending invitations. |

---

## Step 2: Create Lakehouse

### What To Do

Create a Fabric Lakehouse that will serve as the central data store with Bronze/Silver/Gold layers.

### How To Do It

1. In the `Manulife-Fabric-POC` workspace, click **+ New item**.
2. Under **Data Engineering**, select **Lakehouse**.
3. Name the Lakehouse: `lh_manulife_poc`.
4. Click **Create**.
5. Once the Lakehouse opens, you will see two sections:
   - **Tables** (managed Delta tables -- this is where Gold layer tables will live)
   - **Files** (unmanaged file storage -- this is where Bronze and Silver layers will live)
6. Create the folder structure under **Files**:
   - Click on **Files** in the left pane.
   - Click **New subfolder** and create:
     - `bronze/` -- raw ingested data
     - `bronze/structured/` -- CSV files
     - `bronze/unstructured/` -- PDF, Word, and other documents
     - `silver/` -- cleaned and typed data
     - `gold/` -- (optional, if not using managed Tables)
7. Verify the SQL analytics endpoint:
   - In the Lakehouse view, click the dropdown next to the Lakehouse name in the top-left.
   - Select **SQL analytics endpoint**.
   - Verify you can see the endpoint (it will be empty until tables are created).
   - Copy the **SQL connection string** for later use. It looks like: `x]xxxx.datawarehouse.fabric.microsoft.com`.

### Expected Outcome

- Lakehouse `lh_manulife_poc` appears in the workspace.
- Folder structure `bronze/structured/`, `bronze/unstructured/`, `silver/` exists under Files.
- SQL analytics endpoint is accessible.

### Common Issues

| Issue | Resolution |
|---|---|
| Cannot create Lakehouse | Verify workspace is assigned to Fabric capacity and your role is Contributor or higher. |
| SQL analytics endpoint not showing | It can take 1-2 minutes to provision. Refresh the page. |
| Folder creation option not visible | Make sure you have clicked into the **Files** section (not Tables). |

---

## Step 3: Upload Raw Data

### What To Do

Upload the synthetic POC dataset (structured CSVs and unstructured documents) to the Bronze layer.

### How To Do It -- Structured Data

1. Open the `lh_manulife_poc` Lakehouse.
2. Navigate to **Files > bronze > structured**.
3. Click **Upload > Upload files** (or **Upload folder**).
4. Select all CSV files from the POC data package:
   - `dim_customer.csv`
   - `dim_product.csv`
   - `dim_advisor.csv`
   - `dim_date.csv`
   - `dim_policy.csv`
   - `dim_fund.csv`
   - `fact_claims.csv`
   - `fact_transactions.csv`
   - `fact_investments.csv`
   - `fact_policy_premiums.csv`
5. Wait for all uploads to complete (progress shown in notification panel).
6. Verify by clicking each file -- a preview should show the data.

**Alternative -- Upload via Notebook (recommended for reproducibility):**

```python
import os

# If data files are in the notebook's local storage after upload
# Or reference a mounted path
bronze_path = "Files/bronze/structured/"

# List uploaded files to verify
files = mssparkutils.fs.ls(f"abfss://<workspace-id>@onelake.dfs.fabric.microsoft.com/<lakehouse-id>/{bronze_path}")
for f in files:
    print(f.name, f.size)
```

### How To Do It -- Unstructured Data

1. Navigate to **Files > bronze > unstructured**.
2. Click **Upload > Upload files**.
3. Upload sample documents such as:
   - `policy_terms_life_insurance.pdf`
   - `investment_fund_prospectus.pdf`
   - `claims_processing_guidelines.docx`
   - `customer_faq.pdf`
   - `regulatory_compliance_summary.pdf`
4. These will be indexed later via Azure AI Search (Step 6).

### Expected Outcome

- 10 CSV files visible under `bronze/structured/`.
- 3-5 PDF/DOCX files visible under `bronze/unstructured/`.
- File previews render correctly in the Lakehouse explorer.

### Common Issues

| Issue | Resolution |
|---|---|
| Upload fails or times out | Files larger than 5 GB require Azure Storage Explorer or AzCopy. For POC CSVs this should not be an issue. |
| CSV preview shows garbled data | Ensure CSVs are UTF-8 encoded with comma delimiters. |
| "Insufficient permissions" error | Verify your workspace role is Contributor or Admin. |

---

## Step 4: Run Data Transformation Notebooks

### What To Do

Create and execute PySpark notebooks to transform raw Bronze data into typed Silver tables and then into Gold star schema Delta tables.

### How To Do It -- Bronze to Silver Notebook

1. In the workspace, click **+ New item > Notebook**.
2. Name it: `nb_bronze_to_silver`.
3. Attach the notebook to `lh_manulife_poc` by clicking the Lakehouse icon in the left panel and selecting the Lakehouse.
4. Add the following cells:

**Cell 1 -- Configuration:**

```python
# Bronze and Silver paths
bronze_base = "Files/bronze/structured"
silver_base = "Files/silver"

# List of dimension and fact tables
tables = [
    "dim_customer", "dim_product", "dim_advisor", "dim_date",
    "dim_policy", "dim_fund",
    "fact_claims", "fact_transactions", "fact_investments",
    "fact_policy_premiums"
]
```

**Cell 2 -- Read, clean, and write to Silver:**

```python
from pyspark.sql import functions as F
from pyspark.sql.types import *

for table_name in tables:
    print(f"Processing {table_name}...")

    # Read CSV from Bronze
    df = spark.read.option("header", "true").option("inferSchema", "true") \
        .csv(f"{bronze_base}/{table_name}.csv")

    # Basic cleaning
    # 1. Trim whitespace from string columns
    for col_info in df.dtypes:
        if col_info[1] == "string":
            df = df.withColumn(col_info[0], F.trim(F.col(col_info[0])))

    # 2. Drop exact duplicate rows
    df = df.dropDuplicates()

    # 3. Drop rows where primary key is null
    pk_col = df.columns[0]  # First column is assumed to be PK
    df = df.filter(F.col(pk_col).isNotNull())

    # Write to Silver as Parquet
    df.write.mode("overwrite").parquet(f"{silver_base}/{table_name}")
    print(f"  -> Written {df.count()} rows to Silver/{table_name}")

print("Bronze to Silver complete.")
```

5. Click **Run all** to execute.

### How To Do It -- Silver to Gold Notebook

1. Create another notebook: `nb_silver_to_gold`.
2. Attach to `lh_manulife_poc`.
3. Add the following cells:

**Cell 1 -- Schema definitions and type casting:**

```python
from pyspark.sql.types import *
from pyspark.sql import functions as F

silver_base = "Files/silver"

# Define explicit schemas for type safety
schemas = {
    "dim_customer": {
        "customer_key": IntegerType(),
        "customer_id": StringType(),
        "full_name": StringType(),
        "city": StringType(),
        "province": StringType(),
        "postal_code": StringType(),
        "segment": StringType(),
        "age_band": StringType(),
        "registration_date": DateType()
    },
    "dim_product": {
        "product_key": IntegerType(),
        "product_id": StringType(),
        "product_name": StringType(),
        "category": StringType(),
        "product_line": StringType(),
        "risk_tier": StringType()
    },
    "dim_advisor": {
        "advisor_key": IntegerType(),
        "advisor_id": StringType(),
        "full_name": StringType(),
        "branch": StringType(),
        "region": StringType(),
        "certification_level": StringType(),
        "specialization": StringType()
    },
    "dim_date": {
        "date_key": IntegerType(),
        "full_date": DateType(),
        "year": IntegerType(),
        "quarter": IntegerType(),
        "month": IntegerType(),
        "month_name": StringType(),
        "day_of_week": StringType(),
        "is_weekend": BooleanType(),
        "fiscal_year": IntegerType(),
        "fiscal_quarter": IntegerType()
    },
    "dim_policy": {
        "policy_key": IntegerType(),
        "policy_id": StringType(),
        "policy_number": StringType(),
        "policy_type": StringType(),
        "status": StringType(),
        "payment_frequency": StringType(),
        "risk_category": StringType()
    },
    "dim_fund": {
        "fund_key": IntegerType(),
        "fund_name": StringType(),
        "fund_type": StringType(),
        "risk_rating": StringType(),
        "region": StringType()
    },
    "fact_claims": {
        "claim_id": IntegerType(),
        "policy_key": IntegerType(),
        "customer_key": IntegerType(),
        "product_key": IntegerType(),
        "advisor_key": IntegerType(),
        "date_key": IntegerType(),
        "claim_amount": DecimalType(18, 2),
        "approved_amount": DecimalType(18, 2),
        "processing_days": IntegerType(),
        "is_approved": BooleanType(),
        "is_denied": BooleanType()
    },
    "fact_transactions": {
        "transaction_id": IntegerType(),
        "customer_key": IntegerType(),
        "policy_key": IntegerType(),
        "date_key": IntegerType(),
        "transaction_type": StringType(),
        "amount": DecimalType(18, 2),
        "payment_method": StringType()
    },
    "fact_investments": {
        "investment_id": IntegerType(),
        "customer_key": IntegerType(),
        "advisor_key": IntegerType(),
        "date_key": IntegerType(),
        "fund_key": IntegerType(),
        "investment_amount": DecimalType(18, 2),
        "current_value": DecimalType(18, 2),
        "unrealized_gain_loss": DecimalType(18, 2),
        "return_ytd_pct": DecimalType(8, 4)
    },
    "fact_policy_premiums": {
        "policy_key": IntegerType(),
        "customer_key": IntegerType(),
        "product_key": IntegerType(),
        "date_key": IntegerType(),
        "premium_amount": DecimalType(18, 2),
        "coverage_amount": DecimalType(18, 2)
    }
}
```

**Cell 2 -- Cast and write to Gold (managed Delta tables):**

```python
for table_name, col_types in schemas.items():
    print(f"Processing {table_name} -> Gold...")

    # Read from Silver
    df = spark.read.parquet(f"{silver_base}/{table_name}")

    # Cast columns to target types
    for col_name, col_type in col_types.items():
        if col_name in df.columns:
            df = df.withColumn(col_name, F.col(col_name).cast(col_type))

    # Write as managed Delta table (appears under Tables in Lakehouse)
    df.write.mode("overwrite").format("delta").saveAsTable(table_name)
    print(f"  -> {table_name}: {df.count()} rows written to Gold (Delta)")

print("Silver to Gold complete.")
```

**Cell 3 -- Validation:**

```python
# Verify all tables exist and have data
for table_name in schemas.keys():
    count = spark.table(table_name).count()
    print(f"{table_name}: {count} rows")

# Quick referential integrity check
claims_orphan_customers = spark.sql("""
    SELECT COUNT(*) as orphan_count
    FROM fact_claims fc
    LEFT JOIN dim_customer dc ON fc.customer_key = dc.customer_key
    WHERE dc.customer_key IS NULL
""").collect()[0]["orphan_count"]
print(f"\nOrphan customer keys in fact_claims: {claims_orphan_customers}")

claims_orphan_policies = spark.sql("""
    SELECT COUNT(*) as orphan_count
    FROM fact_claims fc
    LEFT JOIN dim_policy dp ON fc.policy_key = dp.policy_key
    WHERE dp.policy_key IS NULL
""").collect()[0]["orphan_count"]
print(f"Orphan policy keys in fact_claims: {claims_orphan_policies}")
```

4. Click **Run all** to execute.

### Expected Outcome

- 10 managed Delta tables appear under the **Tables** section of the Lakehouse.
- All tables have correct data types (not all strings).
- Row counts match expected volumes.
- Zero orphan keys in referential integrity checks.

### Common Issues

| Issue | Resolution |
|---|---|
| `AnalysisException: Table already exists` | Change write mode to `"overwrite"` or drop the table first with `spark.sql("DROP TABLE IF EXISTS ...")`. |
| Type casting errors (null values) | Some CSV values may not parse correctly. Add `.option("nullValue", "")` when reading CSVs. |
| Notebook hangs on "Starting Spark session" | Fabric capacity may be overloaded. Wait 2-3 minutes. If persistent, check capacity health in Admin portal. |
| Tables not visible in Lakehouse | Click the refresh icon in the Lakehouse explorer. Tables may take 30-60 seconds to appear. |

---

## Step 5: Create Semantic Model

### What To Do

Build a Power BI semantic model on top of the Gold Delta tables, define relationships, DAX measures, descriptions, and linguistic schema for AI readiness.

### How To Do It -- Option A: From Fabric Portal (Direct Lake)

1. In the Lakehouse `lh_manulife_poc`, click **New semantic model** (top ribbon).
2. Name it: `sm_manulife_poc`.
3. Select all 10 tables (4 fact + 6 dimension).
4. Click **Confirm**.
5. The semantic model opens in the web-based model editor.

**Define Relationships:**

6. Click the **Model** tab (relationship diagram view).
7. Create relationships by dragging columns between tables. For each relationship:
   - Drag the key column from the dimension table to the matching column in the fact table.
   - Verify cardinality is **One-to-many (1:*)** (dimension to fact).
   - Verify cross-filter direction is **Single** (dimension filters fact).
8. Create all 16 relationships as defined in the semantic model spec (see `semantic-model-spec.md`, Section 5).

**Create DAX Measures:**

9. Click on any table in the **Data** tab.
10. Click **New measure** in the ribbon.
11. Enter each DAX measure from Section 6 of the semantic model spec. Start with:

```dax
Total Premium Revenue =
SUMX(
    fact_policy_premiums,
    fact_policy_premiums[premium_amount]
)
```

12. Repeat for all 24 measures. Assign each measure to its Display Folder:
    - Select the measure.
    - In the **Properties** pane, set **Display folder** (e.g., "Premiums", "Claims", "Investments", "Customers & Policies").

**Add Descriptions:**

13. For each table: select the table, and in the **Properties** pane, add the **Description** from the semantic model spec (Section 10.2).
14. For each column: select the column, add the description.
15. For each measure: select the measure, add the description.

**Hide Technical Columns:**

16. Hide all `_key` columns from report view:
    - Right-click each `_key` column > **Hide in report view**.

**Set Data Categories:**

17. Select `dim_customer[city]` > Properties > **Data category** > City.
18. Select `dim_customer[province]` > Properties > **Data category** > State or Province.
19. Select `dim_customer[postal_code]` > Properties > **Data category** > Postal Code.

### How To Do It -- Option B: Power BI Desktop (for advanced DAX and linguistic schema)

1. Open **Power BI Desktop**.
2. Click **Get Data > Microsoft Fabric > Lakehouses**.
3. Select `lh_manulife_poc` and choose all 10 tables.
4. Choose **Direct Lake** connection mode (or Import if Direct Lake is not available).
5. In **Model view**, create all 16 relationships.
6. In **Model view**, create all DAX measures.
7. To add the linguistic schema:
   - Go to **Model view > Q&A setup** (in the ribbon).
   - Click **Edit linguistic schema**.
   - Paste the YAML from `semantic-model-spec.md` Section 10.1.
   - Click **Apply**.
8. Configure synonyms:
   - In the Q&A setup pane, under **Synonyms**, add synonyms for each table and column as defined in Section 10.3 of the spec.
9. **Publish** the semantic model:
   - Click **Publish** in the ribbon.
   - Select the `Manulife-Fabric-POC` workspace.
   - The model is published as `sm_manulife_poc`.

### Set Refresh Schedule (Import mode only)

10. In the Fabric portal, navigate to the published semantic model.
11. Click **Settings** (gear icon).
12. Under **Scheduled refresh**:
    - Toggle to **On**.
    - Set refresh frequency: **Every 6 hours** (or on-demand for POC).
    - Configure gateway if required (not needed for Direct Lake or Fabric-to-Fabric connections).

### Expected Outcome

- Semantic model `sm_manulife_poc` appears in the workspace.
- All 16 relationships are correctly defined.
- All 24 DAX measures are functional.
- Descriptions are populated on all tables, columns, and measures.
- Hidden columns do not appear in report view.
- Q&A returns reasonable results for questions like "What is total premium revenue?"

### Common Issues

| Issue | Resolution |
|---|---|
| Direct Lake not available as a connection mode | Ensure the tables are managed Delta tables (under Tables, not Files) and the workspace is on Fabric capacity. |
| DAX measure returns blank/error | Check that relationship directions are correct (single direction, dimension to fact). Use `SUMX` instead of `SUM` if column references are ambiguous. |
| Linguistic schema not saving | Ensure the YAML syntax is valid (no tabs, proper indentation). Validate with a YAML linter. |
| "The model is too large" | For POC data volumes this should not occur. If it does, ensure you are not importing duplicate data. |

---

## Step 6: Configure Azure AI Search (for Unstructured)

### What To Do

Set up Azure AI Search to index unstructured documents (PDFs, Word files) with vector embeddings for hybrid search. This enables the orchestration layer to answer questions about policy terms, fund prospectuses, and compliance documents.

### How To Do It

**6.1 Create Azure AI Search Service:**

```bash
# Set variables
RG="rg-manulife-fabric-poc"
LOCATION="canadacentral"
SEARCH_NAME="search-manulife-poc"

# Create resource group (if not already created)
az group create --name $RG --location $LOCATION

# Create Azure AI Search (Standard tier for vector search)
az search service create \
    --name $SEARCH_NAME \
    --resource-group $RG \
    --sku standard \
    --location $LOCATION \
    --partition-count 1 \
    --replica-count 1
```

**6.2 Create Azure OpenAI Deployment (for embeddings):**

```bash
AOAI_NAME="aoai-manulife-poc"

# Create Azure OpenAI resource
az cognitiveservices account create \
    --name $AOAI_NAME \
    --resource-group $RG \
    --kind OpenAI \
    --sku S0 \
    --location canadaeast  # Canada Central may not have OpenAI; use canadaeast

# Deploy embedding model
az cognitiveservices account deployment create \
    --name $AOAI_NAME \
    --resource-group $RG \
    --deployment-name text-embedding-3-large \
    --model-name text-embedding-3-large \
    --model-version "1" \
    --model-format OpenAI \
    --sku-capacity 120 \
    --sku-name Standard
```

**6.3 Upload Documents to Blob Storage:**

Azure AI Search needs a data source. Either use the Lakehouse OneLake path or a separate Blob container.

```bash
STORAGE_NAME="stmanulifepoc"

# Create storage account
az storage account create \
    --name $STORAGE_NAME \
    --resource-group $RG \
    --location $LOCATION \
    --sku Standard_LRS

# Create container for documents
az storage container create \
    --name documents \
    --account-name $STORAGE_NAME

# Upload documents (from local machine)
az storage blob upload-batch \
    --destination documents \
    --source ./data/unstructured/ \
    --account-name $STORAGE_NAME
```

**6.4 Create the Index, Skillset, and Indexer:**

Use the Azure portal or REST API. Below is the REST API approach.

**Create Skillset (document cracking + chunking + embedding):**

```json
PUT https://search-manulife-poc.search.windows.net/skillsets/manulife-skillset?api-version=2024-07-01

{
  "name": "manulife-skillset",
  "description": "Crack documents, chunk text, generate embeddings",
  "skills": [
    {
      "@odata.type": "#Microsoft.Skills.Text.SplitSkill",
      "name": "chunk-text",
      "description": "Split document text into chunks",
      "context": "/document",
      "textSplitMode": "pages",
      "maximumPageLength": 2000,
      "pageOverlapLength": 500,
      "inputs": [
        { "name": "text", "source": "/document/content" }
      ],
      "outputs": [
        { "name": "textItems", "targetName": "chunks" }
      ]
    },
    {
      "@odata.type": "#Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill",
      "name": "generate-embeddings",
      "description": "Generate vector embeddings for each chunk",
      "context": "/document/chunks/*",
      "modelName": "text-embedding-3-large",
      "resourceUri": "https://aoai-manulife-poc.openai.azure.com",
      "deploymentId": "text-embedding-3-large",
      "inputs": [
        { "name": "text", "source": "/document/chunks/*" }
      ],
      "outputs": [
        { "name": "embedding", "targetName": "vector" }
      ]
    }
  ],
  "indexProjections": {
    "selectors": [
      {
        "targetIndexName": "manulife-docs-index",
        "parentKeyFieldName": "parent_id",
        "sourceContext": "/document/chunks/*",
        "mappings": [
          { "name": "chunk", "source": "/document/chunks/*" },
          { "name": "vector", "source": "/document/chunks/*/vector" },
          { "name": "title", "source": "/document/metadata_storage_name" }
        ]
      }
    ],
    "parameters": {
      "projectionMode": "generatedKeyAsId"
    }
  }
}
```

**Create Index (with vector fields):**

```json
PUT https://search-manulife-poc.search.windows.net/indexes/manulife-docs-index?api-version=2024-07-01

{
  "name": "manulife-docs-index",
  "fields": [
    { "name": "chunk_id", "type": "Edm.String", "key": true, "filterable": true },
    { "name": "parent_id", "type": "Edm.String", "filterable": true },
    { "name": "title", "type": "Edm.String", "searchable": true, "filterable": true },
    { "name": "chunk", "type": "Edm.String", "searchable": true },
    {
      "name": "vector",
      "type": "Collection(Edm.Single)",
      "searchable": true,
      "dimensions": 3072,
      "vectorSearchProfile": "my-vector-profile"
    }
  ],
  "vectorSearch": {
    "algorithms": [
      {
        "name": "my-hnsw",
        "kind": "hnsw",
        "hnswParameters": {
          "metric": "cosine",
          "m": 4,
          "efConstruction": 400,
          "efSearch": 500
        }
      }
    ],
    "profiles": [
      {
        "name": "my-vector-profile",
        "algorithm": "my-hnsw"
      }
    ]
  },
  "semantic": {
    "configurations": [
      {
        "name": "my-semantic-config",
        "prioritizedFields": {
          "contentFields": [ { "fieldName": "chunk" } ],
          "titleField": { "fieldName": "title" }
        }
      }
    ]
  }
}
```

**Create Data Source:**

```json
POST https://search-manulife-poc.search.windows.net/datasources?api-version=2024-07-01

{
  "name": "manulife-blob-source",
  "type": "azureblob",
  "credentials": {
    "connectionString": "<storage-connection-string>"
  },
  "container": {
    "name": "documents"
  }
}
```

**Create Indexer:**

```json
PUT https://search-manulife-poc.search.windows.net/indexers/manulife-indexer?api-version=2024-07-01

{
  "name": "manulife-indexer",
  "dataSourceName": "manulife-blob-source",
  "targetIndexName": "manulife-docs-index",
  "skillsetName": "manulife-skillset",
  "parameters": {
    "configuration": {
      "dataToExtract": "contentAndMetadata",
      "parsingMode": "default"
    }
  },
  "fieldMappings": [],
  "outputFieldMappings": []
}
```

**6.5 Test Search Queries:**

```bash
# Keyword search
POST https://search-manulife-poc.search.windows.net/indexes/manulife-docs-index/docs/search?api-version=2024-07-01
{
  "search": "what is the waiting period for critical illness claims",
  "queryType": "semantic",
  "semanticConfiguration": "my-semantic-config",
  "top": 5,
  "select": "title, chunk"
}
```

### Expected Outcome

- Azure AI Search service is provisioned and running.
- Index `manulife-docs-index` contains chunked and vectorized document content.
- Search queries return relevant document chunks.
- Both keyword (BM25) and vector (hybrid) search work.

### Common Issues

| Issue | Resolution |
|---|---|
| Indexer fails with "Skillset execution error" | Verify Azure OpenAI endpoint and API key in the skillset. Ensure the embedding model is deployed. |
| Vector field dimensions mismatch | `text-embedding-3-large` outputs 3072 dimensions. If using `text-embedding-ada-002`, use 1536. |
| Documents not being indexed | Check indexer status in Azure portal > AI Search > Indexers. Look at execution history for errors. |
| "Resource not found" for Azure OpenAI | Azure OpenAI may not be available in Canada Central. Deploy in `canadaeast` or `eastus2`. |

---

## Step 7: Configure Fabric Data Agent

### What To Do

Enable and configure the Fabric Data Agent to answer natural language questions against the semantic model and lakehouse SQL endpoint.

### How To Do It

**7.1 Create Data Agent:**

1. In the `Manulife-Fabric-POC` workspace, click **+ New item**.
2. Under **AI**, select **Data Agent** (preview).
3. Name it: `da_manulife_poc`.
4. Click **Create**.

**7.2 Connect to Semantic Model:**

5. In the Data Agent configuration, click **Add data source**.
6. Select **Semantic model**.
7. Choose `sm_manulife_poc`.
8. The Data Agent will automatically discover all tables, measures, and relationships.

**7.3 Connect to Lakehouse SQL Endpoint:**

9. Click **Add data source** again.
10. Select **Lakehouse SQL analytics endpoint**.
11. Choose `lh_manulife_poc`.
12. This gives the Data Agent direct SQL query capability against the Gold Delta tables.

**7.4 Configure Agent Instructions:**

13. In the **Instructions** field, add context to guide the agent's behavior:

```
You are a data analyst for Manulife, a leading Canadian insurance and wealth management company.

When answering questions:
- Claims Ratio means approved claims paid divided by total premium revenue.
- AUM (Assets Under Management) means the total current market value of all client investment positions.
- "Active customers" means customers who have at least one policy with status = 'Active'.
- Currency values are in Canadian Dollars (CAD).
- Fiscal year aligns with calendar year (January to December).
- When asked about "top advisors", rank by total AUM unless otherwise specified.
- When asked about trends, show monthly data for the last 12 months.
- Always include units (e.g., $, %, days) in your responses.
```

**7.5 Test Natural Language Queries:**

14. In the Data Agent chat interface, test the following queries:

| Test Query | Expected Behavior |
|---|---|
| "What is our total premium revenue?" | Returns sum from fact_policy_premiums |
| "Show me the claims ratio" | Returns approved claims / premiums |
| "How many active policies do we have?" | Returns count from dim_policy where status = Active |
| "Who are the top 5 advisors by AUM?" | Returns ranked list from fact_investments joined to dim_advisor |
| "What is the average claim processing time for life insurance?" | Returns average from fact_claims filtered by dim_product |
| "Compare premium revenue across provinces" | Returns grouped results by province |

15. For each query, review:
    - Was the correct measure or SQL query used?
    - Did the agent correctly join tables?
    - Is the answer numerically correct?
    - Did the agent provide appropriate context?

**7.6 Document Limitations:**

16. Keep a log of queries that produce incorrect or unexpected results. Common limitations include:
    - Complex multi-step calculations may not resolve correctly.
    - Ambiguous column names across tables may confuse the agent.
    - Time intelligence DAX measures may not be triggered by natural language date references.
    - The agent may default to SQL queries over DAX measures when both data sources are connected.

### Expected Outcome

- Data Agent `da_manulife_poc` is created and connected to both the semantic model and SQL endpoint.
- At least 80% of the test queries return correct results.
- Limitations are documented for the validation report.

### Common Issues

| Issue | Resolution |
|---|---|
| "Data Agent" option not visible in New Item menu | Tenant setting "Users can create and use Data Agents" is not enabled. Contact Fabric admin. |
| Data Agent returns "I don't have enough information" | Ensure descriptions are populated on all measures and columns. The agent relies on metadata to understand the model. |
| Data Agent returns incorrect aggregation | Check if the agent is using SQL (SUM on raw columns) vs. DAX (pre-defined measures). Add instructions to prefer the semantic model. |
| Agent response is very slow | This is expected in preview. Response times of 10-30 seconds are normal for complex queries. |
| Agent cannot answer questions about unstructured documents | The Data Agent (as of April 2026) primarily handles structured data. Unstructured documents require the orchestration layer (Step 8). |

---

## Step 8: Set Up Orchestration (Optional)

### What To Do

Build an optional orchestration layer using Azure OpenAI that combines structured data answers (from the Data Agent or direct SQL/DAX) with unstructured document answers (from Azure AI Search). This demonstrates a "single pane of glass" AI assistant experience.

### How To Do It

**8.1 Deploy Azure OpenAI GPT-4o:**

```bash
# Deploy GPT-4o for orchestration
az cognitiveservices account deployment create \
    --name aoai-manulife-poc \
    --resource-group rg-manulife-fabric-poc \
    --deployment-name gpt-4o \
    --model-name gpt-4o \
    --model-version "2024-11-20" \
    --model-format OpenAI \
    --sku-capacity 30 \
    --sku-name GlobalStandard
```

**8.2 Orchestration Architecture:**

```
User Question
     |
     v
Azure OpenAI (GPT-4o) - Router
     |
     +---> Tool 1: query_structured_data()
     |         |-> Calls Fabric SQL endpoint or DAX query via REST API
     |         |-> Returns tabular data
     |
     +---> Tool 2: search_documents()
     |         |-> Calls Azure AI Search hybrid query
     |         |-> Returns relevant document chunks
     |
     v
GPT-4o synthesizes final answer
```

**8.3 Implement Tool Definitions:**

Create a Python application (can be run as an Azure Function, Fabric notebook, or local script):

```python
import os
import json
from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.identity import DefaultAzureCredential
import struct
import pyodbc

# Configuration
AOAI_ENDPOINT = os.environ["AOAI_ENDPOINT"]
AOAI_KEY = os.environ["AOAI_KEY"]
SEARCH_ENDPOINT = os.environ["SEARCH_ENDPOINT"]
SEARCH_KEY = os.environ["SEARCH_KEY"]
SEARCH_INDEX = "manulife-docs-index"
FABRIC_SQL_ENDPOINT = os.environ["FABRIC_SQL_ENDPOINT"]
FABRIC_DATABASE = "lh_manulife_poc"

# Initialize clients
aoai_client = AzureOpenAI(
    azure_endpoint=AOAI_ENDPOINT,
    api_key=AOAI_KEY,
    api_version="2024-10-21"
)

search_client = SearchClient(
    endpoint=SEARCH_ENDPOINT,
    index_name=SEARCH_INDEX,
    credential=AzureKeyCredential(SEARCH_KEY)
)

# Tool definitions for function calling
tools = [
    {
        "type": "function",
        "function": {
            "name": "query_structured_data",
            "description": "Query structured insurance and investment data from the Manulife data warehouse. Use this for questions about premiums, claims, investments, customers, advisors, policies, and funds.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql_query": {
                        "type": "string",
                        "description": "A T-SQL query to run against the Fabric SQL endpoint. Available tables: fact_claims, fact_transactions, fact_investments, fact_policy_premiums, dim_customer, dim_product, dim_advisor, dim_date, dim_policy, dim_fund."
                    }
                },
                "required": ["sql_query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "Search unstructured documents including policy terms, fund prospectuses, claims guidelines, and regulatory documents. Use this for questions about policy conditions, coverage terms, fund details, or compliance requirements.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_query": {
                        "type": "string",
                        "description": "Natural language search query"
                    }
                },
                "required": ["search_query"]
            }
        }
    }
]

def query_structured_data(sql_query: str) -> str:
    """Execute SQL against Fabric SQL endpoint."""
    token = DefaultAzureCredential().get_token("https://database.windows.net/.default").token
    token_bytes = token.encode("UTF-16-LE")
    token_struct = struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)

    conn = pyodbc.connect(
        f"Driver={{ODBC Driver 18 for SQL Server}};"
        f"Server={FABRIC_SQL_ENDPOINT};"
        f"Database={FABRIC_DATABASE};"
        f"Encrypt=Yes;TrustServerCertificate=No",
        attrs_before={1256: token_struct}
    )
    cursor = conn.cursor()
    cursor.execute(sql_query)
    columns = [col[0] for col in cursor.description]
    rows = cursor.fetchall()
    conn.close()

    results = [dict(zip(columns, row)) for row in rows]
    return json.dumps(results[:50], default=str)  # Limit to 50 rows

def search_documents(search_query: str) -> str:
    """Hybrid search against Azure AI Search."""
    results = search_client.search(
        search_text=search_query,
        query_type="semantic",
        semantic_configuration_name="my-semantic-config",
        top=5,
        select=["title", "chunk"]
    )
    docs = [{"title": r["title"], "content": r["chunk"]} for r in results]
    return json.dumps(docs)

def run_orchestrator(user_question: str) -> str:
    """Main orchestration loop."""
    system_prompt = """You are a Manulife AI assistant that helps employees and advisors
    with questions about insurance, investments, and company policies.

    You have access to two tools:
    1. query_structured_data: For numerical/analytical questions about premiums, claims, investments, etc.
    2. search_documents: For questions about policy terms, guidelines, compliance, and procedures.

    Use one or both tools as needed. Always cite your data sources."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_question}
    ]

    response = aoai_client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )

    # Handle tool calls
    while response.choices[0].message.tool_calls:
        msg = response.choices[0].message
        messages.append(msg)

        for tool_call in msg.tool_calls:
            args = json.loads(tool_call.function.arguments)
            if tool_call.function.name == "query_structured_data":
                result = query_structured_data(args["sql_query"])
            elif tool_call.function.name == "search_documents":
                result = search_documents(args["search_query"])
            else:
                result = json.dumps({"error": "Unknown tool"})

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result
            })

        response = aoai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )

    return response.choices[0].message.content
```

**8.4 Test the Orchestrator:**

```python
# Test structured data question
print(run_orchestrator("What is our total AUM and how has it changed this quarter?"))

# Test unstructured document question
print(run_orchestrator("What is the waiting period for critical illness claims?"))

# Test combined question
print(run_orchestrator(
    "What is our claims ratio for life insurance, and what does our policy say about claim dispute resolution?"
))
```

### Expected Outcome

- Orchestrator correctly routes structured questions to SQL and unstructured questions to AI Search.
- Combined questions trigger both tools and the final response synthesizes both sources.
- Response latency is under 15 seconds for most queries.

### Common Issues

| Issue | Resolution |
|---|---|
| SQL query fails with permission error | Ensure the identity (user or service principal) has access to the Fabric SQL endpoint. |
| Azure OpenAI returns "content filter" error | Rephrase the query. Insurance/health terms may trigger content filters. Adjust filter settings in Azure OpenAI Studio if needed. |
| Search returns irrelevant results | Tune the semantic configuration. Add more synonyms or re-chunk documents with smaller page sizes. |

---

## Step 9: Validate POC

### What To Do

Systematically validate that all components work end-to-end and document accuracy, gaps, and performance.

### How To Do It

**9.1 Data Validation:**

Run these validation queries against the Lakehouse SQL endpoint:

```sql
-- Row counts
SELECT 'fact_claims' as tbl, COUNT(*) as cnt FROM fact_claims
UNION ALL SELECT 'fact_transactions', COUNT(*) FROM fact_transactions
UNION ALL SELECT 'fact_investments', COUNT(*) FROM fact_investments
UNION ALL SELECT 'fact_policy_premiums', COUNT(*) FROM fact_policy_premiums
UNION ALL SELECT 'dim_customer', COUNT(*) FROM dim_customer
UNION ALL SELECT 'dim_product', COUNT(*) FROM dim_product
UNION ALL SELECT 'dim_advisor', COUNT(*) FROM dim_advisor
UNION ALL SELECT 'dim_date', COUNT(*) FROM dim_date
UNION ALL SELECT 'dim_policy', COUNT(*) FROM dim_policy
UNION ALL SELECT 'dim_fund', COUNT(*) FROM dim_fund;

-- Referential integrity
SELECT 'claims->customer' as check_name,
       COUNT(*) as orphan_count
FROM fact_claims fc
LEFT JOIN dim_customer dc ON fc.customer_key = dc.customer_key
WHERE dc.customer_key IS NULL;

-- Key metric validation
SELECT
    SUM(premium_amount) as total_premium_revenue,
    COUNT(DISTINCT customer_key) as unique_customers,
    SUM(premium_amount) / COUNT(DISTINCT customer_key) as premium_per_customer
FROM fact_policy_premiums;

SELECT
    SUM(CASE WHEN is_approved = 1 THEN approved_amount ELSE 0 END) as approved_claims,
    COUNT(*) as total_claims,
    AVG(processing_days) as avg_processing_days,
    CAST(SUM(CASE WHEN is_approved = 1 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) as approval_rate
FROM fact_claims;

SELECT
    SUM(current_value) as total_aum,
    AVG(return_ytd_pct) as avg_return_ytd,
    COUNT(DISTINCT customer_key) as investors
FROM fact_investments;
```

**9.2 Semantic Model Validation:**

Create a validation Power BI report with the following visuals:

| Visual | Purpose |
|---|---|
| Card: Total Premium Revenue | Verify measure returns expected value |
| Card: Total AUM | Verify investment measure |
| Card: Claims Ratio | Verify ratio calculation |
| Card: Avg Processing Time | Verify average calculation |
| Table: Premium by Province | Verify geographic dimension works |
| Bar chart: Claims by Product Category | Verify product dimension |
| Line chart: Monthly Premium Trend | Verify time intelligence |
| Matrix: Advisor x AUM | Verify advisor dimension |

**9.3 Data Agent Validation:**

Run each of the 25 sample questions from the semantic model spec and score them:

| Question | Expected Answer | Agent Answer | Correct? | Notes |
|---|---|---|---|---|
| Q1: What is our claims ratio? | (calculated value) | | Y/N | |
| Q2: How many claims denied? | (count) | | Y/N | |
| ... | ... | ... | ... | ... |

Calculate overall accuracy: `Correct answers / Total questions * 100%`

Target: **80%+ accuracy** for the POC to be considered successful.

**9.4 Performance Benchmarks:**

| Metric | Target | Actual |
|---|---|---|
| Notebook execution time (Bronze->Gold) | < 5 minutes | |
| Semantic model refresh time | < 2 minutes | |
| Data Agent response time | < 15 seconds | |
| AI Search query time | < 3 seconds | |
| Orchestrator end-to-end time | < 20 seconds | |

**9.5 Document Findings:**

Create a validation summary with:
- Overall accuracy score
- List of questions that failed and why
- Performance benchmarks
- Recommendations for improvement
- Gaps identified (features not yet available in Fabric Data Agent preview)

### Expected Outcome

- Validation report with quantified accuracy metrics.
- All data integrity checks pass (zero orphan keys).
- Performance benchmarks recorded.
- Clear list of limitations and recommendations.

---

## Step 10: Demo Preparation

### What To Do

Prepare a polished demonstration flow that showcases the end-to-end POC for Microsoft and Manulife stakeholders.

### How To Do It

**10.1 Prepare Demo Questions:**

Select 8-10 questions that demonstrate breadth and depth. Arrange them in a narrative flow:

| # | Demo Question | What It Demonstrates | Expected Wow Factor |
|---|---|---|---|
| 1 | "What is our total premium revenue this year?" | Basic measure retrieval | Quick, accurate answer |
| 2 | "Break that down by product category" | Dimension slicing | Automatic chart generation |
| 3 | "What is our claims ratio and is it healthy?" | KPI with context | Agent provides industry benchmark context |
| 4 | "Which province has the highest claims?" | Geographic analysis | Map visualization potential |
| 5 | "Who are our top 5 advisors by AUM?" | Ranking query | Advisor-level detail |
| 6 | "Show me the monthly premium trend for the last 12 months" | Time intelligence | Trend line |
| 7 | "How many high-value customers do we have?" | Complex filter measure | Segment analysis |
| 8 | "What does our policy say about critical illness waiting periods?" | Unstructured doc search | AI Search integration |
| 9 | "What is the average claim processing time for life insurance vs health insurance?" | Cross-dimension comparison | Side-by-side analysis |
| 10 | "Give me an executive summary of our insurance business performance" | Multi-measure synthesis | AI-generated narrative |

**10.2 Set Up Screen Flow:**

Plan the demo screens in order:

1. **Architecture slide** (2 min) -- Show the data flow from Bronze to Data Agent.
2. **Fabric workspace** (1 min) -- Tour the workspace artifacts (Lakehouse, notebooks, semantic model, Data Agent).
3. **Lakehouse explorer** (1 min) -- Show Bronze/Silver/Gold layers, Delta table previews.
4. **Notebook run** (1 min) -- Show the transformation notebook (pre-run; do not run live to avoid delays).
5. **Semantic model** (2 min) -- Show relationships, DAX measures, descriptions in the web model editor.
6. **Data Agent live demo** (8-10 min) -- Run the 10 demo questions interactively.
7. **Power BI report** (2 min) -- Show the validation report with visualizations.
8. **Orchestration demo** (3 min, optional) -- Show the combined structured + unstructured query.
9. **Next steps slide** (2 min) -- Production roadmap, security, scaling.

**10.3 Prepare Talking Points:**

**Opening:**
- "This POC demonstrates how Microsoft Fabric can serve as a unified analytics platform for Manulife's insurance and wealth management data."
- "We've built a complete data pipeline from raw data to AI-powered natural language querying in under a week."

**Key differentiators to highlight:**
- **Single platform:** Lakehouse, transformation, semantic model, and AI agent all in Fabric -- no separate services to manage.
- **Direct Lake:** Near real-time analytics without data movement or refresh scheduling.
- **Data Agent:** Business users can ask questions in plain English -- no SQL or DAX knowledge required.
- **AI-ready semantic model:** Descriptions, synonyms, and linguistic schema make the model self-documenting for AI consumption.
- **Hybrid AI:** Combine structured analytics with unstructured document search for comprehensive answers.

**Anticipated questions and answers:**

| Question | Suggested Answer |
|---|---|
| "How does this scale to production volumes?" | Fabric capacity scales linearly. F64 handles millions of rows. For billions, F128+ with Direct Lake partitioning. |
| "What about data security and RLS?" | RLS is fully supported in semantic models. We recommend implementing advisor-level and region-level RLS in Phase 2. |
| "Is Data Agent GA?" | Data Agent is in public preview (as of April 2026). GA is expected in H2 2026. The semantic model and Lakehouse components are fully GA. |
| "Can this work with real Manulife data?" | Yes. The architecture is identical. We would connect to Manulife's existing data sources (e.g., Guidewire, Salesforce, SAP) via Fabric pipelines or Dataflows Gen2. |
| "What about compliance and data residency?" | All Fabric and Azure resources are deployed in Canada Central. Data does not leave Canadian borders except for AI processing, which can be restricted via tenant settings. |

**10.4 Pre-Demo Checklist:**

- [ ] Fabric capacity is running (not paused)
- [ ] All notebooks have been run successfully (check last run timestamp)
- [ ] Semantic model is refreshed and accessible
- [ ] Data Agent is responding to queries (test 2-3 questions)
- [ ] AI Search index has documents (check document count in Azure portal)
- [ ] Azure OpenAI deployment is active (if using orchestration)
- [ ] Browser bookmarks are set for: Fabric workspace, Data Agent, Azure portal
- [ ] Screen sharing is tested and resolution is at least 1920x1080
- [ ] Demo questions are printed or in a separate window for easy reference
- [ ] Backup screenshots are prepared in case of live demo failure

**10.5 Contingency Plan:**

If the live demo encounters issues:

1. **Data Agent not responding:** Switch to the pre-built Power BI report that shows the same metrics. Explain: "The Data Agent generates these same insights from natural language -- here is the equivalent dashboard."
2. **Slow response times:** Pre-cache responses by running the demo questions 30 minutes before the demo. Note: "Response times improve with warm cache."
3. **Incorrect answer:** Acknowledge it: "This is a preview feature and occasionally requires refinement. Let me show you the correct answer from the semantic model directly." Switch to Power BI report.
4. **Complete environment failure:** Use pre-recorded screen captures of the demo flow. Always have a backup recording.

---

## Appendix A: Troubleshooting Reference

| Symptom | Likely Cause | Resolution |
|---|---|---|
| Lakehouse tables show 0 rows | Notebook did not run or failed silently | Check notebook output cells for errors. Re-run. |
| Semantic model refresh fails | Direct Lake cannot connect to Delta tables | Verify tables exist under managed Tables (not Files). Check Lakehouse SQL endpoint is online. |
| Data Agent says "no data available" | Semantic model not connected, or no descriptions | Re-add data source in Data Agent config. Ensure all measures have descriptions. |
| DAX measure returns BLANK | Missing relationship or incorrect filter context | Verify all 16 relationships in the model diagram. Check cardinality and direction. |
| AI Search returns 0 results | Indexer has not run or failed | Check indexer status in Azure portal. Re-run indexer. |
| "Circular dependency detected" in DAX | Measure references itself | Review DAX formula for self-references. Use intermediate variables. |
| Notebook takes >10 minutes | Capacity is throttled or data volume is unexpectedly large | Check Fabric capacity utilization in Admin portal. Scale up if needed. |
| Power BI Desktop cannot connect to Lakehouse | XMLA endpoint not enabled or wrong tenant | Enable XMLA read/write in tenant settings. Verify you are signed into the correct tenant. |

---

## Appendix B: Resource Naming Conventions

| Resource Type | Naming Pattern | Example |
|---|---|---|
| Resource Group | `rg-{project}-{environment}` | `rg-manulife-fabric-poc` |
| Fabric Workspace | `{Client}-{Project}-{Environment}` | `Manulife-Fabric-POC` |
| Lakehouse | `lh_{project}_{environment}` | `lh_manulife_poc` |
| Semantic Model | `sm_{project}_{environment}` | `sm_manulife_poc` |
| Data Agent | `da_{project}_{environment}` | `da_manulife_poc` |
| Notebook | `nb_{purpose}` | `nb_bronze_to_silver` |
| AI Search | `search-{project}-{environment}` | `search-manulife-poc` |
| Azure OpenAI | `aoai-{project}-{environment}` | `aoai-manulife-poc` |
| Storage Account | `st{project}{env}` (no hyphens) | `stmanulifepoc` |

---

*End of POC Runbook*
