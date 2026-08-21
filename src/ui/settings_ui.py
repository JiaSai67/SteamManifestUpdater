from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QFileDialog, QStackedWidget, QWidget
from PySide6.QtCore import Qt
from qfluentwidgets import MessageBoxBase, SubtitleLabel, LineEdit, StrongBodyLabel, PushButton, ListWidget, ScrollArea

class SettingsDialog(MessageBoxBase):
    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel('進階設定', self)
        
        self.config = config or {}
        
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(10)
        
        # Main split layout
        split_layout = QHBoxLayout()
        self.viewLayout.addLayout(split_layout)
        
        # Left side: Navigation
        self.nav_list = ListWidget(self)
        self.nav_list.setFixedWidth(160)
        self.nav_list.addItem("網域設定")
        self.nav_list.addItem("資料儲存設定")
        split_layout.addWidget(self.nav_list)
        
        # Right side: Stacked Widget
        self.stacked_widget = QStackedWidget(self)
        
        # Use ScrollArea to prevent cutoff
        scroll_area = ScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.stacked_widget)
        scroll_area.setStyleSheet("QScrollArea{background: transparent; border: none;}")
        
        split_layout.addWidget(scroll_area, 1)
        
        # Create pages
        self._setup_domain_page()
        self._setup_storage_page()
        
        # Connect navigation
        self.nav_list.currentRowChanged.connect(self.stacked_widget.setCurrentIndex)
        self.nav_list.setCurrentRow(0)
        
        self.widget.setMinimumWidth(700)
        self.widget.setMinimumHeight(450)

    def _setup_domain_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setAlignment(Qt.AlignTop)
        
        title = StrongBodyLabel("網域設定", self)
        layout.addWidget(title)
        layout.addSpacing(15)
        
        self.gdrive_input = LineEdit(self)
        self.gdrive_input.setPlaceholderText("例如: https://drive.google.com/...")
        self.gdrive_input.setText(self.config.get("gdrive_url", ""))
        layout.addWidget(QLabel("Google Drive 補丁網盤連結:"))
        layout.addWidget(self.gdrive_input)
        
        layout.addSpacing(10)
        
        self.onlinefix_input = LineEdit(self)
        self.onlinefix_input.setPlaceholderText("例如: https://online-fix.me")
        self.onlinefix_input.setText(self.config.get("onlinefix_domain", ""))
        layout.addWidget(QLabel("Online-Fix 官方網域:"))
        layout.addWidget(self.onlinefix_input)
        
        layout.addSpacing(10)
        
        self.luatools_input = LineEdit(self)
        self.luatools_input.setPlaceholderText("例如: https://lua.tools")
        self.luatools_input.setText(self.config.get("luatools_domain", ""))
        layout.addWidget(QLabel("Lua.tools 官方網域:"))
        layout.addWidget(self.luatools_input)
        
        self.stacked_widget.addWidget(page)

    def _setup_storage_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setAlignment(Qt.AlignTop)
        
        title = StrongBodyLabel("資料儲存設定", self)
        layout.addWidget(title)
        layout.addSpacing(15)
        
        # 1. Lua path
        self.lua_dir_input = LineEdit(self)
        self.lua_dir_input.setText(self.config.get("lua_dir", ""))
        layout.addWidget(QLabel("本地 Lua 資料夾路徑:"))
        layout.addWidget(self._create_dir_selector(self.lua_dir_input))
        
        layout.addSpacing(10)
        
        # 2. Credentials path
        self.credentials_input = LineEdit(self)
        self.credentials_input.setText(self.config.get("credentials_dir", ""))
        layout.addWidget(QLabel("憑證與帳號儲存路徑:"))
        layout.addWidget(self._create_dir_selector(self.credentials_input))
        
        layout.addSpacing(10)
        
        # 3. Cache path
        self.cache_input = LineEdit(self)
        self.cache_input.setText(self.config.get("cache_dir", ""))
        layout.addWidget(QLabel("Online-Fix 暫存與快取路徑:"))
        layout.addWidget(self._create_dir_selector(self.cache_input))
        
        self.stacked_widget.addWidget(page)

    def _create_dir_selector(self, line_edit):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit, 1)
        btn = PushButton("瀏覽", self)
        btn.clicked.connect(lambda: self._browse_dir(line_edit))
        layout.addWidget(btn)
        
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def _browse_dir(self, line_edit):
        path = QFileDialog.getExistingDirectory(self, "選擇資料夾", line_edit.text())
        if path:
            line_edit.setText(path)
