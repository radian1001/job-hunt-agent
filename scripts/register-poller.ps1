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

# Backstop: a hung instance must not block later runs forever (see poll-telegram.ps1's
# -TimeoutSec note). Also allow battery runs and wake-from-sleep.
$t = Get-ScheduledTask -TaskName "JobHuntPoller"
$t.Settings.ExecutionTimeLimit         = "PT30M"
$t.Settings.DisallowStartIfOnBatteries = $false
$t.Settings.StopIfGoingOnBatteries     = $false
$t.Settings.WakeToRun                  = $true
Set-ScheduledTask -InputObject $t | Out-Null
Write-Output "Registered JobHuntPoller: every 5 minutes (30-min limit, battery OK, wake OK)."
