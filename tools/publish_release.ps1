[CmdletBinding()]
param(
    [string]$Version = "",
    [ValidateSet("patch", "full")][string]$Mode = "patch",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Bridge = Join-Path $Root "src\mush-z\worlds\plugins\translation_bridge"

function Invoke-Checked([scriptblock]$Command, [string]$Failure) {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw $Failure }
}

function Invoke-GhCaptured([string[]]$Arguments) {
    # Windows PowerShell 5 can promote a native program's stderr to a
    # terminating NativeCommandError when ErrorActionPreference is Stop.
    # Some gh existence checks intentionally return a non-zero exit code, so
    # capture their output under a non-terminating preference and inspect the
    # exit code ourselves.
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "SilentlyContinue"
        $output = & gh @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = (($output | ForEach-Object { [string]$_ }) -join "`n").Trim()
    }
}

function Write-WorkflowFailureDiagnostics([string]$RunId, [string]$Repository, [string]$Version) {
    $temporaryRoot = if ([string]::IsNullOrWhiteSpace($env:TEMP)) {
        [System.IO.Path]::GetTempPath()
    } else {
        $env:TEMP
    }
    $logPath = Join-Path $temporaryRoot "mush-release-run-$RunId-failed.log"
    $log = Invoke-GhCaptured @("run", "view", $RunId, "--repo", $Repository, "--log-failed")
    $logText = if ($log.Output) { $log.Output + "`n" } else {
        "GitHub did not return a detailed failed-step log. gh exit code: $($log.ExitCode)`n"
    }
    [System.IO.File]::WriteAllText($logPath, $logText, [System.Text.UTF8Encoding]::new($false))

    Write-Host ""
    Write-Host "GITHUB ACTIONS FAILURE DETAILS"
    Write-Host "Run            : $RunId"
    Write-Host "Complete log   : $logPath"
    $important = @($logText -split "`r?`n" | Where-Object {
        $_ -match '(?i)Traceback|Regression tests failed|FileNotFoundError|AssertionError|FAILED|VALIDATION|##\[error\]|Process completed with exit code'
    } | Select-Object -Last 30)
    if ($important.Count -gt 0) {
        Write-Host "Important lines:"
        $important | ForEach-Object { Write-Host "  $_" }
    } else {
        Write-Host "Important lines: no recognizable error summary; inspect the complete log."
    }

    $release = Invoke-GhCaptured @("release", "view", "v$Version", "--repo", $Repository, "--json", "tagName", "--jq", ".tagName")
    $releaseExists = $release.ExitCode -eq 0
    Write-Host "Source commit  : already pushed to $Repository"
    if ($releaseExists) {
        Write-Host "GitHub release : v$Version exists; do not retry with the same version until its state is inspected."
    } else {
        Write-Host "GitHub release : v$Version was not created; the same version may be retried after fixing the error."
        Write-Host "Updater manifest: not confirmed or published by this failed run."
    }
    return [pscustomobject]@{ LogPath = $logPath; ReleaseExists = $releaseExists }
}

function Get-Repository {
    $remote = (& git -C $Root remote get-url origin).Trim()
    if ($LASTEXITCODE -ne 0 -or $remote -notmatch 'github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?$') {
        throw "The origin remote is not a recognizable GitHub repository."
    }
    return "$($Matches[1])/$($Matches[2])"
}

function Get-Python {
    $candidates = @(
        (Join-Path $Bridge "runtime\python\python.exe"),
        $env:MUSHZ_RELEASE_PYTHON,
        "python.exe"
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    foreach ($candidate in $candidates) {
        try {
            & $candidate -c "import sys; assert sys.version_info >= (3, 10)" 2>$null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        } catch {}
    }
    throw "Full packaging requires Python 3.10+ and a prepared runtime/model under the source translation_bridge folder."
}

function Normalize-Version([string]$Value) {
    $clean = $Value.Trim().TrimStart("v")
    if ($clean -notmatch '^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$') {
        throw "Version must look like 1.2.3."
    }
    return $clean
}

function Assert-RemoteBranchContained([string]$BranchName) {
    # Fetch before touching version files or creating a release commit.  The
    # release workflow commits its updater manifest back to main, so a checkout
    # that was current before the previous release can legitimately be behind.
    Invoke-Checked { git -C $Root fetch origin $BranchName } "Unable to refresh origin/$BranchName. Publishing stopped before changing any release files."
    Invoke-Checked { git -C $Root rev-parse --verify "refs/remotes/origin/$BranchName" } "Remote branch origin/$BranchName is unavailable. Publishing stopped safely."

    & git -C $Root merge-base --is-ancestor "origin/$BranchName" HEAD
    if ($LASTEXITCODE -eq 0) { return }
    if ($LASTEXITCODE -ne 1) {
        throw "Unable to compare HEAD with origin/$BranchName. Publishing stopped before changing any release files."
    }

    & git -C $Root merge-base --is-ancestor HEAD "origin/$BranchName"
    $relation = if ($LASTEXITCODE -eq 0) { "the remote branch is ahead of this checkout" } else { "the local and remote branches have diverged" }
    throw @"
Publishing stopped safely before changing the version or creating a release commit because $relation.
Your local commits were not removed or overwritten.
Synchronize the checkout first, for example:
  git fetch origin
  git rebase origin/$BranchName
If rebase reports a conflict, stop and ask Codex or another experienced Git user to resolve it; do not force push.
"@
}

Set-Location $Root
Invoke-Checked { gh auth status } "GitHub login is unavailable. Run gh auth login first."
$Repository = Get-Repository
$Account = (& gh api user --jq .login).Trim()
if ($LASTEXITCODE -ne 0) { throw "Unable to read the current GitHub account." }
$Branch = (& git -C $Root branch --show-current).Trim()
if (-not $Branch) { throw "The repository is in detached HEAD state." }
$DefaultBranch = (& gh repo view $Repository --json defaultBranchRef --jq .defaultBranchRef.name).Trim()
if ($LASTEXITCODE -ne 0 -or -not $DefaultBranch) { throw "Unable to determine the default branch." }
if ($Branch -ne $DefaultBranch) { throw "Publishing is allowed only from the default branch '$DefaultBranch'. Current branch: '$Branch'." }
Assert-RemoteBranchContained $Branch

$latestCheck = Invoke-GhCaptured @("release", "view", "--repo", $Repository, "--json", "tagName", "--jq", ".tagName")
$LatestTag = if ($latestCheck.ExitCode -eq 0) { $latestCheck.Output } else { "" }
$LatestVersion = if ($LatestTag) { $LatestTag.TrimStart("v") } else { "0.0.0" }
if (-not $Version) {
    $parts = $LatestVersion.Split(".")
    $suggested = if ($parts.Count -eq 3) {
        "$($parts[0]).$($parts[1]).$([int]$parts[2] + 1)"
    } else { "1.0.0" }
    $entered = Read-Host "Version [$suggested]"
    $Version = if ([string]::IsNullOrWhiteSpace($entered)) { $suggested } else { $entered }
}
$Version = Normalize-Version $Version

if (-not $PSBoundParameters.ContainsKey("Mode")) {
    $choice = Read-Host "Package: 1=Only Patch (recommended), 2=Only Patch + Full [1]"
    if ($choice -eq "2") { $Mode = "full" } else { $Mode = "patch" }
}

try {
    if ([version]($Version.Split("-")[0]) -le [version]($LatestVersion.Split("-")[0])) {
        throw "Version $Version must be newer than the latest release $LatestVersion."
    }
} catch {
    if ($_.Exception.Message -like "Version * must be newer*") { throw }
    throw "Unable to compare version $Version with $LatestVersion."
}

$releaseCheck = Invoke-GhCaptured @("release", "view", "v$Version", "--repo", $Repository, "--json", "tagName", "--jq", ".tagName")
if ($releaseCheck.ExitCode -eq 0) {
    throw "Release v$Version already exists."
}
if ($releaseCheck.Output -and $releaseCheck.Output -notmatch '(?i)release not found|HTTP 404') {
    throw "Unable to check whether release v$Version exists: $($releaseCheck.Output)"
}

Write-Host ""
Write-Host "GitHub account : $Account"
Write-Host "Repository     : $Repository"
Write-Host "Branch         : $Branch"
Write-Host "Latest release : v$LatestVersion"
Write-Host "New release    : v$Version"
Write-Host "Package        : $(if ($Mode -eq 'full') {'Only Patch + Full'} else {'Only Patch'})"
Write-Host ""

if ($DryRun) {
    Write-Host "DRY RUN PASSED. No files, commits, tags, releases, or manifests were changed."
    exit 0
}

$answer = Read-Host "Publish to this repository? Type Y to continue"
if ($answer -notmatch '^[Yy]$') { throw "Publishing cancelled by user." }

# Check again after the interactive prompts.  A previous workflow could have
# published its manifest while the user was choosing the version/package.
Assert-RemoteBranchContained $Branch

$repositoryFile = Join-Path $Bridge "release_repository.txt"
[System.IO.File]::WriteAllText($repositoryFile, $Repository + "`n", [System.Text.UTF8Encoding]::new($false))
$channel = if ($Version.Contains("-")) { "beta" } else { "stable" }
$versionJson = "{`n  `"version`": `"$Version`",`n  `"channel`": `"$channel`"`n}`n"
[System.IO.File]::WriteAllText((Join-Path $Bridge "translation_version.json"), $versionJson, [System.Text.UTF8Encoding]::new($false))

$FullAsset = $null
if ($Mode -eq "full") {
    $Python = Get-Python
    $runtime = Join-Path $Bridge "runtime"
    $lmtRuntime = Join-Path $Bridge "lmt_runtime"
    if (-not (Test-Path -LiteralPath $runtime) -or -not (Test-Path -LiteralPath $lmtRuntime)) {
        throw "Full mode requires prepared runtime and lmt_runtime folders under source translation_bridge. Nothing was published."
    }
    Invoke-Checked { & $Python (Join-Path $Root "tools\build_release.py") --version $Version --repository $Repository } "Local release preparation failed."
    $FullAsset = Join-Path $Root "dist\Mush-Z_Translation_Mode_Full_v$Version.zip"
    Invoke-Checked { & $Python (Join-Path $Bridge "build_translation_package.py") full $FullAsset } "Full package build failed."
}

Invoke-Checked { git -C $Root add -A } "Unable to stage release files."
$staged = (& git -C $Root diff --cached --name-status) -join "`n"
if ($staged) {
    Write-Host "Files to commit:"
    Write-Host $staged
    $commitAnswer = Read-Host "Commit and publish exactly these files? Type Y to continue"
    if ($commitAnswer -notmatch '^[Yy]$') { throw "Publishing cancelled before commit." }
    Invoke-Checked { git -C $Root diff --cached --check } "Staged files failed Git whitespace validation."
    Invoke-Checked { git -C $Root commit -m "Prepare translation mode v$Version" } "Unable to commit release preparation."
}

Invoke-Checked { git -C $Root push origin $Branch } "Unable to push source changes."
$HeadSha = (& git -C $Root rev-parse HEAD).Trim()
$DispatchTime = [DateTimeOffset]::UtcNow
Invoke-Checked { gh workflow run release-patch.yml --repo $Repository --ref $Branch -f "version=$Version" } "Unable to start the release workflow."

$RunId = $null
for ($attempt = 0; $attempt -lt 30 -and -not $RunId; $attempt++) {
    Start-Sleep -Seconds 2
    $runs = gh run list --repo $Repository --workflow release-patch.yml --branch $Branch --event workflow_dispatch --limit 10 --json databaseId,headSha,createdAt | ConvertFrom-Json
    $match = $runs | Where-Object { $_.headSha -eq $HeadSha -and [DateTimeOffset]$_.createdAt -ge $DispatchTime.AddMinutes(-1) } | Select-Object -First 1
    if ($null -ne $match) { $RunId = [string]$match.databaseId }
}
if (-not $RunId) { throw "The GitHub release workflow was dispatched but could not be located." }
& gh run watch $RunId --repo $Repository --exit-status
if ($LASTEXITCODE -ne 0) {
    $diagnostic = Write-WorkflowFailureDiagnostics $RunId $Repository $Version
    throw "The GitHub release workflow failed. Full diagnostics were saved to $($diagnostic.LogPath)"
}

Invoke-Checked { git -C $Root pull --ff-only origin $Branch } "Release succeeded, but the local checkout could not fast-forward to the published manifest."
if ($Mode -eq "full") {
    Invoke-Checked { gh release upload "v$Version" $FullAsset --repo $Repository --clobber } "Only Patch was published, but Full upload failed."
}

$manifestUrl = "https://github.com/$Repository/releases/latest/download/update_manifest.json"
$manifest = Invoke-RestMethod -Uri $manifestUrl -Headers @{ "User-Agent" = "Mush-Z-Release-Publisher" } -TimeoutSec 20
if ([string]$manifest.version -ne $Version) { throw "Published manifest reports $($manifest.version), expected $Version." }
$release = gh release view "v$Version" --repo $Repository --json isDraft,isPrerelease,assets | ConvertFrom-Json
if ($release.isDraft -or $release.isPrerelease) { throw "Release exists but is not a public stable release." }
$patch = $release.assets | Where-Object { $_.name -eq "Mush-Z_Translation_Mode_Only_Patch_v$Version.zip" }
if ($null -eq $patch) { throw "Published release is missing the Only Patch asset." }

$oldVersion = Join-Path $env:TEMP "mushz-release-old-version.json"
$statusFile = Join-Path $env:TEMP "mushz-release-update-status.txt"
'{"version":"0.0.0","channel":"stable"}' | Set-Content -LiteralPath $oldVersion -Encoding UTF8
& "$env:WINDIR\SysWOW64\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Bridge "check_translation_update.ps1") -VersionFile $oldVersion -StatusFile $statusFile
$status = Get-Content -LiteralPath $statusFile -Raw
if ($status -notmatch 'status=update' -or $status -notmatch "version=$([regex]::Escape($Version))") {
    throw "The player-facing 32-bit update check failed: $status"
}

Write-Host ""
Write-Host "RELEASE COMPLETED AND PLAYER UPDATE CHECK PASSED."
Write-Host "https://github.com/$Repository/releases/tag/v$Version"
