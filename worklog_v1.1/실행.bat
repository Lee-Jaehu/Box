@echo off
rem Worklog manual launcher. Order: Conda env -> embedded Python -> .venv (see scripts\select-python.ps1).
rem No auto-start at boot, no service, no auto-restart. If the app fails, the cause is printed and it stops.
rem Test hooks: WORKLOG_DRY_RUN=1 prints the selected Python and exits. WORKLOG_NO_PAUSE=1 skips the final pause.
chcp 65001 >nul
setlocal EnableExtensions
set "APP_ROOT=%~dp0"
if "%APP_ROOT:~-1%"=="\" set "APP_ROOT=%APP_ROOT:~0,-1%"
set "PY="
set "PY_KIND="
for /f "usebackq tokens=1,2,* delims=|" %%A in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%APP_ROOT%\scripts\select-python.ps1" -AppRoot "%APP_ROOT%"`) do if "%%A"=="OK" call :remember "%%B" "%%C"
if not defined PY goto :no_python
echo [Worklog] Python (%PY_KIND%): %PY%
if "%WORKLOG_DRY_RUN%"=="1" exit /b 0
for %%I in ("%PY%") do set "PY_DIR=%%~dpI"
set "PATH=%PY_DIR%;%PY_DIR%Library\bin;%PY_DIR%Scripts;%PATH%"
set "PYTHONUTF8=1"
cd /d "%APP_ROOT%"
"%PY%" "%APP_ROOT%\backend\run.py"
set "RC=%ERRORLEVEL%"
echo.
echo [Worklog] 서버가 종료되었습니다. (종료 코드 %RC%) 자동으로 다시 시작하지 않습니다.
if not "%RC%"=="0" echo [Worklog] 오류가 났다면 위 메시지와 data\logs\worklog.log 를 확인하세요. 다른 Python 으로 자동 재실행하지 않습니다.
if not "%WORKLOG_NO_PAUSE%"=="1" pause
exit /b %RC%

:remember
set "PY_KIND=%~1"
set "PY=%~2"
exit /b 0

:no_python
echo.
echo [Worklog] 사용할 수 있는 Python 환경을 찾지 못했습니다. 위에 나열된 후보를 확인하세요.
echo           Conda 환경 'worklog' / runtime\python\python.exe / .venv 순서로 찾습니다.
echo           처음 설치라면 같은 폴더의 초기설정.bat 을 먼저 실행하세요.
if not "%WORKLOG_NO_PAUSE%"=="1" pause
exit /b 1
