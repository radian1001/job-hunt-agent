@echo off
cd /d "E:\claude skills\job-hunt-agent"
if not exist logs mkdir logs
echo ===== scan started %date% %time% ===== >> "logs\scan.log"
rem Scoped allowlist (user-approved): reduces what an injected instruction from fetched
rem web content can invoke directly. NOTE: Bash(python/powershell) still permit arbitrary
rem code - accepted residual risk for unattended runs on this machine.
call claude -p "/job-scan" --permission-mode acceptEdits --allowedTools "mcp__tinyfish__search" "mcp__tinyfish__fetch_content" "Bash(python:*)" "Bash(powershell:*)" "Read" "Write" "Edit" >> "logs\scan.log" 2>&1
echo ===== scan exited %errorlevel% at %time% ===== >> "logs\scan.log"
