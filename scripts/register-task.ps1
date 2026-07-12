# Registers (or replaces) all job-hunt-agent scheduled tasks.
$ErrorActionPreference = "Stop"
$scriptsDir = $PSScriptRoot

$tasks = @(
    @{ Name = "JobHuntScan";      Cmd = "run-scan.cmd";      Args = "/sc daily /st 09:00" },
    @{ Name = "JobHuntDiscovery"; Cmd = "run-discovery.cmd"; Args = "/sc weekly /d MON /st 09:30" },
    @{ Name = "JobHuntWeekly";    Cmd = "run-weekly.cmd";    Args = "/sc weekly /d SUN /st 18:00" }
)

foreach ($t in $tasks) {
    $cmd = Join-Path $scriptsDir $t.Cmd
    if (-not (Test-Path $cmd)) { Write-Error "$($t.Cmd) not found at $cmd"; exit 1 }
    $create = "schtasks /create /f /tn `"$($t.Name)`" /tr `"\`"$cmd\`"`" $($t.Args)"
    cmd /c $create
    if ($LASTEXITCODE -ne 0) { Write-Error "schtasks /create failed for $($t.Name)"; exit 1 }

    # Laptop-friendly: run on battery, wake from sleep for the trigger, and kill any
    # run stuck past 2 hours so a hung instance can't block future ones.
    $task = Get-ScheduledTask -TaskName $t.Name
    $task.Settings.DisallowStartIfOnBatteries = $false
    $task.Settings.StopIfGoingOnBatteries     = $false
    $task.Settings.WakeToRun                  = $true
    $task.Settings.ExecutionTimeLimit         = "PT2H"
    Set-ScheduledTask -InputObject $task | Out-Null
    Write-Output "Registered $($t.Name) ($($t.Args)) [battery OK, wake OK, 2h limit]"
}
Write-Output "Note: a shut-down (powered-off) machine cannot wake itself; sleep is fine. Missed runs do not catch up."
