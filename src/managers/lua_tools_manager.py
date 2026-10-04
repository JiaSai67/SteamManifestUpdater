import os
import json
from pathlib import Path
try:
    from PySide6.QtCore import QObject, Signal, QUrl, QTimer
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
except Exception:
    class QObject:
        def __init__(self, *args, **kwargs): pass
    class QWebEngineView: pass
    class QWebEngineProfile: pass
    class QWebEnginePage: pass
    class QUrl: pass
    class QTimer: pass
    def Signal(*args, **kwargs):
        class _DummySig:
            def emit(self, *a, **kw): pass
            def connect(self, *a, **kw): pass
        return _DummySig()

_shared_profile = None
_shared_client = None

def get_lua_tools_profile():
    global _shared_profile
    if _shared_profile is None:
        from managers import config_manager, account_manager
        mgr = account_manager.get_account_manager()
        active = mgr.get_active_account("lua_tools")
        if active and active.get("profile_dir") and Path(active.get("profile_dir")).exists():
            cache_dir = Path(active.get("profile_dir"))
        else:
            _config = config_manager.get_config()
            creds_dir = Path(_config.get("credentials_dir", str(config_manager._root_dir / "data" / "credentials")))
            cache_dir = creds_dir / "profiles" / "lt_default"
            if not cache_dir.exists():
                cache_dir = creds_dir / "lua_tools_profile"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        _shared_profile = QWebEngineProfile("LuaToolsProfile")
        _shared_profile.setPersistentStoragePath(str(cache_dir))
        _shared_profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        
    return _shared_profile

def has_saved_credentials() -> bool:
    """
    同步檢查本地是否已存在有效的持久化登入憑證 (SQLite Cookies)。
    提供 0ms 即時狀態反饋，避免等待 Chromium 網絡加載延遲。
    """
    try:
        from managers import account_manager
        mgr = account_manager.get_account_manager()
        accounts = mgr.get_accounts("lua_tools")
        if accounts:
            for acc in accounts:
                c_file = Path(acc.get("profile_dir", "")) / "Cookies"
                if c_file.exists():
                    return True

        from managers import config_manager
        _config = config_manager.get_config()
        creds_dir = Path(_config.get("credentials_dir", str(config_manager._root_dir / "data" / "credentials")))
        cookie_file = creds_dir / "lua_tools_profile" / "Cookies"
        if not cookie_file.exists():
            return False
        import sqlite3, shutil, tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
            tmp_path = tmp.name
        try:
            shutil.copy2(cookie_file, tmp_path)
            conn = sqlite3.connect(tmp_path)
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM cookies WHERE host_key LIKE '%lua.tools%' AND name LIKE 'sb-%auth-token%'")
            cnt = cur.fetchone()[0]
            conn.close()
            return cnt > 0
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
    except Exception:
        return False

class LuaToolsWebClient(QObject):
    ready = Signal()
    not_logged_in = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from managers import config_manager, account_manager
        self.config = config_manager.get_config()
        self.domain = self.config.get("luatools_domain", "https://lua.tools")
        self.acc_mgr = account_manager.get_account_manager()
        self.acc_mgr.account_changed.connect(self._on_account_changed)

        active = self.acc_mgr.get_active_account("lua_tools")
        if active and active.get("profile_dir") and Path(active.get("profile_dir")).exists():
            p_dir = Path(active.get("profile_dir"))
            acc_id = active.get("id", "default")
        else:
            p_dir = Path(config_manager._root_dir / "data" / "credentials" / "profiles" / "lt_default")
            acc_id = "default"
        p_dir.mkdir(parents=True, exist_ok=True)

        self.current_profile = QWebEngineProfile(f"LT_{acc_id}", self)
        self.current_profile.setPersistentStoragePath(str(p_dir))
        self.current_profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)

        self.page = QWebEnginePage(self.current_profile, self)
        self.view = QWebEngineView()
        self.view.setPage(self.page)
        self.view.hide()

        # 初始狀態直接讀取本地 SQLite 憑證，提供 0ms 反應
        self.is_logged_in = has_saved_credentials()
        self.has_checked = self.is_logged_in

        self.view.loadFinished.connect(self._on_load_finished)
        self.view.load(QUrl(f"{self.domain}/"))

    def _on_account_changed(self, platform: str, account_id: str):
        if platform == "lua_tools":
            acc = self.acc_mgr.get_active_account("lua_tools")
            if acc:
                self.switch_to_account(acc)

    def switch_to_account(self, account_dict_or_id):
        if not account_dict_or_id: return
        if isinstance(account_dict_or_id, str):
            for a in self.acc_mgr.get_accounts("lua_tools"):
                if a.get("id") == account_dict_or_id:
                    account_dict_or_id = a
                    break
        if not isinstance(account_dict_or_id, dict):
            return

        p_dir = Path(account_dict_or_id.get("profile_dir", ""))
        if not p_dir.exists():
            return

        acc_id = account_dict_or_id.get("id", "default")
        print(f"[lua_tools_manager] Switching WebEngine profile to: LT_{acc_id} ({p_dir})")
        
        self.current_profile = QWebEngineProfile(f"LT_{acc_id}", self)
        self.current_profile.setPersistentStoragePath(str(p_dir))
        self.current_profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)

        self.page = QWebEnginePage(self.current_profile, self)
        self.view.setPage(self.page)
        self.is_logged_in = True
        self.has_checked = True
        self.view.load(QUrl(f"{self.domain}/"))

    def _on_load_finished(self, ok):
        if not ok:
            if not self.is_logged_in:
                self.has_checked = True
                self.is_logged_in = False
                self.not_logged_in.emit()
            return
        self.check_login_now()

    def _on_cookie_check(self, has_auth):
        self.has_checked = True
        if has_auth or has_saved_credentials():
            self.is_logged_in = True
            self.ready.emit()
        else:
            self.is_logged_in = False
            self.not_logged_in.emit()

    def check_login_now(self):
        if has_saved_credentials():
            self.is_logged_in = True
            self.has_checked = True
            self.ready.emit()
        js = """
        (function() {
            var hasCookie = document.cookie.match(/sb-db-auth-token\\.\\d+=/) !== null;
            var hasLocal = Object.keys(localStorage || {}).some(function(k) { return k.indexOf('auth-token') !== -1; });
            return hasCookie || hasLocal;
        })();
        """
        self.page.runJavaScript(js, 0, self._on_cookie_check)

    def search_manifest(self, appid, callback):
        js = f"""
        window._luaToolsSearchRes = "__PENDING__";
        fetch('{self.domain}/api/manifest/check?appid={appid}')
            .then(r => r.json())
            .then(data => {{ window._luaToolsSearchRes = JSON.stringify(data); }})
            .catch(e => {{ window._luaToolsSearchRes = JSON.stringify({{error: e.message}}); }});
        """
        self.page.runJavaScript(js)
        self._poll_result('window._luaToolsSearchRes', 0, 40, lambda res: self._handle_search(res, callback))

    def probe_quota(self, callback=None):
        """
        發送輕量探測請求 (Try Quota)，即時檢測當前帳號的真實連線狀態、憑證有效性與剩餘配額。
        """
        def on_probe_res(res):
            status_info = {"platform": "lua_tools", "valid": False, "status": "unknown", "message": ""}
            if not res or not isinstance(res, dict):
                status_info["message"] = "連線逾時或無回應"
            elif res.get("unauthorized") or res.get("status") == 401 or "unauthorized" in str(res).lower():
                status_info["status"] = "expired"
                status_info["message"] = "❌ 憑證已過期或未登入 (401 Unauthorized)"
                from managers.account_manager import get_account_manager
                get_account_manager().mark_account_expired("lua_tools")
            elif res.get("rate_limited") or res.get("status") == 429 or "429" in str(res).lower() or "limit" in str(res).lower():
                status_info["status"] = "exhausted"
                status_info["message"] = "🔴 今日配額已用罄 (429 Rate Limit)"
                from managers.account_manager import get_account_manager
                get_account_manager().mark_account_exhausted("lua_tools")
            elif "error" in res:
                status_info["status"] = "error"
                status_info["message"] = f"⚠️ 伺服器回應: {res.get('error')}"
            else:
                status_info["valid"] = True
                status_info["status"] = "ready"
                status_info["message"] = "✅ 憑證有效，配額正常"
                from managers.account_manager import get_account_manager
                get_account_manager().mark_account_valid("lua_tools")

            if callback:
                callback(status_info)

        self.search_manifest("264710", on_probe_res)

    def _handle_search(self, res, callback):
        if res is None:
            callback({"error": "Request timed out"})
            return
        try:
            data = json.loads(res)
        except Exception as e:
            callback({"error": f"Parse error: {e}", "raw": res})
            return

        if isinstance(data, dict) and "error" in data:
            err_str = str(data.get("error", ""))
            status_code = data.get("status", 0)
            if status_code == 401 or "unauthorized" in err_str.lower() or "auth" in err_str.lower():
                from managers.account_manager import get_account_manager
                get_account_manager().mark_account_expired("lua_tools")
                callback({"error": "Lua.tools 憑證已過期/未登入 (401 Unauthorized)", "unauthorized": True, "status": 401})
                return
            if status_code == 429 or "429" in err_str or "limit" in err_str.lower() or "too many requests" in err_str.lower():
                from managers.account_manager import get_account_manager
                get_account_manager().mark_account_exhausted("lua_tools")
                callback({"error": "Lua.tools 今日配額已用罄 (429 Rate Limit)", "rate_limited": True, "status": 429})
                return

        # Success - mark account valid
        from managers.account_manager import get_account_manager
        get_account_manager().mark_account_valid("lua_tools")
        callback(data)

    def download_manifest(self, appid, source, encoded_game, callback):
        norm_map = {"ryuu": "Ryuu", "luie": "Luie", "sushi": "Sushi", "assiw": "Assiw"}
        norm_source = norm_map.get(str(source).lower(), str(source))
        js = f"""
        window._luaToolsDlRes = "__PENDING__";
        fetch('{self.domain}/api/manifest/download?appid={appid}&source={norm_source}&game_name={encoded_game}')
            .then(async r => {{
                if (!r.ok) {{
                    const text = await r.text();
                    window._luaToolsDlRes = JSON.stringify({{error: text, status: r.status}});
                }} else {{
                    const ct = r.headers.get('content-type') || '';
                    const buf = await r.arrayBuffer();
                    const bytes = new Uint8Array(buf);
                    let binary = '';
                    const len = bytes.byteLength;
                    const CHUNK_SIZE = 8192;
                    for (let i = 0; i < len; i += CHUNK_SIZE) {{
                        const sub = bytes.subarray(i, Math.min(i + CHUNK_SIZE, len));
                        binary += String.fromCharCode.apply(null, sub);
                    }}
                    const b64 = btoa(binary);
                    window._luaToolsDlRes = JSON.stringify({{
                        contentType: ct,
                        size: len,
                        b64: b64,
                        status: 200
                    }});
                }}
            }})
            .catch(e => {{ window._luaToolsDlRes = JSON.stringify({{error: e.message}}); }});
        """
        self.page.runJavaScript(js)
        self._poll_result('window._luaToolsDlRes', 0, 40, lambda res: self._handle_download(res, callback, appid, source, encoded_game))

    def _handle_download(self, res, callback, appid=None, source=None, encoded_game=None):
        if res is None:
            callback({"error": "Download timed out"})
            return
            
        try:
            data = json.loads(res)
        except Exception as e:
            callback({"error": f"Parse error: {e}", "raw": res})
            return

        if "error" in data:
            err_str = str(data.get("error", ""))
            status_code = data.get("status", 0)
            is_unauthorized = (
                status_code == 401
                or status_code == 403
                or "unauthorized" in err_str.lower()
                or "forbidden" in err_str.lower()
                or "login" in err_str.lower()
            )
            is_rate_limited = (
                status_code == 429
                or "429" in err_str
                or "too many requests" in err_str.lower()
                or "limit" in err_str.lower()
                or "quota" in err_str.lower()
                or "exhausted" in err_str.lower()
            )
            is_not_found = "not found" in err_str.lower() or status_code == 404

            if is_unauthorized:
                from managers.account_manager import get_account_manager
                mgr = get_account_manager()
                mgr.mark_account_expired("lua_tools")
                callback({"error": "Lua.tools 憑證已過期/未登入 (401 Unauthorized)", "unauthorized": True, "raw": err_str})
                return

            if is_rate_limited:
                from managers.account_manager import get_account_manager
                mgr = get_account_manager()
                mgr.mark_account_exhausted("lua_tools")
                if mgr.data.get("auto_rotate", True):
                    next_acc = mgr.get_available_account("lua_tools")
                    if next_acc:
                        print(f"[lua_tools_manager] 429 quota reached, auto-rotating to {next_acc.get('name')}")
                        self.switch_to_account(next_acc)
                        # Retry download with new account
                        if appid:
                            QTimer.singleShot(1500, lambda: self.download_manifest(appid, source, encoded_game, callback))
                            return

                callback({"error": "Lua.tools 今日配額已用罄 (429 Rate Limit)", "rate_limited": True, "raw": err_str})
                return

            if is_not_found:
                callback({"error": "Lua.tools 來源暫無此遊戲 Manifest", "not_found": True, "raw": err_str})
                return

            callback(data)
            return

        # Success - record quota usage and mark account valid
        from managers.account_manager import get_account_manager
        mgr = get_account_manager()
        mgr.mark_account_valid("lua_tools")
        mgr.record_quota_usage("lua_tools")

        b64 = data.get("b64")
        if not b64:
            text_data = data.get("data", "")
            callback({"success": True, "data": text_data, "lua_content": text_data, "manifests": {}})
            return

        import base64
        import io
        import zipfile
        try:
            raw_bytes = base64.b64decode(b64)
            if raw_bytes.startswith(b"PK\x03\x04"):
                manifests = {}
                lua_content = ""
                with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
                    lua_files = [f for f in z.namelist() if f.lower().endswith(".lua")]
                    for fn in z.namelist():
                        if fn.lower().endswith(".manifest"):
                            manifests[fn] = z.read(fn)
                    if lua_files:
                        lua_content = z.read(lua_files[0]).decode("utf-8", errors="ignore")
                
                callback({
                    "success": True,
                    "is_zip": True,
                    "data": lua_content,
                    "lua_content": lua_content,
                    "manifests": manifests
                })
            else:
                lua_content = raw_bytes.decode("utf-8", errors="ignore")
                callback({
                    "success": True,
                    "is_zip": False,
                    "data": lua_content,
                    "lua_content": lua_content,
                })
        except Exception as e:
            callback({"error": f"解碼或解壓縮失敗: {e}"})

    def _poll_result(self, var_name, attempts, max_attempts, callback):
        def check_val(val):
            if val != "__PENDING__":
                callback(val)
            elif attempts < max_attempts:
                QTimer.singleShot(250, lambda: self._poll_result(var_name, attempts + 1, max_attempts, callback))
            else:
                callback(None)
        self.page.runJavaScript(var_name, 0, check_val)

def get_shared_client(parent=None):
    global _shared_client
    if _shared_client is None:
        _shared_client = LuaToolsWebClient(None)
    return _shared_client
