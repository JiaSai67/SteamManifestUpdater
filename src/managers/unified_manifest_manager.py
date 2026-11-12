import os
import re
import json
import time
import stat
import threading
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Callable, List

from managers import config_manager, steam_manager

class UnifiedManifestManager:
    """
    聚合 Manifest 與 Lua 管理器 (Ryuu + SteamDB + Lua.tools)
    1. 整合 Ryuu (generator.ryuu.lol)、SteamDB 官方版本鏈與 Lua.tools。
    2. 自動精準對齊 SteamDB 官方最新版本與 Ryuu 庫存。
    3. 執行最佳授權下載策略，並完成 Manifest 部署、Lua 更新/自適應拼裝、ACF 防 401 鎖定。
    """
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = UnifiedManifestManager()
        return cls._instance

    def __init__(self):
        self.config = config_manager.get_config()
        self.keys_api_url = "https://api.993499094.xyz/depotkeys.json"
        self._depot_keys_cache = None
        self._ryuu_cache_lock = threading.Lock()
        self._ryuu_down_until = 0.0
        self._ryuu_last_err = ""

    def get_cached_depot_keys(self) -> Dict[str, str]:
        """讀取或快取公開 23.9 萬把 DepotKeys"""
        if self._depot_keys_cache is not None:
            return self._depot_keys_cache
        
        # 本地快取檔案
        cache_file = config_manager._root_dir / "data" / "cache" / "depotkeys.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    self._depot_keys_cache = json.load(f)
                    return self._depot_keys_cache
            except Exception:
                pass
                
        # 聯網獲取
        try:
            req = urllib.request.Request(self.keys_api_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self._depot_keys_cache = data
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                return self._depot_keys_cache
        except Exception as e:
            print(f"[UnifiedManifestManager] 獲取公共 DepotKeys 失敗: {e}")
            return {}

    def _query_hubcap(self, appid: str, timeout: int = 6, allow_network: bool = True, steamdb_manifests: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        查詢 HubcapDB 平台收錄狀態（0 配額消耗）。
        🌟 採用 HubcapDB 官方免費純查詢端點 GET /api/v1/manifest/{appid}/contents (free: true)，
        直接獲取壓縮包內所有 Depot ID 與 Manifest GID，完全不下載 ZIP、絕不消耗每日 25 次配額！
        """
        try:
            from managers import hubcap_manager
            appid_str = str(appid).strip()

            if not allow_network:
                cached = hubcap_manager._load_hubcap_cached_info(appid_str)
                if cached and cached.get("available"):
                    c_dep = dict(cached.get("depots") or {})
                    if (not c_dep or c_dep == {appid_str: "available"}) and steamdb_manifests:
                        c_dep = dict(steamdb_manifests)
                    elif not c_dep:
                        c_dep = {appid_str: "available"}
                    return {
                        "available": True,
                        "depots": c_dep,
                        "time": cached.get("time", "本地快取"),
                        "last_modified": cached.get("last_modified", ""),
                        "is_aligned_steamdb": False,
                        "has_zip": cached.get("has_zip", True),
                        "quota_exhausted": False,
                        "from_cache": True,
                        "status_msg": "已讀取本地快取"
                    }
                return {
                    "available": False,
                    "depots": {},
                    "time": "未查詢",
                    "is_aligned_steamdb": False,
                    "has_zip": False,
                    "quota_exhausted": False,
                    "from_cache": False,
                    "status_msg": "僅讀取快取"
                }

            # 透過 0 配額免費端點 /api/v1/manifest/{appid}/contents 查詢 (內建 120s 短期快取)
            info = hubcap_manager.query_manifest_info(appid_str, timeout=timeout)
            is_avail = bool(info.get("available"))
            hc_depots = dict(info.get("depots") or {}) if is_avail else {}
            if is_avail:
                # 若為 /status 或 /library 備援確認在庫而尚未附帶具體 GID，結合 SteamDB 官方清單補齊以便後續流程完整運作
                if (not hc_depots or hc_depots == {appid_str: "available"}) and steamdb_manifests:
                    hc_depots = dict(steamdb_manifests)
                elif not hc_depots:
                    hc_depots = {appid_str: "available"}

            return {
                "available": is_avail,
                "depots": hc_depots,
                "time": info.get("time", "即時在庫"),
                "last_modified": info.get("last_modified", ""),
                "is_aligned_steamdb": False,
                "has_zip": info.get("has_zip", is_avail),
                "quota_exhausted": bool(info.get("quota_exhausted")),
                "from_cache": bool(info.get("from_cache")),
                "status_msg": info.get("error", "")
            }
        except Exception as e:
            print(f"[UnifiedManifestManager] Hubcap 查詢異常: {e}")
            return {
                "available": False, 
                "depots": {}, 
                "time": "無", 
                "is_aligned_steamdb": False, 
                "has_zip": False,
                "quota_exhausted": False,
                "from_cache": False,
                "status_msg": str(e)
            }

    def search_all_sources(self, appid: str, timeout: int = 6, steamdb_manifests: Optional[Dict[str, str]] = None, allow_hubcap_network: bool = True) -> Dict[str, Any]:
        """
        異步並行搜尋 Manifest 多源平台 (Ryuu, HubcapDB, Lua.tools)，並以 SteamDB 官方清單為基準仲裁。
        並行執行大幅降低網路等待時間，三平台查詢皆為 0 配額消耗之純查詢端點。
        """
        appid_str = str(appid).strip()
        result = {
            "appid": appid_str,
            "best_source": "ryuu",
            "best_reason": "",
            "ryuu": {"available": False, "depots": {}, "time": "未知", "is_aligned_steamdb": False},
            "hubcap": {"available": False, "depots": {}, "time": "未知", "is_aligned_steamdb": False},
            "luatools": {"available": False, "depots": {}, "time": "未知", "is_aligned_steamdb": False},
            "summary": ""
        }

        # 🌟 若未提供 SteamDB 基準清單，主動快速查詢以作為版本精確仲裁基準
        if steamdb_manifests is None:
            try:
                from managers import version_resolver
                sdb_q = version_resolver.fetch_steamdb_manifests(appid_str, timeout=3)
                steamdb_manifests = sdb_q.get("manifests", {})
            except Exception:
                steamdb_manifests = {}

        # 🌟 異步並行查詢 Ryuu 與 Lua.tools；HubcapDB 嚴格受 allow_hubcap_network 控制，保護使用者配額
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            fut_ryuu = executor.submit(self._query_ryuu, appid_str, timeout)
            fut_hubcap = executor.submit(self._query_hubcap, appid_str, timeout, allow_hubcap_network, steamdb_manifests)
            fut_luatools = executor.submit(self._query_luatools, appid_str, timeout)

            try:
                result["ryuu"] = fut_ryuu.result()
            except Exception as e:
                print(f"[UnifiedManifestManager] Ryuu 查詢異常: {e}")

            try:
                result["hubcap"] = fut_hubcap.result()
            except Exception as e:
                print(f"[UnifiedManifestManager] Hubcap 查詢異常: {e}")

            try:
                result["luatools"] = fut_luatools.result()
            except Exception as e:
                print(f"[UnifiedManifestManager] Lua.tools 查詢異常: {e}")

        # 3. 讀取跨平台即時配額快照並執行版本+額度優先級仲裁
        quota_snapshot = self.get_platforms_quota_snapshot()
        self._arbitrate_best_source(result, steamdb_manifests=steamdb_manifests, quota_snapshot=quota_snapshot)
        return result

    def get_platforms_quota_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """取得 Ryuu、Lua.tools 與 HubcapDB 三平台的即時可用配額與配置狀態快照 (0 配額消耗)"""
        snapshot = {
            "ryuu": {"left": 0, "limit": 0, "has_quota": False, "is_configured": False},
            "luatools": {"left": 0, "limit": 0, "has_quota": False, "is_configured": False},
            "hubcap": {"left": 0, "limit": 0, "has_quota": False, "is_configured": False}
        }
        try:
            from managers import account_manager
            mgr = account_manager.get_account_manager()
            r_left, r_lim = mgr.get_total_remaining_quota("ryuu")
            lt_left, lt_lim = mgr.get_total_remaining_quota("lua_tools")
            snapshot["ryuu"] = {
                "left": int(r_left),
                "limit": int(r_lim),
                "has_quota": int(r_left) > 0,
                "is_configured": int(r_lim) > 0 or len(mgr.get_accounts("ryuu")) > 0
            }
            snapshot["luatools"] = {
                "left": int(lt_left),
                "limit": int(lt_lim),
                "has_quota": int(lt_left) > 0,
                "is_configured": int(lt_lim) > 0 or len(mgr.get_accounts("lua_tools")) > 0
            }
        except Exception as e:
            print(f"[UnifiedManifestManager] 讀取 Ryuu/Lua.tools 配額快照異常: {e}")

        try:
            from managers import hubcap_manager, account_manager
            hc_key = hubcap_manager.get_api_key() or account_manager.get_account_manager().get_any_hubcap_key()
            if hc_key:
                hc_stats = hubcap_manager.fetch_user_stats()
                hc_ok = bool(hc_stats.get("ok") and not hc_stats.get("connection_error"))
                hc_rem = int(hc_stats.get("remaining", 0)) if hc_ok else 0
                hc_lim = int(hc_stats.get("daily_limit", 25) or 25) if hc_ok else 0
                hc_can = bool(hc_stats.get("can_make_requests", True)) and hc_rem > 0 and hc_ok
                snapshot["hubcap"] = {
                    "left": hc_rem,
                    "limit": hc_lim,
                    "has_quota": hc_can,
                    "is_configured": True,
                    "is_valid": hc_ok
                }
        except Exception as e:
            print(f"[UnifiedManifestManager] 讀取 HubcapDB 配額快照異常: {e}")

        return snapshot

    def _log_manifest_check(self, message: str):
        """記錄 Manifest 查詢與網路比對診斷日誌到 logs/manifest_checks.log"""
        try:
            log_dir = config_manager._root_dir / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "manifest_checks.log"
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{now_str}] {message}\n")
        except Exception:
            pass

    def _get_ryuu_cache_path(self) -> Path:
        p = config_manager._root_dir / "data" / "cache" / "ryuu_manifestinfo_cache.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _load_ryuu_cached_info(self, appid: str) -> Optional[Dict[str, Any]]:
        with self._ryuu_cache_lock:
            try:
                cache_file = self._get_ryuu_cache_path()
                if cache_file.exists():
                    c = json.loads(cache_file.read_text(encoding="utf-8"))
                    return c.get(str(appid))
            except Exception:
                pass
        return None

    def _save_ryuu_cached_info(self, appid: str, data: Dict[str, Any]):
        with self._ryuu_cache_lock:
            try:
                cache_file = self._get_ryuu_cache_path()
                c = {}
                if cache_file.exists():
                    try: c = json.loads(cache_file.read_text(encoding="utf-8"))
                    except Exception: c = {}
                c[str(appid)] = data
                cache_file.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

    def _query_ryuu(self, appid: str, timeout: int = 10) -> Dict[str, Any]:
        """
        查詢 generator.ryuu.lol
        - 具備節點斷路器 (Circuit Breaker)：當 Ryuu 節點發生 HTTP 521 / 5xx 異常時，30 秒內自動切換為 2 秒快速單次探測，絕不拖慢 HubcapDB / Lua.tools 備源查找！
        - 具備快取兜底保護：若網路波動失敗，自動回退使用先前已知有效的庫存資料，絕不誤判為未收錄！
        - 全鏈路診斷日誌記錄到 logs/manifest_checks.log
        """
        data = {"available": False, "depots": {}, "time": "無", "branch_manifests": {}, "steamdb_target": {}}
        url = f"https://generator.ryuu.lol/manifestinfo/{appid}"
        start_t = time.time()
        last_error = ""

        # 若 Ryuu 節點處於斷路器冷卻期 (如剛發生 HTTP 521)，自動縮短逾時且僅嘗試 1 次，確保秒速切換備源
        in_cooldown = (start_t < self._ryuu_down_until)
        max_attempts = 1 if in_cooldown else 2
        effective_timeout = 2.0 if in_cooldown else min(max(timeout, 5), 10)

        for attempt in range(1, max_attempts + 1):
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/plain, */*"
                })
                with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
                    res = json.loads(resp.read().decode("utf-8"))
                    bm = res.get("branch_manifests", {})
                    data["branch_manifests"] = bm
                    
                    # 1. 取得 SteamDB 目標版本
                    pub_target = bm.get("public", {}).get("depots", {})
                    data["steamdb_target"] = {str(k): str(v) for k, v in pub_target.items()} if pub_target else {}

                    # 2. 實體二進位檔案清單
                    real_files = bm.get("public", {}).get("files", [])
                    if not real_files:
                        for b_name, b_val in bm.items():
                            if isinstance(b_val, dict) and b_val.get("files"):
                                real_files = b_val.get("files", [])
                                break

                    actual_depots = {}
                    for fn in real_files:
                        if fn.lower().endswith(".manifest"):
                            base = fn[:-9]
                            if "_" in base:
                                parts = base.split("_", 1)
                                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                                    actual_depots[parts[0]] = parts[1]

                    if actual_depots:
                        data["depots"] = actual_depots
                        data["available"] = True
                    elif pub_target:
                        data["depots"] = {str(k): str(v) for k, v in pub_target.items()}
                        data["available"] = True

                    ts = res.get("timestamp")
                    if ts:
                        try:
                            data["time"] = datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
                        except Exception:
                            data["time"] = str(ts)

                    # 成功獲取，解除斷路器並寫入本地快取與日誌
                    self._ryuu_down_until = 0.0
                    self._ryuu_last_err = ""
                    try:
                        from managers import account_manager
                        account_manager.get_account_manager().set_platform_connection_status("ryuu", False, "")
                    except Exception:
                        pass
                    data["connection_error"] = False
                    self._save_ryuu_cached_info(appid, data)
                    elapsed = time.time() - start_t
                    self._log_manifest_check(f"[RyuuOK] AppID: {appid}, Attempt: {attempt}, Time: {elapsed:.2f}s, Depots: {len(data['depots'])}, Available: {data['available']}")
                    return data

            except urllib.error.HTTPError as e:
                last_error = f"HTTP {e.code}"
                if e.code == 404:
                    # 伺服器明確回傳 404：確定無此遊戲，但連線本身正常，不再重試
                    self._ryuu_down_until = 0.0
                    self._ryuu_last_err = ""
                    try:
                        from managers import account_manager
                        account_manager.get_account_manager().set_platform_connection_status("ryuu", False, "")
                    except Exception:
                        pass
                    break
                if e.code >= 500:
                    # 節點掛掉 (如 HTTP 521 / 502 / 503)：立即觸發 30 秒斷路器，不重複無謂等待
                    self._ryuu_down_until = time.time() + 30.0
                    self._ryuu_last_err = last_error
                    break
                time.sleep(0.3)
            except Exception as e:
                last_error = str(e)
                self._ryuu_down_until = time.time() + 15.0
                self._ryuu_last_err = last_error
                if attempt < max_attempts:
                    time.sleep(0.3)

        elapsed = time.time() - start_t
        # 若非 404 / 429，且發生 5xx (如 521) 或網路連線異常，標記 Ryuu 平台連線異常
        is_conn_err = bool(last_error and last_error not in ("HTTP 404", "HTTP 429"))
        if is_conn_err:
            try:
                from managers import account_manager
                account_manager.get_account_manager().set_platform_connection_status("ryuu", True, last_error)
            except Exception:
                pass
            data["connection_error"] = True
            data["error_msg"] = last_error

        # 若所有嘗試均因網路異常失敗，啟動快取兜底保護！
        cached = self._load_ryuu_cached_info(appid)
        if cached and cached.get("available") and cached.get("depots"):
            cached = dict(cached)
            cached["from_cache"] = True
            if is_conn_err:
                cached["connection_error"] = True
                cached["error_msg"] = last_error
            self._log_manifest_check(f"[RyuuFALLBACK] AppID: {appid}, Error: {last_error}, Time: {elapsed:.2f}s, 成功使用歷史快取兜底! (Depots: {len(cached.get('depots', {}))})")
            return cached

        self._log_manifest_check(f"[RyuuFAIL] AppID: {appid}, Error: {last_error}, Time: {elapsed:.2f}s, 無快取可兜底，標為未收錄")
        return data

    def _query_luatools(self, appid: str, timeout: int) -> Dict[str, Any]:
        """
        查詢 Lua.tools 官方 API (/api/manifest/check?appid={appid})
        依據規範：嚴格只檢測並認可 Ryuu 實體 Manifest 來源，杜絕 Luie 等無 Manifest 來源消耗額度。
        """
        data = {"available": False, "depots": {}, "time": "無", "sources": []}
        try:
            import sqlite3, tempfile, shutil
            from pathlib import Path
            from managers import account_manager
            
            mgr = account_manager.get_account_manager()
            acc = mgr.get_available_account("lua_tools") or mgr.get_active_account("lua_tools")
            cookie_hdr = ""
            if acc and acc.get("profile_dir"):
                p_dir = Path(acc.get("profile_dir"))
                cookie_file = p_dir / "Cookies"
                if cookie_file.exists():
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
                        tmp_p = tmp.name
                    try:
                        shutil.copy2(cookie_file, tmp_p)
                        conn = sqlite3.connect(tmp_p)
                        cur = conn.cursor()
                        cur.execute("SELECT name, value FROM cookies WHERE host_key LIKE '%lua.tools%'")
                        cookies = dict(cur.fetchall())
                        conn.close()
                        if cookies:
                            cookie_hdr = "; ".join([f"{k}={v}" for k, v in cookies.items() if v])
                    finally:
                        if os.path.exists(tmp_p): os.remove(tmp_p)

            url = f"https://lua.tools/api/manifest/check?appid={appid}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://lua.tools/"
            }
            if cookie_hdr:
                headers["Cookie"] = cookie_hdr

            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                mgr.set_platform_connection_status("lua_tools", False, "")
                res = json.loads(resp.read().decode("utf-8"))
                if isinstance(res, dict) and "error" not in res:
                    # 🌟 嚴格只判定 Ryuu 來源 (Luie 僅提供 Lua 無 Manifest，不列入可用)
                    ryuu_ok = any(str(k).lower() == "ryuu" and str(v).lower() in ["available", "true", "1", "ok"] for k, v in res.items())
                    if ryuu_ok:
                        data["available"] = True
                        data["sources"] = ["Ryuu"]
                        data["time"] = "即時在庫 (Ryuu 來源)"
        except urllib.error.HTTPError as he:
            if he.code >= 500:
                try:
                    from managers import account_manager
                    account_manager.get_account_manager().set_platform_connection_status("lua_tools", True, f"HTTP {he.code}")
                except Exception:
                    pass
                data["connection_error"] = True
            else:
                try:
                    from managers import account_manager
                    account_manager.get_account_manager().set_platform_connection_status("lua_tools", False, "")
                except Exception:
                    pass
        except Exception as e:
            try:
                from managers import account_manager
                account_manager.get_account_manager().set_platform_connection_status("lua_tools", True, str(e))
            except Exception:
                pass
            data["connection_error"] = True
        return data

    def _arbitrate_best_source(self, result: Dict[str, Any], steamdb_manifests: Optional[Dict[str, str]] = None, quota_snapshot: Optional[Dict[str, Any]] = None):
        """
        多源版本與配額聯合仲裁引擎 (以 SteamDB 官方數據為版本基準，結合三平台即時配額)：
        核心決策流程：
        1. 檢查 Ryuu、Lua.tools、HubcapDB 的額度與版本。
        2. Ryuu = Lua.tools（同源 Manifest 池）：
           若版本為官方最新且額度充足 -> 優先使用 Ryuu，其次使用 Lua.tools。
        3. 若 Ryuu = Lua.tools 版本並非最新，或兩者額度均不足：
           經檢查發現 HubcapDB 版本更新（或在庫可用）且額度充足 -> 使用 HubcapDB。
        4. 若使用者未配置 HubcapDB、或 HubcapDB 額度不足 / 未收錄 / 版本未更新，
           而 Ryuu 或 Lua.tools 有可用版本與額度 -> 優先使用 Ryuu，其次 Lua.tools，並標記非最新版以給予友善提示（絕不拒絕入庫）。
        """
        if quota_snapshot is None:
            quota_snapshot = self.get_platforms_quota_snapshot()
        result["quota_snapshot"] = quota_snapshot

        r_q = quota_snapshot.get("ryuu", {})
        lt_q = quota_snapshot.get("luatools", {})
        hc_q = quota_snapshot.get("hubcap", {})

        ryuu_has_quota = bool(r_q.get("has_quota"))
        lt_has_quota = bool(lt_q.get("has_quota"))
        hc_has_quota = bool(hc_q.get("has_quota"))

        official_depots = {}
        if steamdb_manifests and isinstance(steamdb_manifests, dict):
            official_depots = {str(k).strip(): str(v).strip() for k, v in steamdb_manifests.items() if str(k).strip()}

        ryuu = result.get("ryuu", {})
        ryuu_conn_err = bool(ryuu.get("connection_error"))
        ryuu_ok = bool(ryuu.get("available", False) and ryuu.get("depots"))
        ryuu_live_ok = bool(ryuu_ok and not ryuu_conn_err)
        ryuu_depots = {str(k).strip(): str(v).strip() for k, v in ryuu.get("depots", {}).items()}

        luatools = result.get("luatools", {})
        lt_conn_err = bool(luatools.get("connection_error"))
        lt_ok = bool(luatools.get("available", False))
        lt_live_ok = bool(lt_ok and not lt_conn_err)
        if lt_ok and ryuu_depots and not luatools.get("depots"):
            luatools["depots"] = dict(ryuu_depots)
        elif lt_ok and official_depots and not luatools.get("depots"):
            luatools["depots"] = dict(official_depots)

        # Ryuu 與 Lua.tools 共享同一 Ryuu 來源池
        ryuu_pool_ok = ryuu_ok or lt_ok
        ryuu_pool_live_ok = ryuu_live_ok or lt_live_ok

        hubcap = result.get("hubcap", {})
        hubcap_ok = bool(hubcap.get("available", False))
        if hubcap_ok and not hubcap.get("depots"):
            hubcap["depots"] = dict(official_depots) if official_depots else {str(result.get("appid", "")): "available"}
        hubcap_depots = {str(k).strip(): str(v).strip() for k, v in hubcap.get("depots", {}).items()}

        # 1. 評估 Ryuu (= Lua.tools) 與官方最新版對齊度
        ryuu_matches_steamdb = False
        ryuu_match_count = 0
        if official_depots:
            if ryuu_depots:
                common_ryuu = [k for k in official_depots if k in ryuu_depots]
                if common_ryuu:
                    ryuu_match_count = sum(1 for k in common_ryuu if ryuu_depots[k] == official_depots[k])
                    ryuu_matches_steamdb = (ryuu_match_count == len(official_depots))
        else:
            # 若無 SteamDB 官方基準可比對 (如未公開 Depot)，在庫即視為當前最新可用
            ryuu_matches_steamdb = ryuu_pool_ok

        ryuu["is_aligned_steamdb"] = ryuu_matches_steamdb
        ryuu["matched_official_count"] = ryuu_match_count
        luatools["is_aligned_steamdb"] = ryuu_matches_steamdb
        luatools["matched_official_count"] = ryuu_match_count

        # 2. 評估 HubcapDB 與官方最新版對齊度，以及是否比 Ryuu=Lua.tools 更新
        hubcap_matches_steamdb = False
        hubcap_match_count = 0
        if official_depots:
            if hubcap_depots:
                common_hc = [k for k in official_depots if k in hubcap_depots]
                if common_hc:
                    hubcap_match_count = sum(1 for k in common_hc if hubcap_depots[k] == official_depots[k] or hubcap_depots[k] == "available")
                    hubcap_matches_steamdb = (hubcap_match_count == len(official_depots))
        else:
            hubcap_matches_steamdb = hubcap_ok

        hubcap["is_aligned_steamdb"] = hubcap_matches_steamdb
        hubcap["matched_official_count"] = hubcap_match_count

        hubcap_is_newer = False
        if hubcap_ok:
            if not ryuu_pool_live_ok:
                hubcap_is_newer = True
            elif official_depots:
                if hubcap_matches_steamdb and not ryuu_matches_steamdb:
                    hubcap_is_newer = True
                elif hubcap_match_count > ryuu_match_count:
                    hubcap_is_newer = True

        result["ryuu_is_latest"] = ryuu_matches_steamdb
        result["hubcap_is_newer"] = hubcap_is_newer
        result["expected_outdated"] = False

        # 3. 依照多平台額度、節點連線狀態與版本優先級裁決
        candidate_order = []
        if ryuu_pool_live_ok and ryuu_matches_steamdb and ((ryuu_live_ok and ryuu_has_quota) or (lt_live_ok and lt_has_quota)):
            # 🌟 分支 1：Ryuu = Lua.tools 節點連線正常、版本為最新且額度充足 -> 優先 Ryuu，其次 Lua.tools
            if ryuu_has_quota and ryuu_live_ok:
                result["best_source"] = "ryuu"
                result["best_reason"] = "Ryuu 版本為官方最新且額度充足（優先採用 Ryuu）"
                candidate_order = ["ryuu", "luatools", "hubcap"]
            else:
                result["best_source"] = "luatools"
                result["best_reason"] = "Ryuu=Lua.tools 版本為官方最新，自動採用 Lua.tools"
                candidate_order = ["luatools", "hubcap", "ryuu"]
        else:
            # 🌟 分支 2：Ryuu 節點異常 (如 HTTP 521)、版本並非最新、或兩者額度均不足
            if hubcap_ok and hc_has_quota and (hubcap_is_newer or not ryuu_pool_live_ok or (not ryuu_has_quota and not lt_has_quota)):
                result["best_source"] = "hubcap"
                if ryuu_conn_err:
                    result["best_reason"] = "Ryuu 節點連線異常，已自動切換至 HubcapDB 備援通道"
                elif not ryuu_pool_ok:
                    result["best_reason"] = "Ryuu 與 Lua.tools 尚未收錄，HubcapDB 在庫且額度充足，採用 HubcapDB"
                elif hubcap_is_newer:
                    result["best_reason"] = "Ryuu/Lua.tools 版本並非最新，經檢查 HubcapDB 版本更新且額度充足，採用 HubcapDB"
                else:
                    result["best_reason"] = "Ryuu 與 Lua.tools 額度不足，經檢查 HubcapDB 在庫且額度充足，採用 HubcapDB"
                result["expected_outdated"] = bool(official_depots and not hubcap_matches_steamdb)
                candidate_order = ["hubcap", "luatools", "ryuu"]
            elif ryuu_pool_live_ok and ((ryuu_live_ok and ryuu_has_quota) or (lt_live_ok and lt_has_quota)):
                # 使用者未設定 HubcapDB、HubcapDB 無額度或版本未更新 -> 不拒絕入庫，退回優先 Ryuu、其次 Lua.tools 並標記提示
                result["expected_outdated"] = bool(official_depots and not ryuu_matches_steamdb)
                if ryuu_has_quota and ryuu_live_ok:
                    result["best_source"] = "ryuu"
                    result["best_reason"] = "官方已有新版但目前無更新來源可用，優先採用 Ryuu 現有可用版本入庫"
                    candidate_order = ["ryuu", "luatools", "hubcap"]
                else:
                    result["best_source"] = "luatools"
                    result["best_reason"] = "採用次選 Lua.tools 現有可用版本入庫"
                    candidate_order = ["luatools", "hubcap", "ryuu"]
            elif hubcap_ok and hc_has_quota:
                result["best_source"] = "hubcap"
                result["best_reason"] = "採用 HubcapDB 現有可用版本"
                result["expected_outdated"] = bool(official_depots and not hubcap_matches_steamdb)
                candidate_order = ["hubcap", "luatools", "ryuu"]
            elif lt_live_ok:
                result["best_source"] = "luatools"
                result["best_reason"] = "嘗試透過 Lua.tools 通道獲取可用版本"
                result["expected_outdated"] = bool(official_depots and not ryuu_matches_steamdb)
                candidate_order = ["luatools", "hubcap", "ryuu"]
            elif hubcap_ok:
                result["best_source"] = "hubcap"
                result["best_reason"] = "嘗試透過 HubcapDB 通道獲取可用版本"
                result["expected_outdated"] = bool(official_depots and not hubcap_matches_steamdb)
                candidate_order = ["hubcap", "luatools", "ryuu"]
            elif ryuu_ok:
                result["best_source"] = "ryuu"
                result["best_reason"] = "嘗試透過 Ryuu 通道獲取可用版本"
                result["expected_outdated"] = bool(official_depots and not ryuu_matches_steamdb)
                candidate_order = ["ryuu", "luatools", "hubcap"]
            elif lt_ok:
                result["best_source"] = "luatools"
                result["best_reason"] = "嘗試透過 Lua.tools 通道獲取可用版本"
                result["expected_outdated"] = bool(official_depots and not ryuu_matches_steamdb)
                candidate_order = ["luatools", "hubcap", "ryuu"]
            else:
                result["best_source"] = "none"
                result["best_reason"] = "所有來源均無此遊戲 Manifest"
                candidate_order = []

        # 去重保持順序
        dedup_order = []
        for c in candidate_order:
            if c not in dedup_order:
                dedup_order.append(c)
        result["candidate_order"] = dedup_order

        if hubcap.get("quota_exhausted") or (hc_q.get("is_configured") and not hc_has_quota and hc_q.get("is_valid")):
            result["hubcap_status"] = "今日配額已達上限 (0/25)"
        elif hubcap_ok:
            result["hubcap_status"] = "在庫可用"
        else:
            result["hubcap_status"] = "未收錄或未配置"

    def _check_recent_invalid_install_path(self, appid_str: str, steam_path: Optional[str]) -> bool:
        """檢查 Steam content_log.txt 近期是否曾針對此 AppID 出現 Invalid install path（典型缺 PICS addtoken 症狀）"""
        if not steam_path or not appid_str:
            return False
        try:
            log_file = Path(steam_path) / "logs" / "content_log.txt"
            if not log_file.exists():
                return False
            size = log_file.stat().st_size
            with open(log_file, "rb") as f:
                if size > 65536:
                    f.seek(size - 65536)
                tail = f.read().decode("utf-8", errors="ignore")
            return f"Failed installing AppID {appid_str} (Invalid install path)" in tail
        except Exception:
            return False

    def validate_package_integrity(
        self,
        appid_str: str,
        lua_text: str,
        manifest_bytes_map: Optional[Dict[str, bytes]] = None,
        steam_path: Optional[str] = None,
        official_info: Optional[Dict[str, Any]] = None,
        is_install: bool = False,
        allow_local_tar_stub: bool = False,
    ) -> Dict[str, Any]:
        """
        驗證下載或本地部署包之完整性：
        1. Lua 非空且含有效 addappid() 宣告
        2. Lua 內所有有效 setManifestid() 皆具備對應 .manifest 實體內容，且無任何損毀 / HTML / JSON 錯誤頁 .manifest
        3. 若 Steam PICS 顯示此遊戲受 Token 保護且屬於新安裝（或尚無 appmanifest ACF），Lua 必須包含 addtoken(appid, ...)
        """
        if not lua_text or not lua_text.strip():
            return {"ok": False, "code": "EMPTY_LUA", "reason": "Lua 設定檔內容為空或讀取失敗", "manifest_ids": {}}

        if not re.search(r"addappid\s*\(\s*\d+", lua_text):
            return {"ok": False, "code": "EMPTY_LUA", "reason": "Lua 缺少有效 addappid 宣告", "manifest_ids": {}}

        active_manifests: Dict[str, str] = {}
        for raw_line in lua_text.splitlines():
            code_part = raw_line.split("--", 1)[0]
            if not code_part.strip():
                continue
            for m in re.finditer(r'setManifestid\s*\(\s*(\d+)\s*,\s*["\'](\d+)["\']', code_part):
                active_manifests[m.group(1)] = m.group(2)

        def _is_valid_manifest_bytes(m_bytes: bytes) -> bool:
            if not m_bytes or len(m_bytes) < 16:
                return False
            head = m_bytes[:4]
            if head in (b"\xd0\x17\xf6\x71", b"PK\x03\x04"):
                return True
            if allow_local_tar_stub and head == b"tar.":
                return True
            return False

        # 若有 ZIP 內提取出的所有 .manifest 位元組，先全面驗明其二進位檔頭不可為錯誤頁 / 截斷檔
        if manifest_bytes_map is not None:
            if not manifest_bytes_map and official_info and official_info.get("manifests"):
                return {
                    "ok": False,
                    "code": "MISSING_MANIFEST",
                    "reason": "壓縮包內未包含任何 .manifest 清單檔案",
                    "manifest_ids": active_manifests,
                }
            for fname, m_bytes in manifest_bytes_map.items():
                if not _is_valid_manifest_bytes(m_bytes):
                    preview = m_bytes[:4] if m_bytes else b""
                    return {
                        "ok": False,
                        "code": "CORRUPT_MANIFEST",
                        "reason": f"清單檔 {fname} 二進位格式異常或為 HTML/文字錯誤回應 (檔頭: {preview!r}, 長度: {len(m_bytes or b'')})",
                        "manifest_ids": active_manifests,
                    }

        # 逐一檢查 Lua 有效 setManifestid() 所宣告的 .manifest 是否存在且有效
        for did, gid in active_manifests.items():
            fname = f"{did}_{gid}.manifest"
            m_bytes = None
            if manifest_bytes_map is not None:
                m_bytes = manifest_bytes_map.get(fname)
            elif steam_path:
                m_path = Path(steam_path) / "depotcache" / fname
                if m_path.exists():
                    try:
                        m_bytes = m_path.read_bytes()
                    except Exception:
                        m_bytes = None
            if m_bytes is None:
                return {
                    "ok": False,
                    "code": "MISSING_MANIFEST",
                    "reason": f"Lua 宣告了 Depot {did} ({gid})，但缺少對應實體檔 {fname}",
                    "manifest_ids": active_manifests,
                }
            if not _is_valid_manifest_bytes(m_bytes):
                preview = m_bytes[:4] if m_bytes else b""
                return {
                    "ok": False,
                    "code": "CORRUPT_MANIFEST",
                    "reason": f"實體清單 {fname} 二進位損毀或為錯誤內容 (檔頭: {preview!r})",
                    "manifest_ids": active_manifests,
                }

        # 檢查 PICS Token 保護：僅於全新安裝或尚未建立 appmanifest_<appid>.acf 時要求必須含 addtoken
        acf_exists = bool(steam_path and steam_manager.find_appmanifest(appid_str, steam_path))
        needs_install_token_check = bool(is_install or not acf_exists)

        pics_protected = False
        if official_info and official_info.get("steamcmd_ok"):
            if official_info.get("missing_token") and not official_info.get("has_config"):
                pics_protected = True
        elif self._check_recent_invalid_install_path(appid_str, steam_path):
            pics_protected = True

        if needs_install_token_check and pics_protected:
            has_addtoken = bool(
                re.search(
                    rf'(?m)^[ \t]*(?!--).*?\baddtoken\s*\(\s*["\']?{re.escape(appid_str)}["\']?\s*,',
                    lua_text,
                )
            )
            if not has_addtoken:
                return {
                    "ok": False,
                    "code": "MISSING_PICS_TOKEN",
                    "reason": f"AppID {appid_str} 受 Steam PICS Token 保護且無公開 config，但 Lua 缺少 addtoken({appid_str}, ...)（直接安裝會導致 Steam 報「安裝路徑無效」）",
                    "manifest_ids": active_manifests,
                }

        return {"ok": True, "code": "OK", "reason": "完整性校驗通過", "manifest_ids": active_manifests}

    def _extract_zip_entries_in_memory(
        self, appid_str: str, zip_bytes: bytes
    ) -> Tuple[Optional[str], Dict[str, bytes], Dict[str, str], List[Tuple[str, bytes]], Optional[str]]:
        """將下載到的 ZIP 封包於記憶體中安全拆解為 Lua 文本、Manifest 位元組表與清單字典，不觸及磁碟。"""
        import io, zipfile

        lua_entries: List[Tuple[str, bytes]] = []
        manifest_bytes_map: Dict[str, bytes] = {}
        extracted_manifests: Dict[str, str] = {}

        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                for zname in zf.namelist():
                    if zname.endswith("/"):
                        continue
                    fname = Path(zname).name
                    if not fname:
                        continue
                    lower_name = fname.lower()
                    if lower_name.endswith(".manifest"):
                        m_bytes = zf.read(zname)
                        manifest_bytes_map[fname] = m_bytes
                        m_parts = fname[:-9].split("_")
                        if len(m_parts) == 2 and m_parts[0].isdigit() and m_parts[1].isdigit():
                            extracted_manifests[m_parts[0]] = m_parts[1]
                    elif lower_name.endswith(".lua"):
                        l_bytes = zf.read(zname)
                        lua_entries.append((fname, l_bytes))
        except Exception as ze:
            return None, {}, {}, [], f"ZIP 封包結構異常或解壓失敗: {ze}"

        lua_text = ""
        main_lua_name = f"{appid_str}.lua"
        for fname, l_bytes in lua_entries:
            if fname == main_lua_name:
                lua_text = l_bytes.decode("utf-8", errors="ignore")
                break
        if not lua_text and lua_entries:
            lua_text = "\n".join(b.decode("utf-8", errors="ignore") for _, b in lua_entries)

        return lua_text, manifest_bytes_map, extracted_manifests, lua_entries, None

    def _write_validated_zip_entries(
        self,
        appid_str: str,
        steam_p: str,
        manifest_bytes_map: Dict[str, bytes],
        extracted_manifests: Dict[str, str],
        lua_entries: List[Tuple[str, bytes]],
        logger: Optional[Any] = None,
    ) -> None:
        """將通過記憶體完整性驗證之 Manifest 與 Lua 寫入 Steam 目錄、永久金庫與備援目錄並完成閉環同步。"""
        depotcache = Path(steam_p) / "depotcache"
        depotcache.mkdir(parents=True, exist_ok=True)
        c_backup = Path(steam_p) / "config" / "depotcache"
        c_backup.mkdir(parents=True, exist_ok=True)
        lua_dir = Path(steam_p) / "config" / "lua"
        lua_dir.mkdir(parents=True, exist_ok=True)
        st_lua = Path(steam_p) / "config" / "stplug-in"
        cfg_lua = config_manager.get_config().get("lua_dir")

        for m_name, m_bytes in manifest_bytes_map.items():
            m_target = depotcache / m_name
            if m_target.exists():
                try: os.chmod(m_target, stat.S_IWRITE | stat.S_IREAD)
                except Exception: pass
            m_target.write_bytes(m_bytes)
            try: os.chmod(m_target, stat.S_IWRITE | stat.S_IREAD)
            except Exception: pass

            try:
                c_backup_file = c_backup / m_name
                if c_backup_file.exists():
                    try: os.chmod(c_backup_file, stat.S_IWRITE | stat.S_IREAD)
                    except Exception: pass
                c_backup_file.write_bytes(m_bytes)
                try: os.chmod(c_backup_file, stat.S_IREAD)
                except Exception: pass
                if logger:
                    logger.log_file_op("永久備份 Manifest", str(c_backup_file), size=len(m_bytes), success=True, details="寫入永久金庫 (防 Steam 解除安裝刪除)")
            except Exception as be:
                if logger:
                    logger.log_file_op("永久備份 Manifest", str(c_backup / m_name), size=len(m_bytes), success=False, details=str(be))

            m_parts = m_name[:-9].split("_")
            if logger:
                logger.log_file_op("解壓寫入 Manifest", str(m_target), size=len(m_bytes), success=True, details=f"Depot: {m_parts[0] if len(m_parts)==2 else 'Unknown'}, Manifest: {m_parts[1] if len(m_parts)==2 else m_name}")

        for l_name, l_bytes in lua_entries:
            l_path = lua_dir / l_name
            if l_path.exists():
                try: os.chmod(l_path, stat.S_IWRITE | stat.S_IREAD)
                except Exception: pass
            l_path.write_bytes(l_bytes)

            if st_lua.exists():
                try:
                    st_l_path = st_lua / l_name
                    if st_l_path.exists():
                        try: os.chmod(st_l_path, stat.S_IWRITE | stat.S_IREAD)
                        except Exception: pass
                    st_l_path.write_bytes(l_bytes)
                except Exception: pass

            if cfg_lua and Path(cfg_lua).resolve() != lua_dir.resolve():
                try:
                    Path(cfg_lua).mkdir(parents=True, exist_ok=True)
                    cfg_l_path = Path(cfg_lua) / l_name
                    if cfg_l_path.exists():
                        try: os.chmod(cfg_l_path, stat.S_IWRITE | stat.S_IREAD)
                        except Exception: pass
                    cfg_l_path.write_bytes(l_bytes)
                except Exception: pass

            try:
                l_text = l_bytes.decode("utf-8", errors="ignore")
                for km in re.finditer(r'addappid\s*\(\s*(\d+)\s*,\s*\d+\s*,\s*"([a-fA-F0-9]{64})"', l_text):
                    k_did, k_val = km.group(1), km.group(2)
                    if self._depot_keys_cache is None:
                        self._depot_keys_cache = {}
                    self._depot_keys_cache[k_did] = k_val
            except Exception:
                pass

            if logger:
                logger.log_file_op("解壓寫入 Lua", str(l_path), size=len(l_bytes), success=True, details="主設定檔")

        steam_manager.sync_lua_with_deployed_manifests(
            appid_str, manifests_dict=extracted_manifests, lua_dir=lua_dir
        )
        steam_manager.verify_and_sync_local_manifests(
            appid_str, steam_path=steam_p, lua_dir=lua_dir, target_manifests=extracted_manifests
        )
        steam_manager.sanitize_lua_manifests(appid_str, steam_p, lua_dir)
        steam_manager.lock_game_version(appid_str, steam_p)

    def deploy_best_manifest(self, appid: str, search_result: Any = None, progress_cb: Optional[Callable[[str], None]] = None, logger: Optional[Any] = None, steam_path: Optional[str] = None, is_install: bool = False) -> Tuple[bool, str]:
        """
        【多平台配額與版本智慧仲裁部署引擎】
        1. 前置校驗：自檢本機 Lua 與 depotcache 實體檔案一致性 (Auto-heal)。
        2. 差異判定：若本機實體檔案已是當前可用最高版本，直接完成校準 (0 額度消耗)；若非官方最新版則給予提示、絕不拒絕入庫。
        3. 優先級下載：嚴格依循仲裁順序 (Ryuu=Lua.tools 最新且有額度 -> Ryuu 優先、Lua.tools 次之；非最新或無額度且 Hubcap 更新且有額度 -> HubcapDB；否則退回可用版本並提示)。
        4. 下載後閉環驗證：確保 Lua 檔案與實體 Manifest 100% 同步。
        """
        appid_str = str(appid).strip()
        if not appid_str or not appid_str.isdigit():
            if logger: logger.log_error("參數校驗", f"無效或未提供 AppID: '{appid}'")
            return False, f"無效或未提供 AppID: '{appid}'"
        from managers import steam_manager, version_resolver, hubcap_manager

        steam_p = steam_path or steam_manager.find_steam_path()
        if logger:
            logger.log_step("前置檢查", f"開始部署 AppID {appid_str}，Steam 路徑: {steam_p}")

        # 參數彈性容錯：支援 search_result 為 callable 或 None
        if callable(search_result):
            progress_cb = search_result
            search_result = None
        if not search_result or not isinstance(search_result, dict):
            if logger:
                logger.log_step("多源搜尋", "未傳入搜尋結果，執行即時多源搜尋比對...")
            search_result = self.search_all_sources(appid_str)

        best_src = search_result.get("best_source", "ryuu")
        if logger:
            logger.log_step("多源仲裁", f"最佳來源: {best_src}，候選順序: {search_result.get('candidate_order')}，依據: {search_result.get('best_reason')}")

        # 🌟 步驟 1：前置校驗 —— 本機 Lua 宣告與 depotcache 實體檔案自檢修復
        if progress_cb: progress_cb("正在校驗本機 Lua 宣告與實體 Manifest 檔案...")
        local_check = steam_manager.verify_and_sync_local_manifests(appid_str, steam_path=steam_p)
        local_manifests = local_check.get("lua_manifests", {})
        if logger:
            logger.log_step("本地自檢", f"本地宣告: {local_manifests}, 缺失清單: {local_check.get('missing_files', [])}")

        # 🌟 步驟 2：前置判定 —— 檢查本機是否已經等於目標平台版本且實體 .manifest 檔案完整存在
        if best_src == "hubcap":
            target_depots = search_result.get("hubcap", {}).get("depots", {})
            target_source_info = search_result.get("hubcap", {})
        else:
            target_depots = search_result.get("ryuu", {}).get("depots", {}) or search_result.get("luatools", {}).get("depots", {}) or search_result.get("hubcap", {}).get("depots", {})
            target_source_info = search_result.get("ryuu", {}) if search_result.get("ryuu", {}).get("available") else (search_result.get("luatools", {}) or search_result.get("hubcap", {}))

        missing_files = local_check.get("missing_files", [])
        is_synced = local_check.get("is_synced", False)

        official_manifests = {}
        sdb_info = {}
        try:
            sdb_info = version_resolver.fetch_steamdb_manifests(appid_str, timeout=4)
            official_manifests = sdb_info.get("manifests", {}) or {}
        except Exception:
            sdb_info = {}
            official_manifests = {}

        # 🌟 拓撲檢測：檢查是否存在已棄置 Depot 待遷移
        topo = version_resolver.identify_depot_topology(
            appid_str,
            local_manifests=local_manifests,
            official_manifests=official_manifests or search_result.get("ryuu", {}).get("steamdb_target", {}) or target_depots,
            ryuu_info=search_result.get("ryuu", {})
        )

        if local_manifests and target_depots and is_synced and not missing_files and not topo.get("has_deprecated"):
            is_already_matched = True
            for d_id, t_gid in target_depots.items():
                if d_id not in local_manifests or str(local_manifests[d_id]) != str(t_gid):
                    is_already_matched = False
                    break
                if steam_p:
                    m_f = Path(steam_p) / "depotcache" / f"{d_id}_{t_gid}.manifest"
                    if not m_f.exists():
                        is_already_matched = False
                        break

            # 🌟 核心防護：檢查本地 Lua 是否缺少金鑰！若有 Depot 宣告但缺 64 位元 Key，強制連網下載原廠配置
            if is_already_matched and steam_p:
                lua_f = Path(steam_p) / "config" / "lua" / f"{appid_str}.lua"
                if not lua_f.exists():
                    is_already_matched = False
                else:
                    try:
                        lua_txt = lua_f.read_text(encoding="utf-8", errors="ignore")
                        for d_id in target_depots.keys():
                            if str(d_id) != appid_str:
                                has_naked_add = bool(re.search(rf'addappid\s*\(\s*{d_id}\s*\)', lua_txt))
                                has_keyed_add = bool(re.search(rf'addappid\s*\(\s*{d_id}\s*,\s*\d+\s*,\s*"[a-fA-F0-9]{{64}}"', lua_txt))
                                if has_naked_add and not has_keyed_add:
                                    is_already_matched = False
                                    print(f"[UnifiedManifestManager] 本地 Lua 缺少 Depot {d_id} 之金鑰，強制自雲端下載官方原廠打包檔！")
                                    break
                    except Exception:
                        pass

            # 🌟 深度完整性防護：檢查本機 .manifest 二進位格式與 PICS addtoken（安裝時若缺 addtoken 不可短路跳過！）
            if is_already_matched and steam_p:
                try:
                    lua_f = Path(steam_p) / "config" / "lua" / f"{appid_str}.lua"
                    lua_txt = lua_f.read_text(encoding="utf-8", errors="ignore") if lua_f.exists() else ""
                    local_integ = self.validate_package_integrity(
                        appid_str,
                        lua_txt,
                        manifest_bytes_map=None,
                        steam_path=steam_p,
                        official_info=sdb_info,
                        is_install=is_install,
                        allow_local_tar_stub=True,
                    )
                    if not local_integ.get("ok"):
                        is_already_matched = False
                        warn_local = f"本地清單檔案未通過完整性校驗 ({local_integ.get('reason')})，將自動從雲端重新取得完整資源"
                        print(f"[UnifiedManifestManager] AppID {appid_str} {warn_local}")
                        if logger:
                            logger.log_step("本地完整性不通過", warn_local, status="WARN")
                except Exception:
                    pass

            if is_already_matched:
                steam_manager.sanitize_lua_manifests(appid_str, steam_p)
                steam_manager.lock_game_version(appid_str, steam_p)
                is_aligned_sdb = target_source_info.get("is_aligned_steamdb", True)
                if official_manifests:
                    is_aligned_sdb = all(str(local_manifests.get(str(did))) == str(off_gid) for did, off_gid in official_manifests.items())

                if not is_aligned_sdb:
                    # 🌟 核心修正：版本並非官方最新時，給予友善提示，絕不拒絕入庫！
                    warn_msg = "目前可用平台尚未收錄 Steam 官方最新版本，已先以現有可用版本為您完成清單校準與入庫"
                    search_result["deployed_outdated"] = True
                    search_result["outdated_warning"] = warn_msg
                    search_result["deployed_source"] = best_src if best_src != "none" else "local"
                    print(f"[UnifiedManifestManager] AppID {appid_str} {warn_msg}")
                    if logger: logger.log_step("非最新版提示", warn_msg, status="WARN")
                    return True, f"本機清單已就緒（提示：{warn_msg}）"
                else:
                    search_result["deployed_outdated"] = False
                    search_result["deployed_source"] = best_src if best_src != "none" else "local"
                    msg = "本機 Lua 與實體 Manifest 已與官方最新版本完全吻合，已完成自檢校準！"
                    print(f"[UnifiedManifestManager] AppID {appid_str} {msg}")
                    return True, msg

        # 🌟 步驟 3：嚴格依據仲裁產生之平台候選順序 (candidate_order) 執行下載部署與即時備援
        candidate_order = search_result.get("candidate_order") or ([] if best_src == "none" else [best_src])
        if not candidate_order:
            candidate_order = ["ryuu", "luatools", "hubcap"]

        has_qt_app = False
        try:
            from PySide6.QtCore import QCoreApplication
            has_qt_app = (QCoreApplication.instance() is not None)
        except Exception:
            has_qt_app = False

        quota_snap = search_result.get("quota_snapshot") or self.get_platforms_quota_snapshot()
        errors_by_source = {}
        deployed_ok = False
        deployed_msg = ""
        deployed_src = ""
        integrity_defect_reason = ""
        pending_candidates = list(candidate_order)
        tried_sources = set()
        skip_sources = set()

        def _strip_integrity_prefix(raw_msg: str) -> Tuple[bool, str]:
            text = str(raw_msg or "")
            if text.startswith("[INTEGRITY]"):
                return True, text[len("[INTEGRITY]"):].strip()
            return False, text

        def _record_unexpected_hubcap_if_needed(cur_src: str) -> None:
            if cur_src != "hubcap":
                return
            if not integrity_defect_reason and best_src == "hubcap":
                return
            hc_rem = None
            hc_lim = None
            try:
                hc_stats = hubcap_manager.fetch_user_stats(force_refresh=True)
                if hc_stats and hc_stats.get("ok"):
                    hc_rem = hc_stats.get("remaining")
                    hc_lim = hc_stats.get("daily_limit")
            except Exception:
                pass
            if hc_rem is None:
                hc_snap_fb = quota_snap.get("hubcap") or {}
                hc_rem = hc_snap_fb.get("remaining")
                hc_lim = hc_snap_fb.get("daily_limit")
            reason_txt = (
                integrity_defect_reason
                or errors_by_source.get("ryuu")
                or errors_by_source.get("luatools")
                or "主通道下載檔案不完整或失效"
            )
            rem_str = f"（今日剩餘 {hc_rem}/{hc_lim} 次）" if (hc_rem is not None and hc_lim is not None) else ""
            notice_msg = (
                f"偵測到主來源檔案異常（{reason_txt}），已直接轉向 HubcapDB 取得完整資源，"
                f"意外消耗 1 次 HubcapDB 配額{rem_str}。"
            )
            search_result["unexpected_hubcap_fallback"] = True
            search_result["hubcap_quota_consumed"] = True
            search_result["fallback_reason"] = reason_txt
            search_result["hubcap_remaining"] = hc_rem
            search_result["hubcap_daily_limit"] = hc_lim
            search_result["quota_notice"] = notice_msg
            if logger:
                logger.log_step("意外配額消耗通知", notice_msg, status="WARN")
            if progress_cb:
                progress_cb(f"⚠️ {notice_msg}")

        while pending_candidates:
            cand = pending_candidates.pop(0)
            if cand in tried_sources or cand in skip_sources:
                continue
            tried_sources.add(cand)

            if cand == "ryuu":
                if progress_cb:
                    progress_cb("正在透過 Ryuu 官方授權通道下載 Manifest 與 Lua 打包檔...")
                c_ok, c_msg = self._deploy_from_ryuu_http(
                    appid_str, progress_cb, logger=logger, official_info=sdb_info, is_install=is_install
                )
                is_int_err, clean_msg = _strip_integrity_prefix(c_msg)
                if not c_ok and has_qt_app and not is_int_err:
                    c_ok_qt, c_msg_qt = self._deploy_from_ryuu(appid_str, progress_cb)
                    if c_ok_qt:
                        c_ok, c_msg = c_ok_qt, c_msg_qt
            elif cand == "luatools":
                prev_ryuu_err = errors_by_source.get("ryuu", "")
                if progress_cb:
                    progress_cb("正在透過 Lua.tools 授權通道下載 Manifest 與 Lua 打包檔...")
                c_ok, c_msg = self._deploy_from_luatools_http(
                    appid_str, progress_cb, ryuu_error=prev_ryuu_err, logger=logger, official_info=sdb_info, is_install=is_install
                )
            elif cand == "hubcap":
                hc_key = hubcap_manager.get_api_key()
                if not hc_key:
                    errors_by_source["hubcap"] = "未設定 HubcapDB API Key"
                    continue
                if progress_cb:
                    progress_cb("正在透過 HubcapDB 官方 API 通道下載最新 Manifest 與 Lua 打包檔...")
                if logger:
                    logger.log_step("Hubcap下載", f"調用 HubcapDB 部署通道 ({search_result.get('best_reason', '')})...")
                c_ok, c_msg = hubcap_manager.deploy_from_hubcap(appid_str, steam_path=steam_p, api_key=hc_key, logger=logger)
            else:
                continue

            if not c_ok:
                is_int_err, clean_msg = _strip_integrity_prefix(c_msg)
                errors_by_source[cand] = clean_msg
                if is_int_err and cand in ("ryuu", "luatools"):
                    integrity_defect_reason = clean_msg
                    if cand == "ryuu":
                        skip_sources.add("luatools")
                    if "hubcap" not in tried_sources and "hubcap" not in skip_sources:
                        if "hubcap" in pending_candidates:
                            pending_candidates.remove("hubcap")
                        pending_candidates.insert(0, "hubcap")
                    if logger:
                        logger.log_step("完整性故障直切HubcapDB", f"{cand} 檔案完整性異常 ({clean_msg})，已跳過同源通道並直接切換至 HubcapDB 備援", status="WARN")
                    if progress_cb:
                        progress_cb(f"⚠️ {cand} 下載檔案完整性校驗失敗（{clean_msg}），正直接切換至 HubcapDB 取得完整資源...")
                else:
                    next_candidates = [c for c in pending_candidates if c not in tried_sources and c not in skip_sources]
                    if next_candidates:
                        next_cand = next_candidates[0]
                        next_label = {"ryuu": "Ryuu", "luatools": "Lua.tools", "hubcap": "HubcapDB"}.get(next_cand, next_cand)
                        if logger:
                            logger.log_step("切換備援", f"{cand} 下載未果 ({clean_msg})，自動切換至下一優先級平台 {next_label}...", status="WARN")
                        if progress_cb:
                            progress_cb(f"⚠️ {cand} 未完成，正在自動切換至 {next_label} 備援通道...")
                continue

            # 下載成功後關卡 1：檢查本機 Lua 宣告與實體 .manifest 完整性（含二進位標頭與 PICS addtoken）
            if steam_p:
                local_verify = steam_manager.verify_and_sync_local_manifests(appid_str, steam_path=steam_p)
                missing_f = local_verify.get("missing_files", [])
                lua_f_post = Path(steam_p) / "config" / "lua" / f"{appid_str}.lua"
                lua_txt_post = lua_f_post.read_text(encoding="utf-8", errors="ignore") if lua_f_post.exists() else ""
                post_integ = self.validate_package_integrity(
                    appid_str,
                    lua_txt_post,
                    manifest_bytes_map=None,
                    steam_path=steam_p,
                    official_info=sdb_info,
                    is_install=is_install,
                    allow_local_tar_stub=False,
                )
                if missing_f or not local_verify.get("is_synced", False) or not post_integ.get("ok"):
                    fail_reason = (
                        f"缺少實體 Manifest: {missing_f}" if (missing_f or not local_verify.get("is_synced", False))
                        else post_integ.get("reason", "部署後完整性未通過")
                    )
                    errors_by_source[cand] = f"{cand} 完整性未過關 ({fail_reason})"
                    if logger:
                        logger.log_step("完整性未過關", errors_by_source[cand], status="WARN")
                    if cand in ("ryuu", "luatools"):
                        integrity_defect_reason = fail_reason
                        if cand == "ryuu":
                            skip_sources.add("luatools")
                        if "hubcap" not in tried_sources and "hubcap" not in skip_sources:
                            if "hubcap" in pending_candidates:
                                pending_candidates.remove("hubcap")
                            pending_candidates.insert(0, "hubcap")
                        if progress_cb:
                            progress_cb(f"⚠️ {cand} 檔案完整性驗證未通過（{fail_reason}），正直接切換至 HubcapDB 備援...")
                    continue

                # 關卡 2：比對是否已達 SteamDB 官方最新版
                l_manifests = local_verify.get("lua_manifests", {})
                is_official_latest = True
                lag_reason = ""
                if official_manifests:
                    for did, off_gid in official_manifests.items():
                        cur_gid = l_manifests.get(str(did))
                        if not cur_gid or str(cur_gid) != str(off_gid):
                            is_official_latest = False
                            lag_reason = f"Depot {did} 當前版本 {cur_gid or '無'} 尚未對齊官方最新 {off_gid}"
                            break

                # 若當前使用 Ryuu / Lua.tools 部署成功，但發現實際解壓版本並非官方最新，檢查 HubcapDB 是否有更新版本且配額充足可熱替換
                if not is_official_latest and cand in ("ryuu", "luatools"):
                    hc_key_now = hubcap_manager.get_api_key()
                    hc_snap = quota_snap.get("hubcap", {})
                    if hc_key_now and hc_snap.get("has_quota", True) and "hubcap" not in errors_by_source:
                        hc_info = hubcap_manager.query_manifest_info(appid_str, api_key=hc_key_now)
                        if hc_info.get("available") and hc_info.get("depots"):
                            hc_depots = hc_info.get("depots", {})
                            hc_better = any(
                                str(hc_depots.get(str(k))) == str(v) and str(l_manifests.get(str(k))) != str(v)
                                for k, v in official_manifests.items() if str(k) in hc_depots
                            )
                            if hc_better:
                                if progress_cb:
                                    progress_cb("檢測到 HubcapDB 擁有更新版本且額度充足，正在升級為最新清單...")
                                if logger:
                                    logger.log_step("Hubcap升級", f"{cand} 版本非最新 ({lag_reason})，HubcapDB 版本更新且額度充足，執行升級部署...")
                                ok_hc, msg_hc = hubcap_manager.deploy_from_hubcap(appid_str, steam_path=steam_p, api_key=hc_key_now, logger=logger)
                                if ok_hc:
                                    search_result["deployed_source"] = "hubcap"
                                    search_result["deployed_outdated"] = False
                                    return True, f"✨ {msg_hc}"
                                else:
                                    errors_by_source["hubcap"] = msg_hc
                                    if logger:
                                        logger.log_step("Hubcap升級未果", f"{msg_hc}，保留已就緒之 {cand} 可用版本繼續入庫", status="WARN")

                _record_unexpected_hubcap_if_needed(cand)
                deployed_ok = True
                deployed_msg = c_msg
                deployed_src = cand
                search_result["deployed_source"] = cand
                if not is_official_latest:
                    # 🌟 核心修正：即使版本並非最新（例如用戶無 HubcapDB 金鑰、配額不足或各平台均未收錄最新版），也絕不拒絕入庫！給予友善提示即可！
                    warn_text = "目前平台收錄版本並非 Steam 官方最新版，已先以現有可用版本完成入庫"
                    search_result["deployed_outdated"] = True
                    search_result["outdated_warning"] = warn_text
                    if logger:
                        logger.log_step("非最新版放行", f"{warn_text} ({lag_reason})", status="WARN")
                    return True, f"{c_msg}（提示：{warn_text}）"
                else:
                    search_result["deployed_outdated"] = False
                    return True, c_msg
            else:
                _record_unexpected_hubcap_if_needed(cand)
                deployed_ok = True
                deployed_msg = c_msg
                deployed_src = cand
                search_result["deployed_source"] = cand
                search_result["deployed_outdated"] = False
                return True, c_msg

        if deployed_ok:
            search_result["deployed_source"] = deployed_src
            return True, deployed_msg

        err_summary = "；".join([f"{k}: {v}" for k, v in errors_by_source.items() if v]) or "所有可用平台均未收錄此遊戲或配額不足"
        return False, err_summary

    def _deploy_from_ryuu(self, appid: str, progress_cb: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
        """調用現有 ryuu_manager 進行下載與部署 (嚴格保護非 Qt 環境)"""
        try:
            from PySide6.QtCore import QCoreApplication
            if QCoreApplication.instance() is None:
                return False, "當前為純 Webview 模式，未啟用 Qt 核心事件循環，無法調用 Ryuu WebEngine 通道。"
        except Exception:
            return False, "缺少 PySide6 環境支援。"

        try:
            from managers import ryuu_manager, steam_manager, config_manager
            from pathlib import Path
            from PySide6.QtCore import QEventLoop, QTimer

            client = getattr(ryuu_manager, 'get_shared_ryuu_client', lambda: None)()
            if not client or not client.is_logged_in:
                return False, "Ryuu 尚未登入或憑證已失效"
                
            if progress_cb: progress_cb("正在透過 Ryuu 下載 Manifest 與 Lua 打包檔...")
            
            loop = QEventLoop()
            dl_result = {}
            
            def on_done(res):
                dl_result["res"] = res
                loop.quit()
                
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(loop.quit)
            timer.start(25000)
            
            client.download_manifest(appid, "public", on_done)
            loop.exec()
            timer.stop()
            
            res = dl_result.get("res")
            if not res or res.get("error"):
                err = res.get("error", "超時或無回應") if res else "Ryuu 下載超時"
                return False, f"Ryuu 下載失敗: {err}"
                
            manifests = res.get("manifests", {})
            lua_text = res.get("lua_content", res.get("data", ""))
            
            steam_p = steam_manager.find_steam_path()
            if not steam_p:
                return False, "找不到 Steam 安裝路徑"
            lua_dir = Path(steam_p) / "config" / "lua"
            lua_dir.mkdir(parents=True, exist_ok=True)
            
            import stat
            if lua_text:
                l_file = lua_dir / f"{appid}.lua"
                if l_file.exists():
                    try: os.chmod(l_file, stat.S_IWRITE | stat.S_IREAD)
                    except Exception: pass
                with open(l_file, "w", encoding="utf-8") as f:
                    f.write(lua_text)
                    
            cfg_lua_dir = config_manager.get_config().get("lua_dir")
            if cfg_lua_dir and Path(cfg_lua_dir).resolve() != lua_dir.resolve():
                Path(cfg_lua_dir).mkdir(parents=True, exist_ok=True)
                if lua_text:
                    cfg_l_file = Path(cfg_lua_dir) / f"{appid}.lua"
                    if cfg_l_file.exists():
                        try: os.chmod(cfg_l_file, stat.S_IWRITE | stat.S_IREAD)
                        except Exception: pass
                    with open(cfg_l_file, "w", encoding="utf-8") as f:
                        f.write(lua_text)
                        
            steam_manager.deploy_manifests_to_depotcache(manifests, steam_p, lua_dir)
            steam_manager.verify_and_sync_local_manifests(appid, steam_path=steam_p, lua_dir=lua_dir, target_manifests=manifests)
            steam_manager.sanitize_lua_manifests(appid, steam_p, lua_dir)
            steam_manager.lock_game_version(appid, steam_p)
            
            return True, f"成功透過 Ryuu 部署 {len(manifests)} 個 Manifest，並同步更新 Lua！"
        except Exception as e:
            return False, f"Ryuu 下載發生異常: {e}"

    def _deploy_from_ryuu_http(self, appid: str, progress_cb: Optional[Callable[[str], None]] = None, logger: Optional[Any] = None, official_info: Optional[Dict[str, Any]] = None, is_install: bool = False) -> Tuple[bool, str]:
        """純 Webview 模式下的 Ryuu HTTP 帶 Cookie 專用下載與部署通道 (支援預熱防 400、0 消耗預檢、記憶體完整性驗證與全自動多帳號輪替)"""
        import sqlite3, tempfile, shutil, urllib.request, time
        from pathlib import Path
        from managers import account_manager, steam_manager, config_manager, ryuu_manager, version_resolver

        appid_str = str(appid).strip()
        if not appid_str or not appid_str.isdigit():
            if logger: logger.log_error("參數校驗", f"無效或未提供 AppID: '{appid}'")
            return False, f"無效或未提供 AppID: '{appid}'"
        if official_info is None:
            try:
                official_info = version_resolver.fetch_steamdb_manifests(appid_str, timeout=4)
            except Exception:
                official_info = {}
        mgr = account_manager.get_account_manager()

        # 🌟 步驟 1：預檢與伺服器預熱 (0 額度消耗之盡力嘗試，下載端點嚴格採用標準 URL)
        if progress_cb: progress_cb("正在向 Ryuu 官方伺服器檢測可用版本與預熱清單...")
        if logger:
            logger.log_step("Ryuu預熱", f"向 Ryuu 發起 manifestinfo 預檢與預熱: {appid_str}")
        try:
            ryuu_manager.fetch_ryuu_manifest_info(appid_str)
        except Exception as pre_e:
            if logger:
                logger.log_step("Ryuu預熱", f"預熱請求異常 (非阻斷): {pre_e}", status="WARN")

        url = f"https://generator.ryuu.lol/download?appid={appid_str}"

        # 🌟 步驟 2：同步配額並過濾出真正具備有效 SQLite Session Cookie 的帳號
        try:
            mgr.sync_ryuu_quota_from_server()
        except Exception:
            pass

        all_ryuu = mgr.get_accounts("ryuu")
        active_acc = mgr.get_active_account("ryuu")
        
        valid_candidates = []
        for acc in all_ryuu:
            p_dir = Path(acc.get("profile_dir", ""))
            cookie_file = p_dir / "Cookies"
            if not cookie_file.exists() or cookie_file.stat().st_size == 0:
                continue

            cookie_hdr = ""
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
                    tmp_p = tmp.name
                shutil.copy2(cookie_file, tmp_p)
                conn = sqlite3.connect(tmp_p)
                cur = conn.cursor()
                cur.execute("SELECT name, value FROM cookies WHERE (host_key LIKE '%ryuu%' OR host_key LIKE '%generator%') AND name = 'session'")
                rows = cur.fetchall()
                conn.close()
                if os.path.exists(tmp_p): os.remove(tmp_p)
                if rows and rows[0][1]:
                    cookie_hdr = f"session={rows[0][1]}"
            except Exception as e:
                print(f"[UnifiedManifestManager] 讀取 Ryuu 帳號 [{acc.get('name')}] Cookie 異常: {e}")

            if cookie_hdr:
                is_exh = bool(acc.get("is_exhausted") or (acc.get("quota_used_today", 0) >= acc.get("daily_limit", 50)))
                valid_candidates.append({
                    "account": acc,
                    "cookie_hdr": cookie_hdr,
                    "is_exhausted": is_exh
                })

        if not valid_candidates:
            return False, "尚未綁定或登入任何有效的 Ryuu 授權憑證，請至「憑證管理」新增或登入帳號。"

        # 優先排列未耗盡帳號；活躍帳號若未耗盡則置頂
        unexhausted = [c for c in valid_candidates if not c["is_exhausted"]]
        exhausted = [c for c in valid_candidates if c["is_exhausted"]]

        if active_acc:
            for i, c in enumerate(unexhausted):
                if c["account"].get("id") == active_acc.get("id"):
                    unexhausted.insert(0, unexhausted.pop(i))
                    break

        accounts_to_try = unexhausted + exhausted

        if not unexhausted:
            reset_sec = active_acc.get("reset_in_seconds") if active_acc else None
            reset_tip = ""
            if reset_sec and reset_sec > 0:
                r_h = reset_sec // 3600
                r_m = (reset_sec % 3600) // 60
                reset_tip = f"（伺服器將在約 {r_h} 小時 {r_m} 分鐘後重設額度）"
            return False, f"所有 Ryuu 帳號今日配額均已用罄 (0/50){reset_tip}"

        last_error = ""
        total_accounts = len(accounts_to_try)

        for idx, item in enumerate(accounts_to_try):
            acc = item["account"]
            cookie_hdr = item["cookie_hdr"]
            acc_id = acc.get("id")
            acc_name = acc.get("name") or acc_id

            if progress_cb:
                progress_cb(f"正在透過 Ryuu 帳號 [{acc_name}] ({idx+1}/{total_accounts}) 下載 Manifest 打包檔...")
            if logger:
                quota_left = max(0, 50 - acc.get("quota_used_today", 0))
                logger.log_step("帳號調用", f"透過 Ryuu 帳號 [{acc_name}] ({idx+1}/{total_accounts}) 下載，本日剩餘額度: {quota_left}/50")

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://generator.ryuu.lol/",
                "Cookie": cookie_hdr
            }

            download_ok = False
            for retry in range(2):
                try:
                    if logger:
                        logger.log_network_request("Ryuu", url, method="GET", headers=headers)
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=18) as resp:
                        if resp.status != 200:
                            last_error = f"Ryuu 伺服器回應 HTTP {resp.status}"
                            if logger:
                                logger.log_step("Ryuu回應異常", f"伺服器回應非 200 狀態碼: {resp.status}", status="WARN")
                            time.sleep(0.8)
                            continue
                        data = resp.read()
                        if logger:
                            logger.log_network_response("Ryuu", resp.status, headers=dict(resp.headers), body_sample=data[:100] if data else None, byte_length=len(data) if data else 0, content_type=resp.headers.get("Content-Type", ""))
                        if not data or data[:4] != b"PK\x03\x04":
                            if logger:
                                logger.log_step("格式校驗", f"回應非標準 ZIP 二進位標頭 (前4位元組: {data[:8] if data else 'None'})", status="WARN")
                            if retry < 1:
                                time.sleep(0.8)
                                continue
                            return False, "Ryuu 伺服器目前此遊戲暫無可直接下載的 ZIP 檔案包"

                        steam_p = steam_manager.find_steam_path()
                        if not steam_p: return False, "找不到 Steam 安裝路徑"

                        lua_text, manifest_bytes_map, extracted_manifests, lua_entries, zip_err = self._extract_zip_entries_in_memory(appid_str, data)
                        if zip_err:
                            mgr.set_platform_connection_status("ryuu", False, "")
                            mgr.mark_account_valid("ryuu", acc_id)
                            mgr.record_quota_usage("ryuu", acc_id, 1)
                            mgr.set_active_account("ryuu", acc_id)
                            if logger:
                                logger.log_step("完整性校驗失敗", f"Ryuu [{acc_name}] ZIP 壓縮檔損毀 ({zip_err})", status="WARN")
                            return False, f"[INTEGRITY] {zip_err}"

                        integ = self.validate_package_integrity(
                            appid_str,
                            lua_text or "",
                            manifest_bytes_map=manifest_bytes_map,
                            steam_path=steam_p,
                            official_info=official_info,
                            is_install=is_install,
                            allow_local_tar_stub=False,
                        )
                        if not integ.get("ok"):
                            mgr.set_platform_connection_status("ryuu", False, "")
                            mgr.mark_account_valid("ryuu", acc_id)
                            mgr.record_quota_usage("ryuu", acc_id, 1)
                            mgr.set_active_account("ryuu", acc_id)
                            reason = integ.get("reason", "下載封包完整性驗證未通過")
                            if logger:
                                logger.log_step("完整性校驗失敗", f"Ryuu [{acc_name}] ({integ.get('code')}): {reason}（不寫入磁碟）", status="WARN")
                            return False, f"[INTEGRITY] {reason}"

                        self._write_validated_zip_entries(
                            appid_str, steam_p, manifest_bytes_map, extracted_manifests, lua_entries, logger=logger
                        )

                        # 🌟 同步本地 manifest_updates.json 內紀錄的 local_manifestid (最終是否為最新版由外層依據 SteamDB 比對決定)
                        try:
                            import json
                            manifest_cache_file = Path(__file__).parent.parent.parent / "data" / "manifest_updates.json"
                            if manifest_cache_file.exists():
                                cache_data = json.loads(manifest_cache_file.read_text(encoding="utf-8"))
                                if appid_str in cache_data:
                                    if "depots" in cache_data[appid_str]:
                                        for d_id, m_id in extracted_manifests.items():
                                            if d_id in cache_data[appid_str]["depots"]:
                                                cache_data[appid_str]["depots"][d_id]["local_manifestid"] = m_id
                                    manifest_cache_file.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2), encoding="utf-8")
                        except Exception as ce:
                            print(f"[UnifiedManifestManager] 更新 manifest_updates.json 快取失敗: {ce}")

                        # 🌟 成功記帳 1 次額度，並設為活躍帳號
                        mgr.set_platform_connection_status("ryuu", False, "")
                        mgr.mark_account_valid("ryuu", acc_id)
                        mgr.record_quota_usage("ryuu", acc_id, 1)
                        mgr.set_active_account("ryuu", acc_id)
                        download_ok = True
                        if logger:
                            logger.log_step("部署成功", f"成功透過 Ryuu [{acc_name}] 部署 {len(extracted_manifests)} 個 Manifest，已同步至 Steam 快取與 Lua", status="OK")
                        return True, f"成功透過 Ryuu [{acc_name}] 部署 {len(extracted_manifests)} 個 Manifest，並同步更新 Lua！"

                except urllib.error.HTTPError as he:
                    err_body = ""
                    try: err_body = he.read().decode("utf-8", errors="ignore")
                    except Exception: pass

                    if logger:
                        logger.log_network_response("Ryuu", he.code, headers=dict(he.headers) if hasattr(he, "headers") else {}, body_sample=err_body.encode("utf-8", errors="replace"), byte_length=len(err_body), content_type=getattr(he.headers, "get", lambda k, d="": "")("Content-Type", "") if hasattr(he, "headers") else "")

                    if he.code == 404:
                        mgr.set_platform_connection_status("ryuu", False, "")
                        if logger: logger.log_error("Ryuu請求", "Ryuu 官方伺服器目前未收錄此遊戲 Manifest (HTTP 404)")
                        return False, "Ryuu 官方伺服器目前未收錄此遊戲 Manifest (HTTP 404)。"
                    elif he.code == 400:
                        mgr.set_platform_connection_status("ryuu", False, "")
                        last_error = f"Ryuu 請求錯誤 (HTTP 400)"
                        if err_body:
                            try:
                                j_err = json.loads(err_body)
                                if "error" in j_err: last_error += f": {j_err['error']}"
                            except Exception: pass
                        if logger: logger.log_error("Ryuu請求", f"{last_error} (回應: {err_body[:120]})")
                        # 400 屬於遊戲端點狀態，重試一次後若仍失敗直接終止，絕不輪替其他帳號浪費額度
                        if retry < 1:
                            time.sleep(1.0)
                            continue
                        return False, last_error
                    elif he.code in (401, 403):
                        mgr.set_platform_connection_status("ryuu", False, "")
                        if "too many requests" in err_body.lower() or "rate" in err_body.lower():
                            last_error = "Ryuu 伺服器頻率限制，正在冷卻重試..."
                            if logger: logger.log_step("頻率限制", last_error, status="WARN")
                            if retry < 1:
                                time.sleep(1.2)
                                continue
                            break
                        elif "daily download limit" in err_body.lower() or "limit" in err_body.lower():
                            mgr.mark_account_exhausted("ryuu", acc_id)
                            last_error = f"Ryuu 帳號 [{acc_name}] 今日配額已滿 (50/50)"
                            if logger: logger.log_step("額度用罄", last_error, status="WARN")
                            print(f"[UnifiedManifestManager] {last_error}，正在切換下一個帳號...")
                            break
                        elif "must be logged in" in err_body.lower() or "unauthorized" in err_body.lower():
                            mgr.mark_account_expired("ryuu", acc_id)
                            last_error = f"Ryuu 帳號 [{acc_name}] 憑證過期或未登入"
                            if logger: logger.log_step("憑證過期", last_error, status="WARN")
                            print(f"[UnifiedManifestManager] {last_error}，嘗試切換下一帳號...")
                            break
                        else:
                            last_error = f"Ryuu 帳號 [{acc_name}] 伺服器回應 403 ({err_body[:60]})"
                            if logger: logger.log_step("403回應", last_error, status="WARN")
                            if retry < 1:
                                time.sleep(0.8)
                                continue
                            break
                    elif he.code >= 500:
                        mgr.set_platform_connection_status("ryuu", True, f"HTTP {he.code}")
                        last_error = f"Ryuu 伺服器臨時異常 (HTTP {he.code})"
                        if logger: logger.log_step("伺服器500異常", last_error, status="WARN")
                        if retry < 1:
                            time.sleep(1.0)
                            continue
                        break
                    else:
                        last_error = f"Ryuu 請求錯誤: HTTP {he.code}"
                        if logger: logger.log_step("HTTP異常", last_error, status="WARN")
                        if retry < 1:
                            time.sleep(0.8)
                            continue
                        break
                except Exception as e:
                    mgr.set_platform_connection_status("ryuu", True, str(e))
                    last_error = f"Ryuu HTTP 下載失敗: {e}"
                    if logger: logger.log_error("Ryuu下載異常", str(e), exc=e)
                    if retry < 1:
                        time.sleep(0.8)
                        continue

            if download_ok:
                break

        return False, last_error or "所有可用 Ryuu 帳號均無法完成下載"

    def _deploy_from_luatools_http(self, appid: str, progress_cb: Optional[Callable[[str], None]] = None, ryuu_error: str = "", logger: Optional[Any] = None, official_info: Optional[Dict[str, Any]] = None, is_install: bool = False) -> Tuple[bool, str]:
        """純 Webview 模式下的 Lua.tools HTTP 帶 Cookie 專用下載與備援部署通道 (支援多帳號、記憶體完整性驗證與來源優先級完整 ZIP 下載)"""
        import sqlite3, tempfile, shutil, urllib.request
        from pathlib import Path
        from managers import account_manager, steam_manager, version_resolver

        appid_str = str(appid).strip()
        if not appid_str or not appid_str.isdigit():
            if logger: logger.log_error("參數校驗", f"無效或未提供 AppID: '{appid}'")
            return False, f"無效或未提供 AppID: '{appid}'"
        if official_info is None:
            try:
                official_info = version_resolver.fetch_steamdb_manifests(appid_str, timeout=4)
            except Exception:
                official_info = {}
        mgr = account_manager.get_account_manager()

        accounts_to_try = mgr.get_all_valid_accounts("lua_tools")
        if not accounts_to_try:
            raw_active = mgr.get_active_account("lua_tools")
            if raw_active:
                accounts_to_try = [raw_active]
            else:
                if logger: logger.log_error("Lua.tools憑證", "尚未綁定或登入任何 Lua.tools 授權憑證")
                return False, "尚未綁定或登入任何 Lua.tools 授權憑證，請至「憑證與登入管理」新增或登入帳號。"

        last_error = ""

        steam_p = steam_manager.find_steam_path()
        if not steam_p:
            if logger: logger.log_error("Steam環境", "找不到 Steam 安裝路徑")
            return False, "找不到 Steam 安裝路徑"
        depotcache = Path(steam_p) / "depotcache"
        depotcache.mkdir(parents=True, exist_ok=True)
        lua_dir = Path(steam_p) / "config" / "lua"
        lua_dir.mkdir(parents=True, exist_ok=True)

        for acc in accounts_to_try:
            acc_id = acc.get("id")
            acc_name = acc.get("name") or acc_id
            p_dir = Path(acc.get("profile_dir", ""))
            cookie_file = p_dir / "Cookies"
            if not cookie_file.exists():
                continue

            cookie_hdr = ""
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
                    tmp_p = tmp.name
                shutil.copy2(cookie_file, tmp_p)
                conn = sqlite3.connect(tmp_p)
                cur = conn.cursor()
                cur.execute("SELECT name, value FROM cookies WHERE host_key LIKE '%lua.tools%'")
                cookies = dict(cur.fetchall())
                conn.close()
                if os.path.exists(tmp_p): os.remove(tmp_p)
                if cookies:
                    cookie_hdr = "; ".join([f"{k}={v}" for k, v in cookies.items() if v])
            except Exception as e:
                print(f"[UnifiedManifestManager] 讀取 Lua.tools 帳號 [{acc_name}] Cookie 異常: {e}")

            if not cookie_hdr:
                continue

            # 🌟 核心規範：Lua.tools 聚合平台嚴格只請求 Ryuu 來源 (杜絕 Luie 等純文字無 Manifest 來源浪費 Token 配額)
            # 先透過 0 配額消耗的 /api/manifest/check 預檢 Ryuu 是否在庫
            ryuu_avail = False
            try:
                chk_url = f"https://lua.tools/api/manifest/check?appid={appid_str}"
                chk_req = urllib.request.Request(chk_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://lua.tools/",
                    "Cookie": cookie_hdr
                })
                with urllib.request.urlopen(chk_req, timeout=6) as chk_resp:
                    chk_data = json.loads(chk_resp.read().decode("utf-8"))
                    if isinstance(chk_data, dict) and "error" not in chk_data:
                        for k, v in chk_data.items():
                            if str(k).lower() == "ryuu" and str(v).lower() in ["available", "true", "1", "ok"]:
                                ryuu_avail = True
                                break
                        if not ryuu_avail and chk_data:
                            print(f"[UnifiedManifestManager] Lua.tools 預檢顯示 Ryuu 來源未收錄 (其他來源如 Luie 無 Manifest，不予請求以節省 Token 配額)")
                            last_error = "Lua.tools 伺服器之 Ryuu 來源未收錄此遊戲 Manifest"
                            if logger: logger.log_step("Lua.tools預檢", f"Ryuu 來源未在庫 (現有來源: {list(chk_data.keys())})", status="WARN")
                            continue
            except Exception:
                ryuu_avail = True

            src = "Ryuu"
            if progress_cb:
                progress_cb(f"正在透過 Lua.tools [{acc_name}] 來源 ({src}) 下載 Manifest 完整封裝包...")
            if logger:
                logger.log_step("Lua.tools調用", f"透過帳號 [{acc_name}] (來源: {src}) 發起下載請求")

            url = f"https://lua.tools/api/manifest/download?appid={appid_str}&source={src}&game_name=Game_{appid_str}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://lua.tools/",
                "Cookie": cookie_hdr
            }

            try:
                if logger: logger.log_network_request("Lua.tools", url, method="GET", headers=headers)
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status != 200:
                        last_error = f"Lua.tools 伺服器回應 HTTP {resp.status}"
                        if logger: logger.log_step("Lua.tools回應異常", last_error, status="WARN")
                        continue
                    data = resp.read()
                    if logger:
                        logger.log_network_response("Lua.tools", resp.status, headers=dict(resp.headers), body_sample=data[:100] if data else None, byte_length=len(data) if data else 0, content_type=resp.headers.get("Content-Type", ""))
                    if not data:
                        last_error = f"Lua.tools ({src}) 回應內容為空"
                        if logger: logger.log_step("Lua.tools回應為空", last_error, status="WARN")
                        continue

                    # 檢測 ZIP 打包檔 (直接二進位或 JSON base64)
                    zip_bytes = None
                    if data[:4] == b"PK\x03\x04":
                        zip_bytes = data
                    else:
                        try:
                            j = json.loads(data.decode("utf-8", errors="ignore"))
                            if isinstance(j, dict) and "b64" in j:
                                import base64
                                b_raw = base64.b64decode(j["b64"])
                                if b_raw[:4] == b"PK\x03\x04":
                                    zip_bytes = b_raw
                        except Exception:
                            pass

                    # 成功獲取 ZIP 打包檔
                    if zip_bytes:
                        lua_text, manifest_bytes_map, extracted_manifests, lua_entries, zip_err = self._extract_zip_entries_in_memory(appid_str, zip_bytes)
                        if zip_err:
                            mgr.set_platform_connection_status("lua_tools", False, "")
                            mgr.mark_account_valid("lua_tools", acc_id)
                            mgr.record_quota_usage("lua_tools", acc_id)
                            if logger:
                                logger.log_step("完整性校驗失敗", f"Lua.tools [{acc_name}] ZIP 壓縮檔損毀 ({zip_err})", status="WARN")
                            return False, f"[INTEGRITY] {zip_err}"

                        integ = self.validate_package_integrity(
                            appid_str,
                            lua_text or "",
                            manifest_bytes_map=manifest_bytes_map,
                            steam_path=steam_p,
                            official_info=official_info,
                            is_install=is_install,
                            allow_local_tar_stub=False,
                        )
                        if not integ.get("ok"):
                            mgr.set_platform_connection_status("lua_tools", False, "")
                            mgr.mark_account_valid("lua_tools", acc_id)
                            mgr.record_quota_usage("lua_tools", acc_id)
                            reason = integ.get("reason", "下載封包完整性驗證未通過")
                            if logger:
                                logger.log_step("完整性校驗失敗", f"Lua.tools [{acc_name}] ({integ.get('code')}): {reason}（不寫入磁碟）", status="WARN")
                            return False, f"[INTEGRITY] {reason}"

                        self._write_validated_zip_entries(
                            appid_str, steam_p, manifest_bytes_map, extracted_manifests, lua_entries, logger=logger
                        )
                        mgr.set_platform_connection_status("lua_tools", False, "")
                        mgr.mark_account_valid("lua_tools", acc_id)
                        mgr.record_quota_usage("lua_tools", acc_id)

                        prefix = f"Ryuu 直連未果 ({ryuu_error})，" if ryuu_error else ""
                        if logger:
                            logger.log_step("部署成功", f"成功透過 Lua.tools [{acc_name}] (來源: {src}) 部署 {len(extracted_manifests)} 個 Manifest", status="OK")
                        return True, f"{prefix}已成功切換至 Lua.tools [{acc_name}] (來源: {src}) 部署 {len(extracted_manifests)} 個 Manifest，並同步更新 Lua！"

            except urllib.error.HTTPError as he:
                err_body = ""
                try: err_body = he.read().decode("utf-8", errors="ignore")
                except Exception: pass
                if logger:
                    logger.log_network_response("Lua.tools", he.code, headers=dict(he.headers) if hasattr(he, "headers") else {}, body_sample=err_body.encode("utf-8", errors="replace"), byte_length=len(err_body))
                if he.code == 404:
                    mgr.set_platform_connection_status("lua_tools", False, "")
                    last_error = f"Lua.tools 來源 ({src}) 未收錄"
                elif he.code in (401, 403):
                    mgr.set_platform_connection_status("lua_tools", False, "")
                    mgr.mark_account_expired("lua_tools", acc_id)
                    last_error = f"Lua.tools 帳號 [{acc_name}] 憑證過期 (HTTP {he.code})"
                    if progress_cb:
                        progress_cb(f"⚠️ Lua.tools 帳號 [{acc_name}] 憑證過期，嘗試切換下一帳號...")
                    if logger: logger.log_step("憑證過期", last_error, status="WARN")
                    break
                elif he.code == 429:
                    mgr.set_platform_connection_status("lua_tools", False, "")
                    mgr.mark_account_exhausted("lua_tools", acc_id)
                    last_error = f"Lua.tools 帳號 [{acc_name}] 配額用罄 (HTTP 429)"
                    if progress_cb:
                        progress_cb(f"⚠️ Lua.tools 帳號 [{acc_name}] 今日配額已滿，嘗試切換下一帳號...")
                    if logger: logger.log_step("配額用罄", last_error, status="WARN")
                    break
                else:
                    if he.code >= 500:
                        mgr.set_platform_connection_status("lua_tools", True, f"HTTP {he.code}")
                    last_error = f"Lua.tools 來源 ({src}) 請求錯誤: HTTP {he.code}"
                    if logger: logger.log_step("HTTP異常", last_error, status="WARN")
            except Exception as e:
                mgr.set_platform_connection_status("lua_tools", True, str(e))
                last_error = f"Lua.tools 來源 ({src}) 連線異常: {e}"
                if logger: logger.log_error("Lua.tools下載異常", str(e), exc=e)

        if not last_error:
            last_error = "Lua.tools 備援庫中目前無此遊戲之有效 Manifest 封包。"
        if logger: logger.log_error("Lua.tools失敗", last_error)
        return False, last_error


    def _update_existing_lua(self, lua_file: str, depots: Dict[str, str]):
        """改寫本地 Lua 中的 setManifestid，支援唯讀保護自動解鎖與復原"""
        try:
            if os.path.exists(lua_file):
                os.chmod(lua_file, stat.S_IWRITE | stat.S_IREAD)
            with open(lua_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            
            lines = content.splitlines()
            updated_depots = set()
            new_lines = []

            for line in lines:
                # 匹配 setManifestid(did, ...) ，無論是否有註解 (例如 -- 或 -- [清單缺失防護已停用])
                m = re.match(r'^[ \t]*(?:--[^\n\r]*?)?set[M|m]anifest[i|I]d\s*\(\s*(\d+)\s*,', line)
                if m:
                    did = m.group(1)
                    if did in depots:
                        gid = depots[did]
                        if did not in updated_depots:
                            new_lines.append(f'setManifestid({did}, "{gid}", 0)')
                            updated_depots.add(did)
                        continue
                new_lines.append(line)

            # 若有 depot 未在原檔案中出現，附加於末尾
            for did, gid in depots.items():
                if did not in updated_depots:
                    new_lines.append(f'setManifestid({did}, "{gid}", 0)')
                    updated_depots.add(did)

            content = "\n".join(new_lines)

            with open(lua_file, "w", encoding="utf-8") as f:
                f.write(content)
            
            # 鎖定 Lua 唯讀保護防 Steam 覆寫
            os.chmod(lua_file, stat.S_IREAD)
        except Exception as e:
            print(f"[UnifiedManifestManager] 更新本地 Lua 失敗: {e}")


def get_unified_manifest_manager() -> UnifiedManifestManager:
    return UnifiedManifestManager.get_instance()

