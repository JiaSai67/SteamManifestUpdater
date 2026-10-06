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

class CredentialsHandler:
    def get_credentials_status(self) -> Dict[str, Any]:
        """獲取使用者資訊、Ryuu、HubcapDB 和 Lua.tools 的登入狀態、帳號清單與配額使用資訊"""
        try:
            from managers import account_manager, config_manager, hubcap_manager
            import datetime, time
            mgr = account_manager.get_account_manager()
            mgr.reload_data()

            # 🌟 自動從 Ryuu 官方伺服器同步真實配額 (每 10 秒限制頻率，零額度消耗)
            now = time.time()
            if getattr(self, "_last_ryuu_quota_sync", 0) + 10 < now:
                self._last_ryuu_quota_sync = now
                try:
                    mgr.sync_ryuu_quota_from_server()
                except Exception:
                    pass

            # 1. Ryuu 狀態
            ryuu_accs = mgr.get_accounts("ryuu")
            ryuu_active = mgr.get_active_account("ryuu") or (ryuu_accs[0] if ryuu_accs else None)
            ryuu_logged_in = mgr.has_valid_credentials(ryuu_active, "ryuu") if ryuu_active else False
            ryuu_quota_used = ryuu_active.get("quota_used_today", 0) if ryuu_active else 0
            ryuu_limit = ryuu_active.get("daily_limit", 50) if ryuu_active else 50
            ryuu_name = ryuu_active.get("name", "未登入") if (ryuu_active and ryuu_logged_in) else ("未登入" if not ryuu_active else f"{ryuu_active.get('name', '帳號')} (未授權/過期)")

            # 全域預設 Hubcap Key
            raw_hubcap_key = hubcap_manager.get_api_key()
            default_hubcap_stats = hubcap_manager.fetch_user_stats(raw_hubcap_key) if raw_hubcap_key else {}
            default_hubcap_uid = str(default_hubcap_stats.get("user_id", "")).strip()
            default_hubcap_uname = str(default_hubcap_stats.get("username", "")).strip().lower()

            # 為 Ryuu 帳號清單標註詳細驗證狀態與專屬 Hubcap 狀態
            for acc in ryuu_accs:
                is_val = mgr.has_valid_credentials(acc, "ryuu")
                acc["has_valid_credentials"] = is_val
                acc["is_active"] = bool(ryuu_active and acc.get("id") == ryuu_active.get("id"))
                reset_sec = acc.get("reset_in_seconds")
                reset_str = ""
                if reset_sec and reset_sec > 0:
                    r_h = reset_sec // 3600
                    r_m = (reset_sec % 3600) // 60
                    reset_str = f" ({r_h}h{r_m}m後重設)"

                if not is_val:
                    acc["status_badge"] = "憑證無效"
                elif acc.get("is_exhausted") or (acc.get("quota_used_today", 0) >= acc.get("daily_limit", 50)):
                    acc["status_badge"] = f"配額已滿{reset_str}"
                else:
                    acc["status_badge"] = "正常"

                # 注入該帳號專屬的 Hubcap 狀態
                acc_did = str(acc.get("discord_id", "")).strip()
                acc_id = str(acc.get("id", "")).strip()
                acc_email = str(acc.get("email", "")).strip().lower()
                acc_name = str(acc.get("name", "")).strip().lower()
                h_key = mgr.get_hubcap_key(acc_did) or mgr.get_hubcap_key(acc_id) or mgr.get_hubcap_key(acc_email)

                # 若未單獨綁定，但有全域 Key 且 Discord ID 或 Username 吻合，自動歸屬綁定
                if not h_key and raw_hubcap_key:
                    if (default_hubcap_uid and acc_did == default_hubcap_uid) or (default_hubcap_uname and default_hubcap_uname in acc_name):
                        h_key = raw_hubcap_key
                        mgr.set_hubcap_key(acc_id, raw_hubcap_key, acc_did)

                if h_key:
                    h_stats = hubcap_manager.fetch_user_stats(h_key)
                    acc["hubcap"] = {
                        "is_configured": True,
                        "is_valid": bool(h_stats.get("ok")),
                        "remaining": h_stats.get("remaining", 0),
                        "daily_limit": h_stats.get("daily_limit", 25),
                        "daily_usage": h_stats.get("daily_usage", 0),
                        "api_key_masked": (h_key[:4] + "••••••••" + h_key[-4:]) if len(h_key) > 8 else "••••••••",
                        "error": h_stats.get("error", "")
                    }
                else:
                    acc["hubcap"] = {
                        "is_configured": False,
                        "is_valid": False,
                        "remaining": 0,
                        "daily_limit": 25,
                        "daily_usage": 0,
                        "api_key_masked": "",
                        "error": ""
                    }

            ryuu_left, ryuu_total = mgr.get_total_remaining_quota("ryuu")

            # 2. Lua.tools 狀態
            lt_accs = mgr.get_accounts("lua_tools")
            lt_active = mgr.get_active_account("lua_tools") or (lt_accs[0] if lt_accs else None)
            lt_logged_in = mgr.has_valid_credentials(lt_active, "lua_tools") if lt_active else False
            lt_quota_used = lt_active.get("quota_used_today", 0) if lt_active else 0
            lt_limit = lt_active.get("daily_limit", 25) if lt_active else 25
            lt_name = lt_active.get("name", "未登入") if (lt_active and lt_logged_in) else ("未登入" if not lt_active else f"{lt_active.get('name', '帳號')} (未授權/過期)")

            # 為 Lua.tools 帳號清單標註詳細驗證狀態與專屬 Hubcap 狀態
            for acc in lt_accs:
                is_val = mgr.has_valid_credentials(acc, "lua_tools")
                acc["has_valid_credentials"] = is_val
                acc["is_active"] = bool(lt_active and acc.get("id") == lt_active.get("id"))
                if not is_val:
                    acc["status_badge"] = "憑證無效"
                elif acc.get("is_exhausted"):
                    acc["status_badge"] = "配額已滿"
                else:
                    acc["status_badge"] = "正常"

                acc_did = str(acc.get("discord_id", "")).strip()
                acc_id = str(acc.get("id", "")).strip()
                acc_email = str(acc.get("email", "")).strip().lower()
                acc_name = str(acc.get("name", "")).strip().lower()
                h_key = mgr.get_hubcap_key(acc_did) or mgr.get_hubcap_key(acc_id) or mgr.get_hubcap_key(acc_email)

                # 若未單獨綁定，但有全域 Key 且 Discord ID 或 Username 吻合，自動歸屬綁定
                if not h_key and raw_hubcap_key:
                    if (default_hubcap_uid and acc_did == default_hubcap_uid) or (default_hubcap_uname and default_hubcap_uname in acc_name):
                        h_key = raw_hubcap_key
                        mgr.set_hubcap_key(acc_id, raw_hubcap_key, acc_did)

                if h_key:
                    h_stats = hubcap_manager.fetch_user_stats(h_key)
                    acc["hubcap"] = {
                        "is_configured": True,
                        "is_valid": bool(h_stats.get("ok")),
                        "remaining": h_stats.get("remaining", 0),
                        "daily_limit": h_stats.get("daily_limit", 25),
                        "daily_usage": h_stats.get("daily_usage", 0),
                        "api_key_masked": (h_key[:4] + "••••••••" + h_key[-4:]) if len(h_key) > 8 else "••••••••",
                        "error": h_stats.get("error", "")
                    }
                else:
                    acc["hubcap"] = {
                        "is_configured": False,
                        "is_valid": False,
                        "remaining": 0,
                        "daily_limit": 25,
                        "daily_usage": 0,
                        "api_key_masked": "",
                        "error": ""
                    }

            lt_left, lt_total = mgr.get_total_remaining_quota("lua_tools")

            # 3. 匯總所有帳號的 Hubcap 總額度 (去重計算)
            seen_hubcap_keys = set()
            hubcap_total_left = 0
            hubcap_total_limit = 0
            hubcap_total_used = 0

            for a_list in [ryuu_accs, lt_accs]:
                for a in a_list:
                    ah = a.get("hubcap", {})
                    ak = ah.get("api_key_masked")
                    if ah.get("is_valid") and ak and ak not in seen_hubcap_keys:
                        seen_hubcap_keys.add(ak)
                        hubcap_total_left += ah.get("remaining", 0)
                        hubcap_total_limit += ah.get("daily_limit", 0)
                        hubcap_total_used += ah.get("daily_usage", 0)

            # 4. 使用者個人資料 (User Profile)
            steam_users = self.list_steam_accounts()
            active_steam = steam_users[0] if steam_users else None
            user_name = "Steam 探索者"
            user_sub = "未連結 Steam 帳號"
            user_avatar = ""
            is_steam_linked = False
            steam_id = ""

            if active_steam:
                user_name = active_steam.get("PersonaName") or active_steam.get("AccountName") or "Steam 使用者"
                steam_id = active_steam.get("SteamID", "")
                user_sub = f"Steam ID: {steam_id}" if steam_id else f"帳號: {active_steam.get('AccountName', '')}"
                is_steam_linked = True
            elif ryuu_active and ryuu_logged_in:
                user_name = ryuu_active.get("name", "Discord 授權使用者")
                user_sub = "Discord 授權登入"
            elif lt_active and lt_logged_in:
                user_name = lt_active.get("name", "Discord 授權使用者")
                user_sub = "Discord 授權登入"

            total_quota_available = ryuu_left + hubcap_total_left + lt_left
            total_quota_capacity = ryuu_total + hubcap_total_limit + lt_total

            cfg = config_manager.get_config()
            preferred_source = cfg.get("preferred_source", "auto")
            auto_rotate = mgr.data.get("auto_rotate", True)

            return {
                "ok": True,
                "user_profile": {
                    "name": user_name,
                    "sub": user_sub,
                    "steam_id": steam_id,
                    "is_steam_linked": is_steam_linked,
                    "avatar": user_avatar,
                    "total_quota_available": total_quota_available,
                    "total_quota_capacity": total_quota_capacity
                },
                "ryuu": {
                    "is_logged_in": ryuu_logged_in,
                    "active_account": ryuu_active,
                    "accounts": ryuu_accs,
                    "name": ryuu_name,
                    "quota_used": ryuu_quota_used,
                    "daily_limit": ryuu_limit,
                    "quota_left": max(0, ryuu_limit - ryuu_quota_used) if ryuu_logged_in else 0,
                    "total_quota_left": ryuu_left,
                    "total_quota_limit": ryuu_total
                },
                "hubcap": {
                    "is_configured": bool(seen_hubcap_keys or raw_hubcap_key),
                    "is_valid": hubcap_total_limit > 0 or bool(default_hubcap_stats.get("ok")),
                    "api_key_masked": (raw_hubcap_key[:4] + "••••••••" + raw_hubcap_key[-4:]) if len(raw_hubcap_key) > 8 else "",
                    "daily_limit": hubcap_total_limit or default_hubcap_stats.get("daily_limit", 0),
                    "daily_usage": hubcap_total_used or default_hubcap_stats.get("daily_usage", 0),
                    "remaining": hubcap_total_left or default_hubcap_stats.get("remaining", 0),
                    "resets_at": default_hubcap_stats.get("resets_at", ""),
                    "api_key_expires_at": default_hubcap_stats.get("api_key_expires_at", ""),
                    "can_make_requests": bool(default_hubcap_stats.get("can_make_requests", True)),
                    "error": default_hubcap_stats.get("error", "")
                },
                "lua_tools": {
                    "is_logged_in": lt_logged_in,
                    "active_account": lt_active,
                    "accounts": lt_accs,
                    "name": lt_name,
                    "quota_used": lt_quota_used,
                    "daily_limit": lt_limit,
                    "quota_left": max(0, lt_limit - lt_quota_used) if lt_logged_in else 0,
                    "total_quota_left": lt_left,
                    "total_quota_limit": lt_total
                },
                "settings": {
                    "auto_rotate": auto_rotate,
                    "preferred_source": preferred_source
                }
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_hubcap_api_key(self, api_key: str, target_account_id: str = "") -> Dict[str, Any]:
        """儲存並驗證指定帳號或全域的 HubcapDB API Key"""
        try:
            from managers import hubcap_manager, account_manager
            clean_key = str(api_key or "").strip()
            mgr = account_manager.get_account_manager()
            target_id = str(target_account_id or "").strip()

            if not clean_key:
                if target_id:
                    mgr.set_hubcap_key(target_id, "")
                else:
                    hubcap_manager.set_api_key("")
                return {"ok": True, "msg": "已清除 HubcapDB API Key"}

            # 立即連線驗證
            stats = hubcap_manager.fetch_user_stats(clean_key)
            if stats.get("ok"):
                rem = stats.get("remaining", 0)
                lim = stats.get("daily_limit", 0)
                h_uid = str(stats.get("user_id", "")).strip()
                uname = str(stats.get("username", "")).strip()

                # 綁定至指定帳號或自動關聯之 Discord ID
                bind_target = target_id or h_uid
                if bind_target:
                    mgr.set_hubcap_key(bind_target, clean_key, h_uid)
                # 同步設定主 Key
                if not hubcap_manager.get_api_key() or not target_id:
                    hubcap_manager.set_api_key(clean_key)

                target_tip = f"【{uname}】" if uname else ""
                return {
                    "ok": True,
                    "msg": f"HubcapDB 帳號{target_tip} API Key 驗證成功！可用配額: {rem} / {lim} 次",
                    "stats": stats
                }
            else:
                err = stats.get("error", "金鑰驗證失敗")
                return {"ok": False, "msg": f"API Key 驗證失敗: {err}"}
        except Exception as e:
            return {"ok": False, "msg": f"儲存 HubcapDB 金鑰異常: {e}"}

    def test_credential_connection(self, platform: str) -> Dict[str, Any]:
        """測試指定平台的連線狀態與憑證有效性"""
        try:
            if platform == "ryuu":
                from managers import ryuu_manager
                info = ryuu_manager.fetch_ryuu_manifest_info("480")
                if info.get("error") and "timeout" in str(info.get("error", "")).lower():
                    return {"ok": False, "msg": "Ryuu 官方伺服器連線逾時，請檢查網路代理"}
                return {"ok": True, "msg": "Ryuu 平台連線正常，Manifest 伺服器在線！"}
            elif platform in ("hubcap", "hubcapdb"):
                from managers import hubcap_manager
                return hubcap_manager.test_connection()
            elif platform == "lua_tools":
                import urllib.request
                req = urllib.request.Request("https://lua.tools", headers={"User-Agent": "Mozilla/5.0"})
                try:
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        return {"ok": True, "msg": "Lua.tools 平台連線正常！"}
                except Exception:
                    return {"ok": True, "msg": "Lua.tools 站點可連通"}
            return {"ok": False, "msg": f"未知平台: {platform}"}
        except Exception as e:
            return {"ok": False, "msg": f"連線測試異常: {e}"}

    def save_credential_cookie(self, platform: str, cookie_text: str) -> Dict[str, Any]:
        """手動匯入或更新 Cookie / Token 憑證"""
        try:
            cookie_clean = str(cookie_text).strip()
            if not cookie_clean:
                return {"ok": False, "msg": "憑證內容不能為空"}

            from managers import account_manager
            import sqlite3, time, datetime
            mgr = account_manager.get_account_manager()
            active = mgr.get_active_account(platform)
            if not active:
                acc_id, profile_dir = mgr.create_new_account_profile_dir(platform)
            else:
                acc_id = active.get("id")
                profile_dir = active.get("profile_dir")

            p_dir = Path(profile_dir)
            p_dir.mkdir(parents=True, exist_ok=True)
            cookie_file = p_dir / "Cookies"

            conn = sqlite3.connect(cookie_file)
            cur = conn.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS cookies (
                    creation_utc INTEGER NOT NULL,
                    host_key TEXT NOT NULL,
                    top_frame_site_key TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL,
                    value TEXT NOT NULL,
                    encrypted_value BLOB NOT NULL DEFAULT '',
                    path TEXT NOT NULL DEFAULT '/',
                    expires_utc INTEGER NOT NULL DEFAULT 0,
                    is_secure INTEGER NOT NULL DEFAULT 1,
                    is_httponly INTEGER NOT NULL DEFAULT 1,
                    last_access_utc INTEGER NOT NULL DEFAULT 0,
                    has_expires INTEGER NOT NULL DEFAULT 0,
                    is_persistent INTEGER NOT NULL DEFAULT 1,
                    priority INTEGER NOT NULL DEFAULT 1,
                    samesite INTEGER NOT NULL DEFAULT -1,
                    source_scheme INTEGER NOT NULL DEFAULT 2,
                    source_port INTEGER NOT NULL DEFAULT 443,
                    is_same_party INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (host_key, top_frame_site_key, name, path, source_port)
                )
            ''')

            now_epoch = int((time.time() + 11644473600) * 1000000)
            host = "generator.ryuu.lol" if platform == "ryuu" else "lua.tools"

            if "=" in cookie_clean:
                pairs = cookie_clean.split(";")
                for p in pairs:
                    if "=" in p:
                        k, v = p.strip().split("=", 1)
                        cur.execute('''
                            INSERT OR REPLACE INTO cookies (creation_utc, host_key, name, value, path, is_secure, is_httponly, is_persistent)
                            VALUES (?, ?, ?, ?, '/', 1, 1, 1)
                        ''', (now_epoch, host, k.strip(), v.strip()))
            else:
                key_name = "session" if platform == "ryuu" else "sb-db-auth-token.0"
                cur.execute('''
                    INSERT OR REPLACE INTO cookies (creation_utc, host_key, name, value, path, is_secure, is_httponly, is_persistent)
                    VALUES (?, ?, ?, ?, '/', 1, 1, 1)
                ''', (now_epoch, host, key_name, cookie_clean))

            conn.commit()
            conn.close()

            if not active:
                acc_entry = {
                    "id": acc_id,
                    "platform": platform,
                    "name": f"{platform.upper()} 帳號 (手動匯入)",
                    "profile_dir": str(p_dir),
                    "daily_limit": 50 if platform == "ryuu" else 25,
                    "quota_used_today": 0,
                    "quota_date": datetime.date.today().isoformat(),
                    "is_exhausted": False,
                    "added_time": datetime.datetime.now().isoformat()
                }
                mgr.data.setdefault(platform, []).append(acc_entry)
                if platform == "ryuu":
                    mgr.data["active_account_ryuu"] = acc_id
                else:
                    mgr.data["active_account_lt"] = acc_id
                mgr.save_data()

            return {"ok": True, "msg": f"成功儲存 {platform.upper()} 憑證！"}
        except Exception as e:
            return {"ok": False, "msg": f"儲存憑證失敗: {e}"}

    def clear_credential(self, platform: str) -> Dict[str, Any]:
        """清除指定平台的已存憑證與 Cookie"""
        try:
            from managers import account_manager
            mgr = account_manager.get_account_manager()
            accs = mgr.get_accounts(platform)
            for acc in accs:
                p_dir = Path(acc.get("profile_dir", ""))
                c_file = p_dir / "Cookies"
                if c_file.exists():
                    try: os.remove(c_file)
                    except Exception: pass
            mgr.data[platform] = []
            if platform == "ryuu":
                mgr.data["active_account_ryuu"] = None
            else:
                mgr.data["active_account_lt"] = None
            mgr.save_data()
            return {"ok": True, "msg": f"已清除 {platform.upper()} 的本機登入憑證"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def set_preferred_source(self, source: str) -> bool:
        """
        [已解耦/僅供相容] 設定多源偏好註記。
        注意：核心 Manifest 下載與校驗引擎已全面由 Downloader.js 與 UnifiedManifestManager 固化管線接管
        (Ryuu 優先 -> 自洽性與版本雙重校驗 -> Hubcap 備援熱替換 -> Lua.tools 兜底)，不受此設定干擾。
        """
        try:
            self._config["preferred_source"] = str(source).lower()
            config_manager.save_config(self._config)
            return True
        except Exception:
            return False

    def set_auto_rotate(self, enabled: bool) -> bool:
        """開關多帳號自動輪換"""
        try:
            from managers import account_manager
            mgr = account_manager.get_account_manager()
            mgr.set_auto_rotate(bool(enabled))
            return True
        except Exception:
            return False

    def switch_active_account(self, platform: str, account_id: str) -> Dict[str, Any]:
        """切換指定平台的活躍帳號"""
        try:
            from managers import account_manager
            mgr = account_manager.get_account_manager()
            success = mgr.set_active_account(platform, account_id)
            if success:
                return {"ok": True, "msg": "已切換活躍帳號"}
            return {"ok": False, "msg": "找不到指定的帳號 ID"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def reorder_accounts(self, platform: str, account_ids: List[str]) -> Dict[str, Any]:
        """重新排列指定平台帳號的優先調用順序"""
        try:
            from managers import account_manager
            mgr = account_manager.get_account_manager()
            success = mgr.reorder_accounts(platform, account_ids)
            if success:
                return {"ok": True, "msg": "已更新帳號優先調用順序"}
            return {"ok": False, "msg": "更新順序失敗"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def delete_credential_account(self, platform: str, account_id: str, extra_info: dict = None) -> Dict[str, Any]:
        """刪除指定平台帳號（徹底連根拔起雙平台關聯條目與實體檔案，保證該帳號完全消失不要出現）"""
        try:
            from managers import account_manager
            mgr = account_manager.get_account_manager()
            success = mgr.delete_account_completely(account_id, extra_info=extra_info)
            if success:
                return {"ok": True, "msg": "已成功將該帳號完全刪除！"}
            return {"ok": False, "msg": "找不到指定的帳號"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def clear_all_credential_accounts(self) -> Dict[str, Any]:
        """清空所有平台已綁定之帳號憑證與本機快取檔案"""
        try:
            from managers import account_manager
            mgr = account_manager.get_account_manager()
            success = mgr.clear_all_accounts()
            if success:
                return {"ok": True, "msg": "已成功清空所有平台帳號憑證！"}
            return {"ok": False, "msg": "清空憑證失敗"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def open_discord_login_window(self, platform: str) -> Dict[str, Any]:
        """
        開啟專屬的 Chromium 獨立無痕沙盒授權視窗，引導使用者登入後由系統自動完成身分與 Cookie 綁定。
        """
        try:
            import subprocess
            runner_script = Path(__file__).parent.parent / "ui" / "sandbox_login_runner.py"
            if runner_script.exists():
                plat = "lua_tools" if "lua" in platform.lower() else "ryuu"
                subprocess.Popen(
                    [sys.executable, str(runner_script), "--platform", plat],
                    cwd=str(Path(__file__).parent.parent.parent),
                    creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                )
                return {"ok": True, "msg": f"已啟動 {platform.upper()} 專屬安全沙盒登入視窗！"}

            return {"ok": False, "msg": "找不到沙盒執行器組件"}
        except Exception as e:
            return {"ok": False, "msg": f"啟動登入視窗失敗: {e}"}

    def open_dual_platform_sandbox_login(self) -> Dict[str, Any]:
        """
        開啟獨立無痕安全沙盒視窗，阻斷本機 Discord App 探測，
        支援在同一個乾淨 Session 中一次登入並依序連貫完成 Ryuu (50次) 與 Lua.tools (25次) 雙平台授權。
        """
        try:
            import subprocess
            runner_script = Path(__file__).parent.parent / "ui" / "sandbox_login_runner.py"
            if runner_script.exists():
                subprocess.Popen(
                    [sys.executable, str(runner_script), "--platform", "all"],
                    cwd=str(Path(__file__).parent.parent.parent),
                    creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                )
                return {"ok": True, "msg": "已啟動雙平台連貫安全沙盒登入視窗！"}

            # Fallback: 若 runner 不存在則使用通用子視窗
            return {"ok": False, "msg": "找不到雙平台沙盒執行器組件"}
        except Exception as e:
            return {"ok": False, "msg": f"啟動登入視窗失敗: {e}"}

    def auto_disable_official_cloud(self) -> Dict[str, Any]:
        """自動掃描已安裝之 Lua 入庫遊戲，並於 Steam sharedconfig.vdf 中自動關閉官方雲端以徹底根除報錯"""
        try:
            from managers import steam_cloud_helper
            sp = self._steam_path or steam_manager.find_steam_path()
            if sp:
                return steam_cloud_helper.disable_official_cloud_for_installed_lua_games(Path(sp), only_installed=True)
            return {"ok": False, "msg": "找不到 Steam 目錄"}
        except Exception as e:
            print(f"[WebApi] auto_disable_official_cloud error: {e}")
            return {"ok": False, "msg": str(e)}

    def check_startup_credentials(self) -> Dict[str, Any]:
        """
        每次啟動時自動檢查：
        1. 自動掃描已安裝 Lua 遊戲並關閉官方雲端報錯
        2. Ryuu 與 Lua.tools 憑證狀況
        """
        try:
            # 啟動靜默防護：關閉已安裝 Lua 遊戲的官方雲端開關
            try:
                self.auto_disable_official_cloud()
            except Exception:
                pass

            from managers import account_manager
            mgr = account_manager.get_account_manager()
            return mgr.validate_and_cleanup_all_credentials()
        except Exception as e:
            return {"ok": False, "has_cleaned": False, "error": str(e)}

    def clear_invalid_credentials(self) -> Dict[str, Any]:
        """手動觸發檢查並清理所有無效/過期的憑證檔案"""
        try:
            from managers import account_manager
            mgr = account_manager.get_account_manager()
            return mgr.validate_and_cleanup_all_credentials()
        except Exception as e:
            return {"ok": False, "has_cleaned": False, "error": str(e)}

    def open_hubcap_sandbox_login(self, target_account_id: str = "") -> Dict[str, Any]:
        """
        開啟 HubcapDB 專屬無痕沙盒授權視窗，自動預填已記憶密碼並自動捕獲/綁定 API Key。
        """
        try:
            import subprocess
            runner_script = Path(__file__).parent.parent / "ui" / "sandbox_login_runner.py"
            if runner_script.exists():
                cmd = [sys.executable, str(runner_script), "--platform", "hubcap"]
                if target_account_id:
                    cmd.extend(["--account-id", str(target_account_id)])
                subprocess.Popen(
                    cmd,
                    cwd=str(Path(__file__).parent.parent.parent),
                    creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                )
                return {"ok": True, "msg": "已啟動 HubcapDB 專屬無痕沙盒登入視窗！"}
            return {"ok": False, "msg": "找不到沙盒執行器組件"}
        except Exception as e:
            return {"ok": False, "msg": f"啟動登入視窗失敗: {e}"}

    def relogin_credential_account(self, platform: str, account_id: str) -> Dict[str, Any]:
        """
        針對特定失效帳號開啟專屬沙盒登入視窗，授權完成後自動覆蓋更新該帳號 Cookies / API Key。
        """
        try:
            import subprocess
            runner_script = Path(__file__).parent.parent / "ui" / "sandbox_login_runner.py"
            if runner_script.exists():
                p_lower = str(platform or "").lower()
                if "hubcap" in p_lower:
                    plat = "hubcap"
                elif "lua" in p_lower:
                    plat = "lua_tools"
                else:
                    plat = "ryuu"
                subprocess.Popen(
                    [sys.executable, str(runner_script), "--platform", plat, "--account-id", str(account_id)],
                    cwd=str(Path(__file__).parent.parent.parent),
                    creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                )
                return {"ok": True, "msg": "已開啟該帳號專屬重登視窗，請在完成授權後返回！"}
            return {"ok": False, "msg": "找不到沙盒執行器組件"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def scan_local_discord_accounts(self) -> Dict[str, Any]:
        """已停用：為防範 Discord 帳戶風控與鎖定，本機 Token 掃描已棄置"""
        return {
            "ok": False,
            "msg": "為防範 Discord 帳戶風控與鎖定，本機 Token 一鍵登入已全面停用。請使用 Chromium 獨立沙盒安全自行登入！",
            "accounts": []
        }

    def batch_import_discord_tokens(self, accounts: List[Dict[str, Any]], platforms: List[str] = None) -> Dict[str, Any]:
        """已停用：為防範 Discord 帳戶風控與鎖定，Token 批次登入已棄置"""
        return {
            "ok": False,
            "msg": "為防範 Discord 帳戶風控與鎖定，Token 登入已全面停用。請使用 Chromium 獨立沙盒安全自行登入！"
        }

    def import_discord_token_account(self, platform: str, token: str, display_name: str = "") -> Dict[str, Any]:
        """已停用：為防範 Discord 帳戶風控與鎖定，Token 登入已棄置"""
        return {
            "ok": False,
            "msg": "為防範 Discord 帳戶風控與鎖定，Token 登入已全面停用。請使用 Chromium 獨立沙盒安全自行登入！"
        }

    def open_ryuu_invite(self) -> Dict[str, Any]:
        """使用預設瀏覽器開啟 Ryuu 官方 Discord 伺服器邀請連結"""
        try:
            import webbrowser
            webbrowser.open("https://discord.gg/manifests")
            return {"ok": True, "msg": "已在瀏覽器開啟 Ryuu 官方 Discord 邀請連結 (discord.gg/manifests)"}
        except Exception as e:
            return {"ok": False, "msg": f"開啟連結失敗: {e}"}

    def verify_and_activate_ryuu_account(self, account_id: str) -> Dict[str, Any]:
        """
        直接向 Ryuu 官方網域伺服器 (https://generator.ryuu.lol/api/download_count/{did}) 驗證並同步配額。
        100% 透過網域端點完成，不依賴任何 Discord Token！
        """
        try:
            from managers import account_manager
            mgr = account_manager.get_account_manager()
            mgr.reload_data()
            success = mgr.sync_ryuu_quota_from_server(account_id)

            target = None
            for a in mgr.get_accounts("ryuu"):
                if a.get("id") == account_id:
                    target = a
                    break

            if target:
                left = max(0, target.get("daily_limit", 50) - target.get("quota_used_today", 0))
                return {
                    "ok": True,
                    "msg": f"🎉 網域伺服器同步成功！[{target.get('name')}] 今日剩餘 {left}/50 次額度！"
                }
            return {"ok": True, "msg": "已完成網域伺服器配額同步！"}
        except Exception as e:
            return {"ok": False, "msg": f"網域伺服器驗證異常: {e}"}

    def sync_all_quotas(self) -> Dict[str, Any]:
        """直接主動向各平台官方網域伺服器同步所有帳號之真實剩餘配額"""
        try:
            from managers import account_manager
            mgr = account_manager.get_account_manager()
            mgr.reload_data()
            mgr.sync_all_quotas_from_server()
            return {"ok": True, "msg": "已完成所有帳號網域伺服器配額同步！"}
        except Exception as e:
            return {"ok": False, "msg": f"同步配額失敗: {e}"}

    def open_token_join_server_window(self, account_id_or_token: str = "", display_name: str = "") -> Dict[str, Any]:
        """在瀏覽器中開啟官方 Discord 邀請頁面 (安全無風控)"""
        return self.open_ryuu_invite()

    def bootstrap_game_download(self, appid: str) -> Dict[str, Any]:
        """
        為指定 AppID 部署預引導 ACF 並校準 Manifest，徹底解決 OpenSteamTools 因外部 MRC 伺服器 502/503 崩潰導致 Steam 出現「無網路連線」無法下載的問題。
        """
        ok, msg = steam_manager.ensure_download_bootstrap_acf(appid, steam_path=self._steam_path)
        return {"ok": ok, "msg": msg}

    def get_gas_config(self) -> Dict[str, Any]:
        """取得房主 GAS 網址與範本腳本代碼"""
        try:
            from managers.gas_manager import get_gas_manager
            mgr = get_gas_manager()
            return {
                "ok": True,
                "gas_url": mgr.get_gas_url(),
                "sample_script": mgr.get_sample_script()
            }
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def set_gas_config(self, url: str) -> Dict[str, Any]:
        """保存房主 GAS Web App 網址"""
        try:
            from managers.gas_manager import get_gas_manager
            mgr = get_gas_manager()
            mgr.set_gas_url(url)
            return {"ok": True, "msg": "GAS 網址已保存"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def test_gas_endpoint(self, url: str = "") -> Dict[str, Any]:
        """測試 GAS Web App 是否正常連線"""
        try:
            from managers.gas_manager import get_gas_manager
            return get_gas_manager().test_gas_connection(url)
        except Exception as e:
            return {"ok": False, "msg": f"測試異常: {e}"}

    def clean_gas_space(self, url: str = "") -> Dict[str, Any]:
        """清除房主 Google Drive 上的歷史整合包檔案"""
        try:
            from managers.gas_manager import get_gas_manager
            return get_gas_manager().clean_space(url)
        except Exception as e:
            return {"ok": False, "msg": f"清理空間失敗: {e}"}

    def open_gas_guide_page(self) -> Dict[str, Any]:
        """在預設瀏覽器中直接開啟 GAS 互動式一步一步引導教學網頁"""
        try:
            import webbrowser
            from pathlib import Path
            guide_file = Path(__file__).resolve().parent.parent / "gui" / "gas_guide.html"
            if guide_file.exists():
                webbrowser.open(guide_file.as_uri())
                return {"ok": True}
            return {"ok": False, "msg": "找不到教學網頁檔案"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def launch_chrome_with_gas_extension(self) -> Dict[str, Any]:
        """
        自動啟動 Chrome 瀏覽器並加載專屬 GAS 動態高亮導引擴充套件，直接進入 script.google.com/home
        """
        try:
            import os
            import subprocess
            import shutil
            import winreg
            import webbrowser
            import psutil
            from pathlib import Path

            # 1. 檢查 Chrome 目前是否已在運行
            chrome_running = False
            try:
                chrome_running = any(p.name().lower() == "chrome.exe" for p in psutil.process_iter(['name']))
            except Exception:
                pass

            # 2. 自動探測 Windows Chrome 執行檔路徑
            chrome_candidates = [
                os.path.join(os.environ.get("ProgramFiles", ""), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
            ]

            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as key:
                    reg_val, _ = winreg.QueryValueEx(key, "")
                    if reg_val and os.path.exists(reg_val):
                        chrome_candidates.insert(0, reg_val)
            except Exception:
                pass

            chrome_path = None
            for p in chrome_candidates:
                if p and os.path.exists(p):
                    chrome_path = p
                    break

            if not chrome_path:
                chrome_path = shutil.which("chrome") or shutil.which("google-chrome")

            # 3. 定位擴充套件資料夾 (絕對路徑)
            ext_dir = Path(__file__).resolve().parent.parent / "browser_extension"
            target_url = "https://script.google.com/home"

            # 4. 準備剪貼簿：若 Chrome 已在運行，預先複製高亮腳本方便 F12 Console 一鍵貼上；若非運行則複製 GAS 腳本
            try:
                if chrome_running:
                    content_js_file = ext_dir / "content.js"
                    if content_js_file.exists():
                        self.copy_text(content_js_file.read_text(encoding="utf-8"))
                else:
                    from managers.gas_manager import get_gas_manager
                    sample_code = get_gas_manager().get_sample_script()
                    if sample_code:
                        self.copy_text(sample_code)
            except Exception:
                pass

            # 5. 啟動瀏覽器
            if chrome_path and ext_dir.exists():
                cmd = [
                    chrome_path,
                    f"--load-extension={str(ext_dir.resolve())}",
                    target_url
                ]
                subprocess.Popen(cmd)
                return {
                    "ok": True,
                    "browser": "chrome",
                    "path": chrome_path,
                    "ext_dir": str(ext_dir.resolve()),
                    "chrome_running": chrome_running,
                    "msg": "已為您啟動 Chrome 並嘗試載入導引！"
                }
            else:
                webbrowser.open(target_url)
                return {
                    "ok": True,
                    "browser": "default",
                    "chrome_running": chrome_running,
                    "msg": "未檢測到 Chrome，已使用系統預設瀏覽器開啟 Google Apps Script 首頁"
                }
        except Exception as e:
            return {"ok": False, "msg": f"啟動瀏覽器失敗: {e}"}

    def open_extension_dir(self) -> Dict[str, Any]:
        """在 Windows 檔案總管中開啟 Chrome 引導擴充套件目錄"""
        try:
            import os
            from pathlib import Path
            ext_dir = Path(__file__).resolve().parent.parent / "browser_extension"
            if ext_dir.exists():
                os.startfile(str(ext_dir.resolve()))
                return {"ok": True, "path": str(ext_dir.resolve())}
            return {"ok": False, "msg": "找不到擴充套件目錄"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def open_chrome_extensions_page(self) -> Dict[str, Any]:
        """引導使用者至 Chrome 擴充功能管理頁面"""
        try:
            import subprocess
            import os
            chrome_candidates = [
                os.path.join(os.environ.get("ProgramFiles", ""), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
            ]
            for p in chrome_candidates:
                if p and os.path.exists(p):
                    subprocess.Popen([p, "chrome://extensions"])
                    return {"ok": True}
            return {"ok": False, "msg": "未檢測到 Chrome"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def test_discord_webhook(self, webhook_url: str) -> Dict[str, Any]:
        """測試 Discord Webhook 連線"""
        try:
            from managers.discord_storage import get_discord_storage
            return get_discord_storage().test_webhook(webhook_url)
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def save_discord_webhook(self, webhook_url: str) -> Dict[str, Any]:
        """保存使用者自訂之 Discord Webhook 網址"""
        try:
            from managers.discord_storage import get_discord_storage
            ok = get_discord_storage().set_custom_webhook_url(webhook_url)
            return {"ok": ok, "msg": "Discord Webhook 已成功保存！"}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def get_discord_webhook(self) -> Dict[str, Any]:
        """獲取已保存之 Discord Webhook 網址"""
        try:
            from managers.discord_storage import get_discord_storage
            url = get_discord_storage().get_custom_webhook_url()
            return {"ok": True, "webhook_url": url}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

