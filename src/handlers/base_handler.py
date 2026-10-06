# -*- coding: utf-8 -*-
"""
SMU Base Handler
全域基礎共用處理器，包含視窗生命週期、基礎通訊與共通狀態
"""
import os
import sys
import json
import time
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
import concurrent.futures
import threading

from managers import config_manager
from managers import steam_manager
from managers import unified_manifest_manager


class BaseHandler:
    """全域基礎屬性與視窗/事件控制處理器"""

    def __init__(self):
        self._window = None
        self._config = config_manager.get_config()
        self._steam_path = self._config.get("steam_path") or steam_manager.find_steam_path()
        if self._steam_path:
            self._config["steam_path"] = self._steam_path
            config_manager.save_config(self._config)

        self._unified_mgr = unified_manifest_manager.UnifiedManifestManager.get_instance()
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=6)
        self._is_checking_updates = False
        self._active_watchers = {}

        # 啟動 depotcache 看門狗守護
        self._start_depotcache_watchdog()

    def set_window(self, window):
        """綁定 PyWebView 視窗實例"""
        self._window = window

    def _push_js_event(self, event_name: str, data: Any = None):
        """安全向前端拋送 JavaScript 自訂事件"""
        if not self._window:
            return
        try:
            payload = json.dumps(data, ensure_ascii=False) if data is not None else "null"
            js = f"""
            (function() {{
                try {{
                    const ev = new CustomEvent({json.dumps(event_name)}, {{ detail: {payload} }});
                    window.dispatchEvent(ev);
                }} catch(e) {{
                    console.error('[WebAPI Push Error]', e);
                }}
            }})();
            """
            self._window.evaluate_js(js)
        except Exception as e:
            print(f"[BaseHandler._push_js_event] 拋送事件 {event_name} 失敗: {e}")

    def _get_hwnd(self):
        """安全獲取當前視窗的原生 Win32 HWND 句柄"""
        if not self._window:
            return None
        try:
            import ctypes
            user32 = ctypes.windll.user32
            # 優先從 webview 屬性讀取
            if hasattr(self._window, 'gui') and hasattr(self._window.gui, 'hwnd'):
                return self._window.gui.hwnd
            # 次選透過目前活躍的進程與視窗標題尋找
            pid = os.getpid()
            found_hwnd = [None]
            def enum_cb(h, _):
                lp_pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(h, ctypes.byref(lp_pid))
                if lp_pid.value == pid and user32.IsWindowVisible(h):
                    found_hwnd[0] = h
                    return False
                return True
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
            return found_hwnd[0]
        except Exception:
            return None

    def _start_depotcache_watchdog(self):
        """啟動 depotcache 目錄守護守望線程，即時確保關鍵目錄健康存在"""
        def _loop():
            while True:
                time.sleep(30)
                try:
                    sp = self._steam_path or steam_manager.find_steam_path()
                    if sp:
                        dc = Path(sp) / "depotcache"
                        if not dc.exists():
                            dc.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
        t = threading.Thread(target=_loop, daemon=True, name="depotcache_watchdog")
        t.start()

    # 視窗基本控制 (供前端 Titlebar 統一調用)
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
                user32.ShowWindow(hwnd, 6)
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
                    user32.ShowWindow(hwnd, 9)
                else:
                    user32.ShowWindow(hwnd, 3)
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
                user32.ShowWindow(hwnd, 9)
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

    def move_by(self, dx: int, dy: int) -> bool:
        """平移視窗"""
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = self._get_hwnd()
            if hwnd:
                if user32.IsZoomed(hwnd):
                    user32.ShowWindow(hwnd, 9)
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
                user32.SetWindowPos(hwnd, 0, int(new_x), int(new_y), 0, 0, 0x0015)
                return True
        except Exception:
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
        """觸發作業系統原生視窗拖曳 (Win32 SC_DRAGMOVE)"""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = self._get_hwnd()
            if hwnd:
                user32.ReleaseCapture()
                user32.PostMessageW(hwnd, 0x0112, 0xF012, 0)
                return True
        except Exception as e:
            print(f"[BaseHandler] drag_window error: {e}")
        return False

    def start_resize(self, side: str) -> bool:
        """觸發作業系統原生無邊框視窗邊緣縮放"""
        side_map = {
            "w": 0xF001, "e": 0xF002, "n": 0xF003, "nw": 0xF004,
            "ne": 0xF005, "s": 0xF006, "sw": 0xF007, "se": 0xF008
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
            print(f"[BaseHandler] start_resize error: {e}")
        return False

    def save_window_size(self, width: int = 0, height: int = 0, *args, **kwargs) -> bool:
        """儲存視窗自訂大小"""
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

    def open_external_url(self, url: str) -> bool:
        """使用預設瀏覽器打開外部 URL (相容 alias)"""
        return self.open_url(url)

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
