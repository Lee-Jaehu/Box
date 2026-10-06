@echo off
chcp 65001 >nul
rem Worklog AI connection check: sends a few request shapes to the AI server and prints which ones fail (see backend\ai_check.py).
rem The API key is never printed.
setlocal EnableExtensions
set "APP_ROOT=%~dp0"
if "%APP_ROOT:~-1%"=="\" set "APP_ROOT=%APP_ROOT:~0,-1%"
set "PY="
set "PY_KIND="
for /f "usebackq tokens=1,2,* delims=|" %%A in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%APP_ROOT%\scripts\select-python.ps1" -AppRoot "%APP_ROOT%"`) do if "%%A"=="OK" call :remember "%%B" "%%C"
if not defined PY goto :no_python
for %%I in ("%PY%") do set "PY_DIR=%%~dpI"
set "PATH=%PY_DIR%;%PY_DIR%Library\bin;%PY_DIR%Scripts;%PATH%"
set "PYTHONUTF8=1"
cd /d "%APP_ROOT%"
"%PY%" "%APP_ROOT%\backend\ai_check.py"
set "RC=%ERRORLEVEL%"
echo.
echo [Worklog] AI 점검이 끝났습니다. 위 결과(키는 출력되지 않음)를 공유해 주세요.
if not "%WORKLOG_NO_PAUSE%"=="1" pause
exit /b %RC%

:remember
set "PY_KIND=%~1"
set "PY=%~2"
exit /b 0

:no_python
echo [Worklog] 사용할 수 있는 Python 환경을 찾지 못했습니다. 초기설정.bat 을 먼저 실행하세요.
if not "%WORKLOG_NO_PAUSE%"=="1" pause
exit /b 1
