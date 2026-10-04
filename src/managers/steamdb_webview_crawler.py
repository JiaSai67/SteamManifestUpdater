# -*- coding: utf-8 -*-
"""
SteamDB Native WebView2 Crawler Runner
利用本機 Microsoft Edge WebView2 引擎自動穿透 Cloudflare 盾，
精確爬取指定 Depot 的真實 Manifest 歷史清單。
"""

import sys
import os
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

# 設置 UTF-8 輸出
if sys.platform == "win32":
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except Exception:
        pass


def _parse_steamdb_date(date_str: str) -> tuple:
    """解析 SteamDB 日期 (例如: '26 September 2026 – 23:30:04 UTC' 或 '1 September 2026')"""
    clean = date_str.split("–")[0].strip() if "–" in date_str else date_str.strip()
    clean = clean.replace("UTC", "").strip()
    for fmt in ("%d %B %Y", "%B %d, %Y", "%d %b %Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(clean, fmt)
            return dt.strftime("%Y-%m-%d"), dt.strftime("%y-%m-%d")
        except Exception:
            pass
    return "", ""


def run_webview_crawler(depot_id: str, max_wait: int = 15) -> dict:
    import webview
    
    url = f"https://steamdb.info/depot/{depot_id}/manifests/"
    result = {"success": False, "depot_id": depot_id, "manifests": []}

    def on_loaded(window):
        # 循環等待 Cloudflare 運算完成並提取表格 (最多等待 max_wait 秒)
        shield_count = 0
        for i in range(max_wait):
            time.sleep(1)
            js_code = """
            (function() {
                var title = document.title || '';
                var isJustMoment = title.indexOf('請稍候') !== -1 || title.indexOf('Just a moment') !== -1;
                var table = document.querySelector('.table-manifests') || document.querySelector('table');
                var rows = document.querySelectorAll('tr');
                var manifests = [];
                rows.forEach(function(tr) {
                    var text = tr.innerText || '';
                    var m = text.match(/\\b(\\d{15,22})\\b/);
                    if (m) {
                        var cells = Array.from(tr.querySelectorAll('td, th')).map(c => c.innerText.trim());
                        manifests.push({
                            gid: m[1],
                            cells: cells,
                            raw: text
                        });
                    }
                });
                return {
                    title: title,
                    isJustMoment: isJustMoment,
                    rowCount: rows.length,
                    manifestCount: manifests.length,
                    manifests: manifests
                };
            })();
            """
            try:
                data = window.evaluate_js(js_code)
                if data and not data.get("isJustMoment") and data.get("manifestCount", 0) > 0:
                    raw_items = data.get("manifests", [])
                    clean_manifests = []
                    for it in raw_items:
                        gid = it.get("gid", "")
                        cells = it.get("cells", [])
                        raw = it.get("raw", "")
                        d_str, d_fmt = "", ""
                        for c in cells:
                            d1, d2 = _parse_steamdb_date(c)
                            if d1:
                                d_str, d_fmt = d1, d2
                                break
                        clean_manifests.append({
                            "manifest_id": gid,
                            "date": d_str,
                            "date_str": d_fmt,
                            "branch": "public",
                            "source": "SteamDB"
                        })
                    result["success"] = True
                    result["manifests"] = clean_manifests
                    window.destroy()
                    return
                elif data and data.get("isJustMoment"):
                    shield_count += 1
                    # Cloudflare Managed Challenge (5秒盾) 正常計算需 4~6 秒，若超過 9 秒仍未解開才視為需人工互動退出
                    if shield_count >= 9:
                        break
            except Exception:
                pass
        
        # 超時或遇到人機挑戰退出
        window.destroy()

    window = webview.create_window(
        title="SteamDB Probe",
        url=url,
        width=500,
        height=350,
        hidden=True
    )
    webview.start(on_loaded, window, private_mode=False)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SteamDB WebView2 Crawler Runner")
    parser.add_argument("--depot", type=str, required=True, help="Depot ID")
    parser.add_argument("--timeout", type=int, default=15, help="Max wait seconds")
    args = parser.parse_args()

    res = run_webview_crawler(args.depot, max_wait=args.timeout)
    print("===RESULT_START===")
    print(json.dumps(res, ensure_ascii=False))
    print("===RESULT_END===")
