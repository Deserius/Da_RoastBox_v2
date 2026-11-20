@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if errorlevel 1 exit /b 1
title Da RoastBox - Apply 21+ Roast Pipeline
echo Applying the requested OpenRouter Claude Sonnet 4.5 - GPT-4.1 - GPT-4o chain.
echo These are PAID models; provider account budgets still apply.
echo Existing keys, MongoDB, saved media and shows will be preserved.
echo Stop only your old web-server window first. Leave MongoDB running.
echo The installer will build the 21+ UI and open your browser when ready.
echo.
call "%~dp0install.bat" --configure-writer --start %*
exit /b %errorlevel%
