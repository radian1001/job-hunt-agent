@echo off
cd /d "E:\claude skills\job-hunt-agent"
if not exist logs mkdir logs
echo ===== weekly started %date% %time% ===== >> "logs\weekly.log"
rem Scoped allowlist (user-approved): reduces what an injected instruction from fetched
rem web content can invoke directly. NOTE: Bash(python/powershell) still permit arbitrary
rem code - accepted residual risk for unattended runs on this machine.
call claude -p "/weekly-report" --permission-mode acceptEdits --allowedTools "Bash(python:*)" "Bash(powershell:*)" "Read" "Write" "Edit" >> "logs\weekly.log" 2>&1
echo ===== weekly exited %errorlevel% at %time% ===== >> "logs\weekly.log"
