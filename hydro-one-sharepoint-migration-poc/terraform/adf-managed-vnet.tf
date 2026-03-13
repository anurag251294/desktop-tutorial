###############################################################################
# ADF Managed VNet Integration Runtime + Managed Private Endpoints
#
# ADF Managed VNet provides:
# - Private connectivity to Azure PaaS services
# - Outbound internet access (Graph API, login.microsoftonline.com)
# - No VM to manage (unlike Self-Hosted IR)
# - 2-5 min cold-start on first pipeline run
#
# After deployment, managed private endpoints must be MANUALLY APPROVED
# on each target resource (Storage, SQL, Key Vault).
###############################################################################

# =============================================================================
# Enable Managed VNet on existing ADF (required before creating VNet IR)
# =============================================================================

resource "null_resource" "adf_enable_managed_vnet" {
  count = var.enable_adf_managed_vnet ? 1 : 0

  provisioner "local-exec" {
    interpreter = ["bash", "-c"]
    command     = "az rest --method PUT --url 'https://management.azure.com${data.azurerm_data_factory.main.id}/managedVirtualNetworks/default?api-version=2018-06-01' --body '{\"properties\":{}}'"
  }

  triggers = {
    adf_id = data.azurerm_data_factory.main.id
  }
}

# =============================================================================
# Managed VNet Integration Runtime
# =============================================================================

resource "azurerm_data_factory_integration_runtime_azure" "managed_vnet" {
  count                   = var.enable_adf_managed_vnet ? 1 : 0
  name                    = "ManagedVNetIntegrationRuntime"
  data_factory_id         = data.azurerm_data_factory.main.id
  location                = var.location
  virtual_network_enabled = true

  description = "Integration Runtime with Managed VNet for private endpoint connectivity"

  depends_on = [null_resource.adf_enable_managed_vnet]
}

# =============================================================================
# Managed Private Endpoints
# These create PE requests that must be approved on each target resource.
# =============================================================================

# --- Storage: Blob ---

resource "azurerm_data_factory_managed_private_endpoint" "storage_blob" {
  count              = var.enable_adf_managed_vnet ? 1 : 0
  name               = "mpe-${var.storage_account_name}-blob"
  data_factory_id    = data.azurerm_data_factory.main.id
  target_resource_id = data.azurerm_storage_account.main.id
  subresource_name   = "blob"

  depends_on = [azurerm_data_factory_integration_runtime_azure.managed_vnet]
}

# --- Storage: DFS ---

resource "azurerm_data_factory_managed_private_endpoint" "storage_dfs" {
  count              = var.enable_adf_managed_vnet ? 1 : 0
  name               = "mpe-${var.storage_account_name}-dfs"
  data_factory_id    = data.azurerm_data_factory.main.id
  target_resource_id = data.azurerm_storage_account.main.id
  subresource_name   = "dfs"

  depends_on = [azurerm_data_factory_integration_runtime_azure.managed_vnet]
}

# --- Azure SQL ---

resource "azurerm_data_factory_managed_private_endpoint" "sql" {
  count              = var.enable_adf_managed_vnet ? 1 : 0
  name               = "mpe-${var.sql_server_name}"
  data_factory_id    = data.azurerm_data_factory.main.id
  target_resource_id = data.azurerm_mssql_server.main.id
  subresource_name   = "sqlServer"

  depends_on = [azurerm_data_factory_integration_runtime_azure.managed_vnet]
}

# --- Key Vault ---

resource "azurerm_data_factory_managed_private_endpoint" "keyvault" {
  count              = var.enable_adf_managed_vnet ? 1 : 0
  name               = "mpe-${var.key_vault_name}"
  data_factory_id    = data.azurerm_data_factory.main.id
  target_resource_id = data.azurerm_key_vault.main.id
  subresource_name   = "vault"

  depends_on = [azurerm_data_factory_integration_runtime_azure.managed_vnet]
}
