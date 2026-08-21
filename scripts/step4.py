import sys
import re

filepath = r"g:\python\SteamManifestUpdater\steam_manifest_gui.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Fix Header Resizing
content = content.replace(
    "self.tree.header().setSectionResizeMode(QHeaderView.Fixed)",
    "self.tree.header().setSectionResizeMode(QHeaderView.Interactive)"
)

# Fix Indentation so AppID doesn't look misaligned
content = content.replace(
    "self.tree.setWordWrap(False)",
    "self.tree.setWordWrap(False)\n        self.tree.setIndentation(12)"
)

# Fix Separator / Grid Lines
content = content.replace(
    "self.tree.setWordWrap(False)",
    "self.tree.setWordWrap(False)\n        self.tree.setStyleSheet(\"QTreeView::item { border-bottom: 1px solid #333333; }\")"
)

# Fix process_single_lua logic
old_process_single_lua = """        def process_single_lua(filename):
            nonlocal completed
            filepath = os.path.join(self.lua_dir, filename)
            appid = filename.replace(".lua", "")
            
            result = {
                "appid": appid,
                "status": "normal",
                "game_name": "Unknown",
                "error_msg": "",
                "rows": [],
                "update_date": "未知"
            }
            
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    
                import re
                from update_manifests import extract_steam_depots
                lua_depots = extract_steam_depots(content)
                if not lua_depots:
                    result["status"] = "error"
                    result["error_msg"] = "解析 Lua 失敗或查無 depots"
                    return result
                
                app_info = get_app_info(appid)
                if not app_info or "data" not in app_info:
                    result["status"] = "error"
                    result["error_msg"] = "取得 API 資料失敗"
                    return result
                    
                data = app_info["data"]
                game_name = data.get("name", "Unknown")
                result["game_name"] = game_name
                
                build_id = data.get("depots", {}).get("branches", {}).get("public", {}).get("buildid", "未知")
                update_date = "未知"
                if "timeupdated" in data.get("depots", {}).get("branches", {}).get("public", {}):
                    ts = data["depots"]["branches"]["public"]["timeupdated"]
                    try:
                        update_date = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
                        result["update_date"] = update_date
                    except:
                        pass
                
                is_updated_any = False
                new_content = content
                
                for depot_id_str, lua_manifest_id in lua_depots.items():
                    api_manifest_id = data.get("depots", {}).get(depot_id_str, {}).get("manifests", {}).get("public", {}).get("gid")
                    
                    if not api_manifest_id:
                        continue
                        
                    is_updated = False
                    if str(api_manifest_id) != str(lua_manifest_id):
                        is_updated = True
                        is_updated_any = True
                        # Precise replacement
                        pattern = rf'(\[{depot_id_str}\]\s*=\s*)\"{lua_manifest_id}\"'
                        new_content = re.sub(pattern, rf'\1"{api_manifest_id}"', new_content)
                    
                    result["rows"].append({
                        "depot": depot_id_str,
                        "manifest": str(api_manifest_id) if is_updated else str(lua_manifest_id),
                        "build_id": build_id,
                        "is_updated": is_updated
                    })
                
                if is_updated_any:
                    result["status"] = "updated"
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(new_content)
                
            except Exception as e:
                result["status"] = "error"
                result["error_msg"] = str(e)
            
            completed += 1
            self.progress.emit(completed, total_files)
            return result"""

new_process_single_lua = """        def process_single_lua(filename):
            nonlocal completed
            filepath = os.path.join(self.lua_dir, filename)
            appid = filename.replace(".lua", "")
            
            result = {
                "appid": appid,
                "status": "normal", # 'updated', 'normal', or 'error'
                "game_name": "Unknown",
                "error_msg": "",
                "rows": [], # List of dicts for each row
                "update_date": "未知"
            }
            
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                result["status"] = "error"
                result["error_msg"] = str(e)
                completed += 1
                self.progress.emit(completed, total_files)
                return result
                
            import re
            name_match = re.search(r'--\s*\d+\s*-\s*(.+)', content)
            if name_match:
                result["game_name"] = name_match.group(1).strip()
                
            pattern = re.compile(r'(setManifestid\(\s*(\d+)\s*,\s*"(\d+)"(?:,\s*(\d+))?\s*\))')
            matches = pattern.findall(content)
            
            if not matches:
                result["status"] = "error"
                result["error_msg"] = "無法解析 Lua 檔案內的 depot 格式"
                completed += 1
                self.progress.emit(completed, total_files)
                return result
                
            info = get_app_info(appid)
            is_error = False
            build_id = "未知"
            
            if info:
                if "error" in info:
                    is_error = True
                    result["error_msg"] = info["error"]
                    build_id = f"錯誤: {info['error']}"
                else:
                    common_data = info.get("common", {})
                    if "name" in common_data:
                        result["game_name"] = common_data["name"]
                    
                    depots_data = info.get("depots", {})
                    if "branches" in depots_data and "public" in depots_data["branches"]:
                        public_branch = depots_data["branches"]["public"]
                        if "buildid" in public_branch:
                            build_id = str(public_branch["buildid"])
                        if "timeupdated" in public_branch:
                            ts = public_branch["timeupdated"]
                            try:
                                from datetime import datetime
                                result["update_date"] = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
                            except:
                                pass
            else:
                is_error = True
                result["error_msg"] = "API 回傳空白"
                build_id = "錯誤: API"
            
            is_updated_any = False
            new_content = content
            
            for match in matches:
                old_str = match[0]
                depot_id = match[1]
                old_manifest = match[2]
                
                api_manifest_id = None
                if not is_error and info:
                    api_manifest_id = info.get("depots", {}).get(depot_id, {}).get("manifests", {}).get("public", {}).get("gid")
                
                is_updated = False
                if api_manifest_id and str(api_manifest_id) != old_manifest:
                    is_updated = True
                    is_updated_any = True
                    new_str = re.sub(rf'"{old_manifest}"', f'"{api_manifest_id}"', old_str)
                    new_content = new_content.replace(old_str, new_str)
                
                result["rows"].append({
                    "depot": depot_id,
                    "manifest": str(api_manifest_id) if is_updated else old_manifest,
                    "build_id": build_id,
                    "is_updated": is_updated
                })
                
            if is_error:
                result["status"] = "error"
            elif is_updated_any:
                result["status"] = "updated"
                try:
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(new_content)
                except Exception as e:
                    result["status"] = "error"
                    result["error_msg"] = f"存檔失敗: {e}"
            else:
                result["status"] = "normal"
                
            completed += 1
            self.progress.emit(completed, total_files)
            return result"""

content = content.replace(old_process_single_lua, new_process_single_lua)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)
print("Step 4 Applied.")
