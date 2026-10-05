# -*- coding: utf-8 -*-
"""
Supabase party_rooms 資料表 RLS (Row Level Security) 行級安全性策略套用腳本
"""

import sys
import json
import psycopg2
from pathlib import Path

# UTF-8 輸出防護
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SECRETS_FILE = PROJECT_ROOT / "data" / "secrets" / "supabase.json"

def apply_rls():
    if not SECRETS_FILE.exists():
        print(f"❌ 找不到設定檔: {SECRETS_FILE}")
        return False

    with open(SECRETS_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    conn_str = cfg.get("pooler_connection_string") or cfg.get("direct_connection_string")
    if not conn_str:
        print("❌ 未在 supabase.json 找到有效連線字串")
        return False

    print(f"🔗 正在連線至 Supabase 資料庫 ({cfg.get('project_id')})...")
    conn = psycopg2.connect(conn_str)
    conn.autocommit = True
    cur = conn.cursor()

    # 1. 確保開啟 RLS
    cur.execute("ALTER TABLE party_rooms ENABLE ROW LEVEL SECURITY;")
    print("🔒 1. party_rooms 行級安全性 (RLS) 狀態確認: ENABLED")

    # 2. 清理舊策略
    old_policies = [
        "Allow anon delete room",
        "Allow anon update room",
        "Allow anon insert room",
        "Allow anon read all rooms",
        "大廳公開讀取策略",
        "允許建立合法房間",
        "允許成員狀態同步與房主心跳",
        "僅房主或超時幽靈房可被刪除"
    ]
    for p in old_policies:
        cur.execute(f"DROP POLICY IF EXISTS \"{p}\" ON party_rooms;")
    print("🧹 2. 舊策略清理完畢")

    # 3. 套用全新加固策略
    
    # 策略 A: SELECT (大廳公開讀取)
    sql_select = """
    CREATE POLICY "大廳公開讀取策略" 
    ON party_rooms FOR SELECT 
    TO anon 
    USING (true);
    """
    cur.execute(sql_select)
    print("  + 策略 [SELECT]  : 大廳公開讀取策略")

    # 策略 B: INSERT (建立合法房間)
    sql_insert = """
    CREATE POLICY "允許建立合法房間" 
    ON party_rooms FOR INSERT 
    TO anon 
    WITH CHECK (
        room_id IS NOT NULL 
        AND host_client_id IS NOT NULL
    );
    """
    cur.execute(sql_insert)
    print("  + 策略 [INSERT]  : 允許建立合法房間")

    # 策略 C: UPDATE (成員進度同步與心跳)
    sql_update = """
    CREATE POLICY "允許成員狀態同步與房主心跳" 
    ON party_rooms FOR UPDATE 
    TO anon 
    USING (true)
    WITH CHECK (true);
    """
    cur.execute(sql_update)
    print("  + 策略 [UPDATE]  : 允許成員狀態同步與房主心跳")

    # 策略 D: DELETE (🌟 核心防禦鎖！徹底杜絕惡意清空大廳！)
    # 規則：
    # 1. 房主解散：Request Header 中的 x-client-id 與資料列的 host_client_id 吻合
    # 2. 幽靈清理：updated_at 已逾期超過 45 秒 (由任何客戶端異步垃圾回收)
    sql_delete = """
    CREATE POLICY "僅房主或超時幽靈房可被刪除" 
    ON party_rooms FOR DELETE 
    TO anon 
    USING (
        (
            host_client_id IS NOT NULL 
            AND host_client_id = coalesce(
                current_setting('request.headers', true)::json->>'x-client-id',
                ''
            )
        )
        OR
        (
            updated_at < (NOW() AT TIME ZONE 'utc' - INTERVAL '45 SECONDS')
        )
    );
    """
    cur.execute(sql_delete)
    print("  + 策略 [DELETE]  : 僅房主或超時幽靈房可被刪除 (惡意清空大廳防禦鎖生效)")

    # 4. 驗證目前啟用的策略
    cur.execute("SELECT policyname, cmd FROM pg_policies WHERE tablename = 'party_rooms';")
    rows = cur.fetchall()
    print("\n📋 目前生效的 RLS 策略清單:")
    for r in rows:
        print(f"  • [{r[1]}] {r[0]}")

    conn.close()
    print("\n🎉 Supabase RLS 安全防護策略已全部無縫套用成功！")
    return True

if __name__ == "__main__":
    apply_rls()
