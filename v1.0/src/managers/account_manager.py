import os
import json
import shutil
import sqlite3
import datetime
import tempfile
from pathlib import Path
from PySide6.QtCore import QObject, Signal
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineUrlRequestInterceptor

_ROOT_DIR = Path(__file__).parent.parent.parent
_ACCOUNTS_FILE = _ROOT_DIR / "data" / "credentials" / "accounts_registry.json"
_PROFILES_DIR = _ROOT_DIR / "data" / "credentials" / "profiles"

class AccountManager(QObject):
    account_changed = Signal(str, str) # platform, account_id
    quota_updated = Signal(str, str, int, int) # platform, account_id, used, total
    registry_updated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        _PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        self.data = self._load_data()
        self._auto_migrate_legacy()
        self._check_daily_reset()
        self._sanitize_account_names()

    def _load_data(self) -> dict:
        if _ACCOUNTS_FILE.exists():
            try:
                with open(_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[account_manager] Failed to load registry: {e}")
        return {
            "lua_tools": [],
            "ryuu": [],
            "active_account_lt": None,
            "active_account_ryuu": None,
            "auto_rotate": True
        }

    def save_data(self):
        try:
            _ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_ACCOUNTS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            self.registry_updated.emit()
        except Exception as e:
            print(f"[account_manager] Failed to save registry: {e}")

    def _auto_migrate_legacy(self):
        """
        將現有 data/credentials/lua_tools_profile 和 ryuu_profile 遷移為首個帳號。
        """
        legacy_lt = _ROOT_DIR / "data" / "credentials" / "lua_tools_profile"
        if legacy_lt.exists() and not self.data.get("lua_tools"):
            cookie_file = legacy_lt / "Cookies"
            if cookie_file.exists():
                user_info = self._extract_user_info_from_sqlite(cookie_file, "lua.tools")
                target_dir = _PROFILES_DIR / "lt_default"
                if not target_dir.exists():
                    try:
                        shutil.copytree(legacy_lt, target_dir)
                    except Exception:
                        pass
                
                acc_id = "lt_default"
                acc = {
                    "id": acc_id,
                    "platform": "lua_tools",
                    "name": user_info.get("name", "帳號 1 (預設)"),
                    "email": user_info.get("email", ""),
                    "avatar_url": user_info.get("avatar_url", ""),
                    "profile_dir": str(target_dir),
                    "daily_limit": 25,
                    "quota_used_today": 0,
                    "quota_date": datetime.date.today().isoformat(),
                    "is_exhausted": False,
                    "added_time": datetime.datetime.now().isoformat()
                }
                self.data["lua_tools"].append(acc)
                self.data["active_account_lt"] = acc_id
                self.save_data()

        legacy_ryuu = _ROOT_DIR / "data" / "credentials" / "ryuu_profile"
        if legacy_ryuu.exists() and not self.data.get("ryuu"):
            cookie_file = legacy_ryuu / "Cookies"
            if cookie_file.exists():
                target_dir = _PROFILES_DIR / "ryuu_default"
                if not target_dir.exists():
                    try:
                        shutil.copytree(legacy_ryuu, target_dir)
                    except Exception:
                        pass
                acc_id = "ryuu_default"
                acc = {
                    "id": acc_id,
                    "platform": "ryuu",
                    "name": "Ryuu 帳號 1",
                    "email": "",
                    "avatar_url": "",
                    "profile_dir": str(target_dir),
                    "daily_limit": 50,
                    "quota_used_today": 0,
                    "quota_date": datetime.date.today().isoformat(),
                    "is_exhausted": False,
                    "is_expired": False,
                    "added_time": datetime.datetime.now().isoformat()
                }
                self.data["ryuu"].append(acc)
                self.data["active_account_ryuu"] = acc_id
                self.save_data()

    def update_realtime_quota(self, platform: str, downloads_left: int, daily_limit: int = None, account_id: str = None):
        """
        從網頁或 API 實際讀取到的剩餘配額直接校準本地資料庫。
        """
        self._check_daily_reset()
        acc = None
        if account_id:
            for a in self.get_accounts(platform):
                if a.get("id") == account_id:
                    acc = a
                    break
        if not acc:
            acc = self.get_active_account(platform)
        if not acc:
            return

        if daily_limit:
            acc["daily_limit"] = daily_limit
        total_limit = acc.get("daily_limit", 50 if platform == "ryuu" else 25)
        acc["quota_used_today"] = max(0, total_limit - downloads_left)
        acc["is_exhausted"] = (downloads_left <= 0)
        acc["is_expired"] = False
        self.save_data()
        self.quota_updated.emit(platform, acc["id"], acc["quota_used_today"], total_limit)

    def _extract_user_info_from_sqlite(self, cookie_path: Path, platform_or_pattern: str) -> dict:
        info = {"name": "", "email": "", "avatar_url": ""}
        if not cookie_path.exists():
            return info
        tmp_fd = None
        tmp_path = None
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db")
            os.close(tmp_fd)
            shutil.copy2(cookie_path, tmp_path)
            conn = sqlite3.connect(tmp_path)
            cur = conn.cursor()
            is_lt = "lua" in platform_or_pattern.lower()
            if is_lt:
                cur.execute("SELECT name, value FROM cookies WHERE host_key LIKE '%lua.tools%'")
            else:
                cur.execute("SELECT name, value FROM cookies WHERE host_key LIKE '%ryuu%' OR host_key LIKE '%generator%'")
            cookies = dict(cur.fetchall())
            conn.close()

            if is_lt:
                token_str = (cookies.get("sb-db-auth-token.0", "") + cookies.get("sb-db-auth-token.1", ""))
                if token_str:
                    import base64
                    clean = token_str.replace("base64-", "")
                    padding = "=" * ((4 - len(clean) % 4) % 4)
                    decoded = base64.b64decode(clean + padding).decode("utf-8", errors="ignore")
                    j_data = json.loads(decoded)
                    user = j_data.get("user", {})
                    meta = user.get("user_metadata", {})
                    gname = meta.get("custom_claims", {}).get("global_name")
                    uname = meta.get("full_name") or meta.get("name")
                    if uname and uname.endswith("#0"):
                        uname = uname[:-2]
                    email = user.get("email") or meta.get("email", "")
                    info["email"] = email
                    info["avatar_url"] = meta.get("avatar_url", "")
                    if gname and uname and gname != uname:
                        info["name"] = f"{gname} (@{uname})"
                    elif gname:
                        info["name"] = gname
                    elif uname:
                        info["name"] = f"@{uname}"
                    elif email:
                        info["name"] = email
            else:
                session_val = cookies.get("session", "")
                if session_val:
                    import base64
                    import zlib
                    parts = session_val.split(".")
                    payload = parts[1] if session_val.startswith(".") else parts[0]
                    padding = "=" * ((4 - len(payload) % 4) % 4)
                    raw = base64.urlsafe_b64decode(payload + padding)
                    try:
                        raw = zlib.decompress(raw)
                    except Exception:
                        pass
                    j_data = json.loads(raw.decode("utf-8", errors="ignore"))
                    u = j_data.get("user", {})
                    uid = str(u.get("id", ""))
                    uname = u.get("username", "")
                    avatar = u.get("avatar", "")
                    if uname:
                        info["name"] = f"@{uname}"
                    if avatar and uid:
                        info["avatar_url"] = f"https://cdn.discordapp.com/avatars/{uid}/{avatar}.png"
        except Exception as e:
            print(f"[account_manager] Extract user info failed: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
        return info

    def _sanitize_account_names(self):
        """
        檢查並自動修復既有帳號清單，將「未知帳號」或通用命名依據本地 Cookies 重新校準為具體的使用者名稱。
        """
        changed = False
        for platform in ["lua_tools", "ryuu"]:
            for acc in self.data.get(platform, []):
                curr_name = acc.get("name", "")
                needs_fix = (
                    not curr_name
                    or "未知" in curr_name
                    or curr_name.startswith("Ryuu 帳號 (")
                    or curr_name.startswith("帳號 (")
                )
                if needs_fix:
                    p_dir = Path(acc.get("profile_dir", ""))
                    cookie_file = p_dir / "Cookies"
                    if cookie_file.exists():
                        info = self._extract_user_info_from_sqlite(cookie_file, platform)
                        if info.get("name"):
                            acc["name"] = info["name"]
                            if info.get("email") and not acc.get("email"):
                                acc["email"] = info["email"]
                            if info.get("avatar_url") and not acc.get("avatar_url"):
                                acc["avatar_url"] = info["avatar_url"]
                            changed = True
        if changed:
            self.save_data()

    def _check_daily_reset(self):
        today_str = datetime.date.today().isoformat()
        changed = False
        for platform in ["lua_tools", "ryuu"]:
            for acc in self.data.get(platform, []):
                if acc.get("quota_date") != today_str:
                    acc["quota_date"] = today_str
                    acc["quota_used_today"] = 0
                    acc["is_exhausted"] = False
                    changed = True
        if changed:
            self.save_data()

    def get_accounts(self, platform: str) -> list:
        self._check_daily_reset()
        return self.data.get(platform, [])

    def get_active_account(self, platform: str) -> dict:
        self._check_daily_reset()
        key = "active_account_lt" if platform == "lua_tools" else "active_account_ryuu"
        active_id = self.data.get(key)
        accounts = self.get_accounts(platform)
        if not accounts:
            return None
        for acc in accounts:
            if acc.get("id") == active_id:
                return acc
        # Default to first if not set
        self.data[key] = accounts[0]["id"]
        self.save_data()
        return accounts[0]

    def set_active_account(self, platform: str, account_id: str) -> bool:
        key = "active_account_lt" if platform == "lua_tools" else "active_account_ryuu"
        accounts = self.get_accounts(platform)
        for acc in accounts:
            if acc.get("id") == account_id:
                self.data[key] = account_id
                acc["is_expired"] = False
                self.save_data()
                self.account_changed.emit(platform, account_id)
                return True
        return False

    def create_new_account_profile_dir(self, platform: str) -> tuple[str, Path]:
        import uuid
        acc_id = f"{'lt' if platform == 'lua_tools' else 'ryuu'}_{uuid.uuid4().hex[:8]}"
        p_dir = _PROFILES_DIR / acc_id
        p_dir.mkdir(parents=True, exist_ok=True)
        return acc_id, p_dir

    def register_account(self, platform: str, acc_id: str, profile_dir: Path, name=None) -> dict:
        cookie_file = profile_dir / "Cookies"
        user_info = self._extract_user_info_from_sqlite(cookie_file, platform)

        raw_display = name or user_info.get("name")
        if raw_display and "未知" not in raw_display:
            display_name = raw_display
        elif user_info.get("name") and "未知" not in user_info.get("name"):
            display_name = user_info.get("name")
        else:
            prefix = "Lua.tools" if platform == "lua_tools" else "Ryuu"
            display_name = f"{prefix} 使用者 ({acc_id[-4:]})"
        daily_limit = 25 if platform == "lua_tools" else 50

        # Check if this account ID already exists
        accounts = self.data.setdefault(platform, [])
        for i, existing in enumerate(accounts):
            if existing.get("id") == acc_id:
                existing["name"] = display_name
                existing["email"] = user_info.get("email", existing.get("email", ""))
                existing["avatar_url"] = user_info.get("avatar_url", existing.get("avatar_url", ""))
                existing["daily_limit"] = 50 if platform == "ryuu" else existing.get("daily_limit", 25)
                existing["is_expired"] = False
                existing["is_exhausted"] = False
                self.save_data()
                self.account_changed.emit(platform, acc_id)
                return existing

        new_acc = {
            "id": acc_id,
            "platform": platform,
            "name": display_name,
            "email": user_info.get("email", ""),
            "avatar_url": user_info.get("avatar_url", ""),
            "profile_dir": str(profile_dir),
            "daily_limit": daily_limit,
            "quota_used_today": 0,
            "quota_date": datetime.date.today().isoformat(),
            "is_exhausted": False,
            "is_expired": False,
            "added_time": datetime.datetime.now().isoformat()
        }
        accounts.append(new_acc)
        key = "active_account_lt" if platform == "lua_tools" else "active_account_ryuu"
        self.data[key] = acc_id
        self.save_data()
        self.account_changed.emit(platform, acc_id)
        return new_acc

    def delete_account(self, platform: str, account_id: str) -> bool:
        accounts = self.data.get(platform, [])
        idx_to_remove = None
        for i, acc in enumerate(accounts):
            if acc.get("id") == account_id:
                idx_to_remove = i
                break
        if idx_to_remove is not None:
            removed = accounts.pop(idx_to_remove)
            p_dir = Path(removed.get("profile_dir", ""))
            if p_dir.exists() and p_dir != _ROOT_DIR / "data" / "credentials" / "lua_tools_profile":
                try:
                    shutil.rmtree(p_dir, ignore_errors=True)
                except Exception:
                    pass
            key = "active_account_lt" if platform == "lua_tools" else "active_account_ryuu"
            if self.data.get(key) == account_id:
                self.data[key] = accounts[0]["id"] if accounts else None
            self.save_data()
            self.registry_updated.emit()
            return True
        return False

    def record_quota_usage(self, platform: str, account_id: str = None, count: int = 1):
        self._check_daily_reset()
        acc = None
        if account_id:
            for a in self.get_accounts(platform):
                if a.get("id") == account_id:
                    acc = a
                    break
        if not acc:
            acc = self.get_active_account(platform)
        if not acc:
            return

        default_limit = 50 if platform == "ryuu" else 25
        acc["daily_limit"] = acc.get("daily_limit", default_limit)
        limit = acc["daily_limit"]
        acc["quota_used_today"] = acc.get("quota_used_today", 0) + count
        if acc["quota_used_today"] >= limit:
            acc["is_exhausted"] = True
        self.save_data()
        self.quota_updated.emit(platform, acc["id"], acc["quota_used_today"], limit)

    def mark_account_exhausted(self, platform: str, account_id: str = None):
        """
        當收到 HTTP 429 配額已滿時呼叫，標記當前帳號今日配額已用罄。
        """
        self._check_daily_reset()
        acc = None
        if account_id:
            for a in self.get_accounts(platform):
                if a.get("id") == account_id:
                    acc = a
                    break
        if not acc:
            acc = self.get_active_account(platform)
        if not acc:
            return

        default_limit = 50 if platform == "ryuu" else 25
        limit = acc.get("daily_limit", default_limit)
        acc["is_exhausted"] = True
        acc["quota_used_today"] = limit
        self.save_data()
        self.quota_updated.emit(platform, acc["id"], acc["quota_used_today"], limit)

    def mark_account_expired(self, platform: str, account_id: str = None):
        """
        當收到 HTTP 401 / 403 未授權時呼叫，標記當前帳號憑證已失效/過期。
        """
        self._check_daily_reset()
        acc = None
        if account_id:
            for a in self.get_accounts(platform):
                if a.get("id") == account_id:
                    acc = a
                    break
        if not acc:
            acc = self.get_active_account(platform)
        if not acc:
            return

        acc["is_expired"] = True
        self.save_data()
        self.registry_updated.emit()

    def mark_account_valid(self, platform: str, account_id: str = None):
        """
        當探測或下載成功時呼叫，標記當前帳號憑證有效。
        """
        self._check_daily_reset()
        acc = None
        if account_id:
            for a in self.get_accounts(platform):
                if a.get("id") == account_id:
                    acc = a
                    break
        if not acc:
            acc = self.get_active_account(platform)
        if not acc:
            return

        acc["is_expired"] = False
        self.save_data()
        self.registry_updated.emit()

    def get_available_account(self, platform: str) -> dict:
        """
        取得當前可用（憑證未過期且今日配額未用罄）的帳號。
        若啟用了 auto_rotate，且當前帳號已滿或失效，會自動輪替至下一個可用帳號！
        """
        self._check_daily_reset()
        accounts = self.get_accounts(platform)
        if not accounts:
            return None

        current = self.get_active_account(platform)
        if current and not current.get("is_exhausted") and not current.get("is_expired"):
            return current

        # Current is exhausted or expired, search for another available account
        for acc in accounts:
            if not acc.get("is_exhausted") and not acc.get("is_expired"):
                print(f"[account_manager] Auto-switching {platform} to valid account: {acc.get('name')} ({acc.get('id')})")
                self.set_active_account(platform, acc.get("id"))
                return acc

        return None # All accounts exhausted or expired

    def has_available_quota(self, platform: str) -> bool:
        """
        檢查該平台是否還有任一可用（未耗盡且未達每日上限）的帳號配額。
        """
        return self.get_available_account(platform) is not None

    def is_platform_exhausted(self, platform: str) -> bool:
        """
        檢查該平台是否所有帳號都已耗盡配額。
        """
        return not self.has_available_quota(platform)

    def get_total_remaining_quota(self, platform: str) -> tuple[int, int]:
        """
        回傳 (總剩餘可用次數, 所有帳號今日總配額)
        """
        self._check_daily_reset()
        accounts = self.get_accounts(platform)
        total_limit = sum(a.get("daily_limit", 25) for a in accounts)
        total_used = sum(min(a.get("quota_used_today", 0), a.get("daily_limit", 25)) for a in accounts)
        remaining = max(0, total_limit - total_used)
        return remaining, total_limit


_shared_manager = None
_PROFILE_CACHE = {}

def get_account_manager() -> AccountManager:
    global _shared_manager
    if _shared_manager is None:
        _shared_manager = AccountManager()
    return _shared_manager

class DiscordRpcBlocker(QWebEngineUrlRequestInterceptor):
    """
    攔截並封鎖所有對本機 Discord 桌面端 RPC 端口 (127.0.0.1:6463-6472) 的請求。
    防止 Discord 網頁端自動偵測並強制連線到使用者桌面正在登入的應用程式帳號，
    確保使用者能自由輸入不同的帳號密碼進行登入。
    """
    def __init__(self, parent=None):
        super().__init__(parent)

    def interceptRequest(self, info):
        url = info.requestUrl()
        host = url.host().lower()
        port = url.port()
        if host in ("127.0.0.1", "localhost") and (6463 <= port <= 6472):
            info.block(True)


def get_webengine_profile(platform: str, acc_id: str, profile_dir: Path):
    """
    全域單例 WebEngineProfile 管理池。保證同一個目錄在整個進程生命週期中
    只有唯一的 QWebEngineProfile 實例，杜絕 Chromium SQLite 存取被拒 (0x5) 與 Cookies 衝突丟失。
    同時自動啟用 Discord RPC 阻斷防護，避免自動抓取桌面應用程式帳號。
    """
    from PySide6.QtWebEngineCore import QWebEngineProfile
    profile_dir = Path(profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    cache_key = str(profile_dir.resolve()).lower()
    if cache_key in _PROFILE_CACHE:
        return _PROFILE_CACHE[cache_key]

    prof_name = f"{platform}_{acc_id}"
    prof = QWebEngineProfile(prof_name)
    prof.setPersistentStoragePath(str(profile_dir))
    prof.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)

    # 掛載 Discord 本地 RPC 探測阻斷器（保持 Python 物件引用防止 GC）
    blocker = DiscordRpcBlocker(prof)
    prof._discord_rpc_blocker = blocker
    prof.setUrlRequestInterceptor(blocker)

    _PROFILE_CACHE[cache_key] = prof
    return prof
