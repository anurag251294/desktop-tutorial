###############################################################################
# Terraform Private Endpoints for Hydro One SharePoint Migration
#
# This configuration adds private networking to EXISTING Azure resources.
# It does NOT create or manage the core resources (ADF, Storage, SQL, KV).
#
# Deployment: See README or docs/deployment-guide-private-endpoints.md
###############################################################################

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.80"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id                = var.subscription_id
  skip_provider_registration = true
}

###############################################################################
# Data Sources — reference existing resources (read-only, no import needed)
###############################################################################

data "azurerm_resource_group" "main" {
  name = var.resource_group_name
}

data "azurerm_storage_account" "main" {
  name                = var.storage_account_name
  resource_group_name = var.resource_group_name
}

data "azurerm_mssql_server" "main" {
  name                = var.sql_server_name
  resource_group_name = var.resource_group_name
}

data "azurerm_key_vault" "main" {
  name                = var.key_vault_name
  resource_group_name = var.resource_group_name
}

data "azurerm_data_factory" "main" {
  name                = var.adf_name
  resource_group_name = var.resource_group_name
}
