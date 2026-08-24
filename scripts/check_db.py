import sqlite3
db_path = r'C:\Users\chuan\.gemini\antigravity-ide\conversations\44e813f8-0fc9-453b-8d1e-c93ba2324f94.db'
conn = sqlite3.connect(db_path)
for row in conn.execute("SELECT sql FROM sqlite_master WHERE type='table'"):
    print(row[0])
