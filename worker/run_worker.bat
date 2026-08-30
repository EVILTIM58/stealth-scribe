@echo off
title Stealth-Scribe Worker
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo The worker is not set up yet.
  echo Please run setup_worker_windows.bat first ^(double-click it^).
  echo.
  pause
  exit /b 1
)

:loop
".venv\Scripts\python.exe" "worker.py"
echo.
echo Worker stopped. Restarting in 10 seconds - close this window to quit.
timeout /t 10 >nul
goto loop
