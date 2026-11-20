@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Da RoastBox - Prepared One Click Launch
if not exist "%~dp0start.bat" (
  echo Extract ALL files from the download first, then double-click thelaunch.bat.
  pause
  exit /b 1
)
rem Tail-chain, without CALL's second expansion of percent signs in paths.
"%~dp0start.bat" %*
