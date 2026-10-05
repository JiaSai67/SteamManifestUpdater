# -*- coding: utf-8 -*-
"""
FastCloudStorage - SMU 免登入極速雲端傳輸引擎
支援免登入、免 Google 帳號、0 步驟全自動聯機整合包上傳與下載。
- 主力通道：專屬 Supabase Storage (Tokyo AWS, 超低延遲高速頻寬)
- 備援通道：tmpfiles.org 匿名免空 (自動降級容災)
- 自動生命週期：房間解散時自動調用 API 銷毀遠端整合包，無痕環保
"""

import os
import json
import logging
import requests
from pathlib import Path
from typing import Dict, Any, Optional

from managers import config_manager

logger = logging.getLogger("fast_cloud_storage")

class FastCloudStorage:
    def __init__(self):
        self.root_dir = config_manager._root_dir
        self.secrets_path = self.root_dir / "data" / "secrets" / "supabase.json"
        self._supabase_cfg = self._load_supabase_config()

    def _load_supabase_config(self) -> Dict[str, Any]:
        """讀取 Supabase 配置檔"""
        if self.secrets_path.exists():
            try:
                with open(self.secrets_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"讀取 supabase.json 失敗: {e}")
        return {}

    def upload_package(self, file_path: str, room_code: str) -> Dict[str, Any]:
        """
        全自動免登入上傳聯機整合包
        :param file_path: 本地 ZIP 整合包路徑
        :param room_code: 房間代碼 (如 PKG_A1B2C3 或 6 碼房號)
        :return: {"ok": bool, "download_url": str, "file_id": str, "provider": str, "msg": str}
        """
        p = Path(file_path)
        if not p.exists() or not p.is_file():
            return {"ok": False, "msg": f"本地待上傳檔案不存在: {file_path}"}

        file_size = p.stat().st_size
        filename = f"SMU_Party_{room_code}.zip"

        # 優先嘗試主力通道：專屬 Supabase Storage
        supa_res = self._upload_to_supabase(p, filename)
        if supa_res.get("ok"):
            supa_res["size"] = file_size
            supa_res["filename"] = filename
            return supa_res

        logger.warning(f"Supabase Storage 上傳未成功 ({supa_res.get('msg')})，正在無縫切換至備援匿名通道...")

        # 備援通道：tmpfiles.org 匿名免空
        backup_res = self._upload_to_tmpfiles(p, filename)
        if backup_res.get("ok"):
            backup_res["size"] = file_size
            backup_res["filename"] = filename
            return backup_res

        return {
            "ok": False,
            "msg": f"極速雲端上傳失敗：主力與備援通道均無法連線 ({supa_res.get('msg')}; {backup_res.get('msg')})"
        }

    def _upload_to_supabase(self, path: Path, remote_filename: str) -> Dict[str, Any]:
        """上傳至專屬 Supabase Storage"""
        project_url = self._supabase_cfg.get("project_url")
        anon_key = self._supabase_cfg.get("publishable_key")

        if not project_url or not anon_key:
            return {"ok": False, "msg": "未檢測到 Supabase Storage 配置"}

        upload_url = f"{project_url}/storage/v1/object/party-packages/{remote_filename}"
        public_url = f"{project_url}/storage/v1/object/public/party-packages/{remote_filename}"

        headers = {
            "apikey": anon_key,
            "Authorization": f"Bearer {anon_key}",
            "Content-Type": "application/zip",
            "x-upsert": "true"
        }

        try:
            with open(path, "rb") as f:
                resp = requests.post(upload_url, headers=headers, data=f, timeout=35)

            if resp.status_code in (200, 201):
                logger.info(f"整合包已成功免登入上傳至 Supabase Storage: {public_url}")
                return {
                    "ok": True,
                    "download_url": public_url,
                    "file_id": f"supabase:{remote_filename}",
                    "provider": "Supabase Storage (Tokyo AWS)",
                    "msg": "✅ 已成功上傳至 SMU 免登入極速雲端！"
                }
            else:
                return {"ok": False, "msg": f"Supabase 回應 HTTP {resp.status_code}: {resp.text[:120]}"}
        except Exception as e:
            return {"ok": False, "msg": f"Supabase 連線異常: {e}"}

    def _upload_to_tmpfiles(self, path: Path, remote_filename: str) -> Dict[str, Any]:
        """備援上傳至 tmpfiles.org 匿名免空"""
        try:
            url = "https://tmpfiles.org/api/v1/upload"
            with open(path, "rb") as f:
                files = {"file": (remote_filename, f, "application/zip")}
                resp = requests.post(url, files=files, timeout=40)

            if resp.status_code == 200:
                data = resp.json()
                orig_url = data.get("data", {}).get("url", "")
                if orig_url:
                    # 轉為直鏈下載 (tmpfiles.org/dl/...)
                    direct_url = orig_url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
                    logger.info(f"整合包已上傳至備援通道 tmpfiles: {direct_url}")
                    return {
                        "ok": True,
                        "download_url": direct_url,
                        "file_id": f"tmpfiles:{remote_filename}",
                        "provider": "Tmpfiles Cloud (備援通道)",
                        "msg": "✅ 已成功上傳至備援極速雲端！"
                    }
            return {"ok": False, "msg": f"tmpfiles 回應 HTTP {resp.status_code}"}
        except Exception as e:
            return {"ok": False, "msg": f"tmpfiles 連線異常: {e}"}

    def delete_package(self, file_id: str) -> bool:
        """
        房間解散時自動銷毀雲端暫存檔
        :param file_id: 檔案標識 (如 supabase:SMU_Party_ABC123.zip)
        """
        if not file_id:
            return True

        if file_id.startswith("supabase:"):
            remote_filename = file_id.split("supabase:", 1)[1]
            project_url = self._supabase_cfg.get("project_url")
            anon_key = self._supabase_cfg.get("publishable_key")
            if not project_url or not anon_key:
                return False

            del_url = f"{project_url}/storage/v1/object/party-packages/{remote_filename}"
            headers = {
                "apikey": anon_key,
                "Authorization": f"Bearer {anon_key}"
            }
            try:
                r = requests.delete(del_url, headers=headers, timeout=10)
                logger.info(f"已銷毀 Supabase Storage 檔案: {remote_filename} (HTTP {r.status_code})")
                return r.status_code in (200, 204)
            except Exception as e:
                logger.warning(f"銷毀 Supabase Storage 檔案失敗: {e}")
                return False

        # tmpfiles 免空本身具有過期自動銷毀機制 (無需手動呼叫)
        return True

_fast_storage_inst = None

def get_fast_cloud_storage() -> FastCloudStorage:
    global _fast_storage_inst
    if _fast_storage_inst is None:
        _fast_storage_inst = FastCloudStorage()
    return _fast_storage_inst
