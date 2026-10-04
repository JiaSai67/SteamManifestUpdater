# -*- coding: utf-8 -*-
"""
雲存檔清單與管理模組 (Cloud Saves Manager)
負責掃描透過本工具 Lua 入庫掛載的遊戲與其本機存檔，
精準過濾非入庫遊戲，提供 Spacewar (AppID 480) 創意工坊宿主雲端存檔狀態與一鍵開啟存檔資料夾功能。
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

class CloudSavesManager:
    """管理 Lua 入庫遊戲之雲存檔清單與本機路徑"""

    def __init__(self, steam_path: Optional[str] = None, cloud_redirect_path: Optional[str] = None):
        self.steam_path = Path(steam_path) if steam_path else None
        self.cloud_redirect_path = Path(cloud_redirect_path) if cloud_redirect_path else None
        
        # 若未指定 cloud_redirect_path 且 steam_path 存在，使用 Steam/config/cloud_saves
        if not self.cloud_redirect_path and self.steam_path and self.steam_path.exists():
            self.cloud_redirect_path = self.steam_path / "config" / "cloud_saves"

    def _get_installed_lua_appids(self) -> set:
        """取得本機已透過 Lua 入庫掛載的 AppID 集合"""
        lua_appids = set()
        if not self.steam_path:
            return lua_appids
        
        # 1. 掃描 Steam/config/lua/
        lua_dir = self.steam_path / "config" / "lua"
        if lua_dir.exists():
            for f in lua_dir.glob("*.lua"):
                if f.stem.isdigit() and f.name != "manifest.lua":
                    lua_appids.add(f.stem)
                    
        # 2. 掃描 Steam/config/stplug-in/
        st_dir = self.steam_path / "config" / "stplug-in"
        if st_dir.exists():
            for f in st_dir.glob("*.lua"):
                if f.stem.isdigit() and f.name != "manifest.lua":
                    lua_appids.add(f.stem)
                    
        return lua_appids

    def _get_latest_mtime(self, folder: Path) -> float:
        """快速取得資料夾內最新檔案的修改時間戳"""
        latest = 0.0
        try:
            if not folder.exists():
                return 0.0
            latest = folder.stat().st_mtime
            # 僅掃描直接子項目與一層子目錄，確保在 0.1ms 內完成
            count = 0
            for item in folder.iterdir():
                count += 1
                if count > 50:  # 避免過多檔案耗時
                    break
                try:
                    m = item.stat().st_mtime
                    if m > latest:
                        latest = m
                    if item.is_dir():
                        for sub_item in item.iterdir():
                            sm = sub_item.stat().st_mtime
                            if sm > latest:
                                latest = sm
                except Exception:
                    continue
        except Exception:
            pass
        return latest

    def _format_time(self, ts: float) -> str:
        """格式化時間戳為 YYYY-MM-DD HH:MM"""
        if not ts or ts <= 0:
            return ""
        try:
            dt = datetime.fromtimestamp(ts)
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return ""

    def _resolve_game_name(self, appid: str) -> str:
        """解析遊戲名稱"""
        # 1. 嘗試從本機 appmanifest 讀取 (極速本機讀取)
        if self.steam_path:
            try:
                manifest_file = self.steam_path / "steamapps" / f"appmanifest_{appid}.acf"
                if manifest_file.exists():
                    text = manifest_file.read_text(encoding="utf-8", errors="ignore")
                    for line in text.splitlines():
                        if '"name"' in line.lower():
                            parts = line.split('"')
                            if len(parts) >= 4:
                                return parts[3].strip()
            except Exception:
                pass

        # 2. 嘗試從 name_resolver 取得
        try:
            from managers.name_resolver import resolve_game_name
            name = resolve_game_name(appid)
            if name and not name.startswith("AppID:"):
                return name
        except Exception:
            pass

        return f"Steam 遊戲 {appid}"

    def _resolve_cover_image(self, appid: str) -> str:
        """優先從本地 Steam librarycache 讀取封面圖 (支援 Base64 秒開)，若無則回退至 CDN"""
        if self.steam_path:
            try:
                import base64
                lc = self.steam_path / "appcache" / "librarycache"
                # 1. 舊版單檔結構 appcache/librarycache/<appid>_header.jpg
                for candidate in [f"{appid}_header.jpg", f"{appid}_library_600x900.jpg", f"{appid}_capsule.jpg"]:
                    f = lc / candidate
                    if f.exists() and f.stat().st_size > 500:
                        with open(f, "rb") as fp:
                            return f"data:image/jpeg;base64,{base64.b64encode(fp.read()).decode()}"
                
                # 2. 新版子目錄結構 appcache/librarycache/<appid>/
                app_dir = lc / appid
                if app_dir.is_dir():
                    patterns = ["*header*.jpg", "*capsule*.jpg", "*hero*.jpg", "*.jpg", "*.png"]
                    for pat in patterns:
                        matches = list(app_dir.glob(pat))
                        if not matches:
                            matches = list(app_dir.rglob(pat))
                        for m in matches:
                            if m.is_file() and m.stat().st_size > 500:
                                mime = "image/png" if m.suffix.lower() == ".png" else "image/jpeg"
                                with open(m, "rb") as fp:
                                    return f"data:{mime};base64,{base64.b64encode(fp.read()).decode()}"
            except Exception:
                pass

        return f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"

    def get_cloud_saves_list(self) -> List[Dict[str, Any]]:
        """
        掃描並返回「僅限 Lua 入庫掛載遊戲」的雲存檔列表。
        精準排除非入庫遊戲與 Steam 系統檔案，並按最新儲存時間降序排列。
        """
        lua_appids = self._get_installed_lua_appids()
        saves_map: Dict[str, Dict[str, Any]] = {}

        # 1. 掃描 cloud_redirect_path（例如 Steam/config/cloud_saves/<appid>/）
        if self.cloud_redirect_path and self.cloud_redirect_path.exists():
            try:
                for entry in self.cloud_redirect_path.iterdir():
                    if entry.is_dir() and entry.name.isdigit():
                        appid = entry.name
                        # 核心過濾：只收錄由本工具 Lua 入庫的遊戲
                        if lua_appids and appid not in lua_appids:
                            continue
                        mtime = self._get_latest_mtime(entry)
                        saves_map[appid] = {
                            "appid": appid,
                            "save_dir": str(entry),
                            "mtime": mtime,
                            "source": "cloud_redirect"
                        }
            except Exception:
                pass

        # 2. 掃描 Steam/userdata/<account_id>/<appid>/remote (尋找 Lua 遊戲存檔)
        if self.steam_path:
            userdata_dir = self.steam_path / "userdata"
            if userdata_dir.exists():
                try:
                    for user_dir in userdata_dir.iterdir():
                        if user_dir.is_dir() and user_dir.name.isdigit():
                            for app_entry in user_dir.iterdir():
                                if app_entry.is_dir() and app_entry.name.isdigit():
                                    appid = app_entry.name
                                    # 核心過濾：只收錄由本工具 Lua 入庫的遊戲
                                    if lua_appids and appid not in lua_appids:
                                        continue
                                    remote_dir = app_entry / "remote"
                                    target_dir = remote_dir if remote_dir.exists() else app_entry
                                    mtime = self._get_latest_mtime(target_dir)
                                    
                                    if mtime > 0:
                                        if appid not in saves_map or mtime > saves_map[appid]["mtime"]:
                                            saves_map[appid] = {
                                                "appid": appid,
                                                "save_dir": str(target_dir),
                                                "mtime": mtime,
                                                "source": "steam_userdata"
                                            }
                except Exception:
                    pass

        # 3. 確保所有已掛載 Lua 的遊戲（即使尚未產生存檔）也能在此被清晰識別並受保護
        for appid in lua_appids:
            if appid not in saves_map:
                saves_map[appid] = {
                    "appid": appid,
                    "save_dir": str(self.cloud_redirect_path / appid) if self.cloud_redirect_path else "",
                    "mtime": 0.0,
                    "source": "lua_mounted"
                }

        # 4. 組裝清單結果 (排除 Spacewar 480 本身與 Steam 系統 AppID)
        SYSTEM_APPIDS = {"7", "760", "228980", "228990", "480"}
        result: List[Dict[str, Any]] = []
        for appid, item in saves_map.items():
            if appid in SYSTEM_APPIDS:
                continue
            name = self._resolve_game_name(appid)
            mtime = item["mtime"]
            has_save = (mtime > 0)
            saved_at = self._format_time(mtime) if has_save else "尚未產生存檔"
            image_url = self._resolve_cover_image(appid)
            result.append({
                "appid": appid,
                "name": name,
                "image": image_url,
                "saved_at": saved_at,
                "mtime": mtime,
                "has_save": has_save,
                "status_badge": "☁️ 已同步" if has_save else "🛡️ 雲端待命中",
                "save_dir": item["save_dir"],
                "source": item["source"],
                "host_name": "Spacewar (AppID 480)"
            })

        # 按儲存狀態與最後儲存時間降序排列 (有存檔且最新的排在最前)
        result.sort(key=lambda x: (1 if x["has_save"] else 0, x["mtime"]), reverse=True)
        return result

    def open_save_folder(self, appid: Optional[str] = None) -> bool:
        """
        開啟指定遊戲的存檔資料夾，或開啟總存檔目錄。
        """
        target_dir = None

        if appid:
            # 優先找 cloud_redirect 目錄
            if self.cloud_redirect_path:
                candidate = self.cloud_redirect_path / str(appid)
                if candidate.exists():
                    target_dir = candidate

            # 其次找 userdata 目錄
            if not target_dir and self.steam_path:
                userdata_dir = self.steam_path / "userdata"
                if userdata_dir.exists():
                    for user_dir in userdata_dir.iterdir():
                        candidate = user_dir / str(appid)
                        if candidate.exists():
                            target_dir = candidate / "remote" if (candidate / "remote").exists() else candidate
                            break

        # 若未找到特定遊戲存檔，開啟總目錄
        if not target_dir:
            if self.cloud_redirect_path and self.cloud_redirect_path.exists():
                target_dir = self.cloud_redirect_path
            elif self.steam_path:
                target_dir = self.steam_path / "config" / "cloud_saves"
                target_dir.mkdir(parents=True, exist_ok=True)

        if target_dir and os.path.exists(target_dir):
            try:
                os.startfile(str(target_dir))
                return True
            except Exception:
                pass
        return False
