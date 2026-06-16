# Fabric-native SharePoint → OneLake migration

This is the **recommended** migration path. Instead of porting the legacy Azure
Data Factory pipelines, it uses Fabric-native building blocks to move SharePoint
document libraries straight into **OneLake** — no external storage account, no
ADLS Gen2, and the file content never leaves the Fabric workspace boundary.

> The ADF→Fabric conversion scripts (`Convert-ADF-To-FDF.ps1` /
> `Deploy-FDF-Templates.ps1`) are kept for reference, but this native stack
> supersedes them.

## Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │  PL_Migrate_Master (Data pipeline)           │
                    │                                              │
  SharePoint  ──────┤  1) Refresh_Inventory  → ExecutePipeline ───┼──► PL_SharePoint_Inventory
   (Graph /         │                                              │      SharePoint Online connector
    connector)      │  2) Migrate_Content    → TridentNotebook ───┼──► Migrate_SharePoint_Content
                    │                                              │      PySpark: Graph → OneLake
                    └─────────────────────────────────────────────┘
                                       │                 │
                                       ▼                 ▼
                          Lakehouse  HydroOneMigration  (OneLake)
                            Tables/sharepoint_inventory   (metadata, Delta)
                            Tables/migration_audit        (per-file results)
                            Tables/migration_watermark    (delta links)
                            Files/<site>/<library>/...     (binary documents)
```

- **Inventory (SharePoint connector).** `PL_SharePoint_Inventory` uses Fabric's
  native **SharePoint Online** connector to copy document-library metadata into
  the Lakehouse Delta table `sharepoint_inventory`.
- **Content (Spark).** `Migrate_SharePoint_Content` authenticates to Microsoft
  Graph with a service principal, enumerates files (full, or **delta/incremental**
  via Graph delta links), streams each binary into the Lakehouse **Files** area,
  and records results in `migration_audit` / `migration_watermark` Delta tables.
- **Sink: OneLake.** All output lands in the workspace Lakehouse via the OneLake
  ABFS path (`abfss://<workspace>@onelake.dfs.fabric.microsoft.com/<lakehouse>/…`),
  so it works in headless pipeline runs without the `/lakehouse` POSIX mount.

## Requirements

- Windows PowerShell 5.1 or PowerShell 7+ (the deploy script runs on both).
- Azure CLI signed in (`az login`) with **Contributor** on the target workspace.
- An Entra **app registration** (service principal) with Graph
  `Sites.Read.All` + `Files.Read.All`, and its secret stored in **Key Vault**.
- A Fabric **SharePoint Online connection** in the workspace (for the inventory
  pipeline). The Spark content path uses the service principal above, not this
  connection.

## Deploy

```powershell
az login
Copy-Item .\fabric-native\config\fabric-native.sample.json .\fabric-native\config\fabric-native.json
# edit fabric-native.json: graph tenant/client, Key Vault, sites, and (optionally)
# the SharePoint connection GUID

.\scripts\Deploy-FabricNative.ps1 -WorkspaceId "<workspace-guid>" -ConfigPath .\fabric-native\config\fabric-native.json
```

The deploy is **idempotent** and resolves every cross-item reference for you:

1. Ensures the Lakehouse exists.
2. Assembles the notebook `.ipynb` from `notebook.py` (injecting the default
   Lakehouse and the workspace/lakehouse parameter defaults) and creates it.
3. Creates the pipelines, then — once every item has a GUID — rewrites
   `ExecutePipeline` references, the `TridentNotebook` `notebookId`, and the
   Lakehouse `workspaceId`/`artifactId` to real GUIDs (Fabric rejects name-based
   references).

`-WhatIf` is a fully offline dry-run (no token, no Fabric calls) that validates
the notebook/pipeline assembly locally.

### SharePoint connection

`PL_SharePoint_Inventory` needs a real SharePoint connection GUID
(`sharePointConnectionId` in the config). Until one is supplied the deploy creates
it as an empty **skeleton** and prints a warning — the rest of the stack still
deploys, and the master pipeline's reference to it still resolves. Set the GUID
and re-run to bind it.

## Run

Run `PL_Migrate_Master` from the Fabric UI (or via the Jobs REST API), passing
`SiteUrl`, `LibraryName`, and `Mode` (`full` or `incremental`). It refreshes the
inventory, then runs the notebook to copy content into OneLake. Re-runs are
incremental: the notebook resumes from the stored Graph delta link per
site/library.

## Notebook parameters

| Parameter | Purpose |
|-----------|---------|
| `workspace_id`, `lakehouse_id` | OneLake target (deploy injects defaults). |
| `tenant_id`, `client_id` | Graph service principal. |
| `key_vault_uri`, `client_secret_name` | Where the notebook reads the SP secret at run time. |
| `site_url`, `library_name` | SharePoint document library to migrate. |
| `mode` | `full` (enumerate children) or `incremental` (Graph delta). |

With no `site_url`, the notebook runs a **smoke test** that writes a sample file
to `Files/_smoketest` and a `migration_smoke` Delta table — used to validate the
OneLake write path end to end.
