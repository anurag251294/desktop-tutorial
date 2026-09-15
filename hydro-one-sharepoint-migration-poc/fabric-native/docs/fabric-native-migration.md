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

- **Inventory.** The notebook writes `sharepoint_inventory` from the same Graph
  enumeration it uses to move content. `PL_SharePoint_Inventory` is an optional
  alternative using the **SharePoint Online** connector; it writes its own table,
  `sharepoint_list_inventory`, so the two never overwrite each other.
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
- *Optional:* a Fabric **SharePoint Online connection**, only for the connector
  inventory pipeline. The notebook uses the service principal above.

## Deploy

```powershell
az login
Copy-Item .\fabric-native\config\fabric-native.sample.json .\fabric-native\config\fabric-native.json
# edit fabric-native.json: graph tenant/client, Key Vault, sites, and (optionally)
# the SharePoint connection GUID

.\fabric-native\scripts\Deploy-FabricNative.ps1 -WorkspaceId "<workspace-guid>" -ConfigPath .\fabric-native\config\fabric-native.json
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

`PL_SharePoint_Inventory` is optional, and needs a real SharePoint connection GUID
(`sharePointConnectionId` in the config). Until one is supplied the deploy creates
it as an empty **skeleton** and prints a warning — the rest of the stack still
deploys, and the master pipeline's reference to it still resolves. Set the GUID
and re-run to bind it.

## Run

Run `PL_Migrate_Master` from the Fabric UI (or via the Jobs REST API), passing
`SiteUrl`, `LibraryName`, and `Mode` (`full` or `incremental`). To migrate every
library in the config's `sites` list, run `scripts/Start-FabricMigration.ps1`,
which starts one run per entry in sequence. It refreshes the
inventory, then runs the notebook to copy content into OneLake. Re-runs are
incremental: the notebook resumes from the stored Graph delta link per
site/library. Folder structure is preserved, and renamed or moved folders and
files are relocated in OneLake rather than left behind at their old paths.

## Notebook parameters

| Parameter | Purpose |
|-----------|---------|
| `workspace_id`, `lakehouse_id` | OneLake target (deploy injects defaults). |
| `tenant_id`, `client_id` | Graph service principal. |
| `key_vault_uri`, `client_secret_name` | Where the notebook reads the SP secret at run time. |
| `site_url`, `library_name` | SharePoint document library to migrate. |
| `mode` | `full` (fresh, recursive Graph delta enumeration; ignores the watermark) or `incremental` (resume from the saved delta link). |

With no `site_url`, the notebook runs a **smoke test** that writes a sample file
to `Files/_smoketest` and a `migration_smoke` Delta table — used to validate the
OneLake write path end to end.
