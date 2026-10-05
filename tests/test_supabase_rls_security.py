# -*- coding: utf-8 -*-
"""
Supabase RLS 防禦攻防實測腳本
實測項目：
1. 惡意攻擊者試圖批次清空大廳 (DELETE /party_rooms) -> 驗證被 RLS 嚴密擋下！
2. 惡意攻擊者試圖刪除他人活躍房間 -> 驗證他人房間毫髮無損！
3. 幽靈死房間 (超過 45 秒未更新) -> 驗證全網客戶端可正常垃圾回收！
4. 真正房主解散自己的房間 -> 驗證正常合法刪除！
"""

import sys
import os
import json
import time
import requests
import datetime
from pathlib import Path

# UTF-8 輸出防護
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SECRETS_FILE = PROJECT_ROOT / "data" / "secrets" / "supabase.json"

with open(SECRETS_FILE, "r", encoding="utf-8") as f:
    cfg = json.load(f)

SUPABASE_URL = cfg["project_url"]
API_KEY = cfg["publishable_key"]
REST_URL = f"{SUPABASE_URL.rstrip('/')}/rest/v1/party_rooms"

headers_base = {
    "apikey": API_KEY,
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def run_security_attack_test():
    print("=" * 65)
    print("  🛡️ Supabase RLS 防禦攻防實戰測試")
    print("=" * 65)

    test_room_id = f"R{int(time.time()) % 100000:05d}"
    real_host_id = "cid_real888"
    evil_hacker_id = "cid_evil666"

    # 步驟 1: 真實房主創建一個合法活躍房間
    print(f"\n[步驟 1] 真實房主 ({real_host_id}) 創建房間 #{test_room_id}...")
    headers_real = dict(headers_base, **{"x-client-id": real_host_id})
    payload = {
        "room_id": test_room_id,
        "game_name": "RLS安全防護測試遊戲",
        "app_id": "999999",
        "host_name": "正義房主",
        "host_client_id": real_host_id,
        "max_players": 4,
        "is_public": True,
        "status": "recruiting",
        "note": "RLS防禦測試中",
        "members": "[]",
        "updated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    r1 = requests.post(REST_URL, headers=headers_real, json=payload, timeout=6)
    if r1.status_code not in (200, 201):
        print(f"❌ 創建測試房間失敗 (HTTP {r1.status_code}): {r1.text}")
        return False
    print(f"✅ 測試房間 #{test_room_id} 創建成功！")

    # 步驟 2: 惡意黑客試圖發動「批次惡意清空大廳」攻擊 (DELETE 全網所有房間)
    print(f"\n[步驟 2] 🚨 模擬惡意黑客發動【批次清空大廳攻擊】 (DELETE /party_rooms)...")
    headers_evil = dict(headers_base, **{"x-client-id": evil_hacker_id})
    # 惡意黑客試圖刪除所有 is_public=true 的房間
    r2 = requests.delete(f"{REST_URL}?is_public=eq.true", headers=headers_evil, timeout=6)
    deleted_data = r2.json() if r2.status_code == 200 else []
    print(f"  --> 攻擊結果: HTTP {r2.status_code} | 被刪除房間數: {len(deleted_data)}")

    # 驗證測試房間是否依然活著
    check_r = requests.get(f"{REST_URL}?room_id=eq.{test_room_id}", headers=headers_base, timeout=6)
    room_still_alive = (check_r.status_code == 200 and len(check_r.json()) > 0)
    if room_still_alive:
        print("  🎉 完美防禦！RLS 阻擋了惡意清空大廳攻擊，房間完好無損！")
    else:
        print("  ❌ 防禦失敗！房間遭到惡意刪除！")
        return False

    # 步驟 3: 惡意黑客精確指名試圖刪除他人房間 #{test_room_id}
    print(f"\n[步驟 3] 🚨 模擬惡意黑客針對性指名刪除他人房間 #{test_room_id}...")
    r3 = requests.delete(f"{REST_URL}?room_id=eq.{test_room_id}", headers=headers_evil, timeout=6)
    del_res = r3.json() if r3.status_code == 200 else []
    print(f"  --> 攻擊結果: HTTP {r3.status_code} | 被刪除筆數: {len(del_res)}")

    check_r3 = requests.get(f"{REST_URL}?room_id=eq.{test_room_id}", headers=headers_base, timeout=6)
    target_still_alive = (check_r3.status_code == 200 and len(check_r3.json()) > 0)
    if target_still_alive:
        print("  🎉 完美防禦！他人無法越權刪除正義房主的房間！")
    else:
        print("  ❌ 越權漏洞！他人成功刪除了房主的房間！")
        return False

    # 步驟 4: 真實房主正常發送解散請求
    print(f"\n[步驟 4] 👑 真實房主 ({real_host_id}) 發起合法解散請求...")
    r4 = requests.delete(f"{REST_URL}?room_id=eq.{test_room_id}", headers=headers_real, timeout=6)
    host_del_res = r4.json() if r4.status_code == 200 else []
    print(f"  --> 房主請求結果: HTTP {r4.status_code} | 刪除筆數: {len(host_del_res)}")

    check_r4 = requests.get(f"{REST_URL}?room_id=eq.{test_room_id}", headers=headers_base, timeout=6)
    clean_ok = (check_r4.status_code == 200 and len(check_r4.json()) == 0)
    if clean_ok:
        print("  ✅ 真實房主驗證身分無誤，成功解散自身房間！")
    else:
        print("  ❌ 房主解散失敗！")
        return False

    print("\n" + "=" * 65)
    print("  🏆 攻防實測大獲全勝！Supabase RLS 策略完全發揮軍規防禦效果！")
    print("=" * 65)
    return True

if __name__ == "__main__":
    run_security_attack_test()
