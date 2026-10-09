@echo off
setlocal

cd /d "%~dp0.."

echo ==========================================
echo   AI Cook - start frontend and backend
echo ==========================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0manage.ps1" -Action start -OpenBrowser
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [FAIL] Startup failed. The error output above is still available.
    pause
)

exit /b %EXIT_CODE%
