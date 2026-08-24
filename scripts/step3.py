import sys
filepath = r"g:\python\SteamManifestUpdater\steam_manifest_gui.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Enable Sorting
content = content.replace(
    "self.tree.setWordWrap(False)",
    "self.tree.setWordWrap(False)\n        self.tree.setSortingEnabled(True)"
)

# 2. Modify populate_table to implement grouping colors and hiding redundant text
old_populate = """    def populate_table(self, results):
        from PySide6.QtGui import QColor, QBrush
        from PySide6.QtCore import Qt
        
        self.btn_update.setEnabled(True)
        self.progress_bar.hide()
        self.lbl_status.setText(f"✅ 更新完成！共處理 {len(results)} 個遊戲。")
        
        self.tree.clear()
        
        # Create Category Folders
        node_updated = QTreeWidgetItem(self.tree)
        node_updated.setText(0, "📁 本次啟動被修正的 Lua")
        node_updated.setFirstColumnSpanned(True)
        node_updated.setExpanded(True)
        node_updated.setForeground(0, QBrush(QColor("#00CC6A")))

        node_normal = QTreeWidgetItem(self.tree)
        node_normal.setText(0, "📁 維持現狀 (已經是最新的)")
        node_normal.setFirstColumnSpanned(True)
        node_normal.setExpanded(False)

        node_error = QTreeWidgetItem(self.tree)
        node_error.setText(0, "📁 讀取失敗 / 無法更新")
        node_error.setFirstColumnSpanned(True)
        node_error.setExpanded(False)
        node_error.setForeground(0, QBrush(QColor("#FF5C5C")))
        
        # Populate Data
        for r in results:
            if r["status"] == "updated":
                parent = node_updated
                color = "#00CC6A"
            elif r["status"] == "normal":
                parent = node_normal
                color = ""
            else:
                parent = node_error
                color = "#FF5C5C"
                
            if r["status"] == "error":
                child = QTreeWidgetItem(parent)
                child.setText(0, str(r["appid"]))
                child.setText(1, f"讀取失敗: {r.get('error_msg', '未知錯誤')}")
                child.setForeground(0, QBrush(QColor(color)))
                child.setForeground(1, QBrush(QColor(color)))
                child.setTextAlignment(0, Qt.AlignCenter)
                child.setTextAlignment(1, Qt.AlignVCenter | Qt.AlignLeft)
            else:
                for r_depot in r["rows"]:
                    child = QTreeWidgetItem(parent)
                    child.setText(0, str(r["appid"]))
                    child.setText(1, str(r["game_name"]))
                    child.setText(2, str(r_depot["depot"]))
                    child.setText(3, str(r_depot["manifest"]))
                    child.setText(4, str(r_depot["build_id"]))
                    child.setText(5, str(r["update_date"]))
                    
                    if color:
                        brush = QBrush(QColor(color))
                        for col_idx in range(6):
                            child.setForeground(col_idx, brush)
                            
                    for col_idx in range(6):
                        if col_idx != 1:
                            child.setTextAlignment(col_idx, Qt.AlignCenter)
                        else:
                            child.setTextAlignment(col_idx, Qt.AlignVCenter | Qt.AlignLeft)"""

new_populate = """    def populate_table(self, results):
        from PySide6.QtGui import QColor, QBrush
        from PySide6.QtCore import Qt
        from datetime import datetime
        
        self.btn_update.setEnabled(True)
        self.progress_bar.hide()
        self.lbl_status.setText(f"✅ 更新完成！共處理 {len(results)} 個遊戲。")
        
        self.tree.clear()
        
        # Create Category Folders
        node_updated = QTreeWidgetItem(self.tree)
        node_updated.setText(0, "📁 本次啟動被修正的 Lua")
        node_updated.setFirstColumnSpanned(True)
        node_updated.setExpanded(True)
        node_updated.setForeground(0, QBrush(QColor("#00CC6A")))

        node_normal = QTreeWidgetItem(self.tree)
        node_normal.setText(0, "📁 維持現狀 (已經是最新的)")
        node_normal.setFirstColumnSpanned(True)
        node_normal.setExpanded(False)

        node_error = QTreeWidgetItem(self.tree)
        node_error.setText(0, "📁 讀取失敗 / 無法更新")
        node_error.setFirstColumnSpanned(True)
        node_error.setExpanded(False)
        node_error.setForeground(0, QBrush(QColor("#FF5C5C")))
        
        # Sort results by update date descending by default
        def get_ts(r):
            if r["update_date"] == "未知": return 0
            try: return datetime.strptime(r["update_date"], "%Y-%m-%d %H:%M:%S").timestamp()
            except: return 0
        results.sort(key=get_ts, reverse=True)
        
        # Colors for zebra striping (10-20% difference)
        bg_colors = ["#2B2B2B", "#383838"]
        color_idx = 0
        
        # Populate Data
        for r in results:
            if r["status"] == "updated":
                parent = node_updated
                fg_color = "#00CC6A"
            elif r["status"] == "normal":
                parent = node_normal
                fg_color = ""
            else:
                parent = node_error
                fg_color = "#FF5C5C"
                
            bg_brush = QBrush(QColor(bg_colors[color_idx % 2]))
            color_idx += 1
                
            if r["status"] == "error":
                child = QTreeWidgetItem(parent)
                child.setText(0, str(r["appid"]))
                child.setText(1, f"讀取失敗: {r.get('error_msg', '未知錯誤')}")
                child.setForeground(0, QBrush(QColor(fg_color)))
                child.setForeground(1, QBrush(QColor(fg_color)))
                child.setBackground(0, bg_brush)
                child.setBackground(1, bg_brush)
                child.setTextAlignment(0, Qt.AlignCenter)
                child.setTextAlignment(1, Qt.AlignVCenter | Qt.AlignLeft)
            else:
                is_first_depot = True
                for r_depot in r["rows"]:
                    child = QTreeWidgetItem(parent)
                    
                    if is_first_depot:
                        child.setText(0, str(r["appid"]))
                        child.setText(1, str(r["game_name"]))
                        is_first_depot = False
                    else:
                        child.setText(0, "")
                        child.setText(1, "")
                        
                    child.setText(2, str(r_depot["depot"]))
                    child.setText(3, str(r_depot["manifest"]))
                    child.setText(4, str(r_depot["build_id"]))
                    child.setText(5, str(r["update_date"]))
                    
                    # Apply colors
                    for col_idx in range(6):
                        child.setBackground(col_idx, bg_brush)
                        if fg_color:
                            child.setForeground(col_idx, QBrush(QColor(fg_color)))
                            
                        # Align text
                        if col_idx != 1:
                            child.setTextAlignment(col_idx, Qt.AlignCenter)
                        else:
                            child.setTextAlignment(col_idx, Qt.AlignVCenter | Qt.AlignLeft)"""

content = content.replace(old_populate, new_populate)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)
print("Step 3 Applied.")
