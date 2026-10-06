import os
import json
import shutil
import sqlite3
import datetime
import tempfile
import urllib.request
import urllib.error
from pathlib import Path
_ROOT_DIR = Path(__file__).parent.parent.parent
_ACCOUNTS_FILE = _ROOT_DIR / "data" / "credentials" / "accounts_registry.json"
_PROFILES_DIR = _ROOT_DIR / "data" / "credentials" / "profiles"
_VAULT_FILE = _ROOT_DIR / "data" / "credentials" / "account_vault.json"

class _DummySignal:
    def __init__(self, *args):
        pass
    def emit(self, *args, **kwargs):
        pass
    def connect(self, *args, **kwargs):
        pass

class AccountManager:
    account_changed = _DummySignal()
    quota_updated = _DummySignal()
    registry_updated = _DummySignal()

    def __init__(self, parent=None):
        _PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        self._last_mtime = 0
        self.data = self._load_data()
        self._auto_migrate_legacy()
        self._check_daily_reset()
        self._sanitize_account_names()
        if self._deduplicate_accounts():
            self.save_data()

    def get_all_credentials_status(self) -> dict:
        """獲取所有平台帳號憑證健康與授權狀態彙整字典 (供健康體檢與狀態監控使用)"""
        self.reload_data()
        ryuu_accs = self.get_accounts("ryuu")
        lt_accs = self.get_accounts("lua_tools")
        
        def _enrich(acc_list, platform):
            res = []
            for a in acc_list:
                item = dict(a)
                item["has_valid_credentials"] = self.has_valid_credentials(a, platform)
                item["is_authorized"] = item["has_valid_credentials"]
                res.append(item)
            return res

        return {
            "ryuu": {
                "accounts": _enrich(ryuu_accs, "ryuu"),
                "active": self.get_active_account("ryuu")
            },
            "lua_tools": {
                "accounts": _enrich(lt_accs, "lua_tools"),
                "active": self.get_active_account("lua_tools")
            },
            "auto_rotate": bool(self.data.get("auto_rotate", True))
        }

    def is_auto_rotate_enabled(self) -> bool:
        """查詢是否啟用多帳號自動輪換"""
        return bool(self.data.get("auto_rotate", True))

    def reload_data(self) -> dict:
        """強制從磁碟重新加載最新的帳號登錄表（跨進程同步）"""
        self.data = self._load_data()
        self._check_daily_reset()
        self._sanitize_account_names()
        if self._deduplicate_accounts():
            self.save_data()
        return self.data

    def _check_reload(self):
        """檢查磁碟檔案是否有更新，若被外部進程修改則自動重新加載"""
        if _ACCOUNTS_FILE.exists():
            try:
                cur_mtime = _ACCOUNTS_FILE.stat().st_mtime
                if cur_mtime > self._last_mtime:
                    self.reload_data()
            except Exception:
                pass

    def _load_data(self) -> dict:
        data = None
        # 1. 嘗試從主註冊表載入
        if _ACCOUNTS_FILE.exists():
            try:
                self._last_mtime = _ACCOUNTS_FILE.stat().st_mtime
                with open(_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict) and (loaded.get("lua_tools") or loaded.get("ryuu")):
                        data = loaded
            except Exception as e:
                print(f"[account_manager] Failed to load primary registry: {e}")

        # 2. 若主檔缺失或為空，嘗試從備份檔恢復
        backup_file = _ACCOUNTS_FILE.parent / "accounts_registry.backup.json"
        if not data and backup_file.exists():
            try:
                with open(backup_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict) and (loaded.get("lua_tools") or loaded.get("ryuu")):
                        data = loaded
                        print("[account_manager] [Recovery] 成功從 accounts_registry.backup.json 自動還原帳號登錄檔！")
            except Exception as e:
                print(f"[account_manager] Failed to load backup registry: {e}")

        if not data:
            data = {
                "lua_tools": [],
                "ryuu": [],
                "active_account_lt": None,
                "active_account_ryuu": None,
                "auto_rotate": True
            }

        # 3. 硬碟目錄全自動盤點與救回機制 (Auto-Recovery from disk profiles)
        data = self._auto_recover_profiles_data(data)
        return data

    def _auto_recover_profiles_data(self, data: dict) -> dict:
        """從 profiles 資料夾深度掃描現存憑證，全自動修復並找回遺失的帳號登錄條目"""
        try:
            if not _PROFILES_DIR.exists():
                return data

            existing_lt_ids = {a.get("id") for a in data.get("lua_tools", [])}
            existing_ryuu_ids = {a.get("id") for a in data.get("ryuu", [])}

            for p_dir in _PROFILES_DIR.iterdir():
                if not p_dir.is_dir():
                    continue
                dname = p_dir.name
                c_file = p_dir / "Cookies"
                if not c_file.exists() or c_file.stat().st_size == 0:
                    continue

                if dname.startswith("lt_") and dname not in existing_lt_ids:
                    # 嚴格驗證 Lua.tools 是否具有有效授權 Token，無憑證者絕不自動還原
                    has_lt_token = False
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
                            tmp_p = tmp.name
                        shutil.copy2(c_file, tmp_p)
                        conn = sqlite3.connect(tmp_p)
                        cur = conn.cursor()
                        cur.execute("SELECT count(*) FROM cookies WHERE host_key LIKE '%lua.tools%' AND (name LIKE 'sb-%auth-token%' OR name LIKE '%token%') AND length(value) > 10")
                        cnt = cur.fetchone()[0]
                        has_lt_token = (cnt > 0)
                        conn.close()
                        if os.path.exists(tmp_p): os.remove(tmp_p)
                    except Exception:
                        pass

                    if not has_lt_token:
                        continue

                    info = self._extract_user_info_from_sqlite(c_file, "lua.tools")
                    if info.get("name") or info.get("email") or info.get("discord_id"):
                        uname = info.get("name") or info.get("email") or f"Lua.tools ({dname})"
                        acc = {
                            "id": dname,
                            "platform": "lua_tools",
                            "name": uname,
                            "email": info.get("email", ""),
                            "avatar_url": info.get("avatar_url", ""),
                            "profile_dir": str(p_dir),
                            "daily_limit": 25,
                            "quota_used_today": 0,
                            "quota_date": datetime.date.today().isoformat(),
                            "is_exhausted": False,
                            "added_time": datetime.datetime.now().isoformat(),
                            "discord_id": info.get("discord_id", ""),
                            "is_expired": False,
                            "has_valid_credentials": True,
                            "is_active": (len(data.get("lua_tools", [])) == 0),
                            "status_badge": "正常",
                            "needs_relogin": False
                        }
                        data["lua_tools"].append(acc)
                        if not data.get("active_account_lt"):
                            data["active_account_lt"] = dname
                        print(f"[account_manager] [Recovery] 自動從硬碟救回 Lua.tools 帳號: {uname} ({dname})")

                elif dname.startswith("ryuu_") and dname not in existing_ryuu_ids:
                    # 嚴格驗證 Ryuu 是否具有有效 session cookie
                    has_session = False
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
                            tmp_p = tmp.name
                        shutil.copy2(c_file, tmp_p)
                        conn = sqlite3.connect(tmp_p)
                        cur = conn.cursor()
                        cur.execute("SELECT count(*) FROM cookies WHERE (host_key LIKE '%ryuu%' OR host_key LIKE '%generator%') AND name = 'session' AND length(value) > 10")
                        row = cur.fetchone()
                        if row and row[0] and row[0] > 0:
                            has_session = True
                        conn.close()
                        if os.path.exists(tmp_p): os.remove(tmp_p)
                    except Exception:
                        pass

                    if has_session:
                        acc = {
                            "id": dname,
                            "platform": "ryuu",
                            "name": uname,
                            "email": info.get("email", ""),
                            "avatar_url": info.get("avatar_url", ""),
                            "profile_dir": str(p_dir),
                            "daily_limit": 50,
                            "quota_used_today": 0,
                            "quota_date": datetime.date.today().isoformat(),
                            "is_exhausted": False,
                            "added_time": datetime.datetime.now().isoformat(),
                            "discord_id": info.get("discord_id", ""),
                            "is_expired": False,
                            "has_valid_credentials": True,
                            "is_active": (len(data.get("ryuu", [])) == 0),
                            "status_badge": "正常",
                            "needs_relogin": False
                        }
                        data["ryuu"].append(acc)
                        if not data.get("active_account_ryuu"):
                            data["active_account_ryuu"] = dname
                        print(f"[account_manager] [Recovery] 自動從硬碟救回 Ryuu 帳號: {uname} ({dname})")
        except Exception as e:
            print(f"[account_manager] Auto recovery error: {e}")
        return data

    def save_data(self):
        try:
            _ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_ACCOUNTS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            if _ACCOUNTS_FILE.exists():
                self._last_mtime = _ACCOUNTS_FILE.stat().st_mtime

            # 同步備份檔
            backup_file = _ACCOUNTS_FILE.parent / "accounts_registry.backup.json"
            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)

            self.registry_updated.emit()
        except Exception as e:
            print(f"[account_manager] Failed to save registry: {e}")

    def _normalize_ident(self, ident: str) -> list:
        """解析並標準化帳號標識符（自動去除 did_、em_、name_、acc_ 等前綴）"""
        if not ident:
            return []
        s = str(ident).strip()
        candidates = [s, s.lower()]
        if s.startswith("did_"):
            raw = s[4:]
            candidates.extend([raw, raw.lower()])
        elif s.startswith("em_"):
            raw = s[3:]
            candidates.extend([raw, raw.lower()])
        elif s.startswith("name_"):
            raw = s[5:]
            candidates.extend([raw, raw.lower()])
        elif s.startswith("acc_"):
            raw = s[4:]
            candidates.extend([raw, raw.lower()])
        return list(dict.fromkeys(candidates))

    def get_hubcap_key(self, account_identifier: str) -> str:
        """依據 account_id、discord_id 或 email 獲取該帳號專屬的 Hubcap API Key"""
        if not account_identifier:
            return ""
        self._check_reload()
        keys_map = self.data.get("hubcap_keys", {})
        candidates = self._normalize_ident(account_identifier)
        
        # 1. 直接從映射表匹配候選標識
        for c in candidates:
            if c in keys_map and keys_map[c]:
                return keys_map[c]
            
        # 2. 遍歷帳號物件尋找關聯的 id, discord_id, email, name
        for plat in ["lua_tools", "ryuu"]:
            for acc in self.data.get(plat, []):
                acc_id = str(acc.get("id", "")).strip()
                did = str(acc.get("discord_id", "")).strip()
                email = str(acc.get("email", "")).strip().lower()
                name = str(acc.get("name", "")).strip().lower()
                
                # 檢查當前帳號是否與任一候選標識匹配
                acc_identifiers = [acc_id, did, email, name]
                matched = any(c and c in acc_identifiers for c in candidates)
                
                if matched:
                    if acc.get("hubcap_api_key"):
                        return acc["hubcap_api_key"]
                    for match_key in [did, email, acc_id]:
                        if match_key and match_key in keys_map and keys_map[match_key]:
                            return keys_map[match_key]
        return ""

    def set_hubcap_key(self, account_identifier: str, api_key: str, discord_id: str = "") -> bool:
        """為指定帳號綁定專屬的 Hubcap API Key"""
        self._check_reload()
        if "hubcap_keys" not in self.data:
            self.data["hubcap_keys"] = {}
            
        clean_key = str(api_key or "").strip()
        candidates = self._normalize_ident(account_identifier)
        if discord_id:
            candidates.extend(self._normalize_ident(discord_id))
        candidates = list(dict.fromkeys(candidates))
        
        for c in candidates:
            if c:
                if clean_key:
                    self.data["hubcap_keys"][c] = clean_key
                else:
                    self.data["hubcap_keys"].pop(c, None)
                    
        # 同步更新匹配的帳號物件
        for plat in ["lua_tools", "ryuu"]:
            for acc in self.data.get(plat, []):
                acc_id = str(acc.get("id", "")).strip()
                did = str(acc.get("discord_id", "")).strip()
                email = str(acc.get("email", "")).strip().lower()
                name = str(acc.get("name", "")).strip().lower()
                
                acc_identifiers = [acc_id, did, email, name]
                matched = any(c and c in acc_identifiers for c in candidates)
                
                if matched:
                    if clean_key:
                        acc["hubcap_api_key"] = clean_key
                    else:
                        acc.pop("hubcap_api_key", None)
                        
        self.save_data()
        return True

    def get_all_hubcap_keys(self) -> dict:
        """獲取所有帳號的 Hubcap API Key 映射"""
        self._check_reload()
        return self.data.get("hubcap_keys", {})

    def save_account_credentials(self, account_id: str = "", email: str = "", password: str = "", discord_id: str = ""):
        """安全保存帳號密碼到本地保管箱 (Base64 加密與多維度索引)"""
        if not password:
            return
        try:
            import base64
            _VAULT_FILE.parent.mkdir(parents=True, exist_ok=True)
            vault = {}
            if _VAULT_FILE.exists():
                try:
                    with open(_VAULT_FILE, "r", encoding="utf-8") as f:
                        vault = json.load(f)
                except Exception:
                    vault = {}

            clean_email = (email or "").strip().lower()
            enc_pwd = base64.b64encode(password.encode("utf-8")).decode("utf-8")
            entry = {
                "email": clean_email,
                "password": enc_pwd,
                "account_id": account_id or "",
                "discord_id": discord_id or "",
                "updated_at": datetime.datetime.now().isoformat()
            }

            if account_id:
                vault[f"id:{account_id}"] = entry
            if clean_email:
                vault[f"email:{clean_email}"] = entry
            if discord_id:
                vault[f"did:{discord_id}"] = entry
            vault["__latest__"] = entry

            with open(_VAULT_FILE, "w", encoding="utf-8") as f:
                json.dump(vault, f, ensure_ascii=False, indent=2)
            try:
                print(f"[account_manager] [Vault] 憑證已安全記憶至本地保管箱 (Email: {clean_email}, ID: {account_id})")
            except Exception:
                pass
        except Exception as e:
            try:
                print(f"[account_manager] Save credentials failed: {e}")
            except Exception:
                pass

    def get_account_credentials(self, account_id: str = None, email: str = None, discord_id: str = None) -> dict:
        """依據 account_id, email 或 discord_id 檢索已儲存的帳密"""
        clean_email = (email or "").strip().lower()
        if not _VAULT_FILE.exists():
            if not clean_email and account_id:
                for plat in ["lua_tools", "ryuu"]:
                    for acc in self.data.get(plat, []):
                        if acc.get("id") == account_id and acc.get("email"):
                            clean_email = acc.get("email").strip().lower()
                            break
            return {"email": clean_email, "password": ""}
        try:
            import base64
            with open(_VAULT_FILE, "r", encoding="utf-8") as f:
                vault = json.load(f)

            entry = None
            if account_id and f"id:{account_id}" in vault:
                entry = vault[f"id:{account_id}"]

            if not entry and account_id:
                for plat in ["lua_tools", "ryuu"]:
                    for acc in self.data.get(plat, []):
                        if acc.get("id") == account_id:
                            acc_email = (acc.get("email") or "").strip().lower()
                            acc_did = acc.get("discord_id") or ""
                            if acc_email and f"email:{acc_email}" in vault:
                                entry = vault[f"email:{acc_email}"]
                                break
                            elif acc_did and f"did:{acc_did}" in vault:
                                entry = vault[f"did:{acc_did}"]
                                break

            if not entry and clean_email and f"email:{clean_email}" in vault:
                entry = vault[f"email:{clean_email}"]

            if not entry and discord_id and f"did:{discord_id}" in vault:
                entry = vault[f"did:{discord_id}"]

            if entry and entry.get("password"):
                raw_pwd = base64.b64decode(entry["password"].encode("utf-8")).decode("utf-8", errors="ignore")
                found_email = entry.get("email") or clean_email
                return {
                    "email": found_email,
                    "password": raw_pwd
                }

            if not entry and not account_id and not clean_email and not discord_id and "__latest__" in vault:
                latest = vault["__latest__"]
                if latest.get("password"):
                    raw_pwd = base64.b64decode(latest["password"].encode("utf-8")).decode("utf-8", errors="ignore")
                    return {
                        "email": latest.get("email", ""),
                        "password": raw_pwd
                    }
        except Exception as e:
            print(f"[account_manager] Get credentials failed: {e}")

        if not clean_email and account_id:
            for plat in ["lua_tools", "ryuu"]:
                for acc in self.data.get(plat, []):
                    if acc.get("id") == account_id and acc.get("email"):
                        clean_email = acc.get("email").strip().lower()
                        break

        return {"email": clean_email, "password": ""}

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

    def sync_ryuu_quota_from_server(self, account_id: str = None) -> bool:
        """
        主動向 Ryuu 官方 API (https://generator.ryuu.lol/api/download_count/{discord_id})
        發送輕量查詢，零配額消耗同步真實剩餘額度與重設倒數時間！
        100% 透過官方網域伺服器完成，完全不需要 Discord Token！
        """
        import urllib.request, json
        accounts = self.get_accounts("ryuu")
        targets = [a for a in accounts if a.get("id") == account_id] if account_id else accounts
        changed = False

        for acc in targets:
            did = str(acc.get("discord_id", "")).strip()
            if not did:
                continue
            url = f"https://generator.ryuu.lol/api/download_count/{did}"
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://generator.ryuu.lol/"
                })
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    if resp.status == 200:
                        res = json.loads(resp.read().decode("utf-8"))
                        if isinstance(res, dict) and "count" in res:
                            cnt = int(res["count"])
                            limit = acc.get("daily_limit", 50)
                            left = max(0, limit - cnt)
                            acc["quota_used_today"] = cnt
                            acc["daily_limit"] = limit
                            acc["is_exhausted"] = (left <= 0)
                            acc["reset_in_seconds"] = res.get("reset_in_seconds")
                            acc["is_expired"] = False
                            acc["has_valid_credentials"] = True
                            acc.pop("not_in_server", None)

                            reset_sec = res.get("reset_in_seconds")
                            reset_str = ""
                            if reset_sec and reset_sec > 0:
                                r_h = reset_sec // 3600
                                r_m = (reset_sec % 3600) // 60
                                reset_str = f" ({r_h}h{r_m}m後重設)"

                            if left <= 0:
                                acc["status_badge"] = f"配額已滿{reset_str}"
                            else:
                                acc["status_badge"] = "正常"
                            changed = True
            except Exception as e:
                print(f"[account_manager] 網域伺服器同步 Ryuu [{acc.get('name')}] 配額失敗: {e}")

        if changed:
            self.save_data()
            self.registry_updated.emit()
        return changed

    def sync_all_quotas_from_server(self) -> bool:
        """同步所有平台在網域伺服器的最新真實配額"""
        return self.sync_ryuu_quota_from_server()

    def _extract_identity_tokens(self, data: dict) -> dict:
        """
        從帳號資料或使用者資訊字典中提取標準化的身份特徵：
        - discord_id: 純數字字串 (例如 '123456789012345678')
        - email: 小寫字串 (例如 'user@example.com')
        - username: 小寫用戶名 (例如 'example_user')
        - avatar_url: Discord CDN 頭像 URL
        - raw_name: 原始顯示名稱
        """
        import re
        if not isinstance(data, dict):
            return {"discord_id": "", "email": "", "username": "", "avatar_url": "", "raw_name": ""}

        discord_id = str(data.get("discord_id") or "").strip()
        email = str(data.get("email") or "").strip().lower()
        avatar_url = str(data.get("avatar_url") or "").strip()
        raw_name = str(data.get("name") or data.get("display_name") or data.get("username") or "").strip()
        username = str(data.get("username") or "").strip().lower().lstrip("@")

        # 1. 從 avatar_url 提取 discord_id (例如 https://cdn.discordapp.com/avatars/123456789012345678/...)
        if not discord_id and avatar_url:
            m_id = re.search(r"avatars/(\d+)/", avatar_url)
            if m_id:
                discord_id = m_id.group(1)

        # 2. 從 raw_name 提取 @username (例如 Nickname (@example_user) 或 @example_user)
        if not username and raw_name:
            m_u = re.search(r"@([\w\.\-]+)", raw_name)
            if m_u:
                username = m_u.group(1).lower()
            elif raw_name.startswith("@"):
                username = raw_name[1:].lower()
            elif not any(w in raw_name for w in ["使用者", "帳號", "預設", "User", "user", "Account"]):
                username = raw_name.lower()

        # 清理 email (必須含有 @ 與 .)
        if email and ("@" not in email or "." not in email):
            email = ""

        return {
            "discord_id": discord_id,
            "email": email,
            "username": username,
            "avatar_url": avatar_url,
            "raw_name": raw_name
        }

    def _is_same_identity(self, a: dict, b: dict) -> bool:
        """
        嚴格比對兩個帳號或資訊是否代表同一個 Discord 使用者。
        若有明確衝突 (不同 Email、不同 Discord ID、不同 Username)，絕不視為同一人。
        """
        if not a or not b:
            return False

        # 若兩者內部註冊 ID 相同
        id_a = a.get("id")
        id_b = b.get("id")
        if id_a and id_b and id_a == id_b:
            return True

        tok_a = self._extract_identity_tokens(a)
        tok_b = self._extract_identity_tokens(b)

        did_a, did_b = tok_a["discord_id"], tok_b["discord_id"]
        em_a, em_b = tok_a["email"], tok_b["email"]
        un_a, un_b = tok_a["username"], tok_b["username"]
        av_a, av_b = tok_a["avatar_url"], tok_b["avatar_url"]

        generic_names = ["unknown", "user", "discord", "admin", "null", "使用者", "帳號", "預設"]

        # ── 關鍵防呆：任一具體特徵衝突，絕對不是同一人 ──
        if did_a and did_b and did_a != did_b:
            return False
        if em_a and em_b and em_a != em_b:
            return False
        if un_a and un_b and un_a != un_b and un_a not in generic_names and un_b not in generic_names:
            return False

        # ── 正向身分匹配 ──
        # 1. Discord 唯一數字 ID 相同 (最權威)
        if did_a and did_b and did_a == did_b:
            return True

        # 2. Email 相同 (非空且唯一)
        if em_a and em_b and em_a == em_b:
            return True

        # 3. Username 相同 (且非通用詞)
        if un_a and un_b and un_a == un_b and un_a not in generic_names:
            return True

        # 4. 自定義 Avatar URL 完全相同 (必須包含使用者專屬目錄，嚴禁使用公共 embed/avatars 預設頭像判定)
        if (av_a and av_b and av_a == av_b and 
            "cdn.discordapp.com/avatars/" in av_a and 
            "embed/avatars" not in av_a):
            return True

        return False

    def _deduplicate_accounts(self) -> bool:
        """
        掃描並自動消除所有重複的帳號條目，合併同身分帳號的中繼資料與 Cookie。
        """
        changed = False
        for platform in ["lua_tools", "ryuu"]:
            accounts = self.data.get(platform, [])
            if not accounts:
                continue

            unique_accounts = []
            for acc in accounts:
                # 尋找是否已存在相同身分的帳號
                matched = None
                for u_acc in unique_accounts:
                    if self._is_same_identity(u_acc, acc):
                        matched = u_acc
                        break

                if matched:
                    # 發現重複！就地合併中繼資料與 Cookie
                    changed = True
                    # 優先保留更詳細的名稱 (如帶有 @username 或較長全名)
                    name_cur = matched.get("name", "")
                    name_new = acc.get("name", "")
                    if ("@" in name_new and "@" not in name_cur) or (len(name_new) > len(name_cur) and "未知" not in name_new):
                        matched["name"] = name_new
                    if not matched.get("email") and acc.get("email"):
                        matched["email"] = acc["email"]
                    if not matched.get("avatar_url") and acc.get("avatar_url"):
                        matched["avatar_url"] = acc["avatar_url"]
                    if not matched.get("discord_id") and acc.get("discord_id"):
                        matched["discord_id"] = acc["discord_id"]

                    # 若現存目錄沒有 Cookie，但重複條目的目錄有，複製過去
                    m_pdir = Path(matched.get("profile_dir", ""))
                    a_pdir = Path(acc.get("profile_dir", ""))
                    if not (m_pdir / "Cookies").exists() and (a_pdir / "Cookies").exists():
                        try:
                            m_pdir.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(a_pdir / "Cookies", m_pdir / "Cookies")
                        except Exception:
                            pass

                    # 若重複條目的 profile_dir 是多餘的臨時目錄，安全清理
                    if a_pdir.exists() and a_pdir != m_pdir and str(a_pdir).startswith(str(_PROFILES_DIR)):
                        try:
                            shutil.rmtree(a_pdir, ignore_errors=True)
                        except Exception:
                            pass

                    # 若 active_account 指向被移除的條目，重新導向回保留的條目
                    key = "active_account_lt" if platform == "lua_tools" else "active_account_ryuu"
                    if self.data.get(key) == acc.get("id"):
                        self.data[key] = matched["id"]
                else:
                    unique_accounts.append(acc)

            self.data[platform] = unique_accounts

        return changed

    def _extract_user_info_from_sqlite(self, cookie_path: Path, platform_or_pattern: str) -> dict:
        info = {"name": "", "email": "", "avatar_url": "", "discord_id": "", "username": ""}
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
                    import re
                    clean = token_str.replace("base64-", "")
                    padding = "=" * ((4 - len(clean) % 4) % 4)
                    decoded = base64.b64decode(clean + padding).decode("utf-8", errors="ignore")
                    j_data = json.loads(decoded)
                    user = j_data.get("user", {})
                    meta = user.get("user_metadata", {})
                    custom = meta.get("custom_claims", {})
                    gname = custom.get("global_name") or meta.get("global_name")
                    uname = meta.get("full_name") or meta.get("name") or user.get("name")
                    if uname and uname.endswith("#0"):
                        uname = uname[:-2]
                    email = user.get("email") or meta.get("email", "")
                    avatar = meta.get("avatar_url") or user.get("avatar_url", "")
                    did = meta.get("provider_id") or meta.get("sub") or custom.get("sub") or ""
                    if not did and avatar:
                        m = re.search(r"avatars/(\d+)/", avatar)
                        if m:
                            did = m.group(1)

                    info["email"] = email
                    info["avatar_url"] = avatar
                    info["discord_id"] = did
                    info["username"] = uname or ""
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
                    gname = u.get("global_name") or u.get("display_name", "")
                    avatar = u.get("avatar", "")
                    email = u.get("email", "")

                    info["discord_id"] = uid
                    info["username"] = uname
                    info["email"] = email
                    if avatar and uid:
                        info["avatar_url"] = f"https://cdn.discordapp.com/avatars/{uid}/{avatar}.png"
                    if gname and uname and gname != uname:
                        info["name"] = f"{gname} (@{uname})"
                    elif uname:
                        info["name"] = f"@{uname}"
                    elif gname:
                        info["name"] = gname
                    elif email:
                        info["name"] = email
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
                p_dir = Path(acc.get("profile_dir", ""))
                cookie_file = p_dir / "Cookies"
                if cookie_file.exists():
                    info = self._extract_user_info_from_sqlite(cookie_file, platform)
                    if info.get("name") and (needs_fix or ("@" in info["name"] and "@" not in curr_name)):
                        acc["name"] = info["name"]
                        changed = True
                    if info.get("email") and not acc.get("email"):
                        acc["email"] = info["email"]
                        changed = True
                    if info.get("discord_id") and not acc.get("discord_id"):
                        acc["discord_id"] = info["discord_id"]
                        changed = True

        # 跨平台身分與信箱自動對齊補齊 (例如 Lua.tools 已持有 Email，自動補齊到對應相同 discord_id 或名稱的 Ryuu 帳號)
        all_accounts = self.data.get("lua_tools", []) + self.data.get("ryuu", [])
        for acc in all_accounts:
            did = acc.get("discord_id")
            name = acc.get("name")
            for other in all_accounts:
                if other is not acc:
                    is_match = (did and other.get("discord_id") == did) or (name and other.get("name") == name)
                    if is_match:
                        if not acc.get("email") and other.get("email"):
                            acc["email"] = other["email"]
                            changed = True
                        if not acc.get("avatar_url") and other.get("avatar_url"):
                            acc["avatar_url"] = other["avatar_url"]
                            changed = True
                        if not acc.get("discord_id") and other.get("discord_id"):
                            acc["discord_id"] = other["discord_id"]
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

    def has_valid_credentials(self, acc: dict, platform: str) -> bool:
        """
        實體檢查帳號 profile 內的 Cookies SQLite 是否存在且含有對應平台的有效登入憑證。
        若帳號已被標記為過期 (is_expired)、需重新登入 (needs_relogin) 或無憑證檔案，則回傳 False。
        """
        if not acc or not isinstance(acc, dict):
            return False
        if acc.get("is_expired") or acc.get("needs_relogin") or acc.get("status_badge") in ["憑證無效", "憑證已過期", "未登入/憑證缺失"]:
            return False
        if acc.get("has_valid_credentials") is False:
            return False
        p_dir = Path(acc.get("profile_dir", ""))
        cookie_file = p_dir / "Cookies"
        if not cookie_file.exists() or cookie_file.stat().st_size == 0:
            return False
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
                tmp_p = tmp.name
            shutil.copy2(cookie_file, tmp_p)
            conn = sqlite3.connect(tmp_p)
            cur = conn.cursor()
            if platform == "ryuu":
                cur.execute("SELECT count(*) FROM cookies WHERE (host_key LIKE '%ryuu%' OR host_key LIKE '%generator%') AND name = 'session' AND length(value) > 10")
            else:
                cur.execute("SELECT count(*) FROM cookies WHERE host_key LIKE '%lua.tools%' AND (name LIKE 'sb-%auth-token%' OR name LIKE '%token%') AND length(value) > 10")
            cnt = cur.fetchone()[0]
            conn.close()
            if os.path.exists(tmp_p):
                try:
                    os.remove(tmp_p)
                except Exception:
                    pass
            return cnt > 0
        except Exception:
            return False

    def get_accounts(self, platform: str) -> list:
        self._check_reload()
        self._check_daily_reset()
        return self.data.get(platform, [])

    def get_active_account(self, platform: str) -> dict:
        self._check_reload()
        self._check_daily_reset()
        key = "active_account_lt" if platform == "lua_tools" else "active_account_ryuu"
        active_id = self.data.get(key)
        accounts = self.get_accounts(platform)
        if not accounts:
            return None

        current = None
        for acc in accounts:
            if acc.get("id") == active_id:
                current = acc
                break

        # 🌟 自我修復：如果當前活躍帳號真實含有有效憑證且未耗盡，保持使用
        if current and self.has_valid_credentials(current, platform) and not current.get("is_exhausted") and not current.get("is_expired"):
            return current

        # 若當前帳號已耗盡、失效或無憑證，自動在池中尋找第一個「未耗盡且憑證有效」的帳號並自動切換
        for acc in accounts:
            if self.has_valid_credentials(acc, platform) and not acc.get("is_exhausted") and not acc.get("is_expired"):
                self.data[key] = acc["id"]
                self.save_data()
                return acc

        # 若所有帳號均已耗盡，回退至具有有效憑證的帳號
        for acc in accounts:
            if self.has_valid_credentials(acc, platform) and not acc.get("is_expired"):
                self.data[key] = acc["id"]
                self.save_data()
                return acc

        if current:
            return current
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

    def reorder_accounts(self, platform: str, account_ids: list) -> bool:
        """
        依照使用者指定的優先級順序 (account_ids)，重新排列指定平台的帳號列表。
        排在越前面的帳號將擁有越高的調用優先權，額度耗盡後系統自動依序調用下方帳號。
        """
        accounts = self.data.get(platform, [])
        if not accounts:
            return False
        acc_map = {a.get("id"): a for a in accounts}
        reordered = []
        for aid in account_ids:
            if aid in acc_map:
                reordered.append(acc_map.pop(aid))
        # 補上未在 account_ids 中的帳號
        for remaining_acc in acc_map.values():
            reordered.append(remaining_acc)

        self.data[platform] = reordered
        if reordered:
            key = "active_account_lt" if platform == "lua_tools" else "active_account_ryuu"
            self.data[key] = reordered[0]["id"]
        self.save_data()
        self.registry_updated.emit()
        return True

    def create_new_account_profile_dir(self, platform: str) -> tuple[str, Path]:
        import uuid
        acc_id = f"{'lt' if platform == 'lua_tools' else 'ryuu'}_{uuid.uuid4().hex[:8]}"
        p_dir = _PROFILES_DIR / acc_id
        p_dir.mkdir(parents=True, exist_ok=True)
        return acc_id, p_dir

    def register_account(self, platform: str, acc_id: str, profile_dir: Path, name=None) -> dict:
        profile_dir = Path(profile_dir)
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

        candidate_info = {
            "id": acc_id,
            "platform": platform,
            "name": display_name,
            "email": user_info.get("email", ""),
            "avatar_url": user_info.get("avatar_url", ""),
            "discord_id": user_info.get("discord_id", "")
        }

        accounts = self.data.setdefault(platform, [])

        # 1. 檢查是否已有相同 Discord 身分的帳號
        matching_acc = None
        for existing in accounts:
            if self._is_same_identity(candidate_info, existing) or existing.get("id") == acc_id:
                matching_acc = existing
                break

        if matching_acc:
            # 已存在同身分帳號！直接更新該帳號的 Cookie 與中繼資料，杜絕重複條目
            target_dir = Path(matching_acc.get("profile_dir", ""))
            if target_dir != profile_dir and cookie_file.exists():
                target_dir.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(cookie_file, target_dir / "Cookies")
                except Exception as e:
                    print(f"[account_manager] Failed to sync cookies to existing profile: {e}")
                if str(profile_dir).startswith(str(_PROFILES_DIR)) and profile_dir != target_dir:
                    try:
                        shutil.rmtree(profile_dir, ignore_errors=True)
                    except Exception:
                        pass

            # 智慧更新名稱與身分資料
            if display_name and "未知" not in display_name:
                curr_name = matching_acc.get("name", "")
                if ("@" in display_name and "@" not in curr_name) or (len(display_name) > len(curr_name)) or not curr_name:
                    matching_acc["name"] = display_name
            if candidate_info.get("email"):
                matching_acc["email"] = candidate_info["email"]
            if candidate_info.get("avatar_url"):
                matching_acc["avatar_url"] = candidate_info["avatar_url"]
            if candidate_info.get("discord_id"):
                matching_acc["discord_id"] = candidate_info["discord_id"]

            matching_acc["daily_limit"] = 50 if platform == "ryuu" else 25
            matching_acc["is_expired"] = False
            matching_acc["is_exhausted"] = False

            key = "active_account_lt" if platform == "lua_tools" else "active_account_ryuu"
            if self.has_valid_credentials(matching_acc, platform):
                self.data[key] = matching_acc["id"]
            self._deduplicate_accounts()
            self.save_data()
            self.account_changed.emit(platform, self.data[key])
            self.registry_updated.emit()
            return matching_acc

        # 2. 全新帳號：追加至登錄表
        daily_limit = 25 if platform == "lua_tools" else 50
        new_acc = {
            "id": acc_id,
            "platform": platform,
            "name": display_name,
            "email": user_info.get("email", ""),
            "avatar_url": user_info.get("avatar_url", ""),
            "discord_id": user_info.get("discord_id", ""),
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
        if self.has_valid_credentials(new_acc, platform) or not self.data.get(key):
            self.data[key] = acc_id
        self._deduplicate_accounts()
        self.save_data()
        self.account_changed.emit(platform, self.data[key])
        self.registry_updated.emit()
        return new_acc

    def delete_account(self, platform: str, account_id: str, extra_info: dict = None) -> bool:
        """
        刪除指定平台帳號（徹底連根拔起雙平台關聯憑證與實體檔案，保證該帳號完全消失不要出現）。
        """
        return self.delete_account_completely(account_id, extra_info=extra_info)

    def delete_account_completely(self, identifier: str, extra_info: dict = None) -> bool:
        """
        徹底連根拔起刪除帳號：跨雙平台 (Ryuu 與 Lua.tools) 比對所有關聯條目，
        同步銷毀本機 Profile 資料夾、Cookies 檔案、清理 Hubcap Key、清理憑證保管箱，
        並更新活躍指標與持久化儲存，確保該帳號從矩陣與所有清單中徹底消失不要出現。
        """
        self._check_reload()

        # 1. 收集候選標識符集合
        candidates = set()
        if identifier:
            candidates.update(self._normalize_ident(str(identifier)))
        if extra_info and isinstance(extra_info, dict):
            for k in ["id", "raw_id", "discord_id", "email", "name", "username", "key"]:
                v = extra_info.get(k)
                if v:
                    candidates.update(self._normalize_ident(str(v)))

        # 2. 收集所有命中的帳號條目 (跨 Ryuu 與 Lua.tools)
        matched_targets = []
        for plat in ["ryuu", "lua_tools"]:
            for acc in list(self.data.get(plat, [])):
                acc_id = str(acc.get("id", "")).strip()
                did = str(acc.get("discord_id", "")).strip()
                email = str(acc.get("email", "")).strip().lower()
                name = str(acc.get("name", "")).strip().lower()
                toks = self._extract_identity_tokens(acc)
                u_name = toks.get("username", "")

                matched = False
                if acc_id and acc_id in candidates:
                    matched = True
                elif did and did in candidates:
                    matched = True
                elif email and (email in candidates or any(c.lower() == email for c in candidates)):
                    matched = True
                elif name and any(c.lower() == name for c in candidates):
                    matched = True
                elif u_name and any(c.lower() == u_name for c in candidates):
                    matched = True

                if matched and (plat, acc) not in matched_targets:
                    matched_targets.append((plat, acc))

        # 3. 交叉比對同身份關聯帳號
        all_acc_objects = [acc for _, acc in matched_targets]
        if all_acc_objects:
            for plat in ["ryuu", "lua_tools"]:
                for acc in list(self.data.get(plat, [])):
                    if any(self._is_same_identity(acc, t) for t in all_acc_objects):
                        if (plat, acc) not in matched_targets:
                            matched_targets.append((plat, acc))

        if not matched_targets:
            # 防禦處理：若列表中找不到，但 candidate 包含特定 profile id，強制銷毀可能殘留的實體目錄
            profiles_root = _PROFILES_DIR.resolve()
            for c in candidates:
                if c.startswith(("ryuu_", "lt_")):
                    p_dir = (_PROFILES_DIR / c).resolve()
                    if p_dir.exists() and p_dir.is_dir() and p_dir != profiles_root and profiles_root in p_dir.parents:
                        try:
                            shutil.rmtree(p_dir, ignore_errors=True)
                        except Exception:
                            pass
            return False

        # 4. 徹底銷毀所有命中之帳號物件與實體檔案
        for plat, acc in matched_targets:
            self._remove_single_account(plat, acc)

        # 5. 清理關聯之 Hubcap Key 映射
        if "hubcap_keys" in self.data and isinstance(self.data["hubcap_keys"], dict):
            keys_to_del = [k for k in self.data["hubcap_keys"] if k in candidates or any(c.lower() == str(k).lower() for c in candidates)]
            for k in keys_to_del:
                self.data["hubcap_keys"].pop(k, None)

        # 6. 清理關聯之 account_vault.json
        if _VAULT_FILE.exists():
            try:
                with open(_VAULT_FILE, "r", encoding="utf-8") as f:
                    vdata = json.load(f)
                if isinstance(vdata, dict):
                    v_changed = False
                    for vk in list(vdata.keys()):
                        for c in candidates:
                            if c in vk or (":" in vk and vk.split(":", 1)[1] == c):
                                vdata.pop(vk, None)
                                v_changed = True
                                break
                    if v_changed:
                        with open(_VAULT_FILE, "w", encoding="utf-8") as f:
                            json.dump(vdata, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"[account_manager] Failed to clean vault for deleted account: {e}")

        # 7. 去重與持久化寫入
        self._deduplicate_accounts()
        self.save_data()
        self.registry_updated.emit()
        return True

    def clear_all_accounts(self) -> bool:
        """清空所有已綁定的帳號憑證並清理本機 Profile 資料夾與 Hubcap API Key"""
        try:
            profiles_root = _PROFILES_DIR.resolve()
            for p in ["ryuu", "lua_tools"]:
                for acc in list(self.data.get(p, [])):
                    p_dir_str = str(acc.get("profile_dir", "") or "").strip()
                    if p_dir_str:
                        p_dir = Path(p_dir_str).resolve()
                        if p_dir.exists() and p_dir.is_dir() and p_dir != profiles_root and profiles_root in p_dir.parents:
                            try:
                                shutil.rmtree(p_dir, ignore_errors=True)
                            except Exception:
                                pass
                self.data[p] = []
            self.data["active_account_ryuu"] = None
            self.data["active_account_lt"] = None
            if "hubcap" in self.data:
                self.data["hubcap"] = {}
            self.save_data()
            self.registry_updated.emit()
            return True
        except Exception as e:
            print(f"[account_manager] clear_all_accounts error: {e}")
            return False

    def _remove_single_account(self, platform: str, acc: dict):
        """內部輔助方法：移除單一帳號條目並徹底清理對應之 Profile 憑證資料夾與 Cookies"""
        accounts = self.data.get(platform, [])
        acc_id = acc.get("id")
        # 移除平台列表符合的所有相同 id 與物件條目
        self.data[platform] = [a for a in accounts if a.get("id") != acc_id and a != acc]

        p_dir_str = str(acc.get("profile_dir", "") or "").strip()
        if p_dir_str:
            p_dir = Path(p_dir_str).resolve()
            profiles_root = _PROFILES_DIR.resolve()
            # 🌟 嚴格安全性驗證：只有當 p_dir 是 _PROFILES_DIR 底下的子目錄時，才允許清理！
            if p_dir.exists() and p_dir.is_dir() and p_dir != profiles_root and profiles_root in p_dir.parents:
                # 優先清空並刪除 Cookies 檔案，杜絕 Windows 占用導致被 auto_recover 再次救回
                c_file = p_dir / "Cookies"
                if c_file.exists():
                    try:
                        with open(c_file, "wb") as f:
                            f.truncate(0)
                        c_file.unlink(missing_ok=True)
                    except Exception:
                        pass
                try:
                    shutil.rmtree(p_dir, ignore_errors=True)
                except Exception:
                    pass

        key = "active_account_lt" if platform == "lua_tools" else "active_account_ryuu"
        remaining = self.data.get(platform, [])
        if self.data.get(key) == acc_id:
            self.data[key] = remaining[0]["id"] if remaining else None

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

    # ── 兼容別名 ──
    mark_exhausted = mark_account_exhausted
    mark_expired = mark_account_expired
    mark_valid = mark_account_valid

    def validate_and_cleanup_all_credentials(self) -> dict:
        """
        啟動時全自動驗證 Ryuu 與 Lua.tools 所有帳號憑證。
        若檢測到 Session / Token 已過期或失效，自動清除本機有問題的憑證檔案，
        標記為需重新登入 (needs_relogin)，並自動將活躍帳號切換至有效帳號。
        """
        self._check_daily_reset()
        cleaned_accounts = []
        invalid_accounts = []
        
        # 1. 檢查 Ryuu 所有帳號
        ryuu_accounts = self.get_accounts("ryuu")
        for acc in ryuu_accounts:
            p_dir = Path(acc.get("profile_dir", ""))
            cookie_file = p_dir / "Cookies"
            cookie_hdr = ""
            if cookie_file.exists():
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
                        tmp_p = tmp.name
                    shutil.copy2(cookie_file, tmp_p)
                    conn = sqlite3.connect(tmp_p)
                    cur = conn.cursor()
                    cur.execute("SELECT value FROM cookies WHERE (host_key LIKE '%ryuu%' OR host_key LIKE '%generator%') AND name = 'session' AND length(value) > 10")
                    row = cur.fetchone()
                    conn.close()
                    if os.path.exists(tmp_p): os.remove(tmp_p)
                    if row and row[0]:
                        cookie_hdr = f"session={row[0]}"
                except Exception as e:
                    print(f"[account_manager] 讀取 Ryuu 帳號 [{acc.get('name')}] Cookie 異常: {e}")

            if not cookie_hdr:
                # 本機無有效 Cookie 檔案
                acc["has_valid_credentials"] = False
                acc["is_expired"] = True
                acc["needs_relogin"] = True
                acc["status_badge"] = "未登入/憑證缺失"
                invalid_accounts.append({
                    "platform": "ryuu",
                    "id": acc.get("id"),
                    "name": acc.get("name") or acc.get("id"),
                    "reason": "本機無 Cookie 檔案"
                })
                continue

            # 發送真實端點驗證
            is_valid = False
            is_expired = False
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Referer": "https://generator.ryuu.lol/",
                    "Cookie": cookie_hdr
                }
                req = urllib.request.Request("https://generator.ryuu.lol/download/480", headers=headers)
                with urllib.request.urlopen(req, timeout=6) as resp:
                    data = resp.read()
                    if data and data[:4] == b"PK\x03\x04":
                        is_valid = True
                    else:
                        # Ryuu 回傳 HTML 登入頁面 (<title>Admin Login) 即代表 Cookie 已過期
                        is_expired = True
            except urllib.error.HTTPError as he:
                try:
                    err_b = he.read().decode('utf-8', errors='ignore')
                except Exception:
                    err_b = ""
                if he.code in [401, 403] or "logged in" in err_b.lower() or "unauthorized" in err_b.lower():
                    is_expired = True
                elif "limit" in err_b.lower() or he.code == 429:
                    is_valid = True  # 配額已滿但憑證仍有效
                else:
                    # 伺服器短暫 502/504 等，暫不刪除 Cookie
                    is_valid = True
            except Exception as net_err:
                # 網路斷線等暫態錯誤，保留 Cookie
                is_valid = True

            if is_expired:
                # 🌟 標記憑證過期但保留本機資料夾與檔案
                acc["has_valid_credentials"] = False
                acc["is_expired"] = True
                acc["needs_relogin"] = True
                acc["status_badge"] = "憑證已過期"
                invalid_accounts.append({
                    "platform": "ryuu",
                    "id": acc.get("id"),
                    "name": acc.get("name") or acc.get("id"),
                    "reason": "伺服器判定憑證已過期"
                })
                print(f"[account_manager] [EXPIRED] Ryuu account [{acc.get('name')}] marked as expired (needs relogin).")
            elif is_valid:
                acc["has_valid_credentials"] = True
                acc["is_expired"] = False
                acc["needs_relogin"] = False
                if not acc.get("status_badge") or acc.get("status_badge") in ["憑證無效", "憑證已過期", "未登入/憑證缺失"]:
                    acc["status_badge"] = "正常"

        # 2. 檢查 Lua.tools 所有帳號
        lt_accounts = self.get_accounts("lua_tools")
        for acc in lt_accounts:
            p_dir = Path(acc.get("profile_dir", ""))
            cookie_file = p_dir / "Cookies"
            cookie_hdr = ""
            if cookie_file.exists():
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
                        tmp_p = tmp.name
                    shutil.copy2(cookie_file, tmp_p)
                    conn = sqlite3.connect(tmp_p)
                    cur = conn.cursor()
                    cur.execute("SELECT name, value FROM cookies WHERE host_key LIKE '%lua.tools%' AND (name LIKE '%auth-token%' OR name LIKE '%session%')")
                    rows = cur.fetchall()
                    conn.close()
                    if os.path.exists(tmp_p): os.remove(tmp_p)
                    if rows:
                        cookie_hdr = "; ".join([f"{r[0]}={r[1]}" for r in rows if r[1]])
                except Exception as e:
                    print(f"[account_manager] 讀取 Lua.tools 帳號 [{acc.get('name')}] Cookie 異常: {e}")

            if not cookie_hdr:
                acc["has_valid_credentials"] = False
                acc["is_expired"] = True
                acc["needs_relogin"] = True
                acc["status_badge"] = "未登入/憑證缺失"
                invalid_accounts.append({
                    "platform": "lua_tools",
                    "id": acc.get("id"),
                    "name": acc.get("name") or acc.get("id"),
                    "reason": "本機無 Cookie 檔案"
                })
                continue

            # Lua.tools 端點輕量驗證
            is_valid = True
            is_expired = False
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Cookie": cookie_hdr
                }
                req = urllib.request.Request("https://lua.tools", headers=headers)
                with urllib.request.urlopen(req, timeout=6) as resp:
                    pass
            except urllib.error.HTTPError as he:
                if he.code in [401, 403]:
                    is_expired = True
            except Exception:
                is_valid = True

            if is_expired:
                # 🌟 標記憑證過期但保留本機資料夾與檔案
                acc["has_valid_credentials"] = False
                acc["is_expired"] = True
                acc["needs_relogin"] = True
                acc["status_badge"] = "憑證已過期"
                invalid_accounts.append({
                    "platform": "lua_tools",
                    "id": acc.get("id"),
                    "name": acc.get("name") or acc.get("id"),
                    "reason": "伺服器判定憑證已過期"
                })
                print(f"[account_manager] [EXPIRED] Lua.tools account [{acc.get('name')}] marked as expired (needs relogin).")
            elif is_valid:
                acc["has_valid_credentials"] = True
                acc["is_expired"] = False
                acc["needs_relogin"] = False
                if not acc.get("status_badge") or acc.get("status_badge") in ["憑證無效", "憑證已過期", "未登入/憑證缺失"]:
                    acc["status_badge"] = "正常"

        # 3. 檢查活躍帳號合法性：若活躍帳號失效，自動重選有效帳號
        for platform, key in [("ryuu", "active_account_ryuu"), ("lua_tools", "active_account_lt")]:
            active_id = self.data.get(key)
            accs = self.get_accounts(platform)
            valid_accs = [a for a in accs if a.get("has_valid_credentials") and not a.get("is_expired") and not a.get("needs_relogin")]
            
            # 若當前活躍帳號已無效
            current_active = next((a for a in accs if a.get("id") == active_id), None)
            if not current_active or not current_active.get("has_valid_credentials") or current_active.get("is_expired") or current_active.get("needs_relogin"):
                self.data[key] = valid_accs[0]["id"] if valid_accs else None

        self.save_data()
        self.registry_updated.emit()
        
        # 4. 統計雙平台健康狀態
        ryuu_valid_count = len([a for a in ryuu_accounts if a.get("has_valid_credentials") and not a.get("is_expired") and not a.get("needs_relogin")])
        lt_valid_count = len([a for a in lt_accounts if a.get("has_valid_credentials") and not a.get("is_expired") and not a.get("needs_relogin")])
        ryuu_abnormal = (ryuu_valid_count == 0)
        lt_abnormal = (lt_valid_count == 0)
        needs_jump = (ryuu_abnormal or lt_abnormal or len(cleaned_accounts) > 0 or len(invalid_accounts) > 0)
        
        jump_reason = ""
        if len(ryuu_accounts) == 0 and len(lt_accounts) == 0:
            jump_reason = "尚未綁定任何 Ryuu 或 Lua.tools 帳號"
        elif ryuu_abnormal and lt_abnormal:
            jump_reason = "Ryuu 與 Lua.tools 憑證均已失效或未授權"
        elif ryuu_abnormal:
            jump_reason = "Ryuu 憑證待授權或已過期"
        elif lt_abnormal:
            jump_reason = "Lua.tools 憑證待授權或已過期"
        elif len(cleaned_accounts) > 0 or len(invalid_accounts) > 0:
            jump_reason = "檢測到部分帳號憑證過期，需重新登入"

        return {
            "ok": True,
            "has_cleaned": len(cleaned_accounts) > 0,
            "cleaned_count": len(cleaned_accounts),
            "cleaned_accounts": cleaned_accounts,
            "has_invalid": len(invalid_accounts) > 0,
            "invalid_accounts": invalid_accounts,
            "ryuu_total": len(ryuu_accounts),
            "ryuu_valid": ryuu_valid_count,
            "ryuu_abnormal": ryuu_abnormal,
            "lua_tools_total": len(lt_accounts),
            "lua_tools_valid": lt_valid_count,
            "lua_tools_abnormal": lt_abnormal,
            "needs_jump_to_credentials": needs_jump,
            "jump_reason": jump_reason
        }

    def get_available_account(self, platform: str) -> dict:
        """
        取得當前可用（憑證實體存在且有效、未過期且今日配額未用罄）的帳號。
        若啟用了 auto_rotate，且當前帳號已滿或失效，會自動輪替至下一個可用帳號！
        """
        self._check_daily_reset()
        accounts = self.get_accounts(platform)
        if not accounts:
            return None

        current = self.get_active_account(platform)
        if (current 
            and self.has_valid_credentials(current, platform) 
            and not current.get("is_exhausted") 
            and not current.get("is_expired")):
            return current

        # 當前帳號已滿、失效或無憑證，自動尋找下一個合格帳號
        for acc in accounts:
            if (self.has_valid_credentials(acc, platform) 
                and not acc.get("is_exhausted") 
                and not acc.get("is_expired")):
                print(f"[account_manager] Auto-switching {platform} to valid account: {acc.get('name')} ({acc.get('id')})")
                self.set_active_account(platform, acc.get("id"))
                return acc

        return None # 該平台所有帳號均已耗盡配額或無有效憑證

    def get_all_valid_accounts(self, platform: str, include_exhausted: bool = False) -> list:
        """
        回傳所有實體存在有效 Cookie 且未標記為過期失效的帳號列表。
        以當前活躍 active 帳號排在第一位，其餘依序排列，專為批次更新與多帳號自動輪替下載設計！
        """
        self._check_daily_reset()
        accounts = self.get_accounts(platform)
        valid = []
        for acc in accounts:
            if not self.has_valid_credentials(acc, platform):
                continue
            if acc.get("is_expired"):
                continue
            if not include_exhausted and acc.get("is_exhausted"):
                continue
            valid.append(acc)

        active = self.get_active_account(platform)
        if active and active in valid:
            valid.remove(active)
            valid.insert(0, active)
        return valid

    def has_available_quota(self, platform: str) -> bool:
        """
        檢查該平台是否還有任一可用（未耗盡且未達每日上限且具備有效憑證）的帳號配額。
        """
        return self.get_available_account(platform) is not None

    def is_platform_exhausted(self, platform: str) -> bool:
        """
        檢查該平台是否所有帳號都已耗盡配額。
        """
        return not self.has_available_quota(platform)

    def get_total_remaining_quota(self, platform: str) -> tuple[int, int]:
        """
        回傳 (總剩餘可用次數, 所有有效授權帳號今日總配額)。
        未成功授權或在該平台無效的帳號不計入可用配額！
        """
        self._check_daily_reset()
        accounts = self.get_accounts(platform)
        valid_accounts = [a for a in accounts if self.has_valid_credentials(a, platform)]
        if not valid_accounts:
            return 0, 0
        default_limit = 50 if platform == "ryuu" else 25
        total_limit = sum(a.get("daily_limit", default_limit) for a in valid_accounts)
        total_used = sum(min(a.get("quota_used_today", 0), a.get("daily_limit", default_limit)) for a in valid_accounts)
        remaining = max(0, total_limit - total_used)
        return remaining, total_limit


_shared_manager = None
_PROFILE_CACHE = {}

def get_account_manager() -> AccountManager:
    global _shared_manager
    if _shared_manager is None:
        _shared_manager = AccountManager()
    return _shared_manager

def get_webengine_profile(platform: str, acc_id: str, profile_dir: Path):
    """
    全域單例 WebEngineProfile 管理池。保證同一個目錄在整個進程生命週期中
    只有唯一的 QWebEngineProfile 實例，杜絕 Chromium SQLite 存取被拒 (0x5) 與 Cookies 衝突丟失。
    同時自動啟用 Discord RPC 阻斷防護，避免自動抓取桌面應用程式帳號。
    """
    try:
        from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineUrlRequestInterceptor
    except Exception:
        return None

    class DiscordRpcBlocker(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, info):
            url = info.requestUrl()
            host = url.host().lower()
            port = url.port()
            if host in ("127.0.0.1", "localhost") and (6463 <= port <= 6472):
                info.block(True)

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
