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

VERSION = "1.0.3"

# Suppress stdout/stderr to prevent QFluentWidgets Pro message
# sys.stdout
# sys.stderr
os.environ["QT_API"] = "pyside6"

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

class UpdateWorker(QThread):
    progress = Signal(int, int) # completed, total
    finished = Signal(list)
    status = Signal(str)

    def __init__(self, lua_dir):
        super().__init__()
        self.lua_dir = lua_dir

    def run(self):
        filenames = sorted([f for f in os.listdir(self.lua_dir) if f.endswith(".lua")])
        total_files = len(filenames)
        completed = 0
        results = []

        import concurrent.futures

        def process_single_lua(filename):
            nonlocal completed
            filepath = os.path.join(self.lua_dir, filename)
            appid = filename.replace(".lua", "")
            
            result = {
                "appid": appid,
                "status": "normal",
                "game_name": "Unknown",
                "error_msg": "",
                "rows": [],
                "update_date": "未知"
            }
            
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                result["status"] = "error"
                result["error_msg"] = str(e)
                completed += 1
                self.progress.emit(completed, total_files)
                return result
                
            import re
            name_match = re.search(r'--\s*\d+\s*-\s*(.+)', content)
            if name_match:
                result["game_name"] = name_match.group(1).strip()
                
            pattern = re.compile(r'(setManifestid\(\s*(\d+)\s*,\s*"(\d+)"(?:,\s*(\d+))?\s*\))')
            matches = pattern.findall(content)
            
            if not matches:
                result["status"] = "error"
                result["error_msg"] = "找不到 setManifestid (格式不符)"
                completed += 1
                self.progress.emit(completed, total_files)
                return result
                
            info = get_app_info(appid)
            is_error = False
            build_id = "未知"
            
            if info:
                if "error" in info:
                    is_error = True
                    result["error_msg"] = info["error"]
                    build_id = f"錯誤: {info['error']}"
                else:
                    common_data = info.get("common", {})
                    if "name" in common_data:
                        result["game_name"] = common_data["name"]
                    
                    depots_data = info.get("depots", {})
                    if "branches" in depots_data and "public" in depots_data["branches"]:
                        public_branch = depots_data["branches"]["public"]
                        if "buildid" in public_branch:
                            build_id = str(public_branch["buildid"])
                        if "timeupdated" in public_branch:
                            ts = public_branch["timeupdated"]
                            try:
                                from datetime import datetime
                                result["update_date"] = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
                            except:
                                pass
            else:
                is_error = True
                result["error_msg"] = "API無回應"
                build_id = "錯誤: API"
                
            is_updated_any = False
            new_content = content
            
            for match in matches:
                old_str = match[0]
                depot_id = match[1]
                old_manifest = match[2]
                old_size = match[3] if len(match) > 3 and match[3] else None
                
                api_manifest_id = None
                api_size = None
                if not is_error and info:
                    public_manifest = info.get("depots", {}).get(depot_id, {}).get("manifests", {}).get("public", {})
                    api_manifest_id = public_manifest.get("gid")
                    api_size = public_manifest.get("size")
                    
                is_updated = False
                if api_manifest_id and (str(api_manifest_id) != old_manifest or (old_size and api_size and str(api_size) != old_size)):
                    is_updated = True
                    is_updated_any = True
                    if old_size and api_size:
                        new_str = f'setManifestid({depot_id}, "{api_manifest_id}", {api_size})'
                    else:
                        new_str = f'setManifestid({depot_id}, "{api_manifest_id}")'
                    new_content = new_content.replace(old_str, new_str)
                    
                result["rows"].append({
                    "depot": depot_id,
                    "manifest": str(api_manifest_id) if is_updated else old_manifest,
                    "build_id": build_id,
                    "is_updated": is_updated
                })
                
            if is_error:
                result["status"] = "error"
            elif is_updated_any:
                result["status"] = "updated"
                try:
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(new_content)
                except Exception as e:
                    result["status"] = "error"
                    result["error_msg"] = f"寫入失敗: {e}"
            else:
                result["status"] = "normal"
                
            completed += 1
            self.progress.emit(completed, total_files)
            return result

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(process_single_lua, f) for f in filenames]
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

        self.finished.emit(results)


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
        
        # Pre-cache online-fix sources in background
        import threading
        def _precache():
            onlinefix_manager.get_patch_sources()
        threading.Thread(target=_precache, daemon=True).start()
        
        self.update_ost_status()
        self.start_auto_update_flow()
        
        # Zero-overhead real-time Defender monitoring via Registry
        self.defender_timer = QTimer(self)
        self.defender_timer.timeout.connect(self.check_defender_status)
        self.defender_timer.start(500) # Initial poll at 500ms
        self.check_defender_status()


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
        self.btn_update = PrimaryPushButton("重新整理與全自動更新", self)
        self.btn_update.clicked.connect(self.start_auto_update_flow)
        
        lua_layout.addWidget(title_label)
        lua_layout.addWidget(self.dir_entry, 1)
        lua_layout.addWidget(btn_browse)
        lua_layout.addWidget(btn_reload)
        lua_layout.addWidget(self.btn_update)
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
        
        self.tree = TreeWidget(self)
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels([
            "AppID", "遊戲名稱 (Game)", "更新日期 (Update Date)", "Online-Fix 狀態", "Lua 來源", "補丁 來源"
        ])
        
        self.tree.setColumnWidth(0, 100)
        self.tree.setColumnWidth(1, 350)
        self.tree.setColumnWidth(2, 180)
        self.tree.setColumnWidth(3, 150)
        self.tree.setColumnWidth(4, 100)
        self.tree.setColumnWidth(5, 100)
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
        
        # Restore header state if saved
        import base64
        from PySide6.QtCore import QByteArray
        saved_state = self.config.get('tree_header_state')
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
        
        # Setup switcher
        self.page_switcher.addItem("local", "本機檔案")
        self.page_switcher.addItem("install", "安裝遊戲")
        self.page_switcher.addItem("oneclick", "一鍵安裝")
        self.page_switcher.currentItemChanged.connect(
            lambda k: self.stacked_widget.setCurrentIndex(0 if k == "local" else 1 if k == "install" else 2)
        )
        self.page_switcher.setCurrentItem("local")

    def show_settings_dialog(self):
        from ui.settings_ui import SettingsDialog
        dialog = SettingsDialog(self, config=self.config)
        if dialog.exec():
            # Update config object
            self.config["gdrive_url"] = dialog.gdrive_input.text().strip()
            self.config["onlinefix_domain"] = dialog.onlinefix_input.text().strip()
            self.config["luatools_domain"] = dialog.luatools_input.text().strip()
            
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
            onlinefix_manager.GDRIVE_FOLDER_URL = self.config["gdrive_url"]
            # NOTE: We'll require a restart for cache_dir changes to take full effect safely
            
            InfoBar.success("設定已儲存", "設定已更新！部分路徑變更可能需要重開程式才會完全生效。", position=InfoBarPosition.TOP, parent=self)

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
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        
        sources = onlinefix_manager.get_patch_sources()
        has_source = app_id in sources
        app_src = sources.get(app_id, {})
        
        # Patch Actions
        if app_src.get('local_rar') or app_src.get('cloud_rar'):
            install_action = menu.addAction("📦 安裝 Online-Fix 補丁")
        else:
            install_action = menu.addAction("📦 安裝 Online-Fix (雲端/本地皆無檔案)")
            install_action.setEnabled(False)
            
        install_action.triggered.connect(lambda: self.ui_install_onlinefix(app_id, sources.get(app_id)))
        
        status = onlinefix_manager.get_fix_status(app_id)
        # Uninstall is allowed if we have a record OR if we have a source to compare with
        has_record = str(app_id) in onlinefix_manager._load_records()
        can_uninstall = has_record or (has_source and status != "未安裝")
        
        if can_uninstall:
            uninstall_action = menu.addAction("🗑️ 移除 Online-Fix 補丁")
            uninstall_action.triggered.connect(lambda: self.ui_uninstall_onlinefix(app_id, sources.get(app_id)))
            
            
        menu.exec_(self.tree.viewport().mapToGlobal(pos))

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
        from managers import config_manager
        base_dir = config_manager._root_dir
            
        opensteam_dir = base_dir / "opensteamtools"
        dlls = ["OpenSteamTool.dll", "dwmapi.dll", "xinput1_4.dll"]
        
        try:
            for dll in dlls:
                src = opensteam_dir / dll
                dst = self.steam_path / dll
                if src.exists():
                    shutil.copy2(src, dst)
                else:
                    raise FileNotFoundError(f"安裝檔案遺失: {src}")
            
            lua_dir = self.steam_path / "config" / "lua"
            lua_dir.mkdir(parents=True, exist_ok=True)
            InfoBar.success("成功", "OpenSteamTools 已經極速安裝完畢！", position=InfoBarPosition.TOP, parent=self)
        except Exception as e:
            InfoBar.error("錯誤", f"安裝失敗: {e}", position=InfoBarPosition.TOP, parent=self)
            
        self.update_ost_status()

    def uninstall_ost(self):
        if not self.steam_path: return
        dlls = ["OpenSteamTool.dll", "dwmapi.dll", "xinput1_4.dll"]
        try:
            for dll in dlls:
                dst = self.steam_path / dll
                if dst.exists():
                    dst.unlink()
            InfoBar.success("成功", "OpenSteamTools 已成功移除乾淨！", position=InfoBarPosition.TOP, parent=self)
        except Exception as e:
            InfoBar.error("錯誤", f"移除失敗 (請確認已完全關閉 Steam): {e}", position=InfoBarPosition.TOP, parent=self)
            
        self.update_ost_status()

    def open_defender_settings(self):
        try:
            import os
            os.startfile("windowsdefender://threatsettings")
        except:
            pass

    def ui_install_onlinefix(self, app_id, source):
        if not source: return
        
        # Determine RAR path
        rar_path = source.get('local_rar')
        if not rar_path and source.get('cloud_rar'):
            # Prompt user to download
            rar_path = str(onlinefix_manager.LOCAL_PATCH_DIR / source['cloud_rar']['path'])
            if not os.path.exists(rar_path):
                self.lbl_status.setText("⏳ 正在從 Google Drive 下載補丁...")
                self.progress_bar.show()
                QApplication.processEvents()
                dl_path = onlinefix_manager.download_cloud_patch(source['cloud_rar'])
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
            
    def ui_uninstall_onlinefix(self, app_id, source):
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
                    dl_path = onlinefix_manager.download_cloud_patch(source['cloud_rar'])
                    self.progress_bar.hide()
                    rar_path = dl_path
                    
        success, msg = onlinefix_manager.uninstall_fix(app_id, rar_path)
        if success:
            InfoBar.success("移除成功", "補丁已移除，原始檔案已還原！", position=InfoBarPosition.TOP, parent=self)
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
            self.lbl_defender_status.setText("Defender 即時保護: ❌ 已關閉 (安全，不干擾破解)")
            self.lbl_defender_status.setStyleSheet(f"color: {get_state_color('success')};")
            # Low-frequency polling when disabled (safe state) to conserve resources
            self.defender_timer.setInterval(3000)
        else:
            self.lbl_defender_status.setText("Defender 即時保護: ⚠️ 開啟中 (可能誤刪破解檔)")
            self.lbl_defender_status.setStyleSheet(f"color: {get_state_color('error')};")
            # High-frequency polling when enabled (warning state) for real-time feedback
            self.defender_timer.setInterval(500)

    def start_auto_update_flow(self):
        lua_dir = self.dir_entry.text().strip()
        if not os.path.exists(lua_dir):
            self.lbl_status.setText(f"找不到資料夾: {lua_dir}")
            return
            
        self.tree.clear()
        self.btn_update.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        self.lbl_status.setText("🔄 正在背景極速比對並更新 Lua...")
        
        self.worker = UpdateWorker(lua_dir)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.populate_table)
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
        self.progress_bar.setValue(int((current / total) * 100))

    def populate_table(self, results):
        from PySide6.QtGui import QColor, QBrush
        from PySide6.QtCore import Qt
        from datetime import datetime
        
        self.last_results = results
        self.btn_update.setEnabled(True)
        self.progress_bar.hide()
        self.lbl_status.setText(f"✅ 更新完成！共處理 {len(results)} 個遊戲。")
        
        self.tree.clear()
        
        # Category Folders (Order is guaranteed because SortingEnabled is False)
        node_updated = CustomTreeWidgetItem(self.tree, is_category=True, category_priority=0)
        node_updated.setText(0, "📁 本次啟動被修正的 Lua")
        node_updated.setFirstColumnSpanned(True)
        node_updated.setExpanded(True)
        node_updated.setForeground(0, QBrush(QColor("#00CC6A")))

        node_normal = CustomTreeWidgetItem(self.tree, is_category=True, category_priority=1)
        node_normal.setText(0, "📁 維持現狀 (已經是最新的)")
        node_normal.setFirstColumnSpanned(True)
        node_normal.setExpanded(True)
        node_normal.setForeground(0, QBrush(QColor("#FFFFFF")))

        node_error = CustomTreeWidgetItem(self.tree, is_category=True, category_priority=2)
        node_error.setText(0, "📁 讀取失敗 / 無法更新")
        node_error.setFirstColumnSpanned(True)
        node_error.setExpanded(True)
        node_error.setForeground(0, QBrush(QColor("#FF5C5C")))
        
        # Sort results by update date descending by default
        def get_ts(r):
            if r["update_date"] == "未知": return 0
            try: return datetime.strptime(r["update_date"], "%Y-%m-%d %H:%M:%S").timestamp()
            except: return 0
        results.sort(key=get_ts, reverse=True)
        
        # Zebra striping PER GAME
        bg_colors = ["#222222", "#2B2B2B"]
        color_idx = 0
        
        # Fetch sources once per refresh
        sources = onlinefix_manager.get_patch_sources()
        
        def _fmt_source(local, cloud):
            if local and cloud: return "本+雲"
            if local: return "本地✅"
            if cloud: return "雲端✅"
            return "無數據"
            
        color_idx = 0
        for r in results:
            if r["status"] == "updated":
                parent = node_updated
                fg_color = "#00CC6A"
            elif r["status"] == "normal":
                parent = node_normal
                fg_color = "#FFFFFF"
            else:
                parent = node_error
                fg_color = "#FF5C5C"
                
            bg_brush = QBrush(QColor(bg_colors[color_idx % 2]))
            color_idx += 1
            
            appid = str(r.get("appid", ""))
            game_name = str(r.get("game_name", ""))
            update_date = str(r.get("update_date", ""))
                
            if r["status"] == "error":
                sort_data = {
                    0: appid, 1: game_name, 2: update_date, 3: "", 4: "", 5: "", "idx": 0
                }
                child = CustomTreeWidgetItem(parent, sort_data=sort_data)
                child.setText(0, appid)
                child.setText(1, f"讀取失敗: {r.get('error_msg', '未知錯誤')}")
                child.setForeground(0, QBrush(QColor(fg_color)))
                child.setForeground(1, QBrush(QColor(fg_color)))
                child.setBackground(0, bg_brush)
                child.setBackground(1, bg_brush)
                for i in range(6):
                    child.setTextAlignment(i, Qt.AlignVCenter | Qt.AlignLeft)
            else:
                sort_data = {
                    0: appid, 1: game_name, 2: update_date, 3: "", 4: "", 5: "", "idx": 0
                }
                child = CustomTreeWidgetItem(parent, sort_data=sort_data)
                child.setText(0, appid)
                child.setText(1, game_name)
                child.setText(2, update_date)
                
                of_status = onlinefix_manager.get_fix_status(appid)
                child.setText(3, of_status)
                
                # Set Lua and Patch sources
                app_src = sources.get(appid, {})
                child.setText(4, _fmt_source(app_src.get('local_lua'), app_src.get('cloud_lua')))
                child.setText(5, _fmt_source(app_src.get('local_rar'), app_src.get('cloud_rar')))
                
                for col_idx in range(6):
                    child.setBackground(col_idx, bg_brush)
                    if col_idx == 3:
                        if "⚠️" in of_status:
                            child.setForeground(col_idx, QBrush(QColor("#FF5C5C")))
                        elif "✅" in of_status:
                            child.setForeground(col_idx, QBrush(QColor("#00CC6A")))
                        else:
                            child.setForeground(col_idx, QBrush(QColor(fg_color)))
                    elif col_idx in (4, 5):
                        # Make the source columns easily visible
                        child.setForeground(col_idx, QBrush(QColor("#00CC6A" if "✅" in child.text(col_idx) or "+" in child.text(col_idx) else "#888888")))
                    else:
                        child.setForeground(col_idx, QBrush(QColor(fg_color)))
                    child.setTextAlignment(col_idx, Qt.AlignVCenter | Qt.AlignLeft)

    def closeEvent(self, event):
        try:
            import base64
            header_state = self.tree.header().saveState()
            self.config['tree_header_state'] = base64.b64encode(header_state.data()).decode('utf-8')
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
    
    window = SteamManifestApp()
    window.setWindowIcon(QIcon(icon_path))
    window.show()
    sys.exit(app.exec())
