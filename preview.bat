@echo off
setlocal
title EduGuard - Live Preview Launcher
set "ROOT=%~dp0"

echo ============================================
echo   EduGuard - Student Risk Analytics
echo   Live Preview: http://localhost:5000/login
echo ============================================
echo.

REM Prefer the project virtualenv; fall back to PATH python.
set "PYTHON="
if exist "%ROOT%.venv\Scripts\python.exe" set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if not defined PYTHON set "PYTHON=python"

REM Start the Flask server in its own window if port 5000 is not in use.
netstat -an | findstr ":5000" | findstr "LISTENING" >nul
if %errorlevel% neq 0 (
    echo Starting EduGuard server on port 5000...
    start "EduGuard Server" /MIN "%PYTHON%" -u "%ROOT%backend\run_server.py"
    timeout /t 2 /nobreak >nul
) else (
    echo Server already running on port 5000
)
echo.

REM Wait until /api/health reports status ok (Flask emits compact JSON).
echo Waiting for the server to start...
set /a tries=0
:wait
curl -s http://localhost:5000/api/health > "%TEMP%\eduguard_health.json" 2>nul
findstr /c:"status" "%TEMP%\eduguard_health.json" >nul 2>&1
if %errorlevel% equ 0 goto ready
set /a tries+=1
if %tries% geq 45 (
    echo.
    echo Server did not start in time.
    echo Check backend\run_server.py and that the port is free.
    pause
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto wait

:ready
del "%TEMP%\eduguard_health.json" >nul 2>&1
echo.
echo ============================================
echo   EduGuard is live:
echo   http://localhost:5000/login
echo ============================================
echo.

REM Open the login page in a new, separate browser window.
set "URL=http://localhost:5000/login"
set "BROWSER="
if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" set "BROWSER=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not defined BROWSER if exist "C:\Program Files\Microsoft\Edge\Application\msedge.exe" set "BROWSER=C:\Program Files\Microsoft\Edge\Application\msedge.exe"
if not defined BROWSER if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" set "BROWSER=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not defined BROWSER if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" set "BROWSER=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if not defined BROWSER if exist "C:\Program Files\Mozilla Firefox\firefox.exe" set "BROWSER=C:\Program Files\Mozilla Firefox\firefox.exe"
if not defined BROWSER if exist "C:\Program Files (x86)\Mozilla Firefox\firefox.exe" set "BROWSER=C:\Program Files (x86)\Mozilla Firefox\firefox.exe"

if defined BROWSER (
    echo Opening a new browser window...
    start "" "%BROWSER%" --new-window "%URL%"
) else (
    echo Opening in your default browser...
    start "" "%URL%"
)

echo.
echo Preview opened! The server runs in the "EduGuard Server" window.
echo Close that window (or press Ctrl+C) to stop the server.
echo.
endlocal
exit /b 0