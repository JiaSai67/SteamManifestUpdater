-- manifest.lua — depot 清單請求碼 (MRC) 全局多源鏈
-- 隨 OpenSteamTool 載入至 <Steam>/config/lua/manifest.lua
-- 作用：當 Steam 需要下載 depot 清單 (manifest) 時，透過此函式向公共鏡像取得 MRC 通行證。
-- 返回格式：十進位數字字串（例如 "10942715915414605072"），若全部失敗則返回 nil。

function fetch_manifest_code(gid)
    local sources = {
        -- 主源 1：wudrm HTTP (連線極速穩定，約 0.3s 回傳)
        { url = "http://gmrc.wudrm.com/manifest/" .. gid,  json = false },
        -- 主源 2：wudrm HTTPS 備援
        { url = "https://gmrc.wudrm.com/manifest/" .. gid, json = false },
        -- 備源 1：caigamer
        { url = "http://depotcn.caigamer.cn/manifest/" .. gid,  json = false },
        -- 備源 2：steamrun JSON 格式
        { url = "https://manifest.steam.run/api/manifest/" .. gid, json = true },
    }
    for _, s in ipairs(sources) do
        local body, st = http_get(s.url)
        if body and st == 200 then
            if s.json then
                local code = body:match('"content"%s*:%s*"(%d+)"')
                if code then return code end
            else
                local clean = body:match("^%s*(%d+)%s*$")
                if clean then return clean end
            end
        end
    end
    return nil
end
