[CmdletBinding()]
param(
    [string]$ManifestUrl = "",
    [string]$ManifestFile = "",
    [string]$PatchFile = "",
    [string]$MushZRoot = "",
    [switch]$SkipMushClientCheck,
    [switch]$SkipAddonLaunch,
    [switch]$ShowDownloadProgress,
    [switch]$ProgressDemo
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
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$mushZRoot = if ([string]::IsNullOrWhiteSpace($MushZRoot)) {
    [IO.Path]::GetFullPath((Join-Path $scriptRoot "..\..\.."))
} else {
    [IO.Path]::GetFullPath($MushZRoot)
}
$installBridge = Join-Path $mushZRoot "worlds\plugins\translation_bridge"
$statusLog = Join-Path $installBridge "translation_update.log"
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("mushz_translation_update_" + [guid]::NewGuid().ToString("N"))
$downloadPath = Join-Path $tempRoot "Only_Patch.zip"
$stageRoot = Join-Path $tempRoot "stage"
$backupRoot = Join-Path $tempRoot "backup"
$createdTargets = New-Object System.Collections.Generic.List[string]
$backedUpTargets = New-Object System.Collections.Generic.List[string]

function Write-Status([string]$message) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $message
    Write-Host $message
    Add-Content -LiteralPath $statusLog -Value $line -Encoding UTF8
}

function Stop-WithMessage([string]$message) {
    Write-Status ("ERROR: " + $message)
    throw $message
}

function Test-MushClientRunning {
    return $null -ne (Get-Process -Name "MUSHclient" -ErrorAction SilentlyContinue)
}

function Get-Sha256([string]$path) {
    $stream = [IO.File]::OpenRead($path)
    try {
        $algorithm = [Security.Cryptography.SHA256]::Create()
        try {
            return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace("-", "").ToLowerInvariant()
        } finally {
            $algorithm.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

function Initialize-NvdaProgressSpeech {
    if ($script:NvdaProgressInitialized) { return $script:NvdaProgressReady }
    $script:NvdaProgressInitialized = $true
    $script:NvdaProgressReady = $false
    $dll = Join-Path $mushZRoot "nvdaControllerClient32.dll"
    if (-not (Test-Path -LiteralPath $dll -PathType Leaf)) { return $false }
    try {
        $escaped = $dll.Replace('\', '\\')
        Add-Type -TypeDefinition @"
using System.Runtime.InteropServices;
public static class MushZUpdateNvda {
    [DllImport("$escaped", CharSet=CharSet.Unicode, CallingConvention=CallingConvention.Cdecl)]
    public static extern int nvdaController_speakText(string text);
}
"@
        $script:NvdaProgressReady = $true
    } catch {}
    return $script:NvdaProgressReady
}

function Speak-Progress([string]$message) {
    if (-not (Initialize-NvdaProgressSpeech)) { return }
    try { $null = [MushZUpdateNvda]::nvdaController_speakText($message) } catch {}
}

function New-DownloadProgressWindow([string]$version) {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $form = New-Object System.Windows.Forms.Form
    $form.Text = "Translation Update"
    $form.Width = 520
    $form.Height = 165
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.ControlBox = $false
    $form.TopMost = $true
    $form.ShowInTaskbar = $true

    if (-not ("MushZUpdateWindowFocus" -as [type])) {
        Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class MushZUpdateWindowFocus {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr handle);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr handle, int command);
}
"@
    }

    $label = New-Object System.Windows.Forms.Label
    $label.Location = New-Object System.Drawing.Point(20, 18)
    $label.Size = New-Object System.Drawing.Size(470, 28)
    $label.Text = "Downloading translation update " + $version + "..."
    $label.AccessibleName = $label.Text

    $bar = New-Object System.Windows.Forms.ProgressBar
    $bar.Location = New-Object System.Drawing.Point(20, 55)
    $bar.Size = New-Object System.Drawing.Size(470, 28)
    $bar.Minimum = 0
    $bar.Maximum = 100
    $bar.Value = 0
    $bar.Style = "Continuous"
    $bar.AccessibleName = "Download progress"

    $percent = New-Object System.Windows.Forms.TextBox
    $percent.Location = New-Object System.Drawing.Point(20, 92)
    $percent.Size = New-Object System.Drawing.Size(470, 24)
    $percent.ReadOnly = $true
    $percent.TabStop = $true
    $percent.TextAlign = "Center"
    $percent.Text = "Download progress: 0 percent"
    $percent.AccessibleName = "Download progress: 0 percent"

    $form.Controls.Add($label)
    $form.Controls.Add($bar)
    $form.Controls.Add($percent)
    $form.Show()
    $null = [MushZUpdateWindowFocus]::ShowWindow($form.Handle, 9)
    $form.BringToFront()
    $null = $form.Activate()
    $null = [MushZUpdateWindowFocus]::SetForegroundWindow($form.Handle)
    $null = $percent.Focus()
    $percent.SelectAll()
    [System.Windows.Forms.Application]::DoEvents()
    Speak-Progress "Translation update download started. Download progress: 0 percent."
    return @{ Form = $form; Label = $label; Bar = $bar; Percent = $percent; LastSpoken = 0 }
}

function Set-DownloadProgress($window, [int]$value, [string]$message) {
    if ($null -eq $window) { return }
    $value = [Math]::Max(0, [Math]::Min(100, $value))
    $window.Bar.Style = "Continuous"
    $window.Bar.Value = $value
    $progressText = "Download progress: " + [string]$value + " percent"
    $window.Percent.Text = $progressText
    $window.Percent.AccessibleName = $progressText
    if (-not [string]::IsNullOrWhiteSpace($message)) {
        $window.Label.Text = $message
        $window.Label.AccessibleName = $message
    }
    [System.Windows.Forms.Application]::DoEvents()
    if ($value -eq 100 -or ($value - $window["LastSpoken"]) -ge 10) {
        Speak-Progress ($progressText + ".")
        $window["LastSpoken"] = $value
    }
}

function Close-DownloadProgress($window) {
    if ($null -eq $window) { return }
    try { $window.Form.Close() } catch {}
    try { $window.Form.Dispose() } catch {}
}

function Download-WithProgress([string]$url, [string]$destination, [string]$version) {
    $window = $null
    $response = $null
    $inputStream = $null
    $outputStream = $null
    try {
        if ($ShowDownloadProgress) {
            $window = New-DownloadProgressWindow $version
        }
        $request = [Net.HttpWebRequest]::Create($url)
        $request.Method = "GET"
        $request.UserAgent = "Mush-Z-Translation-Updater"
        $request.Timeout = 120000
        $request.ReadWriteTimeout = 120000
        $response = $request.GetResponse()
        $total = [long]$response.ContentLength
        $inputStream = $response.GetResponseStream()
        $outputStream = [IO.File]::Create($destination)
        $buffer = New-Object byte[] 65536
        $received = [long]0
        $lastPercent = -1
        while (($count = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $outputStream.Write($buffer, 0, $count)
            $received += $count
            if ($total -gt 0) {
                $current = [int][Math]::Floor(($received * 100.0) / $total)
                if ($current -ne $lastPercent) {
                    Set-DownloadProgress $window $current ("Downloading translation update " + $version + "...")
                    $lastPercent = $current
                }
            } elseif ($null -ne $window) {
                $window.Bar.Style = "Marquee"
                $window.Percent.Text = "Downloading update. Total size is not available."
                $window.Percent.AccessibleName = $window.Percent.Text
                [System.Windows.Forms.Application]::DoEvents()
            }
        }
        Set-DownloadProgress $window 100 "Download completed. Verifying the update..."
    } finally {
        if ($null -ne $outputStream) { $outputStream.Dispose() }
        if ($null -ne $inputStream) { $inputStream.Dispose() }
        if ($null -ne $response) { $response.Close() }
        Close-DownloadProgress $window
    }
}

function Show-ProgressDemo {
    $window = New-DownloadProgressWindow "test"
    try {
        foreach ($value in 0, 20, 40, 60, 80, 100) {
            Set-DownloadProgress $window $value "Testing the download progress window..."
            Start-Sleep -Milliseconds 180
        }
    } finally {
        Close-DownloadProgress $window
    }
}

function Open-NvdaAddon {
    if ($SkipAddonLaunch) {
        Write-Status "Test mode: skipped the NVDA add-on installer."
        return
    }
    $addonPath = Join-Path $installBridge "Mush_Client_Translation_Review_v3.nvda-addon"
    if (-not (Test-Path -LiteralPath $addonPath -PathType Leaf)) {
        Write-Status "WARNING: The NVDA add-on package was not found."
        return
    }
    try {
        Start-Process -FilePath $addonPath | Out-Null
        Write-Status "Opened the NVDA add-on installer."
    } catch {
        Write-Status ("WARNING: Could not open the NVDA add-on installer: " + $_.Exception.Message)
    }
}

function Restore-Backup {
    Write-Status "The update did not complete. Restoring the previous files."
    foreach ($target in $createdTargets) {
        if (Test-Path -LiteralPath $target -PathType Leaf) {
            Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue
        }
    }
    foreach ($target in $backedUpTargets) {
        $relative = $target.Substring($mushZRoot.Length).TrimStart('\')
        $backup = Join-Path $backupRoot $relative
        if (Test-Path -LiteralPath $backup -PathType Leaf) {
            $parent = Split-Path -Parent $target
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
            Copy-Item -LiteralPath $backup -Destination $target -Force
        }
    }
}

if ($ProgressDemo) {
    Show-ProgressDemo
    exit 0
}

try {
    if (-not $SkipMushClientCheck -and (Test-MushClientRunning)) {
        Stop-WithMessage "Close MUSHclient before running the translation update."
    }

    New-Item -ItemType Directory -Force -Path $tempRoot, $stageRoot, $backupRoot | Out-Null
    Write-Status "Checking for a translation update."
    $headers = @{ "User-Agent" = "Mush-Z-Translation-Updater" }
    $manifest = if (-not [string]::IsNullOrWhiteSpace($ManifestFile)) {
        Get-Content -LiteralPath $ManifestFile -Raw -Encoding UTF8 | ConvertFrom-Json
    } else {
        Invoke-RestMethod -Uri $ManifestUrl -Headers $headers -TimeoutSec 20
    }

    if ($manifest.schema_version -ne 1) {
        Stop-WithMessage "The update manifest format is not supported."
    }
    if (-not $manifest.published) {
        Write-Status "No automatic update is currently published."
        exit 0
    }
    if ([string]::IsNullOrWhiteSpace([string]$manifest.patch_url)) {
        Stop-WithMessage "The update manifest does not contain an Only Patch URL."
    }
    if ([string]$manifest.sha256 -notmatch "^[0-9a-fA-F]{64}$") {
        Stop-WithMessage "The update manifest does not contain a valid SHA-256 value."
    }

    $localVersion = "0.0.0"
    $localVersionPath = Join-Path $installBridge "translation_version.json"
    if (Test-Path -LiteralPath $localVersionPath) {
        $localInfo = Get-Content -LiteralPath $localVersionPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $localVersion = [string]$localInfo.version
    }
    if ($localVersion -eq [string]$manifest.version) {
        Write-Status ("The installed version is already current: " + $localVersion)
        Open-NvdaAddon
        exit 0
    }

    Write-Status ("Downloading translation update " + [string]$manifest.version + ".")
    if (-not [string]::IsNullOrWhiteSpace($PatchFile)) {
        Copy-Item -LiteralPath $PatchFile -Destination $downloadPath -Force
    } else {
        Download-WithProgress ([string]$manifest.patch_url) $downloadPath ([string]$manifest.version)
    }
    $actualHash = Get-Sha256 $downloadPath
    if ($actualHash -ne ([string]$manifest.sha256).ToLowerInvariant()) {
        Stop-WithMessage "The downloaded file failed SHA-256 verification. The update was cancelled."
    }

    Expand-Archive -LiteralPath $downloadPath -DestinationPath $stageRoot -Force
    $required = @(
        "worlds\plugins\Translation_Mode.xml",
        "worlds\plugins\translation_bridge\translation_worker.py",
        "worlds\plugins\translation_bridge\translation_worker.pyw",
        "PACKAGE_MANIFEST_SHA256.txt"
    )
    foreach ($relative in $required) {
        if (-not (Test-Path -LiteralPath (Join-Path $stageRoot $relative) -PathType Leaf)) {
            Stop-WithMessage ("The Only Patch is missing a required file: " + $relative)
        }
    }

    $protectedNames = @(
        "cloud_translation_config.txt",
        "translation_config.json",
        "translation_cache.sqlite3",
        "backend_choice.json"
    )
    $files = Get-ChildItem -LiteralPath $stageRoot -Recurse -File | Where-Object {
        $_.Name -ne "PACKAGE_MANIFEST_SHA256.txt" -and $_.Name -notin $protectedNames
    }
    foreach ($file in $files) {
        $relative = $file.FullName.Substring($stageRoot.Length).TrimStart('\')
        $target = [IO.Path]::GetFullPath((Join-Path $mushZRoot $relative))
        if (-not $target.StartsWith($mushZRoot + "\", [StringComparison]::OrdinalIgnoreCase)) {
            Stop-WithMessage "The update package contains an unsafe path."
        }
        if (Test-Path -LiteralPath $target -PathType Leaf) {
            $backup = Join-Path $backupRoot $relative
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $backup) | Out-Null
            Copy-Item -LiteralPath $target -Destination $backup -Force
            $backedUpTargets.Add($target)
        } else {
            $createdTargets.Add($target)
        }
    }

    foreach ($file in $files) {
        $relative = $file.FullName.Substring($stageRoot.Length).TrimStart('\')
        $target = [IO.Path]::GetFullPath((Join-Path $mushZRoot $relative))
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $target -Force
    }
    Write-Status ("Translation update completed: " + [string]$manifest.version)
    Open-NvdaAddon
    exit 0
}
catch {
    if ($backedUpTargets.Count -gt 0 -or $createdTargets.Count -gt 0) {
        Restore-Backup
    }
    Write-Status $_.Exception.Message
    exit 1
}
finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
