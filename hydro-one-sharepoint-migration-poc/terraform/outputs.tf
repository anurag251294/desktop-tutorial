###############################################################################
# Outputs
###############################################################################

# --- VNet ---

output "vnet_id" {
  description = "ID of the created VNet"
  value       = azurerm_virtual_network.main.id
}

output "vnet_name" {
  description = "Name of the created VNet"
  value       = azurerm_virtual_network.main.name
}

output "subnet_private_endpoints_id" {
  description = "ID of the private endpoints subnet"
  value       = azurerm_subnet.private_endpoints.id
}

# --- Private Endpoint IPs ---

output "storage_blob_private_ip" {
  description = "Private IP of the storage blob private endpoint"
  value       = var.enable_storage_private_endpoint ? azurerm_private_endpoint.storage_blob[0].private_service_connection[0].private_ip_address : null
}

output "storage_dfs_private_ip" {
  description = "Private IP of the storage DFS private endpoint"
  value       = var.enable_storage_private_endpoint ? azurerm_private_endpoint.storage_dfs[0].private_service_connection[0].private_ip_address : null
}

output "sql_private_ip" {
  description = "Private IP of the SQL private endpoint"
  value       = var.enable_sql_private_endpoint ? azurerm_private_endpoint.sql[0].private_service_connection[0].private_ip_address : null
}

output "keyvault_private_ip" {
  description = "Private IP of the Key Vault private endpoint"
  value       = var.enable_keyvault_private_endpoint ? azurerm_private_endpoint.keyvault[0].private_service_connection[0].private_ip_address : null
}

# --- Private Endpoint IDs ---

output "storage_blob_private_endpoint_id" {
  description = "Resource ID of the storage blob private endpoint"
  value       = var.enable_storage_private_endpoint ? azurerm_private_endpoint.storage_blob[0].id : null
}

output "storage_dfs_private_endpoint_id" {
  description = "Resource ID of the storage DFS private endpoint"
  value       = var.enable_storage_private_endpoint ? azurerm_private_endpoint.storage_dfs[0].id : null
}

output "sql_private_endpoint_id" {
  description = "Resource ID of the SQL private endpoint"
  value       = var.enable_sql_private_endpoint ? azurerm_private_endpoint.sql[0].id : null
}

output "keyvault_private_endpoint_id" {
  description = "Resource ID of the Key Vault private endpoint"
  value       = var.enable_keyvault_private_endpoint ? azurerm_private_endpoint.keyvault[0].id : null
}

# --- ADF Managed VNet ---

output "adf_managed_vnet_ir_name" {
  description = "Name of the ADF Managed VNet Integration Runtime"
  value       = var.enable_adf_managed_vnet ? azurerm_data_factory_integration_runtime_azure.managed_vnet[0].name : null
}

# --- Approval Instructions ---

locals {
  post_deploy_instructions_enabled = <<-EOT

    ============================================================
    POST-DEPLOYMENT: Manual Steps Required
    ============================================================

    1. APPROVE ADF Managed Private Endpoints:
       Go to Azure Portal > Data Factory > Managed private endpoints
       Or run these CLI commands:

       az network private-endpoint-connection approve \
         --resource-group ${var.resource_group_name} \
         --name <connection-name> \
         --type Microsoft.Storage/storageAccounts \
         --resource-name ${var.storage_account_name} \
         --description "Approved for ADF Managed VNet"

       az network private-endpoint-connection approve \
         --resource-group ${var.resource_group_name} \
         --name <connection-name> \
         --type Microsoft.Sql/servers \
         --resource-name ${var.sql_server_name} \
         --description "Approved for ADF Managed VNet"

       az network private-endpoint-connection approve \
         --resource-group ${var.resource_group_name} \
         --name <connection-name> \
         --type Microsoft.KeyVault/vaults \
         --resource-name ${var.key_vault_name} \
         --description "Approved for ADF Managed VNet"

    2. UPDATE ADF Linked Services:
       Change connectVia to "ManagedVNetIntegrationRuntime" for:
       - LS_ADLS_Gen2
       - LS_AzureBlobStorage
       - LS_AzureSqlDatabase
       - LS_AzureKeyVault
       - LS_HTTP_Graph_Download
       - LS_REST_Graph_API

    3. VALIDATE: Run PL_Master_Migration_Orchestrator

    4. LOCKDOWN: Set disable_*_public_access = true in
       terraform.tfvars and run terraform apply again

    ============================================================
  EOT
}

output "post_deployment_instructions" {
  description = "Steps to complete after terraform apply"
  value       = var.enable_adf_managed_vnet ? local.post_deploy_instructions_enabled : "ADF Managed VNet not enabled - no approval steps needed."
}
