# -*- coding: utf-8 -*-
"""
SteamManifestUpdater - Dual-Platform Clean Sandbox Login Runner (pywebview 2.0 Native Edition)
雙平台獨立無痕沙盒授權執行器 (基於 Microsoft Edge WebView2 / pywebview 原生內核)

核心特性：
1. 100% 擺脫 PySide6 / Qt C++ 平台外掛依賴，徹底杜絕 Qt Platform Plugin (qwindows.dll) 崩潰與 DLL 搜尋路徑問題。
2. 採用 Windows 10/11 系統內建 Edge WebView2 引擎，輕量秒開，0 依賴衝突。
3. 支援獨立沙盒無痕環境 (private_mode=True / 獨立臨時 Storage)，絕不污染本機瀏覽器現有快取。
4. 內建 Discord RPC 本機探測阻斷 (Block 127.0.0.1:6463)，確保呈現乾淨帳密與手機 QR 碼登入介面。
5. 雙平台自動連貫授權 (先登入 Ryuu 50次/日 -> 同 Session 一鍵跳轉 Lua.tools 25次/日 -> 自動寫入憑證資料庫並完成)。
6. 智慧無感帳密記憶與自動預填：在 Discord 頁面即時捕獲使用者輸入或自動填入本機已保存之安全帳密，並於授權成功時自動覆蓋更新最新憑證。
"""

import os
import sys
import json
import time
import base64
import shutil
import sqlite3
import argparse
import threading
import zlib
from pathlib import Path

# 將 src 目錄置於 sys.path 首位
_src_dir = Path(__file__).resolve().parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

import webview
from managers.account_manager import get_account_manager, _ROOT_DIR


def generate_sandbox_helper_script(auto_email: str = "", auto_pwd: str = "") -> str:
    """
    生成注入沙盒的前端核心腳本：
    1. 阻斷本機 Discord RPC (6463) 探測
    2. 即時動態捕獲使用者在登入框輸入/修改的帳號密碼
    3. 若本機已有儲存帳密，自動使用 React 原生 Setter 預填入輸入框
    4. 頂部常駐全域多功能導航列 (步驟指示、加入 Discord 伺服器、返回授權頁、跳過前往下一步、立即儲存)
    5. 自動偵測 Ryuu 與 Hubcap 未加入伺服器錯誤，並自動導向官方邀請連結
    """
    js_email = json.dumps(auto_email or "")
    js_pwd = json.dumps(auto_pwd or "")

    template = r'''
    (function() {
        // 1. 初始化全域狀態容器
        if (!window._captured_creds) {
            window._captured_creds = {
                email: '',
                password: '',
                last_updated: 0
            };
        }

        // 2. 阻斷 Discord RPC 探測 (防止直接讀取本機桌面版 Discord)
        if (!window._sandbox_rpc_blocked) {
            window._sandbox_rpc_blocked = true;
            
            var origFetch = window.fetch;
            if (origFetch) {
                window.fetch = function(url, opts) {
                    var urlStr = (typeof url === 'string') ? url : (url && url.url ? url.url : '');
                    if (urlStr && (urlStr.indexOf('127.0.0.1') !== -1 || urlStr.indexOf('localhost') !== -1) && (urlStr.indexOf('6463') !== -1 || urlStr.indexOf('rpc') !== -1)) {
                        return Promise.reject(new Error('Blocked local Discord RPC probe'));
                    }
                    return origFetch.apply(this, arguments);
                };
            }

            var origOpen = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function(method, url) {
                var urlStr = (typeof url === 'string') ? url : '';
                if (urlStr && (urlStr.indexOf('127.0.0.1') !== -1 || urlStr.indexOf('localhost') !== -1) && (urlStr.indexOf('6463') !== -1 || urlStr.indexOf('rpc') !== -1)) {
                    this.abort();
                    return;
                }
                return origOpen.apply(this, arguments);
            };

            var OrigWS = window.WebSocket;
            if (OrigWS) {
                window.WebSocket = function(url, protocols) {
                    var urlStr = (typeof url === 'string') ? url : '';
                    if (urlStr && (urlStr.indexOf('127.0.0.1') !== -1 || urlStr.indexOf('localhost') !== -1)) {
                        throw new Error('Blocked local Discord WebSocket');
                    }
                    return new OrigWS(url, protocols);
                };
            }
        }

        // 3. 帳密即時動態捕獲函數
        function captureFromInput(input) {
            if (!input) return;
            var val = input.value || '';
            if (!val) return;
            var type = (input.type || '').toLowerCase();
            var name = (input.name || '').toLowerCase();
            var ac = (input.getAttribute('autocomplete') || '').toLowerCase();

            if (type === 'password' || name.indexOf('password') !== -1 || ac.indexOf('password') !== -1) {
                window._captured_creds.password = val;
                window._captured_creds.last_updated = Date.now();
            } else if (type === 'email' || name.indexOf('email') !== -1 || name.indexOf('login') !== -1 || ac.indexOf('email') !== -1 || ac.indexOf('username') !== -1 || type === 'text') {
                if (val.indexOf('@') !== -1 || type === 'email' || name.indexOf('email') !== -1 || name.indexOf('login') !== -1) {
                    window._captured_creds.email = val;
                    window._captured_creds.last_updated = Date.now();
                }
            }
        }

        if (!window._credential_listeners_attached) {
            window._credential_listeners_attached = true;
            
            ['input', 'change', 'blur', 'keyup'].forEach(function(evtName) {
                document.addEventListener(evtName, function(e) {
                    if (e && e.target && e.target.tagName === 'INPUT') {
                        captureFromInput(e.target);
                    }
                }, true);
            });

            ['click', 'submit'].forEach(function(evtName) {
                document.addEventListener(evtName, function(e) {
                    var inputs = document.querySelectorAll('input');
                    for (var i = 0; i < inputs.length; i++) {
                        captureFromInput(inputs[i]);
                    }
                }, true);
            });
        }

        // 4. React 深度輸入框安全賦值器
        var autoEmail = __AUTO_EMAIL__;
        var autoPwd = __AUTO_PWD__;

        function fillReactInput(el, value) {
            if (!el || !value) return false;
            if (el.value === value) return true;
            try {
                var valSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
                if (valSetter && valSetter.set) {
                    valSetter.set.call(el, value);
                } else {
                    el.value = value;
                }
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new Event('blur', { bubbles: true }));
                return true;
            } catch(e) {
                try {
                    el.value = value;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                } catch(err) {}
            }
            return false;
        }

        // 5. Discord 登入介面自動預填
        if (window.location.hostname.indexOf('discord.com') !== -1) {
            var emailInput = document.querySelector('input[name="email"], input[type="email"], input[name="login"], input[autocomplete="email"], input[autocomplete="username"]');
            var pwdInput = document.querySelector('input[name="password"], input[type="password"], input[autocomplete="current-password"]');

            var filledAny = false;
            if (emailInput && autoEmail && (!emailInput.value || emailInput.value === '')) {
                fillReactInput(emailInput, autoEmail);
                window._captured_creds.email = autoEmail;
                filledAny = true;
            }
            if (pwdInput && autoPwd && (!pwdInput.value || pwdInput.value === '')) {
                fillReactInput(pwdInput, autoPwd);
                window._captured_creds.password = autoPwd;
                filledAny = true;
            }

            if (filledAny && !document.getElementById('_sm_autofill_badge')) {
                var badge = document.createElement('div');
                badge.id = '_sm_autofill_badge';
                badge.style.cssText = 'position:fixed;top:54px;left:50%;transform:translateX(-50%);background:linear-gradient(135deg, #10b981, #059669);color:#ffffff;padding:8px 18px;border-radius:24px;font-size:13px;font-weight:bold;box-shadow:0 6px 20px rgba(0,0,0,0.35);z-index:999999;pointer-events:none;transition:opacity 0.6s ease;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;display:flex;align-items:center;gap:6px;';
                badge.innerHTML = '<span>⚡</span> <span>已為您自動填入已記憶之帳號密碼，請確認後手動點擊「登入」</span>';
                document.body.appendChild(badge);
                setTimeout(function() {
                    if (badge) {
                        badge.style.opacity = '0';
                        setTimeout(function() { if (badge && badge.parentNode) badge.parentNode.removeChild(badge); }, 600);
                    }
                }, 5000);
            }
        }

        // 6. 頂部常駐全域多功能導航列 (Navbar)
        function renderTopNavbar() {
            var curStep = window._sm_current_step || 1;
            var nav = document.getElementById('_sm_top_navbar');
            if (!nav) {
                nav = document.createElement('div');
                nav.id = '_sm_top_navbar';
                nav.style.cssText = 'position:fixed!important;top:0!important;left:0!important;right:0!important;height:42px!important;background:rgba(20,20,24,0.96)!important;backdrop-filter:blur(10px)!important;border-bottom:1px solid rgba(255,255,255,0.12)!important;z-index:2147483647!important;display:flex!important;align-items:center!important;justify-content:space-between!important;padding:0 14px!important;box-shadow:0 3px 14px rgba(0,0,0,0.45)!important;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif!important;user-select:none!important;box-sizing:border-box!important;';
                document.body.appendChild(nav);

                // 為 body 添加 padding 避免遮蓋頁面頂端
                if (document.body && !document.body.getAttribute('data-sm-nav-pad')) {
                    document.body.setAttribute('data-sm-nav-pad', 'true');
                    document.body.style.setProperty('padding-top', '44px', 'important');
                }
            }

            var stepText = '🐉 步驟 1/3：Ryuu (50次/日)';
            var stepColor = '#10b981';
            var showRyuuBtn = false;
            var showHcBtn = false;
            var nextStepText = '⏩ 跳過 Ryuu，前往步驟 2 (Lua.tools)';

            if (curStep === 1) {
                stepText = '🐉 步驟 1/3：Ryuu 授權 (50次/日)';
                stepColor = '#10b981';
                showRyuuBtn = true;
                nextStepText = '⏩ 跳過 Ryuu，前往步驟 2 (Lua.tools)';
            } else if (curStep === 2) {
                stepText = '🛠️ 步驟 2/3：Lua.tools 授權 (25次/日)';
                stepColor = '#6366f1';
                nextStepText = '⏩ 跳過 Lua，前往步驟 3 (HubcapDB)';
            } else if (curStep === 3) {
                stepText = '🧢 步驟 3/3：HubcapDB 授權 (25次/日)';
                stepColor = '#06b6d4';
                showHcBtn = true;
                nextStepText = '✅ 完成並關閉沙盒';
            }

            nav.innerHTML = `
                <div style="display:flex;align-items:center;gap:10px;">
                    <div style="background:rgba(255,255,255,0.08);border:1px solid ${stepColor};color:#ffffff;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;display:flex;align-items:center;gap:6px;">
                        <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${stepColor};box-shadow:0 0 6px ${stepColor};"></span>
                        <span>${stepText}</span>
                    </div>
                    <span id="_sm_nav_msg" style="color:#e4e4e7;font-size:12px;font-weight:500;"></span>
                </div>
                <div style="display:flex;align-items:center;gap:8px;">
                    ${showRyuuBtn ? '<button id="_sm_nav_btn_ryuu" style="background:#5865F2;color:#ffffff;border:none;padding:5px 11px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:5px;box-shadow:0 2px 8px rgba(88,101,242,0.4);"><span>💬</span><span>加入 Ryuu 伺服器</span></button>' : ''}
                    ${showHcBtn ? '<button id="_sm_nav_btn_hc" style="background:#5865F2;color:#ffffff;border:none;padding:5px 11px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:5px;box-shadow:0 2px 8px rgba(88,101,242,0.4);"><span>💬</span><span>加入 Hubcap 伺服器</span></button>' : ''}
                    <button id="_sm_nav_btn_reload" style="background:#27272a;color:#f4f4f5;border:1px solid #3f3f46;padding:5px 11px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:5px;"><span>🔙</span><span>返回授權頁</span></button>
                    <button id="_sm_nav_btn_skip" style="background:rgba(245,158,11,0.15);color:#fbbf24;border:1px solid rgba(245,158,11,0.4);padding:5px 11px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:5px;"><span>${nextStepText}</span></button>
                    <button id="_sm_nav_btn_save" style="background:linear-gradient(135deg,#10b981,#059669);color:#ffffff;border:none;padding:5px 12px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:5px;box-shadow:0 2px 8px rgba(16,185,129,0.35);"><span>⚡</span><span>立即儲存</span></button>
                </div>
            `;

            var ryuuBtn = document.getElementById('_sm_nav_btn_ryuu');
            if (ryuuBtn) {
                ryuuBtn.onclick = function() {
                    window._action_join_ryuu = true;
                    window.location.href = "https://discord.com/invite/manifests";
                };
            }

            var hcBtn = document.getElementById('_sm_nav_btn_hc');
            if (hcBtn) {
                hcBtn.onclick = function() {
                    window._action_join_hubcap = true;
                    window.location.href = "https://discord.gg/hubcapsmanifest";
                };
            }

            var reloadBtn = document.getElementById('_sm_nav_btn_reload');
            if (reloadBtn) {
                reloadBtn.onclick = function() {
                    window._action_reload_step = true;
                };
            }

            var skipBtn = document.getElementById('_sm_nav_btn_skip');
            if (skipBtn) {
                skipBtn.onclick = function() {
                    window._action_skip_step = true;
                    skipBtn.innerHTML = '<span>⏳ 正在切換步驟...</span>';
                };
            }

            var saveBtn = document.getElementById('_sm_nav_btn_save');
            if (saveBtn) {
                saveBtn.onclick = function() {
                    window._manual_save_requested = true;
                    saveBtn.innerHTML = '<span>⏳ 正在儲存...</span>';
                };
            }
        }
        renderTopNavbar();

        // 7. Lua.tools 無縫過渡：隱藏前端首頁並直接跳轉至 Discord 授權頁面
        if (window.location.hostname.indexOf('lua.tools') !== -1) {
            // 立即注入全螢幕暗色遮罩，完全遮蔽 Lua.tools 首頁
            if (!document.getElementById('_sm_lt_seamless_mask')) {
                var mask = document.createElement('div');
                mask.id = '_sm_lt_seamless_mask';
                mask.style.cssText = 'position:fixed!important;top:42px!important;left:0!important;right:0!important;bottom:0!important;background:#090d16!important;z-index:2147483640!important;display:flex!important;flex-direction:column!important;align-items:center!important;justify-content:center!important;color:#ffffff!important;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif!important;user-select:none!important;';
                mask.innerHTML = '<div style="width:36px;height:36px;border:3px solid rgba(99,102,241,0.25);border-top-color:#6366f1;border-radius:50%;animation:_sm_spin 0.8s linear infinite;margin-bottom:16px;"></div>' +
                                 '<div style="font-size:16px;font-weight:600;color:#818cf8;margin-bottom:6px;">🛠️ 正在為您連接 Lua.tools 專屬授權通道...</div>' +
                                 '<div style="font-size:13px;color:#94a3b8;">即刻為您載入 Discord 授權頁面，請稍候</div>' +
                                 '<style>@keyframes _sm_spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}</style>';
                document.body.appendChild(mask);
            }

            // 高頻輪詢並秒速點擊 Login with Discord 按鈕
            if (!window._lt_auto_clicked) {
                var clickLt = function() {
                    var btns = document.querySelectorAll('button, a');
                    for (var i = 0; i < btns.length; i++) {
                        var t = (btns[i].textContent || '').toLowerCase().trim();
                        if (t.indexOf('login with discord') !== -1 || (t.indexOf('login') !== -1 && t.indexOf('discord') !== -1)) {
                            window._lt_auto_clicked = true;
                            try { btns[i].click(); } catch(e){}
                            return true;
                        }
                    }
                    var sel = document.querySelector('button.login-btn, a[href*="login"], a[href*="discord"], button[class*="discord"]');
                    if (sel) {
                        window._lt_auto_clicked = true;
                        try { sel.click(); } catch(e){}
                        return true;
                    }
                    return false;
                };
                clickLt();
                var ltTimer = setInterval(function() {
                    if (clickLt() || window._lt_auto_clicked) clearInterval(ltTimer);
                }, 50);
            }
        }

        // 8. Discord 伺服器加入成功即時監聽：點擊接受邀請進入頻道後，自動導回對應平台完成授權
        if (window.location.hostname.indexOf('discord.com') !== -1) {
            var isChannelPage = window.location.pathname.indexOf('/channels/') !== -1;
            if (isChannelPage) {
                var curStep = window._sm_current_step || 1;
                if (curStep === 1 && !window._redirecting_step1_success) {
                    window._redirecting_step1_success = true;
                    var msgEl = document.getElementById('_sm_nav_msg');
                    if (msgEl) {
                        msgEl.innerHTML = '<span style="color:#10b981;font-weight:bold;">🎉 成功加入 Ryuu 伺服器！正在自動返回完成登入...</span>';
                    }
                    setTimeout(function() {
                        window.location.href = "https://generator.ryuu.lol/login";
                    }, 600);
                } else if (curStep === 3 && !window._redirecting_step3_success) {
                    window._redirecting_step3_success = true;
                    var msgEl = document.getElementById('_sm_nav_msg');
                    if (msgEl) {
                        msgEl.innerHTML = '<span style="color:#10b981;font-weight:bold;">🎉 成功加入 Hubcap 伺服器！正在自動返回完成登入...</span>';
                    }
                    setTimeout(function() {
                        window.location.href = "https://hubcapmanifest.com/auth/discord";
                    }, 600);
                }
            }
        }

        // 9. 伺服器未加入錯誤即時偵測與自動跳轉
        var bodyTxt = document.body ? (document.body.innerText || '') : '';
        var isRyuu = window.location.hostname.indexOf('ryuu.lol') !== -1;
        var isHc = window.location.hostname.indexOf('hubcapmanifest.com') !== -1 || bodyTxt.indexOf('You must be a member of our Discord server') !== -1;

        // 檢查 Ryuu 未加入伺服器提示
        if (isRyuu) {
            var needRyuuJoin = bodyTxt.indexOf('You must join the Discord server') !== -1 ||
                               bodyTxt.indexOf('discord.gg/manifests') !== -1 ||
                               bodyTxt.indexOf('join the Discord server to use this site') !== -1;
            if (needRyuuJoin) {
                window._needs_join_ryuu_detected = true;
                var msgEl = document.getElementById('_sm_nav_msg');
                if (msgEl) {
                    msgEl.innerHTML = '<span style="color:#ef4444;font-weight:bold;">⚠️ 帳號尚未加入 Ryuu 伺服器！已準備跳轉邀請連結...</span>';
                }
                if (!window._ryuu_invite_auto_redirected) {
                    window._ryuu_invite_auto_redirected = true;
                    window._action_join_ryuu = true;
                    setTimeout(function() {
                        window.location.href = "https://discord.com/invite/manifests";
                    }, 400);
                }
            }
        }

        // 檢查 Hubcap 未加入伺服器提示 (精確支援圖一之 JSON 與各類報錯文字)
        if (isHc) {
            var needHcJoin = bodyTxt.indexOf('You must be a member of our Discord server') !== -1 ||
                             bodyTxt.indexOf('member of our Discord server to access this application') !== -1 ||
                             bodyTxt.indexOf('hubcapsmanifest') !== -1 ||
                             (bodyTxt.indexOf('Discord server') !== -1 && (bodyTxt.indexOf('member') !== -1 || bodyTxt.indexOf('access') !== -1));
            if (needHcJoin) {
                window._needs_join_hc_detected = true;
                var msgEl = document.getElementById('_sm_nav_msg');
                if (msgEl) {
                    msgEl.innerHTML = '<span style="color:#ef4444;font-weight:bold;">⚠️ 帳號尚未加入 Hubcap 伺服器！已準備跳轉邀請連結...</span>';
                }
                if (!window._hc_invite_auto_redirected) {
                    window._hc_invite_auto_redirected = true;
                    window._action_join_hubcap = true;
                    setTimeout(function() {
                        window.location.href = "https://discord.com/invite/hubcapsmanifest";
                    }, 400);
                }
            }
        }

    })();
    '''

    return template.replace("__AUTO_EMAIL__", js_email).replace("__AUTO_PWD__", js_pwd)



def extract_cookies_dict(cookie_objs):
    """
    將 pywebview 回傳的 Cookie 列表 (SimpleCookie, dict 或自定義物件) 統一轉換為標準結構化清單
    修正重點：SimpleCookie 繼承自 dict，但 keys 為 cookie 名稱，故必須優先以 items() 提取！
    """
    result = []
    if not cookie_objs:
        return result
    for ck in cookie_objs:
        if ck is None:
            continue
        
        # 1. 優先處理 SimpleCookie (含 items 疊代器)
        if hasattr(ck, "items") and (type(ck).__name__ == "SimpleCookie" or not isinstance(ck, dict) or "items" in dir(ck)):
            for k, morsel in ck.items():
                dom = ""
                try:
                    if hasattr(morsel, "__getitem__") and "domain" in morsel:
                        dom = morsel["domain"]
                except Exception:
                    pass
                val = getattr(morsel, "value", str(morsel))
                result.append({
                    "name": k,
                    "value": val,
                    "domain": dom or ""
                })
        # 2. 處理原生 dict ({'name': ..., 'value': ..., 'domain': ...})
        elif isinstance(ck, dict) and "name" in ck:
            result.append({
                "name": ck.get("name", ""),
                "value": ck.get("value", ""),
                "domain": ck.get("domain", "") or ""
            })
        # 3. 處理具有屬性的物件 (.name, .value, .domain)
        else:
            name = getattr(ck, 'name', '') or getattr(ck, 'key', '') or getattr(ck, 'Name', '')
            val = getattr(ck, 'value', '') or getattr(ck, 'Value', '')
            dom = getattr(ck, 'domain', '') or getattr(ck, 'Domain', '')
            if name:
                result.append({
                    "name": name,
                    "value": val,
                    "domain": dom or ""
                })
    return result


def decode_flask_session(session_val: str) -> dict:
    """
    安全解碼 Flask Signed Session Cookie 負載：
    支援 Base64 解碼與 zlib 壓縮還原 (適用於以點號 . 開頭的壓縮 Cookie 或 eyJ 開頭的 JSON)
    """
    if not session_val or len(session_val) < 8:
        return {}
    try:
        parts = session_val.split(".")
        payload = parts[1] if session_val.startswith(".") else parts[0]
        padding = "=" * ((4 - len(payload) % 4) % 4)
        raw = base64.urlsafe_b64decode(payload + padding)
        try:
            raw = zlib.decompress(raw)
        except Exception:
            pass
        return json.loads(raw.decode("utf-8", errors="ignore"))
    except Exception:
        return {}


def save_ryuu_cookies(c_file: Path, session_val: str, cookie_objs=None):
    """將 Ryuu 的 Session 與所有相關 Cookie 完整存入 SQLite"""
    try:
        c_file.parent.mkdir(parents=True, exist_ok=True)
        now_epoch = int((time.time() + 11644473600) * 1000000)
        conn = sqlite3.connect(c_file)
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS cookies (
                creation_utc INTEGER NOT NULL, host_key TEXT NOT NULL, top_frame_site_key TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL, value TEXT NOT NULL, encrypted_value BLOB NOT NULL DEFAULT '',
                path TEXT NOT NULL DEFAULT '/', expires_utc INTEGER NOT NULL DEFAULT 0,
                is_secure INTEGER NOT NULL DEFAULT 1, is_httponly INTEGER NOT NULL DEFAULT 1,
                last_access_utc INTEGER NOT NULL DEFAULT 0, has_expires INTEGER NOT NULL DEFAULT 0,
                is_persistent INTEGER NOT NULL DEFAULT 1, priority INTEGER NOT NULL DEFAULT 1,
                samesite INTEGER NOT NULL DEFAULT -1, source_scheme INTEGER NOT NULL DEFAULT 2,
                source_port INTEGER NOT NULL DEFAULT 443, is_same_party INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (host_key, top_frame_site_key, name, path, source_port)
            )
        ''')

        # 1. 寫入 session cookie 至各個常見網域變體
        if session_val:
            for host in ["generator.ryuu.lol", ".generator.ryuu.lol", ".ryuu.lol", "ryuu.lol"]:
                cur.execute('''
                    INSERT OR REPLACE INTO cookies (creation_utc, host_key, name, value, path, is_secure, is_httponly, is_persistent)
                    VALUES (?, ?, 'session', ?, '/', 1, 1, 1)
                ''', (now_epoch, host, session_val))

        # 2. 寫入 get_cookies 取得的所有 Cookie (包含 Cloudflare clearance, tokens 等)
        if cookie_objs:
            parsed = extract_cookies_dict(cookie_objs)
            for ck in parsed:
                c_name = ck.get('name', '')
                c_val = ck.get('value', '')
                c_domain = ck.get('domain', '') or 'generator.ryuu.lol'
                if c_name and c_val:
                    cur.execute('''
                        INSERT OR REPLACE INTO cookies (creation_utc, host_key, name, value, path, is_secure, is_httponly, is_persistent)
                        VALUES (?, ?, ?, ?, '/', 1, 1, 1)
                    ''', (now_epoch, c_domain, c_name, c_val))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Sandbox] Save ryuu cookies error: {e}")


def save_luatools_cookies(c_file: Path, raw_cookie_str: str, raw_local_str: str, cookie_objs=None):
    """將 Lua.tools 的 Cookie 與 LocalStorage 完整存入 SQLite"""
    try:
        c_file.parent.mkdir(parents=True, exist_ok=True)
        now_epoch = int((time.time() + 11644473600) * 1000000)
        conn = sqlite3.connect(c_file)
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS cookies (
                creation_utc INTEGER NOT NULL, host_key TEXT NOT NULL, top_frame_site_key TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL, value TEXT NOT NULL, encrypted_value BLOB NOT NULL DEFAULT '',
                path TEXT NOT NULL DEFAULT '/', expires_utc INTEGER NOT NULL DEFAULT 0,
                is_secure INTEGER NOT NULL DEFAULT 1, is_httponly INTEGER NOT NULL DEFAULT 1,
                last_access_utc INTEGER NOT NULL DEFAULT 0, has_expires INTEGER NOT NULL DEFAULT 0,
                is_persistent INTEGER NOT NULL DEFAULT 1, priority INTEGER NOT NULL DEFAULT 1,
                samesite INTEGER NOT NULL DEFAULT -1, source_scheme INTEGER NOT NULL DEFAULT 2,
                source_port INTEGER NOT NULL DEFAULT 443, is_same_party INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (host_key, top_frame_site_key, name, path, source_port)
            )
        ''')

        # 1. 寫入 document.cookie
        if raw_cookie_str:
            for pair in raw_cookie_str.split(";"):
                if "=" in pair:
                    k, v = pair.strip().split("=", 1)
                    if "sb-db-auth-token" in k or "auth" in k:
                        cur.execute('''
                            INSERT OR REPLACE INTO cookies (creation_utc, host_key, name, value, path, is_secure, is_httponly, is_persistent)
                            VALUES (?, 'lua.tools', ?, ?, '/', 1, 1, 1)
                        ''', (now_epoch, k, v))

        # 2. 寫入 get_cookies 取得的物件
        if cookie_objs:
            parsed = extract_cookies_dict(cookie_objs)
            for ck in parsed:
                c_name = ck.get('name', '')
                c_val = ck.get('value', '')
                c_domain = ck.get('domain', '') or 'lua.tools'
                if c_name and ("sb-" in c_name or "auth" in c_name or "token" in c_name or "cf_" in c_name):
                    cur.execute('''
                        INSERT OR REPLACE INTO cookies (creation_utc, host_key, name, value, path, is_secure, is_httponly, is_persistent)
                        VALUES (?, ?, ?, ?, '/', 1, 1, 1)
                    ''', (now_epoch, c_domain, c_name, c_val))

        # 3. 如果 LocalStorage 內有 Supabase Token，切片轉存為 base64 Cookie
        if raw_local_str:
            raw_b64 = "base64-" + base64.b64encode(raw_local_str.encode("utf-8")).decode("utf-8")
            part0 = raw_b64[:3180]
            part1 = raw_b64[3180:]
            cur.execute('''
                INSERT OR REPLACE INTO cookies (creation_utc, host_key, name, value, path, is_secure, is_httponly, is_persistent)
                VALUES (?, 'lua.tools', 'sb-db-auth-token.0', ?, '/', 1, 1, 1)
            ''', (now_epoch, part0))
            if part1:
                cur.execute('''
                    INSERT OR REPLACE INTO cookies (creation_utc, host_key, name, value, path, is_secure, is_httponly, is_persistent)
                    VALUES (?, 'lua.tools', 'sb-db-auth-token.1', ?, '/', 1, 1, 1)
                ''', (now_epoch, part1))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Sandbox] Save luatools cookies error: {e}")


def run_sandbox(target_platform: str = "all", target_account_id: str = None):
    mgr = get_account_manager()
    mgr.reload_data()
    plat_raw = str(target_platform or "all").lower().strip()
    if plat_raw in ["lua_tools", "luatools"]:
        plat = "lua_tools"
    elif plat_raw in ["hubcap", "hubcapdb"]:
        plat = "hubcap"
    elif plat_raw == "ryuu":
        plat = "ryuu"
    else:
        plat = "all"

    # 檢索已儲存的帳密
    saved_creds = mgr.get_account_credentials(account_id=target_account_id)
    auto_email = saved_creds.get("email", "")
    auto_pwd = saved_creds.get("password", "")

    if auto_email:
        try:
            print(f"[Sandbox] [Auth] 已載入帳號已記憶資訊: {auto_email} (密碼: {'*' * len(auto_pwd) if auto_pwd else '無'})")
        except Exception:
            pass

    # 設定初始標題與網址
    if plat == "ryuu":
        init_title = "🛡️ Ryuu 專屬安全無痕授權沙盒 (50次/日)"
        init_url = "https://generator.ryuu.lol/login"
        initial_step = 1
    elif plat == "lua_tools":
        init_title = "🛡️ Lua.tools 專屬安全無痕授權沙盒 (25次/日)"
        init_url = "https://lua.tools/"
        initial_step = 2
    elif plat == "hubcap":
        init_title = "🛡️ HubcapDB 專屬安全無痕授權沙盒 (25次/日 · 自動獲取 API Key)"
        init_url = "https://hubcapmanifest.com/auth/discord"
        initial_step = 3
    else:
        init_title = "🛡️ 三平台安全無痕連貫授權沙盒 (Ryuu 50次 + Lua 25次 + Hubcap 25次 · 總計 100次/日)"
        init_url = "https://generator.ryuu.lol/login"
        initial_step = 1

    # 建立獨立暫存目錄
    import uuid
    session_id = uuid.uuid4().hex[:8]
    sandbox_storage = _ROOT_DIR / "data" / "credentials" / f"webview_sandbox_{session_id}"
    sandbox_storage.mkdir(parents=True, exist_ok=True)

    window = webview.create_window(
        title=init_title,
        url=init_url,
        width=1060,
        height=820,
        min_size=(880, 640),
        on_top=False
    )

    # 監控狀態
    state = {
        "step": initial_step,
        "target_platform": plat,
        "is_saving": False,
        "ryuu_done": False,
        "lt_done": False,
        "hubcap_done": False,
        "ryuu_info": {},
        "target_account_id": target_account_id,
        "captured_email": auto_email,
        "captured_pwd": auto_pwd,
        "closed": False
    }

    # 動態注入腳本
    helper_script = generate_sandbox_helper_script(auto_email, auto_pwd)

    def background_monitor():
        time.sleep(1.0)
        while not state["closed"]:
            try:
                # 注入目前步驟進度給前端導航列
                try:
                    window.evaluate_js(f"window._sm_current_step = {state['step']};")
                except Exception:
                    pass

                # 注入 RPC 阻斷與即時捕獲/預填腳本
                try:
                    window.evaluate_js(helper_script)
                except Exception:
                    pass

                # 即時提取前端捕獲的帳號與密碼
                try:
                    cap_json = window.evaluate_js("JSON.stringify(window._captured_creds || {})")
                    if cap_json:
                        cap_data = json.loads(cap_json) if isinstance(cap_json, str) else cap_data
                        if cap_data.get("email"):
                            state["captured_email"] = cap_data["email"].strip()
                        if cap_data.get("password"):
                            state["captured_pwd"] = cap_data["password"]
                except Exception:
                    pass

                # 檢查是否觸發手動儲存按鈕
                manual_save = False
                try:
                    manual_save = bool(window.evaluate_js("Boolean(window._manual_save_requested)"))
                except Exception:
                    pass

                # ── 全域導航列事件監聽 ──
                # 1. 加入 Ryuu Discord 伺服器
                try:
                    if bool(window.evaluate_js("Boolean(window._action_join_ryuu)")):
                        window.evaluate_js("window._action_join_ryuu = false;")
                        print("[Sandbox] 正在導向 Ryuu 官方 Discord 伺服器邀請 (discord.com/invite/manifests)...")
                        window.load_url("https://discord.com/invite/manifests")
                        time.sleep(1.0)
                        continue
                except Exception:
                    pass

                # 2. 加入 Hubcap Discord 伺服器
                try:
                    if bool(window.evaluate_js("Boolean(window._action_join_hubcap)")):
                        window.evaluate_js("window._action_join_hubcap = false;")
                        print("[Sandbox] 正在導向 Hubcap 官方 Discord 伺服器邀請 (discord.com/invite/hubcapsmanifest)...")
                        window.load_url("https://discord.com/invite/hubcapsmanifest")
                        time.sleep(1.0)
                        continue
                except Exception:
                    pass

                # 2.5 監聽是否已在 Discord 成功接受邀請並進入伺服器頻道
                try:
                    cur_url = str(window.get_current_url() or "")
                    if "discord.com/channels/" in cur_url:
                        if state["step"] == 1 and not state.get("ryuu_reloaded_after_join"):
                            state["ryuu_reloaded_after_join"] = True
                            print("[Sandbox] 偵測到使用者已成功加入 Ryuu 伺服器，自動導回 Ryuu 登入頁完成授權...")
                            window.load_url("https://generator.ryuu.lol/login")
                            time.sleep(1.2)
                            continue
                        elif state["step"] == 3 and not state.get("hc_reloaded_after_join"):
                            state["hc_reloaded_after_join"] = True
                            print("[Sandbox] 偵測到使用者已成功加入 Hubcap 伺服器，自動導回 Hubcap 登入頁完成授權...")
                            window.load_url("https://hubcapmanifest.com/auth/discord")
                            time.sleep(1.2)
                            continue
                except Exception:
                    pass

                # 3. 返回授權起始頁
                try:
                    if bool(window.evaluate_js("Boolean(window._action_reload_step)")):
                        window.evaluate_js("window._action_reload_step = false;")
                        if state["step"] == 1:
                            print("[Sandbox] 正在重新載入 Ryuu 授權起始頁...")
                            window.load_url("https://generator.ryuu.lol/login")
                        elif state["step"] == 2:
                            print("[Sandbox] 正在重新載入 Lua.tools 首頁...")
                            window.load_url("https://lua.tools/")
                        elif state["step"] == 3:
                            print("[Sandbox] 正在重新載入 Hubcap 授權頁...")
                            window.load_url("https://hubcapmanifest.com/auth/discord")
                        time.sleep(1.0)
                        continue
                except Exception:
                    pass

                # 4. 手動跳過當前步驟 (前往下一平台)
                try:
                    if bool(window.evaluate_js("Boolean(window._action_skip_step)")):
                        window.evaluate_js("window._action_skip_step = false;")
                        if state["step"] == 1:
                            print("[Sandbox] 使用者手動跳過 Ryuu，推進至步驟 2 (Lua.tools)...")
                            state["step"] = 2
                            state["is_saving"] = False
                            window.set_title("🛡️ [步驟 2/3] Lua.tools 專屬安全無痕授權沙盒 (25次/日) · 請點擊授權")
                            window.load_url("https://lua.tools/")
                            time.sleep(1.2)
                            continue
                        elif state["step"] == 2:
                            print("[Sandbox] 使用者手動跳過 Lua.tools，推進至步驟 3 (HubcapDB)...")
                            state["step"] = 3
                            state["is_saving"] = False
                            window.set_title("🛡️ [步驟 3/3] HubcapDB 專屬安全無痕授權沙盒 (25次/日) · 請確認授權以自動獲取 API Key")
                            window.load_url("https://hubcapmanifest.com/auth/discord")
                            time.sleep(1.2)
                            continue
                        elif state["step"] == 3:
                            print("[Sandbox] 使用者點擊完成/結束沙盒視窗。")
                            window.destroy()
                            return
                except Exception:
                    pass

                # ── 步驟 1：Ryuu 平台檢查 ──
                if state["step"] == 1 and not state["is_saving"]:
                    js_ryuu = """
                    (function() {
                        var isRyuu = window.location.hostname.indexOf('ryuu.lol') !== -1;
                        var isLogin = window.location.pathname.indexOf('/login') !== -1;
                        var isHome = isRyuu && (window.location.pathname === '/' || window.location.pathname === '');
                        
                        // 自動輔助點擊登入按鈕 (若在 /login 頁面)
                        if (isLogin) {
                            var loginBtn = document.querySelector('a[href*="discord"], a[href*="login"], button.login-btn, a.btn');
                            if (loginBtn && !window._clicked_ryuu_login) {
                                window._clicked_ryuu_login = true;
                                setTimeout(function() { try { loginBtn.click(); } catch(e){} }, 400);
                            }
                        }

                        var bodyText = document.body ? (document.body.innerText || '') : '';
                        var dlMatch = bodyText.match(/(\\d+)\\s+downloads?\\s+left/i);
                        var dlNum = dlMatch ? parseInt(dlMatch[1]) : null;

                        var dlEl = document.getElementById('downloads-left');
                        if (dlNum === null && dlEl) {
                            var n = parseInt(dlEl.textContent.trim());
                            if (!isNaN(n)) dlNum = n;
                        }

                        var hasAvatar = document.querySelector('img[src*="discordapp"], img[src*="avatars"], img[alt*="avatar"]') !== null;
                        var hasSearch = document.querySelector('input[placeholder*="App ID"], input[placeholder*="search"]') !== null;
                        var hasLogout = document.querySelector('a[href*="logout"], button[class*="logout"]') !== null;
                        var hasProfile = document.getElementById('profile-menu') !== null || document.getElementById('profile-container') !== null;
                        
                        var needsJoinServer = isRyuu && (
                            bodyText.indexOf('You must join the Discord server') !== -1 ||
                            bodyText.indexOf('discord.gg/manifests') !== -1 ||
                            bodyText.indexOf('join the Discord server to use this site') !== -1
                        );

                        var isUiLoggedIn = isHome && (dlNum !== null || hasAvatar || hasSearch || hasLogout || hasProfile);

                        return JSON.stringify({
                            is_ryuu: isRyuu,
                            is_login_page: isLogin,
                            is_home: isHome,
                            is_ui_logged_in: isUiLoggedIn,
                            has_profile: hasProfile,
                            has_logout: hasLogout,
                            needs_join_server: needsJoinServer,
                            downloads_left: dlNum
                        });
                    })();
                    """
                    raw_res = None
                    try:
                        raw_res = window.evaluate_js(js_ryuu)
                    except Exception:
                        pass

                    data = {}
                    if raw_res:
                        try:
                            data = json.loads(raw_res) if isinstance(raw_res, str) else raw_res
                        except Exception:
                            pass
                    needs_join_ryuu = bool(data.get("needs_join_server"))

                    # 1. 偵測到尚未加入 Ryuu 伺服器，自動導航至官方邀請連結並嚴格阻斷進入步驟 2
                    if needs_join_ryuu:
                        if not state.get("ryuu_invite_redirected"):
                            state["ryuu_invite_redirected"] = True
                            print("[Sandbox] 偵測到該帳號尚未加入 Ryuu 伺服器，自動載入官方 Discord 邀請連結...")
                            window.load_url("https://discord.com/invite/manifests")
                        # ⚠️ 嚴格阻斷：只要處於未入群阻斷狀態，絕不推進步驟 2！
                        time.sleep(1.0)
                        continue

                    # 2. 從 pywebview 原生 Cookies 中解析 session (支援 HttpOnly Cookie)
                    session_val = ""
                    has_real_user_session = False
                    raw_cookies = []
                    try:
                        raw_cookies = window.get_cookies()
                        parsed_cookies = extract_cookies_dict(raw_cookies)
                        for ck in parsed_cookies:
                            val = ck.get("value", "")
                            cname = ck.get("name", "")
                            if cname == "session" and len(val) > 8:
                                decoded = decode_flask_session(val)
                                if decoded.get("user") or decoded.get("id") or decoded.get("username"):
                                    session_val = val
                                    has_real_user_session = True
                                    break
                                elif decoded.get("oauth_state") and not decoded.get("user"):
                                    continue
                                else:
                                    session_val = val
                    except Exception as e:
                        print(f"[Sandbox] Ryuu get_cookies check error: {e}")

                    is_ui_logged_in = data.get("is_ui_logged_in", False) or data.get("is_home", False)

                    # 🌟 首次跳授權立即儲存：只要已獲取到真實使用者 Session，或是 UI 已登入，或手動保存，即刻儲存並推進！
                    # 徹底移除 not is_login_page 的限制，杜絕跳兩次授權問題！
                    if not needs_join_ryuu and (has_real_user_session or manual_save or (is_ui_logged_in and session_val)):
                        state["is_saving"] = True
                        dl = data.get("downloads_left")
                        downloads_left = dl if dl is not None else 50
                        print(f"[Sandbox] Step 1 Ryuu Auth OK! 首次授權成功捕獲 (User Session={has_real_user_session})，剩餘額度: {downloads_left}")

                        # 注入視覺回饋標籤
                        try:
                            window.evaluate_js("""
                            (function() {
                                if (document.getElementById('_sm_auth_success_banner')) return;
                                var b = document.createElement('div');
                                b.id = '_sm_auth_success_banner';
                                b.style.cssText = 'position:fixed;top:18px;left:50%;transform:translateX(-50%);background:linear-gradient(135deg, #10b981, #059669);color:#ffffff;padding:12px 28px;border-radius:30px;font-size:15px;font-weight:bold;box-shadow:0 10px 32px rgba(0,0,0,0.6);z-index:99999999;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;display:flex;align-items:center;gap:10px;';
                                b.innerHTML = '<span style="font-size:20px;">🎉</span> <span>Ryuu 授權成功！正在儲存憑證...</span>';
                                document.body.appendChild(b);
                            })();
                            """)
                        except Exception:
                            pass

                        # 取得或建立帳號目錄
                        ryuu_acc_id = state["target_account_id"]
                        ryuu_profile_dir = None
                        if ryuu_acc_id:
                            existing = next((a for a in mgr.get_accounts("ryuu") if a.get("id") == ryuu_acc_id), None)
                            if existing:
                                ryuu_profile_dir = existing.get("profile_dir")

                        if not ryuu_profile_dir:
                            ryuu_acc_id, ryuu_profile_dir = mgr.create_new_account_profile_dir("ryuu")

                        c_file = Path(ryuu_profile_dir) / "Cookies"
                        save_ryuu_cookies(c_file, session_val, cookie_objs=raw_cookies)

                        acc = mgr.register_account("ryuu", ryuu_acc_id, ryuu_profile_dir)
                        acc["has_valid_credentials"] = True
                        acc["is_expired"] = False
                        acc["needs_relogin"] = False
                        acc["status_badge"] = "正常"

                        try:
                            state["ryuu_info"] = mgr._extract_user_info_from_sqlite(c_file, "ryuu")
                            if state["ryuu_info"].get("name"):
                                acc["name"] = state["ryuu_info"]["name"]
                            if state["ryuu_info"].get("avatar_url"):
                                acc["avatar_url"] = state["ryuu_info"]["avatar_url"]
                        except Exception:
                            pass

                        # 帳密自動記憶與更新
                        user_email = state.get("captured_email") or state["ryuu_info"].get("email") or auto_email or ""
                        user_pwd = state.get("captured_pwd") or auto_pwd or ""
                        user_did = state["ryuu_info"].get("id") or ""

                        if user_email and not acc.get("email"):
                            acc["email"] = user_email
                        if user_did and not acc.get("discord_id"):
                            acc["discord_id"] = user_did

                        if user_pwd:
                            mgr.save_account_credentials(
                                account_id=ryuu_acc_id,
                                email=user_email,
                                password=user_pwd,
                                discord_id=user_did
                            )
                            try:
                                print(f"[Sandbox] [Vault] Ryuu 登入成功，帳號密碼已自動保存至本地保管箱: {user_email}")
                            except Exception:
                                pass

                        mgr.update_realtime_quota("ryuu", downloads_left, daily_limit=50, account_id=acc["id"])
                        mgr.save_data()

                        state["ryuu_done"] = True

                        if plat == "ryuu":
                            try:
                                print(f"[Sandbox] Ryuu platform completed! Account ID: {ryuu_acc_id}")
                            except Exception:
                                pass
                            time.sleep(0.8)
                            window.destroy()
                            return

                        # 推進到 Step 2 (Lua.tools)
                        state["step"] = 2
                        state["is_saving"] = False
                        window.set_title("🛡️ [步驟 2/3] Lua.tools 專屬安全無痕授權沙盒 (25次/日) · 請點擊授權")
                        window.load_url("https://lua.tools/")
                        time.sleep(1.5)
                        continue

                # ── 步驟 2：Lua.tools 平台檢查 ──
                elif state["step"] == 2 and not state["is_saving"]:
                    # 自動尋找並點擊 Login with Discord
                    js_auto_click = """
                    (function() {
                        if (window.location.hostname.indexOf('lua.tools') !== -1) {
                            var btns = document.querySelectorAll('button, a');
                            for (var i = 0; i < btns.length; i++) {
                                var txt = (btns[i].textContent || '').toLowerCase().trim();
                                if (txt.indexOf('login with discord') !== -1 || (txt.indexOf('login') !== -1 && txt.indexOf('discord') !== -1)) {
                                    btns[i].click();
                                    return 'clicked';
                                }
                            }
                            var sel = document.querySelector('button.login-btn, a[href*="login"], a[href*="discord"], button[class*="discord"]');
                            if (sel) {
                                sel.click();
                                return 'clicked';
                            }
                        }
                        return 'not_found';
                    })();
                    """
                    try:
                        window.evaluate_js(js_auto_click)
                    except Exception:
                        pass

                    js_lt = """
                    (function() {
                        var hasCookie = document.cookie.match(/sb-db-auth-token(\\.\\d+)?=/) !== null;
                        var rawLocal = "";
                        try {
                            for (var i = 0; i < localStorage.length; i++) {
                                var k = localStorage.key(i);
                                var v = localStorage.getItem(k);
                                if (k.indexOf('sb-') !== -1 || k.indexOf('auth') !== -1 || k.indexOf('supabase') !== -1 || (v && v.indexOf('access_token') !== -1)) {
                                    rawLocal = v;
                                }
                            }
                        } catch(e) {}
                        
                        var tokenData = null;
                        if (rawLocal) {
                            try { tokenData = JSON.parse(rawLocal); } catch(e) {}
                        }
                        
                        var hasLogout = document.querySelector('button[aria-label*="Logout"], button[aria-label*="登出"], a[href*="logout"]') !== null;
                        
                        var loggedIn = false;
                        if (tokenData && (tokenData.access_token || tokenData.user)) {
                            loggedIn = true;
                        } else if (hasCookie) {
                            loggedIn = true;
                        } else if (hasLogout && window.location.hostname.indexOf('lua.tools') !== -1) {
                            loggedIn = true;
                        }
                        
                        var uName = "";
                        var uEmail = "";
                        var uAvatar = "";
                        var uId = "";
                        if (tokenData && tokenData.user) {
                            var u = tokenData.user;
                            uId = u.id || "";
                            uEmail = u.email || "";
                            var meta = u.user_metadata || {};
                            uName = meta.global_name || meta.full_name || meta.name || u.email || "";
                            uAvatar = meta.avatar_url || "";
                        }
                        
                        return JSON.stringify({
                            logged_in: loggedIn,
                            raw_cookie: document.cookie,
                            raw_local: rawLocal,
                            user_id: uId,
                            user_name: uName,
                            user_email: uEmail,
                            user_avatar: uAvatar
                        });
                    })();
                    """
                    raw_res = None
                    try:
                        raw_res = window.evaluate_js(js_lt)
                    except Exception:
                        pass

                    data = {}
                    if raw_res:
                        try:
                            data = json.loads(raw_res) if isinstance(raw_res, str) else raw_res
                        except Exception:
                            pass

                    # 從原生 Cookie 探測
                    has_lt_cookie = False
                    raw_cookies_lt = []
                    try:
                        raw_cookies_lt = window.get_cookies()
                        parsed_lt = extract_cookies_dict(raw_cookies_lt)
                        for ck in parsed_lt:
                            if "sb-db-auth-token" in ck.get("name", ""):
                                has_lt_cookie = True
                                break
                    except Exception:
                        pass

                    if data.get("logged_in") or has_lt_cookie or manual_save:
                        state["is_saving"] = True
                        print(f"[Sandbox] Step 2 Lua.tools Auth OK!")

                        try:
                            window.evaluate_js("""
                            (function() {
                                if (document.getElementById('_sm_auth_success_banner_lt')) return;
                                var b = document.createElement('div');
                                b.id = '_sm_auth_success_banner_lt';
                                b.style.cssText = 'position:fixed;top:18px;left:50%;transform:translateX(-50%);background:linear-gradient(135deg, #10b981, #059669);color:#ffffff;padding:12px 28px;border-radius:30px;font-size:15px;font-weight:bold;box-shadow:0 10px 32px rgba(0,0,0,0.6);z-index:99999999;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;display:flex;align-items:center;gap:10px;';
                                b.innerHTML = '<span style="font-size:20px;">🎉</span> <span>Lua.tools 授權成功！正在儲存憑證...</span>';
                                document.body.appendChild(b);
                            })();
                            """)
                        except Exception:
                            pass

                        raw_cookie = data.get("raw_cookie", "")
                        raw_local = data.get("raw_local", "")
                        uname = data.get("user_name") or state["ryuu_info"].get("name") or "Discord User"
                        uemail = data.get("user_email") or state.get("captured_email") or state["ryuu_info"].get("email") or auto_email or ""
                        uavatar = data.get("user_avatar") or state["ryuu_info"].get("avatar_url") or ""
                        uid = data.get("user_id") or state["ryuu_info"].get("id") or ""

                        lt_acc_id = state["target_account_id"]
                        lt_profile_dir = None
                        if lt_acc_id:
                            existing = next((a for a in mgr.get_accounts("lua_tools") if a.get("id") == lt_acc_id), None)
                            if existing:
                                lt_profile_dir = existing.get("profile_dir")

                        if not lt_profile_dir:
                            lt_acc_id, lt_profile_dir = mgr.create_new_account_profile_dir("lua_tools")

                        c_file = Path(lt_profile_dir) / "Cookies"
                        save_luatools_cookies(c_file, raw_cookie, raw_local, cookie_objs=raw_cookies_lt)

                        acc = mgr.register_account("lua_tools", lt_acc_id, lt_profile_dir, name=uname)
                        acc["has_valid_credentials"] = True
                        acc["is_expired"] = False
                        acc["needs_relogin"] = False
                        acc["status_badge"] = "正常"
                        if uemail and not acc.get("email"):
                            acc["email"] = uemail
                        if uavatar and not acc.get("avatar_url"):
                            acc["avatar_url"] = uavatar
                        if uid and not acc.get("discord_id"):
                            acc["discord_id"] = uid

                        # 帳密自動記憶與更新
                        user_pwd = state.get("captured_pwd") or auto_pwd or ""
                        if user_pwd:
                            mgr.save_account_credentials(
                                account_id=lt_acc_id,
                                email=uemail,
                                password=user_pwd,
                                discord_id=uid
                            )
                            try:
                                print(f"[Sandbox] [Vault] Lua.tools 登入成功，帳號密碼已自動保存至本地保管箱: {uemail}")
                            except Exception:
                                pass

                        mgr.update_realtime_quota("lua_tools", 25, daily_limit=25, account_id=acc["id"])
                        mgr.save_data()

                        state["lt_done"] = True

                        if plat == "lua_tools":
                            try:
                                print(f"[Sandbox] Lua.tools platform completed! Account ID: {lt_acc_id}")
                            except Exception:
                                pass
                            time.sleep(0.8)
                            window.destroy()
                            return

                        # 若為 all 則推進到 Step 3 (HubcapDB)
                        state["step"] = 3
                        state["is_saving"] = False
                        window.set_title("🛡️ [步驟 3/3] HubcapDB 專屬安全無痕授權沙盒 (25次/日) · 請確認授權以自動獲取 API Key")
                        window.load_url("https://hubcapmanifest.com/auth/discord")
                        time.sleep(1.5)
                        continue

                # ── 步驟 3：HubcapDB 平台檢查與 API Key 自動捕獲 ──
                elif state["step"] == 3 and not state["is_saving"]:
                    js_hc = """
                    (function() {
                        var isHubcap = window.location.hostname.indexOf('hubcapmanifest.com') !== -1;
                        var isDiscord = window.location.hostname.indexOf('discord.com') !== -1;
                        
                        // 1. 若在首頁且有 Discord 登入按鈕，自動輔助點擊
                        if (isHubcap && (window.location.pathname === '/' || window.location.pathname === '')) {
                            var loginBtn = document.querySelector('a[href*="/auth/discord"], a[href*="discord"]');
                            if (loginBtn && !window._clicked_hc_login) {
                                window._clicked_hc_login = true;
                                setTimeout(function() { try { loginBtn.click(); } catch(e){} }, 300);
                            }
                        }

                        // 2. 若在 Hubcap 且尚未完成非同步探測，發起前端 fetch
                        if (isHubcap && !window._hc_fetching) {
                            window._hc_fetching = true;
                            fetch('/auth/me', { credentials: 'include' })
                                .then(function(r) { return r.json(); })
                                .then(function(res) {
                                    if (res && res.success && res.user) {
                                        window._hc_user = res.user;
                                        return fetch('/api-keys/my-key-info', { credentials: 'include' })
                                            .then(function(r2) { return r2.json(); })
                                            .then(function(kres) {
                                                if (kres && kres.api_key) {
                                                    window._hc_api_key = kres.api_key;
                                                } else {
                                                    return fetch('/api-keys/generate-key', {
                                                        method: 'POST',
                                                        headers: { 'Content-Type': 'application/json' },
                                                        credentials: 'include'
                                                    }).then(function(r3) { return r3.json(); })
                                                      .then(function(gres) {
                                                          if (gres && gres.api_key) {
                                                              window._hc_api_key = gres.api_key;
                                                          }
                                                      });
                                                }
                                            });
                                    }
                                })
                                .catch(function(e) {})
                                .finally(function() {
                                    setTimeout(function() { window._hc_fetching = false; }, 2500);
                                });
                        }

                        // 3. 掃描 DOM 中可能出現的 API Key
                        var domKey = "";
                        if (isHubcap) {
                            var els = document.querySelectorAll('input, code, span, pre, div');
                            for (var i = 0; i < els.length; i++) {
                                var t = (els[i].value || els[i].textContent || '').trim();
                                if (t.indexOf('smm_') === 0 && t.length >= 30) {
                                    domKey = t;
                                    break;
                                }
                            }
                        }

                        var finalKey = window._hc_api_key || domKey || "";
                        var userObj = window._hc_user || null;

                        var bodyText = document.body ? (document.body.innerText || '') : '';
                        var needsJoinHc = bodyText.indexOf('You must be a member of our Discord server') !== -1 ||
                                          bodyText.indexOf('member of our Discord server') !== -1 ||
                                          bodyText.indexOf('hubcapsmanifest') !== -1 ||
                                          (bodyText.indexOf('Discord server') !== -1 && (bodyText.indexOf('member') !== -1 || bodyText.indexOf('access') !== -1));

                        return JSON.stringify({
                            is_hubcap: isHubcap,
                            is_discord: isDiscord,
                            logged_in: !!userObj || !!finalKey,
                            api_key: finalKey,
                            needs_join_server: needsJoinHc,
                            user: userObj
                        });
                    })();
                    """
                    raw_res_hc = None
                    try:
                        raw_res_hc = window.evaluate_js(js_hc)
                    except Exception:
                        pass

                    data_hc = {}
                    if raw_res_hc:
                        try:
                            data_hc = json.loads(raw_res_hc) if isinstance(raw_res_hc, str) else raw_res_hc
                        except Exception:
                            pass

                    # 偵測到尚未加入 Hubcap 伺服器 (精準支援圖一報錯)，自動導航至官方邀請連結
                    if data_hc.get("needs_join_server"):
                        if not state.get("hc_invite_redirected"):
                            state["hc_invite_redirected"] = True
                            print("[Sandbox] 偵測到該帳號尚未加入 Hubcap 伺服器 (圖一報錯)，自動載入官方 Discord 邀請連結...")
                            window.load_url("https://discord.com/invite/hubcapsmanifest")
                        time.sleep(1.0)
                        continue

                    api_key = str(data_hc.get("api_key") or "").strip()
                    hc_user = data_hc.get("user") or {}
                    hc_logged = bool(data_hc.get("logged_in") or api_key or manual_save)

                    if hc_logged:
                        # 若已有 API Key 或是觸發手動保存
                        if api_key or manual_save:
                            state["is_saving"] = True
                            from managers import hubcap_manager
                            
                            # 若無 key 但手動點擊保存，嘗試從 hubcap_manager 獲取現有
                            if not api_key:
                                api_key = hubcap_manager.get_api_key()

                            print(f"[Sandbox] Step 3 HubcapDB Auth OK! API Key found: {bool(api_key)}")

                            try:
                                window.evaluate_js("""
                                (function() {
                                    if (document.getElementById('_sm_auth_success_banner_hc')) return;
                                    var b = document.createElement('div');
                                    b.id = '_sm_auth_success_banner_hc';
                                    b.style.cssText = 'position:fixed;top:18px;left:50%;transform:translateX(-50%);background:linear-gradient(135deg, #00bcd4, #0097a7);color:#ffffff;padding:12px 28px;border-radius:30px;font-size:15px;font-weight:bold;box-shadow:0 10px 32px rgba(0,0,0,0.6);z-index:99999999;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;display:flex;align-items:center;gap:10px;';
                                    b.innerHTML = '<span style="font-size:20px;">🎉</span> <span>HubcapDB 授權成功！API Key 已自動捕獲並綁定完成！</span>';
                                    document.body.appendChild(b);
                                })();
                                """)
                            except Exception:
                                pass

                            hc_uid = str(hc_user.get("id") or state["ryuu_info"].get("id") or "").strip()
                            hc_name = str(hc_user.get("username") or state["ryuu_info"].get("name") or "").strip()
                            hc_email = str(hc_user.get("email") or state.get("captured_email") or "").strip()

                            target_id = state["target_account_id"] or hc_uid or hc_name or hc_email
                            if target_id and api_key:
                                mgr.set_hubcap_key(target_id, api_key, discord_id=hc_uid)
                                if not hubcap_manager.get_api_key():
                                    hubcap_manager.set_api_key(api_key)

                            # 帳密記憶
                            user_pwd = state.get("captured_pwd") or auto_pwd or ""
                            if user_pwd and hc_email:
                                mgr.save_account_credentials(
                                    account_id=target_id,
                                    email=hc_email,
                                    password=user_pwd,
                                    discord_id=hc_uid
                                )

                            state["hubcap_done"] = True
                            time.sleep(1.0)
                            window.destroy()
                            return
                        else:
                            # 已在 Hubcap 登入狀態但尚未回傳 key，嘗試跳轉至 /user 頁面觸發生成/讀取
                            if data_hc.get("is_hubcap") and not state.get("_redirected_to_user"):
                                state["_redirected_to_user"] = True
                                window.load_url("https://hubcapmanifest.com/user")

            except Exception as e:
                print(f"[Sandbox] Monitor loop exception: {e}")

            time.sleep(0.5)

    # 啟動背景監控線程
    t = threading.Thread(target=background_monitor, daemon=True)
    t.start()

    # 啟動 WebView2 沙盒視窗 (使用獨立儲存路徑與私密模式)
    try:
        webview.start(private_mode=True, storage_path=str(sandbox_storage))
    finally:
        state["closed"] = True
        # 清理暫存沙盒目錄
        if sandbox_storage.exists():
            try:
                shutil.rmtree(sandbox_storage, ignore_errors=True)
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description="SteamManifestUpdater 2.0 Native Sandbox Login Runner")
    parser.add_argument("--platform", default="all", choices=["all", "ryuu", "lua_tools", "luatools", "hubcap", "hubcapdb"], help="Target platform to login")
    parser.add_argument("--account-id", default=None, help="Target account ID to update")
    args, _ = parser.parse_known_args()

    run_sandbox(target_platform=args.platform, target_account_id=args.account_id)


if __name__ == "__main__":
    main()
