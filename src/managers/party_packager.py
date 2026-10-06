# -*- coding: utf-8 -*-
"""
PartyPackager - SMU 本地三檔自動打包器
負責將房主本地的 1. Manifest 2. Lua 腳本 3. 線上聯機補丁 自動打包為加密 ZIP 整合包，供房間成員一鍵同步。
"""

import os
import re
import time
import stat
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
        全方位偵測指定遊戲之三檔就緒狀況 (實體 .manifest 清單, Lua 腳本, OnlineFix 補丁)
        """
        app_id = str(app_id).strip()
        steam_path = steam_manager.find_steam_path()

        status = {
            "app_id": app_id,
            "manifest": {"ready": False, "found": False, "files": [], "missing_files": [], "count": 0, "size": 0},
            "acf": {"ready": False, "found": False, "path": "", "size": 0},
            "lua": {"ready": False, "found": False, "path": "", "size": 0},
            "patch": {"ready": False, "found": False, "source": "", "files_count": 0, "size": 0, "archive_path": ""},
            "all_ready": False,
            "can_package": False
        }

        # 1. 偵測 Lua 腳本 (全面涵蓋 SteamTools 核心目錄與自訂設定)
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

        chosen_lua_path = None
        for l_cand in lua_candidates:
            if l_cand.exists() and l_cand.is_file():
                status["lua"]["ready"] = True
                status["lua"]["found"] = True
                status["lua"]["path"] = str(l_cand)
                status["lua"]["size"] = l_cand.stat().st_size
                chosen_lua_path = l_cand
                break

        # 2. 偵測實體 Manifest (位於 steam/depotcache 或是 steam/config/depotcache 的 .manifest 檔案)
        manifest_files_found = []
        missing_mfs = []
        total_mf_size = 0

        declared_manifests = []
        if chosen_lua_path:
            try:
                l_content = chosen_lua_path.read_text(encoding="utf-8", errors="ignore")
                pattern = re.compile(r'^[ \t]*setManifestid\(\s*(\d+)\s*,\s*["\']?(\d+)["\']?(?:,\s*(\d+))?\s*\)', re.MULTILINE)
                declared_manifests = pattern.findall(l_content)
            except Exception as le:
                logger.debug(f"[Packager] 解析 Lua 宣告清單失敗: {le}")

        if steam_path and declared_manifests:
            sp = Path(steam_path)
            depot_dir = sp / "depotcache"
            backup_dir = sp / "config" / "depotcache"
            backup_dir.mkdir(parents=True, exist_ok=True)

            for d_id, m_id, *rest in declared_manifests:
                if str(m_id) == "0":
                    continue
                mf_name = f"{d_id}_{m_id}.manifest"
                src_depot = depot_dir / mf_name
                src_backup = backup_dir / mf_name
                target_mf = None

                if src_backup.exists() and src_backup.stat().st_size > 0:
                    target_mf = src_backup
                    # 若 depotcache 缺失，順便鏡像同步
                    if not src_depot.exists():
                        try:
                            shutil.copy2(src_backup, src_depot)
                            logger.info(f"[Packager] 自動從金庫鏡像還原清單至 depotcache: {mf_name}")
                        except Exception:
                            pass
                elif src_depot.exists() and src_depot.stat().st_size > 0:
                    target_mf = src_depot
                    # 🌟 順手自動備份至 config/depotcache 防護金庫，避免 Steam 惡意清除！
                    try:
                        shutil.copy2(src_depot, src_backup)
                        logger.info(f"[Packager] 自動備份清單至 config/depotcache 金庫: {mf_name}")
                    except Exception:
                        pass
                elif chosen_lua_path and (chosen_lua_path.parent / mf_name).exists():
                    target_mf = chosen_lua_path.parent / mf_name

                if target_mf and target_mf.exists():
                    manifest_files_found.append(str(target_mf))
                    total_mf_size += target_mf.stat().st_size
                else:
                    missing_mfs.append(mf_name)

        if declared_manifests and not missing_mfs and manifest_files_found:
            status["manifest"]["ready"] = True
            status["manifest"]["found"] = True
            status["manifest"]["files"] = manifest_files_found
            status["manifest"]["count"] = len(manifest_files_found)
            status["manifest"]["size"] = total_mf_size
        else:
            status["manifest"]["ready"] = False
            status["manifest"]["found"] = bool(manifest_files_found)
            status["manifest"]["files"] = manifest_files_found
            status["manifest"]["missing_files"] = missing_mfs
            status["manifest"]["count"] = len(manifest_files_found)
            status["manifest"]["size"] = total_mf_size

        # 3. 偵測 appmanifest_<appid>.acf (作為輔助設定檔，非實體清單)
        if steam_path:
            acf_path = Path(steam_path) / "steamapps" / f"appmanifest_{app_id}.acf"
            if acf_path.exists():
                status["acf"]["ready"] = True
                status["acf"]["found"] = True
                status["acf"]["path"] = str(acf_path)
                status["acf"]["size"] = acf_path.stat().st_size
            else:
                libs = self._get_library_folders(steam_path)
                for lib in libs:
                    cand = Path(lib) / "steamapps" / f"appmanifest_{app_id}.acf"
                    if cand.exists():
                        status["acf"]["ready"] = True
                        status["acf"]["found"] = True
                        status["acf"]["path"] = str(cand)
                        status["acf"]["size"] = cand.stat().st_size
                        break

        # 4. 偵測線上補丁 (OnlineFix / 聯機檔案)
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
        # 只要有補丁或 Manifest 或 Lua 即可打包
        status["can_package"] = (status["patch"]["ready"] or status["manifest"]["ready"] or status["lua"]["ready"])

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
                    "manifest_files": [Path(f).name for f in res_info["manifest"]["files"]],
                    "lua_included": res_info["lua"]["ready"],
                    "patch_source": res_info["patch"]["source"],
                    "version": "2.0.2"
                }

                # 1. 寫入實體 Manifest (.manifest 二進位清單)
                if res_info["manifest"]["files"]:
                    for mf_p in res_info["manifest"]["files"]:
                        m_path = Path(mf_p)
                        if m_path.exists():
                            zf.write(m_path, arcname=f"manifest/{m_path.name}")
                            logger.info(f"[Packager] 已打包實體 Manifest: {m_path.name}")

                # 2. 寫入輔助 ACF 設定檔 (若有)
                if res_info["acf"]["ready"] and res_info["acf"]["path"]:
                    acf_p = Path(res_info["acf"]["path"])
                    if acf_p.exists():
                        zf.write(acf_p, arcname=f"acf/{acf_p.name}")
                        logger.info(f"[Packager] 已打包輔助 ACF: {acf_p.name}")

                # 3. 寫入 Lua 腳本
                if res_info["lua"]["ready"] and res_info["lua"]["path"]:
                    l_path = Path(res_info["lua"]["path"])
                    if l_path.exists():
                        zf.write(l_path, arcname=f"lua/{l_path.name}")
                        logger.info(f"[Packager] 已打包 Lua: {l_path.name}")

                # 4. 寫入線上補丁
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
                "manifest_count": res_info["manifest"]["count"],
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
        隊員端：解壓並套用房主的三檔整合包：
        1. 實體 .manifest 檔案解壓部署至 Steam/depotcache 與 Steam/config/depotcache (防護金庫)
        2. 輔助 ACF 部署至 Steam/steamapps
        3. Lua 腳本部署至 Steam/config/stplug-in 與 Steam/config/lua
        4. 線上聯機補丁套用至遊戲目錄 (若遊戲已就緒)
        """
        import stat
        p = Path(zip_path)
        if not p.exists():
            return {"ok": False, "msg": f"整合包檔案不存在: {zip_path}"}

        steam_path = steam_manager.find_steam_path()
        applied = {"manifest": False, "manifest_count": 0, "lua": False, "patch": False, "files_count": 0}

        try:
            with zipfile.ZipFile(p, "r") as zf:
                namelist = zf.namelist()

                # 1. 部署實體 Manifest 清單至 Steam/depotcache 與 Steam/config/depotcache
                manifest_files = [n for n in namelist if n.startswith("manifest/") and n.endswith(".manifest")]
                if manifest_files and steam_path:
                    sp_depot = Path(steam_path) / "depotcache"
                    sp_config_depot = Path(steam_path) / "config" / "depotcache"
                    sp_depot.mkdir(parents=True, exist_ok=True)
                    sp_config_depot.mkdir(parents=True, exist_ok=True)

                    for mf in manifest_files:
                        fn = Path(mf).name
                        target_depot = sp_depot / fn
                        target_backup = sp_config_depot / fn

                        if target_depot.exists():
                            try: os.chmod(target_depot, stat.S_IWRITE | stat.S_IREAD)
                            except Exception: pass
                        if target_backup.exists():
                            try: os.chmod(target_backup, stat.S_IWRITE | stat.S_IREAD)
                            except Exception: pass

                        with zf.open(mf) as src, open(target_depot, "wb") as dst:
                            shutil.copyfileobj(src, dst)

                        # 取消唯讀，並永久備份至金庫
                        try:
                            os.chmod(target_depot, stat.S_IWRITE | stat.S_IREAD)
                            shutil.copy2(target_depot, target_backup)
                            os.chmod(target_backup, stat.S_IWRITE | stat.S_IREAD)
                        except Exception:
                            pass

                        applied["manifest_count"] += 1
                        logger.info(f"[Packager] 已解壓套用實體 Manifest 並同步金庫備份: {fn}")

                    if applied["manifest_count"] > 0:
                        applied["manifest"] = True

                # 2. 部署 ACF 遊戲設定檔 (若有)
                acf_files = [n for n in namelist if (n.startswith("acf/") or n.startswith("manifest/")) and n.endswith(".acf")]
                if acf_files and steam_path:
                    sp_apps = Path(steam_path) / "steamapps"
                    sp_apps.mkdir(parents=True, exist_ok=True)
                    for af in acf_files:
                        fn = Path(af).name
                        target_acf = sp_apps / fn
                        if target_acf.exists():
                            try: os.chmod(target_acf, stat.S_IWRITE | stat.S_IREAD)
                            except Exception: pass
                        with zf.open(af) as src, open(target_acf, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        logger.info(f"[Packager] 已解壓套用輔助 ACF: {target_acf}")

                # 3. 部署 Lua 腳本
                lua_files = [n for n in namelist if n.startswith("lua/") and n.endswith(".lua")]
                if lua_files and steam_path:
                    cfg_lua_dir = None
                    try:
                        cfg_lua_dir = config_manager.get_config().get("lua_dir")
                    except Exception:
                        pass
                    target_dirs = [Path(steam_path) / "config" / "stplug-in", Path(steam_path) / "config" / "lua"]
                    if cfg_lua_dir:
                        target_dirs.append(Path(cfg_lua_dir))

                    for td in target_dirs:
                        td.mkdir(parents=True, exist_ok=True)
                        for lf in lua_files:
                            fn = Path(lf).name
                            target_f = td / fn
                            if target_f.exists():
                                try: os.chmod(target_f, stat.S_IWRITE | stat.S_IREAD)
                                except Exception: pass
                            with zf.open(lf) as src, open(target_f, "wb") as dst:
                                shutil.copyfileobj(src, dst)

                    applied["lua"] = True
                    logger.info(f"[Packager] 已解壓套用 Lua 腳本至 {len(target_dirs)} 個目錄")

                # 4. 部署線上補丁 (若遊戲主程式目錄已存在)
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
                                try: os.chmod(target_pf, stat.S_IWRITE | stat.S_IREAD)
                                except Exception: pass

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

                        # 🌟 防毒軟體 (Windows Defender) 即時隔離/攔截抽查
                        quarantined_files = []
                        for rel_p in installed_rel_paths:
                            f_path = g_path / rel_p
                            if not f_path.exists() and any(f_path.name.lower().endswith(ext) for ext in [".dll", ".exe", ".ini"]):
                                quarantined_files.append(f_path.name)
                        if quarantined_files:
                            err_msg = f"檔案遭防毒軟體 (Windows Defender) 即時隔離: {', '.join(quarantined_files[:3])}"
                            logger.warning(f"[Packager] {err_msg}")
                            return {
                                "ok": False,
                                "is_antivirus_blocked": True,
                                "game_dir": str(g_path),
                                "blocked_files": quarantined_files,
                                "msg": f"防毒軟體攔截：檔案解壓後遭隔離 ({', '.join(quarantined_files[:2])})，請新增防毒排除項"
                            }

            return {"ok": True, "applied": applied, "msg": "聯機整合包解壓部署成功！"}
        except Exception as e:
            err_str = str(e)
            logger.error(f"[Packager] 解壓部署整合包失敗: {e}", exc_info=True)
            # 判斷是否為 Windows Defender WinError 225 或權限阻擋
            is_av = False
            gdir = str(game_dir) if ('game_dir' in locals() and game_dir) else ""
            if "225" in err_str or "virus" in err_str.lower() or "operation did not complete successfully" in err_str.lower():
                is_av = True
                msg = "防毒軟體 (Windows Defender) 攔截阻止補丁寫入！請將遊戲資料夾加入白名單排除項"
            elif isinstance(e, PermissionError) or "access is denied" in err_str.lower():
                is_av = True
                msg = "寫入檔案被拒 (疑似防毒軟體鎖定檔案或權限不足)，請新增防毒排除項或以管理員身分重試"
            else:
                msg = f"套用整合包失敗: {e}"

            return {
                "ok": False,
                "is_antivirus_blocked": is_av,
                "game_dir": gdir,
                "msg": msg
            }

    def apply_patch_files(self, package_zip_path: str, app_id: str) -> Dict[str, Any]:
        """
        專屬獨立套用線上補丁：
        當 Steam 遊戲主程式剛下載完成或已安裝時，將整合包內的 patch/files/* 解壓套用至遊戲目錄。
        """
        p = Path(package_zip_path)
        if not p.exists():
            return {"ok": False, "msg": f"找不到整合包檔案: {package_zip_path}"}

        game_dir = onlinefix_manager._find_steam_game_dir(app_id)
        if not game_dir or not Path(game_dir).exists():
            return {"ok": False, "msg": f"尚未找到 AppID {app_id} 的遊戲目錄，請確認 Steam 是否已下載安裝完成"}

        g_path = Path(game_dir)
        applied_count = 0
        installed_rel_paths = []
        backed_up_rel_paths = []

        try:
            with zipfile.ZipFile(p, "r") as zf:
                namelist = zf.namelist()
                patch_files = [n for n in namelist if n.startswith("patch/files/") and not n.endswith("/")]
                if not patch_files:
                    return {"ok": True, "msg": "整合包內無專屬線上補丁 (純 Manifest/Lua 入庫)", "files_count": 0}

                for pf in patch_files:
                    rel_sub = pf.replace("patch/files/", "", 1)
                    target_pf = g_path / rel_sub
                    target_pf.parent.mkdir(parents=True, exist_ok=True)

                    if target_pf.exists() and target_pf.is_file():
                        bak_f = target_pf.with_suffix(target_pf.suffix + ".bak")
                        if not bak_f.exists():
                            try:
                                shutil.copy2(target_pf, bak_f)
                                backed_up_rel_paths.append(rel_sub)
                            except Exception as be:
                                logger.warning(f"[Packager] 備份原檔失敗: {be}")

                    if target_pf.exists():
                        try: os.chmod(target_pf, stat.S_IWRITE | stat.S_IREAD)
                        except Exception: pass
                    with zf.open(pf) as src, open(target_pf, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    installed_rel_paths.append(rel_sub)
                    applied_count += 1

            # 寫入部署記錄檔
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
                logger.warning(f"[Packager] 寫入記錄檔失敗: {re}")

            # 防毒隔離抽查
            quarantined_files = []
            for rel_p in installed_rel_paths:
                f_path = g_path / rel_p
                if not f_path.exists() and any(f_path.name.lower().endswith(ext) for ext in [".dll", ".exe", ".ini"]):
                    quarantined_files.append(f_path.name)
            if quarantined_files:
                return {
                    "ok": False,
                    "is_antivirus_blocked": True,
                    "game_dir": str(g_path),
                    "blocked_files": quarantined_files,
                    "msg": f"防毒軟體攔截：補丁解壓後遭隔離 ({', '.join(quarantined_files[:2])})，請新增防毒排除項"
                }

            return {"ok": True, "files_count": applied_count, "msg": f"已成功套用 {applied_count} 個線上補丁檔案"}
        except Exception as e:
            err_str = str(e)
            is_av = ("225" in err_str or "virus" in err_str.lower() or isinstance(e, PermissionError))
            return {
                "ok": False,
                "is_antivirus_blocked": is_av,
                "game_dir": str(g_path),
                "msg": f"補丁套用失敗: {e}"
            }

def get_party_packager() -> PartyPackager:
    return PartyPackager()

