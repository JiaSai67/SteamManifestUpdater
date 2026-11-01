import os
import subprocess
import shutil
from pathlib import Path
import json
import sys
import time
import logging

logger = logging.getLogger(__name__)

from managers import config_manager
_config = config_manager.get_config()

import winreg
import string
import re

def get_all_available_extractors() -> list:
    """
    全方位探測並回傳系統所有可用的解壓縮工具清單 (按格式通用度與優先順序排序且去重)。
    優先順序：7-Zip (全格式命令列最佳) ➔ WinRAR.exe (全格式 GUI/背景) ➔ UnRAR.exe (專解 RAR)。
    支援專案內建、系統 PATH、Windows 官方 App Paths、註冊表關聯與各磁碟 (C~Z) 安裝路徑。
    """
    raw_found = []
    seen_paths = set()

    def _add(ext_type: str, exe_path: str):
        if not exe_path:
            return
        p_clean = os.path.normpath(str(exe_path).strip().strip('"'))
        if p_clean.lower() in seen_paths:
            return
        if os.path.isfile(p_clean):
            seen_paths.add(p_clean.lower())
            is_unrar = os.path.basename(p_clean).lower().startswith("unrar")
            raw_found.append({
                "type": ext_type,
                "path": p_clean,
                "is_unrar_only": is_unrar
            })

    # 0. 優先嘗試專案內建的解壓縮工具 (讓用戶能將工具直接打包進專案或 opensteamtools)
    local_tools = [
        ("7z", config_manager._root_dir / "7z.exe"),
        ("7z", config_manager._root_dir / "opensteamtools" / "7z.exe"),
        ("winrar", config_manager._root_dir / "WinRAR.exe"),
        ("winrar", config_manager._root_dir / "UnRAR.exe"),
        ("winrar", config_manager._root_dir / "opensteamtools" / "UnRAR.exe"),
        ("winrar", config_manager._root_dir / "assets" / "UnRAR.exe"),
    ]
    for ext_type, p in local_tools:
        if p.exists():
            _add(ext_type, str(p))

    # 1. 嘗試系統 PATH 環境變數 (優先 7z，其次 winrar，最後 unrar)
    for name, ext_type in [("7z", "7z"), ("winrar", "winrar"), ("unrar", "winrar")]:
        which_path = shutil.which(name)
        if which_path:
            _add(ext_type, which_path)

    # 2. 嘗試 7-Zip 註冊表專用鍵 (Path, Path64)
    for h in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
        for sub in [r"SOFTWARE\7-Zip", r"SOFTWARE\WOW6432Node\7-Zip"]:
            try:
                with winreg.OpenKey(h, sub) as key:
                    for vn in ["Path", "Path64"]:
                        try:
                            p, _ = winreg.QueryValueEx(key, vn)
                            if p:
                                _add("7z", os.path.join(p, "7z.exe"))
                        except Exception:
                            pass
            except Exception:
                pass

    # 3. 嘗試 Windows 官方應用程式路徑 (App Paths: 支援自訂安裝磁碟、免安裝關聯)
    app_keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\7z.exe", "7z"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths\7z.exe", "7z"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\WinRAR.exe", "winrar"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths\WinRAR.exe", "winrar"),
    ]
    for h, sub, ext_type in app_keys:
        try:
            with winreg.OpenKey(h, sub) as k:
                val, _ = winreg.QueryValueEx(k, "")
                if val:
                    _add(ext_type, val)
                    if ext_type == "winrar":
                        unrar_c = os.path.join(os.path.dirname(val), "UnRAR.exe")
                        _add("winrar", unrar_c)
        except Exception:
            pass

    # 4. 嘗試註冊表檔案關聯 (WinRAR Shell Open Command)
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"WinRAR\shell\open\command") as key:
            val, _ = winreg.QueryValueEx(key, "")
            m = re.match(r'^"([^"]+)"', val)
            target = m.group(1) if m else val.split()[0]
            if target:
                _add("winrar", target)
                unrar_c = os.path.join(os.path.dirname(target), "UnRAR.exe")
                _add("winrar", unrar_c)
    except Exception:
        pass

    # 5. 全磁碟掃描常見安裝目錄 (支援 C:, D:, E:, F:, G:... 任何磁碟槽)
    available_drives = [f"{d}:" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
    for d in available_drives:
        candidates = [
            ("7z", os.path.join(d + "\\", "Program Files", "7-Zip", "7z.exe")),
            ("7z", os.path.join(d + "\\", "Program Files (x86)", "7-Zip", "7z.exe")),
            ("winrar", os.path.join(d + "\\", "Program Files", "WinRAR", "WinRAR.exe")),
            ("winrar", os.path.join(d + "\\", "Program Files (x86)", "WinRAR", "WinRAR.exe")),
            ("winrar", os.path.join(d + "\\", "Program Files", "WinRAR", "UnRAR.exe")),
            ("winrar", os.path.join(d + "\\", "Program Files (x86)", "WinRAR", "UnRAR.exe")),
        ]
        for ext_type, c_path in candidates:
            _add(ext_type, c_path)

    # 智能加權排序：將 7z.exe 與完整版 WinRAR.exe 排在最前（全格式相容），UnRAR.exe 緊隨其後
    def _sort_weight(item):
        t = item["type"]
        is_u = item.get("is_unrar_only", False)
        if t == "7z":
            return 1
        elif t == "winrar" and not is_u:
            return 2
        else:
            return 3

    raw_found.sort(key=_sort_weight)
    return raw_found


def get_extractor():
    """取得優先級最高之可用解壓縮工具"""
    tools = get_all_available_extractors()
    return tools[0] if tools else None

EXTRACTOR = get_extractor()
ARCHIVE_PASSWORDS = ["online-fix.me", "zeigames.com", ""]

# 🌟 已知官方/熱門 Google Drive 補丁檔名至 AppID 精準映射字典 (杜絕純英文檔名無數字無法解析問題)
KNOWN_CLOUD_PATCH_APPIDS = {
    "dimraeth": "2402680",
    "corekeeper": "1621690",
    "core keeper": "1621690",
    "escapethebackrooms": "1943950",
    "escape the backrooms": "1943950",
    "fastfoodsimulator": "2916430",
    "fast food simulator": "2916430",
    "grainrot": "4450620",
    "grain rot": "4450620",
    "minecraftdungeons": "1672970",
    "minecraftdungeonsii": "1672970",
    "pizzahousesimulator": "4132330",
    "pizza house simulator": "4132330",
    "scamline": "3859360",
    "subnautica": "264710",
    "ultimatechickenhorse": "386940",
    "ultimate chicken horse": "386940",
    "deepbluesushi": "4005220",
    "deep blue sushi": "4005220",
    "wraphousesimulator": "3536240",
    "wrap house simulator": "3536240",
}

def _normalize_patch_game_name(text: str, keep_cjk: bool = False) -> str:
    """
    將遊戲名稱或檔名嚴格剔除所有特殊字元、Emoji (🍕) 與商標符號 (™/®/©)，
    僅保留英文、中文與數字以供模糊比對（使用 NFD 避免將 ™ 拆解成英文字母 tm）。
    """
    import re, unicodedata
    if not text:
        return ""
    s = unicodedata.normalize('NFD', str(text)).lower()
    s = re.sub(r'[\u0300-\u036f]+', '', s)
    if keep_cjk and not re.search(r'[a-z]', s):
        return re.sub(r'[^a-z0-9\u4e00-\u9fff]', '', s)
    return re.sub(r'[^a-z0-9]', '', s)

def resolve_appid_for_patch_file(file_name: str, folder_part: str = "") -> str:
    """
    從補丁檔名或目錄路徑智慧反解 Steam AppID：
    1. 優先尋找 4~9 位純數字 AppID
    2. 智能剝離修復標籤後綴 (_Fix_Repair_Steam_Generic, OnlineFix, ZeiGames 等) 與 Emoji
    3. 交叉比對 data/game_names.json、data/game_cache.json 與已知網盤補丁庫字典 (含模糊比對)
    """
    import re
    from difflib import SequenceMatcher
    if not file_name:
        return ""
    
    # 1. 檢查路徑與檔名中的純數字 (排除常見誤判如年份 2020-2029 或通用版本)
    for candidate in [folder_part, file_name]:
        if candidate:
            m = re.findall(r'(?:^|[^0-9])(\d{4,9})(?:[^0-9]|$)', candidate)
            for aid in m:
                if str(aid) not in ("2023", "2024", "2025", "2026", "2027"):
                    return str(aid)

    # 2. 清理檔名修復標籤與後綴
    clean_name = file_name
    for ext in ['.rar', '.zip', '.7z', '.lua', '.tar', '.gz']:
        if clean_name.lower().endswith(ext):
            clean_name = clean_name[:-len(ext)]
            break

    tags_to_strip = [
        '_Fix_Repair_Steam_V2_Generic', '_Fix_Repair_Steam_Generic', '_Fix_Repair_GDK',
        '_Fix_Repair_Steam', '_Fix_Repair', 'Fix_Repair_Steam_Generic',
        '.OnlineFix.ZeiGames.com', 'OnlineFix.ZeiGames.com', 'Online Fix.ZeiGames.com',
        '.OnlineFix', 'OnlineFix', 'Online-Fix', 'Online Fix', 'ZeiGames.com', 'ZeiGames',
        'Generic', '_Steam', 'Steam'
    ]
    for tag in tags_to_strip:
        clean_name = re.sub(re.escape(tag), '', clean_name, flags=re.IGNORECASE)

    clean_name = clean_name.replace('_', ' ').replace('.', ' ').strip()
    norm_clean = _normalize_patch_game_name(clean_name)
    if not norm_clean:
        return ""

    # 3. 優先精準比對已知網盤補丁庫高頻字典
    if norm_clean in KNOWN_CLOUD_PATCH_APPIDS:
        return KNOWN_CLOUD_PATCH_APPIDS[norm_clean]

    # 4. 比對 data/game_names.json 與 data/game_cache.json (精準與模糊比對)
    local_candidates = []
    try:
        gn_file = config_manager._root_dir / "data" / "game_names.json"
        if gn_file.exists():
            gn_data = json.loads(gn_file.read_text(encoding="utf-8"))
            for aid, gname in gn_data.items():
                g_norm = _normalize_patch_game_name(gname)
                if g_norm and len(g_norm) >= 3:
                    if g_norm == norm_clean:
                        return str(aid)
                    local_candidates.append((str(aid), g_norm))
    except Exception:
        pass

    try:
        gc_file = config_manager._root_dir / "data" / "game_cache.json"
        if gc_file.exists():
            gc_data = json.loads(gc_file.read_text(encoding="utf-8"))
            for aid, ginfo in gc_data.items():
                if isinstance(ginfo, dict):
                    for nk in ['english_name', 'name_en', 'name']:
                        g_val = ginfo.get(nk)
                        if g_val:
                            g_norm = _normalize_patch_game_name(g_val)
                            if g_norm and len(g_norm) >= 3:
                                if g_norm == norm_clean:
                                    return str(aid)
                                local_candidates.append((str(aid), g_norm))
    except Exception:
        pass

    for k, v in KNOWN_CLOUD_PATCH_APPIDS.items():
        k_norm = _normalize_patch_game_name(k)
        if k_norm and (k_norm in norm_clean or norm_clean in k_norm):
            return v

    # 子字串或模糊比對 (容許 1~2 個字元或符號差異)
    for aid, g_norm in local_candidates:
        if g_norm in norm_clean or norm_clean in g_norm:
            if min(len(g_norm), len(norm_clean)) / max(len(g_norm), len(norm_clean)) >= 0.72:
                return aid
        if min(len(g_norm), len(norm_clean)) >= 4 and abs(len(g_norm) - len(norm_clean)) <= 2:
            if SequenceMatcher(None, g_norm, norm_clean).ratio() >= 0.84:
                return aid

    return ""

_cache_dir = Path(_config.get("cache_dir", str(config_manager._root_dir / "data" / "cache")))
def get_app_cache_dir(app_id, app_name=None, create=False):
    app_id = str(app_id)
    if LOCAL_PATCH_DIR.exists():
        for d in LOCAL_PATCH_DIR.iterdir():
            if d.is_dir() and d.name.endswith(f" {app_id}"):
                return d
    if app_name:
        import re
        safe_name = re.sub(r'[\\\\/*?:"<>|]', "", app_name).strip()
        new_dir = LOCAL_PATCH_DIR / f"{safe_name} {app_id}"
        if create:
            new_dir.mkdir(parents=True, exist_ok=True)
        return new_dir
    fallback = LOCAL_PATCH_DIR / f"UnknownApp {app_id}"
    if create:
        fallback.mkdir(parents=True, exist_ok=True)
    return fallback

def _clean_empty_cache_dirs():
    """自動清理 LOCAL_PATCH_DIR 中未存放任何實體補丁的空資料夾"""
    if LOCAL_PATCH_DIR.exists():
        import shutil
        for d in list(LOCAL_PATCH_DIR.iterdir()):
            if d.is_dir():
                files = list(d.iterdir())
                has_patch_file = any(f.suffix.lower() in ('.rar', '.zip', '.7z', '.lua') for f in files)
                if not files or (len(files) == 1 and files[0].name == 'patch_record.json' and not has_patch_file):
                    try:
                        shutil.rmtree(d, ignore_errors=True)
                    except Exception:
                        pass

def _find_steam_game_dir(app_id):
    import winreg, re
    libs = set()
    try:
        from managers import steam_manager
        sp = steam_manager.find_steam_path()
        if sp:
            libs.add(os.path.normpath(sp))
    except Exception:
        pass
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam')
        path, _ = winreg.QueryValueEx(key, 'SteamPath')
        winreg.CloseKey(key)
        libs.add(os.path.normpath(path))
    except Exception:
        pass
        
    for lib in list(libs):
        vdf_path = os.path.join(lib, 'steamapps', 'libraryfolders.vdf')
        if os.path.exists(vdf_path):
            try:
                content = open(vdf_path, encoding='utf-8', errors='ignore').read()
                matches = re.findall(r'"path"\s*"([^"]+)"', content, re.IGNORECASE)
                for m in matches:
                    m = m.replace('\\\\', '\\')
                    libs.add(os.path.normpath(m))
            except Exception:
                pass
                
    for lib in libs:
        acf = os.path.join(lib, 'steamapps', f'appmanifest_{app_id}.acf')
        if os.path.exists(acf):
            try:
                content = open(acf, encoding='utf-8', errors='ignore').read()
                m = re.search(r'"installdir"\s*"([^"]+)"', content, re.IGNORECASE)
                if m:
                    return Path(lib) / 'steamapps' / 'common' / m.group(1)
            except Exception:
                pass
    return None

def _get_game_record_path(app_id):
    game_dir = _find_steam_game_dir(app_id)
    if game_dir and game_dir.exists():
        return game_dir / ".onlinefix_record.json"
    return None

ONLINEFIX_SIGNATURE_FILES = [
    # Online-Fix.me specific
    "onlinefix.ini", "onlinefix64.dll", "onlinefix.dll", "steamoverlay.dll", "steamoverlay64.dll", "onlinefix.url",
    # ZeiGames.com specific
    "zeigames.url", "zeigames.ini", "zeigames.txt", "zeigames.dll", "zeigames64.dll",
    # Generic steam emulators / proxy DLLs commonly used by ZeiGames & Online-Fix
    "steam_emu.ini", "steam_interfaces.txt",
    "winmm.dll", "version.dll", "dwmapi.dll", "dinput8.dll", "xinput1_3.dll", "xinput1_4.dll"
]

def is_known_crack_file(file_path_or_name):
    name = Path(file_path_or_name).name.lower()
    if name in ONLINEFIX_SIGNATURE_FILES:
        return True
    if name.startswith(("onlinefix", "zeigames", "steamoverlay", "steam_emu")):
        return True
    if name.endswith(".url") and any(k in name for k in ("online-fix", "onlinefix", "zeigames", "zei")):
        return True
    return False

def _load_record(app_id):
    app_id = str(app_id)
    
    # 1. Primary: Load in-situ record directly from the game directory
    game_record_path = _get_game_record_path(app_id)
    if game_record_path and game_record_path.exists():
        try:
            with open(game_record_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    if "game_dir" not in data or not data["game_dir"]:
                        data["game_dir"] = str(game_record_path.parent)
                    return data
        except Exception:
            pass
            
    # 2. Secondary: Fallback to local cache directory record
    d = get_app_cache_dir(app_id)
    json_path = d / "patch_record.json"
    if json_path.exists():
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    if "game_dir" not in data or not data["game_dir"]:
                        game_dir = _find_steam_game_dir(app_id)
                        if game_dir:
                            data["game_dir"] = str(game_dir)
                    return data
        except Exception:
            pass
            
    # 3. Third: Heuristic signature scan (handles external/manual installs from Online-Fix, ZeiGames, etc.)
    game_dir = _find_steam_game_dir(app_id)
    if game_dir and game_dir.exists():
        found_signatures = []
        try:
            for item in game_dir.iterdir():
                if item.is_file() and is_known_crack_file(item.name):
                    found_signatures.append(item.name)
        except Exception:
            pass
        bak_files = [f.name for f in game_dir.glob("*.bak")]
        
        if found_signatures or bak_files:
            record = {
                "appid": app_id,
                "installed_files": found_signatures,
                "backed_up_files": bak_files,
                "manual_install": True,
                "timestamp": int(time.time())
            }
            # 立即在遊戲目錄底下寫入自行安裝標記，持久化記錄避免後續套娃
            _save_record(app_id, record)
            record["game_dir"] = str(game_dir)
            return record
            
    return None

def _save_record(app_id, record, app_name=None):
    app_id = str(app_id)
    game_dir_str = record.get("game_dir")
    
    # 精簡記錄檔結構：僅保留關鍵資訊與相對路徑，去除冗餘絕對路徑
    compact_record = {
        "appid": app_id,
        "installed_files": record.get("installed_files", []),
        "backed_up_files": record.get("backed_up_files", []),
        "manual_install": bool(record.get("manual_install", False)),
        "source_drive": record.get("source_drive", "Google Drive"),
        "timestamp": int(record.get("timestamp", 0))
    }
    
    # 1. Primary: Save directly inside the game directory (compact single-line JSON, <1KB)
    if game_dir_str and os.path.exists(game_dir_str):
        game_record_path = Path(game_dir_str) / ".onlinefix_record.json"
        try:
            with open(game_record_path, 'w', encoding='utf-8') as f:
                json.dump(compact_record, f, ensure_ascii=False, separators=(',', ':'))
        except Exception:
            pass
            
    # 2. Secondary: Dual backup in cache directory
    d = get_app_cache_dir(app_id, app_name)
    json_path = d / "patch_record.json"
    try:
        cache_record = dict(compact_record)
        if game_dir_str:
            cache_record["game_dir"] = str(game_dir_str)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(cache_record, f, ensure_ascii=False, separators=(',', ':'))
    except Exception:
        pass

def _delete_record(app_id, game_dir=None):
    app_id = str(app_id)
    # 1. Delete from specified or discovered game directory
    if game_dir:
        p = Path(game_dir) / ".onlinefix_record.json"
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass
                
    game_record_path = _get_game_record_path(app_id)
    if game_record_path and game_record_path.exists():
        try:
            game_record_path.unlink()
        except Exception:
            pass
            
    # 2. Delete from cache directory
    d = get_app_cache_dir(app_id)
    json_path = d / "patch_record.json"
    if json_path.exists():
        try:
            json_path.unlink()
        except Exception:
            pass

LOCAL_PATCH_DIR = _cache_dir / "OnlineFix Lua files"
LOCAL_PATCH_DIR.mkdir(parents=True, exist_ok=True)

_cloud_cache_file = _cache_dir / "cloud_cache.json"
_gdrive_index_json = _cache_dir / "gdrive_index.json"
_gdrive_index_txt = _cache_dir / "gdrive_index.txt"
_cloud_cache = None
_last_fetch_time = 0

if _cloud_cache_file.exists():
    try:
        with open(_cloud_cache_file, "r", encoding="utf-8") as f:
            _cloud_cache = json.load(f)
            # 🌟 快取自我修復：若歷史快取中未填入 AppID 或映射已更新，立即智慧補齊並持久化
            if isinstance(_cloud_cache, list):
                _patched_any = False
                for item in _cloud_cache:
                    fname = item.get("name") or Path(item.get("path") or "").name
                    aid = resolve_appid_for_patch_file(fname, item.get("path") or "")
                    if aid and str(item.get("app_id") or "") != str(aid):
                        item["app_id"] = str(aid)
                        _patched_any = True
                if _patched_any:
                    try:
                        with open(_cloud_cache_file, "w", encoding="utf-8") as wf:
                            json.dump(_cloud_cache, wf, ensure_ascii=False, indent=2)
                        appids_json = config_manager._root_dir / "data" / "onlinefix_appids.json"
                        if appids_json.exists():
                            appids_json.unlink()
                    except Exception:
                        pass
    except Exception:
        _cloud_cache = None

def get_cloud_drives():
    drives = _config.get("cloud_drives", [])
    if not drives:
        legacy_url = _config.get("gdrive_url", "https://drive.google.com/drive/folders/13TSWK9I5JWj3MDSGeEubSZm37-IwUoGu?usp=sharing")
        drives = [{"priority": 1, "name": "網盤 1 (官方補丁庫)", "url": legacy_url}]
    return drives

def update_cloud_drives(drives):
    global _cloud_cache, _last_fetch_time
    _config["cloud_drives"] = drives
    if drives:
        _config["gdrive_url"] = drives[0]["url"]
    config_manager.save_config(_config)
    _cloud_cache = None
    _last_fetch_time = 0
    if _cloud_cache_file.exists():
        try:
            _cloud_cache_file.unlink()
        except:
            pass

def _write_gdrive_txt_summary(index_data):
    """將 Google Drive 檔案記錄輸出成清晰乾淨的 TXT 純文字檔案"""
    txt_lines = []
    txt_lines.append("=" * 80)
    txt_lines.append("Google Drive 雲端補丁庫檔案記錄 (自動同步清單)")
    txt_lines.append(f"最後更新時間：{index_data.get('last_updated', '未知')}")
    txt_lines.append(f"總計網盤數：{index_data.get('total_drives', 0)} 個 | 總計補丁檔案：{index_data.get('total_files', 0)} 個")
    txt_lines.append("=" * 80)
    txt_lines.append("")
    
    for d in index_data.get("drives", []):
        d_name = d.get("drive_name", "未知網盤")
        d_prio = d.get("drive_priority", 1)
        d_url = d.get("drive_url", "")
        f_id = d.get("folder_id", "")
        status = d.get("status", "unknown")
        f_cnt = d.get("file_count", 0)
        
        status_icon = "✅ 成功" if status == "success" else f"❌ 失敗 ({d.get('error', '')})"
        
        txt_lines.append(f"【{d_name}】(優先級: {d_prio})")
        txt_lines.append(f"來源網址：{d_url}")
        if f_id:
            txt_lines.append(f"資料夾ID：{f_id}")
        txt_lines.append(f"同步狀態：{status_icon} (共 {f_cnt} 個檔案)")
        txt_lines.append("-" * 80)
        
        files = d.get("files", [])
        if files:
            for f in files:
                aid = f.get("app_id") or "未知AppID"
                f_path = f.get("path", "")
                fid = f.get("id", "")
                txt_lines.append(f"  • [AppID: {aid}] {f_path} (ID: {fid})")
        else:
            txt_lines.append("  (此網盤目前無任何檔案或尚未讀取到內容)")
        txt_lines.append("")
        txt_lines.append("-" * 80)
        txt_lines.append("")
        
    with open(_gdrive_index_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(txt_lines))

def fetch_cloud_cache(force=False, min_interval=30):
    """
    從所有設定的 Google Drive 網盤中調閱補丁檔案清單。
    - 內建 30 秒記憶體 TTL 快取保護 (min_interval=30)，30 秒內連續互動 100% 走記憶體快取
    - 超過 30 秒後之互動自動觸發聯網刷新最新索引
    - 同步產出 gdrive_index.json 與 gdrive_index.txt 雙格式清晰記錄
    """
    global _cloud_cache, _last_fetch_time
    now = time.time()
    
    # 1. 若非強制刷新且記憶體已有快取且在 30 秒 TTL 內，直接回傳
    if not force and _cloud_cache is not None and len(_cloud_cache) > 0 and _last_fetch_time > 0 and (now - _last_fetch_time) < min_interval:
        return _cloud_cache
        
    # 2. 檢查請求間隔 (防止 30 秒內高頻輪詢觸發 Google Drive 429 限流)
    if _last_fetch_time > 0 and (now - _last_fetch_time) < min_interval:
        if _cloud_cache is not None and len(_cloud_cache) > 0:
            return _cloud_cache
        if _cloud_cache_file.exists():
            try:
                with open(_cloud_cache_file, "r", encoding="utf-8") as f:
                    _cloud_cache = json.load(f)
                    return _cloud_cache
            except Exception:
                pass

    drives = get_cloud_drives()
    all_items = []
    structured_drives = []
    
    try:
        import gdown
        import re
        for idx, drive in enumerate(drives):
            url = drive.get("url", "").strip()
            name = drive.get("name", f"網盤 {idx + 1}").strip()
            priority = drive.get("priority", idx + 1)
            if not url:
                continue
                
            drive_files = []
            status_str = "success"
            error_msg = ""
            
            # 解析 GDrive folder id
            folder_id_match = re.search(r'folders/([a-zA-Z0-9_-]+)', url)
            folder_id = folder_id_match.group(1) if folder_id_match else ""
            
            try:
                res = gdown.download_folder(url=url, skip_download=True, quiet=True)
                for f in res:
                    f_path = str(f.path)
                    f_id = str(f.id) if hasattr(f, 'id') else ""
                    norm_path = f_path.replace('/', '\\')
                    parts = norm_path.split('\\')
                    file_name = parts[-1]
                    
                    # 辨識 AppID (全域智慧多層反解，支援純英文無數字檔名)
                    folder_part = parts[0] if len(parts) >= 2 else ""
                    app_id = resolve_appid_for_patch_file(file_name, folder_part=folder_part)
                            
                    item_data = {
                        'path': f_path,
                        'name': file_name,
                        'id': f_id,
                        'app_id': app_id,
                        'drive_name': name,
                        'drive_priority': priority,
                        'drive_url': url
                    }
                    all_items.append(item_data)
                    drive_files.append({
                        'app_id': app_id,
                        'name': file_name,
                        'path': f_path,
                        'id': f_id
                    })
            except Exception as e:
                status_str = "error"
                error_msg = str(e)
                print(f"Error fetching drive {name} ({url}): {e}")
                
            structured_drives.append({
                "drive_name": name,
                "drive_priority": priority,
                "drive_url": url,
                "folder_id": folder_id,
                "status": status_str,
                "error": error_msg,
                "file_count": len(drive_files),
                "synced_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
                "files": drive_files
            })
            
        _cloud_cache = all_items
        _last_fetch_time = now
        
        # 1. 儲存原始快取供舊邏輯相容
        try:
            with open(_cloud_cache_file, "w", encoding="utf-8") as f:
                json.dump(_cloud_cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
            
        # 2. 儲存結構化 JSON 記錄 (清楚記載來源網盤、網址、狀態與完整檔案列表)
        index_data = {
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
            "timestamp": int(now),
            "total_drives": len(structured_drives),
            "total_files": len(all_items),
            "drives": structured_drives
        }
        try:
            with open(_gdrive_index_json, "w", encoding="utf-8") as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving gdrive_index.json: {e}")
            
        # 3. 儲存清晰好讀的 TXT 格式記錄檔 (便於使用者直接以純文字閱讀/查驗)
        try:
            _write_gdrive_txt_summary(index_data)
        except Exception as e:
            print(f"Error saving gdrive_index.txt: {e}")
            
    except Exception as e:
        print(f"fetch_cloud_cache error: {e}")
        if _cloud_cache is None:
            _cloud_cache = []
            
    return _cloud_cache

def sync_cloud_cache():
    return fetch_cloud_cache(force=True, min_interval=0)

def get_gdrive_index_summary():
    """取得 Google Drive 索引記錄摘要與檔案路徑資訊"""
    res = {
        "json_path": str(_gdrive_index_json),
        "txt_path": str(_gdrive_index_txt),
        "exists": _gdrive_index_json.exists(),
        "last_updated": "尚未同步",
        "total_drives": 0,
        "total_files": 0,
        "drives": []
    }
    if _gdrive_index_json.exists():
        try:
            with open(_gdrive_index_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                res.update({
                    "last_updated": data.get("last_updated", "未知"),
                    "total_drives": data.get("total_drives", 0),
                    "total_files": data.get("total_files", 0),
                    "drives": [
                        {
                            "drive_name": d.get("drive_name"),
                            "drive_priority": d.get("drive_priority"),
                            "drive_url": d.get("drive_url"),
                            "file_count": d.get("file_count", 0),
                            "status": d.get("status")
                        }
                        for d in data.get("drives", [])
                    ]
                })
        except Exception:
            pass
    return res

def _is_primary_archive_part(file_name: str) -> bool:
    """判斷是否為主壓縮檔或第一分卷 (例如 .part1.rar / .part01.rar，而非 .part2.rar)"""
    import re
    m = re.search(r'\.part0*(\d+)\.(?:rar|zip|7z)$', file_name.lower())
    if m:
        return int(m.group(1)) == 1
    return True

def get_patch_sources(target_apps=None, target_app_id=None, target_app_name=None, allow_network=False, force_refresh=False):
    global _cloud_cache
    if isinstance(target_apps, (str, int)):
        # 支援位置參數呼叫 get_patch_sources(app_id, app_name)
        pos_id = str(target_apps)
        pos_name = target_app_id if isinstance(target_app_id, str) else (target_app_name or "")
        target_apps = {pos_id: pos_name}
        target_app_id = None
    elif target_apps is None:
        target_apps = {}
    else:
        target_apps = dict(target_apps)
    if target_app_id:
        target_apps[str(target_app_id)] = target_app_name or ""
        
    sources = {}
    
    # 1. Primary: Scan Cloud (Cloud is the authoritative source for all users)
    if (not _cloud_cache and allow_network) or force_refresh:
        fetch_cloud_cache(force=True, min_interval=0 if force_refresh else 15)
            
    if _cloud_cache:
        # Sort by drive_priority ascending (so higher priority drives are indexed first)
        sorted_cache = sorted(_cloud_cache, key=lambda x: x.get('drive_priority', 999))
        for f in sorted_cache:
            norm_path = f['path'].replace('/', '\\')
            parts = norm_path.split('\\')
            drive_prio = f.get('drive_priority', 999)
            drive_name = f.get('drive_name', '網盤 1')
            file_name = parts[-1]
            
            # Extract app_id from cached item or path/filename
            app_id = f.get('app_id')
            if not app_id:
                folder_part = parts[0] if len(parts) >= 2 else ""
                app_id = resolve_appid_for_patch_file(file_name, folder_part=folder_part)
                    
            if app_id:
                app_id = str(app_id)
                if app_id not in sources:
                    sources[app_id] = {
                        'drive_priority': drive_prio,
                        'drive_name': drive_name,
                        'cloud_rars': []
                    }
                
                # If this file comes from a higher priority drive (lower prio number)
                if drive_prio <= sources[app_id].get('drive_priority', 999):
                    if drive_prio < sources[app_id].get('drive_priority', 999):
                        sources[app_id]['drive_priority'] = drive_prio
                        sources[app_id]['drive_name'] = drive_name
                        sources[app_id].pop('cloud_rar', None)
                        sources[app_id]['cloud_rars'] = []
                        sources[app_id].pop('cloud_lua', None)
                        sources[app_id].pop('cloud_lua_obj', None)
                        
                    if file_name.lower().endswith('.lua'):
                        sources[app_id]['cloud_lua'] = True
                        sources[app_id]['cloud_lua_obj'] = f
                    elif file_name.lower().endswith(('.rar', '.zip', '.7z')):
                        if 'cloud_rars' not in sources[app_id]:
                            sources[app_id]['cloud_rars'] = []
                        sources[app_id]['cloud_rars'].append(f)
                        # 🌟 多分卷保護：優先鎖定 part1 或單檔作為主入口，絕不讓 part2 覆蓋 part1！
                        if 'cloud_rar' not in sources[app_id] or _is_primary_archive_part(file_name):
                            sources[app_id]['cloud_rar'] = f
                
        # Fuzzy match logic for target_apps (結合中英文名稱快取，防止傳入中文名無法匹配英文補丁檔名)
        if target_apps:
            from difflib import SequenceMatcher
            gc_data = {}
            try:
                gc_file = config_manager._root_dir / "data" / "game_cache.json"
                if gc_file.exists():
                    gc_data = json.loads(gc_file.read_text(encoding="utf-8"))
            except Exception:
                pass

            for app_id, app_name in target_apps.items():
                app_id = str(app_id)
                if app_id not in sources:
                    sources[app_id] = {}
                    
                if 'cloud_rar' not in sources[app_id]:
                    candidate_names = []
                    if app_name:
                        candidate_names.append(app_name)
                    ginfo = gc_data.get(app_id)
                    if isinstance(ginfo, dict):
                        for nk in ('english_name', 'name_en', 'name'):
                            gv = ginfo.get(nk)
                            if gv and gv not in candidate_names:
                                candidate_names.append(gv)

                    norm_candidates = [_normalize_patch_game_name(cn) for cn in candidate_names if _normalize_patch_game_name(cn)]
                    for f in sorted_cache:
                        if f['path'].lower().endswith(('.rar', '.zip', '.7z')):
                            f_aid = f.get('app_id')
                            is_match = bool(f_aid and str(f_aid) == app_id)
                            if not is_match and norm_candidates:
                                f_norm = _normalize_patch_game_name(f['path'])
                                for t_norm in norm_candidates:
                                    if t_norm in f_norm:
                                        is_match = True
                                        break
                                    if len(t_norm) >= 4 and SequenceMatcher(None, t_norm, f_norm).ratio() >= 0.78:
                                        is_match = True
                                        break
                            if is_match:
                                prio = f.get('drive_priority', 999)
                                if 'drive_priority' not in sources[app_id] or prio <= sources[app_id]['drive_priority']:
                                    if 'drive_priority' not in sources[app_id] or prio < sources[app_id]['drive_priority']:
                                        sources[app_id]['drive_priority'] = prio
                                        sources[app_id]['drive_name'] = f.get('drive_name', '網盤 1')
                                        sources[app_id]['cloud_rars'] = []
                                        sources[app_id].pop('cloud_rar', None)
                                    sources[app_id].setdefault('cloud_rars', []).append(f)
                                    fname_only = f['path'].replace('/', '\\').split('\\')[-1]
                                    if 'cloud_rar' not in sources[app_id] or _is_primary_archive_part(fname_only):
                                        sources[app_id]['cloud_rar'] = f
                            
    # 2. Check local customized/offline lua files if any
    LOCAL_PATCH_DIR = _cache_dir / "OnlineFix Lua files"
    if LOCAL_PATCH_DIR.exists():
        for root, dirs, files in os.walk(LOCAL_PATCH_DIR):
            lua_files = [f for f in files if f.endswith('.lua')]
            if lua_files:
                app_id = lua_files[0].replace('.lua', '')
                if app_id not in sources:
                    sources[app_id] = {}
                sources[app_id]['local_lua'] = True
                
    return sources

def download_cloud_patch(app_id, app_name, cloud_obj, all_cloud_objs=None):
    """
    自 Google Drive 下載線上補丁壓縮包（支援本地快取直接複用與多分卷 .part1/.part2 自動完整下載）
    """
    try:
        import gdown
        import re
        from pathlib import Path
        d = get_app_cache_dir(app_id, app_name, create=True)
        d.mkdir(parents=True, exist_ok=True)

        # 🌟 自動整合多分卷清單 (例如 .part1.rar 與 .part2.rar 必須同時在同目錄下才能解壓)
        objs_to_download = []
        if all_cloud_objs and isinstance(all_cloud_objs, list):
            objs_to_download = list(all_cloud_objs)
        elif cloud_obj:
            objs_to_download = [cloud_obj]
            primary_name = Path(cloud_obj['path']).name
            m_part = re.match(r'^(.+)\.part\d+\.(rar|zip|7z)$', primary_name, re.IGNORECASE)
            if m_part and _cloud_cache:
                base_prefix = m_part.group(1).lower()
                for item in _cloud_cache:
                    iname = Path(item.get('path', '')).name
                    if iname.lower().startswith(base_prefix + '.part') and item not in objs_to_download:
                        objs_to_download.append(item)

        if not objs_to_download and cloud_obj:
            objs_to_download = [cloud_obj]

        primary_out_path = None
        for obj in objs_to_download:
            file_name = Path(obj['path']).name
            out_path = d / file_name
            if _is_primary_archive_part(file_name) or primary_out_path is None:
                primary_out_path = out_path

            # 🌟 若本地快取已存在有效檔案 (例如階段 4 已預先下載)，直接複用免重複下載！
            if out_path.exists() and out_path.stat().st_size > 1024:
                continue

            downloaded_ok = False
            file_id = obj.get('id')
            if file_id:
                try:
                    res = gdown.download(id=file_id, output=str(out_path), quiet=True)
                    if res and Path(res).exists() and Path(res).stat().st_size > 0:
                        downloaded_ok = True
                except Exception as ge:
                    logger.warning(f"[OnlineFix] gdown id 下載異常 ({file_name}): {ge}")

            if not downloaded_ok:
                drive_url = obj.get('drive_url') or obj.get('url')
                if drive_url:
                    try:
                        res = gdown.download(url=drive_url, output=str(out_path), quiet=True)
                        if res and Path(res).exists() and Path(res).stat().st_size > 0:
                            downloaded_ok = True
                    except Exception as ge2:
                        logger.warning(f"[OnlineFix] gdown url 下載異常 ({file_name}): {ge2}")

            if not downloaded_ok and not (out_path.exists() and out_path.stat().st_size > 0):
                return None

        if primary_out_path and primary_out_path.exists() and primary_out_path.stat().st_size > 0:
            return str(primary_out_path)
        return None
    except Exception as e:
        print(f"Error downloading patch for app {app_id}: {e}")
        return None

def install_lua(app_id, source, target_dir):
    app_id = str(app_id)
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / f"{app_id}.lua"
    
    if source.get('local_lua'):
        # Local lua exists in LOCAL_PATCH_DIR
        for root, dirs, files in os.walk(LOCAL_PATCH_DIR):
            if f"{app_id}.lua" in files:
                src_file = Path(root) / f"{app_id}.lua"
                try:
                    shutil.copy2(src_file, target_file)
                    return True, "Lua 本地複製成功"
                except Exception as e:
                    return False, f"Lua 複製失敗: {e}"
                    
    elif source.get('cloud_lua'):
        # Need to download cloud lua
        # We need the cloud_obj for lua. Unfortunately we only stored boolean True in get_patch_sources.
        # Let's fix get_patch_sources to store the cloud object for lua as well!
        cloud_obj = source.get('cloud_lua_obj')
        if cloud_obj:
            res = download_cloud_patch(app_id, None, cloud_obj)
            if res and os.path.exists(res):
                try:
                    shutil.copy2(res, target_file)
                    return True, "Lua 雲端下載並安裝成功"
                except Exception as e:
                    return False, f"Lua 複製失敗: {e}"
    
    return False, "找不到可用的 Lua 來源"

def uninstall_lua(app_id, target_dir):
    app_id = str(app_id)
    target_file = Path(target_dir) / f"{app_id}.lua"
    if target_file.exists():
        try:
            target_file.unlink()
            return True, "Lua 移除成功"
        except Exception as e:
            return False, f"移除失敗: {e}"
    return False, "Lua 檔案不存在"



def _extract_archive_to_dir(rar_path: Path, dest_dir: Path):
    """
    將壓縮檔 (.rar / .zip / .7z) 解壓縮至指定暫存資料夾，並藉由實地掃描暫存資料夾取得檔案清單。
    🌟 徹底廢除 WinRAR 不支援的 'lb' 命令，100% 相容 WinRAR.exe (GUI)、UnRAR.exe 與 7z.exe！
    回傳: (working_pwd, rel_files, last_err)
    """
    global EXTRACTOR
    rar_path = Path(rar_path)
    dest_dir = Path(dest_dir)
    rar_path_str = str(rar_path)
    last_err = ""

    # 1. 若為 .zip 優先嘗試 Python 內建 zipfile 解壓
    if rar_path_str.lower().endswith('.zip'):
        import zipfile
        try:
            with zipfile.ZipFile(rar_path_str) as zf:
                is_encrypted = any(f.flag_bits & 0x1 for f in zf.infolist())
                passwords_to_try = [""] if not is_encrypted else ARCHIVE_PASSWORDS
                for pwd in passwords_to_try:
                    try:
                        if dest_dir.exists():
                            shutil.rmtree(dest_dir, ignore_errors=True)
                        dest_dir.mkdir(parents=True, exist_ok=True)
                        pwd_bytes = pwd.encode('utf-8') if pwd else None
                        zf.extractall(path=str(dest_dir), pwd=pwd_bytes)
                        rel_files = [str(p.relative_to(dest_dir)) for p in dest_dir.rglob("*") if p.is_file()]
                        if rel_files:
                            return pwd, rel_files, ""
                    except NotImplementedError as nie:
                        last_err = f"ZIP 壓縮算法需外部工具支援 ({nie})"
                        break
                    except Exception as ze:
                        last_err = str(ze)
                        continue
        except Exception as e:
            last_err = str(e)

    # 2. 使用外部解壓工具 (多工具備援輪替：7-Zip ➔ UnRAR ➔ WinRAR)
    available_tools = get_all_available_extractors()
    if not available_tools:
        if EXTRACTOR:
            available_tools = [EXTRACTOR]
        else:
            cand = get_extractor()
            if cand:
                available_tools = [cand]

    if not available_tools:
        return None, [], last_err or "找不到解壓縮工具！請先安裝 7-Zip 或 WinRAR。"

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    is_rar_file = rar_path_str.lower().endswith('.rar') or bool(re.search(r'\.part\d+\.rar$', rar_path_str.lower()))

    for tool in available_tools:
        # UnRAR.exe 僅支援 .rar 格式，若非 RAR 檔案則自動跳過，由 7z 或 WinRAR.exe 處理
        if not is_rar_file and tool.get("is_unrar_only", False):
            continue

        for pwd in ARCHIVE_PASSWORDS:
            try:
                if dest_dir.exists():
                    shutil.rmtree(dest_dir, ignore_errors=True)
                dest_dir.mkdir(parents=True, exist_ok=True)

                # 🌟 當測試空密碼時使用 -p-，防止 7z 或 WinRAR 彈出密碼詢問視窗或無窮等待
                pwd_arg = f"-p{pwd}" if pwd else "-p-"

                if tool["type"] == "7z":
                    cmd = [tool["path"], "x", pwd_arg, "-y", f"-o{dest_dir}", str(rar_path)]
                elif tool.get("is_unrar_only", False):
                    # UnRAR.exe 專屬參數 (無 -ibck)
                    dest_str = str(dest_dir)
                    if not dest_str.endswith('\\'):
                        dest_str += '\\'
                    cmd = [tool["path"], "x", pwd_arg, "-y", "-inul", str(rar_path), dest_str]
                else:
                    # WinRAR.exe (GUI版專屬背景無彈窗參數)
                    dest_str = str(dest_dir)
                    if not dest_str.endswith('\\'):
                        dest_str += '\\'
                    cmd = [tool["path"], "x", pwd_arg, "-y", "-inul", "-ibck", str(rar_path), dest_str]

                proc = subprocess.run(
                    cmd,
                    startupinfo=startupinfo,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=180,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                rel_files = [str(p.relative_to(dest_dir)) for p in dest_dir.rglob("*") if p.is_file()]
                if proc.returncode == 0 and rel_files:
                    return pwd, rel_files, ""
                if rel_files and proc.returncode in (0, 1):
                    # WinRAR exit code 1 (Warning: non-fatal) 但已有完整解出檔案時亦視為成功
                    non_empty = any((dest_dir / rf).stat().st_size > 0 for rf in rel_files)
                    if non_empty:
                        return pwd, rel_files, ""
                out_err = ((proc.stderr or "") + " " + (proc.stdout or "")).strip()
                if out_err:
                    last_err = out_err
            except Exception as e:
                last_err = str(e)
                continue

    if dest_dir.exists():
        shutil.rmtree(dest_dir, ignore_errors=True)
    return None, [], last_err


def get_rar_file_list(rar_path):
    """
    取得壓縮包內所有檔案相對路徑清單（自動測試密碼並支援 WinRAR.exe / UnRAR.exe / 7z.exe，完全不使用 'lb' 命令）
    """
    rar_path = Path(rar_path)
    rar_path_str = str(rar_path)
    if not rar_path.exists():
        return None, []

    if rar_path_str.lower().endswith('.zip'):
        import zipfile
        try:
            with zipfile.ZipFile(rar_path_str) as zf:
                is_encrypted = any(f.flag_bits & 0x1 for f in zf.infolist())
                if not is_encrypted:
                    files = [f.filename.replace('/', '\\') for f in zf.infolist() if not f.is_dir()]
                    if files:
                        return "", files
        except Exception:
            pass

    temp_list_dir = rar_path.parent / f"_list_tmp_{int(time.time() * 1000)}_{os.getpid()}"
    try:
        pwd, rel_files, _ = _extract_archive_to_dir(rar_path, temp_list_dir)
        if rel_files:
            return pwd, rel_files
        return None, []
    finally:
        if temp_list_dir.exists():
            shutil.rmtree(temp_list_dir, ignore_errors=True)


def install_fix(app_id, rar_path, game_dir, delete_archive=True, source_drive=None):
    global EXTRACTOR
    rar_path = Path(rar_path)
    game_dir = Path(game_dir)
    app_id = str(app_id)
    
    if not rar_path.exists() or not game_dir.exists():
        return False, "檔案或資料夾不存在"
        
    if not str(rar_path).lower().endswith('.zip'):
        if not EXTRACTOR:
            EXTRACTOR = get_extractor()
        if not EXTRACTOR:
            return False, "找不到解壓縮工具！請先安裝 7-Zip 或 WinRAR。"

    temp_extract_dir = rar_path.parent / f"_extract_tmp_{app_id}_{int(time.time() * 1000)}"
    try:
        working_pwd, files_to_extract, extract_err = _extract_archive_to_dir(rar_path, temp_extract_dir)
        if not files_to_extract:
            detail = f" ({extract_err[:80]})" if extract_err else ""
            return False, f"無法讀取或解壓縮補丁檔內容，可能密碼錯誤、分卷不完整或檔案毀損{detail}"

        backed_up = []
        for rel_path in files_to_extract:
            src_extracted = temp_extract_dir / rel_path
            if not src_extracted.exists() or not src_extracted.is_file():
                continue

            target_path = game_dir / rel_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            is_known_crack = is_known_crack_file(target_path)

            if target_path.exists():
                bak_path = target_path.with_suffix(target_path.suffix + '.bak')
                # 避免套娃：如果目標檔案本身就是已知的 Online-Fix / ZeiGames 補丁檔案，絕不備份為 .bak！
                if not is_known_crack and not bak_path.exists():
                    try:
                        shutil.move(str(target_path), str(bak_path))
                        backed_up.append(str(rel_path))
                    except Exception:
                        pass
                else:
                    try:
                        import stat
                        os.chmod(str(target_path), stat.S_IWRITE | stat.S_IREAD)
                        target_path.unlink()
                    except Exception:
                        pass

            # 將暫存目錄已解壓之檔案搬移/覆寫至遊戲目錄
            try:
                if target_path.exists():
                    import stat
                    os.chmod(str(target_path), stat.S_IWRITE | stat.S_IREAD)
                shutil.copy2(str(src_extracted), str(target_path))
            except Exception as copy_err:
                raise copy_err

        record = _load_record(app_id) or {}
        record.update({
            "game_dir": str(game_dir),
            "installed_files": files_to_extract,
            "backed_up_files": backed_up,
            "source_drive": source_drive or "Google Drive",
            "timestamp": os.path.getmtime(rar_path) if rar_path.exists() else int(time.time())
        })
        _save_record(app_id, record)

        # 關鍵需求：安裝完成後立即刪除臨時下載的壓縮檔（含多分卷 .part*.rar），不永久留存
        if delete_archive and rar_path.exists():
            try:
                import re
                parent_dir = rar_path.parent
                m_part = re.match(r'^(.+)\.part\d+\.(rar|zip|7z)$', rar_path.name, re.IGNORECASE)
                rar_path.unlink(missing_ok=True)
                if m_part and parent_dir.exists():
                    base_prefix = m_part.group(1).lower()
                    for sib in list(parent_dir.iterdir()):
                        if sib.is_file() and sib.name.lower().startswith(base_prefix + '.part'):
                            try:
                                sib.unlink(missing_ok=True)
                            except Exception:
                                pass
                if parent_dir != LOCAL_PATCH_DIR and parent_dir.exists() and not any(parent_dir.iterdir()):
                    parent_dir.rmdir()
            except Exception as e:
                print(f"Error cleaning up archive: {e}")

        return True, "安裝成功"
    except PermissionError as e:
        return False, f"⚠️ 檔案被 Windows Defender 或防毒軟體鎖定無法替換 ({e})。請將 Steam 遊戲目錄加入防毒排除名單後再試！"
    except Exception as e:
        err_str = str(e)
        if "WinError 32" in err_str or "WinError 5" in err_str or "Access is denied" in err_str or "225" in err_str:
            return False, f"⚠️ 檔案存取被拒 (可能被防毒軟體即時掃描或遊戲程序鎖定: {e})。請將 Steam 目錄加入防毒排除名單後再試！"
        return False, f"解壓縮失敗: {e}"
    finally:
        if temp_extract_dir.exists():
            shutil.rmtree(temp_extract_dir, ignore_errors=True)

def uninstall_fix(app_id, forced_rar_path=None):
    app_id = str(app_id)
    record = _load_record(app_id)
    
    if not record:
        if forced_rar_path and os.path.exists(forced_rar_path):
            game_dir = _find_steam_game_dir(app_id)
            if not game_dir or not game_dir.exists():
                return False, "找不到遊戲目錄，無法執行強制移除"
            
            _, files_to_remove = get_rar_file_list(forced_rar_path)
            if not files_to_remove:
                return False, "無法讀取比對壓縮檔內容"
                
            for rel_path in files_to_remove:
                target = game_dir / rel_path
                if target.exists():
                    try:
                        target.unlink()
                    except:
                        pass
                
                # Check if a .bak exists and restore it, even without records!
                bak_path = target.with_suffix(target.suffix + '.bak')
                if bak_path.exists() and not target.exists():
                    try:
                        shutil.move(str(bak_path), str(target))
                    except:
                        pass
            
            # 全樹兜底還原
            for bak in game_dir.rglob("*.bak"):
                orig = bak.with_suffix('')
                if not orig.exists():
                    try:
                        shutil.move(str(bak), str(orig))
                    except:
                        pass
            _delete_record(app_id)
            return True, "強制移除完成，已清理補丁檔案並還原原檔"
        return False, "此遊戲沒有安裝紀錄，且無可用比對檔案"
        
    game_dir_str = record.get("game_dir")
    if not game_dir_str:
        game_dir = _find_steam_game_dir(app_id)
        if not game_dir:
            return False, "找不到遊戲目錄，無法執行移除"
    else:
        game_dir = Path(game_dir_str)
        
    if not game_dir.exists():
        return False, "遊戲目錄不存在"
        
    installed = record.get("installed_files", [])
    backed_up = record.get("backed_up_files", [])
    
    # If it was detected via manual install / residual signatures (Online-Fix, ZeiGames, etc.):
    if record.get("manual_install") or record.get("is_signature"):
        # 1. Clean recorded installed files
        for rel_path in installed:
            target = game_dir / rel_path
            if target.exists():
                try:
                    target.unlink()
                except:
                    pass
        # 2. Clean all known crack/fix signatures found in game directory (Online-Fix, ZeiGames, Goldberg)
        try:
            for item in game_dir.iterdir():
                if item.is_file() and is_known_crack_file(item.name):
                    try:
                        item.unlink()
                    except:
                        pass
        except Exception:
            pass
            
        # 3. Clean steam_settings folder if present from ZeiGames/Goldberg fixes
        steam_settings = game_dir / "steam_settings"
        if steam_settings.exists() and steam_settings.is_dir():
            try:
                shutil.rmtree(steam_settings, ignore_errors=True)
            except:
                pass
                
        # 4. Restore any .bak files found across all subdirectories
        for bak in game_dir.rglob("*.bak"):
            orig = bak.with_suffix('')
            if not orig.exists():
                try:
                    shutil.move(str(bak), str(orig))
                except:
                    pass
        _delete_record(app_id, game_dir)
        return True, "已清理所有補丁相關檔案並還原原始檔案 (.bak)！"
        
    # 依清單帳本 (Ledger) 精準刪除補丁安裝之檔案
    for rel_path in installed:
        target = game_dir / rel_path
        if target.exists():
            try:
                target.unlink()
            except:
                pass
                
    # 依清單帳本精準將備份的原檔 (.bak) 復原
    for rel_path in backed_up:
        target = game_dir / rel_path
        bak_path = target.with_suffix(target.suffix + '.bak')
        if bak_path.exists():
            try:
                shutil.move(str(bak_path), str(target))
            except:
                pass

    # 兜底全樹搜尋：若有未在記錄中的 .bak (包含多層子目錄)，全數復原
    for bak in game_dir.rglob("*.bak"):
        orig = bak.with_suffix('')
        if not orig.exists():
            try:
                shutil.move(str(bak), str(orig))
            except:
                pass
                
    steam_settings = game_dir / "steam_settings"
    if steam_settings.exists() and steam_settings.is_dir():
        try:
            shutil.rmtree(steam_settings, ignore_errors=True)
        except:
            pass
            
    _delete_record(app_id, game_dir)
        
    return True, "移除成功並已還原原始檔案"

def get_fix_status(app_id):
    app_id = str(app_id)
    try:
        record = _load_record(app_id)
        if not record:
            return "未安裝"
            
        game_dir_str = record.get("game_dir")
        if not game_dir_str:
            return "未安裝"
            
        game_dir = Path(game_dir_str)
        if not game_dir.exists():
            return "⚠️ 遊戲目錄遺失"
            
        if record.get("is_signature"):
            return "✅ 已安裝"
            
        installed = record.get("installed_files", [])
        if not installed:
            return "✅ 已安裝"
            
        # 優先精準校驗關鍵二進位/設定檔 (涵蓋 Online-Fix 與 ZeiGames 補丁特徵)
        key_files = [f for f in installed if is_known_crack_file(f) or f.lower().endswith(('.dll', '.ini', '.exe', '.url'))]
        check_list = key_files if key_files else installed[:10]
        
        missing_count = 0
        for f in check_list:
            if not (game_dir / f).exists():
                missing_count += 1
                
        # 🌟 若關鍵補丁檔案全數遺失 (例如 Steam 驗證完整性還原，或使用者手動刪除)
        if missing_count == len(check_list) and len(check_list) > 0:
            # 自動清理孤立失效的紀錄表，恢復乾淨狀態
            _delete_record(app_id, game_dir)
            return "未安裝"

        if missing_count > 0:
            return "⚠️ 部分補丁檔案遺失 (可能被防毒刪除)"
                
        return "✅ 已安裝"
    except Exception:
        return "未安裝"

def is_patch_deployed_locally(app_id: str) -> bool:
    """識別本地 Steam 遊戲目錄下是否已實際部署/套用聯機或專用補丁"""
    status = get_fix_status(app_id)
    return "已安裝" in status

def is_patch_protected(app_id: str) -> bool:
    """
    精確識別本地 Steam 遊戲目錄下是否成功備份了原始檔案 (.bak 或 backed_up_files 記錄)。
    只有在確實有聯機補丁備份檔案時才判定為保護狀態。
    """
    app_id = str(app_id)
    game_dir = _find_steam_game_dir(app_id)
    if not game_dir or not game_dir.exists():
        return False
        
    # 1. 直接檢查遊戲目錄下是否存在 .bak 備份檔案
    try:
        bak_files = list(game_dir.glob("*.bak"))
        if bak_files:
            return True
    except Exception:
        pass
        
    # 2. 檢查 .onlinefix_record.json 或本地快取記錄中的 backed_up_files
    rec = _load_record(app_id)
    if rec:
        backed_up = rec.get("backed_up_files", [])
        if backed_up and len(backed_up) > 0:
            for bf in backed_up:
                bak_p = game_dir / (bf + ".bak")
                if bak_p.exists():
                    return True
                if (game_dir / bf).exists() and bf.endswith('.bak'):
                    return True
    return False

def get_fix_record(app_id):
    return _load_record(str(app_id))

_cached_onlinefix_appids = None
_cached_onlinefix_time = 0

def get_all_onlinefix_appids(force: bool = False):
    """
    精準提取所有真正收錄有 Online-Fix / ZeiGames 聯機補丁的 AppID 清單。
    具備記憶體與磁碟持久化雙層快取機制（記憶體 180 秒，磁碟 24 小時），杜絕重複磁碟與二重迴圈比對，冷啟動 < 1ms。
    """
    global _cached_onlinefix_appids, _cached_onlinefix_time
    now = time.time()
    if not force and _cached_onlinefix_appids is not None and (now - _cached_onlinefix_time < 180):
        return list(_cached_onlinefix_appids)

    # 磁碟持久化快取檢查 (冷啟動極速載入)
    cache_json = config_manager._root_dir / "data" / "onlinefix_appids.json"
    if not force and cache_json.exists():
        try:
            # 若快取在 24 小時內，直接讀取
            if (now - cache_json.stat().st_mtime) < 86400:
                data = json.loads(cache_json.read_text(encoding="utf-8"))
                if isinstance(data, list) and data:
                    _cached_onlinefix_appids = data
                    _cached_onlinefix_time = now
                    return list(_cached_onlinefix_appids)
        except Exception:
            pass

    _clean_empty_cache_dirs()
    appids = set()
    
    # 1. 讀取雲端快取檔案
    cache = fetch_cloud_cache(force=False)
    if cache:
        import re
        # 載入遊戲名稱快取用於名稱反向匹配 (支援無 AppID 檔名的補丁)
        cache_file = config_manager._root_dir / "data" / "game_cache.json"
        game_cache = {}
        if cache_file.exists():
            try:
                game_cache = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                game_cache = {}

        for f in cache:
            # 優先採用快取中已標記之 app_id
            aid = f.get('app_id')
            if not aid:
                p = (f.get('name') or f.get('path') or '').replace('/', '\\')
                parts = p.split('\\')
                fname = parts[-1]
                folder_part = parts[0] if len(parts) >= 2 else ""
                aid = resolve_appid_for_patch_file(fname, folder_part=folder_part)
            if aid:
                appids.add(str(aid))
                    
    # 2. 讀取本地快取目錄中真正存在實體補丁檔案的資料夾
    if LOCAL_PATCH_DIR.exists():
        import re
        for d in LOCAL_PATCH_DIR.iterdir():
            if d.is_dir():
                # 必須真正含有補丁壓縮檔或 Lua 檔才算數！
                files = list(d.iterdir())
                has_real_patch = any(f.suffix.lower() in ('.rar', '.zip', '.7z', '.lua') for f in files)
                if has_real_patch:
                    m = re.findall(r'\b(\d{4,9})\b', d.name)
                    for aid in m:
                        appids.add(str(aid))
    res = list(appids)
    _cached_onlinefix_appids = res
    _cached_onlinefix_time = now

    # 寫入磁碟持久化快取
    try:
        cache_json.parent.mkdir(parents=True, exist_ok=True)
        cache_json.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    return res


# ═══════════════════════════════════════════════════════
# Steam 下載狀態即時監控與自動部署 / 錯誤中斷系統
# ═══════════════════════════════════════════════════════
UPDATE_ERROR_MESSAGES = {
    1: "Steam 回報未知錯誤",
    3: "Steam 下載已手動取消",
    4: "Steam 下載已暫停中斷",
    5: "無網際網路連線 (Steam 下載失敗)",
    6: "磁碟空間不足 (Steam 磁碟已滿)",
    7: "磁碟寫入錯誤 (Disk I/O Error)",
    8: "檔案內容損毀 (Content Corrupt)",
    9: "清單檔案損毀 (Manifest Corrupt)",
    10: "內容檔案鎖定 (Content File Locked，檔案被佔用)",
    11: "連線超時 (Connection Timeout)",
    12: "缺少清單 (無法取得 Manifest 授權 / 401 錯誤)",
    13: "缺少寫入權限 (No Privileges)",
    14: "檔案搬移失敗 (Move Failed)",
    15: "家長控制阻止下載",
    28: "磁碟損壞 (Corrupt Disk)"
}

def get_steam_app_download_report(app_id: str) -> dict:
    """
    精確解析 Steam 遊戲的下載狀態、錯誤代碼與安裝進度。
    回傳 status:
      - 'COMPLETED': 完全安裝就緒 (StateFlags == 4 且執行檔存在)
      - 'DOWNLOADING': 正常下載/更新中
      - 'PAUSED': 下載暫停中
      - 'ERROR': 發生下載錯誤 (內容鎖定、無網路、缺清單等)
      - 'CANCELLED': 任務已取消或 ACF 被移除
    """
    app_id = str(app_id).strip()
    import winreg, re
    from managers import steam_manager
    sp = steam_manager.find_steam_path()
    libs = set()
    if sp: libs.add(os.path.normpath(sp))
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam')
        path, _ = winreg.QueryValueEx(key, 'SteamPath')
        winreg.CloseKey(key)
        libs.add(os.path.normpath(path))
    except Exception:
        pass
        
    for lib in list(libs):
        vdf_path = os.path.join(lib, 'steamapps', 'libraryfolders.vdf')
        if os.path.exists(vdf_path):
            try:
                content = open(vdf_path, encoding='utf-8', errors='ignore').read()
                matches = re.findall(r'"path"\s+"([^"]+)"', content, re.IGNORECASE)
                for m in matches:
                    libs.add(os.path.normpath(m.replace('\\\\', '\\')))
            except Exception:
                pass

    libs_list = list(libs)
    found_acf = None
    target_lib = libs_list[0] if libs_list else ""
    for lib in libs_list:
        acf = os.path.join(lib, 'steamapps', f'appmanifest_{app_id}.acf')
        if os.path.exists(acf):
            found_acf = acf
            target_lib = lib
            break

    try:
        from managers import steam_tracker
        live_rep = steam_tracker.get_steam_live_report(app_id, target_lib)
        st = live_rep.get("status", "NOT_INSTALLED")
        return {
            "status": st,
            "app_id": app_id,
            "state_flags": 4 if st == "COMPLETED" else (512 if st == "PAUSED" else (1024 if st == "DOWNLOADING" else 0)),
            "update_result": 0,
            "error_msg": "使用者已取消下載" if st == "CANCELLED" else None,
            "bytes_downloaded": live_rep.get("bytes_downloaded", 0),
            "bytes_to_download": live_rep.get("bytes_to_download", 0),
            "progress_pct": live_rep.get("progress_pct", 0.0),
            "speed_str": live_rep.get("speed_str", ""),
            "stage_name": live_rep.get("stage_name", st),
            "game_dir": live_rep.get("game_dir", "")
        }
    except Exception as e:
        logger.error(f"[get_steam_app_download_report] steam_tracker 異常: {e}", exc_info=True)
        return {
            "status": "NOT_INSTALLED",
            "app_id": app_id,
            "state_flags": 0,
            "update_result": 0,
            "error_msg": str(e),
            "bytes_downloaded": 0,
            "bytes_to_download": 0,
            "progress_pct": 0.0,
            "speed_str": "",
            "stage_name": "NOT_INSTALLED",
            "game_dir": ""
        }


import threading

class SteamDeployWatcher:
    """Steam 下載狀態背景監控與自動部署管理器 (線程安全單例)"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SteamDeployWatcher, cls).__new__(cls)
                cls._instance._tasks = {} # appid -> dict
                cls._instance._stop_events = {} # appid -> Event
        return cls._instance

    def is_watching(self, app_id: str) -> bool:
        return str(app_id).strip() in self._tasks

    def get_all_watching(self) -> list:
        return list(self._tasks.keys())

    def stop_watch(self, app_id: str):
        app_id = str(app_id).strip()
        with self._lock:
            if app_id in self._stop_events:
                self._stop_events[app_id].set()
            if app_id in self._tasks:
                del self._tasks[app_id]

    def start_watch(self, app_id: str, game_name: str, on_complete=None, on_error=None, max_wait_seconds=7200):
        app_id = str(app_id).strip()
        with self._lock:
            if app_id in self._tasks:
                return False # 已在監控中
            stop_evt = threading.Event()
            self._stop_events[app_id] = stop_evt
            self._tasks[app_id] = {
                "app_id": app_id,
                "game_name": game_name,
                "started_at": time.time()
            }

        def _monitor_loop():
            start_t = time.time()
            cancelled_counts = 0
            while not stop_evt.is_set():
                if time.time() - start_t > max_wait_seconds:
                    self.stop_watch(app_id)
                    if on_error:
                        on_error(app_id, game_name, "監控超時 (超過 2 小時尚未下載完成)")
                    break

                rep = get_steam_app_download_report(app_id)
                status = rep.get("status")

                if status == "COMPLETED":
                    # 下載完成！立即觸發自動補丁部署
                    self.stop_watch(app_id)
                    if on_complete:
                        on_complete(app_id, game_name, rep.get("game_dir"))
                    break

                elif status == "ERROR":
                    # 呈現錯誤 (如無網路、檔案鎖定、缺清單)！立即取消部署
                    self.stop_watch(app_id)
                    err_msg = rep.get("error_msg") or f"Steam 回報錯誤 (代碼 {rep.get('update_result')})"
                    if on_error:
                        on_error(app_id, game_name, err_msg)
                    break

                elif status == "CANCELLED":
                    # 連續 3 次檢查均無清單才確認取消 (防短暫磁碟延遲)
                    cancelled_counts += 1
                    if cancelled_counts >= 3:
                        self.stop_watch(app_id)
                        if on_error:
                            on_error(app_id, game_name, "Steam 下載已手動取消或排程移除")
                        break
                else:
                    cancelled_counts = 0

                # 每 3 秒檢查一次
                time.sleep(3)

        t = threading.Thread(target=_monitor_loop, daemon=True, name=f"SteamWatch_{app_id}")
        t.start()
        return True

_deploy_watcher = SteamDeployWatcher()


# ═══════════════════════════════════════════════════════
# 🌟 Google Drive 雲端補丁庫背景預載入與定時輪詢守護器
# ═══════════════════════════════════════════════════════
_scheduler_started = False
_scheduler_lock = threading.Lock()

def start_cloud_sync_scheduler(interval_sec=300):
    """
    啟動 Google Drive 雲端補丁庫背景預載入與定時輪詢守護執行緒。
    1. 啟動即非同步預載入：軟體開啟時立即於背景向 Google Drive 確定數據，不阻塞 UI；
    2. 定時週期性輪詢：每隔 interval_sec (預設 300 秒) 自動刷新 Google Drive 最新檔案清單；
    3. 全域資料保鮮：確保小卡無論何時查詢，均走記憶體/本地快取，絕對不需等用戶點開小卡才主動連網 TRY。
    """
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True

    def _worker():
        # 1. 啟動首波非同步預載入 (延遲 0.8 秒避開視窗啟動尖峰)
        time.sleep(0.8)
        try:
            print("[OnlineFix] 🚀 啟動背景預載入 Google Drive 雲端補丁庫...")
            fetch_cloud_cache(force=False, min_interval=0)
            aids = get_all_onlinefix_appids(force=True)
            print(f"[OnlineFix] ✅ Google Drive 補丁庫預載入完成，目前收錄 {len(aids)} 款遊戲聯機補丁: {aids}")
        except Exception as e:
            print(f"[OnlineFix] 預載入異常: {e}")

        # 2. 背景定時循環輪詢
        while True:
            time.sleep(interval_sec)
            try:
                print("[OnlineFix] 🔄 正在背景定時輪詢 Google Drive 補丁庫以保持最新數據...")
                fetch_cloud_cache(force=True, min_interval=interval_sec - 10)
                aids = get_all_onlinefix_appids(force=True)
                print(f"[OnlineFix] 🔄 輪詢完成，目前收錄 {len(aids)} 款遊戲聯機補丁。")
            except Exception as e:
                print(f"[OnlineFix] 背景輪詢異常: {e}")

    t = threading.Thread(target=_worker, name="GDriveSyncScheduler", daemon=True)
    t.start()


