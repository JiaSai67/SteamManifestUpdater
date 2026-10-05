/* SteamManifestUpdater - Module: core/utils.js */
// ═══════════════════════════════════════════════════════
// 工具函數
// ═══════════════════════════════════════════════════════
function h(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
// 轉義 onclick JS 字符串裡的單引號（h() 不轉義 '，會導致名字带 ' 的遊戲按鈕失效）
function jsesc(s){ return h(s).replace(/'/g,"\\'"); }
function getDynamicCoverSvg(title){
  var rawName = String(title || 'Steam Game').trim();
  if (rawName.startsWith('Steam 遊戲 ')) rawName = rawName.substring(9);
  var name = rawName.substring(0, 26).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 460 215" width="460" height="215">' +
    '<defs>' +
    '<linearGradient id="csBg" x1="0%" y1="0%" x2="100%" y2="100%">' +
    '<stop offset="0%" stop-color="#1b1219"/>' +
    '<stop offset="50%" stop-color="#281622"/>' +
    '<stop offset="100%" stop-color="#140c13"/>' +
    '</linearGradient>' +
    '<linearGradient id="csPink" x1="0%" y1="0%" x2="100%" y2="100%">' +
    '<stop offset="0%" stop-color="#ff758c"/>' +
    '<stop offset="100%" stop-color="#ff7eb3"/>' +
    '</linearGradient>' +
    '</defs>' +
    '<rect width="460" height="215" fill="url(#csBg)"/>' +
    '<rect x="2" y="2" width="456" height="211" rx="8" fill="none" stroke="rgba(255,183,197,0.22)" stroke-width="2"/>' +
    '<circle cx="230" cy="78" r="32" fill="rgba(255,117,140,0.12)"/>' +
    '<g fill="url(#csPink)" transform="translate(212,60) scale(1.5)">' +
    '<path d="M21 6H3c-1.1 0-2 .9-2 2v8c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm-10 7H8v3H6v-3H3v-2h3V8h2v3h3v2zm4.5 2c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm4-3c-.83 0-1.5-.67-1.5-1.5S18.67 9 19.5 9s1.5.67 1.5 1.5-.67 1.5-1.5 1.5z"/>' +
    '</g>' +
    '<text x="230" y="145" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif" font-size="15" fill="#fbcfe8" font-weight="bold" text-anchor="middle">' + name + '</text>' +
    '<text x="230" y="170" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif" font-size="10.5" fill="rgba(255,183,197,0.7)" font-weight="600" text-anchor="middle">🌸 STEAM GAME</text>' +
    '</svg>'
  );
}
var DEFAULT_GAME_COVER = getDynamicCoverSvg('STEAM GAME');

function imgFb(img, appid, title){
  if(!img) return;
  if(img._fbIdx === undefined) img._fbIdx = 0;
  var fallbacks = [
    'https://cdn.cloudflare.steamstatic.com/steam/apps/' + appid + '/header.jpg',
    'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/' + appid + '/capsule_616x353.jpg',
    'https://cdn.cloudflare.steamstatic.com/steam/apps/' + appid + '/capsule_231x87.jpg',
    'https://cdn.steamchina.pinyuncloud.com/steam/apps/' + appid + '/header.jpg',
    'https://media.st.dl.pinyuncloud.com/steam/apps/' + appid + '/header.jpg'
  ];
  
  while(img._fbIdx < fallbacks.length){
    var nextUrl = fallbacks[img._fbIdx++];
    if(nextUrl !== img.src){
      img.src = nextUrl;
      return;
    }
  }
  
  // 絕不留空白！所有 CDN 均失敗時，給予帶遊戲名稱的高質感櫻花 SVG 封面
  img.onerror = null;
  img.src = getDynamicCoverSvg(title || img.getAttribute('alt') || ('Game ' + appid));
  img.classList.add('i-ok');
}
function tt(msg, type, duration){
  var e=document.getElementById('toast');
  if(!e) return;
  e.textContent=msg;
  e.className='toast '+(type||'in')+' show';
  clearTimeout(e._t);
  var ms = duration || (type === 'er' ? 5000 : (type === 'wn' ? 4500 : 2600));
  e._t=setTimeout(function(){e.classList.remove('show')}, ms);
}

// 🌟 多源下載與備援即時進度監聽 (若 Ryuu 失敗，即刻顯示備援切換)
window.onManifestProgress = function(appid, text){
  try {
    var card = document.querySelector('#glist .card[data-appid="'+appid+'"]') || document.querySelector('#results .card[data-appid="'+appid+'"]');
    if(card){
      var st = card.querySelector('.card-update-status');
      if(st) st.textContent = text;
    }
    if(text.indexOf('⚠️') > -1 || text.indexOf('Ryuu 下載未果') > -1 || text.indexOf('Ryuu 失敗') > -1){
      tt(text, 'wn', 3800);
    }
  } catch(e){}
};
function escHtml(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function openSteam(id){ pywebview.api.open_steam_store(id); }

// ── 動畫 / 圖片增強 ──
// 後台補全遊戲名後實時更新 UI（直接更新頂部 .name 元素）
function updateNames(updates){
  try {
    var cards = document.querySelectorAll('#glist .card');
    for(var i=0;i<cards.length;i++){
      var cardAid = cards[i].getAttribute('data-appid');
      if(cardAid && updates[cardAid]){
        var nameEl = cards[i].querySelector('.name');
        if(nameEl){
          nameEl.textContent = updates[cardAid];
          nameEl.title = updates[cardAid];
        }
      }
    }
    // 同時更新 _pre._games 緩存
    if(_pre._games){
      _pre._games.forEach(function(g){
        if(updates[String(g.appid)]){
          g.name = updates[String(g.appid)];
        }
      });
    }
  } catch(e){}
}
// 圖片加載完成 → 淡入
document.addEventListener('load', function(e){ if(e.target.tagName==='IMG'){ e.target.classList.add('i-ok'); } }, true);
// 卡片入场動畫：给容器內的 .card 設 --i
function staggerCards(container){
  var cards = container.querySelectorAll('.card'); if(!cards.length) return;
  for(var i=0;i<Math.min(cards.length,40);i++) cards[i].style.setProperty('--i', i);
}
// 圖片懒加載 + 已完成檢查
function fixImgs(container){
  container.querySelectorAll('img').forEach(function(img){
    img.setAttribute('loading','lazy');
    if(img.complete) img.classList.add('i-ok');
  });
}
// 骨架屏：搜索結果
var _skelSearch = '<div class=skel-row><div class="skel skel-img"></div><div><div class="skel skel-txt"></div><div class="skel skel-sub"></div></div></div>'.repeat(5);
var _skelManage = '';
for(var _si=0;_si<6;_si++) _skelManage += '<div class=card style="height:170px"><div class=skel style="height:120px;border-radius:14px 14px 0 0"></div><div style="padding:6px"><div class=skel style="height:12px;margin-bottom:4px"></div><div class=skel style="height:9px;width:50%"></div></div></div>';

// 進度彈窗
// sp(title, text, pct?, step?) — pct: 0-100 定長進度, null/undefined 不定長; step: 步骤描述
function sp(title, text, pct, step){ document.getElementById('prog-title').textContent=title; document.getElementById('prog-text').textContent=text; var bar=document.getElementById('prog-bar'); if(pct!=null){ bar.removeAttribute('indeterminate'); bar.value=pct; }else{ bar.removeAttribute('value'); } document.getElementById('prog-step').textContent=step||''; document.getElementById('prog-m').classList.remove('hidden'); }
function cp(){ document.getElementById('prog-m').classList.add('hidden'); document.getElementById('prog-bar').value=0; document.getElementById('prog-bar').removeAttribute('indeterminate'); }

// ── 櫻花流光 系統啟動載入全屏遮罩進度控制器（前端渲染最高優先） ──
var _splashCurrentPercent = 0;
var _splashTargetPercent = 0;
var _splashAnimRaf = null;

// 🌟 協同讓出線程輔助函數：純非同步讓出執行緒，保證極速流暢且杜絕 requestAnimationFrame 後台節流死鎖
function yieldToUI(minMs){
  return new Promise(function(resolve){
    setTimeout(resolve, minMs || 10);
  });
}

var _splashCurrentPercent = 0;
var _splashTargetPercent = 0;
var _splashStepTimer = null;

function setSplashProgress(targetPct, title, desc, stepIdx){
  _splashTargetPercent = Math.min(100, Math.max(0, targetPct));
  var titleEl = document.getElementById('splash-task-title');
  var descEl = document.getElementById('splash-task-desc');
  if(titleEl && title) titleEl.textContent = title;
  if(descEl && desc) descEl.textContent = desc;

  if(stepIdx){
    var dots = document.querySelectorAll('.splash-step-dot');
    dots.forEach(function(dot, idx){
      var dStep = parseInt(dot.getAttribute('data-step') || (idx+1), 10);
      if(dStep < stepIdx){
        dot.className = 'splash-step-dot done';
      } else if(dStep === stepIdx){
        dot.className = 'splash-step-dot active';
      } else {
        dot.className = 'splash-step-dot';
      }
    });
  }

  // 🌟 純非同步 16ms 平滑微插值（每秒 60 幀平滑滾動，杜絕背景節流死鎖，兼具極致流暢與視覺儀式感）
  if(!_splashStepTimer){
    _splashStepTimer = setInterval(function(){
      if(_splashCurrentPercent < _splashTargetPercent){
        var diff = _splashTargetPercent - _splashCurrentPercent;
        var step = Math.max(0.7, diff * 0.2);
        _splashCurrentPercent = Math.min(_splashTargetPercent, _splashCurrentPercent + step);
      } else if(_splashCurrentPercent > _splashTargetPercent){
        _splashCurrentPercent = _splashTargetPercent;
      }

      var rounded = Math.round(_splashCurrentPercent);
      var numEl = document.getElementById('splash-percent-num');
      if(numEl) numEl.textContent = rounded;

      var barEl = document.getElementById('splash-ring-bar');
      if(barEl){
        var circumference = 364.42;
        var offset = circumference - (circumference * (_splashCurrentPercent / 100));
        barEl.style.strokeDashoffset = offset;
      }

      if(_splashCurrentPercent >= _splashTargetPercent){
        clearInterval(_splashStepTimer);
        _splashStepTimer = null;
      }
    }, 16);
  }
}

async function dismissSplashScreen(){
  setSplashProgress(100, '✨ 系統初始化就緒！', '所有系統服務與視覺配置準備完畢', 8);
  var numEl = document.getElementById('splash-percent-num');
  if(numEl) numEl.textContent = '100';
  var barEl = document.getElementById('splash-ring-bar');
  if(barEl) barEl.style.strokeDashoffset = '0';

  var overlay = document.getElementById('splash-overlay');
  if(overlay){
    overlay.classList.add('fade-out');
    await new Promise(function(resolve){
      setTimeout(function(){
        overlay.style.display = 'none';
        resolve();
      }, 380);
    });
  }
}

// ── 進度與提示輔助 ──

// ── 入庫遊戲解析進度監聽（Splash 畫面即時反饋）──
window.on_game_resolved_progress = function(data){
  if(!data) return;
  var cur = data.current || 0;
  var tot = data.total || 0;
  var nm = data.name || ('App_' + data.appid);
  var pct = 85 + Math.round((cur / Math.max(1, tot)) * 10);
  setSplashProgress(pct, '正在確認入庫遊戲資訊與官方封面 (' + cur + '/' + tot + ')...', nm, 6);
};

async function init(){
  var splashDismissed = false;
  // 安全超時保護（延長至 35 秒極端保底，確保名稱與封面確認完成前絕不搶著進系統）
  var safetyTimer = setTimeout(function(){
    if(!splashDismissed){
      splashDismissed = true;
      dismissSplashScreen();
    }
  }, 35000);

  try {
    // ══════════════════════════════════════════════════
    // 🌟 核心突破：第 0 毫秒立即並行啟動「四大重度資料預載入 Promise」
    // 充分利用 Splash Screen 的等待時間，在背景並行拉取，絕不卡頓主執行緒
    // ══════════════════════════════════════════════════
    console.log('[INIT] Parallel preloading core data...');
    var pCreds = (window.pywebview && pywebview.api && pywebview.api.get_credentials_status)
      ? pywebview.api.get_credentials_status().catch(function(e){ console.warn('[PRELOAD] creds error:', e); return null; })
      : Promise.resolve(null);

    var pGames = (window.pywebview && pywebview.api && pywebview.api.list_games)
      ? pywebview.api.list_games().catch(function(e){ console.warn('[PRELOAD] games error:', e); return []; })
      : Promise.resolve([]);

    var pDlls = (window.pywebview && pywebview.api && pywebview.api.check_dlls)
      ? pywebview.api.check_dlls().catch(function(){ return null; })
      : Promise.resolve(null);

    var pAppids = (window.pywebview && pywebview.api && pywebview.api.get_installed_appids)
      ? pywebview.api.get_installed_appids().catch(function(){ return []; })
      : Promise.resolve([]);

    var pHealth = (window.pywebview && pywebview.api && pywebview.api.get_latest_system_health)
      ? pywebview.api.get_latest_system_health().catch(function(e){ console.warn('[PRELOAD] health error:', e); return null; })
      : Promise.resolve(null);

    // ══════════════════════════════════════════════════
    // Step 1 (15%): 讀取偏好設置與主題設定
    // ══════════════════════════════════════════════════
    console.log('[INIT] Starting Step 1 - get_config');
    var config = await pywebview.api.get_config();
    setPath(config.steam_path||'');
    var isDark = config.dark_mode !== undefined ? !!config.dark_mode : (config.dark !== undefined ? !!config.dark : true);
    var tDark = document.getElementById('t-dark');
    if(tDark) tDark.checked = isDark;
    if(isDark){
      document.documentElement.classList.add('dark');
      document.getElementById('app').classList.add('dark');
      var spOver = document.getElementById('splash-overlay');
      if(spOver) spOver.classList.add('dark');
      try { localStorage.setItem('dark_mode', '1'); } catch(e){}
    } else {
      document.documentElement.classList.remove('dark');
      document.getElementById('app').classList.remove('dark');
      var spOver = document.getElementById('splash-overlay');
      if(spOver) spOver.classList.remove('dark');
      try { localStorage.removeItem('dark_mode'); } catch(e){}
    }

    setSplashProgress(15, '載入使用者設定檔與個人化設置...', '讀取本機偏好設置、主題色調與視窗幾何尺寸', 1);
    await yieldToUI(80);
    var tRand = document.getElementById('t-random');
    if(tRand) tRand.checked = !!config.random_browse;
    var tFloat = document.getElementById('t-float');
    if(tFloat) tFloat.checked = !!config.float_enabled;

    if(config.version){
      var vEl = document.getElementById('ver');
      if(vEl) vEl.textContent = config.version;
      var ttlEl = document.getElementById('ttl');
      if(ttlEl) ttlEl.textContent = '🌸 Steam 入庫與清單更新工具 (多源極速版) '+config.version;
    }

    // ══════════════════════════════════════════════════
    // Step 2 (30%): 檢測 Steam 安裝目錄與版本鎖定狀態
    // ══════════════════════════════════════════════════
    console.log('[INIT] Starting Step 2');
    setSplashProgress(30, '檢測 Steam 安裝目錄與版本鎖定...', '驗證 Steam 實體路徑與 ACF 檔案鎖定狀態', 2);
    await yieldToUI(80);

    var _sp = "";
    try { _sp = (await pywebview.api.ensure_steam_path()) || ""; } catch(e){ _sp = config.steam_path || ""; }
    if(_sp !== (config.steam_path||'')) setPath(_sp);
    if(!_sp) tt('⚠️ 未找到 Steam 安裝目錄，請在「設置」頁手動選擇 Steam 路徑後重新注入', 'er');
    try {
      var sLock = await pywebview.api.check_steam_locked();
      if(sLock && !sLock.unlocked) await pywebview.api.lock_steam_version().catch(function(){});
    } catch(e){}
    checkSteamLock();

    // ══════════════════════════════════════════════════
    // Step 3 (45%): 加載背景主題、縮圖與視圖配置
    // ══════════════════════════════════════════════════
    console.log('[INIT] Starting Step 3');
    setSplashProgress(45, '加載背景主題與視覺快取...', '載入自定義桌布、縮圖與網格排版快取', 3);
    await yieldToUI(80);

    loadBgThumbs();
    try { pywebview.api.install_default_bgs().then(loadBgThumbs).catch(function(){}); } catch(e){}
    if(config.bg_active) swBg(config.bg_active);
    initVisualSettings(config);
    var savedView = (config && config.view_mode) || 'grid';
    if(!savedView || savedView === 'undefined'){
      try { savedView = localStorage.getItem('view-mode') || 'grid'; } catch(e){}
    }
    toggleView(savedView);
    bindWindowResize();

    // ══════════════════════════════════════════════════
    // Step 4 (60%): 自檢核心環境與 OpenSteamTools 內核
    // ══════════════════════════════════════════════════
    console.log('[INIT] Starting Step 4');
    setSplashProgress(60, '自檢核心環境與 OpenSteamTools 內核...', '校驗 SteamTools DLL 模組與前置運行環境', 4);
    await yieldToUI(80);

    try {
      var dllRes = await pDlls;
      if(dllRes && dllRes.ok) _hasPassedPrereq = true;
    } catch(e){}

    // ══════════════════════════════════════════════════
    // Step 5 (75%): 🌟 真實預載入憑證與多平台配額矩陣 (徹底杜絕切換等待)
    // ══════════════════════════════════════════════════
    console.log('[INIT] Starting Step 5 - Real Credentials Preload');
    setSplashProgress(75, '同步多平台帳號憑證與配額矩陣...', '預載入 Ryuu / Hubcap / LuaTools 授權與即時額度', 5);
    await yieldToUI(80);

    try {
      var credRes = await pCreds;
      if(credRes && credRes.ok){
        if(typeof loadCredentialsStatus === 'function'){
          await loadCredentialsStatus(false);
        }
        if(typeof updateManageQuota === 'function'){
          updateManageQuota();
        }
      }
    } catch(e){
      console.warn('[INIT] Step 5 credentials render error:', e);
    }

    // ══════════════════════════════════════════════════
    // Step 6 (88%): 🌟 深度確認入庫遊戲真實名稱與高畫質封面（絕不搶著進系統）
    // ══════════════════════════════════════════════════
    console.log('[INIT] Starting Step 6 - Ensure Installed Games Resolved');
    setSplashProgress(85, '校驗本機已入庫遊戲與官方封面...', '對齊本機遊戲清單，確保繁中名稱與高畫質圖片就緒', 6);
    await yieldToUI(80);

    try {
      var games = [];
      if (window.pywebview && pywebview.api && pywebview.api.ensure_installed_games_resolved) {
        var resResolve = await pywebview.api.ensure_installed_games_resolved();
        if (resResolve && resResolve.games && resResolve.games.length) {
          games = resResolve.games;
        } else {
          games = await pGames;
        }
      } else {
        games = await pGames;
      }
      _pre._games = games || [];
      if(typeof renderGames === 'function'){
        var filter = (document.getElementById('mf') ? document.getElementById('mf').value : '').trim().toLowerCase();
        renderGames(_pre._games, filter);
        _pre._rendered = true;
      }
    } catch(e){
      console.warn('[INIT] Step 6 games resolve error:', e);
      try {
        var gamesFallback = await pGames;
        _pre._games = gamesFallback || [];
        if (typeof renderGames === 'function') {
          renderGames(_pre._games, '');
          _pre._rendered = true;
        }
      } catch(_) {}
    }

    // ══════════════════════════════════════════════════
    // Step 7 (96%): 預載入已安裝 AppID 與網盤本機配置
    // ══════════════════════════════════════════════════
    setSplashProgress(96, '初始化已安裝遊戲與網盤配置...', '檢測本機 AppID 映射與多源資料庫緩存', 7);
    await yieldToUI(80);

    try{
      var localIds = await pAppids;
      if(localIds && localIds.length){
        localIds.forEach(function(x){ _installedAppids.add(String(x)); });
      }

      // 🌟 預先就地渲染健康報告，使用者切換「系統」分頁 0ms 秒開
      try {
        pHealth.then(function(hRes){
          if(hRes && hRes.ok && typeof renderHealthCheckOverview === 'function'){
            renderHealthCheckOverview(hRes);
            if(typeof loadHealthHistoryList === 'function') loadHealthHistoryList();
          }
        });
      } catch(e){}
    }catch(e){}

    // ══════════════════════════════════════════════════
    // Step 8 (100%): 全模組預載入就緒！滿幀揭開主介面
    // ══════════════════════════════════════════════════
    setSplashProgress(100, '系統全模組預載入就緒！', '所有核心功能與資料已準備完畢，歡迎使用', 8);
    await yieldToUI(180);

    clearTimeout(safetyTimer);
    if(!splashDismissed){
      splashDismissed = true;
      await dismissSplashScreen();
    }

    // ══════════════════════════════════════════════════
    // 🚀 首屏推薦探索卡片淡入
    // ══════════════════════════════════════════════════
    loadBrowse(0, false).catch(function(){});

    // ══════════════════════════════════════════════════
    // 🚀 Stage 4 (延遲 7500ms): 繁重 Manifest 比對與軟體更新檢測
    // 此時介面已完全穩定，背景靜默爬蟲完全無感
    // ══════════════════════════════════════════════════
    setTimeout(function(){
      startProactiveUpdateCheck(false);
      pywebview.api.check_update().then(function(u){
        if(u && u.has_update && u.version){
          _updateUrl = u.url;
          var uVer = document.getElementById('update-ver');
          if(uVer) uVer.textContent = u.version;
          var pw = u.password || '', pr = document.getElementById('update-pwd-row');
          if(pw){
            var uPw = document.getElementById('update-pwd');
            if(uPw) uPw.textContent = pw;
            var uHint = document.getElementById('update-hint');
            if(uHint) uHint.textContent = '密碼已復制到剪貼板，是否跳轉到下載頁面？';
            if(pr) pr.style.display = '';
          } else {
            if(pr) pr.style.display = 'none';
          }
          var mBox = document.getElementById('modal-update');
          if(mBox) mBox.style.display = 'flex';
        }
      }).catch(function(){});
    }, 7500);

    // 啟動定時配額保鮮 (每 15 秒僅在視窗可見且處於相關分頁時查詢)
    setInterval(function(){
      if(document.visibilityState !== 'hidden'){
        if(_cur === 'credentials') loadCredentialsStatus(false);
        else if(_cur === 'manage') updateManageQuota();
      }
    }, 15000);

    window.addEventListener('focus', function(){
      if(_cur === 'credentials') loadCredentialsStatus(false);
      else if(_cur === 'manage') updateManageQuota();
    });

    // 定時保鮮比對（每 15 分鐘背景主動檢查一次）
    setInterval(function(){
      startProactiveUpdateCheck(false);
    }, 15 * 60 * 1000);

  } catch(e){
    console.error('init error', e);
    clearTimeout(safetyTimer);
    if(!splashDismissed){
      splashDismissed = true;
      dismissSplashScreen();
    }
  }
}

// ── 窗口縮放（無邊框窗口自绘 4邊+4角 手柄；前端按拖的邊算增量並傳"釘住的對邊" fp，後端 resize 自動釘對邊/移動窗口）──
var _rsz = null;  // 當前拖拽狀態 {side, x0, y0, W, H, el, _pend, _raf}

// ── 視窗極速流暢拖曳（透過 rAF 與 W3C PointerCapture 進行滿幀硬體排程，告別 IPC 堵塞與卡頓）──
function bindTitlebarDrag(){
  var tbs = document.querySelectorAll('.titlebar, .splash-titlebar');
  tbs.forEach(function(tb){
    if(!tb || tb._dragBound) return;
    tb._dragBound = true;

    var isDragging = false;
    var startClientX = 0;
    var startClientY = 0;
    var targetX = 0;
    var targetY = 0;
    var rafPending = false;

    function sendMove(x, y) {
      if (window.chrome && window.chrome.webview && window.chrome.webview.postMessage) {
        window.chrome.webview.postMessage(['pywebviewMoveWindow', JSON.stringify([x, y]), 'move']);
      } else if (window.pywebview && window.pywebview._jsApiCallback) {
        window.pywebview._jsApiCallback('pywebviewMoveWindow', [x, y], 'move');
      }
    }

    function onPointerMove(e) {
      if (!isDragging) return;
      targetX = Math.round(e.screenX - startClientX);
      targetY = Math.round(e.screenY - startClientY);

      if (!rafPending) {
        rafPending = true;
        requestAnimationFrame(function() {
          rafPending = false;
          if (!isDragging) return;
          sendMove(targetX, targetY);
        });
      }
    }

    function onPointerUp(e) {
      if (!isDragging) return;
      isDragging = false;
      rafPending = false;
      targetX = Math.round(e.screenX - startClientX);
      targetY = Math.round(e.screenY - startClientY);
      sendMove(targetX, targetY);

      window.removeEventListener('pointermove', onPointerMove, true);
      window.removeEventListener('pointerup', onPointerUp, true);
      window.removeEventListener('pointercancel', onPointerUp, true);
      try {
        if (tb.releasePointerCapture) tb.releasePointerCapture(e.pointerId);
      } catch (_) {}
    }

    tb.addEventListener('pointerdown', function(e) {
      if (e.button !== 0) return;
      if (e.target.closest('button, input, textarea, a, .btns, .no-drag, select, .win-btn, .search-box')) return;

      isDragging = true;
      startClientX = e.clientX;
      startClientY = e.clientY;
      targetX = Math.round(e.screenX - startClientX);
      targetY = Math.round(e.screenY - startClientY);

      try {
        if (tb.setPointerCapture) tb.setPointerCapture(e.pointerId);
      } catch (_) {}

      window.addEventListener('pointermove', onPointerMove, true);
      window.addEventListener('pointerup', onPointerUp, true);
      window.addEventListener('pointercancel', onPointerUp, true);

      e.preventDefault();
    });

    tb.addEventListener('dblclick', function(e) {
      if (e.target.closest('button, input, textarea, a, .btns, .no-drag, select, .win-btn, .search-box')) return;
      e.preventDefault();
      if (window.pywebview && pywebview.api && pywebview.api.maximize) {
        pywebview.api.maximize().catch(function() {});
      }
    });
  });
}

function bindWindowResize(){
  var els = document.querySelectorAll('#rsz i'), i;
  for(i=0; i<els.length; i++){ els[i].addEventListener('pointerdown', rszStart, {passive:false}); }
}
function rszStart(e){
  if(e.button !== 0 || !_rszSafe()) return;
  var side = this.getAttribute('data-side');
  if(!side) return;
  e.preventDefault();

  _rsz = {side:side, x0:e.clientX, y0:e.clientY, sx0:e.screenX, sy0:e.screenY,
          W:window.innerWidth, H:window.innerHeight,
          el:this, _pend:null, _raf:false};
  try{ this.setPointerCapture(e.pointerId); }catch(err){}
  this.classList.add('rsz-on');
  this.addEventListener('pointermove', rszMove, {passive:false});
  this.addEventListener('pointerup', rszEnd);
  this.addEventListener('pointercancel', rszEnd);
}
function _rszSafe(){ return !!(window.pywebview && pywebview.api); }
function _rszFix(side){  // 返回要"釘住"的對邊 fp 串(n↔s、e↔w 取反)；後端按它固定對邊、自動重排窗口
  var m = {n:'s', s:'n', e:'w', w:'e'}, out = '', k;
  for(k = 0; k < side.length; k++) out += m[side.charAt(k)];
  return out;
}
function _rszSize(side, W, H, p){  // 由拖拽增量算目標寬高；N/W 方向增量取負(朝窗口外側拉=變大)
  var w = W + (/e/.test(side) ? p.dx : (/w/.test(side) ? -p.dx : 0));
  var h = H + (/s/.test(side) ? p.dy : (/n/.test(side) ? -p.dy : 0));
  if(w < 880) w = 880;   // 最佳體驗最小限制
  if(h < 580) h = 580;
  return {w: Math.round(w), h: Math.round(h)};
}
function rszMove(e){
  if(!_rsz) return;
  e.preventDefault();
  // E/S 邊拖動時窗口原點不動，client 增量即真實增量(沿用已驗证邏辑)；
  // N/W 邊會让窗口原點每帧移動、client 坐標幾乎不變，必須用屏幕絕對增量(e.screenX/Y)。
  if(/[nw]/.test(_rsz.side))
    _rsz._pend = {dx: e.screenX - _rsz.sx0, dy: e.screenY - _rsz.sy0};
  else
    _rsz._pend = {dx: e.clientX - _rsz.x0, dy: e.clientY - _rsz.y0};
  if(_rsz._raf) return;  // rAF 節流：同一帧只發一次 resize_to
  _rsz._raf = true;
  requestAnimationFrame(function(){
    _rsz._raf = false;
    if(!_rsz || !_rsz._pend) return;
    var p = _rsz._pend; _rsz._pend = null;
    var t = _rszSize(_rsz.side, _rsz.W, _rsz.H, p);
    pywebview.api.resize_to(t.w, t.h, _rszFix(_rsz.side)).catch(function(){});
  });
}
function rszEnd(e){
  if(!_rsz) return;
  var el = _rsz.el, side = _rsz.side, W = _rsz.W, H = _rsz.H, pend = _rsz._pend;
  _rsz = null;
  try{ el.releasePointerCapture && el.releasePointerCapture(e.pointerId); }catch(err){}
  el.removeEventListener('pointermove', rszMove);
  el.removeEventListener('pointerup', rszEnd);
  el.removeEventListener('pointercancel', rszEnd);
  el.classList.remove('rsz-on');
  // 鬆開瞬間最後一帧增量可能還没輪到 rAF，同步補發一次，保证停在鼠標位置
  if(pend){
    var t = _rszSize(side, W, H, pend);
    pywebview.api.resize_to(t.w, t.h, _rszFix(side)).catch(function(){});
  }
  pywebview.api.save_window_size().catch(function(){});  // 落盤，下次啟動保持
}

var _updateUrl = '';
function goUpdate(){
  document.getElementById('update-m').classList.add('hidden');
  if(_updateUrl) pywebview.api.open_url(_updateUrl);
}
function closeUpdate(){
  document.getElementById('update-m').classList.add('hidden');
}


// ── 全域字體大小切換（小 / 正常）──
function setFontSize(size, isInitial){
  size = (size === 'small') ? 'small' : 'normal';
  var html = document.documentElement;
  var body = document.body;
  if(size === 'normal'){
    html.classList.remove('font-small');
    html.classList.add('font-normal');
    if(body){
      body.classList.remove('font-small');
      body.classList.add('font-normal');
    }
  } else {
    html.classList.remove('font-normal');
    html.classList.add('font-small');
    if(body){
      body.classList.remove('font-normal');
      body.classList.add('font-small');
    }
  }
  var bSmall = document.getElementById('btn-font-small');
  var bNormal = document.getElementById('btn-font-normal');
  if(bSmall && bNormal){
    if(size === 'normal'){
      bSmall.className = 'btn btn-o btn-xs';
      bNormal.className = 'btn btn-p btn-xs';
    } else {
      bSmall.className = 'btn btn-p btn-xs';
      bNormal.className = 'btn btn-o btn-xs';
    }
  }
  try { localStorage.setItem('ui_font_size', size); } catch(e){}
  if(!isInitial){
    try { pywebview.api.set_config('ui_font_size', size); } catch(e){}
    tt('介面大小已設定為：' + (size === 'normal' ? '正常 (清晰標準)' : '小 (微縮緊湊)'), 'ok');
  }
}

// ── 視覺調節（背景磨砂、圖片濃度、視窗透明度）──
function onBgBlurChange(v){
  var n = parseInt(v, 10) || 0;
  var valEl = document.getElementById('val-bg-blur');
  if(valEl) valEl.textContent = n + ' px';
  document.documentElement.style.setProperty('--bg-blur', n + 'px');
  try{ pywebview.api.set_config('bg_blur', n); }catch(e){}
}

function onBgOpacityChange(v){
  var n = parseInt(v, 10);
  if(isNaN(n)) n = 80;
  var valEl = document.getElementById('val-bg-opacity');
  if(valEl) valEl.textContent = n + '%';
  document.documentElement.style.setProperty('--bg-opacity', (n / 100).toFixed(2));
  try{ pywebview.api.set_config('bg_opacity', n); }catch(e){}
}

function onWinOpacityChange(v){
  var n = parseInt(v, 10);
  if(isNaN(n)) n = 100;
  var valEl = document.getElementById('val-win-opacity');
  if(valEl) valEl.textContent = n + '%';
  document.documentElement.style.setProperty('--win-opacity', (n / 100).toFixed(2));
  try{ pywebview.api.set_window_opacity(n); }catch(e){}
  try{ pywebview.api.set_config('win_opacity', n); }catch(e){}
}

function onTextBgOpacityChange(v){
  var n = parseInt(v, 10);
  if(isNaN(n)) n = 65;
  var valEl = document.getElementById('val-text-bg-opacity');
  if(valEl) valEl.textContent = n + '%';
  var alpha = (n / 100).toFixed(2);
  document.documentElement.style.setProperty('--card-text-bg', 'rgba(0, 0, 0, ' + alpha + ')');
  try{ pywebview.api.set_config('card_text_bg_opacity', n); }catch(e){}
}

function initVisualSettings(cfg){
  if(!cfg) return;
  var fontSize = (cfg && cfg.ui_font_size) || '';
  if(!fontSize){
    try { fontSize = localStorage.getItem('ui_font_size') || 'normal'; } catch(e){ fontSize = 'normal'; }
  }
  setFontSize(fontSize, true);
  var blur = (cfg.bg_blur !== undefined) ? parseInt(cfg.bg_blur, 10) : 0;
  var bop = (cfg.bg_opacity !== undefined) ? parseInt(cfg.bg_opacity, 10) : 80;
  var wop = (cfg.win_opacity !== undefined) ? parseInt(cfg.win_opacity, 10) : 100;
  var top = (cfg.card_text_bg_opacity !== undefined) ? parseInt(cfg.card_text_bg_opacity, 10) : 65;
  
  var slBlur = document.getElementById('slider-bg-blur');
  var slBop = document.getElementById('slider-bg-opacity');
  var slWop = document.getElementById('slider-win-opacity');
  var slTop = document.getElementById('slider-text-bg-opacity');
  if(slBlur) slBlur.value = blur;
  if(slBop) slBop.value = bop;
  if(slWop) slWop.value = wop;
  if(slTop) slTop.value = top;
  
  var valBlur = document.getElementById('val-bg-blur');
  var valBop = document.getElementById('val-bg-opacity');
  var valWop = document.getElementById('val-win-opacity');
  var valTop = document.getElementById('val-text-bg-opacity');
  if(valBlur) valBlur.textContent = blur + ' px';
  if(valBop) valBop.textContent = bop + '%';
  if(valWop) valWop.textContent = wop + '%';
  if(valTop) valTop.textContent = top + '%';
  
  document.documentElement.style.setProperty('--bg-blur', blur + 'px');
  document.documentElement.style.setProperty('--bg-opacity', (bop / 100).toFixed(2));
  document.documentElement.style.setProperty('--win-opacity', (wop / 100).toFixed(2));
  document.documentElement.style.setProperty('--card-text-bg', 'rgba(0, 0, 0, ' + (top / 100).toFixed(2) + ')');

  // 套用作業系統級真實視窗半透明
  try{ pywebview.api.set_window_opacity(wop); }catch(e){}
}




// 預加載緩存
var _pre = {};
var _expandedDlcs = {};  // {parentAppid: [dlc_game_objects]} 展開的 DLC 緩存

// ── DLC 展開 / 收起 ──
async function toggleDlcs(appid){
  var parentCard = document.querySelector('#glist .card[data-appid="'+appid+'"]');
  if(!parentCard) return;
  if(_expandedDlcs[appid]){
    // 收起：移除已插入的 DLC 卡片
    document.querySelectorAll('#glist .card[data-dlc-parent="'+appid+'"]').forEach(function(c){ c.remove(); });
    delete _expandedDlcs[appid];
    // 更新菜單按鈕文字
    var dd = parentCard.querySelector('.card-dd');
    if(dd){ dd.querySelectorAll('button').forEach(function(b){ if(b.textContent.indexOf('收起 DLC')>-1) b.textContent = '📦 查看 DLC'; }); }
    staggerCards(document.getElementById('glist'));
    return;
  }
  // 展開：调 API 获取已入庫 DLC
  try {
    var dlcs = await pywebview.api.list_game_dlcs(appid);
    if(!dlcs || !dlcs.length){
      tt('该遊戲暫無已入庫 DLC','in');
      var dd2 = parentCard.querySelector('.card-dd');
      if(dd2) dd2.classList.remove('show');
      return;
    }
    _expandedDlcs[appid] = dlcs;
    // 更新菜單按鈕文字
    var dd = parentCard.querySelector('.card-dd');
    if(dd){ dd.querySelectorAll('button').forEach(function(b){ if(b.textContent.indexOf('查看 DLC')>-1) b.textContent = '📦 收起 DLC'; }); }
    // 計算當前卡片在列表中的位置
    var allCards = document.querySelectorAll('#glist .card');
    var idx = Array.from(allCards).indexOf(parentCard);
    // 在父卡片後插入 DLC 卡片
    var h = '';
    for(var i=0; i<dlcs.length; i++){
      var d = dlcs[i];
      var nm = d.name || ('DLC_' + d.appid);
      var dmBtn = d.is_embedded ? '' : '<button class="card-menu" title="更多選項" onclick="event.stopPropagation()"><svg viewBox="0 0 16 16" width="13" height="13" fill="currentColor"><circle cx="2.5" cy="8" r="1.5"/><circle cx="8" cy="8" r="1.5"/><circle cx="13.5" cy="8" r="1.5"/></svg></button>';
      var dm = d.is_embedded ? '' : '<div class="card-dd" onclick="event.stopPropagation()"><button onclick="event.stopPropagation(); editLua(\''+d.appid+'\')">📝 編輯 Lua</button><button class=vfbtn onclick="event.stopPropagation(); toggleVf(\''+d.appid+'\')">'+(d.locked?'解除版本鎖定':'🔒 固定版本')+'</button><button onclick="event.stopPropagation(); inspectDriveStatus(\''+d.appid+'\',\''+jsesc(nm)+'\')">🌐 檢視網盤狀況</button><button onclick="event.stopPropagation(); delGame(\''+d.appid+'\',\''+jsesc(nm)+'\')">🗑 刪除</button></div>';
      h += '<div class="card dlc-card" data-dlc-parent="'+appid+'" data-appid="'+d.appid+'" style="--i:'+(idx+i+1)+'">' +
             '<div class=name title="'+escHtml(nm)+'"><span class=dlc-tag>🏷️ DLC</span> '+escHtml(nm)+'</div>' +
             '<img src="'+d.image+'" loading=lazy onerror="imgFb(this,'+d.appid+')">' +
             dmBtn + dm +
             '<div class=aid>'+escHtml(d.appid)+'</div>' +
           '</div>';
    }
    parentCard.insertAdjacentHTML('afterend', h);
    fixImgs(document.getElementById('glist'));
    staggerCards(document.getElementById('glist'));
    bindCardMenus(document.getElementById('glist'));
  } catch(e){ tt('加載 DLC 失敗','er'); }
}
async function prefetch(p){
  if(p === 'manage'){
    if(!_pre._games){
      try {
        _pre._games = await pywebview.api.list_games();
      } catch(e){ _pre._games = null; }
    }
    if(_pre._games && _pre._games.length && !_pre._rendered){
      renderGames(_pre._games, '');
      _pre._rendered = true;
    }
  }
}

// ═══════════════════════════════════════════════════════
// 全域彈窗背景點擊防誤觸安全機制 (按下 and 彈起均在背景空白處才關閉)
// 徹底防止反白拖曳選取文字時，滑鼠移至小卡外放開導致視窗誤關閉
// ═══════════════════════════════════════════════════════
var _lastMouseDownTarget = null;
document.addEventListener('mousedown', function(e) {
  _lastMouseDownTarget = e.target;
}, true);

/**
 * 判定是否為合格且完整的「空白背景點擊」關閉事件
 * 嚴格校驗：滑鼠按下 (mousedown) 與 彈起 (mouseup/click) 必須均在背景容器元素本身上！
 * 若是在小卡、輸入框等子元素內按下，拖曳至小卡外放開，則絕對不予觸發關閉！
 *
 * @param {Event} e - 點擊事件對象 (click event)
 * @param {HTMLElement} [container] - 預期的背景容器元素 (若不傳則預設為 e.currentTarget 或 e.target)
 * @returns {boolean} 是否為完整合法的背景點擊
 */
function isStrictBackdropClick(e, container) {
  if (!e) return false;
  var modal = container || e.currentTarget || e.target;
  if (!modal) return false;
  var isClickOnModal = (e.target === modal);
  var isMouseDownOnModal = (_lastMouseDownTarget === modal);
  return isClickOnModal && isMouseDownOnModal;
}

/**
 * 為指定的彈窗元素綁定嚴格背景點擊關閉事件
 * @param {HTMLElement|string} modalOrId 
 * @param {Function} closeFn 
 */
function bindBackdropClickClose(modalOrId, closeFn) {
  var modal = typeof modalOrId === 'string' ? document.getElementById(modalOrId) : modalOrId;
  if (!modal || typeof closeFn !== 'function') return;

  var isPressingBackdrop = false;
  modal.addEventListener('mousedown', function(e) {
    isPressingBackdrop = (e.target === modal);
  });

  modal.addEventListener('mouseup', function(e) {
    if (!isPressingBackdrop || e.target !== modal) {
      isPressingBackdrop = false;
    }
  });

  modal.addEventListener('click', function(e) {
    if (isPressingBackdrop && e.target === modal && _lastMouseDownTarget === modal) {
      closeFn(e);
    }
    isPressingBackdrop = false;
  });
}



