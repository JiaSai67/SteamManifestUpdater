@echo off
echo Running Fast Build (Directory Mode)...
pyinstaller -D -w --noconfirm --name SteamManifestUpdater --distpath exegogo\dist --workpath exegogo\build --specpath exegogo src\main.py
echo Build Complete! Check exegogo\dist\SteamManifestUpdater
pause
