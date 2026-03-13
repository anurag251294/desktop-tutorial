###############################################################################
# Private Endpoints + DNS Zone Groups
###############################################################################

# =============================================================================
# Storage Account — Blob sub-resource
# Used by: LS_AzureBlobStorage linked service
# =============================================================================

resource "azurerm_private_endpoint" "storage_blob" {
  count               = var.enable_storage_private_endpoint ? 1 : 0
  name                = "pe-${var.storage_account_name}-blob"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = azurerm_subnet.private_endpoints.id
  tags                = var.tags

  private_service_connection {
    name                           = "psc-${var.storage_account_name}-blob"
    private_connection_resource_id = data.azurerm_storage_account.main.id
    subresource_names              = ["blob"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.zones["blob"].id]
  }
}

# =============================================================================
# Storage Account — DFS sub-resource
# Used by: LS_ADLS_Gen2 linked service (abfss:// protocol)
# =============================================================================

resource "azurerm_private_endpoint" "storage_dfs" {
  count               = var.enable_storage_private_endpoint ? 1 : 0
  name                = "pe-${var.storage_account_name}-dfs"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = azurerm_subnet.private_endpoints.id
  tags                = var.tags

  private_service_connection {
    name                           = "psc-${var.storage_account_name}-dfs"
    private_connection_resource_id = data.azurerm_storage_account.main.id
    subresource_names              = ["dfs"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.zones["dfs"].id]
  }
}

# =============================================================================
# Azure SQL Server
# Used by: LS_AzureSqlDatabase linked service
# =============================================================================

resource "azurerm_private_endpoint" "sql" {
  count               = var.enable_sql_private_endpoint ? 1 : 0
  name                = "pe-${var.sql_server_name}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = azurerm_subnet.private_endpoints.id
  tags                = var.tags

  private_service_connection {
    name                           = "psc-${var.sql_server_name}"
    private_connection_resource_id = data.azurerm_mssql_server.main.id
    subresource_names              = ["sqlServer"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.zones["sql"].id]
  }
}

# =============================================================================
# Key Vault
# Used by: LS_AzureKeyVault linked service
# =============================================================================

resource "azurerm_private_endpoint" "keyvault" {
  count               = var.enable_keyvault_private_endpoint ? 1 : 0
  name                = "pe-${var.key_vault_name}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = azurerm_subnet.private_endpoints.id
  tags                = var.tags

  private_service_connection {
    name                           = "psc-${var.key_vault_name}"
    private_connection_resource_id = data.azurerm_key_vault.main.id
    subresource_names              = ["vault"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.zones["keyvault"].id]
  }
}

# =============================================================================
# Public Access Lockdown (Phase 5)
# These only take effect when disable_*_public_access = true
# =============================================================================

# --- Storage: network rules (manages ONLY network rules, not the full account) ---

resource "azurerm_storage_account_network_rules" "lockdown" {
  count              = var.disable_storage_public_access ? 1 : 0
  storage_account_id = data.azurerm_storage_account.main.id
  default_action     = "Deny"

  # Allow Azure services (ADF, etc.) to bypass when using managed identity
  bypass = ["AzureServices"]
}

# --- SQL Server: disable public access via CLI ---

resource "null_resource" "sql_disable_public_access" {
  count = var.disable_sql_public_access ? 1 : 0

  provisioner "local-exec" {
    interpreter = ["bash", "-c"]
    command     = "az sql server update --resource-group ${var.resource_group_name} --name ${var.sql_server_name} --enable-public-network false"
  }

  triggers = {
    disable = var.disable_sql_public_access
  }
}

# --- Key Vault: disable public access via CLI ---

resource "null_resource" "keyvault_disable_public_access" {
  count = var.disable_keyvault_public_access ? 1 : 0

  provisioner "local-exec" {
    interpreter = ["bash", "-c"]
    command     = "az keyvault update --resource-group ${var.resource_group_name} --name ${var.key_vault_name} --public-network-access Disabled"
  }

  triggers = {
    disable = var.disable_keyvault_public_access
  }
}

# --- ADF: disable public access via CLI ---

resource "null_resource" "adf_disable_public_access" {
  count = var.disable_adf_public_access ? 1 : 0

  provisioner "local-exec" {
    interpreter = ["bash", "-c"]
    command     = "az datafactory update --resource-group ${var.resource_group_name} --name ${var.adf_name} --public-network-access Disabled"
  }

  triggers = {
    disable = var.disable_adf_public_access
  }
}
