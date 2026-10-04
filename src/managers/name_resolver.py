import os
import json
import re
import urllib.request
from pathlib import Path

_NAMES_CACHE_FILE = Path(__file__).parent.parent.parent / "data" / "game_names.json"
_memory_cache = {}

def _load_cache():
    global _memory_cache
    if _memory_cache:
        return
    if _NAMES_CACHE_FILE.exists():
        try:
            _memory_cache = json.loads(_NAMES_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            _memory_cache = {}

def _save_cache():
    try:
        _NAMES_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _NAMES_CACHE_FILE.write_text(json.dumps(_memory_cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[name_resolver] Save cache failed: {e}")

def resolve_game_name(appid, lua_path=None, steam_path=None, allow_network=True) -> str:
    """
    精準解析遊戲名稱：
    1. 快取 (data/game_names.json)
    2. 本地 Lua 註解 (-- {appid} - {name})
    3. 本地 appmanifest_{appid}.acf
    4. Steam 官方 Store API (繁中/簡中/英文)
    5. SteamCMD PICS API
    """
    app_id_str = str(appid).strip()
    if not app_id_str.isdigit():
        return "未知遊戲"

    _load_cache()
    if app_id_str in _memory_cache and _memory_cache[app_id_str] and _memory_cache[app_id_str] != "未知遊戲":
        return _memory_cache[app_id_str]

    # 1. Check local Lua file
    if lua_path:
        lp = Path(lua_path)
        if lp.exists():
            try:
                content = lp.read_text(encoding="utf-8", errors="ignore")
                m = re.search(r'--\s*\d+\s*-\s*(.+)', content)
                if m and m.group(1).strip() and m.group(1).strip() != "未知遊戲":
                    name = m.group(1).strip()
                    _memory_cache[app_id_str] = name
                    _save_cache()
                    return name
            except Exception:
                pass

    # 2. Check local ACF
    if steam_path:
        from managers import steam_manager
        acf = steam_manager.find_appmanifest(app_id_str, steam_path)
        if acf and acf.exists():
            try:
                content = acf.read_text(encoding="utf-8", errors="ignore")
                m = re.search(r'"name"\s+"([^"]+)"', content)
                if m and m.group(1).strip() and m.group(1).strip() != "未知遊戲":
                    name = m.group(1).strip()
                    _memory_cache[app_id_str] = name
                    _save_cache()
                    return name
            except Exception:
                pass

    if not allow_network:
        return "未知遊戲"

    # 3. Steam Store API
    for lang in ["tchinese", "schinese", "english"]:
        url = f"https://store.steampowered.com/api/appdetails?appids={app_id_str}&l={lang}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                app_data = data.get(app_id_str, {})
                if app_data.get('success'):
                    name = app_data.get('data', {}).get('name', '').strip()
                    if name:
                        _memory_cache[app_id_str] = name
                        _save_cache()
                        _update_lua_header(lua_path, app_id_str, name)
                        return name
        except Exception:
            pass

    # 4. SteamCMD PICS API
    try:
        from api.update_manifests import get_app_info
        info = get_app_info(app_id_str)
        if info and "common" in info and "name" in info["common"]:
            name = info["common"]["name"].strip()
            if name:
                _memory_cache[app_id_str] = name
                _save_cache()
                _update_lua_header(lua_path, app_id_str, name)
                return name
    except Exception:
        pass

    return "未知遊戲"

def _update_lua_header(lua_path, appid, name):
    if not lua_path:
        return
    lp = Path(lua_path)
    if not lp.exists():
        return
    try:
        content = lp.read_text(encoding="utf-8", errors="ignore")
        if not re.search(r'--\s*\d+\s*-\s*.+', content):
            # Header does not have game name comment, prepend it
            header = f"-- {appid} - {name}\n"
            os.chmod(lp, 0o666)
            lp.write_text(header + content, encoding="utf-8")
    except Exception:
        pass
