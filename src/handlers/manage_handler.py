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
import stat
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
from managers import onlinefix_manager
from managers import version_resolver

class ManageHandler:
    def _load_unified_game_cache(self) -> Dict[str, Any]:
        """讀取全域統一遊戲快取（優先載入 resources/builtin_game_cache.json，再以 data/game_cache.json 覆蓋）"""
        builtin_cache_file = config_manager.get_root_dir() / "resources" / "builtin_game_cache.json"
        cache_file = config_manager.get_storage_dir() / "game_cache.json"
        game_cache = {}
        if builtin_cache_file.exists():
            try:
                game_cache.update(json.loads(builtin_cache_file.read_text(encoding="utf-8")))
            except Exception:
                pass
        if cache_file.exists():
            try:
                game_cache.update(json.loads(cache_file.read_text(encoding="utf-8")))
            except Exception:
                pass
        return game_cache

    def get_updatable_games(self) -> List[Dict[str, Any]]:
        """
        全庫精確取得當前真正需要更新的遊戲名單 (杜絕前端快照時序差導致漏更)
        直接從 manifest_updates.json 讀取最新狀態，並交叉校驗本地 Lua 檔案
        """
        updates_file = config_manager.get_storage_dir() / "manifest_updates.json"
        cached_updates = {}
        game_cache = self._load_unified_game_cache()

        if updates_file.exists():
            try:
                cached_updates = json.loads(updates_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        sp = self._steam_path or steam_manager.find_steam_path()
        lua_dir = Path(sp) / "config" / "lua" if sp else None

        results = []
        for aid, u in cached_updates.items():
            if not u.get("has_update"):
                continue
            # 🌟 批次更新防線：僅針對 Ryuu 明確收錄新版本的項目，排除需手動嘗試更新 (try_update) 的項目
            if u.get("update_mode") == "try_update" or u.get("can_auto_update") is False:
                continue

            aid_str = str(aid).strip()
            # 確認本地確有此 Lua
            if lua_dir and not (lua_dir / f"{aid_str}.lua").exists():
                continue

            c_info = game_cache.get(aid_str, {})
            name = c_info.get("name", "") or f"App_{aid_str}"
            results.append({
                "appid": aid_str,
                "name": name,
                "has_update": True,
                "version_status": u.get("version_status", "可更新"),
                "latest_date": u.get("latest_date", "未知"),
                "best_source": u.get("best_source", "ryuu"),
                "update_mode": u.get("update_mode", "auto_update"),
                "can_auto_update": u.get("can_auto_update", True)
            })

        return results

    def list_games(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        本地極速掃描所有 Lua 遊戲（記憶體快取 0 延遲，絕不阻塞視窗線程）。
        優先調用記憶體暫存的已整理遊戲資料，當有快取且非強制刷新時直接調用。
        """
        if not force_refresh and getattr(self, "_cached_games", None) is not None:
            return list(self._cached_games)

        with getattr(self, "_cached_games_lock", threading.Lock()):
            if not force_refresh and getattr(self, "_cached_games", None) is not None:
                return list(self._cached_games)

            sp = self._steam_path or steam_manager.find_steam_path()
            if not sp: return []
            lua_dir = Path(sp) / "config" / "lua"
            if not lua_dir.exists(): return []

            games = []
            lua_files = [f for f in lua_dir.glob("*.lua") if f.name != "manifest.lua"]
            pattern = re.compile(r'^[ \t]*(?:--[^\n\r]*?)?set[M|m]anifest[i|I]d\s*\(\s*(\d+)\s*,\s*"(\d+)"', re.MULTILINE)

            # 🌟 批次快速索引所有 Steam 庫的 ACF 檔案，同時即時提取本地官方真實遊戲名稱 (0 延遲秒開)
            acf_map = {}
            acf_names = {}
            try:
                libs = steam_manager.get_steam_libraries(sp)
                for lib in libs:
                    sa = lib / "steamapps"
                    if sa.exists():
                        for acf in sa.glob("appmanifest_*.acf"):
                            parts = acf.stem.split("_")
                            if len(parts) > 1 and parts[1].isdigit():
                                aid = parts[1]
                                acf_map[aid] = acf
                                try:
                                    txt = acf.read_text(encoding="utf-8", errors="ignore")
                                    m_nm = re.search(r'"name"\s+"([^"]+)"', txt)
                                    if m_nm:
                                        acf_names[aid] = m_nm.group(1).strip()
                                except Exception:
                                    pass
            except Exception:
                pass

            # 讀取遊戲快取（優先載入倉庫內建快取，確保初次抓取 0 延遲秒開）
            builtin_cache_file = config_manager.get_root_dir() / "resources" / "builtin_game_cache.json"
            cache_file = config_manager.get_storage_dir() / "game_cache.json"
            game_cache = {}
            cache_dirty = False
            if builtin_cache_file.exists():
                try:
                    game_cache.update(json.loads(builtin_cache_file.read_text(encoding="utf-8")))
                except Exception:
                    pass
            if cache_file.exists():
                try:
                    game_cache.update(json.loads(cache_file.read_text(encoding="utf-8")))
                except Exception:
                    pass

            # 讀取本地已有的版本更新快取（無需重複發起慢速網路請求）
            updates_file = config_manager.get_storage_dir() / "manifest_updates.json"
            cached_updates = {}
            if updates_file.exists():
                try:
                    cached_updates = json.loads(updates_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            # 讀取 Google Drive 網盤補丁庫與已知 Online-Fix / ZeiGames 官網補丁 AppID 清單
            try:
                of_appids = set(onlinefix_manager.get_all_onlinefix_appids())
            except Exception:
                of_appids = set()

            try:
                from api import web_patch_checker
                known_of_appids, known_zg_appids = web_patch_checker.get_known_patch_appids()
            except Exception:
                known_of_appids, known_zg_appids = set(), set()

            for lf in lua_files:
                appid = lf.stem
                if not appid.isdigit(): continue

                try:
                    content = lf.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                c_info = game_cache.get(appid, {})
                game_name = c_info.get("name", "")

                # 多層級名稱探測：1. 官方 ACF 檔 -> 2. Lua 頂部註解 -> 3. 本地 SteamDB 快取
                if not game_name or game_name == "未知遊戲" or game_name.startswith("App_"):
                    if appid in acf_names and acf_names[appid]:
                        game_name = acf_names[appid]

                if not game_name or game_name == "未知遊戲" or game_name.startswith("App_"):
                    name_m = re.search(r'--\s*\d+\s*-\s*(.+)', content)
                    game_name = name_m.group(1).strip() if name_m else ""

                if not game_name or game_name == "未知遊戲" or game_name.startswith("App_"):
                    sdb_file = config_manager.get_storage_dir() / "steamdb_cache" / f"{appid}.json"
                    if sdb_file.exists():
                        try:
                            sdb_data = json.loads(sdb_file.read_text(encoding="utf-8"))
                            sdb_name = sdb_data.get("name") or sdb_data.get("data", {}).get("name")
                            if sdb_name:
                                game_name = sdb_name.strip()
                        except Exception:
                            pass

                if not game_name or game_name == "未知遊戲":
                    game_name = f"App_{appid}"

                from utils.tw_converter import sanitize_game_name
                game_name = sanitize_game_name(game_name, appid)
                english_name = c_info.get("english_name", "") or c_info.get("name_en", "") or acf_names.get(appid, "")

                header_img = c_info.get("header_image", "")
                if not header_img:
                    header_img = f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"

                # 若成功補全新名稱，自動更新至本地快取
                if not game_name.startswith("App_") and (not c_info.get("name") or c_info.get("name").startswith("App_")):
                    c_info["name"] = game_name
                    c_info["english_name"] = english_name or game_name
                    c_info["name_en"] = english_name or game_name
                    c_info["header_image"] = header_img
                    game_cache[appid] = c_info
                    cache_dirty = True

                matches = pattern.findall(content)
                current_mid = matches[0][1] if matches else ""

                # 快速判斷鎖定狀態 (優先從批次 acf_map 讀取，避免遍歷全庫)
                acf = acf_map.get(appid)
                is_locked = False
                if acf and acf.exists():
                    try:
                        acf_text = acf.read_text(encoding="utf-8", errors="ignore")
                        m = re.search(r'"AutoUpdateBehavior"\s+"(\d+)"', acf_text)
                        if m and int(m.group(1)) == 1:
                            is_locked = True
                    except Exception:
                        pass
                else:
                    # 未安裝遊戲：檢查 Lua 自身是否唯讀，極速 0 延遲，杜絕全庫磁碟遍歷
                    try:
                        st = os.stat(lf)
                        is_locked = bool(st.st_mode & stat.S_IREAD) and not bool(st.st_mode & stat.S_IWRITE)
                    except Exception:
                        is_locked = False

                # 直接讀取快取的更新標記，0 延遲秒開！
                u_info = cached_updates.get(appid, {})
                has_update = u_info.get("has_update", False)
                version_status = u_info.get("version_status", "0 版")
                latest_date = u_info.get("latest_date", "未知")
                best_source = u_info.get("best_source", "ryuu")
                # 🌟 核心修復：本地部署狀態檢查不能受限於 of_appids (無論網盤是否收錄，只要本機已部署或手動安裝，即為已部署)
                # 僅針對本地已安裝遊戲 (appid in acf_map) 進行極速檢查，未安裝者耗時 0ms，保證秒開！
                is_deployed = False
                is_protected = False
                if appid in acf_map:
                    try:
                        is_deployed = onlinefix_manager.is_patch_deployed_locally(appid)
                        if is_deployed:
                            is_protected = onlinefix_manager.is_patch_protected(appid)
                    except Exception:
                        pass

                # 🌟 補丁標籤：區分 Google Drive 網盤補丁、Online-Fix 官方補丁、ZeiGames 官方補丁
                has_gdrive = bool(appid in of_appids)
                has_of_web = bool(appid in known_of_appids)
                has_zg_web = bool(appid in known_zg_appids)
                has_any_patch = has_gdrive or has_of_web or has_zg_web

                games.append({
                    "appid": appid,
                    "name": game_name,
                    "english_name": english_name,
                    "name_en": english_name,
                    "image": header_img,
                    "locked": is_locked,
                    "deployed": is_deployed,             # 🌟 本地已部署補丁標記
                    "protected": is_protected,           # 🌟 原始檔案已成功備份保護標記
                    "current_mid": current_mid,
                    "has_update": has_update,            # 🌟 秒開即帶有黃色需更新標記
                    "has_onlinefix": has_any_patch,      # 🌟 相容舊代碼 (代表任何網盤或外網有補丁)
                    "has_gdrive": has_gdrive,            # 🌟 Google Drive 網盤收錄標記
                    "has_onlinefix_web": has_of_web,     # 🌟 Online-Fix 官方網站收錄標記
                    "has_zeigames_web": has_zg_web,      # 🌟 ZeiGames 官方網站收錄標記
                    "version_status": version_status,
                    "latest_date": latest_date,
                    "best_source": best_source,
                    "best_source_name": u_info.get("best_source_name", "Ryuu"),
                    "hubcap_status": u_info.get("hubcap_status", ""),
                    "can_auto_update": u_info.get("can_auto_update", True)
                })

            # 排序：有更新者（黃色需更新項）置頂排列
            games.sort(key=lambda x: (0 if x["has_update"] else 1, x["name"].lower()))
            if cache_dirty:
                try:
                    cache_file.write_text(json.dumps(game_cache, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
            self._cached_games = games

            # 🌟 主動背景補檢：若目前尚未執行雙軌全庫檢查，針對任何未建立有效外網補丁快取的已入庫遊戲於背景執行預檢
            if not getattr(self, "_is_checking_updates", False):
                self._ensure_unindexed_games_patch_checked(games)

            return list(self._cached_games)

    def _ensure_unindexed_games_patch_checked(self, games: List[Dict[str, Any]]):
        """檢查是否有尚未完成外網與網盤補丁檢索的已入庫遊戲，若有則立即在背景執行檢索並即時推播更新小卡標籤"""
        if getattr(self, "_is_checking_unindexed_patches", False):
            return
        try:
            from api import web_patch_checker
            web_patch_checker._load_cache()
            mem = web_patch_checker._patch_memory_cache
            unindexed = []
            for g in games:
                aid = str(g.get("appid") or "").strip()
                if not aid:
                    continue
                entry = mem.get(aid)
                if not entry or not web_patch_checker.is_patch_cache_valid(entry):
                    unindexed.append(g)
            if not unindexed:
                return
        except Exception:
            return

        self._is_checking_unindexed_patches = True

        def _bg_worker(items_to_check):
            try:
                import concurrent.futures
                from managers import onlinefix_manager
                from api import web_patch_checker

                try:
                    of_appids_set = set(onlinefix_manager.get_all_onlinefix_appids())
                except Exception:
                    of_appids_set = set()

                def _check_single(g_item):
                    aid = str(g_item.get("appid") or "").strip()
                    g_name = g_item.get("name") or ""
                    eng_name = g_item.get("english_name") or g_item.get("name_en") or g_name
                    try:
                        patch_res = web_patch_checker.check_all_web_patches(eng_name, appid=aid, force_refresh=False)
                        has_gdrive = bool(aid in of_appids_set)
                        if not has_gdrive:
                            try:
                                p_src = onlinefix_manager.get_patch_sources(target_app_id=aid, target_app_name=eng_name or g_name)
                                app_src = p_src.get(aid, {})
                                if app_src.get("cloud_rar") or app_src.get("cloud_lua") or app_src.get("local_lua"):
                                    has_gdrive = True
                                    of_appids_set.add(aid)
                            except Exception:
                                pass
                        has_of_web = bool(patch_res.get("onlinefix", {}).get("available"))
                        has_zg_web = bool(patch_res.get("zeigames", {}).get("available"))
                        has_any = has_gdrive or has_of_web or has_zg_web

                        # 同步更新 _cached_games 記憶體狀態
                        if self._cached_games:
                            for cg in self._cached_games:
                                if str(cg.get("appid")) == aid:
                                    cg["has_gdrive"] = has_gdrive
                                    cg["has_onlinefix_web"] = has_of_web
                                    cg["has_zeigames_web"] = has_zg_web
                                    cg["has_onlinefix"] = has_any
                                    break

                        if hasattr(self, "_push_js_event"):
                            self._push_js_event("onSingleGamePatchChecked", {
                                "appid": aid,
                                "name": g_name,
                                "has_gdrive": has_gdrive,
                                "has_of_web": has_of_web,
                                "has_zg_web": has_zg_web,
                                "has_onlinefix": has_any,
                                "onlinefix_url": patch_res.get("onlinefix", {}).get("url", ""),
                                "zeigames_url": patch_res.get("zeigames", {}).get("url", "")
                            })
                    except Exception:
                        pass

                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
                    list(ex.map(_check_single, items_to_check))
            except Exception:
                pass
            finally:
                self._is_checking_unindexed_patches = False

        import threading
        threading.Thread(target=_bg_worker, args=(unindexed,), daemon=True).start()

    def ensure_installed_games_resolved(self) -> Dict[str, Any]:
        """
        🌟 初始化階段專屬核心 API：強制校驗並補全所有已入庫遊戲的官方真實繁中名稱與高畫質封面圖片。
        若偵測到缺失名稱或使用預設佔位圖片的遊戲，立即透過多執行緒並行向 Steam 官方 Store API 抓取。
        絕不搶著進系統，向前端即時回報進度，直到所有入庫遊戲確認就緒。
        """
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp:
            return {"ok": False, "msg": "未找到 Steam 安裝目錄", "games": []}

        lua_dir = Path(sp) / "config" / "lua"
        if not lua_dir.exists():
            return {"ok": True, "count": 0, "games": []}

        lua_files = [f for f in lua_dir.glob("*.lua") if f.name != "manifest.lua" and f.stem.isdigit()]
        all_appids = [f.stem for f in lua_files]
        if not all_appids:
            return {"ok": True, "count": 0, "games": []}

        # 1. 載入當前快取（內建快取 + data/game_cache.json）
        builtin_cache_file = config_manager.get_root_dir() / "resources" / "builtin_game_cache.json"
        cache_file = config_manager.get_storage_dir() / "game_cache.json"
        game_cache = {}
        if builtin_cache_file.exists():
            try:
                game_cache.update(json.loads(builtin_cache_file.read_text(encoding="utf-8")))
            except Exception:
                pass
        if cache_file.exists():
            try:
                game_cache.update(json.loads(cache_file.read_text(encoding="utf-8")))
            except Exception:
                pass

        # 2. 檢測哪些 AppID 缺乏有效名稱或有效商店封面
        to_fetch = []
        for aid in all_appids:
            info = game_cache.get(aid, {})
            name = info.get("name", "")
            img = info.get("header_image", "")
            needs_resolve = False
            if not name or name == "未知遊戲" or name.startswith("App_"):
                needs_resolve = True
            elif not img or img.endswith(f"/apps/{aid}/header.jpg"):
                if "header_alt_assets" not in img and "t=" not in img:
                    needs_resolve = True
            if needs_resolve:
                to_fetch.append(aid)

        # 3. 如果需要並行抓取，使用 ThreadPoolExecutor 併發抓取 Steam 官方 Store API
        resolved_count = 0
        total_fetch = len(to_fetch)
        if total_fetch > 0:
            import urllib.request
            import ssl
            from concurrent.futures import ThreadPoolExecutor, as_completed
            from utils.tw_converter import sanitize_game_name

            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            def _fetch_single(aid):
                url = f"https://store.steampowered.com/api/appdetails?appids={aid}&l=tchinese"
                s_name, en_name, hdr = None, None, None
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                    with urllib.request.urlopen(req, timeout=6, context=ctx) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        if data and str(aid) in data and data[str(aid)].get("success"):
                            d = data[str(aid)]["data"]
                            raw_name = d.get("name") or f"App_{aid}"
                            s_name = sanitize_game_name(raw_name, aid)
                            hdr = d.get("header_image") or ""
                            if not re.search(r'[\u4e00-\u9fff]', raw_name):
                                en_name = raw_name
                except Exception:
                    pass
                # 若繁中介面回傳名稱含有中文，額外拉取英文原名以供外網 (online-fix / zeigames) 精準檢索
                if not en_name:
                    try:
                        en_url = f"https://store.steampowered.com/api/appdetails?appids={aid}&l=english"
                        en_req = urllib.request.Request(en_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                        with urllib.request.urlopen(en_req, timeout=5, context=ctx) as en_resp:
                            en_data = json.loads(en_resp.read().decode("utf-8"))
                            if en_data and str(aid) in en_data and en_data[str(aid)].get("success"):
                                en_name = en_data[str(aid)].get("data", {}).get("name") or s_name
                    except Exception:
                        en_name = s_name
                return aid, s_name, en_name, hdr

            with ThreadPoolExecutor(max_workers=min(12, total_fetch)) as executor:
                futures = {executor.submit(_fetch_single, aid): aid for aid in to_fetch}
                for fut in as_completed(futures):
                    aid, s_name, raw_name, hdr = fut.result()
                    resolved_count += 1
                    if s_name:
                        c_info = game_cache.get(aid, {})
                        c_info["name"] = s_name
                        c_info["english_name"] = raw_name or s_name
                        c_info["name_en"] = raw_name or s_name
                        if hdr:
                            c_info["header_image"] = hdr
                        game_cache[aid] = c_info

                    disp_name = s_name or f"App_{aid}"
                    self._push_js_event("on_game_resolved_progress", {
                        "current": resolved_count,
                        "total": total_fetch,
                        "appid": aid,
                        "name": disp_name
                    })

            try:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps(game_cache, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

        # 4. 強制刷新 list_games 記憶體快取
        games = self.list_games(force_refresh=True)
        return {
            "ok": True,
            "count": len(games),
            "total_checked": len(all_appids),
            "resolved_count": resolved_count,
            "games": games
        }

    def trigger_background_update_check(self, force: bool = False) -> Dict[str, Any]:
        """
        供前端或啟動時主動呼叫：在背景守護執行緒中啟動雙軌全庫檢查（軌道 1: Manifest 更新比對 ｜ 軌道 2: 三大源頭線上補丁檢查）。
        立即回傳 0 延遲，不阻塞 UI，查出一筆即時向前端推播點亮一筆！
        """
        import threading
        if getattr(self, "_is_checking_updates", False):
            # 若已在背景運行中，主動補推最新雙軌進度狀態以確保前端 UI 100% 同步
            if hasattr(self, "_push_js_event"):
                if getattr(self, "_last_update_finished", None):
                    self._push_js_event("onAllUpdatesCheckFinished", self._last_update_finished)
                elif getattr(self, "_last_update_progress", None):
                    self._push_js_event("onUpdateProgress", self._last_update_progress)
                if getattr(self, "_last_patch_finished", None):
                    self._push_js_event("onAllPatchesCheckFinished", self._last_patch_finished)
                elif getattr(self, "_last_patch_progress", None):
                    self._push_js_event("onPatchCheckProgress", self._last_patch_progress)
            return {"ok": True, "already_running": True}

        t = threading.Thread(target=self.check_updates_async, kwargs={"force": force}, daemon=True)
        t.start()
        return {"ok": True, "status": "started"}

    def check_updates_async(self, force: bool = False) -> Dict[str, Any]:
        """
        全域主動搜尋並比對所有已入庫遊戲的最新 Manifest 版本狀態（軌道 1）與三大源頭線上補丁狀態（軌道 2：Online-Fix.me、ZeiGames.com、Google Drive）
        並自動在背景補齊缺失的遊戲官方繁體名稱、英文原名與 CDN 封面圖片。
        支援即時逐筆推播與增量快取持久化。
        """
        if getattr(self, "_is_checking_updates", False):
            return {"ok": True, "already_running": True, "updates": {}}
        self._is_checking_updates = True
        self._last_update_progress = None
        self._last_update_finished = None
        self._last_patch_progress = None
        self._last_patch_finished = None

        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp: 
            self._is_checking_updates = False
            return {"ok": False, "updates": {}}
        lua_dir = Path(sp) / "config" / "lua"
        if not lua_dir.exists(): 
            self._is_checking_updates = False
            return {"ok": False, "updates": {}}

        import concurrent.futures
        import threading
        lua_files = [f for f in lua_dir.glob("*.lua") if f.name != "manifest.lua" and f.stem.isdigit()]
        pattern = re.compile(r'^[ \t]*(?:--[^\n\r]*?)?set[M|m]anifest[i|I]d\s*\(\s*(\d+)\s*,\s*"(\d+)"', re.MULTILINE)

        if not lua_files:
            empty_u = {"total": 0, "updated_count": 0, "updates": {}}
            empty_p = {"total": 0, "installed_gdrive": 0, "installed_onlinefix": 0, "installed_zeigames": 0, "total_gdrive": 0, "total_onlinefix": 0, "total_zeigames": 0}
            self._last_update_finished = empty_u
            self._last_patch_finished = empty_p
            if hasattr(self, "_push_js_event"):
                self._push_js_event("onAllUpdatesCheckFinished", empty_u)
                self._push_js_event("onAllPatchesCheckFinished", empty_p)
            self._is_checking_updates = False
            return {"ok": True, "updates": {}, "count": 0, "metadata": {}}

        # 載入遊戲快取以備補全
        game_cache = self._load_unified_game_cache()

        # ═════════════════════════════════════════════════════════════════
        # 🌟 雙軌非同步檢查系統：軌道 2（線上補丁三大源頭：Online-Fix.me、ZeiGames.com、Google Drive 全面核驗）
        # ═════════════════════════════════════════════════════════════════
        def _run_patch_checks():
            try:
                from managers import onlinefix_manager
                from api import web_patch_checker

                # 1. 收集所有已入庫遊戲的中英文名稱（整合 game_cache 與 _cached_games，確保零遺漏）
                g_cache = self._load_unified_game_cache()
                cached_map = {}
                if getattr(self, "_cached_games", None):
                    for cg in self._cached_games:
                        if cg.get("appid"):
                            cached_map[str(cg.get("appid"))] = cg

                patch_items = []
                target_apps_map = {}
                for lf_item in lua_files:
                    aid = lf_item.stem
                    if not aid.isdigit(): continue
                    c_info = g_cache.get(aid, {})
                    cg_info = cached_map.get(aid, {})
                    disp_name = c_info.get("name") or cg_info.get("name") or f"App_{aid}"
                    eng_name = c_info.get("english_name") or c_info.get("name_en") or cg_info.get("english_name") or cg_info.get("name_en") or disp_name
                    patch_items.append((aid, eng_name, disp_name))
                    target_apps_map[aid] = eng_name or disp_name

                total_p_files = len(patch_items)
                if hasattr(self, "_push_js_event"):
                    init_p = {
                        "current": 0,
                        "total": total_p_files,
                        "percent": 0,
                        "stage": "gdrive_sync",
                        "appid": "",
                        "game_name": "同步 Google Drive 雲端補丁庫索引…"
                    }
                    self._last_patch_progress = init_p
                    self._push_js_event("onPatchCheckProgress", init_p)

                # 2. 全面同步源頭 1：Google Drive 雲端補丁庫索引與全域模糊對齊
                onlinefix_manager.fetch_cloud_cache(force=force)
                try:
                    of_appids_set = set(onlinefix_manager.get_all_onlinefix_appids(force=force))
                except Exception:
                    of_appids_set = set()
                try:
                    gdrive_sources_map = onlinefix_manager.get_patch_sources(target_apps=target_apps_map, allow_network=False, force_refresh=False)
                except Exception:
                    gdrive_sources_map = {}

                patch_lock = threading.Lock()
                patch_checked_counter = [0]
                gdrive_hits = set()
                of_hits = set()
                zg_hits = set()

                def _check_one_patch(item):
                    aid, eng_name, g_name = item
                    has_gdrive = False
                    has_of_web = False
                    has_zg_web = False
                    of_url = ""
                    zg_url = ""
                    try:
                        # A. 確保取得真實英文名稱以供外網與網盤精準/模糊匹配
                        resolved_eng = web_patch_checker.resolve_english_game_name(eng_name or g_name, aid)
                        search_title = resolved_eng or eng_name or g_name

                        # B. 核驗源頭 2 & 3：Online-Fix.me 與 ZeiGames.com
                        patch_res = web_patch_checker.check_all_web_patches(search_title, appid=aid, force_refresh=force)
                        has_of_web = bool(patch_res.get("onlinefix", {}).get("available"))
                        has_zg_web = bool(patch_res.get("zeigames", {}).get("available"))
                        of_url = patch_res.get("onlinefix", {}).get("url", "")
                        zg_url = patch_res.get("zeigames", {}).get("url", "")

                        # C. 核驗源頭 1：Google Drive (結合 AppID 索引、批次映射與最新解析英文名二次比對)
                        has_gdrive = bool(aid in of_appids_set)
                        if not has_gdrive:
                            g_src = gdrive_sources_map.get(aid, {})
                            if g_src.get("cloud_rar") or g_src.get("cloud_lua") or g_src.get("local_lua"):
                                has_gdrive = True
                        if not has_gdrive and search_title:
                            try:
                                p_src = onlinefix_manager.get_patch_sources(target_app_id=aid, target_app_name=search_title)
                                app_src = p_src.get(aid, {})
                                if app_src.get("cloud_rar") or app_src.get("cloud_lua") or app_src.get("local_lua"):
                                    has_gdrive = True
                            except Exception:
                                pass
                    except Exception:
                        pass

                    has_any_patch = has_gdrive or has_of_web or has_zg_web

                    with patch_lock:
                        if has_gdrive:
                            of_appids_set.add(aid)
                            gdrive_hits.add(aid)
                        if has_of_web:
                            of_hits.add(aid)
                        if has_zg_web:
                            zg_hits.add(aid)
                        patch_checked_counter[0] += 1
                        cur_p_cnt = patch_checked_counter[0]

                    if self._cached_games:
                        for cg in self._cached_games:
                            if str(cg.get("appid")) == aid:
                                cg["has_gdrive"] = has_gdrive
                                cg["has_onlinefix_web"] = has_of_web
                                cg["has_zeigames_web"] = has_zg_web
                                cg["has_onlinefix"] = has_any_patch
                                break

                    p_pct = int((cur_p_cnt / total_p_files) * 100) if total_p_files > 0 else 100
                    if hasattr(self, "_push_js_event"):
                        p_prog = {
                            "current": cur_p_cnt,
                            "total": total_p_files,
                            "percent": p_pct,
                            "appid": aid,
                            "game_name": g_name if (g_name and not g_name.startswith("App_")) else (eng_name or f"App_{aid}"),
                            "has_gdrive": has_gdrive,
                            "has_of_web": has_of_web,
                            "has_zg_web": has_zg_web,
                            "has_onlinefix": has_any_patch
                        }
                        self._last_patch_progress = p_prog
                        self._push_js_event("onPatchCheckProgress", p_prog)
                        self._push_js_event("onSingleGamePatchChecked", {
                            "appid": aid,
                            "name": g_name,
                            "has_gdrive": has_gdrive,
                            "has_of_web": has_of_web,
                            "has_zg_web": has_zg_web,
                            "has_onlinefix": has_any_patch,
                            "onlinefix_url": of_url,
                            "zeigames_url": zg_url
                        })

                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as patch_exec:
                    list(patch_exec.map(_check_one_patch, patch_items))

                if hasattr(self, "_push_js_event"):
                    known_of, known_zg = web_patch_checker.get_known_patch_appids()
                    p_fin = {
                        "total": total_p_files,
                        "installed_gdrive": len(gdrive_hits),
                        "installed_onlinefix": len(of_hits),
                        "installed_zeigames": len(zg_hits),
                        "total_gdrive": len(of_appids_set),
                        "total_onlinefix": len(known_of),
                        "total_zeigames": len(known_zg)
                    }
                    self._last_patch_finished = p_fin
                    self._push_js_event("onAllPatchesCheckFinished", p_fin)
            except Exception as e:
                print(f"[ManageHandler] Patch check background worker error: {e}")
                if hasattr(self, "_push_js_event"):
                    p_fin_err = {
                        "total": len(lua_files),
                        "installed_gdrive": 0,
                        "installed_onlinefix": 0,
                        "installed_zeigames": 0,
                        "total_gdrive": 0,
                        "total_onlinefix": 0,
                        "total_zeigames": 0
                    }
                    self._last_patch_finished = p_fin_err
                    self._push_js_event("onAllPatchesCheckFinished", p_fin_err)

        patch_thread = threading.Thread(target=_run_patch_checks, daemon=True)
        patch_thread.start()

        updates_file = config_manager.get_storage_dir() / "manifest_updates.json"
        updates_file.parent.mkdir(parents=True, exist_ok=True)
        updates = {}
        if updates_file.exists() and not force:
            try:
                updates = json.loads(updates_file.read_text(encoding="utf-8"))
            except Exception:
                updates = {}

        meta_updates = {}
        save_lock = threading.Lock()
        checked_counter = [0]

        def save_progress():
            try:
                with save_lock:
                    updates_file.parent.mkdir(parents=True, exist_ok=True)
                    updates_file.write_text(json.dumps(updates, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

        def check_one(lf):
            appid = lf.stem
            if not appid.isdigit(): return
            cur_c = game_cache.get(appid, {})
            try:
                diff_info = version_resolver.resolve_manifest_version_diff(
                    appid,
                    lua_dir=str(lua_dir),
                    steam_path=sp,
                    timeout=6
                )
                is_latest = diff_info.get("is_latest", True)
                update_mode = diff_info.get("update_mode", "none")
                v_stat = diff_info.get("version_status", "")
                diff_cnt = diff_info.get("diff_count", 0) or 0
                has_avail = bool(diff_info.get("has_available_update", False) and update_mode == "update")

                # 🌟 依照最新規範分流顯示：
                # 模式 1：原本的黃框，顯示「可更新」，這是 Ryuu 有提供更新源時才呈現
                # 模式 2：新方法，淺紅框，顯示「可嘗試更新」，這是用戶有輸入 hubcap api 且 Ryuu 與最新版對不上時才觸發
                if is_latest:
                    raw_v = "最新版"
                    has_up = False
                elif update_mode == "try_update":
                    raw_v = "可嘗試更新"
                    has_up = True
                elif update_mode == "update":
                    raw_v = v_stat or (f"舊 {diff_cnt} 版" if diff_cnt > 1 else "可更新")
                    has_up = True
                else:
                    raw_v = v_stat or "待雲端同步"
                    has_up = False

                u_item = {
                    "appid": appid,
                    "name": cur_c.get("name") or (game_cache.get(appid, {}).get("name") if appid in game_cache else ""),
                    "has_update": has_up,
                    "update_mode": update_mode,
                    "version_status": raw_v,
                    "latest_date": diff_info.get("latest_date", "未知"),
                    "best_source": "ryuu",
                    "best_source_name": "Ryuu",
                    "can_auto_update": has_avail
                }
                with save_lock:
                    updates[appid] = u_item
                    checked_counter[0] += 1
                    cur_cnt = checked_counter[0]

                # 🌟 即時向前端推送全域檢查進度事件 (讓使用者看到清晰流暢的進度條)
                total_files = len(lua_files)
                pct = int((cur_cnt / total_files) * 100) if total_files > 0 else 100
                prog_payload = {
                    "current": cur_cnt,
                    "total": total_files,
                    "percent": pct,
                    "appid": appid,
                    "game_name": u_item.get("name") or f"App_{appid}",
                    "has_update": has_up
                }
                self._last_update_progress = prog_payload
                if hasattr(self, "_push_js_event"):
                    self._push_js_event("onUpdateProgress", prog_payload)
                    # 若判定該遊戲有更新，即時逐筆推播點亮小卡！
                    if has_up:
                        self._push_js_event("onSingleGameUpdateChecked", u_item)

                # 每查好 5 筆即時安全落盤快取
                if cur_cnt % 5 == 0:
                    save_progress()

            except Exception as e:
                with save_lock:
                    checked_counter[0] += 1
                    cur_cnt = checked_counter[0]
                total_files = len(lua_files)
                pct = int((cur_cnt / total_files) * 100) if total_files > 0 else 100
                prog_payload = {
                    "current": cur_cnt,
                    "total": total_files,
                    "percent": pct,
                    "appid": appid,
                    "game_name": game_cache.get(appid, {}).get("name") or f"App_{appid}",
                    "has_update": False
                }
                self._last_update_progress = prog_payload
                if hasattr(self, "_push_js_event"):
                    self._push_js_event("onUpdateProgress", prog_payload)
                try:
                    from managers import unified_manifest_manager
                    mgr = unified_manifest_manager.UnifiedManifestManager.get_instance()
                    mgr._log_manifest_check(f"[CheckError] AppID: {appid}, Error: {e}")
                except Exception:
                    pass

            # 檢查是否需要背景補全元數據
            cur_c = game_cache.get(appid, {})
            if (not cur_c.get("name") or 
                cur_c.get("name").startswith("App_") or 
                not cur_c.get("name_en") or 
                not cur_c.get("header_image")):
                try:
                    tc_n, sc_n, en_n, img = "", "", "", ""
                    try:
                        req = urllib.request.Request(f'https://store.steampowered.com/api/appdetails?appids={appid}&l=tchinese', headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req, timeout=3) as r:
                            d = json.loads(r.read().decode('utf-8'))
                            if d.get(str(appid), {}).get('success'):
                                tc_n = d[str(appid)]['data'].get('name', '').strip()
                                img = d[str(appid)]['data'].get('header_image', '')
                    except Exception:
                        pass

                    if not tc_n or '\ufffd' in tc_n:
                        try:
                            req = urllib.request.Request(f'https://store.steampowered.com/api/appdetails?appids={appid}&l=schinese', headers={'User-Agent': 'Mozilla/5.0'})
                            with urllib.request.urlopen(req, timeout=3) as r:
                                d = json.loads(r.read().decode('utf-8'))
                                if d.get(str(appid), {}).get('success'):
                                    sc_n = d[str(appid)]['data'].get('name', '').strip()
                                    if not img: img = d[str(appid)]['data'].get('header_image', '')
                        except Exception:
                            pass

                    try:
                        req = urllib.request.Request(f'https://store.steampowered.com/api/appdetails?appids={appid}&l=english', headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req, timeout=3) as r:
                            d = json.loads(r.read().decode('utf-8'))
                            if d.get(str(appid), {}).get('success'):
                                en_n = d[str(appid)]['data'].get('name', '').strip()
                                if not img: img = d[str(appid)]['data'].get('header_image', '')
                    except Exception:
                        pass

                    from utils.tw_converter import sanitize_game_name
                    best_n = tc_n if (tc_n and '\ufffd' not in tc_n) else (sc_n if (sc_n and '\ufffd' not in sc_n) else (en_n or f"App_{appid}"))
                    best_n = sanitize_game_name(best_n, appid)
                    if not img: img = f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"

                    with save_lock:
                        meta_updates[appid] = {
                            "name": best_n,
                            "name_en": en_n or best_n,
                            "english_name": en_n or best_n,
                            "header_image": img
                        }
                        game_cache[appid] = meta_updates[appid]
                        if appid in updates:
                            updates[appid]["name"] = best_n
                        else:
                            updates[appid] = {"appid": appid, "name": best_n}
                except Exception:
                    pass

        try:
            # 限制並行數為 4，避免 CPU 尖峰與網路風暴拖慢視窗
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                list(executor.map(check_one, lua_files))
        finally:
            self._is_checking_updates = False

        # 持久化快取
        save_progress()

        if meta_updates:
            try:
                cache_file = config_manager.get_storage_dir() / "game_cache.json"
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps(game_cache, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

        total_up = len([u for u in updates.values() if u.get("has_update")])
        # 🌟 全庫比對完全確認後一次性推送 (Atomic Delivery)
        fin_payload = {
            "total": len(lua_files),
            "updated_count": total_up,
            "updates": updates
        }
        self._last_update_finished = fin_payload
        if hasattr(self, "_push_js_event"):
            self._push_js_event("onAllUpdatesCheckFinished", fin_payload)

        return {
            "ok": True, 
            "updates": updates, 
            "count": total_up,
            "metadata": meta_updates
        }

    def uninstall_game(self, appid: str, *args, **kwargs) -> Dict[str, Any]:
        """刪除遊戲 Lua 入庫檔案並解除版本鎖定 (還原 ACF 與關聯 Manifest 檔案讀寫權限)"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp: return {"ok": False, "msg": "找不到 Steam 目錄路徑"}

        appid_str = str(appid).strip()
        sp_path = Path(sp)

        # 尋找所有可能存放該遊戲 Lua 的目錄
        lua_candidates = [
            sp_path / "config" / "lua" / f"{appid_str}.lua",
            sp_path / "config" / "stplug-in" / f"{appid_str}.lua",
        ]
        try:
            from managers import config_manager
            cfg_lua = Path(config_manager.get_config().get("lua_dir", config_manager.DEFAULT_LUA_DIR)) / f"{appid_str}.lua"
            if cfg_lua not in lua_candidates:
                lua_candidates.append(cfg_lua)
        except Exception:
            pass

        try:
            import stat
            import win32file
        except Exception:
            win32file = None

        deleted_lua = False
        for lf in lua_candidates:
            if lf.exists():
                try:
                    if win32file:
                        try:
                            win32file.SetFileAttributes(str(lf), win32file.FILE_ATTRIBUTE_NORMAL)
                        except Exception:
                            pass
                    os.chmod(lf, stat.S_IWRITE | stat.S_IREAD)
                    lf.unlink()
                    deleted_lua = True
                except Exception as e:
                    return {"ok": False, "msg": f"刪除 Lua 檔案失敗 ({lf.name}): {e}"}

        # 先解除版本鎖定 (還原 ACF 與關聯 Manifest 為可讀寫)
        try:
            steam_manager.unlock_game_version(appid_str, sp)
        except Exception:
            pass

        # 🌟 自動還原線上補丁原始檔案 (.bak) 並清理補丁殘留
        from managers import onlinefix_manager
        try:
            onlinefix_manager.uninstall_fix(appid_str)
            lua_dir = self._config.get("lua_dir") or (Path(sp) / "config" / "lua")
            if lua_dir:
                onlinefix_manager.uninstall_lua(appid_str, lua_dir)
        except Exception:
            pass

        # 清除 manifest_updates.json 中的更新標記快取
        try:
            updates_file = config_manager.get_storage_dir() / "manifest_updates.json"
            if updates_file.exists():
                u_data = json.loads(updates_file.read_text(encoding="utf-8"))
                if appid_str in u_data:
                    del u_data[appid_str]
                    updates_file.write_text(json.dumps(u_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        # 🌟 若遊戲在 Steam 本地已安裝或下載中，直接喚起 Steam 原生解除安裝命令
        has_local_install = False
        try:
            acf_path = steam_manager.find_appmanifest_path(appid_str, sp)
            game_dir = onlinefix_manager._find_steam_game_dir(appid_str)
            if (acf_path and Path(acf_path).exists()) or (game_dir and Path(game_dir).exists()):
                has_local_install = True
                os.startfile(f"steam://uninstall/{appid_str}")
        except Exception as e:
            print(f"喚起 Steam 解除安裝失敗: {e}")

        self.invalidate_games_cache()
        if has_local_install:
            return {"ok": True, "has_steam_uninstall": True, "msg": f"已成功移除入庫與補丁，並已喚起 Steam 執行遊戲解除安裝 (AppID: {appid_str})"}
        else:
            return {"ok": True, "has_steam_uninstall": False, "msg": f"已成功卸載入庫遊戲 (AppID: {appid_str})"}

    def toggle_version(self, appid: str) -> Dict[str, Any]:
        """切換指定遊戲的 ACF / Lua / Manifest 版本鎖定狀態"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp: return {"ok": False, "msg": "找不到 Steam 目錄路徑"}
        st = steam_manager.get_game_manifest_lock_info(appid, sp)
        if st.get("is_locked"):
            ok, msg = steam_manager.unlock_game_version(appid, sp)
            new_locked = False
        else:
            ok, msg = steam_manager.lock_game_version(appid, sp, set_readonly=True)
            new_locked = True
        return {"ok": ok, "msg": msg, "is_locked": new_locked}

    def clean_phantom_acfs(self) -> Dict[str, Any]:
        """一鍵掃描並安全清理無實體檔案的幽靈 ACF 檔案 (徹底清空 Steam 錯誤下載排程)"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp:
            return {"ok": False, "msg": "找不到 Steam 路徑"}
        cleaned_cnt, cleaned_list = steam_manager.clean_phantom_appmanifests(sp)
        return {
            "ok": True,
            "cleaned_count": cleaned_cnt,
            "cleaned_list": cleaned_list,
            "msg": f"已成功清理 {cleaned_cnt} 個幽靈 ACF 檔案！" if cleaned_cnt > 0 else "目前遊戲庫非常乾淨，未發現任何幽靈 ACF 檔案。"
        }

    def sync_lua_autoupdate(self, restore_non_lua: bool = True) -> Dict[str, Any]:
        """智慧同步自動更新行為：僅對 Lua 關聯遊戲鎖定 AutoUpdateBehavior=1，正版遊戲維持/恢復 AutoUpdateBehavior=0"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp:
            return {"ok": False, "msg": "找不到 Steam 路徑"}
        res = steam_manager.sync_lua_games_autoupdate_behavior(sp, restore_non_lua=restore_non_lua)
        return {
            "ok": True,
            **res,
            "msg": f"自動更新隔離同步完成！已鎖定 {res.get('locked_lua_count', 0)} 個 Lua 遊戲，還原 {res.get('restored_normal_count', 0)} 個正版遊戲。"
        }

    def sync_local_manifests(self, appid: str = "") -> Dict[str, Any]:
        """
        零額度本機 Manifest 與 Lua 雙向自檢同步 (Self-Healing)：
        - 若指定 appid，精確自檢並校準該遊戲。
        - 若未指定 appid，全庫掃描所有本機 Lua 遊戲，比對 depotcache 實體檔案與 Lua 宣告，自動修復不一致之檔案！
        """
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp:
            return {"ok": False, "msg": "找不到 Steam 路徑"}

        if appid:
            r = steam_manager.verify_and_sync_local_manifests(str(appid), steam_path=sp)
            healed = r.get("healed", False)
            msg = f"AppID {appid} 本機校準完成！(已自動修復 Lua 宣告)" if healed else f"AppID {appid} 本機狀態完整吻合。"
            return {"ok": True, "result": r, "msg": msg}
        else:
            lua_dir = Path(sp) / "config" / "lua"
            if not lua_dir.exists():
                return {"ok": True, "healed_count": 0, "msg": "尚未發現任何 Lua 遊戲。"}
            healed_list = []
            for lf in lua_dir.glob("*.lua"):
                if lf.stem.isdigit() and lf.name != "manifest.lua":
                    r = steam_manager.verify_and_sync_local_manifests(lf.stem, steam_path=sp)
                    if r.get("healed"):
                        healed_list.append(lf.stem)
            msg = f"全庫本機同步完成！已自動校準修復 {len(healed_list)} 款遊戲的 Lua 宣告！" if healed_list else "全庫本機 Manifest 與 Lua 狀態已 100% 吻合！"
            return {"ok": True, "healed_count": len(healed_list), "healed_list": healed_list, "msg": msg}

    def get_lua(self, appid: str) -> str:
        """讀取指定遊戲的 Lua 內容"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp: return ""
        f = Path(sp) / "config" / "lua" / f"{appid}.lua"
        if f.exists():
            return f.read_text(encoding="utf-8", errors="ignore")
        return ""

    def save_lua(self, appid: str, content: str) -> bool:
        """儲存編輯後的 Lua 內容"""
        r = self.write_lua(appid, content)
        return r.get("ok", False)

    def list_game_dlcs(self, appid: str) -> List[Dict[str, Any]]:
        """讀取遊戲的已宣告 DLC 清單（精確排除內容 Depot、金鑰 Depot 與本體 AppID）"""
        lua = self.get_lua(appid)
        if not lua: return []

        # 1. 抓取所有 addappid 宣告的 ID，並排除主遊戲 ID
        raw_ids = set(re.findall(r'addappid\s*\(\s*(\d+)', lua))
        raw_ids.discard(str(appid))

        # 2. 排除所有在 setManifestid 中宣告的 Depot ID（Depot 才配置 Manifest，DLC 不會配置 Manifest）
        manifest_depots = set(re.findall(r'set[M|m]anifest[i|I]d\s*\(\s*(\d+)', lua))

        # 3. 排除帶有解密金鑰參數的 Depot ID: addappid(depotid, 0, "key")
        keyed_depots = set(re.findall(r'addappid\s*\(\s*(\d+)\s*,\s*\d+\s*,\s*[\'"][a-fA-F0-9]{16,}[\'"]', lua))

        # 純 DLC ID 清單
        dlc_ids = [did for did in raw_ids if did not in manifest_depots and did not in keyed_depots]

        # 4. 嘗試從本機遊戲快取讀取真實 DLC 名稱與封面
        game_cache = self._load_unified_game_cache()

        from utils.tw_converter import sanitize_game_name

        dlcs = []
        for did in sorted(dlc_ids, key=lambda x: int(x) if x.isdigit() else x):
            c_info = game_cache.get(did, {})
            name = c_info.get("name") or f"DLC_{did}"
            name = sanitize_game_name(name, did)
            header_img = c_info.get("header_image") or f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{did}/header.jpg"

            dlcs.append({
                "appid": did,
                "name": name,
                "image": header_img
            })
        return dlcs

    def clear_all(self) -> Dict[str, Any]:
        """一鍵清除所有已入庫遊戲"""
        sp = self._steam_path or steam_manager.find_steam_path()
        if not sp: return {"ok": False}
        lua_dir = Path(sp) / "config" / "lua"
        count = 0
        if lua_dir.exists():
            for f in lua_dir.glob("*.lua"):
                if f.name != "manifest.lua":
                    try:
                        import stat
                        try:
                            import win32file
                            win32file.SetFileAttributes(str(f), win32file.FILE_ATTRIBUTE_NORMAL)
                        except Exception:
                            pass
                        os.chmod(f, stat.S_IWRITE | stat.S_IREAD)
                        f.unlink()
                        count += 1
                    except Exception:
                        pass
        self.invalidate_games_cache()
        return {"ok": True, "count": count}

