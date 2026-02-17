# Hydro One SharePoint to Azure Migration POC

## Overview

This repository contains the proof-of-concept (POC) solution for migrating approximately **25 TB** of data from SharePoint Online to Azure Blob Storage / ADLS Gen2 for Hydro One.

## Project Structure

```
hydro-one-sharepoint-migration-poc/
├── adf-templates/           # Azure Data Factory ARM templates
│   ├── linkedServices/      # Linked service definitions
│   ├── datasets/            # Dataset definitions
│   ├── pipelines/           # Pipeline definitions
│   ├── triggers/            # Trigger definitions
│   └── dataflows/           # Data flow definitions
├── sql/                     # SQL scripts for control/audit tables
├── scripts/                 # PowerShell automation scripts
├── docs/                    # Documentation
│   ├── architecture.md      # Solution architecture
│   ├── runbook.md          # Operational runbook
│   └── migration-plan.md   # Phased migration plan
├── config/                  # Environment-specific parameters
│   ├── parameters.dev.json
│   └── parameters.prod.json
└── README.md
```

## Quick Start

### Prerequisites

1. Azure Subscription with Contributor access
2. Azure CLI installed and authenticated
3. PowerShell 7.x with Az module
4. PnP.PowerShell module for SharePoint operations
5. SharePoint Online admin access for app registration

### Deployment Steps

1. **Register Azure AD Application for SharePoint Access**
   ```powershell
   .\scripts\Register-SharePointApp.ps1 -TenantId "<tenant-id>"
   ```

2. **Provision Azure Resources**
   ```powershell
   .\scripts\Setup-AzureResources.ps1 -Environment "dev" -Location "canadacentral"
   ```

3. **Deploy ADF ARM Templates**
   ```bash
   az deployment group create \
     --resource-group rg-hydroone-migration-dev \
     --template-file adf-templates/arm-template.json \
     --parameters @config/parameters.dev.json
   ```

4. **Populate Control Table**
   ```powershell
   .\scripts\Populate-ControlTable.ps1 -SharePointTenantUrl "https://hydroone.sharepoint.com"
   ```

5. **Run Pilot Migration**
   - Start with a single small library to validate the approach
   - Monitor via ADF Monitor tab

## Key Features

- **Parameterized Pipelines**: All pipelines are parameterized for flexibility
- **Throttling Management**: Built-in handling for SharePoint 429 responses
- **Retry Logic**: Exponential backoff with 3 retries per file
- **Audit Logging**: Per-file audit trail for compliance
- **Validation Pipeline**: Post-migration file count and size validation
- **Incremental Sync**: Delta queries for ongoing synchronization

## Documentation

- [Architecture Overview](docs/architecture.md)
- [Operational Runbook](docs/runbook.md)
- [Migration Plan](docs/migration-plan.md)

## Support

For issues or questions:
- Hydro One IT Team: [internal contact]
- Microsoft Azure Team: [consultant contact]
- Microsoft Account Team: [TAM contact]

## License

Proprietary - Hydro One Internal Use Only
