# -*- coding: utf-8 -*-
"""
SteamManifestUpdater - Next-Gen Modern WebApi Entry Point
聚合所有專屬模組化 Handler，對前端暴露 100% 完整且相容之 API 介面
"""
import os
import sys
from pathlib import Path

# 確保 handlers 模組可正確載入
_cur_dir = Path(__file__).resolve().parent
if str(_cur_dir) not in sys.path:
    sys.path.insert(0, str(_cur_dir))

from handlers.base_handler import BaseHandler
from handlers.install_handler import InstallHandler
from handlers.search_handler import SearchHandler
from handlers.manage_handler import ManageHandler
from handlers.party_handler import PartyHandler
from handlers.credentials_handler import CredentialsHandler
from handlers.settings_handler import SettingsHandler
from handlers.steam_handler import SteamHandler
from handlers.system_handler import SystemHandler


class WebApi(
    BaseHandler,
    InstallHandler,
    SearchHandler,
    ManageHandler,
    PartyHandler,
    CredentialsHandler,
    SettingsHandler,
    SteamHandler,
    SystemHandler,
):
    """
    統一 WebApi 門面 (Facade)，向 PyWebView 提供完整 API 呼叫能力。
    底層所有業務邏輯已詳細解耦為專屬子模組：
    - BaseHandler: 視窗控制、事件推播、基礎通訊
    - InstallHandler: Manifest+Lua 部署、網盤補丁、Steam 下載管線 (入庫與更新共用)
    - SearchHandler: 遊戲搜尋、SteamDB 瀏覽、詳情解析
    - ManageHandler: 已入庫遊戲管理、DLC、版本切換、更新檢查
    - PartyHandler: 無伺服器組隊大廳、房間同步
    - CredentialsHandler: 三平台憑證、Token 輪替、配額
    - SettingsHandler: 偏好設定、桌布背景、Google Drive 網盤配置
    - SteamHandler: Steam 進程控制、重啟、離線模式、DLL 注入
    - SystemHandler: 系統自癒健康檢查、錯誤報告、診斷日誌
    """

    def __init__(self):
        super().__init__()
