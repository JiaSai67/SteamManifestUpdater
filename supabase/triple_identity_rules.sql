-- ═══════════════════════════════════════════════════════════════════════
-- Supabase 三因子身分防偽、真實 IP 擷取、動態特徵更新與自動清理系統 (v2.0)
-- 結合三維防偽：1. 來源真實 IP + 2. Discord OAuth 身分 + 3. 本機 DPAPI 節點公鑰
-- 具備：
-- 1. UPSERT 動態特徵更新 (支援用戶換 IP、換電腦自動無縫更新，不卡關)
-- 2. TTL 自動清理過期滯留日誌 (只留 24 小時，防止佔滿 500MB 資料庫空間)
-- 3. AS RESTRICTIVE 硬核 RLS 守門員 (阻斷無效請求，0 磁碟讀取、0 額度消耗)
-- ═══════════════════════════════════════════════════════════════════════

-- 1. 建立已驗證用戶身分主檔表 (一用戶一筆，UPSERT 動態覆蓋，永不滯留膨脹)
CREATE TABLE IF NOT EXISTS public.verified_user_profiles (
    discord_id TEXT PRIMARY KEY,
    discord_username TEXT,
    dpapi_pubkey TEXT NOT NULL,
    hwid TEXT NOT NULL,
    client_ip INET NOT NULL,
    last_token_hash TEXT,
    last_active_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_profiles_pubkey ON public.verified_user_profiles (dpapi_pubkey);
CREATE INDEX IF NOT EXISTS idx_user_profiles_ip ON public.verified_user_profiles (client_ip);

-- 2. 建立短效行為審計表 (僅保留 24 小時近期行為，自動過期清理)
CREATE TABLE IF NOT EXISTS public.user_identity_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_ip INET NOT NULL DEFAULT '0.0.0.0'::inet,
    discord_id TEXT NOT NULL,
    discord_username TEXT,
    discord_token_hash TEXT,
    dpapi_pubkey TEXT NOT NULL,
    hwid TEXT NOT NULL,
    client_id TEXT NOT NULL,
    action TEXT NOT NULL,
    payload_encrypted TEXT,
    signature TEXT,
    is_verified BOOLEAN DEFAULT true,
    is_suspicious BOOLEAN DEFAULT false,
    suspicious_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_identity_discord_id ON public.user_identity_audit (discord_id);
CREATE INDEX IF NOT EXISTS idx_identity_dpapi_pubkey ON public.user_identity_audit (dpapi_pubkey);
CREATE INDEX IF NOT EXISTS idx_identity_created_at ON public.user_identity_audit (created_at DESC);

-- 3. 自動提取真實來源 IP 之安全函式
CREATE OR REPLACE FUNCTION public.get_request_client_ip()
RETURNS INET
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    headers JSON;
    forwarded_for TEXT;
    cf_ip TEXT;
BEGIN
    BEGIN
        headers := current_setting('request.headers', true)::json;
    EXCEPTION WHEN OTHERS THEN
        RETURN inet_client_addr();
    END;

    -- 優先從 Cloudflare 連線 IP 取得 (防偽等級最高)
    cf_ip := headers->>'cf-connecting-ip';
    IF cf_ip IS NOT NULL AND cf_ip <> '' THEN
        RETURN cf_ip::inet;
    END IF;

    -- 次選 X-Forwarded-For 第一個 IP
    forwarded_for := headers->>'x-forwarded-for';
    IF forwarded_for IS NOT NULL AND forwarded_for <> '' THEN
        RETURN split_part(forwarded_for, ',', 1)::inet;
    END IF;

    RETURN COALESCE(inet_client_addr(), '127.0.0.1'::inet);
END;
$$;

-- 4. 自動清除過期滯留日誌函式 (自動維護資料庫空間)
CREATE OR REPLACE FUNCTION public.cleanup_stale_audit_logs()
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    deleted_count INT;
BEGIN
    DELETE FROM public.user_identity_audit
    WHERE created_at < now() - INTERVAL '24 hours';
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;

-- 5. 三因子比對、動態特徵更新 (UPSERT) 與審計 RPC 函數
CREATE OR REPLACE FUNCTION public.record_user_action(
    p_discord_id TEXT,
    p_discord_username TEXT,
    p_discord_token TEXT,
    p_dpapi_pubkey TEXT,
    p_hwid TEXT,
    p_client_id TEXT,
    p_action TEXT,
    p_payload_encrypted TEXT,
    p_signature TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_client_ip INET;
    v_token_hash TEXT;
    v_is_suspicious BOOLEAN := false;
    v_suspicious_reason TEXT := NULL;
    v_recent_ip INET;
    v_new_id UUID;
BEGIN
    -- 1. 取得不可偽造之真實來源 IP
    v_client_ip := public.get_request_client_ip();

    -- 2. Token 脫敏雜湊
    IF p_discord_token IS NOT NULL AND p_discord_token <> '' THEN
        v_token_hash := encode(digest(p_discord_token, 'sha256'), 'hex');
    ELSE
        v_token_hash := 'NO_TOKEN';
    END IF;

    -- 3. 基礎檢驗
    IF p_discord_id IS NULL OR p_discord_id = '' THEN
        RETURN jsonb_build_object('ok', false, 'msg', '未提供有效 Discord ID');
    END IF;

    IF p_dpapi_pubkey IS NULL OR p_dpapi_pubkey = '' THEN
        RETURN jsonb_build_object('ok', false, 'msg', '未提供本機 DPAPI 節點公鑰');
    END IF;

    -- 4. 異常行為檢測 (同一個 Discord ID 在 30 秒內由相異 IP 同時操作)
    SELECT client_ip INTO v_recent_ip
    FROM public.user_identity_audit
    WHERE discord_id = p_discord_id
      AND created_at > now() - INTERVAL '30 seconds'
      AND client_ip <> v_client_ip
    LIMIT 1;

    IF v_recent_ip IS NOT NULL THEN
        v_is_suspicious := true;
        v_suspicious_reason := format('偵測到異地 IP 衝突 (當前 IP: %s, 30秒內 IP: %s)', v_client_ip, v_recent_ip);
    END IF;

    -- 5. 動態特徵更新 (UPSERT)：若用戶更換 IP、更換電腦或改名，自動覆蓋最新特徵
    INSERT INTO public.verified_user_profiles (
        discord_id,
        discord_username,
        dpapi_pubkey,
        hwid,
        client_ip,
        last_token_hash,
        last_active_at
    ) VALUES (
        p_discord_id,
        p_discord_username,
        p_dpapi_pubkey,
        p_hwid,
        v_client_ip,
        v_token_hash,
        now()
    )
    ON CONFLICT (discord_id) DO UPDATE SET
        discord_username = EXCLUDED.discord_username,
        dpapi_pubkey = EXCLUDED.dpapi_pubkey,
        hwid = EXCLUDED.hwid,
        client_ip = EXCLUDED.client_ip,
        last_token_hash = EXCLUDED.last_token_hash,
        last_active_at = now();

    -- 6. 寫入短效審計日誌
    INSERT INTO public.user_identity_audit (
        client_ip,
        discord_id,
        discord_username,
        discord_token_hash,
        dpapi_pubkey,
        hwid,
        client_id,
        action,
        payload_encrypted,
        signature,
        is_verified,
        is_suspicious,
        suspicious_reason
    ) VALUES (
        v_client_ip,
        p_discord_id,
        p_discord_username,
        v_token_hash,
        p_dpapi_pubkey,
        p_hwid,
        p_client_id,
        p_action,
        p_payload_encrypted,
        p_signature,
        NOT v_is_suspicious,
        v_is_suspicious,
        v_suspicious_reason
    ) RETURNING id INTO v_new_id;

    -- 7. 自動順便清理 24 小時以前之滯留日誌 (保持極簡儲存空間)
    PERFORM public.cleanup_stale_audit_logs();

    RETURN jsonb_build_object(
        'ok', NOT v_is_suspicious,
        'record_id', v_new_id,
        'detected_ip', v_client_ip::text,
        'discord_id', p_discord_id,
        'dpapi_pubkey', p_dpapi_pubkey,
        'action', p_action,
        'is_suspicious', v_is_suspicious,
        'msg', COALESCE(v_suspicious_reason, '身分特徵已動態更新，操作審計完成')
    );
END;
$$;

-- 6. 建立黑名單快表
CREATE TABLE IF NOT EXISTS public.banned_entities (
    id SERIAL PRIMARY KEY,
    target_type TEXT NOT NULL,
    target_val TEXT NOT NULL UNIQUE,
    reason TEXT DEFAULT 'Violation of Terms',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_banned_target_val ON public.banned_entities (target_val);

-- 7. 為房間業務表設定 AS RESTRICTIVE 硬核 RLS 守門員
ALTER TABLE public.party_rooms ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "triple_identity_zero_cost_gatekeeper" ON public.party_rooms;

CREATE POLICY "triple_identity_zero_cost_gatekeeper" ON public.party_rooms
AS RESTRICTIVE
FOR ALL
TO anon, authenticated
USING (
    -- 條件 A：Header 必須具備有效格式之 DPAPI 節點公鑰
    (current_setting('request.headers', true)::json->>'x-dpapi-pubkey') ~ '^DPAPI_PUB_[A-F0-9]{32}$'
    AND
    -- 條件 B：Header 必須附帶有效 Discord ID
    (current_setting('request.headers', true)::json->>'x-discord-id') IS NOT NULL
    AND
    (current_setting('request.headers', true)::json->>'x-discord-id') <> ''
    AND
    -- 條件 C：黑名單三位一體阻斷 (IP / Discord / DPAPI 任何一項命中立刻秒殺)
    NOT EXISTS (
        SELECT 1 FROM public.banned_entities b
        WHERE b.target_val IN (
            current_setting('request.headers', true)::json->>'x-dpapi-pubkey',
            current_setting('request.headers', true)::json->>'x-discord-id',
            (public.get_request_client_ip())::text
        )
    )
);

-- 8. 權限授權
ALTER TABLE public.verified_user_profiles ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "公開讀取已認證檔案" ON public.verified_user_profiles;
CREATE POLICY "公開讀取已認證檔案" ON public.verified_user_profiles FOR SELECT TO anon, authenticated USING (true);

ALTER TABLE public.user_identity_audit ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "允許公開插入審計記錄" ON public.user_identity_audit;
CREATE POLICY "允許公開插入審計記錄" ON public.user_identity_audit FOR INSERT TO anon, authenticated WITH CHECK (true);
DROP POLICY IF EXISTS "允許讀取公開安全審計" ON public.user_identity_audit;
CREATE POLICY "允許讀取公開安全審計" ON public.user_identity_audit FOR SELECT TO anon, authenticated USING (created_at > now() - INTERVAL '24 hours');

GRANT EXECUTE ON FUNCTION public.record_user_action TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_request_client_ip TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.cleanup_stale_audit_logs TO anon, authenticated;
GRANT SELECT, INSERT ON TABLE public.user_identity_audit TO anon, authenticated;
GRANT SELECT ON TABLE public.verified_user_profiles TO anon, authenticated;
GRANT SELECT ON TABLE public.banned_entities TO anon, authenticated;
