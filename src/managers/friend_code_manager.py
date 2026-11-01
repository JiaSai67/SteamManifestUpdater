# -*- coding: utf-8 -*-
"""
FriendCodeManager - SMU「友邀代碼」無伺服器點對點打包、加密發布與全自動安裝引擎

核心特性：
1. 零雲端資料庫依賴 (Zero Supabase / Zero Turso / Zero OAuth 門檻)：
   好友之間僅需一方提供 Discord Webhook 即可完成打包與託管。
2. 固定 52 碼中英混合加密代碼：
   將 Webhook 授權端點 + 打包當下毫秒級訊息時間戳以 AEAD-SIV 對稱加密濃縮為 52 碼。
3. 動態簽發永不過期直鏈 + 全自動五階段安裝：
   接收端本地解密後，動態向 Discord Webhook 換發最新有效 CDN 直鏈，
   自動完成「下載 (含多分卷無損合併) ➔ 部署 Manifest/Lua ➔ 喚起並監控 Steam 下載 ➔ 套用線上聯機補丁」。
"""

import os
import re
import json
import time
import uuid
import shutil
import zipfile
import logging
import threading
import datetime
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional

from managers import config_manager
from managers import steam_manager
from managers import onlinefix_manager
from managers.party_packager import get_party_packager
from managers.discord_storage import get_discord_storage, is_valid_webhook_url
from utils import friend_code_crypto

logger = logging.getLogger("friend_code_manager")


class FriendCodeManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(FriendCodeManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.root_dir = config_manager._root_dir
        self.history_path = self.root_dir / "data" / "friend_codes_history.json"
        self._history_lock = threading.Lock()

        # 發起方 (打包上傳) 即時狀態
        self._host_lock = threading.Lock()
        self._host_task_running = False
        self._host_state: Dict[str, Any] = {
            "state": "idle",       # idle | running | success | error
            "progress": 0,
            "status_text": "準備就緒",
            "error_msg": "",
            "result": None,
        }

        # 接收方 (解密下載與一鍵安裝) 即時狀態
        self._recv_lock = threading.Lock()
        self._recv_task_id: str = ""
        self._recv_running = False
        self._recv_state: Dict[str, Any] = {
            "state": "idle",       # idle | running | success | error | cancelled
            "stage": 0,            # 1:解密解析 2:下載合併 3:清單部署 4:Steam主程式 5:聯機補丁
            "progress": 0,
            "status_text": "等待輸入友邀代碼",
            "game_name": "",
            "app_id": "",
            "speed_str": "",
            "size_str": "",
            "created_at": "",
            "error_msg": "",
        }

    # ═════════════════════════════════════════════════════════════════════
    # 📜 本地歷史發布紀錄管理 (不含敏感明文輸出至前端)
    # ═════════════════════════════════════════════════════════════════════

    def _load_raw_history(self) -> List[Dict[str, Any]]:
        if not self.history_path.exists():
            return []
        try:
            data = json.loads(self.history_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"[FriendCode] 讀取歷史紀錄失敗: {e}")
            return []

    def _save_raw_history(self, items: List[Dict[str, Any]]):
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            self.history_path.write_text(
                json.dumps(items[:30], ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"[FriendCode] 儲存歷史紀錄失敗: {e}")

    def get_public_history(self) -> List[Dict[str, Any]]:
        """回傳供前端渲染之安全歷史清單 (隱去內部 file_id 中之 Webhook 明文)"""
        with self._history_lock:
            raw = self._load_raw_history()
        safe_list = []
        for item in raw:
            safe_list.append({
                "id": item.get("id", ""),
                "app_id": item.get("app_id", ""),
                "game_name": item.get("game_name", ""),
                "code": item.get("code", ""),
                "size": item.get("size", 0),
                "is_multipart": bool(item.get("is_multipart", False)),
                "total_parts": int(item.get("total_parts", 1) or 1),
                "created_at": item.get("created_at", ""),
                "can_revoke": bool(item.get("file_id")),
            })
        return safe_list

    def revoke_history_item(self, item_id: str) -> Dict[str, Any]:
        """撤銷已發布之友邀代碼：自動刪除 Discord 頻道上對應之整合包附件訊息，並移除本地紀錄"""
        if not item_id:
            return {"ok": False, "msg": "未指定紀錄 ID"}

        target_item = None
        with self._history_lock:
            raw = self._load_raw_history()
            remaining = []
            for it in raw:
                if it.get("id") == item_id:
                    target_item = it
                else:
                    remaining.append(it)
            if not target_item:
                return {"ok": False, "msg": "找不到該筆歷史紀錄"}
            self._save_raw_history(remaining)

        deleted_cloud = False
        file_id = target_item.get("file_id", "")
        if file_id:
            try:
                deleted_cloud = get_discord_storage().delete_package(file_id)
            except Exception as e:
                logger.warning(f"[FriendCode] 刪除雲端訊息異常: {e}")

        msg = "✅ 已撤銷友邀代碼並同步刪除 Discord 雲端整合包！" if deleted_cloud else "✅ 已移除本地友邀代碼紀錄"
        return {"ok": True, "deleted_cloud": deleted_cloud, "msg": msg, "history": self.get_public_history()}

    # ═════════════════════════════════════════════════════════════════════
    # 📦 發起方：本地三檔打包 + Discord Webhook 上傳 + 生成 52 碼友邀代碼
    # ═════════════════════════════════════════════════════════════════════

    def get_host_progress(self) -> Dict[str, Any]:
        with self._host_lock:
            return dict(self._host_state)

    def _set_host_state(self, **kwargs):
        with self._host_lock:
            self._host_state.update(kwargs)

    def start_generate_friend_code(self, app_id: str, game_name: str = "", discord_webhook: str = "") -> Dict[str, Any]:
        """啟動非同步打包與上傳任務，完成後產出 52 碼中英混合加密友邀代碼"""
        app_id = str(app_id or "").strip()
        if not app_id:
            return {"ok": False, "msg": "請先選擇要打包分享的遊戲"}

        discord_mgr = get_discord_storage()
        webhook_target = (discord_webhook or "").strip() or discord_mgr.get_custom_webhook_url()
        if not webhook_target:
            return {"ok": False, "msg": "請先填寫 Discord Webhook 網址"}
        if not is_valid_webhook_url(webhook_target):
            return {"ok": False, "msg": "Discord Webhook 網址格式無效，請確認為 https://discord.com/api/webhooks/... 官方格式"}

        with self._host_lock:
            if self._host_task_running:
                return {"ok": False, "msg": "目前已有正在進行中的打包上傳任務，請稍候"}
            self._host_task_running = True
            self._host_state = {
                "state": "running",
                "progress": 5,
                "status_text": "正在檢查本地核心三檔完整性…",
                "error_msg": "",
                "result": None,
            }

        t = threading.Thread(
            target=self._run_host_package_task,
            args=(app_id, (game_name or "").strip(), webhook_target),
            daemon=True,
            name=f"FriendCodeHost_{app_id}"
        )
        t.start()
        return {"ok": True, "msg": "已啟動本地打包與加密生成任務"}

    def _run_host_package_task(self, app_id: str, game_name: str, webhook_target: str):
        packager = get_party_packager()
        discord_mgr = get_discord_storage()
        zip_path = ""
        try:
            # 1. 嚴格檢查三檔 (Manifest + Lua + 線上補丁)
            inspect = packager.inspect_party_resources(app_id)
            missing = []
            if not inspect.get("manifest", {}).get("ready"):
                missing.append("Manifest 清單檔案")
            if not inspect.get("lua", {}).get("ready"):
                missing.append("Lua 腳本")
            if not inspect.get("patch", {}).get("ready"):
                missing.append("線上聯機補丁")
            if missing or not inspect.get("all_ready"):
                err = f"本地三檔未齊全，缺少：{'、'.join(missing)}。請先完成入庫並安裝線上補丁後再打包！"
                self._set_host_state(state="error", progress=0, status_text="三檔檢查未通過", error_msg=err)
                return

            # 2. 本地封裝 ZIP
            self._set_host_state(progress=18, status_text=f"正在封裝《{game_name or app_id}》核心三檔整合包…")
            temp_tag = f"FC_{uuid.uuid4().hex[:6].upper()}"
            ok, zip_path, details = packager.build_party_package(app_id, temp_tag)
            if not ok or not zip_path:
                err = f"本地封裝整合包失敗: {details.get('error') if isinstance(details, dict) else details}"
                self._set_host_state(state="error", progress=0, status_text="封裝失敗", error_msg=err)
                return

            # 3. 上傳至 Discord Webhook (自動單檔或 8MB 多分卷 + 索引訊息)
            def _on_up_progress(txt: str, pct: int):
                self._set_host_state(progress=pct, status_text=txt)

            up_res = discord_mgr.upload_friend_code_package(
                file_path=zip_path,
                app_id=app_id,
                webhook_url=webhook_target,
                game_name=game_name or f"AppID {app_id}",
                progress_cb=_on_up_progress
            )
            if not up_res or not up_res.get("ok"):
                err = (up_res or {}).get("msg") or "上傳至 Discord Webhook 失敗"
                self._set_host_state(state="error", progress=0, status_text="上傳失敗", error_msg=err)
                return

            # 4. 加密生成 97 碼純英數友邀代碼 (結合 Webhook + 當下訊息時間戳)
            self._set_host_state(progress=96, status_text="正在結合當下時間戳執行 AEAD-SIV 對稱加密…")
            now_sec = int(time.time())
            entry_mid = int(up_res["entry_message_id"])
            is_mp = bool(up_res.get("is_multipart", False))
            code_str = friend_code_crypto.encrypt_friend_code(
                webhook_url=up_res["webhook_url"],
                entry_message_id=entry_mid,
                is_multipart=is_mp,
                timestamp_sec=now_sec
            )

            ts_ms = friend_code_crypto.snowflake_to_timestamp_ms(entry_mid)
            created_str = datetime.datetime.fromtimestamp(ts_ms / 1000.0).strftime("%Y-%m-%d %H:%M:%S")

            record_id = uuid.uuid4().hex[:10]
            raw_entry = {
                "id": record_id,
                "app_id": app_id,
                "game_name": game_name or f"AppID {app_id}",
                "code": code_str,
                "size": int(up_res.get("size", 0) or 0),
                "is_multipart": is_mp,
                "total_parts": int(up_res.get("total_parts", 1) or 1),
                "created_at": created_str,
                "file_id": up_res.get("file_id", ""),
            }
            with self._history_lock:
                hist = self._load_raw_history()
                hist.insert(0, raw_entry)
                self._save_raw_history(hist)

            public_result = {
                "id": record_id,
                "app_id": app_id,
                "game_name": raw_entry["game_name"],
                "code": code_str,
                "size": raw_entry["size"],
                "is_multipart": is_mp,
                "total_parts": raw_entry["total_parts"],
                "created_at": created_str,
                "can_revoke": True,
            }
            self._set_host_state(
                state="success",
                progress=100,
                status_text="✅ 友邀代碼已加密生成！可立即複製分享給好友",
                error_msg="",
                result=public_result,
            )
        except Exception as e:
            logger.error(f"[FriendCode] 打包生成友邀代碼異常: {e}", exc_info=True)
            self._set_host_state(state="error", progress=0, status_text="發生例外錯誤", error_msg=str(e))
        finally:
            if zip_path:
                try:
                    packager.cleanup_package_file(zip_path)
                except Exception:
                    pass
            with self._host_lock:
                self._host_task_running = False

    # ═════════════════════════════════════════════════════════════════════
    # 🔓 接收方：本地離線解密預覽 + 自動下載與五階段一鍵入庫安裝
    # ═════════════════════════════════════════════════════════════════════

    def preview_friend_code(self, raw_code: str, fetch_remote: bool = False) -> Dict[str, Any]:
        """
        本地離線解密校驗友邀代碼 (<0.5ms)。
        若 fetch_remote=True，同步向 Discord Webhook 讀取入口訊息以預覽遊戲名稱、AppID 與檔案大小。
        注意：絕不將解密後之 webhook_url 回傳給前端，確保分享者 Webhook 隱私安全！
        """
        dec = friend_code_crypto.decrypt_friend_code(raw_code)
        if not dec.get("ok"):
            return {"ok": False, "msg": dec.get("msg", "無效的友邀代碼")}

        res: Dict[str, Any] = {
            "ok": True,
            "code": dec["code"],
            "created_at": dec["created_at"],
            "timestamp_ms": dec["timestamp_ms"],
            "is_multipart": dec["is_multipart"],
            "msg": dec["msg"],
        }

        if fetch_remote:
            pkg_info = get_discord_storage().resolve_friend_code_package(
                webhook_url=dec["webhook_url"],
                entry_message_id=dec["entry_message_id"],
                fetch_part_urls=False
            )
            if not pkg_info.get("ok"):
                return {
                    "ok": False,
                    "local_valid": True,
                    "created_at": dec["created_at"],
                    "msg": pkg_info.get("msg", "無法讀取雲端整合包")
                }
            res.update({
                "remote_verified": True,
                "app_id": pkg_info.get("app_id", ""),
                "game_name": pkg_info.get("game_name", ""),
                "size": pkg_info.get("size", 0),
                "total_parts": pkg_info.get("total_parts", 1),
            })

        return res

    def get_install_progress(self) -> Dict[str, Any]:
        with self._recv_lock:
            return dict(self._recv_state)

    def _set_recv_state(self, **kwargs):
        with self._recv_lock:
            self._recv_state.update(kwargs)

    def cancel_redeem_install(self) -> Dict[str, Any]:
        with self._recv_lock:
            if not self._recv_running:
                return {"ok": True, "msg": "目前無進行中的安裝任務"}
            self._recv_task_id = ""
            self._recv_running = False
            self._recv_state.update({
                "state": "cancelled",
                "status_text": "已手動中止下載安裝任務",
                "speed_str": "",
            })
        return {"ok": True, "msg": "已中止友邀代碼安裝任務"}

    def start_redeem_install(self, raw_code: str) -> Dict[str, Any]:
        """貼上代碼後一鍵啟動：本地解密 ➔ 動態簽發直鏈 ➔ 下載合併 ➔ 部署三檔 ➔ Steam 安裝與補丁套用"""
        dec = friend_code_crypto.decrypt_friend_code(raw_code)
        if not dec.get("ok"):
            return {"ok": False, "msg": dec.get("msg", "友邀代碼解密失敗")}

        with self._recv_lock:
            if self._recv_running:
                return {"ok": False, "msg": "目前已有正在執行的友邀代碼安裝任務，請等待完成或先取消"}
            task_id = uuid.uuid4().hex
            self._recv_task_id = task_id
            self._recv_running = True
            self._recv_state = {
                "state": "running",
                "stage": 1,
                "progress": 3,
                "status_text": "本地解密成功，正在向雲端換發最新簽章下載直鏈…",
                "game_name": "解析中…",
                "app_id": "",
                "speed_str": "",
                "size_str": "",
                "created_at": dec.get("created_at", ""),
                "error_msg": "",
            }

        t = threading.Thread(
            target=self._run_redeem_install_task,
            args=(dec, task_id),
            daemon=True,
            name=f"FriendCodeInstall_{task_id[:6]}"
        )
        t.start()
        return {"ok": True, "msg": "已通過本地加密核驗，開始自動下載與安裝！"}

    def _is_cancelled(self, task_id: str) -> bool:
        with self._recv_lock:
            return self._recv_task_id != task_id

    @staticmethod
    def _fmt_bytes(num_bytes: float) -> str:
        if num_bytes <= 0:
            return "0 B"
        mb = num_bytes / (1024 * 1024)
        if mb >= 1.0:
            return f"{mb:.2f} MB"
        return f"{num_bytes / 1024:.1f} KB"

    def _extract_meta_from_zip(self, zip_path: Path) -> Dict[str, str]:
        """從下載完成的整合包 ZIP 內部讀取 package_meta.json 或檔名作為權威 AppID / 遊戲名稱來源"""
        info = {"app_id": "", "game_name": ""}
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                if "package_meta.json" in names:
                    meta = json.loads(zf.read("package_meta.json").decode("utf-8", errors="ignore"))
                    if meta.get("app_id"):
                        info["app_id"] = str(meta["app_id"]).strip()
                    if meta.get("game_name"):
                        info["game_name"] = str(meta["game_name"]).strip()
                if not info["app_id"]:
                    for n in names:
                        if n.startswith("lua/") and n.endswith(".lua"):
                            stem = Path(n).stem
                            if stem.isdigit():
                                info["app_id"] = stem
                                break
        except Exception as e:
            logger.warning(f"[FriendCode] 讀取 package_meta.json 異常: {e}")
        return info

    def _run_redeem_install_task(self, dec: Dict[str, Any], task_id: str):
        packager = get_party_packager()
        discord_mgr = get_discord_storage()
        dl_dir = packager.temp_pack_dir / "friend_downloads"
        dl_dir.mkdir(parents=True, exist_ok=True)
        target_zip = dl_dir / f"fc_{task_id[:8]}.zip"
        temp_parts: List[Path] = []

        try:
            # ── 階段 1：向 Discord Webhook 動態換發最新 CDN 直鏈 ──
            pkg = discord_mgr.resolve_friend_code_package(
                webhook_url=dec["webhook_url"],
                entry_message_id=dec["entry_message_id"],
                fetch_part_urls=True
            )
            if self._is_cancelled(task_id):
                return
            if not pkg.get("ok"):
                self._set_recv_state(
                    state="error",
                    progress=0,
                    status_text="無法取得雲端整合包",
                    error_msg=pkg.get("msg", "整合包不存在或已過期刪除")
                )
                return

            app_id = str(pkg.get("app_id", "")).strip()
            game_name = str(pkg.get("game_name", "")).strip() or (f"AppID {app_id}" if app_id else "好友分享遊戲")
            total_size = int(pkg.get("size", 0) or 0)
            urls: List[str] = pkg.get("download_urls") or []
            total_parts = len(urls)

            if not urls:
                self._set_recv_state(
                    state="error",
                    progress=0,
                    status_text="下載連結為空",
                    error_msg="雲端訊息未包含有效下載附件"
                )
                return

            self._set_recv_state(
                stage=2,
                progress=6,
                game_name=game_name,
                app_id=app_id,
                size_str=self._fmt_bytes(total_size) if total_size else "",
                status_text=f"正在下載《{game_name}》整合包 (共 {total_parts} 卷)…",
            )

            # ── 階段 2：高速串流下載 (支援單檔與多分卷自動重試 + 無損合併) ──
            dl_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Connection": "keep-alive",
            }

            bytes_done_before = 0
            last_pct = 6
            t_start = time.time()

            for idx, p_url in enumerate(urls, 1):
                if self._is_cancelled(task_id):
                    return
                dest_file = target_zip if total_parts == 1 else (dl_dir / f"fc_{task_id[:8]}_part{idx}.bin")
                if total_parts > 1:
                    temp_parts.append(dest_file)

                base_pct = 6 + int(((idx - 1) / total_parts) * 18)
                span_pct = max(1, int(18 / total_parts))

                part_ok = False
                last_err = ""
                for attempt in range(1, 4):
                    if self._is_cancelled(task_id):
                        return
                    try:
                        with requests.get(p_url, headers=dl_headers, stream=True, timeout=(10, 45)) as resp:
                            if resp.status_code == 200:
                                p_len = int(resp.headers.get("content-length") or 0)
                                est_len = p_len if p_len > 0 else (8 * 1024 * 1024)
                                p_dl = 0
                                last_ui_ts = 0.0
                                with open(dest_file, "wb") as f:
                                    for chunk in resp.iter_content(chunk_size=262144):
                                        if self._is_cancelled(task_id):
                                            return
                                        if chunk:
                                            f.write(chunk)
                                            p_dl += len(chunk)
                                            now_t = time.time()
                                            if now_t - last_ui_ts >= 0.15:
                                                last_ui_ts = now_t
                                                ratio = min(1.0, p_dl / max(1, est_len))
                                                cur_pct = min(24, max(last_pct, base_pct + int(ratio * span_pct)))
                                                last_pct = cur_pct
                                                elapsed = max(0.1, now_t - t_start)
                                                spd = (bytes_done_before + p_dl) / elapsed
                                                spd_txt = f"{spd / 1024 / 1024:.2f} MB/s" if spd >= 1048576 else f"{spd / 1024:.0f} KB/s"
                                                label = (
                                                    f"下載分卷 ({idx}/{total_parts})：{self._fmt_bytes(bytes_done_before + p_dl)}"
                                                    if total_parts > 1
                                                    else f"下載整合包：{self._fmt_bytes(p_dl)}"
                                                )
                                                self._set_recv_state(
                                                    progress=cur_pct,
                                                    status_text=label,
                                                    speed_str=spd_txt,
                                                )
                                if dest_file.exists() and dest_file.stat().st_size > 0 and (p_len == 0 or dest_file.stat().st_size >= p_len):
                                    bytes_done_before += dest_file.stat().st_size
                                    part_ok = True
                                    break
                                last_err = f"檔案下載不完整 ({dest_file.stat().st_size if dest_file.exists() else 0}/{p_len})"
                            else:
                                last_err = f"HTTP {resp.status_code}"
                    except Exception as de:
                        last_err = str(de)
                    time.sleep(0.8 * attempt)

                if not part_ok:
                    self._set_recv_state(
                        state="error",
                        progress=0,
                        speed_str="",
                        status_text="下載整合包失敗",
                        error_msg=f"分卷 {idx}/{total_parts} 下載失敗 ({last_err})"
                    )
                    return

            # 多分卷二進位無損合併
            if total_parts > 1:
                self._set_recv_state(progress=25, speed_str="", status_text=f"正在無損合併 {total_parts} 個分卷檔案…")
                with open(target_zip, "wb") as out_f:
                    for pf in temp_parts:
                        with open(pf, "rb") as in_f:
                            shutil.copyfileobj(in_f, out_f, length=1024 * 1024)
                for pf in temp_parts:
                    try:
                        pf.unlink(missing_ok=True)
                    except Exception:
                        pass
                temp_parts.clear()

            if not zipfile.is_zipfile(target_zip):
                self._set_recv_state(
                    state="error",
                    progress=0,
                    speed_str="",
                    status_text="整合包校驗失敗",
                    error_msg="下載後的整合包並非有效 ZIP 格式，請請好友重新打包發布"
                )
                return

            # 補齊 ZIP 內權威 AppID 與遊戲名稱
            z_meta = self._extract_meta_from_zip(target_zip)
            if not app_id and z_meta.get("app_id"):
                app_id = z_meta["app_id"]
            if (not game_name or game_name.startswith("AppID ")) and z_meta.get("game_name"):
                game_name = z_meta["game_name"]

            if not app_id:
                self._set_recv_state(
                    state="error",
                    progress=0,
                    status_text="缺少遊戲 AppID",
                    error_msg="無法由整合包識別目標遊戲 AppID"
                )
                return

            # 嘗試從本地遊戲快取美化中文名稱
            try:
                gc_file = self.root_dir / "data" / "game_cache.json"
                if gc_file.exists() and (not game_name or game_name == f"AppID {app_id}"):
                    gc = json.loads(gc_file.read_text(encoding="utf-8"))
                    g_entry = gc.get(app_id)
                    if isinstance(g_entry, dict) and g_entry.get("name"):
                        game_name = g_entry["name"]
            except Exception:
                pass

            self._set_recv_state(app_id=app_id, game_name=game_name, speed_str="")

            # ── 階段 3：部署實體 Manifest 清單與 Lua 授權腳本 ──
            if self._is_cancelled(task_id):
                return
            self._set_recv_state(stage=3, progress=28, status_text=f"正在部署《{game_name}》Manifest 清單與 Lua 腳本…")
            init_res = packager.extract_and_apply_package(str(target_zip), app_id)
            if not init_res.get("ok"):
                self._set_recv_state(
                    state="error",
                    progress=0,
                    status_text="部署清單與腳本失敗",
                    error_msg=init_res.get("msg", "Manifest/Lua 部署失敗")
                )
                return

            self._set_recv_state(progress=31, status_text="清單與 Lua 授權腳本已就緒，正在檢查 Steam 遊戲狀態…")

            # ── 階段 4：檢查或喚起 Steam 原生下載遊戲主程式 ──
            try:
                from web_api import WebApi
            except ImportError:
                from src.web_api import WebApi
            api_inst = WebApi()
            st_info = api_inst.check_game_installed_status(app_id)
            is_installed = bool(st_info.get("is_installed", False))

            if not is_installed:
                self._set_recv_state(stage=4, progress=33, status_text="正在喚起 Steam 客戶端開始下載遊戲主程式…")
                sp = steam_manager.find_steam_path()
                if sp:
                    try:
                        steam_manager.unlock_game_version(app_id, sp)
                        acf = steam_manager.find_appmanifest(app_id, sp)
                        if acf and acf.exists():
                            c = acf.read_text(encoding="utf-8", errors="ignore")
                            if '"StateFlags"\t\t"4"' not in c and '"StateFlags" "4"' not in c:
                                acf.unlink(missing_ok=True)
                            elif re.search(r'"UpdateResult"\s+"[^0"]+"', c):
                                c = re.sub(r'"UpdateResult"\s+"[^"]*"', '"UpdateResult"\t\t"0"', c)
                                acf.write_text(c, encoding="utf-8")
                    except Exception as ue:
                        logger.warning(f"[FriendCode] 喚起 Steam 前清理殘留 ACF 異常: {ue}")

                # 緩衝 2.5 秒供 OpenSteamTools 熱載入新寫入之 Lua 腳本
                time.sleep(2.5)
                if self._is_cancelled(task_id):
                    return

                try:
                    os.startfile(f"steam://install/{app_id}")
                except Exception:
                    import webbrowser
                    webbrowser.open(f"steam://install/{app_id}")

                self._set_recv_state(
                    stage=4,
                    progress=35,
                    status_text="請在彈出的 Steam 視窗點擊「安裝」，系統將自動監控下載並套用補丁…"
                )

                poll_count = 0
                cancelled_strikes = 0
                launch_ts = time.time()

                while poll_count < 7200:
                    if self._is_cancelled(task_id):
                        return
                    time.sleep(2.5)
                    poll_count += 1

                    rep = onlinefix_manager.get_steam_app_download_report(app_id)
                    st = rep.get("status")
                    pct_steam = float(rep.get("progress_pct", 0) or 0)
                    spd = rep.get("speed_str") or ""

                    chk = api_inst.check_game_installed_status(app_id)
                    if chk.get("is_installed") or st == "COMPLETED":
                        self._set_recv_state(
                            stage=4,
                            progress=91,
                            speed_str="",
                            status_text="Steam 遊戲主程式下載安裝完成！準備套用線上聯機補丁…"
                        )
                        break
                    elif st in ("DOWNLOADING", "PAUSED") or chk.get("is_downloading") or pct_steam > 0:
                        cancelled_strikes = 0
                        mapped = min(90, max(35, 35 + int(pct_steam * 0.55)))
                        label = f"Steam 正在下載遊戲主程式：{pct_steam:.1f}%"
                        if st == "PAUSED":
                            label = f"Steam 下載已暫停 ({pct_steam:.1f}%)，請於 Steam 繼續下載"
                        self._set_recv_state(stage=4, progress=mapped, speed_str=spd, status_text=label)
                    elif st == "ERROR":
                        err_m = rep.get("error_msg") or "Steam 回報下載發生錯誤"
                        self._set_recv_state(
                            state="error",
                            speed_str="",
                            status_text="Steam 下載中斷",
                            error_msg=err_m
                        )
                        return
                    elif st == "CANCELLED":
                        if time.time() - launch_ts < 60.0:
                            cancelled_strikes = 0
                            self._set_recv_state(
                                stage=4,
                                progress=35,
                                status_text="等待在 Steam 視窗確認「安裝 / 下載」…"
                            )
                        else:
                            cancelled_strikes += 1
                            if cancelled_strikes >= 6:
                                self._set_recv_state(
                                    state="error",
                                    speed_str="",
                                    status_text="Steam 下載已取消",
                                    error_msg="未偵測到 Steam 開始下載，請在 Steam 點擊安裝或確認磁碟空間後重新執行"
                                )
                                return

            # ── 階段 5：套用整合包內之線上聯機補丁 ──
            if self._is_cancelled(task_id):
                return
            self._set_recv_state(stage=5, progress=95, speed_str="", status_text="正在將線上聯機補丁部署至遊戲目錄…")

            # 等待 Steam 完成從 downloading 搬移至 common 目錄 (最多輪詢 6 秒)
            for _ in range(6):
                gdir = onlinefix_manager._find_steam_game_dir(app_id)
                if gdir and Path(gdir).exists():
                    break
                time.sleep(1.0)

            patch_res = packager.apply_patch_files(str(target_zip), app_id)
            if patch_res.get("ok"):
                self._set_recv_state(
                    state="success",
                    stage=5,
                    progress=100,
                    speed_str="",
                    status_text=f"🎉《{game_name}》入庫、下載與聯機補丁已全自動安裝完成！現在即可啟動遊戲連線！",
                    error_msg=""
                )
            else:
                err_detail = patch_res.get("msg") or "線上聯機補丁套用失敗"
                self._set_recv_state(
                    state="error",
                    stage=5,
                    progress=92,
                    speed_str="",
                    status_text="遊戲已安裝，但聯機補丁套用失敗",
                    error_msg=err_detail
                )
        except Exception as e:
            logger.error(f"[FriendCode] 解密與自動安裝流程異常: {e}", exc_info=True)
            self._set_recv_state(
                state="error",
                speed_str="",
                status_text="安裝過程發生例外錯誤",
                error_msg=str(e)
            )
        finally:
            for pf in temp_parts:
                try:
                    pf.unlink(missing_ok=True)
                except Exception:
                    pass
            try:
                if target_zip.exists():
                    packager.cleanup_package_file(str(target_zip))
            except Exception:
                pass
            with self._recv_lock:
                if self._recv_task_id == task_id:
                    self._recv_running = False


def get_friend_code_manager() -> FriendCodeManager:
    return FriendCodeManager()

