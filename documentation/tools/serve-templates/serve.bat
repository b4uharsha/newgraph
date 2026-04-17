@echo off
REM Graph OLAP Platform documentation -- local server launcher (Windows).
REM
REM Double-click this file to start a tiny HTTP server rooted at this folder
REM and open the docs in your default browser. The server runs until you
REM close this window.
REM
REM Why this exists: Chrome blocks ES module imports from file:// URLs by
REM security policy, so opening index.html directly does not work in Chrome.
REM Firefox and Edge (if recent) may be more permissive.

cd /d "%~dp0"

set PORT=4321
set URL=http://localhost:%PORT%/

where py >nul 2>nul
if %ERRORLEVEL% == 0 (
    set PY=py -3
    goto run
)

where python >nul 2>nul
if %ERRORLEVEL% == 0 (
    set PY=python
    goto run
)

echo ERROR: Python 3 is required but was not found on PATH.
echo Install Python from https://www.python.org/downloads/ and try again.
pause
exit /b 1

:run
echo Starting docs server at %URL%
echo Press Ctrl+C in this window to stop the server.
echo.

start "" %URL%

%PY% -m http.server %PORT% --bind 127.0.0.1
