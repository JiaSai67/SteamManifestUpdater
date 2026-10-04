@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Steam Manifest Updater 2.0 啟動中...

echo ===================================================
echo   Steam Manifest Updater 2.0 (多源極速版)
echo   正在準備執行環境，請稍候...
echo ===================================================
echo.

:: 1. 檢查系統 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [錯誤] 系統未檢測到 Python 環境！
    echo 請先安裝 Python 3.8 或以上版本，並勾選 "Add Python to PATH"。
    echo 下載網址: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

:: 2. 自動檢查與建立獨立虛擬環境 (.venv) 避免依賴衝突
if not exist ".venv\Scripts\python.exe" (
    echo [資訊] 首次運行，正在建立獨立虛擬環境 (.venv)...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [警告] 建立虛擬環境失敗，改用系統 Python 運行。
        set "PY_EXEC=python"
    ) else (
        set "PY_EXEC=.venv\Scripts\python.exe"
        echo [資訊] 正在自動安裝 2.0 輕量依賴套件 (pywebview, requests, gdown)...
        .venv\Scripts\pip install --upgrade pip >nul 2>&1
        .venv\Scripts\pip install -r requirements.txt
    )
) else (
    set "PY_EXEC=.venv\Scripts\python.exe"
)

:: 3. 啟動 2.0 主程式
echo [資訊] 正在啟動 2.0 櫻花流光現代化介面...
%PY_EXEC% src\main.py

if %errorlevel% neq 0 (
    echo.
    echo [提示] 程式異常退出，請檢查上述錯誤訊息。
    pause
)
