-- manifest.lua — depot 清单请求码全局兜底（多源链）
-- 随内核注入到 <Steam>/config/lua/manifest.lua（OST 默认目录，启动时与各游戏 lua 一并加载）。
-- 作用：OST 给非自有 depot 要「清单请求码」时，先查本函数；全部源失败返回 nil，
--       才回落 opensteamtool.toml 的 [manifest] url（单一源）。本文件让 3 个源互备，抗单源 429/挂掉。
-- 优先级不变：per-game lua 若自带 fetch_manifest_code_ex，OST 先走它，再走本通用函数。
-- 返回约定：成功 = 十进制数字【字符串】（码 >2^53 时字符串才不丢精度）；失败 = nil。
-- http_get(url) → 成功 (body, 200)；网络失败 (nil, "HTTP request failed")，故判断须 st==200 且 body 非 nil。

function fetch_manifest_code(gid)
    local sources = {
        -- 主：国内直连码源（实测 200 稳）
        { url = "https://depotcn.caigamer.cn/manifest/" .. gid,  json = false },
        -- 备：老源 wudrm（常 429 限流，仅主源挂时兜）
        { url = "http://gmrc.wudrm.com/manifest/" .. gid,       json = false },
        -- 兜：steamrun JSON 格式
        { url = "https://manifest.steam.run/api/manifest/" .. gid, json = true },
    }
    for _, s in ipairs(sources) do
        local body, st = http_get(s.url)
        if body and st == 200 then
            if s.json then
                -- steamrun 返回 {"content":"1666836470726104466"}
                local code = body:match('"content"%s*:%s*"(%d+)"')
                if code then return code end
            else
                -- depotcn / wudrm 返回纯文本数字（容忍首尾空白）
                local clean = body:match("^%s*(%d+)%s*$")
                if clean then return clean end
            end
        end
    end
    return nil
end
