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
import re
import time
import requests
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

from managers import config_manager

logger = logging.getLogger("discord_storage")

DISCORD_WEBHOOK_PATTERN = re.compile(
    r"^https:\/\/(?:(?:canary|ptb)\.)?discord(?:app)?\.com\/api\/webhooks\/\d+\/[A-Za-z0-9_-]+$",
    re.IGNORECASE
)

def is_valid_webhook_url(url: str) -> bool:
    """嚴格校驗 Discord Webhook 網址格式 (包含正常、PTB 與 Canary 官方域名)"""
    if not url or not isinstance(url, str):
        return False
    return bool(DISCORD_WEBHOOK_PATTERN.match(url.strip()))

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
        """測試 Webhook 有效性、主動讀取伺服器與頻道名稱並自動記憶"""
        url = str(webhook_url).strip()
        if not is_valid_webhook_url(url):
            return {"ok": False, "msg": "無效的 Discord Webhook 網址 (格式應為 https://discord.com/api/webhooks/... 或 ptb/canary 官方格式)"}
        try:
            # 1. 主動以 GET 請求獲取 Webhook 自身中繼資料 (名稱、頻道 ID、伺服器 ID)
            webhook_name = "Discord Webhook"
            channel_id = ""
            guild_id = ""
            try:
                get_resp = requests.get(url, timeout=6)
                if get_resp.status_code == 200:
                    info_data = get_resp.json()
                    webhook_name = info_data.get("name") or webhook_name
                    channel_id = str(info_data.get("channel_id") or "")
                    guild_id = str(info_data.get("guild_id") or "")
                elif get_resp.status_code == 404:
                    return {"ok": False, "msg": "❌ Discord 回應: 找不到此 Webhook (404 Unknown Webhook)，請確認網址是否正確或已被刪除"}
                elif get_resp.status_code == 401:
                    return {"ok": False, "msg": "❌ Discord 回應: Webhook 授權 Token 無效 (401 Unauthorized)"}
            except Exception as e_get:
                logger.warning(f"[DiscordStorage] 取得 Webhook 資訊微幅逾時或異常: {e_get}")

            # 2. 發送帶 ?wait=true 的測試訊息 Embed 卡片
            payload = {
                "username": "SMU 雲端助理",
                "embeds": [{
                    "title": "✨ SteamManifestUpdater 連線測試成功！",
                    "description": (
                        "本頻道已成功對接為 SteamManifestUpdater 整合包通道！\n"
                        f"• Webhook 名稱：**{webhook_name}**\n"
                        + (f"• 對接頻道 ID：`{channel_id}`\n" if channel_id else "")
                        + "連線狀態正常，可享受 Discord 免費高速 CDN 頻寬！"
                    ),
                    "color": 5814783
                }]
            }
            post_url = url + ("&wait=true" if "?" in url else "?wait=true")
            resp = requests.post(post_url, json=payload, timeout=8)
            if resp.status_code in (200, 204):
                # 測試成功，自動記憶保存到本機設定
                self.set_custom_webhook_url(url)
                channel_info = f" (頻道 ID: {channel_id})" if channel_id else ""
                return {
                    "ok": True,
                    "msg": f"✅ Webhook 連線測試成功！已成功連線至【{webhook_name}】{channel_info}",
                    "details": {
                        "name": webhook_name,
                        "channel_id": channel_id,
                        "guild_id": guild_id
                    }
                }
            elif resp.status_code == 404:
                return {"ok": False, "msg": "❌ Discord 回應: 找不到此 Webhook (404 Unknown Webhook)"}
            elif resp.status_code == 401:
                return {"ok": False, "msg": "❌ Discord 回應: Webhook Token 授權失敗 (401 Unauthorized)"}
            else:
                return {"ok": False, "msg": f"❌ Discord 回應錯誤: HTTP {resp.status_code}"}
        except Exception as e:
            return {"ok": False, "msg": f"連線異常: {e}"}

    # 嚴格定義單檔上傳安全閾值 (9MB) 與分卷切片大小 (8MB)，兼容 Discord 10MB 免加成伺服器上限並降低單卷下載超時風險
    MAX_SINGLE_FILE_SIZE = 9 * 1024 * 1024   # 9 MB 觸發切割閾值
    CHUNK_SIZE = 8 * 1024 * 1024             # 8 MB 安全切片大小 (確保不觸發 Discord 10MB/25MB 上限)

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
        if not is_valid_webhook_url(target_webhook):
            return {"ok": False, "msg": "無效的 Discord Webhook 網址格式 (必須為 https://discord.com/api/webhooks/... 或 ptb/canary 官方格式)"}

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
            logger.info(f"[Discord] 已將整合包安全切成 {total_parts} 個分卷 (每卷 <= 8MB)")

            # 2. 逐卷上傳至 Discord Webhook (含自動重試與 429 限流退避)
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
                part_uploaded = False
                last_err_msg = ""
                for attempt in range(1, 4):
                    try:
                        with open(p_file, "rb") as f:
                            files = {
                                "file": (part_filename, f, "application/octet-stream")
                            }
                            data = {
                                "username": "SMU Party Hub",
                                "content": part_content
                            }
                            logger.info(f"[Discord] 正在上傳分卷 {idx}/{total_parts} (嘗試 {attempt}/3): {part_filename}...")
                            resp = requests.post(post_url, data=data, files=files, timeout=60)

                        if resp.status_code in (200, 201):
                            res_data = resp.json()
                            msg_id = res_data.get("id")
                            atts = res_data.get("attachments", [])
                            if atts and atts[0].get("url"):
                                message_ids.append(msg_id)
                                download_urls.append(atts[0]["url"])
                                logger.info(f"[Discord] 分卷 {idx}/{total_parts} 上傳成功！MsgID: {msg_id}")
                                part_uploaded = True
                                break
                            else:
                                last_err_msg = f"分卷 {idx} 上傳成功但未收到附件直鏈"
                        elif resp.status_code == 429:
                            retry_after = 2.0
                            try:
                                retry_after = float(resp.json().get("retry_after", 2.0)) + 0.5
                            except Exception:
                                pass
                            logger.warning(f"[Discord] 分卷 {idx} 觸發頻率限制 (HTTP 429)，等待 {retry_after:.1f}s 後重試...")
                            time.sleep(retry_after)
                            last_err_msg = "HTTP 429 Too Many Requests"
                        else:
                            last_err_msg = f"分卷 {idx}/{total_parts} 上傳失敗: HTTP {resp.status_code}"
                            time.sleep(1.0 * attempt)
                    except Exception as up_err:
                        last_err_msg = f"分卷 {idx}/{total_parts} 上傳網路異常: {up_err}"
                        logger.warning(f"[Discord] {last_err_msg}")
                        time.sleep(1.2 * attempt)

                if not part_uploaded:
                    return {"ok": False, "msg": last_err_msg or f"分卷 {idx}/{total_parts} 上傳失敗"}

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

    # ═════════════════════════════════════════════════════════════════════
    # 🎫 友邀代碼專屬：免資料庫封裝上傳與動態簽章直鏈解析
    # ═════════════════════════════════════════════════════════════════════

    def upload_friend_code_package(
        self,
        file_path: str,
        app_id: str,
        webhook_url: str = "",
        game_name: str = "",
        progress_cb=None
    ) -> Dict[str, Any]:
        """
        為「友邀代碼」上傳核心三檔整合包至 Discord Webhook：
        - 單檔 (<= 9MB)：單一訊息同時夾帶附件與結構化 Embed 元資料，回傳該訊息之 entry_message_id。
        - 多分卷 (> 9MB)：切片為 <= 8MB 分卷逐一上傳後，額外發送 1 則輕量索引訊息記載所有分卷 MsgID，
          使友邀代碼無論面對單檔或數十個分卷，皆能維持固定 52 碼極簡長度！
        """
        p = Path(file_path)
        if not p.exists() or not p.is_file():
            return {"ok": False, "msg": f"待上傳整合包不存在: {file_path}"}

        file_size = p.stat().st_size
        target_webhook = (webhook_url or "").strip() or self.get_custom_webhook_url()
        if not target_webhook:
            return {"ok": False, "msg": "請先填寫 Discord Webhook 網址"}
        if not is_valid_webhook_url(target_webhook):
            return {"ok": False, "msg": "無效的 Discord Webhook 網址格式 (須為 https://discord.com/api/webhooks/...)"}

        clean_webhook = target_webhook.split("?")[0].rstrip("/")
        post_url = f"{clean_webhook}?wait=true"
        now_ts = int(time.time())
        safe_game = (game_name or f"AppID {app_id}").strip()

        # -------------------------------------------------------------
        # 情況 A: 單檔直傳 (<= 9MB)
        # -------------------------------------------------------------
        if file_size <= self.MAX_SINGLE_FILE_SIZE:
            if callable(progress_cb):
                progress_cb(f"正在上傳整合包至 Discord CDN ({file_size / 1024 / 1024:.2f} MB)…", 55)

            filename = f"SMU_Friend_{app_id}.zip"
            fc_meta = {
                "v": 1,
                "mode": "single",
                "app_id": str(app_id),
                "game_name": safe_game[:80],
                "size": file_size,
                "ts": now_ts,
            }
            payload_obj = {
                "username": "SMU 友邀代碼託管",
                "embeds": [{
                    "title": f"🎫 【{safe_game}】友邀代碼整合包",
                    "description": (
                        f"🎮 **遊戲 AppID**：`{app_id}`\n"
                        f"📦 **整合包大小**：`{file_size / 1024 / 1024:.2f} MB` (單檔極速包)\n"
                        f"🔒 **狀態**：已加密生成友邀代碼，好友貼上代碼即可全自動下載安裝。"
                    ),
                    "color": 16748455,
                    "footer": {"text": "SMU_FC_V1:" + json.dumps(fc_meta, ensure_ascii=False, separators=(",", ":"))}
                }]
            }

            last_err = ""
            for attempt in range(1, 4):
                try:
                    with open(p, "rb") as f:
                        files = {"file": (filename, f, "application/zip")}
                        data = {"payload_json": json.dumps(payload_obj, ensure_ascii=False)}
                        resp = requests.post(post_url, data=data, files=files, timeout=60)

                    if resp.status_code in (200, 201):
                        res_data = resp.json()
                        msg_id = str(res_data.get("id", "")).strip()
                        atts = res_data.get("attachments", [])
                        if msg_id and atts and atts[0].get("url"):
                            self.set_custom_webhook_url(clean_webhook)
                            return {
                                "ok": True,
                                "entry_message_id": int(msg_id),
                                "is_multipart": False,
                                "total_parts": 1,
                                "size": file_size,
                                "webhook_url": clean_webhook,
                                "file_id": f"discord:{msg_id}:{clean_webhook}",
                                "msg": "✅ 整合包已上傳並完成友邀代碼加密封裝！"
                            }
                        last_err = "Discord 未回傳有效訊息 ID 或附件"
                    elif resp.status_code == 429:
                        wait_s = 2.0
                        try:
                            wait_s = float(resp.json().get("retry_after", 2.0)) + 0.5
                        except Exception:
                            pass
                        time.sleep(wait_s)
                        last_err = "Discord 請求過於頻繁 (HTTP 429)"
                    else:
                        last_err = f"Discord 上傳失敗 (HTTP {resp.status_code})"
                        time.sleep(1.0 * attempt)
                except Exception as e:
                    last_err = f"Webhook 連線異常: {e}"
                    time.sleep(1.2 * attempt)

            return {"ok": False, "msg": last_err or "上傳至 Discord Webhook 失敗"}

        # -------------------------------------------------------------
        # 情況 B: 大檔多分卷切片 (> 9MB) + 單一輕量索引訊息
        # -------------------------------------------------------------
        split_dir = self.root_dir / "data" / "party_packages" / "friend_split_temp"
        split_dir.mkdir(parents=True, exist_ok=True)
        part_paths = []

        try:
            if callable(progress_cb):
                progress_cb(f"整合包較大 ({file_size / 1024 / 1024:.2f} MB)，正在執行無損分卷切片…", 35)

            tag = f"{app_id}_{now_ts % 100000}"
            with open(p, "rb") as src:
                part_idx = 1
                while True:
                    chunk = src.read(self.CHUNK_SIZE)
                    if not chunk:
                        break
                    p_path = split_dir / f"SMU_FC_{tag}.part{part_idx}"
                    with open(p_path, "wb") as dst:
                        dst.write(chunk)
                    part_paths.append(p_path)
                    part_idx += 1

            total_parts = len(part_paths)
            part_msg_ids = []

            for idx, p_file in enumerate(part_paths, 1):
                pct = 40 + int(((idx - 1) / max(1, total_parts)) * 48)
                if callable(progress_cb):
                    progress_cb(f"正在上傳分卷 ({idx}/{total_parts}) 至 Discord CDN…", pct)

                part_size = p_file.stat().st_size
                part_content = (
                    f"📦 **【{safe_game}】友邀代碼整合包分卷 ({idx}/{total_parts})**\n"
                    f"🎮 AppID: `{app_id}` ｜ ⚡ 本卷: `{part_size / 1024 / 1024:.2f} MB` / 總計: `{file_size / 1024 / 1024:.2f} MB`"
                )

                uploaded = False
                last_err = ""
                for attempt in range(1, 4):
                    try:
                        with open(p_file, "rb") as f:
                            files = {"file": (p_file.name, f, "application/octet-stream")}
                            data = {"username": "SMU 友邀代碼託管", "content": part_content}
                            resp = requests.post(post_url, data=data, files=files, timeout=60)

                        if resp.status_code in (200, 201):
                            res_data = resp.json()
                            mid = str(res_data.get("id", "")).strip()
                            atts = res_data.get("attachments", [])
                            if mid and atts and atts[0].get("url"):
                                part_msg_ids.append(mid)
                                uploaded = True
                                break
                            last_err = f"分卷 {idx} 未收到附件資訊"
                        elif resp.status_code == 429:
                            wait_s = 2.0
                            try:
                                wait_s = float(resp.json().get("retry_after", 2.0)) + 0.5
                            except Exception:
                                pass
                            time.sleep(wait_s)
                            last_err = "HTTP 429 Too Many Requests"
                        else:
                            last_err = f"分卷 {idx} 上傳失敗: HTTP {resp.status_code}"
                            time.sleep(1.0 * attempt)
                    except Exception as e:
                        last_err = f"分卷 {idx} 上傳異常: {e}"
                        time.sleep(1.2 * attempt)

                if not uploaded:
                    # 清除已上傳之殘留分卷，保持頻道乾淨
                    if part_msg_ids:
                        self.delete_package(f"discord_parts:{','.join(part_msg_ids)}:{clean_webhook}")
                    return {"ok": False, "msg": last_err or f"分卷 {idx}/{total_parts} 上傳失敗"}

            # 發送最終索引訊息 (記錄所有分卷 MsgID)
            if callable(progress_cb):
                progress_cb("正在寫入分卷加密索引並簽發友邀代碼…", 92)

            fc_meta = {
                "v": 1,
                "mode": "multipart",
                "app_id": str(app_id),
                "game_name": safe_game[:80],
                "size": file_size,
                "ts": now_ts,
                "parts": part_msg_ids,
            }
            meta_str = "SMU_FC_V1:" + json.dumps(fc_meta, ensure_ascii=False, separators=(",", ":"))
            embed_obj: Dict[str, Any] = {
                "title": f"🎫 【{safe_game}】友邀代碼多分卷索引 ({total_parts} 卷)",
                "description": (
                    f"🎮 **遊戲 AppID**：`{app_id}`\n"
                    f"📦 **總計大小**：`{file_size / 1024 / 1024:.2f} MB` (共 `{total_parts}` 個安全分卷)\n"
                    f"🔒 **狀態**：索引已建立，請勿刪除此訊息以免友邀代碼失效。"
                ),
                "color": 16748455,
            }
            if len(meta_str) <= 2000:
                embed_obj["footer"] = {"text": meta_str}
            else:
                embed_obj["description"] += f"\n```json\n{meta_str}\n```"

            idx_payload = {
                "username": "SMU 友邀代碼託管",
                "embeds": [embed_obj]
            }

            idx_msg_id = ""
            last_idx_err = ""
            for attempt in range(1, 4):
                try:
                    resp = requests.post(post_url, json=idx_payload, timeout=20)
                    if resp.status_code in (200, 201):
                        idx_msg_id = str(resp.json().get("id", "")).strip()
                        if idx_msg_id:
                            break
                    elif resp.status_code == 429:
                        wait_s = 2.0
                        try:
                            wait_s = float(resp.json().get("retry_after", 2.0)) + 0.5
                        except Exception:
                            pass
                        time.sleep(wait_s)
                    else:
                        last_idx_err = f"索引訊息建立失敗: HTTP {resp.status_code}"
                        time.sleep(1.0)
                except Exception as e:
                    last_idx_err = str(e)
                    time.sleep(1.0)

            if not idx_msg_id:
                self.delete_package(f"discord_parts:{','.join(part_msg_ids)}:{clean_webhook}")
                return {"ok": False, "msg": f"建立多分卷索引失敗: {last_idx_err}"}

            all_ids = part_msg_ids + [idx_msg_id]
            self.set_custom_webhook_url(clean_webhook)
            return {
                "ok": True,
                "entry_message_id": int(idx_msg_id),
                "is_multipart": True,
                "total_parts": total_parts,
                "size": file_size,
                "webhook_url": clean_webhook,
                "file_id": f"discord_parts:{','.join(all_ids)}:{clean_webhook}",
                "msg": f"✅ 已安全切成 {total_parts} 卷上傳並生成加密友邀代碼！"
            }
        except Exception as e:
            logger.error(f"[Discord] 友邀代碼分卷上傳異常: {e}", exc_info=True)
            return {"ok": False, "msg": f"分卷上傳異常: {e}"}
        finally:
            for pf in part_paths:
                try:
                    if pf.exists():
                        pf.unlink()
                except Exception:
                    pass

    def _fetch_webhook_message(self, clean_webhook: str, message_id: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """透過 Discord Webhook GET API 動態取得訊息與最新簽發之 24h CDN 附件直鏈"""
        url = f"{clean_webhook.rstrip('/')}/messages/{str(message_id).strip()}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SMU-Client/2.0"
        }
        for attempt in range(1, 4):
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    return resp.json(), ""
                elif resp.status_code == 404:
                    return None, "此友邀代碼對應的整合包訊息已被刪除或不存在 (HTTP 404)"
                elif resp.status_code in (401, 403):
                    return None, "此友邀代碼的 Discord Webhook 已被頻道管理員撤銷或失效"
                elif resp.status_code == 429:
                    wait_s = 1.8
                    try:
                        wait_s = float(resp.json().get("retry_after", 1.8)) + 0.3
                    except Exception:
                        pass
                    time.sleep(wait_s)
                else:
                    time.sleep(0.8 * attempt)
            except Exception as e:
                if attempt == 3:
                    return None, f"連線至 Discord 伺服器失敗: {e}"
                time.sleep(0.8 * attempt)
        return None, "無法由 Discord Webhook 讀取整合包資訊"

    def resolve_friend_code_package(
        self,
        webhook_url: str,
        entry_message_id: str,
        fetch_part_urls: bool = True
    ) -> Dict[str, Any]:
        """
        接收端解析：向 Discord Webhook 查詢入口訊息，動態簽發最新有效之 CDN 下載直鏈清單。
        即使代碼發布超過 24 小時，每次呼叫仍會由 Discord 動態換發全新簽章 URL，永不過期！
        """
        import concurrent.futures
        clean_webhook = (webhook_url or "").split("?")[0].rstrip("/")
        msg_data, err = self._fetch_webhook_message(clean_webhook, str(entry_message_id))
        if not msg_data:
            return {"ok": False, "msg": err}

        # 解析 SMU_FC_V1 元資料
        fc_meta: Dict[str, Any] = {}
        embeds = msg_data.get("embeds") or []
        for emb in embeds:
            footer_txt = (emb.get("footer") or {}).get("text") or ""
            desc_txt = emb.get("description") or ""
            for candidate in (footer_txt, desc_txt):
                idx = candidate.find("SMU_FC_V1:")
                if idx != -1:
                    raw_json = candidate[idx + len("SMU_FC_V1:"):].strip()
                    if raw_json.endswith("```"):
                        raw_json = raw_json[:-3].strip()
                    try:
                        fc_meta = json.loads(raw_json)
                        break
                    except Exception:
                        pass
            if fc_meta:
                break

        mode = fc_meta.get("mode", "single")
        app_id = str(fc_meta.get("app_id", "")).strip()
        game_name = str(fc_meta.get("game_name", "")).strip()
        total_size = int(fc_meta.get("size", 0) or 0)

        # 單檔備援：從附件檔名 SMU_Friend_{app_id}.zip 推導
        atts = msg_data.get("attachments") or []
        if not app_id and atts:
            fn = atts[0].get("filename", "")
            m_aid = re.search(r"SMU_(?:Friend|Party)_(\d+)\.zip", fn)
            if m_aid:
                app_id = m_aid.group(1)
            if not total_size:
                total_size = int(atts[0].get("size", 0) or 0)

        if mode == "multipart" or fc_meta.get("parts"):
            part_ids = [str(x).strip() for x in (fc_meta.get("parts") or []) if str(x).strip()]
            if not part_ids:
                return {"ok": False, "msg": "多分卷索引訊息缺少分卷清單"}

            if not fetch_part_urls:
                return {
                    "ok": True,
                    "is_multipart": True,
                    "total_parts": len(part_ids),
                    "app_id": app_id,
                    "game_name": game_name or (f"AppID {app_id}" if app_id else "好友分享遊戲"),
                    "size": total_size,
                    "download_urls": [],
                }

            # 併發取得各分卷之最新簽章 CDN URL (保持嚴格順序)
            ordered_urls: List[Optional[str]] = [None] * len(part_ids)
            part_err = ""

            def _resolve_one(idx_and_mid):
                i, p_mid = idx_and_mid
                pdata, perr = self._fetch_webhook_message(clean_webhook, p_mid)
                if not pdata:
                    return i, None, perr
                patts = pdata.get("attachments") or []
                if not patts or not patts[0].get("url"):
                    return i, None, f"分卷 {i + 1} 附件遺失"
                return i, patts[0]["url"], ""

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                for i, purl, perr in pool.map(_resolve_one, enumerate(part_ids)):
                    if not purl:
                        part_err = perr or f"無法取得分卷 {i + 1} 下載直鏈"
                        break
                    ordered_urls[i] = purl

            if part_err or any(u is None for u in ordered_urls):
                return {"ok": False, "msg": part_err or "部分分卷在 Discord 頻道中已被刪除，無法完整下載"}

            return {
                "ok": True,
                "is_multipart": True,
                "total_parts": len(ordered_urls),
                "app_id": app_id,
                "game_name": game_name or (f"AppID {app_id}" if app_id else "好友分享遊戲"),
                "size": total_size,
                "download_urls": [u for u in ordered_urls if u],
            }

        # 單檔模式
        if not atts or not atts[0].get("url"):
            return {"ok": False, "msg": "Discord 訊息內找不到整合包附件，可能已被刪除"}

        if not total_size:
            total_size = int(atts[0].get("size", 0) or 0)

        return {
            "ok": True,
            "is_multipart": False,
            "total_parts": 1,
            "app_id": app_id,
            "game_name": game_name or (f"AppID {app_id}" if app_id else "好友分享遊戲"),
            "size": total_size,
            "download_urls": [atts[0]["url"]],
        }

_discord_storage_inst = None

def get_discord_storage() -> DiscordStorage:
    global _discord_storage_inst
    if _discord_storage_inst is None:
        _discord_storage_inst = DiscordStorage()
    return _discord_storage_inst
