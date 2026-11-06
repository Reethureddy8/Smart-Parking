@echo off
setlocal
cd /d "%~dp0"
title SmartPark
set "URL=http://127.0.0.1:5000/"

where python >nul 2>&1 || (echo Python 3.10+ is required: https://www.python.org/downloads/ & pause & exit /b 1)

rem Already running? Just open it.
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing %URL%api/health -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if %ERRORLEVEL% EQU 0 ( start "" "%URL%" & exit /b 0 )

python -c "import fastapi, uvicorn, multipart, segno, cv2, ultralytics, easyocr" >nul 2>&1
if errorlevel 1 (
  echo Installing dependencies - first run only, this can take a few minutes...
  python -m pip install -r requirements.txt || (echo Dependency install failed. & pause & exit /b 1)
)

python run.py --open
pause
