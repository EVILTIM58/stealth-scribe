@echo off
setlocal enabledelayedexpansion
title Stealth-Scribe Worker - Setup
cd /d "%~dp0"

echo ================================================================
echo   STEALTH-SCRIBE - transcription worker setup
echo   Audio in. Transcribe to English. Save as PDF.
echo ================================================================
echo.
echo This installs everything the worker needs into a private Python
echo environment in this folder. It downloads a few GB, so allow
echo 10-20 minutes. You only do this once.
echo.
pause

REM ---------- find Python ----------
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo.
  echo [X] Python was not found.
  echo     Install Python 3.11 or 3.12 from https://www.python.org/downloads/
  echo     IMPORTANT: tick "Add python.exe to PATH" during install.
  echo.
  pause
  exit /b 1
)

for /f "tokens=2" %%v in ('%PY% -V 2^>^&1') do set "PYVER=%%v"
echo Using Python !PYVER!
echo.

if not exist ".venv\Scripts\python.exe" (
  echo Creating environment...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo [X] Could not create the environment.
    pause
    exit /b 1
  )
)
set "VPY=.venv\Scripts\python.exe"

echo Updating pip...
"%VPY%" -m pip install --upgrade pip setuptools wheel --quiet

REM ---------- GPU detection ----------
set "HASGPU="
where nvidia-smi >nul 2>&1 && set "HASGPU=1"

echo.
if defined HASGPU (
  echo NVIDIA GPU detected - installing the CUDA build of PyTorch.
  echo This is the big download. Sit tight.
  "%VPY%" -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
) else (
  echo No NVIDIA GPU detected - installing the CPU build of PyTorch.
  echo The worker will still work, just a lot slower.
  "%VPY%" -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
)
if errorlevel 1 (
  echo [X] PyTorch install failed. Check your internet connection and re-run.
  pause
  exit /b 1
)

echo.
echo Installing the transcription engine...
"%VPY%" -m pip install faster-whisper numpy requests
if errorlevel 1 (
  echo [X] Install failed.
  pause
  exit /b 1
)

echo.
echo Installing speaker separation...
"%VPY%" -m pip install "pyannote.audio>=3.1.1"
if errorlevel 1 (
  echo [!] Speaker separation could not be installed.
  echo     The worker still runs - it falls back to the built-in detector.
)

if not exist "stealthscribe-worker.json" (
  copy /y "stealthscribe-worker.example.json" "stealthscribe-worker.json" >nul
  echo.
  echo Created stealthscribe-worker.json
)

echo.
echo ================================================================
echo   Setup complete.
echo ================================================================
echo.
echo   NEXT: open stealthscribe-worker.json in Notepad and set
echo     server_url    -^> http://10.0.0.146:8458
echo     worker_token  -^> the same WORKER_TOKEN you put in the
echo                      docker-compose.yml on the NAS
echo.
echo   Then double-click run_worker.bat
echo.
notepad stealthscribe-worker.json
pause
