from ui.theme_utils import get_state_color
import os
import re
import winreg
import urllib.request
import urllib.parse
import json
from pathlib import Path
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from qfluentwidgets import (
    CardWidget, StrongBodyLabel, BodyLabel, PrimaryPushButton, PushButton, 
    LineEdit, InfoBar, SearchLineEdit, TitleLabel, ImageLabel
)

class SteamSearchThread(QThread):
    result_ready = Signal(object) # None or dict {"id": appid, "name": game_name}
    
    def __init__(self, query=None, appid=None, parent=None):
        super().__init__(parent)
        self.query = query
        self.appid = appid
        
    def run(self):
        try:
            if self.appid:
                url = f"https://store.steampowered.com/api/appdetails?appids={self.appid}&l=english"
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as res:
                    data = json.loads(res.read().decode('utf-8'))
                    app_data = data.get(str(self.appid), {})
                    if app_data.get('success'):
                        self.result_ready.emit({'id': self.appid, 'name': app_data['data'].get('name', '')})
                    else:
                        self.result_ready.emit({'id': self.appid, 'name': ''})
                    return
            elif self.query:
                query = urllib.parse.quote(self.query)
                url = f"https://store.steampowered.com/api/storesearch/?term={query}&l=english&cc=US"
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as res:
                    data = json.loads(res.read().decode('utf-8'))
                    if data.get('items') and len(data['items']) > 0:
                        self.result_ready.emit(data['items'][0])
                        return
            self.result_ready.emit(None)
        except Exception:
            if self.appid:
                self.result_ready.emit({'id': self.appid, 'name': ''})
            else:
                self.result_ready.emit(None)


class OneClickInstallWidget(QWidget):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.current_appid = None
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(20)
        
        # Stacked widget to switch between "Blocker" and "Main Content"
        self.stack = QStackedWidget(self)
        self.main_layout.addWidget(self.stack)
        
        self._init_blocker_page()
        self._init_main_page()
        
        self.check_ost_status()
        
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.refresh_all_status)
        self.status_timer.start(1500)
        
        self.is_deploying = False
        self.deploy_step = 0

    def _init_blocker_page(self):
        self.blocker_page = QWidget()
        layout = QVBoxLayout(self.blocker_page)
        layout.setAlignment(Qt.AlignCenter)
        
        icon = TitleLabel("⚠️ 必須先安裝 OpenSteamTools", self)
        icon.setAlignment(Qt.AlignCenter)
        desc = BodyLabel("這是一鍵安裝的必要依賴組件。請先前往「設定」完成安裝後再來使用此功能。", self)
        desc.setAlignment(Qt.AlignCenter)
        
        btn = PrimaryPushButton("立即檢查安裝狀態", self)
        btn.clicked.connect(self.check_ost_status)
        btn.setFixedWidth(200)
        
        layout.addWidget(icon)
        layout.addSpacing(10)
        layout.addWidget(desc)
        layout.addSpacing(20)
        layout.addWidget(btn, alignment=Qt.AlignCenter)
        self.stack.addWidget(self.blocker_page)

    def _init_main_page(self):
        self.main_page = QWidget()
        layout = QVBoxLayout(self.main_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        # 1. Search Bar
        search_card = CardWidget(self)
        search_layout = QVBoxLayout(search_card)
        search_label = StrongBodyLabel("🔍 搜尋遊戲 (支援名稱、AppID、網址)", self)
        
        search_h = QHBoxLayout()
        self.search_input = SearchLineEdit(self)
        self.search_input.setPlaceholderText("請輸入遊戲名稱 (如: Waterpark Simulator) 或貼上 Steam 網址")
        self.search_input.returnPressed.connect(self.perform_search)
        self.search_input.searchSignal.connect(self.perform_search)
        search_h.addWidget(self.search_input, 1)
        
        search_layout.addWidget(search_label)
        search_layout.addLayout(search_h)
        layout.addWidget(search_card)
        
        # 2. Status Board
        self.status_card = CardWidget(self)
        status_layout = QVBoxLayout(self.status_card)
        
        self.game_title_lbl = TitleLabel("尚未選擇遊戲", self)
        status_layout.addWidget(self.game_title_lbl)
        status_layout.addSpacing(10)
        
        # Checklist items
        self.chk_ost = StrongBodyLabel("⏳ 1. OpenSteamTools 安裝狀態: 檢查中...", self)
        self.chk_def = StrongBodyLabel("⏳ 2. Defender 狀態: 檢查中...", self)
        self.chk_login = StrongBodyLabel("⏳ 3. lua.tools 登入狀態: 檢查中...", self)
        self.chk_lua = StrongBodyLabel("⏳ 4. Lua 補丁狀態: 檢查中...", self)
        self.chk_game = StrongBodyLabel("⏳ 5. 遊戲安裝狀態: 檢查中...", self)
        self.chk_of = StrongBodyLabel("⏳ 6. Online-Fix 狀態: 檢查中...", self)
        
        for chk in [self.chk_ost, self.chk_def, self.chk_login, self.chk_lua, self.chk_game, self.chk_of]:
            status_layout.addWidget(chk)
            
        status_layout.addSpacing(20)
        self.action_btn = PrimaryPushButton("一鍵自動處理所有缺漏", self)
        self.action_btn.setEnabled(False)
        self.action_btn.clicked.connect(self.do_action)
        status_layout.addWidget(self.action_btn)
        
        self.status_card.hide()
        layout.addWidget(self.status_card)
        layout.addStretch(1)
        self.stack.addWidget(self.main_page)

    def check_ost_status(self):
        if not self.main_app.steam_path:
            self.stack.setCurrentWidget(self.blocker_page)
            return
            
        dlls = ["OpenSteamTool.dll", "dwmapi.dll", "xinput1_4.dll"]
        is_installed = all((self.main_app.steam_path / dll).exists() for dll in dlls)
        
        if is_installed:
            self.stack.setCurrentWidget(self.main_page)
            self.chk_ost.setText("✅ 1. OpenSteamTools 安裝狀態: 已安裝")
            self.chk_ost.setStyleSheet(f"color: {get_state_color('success')};")
        else:
            self.stack.setCurrentWidget(self.blocker_page)

    def perform_search(self):
        query = self.search_input.text().strip()
        if not query: return
        
        self.search_input.setEnabled(False)
        self.status_card.show()
        self.game_title_lbl.setText("搜尋中...")
        
        # Try direct AppID extraction
        import re
        match = re.search(r'(?:app/|appid=)(\d+)', query.lower())
        appid = None
        if match:
            appid = match.group(1)
        elif query.isdigit():
            appid = query
            
        if appid:
            self.search_thread = SteamSearchThread(appid=appid)
        else:
            # Need to search Steam API by text
            self.search_thread = SteamSearchThread(query=query)
            
        self.search_thread.result_ready.connect(self._on_search_result)
        self.search_thread.start()

    def _on_search_result(self, result):
        if not result:
            self.search_input.setEnabled(True)
            self.game_title_lbl.setText("❌ 搜尋失敗，找不到相關遊戲")
            InfoBar.error("錯誤", "無法找到該名稱對應的遊戲，請嘗試使用 AppID", parent=self)
            return
        self._process_appid(int(result['id']), result.get('name', ''))

    def _process_appid(self, appid, name=""):
        self.current_appid = appid
        self.current_app_name = name
        self.search_input.setEnabled(True)
        self.game_title_lbl.setText(f"🎮 目標遊戲: {name} (ID: {appid})" if name else f"🎮 目標遊戲 AppID: {appid}")
        
        self.refresh_all_status()
        

    def refresh_all_status(self):
        if not self.current_appid: return
        appid = self.current_appid
        
        if self.is_deploying:
            return
            
        # 1. OST
        self.check_ost_status()
        
        # 2. Defender
        is_disabled = False
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows Defender\Real-Time Protection", 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, "DisableRealtimeMonitoring")
            is_disabled = (value == 1)
            winreg.CloseKey(key)
        except:
            is_disabled = False
            
        if is_disabled:
            self.chk_def.setText("✅ 2. Defender 狀態: 已關閉 (安全)")
            self.chk_def.setStyleSheet(f"color: {get_state_color('success')};")
        else:
            self.chk_def.setText("⚠️ 2. Defender 狀態: 開啟中 (會阻擋補丁，必須關閉)")
            self.chk_def.setStyleSheet(f"color: {get_state_color('warning')};")
            
        # 3. Lua.tools Login
        from managers import lua_tools_manager
        client = lua_tools_manager.get_shared_client(self.main_app)
        is_logged_in = False
        
        if client.has_checked:
            if client.is_logged_in:
                self.chk_login.setText("✅ 3. lua.tools 登入狀態: 已登入")
                self.chk_login.setStyleSheet(f"color: {get_state_color('success')};")
                is_logged_in = True
            else:
                self.chk_login.setText("❌ 3. lua.tools 登入狀態: 未登入 (請點擊按鈕登入)")
                self.chk_login.setStyleSheet(f"color: {get_state_color('error')};")
        else:
            self.chk_login.setText("⏳ 3. lua.tools 登入狀態: 檢查中...")
            self.chk_login.setStyleSheet("color: #FFFFFF;")
            
        # 4. Lua Status
        lua_path = self.main_app.steam_path / "config" / "lua" / f"{appid}.lua"
        if lua_path.exists():
            self.chk_lua.setText("✅ 4. Lua 補丁狀態: 已部署")
            self.chk_lua.setStyleSheet(f"color: {get_state_color('success')};")
            lua_ok = True
        else:
            self.chk_lua.setText("❌ 4. Lua 補丁狀態: 未部署")
            self.chk_lua.setStyleSheet(f"color: {get_state_color('error')};")
            lua_ok = False
            
        # 4. Game Status
        game_installed = False
        try:
            if hasattr(self.main_app, 'lua_downloader_widget'):
                game_dir_info = self.main_app.lua_downloader_widget._find_steam_game_dir(appid)
                if game_dir_info and game_dir_info[1]:
                    flags = int(game_dir_info[1])
                    if (flags & 4) == 4:
                        game_installed = True
        except:
            pass

        if game_installed:
            self.chk_game.setText("✅ 5. 遊戲安裝狀態: 已安裝")
            self.chk_game.setStyleSheet(f"color: {get_state_color('success')};")
        else:
            self.chk_game.setText("❌ 5. 遊戲安裝狀態: 未安裝 (將喚起 Steam)")
            self.chk_game.setStyleSheet(f"color: {get_state_color('error')};")
            
        # 6. Online-Fix
        from managers import onlinefix_manager
        sources = onlinefix_manager.get_patch_sources(target_app_id=appid, target_app_name=getattr(self, 'current_app_name', ''))
        if str(appid) not in sources and int(appid) not in sources:
            self.chk_of.setText("⚠️ 6. Online-Fix 狀態: 雲端無檔 (無聯機補丁可安裝)")
            self.chk_of.setStyleSheet(f"color: {get_state_color('warning')};")
            of_ok = True
        else:
            fix_status = onlinefix_manager.get_fix_status(appid)
            of_ok = False
            if "已安裝" in fix_status:
                self.chk_of.setText(f"✅ 6. Online-Fix 狀態: {fix_status}")
                self.chk_of.setStyleSheet(f"color: {get_state_color('success')};")
                of_ok = True
            else:
                self.chk_of.setText(f"❌ 6. Online-Fix 狀態: {fix_status}")
                self.chk_of.setStyleSheet(f"color: {get_state_color('error')};")
            
        # Update Action Button State
        self.action_btn.setEnabled(True)
        if not is_disabled:
            self.action_state = "defender"
            self.action_btn.setText("開啟 Defender 設定 (請手動關閉)")
        elif "檢查中" in self.chk_login.text():
            self.action_state = "checking_login"
            self.action_btn.setText("等待 lua.tools 連線...")
            self.action_btn.setEnabled(False)
        elif not is_logged_in:
            self.action_state = "login"
            self.action_btn.setText("登入 lua.tools")
        elif not lua_ok or not game_installed or not of_ok:
            self.action_state = "deploy"
            self.action_btn.setText("一鍵安裝所有缺漏")
        else:
            self.action_state = "done"
            self.action_btn.setText("全部完美安裝就緒！")
            self.action_btn.setEnabled(False)

    def do_action(self):
        if self.action_state == "defender":
            import os
            os.startfile("windowsdefender://threatsettings")
        elif self.action_state == "login":
            if hasattr(self.main_app, 'lua_downloader_widget'):
                self.main_app.lua_downloader_widget.open_login()
        elif self.action_state == "deploy":
            self.start_deploy_sequence()

    def start_deploy_sequence(self):
        self.is_deploying = True
        self.action_btn.setEnabled(False)
        self.action_btn.setText("🚀 正在執行一鍵部署 (1/6)...")
        
        # We simulate the steps using a QTimer state machine
        self.deploy_step = 1
        self.deploy_timer = QTimer(self)
        self.deploy_timer.timeout.connect(self._deploy_tick)
        self.deploy_timer.start(500)
        
    def _deploy_tick(self):
        appid = self.current_appid
        
        if self.deploy_step == 1:
            self.chk_lua.setText("⏳ 4. Lua 補丁狀態: 部署中...")
            self.chk_lua.setStyleSheet(f"color: {get_state_color('warning')};")
            # Check Lua
            lua_path = self.main_app.steam_path / "config" / "lua" / f"{appid}.lua"
            if lua_path.exists():
                self.chk_lua.setText("✅ 4. Lua 補丁狀態: 已部署")
                self.chk_lua.setStyleSheet(f"color: {get_state_color('success')};")
                self.deploy_step = 2
                return
            
            self.action_btn.setText("🚀 正在下載並安裝 Lua 補丁 (1/6)...")
            self.deploy_timer.stop() # Wait for async
            
            # Use lua client
            from managers import lua_tools_manager
            client = lua_tools_manager.get_shared_client(self.main_app)
            if True:
                def on_search(res):
                    import json
                    if not res:
                        res = {}
                    if isinstance(res, str):
                        try:
                            res = json.loads(res)
                        except:
                            res = {}
                    if isinstance(res, dict) and "error" in res:
                        InfoBar.error("Lua 搜尋失敗", res["error"], parent=self)
                        self._abort_deploy()
                        return
                        
                    available_source = None
                    if isinstance(res, list):
                        for item in res:
                            av_val = item.get("available")
                            available = (str(av_val).lower() == "true" or bool(av_val)) if av_val else False
                            if available:
                                available_source = str(item.get("name", item.get("source", ""))).strip()
                                break
                    elif isinstance(res, dict):
                        for k, v in res.items():
                            if isinstance(v, str) and (v.lower() == "available" or v.lower() == "true"):
                                available_source = k
                                break
                                
                    if not available_source:
                        InfoBar.warning("略過", "該遊戲無可用的 Lua 補丁來源", parent=self)
                        self.chk_lua.setText("✅ 4. Lua 補丁狀態: 無需部署 (無資源)")
                        self.chk_lua.setStyleSheet(f"color: {get_state_color('success')};")
                        self._finish_lua()
                        return
                        
                    def on_dl(dl_res):
                        import json
                        if not dl_res:
                            dl_res = {}
                        if isinstance(dl_res, str):
                            try:
                                dl_res = json.loads(dl_res)
                            except:
                                dl_res = {}
                        if isinstance(dl_res, dict) and dl_res.get("error"):
                            InfoBar.error("Lua 下載失敗", str(dl_res.get("error")), parent=self)
                            self._abort_deploy()
                        elif isinstance(dl_res, dict) and not dl_res.get("data"):
                            InfoBar.error("Lua 下載失敗", "返回資料為空", parent=self)
                            self._abort_deploy()
                        else:
                            try:
                                # Apply
                                lua_dir = self.main_app.steam_path / "config" / "lua"
                                lua_dir.mkdir(parents=True, exist_ok=True)
                                with open(lua_dir / f"{appid}.lua", "w", encoding="utf-8") as f:
                                    f.write(dl_res.get("data", ""))
                                self.chk_lua.setText("✅ 4. Lua 補丁狀態: 已部署")
                                self.chk_lua.setStyleSheet(f"color: {get_state_color('success')};")
                                self._finish_lua()
                            except Exception as e:
                                InfoBar.error("Lua 寫入失敗", str(e), parent=self)
                                self._abort_deploy()
                    
                    client.download_manifest(appid, available_source, f"Game_{appid}", on_dl)
                client.search_manifest(appid, on_search)
            else:
                self._finish_lua()
                
        elif self.deploy_step == 2:
            self.chk_game.setText("⏳ 5. 遊戲安裝狀態: 檢查中...")
            self.chk_game.setStyleSheet(f"color: {get_state_color('warning')};")
            # Check Game Install
            game_installed = False
            try:
                if hasattr(self.main_app, 'lua_downloader_widget'):
                    game_dir_info = self.main_app.lua_downloader_widget._find_steam_game_dir(appid)
                    if game_dir_info and game_dir_info[1]:
                        flags = int(game_dir_info[1])
                        if (flags & 4) == 4:
                            game_installed = True
            except:
                pass
                
            if game_installed:
                self.chk_game.setText("✅ 5. 遊戲安裝狀態: 已安裝")
                self.chk_game.setStyleSheet(f"color: {get_state_color('success')};")
                self.deploy_step = 4 # Skip wait
            else:
                self.chk_game.setText("⏳ 5. 遊戲安裝狀態: 安裝中 (等待 Steam)...")
                self.chk_game.setStyleSheet(f"color: {get_state_color('warning')};")
                self.action_btn.setText("🚀 正在喚起 Steam 安裝遊戲 (2/6)...")
                import os
                try:
                    os.startfile(f"steam://install/{appid}")
                except:
                    pass
                self.deploy_step = 3
                
        elif self.deploy_step == 3:
            # Wait for Game Install
            self.chk_game.setText("⏳ 5. 遊戲安裝狀態: 安裝中 (等待 Steam)...")
            self.chk_game.setStyleSheet(f"color: {get_state_color('warning')};")
            self.action_btn.setText("🚀 等待 Steam 遊戲安裝完畢 (3/6)...")
            game_installed = False
            try:
                if hasattr(self.main_app, 'lua_downloader_widget'):
                    game_dir_info = self.main_app.lua_downloader_widget._find_steam_game_dir(appid)
                    if game_dir_info and game_dir_info[1]:
                        flags = int(game_dir_info[1])
                        if (flags & 4) == 4:
                            game_installed = True
            except:
                pass
                
            if game_installed:
                self.chk_game.setText("✅ 5. 遊戲安裝狀態: 已安裝")
                self.chk_game.setStyleSheet(f"color: {get_state_color('success')};")
                self.deploy_step = 4
                
        elif self.deploy_step == 4:
            # Install OF
            self.chk_of.setText("⏳ 6. Online-Fix 狀態: 部署中...")
            self.chk_of.setStyleSheet(f"color: {get_state_color('warning')};")
            self.action_btn.setText("🚀 正在下載並打入 Online-Fix (4/6)...")
            self.deploy_timer.stop()
            
            from managers import onlinefix_manager
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            
            sources = onlinefix_manager.get_patch_sources(target_app_id=appid, target_app_name=getattr(self, 'current_app_name', ''))
            source = sources.get(str(appid))
            
            if source:
                rar_path = source.get('local_rar')
                if not rar_path and source.get('cloud_rar'):
                    rar_path = str(onlinefix_manager.LOCAL_PATCH_DIR / source['cloud_rar']['path'])
                    import os
                    if not os.path.exists(rar_path):
                        self.chk_of.setText("⏳ 6. Online-Fix 狀態: 下載補丁中...")
                        QApplication.processEvents()
                        dl_path = onlinefix_manager.download_cloud_patch(source['cloud_rar'])
                        rar_path = dl_path if dl_path else None
                        
                if rar_path:
                    try:
                        game_dir_info = self.main_app.lua_downloader_widget._find_steam_game_dir(appid)
                        if game_dir_info and game_dir_info[0]:
                            success, msg = onlinefix_manager.install_fix(appid, rar_path, game_dir_info[0])
                            if success:
                                self.chk_of.setText("✅ 6. Online-Fix 狀態: 已安裝")
                                self.chk_of.setStyleSheet(f"color: {get_state_color('success')};")
                            else:
                                self.chk_of.setText("❌ 6. Online-Fix 狀態: 安裝失敗")
                                self.chk_of.setStyleSheet(f"color: {get_state_color('error')};")
                                InfoBar.error("Online-Fix 失敗", msg, parent=self)
                                self._abort_deploy()
                                return
                    except Exception as e:
                        self.chk_of.setText("❌ 6. Online-Fix 狀態: 安裝錯誤")
                        self.chk_of.setStyleSheet(f"color: {get_state_color('error')};")
                        InfoBar.error("錯誤", str(e), parent=self)
                        self._abort_deploy()
                        return
            else:
                self.chk_of.setText("✅ 6. Online-Fix 狀態: 無需安裝 (無資源)")
                self.chk_of.setStyleSheet(f"color: {get_state_color('success')};")
            
            self._finish_deploy()
    def _finish_lua(self):
        self.deploy_step = 2
        self.deploy_timer.start(1000)
        
    def _finish_deploy(self):
        self.is_deploying = False
        self.action_btn.setText("✅ 部署完成！")
        self.refresh_all_status()

    def _abort_deploy(self):
        self.is_deploying = False
        self.deploy_timer.stop()
        self.action_btn.setEnabled(True)
        self.refresh_all_status()
