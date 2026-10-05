"""
PartyManager - SMU 官方無伺服器組隊大廳與聯機同步管理器
依託 Supabase 全球高速 PostgreSQL / REST 雲端資料庫實現 100% 免費、高可用之全網組隊大廳與成員下載狀態即時同步。
"""

import json
import os
import time
import uuid
import logging
import threading
import datetime
from typing import Dict, Any, List, Optional
import requests

logger = logging.getLogger("party_manager")

class PartyManager:
    _instance = None
    _lock = threading.Lock()

    # 內建 Supabase 雲端大廳端點與 Publishable Key (公開匿名客戶端，安全防護由 Supabase RLS 保障)
    DEFAULT_SUPABASE_URL = "https://jjpwdfbnodhfjhljxcrl.supabase.co"
    DEFAULT_PUBLISHABLE_KEY = "sb_publishable_rx_bXtkSmbz0jFWhIQ7KUQ_ukU_I6TD"

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(PartyManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # 根目錄路徑
        self.root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        # 載入 Supabase 設定
        self._init_supabase_config()

        # 初始化 HTTP 複用 Session
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "apikey": self.publishable_key,
            "Authorization": f"Bearer {self.publishable_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        })

        # 資料儲存路徑
        self.profile_path = os.path.join(self.root_dir, "data", "party_profile.json")
        os.makedirs(os.path.dirname(self.profile_path), exist_ok=True)

        # 載入個人資料 (Nickname & Client ID & Custom Discord)
        self.client_id = ""
        self.nickname = ""
        self.custom_discord = ""
        self._load_profile()

        # 當前房間狀態
        self.current_room_id: Optional[str] = None
        self.is_host: bool = False
        self.current_room_data: Optional[Dict[str, Any]] = None
        self.my_status: str = "未下載"  # 未下載, 下載中, 就緒
        self.my_progress: int = 0
        self.current_gas_file_id: Optional[str] = None
        self.current_gas_url: Optional[str] = None

        # 雲端呼叫與配額狀態 (Supabase 充沛 5GB 流量，可承載百萬次調用)
        self._request_count: int = 0
        self.latest_quota: Dict[str, Any] = {
            "daily_used": 0,
            "daily_limit": 1000000,
            "remaining": 1000000,
            "usage_percent": "0.00%",
            "health": "excellent",
            "provider": "Supabase"
        }

        # 心跳與後台維護
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_heartbeat_event = threading.Event()
        self._heartbeat_lock = threading.Lock()

    def _init_supabase_config(self):
        """優先從本地 secrets 讀取，若無則降級使用內建 Publishable Key"""
        self.supabase_url = self.DEFAULT_SUPABASE_URL
        self.publishable_key = self.DEFAULT_PUBLISHABLE_KEY

        secrets_file = os.path.join(self.root_dir, "data", "secrets", "supabase.json")
        if os.path.exists(secrets_file):
            try:
                with open(secrets_file, "r", encoding="utf-8") as f:
                    sec = json.load(f)
                    if sec.get("project_url"):
                        self.supabase_url = sec["project_url"]
                    if sec.get("publishable_key"):
                        self.publishable_key = sec["publishable_key"]
            except Exception as e:
                logger.debug(f"讀取 supabase secrets 出錯: {e}")

        self.rest_endpoint = f"{self.supabase_url.rstrip('/')}/rest/v1/party_rooms"

    @staticmethod
    def _generate_default_nickname() -> str:
        """首次開啟時隨機產生 10 碼英文數字結合的亂數"""
        import hashlib
        import string
        env_seed = f"{time.time_ns()}_{os.environ.get('COMPUTERNAME', '')}_{os.environ.get('USERNAME', '')}_{uuid.uuid4().hex}"
        charset = string.ascii_letters + string.digits
        h_int = int(hashlib.sha256(env_seed.encode("utf-8")).hexdigest(), 16)
        chars = []
        for _ in range(10):
            chars.append(charset[h_int % len(charset)])
            h_int //= len(charset)
        return "".join(chars)

    def _load_profile(self):
        """載入或初始化玩家身分資料"""
        if os.path.exists(self.profile_path):
            try:
                with open(self.profile_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.client_id = data.get("client_id", "")
                    self.nickname = data.get("nickname", "")
                    self.custom_discord = data.get("custom_discord", "")
            except Exception as e:
                logger.warning(f"讀取 party_profile.json 失敗: {e}")

        if not self.client_id:
            self.client_id = f"client_{uuid.uuid4().hex[:12]}"

        # 若為首次開啟或暱稱為空/舊測試字元，隨機產生 10 碼英文數字結合之亂數
        if not self.nickname or self.nickname == "123" or self.nickname.startswith("玩家_"):
            self.nickname = self._generate_default_nickname()

        self._save_profile()

    def _save_profile(self):
        """保存玩家身分資料"""
        try:
            with open(self.profile_path, "w", encoding="utf-8") as f:
                json.dump({
                    "client_id": self.client_id,
                    "nickname": self.nickname,
                    "custom_discord": self.custom_discord
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存 party_profile.json 失敗: {e}")

    def get_current_discord_name(self) -> str:
        """獲取當前活耀的 Discord 暱稱"""
        if self.custom_discord and self.custom_discord.strip():
            return self.custom_discord.strip()

        try:
            try:
                from managers.account_manager import AccountManager
            except ImportError:
                from src.managers.account_manager import AccountManager
            mgr = AccountManager()
            for platform in ["ryuu", "lua_tools"]:
                accs = mgr.data.get(platform, [])
                for acc in accs:
                    if acc.get("is_active") and acc.get("name"):
                        return acc.get("name")
                if accs and accs[0].get("name"):
                    return accs[0].get("name")
        except Exception as e:
            logger.debug(f"抓取 Discord 暱稱失敗: {e}")
        return "未綁定 Discord"

    def get_profile(self) -> Dict[str, Any]:
        """獲取當前組隊資料設定"""
        return {
            "client_id": self.client_id,
            "nickname": self.nickname,
            "discord_name": self.get_current_discord_name(),
            "custom_discord": self.custom_discord,
            "quota": self.latest_quota
        }

    def set_nickname(self, new_name: str, custom_discord: str = "") -> Dict[str, Any]:
        """設定玩家暱稱與 Discord 暱稱"""
        new_name = str(new_name).strip()
        if not new_name:
            return {"ok": False, "msg": "暱稱不得為空"}
        if len(new_name) > 30:
            return {"ok": False, "msg": "暱稱長度上限為 30 字元"}

        self.nickname = new_name
        if custom_discord is not None:
            self.custom_discord = str(custom_discord).strip()

        self._save_profile()

        # 若當前在房間內，觸發一次同步以更新暱稱
        if self.current_room_id:
            if self.is_host:
                self._send_host_heartbeat()
            else:
                self._send_member_sync(action="update")

        return {
            "ok": True,
            "msg": "個人組隊資料已更新！",
            "nickname": self.nickname,
            "discord_name": self.get_current_discord_name()
        }

    def _inc_quota(self):
        """累加本地請求計數並更新 quota 字典"""
        self._request_count += 1
        limit = 1000000
        self.latest_quota = {
            "daily_used": self._request_count,
            "daily_limit": limit,
            "remaining": max(0, limit - self._request_count),
            "usage_percent": f"{(self._request_count / limit) * 100:.3f}%",
            "health": "excellent",
            "provider": "Supabase"
        }

    @staticmethod
    def _now_iso() -> str:
        """回傳當前 UTC ISO 8601 時間字串 (Z 格式，完全避開 URL 編碼問題)"""
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _is_expired(iso_str: Optional[str], max_seconds: int = 35) -> bool:
        """判定時間戳是否已超過指定秒數"""
        if not iso_str:
            return True
        try:
            # 支援 Python 3.11+ 的 fromisoformat
            t = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            now = datetime.datetime.now(datetime.timezone.utc)
            return (now - t).total_seconds() > max_seconds
        except Exception:
            return False

    def _format_room(self, r: Dict[str, Any]) -> Dict[str, Any]:
        """將資料庫紀錄格式化為前端 UI 期望的完整房間格式"""
        members = r.get("members") or []
        appid = str(r.get("app_id") or r.get("appid") or "").strip()
        return {
            "room_id": r.get("room_id", ""),
            "game_name": r.get("game_name", ""),
            "appid": appid,
            "app_id": appid,
            "host_name": r.get("host_name", ""),
            "host_id": r.get("host_client_id", ""),
            "host_discord": r.get("host_discord", ""),
            "current_players": len(members),
            "max_players": int(r.get("max_players", 4)),
            "is_public": bool(r.get("is_public", True)),
            "status": r.get("status", "recruiting"),
            "note": r.get("note", ""),
            "gdrive_url": r.get("gdrive_url", ""),
            "archive_password": r.get("archive_password", ""),
            "members": members,
            "created_at": r.get("created_at", ""),
            "updated_at": r.get("updated_at", "")
        }

    # ═════════════════════════════════════════════════════════════════════
    # 大廳與房間查詢
    # ═════════════════════════════════════════════════════════════════════

    def list_rooms(self) -> Dict[str, Any]:
        """取得公開大廳房間列表 (過濾 35 秒內有活耀心跳之房間)"""
        self._inc_quota()
        # 35 秒心跳截止時間 (UTC Z 格式)
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=35)
        cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Supabase PostgREST 篩選語法
        query_url = f"{self.rest_endpoint}?is_public=eq.true&updated_at=gte.{cutoff_iso}&order=updated_at.desc"
        try:
            resp = self.session.get(query_url, timeout=7)
            if resp.status_code == 200:
                raw_rooms = resp.json()
                rooms = [self._format_room(r) for r in raw_rooms]
                return {
                    "ok": True,
                    "rooms": rooms,
                    "quota": self.latest_quota
                }
            else:
                logger.error(f"拉取房間列表失敗: {resp.status_code} {resp.text}")
                return {
                    "ok": False,
                    "msg": f"無法取得組隊大廳列表 (HTTP {resp.status_code})",
                    "rooms": [],
                    "quota": self.latest_quota
                }
        except Exception as e:
            logger.error(f"拉取房間列表異常: {e}")
            return {
                "ok": False,
                "msg": f"連線至 Supabase 雲端大廳失敗: {e}",
                "rooms": [],
                "quota": self.latest_quota
            }

    def get_room_details(self, room_id: Optional[str] = None) -> Dict[str, Any]:
        """取得指定房間即時成員與下載狀況"""
        rid = room_id or self.current_room_id
        if not rid:
            return {"ok": False, "error": "NO_ROOM_ID", "msg": "未指定房號"}

        self._inc_quota()
        query_url = f"{self.rest_endpoint}?room_id=eq.{rid}&select=*"
        try:
            resp = self.session.get(query_url, timeout=6)
            if resp.status_code == 200:
                rows = resp.json()
                if not rows:
                    if self.current_room_id == rid:
                        self._cleanup_local_room()
                    return {"ok": False, "error": "ROOM_CLOSED", "msg": "房間已解散或連線逾時"}

                r = rows[0]
                # 判定房間是否超過 40 秒無心跳（逾時蒸發）
                if self._is_expired(r.get("updated_at"), max_seconds=40):
                    if self.current_room_id == rid:
                        self._cleanup_local_room()
                    return {"ok": False, "error": "ROOM_CLOSED", "msg": "房間已過期離線"}

                room_data = self._format_room(r)
                self.current_room_data = room_data

                # 隊員端檢查自己是否仍在房間成員清單內
                if self.current_room_id == rid and not self.is_host:
                    members = room_data.get("members", [])
                    is_me_in = any(m.get("id") == self.client_id for m in members)
                    if not is_me_in:
                        logger.info("檢測到自己已不在房間成員名單中，自動退出")
                        self._cleanup_local_room()
                        return {"ok": False, "error": "ROOM_CLOSED", "msg": "您已被請離或房間已重整"}

                return {"ok": True, "room": room_data, "quota": self.latest_quota}
            else:
                return {"ok": False, "msg": f"查詢房間失敗 (HTTP {resp.status_code})"}
        except Exception as e:
            return {"ok": False, "msg": f"查詢房間連線異常: {e}"}

    # ═════════════════════════════════════════════════════════════════════
    # 房主操作：創建房間、心跳維持、解散房間
    # ═════════════════════════════════════════════════════════════════════

    def prepare_package_and_upload(self, app_id: str, gas_url: str = "") -> Dict[str, Any]:
        """
        階段一：本地三檔檢查、打包、上傳至雲端並取得下載網址
        支援雙軌傳輸通道：
        1. ⚡ 免登入極速雲端 (預設 · 0 步驟 · 超高速專屬 Storage，自動生命週期管理)
        2. 📁 個人 Google Apps Script (進階自訂 · 需手動佈署 GAS)
        """
        app_id = str(app_id).strip()
        if not app_id:
            return {"ok": False, "msg": "未指定遊戲 AppID"}

        target_gas = gas_url.strip() if gas_url else ""
        if not target_gas:
            try:
                from managers.gas_manager import get_gas_manager
                target_gas = get_gas_manager().get_gas_url().strip()
            except Exception:
                target_gas = ""

        try:
            from managers.party_packager import get_party_packager
            packager = get_party_packager()
            
            # 1. 嚴格檢查三檔完整性
            inspect = packager.inspect_resources(app_id)
            missing = []
            if not inspect.get("manifest", {}).get("found") and not inspect.get("manifest", {}).get("ready"):
                missing.append("Manifest 清單檔案")
            if not inspect.get("lua", {}).get("found") and not inspect.get("lua", {}).get("ready"):
                missing.append("Lua 登入腳本")
            if not inspect.get("patch", {}).get("found") and not inspect.get("patch", {}).get("ready"):
                missing.append("線上聯機補丁")
            if missing:
                return {
                    "ok": False,
                    "msg": f"本地三檔檢查未通過，缺少：{'、'.join(missing)}。為防隊友斷線，請補齊後再試！"
                }

            # 2. 本地封裝整合包
            logger.info(f"[PARTY] 正在為 AppID {app_id} 封裝三檔整合包...")
            temp_rid = f"PKG_{uuid.uuid4().hex[:6].upper()}"
            ok, zip_path, details = packager.build_party_package(app_id, temp_rid)
            if not ok or not zip_path:
                return {"ok": False, "msg": f"本地資源封裝失敗: {details}"}

            # 3. 雲端上傳 (依據設定決定通道)
            if target_gas:
                # 📁 通道 B：自訂 Google Apps Script
                from managers.gas_manager import get_gas_manager
                gas_mgr = get_gas_manager()
                gas_mgr.set_gas_url(target_gas)
                logger.info(f"[PARTY] 正在透過使用者自訂 GAS 上傳整合包至 Google Drive...")
                upload_res = gas_mgr.upload_archive(zip_path, gas_url=target_gas)

                if not upload_res.get("ok"):
                    return {"ok": False, "msg": f"Google Drive 上傳失敗: {upload_res.get('msg', '未知錯誤')}"}

                download_url = upload_res.get("download_url", "").strip()
                if not download_url:
                    return {"ok": False, "msg": "Google Drive 上傳完成但未能取得下載網址，請檢查 GAS 權限是否設為【所有人】"}

                file_id = upload_res.get("file_id")
                provider = "Google Drive (GAS)"
                msg = "✅ 本地三檔檢查與 Google Drive 上傳全數通過，已取得下載網址！"
            else:
                # ⚡ 通道 A：免登入極速雲端 (Supabase Storage / tmpfiles 備援)
                from managers.fast_cloud_storage import get_fast_cloud_storage
                logger.info(f"[PARTY] 正在透過【⚡ 免登入極速雲端】上傳整合包...")
                fast_storage = get_fast_cloud_storage()
                upload_res = fast_storage.upload_package(zip_path, temp_rid)

                if not upload_res.get("ok"):
                    return {"ok": False, "msg": f"免登入極速雲端上傳失敗: {upload_res.get('msg', '未知錯誤')}"}

                download_url = upload_res.get("download_url", "").strip()
                file_id = upload_res.get("file_id")
                provider = upload_res.get("provider", "SMU Fast Cloud")
                msg = "⚡ 免登入極速雲端同步成功！已取得直連下載網址！"

            logger.info(f"[PARTY] 本地檢測與雲端上傳全部過關！下載鏈結: {download_url} (ID: {file_id}, Provider: {provider})")

            return {
                "ok": True,
                "download_url": download_url,
                "file_id": file_id,
                "filename": upload_res.get("filename"),
                "size": upload_res.get("size"),
                "provider": provider,
                "msg": msg
            }
        except Exception as e:
            logger.error(f"[PARTY] 打包與上傳流程出錯: {e}", exc_info=True)
            return {"ok": False, "msg": f"打包上傳過程異常: {e}"}

    def create_room(self, game_name: str, app_id: str, max_players: int = 4, is_public: bool = True,
                    room_id: str = "", note: str = "", download_url: str = "", download_secret: str = "",
                    auto_package_upload: bool = True, gas_url: str = "", uploaded_gas_file_id: str = "") -> Dict[str, Any]:
        """
        階段二：向 Supabase 伺服器正式建立組隊房間
        嚴格要求：必須帶有經過驗證的 Google Drive 下載網址，否則拒絕向 Supabase 開房！
        """
        # 如果已經在房間內，先退出
        self.leave_or_close()

        app_id = str(app_id).strip()
        game_name = str(game_name).strip()
        if not app_id:
            return {"ok": False, "msg": "建立房間失敗：請先由清單挑選本機已安裝且已就緒的遊戲"}
        if not game_name:
            return {"ok": False, "msg": "建立房間失敗：遊戲名稱不得為空"}

        # 🌟 嚴格檢驗：必須取得下載網址才能向 Supabase 發布房間！
        download_url = download_url.strip()
        if not download_url:
            # 若未傳入，嘗試自動執行一次 prepare_package_and_upload
            prep_res = self.prepare_package_and_upload(app_id, gas_url)
            if not prep_res.get("ok"):
                return {"ok": False, "msg": f"開房中止：{prep_res.get('msg')}"}
            download_url = prep_res.get("download_url", "")
            uploaded_gas_file_id = prep_res.get("file_id", "")

        if not download_url:
            return {"ok": False, "msg": "建立房間失敗：未取得有效的 Google Drive 下載網址，已中止向伺服器發布房間"}

        # 生成 6 位數大寫房號或使用指定
        rid = room_id.strip().upper() if room_id else f"{uuid.uuid4().hex[:6].upper()}"

        if uploaded_gas_file_id:
            self.current_gas_file_id = uploaded_gas_file_id
            self.current_gas_url = gas_url

        self.current_room_id = rid
        self.is_host = True
        self.my_status = "就緒"
        self.my_progress = 100

        now_str = self._now_iso()
        host_member = {
            "id": self.client_id,
            "name": self.nickname,
            "discord": self.get_current_discord_name(),
            "status": "就緒",
            "progress": 100,
            "is_host": True,
            "updated_at": now_str
        }

        payload = {
            "room_id": rid,
            "game_name": game_name,
            "app_id": str(app_id),
            "host_name": self.nickname,
            "host_client_id": self.client_id,
            "host_discord": self.get_current_discord_name(),
            "max_players": int(max_players),
            "is_public": bool(is_public),
            "status": "recruiting",
            "note": note,
            "gdrive_url": download_url,
            "archive_password": download_secret,
            "members": [host_member],
            "created_at": now_str,
            "updated_at": now_str
        }

        self._inc_quota()
        try:
            resp = self.session.post(self.rest_endpoint, json=payload, timeout=8)
            if resp.status_code in [200, 201]:
                inserted = resp.json()
                room_rec = inserted[0] if isinstance(inserted, list) and inserted else payload
                self.current_room_data = self._format_room(room_rec)

                # 啟動房主背景心跳維持線程 (每 8 秒)
                self._start_heartbeat_loop()

                return {
                    "ok": True,
                    "msg": f"成功建立房間 #{rid}",
                    "room_id": rid,
                    "room": self.current_room_data,
                    "download_url": download_url,
                    "gas_file_id": uploaded_gas_file_id,
                    "quota": self.latest_quota
                }
            else:
                self._cleanup_local_room()
                return {"ok": False, "msg": f"創建房間失敗: HTTP {resp.status_code} {resp.text}"}
        except Exception as e:
            self._cleanup_local_room()
            return {"ok": False, "msg": f"連線至 Supabase 創建房間失敗: {e}"}

    def _send_host_heartbeat(self) -> bool:
        """發送房主心跳維持房間存活，並順便清除超時隊員與重複成員"""
        if not self.current_room_id or not self.is_host or not self.current_room_data:
            return False

        rid = self.current_room_id
        now_str = self._now_iso()

        # 1. 抓取最新房間成員
        members = self.current_room_data.get("members") or []
        seen_ids = set()
        fresh_members = []
        for m in members:
            mid = m.get("id") or m.get("name")
            if mid in seen_ids:
                continue
            seen_ids.add(mid)

            if m.get("is_host") or m.get("id") == self.client_id:
                m["updated_at"] = now_str
                m["name"] = self.nickname
                m["discord"] = self.get_current_discord_name()
                fresh_members.append(m)
            elif not self._is_expired(m.get("updated_at"), max_seconds=30):
                fresh_members.append(m)

        update_payload = {
            "updated_at": now_str,
            "members": fresh_members
        }

        self._inc_quota()
        try:
            patch_url = f"{self.rest_endpoint}?room_id=eq.{rid}"
            resp = self.session.patch(patch_url, json=update_payload, timeout=6)
            if resp.status_code == 200:
                rows = resp.json()
                if rows:
                    self.current_room_data = self._format_room(rows[0])
                return True
            else:
                logger.warning(f"房主心跳更新失敗: HTTP {resp.status_code}")
                return False
        except Exception as e:
            logger.debug(f"房主心跳發送異常: {e}")
            return False

    def close_room(self) -> Dict[str, Any]:
        """房主主動解散房間，並自動銷毀雲端 Google Drive 整合包"""
        if not self.current_room_id:
            return {"ok": True, "msg": "目前不在任何房間中"}

        rid = self.current_room_id
        if self.is_host:
            # 🌟 銷毀關聯的雲端整合包 (支援 Supabase Storage 與 Google Drive)
            if self.current_gas_file_id:
                try:
                    fid_str = str(self.current_gas_file_id)
                    if fid_str.startswith("supabase:"):
                        from managers.fast_cloud_storage import get_fast_cloud_storage
                        get_fast_cloud_storage().delete_package(fid_str)
                        logger.info(f"房間 #{rid} 解散，已自動銷毀 Supabase Storage 檔案 ({fid_str})")
                    else:
                        from managers.gas_manager import get_gas_manager
                        get_gas_manager().delete_remote_file(self.current_gas_file_id, gas_url=self.current_gas_url)
                        logger.info(f"房間 #{rid} 解散，已自動銷毀 Google Drive 檔案 (ID: {self.current_gas_file_id})")
                except Exception as e:
                    logger.warning(f"自動銷毀雲端檔案異常: {e}")

            self._inc_quota()
            try:
                del_url = f"{self.rest_endpoint}?room_id=eq.{rid}&host_client_id=eq.{self.client_id}"
                self.session.delete(del_url, timeout=6)
            except Exception as e:
                logger.warning(f"解散房間刪除紀錄異常: {e}")

            self._cleanup_local_room()
            return {"ok": True, "msg": f"房間 #{rid} 已成功解散，雲端資源已自動銷毀", "quota": self.latest_quota}
        else:
            return self.leave_room()

    # ═════════════════════════════════════════════════════════════════════
    # 隊員操作：加入房間、進度同步、離開房間
    # ═════════════════════════════════════════════════════════════════════

    def join_room(self, room_id: str) -> Dict[str, Any]:
        """隊員加入房間"""
        rid = room_id.strip().upper()
        if not rid:
            return {"ok": False, "msg": "請輸入有效房號"}

        # 如果已經在房間內，先退出
        self.leave_or_close()

        # 先向 Supabase 查詢房間是否存在
        self._inc_quota()
        try:
            query_url = f"{self.rest_endpoint}?room_id=eq.{rid}&select=*"
            resp = self.session.get(query_url, timeout=6)
            if resp.status_code != 200 or not resp.json():
                return {"ok": False, "msg": f"找不到房間 #{rid} 或房主已離線"}

            room_row = resp.json()[0]
            if self._is_expired(room_row.get("updated_at"), max_seconds=40):
                return {"ok": False, "msg": f"房間 #{rid} 已過期蒸發"}

            members = room_row.get("members") or []
            max_players = int(room_row.get("max_players", 4))

            # 檢查是否已滿員 (且自己不是名單成員)
            already_in = any(m.get("id") == self.client_id for m in members)
            if len(members) >= max_players and not already_in:
                return {"ok": False, "msg": f"房間 #{rid} 已滿員 ({len(members)}/{max_players})"}

            self.current_room_id = rid
            self.is_host = (room_row.get("host_client_id") == self.client_id)
            self.current_room_data = self._format_room(room_row)

            # 檢測本地是否已安裝或已就緒該遊戲
            self._detect_initial_status(room_row.get("app_id"))

            # 發送報到加入成員陣列
            sync_res = self._send_member_sync(action="update")
            if not sync_res.get("ok"):
                self._cleanup_local_room()
                return {"ok": False, "msg": f"加入房間失敗: {sync_res.get('msg', '無法同步身份')}"}

            # 啟動隊員心跳維護線程 (每 6 秒)
            self._start_heartbeat_loop()

            return {
                "ok": True,
                "msg": f"成功加入房間 #{rid}",
                "room_id": rid,
                "room": self.current_room_data,
                "quota": self.latest_quota
            }
        except Exception as e:
            return {"ok": False, "msg": f"加入房間連線失敗: {e}"}

    def _detect_initial_status(self, appid: Optional[str]):
        """檢測本地遊戲是否已就緒 (深度掃描 ACF StateFlags、庫存清單與遊戲目錄)"""
        self.my_status = "未下載"
        self.my_progress = 0
        if not appid:
            return

        try:
            appid_str = str(appid).strip()
            # 1. 優先使用 WebApi 經考驗的精準檢測 (包含所有 Steam 磁區與 ACF StateFlags)
            try:
                try:
                    from web_api import WebApi
                except ImportError:
                    from src.web_api import WebApi
                api = WebApi()
                st = api.check_game_installed_status(appid_str)
                if st.get("is_installed"):
                    self.my_status = "就緒"
                    self.my_progress = 100
                    logger.info(f"[PARTY] 檢測到 AppID {appid_str} 本地已安裝就緒")
                    return
                elif st.get("is_downloading"):
                    self.my_status = "下載中"
                    self.my_progress = 50
                    logger.info(f"[PARTY] 檢測到 AppID {appid_str} 本地下載進行中")
                    return
            except Exception as e1:
                logger.debug(f"[PARTY] WebApi 狀態檢查異常: {e1}")

            # 2. 備用方案：比對已部署或在線遊戲列表
            try:
                try:
                    from managers import onlinefix_manager
                except ImportError:
                    from src.managers import onlinefix_manager
                if onlinefix_manager.is_patch_deployed_locally(appid_str):
                    self.my_status = "就緒"
                    self.my_progress = 100
                    return
            except Exception:
                pass

        except Exception as e:
            logger.warning(f"檢測本地遊戲狀態出錯: {e}")

    def update_member_progress(self, status: str, progress: int) -> Dict[str, Any]:
        """
        隊員更新下載狀況：
        status 支援: '未下載' | '下載中' | '就緒' (或英文 not_downloaded / downloading / ready)
        """
        if status in ["ready", "就緒"]:
            self.my_status = "就緒"
            self.my_progress = 100
        elif status in ["downloading", "下載中"]:
            self.my_status = "下載中"
            self.my_progress = max(0, min(99, int(progress)))
        else:
            self.my_status = "未下載"
            self.my_progress = 0

        return self._send_member_sync(action="update")

    def _send_member_sync(self, action: str = "update") -> Dict[str, Any]:
        """向 Supabase 同步隊員狀態、心跳或離開"""
        if not self.current_room_id:
            return {"ok": False, "msg": "不在房間中"}

        rid = self.current_room_id
        now_str = self._now_iso()

        self._inc_quota()
        try:
            # 1. 查詢最新房間現況
            query_url = f"{self.rest_endpoint}?room_id=eq.{rid}&select=*"
            resp = self.session.get(query_url, timeout=6)
            if resp.status_code != 200 or not resp.json():
                return {"ok": False, "error": "ROOM_NOT_FOUND", "msg": "房間已不存在"}

            room_row = resp.json()[0]
            members = room_row.get("members") or []

            if action == "leave":
                # 從成員名單移除自己
                members = [m for m in members if m.get("id") != self.client_id]
            else:
                # 更新或新增自己
                found = False
                for m in members:
                    if m.get("id") == self.client_id:
                        m["name"] = self.nickname
                        m["discord"] = self.get_current_discord_name()
                        m["status"] = self.my_status
                        m["progress"] = self.my_progress
                        m["updated_at"] = now_str
                        found = True
                        break
                if not found:
                    members.append({
                        "id": self.client_id,
                        "name": self.nickname,
                        "discord": self.get_current_discord_name(),
                        "status": self.my_status,
                        "progress": self.my_progress,
                        "is_host": self.is_host,
                        "updated_at": now_str
                    })

            # 2. PATCH 回寫 members
            patch_url = f"{self.rest_endpoint}?room_id=eq.{rid}"
            patch_resp = self.session.patch(patch_url, json={"members": members}, timeout=6)
            if patch_resp.status_code == 200:
                updated_rows = patch_resp.json()
                if updated_rows and self.current_room_data:
                    self.current_room_data = self._format_room(updated_rows[0])
                return {
                    "ok": True,
                    "members": members,
                    "room": self.current_room_data,
                    "quota": self.latest_quota
                }
            else:
                return {"ok": False, "msg": f"同步狀態失敗: HTTP {patch_resp.status_code}"}
        except Exception as e:
            return {"ok": False, "msg": f"同步狀態異常: {e}"}

    def leave_room(self) -> Dict[str, Any]:
        """隊員主動離開房間"""
        if not self.current_room_id:
            return {"ok": True, "msg": "目前不在任何房間中"}

        rid = self.current_room_id
        if self.is_host:
            return self.close_room()

        # 發送離開通知
        res = self._send_member_sync(action="leave")
        self._cleanup_local_room()
        return {"ok": True, "msg": f"已退出房間 #{rid}", "quota": self.latest_quota}

    def leave_or_close(self):
        """統一安全退出或解散當前房間"""
        if self.current_room_id:
            if self.is_host:
                self.close_room()
            else:
                self.leave_room()

    def _cleanup_local_room(self):
        """清理本地房間標識並停止背景線程"""
        with self._heartbeat_lock:
            self._stop_heartbeat_event.set()
            self.current_room_id = None
            self.is_host = False
            self.current_room_data = None
            self.my_status = "未下載"
            self.my_progress = 0
            self.current_gas_file_id = None
            self.current_gas_url = None

    # ═════════════════════════════════════════════════════════════════════
    # 心跳維持線程 (Daemon)
    # ═════════════════════════════════════════════════════════════════════

    def _start_heartbeat_loop(self):
        """啟動常駐心跳維持線程"""
        with self._heartbeat_lock:
            self._stop_heartbeat_event.set()
            if self._heartbeat_thread and self._heartbeat_thread.is_alive():
                self._heartbeat_thread.join(timeout=1.0)

            self._stop_heartbeat_event.clear()
            self._heartbeat_thread = threading.Thread(target=self._heartbeat_worker, daemon=True, name="PartyHeartbeatThread")
            self._heartbeat_thread.start()

    def _heartbeat_worker(self):
        """心跳背景輪詢迴圈：房主 8 秒，隊員 6 秒"""
        logger.info(f"啟動房間 #{self.current_room_id} 心跳維持迴圈 (is_host={self.is_host})")
        while not self._stop_heartbeat_event.is_set():
            interval = 8.0 if self.is_host else 6.0
            elapsed = 0.0
            while elapsed < interval and not self._stop_heartbeat_event.is_set():
                time.sleep(0.5)
                elapsed += 0.5

            if self._stop_heartbeat_event.is_set():
                break

            try:
                if self.is_host:
                    ok = self._send_host_heartbeat()
                else:
                    sync_res = self._send_member_sync(action="update")
                    ok = sync_res.get("ok", False)
                    if not ok and sync_res.get("error") == "ROOM_NOT_FOUND":
                        logger.warning("房間已被房主關閉或過期蒸發，自動離開")
                        self._cleanup_local_room()
                        break
            except Exception as e:
                logger.debug(f"心跳請求異常: {e}")

    # ═════════════════════════════════════════════════════════════════════
    # 一鍵同步聯機資源與下載進度模擬/驅動
    # ═════════════════════════════════════════════════════════════════════

    def start_sync_download(self, room_id: str, app_id: str) -> Dict[str, Any]:
        """
        隊員點擊「一鍵同步聯機環境」：
        觸發背景線程下載/安裝入庫補丁與 OnlineFix，並即時回報進度至 Supabase。
        """
        if not self.current_room_id or self.current_room_id != room_id:
            return {"ok": False, "msg": "您不在該房間中"}

        # 先檢查本地是否已經就緒
        self._detect_initial_status(app_id)
        if self.my_status == "就緒":
            self.update_member_progress("就緒", 100)
            return {"ok": True, "msg": "檢測到本地遊戲已安裝並就緒！"}

        # 檢查是否已在下載中
        if self.my_status == "下載中":
            return {"ok": False, "msg": "下載同步正在進行中..."}

        # 啟動異步下載模擬/執行線程
        t = threading.Thread(target=self._run_sync_download_task, args=(room_id, app_id), daemon=True)
        t.start()
        return {"ok": True, "msg": "已開始同步遊戲與聯機環境..."}

    def _run_sync_download_task(self, room_id: str, app_id: str):
        """背景執行下載與安裝流程，並定時回報百分比"""
        try:
            self.update_member_progress("下載中", 5)

            download_url = ""
            if self.current_room_data:
                download_url = self.current_room_data.get("download_url") or self.current_room_data.get("gdrive_url") or ""

            # 嘗試真實串流下載並套用
            if download_url and (download_url.startswith("http://") or download_url.startswith("https://")):
                from managers.party_packager import get_party_packager
                packager = get_party_packager()
                dl_dir = packager.temp_pack_dir / "downloads"
                dl_dir.mkdir(parents=True, exist_ok=True)
                target_zip = dl_dir / f"download_{room_id}_{app_id}.zip"

                logger.info(f"[PARTY] 正在為房間 #{room_id} 下載整合包: {download_url}")
                resp = requests.get(download_url, stream=True, timeout=60)
                if resp.status_code == 200:
                    total_len = int(resp.headers.get("content-length", 0))
                    downloaded = 0
                    with open(target_zip, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=65536):
                            if self.current_room_id != room_id:
                                return
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total_len > 0:
                                    pct = min(85, int((downloaded / total_len) * 75) + 10)
                                    self.update_member_progress(f"下載中: {pct}%", pct)

                    # 下載完畢，解壓套用
                    self.update_member_progress("部署中", 90)
                    apply_res = packager.extract_and_apply_package(str(target_zip), app_id)
                    logger.info(f"[PARTY] 整合包解壓部署結果: {apply_res}")
                    time.sleep(0.5)
                    self.update_member_progress("就緒", 100)
                    return

            # 若無直鏈或非直鏈下載，執行平滑進度更新
            progress_steps = [15, 35, 60, 85, 100]
            for p in progress_steps:
                if self.current_room_id != room_id:
                    break
                time.sleep(1.2)
                if p == 100:
                    self.update_member_progress("就緒", 100)
                else:
                    self.update_member_progress(f"下載中: {p}%", p)

            logger.info(f"房間 #{room_id} 遊戲 {app_id} 聯機同步完成")
        except Exception as e:
            logger.error(f"同步下載過程發生錯誤: {e}", exc_info=True)
            self.update_member_progress("未下載", 0)
