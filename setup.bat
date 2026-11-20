@echo off
REM ==========================================================================
REM  Da RoastBox - OPTIONAL frontend developer setup for Windows 10 / 11 (x64)
REM
REM  You do NOT need this script to run the app. RUN.bat / server.py serve the
REM  prebuilt frontend/build folder directly - no Node.js or Yarn required.
REM  Run this only if you want to edit the frontend's React source and rebuild
REM  it with Yarn.
REM
REM  Why this script does its own thing instead of a plain "yarn install"
REM    A plain "yarn install --frozen-lockfile" always fails here:
REM    frontend/package.json pins two @emergentbase dev packages to tarballs on
REM    assets.emergent.sh, a host that no longer resolves. Those packages only
REM    provide the Emergent dev overlay and visual editor, and craco.config.js
REM    already loads them defensively. So this removes just those two
REM    devDependencies, installs, then puts package.json back unchanged.
REM
REM  yarn is required, not just preferred. The repo pins 46 transitive
REM  versions through the yarn-only "resolutions" field, and npm hoists
REM  differently: ajv 6 lands where ajv-keywords needs ajv 8 and the build dies
REM  with MODULE_NOT_FOUND. yarn is the tested installer here.
REM
REM  Usage:  setup.bat        install only
REM          setup.bat run    install, then start both servers
REM ==========================================================================
setlocal enabledelayedexpansion
title Da RoastBox - Setup
cd /d "%~dp0"
if errorlevel 1 (
  echo.
  echo Cannot open the project folder.
  echo Extract the whole ZIP to a local folder such as C:\RoastBox,
  echo then run setup.bat again from inside that folder.
  echo.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo   Da RoastBox - local setup
echo ============================================================
echo.

REM ---------------------------------------------------------------- Python
REM Prefer a version this project was built against when several are installed,
REM since the `py` launcher would otherwise pick the newest one. 3.14 is
REM supported too - every pinned dependency has a cp314 Windows wheel - so the
REM fallback chain ends at it rather than failing.
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
if not defined PYEXE goto nopython
for /f "delims=" %%v in ('%PYEXE% --version 2^>^&1') do echo    %%v
REM 3.11 is the floor: older interpreters have no wheels for several pinned
REM packages. Newer versions are allowed - 3.14 ships wheels for every pinned
REM dependency on Windows x64, so refusing it would be wrong.
%PYEXE% -c "import sys;sys.exit(0 if sys.version_info[:2]>=(3,11) else 1)"
if errorlevel 1 goto badpython
%PYEXE% -c "import sys;sys.exit(0 if sys.version_info[:2]<=(3,13) else 1)"
if errorlevel 1 echo    Note: Python 3.14+ is newer than the versions this project was built against. It is expected to work.

REM ---------------------------------------------------------------- venv
if not exist ".venv\Scripts\python.exe" (
  echo ==^> Creating virtual environment ^(.venv^)
  %PYEXE% -m venv .venv
  if errorlevel 1 goto novenv
)
call ".venv\Scripts\activate.bat"
python -m pip install --quiet --upgrade pip
if errorlevel 1 goto nopip

echo ==^> Installing backend dependencies ^(a few minutes^)
python -m pip install --quiet -r backend\requirements.txt
if errorlevel 1 goto nodeps

REM ---------------------------------------------------------------- Node
echo ==^> Checking Node.js
where node >nul 2>&1
if errorlevel 1 goto nonode
for /f "delims=" %%v in ('node --version') do set "NODEV=%%v"
echo    Node !NODEV!
set "NODEMAJOR=!NODEV:v=!"
for /f "tokens=1 delims=." %%a in ("!NODEMAJOR!") do set "NODEMAJOR=%%a"
if !NODEMAJOR! LSS 18 goto oldnode
if !NODEMAJOR! GEQ 25 (
  for /f "delims=" %%v in ('node --version') do echo    WARNING: Node %%v is newer than this project was built against.
  echo             If "yarn start" fails, install Node 20 or 22 LTS.
  echo.
)

echo ==^> Checking yarn
where yarn >nul 2>&1
if errorlevel 1 (
  echo    yarn not found. Installing it globally with npm...
  call npm install -g yarn
  if errorlevel 1 goto noyarn
  where yarn >nul 2>&1
  if errorlevel 1 goto noyarn
)
for /f "delims=" %%v in ('yarn --version') do echo    yarn %%v

REM ---------------------------------------------------------------- frontend
echo ==^> Removing the two unreachable @emergentbase dev packages
cd frontend
if exist package.json.bak del /q package.json.bak
if exist yarn.lock.bak del /q yarn.lock.bak
copy /y package.json package.json.bak >nul
%PYEXE% ..\scripts\prepare_package_json.py package.json
if errorlevel 1 goto badpkg

REM Some networks cannot reach registry.yarnpkg.com, and yarn 1 ignores
REM --registry for URLs the lockfile already resolved. npmjs.org serves the
REM same tarballs with the same sha1 fragments, so a host swap is safe.
copy /y yarn.lock yarn.lock.bak >nul
%PYEXE% ..\scripts\fix_lockfile_registry.py yarn.lock

echo ==^> Installing frontend dependencies ^(this is the slow part^)
call yarn install --ignore-engines --non-interactive
if errorlevel 1 goto retryyarn
goto yarnok

:retryyarn
echo.
echo    First attempt failed. Restoring the original lockfile and retrying.
if exist yarn.lock.bak (
  move /y yarn.lock.bak yarn.lock >nul
  call yarn install --ignore-engines --non-interactive
  if errorlevel 1 goto yarnfailed
) else (
  goto yarnfailed
)

:yarnok
REM Restore both files so the project is left exactly as it shipped.
if exist yarn.lock.bak move /y yarn.lock.bak yarn.lock >nul
move /y package.json.bak package.json >nul
cd ..

REM ---------------------------------------------------------------- .env
echo ==^> Preparing backend\.env
%PYEXE% scripts\make_env.py
if errorlevel 1 goto noenv

echo.
echo ============================================================
echo   Frontend build tools are ready.
echo ============================================================
echo.
echo  This only prepared Node/Yarn so you can edit and rebuild the
echo  frontend's React source. To just RUN the app, you do not need this
echo  script at all - double-click RUN.bat in the project root instead;
echo  it serves the prebuilt frontend\build folder and needs no database.
echo.
echo  To develop the frontend with live reload:
echo    Window 1:  cd /d "%~dp0backend" ^&^& ..\.venv\Scripts\python run_server.py --dev
echo    Window 2:  cd /d "%~dp0frontend" ^&^& yarn start
echo  Then open http://localhost:3000 and click "Browse as guest".
echo.
echo  When you're happy with your changes, rebuild the shipped copy with:
echo    cd /d "%~dp0frontend" ^&^& set CI=false ^&^& yarn build
echo.
echo  Your data is NOT reset by this script. Re-running setup.bat is safe.
echo ============================================================
echo.

if /i "%~1"=="run" goto dorun
goto done

:dorun
echo ==^> Starting backend in a new window
start "RoastBox API" /D "%~dp0backend" cmd /k ..\.venv\Scripts\uvicorn server:app --port 8001
timeout /t 4 /nobreak >nul
echo ==^> Starting frontend in this window
cd /d "%~dp0frontend"
call yarn start
goto done

REM ================================================================= errors
:nopython
echo.
echo ERROR: Python 3.11 or newer was not found.
echo        Install it from https://www.python.org/downloads/windows/
echo        During setup TICK "Add python.exe to PATH".
echo        Prefer the python.org installer over the Microsoft Store build.
echo.
pause
exit /b 1

:badpython
echo.
echo ERROR: Python 3.11 or newer is required.
echo        You have an older interpreter, which has no wheels for several
echo        pinned packages. Install Python 3.13 or 3.14 from
echo        https://www.python.org/downloads/windows/ and run setup.bat again.
echo.
pause
exit /b 1

:novenv
echo.
echo ERROR: Could not create the virtual environment .venv
echo        Check that the folder is writable and that antivirus is not
echo        blocking python.exe. Avoid running this from inside the ZIP viewer.
echo.
pause
exit /b 1

:nopip
echo.
echo ERROR: Could not upgrade pip.
echo        Check your internet connection or corporate proxy settings.
echo.
pause
exit /b 1

:nodeps
echo.
echo ERROR: Backend dependency install failed.
echo        Scroll up for the failing package.
echo        Common causes: no internet, a proxy, antivirus blocking pip.
echo.
pause
exit /b 1

:nonode
echo.
echo ERROR: Node.js 18 or newer was not found.
echo        Install the LTS build from https://nodejs.org/en/download
echo        Node 20 or 22 LTS are the safest choices for this project.
echo        Close this window, reopen a new Command Prompt, and retry so the
echo        updated PATH takes effect.
echo.
pause
exit /b 1

:oldnode
echo.
echo ERROR: Your Node version is too old. This project needs Node 18 or newer.
echo        Install Node 20 or 22 LTS from https://nodejs.org/en/download
echo.
pause
exit /b 1

:noyarn
echo.
echo ERROR: yarn could not be installed automatically.
echo        Install Node 18+ from https://nodejs.org first, then run:
echo            npm install -g yarn
echo        and run setup.bat again.
echo.
pause
exit /b 1

:badpkg
echo.
echo ERROR: Could not rewrite frontend\package.json
echo        Restoring the original file.
move /y package.json.bak package.json >nul
cd ..
pause
exit /b 1

:yarnfailed
echo.
echo ERROR: yarn install failed. Scroll up for the real error.
echo        Common causes: no internet, a proxy, antivirus locking node_modules,
echo        or an antivirus "protected folder" policy blocking writes.
echo        If it mentions EPERM or EACCES, exclude the project folder from
echo        real-time scanning and retry.
echo.
if exist yarn.lock.bak move /y yarn.lock.bak yarn.lock >nul
move /y package.json.bak package.json >nul
cd ..
pause
exit /b 1

:noenv
echo.
echo ERROR: Could not create backend\.env
echo        Check that backend\.env.example exists.
echo.
pause
exit /b 1

:done
pause
