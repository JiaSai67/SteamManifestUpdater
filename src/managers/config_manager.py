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

DEFAULT_LUA_DIR = _get_default_lua_dir()

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
    _config.setdefault("cache_dir", default_cache_dir)
    _config.setdefault("credentials_dir", default_credentials_dir)
    
    # Domain settings
    _config.setdefault("gdrive_url", "https://drive.google.com/drive/folders/13TSWK9I5JWj3MDSGeEubSZm37-IwUoGu?usp=sharing")
    _config.setdefault("onlinefix_domain", "https://online-fix.me")
    _config.setdefault("luatools_domain", "https://lua.tools")
    
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
