import os
import sys
import time
import json
import re
import signal
import threading
from pathlib import Path

# Add src to sys.path
_src_dir = Path(__file__).resolve().parent
_root_dir = _src_dir.parent
sys.path.insert(0, str(_src_dir))

from managers import config_manager
from managers import onlinefix_manager
from api import update_manifests
from utils.toast import send_notification

DATA_DIR = _root_dir / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
PID_FILE = DATA_DIR / "daemon.pid"
LOG_FILE = DATA_DIR / "daemon.log"

_running = True
_known_buildids = {}
_processed_events = {}

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except:
        pass

def signal_handler(signum, frame):
    global _running
    log(f"Received termination signal ({signum}). Exiting daemon...")
    _running = False

def get_steam_libraries():
    """
    Find all Steam library folders configured on the system.
    """
    import winreg
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
                    if os.path.exists(m):
                        libs.add(os.path.normpath(m))
            except Exception:
                pass
    unique_libs = {}
    for p in libs:
        if os.path.exists(p):
            norm_key = os.path.normcase(os.path.normpath(p))
            if norm_key not in unique_libs:
                unique_libs[norm_key] = Path(p)
    return list(unique_libs.values())

def parse_acf(acf_path):
    """
    Parse a Steam appmanifest_<appid>.acf file.
    """
    try:
        with open(acf_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        appid_m = re.search(r'"appid"\s+"(\d+)"', content, re.IGNORECASE)
        name_m = re.search(r'"name"\s+"([^"]+)"', content, re.IGNORECASE)
        dir_m = re.search(r'"installdir"\s+"([^"]+)"', content, re.IGNORECASE)
        build_m = re.search(r'"buildid"\s+"(\d+)"', content, re.IGNORECASE)
        state_m = re.search(r'"StateFlags"\s+"(\d+)"', content, re.IGNORECASE)
        
        return {
            'appid': appid_m.group(1) if appid_m else None,
            'name': name_m.group(1) if name_m else None,
            'installdir': dir_m.group(1) if dir_m else None,
            'buildid': build_m.group(1) if build_m else None,
            'state_flags': int(state_m.group(1)) if state_m else None
        }
    except Exception as e:
        log(f"Error parsing {acf_path}: {e}")
        return None

def handle_game_update(app_id, game_name):
    """
    Handle detected update for a game: check and apply cloud patches and Lua manifests.
    """
    config = config_manager.get_config()
    auto_patch = config.get("daemon_auto_patch", True)
    notify_enabled = config.get("daemon_notify", True)
    
    if not auto_patch:
        log(f"Auto-patch is disabled in config. Skipping {game_name} ({app_id}).")
        return
        
    log(f"Checking updates for {game_name} (AppID: {app_id})...")
    
    try:
        # 1. Update Lua manifests if present
        try:
            update_manifests.process_files()
        except Exception as e:
            log(f"Manifest update error: {e}")
            
        # 2. Check for Cloud Google Drive / OnlineFix patches
        sources = onlinefix_manager.get_patch_sources(
            target_apps={str(app_id): game_name},
            allow_network=True,
            force_refresh=False
        )
        
        app_source = sources.get(str(app_id), {})
        cloud_rar = app_source.get("cloud_rar")
        
        if cloud_rar:
            drive_name = app_source.get("drive_name", "Google Drive 網盤")
            log(f"Found cloud patch in {drive_name} for {game_name}. Downloading...")
            
            download_path = onlinefix_manager.download_cloud_patch(app_id, game_name, cloud_rar)
            if download_path and Path(download_path).exists():
                log(f"Downloaded {download_path}. Installing...")
                ok, msg = onlinefix_manager.install_patch(
                    app_id=app_id,
                    archive_path=download_path,
                    source_drive=drive_name,
                    app_name=game_name
                )
                if ok:
                    log(f"Successfully auto-patched {game_name} ({app_id})!")
                    if notify_enabled:
                        send_notification(
                            "SteamManifestUpdater 守護程式",
                            f"已自動為《{game_name}》套用最新補丁！({drive_name})"
                        )
                else:
                    log(f"Install failed for {game_name}: {msg}")
        else:
            log(f"No cloud patch required for {game_name} ({app_id}).")
    except Exception as e:
        log(f"Error handling update for {game_name}: {e}")

def watch_library_ctypes(steamapps_dir):
    """
    Ultra-low-overhead directory watcher using Windows native ReadDirectoryChangesW.
    Consumes 0% CPU while waiting for OS kernel events.
    """
    import ctypes
    from ctypes import wintypes
    
    FILE_LIST_DIRECTORY = 0x0001
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    FILE_SHARE_DELETE = 0x00000004
    OPEN_EXISTING = 3
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    
    FILE_NOTIFY_CHANGE_FILE_NAME = 0x00000001
    FILE_NOTIFY_CHANGE_LAST_WRITE = 0x00000010
    
    h_dir = ctypes.windll.kernel32.CreateFileW(
        str(steamapps_dir),
        FILE_LIST_DIRECTORY,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        None,
        OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS,
        None
    )
    
    if h_dir == -1 or h_dir == 0:
        log(f"Failed to open handle for {steamapps_dir}")
        return

    buffer = ctypes.create_string_buffer(8192)
    bytes_returned = wintypes.DWORD()
    
    log(f"Watching {steamapps_dir} (Kernel Event Driven, 0% CPU)...")
    
    while _running:
        success = ctypes.windll.kernel32.ReadDirectoryChangesW(
            h_dir,
            buffer,
            len(buffer),
            False, # watch immediate directory only (steamapps/)
            FILE_NOTIFY_CHANGE_FILE_NAME | FILE_NOTIFY_CHANGE_LAST_WRITE,
            ctypes.byref(bytes_returned),
            None,
            None
        )
        
        if not success or not _running:
            break
            
        # Parse returned records
        offset = 0
        while offset < bytes_returned.value:
            next_offset = int.from_bytes(buffer[offset:offset+4], 'little')
            action = int.from_bytes(buffer[offset+4:offset+8], 'little')
            name_len = int.from_bytes(buffer[offset+8:offset+12], 'little')
            raw_name = buffer[offset+12:offset+12+name_len]
            filename = raw_name.decode('utf-16le', errors='ignore')
            
            if filename.startswith("appmanifest_") and filename.endswith(".acf"):
                acf_path = steamapps_dir / filename
                m = re.search(r'appmanifest_(\d+)\.acf', filename)
                if m:
                    app_id = m.group(1)
                    # Debounce: Steam writes multiple times during install/update
                    now = time.time()
                    last_time = _processed_events.get(app_id, 0)
                    if now - last_time > 5.0:
                        _processed_events[app_id] = now
                        threading.Thread(target=_on_manifest_changed, args=(acf_path, app_id), daemon=True).start()
                        
            if next_offset == 0:
                break
            offset += next_offset

    ctypes.windll.kernel32.CloseHandle(h_dir)

def _on_manifest_changed(acf_path, app_id):
    # Wait for Steam to finish writing the file
    time.sleep(2.5)
    if not acf_path.exists():
        return
        
    info = parse_acf(acf_path)
    if not info or not info.get('name'):
        return
        
    build_id = info.get('buildid')
    state = info.get('state_flags')
    name = info.get('name')
    
    # StateFlags 4 = StateFullyInstalled
    prev_build = _known_buildids.get(app_id)
    if prev_build != build_id:
        _known_buildids[app_id] = build_id
        log(f"Detected game update / installation: {name} ({app_id}) -> BuildID: {build_id}")
        handle_game_update(app_id, name)

def periodic_heartbeat():
    """
    [已暫停 / Deprecated]
    因 Valve 伺服端已封鎖未授權 Manifest 線上提取，定期更新 Lua Manifest 功能已全面停用。
    """
    log("Periodic Lua manifest auto-update is paused/deprecated.")
    return

def main():
    global _running
    
    # Write PID file
    my_pid = os.getpid()
    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(my_pid))
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    log(f"==================================================")
    log(f"SteamManifestUpdater Background Daemon Started (PID: {my_pid})")
    log(f"==================================================")
    
    # Initial scan of libraries
    libs = get_steam_libraries()
    log(f"Found {len(libs)} Steam library folder(s).")
    
    watch_threads = []
    for lib in libs:
        steamapps = lib / "steamapps"
        if steamapps.exists():
            t = threading.Thread(target=watch_library_ctypes, args=(steamapps,), daemon=True)
            t.start()
            watch_threads.append(t)
            
    # Start heartbeat thread
    hb_thread = threading.Thread(target=periodic_heartbeat, daemon=True)
    hb_thread.start()
    
    # Send startup notification if enabled
    config = config_manager.get_config()
    if config.get("daemon_notify", True):
        send_notification("SteamManifestUpdater", "背景守護程式已啟動（0% CPU 超低負載模式）")
        
    try:
        while _running:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        log("Daemon shutting down.")
        if PID_FILE.exists():
            try:
                PID_FILE.unlink()
            except:
                pass

if __name__ == "__main__":
    main()
