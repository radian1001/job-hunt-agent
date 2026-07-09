param(
    [Parameter(Mandatory=$true)][string]$Message,
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"

$root = Split-Path $PSScriptRoot -Parent
$configPath = Join-Path $root "config\telegram.json"

if (-not (Test-Path $configPath)) {
    Write-Error "Missing config\telegram.json (copy telegram.json.example and fill it in)"
    exit 1
}

try {
    $config = Get-Content $configPath -Raw | ConvertFrom-Json
} catch {
    Write-Error "config\telegram.json is not valid JSON"
    exit 1
}

if (-not $config.bot_token -or -not $config.chat_id) {
    Write-Error "config\telegram.json must contain bot_token and chat_id"
    exit 1
}

# Telegram hard limit is 4096; stay under 4000 for safety
if ($Message.Length -gt 4000) {
    $Message = $Message.Substring(0, 4000)
}

if ($DryRun) {
    Write-Output "DRYRUN chat_id=$($config.chat_id) len=$($Message.Length)"
    exit 0
}

# PowerShell 5.1 may default to TLS 1.0; Telegram API requires TLS 1.2+
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$uri = "https://api.telegram.org/bot$($config.bot_token)/sendMessage"
$body = @{
    chat_id = $config.chat_id
    text = $Message
    disable_web_page_preview = "true"
}

try {
    $response = Invoke-RestMethod -Uri $uri -Method Post -Body $body
} catch {
    Write-Error "Telegram API request failed: $($_.Exception.Message)"
    exit 1
}

if ($response.ok) {
    Write-Output "sent"
    exit 0
} else {
    Write-Error "Telegram API returned ok=false: $($response | ConvertTo-Json -Compress)"
    exit 1
}
