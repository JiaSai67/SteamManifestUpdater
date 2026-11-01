# -*- coding: utf-8 -*-
"""
SMU 友邀代碼加密與純英數高密度編碼引擎 (Friend Invite Code Crypto Engine)

設計目標：
1. 純本地無伺服器 (Zero-DB / Zero-Server) 對稱驗證加密：
   僅憑一段純英數代碼，即可於接收端本地 100% 離線解密還原出：
   - Discord Webhook 專屬授權端點 (ID + 68 碼 Token + 官方子網域)
   - 該次打包上傳之入口訊息 Snowflake ID (內含毫秒級打包當下時間戳)
   - 單檔 / 多分卷索引模式標記
2. 密碼學強度與防錯校驗 (AEAD-SIV 架構)：
   - 採用 HMAC-SHA256 衍生 32-bit SIV (Synthetic IV) 認證標籤作為動態初始向量與完整性簽章。
   - 每次打包因當下毫秒級時間戳與訊息 ID 不同，產生的整段友邀代碼皆 100% 雪崩變化。
   - 任何 1 字元漏貼、錯字或竄改，皆可在本地 <0.1ms 內 100% 攔截 (誤判率 < 1 / 42.9 億)，杜絕錯誤解密。
3. 最精簡穩定長度 (固定 97 碼純英數)：
   - 採用純英數字元集 (0-9, A-Z, a-z，共 62 個字元，無任何中文)。
   - 總容量 62^97 > 2^576，精確容納 72 bytes 加密封包。
   - 全程無標點、無特殊符號、無空白，於 Discord / LINE / Steam 聊天室雙擊即可完整選取，亦支援從整段邀請文案中自動精準提取。
"""

import re
import time
import hmac
import struct
import hashlib
import datetime
import unicodedata
from typing import Dict, Any, Optional, Tuple

# Discord Epoch (2015-01-01T00:00:00Z in ms)
DISCORD_EPOCH_MS = 1420070400000

# 協定版本與固定封包規格
PROTOCOL_VERSION = 1
STD_PLAINTEXT_LEN = 68   # 1B header + 8B webhook_id + 8B message_id + 51B (68*6bit token)
SIV_TAG_LEN = 4          # 32-bit HMAC-SHA256 Synthetic IV & MAC Tag
STD_PACKET_LEN = STD_PLAINTEXT_LEN + SIV_TAG_LEN  # 72 bytes = 576 bits
STD_CODE_CHARS = 97      # 固定 97 碼純英數 (Base62)

# 對稱主金鑰種子 (分別獨立派生 MAC 金鑰與 CTR 加密金鑰)
_MASTER_SECRET = b"SMU_FRIEND_INVITE_CODE_AEAD_SIV_V1_2026_SAKURA"
_KEY_MAC = hashlib.sha256(_MASTER_SECRET + b":MAC_AUTH").digest()
_KEY_ENC = hashlib.sha256(_MASTER_SECRET + b":CTR_STREAM").digest()

# Base64URL 標準 64 字元表 (對應 Discord Webhook Token 字元集)
_B64URL_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
_B64URL_MAP = {ch: idx for idx, ch in enumerate(_B64URL_ALPHABET)}

# 支援之 Discord 官方 Webhook 網域表 (2 bits: 0~3)
_DOMAINS = (
    "discord.com",
    "ptb.discord.com",
    "canary.discord.com",
    "discordapp.com",
)

_WEBHOOK_PARSE_RE = re.compile(
    r"^https:\/\/((?:(?:canary|ptb)\.)?discord(?:app)?\.com)\/api\/webhooks\/(\d+)\/([A-Za-z0-9_-]+)\/?(?:\?.*)?$",
    re.IGNORECASE
)

# 純英數字池 (Base62: 0-9, A-Z, a-z，共 62 字元，完全無中文)
BASE62_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
BASE62_MAP = {ch: idx for idx, ch in enumerate(BASE62_ALPHABET)}


def _derive_ctr_keystream(siv_tag: bytes, length: int) -> bytes:
    """以 32-bit SIV Tag 作為 Nonce，透過 HMAC-SHA256-CTR 產生加密金鑰流"""
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(_KEY_ENC, siv_tag + struct.pack(">I", counter), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def _compute_siv_tag(plaintext: bytes) -> bytes:
    """計算 32-bit (4-byte) SIV 認證標籤，同時作為隨機化 IV 與完整性簽章"""
    return hmac.new(_KEY_MAC, plaintext, hashlib.sha256).digest()[:SIV_TAG_LEN]


def _pack_6bit_token_68(token: str) -> Optional[bytes]:
    """將標準 68 碼 Base64URL Token 無損壓縮為 51 bytes (408 bits)"""
    if len(token) != 68:
        return None
    acc = 0
    for ch in token:
        val = _B64URL_MAP.get(ch)
        if val is None:
            return None
        acc = (acc << 6) | val
    return acc.to_bytes(51, "big")


def _unpack_6bit_token_68(raw_51: bytes) -> str:
    """將 51 bytes (408 bits) 無損還原為 68 碼 Base64URL Token"""
    acc = int.from_bytes(raw_51, "big")
    chars = [""] * 68
    for i in range(67, -1, -1):
        chars[i] = _B64URL_ALPHABET[acc & 0x3F]
        acc >>= 6
    return "".join(chars)


def parse_discord_webhook(webhook_url: str) -> Tuple[int, int, str]:
    """
    解析並正規化 Discord Webhook 網址。
    回傳: (domain_id, webhook_id_uint64, webhook_token)
    """
    if not webhook_url or not isinstance(webhook_url, str):
        raise ValueError("Webhook 網址為空")
    m = _WEBHOOK_PARSE_RE.match(webhook_url.strip())
    if not m:
        raise ValueError("無效的 Discord Webhook 網址格式")
    host = m.group(1).lower()
    if host.startswith("ptb."):
        domain_id = 1
    elif host.startswith("canary."):
        domain_id = 2
    elif "discordapp.com" in host:
        domain_id = 3
    else:
        domain_id = 0

    webhook_id = int(m.group(2))
    if webhook_id <= 0 or webhook_id >= (1 << 64):
        raise ValueError("Webhook ID 超出 64-bit Snowflake 範圍")
    token = m.group(3)
    return domain_id, webhook_id, token


def snowflake_to_timestamp_ms(snowflake_id: int) -> int:
    """由 Discord 64-bit Snowflake ID 提取精確至毫秒之 UTC 時間戳"""
    return (int(snowflake_id) >> 22) + DISCORD_EPOCH_MS


def _encode_base62(packet: bytes, fixed_97: bool = True) -> str:
    """將加密二進位封包編碼為純英數 (Base62) 字串"""
    if fixed_97:
        if len(packet) != STD_PACKET_LEN:
            raise ValueError(f"標準封包長度必須為 {STD_PACKET_LEN} bytes")
        num = int.from_bytes(packet, "big")
        out = []
        for _ in range(STD_CODE_CHARS):
            num, rem = divmod(num, 62)
            out.append(BASE62_ALPHABET[rem])
        if num != 0:
            raise ValueError("封包數值超出 97 碼編碼容量")
        return "".join(out)

    # 變長備援模式 (若未來 Token 長度 != 68)：附加 2 bytes 長度尾標，並加上前綴 'v'
    framed = packet + struct.pack(">H", len(packet))
    num = int.from_bytes(framed, "big")
    out = []
    temp = num
    while temp > 0:
        temp, rem = divmod(temp, 62)
        out.append(BASE62_ALPHABET[rem])
    return "v" + "".join(out)


def _decode_base62(code_str: str) -> bytes:
    """將純英數 (Base62) 字串還原為加密二進位封包"""
    is_var = code_str.startswith("v") and len(code_str) != STD_CODE_CHARS
    body = code_str[1:] if is_var else code_str

    if not is_var and len(body) != STD_CODE_CHARS:
        raise ValueError(f"友邀代碼長度應為 {STD_CODE_CHARS} 碼 (目前為 {len(body)} 碼)")

    acc = 0
    for ch in reversed(body):
        idx = BASE62_MAP.get(ch)
        if idx is None:
            raise ValueError(f"友邀代碼包含非英數字元 '{ch}'")
        acc = acc * 62 + idx

    if not is_var:
        try:
            return acc.to_bytes(STD_PACKET_LEN, "big")
        except OverflowError:
            raise ValueError("友邀代碼數值溢位，代碼可能已損毀")

    # 變長備援模式解碼
    pkt_len = acc & 0xFFFF
    if pkt_len <= 0 or pkt_len > 4096:
        raise ValueError("變長友邀代碼長度校驗失敗")
    raw = (acc >> 16).to_bytes(pkt_len, "big")
    return raw


def extract_code_from_text(raw_text: str) -> str:
    """
    智慧提取器：
    支援使用者直接貼上純代碼，或連同聊天室邀請文案、括號 `〖...〗`、換行空白一併貼上時，
    自動精準定位並提取出 97 碼純英數友邀代碼。
    """
    if not raw_text or not isinstance(raw_text, str):
        return ""

    norm = unicodedata.normalize("NFKC", raw_text.strip())

    # 1. 若包含專用書名括號 〖...〗 或 [ ... ]，優先擷取括號內內容
    m_bracket = re.search(r"[〖\[]([A-Za-z0-9]{90,140})[〗\]]", norm)
    if m_bracket:
        return m_bracket.group(1)

    # 2. 移除所有空白、換行與不可見字元
    compact = re.sub(r"[\s\u200b-\u200f\ufeff]+", "", norm)

    # 3. 優先檢查變長代碼 (以小寫 'v' 開頭且後接純英數)
    if compact.startswith("v") and len(compact) > 80:
        m_var = re.search(r"\b(v[A-Za-z0-9]{80,140})\b", norm)
        if m_var:
            return m_var.group(1)
        if re.fullmatch(r"v[A-Za-z0-9]+", compact):
            return compact

    # 4. 精確 97 碼全詞匹配
    if len(compact) == STD_CODE_CHARS and re.fullmatch(r"[A-Za-z0-9]{97}", compact):
        return compact

    m_code = re.search(r"\b([A-Za-z0-9]{97})\b", norm)
    if m_code:
        return m_code.group(1)

    # 5. 在無空白文字中精確提取 97 碼
    m_loose = re.search(r"([A-Za-z0-9]{97})", compact)
    if m_loose:
        return m_loose.group(1)

    return compact


def encrypt_friend_code(
    webhook_url: str,
    entry_message_id: int,
    is_multipart: bool = False,
    timestamp_sec: Optional[int] = None
) -> str:
    """
    將 Discord Webhook + 入口訊息 ID (含毫秒級打包時間戳) 加密生成 97 碼純英數「友邀代碼」。
    """
    domain_id, webhook_id, token = parse_discord_webhook(webhook_url)
    msg_id = int(entry_message_id)
    if msg_id <= 0 or msg_id >= (1 << 64):
        raise ValueError("無效的 Discord 訊息 ID")

    ts_val = int(timestamp_sec if timestamp_sec is not None else time.time())
    time_parity = ts_val & 0x01

    packed_token = _pack_6bit_token_68(token)
    is_std_68 = packed_token is not None

    # 組裝 1-byte Header:
    # bits 0..2: PROTOCOL_VERSION (1)
    # bits 3..4: domain_id (0..3)
    # bit  5   : is_multipart (0/1)
    # bit  6   : is_std_68 (0/1)
    # bit  7   : time_parity (0/1)
    header_byte = (
        (PROTOCOL_VERSION & 0x07)
        | ((domain_id & 0x03) << 3)
        | ((1 if is_multipart else 0) << 5)
        | ((1 if is_std_68 else 0) << 6)
        | ((time_parity & 0x01) << 7)
    )

    if is_std_68:
        plaintext = (
            bytes([header_byte])
            + struct.pack(">QQ", webhook_id, msg_id)
            + packed_token
        )
        siv_tag = _compute_siv_tag(plaintext)
        keystream = _derive_ctr_keystream(siv_tag, len(plaintext))
        ciphertext = bytes(p ^ k for p, k in zip(plaintext, keystream))
        packet = siv_tag + ciphertext
        return _encode_base62(packet, fixed_97=True)
    else:
        token_bytes = token.encode("ascii")
        if len(token_bytes) > 200:
            raise ValueError("Webhook Token 長度異常")
        plaintext = (
            bytes([header_byte])
            + struct.pack(">QQB", webhook_id, msg_id, len(token_bytes))
            + token_bytes
        )
        siv_tag = _compute_siv_tag(plaintext)
        keystream = _derive_ctr_keystream(siv_tag, len(plaintext))
        ciphertext = bytes(p ^ k for p, k in zip(plaintext, keystream))
        packet = siv_tag + ciphertext
        return _encode_base62(packet, fixed_97=False)


def decrypt_friend_code(raw_code: str) -> Dict[str, Any]:
    """
    於本地離線解密並驗證「友邀代碼」。
    回傳:
    {
        "ok": bool,
        "code": str,                 # 清理後之純淨友邀代碼
        "webhook_url": str,          # 還原之 Discord Webhook URL (僅供後端內部請求，絕不外洩至前端)
        "webhook_id": str,
        "entry_message_id": str,
        "is_multipart": bool,
        "timestamp_ms": int,         # 打包當下之毫秒級時間戳
        "created_at": str,           # 本地時區格式化時間 (YYYY-MM-DD HH:MM:SS)
        "msg": str
    }
    """
    clean = extract_code_from_text(raw_code)
    if not clean:
        return {"ok": False, "msg": "請貼上友邀代碼"}

    try:
        packet = _decode_base62(clean)
    except ValueError as ve:
        return {"ok": False, "msg": str(ve)}
    except Exception:
        return {"ok": False, "msg": "友邀代碼格式錯誤，無法解析"}

    if len(packet) < SIV_TAG_LEN + 18:
        return {"ok": False, "msg": "友邀代碼資料長度不足"}

    siv_tag = packet[:SIV_TAG_LEN]
    ciphertext = packet[SIV_TAG_LEN:]
    keystream = _derive_ctr_keystream(siv_tag, len(ciphertext))
    plaintext = bytes(c ^ k for c, k in zip(ciphertext, keystream))

    # 嚴格常數時間驗證 32-bit HMAC-SHA256 SIV 完整性簽章
    expected_tag = _compute_siv_tag(plaintext)
    if not hmac.compare_digest(siv_tag, expected_tag):
        return {
            "ok": False,
            "msg": "友邀代碼校驗失敗：代碼可能有錯字、漏字或已損毀，請重新完整複製"
        }

    header_byte = plaintext[0]
    ver = header_byte & 0x07
    if ver != PROTOCOL_VERSION:
        return {"ok": False, "msg": f"不支援的友邀代碼協定版本 (v{ver})，請更新工具至最新版"}

    domain_id = (header_byte >> 3) & 0x03
    is_multipart = bool((header_byte >> 5) & 0x01)
    is_std_68 = bool((header_byte >> 6) & 0x01)

    webhook_id, msg_id = struct.unpack(">QQ", plaintext[1:17])
    if webhook_id <= 0 or msg_id <= 0:
        return {"ok": False, "msg": "友邀代碼內部參數異常"}

    if is_std_68:
        if len(plaintext) != STD_PLAINTEXT_LEN:
            return {"ok": False, "msg": "友邀代碼封包結構不符"}
        token = _unpack_6bit_token_68(plaintext[17:68])
    else:
        t_len = plaintext[17]
        if len(plaintext) != 18 + t_len:
            return {"ok": False, "msg": "變長友邀代碼封包結構不符"}
        token = plaintext[18:18 + t_len].decode("ascii", errors="strict")

    domain_host = _DOMAINS[domain_id]
    webhook_url = f"https://{domain_host}/api/webhooks/{webhook_id}/{token}"
    ts_ms = snowflake_to_timestamp_ms(msg_id)
    try:
        dt_local = datetime.datetime.fromtimestamp(ts_ms / 1000.0)
        created_at_str = dt_local.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        created_at_str = "未知時間"

    return {
        "ok": True,
        "code": clean,
        "webhook_url": webhook_url,
        "webhook_id": str(webhook_id),
        "entry_message_id": str(msg_id),
        "is_multipart": is_multipart,
        "timestamp_ms": ts_ms,
        "created_at": created_at_str,
        "msg": f"✅ 本地解密校驗通過 (打包時間：{created_at_str})"
    }
