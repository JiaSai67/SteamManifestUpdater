import os, re, urllib.request, json, time
lua_dir = r'G:\Games\Steam\config\lua'
pattern = re.compile(r'setManifestid\(\s*(\d+)\s*,\s*"(\d+)"(?:,\s*(\d+))?\s*\)')
mismatches = []

def get_info(appid):
    try:
        url = f'https://api.steamcmd.net/v1/info/{appid}'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get('data', {}).get(str(appid), {})
    except:
        return None

for filename in os.listdir(lua_dir):
    if not filename.endswith('.lua'): continue
    appid = filename.replace('.lua', '')
    with open(os.path.join(lua_dir, filename), 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    matches = pattern.findall(content)
    if not matches: continue
    
    info = get_info(appid)
    if not info: continue
    
    for match in matches:
        depot = match[1]
        old_man = match[2]
        old_size = match[3] if len(match) > 3 else None
        
        public_man = info.get('depots', {}).get(depot, {}).get('manifests', {}).get('public', {})
        api_man = public_man.get('gid')
        api_size = public_man.get('size')
        
        if str(api_man) == old_man and old_size and str(api_size) != old_size:
            mismatches.append(f'{appid}.lua: Depot {depot} size mismatch! Lua={old_size}, API={api_size}')
    
    time.sleep(0.5)

if mismatches:
    print('Found mismatches:')
    print('\n'.join(mismatches))
else:
    print('No mismatches found.')
