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
CACHE_TTL_SECONDS = 30  # 30 秒快取，防止前端輪詢與多帳號瞬發打滿 429
FALLBACK_GRACE_PERIOD = 300  # 5 分鐘容錯寬限期

def clear_stats_cache(api_key: Optional[str] = None):
    """清除配額查詢快取"""
    global _user_stats_cache
    if api_key:
        _user_stats_cache.pop(str(api_key).strip(), None)
    else:
        _user_stats_cache.clear()

def get_api_key() -> str:
    """取得儲存的 Hubcap API Key"""
    cfg = config_manager.get_config()
    return str(cfg.get("hubcap_api_key", "")).strip()

def set_api_key(api_key: str) -> bool:
    """儲存 Hubcap API Key 到 config.json 並清空舊快取"""
    cfg = config_manager.get_config()
    cfg["hubcap_api_key"] = str(api_key).strip()
    config_manager.save_config(cfg)
    clear_stats_cache()
    return True

def get_domain() -> str:
    """取得 Hubcap 網域"""
    cfg = config_manager.get_config()
    domain = cfg.get("hubcap_domain", DEFAULT_HUBCAP_DOMAIN).strip()
    return domain.rstrip("/") if domain else DEFAULT_HUBCAP_DOMAIN

def fetch_user_stats(api_key: Optional[str] = None, force_refresh: bool = False) -> Dict[str, Any]:
    """
    調用 Hubcap 官方 GET /api/v1/user/stats 端點
    支援記憶體快取 (TTL 30s) 與暫時性網路抖動平滑回退，防止介面頻閃與 429 誤報警告
    """
    global _user_stats_cache
    key = (api_key if api_key is not None else get_api_key()).strip()
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
                "is_configured": True,
                "username": username,
                "daily_limit": daily_limit,
                "daily_usage": daily_usage,
                "remaining": remaining,
                "resets_at": data.get("resets_at", ""),
                "api_key_expires_at": data.get("api_key_expires_at", ""),
                "can_make_requests": bool(data.get("can_make_requests", True))
            }
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
            msg = "API Key 無效或已過期 (401 Unauthorized)"
            # 金鑰確已無效，清除快取
            _user_stats_cache.pop(key, None)
            return {
                "ok": False,
                "error": msg,
                "raw_error": err_body,
                "is_configured": True,
                "daily_limit": 0,
                "daily_usage": 0,
                "remaining": 0,
                "can_make_requests": False
            }
        elif he.code == 429:
            msg = "已超過請求頻率限制或配額耗盡 (429 Too Many Requests)"

        # 429 或其他暫時性 HTTP 異常：若先前有有效快取，進行寬容回退避免前端瞬間閃紅
        if cached and cached.get("last_valid_stats") and (now - cached.get("time", 0) < FALLBACK_GRACE_PERIOD):
            logger.warning("Hubcap API 請求遭遇暫時性異常 (%s)，自動回退使用有效快取資料維持顯示", msg)
            return cached["last_valid_stats"]

        return {
            "ok": False,
            "error": msg,
            "raw_error": err_body,
            "is_configured": True,
            "daily_limit": 0,
            "daily_usage": 0,
            "remaining": 0,
            "can_make_requests": False
        }
    except Exception as e:
        # 連線逾時、DNS 抖動或網路連線暫時中斷：若先前有有效快取，回退至有效快取
        if cached and cached.get("last_valid_stats") and (now - cached.get("time", 0) < FALLBACK_GRACE_PERIOD):
            logger.warning("連線至 Hubcap 發生短暫波動 (%s)，自動回退使用有效快取資料維持顯示", e)
            return cached["last_valid_stats"]

        return {
            "ok": False,
            "error": f"連線至 Hubcap 失敗: {e}",
            "is_configured": True,
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

def query_manifest_info(appid: str, api_key: Optional[str] = None, timeout: int = 8) -> Dict[str, Any]:
    """
    向 Hubcap 官方 API 詢問特定遊戲 (AppID) 的 Manifest 與 GID 收錄情況
    支援回傳格式標準化: {"available": bool, "depots": {depot_id: gid}, "version": str, "source": "HubcapDB"}
    """
    appid_str = str(appid).strip()
    if not appid_str or not appid_str.isdigit():
        return {"available": False, "depots": {}, "error": "無效 AppID"}

    key = (api_key if api_key is not None else get_api_key()).strip()
    domain = get_domain()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    if key:
        headers["Authorization"] = f"Bearer {key}"
        headers["X-Api-Key"] = key

    # 嘗試標準 API 端點格式
    test_urls = [
        f"{domain}/api/v1/manifest/{appid_str}",
        f"{domain}/api/v1/app/{appid_str}",
        f"{domain}/api/manifest?appid={appid_str}"
    ]

    for url in test_urls:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, dict):
                    # 容錯解析 depots: 可能是 data["depots"] 或是 data 直接是映射
                    depots_raw = data.get("depots") or data.get("manifests") or {}
                    extracted_depots = {}
                    if isinstance(depots_raw, dict):
                        for k, v in depots_raw.items():
                            if isinstance(v, dict):
                                gid = v.get("gid") or v.get("manifest_id") or v.get("manifestId")
                                if gid: extracted_depots[str(k)] = str(gid)
                            elif v:
                                extracted_depots[str(k)] = str(v)
                    elif isinstance(depots_raw, list):
                        for item in depots_raw:
                            if isinstance(item, dict):
                                did = item.get("depot_id") or item.get("depotId") or item.get("id")
                                gid = item.get("gid") or item.get("manifest_id") or item.get("manifestId")
                                if did and gid:
                                    extracted_depots[str(did)] = str(gid)

                    if extracted_depots:
                        return {
                            "available": True,
                            "depots": extracted_depots,
                            "source": "HubcapDB",
                            "raw": data
                        }
        except Exception:
            continue

    return {"available": False, "depots": {}, "source": "HubcapDB"}

def download_manifest_package(appid: str, api_key: Optional[str] = None, timeout: int = 25) -> Tuple[bool, Optional[bytes], str]:
    """
    向 Hubcap 下載包含 .manifest 與 .lua 之 ZIP 壓縮包二進位資料
    """
    appid_str = str(appid).strip()
    if not appid_str or not appid_str.isdigit():
        return False, None, "無效 AppID"

    key = (api_key if api_key is not None else get_api_key()).strip()
    if not key:
        return False, None, "未設定 Hubcap API Key，無法自 HubcapDB 下載"

    domain = get_domain()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Authorization": f"Bearer {key}",
        "X-Api-Key": key
    }

    # 嘗試官方標準下載端點格式
    download_urls = [
        f"{domain}/api/v1/manifest/{appid_str}/download",
        f"{domain}/download?appid={appid_str}",
        f"{domain}/api/v1/download?appid={appid_str}"
    ]

    last_err = ""
    for url in download_urls:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                # 簡單校驗是否為 ZIP (PK 開頭)
                if data and len(data) > 30 and data[:2] == b"PK":
                    return True, data, "下載成功"
                elif data:
                    try:
                        err_json = json.loads(data.decode("utf-8"))
                        last_err = err_json.get("error") or err_json.get("message") or "非 ZIP 內容"
                    except Exception:
                        last_err = f"回傳非 ZIP 內容 ({len(data)} bytes)"
        except urllib.error.HTTPError as he:
            last_err = f"HTTP {he.code}"
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

        # 核心閉環校驗與防 401 赦免
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
