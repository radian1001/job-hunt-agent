param([switch]$TestMode)
$ErrorActionPreference = "Stop"

function Get-ApplyNumber([string]$text) {
    if ($text -match '(?i)^\s*apply\s+to\s+#?(\d+)\s*$') { return $Matches[1] }
    return $null
}

if ($TestMode) { return }  # dot-source for tests without polling

$root = Split-Path $PSScriptRoot -Parent
try {
    $config = Get-Content (Join-Path $root "config\telegram.json") -Raw | ConvertFrom-Json
    $offsetPath = Join-Path $root "state\telegram-offset.txt"
    # int64: Telegram update_ids exceed Int32 range for newer bots; [int] would
    # overflow-throw on every run and permanently stall the poller.
    $offset = [int64]0
    if (Test-Path $offsetPath) { $offset = [int64](Get-Content $offsetPath -TotalCount 1) }

    $uri = "https://api.telegram.org/bot$($config.bot_token)/getUpdates?offset=$offset&timeout=0"
    $updates = Invoke-RestMethod -Uri $uri

    foreach ($u in $updates.result) {
        Set-Content -Path $offsetPath -Value ($u.update_id + 1) -Encoding utf8
        if (-not $u.message) { continue }
        # Only obey messages from the configured chat — ignore strangers messaging the bot
        if ("$($u.message.chat.id)" -ne "$($config.chat_id)") { continue }
        $n = Get-ApplyNumber $u.message.text
        if ($n) {
            Set-Location $root
            $log = Join-Path $root "logs\draft-$n-$(Get-Date -Format yyyy-MM-dd-HHmm).log"
            # Scoped allowlist (user-approved, same design as the scheduled wrappers): reduces
            # what an injected instruction from fetched web content can invoke directly.
            # NOTE: Bash(python/powershell) still permit arbitrary code - accepted residual risk.
            cmd /c "claude -p `"/draft-application $n`" --permission-mode acceptEdits --allowedTools `"mcp__tinyfish__fetch_content`" `"Bash(python:*)`" `"Bash(powershell:*)`" `"Read`" `"Write`" `"Edit`" > `"$log`" 2>&1"
        }
    }
}
catch {
    # Poller runs unattended every 5 min — failures must leave a trace somewhere findable.
    $errLog = Join-Path $root "logs\poller-error.log"
    Add-Content -Path $errLog -Value "$(Get-Date -Format o) $($_.Exception.Message)" -Encoding utf8
    exit 1
}
