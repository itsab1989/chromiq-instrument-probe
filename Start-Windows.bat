@echo off
REM ChromIQ instrument probe - Windows launcher. Double-click this file.
REM Pure ASCII on purpose: the console codepage mangles anything else.

cd /d "%~dp0"
cls
echo.
echo   ChromIQ instrument probe (Windows)
echo.

REM The tool may run as administrator, so Python is taken ONLY from an
REM installation "for all users" in Program Files, which only an administrator
REM can change. Never a "py" or "python" lying in this folder, on PATH, or in the
REM user's own AppData (review 2 re-check).
set "PYL="
for /d %%D in ("%ProgramFiles%\Python3*") do if exist "%%D\python.exe" set "PYL=%%D\python.exe"
if not defined PYL goto nopython
"%PYL%" -c "print()" >nul 2>&1
if not %errorlevel%==0 goto nopython
"%PYL%" instrument_probe.py --no-pause
goto done

:nopython
echo   Python 3 for all users was not found in Program Files.
echo.
echo   Please install it from:
echo.
echo       https://www.python.org/downloads/
echo.
echo   IMPORTANT: because this tool runs as administrator, Python must be
echo   installed for all users: in the installer choose "Customize
echo   installation", then tick "Install Python for all users" (it then goes
echo   into Program Files). Then double-click this file again.
echo.
echo   Please unpack this tool into a folder of its own (not straight into
echo   Downloads), because it may run as administrator.
echo.
pause
exit /b 1

REM --no-pause above: this file waits below, so the tool must not wait too.
:done
echo.
pause
