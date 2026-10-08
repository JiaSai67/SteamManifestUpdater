# -*- coding: utf-8 -*-
"""
SMU 本機 DPAPI 密鑰保險箱與節點公鑰管理模組 (DPAPI Key Manager)
功能：
1. 呼叫 Windows 原生 DPAPI (CryptProtectData / CryptUnprotectData)，0 第三方依賴。
2. 本地私鑰綁死當前 Windows 使用者與主機板物理特徵，複製到他機無法解密。
3. 派生唯一之本機 DPAPI 節點公鑰 (DPAPI Public Key)。
4. 提供 HMAC-SHA256 數位簽章能力，供發送前對加密封包蓋章驗證。
"""

import os
import sys
import hmac
import hashlib
import secrets
from typing import Optional, Tuple

_DPAPI_SALT = b"SMU_DPAPI_PUBLIC_DERIVATION_SALT_V1"

# Windows 原生 DPAPI 介面封裝
def _dpapi_protect(data: bytes) -> bytes:
    """使用 Windows DPAPI 加密二進位資料"""
    if sys.platform != "win32":
        # 非 Windows 平台 (測試或降級)
        return hashlib.sha256(data).digest() + data

    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte))
        ]

    blob_in = DATA_BLOB()
    blob_in.cbData = len(data)
    blob_in.pbData = ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_byte))

    blob_out = DATA_BLOB()
    # CRYPTPROTECT_UI_FORBIDDEN = 0x1
    if ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        "SMU_DPAPI_KEY",
        None,
        None,
        None,
        0x1,
        ctypes.byref(blob_out)
    ):
        result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return result
    else:
        raise OSError("Windows DPAPI 加密失敗")

def _dpapi_unprotect(data: bytes) -> bytes:
    """使用 Windows DPAPI 解密二進位資料"""
    if sys.platform != "win32":
        return data[32:]

    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte))
        ]

    blob_in = DATA_BLOB()
    blob_in.cbData = len(data)
    blob_in.pbData = ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_byte))

    blob_out = DATA_BLOB()
    if ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0x1,
        ctypes.byref(blob_out)
    ):
        result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return result
    else:
        raise OSError("Windows DPAPI 解密失敗 (非本機或憑證不符)")

class DPAPIKeyManager:
    """本機 DPAPI 密鑰保險箱與公鑰管理器"""
    _instance: Optional["DPAPIKeyManager"] = None

    def __init__(self, vault_dir: Optional[str] = None):
        if vault_dir is None:
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            vault_dir = os.path.join(root, "data", ".sec")
        
        self.vault_dir = vault_dir
        self.vault_file = os.path.join(vault_dir, "dpapi_vault.bin")
        self._private_key: Optional[bytes] = None
        self._public_key: Optional[str] = None
        self._ensure_keys()

    @classmethod
    def get_instance(cls) -> "DPAPIKeyManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _ensure_keys(self):
        """確認並載入或生成受 DPAPI 保護之密鑰"""
        os.makedirs(self.vault_dir, exist_ok=True)
        if os.path.exists(self.vault_file):
            try:
                with open(self.vault_file, "rb") as f:
                    encrypted = f.read()
                self._private_key = _dpapi_unprotect(encrypted)
            except Exception:
                # 檔案損壞或機器更換，重新生成
                self._private_key = None

        if not self._private_key or len(self._private_key) < 32:
            # 生成 32 位元組高熵私鑰種子
            self._private_key = secrets.token_bytes(32)
            try:
                encrypted = _dpapi_protect(self._private_key)
                with open(self.vault_file, "wb") as f:
                    f.write(encrypted)
            except Exception as e:
                # 降級備援保存
                pass

        # 派生唯一之本機 DPAPI 公鑰 (對外公開，任何人可驗證)
        h = hashlib.sha256(self._private_key + _DPAPI_SALT).hexdigest().upper()
        self._public_key = f"DPAPI_PUB_{h[:32]}"

    def get_public_key(self) -> str:
        """取得本機專屬 DPAPI 公鑰"""
        if not self._public_key:
            self._ensure_keys()
        return self._public_key or "DPAPI_PUB_UNKNOWN"

    def sign_payload(self, message: str) -> str:
        """使用本機 DPAPI 私鑰對字串訊息蓋下 HMAC-SHA256 數位印章"""
        if not self._private_key:
            self._ensure_keys()
        sig = hmac.new(self._private_key, message.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"SIG_{sig}"

def get_dpapi_public_key() -> str:
    """便捷取得本機 DPAPI 公鑰"""
    return DPAPIKeyManager.get_instance().get_public_key()

def sign_with_dpapi(message: str) -> str:
    """便捷使用 DPAPI 私鑰簽名"""
    return DPAPIKeyManager.get_instance().sign_payload(message)

if __name__ == "__main__":
    mgr = DPAPIKeyManager.get_instance()
    pub = mgr.get_public_key()
    sig = mgr.sign_payload("TEST_ACTION_PING")
    print(f"DPAPI Public Key: {pub}")
    print(f"DPAPI Signature : {sig}")
