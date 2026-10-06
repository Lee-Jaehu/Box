@echo off
rem Worklog first-time setup: prepares a Python environment in the same order the launcher uses (Conda -> embedded -> venv).
rem   초기설정.bat                 auto (stops at the first option that works)
rem   초기설정.bat -Only venv      one option only (conda | embedded | venv)
rem   초기설정.bat -WheelDir D:\wheels   offline packages ("wheels" folder next to the program is used automatically)
rem   초기설정.bat -Dev            development PC (test packages, Node.js in the conda env)
rem   초기설정.bat -DryRun         show the plan only
rem Never changes the conda base environment, PATH, registry, firewall or services. Data and config are not touched.
rem Test hook: WORKLOG_NO_PAUSE=1 skips the final pause.
chcp 65001 >nul
setlocal EnableExtensions
set "APP_ROOT=%~dp0"
if "%APP_ROOT:~-1%"=="\" set "APP_ROOT=%APP_ROOT:~0,-1%"
echo [Worklog] 실행 환경 초기 설정을 시작합니다.
echo           순서: Conda 환경 -^> embedded Python(runtime\python) -^> .venv. 먼저 성공한 하나만 준비합니다.
echo           인터넷(또는 프록시)이 필요합니다. 오프라인이면 wheels 폴더를 프로그램 폴더에 두세요. 몇 분 걸릴 수 있습니다.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%APP_ROOT%\scripts\setup-env.ps1" -AppRoot "%APP_ROOT%" %*
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo [Worklog] 설정 완료. 이제 실행.bat 으로 서버를 시작하세요. 데이터와 설정 파일은 바꾸지 않았습니다.
  if not exist "%APP_ROOT%\config\config.json" echo           config\config.json 이 없습니다. config\config.example.json 을 복사해 포트·데이터 폴더를 정하세요.
) else (
  echo [Worklog] 설정하지 못했습니다 ^(종료 코드 %RC%^). 위의 [setup] 메시지에서 이유를 확인하세요.
  echo           인터넷 차단: 인터넷 되는 PC에서 scripts\make-wheelhouse.ps1 로 wheels 폴더를 만들어 복사한 뒤 다시 실행.
  echo           Python 없음: Miniconda 또는 python.org 의 Python 3.11 이상을 설치하거나 runtime\python 에 embeddable 패키지를 푸세요.
)
if not "%WORKLOG_NO_PAUSE%"=="1" pause
exit /b %RC%