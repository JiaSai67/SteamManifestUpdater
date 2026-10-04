import os
import re
import json
import base64
import ctypes
from ctypes import wintypes
from pathlib import Path
import urllib.request

class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte))
    ]

def _decrypt_dpapi(encrypted_bytes: bytes) -> bytes:
    if not encrypted_bytes:
        return b""
    p_data_in = DATA_BLOB(len(encrypted_bytes), (ctypes.c_byte * len(encrypted_bytes))(*encrypted_bytes))
    p_data_out = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    success = crypt32.CryptUnprotectData(
        ctypes.byref(p_data_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(p_data_out)
    )
    if not success:
        return b""
    data = ctypes.string_at(p_data_out.pbData, p_data_out.cbData)
    ctypes.windll.kernel32.LocalFree(p_data_out.pbData)
    return data

def _get_master_key(client_path: Path):
    local_state_file = client_path / "Local State"
    if not local_state_file.exists():
        return None
    try:
        with open(local_state_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        enc_key_b64 = data.get("os_crypt", {}).get("encrypted_key")
        if not enc_key_b64:
            return None
        enc_key = base64.b64decode(enc_key_b64)
        if enc_key.startswith(b"DPAPI"):
            enc_key = enc_key[5:]
        return _decrypt_dpapi(enc_key)
    except Exception:
        return None

def _decrypt_token(encrypted_token: bytes, master_key: bytes):
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        iv = encrypted_token[3:15]
        ciphertext_and_tag = encrypted_token[15:]
        aesgcm = AESGCM(master_key)
        decrypted = aesgcm.decrypt(iv, ciphertext_and_tag, None)
        return decrypted.decode("utf-8", errors="ignore")
    except Exception:
        return None

def scan_local_discord_tokens() -> list:
    """
    掃描本機 Discord 桌面端 (Discord, Discord PTB, Discord Canary) 儲存的所有已登入帳號 Token。
    並向 Discord 官方端點 (/api/v9/users/@me) 驗證真實性，
    回傳有效帳號字典清單：
    [
      {
         "id": str,
         "username": str,
         "global_name": str,
         "display_name": str,
         "token": str,
         "masked_token": str,
         "avatar_url": str
      }, ...
    ]
    """
    appdata = os.getenv("APPDATA")
    if not appdata:
        return []

    client_paths = [
        Path(appdata) / "discord",
        Path(appdata) / "discordptb",
        Path(appdata) / "discordcanary"
    ]

    extracted_tokens = set()

    for cp in client_paths:
        if not cp.exists():
            continue
        key = _get_master_key(cp)
        if not key:
            continue

        leveldb_path = cp / "Local Storage" / "leveldb"
        if not leveldb_path.exists():
            continue

        for ext in ("*.ldb", "*.log"):
            for f in leveldb_path.glob(ext):
                try:
                    content = f.read_bytes()
                    matches = re.findall(rb"dQw4w9WgXcQ:[^\"]*", content)
                    for m in matches:
                        b64_part = m.split(b"dQw4w9WgXcQ:")[1]
                        try:
                            enc_bytes = base64.b64decode(b64_part)
                            tok = _decrypt_token(enc_bytes, key)
                            if tok and len(tok) > 30:
                                extracted_tokens.add(tok)
                        except Exception:
                            pass
                except Exception:
                    pass

    valid_accounts = []
    seen_user_ids = set()

    for token in extracted_tokens:
        req = urllib.request.Request(
            "https://discord.com/api/v9/users/@me",
            headers={
                "Authorization": token,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                    uid = str(data.get("id"))
                    if uid in seen_user_ids:
                        continue
                    seen_user_ids.add(uid)
                    
                    uname = data.get("username", "Unknown")
                    gname = data.get("global_name") or uname
                    avatar = data.get("avatar")
                    avatar_url = f"https://cdn.discordapp.com/avatars/{uid}/{avatar}.png" if avatar else ""

                    masked = token[:10] + "..." + token[-6:]
                    valid_accounts.append({
                        "id": uid,
                        "username": uname,
                        "global_name": gname,
                        "display_name": f"{gname} (@{uname})",
                        "token": token,
                        "masked_token": masked,
                        "avatar_url": avatar_url
                    })
        except Exception:
            pass

    return valid_accounts


def login_ryuu_with_discord_token(token: str) -> dict:
    """
    使用 Discord Token 直接向 Discord OAuth API 與 Ryuu 執行純後端授權，
    完全跳過瀏覽器頁面，避免觸發 Windows 安全性金鑰 (Passkey) 彈窗。
    回傳:
      {
         "success": bool,
         "session": str | None,
         "error": "not_in_server" | "auth_failed" | "no_callback" | "no_session" | None,
         "downloads_left": int | None,
         "message": str
      }
    """
    import urllib.request
    import json
    import re
    import requests

    s = requests.Session()
    try:
        # 1. 取得 Ryuu 的 Discord OAuth URL
        r1 = s.get("https://generator.ryuu.lol/login", allow_redirects=False, timeout=10)
        oauth_url = r1.headers.get("Location")
        if not oauth_url:
            return {"success": False, "error": "init_failed", "message": "無法取得 Ryuu OAuth 跳轉位址"}

        # 2. 向 Discord API POST 授權
        headers = {
            "Authorization": token,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Content-Type": "application/json"
        }
        payload = json.dumps({"permissions": "0", "authorize": True}).encode("utf-8")
        req = urllib.request.Request(oauth_url, data=payload, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return {"success": False, "error": "auth_failed", "message": f"Discord 授權失敗 (HTTP {e.code})"}

        callback_url = data.get("location")
        if not callback_url:
            return {"success": False, "error": "no_callback", "message": "Discord 未返回跳轉回調位址"}

        # 3. 回調跳轉回 Ryuu
        r2 = s.get(callback_url, allow_redirects=True, timeout=10)

        # 檢查是否為 not_in_server
        if "not_in_server" in r2.url or "not_in_server" in r2.text:
            return {
                "success": False,
                "error": "not_in_server",
                "message": "此 Discord 帳號尚未加入 Ryuu 官方伺服器！請先在 Discord 加入 discord.gg/manifests 後重試。"
            }

        session_cookie = s.cookies.get("session")
        if not session_cookie:
            return {"success": False, "error": "no_session", "message": "Ryuu 未返回 session 憑證"}

        # 4. 擷取配額
        dl_match = re.search(r'id=["\']downloads-left["\'][^>]*>(\d+)<', r2.text)
        dl_num = int(dl_match.group(1)) if dl_match else 50

        return {
            "success": True,
            "session": session_cookie,
            "downloads_left": dl_num,
            "message": "登入成功"
        }
    except Exception as e:
        return {"success": False, "error": "exception", "message": f"登入流程發生異常: {e}"}

