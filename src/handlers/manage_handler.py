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

class ManageHandler:
    def get_updatable_games(self) -> List[Dict[str, Any]]:
        """
        全庫精確取得當前真正需要更新的遊戲名單 (杜絕前端快照時序差導致漏更)
        直接從 manifest_updates.json 讀取最新狀態，並交叉校驗本地 Lua 檔案
        """
        updates_file = Path(__file__).parent.parent / "data" / "manifest_updates.json"
        cache_file = Path(__file__).parent.parent / "data" / "game_cache.json"
        cached_updates = {}
        game_cache = {}

        if updates_file.exists():
            try:
                cached_updates = json.loads(updates_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        if cache_file.exists():
            try:
                game_cache = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        sp = self._steam_path or steam_manager.find_steam_path()
        lua_dir = Path(sp) / "config" / "lua" if sp else None

        results = []
        for aid, u in cached_updates.items():
            if not u.get("has_update"):
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
                "best_source": u.get("best_source", "ryuu")
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
            builtin_cache_file = Path(__file__).parent / "resources" / "builtin_game_cache.json"
            cache_file = Path(__file__).parent.parent / "data" / "game_cache.json"
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
            updates_file = Path(__file__).parent.parent / "data" / "manifest_updates.json"
            cached_updates = {}
            if updates_file.exists():
                try:
                    cached_updates = json.loads(updates_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            # 讀取所有具有 Online-Fix / ZeiGames 網盤補丁的 AppID 集合（利用記憶體快取）
            try:
                of_appids = set(onlinefix_manager.get_all_onlinefix_appids())
            except Exception:
                of_appids = set()

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
                    sdb_file = Path(__file__).parent.parent / "data" / "steamdb_cache" / f"{appid}.json"
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

                # 🌟 聯機標籤 (has_onlinefix)：嚴格只檢查 Google Drive / 雲端補丁庫是否收錄該遊戲 (藍色標籤 🎮 聯機)
                has_of = bool(appid in of_appids)

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
                    "has_onlinefix": has_of,             # 🌟 藍色邊框標記 (支援 Online-Fix 聯機補丁)
                    "version_status": version_status,
                    "latest_date": latest_date,
                    "best_source": best_source
                })

            # 排序：有更新者（黃色需更新項）置頂排列
            games.sort(key=lambda x: (0 if x["has_update"] else 1, x["name"].lower()))
            if cache_dirty:
                try:
                    cache_file.write_text(json.dumps(game_cache, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
            self._cached_games = games
            return list(self._cached_games)

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
        builtin_cache_file = Path(__file__).parent / "resources" / "builtin_game_cache.json"
        cache_file = Path(__file__).parent.parent / "data" / "game_cache.json"
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
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                    with urllib.request.urlopen(req, timeout=6, context=ctx) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        if data and str(aid) in data and data[str(aid)].get("success"):
                            d = data[str(aid)]["data"]
                            raw_name = d.get("name") or f"App_{aid}"
                            s_name = sanitize_game_name(raw_name, aid)
                            hdr = d.get("header_image") or ""
                            return aid, s_name, raw_name, hdr
                except Exception:
                    pass
                return aid, None, None, None

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
        供前端或啟動時主動呼叫：在背景守護執行緒中啟動全庫 Manifest 更新比對。
        立即回傳 0 延遲，不阻塞 UI，查出一筆即時向前端推播點亮一筆！
        """
        import threading
        if getattr(self, "_is_checking_updates", False):
            return {"ok": True, "already_running": True}

        t = threading.Thread(target=self.check_updates_async, kwargs={"force": force}, daemon=True)
        t.start()
        return {"ok": True, "status": "started"}

    def check_updates_async(self, force: bool = False) -> Dict[str, Any]:
        """
        全域主動搜尋並比對所有已入庫遊戲的最新 Manifest 版本狀態（守護執行緒，不卡頓 UI）
        並自動在背景補齊缺失的遊戲官方繁體名稱、英文原名與 CDN 封面圖片。
        支援即時逐筆推播 (window.onSingleGameUpdateChecked) 與增量快取持久化。
        """
        if getattr(self, "_is_checking_updates", False):
            return {"ok": True, "already_running": True, "updates": {}}
        self._is_checking_updates = True

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
        lua_files = [f for f in lua_dir.glob("*.lua") if f.name != "manifest.lua"]
        pattern = re.compile(r'^[ \t]*(?:--[^\n\r]*?)?set[M|m]anifest[i|I]d\s*\(\s*(\d+)\s*,\s*"(\d+)"', re.MULTILINE)

        # 🌟 配合全域更新輪詢一併同步 Google Drive 雲端補丁庫（內建 60 秒冷卻保護，最多 1 分鐘 1 次）
        try:
            from managers import onlinefix_manager
            onlinefix_manager.fetch_cloud_cache(force=force)
        except Exception:
            pass

        # 載入遊戲快取以備補全
        cache_file = Path(__file__).parent.parent / "data" / "game_cache.json"
        game_cache = {}
        if cache_file.exists():
            try:
                game_cache = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        updates_file = Path(__file__).parent.parent / "data" / "manifest_updates.json"
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
                v_stat = diff_info.get("version_status", "")
                diff_cnt = diff_info.get("diff_count", 0) or 0

                # 🌟 統一口徑：只有當線上庫有實質可更新版本時，has_update 才能為 True！
                # 若 SteamDB 官方有新版，但 Ryuu 尚未收錄（待雲端同步），本地已是目前能取得的最新版，has_update 必須為 False！
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
                    "appid": appid,
                    "name": cur_c.get("name") or (game_cache.get(appid, {}).get("name") if appid in game_cache else ""),
                    "has_update": has_up,
                    "version_status": raw_v,
                    "latest_date": diff_info.get("latest_date", "未知"),
                    "best_source": diff_info.get("best_source", "ryuu")
                }
                with save_lock:
                    updates[appid] = u_item
                    checked_counter[0] += 1

                # 每查好 5 筆即時安全落盤快取 (背景靜默，不在前端邊查邊跳動)
                if checked_counter[0] % 5 == 0:
                    save_progress()

            except Exception as e:
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
                cache_file.write_text(json.dumps(game_cache, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

        total_up = len([u for u in updates.values() if u.get("has_update")])
        # 🌟 全庫比對完全確認後一次性推送 (Atomic Delivery)
        self._push_js_event("onAllUpdatesCheckFinished", {
            "total": len(lua_files),
            "updated_count": total_up,
            "updates": updates
        })

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
            updates_file = Path(__file__).parent.parent / "data" / "manifest_updates.json"
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
        cache_file = Path(__file__).parent.parent / "data" / "game_cache.json"
        game_cache = {}
        if cache_file.exists():
            try:
                game_cache = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass

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

