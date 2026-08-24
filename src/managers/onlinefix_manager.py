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

def _load_record(app_id):
    app_id = str(app_id)
    
    # 1. Primary: Load in-situ record directly from the game directory
    game_record_path = _get_game_record_path(app_id)
    if game_record_path and game_record_path.exists():
        try:
            with open(game_record_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
            
    # 2. Secondary: Fallback to local cache directory record
    d = get_app_cache_dir(app_id)
    json_path = d / "patch_record.json"
    if json_path.exists():
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
            
    # 3. Third: Heuristic signature scan (handles cache clears and external/manual installs)
    game_dir = _find_steam_game_dir(app_id)
    if game_dir and game_dir.exists():
        signature_files = ["OnlineFix.ini", "OnlineFix64.dll", "OnlineFix.dll", "SteamOverlay.dll", "OnlineFix.url"]
        found_signatures = [f for f in signature_files if (game_dir / f).exists()]
        bak_files = [f.name for f in game_dir.glob("*.bak")]
        
        if found_signatures or bak_files:
            return {
                "game_dir": str(game_dir),
                "installed_files": found_signatures,
                "backed_up_files": bak_files,
                "is_signature": True
            }
            
    return None

def _save_record(app_id, record, app_name=None):
    app_id = str(app_id)
    # 1. Primary: Save directly inside the game directory
    game_dir_str = record.get("game_dir")
    if game_dir_str and os.path.exists(game_dir_str):
        game_record_path = Path(game_dir_str) / ".onlinefix_record.json"
        try:
            with open(game_record_path, 'w', encoding='utf-8') as f:
                json.dump(record, f, indent=4, ensure_ascii=False)
        except Exception:
            pass
            
    # 2. Secondary: Dual backup in cache directory
    d = get_app_cache_dir(app_id, app_name)
    json_path = d / "patch_record.json"
    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(record, f, indent=4, ensure_ascii=False)
    except Exception:
        pass

def _delete_record(app_id):
    app_id = str(app_id)
    # 1. Delete from game directory
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

GDRIVE_FOLDER_URL = _config.get("gdrive_url", "https://drive.google.com/drive/folders/13TSWK9I5JWj3MDSGeEubSZm37-IwUoGu?usp=sharing")

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

def fetch_cloud_cache():
    global _cloud_cache
    try:
        import gdown
        res = gdown.download_folder(url=GDRIVE_FOLDER_URL, skip_download=True, quiet=True)
        _cloud_cache = [{'path': f.path, 'id': f.id} for f in res]
        try:
            with open(_cloud_cache_file, "w", encoding="utf-8") as f:
                json.dump(_cloud_cache, f, ensure_ascii=False, indent=2)
        except:
            pass
    except:
        if _cloud_cache is None:
            _cloud_cache = []
    return _cloud_cache

def get_patch_sources(target_apps=None, target_app_id=None, target_app_name=None, allow_network=False):
    global _cloud_cache
    if target_apps is None:
        target_apps = {}
    if target_app_id and target_app_name:
        target_apps[str(target_app_id)] = target_app_name
        
    sources = {}
    
    # 1. Scan Local Dir
    if LOCAL_PATCH_DIR.exists():
        for root, dirs, files in os.walk(LOCAL_PATCH_DIR):
            lua_files = [f for f in files if f.endswith('.lua')]
            rar_files = [f for f in files if f.endswith('.rar') or f.endswith('.zip')]
            
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
    if _cloud_cache is None and allow_network:
        fetch_cloud_cache()
            
    cloud_folders = {}
    root_rar_files = [] # Files in the root without a folder
    
    if _cloud_cache:
        for f in _cloud_cache:
            parts = f['path'].split('\\')
            if len(parts) >= 2:
                folder = parts[0]
                name = parts[-1]
                if folder not in cloud_folders:
                    cloud_folders[folder] = {'lua': None, 'rar': None}
                if name.endswith('.lua'):
                    cloud_folders[folder]['lua'] = {'name': name.replace('.lua', ''), 'obj': f}
                elif name.endswith('.rar') or name.endswith('.zip'):
                    cloud_folders[folder]['rar'] = f
            elif len(parts) == 1:
                name = parts[0]
                if name.endswith('.rar') or name.endswith('.zip'):
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
                        for f in root_rar_files:
                            f_norm = re.sub(r'[^a-z0-9]', '', f['path'].lower())
                            if target_norm in f_norm:
                                sources[app_id]['cloud_rar'] = f
                                break
                        
                        if 'cloud_rar' not in sources[app_id]:
                            for folder, data in cloud_folders.items():
                                folder_norm = re.sub(r'[^a-z0-9]', '', folder.lower())
                                if target_norm in folder_norm and data['rar']:
                                    sources[app_id]['cloud_rar'] = data['rar']
                                    break
                            
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
                for pwd in ARCHIVE_PASSWORDS:
                    try:
                        # Test password by reading 1 byte of the first file
                        for f in zf.infolist():
                            if not f.is_dir():
                                with zf.open(f, pwd=pwd.encode('utf-8')) as test_f:
                                    test_f.read(1)
                                break
                        # If we get here, password is correct
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

def install_fix(app_id, rar_path, game_dir):
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
        if target_path.exists():
            bak_path = target_path.with_suffix(target_path.suffix + '.bak')
            if not bak_path.exists():
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
            with zipfile.ZipFile(str(rar_path)) as zf:
                zf.extractall(path=str(game_dir), pwd=working_pwd.encode('utf-8'))
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
            "timestamp": os.path.getmtime(rar_path)
        })
        _save_record(app_id, record)
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
    
    # If it was detected via heuristic signature:
    if record.get("is_signature"):
        for sig in ["OnlineFix.ini", "OnlineFix64.dll", "OnlineFix.dll", "SteamOverlay.dll", "OnlineFix.url", "winmm.dll", "version.dll"]:
            target = game_dir / sig
            if target.exists():
                try:
                    target.unlink()
                except:
                    pass
        # Restore any .bak files found in game root
        for bak in game_dir.glob("*.bak"):
            orig = bak.with_suffix('')
            if not orig.exists():
                try:
                    shutil.move(str(bak), str(orig))
                except:
                    pass
        _delete_record(app_id)
        return True, "移除成功並已還原原始檔案"
        
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
                
    _delete_record(app_id)
        
    return True, "移除成功並已還原原始檔案"

def get_fix_status(app_id):
    app_id = str(app_id)
    record = _load_record(app_id)
    
    if not record:
        return "未安裝"
        
    game_dir = Path(record["game_dir"])
    if not game_dir.exists():
        return "⚠️ 遊戲目錄遺失"
        
    if record.get("is_signature"):
        return "✅ 已安裝"
        
    installed = record.get("installed_files", [])
    for f in installed:
        if not (game_dir / f).exists():
            return "⚠️ 部分補丁檔案遺失 (可能被防毒刪除)"
            
    return "✅ 已安裝"
