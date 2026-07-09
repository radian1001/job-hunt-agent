# Tests send-telegram.ps1 without hitting the real Telegram API.
$ErrorActionPreference = "Continue"
$root = Split-Path $PSScriptRoot -Parent
$script = Join-Path $PSScriptRoot "send-telegram.ps1"
$configPath = Join-Path $root "config\telegram.json"
$backupPath = Join-Path $root "config\telegram.json.bak"
$failures = 0

# Preserve any real config during the test
$hadReal = Test-Path $configPath
if ($hadReal) { Move-Item $configPath $backupPath -Force }

# Test 1: missing config file -> exit 1
& powershell -NoProfile -ExecutionPolicy Bypass -File $script -Message "hi" -DryRun 2>$null
if ($LASTEXITCODE -eq 1) { Write-Output "PASS missing-config" }
else { Write-Output "FAIL missing-config (exit $LASTEXITCODE, expected 1)"; $failures++ }

# Test 2: config missing chat_id -> exit 1
Set-Content -Path $configPath -Value '{"bot_token": "tok"}' -Encoding utf8
& powershell -NoProfile -ExecutionPolicy Bypass -File $script -Message "hi" -DryRun 2>$null
if ($LASTEXITCODE -eq 1) { Write-Output "PASS invalid-config" }
else { Write-Output "FAIL invalid-config (exit $LASTEXITCODE, expected 1)"; $failures++ }

# Test 3: valid config + DryRun -> prints DRYRUN line with chat_id and message length, exit 0
Set-Content -Path $configPath -Value '{"bot_token": "tok123", "chat_id": "42"}' -Encoding utf8
$out = & powershell -NoProfile -ExecutionPolicy Bypass -File $script -Message "hello" -DryRun
if ($LASTEXITCODE -eq 0 -and $out -match "DRYRUN chat_id=42 len=5") { Write-Output "PASS dryrun" }
else { Write-Output "FAIL dryrun (exit $LASTEXITCODE, output: $out)"; $failures++ }

# Test 4: message over 4000 chars is truncated in DryRun length report
$long = "x" * 5000
$out = & powershell -NoProfile -ExecutionPolicy Bypass -File $script -Message $long -DryRun
if ($LASTEXITCODE -eq 0 -and $out -match "DRYRUN chat_id=42 len=4000") { Write-Output "PASS truncation" }
else { Write-Output "FAIL truncation (exit $LASTEXITCODE, output: $out)"; $failures++ }

# Cleanup
Remove-Item $configPath -Force -Confirm:$false
if ($hadReal) { Move-Item $backupPath $configPath -Force }

if ($failures -gt 0) { Write-Output "$failures TEST(S) FAILED"; exit 1 }
Write-Output "ALL TESTS PASSED"; exit 0
