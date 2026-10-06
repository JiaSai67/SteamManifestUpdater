# -*- coding: utf-8 -*-
"""
PartyLogger - SMU 線上組隊與一鍵安裝專屬診斷日誌中樞
提供：
1. 全鏈路持久化檔案日誌 (logs/party.log)，採用 UTF-8 編碼與自動滾動切片 (10MB x 5)。
2. 與 ErrorReporter 深度整合：一鍵安裝異常、補丁解壓失敗、Steam 授權缺失時自動觸發錯誤回報並持久化至 logs/error_reports.log。
3. 提供給前端與開發者檢視/開啟本地 Log 檔案的介面。
"""

import os
import sys
import logging
import traceback
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Dict, Any, Optional

_root_dir = Path(__file__).resolve().parent.parent.parent
_logs_dir = _root_dir / "logs"
_logs_dir.mkdir(parents=True, exist_ok=True)
_party_log_file = _logs_dir / "party.log"

_is_handler_initialized = False

def _init_party_logging():
    """初始化組隊全域 FileHandler，確保 logs/party.log 100% 寫入"""
    global _is_handler_initialized
    if _is_handler_initialized:
        return

    party_root = logging.getLogger("party")
    party_root.setLevel(logging.INFO)

    # 避免重複掛載
    has_file_handler = any(
        isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", "") == str(_party_log_file)
        for h in party_root.handlers
    )

    if not has_file_handler:
        try:
            fh = RotatingFileHandler(
                str(_party_log_file),
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
                encoding="utf-8"
            )
            fmt = logging.Formatter(
                "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            fh.setFormatter(fmt)
            party_root.addHandler(fh)
        except Exception as e:
            print(f"[PartyLogger] 掛載 party.log 失敗: {e}")

    _is_handler_initialized = True

def get_party_logger(name: str = "general") -> logging.Logger:
    """取得組隊子模組 Logger (如 party.manager, party.packager)"""
    _init_party_logging()
    sub_name = f"party.{name}" if not name.startswith("party") else name
    return logging.getLogger(sub_name)

def log_party_event(category: str, message: str, level: str = "INFO", extra: Optional[Dict[str, Any]] = None):
    """記錄組隊標準事件至 logs/party.log"""
    logger = get_party_logger("event")
    extra_str = f" | {extra}" if extra else ""
    full_msg = f"[{category}] {message}{extra_str}"
    
    lvl = level.upper()
    if lvl == "DEBUG":
        logger.debug(full_msg)
    elif lvl == "WARN" or lvl == "WARNING":
        logger.warning(full_msg)
    elif lvl == "ERROR":
        logger.error(full_msg)
    elif lvl == "CRITICAL":
        logger.critical(full_msg)
    else:
        logger.info(full_msg)

def report_party_error(
    title: str,
    err_msg: str,
    context: str = "",
    level: str = "ERROR",
    extra_fields: Optional[Dict[str, str]] = None,
    sync: bool = False
):
    """
    一鍵安裝或組隊運行異常核心通報：
    1. 記錄至 logs/party.log
    2. 自動持久化記錄至 logs/error_reports.log
    3. 自動向 Discord Webhook 發送結構化崩潰與異常報告
    """
    logger = get_party_logger("error")
    logger.error(f"🚨 [{title}] Context: {context} | Error: {err_msg}")

    try:
        from managers.error_reporter import get_error_reporter
        reporter = get_error_reporter()
        reporter.send_error_report(
            title=f"組隊異常: {title}",
            error_msg=err_msg,
            context=f"Party System - {context}" if context else "Party System",
            level=level,
            extra_fields=extra_fields,
            sync=sync
        )
    except Exception as rep_err:
        logger.warning(f"[PartyLogger] 通報 ErrorReporter 失敗: {rep_err}")

def get_recent_party_logs(max_lines: int = 200) -> str:
    """讀取 logs/party.log 最近 N 行日誌"""
    if not _party_log_file.exists():
        return "尚未生成 logs/party.log 日誌記錄。"
    try:
        lines = _party_log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        recent = lines[-max_lines:] if len(lines) > max_lines else lines
        return "\n".join(recent)
    except Exception as e:
        return f"讀取日誌失敗: {e}"

def open_party_log_file() -> bool:
    """在系統檔案總管或預設編輯器中開啟 logs/party.log"""
    try:
        if not _party_log_file.exists():
            _party_log_file.write_text(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [INFO] [party] Party Log 初始化\n", encoding="utf-8")
        if sys.platform == "win32":
            os.startfile(str(_party_log_file))
            return True
        return False
    except Exception:
        return False
