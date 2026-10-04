# -*- coding: utf-8 -*-
"""
discord_token_scanner - 安全防護與已棄用模組
為防範 Discord 帳戶風控與安全性，所有本機 Token 掃描、Token OAuth 模擬等方法已全面棄用並拔除。
配額驗證已全面遷移至官方網域伺服器 API (Domain Server API)。
"""

RYUU_GUILD_ID = "1133379109968498708"

def scan_local_discord_tokens() -> list:
    """已停用：本機 Token 掃描已棄置"""
    return []

def clean_discord_token(raw_token: str) -> str:
    """清理 Token 字串格式"""
    if not raw_token:
        return ""
    t = str(raw_token).strip().strip('\"\'`')
    for prefix in ["Bot ", "Bearer ", "token "]:
        if t.startswith(prefix):
            t = t[len(prefix):].strip()
    return t

def verify_discord_token(raw_token: str) -> dict | None:
    """已停用：不再透過 Token 請求 Discord 官方 API"""
    return None

def get_token_from_vault(account_id_or_name: str) -> str:
    return ""

def save_token_to_vault(key: str, token: str):
    pass

def login_ryuu_with_discord_token(token: str) -> dict:
    """已停用：請使用獨立沙盒瀏覽器登入或直接呼叫網域伺服器 API 驗證 Quota"""
    return {"success": False, "message": "Token 登入已棄用，請使用獨立沙盒登入或網域伺服器同步配額"}

def login_luatools_with_discord_token(raw_token: str) -> dict:
    """已停用：請使用獨立沙盒瀏覽器登入"""
    return {"success": False, "message": "Token 登入已棄用，請使用獨立沙盒登入"}
