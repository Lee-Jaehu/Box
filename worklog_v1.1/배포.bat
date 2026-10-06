@echo off
chcp 65001 >nul
rem Worklog deploy: copy the new program version into another folder (test PC / operating folder) WITHOUT touching its data and settings.
rem   배포.bat "C:\Users\me\Desktop\tft_test"            apply
rem   배포.bat "C:\Users\me\Desktop\tft_test" -DryRun    only list what would change
rem Preserved in the target: data\, data_test\, config\config.json, .venv\, runtime\, backups. The target's server must be stopped.
rem Test hook: WORKLOG_NO_PAUSE=1 skips the final pause.
setlocal EnableExtensions
set "APP_ROOT=%~dp0"
if "%APP_ROOT:~-1%"=="\" set "APP_ROOT=%APP_ROOT:~0,-1%"
set "TARGET=%~1"
if "%TARGET%"=="" (
  echo [Worklog] 새 버전을 반영할 대상 폴더를 입력하세요. ^(예: C:\Users\me\Desktop\tft_test^)
  set /p "TARGET=대상 폴더: "
)
if "%TARGET%"=="" (
  echo [Worklog] 대상 폴더가 없어 중단합니다.
  if not "%WORKLOG_NO_PAUSE%"=="1" pause
  exit /b 1
)
set "EXTRA="
if /I "%~2"=="-DryRun" set "EXTRA=-DryRun"
echo [Worklog] 반영 대상: %TARGET%
echo           데이터^(data^)와 설정^(config\config.json^)은 건드리지 않습니다.
powershell -NoProfile -ExecutionPolicy Bypass -File "%APP_ROOT%\scripts\deploy.ps1" -Target "%TARGET%" %EXTRA%
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo [Worklog] 완료. 대상 폴더의 서버를 다시 시작하세요. 화면이 안 바뀌면 브라우저를 새로고침하세요.
) else (
  echo [Worklog] 반영 실패 ^(종료 코드 %RC%^). 위 메시지를 확인하세요. 데이터는 변경되지 않았습니다.
)
if not "%WORKLOG_NO_PAUSE%"=="1" pause
exit /b %RC%
