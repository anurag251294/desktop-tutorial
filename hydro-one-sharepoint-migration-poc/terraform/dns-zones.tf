###############################################################################
# Private DNS Zones + VNet Links
#
# These zones enable private name resolution so that
# e.g. sthydroonemigtest.blob.core.windows.net → 10.0.1.x
###############################################################################

locals {
  # Map of zone key → FQDN for all private DNS zones
  private_dns_zones = {
    blob         = "privatelink.blob.core.windows.net"
    dfs          = "privatelink.dfs.core.windows.net"
    sql          = "privatelink.database.windows.net"
    keyvault     = "privatelink.vaultcore.azure.net"
    datafactory  = "privatelink.datafactory.azure.net"
  }
}

# --- Private DNS Zones ---

resource "azurerm_private_dns_zone" "zones" {
  for_each            = local.private_dns_zones
  name                = each.value
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

# --- VNet Links (one per zone) ---

resource "azurerm_private_dns_zone_virtual_network_link" "links" {
  for_each              = local.private_dns_zones
  name                  = "vnetlink-${each.key}-${var.environment}"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.zones[each.key].name
  virtual_network_id    = azurerm_virtual_network.main.id
  registration_enabled  = false
  tags                  = var.tags
}
