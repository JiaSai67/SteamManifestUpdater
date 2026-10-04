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
_cache_dir.mkdir(parents=True, exist_ok=True)

def get_app_cache_dir(app_id, app_name=None):
    app_id = str(app_id)
    if LOCAL_PATCH_DIR.exists():
        for d in LOCAL_PATCH_DIR.iterdir():
            if d.is_dir() and d.name.endswith(f" {app_id}"):
                return d
    if app_name:
        import re
        safe_name = re.sub(r'[\\\\/*?:"<>|]', "", app_name).strip()
        new_dir = LOCAL_PATCH_DIR / f"{safe_name} {app_id}"
        new_dir.mkdir(parents=True, exist_ok=True)
        return new_dir
    fallback = LOCAL_PATCH_DIR / f"UnknownApp {app_id}"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback

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
                    if "game_dir" not in data:
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
                if isinstance(data, dict) and "game_dir" not in data:
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
_cloud_cache = None
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
    global _cloud_cache
    _config["cloud_drives"] = drives
    if drives:
        _config["gdrive_url"] = drives[0]["url"]
    _cloud_cache = None
    if _cloud_cache_file.exists():
        try:
            _cloud_cache_file.unlink()
        except:
            pass

def fetch_cloud_cache(force=False):
    global _cloud_cache
    if not force and _cloud_cache is not None and len(_cloud_cache) > 0:
        return _cloud_cache
        
    drives = get_cloud_drives()
    all_items = []
    
    try:
        import gdown
        for idx, drive in enumerate(drives):
            url = drive.get("url", "").strip()
            name = drive.get("name", f"網盤 {idx + 1}").strip()
            priority = drive.get("priority", idx + 1)
            if not url:
                continue
            try:
                res = gdown.download_folder(url=url, skip_download=True, quiet=True)
                for f in res:
                    all_items.append({
                        'path': f.path,
                        'id': f.id,
                        'drive_name': name,
                        'drive_priority': priority,
                        'drive_url': url
                    })
            except Exception as e:
                print(f"Error fetching drive {name} ({url}): {e}")
                
        _cloud_cache = all_items
        try:
            with open(_cloud_cache_file, "w", encoding="utf-8") as f:
                json.dump(_cloud_cache, f, ensure_ascii=False, indent=2)
        except:
            pass
    except Exception as e:
        print(f"fetch_cloud_cache error: {e}")
        if _cloud_cache is None:
            _cloud_cache = []
    return _cloud_cache

def sync_cloud_cache():
    return fetch_cloud_cache(force=True)

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
        d = get_app_cache_dir(app_id, app_name)
        file_name = Path(cloud_obj['path']).name
        out_path = d / file_name
        res = gdown.download(id=cloud_obj['id'], output=str(out_path), quiet=True)
        return res
    except Exception as e:
        print(f"Error downloading: {e}")
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
    except Exception as e:
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
            _delete_record(app_id)
            return True, "強制移除完成，已清理補丁檔案"
        return False, "此遊戲沒有安裝紀錄，且無可用比對檔案"
        
    game_dir = Path(record["game_dir"])
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
                
        # 4. Restore any .bak files found in game root
        for bak in game_dir.glob("*.bak"):
            orig = bak.with_suffix('')
            if not orig.exists():
                try:
                    shutil.move(str(bak), str(orig))
                except:
                    pass
        _delete_record(app_id, game_dir)
        return True, "因先前自行安裝，現在將移除所有相關檔案，若遊戲無法正常啟動，請使用「驗證檔案完整性」修復遊戲"
        
    for rel_path in installed:
        target = game_dir / rel_path
        if target.exists():
            try:
                target.unlink()
            except:
                pass
                
    for rel_path in backed_up:
        target = game_dir / rel_path
        bak_path = target.with_suffix(target.suffix + '.bak')
        if bak_path.exists():
            try:
                shutil.move(str(bak_path), str(target))
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
    
    for f in check_list:
        if not (game_dir / f).exists():
            return "⚠️ 部分補丁檔案遺失 (可能被防毒刪除)"
            
    return "✅ 已安裝"

def get_fix_record(app_id):
    return _load_record(str(app_id))
