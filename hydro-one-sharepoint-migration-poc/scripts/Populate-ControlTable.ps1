<#
.SYNOPSIS
    Populates the migration control table with SharePoint site collections and document libraries.

.DESCRIPTION
    This script:
    - Connects to SharePoint Online using PnP PowerShell
    - Enumerates all site collections (or specific ones)
    - Gets all document libraries in each site
    - Calculates file counts and sizes
    - Populates the SQL control table

.PARAMETER SharePointTenantUrl
    SharePoint Online tenant URL (e.g., https://hydroone.sharepoint.com)

.PARAMETER SqlServerName
    Azure SQL Server name

.PARAMETER SqlDatabaseName
    Database name containing the control table

.PARAMETER SiteFilter
    Optional filter to limit which sites to enumerate (e.g., "*Documents*")

.EXAMPLE
    .\Populate-ControlTable.ps1 -SharePointTenantUrl "https://hydroone.sharepoint.com" `
        -SqlServerName "sql-hydroone-migration-dev" -SqlDatabaseName "MigrationControl" `
        -ClientId "your-entra-app-client-id"

.NOTES
    Author: Microsoft Azure Data Engineering Team
    Project: Hydro One SharePoint Migration POC
    Requires: PnP.PowerShell module, SqlServer module
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SharePointTenantUrl,

    [Parameter(Mandatory = $true)]
    [string]$SqlServerName,

    [Parameter(Mandatory = $true)]
    [string]$SqlDatabaseName,

    [Parameter(Mandatory = $false)]
    [string]$SiteFilter = "*",

    [Parameter(Mandatory = $false)]
    [string[]]$ExcludeSites = @(),

    [Parameter(Mandatory = $false)]
    [string[]]$SpecificSites = @(),

    [Parameter(Mandatory = $false)]
    [switch]$UseInteractiveAuth,

    [Parameter(Mandatory = $false)]
    [string]$ClientId,

    [Parameter(Mandatory = $false)]
    [string]$CertificateThumbprint
)

#region Configuration
$ErrorActionPreference = "Stop"
$ProgressPreference = "Continue"

# Libraries to exclude (system libraries)
$excludeLibraries = @(
    "Style Library",
    "Site Assets",
    "Site Pages",
    "Form Templates",
    "Preservation Hold Library",
    "_catalogs",
    "appdata",
    "Customized Reports",
    "Web Part Gallery",
    "Master Page Gallery"
)
#endregion

#region Functions
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $color = switch ($Level) {
        "INFO"    { "White" }
        "SUCCESS" { "Green" }
        "WARNING" { "Yellow" }
        "ERROR"   { "Red" }
        default   { "White" }
    }
    Write-Host "[$timestamp] [$Level] $Message" -ForegroundColor $color
}

function Test-CertificateInStore {
    param([string]$Thumbprint)

    Write-Log "  [DIAG] Searching for certificate with thumbprint: $Thumbprint" -Level "INFO"
    $stores = @("Cert:\CurrentUser\My", "Cert:\LocalMachine\My")
    $found = $false
    foreach ($store in $stores) {
        try {
            $cert = Get-ChildItem -Path $store | Where-Object { $_.Thumbprint -eq $Thumbprint }
            if ($cert) {
                $found = $true
                Write-Log "  [DIAG] FOUND certificate in $store" -Level "SUCCESS"
                Write-Log "  [DIAG]   Subject:    $($cert.Subject)" -Level "INFO"
                Write-Log "  [DIAG]   Issuer:     $($cert.Issuer)" -Level "INFO"
                Write-Log "  [DIAG]   NotBefore:  $($cert.NotBefore)" -Level "INFO"
                Write-Log "  [DIAG]   NotAfter:   $($cert.NotAfter)" -Level "INFO"
                Write-Log "  [DIAG]   HasPrivKey: $($cert.HasPrivateKey)" -Level "INFO"
                Write-Log "  [DIAG]   KeyUsage:   $($cert.Extensions | Where-Object { $_ -is [System.Security.Cryptography.X509Certificates.X509KeyUsageExtension] } | ForEach-Object { $_.KeyUsages })" -Level "INFO"
                if ($cert.NotAfter -lt (Get-Date)) {
                    Write-Log "  [DIAG]   WARNING: Certificate has EXPIRED on $($cert.NotAfter)" -Level "ERROR"
                }
                if (-not $cert.HasPrivateKey) {
                    Write-Log "  [DIAG]   WARNING: Certificate does NOT have a private key - auth will fail" -Level "ERROR"
                }
            }
            else {
                Write-Log "  [DIAG] Not found in $store" -Level "INFO"
            }
        }
        catch {
            Write-Log "  [DIAG] Could not search $store : $_" -Level "WARNING"
        }
    }
    if (-not $found) {
        Write-Log "  [DIAG] CERTIFICATE NOT FOUND in any store. Ensure it is imported into CurrentUser\My." -Level "ERROR"
    }
    return $found
}

function Inspect-PnPAccessToken {
    Write-Log "  [DIAG] === Access Token Inspection ===" -Level "INFO"
    try {
        $token = Get-PnPAccessToken -ErrorAction Stop
        if (-not $token) {
            Write-Log "  [DIAG] Get-PnPAccessToken returned null/empty" -Level "ERROR"
            return
        }
        Write-Log "  [DIAG] Access token retrieved (length: $($token.Length) chars)" -Level "SUCCESS"
        Write-Log "  [DIAG] Token prefix: $($token.Substring(0, [Math]::Min(20, $token.Length)))..." -Level "INFO"

        # Decode JWT payload (middle segment)
        $parts = $token.Split('.')
        if ($parts.Count -ge 2) {
            $payload = $parts[1]
            # Fix Base64 padding
            $padded = $payload.Replace('-', '+').Replace('_', '/')
            switch ($padded.Length % 4) {
                2 { $padded += '==' }
                3 { $padded += '=' }
            }
            try {
                $decoded = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($padded))
                $claims = $decoded | ConvertFrom-Json

                Write-Log "  [DIAG] --- JWT Claims ---" -Level "INFO"
                Write-Log "  [DIAG]   aud (audience):  $($claims.aud)" -Level "INFO"
                Write-Log "  [DIAG]   iss (issuer):    $($claims.iss)" -Level "INFO"
                Write-Log "  [DIAG]   app_displayname: $($claims.app_displayname)" -Level "INFO"
                Write-Log "  [DIAG]   appid (clientId):$($claims.appid)" -Level "INFO"
                Write-Log "  [DIAG]   tid (tenantId):  $($claims.tid)" -Level "INFO"
                Write-Log "  [DIAG]   oid (objectId):  $($claims.oid)" -Level "INFO"
                Write-Log "  [DIAG]   sub (subject):   $($claims.sub)" -Level "INFO"
                Write-Log "  [DIAG]   idtyp:           $($claims.idtyp)" -Level "INFO"

                # Token timestamps
                if ($claims.iat) {
                    $issuedAt = [DateTimeOffset]::FromUnixTimeSeconds($claims.iat).DateTime
                    Write-Log "  [DIAG]   iat (issued):    $issuedAt UTC" -Level "INFO"
                }
                if ($claims.exp) {
                    $expiresAt = [DateTimeOffset]::FromUnixTimeSeconds($claims.exp).DateTime
                    $remaining = ($expiresAt - [DateTime]::UtcNow).TotalMinutes
                    Write-Log "  [DIAG]   exp (expires):   $expiresAt UTC ($([math]::Round($remaining, 1)) min remaining)" -Level "INFO"
                    if ($remaining -lt 5) {
                        Write-Log "  [DIAG]   WARNING: Token expires in less than 5 minutes!" -Level "WARNING"
                    }
                }

                # Roles (application permissions)
                if ($claims.roles) {
                    Write-Log "  [DIAG]   --- Application Roles (permissions granted) ---" -Level "INFO"
                    foreach ($role in $claims.roles) {
                        Write-Log "  [DIAG]     ROLE: $role" -Level "SUCCESS"
                    }
                    # Check for required permissions
                    $requiredRoles = @("Sites.Read.All", "Sites.ReadWrite.All", "Sites.FullControl.All", "Files.Read.All", "Files.ReadWrite.All")
                    $hasRead = $claims.roles | Where-Object { $_ -in $requiredRoles }
                    if (-not $hasRead) {
                        Write-Log "  [DIAG]   WARNING: None of the expected SharePoint/Graph roles found!" -Level "ERROR"
                        Write-Log "  [DIAG]   Expected at least one of: $($requiredRoles -join ', ')" -Level "ERROR"
                        Write-Log "  [DIAG]   This will cause 403 Forbidden errors when accessing SharePoint data." -Level "ERROR"
                    }
                }
                else {
                    Write-Log "  [DIAG]   WARNING: No 'roles' claim found in token" -Level "WARNING"
                    Write-Log "  [DIAG]   This means NO application permissions are granted, or admin consent is missing." -Level "ERROR"
                }

                # Scopes (delegated permissions)
                if ($claims.scp) {
                    Write-Log "  [DIAG]   --- Delegated Scopes ---" -Level "INFO"
                    Write-Log "  [DIAG]     SCOPES: $($claims.scp)" -Level "INFO"
                }

                # Audience check
                if ($claims.aud) {
                    if ($claims.aud -like "*sharepoint*") {
                        Write-Log "  [DIAG]   Audience is SharePoint resource" -Level "INFO"
                    }
                    elseif ($claims.aud -like "*graph.microsoft.com*") {
                        Write-Log "  [DIAG]   Audience is Microsoft Graph" -Level "INFO"
                    }
                    else {
                        Write-Log "  [DIAG]   Audience is: $($claims.aud) (not SharePoint or Graph)" -Level "WARNING"
                    }
                }

                Write-Log "  [DIAG] --- End JWT Claims ---" -Level "INFO"
            }
            catch {
                Write-Log "  [DIAG] Could not decode JWT payload: $_" -Level "WARNING"
            }
        }
        else {
            Write-Log "  [DIAG] Token does not appear to be a valid JWT (expected 3 segments, got $($parts.Count))" -Level "WARNING"
        }
    }
    catch {
        Write-Log "  [DIAG] Failed to retrieve access token: $_" -Level "ERROR"
        Write-Log "  [DIAG] Exception type: $($_.Exception.GetType().FullName)" -Level "ERROR"
        Write-Log "  [DIAG] This may indicate the connection was not fully established." -Level "ERROR"
    }
}

function Test-GraphApiAccess {
    param([string]$SiteUrl)

    Write-Log "  [DIAG] === Graph API Permission Probe ===" -Level "INFO"
    try {
        $token = Get-PnPAccessToken -ErrorAction Stop
        $headers = @{ "Authorization" = "Bearer $token"; "Accept" = "application/json" }

        # Test 1: Can we reach Graph API at all?
        Write-Log "  [DIAG] Test 1: GET https://graph.microsoft.com/v1.0/me (basic Graph connectivity)" -Level "INFO"
        try {
            $meResult = Invoke-RestMethod -Uri "https://graph.microsoft.com/v1.0/me" -Headers $headers -Method Get -ErrorAction Stop
            Write-Log "  [DIAG]   PASS - Authenticated as: $($meResult.displayName) ($($meResult.userPrincipalName))" -Level "SUCCESS"
        }
        catch {
            $statusCode = $_.Exception.Response.StatusCode.value__
            Write-Log "  [DIAG]   HTTP $statusCode - $($_.Exception.Message)" -Level "WARNING"
            if ($statusCode -eq 403) {
                Write-Log "  [DIAG]   Note: 403 on /me is expected for app-only (certificate) auth. Testing app endpoint instead..." -Level "INFO"
                try {
                    $orgResult = Invoke-RestMethod -Uri "https://graph.microsoft.com/v1.0/organization" -Headers $headers -Method Get -ErrorAction Stop
                    Write-Log "  [DIAG]   PASS (app-only) - Org: $($orgResult.value[0].displayName) (TenantId: $($orgResult.value[0].id))" -Level "SUCCESS"
                }
                catch {
                    $orgStatus = $_.Exception.Response.StatusCode.value__
                    Write-Log "  [DIAG]   FAIL - /organization also returned HTTP $orgStatus : $($_.Exception.Message)" -Level "ERROR"
                }
            }
        }

        # Test 2: Can we access SharePoint sites via Graph?
        if ($SiteUrl -match "sharepoint\.com(/sites/|/teams/)(.+)$") {
            $sitePath = $Matches[2].TrimEnd('/')
            $hostname = ([Uri]$SiteUrl).Host
            $graphSiteUrl = "https://graph.microsoft.com/v1.0/sites/${hostname}:/sites/${sitePath}"
            Write-Log "  [DIAG] Test 2: GET $graphSiteUrl (Graph API site access)" -Level "INFO"
            try {
                $siteResult = Invoke-RestMethod -Uri $graphSiteUrl -Headers $headers -Method Get -ErrorAction Stop
                Write-Log "  [DIAG]   PASS - Site found: '$($siteResult.displayName)' (id: $($siteResult.id))" -Level "SUCCESS"
            }
            catch {
                $statusCode = $_.Exception.Response.StatusCode.value__
                Write-Log "  [DIAG]   FAIL - HTTP $statusCode : $($_.Exception.Message)" -Level "ERROR"
                if ($statusCode -eq 401) {
                    Write-Log "  [DIAG]   401 Unauthorized: Token is invalid, expired, or audience mismatch" -Level "ERROR"
                }
                elseif ($statusCode -eq 403) {
                    Write-Log "  [DIAG]   403 Forbidden: App lacks Sites.Read.All permission OR admin consent not granted" -Level "ERROR"
                    Write-Log "  [DIAG]   ACTION: Go to Entra ID > App registrations > $ClientId > API permissions" -Level "ERROR"
                    Write-Log "  [DIAG]   Verify Sites.Read.All (Application) has a green checkmark for admin consent" -Level "ERROR"
                }
                elseif ($statusCode -eq 404) {
                    Write-Log "  [DIAG]   404 Not Found: Site does not exist at this path, or app cannot see it" -Level "ERROR"
                    Write-Log "  [DIAG]   Verify the site URL is correct: $SiteUrl" -Level "ERROR"
                }
            }
        }

        # Test 3: Can we list drives (document libraries) via Graph?
        if ($SiteUrl -match "sharepoint\.com(/sites/|/teams/)(.+)$") {
            $graphDrivesUrl = "https://graph.microsoft.com/v1.0/sites/${hostname}:/sites/${sitePath}:/drives"
            Write-Log "  [DIAG] Test 3: GET $graphDrivesUrl (Graph API drives/libraries)" -Level "INFO"
            try {
                $drivesResult = Invoke-RestMethod -Uri $graphDrivesUrl -Headers $headers -Method Get -ErrorAction Stop
                $driveCount = ($drivesResult.value | Measure-Object).Count
                Write-Log "  [DIAG]   PASS - Found $driveCount drive(s):" -Level "SUCCESS"
                $drivesResult.value | ForEach-Object {
                    Write-Log "  [DIAG]     Drive: '$($_.name)' (id: $($_.id), type: $($_.driveType))" -Level "INFO"
                }
            }
            catch {
                $statusCode = $_.Exception.Response.StatusCode.value__
                Write-Log "  [DIAG]   FAIL - HTTP $statusCode : $($_.Exception.Message)" -Level "ERROR"
                if ($statusCode -eq 403) {
                    Write-Log "  [DIAG]   403: App lacks Files.Read.All permission to enumerate drives" -Level "ERROR"
                }
            }
        }

        # Test 4: Test SharePoint REST API access (via PnP context)
        Write-Log "  [DIAG] Test 4: SharePoint REST API via PnP (Get-PnPWeb)" -Level "INFO"
        try {
            $web = Get-PnPWeb -ErrorAction Stop
            Write-Log "  [DIAG]   PASS - PnP Web title: '$($web.Title)', URL: $($web.Url)" -Level "SUCCESS"
        }
        catch {
            Write-Log "  [DIAG]   FAIL - Get-PnPWeb error: $_" -Level "ERROR"
            Write-Log "  [DIAG]   Exception type: $($_.Exception.GetType().FullName)" -Level "ERROR"
        }

        Write-Log "  [DIAG] === End Permission Probe ===" -Level "INFO"
    }
    catch {
        Write-Log "  [DIAG] Permission probe failed (could not get access token): $_" -Level "ERROR"
    }
}

function Get-LibraryStats {
    param(
        [string]$SiteUrl,
        [string]$LibraryName
    )

    Write-Log "      [Get-LibraryStats] Start - Site: $SiteUrl, Library: '$LibraryName'" -Level "INFO"
    $statsStart = Get-Date

    try {
        Write-Log "      [Get-LibraryStats] Calling Get-PnPListItem -List '$LibraryName' -PageSize 5000 -Fields FileLeafRef, File_x0020_Size, FSObjType..." -Level "INFO"
        $items = Get-PnPListItem -List $LibraryName -PageSize 5000 -Fields "FileLeafRef", "File_x0020_Size", "FSObjType"
        $itemCount = ($items | Measure-Object).Count
        $fetchDuration = ((Get-Date) - $statsStart).TotalSeconds
        Write-Log "      [Get-LibraryStats] Retrieved $itemCount total items in $([math]::Round($fetchDuration, 1))s" -Level "INFO"

        if ($itemCount -eq 0) {
            Write-Log "      [Get-LibraryStats] WARNING: 0 items returned. Library may be empty, or auth scope may not allow item enumeration." -Level "WARNING"
        }

        $files = $items | Where-Object { $_["FSObjType"] -eq 0 }
        $folders = $items | Where-Object { $_["FSObjType"] -eq 1 }
        $other = $items | Where-Object { $_["FSObjType"] -ne 0 -and $_["FSObjType"] -ne 1 }
        Write-Log "      [Get-LibraryStats] Breakdown: $(($files | Measure-Object).Count) files, $(($folders | Measure-Object).Count) folders, $(($other | Measure-Object).Count) other" -Level "INFO"

        # Log a sample of the first 3 file names for visual confirmation
        if (($files | Measure-Object).Count -gt 0) {
            $sample = $files | Select-Object -First 3
            $sample | ForEach-Object {
                Write-Log "      [Get-LibraryStats] Sample file: '$($_["FileLeafRef"])' ($([math]::Round([long]$_["File_x0020_Size"] / 1KB, 2)) KB)" -Level "INFO"
            }
        }

        $stats = @{
            FileCount   = ($files | Measure-Object).Count
            FolderCount = ($folders | Measure-Object).Count
            TotalSize   = ($files | ForEach-Object { [long]$_["File_x0020_Size"] } | Measure-Object -Sum).Sum
            LargestFile = ($files | ForEach-Object { [long]$_["File_x0020_Size"] } | Measure-Object -Maximum).Maximum
        }

        Write-Log "      [Get-LibraryStats] Computed stats - Files: $($stats.FileCount), Folders: $($stats.FolderCount), TotalSize: $($stats.TotalSize) bytes ($([math]::Round($stats.TotalSize / 1MB, 2)) MB), Largest: $($stats.LargestFile) bytes" -Level "INFO"
        return $stats
    }
    catch {
        Write-Log "      [Get-LibraryStats] FAILED for library '$LibraryName'" -Level "ERROR"
        Write-Log "      [Get-LibraryStats] Error: $_" -Level "ERROR"
        Write-Log "      [Get-LibraryStats] Exception type: $($_.Exception.GetType().FullName)" -Level "ERROR"
        Write-Log "      [Get-LibraryStats] Exception message: $($_.Exception.Message)" -Level "ERROR"
        if ($_.Exception.InnerException) {
            Write-Log "      [Get-LibraryStats] Inner exception: $($_.Exception.InnerException.Message)" -Level "ERROR"
        }
        Write-Log "      [Get-LibraryStats] Stack trace: $($_.ScriptStackTrace)" -Level "ERROR"
        return @{
            FileCount   = 0
            FolderCount = 0
            TotalSize   = 0
            LargestFile = 0
        }
    }
}

function Insert-ControlTableRecord {
    param(
        [string]$ConnectionString,
        [hashtable]$Record
    )

    $query = @"
    IF NOT EXISTS (
        SELECT 1 FROM dbo.MigrationControl
        WHERE SiteUrl = @SiteUrl AND LibraryName = @LibraryName
    )
    BEGIN
        INSERT INTO dbo.MigrationControl (
            SiteUrl, LibraryName, SiteTitle, LibraryTitle,
            Status, FileCount, FolderCount, TotalSizeBytes, LargestFileSizeBytes,
            Priority, CreatedDate, CreatedBy
        ) VALUES (
            @SiteUrl, @LibraryName, @SiteTitle, @LibraryTitle,
            'Pending', @FileCount, @FolderCount, @TotalSizeBytes, @LargestFileSizeBytes,
            @Priority, GETUTCDATE(), @CreatedBy
        )
    END
    ELSE
    BEGIN
        UPDATE dbo.MigrationControl
        SET FileCount = @FileCount,
            FolderCount = @FolderCount,
            TotalSizeBytes = @TotalSizeBytes,
            LargestFileSizeBytes = @LargestFileSizeBytes,
            ModifiedDate = GETUTCDATE(),
            ModifiedBy = @CreatedBy
        WHERE SiteUrl = @SiteUrl AND LibraryName = @LibraryName
    END
"@

    $params = @{
        SiteUrl             = $Record.SiteUrl
        LibraryName         = $Record.LibraryName
        SiteTitle           = $Record.SiteTitle
        LibraryTitle        = $Record.LibraryTitle
        FileCount           = $Record.FileCount
        FolderCount         = $Record.FolderCount
        TotalSizeBytes      = $Record.TotalSizeBytes
        LargestFileSizeBytes = $Record.LargestFileSizeBytes
        Priority            = $Record.Priority
        CreatedBy           = $env:USERNAME
    }

    Write-Log "      [SQL] Upsert payload: SiteUrl='$($params.SiteUrl)', LibraryName='$($params.LibraryName)', SiteTitle='$($params.SiteTitle)', FileCount=$($params.FileCount), TotalSizeBytes=$($params.TotalSizeBytes), Priority=$($params.Priority)" -Level "INFO"

    # Pre-check: does the row already exist?
    try {
        $existsQuery = "SELECT COUNT(*) AS RowCount FROM dbo.MigrationControl WHERE SiteUrl = '$($params.SiteUrl -replace "'","''")' AND LibraryName = '$($params.LibraryName -replace "'","''")'"
        $existsResult = Invoke-Sqlcmd -ConnectionString $ConnectionString -Query $existsQuery
        $existed = ($existsResult.RowCount -gt 0)
        Write-Log "      [SQL] Pre-check: row $(if ($existed) { 'EXISTS - will UPDATE' } else { 'does NOT exist - will INSERT' })" -Level "INFO"
    }
    catch {
        Write-Log "      [SQL] Pre-check failed (continuing anyway): $_" -Level "WARNING"
        $existed = $null
    }

    $sqlStart = Get-Date
    Invoke-Sqlcmd -ConnectionString $ConnectionString -Query $query -Variable @(
        "SiteUrl=$($params.SiteUrl)",
        "LibraryName=$($params.LibraryName)",
        "SiteTitle=$($params.SiteTitle)",
        "LibraryTitle=$($params.LibraryTitle)",
        "FileCount=$($params.FileCount)",
        "FolderCount=$($params.FolderCount)",
        "TotalSizeBytes=$($params.TotalSizeBytes)",
        "LargestFileSizeBytes=$($params.LargestFileSizeBytes)",
        "Priority=$($params.Priority)",
        "CreatedBy=$($params.CreatedBy)"
    )
    $sqlDuration = ((Get-Date) - $sqlStart).TotalSeconds
    Write-Log "      [SQL] Operation completed in $([math]::Round($sqlDuration, 2))s ($(if ($existed) { 'UPDATE' } elseif ($existed -eq $false) { 'INSERT' } else { 'UNKNOWN' }))" -Level "INFO"
}
#endregion

#region Main Script
Write-Log "========================================" -Level "INFO"
Write-Log "SharePoint Site Enumeration and Control Table Population" -Level "INFO"
Write-Log "========================================" -Level "INFO"

# Log environment details for troubleshooting
Write-Log "PowerShell Version: $($PSVersionTable.PSVersion) ($($PSVersionTable.PSEdition))" -Level "INFO"
Write-Log "OS: $([System.Runtime.InteropServices.RuntimeInformation]::OSDescription)" -Level "INFO"
Write-Log ".NET Runtime: $([System.Runtime.InteropServices.RuntimeInformation]::FrameworkDescription)" -Level "INFO"
Write-Log "Running as: $env:USERNAME on $env:COMPUTERNAME" -Level "INFO"
Write-Log "Working directory: $(Get-Location)" -Level "INFO"
Write-Log "SharePoint Tenant: $SharePointTenantUrl" -Level "INFO"
Write-Log "SQL Server: $SqlServerName" -Level "INFO"
Write-Log "SQL Database: $SqlDatabaseName" -Level "INFO"
Write-Log "Site Filter: $SiteFilter" -Level "INFO"
if ($SpecificSites.Count -gt 0) { Write-Log "Specific Sites: $($SpecificSites -join ', ')" -Level "INFO" }
if ($ExcludeSites.Count -gt 0) { Write-Log "Excluded Sites: $($ExcludeSites -join ', ')" -Level "INFO" }
Write-Log "Auth Mode: $(if ($ClientId -and $CertificateThumbprint) { 'Certificate' } elseif ($ClientId) { 'Interactive with ClientId' } else { 'No ClientId (will fail)' })" -Level "INFO"
Write-Log "ClientId: $(if ($ClientId) { $ClientId } else { '(not provided)' })" -Level "INFO"
Write-Log "========================================" -Level "INFO"

# Check PowerShell version compatibility
if ($PSVersionTable.PSVersion.Major -lt 7) {
    Write-Log "WARNING: PnP.PowerShell 2.x requires PowerShell 7.2+. You are running PowerShell $($PSVersionTable.PSVersion)." -Level "ERROR"
    Write-Log "Please install PowerShell 7: winget install Microsoft.PowerShell" -Level "ERROR"
    Write-Log "Then re-run this script using 'pwsh' instead of 'powershell'." -Level "ERROR"
    throw "PowerShell 7.2+ is required. Current version: $($PSVersionTable.PSVersion)"
}

# Check for required modules
$requiredModules = @("PnP.PowerShell", "SqlServer")
foreach ($module in $requiredModules) {
    if (-not (Get-Module -ListAvailable -Name $module)) {
        Write-Log "Module '$module' not found. Installing..." -Level "WARNING"
        Install-Module -Name $module -Force -AllowClobber -Scope CurrentUser
        Write-Log "Module '$module' installed successfully." -Level "SUCCESS"
    }
    else {
        $moduleVersion = (Get-Module -ListAvailable -Name $module | Sort-Object Version -Descending | Select-Object -First 1).Version
        Write-Log "Module '$module' found (v$moduleVersion)" -Level "INFO"
    }
    Write-Log "Importing module: $module" -Level "INFO"
    Import-Module $module
    Write-Log "Module '$module' imported successfully." -Level "SUCCESS"
}

# Auto-detect if a site URL was passed as -SharePointTenantUrl and extract the site path
# e.g. "https://hydroone.sharepoint.com/sites/MySite" -> tenant="https://hydroone.sharepoint.com", site="/sites/MySite"
if ($SharePointTenantUrl -match "^(https://[^/]+\.sharepoint\.com)(/sites/.+|/teams/.+)$") {
    $extractedTenantUrl = $Matches[1]
    $extractedSitePath = $Matches[2].TrimEnd('/')
    Write-Log "Detected site path in -SharePointTenantUrl: '$extractedSitePath'" -Level "WARNING"
    Write-Log "Extracting tenant root: '$extractedTenantUrl'" -Level "WARNING"
    $SharePointTenantUrl = $extractedTenantUrl
    if ($SpecificSites.Count -eq 0) {
        $SpecificSites = @($extractedSitePath)
        Write-Log "Auto-set -SpecificSites to: $($SpecificSites -join ', ')" -Level "WARNING"
    }
    else {
        Write-Log "SpecificSites already provided, ignoring extracted site path." -Level "INFO"
    }
}

# Build SQL connection string (using Azure AD authentication)
$sqlFqdn = "$SqlServerName.database.windows.net"
$sqlConnectionString = "Server=tcp:$sqlFqdn,1433;Initial Catalog=$SqlDatabaseName;Authentication=Active Directory Integrated;Encrypt=True;TrustServerCertificate=False;Connection Timeout=30;"
Write-Log "SQL connection string built (server: $sqlFqdn, db: $SqlDatabaseName, auth: AD Integrated)" -Level "INFO"

# === SQL PRE-FLIGHT CHECK ===
Write-Log "========================================" -Level "INFO"
Write-Log "SQL CONNECTIVITY PRE-FLIGHT CHECK" -Level "INFO"
Write-Log "========================================" -Level "INFO"

# Step 1: DNS resolution
Write-Log "[SQL-DIAG] Step 1: DNS resolution for $sqlFqdn" -Level "INFO"
try {
    $dnsResult = [System.Net.Dns]::GetHostAddresses($sqlFqdn)
    Write-Log "[SQL-DIAG]   PASS - Resolved to: $($dnsResult.IPAddressToString -join ', ')" -Level "SUCCESS"
}
catch {
    Write-Log "[SQL-DIAG]   FAIL - Cannot resolve hostname: $sqlFqdn" -Level "ERROR"
    Write-Log "[SQL-DIAG]   Error: $($_.Exception.Message)" -Level "ERROR"
    Write-Log "[SQL-DIAG]   --- Troubleshooting ---" -Level "ERROR"
    Write-Log "[SQL-DIAG]   1. Verify the SQL server name is correct: '$SqlServerName'" -Level "ERROR"
    Write-Log "[SQL-DIAG]   2. Check if the server exists: az sql server show --name $SqlServerName --resource-group <rg-name>" -Level "ERROR"
    Write-Log "[SQL-DIAG]   3. If using private endpoints, ensure your DNS can resolve the private link FQDN" -Level "ERROR"
    Write-Log "[SQL-DIAG]   4. Try: nslookup $sqlFqdn" -Level "ERROR"
    throw "SQL Server DNS resolution failed for '$sqlFqdn'. Verify the -SqlServerName parameter is correct."
}

# Step 2: TCP connectivity
Write-Log "[SQL-DIAG] Step 2: TCP connectivity to $sqlFqdn`:1433" -Level "INFO"
try {
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    $connectTask = $tcpClient.ConnectAsync($sqlFqdn, 1433)
    if ($connectTask.Wait(10000)) {
        Write-Log "[SQL-DIAG]   PASS - TCP port 1433 is reachable" -Level "SUCCESS"
    }
    else {
        Write-Log "[SQL-DIAG]   FAIL - TCP connection timed out after 10s" -Level "ERROR"
        Write-Log "[SQL-DIAG]   The server exists but port 1433 is not reachable." -Level "ERROR"
        Write-Log "[SQL-DIAG]   Check: firewall rules, NSG rules, or private endpoint configuration." -Level "ERROR"
    }
    $tcpClient.Close()
}
catch {
    Write-Log "[SQL-DIAG]   FAIL - TCP connection error: $($_.Exception.Message)" -Level "ERROR"
    Write-Log "[SQL-DIAG]   Check firewall rules on the SQL server and network connectivity." -Level "ERROR"
}

# Step 3: SQL authentication test
Write-Log "[SQL-DIAG] Step 3: SQL authentication and database access" -Level "INFO"
try {
    $testResult = Invoke-Sqlcmd -ConnectionString $sqlConnectionString -Query "SELECT DB_NAME() AS DatabaseName, SUSER_SNAME() AS LoginName, SYSTEM_USER AS SystemUser, GETUTCDATE() AS ServerTime" -ErrorAction Stop
    Write-Log "[SQL-DIAG]   PASS - Connected to database: $($testResult.DatabaseName)" -Level "SUCCESS"
    Write-Log "[SQL-DIAG]   Login: $($testResult.LoginName)" -Level "INFO"
    Write-Log "[SQL-DIAG]   System User: $($testResult.SystemUser)" -Level "INFO"
    Write-Log "[SQL-DIAG]   Server Time (UTC): $($testResult.ServerTime)" -Level "INFO"
}
catch {
    Write-Log "[SQL-DIAG]   FAIL - SQL query failed: $($_.Exception.Message)" -Level "ERROR"
    if ($_.Exception.Message -like "*Login failed*") {
        Write-Log "[SQL-DIAG]   Authentication failed. Check:" -Level "ERROR"
        Write-Log "[SQL-DIAG]   1. Your Azure AD account has access to database '$SqlDatabaseName'" -Level "ERROR"
        Write-Log "[SQL-DIAG]   2. You are logged into the correct Azure account: az account show" -Level "ERROR"
        Write-Log "[SQL-DIAG]   3. The SQL Server has Azure AD admin configured" -Level "ERROR"
    }
    elseif ($_.Exception.Message -like "*Cannot open database*") {
        Write-Log "[SQL-DIAG]   Database '$SqlDatabaseName' does not exist or is inaccessible." -Level "ERROR"
    }
    throw "SQL pre-flight check failed. Fix the SQL connection before proceeding."
}

# Step 4: Verify MigrationControl table exists
Write-Log "[SQL-DIAG] Step 4: Verify MigrationControl table exists" -Level "INFO"
try {
    $tableCheck = Invoke-Sqlcmd -ConnectionString $sqlConnectionString -Query "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'MigrationControl'" -ErrorAction Stop
    if ($tableCheck) {
        Write-Log "[SQL-DIAG]   PASS - Table found: $($tableCheck.TABLE_SCHEMA).$($tableCheck.TABLE_NAME)" -Level "SUCCESS"

        # Check current row count
        $rowCount = Invoke-Sqlcmd -ConnectionString $sqlConnectionString -Query "SELECT COUNT(*) AS RowCount FROM dbo.MigrationControl" -ErrorAction Stop
        Write-Log "[SQL-DIAG]   Current row count: $($rowCount.RowCount)" -Level "INFO"
    }
    else {
        Write-Log "[SQL-DIAG]   FAIL - Table 'MigrationControl' not found in database '$SqlDatabaseName'" -Level "ERROR"
        Write-Log "[SQL-DIAG]   Run the DDL script first: sqlcmd -S $sqlFqdn -d $SqlDatabaseName -i sql/create_control_table.sql -G" -Level "ERROR"
        throw "MigrationControl table does not exist."
    }
}
catch [Microsoft.Data.SqlClient.SqlException] {
    Write-Log "[SQL-DIAG]   FAIL - Could not query table metadata: $($_.Exception.Message)" -Level "ERROR"
    throw
}

# Step 5: Test write permission
Write-Log "[SQL-DIAG] Step 5: Verify write permissions (INSERT/UPDATE)" -Level "INFO"
try {
    $permCheck = Invoke-Sqlcmd -ConnectionString $sqlConnectionString -Query @"
        SELECT
            HAS_PERMS_BY_NAME('dbo.MigrationControl', 'OBJECT', 'INSERT') AS CanInsert,
            HAS_PERMS_BY_NAME('dbo.MigrationControl', 'OBJECT', 'UPDATE') AS CanUpdate,
            HAS_PERMS_BY_NAME('dbo.MigrationControl', 'OBJECT', 'SELECT') AS CanSelect
"@ -ErrorAction Stop
    Write-Log "[SQL-DIAG]   SELECT: $(if ($permCheck.CanSelect -eq 1) { 'GRANTED' } else { 'DENIED' })" -Level $(if ($permCheck.CanSelect -eq 1) { "SUCCESS" } else { "ERROR" })
    Write-Log "[SQL-DIAG]   INSERT: $(if ($permCheck.CanInsert -eq 1) { 'GRANTED' } else { 'DENIED' })" -Level $(if ($permCheck.CanInsert -eq 1) { "SUCCESS" } else { "ERROR" })
    Write-Log "[SQL-DIAG]   UPDATE: $(if ($permCheck.CanUpdate -eq 1) { 'GRANTED' } else { 'DENIED' })" -Level $(if ($permCheck.CanUpdate -eq 1) { "SUCCESS" } else { "ERROR" })
    if ($permCheck.CanInsert -ne 1 -or $permCheck.CanUpdate -ne 1) {
        Write-Log "[SQL-DIAG]   WARNING: Missing write permissions. The user needs db_datawriter role." -Level "ERROR"
        Write-Log "[SQL-DIAG]   Run: ALTER ROLE db_datawriter ADD MEMBER [your-user];" -Level "ERROR"
    }
}
catch {
    Write-Log "[SQL-DIAG]   Could not check permissions: $($_.Exception.Message)" -Level "WARNING"
}

Write-Log "[SQL-DIAG] SQL pre-flight check completed." -Level "SUCCESS"
Write-Log "========================================" -Level "INFO"

try {
    # Determine initial connection URL
    # When using -SpecificSites, we don't need admin center access (avoids 404 errors
    # when the app registration lacks SharePoint admin permissions)
    if ($SpecificSites.Count -gt 0) {
        $initialUrl = "$SharePointTenantUrl$($SpecificSites[0])"
        Write-Log "Using -SpecificSites mode: connecting directly to first site (no admin center required)" -Level "INFO"
        Write-Log "Initial connection URL: $initialUrl" -Level "INFO"
    }
    else {
        $initialUrl = $SharePointTenantUrl -replace "\.sharepoint\.com", "-admin.sharepoint.com"
        Write-Log "Connecting to SharePoint Admin Center: $initialUrl" -Level "INFO"
    }

    if ($ClientId -and $CertificateThumbprint) {
        Write-Log "Auth: Certificate-based (ClientId: $ClientId, Thumbprint: $CertificateThumbprint)" -Level "INFO"

        # Pre-flight: validate certificate exists and is valid
        Write-Log "[DIAG] === Pre-flight Certificate Validation ===" -Level "INFO"
        $certFound = Test-CertificateInStore -Thumbprint $CertificateThumbprint
        if (-not $certFound) {
            Write-Log "CERTIFICATE VALIDATION FAILED: Certificate not found in any store." -Level "ERROR"
            Write-Log "Import the certificate: Import-PfxCertificate -FilePath cert.pfx -CertStoreLocation Cert:\CurrentUser\My" -Level "ERROR"
            throw "Certificate with thumbprint $CertificateThumbprint not found."
        }

        # Resolve tenant ID
        $openIdUrl = "https://login.microsoftonline.com/$($SharePointTenantUrl.Split('/')[2].Split('.')[0]).onmicrosoft.com/.well-known/openid-configuration"
        Write-Log "Resolving tenant ID from: $openIdUrl" -Level "INFO"
        try {
            $openIdResponse = Invoke-RestMethod $openIdUrl -ErrorAction Stop
            $tenantId = $openIdResponse.token_endpoint.Split('/')[3]
            Write-Log "Resolved tenant ID: $tenantId" -Level "INFO"
            Write-Log "  token_endpoint: $($openIdResponse.token_endpoint)" -Level "INFO"
            Write-Log "  authorization_endpoint: $($openIdResponse.authorization_endpoint)" -Level "INFO"
        }
        catch {
            Write-Log "FAILED to resolve tenant ID from OpenID configuration" -Level "ERROR"
            Write-Log "  URL attempted: $openIdUrl" -Level "ERROR"
            Write-Log "  Error: $_" -Level "ERROR"
            Write-Log "  Possible cause: the .onmicrosoft.com domain does not match the SharePoint tenant" -Level "ERROR"
            Write-Log "  Try passing -TenantId directly if your tenant uses a custom domain" -Level "ERROR"
            throw
        }

        Write-Log "Calling Connect-PnPOnline with certificate auth..." -Level "INFO"
        Write-Log "  URL: $initialUrl" -Level "INFO"
        Write-Log "  ClientId: $ClientId" -Level "INFO"
        Write-Log "  Thumbprint: $CertificateThumbprint" -Level "INFO"
        Write-Log "  Tenant: $tenantId" -Level "INFO"
        try {
            Connect-PnPOnline -Url $initialUrl -ClientId $ClientId -Thumbprint $CertificateThumbprint -Tenant $tenantId
        }
        catch {
            Write-Log "FAILED to connect to: $initialUrl" -Level "ERROR"
            Write-Log "  Error: $_" -Level "ERROR"
            Write-Log "  Exception type: $($_.Exception.GetType().FullName)" -Level "ERROR"
            Write-Log "  Exception message: $($_.Exception.Message)" -Level "ERROR"
            if ($_.Exception.InnerException) {
                Write-Log "  Inner exception: $($_.Exception.InnerException.Message)" -Level "ERROR"
                Write-Log "  Inner exception type: $($_.Exception.InnerException.GetType().FullName)" -Level "ERROR"
                if ($_.Exception.InnerException.InnerException) {
                    Write-Log "  Inner inner exception: $($_.Exception.InnerException.InnerException.Message)" -Level "ERROR"
                }
            }
            Write-Log "  Stack trace: $($_.ScriptStackTrace)" -Level "ERROR"
            Write-Log "  --- Troubleshooting Guide ---" -Level "ERROR"
            Write-Log "  1. Verify certificate has a private key and is not expired (see DIAG output above)" -Level "ERROR"
            Write-Log "  2. Verify the certificate is uploaded to the Entra ID app registration:" -Level "ERROR"
            Write-Log "     Entra ID > App registrations > $ClientId > Certificates & secrets > Certificates" -Level "ERROR"
            Write-Log "  3. Verify the app has API permissions with admin consent:" -Level "ERROR"
            Write-Log "     Entra ID > App registrations > $ClientId > API permissions" -Level "ERROR"
            Write-Log "     Required: Microsoft Graph > Sites.Read.All (Application) with admin consent" -Level "ERROR"
            Write-Log "  4. Verify the tenant ID is correct: $tenantId" -Level "ERROR"
            Write-Log "  5. Verify the site URL exists: $initialUrl" -Level "ERROR"
            throw
        }
    }
    elseif ($ClientId) {
        Write-Log "Auth: Interactive with ClientId: $ClientId" -Level "INFO"
        Write-Log "Calling Connect-PnPOnline -Interactive -ClientId $ClientId -Url $initialUrl" -Level "INFO"
        Write-Log "A browser window should open for authentication..." -Level "INFO"
        try {
            Connect-PnPOnline -Url $initialUrl -Interactive -ClientId $ClientId
        }
        catch {
            Write-Log "FAILED to connect to: $initialUrl" -Level "ERROR"
            Write-Log "  Error: $_" -Level "ERROR"
            Write-Log "  Exception type: $($_.Exception.GetType().FullName)" -Level "ERROR"
            Write-Log "  Exception message: $($_.Exception.Message)" -Level "ERROR"
            if ($_.Exception.InnerException) {
                Write-Log "  Inner exception: $($_.Exception.InnerException.Message)" -Level "ERROR"
                Write-Log "  Inner exception type: $($_.Exception.InnerException.GetType().FullName)" -Level "ERROR"
            }
            Write-Log "  Stack trace: $($_.ScriptStackTrace)" -Level "ERROR"
            Write-Log "  --- Troubleshooting Guide ---" -Level "ERROR"
            Write-Log "  1. Ensure the Entra ID app has 'http://localhost' as a redirect URI:" -Level "ERROR"
            Write-Log "     Entra ID > App registrations > $ClientId > Authentication > Mobile and desktop" -Level "ERROR"
            Write-Log "  2. Ensure the app has SharePoint API permissions (Sites.Read.All) with admin consent" -Level "ERROR"
            Write-Log "  3. If you see 'NotFound', the site URL may not exist: $initialUrl" -Level "ERROR"
            Write-Log "  4. For admin center access, use -SpecificSites to skip the admin URL requirement" -Level "ERROR"
            throw
        }
    }
    else {
        Write-Log "No -ClientId provided. PnP PowerShell requires a registered Entra ID App ClientId for interactive auth." -Level "ERROR"
        Write-Log "Either:" -Level "ERROR"
        Write-Log "  1. Pass -ClientId with your own Entra ID app registration" -Level "ERROR"
        Write-Log "  2. Use the PnP multi-tenant app: -ClientId '31359c7f-bd7e-475c-86db-fdb8c937548e'" -Level "ERROR"
        Write-Log "     (requires admin consent via Register-PnPManagementShellAccess)" -Level "ERROR"
        throw "ClientId is required for PnP PowerShell interactive authentication."
    }

    Write-Log "Connected successfully to: $initialUrl" -Level "SUCCESS"

    # Verify connection
    try {
        $ctx = Get-PnPContext
        Write-Log "PnP context verified - URL: $($ctx.Url)" -Level "SUCCESS"
    }
    catch {
        Write-Log "Warning: Could not verify PnP context: $_" -Level "WARNING"
    }

    # === POST-CONNECT DIAGNOSTICS ===
    # Inspect access token to reveal granted permissions
    Write-Log "========================================" -Level "INFO"
    Write-Log "POST-CONNECT PERMISSION DIAGNOSTICS" -Level "INFO"
    Write-Log "========================================" -Level "INFO"
    Inspect-PnPAccessToken

    # Probe Graph API and SharePoint permissions directly
    Test-GraphApiAccess -SiteUrl $initialUrl
    Write-Log "========================================" -Level "INFO"

    # Get all site collections
    Write-Log "Enumerating site collections..." -Level "INFO"

    if ($SpecificSites.Count -gt 0) {
        Write-Log "Using specific sites list ($($SpecificSites.Count) sites)" -Level "INFO"
        Write-Log "Skipping Get-PnPTenantSite (avoids requiring SharePoint Administrator role). Site title will be resolved per-site via Get-PnPWeb." -Level "INFO"
        $sites = $SpecificSites | ForEach-Object {
            $targetUrl = "$SharePointTenantUrl$_"
            Write-Log "  Queued site: $targetUrl" -Level "INFO"
            [PSCustomObject]@{
                Url                 = $targetUrl
                Title               = $_
                Template            = "(not queried - non-admin mode)"
                StorageUsageCurrent = 0
            }
        }
    }
    else {
        Write-Log "Querying all tenant sites with filter: '$SiteFilter'" -Level "INFO"
        Write-Log "  NOTE: Get-PnPTenantSite requires SharePoint Administrator role or Global Administrator" -Level "INFO"
        Write-Log "  If this fails, use -SpecificSites instead to bypass admin center access" -Level "INFO"
        try {
            $allSites = Get-PnPTenantSite -Filter "Url -like '$SiteFilter'" -ErrorAction Stop
        }
        catch {
            Write-Log "FAILED: Get-PnPTenantSite returned an error" -Level "ERROR"
            Write-Log "  Error: $_" -Level "ERROR"
            Write-Log "  Exception type: $($_.Exception.GetType().FullName)" -Level "ERROR"
            Write-Log "  Exception message: $($_.Exception.Message)" -Level "ERROR"
            if ($_.Exception.InnerException) {
                Write-Log "  Inner exception: $($_.Exception.InnerException.Message)" -Level "ERROR"
                Write-Log "  Inner exception type: $($_.Exception.InnerException.GetType().FullName)" -Level "ERROR"
            }
            Write-Log "  Stack trace: $($_.ScriptStackTrace)" -Level "ERROR"
            Write-Log "" -Level "INFO"
            Write-Log "  --- Troubleshooting ---" -Level "ERROR"
            Write-Log "  This usually means one of:" -Level "ERROR"
            Write-Log "  1. The connected URL is wrong (connected to: $initialUrl)" -Level "ERROR"
            Write-Log "     Expected format: https://tenant-admin.sharepoint.com" -Level "ERROR"
            Write-Log "  2. The app/user does not have SharePoint Administrator role" -Level "ERROR"
            Write-Log "  3. The access token audience is not SharePoint (see DIAG token output above)" -Level "ERROR"
            Write-Log "" -Level "INFO"
            Write-Log "  RECOMMENDED: Use -SpecificSites to skip admin center and connect directly to sites:" -Level "ERROR"
            Write-Log "    -SpecificSites @('/sites/SiteName1', '/sites/SiteName2')" -Level "ERROR"
            throw
        }
        Write-Log "Raw site count from tenant: $(($allSites | Measure-Object).Count)" -Level "INFO"

        $sites = $allSites | Where-Object {
            $_.Template -notlike "SRCHCEN*" -and
            $_.Template -notlike "SPSMSITEHOST*" -and
            $_.Template -notlike "APPCATALOG*" -and
            $_.Template -notlike "POINTPUBLISHINGHUB*" -and
            $_.Template -notlike "EDISC*" -and
            $_.Url -notlike "*-my.sharepoint.com*"
        }
        Write-Log "After filtering system templates: $(($sites | Measure-Object).Count) sites" -Level "INFO"
    }

    # Apply exclusions
    if ($ExcludeSites.Count -gt 0) {
        $beforeExclusion = ($sites | Measure-Object).Count
        $sites = $sites | Where-Object {
            $siteUrl = $_.Url
            -not ($ExcludeSites | Where-Object { $siteUrl -like "*$_*" })
        }
        $afterExclusion = ($sites | Measure-Object).Count
        Write-Log "Applied exclusions: $beforeExclusion -> $afterExclusion sites ($($beforeExclusion - $afterExclusion) excluded)" -Level "INFO"
    }

    $siteCount = ($sites | Measure-Object).Count
    Write-Log "Total sites to process: $siteCount" -Level "INFO"

    if ($siteCount -eq 0) {
        Write-Log "No sites found to process. Check your SharePointTenantUrl, SiteFilter, or SpecificSites parameters." -Level "WARNING"
    }

    # List all sites that will be processed
    $sites | ForEach-Object { Write-Log "  Site queued: $($_.Url) (Template: $($_.Template), Storage: $([math]::Round($_.StorageUsageCurrent / 1024, 2)) GB)" -Level "INFO" }

    $totalLibraries = 0
    $totalFiles = 0
    $totalSizeGB = 0
    $failedSites = @()

    # Process each site
    $siteIndex = 0
    foreach ($site in $sites) {
        $siteIndex++
        $siteUrl = $site.Url
        $siteRelativeUrl = $siteUrl.Replace($SharePointTenantUrl, "")
        $siteStartTime = Get-Date

        Write-Log "----------------------------------------" -Level "INFO"
        Write-Log "[$siteIndex/$siteCount] Processing site: $siteRelativeUrl ($siteUrl)" -Level "INFO"
        Write-Log "  Site Title: $($site.Title)" -Level "INFO"
        Write-Log "  Template: $($site.Template)" -Level "INFO"
        Write-Log "  Storage Used: $([math]::Round($site.StorageUsageCurrent / 1024, 2)) GB" -Level "INFO"

        try {
            # Connect to the site
            Write-Log "  Disconnecting previous PnP session..." -Level "INFO"
            Disconnect-PnPOnline -ErrorAction SilentlyContinue
            Write-Log "  Connecting to site: $siteUrl" -Level "INFO"
            try {
                if ($ClientId -and $CertificateThumbprint) {
                    Write-Log "  [DIAG] Connect-PnPOnline -Url '$siteUrl' -ClientId '$ClientId' -Thumbprint '$CertificateThumbprint' -Tenant '$tenantId'" -Level "INFO"
                    Connect-PnPOnline -Url $siteUrl -ClientId $ClientId -Thumbprint $CertificateThumbprint -Tenant $tenantId
                }
                else {
                    Write-Log "  [DIAG] Connect-PnPOnline -Url '$siteUrl' -Interactive -ClientId '$ClientId'" -Level "INFO"
                    Connect-PnPOnline -Url $siteUrl -Interactive -ClientId $ClientId
                }
            }
            catch {
                Write-Log "  FAILED to connect to site: $siteUrl" -Level "ERROR"
                Write-Log "  Error: $_" -Level "ERROR"
                Write-Log "  Exception type: $($_.Exception.GetType().FullName)" -Level "ERROR"
                Write-Log "  Exception message: $($_.Exception.Message)" -Level "ERROR"
                if ($_.Exception.InnerException) {
                    Write-Log "  Inner exception: $($_.Exception.InnerException.Message)" -Level "ERROR"
                    Write-Log "  Inner exception type: $($_.Exception.InnerException.GetType().FullName)" -Level "ERROR"
                }
                Write-Log "  Stack trace: $($_.ScriptStackTrace)" -Level "ERROR"
                Write-Log "  --- Possible causes ---" -Level "ERROR"
                Write-Log "  1. Site does not exist: $siteUrl" -Level "ERROR"
                Write-Log "  2. App lacks permission to this specific site" -Level "ERROR"
                Write-Log "  3. Site may require different authentication scope" -Level "ERROR"
                throw
            }
            Write-Log "  Connected to site successfully." -Level "SUCCESS"

            # Run per-site permission diagnostics
            Write-Log "  [DIAG] --- Per-Site Token & Permission Check ---" -Level "INFO"
            Inspect-PnPAccessToken
            Test-GraphApiAccess -SiteUrl $siteUrl
            Write-Log "  [DIAG] --- End Per-Site Check ---" -Level "INFO"

            # Verify the active PnP context (confirms we're really pointing at the right site)
            try {
                $siteCtx = Get-PnPContext
                Write-Log "  PnP context after site connect - Url: $($siteCtx.Url)" -Level "INFO"
            }
            catch {
                Write-Log "  Could not retrieve PnP context: $_" -Level "WARNING"
            }

            # Log the authenticated identity (helps diagnose 'wrong account' issues)
            try {
                $currentUser = Get-PnPProperty -ClientObject (Get-PnPWeb) -Property CurrentUser
                Write-Log "  Authenticated as: $($currentUser.LoginName) ($($currentUser.Title), Email: $($currentUser.Email))" -Level "INFO"
            }
            catch {
                Write-Log "  Could not resolve current user identity: $_" -Level "WARNING"
            }

            # Log site / web details (server-relative URL, language, etc.)
            try {
                $webDetail = Get-PnPWeb -Includes Title, ServerRelativeUrl, Url, Id, Language, WebTemplate, Created
                Write-Log "  Web details - Title: '$($webDetail.Title)', ServerRelativeUrl: '$($webDetail.ServerRelativeUrl)', WebTemplate: '$($webDetail.WebTemplate)', Language: $($webDetail.Language), Created: $($webDetail.Created)" -Level "INFO"
            }
            catch {
                Write-Log "  Could not retrieve web details: $_" -Level "WARNING"
            }

            # When using SpecificSites mode, resolve title via Get-PnPWeb (non-admin operation)
            if ($SpecificSites.Count -gt 0) {
                try {
                    $web = Get-PnPWeb -Includes Title
                    if ($web -and $web.Title) {
                        $site.Title = $web.Title
                        Write-Log "  Resolved site title: $($site.Title)" -Level "INFO"
                    }
                }
                catch {
                    Write-Log "  Could not resolve site title via Get-PnPWeb: $_" -Level "WARNING"
                }
            }

            # Get all document libraries
            Write-Log "  Fetching document libraries (BaseTemplate=101, non-hidden)..." -Level "INFO"
            $listFetchStart = Get-Date
            try {
                $allLists = Get-PnPList -ErrorAction Stop
            }
            catch {
                Write-Log "  FAILED: Get-PnPList returned an error" -Level "ERROR"
                Write-Log "  Error: $_" -Level "ERROR"
                Write-Log "  Exception type: $($_.Exception.GetType().FullName)" -Level "ERROR"
                Write-Log "  Exception message: $($_.Exception.Message)" -Level "ERROR"
                if ($_.Exception.InnerException) {
                    Write-Log "  Inner exception: $($_.Exception.InnerException.Message)" -Level "ERROR"
                }
                Write-Log "  Stack trace: $($_.ScriptStackTrace)" -Level "ERROR"
                Write-Log "  --- Troubleshooting ---" -Level "ERROR"
                Write-Log "  1. The app may lack permission to enumerate lists on this site" -Level "ERROR"
                Write-Log "  2. Check if the access token has the correct audience (see DIAG output)" -Level "ERROR"
                Write-Log "  3. Verify Sites.Read.All permission with admin consent is granted" -Level "ERROR"
                throw
            }
            $listFetchDuration = ((Get-Date) - $listFetchStart).TotalSeconds
            Write-Log "  Get-PnPList completed in $([math]::Round($listFetchDuration, 2))s" -Level "INFO"
            Write-Log "  Total lists/libraries in site: $(($allLists | Measure-Object).Count)" -Level "INFO"

            # Group lists by BaseTemplate for a quick overview
            if (($allLists | Measure-Object).Count -gt 0) {
                $templateGroups = $allLists | Group-Object -Property BaseTemplate | Sort-Object Count -Descending
                Write-Log "  Lists grouped by BaseTemplate:" -Level "INFO"
                $templateGroups | ForEach-Object {
                    $templateName = switch ([int]$_.Name) {
                        100 { "Generic List" }
                        101 { "Document Library" }
                        102 { "Survey" }
                        103 { "Links" }
                        104 { "Announcements" }
                        105 { "Contacts" }
                        106 { "Calendar/Events" }
                        107 { "Tasks" }
                        108 { "Discussion Board" }
                        109 { "Picture Library" }
                        115 { "Form Library" }
                        119 { "Site Pages / Wiki" }
                        171 { "Tasks (project)" }
                        544 { "Microsoft Project Tasks" }
                        700 { "Teams Wiki" }
                        850 { "Publishing" }
                        851 { "Asset Library" }
                        default { "Unknown" }
                    }
                    Write-Log "    BaseTemplate $($_.Name) ($templateName): $($_.Count) list(s)" -Level "INFO"
                }
            }

            $allLists | ForEach-Object {
                $rootFolderUrl = try { $_.RootFolder.ServerRelativeUrl } catch { "(not loaded)" }
                Write-Log "    List: '$($_.Title)' | BaseTemplate=$($_.BaseTemplate) | Hidden=$($_.Hidden) | ItemCount=$($_.ItemCount) | RootFolder=$rootFolderUrl" -Level "INFO"
            }

            $libraries = $allLists | Where-Object {
                $_.BaseTemplate -eq 101 -and  # Document Library
                $_.Hidden -eq $false -and
                $_.Title -notin $excludeLibraries -and
                $_.Title -notlike "Preservation*"
            }

            # Log why each list was filtered out (helps diagnose empty results)
            if (($libraries | Measure-Object).Count -eq 0 -and ($allLists | Measure-Object).Count -gt 0) {
                Write-Log "  All lists filtered out - reasons:" -Level "WARNING"
                $allLists | ForEach-Object {
                    $reasons = @()
                    if ($_.BaseTemplate -ne 101) { $reasons += "not BaseTemplate 101 (got $($_.BaseTemplate))" }
                    if ($_.Hidden) { $reasons += "Hidden=true" }
                    if ($_.Title -in $excludeLibraries) { $reasons += "in exclude list" }
                    if ($_.Title -like "Preservation*") { $reasons += "Preservation*" }
                    Write-Log "    '$($_.Title)' rejected: $($reasons -join ', ')" -Level "WARNING"
                }
            }

            $libCount = ($libraries | Measure-Object).Count
            Write-Log "  Document libraries found (after exclusions): $libCount" -Level "INFO"

            if ($libCount -eq 0) {
                Write-Log "  No document libraries found in this site, skipping." -Level "WARNING"
                continue
            }

            $libIndex = 0
            foreach ($library in $libraries) {
                $libIndex++
                $libStartTime = Get-Date
                Write-Log "  [$libIndex/$libCount] Processing library: '$($library.Title)' (ItemCount: $($library.ItemCount))" -Level "INFO"

                # Get library statistics
                Write-Log "    Fetching library stats (enumerating all items with PageSize=5000)..." -Level "INFO"
                $stats = Get-LibraryStats -SiteUrl $siteUrl -LibraryName $library.Title
                $libDuration = ((Get-Date) - $libStartTime).TotalSeconds
                Write-Log "    Stats retrieved in $([math]::Round($libDuration, 1))s - Files: $($stats.FileCount), Folders: $($stats.FolderCount), Size: $([math]::Round($stats.TotalSize / 1MB, 2)) MB, Largest: $([math]::Round($stats.LargestFile / 1MB, 2)) MB" -Level "INFO"

                if ($stats.FileCount -gt 0) {
                    # Calculate priority based on size (smaller = higher priority for faster initial results)
                    $priority = switch ($stats.TotalSize) {
                        { $_ -lt 104857600 } { 10 }      # < 100 MB
                        { $_ -lt 1073741824 } { 50 }    # < 1 GB
                        { $_ -lt 10737418240 } { 100 }  # < 10 GB
                        default { 200 }                  # > 10 GB
                    }
                    Write-Log "    Assigned priority: $priority (based on size $([math]::Round($stats.TotalSize / 1GB, 2)) GB)" -Level "INFO"

                    # Create record
                    $record = @{
                        SiteUrl              = $siteRelativeUrl
                        LibraryName          = $library.Title
                        SiteTitle            = $site.Title
                        LibraryTitle         = $library.Title
                        FileCount            = $stats.FileCount
                        FolderCount          = $stats.FolderCount
                        TotalSizeBytes       = if ($stats.TotalSize) { $stats.TotalSize } else { 0 }
                        LargestFileSizeBytes = if ($stats.LargestFile) { $stats.LargestFile } else { 0 }
                        Priority             = $priority
                    }

                    # Insert into SQL
                    try {
                        Write-Log "    Upserting record into SQL MigrationControl table..." -Level "INFO"
                        Insert-ControlTableRecord -ConnectionString $sqlConnectionString -Record $record
                        $totalLibraries++
                        $totalFiles += $stats.FileCount
                        $totalSizeGB += ($stats.TotalSize / 1GB)

                        Write-Log "    SQL upsert successful - Files: $($stats.FileCount), Size: $([math]::Round($stats.TotalSize / 1GB, 2)) GB" -Level "SUCCESS"
                    }
                    catch {
                        Write-Log "    SQL upsert FAILED: $_" -Level "ERROR"
                        Write-Log "    Exception type: $($_.Exception.GetType().FullName)" -Level "ERROR"
                        Write-Log "    Connection string (redacted): Server=$SqlServerName.database.windows.net, DB=$SqlDatabaseName" -Level "ERROR"
                    }
                }
                else {
                    Write-Log "    Empty library (0 files), skipping SQL insert." -Level "INFO"
                }
            }

            $siteDuration = ((Get-Date) - $siteStartTime).TotalSeconds
            Write-Log "  Site '$siteRelativeUrl' completed in $([math]::Round($siteDuration, 1))s" -Level "SUCCESS"
        }
        catch {
            $failedSites += $siteUrl
            Write-Log "ERROR processing site $siteUrl" -Level "ERROR"
            Write-Log "  Error message: $_" -Level "ERROR"
            Write-Log "  Exception type: $($_.Exception.GetType().FullName)" -Level "ERROR"
            Write-Log "  Stack trace: $($_.ScriptStackTrace)" -Level "ERROR"
            continue
        }
    }

    # Summary
    Write-Log "========================================" -Level "INFO"
    Write-Log "ENUMERATION SUMMARY" -Level "SUCCESS"
    Write-Log "========================================" -Level "INFO"
    Write-Log "Sites Processed:     $siteCount" -Level "INFO"
    Write-Log "Sites Failed:        $($failedSites.Count)" -Level $(if ($failedSites.Count -gt 0) { "ERROR" } else { "INFO" })
    Write-Log "Libraries Added:     $totalLibraries" -Level "INFO"
    Write-Log "Total Files:         $totalFiles" -Level "INFO"
    Write-Log "Total Size:          $([math]::Round($totalSizeGB, 2)) GB ($([math]::Round($totalSizeGB / 1024, 2)) TB)" -Level "INFO"
    if ($failedSites.Count -gt 0) {
        Write-Log "Failed sites:" -Level "ERROR"
        $failedSites | ForEach-Object { Write-Log "  - $_" -Level "ERROR" }
    }
    Write-Log "========================================" -Level "INFO"

    Write-Log "Control table population completed!" -Level "SUCCESS"
}
catch {
    Write-Log "FATAL ERROR: $_" -Level "ERROR"
    Write-Log "Exception type: $($_.Exception.GetType().FullName)" -Level "ERROR"
    Write-Log "Exception message: $($_.Exception.Message)" -Level "ERROR"
    Write-Log "Stack trace: $($_.ScriptStackTrace)" -Level "ERROR"
    if ($_.Exception.InnerException) {
        Write-Log "Inner exception: $($_.Exception.InnerException.Message)" -Level "ERROR"
        Write-Log "Inner exception type: $($_.Exception.InnerException.GetType().FullName)" -Level "ERROR"
    }
    exit 1
}
finally {
    Write-Log "Cleaning up PnP connection..." -Level "INFO"
    Disconnect-PnPOnline -ErrorAction SilentlyContinue
    Write-Log "Done." -Level "INFO"
}
#endregion
