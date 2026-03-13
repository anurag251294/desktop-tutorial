###############################################################################
# Test Environment Values — Hydro One SharePoint Migration POC
###############################################################################

subscription_id      = "671b1321-4407-420b-b877-97cd40ba898a"
resource_group_name  = "rg-hydroone-migration-test"
location             = "canadacentral"
environment          = "test"

# Existing resources
adf_name             = "adf-hydroone-migration-test"
storage_account_name = "sthydroonemigtest"
sql_server_name      = "sql-hydroone-migration-test"
key_vault_name       = "kv-hydroone-test2"

# Network
vnet_address_space              = ["10.0.0.0/16"]
subnet_default_prefix           = "10.0.0.0/24"
subnet_private_endpoints_prefix = "10.0.1.0/24"

# Enable all private endpoints
enable_storage_private_endpoint  = true
enable_sql_private_endpoint      = true
enable_keyvault_private_endpoint = true
enable_adf_managed_vnet          = true

# Phase 5: Set these to true AFTER validating private connectivity
disable_storage_public_access  = false
disable_sql_public_access      = false
disable_keyvault_public_access = false
disable_adf_public_access      = false
