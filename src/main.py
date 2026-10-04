# -*- coding: utf-8 -*-
"""
SteamManifestUpdater - Next-Gen Modern Cherry/Rose-Gold Multi-Source Manifest & Game Manager
全新櫻花流光多源 Manifest 管理器主程式入口
支援 100% 復刻動效、極致排版、黃色需更新高亮標示與全功能後端聚合 (Ryuu + Lua.tools)。
"""

import os
import sys
from pathlib import Path

# 將 src 目錄置於 sys.path 首位
_src_dir = Path(__file__).resolve().parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

def launch_modern_gui():
    """啟動現代化櫻花流光 Webview 介面"""
    import webview
    from web_api import WebApi

    api = WebApi()

    # HTML 資源路徑 (載入純淨模組化前端頁面，僅約 750 行)
    html_path = (_src_dir / "gui" / "index.html").resolve()
    if not html_path.exists():
        raise FileNotFoundError(f"找不到前端頁面：{html_path}")

    # 讀取使用者個人化設定（深色模式、視窗尺寸）
    MIN_WIDTH = 880
    MIN_HEIGHT = 580
    cfg = api.get_config()
    width = max(int(cfg.get("window_width", 1180)), MIN_WIDTH)
    height = max(int(cfg.get("window_height", 760)), MIN_HEIGHT)

    # 🌟 首要關鍵：啟動時第一時間讀取深色模式設定，動態設定視窗底色，徹底消除閃白
    # 同步寫入 theme_cache.js，使 HTML 在解析第 0 毫秒即直接套用深色模式，杜絕載入時閃白
    is_dark = bool(cfg.get("dark_mode", False) or cfg.get("dark", False))
    bg_color = "#231C1E" if is_dark else "#FFE2E7"
    target_url = html_path.as_uri()

    try:
        import json
        theme_cache_path = _src_dir / "gui" / "theme_cache.js"
        theme_cache_path.write_text(f"window.__INITIAL_CONFIG__ = {json.dumps({'dark_mode': is_dark})};\n", encoding="utf-8")
    except Exception:
        pass

    # 🌟 停用 pywebview 內建無節流拖曳，改由前端 rAF 幀率同步排程處理
    # 設置 .pywebview-drag-disabled 避免預設 querySelectorAll('') 丟出 DOMException
    webview.settings['DRAG_REGION_SELECTOR'] = '.pywebview-drag-disabled'

    # 建立現代化無邊框視窗 (使用本地 URL 模式，原生支援獨立模組化 css/app.css 與 js/modules/*.js)
    window = webview.create_window(
        title="Steam 入庫與清單更新工具 (多源極速版)",
        url=target_url,
        js_api=api,
        width=width,
        height=height,
        min_size=(MIN_WIDTH, MIN_HEIGHT),
        resizable=True,
        frameless=True,       # 啟用無邊框，由 HTML 自定義櫻花流光標題列拖拽
        easy_drag=False,      # 關閉全局拖曳，僅限最上方標題橫條接受鼠標拖曳
        background_color=bg_color
    )

    api.set_window(window)

    # 啟動 Webview 引擎 (關閉 DevTools 避免干擾)
    webview.start(debug=False)

def launch_classic_gui():
    """啟動經典 PySide6 Fluent 介面 (手動參數 --classic / --pyside)"""
    try:
        import main_pyside6
        main_pyside6.main()
    except Exception as e:
        print(f"[Launcher] 經典 PySide6 介面啟動失敗: {e}")

def main():
    # 支援透過 --classic 參數手動選擇經典 Fluent 介面
    if "--classic" in sys.argv or "--pyside" in sys.argv:
        print("[Launcher] 手動參數指定，啟動經典 PySide6 Fluent 介面...")
        launch_classic_gui()
        return

    try:
        launch_modern_gui()
    except Exception as e:
        import traceback
        import time
        err_str = traceback.format_exc()
        print(f"[Launcher] 現代化 Webview 啟動異常:\n{err_str}")
        try:
            log_p = _src_dir.parent / "logs" / "launcher_error.log"
            log_p.parent.mkdir(parents=True, exist_ok=True)
            with open(log_p, "a", encoding="utf-8") as f:
                f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] 啟動異常:\n{err_str}\n")
        except Exception:
            pass

        # 🌟 跨設備友善錯誤對話框提示 (避免黑屏閃退迷茫)
        try:
            import ctypes
            import webbrowser
            is_wv2_err = any(k in err_str.lower() for k in ["webview2", "edge", "dll", "com_error", "not found"])
            if is_wv2_err:
                msg = (
                    "檢測到系統缺少 Microsoft Edge WebView2 執行階段，導致櫻花流光介面無法顯示。\n\n"
                    "是否立即前往微軟官方網站下載 WebView2 安裝程式？\n"
                    "(安裝完成後即可正常啟動)"
                )
                ret = ctypes.windll.user32.MessageBoxW(0, msg, "Steam Manifest Updater - 環境缺失提示", 0x24) # MB_YESNO | MB_ICONQUESTION
                if ret == 6: # IDYES
                    webbrowser.open("https://go.microsoft.com/fwlink/p/?LinkId=2124703")
            else:
                msg = f"軟體啟動過程發生未預期的異常：\n\n{str(e)[:200]}\n\n詳細診斷日誌已儲存至：\nlogs/launcher_error.log"
                ctypes.windll.user32.MessageBoxW(0, msg, "Steam Manifest Updater - 啟動錯誤", 0x10) # MB_ICONERROR
        except Exception:
            pass

if __name__ == "__main__":
    main()
