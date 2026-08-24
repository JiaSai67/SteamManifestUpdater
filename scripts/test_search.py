import urllib.request
import re

try:
    req = urllib.request.Request('https://lua.tools/', headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        html = response.read().decode('utf-8')
        scripts = re.findall(r'src="(/_next/static/chunks/[^"]+)"', html)
        print('Scripts:', scripts)
        
        for s in scripts:
            if 'page-' in s or 'layout-' in s:
                js_req = urllib.request.Request('https://lua.tools' + s, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(js_req) as js_res:
                    js_code = js_res.read().decode('utf-8')
                    endpoints = re.findall(r'/api/[a-zA-Z0-9_/-]+', js_code)
                    if endpoints:
                        print(f"Endpoints in {s}:", set(endpoints))
except Exception as e:
    print(e)
