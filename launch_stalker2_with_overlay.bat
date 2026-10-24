@echo off
rem ================================================================
rem  Starts the Stalker overlay, then starts the game Steam hands over (%*).
rem
rem  Steam > Stalker 2 > Properties > General > Launch Options:
rem     "C:\full\path\to\launch_stalker2_with_overlay.bat" %command%
rem  (use the REAL folder where this .bat and stalker_overlay_display.py are)
rem
rem  Keep this .bat in the SAME folder as stalker_overlay_display.py.
rem  Problems? open overlay_log.txt in this folder - it shows what went wrong.
rem ================================================================

rem --- If Steam cannot find Python, put its full path here, e.g.
rem     set "PYTHON_EXE=C:\Users\YourName\AppData\Local\Programs\Python\Python312\pythonw.exe"
set "PYTHON_EXE="

cd /d "%~dp0"

rem Steam starts this with a minimal PATH, so look for Python in a few places
if not defined PYTHON_EXE for /f "delims=" %%P in ('where pythonw 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE for /f "delims=" %%P in ('where pyw 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do if exist "%%D\pythonw.exe" set "PYTHON_EXE=%%D\pythonw.exe"

echo [%date% %time%] launcher started > "%~dp0overlay_log.txt"
echo python: %PYTHON_EXE% >> "%~dp0overlay_log.txt"
echo game command: %* >> "%~dp0overlay_log.txt"

if not defined PYTHON_EXE (
    echo Python was not found. Set PYTHON_EXE at the top of this file. >> "%~dp0overlay_log.txt"
) else (
    start "" "%PYTHON_EXE%" "%~dp0stalkernet.py" --with-game
)

rem Start the game exactly as Steam asked
%*


                                                  !!!changes made!!!

@echo off
rem ================================================================
rem  Starts the Stalker overlay, then starts the game Steam hands over (%*).
rem
rem  Steam > Stalker 2 > Properties > General > Launch Options:
rem     "C:\full\path\to\launch_stalker2_with_overlay.bat" %command%
rem  (use the REAL folder where this .bat and stalker_overlay_display.py are)
rem
rem  Keep this .bat in the SAME folder as stalker_overlay_display.py.
rem  Problems? open overlay_log.txt in this folder - it shows what went wrong.
rem ================================================================

rem --- If Steam cannot find Python, put its full path here, e.g.
rem     set "PYTHON_EXE=C:\Users\YourName\AppData\Local\Programs\Python\Python312\pythonw.exe"
set "PYTHON_EXE="

cd /d "%~dp0"

rem Steam starts this with a minimal PATH, so look for Python in a few places
if not defined PYTHON_EXE for /f "delims=" %%P in ('where pythonw 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE for /f "delims=" %%P in ('where pyw 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do if exist "%%D\pythonw.exe" set "PYTHON_EXE=%%D\pythonw.exe"

echo [%date% %time%] launcher started > "%~dp0overlay_log.txt"
echo python: %PYTHON_EXE% >> "%~dp0overlay_log.txt"
echo game command: %* >> "%~dp0overlay_log.txt"

if not defined PYTHON_EXE (
    echo Python was not found. Set PYTHON_EXE at the top of this file. >> "%~dp0overlay_log.txt"
) else (
    start "" "%PYTHON_EXE%" "%~dp0stalkernet.py" --with-game
)

rem Start the game exactly as Steam asked
%*
