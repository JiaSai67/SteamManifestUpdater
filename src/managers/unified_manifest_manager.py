import os
import re
import json
import time
import stat
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Callable

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

    def search_all_sources(self, appid: str, timeout: int = 6, steamdb_manifests: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        異步並行搜尋 Manifest 來源 (Ryuu, Lua.tools)，並以 SteamDB 官方清單為基準仲裁。
        並行執行大幅降低網路等待時間。
        """
        appid_str = str(appid).strip()
        result = {
            "appid": appid_str,
            "best_source": "ryuu",
            "best_reason": "",
            "ryuu": {"available": False, "depots": {}, "time": "未知", "is_aligned_steamdb": False},
            "luatools": {"available": False, "depots": {}, "time": "未知", "is_aligned_steamdb": False},
            "summary": ""
        }

        # 🌟 異步並行同時查詢 Ryuu 與 Lua.tools
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            fut_ryuu = executor.submit(self._query_ryuu, appid_str, timeout)
            fut_luatools = executor.submit(self._query_luatools, appid_str, timeout)

            try:
                result["ryuu"] = fut_ryuu.result()
            except Exception as e:
                print(f"[UnifiedManifestManager] Ryuu 查詢異常: {e}")

            try:
                result["luatools"] = fut_luatools.result()
            except Exception as e:
                print(f"[UnifiedManifestManager] Lua.tools 查詢異常: {e}")

        # 3. 版本比對與優先級仲裁 (基於 SteamDB 官方數據)
        self._arbitrate_best_source(result, steamdb_manifests=steamdb_manifests)
        return result

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
        try:
            cache_file = self._get_ryuu_cache_path()
            if cache_file.exists():
                c = json.loads(cache_file.read_text(encoding="utf-8"))
                return c.get(str(appid))
        except Exception:
            pass
        return None

    def _save_ryuu_cached_info(self, appid: str, data: Dict[str, Any]):
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
        - 逾時放寬至 10 秒
        - 具備短暫重試機制（遇超時/連線波動重試 1 次）
        - 具備快取兜底保護：若網路波動失敗，自動回退使用先前已知有效的庫存資料，絕不誤判為未收錄！
        - 全鏈路診斷日誌記錄到 logs/manifest_checks.log
        """
        data = {"available": False, "depots": {}, "time": "無", "branch_manifests": {}, "steamdb_target": {}}
        url = f"https://generator.ryuu.lol/manifestinfo/{appid}"
        start_t = time.time()
        max_attempts = 2
        last_error = ""

        # 放寬逾時，若傳入小於 8 則自動提升至 10 秒
        effective_timeout = max(timeout, 10)

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

                    # 成功獲取，寫入本地快取並記錄日誌
                    self._save_ryuu_cached_info(appid, data)
                    elapsed = time.time() - start_t
                    self._log_manifest_check(f"[RyuuOK] AppID: {appid}, Attempt: {attempt}, Time: {elapsed:.2f}s, Depots: {len(data['depots'])}, Available: {data['available']}")
                    return data

            except urllib.error.HTTPError as e:
                last_error = f"HTTP {e.code}"
                if e.code == 404:
                    # 伺服器明確回傳 404：確定無此遊戲，不再重試
                    break
                time.sleep(0.5)
            except Exception as e:
                last_error = str(e)
                time.sleep(0.5)

        elapsed = time.time() - start_t
        # 若所有嘗試均因網路異常失敗，啟動快取兜底保護！
        cached = self._load_ryuu_cached_info(appid)
        if cached and cached.get("available") and cached.get("depots"):
            cached["from_cache"] = True
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
                res = json.loads(resp.read().decode("utf-8"))
                if isinstance(res, dict) and "error" not in res:
                    # 🌟 嚴格只判定 Ryuu 來源 (Luie 僅提供 Lua 無 Manifest，不列入可用)
                    ryuu_ok = any(str(k).lower() == "ryuu" and str(v).lower() in ["available", "true", "1", "ok"] for k, v in res.items())
                    if ryuu_ok:
                        data["available"] = True
                        data["sources"] = ["Ryuu"]
                        data["time"] = "即時在庫 (Ryuu 來源)"
        except Exception:
            pass
        return data

    def _arbitrate_best_source(self, result: Dict[str, Any], steamdb_manifests: Optional[Dict[str, str]] = None):
        """
        仲裁哪個來源提供最新 Manifest (以 SteamDB 官方數據與 Ryuu 為最高標準)
        """
        ryuu = result["ryuu"]
        ryuu_ok = ryuu.get("available", False)
        ryuu_depots = ryuu.get("depots", {})

        # 比對 SteamDB 官方數據對齊度
        ryuu_matches_steamdb = False
        if steamdb_manifests and ryuu_depots:
            common_ryuu = [k for k in steamdb_manifests if k in ryuu_depots]
            if common_ryuu:
                ryuu_matches_steamdb = all(str(ryuu_depots[k]) == str(steamdb_manifests[k]) for k in common_ryuu)

        ryuu["is_aligned_steamdb"] = ryuu_matches_steamdb

        if ryuu_matches_steamdb:
            result["best_source"] = "ryuu"
            result["best_reason"] = "Ryuu 平台已精確同步 SteamDB 官方最新版本"
        elif ryuu_ok:
            result["best_source"] = "ryuu"
            result["best_reason"] = "Ryuu 平台已收錄可用版本"
        elif result.get("luatools", {}).get("available"):
            result["best_source"] = "luatools"
            result["best_reason"] = "Lua.tools 收錄可用腳本"
        else:
            result["best_source"] = "none"
            result["best_reason"] = "所有來源均無此遊戲 Manifest"

    def deploy_best_manifest(self, appid: str, search_result: Any = None, progress_cb: Optional[Callable[[str], None]] = None, logger: Optional[Any] = None) -> Tuple[bool, str]:
        """
        【先校驗後下載之智慧更新引擎】
        1. 前置校驗：先自檢本機 Lua 與 depotcache 實體檔案一致性 (Auto-heal)。
        2. 差異判定：若本機實體檔案已是線上平台最高收錄版本，直接完成校準，立即阻斷下載流程 (0 額度消耗)。
        3. 必要時下載：若本機確實落後於線上實體版本，才依優先級發起 Ryuu / Lua.tools 下載。
        4. 下載後閉環驗證：確保 Lua 檔案 100% 同步。
        """
        appid_str = str(appid).strip()
        if not appid_str or not appid_str.isdigit():
            if logger: logger.log_error("參數校驗", f"無效或未提供 AppID: '{appid}'")
            return False, f"無效或未提供 AppID: '{appid}'"
        from managers import steam_manager
        
        steam_p = steam_manager.find_steam_path()
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
            
        if logger:
            best_src = search_result.get("best_source", "none")
            logger.log_step("多源仲裁", f"多源仲裁最佳來源: {best_src}")
        
        # 🌟 步驟 1：前置校驗 —— 本機 Lua 宣告與 depotcache 實體檔案自檢修復
        if progress_cb: progress_cb("正在校驗本機 Lua 宣告與實體 Manifest 檔案...")
        local_check = steam_manager.verify_and_sync_local_manifests(appid_str, steam_path=steam_p)
        local_manifests = local_check.get("lua_manifests", {})
        if logger:
            logger.log_step("本地自檢", f"本地宣告: {local_manifests}, 缺失清單: {local_check.get('missing_files', [])}")
        
        # 🌟 步驟 2：前置判定 —— 檢查本機是否已經等於線上可下載實體版本且實體 .manifest 檔案完整存在
        target_depots = search_result.get("ryuu", {}).get("depots", {})
        missing_files = local_check.get("missing_files", [])
        is_synced = local_check.get("is_synced", False)

        # 🌟 拓撲檢測：檢查是否存在已棄置 Depot 待遷移
        from managers import version_resolver
        topo = version_resolver.identify_depot_topology(
            appid_str,
            local_manifests=local_manifests,
            official_manifests=search_result.get("ryuu", {}).get("steamdb_target", {}),
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

            # 🌟 核心防護：檢查本地 Lua 是否缺少金鑰！若有 Depot 宣告但缺 64 位元 Key，強制連網自 Ryuu 下載原廠配置
            if is_already_matched and steam_p:
                lua_f = Path(steam_p) / "config" / "lua" / f"{appid_str}.lua"
                if not lua_f.exists():
                    is_already_matched = False
                else:
                    try:
                        lua_txt = lua_f.read_text(encoding="utf-8", errors="ignore")
                        for d_id in target_depots.keys():
                            if str(d_id) != appid_str:
                                # 若宣告了 addappid(d_id) 但沒有帶 64 位元金鑰，視為不完整
                                has_naked_add = bool(re.search(rf'addappid\s*\(\s*{d_id}\s*\)', lua_txt))
                                has_keyed_add = bool(re.search(rf'addappid\s*\(\s*{d_id}\s*,\s*\d+\s*,\s*"[a-fA-F0-9]{{64}}"', lua_txt))
                                if has_naked_add and not has_keyed_add:
                                    is_already_matched = False
                                    print(f"[UnifiedManifestManager] 本地 Lua 缺少 Depot {d_id} 之金鑰，強制自 Ryuu 下載官方原廠打包檔！")
                                    break
                    except Exception:
                        pass
            
            if is_already_matched:
                # 確保防 401 與鎖定
                steam_manager.sanitize_lua_manifests(appid_str, steam_p)
                steam_manager.lock_game_version(appid_str, steam_p)
                is_aligned_sdb = search_result.get("ryuu", {}).get("is_aligned_steamdb", True)
                if not is_aligned_sdb:
                    msg = "本機已是第三方雲端庫目前最高收錄版本（官方最新版尚待上游同步收錄）"
                else:
                    msg = "本機 Lua 與實體 Manifest 已與線上最高收錄版本完全吻合，已完成自檢校準！"
                print(f"[UnifiedManifestManager] AppID {appid_str} {msg}")
                return True, msg

        # 🌟 優先調用高速直連且原生支援多帳號輪替的 Ryuu HTTP 授權通道
        if progress_cb: progress_cb("正在透過 Ryuu 官方授權通道下載 Manifest 與 Lua 打包檔...")
        ok, ryuu_msg = self._deploy_from_ryuu_http(appid_str, progress_cb, logger=logger)
        
        # ─────────────────────────────────────────────────────────────────
        # 🌟 下載後雙重檢驗檢驗關卡 (關卡 1: 自洽性與完整性 / 關卡 2: 官方真最新性)
        # ─────────────────────────────────────────────────────────────────
        need_hubcap_replace = False
        replace_reason = ""
        
        from managers import version_resolver, hubcap_manager
        official_manifests = {}
        try:
            sdb_info = version_resolver.fetch_steamdb_manifests(appid_str, timeout=4)
            official_manifests = sdb_info.get("manifests", {})
        except Exception:
            pass

        if ok and steam_p:
            # 關卡 1：檢查本地 Lua 宣告與實體 .manifest 是否吻合，且含完整 Depot ID 與金鑰
            local_verify = steam_manager.verify_and_sync_local_manifests(appid_str, steam_path=steam_p)
            l_manifests = local_verify.get("lua_manifests", {})
            d_manifests = local_verify.get("disk_manifests", {})
            missing_f = local_verify.get("missing_files", [])

            if missing_f or not local_verify.get("is_synced", False):
                need_hubcap_replace = True
                replace_reason = f"Ryuu 檔案自洽性未過關 (缺少實體 Manifest 或 Lua 宣告不相符: {missing_f})"
            elif official_manifests:
                # 關卡 2：比對 Manifest 是否真的是 SteamCMD 官方所示之最新版
                is_official_latest = True
                for did, off_gid in official_manifests.items():
                    cur_gid = l_manifests.get(str(did))
                    if cur_gid and str(cur_gid) != str(off_gid):
                        is_official_latest = False
                        replace_reason = f"Ryuu 版本落後於官方 (Depot {did} 本地 {cur_gid} != 官方最新 {off_gid})"
                        break
                if not is_official_latest:
                    need_hubcap_replace = True
        else:
            # Ryuu 下載失敗
            need_hubcap_replace = True
            replace_reason = f"Ryuu 伺服器下載未果: {ryuu_msg}"

        # ─────────────────────────────────────────────────────────────────
        # 🌟 觸發 Hubcap 比對與熱替換管線
        # ─────────────────────────────────────────────────────────────────
        if need_hubcap_replace:
            if logger:
                logger.log_step("Hubcap比對", f"觸發原因: {replace_reason}，向 Hubcap API 詢問最新版本...")
            if progress_cb:
                progress_cb(f"正在向 HubcapDB 詢問版本 (原因: {replace_reason})...")

            hc_info = hubcap_manager.query_manifest_info(appid_str)
            if hc_info.get("available") and hc_info.get("depots"):
                hc_depots = hc_info.get("depots", {})
                # 判定 Hubcap 是否確實為最新版或優於 Ryuu
                hc_is_better = False
                if official_manifests:
                    # 若 Hubcap 等於官方最新版
                    if any(str(hc_depots.get(k)) == str(v) for k, v in official_manifests.items() if k in hc_depots):
                        hc_is_better = True
                elif not ok:
                    hc_is_better = True

                if hc_is_better:
                    if progress_cb: progress_cb("檢測到 HubcapDB 擁有最新完整版本，正在執行熱替換下載...")
                    if logger: logger.log_step("Hubcap替換", "HubcapDB 版本優於現有檔案，執行熱替換部署...")
                    ok_hc, msg_hc = hubcap_manager.deploy_from_hubcap(appid_str, steam_path=steam_p, logger=logger)
                    if ok_hc:
                        return True, f"✨ {msg_hc}（已自動修復：{replace_reason}）"
                    else:
                        if logger: logger.log_step("Hubcap替換失敗", msg_hc, status="WARN")

        # 若 Ryuu 本身成功且 Hubcap 未能替換，直接採用 Ryuu
        if ok:
            return True, ryuu_msg

        # 若 HTTP 通道未成功且當前為 Qt 模式，嘗試 WebEngine 通道作為備援
        has_qt_app = False
        try:
            from PySide6.QtCore import QCoreApplication
            has_qt_app = (QCoreApplication.instance() is not None)
        except Exception:
            has_qt_app = False

        if has_qt_app:
            print(f"[UnifiedManifestManager] Ryuu HTTP 下載未果: {ryuu_msg}，嘗試 Qt WebEngine 通道...")
            ok_qt, qt_msg = self._deploy_from_ryuu(appid_str, progress_cb)
            if ok_qt:
                return True, qt_msg
            ryuu_msg = qt_msg

        # 🌟 核心備援機制：若 Ryuu 與 Hubcap 均未果，嘗試 Lua.tools 備援通道！
        print(f"[UnifiedManifestManager] Ryuu 與 Hubcap 下載未果，嘗試切換至 Lua.tools 備援通道...")
        if progress_cb:
            progress_cb(f"⚠️ 正在嘗試切換至 Lua.tools 備援通道...")
        if logger:
            logger.log_step("切換備援", f"Ryuu 與 Hubcap 未果，啟動 Lua.tools 備援通道", status="WARN")

        ok_lt, lt_msg = self._deploy_from_luatools_http(appid_str, progress_cb, ryuu_error=ryuu_msg, logger=logger)
        if ok_lt:
            return True, lt_msg
        else:
            return False, f"Ryuu 失敗: {ryuu_msg}；Hubcap 與 Lua.tools 備援亦未果: {lt_msg}"

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

    def _deploy_from_ryuu_http(self, appid: str, progress_cb: Optional[Callable[[str], None]] = None, logger: Optional[Any] = None) -> Tuple[bool, str]:
        """純 Webview 模式下的 Ryuu HTTP 帶 Cookie 專用下載與部署通道 (支援預熱防 400、0 消耗預檢與全自動多帳號輪替)"""
        import io, zipfile, sqlite3, tempfile, shutil, urllib.request, time
        from pathlib import Path
        from managers import account_manager, steam_manager, config_manager, ryuu_manager

        appid_str = str(appid).strip()
        if not appid_str or not appid_str.isdigit():
            if logger: logger.log_error("參數校驗", f"無效或未提供 AppID: '{appid}'")
            return False, f"無效或未提供 AppID: '{appid}'"
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
                        depotcache = Path(steam_p) / "depotcache"
                        depotcache.mkdir(parents=True, exist_ok=True)
                        lua_dir = Path(steam_p) / "config" / "lua"
                        lua_dir.mkdir(parents=True, exist_ok=True)

                        extracted_manifests = {}
                        import stat
                        with zipfile.ZipFile(io.BytesIO(data)) as zf:
                            for zname in zf.namelist():
                                if zname.endswith(".manifest"):
                                    m_bytes = zf.read(zname)
                                    m_name = Path(zname).name
                                    m_target = depotcache / m_name
                                    if m_target.exists():
                                        try: os.chmod(m_target, stat.S_IWRITE | stat.S_IREAD)
                                        except Exception: pass
                                    m_target.write_bytes(m_bytes)
                                    try:
                                        os.chmod(m_target, stat.S_IWRITE | stat.S_IREAD)  # 🌟 depotcache 永遠保持可讀寫
                                    except Exception: pass
                                    # 永久備份至 Steam/config/depotcache
                                    try:
                                        c_backup = Path(steam_p) / "config" / "depotcache"
                                        c_backup.mkdir(parents=True, exist_ok=True)
                                        c_backup_file = c_backup / m_name
                                        if c_backup_file.exists():
                                            try: os.chmod(c_backup_file, stat.S_IWRITE | stat.S_IREAD)
                                            except Exception: pass
                                        c_backup_file.write_bytes(m_bytes)
                                        try:
                                            os.chmod(c_backup_file, stat.S_IREAD)  # 🌟 備援金庫設為唯讀保護
                                        except Exception: pass
                                        if logger:
                                            logger.log_file_op("永久備份 Manifest", str(c_backup_file), size=len(m_bytes), success=True, details="寫入永久金庫 (防 Steam 解除安裝刪除)")
                                    except Exception as be:
                                        if logger:
                                            logger.log_file_op("永久備份 Manifest", str(Path(steam_p) / "config" / "depotcache" / m_name), size=len(m_bytes), success=False, details=str(be))
                                    m_parts = m_name.replace(".manifest", "").split("_")
                                    if len(m_parts) == 2:
                                        extracted_manifests[m_parts[0]] = m_parts[1]
                                    if logger:
                                        logger.log_file_op("解壓寫入 Manifest", str(m_target), size=len(m_bytes), success=True, details=f"Depot: {m_parts[0] if len(m_parts)==2 else 'Unknown'}, Manifest: {m_parts[1] if len(m_parts)==2 else m_name}")
                                elif zname.endswith(".lua"):
                                    l_bytes = zf.read(zname)
                                    l_path = lua_dir / Path(zname).name
                                    if l_path.exists():
                                        try: os.chmod(l_path, stat.S_IWRITE | stat.S_IREAD)
                                        except Exception: pass
                                    l_path.write_bytes(l_bytes)
                                    # 同步至 config/stplug-in (SteamTools 目錄)
                                    st_lua = Path(steam_p) / "config" / "stplug-in"
                                    if st_lua.exists():
                                        try:
                                            st_l_path = st_lua / Path(zname).name
                                            if st_l_path.exists():
                                                try: os.chmod(st_l_path, stat.S_IWRITE | stat.S_IREAD)
                                                except Exception: pass
                                            st_l_path.write_bytes(l_bytes)
                                        except Exception: pass
                                    # 同步至自訂 lua 目錄
                                    cfg_lua = config_manager.get_config().get("lua_dir")
                                    if cfg_lua and Path(cfg_lua).resolve() != lua_dir.resolve():
                                        try:
                                            Path(cfg_lua).mkdir(parents=True, exist_ok=True)
                                            cfg_l_path = Path(cfg_lua) / Path(zname).name
                                            if cfg_l_path.exists():
                                                try: os.chmod(cfg_l_path, stat.S_IWRITE | stat.S_IREAD)
                                                except Exception: pass
                                            cfg_l_path.write_bytes(l_bytes)
                                        except Exception: pass
                                    # 🌟 自動解析並永久快取 64 位元 Depot 解密金鑰
                                    try:
                                        l_text = l_bytes.decode("utf-8", errors="ignore")
                                        for km in re.finditer(r'addappid\s*\(\s*(\d+)\s*,\s*\d+\s*,\s*"([a-fA-F0-9]{64})"', l_text):
                                            k_did, k_val = km.group(1), km.group(2)
                                            if self._depot_keys_cache is None: self._depot_keys_cache = {}
                                            self._depot_keys_cache[k_did] = k_val
                                    except Exception:
                                        pass
                                    if logger:
                                        logger.log_file_op("解壓寫入 Lua", str(l_path), size=len(l_bytes), success=True, details="主設定檔")

                        # 🌟 核心閉環驗證：以剛部署的真實 Manifest 檔案更新並閉環校準 Lua (含棄置 Depot 自動遷移)
                        steam_manager.sync_lua_with_deployed_manifests(
                            appid_str, manifests_dict=extracted_manifests, lua_dir=lua_dir
                        )
                        steam_manager.verify_and_sync_local_manifests(
                            appid_str, steam_path=steam_p, lua_dir=lua_dir, target_manifests=extracted_manifests
                        )
                        steam_manager.sanitize_lua_manifests(appid_str, steam_p, lua_dir)
                        steam_manager.lock_game_version(appid_str, steam_p)

                        # 🌟 更新本地 manifest_updates.json 快取狀態為最新版
                        try:
                            import json
                            manifest_cache_file = Path(__file__).parent.parent.parent / "data" / "manifest_updates.json"
                            if manifest_cache_file.exists():
                                cache_data = json.loads(manifest_cache_file.read_text(encoding="utf-8"))
                                if appid_str in cache_data:
                                    cache_data[appid_str]["has_update"] = False
                                    cache_data[appid_str]["version_status"] = "最新版"
                                    if "depots" in cache_data[appid_str]:
                                        for d_id, m_id in extracted_manifests.items():
                                            if d_id in cache_data[appid_str]["depots"]:
                                                cache_data[appid_str]["depots"][d_id]["local_manifestid"] = m_id
                                    manifest_cache_file.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2), encoding="utf-8")
                        except Exception as ce:
                            print(f"[UnifiedManifestManager] 更新 manifest_updates.json 快取失敗: {ce}")

                        # 🌟 成功記帳 1 次額度，並設為活躍帳號
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
                        if logger: logger.log_error("Ryuu請求", "Ryuu 官方伺服器目前未收錄此遊戲 Manifest (HTTP 404)")
                        return False, "Ryuu 官方伺服器目前未收錄此遊戲 Manifest (HTTP 404)。"
                    elif he.code == 400:
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
                    last_error = f"Ryuu HTTP 下載失敗: {e}"
                    if logger: logger.log_error("Ryuu下載異常", str(e), exc=e)
                    if retry < 1:
                        time.sleep(0.8)
                        continue

            if download_ok:
                break

        return False, last_error or "所有可用 Ryuu 帳號均無法完成下載"

    def _deploy_from_luatools_http(self, appid: str, progress_cb: Optional[Callable[[str], None]] = None, ryuu_error: str = "", logger: Optional[Any] = None) -> Tuple[bool, str]:
        """純 Webview 模式下的 Lua.tools HTTP 帶 Cookie 專用下載與備援部署通道 (支援多帳號與來源優先級完整 ZIP 下載)"""
        import io, zipfile, sqlite3, tempfile, shutil, urllib.request, stat
        from pathlib import Path
        from managers import account_manager, steam_manager, config_manager

        appid_str = str(appid).strip()
        if not appid_str or not appid_str.isdigit():
            if logger: logger.log_error("參數校驗", f"無效或未提供 AppID: '{appid}'")
            return False, f"無效或未提供 AppID: '{appid}'"
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
                        extracted_manifests = {}
                        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                            for zname in zf.namelist():
                                if zname.endswith(".manifest"):
                                    m_bytes = zf.read(zname)
                                    m_name = Path(zname).name
                                    m_target = depotcache / m_name
                                    if m_target.exists():
                                        try: os.chmod(m_target, stat.S_IWRITE | stat.S_IREAD)
                                        except Exception: pass
                                    m_target.write_bytes(m_bytes)
                                    try:
                                        import stat
                                        os.chmod(m_target, stat.S_IWRITE | stat.S_IREAD)  # 🌟 depotcache 永遠保持可讀寫
                                    except Exception: pass
                                    # 永久備份至 Steam/config/depotcache
                                    try:
                                        c_backup = Path(steam_p) / "config" / "depotcache"
                                        c_backup.mkdir(parents=True, exist_ok=True)
                                        c_backup_file = c_backup / m_name
                                        if c_backup_file.exists():
                                            try: os.chmod(c_backup_file, stat.S_IWRITE | stat.S_IREAD)
                                            except Exception: pass
                                        c_backup_file.write_bytes(m_bytes)
                                        try:
                                            os.chmod(c_backup_file, stat.S_IREAD)  # 🌟 備援金庫設為唯讀保護
                                        except Exception: pass
                                        if logger:
                                            logger.log_file_op("永久備份 Manifest", str(c_backup_file), size=len(m_bytes), success=True, details="寫入永久金庫 (防 Steam 解除安裝刪除)")
                                    except Exception as be:
                                        if logger:
                                            logger.log_file_op("永久備份 Manifest", str(Path(steam_p) / "config" / "depotcache" / m_name), size=len(m_bytes), success=False, details=str(be))
                                    m_parts = m_name.replace(".manifest", "").split("_")
                                    if len(m_parts) == 2:
                                        extracted_manifests[m_parts[0]] = m_parts[1]
                                    if logger:
                                        logger.log_file_op("解壓寫入 Manifest", str(m_target), size=len(m_bytes), success=True, details=f"Depot: {m_parts[0] if len(m_parts)==2 else 'Unknown'}, Manifest: {m_parts[1] if len(m_parts)==2 else m_name}")
                                elif zname.endswith(".lua"):
                                    l_bytes = zf.read(zname)
                                    l_path = lua_dir / Path(zname).name
                                    if l_path.exists():
                                        try: os.chmod(l_path, stat.S_IWRITE | stat.S_IREAD)
                                        except Exception: pass
                                    l_path.write_bytes(l_bytes)
                                    # 同步至 config/stplug-in
                                    st_lua = Path(steam_p) / "config" / "stplug-in"
                                    if st_lua.exists():
                                        try:
                                            st_l_path = st_lua / Path(zname).name
                                            if st_l_path.exists():
                                                try: os.chmod(st_l_path, stat.S_IWRITE | stat.S_IREAD)
                                                except Exception: pass
                                            st_l_path.write_bytes(l_bytes)
                                        except Exception: pass
                                    if logger:
                                        logger.log_file_op("解壓寫入 Lua", str(l_path), size=len(l_bytes), success=True, details="主設定檔")

                        # 🌟 自動閉環校驗並鎖定
                        steam_manager.verify_and_sync_local_manifests(
                            appid_str, steam_path=steam_p, lua_dir=lua_dir, target_manifests=extracted_manifests
                        )
                        steam_manager.sanitize_lua_manifests(appid_str, steam_p, lua_dir)
                        steam_manager.lock_game_version(appid_str, steam_p)
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
                    last_error = f"Lua.tools 來源 ({src}) 未收錄"
                elif he.code in (401, 403):
                    mgr.mark_account_expired("lua_tools", acc_id)
                    last_error = f"Lua.tools 帳號 [{acc_name}] 憑證過期 (HTTP {he.code})"
                    if progress_cb:
                        progress_cb(f"⚠️ Lua.tools 帳號 [{acc_name}] 憑證過期，嘗試切換下一帳號...")
                    if logger: logger.log_step("憑證過期", last_error, status="WARN")
                    break
                elif he.code == 429:
                    mgr.mark_account_exhausted("lua_tools", acc_id)
                    last_error = f"Lua.tools 帳號 [{acc_name}] 配額用罄 (HTTP 429)"
                    if progress_cb:
                        progress_cb(f"⚠️ Lua.tools 帳號 [{acc_name}] 今日配額已滿，嘗試切換下一帳號...")
                    if logger: logger.log_step("配額用罄", last_error, status="WARN")
                    break
                else:
                    last_error = f"Lua.tools 來源 ({src}) 請求錯誤: HTTP {he.code}"
                    if logger: logger.log_step("HTTP異常", last_error, status="WARN")

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

