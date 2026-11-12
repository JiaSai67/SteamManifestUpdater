# -*- coding: utf-8 -*-
"""
FriendCodeHandler - 友邀代碼 (Friend Invite Code) 前端 API 處理模組
"""

import re
import ctypes
from pathlib import Path
from typing import Dict, Any, List
from managers import steam_manager
from managers import onlinefix_manager
from managers.friend_code_manager import get_friend_code_manager
from managers.discord_storage import get_discord_storage


class FriendCodeHandler:
    def get_friend_code_init_data(self) -> Dict[str, Any]:
        """一次性取得友邀代碼頁面初始化所需資料：已記憶 Webhook、可打包遊戲清單、歷史紀錄與進行中任務狀態"""
        try:
            mgr = get_friend_code_manager()
            webhook_url = get_discord_storage().get_custom_webhook_url()
            games = self.get_ready_games_for_friend_code(pack_mode="all")
            return {
                "ok": True,
                "webhook_url": webhook_url,
                "games": games,
                "history": mgr.get_public_history(),
                "host_progress": mgr.get_host_progress(),
                "install_progress": mgr.get_install_progress(),
            }
        except Exception as e:
            return {"ok": False, "msg": f"初始化友邀代碼資料失敗: {e}"}

    def get_ready_games_for_friend_code(self, pack_mode: str = "all") -> List[Dict[str, Any]]:
        """
        極速批次掃描本地可供「友邀代碼」打包分享之遊戲清單（與線上組隊完全獨立）：
        - 支援兩種打包方法：
          1. with_patch (含線上補丁): 具備 Manifest + Lua + 線上聯機補丁
          2. lua_manifest (無補丁純入庫): 具備 Lua + Manifest 即可打包
        - 採用 O(1) 記憶體集合索引 depotcache 與 Lua，即使本地有數百款遊戲亦能毫秒級載入。
        """
        try:
            games = self.list_games()
            sp = getattr(self, "_steam_path", None) or steam_manager.find_steam_path()
            manifest_names = set()
            manifest_depots = set()
            lua_dirs: List[Path] = []

            if sp:
                sp_path = Path(sp)
                lua_dirs = [
                    sp_path / "config" / "stplug-in",
                    sp_path / "config" / "lua",
                    sp_path / "config" / "stplugins",
                ]
                depot_caches = [sp_path / "depotcache", sp_path / "config" / "depotcache"]
                try:
                    for lib in steam_manager.get_steam_libraries(sp):
                        dc = lib / "depotcache"
                        if dc not in depot_caches:
                            depot_caches.append(dc)
                except Exception:
                    pass

                for dc in depot_caches:
                    if dc.exists():
                        try:
                            for mf in dc.glob("*.manifest"):
                                manifest_names.add(mf.name)
                                if "_" in mf.name:
                                    manifest_depots.add(mf.name.split("_", 1)[0])
                        except Exception:
                            pass

            mf_pattern = re.compile(r'set[M|m]anifest[i|I]d\s*\(\s*(\d+)\s*,\s*["\'](\d+)["\']\s*\)')
            seen = set()
            result = []
            norm_filter = str(pack_mode or "all").strip()

            for g in games:
                appid = str(g.get("appid", "")).strip()
                if not appid or appid in seen:
                    continue

                # 1. 檢查是否具備實體 Manifest 檔案 (O(1) 集合比對)
                has_manifest = appid in manifest_depots
                if not has_manifest and lua_dirs:
                    for ld in lua_dirs:
                        lf = ld / f"{appid}.lua"
                        if lf.exists():
                            try:
                                txt = lf.read_text(encoding="utf-8", errors="ignore")
                                for m in mf_pattern.finditer(txt):
                                    d_id, m_id = m.group(1), m.group(2)
                                    if f"{d_id}_{m_id}.manifest" in manifest_names or d_id in manifest_depots:
                                        has_manifest = True
                                        break
                            except Exception:
                                pass
                            break

                # 2. 檢查是否具備線上聯機補丁 (已部署至遊戲目錄 或 本地快取有補丁壓縮包)
                has_patch = bool(g.get("deployed"))
                if not has_patch:
                    try:
                        app_cache_dir = onlinefix_manager.get_app_cache_dir(appid)
                        if app_cache_dir and Path(app_cache_dir).exists():
                            for f in Path(app_cache_dir).iterdir():
                                if f.is_file() and f.suffix.lower() in (".rar", ".zip", ".7z"):
                                    has_patch = True
                                    break
                    except Exception:
                        pass

                if not has_manifest and not has_patch:
                    continue

                if norm_filter == "with_patch" and not (has_manifest and has_patch):
                    continue
                if norm_filter == "lua_manifest" and not has_manifest:
                    continue

                seen.add(appid)
                name = g.get("name") or g.get("english_name") or f"AppID {appid}"
                eng_name = g.get("english_name") or g.get("name_en") or ""
                result.append({
                    "appid": appid,
                    "name": name,
                    "english_name": eng_name,
                    "has_manifest": bool(has_manifest),
                    "has_lua": True,
                    "has_patch": bool(has_patch),
                    "deployed": bool(has_patch),
                })

            # 排序：優先顯示具備線上補丁的遊戲，其次依名稱排序
            result.sort(key=lambda x: (0 if x.get("has_patch") else 1, str(x.get("name", "")).lower()))
            return result
        except Exception as e:
            print(f"[FriendCode] 掃描可打包遊戲清單異常: {e}")
            return []

    def inspect_friend_code_game(self, app_id: str, pack_mode: str = "with_patch") -> Dict[str, Any]:
        """友邀代碼專屬：檢測指定遊戲在當前打包模式 (with_patch / lua_manifest) 下的資源就緒狀態"""
        try:
            res = get_friend_code_manager().inspect_friend_code_resources(
                app_id=str(app_id or ""),
                pack_mode=str(pack_mode or "with_patch")
            )
            return {"ok": True, "data": res}
        except Exception as e:
            return {"ok": False, "msg": f"檢測友邀代碼資源失敗: {e}"}

    def start_generate_friend_code(
        self,
        app_id: str,
        game_name: str = "",
        discord_webhook: str = "",
        pack_mode: str = "with_patch"
    ) -> Dict[str, Any]:
        """發起打包並上傳至 Discord Webhook，加密生成 97 碼純英數友邀代碼"""
        try:
            return get_friend_code_manager().start_generate_friend_code(
                app_id=str(app_id),
                game_name=str(game_name or ""),
                discord_webhook=str(discord_webhook or ""),
                pack_mode=str(pack_mode or "with_patch")
            )
        except Exception as e:
            return {"ok": False, "msg": f"啟動打包失敗: {e}"}

    def get_friend_code_host_progress(self) -> Dict[str, Any]:
        """輪詢發起方打包上傳進度與生成結果"""
        try:
            return {"ok": True, "data": get_friend_code_manager().get_host_progress()}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def get_friend_code_history(self) -> Dict[str, Any]:
        """取得本地已發布之友邀代碼歷史清單"""
        try:
            return {"ok": True, "history": get_friend_code_manager().get_public_history()}
        except Exception as e:
            return {"ok": False, "history": [], "msg": str(e)}

    def revoke_friend_code_item(self, item_id: str) -> Dict[str, Any]:
        """撤銷友邀代碼並同步刪除 Discord 頻道上之整合包檔案"""
        try:
            return get_friend_code_manager().revoke_history_item(str(item_id))
        except Exception as e:
            return {"ok": False, "msg": f"撤銷失敗: {e}"}

    def preview_friend_code(self, raw_code: str, fetch_remote: bool = False) -> Dict[str, Any]:
        """本地離線解密核驗友邀代碼 (可選同步預覽雲端遊戲名稱與大小)"""
        try:
            return get_friend_code_manager().preview_friend_code(str(raw_code or ""), fetch_remote=bool(fetch_remote))
        except Exception as e:
            return {"ok": False, "msg": f"解析失敗: {e}"}

    def start_redeem_friend_code(self, raw_code: str) -> Dict[str, Any]:
        """接收方貼上代碼後啟動全自動解密、下載與安裝流程"""
        try:
            return get_friend_code_manager().start_redeem_install(str(raw_code or ""))
        except Exception as e:
            return {"ok": False, "msg": f"啟動自動安裝失敗: {e}"}

    def get_friend_code_install_progress(self) -> Dict[str, Any]:
        """輪詢接收方五階段自動下載與安裝進度"""
        try:
            return {"ok": True, "data": get_friend_code_manager().get_install_progress()}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def cancel_friend_code_install(self) -> Dict[str, Any]:
        """取消進行中之友邀代碼下載安裝任務"""
        try:
            return get_friend_code_manager().cancel_redeem_install()
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def read_clipboard_text(self) -> Dict[str, Any]:
        """原生讀取 Windows 系統剪貼簿純文字 (免除 WebView2 file:// 剪貼簿權限彈窗限制)"""
        CF_UNICODETEXT = 13
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        user32.OpenClipboard.restype = ctypes.c_int
        user32.GetClipboardData.argtypes = [ctypes.c_uint]
        user32.GetClipboardData.restype = ctypes.c_void_p
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = ctypes.c_int
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.restype = ctypes.c_int

        if not user32.OpenClipboard(None):
            return {"ok": False, "text": "", "msg": "無法存取系統剪貼簿"}
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return {"ok": True, "text": ""}
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return {"ok": True, "text": ""}
            try:
                text = ctypes.wstring_at(ptr)
                return {"ok": True, "text": text or ""}
            finally:
                kernel32.GlobalUnlock(handle)
        except Exception as e:
            return {"ok": False, "text": "", "msg": str(e)}
        finally:
            user32.CloseClipboard()

    def write_clipboard_text(self, text: str) -> Dict[str, Any]:
        """原生寫入 Windows 系統剪貼簿純文字"""
        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        user32.OpenClipboard.restype = ctypes.c_int
        user32.EmptyClipboard.argtypes = []
        user32.EmptyClipboard.restype = ctypes.c_int
        user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        user32.SetClipboardData.restype = ctypes.c_void_p
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = ctypes.c_int
        kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.restype = ctypes.c_int

        s = str(text or "")
        raw = s.encode("utf-16-le") + b"\x00\x00"

        if not user32.OpenClipboard(None):
            return {"ok": False, "msg": "無法開啟系統剪貼簿"}
        try:
            user32.EmptyClipboard()
            h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(raw))
            if not h_mem:
                return {"ok": False, "msg": "配置剪貼簿記憶體失敗"}
            ptr = kernel32.GlobalLock(h_mem)
            if not ptr:
                return {"ok": False, "msg": "鎖定剪貼簿記憶體失敗"}
            ctypes.memmove(ptr, raw, len(raw))
            kernel32.GlobalUnlock(h_mem)
            user32.SetClipboardData(CF_UNICODETEXT, h_mem)
            return {"ok": True, "msg": "已複製至剪貼簿"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}
        finally:
            user32.CloseClipboard()

