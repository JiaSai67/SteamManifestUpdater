import os
import subprocess
import shutil
from pathlib import Path
import json
import sys
import time

from managers import config_manager
_config = config_manager.get_config()

import winreg

def get_extractor():
    # 0. 優先嘗試專案內建的解壓縮工具 (讓用戶能將工具直接打包進專案)
    local_tools = [
        ("winrar", config_manager._root_dir / "UnRAR.exe"),
        ("winrar", config_manager._root_dir / "opensteamtools" / "UnRAR.exe"),
        ("winrar", config_manager._root_dir / "assets" / "UnRAR.exe"),
        ("winrar", config_manager._root_dir / "WinRAR.exe"),
        ("7z", config_manager._root_dir / "7z.exe"),
        ("7z", config_manager._root_dir / "opensteamtools" / "7z.exe"),
    ]
    for ext_type, p in local_tools:
        if p.exists():
            return {"type": ext_type, "path": str(p)}

    # 1. 嘗試從註冊表找 7-Zip
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\7-Zip") as key:
            path, _ = winreg.QueryValueEx(key, "Path")
            exe_path = os.path.join(path, "7z.exe")
            if os.path.exists(exe_path):
                return {"type": "7z", "path": exe_path}
    except Exception:
        pass
        
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\7-Zip") as key:
            path, _ = winreg.QueryValueEx(key, "Path64")
            exe_path = os.path.join(path, "7z.exe")
            if os.path.exists(exe_path):
                return {"type": "7z", "path": exe_path}
    except Exception:
        pass

    # 2. 嘗試常見 7-Zip 路徑
    for p in [r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"]:
        if os.path.exists(p):
            return {"type": "7z", "path": p}

    # 3. 嘗試從註冊表找 WinRAR
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WinRAR") as key:
            path, _ = winreg.QueryValueEx(key, "exe64")
            if os.path.exists(path):
                return {"type": "winrar", "path": path}
    except Exception:
        pass
        
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WinRAR") as key:
            path, _ = winreg.QueryValueEx(key, "exe32")
            if os.path.exists(path):
                return {"type": "winrar", "path": path}
    except Exception:
        pass

    # 4. 嘗試常見 WinRAR 路徑
    for p in [r"C:\Program Files\WinRAR\WinRAR.exe", r"C:\Program Files (x86)\WinRAR\WinRAR.exe"]:
        if os.path.exists(p):
            return {"type": "winrar", "path": p}

    return None

EXTRACTOR = get_extractor()
ARCHIVE_PASSWORDS = ["online-fix.me", "zeigames.com", ""]

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
                    m = m.replace('\\\\', '\\')
                    libs.add(os.path.normpath(m))
            except Exception:
                pass
                
    for lib in libs:
        acf = os.path.join(lib, 'steamapps', f'appmanifest_{app_id}.acf')
        if os.path.exists(acf):
            try:
                content = open(acf, encoding='utf-8', errors='ignore').read()
                m = re.search(r'"installdir"\s+"([^"]+)"', content, re.IGNORECASE)
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
    except:
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
                    
                    # 辨識 AppID
                    app_id = None
                    if len(parts) >= 2:
                        m = re.search(r'(?:^|[^0-9])(\d{4,9})(?:[^0-9]|$)', parts[0])
                        if m:
                            app_id = m.group(1)
                    if not app_id:
                        m = re.search(r'(?:^|[^0-9])(\d{4,9})(?:[^0-9]|$)', file_name)
                        if m:
                            app_id = m.group(1)
                            
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

def get_patch_sources(target_apps=None, target_app_id=None, target_app_name=None, allow_network=False, force_refresh=False):
    global _cloud_cache
    if target_apps is None:
        target_apps = {}
    if target_app_id and target_app_name:
        target_apps[str(target_app_id)] = target_app_name
        
    sources = {}
    
    # 1. Primary: Scan Cloud (Cloud is the authoritative source for all users)
    if (_cloud_cache is None and allow_network) or force_refresh:
        fetch_cloud_cache(force=True)
            
    cloud_folders = {}
    root_rar_files = [] # Files in the root without a folder
    
    if _cloud_cache:
        # Sort by drive_priority ascending (so higher priority drives are indexed first)
        sorted_cache = sorted(_cloud_cache, key=lambda x: x.get('drive_priority', 999))
        for f in sorted_cache:
            norm_path = f['path'].replace('/', '\\')
            parts = norm_path.split('\\')
            drive_prio = f.get('drive_priority', 999)
            drive_name = f.get('drive_name', '網盤 1')
            file_name = parts[-1]
            
            # Extract app_id from path or filename
            import re
            app_id = None
            if len(parts) >= 2:
                # check folder name for digits
                m = re.search(r'(?:^|[^0-9])(\d{4,9})(?:[^0-9]|$)', parts[0])
                if m:
                    app_id = m.group(1)
            if not app_id:
                # check filename for digits
                m = re.search(r'(?:^|[^0-9])(\d{4,9})(?:[^0-9]|$)', file_name)
                if m:
                    app_id = m.group(1)
                    
            if app_id:
                if app_id not in sources:
                    sources[app_id] = {
                        'drive_priority': drive_prio,
                        'drive_name': drive_name
                    }
                
                # If this file comes from a higher priority drive (lower prio number)
                if drive_prio <= sources[app_id].get('drive_priority', 999):
                    if drive_prio < sources[app_id].get('drive_priority', 999):
                        sources[app_id]['drive_priority'] = drive_prio
                        sources[app_id]['drive_name'] = drive_name
                        sources[app_id].pop('cloud_rar', None)
                        sources[app_id].pop('cloud_lua', None)
                        sources[app_id].pop('cloud_lua_obj', None)
                        
                    if file_name.endswith('.lua'):
                        sources[app_id]['cloud_lua'] = True
                        sources[app_id]['cloud_lua_obj'] = f
                    elif file_name.endswith('.rar') or file_name.endswith('.zip'):
                        sources[app_id]['cloud_rar'] = f
                
        # Fuzzy match logic for target_apps
        if target_apps:
            for app_id, app_name in target_apps.items():
                app_id = str(app_id)
                if app_id not in sources:
                    sources[app_id] = {}
                    
                if 'cloud_rar' not in sources[app_id]:
                    import re
                    target_norm = re.sub(r'[^a-z0-9]', '', app_name.lower())
                    if target_norm:
                        for f in sorted_cache:
                            if f['path'].lower().endswith(('.rar', '.zip')):
                                f_norm = re.sub(r'[^a-z0-9]', '', f['path'].lower())
                                if target_norm in f_norm:
                                    prio = f.get('drive_priority', 999)
                                    if 'drive_priority' not in sources[app_id] or prio < sources[app_id]['drive_priority']:
                                        sources[app_id]['cloud_rar'] = f
                                        sources[app_id]['drive_name'] = f.get('drive_name', '網盤 1')
                                        sources[app_id]['drive_priority'] = prio
                                    break
                            
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

def download_cloud_patch(app_id, app_name, cloud_obj):
    try:
        import gdown
        from pathlib import Path
        d = get_app_cache_dir(app_id, app_name, create=True)
        d.mkdir(parents=True, exist_ok=True)
        file_name = Path(cloud_obj['path']).name
        out_path = d / file_name
        
        file_id = cloud_obj.get('id')
        if file_id:
            res = gdown.download(id=file_id, output=str(out_path), quiet=True)
            if res and Path(res).exists() and Path(res).stat().st_size > 0:
                return res
                
        drive_url = cloud_obj.get('drive_url') or cloud_obj.get('url')
        if drive_url:
            res = gdown.download(url=drive_url, output=str(out_path), quiet=True)
            if res and Path(res).exists() and Path(res).stat().st_size > 0:
                return res
                
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



def get_rar_file_list(rar_path):
    rar_path_str = str(rar_path)
    if rar_path_str.lower().endswith('.zip'):
        import zipfile
        try:
            with zipfile.ZipFile(rar_path_str) as zf:
                is_encrypted = any(f.flag_bits & 0x1 for f in zf.infolist())
                if not is_encrypted:
                    files = [f.filename for f in zf.infolist() if not f.is_dir()]
                    return "", files
                    
                for pwd in ARCHIVE_PASSWORDS:
                    try:
                        pwd_bytes = pwd.encode('utf-8') if pwd else None
                        for f in zf.infolist():
                            if not f.is_dir():
                                with zf.open(f, pwd=pwd_bytes) as test_f:
                                    test_f.read(1)
                                break
                        files = [f.filename for f in zf.infolist() if not f.is_dir()]
                        return pwd, files
                    except Exception:
                        continue
        except Exception as e:
            print(f"Error reading ZIP: {e}")
        return None, []
        
    if not EXTRACTOR:
        return None, []
        
    for pwd in ARCHIVE_PASSWORDS:
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            if EXTRACTOR["type"] == "7z":
                subprocess.check_call(
                    [EXTRACTOR["path"], "t", f"-p{pwd}", str(rar_path)],
                    startupinfo=startupinfo,
                    stderr=subprocess.STDOUT,
                    stdout=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                output = subprocess.check_output(
                    [EXTRACTOR["path"], "l", f"-p{pwd}", str(rar_path)],
                    startupinfo=startupinfo,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                files = []
                parsing = False
                for line in output.split('\n'):
                    if line.startswith('----'):
                        parsing = not parsing
                        continue
                    if parsing:
                        parts = line.split(maxsplit=5)
                        if len(parts) >= 6 and 'D' not in parts[2]:
                            files.append(parts[5].strip())
                return pwd, files
                
            elif EXTRACTOR["type"] == "winrar":
                subprocess.check_call(
                    [EXTRACTOR["path"], "t", "-inul", f"-p{pwd}", str(rar_path)],
                    startupinfo=startupinfo,
                    stderr=subprocess.STDOUT,
                    stdout=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                output = subprocess.check_output(
                    [EXTRACTOR["path"], "lb", "-inul", f"-p{pwd}", str(rar_path)],
                    startupinfo=startupinfo,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                files = [line.strip() for line in output.split('\n') if line.strip() and not line.strip().endswith('\\')]
                return pwd, files
                
        except subprocess.CalledProcessError:
            continue
        except Exception as e:
            print(f"Error reading RAR: {e}")
            break
            
    return None, []

def install_fix(app_id, rar_path, game_dir, delete_archive=True, source_drive=None):
    rar_path = Path(rar_path)
    game_dir = Path(game_dir)
    app_id = str(app_id)
    
    if not rar_path.exists() or not game_dir.exists():
        return False, "檔案或資料夾不存在"
        
    if str(rar_path).lower().endswith('.zip'):
        pass # Python native zip handles this without EXTRACTOR
    elif not EXTRACTOR:
        return False, "找不到解壓縮工具！請先安裝 7-Zip 或 WinRAR。"
        
    working_pwd, files_to_extract = get_rar_file_list(rar_path)
    if not files_to_extract:
        return False, "無法讀取壓縮檔內容，可能密碼錯誤或檔案毀損"
        
    backed_up = []
    for rel_path in files_to_extract:
        target_path = game_dir / rel_path
        is_known_crack = is_known_crack_file(target_path)
        
        if target_path.exists():
            bak_path = target_path.with_suffix(target_path.suffix + '.bak')
            # 避免套娃：如果目標檔案本身就是已知的 Online-Fix / ZeiGames 補丁檔案，絕不備份為 .bak！
            if not is_known_crack and not bak_path.exists():
                try:
                    import shutil
                    shutil.move(str(target_path), str(bak_path))
                    backed_up.append(str(rel_path))
                except Exception as e:
                    pass
            else:
                try:
                    target_path.unlink()
                except:
                    pass
        else:
            try:
                target_path.unlink()
            except:
                pass
                    
    try:
        if str(rar_path).lower().endswith('.zip'):
            import zipfile
            pwd_bytes = working_pwd.encode('utf-8') if working_pwd else None
            with zipfile.ZipFile(str(rar_path)) as zf:
                zf.extractall(path=str(game_dir), pwd=pwd_bytes)
        else:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            if EXTRACTOR["type"] == "7z":
                subprocess.check_call(
                    [EXTRACTOR["path"], "x", f"-p{working_pwd}", "-y", f"-o{game_dir}", str(rar_path)],
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            elif EXTRACTOR["type"] == "winrar":
                # WinRAR x command requires trailing backslash for destination directory
                dest_dir = str(game_dir)
                if not dest_dir.endswith('\\'):
                    dest_dir += '\\'
                
                # Use -inul -ibck to prevent GUI popup errors and background execution
                subprocess.check_call(
                    [EXTRACTOR["path"], "x", f"-p{working_pwd}", "-y", "-inul", "-ibck", str(rar_path), dest_dir],
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            
        record = _load_record(app_id) or {}
        record.update({
            "game_dir": str(game_dir),
            "installed_files": files_to_extract,
            "backed_up_files": backed_up,
            "source_drive": source_drive or "Google Drive",
            "timestamp": os.path.getmtime(rar_path) if rar_path.exists() else 0
        })
        _save_record(app_id, record)
        
        # 關鍵需求：安裝完成後立即刪除臨時下載的壓縮檔，不永久留存，永遠跟隨雲端最新項目
        if delete_archive and rar_path.exists():
            try:
                rar_path.unlink()
                parent_dir = rar_path.parent
                if parent_dir != LOCAL_PATCH_DIR and parent_dir.exists() and not any(parent_dir.iterdir()):
                    parent_dir.rmdir()
            except Exception as e:
                print(f"Error cleaning up archive: {e}")
                
        return True, "安裝成功"
    except PermissionError as e:
        return False, f"⚠️ 檔案被 Windows Defender 或防毒軟體鎖定無法替換 ({e})。請將 Steam 遊戲目錄加入防毒排除名單後再試！"
    except Exception as e:
        err_str = str(e)
        if "WinError 32" in err_str or "WinError 5" in err_str or "Access is denied" in err_str:
            return False, f"⚠️ 檔案存取被拒 (可能被防毒軟體即時掃描或遊戲程序鎖定: {e})。請將 Steam 目錄加入防毒排除名單後再試！"
        return False, f"解壓縮失敗: {e}"

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
            p = (f.get('name') or f.get('path') or '').replace('/', '\\')
            parts = p.split('\\')
            fname = parts[-1].lower()
            
            # 必須是補丁壓縮檔或 lua 或 patch
            if not fname.endswith(('.rar', '.zip', '.7z', '.lua')):
                continue
                
            found_numeric_aid = False
            # 從目錄名或檔名提取 appid
            for part in parts:
                m = re.findall(r'\b(\d{4,9})\b', part)
                for aid in m:
                    appids.add(str(aid))
                    found_numeric_aid = True
                    
            # 若檔名無數字，則與已知的遊戲名稱進行嚴格子字串匹配
            if not found_numeric_aid:
                norm_fname = re.sub(r'[^a-z0-9]', '', fname)
                for aid, g in game_cache.items():
                    name_en = g.get('english_name') or g.get('name_en') or ''
                    name_tc = g.get('name') or ''
                    for n in [name_en, name_tc]:
                        if n and len(n) >= 4:
                            norm_n = re.sub(r'[^a-z0-9]', '', n.lower())
                            if norm_n and len(norm_n) >= 4 and norm_n in norm_fname:
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

