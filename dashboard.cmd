@echo off
title Job Hunt Dashboard - keep this window open
cd /d "%~dp0"
if not exist logs mkdir logs

rem Already running? Just open the browser instead of failing on a busy port.
netstat -ano | findstr ":8765" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo Dashboard is already running - opening browser.
  start "" http://127.0.0.1:8765
  timeout /t 2 >nul
  exit /b 0
)

echo Starting the Job Hunt Dashboard...
echo Opening http://127.0.0.1:8765 in your browser.
echo.
echo Keep this window open while you use the dashboard. Closing it stops the server.
echo.
start "" http://127.0.0.1:8765
python scripts\dashboard.py
echo.
echo Dashboard stopped.
pause
