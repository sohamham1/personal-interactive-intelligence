@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ===================================================
echo   Starting Personal Knowledge Base
echo ===================================================
echo.

echo [1/2] Checking for existing servers on port 8001...
set FOUND=0
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8001 ^| findstr LISTENING') do (
    echo Found old instance running on PID %%a. Stopping it...
    taskkill /F /PID %%a >nul 2>&1
    set FOUND=1
)

if "%FOUND%"=="1" (
    echo Existing server stopped successfully.
    echo Waiting for port to release...
    ping 127.0.0.1 -n 3 >nul
) else (
    echo Port 8001 is clean.
)

echo.
echo [2/2] Launching server...
echo.
echo ---------------------------------------------------
echo  APPLICATION IS RUNNING AT: http://localhost:8001/
echo  To stop the server, close this window or run stop_app.bat
echo ---------------------------------------------------
echo.

venv\Scripts\python.exe -m uvicorn api.server:app --port 8001
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Server failed to start.
    echo Please make sure you have run the setup correctly and uvicorn is installed in venv.
    pause
)
