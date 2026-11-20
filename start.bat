@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Da RoastBox - Prepared One Click Start
cd /d "%~dp0"
if errorlevel 1 (
  echo Cannot open the project folder. Extract the entire ZIP to a writable folder first.
  pause
  exit /b 1
)
if not exist "%~dp0install.py" (
  echo Project files are missing. Extract the entire ZIP, then double-click start.bat again.
  pause
  exit /b 1
)
echo Da RoastBox one-click start
echo Included dependencies are reused/unpacked locally. Missing components are restored or installed automatically.
echo API: 8001 - App: 3000 - Browser opens only after both are ready.
echo Existing settings, accounts, MongoDB and generated media are preserved.
echo.
rem Tail-chain to preserve paths containing percent signs.
"%~dp0install.bat" --start %*
