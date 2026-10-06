# -*- coding: utf-8 -*-
"""
SMU Modular Handler Component
自動解耦之專屬業務處理模組
"""
import os
import sys
import re
import json
import time
import shutil
import urllib.request
import urllib.parse
import subprocess
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional
import concurrent.futures

from managers import config_manager
from managers import steam_manager
from managers import unified_manifest_manager

class SettingsHandler:
    def open_steam_workshop_saves(self, appid: str = "480") -> bool:
        """直接在 Steam 客戶端 (Steam App) 內開啟雲端工作坊存檔項目頁面"""
        try:
            aid = str(appid).strip() if appid else "480"
            url = f"https://steamcommunity.com/my/myworkshopfiles/?appid={aid}&browsefilter=myfiles"
            # 優先嘗試以 Steam 原生協議直接在 Steam 客戶端內部打開
            try:
                os.startfile(f"steam://openurl/{url}")
                return True
            except Exception:
                pass
            import webbrowser
            webbrowser.open(url)
            return True
        except Exception:
            return False

    def open_steam_remote_storage(self) -> bool:
        """在 Steam 客戶端或瀏覽器中開啟 Steam 官方全遊戲線上雲端存檔檢視頁 (Remote Storage)"""
        try:
            url = "https://store.steampowered.com/account/remotestorage"
            try:
                os.startfile(f"steam://openurl/{url}")
                return True
            except Exception:
                pass
            import webbrowser
            webbrowser.open(url)
            return True
        except Exception:
            return False

    def get_config(self) -> Dict[str, Any]:
        """讀取全域配置"""
        self._config = config_manager.get_config()
        if not self._config.get("steam_path"):
            sp = steam_manager.find_steam_path()
            if sp: self._config["steam_path"] = str(sp)
        return self._config

    def set_config(self, key: str, val: Any) -> bool:
        """儲存單項配置（自動相容 dark/dark_mode 與 random/random_browse）"""
        self._config[key] = val
        if key in ("dark", "dark_mode"):
            self._config["dark"] = val
            self._config["dark_mode"] = val
        elif key in ("random", "random_browse"):
            self._config["random"] = val
            self._config["random_browse"] = val
        elif key == "view_mode":
            self._config["view_mode"] = val
        elif key == "cloud_redirect":
            self._config[key] = bool(val)
        elif key == "cloud_redirect_path":
            self._config[key] = val
        config_manager.save_config(self._config)
        return True

    def cloud_dest(self) -> str:
        """取得當前雲存檔去向 (功能已停用，固定回傳 local)"""
        return "local"

    def cloud_set_dest(self, mode: str) -> Dict[str, Any]:
        """設定雲存檔去向 (功能已停用)"""
        return {"ok": True, "mode": "local"}

    def open_cloud_path(self) -> bool:
        """開啟本機存檔儲存目錄 (功能已停用)"""
        return False

    def _apply_cloud_redirect(self, enabled: bool) -> bool:
        """雲存檔目錄聯接管理 (若關閉則清理 junction)"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp:
            return False
        link_dir = Path(sp) / "cloud_redirect" / "storage"
        if not enabled:
            if link_dir.exists() or link_dir.is_symlink():
                try:
                    subprocess.run(["cmd", "/c", "rmdir", str(link_dir)], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                except Exception:
                    pass
            cr_cfg_file = Path(sp) / "cloud_redirect" / "config.json"
            if cr_cfg_file.exists():
                try:
                    with open(cr_cfg_file, "r", encoding="utf-8") as f:
                        cr_cfg = json.load(f)
                    cr_cfg["cloud_redirect"] = False
                    with open(cr_cfg_file, "w", encoding="utf-8") as f:
                        json.dump(cr_cfg, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass
        return True

    def get_cloud_saves_list(self) -> List[Dict[str, Any]]:
        """雲存檔功能已停用，固定返回空清單"""
        return []

    def open_cloud_save_folder(self, appid: str = "") -> bool:
        """開啟指定遊戲或全域存檔資料夾 (功能已停用)"""
        return False

    def get_bg_thumbnails(self) -> List[Dict[str, Any]]:
        """取得可用自訂背景清單 (支援 JPG/PNG/WEBP/GIF 動圖)"""
        bgs_dir = Path("data/backgrounds")
        bgs_dir.mkdir(parents=True, exist_ok=True)
        res = []
        for f in bgs_dir.glob("*.*"):
            if f.suffix.lower() in [".jpg", ".png", ".jpeg", ".webp", ".gif"]:
                data_url = self.get_bg_data(f.name)
                res.append({
                    "id": f.name,
                    "thumb": data_url
                })
        return res

    def add_bg_base64(self, name: str, b64_data: str) -> Dict[str, Any]:
        """透過 Base64 添加自訂背景 (支援 GIF 等動圖)"""
        try:
            import base64
            if "," in b64_data:
                b64_data = b64_data.split(",", 1)[1]
            raw = base64.b64decode(b64_data)
            bgs_dir = Path("data/backgrounds")
            bgs_dir.mkdir(parents=True, exist_ok=True)
            p = bgs_dir / name
            with open(p, "wb") as f:
                f.write(raw)
            return {
                "id": name,
                "thumb": self.get_bg_data(name)
            }
        except Exception:
            return None

    def remove_bg(self, name: str) -> bool:
        """移除自訂背景"""
        p = Path("data/backgrounds") / name
        if p.exists():
            p.unlink()
            return True
        return False

    def restore_default_bgs(self) -> bool:
        """恢復預設背景"""
        self._config["current_bg"] = ""
        config_manager.save_config(self._config)
        return True

    def get_cloud_drives(self) -> List[Dict[str, Any]]:
        """取得設定的所有 Google Drive 雲端網盤清單"""
        from managers import onlinefix_manager
        return onlinefix_manager.get_cloud_drives()

    def save_cloud_drives(self, drives: List[Dict[str, Any]]) -> Dict[str, Any]:
        """更新並儲存 Google Drive 雲端網盤清單（含優先順序與網址）"""
        from managers import onlinefix_manager
        try:
            onlinefix_manager.update_cloud_drives(drives)
            self._config = config_manager.get_config()
            return {"ok": True, "msg": f"已成功儲存 {len(drives)} 個網盤設定！"}
        except Exception as e:
            return {"ok": False, "msg": f"儲存網盤設定失敗: {e}"}

    def sync_cloud_drives(self) -> Dict[str, Any]:
        """強制同步並刷新 Google Drive 雲端補丁快取索引"""
        from managers import onlinefix_manager
        try:
            items = onlinefix_manager.sync_cloud_cache()
            count = len(items) if items else 0
            return {"ok": True, "count": count, "msg": f"已成功同步雲端索引，共掃描到 {count} 個補丁檔案！"}
        except Exception as e:
            return {"ok": False, "msg": f"同步雲端快取失敗: {e}"}

    def get_gdrive_index_summary(self) -> Dict[str, Any]:
        """取得 Google Drive 索引記錄狀態摘要 (包含 JSON / TXT 記錄檔路徑與各網盤統計)"""
        from managers import onlinefix_manager
        try:
            return {"ok": True, "data": onlinefix_manager.get_gdrive_index_summary()}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def get_game_cloud_drive_status(self, appid: str, game_name: str = "") -> Dict[str, Any]:
        """查詢特定遊戲在各個已定義 Google Drive 網盤中的補丁狀況與索引資料 (互動時即時連網讀取)"""
        from managers import onlinefix_manager
        try:
            drives = onlinefix_manager.get_cloud_drives()
            # 點擊檢視網盤狀況時，向 Google Drive 發出即時讀取請求
            cache = onlinefix_manager.fetch_cloud_cache(force=True)
            fix_status = onlinefix_manager.get_fix_status(appid)
            is_deployed = onlinefix_manager.is_patch_deployed_locally(appid)
            fix_rec = onlinefix_manager.get_fix_record(appid) or {}

            appid_str = str(appid).strip()
            norm_game_name = re.sub(r'[^a-z0-9]', '', game_name.lower()) if game_name else ""

            result_drives = []
            for idx, d in enumerate(drives):
                d_name = d.get("name", f"網盤 {idx + 1}").strip()
                d_url = d.get("url", "").strip()
                d_prio = d.get("priority", idx + 1)

                # 篩選此網盤中屬於該遊戲的檔案
                matched_files = []
                if cache:
                    for item in cache:
                        # 檢查來源是否為此網盤（依網盤名稱或網址匹配）
                        if item.get("drive_name") == d_name or (d_url and item.get("drive_url") == d_url):
                            f_path = item.get("path", "")
                            f_name = f_path.replace("\\", "/").split("/")[-1]

                            is_match = False
                            if appid_str and appid_str in f_path:
                                is_match = True
                            elif norm_game_name and len(norm_game_name) >= 3:
                                norm_f = re.sub(r'[^a-z0-9]', '', f_path.lower())
                                if norm_game_name in norm_f:
                                    is_match = True

                            if is_match:
                                matched_files.append({
                                    "name": f_name,
                                    "path": f_path,
                                    "id": item.get("id", "")
                                })

                result_drives.append({
                    "priority": d_prio,
                    "name": d_name,
                    "url": d_url,
                    "files": matched_files,
                    "has_patch": len(matched_files) > 0
                })

            return {
                "ok": True,
                "appid": appid_str,
                "game_name": game_name,
                "installed_status": fix_status,
                "is_deployed": is_deployed,
                "installed_source": fix_rec.get("source_drive", ""),
                "has_cache": cache is not None and len(cache) > 0,
                "drives": result_drives
            }
        except Exception as e:
            return {
                "ok": False,
                "msg": str(e),
                "drives": []
            }

    def check_defender_status(self) -> Dict[str, Any]:
        """檢查 Windows Defender 即時保護狀態 (透過註冊表 0 開銷監測)"""
        is_disabled = False
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows Defender\Real-Time Protection", 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, "DisableRealtimeMonitoring")
            is_disabled = (value == 1)
            winreg.CloseKey(key)
        except Exception:
            is_disabled = False
        return {
            "ok": True,
            "is_disabled": is_disabled,
            "is_realtime_on": not is_disabled,
            "status_text": "已關閉 (安全，不干擾破解補丁)" if is_disabled else "開啟中 (建議關閉即時保護以防補丁被誤殺)"
        }

    def open_defender_settings(self) -> Dict[str, Any]:
        """開啟 Windows Defender 安全性中心威脅防護設定頁面"""
        try:
            os.startfile("windowsdefender://threatsettings")
            return {"ok": True, "msg": "已開啟 Defender 安全設定視窗"}
        except Exception as e:
            return {"ok": False, "msg": f"無法開啟 Defender 設定: {e}"}

    def ensure_cloud_config(self) -> Dict[str, Any]:
        """確保雲存檔配置完整"""
        return {"ok": True}

    def get_bg_data(self, name: str) -> str:
        """讀取自訂背景檔案資料 (支援 GIF 動圖完整 Data URL)"""
        p = Path("data/backgrounds") / name
        if not p.exists(): return ""
        try:
            import base64
            ext = p.suffix.lower().lstrip(".")
            mime = "image/gif" if ext == "gif" else (f"image/{ext}" if ext in ["png", "webp"] else "image/jpeg")
            raw = p.read_bytes()
            b64 = base64.b64encode(raw).decode("ascii")
            return f"data:{mime};base64,{b64}"
        except Exception:
            return ""

    def install_default_bgs(self, force: bool = False) -> bool:
        """安裝預設背景"""
        return True

    def open_defender_exclusion_settings(self) -> Dict[str, Any]:
        """一鍵開啟 Windows 安全性中心之病毒與威脅防護排除項設定頁面"""
        try:
            import os
            import subprocess
            try:
                os.startfile("windowsdefender://threatsettings")
                return {"ok": True, "msg": "已為您開啟 Windows Defender 排除項設定頁面"}
            except Exception:
                subprocess.Popen(["start", "windowsdefender://threatsettings"], shell=True)
                return {"ok": True, "msg": "已為您開啟 Windows Defender 排除項設定頁面"}
        except Exception as e:
            return {"ok": False, "msg": f"無法開啟 Windows 設定: {e}"}

    def add_game_folder_to_defender(self, app_id: str = "") -> Dict[str, Any]:
        """呼叫 PowerShell 將指定遊戲目錄加入 Windows Defender 白名單排除項 (自動請求管理員授權)"""
        try:
            import subprocess
            from pathlib import Path
            from managers import onlinefix_manager

            game_dir = None
            if app_id:
                game_dir = onlinefix_manager._find_steam_game_dir(str(app_id))
            if not game_dir or not Path(game_dir).exists():
                return self.open_defender_exclusion_settings()

            p = Path(game_dir).resolve()
            ps_cmd = f"Add-MpPreference -ExclusionPath '{str(p)}'"
            run_cmd = f"Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -Command {ps_cmd}'"
            subprocess.Popen(["powershell", "-NoProfile", "-Command", run_cmd], shell=True)
            return {"ok": True, "msg": f"已彈出系統管理員授權視窗，請點選「是」以將 {p.name} 資料夾新增至防毒白名單！"}
        except Exception as e:
            return {"ok": False, "msg": f"執行排除項失敗: {e}"}

    def get_cloud_metrics(self) -> Dict[str, Any]:
        """獲取 Supabase 雲端資源與 Egress 脫敏用量 (包含雜湊壓縮密文 Token 與明文數據)"""
        try:
            from managers.cloud_metrics_manager import get_cloud_metrics_manager
            return get_cloud_metrics_manager().get_public_cloud_metrics()
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def sync_cloud_metrics(self) -> Dict[str, Any]:
        """房主端更新最新用量並雜湊壓縮加密同步至 Supabase server_metrics 表"""
        try:
            from managers.cloud_metrics_manager import get_cloud_metrics_manager
            return get_cloud_metrics_manager().sync_metrics_to_supabase()
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def decrypt_cloud_metrics(self, token: str) -> Dict[str, Any]:
        """將雜湊壓縮的密文 Token 還原解密為原始用量字典"""
        try:
            from managers.cloud_metrics_manager import get_cloud_metrics_manager
            data = get_cloud_metrics_manager().decrypt_metrics_payload(token)
            if data:
                return {"ok": True, "data": data}
            return {"ok": False, "msg": "解密失敗或資料格式無效"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

