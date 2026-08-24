import sys
import re

with open("g:/python/SteamManifestUpdater/steam_manifest_gui.py", "r", encoding="utf-8") as f:
    content = f.read()

# We want to replace from '    def save_and_reload(self):' to the end of the file.
split_idx = content.find("    def save_and_reload(self):")
if split_idx == -1:
    print("Cannot find split point!")
    sys.exit(1)

new_code = """    def save_and_reload(self):
        new_dir = self.dir_var.get().strip()
        if not os.path.exists(new_dir):
            messagebox.showerror("錯誤", f"找不到指定的資料夾：\\n{new_dir}")
            return
            
        self.config["lua_dir"] = new_dir
        save_config(self.config)
        self.start_auto_update_flow()
        
    def start_auto_update_flow(self):
        # Clear existing tree
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        lua_dir = self.dir_var.get().strip()
        
        if not os.path.exists(lua_dir):
            self.status_var.set(f"找不到資料夾: {lua_dir}")
            return
            
        self.progress_var.set("🔄 正在極速比對並更新 Lua 中...")
        self.status_var.set("正在進行全自動比對並寫入...")
        self.btn_update.config(state=tk.DISABLED)
        
        # Start background thread to fetch version, update file, and collect results
        threading.Thread(target=self.auto_update_thread, args=(lua_dir,), daemon=True).start()
        
    def auto_update_thread(self, lua_dir):
        import concurrent.futures
        from update_manifests import get_app_info
        
        filenames = sorted([f for f in os.listdir(lua_dir) if f.endswith(".lua")])
        total_files = len(filenames)
        completed = 0
        
        results = []
        
        def process_single_lua(filename):
            nonlocal completed
            filepath = os.path.join(lua_dir, filename)
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
            except Exception:
                return None
                
            name_match = re.search(r'--\\s*\\d+\\s*-\\s*(.+)', content)
            if name_match:
                result["game_name"] = name_match.group(1).strip()
                
            pattern = re.compile(r'setManifestid\\(\\s*(\\d+)\\s*,\\s*"(\\d+)"(?:,\\s*(\\d+))?\\s*\\)')
            matches = pattern.findall(content)
            
            if not matches:
                return None
                
            info = get_app_info(appid)
            api_game_name = None
            is_error = False
            build_id = "未知"
            
            if info:
                if "error" in info:
                    is_error = True
                    result["error_msg"] = info["error"]
                    build_id = f"❌ {info['error']}"
                else:
                    common_data = info.get("common", {})
                    if "name" in common_data:
                        api_game_name = common_data["name"]
                        result["game_name"] = api_game_name
                        
                    branches = info.get("depots", {}).get("branches", {})
                    public_branch = branches.get("public", {})
                    if public_branch:
                        build_id = public_branch.get("buildid", "未知")
                        timestamp = public_branch.get("timeupdated")
                        if timestamp:
                            try:
                                result["update_date"] = datetime.fromtimestamp(int(timestamp)).strftime('%Y-%m-%d %H:%M:%S')
                            except:
                                pass
            
            if not api_game_name and not is_error:
                try:
                    depot_id = matches[0][0]
                    parent_appid = str(int(depot_id) - 1)
                    if parent_appid != appid:
                        parent_info = get_app_info(parent_appid)
                        if parent_info and "error" not in parent_info:
                            common_data = parent_info.get("common", {})
                            if "name" in common_data:
                                result["game_name"] = common_data["name"] + " (DLC/相關項目)"
                except:
                    pass
            
            # File writing logic
            file_modified = False
            updated_content = content
            depots_api = info.get("depots", {}) if info and not is_error else {}
            
            for match in matches:
                depot_id, old_manifest, old_size_str = match
                old_size = old_size_str if len(match) > 2 and match[2] else None
                
                new_manifest = old_manifest
                new_size = old_size
                is_row_updated = False
                
                depot_info = depots_api.get(str(depot_id), {})
                if depot_info:
                    api_manifest = depot_info.get("manifests", {}).get("public", {}).get("gid")
                    api_size = depot_info.get("manifests", {}).get("public", {}).get("size")
                    
                    if api_manifest and str(api_manifest) != str(old_manifest):
                        new_manifest = str(api_manifest)
                        new_size = str(api_size) if api_size else old_size
                        
                        if old_size:
                            old_str = f'setManifestid({depot_id}, "{old_manifest}", {old_size})'
                            new_str = f'setManifestid({depot_id}, "{new_manifest}", {new_size})'
                        else:
                            old_str = f'setManifestid({depot_id}, "{old_manifest}")'
                            new_str = f'setManifestid({depot_id}, "{new_manifest}")'
                            
                        updated_content = updated_content.replace(old_str, new_str)
                        file_modified = True
                        is_row_updated = True
                
                result["rows"].append({
                    "depot_id": depot_id,
                    "manifest_id": new_manifest,
                    "build_id": build_id,
                    "is_updated": is_row_updated
                })
                
            if file_modified:
                try:
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(updated_content)
                    result["status"] = "updated"
                except Exception as e:
                    result["status"] = "error"
                    result["error_msg"] = f"寫入失敗: {e}"
                    
            if is_error:
                result["status"] = "error"
                
            completed += 1
            self.after(0, self.progress_var.set, f"🔄 正在極速比對並更新 Lua ({completed}/{total_files})...")
            
            return result

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(process_single_lua, f) for f in filenames]
            for future in concurrent.futures.as_completed(futures):
                res = future.result()
                if res:
                    results.append(res)
                    
        self.after(0, self.populate_treeview, results)
        
    def populate_treeview(self, results):
        self.btn_update.config(state=tk.NORMAL)
        
        updated_count = sum(1 for r in results if r["status"] == "updated")
        self.progress_var.set(f"✅ 工作結果：已成功更新 {updated_count} 款遊戲")
        self.status_var.set("自動更新流程已完成！")
        
        node_updated = self.tree.insert("", tk.END, text="📁 最近更新的遊戲", open=True, tags=("even",))
        node_normal = self.tree.insert("", tk.END, text="📁 無須更新 / 維持現狀", open=True, tags=("even",))
        node_error = self.tree.insert("", tk.END, text="📁 讀取失敗 / 無法更新", open=True, tags=("error",))
        
        for idx, res in enumerate(results):
            if res["status"] == "updated":
                parent = node_updated
                tag = "odd"
            elif res["status"] == "error":
                parent = node_error
                tag = "error"
            else:
                parent = node_normal
                tag = "even" if idx % 2 == 0 else "odd"
                
            mid_index = len(res["rows"]) // 2
            for i, row in enumerate(res["rows"]):
                disp_appid = res["appid"] if i == mid_index else ""
                disp_name = res["game_name"] if i == mid_index else ""
                
                row_tag = "error" if res["status"] == "error" else tag
                if row["is_updated"]:
                    row_tag = "updated_row"
                    
                self.tree.insert(parent, tk.END, values=(
                    disp_appid, disp_name, row["depot_id"], row["manifest_id"], row["build_id"], res["update_date"]
                ), tags=(row_tag,))

if __name__ == "__main__":
    app = SteamManifestApp()
    app.mainloop()
"""

new_file = content[:split_idx] + new_code

# Also fix the top_frame buttons to include Progress Label and remove the "browse" button? 
# The user might still want to browse. 
# We need to change the Treeview column "#0" configuration in the top half.
# And add the progress_var.
new_file = new_file.replace('self.tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")', 
                            'self.tree = ttk.Treeview(frame, columns=columns, show="tree headings", selectmode="browse")')
new_file = new_file.replace('self.tree.column("appid", width=90, anchor=tk.CENTER)',
                            'self.tree.column("#0", width=180, stretch=tk.NO)\n        self.tree.column("appid", width=90, anchor=tk.CENTER)')

# Change the button text
new_file = new_file.replace('self.btn_update = ttk.Button(top_frame, text="一鍵寫入 Lua 更新", command=self.trigger_update_lua)',
                            'self.btn_update = ttk.Button(top_frame, text="重新整理與全自動更新", command=self.start_auto_update_flow)')

# Add progress label
progress_label_code = """
        # Progress Label
        self.progress_var = tk.StringVar(value="")
        progress_label = ttk.Label(top_frame, textvariable=self.progress_var, font=('Microsoft JhengHei', 10, 'bold'), foreground="#007bff")
        progress_label.pack(side=tk.RIGHT, padx=10)
"""
new_file = new_file.replace('self.btn_update.pack(side=tk.LEFT, padx=5)', 'self.btn_update.pack(side=tk.LEFT, padx=5)' + progress_label_code)

# Add updated_row tag config
updated_tag_code = """        self.tree.tag_configure("error", foreground="#d9534f") # Red text for errors
        self.tree.tag_configure("updated_row", background="#dff0d8", foreground="#3c763d") # Light green
"""
new_file = new_file.replace('self.tree.tag_configure("error", foreground="#d9534f") # Red text for errors', updated_tag_code)

# Replace self.load_local_data() with self.start_auto_update_flow() at the end of __init__
new_file = new_file.replace('self.load_local_data()', 'self.start_auto_update_flow()')


with open("g:/python/SteamManifestUpdater/steam_manifest_gui.py", "w", encoding="utf-8") as f:
    f.write(new_file)

print("Patch applied successfully.")
