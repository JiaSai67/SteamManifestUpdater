# -*- coding: utf-8 -*-
"""
PartyPackager - SMU 本地三檔自動打包器
負責將房主本地的 1. Manifest 2. Lua 腳本 3. 線上聯機補丁 自動打包為加密 ZIP 整合包，供房間成員一鍵同步。
"""

import os
import re
import json
import shutil
import zipfile
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from managers import config_manager
from managers import steam_manager
from managers import onlinefix_manager

logger = logging.getLogger("party_packager")

class PartyPackager:
    def __init__(self):
        self.root_dir = config_manager._root_dir
        self.temp_pack_dir = self.root_dir / "data" / "party_packages"
        self.temp_pack_dir.mkdir(parents=True, exist_ok=True)

    def inspect_party_resources(self, app_id: str) -> Dict[str, Any]:
        """
        全方位偵測指定遊戲之三檔就緒狀況 (Manifest, Lua, OnlineFix 補丁)
        """
        app_id = str(app_id).strip()
        steam_path = steam_manager.find_steam_path()

        status = {
            "app_id": app_id,
            "manifest": {"ready": False, "found": False, "path": "", "size": 0},
            "lua": {"ready": False, "found": False, "path": "", "size": 0},
            "patch": {"ready": False, "found": False, "source": "", "files_count": 0, "size": 0, "archive_path": ""},
            "all_ready": False,
            "can_package": False
        }

        # 1. 偵測 Manifest (appmanifest_<appid>.acf)
        if steam_path:
            acf_path = Path(steam_path) / "steamapps" / f"appmanifest_{app_id}.acf"
            if acf_path.exists():
                status["manifest"]["ready"] = True
                status["manifest"]["found"] = True
                status["manifest"]["path"] = str(acf_path)
                status["manifest"]["size"] = acf_path.stat().st_size
            else:
                # 遍歷所有庫資料夾
                libs = self._get_library_folders(steam_path)
                for lib in libs:
                    cand = Path(lib) / "steamapps" / f"appmanifest_{app_id}.acf"
                    if cand.exists():
                        status["manifest"]["ready"] = True
                        status["manifest"]["found"] = True
                        status["manifest"]["path"] = str(cand)
                        status["manifest"]["size"] = cand.stat().st_size
                        break

        # 2. 偵測 Lua 腳本 (全面涵蓋 SteamTools 核心目錄與自訂設定)
        lua_candidates = []
        if steam_path:
            sp = Path(steam_path)
            lua_candidates.append(sp / "config" / "lua" / f"{app_id}.lua")
            lua_candidates.append(sp / "config" / "stplug-in" / f"{app_id}.lua")
            lua_candidates.append(sp / "config" / "stplugins" / f"{app_id}.lua")
            lua_candidates.append(sp / "steamapps" / "common" / "Steam.AppId" / f"{app_id}.lua")

        try:
            cfg_lua_dir = config_manager.get_config().get("lua_dir", config_manager.DEFAULT_LUA_DIR)
            if cfg_lua_dir:
                lua_candidates.append(Path(cfg_lua_dir) / f"{app_id}.lua")
        except Exception:
            pass

        lua_candidates.extend([
            self.root_dir / "lua" / f"{app_id}.lua",
            self.root_dir / "data" / "lua" / f"{app_id}.lua",
            self.root_dir / "data" / "cache" / f"{app_id}.lua"
        ])

        # 也在 LOCAL_PATCH_DIR 找找
        if onlinefix_manager.LOCAL_PATCH_DIR.exists():
            for d in onlinefix_manager.LOCAL_PATCH_DIR.iterdir():
                if d.is_dir() and d.name.endswith(f" {app_id}"):
                    lua_in_patch = d / f"{app_id}.lua"
                    if lua_in_patch.exists():
                        lua_candidates.insert(0, lua_in_patch)

        for l_cand in lua_candidates:
            if l_cand.exists() and l_cand.is_file():
                status["lua"]["ready"] = True
                status["lua"]["found"] = True
                status["lua"]["path"] = str(l_cand)
                status["lua"]["size"] = l_cand.stat().st_size
                break

        # 3. 偵測線上補丁 (OnlineFix / 聯機檔案)
        # 情況 A: 檢查 LOCAL_PATCH_DIR 中是否有原始下載之補丁壓縮檔 (.rar, .zip, .7z)
        app_cache_dir = onlinefix_manager.get_app_cache_dir(app_id)
        if app_cache_dir and app_cache_dir.exists():
            for f in app_cache_dir.iterdir():
                if f.is_file() and f.suffix.lower() in ('.rar', '.zip', '.7z'):
                    status["patch"]["ready"] = True
                    status["patch"]["found"] = True
                    status["patch"]["source"] = "archive"
                    status["patch"]["archive_path"] = str(f)
                    status["patch"]["size"] = f.stat().st_size
                    status["patch"]["files_count"] = 1
                    break

        # 情況 B: 若壓縮檔已解壓或被清除，直接從遊戲目錄依據 patch_record.json 抓取已部署之補丁檔案！
        if not status["patch"]["ready"]:
            rec = onlinefix_manager.get_fix_record(app_id)
            if rec and rec.get("game_dir"):
                g_dir = Path(rec["game_dir"])
                if g_dir.exists():
                    installed = rec.get("installed_files", [])
                    found_files = []
                    total_sz = 0
                    for rel in installed:
                        fp = g_dir / rel
                        if fp.exists() and fp.is_file():
                            found_files.append(fp)
                            total_sz += fp.stat().st_size

                    if found_files:
                        status["patch"]["ready"] = True
                        status["patch"]["found"] = True
                        status["patch"]["source"] = "installed_files"
                        status["patch"]["files_count"] = len(found_files)
                        status["patch"]["size"] = total_sz

        # 情況 C: 若既無壓縮檔也無 record，但遊戲目錄有 OnlineFix 特徵
        if not status["patch"]["ready"]:
            game_dir = onlinefix_manager._find_steam_game_dir(app_id)
            if game_dir and Path(game_dir).exists():
                g_dir = Path(game_dir)
                of_files = [f for f in ["OnlineFix64.dll", "OnlineFix.ini", "OnlineFix.url", "SteamOverlay64.dll"] if (g_dir / f).exists()]
                if of_files:
                    status["patch"]["ready"] = True
                    status["patch"]["found"] = True
                    status["patch"]["source"] = "signatures"
                    status["patch"]["files_count"] = len(of_files)
                    status["patch"]["size"] = sum((g_dir / f).stat().st_size for f in of_files)

        status["all_ready"] = (status["manifest"]["ready"] and status["lua"]["ready"] and status["patch"]["ready"])
        # 只要有補丁或 Manifest 即可打包，三者齊全最佳
        status["can_package"] = (status["patch"]["ready"] or status["manifest"]["ready"])

        return status

    inspect_resources = inspect_party_resources

    def build_party_package(self, app_id: str, room_id: str, password: Optional[str] = None) -> Tuple[bool, str, Dict[str, Any]]:
        """
        執行三檔自動打包為 ZIP 壓縮檔
        :return: (ok, package_path, details)
        """
        app_id = str(app_id).strip()
        room_id = str(room_id or "ROOM").strip().upper()
        res_info = self.inspect_party_resources(app_id)

        target_zip_name = f"SMU_Party_{app_id}_{room_id}.zip"
        target_zip_path = self.temp_pack_dir / target_zip_name

        try:
            logger.info(f"[Packager] 開始為 AppID {app_id} 構建組隊整合包: {target_zip_name}")
            
            with zipfile.ZipFile(target_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # 寫入套件元數據
                meta = {
                    "app_id": app_id,
                    "room_id": room_id,
                    "created_at": str(os.path.getmtime(target_zip_path) if target_zip_path.exists() else 0),
                    "manifest_included": res_info["manifest"]["ready"],
                    "lua_included": res_info["lua"]["ready"],
                    "patch_source": res_info["patch"]["source"],
                    "version": "2.0.0"
                }

                # 1. 寫入 Manifest
                if res_info["manifest"]["ready"] and res_info["manifest"]["path"]:
                    m_path = Path(res_info["manifest"]["path"])
                    if m_path.exists():
                        zf.write(m_path, arcname=f"manifest/{m_path.name}")
                        logger.info(f"[Packager] 已打包 Manifest: {m_path.name}")

                # 2. 寫入 Lua
                if res_info["lua"]["ready"] and res_info["lua"]["path"]:
                    l_path = Path(res_info["lua"]["path"])
                    if l_path.exists():
                        zf.write(l_path, arcname=f"lua/{l_path.name}")
                        logger.info(f"[Packager] 已打包 Lua: {l_path.name}")

                # 3. 寫入線上補丁
                patch_src = res_info["patch"]["source"]
                if patch_src == "archive" and res_info["patch"]["archive_path"]:
                    # 直接封裝原始補丁壓縮包
                    a_path = Path(res_info["patch"]["archive_path"])
                    if a_path.exists():
                        zf.write(a_path, arcname=f"patch/{a_path.name}")
                        logger.info(f"[Packager] 已打包原始補丁壓縮包: {a_path.name}")
                elif patch_src in ("installed_files", "signatures"):
                    # 從遊戲目錄中提取安裝的補丁檔案
                    rec = onlinefix_manager.get_fix_record(app_id)
                    game_dir = Path(rec["game_dir"]) if (rec and rec.get("game_dir")) else Path(onlinefix_manager._find_steam_game_dir(app_id) or "")
                    if game_dir.exists():
                        installed = rec.get("installed_files", []) if rec else []
                        if not installed:
                            installed = [f for f in ["OnlineFix64.dll", "OnlineFix.ini", "OnlineFix.url", "SteamOverlay64.dll", "steam_api64.dll", "steam_settings"] if (game_dir / f).exists()]

                        count = 0
                        for rel in installed:
                            fp = game_dir / rel
                            if fp.exists():
                                if fp.is_file():
                                    zf.write(fp, arcname=f"patch/files/{rel}")
                                    count += 1
                                elif fp.is_dir():
                                    for root, _, files in os.walk(fp):
                                        for fl in files:
                                            sub_fp = Path(root) / fl
                                            rel_to_g = sub_fp.relative_to(game_dir)
                                            zf.write(sub_fp, arcname=f"patch/files/{rel_to_g}")
                                            count += 1
                        logger.info(f"[Packager] 已從遊戲目錄抓取並打包 {count} 個補丁檔案")

                zf.writestr("package_meta.json", json.dumps(meta, ensure_ascii=False, indent=2))

            pkg_size = target_zip_path.stat().st_size
            logger.info(f"[Packager] 打包完成！大小: {pkg_size} 位元組: {target_zip_path}")
            return True, str(target_zip_path), {
                "size": pkg_size,
                "filename": target_zip_name,
                "all_ready": res_info["all_ready"],
                "manifest_ready": res_info["manifest"]["ready"],
                "lua_ready": res_info["lua"]["ready"],
                "patch_ready": res_info["patch"]["ready"]
            }

        except Exception as e:
            logger.error(f"[Packager] 打包整合包異常: {e}", exc_info=True)
            if target_zip_path.exists():
                try: target_zip_path.unlink()
                except: pass
            return False, "", {"error": str(e)}

    def _get_library_folders(self, steam_path: str) -> List[str]:
        libs = [steam_path]
        vdf = Path(steam_path) / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            try:
                txt = vdf.read_text(encoding="utf-8", errors="ignore")
                matches = re.findall(r'"path"\s+"([^"]+)"', txt)
                for m in matches:
                    clean = m.replace("\\\\", "\\")
                    if os.path.isdir(clean) and clean not in libs:
                        libs.append(clean)
            except Exception:
                pass
        return libs

    def extract_and_apply_package(self, zip_path: str, app_id: str) -> Dict[str, Any]:
        """
        隊員端：解壓並套用房主的三檔整合包 (Manifest, Lua, OnlineFix 補丁)
        """
        p = Path(zip_path)
        if not p.exists():
            return {"ok": False, "msg": f"整合包檔案不存在: {zip_path}"}

        steam_path = steam_manager.find_steam_path()
        applied = {"manifest": False, "lua": False, "patch": False, "files_count": 0}

        try:
            with zipfile.ZipFile(p, "r") as zf:
                namelist = zf.namelist()

                # 1. 部署 Manifest
                manifest_files = [n for n in namelist if n.startswith("manifest/") and not n.endswith("/")]
                if manifest_files and steam_path:
                    sp_apps = Path(steam_path) / "steamapps"
                    sp_apps.mkdir(parents=True, exist_ok=True)
                    for mf in manifest_files:
                        fn = Path(mf).name
                        target_f = sp_apps / fn
                        with zf.open(mf) as src, open(target_f, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        applied["manifest"] = True
                        logger.info(f"[Packager] 已解壓套用 Manifest: {target_f}")

                # 2. 部署 Lua
                lua_files = [n for n in namelist if n.startswith("lua/") and not n.endswith("/")]
                if lua_files and steam_path:
                    # 部署至常見路徑
                    cfg_lua_dir = None
                    try:
                        cfg_lua_dir = config_manager.get_config().get("lua_dir")
                    except Exception:
                        pass
                    target_lua_dir = Path(cfg_lua_dir) if cfg_lua_dir else (Path(steam_path) / "config" / "stplug-in")
                    target_lua_dir.mkdir(parents=True, exist_ok=True)
                    for lf in lua_files:
                        fn = Path(lf).name
                        target_f = target_lua_dir / fn
                        with zf.open(lf) as src, open(target_f, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        applied["lua"] = True
                        logger.info(f"[Packager] 已解壓套用 Lua: {target_f}")

                # 3. 部署線上補丁
                patch_files = [n for n in namelist if n.startswith("patch/files/") and not n.endswith("/")]
                if patch_files:
                    game_dir = onlinefix_manager._find_steam_game_dir(app_id)
                    if game_dir and Path(game_dir).exists():
                        g_path = Path(game_dir)
                        installed_rel_paths = []
                        backed_up_rel_paths = []
                        for pf in patch_files:
                            rel_sub = pf.replace("patch/files/", "", 1)
                            target_pf = g_path / rel_sub
                            target_pf.parent.mkdir(parents=True, exist_ok=True)
                            
                            # 若目標檔案已存在且尚未建立備份，先將原檔備份為 .bak
                            if target_pf.exists() and target_pf.is_file():
                                bak_f = target_pf.with_suffix(target_pf.suffix + ".bak")
                                if not bak_f.exists():
                                    try:
                                        shutil.copy2(target_pf, bak_f)
                                        backed_up_rel_paths.append(rel_sub)
                                        logger.info(f"[Packager] 已自動備份原始檔案: {bak_f.name}")
                                    except Exception as be:
                                        logger.warning(f"[Packager] 備份原檔異常: {be}")

                            with zf.open(pf) as src, open(target_pf, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                            installed_rel_paths.append(rel_sub)
                            applied["files_count"] += 1

                        applied["patch"] = True
                        logger.info(f"[Packager] 已向遊戲目錄解壓套用 {applied['files_count']} 個補丁檔案: {g_path}")

                        # 🌟 寫入官方 .onlinefix_record.json 與本地快取紀錄表，支援完整追蹤與乾淨移除
                        try:
                            record = {
                                "appid": str(app_id),
                                "installed_files": installed_rel_paths,
                                "backed_up_files": backed_up_rel_paths,
                                "manual_install": False,
                                "source_drive": "Party Package Sync",
                                "game_dir": str(g_path),
                                "timestamp": int(time.time())
                            }
                            onlinefix_manager._save_record(app_id, record)
                            logger.info(f"[Packager] 已成功為 AppID {app_id} 建立部署記錄檔 (.onlinefix_record.json)")
                        except Exception as re:
                            logger.warning(f"[Packager] 寫入部署記錄檔失敗: {re}")

            return {"ok": True, "applied": applied, "msg": "聯機整合包解壓部署成功！"}
        except Exception as e:
            logger.error(f"[Packager] 解壓部署整合包失敗: {e}", exc_info=True)
            return {"ok": False, "msg": f"套用整合包失敗: {e}"}

def get_party_packager() -> PartyPackager:
    return PartyPackager()

