import sys

filepath = r"g:\python\SteamManifestUpdater\steam_manifest_gui.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update imports
content = content.replace(
    "TableWidget, SubtitleLabel",
    "TreeWidget, SubtitleLabel"
)
content = content.replace(
    "from update_manifests import get_app_info",
    "from PySide6.QtWidgets import QTreeWidgetItem\nfrom update_manifests import get_app_info"
)

# 2. Replace TableWidget with TreeWidget in initUI
old_ui = """        # 3. Table Widget
        self.table = TableWidget(self)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "AppID", "遊戲名稱 (Game)", "Depot ID", "Manifest ID", "版本 (Build ID)", "更新日期 (Update Date)"
        ])
        # Modern Table Settings
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch) # Only game name stretches
        self.table.setColumnWidth(0, 100)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 200)
        self.table.setColumnWidth(4, 120)
        self.table.setColumnWidth(5, 180)
        self.table.setWordWrap(False)
        main_layout.addWidget(self.table, 1)"""

new_ui = """        # 3. Tree Widget
        self.tree = TreeWidget(self)
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels([
            "AppID", "遊戲名稱 (Game)", "Depot ID", "Manifest ID", "版本 (Build ID)", "更新日期 (Update Date)"
        ])
        self.tree.header().setSectionResizeMode(QHeaderView.Fixed)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch) # Only game name stretches
        
        self.tree.setColumnWidth(0, 100)
        self.tree.setColumnWidth(2, 100)
        self.tree.setColumnWidth(3, 200)
        self.tree.setColumnWidth(4, 120)
        self.tree.setColumnWidth(5, 180)
        self.tree.setWordWrap(False)
        main_layout.addWidget(self.tree, 1)"""
        
content = content.replace(old_ui, new_ui)

# 3. Clear populate_table and self.table.setRowCount(0)
content = content.replace("self.table.setRowCount(0)", "self.tree.clear()")

old_populate = """    def populate_table(self, results):
        self.btn_update.setEnabled(True)
        self.progress_bar.hide()
        self.lbl_status.setText(f"✅ 更新完成！共處理 {len(results)} 個遊戲。")
        
        # Sort results by status
        updated = [r for r in results if r["status"] == "updated"]
        normal = [r for r in results if r["status"] == "normal"]
        errors = [r for r in results if r["status"] == "error"]
        
        # Combine all to one list for simple insertion
        all_rows = []
        for r in updated:
            for r_depot in r["rows"]:
                all_rows.append((r["appid"], r["game_name"], r_depot["depot"], r_depot["manifest"], r_depot["build_id"], r["update_date"], "#00CC6A")) # Green
        for r in normal:
            for r_depot in r["rows"]:
                all_rows.append((r["appid"], r["game_name"], r_depot["depot"], r_depot["manifest"], r_depot["build_id"], r["update_date"], ""))
        for r in errors:
            all_rows.append((r["appid"], "讀取失敗 / 無法更新", "", "", "", "", "#FF5C5C")) # Red
            
        self.table.setRowCount(len(all_rows))
        for row_idx, row_data in enumerate(all_rows):
            from PySide6.QtWidgets import QTableWidgetItem
            from PySide6.QtGui import QColor, QBrush
            
            for col_idx in range(6):
                item = QTableWidgetItem(str(row_data[col_idx]))
                # Center align all except game name
                if col_idx != 1:
                    item.setTextAlignment(Qt.AlignCenter)
                else:
                    item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                
                # Apply color if specified (row_data[6])
                color_hex = row_data[6]
                if color_hex:
                    item.setForeground(QBrush(QColor(color_hex)))
                    
                self.table.setItem(row_idx, col_idx, item)"""

new_populate = """    def populate_table(self, results):
        self.btn_update.setEnabled(True)
        self.progress_bar.hide()
        self.lbl_status.setText(f"✅ 更新完成！共處理 {len(results)} 個遊戲。")
        
        # Step 1: Just clear the tree for now to verify performance.
        self.tree.clear()
        
        # Adding a single dummy node to verify structure renders without lag
        dummy_node = QTreeWidgetItem(["(資料填入測試階段) 正在等待第二步注入..."])
        dummy_node.setFirstColumnSpanned(True)
        self.tree.addTopLevelItem(dummy_node)
"""
content = content.replace(old_populate, new_populate)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)
print("Step 1 Applied.")
