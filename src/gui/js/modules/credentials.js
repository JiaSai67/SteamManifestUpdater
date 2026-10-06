/* SteamManifestUpdater - Module: modules/credentials.js */
// ═══════════════════════════════════════════════════════
// 憑證與帳號管理模組 (Ryuu + Lua.tools 上下融合與優先順序排序)
// ═══════════════════════════════════════════════════════
var _curCookiePlatform = 'ryuu';
var _curScanPlatform = 'ryuu';
var _credAccountsCache = {
  ryuu: [],
  lua_tools: []
};

function _isAccValid(platform, acc) {
  return acc.has_valid_credentials === true && !acc.is_expired && !acc.needs_relogin && acc.status_badge !== '憑證無效' && acc.status_badge !== '憑證已過期' && acc.status_badge !== '未登入/憑證缺失';
}

function _renderCredAccountItem(platform, acc, index, totalCount, isValid) {
  var safeName = h(String(acc.name || acc.id || 'Discord 使用者'));
  var safeEmail = acc.email ? h(String(acc.email)) : '';
  var avatarHtml = acc.avatar_url 
    ? '<img class="cred-acc-avatar" src="' + h(acc.avatar_url) + '" onerror="onAvatarErr(this)">' 
    : '<div class="cred-acc-avatar-placeholder">👤</div>';

  var used = parseInt(acc.quota_used_today) || 0;
  var limit = parseInt(acc.daily_limit) || (platform === 'ryuu' ? 50 : 25);
  var left = Math.max(0, limit - used);
  var pct = limit > 0 ? Math.min(100, Math.round((left / limit) * 100)) : 0;

  var isTopPriority = isValid && (index === 0);
  var isExhausted = (left <= 0);

  if (isValid) {
    // 🌟 具備效力的有效帳號：第一行顯示 #1 ~ #n 順位，第二行顯示剩餘配額，右側提供上移/下移/刪除
    var priorityTag = '';
    if (isTopPriority) {
      priorityTag = isExhausted ? '<span class="cred-priority-badge exhausted">#1 (用罄)</span>' : '<span class="cred-priority-badge p1">#1</span>';
    } else {
      priorityTag = isExhausted ? '<span class="cred-priority-badge exhausted">#' + (index + 1) + ' (用罄)</span>' : '<span class="cred-priority-badge p-sub">#' + (index + 1) + '</span>';
    }
    var headerRightHtml = '<div class="cred-acc-status-box">' + priorityTag + '</div>';

    var resetTipHtml = '';
    if (isExhausted && acc.reset_in_seconds && acc.reset_in_seconds > 0) {
      var rH = Math.floor(acc.reset_in_seconds / 3600);
      var rM = Math.floor((acc.reset_in_seconds % 3600) / 60);
      resetTipHtml = '<span class="cred-acc-reset-tip" style="font-size:0.75rem;color:#f59e0b;margin-left:8px">⏳ 約 ' + rH + ' 小時 ' + rM + ' 分後重設</span>';
    }

    var emailRowHtml = safeEmail 
      ? '<div class="cred-acc-email-row" title="' + safeEmail + '">' +
          '<span class="cred-acc-email-icon">📧</span>' +
          '<span class="cred-acc-email-text">' + safeEmail + '</span>' +
        '</div>' 
      : '';

    var metaRowHtml = '<div class="cred-acc-meta-left">' +
        '<span class="cred-acc-quota">剩餘配額: <b class="cred-acc-quota-text">' + left + '</b> / ' + limit + ' 次</span>' +
        resetTipHtml +
      '</div>';

    var progressBarHtml = '<div class="cred-progress-bar" style="height:4px;margin-top:3px">' +
        '<div class="cred-progress-fill" style="width:' + pct + '%"></div>' +
      '</div>';

    var rankBadge = '<div class="cred-rank-badge">' + (index + 1) + '</div>';

    var upDisabled = (index === 0) ? 'disabled' : '';
    var downDisabled = (index === totalCount - 1) ? 'disabled' : '';
    var upBtn = '<button class="btn-order" ' + upDisabled + ' onclick="moveAccountPriority(\'' + platform + '\', ' + index + ', -1)" title="向上提升調用優先權">⬆️</button>';
    var downBtn = '<button class="btn-order" ' + downDisabled + ' onclick="moveAccountPriority(\'' + platform + '\', ' + index + ', 1)" title="向下降低調用優先權">⬇️</button>';
    var deleteBtn = '<button class="btn-del-acc" onclick="deleteAccount(\'' + platform + '\', \'' + acc.id + '\', \'' + safeName.replace(/'/g, "\\'") + '\')" title="刪除此帳號">🗑️</button>';

    var activeCardClass = (isTopPriority && !isExhausted) ? 'active' : '';

    return '<div class="cred-account-item ' + activeCardClass + '">' +
      rankBadge +
      avatarHtml +
      '<div class="cred-acc-info">' +
        '<div class="cred-acc-header-row">' +
          '<span class="cred-acc-name" title="' + safeName + '">' + safeName + '</span>' +
          headerRightHtml +
        '</div>' +
        emailRowHtml +
        '<div class="cred-acc-meta">' +
          metaRowHtml +
        '</div>' +
        progressBarHtml +
      '</div>' +
      '<div class="cred-acc-actions">' +
        upBtn +
        downBtn +
        deleteBtn +
      '</div>' +
    '</div>';
  } else {
    // 🌟 需補憑證/已過期/被清除之帳號：自動置頂、外觀呈現灰色、剔除調用優先級
    // 🌟 核心排版：帳號名稱下方清楚顯示對應信箱 📧，並與「❌ 憑證過期」標籤及「🔑 重新登入」按鈕完美對齊！
    var rankBadge = '<div class="cred-rank-badge" style="opacity:0.75;background:rgba(245,158,11,0.15);color:#d97706;border-color:rgba(245,158,11,0.35);font-size:13px" title="憑證過期或已清除，需重新登入">⚠️</div>';
    
    var emailRowHtml = safeEmail 
      ? '<div class="cred-acc-email-row" title="' + safeEmail + '">' +
          '<span class="cred-acc-email-icon">📧</span>' +
          '<span class="cred-acc-email-text">' + safeEmail + '</span>' +
        '</div>' 
      : '';

    var metaRowHtml = '<div class="cred-acc-meta-left">' +
        '<span style="color:#E53935;font-size:11px;font-weight:600;display:flex;align-items:center;gap:4px">' +
          '<span>⚠️ 憑證已過期並已清除，請點擊右側重新登入</span>' +
        '</span>' +
      '</div>';
    var progressBarHtml = '<div class="cred-progress-bar" style="height:3px;margin-top:4px;background:rgba(0,0,0,0.03);opacity:0"><div class="cred-progress-fill" style="width:0%"></div></div>';
    
    var expiredBadge = '<span class="cred-expired-tag" style="background:#E53935;color:#fff;font-weight:700;font-size:11.5px;padding:4px 10px;border-radius:6px;box-shadow:0 2px 6px rgba(229,57,53,0.3);white-space:nowrap;display:inline-flex;align-items:center;justify-content:center;height:26px;box-sizing:border-box">❌ 憑證過期</span>';
    var reloginBtn = '<button class="btn btn-p btn-xs btn-relogin" onclick="event.stopPropagation();reloginAccount(\'' + platform + '\', \'' + acc.id + '\')" style="background:linear-gradient(135deg,#FF9800,#F57C00);color:#fff;font-weight:700;white-space:nowrap;padding:4px 12px;font-size:11.5px;border-radius:6px;border:none;cursor:pointer;box-shadow:0 2px 8px rgba(245,124,0,0.35);display:inline-flex;align-items:center;justify-content:center;gap:4px;height:26px;box-sizing:border-box">🔑 重新登入</button>';

    return '<div class="cred-account-item is-expired-cred">' +
      rankBadge +
      avatarHtml +
      '<div class="cred-acc-info">' +
        '<div class="cred-acc-header-row">' +
          '<span class="cred-acc-name" title="' + safeName + '">' + safeName + '</span>' +
        '</div>' +
        emailRowHtml +
        '<div class="cred-acc-meta">' +
          metaRowHtml +
        '</div>' +
        progressBarHtml +
      '</div>' +
      '<div class="cred-acc-actions" style="width:auto;min-width:auto;display:flex;align-items:center;gap:8px;justify-content:flex-end;flex-shrink:0">' +
        expiredBadge +
        reloginBtn +
      '</div>' +
    '</div>';
  }
}

function _renderCachedPlatformList(platform) {
  var list = _credAccountsCache[platform] || [];
  var targetElId = (platform === 'ryuu') ? 'ryuu-account-list' : 'luatools-account-list';
  var box = document.getElementById(targetElId);
  if (!box) return;

  if (list.length === 0) {
    var pName = (platform === 'ryuu') ? 'Ryuu' : 'Lua.tools';
    box.innerHTML = '<div class="cred-empty-state">尚無已綁定的 ' + pName + ' 帳號憑證<br><span style="font-size:10.5px">請點擊右上角「🔑 登入 / 綁定帳號」新增憑證</span></div>';
    return;
  }

  // 🌟 分離「需補憑證 (過期/已清除)」與「有效帳號」
  var expiredAccounts = [];
  var validAccounts = [];
  for (var i = 0; i < list.length; i++) {
    if (_isAccValid(platform, list[i])) {
      validAccounts.push(list[i]);
    } else {
      expiredAccounts.push(list[i]);
    }
  }

  // 🌟 核心規則：需要補憑證的使用者自動移動到最上層，但剔除優先調用序號！
  _credAccountsCache[platform] = expiredAccounts.concat(validAccounts);

  var html = '';
  // 1. 最上層：渲染需補憑證帳號 (呈現灰色、單一「重新登入」按鈕，不給 #1 序號)
  for (var exp = 0; exp < expiredAccounts.length; exp++) {
    html += _renderCredAccountItem(platform, expiredAccounts[exp], exp, expiredAccounts.length, false);
  }
  // 2. 下方：渲染有效帳號 (依序賦予 #1 ~ #n 優先調用順位)
  for (var v = 0; v < validAccounts.length; v++) {
    html += _renderCredAccountItem(platform, validAccounts[v], v, validAccounts.length, true);
  }
  box.innerHTML = html;
}

var _credAutoRefreshTimer = null;
function _startCredentialsAutoRefresh() {
  if (_credAutoRefreshTimer) clearInterval(_credAutoRefreshTimer);
  var attempts = 0;
  var maxAttempts = 25; // 25 * 1.5s = 37.5 秒自動監聽
  _credAutoRefreshTimer = setInterval(async function() {
    attempts++;
    if (attempts > maxAttempts) {
      clearInterval(_credAutoRefreshTimer);
      _credAutoRefreshTimer = null;
      return;
    }
    try {
      if (window.pywebview && pywebview.api && pywebview.api.get_credentials_status) {
        var prevExpired = (_credAccountsCache.ryuu || []).filter(function(a){ return !_isAccValid('ryuu', a); }).length +
                          (_credAccountsCache.lua_tools || []).filter(function(a){ return !_isAccValid('lua_tools', a); }).length;
        var st = await pywebview.api.get_credentials_status();
        if (st && st.ok) {
          _credAccountsCache.ryuu = (st.ryuu && st.ryuu.accounts) || [];
          _credAccountsCache.lua_tools = (st.lua_tools && st.lua_tools.accounts) || [];
          _renderCachedPlatformList('ryuu');
          _renderCachedPlatformList('lua_tools');
          updateCredentialsQuotaSummary(st);
          
          var newExpired = (_credAccountsCache.ryuu || []).filter(function(a){ return !_isAccValid('ryuu', a); }).length +
                           (_credAccountsCache.lua_tools || []).filter(function(a){ return !_isAccValid('lua_tools', a); }).length;
          if (newExpired < prevExpired || (prevExpired > 0 && newExpired === 0)) {
            tt('🎉 檢測到帳號授權完成，憑證已成功更新為正常狀態！', 'ok', 4000);
            clearInterval(_credAutoRefreshTimer);
            _credAutoRefreshTimer = null;
          }
        }
      }
    } catch(e) {
      console.warn('cred auto refresh err:', e);
    }
  }, 1500);
}

async function reloginAccount(platform, accountId){
  try {
    tt('正在開啟 ' + (platform === 'ryuu' ? 'Ryuu' : 'Lua.tools') + ' 登入視窗…', 'in');
    var res = await pywebview.api.relogin_credential_account(platform, accountId);
    if(res && res.ok){
      tt(res.msg || '已開啟登入視窗，完成授權後畫面將自動刷新！', 'ok', 5000);
      _startCredentialsAutoRefresh();
    } else {
      tt((res && res.msg) || '開啟登入視窗失敗', 'er');
    }
  } catch(e){
    tt('開啟登入視窗出錯: ' + (e.message || e), 'er');
  }
}

async function moveAccountPriority(platform, validIndex, delta) {
  var list = _credAccountsCache[platform] || [];
  var expiredAccounts = [];
  var validAccounts = [];
  for (var i = 0; i < list.length; i++) {
    if (_isAccValid(platform, list[i])) {
      validAccounts.push(list[i]);
    } else {
      expiredAccounts.push(list[i]);
    }
  }

  var targetIdx = validIndex + delta;
  if (targetIdx < 0 || targetIdx >= validAccounts.length) return;

  // 僅在有效帳號範圍內交換位置
  var temp = validAccounts[validIndex];
  validAccounts[validIndex] = validAccounts[targetIdx];
  validAccounts[targetIdx] = temp;

  _credAccountsCache[platform] = expiredAccounts.concat(validAccounts);
  _renderCachedPlatformList(platform);

  // 取得最新 ID 列表通知後端儲存
  var newIds = _credAccountsCache[platform].map(function(a) { return a.id; });
  try {
    var res = await pywebview.api.reorder_accounts(platform, newIds);
    if (res && res.ok) {
      tt('已更新 ' + (platform === 'ryuu' ? 'Ryuu' : 'Lua.tools') + ' 帳號調用優先順序', 'ok');
    } else {
      tt((res && res.msg) || '更新順序失敗', 'err');
      loadCredentialsStatus(false);
    }
  } catch (e) {
    tt('更新順序異常: ' + e, 'err');
    loadCredentialsStatus(false);
  }
}

async function openRyuuInvite(accIdOrToken, dName){
  try {
    var r2 = await pywebview.api.open_ryuu_invite();
    if(r2 && r2.msg) tt(r2.msg, 'ok');
  } catch(err){
    window.open('https://discord.gg/manifests', '_blank');
  }
}

async function verifyRyuuAccount(accId){
  sp('正在同步…', '正在向 Ryuu 網域伺服器同步即時配額…', 50);
  try {
    var res = await pywebview.api.verify_and_activate_ryuu_account(accId);
    cp();
    if(res && res.ok){
      tt(res.msg, 'ok');
      loadCredentialsStatus(false);
    } else {
      tt((res && res.msg) || '同步失敗', 'er');
    }
  } catch(e){
    cp();
    tt('同步異常: ' + (e && e.message ? e.message : e), 'er');
  }
}


// ═══════════════════════════════════════════════════════════
// 🌟 跨平台帳號配額矩陣表格渲染函數 (試算表風格)

// ═══════════════════════════════════════════════════════════
// 🌟 跨平台帳號配額矩陣表格渲染函數 (試算表風格 · 雙行資訊 + 方形弧角頭像)

// ═══════════════════════════════════════════════════════════
// 🌟 跨平台帳號配額矩陣 (現代設計 · 順位調整 · 登入/配置即時引導)

// ═══════════════════════════════════════════════════════════
// 🌟 跨平台帳號配額矩陣 (現代設計 · 拖曳順位 · 順位在上方 · 總計 0/0)

// ═══════════════════════════════════════════════════════════
// 🌟 跨平台帳號配額矩陣 (現代設計 · FLIP 絲滑拖曳換位動畫 · 總計 0/0)
// ═══════════════════════════════════════════════════════════
var _credPlatformOrder = ['ryuu', 'hubcap', 'luatools'];
var _lastCredentialsData = null;
var _matrixDraggedPlatform = null;

try {
  var savedOrder = localStorage.getItem('cred_platform_order');
  if (savedOrder) {
    var parsed = JSON.parse(savedOrder);
    if (Array.isArray(parsed) && parsed.length === 3) {
      _credPlatformOrder = parsed;
    }
  }
} catch (e) {}

var PLATFORM_CONFIG = {
  ryuu: {
    id: 'ryuu',
    name: 'ryuu',
    title: '🐉 Ryuu',
    loginAction: 'startDualPlatformSandboxLogin()',
    btnText: '🔑 立即登入'
  },
  hubcap: {
    id: 'hubcap',
    name: 'hubcapdb',
    title: '🧢 HubcapDB',
    configAction: 'openHubcapKeyInputModal()',
    btnText: '⚙️ 立即配置'
  },
  luatools: {
    id: 'luatools',
    name: 'luatools',
    title: '🌙 Lua.tools',
    loginAction: 'startDualPlatformSandboxLogin()',
    btnText: '🔑 立即登入'
  }
};

// 🌟 拖曳生命週期事件
function onMatrixDragStart(e, platformId) {
  _matrixDraggedPlatform = platformId;
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', platformId);
  }
  if (e.currentTarget) {
    e.currentTarget.classList.add('is-dragging');
  }
}

function onMatrixDragEnd(e) {
  _matrixDraggedPlatform = null;
  document.querySelectorAll('.matrix-th-draggable').forEach(function(el) {
    el.classList.remove('drag-over');
    el.classList.remove('is-dragging');
  });
}

function onMatrixDragOver(e) {
  if (e.preventDefault) e.preventDefault();
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
  var th = e.currentTarget;
  if (th && th.dataset && th.dataset.platform !== _matrixDraggedPlatform) {
    if (!th.classList.contains('drag-over')) {
      th.classList.add('drag-over');
    }
  }
  return false;
}

function onMatrixDragEnter(e) {
  if (e.preventDefault) e.preventDefault();
  var th = e.currentTarget;
  if (th && th.dataset && th.dataset.platform !== _matrixDraggedPlatform) {
    th.classList.add('drag-over');
  }
}

function onMatrixDragLeave(e) {
  var th = e.currentTarget;
  if (th && (!e.relatedTarget || !th.contains(e.relatedTarget))) {
    th.classList.remove('drag-over');
  }
}

function onMatrixDrop(e, targetPlatformId) {
  if (e.stopPropagation) e.stopPropagation();
  if (e.preventDefault) e.preventDefault();
  
  document.querySelectorAll('.matrix-th-draggable').forEach(function(el) {
    el.classList.remove('drag-over');
    el.classList.remove('is-dragging');
  });
  
  if (!_matrixDraggedPlatform || _matrixDraggedPlatform === targetPlatformId) return false;
  
  var fromIdx = _credPlatformOrder.indexOf(_matrixDraggedPlatform);
  var toIdx = _credPlatformOrder.indexOf(targetPlatformId);
  
  if (fromIdx !== -1 && toIdx !== -1) {
    _credPlatformOrder.splice(fromIdx, 1);
    _credPlatformOrder.splice(toIdx, 0, _matrixDraggedPlatform);
    
    try {
      localStorage.setItem('cred_platform_order', JSON.stringify(_credPlatformOrder));
    } catch (err) {}
    
    // 🌟 執行 FLIP 絲滑動畫重排 (純 UI 欄位視覺排版，不影響固定之核心下載檢驗順位)
    if (_lastCredentialsData) {
      renderQuotaMatrixAnimated(_lastCredentialsData, true);
    }
    tt('已更新平台檢視排版順序', 'ok');
  }
  
  _matrixDraggedPlatform = null;
  return false;
}

function _extractCleanDiscordId(acc) {
  if (!acc) return '';
  if (acc.username) {
    return acc.username.replace(/^@+/, '').trim();
  }
  var name = acc.name || '';
  var m = name.match(/\(@?([a-zA-Z0-9_\.]+)\)/);
  if (m && m[1]) {
    return m[1].trim();
  }
  return name.replace(/^@+/, '').trim();
}

// 🌟 帶 FLIP 平滑彈簧動畫的矩陣渲染器
function renderQuotaMatrixAnimated(res, triggerAnimation) {
  var table = document.querySelector('.cred-matrix-table');
  var firstPositions = {};
  
  // 1. FIRST: 記錄各直欄與儲存格在畫面上的精確 X 軸位置
  if (table && triggerAnimation) {
    var cells = table.querySelectorAll('[data-col-key]');
    cells.forEach(function(c) {
      var key = c.getAttribute('data-col-key');
      var rect = c.getBoundingClientRect();
      firstPositions[key] = rect.left;
    });
  }
  
  // 2. 重新渲染 DOM
  renderQuotaMatrix(res);
  
  // 3. LAST & INVERT & PLAY: 計算位移並執行平滑彈簧過渡
  if (table && triggerAnimation && Object.keys(firstPositions).length > 0) {
    var newTable = document.querySelector('.cred-matrix-table');
    if (!newTable) return;
    
    var newCells = newTable.querySelectorAll('[data-col-key]');
    var movingElements = [];
    
    newCells.forEach(function(c) {
      var key = c.getAttribute('data-col-key');
      var firstLeft = firstPositions[key];
      if (firstLeft !== undefined) {
        var rect = c.getBoundingClientRect();
        var deltaX = firstLeft - rect.left;
        if (Math.abs(deltaX) > 1) {
          c.style.transform = 'translateX(' + deltaX + 'px)';
          c.style.transition = 'none';
          c.classList.add('column-moving');
          movingElements.push(c);
        }
      }
    });
    
    // 強制瀏覽器 Reflow 計算
    newTable.offsetHeight;
    
    // PLAY: 施加平滑彈簧過渡動畫
    requestAnimationFrame(function() {
      movingElements.forEach(function(c) {
        c.style.transition = 'transform 0.38s cubic-bezier(0.2, 0.9, 0.3, 1.15)';
        c.style.transform = 'translateX(0)';
      });
      
      // 順位標籤彈跳特效
      var badges = newTable.querySelectorAll('.matrix-order-badge');
      badges.forEach(function(b) {
        b.classList.add('popping');
      });
      
      setTimeout(function() {
        movingElements.forEach(function(c) {
          c.style.transition = '';
          c.style.transform = '';
          c.classList.remove('column-moving');
        });
        badges.forEach(function(b) {
          b.classList.remove('popping');
        });
      }, 420);
    });
  }
}

function renderQuotaMatrix(res) {
  _lastCredentialsData = res;
  var wrap = document.getElementById('cred-matrix-table-wrap');
  if (!wrap) return;
  
  var r = res.ryuu || {};
  var hc = res.hubcap || {};
  var lt = res.lua_tools || {};
  
  var rAccounts = r.accounts || [];
  var ltAccounts = lt.accounts || [];
  
  var accountsMap = {};
  var accountOrder = [];
  
  function getAccountKey(acc) {
    if (acc.discord_id) return 'did_' + acc.discord_id;
    if (acc.email) return 'em_' + acc.email.toLowerCase().trim();
    var cid = _extractCleanDiscordId(acc);
    return cid ? ('name_' + cid.toLowerCase()) : ('acc_' + (acc.id || Math.random()));
  }
  
  for (var i = 0; i < rAccounts.length; i++) {
    var ra = rAccounts[i];
    var k = getAccountKey(ra);
    if (!accountsMap[k]) {
      var did = _extractCleanDiscordId(ra);
      accountsMap[k] = {
        key: k,
        raw_id: ra.id || '',
        discord_id: did,
        name: ra.name || did || '',
        email: ra.email || '',
        avatar_url: ra.avatar_url || '',
        ryuu: ra,
        lua: null,
        hubcap: ra.hubcap || null
      };
      accountOrder.push(k);
    } else {
      accountsMap[k].ryuu = ra;
      if (!accountsMap[k].avatar_url && ra.avatar_url) accountsMap[k].avatar_url = ra.avatar_url;
      if (!accountsMap[k].email && ra.email) accountsMap[k].email = ra.email;
      if (!accountsMap[k].discord_id) accountsMap[k].discord_id = _extractCleanDiscordId(ra);
      if (!accountsMap[k].name && ra.name) accountsMap[k].name = ra.name;
      if (ra.hubcap && (!accountsMap[k].hubcap || !accountsMap[k].hubcap.is_configured)) {
        accountsMap[k].hubcap = ra.hubcap;
      }
    }
  }
  
  for (var j = 0; j < ltAccounts.length; j++) {
    var la = ltAccounts[j];
    var lk = getAccountKey(la);
    if (!accountsMap[lk]) {
      var ldid = _extractCleanDiscordId(la);
      accountsMap[lk] = {
        key: lk,
        raw_id: la.id || '',
        discord_id: ldid,
        name: la.name || ldid || '',
        email: la.email || '',
        avatar_url: la.avatar_url || '',
        ryuu: null,
        lua: la,
        hubcap: la.hubcap || null
      };
      accountOrder.push(lk);
    } else {
      accountsMap[lk].lua = la;
      if (!accountsMap[lk].avatar_url && la.avatar_url) accountsMap[lk].avatar_url = la.avatar_url;
      if (!accountsMap[lk].email && la.email) accountsMap[lk].email = la.email;
      if (!accountsMap[lk].discord_id) accountsMap[lk].discord_id = _extractCleanDiscordId(la);
      if (!accountsMap[lk].name && la.name) accountsMap[lk].name = la.name;
      if (la.hubcap && (!accountsMap[lk].hubcap || !accountsMap[lk].hubcap.is_configured)) {
        accountsMap[lk].hubcap = la.hubcap;
      }
    }
  }
  
  if (accountOrder.length === 0) {
    wrap.innerHTML = '<div style="text-align:center;padding:36px 0;color:var(--gray);font-size:13px">' +
      '<div style="font-size:24px;margin-bottom:8px">📭</div>' +
      '尚無已綁定帳號<br>' +
      '<button class="btn btn-p btn-s" onclick="startDualPlatformSandboxLogin()" style="margin-top:10px">🔑 立即登入 Discord 綁定帳號</button>' +
    '</div>';
    return;
  }
  
  // 總計累加器
  var totals = {
    ryuu: { left: 0, limit: 0 },
    hubcap: { left: 0, limit: 0 },
    luatools: { left: 0, limit: 0 }
  };
  
  var seenHubcapKeys = {};
  for (var m = 0; m < accountOrder.length; m++) {
    var item = accountsMap[accountOrder[m]];
    if (item.ryuu && _isAccValid('ryuu', item.ryuu)) {
      var rLim = item.ryuu.daily_limit || 50;
      var rUsed = item.ryuu.quota_used_today || 0;
      var rLft = Math.max(0, rLim - rUsed);
      totals.ryuu.left += rLft;
      totals.ryuu.limit += rLim;
    }
    var itemHc = item.hubcap || (item.ryuu && item.ryuu.hubcap) || (item.lua && item.lua.hubcap);
    if (itemHc && itemHc.is_valid) {
      var hMask = itemHc.api_key_masked || ('acc_' + m);
      if (!seenHubcapKeys[hMask]) {
        seenHubcapKeys[hMask] = true;
        totals.hubcap.left += (itemHc.remaining != null ? itemHc.remaining : 0);
        totals.hubcap.limit += (itemHc.daily_limit || 25);
      }
    }
    if (item.lua && _isAccValid('lua_tools', item.lua)) {
      var lLim = item.lua.daily_limit || 25;
      var lUsed = item.lua.quota_used_today || 0;
      var lLft = Math.max(0, lLim - lUsed);
      totals.luatools.left += lLft;
      totals.luatools.limit += lLim;
    }
  }
  
  var html = '<table class="cred-matrix-table">';
  
  // ─── 表頭 (順位置頂 + 拖曳 + FLIP 動畫鍵) ───
  html += '<thead><tr>';
  html += '<th style="width:34%">帳號名稱 (固定)</th>';
  
  for (var p = 0; p < _credPlatformOrder.length; p++) {
    var pId = _credPlatformOrder[p];
    var pCfg = PLATFORM_CONFIG[pId];
    var orderNum = p + 1;
    
    html += '<th class="matrix-th-draggable" draggable="true" data-platform="' + pId + '" ' +
            'data-col-key="th_' + pId + '" ' +
            'ondragstart="onMatrixDragStart(event, \'' + pId + '\')" ' +
            'ondragend="onMatrixDragEnd(event)" ' +
            'ondragover="onMatrixDragOver(event)" ' +
            'ondragenter="onMatrixDragEnter(event)" ' +
            'ondragleave="onMatrixDragLeave(event)" ' +
            'ondrop="onMatrixDrop(event, \'' + pId + '\')" ' +
            'style="width:22%;text-align:center" title="按住並左右拖曳可自訂排版順序">';
    
    html += '<div class="matrix-th-vertical">';
    html += '<span class="matrix-th-title">' + pCfg.name + '</span>';
    html += '</div>';
    html += '</th>';
  }
  html += '</tr></thead><tbody>';
  
  var defaultAvatar = 'https://cdn.discordapp.com/embed/avatars/0.png';
  
  // ─── 判斷全機唯一 (1機1號) HubcapDB 配置狀態 ───
  var globalHc = res.hubcap || {};
  var configuredHc = null;
  var hcTargetId = '';
  var hcTargetName = '';

  for (var k = 0; k < accountOrder.length; k++) {
    var checkAcc = accountsMap[accountOrder[k]];
    var chkHc = checkAcc.hubcap || (checkAcc.ryuu && checkAcc.ryuu.hubcap) || (checkAcc.lua && checkAcc.lua.hubcap);
    if (chkHc && (chkHc.is_valid || chkHc.is_configured)) {
      configuredHc = chkHc;
      hcTargetId = checkAcc.discord_id || checkAcc.raw_id || checkAcc.key;
      hcTargetName = checkAcc.name || checkAcc.discord_id || '已綁定帳號';
      break;
    }
  }

  if (!configuredHc && (globalHc.is_valid || globalHc.is_configured)) {
    configuredHc = globalHc;
  }

  var singleHubcapCellHtml = '';
  if (configuredHc && configuredHc.is_valid) {
    var hLeft = configuredHc.remaining != null ? configuredHc.remaining : (totals.hubcap.left || 0);
    var hLimit = configuredHc.daily_limit || (totals.hubcap.limit || 25);
    singleHubcapCellHtml = '<td rowspan="' + accountOrder.length + '" class="hubcap-device-cell-td" data-col-key="r0_hubcap">' +
      '<div class="hubcap-device-cell-wrap">' +
        '<span class="hubcap-device-tag">1機1號</span>' +
        '<span class="quota-capsule' + (hLeft === 0 ? ' exhausted' : '') + '" onclick="openHubcapKeyInputModal(\'' + escHtml(hcTargetId) + '\', \'' + escHtml(hcTargetName) + '\')" style="cursor:pointer" title="點擊可變更或清除 Hubcap API Key (全機共用)">' + hLeft + ' / ' + hLimit + '</span>' +
      '</div>' +
    '</td>';
  } else if (configuredHc && configuredHc.is_configured) {
    singleHubcapCellHtml = '<td rowspan="' + accountOrder.length + '" class="hubcap-device-cell-td" data-col-key="r0_hubcap">' +
      '<div class="hubcap-device-cell-wrap">' +
        '<span class="hubcap-device-tag">1機1號</span>' +
        '<button class="matrix-btn-config" style="border-color:#F44336;color:#E53935;background:rgba(244,67,54,0.08)" onclick="openHubcapKeyInputModal(\'' + escHtml(hcTargetId) + '\', \'' + escHtml(hcTargetName) + '\')" title="' + escHtml(configuredHc.error || '金鑰驗證失敗') + '">⚠️ 重新配置</button>' +
      '</div>' +
    '</td>';
  } else {
    singleHubcapCellHtml = '<td rowspan="' + accountOrder.length + '" class="hubcap-device-cell-td" data-col-key="r0_hubcap">' +
      '<div class="hubcap-device-cell-wrap">' +
        '<span class="hubcap-device-tag">1機1號</span>' +
        '<button class="matrix-btn-config" onclick="openHubcapKeyInputModal()">⚙️ 立即配置</button>' +
      '</div>' +
    '</td>';
  }

  // ─── 資料列 (Rows) ───
  for (var rIdx = 0; rIdx < accountOrder.length; rIdx++) {
    var acc = accountsMap[accountOrder[rIdx]];
    var dIdDisplay = escHtml(acc.discord_id || '未知帳號');
    var emailDisplay = escHtml(acc.email || '無提供 Email');
    var avatarSrc = acc.avatar_url || defaultAvatar;
    var accTargetId = acc.discord_id || acc.raw_id || acc.key;
    var accTargetName = acc.name || acc.discord_id || '該帳號';
    
    var userCell = '<div class="user-cell-wrap">' +
      '<img class="user-cell-avatar" src="' + avatarSrc + '" onerror="this.src=\'' + defaultAvatar + '\'" alt="avatar" />' +
      '<div class="user-cell-info">' +
        '<div class="user-cell-discord-id">' + dIdDisplay + '</div>' +
        '<div class="user-cell-email">' + emailDisplay + '</div>' +
      '</div>' +
    '</div>';
    
    html += '<tr data-row-idx="' + rIdx + '">';
    html += '<td>' + userCell + '</td>';
    
    for (var col = 0; col < _credPlatformOrder.length; col++) {
      var colPlatform = _credPlatformOrder[col];
      var cellHtml = '';
      
      if (colPlatform === 'ryuu') {
        var rAcc = acc.ryuu;
        if (rAcc && _isAccValid('ryuu', rAcc)) {
          var rLimit = rAcc.daily_limit || 50;
          var rUsed = rAcc.quota_used_today || 0;
          var rLeft = Math.max(0, rLimit - rUsed);
          if (rLeft > 0) {
            cellHtml = '<span class="quota-capsule">' + rLeft + ' / ' + rLimit + '</span>';
          } else {
            cellHtml = '<button class="matrix-btn-login" onclick="startDualPlatformSandboxLogin()">🔑 立即登入</button>';
          }
        } else {
          cellHtml = '<button class="matrix-btn-login" onclick="startDualPlatformSandboxLogin()">🔑 立即登入</button>';
        }
        html += '<td style="text-align:center" data-col-key="r' + rIdx + '_' + colPlatform + '">' + cellHtml + '</td>';
      } else if (colPlatform === 'hubcap') {
        if (rIdx === 0) {
          html += singleHubcapCellHtml;
        }
        continue;
      } else if (colPlatform === 'luatools') {
        var ltAcc = acc.lua;
        if (ltAcc && _isAccValid('lua_tools', ltAcc)) {
          var lLimit = ltAcc.daily_limit || 25;
          var lUsed = ltAcc.quota_used_today || 0;
          var lLeft = Math.max(0, lLimit - lUsed);
          if (lLeft > 0) {
            cellHtml = '<span class="quota-capsule">' + lLeft + ' / ' + lLimit + '</span>';
          } else {
            cellHtml = '<button class="matrix-btn-login" onclick="startDualPlatformSandboxLogin()">🔑 立即登入</button>';
          }
        } else {
          cellHtml = '<button class="matrix-btn-login" onclick="startDualPlatformSandboxLogin()">🔑 立即登入</button>';
        }
        html += '<td style="text-align:center" data-col-key="r' + rIdx + '_' + colPlatform + '">' + cellHtml + '</td>';
      }
    }
    html += '</tr>';
  }
  
  // ─── 全域總計列 (Total Row) ───
  html += '<tr class="total-row">';
  html += '<td><div class="total-title-cell"><span>📊</span><span>全域可用總計 (Total)</span></div></td>';
  
  for (var t = 0; t < _credPlatformOrder.length; t++) {
    var tPlatform = _credPlatformOrder[t];
    var tot = totals[tPlatform];
    var totHtml = '';
    
    if (tPlatform === 'hubcap') {
      if (totals.hubcap.limit > 0) {
        totHtml = '<span class="quota-capsule quota-total-capsule">' + totals.hubcap.left + ' / ' + totals.hubcap.limit + '</span>';
      } else {
        totHtml = '<span class="quota-capsule quota-total-capsule" style="opacity:0.65">0 / 0</span>';
      }
    } else {
      if (tot.limit > 0 && tot.left > 0) {
        totHtml = '<span class="quota-capsule quota-total-capsule">' + tot.left + ' / ' + tot.limit + '</span>';
      } else {
        totHtml = '<span class="quota-capsule quota-total-capsule" style="opacity:0.65">0 / 0</span>';
      }
    }
    html += '<td style="text-align:center" data-col-key="total_' + tPlatform + '">' + totHtml + '</td>';
  }
  html += '</tr>';
  
  html += '</tbody></table>';
  wrap.innerHTML = html;
}

async function loadCredentialsStatus(showToast){

  try {
    var res = await pywebview.api.get_credentials_status();
    if(!res || !res.ok) return;

    // 0. 渲染左側：使用者個人資料 (User Profile) 與總額度面板
    var prof = res.user_profile || {};
    var uNameEl = document.getElementById('cred-user-name');
    var uSubTextEl = document.getElementById('cred-user-sub-text');
    var uBadgeTextEl = document.getElementById('cred-user-badge-text');
    var uAvatarText = document.getElementById('cred-user-avatar-text');
    var totalAvailEl = document.getElementById('cred-total-available');
    var totalCapEl = document.getElementById('cred-total-capacity');
    var totalBarEl = document.getElementById('cred-total-progress-bar');
    var tqRyuuEl = document.getElementById('cred-tq-ryuu');
    var tqHubcapEl = document.getElementById('cred-tq-hubcap');
    var tqLuaEl = document.getElementById('cred-tq-lua');

    if(uNameEl) uNameEl.textContent = prof.name || 'Steam 探索者';
    if(uSubTextEl) uSubTextEl.textContent = prof.sub || '本機遊戲庫模式';
    if(uBadgeTextEl){
      uBadgeTextEl.textContent = prof.is_steam_linked ? '🟢 Steam 帳號已連結' : '🟣 多平台聚合模式';
    }
    if(uAvatarText && prof.name){
      uAvatarText.textContent = prof.name.substring(0, 1).toUpperCase();
    }

    // 1. 渲染 Ryuu 狀態與多帳號清單
    var r = res.ryuu || {};
    var ryuuBadge = document.getElementById('ryuu-badge');
    var ryuuAccCount = document.getElementById('ryuu-acc-count');
    var ryuuPoolLimit = document.getElementById('ryuu-pool-limit');
    var ryuuPoolLeft = document.getElementById('ryuu-pool-left');
    var ryuuPoolBar = document.getElementById('ryuu-pool-bar');

    var rAccounts = r.accounts || [];
    _credAccountsCache.ryuu = rAccounts;

    var rTotalLimit = 0;
    var rTotalUsed = 0;
    var rValidCount = 0;
    for(var i = 0; i < rAccounts.length; i++){
      if(_isAccValid('ryuu', rAccounts[i])){
        rValidCount++;
        rTotalLimit += (rAccounts[i].daily_limit || 50);
        rTotalUsed += (rAccounts[i].quota_used_today || 0);
      }
    }
    var rTotalLeft = Math.max(0, rTotalLimit - rTotalUsed);
    var rPct = rTotalLimit > 0 ? Math.min(100, Math.round((rTotalLeft / rTotalLimit) * 100)) : 0;

    if(ryuuBadge){
      if(rValidCount > 0){
        if(rValidCount < rAccounts.length){
          ryuuBadge.className = 'cred-status-badge ok';
          ryuuBadge.textContent = '🟢 正常 · ' + rValidCount + ' / ' + rAccounts.length + ' 個帳號可用';
        } else {
          ryuuBadge.className = 'cred-status-badge ok';
          ryuuBadge.textContent = '🟢 正常 · ' + rValidCount + ' 個帳號';
        }
      } else {
        ryuuBadge.className = 'cred-status-badge err';
        ryuuBadge.textContent = rAccounts.length > 0 ? '🔴 憑證已過期 (' + rAccounts.length + ' 個需重登)' : '🔴 未登入 / 無帳號';
      }
    }
    if(ryuuAccCount) ryuuAccCount.textContent = rAccounts.length;
    if(ryuuPoolLimit) ryuuPoolLimit.textContent = rTotalLimit;
    if(ryuuPoolLeft) ryuuPoolLeft.textContent = rTotalLeft;
    if(ryuuPoolBar) ryuuPoolBar.style.width = rPct + '%';

    _renderCachedPlatformList('ryuu');

    // 2. 渲染 HubcapDB 官方 API 狀態
    var hc = res.hubcap || {};
    var hcBadge = document.getElementById('hubcap-badge');
    var hcPoolLimit = document.getElementById('hubcap-pool-limit');
    var hcPoolLeft = document.getElementById('hubcap-pool-left');
    var hcPoolBar = document.getElementById('hubcap-pool-bar');
    var hcKeyPreview = document.getElementById('hubcap-key-preview');
    var hcKeyMeta = document.getElementById('hubcap-key-meta');

    var hcLeft = hc.remaining || 0;
    var hcLimit = hc.daily_limit || (hc.is_configured ? 50 : 0);
    var hcPct = hcLimit > 0 ? Math.min(100, Math.round((hcLeft / hcLimit) * 100)) : 0;

    if(hcBadge){
      if(hc.is_valid){
        hcBadge.className = 'cred-status-badge ok';
        hcBadge.textContent = '🟢 正常 · 官方 API 授權';
      } else if(hc.is_configured){
        hcBadge.className = 'cred-status-badge err';
        hcBadge.textContent = '🔴 金鑰無效或逾時';
      } else {
        hcBadge.className = 'cred-status-badge gray';
        hcBadge.textContent = '⚪ 尚未配置 API Key';
      }
    }
    if(hcPoolLimit) hcPoolLimit.textContent = hcLimit;
    if(hcPoolLeft) hcPoolLeft.textContent = hcLeft;
    if(hcPoolBar) hcPoolBar.style.width = hcPct + '%';
    if(hcKeyPreview) hcKeyPreview.textContent = hc.api_key_masked || '未配置';
    if(hcKeyMeta){
      if(hc.is_valid){
        var resetTip = hc.resets_at ? ' · 重設時間: ' + hc.resets_at.substring(11, 19) + ' UTC' : '';
        hcKeyMeta.textContent = '今日已使用 ' + (hc.daily_usage || 0) + ' 次' + resetTip + ' · 支援高速雙格式解析';
      } else if(hc.is_configured){
        hcKeyMeta.innerHTML = '<span style="color:#E53935">⚠️ ' + (hc.error || '金鑰驗證失敗，請重新輸入有效金鑰') + '</span>';
      } else {
        hcKeyMeta.textContent = '點擊右側「⚙️ 設定 Key」貼上您在 hubcapmanifest.com/user 取得的 API Key';
      }
    }

    // 3. 渲染 Lua.tools 狀態與多帳號清單
    var lt = res.lua_tools || {};
    var ltBadge = document.getElementById('luatools-badge');
    var ltAccCount = document.getElementById('luatools-acc-count');
    var ltPoolLimit = document.getElementById('luatools-pool-limit');
    var ltPoolLeft = document.getElementById('luatools-pool-left');
    var ltPoolBar = document.getElementById('luatools-pool-bar');

    var ltAccounts = lt.accounts || [];
    _credAccountsCache.lua_tools = ltAccounts;

    var ltTotalLimit = 0;
    var ltTotalUsed = 0;
    var ltValidCount = 0;
    for(var j = 0; j < ltAccounts.length; j++){
      if(_isAccValid('lua_tools', ltAccounts[j])){
        ltValidCount++;
        ltTotalLimit += (ltAccounts[j].daily_limit || 25);
        ltTotalUsed += (ltAccounts[j].quota_used_today || 0);
      }
    }
    var ltTotalLeft = Math.max(0, ltTotalLimit - ltTotalUsed);
    var ltPct = ltTotalLimit > 0 ? Math.min(100, Math.round((ltTotalLeft / ltTotalLimit) * 100)) : 0;

    if(ltBadge){
      if(ltValidCount > 0){
        if(ltValidCount < ltAccounts.length){
          ltBadge.className = 'cred-status-badge ok';
          ltBadge.textContent = '🟢 正常 · ' + ltValidCount + ' / ' + ltAccounts.length + ' 個帳號可用';
        } else {
          ltBadge.className = 'cred-status-badge ok';
          ltBadge.textContent = '🟢 正常 · ' + ltValidCount + ' 個帳號';
        }
      } else {
        ltBadge.className = 'cred-status-badge err';
        ltBadge.textContent = ltAccounts.length > 0 ? '🔴 憑證已過期 (' + ltAccounts.length + ' 個需重登)' : '🔴 未登入 / 無帳號';
      }
    }
    if(ltAccCount) ltAccCount.textContent = ltAccounts.length;
    if(ltPoolLimit) ltPoolLimit.textContent = ltTotalLimit;
    if(ltPoolLeft) ltPoolLeft.textContent = ltTotalLeft;
    if(ltPoolBar) ltPoolBar.style.width = ltPct + '%';

    _renderCachedPlatformList('lua_tools');

    // 4. 計算並更新左側總配額統計與迷你分佈
    var allTotalLeft = rTotalLeft + (hc.is_valid ? hcLeft : 0) + ltTotalLeft;
    var allTotalCap = rTotalLimit + (hc.is_valid ? hcLimit : 0) + ltTotalLimit;
    var allPct = allTotalCap > 0 ? Math.min(100, Math.round((allTotalLeft / allTotalCap) * 100)) : 0;

    if(totalAvailEl) totalAvailEl.textContent = allTotalLeft;
    if(totalCapEl) totalCapEl.textContent = allTotalCap;
    if(totalBarEl) totalBarEl.style.width = allPct + '%';
    if(tqRyuuEl) tqRyuuEl.textContent = rTotalLeft;
    if(tqHubcapEl) tqHubcapEl.textContent = hc.is_valid ? hcLeft : 0;
    if(tqLuaEl) tqLuaEl.textContent = ltTotalLeft;

    // 5. 渲染偏好設定
    var s = res.settings || {};
    var pSel = document.getElementById('pref-source-select');
    if(pSel && s.preferred_source) pSel.value = s.preferred_source;

    // 🌟 渲染跨平台帳號配額矩陣總覽表
    renderQuotaMatrix(res);

    var tRot = document.getElementById('t-auto-rotate');
    if(tRot) tRot.checked = !!s.auto_rotate;

    if(showToast) tt('憑證與配額狀態已更新', 'ok');

    // 🌟 同步更新管理頁面頂部配額晶片狀態
    if(typeof updateManageQuota === 'function') updateManageQuota();

    // 若啟動環境檢測彈窗當前處於開啟可見狀態，才連動靜默更新字卡資訊
    var modalWiz = document.getElementById('modal-startup-wizard');
    if(modalWiz && !modalWiz.classList.contains('hidden') && modalWiz.style.display !== 'none'){
      runPrereqCheck(false);
    }
  } catch(e){
    console.error('loadCredentialsStatus error:', e);
  }
}

// ═══════════════════════════════════════════════════════
// HubcapDB API Key 彈窗與管理互動函式
// ═══════════════════════════════════════════════════════
function openHubcapKeyInputModal(targetAccountId, targetAccountName){
  window._currentHubcapTargetAccount = targetAccountId || '';
  window._currentHubcapTargetAccountName = targetAccountName || '';
  var modal = document.getElementById('modal-hubcap-key');
  var input = document.getElementById('input-hubcap-api-key');
  var subTitle = document.getElementById('modal-hubcap-subtitle');
  if(!modal) return;
  if(input) input.value = '';
  if(subTitle) {
    if(targetAccountName) {
      subTitle.textContent = '正在為【' + targetAccountName + '】設定專屬 Hubcap API Key';
    } else {
      subTitle.textContent = '可點擊下方「⚡ 無痕沙盒一鍵登入」自動獲取，或手動貼上 API 金鑰';
    }
  }
  modal.style.display = 'flex';
  modal.classList.remove('hidden');
  if(input) setTimeout(function(){ input.focus(); }, 100);
}

function closeHubcapKeyModal(){
  window._currentHubcapTargetAccount = '';
  window._currentHubcapTargetAccountName = '';
  var modal = document.getElementById('modal-hubcap-key');
  if(modal){
    modal.style.display = 'none';
    modal.classList.add('hidden');
  }
}

async function startHubcapSandboxLogin(targetAccountId){
  var targetId = targetAccountId || window._currentHubcapTargetAccount || '';
  closeHubcapKeyModal();
  tt('正在啟動 HubcapDB 專屬無痕沙盒登入視窗…', 'ok');
  try {
    var res = await pywebview.api.open_hubcap_sandbox_login(targetId);
    if(res && res.ok){
      tt(res.msg || '已啟動 HubcapDB 無痕沙盒，登入後將自動捕獲 API Key', 'ok');
      var pollCount = 0;
      var pollTimer = setInterval(function(){
        pollCount++;
        loadCredentialsStatus(false);
        if(pollCount >= 30) clearInterval(pollTimer);
      }, 2000);
    } else {
      tt((res && res.msg) || '啟動失敗', 'err');
    }
  } catch(e){
    tt('啟動登入異常: ' + e, 'err');
  }
}

async function submitHubcapApiKey(){
  var input = document.getElementById('input-hubcap-api-key');
  var key = input ? input.value.trim() : '';
  var targetAcc = window._currentHubcapTargetAccount || '';
  sp('正在驗證…', '正在向 HubcapDB 伺服器驗證 API Key…', 50);
  try {
    var res = await pywebview.api.save_hubcap_api_key(key, targetAcc);
    cp();
    if(res && res.ok){
      tt(res.msg || 'HubcapDB API Key 設定成功！', 'ok', 4000);
      closeHubcapKeyModal();
      loadCredentialsStatus(false);
    } else {
      tt((res && res.msg) || 'API Key 驗證失敗', 'err', 5000);
    }
  } catch(e){
    cp();
    tt('設定 Hubcap 金鑰出錯: ' + e, 'err');
  }
}

// ═══════════════════════════════════════════════════════
// 平台連線測試與快捷操作函式
// ═══════════════════════════════════════════════════════
async function testCredConn(platform){
  var pNames = { ryuu: 'Ryuu', hubcap: 'HubcapDB', lua_tools: 'Lua.tools' };
  var name = pNames[platform] || platform;
  sp('連線測試中…', '正在測試 ' + name + ' 伺服器連線…', 50);
  try {
    var res = await pywebview.api.test_credential_connection(platform);
    cp();
    if(res && res.ok){
      tt(res.msg || (name + ' 連線正常！'), 'ok', 4000);
    } else {
      tt((res && res.msg) || (name + ' 連線失敗'), 'err', 5000);
    }
  } catch(e){
    cp();
    tt(name + ' 測試異常: ' + e, 'err');
  }
}

async function syncRyuuAllQuotas(){
  sp('同步中…', '正在向 Ryuu 伺服器同步即時配額…', 50);
  try {
    await loadCredentialsStatus(false);
    cp();
    tt('已向 Ryuu 伺服器同步最新配額', 'ok');
  } catch(e){
    cp();
    tt('同步異常: ' + e, 'err');
  }
}

async function clearInvalidCreds(){
  if(!confirm('確定要清除所有已過期的無效帳號憑證嗎？\n有效帳號將完整保留。')) return;
  sp('清理中…', '正在清除過期憑證…', 50);
  try {
    var res = await pywebview.api.clear_invalid_credentials();
    cp();
    if(res && res.ok){
      tt('已成功清除過期無效憑證', 'ok');
      loadCredentialsStatus(false);
    } else {
      tt((res && res.msg) || '清理失敗', 'err');
    }
  } catch(e){
    cp();
    tt('清理異常: ' + e, 'err');
  }
}

async function switchActiveAccount(platform, accountId){
  try {
    tt('正在切換使用中帳號…', 'warn');
    var res = await pywebview.api.switch_active_account(platform, accountId);
    if(res && res.ok){
      tt('已成功切換使用中帳號！', 'ok');
      loadCredentialsStatus(false);
    } else {
      tt((res && res.msg) || '切換失敗', 'err');
    }
  } catch(e){
    tt('切換帳號異常: ' + e, 'err');
  }
}

async function deleteAccount(platform, accountId, accountName){
  if(!confirm('確定要刪除帳號憑證 [' + accountName + '] 嗎？\n系統將直接同步刪除雙平台（Ryuu 與 Lua.tools）的關聯憑證。')) return;
  try {
    var res = await pywebview.api.delete_credential_account(platform, accountId);
    if(res && res.ok){
      tt('已成功同步刪除雙平台帳號憑證', 'ok');
      loadCredentialsStatus(false);
    } else {
      tt((res && res.msg) || '刪除失敗', 'err');
    }
  } catch(e){
    tt('刪除帳號異常: ' + e, 'err');
  }
}

async function openDiscordLoginWindow(platform){
  startDualPlatformSandboxLogin();
}

// ═══════════════════════════════════════════════════════
// 雙軌登入授權管理：正常登入 (雙平台無痕沙盒) vs 一鍵登入 (本機 Token 挑選/排除)
// ═══════════════════════════════════════════════════════
var _scannedFastAccounts = [];
var _selectedFastIndices = new Set();

function openLoginMethodSelectorModal(){
  startDualPlatformSandboxLogin();
}

function closeLoginMethodSelectorModal(){}

async function startDualPlatformSandboxLogin(){
  tt('正在啟動雙平台安全登入視窗，請在彈出的視窗中登入 Discord…', 'ok');
  try {
    var res = await pywebview.api.open_dual_platform_sandbox_login();
    if(res && res.ok){
      tt(res.msg || '已啟動雙平台獨立無痕沙盒登入視窗', 'ok');
      // 自動持續定時輪詢刷新狀態，即時抓取雙平台綁定結果
      var pollCount = 0;
      var pollTimer = setInterval(function(){
        pollCount++;
        loadCredentialsStatus(false);
        if(pollCount >= 30) clearInterval(pollTimer);
      }, 2000);
    } else {
      tt((res && res.msg) || '啟動登入視窗失敗', 'err');
    }
  } catch(e){
    tt('啟動登入異常: ' + e, 'err');
  }
}

function openImageLightbox(src, title){
  var modal = document.getElementById('modal-image-lightbox');
  var img = document.getElementById('lightbox-image');
  var titleEl = document.getElementById('lightbox-title');
  if(!modal || !img) return;
  img.src = src;
  if(titleEl && title) titleEl.textContent = title;
  modal.style.display = 'flex';
  modal.classList.remove('hidden');
}

function closeImageLightbox(){
  var modal = document.getElementById('modal-image-lightbox');
  if(modal){
    modal.style.display = 'none';
    modal.classList.add('hidden');
  }
}

// 支援鍵盤 ESC 關閉燈箱
window.addEventListener('keydown', function(e){
  if(e.key === 'Escape' || e.keyCode === 27){
    closeImageLightbox();
  }
});

