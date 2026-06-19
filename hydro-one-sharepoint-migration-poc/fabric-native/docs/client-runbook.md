# Hydro One SharePoint → OneLake — Client Runbook

A step-by-step guide for deploying and operating the **Fabric-native** SharePoint
migration. Everything lands in **OneLake** inside your Fabric workspace — there is
no external storage account to provision or pay for.

- **Audience:** the team that will run the migration in Hydro One's tenant.
- **What you need going in:** a Fabric workspace on a paid/trial capacity, rights
  to create an Entra app registration, an Azure Key Vault, and Contributor on the
  workspace.
- **Companion docs:** [`fabric-native-migration.md`](fabric-native-migration.md)
  (architecture deep-dive). Artifacts live under `fabric-native/`.

---

## 1. How it works (one diagram)

```
 SharePoint Online                         Fabric workspace
 (Hydro One tenant)                        ┌───────────────────────────────────────┐
                                           │  PL_Migrate_Master (pipeline)          │
   Document libraries                      │   1. Refresh_Inventory ─► PL_SharePoint_Inventory
        │                                  │        (SharePoint Online connector)   │
        │  Microsoft Graph (HTTPS)         │   2. Migrate_Content  ─► Migrate_SharePoint_Content
        ▼                                  │        (Spark notebook)                │
   ┌─────────────┐                         └───────────────┬───────────────────────┘
   │ files +     │                                         │
   │ metadata    │                                         ▼
   └─────────────┘                          Lakehouse: HydroOneMigration  (OneLake)
                                              Files/<site>/<library>/...      ← documents
                                              Tables/sharepoint_inventory     ← what to migrate
                                              Tables/migration_audit          ← per-file result
                                              Tables/migration_watermark      ← delta resume point
```

**Two engines, by design:**
- **Inventory** uses the native **SharePoint Online connector** (no code) to list
  what exists.
- **Content** uses a **Spark notebook** that downloads binaries via Graph and
  writes them to OneLake — reliable for large/binary document libraries and
  supports **incremental** re-runs via Graph delta links.

---

## 2. Prerequisites

| # | Item | Notes |
|---|------|-------|
| 1 | **Fabric workspace** on a capacity (F-SKU or trial) | The migration items and OneLake storage live here. To attach a capacity: `.\fabric-native\scripts\Assign-WorkspaceCapacity.ps1 -Workspace "<name-or-guid>" -Capacity "<name-or-guid>"` (use `-Unassign` to detach). |
| 2 | **Azure CLI** signed in (`az login`) | The deploy script gets its Fabric token from the CLI. Account needs **Contributor** on the workspace. |
| 3 | **Windows PowerShell 5.1** or **PowerShell 7+** | The deploy script runs on the stock Windows shell — no `pwsh` install required. |
| 4 | **Entra app registration** (service principal) | Used by the Spark notebook to read SharePoint via Graph. |
| 5 | **Azure Key Vault** | Stores the app's client secret. The notebook reads it at run time; the secret is never written to config or code. |
| 6 | **Fabric SharePoint Online connection** | *Not required.* The notebook now builds `sharepoint_inventory` itself over Graph. The legacy connector pipeline (`PL_SharePoint_Inventory`) is only an optional alternative — leave `sharePointConnectionId` blank and skip step 2c. |

> The whole flow is **Azure CLI–driven**: `az login` → run the deploy script (it
> gets its Fabric token from `az`) → start the migration with `az rest`. The only
> non-CLI step is the optional Fabric SharePoint connection (2c).

### 2a. App registration + Graph permissions (az CLI)

Run these once. They create the app, grant the Graph **application** permissions
the notebook needs, admin-consent them, and mint a secret.

```bash
# 1) Create the app registration + service principal
appId=$(az ad app create --display-name "HydroOne-SPO-Migration" --query appId -o tsv)
az ad sp create --id "$appId"

# 2) Grant Microsoft Graph application permissions:
#    Sites.Read.All = 332a536c-c7ef-4017-ab91-336970924f0d
#    Files.Read.All = 01d4889c-1287-42c6-ac1f-5d1e02578ef6
az ad app permission add --id "$appId" --api 00000003-0000-0000-c000-000000000000 \
  --api-permissions 332a536c-c7ef-4017-ab91-336970924f0d=Role 01d4889c-1287-42c6-ac1f-5d1e02578ef6=Role

# 3) Admin-consent (requires Global Admin / Privileged Role Admin)
az ad app permission admin-consent --id "$appId"

# 4) Create a client secret
secret=$(az ad app credential reset --id "$appId" --display-name "fabric-migration" --years 1 --query password -o tsv)

# 5) Record these for the config:
tenantId=$(az account show --query tenantId -o tsv)
echo "tenantId=$tenantId"; echo "clientId=$appId"
```

> PowerShell users: same `az` commands; capture with `$appId = az ad app create ... -o tsv`.

### 2b. Store the secret in Key Vault (az CLI)

```bash
az keyvault secret set --vault-name <your-keyvault> --name graph-client-secret --value "$secret"
```

Grant the identity that runs the notebook **Key Vault Secrets User** on the vault:

```bash
az role assignment create --assignee "$appId" --role "Key Vault Secrets User" \
  --scope $(az keyvault show --name <your-keyvault> --query id -o tsv)
```

### 2c. (Skip — no longer needed) Fabric SharePoint connection

**You can skip this step entirely.** The migration notebook now writes the
`sharepoint_inventory` table itself, from the same Graph enumeration it uses to
move content — so no Fabric SharePoint connection is required. Leave
`sharePointConnectionId` blank; `PL_SharePoint_Inventory` deploys as a harmless
empty skeleton and is simply unused.

> Only if you specifically want the low-code **SharePoint Online list** connector
> instead: Fabric portal → **Settings → Manage connections and gateways → New** →
> **SharePoint Online list** → authenticate with an **organizational account**
> (the connector does *not* accept the app's service principal) → **Create**, then
> put the connection **GUID** in `sharePointConnectionId` and re-deploy. Common
> failure: pasting a deep library URL — use the **root site URL**
> (`https://<tenant>.sharepoint.com`).

---

## 3. Configure

```powershell
Copy-Item .\fabric-native\config\fabric-native.sample.json .\fabric-native\config\fabric-native.json
```

Edit `fabric-native.json`:

```jsonc
{
  "lakehouseName": "HydroOneMigration",          // OneLake sink (auto-created)
  "sharePointConnectionId": "<connection-guid>", // from step 2c (blank = inventory deploys as a skeleton)
  "graph": {
    "tenantId": "<directory-tenant-id>",
    "clientId": "<application-client-id>",
    "keyVaultUri": "https://<your-keyvault>.vault.azure.net/",
    "clientSecretName": "graph-client-secret"
  },
  "sites": [
    { "siteUrl": "https://<tenant>.sharepoint.com/sites/<site>", "libraryName": "Documents", "mode": "full" }
  ]
}
```

> The secret itself is **never** placed in this file — only the Key Vault name and
> secret name. The notebook fetches the secret at run time.

---

## 4. Deploy

```powershell
az login
.\fabric-native\scripts\Deploy-FabricNative.ps1 -WorkspaceId "<workspace-guid>" -ConfigPath .\fabric-native\config\fabric-native.json
```

This single command, **idempotently**:

1. Creates the **Lakehouse** if missing.
2. Assembles the notebook `.ipynb` from `notebook.py` (baking in the workspace and
   Lakehouse IDs **and the Graph identity** from your config — tenant/client/vault,
   never the secret) and deploys it.
3. Creates the pipelines, then rewrites every cross-item reference
   (pipeline→pipeline, pipeline→notebook, and the Lakehouse IDs) to real GUIDs —
   Fabric rejects name-based references, so this is done for you.

Re-running is safe: existing items are updated in place.

**Dry run (offline, no Fabric calls):**

```powershell
.\fabric-native\scripts\Deploy-FabricNative.ps1 -WorkspaceId "<workspace-guid>" -ConfigPath .\fabric-native\config\fabric-native.json -WhatIf
```

> If `sharePointConnectionId` is left blank, the inventory pipeline is created as
> an empty **skeleton** and the deploy prints a warning. The rest of the stack
> still deploys and the master pipeline still references it. Set the GUID and
> re-run to bind it.

---

## 5. Run the migration

The deploy **bakes the Graph identity** (`tenant_id`, `client_id`, `keyVaultUri`,
`clientSecretName`) into the notebook from your config, so a run only needs the
site/library/mode. The client secret is fetched from Key Vault at run time.

The deploy prints each item's GUID, e.g.
`Migrate_SharePoint_Content -> <notebook-id>`. Use it below.

### Option A — run the content notebook directly (az CLI)

```bash
ws="<workspace-guid>"; nb="<notebook-id>"
az rest --method post \
  --url "https://api.fabric.microsoft.com/v1/workspaces/$ws/items/$nb/jobs/instances?jobType=RunNotebook" \
  --resource "https://api.fabric.microsoft.com" \
  --headers "Content-Type=application/json" \
  --body '{"executionData":{"parameters":{
            "site_url":{"value":"https://<tenant>.sharepoint.com/sites/<site>","type":"string"},
            "library_name":{"value":"Documents","type":"string"},
            "mode":{"value":"full","type":"string"}}}}'
```

`az rest` starts the job (HTTP 202). Poll its status until `Completed`:

```bash
az rest --method get \
  --url "https://api.fabric.microsoft.com/v1/workspaces/$ws/items/$nb/jobs/instances" \
  --resource "https://api.fabric.microsoft.com" --query "value[-1].status" -o tsv
```

### Option B — run the master pipeline (inventory + content)

```bash
ws="<workspace-guid>"; pl="<PL_Migrate_Master-id>"
az rest --method post \
  --url "https://api.fabric.microsoft.com/v1/workspaces/$ws/items/$pl/jobs/instances?jobType=Pipeline" \
  --resource "https://api.fabric.microsoft.com" \
  --headers "Content-Type=application/json" \
  --body '{"executionData":{"parameters":{
            "SiteUrl":{"value":"https://<tenant>.sharepoint.com/sites/<site>","type":"string"},
            "LibraryName":{"value":"Documents","type":"string"},
            "Mode":{"value":"full","type":"string"}}}}'
```

| Parameter | Example | Meaning |
|-----------|---------|---------|
| `site_url` / `SiteUrl` | `https://contoso.sharepoint.com/sites/Eng` | The SharePoint site. |
| `library_name` / `LibraryName` | `Documents` | The document library. |
| `mode` / `Mode` | `full` or `incremental` | `full` copies everything; `incremental` resumes from the saved Graph delta link. |

**Initial load then ongoing sync:** run once with `mode=full` (or `incremental`,
which on a first run enumerates everything via Graph delta and recurses subfolders),
then schedule it with `mode=incremental` — each run only transfers what changed.
(Portal alternative: open the item and click **Run** / **Schedule**.)

---

## 6. Verify & monitor

**In the Lakehouse (OneLake):**
- `Files/<site>/<library>/…` — the migrated documents (browse in the Lakehouse explorer).
- `Tables/migration_audit` — one row per file: `name`, `size`, `status`
  (`copied` or `error: …`), `dest`, `ts_utc`.
- `Tables/migration_watermark` — the Graph delta link per `site::library`
  (the incremental resume point).
- `Tables/sharepoint_inventory` — the full library listing (files + folders with
  `relative_path`, `size`, `web_url`, `last_modified`), built by the notebook over
  Graph and upserted by `item_id` on every run. No SharePoint connection needed.

**Quick checks (SQL analytics endpoint of the Lakehouse):**

```sql
-- progress
SELECT status, COUNT(*) AS files, SUM(size) AS bytes
FROM migration_audit GROUP BY status;

-- failures to investigate
SELECT name, status, ts_utc FROM migration_audit
WHERE status LIKE 'error:%' ORDER BY ts_utc DESC;
```

**Pipeline / notebook runs:** the workspace **Monitor** hub shows each
`PL_Migrate_Master` run and the notebook job, with Spark logs for deep debugging.

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Deploy: *"InvalidPlatformFile" / "InvalidDefinitionFormat"* | Old tooling. | Use the current `Deploy-FabricNative.ps1`; it sends the correct definition shape. |
| `PL_SharePoint_Inventory` is empty / has no activities | `sharePointConnectionId` blank — **expected**. | None needed: the notebook now builds `sharepoint_inventory`. (Only bind a connection + re-deploy if you specifically want the connector pipeline instead.) |
| `sharepoint_inventory` table missing | Notebook hasn't run yet, or `site_url` blank. | Run `PL_Migrate_Master` (or the notebook); the table appears after the first run alongside `migration_audit`. |
| Notebook job fails immediately | Missing Graph permission or secret. | Confirm `Sites.Read.All`/`Files.Read.All` + admin consent, and that the Key Vault secret exists and the run identity has **Secrets User**. |
| `migration_audit` rows show `error: 403` | App lacks access to that site/library. | Grant the app access to the site collection (or use sites-selected consent). |
| Want to re-copy everything | Watermark already advanced. | Run with `Mode = full` (ignores the watermark). |

---

## 8. What is and isn't included

- **Validated end to end on a live Fabric workspace with real SharePoint data:**
  a real document library (`SalesAndMarketing` / `Documents`) was migrated via the
  deployed notebook using app-only Graph auth — **30 files / 7.96 MB** copied into
  OneLake (including nested subfolders), `migration_audit` all `copied`, and an
  **incremental re-run copied 0** (delta-link resume). This matches the prior ADF
  POC byte-for-byte. Deploy, reference resolution, the master-pipeline run, and the
  OneLake write path are all verified.
- **You provide (credential-bearing):** the app registration + Graph admin consent,
  the Key Vault secret, and — only if you want the inventory table — the Fabric
  SharePoint connection.
- **Scope note:** the inventory pipeline uses the SharePoint Online **list**
  connector for metadata; binary document **content** is moved by the Spark
  notebook (the connector alone does not move large binaries reliably). The content
  migration is fully functional without the connection.
