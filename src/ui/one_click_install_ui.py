from ui.theme_utils import get_state_color
import os
import re
import winreg
import urllib.request
import urllib.parse
import json
from pathlib import Path
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QDialog, QApplication
from PySide6.QtCore import Qt, Signal, QThread, QTimer, QSize
from qfluentwidgets import (
    CardWidget, StrongBodyLabel, BodyLabel, PrimaryPushButton, PushButton, 
    LineEdit, InfoBar, SearchLineEdit, TitleLabel, ImageLabel, SubtitleLabel,
    TransparentToolButton, FluentIcon, ScrollArea
)
from managers.assiw_manager import AssiwCheckThread, AssiwDownloadThread






class InstallTroubleshootDialog(QDialog):
    """當 Steam 安裝異常、無授權或等待超時時的互動處置面板"""
    def __init__(self, appid, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Steam 安裝狀態處置")
        self.setFixedSize(520, 240)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.choice = None  # "retry_restart", "skip", "abort"
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        
        title_lbl = SubtitleLabel("⚠️ 未檢測到 Steam 開始安裝此遊戲", self)
        layout.addWidget(title_lbl)
        
        msg = (
            f"Steam 尚未開始下載或安裝該遊戲 (AppID: {appid})。\n\n"
            "• 若 Steam 彈窗顯示「無授權 / 無許可」，通常是因 Steam 原先在運行中，尚未加載剛寫入的 Lua 授權。\n"
            "• 若此遊戲 Lua 清單失效或您想稍後手動處理，可直接略過此步驟。\n\n"
            "請選擇您的處置方式："
        )
        body_lbl = BodyLabel(msg, self)
        body_lbl.setWordWrap(True)
        layout.addWidget(body_lbl)
        layout.addStretch(1)
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.btn_restart = PrimaryPushButton("🔄 重啟 Steam 並重試", self)
        self.btn_restart.clicked.connect(self._choose_restart)
        btn_layout.addWidget(self.btn_restart)
        
        self.btn_skip = PushButton("⏭️ 略過遊戲安裝 (繼續下一步)", self)
        self.btn_skip.clicked.connect(self._choose_skip)
        btn_layout.addWidget(self.btn_skip)
        
        self.btn_abort = PushButton("⏹️ 中止部署", self)
        self.btn_abort.clicked.connect(self._choose_abort)
        btn_layout.addWidget(self.btn_abort)
        
        layout.addLayout(btn_layout)

    def _choose_restart(self):
        self.choice = "retry_restart"
        self.accept()

    def _choose_skip(self):
        self.choice = "skip"
        self.accept()

    def _choose_abort(self):
        self.choice = "abort"
        self.reject()



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


class CloudPatchSyncThread(QThread):
    sync_finished = Signal(dict)
    
    def __init__(self, appid, name="", parent=None):
        super().__init__(parent)
        self.appid = appid
        self.name = name
        
    def run(self):
        try:
            from managers import onlinefix_manager
            onlinefix_manager.fetch_cloud_cache(force=True)
            sources = onlinefix_manager.get_patch_sources(target_app_id=self.appid, target_app_name=self.name)
            self.sync_finished.emit(sources)
        except Exception as e:
            print(f"CloudPatchSyncThread error: {e}")
            self.sync_finished.emit({})


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
        
        self.is_syncing_cloud = False
        self.sync_dot_count = 1
        self.sync_anim_timer = QTimer(self)
        self.sync_anim_timer.setInterval(350)
        self.sync_anim_timer.timeout.connect(self._update_sync_anim_dots)
        
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.refresh_all_status)
        self.status_timer.start(1500)
        
        self.is_deploying = False
        self.deploy_step = 0
        self.lua_resource_status = None  # None, "checking", "deployed", "available", "none"
        self.lua_available_source = None
        
        from managers import lua_tools_manager, ryuu_manager
        client = lua_tools_manager.get_shared_client(self.main_app)
        if client:
            client.ready.connect(self._on_lua_client_ready)
            client.not_logged_in.connect(self._on_lua_client_not_logged_in)
        ryuu_client = ryuu_manager.get_shared_ryuu_client(self.main_app)
        if ryuu_client:
            ryuu_client.ready.connect(self.refresh_all_status)
            ryuu_client.not_logged_in.connect(self.refresh_all_status)

    def _on_lua_client_ready(self):
        if self.current_appid and getattr(self, 'lua_resource_status', None) in ("checking", "none"):
            self._check_lua_resource(self.current_appid)
            
    def _on_lua_client_not_logged_in(self):
        if self.current_appid and getattr(self, 'lua_resource_status', None) == "checking":
            from managers import onlinefix_manager
            sources = onlinefix_manager.get_patch_sources(target_app_id=self.current_appid, target_app_name=getattr(self, 'current_app_name', ''))
            src_info = sources.get(str(self.current_appid), {})
            if not (src_info.get('cloud_lua') or src_info.get('local_lua')):
                self.lua_resource_status = "none"
                self.refresh_all_status()

    def _init_blocker_page(self):
        self.blocker_page = QWidget()
        layout = QVBoxLayout(self.blocker_page)
        layout.setAlignment(Qt.AlignCenter)
        
        icon = TitleLabel("⚠️ 必須先安裝 OpenSteamTools", self)
        icon.setAlignment(Qt.AlignCenter)
        desc = BodyLabel("這是一鍵安裝的必要依賴組件。點擊下方按鈕將自動為您完成安裝並重啟 Steam 載入模組。", self)
        desc.setAlignment(Qt.AlignCenter)
        
        self.blocker_btn = PrimaryPushButton("🚀 一鍵安裝 OpenSteamTools 並重啟 Steam", self)
        self.blocker_btn.clicked.connect(self._install_ost_from_blocker)
        self.blocker_btn.setFixedWidth(320)
        
        layout.addWidget(icon)
        layout.addSpacing(10)
        layout.addWidget(desc)
        layout.addSpacing(20)
        layout.addWidget(self.blocker_btn, alignment=Qt.AlignCenter)
        self.stack.addWidget(self.blocker_page)

    def _install_ost_from_blocker(self):
        self.blocker_btn.setEnabled(False)
        self.blocker_btn.setText("⏳ 正在安裝並等待 Steam 重啟...")
        QApplication.processEvents()
        
        from managers import steam_manager
        dlls = ["OpenSteamTool.dll", "dwmapi.dll", "xinput1_4.dll"]
        dlls_installed = all((self.main_app.steam_path / dll).exists() for dll in dlls) if self.main_app.steam_path else False
        
        if not dlls_installed:
            success, msg = steam_manager.install_opensteamtools(self.main_app.steam_path)
        else:
            success, msg, pid = steam_manager.restart_steam(self.main_app.steam_path)
            
        self.blocker_btn.setEnabled(True)
        self.blocker_btn.setText("🚀 一鍵安裝 OpenSteamTools 並重啟 Steam")
        
        if success:
            InfoBar.success("成功", "OpenSteamTools 已就緒，且 Steam 已成功重啟！", position=InfoBarPosition.TOP, parent=self)
            self.check_ost_status()
            if hasattr(self.main_app, 'update_ost_status'):
                self.main_app.update_ost_status()
        else:
            InfoBar.error("錯誤", msg, position=InfoBarPosition.TOP, parent=self)

    def _init_main_page(self):
        self.main_page = QWidget()
        layout = QVBoxLayout(self.main_page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # 1. Search Bar
        search_card = CardWidget(self)
        search_layout = QVBoxLayout(search_card)
        search_layout.setContentsMargins(16, 12, 16, 12)
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
        status_layout.setContentsMargins(18, 16, 18, 16)
        status_layout.setSpacing(8)
        
        self.game_title_lbl = TitleLabel("尚未選擇遊戲", self)
        status_layout.addWidget(self.game_title_lbl)
        status_layout.addSpacing(4)
        
        # Checklist items (統一整合為清晰的 1~7 序號)
        self.chk_ost = StrongBodyLabel("⏳ 1. OpenSteamTools 安裝狀態: 檢查中...", self)
        self.chk_def = StrongBodyLabel("⏳ 2. Defender 狀態: 檢查中...", self)
        self.chk_discord_cred = StrongBodyLabel("⏳ 3. Discord 憑證狀態: 檢查中...", self)
        self.chk_lua = StrongBodyLabel("⏳ 4. Lua / 清單補丁狀態: 檢查中...", self)
        self.chk_game = StrongBodyLabel("⏳ 5. 遊戲安裝狀態: 檢查中...", self)
        self.chk_lock = StrongBodyLabel("⏳ 6. 版本鎖定防護 (防 401): 檢查中...", self)
        
        for chk in [self.chk_ost, self.chk_def, self.chk_discord_cred, self.chk_lua, self.chk_game, self.chk_lock]:
            status_layout.addWidget(chk)
            
        of_h = QHBoxLayout()
        of_h.setContentsMargins(0, 0, 0, 0)
        of_h.setSpacing(6)
        self.chk_of = StrongBodyLabel("⏳ 7. Online-Fix 狀態: 檢查中...", self)
        self.btn_refresh_of = TransparentToolButton(FluentIcon.SYNC, self)
        self.btn_refresh_of.setToolTip("重新整理雲端補丁清單")
        self.btn_refresh_of.setIconSize(QSize(13, 13))
        self.btn_refresh_of.setFixedSize(18, 18)
        self.btn_refresh_of.setCursor(Qt.PointingHandCursor)
        self.btn_refresh_of.setStyleSheet("TransparentToolButton { margin: 0px; padding: 0px; border-radius: 3px; }")
        self.btn_refresh_of.clicked.connect(self._trigger_cloud_refresh)
        of_h.addWidget(self.chk_of, 0, Qt.AlignVCenter)
        of_h.addWidget(self.btn_refresh_of, 0, Qt.AlignVCenter)
        of_h.addStretch(1)
        status_layout.addLayout(of_h)
            
        status_layout.addSpacing(6)
        web_btn_h = QHBoxLayout()
        self._of_url = None
        self._zg_url = None
        self.btn_web_of = PushButton("🌐 Online-Fix.me: 尚未檢查", self)
        self.btn_web_of.setFixedHeight(30)
        self.btn_web_of.setEnabled(False)
        self.btn_web_of.clicked.connect(self._open_of_url)
        self.btn_web_zg = PushButton("🌐 ZeiGames.com: 尚未檢查", self)
        self.btn_web_zg.setFixedHeight(30)
        self.btn_web_zg.setEnabled(False)
        self.btn_web_zg.clicked.connect(self._open_zg_url)
        web_btn_h.addWidget(self.btn_web_of)
        web_btn_h.addWidget(self.btn_web_zg)
        status_layout.addLayout(web_btn_h)
            
        status_layout.addSpacing(10)
        action_bar_h = QHBoxLayout()
        action_bar_h.setContentsMargins(0, 0, 0, 0)
        action_bar_h.setSpacing(8)
        
        self.action_btn = PrimaryPushButton("一鍵自動處理所有缺漏", self)
        self.action_btn.setFixedHeight(40)
        self.action_btn.setEnabled(False)
        self.action_btn.clicked.connect(self.do_action)
        action_bar_h.addWidget(self.action_btn, 1)
        
        self.btn_cancel_wait = PushButton("⏹️ 略過/處置", self)
        self.btn_cancel_wait.setToolTip("當 Steam 無法安裝、彈出無授權或需要取消時點擊")
        self.btn_cancel_wait.setFixedHeight(40)
        self.btn_cancel_wait.hide()
        self.btn_cancel_wait.clicked.connect(self._manual_troubleshoot_install)
        action_bar_h.addWidget(self.btn_cancel_wait)
        
        status_layout.addLayout(action_bar_h)
        
        self.status_card.hide()
        layout.addWidget(self.status_card)
        layout.addStretch(1)

        # 外層使用 ScrollArea 包裹，徹底避免任何解析度或視窗高度下裁切按鈕
        self.scroll_area = ScrollArea(self)
        self.scroll_area.setStyleSheet("QScrollArea{background: transparent; border: none;}")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.main_page)
        
        self.stack.addWidget(self.scroll_area)

    def check_ost_status(self):
        if not self.main_app.steam_path:
            self.stack.setCurrentWidget(self.blocker_page)
            return False
            
        dlls = ["OpenSteamTool.dll", "dwmapi.dll", "xinput1_4.dll"]
        is_installed = all((self.main_app.steam_path / dll).exists() for dll in dlls)
        
        if not is_installed:
            self.stack.setCurrentWidget(self.blocker_page)
            self.chk_ost.setText("❌ 1. OpenSteamTools 安裝狀態: 未安裝")
            self.chk_ost.setStyleSheet(f"color: {get_state_color('error')};")
            return False
            
        # DLL 已就緒，放行進入主搜尋介面
        self.stack.setCurrentWidget(self.scroll_area)
        
        from managers import steam_manager
        steam_manager.ensure_manifest_lua(self.main_app.steam_path)
        is_steam_running = steam_manager.is_steam_running()
        if is_steam_running:
            self.chk_ost.setText("✅ 1. OpenSteamTools 安裝狀態: 已安裝 (Steam 運行中)")
        else:
            self.chk_ost.setText("✅ 1. OpenSteamTools 安裝狀態: 已安裝")
        self.chk_ost.setStyleSheet(f"color: {get_state_color('success')};")
        return True

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
        
        # Trigger background web check
        if name:
            self.btn_web_of.setText("🌐 Online-Fix.me: ⏳ 搜尋中...")
            self.btn_web_of.setEnabled(False)
            self.btn_web_zg.setText("🌐 ZeiGames.com: ⏳ 搜尋中...")
            self.btn_web_zg.setEnabled(False)
            
            if hasattr(self, 'web_patch_thread') and self.web_patch_thread and self.web_patch_thread.isRunning():
                self.web_patch_thread.terminate()
            from api.web_patch_checker import WebPatchCheckThread
            self.web_patch_thread = WebPatchCheckThread(name, self)
            self.web_patch_thread.results_ready.connect(self._on_web_patch_results)
            self.web_patch_thread.start()
        else:
            self.btn_web_of.setText("🌐 Online-Fix.me: ❌ 無遊戲名稱")
            self.btn_web_of.setEnabled(False)
            self.btn_web_zg.setText("🌐 ZeiGames.com: ❌ 無遊戲名稱")
            self.btn_web_zg.setEnabled(False)
            
        # Trigger background cloud patch sync (ensures latest Google Drive files are detected)
        if hasattr(self, 'cloud_sync_thread') and self.cloud_sync_thread and self.cloud_sync_thread.isRunning():
            self.cloud_sync_thread.terminate()
        self.cloud_sync_thread = CloudPatchSyncThread(appid, name, self)
        self.cloud_sync_thread.sync_finished.connect(self._on_cloud_sync_finished)
        self.cloud_sync_thread.start()
        
        # Trigger background lua resource check before one-click deploy
        self._check_lua_resource(appid)
        
        self.refresh_all_status()

    def _check_lua_resource(self, appid):
        # 1. First check if already deployed locally in Steam and manifests are complete
        if self.main_app.steam_path:
            lua_path = self.main_app.steam_path / "config" / "lua" / f"{appid}.lua"
            if lua_path.exists():
                from managers import steam_manager
                st = steam_manager.get_lua_manifest_status(appid, self.main_app.steam_path)
                if st.get("is_complete"):
                    self.lua_resource_status = "deployed"
                    self.refresh_all_status()
                    return

        self.lua_resource_status = "checking"
        self.lua_available_source = None
        self.refresh_all_status()

        def _fallback_to_assiw():
            if self.current_appid != appid:
                return
            if hasattr(self, 'assiw_check_thread') and self.assiw_check_thread and self.assiw_check_thread.isRunning():
                self.assiw_check_thread.terminate()
            self.assiw_check_thread = AssiwCheckThread(appid, self)
            def _on_assiw_check(res_appid, supported):
                if self.current_appid != res_appid:
                    return
                if supported:
                    self.lua_resource_status = "available"
                    self.lua_available_source = "Assiw"
                else:
                    self.lua_resource_status = "none"
                self.refresh_all_status()
            self.assiw_check_thread.result_ready.connect(_on_assiw_check)
            self.assiw_check_thread.start()

        def _fallback_to_lt():
            from managers import lua_tools_manager
            client = lua_tools_manager.get_shared_client(self.main_app)
            if client and client.has_checked and not client.is_logged_in:
                _fallback_to_assiw()
                return

            if client:
                def _on_lua_search(res):
                    if self.current_appid != appid:
                        return
                    available_source = None
                    priority = ["Ryuu"]
                    if isinstance(res, list):
                        for pref in priority:
                            for item in res:
                                s_name = str(item.get("name", item.get("source", ""))).strip()
                                av_val = item.get("available")
                                if (str(av_val).lower() == "true" or bool(av_val)) if av_val else False:
                                    if s_name.lower() == pref.lower():
                                        available_source = pref
                                        break
                            if available_source: break
                    elif isinstance(res, dict):
                        for pref in priority:
                            for k, v in res.items():
                                if str(k).lower() == pref.lower():
                                    if isinstance(v, str) and (v.lower() == "available" or v.lower() == "true"):
                                        available_source = pref
                                        break
                            if available_source: break
                    if available_source:
                        self.lua_resource_status = "available"
                        self.lua_available_source = f"Lua.tools ({available_source})"
                        self.refresh_all_status()
                    else:
                        _fallback_to_assiw()

                client.search_manifest(appid, _on_lua_search)
            else:
                _fallback_to_assiw()

        def _check_cloud_patch():
            from managers import onlinefix_manager
            sources = onlinefix_manager.get_patch_sources(target_app_id=appid, target_app_name=getattr(self, 'current_app_name', ''))
            src_info = sources.get(str(appid), {})
            if src_info.get('cloud_lua') or src_info.get('local_lua'):
                self.lua_resource_status = "available"
                self.lua_available_source = src_info.get('drive_name', '網盤')
                self.refresh_all_status()
                return True
            return False


        # 優先順位 1: Ryuu Generator (專屬端點 0 消耗快速檢查)
        from managers import ryuu_manager, account_manager
        acc_mgr = account_manager.get_account_manager()
        ryuu_client = ryuu_manager.get_shared_ryuu_client(self.main_app)
        ryuu_has_quota = (ryuu_client.is_logged_in or ryuu_manager.has_saved_ryuu_credentials()) and acc_mgr.has_available_quota("ryuu")

        if hasattr(self, 'ryuu_check_thread') and self.ryuu_check_thread and self.ryuu_check_thread.isRunning():
            self.ryuu_check_thread.terminate()

        self.ryuu_check_thread = ryuu_manager.RyuuCheckThread(appid, self)
        def _on_ryuu_check_done(res_appid, found, info):
            if self.current_appid != res_appid:
                return
            if found and ryuu_has_quota:
                self.lua_resource_status = "available"
                self.lua_available_source = "Ryuu Generator"
                self.refresh_all_status()
            else:
                # Ryuu 查無此遊戲或無配額，檢查網盤或 Fallback 至 Lua.tools
                if not _check_cloud_patch():
                    _fallback_to_lt()

        self.ryuu_check_thread.result_ready.connect(_on_ryuu_check_done)
        self.ryuu_check_thread.start()


    def _on_cloud_sync_finished(self, sources):
        if hasattr(self, 'btn_refresh_of'):
            self.btn_refresh_of.setEnabled(True)
        if self.current_appid:
            src = sources.get(str(self.current_appid), {})
            if src.get('cloud_lua') or src.get('local_lua'):
                self.lua_resource_status = "available"
        self.refresh_all_status()

    def _update_sync_anim_dots(self):
        if not getattr(self, 'is_syncing_cloud', False) or not self.current_appid:
            return
        dots = "." * self.sync_dot_count
        self.sync_dot_count = (self.sync_dot_count % 3) + 1
        
        from managers import onlinefix_manager
        fix_status = onlinefix_manager.get_fix_status(self.current_appid)
        if "已安裝" in fix_status:
            prefix = "✅ 6. Online-Fix 狀態: 已安裝"
            color = get_state_color('success')
        else:
            sources = onlinefix_manager.get_patch_sources(target_app_id=self.current_appid, target_app_name=getattr(self, 'current_app_name', ''))
            has_cloud_rar = bool(sources.get(str(self.current_appid), {}).get('cloud_rar'))
            if not has_cloud_rar:
                prefix = "⚠️ 6. Online-Fix 狀態: 雲端無檔"
                color = get_state_color('warning')
            else:
                prefix = "❌ 6. Online-Fix 狀態: 未安裝"
                color = get_state_color('error')
                
        self.chk_of.setText(f"{prefix} (來源: 重整中{dots})")
        self.chk_of.setStyleSheet(f"color: {color};")

    def _trigger_cloud_refresh(self):
        if not self.current_appid:
            return
        self.btn_refresh_of.setEnabled(False)
        self.is_syncing_cloud = True
        self.sync_dot_count = 1
        self._update_sync_anim_dots()
        self.sync_anim_timer.start()
        
        if hasattr(self, 'cloud_sync_thread') and self.cloud_sync_thread and self.cloud_sync_thread.isRunning():
            self.cloud_sync_thread.terminate()
        self.cloud_sync_thread = CloudPatchSyncThread(self.current_appid, getattr(self, 'current_app_name', ''), self)
        self.cloud_sync_thread.sync_finished.connect(self._on_cloud_refresh_manual_done)
        self.cloud_sync_thread.start()

    def _on_cloud_refresh_manual_done(self, sources):
        self.is_syncing_cloud = False
        self.sync_anim_timer.stop()
        self.btn_refresh_of.setEnabled(True)
        self.refresh_all_status()
        src_info = sources.get(str(self.current_appid), {})
        if src_info.get('cloud_rar'):
            InfoBar.success("雲端已更新", f"成功抓取到雲端補丁 (來源: {src_info.get('drive_name', '網盤')})！", parent=self)
        else:
            InfoBar.warning("雲端無檔", "已同步最新清單，但目前雲端網盤內尚未找到此遊戲的補丁檔案。", parent=self)

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
            self.btn_web_of.setText("🌐 Online-Fix.me: ✅ 有補丁 (點擊前往)")
            self.btn_web_of.setEnabled(True)
        else:
            self.btn_web_of.setText("🌐 Online-Fix.me: ❌ 無對應網頁")
            self.btn_web_of.setEnabled(False)
            
        if self._zg_url:
            self.btn_web_zg.setText("🌐 ZeiGames.com: ✅ 有補丁 (點擊前往)")
            self.btn_web_zg.setEnabled(True)
        else:
            self.btn_web_zg.setText("🌐 ZeiGames.com: ❌ 無對應網頁")
            self.btn_web_zg.setEnabled(False)
        

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
            self.chk_def.setText(f"⚠️ 2. Defender 狀態: 開啟中 (請關閉 <span style='color: {get_state_color('error')}; font-weight: bold;'>即時保護</span> 功能)")
            self.chk_def.setStyleSheet(f"color: {get_state_color('warning')};")
            
        # 3. Discord 憑證狀態 (整合 Ryuu 與 Lua.tools 雙平台)
        from managers import ryuu_manager, lua_tools_manager
        ryuu_client = ryuu_manager.get_shared_ryuu_client(self.main_app)
        ryuu_logged_in = (ryuu_client and ryuu_client.is_logged_in) or ryuu_manager.has_saved_ryuu_credentials()
        
        client = lua_tools_manager.get_shared_client(self.main_app)
        is_logged_in = (client and client.is_logged_in) or lua_tools_manager.has_saved_credentials()

        ryuu_checking = (ryuu_client and not ryuu_client.has_checked and not ryuu_logged_in)
        lt_checking = (client and not client.has_checked and not is_logged_in)

        if ryuu_checking or lt_checking:
            self.chk_discord_cred.setText("⏳ 3. Discord 憑證狀態: 檢查中...")
            self.chk_discord_cred.setStyleSheet("color: #FFFFFF;")
        elif ryuu_logged_in and is_logged_in:
            self.chk_discord_cred.setText("✅ 3. Discord 憑證狀態: 已登入")
            self.chk_discord_cred.setStyleSheet(f"color: {get_state_color('success')};")
        elif ryuu_logged_in and not is_logged_in:
            self.chk_discord_cred.setText("⚠️ 3. Discord 憑證狀態: 缺少 lua.tools (Ryuu 已登入)")
            self.chk_discord_cred.setStyleSheet(f"color: {get_state_color('warning')};")
        elif not ryuu_logged_in and is_logged_in:
            self.chk_discord_cred.setText("⚠️ 3. Discord 憑證狀態: 缺少 Ryuu (lua.tools 已登入)")
            self.chk_discord_cred.setStyleSheet(f"color: {get_state_color('warning')};")
        else:
            self.chk_discord_cred.setText("❌ 3. Discord 憑證狀態: 缺少 Ryuu, lua.tools (未登入)")
            self.chk_discord_cred.setStyleSheet(f"color: {get_state_color('error')};")
            
        # 4. Lua / 清單補丁狀態
        lua_path = self.main_app.steam_path / "config" / "lua" / f"{appid}.lua"
        from managers import steam_manager
        st = steam_manager.get_lua_manifest_status(appid, self.main_app.steam_path) if self.main_app.steam_path else {}

        if lua_path.exists() and st.get("is_complete"):
            self.chk_lua.setText("✅ 4. Lua / 清單狀態: 已部署 (完整)")
            self.chk_lua.setStyleSheet(f"color: {get_state_color('success')};")
            lua_ok = True
        elif lua_path.exists() and st.get("is_incomplete"):
            missing_cnt = len(st.get("missing_files", []))
            self.chk_lua.setText(f"❌ 4. Lua / 清單狀態: 殘缺 (缺 {missing_cnt} 個清單檔)")
            self.chk_lua.setStyleSheet(f"color: {get_state_color('error')};")
            lua_ok = False
        else:
            from managers import onlinefix_manager
            sources = onlinefix_manager.get_patch_sources(target_app_id=appid, target_app_name=getattr(self, 'current_app_name', ''))
            src_info = sources.get(str(appid), {})
            has_cloud_lua = bool(src_info.get('cloud_lua') or src_info.get('local_lua'))
            
            lua_status = getattr(self, 'lua_resource_status', None)
            
            if has_cloud_lua:
                drive_name = src_info.get('drive_name', '網盤')
                self.chk_lua.setText(f"❌ 4. Lua / 清單狀態: 未部署 (來源: {drive_name})")
                self.chk_lua.setStyleSheet(f"color: {get_state_color('error')};")
                lua_ok = False
            elif lua_status == "available":
                src_name = getattr(self, 'lua_available_source', '')
                src_tag = f" (來源: {src_name})" if src_name else ""
                self.chk_lua.setText(f"❌ 4. Lua / 清單狀態: 未部署{src_tag}")
                self.chk_lua.setStyleSheet(f"color: {get_state_color('error')};")
                lua_ok = False
            elif lua_status == "none":
                self.chk_lua.setText("⚠️ 4. Lua / 清單狀態: 無資源")
                self.chk_lua.setStyleSheet(f"color: {get_state_color('warning')};")
                lua_ok = True  # 無資源：不支援一鍵補漏，不作為缺失項目阻礙按鈕
            else:
                self.chk_lua.setText("⏳ 4. Lua / 清單狀態: 檢查中...")
                self.chk_lua.setStyleSheet("color: #FFFFFF;")
                lua_ok = True  # 檢查中暫時不觸發一鍵部署
            
        # 5. Game Status
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
            
        # 6. Version Lock Status (防 Valve 401 封鎖)
        from managers import steam_manager
        lock_info = steam_manager.get_game_manifest_lock_info(appid, self.main_app.steam_path)
        lock_ok = lock_info.get("is_locked", False)
        if lock_ok:
            self.chk_lock.setText("✅ 6. 版本鎖定防護: 已鎖定 🔒 (防 401 封鎖)")
            self.chk_lock.setStyleSheet(f"color: {get_state_color('success')};")
        else:
            self.chk_lock.setText("⚠️ 6. 版本鎖定防護: 未鎖定 (安裝時自動套用鎖定防護)")
            self.chk_lock.setStyleSheet(f"color: {get_state_color('warning')};")

        # 7. Online-Fix
        if not getattr(self, 'is_syncing_cloud', False):
            from managers import onlinefix_manager
            fix_status = onlinefix_manager.get_fix_status(appid)
            of_ok = False
            
            if "已安裝" in fix_status:
                rec = onlinefix_manager.get_fix_record(appid)
                source_tag = f" (來源: {rec.get('source_drive')})" if rec and rec.get('source_drive') else ""
                self.chk_of.setText(f"✅ 7. Online-Fix 狀態: {fix_status}{source_tag}")
                self.chk_of.setStyleSheet(f"color: {get_state_color('success')};")
                of_ok = True
            else:
                sources = onlinefix_manager.get_patch_sources(target_app_id=appid, target_app_name=getattr(self, 'current_app_name', ''))
                src_info = sources.get(str(appid), {})
                has_cloud_rar = bool(src_info.get('cloud_rar'))
                
                if not has_cloud_rar:
                    self.chk_of.setText("⚠️ 7. Online-Fix 狀態: 雲端無檔")
                    self.chk_of.setStyleSheet(f"color: {get_state_color('warning')};")
                    of_ok = True
                else:
                    drive_name = src_info.get('drive_name', '網盤 1')
                    self.chk_of.setText(f"❌ 7. Online-Fix 狀態: 未安裝 (來源: {drive_name})")
                    self.chk_of.setStyleSheet(f"color: {get_state_color('error')};")
                    of_ok = False
        else:
            of_ok = False
            
        # Update Action Button State
        self.action_btn.setEnabled(True)
        if not is_disabled:
            self.action_state = "defender"
            self.action_btn.setText("開啟 Defender 設定 (請手動關閉)")
        elif "檢查中" in self.chk_discord_cred.text():
            self.action_state = "checking_login"
            self.action_btn.setText("等待來源平台連線...")
            self.action_btn.setEnabled(False)
        elif not is_logged_in and not ryuu_logged_in and not lua_ok:
            self.action_state = "login"
            self.action_btn.setText("登入 Discord (Ryuu / Lua.tools)")
        elif not lua_ok or not game_installed or not lock_ok or not of_ok:
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
        # 防呆檢查：確保 Steam 正常運行且載入 OpenSteamTools
        from managers import steam_manager
        if not steam_manager.is_steam_running():
            self.action_btn.setEnabled(False)
            self.action_btn.setText("⏳ 正在重啟 Steam 並驗證中...")
            QApplication.processEvents()
            re_ok, re_msg, pid = steam_manager.restart_steam(self.main_app.steam_path)
            if not re_ok:
                InfoBar.error("Steam 啟動失敗", f"無法啟動 Steam: {re_msg}，請確認 Steam 是否正常安裝", parent=self)
                self.refresh_all_status()
                return
            self.check_ost_status()
            
        self.is_deploying = True
        self.action_btn.setEnabled(False)
        self.action_btn.setText("🚀 正在執行一鍵部署 (1/5)...")
        
        # We simulate the steps using a QTimer state machine
        self.deploy_step = 1
        self.deploy_timer = QTimer(self)
        self.deploy_timer.timeout.connect(self._deploy_tick)
        self.deploy_timer.start(500)
        
    def _deploy_tick(self):
        appid = self.current_appid
        
        if self.deploy_step == 1:
            self.chk_lua.setText("⏳ 4. Lua / 清單補丁狀態: 部署中...")
            self.chk_lua.setStyleSheet(f"color: {get_state_color('warning')};")
            # Check Lua
            lua_path = self.main_app.steam_path / "config" / "lua" / f"{appid}.lua"
            if lua_path.exists():
                self.chk_lua.setText("✅ 4. Lua / 清單補丁狀態: 已部署")
                self.chk_lua.setStyleSheet(f"color: {get_state_color('success')};")
                self.deploy_step = 2
                return
            
            # 若無資源，跳過 Lua 部署，保持黃色無資源狀態
            from managers import onlinefix_manager
            sources = onlinefix_manager.get_patch_sources(target_app_id=appid, target_app_name=getattr(self, 'current_app_name', ''))
            src_info = sources.get(str(appid), {})
            has_cloud_lua = bool(src_info.get('cloud_lua') or src_info.get('local_lua'))
            
            if getattr(self, 'lua_resource_status', None) == "none" and not has_cloud_lua:
                self.chk_lua.setText("⚠️ 4. Lua / 清單補丁狀態: 無資源")
                self.chk_lua.setStyleSheet(f"color: {get_state_color('warning')};")
                self.deploy_step = 2
                return
                
            # 若網盤有 Lua 補丁，優先直接安裝
            if has_cloud_lua:
                self.action_btn.setText("🚀 正在從網盤套用 Lua 補丁 (1/5)...")
                lua_dir = self.main_app.steam_path / "config" / "lua"
                ok, msg = onlinefix_manager.install_lua(appid, src_info, lua_dir)
                if ok:
                    self.chk_lua.setText("✅ 4. Lua / 清單補丁狀態: 已部署")
                    self.chk_lua.setStyleSheet(f"color: {get_state_color('success')};")
                    self._finish_lua(new_installed=True)
                else:
                    InfoBar.error("Lua 安裝失敗", msg, parent=self)
                    self._abort_deploy()
                return

            self.action_btn.setText("🚀 正在下載並安裝 Lua / 清單 (1/5)...")
            self.deploy_timer.stop() # Wait for async
            
            from managers import ryuu_manager, account_manager, lua_tools_manager, steam_manager
            acc_mgr = account_manager.get_account_manager()
            ryuu_client = ryuu_manager.get_shared_ryuu_client(self.main_app)
            ryuu_has_quota = (ryuu_client.is_logged_in or ryuu_manager.has_saved_ryuu_credentials()) and acc_mgr.has_available_quota("ryuu")

            def _deploy_via_assiw():
                self.action_btn.setText("🚀 正在從下級來源 Assiw 下載 Lua (1/5)...")
                lua_dir = self.main_app.steam_path / "config" / "lua"
                self.assiw_dl_thread = AssiwDownloadThread(appid, lua_dir, self)
                def _on_assiw_dl_done(ok, msg):
                    if ok:
                        self.chk_lua.setText("✅ 4. Lua / 清單補丁狀態: 已部署 (來源: Assiw)")
                        self.chk_lua.setStyleSheet(f"color: {get_state_color('success')};")
                        self._finish_lua(new_installed=True)
                    else:
                        InfoBar.warning("略過", f"該遊戲在各大來源均無可用補丁", parent=self)
                        self.chk_lua.setText("⚠️ 4. Lua / 清單補丁狀態: 無資源")
                        self.chk_lua.setStyleSheet(f"color: {get_state_color('warning')};")
                        self.lua_resource_status = "none"
                        self._finish_lua(new_installed=False)
                self.assiw_dl_thread.finished.connect(_on_assiw_dl_done)
                self.assiw_dl_thread.start()

            def _deploy_via_lt():
                client = lua_tools_manager.get_shared_client(self.main_app)
                if not client:
                    _deploy_via_assiw()
                    return

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
                        _deploy_via_assiw()
                        return
                        
                    available_source = None
                    priority = ["Ryuu"]
                    if isinstance(res, list):
                        for pref in priority:
                            for item in res:
                                s_name = str(item.get("name", item.get("source", ""))).strip()
                                av_val = item.get("available")
                                available = (str(av_val).lower() == "true" or bool(av_val)) if av_val else False
                                if available and s_name.lower() == pref.lower():
                                    available_source = pref
                                    break
                            if available_source: break
                    elif isinstance(res, dict):
                        for pref in priority:
                            for k, v in res.items():
                                if str(k).lower() == pref.lower():
                                    if isinstance(v, str) and (v.lower() == "available" or v.lower() == "true"):
                                        available_source = pref
                                        break
                            if available_source: break
                                
                    if not available_source:
                        _deploy_via_assiw()
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
                        lua_text = dl_res.get("lua_content", dl_res.get("data", "")) if isinstance(dl_res, dict) else ""
                        if isinstance(dl_res, dict) and (dl_res.get("error") or not lua_text):
                            _deploy_via_assiw()
                        else:
                            try:
                                lua_dir = self.main_app.steam_path / "config" / "lua"
                                lua_dir.mkdir(parents=True, exist_ok=True)
                                with open(lua_dir / f"{appid}.lua", "w", encoding="utf-8") as f:
                                    f.write(lua_text)
                                    
                                manifests = dl_res.get("manifests", {})
                                if not manifests:
                                    InfoBar.error(
                                        "安裝中止 (殘缺檔案)",
                                        "來源未提供二進位 .manifest 清單檔！\n依照最新防護規範，缺少 Manifest 的 Lua 檔直接判定為殘缺檔案，系統拒絕安裝。",
                                        parent=self,
                                        duration=6500,
                                        position=InfoBarPosition.TOP
                                    )
                                    self._abort_deploy()
                                    return

                                steam_manager.deploy_manifests_to_depotcache(manifests, self.main_app.steam_path, lua_dir)
                                steam_manager.sync_lua_with_deployed_manifests(appid, manifests, lua_dir)
                                steam_manager.sanitize_lua_manifests(appid, self.main_app.steam_path, lua_dir)
                                steam_manager.lock_game_version(appid, self.main_app.steam_path, set_readonly=True, game_name=getattr(self, 'current_app_name', ''))
                                            
                                m_count = len(manifests)
                                suffix = f" (含 {m_count} 個清單檔)" if m_count > 0 else ""
                                self.chk_lua.setText(f"✅ 4. Lua / 清單補丁狀態: 已部署{suffix} [Lua.tools] 🔒")
                                self.chk_lua.setStyleSheet(f"color: {get_state_color('success')};")
                                self._finish_lua(new_installed=True)
                            except Exception as e:
                                InfoBar.error("Lua 寫入失敗", str(e), parent=self)
                                self._abort_deploy()
                    
                    client.download_manifest(appid, available_source, f"Game_{appid}", on_dl)
                client.search_manifest(appid, on_search)

            def _deploy_via_ryuu():
                info = ryuu_manager.fetch_ryuu_manifest_info(appid)
                if not info.get("found"):
                    _deploy_via_lt()
                    return

                default_branch = info.get("default_branch", "public")
                self.chk_lua.setText(f"⏳ 4. 正在從 Ryuu Generator 下載清單 (分支: {default_branch})...")
                self.chk_lua.setStyleSheet(f"color: {get_state_color('warning')};")
                self.action_btn.setText("🚀 正在從 Ryuu 下載 Manifest 與 Lua (1/5)...")

                def on_ryuu_done(dl_res):
                    if not dl_res or (isinstance(dl_res, dict) and dl_res.get("error")):
                        # Ryuu 失敗，回退至 Lua.tools
                        _deploy_via_lt()
                        return

                    manifests = dl_res.get("manifests", {})
                    lua_text = dl_res.get("lua_content", dl_res.get("data", ""))
                    if not manifests:
                        _deploy_via_lt()
                        return

                    try:
                        lua_dir = self.main_app.steam_path / "config" / "lua"
                        lua_dir.mkdir(parents=True, exist_ok=True)
                        if lua_text:
                            with open(lua_dir / f"{appid}.lua", "w", encoding="utf-8") as f:
                                f.write(lua_text)

                        from managers import config_manager
                        custom_lua_dir = Path(config_manager.get_config().get("lua_dir", config_manager.DEFAULT_LUA_DIR))
                        if custom_lua_dir.resolve() != lua_dir.resolve():
                            custom_lua_dir.mkdir(parents=True, exist_ok=True)
                            if lua_text:
                                with open(custom_lua_dir / f"{appid}.lua", "w", encoding="utf-8") as f:
                                    f.write(lua_text)

                        steam_manager.deploy_manifests_to_depotcache(manifests, self.main_app.steam_path, lua_dir)
                        steam_manager.sync_lua_with_deployed_manifests(appid, manifests, lua_dir)
                        steam_manager.sync_lua_with_deployed_manifests(appid, manifests, custom_lua_dir)
                        steam_manager.sanitize_lua_manifests(appid, self.main_app.steam_path, lua_dir)
                        steam_manager.sanitize_lua_manifests(appid, self.main_app.steam_path, custom_lua_dir)
                        steam_manager.lock_game_version(appid, self.main_app.steam_path, set_readonly=True, game_name=getattr(self, 'current_app_name', ''))

                        m_count = len(manifests)
                        self.chk_lua.setText(f"✅ 4. Lua / 清單補丁狀態: 已部署 (含 {m_count} 個清單檔) [Ryuu] 🔒")
                        self.chk_lua.setStyleSheet(f"color: {get_state_color('success')};")
                        self._finish_lua(new_installed=True)
                    except Exception as e:
                        InfoBar.error("Lua 寫入失敗", str(e), parent=self)
                        self._abort_deploy()

                ryuu_client.download_manifest(appid, default_branch, on_ryuu_done)
            if ryuu_has_quota:
                _deploy_via_ryuu()
            else:
                _deploy_via_lt()
                
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
                from managers import steam_manager
                steam_manager.lock_game_version(appid, self.main_app.steam_path, set_readonly=True, game_name=getattr(self, 'current_app_name', ''))
                self.chk_game.setText("✅ 5. 遊戲安裝狀態: 已安裝")
                self.chk_game.setStyleSheet(f"color: {get_state_color('success')};")
                self.chk_lock.setText("✅ 6. 版本鎖定防護: 已鎖定 🔒 (防 401 封鎖)")
                self.chk_lock.setStyleSheet(f"color: {get_state_color('success')};")
                if hasattr(self, 'btn_cancel_wait'):
                    self.btn_cancel_wait.hide()
                self.deploy_step = 4 # Skip wait
            else:
                # 喚起 Steam 前先完成版本鎖定，防止 Steam 出現無連線 401 錯誤！
                from managers import steam_manager
                steam_manager.lock_game_version(appid, self.main_app.steam_path, set_readonly=True, game_name=getattr(self, 'current_app_name', ''))
                self.chk_lock.setText("✅ 6. 版本鎖定防護: 已鎖定 🔒 (防 401 封鎖)")
                self.chk_lock.setStyleSheet(f"color: {get_state_color('success')};")
                self.chk_game.setText("⏳ 5. 遊戲安裝狀態: 安裝中 (等待 Steam)...")
                self.chk_game.setStyleSheet(f"color: {get_state_color('warning')};")
                self.action_btn.setText("🚀 正在喚起 Steam 安裝遊戲 (2/5)...")
                import os
                import time
                try:
                    os.startfile(f"steam://install/{appid}")
                except:
                    pass
                self.wait_install_start_time = time.time()
                if hasattr(self, 'btn_cancel_wait'):
                    self.btn_cancel_wait.show()
                self.deploy_step = 3
                
        elif self.deploy_step == 3:
            # Wait for Game Install
            self.chk_game.setText("⏳ 5. 遊戲安裝狀態: 安裝中 (等待 Steam)...")
            self.chk_game.setStyleSheet(f"color: {get_state_color('warning')};")
            self.action_btn.setText("🚀 等待 Steam 遊戲安裝完畢 (3/5)...")
            if hasattr(self, 'btn_cancel_wait'):
                self.btn_cancel_wait.show()

            game_installed = False
            is_downloading = False
            try:
                if hasattr(self.main_app, 'lua_downloader_widget'):
                    game_dir_info = self.main_app.lua_downloader_widget._find_steam_game_dir(appid)
                    if game_dir_info and game_dir_info[1]:
                        flags = int(game_dir_info[1])
                        if (flags & 4) == 4:
                            game_installed = True
                        elif (flags & 1024) == 1024 or (flags & 512) == 512 or (flags & 2) == 2 or (flags & 16) == 16:
                            is_downloading = True
            except:
                pass
                
            if game_installed:
                from managers import steam_manager
                steam_manager.lock_game_version(appid, self.main_app.steam_path, set_readonly=True, game_name=getattr(self, 'current_app_name', ''))
                self.chk_game.setText("✅ 5. 遊戲安裝狀態: 已安裝")
                self.chk_game.setStyleSheet(f"color: {get_state_color('success')};")
                self.chk_lock.setText("✅ 6. 版本鎖定防護: 已鎖定 🔒 (防 401 封鎖)")
                self.chk_lock.setStyleSheet(f"color: {get_state_color('success')};")
                if hasattr(self, 'btn_cancel_wait'):
                    self.btn_cancel_wait.hide()
                self.deploy_step = 4
                return

            import time
            elapsed = time.time() - getattr(self, 'wait_install_start_time', time.time())
            if not is_downloading and elapsed > 35:
                # 等待逾時且未開始下載（可能是無授權），主動彈出處置面板防卡死
                self._manual_troubleshoot_install()

                
        elif self.deploy_step == 4:
            # Install OF
            self.chk_of.setText("⏳ 7. Online-Fix 狀態: 部署中...")
            self.chk_of.setStyleSheet(f"color: {get_state_color('warning')};")
            self.action_btn.setText("🚀 正在下載並打入 Online-Fix (4/5)...")
            self.deploy_timer.stop()
            
            from managers import onlinefix_manager
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            
            sources = onlinefix_manager.get_patch_sources(target_app_id=appid, target_app_name=getattr(self, 'current_app_name', ''))
            source = sources.get(str(appid))
            
            if source:
                rar_path = None
                if source and source.get('cloud_rar'):
                    self.chk_of.setText("⏳ 7. Online-Fix 狀態: 下載補丁中...")
                    QApplication.processEvents()
                    dl_path = onlinefix_manager.download_cloud_patch(appid, getattr(self, 'current_app_name', ''), source['cloud_rar'])
                    rar_path = dl_path if dl_path else None
                        
                if rar_path:
                    try:
                        game_dir_info = self.main_app.lua_downloader_widget._find_steam_game_dir(appid)
                        if game_dir_info and game_dir_info[0]:
                            drive_name = source.get('drive_name', '網盤 1') if source else 'Google Drive'
                            success, msg = onlinefix_manager.install_fix(appid, rar_path, game_dir_info[0], source_drive=drive_name)
                            if success:
                                self.chk_of.setText(f"✅ 7. Online-Fix 狀態: 已安裝 (來源: {drive_name})")
                                self.chk_of.setStyleSheet(f"color: {get_state_color('success')};")
                            else:
                                self.chk_of.setText("❌ 7. Online-Fix 狀態: 安裝失敗")
                                self.chk_of.setStyleSheet(f"color: {get_state_color('error')};")
                                InfoBar.error("Online-Fix 失敗", msg, parent=self)
                                self._abort_deploy()
                                return
                    except Exception as e:
                        self.chk_of.setText("❌ 7. Online-Fix 狀態: 安裝錯誤")
                        self.chk_of.setStyleSheet(f"color: {get_state_color('error')};")
                        InfoBar.error("錯誤", str(e), parent=self)
                        self._abort_deploy()
                        return
            else:
                self.chk_of.setText("⚠️ 7. Online-Fix 狀態: 雲端無檔")
                self.chk_of.setStyleSheet(f"color: {get_state_color('warning')};")
            
            self._finish_deploy()

    def _finish_lua(self, new_installed=False):
        # OpenSteamTools 具備即時目錄監聽熱重載，給予 0.5 秒讓監聽線程完成熱注入即可免重啟生效
        if new_installed:
            import time
            time.sleep(0.5)

        self.deploy_step = 2
        self.deploy_timer.start(1000)

    def _manual_troubleshoot_install(self):
        if not getattr(self, 'is_deploying', False) or self.deploy_step != 3:
            return

        self.deploy_timer.stop()
        dlg = InstallTroubleshootDialog(self.current_appid, self)
        dlg.exec()

        choice = getattr(dlg, 'choice', None)
        if choice == "skip":
            # 略過遊戲安裝，直接進入步驟 4 (Online-Fix 補丁)
            self.chk_game.setText("⚠️ 5. 遊戲安裝狀態: 已略過 (手動處理)")
            self.chk_game.setStyleSheet(f"color: {get_state_color('warning')};")
            if hasattr(self, 'btn_cancel_wait'):
                self.btn_cancel_wait.hide()
            self.deploy_step = 4
            self.deploy_timer.start(500)
        elif choice == "retry_restart":
            # 重啟 Steam 重新載入 Lua 授權
            from managers import steam_manager
            from PySide6.QtWidgets import QApplication
            self.action_btn.setText("⏳ 正在重啟 Steam 並重新套用授權...")
            self.chk_game.setText("⏳ 5. 遊戲安裝狀態: 正在重啟 Steam...")
            QApplication.processEvents()
            re_ok, re_msg, pid = steam_manager.restart_steam(self.main_app.steam_path)
            if re_ok:
                InfoBar.success("Steam 已重啟", "已重新載入 Lua 授權，正在再次嘗試喚起安裝...", parent=self)
                import os
                import time
                try:
                    os.startfile(f"steam://install/{self.current_appid}")
                except:
                    pass
                self.wait_install_start_time = time.time()
                self.deploy_step = 3
                self.deploy_timer.start(1000)
            else:
                InfoBar.error("重啟失敗", re_msg, parent=self)
                self._abort_deploy()
        else:
            # 中止部署
            self._abort_deploy()

    def _finish_deploy(self):
        self.is_deploying = False
        if hasattr(self, 'btn_cancel_wait'):
            self.btn_cancel_wait.hide()
        self.action_btn.setText("✅ 部署完成！")
        self.refresh_all_status()

    def _abort_deploy(self):
        self.is_deploying = False
        self.deploy_timer.stop()
        if hasattr(self, 'btn_cancel_wait'):
            self.btn_cancel_wait.hide()
        self.action_btn.setEnabled(True)
        self.refresh_all_status()

