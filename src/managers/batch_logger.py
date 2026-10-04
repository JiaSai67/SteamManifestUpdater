# -*- coding: utf-8 -*-
"""
Batch Update Diagnostic Logger (全鏈路批次更新調度日誌)
專為多遊戲批次自動更新設計之總調度日誌模組：
1. 記錄批次觸發時間、掃描之待更新清單 (避免前端時序差漏更)
2. 記錄各遊戲執行順序、耗時與個別結果 (Success / Fail / Skip)
3. 生成全鏈路結構化 Markdown 批次診斷報告
4. 自動清理超額日誌 (保留最近 10 份)
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

_root_dir = Path(__file__).resolve().parent.parent.parent
_logs_dir = _root_dir / "logs" / "batch_updates"
_logs_dir.mkdir(parents=True, exist_ok=True)

_latest_log_path = _logs_dir / "latest_batch_update.log"
_active_sessions: Dict[str, "BatchUpdateLogger"] = {}


class BatchUpdateLogger:
    """單次批次更新總調度日誌"""
    def __init__(self, target_games: List[Dict[str, Any]]):
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
        self.target_games = target_games or []
        self.total_count = len(self.target_games)
        self.items: List[Dict[str, Any]] = []
        self.success_count = 0
        self.fail_count = 0
        self.log_filename = f"batch_update_{self.session_id}.log"
        self.log_path = _logs_dir / self.log_filename

        # 自動清理舊日誌 (保留最近 10 份)
        self._rotate_logs(max_keep=10)

    def _rotate_logs(self, max_keep: int = 10):
        try:
            logs = sorted(
                [f for f in _logs_dir.glob("batch_update_*.log") if f.is_file()],
                key=lambda x: x.stat().st_mtime
            )
            while len(logs) >= max_keep:
                oldest = logs.pop(0)
                try:
                    oldest.unlink(missing_ok=True)
                except Exception:
                    pass
        except Exception:
            pass

    def log_item(self, appid: str, name: str, success: bool, duration_ms: int = 0, msg: str = ""):
        entry = {
            "appid": str(appid).strip(),
            "name": name or f"App_{appid}",
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "success": success,
            "duration_ms": duration_ms,
            "msg": msg or ("更新成功" if success else "更新失敗")
        }
        self.items.append(entry)
        if success:
            self.success_count += 1
        else:
            self.fail_count += 1
        tag = "[OK]" if success else "[FAIL]"
        try:
            print(f"[BatchUpdateLogger][{self.session_id}] {tag} {entry['name']} ({entry['appid']}) - {entry['msg']} ({duration_ms}ms)")
        except Exception:
            pass

    def finish(self, summary: str = "") -> Dict[str, Any]:
        self.end_time = datetime.now()
        total_duration_ms = int((self.end_time - self.start_time).total_seconds() * 1000)
        
        md_lines = []
        md_lines.append(f"# 【批次更新總調度診斷報告】Session {self.session_id}")
        md_lines.append(f"- **執行時間**: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')} (總耗時 {total_duration_ms} ms)")
        md_lines.append(f"- **待更新排隊數**: {self.total_count} 款遊戲")
        md_lines.append(f"- **最終結果**: 成功 {self.success_count} 款，失敗 {self.fail_count} 款")
        if summary:
            md_lines.append(f"- **備註說明**: {summary}")
        md_lines.append("")

        # 1. 隊列清單
        md_lines.append("## 一、本次批次鎖定之待更新隊列 (Queued Targets)")
        md_lines.append("| # | AppID | 遊戲名稱 | 檢測版本狀態 | 建議來源 |")
        md_lines.append("| :-: | :--- | :--- | :--- | :--- |")
        for idx, g in enumerate(self.target_games):
            aid = g.get("appid", "")
            nm = g.get("name", f"App_{aid}")
            vs = g.get("version_status", "待更新")
            src = g.get("best_source", "ryuu")
            md_lines.append(f"| {idx+1} | `{aid}` | **{nm}** | {vs} | {src} |")
        md_lines.append("")

        # 2. 逐項執行軌跡
        md_lines.append("## 二、逐項更新執行軌跡 (Execution Log)")
        md_lines.append("| 時間 | AppID | 遊戲名稱 | 結果 | 耗時 | 詳細訊息 |")
        md_lines.append("| :--- | :--- | :--- | :-: | :-: | :--- |")
        for it in self.items:
            icon = "🟢 成功" if it["success"] else "🔴 失敗"
            md_lines.append(f"| `{it['timestamp']}` | `{it['appid']}` | **{it['name']}** | {icon} | {it['duration_ms']} ms | {it['msg']} |")
        md_lines.append("")

        # 3. 異常排查建議 (若有失敗項目)
        if self.fail_count > 0:
            md_lines.append("## 三、失敗項目異常診斷")
            for it in self.items:
                if not it["success"]:
                    md_lines.append(f"- **{it['name']} (`{it['appid']}`)**: {it['msg']}")
                    md_lines.append(f"  建議：可於軟體管理頁單獨點擊該小卡嘗試「一鍵更新」，或檢查 `logs/manifest_updates/manifest_update_{it['appid']}_*.log` 獲取網路封包細節。")
            md_lines.append("")

        report_text = "\n".join(md_lines)

        try:
            self.log_path.write_text(report_text, encoding="utf-8")
            _latest_log_path.write_text(report_text, encoding="utf-8")
        except Exception as e:
            print(f"[BatchUpdateLogger] 寫入批次日誌異常: {e}")

        return {
            "session_id": self.session_id,
            "total_count": self.total_count,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "log_filename": self.log_filename,
            "log_path": str(self.log_path),
            "report_markdown": report_text,
            "duration_ms": total_duration_ms
        }


def start_session(target_games: List[Dict[str, Any]]) -> str:
    """啟動一次新的批次更新 session"""
    logger = BatchUpdateLogger(target_games)
    _active_sessions[logger.session_id] = logger
    return logger.session_id


def log_session_item(session_id: str, appid: str, name: str, success: bool, duration_ms: int = 0, msg: str = ""):
    """記錄單個遊戲更新結果"""
    logger = _active_sessions.get(session_id)
    if logger:
        logger.log_item(appid, name, success, duration_ms=duration_ms, msg=msg)


def finish_session(session_id: str, summary: str = "") -> Dict[str, Any]:
    """結束並結算批次日誌"""
    logger = _active_sessions.pop(session_id, None)
    if logger:
        return logger.finish(summary=summary)
    return {"session_id": session_id, "success": False, "msg": "Session not found"}
