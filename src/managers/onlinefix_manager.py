import os
import subprocess
import shutil
from pathlib import Path
import json
import sys

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
RAR_PASSWORD = "online-fix.me"

_cache_dir = Path(_config.get("cache_dir", str(config_manager._root_dir / "data" / "cache")))
_cache_dir.mkdir(parents=True, exist_ok=True)

RECORD_FILE = str(_cache_dir / "onlinefix_records.json")

def _load_records():
    if os.path.exists(RECORD_FILE):
        try:
            with open(RECORD_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

GDRIVE_FOLDER_URL = _config.get("gdrive_url", "https://drive.google.com/drive/folders/13TSWK9I5JWj3MDSGeEubSZm37-IwUoGu?usp=sharing")

LOCAL_PATCH_DIR = _cache_dir / "OnlineFix Lua files"
LOCAL_PATCH_DIR.mkdir(parents=True, exist_ok=True)


_cloud_cache = None

def get_patch_sources(target_app_id=None, target_app_name=""):
    global _cloud_cache
    sources = {}
    
    # 1. Scan Local Dir
    if LOCAL_PATCH_DIR.exists():
        for root, dirs, files in os.walk(LOCAL_PATCH_DIR):
            lua_files = [f for f in files if f.endswith('.lua')]
            rar_files = [f for f in files if f.endswith('.rar')]
            
            # Use lua file to determine app_id if available, otherwise try to extract from folder name
            app_id = None
            if lua_files:
                app_id = lua_files[0].replace('.lua', '')
            else:
                import re
                m = re.search(r'\b(\d+)\b', os.path.basename(root))
                if m:
                    app_id = m.group(1)
                
            if app_id:
                sources[app_id] = {
                    "local_lua": bool(lua_files),
                    "local_rar": str(Path(root) / rar_files[0]) if rar_files else None
                }

    # 2. Scan Cloud
    if _cloud_cache is None:
        try:
            import gdown
            res = gdown.download_folder(url=GDRIVE_FOLDER_URL, skip_download=True, quiet=True)
            _cloud_cache = [{'path': f.path, 'id': f.id} for f in res]
        except:
            _cloud_cache = []
            
    cloud_folders = {}
    root_rar_files = [] # Files in the root without a folder
    
    for f in _cloud_cache:
        parts = f['path'].split('\\')
        if len(parts) >= 2:
            folder = parts[0]
            name = parts[-1]
            if folder not in cloud_folders:
                cloud_folders[folder] = {'lua': None, 'rar': None}
            if name.endswith('.lua'):
                cloud_folders[folder]['lua'] = {'name': name.replace('.lua', ''), 'obj': f}
            elif name.endswith('.rar'):
                cloud_folders[folder]['rar'] = f
        elif len(parts) == 1:
            name = parts[0]
            if name.endswith('.rar'):
                root_rar_files.append(f)
                
    for folder, data in cloud_folders.items():
        app_id = None
        import re
        # Try to extract AppID from folder name (e.g. "waterpark 3293260")
        m = re.search(r'\b(\d+)\b', folder)
        if m:
            app_id = m.group(1)
        elif data['lua']:
            app_id = data['lua']['name']
            
        if not app_id:
            continue
            
        if app_id not in sources:
            sources[app_id] = {}
            
        if data['lua']:
            sources[app_id]['cloud_lua'] = True
            sources[app_id]['cloud_lua_obj'] = data['lua']['obj']
            
        if data['rar']:
            sources[app_id]['cloud_rar'] = data['rar']
            
    # Fuzzy match logic for target_app_id
    if target_app_id:
        target_app_id_str = str(target_app_id)
        if target_app_id_str not in sources and target_app_name:
            import re
            # Normalize target_app_name: lowercase, alphanumeric only
            target_norm = re.sub(r'[^a-z0-9]', '', target_app_name.lower())
            if target_norm:
                # Check root rar files
                for f in root_rar_files:
                    f_norm = re.sub(r'[^a-z0-9]', '', f['path'].lower())
                    if target_norm in f_norm:
                        sources[target_app_id_str] = {'cloud_rar': f}
                        break
                
                # Check cloud_folders that didn't have an app_id
                if target_app_id_str not in sources:
                    for folder, data in cloud_folders.items():
                        folder_norm = re.sub(r'[^a-z0-9]', '', folder.lower())
                        if target_norm in folder_norm and data['rar']:
                            sources[target_app_id_str] = {'cloud_rar': data['rar']}
                            break
                            
    return sources

def download_cloud_patch(cloud_obj):
    try:
        import gdown
        out_path = LOCAL_PATCH_DIR / cloud_obj['path']
        out_path.parent.mkdir(parents=True, exist_ok=True)
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
            res = download_cloud_patch(cloud_obj)
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

def _find_steam_game_dir(app_id):
    import winreg, re
    libs = set()
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam')
        path, _ = winreg.QueryValueEx(key, 'SteamPath')
        winreg.CloseKey(key)
        libs.add(os.path.normpath(path))
    except:
        pass
        
    for lib in list(libs):
        vdf_path = os.path.join(lib, 'steamapps', 'libraryfolders.vdf')
        if os.path.exists(vdf_path):
            try:
                content = open(vdf_path, encoding='utf-8', errors='ignore').read()
                matches = re.findall(r'"path"\s+"([^"]+)"', content, re.IGNORECASE)
                for m in matches:
                    # Windows paths in vdf are escaped, e.g. D:\\Games
                    m = m.replace('\\\\', '\\')
                    libs.add(os.path.normpath(m))
            except:
                pass
                
    for lib in libs:
        acf = os.path.join(lib, 'steamapps', f'appmanifest_{app_id}.acf')
        if os.path.exists(acf):
            try:
                content = open(acf, encoding='utf-8', errors='ignore').read()
                m = re.search(r'"installdir"\s+"([^"]+)"', content, re.IGNORECASE)
                if m:
                    return Path(lib) / 'steamapps' / 'common' / m.group(1)
            except:
                pass
    return None

def _save_records(records):
    with open(RECORD_FILE, 'w', encoding='utf-8') as f:
        json.dump(records, f, indent=4, ensure_ascii=False)

def get_rar_file_list(rar_path):
    if not EXTRACTOR:
        return []
        
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        if EXTRACTOR["type"] == "7z":
            output = subprocess.check_output(
                [EXTRACTOR["path"], "l", f"-p{RAR_PASSWORD}", str(rar_path)],
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
            return files
            
        elif EXTRACTOR["type"] == "winrar":
            output = subprocess.check_output(
                [EXTRACTOR["path"], "lb", f"-p{RAR_PASSWORD}", str(rar_path)],
                startupinfo=startupinfo,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            files = [line.strip() for line in output.split('\n') if line.strip() and not line.strip().endswith('\\')]
            return files
            
    except Exception as e:
        print(f"Error reading RAR: {e}")
        return []

def install_fix(app_id, rar_path, game_dir):
    rar_path = Path(rar_path)
    game_dir = Path(game_dir)
    app_id = str(app_id)
    
    if not rar_path.exists() or not game_dir.exists():
        return False, "檔案或資料夾不存在"
        
    if not EXTRACTOR:
        return False, "找不到解壓縮工具！請先安裝 7-Zip 或 WinRAR。"
        
    files_to_extract = get_rar_file_list(rar_path)
    if not files_to_extract:
        return False, "無法讀取壓縮檔內容，可能密碼錯誤或檔案毀損"
        
    backed_up = []
    for rel_path in files_to_extract:
        target_path = game_dir / rel_path
        if target_path.exists():
            bak_path = target_path.with_suffix(target_path.suffix + '.bak')
            if not target_path.name.lower().startswith('onlinefix'):
                try:
                    import shutil
                    shutil.move(str(target_path), str(bak_path))
                    backed_up.append(str(rel_path))
                except Exception as e:
                    pass
                    
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        if EXTRACTOR["type"] == "7z":
            subprocess.check_call(
                [EXTRACTOR["path"], "x", f"-p{RAR_PASSWORD}", "-y", f"-o{game_dir}", str(rar_path)],
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        elif EXTRACTOR["type"] == "winrar":
            # WinRAR x command requires trailing backslash for destination directory
            dest_dir = str(game_dir)
            if not dest_dir.endswith('\\'):
                dest_dir += '\\'
            subprocess.check_call(
                [EXTRACTOR["path"], "x", f"-p{RAR_PASSWORD}", "-y", str(rar_path), dest_dir],
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
        records = _load_records()
        records[app_id] = {
            "game_dir": str(game_dir),
            "installed_files": files_to_extract,
            "backed_up_files": backed_up,
            "timestamp": os.path.getmtime(rar_path)
        }
        _save_records(records)
        return True, "安裝成功"
    except Exception as e:
        return False, f"解壓縮失敗: {e}"

def uninstall_fix(app_id, forced_rar_path=None):
    app_id = str(app_id)
    records = _load_records()
    
    if app_id not in records:
        if forced_rar_path and os.path.exists(forced_rar_path):
            # Forced uninstall: we don't have records, but we have the RAR file to compare.
            game_dir = _find_steam_game_dir(app_id)
            if not game_dir or not game_dir.exists():
                return False, "找不到遊戲目錄，無法執行強制移除"
            
            files_to_remove = get_rar_file_list(forced_rar_path)
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
            return True, "強制移除完成，已清理補丁檔案"
        return False, "此遊戲沒有安裝紀錄，且無可用比對檔案"
        
    record = records[app_id]
    game_dir = Path(record["game_dir"])
    installed = record.get("installed_files", [])
    backed_up = record.get("backed_up_files", [])
    
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
                
    del records[app_id]
    _save_records(records)
        
    return True, "移除成功並已還原原始檔案"

def get_fix_status(app_id):
    app_id = str(app_id)
    records = _load_records()
    
    if app_id not in records:
        game_dir = _find_steam_game_dir(app_id)
        if game_dir and game_dir.exists():
            # Check for generic online-fix signatures without a specific record
            if (game_dir / 'OnlineFix.ini').exists() or (game_dir / 'OnlineFix64.dll').exists():
                if (game_dir / 'OnlineFix64.dll').exists():
                    return "✅ 已安裝 (自行安裝)"
                else:
                    return "⚠️ 防毒破壞"
        return "未安裝"
        
    record = records[app_id]
    game_dir = Path(record["game_dir"])
    installed = record.get("installed_files", [])
    
    if not game_dir.exists():
        return "⚠️ 遊戲目錄遺失"
        
    # Check core online-fix files presence
    core_files = [f for f in installed if 'onlinefix' in f.lower() and f.endswith('.dll')]
    for core_file in core_files:
        if not (game_dir / core_file).exists():
            return "⚠️ 防毒破壞"
            
    return "✅ 已安裝"
