import os
import json
import stat
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QTextEdit, QLabel
)
from qfluentwidgets import (
    PrimaryPushButton, PushButton, ProgressBar, StrongBodyLabel,
    BodyLabel, SubtitleLabel, CardWidget, InfoBar, InfoBarPosition,
    CheckBox
)
from managers import steam_manager, lua_tools_manager, ryuu_manager, name_resolver
from ui.theme_utils import get_state_color


class BatchManifestRepairDialog(QDialog):
    repaired_finished = Signal()

    def __init__(self, parent=None, steam_path=None, lua_dir=None):
        super().__init__(parent)
        self.setWindowTitle("⚡ 批次補齊 Manifest 清單 (Lua.tools / Ryuu 雙來源)")
        self.resize(920, 720)
        self.steam_path = steam_path or steam_manager.find_steam_path()
        self.lua_dir = lua_dir or (Path(self.steam_path) / "config" / "lua" if self.steam_path else None)
        self.is_running = False
        self.should_stop = False
        self.current_index = 0
        self.queue = []

        self.lt_client = lua_tools_manager.get_shared_client()
        self.ryuu_client = ryuu_manager.get_shared_ryuu_client()

        from managers.account_manager import get_account_manager
        self.acc_mgr = get_account_manager()
        self.acc_mgr.quota_updated.connect(lambda *_: self._check_login_status())
        self.acc_mgr.account_changed.connect(lambda *_: self._check_login_status())
        self.acc_mgr.registry_updated.connect(self._check_login_status)

        self.lt_client.ready.connect(self._check_login_status)
        self.lt_client.not_logged_in.connect(self._check_login_status)
        self.ryuu_client.ready.connect(self._check_login_status)
        self.ryuu_client.not_logged_in.connect(self._check_login_status)

        self._init_ui()
        self._load_incomplete_games()
        self._check_login_status()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        # 1. Title & Description
        title = SubtitleLabel("⚡ 本地殘缺檔案 Manifest 批次修復精靈", self)
        main_layout.addWidget(title)

        desc = BodyLabel(
            "依據最新防護規範，所有本地缺少 .manifest 實體檔之遊戲皆被認定為「殘缺檔案」，無法正常運行。\n"
            "本工具支援 Lua.tools 與 Ryuu Generator 雙平台，支援多帳號與每日配額自動輪替，自動部署至 Steam/depotcache 並啟用版本鎖定防護。",
            self
        )
        desc.setWordWrap(True)
        main_layout.addWidget(desc)

        # 2. Dual Auth & Quota Card
        auth_card = CardWidget(self)
        auth_layout = QVBoxLayout(auth_card)
        auth_layout.setContentsMargins(15, 12, 15, 12)
        auth_layout.setSpacing(8)

        # Row 1: Lua.tools
        r1 = QHBoxLayout()
        self.lbl_lt_status = StrongBodyLabel("1. Lua.tools 聚合平台: 檢查中...", self)
        self.btn_login_lt = PrimaryPushButton("登入 Lua.tools (Discord)", self)
        self.btn_login_lt.clicked.connect(self._open_lt_login)
        r1.addWidget(self.lbl_lt_status, 1)
        r1.addWidget(self.btn_login_lt)
        auth_layout.addLayout(r1)

        # Row 2: Ryuu Generator
        r2 = QHBoxLayout()
        self.lbl_ryuu_status = StrongBodyLabel("2. Ryuu Generator 平台: 檢查中...", self)
        self.btn_login_ryuu = PushButton("登入 Ryuu Generator (Discord)", self)
        self.btn_login_ryuu.clicked.connect(self._open_ryuu_login)
        r2.addWidget(self.lbl_ryuu_status, 1)
        r2.addWidget(self.btn_login_ryuu)
        auth_layout.addLayout(r2)

        # Row 3: Multi-Account & Quota
        r3 = QHBoxLayout()
        self.lbl_quota_summary = BodyLabel("📊 總可用配額: 載入中...", self)
        self.btn_open_accounts = PushButton("👥 多帳號與配額管理 (Quota)", self)
        self.btn_open_accounts.clicked.connect(self._open_account_manager)
        r3.addWidget(self.lbl_quota_summary, 1)
        r3.addWidget(self.btn_open_accounts)
        auth_layout.addLayout(r3)

        main_layout.addWidget(auth_card)

        # 3. Games Table
        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["選取", "AppID", "遊戲名稱", "缺少檔案數量", "處理進度與來源"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Interactive)
        self.table.setColumnWidth(4, 290)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        main_layout.addWidget(self.table, 1)

        # 4. Progress Bar & Real-time Status
        self.progress_bar = ProgressBar(self)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        self.lbl_current_status = BodyLabel("就緒。請確認至少一個平台已登入，然後點擊下方按鈕開始批次修復。", self)
        main_layout.addWidget(self.lbl_current_status)

        # 5. Buttons Row
        btn_layout = QHBoxLayout()
        self.btn_select_all = PushButton("全選", self)
        self.btn_select_all.clicked.connect(self._toggle_select_all)
        self.btn_open_depotcache = PushButton("📂 開啟 depotcache 資料夾", self)
        self.btn_open_depotcache.clicked.connect(self._open_depotcache)

        self.btn_start = PrimaryPushButton("🚀 開始批次下載並部署 Manifest", self)
        self.btn_start.clicked.connect(self._start_batch_repair)

        self.btn_stop = PushButton("⏹️ 停止", self)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_repair)

        self.btn_close = PushButton("關閉", self)
        self.btn_close.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_select_all)
        btn_layout.addWidget(self.btn_open_depotcache)
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.btn_stop)
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_close)
        main_layout.addLayout(btn_layout)

    def _probe_quota(self):
        self.btn_probe_quota.setEnabled(False)
        self.btn_probe_quota.setText("⏳ 探測中...")

        def on_lt_done(lt_info):
            def on_ryuu_done(ryuu_info):
                self.btn_probe_quota.setEnabled(True)
                self.btn_probe_quota.setText("⚡ 探測配額 (Try Quota)")
                self._check_login_status()
                msg = f"Lua.tools: {lt_info.get('message')}\nRyuu: {ryuu_info.get('message')}"
                if lt_info.get("valid") or ryuu_info.get("valid"):
                    InfoBar.success("探測結果", msg, parent=self, duration=5000)
                else:
                    InfoBar.error("探測異常 / 憑證過期", msg, parent=self, duration=7000)

            self.ryuu_client.probe_quota(on_ryuu_done)

        self.lt_client.probe_quota(on_lt_done)

    def _open_account_manager(self):
        from ui.account_manager_ui import MultiAccountManagerDialog
        dlg = MultiAccountManagerDialog(self)
        dlg.exec()
        self._check_login_status()

    def _check_login_status(self):
        # Lua.tools
        lt_acc = self.acc_mgr.get_active_account("lua_tools")
        lt_accounts = self.acc_mgr.get_accounts("lua_tools")
        lt_ok = self.lt_client.is_logged_in or lua_tools_manager.has_saved_credentials()
        if lt_ok and lt_acc:
            is_exp = lt_acc.get("is_expired", False)
            rem = max(0, lt_acc.get("daily_limit", 25) - lt_acc.get("quota_used_today", 0))
            total_rem, total_lim = self.acc_mgr.get_total_remaining_quota("lua_tools")
            acc_name = lt_acc.get("name", "預設帳號")
            if is_exp:
                status_tag = "❌ 憑證已過期 (需重新登入)"
                color = get_state_color('error')
                self.btn_login_lt.setText("重新登入")
            elif lt_acc.get("is_exhausted"):
                status_tag = "🔴 額度已滿(輪替中)"
                color = get_state_color('warning')
                self.btn_login_lt.setText("切換 / 管理")
            else:
                status_tag = f"剩餘 {rem}/{lt_acc.get('daily_limit', 25)} 次"
                color = get_state_color('success')
                self.btn_login_lt.setText("切換 / 管理")
            self.lbl_lt_status.setText(f"1. Lua.tools: [{acc_name}] {status_tag} (共 {len(lt_accounts)} 帳號: 總剩餘 {total_rem}/{total_lim})")
            self.lbl_lt_status.setStyleSheet(f"color: {color};")
        elif lt_ok:
            self.lbl_lt_status.setText("1. Lua.tools 狀態: ✅ 已登入 (憑證已保存)")
            self.lbl_lt_status.setStyleSheet(f"color: {get_state_color('success')};")
            self.btn_login_lt.setText("切換 / 管理")
        else:
            self.lbl_lt_status.setText("1. Lua.tools 狀態: ❌ 未登入")
            self.lbl_lt_status.setStyleSheet(f"color: {get_state_color('error')};")
            self.btn_login_lt.setText("登入 Lua.tools (Discord)")

        # Ryuu
        ryuu_acc = self.acc_mgr.get_active_account("ryuu")
        ryuu_accounts = self.acc_mgr.get_accounts("ryuu")
        ryuu_ok = self.ryuu_client.is_logged_in or ryuu_manager.has_saved_ryuu_credentials()
        if ryuu_ok and ryuu_acc:
            is_exp_r = ryuu_acc.get("is_expired", False)
            rem_r = max(0, ryuu_acc.get("daily_limit", 50) - ryuu_acc.get("quota_used_today", 0))
            total_rem_r, total_lim_r = self.acc_mgr.get_total_remaining_quota("ryuu")
            acc_name_r = ryuu_acc.get("name", "Ryuu 帳號")
            if is_exp_r:
                status_tag_r = "❌ 憑證已過期 (需重新登入)"
                color_r = get_state_color('error')
                self.btn_login_ryuu.setText("重新登入")
            elif ryuu_acc.get("is_exhausted"):
                status_tag_r = "🔴 額度已滿"
                color_r = get_state_color('warning')
                self.btn_login_ryuu.setText("切換 / 管理")
            else:
                status_tag_r = f"剩餘 {rem_r}/{ryuu_acc.get('daily_limit', 50)} 次"
                color_r = get_state_color('success')
                self.btn_login_ryuu.setText("切換 / 管理")
            self.lbl_ryuu_status.setText(f"2. Ryuu Generator: [{acc_name_r}] {status_tag_r} (共 {len(ryuu_accounts)} 帳號: 總剩餘 {total_rem_r}/{total_lim_r})")
            self.lbl_ryuu_status.setStyleSheet(f"color: {color_r};")
        elif ryuu_ok:
            self.lbl_ryuu_status.setText("2. Ryuu Generator 狀態: ✅ 已登入 (憑證已保存)")
            self.lbl_ryuu_status.setStyleSheet(f"color: {get_state_color('success')};")
            self.btn_login_ryuu.setText("切換 / 管理")
        else:
            self.lbl_ryuu_status.setText("2. Ryuu Generator 狀態: ⚠️ 未登入 (可作為備援下載來源)")
            self.lbl_ryuu_status.setStyleSheet(f"color: {get_state_color('warning')};")
            self.btn_login_ryuu.setText("登入 Ryuu (Discord)")

        # Quota summary
        lt_rem, lt_tot = self.acc_mgr.get_total_remaining_quota("lua_tools")
        ryuu_rem, ryuu_tot = self.acc_mgr.get_total_remaining_quota("ryuu")
        auto_rot = "⚡ 自動輪替: 啟用中" if self.acc_mgr.data.get("auto_rotate", True) else "手動選擇"
        self.lbl_quota_summary.setText(f"📊 今日總可用下載配額: Lua.tools 剩餘 {lt_rem}/{lt_tot} 次 | Ryuu 剩餘 {ryuu_rem}/{ryuu_tot} 次 ({auto_rot})")

    def _open_lt_login(self):
        self._open_account_manager()

    def _open_ryuu_login(self):
        self._open_account_manager()

    def _load_incomplete_games(self):
        status_res = steam_manager.get_all_lua_manifest_statuses(self.steam_path, self.lua_dir)
        incomplete_items = status_res.get("incomplete_items", [])
        
        self.table.setRowCount(len(incomplete_items))
        for row, item in enumerate(incomplete_items):
            appid_str = str(item["appid"])
            game_name = item.get("game_name", "未知遊戲")
            if not game_name or game_name == "未知遊戲":
                game_name = name_resolver.resolve_game_name(appid_str, lua_path=item.get("lua_path"), steam_path=self.steam_path)

            # 0. Checkbox
            chk = CheckBox(self.table)
            chk.setChecked(True)
            self.table.setCellWidget(row, 0, chk)

            # 1. AppID
            it_appid = QTableWidgetItem(appid_str)
            it_appid.setTextAlignment(Qt.AlignCenter)
            it_appid.setFlags(it_appid.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, it_appid)

            # 2. Name
            it_name = QTableWidgetItem(game_name)
            it_name.setFlags(it_name.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 2, it_name)

            # 3. Missing count
            missing_count = len(item["missing_files"])
            it_missing = QTableWidgetItem(f"缺少 {missing_count} 個")
            it_missing.setTextAlignment(Qt.AlignCenter)
            it_missing.setToolTip("\n".join(item["missing_files"]))
            it_missing.setFlags(it_missing.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 3, it_missing)

            # 4. Status
            it_status = QTableWidgetItem("等待中")
            it_status.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            it_status.setFlags(it_status.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 4, it_status)

        self.lbl_current_status.setText(f"共偵測到 {len(incomplete_items)} 款殘缺遊戲（缺少 Manifest 清單檔）。")

    def _toggle_select_all(self):
        all_checked = True
        for row in range(self.table.rowCount()):
            w = self.table.cellWidget(row, 0)
            if isinstance(w, CheckBox) and not w.isChecked():
                all_checked = False
                break
        new_state = not all_checked
        for row in range(self.table.rowCount()):
            w = self.table.cellWidget(row, 0)
            if isinstance(w, CheckBox):
                w.setChecked(new_state)

    def _open_depotcache(self):
        if self.steam_path:
            p = Path(self.steam_path) / "depotcache"
            p.mkdir(parents=True, exist_ok=True)
            import subprocess
            subprocess.run(["explorer", str(p)])

    def _start_batch_repair(self):
        lt_ok = self.lt_client.is_logged_in or lua_tools_manager.has_saved_credentials()
        ryuu_ok = self.ryuu_client.is_logged_in or ryuu_manager.has_saved_ryuu_credentials()
        if not lt_ok and not ryuu_ok:
            InfoBar.warning("尚未登入", "Lua.tools 與 Ryuu 皆未登入，請至少登入其中一個平台以取得 Manifest 下載權限！", parent=self)
            self._open_lt_login()
            return

        # Build queue
        self.queue = []
        for row in range(self.table.rowCount()):
            chk = self.table.cellWidget(row, 0)
            if isinstance(chk, CheckBox) and chk.isChecked():
                appid = self.table.item(row, 1).text()
                name = self.table.item(row, 2).text()
                self.queue.append((row, appid, name))

        if not self.queue:
            InfoBar.warning("提示", "未選取任何欲修復的遊戲！", parent=self)
            return

        self.is_running = True
        self.should_stop = False
        self.current_index = 0
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setValue(0)

        self._process_next_item()

    def _stop_repair(self):
        self.should_stop = True
        self.btn_stop.setEnabled(False)
        self.lbl_current_status.setText("正在停止批次修復...")

    def _process_next_item(self):
        if self.should_stop or self.current_index >= len(self.queue):
            self._finish_batch()
            return

        row, appid, name = self.queue[self.current_index]
        total = len(self.queue)
        progress = int((self.current_index / total) * 100)
        self.progress_bar.setValue(progress)

        self.lbl_current_status.setText(f"[{self.current_index + 1}/{total}] 正在多源比對 {name} (AppID: {appid})...")
        item_status = self.table.item(row, 4)

        # 1. 透過 UnifiedManifestManager 進行 Ryuu + Lua.tools 多源比對
        from managers import unified_manifest_manager
        mgr = unified_manifest_manager.get_unified_manifest_manager()
        search_res = mgr.search_all_sources(appid)
        best_source = search_res.get("best_source", "ryuu")
        best_reason = search_res.get("best_reason", "")

        # 2. 檢測 Ryuu 與 Lua.tools 配額狀態並依最佳來源執行
        ryuu_has_quota = (self.ryuu_client.is_logged_in or ryuu_manager.has_saved_ryuu_credentials()) and self.acc_mgr.has_available_quota("ryuu")
        lt_has_quota = (self.lt_client.is_logged_in or lua_tools_manager.has_saved_credentials()) and self.acc_mgr.has_available_quota("lua_tools")

        if best_source == "lua_tools" and lt_has_quota:
            if item_status:
                item_status.setText(f"⚡ 切換至 Lua.tools 下載中 ({best_reason})...")
            self._search_and_download_via_lt(row, appid, name, item_status)
        elif ryuu_has_quota:
            if item_status:
                item_status.setText(f"⚡ 優先使用 Ryuu Generator 下載中 ({best_reason})...")
            self._download_via_ryuu_direct(row, appid, name, item_status)
        elif lt_has_quota:
            if item_status:
                item_status.setText("⏳ (Ryuu 額度用罄) 切換至 Lua.tools 來源...")
            self._search_and_download_via_lt(row, appid, name, item_status)
        else:
            # 所有平台配額皆已用盡或未登入，快速標記剩餘所有項目並終止，避免空轉
            if item_status:
                item_status.setText("🛑 今日所有來源配額均已用罄")
            
            # 將後續佇列項目一併標記為配額用罄略過
            for rem_idx in range(self.current_index + 1, len(self.queue)):
                rem_row, _, _ = self.queue[rem_idx]
                rem_status = self.table.item(rem_row, 4)
                if rem_status:
                    rem_status.setText("🛑 配額耗盡 (已略過)")

            InfoBar.warning(
                "配額已耗盡",
                "Lua.tools 與 Ryuu 今日可用配額已全數用罄。您可以前往「👥 多帳號管理」新增或綁定更多帳號以繼續下載！",
                parent=self,
                duration=7000,
                position=InfoBarPosition.TOP
            )
            self._finish_batch()

    def _search_and_download_via_lt(self, row, appid, name, item_status):
        def on_search(res):
            if self.should_stop:
                self._finish_batch()
                return

            # 🌟 嚴格只認可並請求 Ryuu 來源 (杜絕 Luie 等無 Manifest 來源消耗額度)
            best_source = None
            if isinstance(res, dict):
                sources_dict = res.get("sources", res)
                for pref in ["Ryuu"]:
                    for k, v in sources_dict.items():
                        if str(k).lower() == pref.lower():
                            if (isinstance(v, dict) and v.get("available")) or (isinstance(v, str) and (v.lower() == "available" or v.lower() == "true")) or (isinstance(v, bool) and v):
                                best_source = pref
                                break
                    if best_source: break
            elif isinstance(res, list):
                for it in res:
                    s_name = str(it.get("name", it.get("source", ""))).strip()
                    av_val = it.get("available")
                    if (str(av_val).lower() == "true" or bool(av_val)) if av_val is not None else False:
                        for pref in ["Ryuu"]:
                            if s_name.lower() == pref.lower():
                                best_source = pref
                                break
                        if best_source: break

            if not best_source:
                if item_status:
                    item_status.setText("⚠️ Lua.tools (Ryuu 來源) 暫無此遊戲 Manifest")
                self._step_done()
                return

            if item_status:
                item_status.setText(f"⬇️ 下載中 (來源: {best_source})...")

            # Download from lua.tools with normalized source case
            def on_download(dl_res):
                if self.should_stop:
                    self._finish_batch()
                    return

                if not dl_res or (isinstance(dl_res, dict) and dl_res.get("error")):
                    err = str(dl_res.get("error", "錯誤")) if isinstance(dl_res, dict) else "錯誤"
                    is_unauth = isinstance(dl_res, dict) and dl_res.get("unauthorized")
                    if item_status:
                        if is_unauth:
                            item_status.setText("❌ Lua.tools 憑證已過期/未授權")
                        else:
                            item_status.setText(f"❌ 下載失敗: {err[:35]}")
                    self._step_done()
                    return

                manifests = dl_res.get("manifests", {})
                if not manifests:
                    if item_status:
                        item_status.setText("⚠️ 來源未提供 Manifest 實體檔")
                    self._step_done()
                    return

                lua_content = dl_res.get("lua_content", dl_res.get("data", ""))
                self._save_and_lock_manifests(row, appid, name, manifests, item_status, source_name=f"Lua.tools ({best_source})", lua_content=lua_content)

            self.lt_client.download_manifest(appid, best_source, f"Game_{appid}", on_download)

        self.lt_client.search_manifest(appid, on_search)

    def _download_via_ryuu_direct(self, row, appid, name, item_status):
        if item_status:
            item_status.setText("⏳ (Ryuu 專屬) 預檢遊戲檔案庫存中...")

        # 1. 使用 Ryuu 專屬公開端點進行 0 消耗快速預檢
        info = ryuu_manager.fetch_ryuu_manifest_info(appid)
        if not info.get("found"):
            # Ryuu 查無此遊戲，Fallback 切換至 Lua.tools
            lt_has_quota = (self.lt_client.is_logged_in or lua_tools_manager.has_saved_credentials()) and self.acc_mgr.has_available_quota("lua_tools")
            if lt_has_quota:
                if item_status:
                    item_status.setText("🔄 Ryuu 暫無此遊戲，切換至 Lua.tools 搜尋...")
                self._search_and_download_via_lt(row, appid, name, item_status)
                return

            if item_status:
                item_status.setText("⚠️ Ryuu 來源暫無此遊戲 Manifest")
            self._step_done()
            return

        default_branch = info.get("default_branch", "public")
        file_count = len(info.get("files", []))
        if item_status:
            item_status.setText(f"⬇️ Ryuu 下載中 ({file_count} 檔案, 分支: {default_branch})...")

        def on_ryuu_dl(dl_res):
            if self.should_stop:
                self._finish_batch()
                return

            if not dl_res or (isinstance(dl_res, dict) and dl_res.get("error")):
                err = str(dl_res.get("error", "錯誤")) if isinstance(dl_res, dict) else "錯誤"
                is_unauth = isinstance(dl_res, dict) and dl_res.get("unauthorized")
                is_quota_exhausted = isinstance(dl_res, dict) and dl_res.get("quota_exhausted")
                is_rate_limited = isinstance(dl_res, dict) and dl_res.get("rate_limited")
                is_not_found = isinstance(dl_res, dict) and dl_res.get("not_found")

                # 若 Ryuu 發生錯誤或配額滿，嘗試 Fallback 到 Lua.tools
                lt_has_quota = (self.lt_client.is_logged_in or lua_tools_manager.has_saved_credentials()) and self.acc_mgr.has_available_quota("lua_tools")
                if lt_has_quota and (is_quota_exhausted or is_rate_limited or is_not_found):
                    if item_status:
                        item_status.setText("🔄 Ryuu 下載受限，自動切換至 Lua.tools...")
                    self._search_and_download_via_lt(row, appid, name, item_status)
                    return

                if is_unauth:
                    if item_status:
                        item_status.setText("❌ Ryuu 憑證未登入/已失效")
                elif is_quota_exhausted:
                    if item_status:
                        item_status.setText("🛑 Ryuu 今日配額已滿 (50/50)")
                elif is_rate_limited:
                    if item_status:
                        item_status.setText("🛑 Ryuu 發送頻率過快")
                elif is_not_found:
                    if item_status:
                        item_status.setText("⚠️ Ryuu 來源暫無此遊戲 Manifest")
                else:
                    if item_status:
                        item_status.setText(f"❌ Ryuu 下載失敗: {err[:35]}")
                self._step_done()
                return

            manifests = dl_res.get("manifests", {})
            if not manifests:
                if item_status:
                    item_status.setText("⚠️ Ryuu 來源缺少 Manifest 實體檔")
                self._step_done()
                return

            lua_content = dl_res.get("lua_content", dl_res.get("data", ""))
            self._save_and_lock_manifests(row, appid, name, manifests, item_status, source_name="Ryuu Direct", lua_content=lua_content)

        self.ryuu_client.download_manifest(appid, default_branch, on_ryuu_dl)

    def _save_and_lock_manifests(self, row, appid, name, manifests, item_status, source_name="", lua_content=""):
        deployed, failed = steam_manager.deploy_manifests_to_depotcache(
            manifests, self.steam_path, self.lua_dir
        )

        # 1. 強制將 Ryuu / 下載來源之完整 Lua 覆蓋寫入本地 Lua 目錄與 Steam 目錄，確保與 Manifest 100% 同步
        if lua_content and lua_content.strip():
            try:
                if self.lua_dir:
                    lua_file = Path(self.lua_dir) / f"{appid}.lua"
                    lua_file.parent.mkdir(parents=True, exist_ok=True)
                    if lua_file.exists():
                        os.chmod(lua_file, stat.S_IWRITE | stat.S_IREAD)
                    lua_file.write_text(lua_content, encoding="utf-8")

                if self.steam_path:
                    steam_lua_file = Path(self.steam_path) / "config" / "lua" / f"{appid}.lua"
                    if not self.lua_dir or Path(self.lua_dir).resolve() != steam_lua_file.parent.resolve():
                        steam_lua_file.parent.mkdir(parents=True, exist_ok=True)
                        if steam_lua_file.exists():
                            os.chmod(steam_lua_file, stat.S_IWRITE | stat.S_IREAD)
                        steam_lua_file.write_text(lua_content, encoding="utf-8")
            except Exception as e:
                print(f"[batch_manifest_ui] Write lua failed for {appid}: {e}")

        # 2. 同步更新本地與 Steam Lua 檔案宣告之 Manifest ID
        if self.lua_dir:
            steam_manager.sync_lua_with_deployed_manifests(appid, manifests, self.lua_dir)
        if self.steam_path:
            steam_manager.sync_lua_with_deployed_manifests(appid, manifests, Path(self.steam_path) / "config" / "lua")

        # 3. 雙重保護：自動清洗並註解缺少實體清單的可選 DLC，防止殘缺報警與 Steam 401 錯誤
        if self.lua_dir:
            steam_manager.sanitize_lua_manifests(appid, self.steam_path, self.lua_dir)
        if self.steam_path:
            steam_manager.sanitize_lua_manifests(appid, self.steam_path, Path(self.steam_path) / "config" / "lua")

        lock_ok, lock_msg = steam_manager.lock_game_version(
            appid, self.steam_path, set_readonly=True, game_name=name
        )

        src_text = f" [{source_name}]" if source_name else ""
        if item_status:
            item_status.setText(f"✅ 成功部署 {deployed} 個 Manifest 🔒{src_text}")

        self._step_done()

    def _step_done(self):
        self.current_index += 1
        QTimer.singleShot(350, self._process_next_item)

    def _finish_batch(self):
        self.is_running = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setValue(100)

        success_count = 0
        for row in range(self.table.rowCount()):
            it = self.table.item(row, 4)
            if it and "✅" in it.text():
                success_count += 1

        self.lbl_current_status.setText(f"🎉 批次處理完畢！成功補齊 {success_count} 款遊戲之 Manifest。")
        InfoBar.success(
            "批次修復完成",
            f"已成功部署 {success_count} 款遊戲的 Manifest 檔案，並自動啟用版本鎖定防護 🔒！",
            parent=self,
            duration=6000,
            position=InfoBarPosition.TOP
        )
        self.repaired_finished.emit()
