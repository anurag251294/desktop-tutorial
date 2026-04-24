#!/bin/bash
# =============================================================================
# Manulife Fabric POC — Azure Resource Provisioning Script
# =============================================================================
# This script provisions the Azure resources required for the POC.
# It is intended as a reference — review and adjust parameters before running.
#
# Prerequisites:
#   - Azure CLI installed and authenticated (az login)
#   - Sufficient permissions (Contributor on subscription)
#   - Fabric capacity must be provisioned separately via admin portal
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration — Update these values for your environment
# -----------------------------------------------------------------------------
SUBSCRIPTION_ID="<your-subscription-id>"
RESOURCE_GROUP="rg-manulife-fabric-poc"
LOCATION="canadacentral"
TAGS="project=manulife-poc environment=dev owner=your-team"

# Azure AI Search
SEARCH_SERVICE_NAME="srch-manulife-poc"
SEARCH_SKU="basic"  # basic is sufficient for POC; standard for production

# Azure OpenAI
OPENAI_SERVICE_NAME="aoai-manulife-poc"
OPENAI_SKU="S0"

# Storage (for staging data before OneLake upload, if needed)
STORAGE_ACCOUNT_NAME="stmanulifepoc"
STORAGE_SKU="Standard_LRS"

# Key Vault (for secrets management)
KEYVAULT_NAME="kv-manulife-poc"

# -----------------------------------------------------------------------------
# Set subscription
# -----------------------------------------------------------------------------
echo "Setting subscription to $SUBSCRIPTION_ID..."
az account set --subscription "$SUBSCRIPTION_ID"

# -----------------------------------------------------------------------------
# Create Resource Group
# -----------------------------------------------------------------------------
echo "Creating resource group $RESOURCE_GROUP in $LOCATION..."
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --tags $TAGS

# -----------------------------------------------------------------------------
# Create Azure AI Search Service
# -----------------------------------------------------------------------------
echo "Creating Azure AI Search service $SEARCH_SERVICE_NAME..."
az search service create \
  --name "$SEARCH_SERVICE_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku "$SEARCH_SKU" \
  --partition-count 1 \
  --replica-count 1

echo "AI Search endpoint: https://${SEARCH_SERVICE_NAME}.search.windows.net"

# Retrieve admin key
SEARCH_ADMIN_KEY=$(az search admin-key show \
  --service-name "$SEARCH_SERVICE_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "primaryKey" -o tsv)
echo "AI Search admin key retrieved (store in Key Vault)."

# -----------------------------------------------------------------------------
# Create Azure OpenAI Service
# -----------------------------------------------------------------------------
echo "Creating Azure OpenAI service $OPENAI_SERVICE_NAME..."
az cognitiveservices account create \
  --name "$OPENAI_SERVICE_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --kind "OpenAI" \
  --sku "$OPENAI_SKU" \
  --custom-domain "$OPENAI_SERVICE_NAME"

echo "OpenAI endpoint: https://${OPENAI_SERVICE_NAME}.openai.azure.com/"

# Deploy text-embedding-ada-002 for document embeddings
echo "Deploying text-embedding-ada-002 model..."
az cognitiveservices account deployment create \
  --name "$OPENAI_SERVICE_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --deployment-name "text-embedding-ada-002" \
  --model-name "text-embedding-ada-002" \
  --model-version "2" \
  --model-format "OpenAI" \
  --sku-name "Standard" \
  --sku-capacity 120

# Deploy GPT-4o for orchestration / enrichment
echo "Deploying GPT-4o model..."
az cognitiveservices account deployment create \
  --name "$OPENAI_SERVICE_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --deployment-name "gpt-4o" \
  --model-name "gpt-4o" \
  --model-version "2024-08-06" \
  --model-format "OpenAI" \
  --sku-name "GlobalStandard" \
  --sku-capacity 30

# Retrieve OpenAI key
OPENAI_KEY=$(az cognitiveservices account keys list \
  --name "$OPENAI_SERVICE_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "key1" -o tsv)
echo "OpenAI key retrieved (store in Key Vault)."

# -----------------------------------------------------------------------------
# Create Storage Account (staging)
# -----------------------------------------------------------------------------
echo "Creating storage account $STORAGE_ACCOUNT_NAME..."
az storage account create \
  --name "$STORAGE_ACCOUNT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku "$STORAGE_SKU" \
  --kind "StorageV2" \
  --enable-hierarchical-namespace true

# Create containers
STORAGE_KEY=$(az storage account keys list \
  --account-name "$STORAGE_ACCOUNT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "[0].value" -o tsv)

az storage container create \
  --name "raw-data" \
  --account-name "$STORAGE_ACCOUNT_NAME" \
  --account-key "$STORAGE_KEY"

az storage container create \
  --name "unstructured-docs" \
  --account-name "$STORAGE_ACCOUNT_NAME" \
  --account-key "$STORAGE_KEY"

# -----------------------------------------------------------------------------
# Create Key Vault
# -----------------------------------------------------------------------------
echo "Creating Key Vault $KEYVAULT_NAME..."
az keyvault create \
  --name "$KEYVAULT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --enable-rbac-authorization true

# Store secrets
echo "Storing secrets in Key Vault..."
az keyvault secret set \
  --vault-name "$KEYVAULT_NAME" \
  --name "search-admin-key" \
  --value "$SEARCH_ADMIN_KEY"

az keyvault secret set \
  --vault-name "$KEYVAULT_NAME" \
  --name "openai-api-key" \
  --value "$OPENAI_KEY"

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo "============================================="
echo "  Manulife Fabric POC — Resource Summary"
echo "============================================="
echo "Resource Group:    $RESOURCE_GROUP"
echo "Location:          $LOCATION"
echo ""
echo "AI Search:         https://${SEARCH_SERVICE_NAME}.search.windows.net"
echo "Azure OpenAI:      https://${OPENAI_SERVICE_NAME}.openai.azure.com/"
echo "Storage Account:   $STORAGE_ACCOUNT_NAME"
echo "Key Vault:         $KEYVAULT_NAME"
echo ""
echo "Models Deployed:"
echo "  - text-embedding-ada-002 (embeddings)"
echo "  - gpt-4o (orchestration)"
echo ""
echo "Next Steps:"
echo "  1. Provision Fabric capacity via admin.powerbi.com"
echo "  2. Create Fabric workspace and assign capacity"
echo "  3. Create Lakehouse and upload data"
echo "  4. Follow the POC runbook: docs/poc-runbook.md"
echo "============================================="
