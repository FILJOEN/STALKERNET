@echo off
rem Builds StalkerNet.exe (no Python needed to RUN it). Run this ONCE on your own PC.
rem Needs Python + PyQt5 here:  pip install PyQt5 pyinstaller
cd /d "%~dp0"
pip install PyQt5 pyinstaller
pyinstaller --noconfirm --clean --noconsole --onedir --name StalkerNet stalkernet.py
echo.
echo Done. Your program is in dist\StalkerNet\ (StalkerNet.exe inside).
echo Now copy these next to StalkerNet.exe in that folder: messages, images, vids, sounds, fonts, settings.txt
echo and launch_stalkernet.bat
pause



                                                changes made
@echo off 
rem Builds StalkerNet.exe (no Python needed to RUN it). Run this on your own PC.
rem Needs Python + PyQt5 here:  pip install PyQt5 pyinstaller
rem Put your icon next to this file and name it StalkerNet.ico - it is used automatically.
cd /d "%~dp0"
pip install PyQt5 pyinstaller

if exist "StalkerNet.ico" goto withicon

echo.
echo No StalkerNet.ico found next to this file - building with the default icon.
pyinstaller --noconfirm --clean --noconsole --onedir --name StalkerNet stalkernet.py
goto finished

:withicon
echo.
echo Using the icon StalkerNet.ico
pyinstaller --noconfirm --clean --noconsole --onedir --icon=StalkerNet.ico --name StalkerNet stalkernet.py

:finished
echo.
echo Done. Your program is in dist\StalkerNet\ (StalkerNet.exe inside).
echo Check the date of dist\StalkerNet\StalkerNet.exe - it must be from just now.
echo Now copy these next to StalkerNet.exe in that folder: messages, images, vids, sounds, fonts, settings.txt
echo and launch_stalkernet.bat
pause
