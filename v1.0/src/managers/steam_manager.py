import os
import sys
import time
import shutil
import subprocess
import re
import stat
from pathlib import Path
import winreg

def get_steam_pid():
    """
    檢查 steam.exe 是否在運行中，若有則回傳其 Process ID (PID)，否則回傳 None。
    """
    try:
        output = subprocess.check_output(
            ['tasklist', '/fi', 'imagename eq steam.exe', '/fo', 'csv', '/nh'],
            creationflags=subprocess.CREATE_NO_WINDOW,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        for line in output.strip().split('\n'):
            parts = line.split(',')
            if len(parts) >= 2 and 'steam.exe' in parts[0].lower():
                pid_str = parts[1].replace('"', '').strip()
                if pid_str.isdigit():
                    return int(pid_str)
    except Exception:
        pass
    return None

def is_steam_running():
    """
    判斷 Steam 是否正在運行中。
    """
    return get_steam_pid() is not None

def kill_steam(timeout=6):
    """
    強制終止 Steam 及其網頁小幫手行程，並輪詢確認完全退出。
    """
    if not is_steam_running():
        return True
        
    try:
        subprocess.call(
            ['taskkill', '/F', '/IM', 'steam.exe'],
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        subprocess.call(
            ['taskkill', '/F', '/IM', 'steamwebhelper.exe'],
            creationflags=subprocess.CREATE_NO_WINDOW
        )
    except Exception:
        pass
        
    start_time = time.time()
    while time.time() - start_time < timeout:
        if not is_steam_running():
            time.sleep(0.5)
            return True
        time.sleep(0.3)
    return not is_steam_running()

def launch_steam(steam_path):
    """
    啟動 steam.exe。
    """
    steam_exe = Path(steam_path) / "steam.exe"
    if not steam_exe.exists():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                reg_path, _ = winreg.QueryValueEx(key, "SteamExe")
                if os.path.exists(reg_path):
                    steam_exe = Path(reg_path)
        except Exception:
            pass
            
    if not steam_exe.exists():
        return False
        
    try:
        subprocess.Popen([str(steam_exe)], shell=False)
        return True
    except Exception as e:
        print(f"Error launching Steam: {e}")
        return False

def restart_steam(steam_path, timeout=10):
    """
    安全重啟 Steam 並精準驗證新行程是否成功運行。
    回傳: (成功與否: bool, 說明訊息: str, 新 PID: int or None)
    """
    was_running = is_steam_running()
    if was_running:
        kill_ok = kill_steam(timeout=6)
        if not kill_ok:
            return False, "無法終止舊有的 Steam 行程，請手動關閉後重試", None
            
    # 啟動 Steam
    launched = launch_steam(steam_path)
    if not launched:
        return False, "找不到 steam.exe 或無法啟動 Steam", None
        
    # 精準輪詢偵測新 Steam 行程 PID
    start_time = time.time()
    while time.time() - start_time < timeout:
        new_pid = get_steam_pid()
        if new_pid is not None:
            time.sleep(1.0) # 等待模組與 Hook 初始加載完成
            return True, f"Steam 重啟成功 (新 PID: {new_pid})", new_pid
        time.sleep(0.5)
        
    return False, "Steam 啟動超時，請手動確認 Steam 是否正常開啟", None

def install_opensteamtools(steam_path, opensteam_src_dir=None):
    """
    防呆流程：安裝 OpenSteamTools DLLs 並自動重啟 Steam 確保 Hook 立即生效。
    """
    steam_path = Path(steam_path)
    if not steam_path.exists():
        return False, "Steam 路徑不存在"
        
    if not opensteam_src_dir:
        from managers import config_manager
        opensteam_src_dir = config_manager._root_dir / "opensteamtools"
        
    opensteam_src_dir = Path(opensteam_src_dir)
    dlls = ["OpenSteamTool.dll", "dwmapi.dll", "xinput1_4.dll"]
    
    # 1. 先關閉 Steam，避免 DLL 檔案被鎖定 (PermissionError)
    if is_steam_running():
        kill_steam(timeout=6)
        
    # 2. 部署 DLL 檔案
    try:
        for dll in dlls:
            src = opensteam_src_dir / dll
            dst = steam_path / dll
            if src.exists():
                shutil.copy2(src, dst)
            else:
                return False, f"安裝檔案遺失: {src}"
                
        lua_dir = steam_path / "config" / "lua"
        lua_dir.mkdir(parents=True, exist_ok=True)
        
        # 部署 manifest.lua (動態 MRC 取碼鏈)
        manifest_lua_src = opensteam_src_dir / "manifest.lua"
        if manifest_lua_src.exists():
            shutil.copy2(manifest_lua_src, lua_dir / "manifest.lua")
            
        # 部署 opensteamtool.toml (核心組態備援)
        toml_src = opensteam_src_dir / "opensteamtool.toml"
        if toml_src.exists():
            shutil.copy2(toml_src, steam_path / "opensteamtool.toml")
    except Exception as e:
        return False, f"複製檔案失敗: {e}"
        
    # 3. 自動重啟 Steam 並驗證
    re_ok, re_msg, pid = restart_steam(steam_path)
    if re_ok:
        return True, f"OpenSteamTools 安裝完成，且已自動為您重啟 Steam！"
    else:
        return True, f"OpenSteamTools 安裝完成！(Steam 啟動提示: {re_msg}，請確認 Steam 是否開啟)"

def ensure_manifest_lua(steam_path, opensteam_src_dir=None):
    """
    確保 Steam/config/lua/manifest.lua 與 opensteamtool.toml 存在且為最新。
    OpenSteamTools 具備目錄熱重載，無需重啟 Steam 即可生效。
    """
    if not steam_path:
        return False
    steam_path = Path(steam_path)
    if not steam_path.exists():
        return False
        
    if not opensteam_src_dir:
        from managers import config_manager
        opensteam_src_dir = config_manager._root_dir / "opensteamtools"
    opensteam_src_dir = Path(opensteam_src_dir)
    
    try:
        lua_dir = steam_path / "config" / "lua"
        lua_dir.mkdir(parents=True, exist_ok=True)
        manifest_src = opensteam_src_dir / "manifest.lua"
        manifest_dst = lua_dir / "manifest.lua"
        if manifest_src.exists():
            shutil.copy2(manifest_src, manifest_dst)
            
        toml_src = opensteam_src_dir / "opensteamtool.toml"
        toml_dst = steam_path / "opensteamtool.toml"
        if toml_src.exists() and not toml_dst.exists():
            shutil.copy2(toml_src, toml_dst)
        return True
    except Exception as e:
        print(f"[steam_manager] ensure_manifest_lua error: {e}")
        return False

def uninstall_opensteamtools(steam_path):
    """
    防呆流程：移除 OpenSteamTools DLLs 並自動重啟 Steam 還原純淨環境。
    """
    steam_path = Path(steam_path)
    if not steam_path.exists():
        return False, "Steam 路徑不存在"
        
    # 1. 關閉 Steam 釋放 DLL 檔案鎖定
    if is_steam_running():
        kill_steam(timeout=6)
        
    dlls = ["OpenSteamTool.dll", "dwmapi.dll", "xinput1_4.dll"]
    try:
        for dll in dlls:
            dst = steam_path / dll
            if dst.exists():
                dst.unlink()
                
        # 移除 opensteamtool.toml
        toml_dst = steam_path / "opensteamtool.toml"
        if toml_dst.exists():
            toml_dst.unlink()
    except Exception as e:
        return False, f"刪除檔案失敗: {e}"
        
    # 2. 重啟 Steam
    re_ok, re_msg, pid = restart_steam(steam_path)
    if re_ok:
        return True, f"OpenSteamTools 已成功移除，且已自動重啟 Steam！"
    else:
        return True, f"OpenSteamTools 已成功移除！(請手動啟動 Steam)"

# ==============================================================================
# Steam Manifest & 版本鎖定防護核心模組 (應對 Valve 2026-09 CDN 401 封鎖)
# ==============================================================================

def get_steam_libraries(steam_path=None):
    """
    動態檢索當前電腦上所有的 Steam 遊戲庫目錄 (包含預設與額外磁碟分割區)。
    回傳: List[Path]
    """
    libs = []
    if steam_path:
        p = Path(steam_path).resolve()
        if p.exists() and p not in libs:
            libs.append(p)
            
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        path, _ = winreg.QueryValueEx(key, "SteamPath")
        winreg.CloseKey(key)
        reg_p = Path(path).resolve()
        if reg_p.exists() and reg_p not in libs:
            libs.append(reg_p)
    except Exception:
        pass
        
    for lib in list(libs):
        vdf = lib / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            try:
                content = vdf.read_text(encoding="utf-8", errors="ignore")
                matches = re.findall(r'"path"\s+"([^"]+)"', content)
                for m in matches:
                    p = Path(m.replace('\\\\', '\\')).resolve()
                    if p.exists() and p not in libs:
                        libs.append(p)
            except Exception:
                pass
    return libs

def find_appmanifest(app_id, steam_path=None):
    """
    跨所有 Steam 遊戲庫目錄搜尋指定 AppID 的 appmanifest_<appid>.acf 檔案路徑。
    回傳: Path 或 None
    """
    libs = get_steam_libraries(steam_path)
    for lib in libs:
        acf = lib / "steamapps" / f"appmanifest_{app_id}.acf"
        if acf.exists():
            return acf
    return None

def get_game_manifest_lock_info(app_id, steam_path=None):
    """
    檢查指定遊戲的 Manifest 與 ACF 鎖定狀態。
    回傳: dict
    """
    app_id_str = str(app_id)
    acf = find_appmanifest(app_id_str, steam_path)
    
    from managers import config_manager
    lua_dir = Path(config_manager.get_config().get("lua_dir", config_manager.DEFAULT_LUA_DIR))
    lua_file = lua_dir / f"{app_id_str}.lua"
    has_lua = lua_file.exists()
    is_lua_ro = False
    if has_lua:
        st = os.stat(lua_file)
        is_lua_ro = bool(st.st_mode & stat.S_IREAD) and not bool(st.st_mode & stat.S_IWRITE)
        
    if not acf:
        return {
            "has_acf": False,
            "acf_path": None,
            "auto_update_behavior": None,
            "is_readonly": False,
            "has_lua": has_lua,
            "is_lua_readonly": is_lua_ro,
            "is_locked": is_lua_ro,
            "status_text": "未鎖定 (無 ACF 快取)" if not is_lua_ro else "Lua 唯讀鎖定中 🔒"
        }
        
    st = os.stat(acf)
    is_ro = bool(st.st_mode & stat.S_IREAD) and not bool(st.st_mode & stat.S_IWRITE)
    content = acf.read_text(encoding="utf-8", errors="ignore")
    
    auto_update = None
    m = re.search(r'"AutoUpdateBehavior"\s+"(\d+)"', content)
    if m:
        auto_update = int(m.group(1))
        
    is_locked = (auto_update == 1) or is_ro
    if is_locked:
        status_text = "已鎖定 🔒 (已關閉背景更新，防 401 封鎖)"
        if is_ro:
            status_text += " [唯讀保護]"
    else:
        status_text = "未鎖定 ⚠️ (自動更新開啟中，可能觸發 401 封鎖)"
        
    return {
        "has_acf": True,
        "acf_path": acf,
        "auto_update_behavior": auto_update,
        "is_readonly": is_ro,
        "has_lua": has_lua,
        "is_lua_readonly": is_lua_ro,
        "is_locked": is_locked,
        "status_text": status_text
    }

def lock_game_version(app_id, steam_path=None, set_readonly=False, game_name=None):
    """
    鎖定遊戲版本防封鎖：
    1. 將 appmanifest_<appid>.acf 中的 AutoUpdateBehavior 設為 1 (僅在啟動時更新，阻止背景向 CDN 查詢 Manifest)
    2. 將 ScheduledAutoUpdate 設為 0
    3. 絕不將 ACF 設為作業系統唯讀屬性！(ACF 唯讀會導致 Steam 無法寫入下載進度，引發致命「磁碟寫入錯誤」)
       若 ACF 原先存在唯讀屬性，主動予以解除為可讀寫。
    4. 將 <appid>.lua 設為唯讀保護 (保護 Lua 不被清理，且完全不影響 Steam 磁碟寫入)
    回傳: (success: bool, message: str)
    """
    app_id_str = str(app_id)
    acf = find_appmanifest(app_id_str, steam_path)
    
    # 若尚無 ACF 檔案，建立乾淨的鎖定範本
    created_new = False
    if not acf:
        libs = get_steam_libraries(steam_path)
        if not libs:
            return False, "找不到可用的 Steam 遊戲庫路徑"
        primary_steamapps = libs[0] / "steamapps"
        primary_steamapps.mkdir(parents=True, exist_ok=True)
        acf = primary_steamapps / f"appmanifest_{app_id_str}.acf"
        
        name_str = game_name or f"App_{app_id_str}"
        stub_content = f'''"AppState"
{{
\t"appid"\t\t"{app_id_str}"
\t"Universe"\t\t"1"
\t"name"\t\t"{name_str}"
\t"StateFlags"\t\t"1026"
\t"installdir"\t\t"{name_str}"
\t"AutoUpdateBehavior"\t\t"1"
\t"ScheduledAutoUpdate"\t\t"0"
}}
'''
        try:
            acf.write_text(stub_content, encoding="utf-8")
            created_new = True
        except Exception as e:
            return False, f"建立 ACF 範本失敗: {e}"

    try:
        # 解鎖並維持寫入權限 (消除唯讀屬性)
        if acf.exists():
            os.chmod(acf, stat.S_IWRITE | stat.S_IREAD)
            try:
                import win32file
                win32file.SetFileAttributes(str(acf), win32file.FILE_ATTRIBUTE_NORMAL)
            except Exception:
                pass
            content = acf.read_text(encoding="utf-8", errors="ignore")
            
            if re.search(r'"AutoUpdateBehavior"\s+"[^"]*"', content):
                content = re.sub(r'"AutoUpdateBehavior"\s+"[^"]*"', '"AutoUpdateBehavior"\t\t"1"', content)
            else:
                content = re.sub(r'(\s*\}\s*)$', '\n\t"AutoUpdateBehavior"\t\t"1"\\1', content)
                
            if re.search(r'"ScheduledAutoUpdate"\s+"[^"]*"', content):
                content = re.sub(r'"ScheduledAutoUpdate"\s+"[^"]*"', '"ScheduledAutoUpdate"\t\t"0"', content)
            else:
                content = re.sub(r'(\s*\}\s*)$', '\n\t"ScheduledAutoUpdate"\t\t"0"\\1', content)
                
            acf.write_text(content, encoding="utf-8")
            
            # 核心防護修正：嚴禁將 ACF 設為 S_IREAD 唯讀！
            # Steam 下載引擎需要持續向 ACF 寫入下載進度，若唯讀必定引發「磁碟寫入錯誤」。
            os.chmod(acf, stat.S_IWRITE | stat.S_IREAD)
    except Exception as e:
        return False, f"修改 appmanifest 失敗: {e}"
        
    # 鎖定 Lua 檔案唯讀 (Steam 本體不會寫入 Lua，只有 OST 讀取，因此保護 Lua 唯讀安全有效)
    try:
        from managers import config_manager
        lua_dir = Path(config_manager.get_config().get("lua_dir", config_manager.DEFAULT_LUA_DIR))
        lua_file = lua_dir / f"{app_id_str}.lua"
        if lua_file.exists():
            os.chmod(lua_file, stat.S_IREAD)
    except Exception:
        pass
        
    action_str = "已預先建立並鎖定 ACF" if created_new else "版本已鎖定成功"
    return True, f"{action_str}！已設定 AutoUpdateBehavior=1 (防 401 封鎖，且維持磁碟寫入安全)！"


def unlock_game_version(app_id, steam_path=None):
    """
    解除遊戲版本鎖定，恢復 Steam 預設自動更新與正常寫入權限。
    回傳: (success: bool, message: str)
    """
    app_id_str = str(app_id)
    acf = find_appmanifest(app_id_str, steam_path)
    
    if acf and acf.exists():
        try:
            os.chmod(acf, stat.S_IWRITE | stat.S_IREAD)
            try:
                import win32file
                win32file.SetFileAttributes(str(acf), win32file.FILE_ATTRIBUTE_NORMAL)
            except Exception:
                pass
            content = acf.read_text(encoding="utf-8", errors="ignore")
            if re.search(r'"AutoUpdateBehavior"\s+"[^"]*"', content):
                content = re.sub(r'"AutoUpdateBehavior"\s+"[^"]*"', '"AutoUpdateBehavior"\t\t"0"', content)
                acf.write_text(content, encoding="utf-8")
        except Exception as e:
            return False, f"解除 ACF 鎖定失敗: {e}"
            
    try:
        from managers import config_manager
        lua_dir = Path(config_manager.get_config().get("lua_dir", config_manager.DEFAULT_LUA_DIR))
        lua_file = lua_dir / f"{app_id_str}.lua"
        if lua_file.exists():
            os.chmod(lua_file, stat.S_IWRITE | stat.S_IREAD)
    except Exception:
        pass
        
    return True, "已解除版本鎖定，恢復 Steam 預設更新機制與檔案寫入權限。"

def unlock_all_appmanifests_readonly(steam_path=None) -> int:
    """
    掃描所有 Steam 遊戲庫目錄，解除所有被設為「唯讀」的 appmanifest_<appid>.acf 檔案。
    徹底根治 Steam 下載時出現的「磁碟寫入錯誤 (Disk write error)」。
    回傳: 已解除唯讀的檔案數量
    """
    libs = get_steam_libraries(steam_path)
    unlocked_count = 0
    for lib in libs:
        sapps = lib / "steamapps"
        if not sapps.exists():
            continue
        for acf in sapps.glob("appmanifest_*.acf"):
            try:
                os.chmod(acf, stat.S_IWRITE | stat.S_IREAD)
                try:
                    import win32file
                    attrs = win32file.GetFileAttributes(str(acf))
                    if attrs & win32file.FILE_ATTRIBUTE_READONLY:
                        win32file.SetFileAttributes(str(acf), win32file.FILE_ATTRIBUTE_NORMAL)
                        unlocked_count += 1
                except Exception:
                    pass
            except Exception as e:
                print(f"[steam_manager] 解除 ACF 唯讀失敗 {acf.name}: {e}")
    return unlocked_count

unlock_all_acf_readonly = unlock_all_appmanifests_readonly

def deploy_manifests_to_depotcache(manifests_dict, steam_path=None, lua_dir=None):
    """
    將下載回來的二進位 Manifest 檔案寫入 Steam/depotcache，並將 Lua 腳本寫入 Steam/config/lua 目錄。
    回傳: (deployed_count: int, failed_count: int)
    """
    if not manifests_dict:
        return 0, 0
        
    deployed = 0
    failed = 0
    
    if not steam_path:
        steam_path = find_steam_path()
        
    depotcache = Path(steam_path) / "depotcache" if steam_path else None
    if depotcache:
        depotcache.mkdir(parents=True, exist_ok=True)
        
    if not lua_dir and steam_path:
        lua_dir = Path(steam_path) / "config" / "lua"
    lua_path = Path(lua_dir) if lua_dir else None
    if lua_path:
        lua_path.mkdir(parents=True, exist_ok=True)
        
    for m_name, m_data in manifests_dict.items():
        if not m_name or not m_data:
            continue
            
        t_dir = lua_path if m_name.lower().endswith(".lua") else depotcache
        if not t_dir:
            continue
            
        try:
            dest = t_dir / m_name
            if dest.exists():
                os.chmod(dest, stat.S_IWRITE | stat.S_IREAD)
            if isinstance(m_data, bytes):
                dest.write_bytes(m_data)
            elif isinstance(m_data, str):
                dest.write_text(m_data, encoding="utf-8")
            deployed += 1
        except Exception as e:
            print(f"[steam_manager] deploy manifest {m_name} to {t_dir} failed: {e}")
            failed += 1
            
    return deployed, failed


def sync_lua_with_deployed_manifests(appid, manifests_dict, lua_dir=None):
    """
    當下載並部署了新的 Manifest 檔案後，自動同步更新本地 Lua 檔案中對應 depot 的 setManifestid 宣告。
    確保本地 Lua 宣告的 Manifest ID 與剛部署到 depotcache 的實體檔完全吻合，徹底修復殘缺狀態。
    """
    if not manifests_dict:
        return False
    
    if not lua_dir:
        steam_p = find_steam_path()
        if steam_p:
            lua_dir = Path(steam_p) / "config" / "lua"
            
    if not lua_dir:
        return False
        
    lua_file = Path(lua_dir) / f"{appid}.lua"
    if not lua_file.exists():
        return False
        
    depot_manifest_map = {}
    for fn in manifests_dict.keys():
        if fn.lower().endswith(".manifest"):
            base = fn[:-9]
            if "_" in base:
                parts = base.split("_", 1)
                depot_manifest_map[parts[0]] = parts[1]
                
    if not depot_manifest_map:
        return False
        
    try:
        os.chmod(lua_file, stat.S_IWRITE | stat.S_IREAD)
        content = lua_file.read_text(encoding="utf-8", errors="ignore")
        modified = False
        for d_id, new_m_id in depot_manifest_map.items():
            pattern = re.compile(rf'^[ \t]*(setManifestid\(\s*{d_id}\s*,\s*)"\d+"(.*?\))', re.MULTILINE)
            if pattern.search(content):
                content = pattern.sub(rf'\g<1>"{new_m_id}"\g<2>', content)
                modified = True
                
        if modified:
            lua_file.write_text(content, encoding="utf-8")
            return True
    except Exception as e:
        print(f"[steam_manager] sync_lua_with_deployed_manifests error for {appid}: {e}")
    return False


def sanitize_lua_manifests(appid, steam_path=None, lua_dir=None):
    """
    清洗指定 AppID 的 Lua 檔案宣告：
    檢查 Lua 中每一條 setManifestid(depot_id, manifest_id)。
    如果某個 depot 的 .manifest 實體檔在 depotcache (或 lua 目錄) 中不存在：
    自動將該行加上註解：
      -- [清單缺失防護已停用] setManifestid(...)
    防止 Steam 在下載遊戲時向 Valve 伺服器請求不存在授權的孤兒 DLC/Depot 清單碼，
    徹底避免引發 401 Unauthorized「磁碟寫入錯誤」或「無網路連線」。
    """
    app_id_str = str(appid)
    if not lua_dir:
        from managers import config_manager
        lua_dir = Path(config_manager.get_config().get("lua_dir", config_manager.DEFAULT_LUA_DIR))
    else:
        lua_dir = Path(lua_dir)

    if not steam_path:
        steam_path = find_steam_path()
    else:
        steam_path = Path(steam_path)

    lua_file = lua_dir / f"{app_id_str}.lua"
    if not lua_file.exists():
        return False

    depotcache_dir = (steam_path / "depotcache") if steam_path else None
    if not depotcache_dir or not depotcache_dir.exists():
        return False

    try:
        os.chmod(lua_file, stat.S_IWRITE | stat.S_IREAD)
        content = lua_file.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"[steam_manager] sanitize read error for {appid}: {e}")
        return False

    pattern = re.compile(r'^[ \t]*(setManifestid\(\s*(\d+)\s*,\s*"(\d+)"(?:,\s*(\d+))?\s*\))', re.MULTILINE)
    modified = False

    def replacer(match):
        nonlocal modified
        full_stmt = match.group(1)
        depot_id = match.group(2)
        manifest_id = match.group(3)
        fn = f"{depot_id}_{manifest_id}.manifest"
        exists_in_cache = (depotcache_dir / fn).exists() if depotcache_dir else False
        exists_in_lua = (lua_dir / fn).exists() if lua_dir else False
        if not exists_in_cache and not exists_in_lua:
            modified = True
            return f"-- [清單缺失防護已停用] {full_stmt}"
        return full_stmt

    new_content = pattern.sub(replacer, content)
    if modified:
        try:
            lua_file.write_text(new_content, encoding="utf-8")
            print(f"[steam_manager] Sanitized Lua for {appid}: commented out missing manifests.")
            return True
        except Exception as e:
            print(f"[steam_manager] sanitize write error for {appid}: {e}")

    return False



def find_steam_path():
    """
    從 Windows 註冊表或設定取得 Steam 安裝目錄。
    """
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            reg_path, _ = winreg.QueryValueEx(key, "SteamPath")
            if reg_path and os.path.exists(reg_path):
                return Path(reg_path)
    except Exception:
        pass
        
    try:
        from managers import config_manager
        lua_dir = config_manager.get_config().get("lua_dir")
        if lua_dir:
            p = Path(lua_dir).parent.parent
            if (p / "steam.exe").exists():
                return p
    except Exception:
        pass
        
    for p in [Path("C:/Program Files (x86)/Steam"), Path("C:/Program Files/Steam"), Path("G:/Games/Steam")]:
        if (p / "steam.exe").exists():
            return p
    return None


def get_steam_path():
    """取得 Steam 安裝目錄字串"""
    p = find_steam_path()
    return str(p) if p else None


def get_depotcache_path():
    """取得 Steam depotcache 目錄字串並確保目錄存在"""
    sp = find_steam_path()
    if sp:
        depotcache = Path(sp) / "depotcache"
        depotcache.mkdir(parents=True, exist_ok=True)
        return str(depotcache)
    return None


def get_lua_path():
    """取得 Steam lua 目錄字串並確保目錄存在"""
    try:
        from managers import config_manager
        cfg_lua = config_manager.get_config().get("lua_dir")
        if cfg_lua and os.path.exists(cfg_lua):
            return str(cfg_lua)
    except Exception:
        pass
    sp = find_steam_path()
    if sp:
        lua_p = Path(sp) / "config" / "lua"
        lua_p.mkdir(parents=True, exist_ok=True)
        return str(lua_p)
    return None


def get_lua_manifest_status(appid, steam_path=None, lua_dir=None):
    """
    解析指定 appid 的本地 Lua 檔案，檢查宣告的 setManifestid 與磁碟上 (depotcache 與 lua 目錄) 的二進位 .manifest 檔案是否齊全。
    依據安全防護規範：沒有 manifest 的檔案或檔案缺少者皆視為「殘缺檔案」。
    
    回傳字典:
    {
        "appid": str,
        "has_lua": bool,
        "lua_path": Path | None,
        "is_complete": bool,
        "is_incomplete": bool,
        "status": "complete" | "missing_manifest" | "no_manifest_defined" | "no_lua",
        "status_text": str,
        "declared_manifests": [(depot_id, manifest_id), ...],
        "found_files": [filename, ...],
        "missing_files": [filename, ...],
        "game_name": str
    }
    """
    from managers import config_manager
    app_id_str = str(appid)
    
    if not lua_dir:
        lua_dir = Path(config_manager.get_config().get("lua_dir", config_manager.DEFAULT_LUA_DIR))
    else:
        lua_dir = Path(lua_dir)
        
    if not steam_path:
        steam_path = find_steam_path()
    else:
        steam_path = Path(steam_path)

    lua_file = lua_dir / f"{app_id_str}.lua"
    if not lua_file.exists():
        return {
            "appid": app_id_str,
            "has_lua": False,
            "lua_path": None,
            "is_complete": False,
            "is_incomplete": True,
            "status": "no_lua",
            "status_text": "找不到對應的 Lua 檔案",
            "declared_manifests": [],
            "found_files": [],
            "missing_files": [],
            "game_name": "未知遊戲"
        }

    try:
        content = lua_file.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return {
            "appid": app_id_str,
            "has_lua": True,
            "lua_path": lua_file,
            "is_complete": False,
            "is_incomplete": True,
            "status": "error",
            "status_text": f"讀取失敗: {e}",
            "declared_manifests": [],
            "found_files": [],
            "missing_files": [],
            "game_name": "未知遊戲"
        }

    game_name = "未知遊戲"
    m_name = re.search(r'--\s*\d+\s*-\s*(.+)', content)
    if m_name and m_name.group(1).strip():
        game_name = m_name.group(1).strip()

    if game_name == "未知遊戲":
        try:
            from managers import name_resolver
            game_name = name_resolver.resolve_game_name(app_id_str, lua_path=lua_file, steam_path=steam_path)
        except Exception:
            pass

    pattern = re.compile(r'^[ \t]*setManifestid\(\s*(\d+)\s*,\s*"(\d+)"(?:,\s*(\d+))?\s*\)', re.MULTILINE)
    matches = pattern.findall(content)
    declared = [(m[0], m[1]) for m in matches]


    if not declared:
        # 沒有 setManifestid 宣告，屬於殘缺檔案
        return {
            "appid": app_id_str,
            "has_lua": True,
            "lua_path": lua_file,
            "is_complete": False,
            "is_incomplete": True,
            "status": "no_manifest_defined",
            "status_text": "殘缺檔案 (無 Manifest 宣告，不支援安裝)",
            "declared_manifests": [],
            "found_files": [],
            "missing_files": [],
            "game_name": game_name
        }

    depotcache_dir = (steam_path / "depotcache") if steam_path else None
    if depotcache_dir:
        depotcache_dir.mkdir(parents=True, exist_ok=True)
    found = []
    missing = []

    for depot_id, manifest_id in declared:
        fn = f"{depot_id}_{manifest_id}.manifest"
        exists_in_cache = (depotcache_dir / fn).exists() if (depotcache_dir and depotcache_dir.exists()) else False
        exists_in_lua = (lua_dir / fn).exists() if lua_dir else False

        # 自動自癒修復：若檔案曾誤放入 lua 目錄，自動同步遷移至 depotcache 目錄
        if not exists_in_cache and exists_in_lua and depotcache_dir:
            try:
                import shutil
                shutil.copy2(lua_dir / fn, depotcache_dir / fn)
                exists_in_cache = True
                print(f"[steam_manager] Auto-migrated manifest {fn} from lua_dir to depotcache")
            except Exception as e:
                print(f"[steam_manager] Failed to auto-migrate {fn}: {e}")

        # Steam 下載引擎只讀取 depotcache 目錄！
        if exists_in_cache:
            found.append(fn)
        else:
            missing.append(fn)

    # 智慧校驗與跨平台容錯：
    # 若本機已成功安裝該遊戲 (ACF 存在且 StateFlags 包含 4)，檢查 missing 的 Depot 是否根本不在 Windows 的 InstalledDepots 內。
    # 例如 macOS 專屬 Depot (如 Sephiria 2436942) 在 Windows 環境下無需下載，不應被誤判為殘缺。
    if missing and steam_path:
        acf_file = steam_path / "steamapps" / f"appmanifest_{app_id_str}.acf"
        if acf_file.exists():
            try:
                acf_text = acf_file.read_text(encoding="utf-8", errors="ignore")
                sf_m = re.search(r'"StateFlags"\s+"(\d+)"', acf_text)
                is_installed = sf_m and (int(sf_m.group(1)) & 4 != 0 or sf_m.group(1) == "4")
                if is_installed:
                    in_depots_sec = re.search(r'"InstalledDepots"\s*\{([^}]+)\}', acf_text)
                    if in_depots_sec:
                        installed_depots = set(re.findall(r'"(\d+)"\s*\{', in_depots_sec.group(1)))
                        if installed_depots:
                            real_missing = []
                            for fn in missing:
                                d_id = fn.split("_")[0]
                                if d_id in installed_depots:
                                    real_missing.append(fn)
                                else:
                                    print(f"[steam_manager] AppID {app_id_str}: 赦免非本機平台/非必要缺失 Depot {d_id} ({fn})")
                            missing = real_missing
            except Exception:
                pass

    is_complete = len(missing) == 0 and len(declared) > 0
    status = "complete" if is_complete else "missing_manifest"
    status_text = "完整 (Manifest 檔案齊全)" if is_complete else f"殘缺檔案 (缺少 {len(missing)} 個 Manifest 檔)"

    return {
        "appid": app_id_str,
        "has_lua": True,
        "lua_path": lua_file,
        "is_complete": is_complete,
        "is_incomplete": not is_complete,
        "status": status,
        "status_text": status_text,
        "declared_manifests": declared,
        "found_files": found,
        "missing_files": missing,
        "game_name": game_name
    }


def get_all_lua_manifest_statuses(steam_path=None, lua_dir=None):
    """
    掃描全部本地 Lua 檔案，並統計完整與殘缺狀態。
    """
    from managers import config_manager
    if not lua_dir:
        lua_dir = Path(config_manager.get_config().get("lua_dir", config_manager.DEFAULT_LUA_DIR))
    else:
        lua_dir = Path(lua_dir)

    if not lua_dir.exists():
        return {"total": 0, "complete_count": 0, "incomplete_count": 0, "items": [], "incomplete_items": []}

    lua_files = sorted(lua_dir.glob("*.lua"))
    items = []
    incomplete_items = []
    complete_count = 0

    for lf in lua_files:
        appid = lf.stem
        if not appid.isdigit():
            continue
        res = get_lua_manifest_status(appid, steam_path, lua_dir)
        items.append(res)
        if res["is_complete"]:
            complete_count += 1
        else:
            incomplete_items.append(res)

    return {
        "total": len(items),
        "complete_count": complete_count,
        "incomplete_count": len(incomplete_items),
        "items": items,
        "incomplete_items": incomplete_items
    }


