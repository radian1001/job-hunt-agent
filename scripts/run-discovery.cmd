@echo off
cd /d "E:\claude skills\job-hunt-agent"
echo ===== discovery started %date% %time% ===== >> "logs\discovery.log"
rem Scoped allowlist (user-approved): auto-approves only the tools the skill needs;
rem anything a web page might inject outside this list stalls instead of running.
call claude -p "/discover-startups" --permission-mode acceptEdits --allowedTools "mcp__tinyfish__search" "mcp__tinyfish__fetch_content" "mcp__tinyfish__run_big_search" "Bash(python:*)" "Bash(powershell:*)" "Bash(grep:*)" "Read" "Write" "Edit" >> "logs\discovery.log" 2>&1
echo ===== discovery exited %errorlevel% at %time% ===== >> "logs\discovery.log"
