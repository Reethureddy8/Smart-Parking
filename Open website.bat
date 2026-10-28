@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title SmartPark AI
set "URL=http://127.0.0.1:5000/"

where python >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not in PATH.
    pause
    exit /b 1
)

powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5000/login -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if %ERRORLEVEL% EQU 0 (
    start "" "%URL%"
    exit /b 0
)

echo Starting SmartPark AI...
echo First launch can take a few minutes while AI models load.
echo Keep the "SmartPark Server" window open while you use the site.
echo.

start "SmartPark Server" cmd /k "cd /d "%~dp0" && python flask_app.py"

echo Waiting for the site to come up...
powershell -NoProfile -Command ^
  "$ok=$false; for($i=0; $i -lt 180; $i++){ try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5000/login -TimeoutSec 2 | Out-Null; $ok=$true; break } catch { Start-Sleep -Seconds 2 } }; if(-not $ok){ exit 1 }"

if %ERRORLEVEL% NEQ 0 (
    echo The server did not start in time. Check the SmartPark Server window for errors.
    pause
    exit /b 1
)

start "" "%URL%"
exit /b 0
