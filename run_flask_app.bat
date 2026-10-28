@echo off
echo ========================================
echo  AI Smart Parking System - Flask App
echo ========================================
echo.

echo Checking Python installation...
python --version
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)
echo.

echo Installing required packages...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install packages
    pause
    exit /b 1
)
echo.

echo ========================================
echo  Starting Flask Application
echo ========================================
echo.
echo Application will be available at:
echo http://localhost:5000
echo.
echo Press Ctrl+C to stop the server
echo.

python flask_app.py

pause
