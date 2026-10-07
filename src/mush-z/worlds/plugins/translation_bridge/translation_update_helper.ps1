[CmdletBinding()]
param(
    [int]$CloseTimeoutSeconds = 180,
    [string]$StatusLogPath = "",
    [switch]$TestOnly,
    [switch]$SuppressDialogs
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$updater = Join-Path $scriptRoot "update_translation.ps1"
$statusLog = if ([string]::IsNullOrWhiteSpace($StatusLogPath)) {
    Join-Path $scriptRoot "translation_update.log"
} else {
    [IO.Path]::GetFullPath($StatusLogPath)
}

function Write-HelperStatus([string]$message) {
    Write-Host $message
    Add-Content -LiteralPath $statusLog -Value ((Get-Date -Format "yyyy-MM-dd HH:mm:ss") + " " + $message) -Encoding UTF8
}

function New-HandoffWindow {
    if ($SuppressDialogs) { return $null }
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    if (-not ("MushZUpdateHandoffWindow" -as [type])) {
        Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class MushZUpdateHandoffWindow {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr handle);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr handle, int command);
}
"@
    }
    $form = New-Object System.Windows.Forms.Form
    $form.Text = "Translation Update"
    $form.Width = 520
    $form.Height = 145
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.ControlBox = $false
    $form.ShowInTaskbar = $true
    $label = New-Object System.Windows.Forms.TextBox
    $label.Location = New-Object System.Drawing.Point(20, 25)
    $label.Size = New-Object System.Drawing.Size(470, 55)
    $label.Multiline = $true
    $label.ReadOnly = $true
    $label.TabStop = $true
    $label.TextAlign = "Center"
    $label.Text = "Waiting for MUSHclient to close..."
    $label.AccessibleName = $label.Text
    $form.Controls.Add($label)
    $null = $form.Handle
    # SW_SHOWNOACTIVATE keeps MUSHclient in front, but places this persistent
    # handoff window in the desktop Z order before MUSHclient closes.
    $null = [MushZUpdateHandoffWindow]::ShowWindow($form.Handle, 4)
    [System.Windows.Forms.Application]::DoEvents()
    return @{ Form = $form; Label = $label }
}

function Set-HandoffText($window, [string]$text, [switch]$Activate) {
    if ($null -eq $window) { return }
    $window.Label.Text = $text
    $window.Label.AccessibleName = $text
    if ($Activate) {
        $null = [MushZUpdateHandoffWindow]::ShowWindow($window.Form.Handle, 9)
        $window.Form.BringToFront()
        $null = $window.Form.Activate()
        $null = [MushZUpdateHandoffWindow]::SetForegroundWindow($window.Form.Handle)
        $null = $window.Label.Focus()
        $window.Label.SelectAll()
    }
    [System.Windows.Forms.Application]::DoEvents()
}

function Close-HandoffWindow($window) {
    if ($null -eq $window) { return }
    try { $window.Form.Close() } catch {}
    try { $window.Form.Dispose() } catch {}
}

function Confirm-AndOpenAddon($handoffWindow) {
    $addon = Join-Path $scriptRoot "Mush_Client_Translation_Review_v3.nvda-addon"
    if (-not (Test-Path -LiteralPath $addon -PathType Leaf)) {
        throw "The NVDA add-on package was not found."
    }
    if ($SuppressDialogs) {
        Write-HelperStatus "Test mode: skipped the add-on confirmation dialog."
        return
    }
    Set-HandoffText $handoffWindow "Update completed. Ready to install the NVDA add-on." -Activate
    $answer = [System.Windows.Forms.MessageBox]::Show(
        $handoffWindow.Form,
        "Update completed. Press Enter or choose OK to install the NVDA add-on.",
        "Translation Update",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    )
    if ($answer -eq [System.Windows.Forms.DialogResult]::OK) {
        Start-Process -FilePath $addon | Out-Null
        Write-HelperStatus "Opened the NVDA add-on installer after confirmation."
    } else {
        Write-HelperStatus "The update completed, but the add-on installer was not opened."
    }
}

function Start-HiddenUpdater([string]$arguments, $handoffWindow) {
    $powerShellExe = Join-Path $PSHOME "powershell.exe"
    $commandLine = '-NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $updater + '" ' + $arguments
    $process = Start-Process -FilePath $powerShellExe -ArgumentList $commandLine -WindowStyle Hidden -PassThru
    while (-not $process.HasExited) {
        if ($null -ne $handoffWindow) {
            [System.Windows.Forms.Application]::DoEvents()
        }
        Start-Sleep -Milliseconds 50
        $process.Refresh()
    }
    return $process
}

$handoffWindow = $null
try {
    $handoffWindow = New-HandoffWindow
    Write-HelperStatus "Waiting for MUSHclient to close normally."
    $deadline = (Get-Date).AddSeconds([Math]::Max(1, $CloseTimeoutSeconds))
    while ($null -ne (Get-Process -Name "MUSHclient" -ErrorAction SilentlyContinue)) {
        if ((Get-Date) -ge $deadline) {
            throw "MUSHclient did not close before the timeout. The update was cancelled and no files were changed."
        }
        if ($null -ne $handoffWindow) {
            [System.Windows.Forms.Application]::DoEvents()
        }
        Start-Sleep -Milliseconds 250
    }
    # Give Translation Mode's heartbeat cleanup a short opportunity to close
    # SQLite and its child llama-server before files are replaced.
    Start-Sleep -Milliseconds 750
    Set-HandoffText $handoffWindow "MUSHclient has closed. Starting the translation update..." -Activate
    if ($TestOnly) {
        $demo = Start-HiddenUpdater "-ProgressDemo" $handoffWindow
        if ($demo.ExitCode -ne 0) {
            throw "The progress window test failed with exit code $($demo.ExitCode)."
        }
        Confirm-AndOpenAddon $handoffWindow
        Write-HelperStatus "Handoff test passed. No files were downloaded or replaced."
        exit 0
    }
    if (-not (Test-Path -LiteralPath $updater -PathType Leaf)) {
        throw "The translation updater was not found."
    }
    Write-HelperStatus "MUSHclient has closed. Starting the translation update in the background."
    $updateProcess = Start-HiddenUpdater "-ShowDownloadProgress -SkipAddonLaunch" $handoffWindow
    if ($updateProcess.ExitCode -ne 0) {
        throw "The translation updater failed with exit code $($updateProcess.ExitCode)."
    }
    Confirm-AndOpenAddon $handoffWindow
    Write-HelperStatus "Automatic update completed."
    exit 0
} catch {
    Write-HelperStatus ("ERROR: " + $_.Exception.Message)
    if (-not $SuppressDialogs) {
        try {
            Set-HandoffText $handoffWindow "The automatic translation update failed." -Activate
            $null = [System.Windows.Forms.MessageBox]::Show(
                $handoffWindow.Form,
                "The automatic translation update failed. No incomplete update was kept. See translation_update.log for details.",
                "Translation Update",
                [System.Windows.Forms.MessageBoxButtons]::OK,
                [System.Windows.Forms.MessageBoxIcon]::Error
            )
        } catch {}
    }
    exit 1
} finally {
    Close-HandoffWindow $handoffWindow
}
