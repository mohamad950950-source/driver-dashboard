@echo off
title Driver Dashboard — Install & Start
cd /d C:\Users\shafee\Downloads\driver-dashboard

echo ==========================================
echo   Driver Dashboard — تشغيل دائم
echo ==========================================
echo.

REM Kill old
taskkill /f /im python.exe 2>nul >nul
taskkill /f /im ssh.exe 2>nul >nul
timeout /t 2 /nobreak >nul

REM Clean DB (optional — fresh start)
if exist data\driver.db del data\driver.db
mkdir data uploads 2>nul
echo ✅ قاعدة بيانات جديدة

REM Add to Windows startup
copy /Y run_hidden.vbs "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\DriverDashboard.vbs" >nul 2>&1
if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\DriverDashboard.vbs" (
    echo ✅ يشتغل تلقائياً مع Windows
) else (
    echo ⚠️ لم نتمكن من الإضافة التلقائية
)

REM Start daemon
echo.
start /B wscript run_hidden.vbs >nul 2>&1
timeout /t 5 /nobreak >nul

REM Verify
curl -s http://localhost:8000/login >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ السيرفر شغال: http://localhost:8000
) else (
    echo ⚠️ السيرفر لسه بيشتغل — افتح الرابط بعد شوية
)

echo.
echo ==========================================
echo   ✅ تم! الرابط: http://localhost:8000
echo ==========================================
echo.
echo صاحب العربية:  رقم العربية + التلفون
echo السواق:        رقم الموبايل + كود OTP
echo.
echo لإيقاف السيرفر: stop_server.bat
echo.
pause
