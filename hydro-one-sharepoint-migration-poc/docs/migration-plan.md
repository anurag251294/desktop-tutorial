# Hydro One SharePoint Migration - Phased Migration Plan

## Project Overview

| Attribute | Value |
|-----------|-------|
| Client | Hydro One |
| Data Volume | ~25 TB |
| Source | SharePoint Online |
| Destination | Azure Data Lake Storage Gen2 |
| Urgency | High (SharePoint storage at capacity) |
| Timeline | 10 weeks |

---

## Technical Approach

### API Strategy: Microsoft Graph API

The migration uses **Microsoft Graph API** (not SharePoint REST API) for all SharePoint Online interactions. This decision was validated during the POC phase after discovering that the SharePoint REST API is incompatible with Azure AD v2.0 app-only (client credentials) tokens. The Graph API provides full support for the OAuth 2.0 client credentials flow with AAD v2.0 endpoints.

**Graph API endpoints used:**

| Operation | Graph API Endpoint |
|-----------|-------------------|
| Resolve site to drive | `GET /v1.0/sites/{host}:/{sitePath}:/drives` |
| Enumerate root items | `GET /v1.0/drives/{driveId}/root/children` |
| Enumerate subfolder items | `GET /v1.0/drives/{driveId}/items/{itemId}/children` |
| Download file content | `GET /v1.0/drives/{driveId}/items/{itemId}/content` (302 redirect to pre-authenticated download URL) |
| Pagination | `@odata.nextLink` for large result sets |
| Delta query (all files, all depths) | `GET /v1.0/drives/{driveId}/root/delta?$top=200` |
| Delta link (incremental) | `@odata.deltaLink` stored in SQL for true incremental sync |

**Authentication flow:**
1. Service Principal client secret retrieved from Azure Key Vault (via Managed Identity)
2. OAuth 2.0 client credentials token acquired from `https://login.microsoftonline.com/{tenantId}/oauth2/v2.0/token` with scope `https://graph.microsoft.com/.default`
3. Bearer token used in all Graph API calls

### ADF Pipeline Architecture

The migration is orchestrated through Azure Data Factory with the following pipelines:

| # | Pipeline | Purpose |
|---|----------|---------|
| 1 | `PL_Master_Migration_Orchestrator` | Reads from control table, iterates through libraries in batches |
| 2 | `PL_Migrate_Single_Library` | Delta query enumeration with paginated Until loop, calls `PL_Copy_File_Batch` for file copy + audit logging |
| 3 | `PL_Copy_File_Batch` | Child pipeline with ForEach file copy + audit logging (workaround for ADF Until activity restriction — see ADF Limitations below) |
| 4 | `PL_Process_Subfolder` | Processes subfolder children with pagination, calls `PL_Copy_File_Batch` for file copy + audit logging |
| 5 | `PL_Incremental_Sync` | Delta sync with deltaLink persistence, calls `PL_Copy_File_Batch` for file copy + audit logging |
| 6 | `PL_Post_Migration_Validation` | Post-migration validation comparing source file counts/sizes vs destination |

**Deployment order:** `PL_Copy_File_Batch` must be deployed before its parent pipelines (`PL_Migrate_Single_Library`, `PL_Process_Subfolder`, `PL_Incremental_Sync`), since they reference it via ExecutePipeline. Recommended deployment sequence:

1. `PL_Copy_File_Batch` (child — no dependencies)
2. `PL_Process_Subfolder` (depends on `PL_Copy_File_Batch`)
3. `PL_Migrate_Single_Library` (depends on `PL_Copy_File_Batch` and `PL_Process_Subfolder`)
4. `PL_Incremental_Sync` (depends on `PL_Copy_File_Batch`)
5. `PL_Post_Migration_Validation` (standalone)
6. `PL_Master_Migration_Orchestrator` (depends on `PL_Migrate_Single_Library`)

**Token management:** Token is refreshed every Until iteration via WebActivity call to the AAD token endpoint. AAD returns a cached token if still valid, adding only ~500ms overhead per iteration. This always-refresh approach eliminates the need for IfCondition-based expiry checks inside Until loops (which ADF does not permit).

### ADF Limitations Discovered During Implementation

During POC development, several Azure Data Factory activity nesting restrictions were discovered that shaped the pipeline architecture:

| Limitation | Description |
|------------|-------------|
| **Until cannot contain ForEach** | The Until activity only permits ExecutePipeline as a child activity; ForEach, IfCondition, and Switch are not allowed inside Until |
| **IfCondition cannot contain ForEach** | ForEach is not permitted as a child activity inside IfCondition branches |
| **SetVariable cannot self-reference** | A SetVariable activity cannot reference the same variable it is setting (e.g., appending to an array or incrementing a counter requires a separate variable) |

**Solution: Child pipeline pattern + flat SetVariable with `@if()` expressions**

To work around these restrictions, file copy and audit logging logic was extracted into a dedicated child pipeline (`PL_Copy_File_Batch`). Parent pipelines (`PL_Migrate_Single_Library`, `PL_Process_Subfolder`, `PL_Incremental_Sync`) call `PL_Copy_File_Batch` via ExecutePipeline inside their Until pagination loops. Conditional logic that would otherwise require IfCondition is handled with flat `SetVariable` activities using `@if()` expressions inline.

### Prerequisites

| Requirement | Details |
|-------------|---------|
| Azure AD App Registration | Service Principal with client secret stored in Key Vault |
| **Graph API Permissions (Application)** | **`Sites.Read.All`**, **`Files.Read.All`** (admin-consented) |
| Azure Data Factory | With System-Assigned Managed Identity enabled |
| ADLS Gen2 Storage Account | Managed Identity granted Storage Blob Data Contributor |
| Azure SQL Database | Managed Identity granted db_datareader, db_datawriter; control tables deployed |
| Azure Key Vault | Managed Identity granted Key Vault Secrets User; client secret stored |

> **Note:** SharePoint-specific permissions (e.g., `Sites.FullControl.All` via SharePoint admin) are **not** required. The Graph API application permissions (`Sites.Read.All`, `Files.Read.All`) granted through Azure AD are sufficient for read-only migration.

---

## Phased Approach

### Phase 1: POC Validation (Week 1) -- COMPLETED

**Objective:** Validate migration approach with 1-2 small libraries

**Status:** Successfully completed on **February 17, 2026** using the **SalesAndMarketing** site (`/sites/SalesAndMarketing` / `Shared Documents` library) on the dev/test tenant (`m365x52073746.sharepoint.com`).

**Key POC findings:**
- Microsoft Graph API validated as the correct approach for app-only (client credentials) access to SharePoint Online content
- SharePoint REST API was initially attempted but found to be incompatible with AAD v2.0 app-only tokens; Graph API resolved this
- ADF pipelines successfully enumerate folders, download files via Graph pre-authenticated URLs, and write to ADLS Gen2
- Folder structure is preserved in the destination container
- ADF does not support recursive pipeline execution; subfolder processing uses iterative patterns within `PL_Process_Subfolder`
- Production readiness improvements implemented: delta-based file enumeration (unlimited depth), pagination via Until loops, always-refresh token strategy (AAD caches valid tokens, ~500ms overhead per iteration), child pipeline pattern (`PL_Copy_File_Batch`), configurable throttle delays, and deltaLink persistence for true incremental sync

| Task | Owner | Duration | Deliverable | Status |
|------|-------|----------|-------------|--------|
| Deploy Azure resources (dev) | Microsoft | 1 day | Resource group deployed | Done |
| Register Azure AD app | Microsoft | 0.5 day | App with Graph API permissions, admin consent | Done |
| Deploy ADF pipelines (6 pipelines) | Microsoft | 1 day | Pipelines deployed (Graph API based, child pipeline pattern) | Done |
| Initialize control database | Microsoft | 0.5 day | Tables created | Done |
| Enumerate test library via Graph API | Microsoft | 0.5 day | Control table populated (SalesAndMarketing) | Done |
| Run POC migration | Microsoft | 1 day | Files migrated to ADLS | Done |
| Validate POC results | Microsoft/Hydro One | 1 day | Validation report | Done |
| POC sign-off | Hydro One | 0.5 day | Approval to proceed | Pending |

**Success Criteria:**
- [x] All files from SalesAndMarketing library migrated successfully
- [x] File count matches 100%
- [x] Files are accessible in ADLS
- [x] Folder structure preserved
- [x] No errors in audit log

**Exit Criteria:**
- [ ] POC sign-off obtained
- [x] Issues documented and resolved (Graph API pivot documented)
- [x] Production features implemented (pagination, always-refresh token, child pipeline pattern, deep folders, deltaLink)
- [ ] Go/No-Go decision for Phase 2

---

### Phase 2: Pilot Migration (Week 2-3)

**Objective:** Migrate ~1 TB across multiple libraries to validate at scale

| Task | Owner | Duration | Deliverable |
|------|-------|----------|-------------|
| Enumerate all pilot libraries | Microsoft | 1 day | Full inventory |
| Configure production parameters | Microsoft | 0.5 day | Optimized settings |
| Execute pilot migration (batch 1) | Microsoft | 2 days | 500 GB migrated |
| Monitor and tune | Microsoft | Ongoing | Performance metrics |
| Execute pilot migration (batch 2) | Microsoft | 2 days | 500 GB migrated |
| Validate pilot results | Microsoft/Hydro One | 2 days | Validation report |
| Document lessons learned | Microsoft | 1 day | Lessons learned doc |
| Pilot sign-off | Hydro One | 0.5 day | Approval for bulk |

**Pilot Scope:**
- 10-20 document libraries
- Mix of sizes (small, medium, large)
- Mix of file types (documents, images, etc.)
- Total: ~1 TB

**Success Criteria:**
- [ ] 1 TB migrated successfully
- [ ] <5% failed files (all recoverable)
- [ ] Throughput >50 GB/day achieved
- [ ] Throttling managed effectively
- [ ] No data loss
- [ ] Pagination verified (Until loop with PageSize=3 runs multiple iterations)
- [ ] Deep folder files (depth >2) migrated with correct ADLS paths
- [ ] Token refresh verified (always-refresh via WebActivity every Until iteration, AAD caches valid tokens)
- [ ] DeltaLink stored in IncrementalWatermark after initial migration
- [ ] Incremental sync uses stored DeltaLink (only changed files copied)

---

### Phase 3: Bulk Migration (Week 4-8)

**Objective:** Migrate remaining 24 TB in batches of 2-5 TB

#### Week 4-5: Batch 1 (5 TB)
| Day | Activity | Volume |
|-----|----------|--------|
| Mon-Tue | Migrate small libraries (<100 MB) | 0.5 TB |
| Wed-Thu | Migrate medium libraries (100 MB - 1 GB) | 1.5 TB |
| Fri-Sun | Migrate large libraries (1-10 GB) | 3 TB |

#### Week 5-6: Batch 2 (5 TB)
| Day | Activity | Volume |
|-----|----------|--------|
| Mon-Tue | Migrate remaining medium libraries | 2 TB |
| Wed-Sun | Migrate large libraries | 3 TB |

#### Week 6-7: Batch 3 (7 TB)
| Day | Activity | Volume |
|-----|----------|--------|
| Mon-Sun | Migrate largest libraries (>10 GB) | 7 TB |

#### Week 7-8: Batch 4 (7 TB)
| Day | Activity | Volume |
|-----|----------|--------|
| Mon-Sun | Migrate remaining libraries | 7 TB |
| Thu-Fri | Retry failed items | Variable |
| Weekend | Final cleanup | Variable |

**Daily Schedule (Bulk Migration):**
| Time (EST) | Activity |
|------------|----------|
| 8:00 PM | Start evening batch |
| 8:00 AM | Review overnight results |
| 9:00 AM | Address failures |
| 5:00 PM | Prepare next batch |
| 8:00 PM | Start next batch |

**Weekly Checkpoints:**
- Monday: Review weekend progress
- Wednesday: Mid-week status meeting
- Friday: Weekly status report

---

### Phase 4: Validation & Cutover (Week 9-10)

**Objective:** Validate all migrated data and transition to production state

#### Week 9: Validation
| Task | Owner | Duration | Deliverable |
|------|-------|----------|-------------|
| Run validation pipeline | Microsoft | 1 day | Validation results |
| Address discrepancies | Microsoft | 2 days | Issues resolved |
| Verify production features (pagination, deep folders, deltaLink, always-refresh token, child pipeline pattern) | Microsoft | 1 day | Production test checklist |
| Generate final report | Microsoft | 1 day | Migration report |
| Business validation | Hydro One | 2 days | Business sign-off |

#### Week 10: Cutover
| Task | Owner | Duration | Deliverable |
|------|-------|----------|-------------|
| Enable incremental sync | Microsoft | 0.5 day | Sync running |
| Update documentation | Microsoft | 1 day | Updated runbook |
| Knowledge transfer | Microsoft | 2 days | Training complete |
| Handoff to sustainment | Microsoft/Hydro One | 1 day | Handoff complete |
| Final sign-off | Hydro One | 0.5 day | Project closure |

---

### Phase 5: Incremental Sync & Monitoring (Ongoing)

**Objective:** Maintain synchronization and monitor for issues

| Activity | Frequency | Owner |
|----------|-----------|-------|
| Incremental sync | Daily (2 AM EST) | Automated |
| Monitor sync results | Daily | Hydro One |
| Weekly health check | Weekly | Hydro One |
| Monthly reporting | Monthly | Hydro One |
| Quarterly review | Quarterly | Microsoft/Hydro One |

---

## Risk Register

| ID | Risk | Likelihood | Impact | Mitigation | Status | Owner |
|----|------|------------|--------|------------|--------|-------|
| R1 | SharePoint throttling delays migration | High | Medium | Off-peak scheduling, Microsoft engagement | Open | Microsoft |
| R2 | Large files (>10 GB) fail to migrate | Medium | Low | Individual handling, increased timeout | Open | Microsoft |
| R3 | API permissions revoked during migration | Low | High | Regular monitoring, backup credentials | Open | Microsoft |
| R4 | SharePoint service outage | Low | High | Built-in retry, pause capability | Open | N/A |
| R5 | Data corruption during transfer | Low | High | Checksum validation, source unchanged | Open | Microsoft |
| R6 | ADLS storage capacity exceeded | Low | Medium | Capacity monitoring, alerts | Open | Microsoft |
| R7 | Key personnel unavailable | Medium | Medium | Cross-training, documentation | Open | Both |
| R8 | Business content changes during migration | Medium | Low | Incremental sync, re-migration capability | Open | Microsoft |
| R9 | Network bandwidth insufficient | Low | Medium | Off-peak scheduling, bandwidth monitoring | Open | Hydro One |
| R10 | Regulatory/compliance issues | Low | High | Early legal review, audit logging | Open | Hydro One |
| R11 | SharePoint REST API incompatible with AAD v2.0 app-only tokens | High | High | Switched to Microsoft Graph API for all file enumeration and downloads. Graph API fully supports client credentials flow with AAD v2.0 endpoints. | **Resolved** (POC) | Microsoft |
| R12 | ADF does not support recursive pipeline execution | Medium | Medium | Replaced subfolder-based enumeration with Graph API delta query (`/root/delta`), which returns ALL files at ALL folder depths in a flat list. No recursive traversal needed. `PL_Process_Subfolder` retained as standalone utility with pagination support. | **Resolved** (Production) | Microsoft |
| R13 | Token expiration during long-running migrations | Medium | High | Token refreshed every Until iteration via WebActivity. AAD returns cached token if still valid (~500ms overhead per iteration). Eliminates the need for IfCondition inside Until loops, avoiding ADF container activity restrictions. | **Resolved** (Production) | Microsoft |
| R14 | ADF Until activity cannot contain ForEach, IfCondition, or Switch | High | High | Extracted file copy + audit logging into child pipeline (`PL_Copy_File_Batch`). Parent pipelines call it via ExecutePipeline inside Until loops. Conditional logic uses flat SetVariable with `@if()` expressions. | **Resolved** (Production) | Microsoft |

### Risk Response Plan

**R1 - SharePoint Throttling:**
- Primary: Run migrations during off-peak hours (8 PM - 6 AM EST)
- Secondary: Request throttling limit increase from Microsoft
- Tertiary: Reduce parallelism and extend timeline

**R5 - Data Corruption:**
- Primary: File count and size validation post-migration
- Secondary: Checksum validation for sampled files
- Tertiary: Re-migrate from source (data unchanged)

**R11 - SharePoint REST API Incompatibility (RESOLVED):**
- **Root Cause:** The SharePoint REST API (`/_api/web/...`) does not accept access tokens acquired via the AAD v2.0 client credentials flow (`/oauth2/v2.0/token` with `client_credentials` grant). SharePoint REST API requires either legacy SharePoint App-Only tokens or AAD v1.0 tokens, which are not compatible with modern app registrations using application permissions.
- **Resolution:** Switched all file enumeration and download operations to Microsoft Graph API (`https://graph.microsoft.com/v1.0/...`). Graph API natively supports AAD v2.0 app-only tokens and provides equivalent functionality for listing drive items, navigating folder hierarchies, and downloading file content via pre-authenticated URLs.
- **Impact:** No functional loss. Graph API provides the same capabilities with better alignment to modern authentication patterns. Required application permissions changed from SharePoint-specific to `Sites.Read.All` and `Files.Read.All` (Microsoft Graph).

**R12 - ADF Recursive Pipeline Limitation (RESOLVED):**
- **Root Cause:** Azure Data Factory does not allow a pipeline to call itself recursively via Execute Pipeline activity.
- **Resolution:** Replaced subfolder-based enumeration with Graph API delta query (`/root/delta`), which returns ALL files at ALL folder depths in a flat list. No recursive traversal needed. `PL_Process_Subfolder` retained as standalone utility with pagination support.
- **Impact:** No folder depth limitation. Delta query eliminates the need for recursive or iterative folder traversal entirely.

**R13 - Token Expiration During Long-Running Migrations (RESOLVED):**
- **Root Cause:** AAD OAuth2 access tokens have an approximate 60-minute lifetime. Long-running migrations processing large libraries can exceed this duration.
- **Resolution:** Adopted an always-refresh approach: token is refreshed every Until iteration via WebActivity. AAD returns a cached token if still valid, adding only ~500ms overhead per iteration. This eliminates the need for IfCondition-based token expiry checks inside Until loops, avoiding ADF container activity restrictions entirely.
- **Impact:** Large libraries with thousands of files can be processed without token-related failures. No conditional logic needed inside Until loops.

**R14 - ADF Until Activity Container Restrictions (RESOLVED):**
- **Root Cause:** Azure Data Factory's Until activity only permits ExecutePipeline as a child activity. ForEach, IfCondition, and Switch activities are not allowed inside Until. Additionally, IfCondition cannot contain ForEach, and SetVariable cannot self-reference the variable being set.
- **Resolution:** Extracted file copy and audit logging into a dedicated child pipeline (`PL_Copy_File_Batch`). Parent pipelines call it via ExecutePipeline inside Until pagination loops. Conditional logic uses flat SetVariable activities with `@if()` expressions instead of IfCondition blocks.
- **Impact:** All pagination loops work within ADF constraints. The child pipeline pattern provides clean separation of concerns and reusability across `PL_Migrate_Single_Library`, `PL_Process_Subfolder`, and `PL_Incremental_Sync`.

---

## RACI Matrix

| Activity | Hydro One IT | Hydro One Business | Microsoft | Microsoft |
|----------|-------------|-------------------|-----|-----------|
| Azure subscription setup | A/R | I | C | - |
| SharePoint admin consent | A/R | I | C | - |
| ADF deployment | A | I | R | - |
| Migration execution | A | I | R | - |
| Monitoring | A | I | R | - |
| Business validation | I | A/R | C | - |
| Throttling escalation | I | I | R | A |
| Knowledge transfer | A/R | I | R | - |
| Ongoing maintenance | R | I | C | - |

**Legend:** R = Responsible, A = Accountable, C = Consulted, I = Informed

---

## Resource Requirements

### Microsoft Team
| Role | FTE | Duration |
|------|-----|----------|
| Azure Data Engineer (Lead) | 1 | 10 weeks |
| Azure Data Engineer | 1 | 8 weeks |
| Project Manager | 0.5 | 10 weeks |

### Hydro One Team
| Role | FTE | Duration |
|------|-----|----------|
| SharePoint Administrator | 0.25 | 10 weeks |
| IT Project Manager | 0.5 | 10 weeks |
| Business Stakeholder | 0.1 | 2 weeks |

### Azure Resources
| Resource | Specification | Monthly Cost (Est.) |
|----------|---------------|---------------------|
| ADLS Gen2 | 30 TB, Hot tier | $600 |
| Azure Data Factory | Pay-as-you-go | $100-200 |
| Azure SQL | S1 Standard | $30 |
| Key Vault | Standard | $5 |
| **Total** | | **~$800-850/month** |

---

## Timeline Summary

```
Week 1  |████████| Phase 1: POC Validation          *** COMPLETED 2026-02-17 ***
Week 2  |████████| Phase 2: Pilot Migration (1 TB)
Week 3  |████████| Phase 2: Pilot Migration (continued)
Week 4  |████████| Phase 3: Bulk Migration - Batch 1 (5 TB)
Week 5  |████████| Phase 3: Bulk Migration - Batch 2 (5 TB)
Week 6  |████████| Phase 3: Bulk Migration - Batch 3 (7 TB)
Week 7  |████████| Phase 3: Bulk Migration - Batch 4 (7 TB)
Week 8  |████████| Phase 3: Bulk Migration - Cleanup
Week 9  |████████| Phase 4: Validation
Week 10 |████████| Phase 4: Cutover & Handoff
```

---

## Key Milestones

| Milestone | Target Date | Status |
|-----------|-------------|--------|
| M1: POC Complete | Week 1 | **Complete (2026-02-17)** |
| M2: Pilot Complete (1 TB) | Week 3 | Pending |
| M3: 50% Migration Complete (12.5 TB) | Week 6 | Pending |
| M4: Bulk Migration Complete (25 TB) | Week 8 | Pending |
| M5: Validation Complete | Week 9 | Pending |
| M6: Project Handoff | Week 10 | Pending |

---

## Assumptions

1. SharePoint Online service remains available during migration window
2. Network bandwidth is sufficient for estimated throughput
3. Microsoft will provide throttling relief if requested
4. Business stakeholders available for validation during Week 9
5. No major changes to source content during migration
6. Azure subscription has sufficient quota
7. Microsoft Graph API permissions (`Sites.Read.All`, `Files.Read.All`) remain consented throughout migration

## Dependencies

1. Azure AD app registration requires Global Administrator (or Application Administrator with admin consent workflow)
2. Graph API application permissions (`Sites.Read.All`, `Files.Read.All`) require admin consent before migration
3. Microsoft TAM engagement for throttling limit increase
4. Hydro One IT approval for Azure resource deployment
5. Business owner sign-off required at each phase

---

## Communication Plan

| Meeting | Frequency | Attendees | Purpose |
|---------|-----------|-----------|---------|
| Daily Standup | Daily | Microsoft Team | Progress updates |
| Status Meeting | Weekly | Microsoft, Hydro One IT | Weekly progress |
| Steering Committee | Bi-weekly | All stakeholders | Executive updates |
| Issue Escalation | As needed | Relevant parties | Issue resolution |

### Status Report Template

```
HYDRO ONE SHAREPOINT MIGRATION - WEEKLY STATUS REPORT
Week: [X] of 10
Date: [YYYY-MM-DD]

SUMMARY:
[1-2 sentence summary]

PROGRESS:
- Libraries Completed: XX / XXX (XX%)
- Data Migrated: XX TB / 25 TB (XX%)
- Files Migrated: XXX,XXX

THIS WEEK:
- [Accomplishment 1]
- [Accomplishment 2]

NEXT WEEK:
- [Plan 1]
- [Plan 2]

RISKS/ISSUES:
- [Risk/Issue and status]

DECISIONS NEEDED:
- [Decision required]
```

---

## Appendix: Detailed Week-by-Week Plan

### Week 1 - POC Validation (COMPLETED 2026-02-17)

| Day | Task | Hours | Owner | Status |
|-----|------|-------|-------|--------|
| Mon | Deploy Azure resources | 4 | Microsoft | Done |
| Mon | Register Azure AD app (Graph API permissions) | 2 | Microsoft | Done |
| Tue | Deploy ADF pipelines (Graph API based; deploy `PL_Copy_File_Batch` first, then parent pipelines) | 6 | Microsoft | Done |
| Wed | Initialize SQL database | 2 | Microsoft | Done |
| Wed | Enumerate SalesAndMarketing library via Graph API | 2 | Microsoft | Done |
| Wed | Run POC migration | 4 | Microsoft | Done |
| Thu | Monitor and troubleshoot | 6 | Microsoft | Done |
| Fri | Validate results | 4 | Microsoft | Done |
| Fri | POC sign-off meeting | 2 | All | Pending |

**POC Notes:**
- Target site: `/sites/SalesAndMarketing` (Shared Documents library)
- Tenant: `m365x52073746.sharepoint.com` (dev/test)
- Key pivot: Switched from SharePoint REST API to Microsoft Graph API due to AAD v2.0 token incompatibility
- All file enumeration uses Graph drives/items endpoints; downloads use Graph `/content` endpoint (302 redirect to pre-authenticated URL)
- Child pipeline pattern (`PL_Copy_File_Batch`) adopted to work around ADF Until activity nesting restrictions
- Token refresh: always-refresh every Until iteration (AAD caches valid tokens, ~500ms overhead)

### Week 2-3 - Pilot Migration

*Detailed task breakdown similar to Week 1...*

### Week 4-8 - Bulk Migration

*Migration batches scheduled by library size and priority...*
