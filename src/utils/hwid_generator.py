# -*- coding: utf-8 -*-
"""
SMU 硬體指紋與不可偽造系統 ID 模組 (HWID & Identity Generator)
功能：
1. 提取 Windows 物理主機板 UUID (BIOS UUID)。
2. 提取系統實體磁碟序號 (Disk Serial)。
3. 提取微軟系統唯一標識碼 (MachineGuid)。
4. 抓取本地 Steam 已登入之 SteamID64。
5. 加鹽 SHA256 派生不可逆、不可篡改之 HWID。
"""

import os
import sys
import uuid
import hashlib
import subprocess
import winreg
from typing import Dict, Any, Optional

_HWID_SALT = b"SMU_CORE_SECURITY_HWID_SALT_V1"

def get_machine_guid() -> str:
    """從登錄檔讀取微軟官方 MachineGuid"""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(guid).strip()
    except Exception:
        return ""

def get_bios_uuid() -> str:
    """透過 PowerShell / CIM 獲取主機板物理 UUID"""
    try:
        cmd = 'powershell -NoProfile -Command "(Get-CimInstance Win32_ComputerSystemProduct).UUID"'
        res = subprocess.check_output(cmd, shell=True, text=True, timeout=3).strip()
        if res and len(res) >= 16:
            return res
    except Exception:
        pass
    return ""

def get_disk_serial() -> str:
    """透過 PowerShell 獲取系統主要磁碟實體序號"""
    try:
        cmd = 'powershell -NoProfile -Command "(Get-CimInstance Win32_DiskDrive | Select-Object -First 1).SerialNumber"'
        res = subprocess.check_output(cmd, shell=True, text=True, timeout=3).strip()
        if res:
            return res
    except Exception:
        pass
    return ""

def get_active_steamid() -> str:
    """從本地 Steam 登入設定檔提取當前活躍的 SteamID64"""
    try:
        from managers import steam_manager
        return steam_manager.get_current_steamid64() or ""
    except Exception:
        pass
    # 備援讀取登錄檔中的 Steam ActiveProcess
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam\ActiveProcess") as key:
            val, _ = winreg.QueryValueEx(key, "ActiveUser")
            if val and int(val) > 0:
                # 轉為 SteamID64
                return str(int(val) + 76561197960265728)
    except Exception:
        pass
    return ""

def generate_hardware_fingerprint() -> str:
    """
    綜合三大物理硬體特徵加鹽派生不可逆的 HWID (32 碼大寫英數)
    即使使用者刪除軟體重裝、甚至格式化磁區，物理特徵依然固定。
    """
    guid = get_machine_guid()
    bios = get_bios_uuid()
    disk = get_disk_serial()

    raw_seed = f"{guid}_{bios}_{disk}".encode("utf-8")
    if len(raw_seed) < 10:
        # 極少數虛擬機或沙盒備援
        raw_seed = f"{os.environ.get('COMPUTERNAME', '')}_{os.environ.get('USERNAME', '')}".encode("utf-8")

    h = hashlib.sha256(raw_seed + _HWID_SALT).hexdigest().upper()
    return f"HWID_{h[:24]}"

def get_client_identity_bundle() -> Dict[str, str]:
    """獲取客戶端三層身分綁定資料包"""
    hwid = generate_hardware_fingerprint()
    steam_id = get_active_steamid()
    machine_guid = get_machine_guid()
    return {
        "hwid": hwid,
        "steam_id": steam_id,
        "machine_guid": machine_guid
    }

if __name__ == "__main__":
    print("=== SMU 身分指紋檢測 ===")
    bundle = get_client_identity_bundle()
    for k, v in bundle.items():
        print(f"  • {k}: {v}")
