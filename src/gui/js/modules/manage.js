/* SteamManifestUpdater - Module: modules/manage.js */
// ═══════════════════════════════════════════════════════
// 管理入庫頁面：即時計算並展示 Ryuu, HubcapDB 與 Lua.tools 剩餘總配額
// ═══════════════════════════════════════════════════════
function _checkAccountValidHelper(platform, acc){
  if(!acc) return false;
  if(typeof _isAccValid === 'function'){
    return _isAccValid(platform, acc);
  }
  return acc.has_valid_credentials === true && !acc.is_expired && !acc.needs_relogin &&
         acc.status_badge !== '憑證無效' && acc.status_badge !== '憑證已過期' && acc.status_badge !== '未登入/憑證缺失';
}

async function updateManageQuota(){
  try {
    if(!window.pywebview || !window.pywebview.api || !window.pywebview.api.get_credentials_status) return;
    var res = await pywebview.api.get_credentials_status();
    if(!res || !res.ok) return;

    var box = document.getElementById('manage-quota-box');
    if(!box) return;

    // 1. Ryuu 配額與狀態計算
    var rAccounts = (res.ryuu && res.ryuu.accounts) || [];
    var rValidAccs = rAccounts.filter(function(a){ return _checkAccountValidHelper('ryuu', a); });
    var rTotalLeft = 0;
    var rTotalLimit = 0;
    for(var i = 0; i < rValidAccs.length; i++){
      var acc = rValidAccs[i];
      var limit = parseInt(acc.daily_limit) || 50;
      var used = parseInt(acc.quota_used_today) || 0;
      rTotalLeft += Math.max(0, limit - used);
      rTotalLimit += limit;
    }

    var rChipHtml = '';
    if(rAccounts.length === 0){
      rChipHtml = '<span class="quota-chip quota-chip-unlogin" onclick="switchPage(\'credentials\')" title="尚未登入 Ryuu 帳號，點擊前往登入">🐉 Ryuu: <b>🔑 未登入</b></span>';
    } else if(rValidAccs.length === 0){
      rChipHtml = '<span class="quota-chip quota-chip-expired" onclick="switchPage(\'credentials\')" title="Ryuu 憑證已過期，點擊重新登入">🐉 Ryuu: <b>⚠️ 待重登</b></span>';
    } else if(rTotalLeft <= 0){
      rChipHtml = '<span class="quota-chip quota-chip-exhausted" onclick="switchPage(\'credentials\')" title="今日配額已用罄，點擊查看">🐉 Ryuu: <b>0 次 (今日滿)</b></span>';
    } else {
      var rTitle = '🐉 Ryuu 今日剩餘配額: ' + rTotalLeft + ' / ' + rTotalLimit + ' 次 (' + rValidAccs.length + ' 個有效帳號)';
      rChipHtml = '<span class="quota-chip quota-chip-ryuu" onclick="switchPage(\'credentials\')" title="' + rTitle + '">🐉 Ryuu: <b>' + rTotalLeft + '</b> 次</span>';
    }

    // 2. HubcapDB 官方配額與狀態計算
    var hc = res.hubcap || {};
    var hcLeft = hc.remaining || 0;
    var hcLimit = hc.daily_limit || (hc.is_configured ? 50 : 0);
    var hcIsValid = !!hc.is_valid;
    var hcChipHtml = '';
    if(hc.is_configured){
      if(hcIsValid){
        var hcTitle = '🧢 HubcapDB 今日剩餘配額: ' + hcLeft + ' / ' + hcLimit + ' 次 (已授權)';
        hcChipHtml = '<span class="quota-chip quota-chip-hubcap" onclick="switchPage(\'credentials\')" title="' + hcTitle + '">🧢 Hubcap: <b>' + hcLeft + '</b> 次</span>';
      } else {
        hcChipHtml = '<span class="quota-chip quota-chip-expired" onclick="switchPage(\'credentials\')" title="Hubcap 金鑰過期或無效，點擊設定">🧢 Hubcap: <b>⚠️ 待設定</b></span>';
      }
    }

    // 3. Lua.tools 配額與狀態計算
    var ltAccounts = (res.lua_tools && res.lua_tools.accounts) || [];
    var ltValidAccs = ltAccounts.filter(function(a){ return _checkAccountValidHelper('lua_tools', a); });
    var ltTotalLeft = 0;
    var ltTotalLimit = 0;
    for(var j = 0; j < ltValidAccs.length; j++){
      var lacc = ltValidAccs[j];
      var llimit = parseInt(lacc.daily_limit) || 25;
      var lused = parseInt(lacc.quota_used_today) || 0;
      ltTotalLeft += Math.max(0, llimit - lused);
      ltTotalLimit += llimit;
    }

    var ltChipHtml = '';
    if(ltAccounts.length === 0){
      ltChipHtml = '<span class="quota-chip quota-chip-unlogin" onclick="switchPage(\'credentials\')" title="尚未登入 Lua.tools 帳號，點擊前往登入">🌙 Lua: <b>🔑 未登入</b></span>';
    } else if(ltValidAccs.length === 0){
      ltChipHtml = '<span class="quota-chip quota-chip-expired" onclick="switchPage(\'credentials\')" title="Lua.tools 憑證已過期，點擊重新登入">🌙 Lua: <b>⚠️ 待重登</b></span>';
    } else if(ltTotalLeft <= 0){
      ltChipHtml = '<span class="quota-chip quota-chip-exhausted" onclick="switchPage(\'credentials\')" title="今日配額已用罄，點擊查看">🌙 Lua: <b>0 次 (今日滿)</b></span>';
    } else {
      var ltTitle = '🌙 Lua.tools 今日剩餘配額: ' + ltTotalLeft + ' / ' + ltTotalLimit + ' 次 (' + ltValidAccs.length + ' 個有效帳號)';
      ltChipHtml = '<span class="quota-chip quota-chip-lua" onclick="switchPage(\'credentials\')" title="' + ltTitle + '">🌙 Lua: <b>' + ltTotalLeft + '</b> 次</span>';
    }

    box.innerHTML = rChipHtml + hcChipHtml + ltChipHtml;
  } catch(e){}
}


// ═══════════════════════════════════════════════════════
// 管理（極速秒開 + 主動全域搜尋比對，絕不拖垮視窗）
// ═══════════════════════════════════════════════════════
var _checkingUpdates = false;
var _lastUpdateCheckTime = 0;
var _knownUpdates = {};

// 🌟 主動全庫比對觸發器（開機自動跑、定時自動跑、切換頁面自動保鮮、按鈕手動強制刷新）
function startProactiveUpdateCheck(force){
  var now = Date.now();
  if(!force && (now - _lastUpdateCheckTime < 180000)) {
    // 3 分鐘內不重複發起非強制的主動背景掃描
    return;
  }
  _lastUpdateCheckTime = now;
  _checkingUpdates = true;

  try {
    if(window.pywebview && window.pywebview.api && window.pywebview.api.trigger_background_update_check){
      window.pywebview.api.trigger_background_update_check(!!force).then(function(r){
        // 已在背景守護執行緒中啟動
      }).catch(function(){ _checkingUpdates = false; });
    } else if(window.pywebview && window.pywebview.api && window.pywebview.api.check_updates_async){
      window.pywebview.api.check_updates_async(!!force).then(function(res){
        _checkingUpdates = false;
        if(res){
          if(res.updates) applyAsyncUpdates(res.updates);
          if(res.metadata) applyAsyncMetadata(res.metadata);
        }
      }).catch(function(){ _checkingUpdates = false; });
    }
  } catch(e){
    _checkingUpdates = false;
  }
}

// 🌟 即時接收後端單一遊戲比對結果（流式即時點亮，完全無感 0 卡頓）
window.onSingleGameUpdateChecked = function(u){
  try {
    if(!u || !u.appid) return;
    var aid = String(u.appid);
    _knownUpdates[aid] = u;

    // 1. 同步到全域已載入快取 _pre._games
    var statusChanged = false;
    if(_pre._games && _pre._games.length){
      for(var i=0; i<_pre._games.length; i++){
        var g = _pre._games[i];
        if(String(g.appid) === aid){
          if(g.has_update !== !!u.has_update || g.version_status !== u.version_status){
            statusChanged = true;
          }
          g.has_update = !!u.has_update;
          g.version_status = u.version_status || (u.has_update ? '可更新' : '最新版');
          g.latest_date = u.latest_date || g.latest_date;
          g.best_source = u.best_source || g.best_source;
          break;
        }
      }
    }

    // 2. 原地增量更新「管理入庫」卡片 DOM（不閃爍、不重新排版、即時精準點亮）
    var mCard = document.querySelector('#glist .card[data-appid="'+aid+'"]');
    if(mCard){
      var cornerBox = mCard.querySelector('.card-corner-tags');
      if(!cornerBox){
        mCard.insertAdjacentHTML('afterbegin', '<div class="card-corner-tags"></div>');
        cornerBox = mCard.querySelector('.card-corner-tags');
      }
      var upTag = cornerBox.querySelector('.tag-up');
      var ddEl = mCard.querySelector('.card-dd');
      if(u.has_update){
        mCard.classList.add('needs-update');
        var rawStatus = String(u.version_status || '可更新').replace(/跨越/g, '舊').replace(/⚡/g, '').trim();
        if(!upTag){
          cornerBox.insertAdjacentHTML('beforeend', '<span class="corner-tag tag-up" title="'+escHtml(rawStatus)+'">⚡ ' + escHtml(rawStatus) + '</span>');
        } else {
          upTag.textContent = '⚡ ' + rawStatus;
        }
        if(ddEl && !ddEl.querySelector('.btn-auto-up')){
          var nm = mCard.querySelector('.name') ? mCard.querySelector('.name').getAttribute('title') : ('App_' + aid);
          var upBtnHtml = '<button class="btn-auto-up" style="color:#ffd700;font-weight:bold" onclick="autoUpdateSingle(\''+aid+'\',\''+jsesc(nm)+'\')">⚡ 一鍵更新 Manifest</button>';
          ddEl.insertAdjacentHTML('afterbegin', upBtnHtml);
        }
      } else {
        mCard.classList.remove('needs-update');
        if(upTag) upTag.remove();
        if(ddEl){
          var btnAuto = ddEl.querySelector('.btn-auto-up');
          if(btnAuto) btnAuto.remove();
        }
      }
      refreshUpdateCountUI();
    }

    // 3. 原地增量更新「首頁/搜尋」卡片 DOM
    var bCard = document.querySelector('#results .card[data-appid="'+aid+'"]');
    if(bCard){
      var bCorner = bCard.querySelector('.card-corner-tags');
      if(!bCorner){
        bCard.insertAdjacentHTML('afterbegin', '<div class="card-corner-tags"></div>');
        bCorner = bCard.querySelector('.card-corner-tags');
      }
      var bUpTag = bCorner.querySelector('.tag-up');
      if(u.has_update){
        bCard.classList.add('needs-update');
        if(!bUpTag){
          bCorner.insertAdjacentHTML('beforeend', '<span class="corner-tag tag-up" title="官方有新版本可更新">⚡ 可更新</span>');
        }
      } else {
        bCard.classList.remove('needs-update');
        if(bUpTag) bUpTag.remove();
      }
    }
  } catch(e){ console.error('onSingleGameUpdateChecked error:', e); }
};

// 🌟 全庫比對完全確認後一次性推送通知（無感局部修補 DOM，絕不重新渲染整個畫面）
window.onAllUpdatesCheckFinished = function(summary){
  try {
    _checkingUpdates = false;
    if(summary && summary.updates){
      applyAsyncUpdates(summary.updates);
    }
    loadOnlineFixAppids().catch(function(){});
    var upCount = refreshUpdateCountUI();
    if(upCount > 0){
      tt('🔍 主動比對完成：發現 ' + upCount + ' 款遊戲有最新版本 Manifest 可更新！', 'in');
    }
  } catch(e){}
};

function refreshUpdateCountUI(){
  var upCount = 0;
  try {
    if(!_pre._games) return 0;
    upCount = _pre._games.filter(function(x){ return x.has_update; }).length;
    var btnBatch = document.getElementById('btn-batch-update');
    var mc = document.getElementById('mc');
    if(btnBatch){
      if(upCount > 0){
        btnBatch.style.display = 'inline-block';
        btnBatch.textContent = '⚡ 批次更新 ('+upCount+' 款可更新)';
        if(mc) mc.innerHTML = '（共 '+_pre._games.length+' 款，<b style="color:#E65100">'+upCount+' 款可更新</b>）';
      } else {
        btnBatch.style.display = 'none';
        if(mc) mc.textContent = _pre._games.length ? '（共 '+_pre._games.length+' 款）' : '';
      }
    }
  } catch(e){}
  return upCount;
}

async function rg(force){
  var filter = (document.getElementById('mf').value||'').trim().toLowerCase();
  var c = document.getElementById('glist');

  // 1. 非強制刷新（如切換頁面或背景調用）：若已有快取且 DOM 已經掛載，且無 App_xxx 殘留名稱，直接秒開返回；若 DOM 未掛載則渲染一次
  var hasUnresolvedName = _pre._games && _pre._games.some(function(g){ return !g.name || g.name.startsWith('App_'); });
  if(!force && !hasUnresolvedName && _pre._rendered && _pre._games && _pre._games.length > 0){
    if(!c || !c.querySelector('.card')){
      renderGames(_pre._games, filter);
    }
    return;
  }

  // 2. 若完全沒有任何快取，顯示骨架屏
  if(!_pre._games || !_pre._games.length){
    if(c) c.innerHTML = '<div id=glist-loading>'+_skelManage+'</div>';
  }

  try {
    // 3. 本地極速獲取最新入庫遊戲清單（~10ms），完成後只進行一次精準渲染（杜絕雙重渲染動畫）
    var games = await pywebview.api.list_games(!!hasUnresolvedName || !!force);
    _pre._games = games || [];
    if(games && games.length){
      if(!_deployedAppids) _deployedAppids = new Set();
      if(!_onlinefixAppids) _onlinefixAppids = new Set();
      games.forEach(function(g){
        var a = String(g.appid);
        if(g.deployed) _deployedAppids.add(a);
        if(g.has_onlinefix) _onlinefixAppids.add(a);
      });
    }
    _pre._rendered = true;
    renderGames(_pre._games, filter);

    // 4. 主動觸發全庫更新比對（非同步守護線程，不阻塞 UI）
    startProactiveUpdateCheck(!!force);
  } catch(e){ console.error('rg:', e); }
}

// 🌟 增量平滑修補小卡 DOM（局部操作 Class 與 Tag，杜絕全頁打碎重繪與閃爍）
function applyAsyncUpdates(updates){
  try {
    if(!_pre._games || !updates) return;
    _pre._games.forEach(function(g){
      var aid = String(g.appid);
      if(updates[aid]){
        var u = updates[aid];
        _knownUpdates[aid] = u;
        g.has_update = !!u.has_update;
        g.version_status = u.version_status || (u.has_update ? '可更新' : '最新版');
        g.latest_date = u.latest_date || g.latest_date;

        // 局部修補「管理入庫」卡片
        var mCard = document.querySelector('#glist .card[data-appid="'+aid+'"]');

        // 🌟 即時平滑替換卡片標題為官方真實遊戲名稱 (消除 App_xxx 殘留)
        if(u.name && !u.name.startsWith('App_')){
          g.name = u.name;
          if(mCard){
            var nameEl = mCard.querySelector('.name');
            if(nameEl && nameEl.textContent.trim().startsWith('App_')){
              nameEl.textContent = u.name;
              nameEl.setAttribute('title', u.name);
            }
          }
        }

        if(mCard){
          var cornerBox = mCard.querySelector('.card-corner-tags');
          if(!cornerBox){
            mCard.insertAdjacentHTML('afterbegin', '<div class="card-corner-tags"></div>');
            cornerBox = mCard.querySelector('.card-corner-tags');
          }
          var upTag = cornerBox.querySelector('.tag-up');
          var ddEl = mCard.querySelector('.card-dd');
          if(u.has_update){
            mCard.classList.add('needs-update');
            var rawStatus = String(g.version_status).replace(/跨越/g, '舊').replace(/⚡/g, '').trim();
            if(!upTag){
              cornerBox.insertAdjacentHTML('beforeend', '<span class="corner-tag tag-up" title="'+escHtml(rawStatus)+'">⚡ ' + escHtml(rawStatus) + '</span>');
            } else {
              upTag.textContent = '⚡ ' + rawStatus;
            }
            if(ddEl && !ddEl.querySelector('.btn-auto-up')){
              var nm = mCard.querySelector('.name') ? mCard.querySelector('.name').getAttribute('title') : ('App_' + aid);
              var upBtnHtml = '<button class="btn-auto-up" style="color:#ffd700;font-weight:bold" onclick="autoUpdateSingle(\''+aid+'\',\''+jsesc(nm)+'\')">⚡ 一鍵更新 Manifest</button>';
              ddEl.insertAdjacentHTML('afterbegin', upBtnHtml);
            }
          } else {
            mCard.classList.remove('needs-update');
            if(upTag) upTag.remove();
            if(ddEl){
              var btnAuto = ddEl.querySelector('.btn-auto-up');
              if(btnAuto) btnAuto.remove();
            }
          }
        }
      }
    });
    refreshUpdateCountUI();
  } catch(e){}
}

// 🌟 增量平滑更新遊戲封面與名稱元數據（局部修改 img 與 title，絕不重繪整頁）
function applyAsyncMetadata(metadata){
  try {
    if(!_pre._games || !metadata) return;
    _pre._games.forEach(function(g){
      var aid = String(g.appid);
      if(metadata[aid]){
        var m = metadata[aid];
        if(m.name && m.name !== g.name){ g.name = m.name; }
        if(m.english_name){ g.english_name = m.english_name; g.name_en = m.english_name; }
        if(m.header_image && m.header_image !== g.image){ g.image = m.header_image; }

        var mCard = document.querySelector('#glist .card[data-appid="'+aid+'"]');
        if(mCard){
          if(m.name){
            var nEl = mCard.querySelector('.name');
            if(nEl){ nEl.textContent = m.name; nEl.setAttribute('title', m.name); }
          }
          if(m.header_image){
            var imgEl = mCard.querySelector('img');
            if(imgEl) imgEl.src = m.header_image;
          }
        }
      }
    });
  } catch(e){}
}
// 篩選防抖：即時在記憶體快取中過濾，若無快取自動獲取
var _rgTimer = null;
function rgDebounce(){
  clearTimeout(_rgTimer);
  _rgTimer = setTimeout(function(){
    var filter = (document.getElementById('mf').value||'').trim().toLowerCase();
    if(_pre && _pre._games && _pre._games.length > 0){
      renderGames(_pre._games, filter);
    } else {
      rg(true);
    }
  }, 120);
}

// ═══════════════════════════════════════════════════════
// 🌟 黃色醒目更新：單個更新與全部批次自動更新 (統一委託 Downloader 調度中心)
// ═══════════════════════════════════════════════════════
async function autoUpdateSingle(appid, name){
  if(window.Downloader && Downloader.updateGame){
    return Downloader.updateGame(appid, name);
  }
}

async function autoUpdateAll(){
  if(window.Downloader && Downloader.updateAllGames){
    return Downloader.updateAllGames();
  }
}

var _manageSortMode = 'default';

function changeManageSort(){
  var sel = document.getElementById('manage-sort-mode');
  if(sel) _manageSortMode = sel.value || 'default';
  if(_pre && _pre._games){
    var filter = (document.getElementById('mf').value||'').trim().toLowerCase();
    renderGames(_pre._games, filter);
  }
}

function renderGames(games, filter){
  try {
    if(!games) games = [];
    var sel = document.getElementById('manage-sort-mode');
    if(sel) _manageSortMode = sel.value || 'default';

    // 🌟 依使用者選擇的排序規則進行排序 (預設、聯機優先、已部署優先、備份保護優先)
    games.sort(function(a, b){
      var aAid = String(a.appid), bAid = String(b.appid);
      var aUp = a.has_update ? 1 : 0, bUp = b.has_update ? 1 : 0;
      var aOf = (a.has_onlinefix || (_onlinefixAppids && _onlinefixAppids.has(aAid))) ? 1 : 0;
      var bOf = (b.has_onlinefix || (_onlinefixAppids && _onlinefixAppids.has(bAid))) ? 1 : 0;
      var aDep = (a.deployed !== undefined ? (a.deployed ? 1 : 0) : ((_deployedAppids && _deployedAppids.has(aAid)) ? 1 : 0));
      var bDep = (b.deployed !== undefined ? (b.deployed ? 1 : 0) : ((_deployedAppids && _deployedAppids.has(bAid)) ? 1 : 0));
      var aProt = (a.protected !== undefined ? (a.protected ? 1 : 0) : ((_protectedAppids && _protectedAppids.has(aAid)) ? 1 : 0));
      var bProt = (b.protected !== undefined ? (b.protected ? 1 : 0) : ((_protectedAppids && _protectedAppids.has(bAid)) ? 1 : 0));

      if(_manageSortMode === 'onlinefix'){
        if(aOf !== bOf) return bOf - aOf; // 🎮 聯機遊戲置頂
      } else if(_manageSortMode === 'deployed'){
        if(aDep !== bDep) return bDep - aDep; // ✅ 已部署遊戲置頂
      }

      // 預設規則：可更新項目 (has_update: true) 絕對置頂排列，其餘依遊戲名稱排序
      if(aUp !== bUp) return bUp - aUp;
      return (a.name || '').localeCompare(b.name || '');
    });
    if(filter){
      var q = filter.trim().toLowerCase();
      games = games.filter(function(g){
        var matchAppid = String(g.appid).indexOf(q) > -1;
        var matchName = (g.name || '').toLowerCase().indexOf(q) > -1;
        var matchEn = (g.english_name || g.name_en || '').toLowerCase().indexOf(q) > -1;
        return matchAppid || matchName || matchEn;
      });
    }
    var upCount = games.filter(function(x){ return x.has_update; }).length;
    var btnBatch = document.getElementById('btn-batch-update');
    if(btnBatch){
      if(upCount > 0){
        btnBatch.style.display = 'inline-block';
        btnBatch.textContent = '⚡ 批次更新 ('+upCount+' 款可更新)';
        document.getElementById('mc').innerHTML = '（共 '+games.length+' 款，<b style="color:#E65100">'+upCount+' 款可更新</b>）';
      } else {
        btnBatch.style.display = 'none';
        document.getElementById('mc').textContent = games.length ? '（共 '+games.length+' 款）' : '';
      }
    }
    updateManageQuota();
    var c = document.getElementById('glist');
    if(!games.length){ c.innerHTML = '<div class=empty><div class=icon>📭</div><p>暫無入庫記錄</p></div>'; _expandedDlcs = {}; return; }
    var h = '';
    for(var i=0; i<games.length; i++){
      var g = games[i];
      var nm = g.name || ('App_' + g.appid);
      var label = g.type_unknown ? ' <span class=unknown-tag>識別中…</span>' : '';
      var isUp = !!g.has_update;
      var aidStr = String(g.appid);
      var hasOf = (g.has_onlinefix !== undefined ? !!g.has_onlinefix : (_onlinefixAppids && _onlinefixAppids.has(aidStr)));
      var isDeployed = (g.deployed !== undefined ? !!g.deployed : (_deployedAppids && _deployedAppids.has(aidStr)));

      var cardClass = 'card' + (isUp ? ' needs-update' : '') + (hasOf ? ' has-onlinefix' : '');
      var rawStatus = String(g.version_status || '可更新').replace(/跨越/g, '舊').replace(/⚡/g, '').trim();
      
      // 🌟 右上角垂直堆疊標籤（從右上開始由上往下直排）
      var tagsHtml = '';
      if(hasOf) tagsHtml += '<span class="corner-tag tag-of" title="支援 Online-Fix 聯機補丁">🎮 聯機</span>';
      if(isDeployed) tagsHtml += '<span class="corner-tag tag-dep" title="本地已成功部署線上補丁">✅ 部署</span>';
      if(isUp) tagsHtml += '<span class="corner-tag tag-up" title="'+escHtml(rawStatus)+'">⚡ ' + escHtml(rawStatus) + '</span>';
      var cornerTagsDiv = tagsHtml ? '<div class="card-corner-tags">' + tagsHtml + '</div>' : '';

      var upMenuBtn = isUp ? '<button style="color:#ffd700;font-weight:bold" onclick="autoUpdateSingle(\''+g.appid+'\',\''+jsesc(nm)+'\')">⚡ 一鍵更新 Manifest</button>' : '';
      
      // 頂部：純遊戲名稱
      var topTitle = escHtml(nm) + label;
      // 底部：純粹乾淨的 AppID
      var bottomTitle = '<span class="aid-num">' + escHtml(g.appid) + '</span>';
      
      // Manifest ID 不用顯示，卡片整體更清爽工整
      h += '<div class="'+cardClass+'" data-appid="'+g.appid+'" style="--i:'+i+'" onclick="openGameDetail(\''+g.appid+'\',\''+jsesc(nm)+'\',\''+jsesc(g.image||'')+'\')">' +
             cornerTagsDiv +
             '<div class="name" title="'+escHtml(nm)+'">'+topTitle+'</div>' +
             '<img src="'+g.image+'" loading="lazy" onerror="imgFb(this,'+g.appid+')">' +
             '<button class="card-menu" title="更多選項" onclick="event.stopPropagation()"><svg viewBox="0 0 16 16" width="13" height="13" fill="currentColor"><circle cx="2.5" cy="8" r="1.5"/><circle cx="8" cy="8" r="1.5"/><circle cx="13.5" cy="8" r="1.5"/></svg></button>' +
             '<div class="card-dd" onclick="event.stopPropagation()">' +
               upMenuBtn +
                (hasOf ? '<button style="color:#00bcd4;font-weight:600" onclick="event.stopPropagation(); installOnlinePatch(\''+g.appid+'\',\''+jsesc(nm)+'\')">🚀 安裝線上補丁</button><button style="color:var(--err)" onclick="event.stopPropagation(); removeOnlinePatch(\''+g.appid+'\',\''+jsesc(nm)+'\')">🗑️ 移除線上補丁</button>' : '') +
               '<button onclick="event.stopPropagation(); editLua(\''+g.appid+'\')">📝 編輯 Lua</button>' +
               '<button class="vfbtn" onclick="event.stopPropagation(); toggleVf(\''+g.appid+'\')">'+(g.locked?'解除版本鎖定':'固定版本')+'</button>' +
               '<button onclick="event.stopPropagation(); viewDlcs(\''+g.appid+'\')">📦 查看 DLC</button>' +
               '<button onclick="event.stopPropagation(); inspectDriveStatus(\''+g.appid+'\',\''+jsesc(nm)+'\')">🌐 檢視網盤狀況</button>' +
               '<button onclick="event.stopPropagation(); delGame(\''+g.appid+'\',\''+jsesc(nm)+'\')">🗑 刪除</button>' +
             '</div>' +
             '<div class="aid" title="'+escHtml(g.appid)+'">'+bottomTitle+'</div>' +
           '</div>';
    }
    c.innerHTML = h;
    fixImgs(c);
    // 恢復已展開的 DLC（renderGames 重绘了全部 HTML）
    var baseIdx = games.length;
    for(var parentAppid in _expandedDlcs){
      var dlcs = _expandedDlcs[parentAppid];
      if(!dlcs || !dlcs.length) continue;
      var parentCard = c.querySelector('.card[data-appid="'+parentAppid+'"]');
      if(!parentCard) continue;
      var dlcH = '';
      for(var di=0; di<dlcs.length; di++){
        var d = dlcs[di];
        var dnm = d.name || ('DLC_' + d.appid);
        var dMenuBtn = d.is_embedded ? '' : '<button class="card-menu" title="更多選項" onclick="event.stopPropagation()"><svg viewBox="0 0 16 16" width="13" height="13" fill="currentColor"><circle cx="2.5" cy="8" r="1.5"/><circle cx="8" cy="8" r="1.5"/><circle cx="13.5" cy="8" r="1.5"/></svg></button>';
        var dMenu = d.is_embedded ? '' : '<div class="card-dd" onclick="event.stopPropagation()"><button onclick="event.stopPropagation(); editLua(\''+d.appid+'\')">📝 編輯 Lua</button><button class="vfbtn" onclick="event.stopPropagation(); toggleVf(\''+d.appid+'\')">'+(d.locked?'解除版本鎖定':'固定版本')+'</button><button onclick="event.stopPropagation(); inspectDriveStatus(\''+d.appid+'\',\''+jsesc(dnm)+'\')">🌐 檢視網盤狀況</button><button onclick="event.stopPropagation(); delGame(\''+d.appid+'\',\''+jsesc(dnm)+'\')">🗑 刪除</button></div>';
        
        // DLC 卡片：頂部為 DLC 名稱，底部為純數字 AppID，不顯示 Manifest ID
        dlcH += '<div class="card dlc-card" data-dlc-parent="'+parentAppid+'" data-appid="'+d.appid+'" style="--i:'+(baseIdx+di)+'">' +
                  '<div class=name title="'+escHtml(dnm)+'"><span class=dlc-tag>🏷️ DLC</span> '+escHtml(dnm)+'</div>' +
                  '<img src="'+d.image+'" loading=lazy onerror="imgFb(this,'+d.appid+')">' +
                  dMenuBtn + dMenu +
                  '<div class=aid><span class="aid-num">'+escHtml(d.appid)+'</span></div>' +
                '</div>';
      }
      parentCard.insertAdjacentHTML('afterend', dlcH);
      baseIdx += dlcs.length;
    }
    fixImgs(c); bindCardMenus(c); staggerCards(c);
  } catch(e){ document.getElementById('glist').innerHTML = '<div class=empty><p>ERR: '+(e.message||e)+'</p></div>'; }
}
// ═══════════════════════════════════════════════════════
// 網格與列表檢視模式即時切換 (toggleView)
// ═══════════════════════════════════════════════════════
function toggleView(mode){
  var sel = document.getElementById('view-mode');
  var m = mode || (sel ? sel.value : 'grid');
  var glist = document.getElementById('glist');
  if(!glist) return;

  if(m === 'list'){
    glist.classList.add('list');
  } else {
    glist.classList.remove('list');
  }

  if(sel && sel.value !== m){
    sel.value = m;
  }

  if(typeof staggerCards === 'function') staggerCards(glist);

  try { localStorage.setItem('view-mode', m); } catch(e){}
  try {
    if(window.pywebview && pywebview.api && pywebview.api.set_config){
      pywebview.api.set_config('view_mode', m);
    }
  } catch(e){}
}
// ═══════════════════════════════════════════════════════
// 管理卡片下拉功能實作：編輯 Lua、版本鎖定、查看 DLC、刪除遊戲
// ═══════════════════════════════════════════════════════
async function editLua(appid){
  if(!appid) return;
  var aid = String(appid);
  document.querySelectorAll('.card-dd.show').forEach(function(d){ d.classList.remove('show'); });
  try {
    var content = await pywebview.api.get_lua(aid);
    var modal = document.getElementById('lua-m');
    var txtEl = document.getElementById('lua-text');
    var aidEl = document.getElementById('lua-appid');
    if(!modal || !txtEl) return;
    
    if(aidEl) aidEl.textContent = 'AppID: ' + aid;
    txtEl.value = content || '';
    modal.classList.remove('hidden');

    var btnSave = document.getElementById('btn-lua-save');
    var btnClose = document.getElementById('btn-lua-close');
    
    if(btnSave){
      btnSave.onclick = async function(e){
        if(e) e.stopPropagation();
        try {
          var ok = await pywebview.api.save_lua(aid, txtEl.value);
          if(ok){
            tt('✅ Lua 儲存成功', 'ok');
            modal.classList.add('hidden');
          } else {
            tt('❌ 儲存失敗', 'er');
          }
        } catch(err){
          tt('❌ 儲存出錯: ' + (err.message || err), 'er');
        }
      };
    }
    
    if(btnClose){
      btnClose.onclick = function(e){
        if(e) e.stopPropagation();
        modal.classList.add('hidden');
      };
    }
  } catch(e){
    tt('❌ 讀取 Lua 失敗: ' + (e.message || e), 'er');
  }
}

async function toggleVf(appid){
  if(!appid) return;
  document.querySelectorAll('.card-dd.show').forEach(function(d){ d.classList.remove('show'); });
  try {
    var res = await pywebview.api.toggle_version(String(appid));
    if(res && res.ok){
      var isLocked = (res.is_locked !== undefined) ? !!res.is_locked : (res.msg && (res.msg.indexOf('解除') === -1) && (res.msg.indexOf('鎖定') > -1 || res.msg.indexOf('锁定') > -1));
      tt(res.msg || (isLocked ? '🔒 已鎖定版本' : '🔓 已解除版本鎖定'), 'ok');
      var card = document.querySelector('#glist .card[data-appid="'+appid+'"]');
      if(card){
        var btn = card.querySelector('.vfbtn');
        if(btn) btn.textContent = isLocked ? '解除版本鎖定' : '固定版本';
      }
      if(isLocked) _lockedAppids.add(String(appid));
      else _lockedAppids.delete(String(appid));
      if(_pre && _pre._games){
        for(var i=0; i<_pre._games.length; i++){
          if(String(_pre._games[i].appid) === String(appid)){
            _pre._games[i].locked = isLocked;
            break;
          }
        }
        var filter = (document.getElementById('mf').value||'').trim().toLowerCase();
        renderGames(_pre._games, filter);
      }
    } else {
      tt((res && res.msg) || '操作失敗', 'er');
    }
  } catch(e){
    tt('切換鎖定失敗: ' + (e.message || e), 'er');
  }
}
var toggleVer = toggleVf;

function viewDlcs(appid){
  document.querySelectorAll('.card-dd.show').forEach(function(d){ d.classList.remove('show'); });
  toggleDlcs(appid);
}

function delGame(appid, name){
  document.querySelectorAll('.card-dd.show').forEach(function(d){ d.classList.remove('show'); });
  ug(appid, name);
}

// 全局：给容器內卡片綁定下拉菜單事件（跳過已綁的卡片，防重復綁定）
function bindCardMenus(container){
  var fresh = container.querySelectorAll('.card:not([data-bound])');
  if(!fresh.length) return;
  fresh.forEach(function(c){ c.setAttribute('data-bound','1'); });
  var freshSet = new Set(fresh);

  // ⋯ 菜單按鈕
  container.querySelectorAll('.card-menu').forEach(function(m){
    var card = m.closest('.card');
    if(!card || !freshSet.has(card)) return;
    m.addEventListener('click', function(e){
      e.stopPropagation();
      var dd = this.nextElementSibling;
      if(!dd || !dd.classList.contains('card-dd')) return;
      if(dd.classList.contains('show')){ 
        dd.classList.remove('show'); 
      } else { 
        document.querySelectorAll('.card-dd.show').forEach(function(d){ d.classList.remove('show'); }); 
        dd.classList.add('show'); 
      }
    });
  });

  // 下拉菜單本體點擊與滾輪事件處理，徹底杜絕穿透到下方卡片並支援順暢滾動
  container.querySelectorAll('.card-dd').forEach(function(dd){
    var card = dd.closest('.card');
    if(!card || !freshSet.has(card)) return;
    dd.addEventListener('click', function(e){
      e.stopPropagation();
    });
    dd.addEventListener('wheel', function(e){
      e.stopPropagation();
    }, { passive: true });
  });
}
function _cardAid(card){ var a=card.getAttribute('data-appid'); return a ? parseInt(a) : 0; }
function _closeMenu(el){ var dd = el.closest('.card-dd'); if(dd){ dd.classList.remove('show'); } }
// 點擊空白處關閉下拉
document.addEventListener('click', function(){ document.querySelectorAll('.card-dd.show').forEach(function(d){d.classList.remove('show')}); });

async function ug(appid, name){
  var gameTitle = name || ('App ID: ' + appid);
  if(!confirm('確定要卸載「' + gameTitle + '」嗎？')) return;
  
  var aidStr = String(appid).trim();
  var card = document.querySelector('#glist .card[data-appid="'+aidStr+'"]');
  if(!card){
    var cards = document.querySelectorAll('#glist .card');
    for(var i=0; i<cards.length; i++){
      var nEl = cards[i].querySelector('.name');
      if(nEl && (nEl.textContent.indexOf(aidStr) > -1 || nEl.getAttribute('title') === name)){
        card = cards[i]; break;
      }
    }
  }

  if(card){
    card.classList.add('rm');
    await new Promise(function(r){ setTimeout(r, 220); });
  }

  try {
    var res = await pywebview.api.uninstall_game(aidStr, false);
    if(res && res.ok === false){
      if(card) card.classList.remove('rm');
      tt('❌ 卸載失敗: ' + (res.msg || '未知錯誤'), 'er');
      return;
    }

    tt((res && res.msg) || '已成功卸載入庫遊戲！', 'ok');

    // 🌟 原地精準移除特定小卡 DOM，後方卡片自動平滑遞補！
    if(card) card.remove();

    // 1. 同步更新記憶體快取 _pre._games
    if(_pre && _pre._games){
      _pre._games = _pre._games.filter(function(x){ return String(x.appid) !== aidStr; });
      var upCount = _pre._games.filter(function(x){ return x.has_update; }).length;
      var mc = document.getElementById('mc');
      if(mc){
        if(upCount > 0){
          mc.innerHTML = '（共 '+_pre._games.length+' 款，<b style="color:#E65100">'+upCount+' 款可更新</b>）';
        } else {
          mc.textContent = _pre._games.length ? '（共 '+_pre._games.length+' 款）' : '';
        }
      }
      var btnBatch = document.getElementById('btn-batch-update');
      if(btnBatch){
        if(upCount > 0){
          btnBatch.style.display = 'inline-block';
          btnBatch.textContent = '⚡ 批次更新 ('+upCount+' 款可更新)';
        } else {
          btnBatch.style.display = 'none';
        }
      }
      if(!_pre._games.length){
        var glist = document.getElementById('glist');
        if(glist) glist.innerHTML = '<div class=empty><div class=icon>📭</div><p>暫無入庫記錄</p></div>';
      }
      updateManageQuota();
      refreshUpdateCountUI();
    }

    // 2. 清理全域 Set 狀態
    if(_installedAppids) _installedAppids.delete(aidStr);
    if(_onlinefixAppids) _onlinefixAppids.delete(aidStr);
    if(_deployedAppids) _deployedAppids.delete(aidStr);
    if(_protectedAppids) _protectedAppids.delete(aidStr);

    // 3. 若首頁/搜尋頁面中包含此遊戲，原地切換其操作按鈕為「一鍵入庫」
    var bCard = document.querySelector('#results .card[data-appid="'+aidStr+'"]');
    if(bCard){
      var btnMenu = bCard.querySelector('.card-menu');
      if(btnMenu){
        btnMenu.className = 'card-menu';
        btnMenu.title = '一鍵入庫';
        btnMenu.innerHTML = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';
        btnMenu.setAttribute('onclick', "event.stopPropagation(); ag('"+aidStr+"','"+jsesc(name||'')+"')");
      }
    }

    tt('🗑️ 已卸載「' + gameTitle + '」', 'in');
  } catch(e){
    if(card) card.classList.remove('rm');
    tt('❌ 卸載出錯: ' + (e.message || e), 'er');
  }
}

async function ca(){
  var games = await pywebview.api.list_games();
  if(!games||!games.length){ tt('當前没有入庫記錄', 'in'); return; }
  if(!confirm('確定要清除全部 '+games.length+' 款入庫遊戲吗？')) return;
  try { await pywebview.api.clear_all(); tt('已清空全部入庫', 'in'); _pre._games=null; _pre._rendered=false; rg(); }
  catch(e){ tt('清空失敗', 'er'); }
}

