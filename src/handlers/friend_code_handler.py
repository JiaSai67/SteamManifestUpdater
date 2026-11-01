# -*- coding: utf-8 -*-
"""
FriendCodeHandler - 友邀代碼 (Friend Invite Code) 前端 API 處理模組
"""

import ctypes
from typing import Dict, Any, List
from managers.friend_code_manager import get_friend_code_manager
from managers.discord_storage import get_discord_storage
from managers.party_packager import get_party_packager


class FriendCodeHandler:
    def get_friend_code_init_data(self) -> Dict[str, Any]:
        """一次性取得友邀代碼頁面初始化所需資料：已記憶 Webhook、可打包遊戲清單、歷史紀錄與進行中任務狀態"""
        try:
            mgr = get_friend_code_manager()
            webhook_url = get_discord_storage().get_custom_webhook_url()
            games = self.get_ready_games_for_friend_code()
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

    def get_ready_games_for_friend_code(self) -> List[Dict[str, Any]]:
        """
        取得本地已就緒可供打包分享之遊戲清單：
        同時涵蓋「已部署線上聯機補丁」或「本地三檔 (Manifest + Lua + 補丁包) 皆齊全」之遊戲
        """
        try:
            games = self.list_games()
            packager = get_party_packager()
            seen = set()
            result = []
            for g in games:
                appid = str(g.get("appid", "")).strip()
                if not appid or appid in seen:
                    continue
                is_ready = bool(g.get("deployed"))
                if not is_ready:
                    try:
                        from managers import onlinefix_manager
                        is_ready = onlinefix_manager.is_patch_deployed_locally(appid)
                    except Exception:
                        pass
                if not is_ready:
                    try:
                        insp = packager.inspect_party_resources(appid)
                        is_ready = bool(insp.get("all_ready"))
                    except Exception:
                        pass

                if is_ready:
                    seen.add(appid)
                    name = g.get("name") or g.get("english_name") or f"AppID {appid}"
                    result.append({
                        "appid": appid,
                        "name": name,
                        "deployed": True,
                    })
            return result
        except Exception as e:
            print(f"[FriendCode] 掃描可打包遊戲清單異常: {e}")
            return []

    def start_generate_friend_code(self, app_id: str, game_name: str = "", discord_webhook: str = "") -> Dict[str, Any]:
        """發起打包並上傳至 Discord Webhook，加密生成 52 碼中英混合友邀代碼"""
        try:
            return get_friend_code_manager().start_generate_friend_code(
                app_id=str(app_id),
                game_name=str(game_name or ""),
                discord_webhook=str(discord_webhook or "")
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

