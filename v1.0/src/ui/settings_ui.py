import html
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QFileDialog, QStackedWidget, QWidget,
    QScrollArea, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor
from qfluentwidgets import (
    MessageBoxBase, SubtitleLabel, LineEdit, StrongBodyLabel, BodyLabel,
    CaptionLabel, PushButton, PrimaryPushButton, ListWidget, ScrollArea,
    CardWidget, SwitchButton, InfoBar, InfoBarPosition
)

class GoogleDrivePriorityRow(CardWidget):
    def __init__(self, index=1, name="", url="", on_move_up=None, on_move_down=None, on_delete=None, is_first=False, is_last=False, parent=None):
        super().__init__(parent)
        self.on_move_up = on_move_up
        self.on_move_down = on_move_down
        self.on_delete = on_delete
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        
        # Header: Priority Badge + Order Buttons
        header_h = QHBoxLayout()
        priority_label = f"網盤 {index}" + (" (最高優先級)" if index == 1 else "")
        self.lbl_badge = StrongBodyLabel(priority_label, self)
        if index == 1:
            self.lbl_badge.setStyleSheet("color: #00bcd4; font-weight: bold;")
        else:
            self.lbl_badge.setStyleSheet("font-weight: bold;")
            
        header_h.addWidget(self.lbl_badge)
        header_h.addStretch(1)
        
        self.btn_up = PushButton("🔼 上移", self)
        self.btn_up.setFixedWidth(75)
        self.btn_up.setEnabled(not is_first)
        self.btn_up.clicked.connect(lambda: self.on_move_up(self) if self.on_move_up else None)
        
        self.btn_down = PushButton("🔽 下移", self)
        self.btn_down.setFixedWidth(75)
        self.btn_down.setEnabled(not is_last)
        self.btn_down.clicked.connect(lambda: self.on_move_down(self) if self.on_move_down else None)
        
        self.btn_del = PushButton("🗑️ 刪除", self)
        self.btn_del.setFixedWidth(75)
        self.btn_del.clicked.connect(lambda: self.on_delete(self) if self.on_delete else None)
        
        header_h.addWidget(self.btn_up)
        header_h.addWidget(self.btn_down)
        header_h.addWidget(self.btn_del)
        layout.addLayout(header_h)
        
        # Inputs: Name & URL
        inputs_h = QHBoxLayout()
        inputs_h.setSpacing(8)
        
        self.name_input = LineEdit(self)
        self.name_input.setPlaceholderText("網盤名稱 (如: 官方補丁庫、自訂庫)")
        self.name_input.setText(name)
        self.name_input.setFixedWidth(160)
        
        self.url_input = LineEdit(self)
        self.url_input.setPlaceholderText("Google Drive 網址 (https://drive.google.com/drive/folders/...)")
        self.url_input.setText(url)
        
        inputs_h.addWidget(self.name_input)
        inputs_h.addWidget(self.url_input, 1)
        layout.addLayout(inputs_h)
        
    def set_priority(self, index, is_first, is_last):
        priority_label = f"網盤 {index}" + (" (最高優先級)" if index == 1 else "")
        self.lbl_badge.setText(priority_label)
        if index == 1:
            self.lbl_badge.setStyleSheet("color: #00bcd4; font-weight: bold;")
        else:
            self.lbl_badge.setStyleSheet("font-weight: bold;")
        self.btn_up.setEnabled(not is_first)
        self.btn_down.setEnabled(not is_last)
        
    def get_data(self):
        return {
            "name": self.name_input.text().strip(),
            "url": self.url_input.text().strip()
        }


class GDriveGuideCard(CardWidget):
    """ Compact Guide Card providing concise instructions on Google Drive setup and patch placement """
    def __init__(self, parent=None, default_expanded=True):
        super().__init__(parent)
        self.setStyleSheet("""
            GDriveGuideCard {
                background-color: #232323;
                border: 1px solid rgba(0, 188, 212, 0.3);
                border-radius: 8px;
            }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 10, 14, 10)
        main_layout.setSpacing(8)
        
        # Header with title and toggle button
        header_h = QHBoxLayout()
        header_h.setSpacing(8)
        
        self.lbl_title = StrongBodyLabel("網盤新增與補丁放置說明", self)
        self.lbl_title.setStyleSheet("color: #00bcd4; font-weight: bold; font-size: 13px;")
        header_h.addWidget(self.lbl_title)
        
        header_h.addStretch(1)
        
        self.toggle_btn = PushButton("收合說明" if default_expanded else "查看說明", self)
        self.toggle_btn.setFixedWidth(80)
        self.toggle_btn.clicked.connect(self._toggle_expanded)
        header_h.addWidget(self.toggle_btn)
        
        main_layout.addLayout(header_h)
        
        # Guide Content Container
        self.content_widget = QWidget(self)
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(2, 2, 2, 2)
        content_layout.setSpacing(6)
        
        guide_lbl = QLabel(self.content_widget)
        guide_lbl.setWordWrap(True)
        guide_lbl.setTextFormat(Qt.RichText)
        guide_lbl.setText("""
<div style="line-height: 1.6; color: #d0d0d0; font-size: 12px;">
  <div style="margin-bottom: 6px;">
    <b style="color: #00bcd4;">1. 網盤連結：</b>在 Google 雲端硬碟建立資料夾，設定共用權限為<span style="color: #a5d6a7; font-weight: bold;">「知道連結的使用者皆可查看」</span>，複製資料夾網址並貼入下方網址欄。
  </div>
  <div>
    <b style="color: #00bcd4;">2. 放置補丁：</b>直接將下載的補丁壓縮檔（.rar / .zip）丟進該雲端資料夾即可，軟體會自動分析遊戲名稱並進行匹配。
  </div>
</div>
        """)
        content_layout.addWidget(guide_lbl)
        main_layout.addWidget(self.content_widget)
        
        self.content_widget.setVisible(default_expanded)
        
    def _toggle_expanded(self):
        is_vis = self.content_widget.isVisible()
        self.content_widget.setVisible(not is_vis)
        self.toggle_btn.setText("收合說明" if not is_vis else "查看說明")


class SettingsChangesDialog(MessageBoxBase):
    """ Dialog to review modified settings with diff cards (used for both Save and Cancel confirmation) """
    def __init__(self, parent=None, changes=None, is_discard_mode=False):
        super().__init__(parent)
        self.widget.setFixedSize(540, 440)
        self.changes = changes or []
        
        if is_discard_mode:
            self.titleLabel = SubtitleLabel("放棄未儲存的修改？")
            header_text = "以下修改尚未儲存，確定要放棄並離開嗎？"
            self.yesButton.setText("放棄")
            self.yesButton.setStyleSheet("""
                PrimaryPushButton, PushButton {
                    background-color: #cf3434;
                    border: 1px solid #cf3434;
                    border-radius: 5px;
                    color: #ffffff;
                    font: 14px 'Segoe UI', 'Microsoft YaHei', 'PingFang SC';
                    padding: 5px 9px 6px 9px;
                    outline: none;
                }
                PrimaryPushButton:hover, PushButton:hover {
                    background-color: #e53935;
                    border: 1px solid #e53935;
                }
                PrimaryPushButton:pressed, PushButton:pressed {
                    background-color: #b71c1c;
                    border: 1px solid #b71c1c;
                }
            """)
            self.cancelButton.setText("取消")
        else:
            self.titleLabel = SubtitleLabel("確認儲存設定")
            header_text = "您進行了以下修改："
            self.yesButton.setText("確定")
            self.cancelButton.setText("取消")
            
        # Ensure identical height and geometry alignment for both buttons
        self.yesButton.setFixedHeight(35)
        self.cancelButton.setFixedHeight(35)
            
        self.viewLayout.addWidget(self.titleLabel)
        
        header_lbl = StrongBodyLabel(header_text)
        self.viewLayout.addWidget(header_lbl)
        self.viewLayout.addSpacing(6)
        
        # Scroll Area for changes
        scroll = ScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{background: transparent; border: none;}")
        scroll.viewport().setStyleSheet("background: transparent;")
        
        content_w = QWidget()
        content_l = QVBoxLayout(content_w)
        content_l.setContentsMargins(4, 4, 4, 4)
        content_l.setSpacing(10)
        
        for title, old_val, new_val in self.changes:
            item_card = CardWidget()
            item_card.setStyleSheet("""
                CardWidget {
                    background-color: #292929;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 8px;
                }
            """)
            card_l = QVBoxLayout(item_card)
            card_l.setContentsMargins(14, 12, 14, 12)
            card_l.setSpacing(6)
            
            t_lbl = QLabel()
            t_lbl.setTextFormat(Qt.RichText)
            parts = [p.strip() for p in title.split(">")]
            formatted_title = ' <span style="color: #00bcd4; font-weight: bold;">&gt;</span> '.join(
                [f'<span style="color: #ffffff; font-weight: bold; font-size: 13px;">{p}</span>' for p in parts]
            )
            t_lbl.setText(formatted_title)
            card_l.addWidget(t_lbl)
            
            old_str = html.escape(str(old_val) if old_val else "(無)").replace("\n", "<br>")
            new_str = html.escape(str(new_val) if new_val else "(無)").replace("\n", "<br>")
            
            diff_lbl = QLabel()
            diff_lbl.setWordWrap(True)
            diff_lbl.setTextFormat(Qt.RichText)
            diff_lbl.setText(
                f'<span style="color: #ffb74d; font-family: Consolas, monospace;">"{old_str}"</span> &gt;<br>'
                f'<span style="color: #ffffff; font-family: Consolas, monospace; font-weight: bold;">"{new_str}"</span>'
            )
            card_l.addWidget(diff_lbl)
            content_l.addWidget(item_card)
            
        content_l.addStretch(1)
        scroll.setWidget(content_w)
        self.viewLayout.addWidget(scroll, 1)


class SettingsReviewDialog(SettingsChangesDialog):
    def __init__(self, parent=None, changes=None):
        super().__init__(parent, changes=changes, is_discard_mode=False)


class CancelConfirmDialog(SettingsChangesDialog):
    def __init__(self, parent=None, changes=None):
        super().__init__(parent, changes=changes, is_discard_mode=True)


class SettingsDialog(MessageBoxBase):
    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.config = config or {}
        
        # Remove default bottom button group so viewLayout expands to bottom
        self.buttonGroup.hide()
        self.vBoxLayout.removeWidget(self.buttonGroup)
        
        # Set fixed geometry on widget
        self.widget.setFixedSize(780, 500)
        self.viewLayout.setContentsMargins(24, 24, 24, 24)
        
        # Main split layout
        split_layout = QHBoxLayout()
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(16)
        self.viewLayout.addLayout(split_layout)
        
        # Left column: Title + Navigation + Action Buttons at bottom
        left_column = QVBoxLayout()
        left_column.setContentsMargins(0, 0, 0, 0)
        left_column.setSpacing(10)
        
        self.titleLabel = SubtitleLabel('進階設定')
        left_column.addWidget(self.titleLabel)
        
        self.nav_list = ListWidget()
        self.nav_list.setFixedWidth(160)
        self.nav_list.addItem("Google Drive 網盤")
        self.nav_list.addItem("背景守護設定")
        self.nav_list.addItem("網域設定")
        self.nav_list.addItem("資料儲存設定")
        left_column.addWidget(self.nav_list)
        
        left_column.addStretch(1)
        
        # Action buttons in left column
        self.btn_save = PrimaryPushButton("儲存")
        self.btn_save.setFixedHeight(34)
        self.btn_save.clicked.connect(self._on_save_clicked)
        
        self.btn_cancel = PushButton("取消")
        self.btn_cancel.setFixedHeight(34)
        self.btn_cancel.clicked.connect(self.reject)
        
        left_column.addWidget(self.btn_save)
        left_column.addWidget(self.btn_cancel)
        
        split_layout.addLayout(left_column)
        
        # Right side: Styled Content Container Card
        self.content_card = CardWidget()
        self.content_card.setStyleSheet("""
            CardWidget {
                background-color: #292929;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
        """)
        card_layout = QVBoxLayout(self.content_card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        
        # Right side: Stacked Widget inside ScrollArea
        self.stacked_widget = QStackedWidget()
        
        scroll_area = ScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.stacked_widget)
        scroll_area.setStyleSheet("QScrollArea{background: transparent; border: none;}")
        scroll_area.viewport().setStyleSheet("background: transparent;")
        
        card_layout.addWidget(scroll_area)
        split_layout.addWidget(self.content_card, 1)
        
        # Create pages (0=Google Drive 網盤, 1=背景守護設定, 2=網域設定, 3=資料儲存設定)
        self._setup_gdrive_page()
        self._setup_daemon_page()
        self._setup_domain_page()
        self._setup_storage_page()
        
        # Connect navigation
        self.nav_list.currentRowChanged.connect(self.stacked_widget.setCurrentIndex)
        self.nav_list.setCurrentRow(0)
        
        # Pre-activate layout
        self.widget.layout().activate()

    def showEvent(self, e):
        """ Synchronous unified fade-in animation without graphics effect conflict """
        self.widget.setGraphicsEffect(None)
        
        opacityEffect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(opacityEffect)
        
        opacityAni = QPropertyAnimation(opacityEffect, b'opacity', self)
        opacityAni.setStartValue(0)
        opacityAni.setEndValue(1)
        opacityAni.setDuration(180)
        opacityAni.setEasingCurve(QEasingCurve.OutCubic)
        
        def on_finished():
            self.setGraphicsEffect(None)
            self.setShadowEffect(60, (0, 10), QColor(0, 0, 0, 80))
            
        opacityAni.finished.connect(on_finished)
        opacityAni.start()
        
        super(MessageBoxBase, self).showEvent(e)

    def done(self, code):
        """ Synchronous fade-out animation """
        self.widget.setGraphicsEffect(None)
        opacityEffect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(opacityEffect)
        
        opacityAni = QPropertyAnimation(opacityEffect, b'opacity', self)
        opacityAni.setStartValue(1)
        opacityAni.setEndValue(0)
        opacityAni.setDuration(120)
        opacityAni.finished.connect(lambda: self._onDone(code))
        opacityAni.start()

    def reject(self):
        """ Check for unsaved changes before closing on Cancel / ESC """
        changes = self._get_changes()
        if changes:
            confirm_dlg = CancelConfirmDialog(self, changes=changes)
            if not confirm_dlg.exec():
                return
        super().reject()

    def _get_changes(self):
        """ Compare current form with initial config and return list of (breadcrumb_title, old, new) """
        changes = []
        
        # 1. 網域設定
        old_of = self.config.get("onlinefix_domain", "https://online-fix.me")
        new_of = self.onlinefix_input.text().strip()
        if old_of != new_of:
            changes.append(("網域設定 > Online-Fix 官方網域", old_of, new_of))
            
        old_zg = self.config.get("zeigames_domain", "https://zeigames.com/")
        new_zg = self.zeigames_input.text().strip()
        if old_zg != new_zg:
            changes.append(("網域設定 > ZeiGames 官方網域", old_zg, new_zg))
            
        old_lt = self.config.get("luatools_domain", "https://lua.tools")
        new_lt = self.luatools_input.text().strip()
        if old_lt != new_lt:
            changes.append(("網域設定 > Lua.tools 官方網域", old_lt, new_lt))
            
        old_as = self.config.get("assiw_domain", "https://steam.assiw.xyz")
        new_as = getattr(self, "assiw_input", None).text().strip() if getattr(self, "assiw_input", None) else old_as
        if old_as != new_as:
            changes.append(("網域設定 > Steam Assiw 網域 (下級來源)", old_as, new_as))
            
        # 2. Google Drive 網盤設定

        old_drives = self.config.get("cloud_drives", [])
        if not old_drives:
            legacy_url = self.config.get("gdrive_url", "https://drive.google.com/drive/folders/13TSWK9I5JWj3MDSGeEubSZm37-IwUoGu?usp=sharing")
            old_drives = [{"priority": 1, "name": "官方補丁庫", "url": legacy_url}]
        new_drives = self.get_cloud_drives()
        
        # Check if it's purely a reordering of existing drives
        old_tuples = [(d.get("name", "").strip(), d.get("url", "").strip()) for d in old_drives]
        new_tuples = [(d.get("name", "").strip(), d.get("url", "").strip()) for d in new_drives]
        
        if len(old_tuples) == len(new_tuples) and sorted(old_tuples) == sorted(new_tuples) and old_tuples != new_tuples:
            old_order_str = " > ".join([f"[{i+1}] {name or '未命名'}" for i, (name, _) in enumerate(old_tuples)])
            new_order_str = " > ".join([f"[{i+1}] {name or '未命名'}" for i, (name, _) in enumerate(new_tuples)])
            changes.append(("Google Drive 網盤 > 優先級順序", old_order_str, new_order_str))
        else:
            max_len = max(len(old_drives), len(new_drives))
            for i in range(max_len):
                drive_num = i + 1
                if i < len(old_drives) and i < len(new_drives):
                    old_d = old_drives[i]
                    new_d = new_drives[i]
                    old_name = old_d.get("name", f"網盤 {drive_num}").strip()
                    new_name = new_d.get("name", f"網盤 {drive_num}").strip()
                    old_url = old_d.get("url", "").strip()
                    new_url = new_d.get("url", "").strip()

                    # 1) 網盤名稱變更
                    if old_name != new_name:
                        changes.append((f"Google Drive 網盤 > 網盤 {drive_num} > 網盤名稱", old_name, new_name))

                    # 2) 網盤網址變更
                    if old_url != new_url:
                        drive_tag = f"網盤 {drive_num} ({new_name})" if new_name else f"網盤 {drive_num}"
                        changes.append((f"Google Drive 網盤 > {drive_tag} > 網盤網址", old_url, new_url))

                elif i < len(old_drives):
                    # 刪除的網盤
                    old_d = old_drives[i]
                    old_name = old_d.get("name", f"網盤 {drive_num}").strip()
                    old_url = old_d.get("url", "").strip()
                    changes.append((f"Google Drive 網盤 > 網盤 {drive_num} (刪除網盤)", f"{old_name} ({old_url})", "(已移除)"))

                else:
                    # 新增的網盤
                    new_d = new_drives[i]
                    new_name = new_d.get("name", f"網盤 {drive_num}").strip()
                    new_url = new_d.get("url", "").strip()
                    changes.append((f"Google Drive 網盤 > 網盤 {drive_num} (新增網盤)", "(無)", f"{new_name} ({new_url})"))
            
        # 3. 背景守護設定
        old_ap = self.config.get("daemon_auto_patch", True)
        new_ap = self.switch_autopatch.isChecked()
        if old_ap != new_ap:
            changes.append(("背景守護設定 > 自動下載並套用補丁", "開啟" if old_ap else "關閉", "開啟" if new_ap else "關閉"))
            
        old_notif = self.config.get("daemon_notify", True)
        new_notif = self.switch_notify.isChecked()
        if old_notif != new_notif:
            changes.append(("背景守護設定 > 桌面氣泡通知", "開啟" if old_notif else "關閉", "開啟" if new_notif else "關閉"))

        # 4. 資料儲存設定
        old_lua = self.config.get("lua_dir", "")
        new_lua = self.lua_dir_input.text().strip()
        if old_lua != new_lua:
            changes.append(("資料儲存設定 > 本地 Lua 資料夾路徑", old_lua, new_lua))
            
        old_creds = self.config.get("credentials_dir", "")
        new_creds = self.credentials_input.text().strip()
        if old_creds != new_creds:
            changes.append(("資料儲存設定 > 憑證與帳號儲存路徑", old_creds, new_creds))
            
        old_cache = self.config.get("cache_dir", "")
        new_cache = self.cache_input.text().strip()
        if old_cache != new_cache:
            changes.append(("資料儲存設定 > Online-Fix 暫存與快取路徑", old_cache, new_cache))
            
        return changes

    def _on_save_clicked(self):
        changes = self._get_changes()
        if not changes:
            self.accept()
            return
            
        review_dlg = SettingsReviewDialog(self, changes=changes)
        if review_dlg.exec():
            self.accept()

    def _setup_daemon_page(self):
        from utils import autostart
        from utils.toast import send_notification
        
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignTop)
        
        title = StrongBodyLabel("背景守護設定 (超低負載模式)", page)
        layout.addWidget(title)
        desc = CaptionLabel("啟用微型背景守護後，程式將以極低負載（RAM < 10MB，CPU 0%）在系統常駐；當 Steam 下載或更新遊戲時，自動於背景完成補丁與 Manifest 比對套用。", page)
        desc.setWordWrap(True)
        layout.addWidget(desc)
        layout.addSpacing(2)
        
        # Notice Card
        notice_card = CardWidget(page)
        notice_card.setStyleSheet("""
            CardWidget {
                background-color: #2b1d1d;
                border: 1px solid #d32f2f;
                border-radius: 8px;
            }
        """)
        n_layout = QVBoxLayout(notice_card)
        n_layout.setContentsMargins(16, 12, 16, 12)
        n_title = StrongBodyLabel("⚠️ 功能已暫停：因 Valve 伺服端更新，守護與線上 Manifest 更新已停用", notice_card)
        n_title.setStyleSheet("color: #ff8a80; font-weight: bold;")
        n_desc = CaptionLabel("Valve 伺服端已封鎖未授權遊戲在線獲取 Manifest 清單。為避免修改 Lua 導致 Steam 下載報錯（無網路連線），背景定時比對與自動更新已作廢暫停。", notice_card)
        n_desc.setStyleSheet("color: #e0e0e0;")
        n_desc.setWordWrap(True)
        n_layout.addWidget(n_title)
        n_layout.addWidget(n_desc)
        layout.addWidget(notice_card)

        # 1. Status & Control Card
        status_card = CardWidget(page)
        status_card.setStyleSheet("""
            CardWidget {
                background-color: #232323;
                border: 1px solid rgba(0, 188, 212, 0.25);
                border-radius: 8px;
            }
        """)
        s_layout = QHBoxLayout(status_card)
        s_layout.setContentsMargins(16, 14, 16, 14)
        s_layout.setSpacing(12)
        
        self.daemon_status_lbl = StrongBodyLabel(status_card)
        s_layout.addWidget(self.daemon_status_lbl, 1)
        
        self.btn_daemon_toggle = PrimaryPushButton("啟動守護", status_card)
        self.btn_daemon_toggle.setFixedWidth(110)
        self.btn_daemon_toggle.clicked.connect(self._toggle_daemon_process)
        s_layout.addWidget(self.btn_daemon_toggle)
        
        self._update_daemon_status_ui()
        self._sync_daemon_button_state()
        layout.addWidget(status_card)
        
        # 2. Automation Options Card
        opts_card = CardWidget(page)
        opts_card.setStyleSheet("""
            CardWidget {
                background-color: #232323;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
        """)
        opts_layout = QVBoxLayout(opts_card)
        opts_layout.setContentsMargins(16, 14, 16, 14)
        opts_layout.setSpacing(12)
        
        # Switch 1: Autostart with Windows
        row1 = QHBoxLayout()
        r1_text = QVBoxLayout()
        r1_title = StrongBodyLabel("開機自動於背景守護", opts_card)
        r1_desc = CaptionLabel("開機自動登錄微型守護進程，無需打開主介面即可自動維持遊戲更新狀態。", opts_card)
        r1_desc.setWordWrap(True)
        r1_text.addWidget(r1_title)
        r1_text.addWidget(r1_desc)
        row1.addLayout(r1_text, 1)
        
        self.switch_autostart = SwitchButton(opts_card)
        self.switch_autostart.setChecked(autostart.is_autostart_enabled())
        self.switch_autostart.checkedChanged.connect(self._on_autostart_changed)
        row1.addWidget(self.switch_autostart)
        opts_layout.addLayout(row1)
        
        opts_layout.addSpacing(4)
        
        # Switch 2: Auto-patch on game update
        row2 = QHBoxLayout()
        r2_text = QVBoxLayout()
        r2_title = StrongBodyLabel("偵測更新時自動下載並套用補丁", opts_card)
        r2_desc = CaptionLabel("當 Steam 完成遊戲下載或版本更新時，自動從網盤檢索對應補丁並無感安裝。", opts_card)
        r2_desc.setWordWrap(True)
        r2_text.addWidget(r2_title)
        r2_text.addWidget(r2_desc)
        row2.addLayout(r2_text, 1)
        
        self.switch_autopatch = SwitchButton(opts_card)
        self.switch_autopatch.setChecked(self.config.get("daemon_auto_patch", True))
        row2.addWidget(self.switch_autopatch)
        opts_layout.addLayout(row2)
        
        opts_layout.addSpacing(4)
        
        # Switch 3: Windows Toast notification
        row3 = QHBoxLayout()
        r3_text = QVBoxLayout()
        r3_title = StrongBodyLabel("更新完成後發送 Windows 桌面通知", opts_card)
        r3_desc = CaptionLabel("背景自動完成遊戲補丁更新時，在右下角發送系統桌面氣泡通知。", opts_card)
        r3_desc.setWordWrap(True)
        r3_text.addWidget(r3_title)
        r3_text.addWidget(r3_desc)
        row3.addLayout(r3_text, 1)
        
        self.switch_notify = SwitchButton(opts_card)
        self.switch_notify.setChecked(self.config.get("daemon_notify", True))
        row3.addWidget(self.switch_notify)
        opts_layout.addLayout(row3)
        
        opts_layout.addSpacing(6)
        
        # Test Notification Button
        btn_test_toast = PushButton("發送測試通知", opts_card)
        btn_test_toast.setFixedWidth(120)
        btn_test_toast.clicked.connect(self._send_test_toast)
        opts_layout.addWidget(btn_test_toast)
        
        layout.addWidget(opts_card)
        self.stacked_widget.addWidget(page)

    def _send_test_toast(self):
        from utils.toast import send_notification
        send_notification("SteamManifest 測試通知", "Windows 桌面通知功能運作正常！")
        InfoBar.success(
            title="測試通知已發送",
            content="已發送桌面通知！若無彈出請確認 Windows 通知與專注輔助設定。",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3500,
            parent=self
        )

    def _update_daemon_status_ui(self):
        from utils import autostart
        is_running = autostart.is_daemon_running()
        pid = autostart.get_daemon_pid()
        if is_running:
            self.daemon_status_lbl.setText(f"🟢 守護進程運行中 (PID: {pid})")
            self.daemon_status_lbl.setStyleSheet("color: #a5d6a7; font-weight: bold; font-size: 13px;")
        else:
            self.daemon_status_lbl.setText("⚪ 守護進程已暫停使用 (安全狀態)")
            self.daemon_status_lbl.setStyleSheet("color: #9e9e9e; font-weight: bold; font-size: 13px;")

    def _sync_daemon_button_state(self):
        from utils import autostart
        is_running = autostart.is_daemon_running()
        if is_running:
            self.btn_daemon_toggle.setText("停止守護")
            self.btn_daemon_toggle.setStyleSheet("""
                PrimaryPushButton, PushButton {
                    background-color: #cf3434;
                    border: 1px solid #cf3434;
                    border-radius: 5px;
                    color: #ffffff;
                }
                PrimaryPushButton:hover, PushButton:hover {
                    background-color: #e53935;
                }
            """)
        else:
            self.btn_daemon_toggle.setText("已暫停")
            self.btn_daemon_toggle.setEnabled(False)
            self.btn_daemon_toggle.setStyleSheet("")

    def _toggle_daemon_process(self):
        from utils import autostart
        if autostart.is_daemon_running():
            autostart.stop_daemon()
            self._update_daemon_status_ui()
            self._sync_daemon_button_state()
        else:
            InfoBar.warning(
                title="守護功能已暫停",
                content="因 Valve 伺服端更新，線上 Manifest 清單提取已失效，背景守護目前暫停使用。",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=4000,
                parent=self
            )

    def _on_autostart_changed(self, checked):
        from utils import autostart
        autostart.set_autostart(checked)

    def _setup_domain_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignTop)
        
        title = StrongBodyLabel("網域設定", page)
        layout.addWidget(title)
        desc = CaptionLabel("系統預設網域配置（僅供檢視，禁止修改）。", page)
        desc.setWordWrap(True)
        layout.addWidget(desc)
        layout.addSpacing(6)
        
        # 1. Online-Fix Domain
        self.onlinefix_input = LineEdit(page)
        self.onlinefix_input.setPlaceholderText("例如: https://online-fix.me")
        self.onlinefix_input.setText(self.config.get("onlinefix_domain", "https://online-fix.me"))
        self.onlinefix_input.setReadOnly(True)
        layout.addWidget(BodyLabel("Online-Fix 官方網域:", page))
        layout.addWidget(self.onlinefix_input)
        
        layout.addSpacing(6)
        
        # 2. ZeiGames Domain
        self.zeigames_input = LineEdit(page)
        self.zeigames_input.setPlaceholderText("例如: https://zeigames.com/")
        self.zeigames_input.setText(self.config.get("zeigames_domain", "https://zeigames.com/"))
        self.zeigames_input.setReadOnly(True)
        layout.addWidget(BodyLabel("ZeiGames 官方網域:", page))
        layout.addWidget(self.zeigames_input)
        
        layout.addSpacing(6)
        
        # 3. Ryuu Domain (第一手 Manifest 庫存)
        self.ryuu_input = LineEdit(page)
        self.ryuu_input.setPlaceholderText("例如: https://generator.ryuu.lol")
        self.ryuu_input.setText("https://generator.ryuu.lol")
        self.ryuu_input.setReadOnly(True)
        layout.addWidget(BodyLabel("Ryuu's Manifests 官方網域 (第一手清單庫存源):", page))
        layout.addWidget(self.ryuu_input)
        
        layout.addSpacing(6)

        # 4. Lua.tools Domain (聚合平台)
        self.luatools_input = LineEdit(page)
        self.luatools_input.setPlaceholderText("例如: https://lua.tools")
        self.luatools_input.setText(self.config.get("luatools_domain", "https://lua.tools"))
        self.luatools_input.setReadOnly(True)
        layout.addWidget(BodyLabel("Lua.tools 官方網域 (聚合備援平台):", page))
        layout.addWidget(self.luatools_input)
        
        layout.addSpacing(6)
        
        # 4. Assiw Domain (Lua.tools 下級來源)
        self.assiw_input = LineEdit(page)
        self.assiw_input.setPlaceholderText("例如: https://steam.assiw.xyz")
        self.assiw_input.setText(self.config.get("assiw_domain", "https://steam.assiw.xyz"))
        self.assiw_input.setReadOnly(True)
        layout.addWidget(BodyLabel("Steam Assiw 網域 (Lua.tools 下級備用來源):", page))
        layout.addWidget(self.assiw_input)
        
        self.stacked_widget.addWidget(page)


    def _setup_gdrive_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignTop)
        
        title = StrongBodyLabel("Google Drive 網盤優先級設定", page)
        layout.addWidget(title)
        desc = CaptionLabel("由上至下依序檢索補丁。若不同網盤包含相同遊戲檔案，將優先採用排序在上方（優先級較高）的網盤檔案。", page)
        desc.setWordWrap(True)
        layout.addWidget(desc)
        layout.addSpacing(2)
        
        # Guide Card
        self.guide_card = GDriveGuideCard(page, default_expanded=True)
        layout.addWidget(self.guide_card)
        layout.addSpacing(4)
        
        # Header with Add Button
        header_h = QHBoxLayout()
        header_h.addWidget(BodyLabel("網盤清單 (可透過上移/下移調整優先級):", page), 1)
        
        self.add_drive_btn = PrimaryPushButton("➕ 新增 Google Drive 網盤", page)
        self.add_drive_btn.clicked.connect(lambda: self._add_drive_row())
        header_h.addWidget(self.add_drive_btn)
        layout.addLayout(header_h)
        
        # Container for drive rows
        self.drives_container = QWidget(page)
        self.drives_layout = QVBoxLayout(self.drives_container)
        self.drives_layout.setContentsMargins(0, 4, 0, 4)
        self.drives_layout.setSpacing(10)
        
        layout.addWidget(self.drives_container)
        
        # Load existing drives
        self.drive_rows = []
        saved_drives = self.config.get("cloud_drives", [])
        
        # If no saved list, check legacy gdrive_url or default
        if not saved_drives:
            legacy_url = self.config.get("gdrive_url", "https://drive.google.com/drive/folders/13TSWK9I5JWj3MDSGeEubSZm37-IwUoGu?usp=sharing")
            saved_drives = [{"name": "官方補丁庫", "url": legacy_url}]
            
        for d in saved_drives:
            if isinstance(d, dict):
                self._add_drive_row(d.get("name", ""), d.get("url", ""))
                
        self._update_drive_priorities()
        self.stacked_widget.addWidget(page)

    def _add_drive_row(self, name="", url=""):
        row = GoogleDrivePriorityRow(
            index=len(self.drive_rows) + 1,
            name=name if name else f"網盤 {len(self.drive_rows) + 1}",
            url=url,
            on_move_up=self._move_drive_up,
            on_move_down=self._move_drive_down,
            on_delete=self._remove_drive_row,
            parent=self.drives_container
        )
        self.drive_rows.append(row)
        self.drives_layout.addWidget(row)
        self._update_drive_priorities()

    def _move_drive_up(self, row):
        idx = self.drive_rows.index(row)
        if idx > 0:
            self.drive_rows[idx], self.drive_rows[idx - 1] = self.drive_rows[idx - 1], self.drive_rows[idx]
            self._rebuild_drives_layout()

    def _move_drive_down(self, row):
        idx = self.drive_rows.index(row)
        if idx < len(self.drive_rows) - 1:
            self.drive_rows[idx], self.drive_rows[idx + 1] = self.drive_rows[idx + 1], self.drive_rows[idx]
            self._rebuild_drives_layout()

    def _remove_drive_row(self, row):
        if row in self.drive_rows:
            self.drive_rows.remove(row)
            self.drives_layout.removeWidget(row)
            row.deleteLater()
            self._update_drive_priorities()

    def _rebuild_drives_layout(self):
        for row in self.drive_rows:
            self.drives_layout.removeWidget(row)
        for row in self.drive_rows:
            self.drives_layout.addWidget(row)
        self._update_drive_priorities()

    def _update_drive_priorities(self):
        total = len(self.drive_rows)
        for idx, row in enumerate(self.drive_rows):
            row.set_priority(index=idx + 1, is_first=(idx == 0), is_last=(idx == total - 1))

    def get_cloud_drives(self):
        drives = []
        for idx, row in enumerate(self.drive_rows):
            data = row.get_data()
            if data["url"] or data["name"]:
                drives.append({
                    "priority": idx + 1,
                    "name": data["name"] if data["name"] else f"網盤 {idx + 1}",
                    "url": data["url"]
                })
        return drives

    def _setup_storage_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignTop)
        
        title = StrongBodyLabel("資料儲存設定", page)
        layout.addWidget(title)
        desc = CaptionLabel("系統預設資料存放路徑（僅供檢視，禁止修改）。", page)
        desc.setWordWrap(True)
        layout.addWidget(desc)
        layout.addSpacing(6)
        
        # 1. Lua path
        self.lua_dir_input = LineEdit(page)
        self.lua_dir_input.setText(self.config.get("lua_dir", ""))
        self.lua_dir_input.setReadOnly(True)
        layout.addWidget(BodyLabel("本地 Lua 資料夾路徑:", page))
        layout.addWidget(self.lua_dir_input)
        
        layout.addSpacing(6)
        
        # 2. Credentials path
        self.credentials_input = LineEdit(page)
        self.credentials_input.setText(self.config.get("credentials_dir", ""))
        self.credentials_input.setReadOnly(True)
        layout.addWidget(BodyLabel("憑證與帳號儲存路徑:", page))
        layout.addWidget(self.credentials_input)
        
        layout.addSpacing(6)
        
        # 3. Cache path
        self.cache_input = LineEdit(page)
        self.cache_input.setText(self.config.get("cache_dir", ""))
        self.cache_input.setReadOnly(True)
        layout.addWidget(BodyLabel("Online-Fix 暫存與快取路徑:", page))
        layout.addWidget(self.cache_input)
        
        self.stacked_widget.addWidget(page)
