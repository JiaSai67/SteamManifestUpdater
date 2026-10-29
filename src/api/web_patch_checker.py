import os
import time
import json
import urllib.request
import urllib.parse
import unicodedata
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

_BASE_DIR = Path(__file__).parent.parent.parent
_CACHE_FILE = _BASE_DIR / "data" / "cache" / "web_patch_cache.json"
_GAME_CACHE_FILE = _BASE_DIR / "data" / "game_cache.json"
_STEAMDB_CACHE_DIR = _BASE_DIR / "data" / "steamdb_cache"
_CACHE_SCHEMA_VER = 3
_patch_memory_cache = {}

_CJK_RE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u30ff\uac00-\ud7af]')
_NOISE_SUFFIX_RE = re.compile(
    r'(online[-_\s]*fix|po[-_\s]*seti|na[-_\s]*dvoih|fix[-_\s]*repair|free[-_\s]*download|full[-_\s]*version|steam[-_\s]*rip|repack)',
    flags=re.IGNORECASE
)
_NOISE_TOKENS = {"po", "seti", "poseti", "na", "dvoih", "nadvoih", "onlinefix", "fixrepair", "freedownload", "repack", "steamrip"}

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

def _is_valid_english_name(name: str) -> bool:
    """判斷名稱是否為有效的英文搜尋名稱（含至少 2 個英文字母且不含中日韓文字或 App_ 前綴）"""
    if not name or not isinstance(name, str):
        return False
    s = name.strip()
    if not s or s.startswith("App_"):
        return False
    if _CJK_RE.search(s):
        return False
    return len(re.findall(r'[a-zA-Z]', s)) >= 2

def resolve_english_game_name(game_name: str, appid: str = "") -> str:
    """
    確保取得用於外網 (online-fix.me / zeigames.com) 搜尋的英文遊戲名稱：
    若傳入的 game_name 含有中文字元、為空或為 App_xxx，自動從本地 game_cache、steamdb_cache 或 Steam 商店英文 API 解析真實英文名。
    """
    raw_name = str(game_name or "").strip()
    aid = str(appid or "").strip()

    if _is_valid_english_name(raw_name):
        return raw_name

    if not aid or not aid.isdigit():
        return raw_name

    # 1. 檢查 data/game_cache.json
    try:
        if _GAME_CACHE_FILE.exists():
            g_cache = json.loads(_GAME_CACHE_FILE.read_text(encoding="utf-8"))
            c_info = g_cache.get(aid, {})
            if isinstance(c_info, dict):
                for key in ("english_name", "name_en", "name"):
                    cand = str(c_info.get(key) or "").strip()
                    if _is_valid_english_name(cand):
                        return cand
    except Exception:
        pass

    # 2. 檢查 data/steamdb_cache/{aid}.json
    try:
        sdb_path = _STEAMDB_CACHE_DIR / f"{aid}.json"
        if sdb_path.exists():
            sdb_data = json.loads(sdb_path.read_text(encoding="utf-8"))
            if isinstance(sdb_data, dict):
                for key in ("english_name", "name_en", "name"):
                    cand = str(sdb_data.get(key) or "").strip()
                    if _is_valid_english_name(cand):
                        return cand
    except Exception:
        pass

    # 3. 向 Steam 商店 API 查詢英文名稱 (l=english) 並回寫至 game_cache.json
    try:
        url = f"https://store.steampowered.com/api/appdetails?appids={aid}&l=english"
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=4.0) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            if data and str(aid) in data and data[str(aid)].get("success"):
                en_name = str(data[str(aid)].get("data", {}).get("name") or "").strip()
                if en_name:
                    try:
                        g_cache = {}
                        if _GAME_CACHE_FILE.exists():
                            g_cache = json.loads(_GAME_CACHE_FILE.read_text(encoding="utf-8"))
                        c_info = g_cache.get(aid, {})
                        if not isinstance(c_info, dict):
                            c_info = {"name": en_name}
                        c_info["english_name"] = en_name
                        c_info["name_en"] = en_name
                        if not c_info.get("name") or str(c_info.get("name")).startswith("App_"):
                            c_info["name"] = en_name
                        g_cache[aid] = c_info
                        _GAME_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                        _GAME_CACHE_FILE.write_text(json.dumps(g_cache, ensure_ascii=False, indent=2), encoding="utf-8")
                    except Exception:
                        pass
                    return en_name
    except Exception:
        pass

    return raw_name

def strip_special_chars(text: str, keep_cjk: bool = True) -> str:
    """
    嚴格剔除所有特殊字元、Emoji (如 🍕)、商標符號 (™/®/©)、俄文後綴 (如 по сети) 與標點符號，
    僅保留英文 (a-zA-Z)、中文 (\\u4e00-\\u9fff) 與數字 (0-9)。
    注意：使用 NFD 僅剝離拉丁字母重音符，嚴禁使用 NFKD (避免將 ™ 拆解成英文字母 TM 導致 'Solarpunk™' 變成 'SolarpunkTM')。
    """
    if not text:
        return ""
    s = unicodedata.normalize('NFD', str(text))
    s = re.sub(r'[\u0300-\u036f]+', '', s)
    if keep_cjk:
        s = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]+', ' ', s)
    else:
        s = re.sub(r'[^a-zA-Z0-9]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def clean_search_query(text: str) -> str:
    """
    清理搜尋關鍵字：剔除所有特殊字元、Emoji (如 🍕)、商標符號 (™/®/©)，僅保留英文、中文與數字。
    若字串中已含英文字母，針對外網搜尋自動提取純英數關鍵字，避免中英混雜影響外網檢索。
    """
    if not text:
        return ""
    s = str(text).strip()
    s = re.sub(r'\s*[\(\[\{]\s*(demo|prologue|playtest|beta)\s*[\)\]\}]\s*', ' ', s, flags=re.IGNORECASE)
    s = re.sub(r"['’‘`]", "", s)
    if re.search(r'[a-zA-Z]', s):
        return strip_special_chars(s, keep_cjk=False)
    return strip_special_chars(s, keep_cjk=True)

def get_search_queries(game_name: str) -> list:
    """產生主搜尋詞與備援簡化搜尋詞（規避副標題、撇號或特殊符號差異）"""
    queries = []
    q1 = clean_search_query(game_name)
    if q1:
        queries.append(q1)
    raw = str(game_name or "").strip()
    # 若含副標題分隔符 (: 或 - )，加入主標題作為備援搜尋詞
    if ":" in raw or " - " in raw or " – " in raw:
        main_part = re.split(r'[:]| - | – ', raw, maxsplit=1)[0].strip()
        q_main = clean_search_query(main_part)
        if q_main and len(q_main) >= 4 and q_main not in queries:
            queries.append(q_main)
    # 若含所有格 's，加入去除 's 的詞幹版本
    if re.search(r"['’‘`]s\b", raw, flags=re.IGNORECASE):
        no_pos = re.sub(r"['’‘`]s\b", "", raw, flags=re.IGNORECASE)
        q_nopos = clean_search_query(no_pos)
        if q_nopos and q_nopos not in queries:
            queries.append(q_nopos)
    return queries

def _extract_tokens(text: str, keep_cjk: bool = True) -> list:
    """將遊戲名稱、專欄標題或網址 slug 剔除特殊字元，僅提取小寫英文、中文與數字單詞列表"""
    if not text:
        return []
    s = str(text).lower().strip()
    s = re.sub(r'\.(html|htm|php)$', '', s)
    s = re.sub(r'^\d+-', '', s)
    s = _NOISE_SUFFIX_RE.sub(' ', s)
    s = re.sub(r"['’‘`]", "", s)
    s = unicodedata.normalize('NFD', s)
    s = re.sub(r'[\u0300-\u036f]+', '', s)
    pattern = r'[a-z0-9\u4e00-\u9fff]+' if keep_cjk else r'[a-z0-9]+'
    tokens = re.findall(pattern, s)
    return [t for t in tokens if t not in _NOISE_TOKENS]

def normalize_title(text, keep_cjk: bool = True):
    """將遊戲名稱或標題正規化（剔除特殊字元，僅保留英文、中文與數字）"""
    if not text:
        return ""
    return "".join(_extract_tokens(text, keep_cjk=keep_cjk))

def _match_token_lists(t_tokens: list, c_tokens: list, raw_game_name: str = "") -> bool:
    if not t_tokens or not c_tokens:
        return False

    extra_tail_words = {"online", "coop", "multiplayer", "lan", "fix", "steam", "download", "free", "game"}
    c_filtered = list(c_tokens)
    while len(c_filtered) > len(t_tokens) and c_filtered[-1] in extra_tail_words and c_filtered[-1] not in t_tokens:
        c_filtered.pop()

    t_norm = "".join(t_tokens)
    c_norm = "".join(c_tokens)
    c_clean = "".join(c_filtered)

    if not t_norm or not c_clean:
        return False

    # 1. 正規化後完全一致 (例如 'Solarpunk™' -> 'solarpunk' == 'Solarpunk по сети' -> 'solarpunk')
    if t_norm == c_norm or t_norm == c_clean:
        return True

    # 2. 主標題比對 (例如含副標題之遊戲)
    if ":" in raw_game_name or " - " in raw_game_name or " – " in raw_game_name:
        main_part = re.split(r'[:]| - | – ', raw_game_name, maxsplit=1)[0].strip()
        main_norm = normalize_title(main_part, keep_cjk=False) or normalize_title(main_part, keep_cjk=True)
        if len(main_norm) >= 5 and (main_norm == c_clean or main_norm == c_norm):
            return True

    # 3. 包含關係且長度比例合理
    if len(t_norm) >= 4 and len(c_clean) >= 4:
        if t_norm in c_clean or c_clean in t_norm:
            if SequenceMatcher(None, t_norm, c_clean).ratio() >= 0.72:
                return True

    # 4. 模糊編輯距離比對：容許 1~2 個字元差異
    if min(len(t_norm), len(c_clean)) >= 4 and abs(len(t_norm) - len(c_clean)) <= 3:
        if SequenceMatcher(None, t_norm, c_clean).ratio() >= 0.82:
            return True

    # 5. 單詞級別模糊比對 (當單詞數相同且 >= 2 時，容許單詞微幅拼寫或單複數差異)
    if len(t_tokens) == len(c_filtered) and len(t_tokens) >= 2:
        if all(tw == cw or SequenceMatcher(None, tw, cw).ratio() >= 0.80 for tw, cw in zip(t_tokens, c_filtered)):
            return True

    return False

def is_matching(game_name, candidate_slug):
    """
    智慧模糊比對搜尋結果是否確實為該遊戲：
    1. 嚴格剔除特殊字元 (如 ™、®、🍕 等)，僅比對英文、中文與數字
    2. 自動忽略外網常見後綴詞 (如 'по сети'、'-po-seti'、'-online'、'-coop')
    3. 同時支援「英中數全集」與「純英數」雙模式比對，並容許 1~2 個字元差異
    """
    raw_str = str(game_name or "")
    # 模式 A：保留英文、中文與數字
    if _match_token_lists(_extract_tokens(game_name, keep_cjk=True), _extract_tokens(candidate_slug, keep_cjk=True), raw_str):
        return True
    # 模式 B：僅保留英文與數字 (解決中英雙語標題對齊純英文網址 slug / 俄文標題的問題)
    if _match_token_lists(_extract_tokens(game_name, keep_cjk=False), _extract_tokens(candidate_slug, keep_cjk=False), raw_str):
        return True
    return False

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
    search_q = clean_search_query(clean_name)
    appid_str = str(appid).strip() if appid else ""

    # 0. 檢查種子資料庫
    if appid_str and appid_str in _SEED_PATCHES and _SEED_PATCHES[appid_str].get("zeigames"):
        return _SEED_PATCHES[appid_str]["zeigames"]
    if norm_name in _SEED_PATCHES and _SEED_PATCHES[norm_name].get("zeigames"):
        return _SEED_PATCHES[norm_name]["zeigames"]
    if search_q.lower() in _SEED_PATCHES and _SEED_PATCHES[search_q.lower()].get("zeigames"):
        return _SEED_PATCHES[search_q.lower()]["zeigames"]

    queries = get_search_queries(clean_name)
    if not queries:
        return None

    # 1. 嘗試官方站內搜尋 (使用剔除特殊字元後的關鍵字)
    for q in queries:
        encoded = urllib.parse.quote_plus(q)
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
    for q in queries[:1]:
        for ddg_q in (f'site:zeigames.com/files/file/ "{q}"', f'site:zeigames.com/files/file/ {q}'):
            candidates = _search_ddg_for_site(ddg_q, 'zeigames.com/files/file/')
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
    search_q = clean_search_query(clean_name)
    appid_str = str(appid).strip() if appid else ""

    # 0. 檢查種子資料庫
    if appid_str and appid_str in _SEED_PATCHES and _SEED_PATCHES[appid_str].get("onlinefix"):
        return _SEED_PATCHES[appid_str]["onlinefix"]
    if norm_name in _SEED_PATCHES and _SEED_PATCHES[norm_name].get("onlinefix"):
        return _SEED_PATCHES[norm_name]["onlinefix"]
    if search_q.lower() in _SEED_PATCHES and _SEED_PATCHES[search_q.lower()].get("onlinefix"):
        return _SEED_PATCHES[search_q.lower()]["onlinefix"]

    queries = get_search_queries(clean_name)
    if not queries:
        return None

    # 1. 嘗試官方站內搜尋 (使用剔除特殊字元後的乾淨英數關鍵字，同時比對網址 slug 與專欄標題)
    url = "https://online-fix.me/index.php?do=search"
    for q in queries:
        data = urllib.parse.urlencode({
            'do': 'search',
            'subaction': 'search',
            'story': q,
            'search_start': 0,
            'full_search': 0,
            'result_from': 1
        }).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=3.5) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
                # 比對所有遊戲專欄連結與標題 (支援多層分類路徑與標題如 'Solarpunk по сети')
                link_blocks = re.findall(
                    r'<a[^>]+href=["\'](https://online-fix\.me/games/(?:[^"\'/]+/)+(\d+)-([^"\'/\.]+)\.html)["\'][^>]*>(.*?)</a>',
                    html,
                    flags=re.IGNORECASE | re.DOTALL
                )
                for full_url, post_id, slug, inner_html in link_blocks:
                    title_text = re.sub(r'<[^>]+>', ' ', inner_html).strip()
                    if is_matching(clean_name, slug) or (title_text and is_matching(clean_name, title_text)):
                        return full_url
                matches = re.findall(r'href=["\'](https://online-fix\.me/games/(?:[^"\'/]+/)+(\d+)-([^"\'/\.]+)\.html)["\']', html)
                for full_url, post_id, slug in matches:
                    if is_matching(clean_name, slug):
                        return full_url
        except Exception:
            pass

    # 2. DuckDuckGo 備援 (同時支援精準與模糊關鍵字檢索)
    for q in queries[:1]:
        for ddg_q in (f'site:online-fix.me "{q}"', f'site:online-fix.me/games/ {q}'):
            candidates = _search_ddg_for_site(ddg_q, 'online-fix.me/games/')
            for cand_url in candidates:
                m = re.search(r'online-fix\.me/games/(?:[^"\'/]+/)+(\d+)-([^/\.]*)\.html', cand_url)
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
    - 未收錄 (available == False)：TTL 為 24 小時 (86400s)，且必須符合最新快取結構版本 (_v >= 2)
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
    # 若舊版快取判定為未收錄 (False)，但當時未經過 Emoji 剝離與英文名強制解析 (_v < 2)，視為需重驗
    if not has_any and entry.get("_v", 1) < _CACHE_SCHEMA_VER:
        return False

    ttl = 604800 if has_any else 86400
    return (now - updated_at) < ttl


def check_all_web_patches(game_name: str, appid: str = None, force_refresh: bool = False, on_step = None) -> dict:
    """
    並行查詢 Online-Fix 與 ZeiGames 是否收錄該遊戲補丁。
    具備智慧架構：
    1. 非對稱 TTL 快取 (已收錄 7 天 / 未收錄 24 小時)
    2. 目標存活校驗探針 (防止文章被站長刪除或 404 死鏈)
    3. 自動解析真實英文名稱與 Emoji/特殊符號模糊正規化
    4. 支援動態進度回調 (on_step)
    """
    _load_cache()
    raw_input_name = str(game_name or "").strip()
    appid_str = str(appid or "").strip()

    # 自動解析真實英文遊戲名稱（防止傳入中文譯名導致外網搜尋失敗並污染快取）
    clean_name = resolve_english_game_name(raw_input_name, appid_str)
    cache_key = f"{appid_str}:{clean_name}" if appid_str else clean_name
    raw_cache_key = f"{appid_str}:{raw_input_name}" if appid_str else raw_input_name

    if not clean_name or clean_name.startswith("App_") or not clean_search_query(clean_name):
        return {
            "onlinefix": {"name": "Online-Fix", "available": False, "url": ""},
            "zeigames": {"name": "ZeiGames", "available": False, "url": ""}
        }

    # 1. 命中快取且未過期時直接使用 (0 延遲)
    if not force_refresh:
        cached = (
            _patch_memory_cache.get(cache_key)
            or (appid_str and _patch_memory_cache.get(appid_str))
            or _patch_memory_cache.get(clean_name)
            or _patch_memory_cache.get(raw_cache_key)
        )
        if cached and is_patch_cache_valid(cached):
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
            of_url = fut_of.result(timeout=5.5)
        except Exception:
            of_url = None
        if on_step:
            on_step("zeigames")
        try:
            zg_url = fut_zg.result(timeout=5.5)
        except Exception:
            zg_url = None

    # 二次死鏈防護：確保爬取到的網址確實存活
    if of_url and not is_url_alive(of_url, timeout=2.5):
        of_url = None
    if zg_url and not is_url_alive(zg_url, timeout=2.5):
        zg_url = None

    now_ts = int(time.time())
    result = {
        "_v": _CACHE_SCHEMA_VER,
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
    if raw_input_name and raw_input_name != clean_name:
        _patch_memory_cache[raw_cache_key] = result
        _patch_memory_cache[raw_input_name] = result
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
