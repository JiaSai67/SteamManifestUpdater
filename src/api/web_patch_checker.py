import urllib.request
import urllib.parse
import re
import ssl
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import QThread, Signal

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}

def normalize_title(text):
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'online[-_\s]*fix', '', text)
    text = re.sub(r'po[-_\s]*seti', '', text)
    text = re.sub(r'fix[-_\s]*repair', '', text)
    text = re.sub(r'[^a-z0-9]', '', text)
    return text

def is_matching(game_name, candidate_slug):
    t_norm = normalize_title(game_name)
    c_norm = normalize_title(candidate_slug)
    if not t_norm or not c_norm:
        return False
    if t_norm == c_norm:
        return True
    if t_norm in c_norm or c_norm in t_norm:
        ratio = SequenceMatcher(None, t_norm, c_norm).ratio()
        return ratio >= 0.70
    ratio = SequenceMatcher(None, t_norm, c_norm).ratio()
    return ratio >= 0.85

def check_zeigames(game_name):
    if not game_name:
        return None
    encoded = urllib.parse.quote_plus(game_name)
    url = f"https://zeigames.com/search/?q={encoded}&type=downloads_file"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            matches = re.findall(r'href=[\'"](https://zeigames\.com/files/file/(\d+)-([^\'"/?#]+)/?)[\'"]', html)
            for full_url, file_id, slug in matches:
                clean_url = f"https://zeigames.com/files/file/{file_id}-{slug}/"
                if is_matching(game_name, slug):
                    return clean_url
            return None
    except Exception:
        return None

def check_onlinefix(game_name):
    if not game_name:
        return None
    url = "https://online-fix.me/index.php?do=search"
    data = urllib.parse.urlencode({
        'do': 'search',
        'subaction': 'search',
        'story': game_name,
        'search_start': 0,
        'full_search': 0,
        'result_from': 1
    }).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            matches = re.findall(r'href=[\'"](https://online-fix\.me/games/[^/]+/(\d+)-([^\'"]+)\.html)[\'"]', html)
            for full_url, post_id, slug in matches:
                if is_matching(game_name, slug):
                    return full_url
            return None
    except Exception:
        return None

class WebPatchCheckThread(QThread):
    results_ready = Signal(dict)
    
    def __init__(self, game_name, parent=None):
        super().__init__(parent)
        self.game_name = game_name

    def run(self):
        result = {
            "game_name": self.game_name,
            "onlinefix_url": None,
            "zeigames_url": None
        }
        if not self.game_name:
            self.results_ready.emit(result)
            return

        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_of = executor.submit(check_onlinefix, self.game_name)
            fut_zg = executor.submit(check_zeigames, self.game_name)
            
            try:
                result["onlinefix_url"] = fut_of.result(timeout=10)
            except Exception:
                result["onlinefix_url"] = None
                
            try:
                result["zeigames_url"] = fut_zg.result(timeout=10)
            except Exception:
                result["zeigames_url"] = None
                
        self.results_ready.emit(result)
