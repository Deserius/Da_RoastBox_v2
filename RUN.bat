@echo off
REM Double-click this to start Da RoastBox and open it in your default browser.
REM All first-run setup (virtual environment, package install) is handled by
REM server.py itself - this just finds a Python interpreter and hands off to it.
setlocal EnableExtensions
cd /d "%~dp0"
if errorlevel 1 (
  echo.
  echo Cannot open the project folder. Extract the whole ZIP to a local
  echo folder such as C:\RoastBox, then run RUN.bat again from inside it.
  pause
  exit /b 1
)
title Da RoastBox

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

%PYEXE% server.py %*
if errorlevel 1 (
  echo.
  pause
)
