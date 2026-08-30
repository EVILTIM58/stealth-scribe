@echo off
setlocal
title Stealth-Scribe Worker - autostart
cd /d "%~dp0"

echo This registers the Stealth-Scribe worker to start automatically when you log in,
echo so recordings you upload get transcribed without you starting anything.
echo.
choice /c YN /m "Register autostart now"
if errorlevel 2 goto :end

schtasks /create /tn "Stealth-Scribe Worker" /tr "\"%~dp0run_worker.bat\"" /sc onlogon /rl highest /f
if errorlevel 1 (
  echo.
  echo [X] Could not register. Try running this file as Administrator.
) else (
  echo.
  echo Registered. Remove it any time with:
  echo    schtasks /delete /tn "Stealth-Scribe Worker" /f
)

:end
echo.
pause
