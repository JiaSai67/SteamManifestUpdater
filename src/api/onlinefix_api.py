import urllib.request
import urllib.parse
import json
import re

class OnlineFixAPI:
    def __init__(self):
        from managers import config_manager
        self.config = config_manager.get_config()
        self.domain = self.config.get("onlinefix_domain", "https://online-fix.me")
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    def get_steam_game_name(self, appid):
        url = f"https://store.steampowered.com/api/appdetails?appids={appid}"
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=10) as res:
                data = json.loads(res.read().decode('utf-8'))
                if str(appid) in data and data[str(appid)]['success']:
                    name = data[str(appid)]['data']['name']
                    # Clean up name for search: remove special chars
                    clean_name = re.sub(r'[^\w\s-]', '', name).strip()
                    # Take first two words if too long to ensure broad search
                    words = clean_name.split()
                    if len(words) > 3:
                        clean_name = " ".join(words[:3])
                    return clean_name
        except Exception as e:
            print(f"Error fetching steam name: {e}")
        return None

    def search_game(self, query):
        url = f"{self.domain}/index.php?do=search"
        data = urllib.parse.urlencode({'do': 'search', 'subaction': 'search', 'story': query}).encode('utf-8')
        try:
            req = urllib.request.Request(url, data=data, headers=self.headers)
            with urllib.request.urlopen(req, timeout=10) as res:
                html = res.read().decode('utf-8', errors='ignore')
                # Find all links to games
                domain_escaped = re.escape(self.domain)
                links = re.findall(rf'<a[^>]+href=[\'\"]({domain_escaped}/games/[^\'\"]+)[\'\"][^>]*>(.*?)</a>', html)
                # Filter out comments and duplicates
                game_pages = []
                seen = set()
                for link, title in links:
                    if '#' not in link and link not in seen:
                        # Clean title
                        title = re.sub(r'<[^>]+>', '', title).strip()
                        game_pages.append({"url": link, "title": title})
                        seen.add(link)
                return game_pages
        except Exception as e:
            print(f"Error searching online-fix: {e}")
            return []

    def get_download_links(self, game_url):
        try:
            req = urllib.request.Request(game_url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=10) as res:
                html = res.read().decode('utf-8', errors='ignore')
                links = re.findall(r'<a[^>]+href=[\'\"]([^\'\"]+)[\'\"][^>]*>([^<]+)</a>', html)
                
                downloads = {}
                for url, text in links:
                    if 'Скачать с Online-Fix Hosters' in text or 'Online-Fix Hosters' in text:
                        downloads['hosters'] = url
                    elif 'Скачать Torrent' in text or 'Torrent' in text:
                        downloads['torrent'] = url
                    elif 'Скачать с Online-Fix Drive' in text or 'Online-Fix Drive' in text:
                        downloads['drive'] = url
                return downloads
        except Exception as e:
            print(f"Error getting download links: {e}")
            return {}
