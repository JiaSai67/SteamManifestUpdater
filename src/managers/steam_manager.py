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

def uninstall_opensteamtools(steam_path, restart_steam_after=False):
    """
    防呆流程：移除 OpenSteamTools DLLs 並可選重啟 Steam 還原純淨環境。
    """
    steam_path = Path(steam_path)
    if not steam_path.exists():
        return False, "Steam 路徑不存在"
        
    # 1. 關閉 Steam 釋放 DLL 檔案鎖定 (若運行中)
    was_running = is_steam_running()
    if was_running:
        kill_steam(timeout=6)
        
    dlls = ["OpenSteamTool.dll", "dwmapi.dll", "xinput1_4.dll"]
    removed_count = 0
    try:
        for dll in dlls:
            dst = steam_path / dll
            if dst.exists():
                dst.unlink()
                removed_count += 1
                
        # 移除 opensteamtool.toml
        toml_dst = steam_path / "opensteamtool.toml"
        if toml_dst.exists():
            toml_dst.unlink()
            removed_count += 1
    except Exception as e:
        return False, f"刪除檔案失敗: {e}"
        
    # 2. 若需要且原本在運行才重啟 Steam
    if restart_steam_after and was_running:
        re_ok, re_msg, pid = restart_steam(steam_path)
        if re_ok:
            return True, f"OpenSteamTools 已成功移除，且已為您重啟 Steam！"
        else:
            return True, f"OpenSteamTools 已成功移除！(請手動啟動 Steam)"
    return True, f"OpenSteamTools 核心組件已成功移除！已清理 {removed_count} 個檔案。"

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

def _set_path_readonly(p: Path):
    """將指定檔案路徑設為 Windows 唯讀保護屬性 (FILE_ATTRIBUTE_READONLY + stat.S_IREAD)"""
    try:
        if not p.exists():
            return
        try:
            import win32file
            win32file.SetFileAttributes(str(p), win32file.FILE_ATTRIBUTE_READONLY)
        except Exception:
            pass
        os.chmod(p, stat.S_IREAD)
    except Exception:
        pass


def _set_path_writable(p: Path):
    """將指定檔案路徑還原為正常讀寫權限 (FILE_ATTRIBUTE_NORMAL + stat.S_IWRITE | stat.S_IREAD)"""
    try:
        if not p.exists():
            return
        try:
            import win32file
            win32file.SetFileAttributes(str(p), win32file.FILE_ATTRIBUTE_NORMAL)
        except Exception:
            pass
        os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
    except Exception:
        pass


def get_game_manifest_files(app_id, steam_path=None) -> list:
    """
    獲取指定遊戲關聯的所有實體 Manifest 檔案清單（包含當前版本與所有歷史版本）：
    1. 從 <app_id>.lua 解析所有宣告的 Depot ID (setManifestid, addappid)
    2. 加入 app_id 本身
    3. 掃描 Steam/depotcache 與 Steam/config/depotcache 中所有符合 {depot_id}_*.manifest 與 {depot_id}.manifest 的檔案
    4. 回傳實體存在的 Path 物件清單 (自動去重複)
    """
    app_id_str = str(app_id).strip()
    if not steam_path:
        steam_path = find_steam_path()
    if not steam_path:
        return []

    sp = Path(steam_path)

    # 尋找所有可能存放該遊戲 Lua 的目錄
    lua_candidates = [
        sp / "config" / "lua" / f"{app_id_str}.lua",
        sp / "config" / "stplug-in" / f"{app_id_str}.lua",
    ]
    try:
        from managers import config_manager
        cfg_lua = Path(config_manager.get_config().get("lua_dir", config_manager.DEFAULT_LUA_DIR)) / f"{app_id_str}.lua"
        if cfg_lua not in lua_candidates:
            lua_candidates.append(cfg_lua)
    except Exception:
        pass

    lua_file = None
    for cand in lua_candidates:
        if cand.exists():
            lua_file = cand
            break

    depot_ids = {app_id_str}
    if lua_file and lua_file.exists():
        try:
            content = lua_file.read_text(encoding="utf-8", errors="ignore")
            # 匹配 setManifestid(did, ...) 或 addappid(did, ...)
            matches = re.findall(r'(?:set[M|m]anifest[i|I]d|addappid)\s*\(\s*(\d+)', content)
            for did in matches:
                if did and did != "0":
                    depot_ids.add(str(did))
        except Exception as e:
            print(f"[get_game_manifest_files] 解析 Lua 失敗: {e}")

    search_dirs = [
        sp / "depotcache",
        sp / "config" / "depotcache",
        sp / "config" / "lua",
    ]

    found_manifests = []
    seen_paths = set()

    for s_dir in search_dirs:
        if not s_dir.exists():
            continue
        for did in depot_ids:
            # 匹配該 depot 的所有當前與歷史版本 Manifest: {did}_*.manifest 以及 {did}.manifest
            for pattern in (f"{did}_*.manifest", f"{did}.manifest"):
                for m_file in s_dir.glob(pattern):
                    if m_file.is_file():
                        try:
                            resolved = m_file.resolve()
                            if resolved not in seen_paths:
                                seen_paths.add(resolved)
                                found_manifests.append(m_file)
                        except Exception:
                            if m_file not in found_manifests:
                                found_manifests.append(m_file)

    return found_manifests


def get_game_manifest_lock_info(app_id, steam_path=None):
    """
    檢查指定遊戲的 Manifest、Lua 與 ACF 鎖定狀態。
    回傳: dict
    """
    app_id_str = str(app_id).strip()
    if not steam_path:
        steam_path = find_steam_path()
    sp = Path(steam_path) if steam_path else None

    # 檢查 Lua 檔案狀態
    lua_candidates = []
    if sp:
        lua_candidates.extend([
            sp / "config" / "lua" / f"{app_id_str}.lua",
            sp / "config" / "stplug-in" / f"{app_id_str}.lua",
        ])
    try:
        from managers import config_manager
        cfg_lua = Path(config_manager.get_config().get("lua_dir", config_manager.DEFAULT_LUA_DIR)) / f"{app_id_str}.lua"
        if cfg_lua not in lua_candidates:
            lua_candidates.append(cfg_lua)
    except Exception:
        pass

    lua_file = None
    has_lua = False
    is_lua_ro = False
    for cand in lua_candidates:
        if cand.exists():
            lua_file = cand
            has_lua = True
            try:
                st = os.stat(cand)
                is_lua_ro = bool(st.st_mode & stat.S_IREAD) and not bool(st.st_mode & stat.S_IWRITE)
                try:
                    import win32file
                    attrs = win32file.GetFileAttributes(str(cand))
                    if attrs != -1 and (attrs & win32file.FILE_ATTRIBUTE_READONLY):
                        is_lua_ro = True
                except Exception:
                    pass
            except Exception:
                pass
            break

    # 檢查所有關聯實體 Manifest 檔案（含歷史版本）
    manifest_files = get_game_manifest_files(app_id_str, steam_path)
    locked_manifests_count = 0
    for mf in manifest_files:
        try:
            st = os.stat(mf)
            ro = bool(st.st_mode & stat.S_IREAD) and not bool(st.st_mode & stat.S_IWRITE)
            try:
                import win32file
                attrs = win32file.GetFileAttributes(str(mf))
                if attrs != -1 and (attrs & win32file.FILE_ATTRIBUTE_READONLY):
                    ro = True
            except Exception:
                pass
            if ro:
                locked_manifests_count += 1
        except Exception:
            pass

    acf = find_appmanifest(app_id_str, steam_path)
    if not acf or not acf.exists():
        is_locked = is_lua_ro or (locked_manifests_count > 0 and locked_manifests_count == len(manifest_files))
        status_text = "未鎖定"
        if is_locked:
            status_text = f"已鎖定 🔒 (Lua 與 {locked_manifests_count} 個 Manifest 唯讀中)"
        return {
            "has_acf": False,
            "acf_path": None,
            "auto_update_behavior": None,
            "is_readonly": False,
            "has_lua": has_lua,
            "is_lua_readonly": is_lua_ro,
            "manifest_count": len(manifest_files),
            "manifest_locked_count": locked_manifests_count,
            "is_locked": is_locked,
            "status_text": status_text
        }

    st = os.stat(acf)
    is_ro = bool(st.st_mode & stat.S_IREAD) and not bool(st.st_mode & stat.S_IWRITE)
    content = acf.read_text(encoding="utf-8", errors="ignore")

    auto_update = None
    m = re.search(r'"AutoUpdateBehavior"\s+"(\d+)"', content)
    if m:
        auto_update = int(m.group(1))

    is_locked = (auto_update == 1) or is_ro or is_lua_ro or (locked_manifests_count > 0 and locked_manifests_count == len(manifest_files))
    if is_locked:
        status_text = f"已鎖定 🔒 (防 401 封鎖，含 {locked_manifests_count} 個 Manifest 唯讀鎖定)"
        if is_ro:
            status_text += " [ACF唯讀]"
    else:
        status_text = "未鎖定 ⚠️ (自動更新開啟中，可能觸發 401 封鎖)"

    return {
        "has_acf": True,
        "acf_path": acf,
        "auto_update_behavior": auto_update,
        "is_readonly": is_ro,
        "has_lua": has_lua,
        "is_lua_readonly": is_lua_ro,
        "manifest_count": len(manifest_files),
        "manifest_locked_count": locked_manifests_count,
        "is_locked": is_locked,
        "status_text": status_text
    }


def lock_game_version(app_id, steam_path=None, set_readonly=False, game_name=None):
    """
    鎖定遊戲版本防封鎖與版本漂移：
    1. 鎖定 <appid>.lua 檔案為唯讀屬性 (FILE_ATTRIBUTE_READONLY)。
    2. 鎖定該遊戲底下所有關聯的 Manifest 檔案為唯讀屬性（包含當前版本與所有歷史版本，涵蓋 depotcache 與 config/depotcache）。
    3. 絕不主動為未安裝的遊戲建立假 ACF 範本！(避免產生 StateFlags: 1026 幽靈排程)
    4. 若遊戲確實已安裝且存在 ACF，將 AutoUpdateBehavior 設為 1 (僅在啟動時更新，阻止背景自動更新)，ScheduledAutoUpdate 設為 0。
    5. 絕不將 ACF 設為作業系統唯讀屬性！(保持可讀寫，避免引發 Steam 磁碟寫入錯誤)
    回傳: (success: bool, message: str)
    """
    app_id_str = str(app_id).strip()
    if not steam_path:
        steam_path = find_steam_path()
    sp = Path(steam_path) if steam_path else None

    # 1. 鎖定 Lua 檔案唯讀保護
    lua_candidates = []
    if sp:
        lua_candidates.extend([
            sp / "config" / "lua" / f"{app_id_str}.lua",
            sp / "config" / "stplug-in" / f"{app_id_str}.lua",
        ])
    try:
        from managers import config_manager
        cfg_lua = Path(config_manager.get_config().get("lua_dir", config_manager.DEFAULT_LUA_DIR)) / f"{app_id_str}.lua"
        if cfg_lua not in lua_candidates:
            lua_candidates.append(cfg_lua)
    except Exception:
        pass

    locked_lua_count = 0
    for lf in lua_candidates:
        if lf.exists():
            _set_path_readonly(lf)
            locked_lua_count += 1

    # 2. 鎖定底下所有關聯的實體 Manifest 檔案：
    #    - config/depotcache (備援庫)：設為唯讀保護，作為黃金備份
    #    - depotcache (Steam 運行目錄)：強制取消唯讀 (設為可讀寫)，確保 Steam 下載/校驗時正常讀寫，絕不觸發 Content Corrupt 錯誤
    manifest_files = get_game_manifest_files(app_id_str, steam_path)
    locked_manifest_count = 0
    for mf in manifest_files:
        if "config" in mf.parts and "depotcache" in mf.parts:
            _set_path_readonly(mf)
            locked_manifest_count += 1
        else:
            _set_path_writable(mf)  # 🌟 depotcache 運行目錄永遠保持可讀寫

    # 3. 檢查 ACF 狀態
    acf = find_appmanifest(app_id_str, steam_path)

    # 若尚無 ACF 檔案，未安裝遊戲無需亦不可產生 ACF
    if not acf or not acf.exists():
        msg = f"版本已鎖定成功 🔒！已保護 Lua 與 {locked_manifest_count} 個備援 Manifest 檔案，且 Steam 運行快取保持可讀寫。"
        return True, msg

    # 若 ACF 存在，進一步檢查是否為未下載實體檔案的幽靈 ACF
    try:
        content = acf.read_text(encoding="utf-8", errors="ignore")
        m_dir = re.search(r'"installdir"\s+"([^"]+)"', content)
        installdir = m_dir.group(1) if m_dir else ""
        common_dir = acf.parent / "common" / installdir if installdir else None
        dir_exists = (common_dir.exists() and any(common_dir.iterdir())) if (common_dir and common_dir.exists()) else False

        # 若實體遊戲目錄根本不存在，判定為幽靈 ACF，直接清理以解除 Steam 排程
        if not dir_exists:
            try:
                _set_path_writable(acf)
                acf.unlink()
                return True, f"偵測到未安裝實體檔案之幽靈 ACF ({acf.name})，已自動清除；並已鎖定 Lua 與 {locked_manifest_count} 個關聯 Manifest（含歷史版本）為唯讀。"
            except Exception as e:
                return False, f"清理幽靈 ACF 失敗: {e}"

        # 遊戲已安裝實體檔案：將 AutoUpdateBehavior 設為 1，ScheduledAutoUpdate 設為 0
        _set_path_writable(acf)

        if re.search(r'"AutoUpdateBehavior"\s+"[^"]*"', content):
            content = re.sub(r'"AutoUpdateBehavior"\s+"[^"]*"', '"AutoUpdateBehavior"\t\t"1"', content)
        else:
            content = re.sub(r'(\s*\}\s*)$', '\n\t"AutoUpdateBehavior"\t\t"1"\\1', content)

        if re.search(r'"ScheduledAutoUpdate"\s+"[^"]*"', content):
            content = re.sub(r'"ScheduledAutoUpdate"\s+"[^"]*"', '"ScheduledAutoUpdate"\t\t"0"', content)
        else:
            content = re.sub(r'(\s*\}\s*)$', '\n\t"ScheduledAutoUpdate"\t\t"0"\\1', content)

        acf.write_text(content, encoding="utf-8")
        _set_path_writable(acf)  # 保持可讀寫，防 Steam 寫入錯誤
    except Exception as e:
        return False, f"修改 appmanifest 失敗: {e}"

    return True, f"版本已鎖定成功 🔒！已設定 AutoUpdateBehavior=1 (僅啟動時更新)，並鎖定 Lua 與 {locked_manifest_count} 個關聯 Manifest 檔案（含歷史版本）為唯讀狀態。"


def unlock_game_version(app_id, steam_path=None):
    """
    解除遊戲版本鎖定：
    1. 解鎖 <appid>.lua 檔案，恢復正常讀寫權限。
    2. 解鎖該遊戲關聯的所有實體 Manifest 檔案（包含當前與歷史版本），恢復正常讀寫權限。
    3. 恢復 Steam 預設自動更新 (AutoUpdateBehavior=0)。
    回傳: (success: bool, message: str)
    """
    app_id_str = str(app_id).strip()
    if not steam_path:
        steam_path = find_steam_path()
    sp = Path(steam_path) if steam_path else None

    # 1. 解鎖 Lua 檔案
    lua_candidates = []
    if sp:
        lua_candidates.extend([
            sp / "config" / "lua" / f"{app_id_str}.lua",
            sp / "config" / "stplug-in" / f"{app_id_str}.lua",
        ])
    try:
        from managers import config_manager
        cfg_lua = Path(config_manager.get_config().get("lua_dir", config_manager.DEFAULT_LUA_DIR)) / f"{app_id_str}.lua"
        if cfg_lua not in lua_candidates:
            lua_candidates.append(cfg_lua)
    except Exception:
        pass

    for lf in lua_candidates:
        if lf.exists():
            _set_path_writable(lf)

    # 2. 解鎖關聯的所有實體 Manifest 檔案（含歷史版本）
    manifest_files = get_game_manifest_files(app_id_str, steam_path)
    unlocked_manifest_count = 0
    for mf in manifest_files:
        _set_path_writable(mf)
        unlocked_manifest_count += 1

    # 3. 解除 ACF 鎖定
    acf = find_appmanifest(app_id_str, steam_path)
    if acf and acf.exists():
        try:
            _set_path_writable(acf)
            content = acf.read_text(encoding="utf-8", errors="ignore")
            if re.search(r'"AutoUpdateBehavior"\s+"[^"]*"', content):
                content = re.sub(r'"AutoUpdateBehavior"\s+"[^"]*"', '"AutoUpdateBehavior"\t\t"0"', content)
                acf.write_text(content, encoding="utf-8")
        except Exception as e:
            return False, f"解除 ACF 鎖定失敗: {e}"

    return True, f"已解除版本鎖定 🔓！已恢復 Lua 與 {unlocked_manifest_count} 個關聯 Manifest 檔案之正常讀寫權限。"


def clean_phantom_appmanifests(steam_path=None):
    """
    掃描所有 Steam 遊戲庫目錄，安全清理所有無實體遊戲檔案的「幽靈 ACF」檔案。
    徹底解決未下載遊戲因殘留/誤建 ACF 而被強行塞入 Steam 下載排程的問題。
    回傳: (cleaned_count: int, cleaned_list: list)
    """
    libs = get_steam_libraries(steam_path)
    cleaned_list = []
    
    if not steam_path:
        steam_path = find_steam_path()
    lua_dir = Path(steam_path) / "config" / "lua" if steam_path else None
    
    for lib in libs:
        sapps = lib / "steamapps"
        if not sapps.exists():
            continue
            
        for acf in list(sapps.glob("appmanifest_*.acf")):
            try:
                text = acf.read_text(encoding="utf-8", errors="ignore")
                m_app = re.search(r'"appid"\s+"(\d+)"', text)
                m_name = re.search(r'"name"\s+"([^"]+)"', text)
                m_dir = re.search(r'"installdir"\s+"([^"]+)"', text)
                m_flags = re.search(r'"StateFlags"\s+"([^"]+)"', text)
                
                appid = m_app.group(1) if m_app else acf.stem.replace("appmanifest_", "")
                name = m_name.group(1) if m_name else f"App_{appid}"
                installdir = m_dir.group(1) if m_dir else ""
                flags = m_flags.group(1) if m_flags else ""
                
                # 排除 Steamworks Common Redistributables (228980) 官方運行庫
                if appid == "228980":
                    continue
                    
                common_dir = sapps / "common" / installdir if installdir else None
                dir_exists = (common_dir.exists() and any(common_dir.iterdir())) if (common_dir and common_dir.exists()) else False
                
                # 判斷是否為 Lua 關聯遊戲
                has_lua = (lua_dir / f"{appid}.lua").exists() if (lua_dir and lua_dir.exists()) else False
                
                # 幽靈 ACF 判定條件：實體目錄不存在，且 (StateFlags 為 1026/514/1042 或本機有 Lua 或 name 為 App_*)
                is_phantom = (not dir_exists) and (flags in ["1026", "514", "1042", "2"] or has_lua or name.startswith("App_"))
                
                if is_phantom:
                    os.chmod(acf, stat.S_IWRITE | stat.S_IREAD)
                    try:
                        import win32file
                        win32file.SetFileAttributes(str(acf), win32file.FILE_ATTRIBUTE_NORMAL)
                    except Exception:
                        pass
                    acf.unlink()
                    cleaned_list.append({
                        "appid": appid,
                        "name": name,
                        "acf_path": str(acf),
                        "reason": f"實體目錄不存在 (StateFlags: {flags})"
                    })
                    print(f"[steam_manager] 已安全清理幽靈 ACF: {acf.name} ({name})")
            except Exception as e:
                print(f"[steam_manager] 清理幽靈 ACF 失敗 {acf.name}: {e}")
                
    return len(cleaned_list), cleaned_list


def sync_lua_games_autoupdate_behavior(steam_path=None, restore_non_lua=True):
    """
    智慧自動更新隔離管理：
    1. 先執行 clean_phantom_appmanifests 清除所有無實體遊戲的幽靈 ACF。
    2. 針對本機存在 <appid>.lua 且已安裝實體遊戲的項目：強制設定 AutoUpdateBehavior = 1 (僅啟動時更新，防 401 封鎖)。
    3. 針對非 Lua 的正常正版遊戲 (且 restore_non_lua=True)：自動還原 AutoUpdateBehavior = 0 (Steam 預設自動更新)，絕不影響正常收藏庫運作！
    回傳: dict 統計資訊
    """
    libs = get_steam_libraries(steam_path)
    if not steam_path:
        steam_path = find_steam_path()
        
    lua_dir = Path(steam_path) / "config" / "lua" if steam_path else None
    existing_luas = set()
    if lua_dir and lua_dir.exists():
        existing_luas = {f.stem for f in lua_dir.glob("*.lua") if f.stem.isdigit()}
        
    # 1. 清理幽靈 ACF
    cleaned_count, cleaned_list = clean_phantom_appmanifests(steam_path)
    
    locked_lua_games = []
    restored_normal_games = []
    
    for lib in libs:
        sapps = lib / "steamapps"
        if not sapps.exists():
            continue
            
        for acf in sapps.glob("appmanifest_*.acf"):
            try:
                text = acf.read_text(encoding="utf-8", errors="ignore")
                m_app = re.search(r'"appid"\s+"(\d+)"', text)
                m_name = re.search(r'"name"\s+"([^"]+)"', text)
                m_upd = re.search(r'"AutoUpdateBehavior"\s+"(\d+)"', text)
                
                appid = m_app.group(1) if m_app else acf.stem.replace("appmanifest_", "")
                name = m_name.group(1) if m_name else f"App_{appid}"
                current_upd = m_upd.group(1) if m_upd else "0"
                
                # 排除官方運行庫
                if appid == "228980":
                    continue
                    
                is_lua_game = (appid in existing_luas)
                
                if is_lua_game:
                    # Lua 遊戲：確保 AutoUpdateBehavior = 1, ScheduledAutoUpdate = 0
                    if current_upd != "1":
                        os.chmod(acf, stat.S_IWRITE | stat.S_IREAD)
                        try:
                            import win32file
                            win32file.SetFileAttributes(str(acf), win32file.FILE_ATTRIBUTE_NORMAL)
                        except Exception:
                            pass
                            
                        content = text
                        if re.search(r'"AutoUpdateBehavior"\s+"[^"]*"', content):
                            content = re.sub(r'"AutoUpdateBehavior"\s+"[^"]*"', '"AutoUpdateBehavior"\t\t"1"', content)
                        else:
                            content = re.sub(r'(\s*\}\s*)$', '\n\t"AutoUpdateBehavior"\t\t"1"\\1', content)
                            
                        if re.search(r'"ScheduledAutoUpdate"\s+"[^"]*"', content):
                            content = re.sub(r'"ScheduledAutoUpdate"\s+"[^"]*"', '"ScheduledAutoUpdate"\t\t"0"', content)
                        else:
                            content = re.sub(r'(\s*\}\s*)$', '\n\t"ScheduledAutoUpdate"\t\t"0"\\1', content)
                            
                        acf.write_text(content, encoding="utf-8")
                        os.chmod(acf, stat.S_IWRITE | stat.S_IREAD)
                    locked_lua_games.append({"appid": appid, "name": name})
                else:
                    # 非 Lua 遊戲 (正版遊戲)：若被設為 1 且允許還原，恢復為 0
                    if restore_non_lua and current_upd == "1":
                        os.chmod(acf, stat.S_IWRITE | stat.S_IREAD)
                        try:
                            import win32file
                            win32file.SetFileAttributes(str(acf), win32file.FILE_ATTRIBUTE_NORMAL)
                        except Exception:
                            pass
                            
                        content = text
                        if re.search(r'"AutoUpdateBehavior"\s+"[^"]*"', content):
                            content = re.sub(r'"AutoUpdateBehavior"\s+"[^"]*"', '"AutoUpdateBehavior"\t\t"0"', content)
                            acf.write_text(content, encoding="utf-8")
                        os.chmod(acf, stat.S_IWRITE | stat.S_IREAD)
                        restored_normal_games.append({"appid": appid, "name": name})
            except Exception as e:
                print(f"[steam_manager] 處理 ACF 自動更新設定失敗 {acf.name}: {e}")
                
    return {
        "cleaned_phantom_count": cleaned_count,
        "cleaned_phantom_list": cleaned_list,
        "locked_lua_count": len(locked_lua_games),
        "locked_lua_games": locked_lua_games,
        "restored_normal_count": len(restored_normal_games),
        "restored_normal_games": restored_normal_games
    }


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
    【核心防護機制】：
    1. 同步永久備份至 Steam/config/depotcache (Steam 解除安裝時絕不會刪除此目錄)。
    2. 對寫入 Steam/depotcache 的 .manifest 二進位清單設定「唯讀屬性 (Read-Only)」，
       防止 Steam 在使用者點擊解除安裝時惡意清空 depotcache 清單，確保後續再次下載永遠免受 MRC 遠端伺服器 502/503 癱瘓之苦！
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
        
    # 永久 Manifest 備份目錄 (Steam/config/depotcache，Steam 解除安裝時絕不會刪除此目錄)
    config_depotcache = (Path(steam_path) / "config" / "depotcache") if steam_path else None
    if config_depotcache:
        config_depotcache.mkdir(parents=True, exist_ok=True)
        
    lua_targets = []
    if lua_dir:
        lua_targets.append(Path(lua_dir))
    if steam_path:
        def_l = Path(steam_path) / "config" / "lua"
        if def_l not in lua_targets:
            lua_targets.append(def_l)
        st_l = Path(steam_path) / "config" / "stplug-in"
        if st_l.exists() and st_l not in lua_targets:
            lua_targets.append(st_l)
    for lt in lua_targets:
        lt.mkdir(parents=True, exist_ok=True)
        
    for m_name, m_data in manifests_dict.items():
        if not m_name or not m_data:
            continue
            
        is_lua = m_name.lower().endswith(".lua")
        targets = lua_targets if is_lua else ([depotcache] if depotcache else [])
        if not targets:
            continue
            
        # 若為 .manifest 檔案，永久備份至 Steam/config/depotcache
        if not is_lua and m_name.lower().endswith(".manifest") and config_depotcache:
            try:
                c_dst = config_depotcache / m_name
                if c_dst.exists():
                    try: os.chmod(c_dst, stat.S_IWRITE | stat.S_IREAD)
                    except Exception: pass
                if isinstance(m_data, bytes):
                    c_dst.write_bytes(m_data)
                elif isinstance(m_data, str):
                    c_dst.write_text(m_data, encoding="utf-8")
                try:
                    os.chmod(c_dst, stat.S_IREAD)  # 🌟 備援金庫設為唯讀保護
                except Exception:
                    pass
            except Exception as e:
                print(f"[steam_manager] backup to config/depotcache failed {m_name}: {e}")
            
        success_any = False
        for t_dir in targets:
            try:
                dest = t_dir / m_name
                if dest.exists():
                    os.chmod(dest, stat.S_IWRITE | stat.S_IREAD)
                if isinstance(m_data, bytes):
                    dest.write_bytes(m_data)
                elif isinstance(m_data, str):
                    dest.write_text(m_data, encoding="utf-8")
                    
                # 🌟 depotcache 運行目錄永遠保持可讀寫 (取消唯讀)
                if not is_lua and m_name.lower().endswith(".manifest") and t_dir == depotcache:
                    try:
                        os.chmod(dest, stat.S_IWRITE | stat.S_IREAD)
                    except Exception:
                        pass
                success_any = True
            except Exception as e:
                print(f"[steam_manager] deploy manifest {m_name} to {t_dir} failed: {e}")
        if success_any:
            deployed += 1
        else:
            failed += 1
            
    return deployed, failed


def sync_lua_with_deployed_manifests(appid, manifests_dict, lua_dir=None, deprecated_depots=None):
    """
    當下載並部署了新的 Manifest 檔案後，自動同步更新本地 Lua 檔案中對應 depot 的 setManifestid 宣告。
    確保本地 Lua 宣告的 Manifest ID 與剛部署到 depotcache 的實體檔完全吻合，徹底修復殘缺狀態。
    支援自動遷移與停用已棄置之舊 Depot (Deprecated Depots)，並同步更新 ACF 節點。
    """
    if not manifests_dict:
        return False
    
    appid_str = str(appid).strip()
    target_lua_dirs = []
    
    if lua_dir:
        target_lua_dirs.append(Path(lua_dir))
        
    steam_p = find_steam_path()
    if steam_p:
        def_lua = Path(steam_p) / "config" / "lua"
        if def_lua not in target_lua_dirs:
            target_lua_dirs.append(def_lua)
        st_lua = Path(steam_p) / "config" / "stplug-in"
        if st_lua.exists() and st_lua not in target_lua_dirs:
            target_lua_dirs.append(st_lua)
            
    from managers import config_manager
    cfg_lua = config_manager.get_config().get("lua_dir")
    if cfg_lua:
        cfg_p = Path(cfg_lua)
        if cfg_p not in target_lua_dirs:
            target_lua_dirs.append(cfg_p)

    # 🌟 解析 manifests_dict 支援三種輸入格式：
    # 1. {"3934271_215526684630175472.manifest": ...}
    # 2. {"3934271_215526684630175472": ...}
    # 3. {"3934271": "215526684630175472"}
    depot_manifest_map = {}
    for k, v in manifests_dict.items():
        k_str = str(k).strip()
        if k_str.lower().endswith(".manifest"):
            base = k_str[:-9]
            if "_" in base:
                parts = base.split("_", 1)
                depot_manifest_map[parts[0]] = parts[1]
        elif "_" in k_str:
            parts = k_str.split("_", 1)
            depot_manifest_map[parts[0]] = parts[1]
        else:
            depot_manifest_map[k_str] = str(v).strip()
            
    if not depot_manifest_map:
        return False

    # 🌟 自動檢測本地是否存在官方已棄置之 Depot
    if deprecated_depots is None:
        try:
            from managers import version_resolver
            cur_status = get_lua_manifest_status(appid_str, steam_path=steam_p)
            cur_local = {str(d): str(m) for d, m in cur_status.get("declared_manifests", []) if str(m) != "0"}
            topo = version_resolver.identify_depot_topology(appid_str, local_manifests=cur_local, official_manifests=depot_manifest_map)
            if topo.get("has_deprecated"):
                deprecated_depots = topo.get("replaced_map", {})
        except Exception:
            pass
        
    any_modified = False
    for l_dir in target_lua_dirs:
        lua_file = l_dir / f"{appid_str}.lua"
        if not lua_file.exists():
            continue
            
        try:
            os.chmod(lua_file, stat.S_IWRITE | stat.S_IREAD)
            content = lua_file.read_text(encoding="utf-8", errors="ignore")
            modified = False
            
            for d_id, new_m_id in depot_manifest_map.items():
                if deprecated_depots and str(d_id).strip() in deprecated_depots:
                    # 🌟 官方已棄置之舊 Depot，嚴禁重新啟用，由後續 deprecated_depots 區塊註解停用
                    continue
                # 匹配存在的 setManifestid 行（包含已被註解的）
                pattern = re.compile(rf'^[ \t]*(?:--[^\n\r]*?)?(setManifestid\(\s*{re.escape(str(d_id))}\s*,\s*)["\']?\d+["\']?(.*?\))', re.MULTILINE)
                if pattern.search(content):
                    content = pattern.sub(rf'\g<1>"{new_m_id}"\g<2>', content)
                    modified = True
                else:
                    # 如果 Lua 中沒有 setManifestid，但有 addappid(d_id, ...)，在其下一行追加
                    add_pattern = re.compile(rf'(^[ \t]*addappid\(\s*{re.escape(str(d_id))}[^\n\r]*\))', re.MULTILINE)
                    if add_pattern.search(content):
                        content = add_pattern.sub(rf'\g<1>\nsetManifestid({d_id},"{new_m_id}")', content)
                        modified = True
                    else:
                        # 追加到檔案末尾
                        content += f'\nsetManifestid({d_id},"{new_m_id}")'
                        modified = True

            # 🌟 處理官方已棄置之舊 Depot 停用與註解標記 (Deprecated Depots)
            if deprecated_depots and isinstance(deprecated_depots, dict):
                for old_did, rep_did in deprecated_depots.items():
                    old_did_str = str(old_did).strip()
                    rep_did_str = str(rep_did).strip()
                    # 註解 setManifestid(old_did, ...)
                    dep_set_pat = re.compile(rf'^[ \t]*(?!--\s*\[官方已棄置)(?:--\s*)?(setManifestid\(\s*{re.escape(old_did_str)}\s*,\s*["\']?\d+["\']?.*?\))', re.MULTILINE)
                    if dep_set_pat.search(content):
                        content = dep_set_pat.sub(rf'-- [官方已棄置此 Depot，已由 {rep_did_str} 接替] \g<1>', content)
                        modified = True
                    
                    # 確保新接替的 Depot 有宣告 addappid
                    if rep_did_str and not re.search(rf'addappid\(\s*{re.escape(rep_did_str)}', content):
                        add_old_pat = re.compile(rf'(^[ \t]*addappid\(\s*{re.escape(old_did_str)}[^\n\r]*\))', re.MULTILINE)
                        if add_old_pat.search(content):
                            content = add_old_pat.sub(rf'\g<1>\naddappid({rep_did_str})', content)
                            modified = True
                        else:
                            content += f'\naddappid({rep_did_str})'
                            modified = True
                    
            if modified:
                lua_file.write_text(content, encoding="utf-8")
                any_modified = True
                print(f"[steam_manager] 成功同步 {appid_str}.lua 的 Manifest 宣告至: {l_dir}")
        except Exception as e:
            print(f"[steam_manager] sync_lua_with_deployed_manifests error for {appid_str} at {lua_file}: {e}")

    # 🌟 同步更新本地 ACF 檔案 (若存在) 之 InstalledDepots 節點
    if steam_p and deprecated_depots and isinstance(deprecated_depots, dict):
        try:
            acf_file = Path(steam_p) / "steamapps" / f"appmanifest_{appid_str}.acf"
            if acf_file.exists():
                acf_text = acf_file.read_text(encoding="utf-8", errors="ignore")
                acf_mod = False
                for old_did, rep_did in deprecated_depots.items():
                    old_d_str = str(old_did).strip()
                    rep_d_str = str(rep_did).strip()
                    if f'"{old_d_str}"' in acf_text and f'"{rep_d_str}"' not in acf_text:
                        acf_text = acf_text.replace(f'"{old_d_str}"', f'"{rep_d_str}"')
                        new_gid = depot_manifest_map.get(rep_d_str)
                        if new_gid:
                            acf_text = re.sub(
                                rf'("{re.escape(rep_d_str)}"\s*\{{[^}}]*?"manifest"\s*")[^"]*(")',
                                rf'\g<1>{new_gid}\g<2>',
                                acf_text
                            )
                        acf_mod = True
                if acf_mod:
                    os.chmod(acf_file, stat.S_IWRITE | stat.S_IREAD)
                    acf_file.write_text(acf_text, encoding="utf-8")
                    print(f"[steam_manager] 成功同步 {acf_file.name} 中已棄置 Depot 遷移節點")
        except Exception as e_acf:
            print(f"[steam_manager] 遷移 ACF 節點異常 (非阻斷): {e_acf}")
            
    return any_modified


def sync_config_depotcache_backup(steam_path=None, return_list=False):
    """
    將 Steam/config/depotcache 永久備份目錄中的所有 .manifest 檔案自動鏡像同步至標準 Steam/depotcache，
    確保 Steam 下載引擎可讀取，同時【永久保留】Steam/config/depotcache 中的備份，
    完全防禦 Steam 在遊戲解除安裝時惡意清空 depotcache 的問題！
    回傳: synced_count (int) 或 (synced_count, synced_files)
    """
    if not steam_path:
        steam_path = find_steam_path()
    if not steam_path:
        return (0, []) if return_list else 0
    sp = Path(steam_path)
    backup_dir = sp / "config" / "depotcache"
    target_dir = sp / "depotcache"
    if not backup_dir.exists():
        return (0, []) if return_list else 0
    target_dir.mkdir(parents=True, exist_ok=True)
    synced = 0
    synced_files = []
    try:
        for f in backup_dir.glob("*.manifest"):
            dest = target_dir / f.name
            try:
                if not dest.exists() or dest.stat().st_size != f.stat().st_size:
                    if dest.exists():
                        try: os.chmod(dest, stat.S_IWRITE | stat.S_IREAD)
                        except Exception: pass
                    shutil.copy2(f, dest)
                    try: os.chmod(dest, stat.S_IWRITE | stat.S_IREAD)  # 🌟 depotcache 永遠保持可讀寫 (取消唯讀)
                    except Exception: pass
                    synced += 1
                    synced_files.append(f.name)
            except Exception:
                pass
    except Exception as e:
        print(f"[steam_manager] sync_config_depotcache_backup error: {e}")
    if return_list:
        return synced, synced_files
    return synced

# 保持歷史兼容呼叫
migrate_legacy_config_depotcache = sync_config_depotcache_backup


def backup_declared_manifests_to_config_depotcache(steam_path=None, lua_dir=None):
    """
    掃描本地所有 Lua 遊戲宣告之 Manifest，並將 depotcache 中的對應實體檔案備份至 Steam/config/depotcache (防護金庫)。
    回傳字典: {
        "scanned_lua": int,
        "declared_total": int,
        "already_backed_up": int,
        "newly_backed_up": int,
        "missing_files": list,
        "backed_up_files": list
    }
    """
    if not steam_path:
        steam_path = find_steam_path()
    if not steam_path:
        return {"scanned_lua": 0, "declared_total": 0, "already_backed_up": 0, "newly_backed_up": 0, "missing_files": [], "backed_up_files": []}

    sp = Path(steam_path)
    if not lua_dir:
        l_dir = sp / "config" / "lua"
    else:
        l_dir = Path(lua_dir)

    depot_dir = sp / "depotcache"
    backup_dir = sp / "config" / "depotcache"
    backup_dir.mkdir(parents=True, exist_ok=True)

    if not l_dir.exists():
        return {"scanned_lua": 0, "declared_total": 0, "already_backed_up": 0, "newly_backed_up": 0, "missing_files": [], "backed_up_files": []}

    pattern = re.compile(r'setManifestid\(\s*(\d+)\s*,\s*["\']?(\d+)["\']?', re.IGNORECASE)
    all_declared = set()
    lua_files = [f for f in l_dir.glob("*.lua") if f.name != "manifest.lua"]

    for lf in lua_files:
        try:
            content = lf.read_text(encoding="utf-8", errors="ignore")
            for d, m in pattern.findall(content):
                if str(m) != "0":
                    all_declared.add(f"{d}_{m}.manifest")
        except Exception:
            pass

    already = 0
    newly = 0
    missing = []
    backed_up = []

    for fn in sorted(all_declared):
        dst = backup_dir / fn
        src_depot = depot_dir / fn
        src_lua = l_dir / fn

        if dst.exists() and dst.stat().st_size > 0:
            already += 1
            backed_up.append(fn)
        elif src_depot.exists():
            try:
                shutil.copy2(src_depot, dst)
                newly += 1
                backed_up.append(fn)
            except Exception:
                pass
        elif src_lua.exists():
            try:
                shutil.copy2(src_lua, dst)
                newly += 1
                backed_up.append(fn)
            except Exception:
                pass
        else:
            missing.append(fn)

    return {
        "scanned_lua": len(lua_files),
        "declared_total": len(all_declared),
        "already_backed_up": already,
        "newly_backed_up": newly,
        "missing_files": missing,
        "backed_up_files": backed_up
    }


def sync_all_lua_directories(steam_path=None):
    """
    雙向同步所有 Lua 目錄 (Steam/config/lua 與 Steam/config/stplug-in)，
    確保 SteamTools 與 OpenSteamTools 等外掛讀取到的 Lua 內容與 Manifest 宣告 100% 一致。
    """
    if not steam_path:
        steam_path = find_steam_path()
    if not steam_path:
        return 0
    sp = Path(steam_path)
    dir_lua = sp / "config" / "lua"
    dir_st = sp / "config" / "stplug-in"
    if not dir_lua.exists() or not dir_st.exists():
        return 0
    synced = 0
    try:
        for f in dir_lua.glob("*.lua"):
            dst = dir_st / f.name
            if not dst.exists() or dst.stat().st_mtime < f.stat().st_mtime:
                try:
                    if dst.exists(): os.chmod(dst, stat.S_IWRITE | stat.S_IREAD)
                    shutil.copy2(f, dst)
                    synced += 1
                except Exception:
                    pass
    except Exception as e:
        print(f"[steam_manager] sync_all_lua_directories error: {e}")
    return synced


def verify_and_sync_local_manifests(appid, steam_path=None, lua_dir=None, target_manifests=None):
    """
    【三方比對之本機一致性自檢與閉環驗證】
    1. 在檢查更新、搜尋或下載前，先行比對本地 Lua 檔案中的 setManifestid 宣告與本地 depotcache 實體二進位檔案。
    2. 自動解析本地 depotcache 實體檔案之 Valve 官方建立時間戳 (creation_time)。
    3. 若本機已有更新的實體 Manifest 檔案但 Lua 未宣告或宣告舊版，自動修復 (Self-healing) 並寫入 Lua。
    4. 若 Lua 宣告了 Manifest 但實體檔案不存在，精確標記為 missing_files 缺失。
    5. 回傳包含校準狀態、Lua 宣告清單與實體檔案清單的完整自檢結構。
    """
    appid_str = str(appid).strip()
    if not steam_path:
        steam_path = find_steam_path()
    if steam_path:
        steam_path = Path(steam_path)
        # 自動執行歷史 config/depotcache 檔案遷移
        migrate_legacy_config_depotcache(steam_path)
        # 自動執行 Lua 外掛目錄雙向同步 (config/lua <-> config/stplug-in)
        sync_all_lua_directories(steam_path)

    if not lua_dir:
        from managers import config_manager
        lua_dir = Path(config_manager.get_config().get("lua_dir", config_manager.DEFAULT_LUA_DIR))
    else:
        lua_dir = Path(lua_dir)

    lua_file = lua_dir / f"{appid_str}.lua"
    if not lua_file.exists() and steam_path:
        def_lua = steam_path / "config" / "lua" / f"{appid_str}.lua"
        if def_lua.exists():
            lua_file = def_lua

    # 1. 解析目前 Lua 中的宣告與已定義之 Depot IDs
    lua_manifests = {}
    app_depot_ids = set()
    deprecated_declared_depots = set()
    if lua_file.exists():
        try:
            txt = lua_file.read_text(encoding="utf-8", errors="ignore")
            for line in txt.splitlines():
                line_str = line.strip()
                if not line_str:
                    continue
                is_comment = line_str.startswith("--")
                is_deprecated_line = "[官方已棄置此 Depot" in line_str
                m_set = re.search(r'setManifestid\(\s*(\d+)\s*,\s*["\']?(\d+)["\']?', line_str)
                if m_set:
                    did, mid = m_set.group(1), m_set.group(2)
                    if is_deprecated_line:
                        deprecated_declared_depots.add(did)
                    else:
                        app_depot_ids.add(did)
                    # 🌟 核心防護：只有未被註解且非棄置的啟用宣告才計入待驗證清單
                    if not is_comment and not is_deprecated_line:
                        lua_manifests[did] = mid
                m_add = re.search(r'addappid\(\s*(\d+)', line_str)
                if m_add:
                    did_add = m_add.group(1)
                    if not is_comment and did_add not in deprecated_declared_depots:
                        app_depot_ids.add(did_add)
        except Exception:
            pass

    if appid_str.isdigit():
        app_depot_ids.add(appid_str)
        app_depot_ids.add(str(int(appid_str) + 1))

    # 2. 掃描本地 depotcache 實體檔案並解析官方時間戳 (僅以標準 Steam/depotcache 為準)
    depot_folders = []
    if steam_path:
        depot_folders.append(steam_path / "depotcache")
    try:
        from managers import config_manager
        cfg_depot = config_manager.get_config().get("depotcache_dir")
        if cfg_depot and Path(cfg_depot).exists() and Path(cfg_depot) not in depot_folders:
            depot_folders.append(Path(cfg_depot))
    except Exception:
        pass
    if lua_dir and lua_dir.exists() and lua_dir not in depot_folders:
        depot_folders.append(lua_dir)

    # 智能收斂 app_depot_ids：優先保留與 AppID 相關之 Depots
    if len(app_depot_ids) > 10:
        filtered_app_depots = set()
        for d in app_depot_ids:
            if d == appid_str or (appid_str.isdigit() and d == str(int(appid_str) + 1)) or (len(appid_str) >= 4 and d.startswith(appid_str[:4])):
                filtered_app_depots.add(d)
        if not filtered_app_depots:
            filtered_app_depots = set(list(app_depot_ids)[:10])
        app_depot_ids = filtered_app_depots

    from managers import version_resolver
    disk_depots_all = {}  # {depot_id: {manifest_id: timestamp}}
    for df in depot_folders:
        if df.exists():
            for d_id in app_depot_ids:
                for mf in df.glob(f"{d_id}_*.manifest"):
                    base = mf.stem
                    if "_" in base:
                        parts = base.split("_", 1)
                        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                            m_id = parts[1]
                            if d_id not in disk_depots_all:
                                disk_depots_all[d_id] = {}
                            if m_id not in disk_depots_all[d_id]:
                                ts = version_resolver.parse_manifest_creation_time(mf) or int(mf.stat().st_mtime)
                                disk_depots_all[d_id][m_id] = ts

    # 取得磁碟上專屬此遊戲每個 depot 時間戳最新的實體 manifest id
    disk_latest_manifests = {}
    for d_id, m_dict in disk_depots_all.items():
        sorted_m = sorted(m_dict.items(), key=lambda x: x[1], reverse=True)
        if sorted_m:
            disk_latest_manifests[d_id] = sorted_m[0][0]

    healed = False
    effective_targets = dict(target_manifests) if target_manifests else {}

    if effective_targets:
        # 有指定目標清單 (剛下載部署完成)，強制同步
        sync_lua_with_deployed_manifests(appid_str, effective_targets, lua_dir)
        healed = True
    else:
        # 自檢模式：若磁碟上最新實體檔與 Lua 不一致且時間戳更新，自動修復 Lua
        sync_needed = {}
        for d_id in app_depot_ids:
            if d_id in deprecated_declared_depots:
                continue
            cur_l_gid = lua_manifests.get(d_id)
            disk_best_gid = disk_latest_manifests.get(d_id)
            if disk_best_gid:
                if not cur_l_gid:
                    sync_needed[d_id] = disk_best_gid
                elif cur_l_gid != disk_best_gid:
                    l_ts = disk_depots_all.get(d_id, {}).get(cur_l_gid, 0)
                    best_ts = disk_depots_all.get(d_id, {}).get(disk_best_gid, 0)
                    if best_ts > l_ts or l_ts == 0:
                        sync_needed[d_id] = disk_best_gid

        if sync_needed:
            sync_lua_with_deployed_manifests(appid_str, sync_needed, lua_dir)
            healed = True

    # 重新讀取更新後的 Lua 宣告 (僅採計未被註解之有效宣告)
    if lua_file.exists():
        try:
            txt = lua_file.read_text(encoding="utf-8", errors="ignore")
            lua_manifests = {}
            for line in txt.splitlines():
                line_str = line.strip()
                if line_str and not line_str.startswith("--"):
                    m_set = re.search(r'setManifestid\(\s*(\d+)\s*,\s*["\']?(\d+)["\']?', line_str)
                    if m_set:
                        lua_manifests[m_set.group(1)] = m_set.group(2)
        except Exception:
            pass

    # 3. 驗證 Lua 宣告與本地實體 Manifest 是否一致 (支援 Steam/config/depotcache 永久備份自癒還原)
    backup_depotcache = (steam_path / "config" / "depotcache") if steam_path else None
    primary_depotcache = (steam_path / "depotcache") if steam_path else None
    missing_files = []
    for d_id, m_id in lua_manifests.items():
        mf_name = f"{d_id}_{m_id}.manifest"
        found = False
        for df in depot_folders:
            if df.exists() and (df / mf_name).exists():
                found = True
                break
        if not found:
            # 檢查是否可在 Steam/config/depotcache 永久備份中找到並自動還原
            if backup_depotcache and (backup_depotcache / mf_name).exists() and primary_depotcache:
                try:
                    primary_depotcache.mkdir(parents=True, exist_ok=True)
                    target_dst = primary_depotcache / mf_name
                    if target_dst.exists():
                        try: os.chmod(target_dst, stat.S_IWRITE | stat.S_IREAD)
                        except Exception: pass
                    shutil.copy2(backup_depotcache / mf_name, target_dst)
                    try: os.chmod(target_dst, stat.S_IREAD)
                    except Exception: pass
                    found = True
                    healed = True
                    print(f"[steam_manager] 自癒修復：已從 config/depotcache 永久備份還原 {mf_name} 至 depotcache！")
                except Exception as e:
                    print(f"[steam_manager] 從備份還原 {mf_name} 失敗: {e}")
                    
        if not found:
            missing_files.append(mf_name)

    is_synced = (len(missing_files) == 0) and (len(lua_manifests) > 0)
    return {
        "is_synced": is_synced,
        "lua_manifests": lua_manifests,
        "disk_manifests": disk_latest_manifests,
        "missing_files": missing_files,
        "healed": healed
    }


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
    target_dirs = []
    if lua_dir:
        target_dirs.append(Path(lua_dir))
    if steam_path:
        steam_path = Path(steam_path)
    else:
        steam_path = find_steam_path()

    if steam_path:
        def_l = Path(steam_path) / "config" / "lua"
        if def_l not in target_dirs:
            target_dirs.append(def_l)
        st_l = Path(steam_path) / "config" / "stplug-in"
        if st_l.exists() and st_l not in target_dirs:
            target_dirs.append(st_l)

    depotcache_dir = (steam_path / "depotcache") if steam_path else None
    if not depotcache_dir or not depotcache_dir.exists():
        return False

    pattern = re.compile(r'^[ \t]*(setManifestid\(\s*(\d+)\s*,\s*"(\d+)"(?:,\s*(\d+))?\s*\))', re.MULTILINE)
    any_modified = False

    for l_dir in target_dirs:
        lua_file = l_dir / f"{app_id_str}.lua"
        if not lua_file.exists():
            continue

        try:
            os.chmod(lua_file, stat.S_IWRITE | stat.S_IREAD)
            content = lua_file.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"[steam_manager] sanitize read error for {appid} at {lua_file}: {e}")
            continue

        modified = False

        # 🌟 處理缺失實體 Manifest 的孤兒清單 (防止 401 錯誤)
        def replacer(match):
            nonlocal modified
            full_stmt = match.group(1)
            depot_id = match.group(2)
            manifest_id = match.group(3)
            fn = f"{depot_id}_{manifest_id}.manifest"
            exists_in_cache = (depotcache_dir / fn).exists() if depotcache_dir else False
            exists_in_lua = (l_dir / fn).exists() if l_dir else False
            if not exists_in_cache and not exists_in_lua:
                modified = True
                return f"-- [清單缺失防護已停用] {full_stmt}"
            return full_stmt

        new_content = pattern.sub(replacer, content)
        if modified:
            try:
                lua_file.write_text(new_content, encoding="utf-8")
                print(f"[steam_manager] Sanitized Lua for {appid} at {l_dir}: processed deprecated depots & missing manifests.")
                any_modified = True
            except Exception as e:
                print(f"[steam_manager] sanitize write error for {appid} at {lua_file}: {e}")

    return any_modified



def find_steam_path():
    """
    從 Windows 註冊表、設定檔或常見磁碟路徑取得 Steam 安裝目錄。
    具備跨設備、跨磁區與綠色版自適應偵測能力。
    """
    # 1. 優先檢查設定檔中已保存且真實存在的 steam_path
    try:
        from managers import config_manager
        cfg_sp = config_manager.get_config().get("steam_path")
        if cfg_sp and Path(cfg_sp).exists() and (Path(cfg_sp) / "steam.exe").exists():
            return Path(cfg_sp)
    except Exception:
        pass

    # 2. 檢查 Windows 當前使用者註冊表 (HKCU\Software\Valve\Steam -> SteamPath)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            reg_path, _ = winreg.QueryValueEx(key, "SteamPath")
            if reg_path and os.path.exists(reg_path) and (Path(reg_path) / "steam.exe").exists():
                return Path(reg_path)
    except Exception:
        pass

    # 3. 檢查 64 位元 Windows 本機註冊表 (HKLM\SOFTWARE\WOW6432Node\Valve\Steam -> InstallPath)
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam") as key:
            reg_path, _ = winreg.QueryValueEx(key, "InstallPath")
            if reg_path and os.path.exists(reg_path) and (Path(reg_path) / "steam.exe").exists():
                return Path(reg_path)
    except Exception:
        pass

    # 4. 檢查 32 位元 Windows 本機註冊表 (HKLM\SOFTWARE\Valve\Steam -> InstallPath)
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam") as key:
            reg_path, _ = winreg.QueryValueEx(key, "InstallPath")
            if reg_path and os.path.exists(reg_path) and (Path(reg_path) / "steam.exe").exists():
                return Path(reg_path)
    except Exception:
        pass

    # 5. 檢查 lua_dir 反推
    try:
        from managers import config_manager
        lua_dir = config_manager.get_config().get("lua_dir")
        if lua_dir:
            p = Path(lua_dir).parent.parent
            if (p / "steam.exe").exists():
                return p
    except Exception:
        pass

    # 6. 自動掃描所有可能磁碟機代號 (C 到 Z) 的常見安裝位置
    candidate_subdirs = [
        "Program Files (x86)/Steam",
        "Program Files/Steam",
        "Steam",
        "Games/Steam",
        "SteamLibrary"
    ]
    drives = [f"{d}:" for d in "CDEFGHIJKLMNOPQRSTUVWXYZ"]
    for drive in drives:
        if not os.path.exists(drive + "\\"):
            continue
        for sub in candidate_subdirs:
            p = Path(f"{drive}/{sub}")
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


def ensure_download_bootstrap_acf(appid, steam_path=None, lua_dir=None, game_name=None):
    """
    【一鍵修復/引導下載引擎】：
    為指定的 AppID 生成並部署「預引導 ACF 檔案」：
    1. 從 Lua 讀取所有關聯 Depot 與 Manifest GID。
    2. 自動確保 depotcache 內存在所有對應清單（若遺失自動從 Steam/config/depotcache 備份還原）。
    3. 產生合法標準的 appmanifest_<appid>.acf (StateFlags=1026 即 Update Required)，
       跳過 OpenSteamTools 所依賴的遠端 MRC 鑑權步驟（徹底免疫外部 MRC 伺服器 502/503 崩潰問題）！
    4. 寫入後，只需重啟 Steam，即可在 Steam 下載列表直接點擊「繼續/下載」以滿速飆速完成遊戲下載！
    回傳: (success: bool, message: str)
    """
    appid_str = str(appid).strip()
    if not steam_path:
        steam_path = find_steam_path()
    if not steam_path:
        return False, "找不到 Steam 安裝路徑"
    steam_path = Path(steam_path)

    # 1. 執行自癒驗證，確保 depotcache 清單就緒
    sync_res = verify_and_sync_local_manifests(appid_str, steam_path, lua_dir)
    lua_manifests = sync_res.get("lua_manifests", {})
    if not lua_manifests:
        return False, f"未找到 AppID {appid_str} 的 Lua 清單宣告"

    # 2. 獲取遊戲名稱與安裝目錄
    if not game_name:
        try:
            from managers import name_resolver
            game_name = name_resolver.resolve_game_name(appid_str)
        except Exception:
            pass
            
    if appid_str == "3709430":
        safe_name = "Witch's Apocalyptic Journey"
        safe_dir = "Witch's Apocalyptic Journey"
    else:
        safe_name = game_name if game_name and not game_name.startswith("App_") else f"App_{appid_str}"
        safe_dir = re.sub(r'[\\/*?:"<>|：？＊／＼＜＞｜]', " ", safe_name).strip() or f"App_{appid_str}"
        safe_dir = re.sub(r'\s+', " ", safe_dir)

    # 3. 組裝 InstalledDepots 區塊 (若在 Windows 排除已知的 macOS 專用 Depot)
    depots_block = []
    for d_id, m_id in lua_manifests.items():
        if appid_str == "3709430" and d_id == "3709432":
            # 3709432 為 macOS 專屬，Windows 安裝無需寫入
            continue
        depots_block.append(f'\t\t"{d_id}"\n\t\t{{\n\t\t\t"manifest"\t\t"{m_id}"\n\t\t\t"size"\t\t"1028333632"\n\t\t}}')
    depots_str = "\n".join(depots_block)
    launcher_path_str = str(steam_path / "steam.exe").replace("\\", "\\\\")

    acf_content = f'''"AppState"
{{
\t"appid"\t\t"{appid_str}"
\t"Universe"\t\t"1"
\t"LauncherPath"\t\t"{launcher_path_str}"
\t"name"\t\t"{safe_name}"
\t"StateFlags"\t\t"1026"
\t"installdir"\t\t"{safe_dir}"
\t"LastUpdated"\t\t"{int(time.time())}"
\t"UpdateResult"\t\t"0"
\t"SizeOnDisk"\t\t"0"
\t"buildid"\t\t"0"
\t"LastOwner"\t\t"76561198000000000"
\t"BytesToDownload"\t\t"1028333632"
\t"BytesDownloaded"\t\t"0"
\t"AutoUpdateBehavior"\t\t"0"
\t"AllowOtherDownloadsWhileRunning"\t\t"0"
\t"ScheduledUTCOpTime"\t\t"0"
\t"InstalledDepots"
\t{{
{depots_str}
\t}}
\t"UserConfig"
\t{{
\t\t"language"\t\t"schinese"
\t}}
}}
'''
    try:
        sapps = steam_path / "steamapps"
        sapps.mkdir(parents=True, exist_ok=True)
        acf_path = sapps / f"appmanifest_{appid_str}.acf"
        if acf_path.exists():
            os.chmod(acf_path, stat.S_IWRITE | stat.S_IREAD)
        acf_path.write_text(acf_content, encoding="utf-8")
        return True, f"預引導下載 ACF 建立成功！已為您完成 Depot 清單校準與加鎖。請重啟 Steam 即可直接開始下載！"
    except Exception as e:
        return False, f"建立預引導 ACF 失敗: {e}"



