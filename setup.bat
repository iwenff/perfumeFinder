@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
py -3.12 -c "import sys; sys.exit(sys.version_info[:2] != (3, 12))" >nul 2>&1
if not errorlevel 1 goto launcher
python -c "import sys; sys.exit(sys.version_info[:2] != (3, 12))" >nul 2>&1
if errorlevel 1 goto missing
if not exist ".venv\Scripts\python.exe" python -m venv .venv
goto install

:launcher
if not exist ".venv\Scripts\python.exe" py -3.12 -m venv .venv

:install
if not exist ".venv\Scripts\python.exe" goto failed
".venv\Scripts\python.exe" -c "import sys; sys.exit(sys.version_info[:2] != (3, 12))"
if errorlevel 1 goto wrongenv
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m app.setup
if errorlevel 1 goto failed
pause
exit /b 0

:missing
echo Установите Python 3.12 по инструкции README.md.
goto failed

:wrongenv
echo Переименуйте папку .venv и снова запустите setup.bat.

:failed
pause
exit /b 1
