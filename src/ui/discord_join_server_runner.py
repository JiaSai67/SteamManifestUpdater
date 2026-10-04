# -*- coding: utf-8 -*-
"""
SteamManifestUpdater - Discord Token 直達加入伺服器助手
專為 Discord 帳號身分設計：於獨立無痕環境中載入 Discord，使用 Token（或帳密/手動貼入 Token）進行身分認證，
自動直達 Ryuu 官方伺服器邀請頁面 (discord.gg/manifests)，
自動突破「在瀏覽器中繼續」中介確認頁，並自動輔助點擊「接受邀請」。
偵測到加群成功後，立即自動向 Ryuu 伺服器換取 50 次/日 配額、寫入資料庫並優雅自動關閉。
"""

import os
import sys
import json
import time
import argparse
import sqlite3
import shutil
import tempfile
from pathlib import Path

_src_dir = Path(__file__).resolve().parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

# 自動設定 Qt 平台外掛與 Windows DLL 搜尋目錄，徹底防止 Qt Platform Plugin 初始化失敗崩潰
try:
    import PySide6
    _pyside_dir = Path(PySide6.__file__).parent
    _platforms_dir = _pyside_dir / "plugins" / "platforms"
    if _platforms_dir.exists():
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(_platforms_dir)
        os.environ["QT_PLUGIN_PATH"] = str(_pyside_dir / "plugins")
    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(str(_pyside_dir))
            os.add_dll_directory(str(_pyside_dir / "bin"))
        except Exception:
            pass
    os.environ["PATH"] = f"{_pyside_dir};{_pyside_dir / 'bin'};{os.environ.get('PATH', '')}"
except Exception:
    pass

from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QWidget,
    QLabel, QPushButton, QProgressBar, QFrame, QLineEdit
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineScript
from PySide6.QtWebEngineWidgets import QWebEngineView

from managers.account_manager import get_account_manager, _ROOT_DIR
from utils.discord_token_scanner import (
    clean_discord_token, login_ryuu_with_discord_token, RYUU_GUILD_ID,
    save_token_to_vault, get_token_from_vault, scan_local_discord_tokens,
    verify_discord_token
)


class DiscordJoinServerWindow(QDialog):
    def __init__(self, token: str = "", account_id: str = None, display_name: str = None, parent=None):
        super().__init__(parent)
        self.token = clean_discord_token(token) if token else ""
        self.account_id = account_id or ""
        self.display_name = display_name or "Discord 帳號"
        self.has_joined = False
        self.injected_token = False
        self.is_discord_logged_in = False
        self.navigated_to_invite = False
        self.mgr = get_account_manager()

        # 讀取本機掃描到的身分候選快取
        self.scanned_accounts = []
        scanned_cache_file = _ROOT_DIR / "data" / "credentials" / "scanned_discord_accounts.json"
        if scanned_cache_file.exists():
            try:
                with open(scanned_cache_file, "r", encoding="utf-8") as scf:
                    self.scanned_accounts = json.load(scf)
            except Exception:
                pass

        # 若未提供 token，嘗試由 Token Vault / 登錄表 / 本機掃描中智慧補足
        if not self.token:
            if self.account_id:
                self.token = get_token_from_vault(self.account_id)
            if not self.token and self.display_name:
                self.token = get_token_from_vault(self.display_name)
            # 嘗試從名稱中提取 @用戶名 或 純暱稱比對
            if not self.token and self.display_name:
                import re
                m = re.search(r'@([a-zA-Z0-9_\.]+)', self.display_name)
                if m:
                    self.token = get_token_from_vault(m.group(1))
                if not self.token:
                    clean_n = re.sub(r'[\(\)@\s]', '', self.display_name)
                    self.token = get_token_from_vault(clean_n)
            # 查閱帳號註冊表對應的 discord_id
            if not self.token:
                accs = self.mgr.get_accounts("ryuu") + self.mgr.get_accounts("lua_tools")
                for a in accs:
                    if (self.account_id and a.get("id") == self.account_id) or \
                       (self.display_name and (self.display_name in a.get("name", "") or a.get("name", "") in self.display_name)):
                        did = a.get("discord_id")
                        if did:
                            self.token = get_token_from_vault(did)
                            if self.token:
                                break
            # 從本機掃描到的身分中尋找匹配 (比對 Discord ID 或精確/模糊用戶名)
            if not self.token and self.scanned_accounts:
                t_did = ""
                for a in self.mgr.get_accounts("ryuu") + self.mgr.get_accounts("lua_tools"):
                    if (self.account_id and a.get("id") == self.account_id) or \
                       (self.display_name and (self.display_name in a.get("name", "") or a.get("name", "") in self.display_name)):
                        t_did = str(a.get("discord_id", "")).strip()
                        if t_did:
                            break

                t_name_lower = self.display_name.lower()
                clean_t_name = re.sub(r'[\(\)@\s]', '', t_name_lower)
                for l_acc in self.scanned_accounts:
                    l_id = str(l_acc.get("id", "")).strip()
                    l_uname = str(l_acc.get("username", "")).lower()
                    l_gname = str(l_acc.get("global_name", "")).lower()
                    l_dname = str(l_acc.get("display_name", "")).lower()
                    # 1. 精確 Discord ID 匹配
                    if t_did and l_id and t_did == l_id:
                        self.token = clean_discord_token(l_acc.get("token"))
                        break
                    # 2. @用戶名 或 暱稱匹配
                    if (l_uname and (f"@{l_uname}" in t_name_lower or l_uname in clean_t_name)) or \
                       (l_gname and (l_gname in t_name_lower or l_gname in clean_t_name)) or \
                       (clean_t_name and (clean_t_name == l_uname or clean_t_name in l_dname)):
                        self.token = clean_discord_token(l_acc.get("token"))
                        break

        self.setWindowTitle(f"🛡️ Discord 獨立無痕直達加群 - {self.display_name}")
        self.resize(620, 760)
        self.setWindowFlags(Qt.Window | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint | Qt.WindowTitleHint)

        # 100% 獨立無痕暫存沙盒，絕不干擾本機現有瀏覽器與其他帳號
        self.temp_dir = Path(tempfile.mkdtemp(prefix="discord_join_"))
        self.profile = QWebEngineProfile(f"Join_{int(time.time()*1000)}", self)
        self.profile.setPersistentStoragePath(str(self.temp_dir))
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        self.profile.setHttpUserAgent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )

        self._setup_injector_script()

        self.page = QWebEnginePage(self.profile, self)
        self.view = QWebEngineView(self)
        self.view.setPage(self.page)

        self._setup_ui()
        self.show()
        self._start_flow()

    def _setup_injector_script(self):
        self.profile.scripts().clear()
        if self.token:
            tok_json = json.dumps(self.token)
            script = QWebEngineScript()
            script.setName("DiscordTokenInjector")
            script.setInjectionPoint(QWebEngineScript.DocumentCreation)
            script.setWorldId(QWebEngineScript.MainWorld)
            script.setRunsOnSubFrames(True)
            script.setSourceCode(f"""
            (function() {{
                try {{
                    const tok = {tok_json};
                    window.localStorage.setItem('token', JSON.stringify(tok));
                }} catch(e) {{}}
            }})();
            """)
            self.profile.scripts().insert(script)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # 頂部狀態與操作卡
        header = QFrame(self)
        header.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FFF3E0, stop:1 #FFF8E1);
                border: 1.5px solid #FFB74D;
                border-radius: 10px;
                padding: 10px;
            }
        """)
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(8, 8, 8, 8)
        h_layout.setSpacing(6)

        title_text = f"⚡ 已為您自動帶入 [{self.display_name}] 的 Token，正在直達加群..." if self.token else f"🔑 請確認 [{self.display_name}] 的 Token 或登入"
        self.lbl_title = QLabel(title_text, header)
        self.lbl_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #E65100;")
        h_layout.addWidget(self.lbl_title)

        tip_text = "系統已自動填入您的身分 Token，正在安全載入認證並直達加群頁面..." if self.token else "本視窗為獨立無痕環境。您可點選下方已偵測的身分一鍵帶入，或在下方登入（系統將自動擷取 Token）。"
        self.lbl_tip = QLabel(tip_text, header)
        self.lbl_tip.setStyleSheet("font-size: 11px; color: #5D4037;")
        self.lbl_tip.setWordWrap(True)
        h_layout.addWidget(self.lbl_tip)

        # 快捷 Token 填入列
        tok_bar = QHBoxLayout()
        tok_bar.setSpacing(6)
        self.txt_token = QLineEdit(header)
        self.txt_token.setPlaceholderText("Discord Token (系統將自動抓取並填入)...")
        if self.token:
            self.txt_token.setText(self.token)
        self.txt_token.setStyleSheet("""
            QLineEdit {
                padding: 5px 8px;
                font-size: 11px;
                border: 1px solid #FFB74D;
                border-radius: 6px;
                background: #FFFFFF;
                color: #333;
            }
        """)
        self.txt_token.returnPressed.connect(self._on_btn_token_login_clicked)
        tok_bar.addWidget(self.txt_token, 1)

        self.btn_token_login = QPushButton("⚡ 一鍵 Token 登入", header)
        self.btn_token_login.setCursor(Qt.PointingHandCursor)
        self.btn_token_login.setStyleSheet("""
            QPushButton {
                padding: 5px 14px;
                font-size: 11px;
                font-weight: bold;
                background: #FF9800;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover { background: #F57C00; }
        """)
        self.btn_token_login.clicked.connect(self._on_btn_token_login_clicked)
        tok_bar.addWidget(self.btn_token_login)
        h_layout.addLayout(tok_bar)

        self.pbar = QProgressBar(header)
        self.pbar.setFixedHeight(5)
        self.pbar.setTextVisible(False)
        self.pbar.setRange(0, 100)
        self.pbar.setValue(20 if self.token else 10)
        self.pbar.setStyleSheet("""
            QProgressBar { background: rgba(0,0,0,0.08); border-radius: 2px; border: none; }
            QProgressBar::chunk { background: #FF9800; border-radius: 2px; }
        """)
        h_layout.addWidget(self.pbar)

        layout.addWidget(header)
        layout.addWidget(self.view, 1)

        # 底部狀態列
        bot = QHBoxLayout()
        bot.setContentsMargins(0, 0, 0, 0)
        
        self.lbl_bot_status = QLabel("狀態: 正在載入無痕環境...", self)
        self.lbl_bot_status.setStyleSheet("font-size: 11px; color: #888;")
        bot.addWidget(self.lbl_bot_status)

        bot.addStretch()

        self.btn_cancel = QPushButton("關閉視窗", self)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                padding: 5px 14px;
                background: #FFFFFF;
                border: 1px solid #CCC;
                border-radius: 6px;
                font-size: 11px;
                color: #555;
            }
            QPushButton:hover { background: #F5F5F5; color: #333; }
        """)
        self.btn_cancel.clicked.connect(self.reject)
        bot.addWidget(self.btn_cancel)
        layout.addLayout(bot)

    def _on_btn_token_login_clicked(self):
        raw = self.txt_token.text().strip()
        tok = clean_discord_token(raw)
        if not tok:
            self.lbl_tip.setText("⚠️ 請先在輸入框貼上有效的 Discord Token。")
            return

        self.token = tok
        if self.account_id:
            save_token_to_vault(self.account_id, tok)
        if self.display_name:
            save_token_to_vault(self.display_name, tok)

        self._setup_injector_script()
        self.lbl_title.setText(f"🔑 正在以此 Token 注入登入...")
        self.lbl_tip.setText("Token 已更新，正在注入會話並直達加群...")
        self.pbar.setValue(40)
        self.lbl_bot_status.setText("注入 Token 中...")

        tok_json = json.dumps(tok)
        js = f"""
        (function() {{
            try {{
                const tok = {tok_json};
                let iframe = document.createElement('iframe');
                document.body.appendChild(iframe);
                if (iframe.contentWindow && iframe.contentWindow.localStorage) {{
                    iframe.contentWindow.localStorage.setItem('token', JSON.stringify(tok));
                }}
                window.localStorage.setItem('token', JSON.stringify(tok));
            }} catch(e) {{}}
            setTimeout(function() {{
                if (window.location.href.indexOf('login') !== -1) {{
                    window.location.reload();
                }} else {{
                    window.location.href = 'https://discord.com/login';
                }}
            }}, 200);
        }})();
        """
        self.page.runJavaScript(js)

    def _start_flow(self):
        self.view.urlChanged.connect(self._on_url_changed)
        self.view.loadFinished.connect(self._on_load_finished)

        if self.token:
            self.lbl_title.setText(f"🔑 正在載入 Discord 身分認證頁面...")
            self.lbl_tip.setText("正在帶入此 Token 身分，建立已登入的獨立 Session...")
            self.pbar.setValue(30)
            self.lbl_bot_status.setText("連線中: discord.com/login")
            self.view.load(QUrl("https://discord.com/login"))
        else:
            self.lbl_title.setText(f"🔑 請在下方登入 [{self.display_name}] 或上方確認 Token")
            self.lbl_tip.setText("提示：您可點選上方已偵測的身分一鍵帶入，或在下方登入（系統將自動擷取 Token）。")
            self.pbar.setValue(20)
            self.lbl_bot_status.setText("等待登入中...")
            self.view.load(QUrl("https://discord.com/login"))

    def _on_load_finished(self, ok):
        if not ok:
            return
        curr_url = self.view.url().toString()

        # 當處於 login 頁且有 token 且尚未執行注入時，寫入 localStorage 並 reload 觸發 Discord Client 登入
        if "discord.com/login" in curr_url and self.token and not self.injected_token:
            self.injected_token = True
            self.pbar.setValue(50)
            self.lbl_title.setText(f"🔑 正在以 [{self.display_name}] 身分登入 Discord...")
            self.lbl_tip.setText("Token 憑證已帶入，正在初始化 Discord 使用者會話...")
            self.lbl_bot_status.setText("身分驗證中...")

            token_json = json.dumps(self.token)
            js = f"""
            (function() {{
                try {{
                    const tok = {token_json};
                    let iframe = document.createElement('iframe');
                    document.body.appendChild(iframe);
                    if (iframe.contentWindow && iframe.contentWindow.localStorage) {{
                        iframe.contentWindow.localStorage.setItem('token', JSON.stringify(tok));
                    }}
                    window.localStorage.setItem('token', JSON.stringify(tok));
                }} catch(e) {{}}
                setTimeout(function() {{
                    window.location.reload();
                }}, 400);
            }})();
            """
            self.page.runJavaScript(js)

        elif "invite/manifests" in curr_url or "discord.gg/manifests" in curr_url:
            self.pbar.setValue(90)
            self.lbl_title.setText(f"👉 請點擊畫面上的「接受邀請」加入伺服器")
            self.lbl_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #1976D2;")
            self.lbl_tip.setText("提示：已成功帶入身分！系統正為您自動直達邀請確認卡。若遇人機驗證請手動勾選完成。")
            self.lbl_bot_status.setText("等待加群確認...")

            # 注入智慧巡檢腳本：自動點擊「在瀏覽器中繼續」（突破圖二），以及自動點擊「接受邀請」
            js_helper = """
            (function() {
                var count = 0;
                var timer = setInterval(function() {
                    count++;
                    if (count > 60) { clearInterval(timer); return; }
                    var allElements = document.querySelectorAll('button, a, div[role="button"]');
                    
                    // 1. 先檢測並自動點擊「在瀏覽器中繼續」(突破圖二中介卡片)
                    for (var i = 0; i < allElements.length; i++) {
                        var el = allElements[i];
                        var txt = (el.innerText || el.textContent || '').trim();
                        if (txt.indexOf('在瀏覽器中繼續') !== -1 || 
                            txt.indexOf('Continue in browser') !== -1 || 
                            txt.indexOf('Continue in Browser') !== -1 || 
                            txt.indexOf('Continue to Discord') !== -1) {
                            el.click();
                            break;
                        }
                    }

                    // 2. 檢測並輔助點擊「接受邀請」
                    for (var j = 0; j < allElements.length; j++) {
                        var b = allElements[j];
                        var btxt = (b.innerText || b.textContent || '').trim();
                        if (btxt.indexOf('接受邀請') !== -1 || 
                            btxt.indexOf('Accept Invite') !== -1 || 
                            btxt.indexOf('Join Server') !== -1) {
                            b.click();
                            break;
                        }
                    }
                }, 400);
            })();
            """
            self.page.runJavaScript(js_helper)

    def _on_token_captured(self, val):
        if val:
            tok = clean_discord_token(str(val))
            if tok and len(tok) > 20:
                self.token = tok
                self.txt_token.setText(tok)
                if self.account_id:
                    save_token_to_vault(self.account_id, tok)
                if self.display_name:
                    save_token_to_vault(self.display_name, tok)
                # 驗證此 token 取得 user id 並自動同步至 accounts_registry
                try:
                    uinfo = verify_discord_token(tok)
                    if uinfo:
                        uid = str(uinfo.get("id", "")).strip()
                        if uid:
                            save_token_to_vault(uid, tok)
                            for a in self.mgr.get_accounts("ryuu") + self.mgr.get_accounts("lua_tools"):
                                if (self.account_id and a.get("id") == self.account_id) or \
                                   (self.display_name and (self.display_name in a.get("name", "") or a.get("name", "") in self.display_name)):
                                    a["discord_id"] = uid
                                    self.mgr.save_data()
                except Exception:
                    pass

    def _on_url_changed(self, url: QUrl):
        url_str = url.toString()

        # 階段 A: 偵測是否已成功登入 Discord (進入 channels/@me 或 channels)
        if ("channels/@me" in url_str or ("channels" in url_str and "invite" not in url_str and "login" not in url_str)):
            if not self.is_discord_logged_in:
                self.is_discord_logged_in = True
                self.pbar.setValue(75)
                self.lbl_title.setText(f"✅ 身分認證成功！正在直達 Ryuu 官方伺服器...")
                self.lbl_tip.setText("Discord 帳號已就緒，即將為您開啟伺服器邀請頁面...")
                self.lbl_bot_status.setText("前往邀請頁面...")

                # 注入 Token 深度嗅探腳本 (無論有無 token，都捕獲最新 session token 自動回填與保存)
                sniffer_js = """
                (function() {
                    try {
                        var t = window.localStorage.getItem('token');
                        if (t) {
                            try { return JSON.parse(t); } catch(e) { return t.replace(/\"/g, ''); }
                        }
                        var m = [];
                        if (window.webpackChunkdiscord_app) {
                            window.webpackChunkdiscord_app.push([['__token_sniffer__'], {}, function(e) {
                                for (var c in e.c) m.push(e.c[c]);
                            }]);
                            for (var i = 0; i < m.length; i++) {
                                var mod = m[i];
                                if (mod && mod.exports) {
                                    if (mod.exports.default && typeof mod.exports.default.getToken === 'function') {
                                        var tok = mod.exports.default.getToken();
                                        if (tok) return tok;
                                    }
                                    if (typeof mod.exports.getToken === 'function') {
                                        var tok = mod.exports.getToken();
                                        if (tok) return tok;
                                    }
                                }
                            }
                        }
                    } catch(e) {}
                    return null;
                })();
                """
                self.page.runJavaScript(sniffer_js, self._on_token_captured)

                if not self.navigated_to_invite:
                    self.navigated_to_invite = True
                    # 延遲 400ms 跳轉至邀請頁面，確保 Discord 認證 cookie/session 完全就緒
                    QTimer.singleShot(400, lambda: self.view.load(QUrl("https://discord.com/invite/manifests")))

        # 階段 B: 偵測是否已成功加入 Ryuu 伺服器
        if (f"channels/{RYUU_GUILD_ID}" in url_str or 
            ("channels/1326675724597465160" in url_str)):
            if not self.has_joined:
                self.has_joined = True
                self._handle_join_success()

    def _handle_join_success(self):
        self.lbl_title.setText("🎉 加群成功！正在自動為您啟用 Ryuu 50次/日 配額...")
        self.lbl_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #2E7D32;")
        self.lbl_tip.setText("太棒了！系統正在自動向 Ryuu 官方伺服器換取 Session 憑證，請稍候...")
        self.pbar.setValue(95)
        self.lbl_bot_status.setText("啟用 50 次配額中...")

        # 非同步延遲 800ms 發送請求給 Ryuu 換 Session
        QTimer.singleShot(800, self._exchange_ryuu_session)

    def _exchange_ryuu_session(self, retry_count=0):
        # 若當前 token 未就緒，嘗試再次從 Vault 取得
        if not self.token and self.account_id:
            self.token = get_token_from_vault(self.account_id)
        if not self.token and self.display_name:
            self.token = get_token_from_vault(self.display_name)

        res = login_ryuu_with_discord_token(self.token) if self.token else {"success": False, "message": "尚未取得有效 Token"}
        if res.get("success"):
            session_val = res.get("session")
            dl_left = res.get("downloads_left", 50)
            
            # 若有指定 account_id 則更新該帳號，若無則查找同身分或新註冊
            target = None
            accounts = self.mgr.get_accounts("ryuu")
            if self.account_id:
                for a in accounts:
                    if a.get("id") == self.account_id:
                        target = a
                        break
            if not target:
                for a in accounts:
                    if self.display_name and (self.display_name in a.get("name", "") or a.get("name", "") in self.display_name):
                        target = a
                        break

            if target:
                p_dir = Path(target.get("profile_dir", ""))
                acc_id = target.get("id")
            else:
                acc_id, p_dir = self.mgr.create_new_account_profile_dir("ryuu")
                target = self.mgr.register_account("ryuu", acc_id, p_dir, name=self.display_name)

            # 寫入 SQLite Cookies
            c_file = p_dir / "Cookies"
            p_dir.mkdir(parents=True, exist_ok=True)
            now_epoch = int((time.time() + 11644473600) * 1000000)
            conn = sqlite3.connect(c_file)
            cur = conn.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS cookies (
                    creation_utc INTEGER NOT NULL, host_key TEXT NOT NULL, top_frame_site_key TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL, value TEXT NOT NULL, encrypted_value BLOB NOT NULL DEFAULT '',
                    path TEXT NOT NULL DEFAULT '/', expires_utc INTEGER NOT NULL DEFAULT 0,
                    is_secure INTEGER NOT NULL DEFAULT 1, is_httponly INTEGER NOT NULL DEFAULT 1,
                    last_access_utc INTEGER NOT NULL DEFAULT 0, has_expires INTEGER NOT NULL DEFAULT 0,
                    is_persistent INTEGER NOT NULL DEFAULT 1, priority INTEGER NOT NULL DEFAULT 1,
                    samesite INTEGER NOT NULL DEFAULT -1, source_scheme INTEGER NOT NULL DEFAULT 2,
                    source_port INTEGER NOT NULL DEFAULT 443, is_same_party INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (host_key, top_frame_site_key, name, path, source_port)
                )
            ''')
            cur.execute('''
                INSERT OR REPLACE INTO cookies (creation_utc, host_key, name, value, path, is_secure, is_httponly, is_persistent)
                VALUES (?, 'generator.ryuu.lol', 'session', ?, '/', 1, 1, 1)
            ''', (now_epoch, session_val))
            conn.commit()
            conn.close()

            target["not_in_server"] = False
            target["is_expired"] = False
            self.mgr.save_data()
            self.mgr.update_realtime_quota("ryuu", dl_left, daily_limit=50, account_id=acc_id)
            if self.token:
                save_token_to_vault(acc_id, self.token)
                save_token_to_vault(self.display_name, self.token)

            self.lbl_title.setText(f"✅ 配額啟用成功！Ryuu 50次/日 已到手！")
            self.lbl_tip.setText("太棒了！已順利完成授權，視窗將於 2 秒後自動關閉...")
            self.pbar.setValue(100)
            self.lbl_bot_status.setText("加群完成！")
            QTimer.singleShot(1800, self.accept)
        else:
            if retry_count < 2:
                # Discord 伺服器身分同步可能有些微網路延遲，重試一次
                self.lbl_tip.setText("正在等待 Discord 官方同步加群紀錄，稍候再次檢測...")
                QTimer.singleShot(1500, lambda: self._exchange_ryuu_session(retry_count + 1))
            else:
                self.lbl_title.setText("⚠️ 換取 Ryuu 憑證稍有延遲")
                self.lbl_tip.setText(f"提示：{res.get('message', '請至軟體介面點擊「啟用」按鈕')}。您可以關閉此視窗。")
                self.btn_cancel.setText("完成並關閉")
                self.lbl_bot_status.setText("等待手動啟用")

    def closeEvent(self, event):
        # 清理暫存沙盒目錄
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass
        super().closeEvent(event)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", default="", help="Discord Token")
    parser.add_argument("--account-id", default="", help="Account ID in registry")
    parser.add_argument("--name", default="", help="Display name")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    win = DiscordJoinServerWindow(
        token=args.token,
        account_id=args.account_id,
        display_name=args.name
    )
    win.show()
    win.raise_()
    win.activateWindow()

    # 強制置頂並獲取焦點
    try:
        import ctypes
        hwnd = int(win.winId())
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_SHOWWINDOW = 0x0040
        ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        ctypes.windll.user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.BringWindowToTop(hwnd)
    except Exception:
        pass

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
