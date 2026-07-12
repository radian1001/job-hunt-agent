@echo off
cd /d "E:\claude skills\job-hunt-agent"
if not exist logs mkdir logs
echo ===== discovery started %date% %time% ===== >> "logs\discovery.log"
rem Scoped allowlist (user-approved): reduces what an injected instruction from fetched
rem web content can invoke directly. NOTE: Bash(python/powershell) still permit arbitrary
rem code - accepted residual risk for unattended runs on this machine.
call claude -p "/discover-startups" --permission-mode acceptEdits --allowedTools "mcp__tinyfish__fetch_content" "mcp__tinyfish__run_big_search" "Bash(python:*)" "Bash(powershell:*)" "Bash(grep:*)" "Read" "Write" "Edit" >> "logs\discovery.log" 2>&1
echo ===== discovery exited %errorlevel% at %time% ===== >> "logs\discovery.log"
