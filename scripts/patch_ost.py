import sys

filepath = r"g:\python\SteamManifestUpdater\steam_manifest_gui.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add imports
import_block = """import os
import re
import json
import urllib.request
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
from pathlib import Path
import winreg
import shutil
from update_manifests import process_files

def get_steam_path():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        path, _ = winreg.QueryValueEx(key, "SteamPath")
        winreg.CloseKey(key)
        steam_dir = Path(path).resolve()
        if steam_dir.exists():
            return steam_dir
    except Exception:
        pass
    
    default_paths = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Steam",
        Path(r"C:\Steam")
    ]
    for p in default_paths:
        if p.exists():
            return p
    return None
"""

content = content.replace("""import os
import re
import json
import urllib.request
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
import threading
from update_manifests import process_files""", import_block)

# 2. Add UI to __init__
ui_injection = """        # Note Frame
        note_frame = ttk.Frame(self)
        note_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Label(note_frame, text="💡 註解：請在此指定 Steam 存放 Lua 檔案的資料夾。點擊「鎖定並重新載入」後，程式下次開啟將固定讀取此路徑。", foreground="gray", font=('Microsoft JhengHei', 9)).pack(side=tk.LEFT)
        
        # OST Frame
        self.steam_path = get_steam_path()
        ost_frame = ttk.Frame(self)
        ost_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        self.lbl_ost_status = ttk.Label(ost_frame, text="OpenSteamTools 狀態: 偵測中...", font=('Microsoft JhengHei', 10, 'bold'))
        self.lbl_ost_status.pack(side=tk.LEFT, padx=(0, 10))
        
        self.btn_install_ost = ttk.Button(ost_frame, text="一鍵安裝 OpenSteamTools", command=self.install_ost)
        self.btn_install_ost.pack(side=tk.LEFT, padx=5)
        
        self.btn_uninstall_ost = ttk.Button(ost_frame, text="移除", command=self.uninstall_ost)
        self.btn_uninstall_ost.pack(side=tk.LEFT, padx=5)
        
        self.update_ost_status()
"""

# we replace note_frame part with both note_frame and ost_frame
old_note_frame = """        # Note Frame
        note_frame = ttk.Frame(self)
        note_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Label(note_frame, text="💡 註解：請在此指定 Steam 存放 Lua 檔案的資料夾。點擊「鎖定並重新載入」後，程式下次開啟將固定讀取此路徑。", foreground="gray", font=('Microsoft JhengHei', 9)).pack(side=tk.LEFT)"""

content = content.replace(old_note_frame, ui_injection)

# 3. Add methods at the end of the class (before if __name__ == "__main__":)
methods_code = """
    def update_ost_status(self):
        if not self.steam_path:
            self.lbl_ost_status.config(text="OpenSteamTools 狀態: 找不到 Steam 安裝路徑", foreground="red")
            self.btn_install_ost.config(state=tk.DISABLED)
            self.btn_uninstall_ost.config(state=tk.DISABLED)
            return
            
        dlls = ["OpenSteamTool.dll", "dwmapi.dll", "xinput1_4.dll"]
        is_installed = all((self.steam_path / dll).exists() for dll in dlls)
        
        if is_installed:
            self.lbl_ost_status.config(text="OpenSteamTools 狀態: ✅ 已部署", foreground="green")
            self.btn_install_ost.config(state=tk.DISABLED)
            self.btn_uninstall_ost.config(state=tk.NORMAL)
        else:
            self.lbl_ost_status.config(text="OpenSteamTools 狀態: ❌ 未安裝", foreground="red")
            self.btn_install_ost.config(state=tk.NORMAL)
            self.btn_uninstall_ost.config(state=tk.DISABLED)

    def install_ost(self):
        if not self.steam_path: return
        base_dir = Path(__file__).resolve().parent.parent
        opensteam_dir = base_dir / "opensteamtools"
        dlls = ["OpenSteamTool.dll", "dwmapi.dll", "xinput1_4.dll"]
        
        try:
            for dll in dlls:
                src = opensteam_dir / dll
                dst = self.steam_path / dll
                if src.exists():
                    shutil.copy2(src, dst)
            
            lua_dir = self.steam_path / "config" / "lua"
            lua_dir.mkdir(parents=True, exist_ok=True)
            messagebox.showinfo("成功", "OpenSteamTools 安裝成功！")
        except Exception as e:
            messagebox.showerror("錯誤", f"安裝失敗: {e}")
            
        self.update_ost_status()
        
    def uninstall_ost(self):
        if not self.steam_path: return
        dlls = ["OpenSteamTool.dll", "dwmapi.dll", "xinput1_4.dll"]
        
        try:
            for dll in dlls:
                dst = self.steam_path / dll
                if dst.exists():
                    dst.unlink()
            messagebox.showinfo("成功", "OpenSteamTools 已成功移除！")
        except Exception as e:
            messagebox.showerror("錯誤", f"移除失敗 (請確認已完全關閉 Steam): {e}")
            
        self.update_ost_status()

if __name__ == "__main__":
"""

content = content.replace('if __name__ == "__main__":', methods_code)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("OST Patch applied successfully.")
