from ui.theme_utils import get_state_color
import os
import json
import stat
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QUrl, QTimer, QObject, QThread
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from managers import lua_tools_manager
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QListWidget, QListWidgetItem, QLabel, QStackedWidget
)
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from qfluentwidgets import (
    PushButton, PrimaryPushButton, LineEdit, StrongBodyLabel, BodyLabel,
    InfoBar, InfoBarPosition, CardWidget, SubtitleLabel, ImageLabel, SegmentedWidget, CaptionLabel
)


_shared_profile = None


class LuaToolsLoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("登入 Lua.Tools")
        self.resize(800, 600)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        
        # Force title bar to match theme
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
        
        # Use persistent profile to save login state
        from managers.lua_tools_manager import get_lua_tools_profile
        profile = get_lua_tools_profile()
        page = QWebEnginePage(profile, self.view)
        self.view.setPage(page)
        
        layout.addWidget(self.view)
        
        self.view.load(QUrl("https://lua.tools/"))
        self.view.loadFinished.connect(self.check_login)
        
        # Also poll cookie every 2 seconds just in case
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_login)
        self.timer.start(2000)

    def check_login(self):
        self.view.page().runJavaScript(
            "document.cookie.match(/sb-db-auth-token\\.\\d+=/) !== null",
            0,
            self._handle_check
        )
        
    def _handle_check(self, has_auth):
        if has_auth:
            self.timer.stop()
            self.accept()


class RyuuLoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("登入 Ryuu Manifests (generator.ryuu.lol)")
        self.resize(850, 650)
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
        from managers.ryuu_manager import get_ryuu_profile
        profile = get_ryuu_profile()
        page = QWebEnginePage(profile, self.view)
        self.view.setPage(page)
        layout.addWidget(self.view)
        
        self.view.load(QUrl("https://generator.ryuu.lol/"))
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

class ImageLoadThread(QThread):
    image_ready = Signal(object) # None if failed, bytes if success
    info_ready = Signal(str)

    def __init__(self, appid, parent=None):
        super().__init__(parent)
        self.appid = appid

    def run(self):
        import urllib.request, json
        # 1. Get app details
        url = f"https://store.steampowered.com/api/appdetails?appids={self.appid}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as res:
                data = json.loads(res.read().decode('utf-8'))
                if str(self.appid) not in data or not data[str(self.appid)]['success']:
                    self.image_ready.emit(None)
                    self.info_ready.emit("")
                    return
                
                game_name = data[str(self.appid)]['data'].get('name', '')
                self.info_ready.emit(game_name)
                
                header_url = data[str(self.appid)]['data'].get('header_image', '')
                if not header_url:
                    self.image_ready.emit(None)
                    return
            
            # 2. Download image
            req = urllib.request.Request(header_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as res:
                img_data = res.read()
                self.image_ready.emit(img_data)
        except:
            self.image_ready.emit(None)
            self.info_ready.emit("")

class LuaToolsDownloaderWidget(QWidget):
    download_successful = Signal()
    
    def __init__(self, parent=None, lua_dir=""):
        super().__init__(parent)
        self.lua_dir = lua_dir
        
        from managers import ryuu_manager
        self.ryuu_client = ryuu_manager.get_shared_ryuu_client(self.parent())
        self.ryuu_client.ready.connect(self.on_ryuu_ready)
        self.ryuu_client.not_logged_in.connect(self.on_ryuu_not_logged_in)
        
        self.client = lua_tools_manager.get_shared_client(self.parent())
        self.client.ready.connect(self.on_client_ready)
        self.client.not_logged_in.connect(self.on_client_not_logged_in)

        self.of_thread = None
        
        self.initUI()
        
        if self.ryuu_client.has_checked:
            if self.ryuu_client.is_logged_in:
                self.on_ryuu_ready()
            else:
                self.on_ryuu_not_logged_in()
                
        if self.client.has_checked:
            if self.client.is_logged_in:
                self.on_client_ready()
            else:
                self.on_client_not_logged_in()
        
    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)

        # Top Area (5:5 ratio)
        top_layout = QHBoxLayout()
        top_layout.setSpacing(15)

        # Left side: Search (50%)
        search_card = CardWidget(self)
        search_layout = QHBoxLayout(search_card)
        search_layout.setContentsMargins(15, 12, 15, 12)
        
        self.search_input = LineEdit(self)
        self.search_input.setPlaceholderText("輸入 AppID 或商店網址...")
        self.search_input.setEnabled(False)
        self.search_btn = PrimaryPushButton("搜尋 Manifest", self)
        self.search_btn.setEnabled(False)
        self.search_btn.clicked.connect(self.do_search)
        
        search_layout.addWidget(self.search_input, 1)
        search_layout.addWidget(self.search_btn)
        top_layout.addWidget(search_card, 5)

        # Right side: Dual-Platform Login Status (50%)
        auth_card = CardWidget(self)
        auth_layout = QVBoxLayout(auth_card)
        auth_layout.setContentsMargins(14, 10, 14, 10)
        auth_layout.setSpacing(6)
        
        # Row 1: Ryuu
        r_layout = QHBoxLayout()
        r_layout.setContentsMargins(0, 0, 0, 0)
        r_title = StrongBodyLabel("1. Ryuu (generator.ryuu.lol):", self)
        self.ryuu_status_label = BodyLabel("檢查中...", self)
        self.ryuu_login_btn = PrimaryPushButton("登入 Ryuu", self)
        self.ryuu_login_btn.hide()
        self.ryuu_login_btn.clicked.connect(self.open_ryuu_login)
        self.ryuu_relogin_btn = PushButton("重登", self)
        self.ryuu_relogin_btn.hide()
        self.ryuu_relogin_btn.clicked.connect(self.open_ryuu_login)
        
        r_layout.addWidget(r_title)
        r_layout.addWidget(self.ryuu_status_label, 1)
        r_layout.addWidget(self.ryuu_login_btn)
        r_layout.addWidget(self.ryuu_relogin_btn)
        auth_layout.addLayout(r_layout)
        
        # Row 2: Lua.tools
        lt_layout = QHBoxLayout()
        lt_layout.setContentsMargins(0, 0, 0, 0)
        lt_title = StrongBodyLabel("2. Lua.tools (lua.tools 聚合):", self)
        self.status_label = BodyLabel("檢查中...", self)
        self.login_btn = PrimaryPushButton("登入 Lua.tools", self)
        self.login_btn.hide()
        self.login_btn.clicked.connect(self.open_login)
        self.relogin_btn = PushButton("重登", self)
        self.relogin_btn.hide()
        self.relogin_btn.clicked.connect(self.open_login)
        
        lt_layout.addWidget(lt_title)
        lt_layout.addWidget(self.status_label, 1)
        lt_layout.addWidget(self.login_btn)
        lt_layout.addWidget(self.relogin_btn)
        auth_layout.addLayout(lt_layout)

        # Row 3: Multi-Account & Quota
        acc_layout = QHBoxLayout()
        acc_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_acc_summary = CaptionLabel("多帳號配額 (Quota): 支援自動輪替", self)
        self.btn_acc_mgr = PushButton("👥 帳號管理 (Quota)", self)
        self.btn_acc_mgr.setFixedHeight(26)
        self.btn_acc_mgr.clicked.connect(self.open_account_manager)
        acc_layout.addWidget(self.lbl_acc_summary, 1)
        acc_layout.addWidget(self.btn_acc_mgr)
        auth_layout.addLayout(acc_layout)
        
        top_layout.addWidget(auth_card, 5)

        layout.addLayout(top_layout)
        
        # Content Split Layout
        split_layout = QHBoxLayout()
        layout.addLayout(split_layout, 1)

        # Left: Image Display Area
        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumWidth(300)
        self.image_label.hide()
        split_layout.addWidget(self.image_label, 7)

        self.img_thread = None

        # Right: Tabs
        right_panel = QWidget(self)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        self.source_tabs = SegmentedWidget(self)
        self.source_stack = QStackedWidget(self)
        
        right_layout.addWidget(self.source_tabs)
        right_layout.addWidget(self.source_stack, 1)
        split_layout.addWidget(right_panel, 3)
        
        # Tab 1: Lua
        self.lua_page = QWidget()
        lua_page_layout = QVBoxLayout(self.lua_page)
        lua_page_layout.setContentsMargins(0, 10, 0, 0)
        lua_page_layout.setSpacing(10)
        
        # Cards for Ryuu, Assiw, Luie, Sushi
        self.sources = {}
        for s in ["Ryuu", "Assiw", "Luie", "Sushi"]:
            card = CardWidget(self)
            c_layout = QHBoxLayout(card)
            
            # Name
            name_lbl = StrongBodyLabel(s, self)
            c_layout.addWidget(name_lbl)
            
            if s == "Ryuu":
                rec_lbl = BodyLabel("RECOMMENDED", self)
                rec_lbl.setStyleSheet(f"color: {get_state_color('accent')}; border: 1px solid {get_state_color('accent')}; border-radius: 4px; padding: 2px 4px; font-size: 10px;")
                c_layout.addWidget(rec_lbl)
            elif s == "Assiw":
                rec_lbl = BodyLabel("FALLBACK (備用)", self)
                rec_lbl.setStyleSheet(f"color: {get_state_color('warning')}; border: 1px solid {get_state_color('warning')}; border-radius: 4px; padding: 2px 4px; font-size: 10px;")
                c_layout.addWidget(rec_lbl)
                
            c_layout.addStretch(1)
            
            # Status
            status_lbl = BodyLabel("N/A", self)
            status_lbl.setStyleSheet(f"color: {get_state_color('muted')};")
            c_layout.addWidget(status_lbl)
            
            # Download Btn
            dl_btn = PrimaryPushButton("Download", self)
            dl_btn.setEnabled(False)
            dl_btn.clicked.connect(lambda checked=False, src=s: self._on_download_source_clicked(src))
            c_layout.addWidget(dl_btn)
            
            self.sources[s] = {"status": status_lbl, "btn": dl_btn}
            lua_page_layout.addWidget(card)

        # Lock Action Card in Lua Downloader page (防 401 封鎖)
        lock_card = CardWidget(self)
        lock_layout = QHBoxLayout(lock_card)
        lock_layout.setContentsMargins(12, 10, 12, 10)
        
        self.lbl_lock_notice = StrongBodyLabel("🛡️ 版本鎖定防護 (防 401 封鎖):", self)
        self.btn_toggle_lock = PushButton("請先搜尋遊戲", self)
        self.btn_toggle_lock.setEnabled(False)
        self.btn_toggle_lock.clicked.connect(self._toggle_current_lock)
        
        lock_layout.addWidget(self.lbl_lock_notice)
        lock_layout.addStretch(1)
        lock_layout.addWidget(self.btn_toggle_lock)
        lua_page_layout.addWidget(lock_card)

        lua_page_layout.addStretch(1)
        self.source_stack.addWidget(self.lua_page)
        
        # Tab 2: Online-Fix
        self.of_page = QWidget()
        of_page_layout = QVBoxLayout(self.of_page)
        of_page_layout.setContentsMargins(0, 10, 0, 0)
        of_page_layout.setSpacing(10)
        
        # Install buttons
        action_card = CardWidget(self)
        action_layout = QVBoxLayout(action_card)
        
        self.of_status_lbl = BodyLabel("請先搜尋遊戲以進行安裝", self)
        action_layout.addWidget(self.of_status_lbl)
        
        self.of_install_btn = PrimaryPushButton("自動下載並安裝 Online-Fix 補丁", self)
        self.of_install_btn.setEnabled(False)
        self.of_install_btn.clicked.connect(self._auto_install_of)
        action_layout.addWidget(self.of_install_btn)
        
        self.of_open_drive_btn = PushButton("🌐 瀏覽 Google Drive 共用補丁庫", self)
        self.of_open_drive_btn.clicked.connect(self._open_gdrive_folder)
        action_layout.addWidget(self.of_open_drive_btn)
        
        # Web Patch Sources
        web_source_card = CardWidget(self)
        web_source_layout = QVBoxLayout(web_source_card)
        web_source_title = StrongBodyLabel("🌐 外部補丁網頁檢查", self)
        web_source_layout.addWidget(web_source_title)
        
        self._of_url = None
        self._zg_url = None
        self.of_web_btn = PushButton("🌐 Online-Fix.me: 尚未檢查", self)
        self.of_web_btn.setEnabled(False)
        self.of_web_btn.clicked.connect(self._open_of_url)
        web_source_layout.addWidget(self.of_web_btn)
        
        self.zg_web_btn = PushButton("🌐 ZeiGames.com: 尚未檢查", self)
        self.zg_web_btn.setEnabled(False)
        self.zg_web_btn.clicked.connect(self._open_zg_url)
        web_source_layout.addWidget(self.zg_web_btn)
        
        action_layout.addWidget(web_source_card)
        
        of_page_layout.addWidget(action_card)
        of_page_layout.addStretch(1)
        self.source_stack.addWidget(self.of_page)
        
        self.source_tabs.addItem("lua", "Lua 下載", lambda: self.source_stack.setCurrentIndex(0))
        self.source_tabs.addItem("of", "Online-Fix 下載", lambda: self.source_stack.setCurrentIndex(1))
        self.source_tabs.setCurrentItem("lua")

    def load_game_image(self, appid):
        self.image_label.hide()
        if self.img_thread and self.img_thread.isRunning():
            self.img_thread.terminate()
        self.img_thread = ImageLoadThread(appid, self)
        self.img_thread.image_ready.connect(self.on_image_downloaded)
        self.img_thread.info_ready.connect(self.on_game_info_ready)
        self.img_thread.start()

    def on_game_info_ready(self, game_name):
        self.current_game_name = game_name
        if game_name:
            self.of_web_btn.setText("🌐 Online-Fix.me: ⏳ 搜尋中...")
            self.of_web_btn.setEnabled(False)
            self.zg_web_btn.setText("🌐 ZeiGames.com: ⏳ 搜尋中...")
            self.zg_web_btn.setEnabled(False)
            
            if hasattr(self, 'web_patch_thread') and self.web_patch_thread and self.web_patch_thread.isRunning():
                self.web_patch_thread.terminate()
            from api.web_patch_checker import WebPatchCheckThread
            self.web_patch_thread = WebPatchCheckThread(game_name, self)
            self.web_patch_thread.results_ready.connect(self._on_web_patch_results)
            self.web_patch_thread.start()
        else:
            self.of_web_btn.setText("🌐 Online-Fix.me: ❌ 無遊戲名稱")
            self.of_web_btn.setEnabled(False)
            self.zg_web_btn.setText("🌐 ZeiGames.com: ❌ 無遊戲名稱")
            self.zg_web_btn.setEnabled(False)

    def _open_of_url(self):
        if self._of_url:
            import webbrowser
            webbrowser.open(self._of_url)

    def _open_zg_url(self):
        if self._zg_url:
            import webbrowser
            webbrowser.open(self._zg_url)

    def _on_web_patch_results(self, res):
        self._of_url = res.get("onlinefix_url")
        self._zg_url = res.get("zeigames_url")
            
        if self._of_url:
            self.of_web_btn.setText("🌐 Online-Fix.me: ✅ 有補丁 (點擊前往)")
            self.of_web_btn.setEnabled(True)
        else:
            self.of_web_btn.setText("🌐 Online-Fix.me: ❌ 無對應網頁")
            self.of_web_btn.setEnabled(False)
            
        if self._zg_url:
            self.zg_web_btn.setText("🌐 ZeiGames.com: ✅ 有補丁 (點擊前往)")
            self.zg_web_btn.setEnabled(True)
        else:
            self.zg_web_btn.setText("🌐 ZeiGames.com: ❌ 無對應網頁")
            self.zg_web_btn.setEnabled(False)

    def _open_gdrive_folder(self):
        from managers import onlinefix_manager
        import webbrowser
        webbrowser.open(onlinefix_manager.GDRIVE_FOLDER_URL)

    def on_image_downloaded(self, data):
        if data:
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                pixmap = pixmap.scaledToWidth(600, Qt.SmoothTransformation)
                self.image_label.setPixmap(pixmap)
                self.image_label.show()
                return
        # If error or failed to load, hide the image label
        self.image_label.hide()
        
    def on_ryuu_ready(self):
        self.ryuu_status_label.setText("已登入 ✅")
        self.ryuu_status_label.setStyleSheet(f"color: {get_state_color('success')}; font-weight: bold;")
        self.ryuu_login_btn.hide()
        self.ryuu_relogin_btn.show()
        self._update_search_state()

    def on_ryuu_not_logged_in(self):
        self.ryuu_status_label.setText("未登入 ❌")
        self.ryuu_status_label.setStyleSheet(f"color: {get_state_color('error')}; font-weight: bold;")
        self.ryuu_login_btn.show()
        self.ryuu_relogin_btn.hide()
        self._update_search_state()

    def on_client_ready(self):
        self.status_label.setText("已登入 ✅")
        self.status_label.setStyleSheet(f"color: {get_state_color('success')}; font-weight: bold;")
        self.login_btn.hide()
        self.relogin_btn.show()
        self._update_search_state()

    def on_client_not_logged_in(self):
        self.status_label.setText("未登入 ❌")
        self.status_label.setStyleSheet(f"color: {get_state_color('error')}; font-weight: bold;")
        self.login_btn.show()
        self.relogin_btn.hide()
        self._update_search_state()

    def _update_search_state(self):
        has_any = (hasattr(self, 'ryuu_client') and self.ryuu_client.is_logged_in) or \
                  (hasattr(self, 'client') and self.client.is_logged_in)
        self.search_input.setEnabled(has_any)
        self.search_btn.setEnabled(has_any)

    def open_account_manager(self):
        from ui.account_manager_ui import MultiAccountManagerDialog
        dlg = MultiAccountManagerDialog(self)
        dlg.exec()
        if hasattr(self, 'client'):
            self.client.check_login_now()
        if hasattr(self, 'ryuu_client'):
            self.ryuu_client.check_login_now()

    def open_ryuu_login(self):
        self.open_account_manager()

    def open_login(self):
        self.open_account_manager()
            
    def _extract_appid(self, text):
        import re
        text = text.strip()
        if text.isdigit():
            return text
            
        # Try to extract from Steam Store URL format: /app/123456
        match = re.search(r'/app/(\d+)', text)
        if match:
            return match.group(1)
            
        return None

    def do_search(self):
        import re
        query = self.search_input.text().strip()
        if not query:
            return
            
        self.search_btn.setEnabled(False)
        self.search_btn.setText("搜尋中...")
        
        match = re.search(r'(?:app/|appid=)(\d+)', query.lower())
        appid = None
        if match:
            appid = match.group(1)
        elif query.isdigit():
            appid = query
            
        from ui.one_click_install_ui import SteamSearchThread
        if appid:
            self.steam_search_thread = SteamSearchThread(appid=appid)
        else:
            self.steam_search_thread = SteamSearchThread(query=query)
            
        self.steam_search_thread.result_ready.connect(self._on_steam_search_result)
        self.steam_search_thread.start()

    def _on_steam_search_result(self, result):
        if not result:
            self.search_btn.setEnabled(True)
            self.search_btn.setText("搜尋 Manifest")
            from qfluentwidgets import InfoBar
            InfoBar.error("錯誤", "找不到該遊戲名稱或 AppID", parent=self)
            return
            
        appid = int(result['id'])
        self.current_game_name = result.get('name', '')
        self.search_input.setText(str(appid))
        
        self.of_status_lbl.setText(f"檢查補丁來源中 (AppID: {appid})...")
        self.of_install_btn.setEnabled(False)

        self.current_appid = appid
        self.load_game_image(appid)
        
        self.client.search_manifest(appid, self.on_search_result)
        
        # Trigger background check for Ryuu Generator direct source
        self._check_ryuu_source(appid)

        # Trigger background check for Assiw downstream source
        self._check_assiw_source(appid)
        
        # Trigger background check for OF patch
        self._check_of_sources(appid)

        # Refresh Version Lock button
        self._refresh_lock_button()

    def _check_ryuu_source(self, appid):
        if "Ryuu" in self.sources:
            self.sources["Ryuu"]["status"].setText("檢查中...")
            self.sources["Ryuu"]["status"].setStyleSheet(f"color: {get_state_color('muted')};")
            self.sources["Ryuu"]["btn"].setEnabled(False)

        if hasattr(self, 'ryuu_check_thread') and self.ryuu_check_thread and self.ryuu_check_thread.isRunning():
            self.ryuu_check_thread.terminate()

        from managers.ryuu_manager import RyuuCheckThread
        self.ryuu_check_thread = RyuuCheckThread(appid, self)

        def _on_ryuu_done(res_appid, found, info):
            if self.current_appid != res_appid:
                return
            if "Ryuu" in self.sources:
                if found:
                    self.current_ryuu_info = info
                    f_count = len(info.get("files", []))
                    self.sources["Ryuu"]["status"].setText(f"AVAILABLE (Ryuu 官方 {f_count} 檔)")
                    self.sources["Ryuu"]["status"].setStyleSheet(f"color: {get_state_color('success')}; font-weight: bold;")
                    self.sources["Ryuu"]["btn"].setEnabled(True)
                else:
                    self.current_ryuu_info = None
                    curr_text = self.sources["Ryuu"]["status"].text()
                    if "AVAILABLE" not in curr_text:
                        self.sources["Ryuu"]["status"].setText("N/A")
                        self.sources["Ryuu"]["status"].setStyleSheet(f"color: {get_state_color('muted')};")
                        self.sources["Ryuu"]["btn"].setEnabled(False)

        self.ryuu_check_thread.result_ready.connect(_on_ryuu_done)
        self.ryuu_check_thread.start()

    def _check_assiw_source(self, appid):
        if "Assiw" in self.sources:
            self.sources["Assiw"]["status"].setText("檢查中...")
            self.sources["Assiw"]["status"].setStyleSheet(f"color: {get_state_color('muted')};")
            self.sources["Assiw"]["btn"].setEnabled(False)

        if hasattr(self, 'assiw_check_thread') and self.assiw_check_thread and self.assiw_check_thread.isRunning():
            self.assiw_check_thread.terminate()

        from managers.assiw_manager import AssiwCheckThread
        self.assiw_check_thread = AssiwCheckThread(appid, self)

        def _on_assiw_done(res_appid, supported):
            if self.current_appid != res_appid:
                return
            if "Assiw" in self.sources:
                if supported:
                    self.sources["Assiw"]["status"].setText("AVAILABLE")
                    self.sources["Assiw"]["status"].setStyleSheet(f"color: {get_state_color('success')}; font-weight: bold;")
                    self.sources["Assiw"]["btn"].setEnabled(True)
                else:
                    self.sources["Assiw"]["status"].setText("N/A")
                    self.sources["Assiw"]["status"].setStyleSheet(f"color: {get_state_color('muted')};")
                    self.sources["Assiw"]["btn"].setEnabled(False)

        self.assiw_check_thread.result_ready.connect(_on_assiw_done)
        self.assiw_check_thread.start()


    def _check_of_sources(self, appid):
        from managers import onlinefix_manager
        sources = onlinefix_manager.get_patch_sources(target_app_id=appid, target_app_name=self.current_game_name)
        source = sources.get(str(appid))
        
        # Check game installation
        game_dir_info = self._find_steam_game_dir(appid)
        is_installed = False
        if game_dir_info and game_dir_info[1]:
            try:
                flags = int(game_dir_info[1])
                if (flags & 4) == 4:
                    is_installed = True
            except:
                pass

        # Check patch status
        fix_status = onlinefix_manager.get_fix_status(appid)
        is_patched = "已安裝" in fix_status

        if source and (source.get('local_rar') or source.get('cloud_rar')):
            if is_patched:
                status_text = f"✅ 補丁可用，且此遊戲已打過補丁！ (AppID: {appid})"
                self.of_install_btn.setText("重新下載並覆蓋 Online-Fix 補丁")
            elif is_installed:
                status_text = f"✅ 補丁可用，且遊戲已安裝 (AppID: {appid})"
                self.of_install_btn.setText("自動下載並安裝 Online-Fix 補丁")
            else:
                status_text = f"⏳ 補丁可用，但遊戲尚未安裝\n(點擊安裝將自動喚起 Steam 下載並在完成後打補丁)"
                self.of_install_btn.setText("自動下載並安裝 Online-Fix 補丁")
                
            self.of_status_lbl.setText(status_text)
            self.of_status_lbl.setStyleSheet(f"color: {get_state_color('success')}; font-weight: bold;")
            self.of_install_btn.setEnabled(True)
        else:
            if is_patched:
                status_text = f"✅ 遊戲已打過補丁！但雲端庫無對應補丁 (AppID: {appid})"
                self.of_status_lbl.setStyleSheet(f"color: {get_state_color('success')}; font-weight: bold;")
            elif is_installed:
                status_text = f"❌ 遊戲已安裝，但補丁庫無對應補丁 (AppID: {appid})"
                self.of_status_lbl.setStyleSheet(f"color: {get_state_color('error')}; font-weight: bold;")
            else:
                status_text = f"❌ 補丁庫無對應補丁，且遊戲未安裝 (AppID: {appid})"
                self.of_status_lbl.setStyleSheet(f"color: {get_state_color('error')}; font-weight: bold;")
                
            self.of_install_btn.setText("自動下載並安裝 Online-Fix 補丁")
            self.of_status_lbl.setText(status_text)
            self.of_install_btn.setEnabled(False)

    def _find_steam_game_dir(self, app_id):
        import winreg, re, os
        from pathlib import Path
        libs = set()
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam')
            path, _ = winreg.QueryValueEx(key, 'SteamPath')
            winreg.CloseKey(key)
            libs.add(os.path.normpath(path))
        except:
            pass
        for lib in list(libs):
            vdf_path = os.path.join(lib, 'steamapps', 'libraryfolders.vdf')
            if os.path.exists(vdf_path):
                try:
                    content = open(vdf_path, encoding='utf-8', errors='ignore').read()
                    matches = re.findall(r'"path"\s+"([^"]+)"', content, re.IGNORECASE)
                    for m in matches:
                        m = m.replace('\\\\', '\\')
                        libs.add(os.path.normpath(m))
                except:
                    pass
        for lib in libs:
            acf = os.path.join(lib, 'steamapps', f'appmanifest_{app_id}.acf')
            if os.path.exists(acf):
                try:
                    content = open(acf, encoding='utf-8', errors='ignore').read()
                    state_match = re.search(r'"StateFlags"\s+"(\d+)"', content, re.IGNORECASE)
                    m = re.search(r'"installdir"\s+"([^"]+)"', content, re.IGNORECASE)
                    if m:
                        return Path(lib) / 'steamapps' / 'common' / m.group(1), state_match.group(1) if state_match else "0"
                except:
                    pass
        return None, None

    def _auto_install_of(self):
        from qfluentwidgets import InfoBar
        from PySide6.QtWidgets import QApplication
        from managers import onlinefix_manager
        
        sources = onlinefix_manager.get_patch_sources(target_app_id=self.current_appid, target_app_name=getattr(self, 'current_game_name', ''))
        source = sources.get(str(self.current_appid))
        if not source:
            InfoBar.error("錯誤", "找不到此遊戲的 Online-Fix 補丁來源！", parent=self)
            return
            
        rar_path = source.get('local_rar')
        if not rar_path and source.get('cloud_rar'):
            # Prompt user to download
            rar_path = str(onlinefix_manager.LOCAL_PATCH_DIR / source['cloud_rar']['path'])
            import os
            if not os.path.exists(rar_path):
                self.of_status_lbl.setText("⏳ 正在從 Google Drive 下載補丁...")
                QApplication.processEvents()
                dl_path = onlinefix_manager.download_cloud_patch(self.current_appid, getattr(self, 'current_game_name', ''), source['cloud_rar'])
                if not dl_path:
                    InfoBar.error("下載失敗", "無法從 Google Drive 取得補丁", parent=self)
                    self._check_of_sources(self.current_appid) # Reset status
                    return
                rar_path = dl_path
                
        if not rar_path:
            InfoBar.error("錯誤", "沒有可用的本地或雲端壓縮檔！", parent=self)
            return
            
        self._check_of_sources(self.current_appid) # Reset status
        self._handle_of_downloaded(rar_path)

    def _handle_of_downloaded(self, downloaded_file):
        import os
        from qfluentwidgets import BodyLabel, PushButton
        game_dir_info = self._find_steam_game_dir(self.current_appid)
        
        # Check if fully installed: StateFlags has the 4 bit set (4 = Fully Installed)
        is_installed = False
        if game_dir_info and game_dir_info[1]:
            try:
                flags = int(game_dir_info[1])
                if (flags & 4) == 4:
                    is_installed = True
            except:
                pass
                
        if is_installed:
            self._apply_online_fix(downloaded_file, game_dir_info[0])
        else:
            # Trigger Steam Installation and Wait
            self.wait_dlg = QDialog(self)
            self.wait_dlg.setWindowTitle("等待 Steam 安裝")
            self.wait_dlg.setFixedSize(450, 150)
            layout = QVBoxLayout(self.wait_dlg)
            
            lbl = BodyLabel(f"遊戲尚未安裝或正在下載中 (AppID: {self.current_appid})\n\n已喚起 Steam 進行安裝，請在 Steam 完成下載後，本視窗將自動繼續打入補丁。", self.wait_dlg)
            layout.addWidget(lbl)
            
            cancel_btn = PushButton("取消等待", self.wait_dlg)
            cancel_btn.clicked.connect(self.wait_dlg.reject)
            layout.addWidget(cancel_btn, alignment=Qt.AlignCenter)
            
            # Start steam install command
            try:
                os.startfile(f"steam://install/{self.current_appid}")
            except Exception as e:
                InfoBar.warning("喚起失敗", f"無法自動喚起 Steam: {e}", parent=self)
            
            # Polling timer
            self.poll_timer = QTimer(self.wait_dlg)
            self.poll_timer.timeout.connect(lambda: self._check_install_status(downloaded_file))
            self.poll_timer.start(3000) # Poll every 3 seconds
            
            if self.wait_dlg.exec() == QDialog.Rejected:
                self.poll_timer.stop()
                InfoBar.warning("已取消", "已取消等待 Steam 安裝，Online-Fix 補丁尚未打入。", parent=self)

    def _check_install_status(self, downloaded_file):
        game_dir_info = self._find_steam_game_dir(self.current_appid)
        if game_dir_info and game_dir_info[1]:
            try:
                flags = int(game_dir_info[1])
                if (flags & 4) == 4:
                    self.poll_timer.stop()
                    self.wait_dlg.accept()
                    self._apply_online_fix(downloaded_file, game_dir_info[0])
            except:
                pass

    def _apply_online_fix(self, downloaded_file, game_dir):
        from managers.onlinefix_manager import install_fix
        success, msg = install_fix(self.current_appid, downloaded_file, game_dir)
        if success:
            InfoBar.success("Online-Fix", f"安裝成功: {msg}", parent=self)
            self.download_successful.emit()
            self._check_of_sources(self.current_appid)
        else:
            InfoBar.error("Online-Fix 安裝失敗", msg, parent=self)
        
    def _on_download_source_clicked(self, src):
        if not self.current_appid:
            return

        if src == "Assiw":
            if not self.lua_dir or not os.path.isdir(self.lua_dir):
                InfoBar.error("錯誤", "找不到 Lua 儲存目錄", parent=self)
                return
            self.sources["Assiw"]["btn"].setEnabled(False)
            self.sources["Assiw"]["btn"].setText("下載中...")

            from managers.assiw_manager import AssiwDownloadThread
            self.assiw_dl_thread = AssiwDownloadThread(self.current_appid, self.lua_dir, self)

            def _on_assiw_dl_done(ok, msg):
                if "Assiw" in self.sources:
                    self.sources["Assiw"]["btn"].setEnabled(True)
                    self.sources["Assiw"]["btn"].setText("Download")
                if ok:
                    from managers import steam_manager
                    steam_dir = Path(self.lua_dir).parent.parent if self.lua_dir else None
                    clean_name = getattr(self, 'current_game_name', f"App_{self.current_appid}")
                    steam_manager.lock_game_version(self.current_appid, steam_dir, set_readonly=True, game_name=clean_name)
                    self._refresh_lock_button()
                    InfoBar.success("下載成功", f"已成功從下級來源 Assiw 儲存至 {self.current_appid}.lua，並自動啟用版本鎖定防護 🔒！", parent=self, position=InfoBarPosition.TOP)
                    self.download_successful.emit()
                else:
                    InfoBar.error("下載失敗", f"Assiw 下載失敗: {msg}", parent=self, position=InfoBarPosition.TOP)

            self.assiw_dl_thread.finished.connect(_on_assiw_dl_done)
            self.assiw_dl_thread.start()
            return

        if src == "Ryuu":
            from managers import ryuu_manager, account_manager
            acc_mgr = account_manager.get_account_manager()
            ryuu_has_quota = (self.ryuu_client.is_logged_in or ryuu_manager.has_saved_ryuu_credentials()) and acc_mgr.has_available_quota("ryuu")

            if ryuu_has_quota:
                self.sources["Ryuu"]["btn"].setEnabled(False)
                self.sources["Ryuu"]["btn"].setText("下載中...")
                info = getattr(self, 'current_ryuu_info', None)
                if not info:
                    info = ryuu_manager.fetch_ryuu_manifest_info(self.current_appid)
                default_branch = info.get("default_branch", "public") if info else "public"

                def on_ryuu_dl(res):
                    if "Ryuu" in self.sources:
                        self.sources["Ryuu"]["btn"].setEnabled(True)
                        self.sources["Ryuu"]["btn"].setText("Download")

                    if not res or (isinstance(res, dict) and res.get("error")):
                        print(f"[lua_tools_ui] Ryuu direct download failed, fallback to lua.tools...")
                        self.client.download_manifest(
                            self.current_appid, "Ryuu", f"Game_{self.current_appid}",
                            lambda lt_res: self.on_download_result(self.current_appid, lt_res)
                        )
                        return

                    self.on_download_result(self.current_appid, res)

                self.ryuu_client.download_manifest(self.current_appid, default_branch, on_ryuu_dl)
                return

        self.client.download_manifest(
            self.current_appid, src, f"Game_{self.current_appid}",
            lambda res: self.on_download_result(self.current_appid, res)
        )

    def on_search_result(self, data):
        self.search_btn.setEnabled(True)
        self.search_btn.setText("搜尋 Manifest")

        # Reset lua.tools sources (exclude Assiw as it is handled by AssiwCheckThread)
        for s in self.sources:
            if s == "Assiw":
                continue
            if s == "Ryuu" and getattr(self, 'current_ryuu_info', None):
                continue
            self.sources[s]["status"].setText("N/A")
            self.sources[s]["status"].setStyleSheet(f"color: {get_state_color('muted')};")
            self.sources[s]["btn"].setEnabled(False)

        if isinstance(data, dict) and "error" in data:
            if not (data.get("error") == "Unauthorized" or data.get("error", "").startswith("401")):
                InfoBar.error("搜尋失敗", data["error"], parent=self)
            return

        # Handle different API response formats
        parsed_sources = {}
        
        if isinstance(data, list):
            # Format A: List of objects (e.g. {"name": "Luie", "available": true})
            for item in data:
                name = str(item.get("name", item.get("source", ""))).strip()
                av_val = item.get("available")
                if isinstance(av_val, str):
                    available = av_val.lower() == "true"
                else:
                    available = bool(av_val)
                parsed_sources[name.lower()] = {"name": name, "available": available}
                
        elif isinstance(data, dict):
            # Format B: Dictionary of {source_name: status_string}
            for k, v in data.items():
                if isinstance(v, str):
                    parsed_sources[k.lower()] = {"name": k, "available": (v.lower() == "available" or v.lower() == "true")}

        # Update UI for lua.tools sources
        for s in self.sources:
            if s == "Assiw":
                continue
            if s == "Ryuu" and getattr(self, 'current_ryuu_info', None):
                continue
            s_lower = s.lower()
            if s_lower in parsed_sources:
                if parsed_sources[s_lower]["available"]:
                    self.sources[s]["status"].setText("AVAILABLE")
                    self.sources[s]["status"].setStyleSheet(f"color: {get_state_color('success')}; font-weight: bold;")
                    self.sources[s]["btn"].setEnabled(True)
                else:
                    self.sources[s]["status"].setText("N/A")
                    self.sources[s]["status"].setStyleSheet(f"color: {get_state_color('muted')};")


    def on_download_result(self, appid, res):
        if isinstance(res, dict) and res.get("error"):
            err_msg = res.get("error")
            InfoBar.error("下載失敗", f"API 回傳錯誤:\n{err_msg[:100]}", parent=self, position=InfoBarPosition.TOP)
            return

        lua_text = ""
        manifests = {}
        if isinstance(res, dict):
            lua_text = res.get("lua_content", res.get("data", ""))
            manifests = res.get("manifests", {})
        elif isinstance(res, str):
            lua_text = res

        if not lua_text or not lua_text.strip():
            InfoBar.error("下載失敗", "回傳內容為空或無有效腳本", parent=self, position=InfoBarPosition.TOP)
            return

        # 核心防護規範：沒有 manifest 的檔案直接認定為殘缺檔案，不支援安裝
        if not manifests:
            InfoBar.error(
                "拒絕安裝 (殘缺檔案)",
                "此來源未提供二進位 .manifest 清單檔！\n依照最新防護規範，缺少 Manifest 的 Lua 檔直接判定為殘缺檔案，系統不支援安裝。",
                parent=self,
                duration=6500,
                position=InfoBarPosition.TOP
            )
            return

        # Save to file
        if not self.lua_dir or not os.path.isdir(self.lua_dir):
            InfoBar.error("錯誤", "找不到 Lua 儲存目錄", parent=self)
            return

        filepath = os.path.join(self.lua_dir, f"{appid}.lua")
        try:
            # 若檔案已存在且唯讀，先解除唯讀以寫入
            if os.path.exists(filepath):
                os.chmod(filepath, stat.S_IWRITE | stat.S_IREAD)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(lua_text)

            from managers import steam_manager
            steam_dir = Path(self.lua_dir).parent.parent if self.lua_dir else None
            if not steam_dir or not steam_dir.exists():
                steam_dir = steam_manager.find_steam_path()

            # 確保同時將官方 lua 寫入 Steam 的 config/lua 目錄
            if steam_dir:
                steam_lua_file = Path(steam_dir) / "config" / "lua" / f"{appid}.lua"
                if steam_lua_file.resolve() != Path(filepath).resolve():
                    steam_lua_file.parent.mkdir(parents=True, exist_ok=True)
                    if steam_lua_file.exists():
                        os.chmod(steam_lua_file, stat.S_IWRITE | stat.S_IREAD)
                    steam_lua_file.write_text(lua_text, encoding="utf-8")

            # 1. 部署所有下載之二進位 Manifest 至 depotcache 與 lua 目錄
            if manifests:
                steam_manager.deploy_manifests_to_depotcache(manifests, steam_dir, self.lua_dir)
                steam_manager.sync_lua_with_deployed_manifests(appid, manifests, self.lua_dir)
                if steam_dir:
                    steam_manager.sync_lua_with_deployed_manifests(appid, manifests, Path(steam_dir) / "config" / "lua")
                steam_manager.sanitize_lua_manifests(appid, steam_dir, self.lua_dir)
                if steam_dir:
                    steam_manager.sanitize_lua_manifests(appid, steam_dir, Path(steam_dir) / "config" / "lua")

            # 2. 自動鎖定版本與防封鎖 (防 Valve 2026-09 401 斷線)
            game_name = getattr(self, 'current_game_name', f"App_{appid}")
            lock_ok, lock_msg = steam_manager.lock_game_version(appid, steam_dir, set_readonly=True, game_name=game_name)

            self._refresh_lock_button()

            m_count = len(manifests)
            suffix = f" (含 {m_count} 個清單檔)" if m_count > 0 else ""
            lock_suffix = "，已自動啟用版本鎖定防護 🔒！" if lock_ok else "！"
            InfoBar.success("下載與部署成功", f"已成功儲存至 {appid}.lua{suffix}{lock_suffix}", parent=self, position=InfoBarPosition.TOP)
            self.download_successful.emit()
        except Exception as e:
            InfoBar.error("儲存失敗", str(e), parent=self)

    def _refresh_lock_button(self):
        if not hasattr(self, 'btn_toggle_lock'):
            return
        if not self.current_appid:
            self.btn_toggle_lock.setEnabled(False)
            self.btn_toggle_lock.setText("請先搜尋遊戲")
            return
            
        from managers import steam_manager
        steam_dir = Path(self.lua_dir).parent.parent if self.lua_dir else None
        lock_info = steam_manager.get_game_manifest_lock_info(self.current_appid, steam_dir)
        self.btn_toggle_lock.setEnabled(True)
        if lock_info.get("is_locked"):
            self.btn_toggle_lock.setText("🔓 解除版本鎖定 (目前已受保護 🔒)")
            self.btn_toggle_lock.setToolTip(f"當前狀態: {lock_info['status_text']}\n點擊可解除唯讀與 AutoUpdateBehavior 鎖定")
        else:
            self.btn_toggle_lock.setText("🔒 一鍵鎖定版本防封鎖 (停用自動更新)")
            self.btn_toggle_lock.setToolTip("強烈推薦！鎖定後 Steam 下載將直接使用本地 Manifest，不會向 Valve 查詢導致 401 斷線！")

    def _toggle_current_lock(self):
        if not self.current_appid:
            return
        from managers import steam_manager
        steam_dir = Path(self.lua_dir).parent.parent if self.lua_dir else None
        lock_info = steam_manager.get_game_manifest_lock_info(self.current_appid, steam_dir)
        game_name = getattr(self, 'current_game_name', f"App_{self.current_appid}")
        
        if lock_info.get("is_locked"):
            ok, msg = steam_manager.unlock_game_version(self.current_appid, steam_dir)
            if ok:
                InfoBar.info("已解除鎖定", f"「{game_name}」{msg}", parent=self, position=InfoBarPosition.TOP)
            else:
                InfoBar.error("解除鎖定失敗", msg, parent=self, position=InfoBarPosition.TOP)
        else:
            ok, msg = steam_manager.lock_game_version(self.current_appid, steam_dir, set_readonly=True, game_name=game_name)
            if ok:
                InfoBar.success("版本鎖定成功", f"「{game_name}」{msg}", parent=self, position=InfoBarPosition.TOP)
            else:
                InfoBar.error("鎖定失敗", msg, parent=self, position=InfoBarPosition.TOP)
                
        self._refresh_lock_button()
        self.download_successful.emit()
