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

class PartyHandler:
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

    def start_discord_oauth(self) -> Dict[str, Any]:
        """啟動 Discord OAuth2 官方授權流程 (本地 18888 端口秒級回調)"""
        try:
            return self._get_party_manager().start_discord_oauth()
        except Exception as e:
            return {"ok": False, "msg": f"啟動 Discord 驗證失敗: {e}"}

    def get_lobby_rooms(self) -> Dict[str, Any]:
        """獲取全網公開組隊房間列表"""
        try:
            return self._get_party_manager().list_rooms()
        except Exception as e:
            return {"ok": False, "rooms": [], "msg": f"連線雲端大廳失敗: {e}"}

    def get_party_room_details(self, room_id: str = "", scope: str = "all") -> Dict[str, Any]:
        """
        查詢特定房間狀態 (支援針對性投影 scope: 'all' | 'info' | 'download' | 'members' | 'quota')
        """
        try:
            return self._get_party_manager().get_room_details(room_id if room_id else None, scope=scope)
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def get_party_room_basic_info(self, room_id: str = "") -> Dict[str, Any]:
        """針對性抓取：只抓房間資訊 (房號、遊戲、房主、人數、規則)，完全排除下載資訊"""
        try:
            return self._get_party_manager().get_room_basic_info(room_id if room_id else None)
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def get_party_room_download_info(self, room_id: str = "") -> Dict[str, Any]:
        """針對性抓取：只抓下載資訊 (下載鏈結、解壓密碼)，於隊員準備下載時精準單次獲取"""
        try:
            return self._get_party_manager().get_room_download_info(room_id if room_id else None)
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def get_party_room_members_info(self, room_id: str = "") -> Dict[str, Any]:
        """針對性抓取：只抓成員清單與心跳狀態 (適合隊員房內輪詢，流量節省 80%)"""
        try:
            return self._get_party_manager().get_room_members_info(room_id if room_id else None)
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def get_party_quota_info(self) -> Dict[str, Any]:
        """針對性抓取：只抓額度資訊與 Egress 監控數據 (受 5 分鐘 TTL 保護)"""
        try:
            return self._get_party_manager().get_quota_info()
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def send_party_contact_info(self, room_id: str, contact_info: str) -> Dict[str, Any]:
        """房主發布組隊完成聯絡資訊 (如 Discord 房號)，並排程 30 秒後銷毀房間"""
        try:
            return self._get_party_manager().send_room_contact_info(room_id, contact_info)
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def get_party_contact_info(self, room_id: str = "") -> Dict[str, Any]:
        """隊員獲取房主發布的房間聯絡資訊 (極輕量輪詢)"""
        try:
            return self._get_party_manager().get_room_contact_info(room_id)
        except Exception as e:
            return {"ok": False, "has_contact": False, "msg": str(e)}

    def inspect_party_resources(self, app_id: str) -> Dict[str, Any]:
        """檢測指定遊戲本地 Manifest, Lua 與線上補丁三檔就緒狀況"""
        try:
            from managers.party_packager import get_party_packager
            return get_party_packager().inspect_party_resources(app_id)
        except Exception as e:
            return {"ok": False, "error": str(e), "can_package": False}

    def prepare_party_package_upload(self, app_id: str, discord_webhook: str = "", game_name: str = "") -> Dict[str, Any]:
        """
        階段一：本地三檔檢查、打包並上傳至雲端（首選 Discord Webhook CDN，無限流量），確保取得下載網址
        """
        try:
            return self._get_party_manager().prepare_package_and_upload(
                app_id=str(app_id),
                discord_webhook=str(discord_webhook),
                game_name=str(game_name)
            )
        except Exception as e:
            return {"ok": False, "msg": f"本地打包與雲端上傳失敗: {e}"}

    def create_party_room(self, game_name: str, app_id: str, max_players: int = 4, is_public: bool = True,
                          note: str = "", auto_package_upload: bool = True, gas_url: str = "",
                          download_url: str = "", uploaded_gas_file_id: str = "") -> Dict[str, Any]:
        """
        階段二：向 Supabase 正式建立房間（必須含有已取得並驗證過的 Google Drive 下載網址）
        """
        try:
            return self._get_party_manager().create_room(
                game_name=game_name,
                app_id=str(app_id),
                max_players=int(max_players),
                is_public=bool(is_public),
                note=note,
                auto_package_upload=bool(auto_package_upload),
                gas_url=gas_url,
                download_url=download_url,
                uploaded_gas_file_id=uploaded_gas_file_id
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

    def get_party_logs(self, lines: int = 200) -> Dict[str, Any]:
        """讀取組隊與一鍵安裝日誌 logs/party.log 最新內容"""
        try:
            from managers.party_logger import get_recent_party_logs
            return {"ok": True, "logs": get_recent_party_logs(lines)}
        except Exception as e:
            return {"ok": False, "msg": f"讀取組隊日誌失敗: {e}"}

    def open_party_log(self) -> Dict[str, Any]:
        """在作業系統預設文字編輯器中開啟 logs/party.log"""
        try:
            from managers.party_logger import open_party_log_file
            ok = open_party_log_file()
            return {"ok": ok, "msg": "已開啟 logs/party.log" if ok else "開啟失敗"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def verify_party_fallback_passcode(self, passcode: str) -> Dict[str, Any]:
        """驗證今日備援門禁通行碼 (不可逆伺服器核驗)"""
        try:
            return self._get_party_manager().verify_fallback_passcode(passcode)
        except Exception as e:
            return {"ok": False, "msg": f"核驗通行碼失敗: {e}"}

    def check_party_identity_status(self) -> Dict[str, Any]:
        """檢查當前硬體指紋與身分黑名單狀態"""
        try:
            mgr = self._get_party_manager()
            is_banned, ban_reason = mgr.check_if_banned()
            has_lease = mgr.has_valid_fallback_lease()
            return {
                "ok": True,
                "is_banned": is_banned,
                "ban_reason": ban_reason,
                "has_fallback_lease": has_lease,
                "hwid": mgr.hwid,
                "steam_id": mgr.steam_id
            }
        except Exception as e:
            return {"ok": False, "msg": str(e)}

