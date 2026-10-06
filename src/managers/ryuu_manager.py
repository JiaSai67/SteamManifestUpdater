import os
import json
import urllib.request
from pathlib import Path
try:
    from PySide6.QtCore import QObject, Signal, QUrl, QTimer, QThread
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
except Exception:
    class QObject:
        def __init__(self, *args, **kwargs): pass
    class QThread:
        def __init__(self, *args, **kwargs): pass
    class QDialog:
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

_shared_ryuu_profile = None
_shared_ryuu_client = None

def get_ryuu_profile():
    from managers import config_manager, account_manager
    mgr = account_manager.get_account_manager()
    active = mgr.get_active_account("ryuu")
    if active and active.get("profile_dir") and Path(active.get("profile_dir")).exists():
        p_dir = Path(active.get("profile_dir"))
        acc_id = active.get("id", "default")
    else:
        _config = config_manager.get_config()
        creds_dir = Path(_config.get("credentials_dir", str(config_manager._root_dir / "data" / "credentials")))
        p_dir = creds_dir / "profiles" / "ryuu_default"
        acc_id = "default"
    return account_manager.get_webengine_profile("ryuu", acc_id, p_dir)

def has_saved_ryuu_credentials() -> bool:
    """
    同步檢查本地是否已存在有效的 Ryuu 持久化登入憑證 (SQLite Cookies)。
    提供 0ms 即時狀態反饋，避免等待 Chromium 網絡加載延遲。
    """
    try:
        from managers import account_manager
        mgr = account_manager.get_account_manager()
        accounts = mgr.get_accounts("ryuu")
        if accounts:
            for acc in accounts:
                c_file = Path(acc.get("profile_dir", "")) / "Cookies"
                if c_file.exists():
                    return True

        from managers import config_manager
        _config = config_manager.get_config()
        creds_dir = Path(_config.get("credentials_dir", str(config_manager._root_dir / "data" / "credentials")))
        cookie_file = creds_dir / "ryuu_profile" / "Cookies"
        if not cookie_file.exists():
            return False
        import sqlite3, shutil, tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
            tmp_path = tmp.name
        try:
            shutil.copy2(cookie_file, tmp_path)
            conn = sqlite3.connect(tmp_path)
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM cookies WHERE host_key LIKE '%ryuu%' OR host_key LIKE '%discord%'")
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

def fetch_ryuu_manifest_info(appid, timeout=10):
    """
    Query generator.ryuu.lol/manifestinfo/{appid} directly (No authentication required).
    專屬 Ryuu 公開資訊解析端點，0 消耗每日配額、0 延遲。
    回傳字典：
      {
         "found": bool,
         "default_branch": str,
         "files": list,
         "data": dict,
         "error": str (optional)
      }
    """
    url = f"https://generator.ryuu.lol/manifestinfo/{appid}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://generator.ryuu.lol/",
        "Accept": "application/json, text/plain, */*"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                files = []
                bm = data.get("branch_manifests", {})
                for b, bdata in bm.items():
                    if isinstance(bdata, dict):
                        files.extend(bdata.get("files", []))
                default_branch = data.get("default_branch", "public")
                has_files = len(files) > 0
                return {
                    "found": has_files,
                    "default_branch": default_branch,
                    "files": files,
                    "data": data
                }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"found": False, "error": "Game not found (404)"}
        return {"found": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        print(f"[ryuu_manager] fetch_manifest_info error for {appid}: {e}")
        return {"found": False, "error": str(e)}
    return {"found": False, "error": "Empty response"}


class RyuuCheckThread(QThread):
    result_ready = Signal(int, bool, dict)  # appid, found, info

    def __init__(self, appid, parent=None):
        super().__init__(parent)
        self.appid = int(appid)

    def run(self):
        info = fetch_ryuu_manifest_info(self.appid)
        self.result_ready.emit(self.appid, info.get("found", False), info)


class RyuuWebClient(QObject):
    ready = Signal()
    not_logged_in = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from managers import account_manager, config_manager
        self.domain = "https://generator.ryuu.lol"
        self.acc_mgr = account_manager.get_account_manager()
        self.acc_mgr.account_changed.connect(self._on_account_changed)

        active = self.acc_mgr.get_active_account("ryuu")
        if active and active.get("profile_dir") and Path(active.get("profile_dir")).exists():
            p_dir = Path(active.get("profile_dir"))
            acc_id = active.get("id", "default")
        else:
            p_dir = Path(config_manager._root_dir / "data" / "credentials" / "profiles" / "ryuu_default")
            acc_id = "default"
        p_dir.mkdir(parents=True, exist_ok=True)

        self.current_profile = account_manager.get_webengine_profile("ryuu", acc_id, p_dir)
        self.page = QWebEnginePage(self.current_profile, self)
        self.view = QWebEngineView()
        self.view.setPage(self.page)
        self.view.hide()

        # 初始狀態直接讀取本地 SQLite 憑證，提供 0ms 反應
        self.is_logged_in = has_saved_ryuu_credentials()
        self.has_checked = self.is_logged_in

        self.view.loadFinished.connect(self._on_load_finished)
        self.view.load(QUrl(f"{self.domain}/"))

    def _on_account_changed(self, platform: str, account_id: str):
        if platform == "ryuu":
            acc = self.acc_mgr.get_active_account("ryuu")
            if acc:
                self.switch_to_account(acc)

    def switch_to_account(self, account_dict_or_id):
        if not account_dict_or_id: return
        if isinstance(account_dict_or_id, str):
            for a in self.acc_mgr.get_accounts("ryuu"):
                if a.get("id") == account_dict_or_id:
                    account_dict_or_id = a
                    break
        if not isinstance(account_dict_or_id, dict):
            return

        p_dir = Path(account_dict_or_id.get("profile_dir", ""))
        if not p_dir.exists():
            return

        acc_id = account_dict_or_id.get("id", "default")
        from managers import account_manager
        print(f"[ryuu_manager] Switching WebEngine profile to: Ryuu_{acc_id} ({p_dir})")

        self.current_profile = account_manager.get_webengine_profile("ryuu", acc_id, p_dir)
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

    def check_login_now(self):
        js = """
        (function() {
            window._ryuuLoginRes = "__PENDING__";
            try {
                var hasProfile = document.getElementById('profile-menu') !== null || document.getElementById('profile-container') !== null;
                var dlEl = document.getElementById('downloads-left');
                var userId = dlEl ? dlEl.getAttribute('data-user-id') : null;
                var hasLogout = document.querySelector('a[href="/logout"]') !== null;
                var hasCookie = document.cookie.indexOf('session=') !== -1 || document.cookie.indexOf('auth=') !== -1;
                var loggedIn = hasProfile || (dlEl !== null) || hasLogout || (hasCookie && window.location.pathname === '/');
                
                if (userId) {
                    fetch('/api/download_count/' + userId)
                        .then(r => r.json())
                        .then(data => {
                            var cnt = (data && typeof data.count === 'number') ? data.count : null;
                            var left = (cnt !== null) ? Math.max(0, 50 - cnt) : null;
                            window._ryuuLoginRes = JSON.stringify({
                                logged_in: true,
                                downloads_left: left,
                                count: cnt,
                                reset_seconds: data.reset_in_seconds,
                                user_id: userId
                            });
                        })
                        .catch(e => {
                            window._ryuuLoginRes = JSON.stringify({
                                logged_in: loggedIn,
                                downloads_left: null,
                                user_id: userId
                            });
                        });
                } else {
                    window._ryuuLoginRes = JSON.stringify({
                        logged_in: loggedIn,
                        downloads_left: null,
                        user_id: null
                    });
                }
            } catch(err) {
                window._ryuuLoginRes = JSON.stringify({ logged_in: false, error: err.message });
            }
        })();
        """
        self.page.runJavaScript(js)
        self._poll_result("window._ryuuLoginRes", 0, 30, self._on_cookie_check)

    def _on_cookie_check(self, res_json):
        self.has_checked = True
        has_auth = False
        downloads_left = None
        user_id = None
        if isinstance(res_json, str):
            try:
                data = json.loads(res_json)
                has_auth = bool(data.get("logged_in"))
                downloads_left = data.get("downloads_left")
                user_id = data.get("user_id")
            except Exception:
                pass
        elif isinstance(res_json, bool):
            has_auth = res_json

        if has_auth or has_saved_ryuu_credentials():
            self.is_logged_in = True
            if downloads_left is not None:
                from managers.account_manager import get_account_manager
                get_account_manager().update_realtime_quota("ryuu", downloads_left, daily_limit=50)
                if downloads_left <= 0:
                    get_account_manager().mark_account_exhausted("ryuu")
                else:
                    get_account_manager().mark_account_valid("ryuu")
            self.ready.emit()
        else:
            self.is_logged_in = False
            self.not_logged_in.emit()

    def download_manifest(self, appid, branch="public", callback=None):
        """
        Ryuu 專屬雙軌下載流程：
        1. 先使用公開 0 消耗的 fetch_ryuu_manifest_info 進行預檢，確認是否有庫存與真實 default_branch。
        2. 若有庫存，再透過 WebEngine 專屬通道提取二進位 ZIP 串流，精確解壓縮。
        """
        import time
        # 1. 預檢
        info = fetch_ryuu_manifest_info(appid)
        if not info.get("found"):
            if callback:
                err_msg = info.get("error", "Ryuu 來源暫無此遊戲 Manifest (官方無檔案)")
                callback({"error": err_msg, "not_found": True})
            return

        real_branch = info.get("default_branch") or branch or "public"
        req_id = f"{appid}_{int(time.time() * 1000)}"
        var_name = f"_ryuuDl_{req_id}"
        
        # 🌟 Ryuu 官方標準下載端點為 /download?appid={appid} (若非 public 分支則帶 &branch={real_branch})，嚴格杜絕非標準之 file_type 參數 (防 HTTP 400)
        branch_param = f"&branch={real_branch}" if (real_branch and real_branch != "public") else ""
        dl_url = f"{self.domain}/download?appid={appid}{branch_param}"

        js = f"""
        window['{var_name}'] = "__PENDING__";
        fetch('{dl_url}', {{
            credentials: 'include'
        }})
            .then(async r => {{
                if (!r.ok) {{
                    const text = await r.text();
                    window['{var_name}'] = JSON.stringify({{error: text, status: r.status}});
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
                    window['{var_name}'] = JSON.stringify({{
                        contentType: ct,
                        size: len,
                        b64: b64,
                        status: 200
                    }});
                }}
            }})
            .catch(e => {{ window['{var_name}'] = JSON.stringify({{error: e.message}}); }});
        """
        self.page.runJavaScript(js)
        self._poll_result(f"window['{var_name}']", 0, 50, lambda res: self._handle_download(res, callback, appid, real_branch, var_name))

    def probe_quota(self, callback=None):
        """
        發送輕量探測請求 (Try Quota)，調用 Ryuu 原生官方 API (/api/download_count/{userId})，
        不消耗任何下載配額，精準檢測當前帳號的真實連線狀態、憑證有效性與剩餘配額。
        """
        js = """
        (function() {
            window._ryuuProbeRes = "__PENDING__";
            try {
                var dlEl = document.getElementById('downloads-left');
                var userId = dlEl ? dlEl.getAttribute('data-user-id') : null;
                var hasLogout = document.querySelector('a[href="/logout"]') !== null;
                var hasCookie = document.cookie.indexOf('session=') !== -1 || document.cookie.indexOf('auth=') !== -1;
                
                if (userId) {
                    fetch('/api/download_count/' + userId)
                        .then(r => r.json())
                        .then(data => {
                            window._ryuuProbeRes = JSON.stringify({
                                ok: true,
                                count: data.count,
                                reset_seconds: data.reset_in_seconds,
                                user_id: userId
                            });
                        })
                        .catch(e => {
                            window._ryuuProbeRes = JSON.stringify({ ok: false, error: e.message });
                        });
                } else if (hasLogout || hasCookie) {
                    window._ryuuProbeRes = JSON.stringify({ ok: true, count: null, note: "logged_in_no_uid" });
                } else {
                    window._ryuuProbeRes = JSON.stringify({ ok: false, unauthorized: true });
                }
            } catch(e) {
                window._ryuuProbeRes = JSON.stringify({ ok: false, error: e.message });
            }
        })();
        """
        def on_probe_done(res_str):
            status_info = {"platform": "ryuu", "valid": False, "status": "unknown", "message": ""}
            from managers.account_manager import get_account_manager
            mgr = get_account_manager()

            if not res_str or res_str == "__PENDING__":
                status_info["message"] = "連線逾時或無回應"
            else:
                try:
                    data = json.loads(res_str)
                    if data.get("ok"):
                        count = data.get("count")
                        secs = data.get("reset_seconds", 0)
                        if count is not None:
                            rem = max(0, 50 - count)
                            mgr.update_realtime_quota("ryuu", rem, daily_limit=50)
                            if rem <= 0:
                                status_info["valid"] = True
                                status_info["status"] = "exhausted"
                                time_str = f" (倒數 {secs//3600}時{(secs%3600)//60}分重設)" if secs else ""
                                status_info["message"] = f"🔴 今日配額已用罄 (0/50 次){time_str}"
                                mgr.mark_account_exhausted("ryuu")
                            else:
                                status_info["valid"] = True
                                status_info["status"] = "ready"
                                status_info["message"] = f"✅ Ryuu 憑證有效 (剩餘 {rem}/50 次)"
                                mgr.mark_account_valid("ryuu")
                        else:
                            status_info["valid"] = True
                            status_info["status"] = "ready"
                            status_info["message"] = "✅ Ryuu 憑證有效 (通訊正常)"
                            mgr.mark_account_valid("ryuu")
                    elif data.get("unauthorized"):
                        status_info["status"] = "expired"
                        status_info["message"] = "❌ 憑證已過期或未登入"
                        mgr.mark_account_expired("ryuu")
                    else:
                        status_info["status"] = "error"
                        status_info["message"] = f"⚠️ 探測回應: {data.get('error')}"
                except Exception as e:
                    status_info["message"] = f"解析回應失敗: {e}"

            if callback:
                callback(status_info)

        self.page.runJavaScript(js)
        self._poll_result("window._ryuuProbeRes", 0, 30, on_probe_done)

    def _handle_download(self, res, callback, appid=None, branch="public", var_name=None):
        if var_name:
            try:
                self.page.runJavaScript(f"delete window['{var_name}'];")
            except Exception:
                pass

        if not callback: return
        if not res or res == "__PENDING__":
            callback({"error": "Ryuu 下載逾時或無回應"})
            return
            
        try:
            data = json.loads(res)
        except Exception as e:
            callback({"error": f"解析回應失敗: {e}", "raw": str(res)})
            return

        if "error" in data:
            err_str = str(data.get("error", ""))
            status_code = data.get("status", 0)

            # 1. 每日配額用罄 (Daily download limit reached)
            is_quota_exhausted = "daily download limit" in err_str.lower() or "limit reached" in err_str.lower()
            
            # 2. 頻率限制 (Too many requests)
            is_rate_limited = (
                status_code == 429
                or "429" in err_str
                or "too many requests" in err_str.lower()
                or "slow down" in err_str.lower()
            )

            # 3. 遊戲未找到
            is_not_found = "game not found" in err_str.lower() or status_code == 404

            # 4. 憑證未登入 / 失效 (排除配額滿與限流)
            is_unauthorized = (
                not is_quota_exhausted
                and not is_rate_limited
                and not is_not_found
                and (
                    status_code == 401
                    or "must be logged in" in err_str.lower()
                    or "unauthorized" in err_str.lower()
                )
            )

            if is_quota_exhausted or is_rate_limited:
                from managers.account_manager import get_account_manager
                mgr = get_account_manager()
                if is_quota_exhausted:
                    mgr.update_realtime_quota("ryuu", 0, daily_limit=50)
                    mgr.mark_account_exhausted("ryuu")
                
                if mgr.data.get("auto_rotate", True):
                    next_acc = mgr.get_available_account("ryuu")
                    if next_acc:
                        print(f"[ryuu_manager] Quota/Rate limit reached, auto-rotating to {next_acc.get('name')}")
                        self.switch_to_account(next_acc)
                        if appid:
                            QTimer.singleShot(1500, lambda: self.download_manifest(appid, branch, callback))
                            return

                msg = "Ryuu 今日下載配額已用罄 (50/50)" if is_quota_exhausted else "Ryuu 發送頻率過快受限"
                callback({"error": msg, "rate_limited": True, "quota_exhausted": is_quota_exhausted, "raw": err_str})
                return

            if is_unauthorized:
                from managers.account_manager import get_account_manager
                mgr = get_account_manager()
                if "must be logged in" in err_str.lower():
                    mgr.mark_account_expired("ryuu")
                callback({"error": "Ryuu 憑證未登入或已失效", "unauthorized": True, "raw": err_str})
                return

            if is_not_found:
                from managers.account_manager import get_account_manager
                get_account_manager().mark_account_valid("ryuu")
                callback({"error": "來源暫無此遊戲 Manifest (Game not found)", "not_found": True, "raw": err_str})
                return

            callback(data)
            return

        # Success - record quota usage and mark account valid
        from managers.account_manager import get_account_manager
        mgr = get_account_manager()
        mgr.mark_account_valid("ryuu")
        mgr.record_quota_usage("ryuu")

        b64_str = data.get("b64", "")
        import base64
        import io
        import zipfile
        try:
            raw_bytes = base64.b64decode(b64_str)
            if raw_bytes.startswith(b"PK\x03\x04"):
                manifests = {}
                lua_content = ""
                with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
                    for fn in z.namelist():
                        if fn.lower().endswith(".manifest") or fn.lower().endswith(".lua"):
                            manifests[fn] = z.read(fn)
                        if fn.lower().endswith(".lua"):
                            lua_content = z.read(fn).decode("utf-8", errors="ignore")
                
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
                    "manifests": {}
                })
        except Exception as e:
            callback({"error": f"解碼或解壓縮失敗: {e}"})

    def _poll_result(self, js_expr, attempts, max_attempts, callback):
        def check_val(val):
            if val != "__PENDING__" and val is not None and str(val).strip() != "":
                callback(val)
            elif attempts < max_attempts:
                QTimer.singleShot(250, lambda: self._poll_result(js_expr, attempts + 1, max_attempts, callback))
            else:
                callback(None)
        self.page.runJavaScript(f"(typeof {js_expr} !== 'undefined') ? {js_expr} : '__PENDING__'", 0, check_val)


from PySide6.QtWidgets import QDialog, QVBoxLayout
from PySide6.QtCore import Qt

class RyuuLoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("登入 Ryuu Generator (Discord)")
        self.resize(1000, 750)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        try:
            from qfluentwidgets import isDarkTheme
            import ctypes
            hwnd = int(self.winId())
            value = ctypes.c_int(1 if isDarkTheme() else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.view = QWebEngineView(self)
        self.view.setPage(QWebEnginePage(get_ryuu_profile(), self.view))
        layout.addWidget(self.view)
        
        self.view.load(QUrl("https://generator.ryuu.lol/login"))
        self.view.loadFinished.connect(self.check_login)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_login)
        self.timer.start(2000)

    def check_login(self):
        js = """
        (function() {
            var hasLogin = document.querySelector('a[href="/login"]') !== null;
            var hasDownloadsLeft = document.getElementById('downloads-left') !== null;
            var hasLogout = document.querySelector('a[href="/logout"]') !== null;
            var hasSessionCookie = document.cookie.indexOf('session=') !== -1 || document.cookie.indexOf('auth=') !== -1;
            return (!hasLogin && (hasDownloadsLeft || hasLogout || hasSessionCookie)) || hasDownloadsLeft || hasLogout;
        })();
        """
        self.view.page().runJavaScript(js, 0, self._handle_check)

    def _handle_check(self, has_auth):
        if has_auth:
            self.timer.stop()
            self.accept()


def get_shared_ryuu_client(parent=None):
    global _shared_ryuu_client
    if _shared_ryuu_client is None:
        _shared_ryuu_client = RyuuWebClient(None)
    return _shared_ryuu_client

get_ryuu_manager = get_shared_ryuu_client

