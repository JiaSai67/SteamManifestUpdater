import urllib.request
try:
    req = urllib.request.Request('https://lua.tools/api/manifest/check?appid=4450620', headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        print(response.read().decode('utf-8'))
except Exception as e:
    print(e)
