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
