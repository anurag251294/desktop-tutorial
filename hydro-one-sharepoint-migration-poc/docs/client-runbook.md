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
| 1 | **Fabric workspace** on a capacity (F-SKU or trial) | The migration items and OneLake storage live here. |
| 2 | **Azure CLI** signed in (`az login`) | The deploy script gets its Fabric token from the CLI. Account needs **Contributor** on the workspace. |
| 3 | **Windows PowerShell 5.1** or **PowerShell 7+** | The deploy script runs on the stock Windows shell — no `pwsh` install required. |
| 4 | **Entra app registration** (service principal) | Used by the Spark notebook to read SharePoint via Graph. |
| 5 | **Azure Key Vault** | Stores the app's client secret. The notebook reads it at run time; the secret is never written to config or code. |
| 6 | **Fabric SharePoint Online connection** | Used by the inventory pipeline. Created once in the Fabric portal. |

### 2a. App registration + Graph permissions

1. Entra ID → **App registrations** → **New registration** (single tenant is fine
   for same-tenant SharePoint).
2. **API permissions** → Microsoft Graph → **Application permissions** → add
   **`Sites.Read.All`** and **`Files.Read.All`** → **Grant admin consent**.
3. **Certificates & secrets** → **New client secret** → copy the value.
4. Note the **Application (client) ID** and **Directory (tenant) ID**.

### 2b. Store the secret in Key Vault

```powershell
az keyvault secret set --vault-name <your-keyvault> --name graph-client-secret --value "<the-secret-value>"
```

Grant the identity that runs the notebook **Key Vault Secrets User** on the vault
(the workspace identity, or the same service principal).

### 2c. Create the Fabric SharePoint connection

In the Fabric portal: **Settings → Manage connections and gateways → New** →
**SharePoint Online list** → enter a site URL and authenticate → **Create**.
Copy the connection's **GUID** (Settings → the connection → ID). You'll paste it
into the config below.

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
.\scripts\Deploy-FabricNative.ps1 -WorkspaceId "<workspace-guid>" -ConfigPath .\fabric-native\config\fabric-native.json
```

This single command, **idempotently**:

1. Creates the **Lakehouse** if missing.
2. Assembles the notebook `.ipynb` from `notebook.py` (injecting the workspace and
   Lakehouse IDs) and deploys it.
3. Creates the pipelines, then rewrites every cross-item reference
   (pipeline→pipeline, pipeline→notebook, and the Lakehouse IDs) to real GUIDs —
   Fabric rejects name-based references, so this is done for you.

Re-running is safe: existing items are updated in place.

**Dry run (offline, no Fabric calls):**

```powershell
.\scripts\Deploy-FabricNative.ps1 -WorkspaceId "<workspace-guid>" -ConfigPath .\fabric-native\config\fabric-native.json -WhatIf
```

> If `sharePointConnectionId` is left blank, the inventory pipeline is created as
> an empty **skeleton** and the deploy prints a warning. The rest of the stack
> still deploys and the master pipeline still references it. Set the GUID and
> re-run to bind it.

---

## 5. Run the migration

Run **`PL_Migrate_Master`** from the Fabric portal (**Run**) or via REST, supplying
parameters:

| Parameter | Example | Meaning |
|-----------|---------|---------|
| `SiteUrl` | `https://contoso.sharepoint.com/sites/Eng` | The SharePoint site. |
| `LibraryName` | `Documents` | The document library. |
| `Mode` | `full` or `incremental` | `full` copies everything; `incremental` resumes from the saved Graph delta link. |

The pipeline refreshes the inventory, then runs the notebook to copy content into
`Files/<site>/<library>/…` in the Lakehouse.

**Initial load then ongoing sync:** run once with `Mode = full`, then schedule
`PL_Migrate_Master` with `Mode = incremental` (Fabric **Schedule** on the pipeline).
Each incremental run only transfers what changed since the last run.

---

## 6. Verify & monitor

**In the Lakehouse (OneLake):**
- `Files/<site>/<library>/…` — the migrated documents (browse in the Lakehouse explorer).
- `Tables/migration_audit` — one row per file: `name`, `size`, `status`
  (`copied` or `error: …`), `dest`, `ts_utc`.
- `Tables/migration_watermark` — the Graph delta link per `site::library`
  (the incremental resume point).
- `Tables/sharepoint_inventory` — the library listing from the connector.

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
| Inventory pipeline left as a skeleton | `sharePointConnectionId` blank. | Create the SharePoint connection (2c), set the GUID, re-deploy. |
| Notebook job fails immediately | Missing Graph permission or secret. | Confirm `Sites.Read.All`/`Files.Read.All` + admin consent, and that the Key Vault secret exists and the run identity has **Secrets User**. |
| `migration_audit` rows show `error: 403` | App lacks access to that site/library. | Grant the app access to the site collection (or use sites-selected consent). |
| Want to re-copy everything | Watermark already advanced. | Run with `Mode = full` (ignores the watermark). |

---

## 8. What is and isn't included

- **Included & validated end to end on a live Fabric workspace:** Lakehouse
  provisioning, notebook assembly + deploy, pipeline deploy with all references
  resolved, the master pipeline run, and the OneLake write path (files + Delta
  tables).
- **You provide (credential-bearing, can't be scripted blind):** the app
  registration + Graph consent, the Key Vault secret, and the Fabric SharePoint
  connection.
- **Scope note:** the inventory pipeline uses the SharePoint Online **list**
  connector for metadata; binary document **content** is moved by the Spark
  notebook (the connector alone does not move large binaries reliably).
