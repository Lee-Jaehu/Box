@echo off
chcp 65001 >nul
rem 주간업무 PPT 테스트 화면 실행 (Windows)
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (set PY=py -3) else (set PY=python)

if not exist ".venv\Scripts\python.exe" (
  echo [1/2] 가상환경을 만듭니다...
  %PY% -m venv .venv || goto :nopython
)

echo [2/2] 필요한 패키지를 확인합니다...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo.
  echo 패키지 설치에 실패했습니다. 사내 프록시 환경이면 아래처럼 다시 시도하세요.
  echo   .venv\Scripts\python.exe -m pip install --proxy http://프록시주소:포트 -r requirements.txt
  echo 또는 IT팀에 python-pptx, jsonschema, fonttools 설치를 요청하세요.
  pause
  exit /b 1
)

echo.
echo 브라우저가 열리지 않으면 http://127.0.0.1:8765 에 접속하세요. 종료는 이 창에서 Ctrl+C.
".venv\Scripts\python.exe" -m weekly_report serve
pause
exit /b 0

:nopython
echo Python 3.11 이상이 필요합니다. https://www.python.org 에서 설치하거나 IT팀에 요청하세요.
pause
exit /b 1
