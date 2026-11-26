@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "version_check=import sys; sys.exit(sys.version_info[:2] not in ((3, 12), (3, 13)))"
if exist ".venv\Scripts\python.exe" goto install

py -3.13 -c "%version_check%" >nul 2>&1
if not errorlevel 1 (
    py -3.13 -m venv .venv
    goto install
)
py -3.12 -c "%version_check%" >nul 2>&1
if not errorlevel 1 (
    py -3.12 -m venv .venv
    goto install
)
python -c "%version_check%" >nul 2>&1
if errorlevel 1 goto missing
python -m venv .venv

:install
if not exist ".venv\Scripts\python.exe" goto failed
".venv\Scripts\python.exe" -c "%version_check%"
if errorlevel 1 goto wrongenv
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m app.setup
if errorlevel 1 goto failed
pause
exit /b 0

:missing
echo Установите Python 3.13 или 3.12 по инструкции README.md.
goto failed

:wrongenv
echo Для .venv нужен Python 3.13 или 3.12. Переименуйте папку .venv и снова запустите setup.bat.

:failed
pause
exit /b 1
