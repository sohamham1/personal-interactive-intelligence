@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ===================================================
echo   Starting Personal Knowledge Base
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
echo [2/2] Launching server...
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
    echo [ERROR] Server failed to start.
    echo Please make sure you have run the setup correctly and uvicorn is installed in venv.
    pause
)
