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

# Build SQL connection string (using Azure AD authentication)
$sqlConnectionString = "Server=tcp:$SqlServerName.database.windows.net,1433;Initial Catalog=$SqlDatabaseName;Authentication=Active Directory Integrated;Encrypt=True;TrustServerCertificate=False;Connection Timeout=30;"
Write-Log "SQL connection string built (server: $SqlServerName.database.windows.net, db: $SqlDatabaseName, auth: AD Integrated)" -Level "INFO"

try {
    # Connect to SharePoint Admin Center
    $adminUrl = $SharePointTenantUrl -replace ".sharepoint.com", "-admin.sharepoint.com"
    Write-Log "Connecting to SharePoint Admin Center: $adminUrl" -Level "INFO"

    if ($ClientId -and $CertificateThumbprint) {
        Write-Log "Auth: Certificate-based (ClientId: $ClientId, Thumbprint: $CertificateThumbprint)" -Level "INFO"
        $openIdUrl = "https://login.microsoftonline.com/$($SharePointTenantUrl.Split('/')[2].Split('.')[0]).onmicrosoft.com/.well-known/openid_configuration"
        Write-Log "Resolving tenant ID from: $openIdUrl" -Level "INFO"
        $tenantId = (Invoke-RestMethod $openIdUrl).token_endpoint.Split('/')[3]
        Write-Log "Resolved tenant ID: $tenantId" -Level "INFO"
        Write-Log "Calling Connect-PnPOnline with certificate auth..." -Level "INFO"
        Connect-PnPOnline -Url $adminUrl -ClientId $ClientId -Thumbprint $CertificateThumbprint -Tenant $tenantId
    }
    elseif ($ClientId) {
        Write-Log "Auth: Interactive with ClientId: $ClientId" -Level "INFO"
        Write-Log "Calling Connect-PnPOnline -Interactive -ClientId $ClientId -Url $adminUrl" -Level "INFO"
        Write-Log "A browser window should open for authentication..." -Level "INFO"
        Connect-PnPOnline -Url $adminUrl -Interactive -ClientId $ClientId
    }
    else {
        Write-Log "No -ClientId provided. PnP PowerShell requires a registered Entra ID App ClientId for interactive auth." -Level "ERROR"
        Write-Log "Either:" -Level "ERROR"
        Write-Log "  1. Pass -ClientId with your own Entra ID app registration" -Level "ERROR"
        Write-Log "  2. Use the PnP multi-tenant app: -ClientId '31359c7f-bd7e-475c-86db-fdb8c937548e'" -Level "ERROR"
        Write-Log "     (requires admin consent via Register-PnPManagementShellAccess)" -Level "ERROR"
        throw "ClientId is required for PnP PowerShell interactive authentication."
    }

    Write-Log "Connected to SharePoint Admin Center successfully!" -Level "SUCCESS"

    # Verify connection
    try {
        $ctx = Get-PnPContext
        Write-Log "PnP context verified - URL: $($ctx.Url)" -Level "SUCCESS"
    }
    catch {
        Write-Log "Warning: Could not verify PnP context: $_" -Level "WARNING"
    }

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
        $allSites = Get-PnPTenantSite -Filter "Url -like '$SiteFilter'"
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
            if ($ClientId -and $CertificateThumbprint) {
                Connect-PnPOnline -Url $siteUrl -ClientId $ClientId -Thumbprint $CertificateThumbprint -Tenant $tenantId
            }
            else {
                Connect-PnPOnline -Url $siteUrl -Interactive -ClientId $ClientId
            }
            Write-Log "  Connected to site successfully." -Level "SUCCESS"

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
            $allLists = Get-PnPList
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
