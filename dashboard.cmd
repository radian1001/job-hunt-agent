@echo off
rem Double-click this to open the job-hunt dashboard.
cd /d "%~dp0"
if not exist logs mkdir logs
start "" http://127.0.0.1:8765
python scripts\dashboard.py
pause
