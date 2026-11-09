@echo off
rem Windows: double-click to start the app, then the browser opens on it. Close this window to stop.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Not set up yet - double-click setup.bat first.
    pause
    exit /b 1
)
start "" http://127.0.0.1:5000
.venv\Scripts\python app.py
pause
