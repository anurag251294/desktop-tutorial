# Hydro One SharePoint Migration - Architecture Decision Records

## Overview

Architecture Decision Records (ADRs) capture the key technical decisions made during the
design and implementation of the Hydro One SharePoint Online to ADLS Gen2 migration solution.
Each record documents the context, the decision itself, the alternatives that were evaluated,
and the consequences — both positive and negative.

These records serve several purposes:

- **Institutional memory**: Future team members can understand *why* things were built a
  certain way, not just *how*.
- **Audit trail**: Decisions are traceable to specific constraints discovered during the POC.
- **Reuse**: Many of these patterns (especially the ADF workarounds) apply to any Graph API
  migration built on Azure Data Factory.

All decisions below were validated during the February 2026 proof-of-concept phase against
the M365 developer tenant (`m365x52073746.sharepoint.com`) and the MCAPS Azure subscription.

---

## ADR-1: Microsoft Graph API over SharePoint REST API

- **Date**: February 2026
- **Status**: Accepted
- **Context**: The migration solution requires app-only (client credentials) access to
  SharePoint Online document libraries. No interactive user sign-in is possible because
  ADF pipelines run unattended. The initial implementation attempted to use the SharePoint
  REST API (`/_api/web/lists`) with an AAD v2.0 client-credentials token.
- **Decision**: Use the Microsoft Graph API (`https://graph.microsoft.com/v1.0/`) for all
  SharePoint file enumeration and download operations.
- **Alternatives Considered**:
  - **SharePoint REST API** (`/_api/`): Rejected. SharePoint REST endpoints return
    "Unsupported app only token" when presented with an AAD v2.0 client-credentials token.
    The legacy AAD v1.0 endpoint is deprecated and not recommended for new development.
  - **SharePoint CSOM (.NET client library)**: Rejected. Requires a .NET runtime, which
    adds deployment complexity inside ADF. Also affected by the same token-format issue.
  - **Third-party migration tools (ShareGate, AvePoint)**: Rejected for the POC phase due
    to licensing cost and procurement timelines. May be revisited for production if ADF
    throughput proves insufficient.
- **Consequences**:
  - *Positive*: Graph API works seamlessly with AAD v2.0 app-only tokens. Single consistent
    API surface for files, permissions, and delta queries.
  - *Positive*: Graph delta endpoint eliminates the need for recursive folder traversal.
  - *Negative*: Graph API has throttling limits (per-app, per-tenant). Must implement retry
    logic and respect `Retry-After` headers.
  - *Negative*: Some SharePoint-specific metadata (e.g., custom columns, content type IDs)
    requires additional `$expand` or `$select` calls through Graph.
- **Validation**: POC successfully enumerated and downloaded files from three document
  libraries using Graph API with client-credentials tokens acquired against the SharePoint
  tenant's AAD endpoint (`https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`
  with scope `https://graph.microsoft.com/.default`).

---

## ADR-2: Delta Query for File Enumeration

- **Date**: February 2026
- **Status**: Accepted
- **Context**: SharePoint document libraries can contain deeply nested folder structures.
  Enumerating all files requires either recursive `/children` calls at each folder level
  or a mechanism that returns the full tree in a flat list. The initial pipeline design
  used `PL_Process_Subfolder` to recursively traverse subfolders, but this added complexity
  and required multiple pipeline invocations per depth level.
- **Decision**: Use the Graph delta endpoint (`/v1.0/drives/{driveId}/root/delta`) as the
  primary file enumeration mechanism. Delta returns all items at all folder depths in a
  single paginated response.
- **Alternatives Considered**:
  - **Recursive `/children` traversal via PL_Process_Subfolder**: Rejected as primary
    approach. Requires one pipeline execution per folder, scales poorly with deep nesting,
    and does not support incremental sync.
  - **SharePoint Search API**: Rejected. Search indexes are eventually consistent (up to
    15-minute delay), which could cause files to be missed during migration.
- **Consequences**:
  - *Positive*: Single API call (paginated) returns every file regardless of folder depth.
  - *Positive*: The `@odata.deltaLink` returned after a full enumeration enables incremental
    sync — subsequent calls return only changed/added/deleted items.
  - *Positive*: Eliminates the recursive pipeline pattern entirely for initial migration.
  - *Negative*: Delta responses include folders as well as files; pipeline must filter on
    `file` facet to skip folder entries.
  - *Negative*: Delta responses can be very large for libraries with millions of items;
    pagination handling in the Until loop is essential.
- **Validation**: POC confirmed that `/root/delta` returns files from all subfolder depths.
  The `deltaLink` was persisted to SQL and successfully used by `PL_Incremental_Sync` to
  detect newly added files without re-scanning the entire library.

---

## ADR-3: Child Pipeline Pattern (PL_Copy_File_Batch)

- **Date**: February 2026
- **Status**: Accepted
- **Context**: The migration pipeline uses an Until loop to handle paginated Graph API
  responses. Inside each iteration, the pipeline needs to iterate over the returned files
  (ForEach) and copy each one. However, ADF imposes a strict constraint: Until loops cannot
  contain ForEach, IfCondition, or Switch activities as direct children.
- **Decision**: Extract the ForEach file-copy logic into a separate child pipeline
  (`PL_Copy_File_Batch`) and invoke it from the Until loop via an ExecutePipeline activity.
- **Alternatives Considered**:
  - **Flatten everything into the Until loop**: Rejected. ADF validation explicitly blocks
    ForEach inside Until with a "container activities not allowed" error.
  - **Use a Data Flow instead of pipeline activities**: Rejected. Data Flows are optimized
    for structured data transformations, not individual file copy operations with per-file
    error handling and audit logging.
- **Consequences**:
  - *Positive*: Cleanly separates pagination logic (Until) from file processing logic
    (ForEach), improving readability and testability.
  - *Positive*: `PL_Copy_File_Batch` can be tested independently with a hardcoded file list.
  - *Negative*: Adds one additional pipeline invocation per page of results, introducing
    minor overhead (~2-3 seconds per ExecutePipeline call).
  - *Negative*: Debugging requires navigating parent and child pipeline runs in ADF Monitor.
- **Validation**: POC successfully processed paginated delta responses with 50+ files per
  page. The child pipeline pattern executed without errors across multiple pagination cycles.

---

## ADR-4: Always-Refresh Token Strategy

- **Date**: February 2026
- **Status**: Accepted
- **Context**: Long-running migrations can process hundreds of thousands of files over many
  hours. OAuth tokens issued by AAD have a default lifetime of 60 minutes. The pipeline
  needs a strategy to ensure valid tokens are always available. The natural approach — check
  token age with an IfCondition and refresh only when needed — is blocked by ADF's
  restriction on IfCondition inside Until loops.
- **Decision**: Refresh the access token on every Until loop iteration by calling the AAD
  token endpoint via a WebActivity at the top of each loop cycle.
- **Alternatives Considered**:
  - **Conditional refresh with IfCondition**: Rejected. IfCondition is a container activity
    and cannot be placed inside Until.
  - **Refresh every N iterations via a counter variable**: Considered but rejected for
    simplicity. Would require additional counter logic and still risks edge cases where
    the token expires between refreshes.
- **Consequences**:
  - *Positive*: Token is always fresh. Eliminates any possibility of mid-migration auth
    failures due to expiration.
  - *Positive*: Simple implementation — one WebActivity, no conditional logic needed.
  - *Negative*: Adds ~500ms of overhead per loop iteration for the token request.
  - *Negative*: Generates higher request volume against AAD token endpoint (acceptable
    within AAD's rate limits for a single application).
- **Validation**: POC confirmed that AAD caches tokens server-side and returns them in
  approximately 400-600ms. Over a 2-hour test run, no token expiration errors occurred.

---

## ADR-5: Graph /content Endpoint over @microsoft.graph.downloadUrl

- **Date**: February 2026
- **Status**: Accepted
- **Context**: When downloading files from SharePoint via Graph API, there are two common
  approaches: (1) use the `@microsoft.graph.downloadUrl` property returned in the driveItem
  metadata, which is a pre-authenticated, short-lived URL; or (2) call the `/content`
  endpoint directly with a Bearer token. The initial implementation used `downloadUrl`, but
  ADF's HTTP connector exhibited a bug where it doubled the base URL.
- **Decision**: Use `GET /v1.0/drives/{driveId}/items/{itemId}/content` with the Bearer
  token passed in `additionalHeaders` of the Copy activity's HTTP source.
- **Alternatives Considered**:
  - **@microsoft.graph.downloadUrl**: Rejected. ADF's HTTP connector prepends its configured
    base URL to the `downloadUrl`, resulting in a malformed URL like
    `https://graph.microsoft.com/https://...sharepoint.com/...`. No workaround was found
    within ADF's HTTP linked service configuration.
- **Consequences**:
  - *Positive*: Reliable file downloads with consistent URL construction.
  - *Positive*: Uses the same Bearer token already obtained for enumeration — no additional
    auth flow needed.
  - *Negative*: The `/content` endpoint returns a 302 redirect to the actual download URL.
    ADF's HTTP connector follows redirects automatically, so this is transparent but adds
    one extra hop of latency per file.
  - *Negative*: Requires the token to have `Files.Read.All` permission (already granted).
- **Validation**: POC successfully downloaded files of various types (DOCX, XLSX, PDF, PNG,
  ZIP) ranging from 1 KB to 250 MB using the `/content` endpoint pattern.

---

## ADR-6: Cross-Tenant Service Principal Model

- **Date**: February 2026
- **Status**: Accepted
- **Context**: The ADF instance runs in the MCAPS (Microsoft) Azure tenant
  (`fe64e912-...`), but the SharePoint Online environment belongs to Hydro One's tenant
  (`5447cfcd-...` in POC). The service principal must authenticate against the SharePoint
  tenant's AAD to obtain tokens with SharePoint permissions.
- **Decision**: Register the application in the SharePoint (Hydro One) tenant, grant it
  `Sites.Read.All` and `Files.Read.All` (Application type) with admin consent, and store
  the client secret in the MCAPS tenant's Azure Key Vault (`kv-hydroone-test2`).
- **Alternatives Considered**:
  - **Multi-tenant app registration**: Rejected. Adds unnecessary complexity (consent
    framework, redirect URIs) for a backend service that only needs access to one tenant.
  - **Azure B2B (guest accounts)**: Rejected. B2B is designed for user-level access, not
    service principal scenarios.
- **Consequences**:
  - *Positive*: Clean separation — the app registration lives where the data lives
    (SharePoint tenant), and the orchestration engine (ADF) only needs the client ID and
    secret.
  - *Positive*: Secret rotation is simple — generate a new secret in the SP tenant, update
    Key Vault in the MCAPS tenant, no pipeline changes required.
  - *Negative*: Requires coordination between two tenant administrators for initial setup
    and secret rotation.
  - *Negative*: If the Hydro One tenant enforces Conditional Access policies on service
    principals, additional configuration may be needed.
- **Validation**: POC acquired tokens from the SharePoint tenant's AAD endpoint using
  client credentials stored in MCAPS Key Vault. ADF's Key Vault linked service retrieved
  the secret at runtime without issues.

---

## ADR-7: Conditional @if() Expressions over IfCondition Activity

- **Date**: February 2026
- **Status**: Accepted
- **Context**: Several points in the pipeline logic require conditional behavior inside
  Until loops — for example, determining whether to continue pagination or exit the loop,
  and constructing the next page URL. The IfCondition activity is the standard ADF approach
  for branching, but it is classified as a container activity and is prohibited inside Until.
- **Decision**: Replace all IfCondition activities inside Until loops with flat SetVariable
  activities using `@if()` expression functions. The `@if(condition, trueValue, falseValue)`
  function evaluates inline and does not require a container activity.
- **Alternatives Considered**:
  - **IfCondition activity**: Rejected. ADF validation blocks it inside Until with a
    "container activities not allowed inside Until" error.
  - **Switch activity**: Rejected. Also a container activity, same restriction applies.
- **Consequences**:
  - *Positive*: All conditional logic fits within flat SetVariable activities, which are
    permitted inside Until loops.
  - *Positive*: Reduces activity count — one SetVariable replaces an IfCondition with two
    child branches.
  - *Negative*: Complex conditional logic becomes harder to read in `@if()` expressions
    compared to the visual IfCondition branches.
  - *Negative*: Cannot execute different *activities* conditionally — only variable values
    can be set conditionally. For truly different activity paths, ExecutePipeline to a child
    pipeline is required.
- **Validation**: POC used `@if()` expressions for pagination control (`HasMorePages`
  variable) and next-page URL construction. The Until loop correctly exited when no
  `@odata.nextLink` was present in the Graph API response.

---

## ADR-8: Azure Data Factory over Alternative Migration Tools

- **Date**: February 2026
- **Status**: Accepted
- **Context**: Multiple tools and platforms could orchestrate a SharePoint-to-ADLS migration.
  The selection criteria included: cloud-native (no on-premises infrastructure), enterprise
  monitoring and alerting, parameterized execution for multiple libraries, integration with
  Azure Key Vault and ADLS Gen2, and supportability within the existing Azure environment.
- **Decision**: Use Azure Data Factory as the primary orchestration engine, leveraging its
  HTTP connector for Graph API calls, Copy activity for file transfer, and SQL connector
  for audit logging.
- **Alternatives Considered**:
  - **ShareGate / AvePoint**: Rejected for POC phase. These are mature migration tools but
    require separate licensing, procurement, and are optimized for SharePoint-to-SharePoint
    migrations rather than SharePoint-to-ADLS.
  - **Custom Python scripts (Azure Functions or VMs)**: Rejected. Would require building
    pagination, retry logic, parallelism, monitoring, and error handling from scratch. ADF
    provides these capabilities out of the box.
  - **Custom PowerShell scripts**: Rejected for the same reasons as Python. PowerShell was
    used for setup and monitoring scripts but not for the core data movement.
  - **Azure Logic Apps**: Considered but rejected. Logic Apps has SharePoint connectors but
    they are designed for event-driven scenarios, not bulk data migration. Pricing model
    (per-action) would be expensive at scale.
- **Consequences**:
  - *Positive*: Native Azure service with built-in monitoring (ADF Monitor), alerting, and
    integration with Azure DevOps for CI/CD.
  - *Positive*: Managed Identity support for ADLS Gen2 writes — no storage keys needed.
  - *Positive*: Parameterized pipelines allow the same logic to process any library by
    passing different control-table rows.
  - *Positive*: Built-in retry policies on Copy activities and Web activities.
  - *Negative*: ADF has significant constraints on activity nesting (see ADR-3, ADR-4,
    ADR-7), requiring workarounds that add complexity.
  - *Negative*: ADF's expression language is limited compared to a general-purpose
    programming language, making complex string manipulation cumbersome.
- **Validation**: POC successfully migrated three document libraries (~5,000 files) using
  ADF pipelines. End-to-end execution, audit logging, and incremental sync all functioned
  as expected.

---

## Summary

| ADR | Decision | Primary Driver |
|-----|----------|----------------|
| 1 | Graph API over SP REST API | AAD v2.0 token incompatibility |
| 2 | Delta query for enumeration | Flat file list at all depths, incremental sync |
| 3 | Child pipeline pattern | ADF Until cannot contain ForEach |
| 4 | Always-refresh tokens | ADF Until cannot contain IfCondition |
| 5 | /content endpoint | ADF HTTP connector URL doubling bug |
| 6 | Cross-tenant service principal | ADF in MCAPS, SharePoint in client tenant |
| 7 | @if() expressions | ADF Until cannot contain IfCondition/Switch |
| 8 | ADF over alternatives | Cloud-native, enterprise monitoring, parameterized |

All decisions were validated during the February 2026 POC and are documented here for
reference during the production implementation phase.
