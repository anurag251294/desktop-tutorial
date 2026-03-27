# Hydro One SharePoint Migration - Changelog

All notable changes to this solution are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [2.0] - 2026-02-18 (Current - Production-Ready POC)

### End-to-End Validated

- Validated on **SalesAndMarketing** site: 30 files, 7.96 MB, 0 failures in ~2 min 5 sec
- All six SQL tables populated and verified
- Post-migration validation pipeline confirmed source/destination parity

### Added

- **PL_Incremental_Sync** pipeline with deltaLink persistence
  - Uses Graph delta query to detect new, modified, and deleted files
  - Stores deltaLink in SQL for subsequent runs
- **PL_Validation** pipeline for post-migration file count and size comparison
  - Compares source (Graph API) vs destination (ADLS) file counts and byte totals
  - Writes results to ValidationLog table
- **IncrementalWatermark** SQL table for storing deltaLinks and DriveIds
- **SyncLog** SQL table for incremental sync run tracking
- Configurable pipeline parameters:
  - `PageSize` — controls Graph API page size (default 200)
  - `CopyBatchCount` — number of files per PL_Copy_File_Batch invocation
  - `ThrottleDelaySeconds` — wait between batches to avoid Graph 429 errors
- Terraform configuration for private endpoints (7 `.tf` files)
  - Key Vault, SQL Server, Storage Account, ADF managed VNet
- Comprehensive documentation suite:
  - `architecture.md` — solution overview and data flow
  - `deployment-guide.md` — step-by-step provisioning
  - `runbook.md` — day-to-day operations
  - `migration-plan.md` — phased rollout strategy
  - `pipeline-documentation.md` — pipeline-by-pipeline reference

### Changed

- Replaced SharePoint REST API with Microsoft Graph API for all operations (ADR-1)
- Replaced recursive subfolder traversal with Graph delta query `/root/delta` (ADR-2)
- Extracted ForEach file copy into child pipeline **PL_Copy_File_Batch** (ADR-3)
- Replaced conditional token refresh with always-refresh-per-iteration pattern (ADR-4)
- Replaced `@microsoft.graph.downloadUrl` with Graph `/content` endpoint (ADR-5)
- Replaced IfCondition activities with flat `@if()` expressions in SetVariable (ADR-7)
- Until loop restructured to use only flat activities (no nested containers)
- Audit logging now captures `CopyStartTime`, `CopyEndTime`, and checksums

### Fixed

- **"Unsupported app only token"** — switched from SharePoint REST to Graph API
- **Doubled download URL** — switched from `@microsoft.graph.downloadUrl` to `/content` endpoint
- **ADF circular reference** — replaced self-referencing pipeline with delta query
- **Token expiration during long runs** — always-refresh pattern ensures fresh token each iteration
- **Container nesting errors in Until** — child pipeline pattern (PL_Copy_File_Batch)
- **Self-referencing SetVariable** — replaced `variables('SameVar')` with empty string fallback

### Architecture Decision Records

| ADR | Title                                      | Decision                                          |
|-----|--------------------------------------------|---------------------------------------------------|
| 1   | Graph API over SharePoint REST API         | AAD v2.0 tokens incompatible with SP REST         |
| 2   | Delta query over recursive traversal       | Eliminates depth limits and circular refs          |
| 3   | Child pipeline for ForEach in Until        | ADF prohibits container activities inside Until    |
| 4   | Always-refresh token pattern               | AAD caches server-side; cost is negligible         |
| 5   | /content endpoint over downloadUrl         | ADF HTTP connector doubles base URL with downloadUrl |
| 7   | Flat @if() over IfCondition activity       | IfCondition cannot nest inside Until               |

---

## [1.0] - 2026-02-17 (Initial POC)

### Added

- **PL_Master_Migration_Orchestrator** pipeline
  - Reads MigrationControl table, iterates libraries via ForEach
- **PL_Migrate_Single_Library** pipeline (SharePoint REST API based)
  - Paginated file listing with Until loop
- **PL_Process_Subfolder** pipeline (recursive subfolder traversal)
  - Processes subfolder children, paginated, calls PL_Copy_File_Batch
- **PL_Copy_File_Batch** pipeline (child pipeline workaround)
  - ForEach file copy with audit logging to MigrationAuditLog
- **MigrationControl** SQL table — library-level tracking
- **MigrationAuditLog** SQL table — file-level audit trail
- **BatchLog** SQL table — batch run tracking
- Scripts:
  - `Setup-AzureResources.ps1` — provisions Azure resources
  - `Register-SharePointApp.ps1` — creates AAD app registration
  - `Populate-ControlTable.ps1` — seeds MigrationControl from SharePoint
  - `Deploy-ADF-Templates.sh` — deploys ARM templates to ADF
  - `Monitor-Migration.ps1` — real-time pipeline monitoring
  - `Validate-Migration.ps1` — post-migration file count checks
- ARM templates for linked services, datasets, and pipelines
- Config files for dev (`config.dev.json`) and prod (`config.prod.json`) environments

### Known Issues (Resolved in 2.0)

- SharePoint REST API incompatible with AAD v2.0 app-only tokens
- ADF Until activity prohibits nested container activities (ForEach, IfCondition)
- Token expiration not handled for long-running libraries (>1 hour)
- No incremental sync capability — full migration only
- No post-migration validation pipeline
- Self-referencing variable issue in Until loop SetVariable activities

---

## Versioning Notes

- Version 1.0 was a proof-of-concept that surfaced ADF and SharePoint API constraints.
- Version 2.0 resolved all known issues and is validated for production use.
- Future versions will address multi-site parallelism and metadata preservation.
