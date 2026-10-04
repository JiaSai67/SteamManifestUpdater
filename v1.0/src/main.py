import os
import sys
from ui.theme_utils import get_state_color
import json
import urllib.request
import threading
from datetime import datetime
from pathlib import Path
import winreg
import shutil
import concurrent.futures
from managers import onlinefix_manager

VERSION = "1.0.53-dev"

# Suppress stdout/stderr to prevent QFluentWidgets Pro message
# sys.stdout
# sys.stderr
os.environ["QT_API"] = "pyside6"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-logging --log-level=3 --silent-debugger-extension-api"

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer
from PySide6.QtGui import QIcon, QFont
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QHeaderView, QFileDialog, QTreeWidget, QTreeWidgetItem, QStackedWidget

from qfluentwidgets import (
    setTheme, Theme, LineEdit, PushButton, PrimaryPushButton, 
    TreeWidget, SubtitleLabel, BodyLabel, InfoBar, InfoBarPosition, ProgressBar, StrongBodyLabel, CardWidget, SegmentedWidget
)

from PySide6.QtWidgets import QTreeWidgetItem
from api.update_manifests import get_app_info
from ui.lua_tools_ui import LuaToolsDownloaderWidget

class CustomTreeWidgetItem(QTreeWidgetItem):
    def __init__(self, parent=None, is_category=False, category_priority=0, sort_data=None):
        super().__init__(parent)
        self.is_category = is_category
        self.category_priority = category_priority
        self.sort_data = sort_data or {}
        
    def __lt__(self, other):
        # 1. Categories logic: fixed position
        if getattr(self, 'is_category', False) and getattr(other, 'is_category', False):
            sort_order = self.treeWidget().header().sortIndicatorOrder()
            if sort_order == Qt.AscendingOrder:
                return self.category_priority < getattr(other, 'category_priority', 0)
            else:
                return self.category_priority > getattr(other, 'category_priority', 0)
                
        col = self.treeWidget().sortColumn()
        
        my_appid = self.sort_data.get(0, "")
        other_appid = getattr(other, 'sort_data', {}).get(0, "")
        
        # 2. Different games: sort by the actual value of the column
        if my_appid != other_appid:
            my_val = self.sort_data.get(col, "")
            other_val = getattr(other, 'sort_data', {}).get(col, "")
            try:
                return float(my_val) < float(other_val)
            except ValueError:
                return str(my_val).lower() < str(other_val).lower()
                
        # 3. Same game (Depots): maintain the strict parent-child order
        my_idx = self.sort_data.get("idx", 0)
        other_idx = getattr(other, 'sort_data', {}).get("idx", 0)
        
        sort_order = self.treeWidget().header().sortIndicatorOrder()
        if sort_order == Qt.AscendingOrder:
            return my_idx < other_idx
        else:
            return my_idx > other_idx

from managers import config_manager


def get_steam_path():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        path, _ = winreg.QueryValueEx(key, "SteamPath")
        winreg.CloseKey(key)
        steam_dir = Path(path).resolve()
        if steam_dir.exists():
            return steam_dir
    except Exception:
        pass
    
    default_paths = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Steam",
        Path(r"C:\Steam")
    ]
    for p in default_paths:
        if p.exists():
            return p
    return None

class CloudPrecacheWorker(QThread):
    finished = Signal()

    def run(self):
        onlinefix_manager.fetch_cloud_cache()
        self.finished.emit()

class UpdateWorker(QThread):
    progress = Signal(int, int) # completed, total
    finished = Signal()
    item_checked = Signal(dict)
    status = Signal(str)

    def __init__(self, items, steam_path=None, lua_dir=None):
        super().__init__()
        self.items = items
        self.steam_path = steam_path
        self.lua_dir = lua_dir
        self.is_cancelled = False

    def run(self):
        total = len(self.items)
        if total == 0:
            self.finished.emit()
            return
            
        completed = 0
        import concurrent.futures

        def process_single(item):
            if self.is_cancelled: return item
            
            filepath = item["filepath"]
            appid = item["appid"]
            result = {
                "appid": appid,
                "status": "normal",
                "game_name": item.get("game_name", "未知遊戲"),
                "error_msg": "",
                "rows": [],
                "local_date": item.get("local_date", "未知"),
                "latest_date": "未知",
                "version_status": "未知",
                "diff_count": 0,
                "is_latest": True,
                "filepath": filepath
            }
            
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception as e:
                result["status"] = "error"
                result["error_msg"] = str(e)
                result["version_status"] = "讀取失敗"
                return result
                
            import re
            name_match = re.search(r'--\s*\d+\s*-\s*(.+)', content)
            if name_match and name_match.group(1).strip():
                result["game_name"] = name_match.group(1).strip()
            if not result.get("game_name") or result["game_name"] == "未知遊戲":
                try:
                    from managers import name_resolver
                    result["game_name"] = name_resolver.resolve_game_name(appid, lua_path=filepath, steam_path=self.steam_path)
                except Exception:
                    pass
                
            pattern = re.compile(r'^[ \t]*(setManifestid\(\s*(\d+)\s*,\s*"(\d+)"(?:,\s*(\d+))?\s*\))', re.MULTILINE)
            matches = pattern.findall(content)
            if not matches:
                result["status"] = "error"
                result["error_msg"] = "找不到 setManifestid (格式不符)"
                result["version_status"] = "格式不符"
                return result
                
            local_manifests = {m[1]: m[2] for m in matches}
            
            # 1. Manifest 實體完整性檢查
            from managers import steam_manager, version_resolver
            m_status = steam_manager.get_lua_manifest_status(appid, steam_path=self.steam_path, lua_dir=self.lua_dir)
            result["manifest_info"] = m_status

            # 2. 版本差異與日期比對 (當前版本日期 vs 最新版本日期 vs 跨越版本數)
            try:
                diff_info = version_resolver.resolve_manifest_version_diff(
                    appid,
                    local_manifests=local_manifests,
                    lua_dir=self.lua_dir,
                    steam_path=self.steam_path,
                    timeout=7
                )
                result["local_date"] = diff_info.get("local_date", "未知")
                result["latest_date"] = diff_info.get("latest_date", "未知")
                result["version_status"] = diff_info.get("version_status", "0 版")
                result["diff_count"] = diff_info.get("diff_count", 0)
                result["is_latest"] = diff_info.get("is_latest", True)
                result["has_available_update"] = diff_info.get("has_available_update", False)
                result["ryuu_has_update"] = diff_info.get("ryuu_has_update", False)
                result["ryuu_update_depots"] = diff_info.get("ryuu_update_depots", [])
                result["unified_search"] = diff_info.get("unified_search", {})
                result["diff_info"] = diff_info
            except Exception as e:
                result["local_date"] = item.get("local_date", "未知")
                result["latest_date"] = "查詢超時"
                result["version_status"] = "查詢失敗"
                result["is_latest"] = True
                result["has_available_update"] = False
                result["ryuu_has_update"] = False

            # 3. 狀態分類判定
            if m_status.get("is_incomplete"):
                result["status"] = "incomplete"
                result["error_msg"] = m_status.get("status_text", "殘缺檔案 (缺少 Manifest)")
                result["version_status"] = "缺檔"
            elif result.get("ryuu_has_update"):
                result["status"] = "ryuu_outdated"
            elif not result["is_latest"]:
                result["status"] = "outdated"
            else:
                result["status"] = "up_to_date"
                
            return result

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            futures = {executor.submit(process_single, item): item for item in self.items}
            for future in concurrent.futures.as_completed(futures):
                if self.is_cancelled: break
                final_res = future.result()
                completed += 1
                self.progress.emit(completed, total)
                self.item_checked.emit(final_res)

        self.finished.emit()

class SearchableTreeWidget(TreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.search_text = ""
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(1000)
        self.search_timer.timeout.connect(self.clear_search)
        
        # Remove QFluentWidgets smooth scroll delegate filter to eliminate animation and delay
        if hasattr(self, 'scrollDelegate') and self.scrollDelegate:
            try:
                self.viewport().removeEventFilter(self.scrollDelegate)
            except Exception:
                pass
                
        # Set discrete scroll mode for immediate jumping
        self.setVerticalScrollMode(QTreeWidget.ScrollPerItem)
        if self.verticalScrollBar():
            self.verticalScrollBar().setSingleStep(1)
        
    def clear_search(self):
        self.search_text = ""
        
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Home, Qt.Key_End, Qt.Key_Return, Qt.Key_Enter):
            super().keyPressEvent(event)
            return
            
        if event.key() == Qt.Key_Backspace:
            if self.search_text:
                self.search_text = self.search_text[:-1]
                if self.search_text:
                    self.search_timer.start()
                    self.find_and_select()
                else:
                    self.clear_search()
            return
            
        text = event.text()
        if text.isprintable() and text:
            self.search_text += text.lower()
            self.search_timer.start()
            self.find_and_select()
        else:
            super().keyPressEvent(event)
            
    def find_and_select(self):
        from PySide6.QtWidgets import QTreeWidgetItemIterator
        if not self.search_text:
            return
            
        # 搜尋邏輯：打數字僅搜尋 AppID (欄位 0)；打文字/字母僅搜尋遊戲名稱 (欄位 1)
        is_numeric = self.search_text.isdigit()
        
        # 1. 優先前綴搜尋 (Prefix match)
        iterator = QTreeWidgetItemIterator(self)
        while iterator.value():
            item = iterator.value()
            if not getattr(item, 'is_category', False):
                if is_numeric:
                    appid = item.text(0).strip().lower()
                    if appid.startswith(self.search_text):
                        self.setCurrentItem(item)
                        self.scrollToItem(item)
                        return
                else:
                    game_name = item.text(1).strip().lower()
                    if game_name.startswith(self.search_text):
                        self.setCurrentItem(item)
                        self.scrollToItem(item)
                        return
            iterator += 1

        # 2. 次要包含搜尋 (Substring match fallback)
        iterator = QTreeWidgetItemIterator(self)
        while iterator.value():
            item = iterator.value()
            if not getattr(item, 'is_category', False):
                if is_numeric:
                    appid = item.text(0).strip().lower()
                    if self.search_text in appid:
                        self.setCurrentItem(item)
                        self.scrollToItem(item)
                        return
                else:
                    game_name = item.text(1).strip().lower()
                    if self.search_text in game_name:
                        self.setCurrentItem(item)
                        self.scrollToItem(item)
                        return
            iterator += 1

    def wheelEvent(self, event):
        # Native instant wheel jump (3 items per notch, 0ms delay, zero interpolation)
        num_degrees = event.angleDelta().y() / 8
        num_steps = num_degrees / 15
        sb = self.verticalScrollBar()
        if sb:
            new_val = int(sb.value() - num_steps * 3)
            sb.setValue(max(sb.minimum(), min(sb.maximum(), new_val)))
        event.accept()

class SteamManifestApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("mainWindow")
        
        self.config = config_manager.get_config()
        self.steam_path = get_steam_path()
        self.initUI()
        
        # Follow system theme dynamically
        from qfluentwidgets import setTheme, Theme, qconfig
        setTheme(Theme.AUTO)
        self.update_theme_styles()
        qconfig.themeChanged.connect(self.update_theme_styles)
        
        # Pre-cache online-fix sources in background QThread with live UI sync
        self.cloud_pending = (onlinefix_manager._cloud_cache is None)
        self.cloud_worker = CloudPrecacheWorker(self)
        self.cloud_worker.finished.connect(self.refresh_sources_column)
        self.cloud_worker.start()
        
        # Looping animation timer for pending data queries
        self.loading_timer = QTimer(self)
        self.loading_dots_count = 0
        self.loading_timer.timeout.connect(self.animate_loading_dots)
        self.checking_appids = set()
        
        self.update_ost_status()
        self.start_auto_update_flow()
        
        # Zero-overhead real-time Defender monitoring via Registry
        self.defender_timer = QTimer(self)
        self.defender_timer.timeout.connect(self.check_defender_status)
        self.defender_timer.start(500) # Initial poll at 500ms
        self.check_defender_status()

        # 自動修復：解除歷史遺留之 ACF 唯讀屬性，徹底消除 Steam「磁碟寫入錯誤」
        try:
            from managers import steam_manager
            steam_manager.unlock_all_appmanifests_readonly(self.steam_path)
        except Exception:
            pass


    def update_theme_styles(self):
        from qfluentwidgets import isDarkTheme
        is_dark = isDarkTheme()
        
        if not isDarkTheme():
            pass # Fluent Widgets handles the background natively, do not override
        else:
            self.setStyleSheet("#mainWindow { background-color: rgb(32, 32, 32); }")
            
        # Force title bar to match theme on Windows
        try:
            import ctypes
            hwnd = int(self.winId())
            value = ctypes.c_int(1 if is_dark else 0)
            # DWMWA_USE_IMMERSIVE_DARK_MODE (20 for Win11, 19 for Win10 20H1+)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(value), ctypes.sizeof(value))
            
            # Refresh frame
            import win32gui
            import win32con
            win32gui.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED)
        except Exception:
            pass

    def initUI(self):
        self.setWindowTitle(f"Steam Lua Manifest Viewer (Fluent UI) - {VERSION}")
        self.resize(1200, 700)
        self.setMinimumSize(900, 500)
        self.setAcceptDrops(True)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # 1. Header Card (Lua Folder)
        lua_card = CardWidget(self)
        lua_layout = QHBoxLayout(lua_card)
        lua_layout.setContentsMargins(15, 15, 15, 15)
        
        title_label = StrongBodyLabel("Lua 資料夾路徑:", self)
        self.dir_entry = LineEdit(self)
        self.dir_entry.setText(self.config.get("lua_dir", config_manager.DEFAULT_LUA_DIR))
        
        btn_browse = PushButton("瀏覽...", self)
        btn_browse.clicked.connect(self.browse_folder)
        btn_reload = PushButton("鎖定並重新載入", self)
        btn_reload.clicked.connect(self.save_and_reload)
        self.btn_update = PushButton("檢查與重新整理", self)
        self.btn_update.setToolTip("掃描本機遊戲清單，並聯網比對 SteamDB 與 generator.ryuu 之最新版本")
        self.btn_update.clicked.connect(self.start_auto_update_flow)

        self.btn_auto_update_ryuu = PrimaryPushButton("⚡ 一鍵自動更新 (Ryuu 來源)", self)
        self.btn_auto_update_ryuu.setToolTip("依據 generator.ryuu 搜尋結果，一鍵自動下載最新 Manifest 實體檔並同步更新 Lua 設定檔")
        self.btn_auto_update_ryuu.clicked.connect(self.ui_batch_auto_update_ryuu)
        self.btn_auto_update_ryuu.hide()
        
        lua_layout.addWidget(title_label)
        lua_layout.addWidget(self.dir_entry, 1)
        lua_layout.addWidget(btn_browse)
        lua_layout.addWidget(btn_reload)
        lua_layout.addWidget(self.btn_update)
        lua_layout.addWidget(self.btn_auto_update_ryuu)
        main_layout.addWidget(lua_card)

        # 2. OpenSteamTools Card
        ost_card = CardWidget(self)
        ost_layout = QHBoxLayout(ost_card)
        ost_layout.setContentsMargins(15, 15, 15, 15)
        
        self.lbl_ost_status = StrongBodyLabel("OpenSteamTools 狀態: 偵測中...", self)
        self.btn_install_ost = PrimaryPushButton("一鍵安裝 OpenSteamTools", self)
        self.btn_install_ost.clicked.connect(self.install_ost)
        self.btn_uninstall_ost = PushButton("移除", self)
        self.btn_uninstall_ost.clicked.connect(self.uninstall_ost)
        
        # Defender section
        from PySide6.QtWidgets import QFrame
        separator = QFrame(self)
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        
        self.lbl_defender_status = StrongBodyLabel("Defender 即時保護: 偵測中...", self)
        self.btn_open_defender = PushButton("開啟設定", self)
        self.btn_open_defender.clicked.connect(self.open_defender_settings)
        
        ost_layout.addWidget(self.lbl_ost_status)
        ost_layout.addWidget(self.btn_install_ost)
        ost_layout.addWidget(self.btn_uninstall_ost)
        ost_layout.addWidget(separator)
        ost_layout.addWidget(self.lbl_defender_status, 1)
        ost_layout.addWidget(self.btn_open_defender)
        main_layout.addWidget(ost_card)

        # 3. Content Area with Page Switcher
        self.page_switcher = SegmentedWidget(self)
        self.stacked_widget = QStackedWidget(self)
        
        # Align switcher to the left
        switcher_layout = QHBoxLayout()
        switcher_layout.addWidget(self.page_switcher, 0, Qt.AlignLeft)
        switcher_layout.addStretch(1)
        
        self.btn_settings = PushButton("設定", self)
        self.btn_settings.clicked.connect(self.show_settings_dialog)
        switcher_layout.addWidget(self.btn_settings, 0, Qt.AlignRight)
        
        main_layout.addLayout(switcher_layout)
        main_layout.addWidget(self.stacked_widget)
        
        # --- Page 1: 本機檔案 (Local Files) ---
        self.page_local = QWidget()
        layout_local = QVBoxLayout(self.page_local)
        layout_local.setContentsMargins(0, 0, 0, 0)
        layout_local.setSpacing(10)
        
        # Manifest Warning & Repair Banner
        self.manifest_warning_card = CardWidget(self.page_local)
        warning_layout = QHBoxLayout(self.manifest_warning_card)
        warning_layout.setContentsMargins(15, 10, 15, 10)
        
        self.lbl_manifest_warning = StrongBodyLabel("⚠️ 偵測到本地有殘缺遊戲（缺少 Manifest 檔案）", self.page_local)
        self.lbl_manifest_warning.setStyleSheet(f"color: {get_state_color('warning')};")
        self.btn_batch_repair_manifests = PrimaryPushButton("⚡ 批次補齊缺少之 Manifest", self.page_local)
        self.btn_batch_repair_manifests.clicked.connect(self.show_batch_manifest_dialog)
        
        warning_layout.addWidget(self.lbl_manifest_warning, 1)
        warning_layout.addWidget(self.btn_batch_repair_manifests)
        self.manifest_warning_card.hide()
        layout_local.addWidget(self.manifest_warning_card)
        
        self.tree = SearchableTreeWidget(self)
        self.tree.setColumnCount(8)
        self.tree.setHeaderLabels([
            "AppID", "遊戲名稱", "當前版本日期", "最新版本日期", "版本狀態", "Online-Fix 狀態", "Lua 來源", "補丁 來源"
        ])
        
        self.tree.setColumnWidth(0, 95)
        self.tree.setColumnWidth(1, 280)
        self.tree.setColumnWidth(2, 115)
        self.tree.setColumnWidth(3, 115)
        self.tree.setColumnWidth(4, 115)
        self.tree.setColumnWidth(5, 120)
        self.tree.setColumnWidth(6, 80)
        self.tree.setColumnWidth(7, 80)
        self.tree.setWordWrap(False)
        self.tree.setIndentation(12)
        
        # Enable column toggle via right click
        self.tree.header().setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.header().customContextMenuRequested.connect(self.show_header_menu)
        
        # Enable context menu for items
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_item_menu)
        
        # Enable smart sorting
        self.tree.setSortingEnabled(True)
        
        # Restore header state if saved (only if column count matches 8)
        import base64
        from PySide6.QtCore import QByteArray
        saved_state = self.config.get('tree_header_state_v2')
        if saved_state:
            try:
                state_bytes = QByteArray(base64.b64decode(saved_state.encode('utf-8')))
                self.tree.header().restoreState(state_bytes)
            except Exception as e:
                print(f"Error restoring tree state: {e}")
                
        # FORCE interactive mode and no stretch, overriding whatever was saved in config
        self.tree.header().setSectionResizeMode(QHeaderView.Interactive)
        self.tree.header().setStretchLastSection(False)
        from PySide6.QtWidgets import QAbstractItemView
        self.tree.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
        layout_local.addWidget(self.tree, 1)
        
        # 4. Status and Progress (exclusive to local files page)
        status_layout = QHBoxLayout()
        self.lbl_status = BodyLabel("就緒", self)
        self.progress_bar = ProgressBar(self)
        self.progress_bar.hide()
        status_layout.addWidget(self.lbl_status)
        status_layout.addWidget(self.progress_bar, 1)
        layout_local.addLayout(status_layout)
        
        self.stacked_widget.addWidget(self.page_local)

        # --- Page 2: 安裝遊戲 (Install Game) ---
        self.page_install = QWidget()
        layout_install = QVBoxLayout(self.page_install)
        layout_install.setContentsMargins(0, 0, 0, 0)
        layout_install.setSpacing(15)
        
        from ui import lua_tools_ui
        self.lua_downloader_widget = lua_tools_ui.LuaToolsDownloaderWidget(self, lua_dir=self.config.get("lua_dir", config_manager.DEFAULT_LUA_DIR))
        self.lua_downloader_widget.download_successful.connect(self.save_and_reload)
        layout_install.addWidget(self.lua_downloader_widget)
        
        self.stacked_widget.addWidget(self.page_install)
        
        # --- Page 3: 一鍵安裝 (One Click Install) ---
        from ui import one_click_install_ui
        self.page_oneclick = one_click_install_ui.OneClickInstallWidget(self)
        self.stacked_widget.addWidget(self.page_oneclick)
        
        # Setup switcher ("一鍵安裝" | "本機檔案" | "安裝遊戲")
        self.page_switcher.addItem("oneclick", "一鍵安裝")
        self.page_switcher.addItem("local", "本機檔案")
        self.page_switcher.addItem("install", "安裝遊戲")
        self.page_switcher.currentItemChanged.connect(
            lambda k: self.stacked_widget.setCurrentWidget(
                self.page_oneclick if k == "oneclick" else (self.page_local if k == "local" else self.page_install)
            )
        )
        self.page_switcher.setCurrentItem("oneclick")

    def show_settings_dialog(self):
        from ui.settings_ui import SettingsDialog
        dialog = SettingsDialog(self, config=self.config)
        if dialog.exec():
            # Update config object
            self.config["onlinefix_domain"] = dialog.onlinefix_input.text().strip()
            self.config["zeigames_domain"] = dialog.zeigames_input.text().strip()
            self.config["luatools_domain"] = dialog.luatools_input.text().strip()
            
            drives = dialog.get_cloud_drives()
            self.config["cloud_drives"] = drives
            if drives:
                self.config["gdrive_url"] = drives[0]["url"]
            
            # Update daemon settings
            self.config["daemon_auto_patch"] = dialog.switch_autopatch.isChecked()
            self.config["daemon_notify"] = dialog.switch_notify.isChecked()
            
            # Update storage paths
            new_lua_dir = dialog.lua_dir_input.text().strip()
            if new_lua_dir:
                self.config["lua_dir"] = new_lua_dir
                self.dir_entry.setText(new_lua_dir)
                
            new_creds_dir = dialog.credentials_input.text().strip()
            if new_creds_dir:
                self.config["credentials_dir"] = new_creds_dir
                
            new_cache_dir = dialog.cache_input.text().strip()
            if new_cache_dir:
                self.config["cache_dir"] = new_cache_dir
                
            config_manager.save_config(self.config)
            
            # Apply to global constants dynamically
            onlinefix_manager.update_cloud_drives(drives)
            
            InfoBar.success("設定已儲存", "設定已更新！已同步網盤與背景守護配置。", position=InfoBarPosition.TOP, parent=self)

    def show_header_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        for i in range(self.tree.columnCount()):
            title = self.tree.headerItem().text(i)
            action = menu.addAction(title)
            action.setCheckable(True)
            action.setChecked(not self.tree.isColumnHidden(i))
            action.toggled.connect(lambda checked, col=i: self.tree.setColumnHidden(col, not checked))
        menu.exec_(self.tree.header().mapToGlobal(pos))

    def show_item_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item or item.is_category: return
        
        app_id = item.text(0)
        game_name = item.text(1)
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        
        sources = onlinefix_manager.get_patch_sources(target_apps={app_id: game_name}, allow_network=False)
        has_source = app_id in sources
        app_src = sources.get(app_id, {})
        
        version_status = item.text(4)
        game_res = next((r for r in getattr(self, 'last_results', []) if str(r.get("appid")) == app_id), None)
        has_update = (game_res.get("has_available_update", False) or game_res.get("ryuu_has_update", False)) if game_res else False
        best_source = game_res.get("best_source", "github") if game_res else "github"
        source_name = "GitHub" if best_source == "github" else ("Ryuu" if best_source == "ryuu" else "Lua.tools")

        if has_update:
            update_action = menu.addAction(f"⚡ 立即自動更新至最新版本 (推薦: {source_name})")
            update_action.triggered.connect(lambda: self.ui_auto_update_single_game_via_ryuu(app_id, game_name))
            menu.addSeparator()
        elif "跨越" in version_status:
            update_action = menu.addAction(f"🚀 前往一鍵安裝更新至最新版 ({version_status})")
            update_action.triggered.connect(lambda: self.switch_to_oneclick_install(app_id))
            menu.addSeparator()

        # Patch Actions
        if app_src.get('local_rar') or app_src.get('cloud_rar'):
            install_action = menu.addAction("📦 安裝 Online-Fix 補丁")
        else:
            install_action = menu.addAction("📦 安裝 Online-Fix (雲端/本地皆無檔案)")
            install_action.setEnabled(False)
            
        install_action.triggered.connect(lambda: self.ui_install_onlinefix(app_id, game_name, sources.get(app_id)))
        
        status = onlinefix_manager.get_fix_status(app_id)
        # Uninstall is allowed if we have a record OR if we have a source to compare with
        has_record = onlinefix_manager._load_record(app_id) is not None
        can_uninstall = has_record or (has_source and status != "未安裝")
        
        if can_uninstall:
            uninstall_action = menu.addAction("🗑️ 移除 Online-Fix 補丁")
            uninstall_action.triggered.connect(lambda: self.ui_uninstall_onlinefix(app_id, game_name, sources.get(app_id)))
            
        menu.addSeparator()

        # Manifest / Build Lock Actions (防 Valve 2026-09 401 封鎖)
        from managers import steam_manager
        lock_info = steam_manager.get_game_manifest_lock_info(app_id, self.steam_path)
        if lock_info.get("is_locked"):
            lock_action = menu.addAction("🔓 解除版本鎖定 (目前已受保護 🔒)")
            lock_action.triggered.connect(lambda: self.ui_unlock_manifest(app_id, game_name))
        else:
            lock_action = menu.addAction("🔒 鎖定版本防封鎖 (停用自動更新 / 防 401)")
            lock_action.triggered.connect(lambda: self.ui_lock_manifest(app_id, game_name))
            
        # Manifest 完整性與殘缺修復選項
        m_status = steam_manager.get_lua_manifest_status(app_id, self.steam_path, self.config.get("lua_dir"))
        if m_status.get("is_incomplete"):
            repair_action = menu.addAction(f"⚡ 補齊 Manifest 清單 (缺少 {len(m_status.get('missing_files', []))} 個檔案)")
            repair_action.triggered.connect(self.show_batch_manifest_dialog)

        if lock_info.get("has_acf") and lock_info.get("acf_path"):
            open_acf_action = menu.addAction("📂 開啟 appmanifest 檔案位置")
            open_acf_action.triggered.connect(lambda: self.ui_open_acf_folder(lock_info["acf_path"]))

        menu.addSeparator()
        
        delete_lua_action = menu.addAction("🗑️ 刪除此 Lua 設定檔")
        delete_lua_action.triggered.connect(lambda: self.confirm_and_delete_lua(app_id, game_name))
            
        menu.exec_(self.tree.viewport().mapToGlobal(pos))

    def show_batch_manifest_dialog(self):
        from ui.batch_manifest_ui import BatchManifestRepairDialog
        dlg = BatchManifestRepairDialog(self, self.steam_path, self.config.get("lua_dir"))
        dlg.repaired_finished.connect(self.start_auto_update_flow)
        dlg.exec()

    def ui_auto_update_single_game_via_ryuu(self, app_id, game_name):
        from managers import unified_manifest_manager
        clean_name = game_name.replace("🔒 ", "").replace("⚠️ [殘缺] ", "").strip()
        self.lbl_status.setText(f"⏳ 正在多源比對並下載「{clean_name}」最新版本 Manifest 與 Lua...")
        self.progress_bar.show()
        self.progress_bar.setValue(30)
        QApplication.processEvents()

        mgr = unified_manifest_manager.get_unified_manifest_manager()
        search_res = mgr.search_all_sources(app_id)
        best_source = search_res.get("best_source", "github")
        best_reason = search_res.get("best_reason", "")
        source_name = "GitHub" if best_source == "github" else ("Ryuu" if best_source == "ryuu" else "Lua.tools")

        self.lbl_status.setText(f"⏳ 仲裁結果: 最佳來源為 {source_name} ({best_reason})，正在部署...")
        self.progress_bar.setValue(60)
        QApplication.processEvents()

        def on_progress(txt):
            self.lbl_status.setText(f"⏳ 「{clean_name}」: {txt}")
            QApplication.processEvents()

        success, msg = mgr.deploy_best_manifest(app_id, search_res, progress_cb=on_progress)
        self.progress_bar.hide()

        if success:
            InfoBar.success("自動更新成功！", f"「{clean_name}」已透過 {source_name} 成功更新為最新版本 Manifest！\n{best_reason}", position=InfoBarPosition.TOP, parent=self)
            self.start_auto_update_flow()
        else:
            InfoBar.error("更新失敗", f"「{clean_name}」自動更新失敗: {msg}", position=InfoBarPosition.TOP, parent=self)

    def ui_batch_auto_update_ryuu(self):
        updatable = [r for r in getattr(self, 'last_results', []) if (r.get("has_available_update") or r.get("ryuu_has_update"))]
        if not updatable:
            InfoBar.info("無可用更新", "目前所有本地遊戲在 GitHub / Ryuu 上皆已是最新版本！", position=InfoBarPosition.TOP, parent=self)
            return

        from managers import unified_manifest_manager
        mgr = unified_manifest_manager.get_unified_manifest_manager()

        total = len(updatable)
        self.btn_auto_update_ryuu.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setValue(0)

        import collections
        queue = collections.deque(updatable)
        success_count = 0

        def process_next():
            nonlocal success_count
            if not queue:
                self.btn_auto_update_ryuu.setEnabled(True)
                self.progress_bar.hide()
                InfoBar.success("批次更新完成", f"已成功將 {success_count} 款遊戲透過多源智慧比對更新為最新 Manifest！", position=InfoBarPosition.TOP, parent=self)
                self.start_auto_update_flow()
                return

            item = queue.popleft()
            app_id = str(item.get("appid"))
            game_name = item.get("game_name", app_id)
            current_idx = total - len(queue)
            self.progress_bar.setValue(int((current_idx / total) * 100))
            self.lbl_status.setText(f"⏳ ({current_idx}/{total}) 正在多源比對與更新「{game_name}」...")
            QApplication.processEvents()

            search_res = item.get("unified_search") or mgr.search_all_sources(app_id)
            ok, msg = mgr.deploy_best_manifest(app_id, search_res)
            if ok:
                success_count += 1

            QTimer.singleShot(500, process_next)

        process_next()

    def ui_lock_manifest(self, app_id, game_name):
        from managers import steam_manager
        clean_name = game_name.replace("🔒 ", "").strip()
        success, msg = steam_manager.lock_game_version(app_id, self.steam_path, set_readonly=True, game_name=clean_name)
        if success:
            InfoBar.success("版本鎖定成功", f"「{clean_name}」{msg}", position=InfoBarPosition.TOP, parent=self)
            self.start_auto_update_flow() # Refresh UI
        else:
            InfoBar.error("鎖定失敗", msg, position=InfoBarPosition.TOP, parent=self)

    def ui_unlock_manifest(self, app_id, game_name):
        from managers import steam_manager
        clean_name = game_name.replace("🔒 ", "").strip()
        success, msg = steam_manager.unlock_game_version(app_id, self.steam_path)
        if success:
            InfoBar.info("已解除鎖定", f"「{clean_name}」{msg}", position=InfoBarPosition.TOP, parent=self)
            self.start_auto_update_flow() # Refresh UI
        else:
            InfoBar.error("解除鎖定失敗", msg, position=InfoBarPosition.TOP, parent=self)

    def ui_open_acf_folder(self, acf_path):
        try:
            import subprocess
            subprocess.run(["explorer", f"/select,{str(acf_path)}"])
        except Exception as e:
            print(f"Error opening explorer: {e}")

    def confirm_and_delete_lua(self, app_id, game_name):
        from qfluentwidgets import MessageBox
        w = MessageBox("確認刪除", f"確定要刪除「{game_name}」的 Lua 設定檔 ({app_id}.lua) 嗎？\n\n刪除後 Steam 將不再攔截並套用此遊戲的 Manifest。", self)
        if w.exec():
            self.ui_uninstall_lua(app_id)

    def switch_to_oneclick_install(self, app_id):
        self.page_switcher.setCurrentItem("oneclick")
        if hasattr(self, 'page_oneclick') and hasattr(self.page_oneclick, 'search_input'):
            self.page_oneclick.search_input.setText(str(app_id))
            if hasattr(self.page_oneclick, 'on_search_clicked'):
                self.page_oneclick.on_search_clicked()

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "選擇 Lua 資料夾", self.dir_entry.text())
        if folder:
            self.dir_entry.setText(folder)

    def save_and_reload(self):
        new_dir = self.dir_entry.text().strip()
        if not os.path.exists(new_dir):
            InfoBar.error("錯誤", f"找不到指定的資料夾：\n{new_dir}", position=InfoBarPosition.TOP, parent=self)
            return
        self.config["lua_dir"] = new_dir
        save_config(self.config)
        self.start_auto_update_flow()

    def update_ost_status(self):
        if not self.steam_path:
            self.lbl_ost_status.setText("OpenSteamTools 狀態: 找不到 Steam 安裝路徑")
            self.lbl_ost_status.setStyleSheet(f"color: {get_state_color('error')};")
            self.btn_install_ost.setEnabled(False)
            self.btn_uninstall_ost.setEnabled(False)
            return
            
        dlls = ["OpenSteamTool.dll", "dwmapi.dll", "xinput1_4.dll"]
        is_installed = all((self.steam_path / dll).exists() for dll in dlls)
        
        if is_installed:
            from managers import steam_manager
            steam_manager.ensure_manifest_lua(self.steam_path)
            self.lbl_ost_status.setText("OpenSteamTools 狀態: ✅ 已部署 (完美運行中)")
            self.lbl_ost_status.setStyleSheet(f"color: {get_state_color('success')};")
            self.btn_install_ost.setEnabled(False)
            self.btn_uninstall_ost.setEnabled(True)
        else:
            self.lbl_ost_status.setText("OpenSteamTools 狀態: ❌ 未安裝")
            self.lbl_ost_status.setStyleSheet(f"color: {get_state_color('error')};")
            self.btn_install_ost.setEnabled(True)
            self.btn_uninstall_ost.setEnabled(False)
            
        if hasattr(self, 'page_oneclick'):
            self.page_oneclick.check_ost_status()

    def install_ost(self):
        if not self.steam_path: return
        from managers import steam_manager
        success, msg = steam_manager.install_opensteamtools(self.steam_path)
        if success:
            InfoBar.success("成功", msg, position=InfoBarPosition.TOP, parent=self)
        else:
            InfoBar.error("錯誤", msg, position=InfoBarPosition.TOP, parent=self)
        self.update_ost_status()

    def uninstall_ost(self):
        if not self.steam_path: return
        from managers import steam_manager
        success, msg = steam_manager.uninstall_opensteamtools(self.steam_path)
        if success:
            InfoBar.success("成功", msg, position=InfoBarPosition.TOP, parent=self)
        else:
            InfoBar.error("錯誤", msg, position=InfoBarPosition.TOP, parent=self)
        self.update_ost_status()

    def open_defender_settings(self):
        try:
            import os
            os.startfile("windowsdefender://threatsettings")
        except:
            pass

    def ui_install_onlinefix(self, app_id, app_name, source):
        if not source: return
        
        # Determine RAR path from cloud
        rar_path = None
        if source and source.get('cloud_rar'):
            self.lbl_status.setText("⏳ 正在從 Google Drive 下載補丁...")
            self.progress_bar.show()
            QApplication.processEvents()
            dl_path = onlinefix_manager.download_cloud_patch(app_id, app_name, source['cloud_rar'])
            self.progress_bar.hide()
            if not dl_path:
                InfoBar.error("下載失敗", "無法從 Google Drive 取得補丁", position=InfoBarPosition.TOP, parent=self)
                return
            rar_path = dl_path

        game_dir = onlinefix_manager._find_steam_game_dir(app_id)
        if not game_dir:
            game_dir = QFileDialog.getExistingDirectory(self, "選擇此遊戲的【安裝根目錄】")
            if not game_dir: return
        
        success, msg = onlinefix_manager.install_fix(app_id, rar_path, game_dir)
        if success:
            InfoBar.success("安裝成功", f"補丁已部署並備份原始檔！", position=InfoBarPosition.TOP, parent=self)
            self.populate_table(self.last_results) # Refresh table status
        else:
            InfoBar.error("安裝失敗", msg, position=InfoBarPosition.TOP, parent=self)
            
    def ui_uninstall_onlinefix(self, app_id, app_name, source):
        # Determine RAR path for comparison
        rar_path = None
        if source:
            rar_path = source.get('local_rar')
            if not rar_path and source.get('cloud_rar'):
                rar_path = str(onlinefix_manager.LOCAL_PATCH_DIR / source['cloud_rar']['path'])
                if not os.path.exists(rar_path):
                    self.lbl_status.setText("⏳ 正在從 Google Drive 下載比對檔...")
                    self.progress_bar.show()
                    QApplication.processEvents()
                    dl_path = onlinefix_manager.download_cloud_patch(app_id, app_name, source['cloud_rar'])
                    self.progress_bar.hide()
                    rar_path = dl_path
                    
        success, msg = onlinefix_manager.uninstall_fix(app_id, rar_path)
        if success:
            if "驗證檔案完整性" in msg:
                InfoBar.warning("移除提示 (自行安裝)", msg, duration=8000, position=InfoBarPosition.TOP, parent=self)
            else:
                InfoBar.success("移除成功", msg, position=InfoBarPosition.TOP, parent=self)
            self.start_auto_update_flow() # Refresh tree fully
        else:
            InfoBar.error("移除失敗", msg, position=InfoBarPosition.TOP, parent=self)

    def ui_install_lua(self, app_id, source):
        success, msg = onlinefix_manager.install_lua(app_id, source, self.config["lua_dir"])
        if success:
            InfoBar.success("安裝成功", "Lua 設定檔已安裝", position=InfoBarPosition.TOP, parent=self)
            self.start_auto_update_flow() # Refresh tree
        else:
            InfoBar.error("安裝失敗", msg, position=InfoBarPosition.TOP, parent=self)
            
    def ui_uninstall_lua(self, app_id):
        success, msg = onlinefix_manager.uninstall_lua(app_id, self.config["lua_dir"])
        if success:
            InfoBar.success("移除成功", "Lua 設定檔已移除", position=InfoBarPosition.TOP, parent=self)
            self.start_auto_update_flow() # Refresh tree
        else:
            InfoBar.error("移除失敗", msg, position=InfoBarPosition.TOP, parent=self)

    def check_defender_status(self):
        is_disabled = False
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows Defender\Real-Time Protection", 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, "DisableRealtimeMonitoring")
            is_disabled = (value == 1)
            winreg.CloseKey(key)
        except Exception:
            is_disabled = False

        if is_disabled:
            self.lbl_defender_status.setText("Defender 狀態: ❌ 已關閉 (安全，不干擾破解)")
            self.lbl_defender_status.setStyleSheet(f"color: {get_state_color('success')};")
            # Low-frequency polling when disabled (safe state) to conserve resources
            self.defender_timer.setInterval(3000)
        else:
            self.lbl_defender_status.setText(f"Defender 狀態: ⚠️ 開啟中 (請關閉 <span style='color: {get_state_color('error')}; font-weight: bold;'>即時保護</span> 功能)")
            self.lbl_defender_status.setStyleSheet(f"color: {get_state_color('warning')};")
            # High-frequency polling when enabled (warning state) for real-time feedback
            self.defender_timer.setInterval(500)

    def start_auto_update_flow(self):
        lua_dir = self.dir_entry.text().strip()
        if not os.path.exists(lua_dir):
            self.lbl_status.setText(f"找不到資料夾: {lua_dir}")
            return
            
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.is_cancelled = True
            self.worker.wait()
            
        filenames = sorted([f for f in os.listdir(lua_dir) if f.endswith(".lua")])
        initial_items = []
        import re
        from managers import version_resolver
        for filename in filenames:
            appid = filename[:-4]
            if not appid.isdigit():
                continue
            filepath = os.path.join(lua_dir, filename)
            game_name = "未知遊戲"
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    chunk = f.read(512)
                m = re.search(r'--\s*\d+\s*-\s*(.+)', chunk)
                if m and m.group(1).strip():
                    game_name = m.group(1).strip()
            except:
                pass
            if not game_name or game_name == "未知遊戲":
                try:
                    from managers import name_resolver
                    game_name = name_resolver.resolve_game_name(appid, lua_path=filepath, steam_path=self.steam_path, allow_network=False)
                except Exception:
                    pass

            # 快速本機讀取當前版本日期 (0ms)
            local_date, _ = version_resolver.get_local_version_date(appid, lua_dir=lua_dir, steam_path=self.steam_path)

            initial_items.append({
                "appid": appid,
                "game_name": game_name,
                "local_date": local_date,
                "latest_date": "查詢中...",
                "version_status": "比對中...",
                "status": "up_to_date",
                "filepath": filepath
            })
            
        self.checking_appids = set(str(r["appid"]) for r in initial_items)
        if not self.loading_timer.isActive():
            self.loading_timer.start(350)
            
        self.populate_initial_table(initial_items)
        
        self.btn_update.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        self.lbl_status.setText(f"🔄 正在整理遊戲清單 (共 {len(initial_items)} 個遊戲)...")
        
        self.worker = UpdateWorker(initial_items, steam_path=self.steam_path, lua_dir=lua_dir)
        self.worker.progress.connect(self.update_progress)
        self.worker.item_checked.connect(self.on_item_checked)
        self.worker.finished.connect(self.on_update_finished)
        self.worker.start()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            lua_dir = self.dir_entry.text().strip()
            if not os.path.exists(lua_dir):
                InfoBar.error("錯誤", "目前指定的 Lua 資料夾不存在，無法複製", position=InfoBarPosition.TOP, parent=self)
                return
                
            copied = 0
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path.lower().endswith('.lua'):
                    try:
                        shutil.copy2(file_path, lua_dir)
                        copied += 1
                    except Exception as e:
                        InfoBar.error("錯誤", f"複製失敗: {e}", position=InfoBarPosition.TOP, parent=self)
            
            if copied > 0:
                InfoBar.success("成功", f"成功複製 {copied} 個 Lua 檔案！", position=InfoBarPosition.TOP, parent=self)
                self.start_auto_update_flow()

    def update_progress(self, current, total):
        if total > 0:
            self.progress_bar.setValue(int((current / total) * 100))

    def format_source_text(self, local, cloud):
        if local and cloud: return "本+雲"
        if local: return "本地✅"
        if cloud: return "雲端✅"
        if self.cloud_pending: return "查詢中"
        return "無數據"

    def animate_loading_dots(self):
        if not hasattr(self, 'items_map') or not self.items_map:
            return
        self.loading_dots_count = (self.loading_dots_count + 1) % 4
        dots = "." * self.loading_dots_count
        loading_text = f"查詢中{dots}"
        comparing_text = f"比對中{dots}"
        
        # 最新日期 (Col 3) 與版本狀態 (Col 4)
        for appid in list(self.checking_appids):
            child = self.items_map.get(appid)
            if child:
                if child.text(3).startswith("查詢中"):
                    child.setText(3, loading_text)
                    child.sort_data[3] = loading_text
                if child.text(4).startswith("比對中"):
                    child.setText(4, comparing_text)
                    child.sort_data[4] = comparing_text
                
        # 網盤來源 (Col 6: Lua, Col 7: 補丁)
        if self.cloud_pending:
            for appid, child in self.items_map.items():
                if child.text(6).startswith("查詢中"):
                    child.setText(6, loading_text)
                    child.sort_data[6] = loading_text
                if child.text(7).startswith("查詢中"):
                    child.setText(7, loading_text)
                    child.sort_data[7] = loading_text

    def refresh_sources_column(self):
        from PySide6.QtGui import QColor, QBrush
        self.cloud_pending = False
        if not hasattr(self, 'items_map') or not self.items_map:
            return
        target_apps = {str(r.get("appid", "")): str(r.get("game_name", "")) for r in getattr(self, 'last_results', []) if r.get("game_name") and r.get("game_name") != "未知遊戲"}
        sources = onlinefix_manager.get_patch_sources(target_apps=target_apps, allow_network=False)
        for appid, child in self.items_map.items():
            app_src = sources.get(appid, {})
            child.setText(6, self.format_source_text(app_src.get('local_lua'), app_src.get('cloud_lua')))
            child.setText(7, self.format_source_text(app_src.get('local_rar'), app_src.get('cloud_rar')))
            child.setForeground(6, QBrush(QColor(get_state_color("success") if "✅" in child.text(6) or "+" in child.text(6) else get_state_color("text_muted"))))
            child.setForeground(7, QBrush(QColor(get_state_color("success") if "✅" in child.text(7) or "+" in child.text(7) else get_state_color("text_muted"))))
            child.sort_data[6] = child.text(6)
            child.sort_data[7] = child.text(7)
            
        if len(self.checking_appids) == 0:
            self.loading_timer.stop()

    def populate_initial_table(self, items):
        from PySide6.QtGui import QColor, QBrush
        from PySide6.QtCore import Qt
        
        self.last_results = items
        self.tree.clear()
        
        # Category Folders (統一分類，不再依有無更新拆分)
        self.node_games = CustomTreeWidgetItem(self.tree, is_category=True, category_priority=0)
        self.node_games.setText(0, "📁 本機遊戲清單")
        self.node_games.setFirstColumnSpanned(True)
        self.node_games.setExpanded(True)
        self.node_games.setForeground(0, QBrush(QColor(get_state_color("text"))))

        self.node_incomplete = CustomTreeWidgetItem(self.tree, is_category=True, category_priority=1)
        self.node_incomplete.setText(0, "📁 殘缺檔案 (缺少 Manifest 實體檔，不支援安裝與運行)")
        self.node_incomplete.setFirstColumnSpanned(True)
        self.node_incomplete.setExpanded(True)
        self.node_incomplete.setForeground(0, QBrush(QColor(get_state_color("warning"))))

        self.node_error = CustomTreeWidgetItem(self.tree, is_category=True, category_priority=2)
        self.node_error.setText(0, "📁 讀取失敗 / 網路異常")
        self.node_error.setFirstColumnSpanned(True)
        self.node_error.setExpanded(True)
        self.node_error.setForeground(0, QBrush(QColor(get_state_color("error"))))
        
        self.items_map = {}
        bg_colors = [get_state_color("bg_stripe_1"), get_state_color("bg_stripe_2")]
        color_idx = 0
        incomplete_count = 0
        
        target_apps = {str(r.get("appid", "")): str(r.get("game_name", "")) for r in items if r.get("game_name") and r.get("game_name") != "未知遊戲"}
        sources = onlinefix_manager.get_patch_sources(target_apps=target_apps, allow_network=False)
        
        from managers import steam_manager
        for r in items:
            appid = str(r.get("appid", ""))
            game_name = str(r.get("game_name", ""))
            local_date = str(r.get("local_date", "未知"))
            latest_date = str(r.get("latest_date", "查詢中..."))
            version_status = str(r.get("version_status", "比對中..."))

            # 檢查 Manifest 完整度 (安全規範：缺少 manifest 判定為殘缺檔案)
            m_status = steam_manager.get_lua_manifest_status(appid, self.steam_path, self.config.get("lua_dir"))
            lock_info = steam_manager.get_game_manifest_lock_info(appid, self.steam_path)
            is_locked = lock_info.get("is_locked", False)

            if m_status.get("is_incomplete"):
                parent = self.node_incomplete
                fg_color = get_state_color("warning")
                display_name = f"⚠️ [殘缺] {game_name}"
                version_status = "缺檔"
                incomplete_count += 1
            else:
                parent = self.node_games
                fg_color = get_state_color("text")
                prefix = "🔒 " if is_locked else ""
                display_name = f"{prefix}{game_name}"
                
            bg_brush = QBrush(QColor(bg_colors[color_idx % 2]))
            color_idx += 1
            
            sort_data = {
                0: appid, 1: game_name, 2: local_date, 3: latest_date, 4: version_status, 5: "", 6: "", 7: "", "idx": 0
            }
            child = CustomTreeWidgetItem(parent, sort_data=sort_data)
            child.setText(0, appid)
            child.setText(1, display_name)
            child.setText(2, local_date)
            child.setText(3, latest_date)
            child.setText(4, version_status)
            child.setToolTip(1, f"遊戲名稱: {game_name}\nManifest 狀態: {m_status.get('status_text', '')}\n版本鎖定保護: {lock_info['status_text']}\n(右鍵點擊可進行鎖定/解鎖/補齊 Manifest)")
            child.setToolTip(4, f"當前版本日期: {local_date}\n最新版本發布: {latest_date}\n版本狀態: {version_status}")
                
            child.setForeground(0, QBrush(QColor(fg_color)))
            child.setForeground(1, QBrush(QColor(fg_color)))
            child.setForeground(2, QBrush(QColor(get_state_color("text"))))
            child.setForeground(3, QBrush(QColor(get_state_color("text_muted"))))
            child.setForeground(4, QBrush(QColor(get_state_color("text_muted"))))
            
            for i in range(8):
                child.setBackground(i, bg_brush)
                child.setTextAlignment(i, Qt.AlignVCenter | Qt.AlignLeft)
                
            of_status = onlinefix_manager.get_fix_status(appid)
            child.setText(5, of_status)
            
            app_src = sources.get(appid, {})
            child.setText(6, self.format_source_text(app_src.get('local_lua'), app_src.get('cloud_lua')))
            child.setText(7, self.format_source_text(app_src.get('local_rar'), app_src.get('cloud_rar')))
            if "⚠️" in of_status:
                child.setForeground(5, QBrush(QColor(get_state_color("error"))))
            elif "✅" in of_status:
                child.setForeground(5, QBrush(QColor(get_state_color("success"))))
            else:
                child.setForeground(5, QBrush(QColor(fg_color)))
                
            if "查詢中" in child.text(6):
                child.setForeground(6, QBrush(QColor(get_state_color("warning"))))
            elif "✅" in child.text(6) or "+" in child.text(6):
                child.setForeground(6, QBrush(QColor(get_state_color("success"))))
            else:
                child.setForeground(6, QBrush(QColor(get_state_color("text_muted"))))
                
            if "查詢中" in child.text(7):
                child.setForeground(7, QBrush(QColor(get_state_color("warning"))))
            elif "✅" in child.text(7) or "+" in child.text(7):
                child.setForeground(7, QBrush(QColor(get_state_color("success"))))
            else:
                child.setForeground(7, QBrush(QColor(get_state_color("text_muted"))))
                
            self.items_map[appid] = child
            
        self.tree.expandAll()

        # 更新殘缺檔案修復橫幅
        if incomplete_count > 0:
            self.manifest_warning_card.show()
            self.lbl_manifest_warning.setText(f"⚠️ 偵測到本地有 {incomplete_count} 款遊戲缺少 Manifest 實體檔（已被判定為殘缺檔案，不支援安裝與運行）")
            self.btn_batch_repair_manifests.setText(f"⚡ 批次補齊缺少之 Manifest ({incomplete_count} 款)")
        else:
            self.manifest_warning_card.hide()

    def populate_table(self, results):
        self.populate_initial_table(results)

    def on_item_checked(self, r):
        appid = str(r.get("appid", ""))
        self.checking_appids.discard(appid)
        child = getattr(self, 'items_map', {}).get(appid)
        if not child: return
        
        from PySide6.QtGui import QColor, QBrush
        from PySide6.QtCore import Qt
        
        if hasattr(self, 'last_results'):
            for i, res in enumerate(self.last_results):
                if str(res.get("appid")) == appid:
                    self.last_results[i] = r
                    break
                
        status = r.get("status", "up_to_date")
        game_name = r.get("game_name", child.text(1))
        local_date = str(r.get("local_date", child.text(2)))
        latest_date = str(r.get("latest_date", "未知"))
        version_status = str(r.get("version_status", "未知"))
        is_latest = r.get("is_latest", True)
        
        from managers import steam_manager, name_resolver
        m_status = steam_manager.get_lua_manifest_status(appid, self.steam_path, self.config.get("lua_dir"))
        lock_info = steam_manager.get_game_manifest_lock_info(appid, self.steam_path)
        is_locked = lock_info.get("is_locked", False)
        prefix = "🔒 " if is_locked else ""

        # Resolve clean game name
        if not game_name or game_name == "未知遊戲" or "讀取失敗" in game_name:
            resolved = name_resolver.resolve_game_name(appid, steam_path=self.steam_path)
            if resolved and resolved != "未知遊戲":
                game_name = resolved

        import re
        clean_name = game_name.replace("⚠️ [殘缺] ", "").replace("🔒 ", "")
        clean_name = re.sub(r"\s*\[(?:v|Hotfix)[^\]]+\]$", "", clean_name)

        # 節點歸屬：全部統一收納在 self.node_games (不再依是否有新版本拆分)
        current_parent = child.parent()
        target_parent = self.node_games
        fg_color = get_state_color("text")
        
        if status == "error":
            target_parent = self.node_error
            fg_color = get_state_color("error")
            display_name = f"讀取失敗: {r.get('error_msg', '未知錯誤')}"
            version_status = "讀取失敗"
        elif status == "incomplete" or m_status.get("is_incomplete"):
            target_parent = self.node_incomplete
            fg_color = get_state_color("warning")
            display_name = f"⚠️ [殘缺] {clean_name}"
            version_status = "殘缺 (缺檔)"
        else:
            target_parent = self.node_games
            fg_color = get_state_color("text")
            display_name = f"{prefix}{clean_name}"
            
        if current_parent != target_parent:
            if current_parent:
                current_parent.removeChild(child)
            target_parent.insertChild(0, child)
            target_parent.setExpanded(True)
            
        # Update text across all columns
        child.setText(0, appid)
        child.setText(1, display_name)
        child.setText(2, local_date)
        child.setText(3, latest_date)
        child.setText(4, version_status)
        child.setToolTip(1, f"遊戲名稱: {clean_name}\nManifest 狀態: {m_status.get('status_text', '')}\n版本鎖定保護: {lock_info['status_text']}\n(右鍵點擊可進行鎖定/解鎖/補齊 Manifest)")
        child.setToolTip(4, f"當前版本日期: {local_date}\n最新版本發布: {latest_date}\n版本狀態: {version_status}\n(對比 generator.ryuu 搜尋結果)")
        
        of_status = onlinefix_manager.get_fix_status(appid)
        child.setText(5, of_status)
        
        sources = onlinefix_manager.get_patch_sources(target_apps={appid: game_name}, allow_network=False)
        app_src = sources.get(appid, {})
        child.setText(6, self.format_source_text(app_src.get('local_lua'), app_src.get('cloud_lua')))
        child.setText(7, self.format_source_text(app_src.get('local_rar'), app_src.get('cloud_rar')))

        # 判定此檔案是否需要更新 (多源聚合庫有新版可供自動更新，或版本狀態包含跨越版本)
        is_updatable = bool(
            r.get("has_available_update") or 
            r.get("ryuu_has_update") or 
            ("跨越" in str(version_status))
        )
        child.is_updatable = is_updatable

        if is_updatable:
            # 依使用者需求：需要更新的檔案整行全部文字替換為黃色顯示
            yellow_brush = QBrush(QColor(get_state_color("warning")))
            for col_idx in range(8):
                child.setForeground(col_idx, yellow_brush)
        else:
            # Update foreground colors
            child.setForeground(0, QBrush(QColor(fg_color)))
            child.setForeground(1, QBrush(QColor(fg_color)))
            child.setForeground(2, QBrush(QColor(get_state_color("text"))))
            child.setForeground(3, QBrush(QColor(get_state_color("text"))))
            if "0 版" in version_status:
                child.setForeground(4, QBrush(QColor(get_state_color("text_muted"))))
            elif "缺檔" in version_status or "殘缺" in version_status:
                child.setForeground(4, QBrush(QColor(get_state_color("warning"))))
            else:
                child.setForeground(4, QBrush(QColor(get_state_color("text_muted"))))
            
            if "⚠️" in of_status:
                child.setForeground(5, QBrush(QColor(get_state_color("error"))))
            elif "✅" in of_status:
                child.setForeground(5, QBrush(QColor(get_state_color("success"))))
            else:
                child.setForeground(5, QBrush(QColor(fg_color)))
                
            if "查詢中" in child.text(6):
                child.setForeground(6, QBrush(QColor(get_state_color("warning"))))
            elif "✅" in child.text(6) or "+" in child.text(6):
                child.setForeground(6, QBrush(QColor(get_state_color("success"))))
            else:
                child.setForeground(6, QBrush(QColor(get_state_color("text_muted"))))
                
            if "查詢中" in child.text(7):
                child.setForeground(7, QBrush(QColor(get_state_color("warning"))))
            elif "✅" in child.text(7) or "+" in child.text(7):
                child.setForeground(7, QBrush(QColor(get_state_color("success"))))
            else:
                child.setForeground(7, QBrush(QColor(get_state_color("text_muted"))))

        for col_idx in range(8):
            child.sort_data[col_idx] = child.text(col_idx)

    def on_update_finished(self):
        from PySide6.QtGui import QColor, QBrush
        self.btn_update.setEnabled(True)
        self.progress_bar.hide()
        self.checking_appids.clear()
        if not self.cloud_pending:
            self.loading_timer.stop()
            
        total_count = len(getattr(self, 'last_results', []))
        games_count = self.node_games.childCount()
        incomplete_count = self.node_incomplete.childCount()

        # 統計多源聚合來源 (GitHub / Ryuu / Lua.tools) 中有可用更新的遊戲數量
        updatable = [r for r in getattr(self, 'last_results', []) if (r.get("has_available_update") or r.get("ryuu_has_update"))]
        updatable_count = len(updatable)

        if updatable_count > 0:
            self.node_games.setText(0, f"📁 本機遊戲清單 (共 {games_count} 款，其中 {updatable_count} 款有最新版 Manifest 可更新 ⚡)")
            self.lbl_status.setText(f"✅ 檢查完成！共 {total_count} 個遊戲 (偵測到 {updatable_count} 款遊戲在多源聚合庫中有最新 Manifest，可執行自動更新)。")
            self.btn_auto_update_ryuu.setText(f"⚡ 一鍵自動更新 ({updatable_count} 款多源新版)")
            self.btn_auto_update_ryuu.show()
        else:
            self.node_games.setText(0, f"📁 本機遊戲清單 (共 {games_count} 款)")
            self.lbl_status.setText(f"✅ 檢查完成！共 {total_count} 個遊戲 (所有本地遊戲在 GitHub / Ryuu 上皆已是最新檔案)。")
            self.btn_auto_update_ryuu.hide()
        
        # Batch refresh all sources in case cloud cache finished in background
        target_apps = {str(r.get("appid", "")): str(r.get("game_name", "")) for r in getattr(self, 'last_results', []) if r.get("game_name") and r.get("game_name") != "未知遊戲"}
        sources = onlinefix_manager.get_patch_sources(target_apps=target_apps, allow_network=False)
        for appid, child in getattr(self, 'items_map', {}).items():
            app_src = sources.get(appid, {})
            child.setText(6, self.format_source_text(app_src.get('local_lua'), app_src.get('cloud_lua')))
            child.setText(7, self.format_source_text(app_src.get('local_rar'), app_src.get('cloud_rar')))
            if getattr(child, 'is_updatable', False):
                yellow_brush = QBrush(QColor(get_state_color("warning")))
                child.setForeground(6, yellow_brush)
                child.setForeground(7, yellow_brush)
            else:
                if "查詢中" in child.text(6):
                    child.setForeground(6, QBrush(QColor(get_state_color("warning"))))
                elif "✅" in child.text(6) or "+" in child.text(6):
                    child.setForeground(6, QBrush(QColor(get_state_color("success"))))
                else:
                    child.setForeground(6, QBrush(QColor(get_state_color("text_muted"))))
                    
                if "查詢中" in child.text(7):
                    child.setForeground(7, QBrush(QColor(get_state_color("warning"))))
                elif "✅" in child.text(7) or "+" in child.text(7):
                    child.setForeground(7, QBrush(QColor(get_state_color("success"))))
                else:
                    child.setForeground(7, QBrush(QColor(get_state_color("text_muted"))))
        
        self.tree.expandAll()

    def closeEvent(self, event):
        try:
            import base64
            header_state = self.tree.header().saveState()
            self.config['tree_header_state_v2'] = base64.b64encode(header_state.data()).decode('utf-8')
            config_manager.save_config(self.config)
        except Exception:
            pass
        super().closeEvent(event)


if __name__ == "__main__":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("mycompany.steammanifestupdater.1")
    except:
        pass
        
    app = QApplication(sys.argv)
    
    # 設置全域字型 (Impeccable Typography)
    font = QFont("Segoe UI Variable Display", 10)
    font.insertSubstitution("Segoe UI Variable Display", "Microsoft YaHei UI")
    app.setFont(font)
    
    setTheme(Theme.AUTO) # Allow adaptive themes instead of forced dark
    
    from managers import config_manager
    icon_path = str(config_manager._root_dir / "assets" / "icon.ico")
        
    app.setWindowIcon(QIcon(icon_path))
    
    # Auto-start background daemon if not already active
    try:
        from utils import autostart
        if not autostart.is_daemon_running():
            autostart.start_daemon()
    except Exception as e:
        print(f"Auto-start daemon info: {e}")
    
    window = SteamManifestApp()
    window.setWindowIcon(QIcon(icon_path))
    window.show()
    sys.exit(app.exec())
