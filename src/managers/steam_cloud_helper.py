# -*- coding: utf-8 -*-
"""
Steam 官方雲端開關自動防護模組 (Steam Cloud Auto-Disable Helper)
專門負責在啟動時自動掃描本機已安裝之 Lua 入庫遊戲，
並於 Steam 的 sharedconfig.vdf 中自動將其「官方 Steam 雲端」開關切換為關閉 (cloudenabled = 0)，
徹底根除 Steam 側邊欄「Steam 雲端發生錯誤」驚嘆號與警告圖示，同時不影響本工具的本地與工作坊存檔同步。
"""

import os
import re
from pathlib import Path
from typing import Dict, Any, List, Set, Optional

def get_steam_library_folders(steam_path: Path) -> List[Path]:
    """讀取 libraryfolders.vdf 獲取所有 Steam 庫目錄 (支援多硬碟多庫)"""
    folders = [steam_path]
    vdf_file = steam_path / "steamapps" / "libraryfolders.vdf"
    if not vdf_file.exists():
        return folders

    try:
        content = vdf_file.read_text(encoding="utf-8", errors="ignore")
        # 提取 "path" "\path\to\library"
        matches = re.findall(r'"path"\s*"([^"]+)"', content, re.IGNORECASE)
        for m in matches:
            clean_p = Path(m.replace("\\\\", "\\"))
            if clean_p.exists() and clean_p not in folders:
                folders.append(clean_p)
    except Exception as e:
        print(f"[SteamCloudHelper] 讀取 libraryfolders.vdf 異常: {e}")

    return folders


def get_all_installed_appids(steam_path: Path) -> Set[str]:
    """掃描所有 Steam 庫目錄中真實已安裝的 AppID"""
    installed = set()
    library_folders = get_steam_library_folders(steam_path)
    for lib in library_folders:
        steamapps = lib / "steamapps" if (lib / "steamapps").exists() else lib
        for acf in steamapps.glob("appmanifest_*.acf"):
            aid = acf.stem.replace("appmanifest_", "").strip()
            if aid.isdigit():
                installed.add(aid)
    return installed


def get_installed_lua_appids(steam_path: Path, only_installed: bool = True) -> Set[str]:
    """獲取本機已安裝且屬於 Lua 入庫的 AppID 清單"""
    lua_appids = set()
    
    # 1. 掃描 config/lua/
    lua_dir = steam_path / "config" / "lua"
    if lua_dir.exists():
        for f in lua_dir.glob("*.lua"):
            if f.stem.isdigit() and f.name != "manifest.lua":
                lua_appids.add(f.stem)

    # 2. 掃描 config/stplug-in/
    st_dir = steam_path / "config" / "stplug-in"
    if st_dir.exists():
        for f in st_dir.glob("*.lua"):
            if f.stem.isdigit() and f.name != "manifest.lua":
                lua_appids.add(f.stem)

    if not only_installed:
        return lua_appids

    installed = get_all_installed_appids(steam_path)
    # 取交集：只針對「真實已安裝」的 Lua 遊戲
    return lua_appids.intersection(installed)


def update_single_sharedconfig(vdf_path: Path, target_appids: Set[str]) -> int:
    """
    精準安全更新單一 sharedconfig.vdf，將 target_appids 的 cloudenabled 設為 0
    保證保留所有原有縮排、大括號與設定項目。
    """
    if not vdf_path.exists() or not target_appids:
        return 0

    try:
        content = vdf_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return 0

    # 尋找 "Apps" 區塊，若不存在則在 Software -> Valve -> "Steam" 下自動初始化
    apps_match = re.search(r'("Apps"\s*\{)', content, re.IGNORECASE)
    if not apps_match:
        steam_match = re.search(r'("Steam"\s*\{)', content, re.IGNORECASE)
        if steam_match:
            steam_end = steam_match.end()
            content = content[:steam_end] + '\n\t\t\t\t"Apps"\n\t\t\t\t{\n\t\t\t\t}' + content[steam_end:]
            apps_match = re.search(r'("Apps"\s*\{)', content, re.IGNORECASE)
        else:
            return 0

    if not apps_match:
        return 0

    modified_count = 0
    apps_start_pos = apps_match.end()
    new_entries = []

    for aid in target_appids:
        # 1. 檢查是否已有該 appid 且包含 cloudenabled
        app_full_pattern = re.compile(r'("' + re.escape(aid) + r'"\s*\{[^}]*\})', re.DOTALL)
        m = app_full_pattern.search(content)


        if m:
            old_block = m.group(1)
            if '"cloudenabled"' in old_block:
                # 若 cloudenabled 不是 "0"，替換為 "0"
                if re.search(r'"cloudenabled"\s*"0"', old_block):
                    continue  # 已經是 0，略過
                new_block = re.sub(r'"cloudenabled"\s*"[^"]*"', '"cloudenabled"\t\t"0"', old_block)
                content = content.replace(old_block, new_block, 1)
                modified_count += 1
            else:
                # 有 block 但沒有 cloudenabled，插入 cloudenabled
                inner_idx = old_block.find("{") + 1
                new_block = old_block[:inner_idx] + '\n\t\t\t\t\t"cloudenabled"\t\t"0"' + old_block[inner_idx:]
                content = content.replace(old_block, new_block, 1)
                modified_count += 1
        else:
            # 完全沒有該 app 區塊，構建新項目
            new_entries.append(f'\n\t\t\t\t\t"{aid}"\n\t\t\t\t\t{{\n\t\t\t\t\t\t"cloudenabled"\t\t"0"\n\t\t\t\t\t}}')
            modified_count += 1

    if new_entries:
        insert_str = "".join(new_entries)
        content = content[:apps_start_pos] + insert_str + content[apps_start_pos:]

    if modified_count > 0:
        try:
            # 建立備份
            bak = vdf_path.with_suffix(".vdf.bak")
            if not bak.exists():
                bak.write_text(vdf_path.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
            vdf_path.write_text(content, encoding="utf-8")
        except Exception as e:
            print(f"[SteamCloudHelper] 寫入 {vdf_path} 失敗: {e}")
            return 0

    return modified_count


def disable_official_cloud_for_single_appid(steam_path: Path, appid: str) -> bool:
    """
    動態寫入單一 AppID：在入庫或生成新 Lua 檔案的當下即時呼叫，
    將該 AppID 自動寫入本機所有 Steam 帳號的 sharedconfig.vdf 中 (cloudenabled = 0)。
    """
    if not steam_path or not steam_path.exists() or not str(appid).isdigit():
        return False

    userdata_dir = steam_path / "userdata"
    if not userdata_dir.exists():
        return False

    target_appids = {str(appid)}
    success = False

    for user_folder in userdata_dir.iterdir():
        if user_folder.is_dir() and user_folder.name.isdigit():
            vdf_file = user_folder / "7" / "remote" / "sharedconfig.vdf"
            if vdf_file.exists():
                mod = update_single_sharedconfig(vdf_file, target_appids)
                if mod > 0:
                    success = True

    if success:
        print(f"[SteamCloudHelper] [RealtimeInject] 已成功為新入庫遊戲 AppID {appid} 動態關閉官方 Steam 雲端！")
    return success


def disable_official_cloud_for_installed_lua_games(steam_path: Path, only_installed: bool = False) -> Dict[str, Any]:
    """
    主進入點：自動檢查並關閉本機 Lua 入庫遊戲的 Steam 官方雲端功能。
    預設 only_installed=False 實現「全量預先免疫」：無論遊戲是否已下載安裝本體，
    只要本機有 Lua 檔案，就預先在 sharedconfig.vdf 中寫入 cloudenabled = 0，
    未來在 Steam 內下載與啟動時 100% 杜絕報錯！
    """
    if not steam_path or not steam_path.exists():
        return {"ok": False, "msg": "Steam 目錄不存在", "modified_count": 0, "games": []}

    target_appids = get_installed_lua_appids(steam_path, only_installed=only_installed)
    if not target_appids:
        return {"ok": True, "msg": "未檢測到需要處理的 Lua 遊戲", "modified_count": 0, "games": []}

    userdata_dir = steam_path / "userdata"
    if not userdata_dir.exists():
        return {"ok": False, "msg": "找不到 Steam/userdata 目錄", "modified_count": 0, "games": []}

    total_modified = 0
    users_processed = 0

    for user_folder in userdata_dir.iterdir():
        if user_folder.is_dir() and user_folder.name.isdigit():
            vdf_file = user_folder / "7" / "remote" / "sharedconfig.vdf"
            if vdf_file.exists():
                mod = update_single_sharedconfig(vdf_file, target_appids)
                if mod > 0:
                    total_modified += mod
                users_processed += 1

    from managers.name_resolver import resolve_game_name
    game_names = [f"{resolve_game_name(aid)} ({aid})" for aid in target_appids]

    print(f"[SteamCloudHelper] [AutoFix] 已為 {len(target_appids)} 款 Lua 入庫遊戲完成官方雲端防護 (共更新 {total_modified} 個設定項目)")
    return {
        "ok": True,
        "modified_count": total_modified,
        "target_appids_count": len(target_appids),
        "appids": list(target_appids),
        "games": game_names,
        "msg": f"已成功為 {len(target_appids)} 款 Lua 遊戲關閉官方雲端開關，徹底杜絕 Steam 雲端錯誤！"
    }

