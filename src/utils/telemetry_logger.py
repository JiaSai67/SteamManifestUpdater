# -*- coding: utf-8 -*-
"""
SMU 組隊大廳與雲端資料流專屬診斷日誌收集器 (Telemetry Logger)
功能：
1. 收集本地端到端所有資料流 (OAuth -> DPAPI -> Supabase -> Turso -> WebRTC)。
2. 環形內存隊列保留最新 300 條記錄，前端可實時查看與一鍵複製。
3. 自動同步寫入 logs/party_telemetry.log 供線下排查。
"""

import os
import sys
import time
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger("party_telemetry")

class TelemetryLogger:
    _instance: Optional["TelemetryLogger"] = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(TelemetryLogger, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._logs: List[Dict[str, Any]] = []
        self._max_logs = 300
        
        # 決定 log 檔案路徑
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.log_dir = os.path.join(root_dir, "logs")
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, "party_telemetry.log")

    def log(self, category: str, message: str, level: str = "INFO", details: Optional[Dict[str, Any]] = None):
        """
        記錄一筆結構化遙測事件
        category: OAUTH | DPAPI | SUPABASE | TURSO | WEBRTC | SYSTEM
        level: INFO | SUCCESS | WARN | ERROR
        """
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        item = {
            "timestamp": ts,
            "category": category.upper(),
            "level": level.upper(),
            "message": message,
            "details": details or {}
        }
        self._logs.append(item)
        if len(self._logs) > self._max_logs:
            self._logs.pop(0)

        # 寫入檔案
        try:
            line = f"[{ts}] [{item['category']}] [{item['level']}] {message}"
            if details:
                line += f" | {json.dumps(details, ensure_ascii=False)}"
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def get_logs(self, limit: int = 150) -> List[Dict[str, Any]]:
        """取得近期日誌"""
        return self._logs[-limit:]

    def get_formatted_text(self, limit: int = 150) -> str:
        """取得適合複製貼上的純文字日誌"""
        lines = []
        for item in self._logs[-limit:]:
            line = f"[{item['timestamp']}] [{item['category']}] [{item['level']}] {item['message']}"
            if item.get("details"):
                line += f"\n  ↳ 參數/回應: {json.dumps(item['details'], ensure_ascii=False)}"
            lines.append(line)
        return "\n".join(lines)

    def clear(self):
        """清空日誌"""
        self._logs.clear()
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, "w", encoding="utf-8") as f:
                    f.write(f"--- 日誌已於 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 重置 ---\n")
        except Exception:
            pass

    def open_log_file(self) -> bool:
        """在作業系統預設程式中開啟 logs/party_telemetry.log"""
        try:
            if not os.path.exists(self.log_file):
                with open(self.log_file, "w", encoding="utf-8") as f:
                    f.write(f"--- 日誌建立於 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            if sys.platform == "win32":
                os.startfile(self.log_file)
                return True
        except Exception as e:
            logger.error(f"開啟日誌檔案失敗: {e}")
        return False

    def open_log_folder(self) -> bool:
        """在 Windows 檔案總管中開啟 logs 資料夾"""
        try:
            os.makedirs(self.log_dir, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(self.log_dir)
                return True
        except Exception as e:
            logger.error(f"開啟日誌資料夾失敗: {e}")
        return False

_telemetry_inst = TelemetryLogger()

def get_telemetry_logger() -> TelemetryLogger:
    return _telemetry_inst

def tlog(category: str, message: str, level: str = "INFO", details: Optional[Dict[str, Any]] = None):
    _telemetry_inst.log(category, message, level, details)
