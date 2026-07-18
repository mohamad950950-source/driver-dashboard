@echo off
title Driver Dashboard — تشغيل
cd /d C:\Users\shafee\Downloads\driver-dashboard

echo ==================================
echo   Driver Dashboard
echo   متتبع أرباح السواقين
echo ==================================
echo.

REM Kill any old processes
taskkill /f /im python.exe 2>nul >nul
taskkill /f /im ssh.exe 2>nul >nul

REM Ensure directories
if not exist data mkdir data
if not exist uploads mkdir uploads

REM Start server
echo Starting server...
uv run python app.py

pause
