# -*- coding: utf-8 -*-
"""
GASManager - Google Apps Script 雲端傳輸與生命週期銷毀管理器
負責透過房主自持之 GAS Web App 進行 0 成本、免伺服器之 Google Drive 檔案上傳與自動銷毀。
"""

import os
import json
import base64
import logging
import requests
from typing import Dict, Any, Optional
from pathlib import Path
from managers import config_manager

logger = logging.getLogger("gas_manager")

GAS_SAMPLE_CODE = """// 🌸 SMU (SteamManifestUpdater) - Google Drive 專屬邊緣上傳與銷毀腳本
function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var action = data.action;
    
    // 1. 上傳檔案 (預設自動清理歷史舊包，避免房主未正常關閉房間累積舊檔)
    if (action === "upload") {
      var folderName = "SMU_Party_Packages";
      var folders = DriveApp.getFoldersByName(folderName);
      var folder = folders.hasNext() ? folders.next() : DriveApp.createFolder(folderName);
      
      // 🌟 自動清除舊檔案防呆機制：
      // 若房主上次未正常解散房間，上傳前先把該資料夾內的歷史舊包移至垃圾桶，確保不佔用雲端空間！
      if (data.clean_before_upload !== false) {
        var oldFiles = folder.getFiles();
        while (oldFiles.hasNext()) {
          try {
            oldFiles.next().setTrashed(true);
          } catch(e) {}
        }
      }
      
      var decoded = Utilities.base64Decode(data.base64_data);
      var blob = Utilities.newBlob(decoded, data.mime_type || "application/zip", data.filename || "party_package.zip");
      var file = folder.createFile(blob);
      
      // 設定為知道連結即可下載檢視
      file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
      
      var fileId = file.getId();
      var downloadUrl = "https://drive.google.com/uc?export=download&id=" + fileId;
      
      return ContentService.createTextOutput(JSON.stringify({
        ok: true,
        file_id: fileId,
        download_url: downloadUrl,
        filename: file.getName(),
        size: file.getSize()
      })).setMimeType(ContentService.MimeType.JSON);
    }
    
    // 2. 房間解散時銷毀檔案
    if (action === "delete") {
      var fileId = data.file_id;
      if (fileId) {
        try {
          var file = DriveApp.getFileById(fileId);
          file.setTrashed(true);
          return ContentService.createTextOutput(JSON.stringify({
            ok: true,
            msg: "檔案已移至垃圾桶 (已銷毀)"
          })).setMimeType(ContentService.MimeType.JSON);
        } catch(err) {
          return ContentService.createTextOutput(JSON.stringify({
            ok: true,
            msg: "檔案可能已不存在: " + err.toString()
          })).setMimeType(ContentService.MimeType.JSON);
        }
      }
    }
    
    // 3. 清空專屬資料夾內的所有歷史整合包
    if (action === "clean_all" || action === "cleanup") {
      var folderName = "SMU_Party_Packages";
      var folders = DriveApp.getFoldersByName(folderName);
      var count = 0;
      if (folders.hasNext()) {
        var fldr = folders.next();
        var fls = fldr.getFiles();
        while (fls.hasNext()) {
          try {
            fls.next().setTrashed(true);
            count++;
          } catch(e) {}
        }
      }
      return ContentService.createTextOutput(JSON.stringify({
        ok: true,
        msg: "已將 " + count + " 個歷史檔案移至垃圾桶 (空間已釋放)"
      })).setMimeType(ContentService.MimeType.JSON);
    }

    // 4. 連線測試
    if (action === "ping") {
      return ContentService.createTextOutput(JSON.stringify({
        ok: true,
        msg: "SMU GAS 服務正常連線",
        time: new Date().toISOString()
      })).setMimeType(ContentService.MimeType.JSON);
    }
    
    return ContentService.createTextOutput(JSON.stringify({ ok: false, error: "未知操作指令" })).setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ ok: false, error: err.toString() })).setMimeType(ContentService.MimeType.JSON);
  }
}
"""

class GASManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(GASManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "SMU-Client/2.0 (GAS Uploader; Windows NT 10.0)"
        })

    def get_gas_url(self) -> str:
        """取得本地保存的 GAS Web App 網址"""
        cfg = config_manager.get_config()
        return str(cfg.get("gas_web_app_url", "")).strip()

    def set_gas_url(self, url: str) -> bool:
        """保存房主的 GAS Web App 網址"""
        clean_url = str(url or "").strip()
        cfg = config_manager.get_config()
        cfg["gas_web_app_url"] = clean_url
        return config_manager.save_config(cfg)

    def get_sample_script(self) -> str:
        """取得 GAS 範本腳本代碼供前端一鍵複製"""
        return GAS_SAMPLE_CODE

    def test_gas_connection(self, url: Optional[str] = None) -> Dict[str, Any]:
        """測試指定或已保存之 GAS Web App 是否暢通可用"""
        target_url = (url or self.get_gas_url()).strip()
        if not target_url:
            return {"ok": False, "msg": "未設定 GAS Web App 網址"}

        try:
            resp = self.session.post(
                target_url,
                json={"action": "ping"},
                timeout=12,
                allow_redirects=True
            )
            if resp.status_code == 200:
                try:
                    res_json = resp.json()
                    if res_json.get("ok"):
                        return {"ok": True, "msg": "✅ GAS 雲端連線測試成功！服務正常運作", "data": res_json}
                    else:
                        return {"ok": False, "msg": f"GAS 回報錯誤: {res_json.get('error')}"}
                except Exception:
                    return {"ok": False, "msg": f"GAS 回傳非 JSON 格式 (HTTP {resp.status_code})"}
            else:
                return {"ok": False, "msg": f"GAS 回應異常 (HTTP {resp.status_code})"}
        except requests.exceptions.Timeout:
            return {"ok": False, "msg": "連線逾時，請確認 Google Apps Script 部署權限設定為「所有人 (Anyone)」"}
        except Exception as e:
            return {"ok": False, "msg": f"連線至 GAS 失敗: {e}"}

    def upload_archive(self, file_path: str, custom_filename: str = "", gas_url: Optional[str] = None) -> Dict[str, Any]:
        """
        將本地打包之 zip 檔案編碼為 Base64 並透過 GAS 上傳至 Google Drive
        """
        target_url = (gas_url or self.get_gas_url()).strip()
        if not target_url:
            return {"ok": False, "msg": "未配置房主專屬 GAS 網址"}

        p = Path(file_path)
        if not p.exists():
            return {"ok": False, "msg": f"打包檔案不存在: {file_path}"}

        file_size = p.stat().st_size
        filename = custom_filename or p.name

        try:
            logger.info(f"[GAS] 讀取檔案中 ({file_size} 位元組): {p.name}")
            with open(p, "rb") as f:
                b64_content = base64.b64encode(f.read()).decode("utf-8")

            payload = {
                "action": "upload",
                "filename": filename,
                "mime_type": "application/zip",
                "base64_data": b64_content,
                "clean_before_upload": True
            }

            logger.info(f"[GAS] 正在發送 Base64 數據至 Google Apps Script...")
            resp = self.session.post(
                target_url,
                json=payload,
                timeout=60,
                allow_redirects=True
            )

            if resp.status_code == 200:
                res_json = resp.json()
                if res_json.get("ok") and res_json.get("download_url"):
                    logger.info(f"[GAS] 上傳成功！Google Drive 下載網址: {res_json.get('download_url')}")
                    return {
                        "ok": True,
                        "file_id": res_json.get("file_id"),
                        "download_url": res_json.get("download_url"),
                        "filename": res_json.get("filename", filename),
                        "size": res_json.get("size", file_size),
                        "msg": "✅ 整合包已成功上傳至 Google Drive"
                    }
                else:
                    return {"ok": False, "msg": f"GAS 回報上傳失敗: {res_json.get('error')}"}
            else:
                return {"ok": False, "msg": f"GAS 伺服器回應異常: HTTP {resp.status_code}"}
        except Exception as e:
            logger.error(f"[GAS] 上傳異常: {e}", exc_info=True)
            return {"ok": False, "msg": f"上傳至 Google Drive 失敗: {e}"}

    def delete_remote_file(self, file_id: str, gas_url: Optional[str] = None) -> Dict[str, Any]:
        """
        房間解散時調用 GAS 將遠端檔案自動銷毀 (移入垃圾桶)
        """
        if not file_id:
            return {"ok": True, "msg": "無遠端檔案 ID，略過銷毀"}

        target_url = (gas_url or self.get_gas_url()).strip()
        if not target_url:
            return {"ok": False, "msg": "未配置 GAS 網址"}

        try:
            logger.info(f"[GAS] 正在銷毀遠端 Google Drive 檔案 (ID: {file_id})...")
            resp = self.session.post(
                target_url,
                json={"action": "delete", "file_id": file_id},
                timeout=15,
                allow_redirects=True
            )
            if resp.status_code == 200:
                res_json = resp.json()
                logger.info(f"[GAS] 遠端檔案銷毀結果: {res_json}")
                return {"ok": True, "msg": res_json.get("msg", "遠端檔案已銷毀")}
            else:
                return {"ok": False, "msg": f"銷毀請求失敗 HTTP {resp.status_code}"}
        except Exception as e:
            logger.warning(f"[GAS] 銷毀檔案異常: {e}")
            return {"ok": False, "msg": str(e)}

    def clean_space(self, gas_url: Optional[str] = None) -> Dict[str, Any]:
        """
        主動清除房主 Google Drive 上 SMU_Party_Packages 專屬資料夾內的所有歷史遺留檔案
        """
        target_url = (gas_url or self.get_gas_url()).strip()
        if not target_url:
            return {"ok": False, "msg": "未配置 GAS 網址"}

        try:
            logger.info("[GAS] 正在發送清空歷史整合包指令至 Google Apps Script...")
            resp = self.session.post(
                target_url,
                json={"action": "clean_all"},
                timeout=20,
                allow_redirects=True
            )
            if resp.status_code == 200:
                res_json = resp.json()
                logger.info(f"[GAS] 清理空間結果: {res_json}")
                return {"ok": True, "msg": res_json.get("msg", "歷史空間已成功清理")}
            else:
                return {"ok": False, "msg": f"清理請求異常 HTTP {resp.status_code}"}
        except Exception as e:
            logger.warning(f"[GAS] 清理空間失敗: {e}")
            return {"ok": False, "msg": str(e)}

def get_gas_manager() -> GASManager:
    return GASManager()
