# Hydro One SharePoint Migration - Private Endpoints (Terraform)

## Overview

The POC environment uses public network access for simplicity and speed of setup.
For production deployments, private endpoints should be enabled to meet security and
compliance requirements. The Terraform configuration in `terraform/` adds private
networking on top of the existing resources -- it does NOT create the core resources
(ADF, Storage Account, SQL Server, Key Vault). Those are provisioned by the
`Setup-AzureResources.ps1` PowerShell script.

Key points:

- **POC**: Public access is sufficient; skip Terraform entirely.
- **Production**: Layer private endpoints on top of existing resources using Terraform.
- Terraform manages 7 files in the `terraform/` directory.
- All private endpoint feature flags default to enabled; public access lockdown defaults to disabled.

## When to Use This

Use this Terraform configuration when:

1. The POC has been validated end-to-end and you are preparing for production.
2. Security or compliance policy requires private networking (no public endpoints).
3. The organization mandates VNet-integrated data movement for ADF.

Do NOT use this during initial POC or development setup. Public access is fine for
validating pipeline logic, delta queries, and migration correctness.

## What It Provisions

| Resource | Details |
|---|---|
| Virtual Network | `10.0.0.0/16` with 2 subnets |
| Subnet: `snet-default` | `10.0.1.0/24` -- general workloads |
| Subnet: `snet-private-endpoints` | `10.0.2.0/24` -- dedicated to private endpoints |
| Private Endpoint: Storage (blob) | Connects to `sthydroonemigtest` blob sub-resource |
| Private Endpoint: Storage (dfs) | Connects to `sthydroonemigtest` dfs sub-resource |
| Private Endpoint: SQL Server | Connects to `sql-hydroone-migration-test` |
| Private Endpoint: Key Vault | Connects to `kv-hydroone-test2` |
| ADF Managed VNet Integration Runtime | Replaces AutoResolveIntegrationRuntime with managed VNet IR |
| ADF Managed Private Endpoints | ADF-managed PEs for Storage, SQL, and Key Vault |
| Private DNS Zone: `privatelink.blob.core.windows.net` | DNS resolution for Storage blob PE |
| Private DNS Zone: `privatelink.dfs.core.windows.net` | DNS resolution for Storage dfs PE |
| Private DNS Zone: `privatelink.database.windows.net` | DNS resolution for SQL Server PE |
| Private DNS Zone: `privatelink.vaultcore.azure.net` | DNS resolution for Key Vault PE |

## File Descriptions

| File | Purpose |
|---|---|
| `main.tf` | Provider configuration (azurerm >= 3.80), resource group data source, Terraform backend |
| `variables.tf` | All input variables with descriptions, types, defaults, and feature toggles |
| `outputs.tf` | Output values: VNet ID, subnet IDs, private endpoint IDs, DNS zone names |
| `network.tf` | VNet and subnet definitions, NSG rules for the private endpoint subnet |
| `private-endpoints.tf` | Private endpoints for Storage (blob + dfs), SQL Server, Key Vault |
| `adf-managed-vnet.tf` | ADF Managed VNet Integration Runtime and managed private endpoints |
| `dns-zones.tf` | Private DNS zones and VNet links for all four privatelink domains |
| `terraform.tfvars` | Environment-specific values (resource names, resource group, subscription) |

## Prerequisites

- Terraform >= 1.5.0
- Azure CLI authenticated (`az login`) with sufficient permissions
- Core resources already provisioned via `Setup-AzureResources.ps1`:
  - Azure Data Factory: `adf-hydroone-migration-test`
  - Storage Account: `sthydroonemigtest`
  - SQL Server: `sql-hydroone-migration-test`
  - Key Vault: `kv-hydroone-test2`
  - Resource Group: `rg-hydroone-migration-test`
- Existing resource names configured in `terraform.tfvars`
- Contributor role (or higher) on the resource group
- Network Contributor role if VNet is in a different resource group (not the case here)

## Deployment Steps

1. Navigate to the Terraform directory:

   ```bash
   cd terraform/
   ```

2. Update `terraform.tfvars` with actual resource names and subscription ID:

   ```hcl
   resource_group_name = "rg-hydroone-migration-test"
   location            = "canadacentral"
   subscription_id     = "671b1321-4407-420b-b877-97cd40ba898a"
   storage_account_name = "sthydroonemigtest"
   sql_server_name      = "sql-hydroone-migration-test"
   key_vault_name       = "kv-hydroone-test2"
   adf_name             = "adf-hydroone-migration-test"
   ```

3. Initialize Terraform:

   ```bash
   terraform init
   ```

4. Review the plan:

   ```bash
   terraform plan -out=tfplan
   ```

5. Apply the configuration:

   ```bash
   terraform apply tfplan
   ```

6. Validate private connectivity:
   - Open ADF Studio and trigger a test pipeline run using the new Managed VNet IR.
   - Confirm linked service connections succeed through the private endpoints.
   - Check that DNS resolution returns private IP addresses (10.0.2.x) for each service.

7. (Optional) Enable public access lockdown after PE validation:

   ```hcl
   disable_storage_public_access  = true
   disable_sql_public_access      = true
   disable_keyvault_public_access = true
   disable_adf_public_access      = true
   ```

8. Apply again:

   ```bash
   terraform plan -out=tfplan && terraform apply tfplan
   ```

## Configuration Variables

### Core Variables

| Variable | Type | Description | Default |
|---|---|---|---|
| `resource_group_name` | string | Name of the existing resource group | -- (required) |
| `location` | string | Azure region | `"canadacentral"` |
| `subscription_id` | string | Azure subscription ID | -- (required) |
| `storage_account_name` | string | Existing storage account name | -- (required) |
| `sql_server_name` | string | Existing SQL Server name | -- (required) |
| `key_vault_name` | string | Existing Key Vault name | -- (required) |
| `adf_name` | string | Existing ADF instance name | -- (required) |
| `vnet_address_space` | list(string) | VNet CIDR blocks | `["10.0.0.0/16"]` |
| `subnet_default_prefix` | string | Default subnet CIDR | `"10.0.1.0/24"` |
| `subnet_pe_prefix` | string | Private endpoint subnet CIDR | `"10.0.2.0/24"` |
| `tags` | map(string) | Tags applied to all resources | `{ project = "hydro-one-migration" }` |

### Feature Toggles

| Variable | Type | Default | Description |
|---|---|---|---|
| `enable_storage_private_endpoint` | bool | `true` | Create private endpoints for Storage (blob + dfs) |
| `enable_sql_private_endpoint` | bool | `true` | Create private endpoint for SQL Server |
| `enable_keyvault_private_endpoint` | bool | `true` | Create private endpoint for Key Vault |
| `enable_adf_managed_vnet` | bool | `true` | Create ADF Managed VNet Integration Runtime |

### Public Access Lockdown Toggles

| Variable | Type | Default | Description |
|---|---|---|---|
| `disable_storage_public_access` | bool | `false` | Disable public blob/dfs access on the storage account |
| `disable_sql_public_access` | bool | `false` | Disable public access on SQL Server |
| `disable_keyvault_public_access` | bool | `false` | Disable public access on Key Vault |
| `disable_adf_public_access` | bool | `false` | Disable public network access on ADF |

**WARNING**: Do not set any `disable_*_public_access` variable to `true` until you have
confirmed that all connectivity works through private endpoints. Premature lockdown will
break ADF pipeline execution and prevent portal access to these resources.

## Impact on ADF Linked Services

When private endpoints are enabled, the existing ADF linked services behave as follows:

| Linked Service | Change Required | Notes |
|---|---|---|
| `LS_AzureBlobStorage` | None | Managed Identity authentication works through PE without modification |
| `LS_AzureSqlDatabase` | None | Connection string resolves to private IP via DNS zone |
| `LS_KeyVault` | None | Managed Identity authentication works through PE without modification |
| `LS_HTTP_Graph_Download` | None | Microsoft Graph API is an external public endpoint; PE is not applicable |

The only change is that pipeline activities should use the new Managed VNet Integration
Runtime (`ManagedVnetIntegrationRuntime`) instead of `AutoResolveIntegrationRuntime`.
Update each linked service's `connectVia` property to reference the managed IR.

Note: `LS_HTTP_Graph_Download` must continue using the public Graph API endpoint
(`https://graph.microsoft.com`). There is no private endpoint available for external
Microsoft Graph API calls. This is expected and does not affect security posture, as
Graph API calls are authenticated via OAuth2 bearer tokens.

## Public Access Lockdown Procedure

Follow these steps strictly in order after private endpoints are provisioned:

1. **Validate PE connectivity** -- Run all pipelines end-to-end using the Managed VNet IR.
   Confirm successful data movement for Storage, SQL, and Key Vault operations.

2. **Check DNS resolution** -- From within the VNet (or via ADF debug), verify that
   service FQDNs resolve to `10.0.2.x` private IPs, not public IPs.

3. **Lock down one service at a time** -- Start with the least disruptive service:
   - First: `disable_keyvault_public_access = true` then `terraform apply`
   - Test pipelines. If passing, continue.
   - Next: `disable_sql_public_access = true` then `terraform apply`
   - Test pipelines. If passing, continue.
   - Next: `disable_storage_public_access = true` then `terraform apply`
   - Test pipelines. If passing, continue.
   - Last: `disable_adf_public_access = true` then `terraform apply`

4. **Verify portal access** -- After disabling public access, Azure Portal operations
   may require a VPN or bastion host. Confirm that administrators can still manage
   resources through approved network paths.

5. **Run full regression** -- Execute the master orchestration pipeline
   (`PL_Master_Migration_Orchestrator`) with incremental sync to confirm end-to-end
   functionality under full lockdown.

## Rollback

If private endpoints cause connectivity issues or pipeline failures:

1. Set the problematic feature toggle(s) back to `false` in `terraform.tfvars`:

   ```hcl
   disable_storage_public_access = false
   disable_sql_public_access     = false
   ```

2. Re-apply:

   ```bash
   terraform apply
   ```

3. To remove private endpoints entirely, set `enable_*_private_endpoint` variables to
   `false` and apply. Terraform will destroy the PE resources and DNS zones.

4. Switch linked services back to `AutoResolveIntegrationRuntime` if the Managed VNet
   IR is also being removed.

Rollback is non-destructive. Re-enabling public access does not affect data or
pipeline definitions. The ADF pipelines will resume using public endpoints immediately.
