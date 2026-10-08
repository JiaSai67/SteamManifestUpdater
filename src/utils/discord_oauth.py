# -*- coding: utf-8 -*-
"""
Discord OAuth2 官方身分驗證與本地回調攔截模組
功能：
1. 在本地臨時監聽 127.0.0.1:18888/callback (0 外部依賴，0 雲端伺服器)。
2. 自動開啟系統預設瀏覽器跳轉 Discord 官方授權頁面 (100% 官方標準，0 帳號軟鎖風險)。
3. 毫秒級攔截回傳之一次性授權代碼 (Authorization Code)。
4. 向 Discord 官方兌換全球唯一不可篡改的 Snowflake ID 與使用者名稱。
5. 成功後自動關閉本地監聽，釋放系統資源。
"""

import os
import json
import logging
import threading
import webbrowser
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, Optional
import requests

logger = logging.getLogger("discord_oauth")

DEFAULT_CLIENT_ID = "1557458328924192848"
DEFAULT_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET", "")
DEFAULT_PORT = 18888

class DiscordOAuthService:
    def __init__(self, client_id: str = DEFAULT_CLIENT_ID, client_secret: str = "", port: int = DEFAULT_PORT):
        self.client_id = (client_id or DEFAULT_CLIENT_ID).strip()
        self.client_secret = (client_secret or DEFAULT_CLIENT_SECRET).strip()
        self.port = port
        self.redirect_uri = f"http://127.0.0.1:{self.port}/callback"
        self._auth_result: Optional[Dict[str, Any]] = None
        self._server: Optional[HTTPServer] = None
        self._is_listening = False

    def get_auth_url(self) -> str:
        """生成 Discord 官方授權連結"""
        base_url = "https://discord.com/oauth2/authorize"
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": "identify",
            "prompt": "consent"
        }
        return f"{base_url}?{urllib.parse.urlencode(params)}"

    def start_oauth_flow(self, timeout_seconds: int = 60) -> Dict[str, Any]:
        """
        啟動完整 Discord OAuth 驗證流程 (同步阻塞或由背景線程調用)
        """
        auth_code_holder = {"code": None, "error": None}

        class _CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                query = urllib.parse.urlparse(self.path).query
                params = urllib.parse.parse_qs(query)

                if "code" in params:
                    auth_code_holder["code"] = params["code"][0]
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    html_content = """
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <meta charset="utf-8">
                        <title>Discord 驗證成功</title>
                        <style>
                            body { background: #0f1015; color: #fff; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
                            .card { background: #1a1b23; border: 1px solid #5865F2; padding: 40px; border-radius: 16px; text-align: center; box-shadow: 0 12px 40px rgba(0,0,0,0.6); max-width: 400px; }
                            h2 { color: #5865F2; margin-top: 0; font-size: 24px; }
                            p { color: #9ca3af; font-size: 14px; line-height: 1.6; }
                            .badge { background: rgba(88, 101, 242, 0.2); color: #858ff7; padding: 6px 12px; border-radius: 20px; display: inline-block; font-size: 13px; font-weight: 600; margin-bottom: 16px; }
                        </style>
                    </head>
                    <body>
                        <div class="card">
                            <div class="badge">🛡️ SMU 安全聯機身分認證</div>
                            <h2>✅ 授權成功！</h2>
                            <p>您的 Discord 官方身分已成功綁定至本機 SMU 客戶端。<br>您可以關閉此分頁並返回遊戲工具繼續遊玩。</p>
                        </div>
                    </body>
                    </html>
                    """
                    self.wfile.write(html_content.encode("utf-8"))
                elif "error" in params:
                    auth_code_holder["error"] = params.get("error_description", ["使用者取消了授權"])[0]
                    self.send_response(400)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"<h1>Discord \xe6\x8e\x88\xe6\xac\x8a\xe5\xa4\xb1\xe6\x95\x97</h1><p>\xe4\xbd\xbf\xe7\x94\xa8\xe8\x80\x85\xe5\x8f\x96\xe6\xb6\x88\xe4\xba\x86\xe6\x8e\x88\xe6\xac\x8a\xe3\x80\x82</p>")
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass  # 靜音本機請求日誌

        # 啟動微型本地 HTTP 服務
        try:
            server = HTTPServer(("127.0.0.1", self.port), _CallbackHandler)
            server.timeout = timeout_seconds
            self._server = server
        except Exception as e:
            logger.error(f"[Discord OAuth] 本機 Port {self.port} 綁定失敗: {e}")
            return {"ok": False, "msg": f"無法開啟本機回調監聽 (Port {self.port} 被佔用): {e}"}

        # 開啟瀏覽器進行授權
        auth_url = self.get_auth_url()
        logger.info(f"[Discord OAuth] 正在開啟瀏覽器授權: {auth_url}")
        webbrowser.open(auth_url)

        # 監聽單次請求
        try:
            server.handle_request()
        finally:
            server.server_close()
            self._server = None

        code = auth_code_holder["code"]
        if not code:
            err_msg = auth_code_holder["error"] or "授權超時或未完成授權"
            return {"ok": False, "msg": err_msg}

        # 拿 Code 兌換真實用戶身份
        return self.exchange_code_for_identity(code)

    def exchange_code_for_identity(self, code: str) -> Dict[str, Any]:
        """
        向 Discord 官方交換 Access Token 並提取用戶不可偽造的唯一身分
        """
        if not self.client_secret:
            # 若尚未配置 Client Secret，回傳已成功取得 Code 之憑證
            # (可交由後台或以 Code 完成標識)
            return {
                "ok": True,
                "code": code,
                "msg": "已取得 Discord 官方授權碼 (Code)，請配置 Client Secret 以自動獲取完整個人資料",
                "needs_secret": True
            }

        token_url = "https://discord.com/api/oauth2/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri
        }

        try:
            resp = requests.post(token_url, data=data, headers=headers, timeout=10)
            if resp.status_code != 200:
                logger.error(f"[Discord OAuth] Token 交換失敗 HTTP {resp.status_code}: {resp.text}")
                return {"ok": False, "msg": f"Token 交換失敗: HTTP {resp.status_code}"}

            token_data = resp.json()
            access_token = token_data.get("access_token")
            if not access_token:
                return {"ok": False, "msg": "未取得有效的 access_token"}

            # 抓取用戶資料
            user_url = "https://discord.com/api/users/@me"
            user_resp = requests.get(user_url, headers={"Authorization": f"Bearer {access_token}"}, timeout=8)
            if user_resp.status_code != 200:
                return {"ok": False, "msg": f"獲取 Discord 用戶資料失敗: HTTP {user_resp.status_code}"}

            user_data = user_resp.json()
            discord_id = str(user_data.get("id", ""))
            username = user_data.get("username", "")
            global_name = user_data.get("global_name") or username
            avatar_hash = user_data.get("avatar")
            
            avatar_url = ""
            if avatar_hash:
                avatar_url = f"https://cdn.discordapp.com/avatars/{discord_id}/{avatar_hash}.png"

            return {
                "ok": True,
                "discord_id": discord_id,
                "username": username,
                "global_name": global_name,
                "avatar_url": avatar_url,
                "access_token": access_token,
                "msg": f"認證成功！歡迎 @{username}"
            }
        except Exception as e:
            logger.error(f"[Discord OAuth] 請求 Discord 官方異常: {e}")
            return {"ok": False, "msg": f"連線至 Discord 失敗: {e}"}

_discord_service_inst: Optional[DiscordOAuthService] = None

def get_discord_oauth_service(client_secret: str = "") -> DiscordOAuthService:
    global _discord_service_inst
    sec = client_secret or DEFAULT_CLIENT_SECRET
    if _discord_service_inst is None:
        _discord_service_inst = DiscordOAuthService(client_id=DEFAULT_CLIENT_ID, client_secret=sec)
    else:
        _discord_service_inst.client_secret = sec
    return _discord_service_inst
