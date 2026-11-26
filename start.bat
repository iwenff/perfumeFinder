@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Сначала запустите setup.bat.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m app.main
set "bot_exit=%errorlevel%"
if not "%bot_exit%"=="0" pause
exit /b %bot_exit%
