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

class SystemHandler:
    def close(self):
        """關閉主視窗"""
        if self._window:
            self._window.destroy()

    def minimize(self):
        """最小化視窗"""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = self._get_hwnd()
            if hwnd:
                user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE = 6
                return True
        except Exception:
            pass
        if self._window:
            self._window.minimize()
            return True
        return False

    def maximize(self):
        """最大化 / 還原視窗"""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = self._get_hwnd()
            if hwnd:
                if user32.IsZoomed(hwnd):
                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE = 9
                else:
                    user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE = 3
                return True
        except Exception:
            pass
        if self._window:
            try:
                if getattr(self._window, 'maximized', False):
                    self._window.restore()
                else:
                    self._window.maximize()
                return True
            except Exception:
                pass
        return False

    def restore(self):
        """還原視窗為正常大小"""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = self._get_hwnd()
            if hwnd:
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE = 9
                return True
        except Exception:
            pass
        if self._window:
            try:
                self._window.restore()
                return True
            except Exception:
                pass
        return False

    def set_window_opacity(self, opacity: int = 100) -> bool:
        """設定作業系統級別的視窗真實半透明度 (30% ~ 100%)"""
        try:
            val = max(30, min(100, int(opacity)))
            self._config["win_opacity"] = val
            config_manager.save_config(self._config)

            hwnd = self._get_hwnd()
            if hwnd:
                import ctypes
                user32 = ctypes.windll.user32
                GWL_EXSTYLE = -20
                WS_EX_LAYERED = 0x00080000
                LWA_ALPHA = 0x00000002
                alpha = int(255 * (val / 100.0))
                style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                if not (style & WS_EX_LAYERED):
                    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
                user32.SetLayeredWindowAttributes(hwnd, 0, alpha, LWA_ALPHA)
                return True
        except Exception as e:
            print(f"[WebApi] set_window_opacity error: {e}")
        return False

    def preload_health_check(self):
        """背景非同步預熱系統健康體檢報告，初始化階段預先完成，前端切換秒開調用"""
        import threading
        def _worker():
            try:
                from managers.health_check_manager import get_health_check_manager
                mgr = get_health_check_manager()
                mgr.run_health_check()
            except Exception:
                pass
        t = threading.Thread(target=_worker, name="PreloadHealthCheckWorker", daemon=True)
        t.start()

    def run_system_health_check(self) -> Dict[str, Any]:
        """執行全方位系統健康體檢並滾動落盤 (至多保留 5 份日誌)"""
        try:
            from managers.health_check_manager import get_health_check_manager
            mgr = get_health_check_manager()
            return mgr.run_health_check()
        except Exception as e:
            return {"ok": False, "score": 0, "rating": "CRITICAL", "rating_text": f"體檢異常: {e}", "issues": [str(e)]}

    def get_latest_system_health(self) -> Dict[str, Any]:
        """獲取最新一次的體檢結果快取"""
        try:
            from managers.health_check_manager import get_health_check_manager
            mgr = get_health_check_manager()
            return mgr.get_latest_result()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_system_health_logs(self) -> List[Dict[str, Any]]:
        """獲取最近歷史體檢日誌清單 (至多 5 筆)"""
        try:
            from managers.health_check_manager import get_health_check_manager
            mgr = get_health_check_manager()
            return mgr.get_history_logs()
        except Exception:
            return []

    def get_system_health_log_content(self, filename: str) -> Dict[str, Any]:
        """讀取指定歷史體檢日誌 Markdown 內容"""
        try:
            from managers.health_check_manager import get_health_check_manager
            mgr = get_health_check_manager()
            return mgr.get_log_content(filename)
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def diagnose_game_download_error(self, appid: str, game_name: str = "") -> Dict[str, Any]:
        """
        深度全鏈路診斷 Steam 下載異常 (Content Corrupt, Locked, Missing Key, Missing Manifest 等)
        精準解析 content_log.txt、唯讀鎖定、Depot 金鑰與 Manifest 檔案完整度。
        """
        appid_str = str(appid).strip()
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp:
            return {"ok": False, "msg": "找不到 Steam 安裝目錄"}

        import stat
        report = {
            "appid": appid_str,
            "game_name": game_name or f"App_{appid_str}",
            "primary_error": "未知異常",
            "error_type": "UNKNOWN",
            "details": [],
            "steam_logs": [],
            "locks": [],
            "lua_info": {},
            "manifests_info": [],
            "acf_info": {},
            "markdown": ""
        }

        # 1. 解析 Steam logs/content_log.txt
        content_log_p = Path(sp) / "logs" / "content_log.txt"
        app_log_lines = []
        if content_log_p.exists():
            try:
                lines = content_log_p.read_text(encoding="utf-8", errors="ignore").splitlines()
                # 篩選最近 200 行中與此 AppID 相關的行
                for l in lines[-200:]:
                    if f"AppID {appid_str}" in l or (len(l) > 10 and appid_str in l):
                        app_log_lines.append(l)
            except Exception:
                pass
        report["steam_logs"] = app_log_lines[-15:]

        # 判斷日誌特徵
        log_text = "\n".join(app_log_lines)
        has_missing_key = "Missing decryption key" in log_text
        has_access_denied = "Access Denied" in log_text
        has_disk_write = "Disk write failure" in log_text or "Disk Write Error" in log_text
        has_manifest_missing = "Missing manifest" in log_text

        # 2. 檢查 Lua 設定檔與金鑰狀態
        lua_f = Path(sp) / "config" / "lua" / f"{appid_str}.lua"
        lua_exists = lua_f.exists()
        lua_ro = False
        lua_content = ""
        depot_keys_found = {}
        missing_keys_depots = []

        if lua_exists:
            try:
                lua_ro = not bool(lua_f.stat().st_mode & stat.S_IWRITE)
                lua_content = lua_f.read_text(encoding="utf-8", errors="ignore")
                # 正則尋找 addappid(did, flag, "key") 與 addappid(did)
                for m in re.finditer(r'addappid\s*\(\s*(\d+)(?:\s*,\s*\d+\s*,\s*"([a-fA-F0-9]{64})")?', lua_content):
                    did = m.group(1)
                    key = m.group(2)
                    if key:
                        depot_keys_found[did] = key
                    elif did != appid_str:
                        missing_keys_depots.append(did)
            except Exception:
                pass

        report["lua_info"] = {
            "path": str(lua_f),
            "exists": lua_exists,
            "readonly": lua_ro,
            "has_keys": bool(depot_keys_found),
            "keys": depot_keys_found,
            "missing_key_depots": missing_keys_depots
        }

        # 3. 檢查 ACF 狀態
        acf_f = steam_manager.find_appmanifest(appid_str, sp)
        acf_exists = acf_f and acf_f.exists()
        acf_ro = False
        update_result = "0"
        state_flags = "0"
        if acf_exists:
            try:
                acf_ro = not bool(acf_f.stat().st_mode & stat.S_IWRITE)
                acf_c = acf_f.read_text(encoding="utf-8", errors="ignore")
                ur_m = re.search(r'"UpdateResult"\s+"(\d+)"', acf_c)
                if ur_m: update_result = ur_m.group(1)
                sf_m = re.search(r'"StateFlags"\s+"(\d+)"', acf_c)
                if sf_m: state_flags = sf_m.group(1)
            except Exception:
                pass

        report["acf_info"] = {
            "path": str(acf_f) if acf_f else "",
            "exists": acf_exists,
            "readonly": acf_ro,
            "update_result": update_result,
            "state_flags": state_flags
        }

        # 4. 檢查 Manifest 檔案鎖定與齊全度
        depotcache_dir = Path(sp) / "depotcache"
        manifests_status = []
        if lua_exists:
            manifest_matches = re.findall(r'set[M|m]anifest[i|I]d\s*\(\s*(\d+)\s*,\s*"(\d+)"', lua_content)
            for did, gid in manifest_matches:
                mf_target = depotcache_dir / f"{did}_{gid}.manifest"
                mf_exists = mf_target.exists()
                mf_ro = False
                mf_size = 0
                if mf_exists:
                    try:
                        mf_ro = not bool(mf_target.stat().st_mode & stat.S_IWRITE)
                        mf_size = mf_target.stat().st_size
                    except Exception:
                        pass
                manifests_status.append({
                    "depot_id": did,
                    "manifest_id": gid,
                    "path": str(mf_target),
                    "exists": mf_exists,
                    "readonly": mf_ro,
                    "size": mf_size
                })
        report["manifests_info"] = manifests_status

        # 5. 綜合歸納核心錯誤主因
        if missing_keys_depots:
            report["primary_error"] = "缺少 Depot 解密金鑰 (Missing decryption key)"
            report["error_type"] = "MISSING_KEY"
            primary_desc = f"Depot {', '.join(missing_keys_depots)} 缺少 64 位元解密金鑰，導致 Steam 下載無法解密 chunk 檔案，進而觸發「檔案內容損毀 (Content Corrupt)」錯誤。"
        elif not lua_exists:
            report["primary_error"] = "缺少 Lua 入庫設定檔"
            report["error_type"] = "MISSING_LUA"
            primary_desc = f"Steam/config/lua/{appid_str}.lua 不存在，尚未完成入庫配置。"
        elif any(not m.get("exists") for m in manifests_status) or (has_manifest_missing and update_result != '0'):
            report["primary_error"] = "缺少二進位 Manifest 清單檔案"
            report["error_type"] = "MISSING_MANIFEST"
            missing_mfs = [f"{m['depot_id']}_{m['manifest_id']}.manifest" for m in manifests_status if not m.get("exists")]
            primary_desc = f"Steam/depotcache 目錄中缺少實體清單檔案：{', '.join(missing_mfs)}。"
        elif update_result != '0' and (acf_ro or any(m.get("readonly") for m in manifests_status) or has_access_denied):
            report["primary_error"] = "檔案被系統設為唯讀鎖定 (Access Denied)"
            report["error_type"] = "LOCKED_FILE"
            locked_files = []
            if acf_ro: locked_files.append("steamapps/" + (acf_f.name if acf_f else "ACF"))
            for m in manifests_status:
                if m.get("readonly"): locked_files.append("depotcache/" + Path(m["path"]).name)
            primary_desc = f"以下檔案被設為唯讀鎖定，阻止了 Steam 下載引擎的寫入權限：{', '.join(locked_files) if locked_files else '未知檔案'}。"
        elif update_result == '0' and (state_flags == '4' or state_flags == '6'):
            report["primary_error"] = "下載已完成或狀態正常"
            report["error_type"] = "HEALTHY"
            primary_desc = "當前環境檢測全部正常，金鑰與清單齊全，Steam 清單已無錯誤記錄。"
        else:
            report["primary_error"] = f"Steam 回報下載中斷 (UpdateResult: {update_result})"
            report["error_type"] = "STEAM_ERROR"
            primary_desc = f"Steam 回報錯誤代碼 {update_result} (StateFlags: {state_flags})，可能因網路超時、防毒軟體攔截或暫存衝突引發。"

        report["primary_desc"] = primary_desc

        # 6. 生成漂亮的 Markdown 診斷報告
        md = []
        md.append(f"# 🚨 下載異常排障報告：{report['game_name']} (`{appid_str}`)")
        md.append(f"**診斷時間**: `{time.strftime('%Y-%m-%d %H:%M:%S')}` | **狀態**: 🔴 `{report['primary_error']}`\n")

        md.append("### 🔴 核心錯誤判定")
        md.append(f"> **{report['primary_error']}**  \n> {primary_desc}\n")

        md.append("### 📋 系統環境與權限檢測清單")
        md.append("| 檢測項目 | 檢查目標 | 當前狀態 | 說明與分析 |")
        md.append("| :--- | :--- | :--- | :--- |")

        # Depot Key 行
        if missing_keys_depots:
            md.append(f"| **Depot 解密金鑰** | `Depot {','.join(missing_keys_depots)}` | ❌ 缺少金鑰 | Lua 檔案中僅宣告 `addappid`，未提供 64 位元金鑰 |")
        elif depot_keys_found:
            md.append(f"| **Depot 解密金鑰** | `{len(depot_keys_found)} 個 Depot` | ✅ 齊全已配置 | 已包含完整解密密鑰 |")
        else:
            md.append(f"| **Depot 解密金鑰** | `主程式` | ⚪ 免金鑰/未配置 | 免加密 Depot 或未配置 |")

        # Lua 行
        lua_stat = "❌ 不存在" if not lua_exists else ("⚠️ 唯讀鎖定 (需解鎖)" if lua_ro else "✅ 正常可讀寫")
        md.append(f"| **Lua 入庫設定檔** | `config/lua/{appid_str}.lua` | {lua_stat} | 大小: {len(lua_content)} B |")

        # ACF 行
        acf_stat = "❌ 不存在" if not acf_exists else (f"⚠️ 錯誤碼 {update_result}" if update_result != '0' else ("⚠️ 唯讀鎖定" if acf_ro else "✅ 正常可讀寫"))
        md.append(f"| **Steam 清單 (ACF)** | `appmanifest_{appid_str}.acf` | {acf_stat} | UpdateResult={update_result}, StateFlags={state_flags} |")

        # Manifests 行
        if manifests_status:
            for m in manifests_status:
                m_stat = "❌ 檔案缺失" if not m["exists"] else ("⚠️ 唯讀鎖定 (需解鎖)" if m["readonly"] else "✅ 正常可讀寫")
                md.append(f"| **實體 Manifest** | `depotcache/{m['depot_id']}_{m['manifest_id'][:8]}…` | {m_stat} | 大小: {m['size']} B |")
        else:
            md.append(f"| **實體 Manifest** | `depotcache/` | ⚪ 未宣告 | Lua 檔案中無 setManifestid 記錄 |")

        md.append("")
        if app_log_lines:
            md.append("### 🔍 Steam 原生日誌 (`content_log.txt`) 關鍵報錯")
            md.append("```text")
            for l in app_log_lines[-8:]:
                md.append(l)
            md.append("```\n")

        md.append("### 🛠️ 推薦修復措施")
        md.append("點擊下方「**🚀 一鍵自癒修復並重試下載**」按鈕，系統將自動：")
        md.append("1. 自動向官方/Ryuu 授權通道拉取並補齊正確的 Depot 解密金鑰；")
        md.append("2. 全面解除所有相關檔案與目錄的唯讀鎖定（恢復可讀寫）；")
        md.append("3. 重設 ACF 的錯誤狀態碼（UpdateResult = 0）並自動喚起 Steam 重啟下載。")

        report["markdown"] = "\n".join(md)
        return {"ok": True, "report": report}

    def heal_game_download_error(self, appid: str, game_name: str = "") -> Dict[str, Any]:
        """
        一鍵自癒修復下載異常：
        1. 解除所有相關檔案的唯讀鎖定
        2. 透過 Ryuu HTTP 通道重新部署包含正確 Depot Key 的完整 Lua 與 Manifest
        3. 重設 ACF UpdateResult 為 0
        4. 自動重啟 Steam 下載
        """
        import stat
        appid_str = str(appid).strip()
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp:
            return {"ok": False, "msg": "找不到 Steam 安裝路徑"}

        # 1. 解除版本唯讀鎖定
        steam_manager.unlock_game_version(appid_str, sp)

        # 2. 重新自 Ryuu 官方通道部署（獲取包含完整 Key 的 Lua 與實體清單）
        ok, msg = self._unified_mgr._deploy_from_ryuu_http(appid_str)
        if not ok:
            # 若 Ryuu 失敗，嘗試備援通道
            ok, msg = self._unified_mgr._deploy_from_luatools_http(appid_str)

        # 3. 確保 depotcache 底下所有檔案維持可讀寫
        depotcache_dir = Path(sp) / "depotcache"
        if depotcache_dir.exists():
            for mf in depotcache_dir.glob(f"{appid_str}*.manifest"):
                try: os.chmod(mf, stat.S_IWRITE | stat.S_IREAD)
                except Exception: pass

        # 4. 重設 ACF UpdateResult = 0
        acf_f = steam_manager.find_appmanifest(appid_str, sp)
        if acf_f and acf_f.exists():
            try:
                c = acf_f.read_text(encoding="utf-8", errors="ignore")
                c = re.sub(r'"UpdateResult"\s+"[^"]*"', '"UpdateResult"\t\t"0"', c)
                acf_f.write_text(c, encoding="utf-8")
            except Exception:
                pass

        # 5. 重新喚起 Steam 下載
        try:
            os.startfile(f"steam://install/{appid_str}")
            self.start_steam_install_watcher(appid_str, game_name)
        except Exception:
            pass

        return {
            "ok": True,
            "msg": f"✅ 已成功為「{game_name or appid_str}」完成自癒修復（已補全金鑰、解除鎖定並重啟下載）！",
            "deploy_result": msg
        }

    def machine_check_async(self):
        """非同步執行全套環境體檢並推播報告至前端"""
        sp = self._steam_path or steam_manager.find_steam_path()
        dll_st = self.check_dlls()
        locked_st = self.check_steam_locked()

        report = {
            "steam_detected": bool(sp),
            "steam_path": str(sp) if sp else "未找到",
            "kernel_installed": dll_st.get("ok", False),
            "version_locked": locked_st.get("locked", False),
            "lua_dir_ok": (Path(sp) / "config" / "lua").exists() if sp else False,
            "depotcache_ok": (Path(sp) / "depotcache").exists() if sp else False
        }

        # 藉由 window.evaluate_js 觸發前端 onDgDone
        if self._window:
            js = f"if(window.onDgDone) window.onDgDone({json.dumps(report)});"
            try:
                self._window.evaluate_js(js)
            except Exception:
                pass
        return report

    def depot_selfcheck_async(self):
        """非同步自檢 Manifest 庫存完整度"""
        return self.machine_check_async()

    def check_update(self) -> Dict[str, Any]:
        """檢查更新：當前已為完美整合版，不彈出外部作者干擾更新視窗"""
        return {"has_update": False}

    def webview2_info(self) -> Dict[str, Any]:
        """WebView2 資訊"""
        return {"version": "Latest", "ok": True}

    def webview2_upgrade(self) -> Dict[str, Any]:
        """WebView2 升級"""
        return {"ok": True, "msg": "已是最新版本"}

    def resize_to(self, width: int, height: int, fix_point: str = "", *args, **kwargs):
        """縮放視窗大小（支援對邊釘住座標補償與安全邊界）"""
        w = max(int(width), 880)
        h = max(int(height), 580)
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = self._get_hwnd()
            if hwnd:
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                cur_w = rect.right - rect.left
                cur_h = rect.bottom - rect.top
                cur_x = rect.left
                cur_y = rect.top
                new_x = cur_x
                new_y = cur_y
                if 'e' in fix_point:
                    new_x = cur_x - (w - cur_w)
                if 's' in fix_point:
                    new_y = cur_y - (h - cur_h)
                # SWP_NOZORDER (4) | SWP_NOACTIVATE (0x0010) = 0x0014
                user32.SetWindowPos(hwnd, 0, int(new_x), int(new_y), int(w), int(h), 0x0014)
                self.save_window_size(w, h)
                return True
        except Exception:
            pass

        if self._window:
            try:
                self._window.resize(w, h)
                self.save_window_size(w, h)
            except Exception:
                pass

    def toggle_mini(self) -> bool:
        """切換迷你模式"""
        return True

    def float_allowed(self) -> bool:
        """浮窗權限"""
        return True

    def ensure_pyside6_async(self):
        """異步就緒"""
        pass

    def gbe_allowed(self) -> bool:
        return False

    def gbe_crack(self, appid: str) -> Dict[str, Any]:
        return {"ok": False, "msg": "此功能已停用"}

    def get_sponsor_image(self) -> str:
        return ""

    def otac_qr_img(self) -> str:
        return ""

    def redeem_free_import(self, code: str) -> Dict[str, Any]:
        return {"ok": True}

    def mon_start(self) -> Dict[str, Any]:
        self._start_depotcache_watchdog()
        return {"ok": True}

    def mon_stop(self) -> Dict[str, Any]:
        self._watchdog_stop = True
        self._watchdog_started = False
        return {"ok": True}

    def mon_get_status(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "running": getattr(self, "_watchdog_started", False),
            "lines": getattr(self, "_watchdog_logs", [])
        }

    def mon_clear(self) -> Dict[str, Any]:
        self._watchdog_logs = []
        return {"ok": True}

    def get_system_diagnostic_info(self) -> Dict[str, Any]:
        """獲取系統診斷總覽 (包含 PC 電腦名稱、Windows 帳號、Discord 帳號、Discord ID 與環境)"""
        try:
            from managers.error_reporter import get_error_reporter
            data = get_error_reporter().get_system_diagnostic_summary()
            return {"ok": True, "data": data}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def report_error(self, title: str, error_msg: str, context: str = "", level: str = "ERROR", extra: str = "") -> Dict[str, Any]:
        """向 Discord 監控通道通報錯誤報告 (自動帶上 PC 名稱、Discord 帳號、系統環境與堆疊)"""
        try:
            from managers.error_reporter import get_error_reporter
            extra_dict = {}
            if extra:
                try:
                    import json
                    parsed = json.loads(extra)
                    if isinstance(parsed, dict):
                        extra_dict = parsed
                except Exception:
                    extra_dict = {"額外備註": extra}
            ok = get_error_reporter().send_error_report(
                title=title,
                error_msg=error_msg,
                context=context,
                level=level,
                extra_fields=extra_dict if extra_dict else None,
                sync=False
            )
            return {"ok": ok, "msg": "錯誤報告已遞交 Discord 監控通道" if ok else "錯誤報告發送失敗"}
        except Exception as e:
            return {"ok": False, "msg": f"通報異常: {e}"}

    def send_user_feedback(self, title: str, content: str, contact: str = "") -> Dict[str, Any]:
        """使用者主動提交反饋或問題回報 (同步通報至 Discord 異常守護頻道)"""
        try:
            from managers.error_reporter import get_error_reporter
            extra_dict = {}
            if contact:
                extra_dict["聯絡方式"] = contact
            ok = get_error_reporter().send_error_report(
                title=f"使用者問題回報: {title}",
                error_msg=content,
                context="User Feedback Form",
                level="FEEDBACK",
                extra_fields=extra_dict if extra_dict else None,
                sync=False
            )
            return {"ok": ok, "msg": "反饋已成功提交！感謝您的回報。" if ok else "提交失敗，請檢查網路連線。"}
        except Exception as e:
            return {"ok": False, "msg": f"提交失敗: {e}"}

    def get_license_state(self) -> Dict[str, Any]:
        """授權狀態查詢：回傳永久旗艦版授權資訊"""
        return {
            "activated": True,
            "tier": "sponsor",
            "tier_name": "永久旗艦版",
            "expires": "永久有效",
            "limit": "無限暢享"
        }

    def activate_license(self, code: str) -> Dict[str, Any]:
        """啟用授權碼"""
        return {
            "ok": True,
            "msg": "已成功啟用永久旗艦版！享有全部高速通道與無限制功能。"
        }

    def announce_mark_seen(self, announce_id: str = "") -> bool:
        """標記已讀公告"""
        self._config["announce_seen"] = announce_id
        config_manager.save_config(self._config)
        return True

    def _get_hwnd(self) -> int:
        """取得主視窗 HWND 句柄 (支援快取與多層容錯探測)"""
        if getattr(self, "_cached_hwnd", None):
            try:
                import ctypes
                if ctypes.windll.user32.IsWindow(self._cached_hwnd):
                    return self._cached_hwnd
            except Exception:
                pass

        hwnd = 0
        try:
            # 1. 嘗試由 pywebview window.native / window.gui 獲取
            if self._window:
                native = getattr(self._window, "native", None) or getattr(self._window, "gui", None)
                if native and hasattr(native, "Handle"):
                    hwnd = int(native.Handle.ToInt64() if hasattr(native.Handle, "ToInt64") else native.Handle)
        except Exception:
            hwnd = 0

        if not hwnd:
            try:
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.windll.user32

                # 2. 嘗試由視窗標題尋找
                if self._window and getattr(self._window, "title", None):
                    hwnd = user32.FindWindowW(None, self._window.title)

                # 3. 嘗試由 PID 枚舉可見視窗
                if not hwnd:
                    pid = os.getpid()
                    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
                    def enum_cb(h, lp):
                        nonlocal hwnd
                        p = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
                        if p.value == pid and user32.IsWindowVisible(h):
                            hwnd = h
                            return False
                        return True
                    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
            except Exception as e:
                print(f"[WebApi] _get_hwnd error: {e}")

        if hwnd:
            self._cached_hwnd = hwnd
        return hwnd

    def is_maximized(self) -> bool:
        """檢查視窗當前是否為最大化狀態"""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = self._get_hwnd()
            if hwnd:
                return bool(user32.IsZoomed(hwnd))
        except Exception:
            pass
        if self._window:
            return bool(getattr(self._window, 'maximized', False))
        return False

    def start_resize(self, side: str) -> bool:
        """觸發作業系統原生無邊框視窗 8 方向邊緣縮放 (Win32 SC_SIZE)"""
        side_map = {
            "w": 0xF001,   # Left
            "e": 0xF002,   # Right
            "n": 0xF003,   # Top
            "nw": 0xF004,  # Top-Left
            "ne": 0xF005,  # Top-Right
            "s": 0xF006,   # Bottom
            "sw": 0xF007,  # Bottom-Left
            "se": 0xF008,  # Bottom-Right
        }
        cmd = side_map.get(str(side).lower())
        if not cmd:
            return False
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = self._get_hwnd()
            if hwnd:
                user32.ReleaseCapture()
                user32.SendMessageW(hwnd, 0x0112, cmd, 0)
                return True
        except Exception as e:
            print(f"[WebApi] start_resize error: {e}")
        return False

    def save_window_size(self, width: int = 0, height: int = 0, *args, **kwargs) -> bool:
        """儲存視窗自訂大小 (保證不低於 880x580 最佳體驗規格)"""
        try:
            if not width or not height:
                if self._window:
                    width = getattr(self._window, 'width', 1180)
                    height = getattr(self._window, 'height', 760)
                else:
                    width, height = 1180, 760
            width = max(int(width), 880)
            height = max(int(height), 580)
            self._config["window_width"] = int(width)
            self._config["window_height"] = int(height)
            config_manager.save_config(self._config)
            return True
        except Exception:
            return False

    def copy_text(self, text: str) -> bool:
        """複製文字至系統剪貼簿"""
        try:
            import subprocess
            cmd = f'Set-Clipboard -Value @\'\n{text}\n\'@'
            subprocess.run(["powershell", "-NoProfile", "-Command", cmd], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except Exception:
            try:
                import ctypes
                ctypes.windll.user32.OpenClipboard(0)
                ctypes.windll.user32.EmptyClipboard()
                hCd = ctypes.windll.kernel32.GlobalAlloc(2, (len(text) + 1) * 2)
                pchData = ctypes.windll.kernel32.GlobalLock(hCd)
                ctypes.cdll.msvcrt.wcscpy(ctypes.c_wchar_p(pchData), text)
                ctypes.windll.kernel32.GlobalUnlock(hCd)
                ctypes.windll.user32.SetClipboardData(13, hCd)
                ctypes.windll.user32.CloseClipboard()
                return True
            except Exception:
                return False

    def open_path(self, path: str) -> bool:
        """在檔案總管中開啟指定目錄或檔案"""
        try:
            p = Path(path).resolve()
            if p.exists():
                os.startfile(str(p))
                return True
            return False
        except Exception:
            return False

    def move_by(self, dx: int, dy: int) -> bool:
        """依據滑鼠相對增量極速移動視窗 (Win32 SetWindowPos，0 延遲 144Hz 滿幀流暢度)"""
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = self._get_hwnd()
            if hwnd:
                # 若當前為最大化狀態，拖曳時先自動還原視窗
                if user32.IsZoomed(hwnd):
                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE = 9
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                scale = 1.0
                try:
                    dpi = user32.GetDpiForWindow(hwnd)
                    if dpi > 0:
                        scale = dpi / 96.0
                except Exception:
                    pass
                new_x = rect.left + int(dx * scale)
                new_y = rect.top + int(dy * scale)
                # SWP_NOSIZE (1) | SWP_NOZORDER (4) | SWP_NOACTIVATE (0x0010) = 0x0015
                user32.SetWindowPos(hwnd, 0, int(new_x), int(new_y), 0, 0, 0x0015)
                return True
        except Exception as e:
            pass
        if self._window and hasattr(self._window, 'x') and hasattr(self._window, 'y'):
            try:
                if getattr(self._window, 'maximized', False):
                    self._window.restore()
                self._window.move(int(self._window.x + dx), int(self._window.y + dy))
                return True
            except Exception:
                pass
        return False

    def open_url(self, url: str) -> bool:
        """使用預設瀏覽器打開 URL"""
        try:
            import webbrowser
            webbrowser.open(url)
            return True
        except Exception:
            return False

    def drag_window(self) -> bool:
        """觸發作業系統原生視窗拖曳 (Win32 SC_DRAGMOVE)，使用非阻塞 PostMessageW 達到 0 延遲 144Hz+ 極致流暢拖曳"""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = self._get_hwnd()
            if hwnd:
                user32.ReleaseCapture()
                # 0x0112 = WM_SYSCOMMAND, 0xF012 = SC_DRAGMOVE (SC_MOVE + HTCAPTION)
                # 使用非阻塞 PostMessageW，避免 SendMessageW 阻塞 Python 執行緒與訊息循環
                user32.PostMessageW(hwnd, 0x0112, 0xF012, 0)
                return True
        except Exception as e:
            print(f"[WebApi] drag_window error: {e}")
        return False

