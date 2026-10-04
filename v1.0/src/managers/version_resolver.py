import os
import re
import json
import struct
import urllib.request
import datetime
from pathlib import Path

from managers import config_manager

_VERSION_CACHE_FILE = Path(__file__).parent.parent.parent / "data" / "version_cache.json"
_memory_version_cache = {}

def _load_cache():
    global _memory_version_cache
    if _memory_version_cache:
        return
    if _VERSION_CACHE_FILE.exists():
        try:
            _memory_version_cache = json.loads(_VERSION_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            _memory_version_cache = {}

def _save_cache():
    try:
        _VERSION_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _VERSION_CACHE_FILE.write_text(json.dumps(_memory_version_cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[version_resolver] Save cache failed: {e}")

def parse_manifest_creation_time(file_path) -> int | None:
    """
    直接從 Steam Depot Manifest 二進位檔案的 Metadata protobuf 中解析出
    Valve 官方伺服器在生成此特定 Manifest 時寫入的真實 Unix Timestamp (creation_time)。
    此時間戳 100% 與 SteamDB 官方資料庫上該 Manifest ID 的發布日期一致。
    """
    try:
        p = Path(file_path)
        if not p.exists():
            return None
        data = p.read_bytes()
        if len(data) < 16:
            return None
        magic, payload_len = struct.unpack('<II', data[:8])
        if magic != 0x71F617D0:
            return None
        
        # 結構: Magic(4B) + PayloadLen(4B) + Payload(payload_len) + PayloadCRC(4B) + MetaLen(4B) + Metadata
        meta_len_offset = 8 + payload_len + 4
        if meta_len_offset + 4 > len(data):
            return None
        
        meta_len, = struct.unpack('<I', data[meta_len_offset:meta_len_offset+4])
        meta_data = data[meta_len_offset+4 : meta_len_offset+4+meta_len]
        
        idx = 0
        creation_time = 0
        while idx < len(meta_data):
            key = 0; shift = 0
            while idx < len(meta_data):
                b = meta_data[idx]; idx += 1
                key |= (b & 0x7F) << shift
                if not (b & 0x80): break
                shift += 7
            f_num = key >> 3
            w_type = key & 0x07
            if f_num == 0: break
            if w_type == 0: # varint
                val = 0; shift = 0
                while idx < len(meta_data):
                    b = meta_data[idx]; idx += 1
                    val |= (b & 0x7F) << shift
                    if not (b & 0x80): break
                    shift += 7
                if f_num == 3:
                    creation_time = val
                    break
            elif w_type == 1:
                idx += 8
            elif w_type == 2:
                l = 0; shift = 0
                while idx < len(meta_data):
                    b = meta_data[idx]; idx += 1
                    l |= (b & 0x7F) << shift
                    if not (b & 0x80): break
                    shift += 7
                idx += l
            elif w_type == 5:
                idx += 4
            else:
                break
                
        if creation_time > 0:
            return creation_time
    except Exception:
        pass
    return None

def get_local_version_date(appid, lua_dir=None, steam_path=None, local_manifests=None) -> tuple[str, int]:
    """
    嚴格比對本地宣告之 Manifest 實體二進位檔案內的官方 Metadata (creation_time)，
    取得該本地版本在 Steam / SteamDB 上當初上傳/發布的真實官方日期。
    回傳: (date_str: "YYYY-MM-DD", timestamp: int)
    """
    app_id_str = str(appid).strip()
    if not lua_dir:
        lua_dir = Path(config_manager.get_config().get("lua_dir", config_manager.DEFAULT_LUA_DIR))
    else:
        lua_dir = Path(lua_dir)

    if not steam_path:
        from managers import steam_manager
        steam_path = steam_manager.find_steam_path()
    depotcache = Path(steam_path) / "depotcache" if steam_path else None

    # 1. 解析本地 Manifest 宣告
    manifest_pairs = []
    if local_manifests:
        manifest_pairs = list(local_manifests.items())
    else:
        lua_file = lua_dir / f"{app_id_str}.lua"
        if lua_file.exists():
            try:
                content = lua_file.read_text(encoding="utf-8", errors="ignore")
                manifest_pairs = re.findall(r'setManifestid\(\s*(\d+)\s*,\s*"(\d+)"', content)
            except Exception:
                pass

    # 2. 嚴格解析本地 .manifest 檔案二進位中 Valve 官方記錄的真實上傳時間 (creation_time)
    creation_timestamps = []
    if depotcache and depotcache.exists() and manifest_pairs:
        for d, m in manifest_pairs:
            mf = depotcache / f"{d}_{m}.manifest"
            if mf.exists():
                ts = parse_manifest_creation_time(mf)
                if ts:
                    creation_timestamps.append(ts)

    if creation_timestamps:
        max_ts = max(creation_timestamps)
        date_str = datetime.datetime.fromtimestamp(max_ts).strftime("%Y-%m-%d")
        return date_str, max_ts

    return "未知", 0

def resolve_manifest_version_diff(appid, local_manifests=None, local_date_ts=None, lua_dir=None, steam_path=None, timeout=6) -> dict:
    """
    精確比對本地 Manifest 與線上最新 Manifest，產出：
    - local_date (當前版本日期, YYYY-MM-DD)
    - latest_date (最新版本日期, YYYY-MM-DD)
    - version_status ("最新" 或 "跨越 X 版")
    - diff_count (跨越版本數量, int)
    - is_latest (bool)
    """
    app_id_str = str(appid).strip()
    result = {
        "appid": app_id_str,
        "local_date": "未知",
        "latest_date": "未知",
        "version_status": "未知",
        "diff_count": 0,
        "is_latest": True,
        "local_manifests": local_manifests or {},
        "latest_manifests": {}
    }

    # 1. 取得本地 Manifests 宣告
    if not local_manifests:
        if not lua_dir:
            lua_dir = Path(config_manager.get_config().get("lua_dir", config_manager.DEFAULT_LUA_DIR))
        else:
            lua_dir = Path(lua_dir)
        lua_file = lua_dir / f"{app_id_str}.lua"
        if lua_file.exists():
            try:
                txt = lua_file.read_text(encoding="utf-8", errors="ignore")
                local_manifests = dict(re.findall(r'setManifestid\(\s*(\d+)\s*,\s*"(\d+)"', txt))
            except Exception:
                local_manifests = {}
    result["local_manifests"] = local_manifests or {}

    # 2. 解析本地版本對應的真實官方發布日期
    local_date_str, auto_local_ts = get_local_version_date(app_id_str, lua_dir=lua_dir, steam_path=steam_path, local_manifests=local_manifests)
    result["local_date"] = local_date_str
    actual_local_ts = local_date_ts if local_date_ts else auto_local_ts

    # 2. 查詢 SteamDB (SteamCMD 官方數據庫) 獲取最新 Manifest 發布日期與 Manifest ID
    steamdb_manifests = {}
    steamdb_date_str = ""
    steamdb_ts = 0

    try:
        req = urllib.request.Request(
            f"https://api.steamcmd.net/v1/info/{app_id_str}",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            app_d = data.get("data", {}).get(app_id_str, {})
            pub = app_d.get("depots", {}).get("branches", {}).get("public", {})
            ts = pub.get("timeupdated") or pub.get("timebuildupdated")
            if ts:
                steamdb_ts = int(ts)
                steamdb_date_str = datetime.datetime.fromtimestamp(steamdb_ts).strftime("%Y-%m-%d")
            for d_id, d_val in app_d.get("depots", {}).items():
                if isinstance(d_val, dict) and "manifests" in d_val:
                    m_pub = d_val["manifests"].get("public")
                    if m_pub:
                        steamdb_manifests[str(d_id)] = str(m_pub.get("gid", ""))
    except Exception:
        pass

    # 3. 查詢三方聚合最新清單庫存 (GitHub + Ryuu + Lua.tools)
    from managers import unified_manifest_manager
    unified_mgr = unified_manifest_manager.get_unified_manifest_manager()
    unified_search = unified_mgr.search_all_sources(app_id_str, timeout=timeout)
    
    best_source = unified_search.get("best_source", "github")
    best_reason = unified_search.get("best_reason", "")
    
    # 取出三方各自庫存
    gh_manifests = unified_search.get("github", {}).get("depots", {})
    ryuu_manifests = unified_search.get("ryuu", {}).get("depots", {})
    
    # 決定線上最佳 Manifest ID (優先使用仲裁出的最佳來源)
    best_manifests = gh_manifests if best_source == "github" and gh_manifests else ryuu_manifests
    if not best_manifests:
        best_manifests = ryuu_manifests if ryuu_manifests else gh_manifests
    if not best_manifests and steamdb_manifests:
        best_manifests = steamdb_manifests
        
    latest_manifests = steamdb_manifests if steamdb_manifests else best_manifests
    if not latest_manifests:
        latest_manifests = best_manifests

    # 最新版本日期以 SteamDB 資料庫記載的時間為基準
    result["latest_date"] = steamdb_date_str if steamdb_date_str else "未知"
    result["latest_manifests"] = latest_manifests
    result["unified_search"] = unified_search
    result["best_source"] = best_source
    result["best_reason"] = best_reason

    # 4. 追蹤線上可用版本是否有更新 (以此決定是否能自動更新)
    has_available_update = False
    diff_update_depots = []
    if best_manifests and local_manifests:
        for d_id, b_m in best_manifests.items():
            l_m = local_manifests.get(str(d_id))
            if l_m and str(l_m) != str(b_m):
                has_available_update = True
                diff_update_depots.append((str(d_id), str(l_m), str(b_m)))

    result["ryuu_manifests"] = ryuu_manifests
    result["has_available_update"] = has_available_update
    result["ryuu_has_update"] = has_available_update # 向下相容原本 UI 欄位
    result["diff_update_depots"] = diff_update_depots

    # 比對本地 Manifest 與線上最新清單
    is_latest = True
    if local_manifests and latest_manifests:
        for d_id, l_m in local_manifests.items():
            if d_id in latest_manifests:
                if str(l_m) != str(latest_manifests[d_id]):
                    is_latest = False
                    break
    elif not local_manifests:
        is_latest = False

    result["is_latest"] = is_latest

    # 若本地版本已是最新，且先前未能從本機實體檔解析出時間戳，直接自動同步 SteamDB 官方發布時間
    if is_latest and steamdb_date_str and (result["local_date"] == "未知" or not result["local_date"]):
        result["local_date"] = steamdb_date_str
        actual_local_ts = steamdb_ts

    # 5. 計算跨越版本數
    diff_count = 0
    if not is_latest and local_manifests and latest_manifests:
        try:
            news_url = f"https://api.steampowered.com/ISteamNews/GetNewsForApp/v0002/?appid={app_id_str}&count=25&maxlength=200&format=json"
            req_news = urllib.request.Request(news_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req_news, timeout=4) as resp_news:
                news_data = json.loads(resp_news.read().decode("utf-8"))
                items = news_data.get("appnews", {}).get("newsitems", [])
                patch_items = 0
                cutoff_ts = (actual_local_ts + 86400) if actual_local_ts > 0 else 0
                for item in items:
                    item_ts = item.get("date", 0)
                    if item_ts > cutoff_ts:
                        title = item.get("title", "").lower()
                        if any(w in title for w in ["patch", "update", "hotfix", "v0.", "v1.", "v2.", "version", "notes", "changelog", "release"]):
                            patch_items += 1
                diff_count = max(1, patch_items)
        except Exception:
            diff_count = 1
    elif not is_latest:
        diff_count = 1

    result["diff_count"] = diff_count
    # 版本狀態只顯示跨越多少版本
    if is_latest or diff_count == 0:
        result["version_status"] = "0 版"
    else:
        result["version_status"] = f"舊 {diff_count} 版"

    return result

def get_cached_version(appid) -> str:
    """
    從快取中快速取得已推敲之版本字串，若無快取則回傳空字串。
    """
    _load_cache()
    info = _memory_version_cache.get(str(appid), {})
    return info.get("version_str", "")

def resolve_game_version(appid, buildid=None, timeupdated=None, timeout=5) -> dict:
    """
    透過 Steam 官方新聞與社群公告 API，比對時間戳與標題正則語義，推敲出遊戲內部版本號。
    回傳字典:
    {
        "appid": str,
        "version_str": str,        # 例如: "v1.0.63" 或 "Hotfix 2"
        "announcement_title": str, # 例如: "UPDATE 1.0.63 - Patch Notes"
        "date_str": str,           # 例如: "2026-08-18"
        "build_id": str
    }
    """
    app_id_str = str(appid).strip()
    if not app_id_str.isdigit():
        return {"appid": app_id_str, "version_str": "", "announcement_title": "", "date_str": "", "build_id": ""}

    _load_cache()
    if app_id_str in _memory_version_cache:
        cached = _memory_version_cache[app_id_str]
        if cached.get("version_str"):
            return cached

    url = f"https://api.steampowered.com/ISteamNews/GetNewsForApp/v0002/?appid={app_id_str}&count=12&maxlength=5000&format=json"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    
    best_match = {
        "appid": app_id_str,
        "version_str": "",
        "announcement_title": "",
        "date_str": "",
        "build_id": str(buildid or "")
    }

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            items = data.get('appnews', {}).get('newsitems', [])

            for it in items:
                title = it.get('title', '').strip()
                date_ts = it.get('date', 0)
                date_str = datetime.datetime.fromtimestamp(date_ts).strftime('%Y-%m-%d') if date_ts else ""
                raw_contents = it.get('contents', '')

                # 深入文字清洗：將 HTML 實體與標籤轉為空格，防止單詞與版號黏連
                clean_contents = re.sub(r'<[^>]+>', ' ', raw_contents)
                clean_contents = re.sub(r'\[\/?(?:b|i|u|h\d|list|\*|img|url|quote)[^\]]*\]', ' ', clean_contents, flags=re.IGNORECASE)
                clean_contents = re.sub(r'\s+', ' ', clean_contents)

                candidates = []

                def evaluate_text(txt, is_title=True):
                    if not txt: return

                    # 1. 最高權重：明確的 v/V 前綴且為三段式以上語義版本 (如 V1.0.503, v0.10.13.0) -> Score: 100 / 95
                    for m in re.finditer(r'\b[vV]([0-9]+(?:\.[0-9]+){2,4})\b', txt):
                        candidates.append((f"v{m.group(1)}", 100 if is_title else 95))

                    # 2. 次高權重：明確前綴宣告 (如 Patch Notes - 0.10.13.0, Version 1.0.503) -> Score: 98 / 88
                    for m in re.finditer(r'(?:patch\s*notes?|release\s*notes?|changelog|game\s*version|current\s*version)\s*[-:–—]\s*(?:v|V)?([0-9]+(?:\.[0-9]+)+)', txt, re.IGNORECASE):
                        ver = m.group(1).strip()
                        score = 98 if ver.count('.') >= 2 else 88
                        candidates.append((f"v{ver}" if not ver.lower().startswith("v") else ver, score))

                    # 3. 三段式或四段式純數字語義版本 (如 1.0.503, 0.10.13.0) -> Score: 90 / 85
                    for m in re.finditer(r'\b([0-9]+\.[0-9]+(?:\.[0-9]+){1,3})\b', txt):
                        candidates.append((f"v{m.group(1)}", 90 if is_title else 85))

                    # 4. 明確 v/V 前綴的兩段式版本 (如 v1.2, V2.0) -> Score: 80 / 70
                    for m in re.finditer(r'\b[vV]([0-9]+\.[0-9]+)\b', txt):
                        candidates.append((f"v{m.group(1)}", 80 if is_title else 70))

                    # 5. Hotfix #N -> Score: 75
                    for m in re.finditer(r'\b(?:hotfix)\s*#?([0-9]+|[a-zA-Z0-9_\-]+)\b', txt, re.IGNORECASE):
                        candidates.append((f"Hotfix {m.group(1).strip()}", 75))

                    # 6. 最低權重：Update/Patch + 兩段式浮點數 (如 Update 8.20, Patch 8.7)
                    # 此類極高機率為日期 (如 8月20日、8月7日)，給予懲罰分防止誤搶版本號！
                    for m in re.finditer(r'\b(?:update|patch)\s+([0-9]+\.[0-9]+)\b', txt, re.IGNORECASE):
                        ver = m.group(1).strip()
                        parts = ver.split('.')
                        is_likely_date = (1 <= int(parts[0]) <= 12 and 1 <= int(parts[1]) <= 31)
                        score = 30 if is_likely_date else 60
                        candidates.append((f"v{ver}", score))

                evaluate_text(title, is_title=True)
                evaluate_text(clean_contents, is_title=False)

                if candidates:
                    # 依置信度由大到小排序，同分時取版本字串較長者 (保留完整三段號)
                    candidates.sort(key=lambda x: (x[1], len(x[0])), reverse=True)
                    best_match["version_str"] = candidates[0][0]
                    best_match["announcement_title"] = title
                    best_match["date_str"] = date_str
                    break

            # 終極兜底: 若公告全文皆無版本號，但有公告時間與 BuildID
            if not best_match["version_str"] and items:
                first_item = items[0]
                date_ts = first_item.get('date', 0)
                date_str = datetime.datetime.fromtimestamp(date_ts).strftime('%m-%d') if date_ts else ""
                b_id = str(buildid or "")
                if b_id:
                    best_match["version_str"] = f"Build {b_id}"
                elif date_str:
                    best_match["version_str"] = f"更新 ({date_str})"
                best_match["announcement_title"] = first_item.get('title', '').strip()
                best_match["date_str"] = datetime.datetime.fromtimestamp(date_ts).strftime('%Y-%m-%d') if date_ts else ""

    except Exception as e:
        print(f"[version_resolver] Error for {appid}: {e}")

    if best_match["version_str"]:
        _memory_version_cache[app_id_str] = best_match
        _save_cache()

    return best_match
