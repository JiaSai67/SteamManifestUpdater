import os
import re
import json
import zlib
import time
import stat
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Callable

from managers import config_manager, steam_manager

class UnifiedManifestManager:
    """
    三方聚合 Manifest 與 Lua 管理器 (GitHub + Ryuu + Lua.tools)
    1. 同時搜尋 GitHub (P-ToyStore)、Ryuu (generator.ryuu.lol)、Lua.tools 三大來源。
    2. 自動精準比對哪一邊提供的 Manifest 版本最新。
    3. 自動決定最佳下載策略，並完成 Manifest 解壓、Lua 更新/自適應拼裝、ACF 防 401 鎖定。
    """
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = UnifiedManifestManager()
        return cls._instance

    def __init__(self):
        self.config = config_manager.get_config()
        self.github_owner = "P-ToyStore"
        self.github_repo = "SteamManifestCache_Pro"
        self.keys_api_url = "https://api.993499094.xyz/depotkeys.json"
        self._depot_keys_cache = None

    def get_cached_depot_keys(self) -> Dict[str, str]:
        """讀取或快取公開 23.9 萬把 DepotKeys"""
        if self._depot_keys_cache is not None:
            return self._depot_keys_cache
        
        # 本地快取檔案
        cache_file = config_manager._root_dir / "data" / "cache" / "depotkeys.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    self._depot_keys_cache = json.load(f)
                    return self._depot_keys_cache
            except Exception:
                pass
                
        # 聯網獲取
        try:
            req = urllib.request.Request(self.keys_api_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self._depot_keys_cache = data
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                return self._depot_keys_cache
        except Exception as e:
            print(f"[UnifiedManifestManager] 獲取公共 DepotKeys 失敗: {e}")
            return {}

    def search_all_sources(self, appid: str, timeout: int = 6) -> Dict[str, Any]:
        """
        同時搜尋三方來源 (GitHub, Ryuu, Lua.tools)，並裁定哪一邊版本最新
        """
        appid_str = str(appid).strip()
        result = {
            "appid": appid_str,
            "best_source": "github",
            "best_reason": "",
            "github": {"available": False, "depots": {}, "time": "未知", "appinfo_vdf": None},
            "ryuu": {"available": False, "depots": {}, "time": "未知"},
            "luatools": {"available": False, "depots": {}, "time": "未知"},
            "summary": ""
        }

        # 1. 搜尋 GitHub (P-ToyStore)
        gh_data = self._query_github(appid_str, timeout)
        result["github"] = gh_data

        # 2. 搜尋 Ryuu (generator.ryuu.lol)
        ryuu_data = self._query_ryuu(appid_str, timeout)
        result["ryuu"] = ryuu_data

        # 3. 搜尋 Lua.tools (若有快取或輕量檢查)
        lt_data = self._query_luatools(appid_str, timeout)
        result["luatools"] = lt_data

        # 4. 版本比對與優先級仲裁 (Arbitration)
        self._arbitrate_best_source(result)
        return result

    def _parse_vdf(self, text: str) -> Dict[str, Any]:
        """層級遞迴下降 VDF 鍵值對解析器"""
        root = {}
        stack = [root]
        tokens = re.findall(r'"([^"]*)"|(\{)|(\})', text)
        current_key = None
        for val, open_b, close_b in tokens:
            if open_b:
                new_dict = {}
                if stack and current_key:
                    stack[-1][current_key] = new_dict
                    stack.append(new_dict)
                    current_key = None
            elif close_b:
                if len(stack) > 1:
                    stack.pop()
            elif val is not None:
                if current_key is None:
                    current_key = val
                else:
                    stack[-1][current_key] = val
                    current_key = None
        return root

    def _query_github(self, appid: str, timeout: int) -> Dict[str, Any]:
        """查詢 GitHub 倉庫 (Raw-First: 優先讀取 appinfo.vdf，0 API 開銷，永不 403 限流)"""
        data = {"available": False, "depots": {}, "time": "無", "files": []}
        
        # 1. 優先嘗試 Raw appinfo.vdf
        vdf_url = f"https://raw.githubusercontent.com/{self.github_owner}/{self.github_repo}/{appid}/appinfo.vdf"
        try:
            req = urllib.request.Request(vdf_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                vdf_text = resp.read().decode("utf-8")
                
            parsed = self._parse_vdf(vdf_text)
            appinfo = parsed.get("appinfo", {})
            depots = appinfo.get("depots", {})
            for did, dval in depots.items():
                if did.isdigit() and isinstance(dval, dict):
                    m_block = dval.get("manifests", {})
                    if isinstance(m_block, dict):
                        pub = m_block.get("public", {})
                        if isinstance(pub, dict) and "gid" in pub:
                            data["depots"][did] = str(pub["gid"])
                            
            # 提取更新時間
            pub_branch = depots.get("branches", {}).get("public", {}) if isinstance(depots.get("branches"), dict) else {}
            ts = pub_branch.get("timeupdated")
            if ts and str(ts).isdigit():
                data["time"] = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M")
                
            if data["depots"]:
                data["available"] = True
                return data
        except Exception:
            pass

        # 2. 回退到 GitHub API (若 Raw 獲取失敗)
        try:
            url = f"https://api.github.com/repos/{self.github_owner}/{self.github_repo}/contents/?ref={appid}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                files = json.loads(resp.read().decode("utf-8"))
                for f in files:
                    fname = f.get("name", "")
                    data["files"].append(fname)
                    m = re.match(r"^(\d+)_(\d+)\.manifest$", fname)
                    if m:
                        did, gid = m.group(1), m.group(2)
                        data["depots"][did] = gid
                data["available"] = len(data["depots"]) > 0
        except Exception:
            pass
        return data

    def _query_ryuu(self, appid: str, timeout: int) -> Dict[str, Any]:
        """查詢 generator.ryuu.lol"""
        data = {"available": False, "depots": {}, "time": "無"}
        try:
            url = f"https://generator.ryuu.lol/manifestinfo/{appid}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                depots = res.get("branch_manifests", {}).get("public", {}).get("depots", {})
                if depots:
                    data["depots"] = {str(k): str(v) for k, v in depots.items()}
                    data["available"] = True
                ts = res.get("timestamp")
                if ts:
                    try:
                        data["time"] = datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        data["time"] = str(ts)
        except Exception:
            pass
        return data

    def _query_luatools(self, appid: str, timeout: int) -> Dict[str, Any]:
        """查詢 Lua.tools 快取/公共接口"""
        data = {"available": False, "depots": {}, "time": "無"}
        # Lua.tools 通常由 WebEngine 查詢，此處保留接口結構
        return data

    def _arbitrate_best_source(self, result: Dict[str, Any]):
        """
        仲裁哪個來源提供最新 Manifest
        規則：
        1. 若 GitHub 與 Ryuu 的 Manifest GID 完全相同 -> 判定為同版本，優先選擇 GitHub (免配額、直連、零429)。
        2. 若兩者 GID 不同 -> 比對時間戳，較晚/更新者獲勝。
        3. 若一方無資料，由有資料方獲勝。
        """
        gh = result["github"]
        ryuu = result["ryuu"]

        gh_ok = gh.get("available", False)
        ryuu_ok = ryuu.get("available", False)

        if gh_ok and ryuu_ok:
            # 比較主 depot 的 GID
            gh_depots = gh.get("depots", {})
            ryuu_depots = ryuu.get("depots", {})
            
            # 檢查交集 depot
            common_keys = set(gh_depots.keys()) & set(ryuu_depots.keys())
            if common_keys:
                all_match = all(gh_depots[k] == ryuu_depots[k] for k in common_keys)
                if all_match:
                    result["best_source"] = "github"
                    result["best_reason"] = "GitHub 與 Ryuu 版本一致 (均為最新)，優先使用 GitHub 免配額高速源"
                else:
                    # GID 不同，比較時間戳
                    gh_time = gh.get("time", "")
                    ryuu_time = ryuu.get("time", "")
                    if gh_time > ryuu_time:
                        result["best_source"] = "github"
                        result["best_reason"] = f"⚡ GitHub 版本較新 ({gh_time})"
                    else:
                        result["best_source"] = "ryuu"
                        result["best_reason"] = f"⚡ Ryuu 版本較新 ({ryuu_time})"
            else:
                result["best_source"] = "github"
                result["best_reason"] = "優先使用 GitHub 倉庫"
        elif gh_ok and not ryuu_ok:
            result["best_source"] = "github"
            result["best_reason"] = "僅 GitHub 倉庫收錄此遊戲"
        elif not gh_ok and ryuu_ok:
            result["best_source"] = "ryuu"
            result["best_reason"] = "僅 Ryuu 平台收錄此遊戲"
        else:
            result["best_source"] = "none"
            result["best_reason"] = "所有來源均無此遊戲 Manifest"

    def deploy_best_manifest(self, appid: str, search_result: Dict[str, Any], progress_cb: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
        """
        根據搜尋仲裁結果，自動執行最佳下載並完成全套部署 (Manifest + Lua + ACF 防 401)
        """
        best_source = search_result.get("best_source", "github")
        if best_source == "github":
            return self._deploy_from_github(appid, search_result, progress_cb)
        elif best_source == "ryuu":
            return self._deploy_from_ryuu(appid, progress_cb)
        else:
            return False, "無可用來源"

    def _deploy_from_github(self, appid: str, search_result: Dict[str, Any], progress_cb: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
        """從 GitHub 下載 Manifest、解壓 Pro 格式、更新/組裝 Lua、修復 ACF"""
        depotcache_dir = steam_manager.get_depotcache_path()
        if not depotcache_dir or not os.path.exists(depotcache_dir):
            return False, "無法取得 Steam depotcache 目錄"

        gh_info = search_result.get("github", {})
        depots = gh_info.get("depots", {})
        if not depots:
            return False, "GitHub 倉庫無可用 Depot 清單"

        total_depots = len(depots)
        if progress_cb: progress_cb(f"正在從 GitHub 下載 {total_depots} 個 Manifest 清單...")

        # 1. 逐個下載 Manifest 檔案並解壓 Pro 格式，支援 CDN 鏡像降級
        downloaded_count = 0
        for idx, (did, gid) in enumerate(depots.items(), start=1):
            manifest_name = f"{did}_{gid}.manifest"
            target_path = os.path.join(depotcache_dir, manifest_name)
            
            if progress_cb: progress_cb(f"正在下載 Depot {did} ({idx}/{total_depots})...")

            urls_to_try = [
                f"https://raw.githubusercontent.com/{self.github_owner}/{self.github_repo}/{appid}/{manifest_name}",
                f"https://ghproxy.net/https://raw.githubusercontent.com/{self.github_owner}/{self.github_repo}/{appid}/{manifest_name}",
                f"https://fastly.jsdelivr.net/gh/{self.github_owner}/{self.github_repo}@{appid}/{manifest_name}"
            ]
            
            raw_bytes = None
            for u in urls_to_try:
                try:
                    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
                    raw_bytes = urllib.request.urlopen(req, timeout=12).read()
                    if raw_bytes and len(raw_bytes) > 0:
                        break
                except Exception:
                    continue

            if raw_bytes:
                try:
                    # 解壓檢測：若是 Pro 壓縮格式 (Magic 0x78DA)，去頭 10 字節 raw deflate
                    placed_bytes = self._decompress_manifest(raw_bytes)
                    with open(target_path, "wb") as f:
                        f.write(placed_bytes)
                    downloaded_count += 1
                except Exception as e:
                    print(f"[UnifiedManifestManager] 解壓寫入 Depot {did} 失敗: {e}")
            else:
                print(f"[UnifiedManifestManager] 鏡像下載 Depot {did} ({manifest_name}) 均失敗")

        if downloaded_count == 0:
            return False, "下載 Manifest 失敗 (網路超時或檔案遺失)"

        if progress_cb: progress_cb("Manifest 下載完成，正在更新/組裝 Lua 腳本...")

        # 2. 更新或自主拼裝 Lua
        lua_dir = steam_manager.get_lua_path()
        if lua_dir:
            lua_file = os.path.join(lua_dir, f"{appid}.lua")
            if os.path.exists(lua_file):
                # 本機已存在 Lua -> 改寫並鎖定各 Depot 的 setManifestid
                self._update_existing_lua(lua_file, depots)
            else:
                # 本機無 Lua -> 嘗試下載 appinfo.vdf 並自適應組裝
                self._assemble_and_save_lua(appid, depots, lua_file)

            # 2.5 自動關聯補齊 DLC：若本地 Lua 仍有宣告缺漏的 DLC Depot，自動連帶從 GitHub 補齊
            try:
                st_check = steam_manager.get_lua_manifest_status(appid)
                missing_files = st_check.get("missing_files", [])
                if missing_files and os.path.exists(lua_file):
                    with open(lua_file, "r", encoding="utf-8", errors="ignore") as f:
                        lua_raw = f.read()
                    all_ids = set(re.findall(r'addappid\((\d+)', lua_raw))
                    for sub_id in all_ids:
                        if sub_id != str(appid):
                            sub_res = self.search_all_sources(sub_id)
                            if sub_res.get("github", {}).get("available"):
                                sub_depots = sub_res.get("github", {}).get("depots", {})
                                # 若此 DLC 含有缺失的 depot
                                if any(f"{did}_{gid}.manifest" in missing_files for did, gid in sub_depots.items()):
                                    if progress_cb: progress_cb(f"正在自動連帶補齊 DLC (AppID: {sub_id}) 清單...")
                                    self._deploy_from_github(sub_id, sub_res, progress_cb)
            except Exception as e:
                print(f"[UnifiedManifestManager] 自動聯動補齊 DLC 失敗: {e}")

        # 3. ACF 防 401 封鎖與版本防護鎖定
        if progress_cb: progress_cb("正在執行 ACF 狀態赦免與防 401 封鎖防護...")
        steam_manager.lock_game_version(appid)

        return True, f"成功透過 GitHub 部署 {downloaded_count} 個 Manifest，並完成 Lua 更新與防 401 鎖定！"

    def _deploy_from_ryuu(self, appid: str, progress_cb: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
        """調用現有 ryuu_manager 進行下載與部署"""
        try:
            from managers import ryuu_manager, steam_manager, config_manager
            from pathlib import Path
            from PySide6.QtCore import QEventLoop, QTimer

            client = getattr(ryuu_manager, 'get_shared_ryuu_client', lambda: None)()
            if not client or not client.is_logged_in:
                return False, "Ryuu 尚未登入或憑證已失效"
                
            if progress_cb: progress_cb("正在透過 Ryuu 下載 Manifest 與 Lua 打包檔...")
            
            loop = QEventLoop()
            dl_result = {}
            
            def on_done(res):
                dl_result["res"] = res
                loop.quit()
                
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(loop.quit)
            timer.start(25000)
            
            client.download_manifest(appid, "public", on_done)
            loop.exec()
            timer.stop()
            
            res = dl_result.get("res")
            if not res or res.get("error"):
                err = res.get("error", "超時或無回應") if res else "Ryuu 下載超時"
                return False, f"Ryuu 下載失敗: {err}"
                
            manifests = res.get("manifests", {})
            lua_text = res.get("lua_content", res.get("data", ""))
            
            steam_p = steam_manager.find_steam_path()
            if not steam_p:
                return False, "找不到 Steam 安裝路徑"
            lua_dir = Path(steam_p) / "config" / "lua"
            lua_dir.mkdir(parents=True, exist_ok=True)
            
            if lua_text:
                with open(lua_dir / f"{appid}.lua", "w", encoding="utf-8") as f:
                    f.write(lua_text)
                    
            cfg_lua_dir = config_manager.get_config().get("lua_dir")
            if cfg_lua_dir and Path(cfg_lua_dir).resolve() != lua_dir.resolve():
                Path(cfg_lua_dir).mkdir(parents=True, exist_ok=True)
                if lua_text:
                    with open(Path(cfg_lua_dir) / f"{appid}.lua", "w", encoding="utf-8") as f:
                        f.write(lua_text)
                        
            steam_manager.deploy_manifests_to_depotcache(manifests, steam_p, lua_dir)
            steam_manager.sync_lua_with_deployed_manifests(appid, manifests, lua_dir)
            steam_manager.sanitize_lua_manifests(appid, steam_p, lua_dir)
            steam_manager.lock_game_version(appid, steam_p)
            
            return True, f"成功透過 Ryuu 部署 {len(manifests)} 個 Manifest，並同步更新 Lua！"
        except Exception as e:
            return False, f"Ryuu 下載發生異常: {e}"

    def _decompress_manifest(self, raw_bytes: bytes) -> bytes:
        """解壓 GitHub Pro 系 Manifest (去頭 10 字節 raw deflate)"""
        if len(raw_bytes) < 16:
            return raw_bytes
        # 檢查是否已是 Steam 原生 Magic Header (0x71F617D0)
        if raw_bytes[:4] == b"\xd0\x17\xf6\x71":
            return raw_bytes
        # 嘗試去頭 10 字節解壓
        try:
            d_obj = zlib.decompressobj(-zlib.MAX_WBITS)
            dec = d_obj.decompress(raw_bytes[10:])
            if dec[:4] == b"\xd0\x17\xf6\x71":
                return dec
        except Exception:
            pass
        # 嘗試其他偏移
        for off in (0, 2):
            try:
                dec = zlib.decompress(raw_bytes[off:])
                if dec[:4] == b"\xd0\x17\xf6\x71":
                    return dec
            except Exception:
                pass
        return raw_bytes

    def _update_existing_lua(self, lua_file: str, depots: Dict[str, str]):
        """改寫本地 Lua 中的 setManifestid，支援唯讀保護自動解鎖與復原"""
        try:
            if os.path.exists(lua_file):
                os.chmod(lua_file, stat.S_IWRITE | stat.S_IREAD)
            with open(lua_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            
            lines = content.splitlines()
            updated_depots = set()
            new_lines = []

            for line in lines:
                # 匹配 setManifestid(did, ...) ，無論是否有註解 (例如 -- 或 -- [清單缺失防護已停用])
                m = re.match(r'^[ \t]*(?:--[^\n\r]*?)?set[M|m]anifest[i|I]d\s*\(\s*(\d+)\s*,', line)
                if m:
                    did = m.group(1)
                    if did in depots:
                        gid = depots[did]
                        if did not in updated_depots:
                            new_lines.append(f'setManifestid({did}, "{gid}", 0)')
                            updated_depots.add(did)
                        continue
                new_lines.append(line)

            # 若有 depot 未在原檔案中出現，附加於末尾
            for did, gid in depots.items():
                if did not in updated_depots:
                    new_lines.append(f'setManifestid({did}, "{gid}", 0)')
                    updated_depots.add(did)

            content = "\n".join(new_lines)

            with open(lua_file, "w", encoding="utf-8") as f:
                f.write(content)
            
            # 鎖定 Lua 唯讀保護防 Steam 覆寫
            os.chmod(lua_file, stat.S_IREAD)
        except Exception as e:
            print(f"[UnifiedManifestManager] 更新本地 Lua 失敗: {e}")

    def _assemble_and_save_lua(self, appid: str, depots: Dict[str, str], dest_lua_file: str):
        """從 appinfo.vdf + 公開 DepotKeys 自適應組裝新 Lua，支援唯讀保護"""
        try:
            vdf_url = f"https://raw.githubusercontent.com/{self.github_owner}/{self.github_repo}/{appid}/appinfo.vdf"
            req = urllib.request.Request(vdf_url, headers={"User-Agent": "Mozilla/5.0"})
            vdf_text = urllib.request.urlopen(req, timeout=8).read().decode("utf-8")
            
            keys_data = self.get_cached_depot_keys()
            
            lines = [
                f"-- Auto-Assembled Lua by UnifiedManifestManager",
                f"-- Generated for AppID: {appid}",
                f"addappid({appid})"
            ]
            
            # 提取 DLC
            dlc_matches = re.findall(r'"(\d+)"\s*\{\s*"type"\s*"dlc"', vdf_text, re.IGNORECASE)
            for dlc_id in dlc_matches:
                if dlc_id != str(appid):
                    lines.append(f"addappid({dlc_id})")
                    
            # 遍歷 depots
            for did, gid in depots.items():
                key = keys_data.get(str(did), "")
                if key:
                    lines.append(f'addappid({did}, 1, "{key}")')
                else:
                    lines.append(f"addappid({did})")
                lines.append(f'setManifestid({did}, "{gid}", 0)')
                
            os.makedirs(os.path.dirname(dest_lua_file), exist_ok=True)
            if os.path.exists(dest_lua_file):
                os.chmod(dest_lua_file, stat.S_IWRITE | stat.S_IREAD)
            with open(dest_lua_file, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            # 寫入後設置唯讀保護
            os.chmod(dest_lua_file, stat.S_IREAD)
        except Exception as e:
            print(f"[UnifiedManifestManager] 自適應組裝 Lua 失敗: {e}")

def get_unified_manifest_manager() -> UnifiedManifestManager:
    return UnifiedManifestManager.get_instance()

