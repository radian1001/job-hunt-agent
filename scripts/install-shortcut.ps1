# Puts a "Job Hunt Dashboard" shortcut on the Desktop, pointing at dashboard.cmd
# with the project's icon. Re-run any time to recreate or repair it.
$ErrorActionPreference = "Stop"

$root   = Split-Path $PSScriptRoot -Parent
$target = Join-Path $root "dashboard.cmd"
$icon   = Join-Path $root "assets\dashboard.ico"

if (-not (Test-Path $target)) { Write-Error "dashboard.cmd not found at $target"; exit 1 }
if (-not (Test-Path $icon)) {
    Write-Output "Icon missing - generating it..."
    & python (Join-Path $PSScriptRoot "make-icon.py")
    if (-not (Test-Path $icon)) { Write-Error "could not generate $icon"; exit 1 }
}

$lnkPath = Join-Path ([Environment]::GetFolderPath('Desktop')) "Job Hunt Dashboard.lnk"
$ws  = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut($lnkPath)
$lnk.TargetPath       = $target
$lnk.WorkingDirectory = $root
$lnk.IconLocation     = "$icon,0"
$lnk.Description      = "Open the local job-hunt dashboard (scan jobs, draft applications, track pipeline)"
$lnk.WindowStyle      = 7   # minimized: the server console stays out of the way
$lnk.Save()

Write-Output "Created: $lnkPath"
Write-Output "Double-click it to start the dashboard and open http://127.0.0.1:8765"
Write-Output "Keep the console window open while using it; closing it stops the server."
