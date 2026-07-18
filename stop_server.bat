@echo off
title Driver Dashboard — Stop

echo ==========================================
echo   إيقاف Driver Dashboard
echo ==========================================
echo.

REM Stop daemon (find python running run_daemon.py)
echo [1/2] إيقاف السيرفر...
taskkill /f /im python.exe 2>nul >nul
taskkill /f /im ssh.exe 2>nul >nul
timeout /t 2 /nobreak >nul

REM Check
curl -s http://localhost:8000/login >nul 2>&1
if %errorlevel% neq 0 (
    echo ✅ السيرفر تم إيقافه
) else (
    echo ⚠️ لسه شغال — حاول مرة تانية
)

REM Remove from startup
echo [2/2] إزالة من بدء تشغيل Windows...
set STARTUP_FILE=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\DriverDashboard.vbs
if exist "%STARTUP_FILE%" (
    del "%STARTUP_FILE%"
    echo ✅ تمت الإزالة من بدء التشغيل
) else (
    echo غير موجود في بدء التشغيل
)

echo.
echo ==========================================
echo   ✅ تم الإيقاف
echo ==========================================
pause
