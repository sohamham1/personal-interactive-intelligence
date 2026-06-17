@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Recall_Server_Window

echo ===================================================
echo   Starting Recall
echo ===================================================
echo.

echo [1/2] Checking for existing servers on port 8000...
set FOUND=0
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    echo Found old instance running on PID %%a. Stopping it...
    taskkill /F /PID %%a >nul 2>&1
    set FOUND=1
)

if "%FOUND%"=="1" (
    echo Existing server stopped successfully.
    echo Waiting for port to release...
    ping 127.0.0.1 -n 3 >nul
) else (
    echo Port 8000 is clean.
)

echo.
echo [2/3] Checking codebase version...
for /f "tokens=*" %%i in ('git rev-parse --short HEAD 2^>nul') do set COMMIT=%%i
if "!COMMIT!"=="" set COMMIT=Unknown
echo Active version: !COMMIT!

echo.
echo [3/3] Launching server...
echo.
echo ---------------------------------------------------
echo  APPLICATION IS RUNNING AT: http://localhost:8000/
echo  To stop the server, close this window or run stop.bat
echo ---------------------------------------------------
echo.

:: Launch the browser after a short delay in the background
start /B cmd /c "timeout /t 2 >nul & start http://localhost:8000/"

:: Start the server in the foreground on all network interfaces (for phone access)
venv\Scripts\python.exe -m uvicorn api.server:app --host 0.0.0.0 --port 8000
if %errorlevel% neq 0 (
    echo.
    echo [INFO] Server stopped or encountered an error.
    echo Auto-closing in 10 seconds...
    timeout /t 10 >nul
)
