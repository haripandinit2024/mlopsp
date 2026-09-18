@echo off
title MLOps Dashboard Preview
cd /d "%~dp0"

echo Regenerating preview with latest model data...
".venv\Scripts\python.exe" src\generate_dashboard_preview.py

echo Starting preview server on port 5500...
start "MLOps Preview Server" cmd /k ".venv\Scripts\python.exe -m http.server 5500 -d frontend\public"

timeout /t 2 /nobreak >nul
start http://127.0.0.1:5500/dashboard_preview.html
echo Preview opened in your browser.