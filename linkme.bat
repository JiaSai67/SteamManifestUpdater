@echo off
chcp 65001 >nul
cd /d "%~dp0"
set CWD=%~dp0
if "%CWD:~-1%"=="\" set CWD=%CWD:~0,-1%

set PROJECT_NAME=Steam Manifest 更新工具2.0.13
set PROJECT_DESC=全新 2.0.13 櫻花流光極速版：下載前檔頭與 PICS Token 完整性防呆驗證、缺陷自動直切 HubcapDB 與意外配額獨立通知、多源 Manifest (Ryuu + Lua.tools + HubcapDB) 自動比對、友邀代碼雙打包與組隊一鍵安裝
set EXEC_FILE=%CWD%\src\main.py

echo Registering "%PROJECT_NAME%" to AI Tool Launcher...
if exist "..\register_api.py" (
    python "..\register_api.py" --name "%PROJECT_NAME%" --desc "%PROJECT_DESC%" --exec "%EXEC_FILE%" --cwd "%CWD%"
) else if exist "g:\python\toolLauncher\register_api.py" (
    python "g:\python\toolLauncher\register_api.py" --name "%PROJECT_NAME%" --desc "%PROJECT_DESC%" --exec "%EXEC_FILE%" --cwd "%CWD%"
)

echo.
echo Registration complete! You can now close this window.
