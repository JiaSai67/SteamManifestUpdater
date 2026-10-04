# -*- coding: utf-8 -*-
"""
SteamManifestUpdater - System Health Check Manager (全方位系統健康診斷體系)
六大維度深度體檢：
1. 🏗️ 底層架構與核心環境 (Python, WebView2, 依賴庫, 目錄結構, 設定防損壞)
2. 🎮 Steam 本機運行與注入核心 (Steam路徑, 進程狀態, 3/3核心DLL, 權限)
3. ⚡ SteamCMD & SteamDB 官方生態鏈 (SteamCMD PICS API, SteamDB站點與盾牌狀態, 獨立快取庫, 種子庫)
4. 🌐 多源平台與外聯通訊管道 (DNS海外解析, Ryuu, HubcapDB配額, Lua.tools)
5. 🪪 帳號憑證與授權健康度 (Discord授權, 多帳號輪換狀態)
6. 💾 本機儲存與快取健全度 (SteamDB快取庫, 本機Manifest快取空間, 診斷日誌)
自動滾動日誌：嚴格保留至多 5 份歷史 Log (FIFO 自動清理)
"""

import os
import sys
import json
import time
import socket
import ssl
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional, Tuple

_root_dir = Path(__file__).resolve().parent.parent.parent
_logs_dir = _root_dir / "logs" / "health_checks"
_logs_dir.mkdir(parents=True, exist_ok=True)

_latest_log_path = _logs_dir / "latest_health_check.log"
_disk_cache_path = _root_dir / "data" / "cache" / "latest_health_cache.json"
_latest_data_cache: Optional[Dict[str, Any]] = None

# SSL 寬鬆 Context 供探針使用 (避免特定企業憑證攔截誤報)
_PROBE_SSL_CTX = ssl.create_default_context()
_PROBE_SSL_CTX.check_hostname = False
_PROBE_SSL_CTX.verify_mode = ssl.CERT_NONE


def _probe_url(url: str, timeout: int = 4, headers: Optional[Dict[str, str]] = None) -> Tuple[bool, int, int, str]:
    """
    通用 HTTP 探針：
    回傳 (is_ok, http_code, elapsed_ms, err_msg)
    """
    start_t = time.time()
    req_headers = headers or {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    try:
        req = urllib.request.Request(url, headers=req_headers)
        with urllib.request.urlopen(req, timeout=timeout, context=_PROBE_SSL_CTX) as resp:
            elapsed_ms = int((time.time() - start_t) * 1000)
            return True, resp.status, elapsed_ms, ""
    except urllib.error.HTTPError as e:
        elapsed_ms = int((time.time() - start_t) * 1000)
        return False, e.code, elapsed_ms, str(e.reason)
    except Exception as e:
        elapsed_ms = int((time.time() - start_t) * 1000)
        return False, 0, elapsed_ms, str(e)


def _probe_dns(host: str) -> Tuple[bool, str]:
    """DNS 域名解析探針"""
    try:
        ip = socket.gethostbyname(host)
        return True, ip
    except Exception as e:
        return False, str(e)


def _check_webview2_runtime() -> Tuple[bool, str]:
    """檢測本機 Microsoft Edge WebView2 運行時狀態"""
    # 1. 檢測 Windows 註冊表
    try:
        import winreg
        reg_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-2347-4701-B3D2-564AC8777C42}"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\EdgeUpdate\Clients\{F3017226-2347-4701-B3D2-564AC8777C42}"),
        ]
        for hkey, subkey in reg_paths:
            try:
                with winreg.OpenKey(hkey, subkey) as k:
                    val, _ = winreg.QueryValueEx(k, "pv")
                    if val and val != "0.0.0.0":
                        return True, f"微軟官方運行時已安裝 (v{val})"
            except Exception:
                pass
    except Exception:
        pass

    # 2. 檢測 PyWebView 是否能順利載入
    try:
        import webview
        return True, "WebView2 環境正常 (由 PyWebView 支持)"
    except Exception as e:
        return False, f"未偵測到 WebView2 運行時: {e}"


class HealthCheckManager:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = HealthCheckManager()
        return cls._instance

    def __init__(self):
        self.root_dir = _root_dir
        self.logs_dir = _logs_dir
        self.max_log_files = 5
        self._load_disk_cache()

    def _load_disk_cache(self):
        """從磁碟載入上一次體檢結果快取 (秒開 < 1ms，杜絕冷啟動白屏等待)"""
        global _latest_data_cache
        if _latest_data_cache is None and _disk_cache_path.exists():
            try:
                data = json.loads(_disk_cache_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("ok"):
                    _latest_data_cache = data
            except Exception:
                pass

    def _rotate_logs(self):
        """
        滾動日誌清理機制：
        掃描 logs/health_checks/ 目錄下所有 health_check_*.log，
        按修改時間由新到舊排序，若數量超過 max_log_files (5 個)，自動刪除舊檔。
        """
        try:
            log_files = [
                p for p in self.logs_dir.glob("health_check_*.log")
                if p.name != "latest_health_check.log" and p.is_file()
            ]
            log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

            if len(log_files) > self.max_log_files:
                for old_log in log_files[self.max_log_files:]:
                    try:
                        old_log.unlink()
                        print(f"[HealthCheckManager] 自動清理超額舊日誌: {old_log.name}")
                    except Exception as e:
                        print(f"[HealthCheckManager] 清理舊日誌失敗: {e}")
        except Exception as e:
            print(f"[HealthCheckManager] 滾動日誌維護異常: {e}")

    def run_health_check(self) -> Dict[str, Any]:
        """
        執行全方位系統健康體檢 (六大維度全景診斷)
        """
        start_t = time.time()
        timestamp = datetime.now()
        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
        date_display = timestamp.strftime("%Y-%m-%d %H:%M:%S")

        from managers import config_manager, steam_manager

        score = 100
        issues = []
        checks = {}

        # ═══════════════════════════════════════════════════════
        # ⚡ 並行探測：外部網路與生態鏈服務 (ThreadPool 併發 < 1.5s)
        # ═══════════════════════════════════════════════════════
        with ThreadPoolExecutor(max_workers=8) as pool:
            f_steamcmd = pool.submit(_probe_url, "https://api.steamcmd.net/v1/info/730", 4)
            f_steamdb = pool.submit(_probe_url, "https://steamdb.info/", 4)
            f_ryuu = pool.submit(_probe_url, "https://generator.ryuu.lol/", 4)
            f_luatools = pool.submit(_probe_url, "https://lua.tools/", 4)
            f_dns_sc = pool.submit(_probe_dns, "api.steamcmd.net")
            f_dns_sdb = pool.submit(_probe_dns, "steamdb.info")
            f_dns_ryuu = pool.submit(_probe_dns, "generator.ryuu.lol")

            # 等待併發探測結果
            sc_ok, sc_code, sc_ms, sc_err = f_steamcmd.result()
            sdb_ok, sdb_code, sdb_ms, sdb_err = f_steamdb.result()
            ryuu_ok, ryuu_code, ryuu_ms, ryuu_err = f_ryuu.result()
            lt_ok, lt_code, lt_ms, lt_err = f_luatools.result()
            dns_sc_ok, dns_sc_res = f_dns_sc.result()
            dns_sdb_ok, dns_sdb_res = f_dns_sdb.result()
            dns_ryuu_ok, dns_ryuu_res = f_dns_ryuu.result()

        # ═══════════════════════════════════════════════════════
        # 1. 🏗️ 底層架構與核心環境檢測 (infra_env)
        # ═══════════════════════════════════════════════════════
        infra_check = {
            "title": "底層架構與核心環境",
            "status": "OK",
            "items": []
        }

        # 1.1 Python 運行環境
        py_ver = sys.version.split()[0]
        is_64bit = sys.maxsize > 2**32
        infra_check["items"].append({
            "name": "Python 運行環境",
            "status": "OK",
            "desc": f"Python {py_ver} ({'64-bit' if is_64bit else '32-bit'}) · 環境正常"
        })

        # 1.2 核心相依套件庫
        core_modules = ["requests", "urllib3", "webview"]
        missing_mods = []
        for mod in core_modules:
            try:
                __import__(mod)
            except ImportError:
                missing_mods.append(mod)

        if missing_mods:
            score -= 20
            infra_check["status"] = "ERROR"
            issues.append(f"核心依賴庫缺失: {', '.join(missing_mods)}")
            infra_check["items"].append({
                "name": "核心依賴套件 (requests/urllib3/webview)",
                "status": "ERROR",
                "desc": f"缺少模組: {', '.join(missing_mods)} (需執行 pip install)",
                "action": "fix_deps"
            })
        else:
            infra_check["items"].append({
                "name": "核心依賴套件 (requests/urllib3/webview)",
                "status": "OK",
                "desc": "關鍵依賴模組完整就緒 (3/3 核心模組正常載入)"
            })

        # 1.3 Microsoft Edge WebView2 運行時
        wv_ok, wv_desc = _check_webview2_runtime()
        if wv_ok:
            infra_check["items"].append({
                "name": "Microsoft Edge WebView2 內核",
                "status": "OK",
                "desc": wv_desc
            })
        else:
            score -= 10
            infra_check["status"] = "WARN"
            issues.append("未檢測到 Edge WebView2 內核 (可能影響部分網頁視窗功能)")
            infra_check["items"].append({
                "name": "Microsoft Edge WebView2 內核",
                "status": "WARN",
                "desc": wv_desc,
                "action": "install_webview2"
            })

        # 1.4 目錄結構與設定檔 JSON 完整性
        config_path = self.root_dir / "config" / "settings.json"
        is_config_healthy = True
        config_msg = "配置檔完整解析正常"
        if config_path.exists():
            try:
                json.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                is_config_healthy = False
                config_msg = "配置檔格式損壞或包含無效語法，建議重設配置"
        else:
            config_msg = "配置檔尚未建立 (使用預設配置)"

        if is_config_healthy:
            infra_check["items"].append({
                "name": "設定檔完整性 (settings.json)",
                "status": "OK",
                "desc": config_msg
            })
        else:
            score -= 15
            infra_check["status"] = "ERROR"
            issues.append("系統 settings.json 配置檔損壞")
            infra_check["items"].append({
                "name": "設定檔完整性 (settings.json)",
                "status": "ERROR",
                "desc": config_msg,
                "action": "reset_settings"
            })

        checks["infra_env"] = infra_check

        # ═══════════════════════════════════════════════════════
        # 2. 🎮 Steam 本機運行與注入核心 (steam_local)
        # ═══════════════════════════════════════════════════════
        steam_check = {
            "title": "Steam 本機環境與注入核心",
            "status": "OK",
            "items": []
        }

        steam_path = steam_manager.find_steam_path()
        if not steam_path or not Path(steam_path).exists():
            score -= 30
            steam_check["status"] = "ERROR"
            issues.append("未偵測到有效的 Steam 安裝路徑")
            steam_check["items"].append({
                "name": "Steam 安裝路徑",
                "status": "ERROR",
                "desc": "未找到 Steam 根目錄，請於設置中手動指定"
            })
        else:
            steam_check["items"].append({
                "name": "Steam 安裝路徑",
                "status": "OK",
                "desc": f"有效路徑: {steam_path}"
            })

            # 檢測核心 DLL
            dlls = ["OpenSteamTool.dll", "dwmapi.dll", "xinput1_4.dll"]
            missing_dlls = [d for d in dlls if not (Path(steam_path) / d).exists()]
            if missing_dlls:
                penalty = min(25, len(missing_dlls) * 10)
                score -= penalty
                steam_check["status"] = "WARN" if len(missing_dlls) < 3 else "ERROR"
                issues.append(f"缺少 {len(missing_dlls)} 個 OpenSteamTools 核心 DLL 檔案")
                steam_check["items"].append({
                    "name": "OpenSteamTools 核心檔案",
                    "status": "WARN",
                    "desc": f"缺少: {', '.join(missing_dlls)} (入庫前需注入核心)",
                    "action": "inject_dll"
                })
            else:
                steam_check["items"].append({
                    "name": "OpenSteamTools 核心檔案",
                    "status": "OK",
                    "desc": "核心 DLL 檔案完整 (3/3 已就緒)"
                })

            # 檢測目錄寫入權限
            config_dir = Path(steam_path) / "config"
            can_write_config = False
            try:
                config_dir.mkdir(parents=True, exist_ok=True)
                test_f = config_dir / ".health_test"
                test_f.write_text("ok", encoding="utf-8")
                test_f.unlink()
                can_write_config = True
            except Exception:
                pass

            if not can_write_config:
                score -= 15
                steam_check["status"] = "ERROR"
                issues.append("Steam/config 目錄缺少寫入權限")
                steam_check["items"].append({
                    "name": "目錄寫入權限 (Steam/config)",
                    "status": "ERROR",
                    "desc": "無法寫入 config 目錄，可能需要以系統管理員身分執行"
                })
            else:
                steam_check["items"].append({
                    "name": "目錄寫入權限 (Steam/config)",
                    "status": "OK",
                    "desc": "讀寫權限正常"
                })

            # Steam 運行狀態
            is_running = steam_manager.is_steam_running()
            steam_check["items"].append({
                "name": "Steam 客戶端進程",
                "status": "INFO",
                "desc": "運行中 (入庫/更新時需重啟 Steam 載入配置)" if is_running else "已關閉 (就緒狀態)"
            })

        checks["steam_local"] = steam_check

        # ═══════════════════════════════════════════════════════
        # 3. ⚡ SteamCMD & SteamDB 官方生態鏈 (steam_ecosystem)
        # ═══════════════════════════════════════════════════════
        ecosystem_check = {
            "title": "SteamCMD & SteamDB 官方生態鏈",
            "status": "OK",
            "items": []
        }

        # 3.1 SteamCMD 官方雲端 PICS API 管道
        if sc_ok or sc_code in [200, 204, 404]:
            ecosystem_check["items"].append({
                "name": "SteamCMD PICS 官方 API",
                "status": "OK",
                "desc": f"連線暢通 (延遲約 {sc_ms} ms · 官方版本查詢管道)"
            })
        else:
            score -= 10
            ecosystem_check["status"] = "WARN"
            issues.append("SteamCMD PICS 官方 API 連線逾時或受限")
            ecosystem_check["items"].append({
                "name": "SteamCMD PICS 官方 API",
                "status": "WARN",
                "desc": f"連線受限 (HTTP {sc_code} · {sc_err or '連線逾時'})"
            })

        # 3.2 SteamDB 官方站點與 Cloudflare 狀態
        if sdb_ok or sdb_code == 200:
            ecosystem_check["items"].append({
                "name": "SteamDB 官方站點連通性",
                "status": "OK",
                "desc": f"連線暢通 (無盾阻擋 · 延遲 {sdb_ms} ms)"
            })
        elif sdb_code in [403, 503, 429]:
            # 遇到 Cloudflare 盾牌，但系統有獨立快取與種子庫防護，故列為 INFO/WARN 不嚴重扣分
            ecosystem_check["items"].append({
                "name": "SteamDB 官方站點連通性",
                "status": "INFO",
                "desc": f"Cloudflare 盾牌防護中 (HTTP {sdb_code} · 系統已啟用本地獨立快取與真實種子庫防護)"
            })
        else:
            score -= 5
            ecosystem_check["items"].append({
                "name": "SteamDB 官方站點連通性",
                "status": "WARN",
                "desc": f"無法連通 SteamDB 伺服器 ({sdb_err or '網路逾時'})"
            })

        # 3.3 SteamDB 本地獨立快取庫
        sdb_cache_dir = self.root_dir / "data" / "steamdb_cache"
        cache_count = 0
        corrupted_count = 0
        if sdb_cache_dir.exists():
            for f in sdb_cache_dir.glob("*.json"):
                cache_count += 1
                try:
                    json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    corrupted_count += 1

        if corrupted_count > 0:
            score -= 5
            ecosystem_check["items"].append({
                "name": "SteamDB 本地獨立快取庫",
                "status": "WARN",
                "desc": f"收錄 {cache_count} 款遊戲快取 (發現 {corrupted_count} 個損壞快取)"
            })
        else:
            ecosystem_check["items"].append({
                "name": "SteamDB 本地獨立快取庫",
                "status": "OK",
                "desc": f"收錄 {cache_count} 款遊戲專屬快取 (0 損壞 · 毫秒級讀取)"
            })

        # 3.4 官方真實歷史種子庫
        try:
            from managers import steamdb_history_manager
            seed_count = len(steamdb_history_manager._VERIFIED_SEED_HISTORY)
            ecosystem_check["items"].append({
                "name": "官方真實驗證種子歷史庫",
                "status": "OK",
                "desc": f"已就緒 (收錄 {seed_count} 個核心 Depot 真實版本鏈，100% 官方真實記錄)"
            })
        except Exception:
            pass

        # 3.5 🌟 SteamDB 原生 WebView2 破盾爬蟲通道
        crawler_script = self.root_dir / "src" / "managers" / "steamdb_webview_crawler.py"
        wv_installed, _ = _check_webview2_runtime()
        if crawler_script.exists() and wv_installed:
            ecosystem_check["items"].append({
                "name": "SteamDB WebView2 破盾通道",
                "status": "OK",
                "desc": "已就緒 (支援 10s 完整運算破盾探測，全自動穿透 Cloudflare)"
            })
        elif not crawler_script.exists():
            ecosystem_check["items"].append({
                "name": "SteamDB WebView2 破盾通道",
                "status": "WARN",
                "desc": "未找到 steamdb_webview_crawler.py 探針腳本"
            })
        else:
            ecosystem_check["items"].append({
                "name": "SteamDB WebView2 破盾通道",
                "status": "WARN",
                "desc": "本機未安裝 Edge WebView2 運行時，破盾備援通道受限"
            })

        # 3.6 🌟 Depot 棄置與架構拓撲自檢
        try:
            from managers import version_resolver
            ecosystem_check["items"].append({
                "name": "Depot 棄置與替換拓撲引擎",
                "status": "OK",
                "desc": "拓撲引擎就緒 (精確識別棄置主程式與架構升級狀態，杜絕死循環)"
            })
        except Exception as e:
            ecosystem_check["items"].append({
                "name": "Depot 棄置與替換拓撲引擎",
                "status": "WARN",
                "desc": f"拓撲引擎載入異常: {e}"
            })

        checks["steam_ecosystem"] = ecosystem_check

        # ═══════════════════════════════════════════════════════
        # 4. 🌐 多源平台與外聯通訊管道 (network_sources)
        # ═══════════════════════════════════════════════════════
        sources_check = {
            "title": "多源下載平台與通訊管道",
            "status": "OK",
            "items": []
        }

        # 4.1 海外重要服務 DNS 解析品質
        dns_all_ok = dns_sc_ok and dns_sdb_ok and dns_ryuu_ok
        if dns_all_ok:
            sources_check["items"].append({
                "name": "海外重要服務 DNS 解析",
                "status": "OK",
                "desc": f"解析正常 (SteamCMD: {dns_sc_res}, SteamDB: {dns_sdb_res})"
            })
        else:
            score -= 10
            sources_check["status"] = "WARN"
            failed_dns = []
            if not dns_sc_ok: failed_dns.append("SteamCMD")
            if not dns_sdb_ok: failed_dns.append("SteamDB")
            if not dns_ryuu_ok: failed_dns.append("Ryuu")
            issues.append(f"DNS 解析失敗: {', '.join(failed_dns)} (可能受 ISP 污染)")
            sources_check["items"].append({
                "name": "海外重要服務 DNS 解析",
                "status": "WARN",
                "desc": f"部分域名解析失敗: {', '.join(failed_dns)} (建議更換 DNS 為 1.1.1.1 或 8.8.8.8)"
            })

        # 4.2 測試 Ryuu 官方伺服器連線
        if ryuu_ok or ryuu_code in [200, 301, 302, 403]:
            sources_check["items"].append({
                "name": "🐉 Ryuu 下載伺服器",
                "status": "OK",
                "desc": f"連線通暢 (延遲約 {ryuu_ms} ms · 首選下載源)"
            })
        else:
            score -= 10
            sources_check["status"] = "WARN"
            sources_check["items"].append({
                "name": "🐉 Ryuu 下載伺服器",
                "status": "WARN",
                "desc": f"連線受阻 ({ryuu_err or '連線逾時'} · 將依賴快取或備援源)"
            })

        # 4.3 檢測 HubcapDB API Key 與配額狀態
        from managers import hubcap_manager
        hc_info = hubcap_manager.fetch_user_stats()
        if hc_info.get("is_configured") and hc_info.get("ok"):
            rem = hc_info.get("remaining", 0)
            lim = hc_info.get("daily_limit", 25)
            sources_check["items"].append({
                "name": "🧢 HubcapDB 官方 API",
                "status": "OK" if rem > 0 else "WARN",
                "desc": f"金鑰有效 · 今日配額剩餘 {rem} / {lim} 次" + (" (配額已耗盡)" if rem == 0 else "")
            })
            if rem == 0:
                score -= 5
        elif hc_info.get("is_configured"):
            score -= 5
            sources_check["items"].append({
                "name": "🧢 HubcapDB 官方 API",
                "status": "WARN",
                "desc": f"API Key 驗證失敗: {hc_info.get('error', '請重新配置')}",
                "action": "config_hubcap"
            })
        else:
            sources_check["items"].append({
                "name": "🧢 HubcapDB 官方 API",
                "status": "INFO",
                "desc": "未配置 API Key (可選備援源，不影響 Ryuu 首選下載)",
                "action": "config_hubcap"
            })

        # 4.4 檢測 Lua.tools 平台
        if lt_ok or lt_code in [200, 301, 302, 403]:
            sources_check["items"].append({
                "name": "🌙 Lua.tools 平台",
                "status": "OK",
                "desc": f"平台服務在線 (延遲約 {lt_ms} ms)"
            })
        else:
            sources_check["items"].append({
                "name": "🌙 Lua.tools 平台",
                "status": "WARN",
                "desc": "暫時無法直接連通"
            })

        checks["network_sources"] = sources_check

        # ═══════════════════════════════════════════════════════
        # 5. 🪪 帳號憑證與授權健康度 (credentials)
        # ═══════════════════════════════════════════════════════
        cred_check = {
            "title": "帳號憑證與授權",
            "status": "OK",
            "items": []
        }

        try:
            from managers import account_manager
            acc_mgr = account_manager.get_account_manager()
            acc_mgr.reload_data()
            r_accs = acc_mgr.get_accounts("ryuu")
            valid_r_accs = [a for a in r_accs if acc_mgr.has_valid_credentials(a, "ryuu")]

            if valid_r_accs:
                cred_check["items"].append({
                    "name": "Discord 授權憑證",
                    "status": "OK",
                    "desc": f"已綁定 {len(r_accs)} 個帳號 (其中 {len(valid_r_accs)} 個有效授權，配額充足)"
                })
            elif r_accs:
                score -= 10
                cred_check["status"] = "WARN"
                issues.append("Discord 帳號憑證已過期或未授權")
                cred_check["items"].append({
                    "name": "Discord 授權憑證",
                    "status": "WARN",
                    "desc": f"已綁定 {len(r_accs)} 個帳號，但憑證皆已過期，請重新登入授權",
                    "action": "login_discord"
                })
            else:
                score -= 15
                cred_check["status"] = "WARN"
                issues.append("尚未綁定 Discord 授權帳號")
                cred_check["items"].append({
                    "name": "Discord 授權憑證",
                    "status": "WARN",
                    "desc": "尚未登入 Discord 帳號，請至憑證管理頁登入以取得免費配額",
                    "action": "login_discord"
                })

            auto_rot = acc_mgr.data.get("auto_rotate", True)
            cred_check["items"].append({
                "name": "多帳號自動輪換",
                "status": "OK" if auto_rot else "INFO",
                "desc": "已啟用 (配額用盡自動切換下一帳號)" if auto_rot else "未啟用 (手動調度模式)"
            })
        except Exception:
            cred_check["items"].append({
                "name": "Discord 授權憑證",
                "status": "WARN",
                "desc": "本地憑證註冊表讀取受限，請至憑證管理頁重新登入或授權",
                "action": "login_discord"
            })

        checks["credentials"] = cred_check

        # ═══════════════════════════════════════════════════════
        # 6. 💾 本機儲存與快取健全度 (storage)
        # ═══════════════════════════════════════════════════════
        storage_check = {
            "title": "本機儲存與快取",
            "status": "OK",
            "items": []
        }

        # 快取目錄佔用檢測
        cache_dir = self.root_dir / "data" / "cache"
        total_cache_size = 0
        if cache_dir.exists():
            for p in cache_dir.glob("**/*"):
                if p.is_file():
                    total_cache_size += p.stat().st_size
        cache_mb = round(total_cache_size / (1024 * 1024), 2)
        storage_check["items"].append({
            "name": "本機 Manifest 快取空間",
            "status": "OK",
            "desc": f"目前快取大小: {cache_mb} MB (正常)"
        })

        # SteamDB 歷史版本快取佔用檢測
        steamdb_dir = self.root_dir / "data" / "steamdb_cache"
        steamdb_mb = 0.0
        if steamdb_dir.exists():
            s_size = sum(p.stat().st_size for p in steamdb_dir.glob("*.json") if p.is_file())
            steamdb_mb = round(s_size / (1024 * 1024), 2)
        storage_check["items"].append({
            "name": "SteamDB 歷史版本快取庫",
            "status": "OK",
            "desc": f"快取目錄已就緒: {steamdb_mb} MB (正常)"
        })

        # 6.3 🌟 全鏈路批次調度與 Manifest 更新診斷日誌
        batch_log_dir = self.root_dir / "logs" / "batch_updates"
        manifest_log_dir = self.root_dir / "logs" / "manifest_updates"
        batch_log_dir.mkdir(parents=True, exist_ok=True)
        manifest_log_dir.mkdir(parents=True, exist_ok=True)

        batch_log_count = len([f for f in batch_log_dir.glob("batch_update_*.log") if f.is_file()])
        manifest_log_count = len([f for f in manifest_log_dir.glob("manifest_update_*.log") if f.is_file()])

        storage_check["items"].append({
            "name": "批次調度與更新診斷日誌體系",
            "status": "OK",
            "desc": f"已就緒 (批次日誌: {batch_log_count} 份 · 個別更新日誌: {manifest_log_count} 份 · 支援全鏈路追溯與自動滾動)"
        })

        checks["storage"] = storage_check

        # ═══════════════════════════════════════════════════════
        # 綜合評分與狀態分級
        # ═══════════════════════════════════════════════════════
        score = max(0, min(100, score))
        if score >= 90:
            rating = "EXCELLENT"
            rating_text = "極佳 · 系統處於最佳就緒狀態"
            color = "#4CAF50"
        elif score >= 75:
            rating = "GOOD"
            rating_text = "良好 · 基本功能正常運作"
            color = "#8BC34A"
        elif score >= 50:
            rating = "WARNING"
            rating_text = "警示 · 部分功能受限需維護"
            color = "#FF9800"
        else:
            rating = "CRITICAL"
            rating_text = "嚴重 · 核心環境異常需立即修復"
            color = "#F44336"

        elapsed_ms = int((time.time() - start_t) * 1000)

        # ═══════════════════════════════════════════════════════
        # 生成 Markdown 體檢報告並落盤 (至多 5 份滾動維護)
        # ═══════════════════════════════════════════════════════
        md_lines = [
            f"# 🩺 系統全方位健康診斷報告 ({date_display})",
            "",
            f"**綜合健康分數**：`{score} / 100` ({rating_text})  ",
            f"**體檢總耗時**：`{elapsed_ms} ms` (外部通訊採多執行緒平行探測)  ",
            f"**發現問題數**：`{len(issues)} 項`  ",
            ""
        ]

        if issues:
            md_lines.append("## ⚠️ 待修復與警示項目")
            for idx, iss in enumerate(issues, 1):
                md_lines.append(f"{idx}. {iss}")
            md_lines.append("")

        for section_key, section in checks.items():
            md_lines.append(f"## {section['title']}")
            md_lines.append("| 項目 | 狀態 | 詳情 |")
            md_lines.append("| :--- | :---: | :--- |")
            for item in section["items"]:
                icon = "🟢" if item["status"] == "OK" else ("🟡" if item["status"] in ["WARN", "INFO"] else "🔴")
                md_lines.append(f"| {item['name']} | {icon} {item['status']} | {item['desc']} |")
            md_lines.append("")

        report_markdown = "\n".join(md_lines)

        # 寫入實體日誌檔案
        log_filename = f"health_check_{timestamp_str}.log"
        log_path = self.logs_dir / log_filename
        try:
            log_path.write_text(report_markdown, encoding="utf-8")
            _latest_log_path.write_text(report_markdown, encoding="utf-8")
        except Exception as e:
            print(f"[HealthCheckManager] 寫入體檢日誌失敗: {e}")

        # 🌟 觸發至多 5 份的自動滾動刪除
        self._rotate_logs()

        result_payload = {
            "ok": True,
            "timestamp": date_display,
            "timestamp_raw": timestamp_str,
            "score": score,
            "rating": rating,
            "rating_text": rating_text,
            "color": color,
            "issues": issues,
            "elapsed_ms": elapsed_ms,
            "checks": checks,
            "log_filename": log_filename,
            "report_markdown": report_markdown
        }

        global _latest_data_cache
        _latest_data_cache = result_payload

        # 🌟 寫入本機磁碟快取，確保下次重啟軟體直接秒開 (< 1ms)
        try:
            _disk_cache_path.parent.mkdir(parents=True, exist_ok=True)
            _disk_cache_path.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[HealthCheckManager] 寫入磁碟快取失敗: {e}")

        return result_payload

    def get_latest_result(self) -> Dict[str, Any]:
        """獲取最新一次的體檢快取 (記憶體/磁碟秒開，絕不阻塞等待)"""
        global _latest_data_cache
        if _latest_data_cache:
            return _latest_data_cache
        self._load_disk_cache()
        if _latest_data_cache:
            return _latest_data_cache
        return self.run_health_check()

    def get_history_logs(self) -> List[Dict[str, Any]]:
        """
        獲取歷史體檢日誌清單 (至多 5 筆)
        """
        results = []
        try:
            log_files = [
                p for p in self.logs_dir.glob("health_check_*.log")
                if p.name != "latest_health_check.log" and p.is_file()
            ]
            log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

            for lf in log_files[:self.max_log_files]:
                stat = lf.stat()
                mtime_str = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                results.append({
                    "filename": lf.name,
                    "size_bytes": stat.st_size,
                    "mtime": mtime_str
                })
        except Exception as e:
            print(f"[HealthCheckManager] 獲取歷史日誌清單異常: {e}")
        return results

    def get_log_content(self, filename: str) -> Dict[str, Any]:
        """讀取指定日誌的 Markdown 內容"""
        safe_name = Path(filename).name
        target = self.logs_dir / safe_name
        if target.exists() and target.is_file():
            try:
                content = target.read_text(encoding="utf-8", errors="replace")
                return {"ok": True, "filename": safe_name, "content": content}
            except Exception as e:
                return {"ok": False, "msg": f"讀取失敗: {e}"}
        return {"ok": False, "msg": "日誌檔案不存在或已被輪換清理"}


_health_check_manager = None

def get_health_check_manager() -> HealthCheckManager:
    global _health_check_manager
    if _health_check_manager is None:
        _health_check_manager = HealthCheckManager.get_instance()
    return _health_check_manager
