#!/bin/bash
###############################################################################
# Deploy ADF Templates in Correct Dependency Order
#
# Usage:
#   chmod +x scripts/Deploy-ADF-Templates.sh
#   ./scripts/Deploy-ADF-Templates.sh \
#     --factory "az-adf-virtualassets-migration-prd" \
#     --resource-group "az-rg-tx-virtualassets-prd-cac-002" \
#     --storage-account "<storage-account-name>" \
#     --sql-server "<sql-server-name>" \
#     --sql-database "<sql-database-name>" \
#     --key-vault "<key-vault-name>" \
#     --subscription "<subscription-id>"
###############################################################################

set -euo pipefail

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --factory)          FACTORY="$2"; shift 2;;
    --resource-group)   RG="$2"; shift 2;;
    --storage-account)  STORAGE="$2"; shift 2;;
    --sql-server)       SQL_SERVER="$2"; shift 2;;
    --sql-database)     SQL_DB="$2"; shift 2;;
    --key-vault)        KV="$2"; shift 2;;
    --subscription)     SUB="$2"; shift 2;;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
done

# --- Validate required args ---
for var in FACTORY RG STORAGE SQL_SERVER SQL_DB KV SUB; do
  if [ -z "${!var:-}" ]; then
    echo "ERROR: --$(echo $var | tr '[:upper:]' '[:lower:]' | tr '_' '-') is required"
    exit 1
  fi
done

TEMPLATE_DIR="adf-templates"

echo "============================================"
echo "ADF Template Deployment"
echo "  Factory:         $FACTORY"
echo "  Resource Group:  $RG"
echo "  Subscription:    $SUB"
echo "============================================"

# --- STEP 1: Linked Services (no dependencies) ---
echo ""
echo "=== STEP 1/3: Deploying Linked Services ==="

echo "[1/4] LS_AzureKeyVault..."
az deployment group create --resource-group "$RG" \
  --template-file "$TEMPLATE_DIR/linkedServices/LS_KeyVault.json" \
  --parameters factoryName="$FACTORY" \
    keyVaultName="$KV" \
    keyVaultResourceGroup="$RG" \
    subscriptionId="$SUB" \
  --name "ls-keyvault" --no-wait=false -o none

echo "[2/4] LS_ADLS_Gen2 + LS_AzureBlobStorage..."
az deployment group create --resource-group "$RG" \
  --template-file "$TEMPLATE_DIR/linkedServices/LS_AzureBlobStorage.json" \
  --parameters factoryName="$FACTORY" \
    storageAccountName="$STORAGE" \
  --name "ls-storage" --no-wait=false -o none

echo "[3/4] LS_AzureSqlDatabase..."
az deployment group create --resource-group "$RG" \
  --template-file "$TEMPLATE_DIR/linkedServices/LS_AzureSqlDatabase.json" \
  --parameters factoryName="$FACTORY" \
    sqlServerName="$SQL_SERVER" \
    sqlDatabaseName="$SQL_DB" \
  --name "ls-sql" --no-wait=false -o none

echo "[4/4] LS_HTTP_Graph_Download..."
az deployment group create --resource-group "$RG" \
  --template-file "$TEMPLATE_DIR/linkedServices/LS_HTTP_Graph_Download.json" \
  --parameters factoryName="$FACTORY" \
  --name "ls-graph-download" --no-wait=false -o none

echo "Linked Services deployed."

# --- STEP 2: Datasets (depend on linked services) ---
echo ""
echo "=== STEP 2/3: Deploying Datasets ==="

echo "[1/3] DS_SQL_ControlTables (MigrationControl, AuditLog, Watermark)..."
az deployment group create --resource-group "$RG" \
  --template-file "$TEMPLATE_DIR/datasets/DS_SQL_ControlTables.json" \
  --parameters factoryName="$FACTORY" \
  --name "ds-sql" --no-wait=false -o none

echo "[2/3] DS_ADLS_Sink (Binary, Parquet, JSON)..."
az deployment group create --resource-group "$RG" \
  --template-file "$TEMPLATE_DIR/datasets/DS_ADLS_Sink.json" \
  --parameters factoryName="$FACTORY" \
  --name "ds-adls" --no-wait=false -o none

echo "[3/3] DS_Graph_Content_Download..."
az deployment group create --resource-group "$RG" \
  --template-file "$TEMPLATE_DIR/datasets/DS_Graph_Content_Download.json" \
  --parameters factoryName="$FACTORY" \
  --name "ds-graph" --no-wait=false -o none

echo "Datasets deployed."

# --- STEP 3: Pipelines (depend on datasets; children first) ---
echo ""
echo "=== STEP 3/3: Deploying Pipelines ==="

echo "[1/6] PL_Copy_File_Batch (child - no pipeline deps)..."
az deployment group create --resource-group "$RG" \
  --template-file "$TEMPLATE_DIR/pipelines/PL_Copy_File_Batch.json" \
  --parameters factoryName="$FACTORY" \
  --name "pl-copy-file-batch" --no-wait=false -o none

echo "[2/6] PL_Process_Subfolder..."
az deployment group create --resource-group "$RG" \
  --template-file "$TEMPLATE_DIR/pipelines/PL_Process_Subfolder.json" \
  --parameters factoryName="$FACTORY" \
  --name "pl-process-subfolder" --no-wait=false -o none

echo "[3/6] PL_Migrate_Single_Library (calls PL_Copy_File_Batch)..."
az deployment group create --resource-group "$RG" \
  --template-file "$TEMPLATE_DIR/pipelines/PL_Migrate_Single_Library.json" \
  --parameters factoryName="$FACTORY" \
  --name "pl-migrate-single-library" --no-wait=false -o none

echo "[4/6] PL_Incremental_Sync (calls PL_Copy_File_Batch)..."
az deployment group create --resource-group "$RG" \
  --template-file "$TEMPLATE_DIR/pipelines/PL_Incremental_Sync.json" \
  --parameters factoryName="$FACTORY" \
  --name "pl-incremental-sync" --no-wait=false -o none

echo "[5/6] PL_Validation..."
az deployment group create --resource-group "$RG" \
  --template-file "$TEMPLATE_DIR/pipelines/PL_Validation.json" \
  --parameters factoryName="$FACTORY" \
  --name "pl-validation" --no-wait=false -o none

echo "[6/6] PL_Master_Migration_Orchestrator (calls PL_Migrate_Single_Library)..."
az deployment group create --resource-group "$RG" \
  --template-file "$TEMPLATE_DIR/pipelines/PL_Master_Migration_Orchestrator.json" \
  --parameters factoryName="$FACTORY" \
  --name "pl-master-orchestrator" --no-wait=false -o none

echo ""
echo "============================================"
echo "ALL DEPLOYMENTS COMPLETED SUCCESSFULLY"
echo "============================================"
echo ""
echo "Deployed to: $FACTORY"
echo "  - 4 Linked Services"
echo "  - 7 Datasets"
echo "  - 6 Pipelines"
echo ""
echo "Next steps:"
echo "  1. Verify linked service connections in ADF Studio"
echo "  2. Run SQL scripts (sql/create_control_table.sql, sql/create_audit_log_table.sql)"
echo "  3. Populate control table (scripts/Populate-ControlTable.ps1)"
echo "  4. Trigger PL_Master_Migration_Orchestrator"
