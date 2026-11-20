@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Da RoastBox - One Click Launch
if not exist "%~dp0start.bat" (
  echo Extract ALL files from the ZIP first, then double-click LAUNCH_DA_ROASTBOX.bat.
  echo Do not run this file inside the ZIP viewer.
  pause
  exit /b 1
)
rem Tail-chain: no CALL re-expansion of percent signs in the project path.
"%~dp0start.bat" %*
