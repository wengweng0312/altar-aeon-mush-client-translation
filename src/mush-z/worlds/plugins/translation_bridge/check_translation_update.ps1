[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$VersionFile,
    [Parameter(Mandatory = $true)][string]$StatusFile,
    [string]$ManifestUrl = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if ([string]::IsNullOrWhiteSpace($ManifestUrl)) {
    $repositoryFile = Join-Path $PSScriptRoot "release_repository.txt"
    $repository = if (Test-Path -LiteralPath $repositoryFile) {
        (Get-Content -LiteralPath $repositoryFile -Raw -Encoding UTF8).Trim()
    } else {
        "wengweng0312/altar-aeon-mush-client-translation"
    }
    if ($repository -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') {
        throw "Invalid release repository configuration."
    }
    $ManifestUrl = "https://github.com/$repository/releases/latest/download/update_manifest.json"
}

function Convert-Version([string]$value) {
    $clean = $value.Trim().TrimStart("v")
    $parts = $clean.Split("-", 2)
    $core = $parts[0].Split(".")
    if ($core.Count -ne 3) { throw "invalid version" }
    return [pscustomobject]@{
        Major = [int]$core[0]
        Minor = [int]$core[1]
        Patch = [int]$core[2]
        Pre = if ($parts.Count -gt 1) { $parts[1] } else { "" }
    }
}

function Test-Newer([string]$remoteValue, [string]$localValue) {
    $remote = Convert-Version $remoteValue
    $local = Convert-Version $localValue
    foreach ($name in @("Major", "Minor", "Patch")) {
        if ($remote.$name -gt $local.$name) { return $true }
        if ($remote.$name -lt $local.$name) { return $false }
    }
    if ($remote.Pre -eq $local.Pre) { return $false }
    if ([string]::IsNullOrEmpty($remote.Pre)) { return $true }
    if ([string]::IsNullOrEmpty($local.Pre)) { return $false }
    return [string]::Compare($remote.Pre, $local.Pre, $true) -gt 0
}

function Write-Result([string]$status, [string]$version = "", [string]$url = "") {
    $parent = Split-Path -Parent $StatusFile
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    $temporary = $StatusFile + ".tmp"
    @(
        "status=" + $status
        "version=" + $version
        "url=" + $url
    ) | Set-Content -LiteralPath $temporary -Encoding ASCII
    Move-Item -LiteralPath $temporary -Destination $StatusFile -Force
}

try {
    $local = Get-Content -LiteralPath $VersionFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $headers = @{ "User-Agent" = "Mush-Z-Translation-Update-Check" }
    $manifest = Invoke-RestMethod -Uri $ManifestUrl -Headers $headers -TimeoutSec 8
    if ($manifest.schema_version -ne 1 -or -not $manifest.published) {
        Write-Result "current" ([string]$local.version)
        exit 0
    }
    if (Test-Newer ([string]$manifest.version) ([string]$local.version)) {
        Write-Result "update" ([string]$manifest.version) ([string]$manifest.release_notes_url)
    } else {
        Write-Result "current" ([string]$local.version)
    }
    exit 0
}
catch {
    Write-Result "error"
    exit 0
}
