from ui.theme_utils import get_state_color
import os
import json
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
    InfoBar, InfoBarPosition, CardWidget, SubtitleLabel, ImageLabel, SegmentedWidget
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


            return
        
        results = api.search_game(name)
        if not results:
            self.result_ready.emit({"error": f"在 Online-Fix 找不到 {name}"})
            return
            
        links = api.get_download_links(results[0]['url'])
        self.result_ready.emit({"links": links, "name": name, "game_url": results[0]['url']})

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
        
        self.client = lua_tools_manager.get_shared_client(self.parent())
        self.client.ready.connect(self.on_client_ready)
        self.client.not_logged_in.connect(self.on_client_not_logged_in)
        
        if self.client.has_checked:
            if self.client.is_logged_in:
                self.on_client_ready()
            else:
                self.on_client_not_logged_in()

        self.of_thread = None
        
        self.initUI()
        
    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)

        # Top Area (7:3 ratio)
        top_layout = QHBoxLayout()
        top_layout.setSpacing(15)

        # Left side: Search (70%)
        search_card = CardWidget(self)
        search_layout = QHBoxLayout(search_card)
        search_layout.setContentsMargins(15, 10, 15, 10)
        
        self.search_input = LineEdit(self)
        self.search_input.setPlaceholderText("輸入 AppID 或商店網址...")
        self.search_input.setEnabled(False)
        self.search_btn = PrimaryPushButton("搜尋 Manifest", self)
        self.search_btn.setEnabled(False)
        self.search_btn.clicked.connect(self.do_search)
        
        search_layout.addWidget(self.search_input, 1)
        search_layout.addWidget(self.search_btn)
        top_layout.addWidget(search_card, 7)

        # Right side: Login Status (30%)
        status_card = CardWidget(self)
        status_layout = QHBoxLayout(status_card)
        status_layout.setContentsMargins(15, 10, 15, 10)
        
        self.status_label = BodyLabel("檢查登入中...", self)
        
        self.login_btn = PrimaryPushButton("登入帳號", self)
        self.login_btn.hide()
        self.login_btn.clicked.connect(self.open_login)
        
        self.relogin_btn = PushButton("重新登入", self)
        self.relogin_btn.hide()
        self.relogin_btn.clicked.connect(self.open_login)
        
        status_layout.addWidget(self.status_label, 1)
        status_layout.addWidget(self.login_btn)
        status_layout.addWidget(self.relogin_btn)
        top_layout.addWidget(status_card, 3)

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
        
        # 3 Cards for Luie, Ryuu, Sushi
        self.sources = {}
        for s in ["Luie", "Ryuu", "Sushi"]:
            card = CardWidget(self)
            c_layout = QHBoxLayout(card)
            
            # Name
            name_lbl = StrongBodyLabel(s, self)
            c_layout.addWidget(name_lbl)
            
            if s == "Luie":
                rec_lbl = BodyLabel("RECOMMENDED", self)
                rec_lbl.setStyleSheet(f"color: {get_state_color('accent')}; border: 1px solid {get_state_color('accent')}; border-radius: 4px; padding: 2px 4px; font-size: 10px;")
                c_layout.addWidget(rec_lbl)
                
            c_layout.addStretch(1)
            
            # Status
            status_lbl = BodyLabel("N/A", self)
            status_lbl.setStyleSheet(f"color: {get_state_color('muted')};")
            c_layout.addWidget(status_lbl)
            
            # Download Btn
            dl_btn = PrimaryPushButton("Download", self)
            dl_btn.setEnabled(False)
            c_layout.addWidget(dl_btn)
            
            self.sources[s] = {"status": status_lbl, "btn": dl_btn}
            lua_page_layout.addWidget(card)
            
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
        
        self.of_open_web_btn = PushButton("🌐 在 Online-Fix 網頁上搜尋此遊戲", self)
        self.of_open_web_btn.setEnabled(False)
        self.of_open_web_btn.clicked.connect(self._open_onlinefix_webpage)
        action_layout.addWidget(self.of_open_web_btn)
        
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
            self.of_open_web_btn.setEnabled(True)
        else:
            self.of_open_web_btn.setEnabled(False)

    def _open_gdrive_folder(self):
        from managers import onlinefix_manager
        import webbrowser
        webbrowser.open(onlinefix_manager.GDRIVE_FOLDER_URL)

    def _open_onlinefix_webpage(self):
        import urllib.parse
        import webbrowser
        import re
        if getattr(self, 'current_game_name', None):
            # Clean up game name (remove trademarks)
            clean_name = re.sub(r'[^a-zA-Z0-9\s-]', '', self.current_game_name).strip()
            if not clean_name: clean_name = self.current_game_name
            query = urllib.parse.quote(clean_name)
            url = f"https://online-fix.me/index.php?do=search&subaction=search&story={query}"
            webbrowser.open(url)

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
        
    def on_client_ready(self):
        self.status_label.setText("連線狀態：已登入 (準備就緒)")
        self.status_label.setStyleSheet(f"color: {get_state_color('success')};")
        self.login_btn.hide()
        self.relogin_btn.show()
        self.search_input.setEnabled(True)
        self.search_btn.setEnabled(True)
        
    def on_client_not_logged_in(self):
        self.status_label.setText("連線狀態：憑證無效或未登入")
        self.status_label.setStyleSheet(f"color: {get_state_color('error')};")
        self.login_btn.show()
        self.relogin_btn.hide()
        self.search_input.setEnabled(False)
        self.search_btn.setEnabled(False)
        
    def open_login(self):
        dlg = LuaToolsLoginDialog(self)
        if dlg.exec():
            self.client.view.reload()
            self.status_label.setText("連線狀態：重新連線中...")
            
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
        appid_text = self.search_input.text().strip()
        if not appid_text:
            return
            
        # Extract AppID from URL or raw numbers
        match = re.search(r'(?:app/|appid=)(\d+)', appid_text.lower())
        if match:
            appid_text = match.group(1)
        else:
            match = re.search(r'\d+', appid_text)
            if match:
                appid_text = match.group(0)
            
        try:
            appid = int(appid_text)
            # update input field to show clean appid
            self.search_input.setText(str(appid))
        except ValueError:
            InfoBar.error("錯誤", "無法從輸入中解析出 AppID", parent=self)
            return

        self.search_btn.setEnabled(False)
        self.search_btn.setText("搜尋中...")
        
        self.of_status_lbl.setText(f"檢查補丁來源中 (AppID: {appid})...")
        self.of_install_btn.setEnabled(False)

        self.current_appid = appid
        self.load_game_image(appid)
        
        self.client.search_manifest(appid, self.on_search_result)
        
        # Trigger background check for OF patch
        self._check_of_sources(appid)

    def _check_of_sources(self, appid):
        from managers import onlinefix_manager
        sources = onlinefix_manager.get_patch_sources()
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
                        m = m.replace('\\\\', '\')
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
        
        sources = onlinefix_manager.get_patch_sources()
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
                dl_path = onlinefix_manager.download_cloud_patch(source['cloud_rar'])
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
        
    def on_search_result(self, data):
        self.search_btn.setEnabled(True)
        self.search_btn.setText("搜尋 Manifest")
        
        import json
        try:
            with open("debug_search_data.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except:
            pass

        # Reset all sources
        for s in self.sources:
            self.sources[s]["status"].setText("N/A")
            self.sources[s]["status"].setStyleSheet(f"color: {get_state_color('muted')};")
            self.sources[s]["btn"].setEnabled(False)
            try:
                self.sources[s]["btn"].clicked.disconnect()
            except Exception:
                pass

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

        # Update UI
        for s in self.sources:
            s_lower = s.lower()
            if s_lower in parsed_sources:
                if parsed_sources[s_lower]["available"]:
                    self.sources[s]["status"].setText("AVAILABLE")
                    self.sources[s]["status"].setStyleSheet(f"color: {get_state_color('success')}; font-weight: bold;")
                    self.sources[s]["btn"].setEnabled(True)
                    # Connect the button directly to download
                    self.sources[s]["btn"].clicked.connect(
                        lambda checked=False, src=s: self.client.download_manifest(
                            self.current_appid, src, f"Game_{self.current_appid}", 
                            lambda res: self.on_download_result(self.current_appid, res)
                        )
                    )
                else:
                    self.sources[s]["status"].setText("N/A")
                    self.sources[s]["status"].setStyleSheet(f"color: {get_state_color('muted')};")

    def on_download_result(self, appid, text):
        if text.startswith("ERROR:") or "error" in text.lower() or not text.strip():
            if not text.strip():
                text = "Empty response"
            InfoBar.error("下載失敗", f"API 回傳錯誤或無內容:\n{text[:100]}", parent=self, position=InfoBarPosition.TOP)
            return

        # Save to file
        if not self.lua_dir or not os.path.isdir(self.lua_dir):
            InfoBar.error("錯誤", "找不到 Lua 儲存目錄", parent=self)
            return

        filepath = os.path.join(self.lua_dir, f"{appid}.lua")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text)
            InfoBar.success("下載成功", f"已成功儲存至 {appid}.lua", parent=self, position=InfoBarPosition.TOP)
            self.download_successful.emit()
        except Exception as e:
            InfoBar.error("儲存失敗", str(e), parent=self)
