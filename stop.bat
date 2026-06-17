@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo   Stopping Recall
echo ===================================================
echo.

set FOUND=0
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    echo Stopping running server instance (PID: %%a)...
    taskkill /F /PID %%a >nul 2>&1
    set FOUND=1
)

:: Forcefully close the start.bat command window if it's still open
taskkill /FI "WINDOWTITLE eq Recall_Server_Window*" /T /F >nul 2>&1

echo.
if "%FOUND%"=="1" (
    echo Recall server has been stopped cleanly.
) else (
    echo No active server instance was found running on port 8000.
)
echo.

echo Closing in 3 seconds...
timeout /t 3 >nul
