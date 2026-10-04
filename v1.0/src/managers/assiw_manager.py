import io
import time
import zipfile
import hashlib
import random
import requests
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

from PySide6.QtCore import QThread, Signal

BASE_URL = "https://steam.assiw.xyz"
SECRET_SALT = "bPMC|RW2@QSA*_Ch#hck"
MASTER_SALT = "steamstart2020"
MASTER_CARD_KEY = "L8RCpeQc7uTTCDyfR6ea"

_cached_token: Optional[str] = None
_token_expiry: float = 0.0

def _generate_random_ip() -> str:
    """Generate a plausible public IPv4 address to rotate IP quota."""
    first = random.choice([
        random.randint(11, 126),
        random.randint(128, 168),
        random.randint(173, 191),
        random.randint(193, 223)
    ])
    return f"{first}.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}"

def get_quota(ip: Optional[str] = None, timeout: int = 5) -> Dict[str, Any]:
    """
    Check current remaining quota from /down/quota.
    If ip is provided, checks quota for that simulated IP via X-Forwarded-For.
    """
    url = f"{BASE_URL}/down/quota"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://steam.assiw.xyz/"
    }
    if ip:
        headers["X-Forwarded-For"] = ip
        headers["X-Real-IP"] = ip
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {"max": 25, "remaining": 0, "success": False}

def get_active_card_key() -> str:
    """Get the active card key, allowing custom key override from config."""
    try:
        from managers import config_manager
        cfg = config_manager.get_config()
        custom_key = cfg.get("assiw_card_key", "").strip()
        if custom_key:
            return custom_key
    except Exception:
        pass
    return MASTER_CARD_KEY


def md5(text: str) -> str:
    """Compute hex MD5 hash."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def encrypt_key(key: str, ts: int) -> str:
    """
    Encrypt the master card key using XOR with MD5 stream cipher.
    Matches frontend JavaScript logic:
    hash = md5(ts + ':' + SECRET_SALT)
    """
    h = hashlib.md5(f"{ts}:{SECRET_SALT}".encode("utf-8")).hexdigest()
    key_bytes = [int(h[i:i+2], 16) for i in range(0, 32, 2)]
    res = []
    for i, c in enumerate(key):
        xor_val = ord(c) ^ key_bytes[i % len(key_bytes)]
        res.append(f"{xor_val:02x}")
    return "".join(res)

def check_supported(appid: int | str, timeout: int = 5) -> bool:
    """
    Fast check whether steam.assiw.xyz has a manifest for this appid.
    GET /pp/check?appid={appid}
    Returns True if supported, False otherwise.
    """
    url = f"{BASE_URL}/pp/check?appid={appid}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://steam.assiw.xyz/"
    }
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            return bool(data.get("ok") and data.get("supported"))
    except Exception:
        pass
    return False

def get_stlua_token(force_refresh: bool = False, timeout: int = 5) -> Optional[str]:
    """
    Retrieve access token for /stlua/ APIs.
    Tolerates server clock drifts by testing offsets.
    """
    global _cached_token, _token_expiry
    now = time.time()
    if not force_refresh and _cached_token and now < _token_expiry:
        return _cached_token

    now_ts = int(now)
    offsets = [0, -1, 1, -2, 2, -3, 3, -5, 5, -10, 10, -30, 30, -60, 60]
    headers_base = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://steam.assiw.xyz/"
    }
    
    for offset in offsets:
        ts = now_ts + offset
        master_key = md5(f"{MASTER_SALT}{ts}")
        url = f"{BASE_URL}/stlua/auth/mssld"
        headers = {**headers_base, "x-master-key": master_key}
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200:
                data = r.json()
                if data.get("success") and "data" in data and "token" in data["data"]:
                    _cached_token = data["data"]["token"]
                    _token_expiry = now + 1800 # cache for 30 minutes
                    return _cached_token
        except Exception:
            continue
            
    return None

def search_product(appid: int | str, timeout: int = 6) -> List[Dict[str, Any]]:
    """
    Search product information from Assiw.
    POST /stlua/lua
    """
    token = get_stlua_token()
    if not token:
        return []

    url = f"{BASE_URL}/stlua/lua"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "x-access-token": token,
        "Content-Type": "application/json",
        "Referer": "https://steam.assiw.xyz/"
    }
    payload = {"appid": str(appid)}
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            if data.get("success") and isinstance(data.get("data"), list):
                return data["data"]
    except Exception:
        pass
    return []

def fetch_lua_content(appid: int | str, timeout: int = 15, max_retries: int = 3) -> Tuple[bool, str]:
    """
    Download zip blob from Assiw and extract the Lua content.
    Automatically rotates client IP via X-Forwarded-For headers to bypass rate/quota limits.
    Returns (success: bool, content_or_err: str).
    """
    active_key = get_active_card_key()
    last_err = ""
    
    for attempt in range(max_retries):
        now_ts = int(time.time())
        sign = md5(f"{appid}:{now_ts}:{SECRET_SALT}")
        enc_key = encrypt_key(active_key, now_ts)
        
        simulated_ip = _generate_random_ip()
        url = f"{BASE_URL}/down"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json",
            "Referer": "https://steam.assiw.xyz/",
            "X-Forwarded-For": simulated_ip,
            "X-Real-IP": simulated_ip
        }
        payload = {
            "appid": str(appid),
            "ts": now_ts,
            "sign": sign,
            "key": enc_key
        }
        
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}: {r.text[:100]}"
                continue
                
            content = r.content
            if not content.startswith(b"PK"):
                # Not a zip file, possibly an error JSON
                try:
                    err_json = r.json()
                    msg = err_json.get("message", "無效的下載回應")
                    last_err = msg
                    if "次数" in msg or "quota" in msg.lower() or "limit" in msg.lower():
                        continue
                    return False, msg
                except Exception:
                    last_err = f"非預期的檔案格式: {r.text[:100]}"
                    continue
                    
            # Extract Lua file and manifests
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                # 1. Look for exact match {appid}.lua
                target_name = f"{appid}.lua"
                lua_files = [f for f in z.namelist() if f.lower().endswith(".lua")]
                
                chosen_file = None
                if target_name in z.namelist():
                    chosen_file = target_name
                elif lua_files:
                    chosen_file = lua_files[0]
                    
                if not chosen_file:
                    return False, "壓縮檔內未找到 .lua 檔案"
                    
                lua_bytes = z.read(chosen_file)
                lua_text = lua_bytes.decode("utf-8", errors="ignore")
                
                manifests = {}
                for fn in z.namelist():
                    if fn.lower().endswith(".manifest"):
                        manifests[fn] = z.read(fn)
                        
                return True, (lua_text, manifests)
                
        except Exception as e:
            last_err = f"連線或下載失敗: {str(e)}"
            continue

    return False, last_err or "下載失敗或超過重試次數"


def download_lua(appid: int | str, target_dir: Path | str, timeout: int = 15) -> Tuple[bool, str]:
    """
    Download and deploy the Lua manifest for `appid` directly into `target_dir`.
    Creates target_dir / f"{appid}.lua" and deploys .manifest to depotcache / target_dir.
    Returns (success: bool, message: str).
    """
    ok, res = fetch_lua_content(appid, timeout=timeout)
    if not ok:
        return False, str(res)
        
    lua_text = res[0] if isinstance(res, (tuple, list)) else str(res)
    manifests = res[1] if isinstance(res, (tuple, list)) and len(res) > 1 else {}

    # 核心防護規範：沒有 manifest 的檔案直接認定為殘缺檔案，不支援安裝
    if not manifests:
        return False, "來源未提供二進位 .manifest 清單檔（依照安全防護規範判定為殘缺檔案，系統不支援安裝）"
        
    try:
        dest_dir = Path(target_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        file_path = dest_dir / f"{appid}.lua"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(lua_text)
            
        # Deploy manifests
        if manifests:
            steam_dir = dest_dir.parent.parent
            depotcache_dir = steam_dir / "depotcache"
            if depotcache_dir.exists():
                for m_name, m_data in manifests.items():
                    try:
                        (depotcache_dir / m_name).write_bytes(m_data)
                    except Exception:
                        pass
            for m_name, m_data in manifests.items():
                try:
                    (dest_dir / m_name).write_bytes(m_data)
                except Exception:
                    pass
                    
        return True, str(file_path)
    except Exception as e:
        return False, f"儲存 Lua 檔案失敗: {str(e)}"


class AssiwCheckThread(QThread):
    """Background worker to check if Assiw supports an appid."""
    result_ready = Signal(int, bool)  # (appid, is_supported)

    def __init__(self, appid: int | str, parent=None):
        super().__init__(parent)
        self.appid = int(appid) if str(appid).isdigit() else 0

    def run(self):
        try:
            supported = check_supported(self.appid)
            self.result_ready.emit(self.appid, supported)
        except Exception:
            self.result_ready.emit(self.appid, False)


class AssiwDownloadThread(QThread):
    """Background worker to download Lua from Assiw without freezing GUI."""
    finished = Signal(bool, str)  # (success, message_or_filepath)

    def __init__(self, appid: int | str, target_dir: Path | str, parent=None):
        super().__init__(parent)
        self.appid = int(appid) if str(appid).isdigit() else 0
        self.target_dir = target_dir

    def run(self):
        try:
            ok, msg = download_lua(self.appid, self.target_dir)
            self.finished.emit(ok, msg)
        except Exception as e:
            self.finished.emit(False, str(e))

