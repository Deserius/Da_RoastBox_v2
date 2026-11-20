@echo off
REM Double-click to start Da RoastBox and open it in your default browser.
REM Runs the backend from .venv and launches the frontend dev server.
setlocal
cd /d "%~dp0"
title Da RoastBox

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo Python environment not found. Running setup first...
  echo.
  call setup.bat
  if errorlevel 1 goto fail
)
if not exist "frontend\node_modules" (
  echo.
  echo Frontend dependencies not found. Running setup first...
  echo.
  call setup.bat
  if errorlevel 1 goto fail
)

echo.
echo Starting Da RoastBox...
echo   API      http://localhost:8001
echo   App      http://localhost:3000
echo   Passphrase for Settings: roastbox
echo.
cd backend
..\.venv\Scripts\python run_server.py
goto end

:fail
echo.
echo Setup did not complete. Read the message above.
pause
exit /b 1

:end
pause
