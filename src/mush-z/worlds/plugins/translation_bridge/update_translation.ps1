[CmdletBinding()]
param(
    [string]$ManifestUrl = "https://github.com/wengweng0312/altar-aeon-mush-client-translation/releases/latest/download/update_manifest.json"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$mushZRoot = [IO.Path]::GetFullPath((Join-Path $scriptRoot "..\..\.."))
$statusLog = Join-Path $scriptRoot "translation_update.log"
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

function Restore-Backup {
    Write-Status "更新未完成，正在回復舊版檔案。"
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

try {
    if (Test-MushClientRunning) {
        Stop-WithMessage "請先關閉 MUSHclient，再執行翻譯更新。"
    }

    New-Item -ItemType Directory -Force -Path $tempRoot, $stageRoot, $backupRoot | Out-Null
    Write-Status "正在檢查翻譯更新。"
    $headers = @{ "User-Agent" = "Mush-Z-Translation-Updater" }
    $manifest = Invoke-RestMethod -Uri $ManifestUrl -Headers $headers -TimeoutSec 20

    if ($manifest.schema_version -ne 1) {
        Stop-WithMessage "不支援的更新資訊格式。"
    }
    if (-not $manifest.published) {
        Write-Status "目前尚未發布可自動安裝的版本。"
        exit 0
    }
    if ([string]::IsNullOrWhiteSpace([string]$manifest.patch_url)) {
        Stop-WithMessage "更新資訊缺少 Only Patch 下載位置。"
    }
    if ([string]$manifest.sha256 -notmatch "^[0-9a-fA-F]{64}$") {
        Stop-WithMessage "更新資訊缺少有效的 SHA-256。"
    }

    $localVersion = "0.0.0"
    $localVersionPath = Join-Path $scriptRoot "translation_version.json"
    if (Test-Path -LiteralPath $localVersionPath) {
        $localInfo = Get-Content -LiteralPath $localVersionPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $localVersion = [string]$localInfo.version
    }
    if ($localVersion -eq [string]$manifest.version) {
        Write-Status ("已經是最新版 " + $localVersion + "。")
        exit 0
    }

    Write-Status ("正在下載翻譯更新 " + [string]$manifest.version + "。")
    Invoke-WebRequest -Uri ([string]$manifest.patch_url) -Headers $headers -OutFile $downloadPath -TimeoutSec 120
    $actualHash = (Get-FileHash -LiteralPath $downloadPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne ([string]$manifest.sha256).ToLowerInvariant()) {
        Stop-WithMessage "下載檔案的 SHA-256 不符合，更新已取消。"
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
            Stop-WithMessage ("Only Patch 缺少必要檔案：" + $relative)
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
            Stop-WithMessage "更新包包含不安全的路徑。"
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
    Write-Status ("翻譯更新完成：" + [string]$manifest.version)
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
