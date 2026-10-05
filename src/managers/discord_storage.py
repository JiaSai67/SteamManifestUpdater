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
        """測試 Webhook 有效性並自動記憶"""
        url = str(webhook_url).strip()
        if not url or "/api/webhooks/" not in url or not (url.startswith("http://") or url.startswith("https://")):
            return {"ok": False, "msg": "無效的 Discord Webhook 網址 (格式應為 https://discord.com/api/webhooks/... 或 ptb/canary 域名)"}
        try:
            payload = {
                "username": "SMU 雲端助理",
                "embeds": [{
                    "title": "✨ SteamManifestUpdater 連線測試成功！",
                    "description": "本頻道已就緒作為組隊聯機整合包託管通道。\n開房時整合包將透過此處上傳至 Discord 專用 CDN，隊友可享受無限下載頻寬！",
                    "color": 5814783
                }]
            }
            resp = requests.post(url, json=payload, timeout=8)
            if resp.status_code in (200, 204):
                # 測試成功，自動記憶保存到本機設定
                self.set_custom_webhook_url(url)
                return {"ok": True, "msg": "✅ Discord Webhook 連線測試成功！已自動保存設定"}
            else:
                return {"ok": False, "msg": f"Discord 回應錯誤: HTTP {resp.status_code}"}
        except Exception as e:
            return {"ok": False, "msg": f"連線異常: {e}"}

    # 嚴格定義單檔上傳安全閾值 (20MB) 與分卷切片大小 (19MB)
    MAX_SINGLE_FILE_SIZE = 20 * 1024 * 1024  # 20 MB 觸發切割閾值
    CHUNK_SIZE = 19 * 1024 * 1024            # 19 MB 安全切片大小 (確保不觸發 Discord 25MB 上限)

    def upload_package(self, file_path: str, room_code: str, webhook_url: str = "",
                       game_name: str = "", host_name: str = "") -> Dict[str, Any]:
        """
        透過 Discord Webhook 上傳三檔整合包。
        若檔案超過 20MB，自動執行安全二進位切片分卷 (Part 1, Part 2...) 分批上傳，徹底突破 25MB 限制。
        :return: {"ok": bool, "download_url": str, "file_id": str, "provider": str, "msg": str}
        """
        p = Path(file_path)
        if not p.exists() or not p.is_file():
            return {"ok": False, "msg": f"待上傳檔案不存在: {file_path}"}

        file_size = p.stat().st_size
        target_webhook = webhook_url.strip() or self.get_custom_webhook_url()
        if not target_webhook:
            return {"ok": False, "msg": "未設定 Discord Webhook 網址"}

        sep = "&" if "?" in target_webhook else "?"
        post_url = f"{target_webhook}{sep}wait=true"

        # -------------------------------------------------------------
        # 情況 A: 檔案 <= 20MB，走標準單檔上傳
        # -------------------------------------------------------------
        if file_size <= self.MAX_SINGLE_FILE_SIZE:
            filename = f"SMU_Party_{room_code}.zip"
            content_text = (
                f"🎮 **【{game_name or '聯機遊戲'}】組隊房間已建立！**\n"
                f"🔑 **房號**: `#{room_code}` ｜ 👑 **房主**: `{host_name or '玩家'}`\n"
                f"📦 核心三檔整合包 ({file_size/1024/1024:.2f} MB) 已上傳完畢，隊友啟動 SMU 即可秒級下載入庫！"
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
                    logger.info(f"[Discord] 正在上傳單檔整合包 {filename} ({file_size/1024/1024:.2f}MB) 至 Discord Webhook...")
                    resp = requests.post(post_url, data=data, files=files, timeout=40)

                if resp.status_code in (200, 201):
                    res_data = resp.json()
                    message_id = res_data.get("id", "")
                    attachments = res_data.get("attachments", [])
                    if attachments and attachments[0].get("url"):
                        download_url = attachments[0]["url"]
                        file_id = f"discord:{message_id}:{target_webhook}"
                        self.set_custom_webhook_url(target_webhook)
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

        # -------------------------------------------------------------
        # 情況 B: 檔案 > 20MB，啟動大檔安全分卷切片機制 (Part 1, Part 2...)
        # -------------------------------------------------------------
        logger.info(f"[Discord] 檢測到整合包大小為 {file_size/1024/1024:.2f} MB (> 20MB 安全閾值)，啟動多分卷切片上傳...")
        split_dir = self.root_dir / "data" / "party_packages" / "split_temp"
        split_dir.mkdir(parents=True, exist_ok=True)

        part_paths = []
        try:
            # 1. 本地二進位切片
            with open(p, "rb") as src:
                part_idx = 1
                while True:
                    chunk = src.read(self.CHUNK_SIZE)
                    if not chunk:
                        break
                    p_path = split_dir / f"SMU_Party_{room_code}.part{part_idx}"
                    with open(p_path, "wb") as dst:
                        dst.write(chunk)
                    part_paths.append(p_path)
                    part_idx += 1

            total_parts = len(part_paths)
            logger.info(f"[Discord] 已將整合包安全切成 {total_parts} 個分卷 (每卷 <= 19MB)")

            # 2. 逐卷上傳至 Discord Webhook
            download_urls = []
            message_ids = []

            for idx, p_file in enumerate(part_paths, 1):
                part_size = p_file.stat().st_size
                part_filename = p_file.name
                part_content = (
                    f"📦 **【{game_name or '聯機遊戲'}】整合包分卷切片 ({idx}/{total_parts})**\n"
                    f"🔑 房號: `#{room_code}` ｜ 👑 房主: `{host_name or '玩家'}`\n"
                    f"⚡ 本卷大小: `{part_size/1024/1024:.2f} MB` ｜ 總大小: `{file_size/1024/1024:.2f} MB`"
                )
                with open(p_file, "rb") as f:
                    files = {
                        "file": (part_filename, f, "application/octet-stream")
                    }
                    data = {
                        "username": "SMU Party Hub",
                        "content": part_content
                    }
                    logger.info(f"[Discord] 正在上傳分卷 {idx}/{total_parts}: {part_filename}...")
                    resp = requests.post(post_url, data=data, files=files, timeout=50)

                if resp.status_code in (200, 201):
                    res_data = resp.json()
                    msg_id = res_data.get("id")
                    atts = res_data.get("attachments", [])
                    if atts and atts[0].get("url"):
                        message_ids.append(msg_id)
                        download_urls.append(atts[0]["url"])
                        logger.info(f"[Discord] 分卷 {idx}/{total_parts} 上傳成功！MsgID: {msg_id}")
                    else:
                        return {"ok": False, "msg": f"分卷 {idx} 上傳成功但未收到附件直鏈"}
                else:
                    return {"ok": False, "msg": f"分卷 {idx}/{total_parts} 上傳失敗: HTTP {resp.status_code}"}

            # 3. 封裝多卷複合式資訊
            composite_url = f"multipart:{'|||'.join(download_urls)}"
            composite_file_id = f"discord_parts:{','.join(message_ids)}:{target_webhook}"
            self.set_custom_webhook_url(target_webhook)

            logger.info(f"[Discord] 恭喜！{total_parts} 個分卷全部上傳完畢！")
            return {
                "ok": True,
                "download_url": composite_url,
                "file_id": composite_file_id,
                "size": file_size,
                "is_multipart": True,
                "total_parts": total_parts,
                "filename": f"SMU_Party_{room_code}.zip (共 {total_parts} 卷)",
                "provider": f"Discord CDN ({total_parts} 分卷 · 無限流量)",
                "msg": f"✅ 整合包已安全切成 {total_parts} 個分卷並成功上傳至 Discord CDN！"
            }

        except Exception as e:
            logger.error(f"[Discord] 分卷切片上傳失敗: {e}", exc_info=True)
            return {"ok": False, "msg": f"分卷切片上傳異常: {e}"}
        finally:
            # 清理臨時切片檔案
            for p_file in part_paths:
                try:
                    if p_file.exists():
                        p_file.unlink()
                except Exception:
                    pass

    def delete_package(self, file_id: str) -> bool:
        """
        房間解散時自動抹除 Discord 頻道的開房訊息與附件。
        支援單一檔案 (discord:{msg_id}:{webhook}) 與多卷檔案 (discord_parts:{msg_id1},{msg_id2}:{webhook})。
        """
        if not file_id:
            return False

        try:
            # 情況 A: 多分卷批次刪除
            if file_id.startswith("discord_parts:"):
                parts = file_id.split(":", 2)
                if len(parts) < 3:
                    return False
                msg_ids = parts[1].split(",")
                webhook_url = parts[2].rstrip("/")
                all_ok = True
                for mid in msg_ids:
                    mid = mid.strip()
                    if not mid:
                        continue
                    del_url = f"{webhook_url}/messages/{mid}"
                    r = requests.delete(del_url, timeout=8)
                    logger.info(f"[Discord] 已抹除分卷訊息 MsgID {mid} (HTTP {r.status_code})")
                    if r.status_code not in (200, 204):
                        all_ok = False
                return all_ok

            # 情況 B: 單檔刪除
            elif file_id.startswith("discord:"):
                parts = file_id.split(":", 2)
                if len(parts) < 3:
                    return False
                message_id = parts[1]
                webhook_url = parts[2].rstrip("/")

                del_url = f"{webhook_url}/messages/{message_id}"
                r = requests.delete(del_url, timeout=8)
                logger.info(f"[Discord] 已自動刪除開房訊息與附件: MsgID {message_id} (HTTP {r.status_code})")
                return r.status_code in (200, 204)

            return False
        except Exception as e:
            logger.warning(f"[Discord] 刪除訊息異常: {e}")
            return False

_discord_storage_inst = None

def get_discord_storage() -> DiscordStorage:
    global _discord_storage_inst
    if _discord_storage_inst is None:
        _discord_storage_inst = DiscordStorage()
    return _discord_storage_inst
