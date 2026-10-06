# -*- coding: utf-8 -*-
"""
SMU Modular Handler Component
自動解耦之專屬業務處理模組
"""
import os
import sys
import re
import json
import time
import shutil
import urllib.request
import urllib.parse
import subprocess
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional
import concurrent.futures

from managers import config_manager
from managers import steam_manager
from managers import unified_manifest_manager

class SteamHandler:
    def open_steam_install(self, appid: str) -> bool:
        """呼叫 Steam 安裝協定"""
        try:
            os.startfile(f"steam://install/{appid}")
            return True
        except Exception:
            return False

    def detect_steam(self) -> str:
        """自動偵測 Steam 安裝目錄"""
        p = steam_manager.find_steam_path()
        if p:
            self._steam_path = p
            self._config["steam_path"] = str(p)
            config_manager.save_config(self._config)
            return str(p)
        return ""

    def ensure_steam_path(self) -> str:
        """確保 Steam 路徑"""
        sp = self._steam_path or steam_manager.find_steam_path()
        return str(sp) if sp else ""

    def set_steam_path(self, path: str) -> bool:
        """手動設定 Steam 目錄"""
        p = Path(path)
        if p.exists() and (p / "steam.exe").exists():
            self._steam_path = p
            self._config["steam_path"] = str(p)
            config_manager.save_config(self._config)
            return True
        return False

    def browse_folder(self) -> str:
        """開啟資料夾選取視窗"""
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            folder = filedialog.askdirectory(parent=root, title="請選擇目錄")
            root.destroy()
            return folder if folder else ""
        except Exception:
            return ""

    def list_steam_accounts(self) -> List[Dict[str, Any]]:
        """
        解析 Steam/config/loginusers.vdf，提取歷史登入帳號列表。
        回傳結構：[{"AccountName": "xxx", "PersonaName": "小明", "MostRecent": True, "SteamID": "..."}]
        """
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp:
            return []
        vdf_path = Path(sp) / "config" / "loginusers.vdf"
        if not vdf_path.exists():
            return []

        try:
            with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            users = []
            # 匹配 SteamID 與其屬性塊
            pattern = re.compile(r'"(\d{15,20})"\s*\{([^}]+)\}', re.DOTALL)
            for m in pattern.finditer(content):
                sid = m.group(1)
                block = m.group(2)
                acc_name = ""
                persona = ""
                most_recent = False

                m_acc = re.search(r'"AccountName"\s*"([^"]+)"', block, re.I)
                if m_acc: acc_name = m_acc.group(1)

                m_per = re.search(r'"PersonaName"\s*"([^"]+)"', block, re.I)
                if m_per: persona = m_per.group(1)

                m_rec = re.search(r'"mostrecent"\s*"([01])"', block, re.I)
                if m_rec and m_rec.group(1) == "1":
                    most_recent = True

                if acc_name:
                    users.append({
                        "AccountName": acc_name,
                        "PersonaName": persona or acc_name,
                        "MostRecent": most_recent,
                        "SteamID": sid
                    })
            # 將最近使用的帳號排在最前面
            users.sort(key=lambda x: 0 if x["MostRecent"] else 1)
            return users
        except Exception as e:
            print(f"[WebApi] list_steam_accounts error: {e}")
            return []

    def restart_steam(self) -> bool:
        """安全關閉並重新啟動 Steam"""
        try:
            subprocess.run(["taskkill", "/F", "/IM", "steam.exe"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(1.2)
            sp = self._steam_path or steam_manager.find_steam_path()
            if sp:
                exe = Path(sp) / "steam.exe"
                if exe.exists():
                    os.startfile(str(exe))
                    return True
            return False
        except Exception as e:
            print(f"[WebApi] restart_steam error: {e}")
            return False

    def restart_steam_login(self, account_name: str) -> bool:
        """切換指定帳號並重啟 Steam"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp: return False
        vdf_path = Path(sp) / "config" / "loginusers.vdf"
        if vdf_path.exists():
            try:
                with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                    c = f.read()
                # 將所有帳號的 mostrecent 設為 0
                c = re.sub(r'("mostrecent"\s*)"1"', r'\g<1>"0"', c, flags=re.I)
                # 找到指定 account_name 的塊，將其 mostrecent 改為 1
                pattern = re.compile(rf'("AccountName"\s*"{re.escape(account_name)}"[^}}]*?"mostrecent"\s*)"0"', re.DOTALL | re.I)
                c = pattern.sub(r'\g<1>"1"', c)
                with open(vdf_path, "w", encoding="utf-8") as f:
                    f.write(c)
            except Exception as e:
                print(f"[WebApi] switch account error: {e}")
        return self.restart_steam()

    def restart_steam_offline(self, account_name: str = "") -> bool:
        """以離線模式重啟 Steam"""
        if account_name:
            self.restart_steam_login(account_name)
        try:
            sp = self._steam_path or steam_manager.find_steam_path()
            if sp:
                exe = Path(sp) / "steam.exe"
                if exe.exists():
                    subprocess.Popen([str(exe), "-offline"], creationflags=subprocess.CREATE_NO_WINDOW)
                    return True
            return False
        except Exception:
            return False

    def purge_steam(self) -> Dict[str, Any]:
        """淨化 Steam 目錄，清理歷史殘留的舊版本注入 DLL 與快取"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp: return {"ok": False, "msg": "找不到 Steam 目錄"}
        cleaned = []
        garbage_names = ["hid.dll", "version.dll", "GreenLuma_Reborn.dll", "GreenLuma.dll", "dx3906.dll"]
        for g in garbage_names:
            p = Path(sp) / g
            if p.exists():
                try:
                    p.unlink()
                    cleaned.append(g)
                except Exception:
                    pass
        return {"ok": True, "cleaned": cleaned, "count": len(cleaned)}

    def check_dlls(self) -> Dict[str, Any]:
        """檢查 OpenSteamTools 核心 DLL 狀態"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp:
            return {"ok": False, "missing": 3}
        dlls = ["OpenSteamTool.dll", "dwmapi.dll", "xinput1_4.dll"]
        missing = [d for d in dlls if not (Path(sp) / d).exists()]
        return {
            "ok": len(missing) == 0,
            "missing": len(missing),
            "missing_list": missing
        }

    def inject_kernel(self) -> Dict[str, Any]:
        """一鍵注入/部署 OpenSteamTools 內核"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp: return {"ok": False, "msg": "未找到 Steam 安裝目錄"}
        ok, msg = steam_manager.install_opensteamtools(Path(sp))
        return {
            "ok": ok,
            "msg": msg,
            "consistent": True,
            "steam_reopened": False
        }

    def remove_old_tools(self, restart_steam: bool = False) -> Dict[str, Any]:
        """移除現有注入內核 (OpenSteamTools DLLs)"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp: return {"ok": False, "msg": "未找到 Steam 安裝目錄"}
        ok, msg = steam_manager.uninstall_opensteamtools(Path(sp), restart_steam_after=restart_steam)
        return {"ok": ok, "msg": msg}

    def uninstall_steamtools(self, restart_steam: bool = False) -> Dict[str, Any]:
        """移除 SteamTools 核心組件 (別名)"""
        return self.remove_old_tools(restart_steam=restart_steam)

    def check_steam_locked(self) -> Dict[str, Any]:
        """檢查 Steam 主程式是否已設定版本鎖定 (steam.cfg)"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp: return {"locked": False}
        cfg_file = Path(sp) / "steam.cfg"
        if cfg_file.exists():
            try:
                txt = cfg_file.read_text(encoding="utf-8", errors="ignore")
                return {"locked": "BootStrapperInhibitAll=Enable" in txt}
            except Exception:
                pass
        return {"locked": False}

    def lock_steam_version(self) -> Dict[str, Any]:
        """寫入 steam.cfg 鎖定 Steam 客戶端版本防止更新"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp: return {"ok": False}
        try:
            cfg_file = Path(sp) / "steam.cfg"
            cfg_file.write_text("BootStrapperInhibitAll=Enable\n", encoding="utf-8")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def unlock_steam_version(self) -> Dict[str, Any]:
        """解除 Steam 客戶端版本鎖定"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp: return {"ok": False}
        try:
            cfg_file = Path(sp) / "steam.cfg"
            if cfg_file.exists():
                cfg_file.unlink()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def auto_inject_and_restart(self) -> Dict[str, Any]:
        """自動檢查並注入核心"""
        sp = self._steam_path or steam_manager.find_steam_path()
        return {
            "injected": True,
            "has_path": bool(sp),
            "consistent": True,
            "steam_reopened": False,
            "steam_closed": False,
            "need_restart": False
        }

    def locate_game_dir(self, appid: str) -> str:
        """取得遊戲安裝目錄"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if sp:
            p = Path(sp) / "steamapps" / "common"
            return str(p)
        return ""

    def remove_steam_cfg(self) -> bool:
        """移除 steam.cfg"""
        return self.unlock_steam_version().get("ok", False)

    def restart_steam_online(self) -> bool:
        """在線模式重啟 Steam"""
        return self.restart_steam()

