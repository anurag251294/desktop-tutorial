#!/bin/bash
# Microsoft Fabric Capacity - Administration Field Test Commands
# Date: 2026-01-21
# Purpose: Validate whether administration field is required for Fabric capacity creation

# =============================================================================
# SETUP
# =============================================================================

# Login to Azure
az login

# Set variables
SUBSCRIPTION_ID="<your-subscription-id>"
RESOURCE_GROUP="<your-resource-group>"
CAPACITY_NAME="<your-capacity-name>"
LOCATION="<your-location>"  # e.g., eastus, westus, etc.
ADMIN_EMAIL="<your-admin-email>"  # e.g., admin@contoso.com

# =============================================================================
# PREREQUISITES
# =============================================================================

# Check current account
az account show -o json

# List resource groups
az group list -o table

# Create resource group (if needed)
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" -o json

# Register Microsoft.Fabric provider
az provider register --namespace Microsoft.Fabric

# Check registration status (wait until "Registered")
az provider show -n Microsoft.Fabric --query "registrationState" -o tsv

# Install Fabric CLI extension
az extension add --name microsoft-fabric --yes

# =============================================================================
# TEST 1: REST API - WITHOUT administration field
# Expected: HTTP 400 "At least one capacity administrator is required"
# =============================================================================

az rest --method PUT \
  --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.Fabric/capacities/${CAPACITY_NAME}?api-version=2023-11-01" \
  --body "{
    \"location\": \"${LOCATION}\",
    \"sku\": {
      \"name\": \"F2\",
      \"tier\": \"Fabric\"
    },
    \"properties\": {}
  }"

# =============================================================================
# TEST 2: REST API - WITH administration field
# Expected: HTTP 200 (or 401 if user lacks Fabric Admin role)
# =============================================================================

az rest --method PUT \
  --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.Fabric/capacities/${CAPACITY_NAME}?api-version=2023-11-01" \
  --body "{
    \"location\": \"${LOCATION}\",
    \"sku\": {
      \"name\": \"F2\",
      \"tier\": \"Fabric\"
    },
    \"properties\": {
      \"administration\": {
        \"members\": [\"${ADMIN_EMAIL}\"]
      }
    }
  }"

# =============================================================================
# TEST 3: Azure CLI - WITHOUT administration flag
# Expected: HTTP 400 "At least one capacity administrator is required"
# =============================================================================

az fabric capacity create \
  --resource-group "$RESOURCE_GROUP" \
  --capacity-name "$CAPACITY_NAME" \
  --sku "{name:F2,tier:Fabric}" \
  --location "$LOCATION"

# =============================================================================
# TEST 4: Azure CLI - WITH administration flag
# Expected: HTTP 200 (or 401 if user lacks Fabric Admin role)
# =============================================================================

az fabric capacity create \
  --resource-group "$RESOURCE_GROUP" \
  --capacity-name "$CAPACITY_NAME" \
  --sku "{name:F2,tier:Fabric}" \
  --location "$LOCATION" \
  --administration "{members:[${ADMIN_EMAIL}]}"

# =============================================================================
# HELPER COMMANDS
# =============================================================================

# Check CLI help to see if administration is marked as required
az fabric capacity create --help

# List available Fabric SKUs
az fabric capacity list-skus -o table

# Check Fabric capacity resource type details
az provider show -n Microsoft.Fabric -o json --query "resourceTypes[?resourceType=='capacities']"

# Check user's role assignments
az role assignment list --all --output table

# Check user's directory roles (for Fabric Admin)
az rest --method GET --url "https://graph.microsoft.com/v1.0/me/memberOf" -o json

# List all activated directory roles in tenant
az rest --method GET --url "https://graph.microsoft.com/v1.0/directoryRoles" -o json

# Search for Fabric Administrator role template
az rest --method GET --url "https://graph.microsoft.com/v1.0/directoryRoleTemplates" -o json | grep -i -A5 -B5 "fabric"

# =============================================================================
# CLEANUP (if needed)
# =============================================================================

# Delete the capacity (if created)
# az fabric capacity delete --resource-group "$RESOURCE_GROUP" --capacity-name "$CAPACITY_NAME" --yes

# Delete the resource group
# az group delete --name "$RESOURCE_GROUP" --yes --no-wait
