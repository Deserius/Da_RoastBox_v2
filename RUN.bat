@echo off
REM Double-click this to start Da RoastBox and open it in your default browser.
REM First run: creates a Python virtual environment and installs the backend
REM packages (a couple of minutes). No MongoDB, Node.js, or Yarn needed - the
REM database is built in and the frontend ships prebuilt.
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
if errorlevel 1 (
  echo.
  echo Cannot open the project folder. Extract the whole ZIP to a local
  echo folder such as C:\RoastBox, then run RUN.bat again from inside it.
  pause
  exit /b 1
)
title Da RoastBox

if exist ".venv\Scripts\python.exe" goto haveenv

echo.
echo ============================================================
echo   Da RoastBox - first-time setup
echo ============================================================
echo.
echo ==^> Checking Python
set "PYEXE="
for %%v in (3.13 3.12 3.11 3.14) do (
  if not defined PYEXE (
    py -%%v --version >nul 2>&1
    if not errorlevel 1 set "PYEXE=py -%%v"
  )
)
if not defined PYEXE (
  py -3 --version >nul 2>&1
  if not errorlevel 1 set "PYEXE=py -3"
)
if not defined PYEXE (
  python --version >nul 2>&1
  if not errorlevel 1 set "PYEXE=python"
)
if not defined PYEXE (
  echo.
  echo Python was not found on this PC.
  echo Install Python 3.11, 3.12, 3.13, or 3.14 from https://python.org/downloads/
  echo ^(tick "Add python.exe to PATH" during install^), then run RUN.bat again.
  echo.
  pause
  exit /b 1
)
for /f "delims=" %%v in ('%PYEXE% --version 2^>^&1') do echo    %%v

echo ==^> Creating a virtual environment ^(.venv^)
%PYEXE% -m venv .venv
if errorlevel 1 (
  echo.
  echo Could not create .venv. See the error above.
  pause
  exit /b 1
)

echo ==^> Installing Python packages ^(a few minutes the first time^)
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -r backend\requirements.txt
if errorlevel 1 (
  echo.
  echo Could not install the Python packages. See the error above.
  echo You can retry with:  .venv\Scripts\python -m pip install -r backend\requirements.txt
  pause
  exit /b 1
)
echo ==^> Setup complete
echo.

:haveenv
echo.
echo Starting Da RoastBox...
echo   Set your API keys any time with:  python install.py
echo   Settings console passphrase: roastbox
echo.
".venv\Scripts\python.exe" server.py %*
if errorlevel 1 (
  echo.
  pause
)
