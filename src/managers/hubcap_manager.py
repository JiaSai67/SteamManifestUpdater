"""
HubcapDB (hubcapmanifest.com) 管理模組
提供 Hubcap Manifest 平台的 API 認證、配額查詢、連線測試與 Manifest / Lua 下載支援。
"""

import json
import logging
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from managers import config_manager

logger = logging.getLogger("hubcap_manager")

DEFAULT_HUBCAP_DOMAIN = "https://hubcapmanifest.com"

# 快取結構: {api_key: {"time": float, "stats": dict, "last_valid_stats": dict}}
_user_stats_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 5  # 5 秒短快取，兼顧即時檢測與防止同瞬間重複請求
FALLBACK_GRACE_PERIOD = 0  # 連線異常時直接回報 Error，不以歷史數字掩蓋異常

def clean_api_key(raw_key: Optional[str]) -> str:
    """標準化清理使用者貼上的 HubcapDB API Key (去除隱形空白、換行、引號與重複 Bearer 前綴)"""
    if not raw_key:
        return ""
    val = str(raw_key).strip().strip('"').strip("'").strip()
    while val.lower().startswith("bearer "):
        val = val[7:].strip().strip('"').strip("'").strip()
    return val

def clear_stats_cache(api_key: Optional[str] = None):
    """清除配額查詢快取"""
    global _user_stats_cache
    if api_key:
        _user_stats_cache.pop(clean_api_key(api_key), None)
    else:
        _user_stats_cache.clear()

def get_api_key() -> str:
    """取得儲存的 Hubcap API Key (支援 config.json 與 accounts_registry.json 自動雙向橋接自癒)"""
    cfg = config_manager.get_config()
    key = clean_api_key(cfg.get("hubcap_api_key", ""))
    if key:
        if key != str(cfg.get("hubcap_api_key", "")):
            cfg["hubcap_api_key"] = key
            config_manager.save_config(cfg)
        return key

    # 🌟 自癒橋接：若 config.json 尚未同步，主動從 account_manager 檢查是否已有綁定金鑰
    try:
        from managers import account_manager
        fallback_key = clean_api_key(account_manager.get_account_manager().get_any_hubcap_key())
        if fallback_key:
            cfg["hubcap_api_key"] = fallback_key
            config_manager.save_config(cfg)
            return fallback_key
    except Exception:
        pass
    return ""

def set_api_key(api_key: str) -> bool:
    """儲存 Hubcap API Key 到 config.json 並清空舊快取與錯誤狀態"""
    global _manifest_zip_cache
    clean = clean_api_key(api_key)
    cfg = config_manager.get_config()
    cfg["hubcap_api_key"] = clean
    config_manager.save_config(cfg)
    clear_stats_cache()
    _manifest_zip_cache.clear()
    try:
        from managers import account_manager
        account_manager.get_account_manager().set_platform_connection_status("hubcap", False, "")
    except Exception:
        pass
    # 清理負向磁碟快取，確保新設定金鑰後查詢立即生效
    try:
        cf = _get_hubcap_cache_file()
        if cf.exists():
            c_data = json.loads(cf.read_text(encoding="utf-8"))
            if isinstance(c_data, dict):
                cleaned_cache = {k: v for k, v in c_data.items() if isinstance(v, dict) and v.get("available")}
                if len(cleaned_cache) != len(c_data):
                    cf.write_text(json.dumps(cleaned_cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return True

def get_domain() -> str:
    """取得 Hubcap 網域"""
    cfg = config_manager.get_config()
    domain = cfg.get("hubcap_domain", DEFAULT_HUBCAP_DOMAIN).strip()
    return domain.rstrip("/") if domain else DEFAULT_HUBCAP_DOMAIN

def fetch_user_stats(api_key: Optional[str] = None, force_refresh: bool = False, _allow_heal: bool = True) -> Dict[str, Any]:
    """
    調用 Hubcap 官方 GET /api/v1/user/stats 端點
    支援記憶體快取與多儲存源金鑰分裂自癒 (若主金鑰 401 過期，自動檢索 accounts_registry 內新綁定之有效金鑰並同步)
    """
    global _user_stats_cache
    current_cfg_key = get_api_key()
    key = clean_api_key(api_key) if api_key is not None else current_cfg_key
    if not key:
        return {
            "ok": False,
            "error": "未設定 Hubcap API Key",
            "is_configured": False,
            "daily_limit": 0,
            "daily_usage": 0,
            "remaining": 0,
            "can_make_requests": False
        }

    now = time.time()
    cached = _user_stats_cache.get(key)
    if not force_refresh and cached:
        # 若快取尚在 TTL 內且結果正常，直接返回快取
        if (now - cached.get("time", 0) < CACHE_TTL_SECONDS) and cached.get("stats", {}).get("ok"):
            return cached["stats"]

    domain = get_domain()
    url = f"{domain}/api/v1/user/stats"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            daily_limit = int(data.get("daily_limit") or data.get("role_daily_limit") or 25)
            daily_usage = int(data.get("daily_usage", 0))
            # 官方 API 給予 daily_limit 與 daily_usage，剩餘配額由兩者相減計算
            remaining = max(0, daily_limit - daily_usage)
            username = str(data.get("username", "")).strip()

            res = {
                "ok": True,
                "is_valid": True,
                "connection_error": False,
                "is_configured": True,
                "username": username,
                "daily_limit": daily_limit,
                "daily_usage": daily_usage,
                "remaining": remaining,
                "resets_at": data.get("resets_at", ""),
                "api_key_expires_at": data.get("api_key_expires_at", ""),
                "can_make_requests": bool(data.get("can_make_requests", True)) and (remaining > 0),
                "quota_exhausted": (remaining <= 0)
            }
            try:
                from managers import account_manager
                account_manager.get_account_manager().set_platform_connection_status("hubcap", False, "")
            except Exception:
                pass
            # 更新快取
            _user_stats_cache[key] = {
                "time": now,
                "stats": res,
                "last_valid_stats": res
            }
            return res
    except urllib.error.HTTPError as he:
        err_body = ""
        try:
            err_body = he.read().decode("utf-8")
        except Exception:
            pass
        msg = f"HTTP {he.code}"
        if he.code == 401:
            # 🌟 金鑰分裂自癒：若失敗的是當前系統舊金鑰，自動掃描 accounts_registry.json 是否存有使用者新填寫的有效金鑰！
            if _allow_heal and (api_key is None or key == current_cfg_key):
                try:
                    from managers import account_manager
                    mgr = account_manager.get_account_manager()
                    alt_keys = [k for k in mgr.get_all_unique_hubcap_keys() if clean_api_key(k) and clean_api_key(k) != key]
                    for alt_k in reversed(alt_keys):
                        clean_alt = clean_api_key(alt_k)
                        alt_res = fetch_user_stats(clean_alt, force_refresh=True, _allow_heal=False)
                        if alt_res.get("ok"):
                            logger.info("自動自癒救回有效 HubcapDB API Key 並同步至全域設定")
                            set_api_key(clean_alt)
                            mgr.clear_all_hubcap_keys()
                            mgr.set_hubcap_key("hubcap_default", clean_alt)
                            _user_stats_cache[clean_alt] = {
                                "time": time.time(),
                                "stats": alt_res,
                                "last_valid_stats": alt_res
                            }
                            return alt_res
                except Exception as heal_e:
                    logger.debug("Hubcap 金鑰自癒檢測異常: %s", heal_e)

            msg = "API Key 無效或已過期 (401 Unauthorized)"
            try:
                from managers import account_manager
                account_manager.get_account_manager().set_platform_connection_status("hubcap", False, "")
            except Exception:
                pass
            # 金鑰確已無效，清除快取
            _user_stats_cache.pop(key, None)
            return {
                "ok": False,
                "connection_error": False,
                "error": msg,
                "raw_error": err_body,
                "is_configured": True,
                "is_valid": False,
                "daily_limit": 0,
                "daily_usage": 0,
                "remaining": 0,
                "can_make_requests": False
            }
        elif he.code == 429:
            msg = "已超過請求頻率限制或今日配額耗盡 (429 Too Many Requests)"
            try:
                from managers import account_manager
                account_manager.get_account_manager().set_platform_connection_status("hubcap", False, "")
            except Exception:
                pass
            prev_limit = 25
            if cached and cached.get("last_valid_stats"):
                prev_limit = cached["last_valid_stats"].get("daily_limit") or 25
            res_429 = {
                "ok": True,
                "connection_error": False,
                "is_configured": True,
                "is_valid": True,
                "quota_exhausted": True,
                "daily_limit": prev_limit,
                "daily_usage": prev_limit,
                "remaining": 0,
                "can_make_requests": False,
                "error": msg,
                "raw_error": err_body
            }
            _user_stats_cache[key] = {
                "time": now,
                "stats": res_429,
                "last_valid_stats": res_429
            }
            return res_429

        # 其他 HTTP 異常 (如 521 / 5xx)：標記連線異常並直接回傳 Error 狀態
        _user_stats_cache.pop(key, None)
        try:
            from managers import account_manager
            account_manager.get_account_manager().set_platform_connection_status("hubcap", True, msg)
        except Exception:
            pass
        return {
            "ok": False,
            "connection_error": True,
            "error": msg,
            "raw_error": err_body,
            "is_configured": True,
            "is_valid": False,
            "daily_limit": 0,
            "daily_usage": 0,
            "remaining": 0,
            "can_make_requests": False
        }
    except Exception as e:
        # 連線逾時、DNS 抖動或網路連線中斷：標記連線異常並直接回傳 Error 狀態
        _user_stats_cache.pop(key, None)
        err_str = f"連線至 Hubcap 失敗: {e}"
        try:
            from managers import account_manager
            account_manager.get_account_manager().set_platform_connection_status("hubcap", True, str(e))
        except Exception:
            pass
        return {
            "ok": False,
            "connection_error": True,
            "error": err_str,
            "is_configured": True,
            "is_valid": False,
            "daily_limit": 0,
            "daily_usage": 0,
            "remaining": 0,
            "can_make_requests": False
        }

def test_connection(api_key: Optional[str] = None) -> Dict[str, Any]:
    """測試 HubcapDB 平台連線與金鑰有效性 (強制即時發出請求)"""
    start_t = time.time()
    stats = fetch_user_stats(api_key, force_refresh=True)
    latency_ms = int((time.time() - start_t) * 1000)
    
    if stats.get("ok"):
        rem = stats.get("remaining", 0)
        lim = stats.get("daily_limit", 0)
        return {
            "ok": True,
            "latency_ms": latency_ms,
            "msg": f"HubcapDB 連線正常！延遲 {latency_ms}ms · 剩餘配額: {rem} / {lim} 次",
            "stats": stats
        }
    else:
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "msg": f"HubcapDB 測試失敗: {stats.get('error', '未知錯誤')}",
            "stats": stats
        }

_manifest_zip_cache: Dict[str, Dict[str, Any]] = {}

def _get_hubcap_cache_file() -> Path:
    p = config_manager._root_dir / "data" / "cache" / "hubcap_manifest_cache.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

def _load_hubcap_cached_info(appid: str) -> Optional[Dict[str, Any]]:
    try:
        cf = _get_hubcap_cache_file()
        if cf.exists():
            c = json.loads(cf.read_text(encoding="utf-8"))
            return c.get(str(appid))
    except Exception:
        pass
    return None

def _save_hubcap_cached_info(appid: str, data: Dict[str, Any]):
    try:
        cf = _get_hubcap_cache_file()
        c = {}
        if cf.exists():
            try:
                c = json.loads(cf.read_text(encoding="utf-8"))
            except Exception:
                c = {}
        c[str(appid)] = data
        cf.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def query_manifest_info(appid: str, api_key: Optional[str] = None, timeout: int = 10, use_cache: bool = True, cache_ttl: int = 120) -> Dict[str, Any]:
    """
    向 Hubcap 官方免費純查詢 API 詢問特定遊戲 (AppID) 的 Manifest 與 GID 收錄情況（0 配額消耗）。
    🌟 核心規範：嚴格只呼叫官方 free: true 的純查詢端點：
       1. GET /api/v1/manifest/{appid}/contents （列出壓縮包內所有 depot_id 與 manifest_id，不下載 ZIP、不扣每日 25 次配額）
       2. GET /api/v1/status/{appid} （查詢檔案狀態與遊戲名稱，不扣配額）
    絕不在此函式呼叫 /api/v1/manifest/{appid} 下載端點，確保搜尋與比對 100% 零配額消耗！
    支援回傳格式: {"available": bool, "depots": {depot_id: gid}, "source": "HubcapDB", "last_modified": str, "time": str}
    """
    appid_str = str(appid).strip()
    if not appid_str or not appid_str.isdigit():
        return {"available": False, "depots": {}, "error": "無效 AppID"}

    key = clean_api_key(api_key) if api_key is not None else get_api_key()
    if not key:
        cached = _load_hubcap_cached_info(appid_str)
        if cached and cached.get("available") and cached.get("depots"):
            cached = dict(cached)
            cached["from_cache"] = True
            return cached
        return {
            "available": False,
            "depots": {},
            "source": "HubcapDB",
            "quota_exhausted": False,
            "connection_error": False,
            "error": "未設定 Hubcap API Key"
        }

    # 短期快取命中（僅命中有效在庫或明確 404 未收錄紀錄，預設 120 秒內同一遊戲不重複發送網路請求）
    if use_cache:
        cached_early = _load_hubcap_cached_info(appid_str)
        if cached_early and (time.time() - float(cached_early.get("cached_at", 0)) < cache_ttl):
            if cached_early.get("available") or cached_early.get("error") == "未收錄":
                res_early = dict(cached_early)
                res_early["from_cache"] = True
                return res_early

    domain = get_domain()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Authorization": f"Bearer {key}"
    }

    # 🌟 官方 0 配額免費查詢端點：首選 /api/v1/manifest/{appid}/contents (free: true)
    free_contents_url = f"{domain}/api/v1/manifest/{appid_str}/contents"
    free_status_url = f"{domain}/api/v1/status/{appid_str}"

    quota_exhausted = False
    last_err = ""

    # 1. 查詢 /api/v1/manifest/{appid}/contents (0 配額消耗，直接取得所有 Depot ID 與 Manifest GID)
    try:
        req = urllib.request.Request(free_contents_url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            if data:
                json_data = json.loads(data.decode("utf-8"))
                if isinstance(json_data, dict):
                    try:
                        from managers import account_manager
                        account_manager.get_account_manager().set_platform_connection_status("hubcap", False, "")
                    except Exception:
                        pass

                    depots_raw = json_data.get("manifests") or json_data.get("depots") or []
                    extracted_depots = {}
                    if isinstance(depots_raw, list):
                        for item in depots_raw:
                            if isinstance(item, dict):
                                did = item.get("depot_id") or item.get("depotId") or item.get("id")
                                gid = item.get("manifest_id") or item.get("gid") or item.get("manifestId")
                                if did and gid:
                                    extracted_depots[str(did).strip()] = str(gid).strip()
                    elif isinstance(depots_raw, dict):
                        for k, v in depots_raw.items():
                            if isinstance(v, dict):
                                gid = v.get("manifest_id") or v.get("gid") or v.get("manifestId")
                                if gid:
                                    extracted_depots[str(k).strip()] = str(gid).strip()
                            elif v:
                                extracted_depots[str(k).strip()] = str(v).strip()

                    zip_exists = bool(json_data.get("zip_exists", bool(extracted_depots)))
                    last_mod = str(json_data.get("last_modified", "")).strip()
                    time_disp = last_mod[:16].replace("T", " ") if last_mod else "即時在庫"

                    if extracted_depots and zip_exists:
                        res_ok = {
                            "available": True,
                            "depots": extracted_depots,
                            "source": "HubcapDB",
                            "has_zip": zip_exists,
                            "file_size": int(json_data.get("file_size") or 0),
                            "last_modified": last_mod,
                            "time": time_disp,
                            "branch": str(json_data.get("branch", "public")),
                            "quota_exhausted": False,
                            "cached_at": time.time()
                        }
                        _save_hubcap_cached_info(appid_str, res_ok)
                        return res_ok
                    else:
                        res_not_found = {
                            "available": False,
                            "depots": {},
                            "source": "HubcapDB",
                            "has_zip": False,
                            "quota_exhausted": False,
                            "connection_error": False,
                            "error": "未收錄",
                            "cached_at": time.time()
                        }
                        _save_hubcap_cached_info(appid_str, res_not_found)
                        return res_not_found
    except urllib.error.HTTPError as he:
        last_err = f"HTTP {he.code}"
        if he.code == 401 and api_key is None:
            # 觸發金鑰自癒檢測，若救回有效新金鑰則立即重試一次免費查詢
            heal_st = fetch_user_stats(force_refresh=True)
            new_k = get_api_key()
            if heal_st.get("ok") and new_k and new_k != key:
                return query_manifest_info(appid_str, api_key=new_k, timeout=timeout, use_cache=False, cache_ttl=cache_ttl)
        if he.code == 404:
            try:
                from managers import account_manager
                account_manager.get_account_manager().set_platform_connection_status("hubcap", False, "")
            except Exception:
                pass
            res_404 = {
                "available": False,
                "depots": {},
                "source": "HubcapDB",
                "has_zip": False,
                "quota_exhausted": False,
                "connection_error": False,
                "error": "未收錄",
                "cached_at": time.time()
            }
            _save_hubcap_cached_info(appid_str, res_404)
            return res_404
        elif he.code == 429:
            # 僅代表觸發每分鐘速率限制 (Rate Limit)
            last_err = "請求頻率過高 (HTTP 429)"
    except Exception as e:
        last_err = str(e)
        logger.debug("嘗試 Hubcap 免費端點 %s 失敗: %s", free_contents_url, e)

    # 2. 備援：查詢 /api/v1/status/{appid} (同樣為 free: true 0 配額端點)
    try:
        req_st = urllib.request.Request(free_status_url, headers=headers)
        with urllib.request.urlopen(req_st, timeout=timeout) as resp_st:
            st_data = json.loads(resp_st.read().decode("utf-8"))
            if isinstance(st_data, dict):
                try:
                    from managers import account_manager
                    account_manager.get_account_manager().set_platform_connection_status("hubcap", False, "")
                except Exception:
                    pass
                is_avail = (st_data.get("status") == "available") and bool(st_data.get("manifest_file_exists"))
                if not is_avail:
                    res_unavail = {
                        "available": False,
                        "depots": {},
                        "source": "HubcapDB",
                        "game_name": str(st_data.get("game_name", "")).strip(),
                        "quota_exhausted": False,
                        "connection_error": False,
                        "error": "未收錄",
                        "cached_at": time.time()
                    }
                    _save_hubcap_cached_info(appid_str, res_unavail)
                    return res_unavail
    except urllib.error.HTTPError as he:
        if he.code == 404:
            res_404 = {
                "available": False,
                "depots": {},
                "source": "HubcapDB",
                "quota_exhausted": False,
                "connection_error": False,
                "error": "未收錄",
                "cached_at": time.time()
            }
            _save_hubcap_cached_info(appid_str, res_404)
            return res_404
        last_err = f"HTTP {he.code}"
    except Exception as e:
        last_err = str(e)

    is_conn_err = bool(last_err and not quota_exhausted and last_err != "HTTP 404")
    if is_conn_err:
        clear_stats_cache()
        try:
            from managers import account_manager
            account_manager.get_account_manager().set_platform_connection_status("hubcap", True, last_err)
        except Exception:
            pass

    # 🌟 若連線失敗，嘗試自磁碟快取兜底
    cached = _load_hubcap_cached_info(appid_str)
    if cached and cached.get("available") and cached.get("depots"):
        cached = dict(cached)
        cached["from_cache"] = True
        cached["quota_exhausted"] = quota_exhausted
        if is_conn_err:
            cached["connection_error"] = True
            cached["error_msg"] = last_err
        return cached

    return {
        "available": False, 
        "depots": {}, 
        "source": "HubcapDB", 
        "quota_exhausted": quota_exhausted,
        "connection_error": is_conn_err,
        "error": last_err or "未收錄"
    }

def search_hubcap_games(query: str, by_appid: bool = False, limit: int = 50, api_key: Optional[str] = None, timeout: int = 8) -> Dict[str, Any]:
    """
    呼叫 HubcapDB 官方免費搜尋端點 GET /api/v1/search (free: true，0 配額消耗)。
    支援以遊戲名稱或精確 AppID (by_appid=True) 搜尋 HubcapDB 收錄之遊戲與封面。
    """
    import urllib.parse
    q_str = str(query).strip()
    if len(q_str) < 3:
        return {"ok": False, "results": [], "count": 0, "error": "搜尋字串至少需 3 個字元"}

    key = clean_api_key(api_key) if api_key is not None else get_api_key()
    if not key:
        return {"ok": False, "results": [], "count": 0, "error": "未設定 Hubcap API Key"}

    domain = get_domain()
    appid_flag = "true" if by_appid else "false"
    url = f"{domain}/api/v1/search?q={urllib.parse.quote(q_str)}&limit={int(limit)}&appid={appid_flag}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Authorization": f"Bearer {key}"
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results", []) if isinstance(data, dict) else []
            return {
                "ok": True,
                "query": q_str,
                "count": int(data.get("count", len(results))) if isinstance(data, dict) else len(results),
                "results": results
            }
    except Exception as e:
        return {"ok": False, "results": [], "count": 0, "error": str(e)}

def batch_check_library(app_ids: list, include_adult: bool = True, api_key: Optional[str] = None, timeout: int = 10) -> Dict[str, Any]:
    """
    呼叫 HubcapDB 官方免費批量檢查端點 POST /api/v1/library (free: true，0 配額消耗)。
    一次最多可傳入 5,000 個 AppID，快速回傳哪些 AppID 在 HubcapDB 有可用 Manifest。
    """
    clean_ids = [int(str(x).strip()) for x in (app_ids or []) if str(x).strip().isdigit()]
    if not clean_ids:
        return {"ok": True, "available": {}, "missing": [], "available_count": 0}

    key = clean_api_key(api_key) if api_key is not None else get_api_key()
    if not key:
        return {"ok": False, "available": {}, "missing": clean_ids, "error": "未設定 Hubcap API Key"}

    domain = get_domain()
    url = f"{domain}/api/v1/library"
    payload = json.dumps({"app_ids": clean_ids[:5000], "include_adult": bool(include_adult)}).encode("utf-8")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}"
    }
    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            avail_list = data.get("available", []) if isinstance(data, dict) else []
            avail_map = {str(item.get("app_id")): item for item in avail_list if isinstance(item, dict) and item.get("app_id")}
            return {
                "ok": True,
                "available": avail_map,
                "missing": data.get("missing", []) if isinstance(data, dict) else [],
                "available_count": len(avail_map)
            }
    except Exception as e:
        return {"ok": False, "available": {}, "missing": clean_ids, "error": str(e)}

def download_manifest_package(appid: str, api_key: Optional[str] = None, timeout: int = 25) -> Tuple[bool, Optional[bytes], str]:
    """
    向 Hubcap 下載包含 .manifest 與 .lua 之 ZIP 壓縮包二進位資料。
    優先命中 query_manifest_info 所暫存之記憶體二進位資料，實現 0 延遲且節省配額。
    """
    appid_str = str(appid).strip()
    if not appid_str or not appid_str.isdigit():
        return False, None, "無效 AppID"

    # 1. 優先檢查記憶體暫存 (120 秒內有效)
    cached = _manifest_zip_cache.get(appid_str)
    if cached and (time.time() - cached.get("time", 0) < 120) and cached.get("data"):
        return True, cached["data"], "下載成功 (命中記憶體暫存)"

    key = clean_api_key(api_key) if api_key is not None else get_api_key()
    if not key:
        return False, None, "未設定 Hubcap API Key，無法自 HubcapDB 下載"

    domain = get_domain()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Authorization": f"Bearer {key}"
    }

    # 官方標準下載端點：GET /api/v1/manifest/{appid}
    download_urls = [
        f"{domain}/api/v1/manifest/{appid_str}",
        f"{domain}/api/v1/manifest/{appid_str}/download"
    ]

    last_err = ""
    for url in download_urls:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                # 校驗是否為標準 ZIP (PK 開頭)
                if data and len(data) > 30 and data.startswith(b"PK"):
                    # 寫入短暫記憶體快取，並立即清除配額統計快取以便即時反映已扣除配額
                    _manifest_zip_cache[appid_str] = {
                        "time": time.time(),
                        "data": data
                    }
                    clear_stats_cache()
                    return True, data, "下載成功"
                elif data:
                    try:
                        err_json = json.loads(data.decode("utf-8"))
                        last_err = err_json.get("error") or err_json.get("message") or "非 ZIP 內容"
                    except Exception:
                        last_err = f"回傳非 ZIP 內容 ({len(data)} bytes)"
                    break
        except urllib.error.HTTPError as he:
            err_detail = ""
            try:
                raw_b = he.read().decode("utf-8", errors="ignore")
                if raw_b:
                    j_b = json.loads(raw_b)
                    if isinstance(j_b, dict):
                        err_detail = str(j_b.get("error") or j_b.get("message") or "").strip()
            except Exception:
                pass
            if he.code == 401:
                if api_key is None:
                    heal_st = fetch_user_stats(force_refresh=True)
                    new_k = get_api_key()
                    if heal_st.get("ok") and new_k and new_k != key:
                        return download_manifest_package(appid_str, api_key=new_k, timeout=timeout)
                last_err = f"Hubcap API Key 無效或已過期 (401{': ' + err_detail if err_detail else ''})"
                clear_stats_cache()
                break
            elif he.code == 403:
                last_err = f"Hubcap 權限不足或已達上限 (403{': ' + err_detail if err_detail else ''})"
                clear_stats_cache()
                break
            elif he.code == 404:
                last_err = f"HubcapDB 尚未收錄此遊戲 Manifest (404{': ' + err_detail if err_detail else ''})"
                break
            elif he.code == 429:
                last_err = f"Hubcap 今日額度已用罄或頻率受限 (429{': ' + err_detail if err_detail else ''})"
                clear_stats_cache()
                break
            else:
                last_err = f"HTTP {he.code}{(': ' + err_detail) if err_detail else ''}"
        except Exception as e:
            last_err = str(e)

    return False, None, f"Hubcap 下載未果: {last_err}"

def deploy_from_hubcap(appid: str, steam_path: Optional[str] = None, api_key: Optional[str] = None, logger: Optional[Any] = None) -> Tuple[bool, str]:
    """
    從 Hubcap 下載並實體部署 Manifest、永久金庫備份、Lua 腳本與 ACF 防 401 鎖定
    """
    import io, zipfile, stat, os, re
    from managers import steam_manager, config_manager

    appid_str = str(appid).strip()
    ok, zip_bytes, err = download_manifest_package(appid_str, api_key=api_key)
    if not ok or not zip_bytes:
        if logger: logger.log_error("Hubcap下載", err)
        return False, err

    sp = steam_path or steam_manager.find_steam_path()
    if not sp:
        return False, "找不到本機 Steam 目錄"

    depotcache = Path(sp) / "depotcache"
    depotcache.mkdir(parents=True, exist_ok=True)
    c_backup = Path(sp) / "config" / "depotcache"
    c_backup.mkdir(parents=True, exist_ok=True)
    lua_dir = Path(sp) / "config" / "lua"
    lua_dir.mkdir(parents=True, exist_ok=True)

    extracted_manifests = {}
    try:
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
                    try: os.chmod(m_target, stat.S_IWRITE | stat.S_IREAD)
                    except Exception: pass

                    # 永久金庫備份
                    c_backup_file = c_backup / m_name
                    if c_backup_file.exists():
                        try: os.chmod(c_backup_file, stat.S_IWRITE | stat.S_IREAD)
                        except Exception: pass
                    c_backup_file.write_bytes(m_bytes)
                    try: os.chmod(c_backup_file, stat.S_IREAD)
                    except Exception: pass

                    m_parts = m_name.replace(".manifest", "").split("_")
                    if len(m_parts) == 2:
                        extracted_manifests[m_parts[0]] = m_parts[1]
                elif zname.endswith(".lua"):
                    l_bytes = zf.read(zname)
                    l_path = lua_dir / Path(zname).name
                    if l_path.exists():
                        try: os.chmod(l_path, stat.S_IWRITE | stat.S_IREAD)
                        except Exception: pass
                    l_path.write_bytes(l_bytes)

                    # 同步到 stplug-in
                    st_lua = Path(sp) / "config" / "stplug-in"
                    if st_lua.exists():
                        try:
                            st_l_path = st_lua / Path(zname).name
                            if st_l_path.exists():
                                try: os.chmod(st_l_path, stat.S_IWRITE | stat.S_IREAD)
                                except Exception: pass
                            st_l_path.write_bytes(l_bytes)
                        except Exception: pass

                    # 同步至使用者自訂 lua 目錄
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

        # 核心閉環校驗與防 401 赦免
        steam_manager.sync_lua_with_deployed_manifests(
            appid_str, manifests_dict=extracted_manifests, lua_dir=lua_dir
        )
        steam_manager.verify_and_sync_local_manifests(
            appid_str, steam_path=sp, lua_dir=lua_dir, target_manifests=extracted_manifests
        )
        steam_manager.sanitize_lua_manifests(appid_str, sp, lua_dir)
        steam_manager.lock_game_version(appid_str, sp)

        # 更新本地 manifest_updates.json 快取狀態
        try:
            manifest_cache_file = Path(__file__).parent.parent.parent / "data" / "manifest_updates.json"
            if manifest_cache_file.exists():
                cache_data = json.loads(manifest_cache_file.read_text(encoding="utf-8"))
                if appid_str in cache_data:
                    cache_data[appid_str]["has_update"] = False
                    cache_data[appid_str]["version_status"] = "最新版"
                    cache_data[appid_str]["best_source"] = "hubcap"
                    manifest_cache_file.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        if logger:
            logger.log_step("部署成功", f"成功自 HubcapDB 部署 {len(extracted_manifests)} 個 Manifest，並完成自檢與鎖定", status="OK")

        return True, f"成功自 HubcapDB 部署 {len(extracted_manifests)} 個 Manifest，已完全替換本地檔案！"
    except Exception as e:
        if logger: logger.log_error("部署異常", str(e))
        return False, f"解壓或部署 Hubcap 檔案失敗: {e}"
