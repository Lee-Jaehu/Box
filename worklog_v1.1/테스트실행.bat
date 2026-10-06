@echo off
rem Worklog TEST launcher: same program, but a different port and a separate data folder so it never touches the real server/data.
rem   테스트실행.bat            port 8100, data folder  <program folder>\data_test
rem   테스트실행.bat 8200       port 8200
rem To change the defaults permanently, edit the two "set" lines below.
rem Test hooks: WORKLOG_DRY_RUN=1 prints the selected Python and exits. WORKLOG_NO_PAUSE=1 skips the final pause.
chcp 65001 >nul
setlocal EnableExtensions
set "APP_ROOT=%~dp0"
if "%APP_ROOT:~-1%"=="\" set "APP_ROOT=%APP_ROOT:~0,-1%"

set "TEST_PORT=8100"
set "TEST_DATA_DIR=%APP_ROOT%\data_test"
if not "%~1"=="" set "TEST_PORT=%~1"

powershell -NoProfile -ExecutionPolicy Bypass -File "%APP_ROOT%\scripts\check-port.ps1" -Port %TEST_PORT%
set "PORT_RC=%ERRORLEVEL%"
if "%PORT_RC%"=="2" (
  echo [Worklog 테스트] 포트 %TEST_PORT% 는 이미 다른 프로그램이 사용 중입니다. 다른 포트로 실행하세요. 예: 테스트실행.bat 8200
  if not "%WORKLOG_NO_PAUSE%"=="1" pause
  exit /b 2
)
if "%PORT_RC%"=="3" (
  echo [Worklog 테스트] 포트 %TEST_PORT% 는 Windows 가 예약한 포트라 사용할 수 없습니다. 다른 포트로 실행하세요. 예: 테스트실행.bat 8200
  echo                  예약 범위 확인: netsh interface ipv4 show excludedportrange protocol=tcp
  if not "%WORKLOG_NO_PAUSE%"=="1" pause
  exit /b 3
)

rem WORKLOG_* environment variables override config\config.json (see README). The real server's data folder is never used.
set "WORKLOG_PORT=%TEST_PORT%"
set "WORKLOG_DATA_DIR=%TEST_DATA_DIR%"
rem BACKUP_DIR in config.json would otherwise send test backups into the real server's backup folder, so pin it inside the test data folder.
set "WORKLOG_BACKUP_DIR=%TEST_DATA_DIR%\backups"
echo.
echo ================= Worklog 테스트 서버 =================
echo  포트        : %TEST_PORT%   (운영 서버와 별도)
echo  데이터 폴더 : %TEST_DATA_DIR%   (운영 데이터와 분리됨)
echo  백업 폴더   : %TEST_DATA_DIR%\backups   (운영 백업과 분리됨)
echo  주소        : http://localhost:%TEST_PORT%/
echo ========================================================
call "%APP_ROOT%\실행.bat"
exit /b %ERRORLEVEL%
