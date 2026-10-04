# -*- coding: utf-8 -*-
"""
Manifest Update Diagnostic Logger
專門為 Manifest 更新與多源下載設計之全鏈路結構化診斷日誌模組。
記錄完整的網路請求、狀態碼、回應內容特徵、檔案落盤與異常呼叫棧，
支援實體日誌持久化儲存與前端即時視覺化呈現。
"""

import os
import sys
import json
import time
import traceback
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

_root_dir = Path(__file__).resolve().parent.parent.parent
_logs_dir = _root_dir / "logs" / "manifest_updates"
_logs_dir.mkdir(parents=True, exist_ok=True)

_latest_log_path = _logs_dir / "latest_update.log"
_latest_log_cache: Optional[Dict[str, Any]] = None


def _safe_print(text: str):
    """安全控制台輸出，徹底免疫 Windows cp950 的 Emoji 與特殊字元編碼異常"""
    try:
        if sys.platform == "win32" and hasattr(sys.stdout, "buffer") and sys.stdout.buffer:
            sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
            sys.stdout.buffer.flush()
            return
        print(text)
    except Exception:
        try:
            enc = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
            print(text.encode(enc, errors="replace").decode(enc, errors="replace"))
        except Exception:
            pass


class ManifestUpdateLogger:
    """單次 Manifest 更新診斷日誌收集器"""
    def __init__(self, appid: str, game_name: str = ""):
        self.appid = str(appid).strip()
        self.game_name = game_name or f"App_{self.appid}"
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
        self.steps: List[Dict[str, Any]] = []
        self.network_logs: List[Dict[str, Any]] = []
        self.file_operations: List[Dict[str, Any]] = []
        self.errors: List[Dict[str, Any]] = []
        self.success: bool = False
        self.summary: str = ""
        self.timestamp_str = self.start_time.strftime("%Y%m%d_%H%M%S")
        self.log_filename = f"manifest_update_{self.appid}_{self.timestamp_str}.log"
        self.log_path = _logs_dir / self.log_filename

    def log_step(self, stage: str, message: str, status: str = "INFO", details: Any = None):
        """記錄執行步驟"""
        entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "stage": stage,
            "message": message,
            "status": status, # INFO, OK, WARN, ERROR
            "details": details
        }
        self.steps.append(entry)
        _safe_print(f"[ManifestLogger][AppID:{self.appid}][{stage}][{status}] {message}")

    def log_network_request(self, source: str, url: str, method: str = "GET", headers: dict = None):
        """記錄發起的網路請求 (遮蔽敏感 Cookie 資訊)"""
        safe_headers = {}
        if headers:
            for k, v in headers.items():
                if k.lower() == "cookie":
                    # 僅保留 session 前 12 碼供辨識，遮蔽其餘字元
                    cookies_str = str(v)
                    safe_parts = []
                    for part in cookies_str.split(";"):
                        p = part.strip()
                        if "=" in p:
                            ck, cv = p.split("=", 1)
                            if len(cv) > 12:
                                safe_parts.append(f"{ck}={cv[:8]}...{cv[-4:]}")
                            else:
                                safe_parts.append(f"{ck}=***")
                        else:
                            safe_parts.append(p)
                    safe_headers[k] = "; ".join(safe_parts)
                else:
                    safe_headers[k] = v

        entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "type": "REQUEST",
            "source": source,
            "method": method,
            "url": url,
            "headers": safe_headers
        }
        self.network_logs.append(entry)

    def log_network_response(
        self,
        source: str,
        status_code: int,
        headers: dict = None,
        body_sample: bytes = None,
        byte_length: int = 0,
        content_type: str = ""
    ):
        """記錄伺服器回傳結果、資料類型與特徵頭"""
        is_zip = False
        sample_repr = ""

        if body_sample:
            if len(body_sample) >= 4 and body_sample[:4] == b"PK\x03\x04":
                is_zip = True
                sample_repr = "[PK ZIP 二進位壓縮包標準標頭]"
            else:
                try:
                    sample_repr = body_sample[:500].decode("utf-8", errors="replace")
                except Exception:
                    sample_repr = repr(body_sample[:100])

        entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "type": "RESPONSE",
            "source": source,
            "status_code": status_code,
            "headers": dict(headers) if headers else {},
            "content_type": content_type,
            "byte_length": byte_length,
            "is_zip": is_zip,
            "body_sample": sample_repr
        }
        self.network_logs.append(entry)

    def log_file_op(self, action: str, path: str, size: int = 0, success: bool = True, details: str = ""):
        """記錄檔案寫入/複製/解壓操作"""
        entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "action": action,
            "path": str(path),
            "size": size,
            "success": success,
            "details": details
        }
        self.file_operations.append(entry)

    def log_error(self, stage: str, error_msg: str, exc: Optional[Exception] = None):
        """記錄錯誤與呼叫棧"""
        tb_str = traceback.format_exc() if exc else ""
        entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "stage": stage,
            "error_msg": str(error_msg),
            "traceback": tb_str
        }
        self.errors.append(entry)
        self.log_step(stage, f"發生錯誤: {error_msg}", status="ERROR")

    def finish(self, success: bool, summary: str = "") -> Dict[str, Any]:
        """結算日誌並持久化儲存為 Markdown 格式與純文字日誌"""
        self.end_time = datetime.now()
        self.success = success
        self.summary = summary or ("更新成功" if success else "更新未完成")
        duration_ms = int((self.end_time - self.start_time).total_seconds() * 1000)

        # 生成精美 Markdown 診斷報告
        md_lines = []
        status_tag = "✅ 更新成功" if self.success else "❌ 更新失敗"
        md_lines.append(f"# 【Manifest 更新診斷報告】{self.game_name} ({self.appid})")
        md_lines.append(f"- **診斷狀態**: {status_tag}")
        md_lines.append(f"- **目標遊戲**: {self.game_name} (AppID: `{self.appid}`)")
        md_lines.append(f"- **執行時間**: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')} (耗時 {duration_ms} ms)")
        md_lines.append(f"- **最終結果**: {self.summary}")
        md_lines.append("")

        # 1. 執行步驟軌跡
        md_lines.append("## 一、全鏈路執行軌跡 (Execution Steps)")
        md_lines.append("| 時間 | 階段 | 狀態 | 描述說明 |")
        md_lines.append("| :--- | :--- | :--- | :--- |")
        for s in self.steps:
            stat_icon = "🟢" if s["status"] == "OK" else ("🔴" if s["status"] == "ERROR" else ("🟡" if s["status"] == "WARN" else "⚪"))
            md_lines.append(f"| `{s['timestamp']}` | **{s['stage']}** | {stat_icon} {s['status']} | {s['message']} |")
        md_lines.append("")

        # 2. 網路通訊詳情 (含請求與伺服器回應)
        md_lines.append("## 二、網路請求與伺服器回應詳情 (Network Trace)")
        if not self.network_logs:
            md_lines.append("> ⚠️ 無發起任何外部網路通訊 (可能已命中本地完全一致快取)")
        else:
            for i, net in enumerate(self.network_logs):
                if net["type"] == "REQUEST":
                    md_lines.append(f"### 請求 #{i+1} [{net['source']}] {net['method']} `{net['url']}`")
                    if net["headers"]:
                        md_lines.append("```yaml")
                        for hk, hv in net["headers"].items():
                            md_lines.append(f"{hk}: {hv}")
                        md_lines.append("```")
                elif net["type"] == "RESPONSE":
                    code_color = "🟢" if 200 <= net["status_code"] < 300 else "🔴"
                    md_lines.append(f"**回應 #{i+1}**: {code_color} HTTP `{net['status_code']}` | 接收大小: `{net['byte_length']} bytes` | 是否為 ZIP: `{net['is_zip']}`")
                    if net["body_sample"]:
                        md_lines.append("```text")
                        md_lines.append(net["body_sample"])
                        md_lines.append("```")
        md_lines.append("")

        # 3. 檔案系統操作詳情
        md_lines.append("## 三、檔案落盤與同步狀態 (File Operations)")
        if not self.file_operations:
            md_lines.append("> ⚠️ 未進行任何磁碟實體寫入操作")
        else:
            md_lines.append("| 時間 | 操作 | 目標路徑 | 大小 | 結果 |")
            md_lines.append("| :--- | :--- | :--- | :--- | :--- |")
            for f in self.file_operations:
                res_icon = "✅" if f["success"] else "❌"
                md_lines.append(f"| `{f['timestamp']}` | {f['action']} | `{f['path']}` | {f['size']} B | {res_icon} {f['details']} |")
        md_lines.append("")

        # 4. 異常與錯誤堆疊
        if self.errors:
            md_lines.append("## 四、異常錯誤詳細堆疊 (Errors & Exceptions)")
            for err in self.errors:
                md_lines.append(f"### 🔴 [{err['stage']}] {err['error_msg']}")
                if err["traceback"]:
                    md_lines.append("```python")
                    md_lines.append(err["traceback"])
                    md_lines.append("```")
            md_lines.append("")

        report_text = "\n".join(md_lines)

        # 實體寫入檔案
        try:
            self.log_path.write_text(report_text, encoding="utf-8")
            _latest_log_path.write_text(report_text, encoding="utf-8")
        except Exception as e:
            print(f"[ManifestLogger] 寫入實體日誌檔案異常: {e}")

        result_payload = {
            "appid": self.appid,
            "game_name": self.game_name,
            "success": self.success,
            "summary": self.summary,
            "log_filename": self.log_filename,
            "log_path": str(self.log_path),
            "report_markdown": report_text,
            "duration_ms": duration_ms
        }

        global _latest_log_cache
        _latest_log_cache = result_payload
        return result_payload


def get_latest_log() -> Dict[str, Any]:
    """獲取最後一次更新的日誌資料"""
    global _latest_log_cache
    if _latest_log_cache:
        return _latest_log_cache

    if _latest_log_path.exists():
        try:
            txt = _latest_log_path.read_text(encoding="utf-8", errors="replace")
            return {
                "success": True,
                "log_path": str(_latest_log_path),
                "report_markdown": txt,
                "summary": "從 latest_update.log 載入之歷史日誌"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    return {"success": False, "error": "尚無任何更新日誌紀錄"}


def get_logs_directory() -> str:
    """取得日誌儲存目錄絕對路徑"""
    return str(_logs_dir)
