@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo   Stopping Personal Knowledge Base
echo ===================================================
echo.

set FOUND=0
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8001 ^| findstr LISTENING') do (
    echo Stopping running server instance (PID: %%a)...
    taskkill /F /PID %%a >nul 2>&1
    set FOUND=1
)

echo.
if "%FOUND%"=="1" (
    echo Personal Knowledge Base server has been stopped cleanly.
) else (
    echo No active server instance was found running on port 8001.
)
echo.

echo Closing in 3 seconds...
timeout /t 3 >nul
