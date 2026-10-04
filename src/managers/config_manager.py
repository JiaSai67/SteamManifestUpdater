import json
import os
from pathlib import Path

import sys
# Get root directory of the project
if getattr(sys, 'frozen', False) or "__compiled__" in globals():
    # If running as executable, the root is the folder containing the exe
    _root_dir = Path(sys.argv[0]).resolve().parent
else:
    # If running from source, it's the parent of src/managers
    _root_dir = Path(__file__).resolve().parent.parent.parent
_storage_dir = _root_dir / "data"
_storage_dir.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = str(_storage_dir / "config.json")
def _get_default_lua_dir():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        path, _ = winreg.QueryValueEx(key, "SteamPath")
        winreg.CloseKey(key)
        steam_dir = Path(path).resolve()
        if steam_dir.exists():
            return str(steam_dir / "config" / "lua")
    except Exception:
        pass
    return r"C:\Program Files (x86)\Steam\config\lua"

def _get_default_cloud_save_dir():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        path, _ = winreg.QueryValueEx(key, "SteamPath")
        winreg.CloseKey(key)
        steam_dir = Path(path).resolve()
        if steam_dir.exists():
            return str(steam_dir / "config" / "cloud_saves")
    except Exception:
        pass
    return r"C:\Program Files (x86)\Steam\config\cloud_saves"

DEFAULT_LUA_DIR = _get_default_lua_dir()
DEFAULT_CLOUD_SAVE_DIR = _get_default_cloud_save_dir()

_config = None

def get_config():
    global _config
    if _config is None:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    _config = json.load(f)
            except:
                pass
        if _config is None:
            _config = {}
            
    # Set defaults
    _config.setdefault("lua_dir", DEFAULT_LUA_DIR)
    
    # Storage settings
    default_cache_dir = str(_storage_dir / "cache")
    default_credentials_dir = str(_storage_dir / "credentials")
    
    # 🌟 跨設備與不同使用者路徑自癒機制 (Path Self-Healing)
    curr_cache = _config.get("cache_dir")
    if not curr_cache or not Path(curr_cache).parent.exists():
        _config["cache_dir"] = default_cache_dir
        
    curr_creds = _config.get("credentials_dir")
    if not curr_creds or not Path(curr_creds).parent.exists():
        _config["credentials_dir"] = default_credentials_dir

    try:
        Path(_config["cache_dir"]).mkdir(parents=True, exist_ok=True)
        Path(_config["credentials_dir"]).mkdir(parents=True, exist_ok=True)
    except Exception:
        _config["cache_dir"] = default_cache_dir
        _config["credentials_dir"] = default_credentials_dir
        Path(default_cache_dir).mkdir(parents=True, exist_ok=True)
        Path(default_credentials_dir).mkdir(parents=True, exist_ok=True)

    # 🌟 跨設備 Steam 與 Lua 目錄動態自動校準
    curr_sp = _config.get("steam_path")
    if not curr_sp or not Path(curr_sp).exists() or not (Path(curr_sp) / "steam.exe").exists():
        try:
            from managers import steam_manager
            found_sp = steam_manager.find_steam_path()
            if found_sp and found_sp.exists():
                _config["steam_path"] = str(found_sp)
                _config["lua_dir"] = str(found_sp / "config" / "lua")
        except Exception:
            pass
    
    # Cloud Save Redirect settings (已下線停用，預設關閉)
    _config.setdefault("cloud_redirect", False)
    _config.setdefault("cloud_redirect_path", "")
    _config.setdefault("cloud_redirect_mode", "local")
    
    # Domain settings
    _config.setdefault("onlinefix_domain", "https://online-fix.me")
    _config.setdefault("zeigames_domain", "https://zeigames.com/")
    _config.setdefault("luatools_domain", "https://lua.tools")
    _config.setdefault("hubcap_domain", "https://hubcapmanifest.com")
    _config.setdefault("hubcap_api_key", "")
    _config.setdefault("assiw_domain", "https://steam.assiw.xyz")
    
    # Cloud Drives settings
    _config.setdefault("gdrive_url", "https://drive.google.com/drive/folders/13TSWK9I5JWj3MDSGeEubSZm37-IwUoGu?usp=sharing")
    _config.setdefault("cloud_drives", [])
    
    # UI settings
    _config.setdefault("ui_font_size", "small")
    
    return _config

def save_config(config=None):
    global _config
    if config is not None:
        _config = config
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(_config, f, indent=4, ensure_ascii=False)
    except:
        pass
