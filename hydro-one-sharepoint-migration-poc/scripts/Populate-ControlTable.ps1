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

.PARAMETER SqlUsername
    Optional SQL Server username for SQL authentication (instead of AD Integrated).
    Use this when AD Integrated auth fails due to ADFS/federation issues.

.PARAMETER SqlPassword
    Optional SQL Server password (SecureString) for SQL authentication.
    If SqlUsername is provided without SqlPassword, you will be prompted.

.EXAMPLE
    .\Populate-ControlTable.ps1 -SharePointTenantUrl "https://hydroone.sharepoint.com" `
        -SqlServerName "sql-hydroone-migration-dev" -SqlDatabaseName "MigrationControl" `
        -ClientId "your-entra-app-client-id"

.EXAMPLE
    # Using SQL authentication instead of AD Integrated:
    .\Populate-ControlTable.ps1 -SharePointTenantUrl "https://hydroone.sharepoint.com" `
        -SqlServerName "sql-hydroone-migration-dev" -SqlDatabaseName "MigrationControl" `
        -ClientId "your-entra-app-client-id" -CertificateThumbprint "ABC123..." `
        -SpecificSites @("/sites/MySite") `
        -SqlUsername "sqladmin" -SqlPassword (ConvertTo-SecureString "YourPassword" -AsPlainText -Force)

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
    [string]$CertificateThumbprint,

    [Parameter(Mandatory = $false)]
    [string]$SqlUsername,

    [Parameter(Mandatory = $false)]
    [securestring]$SqlPassword
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

# Generate a unique log file path for this run
$script:LogFilePath = Join-Path (Get-Location) "Populate-ControlTable_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"
    $color = switch ($Level) {
        "INFO"    { "White" }
        "SUCCESS" { "Green" }
        "WARNING" { "Yellow" }
        "ERROR"   { "Red" }
        "DEBUG"   { "DarkGray" }
        default   { "White" }
    }
    $logLine = "[$timestamp] [$Level] $Message"
    Write-Host $logLine -ForegroundColor $color
    # Also write to log file for later analysis
    try { $logLine | Out-File -Append -FilePath $script:LogFilePath -Encoding UTF8 } catch {}
}

function Write-ExceptionDetail {
    param($ErrorRecord, [string]$Prefix = "")
    Write-Log "${Prefix}Exception type: $($ErrorRecord.Exception.GetType().FullName)" -Level "ERROR"
    Write-Log "${Prefix}Exception message: $($ErrorRecord.Exception.Message)" -Level "ERROR"
    Write-Log "${Prefix}Stack trace: $($ErrorRecord.ScriptStackTrace)" -Level "ERROR"
    if ($ErrorRecord.Exception.InnerException) {
        Write-Log "${Prefix}Inner exception type: $($ErrorRecord.Exception.InnerException.GetType().FullName)" -Level "ERROR"
        Write-Log "${Prefix}Inner exception message: $($ErrorRecord.Exception.InnerException.Message)" -Level "ERROR"
        if ($ErrorRecord.Exception.InnerException.InnerException) {
            Write-Log "${Prefix}Inner inner exception type: $($ErrorRecord.Exception.InnerException.InnerException.GetType().FullName)" -Level "ERROR"
            Write-Log "${Prefix}Inner inner exception message: $($ErrorRecord.Exception.InnerException.InnerException.Message)" -Level "ERROR"
        }
    }
    # For HTTP/web exceptions, extract response body
    if ($ErrorRecord.Exception -is [System.Net.WebException] -and $ErrorRecord.Exception.Response) {
        try {
            $stream = $ErrorRecord.Exception.Response.GetResponseStream()
            $reader = New-Object System.IO.StreamReader($stream)
            $body = $reader.ReadToEnd()
            Write-Log "${Prefix}HTTP Response Status: $($ErrorRecord.Exception.Response.StatusCode) ($($ErrorRecord.Exception.Response.StatusDescription))" -Level "ERROR"
            Write-Log "${Prefix}HTTP Response Body: $body" -Level "ERROR"
            $reader.Close()
            $stream.Close()
        }
        catch { Write-Log "${Prefix}(could not read HTTP response body)" -Level "DEBUG" }
    }
    # For SqlException, extract additional SQL details
    if ($ErrorRecord.Exception -is [Microsoft.Data.SqlClient.SqlException]) {
        $sqlEx = $ErrorRecord.Exception
        Write-Log "${Prefix}SQL Error Number: $($sqlEx.Number)" -Level "ERROR"
        Write-Log "${Prefix}SQL Error State: $($sqlEx.State)" -Level "ERROR"
        Write-Log "${Prefix}SQL Error Class: $($sqlEx.Class)" -Level "ERROR"
        Write-Log "${Prefix}SQL Server: $($sqlEx.Server)" -Level "ERROR"
        Write-Log "${Prefix}SQL Procedure: $($sqlEx.Procedure)" -Level "ERROR"
        Write-Log "${Prefix}SQL Line: $($sqlEx.LineNumber)" -Level "ERROR"
        foreach ($sqlError in $sqlEx.Errors) {
            Write-Log "${Prefix}  SQL Error Detail: [$($sqlError.Number)] $($sqlError.Message) (State=$($sqlError.State), Class=$($sqlError.Class), Server=$($sqlError.Server), Procedure=$($sqlError.Procedure), Line=$($sqlError.LineNumber))" -Level "ERROR"
        }
    }
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
$scriptStartTime = Get-Date
Write-Log "========================================" -Level "INFO"
Write-Log "SharePoint Site Enumeration and Control Table Population" -Level "INFO"
Write-Log "Script started at: $($scriptStartTime.ToString('yyyy-MM-dd HH:mm:ss.fff'))" -Level "INFO"
Write-Log "Log file: $script:LogFilePath" -Level "INFO"
Write-Log "========================================" -Level "INFO"

# Log environment details for troubleshooting
Write-Log "" -Level "INFO"
Write-Log "=== ENVIRONMENT DIAGNOSTICS ===" -Level "INFO"
Write-Log "PowerShell Version: $($PSVersionTable.PSVersion) ($($PSVersionTable.PSEdition))" -Level "INFO"
Write-Log "OS: $([System.Runtime.InteropServices.RuntimeInformation]::OSDescription)" -Level "INFO"
Write-Log ".NET Runtime: $([System.Runtime.InteropServices.RuntimeInformation]::FrameworkDescription)" -Level "INFO"
Write-Log "Running as: $env:USERNAME on $env:COMPUTERNAME" -Level "INFO"
Write-Log "Working directory: $(Get-Location)" -Level "INFO"
Write-Log "User domain: $env:USERDOMAIN" -Level "INFO"
Write-Log "User profile: $env:USERPROFILE" -Level "INFO"
Write-Log "Temp path: $([System.IO.Path]::GetTempPath())" -Level "INFO"

# Network diagnostics
Write-Log "" -Level "INFO"
Write-Log "=== NETWORK DIAGNOSTICS ===" -Level "INFO"
try {
    $localIPs = [System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) | Where-Object { $_.AddressFamily -eq 'InterNetwork' }
    Write-Log "Local IP addresses: $($localIPs.IPAddressToString -join ', ')" -Level "INFO"
}
catch { Write-Log "Could not resolve local IP: $_" -Level "DEBUG" }

# Test internet connectivity
Write-Log "Testing outbound HTTPS connectivity..." -Level "INFO"
$connectivityTargets = @(
    @{ Name = "Microsoft Login (OAuth)"; Url = "https://login.microsoftonline.com" },
    @{ Name = "Microsoft Graph API";    Url = "https://graph.microsoft.com" },
    @{ Name = "SharePoint Online";      Url = $SharePointTenantUrl }
)
foreach ($target in $connectivityTargets) {
    try {
        $response = Invoke-WebRequest -Uri $target.Url -Method Head -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop
        Write-Log "  $($target.Name) ($($target.Url)): REACHABLE (HTTP $($response.StatusCode))" -Level "SUCCESS"
    }
    catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        if ($statusCode) {
            Write-Log "  $($target.Name) ($($target.Url)): HTTP $statusCode (server reachable, returned error - this may be OK)" -Level "WARNING"
        }
        else {
            Write-Log "  $($target.Name) ($($target.Url)): UNREACHABLE - $($_.Exception.Message)" -Level "ERROR"
        }
    }
}

# Check Azure CLI login context (helps diagnose AD Integrated auth issues for SQL)
Write-Log "" -Level "INFO"
Write-Log "=== AZURE CLI CONTEXT ===" -Level "INFO"
try {
    $azAccount = az account show 2>&1 | ConvertFrom-Json -ErrorAction Stop
    Write-Log "Azure CLI logged in: YES" -Level "SUCCESS"
    Write-Log "  Subscription: $($azAccount.name) ($($azAccount.id))" -Level "INFO"
    Write-Log "  Tenant: $($azAccount.tenantId)" -Level "INFO"
    Write-Log "  User: $($azAccount.user.name) (type: $($azAccount.user.type))" -Level "INFO"
    Write-Log "  Environment: $($azAccount.environmentName)" -Level "INFO"
    Write-Log "  Home tenant: $($azAccount.homeTenantId)" -Level "INFO"
}
catch {
    Write-Log "Azure CLI: NOT LOGGED IN or az not installed" -Level "WARNING"
    Write-Log "  This affects SQL 'Active Directory Integrated' auth. Run: az login" -Level "WARNING"
    Write-Log "  Error: $_" -Level "DEBUG"
}

Write-Log "" -Level "INFO"
Write-Log "=== SCRIPT PARAMETERS ===" -Level "INFO"
Write-Log "SharePoint Tenant: $SharePointTenantUrl" -Level "INFO"
Write-Log "SQL Server: $SqlServerName" -Level "INFO"
Write-Log "SQL Database: $SqlDatabaseName" -Level "INFO"
Write-Log "Site Filter: $SiteFilter" -Level "INFO"
Write-Log "SpecificSites count: $($SpecificSites.Count)" -Level "INFO"
if ($SpecificSites.Count -gt 0) { Write-Log "Specific Sites: $($SpecificSites -join ', ')" -Level "INFO" }
Write-Log "ExcludeSites count: $($ExcludeSites.Count)" -Level "INFO"
if ($ExcludeSites.Count -gt 0) { Write-Log "Excluded Sites: $($ExcludeSites -join ', ')" -Level "INFO" }
Write-Log "Auth Mode: $(if ($ClientId -and $CertificateThumbprint) { 'Certificate' } elseif ($ClientId) { 'Interactive with ClientId' } else { 'No ClientId (will fail)' })" -Level "INFO"
Write-Log "ClientId: $(if ($ClientId) { $ClientId } else { '(not provided)' })" -Level "INFO"
Write-Log "CertificateThumbprint: $(if ($CertificateThumbprint) { $CertificateThumbprint } else { '(not provided)' })" -Level "INFO"
Write-Log "UseInteractiveAuth: $UseInteractiveAuth" -Level "INFO"
Write-Log "SqlUsername: $(if ($SqlUsername) { $SqlUsername } else { '(not provided - using AD Integrated)' })" -Level "INFO"
Write-Log "SqlPassword: $(if ($SqlPassword) { '(provided)' } else { '(not provided)' })" -Level "INFO"
Write-Log "========================================" -Level "INFO"

# Check PowerShell version compatibility
if ($PSVersionTable.PSVersion.Major -lt 7) {
    Write-Log "WARNING: PnP.PowerShell 2.x requires PowerShell 7.2+. You are running PowerShell $($PSVersionTable.PSVersion)." -Level "ERROR"
    Write-Log "Please install PowerShell 7: winget install Microsoft.PowerShell" -Level "ERROR"
    Write-Log "Then re-run this script using 'pwsh' instead of 'powershell'." -Level "ERROR"
    throw "PowerShell 7.2+ is required. Current version: $($PSVersionTable.PSVersion)"
}

# Check for required modules
Write-Log "" -Level "INFO"
Write-Log "=== MODULE VALIDATION ===" -Level "INFO"
$requiredModules = @("PnP.PowerShell", "SqlServer")
foreach ($module in $requiredModules) {
    if (-not (Get-Module -ListAvailable -Name $module)) {
        Write-Log "Module '$module' not found. Installing..." -Level "WARNING"
        try {
            Install-Module -Name $module -Force -AllowClobber -Scope CurrentUser -ErrorAction Stop
            Write-Log "Module '$module' installed successfully." -Level "SUCCESS"
        }
        catch {
            Write-Log "FAILED to install module '$module': $_" -Level "ERROR"
            Write-ExceptionDetail $_
            throw
        }
    }
    else {
        $allVersions = Get-Module -ListAvailable -Name $module | Sort-Object Version -Descending
        $latestVersion = $allVersions | Select-Object -First 1
        Write-Log "Module '$module' found (v$($latestVersion.Version))" -Level "INFO"
        Write-Log "  Module path: $($latestVersion.ModuleBase)" -Level "DEBUG"
        if ($allVersions.Count -gt 1) {
            Write-Log "  Multiple versions installed: $($allVersions.Version -join ', ')" -Level "DEBUG"
        }
    }
    Write-Log "Importing module: $module" -Level "INFO"
    try {
        Import-Module $module -ErrorAction Stop
        $imported = Get-Module -Name $module
        Write-Log "Module '$module' imported successfully (v$($imported.Version))" -Level "SUCCESS"
    }
    catch {
        Write-Log "FAILED to import module '$module': $_" -Level "ERROR"
        Write-ExceptionDetail $_
        throw
    }
}
Write-Log "=== END MODULE VALIDATION ===" -Level "INFO"

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

# Build SQL connection string
$sqlFqdn = "$SqlServerName.database.windows.net"
if ($SqlUsername) {
    # SQL Authentication (username/password)
    if (-not $SqlPassword) {
        Write-Log "SqlUsername provided but SqlPassword is missing. Prompting..." -Level "WARNING"
        $SqlPassword = Read-Host -Prompt "Enter SQL password for '$SqlUsername'" -AsSecureString
    }
    $plainPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SqlPassword)
    )
    $sqlConnectionString = "Server=tcp:$sqlFqdn,1433;Initial Catalog=$SqlDatabaseName;User ID=$SqlUsername;Password=$plainPassword;Encrypt=True;TrustServerCertificate=False;Connection Timeout=30;"
    $sqlAuthMode = "SQL Authentication (user: $SqlUsername)"
    Write-Log "SQL connection string built (server: $sqlFqdn, db: $SqlDatabaseName, auth: SQL Auth, user: $SqlUsername)" -Level "INFO"
}
else {
    # Azure AD Integrated (default)
    $sqlConnectionString = "Server=tcp:$sqlFqdn,1433;Initial Catalog=$SqlDatabaseName;Authentication=Active Directory Integrated;Encrypt=True;TrustServerCertificate=False;Connection Timeout=30;"
    $sqlAuthMode = "Active Directory Integrated"
    Write-Log "SQL connection string built (server: $sqlFqdn, db: $SqlDatabaseName, auth: AD Integrated)" -Level "INFO"
    Write-Log "  TIP: If AD Integrated auth fails (ADFS/federated issues), use -SqlUsername and -SqlPassword for SQL auth instead" -Level "INFO"
}

# === SQL PRE-FLIGHT CHECK ===
Write-Log "========================================" -Level "INFO"
Write-Log "SQL CONNECTIVITY PRE-FLIGHT CHECK" -Level "INFO"
Write-Log "========================================" -Level "INFO"

# Step 1: DNS resolution
Write-Log "[SQL-DIAG] Step 1/6: DNS resolution for $sqlFqdn" -Level "INFO"
try {
    $dnsStart = Get-Date
    $dnsResult = [System.Net.Dns]::GetHostAddresses($sqlFqdn)
    $dnsDuration = ((Get-Date) - $dnsStart).TotalMilliseconds
    Write-Log "[SQL-DIAG]   PASS - Resolved to: $($dnsResult.IPAddressToString -join ', ') (took $([math]::Round($dnsDuration))ms)" -Level "SUCCESS"
    foreach ($ip in $dnsResult) {
        Write-Log "[SQL-DIAG]   IP: $($ip.IPAddressToString) (AddressFamily: $($ip.AddressFamily))" -Level "DEBUG"
    }

    # Also check privatelink FQDN to detect private endpoint configuration
    $privateFqdn = "$SqlServerName.privatelink.database.windows.net"
    Write-Log "[SQL-DIAG]   Checking private endpoint DNS: $privateFqdn" -Level "DEBUG"
    try {
        $privateDns = [System.Net.Dns]::GetHostAddresses($privateFqdn)
        Write-Log "[SQL-DIAG]   Private endpoint DNS resolves to: $($privateDns.IPAddressToString -join ', ')" -Level "INFO"
        Write-Log "[SQL-DIAG]   Private endpoint appears to be configured." -Level "INFO"
    }
    catch {
        Write-Log "[SQL-DIAG]   Private endpoint DNS does not resolve (not configured or using public access)" -Level "DEBUG"
    }
}
catch {
    Write-Log "[SQL-DIAG]   FAIL - Cannot resolve hostname: $sqlFqdn" -Level "ERROR"
    Write-ExceptionDetail $_ "  [SQL-DIAG]   "
    Write-Log "[SQL-DIAG]   --- Troubleshooting ---" -Level "ERROR"
    Write-Log "[SQL-DIAG]   1. Verify the SQL server name is correct: '$SqlServerName'" -Level "ERROR"
    Write-Log "[SQL-DIAG]   2. The full FQDN being resolved is: $sqlFqdn" -Level "ERROR"
    Write-Log "[SQL-DIAG]   3. Check if the server exists in Azure:" -Level "ERROR"
    Write-Log "[SQL-DIAG]      az sql server list --query ""[?name=='$SqlServerName'].[name,fullyQualifiedDomainName,state]"" -o table" -Level "ERROR"
    Write-Log "[SQL-DIAG]   4. If using private endpoints, check private DNS zone configuration" -Level "ERROR"
    Write-Log "[SQL-DIAG]   5. Try manual DNS lookup: nslookup $sqlFqdn" -Level "ERROR"
    Write-Log "[SQL-DIAG]   6. Try manual DNS lookup: Resolve-DnsName $sqlFqdn" -Level "ERROR"
    Write-Log "[SQL-DIAG]   7. Check your DNS server: (Get-DnsClientServerAddress -AddressFamily IPv4).ServerAddresses" -Level "ERROR"
    try {
        $dnsServers = (Get-DnsClientServerAddress -AddressFamily IPv4 -ErrorAction Stop).ServerAddresses | Select-Object -Unique
        Write-Log "[SQL-DIAG]   Current DNS servers: $($dnsServers -join ', ')" -Level "ERROR"
    }
    catch { Write-Log "[SQL-DIAG]   (could not query DNS server configuration)" -Level "DEBUG" }
    throw "SQL Server DNS resolution failed for '$sqlFqdn'. Verify the -SqlServerName parameter is correct."
}

# Step 2: TCP connectivity
Write-Log "[SQL-DIAG] Step 2/6: TCP connectivity to ${sqlFqdn}:1433" -Level "INFO"
try {
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    $tcpStart = Get-Date
    $connectTask = $tcpClient.ConnectAsync($sqlFqdn, 1433)
    if ($connectTask.Wait(10000)) {
        $tcpDuration = ((Get-Date) - $tcpStart).TotalMilliseconds
        Write-Log "[SQL-DIAG]   PASS - TCP port 1433 is reachable (took $([math]::Round($tcpDuration))ms)" -Level "SUCCESS"
        Write-Log "[SQL-DIAG]   Local endpoint: $($tcpClient.Client.LocalEndPoint)" -Level "DEBUG"
        Write-Log "[SQL-DIAG]   Remote endpoint: $($tcpClient.Client.RemoteEndPoint)" -Level "DEBUG"
    }
    else {
        Write-Log "[SQL-DIAG]   FAIL - TCP connection timed out after 10s" -Level "ERROR"
        Write-Log "[SQL-DIAG]   The DNS resolved but the port is unreachable." -Level "ERROR"
        Write-Log "[SQL-DIAG]   --- Troubleshooting ---" -Level "ERROR"
        Write-Log "[SQL-DIAG]   1. Check SQL Server firewall rules allow your IP" -Level "ERROR"
        Write-Log "[SQL-DIAG]   2. Check for AllowAzureServices firewall rule:" -Level "ERROR"
        Write-Log "[SQL-DIAG]      az sql server firewall-rule list --server $SqlServerName --resource-group <rg-name> -o table" -Level "ERROR"
        Write-Log "[SQL-DIAG]   3. If behind a corporate firewall/VPN, ensure port 1433 outbound is allowed" -Level "ERROR"
        Write-Log "[SQL-DIAG]   4. Try: Test-NetConnection $sqlFqdn -Port 1433" -Level "ERROR"
        Write-Log "[SQL-DIAG]   5. Check NSG rules if using VNet integration" -Level "ERROR"
    }
    $tcpClient.Close()
}
catch {
    Write-Log "[SQL-DIAG]   FAIL - TCP connection error" -Level "ERROR"
    Write-ExceptionDetail $_ "  [SQL-DIAG]   "
    Write-Log "[SQL-DIAG]   --- Troubleshooting ---" -Level "ERROR"
    Write-Log "[SQL-DIAG]   1. Firewall may be blocking port 1433" -Level "ERROR"
    Write-Log "[SQL-DIAG]   2. Try: Test-NetConnection $sqlFqdn -Port 1433" -Level "ERROR"
    Write-Log "[SQL-DIAG]   3. Check if VPN is required and connected" -Level "ERROR"
}

# Step 3: SQL authentication test
Write-Log "[SQL-DIAG] Step 3/6: SQL authentication and database access" -Level "INFO"
Write-Log "[SQL-DIAG]   Connection string (sanitized): Server=tcp:$sqlFqdn,1433; Database=$SqlDatabaseName; Auth=AD Integrated; Encrypt=True" -Level "INFO"
try {
    $sqlAuthStart = Get-Date
    $testResult = Invoke-Sqlcmd -ConnectionString $sqlConnectionString -Query @"
        SELECT
            DB_NAME() AS DatabaseName,
            SUSER_SNAME() AS LoginName,
            SYSTEM_USER AS SystemUser,
            ORIGINAL_LOGIN() AS OriginalLogin,
            USER_NAME() AS DatabaseUser,
            GETUTCDATE() AS ServerTimeUTC,
            SERVERPROPERTY('ProductVersion') AS SqlVersion,
            SERVERPROPERTY('Edition') AS SqlEdition,
            SERVERPROPERTY('ServerName') AS ServerName,
            SERVERPROPERTY('EngineEdition') AS EngineEdition,
            CONNECTIONPROPERTY('client_net_address') AS ClientIP,
            CONNECTIONPROPERTY('protocol_type') AS ProtocolType,
            CONNECTIONPROPERTY('auth_scheme') AS AuthScheme,
            CONNECTIONPROPERTY('net_transport') AS NetTransport
"@ -ErrorAction Stop
    $sqlAuthDuration = ((Get-Date) - $sqlAuthStart).TotalSeconds
    Write-Log "[SQL-DIAG]   PASS - Connected to database: $($testResult.DatabaseName) (took $([math]::Round($sqlAuthDuration, 2))s)" -Level "SUCCESS"
    Write-Log "[SQL-DIAG]   Login: $($testResult.LoginName)" -Level "INFO"
    Write-Log "[SQL-DIAG]   System User: $($testResult.SystemUser)" -Level "INFO"
    Write-Log "[SQL-DIAG]   Original Login: $($testResult.OriginalLogin)" -Level "INFO"
    Write-Log "[SQL-DIAG]   Database User: $($testResult.DatabaseUser)" -Level "INFO"
    Write-Log "[SQL-DIAG]   Server Time (UTC): $($testResult.ServerTimeUTC)" -Level "INFO"
    Write-Log "[SQL-DIAG]   SQL Version: $($testResult.SqlVersion) ($($testResult.SqlEdition))" -Level "INFO"
    Write-Log "[SQL-DIAG]   Server Name: $($testResult.ServerName)" -Level "INFO"
    Write-Log "[SQL-DIAG]   Client IP: $($testResult.ClientIP)" -Level "INFO"
    Write-Log "[SQL-DIAG]   Auth Scheme: $($testResult.AuthScheme)" -Level "INFO"
    Write-Log "[SQL-DIAG]   Protocol: $($testResult.ProtocolType) ($($testResult.NetTransport))" -Level "INFO"
}
catch {
    Write-Log "[SQL-DIAG]   FAIL - SQL authentication failed" -Level "ERROR"
    Write-ExceptionDetail $_ "  [SQL-DIAG]   "
    if ($_.Exception.Message -like "*Login failed*") {
        Write-Log "[SQL-DIAG]   --- Authentication Troubleshooting ---" -Level "ERROR"
        Write-Log "[SQL-DIAG]   1. Check your Azure AD login: az account show" -Level "ERROR"
        Write-Log "[SQL-DIAG]   2. Verify Azure AD admin is set on the SQL server:" -Level "ERROR"
        Write-Log "[SQL-DIAG]      az sql server ad-admin list --server $SqlServerName --resource-group <rg-name>" -Level "ERROR"
        Write-Log "[SQL-DIAG]   3. Verify your user exists in the database:" -Level "ERROR"
        Write-Log "[SQL-DIAG]      SELECT name, type_desc FROM sys.database_principals WHERE type IN ('E','X')" -Level "ERROR"
        Write-Log "[SQL-DIAG]   4. If using Managed Identity, ensure the correct identity is assigned" -Level "ERROR"
    }
    elseif ($_.Exception.Message -like "*Cannot open database*") {
        Write-Log "[SQL-DIAG]   Database '$SqlDatabaseName' does not exist or user lacks access." -Level "ERROR"
        Write-Log "[SQL-DIAG]   List databases: az sql db list --server $SqlServerName --resource-group <rg-name> -o table" -Level "ERROR"
    }
    elseif ($_.Exception.Message -like "*token*" -or $_.Exception.Message -like "*AADSTS*") {
        Write-Log "[SQL-DIAG]   Azure AD token acquisition failed." -Level "ERROR"
        Write-Log "[SQL-DIAG]   1. Re-authenticate: az login --tenant <tenant-id>" -Level "ERROR"
        Write-Log "[SQL-DIAG]   2. Clear token cache: az account clear && az login" -Level "ERROR"
    }
    throw "SQL pre-flight check failed. Fix the SQL connection before proceeding."
}

# Step 4: Verify MigrationControl table exists
Write-Log "[SQL-DIAG] Step 4/6: Verify MigrationControl table exists" -Level "INFO"
try {
    $tableCheck = Invoke-Sqlcmd -ConnectionString $sqlConnectionString -Query @"
        SELECT TABLE_SCHEMA, TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_NAME = 'MigrationControl'
"@ -ErrorAction Stop
    if ($tableCheck) {
        Write-Log "[SQL-DIAG]   PASS - Table found: $($tableCheck.TABLE_SCHEMA).$($tableCheck.TABLE_NAME)" -Level "SUCCESS"

        # Check current row count and status distribution
        $rowCount = Invoke-Sqlcmd -ConnectionString $sqlConnectionString -Query "SELECT COUNT(*) AS RowCount FROM dbo.MigrationControl" -ErrorAction Stop
        Write-Log "[SQL-DIAG]   Current row count: $($rowCount.RowCount)" -Level "INFO"

        if ($rowCount.RowCount -gt 0) {
            $statusDist = Invoke-Sqlcmd -ConnectionString $sqlConnectionString -Query "SELECT Status, COUNT(*) AS Cnt FROM dbo.MigrationControl GROUP BY Status ORDER BY Cnt DESC" -ErrorAction Stop
            Write-Log "[SQL-DIAG]   Status distribution:" -Level "INFO"
            foreach ($row in $statusDist) {
                Write-Log "[SQL-DIAG]     $($row.Status): $($row.Cnt)" -Level "INFO"
            }
        }

        # Log table columns for schema verification
        $columns = Invoke-Sqlcmd -ConnectionString $sqlConnectionString -Query @"
            SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'MigrationControl' AND TABLE_SCHEMA = 'dbo'
            ORDER BY ORDINAL_POSITION
"@ -ErrorAction Stop
        Write-Log "[SQL-DIAG]   Table schema ($($columns.Count) columns):" -Level "DEBUG"
        foreach ($col in $columns) {
            $typeStr = $col.DATA_TYPE
            if ($col.CHARACTER_MAXIMUM_LENGTH -and $col.CHARACTER_MAXIMUM_LENGTH -gt 0) { $typeStr += "($($col.CHARACTER_MAXIMUM_LENGTH))" }
            Write-Log "[SQL-DIAG]     $($col.COLUMN_NAME) ($typeStr, nullable=$($col.IS_NULLABLE))" -Level "DEBUG"
        }
    }
    else {
        Write-Log "[SQL-DIAG]   FAIL - Table 'MigrationControl' not found in database '$SqlDatabaseName'" -Level "ERROR"
        # List what tables do exist
        $existingTables = Invoke-Sqlcmd -ConnectionString $sqlConnectionString -Query "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES ORDER BY TABLE_SCHEMA, TABLE_NAME" -ErrorAction SilentlyContinue
        if ($existingTables) {
            Write-Log "[SQL-DIAG]   Tables that DO exist in the database:" -Level "ERROR"
            foreach ($t in $existingTables) { Write-Log "[SQL-DIAG]     $($t.TABLE_SCHEMA).$($t.TABLE_NAME)" -Level "ERROR" }
        }
        else {
            Write-Log "[SQL-DIAG]   Database appears to have NO tables at all." -Level "ERROR"
        }
        Write-Log "[SQL-DIAG]   Run the DDL script first:" -Level "ERROR"
        Write-Log "[SQL-DIAG]     sqlcmd -S $sqlFqdn -d $SqlDatabaseName -i sql/create_control_table.sql -G" -Level "ERROR"
        throw "MigrationControl table does not exist."
    }
}
catch [Microsoft.Data.SqlClient.SqlException] {
    Write-Log "[SQL-DIAG]   FAIL - Could not query table metadata" -Level "ERROR"
    Write-ExceptionDetail $_ "  [SQL-DIAG]   "
    throw
}

# Step 5: Test write permissions
Write-Log "[SQL-DIAG] Step 5/6: Verify write permissions (SELECT/INSERT/UPDATE/EXECUTE)" -Level "INFO"
try {
    $permCheck = Invoke-Sqlcmd -ConnectionString $sqlConnectionString -Query @"
        SELECT
            HAS_PERMS_BY_NAME('dbo.MigrationControl', 'OBJECT', 'SELECT') AS CanSelect,
            HAS_PERMS_BY_NAME('dbo.MigrationControl', 'OBJECT', 'INSERT') AS CanInsert,
            HAS_PERMS_BY_NAME('dbo.MigrationControl', 'OBJECT', 'UPDATE') AS CanUpdate,
            HAS_PERMS_BY_NAME('dbo.MigrationControl', 'OBJECT', 'DELETE') AS CanDelete,
            IS_MEMBER('db_datareader') AS IsDataReader,
            IS_MEMBER('db_datawriter') AS IsDataWriter,
            IS_MEMBER('db_owner') AS IsDbOwner
"@ -ErrorAction Stop
    Write-Log "[SQL-DIAG]   Object permissions on dbo.MigrationControl:" -Level "INFO"
    Write-Log "[SQL-DIAG]     SELECT: $(if ($permCheck.CanSelect -eq 1) { 'GRANTED' } else { 'DENIED' })" -Level $(if ($permCheck.CanSelect -eq 1) { "SUCCESS" } else { "ERROR" })
    Write-Log "[SQL-DIAG]     INSERT: $(if ($permCheck.CanInsert -eq 1) { 'GRANTED' } else { 'DENIED' })" -Level $(if ($permCheck.CanInsert -eq 1) { "SUCCESS" } else { "ERROR" })
    Write-Log "[SQL-DIAG]     UPDATE: $(if ($permCheck.CanUpdate -eq 1) { 'GRANTED' } else { 'DENIED' })" -Level $(if ($permCheck.CanUpdate -eq 1) { "SUCCESS" } else { "ERROR" })
    Write-Log "[SQL-DIAG]     DELETE: $(if ($permCheck.CanDelete -eq 1) { 'GRANTED' } else { 'DENIED' })" -Level $(if ($permCheck.CanDelete -eq 1) { "SUCCESS" } else { "ERROR" })
    Write-Log "[SQL-DIAG]   Role memberships:" -Level "INFO"
    Write-Log "[SQL-DIAG]     db_datareader: $(if ($permCheck.IsDataReader -eq 1) { 'YES' } else { 'NO' })" -Level $(if ($permCheck.IsDataReader -eq 1) { "SUCCESS" } else { "WARNING" })
    Write-Log "[SQL-DIAG]     db_datawriter: $(if ($permCheck.IsDataWriter -eq 1) { 'YES' } else { 'NO' })" -Level $(if ($permCheck.IsDataWriter -eq 1) { "SUCCESS" } else { "WARNING" })
    Write-Log "[SQL-DIAG]     db_owner:      $(if ($permCheck.IsDbOwner -eq 1) { 'YES' } else { 'NO' })" -Level "INFO"
    if ($permCheck.CanInsert -ne 1 -or $permCheck.CanUpdate -ne 1) {
        Write-Log "[SQL-DIAG]   WARNING: Missing write permissions." -Level "ERROR"
        Write-Log "[SQL-DIAG]   Fix with: ALTER ROLE db_datawriter ADD MEMBER [$(if ($testResult) { $testResult.DatabaseUser } else { 'your-user' })];" -Level "ERROR"
    }
}
catch {
    Write-Log "[SQL-DIAG]   Could not check permissions" -Level "WARNING"
    Write-ExceptionDetail $_ "  [SQL-DIAG]   "
}

# Step 6: Test upsert dry-run
Write-Log "[SQL-DIAG] Step 6/6: Dry-run INSERT/ROLLBACK test" -Level "INFO"
try {
    Invoke-Sqlcmd -ConnectionString $sqlConnectionString -Query @"
        BEGIN TRANSACTION
        INSERT INTO dbo.MigrationControl (SiteUrl, LibraryName, SiteTitle, LibraryTitle, Status, FileCount, FolderCount, TotalSizeBytes, LargestFileSizeBytes, Priority, CreatedDate, CreatedBy)
        VALUES ('__DIAG_TEST__', '__DIAG_TEST__', 'test', 'test', 'Pending', 0, 0, 0, 0, 999, GETUTCDATE(), 'DIAG')
        ROLLBACK TRANSACTION
"@ -ErrorAction Stop
    Write-Log "[SQL-DIAG]   PASS - INSERT test succeeded (rolled back, no data written)" -Level "SUCCESS"
}
catch {
    Write-Log "[SQL-DIAG]   FAIL - INSERT dry-run failed" -Level "ERROR"
    Write-ExceptionDetail $_ "  [SQL-DIAG]   "
    Write-Log "[SQL-DIAG]   This means the script will fail when trying to write migration data." -Level "ERROR"
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
                        Write-Log "    SQL upsert FAILED" -Level "ERROR"
                        Write-ExceptionDetail $_ "    "
                        Write-Log "    Connection string (redacted): Server=$sqlFqdn, DB=$SqlDatabaseName, Auth=AD Integrated" -Level "ERROR"
                        Write-Log "    --- SQL Upsert Troubleshooting ---" -Level "ERROR"
                        if ($_.Exception.Message -like "*network*" -or $_.Exception.Message -like "*not found or was not accessible*") {
                            Write-Log "    SQL server became unreachable during migration. Check network/firewall." -Level "ERROR"
                        }
                        elseif ($_.Exception.Message -like "*Login failed*" -or $_.Exception.Message -like "*authenticate*" -or $_.Exception.Message -like "*token*") {
                            Write-Log "    Authentication token may have expired. Try re-running: az login" -Level "ERROR"
                        }
                        elseif ($_.Exception.Message -like "*permission*" -or $_.Exception.Message -like "*denied*") {
                            Write-Log "    Write permission denied. Check db_datawriter role assignment." -Level "ERROR"
                        }
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
            Write-ExceptionDetail $_ "  "
            Write-Log "  --- Site Error Context ---" -Level "ERROR"
            Write-Log "  Site URL: $siteUrl" -Level "ERROR"
            Write-Log "  Site relative URL: $siteRelativeUrl" -Level "ERROR"
            Write-Log "  Site index: $siteIndex of $siteCount" -Level "ERROR"
            Write-Log "  Elapsed time for this site: $([math]::Round(((Get-Date) - $siteStartTime).TotalSeconds, 1))s" -Level "ERROR"
            Write-Log "  Continuing to next site..." -Level "WARNING"
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

    $totalDuration = ((Get-Date) - $scriptStartTime).TotalSeconds
    Write-Log "Control table population completed!" -Level "SUCCESS"
    Write-Log "Total script duration: $([math]::Round($totalDuration, 1))s ($([math]::Round($totalDuration / 60, 1)) min)" -Level "INFO"
    Write-Log "Log file saved to: $script:LogFilePath" -Level "INFO"
}
catch {
    Write-Log "========================================" -Level "ERROR"
    Write-Log "FATAL ERROR" -Level "ERROR"
    Write-Log "========================================" -Level "ERROR"
    Write-ExceptionDetail $_
    $totalDuration = ((Get-Date) - $scriptStartTime).TotalSeconds
    Write-Log "Script failed after $([math]::Round($totalDuration, 1))s" -Level "ERROR"
    Write-Log "Log file saved to: $script:LogFilePath" -Level "ERROR"
    Write-Log "Share this log file for troubleshooting." -Level "ERROR"
    exit 1
}
finally {
    Write-Log "Cleaning up PnP connection..." -Level "INFO"
    Disconnect-PnPOnline -ErrorAction SilentlyContinue
    Write-Log "Done." -Level "INFO"
    Write-Log "Full log available at: $script:LogFilePath" -Level "INFO"
}
#endregion
