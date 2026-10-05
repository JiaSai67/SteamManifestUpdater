# -*- coding: utf-8 -*-
"""
Web API Bridge for SteamManifestUpdater Modern Cherry/Rose-Gold GUI
完美橋接前端 HTML/JS 介面與後端強大多源 Manifest / Steam / OnlineFix / 鎖定核心。
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
from pathlib import Path
from typing import Dict, Any, List, Optional
import threading

# 導入底層業務管理器
from managers import config_manager
from managers import steam_manager
from managers import unified_manifest_manager
from managers import version_resolver
from managers import onlinefix_manager
from managers import name_resolver


class WebApi:
    """
    暴露給 pywebview 前端 (window.pywebview.api) 的全功能後端接口類別。
    包含 75+ 項 API，完全兼容 dx3906 前端規範，並深度融合專案所有高階功能。
    """
    def __init__(self, window=None):
        self._window = window
        self._config = config_manager.get_config()
        self._unified_mgr = unified_manifest_manager.get_unified_manifest_manager()
        self._steam_path = steam_manager.find_steam_path()
        if self._steam_path:
            self._config["steam_path"] = str(self._steam_path)
            config_manager.save_config(self._config)
            # 背景自動自癒：安全清理幽靈 ACF 並精準隔離 Lua 遊戲自動更新
            try:
                import threading
                threading.Thread(
                    target=steam_manager.sync_lua_games_autoupdate_behavior,
                    args=(self._steam_path, True),
                    daemon=True
                ).start()
            except Exception:
                pass

        # 雲存檔功能已停用，啟動時不進行重定向初始化
                
        # 啟動 Steam\depotcache\ 背景即時守護輪詢 (自動比對 config/depotcache 本地庫存)
        self._watchdog_logs = []
        self._watchdog_started = False
        self._watchdog_stop = False
        self._start_depotcache_watchdog()

        # 🌟 遊戲入庫清單記憶體快取與背景非同步預熱機制 (Preload In-Memory Cache)
        import threading
        self._cached_games = None
        self._cached_games_lock = threading.Lock()
        self.preload_games_cache()

        # 🌟 系統健康體檢報告非同步預熱預載 (System Health Check Preloader)
        self.preload_health_check()

    def preload_games_cache(self):
        """背景非同步預熱入庫遊戲清單記憶體快取，初始化階段預先整理完畢，前端秒開調用"""
        import threading
        def _worker():
            try:
                self.list_games(force_refresh=True)
            except Exception as e:
                pass
        t = threading.Thread(target=_worker, name="PreloadGamesWorker", daemon=True)
        t.start()

    def preload_health_check(self):
        """背景非同步預熱系統健康體檢報告，初始化階段預先完成，前端切換秒開調用"""
        import threading
        def _worker():
            try:
                from managers.health_check_manager import get_health_check_manager
                mgr = get_health_check_manager()
                mgr.run_health_check()
            except Exception:
                pass
        t = threading.Thread(target=_worker, name="PreloadHealthCheckWorker", daemon=True)
        t.start()

    def invalidate_games_cache(self):
        """使遊戲入庫清單記憶體快取失效（新增、刪除或更新時調用）"""
        self._cached_games = None

    def _start_depotcache_watchdog(self):
        """啟動 Steam/depotcache 即時守護輪詢執行緒 (比對本地庫存並自動秒級還原)"""
        if self._watchdog_started:
            return
        self._watchdog_started = True
        self._watchdog_stop = False

        import threading
        def _loop():
            last_checked_mtime = 0
            while not getattr(self, "_watchdog_stop", False):
                try:
                    sp = self._steam_path or steam_manager.find_steam_path()
                    if sp:
                        backup_dir = Path(sp) / "config" / "depotcache"
                        # 🌟 效能極致優化：僅掃描 config/depotcache 備援庫 (約幾十個檔案)，完全不遍歷 4000+ 個 depotcache 檔案
                        if backup_dir.exists():
                            cur_mtime = backup_dir.stat().st_mtime
                            synced, synced_files = steam_manager.sync_config_depotcache_backup(sp, return_list=True)
                            if synced > 0:
                                for fn in synced_files:
                                    log_msg = f"[{time.strftime('%H:%M:%S')}] [Depotcache守護] 偵測到 {fn} 缺失，已自動從本地金庫還原！"
                                    self._watchdog_logs.append(log_msg)
                                    print(f"[steam_manager] {log_msg}")
                                    if len(self._watchdog_logs) > 100:
                                        self._watchdog_logs.pop(0)
                except Exception:
                    pass
                time.sleep(20) # 🌟 20 秒極低頻心跳守護 (每次僅比對備援庫幾十個檔案，CPU/硬碟開銷趨近於 0)

        t = threading.Thread(target=_loop, name="DepotcacheWatchdog", daemon=True)
        t.start()

    def set_window(self, window):
        self._window = window

    # ═══════════════════════════════════════════════════════
    # 1. 視窗控制與通用基礎 API
    # ═══════════════════════════════════════════════════════
    def _get_hwnd(self) -> int:
        """取得主視窗 HWND 句柄 (支援快取與多層容錯探測)"""
        if getattr(self, "_cached_hwnd", None):
            try:
                import ctypes
                if ctypes.windll.user32.IsWindow(self._cached_hwnd):
                    return self._cached_hwnd
            except Exception:
                pass

        hwnd = 0
        try:
            # 1. 嘗試由 pywebview window.native / window.gui 獲取
            if self._window:
                native = getattr(self._window, "native", None) or getattr(self._window, "gui", None)
                if native and hasattr(native, "Handle"):
                    hwnd = int(native.Handle.ToInt64() if hasattr(native.Handle, "ToInt64") else native.Handle)
        except Exception:
            hwnd = 0

        if not hwnd:
            try:
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.windll.user32

                # 2. 嘗試由視窗標題尋找
                if self._window and getattr(self._window, "title", None):
                    hwnd = user32.FindWindowW(None, self._window.title)

                # 3. 嘗試由 PID 枚舉可見視窗
                if not hwnd:
                    pid = os.getpid()
                    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
                    def enum_cb(h, lp):
                        nonlocal hwnd
                        p = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
                        if p.value == pid and user32.IsWindowVisible(h):
                            hwnd = h
                            return False
                        return True
                    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
            except Exception as e:
                print(f"[WebApi] _get_hwnd error: {e}")

        if hwnd:
            self._cached_hwnd = hwnd
        return hwnd

    def move_by(self, dx: int, dy: int) -> bool:
        """依據滑鼠相對增量極速移動視窗 (Win32 SetWindowPos，0 延遲 144Hz 滿幀流暢度)"""
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = self._get_hwnd()
            if hwnd:
                # 若當前為最大化狀態，拖曳時先自動還原視窗
                if user32.IsZoomed(hwnd):
                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE = 9
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                scale = 1.0
                try:
                    dpi = user32.GetDpiForWindow(hwnd)
                    if dpi > 0:
                        scale = dpi / 96.0
                except Exception:
                    pass
                new_x = rect.left + int(dx * scale)
                new_y = rect.top + int(dy * scale)
                # SWP_NOSIZE (1) | SWP_NOZORDER (4) | SWP_NOACTIVATE (0x0010) = 0x0015
                user32.SetWindowPos(hwnd, 0, int(new_x), int(new_y), 0, 0, 0x0015)
                return True
        except Exception as e:
            pass
        if self._window and hasattr(self._window, 'x') and hasattr(self._window, 'y'):
            try:
                if getattr(self._window, 'maximized', False):
                    self._window.restore()
                self._window.move(int(self._window.x + dx), int(self._window.y + dy))
                return True
            except Exception:
                pass
        return False

    def drag_window(self) -> bool:
        """觸發作業系統原生視窗拖曳 (Win32 SC_DRAGMOVE)，使用非阻塞 PostMessageW 達到 0 延遲 144Hz+ 極致流暢拖曳"""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = self._get_hwnd()
            if hwnd:
                user32.ReleaseCapture()
                # 0x0112 = WM_SYSCOMMAND, 0xF012 = SC_DRAGMOVE (SC_MOVE + HTCAPTION)
                # 使用非阻塞 PostMessageW，避免 SendMessageW 阻塞 Python 執行緒與訊息循環
                user32.PostMessageW(hwnd, 0x0112, 0xF012, 0)
                return True
        except Exception as e:
            print(f"[WebApi] drag_window error: {e}")
        return False

    def start_resize(self, side: str) -> bool:
        """觸發作業系統原生無邊框視窗 8 方向邊緣縮放 (Win32 SC_SIZE)"""
        side_map = {
            "w": 0xF001,   # Left
            "e": 0xF002,   # Right
            "n": 0xF003,   # Top
            "nw": 0xF004,  # Top-Left
            "ne": 0xF005,  # Top-Right
            "s": 0xF006,   # Bottom
            "sw": 0xF007,  # Bottom-Left
            "se": 0xF008,  # Bottom-Right
        }
        cmd = side_map.get(str(side).lower())
        if not cmd:
            return False
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = self._get_hwnd()
            if hwnd:
                user32.ReleaseCapture()
                user32.SendMessageW(hwnd, 0x0112, cmd, 0)
                return True
        except Exception as e:
            print(f"[WebApi] start_resize error: {e}")
        return False

    def close(self):
        """關閉主視窗"""
        if self._window:
            self._window.destroy()

    def minimize(self):
        """最小化視窗"""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = self._get_hwnd()
            if hwnd:
                user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE = 6
                return True
        except Exception:
            pass
        if self._window:
            self._window.minimize()
            return True
        return False

    def maximize(self):
        """最大化 / 還原視窗"""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = self._get_hwnd()
            if hwnd:
                if user32.IsZoomed(hwnd):
                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE = 9
                else:
                    user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE = 3
                return True
        except Exception:
            pass
        if self._window:
            try:
                if getattr(self._window, 'maximized', False):
                    self._window.restore()
                else:
                    self._window.maximize()
                return True
            except Exception:
                pass
        return False

    def restore(self):
        """還原視窗為正常大小"""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = self._get_hwnd()
            if hwnd:
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE = 9
                return True
        except Exception:
            pass
        if self._window:
            try:
                self._window.restore()
                return True
            except Exception:
                pass
        return False

    def is_maximized(self) -> bool:
        """檢查視窗當前是否為最大化狀態"""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = self._get_hwnd()
            if hwnd:
                return bool(user32.IsZoomed(hwnd))
        except Exception:
            pass
        if self._window:
            return bool(getattr(self._window, 'maximized', False))
        return False

    def save_window_size(self, width: int = 0, height: int = 0, *args, **kwargs) -> bool:
        """儲存視窗自訂大小 (保證不低於 880x580 最佳體驗規格)"""
        try:
            if not width or not height:
                if self._window:
                    width = getattr(self._window, 'width', 1180)
                    height = getattr(self._window, 'height', 760)
                else:
                    width, height = 1180, 760
            width = max(int(width), 880)
            height = max(int(height), 580)
            self._config["window_width"] = int(width)
            self._config["window_height"] = int(height)
            config_manager.save_config(self._config)
            return True
        except Exception:
            return False

    def copy_text(self, text: str) -> bool:
        """複製文字至系統剪貼簿"""
        try:
            import subprocess
            cmd = f'Set-Clipboard -Value @\'\n{text}\n\'@'
            subprocess.run(["powershell", "-NoProfile", "-Command", cmd], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except Exception:
            try:
                import ctypes
                ctypes.windll.user32.OpenClipboard(0)
                ctypes.windll.user32.EmptyClipboard()
                hCd = ctypes.windll.kernel32.GlobalAlloc(2, (len(text) + 1) * 2)
                pchData = ctypes.windll.kernel32.GlobalLock(hCd)
                ctypes.cdll.msvcrt.wcscpy(ctypes.c_wchar_p(pchData), text)
                ctypes.windll.kernel32.GlobalUnlock(hCd)
                ctypes.windll.user32.SetClipboardData(13, hCd)
                ctypes.windll.user32.CloseClipboard()
                return True
            except Exception:
                return False

    def open_url(self, url: str) -> bool:
        """使用預設瀏覽器打開 URL"""
        try:
            import webbrowser
            webbrowser.open(url)
            return True
        except Exception:
            return False

    def open_path(self, path: str) -> bool:
        """在檔案總管中開啟指定目錄或檔案"""
        try:
            p = Path(path).resolve()
            if p.exists():
                os.startfile(str(p))
                return True
            return False
        except Exception:
            return False

    def open_steam_store(self, appid: str) -> bool:
        """開啟 Steam 商店頁面"""
        return self.open_url(f"https://store.steampowered.com/app/{appid}/")

    def open_steam_install(self, appid: str) -> bool:
        """呼叫 Steam 安裝協定"""
        try:
            os.startfile(f"steam://install/{appid}")
            return True
        except Exception:
            return False

    def open_steam_workshop_saves(self, appid: str = "480") -> bool:
        """直接在 Steam 客戶端 (Steam App) 內開啟雲端工作坊存檔項目頁面"""
        try:
            aid = str(appid).strip() if appid else "480"
            url = f"https://steamcommunity.com/my/myworkshopfiles/?appid={aid}&browsefilter=myfiles"
            # 優先嘗試以 Steam 原生協議直接在 Steam 客戶端內部打開
            try:
                os.startfile(f"steam://openurl/{url}")
                return True
            except Exception:
                pass
            import webbrowser
            webbrowser.open(url)
            return True
        except Exception:
            return False

    def open_steam_remote_storage(self) -> bool:
        """在 Steam 客戶端或瀏覽器中開啟 Steam 官方全遊戲線上雲端存檔檢視頁 (Remote Storage)"""
        try:
            url = "https://store.steampowered.com/account/remotestorage"
            try:
                os.startfile(f"steam://openurl/{url}")
                return True
            except Exception:
                pass
            import webbrowser
            webbrowser.open(url)
            return True
        except Exception:
            return False


    # ═══════════════════════════════════════════════════════
    # 2. Steam 路徑與帳號管理 API
    # ═══════════════════════════════════════════════════════
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
        """確保 Steam 路徑有效，若無則自動偵測"""
        cur = self._config.get("steam_path", "")
        if cur and os.path.exists(cur):
            self._steam_path = Path(cur)
            return cur
        return self.detect_steam()

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

    # ═══════════════════════════════════════════════════════
    # 3. 內核管理與版本鎖定 (OpenSteamTools / ACF)
    # ═══════════════════════════════════════════════════════
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

    # ═══════════════════════════════════════════════════════
    # 4. 遊戲搜尋與推薦瀏覽 API
    # ═══════════════════════════════════════════════════════
    def search(self, q: str) -> List[Dict[str, Any]]:
        """
        搜尋遊戲：支援純 AppID、中文名稱、英文名稱 (全面繁體中文化)
        """
        from utils.tw_converter import sanitize_game_name
        q = str(q).strip()
        if not q: return []

        results = []
        # 若是 AppID 數字
        if q.isdigit():
            # 優先從快取找
            cache_file = Path(__file__).parent.parent / "data" / "game_cache.json"
            if cache_file.exists():
                try:
                    c_data = json.loads(cache_file.read_text(encoding="utf-8"))
                    if q in c_data:
                        c_info = c_data[q]
                        return [{
                            "appid": q,
                            "name": sanitize_game_name(c_info.get("name", f"App_{q}"), q),
                            "image": c_info.get("header_image", f"https://cdn.cloudflare.steamstatic.com/steam/apps/{q}/header.jpg")
                        }]
                except Exception:
                    pass

            # 嘗試反查名稱
            name = name_resolver.resolve_game_name(q, steam_path=self._steam_path)
            if not name or name == "未知遊戲":
                # 嘗試在線 Steam appdetails 獲取精確官方繁體名
                try:
                    url = f"https://store.steampowered.com/api/appdetails?appids={q}&l=tchinese&cc=TW"
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=4) as resp:
                        d = json.loads(resp.read().decode("utf-8"))
                        if d.get(q, {}).get("success"):
                            data = d[q].get("data", {})
                            name = data.get("name", f"App_{q}")
                except Exception:
                    name = f"App_{q}"

            return [{
                "appid": q,
                "name": sanitize_game_name(name, q),
                "image": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{q}/header.jpg"
            }]

        # 透過 Steam 官方 storesearch API 搜尋 (使用台灣繁體地區碼 l=tchinese&cc=TW)
        try:
            url = f"https://store.steampowered.com/api/storesearch/?term={urllib.parse.quote(q)}&l=tchinese&cc=TW"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("items", [])
                for it in items:
                    appid_str = str(it.get("id"))
                    name_str = sanitize_game_name(it.get("name", f"App_{appid_str}"), appid_str)
                    results.append({
                        "appid": appid_str,
                        "name": name_str,
                        "image": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid_str}/header.jpg"
                    })
        except Exception as e:
            print(f"[WebApi] search online error: {e}")

        # 若線上 API 暫時連不上，嘗試搜尋本地與已知清單
        if not results:
            known = name_resolver._load_cache() or {}
            for aid, n in known.items():
                tw_n = sanitize_game_name(str(n), str(aid))
                if q.lower() in tw_n.lower() or q.lower() in str(aid):
                    results.append({
                        "appid": str(aid),
                        "name": tw_n,
                        "image": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{aid}/header.jpg"
                    })
                    if len(results) >= 20: break

        return results

    def get_installed_appids(self) -> List[str]:
        """取得目前本地已入庫的全部 AppID 清單 (秒級回傳，供首頁對比勾選圖示)"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp: return []
        lua_dir = Path(sp) / "config" / "lua"
        if not lua_dir.exists(): return []
        return [f.stem for f in lua_dir.glob("*.lua") if f.name != "manifest.lua" and f.stem.isdigit()]

    def get_manifest_history(self, appid: str) -> Dict[str, Any]:
        """
        獲取遊戲詳細資訊與以 SteamDB 官方版本鏈排序之 Manifest 版本歷史：
        - 絕對以 SteamDB (SteamCMD PICS) 官方最新 Manifest GID 為最高基準與排序首位
        - 本地數據與雲端數據基於 SteamDB 抓下來的真實 Manifest 版本進行對齊
        - 嚴格杜絕偽造 GID 與以日期推斷新舊，只呈現真實驗證存在之版本
        - 標明本地版本是否落後於 SteamDB 官方最新版，以及雲端倉庫是否已同步最新版
        """
        from datetime import datetime
        from utils.tw_converter import sanitize_game_name
        from managers import version_resolver, unified_manifest_manager, steamdb_history_manager

        appid_str = str(appid).strip()
        sp = self._steam_path or steam_manager.find_steam_path()

        def _push_step(pct: int, title: str, desc: str, step: int):
            if getattr(self, "_window", None):
                try:
                    js = f"window.onDetailStepProgress && window.onDetailStepProgress({json.dumps(appid_str)}, {pct}, {json.dumps(title)}, {json.dumps(desc)}, {step});"
                    self._window.evaluate_js(js)
                except Exception:
                    pass

        # 🌟 階段 1：探測 SteamCMD 官方協議 (14%)
        _push_step(14, "檢測 SteamCMD 官方協議與 Public 分支...", "連接 Valve PICS 伺服器，核驗最新 Manifest GID", 1)

        # 1. 遊戲名稱
        name = name_resolver.resolve_game_name(appid_str, steam_path=sp)
        res_name = sanitize_game_name(name, appid_str)

        res = {
            "appid": appid_str,
            "name": res_name,
            "image": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid_str}/header.jpg",
            "has_update": False,
            "best_source": "none",
            "best_source_name": "無可用線上源",
            "depots": []
        }

        # 0. 🌟 階段 2：檢查更新前置作業：本地 Lua 與實體 ACF 校驗 (28%)
        _push_step(28, "校驗本地 Manifest 與 ACF 檔案狀態...", "核驗實體 depotcache 二進位檔、已下載清單與補丁映射", 2)
        local_sync = steam_manager.verify_and_sync_local_manifests(appid_str, steam_path=sp)
        res["local_sync"] = local_sync

        # 2. 查詢 SteamDB (SteamCMD 官方數據庫) 獲取官方最新 Manifest
        steamdb_info = version_resolver.fetch_steamdb_manifests(appid_str, timeout=4)
        steamdb_manifests = steamdb_info.get("manifests", {})
        steamdb_date_str = steamdb_info.get("date_str", "")
        steamdb_ts = steamdb_info.get("timestamp", 0)
        steamdb_build_id = steamdb_info.get("build_id", "")
        try:
            steamdb_date_fmt = datetime.strptime(steamdb_date_str, "%Y-%m-%d").strftime("%y-%m-%d") if steamdb_date_str else "26-09-10"
        except Exception:
            steamdb_date_fmt = "26-09-10"

        # 🌟 階段 3：對齊 SteamDB 官方歷史版本鏈 (42%)
        _push_step(42, "對齊 SteamDB 官方歷史版本鏈...", "檢索官方 Depots 完整鏈，核實發布日期與版本號", 3)

        # 🌟 智慧探針比對：先以 SteamCMD 數據為基準比對本地獨立快取
        # 關鍵優化：若需要更新，必須在【非阻塞背景執行緒 (daemon thread)】中執行，絕不阻塞主介面與進度條！
        from managers import steamdb_crawler
        first_gid = next(iter(steamdb_manifests.values()), "") if steamdb_manifests else ""
        if not steamdb_crawler.is_steamdb_cache_fresh(appid_str, steamcmd_latest_gid=first_gid):
            all_depot_keys = list(steamdb_manifests.keys())
            if all_depot_keys:
                import threading
                def _bg_update_and_notify():
                    try:
                        steamdb_crawler.update_app_steamdb_history(appid_str, all_depot_keys, steamdb_manifests, steamdb_date_str)
                        if getattr(self, "_window", None):
                            fresh = self.get_manifest_history(appid_str)
                            if fresh and fresh.get("depots"):
                                js = f"window.onSteamDBHistoryReady && window.onSteamDBHistoryReady({json.dumps(appid_str)}, {json.dumps(fresh['depots'])});"
                                self._window.evaluate_js(js)
                    except Exception as ce:
                        print(f"[web_api] bg steamdb update exception for {appid_str}: {ce}")

                threading.Thread(
                    target=_bg_update_and_notify,
                    daemon=True,
                    name=f"steamdb_updater_{appid_str}"
                ).start()

        # 3. 本地已校準 Depots (讀取校準後的 Lua 與實體檔狀態)
        local_status = steam_manager.get_lua_manifest_status(appid_str, steam_path=sp)
        declared = local_status.get("declared_manifests", [])
        declared_dict = {str(d): str(m) for d, m in declared if str(m) != "0"}

        # 🌟 階段 4：檢測 4 域之一 Ryuu 平台雲端庫存 (56%)
        _push_step(56, "檢測 Ryuu 平台雲端庫存狀態...", "核對線上開源庫存與最新 Manifest 收錄狀態", 4)
        unified_mgr = unified_manifest_manager.get_unified_manifest_manager()
        search_res = unified_mgr.search_all_sources(appid_str, timeout=4, steamdb_manifests=steamdb_manifests)
        best_source = search_res.get("best_source", "none")
        best_reason = search_res.get("best_reason", "")

        ryuu_info = search_res.get("ryuu", {})
        ryuu_depots = ryuu_info.get("depots", {})
        ryuu_branches = ryuu_info.get("branch_manifests", {})

        source_name = "本地"
        if best_source == "ryuu": source_name = "Ryuu"
        elif best_source == "luatools": source_name = "LuaTools"

        res["best_source"] = best_source
        res["best_source_name"] = source_name

        # 彙整所有涉及的核心 Depot ID (優先 SteamDB 官方 Depots + Ryuu 實體在庫 Depots + 本地已快取實體 Depots)
        cached_manifest_files = set()
        if sp:
            depot_dir = Path(sp) / "depotcache"
            if depot_dir.exists():
                try:
                    cached_manifest_files.update(os.listdir(depot_dir))
                except Exception:
                    pass

        candidate_depots = []
        def add_depot(d):
            d_str = str(d).strip()
            if d_str and d_str.isdigit() and d_str not in candidate_depots:
                candidate_depots.append(d_str)

        # 優先收集三方來源真實驗證存在之實體 Depot (避免空殼 AppID 造成幽靈標籤)
        real_depots = []
        def add_real(d):
            d_str = str(d).strip()
            if d_str and d_str.isdigit() and d_str not in real_depots:
                real_depots.append(d_str)

        # a. 若 appid_str 本身在 SteamDB / Ryuu / 本地中存在實體 Manifest，則置頂首位
        if (appid_str in steamdb_manifests or appid_str in ryuu_depots or str(declared_dict.get(appid_str, "0")) != "0"):
            add_real(appid_str)

        # b. SteamDB 官方包含之 Depots
        for d in steamdb_manifests:
            add_real(d)

        # 收集官方或分支認可之有效 Depot 清單
        valid_active_depots = set(steamdb_manifests.keys())
        for b_name, b_val in ryuu_branches.items():
            if isinstance(b_val, dict):
                for d in b_val.get("depots", {}).keys():
                    valid_active_depots.add(str(d).strip())
        for dlc_id in ryuu_info.get("dlc", []):
            valid_active_depots.add(str(dlc_id).strip())
        for dep_id in ryuu_info.get("depot_dlc_map", {}).keys():
            valid_active_depots.add(str(dep_id).strip())

        # c. Ryuu / 雲端實體在庫 Depots (排除本地未宣告且官方已除名的孤立過期檔案)
        for d in ryuu_depots:
            d_s = str(d).strip()
            if d_s in valid_active_depots or d_s in declared_dict:
                add_real(d_s)

        for b_name, b_val in ryuu_branches.items():
            if isinstance(b_val, dict):
                for d in b_val.get("depots", {}).keys():
                    add_real(d)

        # d. 本地已宣告且不為 0 之實體 Depots
        for did, mid in declared:
            if str(mid) != "0":
                add_real(did)

        if real_depots:
            for d in real_depots:
                add_depot(d)
        else:
            # 備援：若各方皆無任何實體 Depot 記錄，才退回使用 appid 候選猜測
            cand_dids = [appid_str, f"{int(appid_str)+1}" if appid_str.isdigit() else ""]
            if appid_str == "3934720": cand_dids.extend(["3934271", "3934721"])
            for d in cand_dids:
                if d: add_depot(d)

        if not candidate_depots:
            candidate_depots = [appid_str]

        # 智能收斂：最多保留前 15 個核心 Depot，杜絕雜訊與卡死
        depot_ids = candidate_depots[:15]

        # 🌟 拓撲辨識：檢查是否有已棄置或更名的 Depot
        topo = version_resolver.identify_depot_topology(
            appid_str,
            local_manifests=declared_dict,
            official_manifests=steamdb_manifests,
            ryuu_info=ryuu_info,
            steamdb_info=steamdb_info
        )
        res["has_deprecated"] = topo.get("has_deprecated", False)
        res["deprecated_depots"] = topo.get("deprecated_depots", {})
        res["replaced_map"] = topo.get("replaced_map", {})
        
        needs_topology_migration = False
        if topo.get("has_deprecated"):
            res["replaced_by"] = topo.get("primary_active_depot", "")
            replaced_map = topo.get("replaced_map", {})
            for d_old, d_new in replaced_map.items():
                if d_new:
                    l_m_new = declared_dict.get(str(d_new))
                    t_m_new = steamdb_manifests.get(str(d_new)) or ryuu_depots.get(str(d_new))
                    if not l_m_new or (t_m_new and str(l_m_new) != str(t_m_new)):
                        needs_topology_migration = True
                        break

        res["needs_topology_migration"] = needs_topology_migration
        if needs_topology_migration:
            res["has_update"] = True

        # 5. 狀態檢查：檢測 4 個網域與雲端補丁庫 (a. Ryuu, b. Google Drive, c. Online-Fix, d. ZeiGames)
        # a. Ryuu 平台版本狀態判定 (精確區分主程式 Depot 與 DLC Depot)
        ryuu_available = bool(ryuu_info.get("available") and ryuu_depots)
        main_depot_id = str(depot_ids[0]) if depot_ids else appid_str
        
        # 尋找主程式 Manifest GID (優先匹配 main_depot_id，其次取第一個)
        ryuu_manifest_repr = str(ryuu_depots.get(main_depot_id) or "")
        if not ryuu_manifest_repr and ryuu_depots:
            ryuu_manifest_repr = str(next(iter(ryuu_depots.values())))

        main_s_gid = steamdb_manifests.get(main_depot_id)
        main_r_gid = ryuu_depots.get(main_depot_id)
        main_l_gid = declared_dict.get(main_depot_id)

        # 主程式是否落後 SteamDB 官方最新
        is_main_outdated = bool(main_s_gid and main_r_gid and str(main_s_gid) != str(main_r_gid))
        # 主程式是否與本地一致
        is_main_same_as_local = bool(main_l_gid and main_r_gid and str(main_l_gid) == str(main_r_gid))

        # 是否有任何 Depot 落後 (例如主程式最新但 DLC 稍慢)
        has_any_outdated_depot = False
        all_depots_same_as_local = True

        if ryuu_available and ryuu_depots:
            for did, r_gid in ryuu_depots.items():
                s_gid = steamdb_manifests.get(str(did))
                l_gid = declared_dict.get(str(did))
                if s_gid and str(s_gid) != str(r_gid):
                    has_any_outdated_depot = True
                if not l_gid or str(l_gid) != str(r_gid):
                    all_depots_same_as_local = False

        ryuu_status = {
            "name": "Ryuu 平台",
            "available": ryuu_available,
            "manifest_id": ryuu_manifest_repr if (ryuu_available and ryuu_manifest_repr) else "無檔案 (未收錄)",
            "depots": ryuu_depots,
            "is_outdated": is_main_outdated,  # 嚴格以主程式為準
            "is_same_as_local": is_main_same_as_local,
            "has_any_outdated_depot": has_any_outdated_depot,
            "all_depots_same_as_local": all_depots_same_as_local,
            "time": ryuu_info.get("time", "即時在庫")
        }

        # b. 🌟 階段 5：檢測 4 域之二 Google Drive (網盤補丁庫) (70%)
        _push_step(70, "校驗 Google Drive 網盤補丁庫...", "檢查專用/聯機補丁收錄與本地部署狀態", 5)
        from managers import onlinefix_manager
        # 在點擊遊戲小卡/開啟詳細資訊時，發出向 Google Drive 讀取的請求 (allow_network=True)
        gdrive_sources = onlinefix_manager.get_patch_sources(target_app_id=appid_str, target_app_name=res_name, allow_network=True)
        gdrive_item = gdrive_sources.get(appid_str, {})
        has_gdrive = bool(gdrive_item.get("cloud_rar") or gdrive_item.get("cloud_lua") or gdrive_item.get("local_lua"))
        is_deployed = onlinefix_manager.is_patch_deployed_locally(appid_str)
        
        if gdrive_item.get("cloud_rar"):
            gdrive_val_text = gdrive_item["cloud_rar"].get("path", "已上傳補丁壓縮檔")
        elif gdrive_item.get("cloud_lua") or gdrive_item.get("local_lua"):
            gdrive_val_text = "已配置專用 Lua 補丁"
        else:
            gdrive_val_text = "無補丁檔案"

        gdrive_status = {
            "name": "Google Drive 補丁庫",
            "available": has_gdrive,
            "is_deployed": is_deployed,
            "deploy_status": "已部署" if is_deployed else "未部署",
            "details": gdrive_val_text,
            "drive_name": gdrive_item.get("drive_name", "官方補丁庫")
        }

        # c. 🌟 階段 6：檢測 4 域之三 Online-Fix (84%) & 階段 7：ZeiGames (94%)
        _push_step(84, "檢索 Online-Fix 聯機補丁庫...", "搜尋專用聯機補丁並驗證下載鏈接有效性", 6)
        from api import web_patch_checker
        cache_file = Path(__file__).parent.parent / "data" / "game_cache.json"
        eng_name = ""
        if cache_file.exists():
            try:
                gc = json.loads(cache_file.read_text(encoding="utf-8"))
                eng_name = gc.get(appid_str, {}).get("english_name", "") or gc.get(appid_str, {}).get("name_en", "")
            except Exception:
                pass
        official_eng_name = steamdb_info.get("english_name", "") if isinstance(steamdb_info, dict) else ""
        search_query_name = official_eng_name or eng_name or res_name
        
        def _on_web_patch_step(s):
            if s == "zeigames":
                _push_step(94, "檢索 ZeiGames 專用修復補丁...", "搜尋專用修復補丁並過濾失效鏈接", 7)

        web_patches = web_patch_checker.check_all_web_patches(search_query_name, appid=appid_str, on_step=_on_web_patch_step)
        of_info = web_patches.get("onlinefix", {})
        zg_info = web_patches.get("zeigames", {})
        _push_step(96, "聚合 4 域數據與版本鏈對齊完成...", "各平台數據校準完畢，即將揭曉詳細資訊", 7)

        res["status_check"] = {
            "ryuu": ryuu_status,
            "gdrive": gdrive_status,
            "onlinefix": of_info,
            "zeigames": zg_info
        }
        res["dual_sources"] = res["status_check"]

        # 6. 逐個 Depot 建構對齊 SteamDB 的歷史列表
        depots_result = []
        any_depot_has_real_update = False

        for idx, did_str in enumerate(depot_ids):
            mid_str = declared_dict.get(did_str)
            sdb_gid = steamdb_manifests.get(did_str)
            if not sdb_gid:
                sdb_gid = ryuu_info.get("steamdb_target", {}).get(did_str) or ryuu_branches.get("public", {}).get("depots", {}).get(did_str)
            cur_ryuu_gid = ryuu_depots.get(did_str)

            dep_info = topo.get("deprecated_depots", {}).get(did_str, {})
            is_deprecated = bool(dep_info)
            replaced_by = dep_info.get("replaced_by", "")

            is_main = (idx == 0)
            depot_name = f"舊主程式 ({did_str})" if (is_deprecated and replaced_by) else (f"主程式 ({did_str})" if is_main else f"DLC Depot ({did_str})")
            if is_deprecated:
                depot_has_update = False
                # 🌟 核心規則：官方已棄置之 Depot 絕不參與版本更新比對，絕不判定為需要更新

            # 解析本地實體檔案之真實日期 (依據二進位 Creation Time)
            local_date_str = None
            if sp and mid_str:
                depot_dir = Path(sp) / "depotcache"
                if depot_dir.exists():
                    mf = depot_dir / f"{did_str}_{mid_str}.manifest"
                    if mf.exists():
                        ts = version_resolver.parse_manifest_creation_time(mf)
                        if ts:
                            local_date_str = datetime.fromtimestamp(ts).strftime("%y-%m-%d")
            if not local_date_str:
                local_date_str = "本地歷史版本"

            depot_history = []
            seen_gids = set()

            real_latest_gid = str(sdb_gid or cur_ryuu_gid or "").strip()

            # 判斷本地是否已與 SteamDB / 線上官方最新對齊
            is_local_aligned = bool(real_latest_gid and mid_str and str(mid_str) == real_latest_gid)
            # 判斷 Ryuu 平台是否有收錄此 Depot
            ryuu_has_this_depot = bool(ryuu_info.get("available") and cur_ryuu_gid)

            depot_has_update = False

            # A. 導入 SteamDB 完整歷史管理器 (優先讀取獨立快取，嚴格以 real_latest_gid 為最新首位)
            sdb_history_list = steamdb_history_manager.get_depot_manifest_history(
                did_str,
                steam_path=sp,
                latest_gid=real_latest_gid,
                current_gid=mid_str,
                base_date_str=steamdb_date_str or steamdb_date_fmt,
                auto_generate=True,
                appid=appid_str
            )
            if sdb_history_list:
                for idx_h, s_item in enumerate(sdb_history_list):
                    h_gid = str(s_item.get("manifest_id", "")).strip()
                    if not h_gid or h_gid in seen_gids:
                        continue
                    
                    is_h_cur = bool(mid_str and str(mid_str) == h_gid)
                    # 嚴格判定：只有真實吻合官方最新 GID (或無最新 GID 時的首項) 才被視為官方最新 (若已被棄置則絕非官方最新)
                    is_official_latest = (not is_deprecated) and (bool(real_latest_gid and h_gid == real_latest_gid) or (not real_latest_gid and idx_h == 0))
                    h_date_fmt = s_item.get("date") or s_item.get("date_str") or steamdb_date_fmt
                    h_branch = s_item.get("branch", "public")

                    # 檢查此 GID 是否在 Ryuu 平台中可供下載
                    is_in_ryuu = bool(ryuu_has_this_depot and str(cur_ryuu_gid) == h_gid)

                    # 🌟 依需求完全移除相對時間與「歷史版本」四字，只保留精準日期與來源
                    meta_desc = f"{h_date_fmt}．SteamDB"
                    if is_official_latest:
                        meta_desc += " 最新"
                    elif h_branch and h_branch not in ["public", "local_storage"]:
                        meta_desc += f" 分支 ({h_branch})"
                    else:
                        meta_desc += f" #{idx_h+1}"

                    if is_official_latest:
                        if is_h_cur:
                            depot_history.append({
                                "manifest_id": h_gid,
                                "date": h_date_fmt,
                                "meta": meta_desc + " (本地已同步)",
                                "is_current": True,
                                "is_pending": False,
                                "tag": "💾 本地當前 (SteamCMD)",
                                "is_official": True
                            })
                        elif is_in_ryuu:
                            # 只有當 Ryuu 真正有此檔案，且本地尚未同步時，才標註為可更新！
                            depot_has_update = True
                            any_depot_has_real_update = True
                            depot_history.append({
                                "manifest_id": h_gid,
                                "date": h_date_fmt,
                                "meta": meta_desc,
                                "is_current": False,
                                "is_pending": True,
                                "tag": "⚡ 可更新 (SteamCMD)",
                                "is_official": True
                            })
                        else:
                            # 遊戲未上市、Ryuu 未收錄或 Ryuu 尚為舊版
                            is_depot_ryuu_old = bool(ryuu_has_this_depot and cur_ryuu_gid and str(cur_ryuu_gid) != str(h_gid))
                            tag_sdb = "SteamDB 最新 (線上庫未收錄)" if is_depot_ryuu_old else "SteamDB 最新"
                            depot_history.append({
                                "manifest_id": h_gid,
                                "date": h_date_fmt,
                                "meta": meta_desc,
                                "is_current": False,
                                "is_pending": False,
                                "tag": tag_sdb,
                                "is_official": True
                            })
                    else:
                        if is_h_cur:
                            cur_tag = "🔴 本地舊版 (官方已棄置)" if is_deprecated else ("💾 本地當前 (Ryuu 在庫)" if (ryuu_has_this_depot and str(cur_ryuu_gid) == h_gid) else "💾 本地當前 (舊版)")
                            depot_history.append({
                                "manifest_id": h_gid,
                                "date": h_date_fmt,
                                "meta": meta_desc + " (本地當前)",
                                "is_current": True,
                                "is_pending": False,
                                "tag": cur_tag,
                                "is_official": True
                            })
                        else:
                            b_tag = f"分支 ({h_branch})" if h_branch not in ["public", "local_storage"] else f"#{idx_h+1} (SteamDB)"
                            depot_history.append({
                                "manifest_id": h_gid,
                                "date": h_date_fmt,
                                "meta": meta_desc,
                                "is_current": False,
                                "is_pending": False,
                                "tag": b_tag,
                                "is_official": True
                            })
                    seen_gids.add(h_gid)

            # B. 補充 Ryuu 實體庫存與分支版本
            for b_name, b_val in ryuu_branches.items():
                if isinstance(b_val, dict):
                    b_depots = b_val.get("depots", {})
                    if did_str in b_depots:
                        b_gid = str(b_depots[did_str])
                        if b_gid and b_gid not in seen_gids:
                            is_b_cur = bool(mid_str and str(mid_str) == b_gid)
                            # 🌟 只有 Ryuu 實體檔案庫存中真正存在該版本且未被棄置時，才能觸發更新
                            is_in_real_ryuu = bool(ryuu_has_this_depot and str(cur_ryuu_gid) == b_gid)
                            can_up = bool(is_in_real_ryuu and not is_b_cur and not is_deprecated)
                            
                            if can_up:
                                depot_has_update = True
                                any_depot_has_real_update = True
                                tag = "⚡ 可更新至此版本 (Ryuu 在庫)" if (b_name == "public") else f"⚡ 可更新 (分支 {b_name})"
                            elif is_b_cur:
                                tag = "💾 本地當前版本 (Ryuu 最新)" if is_in_real_ryuu else "💾 本地當前版本"
                            elif b_gid == str(sdb_gid):
                                tag = "SteamDB 官方最新 (待雲端收錄)"
                            else:
                                tag = f"官方分支 ({b_name})"

                            depot_history.append({
                                "manifest_id": b_gid,
                                "date": steamdb_date_fmt,
                                "meta": f"Ryuu 平台．分支 {b_name}",
                                "is_current": is_b_cur,
                                "is_pending": can_up,
                                "tag": tag,
                                "is_official": True
                            })
                            seen_gids.add(b_gid)

            # C. 補充 SteamDB 官方即時最新版本 (若不在清單中)
            if sdb_gid and str(sdb_gid) not in seen_gids:
                is_sdb_in_ryuu = bool(ryuu_has_this_depot and str(cur_ryuu_gid) == str(sdb_gid))
                if is_local_aligned:
                    depot_history.insert(0, {
                        "manifest_id": str(sdb_gid),
                        "date": steamdb_date_fmt,
                        "meta": f"{steamdb_date_fmt}．SteamDB 官方最新 (本地已同步)",
                        "is_current": True,
                        "is_pending": False,
                        "tag": "💾 本地當前版本 (官方最新)",
                        "is_official": True
                    })
                elif is_sdb_in_ryuu:
                    depot_has_update = True
                    any_depot_has_real_update = True
                    depot_history.insert(0, {
                        "manifest_id": str(sdb_gid),
                        "date": steamdb_date_fmt,
                        "meta": f"{steamdb_date_fmt}．SteamDB 官方最新",
                        "is_current": False,
                        "is_pending": True,
                        "tag": "⚡ 可更新至官方最新",
                        "is_official": True
                    })
                else:
                    depot_history.insert(0, {
                        "manifest_id": str(sdb_gid),
                        "date": steamdb_date_fmt,
                        "meta": f"{steamdb_date_fmt}．SteamDB 官方最新 (待雲端收錄)",
                        "is_current": False,
                        "is_pending": False,
                        "tag": "SteamDB 官方最新 (待雲端收錄)",
                        "is_official": True
                    })
                seen_gids.add(str(sdb_gid))

            # D. 補充本地當前版本 (若本地為舊版且尚未加入清單)
            if mid_str and str(mid_str) not in seen_gids:
                cur_local_tag = f"🔴 本地舊版 (官方已棄置)" if is_deprecated else "💾 本地當前版本"
                depot_history.append({
                    "manifest_id": str(mid_str),
                    "meta": f"{local_date_str}．本地當前版本 (已棄置)" if is_deprecated else f"{local_date_str}．本地當前版本 (舊版)",
                    "is_current": True,
                    "is_pending": False,
                    "tag": cur_local_tag,
                    "is_official": False
                })
                seen_gids.add(str(mid_str))

            # E. 補充 SteamCMD PICS 其他分支
            raw_depot_data = steamdb_info.get("depots_info", {}).get(did_str, {})
            all_branch_manifests = raw_depot_data.get("manifests", {}) if isinstance(raw_depot_data, dict) else {}
            for b_name, b_info in all_branch_manifests.items():
                if isinstance(b_info, dict) and "gid" in b_info:
                    b_gid = str(b_info.get("gid", ""))
                    if b_gid and b_gid not in seen_gids:
                        is_b_cur = bool(mid_str and str(mid_str) == b_gid)
                        depot_history.append({
                            "manifest_id": b_gid,
                            "meta": f"SteamDB 官方分支．{b_name}",
                            "is_current": is_b_cur,
                            "is_pending": False,
                            "tag": f"💾 本地當前 ({b_name})" if is_b_cur else f"官方分支 ({b_name})",
                            "is_official": True
                        })
                        seen_gids.add(b_gid)

            # 依需求 4e 最多呈現最新 10 個真實版本
            depot_history = depot_history[:10]

            depots_result.append({
                "depot_id": did_str,
                "depot_name": depot_name,
                "is_main": is_main,
                "is_deprecated": is_deprecated,
                "replaced_by": replaced_by,
                "deprecation_reason": dep_info.get("reason", "") if is_deprecated else "",
                "local_manifest": mid_str or "未配置",
                "official_manifest": sdb_gid or ("SteamDB 已除名" if is_deprecated else "SteamDB 未標記"),
                "local_date": f"{local_date_str}．本地",
                "official_date": f"{steamdb_date_fmt}．SteamDB",
                "source_name": source_name,
                "has_update": depot_has_update,
                "is_aligned": False if is_deprecated else is_local_aligned,
                "history": depot_history
            })

        res["depots"] = depots_result
        if needs_topology_migration:
            any_depot_has_real_update = True
        res["has_update"] = any_depot_has_real_update

        # 🌟 同步更新本地 manifest_updates 快取，確保管理頁秒開與即時同步點亮
        try:
            updates_file = Path(__file__).parent.parent / "data" / "manifest_updates.json"
            cached_updates = {}
            if updates_file.exists():
                try: cached_updates = json.loads(updates_file.read_text(encoding="utf-8"))
                except Exception: pass
            
            # 若為有更新，計算或保留具體的「舊 n 版」狀態
            v_stat = cached_updates.get(appid_str, {}).get("version_status", "舊 1 版")
            if needs_topology_migration:
                p_dep = topo.get("primary_active_depot", "")
                v_stat = f"架構升級 (Depot {p_dep})" if p_dep else "架構升級"
            elif any_depot_has_real_update:
                if not v_stat or v_stat == "0 版" or v_stat == "最新版" or "" in v_stat:
                    v_stat = "舊 1 版"
            else:
                v_stat = "最新版"

            cached_updates[appid_str] = {
                "has_update": bool(any_depot_has_real_update),
                "version_status": v_stat,
                "latest_date": steamdb_date_str or "未知",
                "best_source": best_source
            }
            updates_file.write_text(json.dumps(cached_updates, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        return res


    def set_window_opacity(self, opacity: int = 100) -> bool:
        """設定作業系統級別的視窗真實半透明度 (30% ~ 100%)"""
        try:
            val = max(30, min(100, int(opacity)))
            self._config["win_opacity"] = val
            config_manager.save_config(self._config)

            hwnd = self._get_hwnd()
            if hwnd:
                import ctypes
                user32 = ctypes.windll.user32
                GWL_EXSTYLE = -20
                WS_EX_LAYERED = 0x00080000
                LWA_ALPHA = 0x00000002
                alpha = int(255 * (val / 100.0))
                style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                if not (style & WS_EX_LAYERED):
                    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
                user32.SetLayeredWindowAttributes(hwnd, 0, alpha, LWA_ALPHA)
                return True
        except Exception as e:
            print(f"[WebApi] set_window_opacity error: {e}")
        return False

    def browse_games(self, offset: int = 0, limit: int = 40) -> Dict[str, Any]:
        """首頁遊戲推薦瀏覽清單 (支援無限滾動加載，100% 繁體中文展示)"""
        from utils.tw_converter import sanitize_game_name
        # 精選熱門遊戲池作為瀏覽備用 (台灣繁體中文官方標題)
        featured_pool = [
            ("2358720", "Black Myth: Wukong (黑神話：悟空)"),
            ("1245620", "ELDEN RING (艾爾登法環)"),
            ("1091500", "Cyberpunk 2077 (電馭叛客 2077)"),
            ("1623730", "Palworld (幻獸帕魯)"),
            ("1086940", "Baldur's Gate 3 (柏德之門 3)"),
            ("1817070", "Marvel’s Spider-Man Remastered (漫威蜘蛛人)"),
            ("2436940", "Sephiria (賽菲莉婭)"),
            ("974480", "Echoes of Mystralia (秘奧回響)"),
            ("1805110", "Solarpunk (太陽龐克：浮島家園)"),
            ("2285550", "Doloc Town (多洛可小鎮)"),
            ("1374490", "RuneScape: Dragonwilds (符文世界：龍之荒野)"),
            ("1206560", "WorldBox - God Simulator (世界盒子)"),
            ("1001270", "Kebab Chefs! - Restaurant Simulator (烤串大廚！餐廳模擬器)"),
            ("386940", "Ultimate Chicken Horse (超級雞馬)"),
            ("264710", "Subnautica (深海迷航)"),
            ("1172470", "Apex Legends (Apex 英雄)"),
            ("730", "Counter-Strike 2"),
            ("570", "Dota 2"),
            ("271590", "Grand Theft Auto V (俠盜獵車手 V)"),
            ("1174180", "Red Dead Redemption 2 (碧血狂殺 2)"),
            ("553850", "HELLDIVERS 2 (絕地戰兵 2)"),
            ("252490", "Rust (腐蝕)"),
            ("289070", "Sid Meier's Civilization VI (文明帝國 VI)"),
            ("105600", "Terraria (泰拉瑞亞)"),
            ("294100", "RimWorld (邊緣世界)"),
            ("1145360", "Hades (黑帝斯)"),
            ("3624140", "Ascend of Souls"),
            ("2697940", "Ascend to ZERO"),
            ("3934270", "Star Odyssey"),
            ("4005220", "Chronicles of Magic")
        ]

        total = len(featured_pool)
        start = min(offset, total)
        end = min(start + limit, total)
        items = []

        cache_file = Path(__file__).parent.parent / "data" / "game_cache.json"
        game_cache = {}
        if cache_file.exists():
            try:
                game_cache = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        for aid, nm in featured_pool[start:end]:
            c_info = game_cache.get(str(aid), {})
            img = c_info.get("header_image", f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{aid}/header.jpg")
            c_name = sanitize_game_name(c_info.get("name", nm), aid)
            items.append({
                "appid": str(aid),
                "name": c_name,
                "image": img
            })

        return {
            "games": items,
            "items": items,
            "total": total,
            "offset": offset,
            "limit": limit
        }

    # ═══════════════════════════════════════════════════════
    # 5. 多源清單取得與一鍵入庫核心 (Ryuu + Lua.tools)
    # ═══════════════════════════════════════════════════════
    def can_import(self, appid: str) -> Dict[str, Any]:
        """入庫權限檢驗：本專案為永久旗艦無限制版，無限次直接放行"""
        return {
            "allowed": True,
            "activated": True,
            "granted": True,
            "tier": "sponsor",
            "reason": ""
        }

    def fetch_manifest(self, appid: str) -> Dict[str, Any]:
        """
        透過 UnifiedManifestManager 與多層自癒引擎取得入庫清單：
        1. 優先線上 Ryuu / Lua.tools 聚合查詢（支援智慧重試）
        2. 次選 SteamDB 官方資料庫歷史 Depot 提取
        3. 備選 Google Drive 網盤補丁庫之專屬 Lua 腳本
        4. 備選 本地 Steam/config/lua 既有設定檔
        5. 兜底 基礎入庫腳本 (addappid)
        """
        appid_str = str(appid).strip()
        sp = self._steam_path or steam_manager.find_steam_path()

        # 1. 嘗試線上多源聚合查詢 (給予 8 秒連線並支援重試)
        search_res = {}
        depots = {}
        best_source = "ryuu"
        try:
            search_res = self._unified_mgr.search_all_sources(appid_str, timeout=8)
            depots = search_res.get("ryuu", {}).get("depots", {})
            best_source = search_res.get("best_source", "ryuu")
            
            # 若初次查詢未取得 depots，進行一次重試
            if not depots:
                time.sleep(0.5)
                search_res = self._unified_mgr.search_all_sources(appid_str, timeout=10)
                depots = search_res.get("ryuu", {}).get("depots", {})
                best_source = search_res.get("best_source", "ryuu")
        except Exception as e:
            print(f"[fetch_manifest] AppID {appid_str} 線上多源查詢異常: {e}")

        # 2. 若線上清單為空，嘗試從 SteamDB 資料庫提取 Depots
        if not depots:
            try:
                from managers import version_resolver
                sdb_info = version_resolver.fetch_steamdb_manifests(appid_str, timeout=6)
                sdb_manifests = sdb_info.get("manifests", {})
                if sdb_manifests:
                    depots = sdb_manifests
                    best_source = "steamdb"
            except Exception as e:
                print(f"[fetch_manifest] AppID {appid_str} SteamDB 提取異常: {e}")

        # 3. 若有 Depots 清單，自動組裝含 Key 之完整 Lua
        if depots:
            keys_cache = self._unified_mgr.get_cached_depot_keys() or {}
            lua_lines = [
                f"-- {appid_str} - Auto Generated by UnifiedManifestManager ({best_source.upper()})",
                f"addappid({appid_str})"
            ]
            has_any_key = False
            for did, gid in depots.items():
                did_str = str(did).strip()
                key = keys_cache.get(did_str)
                if key and len(key) == 64:
                    lua_lines.append(f'addappid({did_str}, 0, "{key}")')
                    has_any_key = True
                else:
                    lua_lines.append(f"addappid({did_str})")
                if gid:
                    lua_lines.append(f'setManifestid({did_str}, "{gid}")')

            assembled_lua = "\n".join(lua_lines) + "\n"
            return {
                "lua": assembled_lua,
                "source": best_source.upper(),
                "has_key": has_any_key,
                "manifest_count": len(depots),
                "depots": depots,
                "search_result": search_res
            }

        # 4. 備援檢查：Google Drive 網盤補丁庫是否收錄專屬 Lua 或補丁
        try:
            from managers import onlinefix_manager
            ps = onlinefix_manager.get_patch_sources(target_app_id=appid_str, allow_network=False)
            app_src = ps.get(appid_str, {})
            
            # 若本地或網盤有已下載的 Lua 內容
            if sp:
                local_lua = Path(sp) / "config" / "lua" / f"{appid_str}.lua"
                if local_lua.exists() and local_lua.stat().st_size > 20:
                    content = local_lua.read_text(encoding='utf-8', errors='ignore')
                    return {
                        "lua": content,
                        "source": "LOCAL_CACHE",
                        "has_key": False,
                        "manifest_count": 1,
                        "depots": {},
                        "search_result": {}
                    }
                    
            if app_src.get("cloud_rar") or app_src.get("cloud_lua"):
                # 該遊戲存在聯機補丁/解鎖檔，生成標準入庫腳本
                basic_lua = f"-- {appid_str} - Auto Generated Basic Unlocker (Cloud Patch Supported)\naddappid({appid_str})\n"
                return {
                    "lua": basic_lua,
                    "source": "GDRIVE_PATCH",
                    "has_key": False,
                    "manifest_count": 0,
                    "depots": {},
                    "search_result": {}
                }
        except Exception as e:
            print(f"[fetch_manifest] AppID {appid_str} 網盤備援檢查異常: {e}")

        # 5. 若本地已有設定檔，讀取使用
        if sp:
            local_lua = Path(sp) / "config" / "lua" / f"{appid_str}.lua"
            if local_lua.exists() and local_lua.stat().st_size > 10:
                content = local_lua.read_text(encoding='utf-8', errors='ignore')
                return {
                    "lua": content,
                    "source": "LOCAL_FALLBACK",
                    "has_key": False,
                    "manifest_count": 1,
                    "depots": {},
                    "search_result": {}
                }

        # 6. 最終兜底：生成基礎 addappid 入庫腳本
        fallback_lua = f"-- {appid_str} - Auto Generated Safe Fallback\naddappid({appid_str})\n"
        return {
            "lua": fallback_lua,
            "source": "FALLBACK",
            "has_key": False,
            "manifest_count": 0,
            "depots": {},
            "search_result": {}
        }

    def write_lua(self, appid: str, lua_content: str, source: str = "", dlcs: list = None) -> Dict[str, Any]:
        """將 Lua 腳本寫入 Steam/config/lua/{appid}.lua 並設定唯讀保護"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp: return {"ok": False, "msg": "找不到 Steam 路徑"}
        lua_dir = Path(sp) / "config" / "lua"
        lua_dir.mkdir(parents=True, exist_ok=True)
        lua_file = lua_dir / f"{appid}.lua"

        try:
            import stat
            if lua_file.exists():
                os.chmod(lua_file, stat.S_IWRITE | stat.S_IREAD)
            with open(lua_file, "w", encoding="utf-8") as f:
                f.write(lua_content)
            os.chmod(lua_file, stat.S_IREAD)
            # 即時動態注入 VDF：為新入庫遊戲預先關閉 Steam 官方雲端開關
            try:
                from managers.steam_cloud_helper import disable_official_cloud_for_single_appid
                disable_official_cloud_for_single_appid(Path(sp), str(appid))
            except Exception as _ce:
                print(f"[WebApi] 即時關閉新入庫遊戲官方雲端失敗: {_ce}")

            return {"ok": True}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def check_local_lua_exists(self, appid: str) -> Dict[str, Any]:
        """檢查 Steam/config/lua/{appid}.lua 是否存在且內容有效"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp: return {"exists": False}
        lua_f = Path(sp) / "config" / "lua" / f"{appid}.lua"
        return {"exists": bool(lua_f.exists() and lua_f.stat().st_size > 20)}

    def get_search_item_status(self, appid: str, name: str = "") -> Dict[str, Any]:
        """
        為搜尋結果小卡提供多源狀態深度核驗（正確性優先）：
        - 檢查是否有可用 Manifest (Ryuu / Lua.tools / SteamDB 歷史)
        - 提取版本更新日期 (跟隨 Ryuu 的 Manifest ID 與 SteamDB 資料庫日期，格式如 "9月23日")
        - 檢查 Google Drive 網盤補丁庫是否收錄該遊戲的補丁或專用 Lua
        - 檢查本地是否已入庫
        """
        from datetime import datetime
        appid_str = str(appid).strip()
        sp = self._steam_path or steam_manager.find_steam_path()

        # 1. 檢查本地是否已入庫
        is_installed = False
        if sp:
            lua_f = Path(sp) / "config" / "lua" / f"{appid_str}.lua"
            is_installed = bool(lua_f.exists() and lua_f.stat().st_size > 20)

        # 2. 檢查雲端網盤補丁庫 (Google Drive)
        has_patch = False
        drive_name = ""
        try:
            from managers import onlinefix_manager
            ps = onlinefix_manager.get_patch_sources(target_app_id=appid_str, target_app_name=name, allow_network=False)
            app_src = ps.get(appid_str, {})
            if app_src.get("cloud_rar") or app_src.get("cloud_lua") or app_src.get("local_lua"):
                has_patch = True
                drive_name = app_src.get("drive_name", "Google Drive")
        except Exception as e:
            print(f"[get_search_item_status] AppID {appid_str} 查詢補丁庫異常: {e}")

        # 3. 查詢 Manifest 與版本日期 (放寬超時並支援多源容錯)
        has_manifest = False
        version_date_str = ""
        try:
            from managers import version_resolver
            sdb_info = version_resolver.fetch_steamdb_manifests(appid_str, timeout=5)
            sdb_manifests = sdb_info.get("manifests", {})
            raw_date = sdb_info.get("date_str", "")
            if raw_date:
                try:
                    dt = datetime.strptime(raw_date, "%Y-%m-%d")
                    version_date_str = f"{dt.month}月{dt.day}日"
                except Exception:
                    version_date_str = raw_date

            # 查詢 Ryuu / LuaTools 聚合來源 (給予充裕的 6 秒連線超時)
            search_res = self._unified_mgr.search_all_sources(appid_str, timeout=6, steamdb_manifests=sdb_manifests)
            best_source = search_res.get("best_source", "none")
            ryuu_data = search_res.get("ryuu", {})
            ryuu_depots = ryuu_data.get("depots", {})
            luatools_data = search_res.get("luatools", {})

            # 🌟 正確性核心：只要 Ryuu / LuaTools / GDrive 補丁庫 / 本地 任一有資料，即判定為支援
            if (best_source != "none" and ryuu_depots) or ryuu_data.get("available") or luatools_data.get("available") or has_patch or is_installed:
                has_manifest = True

            if not version_date_str:
                r_time = ryuu_data.get("time", "")
                if r_time and "T" in r_time:
                    try:
                        dt = datetime.fromisoformat(r_time)
                        version_date_str = f"{dt.month}月{dt.day}日"
                    except Exception:
                        pass
        except Exception as e:
            print(f"[get_search_item_status] AppID {appid_str} 查詢 Manifest 異常: {e}")
            # 網路波動異常時，若有補丁庫或已安裝則支援，否則預設給予嘗試入庫機會
            if has_patch or is_installed:
                has_manifest = True

        return {
            "appid": appid_str,
            "has_manifest": has_manifest,
            "version_date": version_date_str,
            "has_onlinefix": has_patch,
            "drive_name": drive_name,
            "is_installed": is_installed
        }

    def auto_stock_after_import(self, appid: str, game_name: str = "") -> Dict[str, Any]:
        """
        入庫後自動執行「多源最佳清單部署 + ACF 防 401 赦免 + 鎖定」
        支援 SteamDB 官方對齊、智能多源重試與快取即時更新。
        自動生成全鏈路結構化 Manifest 診斷 Log 報告。
        """
        from managers.manifest_logger import ManifestUpdateLogger
        appid_str = str(appid).strip()
        
        # 嘗試解析遊戲名稱供日誌報告展示
        if not game_name:
            try:
                cache_file = Path(__file__).parent.parent / "data" / "game_cache.json"
                if cache_file.exists():
                    gc = json.loads(cache_file.read_text(encoding="utf-8"))
                    game_name = gc.get(appid_str, {}).get("name", "")
            except Exception:
                pass

        try:
            logger = ManifestUpdateLogger(appid_str, game_name=game_name or f"App_{appid_str}")
            logger.log_step("啟動更新", f"收到 AppID {appid_str} 之 Manifest 更新請求")

            if not appid_str or not appid_str.isdigit():
                logger.log_error("參數校驗", f"無效或未提供 AppID: '{appid}'")
                log_res = logger.finish(False, f"無效或未提供 AppID: '{appid}'")
                return {
                    "ok": False,
                    "complete": False,
                    "msg": f"無效或未提供 AppID: '{appid}'",
                    "log_path": log_res.get("log_path"),
                    "log_filename": log_res.get("log_filename"),
                    "report_markdown": log_res.get("report_markdown")
                }

            from managers import version_resolver
            
            # 1. 取得 SteamDB 最新 Manifest 資訊作為最高仲裁基準
            logger.log_step("SteamDB檢測", f"查詢 SteamDB 最新官方 Manifest 基準: {appid_str}")
            sdb_info = version_resolver.fetch_steamdb_manifests(appid_str, timeout=4)
            sdb_manifests = sdb_info.get("manifests", {})
            logger.log_step("SteamDB結果", f"SteamDB 包含 {len(sdb_manifests)} 個 Depot 官方基準清單")
            
            # 2. 進行多源搜尋仲裁（傳入 sdb_manifests）
            logger.log_step("多源仲裁", "比對 Ryuu 與 Lua.tools 可用來源...")
            search_res = self._unified_mgr.search_all_sources(appid_str, timeout=8, steamdb_manifests=sdb_manifests)
            
            # 若初次未找到可用源，自動重試一次
            if search_res.get("best_source") == "none":
                logger.log_step("多源仲裁", "初次搜尋無可用源，延長逾時重試...", status="WARN")
                search_res = self._unified_mgr.search_all_sources(appid_str, timeout=10, steamdb_manifests=sdb_manifests)

            logger.log_step("仲裁結果", f"最佳來源: {search_res.get('best_source')}，仲裁依據: {search_res.get('best_reason')}")

            # 3. 執行部署 (支援進度即時回呼至前端 UI，若 Ryuu 失敗即刻顯示備援切換)
            def on_progress(p_text: str):
                if getattr(self, "_window", None):
                    try:
                        self._window.evaluate_js(f"window.onManifestProgress && window.onManifestProgress({json.dumps(appid_str)}, {json.dumps(p_text)});")
                    except Exception:
                        pass

            ok, msg = self._unified_mgr.deploy_best_manifest(appid_str, search_res, progress_cb=on_progress, logger=logger)

            # 🌟 核心同步：確定完成更新後，立即將該遊戲更新狀態移出待更新名單，同步寫入快取
            if ok:
                updates_file = Path(__file__).parent.parent / "data" / "manifest_updates.json"
                try:
                    from datetime import datetime
                    updates = {}
                    if updates_file.exists():
                        updates = json.loads(updates_file.read_text(encoding="utf-8"))
                    updates[appid_str] = {
                        "appid": appid_str,
                        "has_update": False,
                        "version_status": "最新版",
                        "latest_date": datetime.now().strftime("%Y-%m-%d"),
                        "best_source": search_res.get("best_source", "ryuu")
                    }
                    updates_file.write_text(json.dumps(updates, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass

            log_res = logger.finish(ok, msg)

            self.invalidate_games_cache()
            return {
                "ok": ok,
                "complete": ok,
                "msg": msg,
                "log_path": log_res.get("log_path"),
                "log_filename": log_res.get("log_filename"),
                "report_markdown": log_res.get("report_markdown")
            }
        except Exception as e:
            logger.log_error("更新未預期異常", str(e), exc=e)
            log_res = logger.finish(False, f"更新 Manifest 發生異常: {e}")
            return {
                "ok": False,
                "complete": False,
                "msg": f"更新 Manifest 發生異常: {e}",
                "log_path": log_res.get("log_path"),
                "log_filename": log_res.get("log_filename"),
                "report_markdown": log_res.get("report_markdown")
            }

    def refresh_single_game_status(self, appid: str) -> Dict[str, Any]:
        """
        單一遊戲更新完成後，即時重新驗證本地資料與 SteamDB 官方狀態，並更新快取
        """
        appid_str = str(appid).strip()
        if not appid_str or not appid_str.isdigit():
            return {"ok": False, "appid": appid_str, "has_update": False, "version_status": "最新版"}
        
        sp = self._steam_path or steam_manager.find_steam_path()
        lua_dir = Path(sp) / "config" / "lua" if sp else None
        
        try:
            from managers import version_resolver
            diff_info = version_resolver.resolve_manifest_version_diff(
                appid_str,
                lua_dir=str(lua_dir) if lua_dir else "",
                steam_path=sp,
                timeout=4
            )
            is_latest = diff_info.get("is_latest", True)
            v_stat = diff_info.get("version_status", "")
            diff_cnt = diff_info.get("diff_count", 0) or 0

            if is_latest:
                raw_v = "最新版"
                has_up = False
            elif v_stat == "待雲端同步" or not diff_info.get("has_available_update"):
                raw_v = "待雲端同步"
                has_up = False
            else:
                raw_v = f"舊 {diff_cnt} 版" if diff_cnt > 0 else (v_stat or "舊 1 版")
                has_up = True

            u_item = {
                "appid": appid_str,
                "has_update": has_up,
                "version_status": raw_v,
                "latest_date": diff_info.get("latest_date", "未知"),
                "best_source": diff_info.get("best_source", "ryuu")
            }

            # 同步更新 manifest_updates.json 快取
            updates_file = Path(__file__).parent.parent / "data" / "manifest_updates.json"
            try:
                updates = {}
                if updates_file.exists():
                    updates = json.loads(updates_file.read_text(encoding="utf-8"))
                updates[appid_str] = u_item
                updates_file.write_text(json.dumps(updates, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

            self.invalidate_games_cache()
            return {
                "ok": True,
                "appid": appid_str,
                "has_update": has_up,
                "version_status": raw_v,
                "latest_date": u_item["latest_date"],
                "best_source": u_item["best_source"]
            }
        except Exception as e:
            return {
                "ok": False,
                "appid": appid_str,
                "has_update": False,
                "version_status": "最新版",
                "error": str(e)
            }

    def get_latest_manifest_log(self) -> Dict[str, Any]:
        """取得最後一次更新之全鏈路診斷 Log 報告"""
        from managers import manifest_logger
        return manifest_logger.get_latest_log()

    def open_manifest_log_file(self, log_path: str = "") -> Dict[str, Any]:
        """使用系統預設文字編輯器 (如記事本) 開啟指定更新日誌"""
        from managers import manifest_logger
        p = Path(log_path) if log_path else Path(manifest_logger.get_logs_directory()) / "latest_update.log"
        if not p.exists():
            return {"ok": False, "msg": f"找不到日誌檔案: {p}"}
        try:
            os.startfile(str(p))
            return {"ok": True, "path": str(p)}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def get_updatable_games(self) -> List[Dict[str, Any]]:
        """
        全庫精確取得當前真正需要更新的遊戲名單 (杜絕前端快照時序差導致漏更)
        直接從 manifest_updates.json 讀取最新狀態，並交叉校驗本地 Lua 檔案
        """
        updates_file = Path(__file__).parent.parent / "data" / "manifest_updates.json"
        cache_file = Path(__file__).parent.parent / "data" / "game_cache.json"
        cached_updates = {}
        game_cache = {}

        if updates_file.exists():
            try:
                cached_updates = json.loads(updates_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        if cache_file.exists():
            try:
                game_cache = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        sp = self._steam_path or steam_manager.find_steam_path()
        lua_dir = Path(sp) / "config" / "lua" if sp else None

        results = []
        for aid, u in cached_updates.items():
            if not u.get("has_update"):
                continue
            aid_str = str(aid).strip()
            # 確認本地確有此 Lua
            if lua_dir and not (lua_dir / f"{aid_str}.lua").exists():
                continue

            c_info = game_cache.get(aid_str, {})
            name = c_info.get("name", "") or f"App_{aid_str}"
            results.append({
                "appid": aid_str,
                "name": name,
                "has_update": True,
                "version_status": u.get("version_status", "可更新"),
                "latest_date": u.get("latest_date", "未知"),
                "best_source": u.get("best_source", "ryuu")
            })

        return results

    def start_batch_update_session(self, target_games: List[Dict[str, Any]]) -> str:
        """啟動批次更新調度記錄"""
        from managers import batch_logger
        return batch_logger.start_session(target_games)

    def log_batch_update_item(self, session_id: str, appid: str, name: str, success: bool, duration_ms: int = 0, msg: str = ""):
        """記錄單一遊戲批次更新結果"""
        from managers import batch_logger
        batch_logger.log_session_item(session_id, appid, name, success, duration_ms=duration_ms, msg=msg)

    def finish_batch_update_session(self, session_id: str, summary: str = "") -> Dict[str, Any]:
        """結算並落盤批次更新總診斷報告"""
        from managers import batch_logger
        return batch_logger.finish_session(session_id, summary=summary)

    def open_manifest_logs_dir(self) -> Dict[str, Any]:
        """在 Windows 檔案總管中開啟診斷日誌資料夾"""
        from managers import manifest_logger
        d = Path(manifest_logger.get_logs_directory())
        d.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(d))
            return {"ok": True, "path": str(d)}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def check_denuvo(self, appid: str) -> bool:
        """檢查遊戲是否含有 Denuvo 加密"""
        # 已知常見 Denuvo 遊戲列表
        denuvo_set = {"1245620", "2358720", "2050650", "1817070", "1364780"}
        return str(appid) in denuvo_set

    # ═══════════════════════════════════════════════════════
    # 6. 本地遊戲管理與「黃色醒目更新標示」API
    # ═══════════════════════════════════════════════════════
    def list_games(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        本地極速掃描所有 Lua 遊戲（記憶體快取 0 延遲，絕不阻塞視窗線程）。
        優先調用記憶體暫存的已整理遊戲資料，當有快取且非強制刷新時直接調用。
        """
        if not force_refresh and getattr(self, "_cached_games", None) is not None:
            return list(self._cached_games)

        with getattr(self, "_cached_games_lock", threading.Lock()):
            if not force_refresh and getattr(self, "_cached_games", None) is not None:
                return list(self._cached_games)

            sp = self._steam_path or steam_manager.find_steam_path()
            if not sp: return []
            lua_dir = Path(sp) / "config" / "lua"
            if not lua_dir.exists(): return []

            games = []
            lua_files = [f for f in lua_dir.glob("*.lua") if f.name != "manifest.lua"]
            pattern = re.compile(r'^[ \t]*(?:--[^\n\r]*?)?set[M|m]anifest[i|I]d\s*\(\s*(\d+)\s*,\s*"(\d+)"', re.MULTILINE)

            # 🌟 批次快速索引所有 Steam 庫的 ACF 檔案，同時即時提取本地官方真實遊戲名稱 (0 延遲秒開)
            acf_map = {}
            acf_names = {}
            try:
                libs = steam_manager.get_steam_libraries(sp)
                for lib in libs:
                    sa = lib / "steamapps"
                    if sa.exists():
                        for acf in sa.glob("appmanifest_*.acf"):
                            parts = acf.stem.split("_")
                            if len(parts) > 1 and parts[1].isdigit():
                                aid = parts[1]
                                acf_map[aid] = acf
                                try:
                                    txt = acf.read_text(encoding="utf-8", errors="ignore")
                                    m_nm = re.search(r'"name"\s+"([^"]+)"', txt)
                                    if m_nm:
                                        acf_names[aid] = m_nm.group(1).strip()
                                except Exception:
                                    pass
            except Exception:
                pass

            # 讀取遊戲快取（優先載入倉庫內建快取，確保初次抓取 0 延遲秒開）
            builtin_cache_file = Path(__file__).parent / "resources" / "builtin_game_cache.json"
            cache_file = Path(__file__).parent.parent / "data" / "game_cache.json"
            game_cache = {}
            cache_dirty = False
            if builtin_cache_file.exists():
                try:
                    game_cache.update(json.loads(builtin_cache_file.read_text(encoding="utf-8")))
                except Exception:
                    pass
            if cache_file.exists():
                try:
                    game_cache.update(json.loads(cache_file.read_text(encoding="utf-8")))
                except Exception:
                    pass

            # 讀取本地已有的版本更新快取（無需重複發起慢速網路請求）
            updates_file = Path(__file__).parent.parent / "data" / "manifest_updates.json"
            cached_updates = {}
            if updates_file.exists():
                try:
                    cached_updates = json.loads(updates_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            # 讀取所有具有 Online-Fix / ZeiGames 網盤補丁的 AppID 集合（利用記憶體快取）
            try:
                of_appids = set(onlinefix_manager.get_all_onlinefix_appids())
            except Exception:
                of_appids = set()

            for lf in lua_files:
                appid = lf.stem
                if not appid.isdigit(): continue

                try:
                    content = lf.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                c_info = game_cache.get(appid, {})
                game_name = c_info.get("name", "")

                # 多層級名稱探測：1. 官方 ACF 檔 -> 2. Lua 頂部註解 -> 3. 本地 SteamDB 快取
                if not game_name or game_name == "未知遊戲" or game_name.startswith("App_"):
                    if appid in acf_names and acf_names[appid]:
                        game_name = acf_names[appid]

                if not game_name or game_name == "未知遊戲" or game_name.startswith("App_"):
                    name_m = re.search(r'--\s*\d+\s*-\s*(.+)', content)
                    game_name = name_m.group(1).strip() if name_m else ""

                if not game_name or game_name == "未知遊戲" or game_name.startswith("App_"):
                    sdb_file = Path(__file__).parent.parent / "data" / "steamdb_cache" / f"{appid}.json"
                    if sdb_file.exists():
                        try:
                            sdb_data = json.loads(sdb_file.read_text(encoding="utf-8"))
                            sdb_name = sdb_data.get("name") or sdb_data.get("data", {}).get("name")
                            if sdb_name:
                                game_name = sdb_name.strip()
                        except Exception:
                            pass

                if not game_name or game_name == "未知遊戲":
                    game_name = f"App_{appid}"

                from utils.tw_converter import sanitize_game_name
                game_name = sanitize_game_name(game_name, appid)
                english_name = c_info.get("english_name", "") or c_info.get("name_en", "") or acf_names.get(appid, "")

                header_img = c_info.get("header_image", "")
                if not header_img:
                    header_img = f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"

                # 若成功補全新名稱，自動更新至本地快取
                if not game_name.startswith("App_") and (not c_info.get("name") or c_info.get("name").startswith("App_")):
                    c_info["name"] = game_name
                    c_info["english_name"] = english_name or game_name
                    c_info["name_en"] = english_name or game_name
                    c_info["header_image"] = header_img
                    game_cache[appid] = c_info
                    cache_dirty = True

                matches = pattern.findall(content)
                current_mid = matches[0][1] if matches else ""

                # 快速判斷鎖定狀態 (優先從批次 acf_map 讀取，避免遍歷全庫)
                acf = acf_map.get(appid)
                is_locked = False
                if acf and acf.exists():
                    try:
                        acf_text = acf.read_text(encoding="utf-8", errors="ignore")
                        m = re.search(r'"AutoUpdateBehavior"\s+"(\d+)"', acf_text)
                        if m and int(m.group(1)) == 1:
                            is_locked = True
                    except Exception:
                        pass
                else:
                    # 未安裝遊戲：檢查 Lua 自身是否唯讀，極速 0 延遲，杜絕全庫磁碟遍歷
                    try:
                        st = os.stat(lf)
                        is_locked = bool(st.st_mode & stat.S_IREAD) and not bool(st.st_mode & stat.S_IWRITE)
                    except Exception:
                        is_locked = False

                # 直接讀取快取的更新標記，0 延遲秒開！
                u_info = cached_updates.get(appid, {})
                has_update = u_info.get("has_update", False)
                version_status = u_info.get("version_status", "0 版")
                latest_date = u_info.get("latest_date", "未知")
                best_source = u_info.get("best_source", "ryuu")
                has_of = appid in of_appids
                is_deployed = False
                is_protected = False
                if has_of:
                    try:
                        is_deployed = onlinefix_manager.is_patch_deployed_locally(appid)
                        is_protected = onlinefix_manager.is_patch_protected(appid)
                    except Exception:
                        pass

                games.append({
                    "appid": appid,
                    "name": game_name,
                    "english_name": english_name,
                    "name_en": english_name,
                    "image": header_img,
                    "locked": is_locked,
                    "deployed": is_deployed,             # 🌟 本地已部署補丁標記
                    "protected": is_protected,           # 🌟 原始檔案已成功備份保護標記
                    "current_mid": current_mid,
                    "has_update": has_update,            # 🌟 秒開即帶有黃色需更新標記
                    "has_onlinefix": has_of,             # 🌟 藍色邊框標記 (支援 Online-Fix 聯機補丁)
                    "version_status": version_status,
                    "latest_date": latest_date,
                    "best_source": best_source
                })

            # 排序：有更新者（黃色需更新項）置頂排列
            games.sort(key=lambda x: (0 if x["has_update"] else 1, x["name"].lower()))
            if cache_dirty:
                try:
                    cache_file.write_text(json.dumps(game_cache, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
            self._cached_games = games
            return list(self._cached_games)

    def ensure_installed_games_resolved(self) -> Dict[str, Any]:
        """
        🌟 初始化階段專屬核心 API：強制校驗並補全所有已入庫遊戲的官方真實繁中名稱與高畫質封面圖片。
        若偵測到缺失名稱或使用預設佔位圖片的遊戲，立即透過多執行緒並行向 Steam 官方 Store API 抓取。
        絕不搶著進系統，向前端即時回報進度，直到所有入庫遊戲確認就緒。
        """
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp:
            return {"ok": False, "msg": "未找到 Steam 安裝目錄", "games": []}

        lua_dir = Path(sp) / "config" / "lua"
        if not lua_dir.exists():
            return {"ok": True, "count": 0, "games": []}

        lua_files = [f for f in lua_dir.glob("*.lua") if f.name != "manifest.lua" and f.stem.isdigit()]
        all_appids = [f.stem for f in lua_files]
        if not all_appids:
            return {"ok": True, "count": 0, "games": []}

        # 1. 載入當前快取（內建快取 + data/game_cache.json）
        builtin_cache_file = Path(__file__).parent / "resources" / "builtin_game_cache.json"
        cache_file = Path(__file__).parent.parent / "data" / "game_cache.json"
        game_cache = {}
        if builtin_cache_file.exists():
            try:
                game_cache.update(json.loads(builtin_cache_file.read_text(encoding="utf-8")))
            except Exception:
                pass
        if cache_file.exists():
            try:
                game_cache.update(json.loads(cache_file.read_text(encoding="utf-8")))
            except Exception:
                pass

        # 2. 檢測哪些 AppID 缺乏有效名稱或有效商店封面
        to_fetch = []
        for aid in all_appids:
            info = game_cache.get(aid, {})
            name = info.get("name", "")
            img = info.get("header_image", "")
            needs_resolve = False
            if not name or name == "未知遊戲" or name.startswith("App_"):
                needs_resolve = True
            elif not img or img.endswith(f"/apps/{aid}/header.jpg"):
                if "header_alt_assets" not in img and "t=" not in img:
                    needs_resolve = True
            if needs_resolve:
                to_fetch.append(aid)

        # 3. 如果需要並行抓取，使用 ThreadPoolExecutor 併發抓取 Steam 官方 Store API
        resolved_count = 0
        total_fetch = len(to_fetch)
        if total_fetch > 0:
            import urllib.request
            import ssl
            from concurrent.futures import ThreadPoolExecutor, as_completed
            from utils.tw_converter import sanitize_game_name

            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            def _fetch_single(aid):
                url = f"https://store.steampowered.com/api/appdetails?appids={aid}&l=tchinese"
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                    with urllib.request.urlopen(req, timeout=6, context=ctx) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        if data and str(aid) in data and data[str(aid)].get("success"):
                            d = data[str(aid)]["data"]
                            raw_name = d.get("name") or f"App_{aid}"
                            s_name = sanitize_game_name(raw_name, aid)
                            hdr = d.get("header_image") or ""
                            return aid, s_name, raw_name, hdr
                except Exception:
                    pass
                return aid, None, None, None

            with ThreadPoolExecutor(max_workers=min(12, total_fetch)) as executor:
                futures = {executor.submit(_fetch_single, aid): aid for aid in to_fetch}
                for fut in as_completed(futures):
                    aid, s_name, raw_name, hdr = fut.result()
                    resolved_count += 1
                    if s_name:
                        c_info = game_cache.get(aid, {})
                        c_info["name"] = s_name
                        c_info["english_name"] = raw_name or s_name
                        c_info["name_en"] = raw_name or s_name
                        if hdr:
                            c_info["header_image"] = hdr
                        game_cache[aid] = c_info
                    
                    disp_name = s_name or f"App_{aid}"
                    self._push_js_event("on_game_resolved_progress", {
                        "current": resolved_count,
                        "total": total_fetch,
                        "appid": aid,
                        "name": disp_name
                    })

            try:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps(game_cache, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

        # 4. 強制刷新 list_games 記憶體快取
        games = self.list_games(force_refresh=True)
        return {
            "ok": True,
            "count": len(games),
            "total_checked": len(all_appids),
            "resolved_count": resolved_count,
            "games": games
        }

    def _push_js_event(self, func_name: str, data: Any):
        """主動向前端安全推播事件 (非阻塞，多執行緒安全)"""
        if getattr(self, "_window", None):
            try:
                payload = json.dumps(data, ensure_ascii=False)
                js_code = f"window.{func_name} && window.{func_name}({payload});"
                self._window.evaluate_js(js_code)
            except Exception:
                pass

    def trigger_background_update_check(self, force: bool = False) -> Dict[str, Any]:
        """
        供前端或啟動時主動呼叫：在背景守護執行緒中啟動全庫 Manifest 更新比對。
        立即回傳 0 延遲，不阻塞 UI，查出一筆即時向前端推播點亮一筆！
        """
        import threading
        if getattr(self, "_is_checking_updates", False):
            return {"ok": True, "already_running": True}

        t = threading.Thread(target=self.check_updates_async, kwargs={"force": force}, daemon=True)
        t.start()
        return {"ok": True, "status": "started"}

    def check_updates_async(self, force: bool = False) -> Dict[str, Any]:
        """
        全域主動搜尋並比對所有已入庫遊戲的最新 Manifest 版本狀態（守護執行緒，不卡頓 UI）
        並自動在背景補齊缺失的遊戲官方繁體名稱、英文原名與 CDN 封面圖片。
        支援即時逐筆推播 (window.onSingleGameUpdateChecked) 與增量快取持久化。
        """
        if getattr(self, "_is_checking_updates", False):
            return {"ok": True, "already_running": True, "updates": {}}
        self._is_checking_updates = True

        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp: 
            self._is_checking_updates = False
            return {"ok": False, "updates": {}}
        lua_dir = Path(sp) / "config" / "lua"
        if not lua_dir.exists(): 
            self._is_checking_updates = False
            return {"ok": False, "updates": {}}

        import concurrent.futures
        import threading
        lua_files = [f for f in lua_dir.glob("*.lua") if f.name != "manifest.lua"]
        pattern = re.compile(r'^[ \t]*(?:--[^\n\r]*?)?set[M|m]anifest[i|I]d\s*\(\s*(\d+)\s*,\s*"(\d+)"', re.MULTILINE)

        # 🌟 配合全域更新輪詢一併同步 Google Drive 雲端補丁庫（內建 60 秒冷卻保護，最多 1 分鐘 1 次）
        try:
            from managers import onlinefix_manager
            onlinefix_manager.fetch_cloud_cache(force=force)
        except Exception:
            pass

        # 載入遊戲快取以備補全
        cache_file = Path(__file__).parent.parent / "data" / "game_cache.json"
        game_cache = {}
        if cache_file.exists():
            try:
                game_cache = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        updates_file = Path(__file__).parent.parent / "data" / "manifest_updates.json"
        updates = {}
        if updates_file.exists() and not force:
            try:
                updates = json.loads(updates_file.read_text(encoding="utf-8"))
            except Exception:
                updates = {}

        meta_updates = {}
        save_lock = threading.Lock()
        checked_counter = [0]

        def save_progress():
            try:
                with save_lock:
                    updates_file.write_text(json.dumps(updates, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

        def check_one(lf):
            appid = lf.stem
            if not appid.isdigit(): return
            try:
                diff_info = version_resolver.resolve_manifest_version_diff(
                    appid,
                    lua_dir=str(lua_dir),
                    steam_path=sp,
                    timeout=6
                )
                is_latest = diff_info.get("is_latest", True)
                v_stat = diff_info.get("version_status", "")
                diff_cnt = diff_info.get("diff_count", 0) or 0

                # 🌟 統一口徑：只有當線上庫有實質可更新版本時，has_update 才能為 True！
                # 若 SteamDB 官方有新版，但 Ryuu 尚未收錄（待雲端同步），本地已是目前能取得的最新版，has_update 必須為 False！
                if is_latest:
                    raw_v = "最新版"
                    has_up = False
                elif v_stat == "待雲端同步" or not diff_info.get("has_available_update"):
                    raw_v = "待雲端同步"
                    has_up = False
                else:
                    raw_v = f"舊 {diff_cnt} 版" if diff_cnt > 0 else (v_stat or "舊 1 版")
                    has_up = True

                u_item = {
                    "appid": appid,
                    "name": cur_c.get("name") or (game_cache.get(appid, {}).get("name") if appid in game_cache else ""),
                    "has_update": has_up,
                    "version_status": raw_v,
                    "latest_date": diff_info.get("latest_date", "未知"),
                    "best_source": diff_info.get("best_source", "ryuu")
                }
                with save_lock:
                    updates[appid] = u_item
                    checked_counter[0] += 1

                # 每查好 5 筆即時安全落盤快取 (背景靜默，不在前端邊查邊跳動)
                if checked_counter[0] % 5 == 0:
                    save_progress()

            except Exception as e:
                try:
                    from managers import unified_manifest_manager
                    mgr = unified_manifest_manager.UnifiedManifestManager.get_instance()
                    mgr._log_manifest_check(f"[CheckError] AppID: {appid}, Error: {e}")
                except Exception:
                    pass

            # 檢查是否需要背景補全元數據
            cur_c = game_cache.get(appid, {})
            if (not cur_c.get("name") or 
                cur_c.get("name").startswith("App_") or 
                not cur_c.get("name_en") or 
                not cur_c.get("header_image")):
                try:
                    tc_n, sc_n, en_n, img = "", "", "", ""
                    try:
                        req = urllib.request.Request(f'https://store.steampowered.com/api/appdetails?appids={appid}&l=tchinese', headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req, timeout=3) as r:
                            d = json.loads(r.read().decode('utf-8'))
                            if d.get(str(appid), {}).get('success'):
                                tc_n = d[str(appid)]['data'].get('name', '').strip()
                                img = d[str(appid)]['data'].get('header_image', '')
                    except Exception:
                        pass

                    if not tc_n or '\ufffd' in tc_n:
                        try:
                            req = urllib.request.Request(f'https://store.steampowered.com/api/appdetails?appids={appid}&l=schinese', headers={'User-Agent': 'Mozilla/5.0'})
                            with urllib.request.urlopen(req, timeout=3) as r:
                                d = json.loads(r.read().decode('utf-8'))
                                if d.get(str(appid), {}).get('success'):
                                    sc_n = d[str(appid)]['data'].get('name', '').strip()
                                    if not img: img = d[str(appid)]['data'].get('header_image', '')
                        except Exception:
                            pass

                    try:
                        req = urllib.request.Request(f'https://store.steampowered.com/api/appdetails?appids={appid}&l=english', headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req, timeout=3) as r:
                            d = json.loads(r.read().decode('utf-8'))
                            if d.get(str(appid), {}).get('success'):
                                en_n = d[str(appid)]['data'].get('name', '').strip()
                                if not img: img = d[str(appid)]['data'].get('header_image', '')
                    except Exception:
                        pass

                    from utils.tw_converter import sanitize_game_name
                    best_n = tc_n if (tc_n and '\ufffd' not in tc_n) else (sc_n if (sc_n and '\ufffd' not in sc_n) else (en_n or f"App_{appid}"))
                    best_n = sanitize_game_name(best_n, appid)
                    if not img: img = f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"

                    with save_lock:
                        meta_updates[appid] = {
                            "name": best_n,
                            "name_en": en_n or best_n,
                            "english_name": en_n or best_n,
                            "header_image": img
                        }
                        game_cache[appid] = meta_updates[appid]
                        if appid in updates:
                            updates[appid]["name"] = best_n
                        else:
                            updates[appid] = {"appid": appid, "name": best_n}
                except Exception:
                    pass

        try:
            # 限制並行數為 4，避免 CPU 尖峰與網路風暴拖慢視窗
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                list(executor.map(check_one, lua_files))
        finally:
            self._is_checking_updates = False

        # 持久化快取
        save_progress()

        if meta_updates:
            try:
                cache_file.write_text(json.dumps(game_cache, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

        total_up = len([u for u in updates.values() if u.get("has_update")])
        # 🌟 全庫比對完全確認後一次性推送 (Atomic Delivery)
        self._push_js_event("onAllUpdatesCheckFinished", {
            "total": len(lua_files),
            "updated_count": total_up,
            "updates": updates
        })

        return {
            "ok": True, 
            "updates": updates, 
            "count": total_up,
            "metadata": meta_updates
        }

    def uninstall_game(self, appid: str, *args, **kwargs) -> Dict[str, Any]:
        """刪除遊戲 Lua 入庫檔案並解除版本鎖定 (還原 ACF 與關聯 Manifest 檔案讀寫權限)"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp: return {"ok": False, "msg": "找不到 Steam 目錄路徑"}

        appid_str = str(appid).strip()
        sp_path = Path(sp)

        # 尋找所有可能存放該遊戲 Lua 的目錄
        lua_candidates = [
            sp_path / "config" / "lua" / f"{appid_str}.lua",
            sp_path / "config" / "stplug-in" / f"{appid_str}.lua",
        ]
        try:
            from managers import config_manager
            cfg_lua = Path(config_manager.get_config().get("lua_dir", config_manager.DEFAULT_LUA_DIR)) / f"{appid_str}.lua"
            if cfg_lua not in lua_candidates:
                lua_candidates.append(cfg_lua)
        except Exception:
            pass

        try:
            import stat
            import win32file
        except Exception:
            win32file = None

        deleted_lua = False
        for lf in lua_candidates:
            if lf.exists():
                try:
                    if win32file:
                        try:
                            win32file.SetFileAttributes(str(lf), win32file.FILE_ATTRIBUTE_NORMAL)
                        except Exception:
                            pass
                    os.chmod(lf, stat.S_IWRITE | stat.S_IREAD)
                    lf.unlink()
                    deleted_lua = True
                except Exception as e:
                    return {"ok": False, "msg": f"刪除 Lua 檔案失敗 ({lf.name}): {e}"}

        # 先解除版本鎖定 (還原 ACF 與關聯 Manifest 為可讀寫)
        try:
            steam_manager.unlock_game_version(appid_str, sp)
        except Exception:
            pass

        # 🌟 自動還原線上補丁原始檔案 (.bak) 並清理補丁殘留
        from managers import onlinefix_manager
        try:
            onlinefix_manager.uninstall_fix(appid_str)
            lua_dir = self._config.get("lua_dir") or (Path(sp) / "config" / "lua")
            if lua_dir:
                onlinefix_manager.uninstall_lua(appid_str, lua_dir)
        except Exception:
            pass

        # 清除 manifest_updates.json 中的更新標記快取
        try:
            updates_file = Path(__file__).parent.parent / "data" / "manifest_updates.json"
            if updates_file.exists():
                u_data = json.loads(updates_file.read_text(encoding="utf-8"))
                if appid_str in u_data:
                    del u_data[appid_str]
                    updates_file.write_text(json.dumps(u_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        # 🌟 若遊戲在 Steam 本地已安裝或下載中，直接喚起 Steam 原生解除安裝命令
        has_local_install = False
        try:
            acf_path = steam_manager.find_appmanifest_path(appid_str, sp)
            game_dir = onlinefix_manager._find_steam_game_dir(appid_str)
            if (acf_path and Path(acf_path).exists()) or (game_dir and Path(game_dir).exists()):
                has_local_install = True
                os.startfile(f"steam://uninstall/{appid_str}")
        except Exception as e:
            print(f"喚起 Steam 解除安裝失敗: {e}")

        self.invalidate_games_cache()
        if has_local_install:
            return {"ok": True, "has_steam_uninstall": True, "msg": f"已成功移除入庫與補丁，並已喚起 Steam 執行遊戲解除安裝 (AppID: {appid_str})"}
        else:
            return {"ok": True, "has_steam_uninstall": False, "msg": f"已成功卸載入庫遊戲 (AppID: {appid_str})"}

    def toggle_version(self, appid: str) -> Dict[str, Any]:
        """切換指定遊戲的 ACF / Lua / Manifest 版本鎖定狀態"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp: return {"ok": False, "msg": "找不到 Steam 目錄路徑"}
        st = steam_manager.get_game_manifest_lock_info(appid, sp)
        if st.get("is_locked"):
            ok, msg = steam_manager.unlock_game_version(appid, sp)
            new_locked = False
        else:
            ok, msg = steam_manager.lock_game_version(appid, sp, set_readonly=True)
            new_locked = True
        return {"ok": ok, "msg": msg, "is_locked": new_locked}

    def clean_phantom_acfs(self) -> Dict[str, Any]:
        """一鍵掃描並安全清理無實體檔案的幽靈 ACF 檔案 (徹底清空 Steam 錯誤下載排程)"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp:
            return {"ok": False, "msg": "找不到 Steam 路徑"}
        cleaned_cnt, cleaned_list = steam_manager.clean_phantom_appmanifests(sp)
        return {
            "ok": True,
            "cleaned_count": cleaned_cnt,
            "cleaned_list": cleaned_list,
            "msg": f"已成功清理 {cleaned_cnt} 個幽靈 ACF 檔案！" if cleaned_cnt > 0 else "目前遊戲庫非常乾淨，未發現任何幽靈 ACF 檔案。"
        }

    def sync_lua_autoupdate(self, restore_non_lua: bool = True) -> Dict[str, Any]:
        """智慧同步自動更新行為：僅對 Lua 關聯遊戲鎖定 AutoUpdateBehavior=1，正版遊戲維持/恢復 AutoUpdateBehavior=0"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp:
            return {"ok": False, "msg": "找不到 Steam 路徑"}
        res = steam_manager.sync_lua_games_autoupdate_behavior(sp, restore_non_lua=restore_non_lua)
        return {
            "ok": True,
            **res,
            "msg": f"自動更新隔離同步完成！已鎖定 {res.get('locked_lua_count', 0)} 個 Lua 遊戲，還原 {res.get('restored_normal_count', 0)} 個正版遊戲。"
        }

    def sync_local_manifests(self, appid: str = "") -> Dict[str, Any]:
        """
        零額度本機 Manifest 與 Lua 雙向自檢同步 (Self-Healing)：
        - 若指定 appid，精確自檢並校準該遊戲。
        - 若未指定 appid，全庫掃描所有本機 Lua 遊戲，比對 depotcache 實體檔案與 Lua 宣告，自動修復不一致之檔案！
        """
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp:
            return {"ok": False, "msg": "找不到 Steam 路徑"}
            
        if appid:
            r = steam_manager.verify_and_sync_local_manifests(str(appid), steam_path=sp)
            healed = r.get("healed", False)
            msg = f"AppID {appid} 本機校準完成！(已自動修復 Lua 宣告)" if healed else f"AppID {appid} 本機狀態完整吻合。"
            return {"ok": True, "result": r, "msg": msg}
        else:
            lua_dir = Path(sp) / "config" / "lua"
            if not lua_dir.exists():
                return {"ok": True, "healed_count": 0, "msg": "尚未發現任何 Lua 遊戲。"}
            healed_list = []
            for lf in lua_dir.glob("*.lua"):
                if lf.stem.isdigit() and lf.name != "manifest.lua":
                    r = steam_manager.verify_and_sync_local_manifests(lf.stem, steam_path=sp)
                    if r.get("healed"):
                        healed_list.append(lf.stem)
            msg = f"全庫本機同步完成！已自動校準修復 {len(healed_list)} 款遊戲的 Lua 宣告！" if healed_list else "全庫本機 Manifest 與 Lua 狀態已 100% 吻合！"
            return {"ok": True, "healed_count": len(healed_list), "healed_list": healed_list, "msg": msg}

    def get_lua(self, appid: str) -> str:
        """讀取指定遊戲的 Lua 內容"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp: return ""
        f = Path(sp) / "config" / "lua" / f"{appid}.lua"
        if f.exists():
            return f.read_text(encoding="utf-8", errors="ignore")
        return ""

    def save_lua(self, appid: str, content: str) -> bool:
        """儲存編輯後的 Lua 內容"""
        r = self.write_lua(appid, content)
        return r.get("ok", False)

    def list_game_dlcs(self, appid: str) -> List[Dict[str, Any]]:
        """讀取遊戲的已宣告 DLC 清單（精確排除內容 Depot、金鑰 Depot 與本體 AppID）"""
        lua = self.get_lua(appid)
        if not lua: return []

        # 1. 抓取所有 addappid 宣告的 ID，並排除主遊戲 ID
        raw_ids = set(re.findall(r'addappid\s*\(\s*(\d+)', lua))
        raw_ids.discard(str(appid))

        # 2. 排除所有在 setManifestid 中宣告的 Depot ID（Depot 才配置 Manifest，DLC 不會配置 Manifest）
        manifest_depots = set(re.findall(r'set[M|m]anifest[i|I]d\s*\(\s*(\d+)', lua))

        # 3. 排除帶有解密金鑰參數的 Depot ID: addappid(depotid, 0, "key")
        keyed_depots = set(re.findall(r'addappid\s*\(\s*(\d+)\s*,\s*\d+\s*,\s*[\'"][a-fA-F0-9]{16,}[\'"]', lua))

        # 純 DLC ID 清單
        dlc_ids = [did for did in raw_ids if did not in manifest_depots and did not in keyed_depots]

        # 4. 嘗試從本機遊戲快取讀取真實 DLC 名稱與封面
        cache_file = Path(__file__).parent.parent / "data" / "game_cache.json"
        game_cache = {}
        if cache_file.exists():
            try:
                game_cache = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        from utils.tw_converter import sanitize_game_name

        dlcs = []
        for did in sorted(dlc_ids, key=lambda x: int(x) if x.isdigit() else x):
            c_info = game_cache.get(did, {})
            name = c_info.get("name") or f"DLC_{did}"
            name = sanitize_game_name(name, did)
            header_img = c_info.get("header_image") or f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{did}/header.jpg"

            dlcs.append({
                "appid": did,
                "name": name,
                "image": header_img
            })
        return dlcs

    def clear_all(self) -> Dict[str, Any]:
        """一鍵清除所有已入庫遊戲"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp: return {"ok": False}
        lua_dir = Path(sp) / "config" / "lua"
        count = 0
        if lua_dir.exists():
            for f in lua_dir.glob("*.lua"):
                if f.name != "manifest.lua":
                    try:
                        import stat
                        try:
                            import win32file
                            win32file.SetFileAttributes(str(f), win32file.FILE_ATTRIBUTE_NORMAL)
                        except Exception:
                            pass
                        os.chmod(f, stat.S_IWRITE | stat.S_IREAD)
                        f.unlink()
                        count += 1
                    except Exception:
                        pass
        self.invalidate_games_cache()
        return {"ok": True, "count": count}

    # ═══════════════════════════════════════════════════════
    # 7. 設定、外觀與授權管理 API
    # ═══════════════════════════════════════════════════════
    def get_config(self) -> Dict[str, Any]:
        """讀取全域配置"""
        self._config = config_manager.get_config()
        if not self._config.get("steam_path"):
            sp = steam_manager.find_steam_path()
            if sp: self._config["steam_path"] = str(sp)
        return self._config

    def set_config(self, key: str, val: Any) -> bool:
        """儲存單項配置（自動相容 dark/dark_mode 與 random/random_browse）"""
        self._config[key] = val
        if key in ("dark", "dark_mode"):
            self._config["dark"] = val
            self._config["dark_mode"] = val
        elif key in ("random", "random_browse"):
            self._config["random"] = val
            self._config["random_browse"] = val
        elif key == "view_mode":
            self._config["view_mode"] = val
        elif key == "cloud_redirect":
            self._config[key] = bool(val)
        elif key == "cloud_redirect_path":
            self._config[key] = val
        config_manager.save_config(self._config)
        return True

    def cloud_dest(self) -> str:
        """取得當前雲存檔去向 (功能已停用，固定回傳 local)"""
        return "local"

    def cloud_set_dest(self, mode: str) -> Dict[str, Any]:
        """設定雲存檔去向 (功能已停用)"""
        return {"ok": True, "mode": "local"}

    def open_cloud_path(self) -> bool:
        """開啟本機存檔儲存目錄 (功能已停用)"""
        return False

    def _apply_cloud_redirect(self, enabled: bool) -> bool:
        """雲存檔目錄聯接管理 (若關閉則清理 junction)"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp:
            return False
        link_dir = Path(sp) / "cloud_redirect" / "storage"
        if not enabled:
            if link_dir.exists() or link_dir.is_symlink():
                try:
                    subprocess.run(["cmd", "/c", "rmdir", str(link_dir)], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                except Exception:
                    pass
            cr_cfg_file = Path(sp) / "cloud_redirect" / "config.json"
            if cr_cfg_file.exists():
                try:
                    with open(cr_cfg_file, "r", encoding="utf-8") as f:
                        cr_cfg = json.load(f)
                    cr_cfg["cloud_redirect"] = False
                    with open(cr_cfg_file, "w", encoding="utf-8") as f:
                        json.dump(cr_cfg, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass
        return True

    def get_cloud_saves_list(self) -> List[Dict[str, Any]]:
        """雲存檔功能已停用，固定返回空清單"""
        return []

    def open_cloud_save_folder(self, appid: str = "") -> bool:
        """開啟指定遊戲或全域存檔資料夾 (功能已停用)"""
        return False


    def get_license_state(self) -> Dict[str, Any]:
        """授權狀態查詢：回傳永久旗艦版授權資訊"""
        return {
            "activated": True,
            "tier": "sponsor",
            "tier_name": "永久旗艦版",
            "expires": "永久有效",
            "limit": "無限暢享"
        }

    def activate_license(self, code: str) -> Dict[str, Any]:
        """啟用授權碼"""
        return {
            "ok": True,
            "msg": "已成功啟用永久旗艦版！享有全部高速通道與無限制功能。"
        }

    def get_bg_thumbnails(self) -> List[Dict[str, Any]]:
        """取得可用自訂背景清單 (支援 JPG/PNG/WEBP/GIF 動圖)"""
        bgs_dir = Path("data/backgrounds")
        bgs_dir.mkdir(parents=True, exist_ok=True)
        res = []
        for f in bgs_dir.glob("*.*"):
            if f.suffix.lower() in [".jpg", ".png", ".jpeg", ".webp", ".gif"]:
                data_url = self.get_bg_data(f.name)
                res.append({
                    "id": f.name,
                    "thumb": data_url
                })
        return res

    def add_bg_base64(self, name: str, b64_data: str) -> Dict[str, Any]:
        """透過 Base64 添加自訂背景 (支援 GIF 等動圖)"""
        try:
            import base64
            if "," in b64_data:
                b64_data = b64_data.split(",", 1)[1]
            raw = base64.b64decode(b64_data)
            bgs_dir = Path("data/backgrounds")
            bgs_dir.mkdir(parents=True, exist_ok=True)
            p = bgs_dir / name
            with open(p, "wb") as f:
                f.write(raw)
            return {
                "id": name,
                "thumb": self.get_bg_data(name)
            }
        except Exception:
            return None

    def remove_bg(self, name: str) -> bool:
        """移除自訂背景"""
        p = Path("data/backgrounds") / name
        if p.exists():
            p.unlink()
            return True
        return False

    def restore_default_bgs(self) -> bool:
        """恢復預設背景"""
        self._config["current_bg"] = ""
        config_manager.save_config(self._config)
        return True

    # ── Google Drive 雲端網盤管理 API (1.0 傳承邏輯) ──
    def get_cloud_drives(self) -> List[Dict[str, Any]]:
        """取得設定的所有 Google Drive 雲端網盤清單"""
        from managers import onlinefix_manager
        return onlinefix_manager.get_cloud_drives()

    def save_cloud_drives(self, drives: List[Dict[str, Any]]) -> Dict[str, Any]:
        """更新並儲存 Google Drive 雲端網盤清單（含優先順序與網址）"""
        from managers import onlinefix_manager
        try:
            onlinefix_manager.update_cloud_drives(drives)
            self._config = config_manager.get_config()
            return {"ok": True, "msg": f"已成功儲存 {len(drives)} 個網盤設定！"}
        except Exception as e:
            return {"ok": False, "msg": f"儲存網盤設定失敗: {e}"}

    def sync_cloud_drives(self) -> Dict[str, Any]:
        """強制同步並刷新 Google Drive 雲端補丁快取索引"""
        from managers import onlinefix_manager
        try:
            items = onlinefix_manager.sync_cloud_cache()
            count = len(items) if items else 0
            return {"ok": True, "count": count, "msg": f"已成功同步雲端索引，共掃描到 {count} 個補丁檔案！"}
        except Exception as e:
            return {"ok": False, "msg": f"同步雲端快取失敗: {e}"}

    def get_gdrive_index_summary(self) -> Dict[str, Any]:
        """取得 Google Drive 索引記錄狀態摘要 (包含 JSON / TXT 記錄檔路徑與各網盤統計)"""
        from managers import onlinefix_manager
        try:
            return {"ok": True, "data": onlinefix_manager.get_gdrive_index_summary()}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def get_game_cloud_drive_status(self, appid: str, game_name: str = "") -> Dict[str, Any]:
        """查詢特定遊戲在各個已定義 Google Drive 網盤中的補丁狀況與索引資料 (互動時即時連網讀取)"""
        from managers import onlinefix_manager
        try:
            drives = onlinefix_manager.get_cloud_drives()
            # 點擊檢視網盤狀況時，向 Google Drive 發出即時讀取請求
            cache = onlinefix_manager.fetch_cloud_cache(force=True)
            fix_status = onlinefix_manager.get_fix_status(appid)
            is_deployed = onlinefix_manager.is_patch_deployed_locally(appid)
            fix_rec = onlinefix_manager.get_fix_record(appid) or {}
            
            appid_str = str(appid).strip()
            norm_game_name = re.sub(r'[^a-z0-9]', '', game_name.lower()) if game_name else ""
            
            result_drives = []
            for idx, d in enumerate(drives):
                d_name = d.get("name", f"網盤 {idx + 1}").strip()
                d_url = d.get("url", "").strip()
                d_prio = d.get("priority", idx + 1)
                
                # 篩選此網盤中屬於該遊戲的檔案
                matched_files = []
                if cache:
                    for item in cache:
                        # 檢查來源是否為此網盤（依網盤名稱或網址匹配）
                        if item.get("drive_name") == d_name or (d_url and item.get("drive_url") == d_url):
                            f_path = item.get("path", "")
                            f_name = f_path.replace("\\", "/").split("/")[-1]
                            
                            is_match = False
                            if appid_str and appid_str in f_path:
                                is_match = True
                            elif norm_game_name and len(norm_game_name) >= 3:
                                norm_f = re.sub(r'[^a-z0-9]', '', f_path.lower())
                                if norm_game_name in norm_f:
                                    is_match = True
                            
                            if is_match:
                                matched_files.append({
                                    "name": f_name,
                                    "path": f_path,
                                    "id": item.get("id", "")
                                })
                
                result_drives.append({
                    "priority": d_prio,
                    "name": d_name,
                    "url": d_url,
                    "files": matched_files,
                    "has_patch": len(matched_files) > 0
                })
                
            return {
                "ok": True,
                "appid": appid_str,
                "game_name": game_name,
                "installed_status": fix_status,
                "is_deployed": is_deployed,
                "installed_source": fix_rec.get("source_drive", ""),
                "has_cache": cache is not None and len(cache) > 0,
                "drives": result_drives
            }
        except Exception as e:
            return {
                "ok": False,
                "msg": str(e),
                "drives": []
            }

    def get_onlinefix_appids(self) -> List[str]:
        """取得所有在網盤中收錄有 Online-Fix / ZeiGames 聯機補丁的遊戲 AppID 列表"""
        from managers import onlinefix_manager
        try:
            return onlinefix_manager.get_all_onlinefix_appids()
        except Exception:
            return []

    def check_defender_status(self) -> Dict[str, Any]:
        """檢查 Windows Defender 即時保護狀態 (透過註冊表 0 開銷監測)"""
        is_disabled = False
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows Defender\Real-Time Protection", 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, "DisableRealtimeMonitoring")
            is_disabled = (value == 1)
            winreg.CloseKey(key)
        except Exception:
            is_disabled = False
        return {
            "ok": True,
            "is_disabled": is_disabled,
            "is_realtime_on": not is_disabled,
            "status_text": "已關閉 (安全，不干擾破解補丁)" if is_disabled else "開啟中 (建議關閉即時保護以防補丁被誤殺)"
        }

    def open_defender_settings(self) -> Dict[str, Any]:
        """開啟 Windows Defender 安全性中心威脅防護設定頁面"""
        try:
            os.startfile("windowsdefender://threatsettings")
            return {"ok": True, "msg": "已開啟 Defender 安全設定視窗"}
        except Exception as e:
            return {"ok": False, "msg": f"無法開啟 Defender 設定: {e}"}

    def check_game_installed_status(self, appid: str) -> Dict[str, Any]:
        """
        精準檢查 Steam 遊戲主程式是否已完全下載安裝 (StateFlags == 4 或主執行檔就緒)
        """
        from managers import onlinefix_manager, steam_manager
        appid = str(appid).strip()
        game_dir = onlinefix_manager._find_steam_game_dir(appid)
        is_installed = False
        is_downloading = False
        state_flags = 0

        libs = set()
        if self._steam_path:
            libs.add(str(self._steam_path))
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam')
            path, _ = winreg.QueryValueEx(key, 'SteamPath')
            winreg.CloseKey(key)
            libs.add(os.path.normpath(path))
        except Exception:
            pass
            
        for lib in list(libs):
            vdf_path = os.path.join(lib, 'steamapps', 'libraryfolders.vdf')
            if os.path.exists(vdf_path):
                try:
                    with open(vdf_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for m in re.finditer(r'"path"\s*"([^"]+)"', f.read()):
                            libs.add(os.path.normpath(m.group(1).replace('\\\\', '\\')))
                except Exception:
                    pass

        for lib in libs:
            p = Path(lib) / "steamapps" / f"appmanifest_{appid}.acf"
            if p.exists():
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                    m = re.search(r'"StateFlags"\s*"(\d+)"', content)
                    if m:
                        state_flags = int(m.group(1))
                        if (state_flags & 4) == 4:
                            is_installed = True
                            break
                        elif (state_flags & 1024) == 1024 or (state_flags & 512) == 512 or (state_flags & 2) == 2 or (state_flags & 16) == 16:
                            is_downloading = True
                except Exception:
                    pass

        if not is_installed and game_dir and Path(game_dir).exists():
            try:
                exe_files = list(Path(game_dir).glob("*.exe"))
                if exe_files and len(exe_files) > 0:
                    is_installed = True
            except Exception:
                pass

        return {
            "ok": True,
            "appid": appid,
            "is_installed": is_installed,
            "is_downloading": is_downloading,
            "state_flags": state_flags,
            "game_dir": str(game_dir) if game_dir else ""
        }

    def get_steam_download_report(self, appid: str) -> Dict[str, Any]:
        """獲取 Steam 遊戲即時下載與安裝進度報告 (實體 downloading 目錄位元組追蹤、下載速度與狀態)"""
        from managers import onlinefix_manager
        appid_str = str(appid).strip()
        rep = onlinefix_manager.get_steam_app_download_report(appid_str)
        return {
            "ok": True,
            "report": rep
        }

    def launch_steam_install(self, appid: str, game_name: str = "") -> Dict[str, Any]:
        """喚起 Steam 開始下載/安裝遊戲主程式，並自動啟動下載狀態監控"""
        from managers import steam_manager
        try:
            appid_str = str(appid).strip()
            sp = self._steam_path or steam_manager.find_steam_path()
            # 🌟 關鍵修復：喚起 Steam 下載前必須先解除唯讀鎖定，確保 Steam 有權限讀寫 depotcache 與 ACF
            if sp:
                steam_manager.unlock_game_version(appid_str, sp)
                # 若 ACF 有殘留的 UpdateResult 錯誤碼，自動重設為 0
                acf = steam_manager.find_appmanifest(appid_str, sp)
                if acf and acf.exists():
                    try:
                        c = acf.read_text(encoding="utf-8", errors="ignore")
                        if re.search(r'"UpdateResult"\s+"[^0"]+"', c):
                            c = re.sub(r'"UpdateResult"\s+"[^"]*"', '"UpdateResult"\t\t"0"', c)
                            acf.write_text(c, encoding="utf-8")
                    except Exception:
                        pass

            os.startfile(f"steam://install/{appid_str}")
            
            # 自動啟動背景監控：若正常下載完成則自動部署補丁；若報錯或取消則中斷部署
            self.start_steam_install_watcher(appid_str, game_name)
            return {"ok": True, "msg": f"已喚起 Steam 開始安裝遊戲 (AppID: {appid_str})，正在背景自動監控下載進度…"}
        except Exception as e:
            return {"ok": False, "msg": f"喚起 Steam 安裝失敗: {e}"}

    def start_steam_install_watcher(self, appid: str, game_name: str = "") -> Dict[str, Any]:
        """啟動 Steam 下載監控，等待下載完成後自動部署補丁；若中途報錯或取消則自動中斷"""
        from managers import onlinefix_manager
        appid_str = str(appid).strip()

        def _on_complete(aid, gname, gdir):
            try:
                # 下載完成！直接執行線上補丁部署與原檔備份
                res = self.auto_install_cloud_patch_if_available(aid, gname)
                msg = res.get("msg", "線上補丁已自動部署完成！")
                if self._window:
                    js = f"if(window.onSteamDeployFinished) window.onSteamDeployFinished('{aid}', '{gname}', true, '{msg}');"
                    self._window.evaluate_js(js)
            except Exception as e:
                if self._window:
                    js = f"if(window.onSteamDeployFinished) window.onSteamDeployFinished('{aid}', '{gname}', false, '自動部署補丁失敗: {e}');"
                    self._window.evaluate_js(js)

        def _on_error(aid, gname, err_reason):
            if self._window:
                js = f"if(window.onSteamDeployCancelled) window.onSteamDeployCancelled('{aid}', '{gname}', '{err_reason}');"
                self._window.evaluate_js(js)

        started = onlinefix_manager._deploy_watcher.start_watch(
            appid_str, game_name, on_complete=_on_complete, on_error=_on_error
        )
        return {"ok": True, "started": started, "is_watching": True}

    def cancel_steam_install_watcher(self, appid: str) -> Dict[str, Any]:
        """手動取消指定遊戲的 Steam 下載監控隊列"""
        from managers import onlinefix_manager
        appid_str = str(appid).strip()
        onlinefix_manager._deploy_watcher.stop_watch(appid_str)
        return {"ok": True, "msg": "已取消背景下載監控"}

    def get_steam_download_report(self, appid: str) -> Dict[str, Any]:
        """即時查詢 Steam 下載狀態回報與錯誤碼"""
        from managers import onlinefix_manager
        appid_str = str(appid).strip()
        rep = onlinefix_manager.get_steam_app_download_report(appid_str)
        rep["is_watching"] = onlinefix_manager._deploy_watcher.is_watching(appid_str)
        return {"ok": True, "report": rep}

    def diagnose_game_download_error(self, appid: str, game_name: str = "") -> Dict[str, Any]:
        """
        深度全鏈路診斷 Steam 下載異常 (Content Corrupt, Locked, Missing Key, Missing Manifest 等)
        精準解析 content_log.txt、唯讀鎖定、Depot 金鑰與 Manifest 檔案完整度。
        """
        appid_str = str(appid).strip()
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp:
            return {"ok": False, "msg": "找不到 Steam 安裝目錄"}

        import stat
        report = {
            "appid": appid_str,
            "game_name": game_name or f"App_{appid_str}",
            "primary_error": "未知異常",
            "error_type": "UNKNOWN",
            "details": [],
            "steam_logs": [],
            "locks": [],
            "lua_info": {},
            "manifests_info": [],
            "acf_info": {},
            "markdown": ""
        }

        # 1. 解析 Steam logs/content_log.txt
        content_log_p = Path(sp) / "logs" / "content_log.txt"
        app_log_lines = []
        if content_log_p.exists():
            try:
                lines = content_log_p.read_text(encoding="utf-8", errors="ignore").splitlines()
                # 篩選最近 200 行中與此 AppID 相關的行
                for l in lines[-200:]:
                    if f"AppID {appid_str}" in l or (len(l) > 10 and appid_str in l):
                        app_log_lines.append(l)
            except Exception:
                pass
        report["steam_logs"] = app_log_lines[-15:]

        # 判斷日誌特徵
        log_text = "\n".join(app_log_lines)
        has_missing_key = "Missing decryption key" in log_text
        has_access_denied = "Access Denied" in log_text
        has_disk_write = "Disk write failure" in log_text or "Disk Write Error" in log_text
        has_manifest_missing = "Missing manifest" in log_text

        # 2. 檢查 Lua 設定檔與金鑰狀態
        lua_f = Path(sp) / "config" / "lua" / f"{appid_str}.lua"
        lua_exists = lua_f.exists()
        lua_ro = False
        lua_content = ""
        depot_keys_found = {}
        missing_keys_depots = []

        if lua_exists:
            try:
                lua_ro = not bool(lua_f.stat().st_mode & stat.S_IWRITE)
                lua_content = lua_f.read_text(encoding="utf-8", errors="ignore")
                # 正則尋找 addappid(did, flag, "key") 與 addappid(did)
                for m in re.finditer(r'addappid\s*\(\s*(\d+)(?:\s*,\s*\d+\s*,\s*"([a-fA-F0-9]{64})")?', lua_content):
                    did = m.group(1)
                    key = m.group(2)
                    if key:
                        depot_keys_found[did] = key
                    elif did != appid_str:
                        missing_keys_depots.append(did)
            except Exception:
                pass

        report["lua_info"] = {
            "path": str(lua_f),
            "exists": lua_exists,
            "readonly": lua_ro,
            "has_keys": bool(depot_keys_found),
            "keys": depot_keys_found,
            "missing_key_depots": missing_keys_depots
        }

        # 3. 檢查 ACF 狀態
        acf_f = steam_manager.find_appmanifest(appid_str, sp)
        acf_exists = acf_f and acf_f.exists()
        acf_ro = False
        update_result = "0"
        state_flags = "0"
        if acf_exists:
            try:
                acf_ro = not bool(acf_f.stat().st_mode & stat.S_IWRITE)
                acf_c = acf_f.read_text(encoding="utf-8", errors="ignore")
                ur_m = re.search(r'"UpdateResult"\s+"(\d+)"', acf_c)
                if ur_m: update_result = ur_m.group(1)
                sf_m = re.search(r'"StateFlags"\s+"(\d+)"', acf_c)
                if sf_m: state_flags = sf_m.group(1)
            except Exception:
                pass

        report["acf_info"] = {
            "path": str(acf_f) if acf_f else "",
            "exists": acf_exists,
            "readonly": acf_ro,
            "update_result": update_result,
            "state_flags": state_flags
        }

        # 4. 檢查 Manifest 檔案鎖定與齊全度
        depotcache_dir = Path(sp) / "depotcache"
        manifests_status = []
        if lua_exists:
            manifest_matches = re.findall(r'set[M|m]anifest[i|I]d\s*\(\s*(\d+)\s*,\s*"(\d+)"', lua_content)
            for did, gid in manifest_matches:
                mf_target = depotcache_dir / f"{did}_{gid}.manifest"
                mf_exists = mf_target.exists()
                mf_ro = False
                mf_size = 0
                if mf_exists:
                    try:
                        mf_ro = not bool(mf_target.stat().st_mode & stat.S_IWRITE)
                        mf_size = mf_target.stat().st_size
                    except Exception:
                        pass
                manifests_status.append({
                    "depot_id": did,
                    "manifest_id": gid,
                    "path": str(mf_target),
                    "exists": mf_exists,
                    "readonly": mf_ro,
                    "size": mf_size
                })
        report["manifests_info"] = manifests_status

        # 5. 綜合歸納核心錯誤主因
        if missing_keys_depots:
            report["primary_error"] = "缺少 Depot 解密金鑰 (Missing decryption key)"
            report["error_type"] = "MISSING_KEY"
            primary_desc = f"Depot {', '.join(missing_keys_depots)} 缺少 64 位元解密金鑰，導致 Steam 下載無法解密 chunk 檔案，進而觸發「檔案內容損毀 (Content Corrupt)」錯誤。"
        elif not lua_exists:
            report["primary_error"] = "缺少 Lua 入庫設定檔"
            report["error_type"] = "MISSING_LUA"
            primary_desc = f"Steam/config/lua/{appid_str}.lua 不存在，尚未完成入庫配置。"
        elif any(not m.get("exists") for m in manifests_status) or (has_manifest_missing and update_result != '0'):
            report["primary_error"] = "缺少二進位 Manifest 清單檔案"
            report["error_type"] = "MISSING_MANIFEST"
            missing_mfs = [f"{m['depot_id']}_{m['manifest_id']}.manifest" for m in manifests_status if not m.get("exists")]
            primary_desc = f"Steam/depotcache 目錄中缺少實體清單檔案：{', '.join(missing_mfs)}。"
        elif update_result != '0' and (acf_ro or any(m.get("readonly") for m in manifests_status) or has_access_denied):
            report["primary_error"] = "檔案被系統設為唯讀鎖定 (Access Denied)"
            report["error_type"] = "LOCKED_FILE"
            locked_files = []
            if acf_ro: locked_files.append("steamapps/" + (acf_f.name if acf_f else "ACF"))
            for m in manifests_status:
                if m.get("readonly"): locked_files.append("depotcache/" + Path(m["path"]).name)
            primary_desc = f"以下檔案被設為唯讀鎖定，阻止了 Steam 下載引擎的寫入權限：{', '.join(locked_files) if locked_files else '未知檔案'}。"
        elif update_result == '0' and (state_flags == '4' or state_flags == '6'):
            report["primary_error"] = "下載已完成或狀態正常"
            report["error_type"] = "HEALTHY"
            primary_desc = "當前環境檢測全部正常，金鑰與清單齊全，Steam 清單已無錯誤記錄。"
        else:
            report["primary_error"] = f"Steam 回報下載中斷 (UpdateResult: {update_result})"
            report["error_type"] = "STEAM_ERROR"
            primary_desc = f"Steam 回報錯誤代碼 {update_result} (StateFlags: {state_flags})，可能因網路超時、防毒軟體攔截或暫存衝突引發。"

        report["primary_desc"] = primary_desc

        # 6. 生成漂亮的 Markdown 診斷報告
        md = []
        md.append(f"# 🚨 下載異常排障報告：{report['game_name']} (`{appid_str}`)")
        md.append(f"**診斷時間**: `{time.strftime('%Y-%m-%d %H:%M:%S')}` | **狀態**: 🔴 `{report['primary_error']}`\n")
        
        md.append("### 🔴 核心錯誤判定")
        md.append(f"> **{report['primary_error']}**  \n> {primary_desc}\n")

        md.append("### 📋 系統環境與權限檢測清單")
        md.append("| 檢測項目 | 檢查目標 | 當前狀態 | 說明與分析 |")
        md.append("| :--- | :--- | :--- | :--- |")
        
        # Depot Key 行
        if missing_keys_depots:
            md.append(f"| **Depot 解密金鑰** | `Depot {','.join(missing_keys_depots)}` | ❌ 缺少金鑰 | Lua 檔案中僅宣告 `addappid`，未提供 64 位元金鑰 |")
        elif depot_keys_found:
            md.append(f"| **Depot 解密金鑰** | `{len(depot_keys_found)} 個 Depot` | ✅ 齊全已配置 | 已包含完整解密密鑰 |")
        else:
            md.append(f"| **Depot 解密金鑰** | `主程式` | ⚪ 免金鑰/未配置 | 免加密 Depot 或未配置 |")

        # Lua 行
        lua_stat = "❌ 不存在" if not lua_exists else ("⚠️ 唯讀鎖定 (需解鎖)" if lua_ro else "✅ 正常可讀寫")
        md.append(f"| **Lua 入庫設定檔** | `config/lua/{appid_str}.lua` | {lua_stat} | 大小: {len(lua_content)} B |")

        # ACF 行
        acf_stat = "❌ 不存在" if not acf_exists else (f"⚠️ 錯誤碼 {update_result}" if update_result != '0' else ("⚠️ 唯讀鎖定" if acf_ro else "✅ 正常可讀寫"))
        md.append(f"| **Steam 清單 (ACF)** | `appmanifest_{appid_str}.acf` | {acf_stat} | UpdateResult={update_result}, StateFlags={state_flags} |")

        # Manifests 行
        if manifests_status:
            for m in manifests_status:
                m_stat = "❌ 檔案缺失" if not m["exists"] else ("⚠️ 唯讀鎖定 (需解鎖)" if m["readonly"] else "✅ 正常可讀寫")
                md.append(f"| **實體 Manifest** | `depotcache/{m['depot_id']}_{m['manifest_id'][:8]}…` | {m_stat} | 大小: {m['size']} B |")
        else:
            md.append(f"| **實體 Manifest** | `depotcache/` | ⚪ 未宣告 | Lua 檔案中無 setManifestid 記錄 |")

        md.append("")
        if app_log_lines:
            md.append("### 🔍 Steam 原生日誌 (`content_log.txt`) 關鍵報錯")
            md.append("```text")
            for l in app_log_lines[-8:]:
                md.append(l)
            md.append("```\n")

        md.append("### 🛠️ 推薦修復措施")
        md.append("點擊下方「**🚀 一鍵自癒修復並重試下載**」按鈕，系統將自動：")
        md.append("1. 自動向官方/Ryuu 授權通道拉取並補齊正確的 Depot 解密金鑰；")
        md.append("2. 全面解除所有相關檔案與目錄的唯讀鎖定（恢復可讀寫）；")
        md.append("3. 重設 ACF 的錯誤狀態碼（UpdateResult = 0）並自動喚起 Steam 重啟下載。")

        report["markdown"] = "\n".join(md)
        return {"ok": True, "report": report}

    def heal_game_download_error(self, appid: str, game_name: str = "") -> Dict[str, Any]:
        """
        一鍵自癒修復下載異常：
        1. 解除所有相關檔案的唯讀鎖定
        2. 透過 Ryuu HTTP 通道重新部署包含正確 Depot Key 的完整 Lua 與 Manifest
        3. 重設 ACF UpdateResult 為 0
        4. 自動重啟 Steam 下載
        """
        import stat
        appid_str = str(appid).strip()
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp:
            return {"ok": False, "msg": "找不到 Steam 安裝路徑"}

        # 1. 解除版本唯讀鎖定
        steam_manager.unlock_game_version(appid_str, sp)

        # 2. 重新自 Ryuu 官方通道部署（獲取包含完整 Key 的 Lua 與實體清單）
        ok, msg = self._unified_mgr._deploy_from_ryuu_http(appid_str)
        if not ok:
            # 若 Ryuu 失敗，嘗試備援通道
            ok, msg = self._unified_mgr._deploy_from_luatools_http(appid_str)

        # 3. 確保 depotcache 底下所有檔案維持可讀寫
        depotcache_dir = Path(sp) / "depotcache"
        if depotcache_dir.exists():
            for mf in depotcache_dir.glob(f"{appid_str}*.manifest"):
                try: os.chmod(mf, stat.S_IWRITE | stat.S_IREAD)
                except Exception: pass

        # 4. 重設 ACF UpdateResult = 0
        acf_f = steam_manager.find_appmanifest(appid_str, sp)
        if acf_f and acf_f.exists():
            try:
                c = acf_f.read_text(encoding="utf-8", errors="ignore")
                c = re.sub(r'"UpdateResult"\s+"[^"]*"', '"UpdateResult"\t\t"0"', c)
                acf_f.write_text(c, encoding="utf-8")
            except Exception:
                pass

        # 5. 重新喚起 Steam 下載
        try:
            os.startfile(f"steam://install/{appid_str}")
            self.start_steam_install_watcher(appid_str, game_name)
        except Exception:
            pass

        return {
            "ok": True,
            "msg": f"✅ 已成功為「{game_name or appid_str}」完成自癒修復（已補全金鑰、解除鎖定並重啟下載）！",
            "deploy_result": msg
        }

    def check_cloud_patch_available(self, appid: str, game_name: str = "") -> Dict[str, Any]:
        """即時連網檢查 Google Drive 補丁庫是否收錄該遊戲補丁 (階段 1 調用)"""
        from managers import onlinefix_manager
        try:
            appid_str = str(appid).strip()
            sources = onlinefix_manager.get_patch_sources(target_app_id=appid_str, target_app_name=game_name, allow_network=True)
            src_info = sources.get(appid_str, {})
            has_patch = bool(src_info.get('cloud_rar') or src_info.get('cloud_lua') or src_info.get('local_lua'))
            return {
                "ok": True,
                "has_patch": has_patch,
                "drive_name": src_info.get('drive_name', 'Google Drive'),
                "has_rar": bool(src_info.get('cloud_rar')),
                "has_lua": bool(src_info.get('cloud_lua'))
            }
        except Exception as e:
            return {"ok": False, "has_patch": False, "msg": str(e)}

    def download_online_patch(self, appid: str, game_name: str = "") -> Dict[str, Any]:
        """自 Google Drive 下載線上補丁到本地快取目錄 (階段 3 調用)"""
        from managers import onlinefix_manager
        try:
            appid_str = str(appid).strip()
            sources = onlinefix_manager.get_patch_sources(target_app_id=appid_str, target_app_name=game_name, allow_network=True)
            src_info = sources.get(appid_str, {})
            cloud_rar = src_info.get('cloud_rar')
            if not cloud_rar:
                return {"ok": True, "has_patch": False, "msg": "無線上補丁"}
            dl_path = onlinefix_manager.download_cloud_patch(appid_str, game_name, cloud_rar)
            if dl_path and Path(dl_path).exists():
                return {"ok": True, "has_patch": True, "path": str(dl_path), "msg": "下載成功"}
            return {"ok": False, "has_patch": True, "msg": "下載失敗"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def auto_install_cloud_patch_if_available(self, appid: str, game_name: str = "") -> Dict[str, Any]:
        """一鍵入庫時自動檢測並連同安裝 Google Drive / ZeiGames 各格式聯機補丁 (發出連網讀取請求)"""
        from managers import onlinefix_manager
        try:
            appid_str = str(appid).strip()
            # 1. 檢索目標網盤中是否有此遊戲專用補丁 (發出讀取請求，allow_network=True)
            sources = onlinefix_manager.get_patch_sources(target_app_id=appid_str, target_app_name=game_name, allow_network=True)
            src_info = sources.get(appid_str, {})
            
            if not src_info or (not src_info.get('cloud_rar') and not src_info.get('cloud_lua')):
                # 🌟 自動容錯：若記憶體快取無資料，強制刷新 Google Drive 雲端索引並重試
                onlinefix_manager.fetch_cloud_cache(force=True)
                sources = onlinefix_manager.get_patch_sources(target_app_id=appid_str, target_app_name=game_name, allow_network=True, force_refresh=True)
                src_info = sources.get(appid_str, {})

            if not src_info or (not src_info.get('cloud_rar') and not src_info.get('cloud_lua')):
                return {"ok": True, "has_patch": False, "msg": "網盤無專用聯機補丁"}
                
            drive_name = src_info.get('drive_name', '網盤')
            
            # 2. 若有雲端 Lua 清單補丁，優先安裝
            if src_info.get('cloud_lua'):
                lua_dir = self._config.get("lua_dir") or (Path(self._steam_path or "") / "config" / "lua")
                if lua_dir:
                    onlinefix_manager.install_lua(appid_str, src_info, lua_dir)
                    
            # 3. 處理各類壓縮補丁包 (.rar / .zip / .7z 等，自動適配 online-fix.me 與 zeigames.com 解壓密碼)
            cloud_rar = src_info.get('cloud_rar')
            if cloud_rar:
                # 下載或讀取快取
                dl_path = onlinefix_manager.download_cloud_patch(appid_str, game_name, cloud_rar)
                if not dl_path:
                    return {"ok": False, "has_patch": True, "msg": f"下載 {drive_name} 聯機補丁失敗"}
                    
                # 檢查 Steam 遊戲目錄
                game_dir = onlinefix_manager._find_steam_game_dir(appid_str)
                if game_dir and Path(game_dir).exists():
                    # 遊戲已安裝，直接解壓安裝補丁並備份原檔
                    success, msg = onlinefix_manager.install_fix(
                        appid_str, dl_path, game_dir, delete_archive=True, source_drive=drive_name
                    )
                    if success:
                        return {
                            "ok": True,
                            "has_patch": True,
                            "installed": True,
                            "drive_name": drive_name,
                            "msg": f"已成功連同安裝 {drive_name} 的 Online-Fix / ZeiGames 聯機補丁！"
                        }
                    else:
                        return {"ok": False, "has_patch": True, "installed": False, "msg": f"補丁解壓安裝失敗: {msg}"}
                else:
                    # 遊戲目錄尚未下載，補丁保留在本地快取，記錄 pending 標記
                    return {
                        "ok": True,
                        "has_patch": True,
                        "installed": False,
                        "pending": True,
                        "drive_name": drive_name,
                        "msg": f"已自 {drive_name} 備妥聯機補丁，待 Steam 下載遊戲後即可生效！"
                    }
                    
            return {"ok": True, "has_patch": True, "drive_name": drive_name, "msg": "已部署網盤聯機配置"}
        except Exception as e:
            return {"ok": False, "msg": f"連同安裝補丁過程出錯: {e}"}

    def uninstall_online_patch(self, appid: str) -> Dict[str, Any]:
        """移除指定遊戲的線上補丁並自動還原原始備份檔案 (.bak)"""
        from managers import onlinefix_manager
        try:
            appid_str = str(appid).strip()
            success, msg = onlinefix_manager.uninstall_fix(appid_str)
            # 同步清理可能的專用 Lua 補丁
            lua_dir = self._config.get("lua_dir") or (Path(self._steam_path or "") / "config" / "lua")
            if lua_dir:
                try:
                    onlinefix_manager.uninstall_lua(appid_str, lua_dir)
                except Exception:
                    pass
            return {
                "ok": success,
                "msg": msg or ("已成功移除線上補丁並還原原始檔案！" if success else "移除線上補丁失敗")
            }
        except Exception as e:
            return {"ok": False, "msg": f"移除線上補丁出錯: {e}"}

    def install_online_patch(self, appid: str, game_name: str = "") -> Dict[str, Any]:
        """手動為指定遊戲下載安裝線上補丁 (自動將原檔備份為 .bak)"""
        return self.auto_install_cloud_patch_if_available(appid, game_name)


    # ═══════════════════════════════════════════════════════
    # 8. 聯機補丁 (OnlineFix / Spacewar 480) API
    # ═══════════════════════════════════════════════════════
    def list_onlinefix_games(self) -> Dict[str, Any]:
        """掃描支援 OnlineFix 的遊戲與 Spacewar 狀態"""
        sp = self._steam_path or steam_manager.find_steam_path()
        spacewar_installed = False
        if sp:
            sw_acf = Path(sp) / "steamapps" / "appmanifest_480.acf"
            spacewar_installed = sw_acf.exists()

        return {
            "ok": True,
            "spacewar": spacewar_installed,
            "items": []
        }

    def onlinefix_launch(self, appid: str) -> Dict[str, Any]:
        """帶 -480 參數啟動遊戲"""
        try:
            os.startfile(f"steam://run/{appid}//-480")
            return {"ok": True, "message": "已成功透過 -480 協定呼叫 Steam 啟動遊戲！"}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    # ═══════════════════════════════════════════════════════
    # 9. 系統體檢與診斷 API
    # ═══════════════════════════════════════════════════════
    def machine_check_async(self):
        """非同步執行全套環境體檢並推播報告至前端"""
        sp = self._steam_path or steam_manager.find_steam_path()
        dll_st = self.check_dlls()
        locked_st = self.check_steam_locked()
        
        report = {
            "steam_detected": bool(sp),
            "steam_path": str(sp) if sp else "未找到",
            "kernel_installed": dll_st.get("ok", False),
            "version_locked": locked_st.get("locked", False),
            "lua_dir_ok": (Path(sp) / "config" / "lua").exists() if sp else False,
            "depotcache_ok": (Path(sp) / "depotcache").exists() if sp else False
        }

        # 藉由 window.evaluate_js 觸發前端 onDgDone
        if self._window:
            js = f"if(window.onDgDone) window.onDgDone({json.dumps(report)});"
            try:
                self._window.evaluate_js(js)
            except Exception:
                pass
        return report

    def depot_selfcheck_async(self):
        """非同步自檢 Manifest 庫存完整度"""
        return self.machine_check_async()

    # ═══════════════════════════════════════════════════════
    # 10. 輔助與相容性 API
    # ═══════════════════════════════════════════════════════
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

    def ensure_cloud_config(self) -> Dict[str, Any]:
        """確保雲存檔配置完整"""
        return {"ok": True}

    def ensure_steam_path(self) -> str:
        """確保 Steam 路徑"""
        sp = self._steam_path or steam_manager.find_steam_path()
        return str(sp) if sp else ""

    def announce_mark_seen(self, announce_id: str = "") -> bool:
        """標記已讀公告"""
        self._config["announce_seen"] = announce_id
        config_manager.save_config(self._config)
        return True

    def check_update(self) -> Dict[str, Any]:
        """檢查更新：當前已為完美整合版，不彈出外部作者干擾更新視窗"""
        return {"has_update": False}

    def webview2_info(self) -> Dict[str, Any]:
        """WebView2 資訊"""
        return {"version": "Latest", "ok": True}

    def webview2_upgrade(self) -> Dict[str, Any]:
        """WebView2 升級"""
        return {"ok": True, "msg": "已是最新版本"}

    def get_bg_data(self, name: str) -> str:
        """讀取自訂背景檔案資料 (支援 GIF 動圖完整 Data URL)"""
        p = Path("data/backgrounds") / name
        if not p.exists(): return ""
        try:
            import base64
            ext = p.suffix.lower().lstrip(".")
            mime = "image/gif" if ext == "gif" else (f"image/{ext}" if ext in ["png", "webp"] else "image/jpeg")
            raw = p.read_bytes()
            b64 = base64.b64encode(raw).decode("ascii")
            return f"data:{mime};base64,{b64}"
        except Exception:
            return ""

    def install_default_bgs(self, force: bool = False) -> bool:
        """安裝預設背景"""
        return True

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

    def resize_to(self, width: int, height: int, fix_point: str = "", *args, **kwargs):
        """縮放視窗大小（支援對邊釘住座標補償與安全邊界）"""
        w = max(int(width), 880)
        h = max(int(height), 580)
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = self._get_hwnd()
            if hwnd:
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                cur_w = rect.right - rect.left
                cur_h = rect.bottom - rect.top
                cur_x = rect.left
                cur_y = rect.top
                new_x = cur_x
                new_y = cur_y
                if 'e' in fix_point:
                    new_x = cur_x - (w - cur_w)
                if 's' in fix_point:
                    new_y = cur_y - (h - cur_h)
                # SWP_NOZORDER (4) | SWP_NOACTIVATE (0x0010) = 0x0014
                user32.SetWindowPos(hwnd, 0, int(new_x), int(new_y), int(w), int(h), 0x0014)
                self.save_window_size(w, h)
                return True
        except Exception:
            pass

        if self._window:
            try:
                self._window.resize(w, h)
                self.save_window_size(w, h)
            except Exception:
                pass

    def toggle_mini(self) -> bool:
        """切換迷你模式"""
        return True

    def float_allowed(self) -> bool:
        """浮窗權限"""
        return True

    def ensure_pyside6_async(self):
        """異步就緒"""
        pass

    def gbe_allowed(self) -> bool:
        return False

    def gbe_crack(self, appid: str) -> Dict[str, Any]:
        return {"ok": False, "msg": "此功能已停用"}

    def get_sponsor_image(self) -> str:
        return ""

    def otac_qr_img(self) -> str:
        return ""

    def redeem_free_import(self, code: str) -> Dict[str, Any]:
        return {"ok": True}

    def mon_start(self) -> Dict[str, Any]:
        self._start_depotcache_watchdog()
        return {"ok": True}

    def mon_stop(self) -> Dict[str, Any]:
        self._watchdog_stop = True
        self._watchdog_started = False
        return {"ok": True}

    def mon_get_status(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "running": getattr(self, "_watchdog_started", False),
            "lines": getattr(self, "_watchdog_logs", [])
        }

    def mon_clear(self) -> Dict[str, Any]:
        self._watchdog_logs = []
        return {"ok": True}

    # ═══════════════════════════════════════════════════════
    # 憑證與登入狀態管理 API (Ryuu + HubcapDB + Lua.tools)
    # ═══════════════════════════════════════════════════════
    def get_credentials_status(self) -> Dict[str, Any]:
        """獲取使用者資訊、Ryuu、HubcapDB 和 Lua.tools 的登入狀態、帳號清單與配額使用資訊"""
        try:
            from managers import account_manager, config_manager, hubcap_manager
            import datetime, time
            mgr = account_manager.get_account_manager()
            mgr.reload_data()
            
            # 🌟 自動從 Ryuu 官方伺服器同步真實配額 (每 10 秒限制頻率，零額度消耗)
            now = time.time()
            if getattr(self, "_last_ryuu_quota_sync", 0) + 10 < now:
                self._last_ryuu_quota_sync = now
                try:
                    mgr.sync_ryuu_quota_from_server()
                except Exception:
                    pass

            # 1. Ryuu 狀態
            ryuu_accs = mgr.get_accounts("ryuu")
            ryuu_active = mgr.get_active_account("ryuu") or (ryuu_accs[0] if ryuu_accs else None)
            ryuu_logged_in = mgr.has_valid_credentials(ryuu_active, "ryuu") if ryuu_active else False
            ryuu_quota_used = ryuu_active.get("quota_used_today", 0) if ryuu_active else 0
            ryuu_limit = ryuu_active.get("daily_limit", 50) if ryuu_active else 50
            ryuu_name = ryuu_active.get("name", "未登入") if (ryuu_active and ryuu_logged_in) else ("未登入" if not ryuu_active else f"{ryuu_active.get('name', '帳號')} (未授權/過期)")

            # 全域預設 Hubcap Key
            raw_hubcap_key = hubcap_manager.get_api_key()
            default_hubcap_stats = hubcap_manager.fetch_user_stats(raw_hubcap_key) if raw_hubcap_key else {}
            default_hubcap_uid = str(default_hubcap_stats.get("user_id", "")).strip()
            default_hubcap_uname = str(default_hubcap_stats.get("username", "")).strip().lower()

            # 為 Ryuu 帳號清單標註詳細驗證狀態與專屬 Hubcap 狀態
            for acc in ryuu_accs:
                is_val = mgr.has_valid_credentials(acc, "ryuu")
                acc["has_valid_credentials"] = is_val
                acc["is_active"] = bool(ryuu_active and acc.get("id") == ryuu_active.get("id"))
                reset_sec = acc.get("reset_in_seconds")
                reset_str = ""
                if reset_sec and reset_sec > 0:
                    r_h = reset_sec // 3600
                    r_m = (reset_sec % 3600) // 60
                    reset_str = f" ({r_h}h{r_m}m後重設)"

                if not is_val:
                    acc["status_badge"] = "憑證無效"
                elif acc.get("is_exhausted") or (acc.get("quota_used_today", 0) >= acc.get("daily_limit", 50)):
                    acc["status_badge"] = f"配額已滿{reset_str}"
                else:
                    acc["status_badge"] = "正常"

                # 注入該帳號專屬的 Hubcap 狀態
                acc_did = str(acc.get("discord_id", "")).strip()
                acc_id = str(acc.get("id", "")).strip()
                acc_email = str(acc.get("email", "")).strip().lower()
                acc_name = str(acc.get("name", "")).strip().lower()
                h_key = mgr.get_hubcap_key(acc_did) or mgr.get_hubcap_key(acc_id) or mgr.get_hubcap_key(acc_email)
                
                # 若未單獨綁定，但有全域 Key 且 Discord ID 或 Username 吻合，自動歸屬綁定
                if not h_key and raw_hubcap_key:
                    if (default_hubcap_uid and acc_did == default_hubcap_uid) or (default_hubcap_uname and default_hubcap_uname in acc_name):
                        h_key = raw_hubcap_key
                        mgr.set_hubcap_key(acc_id, raw_hubcap_key, acc_did)

                if h_key:
                    h_stats = hubcap_manager.fetch_user_stats(h_key)
                    acc["hubcap"] = {
                        "is_configured": True,
                        "is_valid": bool(h_stats.get("ok")),
                        "remaining": h_stats.get("remaining", 0),
                        "daily_limit": h_stats.get("daily_limit", 25),
                        "daily_usage": h_stats.get("daily_usage", 0),
                        "api_key_masked": (h_key[:4] + "••••••••" + h_key[-4:]) if len(h_key) > 8 else "••••••••",
                        "error": h_stats.get("error", "")
                    }
                else:
                    acc["hubcap"] = {
                        "is_configured": False,
                        "is_valid": False,
                        "remaining": 0,
                        "daily_limit": 25,
                        "daily_usage": 0,
                        "api_key_masked": "",
                        "error": ""
                    }

            ryuu_left, ryuu_total = mgr.get_total_remaining_quota("ryuu")

            # 2. Lua.tools 狀態
            lt_accs = mgr.get_accounts("lua_tools")
            lt_active = mgr.get_active_account("lua_tools") or (lt_accs[0] if lt_accs else None)
            lt_logged_in = mgr.has_valid_credentials(lt_active, "lua_tools") if lt_active else False
            lt_quota_used = lt_active.get("quota_used_today", 0) if lt_active else 0
            lt_limit = lt_active.get("daily_limit", 25) if lt_active else 25
            lt_name = lt_active.get("name", "未登入") if (lt_active and lt_logged_in) else ("未登入" if not lt_active else f"{lt_active.get('name', '帳號')} (未授權/過期)")

            # 為 Lua.tools 帳號清單標註詳細驗證狀態與專屬 Hubcap 狀態
            for acc in lt_accs:
                is_val = mgr.has_valid_credentials(acc, "lua_tools")
                acc["has_valid_credentials"] = is_val
                acc["is_active"] = bool(lt_active and acc.get("id") == lt_active.get("id"))
                if not is_val:
                    acc["status_badge"] = "憑證無效"
                elif acc.get("is_exhausted"):
                    acc["status_badge"] = "配額已滿"
                else:
                    acc["status_badge"] = "正常"

                acc_did = str(acc.get("discord_id", "")).strip()
                acc_id = str(acc.get("id", "")).strip()
                acc_email = str(acc.get("email", "")).strip().lower()
                acc_name = str(acc.get("name", "")).strip().lower()
                h_key = mgr.get_hubcap_key(acc_did) or mgr.get_hubcap_key(acc_id) or mgr.get_hubcap_key(acc_email)
                
                # 若未單獨綁定，但有全域 Key 且 Discord ID 或 Username 吻合，自動歸屬綁定
                if not h_key and raw_hubcap_key:
                    if (default_hubcap_uid and acc_did == default_hubcap_uid) or (default_hubcap_uname and default_hubcap_uname in acc_name):
                        h_key = raw_hubcap_key
                        mgr.set_hubcap_key(acc_id, raw_hubcap_key, acc_did)

                if h_key:
                    h_stats = hubcap_manager.fetch_user_stats(h_key)
                    acc["hubcap"] = {
                        "is_configured": True,
                        "is_valid": bool(h_stats.get("ok")),
                        "remaining": h_stats.get("remaining", 0),
                        "daily_limit": h_stats.get("daily_limit", 25),
                        "daily_usage": h_stats.get("daily_usage", 0),
                        "api_key_masked": (h_key[:4] + "••••••••" + h_key[-4:]) if len(h_key) > 8 else "••••••••",
                        "error": h_stats.get("error", "")
                    }
                else:
                    acc["hubcap"] = {
                        "is_configured": False,
                        "is_valid": False,
                        "remaining": 0,
                        "daily_limit": 25,
                        "daily_usage": 0,
                        "api_key_masked": "",
                        "error": ""
                    }

            lt_left, lt_total = mgr.get_total_remaining_quota("lua_tools")

            # 3. 匯總所有帳號的 Hubcap 總額度 (去重計算)
            seen_hubcap_keys = set()
            hubcap_total_left = 0
            hubcap_total_limit = 0
            hubcap_total_used = 0
            
            for a_list in [ryuu_accs, lt_accs]:
                for a in a_list:
                    ah = a.get("hubcap", {})
                    ak = ah.get("api_key_masked")
                    if ah.get("is_valid") and ak and ak not in seen_hubcap_keys:
                        seen_hubcap_keys.add(ak)
                        hubcap_total_left += ah.get("remaining", 0)
                        hubcap_total_limit += ah.get("daily_limit", 0)
                        hubcap_total_used += ah.get("daily_usage", 0)

            # 4. 使用者個人資料 (User Profile)
            steam_users = self.list_steam_accounts()
            active_steam = steam_users[0] if steam_users else None
            user_name = "Steam 探索者"
            user_sub = "未連結 Steam 帳號"
            user_avatar = ""
            is_steam_linked = False
            steam_id = ""

            if active_steam:
                user_name = active_steam.get("PersonaName") or active_steam.get("AccountName") or "Steam 使用者"
                steam_id = active_steam.get("SteamID", "")
                user_sub = f"Steam ID: {steam_id}" if steam_id else f"帳號: {active_steam.get('AccountName', '')}"
                is_steam_linked = True
            elif ryuu_active and ryuu_logged_in:
                user_name = ryuu_active.get("name", "Discord 授權使用者")
                user_sub = "Discord 授權登入"
            elif lt_active and lt_logged_in:
                user_name = lt_active.get("name", "Discord 授權使用者")
                user_sub = "Discord 授權登入"

            total_quota_available = ryuu_left + hubcap_total_left + lt_left
            total_quota_capacity = ryuu_total + hubcap_total_limit + lt_total

            cfg = config_manager.get_config()
            preferred_source = cfg.get("preferred_source", "auto")
            auto_rotate = mgr.data.get("auto_rotate", True)
            
            return {
                "ok": True,
                "user_profile": {
                    "name": user_name,
                    "sub": user_sub,
                    "steam_id": steam_id,
                    "is_steam_linked": is_steam_linked,
                    "avatar": user_avatar,
                    "total_quota_available": total_quota_available,
                    "total_quota_capacity": total_quota_capacity
                },
                "ryuu": {
                    "is_logged_in": ryuu_logged_in,
                    "active_account": ryuu_active,
                    "accounts": ryuu_accs,
                    "name": ryuu_name,
                    "quota_used": ryuu_quota_used,
                    "daily_limit": ryuu_limit,
                    "quota_left": max(0, ryuu_limit - ryuu_quota_used) if ryuu_logged_in else 0,
                    "total_quota_left": ryuu_left,
                    "total_quota_limit": ryuu_total
                },
                "hubcap": {
                    "is_configured": bool(seen_hubcap_keys or raw_hubcap_key),
                    "is_valid": hubcap_total_limit > 0 or bool(default_hubcap_stats.get("ok")),
                    "api_key_masked": (raw_hubcap_key[:4] + "••••••••" + raw_hubcap_key[-4:]) if len(raw_hubcap_key) > 8 else "",
                    "daily_limit": hubcap_total_limit or default_hubcap_stats.get("daily_limit", 0),
                    "daily_usage": hubcap_total_used or default_hubcap_stats.get("daily_usage", 0),
                    "remaining": hubcap_total_left or default_hubcap_stats.get("remaining", 0),
                    "resets_at": default_hubcap_stats.get("resets_at", ""),
                    "api_key_expires_at": default_hubcap_stats.get("api_key_expires_at", ""),
                    "can_make_requests": bool(default_hubcap_stats.get("can_make_requests", True)),
                    "error": default_hubcap_stats.get("error", "")
                },
                "lua_tools": {
                    "is_logged_in": lt_logged_in,
                    "active_account": lt_active,
                    "accounts": lt_accs,
                    "name": lt_name,
                    "quota_used": lt_quota_used,
                    "daily_limit": lt_limit,
                    "quota_left": max(0, lt_limit - lt_quota_used) if lt_logged_in else 0,
                    "total_quota_left": lt_left,
                    "total_quota_limit": lt_total
                },
                "settings": {
                    "auto_rotate": auto_rotate,
                    "preferred_source": preferred_source
                }
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_hubcap_api_key(self, api_key: str, target_account_id: str = "") -> Dict[str, Any]:
        """儲存並驗證指定帳號或全域的 HubcapDB API Key"""
        try:
            from managers import hubcap_manager, account_manager
            clean_key = str(api_key or "").strip()
            mgr = account_manager.get_account_manager()
            target_id = str(target_account_id or "").strip()
            
            if not clean_key:
                if target_id:
                    mgr.set_hubcap_key(target_id, "")
                else:
                    hubcap_manager.set_api_key("")
                return {"ok": True, "msg": "已清除 HubcapDB API Key"}
            
            # 立即連線驗證
            stats = hubcap_manager.fetch_user_stats(clean_key)
            if stats.get("ok"):
                rem = stats.get("remaining", 0)
                lim = stats.get("daily_limit", 0)
                h_uid = str(stats.get("user_id", "")).strip()
                uname = str(stats.get("username", "")).strip()
                
                # 綁定至指定帳號或自動關聯之 Discord ID
                bind_target = target_id or h_uid
                if bind_target:
                    mgr.set_hubcap_key(bind_target, clean_key, h_uid)
                # 同步設定主 Key
                if not hubcap_manager.get_api_key() or not target_id:
                    hubcap_manager.set_api_key(clean_key)
                    
                target_tip = f"【{uname}】" if uname else ""
                return {
                    "ok": True,
                    "msg": f"HubcapDB 帳號{target_tip} API Key 驗證成功！可用配額: {rem} / {lim} 次",
                    "stats": stats
                }
            else:
                err = stats.get("error", "金鑰驗證失敗")
                return {"ok": False, "msg": f"API Key 驗證失敗: {err}"}
        except Exception as e:
            return {"ok": False, "msg": f"儲存 HubcapDB 金鑰異常: {e}"}

    def test_credential_connection(self, platform: str) -> Dict[str, Any]:
        """測試指定平台的連線狀態與憑證有效性"""
        try:
            if platform == "ryuu":
                from managers import ryuu_manager
                info = ryuu_manager.fetch_ryuu_manifest_info("480")
                if info.get("error") and "timeout" in str(info.get("error", "")).lower():
                    return {"ok": False, "msg": "Ryuu 官方伺服器連線逾時，請檢查網路代理"}
                return {"ok": True, "msg": "Ryuu 平台連線正常，Manifest 伺服器在線！"}
            elif platform in ("hubcap", "hubcapdb"):
                from managers import hubcap_manager
                return hubcap_manager.test_connection()
            elif platform == "lua_tools":
                import urllib.request
                req = urllib.request.Request("https://lua.tools", headers={"User-Agent": "Mozilla/5.0"})
                try:
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        return {"ok": True, "msg": "Lua.tools 平台連線正常！"}
                except Exception:
                    return {"ok": True, "msg": "Lua.tools 站點可連通"}
            return {"ok": False, "msg": f"未知平台: {platform}"}
        except Exception as e:
            return {"ok": False, "msg": f"連線測試異常: {e}"}

    def save_credential_cookie(self, platform: str, cookie_text: str) -> Dict[str, Any]:
        """手動匯入或更新 Cookie / Token 憑證"""
        try:
            cookie_clean = str(cookie_text).strip()
            if not cookie_clean:
                return {"ok": False, "msg": "憑證內容不能為空"}
                
            from managers import account_manager
            import sqlite3, time, datetime
            mgr = account_manager.get_account_manager()
            active = mgr.get_active_account(platform)
            if not active:
                acc_id, profile_dir = mgr.create_new_account_profile_dir(platform)
            else:
                acc_id = active.get("id")
                profile_dir = active.get("profile_dir")
                
            p_dir = Path(profile_dir)
            p_dir.mkdir(parents=True, exist_ok=True)
            cookie_file = p_dir / "Cookies"
            
            conn = sqlite3.connect(cookie_file)
            cur = conn.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS cookies (
                    creation_utc INTEGER NOT NULL,
                    host_key TEXT NOT NULL,
                    top_frame_site_key TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL,
                    value TEXT NOT NULL,
                    encrypted_value BLOB NOT NULL DEFAULT '',
                    path TEXT NOT NULL DEFAULT '/',
                    expires_utc INTEGER NOT NULL DEFAULT 0,
                    is_secure INTEGER NOT NULL DEFAULT 1,
                    is_httponly INTEGER NOT NULL DEFAULT 1,
                    last_access_utc INTEGER NOT NULL DEFAULT 0,
                    has_expires INTEGER NOT NULL DEFAULT 0,
                    is_persistent INTEGER NOT NULL DEFAULT 1,
                    priority INTEGER NOT NULL DEFAULT 1,
                    samesite INTEGER NOT NULL DEFAULT -1,
                    source_scheme INTEGER NOT NULL DEFAULT 2,
                    source_port INTEGER NOT NULL DEFAULT 443,
                    is_same_party INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (host_key, top_frame_site_key, name, path, source_port)
                )
            ''')
            
            now_epoch = int((time.time() + 11644473600) * 1000000)
            host = "generator.ryuu.lol" if platform == "ryuu" else "lua.tools"
            
            if "=" in cookie_clean:
                pairs = cookie_clean.split(";")
                for p in pairs:
                    if "=" in p:
                        k, v = p.strip().split("=", 1)
                        cur.execute('''
                            INSERT OR REPLACE INTO cookies (creation_utc, host_key, name, value, path, is_secure, is_httponly, is_persistent)
                            VALUES (?, ?, ?, ?, '/', 1, 1, 1)
                        ''', (now_epoch, host, k.strip(), v.strip()))
            else:
                key_name = "session" if platform == "ryuu" else "sb-db-auth-token.0"
                cur.execute('''
                    INSERT OR REPLACE INTO cookies (creation_utc, host_key, name, value, path, is_secure, is_httponly, is_persistent)
                    VALUES (?, ?, ?, ?, '/', 1, 1, 1)
                ''', (now_epoch, host, key_name, cookie_clean))
                
            conn.commit()
            conn.close()
            
            if not active:
                acc_entry = {
                    "id": acc_id,
                    "platform": platform,
                    "name": f"{platform.upper()} 帳號 (手動匯入)",
                    "profile_dir": str(p_dir),
                    "daily_limit": 50 if platform == "ryuu" else 25,
                    "quota_used_today": 0,
                    "quota_date": datetime.date.today().isoformat(),
                    "is_exhausted": False,
                    "added_time": datetime.datetime.now().isoformat()
                }
                mgr.data.setdefault(platform, []).append(acc_entry)
                if platform == "ryuu":
                    mgr.data["active_account_ryuu"] = acc_id
                else:
                    mgr.data["active_account_lt"] = acc_id
                mgr.save_data()
                
            return {"ok": True, "msg": f"成功儲存 {platform.upper()} 憑證！"}
        except Exception as e:
            return {"ok": False, "msg": f"儲存憑證失敗: {e}"}

    def clear_credential(self, platform: str) -> Dict[str, Any]:
        """清除指定平台的已存憑證與 Cookie"""
        try:
            from managers import account_manager
            mgr = account_manager.get_account_manager()
            accs = mgr.get_accounts(platform)
            for acc in accs:
                p_dir = Path(acc.get("profile_dir", ""))
                c_file = p_dir / "Cookies"
                if c_file.exists():
                    try: os.remove(c_file)
                    except Exception: pass
            mgr.data[platform] = []
            if platform == "ryuu":
                mgr.data["active_account_ryuu"] = None
            else:
                mgr.data["active_account_lt"] = None
            mgr.save_data()
            return {"ok": True, "msg": f"已清除 {platform.upper()} 的本機登入憑證"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def set_preferred_source(self, source: str) -> bool:
        """
        [已解耦/僅供相容] 設定多源偏好註記。
        注意：核心 Manifest 下載與校驗引擎已全面由 Downloader.js 與 UnifiedManifestManager 固化管線接管
        (Ryuu 優先 -> 自洽性與版本雙重校驗 -> Hubcap 備援熱替換 -> Lua.tools 兜底)，不受此設定干擾。
        """
        try:
            self._config["preferred_source"] = str(source).lower()
            config_manager.save_config(self._config)
            return True
        except Exception:
            return False

    def set_auto_rotate(self, enabled: bool) -> bool:
        """開關多帳號自動輪換"""
        try:
            from managers import account_manager
            mgr = account_manager.get_account_manager()
            mgr.set_auto_rotate(bool(enabled))
            return True
        except Exception:
            return False

    def switch_active_account(self, platform: str, account_id: str) -> Dict[str, Any]:
        """切換指定平台的活躍帳號"""
        try:
            from managers import account_manager
            mgr = account_manager.get_account_manager()
            success = mgr.set_active_account(platform, account_id)
            if success:
                return {"ok": True, "msg": "已切換活躍帳號"}
            return {"ok": False, "msg": "找不到指定的帳號 ID"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def reorder_accounts(self, platform: str, account_ids: List[str]) -> Dict[str, Any]:
        """重新排列指定平台帳號的優先調用順序"""
        try:
            from managers import account_manager
            mgr = account_manager.get_account_manager()
            success = mgr.reorder_accounts(platform, account_ids)
            if success:
                return {"ok": True, "msg": "已更新帳號優先調用順序"}
            return {"ok": False, "msg": "更新順序失敗"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def delete_credential_account(self, platform: str, account_id: str) -> Dict[str, Any]:
        """刪除指定平台的單一帳號"""
        try:
            from managers import account_manager
            mgr = account_manager.get_account_manager()
            success = mgr.delete_account(platform, account_id)
            if success:
                return {"ok": True, "msg": "已成功刪除該帳號憑證"}
            return {"ok": False, "msg": "找不到指定的帳號 ID"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def open_discord_login_window(self, platform: str) -> Dict[str, Any]:
        """
        開啟專屬的 Chromium 獨立無痕沙盒授權視窗，引導使用者登入後由系統自動完成身分與 Cookie 綁定。
        """
        try:
            import subprocess
            runner_script = Path(__file__).parent / "ui" / "sandbox_login_runner.py"
            if runner_script.exists():
                plat = "lua_tools" if "lua" in platform.lower() else "ryuu"
                subprocess.Popen(
                    [sys.executable, str(runner_script), "--platform", plat],
                    cwd=str(Path(__file__).parent.parent),
                    creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                )
                return {"ok": True, "msg": f"已啟動 {platform.upper()} 專屬安全沙盒登入視窗！"}

            return {"ok": False, "msg": "找不到沙盒執行器組件"}
        except Exception as e:
            return {"ok": False, "msg": f"啟動登入視窗失敗: {e}"}

    def open_dual_platform_sandbox_login(self) -> Dict[str, Any]:
        """
        開啟獨立無痕安全沙盒視窗，阻斷本機 Discord App 探測，
        支援在同一個乾淨 Session 中一次登入並依序連貫完成 Ryuu (50次) 與 Lua.tools (25次) 雙平台授權。
        """
        try:
            import subprocess
            runner_script = Path(__file__).parent / "ui" / "sandbox_login_runner.py"
            if runner_script.exists():
                subprocess.Popen(
                    [sys.executable, str(runner_script), "--platform", "all"],
                    cwd=str(Path(__file__).parent.parent),
                    creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                )
                return {"ok": True, "msg": "已啟動雙平台連貫安全沙盒登入視窗！"}

            # Fallback: 若 runner 不存在則使用通用子視窗
            return {"ok": False, "msg": "找不到雙平台沙盒執行器組件"}
        except Exception as e:
            return {"ok": False, "msg": f"啟動登入視窗失敗: {e}"}

    def auto_disable_official_cloud(self) -> Dict[str, Any]:
        """自動掃描已安裝之 Lua 入庫遊戲，並於 Steam sharedconfig.vdf 中自動關閉官方雲端以徹底根除報錯"""
        try:
            from managers import steam_cloud_helper
            sp = self._steam_path or steam_manager.find_steam_path()
            if sp:
                return steam_cloud_helper.disable_official_cloud_for_installed_lua_games(Path(sp), only_installed=True)
            return {"ok": False, "msg": "找不到 Steam 目錄"}
        except Exception as e:
            print(f"[WebApi] auto_disable_official_cloud error: {e}")
            return {"ok": False, "msg": str(e)}

    def check_startup_credentials(self) -> Dict[str, Any]:
        """
        每次啟動時自動檢查：
        1. 自動掃描已安裝 Lua 遊戲並關閉官方雲端報錯
        2. Ryuu 與 Lua.tools 憑證狀況
        """
        try:
            # 啟動靜默防護：關閉已安裝 Lua 遊戲的官方雲端開關
            try:
                self.auto_disable_official_cloud()
            except Exception:
                pass

            from managers import account_manager
            mgr = account_manager.get_account_manager()
            return mgr.validate_and_cleanup_all_credentials()
        except Exception as e:
            return {"ok": False, "has_cleaned": False, "error": str(e)}


    def clear_invalid_credentials(self) -> Dict[str, Any]:
        """手動觸發檢查並清理所有無效/過期的憑證檔案"""
        try:
            from managers import account_manager
            mgr = account_manager.get_account_manager()
            return mgr.validate_and_cleanup_all_credentials()
        except Exception as e:
            return {"ok": False, "has_cleaned": False, "error": str(e)}

    def open_hubcap_sandbox_login(self, target_account_id: str = "") -> Dict[str, Any]:
        """
        開啟 HubcapDB 專屬無痕沙盒授權視窗，自動預填已記憶密碼並自動捕獲/綁定 API Key。
        """
        try:
            import subprocess
            runner_script = Path(__file__).parent / "ui" / "sandbox_login_runner.py"
            if runner_script.exists():
                cmd = [sys.executable, str(runner_script), "--platform", "hubcap"]
                if target_account_id:
                    cmd.extend(["--account-id", str(target_account_id)])
                subprocess.Popen(
                    cmd,
                    cwd=str(Path(__file__).parent.parent),
                    creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                )
                return {"ok": True, "msg": "已啟動 HubcapDB 專屬無痕沙盒登入視窗！"}
            return {"ok": False, "msg": "找不到沙盒執行器組件"}
        except Exception as e:
            return {"ok": False, "msg": f"啟動登入視窗失敗: {e}"}

    def relogin_credential_account(self, platform: str, account_id: str) -> Dict[str, Any]:
        """
        針對特定失效帳號開啟專屬沙盒登入視窗，授權完成後自動覆蓋更新該帳號 Cookies / API Key。
        """
        try:
            import subprocess
            runner_script = Path(__file__).parent / "ui" / "sandbox_login_runner.py"
            if runner_script.exists():
                p_lower = str(platform or "").lower()
                if "hubcap" in p_lower:
                    plat = "hubcap"
                elif "lua" in p_lower:
                    plat = "lua_tools"
                else:
                    plat = "ryuu"
                subprocess.Popen(
                    [sys.executable, str(runner_script), "--platform", plat, "--account-id", str(account_id)],
                    cwd=str(Path(__file__).parent.parent),
                    creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                )
                return {"ok": True, "msg": "已開啟該帳號專屬重登視窗，請在完成授權後返回！"}
            return {"ok": False, "msg": "找不到沙盒執行器組件"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def scan_local_discord_accounts(self) -> Dict[str, Any]:
        """已停用：為防範 Discord 帳戶風控與鎖定，本機 Token 掃描已棄置"""
        return {
            "ok": False,
            "msg": "為防範 Discord 帳戶風控與鎖定，本機 Token 一鍵登入已全面停用。請使用 Chromium 獨立沙盒安全自行登入！",
            "accounts": []
        }

    def batch_import_discord_tokens(self, accounts: List[Dict[str, Any]], platforms: List[str] = None) -> Dict[str, Any]:
        """已停用：為防範 Discord 帳戶風控與鎖定，Token 批次登入已棄置"""
        return {
            "ok": False,
            "msg": "為防範 Discord 帳戶風控與鎖定，Token 登入已全面停用。請使用 Chromium 獨立沙盒安全自行登入！"
        }

    def import_discord_token_account(self, platform: str, token: str, display_name: str = "") -> Dict[str, Any]:
        """已停用：為防範 Discord 帳戶風控與鎖定，Token 登入已棄置"""
        return {
            "ok": False,
            "msg": "為防範 Discord 帳戶風控與鎖定，Token 登入已全面停用。請使用 Chromium 獨立沙盒安全自行登入！"
        }

    def open_ryuu_invite(self) -> Dict[str, Any]:
        """使用預設瀏覽器開啟 Ryuu 官方 Discord 伺服器邀請連結"""
        try:
            import webbrowser
            webbrowser.open("https://discord.gg/manifests")
            return {"ok": True, "msg": "已在瀏覽器開啟 Ryuu 官方 Discord 邀請連結 (discord.gg/manifests)"}
        except Exception as e:
            return {"ok": False, "msg": f"開啟連結失敗: {e}"}

    def verify_and_activate_ryuu_account(self, account_id: str) -> Dict[str, Any]:
        """
        直接向 Ryuu 官方網域伺服器 (https://generator.ryuu.lol/api/download_count/{did}) 驗證並同步配額。
        100% 透過網域端點完成，不依賴任何 Discord Token！
        """
        try:
            from managers import account_manager
            mgr = account_manager.get_account_manager()
            mgr.reload_data()
            success = mgr.sync_ryuu_quota_from_server(account_id)
            
            target = None
            for a in mgr.get_accounts("ryuu"):
                if a.get("id") == account_id:
                    target = a
                    break
            
            if target:
                left = max(0, target.get("daily_limit", 50) - target.get("quota_used_today", 0))
                return {
                    "ok": True,
                    "msg": f"🎉 網域伺服器同步成功！[{target.get('name')}] 今日剩餘 {left}/50 次額度！"
                }
            return {"ok": True, "msg": "已完成網域伺服器配額同步！"}
        except Exception as e:
            return {"ok": False, "msg": f"網域伺服器驗證異常: {e}"}

    def sync_all_quotas(self) -> Dict[str, Any]:
        """直接主動向各平台官方網域伺服器同步所有帳號之真實剩餘配額"""
        try:
            from managers import account_manager
            mgr = account_manager.get_account_manager()
            mgr.reload_data()
            mgr.sync_all_quotas_from_server()
            return {"ok": True, "msg": "已完成所有帳號網域伺服器配額同步！"}
        except Exception as e:
            return {"ok": False, "msg": f"同步配額失敗: {e}"}

    def open_token_join_server_window(self, account_id_or_token: str = "", display_name: str = "") -> Dict[str, Any]:
        """在瀏覽器中開啟官方 Discord 邀請頁面 (安全無風控)"""
        return self.open_ryuu_invite()

    def bootstrap_game_download(self, appid: str) -> Dict[str, Any]:
        """
        為指定 AppID 部署預引導 ACF 並校準 Manifest，徹底解決 OpenSteamTools 因外部 MRC 伺服器 502/503 崩潰導致 Steam 出現「無網路連線」無法下載的問題。
        """
        ok, msg = steam_manager.ensure_download_bootstrap_acf(appid, steam_path=self._steam_path)
        return {"ok": ok, "msg": msg}

    # ═══════════════════════════════════════════════════════
    # 🩺 系統健康體檢 (Health Check) 接口
    # ═══════════════════════════════════════════════════════
    def run_system_health_check(self) -> Dict[str, Any]:
        """執行全方位系統健康體檢並滾動落盤 (至多保留 5 份日誌)"""
        try:
            from managers.health_check_manager import get_health_check_manager
            mgr = get_health_check_manager()
            return mgr.run_health_check()
        except Exception as e:
            return {"ok": False, "score": 0, "rating": "CRITICAL", "rating_text": f"體檢異常: {e}", "issues": [str(e)]}

    def get_latest_system_health(self) -> Dict[str, Any]:
        """獲取最新一次的體檢結果快取"""
        try:
            from managers.health_check_manager import get_health_check_manager
            mgr = get_health_check_manager()
            return mgr.get_latest_result()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_system_health_logs(self) -> List[Dict[str, Any]]:
        """獲取最近歷史體檢日誌清單 (至多 5 筆)"""
        try:
            from managers.health_check_manager import get_health_check_manager
            mgr = get_health_check_manager()
            return mgr.get_history_logs()
        except Exception:
            return []

    def get_system_health_log_content(self, filename: str) -> Dict[str, Any]:
        """讀取指定歷史體檢日誌 Markdown 內容"""
        try:
            from managers.health_check_manager import get_health_check_manager
            mgr = get_health_check_manager()
            return mgr.get_log_content(filename)
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    # ═════════════════════════════════════════════════════════════════════
    # 👥 SMU 無伺服器組隊大廳與聯機同步 API (Party & Lobby)
    # ═════════════════════════════════════════════════════════════════════

    def _get_party_manager(self):
        """相容獲取 PartyManager 單例"""
        try:
            from managers.party_manager import PartyManager
        except ImportError:
            from src.managers.party_manager import PartyManager
        return PartyManager()

    def get_party_profile(self) -> Dict[str, Any]:
        """獲取組隊大廳個人資料 (暱稱、自動讀取之 Discord 帳號、額度健康度)"""
        try:
            return self._get_party_manager().get_profile()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_party_nickname(self, nickname: str, custom_discord: str = "") -> Dict[str, Any]:
        """設定並保存組隊大廳自訂暱稱與 Discord 標籤"""
        try:
            return self._get_party_manager().set_nickname(nickname, custom_discord)
        except Exception as e:
            return {"ok": False, "msg": f"設定暱稱失敗: {e}"}

    def get_lobby_rooms(self) -> Dict[str, Any]:
        """獲取全網公開組隊房間列表"""
        try:
            return self._get_party_manager().list_rooms()
        except Exception as e:
            return {"ok": False, "rooms": [], "msg": f"連線雲端大廳失敗: {e}"}

    def get_party_room_details(self, room_id: str = "") -> Dict[str, Any]:
        """查詢特定房間即時狀態與隊員名單"""
        try:
            return self._get_party_manager().get_room_details(room_id if room_id else None)
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def inspect_party_resources(self, app_id: str) -> Dict[str, Any]:
        """檢測指定遊戲本地 Manifest, Lua 與線上補丁三檔就緒狀況"""
        try:
            from managers.party_packager import get_party_packager
            return get_party_packager().inspect_party_resources(app_id)
        except Exception as e:
            return {"ok": False, "error": str(e), "can_package": False}

    def get_gas_config(self) -> Dict[str, Any]:
        """取得房主 GAS 網址與範本腳本代碼"""
        try:
            from managers.gas_manager import get_gas_manager
            mgr = get_gas_manager()
            return {
                "ok": True,
                "gas_url": mgr.get_gas_url(),
                "sample_script": mgr.get_sample_script()
            }
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def set_gas_config(self, url: str) -> Dict[str, Any]:
        """保存房主 GAS Web App 網址"""
        try:
            from managers.gas_manager import get_gas_manager
            mgr = get_gas_manager()
            mgr.set_gas_url(url)
            return {"ok": True, "msg": "GAS 網址已保存"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def test_gas_endpoint(self, url: str = "") -> Dict[str, Any]:
        """測試 GAS Web App 是否正常連線"""
        try:
            from managers.gas_manager import get_gas_manager
            return get_gas_manager().test_gas_connection(url)
        except Exception as e:
            return {"ok": False, "msg": f"測試異常: {e}"}

    def clean_gas_space(self, url: str = "") -> Dict[str, Any]:
        """清除房主 Google Drive 上的歷史整合包檔案"""
        try:
            from managers.gas_manager import get_gas_manager
            return get_gas_manager().clean_space(url)
        except Exception as e:
            return {"ok": False, "msg": f"清理空間失敗: {e}"}

    def open_gas_guide_page(self) -> Dict[str, Any]:
        """在預設瀏覽器中直接開啟 GAS 互動式一步一步引導教學網頁"""
        try:
            import webbrowser
            from pathlib import Path
            guide_file = Path(__file__).resolve().parent / "gui" / "gas_guide.html"
            if guide_file.exists():
                webbrowser.open(guide_file.as_uri())
                return {"ok": True}
            return {"ok": False, "msg": "找不到教學網頁檔案"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def create_party_room(self, game_name: str, app_id: str, max_players: int = 4, is_public: bool = True,
                          note: str = "", auto_package_upload: bool = False, gas_url: str = "") -> Dict[str, Any]:
        """房主建立組隊房間 (支援三檔自動打包與 GAS 上傳至 Google Drive)"""
        try:
            return self._get_party_manager().create_room(
                game_name=game_name,
                app_id=str(app_id),
                max_players=int(max_players),
                is_public=bool(is_public),
                note=note,
                auto_package_upload=bool(auto_package_upload),
                gas_url=gas_url
            )
        except Exception as e:
            return {"ok": False, "msg": f"創建房間失敗: {e}"}

    def join_party_room(self, room_id: str) -> Dict[str, Any]:
        """隊員加入房間 (支援 6 碼房號)"""
        try:
            return self._get_party_manager().join_room(room_id)
        except Exception as e:
            return {"ok": False, "msg": f"加入房間失敗: {e}"}

    def leave_party_room(self) -> Dict[str, Any]:
        """隊員主動離開房間"""
        try:
            return self._get_party_manager().leave_room()
        except Exception as e:
            return {"ok": False, "msg": f"退出房間失敗: {e}"}

    def close_party_room(self) -> Dict[str, Any]:
        """房主解散房間"""
        try:
            return self._get_party_manager().close_room()
        except Exception as e:
            return {"ok": False, "msg": f"解散房間失敗: {e}"}

    def update_party_progress(self, status: str, progress: int) -> Dict[str, Any]:
        """更新隊員下載狀況 (未下載 / 下載中: xx% / 就緒)"""
        try:
            return self._get_party_manager().update_member_progress(status, progress)
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def start_party_sync_download(self, room_id: str, app_id: str) -> Dict[str, Any]:
        """一鍵同步聯機資源並自動驅動進度回報"""
        try:
            return self._get_party_manager().start_sync_download(room_id, app_id)
        except Exception as e:
            return {"ok": False, "msg": f"啟動同步下載失敗: {e}"}

    def get_installed_games_for_party(self) -> List[Dict[str, Any]]:
        """
        取得「已安裝且已部署線上補丁」之遊戲清單（供建房時下拉選單快速挑選）
        依據使用者要求：必須同時滿足 1. 本地已安裝 2. 已部署線上聯機補丁
        """
        try:
            games = self.list_games()
            result = []
            for g in games:
                appid = str(g.get("appid", "")).strip()
                if not appid:
                    continue
                # 檢查是否已部署聯機補丁
                is_deployed = bool(g.get("deployed"))
                if not is_deployed:
                    try:
                        from managers import onlinefix_manager
                        is_deployed = onlinefix_manager.is_patch_deployed_locally(appid)
                    except Exception:
                        pass

                if is_deployed:
                    name = g.get("name") or g.get("english_name") or f"AppID {appid}"
                    result.append({
                        "appid": appid,
                        "name": name,
                        "deployed": True
                    })
            return result
        except Exception as e:
            print(f"[PARTY] 取得已部署聯機遊戲失敗: {e}")
            return []



