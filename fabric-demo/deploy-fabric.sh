#!/bin/bash
# =============================================================================
# Microsoft Fabric Demo - One-Click Deployment
# Creates a Fabric capacity + resource group for a quick analytics demo
# =============================================================================

set -euo pipefail

# Configuration
RESOURCE_GROUP="rg-fabric-demo"
LOCATION="canadacentral"
CAPACITY_NAME="fabdemo$(date +%s | tail -c 6)"
SKU="F2"                          # Smallest Fabric SKU
ADMIN_EMAIL="anuragdhuria@MngEnvMCAP510531.onmicrosoft.com"
SUBSCRIPTION="671b1321-4407-420b-b877-97cd40ba898a"

echo "=========================================="
echo "  Microsoft Fabric Demo Deployment"
echo "=========================================="
echo ""
echo "  Resource Group : $RESOURCE_GROUP"
echo "  Location       : $LOCATION"
echo "  Capacity       : $CAPACITY_NAME (SKU: $SKU)"
echo "  Admin          : $ADMIN_EMAIL"
echo ""

# Set subscription
az account set --subscription "$SUBSCRIPTION"

# 1. Create resource group
echo "[1/3] Creating resource group..."
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none

echo "  ✓ Resource group '$RESOURCE_GROUP' created"

# 2. Create Fabric capacity
echo "[2/3] Creating Fabric capacity (this takes ~2 minutes)..."
az fabric capacity create \
  --resource-group "$RESOURCE_GROUP" \
  --capacity-name "$CAPACITY_NAME" \
  --location "$LOCATION" \
  --sku "{name:$SKU,tier:Fabric}" \
  --administration "{members:[$ADMIN_EMAIL]}" \
  --output none

echo "  ✓ Fabric capacity '$CAPACITY_NAME' created"

# 3. Show the result
echo "[3/3] Verifying deployment..."
az fabric capacity show \
  --resource-group "$RESOURCE_GROUP" \
  --capacity-name "$CAPACITY_NAME" \
  --output table

echo ""
echo "=========================================="
echo "  Deployment Complete!"
echo "=========================================="
echo ""
echo "  Next steps:"
echo "  1. Go to https://app.fabric.microsoft.com"
echo "  2. Create a new Workspace and assign it to capacity '$CAPACITY_NAME'"
echo "  3. Create a Lakehouse named 'SalesLakehouse'"
echo "  4. Import the notebook: fabric-demo/sales_analytics_notebook.py"
echo "  5. Run the notebook to generate sample data & charts"
echo ""
echo "  To clean up:  az group delete -n $RESOURCE_GROUP --yes --no-wait"
echo ""
