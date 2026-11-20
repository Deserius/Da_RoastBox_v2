@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Da RoastBox - Automatic Setup and Launch
pushd "%~dp0"
if errorlevel 1 (
  echo Cannot open this folder. Extract the complete ZIP to a writable local folder.
  pause
  exit /b 1
)
if not exist "%~dp0scripts\bootstrap_python.ps1" goto incomplete
if not exist "%~dp0deploy\windows-bootstrap.json" goto incomplete
rem Use the built-in Windows host, not a command downloaded from the PATH.
set "PS_HOST=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
rem Sysnative selects the x64 host when started by a 32-bit file manager.
if exist "%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe" set "PS_HOST=%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS_HOST%" (
  echo Windows PowerShell 5.1 is required. This launcher requires x64 Windows. Local MongoDB requires Windows 11 or Server 2022.
  echo Windows security or organizational policy may require administrator assistance.
  popd
  pause
  exit /b 1
)
echo Preparing the app automatically. Please leave this window open.
echo Internet is needed for missing dependencies; existing configuration and data are kept.
rem Bypass is process-only. Do NOT change the user's or machine's policy.
"%PS_HOST%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap_python.ps1" -ProjectRoot "%~dp0." %*
set "SETUP_RESULT=%errorlevel%"
popd
if not "%SETUP_RESULT%"=="0" (
  echo.
  echo Setup or startup stopped. Read the error above; no database files were deleted.
  echo Retry LAUNCH_DA_ROASTBOX.bat after resolving the reported issue.
  echo Existing data is not reset. See docs\LOCAL_INSTALL.md for recovery.
  pause
  exit /b %SETUP_RESULT%
)
echo.
echo Local web session completed. MongoDB and saved data were left intact.
pause
exit /b 0

:incomplete
echo Required setup files are missing. Use Extract All on the complete ZIP first.
echo Then double-click LAUNCH_DA_ROASTBOX.bat in the extracted folder.
popd
pause
exit /b 1
