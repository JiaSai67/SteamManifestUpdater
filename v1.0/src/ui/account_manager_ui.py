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
    ComboBox, CheckBox
)
from managers.account_manager import get_account_manager, get_webengine_profile
from managers import lua_tools_manager, ryuu_manager
from ui.theme_utils import get_state_color
from utils.discord_token_scanner import scan_local_discord_tokens, login_ryuu_with_discord_token


class AddAccountLoginDialog(QDialog):
    """
    登入並新增帳號的獨立視窗。使用隔離的 QWebEngineProfile 目錄，支援內建瀏覽器登入與手動貼上 Session。
    """
    login_success = Signal(dict)

    def __init__(self, platform: str, parent=None):
        super().__init__(parent)
        self.platform = platform
        self.mgr = get_account_manager()
        self.acc_id, self.profile_dir = self.mgr.create_new_account_profile_dir(platform)
        self.detected_downloads_left = None
        self.user_display_name = None

        title_str = "登入並新增 Lua.tools 帳號" if platform == "lua_tools" else "登入並新增 Ryuu 帳號"
        self.setWindowTitle(f"➕ {title_str} (Discord OAuth)")
        self.resize(920, 700)
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

        # 頂部：本機 Discord 帳號快選面板
        dc_card = CardWidget(self)
        dc_layout = QHBoxLayout(dc_card)
        dc_layout.setContentsMargins(12, 8, 12, 8)
        dc_layout.setSpacing(8)

        lbl_dc = StrongBodyLabel("⚡ 本機已登入 Discord 帳號：", dc_card)
        self.combo_discord = ComboBox(dc_card)
        self.combo_discord.setMinimumWidth(260)
        self.btn_inject_discord = PrimaryPushButton("🔑 一鍵帶入此身分登入", dc_card)
        self.btn_inject_discord.clicked.connect(self._apply_selected_discord_token)

        self.btn_switch_account = PushButton("🔄 手動輸入其他帳密", dc_card)
        self.btn_switch_account.setToolTip("跳轉至 Discord 官方登入頁面手動輸入帳號密碼")
        self.btn_switch_account.clicked.connect(self._goto_discord_switch)

        dc_layout.addWidget(lbl_dc)
        dc_layout.addWidget(self.combo_discord, 1)
        dc_layout.addWidget(self.btn_inject_discord)
        dc_layout.addWidget(self.btn_switch_account)
        layout.addWidget(dc_card)

        # 頂部提示與狀態列
        self.lbl_status = StrongBodyLabel("⏳ 請點擊「一鍵帶入此身分登入」，或在下方頁面中點擊登入並授權 Discord 帳號...", self)
        layout.addWidget(self.lbl_status)

        # 瀏覽器視圖
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

        # 載入本機 Discord 帳號選項
        self._load_local_discord_accounts()

        self._pending_inject_token = None
        self._target_url = "https://lua.tools/" if platform == "lua_tools" else "https://generator.ryuu.lol/login"
        self.view.load(QUrl(self._target_url))
        self.view.loadFinished.connect(self._on_load_finished)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._check_login)
        self.timer.start(1200)

    def _load_local_discord_accounts(self):
        self.combo_discord.clear()
        try:
            tokens = scan_local_discord_tokens()
        except Exception:
            tokens = []

        if tokens:
            for t in tokens:
                d_name = t.get("display_name") or t.get("username")
                u_name = t.get("username", "")
                text = f"👤 {d_name}" if (u_name and f"@{u_name}" in d_name) else f"👤 {d_name} (@{u_name})"
                self.combo_discord.addItem(text, userData=t)
            self.combo_discord.addItem("🌐 手動登入 (不使用本機 Token)", userData=None)
        else:
            self.combo_discord.addItem("⚠️ 未在電腦中偵測到已登入的 Discord 帳號", userData=None)
            self.btn_inject_discord.setEnabled(False)

    def _apply_selected_discord_token(self):
        data = self.combo_discord.currentData()
        if not data or not data.get("token"):
            InfoBar.warning("未選擇身分", "請選擇有效的本機 Discord 帳號，或使用手動登入！", parent=self, duration=3000)
            return

        token = data["token"]
        d_name = data.get("display_name") or data.get("username")
        u_name = data.get("username", "")
        self.user_display_name = d_name if (u_name and f"@{u_name}" in d_name) else f"{d_name} (@{u_name})"

        if self.platform == "ryuu":
            self.lbl_status.setText(f"🔑 正在以純 Token API 直接授權 Ryuu 身分 [{self.user_display_name}]，請稍候...")
            self.lbl_status.setStyleSheet(f"color: {get_state_color('processing')};")

            res = login_ryuu_with_discord_token(token)
            if res.get("success"):
                session_val = res.get("session")
                self.detected_downloads_left = res.get("downloads_left", 50)
                # 注入 Cookie 到 QWebEngineProfile
                cookie_store = self.profile.cookieStore()
                cookie = QNetworkCookie(b"session", session_val.encode())
                cookie.setDomain(".generator.ryuu.lol")
                cookie.setPath("/")
                cookie.setExpirationDate(QDateTime.currentDateTime().addDays(30))
                cookie_store.setCookie(cookie, QUrl("https://generator.ryuu.lol/"))

                self.lbl_status.setText(f"🟢 [Token 直接授權成功] 已獲取 Ryuu 憑證與配額：{self.detected_downloads_left} 次/日！點擊右下方「儲存並套用」完成。")
                self.lbl_status.setStyleSheet(f"color: {get_state_color('success')};")
                InfoBar.success("授權成功", f"已成功以 [{self.user_display_name}] 身分完成 Ryuu 授權！", parent=self, duration=4000)
                self.view.load(QUrl("https://generator.ryuu.lol/"))
                return
            elif res.get("error") == "not_in_server":
                self.lbl_status.setText(f"⚠️ [{self.user_display_name}] 尚未加入 Ryuu 官方伺服器！請點擊下方頁面「接受邀請」加入 discord.gg/manifests")
                self.lbl_status.setStyleSheet(f"color: {get_state_color('warning')};")
                InfoBar.warning("未加入伺服器", f"帳號 [{self.user_display_name}] 尚未加入 Ryuu 官方伺服器！已為您載入邀請頁面，請加入伺服器後再次點擊帶入身分。", parent=self, duration=9000)
                self.view.load(QUrl("https://discord.gg/manifests"))
                return
            else:
                InfoBar.error("授權失敗", f"Ryuu Token 授權失敗: {res.get('message')}", parent=self, duration=5000)

        # 非 Ryuu 或 fallback
        self._pending_inject_token = token
        self.lbl_status.setText(f"🔑 正在帶入 Discord 身分 [{self.user_display_name}]，請稍候...")
        self.lbl_status.setStyleSheet(f"color: {get_state_color('processing')};")
        self.view.load(QUrl(self._target_url))

    def _on_load_finished(self, ok):
        url = self.view.url().toString()
        if self._pending_inject_token and "discord.com/login" in url:
            tok = self._pending_inject_token
            self._pending_inject_token = None
            next_url = self._target_url
            inject_js = f"""
            (function() {{
                try {{
                    let iframe = document.createElement('iframe');
                    document.body.appendChild(iframe);
                    iframe.contentWindow.localStorage.setItem('token', `"{tok}"`);
                    window.localStorage.setItem('token', `"{tok}"`);
                }} catch(e) {{}}
                window.location.href = "{next_url}";
            }})();
            """
            self.page.runJavaScript(inject_js)
            self.lbl_status.setText(f"🚀 已切換身分為 [{self.user_display_name}]，正在跳轉至授權頁面...")
        self._check_login()

    def _goto_discord_switch(self):
        self.lbl_status.setText("🔄 正在跳轉至 Discord 官方登入頁面，請手動輸入帳號密碼...")
        self.view.load(QUrl("https://discord.com/login"))

    def _check_login(self):
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
        if not res_json: return
        try:
            data = json.loads(res_json) if isinstance(res_json, str) else res_json
            if data.get("logged_in"):
                dl = data.get("downloads_left")
                if dl is not None:
                    self.detected_downloads_left = dl
                    self.lbl_status.setText(f"🟢 登入成功！已偵測到可用配額：{dl} 次/日。請點擊右下方「儲存並套用」完成。")
                    self.lbl_status.setStyleSheet(f"color: {get_state_color('success')};")
                else:
                    self.lbl_status.setText("🟢 偵測到登入憑證有效！請點擊右下方「儲存並套用」完成。")
                    self.lbl_status.setStyleSheet(f"color: {get_state_color('success')};")
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
    一鍵掃描並帶入本機 Discord 帳號身分，依序為 Ryuu (50 次/日) 與 Lua.tools (25 次/日) 完成綁定。
    """
    login_completed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚡ Ryuu & Lua.tools 雙平台同步授權登入")
        self.resize(960, 720)
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
        self.user_display_name = None
        self.created_accounts = []
        self._pending_inject = None

        self._init_ui()
        self._load_local_discord_accounts()

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
            "自動載入本機已登入的 Discord 分身或主帳號，一鍵同時完成 Ryuu Generator (50次/日) 與 Lua.tools (25次/日) 授權綁定。\n"
            "兩大平台各自擁有獨立憑證與配額池，額度耗盡時系統將自動輪替。",
            self
        )
        desc.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(desc)
        layout.addLayout(header_layout)

        # 2. 身分與平台設定卡片
        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(15, 12, 15, 12)
        card_layout.setSpacing(10)

        row1 = QHBoxLayout()
        lbl_acc = StrongBodyLabel("👤 選擇本機 Discord 身分：", card)
        self.combo_discord = ComboBox(card)
        self.combo_discord.setMinimumWidth(280)
        self.btn_refresh_tokens = ToolButton(FluentIcon.SYNC, card)
        self.btn_refresh_tokens.setToolTip("重新掃描電腦中已登入的 Discord 帳號")
        self.btn_refresh_tokens.clicked.connect(self._load_local_discord_accounts)

        row1.addWidget(lbl_acc)
        row1.addWidget(self.combo_discord, 1)
        row1.addWidget(self.btn_refresh_tokens)
        card_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.chk_ryuu = CheckBox("登入 Ryuu Generator (generator.ryuu.lol - 每日 50 次額度)", card)
        self.chk_ryuu.setChecked(True)
        self.chk_lt = CheckBox("登入 Lua.tools (lua.tools - 每日 25 次額度)", card)
        self.chk_lt.setChecked(True)

        self.btn_start = PrimaryPushButton("🚀 開始雙平台同步登入", card)
        self.btn_start.clicked.connect(self._start_dual_flow)

        row2.addWidget(self.chk_ryuu)
        row2.addWidget(self.chk_lt)
        row2.addStretch(1)
        row2.addWidget(self.btn_start)
        card_layout.addLayout(row2)
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
        self.lbl_status = StrongBodyLabel("💡 請選擇欲綁定的 Discord 身分後，點擊「開始雙平台同步登入」...", self)
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

    def _load_local_discord_accounts(self):
        self.combo_discord.clear()
        try:
            tokens = scan_local_discord_tokens()
        except Exception:
            tokens = []

        if tokens:
            for t in tokens:
                d_name = t.get("display_name") or t.get("username")
                u_name = t.get("username", "")
                text = f"👤 {d_name}" if (u_name and f"@{u_name}" in d_name) else f"👤 {d_name} (@{u_name})"
                self.combo_discord.addItem(text, userData=t)
            self.combo_discord.addItem("🌐 手動在視窗中登入 Discord", userData=None)
        else:
            self.combo_discord.addItem("⚠️ 未在電腦中偵測到已登入的 Discord 帳號", userData=None)

    def _start_dual_flow(self):
        self.targets = []
        if self.chk_ryuu.isChecked():
            self.targets.append("ryuu")
        if self.chk_lt.isChecked():
            self.targets.append("lua_tools")

        if not self.targets:
            InfoBar.warning("未勾選平台", "請至少勾選一個欲登入的網域平台！", parent=self, duration=3000)
            return

        token_data = self.combo_discord.currentData()
        if token_data:
            d_name = token_data.get("display_name") or token_data.get("username")
            u_name = token_data.get("username", "")
            self.user_display_name = d_name if (u_name and f"@{u_name}" in d_name) else f"{d_name} (@{u_name})"
        else:
            self.user_display_name = "手動登入身分"

        self.btn_start.setEnabled(False)
        self.combo_discord.setEnabled(False)
        self.chk_ryuu.setEnabled(False)
        self.chk_lt.setEnabled(False)
        self.target_index = -1
        self._run_next_target()

    def _run_next_target(self):
        self.target_index += 1
        if self.target_index >= len(self.targets):
            self.timer.stop()
            self.lbl_status.setText("🎉 恭喜！所選網域平台的帳號與下載配額均已成功綁定保存！")
            self.lbl_status.setStyleSheet(f"color: {get_state_color('success')};")
            self.btn_done.setEnabled(True)
            self.btn_done.setText("✅ 完成並關閉")
            self.login_completed.emit(self.created_accounts)
            InfoBar.success("雙平台登入成功", "已成功登入並建立憑證！", parent=self, duration=4000)
            return

        self.cur_platform = self.targets[self.target_index]
        self.cur_acc_id, self.cur_profile_dir = self.mgr.create_new_account_profile_dir(self.cur_platform)
        self.cur_profile = get_webengine_profile(self.cur_platform, self.cur_acc_id, self.cur_profile_dir)
        page = QWebEnginePage(self.cur_profile, self.view)
        self.view.setPage(page)

        token_data = self.combo_discord.currentData()
        token = token_data.get("token") if token_data else None

        if self.cur_platform == "ryuu" and token:
            self.lbl_step_ryuu.setText("1. Ryuu Generator: ⏳ Token 授權中...")
            self.lbl_step_ryuu.setStyleSheet(f"color: {get_state_color('processing')};")
            self.lbl_status.setText(f"🔑 正在使用 Token 直接為 Ryuu 執行後端授權...")
            self.lbl_status.setStyleSheet(f"color: {get_state_color('processing')};")

            res = login_ryuu_with_discord_token(token)
            if res.get("success"):
                session_val = res.get("session")
                cookie_store = self.cur_profile.cookieStore()
                cookie = QNetworkCookie(b"session", session_val.encode())
                cookie.setDomain(".generator.ryuu.lol")
                cookie.setPath("/")
                cookie.setExpirationDate(QDateTime.currentDateTime().addDays(30))
                cookie_store.setCookie(cookie, QUrl("https://generator.ryuu.lol/"))

                acc = self.mgr.register_account("ryuu", self.cur_acc_id, self.cur_profile_dir, name=self.user_display_name)
                dl_val = res.get("downloads_left", 50)
                self.mgr.update_realtime_quota("ryuu", dl_val, daily_limit=50, account_id=acc["id"])
                self.created_accounts.append(acc)

                self.lbl_step_ryuu.setText(f"1. Ryuu Generator: 🟢 已完成 (配額: {dl_val} 次/日)")
                self.lbl_step_ryuu.setStyleSheet(f"color: {get_state_color('success')};")
                self.lbl_status.setText(f"🟢 Ryuu 授權成功 (配額: {dl_val} 次/日)，正在進入步驟 2 (Lua.tools)...")
                self.lbl_status.setStyleSheet(f"color: {get_state_color('success')};")

                QTimer.singleShot(1200, self._run_next_target)
                return
            elif res.get("error") == "not_in_server":
                self.lbl_step_ryuu.setText("1. Ryuu Generator: ⚠️ 尚未加入伺服器")
                self.lbl_step_ryuu.setStyleSheet(f"color: {get_state_color('warning')};")
                self.lbl_status.setText(f"⚠️ [{self.user_display_name}] 尚未加入 Ryuu 伺服器！請在下方點擊「加入伺服器」...")
                self.lbl_status.setStyleSheet(f"color: {get_state_color('warning')};")
                InfoBar.warning("未加入伺服器", f"帳號 [{self.user_display_name}] 尚未加入 Ryuu 官方伺服器！請加入 discord.gg/manifests 後重試。", parent=self, duration=9000)
                self.view.load(QUrl("https://discord.gg/manifests"))
                return

        if self.cur_platform == "ryuu":
            self.lbl_step_ryuu.setText("1. Ryuu Generator: ⏳ 授權中...")
            self.lbl_step_ryuu.setStyleSheet(f"color: {get_state_color('processing')};")
            self.lbl_status.setText("💡 正在為 Ryuu Generator (generator.ryuu.lol) 載入授權頁面，請在下方確認並點擊「授權」...")
            self.lbl_status.setStyleSheet(f"color: {get_state_color('processing')};")
            target_url = "https://generator.ryuu.lol/login"
        else:
            self.lbl_step_lt.setText("2. Lua.tools: ⏳ 授權中...")
            self.lbl_step_lt.setStyleSheet(f"color: {get_state_color('processing')};")
            self.lbl_status.setText("💡 正在為 Lua.tools (lua.tools) 載入授權頁面，請在下方確認並點擊「授權」...")
            self.lbl_status.setStyleSheet(f"color: {get_state_color('processing')};")
            target_url = "https://lua.tools/"

        self._pending_inject = None
        self.view.load(QUrl(target_url))
        self.timer.start(1200)

    def _on_load_finished(self, ok):
        url = self.view.url().toString()
        if self._pending_inject and "discord.com/login" in url:
            next_url, tok = self._pending_inject
            self._pending_inject = None
            inject_js = f"""
            (function() {{
                try {{
                    let iframe = document.createElement('iframe');
                    document.body.appendChild(iframe);
                    iframe.contentWindow.localStorage.setItem('token', `"{tok}"`);
                    window.localStorage.setItem('token', `"{tok}"`);
                }} catch(e) {{}}
                window.location.href = "{next_url}";
            }})();
            """
            self.view.page().runJavaScript(inject_js)
            self.lbl_status.setText(f"🚀 已切換身分為 [{self.user_display_name}]，正在跳轉至授權頁面...")

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
                acc = self.mgr.register_account(plat, self.cur_acc_id, self.cur_profile_dir, name=self.user_display_name)
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
        self.resize(880, 620)
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
            "可同時登入並保存多個 Discord/Lua.tools/Ryuu 帳號憑證。\n"
            "系統將即時監控各帳號當日剩餘下載配額，當單一帳號額度用罄 (HTTP 429) 時將自動無縫輪替，實現不間斷下載。",
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

        # 6. Bottom Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_dual_login = PrimaryPushButton("⚡ 雙平台同步一鍵登入 (Ryuu & Lua.tools)", self)
        self.btn_dual_login.setToolTip("推薦：同時登入 Ryuu 與 Lua.tools，獲取最大下載配額")
        self.btn_dual_login.clicked.connect(self._open_dual_login)

        self.btn_probe_quota = PushButton("⚡ 探測配額", self)
        self.btn_probe_quota.clicked.connect(self._probe_current_platform_quota)

        self.btn_add_lt = PushButton("➕ 單獨登入 Lua.tools", self)
        self.btn_add_lt.clicked.connect(lambda: self._open_add_account("lua_tools"))

        self.btn_add_ryuu = PushButton("➕ 單獨登入 Ryuu", self)
        self.btn_add_ryuu.clicked.connect(lambda: self._open_add_account("ryuu"))

        self.btn_close = PushButton("關閉", self)
        self.btn_close.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_dual_login)
        btn_layout.addWidget(self.btn_probe_quota)
        btn_layout.addWidget(self.btn_add_lt)
        btn_layout.addWidget(self.btn_add_ryuu)
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

        self.current_platform = "lua_tools"

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
                InfoBar.error("憑證過期", f"{info.get('platform', '').upper()}: {msg}，請點擊「➕ 登入」重新授權！", parent=self, duration=6000)
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
