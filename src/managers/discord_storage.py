# -*- coding: utf-8 -*-
"""
DiscordStorage - SMU Discord Webhook 雲端傳輸引擎
支援透過 Discord Webhook 免登入上傳三檔整合包，享受 Discord Cloudflare CDN 無限下載頻寬。
- 單檔上限：25 MB (完美覆蓋 Manifest、Lua 與聯機補丁)
- 流量限制：永久無限 (免費)
- 生命週期：房間解散時自動調用 Webhook DELETE 刪除訊息與附件，無痕環保
"""

import os
import json
import logging
import requests
from pathlib import Path
from typing import Dict, Any, Optional

from managers import config_manager

logger = logging.getLogger("discord_storage")

class DiscordStorage:
    def __init__(self):
        self.root_dir = config_manager._root_dir
        self.config_path = self.root_dir / "data" / "secrets" / "party_cloud.json"
        self._cfg = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"讀取 party_cloud.json 失敗: {e}")
        return {}

    def _save_config(self):
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存 party_cloud.json 失敗: {e}")

    def get_custom_webhook_url(self) -> str:
        return self._cfg.get("custom_webhook_url", "").strip()

    def set_custom_webhook_url(self, url: str) -> bool:
        self._cfg["custom_webhook_url"] = str(url).strip()
        self._save_config()
        return True

    def test_webhook(self, webhook_url: str) -> Dict[str, Any]:
        """測試 Webhook 有效性"""
        url = str(webhook_url).strip()
        if not url or not url.startswith("https://discord.com/api/webhooks/"):
            return {"ok": False, "msg": "無效的 Discord Webhook 網址 (格式應為 https://discord.com/api/webhooks/...)"}
        try:
            payload = {
                "username": "SMU 雲端助理",
                "content": "✨ **SteamManifestUpdater 連線測試成功！** 本頻道已就緒作為組隊聯機整合包託管通道。"
            }
            resp = requests.post(url, json=payload, timeout=8)
            if resp.status_code in (200, 204):
                return {"ok": True, "msg": "✅ Discord Webhook 連線測試成功！"}
            else:
                return {"ok": False, "msg": f"Discord 回應錯誤: HTTP {resp.status_code}"}
        except Exception as e:
            return {"ok": False, "msg": f"連線異常: {e}"}

    def upload_package(self, file_path: str, room_code: str, webhook_url: str = "",
                       game_name: str = "", host_name: str = "") -> Dict[str, Any]:
        """
        透過 Discord Webhook 上傳三檔整合包
        :return: {"ok": bool, "download_url": str, "file_id": str, "provider": str, "msg": str}
        """
        p = Path(file_path)
        if not p.exists() or not p.is_file():
            return {"ok": False, "msg": f"待上傳檔案不存在: {file_path}"}

        file_size = p.stat().st_size
        if file_size > 25 * 1024 * 1024:
            return {"ok": False, "msg": f"整合包大小 ({file_size/1024/1024:.1f}MB) 超過 Discord 免費單檔 25MB 上限"}

        target_webhook = webhook_url.strip() or self.get_custom_webhook_url()
        if not target_webhook:
            return {"ok": False, "msg": "未設定 Discord Webhook 網址"}

        # 加上 wait=true 參數以確保 Discord 回傳包含 attachments 與 message id 的 JSON 物件
        sep = "&" if "?" in target_webhook else "?"
        post_url = f"{target_webhook}{sep}wait=true"

        filename = f"SMU_Party_{room_code}.zip"
        content_text = (
            f"🎮 **【{game_name or '聯機遊戲'}】組隊房間已建立！**\n"
            f"🔑 **房號**: `#{room_code}` ｜ 👑 **房主**: `{host_name or '玩家'}`\n"
            f"📦 核心三檔整合包已上傳完畢，隊友啟動 SMU 即可秒級下載入庫！"
        )

        try:
            with open(p, "rb") as f:
                files = {
                    "file": (filename, f, "application/zip")
                }
                data = {
                    "username": "SMU Party Hub",
                    "content": content_text
                }
                logger.info(f"[Discord] 正在上傳整合包 {filename} 至 Discord Webhook...")
                resp = requests.post(post_url, data=data, files=files, timeout=40)

            if resp.status_code in (200, 201):
                res_data = resp.json()
                message_id = res_data.get("id", "")
                attachments = res_data.get("attachments", [])
                if attachments and attachments[0].get("url"):
                    download_url = attachments[0]["url"]
                    file_id = f"discord:{message_id}:{target_webhook}"
                    logger.info(f"[Discord] 上傳成功！下載直鏈: {download_url} (MsgID: {message_id})")
                    return {
                        "ok": True,
                        "download_url": download_url,
                        "file_id": file_id,
                        "message_id": message_id,
                        "size": file_size,
                        "filename": filename,
                        "provider": "Discord CDN (無限流量)",
                        "msg": "✅ 整合包已成功上傳至 Discord 專用 CDN (無限下載流量)！"
                    }
                else:
                    return {"ok": False, "msg": "Discord 未能回傳有效附件下載直鏈"}
            else:
                return {"ok": False, "msg": f"Discord 上傳失敗: HTTP {resp.status_code} {resp.text[:120]}"}
        except Exception as e:
            logger.error(f"[Discord] 上傳異常: {e}", exc_info=True)
            return {"ok": False, "msg": f"Discord Webhook 連線異常: {e}"}

    def delete_package(self, file_id: str) -> bool:
        """
        房間解散時自動抹除 Discord 頻道的開房訊息與附件
        file_id 格式: discord:{message_id}:{webhook_url}
        """
        if not file_id or not file_id.startswith("discord:"):
            return False

        try:
            parts = file_id.split(":", 2)
            if len(parts) < 3:
                return False
            message_id = parts[1]
            webhook_url = parts[2]

            # Discord Webhook 刪除訊息端點: DELETE {webhook_url}/messages/{message_id}
            del_url = f"{webhook_url.rstrip('/')}/messages/{message_id}"
            r = requests.delete(del_url, timeout=8)
            logger.info(f"[Discord] 已自動刪除開房訊息與附件: MsgID {message_id} (HTTP {r.status_code})")
            return r.status_code in (200, 204)
        except Exception as e:
            logger.warning(f"[Discord] 刪除訊息異常: {e}")
            return False

_discord_storage_inst = None

def get_discord_storage() -> DiscordStorage:
    global _discord_storage_inst
    if _discord_storage_inst is None:
        _discord_storage_inst = DiscordStorage()
    return _discord_storage_inst
