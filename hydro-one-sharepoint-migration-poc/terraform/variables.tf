###############################################################################
# Variables
###############################################################################

# --- Existing Resource References ---

variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "resource_group_name" {
  description = "Name of the existing resource group"
  type        = string
}

variable "location" {
  description = "Azure region (must match existing resources)"
  type        = string
  default     = "canadacentral"
}

variable "environment" {
  description = "Environment name used in resource naming"
  type        = string
  default     = "test"
}

variable "adf_name" {
  description = "Name of the existing Azure Data Factory"
  type        = string
}

variable "storage_account_name" {
  description = "Name of the existing ADLS Gen2 storage account"
  type        = string
}

variable "sql_server_name" {
  description = "Name of the existing Azure SQL Server (logical server)"
  type        = string
}

variable "key_vault_name" {
  description = "Name of the existing Azure Key Vault"
  type        = string
}

# --- Network Configuration ---

variable "vnet_address_space" {
  description = "Address space for the VNet"
  type        = list(string)
  default     = ["10.0.0.0/16"]
}

variable "subnet_default_prefix" {
  description = "CIDR for the default subnet"
  type        = string
  default     = "10.0.0.0/24"
}

variable "subnet_private_endpoints_prefix" {
  description = "CIDR for the private endpoints subnet"
  type        = string
  default     = "10.0.1.0/24"
}

# --- Feature Toggles: Private Endpoints ---

variable "enable_storage_private_endpoint" {
  description = "Create private endpoints for ADLS Gen2 (blob + dfs)"
  type        = bool
  default     = true
}

variable "enable_sql_private_endpoint" {
  description = "Create private endpoint for Azure SQL"
  type        = bool
  default     = true
}

variable "enable_keyvault_private_endpoint" {
  description = "Create private endpoint for Key Vault"
  type        = bool
  default     = true
}

variable "enable_adf_managed_vnet" {
  description = "Create ADF Managed VNet Integration Runtime and managed private endpoints"
  type        = bool
  default     = true
}

# --- Feature Toggles: Public Access Lockdown ---
# WARNING: Only set these to true AFTER validating private connectivity works.

variable "disable_storage_public_access" {
  description = "Disable public network access on the storage account. Only enable after PE validation."
  type        = bool
  default     = false
}

variable "disable_sql_public_access" {
  description = "Disable public network access on Azure SQL. Only enable after PE validation."
  type        = bool
  default     = false
}

variable "disable_keyvault_public_access" {
  description = "Disable public network access on Key Vault. Only enable after PE validation."
  type        = bool
  default     = false
}

variable "disable_adf_public_access" {
  description = "Disable public network access on ADF. Only enable after PE validation."
  type        = bool
  default     = false
}

# --- Tags ---

variable "tags" {
  description = "Tags applied to all new resources"
  type        = map(string)
  default = {
    Project     = "Hydro One SharePoint Migration"
    ManagedBy   = "Terraform"
    Component   = "Private Networking"
  }
}
