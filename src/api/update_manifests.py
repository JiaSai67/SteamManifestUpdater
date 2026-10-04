import os
import re
import json
import urllib.request
import urllib.error
import time
from datetime import datetime

from managers import config_manager
LUA_DIR = config_manager.DEFAULT_LUA_DIR
from pathlib import Path
LOG_FILE = str(Path(LUA_DIR) / "update_log.txt")

def get_app_info(appid):
    url = f"https://api.steamcmd.net/v1/info/{appid}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data.get('status') == 'success':
                return data.get('data', {}).get(str(appid), {})
            return {"error": "API Error: Status not success"}
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code} ({e.reason})"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)}"}

def process_files(lua_dir=LUA_DIR, log_file=LOG_FILE):
    """
    [已作廢 / Deprecated]
    因 Valve 伺服端更新，未持有授權的遊戲無法在線獲取 Manifest 清單 (401 Unauthorized)。
    自動更新 .lua 內的 Manifest ID 會導致本機缺少實體 .manifest 檔案，從而引發 Steam「無網路連線」錯誤。
    此功能已全面作廢停用，保留函式僅維持相容性。
    """
    print("[update_manifests] 注意：因 Valve 伺服端清單政策調整，Lua 自動線上更新功能已作廢並停止運作。")
    return []

if __name__ == "__main__":
    process_files()
