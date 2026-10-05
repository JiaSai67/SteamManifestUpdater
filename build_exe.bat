@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 編譯 Steam Manifest Updater 專屬啟動器

set "CSC=C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" (
    set "CSC=C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
)

if not exist "%CSC%" (
    echo [錯誤] 找不到 Windows 內建 C# 編譯器 (csc.exe)！
    pause
    exit /b 1
)

echo 正在編譯 SteamManifestUpdater.exe (嵌入 assets\sakura.ico 專屬櫻花圖示)...
"%CSC%" /target:winexe /optimize+ /platform:x64 /win32icon:"assets\sakura.ico" /out:"SteamManifestUpdater.exe" /r:System.dll,System.Core.dll,System.Drawing.dll,System.Windows.Forms.dll Wrapper.cs

if %errorlevel% equ 0 (
    echo [成功] 已生成專屬 SteamManifestUpdater.exe！
) else (
    echo [失敗] 編譯發生錯誤。
)
pause
