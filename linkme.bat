@echo off
chcp 65001 >nul
set CWD=%~dp0
if "%CWD:~-1%"=="\" set CWD=%CWD:~0,-1%

set PROJECT_NAME=Steam Manifest 更新工具
set PROJECT_DESC=自動讀取並更新 Steam Lua 設定檔，取得最新版的 Depot ID 與 Manifest ID。支援鎖定資料夾功能。
set EXEC_FILE=%CWD%\打開點我！.bat

echo Registering "%PROJECT_NAME%" to AI Tool Launcher...
python g:\python\toolLauncher\register_api.py --name "%PROJECT_NAME%" --desc "%PROJECT_DESC%" --exec "%EXEC_FILE%" --cwd "%CWD%"

echo.
echo Registration complete! You can now close this window.
pause
