#!/bin/bash
# Tear down the Fabric demo resources to avoid charges
set -euo pipefail

RESOURCE_GROUP="rg-fabric-demo"

echo "Deleting resource group '$RESOURCE_GROUP' and all resources..."
az group delete --name "$RESOURCE_GROUP" --yes --no-wait
echo "✓ Deletion started (runs in background). Resources will be removed in ~5 minutes."
