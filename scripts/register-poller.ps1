$ErrorActionPreference = "Stop"
# NOTE: deviated from brief's naked `schtasks /tr $action` — a /tr value containing spaces
# and embedded quotes gets mis-tokenized by PowerShell's native-arg passing (same failure
# class Task 11's register-task.ps1 hit). Route through cmd /c with escaped inner quotes,
# matching the proven pattern from register-task.ps1.
$scriptPath = Join-Path $PSScriptRoot "poll-telegram.ps1"
if (-not (Test-Path $scriptPath)) { Write-Error "poll-telegram.ps1 not found at $scriptPath"; exit 1 }
$trValue = "powershell -NoProfile -ExecutionPolicy Bypass -File \`"$scriptPath\`""
$create = "schtasks /create /f /tn `"JobHuntPoller`" /tr `"$trValue`" /sc minute /mo 5"
cmd /c $create
if ($LASTEXITCODE -ne 0) { Write-Error "schtasks /create failed"; exit 1 }
Write-Output "Registered JobHuntPoller: every 5 minutes."
