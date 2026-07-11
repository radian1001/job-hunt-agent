@echo off
cd /d "E:\claude skills\job-hunt-agent"
echo ===== weekly started %date% %time% ===== >> "logs\weekly.log"
rem Scoped allowlist (user-approved): auto-approves only the tools the skill needs;
rem anything outside this list stalls instead of running.
call claude -p "/weekly-report" --permission-mode acceptEdits --allowedTools "Bash(python:*)" "Bash(powershell:*)" "Read" "Write" "Edit" >> "logs\weekly.log" 2>&1
echo ===== weekly exited %errorlevel% at %time% ===== >> "logs\weekly.log"
