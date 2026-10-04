import os
import json
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, QTimer, Signal, QDateTime
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QLabel, QStackedWidget
)
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView

from qfluentwidgets import (
    PrimaryPushButton, PushButton, ProgressBar, StrongBodyLabel,
    BodyLabel, SubtitleLabel, CaptionLabel, CardWidget, InfoBar,
    InfoBarPosition, SegmentedWidget, SwitchButton, ToolButton, FluentIcon,
    ComboBox, CheckBox, LineEdit
)
from managers.account_manager import get_account_manager, get_webengine_profile
from managers import lua_tools_manager, ryuu_manager
from ui.theme_utils import get_state_color


class AddAccountLoginDialog(QDialog):
    """
    登入並新增帳號的獨立無痕沙盒視窗。
    使用完全隔離的 QWebEngineProfile 目錄與 Discord RPC 阻斷防護，
    支援正規帳密登入與手機 Discord App QR Code 掃碼登入，100% 官方標準 Chromium 環境，零風控風險。
    """
    login_success = Signal(dict)

    def __init__(self, platform: str, parent=None):
        super().__init__(parent)
        self.platform = platform
        self.mgr = get_account_manager()
        self.acc_id, self.profile_dir = self.mgr.create_new_account_profile_dir(platform)
        self.detected_downloads_left = None
        self.user_display_name = None
        self._is_saving = False

        title_str = "登入並新增 Lua.tools 帳號" if platform == "lua_tools" else "登入並新增 Ryuu 帳號"
        self.setWindowTitle(f"🛡️ {title_str} (獨立安全沙盒)")
        self.resize(980, 750)
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
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(10)

        # 頂部：安全沙盒導引卡片
        nav_card = CardWidget(self)
        nav_layout = QHBoxLayout(nav_card)
        nav_layout.setContentsMargins(14, 10, 14, 10)
        nav_layout.setSpacing(10)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        lbl_mode = StrongBodyLabel("🛡️ 獨立安全沙盒環境已就緒", nav_card)
        lbl_hint = CaptionLabel("請在下方視窗輸入 Discord 帳號密碼，或使用手機 Discord App 掃描 QR 碼快速登入並點擊「授權」。", nav_card)
        info_col.addWidget(lbl_mode)
        info_col.addWidget(lbl_hint)
        nav_layout.addLayout(info_col, 1)

        self.btn_refresh = ToolButton(FluentIcon.SYNC, nav_card)
        self.btn_refresh.setToolTip("重新整理頁面")
        self.btn_refresh.clicked.connect(self._reload_page)

        self.btn_goto_home = PushButton("🏠 重新載入", nav_card)
        self.btn_goto_home.clicked.connect(self._goto_target_url)

        nav_layout.addWidget(self.btn_refresh)
        nav_layout.addWidget(self.btn_goto_home)
        layout.addWidget(nav_card)

        # 狀態列
        self.lbl_status = StrongBodyLabel("⏳ 正在載入官方授權登入頁面，請在下方視窗完成登入...", self)
        layout.addWidget(self.lbl_status)

        # 瀏覽器視圖（獨立 Profile）
        self.profile = get_webengine_profile(self.platform, self.acc_id, self.profile_dir)
        self.view = QWebEngineView(self)
        self.page = QWebEnginePage(self.profile, self.view)
        self.view.setPage(self.page)
        layout.addWidget(self.view, 1)

        # 底部動作列
        bottom_layout = QHBoxLayout()
        self.btn_confirm = PrimaryPushButton("✅ 儲存並套用此帳號", self)
        self.btn_confirm.clicked.connect(self._finish_registration)
        self.btn_cancel = PushButton("取消", self)
        self.btn_cancel.clicked.connect(self.reject)

        bottom_layout.addStretch(1)
        bottom_layout.addWidget(self.btn_cancel)
        bottom_layout.addWidget(self.btn_confirm)
        layout.addLayout(bottom_layout)

        self._target_url = "https://lua.tools/" if platform == "lua_tools" else "https://generator.ryuu.lol/login"
        self.view.load(QUrl(self._target_url))
        self.view.loadFinished.connect(self._on_load_finished)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._check_login)
        self.timer.start(1200)

    def _reload_page(self):
        self.view.reload()

    def _goto_target_url(self):
        self.view.load(QUrl(self._target_url))

    def _on_load_finished(self, ok):
        self._check_login()

    def _check_login(self):
        if self._is_saving:
            return

        if self.platform == "lua_tools":
            js = """
            (function() {
                var hasCookie = document.cookie.match(/sb-db-auth-token\\.\\d+=/) !== null;
                var hasLocal = Object.keys(localStorage || {}).some(function(k) { return k.indexOf('auth-token') !== -1; });
                return JSON.stringify({
                    logged_in: hasCookie || hasLocal,
                    name: null,
                    downloads_left: null
                });
            })();
            """
        else:
            js = """
            (function() {
                var hasProfile = document.getElementById('profile-menu') !== null || document.getElementById('profile-container') !== null;
                var dlEl = document.getElementById('downloads-left');
                var hasLogout = document.querySelector('a[href="/logout"]') !== null;
                var hasValidCookie = document.cookie.indexOf('session=') !== -1 || document.cookie.indexOf('auth=') !== -1;
                var dlText = dlEl ? dlEl.textContent.trim() : "";
                var dlNum = parseInt(dlText);
                var isHome = window.location.pathname === '/' || window.location.pathname === '';
                var loggedIn = hasProfile || (dlEl !== null) || hasLogout || (hasValidCookie && isHome);
                return JSON.stringify({
                    logged_in: loggedIn,
                    name: dlEl ? "Ryuu 帳號" : null,
                    downloads_left: isNaN(dlNum) ? null : dlNum
                });
            })();
            """
        self.page.runJavaScript(js, 0, self._on_auth_result)

    def _on_auth_result(self, res_json):
        if not res_json or self._is_saving:
            return
        try:
            data = json.loads(res_json) if isinstance(res_json, str) else res_json
            if data.get("logged_in"):
                dl = data.get("downloads_left")
                if dl is not None:
                    self.detected_downloads_left = dl
                    self.lbl_status.setText(f"🟢 登入授權成功！已偵測到可用配額：{dl} 次/日。正在保存憑證...")
                    self.lbl_status.setStyleSheet(f"color: {get_state_color('success')};")
                else:
                    self.lbl_status.setText("🟢 登入授權成功！已偵測到有效長效憑證。正在保存憑證...")
                    self.lbl_status.setStyleSheet(f"color: {get_state_color('success')};")
                
                # 自動延遲完成保存
                self._is_saving = True
                QTimer.singleShot(1000, self._finish_registration)
        except Exception:
            pass

    def _finish_registration(self):
        self.timer.stop()
        try:
            self.view.setPage(None)
        except Exception:
            pass
        acc = self.mgr.register_account(self.platform, self.acc_id, self.profile_dir, name=self.user_display_name)
        if self.detected_downloads_left is not None:
            limit = 50 if self.platform == "ryuu" else 25
            self.mgr.update_realtime_quota(self.platform, self.detected_downloads_left, daily_limit=limit, account_id=acc["id"])
        self.login_success.emit(acc)
        self.accept()

    def closeEvent(self, event):
        self.timer.stop()
        try:
            self.view.setPage(None)
        except Exception:
            pass
        super().closeEvent(event)


class DualPlatformLoginDialog(QDialog):
    """
    Ryuu 與 Lua.tools 雙平台同步授權登入精靈。
    在同一組乾淨的獨立沙盒 Session 下，依序引導完成 Ryuu (50 次/日) 與 Lua.tools (25 次/日) 授權綁定。
    """
    login_completed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚡ Ryuu & Lua.tools 雙平台同步授權登入")
        self.resize(980, 750)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.mgr = get_account_manager()

        try:
            from qfluentwidgets import isDarkTheme
            import ctypes
            hwnd = int(self.winId())
            value = ctypes.c_int(1 if isDarkTheme() else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass

        self.targets = []
        self.target_index = -1
        self.cur_platform = None
        self.cur_acc_id = None
        self.cur_profile_dir = None
        self.cur_profile = None
        self.created_accounts = []

        self._init_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._check_login_status)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # 1. 標題與說明
        header_layout = QVBoxLayout()
        title = SubtitleLabel("⚡ Ryuu & Lua.tools 雙平台一鍵同步登入", self)
        desc = BodyLabel(
            "透過獨立沙盒依序為 Ryuu Generator (50次/日) 與 Lua.tools (25次/日) 完成授權綁定。\n"
            "兩大平台各自擁有獨立憑證與長效配額池，額度耗盡時系統將自動輪替，全程 0 風控。",
            self
        )
        desc.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(desc)
        layout.addLayout(header_layout)

        # 2. 平台選擇卡片
        card = CardWidget(self)
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(15, 10, 15, 10)
        card_layout.setSpacing(12)

        self.chk_ryuu = CheckBox("登入 Ryuu Generator (generator.ryuu.lol - 每日 50 次額度)", card)
        self.chk_ryuu.setChecked(True)
        self.chk_lt = CheckBox("登入 Lua.tools (lua.tools - 每日 25 次額度)", card)
        self.chk_lt.setChecked(True)

        self.btn_start = PrimaryPushButton("🚀 開始雙平台登入", card)
        self.btn_start.clicked.connect(self._start_dual_flow)

        card_layout.addWidget(self.chk_ryuu)
        card_layout.addWidget(self.chk_lt)
        card_layout.addStretch(1)
        card_layout.addWidget(self.btn_start)
        layout.addWidget(card)

        # 3. 步驟進度卡片
        step_card = CardWidget(self)
        step_layout = QHBoxLayout(step_card)
        step_layout.setContentsMargins(15, 8, 15, 8)
        self.lbl_step_ryuu = StrongBodyLabel("1. Ryuu Generator: ⚪ 等待開始", step_card)
        self.lbl_step_lt = StrongBodyLabel("2. Lua.tools: ⚪ 等待開始", step_card)
        step_layout.addWidget(self.lbl_step_ryuu, 1)
        step_layout.addWidget(self.lbl_step_lt, 1)
        layout.addWidget(step_card)

        # 4. 即時狀態導引列
        self.lbl_status = StrongBodyLabel("💡 請點擊「開始雙平台登入」，系統將依序載入官方登入授權頁面...", self)
        layout.addWidget(self.lbl_status)

        # 5. 瀏覽器視圖
        self.view = QWebEngineView(self)
        self.view.loadFinished.connect(self._on_load_finished)
        layout.addWidget(self.view, 1)

        # 6. 底部按鈕
        bottom_layout = QHBoxLayout()
        self.btn_done = PrimaryPushButton("✅ 完成並關閉", self)
        self.btn_done.setEnabled(False)
        self.btn_done.clicked.connect(self.accept)
        self.btn_cancel = PushButton("關閉", self)
        self.btn_cancel.clicked.connect(self.reject)

        bottom_layout.addStretch(1)
        bottom_layout.addWidget(self.btn_cancel)
        bottom_layout.addWidget(self.btn_done)
        layout.addLayout(bottom_layout)

    def _start_dual_flow(self):
        self.targets = []
        if self.chk_ryuu.isChecked():
            self.targets.append("ryuu")
        if self.chk_lt.isChecked():
            self.targets.append("lua_tools")

        if not self.targets:
            InfoBar.warning("未勾選平台", "請至少勾選一個欲登入的網域平台！", parent=self, duration=3000)
            return

        self.btn_start.setEnabled(False)
        self.chk_ryuu.setEnabled(False)
        self.chk_lt.setEnabled(False)
        self.target_index = -1

        # 建立共用的獨立無痕沙盒 Profile，達成一次登入 Discord 即可連貫授權雙平台
        import uuid
        self.sync_session_id = f"dual_{uuid.uuid4().hex[:8]}"
        self.sync_acc_id, self.sync_profile_dir = self.mgr.create_new_account_profile_dir("dual_sync")
        self.sync_profile = get_webengine_profile("dual_sync", self.sync_acc_id, self.sync_profile_dir)
        page = QWebEnginePage(self.sync_profile, self.view)
        self.view.setPage(page)

        self._run_next_target()

    def _run_next_target(self):
        self.target_index += 1
        if self.target_index >= len(self.targets):
            self.timer.stop()
            self.lbl_status.setText("🎉 恭喜！雙平台帳號均已成功授權綁定，單帳號 75 次/日配額已就緒！")
            self.lbl_status.setStyleSheet(f"color: {get_state_color('success')};")
            self.btn_done.setEnabled(True)
            self.btn_done.setText("✅ 完成並關閉")
            self.login_completed.emit(self.created_accounts)
            InfoBar.success("雙平台授權成功", "已成功登入並建立 Ryuu 與 Lua.tools 長效憑證！", parent=self, duration=4000)
            return

        self.cur_platform = self.targets[self.target_index]
        self.cur_acc_id, self.cur_profile_dir = self.mgr.create_new_account_profile_dir(self.cur_platform)

        # 複製共用沙盒的 Cookies 到各平台專屬目錄
        import shutil
        src_cookies = Path(self.sync_profile_dir) / "Cookies"
        dst_cookies = Path(self.cur_profile_dir) / "Cookies"
        if src_cookies.exists():
            try:
                shutil.copy2(src_cookies, dst_cookies)
            except Exception:
                pass

        if self.cur_platform == "ryuu":
            self.lbl_step_ryuu.setText("1. Ryuu Generator: ⏳ 授權中...")
            self.lbl_step_ryuu.setStyleSheet(f"color: {get_state_color('processing')};")
            self.lbl_status.setText("💡 [步驟 1/2] 正在載入 Ryuu (generator.ryuu.lol) 授權頁面，請登入 Discord 並點擊「授權」...")
            self.lbl_status.setStyleSheet(f"color: {get_state_color('processing')};")
            target_url = "https://generator.ryuu.lol/login"
        else:
            self.lbl_step_lt.setText("2. Lua.tools: ⏳ 授權中...")
            self.lbl_step_lt.setStyleSheet(f"color: {get_state_color('processing')};")
            self.lbl_status.setText("💡 [步驟 2/2] 正在載入 Lua.tools (lua.tools)，Discord 身分已自動帶入，請直接點擊「授權」...")
            self.lbl_status.setStyleSheet(f"color: {get_state_color('processing')};")
            target_url = "https://lua.tools/"

        self.view.load(QUrl(target_url))
        self.timer.start(1200)

    def _on_load_finished(self, ok):
        self._check_login_status()

    def _check_login_status(self):
        if not self.cur_platform:
            return

        if self.cur_platform == "ryuu":
            js = """
            (function() {
                var hasProfile = document.getElementById('profile-menu') !== null || document.getElementById('profile-container') !== null;
                var dlEl = document.getElementById('downloads-left');
                var hasLogout = document.querySelector('a[href="/logout"]') !== null;
                var hasValidCookie = document.cookie.indexOf('session=') !== -1 || document.cookie.indexOf('auth=') !== -1;
                var dlText = dlEl ? dlEl.textContent.trim() : "";
                var dlNum = parseInt(dlText);
                var isHome = window.location.pathname === '/' || window.location.pathname === '';
                var loggedIn = hasProfile || (dlEl !== null) || hasLogout || (hasValidCookie && isHome);
                return JSON.stringify({
                    logged_in: loggedIn,
                    downloads_left: isNaN(dlNum) ? null : dlNum
                });
            })();
            """
        else:
            js = """
            (function() {
                var hasCookie = document.cookie.match(/sb-db-auth-token\\.\\d+=/) !== null;
                var hasLocal = Object.keys(localStorage || {}).some(function(k) { return k.indexOf('auth-token') !== -1; });
                return JSON.stringify({
                    logged_in: hasCookie || hasLocal,
                    downloads_left: null
                });
            })();
            """

        self.view.page().runJavaScript(js, 0, self._on_step_auth_result)

    def _on_step_auth_result(self, res_json):
        if not res_json or not self.cur_platform:
            return
        try:
            data = json.loads(res_json) if isinstance(res_json, str) else res_json
            if data.get("logged_in"):
                self.timer.stop()
                plat = self.cur_platform
                
                # 同步最新的 Session Cookie 到該帳號專屬目錄
                import shutil
                src_cookies = Path(self.sync_profile_dir) / "Cookies"
                dst_cookies = Path(self.cur_profile_dir) / "Cookies"
                if src_cookies.exists():
                    try:
                        shutil.copy2(src_cookies, dst_cookies)
                    except Exception:
                        pass

                acc = self.mgr.register_account(plat, self.cur_acc_id, self.cur_profile_dir)
                dl = data.get("downloads_left")
                limit = 50 if plat == "ryuu" else 25
                dl_val = dl if dl is not None else limit
                self.mgr.update_realtime_quota(plat, dl_val, daily_limit=limit, account_id=acc["id"])
                self.created_accounts.append(acc)

                if plat == "ryuu":
                    self.lbl_step_ryuu.setText(f"1. Ryuu Generator: 🟢 已完成 (配額: {dl_val} 次/日)")
                    self.lbl_step_ryuu.setStyleSheet(f"color: {get_state_color('success')};")
                else:
                    self.lbl_step_lt.setText(f"2. Lua.tools: 🟢 已完成 (配額: {dl_val} 次/日)")
                    self.lbl_step_lt.setStyleSheet(f"color: {get_state_color('success')};")

                # 自動切換到下一個目標
                QTimer.singleShot(1500, self._run_next_target)
        except Exception:
            pass

    def closeEvent(self, event):
        self.timer.stop()
        try:
            self.view.setPage(None)
        except Exception:
            pass
        super().closeEvent(event)






class MultiAccountManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("👥 多帳號憑證與配額管理中心")
        self.resize(920, 640)
        self.mgr = get_account_manager()

        self._init_ui()
        self._load_accounts()
        self.mgr.account_changed.connect(lambda *_: self._load_accounts())
        self.mgr.quota_updated.connect(lambda *_: self._load_accounts())
        self.mgr.registry_updated.connect(self._load_accounts)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 1. Header
        title = SubtitleLabel("👥 多帳號憑證切換與每日配額 (Quota) 守護", self)
        layout.addWidget(title)

        desc = BodyLabel(
            "透過【🛡️ 獨立無痕沙盒安全登入】，由使用者自行在官方 Chromium 介面登入 Discord 完成授權。\n"
            "系統即時監控各帳號當日剩餘下載配額，當單一帳號額度用罄 (HTTP 429) 時將自動無縫輪替，實現不間斷下載。",
            self
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 2. Controls & Auto Rotate Card
        opt_card = CardWidget(self)
        opt_layout = QHBoxLayout(opt_card)
        opt_layout.setContentsMargins(15, 10, 15, 10)

        self.lbl_auto_rotate = StrongBodyLabel("⚡ 自動輪替模式 (當前帳號額度耗盡時，自動切換至下一個可用帳號):", self)
        self.sw_auto_rotate = SwitchButton(self)
        self.sw_auto_rotate.setChecked(self.mgr.data.get("auto_rotate", True))
        self.sw_auto_rotate.checkedChanged.connect(self._on_auto_rotate_changed)
        opt_layout.addWidget(self.lbl_auto_rotate, 1)
        opt_layout.addWidget(self.sw_auto_rotate)
        layout.addWidget(opt_card)

        # 3. Platform Switch Tab
        self.segmented = SegmentedWidget(self)
        self.segmented.addItem("tab_lt", "1. Lua.tools 帳號群", onClick=lambda: self._switch_tab(0))
        self.segmented.addItem("tab_ryuu", "2. Ryuu Generator 帳號群", onClick=lambda: self._switch_tab(1))
        self.segmented.setCurrentItem("tab_lt")
        layout.addWidget(self.segmented)

        # 4. Accounts Table
        self.table = QTableWidget(self)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["使用中", "帳號名稱 / Email", "平台", "今日配額 (Quota)", "狀態", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 1)

        # 5. Summary Label
        self.lbl_summary = BodyLabel("總計可用次數計算中...", self)
        layout.addWidget(self.lbl_summary)

        # 6. Bottom Action Buttons (純沙盒安全登入)
        btn_layout = QHBoxLayout()
        self.btn_dual_login = PrimaryPushButton("🛡️ 雙平台安全沙盒登入 (Ryuu + Lua.tools)", self)
        self.btn_dual_login.setToolTip("安全模式：開啟獨立無痕 Chromium 沙盒，由使用者自行登入或掃碼授權，零風控")
        self.btn_dual_login.clicked.connect(self._open_dual_login)

        self.btn_add_single = PushButton("➕ 單獨沙盒登入", self)
        self.btn_add_single.setToolTip("在獨立無痕沙盒中單獨登入目前所選分頁的平台")
        self.btn_add_single.clicked.connect(lambda: self._open_add_account(self.current_platform))

        self.btn_probe_quota = PushButton("⚡ 探測配額", self)
        self.btn_probe_quota.clicked.connect(self._probe_current_platform_quota)

        self.btn_close = PushButton("關閉", self)
        self.btn_close.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_dual_login)
        btn_layout.addWidget(self.btn_add_single)
        btn_layout.addWidget(self.btn_probe_quota)
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

        self.current_platform = "lua_tools"

    def _open_fast_auth(self):
        dlg = FastLocalAccountAuthDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self._load_accounts()

    def _probe_current_platform_quota(self):
        self.btn_probe_quota.setEnabled(False)
        self.btn_probe_quota.setText("⏳ 正在探測配額...")

        def on_probed(info):
            self.btn_probe_quota.setEnabled(True)
            self.btn_probe_quota.setText("⚡ 探測配額 (Try Quota)")
            self._load_accounts()
            msg = info.get("message", "探測完畢")
            if info.get("valid"):
                InfoBar.success("探測結果", f"{info.get('platform', '').upper()}: {msg}", parent=self, duration=4000)
            elif info.get("status") == "expired":
                InfoBar.error("憑證過期", f"{info.get('platform', '').upper()}: {msg}，請重新授權！", parent=self, duration=6000)
            elif info.get("status") == "exhausted":
                InfoBar.warning("配額已用罄", f"{info.get('platform', '').upper()}: {msg}，已自動標記該帳號！", parent=self, duration=5000)
            else:
                InfoBar.info("探測回饋", f"{info.get('platform', '').upper()}: {msg}", parent=self, duration=4000)

        if self.current_platform == "lua_tools":
            lua_tools_manager.get_shared_client().probe_quota(on_probed)
        else:
            ryuu_manager.get_shared_ryuu_client().probe_quota(on_probed)

    def _switch_tab(self, idx):
        self.current_platform = "lua_tools" if idx == 0 else "ryuu"
        self._load_accounts()

    def _on_auto_rotate_changed(self, checked):
        self.mgr.data["auto_rotate"] = checked
        self.mgr.save_data()

    def _open_dual_login(self):
        dlg = DualPlatformLoginDialog(self)
        if dlg.exec() == QDialog.Accepted:
            InfoBar.success(
                "雙平台登入成功",
                "已成功為 Ryuu 與 Lua.tools 同步新增並啟用最新憑證！",
                parent=self,
                duration=4000
            )
            self._load_accounts()

    def _open_add_account(self, platform: str):
        dlg = AddAccountLoginDialog(platform, self)
        if dlg.exec() == QDialog.Accepted:
            InfoBar.success(
                "新增帳號成功",
                f"已成功登入並保存新的 {platform.upper()} 帳號憑證！",
                parent=self,
                duration=3000
            )
            self._load_accounts()

    def _load_accounts(self):
        accounts = self.mgr.get_accounts(self.current_platform)
        active_acc = self.mgr.get_active_account(self.current_platform)
        active_id = active_acc["id"] if active_acc else None

        self.table.setRowCount(len(accounts))
        for row, acc in enumerate(accounts):
            acc_id = acc.get("id")
            is_active = (acc_id == active_id)

            # 0. Active Badge
            it_active = QTableWidgetItem("⭐ 使用中" if is_active else "")
            it_active.setTextAlignment(Qt.AlignCenter)
            it_active.setFlags(it_active.flags() & ~Qt.ItemIsEditable)
            if is_active:
                it_active.setForeground(Qt.green)
            self.table.setItem(row, 0, it_active)

            # 1. Name & Email
            name_str = acc.get("name", "帳號")
            email_str = acc.get("email", "")
            display_str = f"{name_str} ({email_str})" if email_str else name_str
            it_name = QTableWidgetItem(display_str)
            it_name.setFlags(it_name.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, it_name)

            # 2. Platform
            it_plat = QTableWidgetItem("Lua.tools" if acc.get("platform") == "lua_tools" else "Ryuu")
            it_plat.setTextAlignment(Qt.AlignCenter)
            it_plat.setFlags(it_plat.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 2, it_plat)

            # 3. Quota
            used = acc.get("quota_used_today", 0)
            limit = acc.get("daily_limit", 25)
            rem = max(0, limit - used)
            it_quota = QTableWidgetItem(f"剩餘 {rem} / {limit} 次 (今日已用 {used})")
            it_quota.setTextAlignment(Qt.AlignCenter)
            it_quota.setFlags(it_quota.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 3, it_quota)

            # 4. Status
            is_expired = acc.get("is_expired", False)
            is_exhausted = acc.get("is_exhausted", False) or (rem <= 0)
            if is_expired:
                it_status = QTableWidgetItem("❌ 憑證已過期")
                it_status.setForeground(Qt.red)
            elif is_exhausted:
                it_status = QTableWidgetItem("🔴 配額已滿")
                it_status.setForeground(Qt.yellow)
            else:
                it_status = QTableWidgetItem("🟢 正常可用")
                it_status.setForeground(Qt.green)
            it_status.setTextAlignment(Qt.AlignCenter)
            it_status.setFlags(it_status.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 4, it_status)

            # 5. Actions (Switch / Delete)
            cell_widget = QWidget()
            cell_layout = QHBoxLayout(cell_widget)
            cell_layout.setContentsMargins(4, 2, 4, 2)
            cell_layout.setSpacing(6)

            if not is_active:
                btn_set = PushButton("切換", cell_widget)
                btn_set.setFixedHeight(26)
                btn_set.clicked.connect(lambda _, a=acc_id: self._set_active(a))
                cell_layout.addWidget(btn_set)

            btn_del = PushButton("刪除", cell_widget)
            btn_del.setFixedHeight(26)
            btn_del.clicked.connect(lambda _, a=acc_id: self._delete_acc(a))
            cell_layout.addWidget(btn_del)

            self.table.setCellWidget(row, 5, cell_widget)

        rem_total, limit_total = self.mgr.get_total_remaining_quota(self.current_platform)
        plat_name = "Lua.tools" if self.current_platform == "lua_tools" else "Ryuu"
        self.lbl_summary.setText(
            f"📊 【{plat_name} 總計】共綁定 {len(accounts)} 個帳號 | 今日總剩餘可用配額: {rem_total} / {limit_total} 次"
        )

    def _set_active(self, acc_id: str):
        self.mgr.set_active_account(self.current_platform, acc_id)
        # Switch WebClient profile
        acc = self.mgr.get_active_account(self.current_platform)
        if self.current_platform == "lua_tools":
            lua_tools_manager.get_shared_client().switch_to_account(acc)
        else:
            ryuu_manager.get_shared_ryuu_client().switch_to_account(acc)
        self._load_accounts()

    def _delete_acc(self, acc_id: str):
        self.mgr.delete_account(self.current_platform, acc_id)
        self._load_accounts()
