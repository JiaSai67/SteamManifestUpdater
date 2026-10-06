# -*- coding: utf-8 -*-
"""
SMU Modular Handler Component
自動解耦之專屬業務處理模組
"""
import os
import sys
import re
import json
import time
import shutil
import urllib.request
import urllib.parse
import subprocess
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional
import concurrent.futures

from managers import config_manager
from managers import steam_manager
from managers import unified_manifest_manager
from managers import name_resolver

class SearchHandler:
    def search(self, q: str) -> List[Dict[str, Any]]:
        """
        搜尋遊戲：支援純 AppID、中文名稱、英文名稱 (全面繁體中文化)
        """
        from utils.tw_converter import sanitize_game_name
        q = str(q).strip()
        if not q: return []

        results = []
        # 若是 AppID 數字
        if q.isdigit():
            # 優先從快取找
            cache_file = Path(__file__).parent.parent / "data" / "game_cache.json"
            if cache_file.exists():
                try:
                    c_data = json.loads(cache_file.read_text(encoding="utf-8"))
                    if q in c_data:
                        c_info = c_data[q]
                        return [{
                            "appid": q,
                            "name": sanitize_game_name(c_info.get("name", f"App_{q}"), q),
                            "image": c_info.get("header_image", f"https://cdn.cloudflare.steamstatic.com/steam/apps/{q}/header.jpg")
                        }]
                except Exception:
                    pass

            # 嘗試反查名稱
            name = name_resolver.resolve_game_name(q, steam_path=self._steam_path)
            if not name or name == "未知遊戲":
                # 嘗試在線 Steam appdetails 獲取精確官方繁體名
                try:
                    url = f"https://store.steampowered.com/api/appdetails?appids={q}&l=tchinese&cc=TW"
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=4) as resp:
                        d = json.loads(resp.read().decode("utf-8"))
                        if d.get(q, {}).get("success"):
                            data = d[q].get("data", {})
                            name = data.get("name", f"App_{q}")
                except Exception:
                    name = f"App_{q}"

            return [{
                "appid": q,
                "name": sanitize_game_name(name, q),
                "image": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{q}/header.jpg"
            }]

        # 透過 Steam 官方 storesearch API 搜尋 (使用台灣繁體地區碼 l=tchinese&cc=TW)
        try:
            url = f"https://store.steampowered.com/api/storesearch/?term={urllib.parse.quote(q)}&l=tchinese&cc=TW"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("items", [])
                for it in items:
                    appid_str = str(it.get("id"))
                    name_str = sanitize_game_name(it.get("name", f"App_{appid_str}"), appid_str)
                    results.append({
                        "appid": appid_str,
                        "name": name_str,
                        "image": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid_str}/header.jpg"
                    })
        except Exception as e:
            print(f"[WebApi] search online error: {e}")

        # 若線上 API 暫時連不上，嘗試搜尋本地與已知清單
        if not results:
            known = name_resolver._load_cache() or {}
            for aid, n in known.items():
                tw_n = sanitize_game_name(str(n), str(aid))
                if q.lower() in tw_n.lower() or q.lower() in str(aid):
                    results.append({
                        "appid": str(aid),
                        "name": tw_n,
                        "image": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{aid}/header.jpg"
                    })
                    if len(results) >= 20: break

        return results

    def browse_games(self, offset: int = 0, limit: int = 40) -> Dict[str, Any]:
        """首頁遊戲推薦瀏覽清單 (支援無限滾動加載，100% 繁體中文展示)"""
        from utils.tw_converter import sanitize_game_name
        # 精選熱門遊戲池作為瀏覽備用 (台灣繁體中文官方標題)
        featured_pool = [
            ("2358720", "Black Myth: Wukong (黑神話：悟空)"),
            ("1245620", "ELDEN RING (艾爾登法環)"),
            ("1091500", "Cyberpunk 2077 (電馭叛客 2077)"),
            ("1623730", "Palworld (幻獸帕魯)"),
            ("1086940", "Baldur's Gate 3 (柏德之門 3)"),
            ("1817070", "Marvel’s Spider-Man Remastered (漫威蜘蛛人)"),
            ("2436940", "Sephiria (賽菲莉婭)"),
            ("974480", "Echoes of Mystralia (秘奧回響)"),
            ("1805110", "Solarpunk (太陽龐克：浮島家園)"),
            ("2285550", "Doloc Town (多洛可小鎮)"),
            ("1374490", "RuneScape: Dragonwilds (符文世界：龍之荒野)"),
            ("1206560", "WorldBox - God Simulator (世界盒子)"),
            ("1001270", "Kebab Chefs! - Restaurant Simulator (烤串大廚！餐廳模擬器)"),
            ("386940", "Ultimate Chicken Horse (超級雞馬)"),
            ("264710", "Subnautica (深海迷航)"),
            ("1172470", "Apex Legends (Apex 英雄)"),
            ("730", "Counter-Strike 2"),
            ("570", "Dota 2"),
            ("271590", "Grand Theft Auto V (俠盜獵車手 V)"),
            ("1174180", "Red Dead Redemption 2 (碧血狂殺 2)"),
            ("553850", "HELLDIVERS 2 (絕地戰兵 2)"),
            ("252490", "Rust (腐蝕)"),
            ("289070", "Sid Meier's Civilization VI (文明帝國 VI)"),
            ("105600", "Terraria (泰拉瑞亞)"),
            ("294100", "RimWorld (邊緣世界)"),
            ("1145360", "Hades (黑帝斯)"),
            ("3624140", "Ascend of Souls"),
            ("2697940", "Ascend to ZERO"),
            ("3934270", "Star Odyssey"),
            ("4005220", "Chronicles of Magic")
        ]

        total = len(featured_pool)
        start = min(offset, total)
        end = min(start + limit, total)
        items = []

        cache_file = Path(__file__).parent.parent / "data" / "game_cache.json"
        game_cache = {}
        if cache_file.exists():
            try:
                game_cache = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        for aid, nm in featured_pool[start:end]:
            c_info = game_cache.get(str(aid), {})
            img = c_info.get("header_image", f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{aid}/header.jpg")
            c_name = sanitize_game_name(c_info.get("name", nm), aid)
            items.append({
                "appid": str(aid),
                "name": c_name,
                "image": img
            })

        return {
            "games": items,
            "items": items,
            "total": total,
            "offset": offset,
            "limit": limit
        }

    def get_installed_appids(self) -> List[str]:
        """取得目前本地已入庫的全部 AppID 清單 (秒級回傳，供首頁對比勾選圖示)"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp: return []
        lua_dir = Path(sp) / "config" / "lua"
        if not lua_dir.exists(): return []
        return [f.stem for f in lua_dir.glob("*.lua") if f.name != "manifest.lua" and f.stem.isdigit()]

    def get_manifest_history(self, appid: str) -> Dict[str, Any]:
        """
        獲取遊戲詳細資訊與以 SteamDB 官方版本鏈排序之 Manifest 版本歷史：
        - 絕對以 SteamDB (SteamCMD PICS) 官方最新 Manifest GID 為最高基準與排序首位
        - 本地數據與雲端數據基於 SteamDB 抓下來的真實 Manifest 版本進行對齊
        - 嚴格杜絕偽造 GID 與以日期推斷新舊，只呈現真實驗證存在之版本
        - 標明本地版本是否落後於 SteamDB 官方最新版，以及雲端倉庫是否已同步最新版
        """
        from datetime import datetime
        from utils.tw_converter import sanitize_game_name
        from managers import version_resolver, unified_manifest_manager, steamdb_history_manager

        appid_str = str(appid).strip()
        sp = self._steam_path or steam_manager.find_steam_path()

        def _push_step(pct: int, title: str, desc: str, step: int):
            if getattr(self, "_window", None):
                try:
                    js = f"window.onDetailStepProgress && window.onDetailStepProgress({json.dumps(appid_str)}, {pct}, {json.dumps(title)}, {json.dumps(desc)}, {step});"
                    self._window.evaluate_js(js)
                except Exception:
                    pass

        # 🌟 階段 1：探測 SteamCMD 官方協議 (14%)
        _push_step(14, "檢測 SteamCMD 官方協議與 Public 分支...", "連接 Valve PICS 伺服器，核驗最新 Manifest GID", 1)

        # 1. 遊戲名稱
        name = name_resolver.resolve_game_name(appid_str, steam_path=sp)
        res_name = sanitize_game_name(name, appid_str)

        res = {
            "appid": appid_str,
            "name": res_name,
            "image": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid_str}/header.jpg",
            "has_update": False,
            "best_source": "none",
            "best_source_name": "無可用線上源",
            "depots": []
        }

        # 0. 🌟 階段 2：檢查更新前置作業：本地 Lua 與實體 ACF 校驗 (28%)
        _push_step(28, "校驗本地 Manifest 與 ACF 檔案狀態...", "核驗實體 depotcache 二進位檔、已下載清單與補丁映射", 2)
        local_sync = steam_manager.verify_and_sync_local_manifests(appid_str, steam_path=sp)
        res["local_sync"] = local_sync

        # 2. 查詢 SteamDB (SteamCMD 官方數據庫) 獲取官方最新 Manifest
        steamdb_info = version_resolver.fetch_steamdb_manifests(appid_str, timeout=4)
        steamdb_manifests = steamdb_info.get("manifests", {})
        steamdb_date_str = steamdb_info.get("date_str", "")
        steamdb_ts = steamdb_info.get("timestamp", 0)
        steamdb_build_id = steamdb_info.get("build_id", "")
        try:
            steamdb_date_fmt = datetime.strptime(steamdb_date_str, "%Y-%m-%d").strftime("%y-%m-%d") if steamdb_date_str else "26-09-10"
        except Exception:
            steamdb_date_fmt = "26-09-10"

        # 🌟 階段 3：對齊 SteamDB 官方歷史版本鏈 (42%)
        _push_step(42, "對齊 SteamDB 官方歷史版本鏈...", "檢索官方 Depots 完整鏈，核實發布日期與版本號", 3)

        # 🌟 智慧探針比對：若本地快取尚未建立或有新版本，在背景非同步啟動 SteamDB 更新，UI 即時零延遲呈現
        from managers import steamdb_crawler
        first_gid = next(iter(steamdb_manifests.values()), "") if steamdb_manifests else ""
        if not steamdb_crawler.is_steamdb_cache_fresh(appid_str, steamcmd_latest_gid=first_gid):
            all_depot_keys = list(steamdb_manifests.keys())
            if all_depot_keys:
                import threading
                def _bg_steamdb_sync():
                    try:
                        steamdb_crawler.update_app_steamdb_history(
                            appid_str,
                            all_depot_keys,
                            steamdb_manifests,
                            steamcmd_date_str
                        )
                    except Exception as ce:
                        print(f"[web_api] App {appid_str} SteamDB 背景更新異常: {ce}")
                threading.Thread(target=_bg_steamdb_sync, daemon=True).start()

        res["steamdb_timeout"] = False
        res["steamdb_error"] = ""

        # 3. 本地已校準 Depots (讀取校準後的 Lua 與實體檔狀態)
        local_status = steam_manager.get_lua_manifest_status(appid_str, steam_path=sp)
        declared = local_status.get("declared_manifests", [])
        declared_dict = {str(d): str(m) for d, m in declared if str(m) != "0"}

        # 🌟 階段 4：檢測 4 域之一 Ryuu 平台雲端庫存 (56%)
        _push_step(56, "檢測 Ryuu 平台雲端庫存狀態...", "核對線上開源庫存與最新 Manifest 收錄狀態", 4)
        unified_mgr = unified_manifest_manager.get_unified_manifest_manager()
        search_res = unified_mgr.search_all_sources(appid_str, timeout=4, steamdb_manifests=steamdb_manifests)
        best_source = search_res.get("best_source", "none")
        best_reason = search_res.get("best_reason", "")

        ryuu_info = search_res.get("ryuu", {})
        ryuu_depots = ryuu_info.get("depots", {})
        ryuu_branches = ryuu_info.get("branch_manifests", {})

        source_name = "本地"
        if best_source == "ryuu": source_name = "Ryuu"
        elif best_source == "luatools": source_name = "LuaTools"

        res["best_source"] = best_source
        res["best_source_name"] = source_name

        # 彙整所有涉及的核心 Depot ID (優先 SteamDB 官方 Depots + Ryuu 實體在庫 Depots + 本地已快取實體 Depots)
        cached_manifest_files = set()
        if sp:
            depot_dir = Path(sp) / "depotcache"
            if depot_dir.exists():
                try:
                    cached_manifest_files.update(os.listdir(depot_dir))
                except Exception:
                    pass

        candidate_depots = []
        def add_depot(d):
            d_str = str(d).strip()
            if d_str and d_str.isdigit() and d_str not in candidate_depots:
                candidate_depots.append(d_str)

        # 優先收集三方來源真實驗證存在之實體 Depot (避免空殼 AppID 造成幽靈標籤)
        real_depots = []
        def add_real(d):
            d_str = str(d).strip()
            if d_str and d_str.isdigit() and d_str not in real_depots:
                real_depots.append(d_str)

        # a. 若 appid_str 本身在 SteamDB / Ryuu / 本地中存在實體 Manifest，則置頂首位
        if (appid_str in steamdb_manifests or appid_str in ryuu_depots or str(declared_dict.get(appid_str, "0")) != "0"):
            add_real(appid_str)

        # b. SteamDB 官方包含之 Depots
        for d in steamdb_manifests:
            add_real(d)

        # 收集官方或分支認可之有效 Depot 清單
        valid_active_depots = set(steamdb_manifests.keys())
        for b_name, b_val in ryuu_branches.items():
            if isinstance(b_val, dict):
                for d in b_val.get("depots", {}).keys():
                    valid_active_depots.add(str(d).strip())
        for dlc_id in ryuu_info.get("dlc", []):
            valid_active_depots.add(str(dlc_id).strip())
        for dep_id in ryuu_info.get("depot_dlc_map", {}).keys():
            valid_active_depots.add(str(dep_id).strip())

        # c. Ryuu / 雲端實體在庫 Depots (排除本地未宣告且官方已除名的孤立過期檔案)
        for d in ryuu_depots:
            d_s = str(d).strip()
            if d_s in valid_active_depots or d_s in declared_dict:
                add_real(d_s)

        for b_name, b_val in ryuu_branches.items():
            if isinstance(b_val, dict):
                for d in b_val.get("depots", {}).keys():
                    add_real(d)

        # d. 本地已宣告且不為 0 之實體 Depots
        for did, mid in declared:
            if str(mid) != "0":
                add_real(did)

        if real_depots:
            for d in real_depots:
                add_depot(d)
        else:
            # 備援：若各方皆無任何實體 Depot 記錄，才退回使用 appid 候選猜測
            cand_dids = [appid_str, f"{int(appid_str)+1}" if appid_str.isdigit() else ""]
            if appid_str == "3934720": cand_dids.extend(["3934271", "3934721"])
            for d in cand_dids:
                if d: add_depot(d)

        if not candidate_depots:
            candidate_depots = [appid_str]

        # 智能收斂：最多保留前 15 個核心 Depot，杜絕雜訊與卡死
        depot_ids = candidate_depots[:15]

        # 🌟 拓撲辨識：檢查是否有已棄置或更名的 Depot
        topo = version_resolver.identify_depot_topology(
            appid_str,
            local_manifests=declared_dict,
            official_manifests=steamdb_manifests,
            ryuu_info=ryuu_info,
            steamdb_info=steamdb_info
        )
        res["has_deprecated"] = topo.get("has_deprecated", False)
        res["deprecated_depots"] = topo.get("deprecated_depots", {})
        res["replaced_map"] = topo.get("replaced_map", {})

        needs_topology_migration = False
        if topo.get("has_deprecated"):
            res["replaced_by"] = topo.get("primary_active_depot", "")
            replaced_map = topo.get("replaced_map", {})
            for d_old, d_new in replaced_map.items():
                if d_new:
                    l_m_new = declared_dict.get(str(d_new))
                    t_m_new = steamdb_manifests.get(str(d_new)) or ryuu_depots.get(str(d_new))
                    if not l_m_new or (t_m_new and str(l_m_new) != str(t_m_new)):
                        needs_topology_migration = True
                        break

        res["needs_topology_migration"] = needs_topology_migration
        if needs_topology_migration:
            res["has_update"] = True

        # 5. 狀態檢查：檢測 4 個網域與雲端補丁庫 (a. Ryuu, b. Google Drive, c. Online-Fix, d. ZeiGames)
        # a. Ryuu 平台版本狀態判定 (精確區分主程式 Depot 與 DLC Depot)
        ryuu_available = bool(ryuu_info.get("available") and ryuu_depots)
        main_depot_id = str(depot_ids[0]) if depot_ids else appid_str

        # 尋找主程式 Manifest GID (優先匹配 main_depot_id，其次取第一個)
        ryuu_manifest_repr = str(ryuu_depots.get(main_depot_id) or "")
        if not ryuu_manifest_repr and ryuu_depots:
            ryuu_manifest_repr = str(next(iter(ryuu_depots.values())))

        main_s_gid = steamdb_manifests.get(main_depot_id)
        main_r_gid = ryuu_depots.get(main_depot_id)
        main_l_gid = declared_dict.get(main_depot_id)

        # 主程式是否落後 SteamDB 官方最新
        is_main_outdated = bool(main_s_gid and main_r_gid and str(main_s_gid) != str(main_r_gid))
        # 主程式是否與本地一致
        is_main_same_as_local = bool(main_l_gid and main_r_gid and str(main_l_gid) == str(main_r_gid))

        # 是否有任何 Depot 落後 (例如主程式最新但 DLC 稍慢)
        has_any_outdated_depot = False
        all_depots_same_as_local = True

        if ryuu_available and ryuu_depots:
            for did, r_gid in ryuu_depots.items():
                s_gid = steamdb_manifests.get(str(did))
                l_gid = declared_dict.get(str(did))
                if s_gid and str(s_gid) != str(r_gid):
                    has_any_outdated_depot = True
                if not l_gid or str(l_gid) != str(r_gid):
                    all_depots_same_as_local = False

        ryuu_status = {
            "name": "Ryuu 平台",
            "available": ryuu_available,
            "manifest_id": ryuu_manifest_repr if (ryuu_available and ryuu_manifest_repr) else "無檔案 (未收錄)",
            "depots": ryuu_depots,
            "is_outdated": is_main_outdated,  # 嚴格以主程式為準
            "is_same_as_local": is_main_same_as_local,
            "has_any_outdated_depot": has_any_outdated_depot,
            "all_depots_same_as_local": all_depots_same_as_local,
            "time": ryuu_info.get("time", "即時在庫")
        }

        # b. 🌟 階段 5：檢測 4 域之二 Google Drive (網盤補丁庫) (70%)
        _push_step(70, "校驗 Google Drive 網盤補丁庫...", "檢查專用/聯機補丁收錄與本地部署狀態", 5)
        from managers import onlinefix_manager
        # 在點擊遊戲小卡/開啟詳細資訊時，發出向 Google Drive 讀取的請求 (allow_network=True)
        gdrive_sources = onlinefix_manager.get_patch_sources(target_app_id=appid_str, target_app_name=res_name, allow_network=True)
        gdrive_item = gdrive_sources.get(appid_str, {})
        has_gdrive = bool(gdrive_item.get("cloud_rar") or gdrive_item.get("cloud_lua") or gdrive_item.get("local_lua"))
        is_deployed = onlinefix_manager.is_patch_deployed_locally(appid_str)

        if gdrive_item.get("cloud_rar"):
            gdrive_val_text = gdrive_item["cloud_rar"].get("path", "已上傳補丁壓縮檔")
        elif gdrive_item.get("cloud_lua") or gdrive_item.get("local_lua"):
            gdrive_val_text = "已配置專用 Lua 補丁"
        else:
            gdrive_val_text = "無補丁檔案"

        gdrive_status = {
            "name": "Google Drive 補丁庫",
            "available": has_gdrive,
            "is_deployed": is_deployed,
            "deploy_status": "已部署" if is_deployed else "未部署",
            "details": gdrive_val_text,
            "drive_name": gdrive_item.get("drive_name", "官方補丁庫")
        }

        # c. 🌟 階段 6：檢測 4 域之三 Online-Fix (84%) & 階段 7：ZeiGames (94%)
        _push_step(84, "檢索 Online-Fix 聯機補丁庫...", "搜尋專用聯機補丁並驗證下載鏈接有效性", 6)
        from api import web_patch_checker
        cache_file = Path(__file__).parent.parent / "data" / "game_cache.json"
        eng_name = ""
        if cache_file.exists():
            try:
                gc = json.loads(cache_file.read_text(encoding="utf-8"))
                eng_name = gc.get(appid_str, {}).get("english_name", "") or gc.get(appid_str, {}).get("name_en", "")
            except Exception:
                pass
        official_eng_name = steamdb_info.get("english_name", "") if isinstance(steamdb_info, dict) else ""
        search_query_name = official_eng_name or eng_name or res_name

        def _on_web_patch_step(s):
            if s == "zeigames":
                _push_step(94, "檢索 ZeiGames 專用修復補丁...", "搜尋專用修復補丁並過濾失效鏈接", 7)

        web_patches = web_patch_checker.check_all_web_patches(search_query_name, appid=appid_str, on_step=_on_web_patch_step)
        of_info = web_patches.get("onlinefix", {})
        zg_info = web_patches.get("zeigames", {})
        _push_step(96, "聚合 4 域數據與版本鏈對齊完成...", "各平台數據校準完畢，即將揭曉詳細資訊", 7)

        res["status_check"] = {
            "ryuu": ryuu_status,
            "gdrive": gdrive_status,
            "onlinefix": of_info,
            "zeigames": zg_info
        }
        res["dual_sources"] = res["status_check"]

        # 6. 逐個 Depot 建構對齊 SteamDB 的歷史列表
        depots_result = []
        any_depot_has_real_update = False

        for idx, did_str in enumerate(depot_ids):
            mid_str = declared_dict.get(did_str)
            sdb_gid = steamdb_manifests.get(did_str)
            if not sdb_gid:
                sdb_gid = ryuu_info.get("steamdb_target", {}).get(did_str) or ryuu_branches.get("public", {}).get("depots", {}).get(did_str)
            cur_ryuu_gid = ryuu_depots.get(did_str)

            dep_info = topo.get("deprecated_depots", {}).get(did_str, {})
            is_deprecated = bool(dep_info)
            replaced_by = dep_info.get("replaced_by", "")

            is_main = (idx == 0)
            depot_name = f"舊主程式 ({did_str})" if (is_deprecated and replaced_by) else (f"主程式 ({did_str})" if is_main else f"DLC Depot ({did_str})")
            if is_deprecated:
                depot_has_update = False
                # 🌟 核心規則：官方已棄置之 Depot 絕不參與版本更新比對，絕不判定為需要更新

            # 解析本地實體檔案之真實日期 (依據二進位 Creation Time)
            local_date_str = None
            if sp and mid_str:
                depot_dir = Path(sp) / "depotcache"
                if depot_dir.exists():
                    mf = depot_dir / f"{did_str}_{mid_str}.manifest"
                    if mf.exists():
                        ts = version_resolver.parse_manifest_creation_time(mf)
                        if ts:
                            local_date_str = datetime.fromtimestamp(ts).strftime("%y-%m-%d")
            if not local_date_str:
                local_date_str = "本地歷史版本"

            depot_history = []
            seen_gids = set()

            real_latest_gid = str(sdb_gid or cur_ryuu_gid or "").strip()

            # 判斷本地是否已與 SteamDB / 線上官方最新對齊
            is_local_aligned = bool(real_latest_gid and mid_str and str(mid_str) == real_latest_gid)
            # 判斷 Ryuu 平台是否有收錄此 Depot
            ryuu_has_this_depot = bool(ryuu_info.get("available") and cur_ryuu_gid)

            depot_has_update = False

            # A. 導入 SteamDB 完整歷史管理器 (優先讀取獨立快取，嚴格以 real_latest_gid 為最新首位)
            sdb_history_list = steamdb_history_manager.get_depot_manifest_history(
                did_str,
                steam_path=sp,
                latest_gid=real_latest_gid,
                current_gid=mid_str,
                base_date_str=steamdb_date_str or steamdb_date_fmt,
                auto_generate=True,
                appid=appid_str
            )
            if sdb_history_list:
                for idx_h, s_item in enumerate(sdb_history_list):
                    h_gid = str(s_item.get("manifest_id", "")).strip()
                    if not h_gid or h_gid in seen_gids:
                        continue

                    is_h_cur = bool(mid_str and str(mid_str) == h_gid)
                    # 嚴格判定：只有真實吻合官方最新 GID (或無最新 GID 時的首項) 才被視為官方最新 (若已被棄置則絕非官方最新)
                    is_official_latest = (not is_deprecated) and (bool(real_latest_gid and h_gid == real_latest_gid) or (not real_latest_gid and idx_h == 0))
                    h_date_fmt = s_item.get("date") or s_item.get("date_str") or steamdb_date_fmt
                    h_branch = s_item.get("branch", "public")

                    # 檢查此 GID 是否在 Ryuu 平台中可供下載
                    is_in_ryuu = bool(ryuu_has_this_depot and str(cur_ryuu_gid) == h_gid)

                    # 🌟 依需求完全移除相對時間與「歷史版本」四字，只保留精準日期與來源
                    meta_desc = f"{h_date_fmt}．SteamDB"
                    if is_official_latest:
                        meta_desc += " 最新"
                    elif h_branch and h_branch not in ["public", "local_storage"]:
                        meta_desc += f" 分支 ({h_branch})"
                    else:
                        meta_desc += f" #{idx_h+1}"

                    if is_official_latest:
                        if is_h_cur:
                            depot_history.append({
                                "manifest_id": h_gid,
                                "date": h_date_fmt,
                                "meta": meta_desc + " (本地已同步)",
                                "is_current": True,
                                "is_pending": False,
                                "tag": "💾 本地當前 (SteamCMD)",
                                "is_official": True
                            })
                        elif is_in_ryuu:
                            # 只有當 Ryuu 真正有此檔案，且本地尚未同步時，才標註為可更新！
                            depot_has_update = True
                            any_depot_has_real_update = True
                            depot_history.append({
                                "manifest_id": h_gid,
                                "date": h_date_fmt,
                                "meta": meta_desc,
                                "is_current": False,
                                "is_pending": True,
                                "tag": "⚡ 可更新 (SteamCMD)",
                                "is_official": True
                            })
                        else:
                            # 遊戲未上市、Ryuu 未收錄或 Ryuu 尚為舊版
                            is_depot_ryuu_old = bool(ryuu_has_this_depot and cur_ryuu_gid and str(cur_ryuu_gid) != str(h_gid))
                            tag_sdb = "SteamDB 最新 (線上庫未收錄)" if is_depot_ryuu_old else "SteamDB 最新"
                            depot_history.append({
                                "manifest_id": h_gid,
                                "date": h_date_fmt,
                                "meta": meta_desc,
                                "is_current": False,
                                "is_pending": False,
                                "tag": tag_sdb,
                                "is_official": True
                            })
                    else:
                        if is_h_cur:
                            cur_tag = "🔴 本地舊版 (官方已棄置)" if is_deprecated else ("💾 本地當前 (Ryuu 在庫)" if (ryuu_has_this_depot and str(cur_ryuu_gid) == h_gid) else "💾 本地當前 (舊版)")
                            depot_history.append({
                                "manifest_id": h_gid,
                                "date": h_date_fmt,
                                "meta": meta_desc + " (本地當前)",
                                "is_current": True,
                                "is_pending": False,
                                "tag": cur_tag,
                                "is_official": True
                            })
                        else:
                            b_tag = f"分支 ({h_branch})" if h_branch not in ["public", "local_storage"] else f"#{idx_h+1} (SteamDB)"
                            depot_history.append({
                                "manifest_id": h_gid,
                                "date": h_date_fmt,
                                "meta": meta_desc,
                                "is_current": False,
                                "is_pending": False,
                                "tag": b_tag,
                                "is_official": True
                            })
                    seen_gids.add(h_gid)

            # B. 補充 Ryuu 實體庫存與分支版本
            for b_name, b_val in ryuu_branches.items():
                if isinstance(b_val, dict):
                    b_depots = b_val.get("depots", {})
                    if did_str in b_depots:
                        b_gid = str(b_depots[did_str])
                        if b_gid and b_gid not in seen_gids:
                            is_b_cur = bool(mid_str and str(mid_str) == b_gid)
                            # 🌟 只有 Ryuu 實體檔案庫存中真正存在該版本且未被棄置時，才能觸發更新
                            is_in_real_ryuu = bool(ryuu_has_this_depot and str(cur_ryuu_gid) == b_gid)
                            can_up = bool(is_in_real_ryuu and not is_b_cur and not is_deprecated)

                            if can_up:
                                depot_has_update = True
                                any_depot_has_real_update = True
                                tag = "⚡ 可更新至此版本 (Ryuu 在庫)" if (b_name == "public") else f"⚡ 可更新 (分支 {b_name})"
                            elif is_b_cur:
                                tag = "💾 本地當前版本 (Ryuu 最新)" if is_in_real_ryuu else "💾 本地當前版本"
                            elif b_gid == str(sdb_gid):
                                tag = "SteamDB 官方最新 (待雲端收錄)"
                            else:
                                tag = f"官方分支 ({b_name})"

                            depot_history.append({
                                "manifest_id": b_gid,
                                "date": steamdb_date_fmt,
                                "meta": f"Ryuu 平台．分支 {b_name}",
                                "is_current": is_b_cur,
                                "is_pending": can_up,
                                "tag": tag,
                                "is_official": True
                            })
                            seen_gids.add(b_gid)

            # C. 補充 SteamDB 官方即時最新版本 (若不在清單中)
            if sdb_gid and str(sdb_gid) not in seen_gids:
                is_sdb_in_ryuu = bool(ryuu_has_this_depot and str(cur_ryuu_gid) == str(sdb_gid))
                if is_local_aligned:
                    depot_history.insert(0, {
                        "manifest_id": str(sdb_gid),
                        "date": steamdb_date_fmt,
                        "meta": f"{steamdb_date_fmt}．SteamDB 官方最新 (本地已同步)",
                        "is_current": True,
                        "is_pending": False,
                        "tag": "💾 本地當前版本 (官方最新)",
                        "is_official": True
                    })
                elif is_sdb_in_ryuu:
                    depot_has_update = True
                    any_depot_has_real_update = True
                    depot_history.insert(0, {
                        "manifest_id": str(sdb_gid),
                        "date": steamdb_date_fmt,
                        "meta": f"{steamdb_date_fmt}．SteamDB 官方最新",
                        "is_current": False,
                        "is_pending": True,
                        "tag": "⚡ 可更新至官方最新",
                        "is_official": True
                    })
                else:
                    depot_history.insert(0, {
                        "manifest_id": str(sdb_gid),
                        "date": steamdb_date_fmt,
                        "meta": f"{steamdb_date_fmt}．SteamDB 官方最新 (待雲端收錄)",
                        "is_current": False,
                        "is_pending": False,
                        "tag": "SteamDB 官方最新 (待雲端收錄)",
                        "is_official": True
                    })
                seen_gids.add(str(sdb_gid))

            # D. 補充本地當前版本 (若本地為舊版且尚未加入清單)
            if mid_str and str(mid_str) not in seen_gids:
                cur_local_tag = f"🔴 本地舊版 (官方已棄置)" if is_deprecated else "💾 本地當前版本"
                depot_history.append({
                    "manifest_id": str(mid_str),
                    "meta": f"{local_date_str}．本地當前版本 (已棄置)" if is_deprecated else f"{local_date_str}．本地當前版本 (舊版)",
                    "is_current": True,
                    "is_pending": False,
                    "tag": cur_local_tag,
                    "is_official": False
                })
                seen_gids.add(str(mid_str))

            # E. 補充 SteamCMD PICS 其他分支
            raw_depot_data = steamdb_info.get("depots_info", {}).get(did_str, {})
            all_branch_manifests = raw_depot_data.get("manifests", {}) if isinstance(raw_depot_data, dict) else {}
            for b_name, b_info in all_branch_manifests.items():
                if isinstance(b_info, dict) and "gid" in b_info:
                    b_gid = str(b_info.get("gid", ""))
                    if b_gid and b_gid not in seen_gids:
                        is_b_cur = bool(mid_str and str(mid_str) == b_gid)
                        depot_history.append({
                            "manifest_id": b_gid,
                            "meta": f"SteamDB 官方分支．{b_name}",
                            "is_current": is_b_cur,
                            "is_pending": False,
                            "tag": f"💾 本地當前 ({b_name})" if is_b_cur else f"官方分支 ({b_name})",
                            "is_official": True
                        })
                        seen_gids.add(b_gid)

            # 依需求 4e 最多呈現最新 10 個真實版本
            depot_history = depot_history[:10]

            depots_result.append({
                "depot_id": did_str,
                "depot_name": depot_name,
                "is_main": is_main,
                "is_deprecated": is_deprecated,
                "replaced_by": replaced_by,
                "deprecation_reason": dep_info.get("reason", "") if is_deprecated else "",
                "local_manifest": mid_str or "未配置",
                "official_manifest": sdb_gid or ("SteamDB 已除名" if is_deprecated else "SteamDB 未標記"),
                "local_date": f"{local_date_str}．本地",
                "official_date": f"{steamdb_date_fmt}．SteamDB",
                "source_name": source_name,
                "has_update": depot_has_update,
                "is_aligned": False if is_deprecated else is_local_aligned,
                "history": depot_history
            })

        res["depots"] = depots_result
        if needs_topology_migration:
            any_depot_has_real_update = True
        res["has_update"] = any_depot_has_real_update

        # 🌟 同步更新本地 manifest_updates 快取，確保管理頁秒開與即時同步點亮
        try:
            updates_file = Path(__file__).parent.parent / "data" / "manifest_updates.json"
            cached_updates = {}
            if updates_file.exists():
                try: cached_updates = json.loads(updates_file.read_text(encoding="utf-8"))
                except Exception: pass

            # 若為有更新，計算或保留具體的「舊 n 版」狀態
            v_stat = cached_updates.get(appid_str, {}).get("version_status", "舊 1 版")
            if needs_topology_migration:
                p_dep = topo.get("primary_active_depot", "")
                v_stat = f"架構升級 (Depot {p_dep})" if p_dep else "架構升級"
            elif any_depot_has_real_update:
                if not v_stat or v_stat == "0 版" or v_stat == "最新版" or "" in v_stat:
                    v_stat = "舊 1 版"
            else:
                v_stat = "最新版"

            cached_updates[appid_str] = {
                "has_update": bool(any_depot_has_real_update),
                "version_status": v_stat,
                "latest_date": steamdb_date_str or "未知",
                "best_source": best_source
            }
            updates_file.write_text(json.dumps(cached_updates, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        return res

    def check_denuvo(self, appid: str) -> bool:
        """檢查遊戲是否含有 Denuvo 加密"""
        # 已知常見 Denuvo 遊戲列表
        denuvo_set = {"1245620", "2358720", "2050650", "1817070", "1364780"}
        return str(appid) in denuvo_set

    def get_search_item_status(self, appid: str, name: str = "") -> Dict[str, Any]:
        """
        為搜尋結果小卡提供多源狀態深度核驗（正確性優先）：
        - 檢查是否有可用 Manifest (Ryuu / Lua.tools / SteamDB 歷史)
        - 提取版本更新日期 (跟隨 Ryuu 的 Manifest ID 與 SteamDB 資料庫日期，格式如 "9月23日")
        - 檢查 Google Drive 網盤補丁庫是否收錄該遊戲的補丁或專用 Lua
        - 檢查本地是否已入庫
        """
        from datetime import datetime
        appid_str = str(appid).strip()
        sp = self._steam_path or steam_manager.find_steam_path()

        # 1. 檢查本地是否已入庫
        is_installed = False
        if sp:
            lua_f = Path(sp) / "config" / "lua" / f"{appid_str}.lua"
            is_installed = bool(lua_f.exists() and lua_f.stat().st_size > 20)

        # 2. 檢查雲端網盤補丁庫 (Google Drive)
        has_patch = False
        drive_name = ""
        try:
            from managers import onlinefix_manager
            ps = onlinefix_manager.get_patch_sources(target_app_id=appid_str, target_app_name=name, allow_network=False)
            app_src = ps.get(appid_str, {})
            if app_src.get("cloud_rar") or app_src.get("cloud_lua") or app_src.get("local_lua"):
                has_patch = True
                drive_name = app_src.get("drive_name", "Google Drive")
        except Exception as e:
            print(f"[get_search_item_status] AppID {appid_str} 查詢補丁庫異常: {e}")

        # 3. 查詢 Manifest 與版本日期 (放寬超時並支援多源容錯)
        has_manifest = False
        version_date_str = ""
        try:
            from managers import version_resolver
            sdb_info = version_resolver.fetch_steamdb_manifests(appid_str, timeout=5)
            sdb_manifests = sdb_info.get("manifests", {})
            raw_date = sdb_info.get("date_str", "")
            if raw_date:
                try:
                    dt = datetime.strptime(raw_date, "%Y-%m-%d")
                    version_date_str = f"{dt.month}月{dt.day}日"
                except Exception:
                    version_date_str = raw_date

            # 查詢 Ryuu / LuaTools 聚合來源 (給予充裕的 6 秒連線超時)
            search_res = self._unified_mgr.search_all_sources(appid_str, timeout=6, steamdb_manifests=sdb_manifests)
            best_source = search_res.get("best_source", "none")
            ryuu_data = search_res.get("ryuu", {})
            ryuu_depots = ryuu_data.get("depots", {})
            luatools_data = search_res.get("luatools", {})

            # 🌟 正確性核心：只要 Ryuu / LuaTools / GDrive 補丁庫 / 本地 任一有資料，即判定為支援
            if (best_source != "none" and ryuu_depots) or ryuu_data.get("available") or luatools_data.get("available") or has_patch or is_installed:
                has_manifest = True

            if not version_date_str:
                r_time = ryuu_data.get("time", "")
                if r_time and "T" in r_time:
                    try:
                        dt = datetime.fromisoformat(r_time)
                        version_date_str = f"{dt.month}月{dt.day}日"
                    except Exception:
                        pass
        except Exception as e:
            print(f"[get_search_item_status] AppID {appid_str} 查詢 Manifest 異常: {e}")
            # 網路波動異常時，若有補丁庫或已安裝則支援，否則預設給予嘗試入庫機會
            if has_patch or is_installed:
                has_manifest = True

        return {
            "appid": appid_str,
            "has_manifest": has_manifest,
            "version_date": version_date_str,
            "has_onlinefix": has_patch,
            "drive_name": drive_name,
            "is_installed": is_installed
        }

    def refresh_single_game_status(self, appid: str) -> Dict[str, Any]:
        """
        單一遊戲更新完成後，即時重新驗證本地資料與 SteamDB 官方狀態，並更新快取
        """
        appid_str = str(appid).strip()
        if not appid_str or not appid_str.isdigit():
            return {"ok": False, "appid": appid_str, "has_update": False, "version_status": "最新版"}

        # 🌟 優先讀取剛更新之快取，若已標記為最新版則立即秒回 (0ms 反饋)
        updates_file = Path(__file__).parent.parent / "data" / "manifest_updates.json"
        if updates_file.exists():
            try:
                updates = json.loads(updates_file.read_text(encoding="utf-8"))
                cached = updates.get(appid_str)
                if cached and cached.get("has_update") is False:
                    return {
                        "ok": True,
                        "appid": appid_str,
                        "has_update": False,
                        "version_status": cached.get("version_status", "最新版"),
                        "latest_date": cached.get("latest_date", ""),
                        "best_source": cached.get("best_source", "官方")
                    }
            except Exception:
                pass

        sp = self._steam_path or steam_manager.find_steam_path()
        lua_dir = Path(sp) / "config" / "lua" if sp else None

        try:
            from managers import version_resolver
            diff_info = version_resolver.resolve_manifest_version_diff(
                appid_str,
                lua_dir=str(lua_dir) if lua_dir else "",
                steam_path=sp,
                timeout=4
            )
            is_latest = diff_info.get("is_latest", True)
            v_stat = diff_info.get("version_status", "")
            diff_cnt = diff_info.get("diff_count", 0) or 0

            if is_latest:
                raw_v = "最新版"
                has_up = False
            elif v_stat == "待雲端同步" or not diff_info.get("has_available_update"):
                raw_v = "待雲端同步"
                has_up = False
            else:
                raw_v = f"舊 {diff_cnt} 版" if diff_cnt > 0 else (v_stat or "舊 1 版")
                has_up = True

            u_item = {
                "appid": appid_str,
                "has_update": has_up,
                "version_status": raw_v,
                "latest_date": diff_info.get("latest_date", "未知"),
                "best_source": diff_info.get("best_source", "ryuu")
            }

            # 同步更新 manifest_updates.json 快取
            updates_file = Path(__file__).parent.parent / "data" / "manifest_updates.json"
            try:
                updates = {}
                if updates_file.exists():
                    updates = json.loads(updates_file.read_text(encoding="utf-8"))
                updates[appid_str] = u_item
                updates_file.write_text(json.dumps(updates, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

            self.invalidate_games_cache()
            return {
                "ok": True,
                "appid": appid_str,
                "has_update": has_up,
                "version_status": raw_v,
                "latest_date": u_item["latest_date"],
                "best_source": u_item["best_source"]
            }
        except Exception as e:
            return {
                "ok": False,
                "appid": appid_str,
                "has_update": False,
                "version_status": "最新版",
                "error": str(e)
            }

    def can_import(self, appid: str) -> Dict[str, Any]:
        """入庫權限檢驗：本專案為永久旗艦無限制版，無限次直接放行"""
        return {
            "allowed": True,
            "activated": True,
            "granted": True,
            "tier": "sponsor",
            "reason": ""
        }

    def preload_games_cache(self):
        """背景非同步預熱入庫遊戲清單記憶體快取，初始化階段預先整理完畢，前端秒開調用"""
        import threading
        def _worker():
            try:
                self.list_games(force_refresh=True)
            except Exception as e:
                pass
        t = threading.Thread(target=_worker, name="PreloadGamesWorker", daemon=True)
        t.start()

    def invalidate_games_cache(self):
        """使遊戲入庫清單記憶體快取失效（新增、刪除或更新時調用）"""
        self._cached_games = None

    def open_steam_store(self, appid: str) -> bool:
        """開啟 Steam 商店頁面"""
        return self.open_url(f"https://store.steampowered.com/app/{appid}/")

