@echo off
chcp 65001 >nul
cd /d "%~dp0"
set CWD=%~dp0
if "%CWD:~-1%"=="\" set CWD=%CWD:~0,-1%

set PROJECT_NAME=Steam Manifest 更新工具2.0.1
set PROJECT_DESC=全新 2.0.1 櫻花流光極速版：多源 Manifest (Ryuu + Lua.tools) 自動比對、組隊系統全自動一鍵安裝、純 AppID 驅動與全自動入庫
set EXEC_FILE=%CWD%\src\main.py

echo Registering "%PROJECT_NAME%" to AI Tool Launcher...
if exist "..\register_api.py" (
    python "..\register_api.py" --name "%PROJECT_NAME%" --desc "%PROJECT_DESC%" --exec "%EXEC_FILE%" --cwd "%CWD%"
) else if exist "g:\python\toolLauncher\register_api.py" (
    python "g:\python\toolLauncher\register_api.py" --name "%PROJECT_NAME%" --desc "%PROJECT_DESC%" --exec "%EXEC_FILE%" --cwd "%CWD%"
)

echo.
echo Registration complete! You can now close this window.
