@echo off
cd /d "E:\claude skills\job-hunt-agent"
echo ===== scan started %date% %time% ===== >> "logs\scan.log"
rem Scoped allowlist (user-approved): auto-approves only the tools the skill needs;
rem anything a web page might inject outside this list stalls instead of running.
call claude -p "/job-scan" --permission-mode acceptEdits --allowedTools "mcp__tinyfish__search" "mcp__tinyfish__fetch_content" "mcp__tinyfish__run_big_search" "Bash(python:*)" "Bash(powershell:*)" "Read" "Write" "Edit" >> "logs\scan.log" 2>&1
echo ===== scan exited %errorlevel% at %time% ===== >> "logs\scan.log"
