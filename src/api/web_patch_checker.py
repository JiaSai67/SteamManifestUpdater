import os
import time
import json
import urllib.request
import urllib.parse
import re
import ssl
from pathlib import Path
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}

_CACHE_FILE = Path(__file__).parent.parent.parent / "data" / "cache" / "web_patch_cache.json"
_patch_memory_cache = {}

# 內建精準補丁收錄種子庫 (涵蓋 1.0 記載與社群熱門補丁映射)
_SEED_PATCHES = {
    "4005220": {
        "onlinefix": "",
        "zeigames": "https://zeigames.com/files/file/2805-deep-blue-sushi-online-fix/"
    },
    "deep blue sushi": {
        "onlinefix": "",
        "zeigames": "https://zeigames.com/files/file/2805-deep-blue-sushi-online-fix/"
    }
}

def _load_cache():
    global _patch_memory_cache
    if _patch_memory_cache:
        return
    if _CACHE_FILE.exists():
        try:
            _patch_memory_cache = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            _patch_memory_cache = {}

def _save_cache():
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(_patch_memory_cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[web_patch_checker] Save cache failed: {e}")

def normalize_title(text):
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'online[-_\s]*fix', '', text)
    text = re.sub(r'po[-_\s]*seti', '', text)
    text = re.sub(r'fix[-_\s]*repair', '', text)
    text = re.sub(r'[^a-z0-9]', '', text)
    return text

def is_matching(game_name, candidate_slug):
    t_norm = normalize_title(game_name)
    c_norm = normalize_title(candidate_slug)
    if not t_norm or not c_norm:
        return False
    if t_norm == c_norm:
        return True
    if t_norm in c_norm or c_norm in t_norm:
        return SequenceMatcher(None, t_norm, c_norm).ratio() >= 0.60
    return SequenceMatcher(None, t_norm, c_norm).ratio() >= 0.75

def _search_ddg_for_site(query: str, domain_pattern: str) -> list:
    """
    透過 DuckDuckGo HTML 索引搜尋引擎爬取目標站點連結，避開 WAF / 403 阻擋。
    """
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    req = urllib.request.Request(url, headers=HEADERS)
    candidates = []
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=4.0) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            for m in re.findall(rf'href=["\'](https?://[^"\']*{domain_pattern}[^"\']*)["\']', html):
                candidates.append(m)
            for u in re.findall(r'uddg=([^&\'"]+)', html):
                try:
                    unq = urllib.parse.unquote(u)
                    if domain_pattern in unq:
                        candidates.append(unq)
                except Exception:
                    pass
    except Exception:
        pass
    return candidates

def check_zeigames(game_name, appid=None):
    if not game_name or str(game_name).startswith("App_"):
        return None
    
    clean_name = str(game_name).strip()
    norm_name = clean_name.lower()
    appid_str = str(appid).strip() if appid else ""

    # 0. 檢查種子資料庫
    if appid_str and appid_str in _SEED_PATCHES and _SEED_PATCHES[appid_str].get("zeigames"):
        return _SEED_PATCHES[appid_str]["zeigames"]
    if norm_name in _SEED_PATCHES and _SEED_PATCHES[norm_name].get("zeigames"):
        return _SEED_PATCHES[norm_name]["zeigames"]

    # 1. 嘗試官方站內搜尋
    encoded = urllib.parse.quote_plus(clean_name)
    url = f"https://zeigames.com/search/?q={encoded}&type=downloads_file"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=3.0) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            matches = re.findall(r'href=["\'](https://zeigames\.com/files/file/(\d+)-([^"\'/?#]+)/?)["\']', html)
            for full_url, file_id, slug in matches:
                clean_url = f"https://zeigames.com/files/file/{file_id}-{slug}/"
                if is_matching(clean_name, slug):
                    return clean_url
    except Exception:
        pass

    # 2. DuckDuckGo 索引搜尋備援 (避開 Cloudflare 403)
    query = f'site:zeigames.com/files/file/ "{clean_name}"'
    candidates = _search_ddg_for_site(query, 'zeigames.com/files/file/')
    for cand_url in candidates:
        m = re.search(r'zeigames\.com/files/file/(\d+)-([^/?#"\']+)', cand_url)
        if m:
            file_id = m.group(1)
            slug = m.group(2)
            clean_url = f"https://zeigames.com/files/file/{file_id}-{slug}/"
            if is_matching(clean_name, slug):
                return clean_url

    return None

def check_onlinefix(game_name, appid=None):
    if not game_name or str(game_name).startswith("App_"):
        return None
    
    clean_name = str(game_name).strip()
    norm_name = clean_name.lower()
    appid_str = str(appid).strip() if appid else ""

    # 0. 檢查種子資料庫
    if appid_str and appid_str in _SEED_PATCHES and _SEED_PATCHES[appid_str].get("onlinefix"):
        return _SEED_PATCHES[appid_str]["onlinefix"]
    if norm_name in _SEED_PATCHES and _SEED_PATCHES[norm_name].get("onlinefix"):
        return _SEED_PATCHES[norm_name]["onlinefix"]

    # 1. 嘗試官方站內搜尋 (在線狀態精準解析)
    url = "https://online-fix.me/index.php?do=search"
    data = urllib.parse.urlencode({
        'do': 'search',
        'subaction': 'search',
        'story': clean_name,
        'search_start': 0,
        'full_search': 0,
        'result_from': 1
    }).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=3.5) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            matches = re.findall(r'href=["\'](https://online-fix\.me/games/[^/]+/(\d+)-([^"\']+)\.html)["\']', html)
            for full_url, post_id, slug in matches:
                if is_matching(clean_name, slug):
                    return full_url
    except Exception:
        pass

    # 2. DuckDuckGo 備援
    query = f'site:online-fix.me "{clean_name}"'
    candidates = _search_ddg_for_site(query, 'online-fix.me/games/')
    for cand_url in candidates:
        m = re.search(r'online-fix\.me/games/[^/]+/(\d+)-([^/\.]*)\.html', cand_url)
        if m:
            slug = m.group(2)
            if is_matching(clean_name, slug):
                return cand_url

    return None

def is_url_alive(url: str, timeout: float = 3.0) -> bool:
    """發送輕量 HEAD 請求快速驗證目標補丁網址是否依然存活，防止文章被刪除/404下架"""
    if not url:
        return False
    try:
        req = urllib.request.Request(url, headers=HEADERS, method='HEAD')
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            return resp.status < 400
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return False
        # 若站點不支援 HEAD 則以 GET 測試
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                return resp.status < 400
        except Exception:
            return False
    except Exception:
        return False


def is_patch_cache_valid(entry: dict) -> bool:
    """
    檢查補丁快取項是否依然有效：
    - 已收錄 (available == True)：TTL 為 7 天 (604800s)
    - 未收錄 (available == False)：TTL 為 24 小時 (86400s)
    """
    if not isinstance(entry, dict):
        return False
    now = time.time()
    
    # 支援新舊格式相容
    of = entry.get("onlinefix", {})
    zg = entry.get("zeigames", {})
    updated_at = entry.get("_updated_at", 0)
    
    if not updated_at:
        # 舊版無時間戳快取，視為過期需校驗
        return False
        
    has_any = of.get("available") or zg.get("available")
    ttl = 604800 if has_any else 86400
    return (now - updated_at) < ttl


def check_all_web_patches(game_name: str, appid: str = None, force_refresh: bool = False, on_step = None) -> dict:
    """
    並行查詢 Online-Fix 與 ZeiGames 是否收錄該遊戲補丁。
    具備智慧架構：
    1. 非對稱 TTL 快取 (已收錄 7 天 / 未收錄 24 小時)
    2. 目標存活校驗探針 (防止文章被站長刪除或 404 死鏈)
    3. 英文名稱優先與強制刷新支援 (force_refresh)
    4. 支援動態進度回調 (on_step)
    """
    import time
    _load_cache()
    clean_name = str(game_name or "").strip()
    appid_str = str(appid or "").strip()
    cache_key = f"{appid_str}:{clean_name}" if appid_str else clean_name

    if not clean_name or clean_name.startswith("App_"):
        return {
            "onlinefix": {"name": "Online-Fix", "available": False, "url": ""},
            "zeigames": {"name": "ZeiGames", "available": False, "url": ""}
        }

    # 1. 命中快取且未過期時直接使用 (0 延遲)
    if not force_refresh:
        cached = _patch_memory_cache.get(cache_key) or _patch_memory_cache.get(clean_name) or (appid_str and _patch_memory_cache.get(appid_str))
        if cached and is_patch_cache_valid(cached):
            # 若快取記錄為已收錄，但已超過 3 天，進行背景或輕量死鏈抽檢
            of_url = cached.get("onlinefix", {}).get("url")
            zg_url = cached.get("zeigames", {}).get("url")
            
            # 若 URL 存在但驗證已失效 (例如被刪除 404)，則觸發重新搜尋
            urls_to_check = [u for u in [of_url, zg_url] if u]
            is_dead = False
            for u in urls_to_check:
                if not is_url_alive(u, timeout=2.0):
                    is_dead = True
                    break
            if not is_dead:
                if on_step:
                    on_step("zeigames")
                return cached

    of_url = None
    zg_url = None

    with ThreadPoolExecutor(max_workers=2) as executor:
        fut_of = executor.submit(check_onlinefix, clean_name, appid_str)
        fut_zg = executor.submit(check_zeigames, clean_name, appid_str)
        try:
            of_url = fut_of.result(timeout=5.0)
        except Exception:
            of_url = None
        if on_step:
            on_step("zeigames")
        try:
            zg_url = fut_zg.result(timeout=5.0)
        except Exception:
            zg_url = None

    # 二次死鏈防護：確保爬取到的網址確實存活
    if of_url and not is_url_alive(of_url, timeout=2.5):
        of_url = None
    if zg_url and not is_url_alive(zg_url, timeout=2.5):
        zg_url = None

    now_ts = int(time.time())
    result = {
        "_updated_at": now_ts,
        "onlinefix": {
            "name": "Online-Fix",
            "available": bool(of_url),
            "url": of_url or ""
        },
        "zeigames": {
            "name": "ZeiGames",
            "available": bool(zg_url),
            "url": zg_url or ""
        }
    }

    _patch_memory_cache[cache_key] = result
    _patch_memory_cache[clean_name] = result
    if appid_str:
        _patch_memory_cache[appid_str] = result
    _save_cache()

    return result

def get_known_patch_appids():
    """
    自記憶體、磁碟快取與種子庫中快速彙整已確認收錄補丁的 AppID 集合
    回傳: (onlinefix_appids_set, zeigames_appids_set)
    """
    _load_cache()
    of_set = set()
    zg_set = set()

    # 1. 種子資料庫
    for k, v in _SEED_PATCHES.items():
        if k.isdigit():
            if v.get("onlinefix"):
                of_set.add(k)
            if v.get("zeigames"):
                zg_set.add(k)

    # 2. 磁碟與記憶體快取
    for k, v in _patch_memory_cache.items():
        if not isinstance(v, dict):
            continue
        aid = ""
        if k.isdigit():
            aid = k
        elif ":" in k:
            parts = k.split(":", 1)
            if parts[0].isdigit():
                aid = parts[0]

        if aid:
            if v.get("onlinefix", {}).get("available"):
                of_set.add(aid)
            if v.get("zeigames", {}).get("available"):
                zg_set.add(aid)

    return of_set, zg_set
