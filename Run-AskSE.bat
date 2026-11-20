@echo off
REM AskSE launcher - double-click to set up (first run), start the server and open the browser.
cd /d "%~dp0"
title AskSE server

where python >nul 2>nul
if errorlevel 1 (
    echo Python is not installed or not on PATH. Install Python 3.10+ from https://www.python.org and tick "Add python.exe to PATH".
    pause
    exit /b 1
)

if not exist "venv\Scripts\python.exe" (
    echo First run: creating the virtual environment...
    python -m venv venv
    if errorlevel 1 goto fail
)

echo Checking dependencies...
"venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 goto fail

echo.
echo Starting AskSE at http://127.0.0.1:8000
echo No .env file = demo mode. Add LLM_API_KEY to .env for AI mode.
echo Close this window to stop the server.
echo.
start "" cmd /c "timeout /t 3 /nobreak >nul & start "" http://127.0.0.1:8000"
"venv\Scripts\python.exe" main.py
pause
exit /b 0

:fail
echo.
echo Setup failed. Check your internet connection and try again.
pause
exit /b 1
