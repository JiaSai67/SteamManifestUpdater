import os
import json
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QUrl, QTimer
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage

_shared_profile = None
_shared_client = None

def get_lua_tools_profile():
    global _shared_profile
    if _shared_profile is None:
        from managers import config_manager
        _config = config_manager.get_config()
        
        creds_dir = Path(_config.get("credentials_dir", str(config_manager._root_dir / "data" / "credentials")))
        cache_dir = creds_dir / "lua_tools_profile"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        _shared_profile = QWebEngineProfile("LuaToolsProfile")
        _shared_profile.setPersistentStoragePath(str(cache_dir))
        _shared_profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        
    return _shared_profile

class LuaToolsWebClient(QObject):
    ready = Signal()
    not_logged_in = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from managers import config_manager
        self.config = config_manager.get_config()
        self.domain = self.config.get("luatools_domain", "https://lua.tools")
        
        self.page = QWebEnginePage(get_lua_tools_profile(), self)
        self.view = QWebEngineView()
        self.view.setPage(self.page)
        self.view.hide()
        
        self.is_logged_in = False
        self.has_checked = False
        
        self.view.loadFinished.connect(self._on_load_finished)
        self.view.load(QUrl(f"{self.domain}/"))

    def _on_load_finished(self, ok):
        if not ok:
            self.has_checked = True
            self.is_logged_in = False
            self.not_logged_in.emit()
            return
        self.page.runJavaScript(
            "document.cookie.match(/sb-db-auth-token\\.\\d+=/) !== null", 
            0, 
            self._on_cookie_check
        )

    def _on_cookie_check(self, has_auth):
        self.has_checked = True
        if has_auth:
            self.is_logged_in = True
            self.ready.emit()
        else:
            self.is_logged_in = False
            self.not_logged_in.emit()

    def check_login_now(self):
        self.page.runJavaScript(
            "document.cookie.match(/sb-db-auth-token\\.\\d+=/) !== null", 
            0, 
            self._on_cookie_check
        )

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

    def _handle_search(self, res, callback):
        if res is None:
            callback({"error": "Request timed out"})
        else:
            try:
                data = json.loads(res)
                callback(data)
            except Exception as e:
                callback({"error": f"Parse error: {e}", "raw": res})

    def download_manifest(self, appid, source, encoded_game, callback):
        js = f"""
        window._luaToolsDlRes = "__PENDING__";
        fetch('{self.domain}/api/manifest/download?appid={appid}&source={source}&game_name={encoded_game}')
            .then(async r => {{
                if (!r.ok) {{
                    const text = await r.text();
                    window._luaToolsDlRes = JSON.stringify({{error: text}});
                }} else {{
                    const text = await r.text();
                    window._luaToolsDlRes = JSON.stringify({{data: text}});
                }}
            }})
            .catch(e => {{ window._luaToolsDlRes = JSON.stringify({{error: e.message}}); }});
        """
        self.page.runJavaScript(js)
        self._poll_result('window._luaToolsDlRes', 0, 40, lambda res: self._handle_download(res, callback))

    def _handle_download(self, res, callback):
        if res is None:
            callback({"error": "Download timed out"})
        else:
            try:
                data = json.loads(res)
                callback(data)
            except Exception as e:
                callback({"error": f"Parse error: {e}", "raw": res})

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
        _shared_client = LuaToolsWebClient(parent)
    return _shared_client
