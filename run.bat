@echo off
title MLOps Dashboard - Backend
set ROOT=%~dp0
echo Starting backend at http://localhost:5000 ...
"%ROOT%.venv\Scripts\python.exe" -u "%ROOT%backend\run_server.py"
exit /b %ERRORLEVEL%