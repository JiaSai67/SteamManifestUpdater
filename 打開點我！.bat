@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo 正在檢查並安裝所需套件...
python -m pip install -r requirements.txt >nul 2>&1

set PYTHONPATH=src
python src\main.py > startup.log 2>&1
