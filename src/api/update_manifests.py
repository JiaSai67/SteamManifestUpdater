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
    if not os.path.exists(lua_dir):
        print(f"Directory {lua_dir} does not exist.")
        return

    log_entries = []
    
    # Process each lua file
    for filename in os.listdir(lua_dir):
        if not filename.endswith(".lua"):
            continue
            
        filepath = os.path.join(lua_dir, filename)
        appid = filename.replace(".lua", "")
        
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Match setManifestid(depot_id, "manifest_id", size) or setManifestid(depot_id, "manifest_id")
        pattern = re.compile(r'setManifestid\(\s*(\d+)\s*,\s*"(\d+)"(?:,\s*(\d+))?\s*\)')
        matches = pattern.findall(content)
        
        if not matches:
            continue
            
        print(f"Processing app {appid} ({filename})...")
        app_info = get_app_info(appid)
        if not app_info or "error" in app_info:
            err_msg = app_info.get("error", "Unknown error") if app_info else "Failed to get info"
            print(f"Failed to get info for app {appid} ({err_msg}). Skipping.")
            log_entries.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{appid}] Failed: {err_msg}")
            continue
            
        depots = app_info.get("depots", {})
        
        updated_content = content
        file_modified = False
        
        for match in matches:
            depot_id, old_manifest, old_size = match
            
            depot_info = depots.get(str(depot_id))
            if not depot_info:
                print(f"  Depot {depot_id} not found in API response for app {appid}.")
                continue
                
            manifests = depot_info.get("manifests", {})
            public_manifest = manifests.get("public")
            if not public_manifest:
                print(f"  No public manifest for depot {depot_id} in app {appid}.")
                continue
                
            new_manifest = public_manifest.get("gid")
            new_size = public_manifest.get("size")
            
            if new_manifest and (str(new_manifest) != str(old_manifest) or (old_size and new_size and str(new_size) != str(old_size))):
                if old_size:
                    old_str = f'setManifestid({depot_id}, "{old_manifest}", {old_size})'
                    new_str = f'setManifestid({depot_id}, "{new_manifest}", {new_size})'
                else:
                    old_str = f'setManifestid({depot_id}, "{old_manifest}")'
                    new_str = f'setManifestid({depot_id}, "{new_manifest}")'
                
                updated_content = updated_content.replace(old_str, new_str)
                file_modified = True
                
                log_msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{appid}] Depot {depot_id}: Manifest {old_manifest} -> {new_manifest}" + (f", Size {old_size} -> {new_size}" if old_size else "")
                print(f"  {log_msg}")
                log_entries.append(log_msg)
            else:
                print(f"  Depot {depot_id}: Manifest is up to date ({old_manifest}).")
                
        if file_modified:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(updated_content)
                
        time.sleep(1) # respect API rate limits
        
    if log_entries:
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write("\n".join(log_entries) + "\n")
            print(f"\nUpdate log appended to {log_file}")
        except Exception as e:
            print(f"Failed to write log: {e}")
            
        return log_entries
    else:
        print("Done! No updates needed.")
        return []

if __name__ == "__main__":
    process_files()
