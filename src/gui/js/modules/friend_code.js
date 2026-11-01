/* SteamManifestUpdater - Module: friend_code.js (友邀代碼：無伺服器點對點打包加密與一鍵解密安裝) */

var _fcHostPollTimer = null;
var _fcRecvPollTimer = null;
var _fcWebhookSaveTimer = null;
var _fcPreviewDebounce = null;
var _fcPreviewSeq = 0;
var _fcInspectReady = false;
var _fcCurrentResult = null;
var _fcHistoryCache = [];

function _fcEsc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function _fcFmtSize(bytes) {
  var b = Number(bytes || 0);
  if (!b || b <= 0) return '';
  var mb = b / (1024 * 1024);
  if (mb >= 1) return mb.toFixed(2) + ' MB';
  return (b / 1024).toFixed(1) + ' KB';
}

function _setFcBadge(id, cls, text) {
  var el = document.getElementById(id);
  if (!el) return;
  el.className = 'fc-badge' + (cls ? ' ' + cls : '');
  el.textContent = text;
}

function _fcToast(msg) {
  if (typeof toast === 'function') {
    toast(msg);
  }
}

async function _fcCopyText(text, successMsg) {
  if (!text) return;
  try {
    if (window.pywebview && pywebview.api && pywebview.api.write_clipboard_text) {
      var res = await pywebview.api.write_clipboard_text(String(text));
      if (res && res.ok) {
        _fcToast(successMsg || '📋 已複製至剪貼簿！');
        return;
      }
    }
  } catch (e) {}
  try {
    await navigator.clipboard.writeText(String(text));
    _fcToast(successMsg || '📋 已複製至剪貼簿！');
  } catch (e2) {
    _fcToast('⚠️ 複製失敗，請手動選取文字複製');
  }
}

// ═══════════════════════════════════════════════════════════════════════
// 初始化與頁面切換掛載
// ═══════════════════════════════════════════════════════════════════════

async function initFriendCodePage() {
  if (!window.pywebview || !pywebview.api || !pywebview.api.get_friend_code_init_data) return;
  try {
    var res = await pywebview.api.get_friend_code_init_data();
    if (!res || !res.ok) return;

    var whInput = document.getElementById('fc-input-webhook');
    if (whInput && !whInput.value.trim() && res.webhook_url) {
      whInput.value = res.webhook_url;
    }

    _renderFcGamesDropdown(res.games || []);
    _fcHistoryCache = res.history || [];
    _renderFcHistoryList(_fcHistoryCache);

    if (res.host_progress && res.host_progress.state === 'running') {
      _applyFcHostProgress(res.host_progress);
      _startFcHostPolling();
    } else if (res.host_progress && res.host_progress.result && !_fcCurrentResult) {
      _fcCurrentResult = res.host_progress.result;
      _renderFcGeneratedResult(_fcCurrentResult);
    }

    if (res.install_progress && res.install_progress.state === 'running') {
      _applyFcRecvProgress(res.install_progress);
      _startFcRecvPolling();
    }

    _updateFcGenerateBtnState();
  } catch (e) {
    console.warn('[FriendCode] 初始化異常:', e);
  }
}

async function refreshFcReadyGames() {
  if (!window.pywebview || !pywebview.api) return;
  try {
    var games = await pywebview.api.get_ready_games_for_friend_code();
    _renderFcGamesDropdown(games || []);
    _fcToast('🔄 已重新掃描本機可打包之聯機遊戲');
  } catch (e) {
    _fcToast('⚠️ 掃描遊戲清單失敗');
  }
}

function _renderFcGamesDropdown(games) {
  var sel = document.getElementById('fc-select-game');
  if (!sel) return;
  var prevVal = sel.value || '';
  var html = '<option value="">-- 請挑選本機已入庫且已安裝線上補丁的遊戲 --</option>';
  if (games && games.length > 0) {
    for (var i = 0; i < games.length; i++) {
      var g = games[i];
      var aid = String(g.appid || '');
      var nm = g.name || ('AppID ' + aid);
      var selected = (aid === prevVal) ? ' selected' : '';
      html += '<option value="' + _fcEsc(aid) + '" data-name="' + _fcEsc(nm) + '"' + selected + '>🎮 ' + _fcEsc(nm) + ' (AppID: ' + _fcEsc(aid) + ')</option>';
    }
  } else {
    html = '<option value="">⚠️ 尚未偵測到已安裝線上補丁的遊戲（請先於遊戲入庫/管理入庫完成部署）</option>';
  }
  sel.innerHTML = html;
  if (sel.value) {
    onFcGameSelectChange();
  } else {
    _fcInspectReady = false;
    _resetFcInspectChips();
    _updateFcGenerateBtnState();
  }
}

function _resetFcInspectChips() {
  var m = document.getElementById('fc-chip-manifest');
  var l = document.getElementById('fc-chip-lua');
  var p = document.getElementById('fc-chip-patch');
  if (m) { m.className = 'fc-res-chip'; m.textContent = '📄 Manifest'; }
  if (l) { l.className = 'fc-res-chip'; l.textContent = '📜 Lua 腳本'; }
  if (p) { p.className = 'fc-res-chip'; p.textContent = '🎮 線上補丁'; }
  _setFcBadge('fc-host-badge', '', '分享方');
}

async function onFcGameSelectChange() {
  var sel = document.getElementById('fc-select-game');
  var aid = sel ? (sel.value || '').trim() : '';
  if (!aid) {
    _fcInspectReady = false;
    _resetFcInspectChips();
    _updateFcGenerateBtnState();
    return;
  }

  var m = document.getElementById('fc-chip-manifest');
  var l = document.getElementById('fc-chip-lua');
  var p = document.getElementById('fc-chip-patch');
  if (m) { m.className = 'fc-res-chip'; m.textContent = '📄 Manifest …'; }
  if (l) { l.className = 'fc-res-chip'; l.textContent = '📜 Lua 腳本 …'; }
  if (p) { p.className = 'fc-res-chip'; p.textContent = '🎮 線上補丁 …'; }
  _setFcBadge('fc-host-badge', 'warn', '檢查中');

  try {
    var insp = await pywebview.api.inspect_party_resources(aid);
    var mOk = !!(insp && insp.manifest && insp.manifest.ready);
    var lOk = !!(insp && insp.lua && insp.lua.ready);
    var pOk = !!(insp && insp.patch && insp.patch.ready);

    if (m) {
      m.className = 'fc-res-chip ' + (mOk ? 'ok' : 'bad');
      m.textContent = mOk ? ('✓ Manifest (' + (insp.manifest.count || 1) + ')') : '✕ Manifest';
    }
    if (l) {
      l.className = 'fc-res-chip ' + (lOk ? 'ok' : 'bad');
      l.textContent = lOk ? '✓ Lua 腳本' : '✕ Lua 腳本';
    }
    if (p) {
      p.className = 'fc-res-chip ' + (pOk ? 'ok' : 'bad');
      p.textContent = pOk ? '✓ 線上補丁' : '✕ 線上補丁';
    }

    _fcInspectReady = !!(mOk && lOk && pOk);
  } catch (e) {
    _fcInspectReady = false;
  }
  _setFcBadge('fc-host-badge', _fcInspectReady ? 'ok' : 'err', _fcInspectReady ? '三檔就緒' : '三檔不全');
  _updateFcGenerateBtnState();
}

function _isFcValidWebhookFormat(url) {
  if (!url) return false;
  return /^https:\/\/(?:(?:canary|ptb)\.)?discord(?:app)?\.com\/api\/webhooks\/\d+\/[A-Za-z0-9_-]+\/?(?:\?.*)?$/i.test(url.trim());
}

function onFcWebhookInput() {
  var el = document.getElementById('fc-input-webhook');
  var val = el ? el.value.trim() : '';
  _updateFcGenerateBtnState();

  // 清除先前的測試結果框
  var box = document.getElementById('fc-webhook-test-result');
  if (box) box.style.display = 'none';

  // 同步更新組隊大廳之 Webhook 欄位（共用記憶）
  var partyWh = document.getElementById('input-party-discord-webhook');
  if (partyWh && val) {
    partyWh.value = val;
  }

  if (_fcWebhookSaveTimer) clearTimeout(_fcWebhookSaveTimer);
  _fcWebhookSaveTimer = setTimeout(function() {
    if (val && _isFcValidWebhookFormat(val) && window.pywebview && pywebview.api && pywebview.api.save_discord_webhook) {
      pywebview.api.save_discord_webhook(val).catch(function() {});
    }
  }, 400);
}

async function testFcWebhookConnection() {
  var el = document.getElementById('fc-input-webhook');
  var val = el ? el.value.trim() : '';
  if (!val) {
    _fcToast('⚠️ 請先貼上 Discord Webhook 網址');
    return;
  }
  var btn = document.getElementById('btn-fc-test-webhook');
  var box = document.getElementById('fc-webhook-test-result');
  var oldTxt = btn ? btn.textContent : '🔗 測試';
  if (btn) { btn.disabled = true; btn.textContent = '測試中…'; }
  try {
    var res = await pywebview.api.test_discord_webhook(val);
    if (res && res.ok) {
      _fcToast(res.msg || '✅ Discord Webhook 連線測試成功！');
      if (box) {
        var name = (res.details && res.details.name) || 'Discord Webhook';
        var chId = (res.details && res.details.channel_id) ? '<span style="font-family:monospace;font-size:11px;background:rgba(0,0,0,0.06);padding:2px 6px;border-radius:4px">' + _fcEsc(res.details.channel_id) + '</span>' : '';
        box.className = 'fc-verify-banner valid';
        box.style.display = 'block';
        box.innerHTML = '<div style="display:flex;align-items:flex-start;gap:8px">'
          + '<span style="font-size:16px;line-height:1">✅</span>'
          + '<div style="flex:1;min-width:0">'
          + '<div style="font-weight:700;color:#10B981;font-size:12.5px;margin-bottom:2px">連線測試成功！已成功發送測試通知</div>'
          + '<div style="font-size:11.5px;color:var(--fg);opacity:0.9">對接 Webhook：<b>' + _fcEsc(name) + '</b> ' + (chId ? '（頻道 ID：' + chId + '）' : '') + '</div>'
          + '<div style="font-size:10.5px;color:var(--gray);margin-top:3px">💡 無需前往 Discord 查看，本機已收到 Discord 伺服器成功應答並確認具備上傳權限。</div>'
          + '</div>'
          + '</div>';
      }
      _updateFcGenerateBtnState();
    } else {
      var err = (res && res.msg) || 'Webhook 連線失敗';
      _fcToast('❌ ' + err);
      if (box) {
        box.className = 'fc-verify-banner invalid';
        box.style.display = 'block';
        box.innerHTML = '<div style="display:flex;align-items:flex-start;gap:8px">'
          + '<span style="font-size:16px;line-height:1">❌</span>'
          + '<div style="flex:1;min-width:0">'
          + '<div style="font-weight:700;color:#EF4444;font-size:12px;margin-bottom:2px">連線測試未通過</div>'
          + '<div style="font-size:11px;color:var(--fg);opacity:0.9">' + _fcEsc(err) + '</div>'
          + '</div>'
          + '</div>';
      }
    }
  } catch (e) {
    _fcToast('❌ 測試異常: ' + e);
    if (box) {
      box.className = 'fc-verify-banner invalid';
      box.style.display = 'block';
      box.innerHTML = '<span style="color:#EF4444;font-size:11.5px">❌ 測試異常：' + _fcEsc(String(e)) + '</span>';
    }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = oldTxt; }
  }
}

function openFcWebhookTutorialModal() {
  var modal = document.getElementById('modal-fc-webhook-guide');
  if (modal) {
    modal.style.display = 'flex';
    modal.classList.remove('hidden');
    modal.classList.add('active');
    var card = modal.querySelector('.webhook-tutorial-card');
    if (card) {
      card.classList.remove('fade-in-active');
      setTimeout(function() {
        card.classList.add('fade-in-active');
      }, 50);
    }
    var vid = document.getElementById('fc-webhook-guide-video');
    if (vid && typeof vid.play === 'function') {
      try {
        vid.currentTime = 0;
        vid.play().catch(function(err) {
          console.warn('[FriendCode] Webhook 教學影片播放:', err);
        });
      } catch (e) {}
    }
  }
}

function closeFcWebhookTutorialModal() {
  var modal = document.getElementById('modal-fc-webhook-guide');
  if (modal) {
    modal.style.display = 'none';
    modal.classList.remove('active');
    modal.classList.add('hidden');
    var vid = document.getElementById('fc-webhook-guide-video');
    if (vid && typeof vid.pause === 'function') {
      try { vid.pause(); } catch (e) {}
    }
  }
}

function _updateFcGenerateBtnState() {
  var btn = document.getElementById('btn-fc-generate');
  if (!btn) return;
  var sel = document.getElementById('fc-select-game');
  var wh = document.getElementById('fc-input-webhook');
  var hasGame = !!(sel && sel.value);
  var hasWh = !!(wh && _isFcValidWebhookFormat(wh.value));
  var canGo = hasGame && _fcInspectReady && hasWh && !_fcHostPollTimer;
  btn.disabled = !canGo;
  if (!hasGame) {
    btn.title = '請先選擇要打包分享的遊戲';
  } else if (!_fcInspectReady) {
    btn.title = '所選遊戲本地三檔尚未齊全';
  } else if (!hasWh) {
    btn.title = '請填寫正確的 Discord Webhook 網址';
  } else {
    btn.title = '立即封裝三檔並生成加密友邀代碼';
  }
}

// ═══════════════════════════════════════════════════════════════════════
// 發起方：打包上傳並加密生成友邀代碼
// ═══════════════════════════════════════════════════════════════════════

async function submitGenerateFriendCode() {
  var sel = document.getElementById('fc-select-game');
  var wh = document.getElementById('fc-input-webhook');
  if (!sel || !sel.value) {
    _fcToast('⚠️ 請先選擇要打包的遊戲');
    return;
  }
  var appId = sel.value.trim();
  var opt = sel.options[sel.selectedIndex];
  var gameName = (opt && opt.getAttribute('data-name')) ? opt.getAttribute('data-name') : appId;
  var webhookUrl = wh ? wh.value.trim() : '';

  if (!_isFcValidWebhookFormat(webhookUrl)) {
    _fcToast('⚠️ 請輸入有效的 Discord Webhook 網址');
    return;
  }

  var btn = document.getElementById('btn-fc-generate');
  if (btn) btn.disabled = true;

  var errBox = document.getElementById('fc-host-error-box');
  if (errBox) errBox.style.display = 'none';

  try {
    var res = await pywebview.api.start_generate_friend_code(appId, gameName, webhookUrl);
    if (!res || !res.ok) {
      _fcToast('❌ ' + ((res && res.msg) || '啟動打包失敗'));
      if (errBox) {
        errBox.textContent = '❌ ' + ((res && res.msg) || '啟動打包失敗');
        errBox.style.display = 'block';
      }
      _updateFcGenerateBtnState();
      return;
    }
    var progWrap = document.getElementById('fc-host-progress-wrap');
    if (progWrap) progWrap.style.display = 'block';
    _startFcHostPolling();
  } catch (e) {
    _fcToast('❌ 打包請求異常: ' + e);
    _updateFcGenerateBtnState();
  }
}

function _startFcHostPolling() {
  if (_fcHostPollTimer) clearInterval(_fcHostPollTimer);
  _fcHostPollTimer = setInterval(async function() {
    try {
      var res = await pywebview.api.get_friend_code_host_progress();
      if (!res || !res.ok || !res.data) return;
      _applyFcHostProgress(res.data);
    } catch (e) {}
  }, 450);
  _updateFcGenerateBtnState();
}

function _stopFcHostPolling() {
  if (_fcHostPollTimer) {
    clearInterval(_fcHostPollTimer);
    _fcHostPollTimer = null;
  }
  _updateFcGenerateBtnState();
}

async function _applyFcHostProgress(d) {
  var progWrap = document.getElementById('fc-host-progress-wrap');
  var bar = document.getElementById('fc-host-bar');
  var txt = document.getElementById('fc-host-status-text');
  var pctEl = document.getElementById('fc-host-pct');
  var errBox = document.getElementById('fc-host-error-box');

  if (progWrap) progWrap.style.display = 'block';
  var pct = Math.max(0, Math.min(100, Number(d.progress || 0)));
  if (bar) bar.style.width = pct + '%';
  if (txt) txt.textContent = d.status_text || '處理中…';
  if (pctEl) pctEl.textContent = pct + '%';

  if (d.state === 'success') {
    _stopFcHostPolling();
    _setFcBadge('fc-host-badge', 'ok', '已生成');
    if (progWrap) {
      setTimeout(function() { progWrap.style.display = 'none'; }, 1000);
    }
    if (d.result) {
      _fcCurrentResult = d.result;
      _renderFcGeneratedResult(d.result);
    }
    try {
      var hRes = await pywebview.api.get_friend_code_history();
      if (hRes && hRes.ok) {
        _fcHistoryCache = hRes.history || [];
        _renderFcHistoryList(_fcHistoryCache);
      }
    } catch (e) {}
    _fcToast('🎉 友邀代碼生成完畢！點擊即可複製傳給好友');
  } else if (d.state === 'error') {
    _stopFcHostPolling();
    if (errBox && d.error_msg) {
      errBox.textContent = '❌ ' + d.error_msg;
      errBox.style.display = 'block';
    }
    _fcToast('❌ ' + (d.error_msg || '打包失敗'));
  }
}

function _renderFcGeneratedResult(item) {
  var wrap = document.getElementById('fc-result-card');
  if (!wrap || !item || !item.code) return;
  wrap.style.display = 'block';

  var metaEl = document.getElementById('fc-result-meta');
  var codeEl = document.getElementById('fc-result-code-text');
  var sizeStr = _fcFmtSize(item.size);
  var partTag = item.is_multipart ? (' · ' + (item.total_parts || 2) + ' 分卷') : ' · 單檔極速包';
  if (metaEl) {
    metaEl.innerHTML = '🎮 <b>' + _fcEsc(item.game_name) + '</b> <span style="opacity:.8">(AppID: ' + _fcEsc(item.app_id) + (sizeStr ? ' · ' + sizeStr : '') + partTag + ')</span><br>'
      + '<span style="font-size:10.5px;opacity:.82">🕒 加密時間戳：' + _fcEsc(item.created_at) + ' ｜ 長度：' + item.code.length + ' 碼純英數</span>';
  }
  if (codeEl) {
    codeEl.textContent = item.code;
  }
}

function copyCurrentFriendCodeRaw() {
  if (!_fcCurrentResult || !_fcCurrentResult.code) return;
  _fcCopyText(_fcCurrentResult.code, '📋 已複製純英數友邀代碼！可直接傳給好友');
}

function copyCurrentFriendCodeInvite() {
  if (!_fcCurrentResult || !_fcCurrentResult.code) return;
  var msg = '🎮 一起玩《' + (_fcCurrentResult.game_name || '聯機遊戲') + '》！\n'
    + '打開 SMU 左側「🎫 友邀代碼」貼上以下代碼，即可自動解密下載並安裝：\n'
    + '〖' + _fcCurrentResult.code + '〗';
  _fcCopyText(msg, '💬 已複製完整好友邀請訊息！可直接貼到 Discord / LINE');
}

function _renderFcHistoryList(list) {
  var box = document.getElementById('fc-history-list');
  var sec = document.getElementById('fc-history-section');
  var cnt = document.getElementById('fc-history-count');
  if (!box || !sec) return;

  if (!list || list.length === 0) {
    sec.style.display = 'none';
    box.innerHTML = '';
    return;
  }
  sec.style.display = 'block';
  if (cnt) cnt.textContent = list.length + ' 筆';

  var html = '';
  for (var i = 0; i < list.length; i++) {
    var it = list[i];
    var sz = _fcFmtSize(it.size);
    var pInfo = it.is_multipart ? (it.total_parts + '卷') : '單檔';
    html += '<div class="fc-history-item">'
      + '<div class="fc-history-meta">'
      + '<div class="fc-history-title">🎮 ' + _fcEsc(it.game_name) + ' <span style="font-weight:400;opacity:.75">(' + _fcEsc(it.app_id) + ')</span></div>'
      + '<div class="fc-history-sub">🕒 ' + _fcEsc(it.created_at) + (sz ? ' · ' + sz : '') + ' · ' + pInfo + '</div>'
      + '</div>'
      + '<div style="display:flex;gap:5px;flex-shrink:0">'
      + '<button type="button" class="btn btn-p btn-xs" onclick="copyFcHistoryItem(\'' + _fcEsc(it.id) + '\')" title="複製此筆友邀代碼">📋 複製</button>'
      + '<button type="button" class="btn btn-o btn-xs" onclick="revokeFcHistoryItem(\'' + _fcEsc(it.id) + '\')" style="color:#ef4444;border-color:rgba(239,68,68,.35)" title="刪除 Discord 頻道上的整合包檔案並使此代碼失效">🗑️ 撤銷</button>'
      + '</div>'
      + '</div>';
  }
  box.innerHTML = html;
}

function copyFcHistoryItem(itemId) {
  for (var i = 0; i < _fcHistoryCache.length; i++) {
    if (_fcHistoryCache[i].id === itemId) {
      _fcCurrentResult = _fcHistoryCache[i];
      _renderFcGeneratedResult(_fcCurrentResult);
      _fcCopyText(_fcHistoryCache[i].code, '📋 已複製《' + _fcHistoryCache[i].game_name + '》友邀代碼！');
      return;
    }
  }
}

async function revokeFcHistoryItem(itemId) {
  if (!itemId) return;
  try {
    var res = await pywebview.api.revoke_friend_code_item(itemId);
    if (res && res.ok) {
      _fcHistoryCache = res.history || [];
      _renderFcHistoryList(_fcHistoryCache);
      if (_fcCurrentResult && _fcCurrentResult.id === itemId) {
        _fcCurrentResult = null;
        var card = document.getElementById('fc-result-card');
        if (card) card.style.display = 'none';
      }
      _fcToast(res.msg || '✅ 已撤銷友邀代碼');
    } else {
      _fcToast('❌ ' + ((res && res.msg) || '撤銷失敗'));
    }
  } catch (e) {
    _fcToast('❌ 撤銷異常: ' + e);
  }
}

// ═══════════════════════════════════════════════════════════════════════
// 接收方：貼上代碼、本地離線解密預覽與五階段全自動下載安裝
// ═══════════════════════════════════════════════════════════════════════

async function pasteFriendCodeFromClipboard() {
  var text = '';
  try {
    if (window.pywebview && pywebview.api && pywebview.api.read_clipboard_text) {
      var res = await pywebview.api.read_clipboard_text();
      if (res && res.ok && res.text) {
        text = res.text;
      }
    }
  } catch (e) {}

  if (!text) {
    try {
      text = await navigator.clipboard.readText();
    } catch (e2) {}
  }

  if (!text || !text.trim()) {
    _fcToast('⚠️ 剪貼簿目前沒有文字內容');
    return;
  }

  var input = document.getElementById('fc-input-code');
  if (input) {
    input.value = text.trim();
    onFriendCodeInputChange();
  }
}

function clearFriendCodeInput() {
  var input = document.getElementById('fc-input-code');
  if (input) input.value = '';
  var banner = document.getElementById('fc-verify-banner');
  if (banner) banner.style.display = 'none';
  var btn = document.getElementById('btn-fc-redeem');
  if (btn && !_fcRecvPollTimer) btn.disabled = true;
}

function onFriendCodeInputChange() {
  var input = document.getElementById('fc-input-code');
  var raw = input ? input.value.trim() : '';
  var banner = document.getElementById('fc-verify-banner');
  var btn = document.getElementById('btn-fc-redeem');

  if (!raw) {
    if (banner) banner.style.display = 'none';
    if (btn && !_fcRecvPollTimer) btn.disabled = true;
    return;
  }

  if (_fcPreviewDebounce) clearTimeout(_fcPreviewDebounce);
  var mySeq = ++_fcPreviewSeq;

  _fcPreviewDebounce = setTimeout(async function() {
    try {
      // 第一步：0.5ms 純本地離線解密校驗
      var localRes = await pywebview.api.preview_friend_code(raw, false);
      if (mySeq !== _fcPreviewSeq) return;

      if (!localRes || !localRes.ok) {
        if (banner) {
          banner.className = 'fc-verify-banner invalid';
          banner.style.display = 'block';
          banner.innerHTML = '⚠️ <b>本地解密未通過：</b>' + _fcEsc((localRes && localRes.msg) || '代碼不完整或有誤');
        }
        if (btn && !_fcRecvPollTimer) btn.disabled = true;
        return;
      }

      if (btn && !_fcRecvPollTimer) btn.disabled = false;
      if (banner) {
        banner.className = 'fc-verify-banner valid';
        banner.style.display = 'block';
        banner.innerHTML = '✅ <b>本地加密簽章核驗通過！</b>（發布時間：' + _fcEsc(localRes.created_at) + '）<br>'
          + '<span style="opacity:.85">⏳ 正在向雲端讀取整合包遊戲資訊…</span>';
      }

      // 第二步：非同步向 Discord Webhook 預覽遊戲名稱與大小
      var remoteRes = await pywebview.api.preview_friend_code(raw, true);
      if (mySeq !== _fcPreviewSeq) return;

      if (remoteRes && remoteRes.ok && remoteRes.remote_verified) {
        var sz = _fcFmtSize(remoteRes.size);
        var pTag = remoteRes.is_multipart ? ('共 ' + (remoteRes.total_parts || 2) + ' 分卷') : '單檔極速包';
        if (banner) {
          banner.className = 'fc-verify-banner valid';
          banner.innerHTML = '✅ <b>本地解密與雲端檔案核驗通過！</b><br>'
            + '🎮 遊戲：<b>' + _fcEsc(remoteRes.game_name) + '</b> '
            + '<span style="opacity:.85">(AppID: ' + _fcEsc(remoteRes.app_id || '自動識別') + (sz ? ' · ' + sz : '') + ' · ' + pTag + ')</span><br>'
            + '<span style="font-size:10.5px;opacity:.82">🕒 好友打包時間：' + _fcEsc(remoteRes.created_at) + '</span>';
        }
      } else if (remoteRes && !remoteRes.ok) {
        if (banner) {
          banner.className = 'fc-verify-banner invalid';
          banner.innerHTML = '❌ <b>雲端檔案已失效：</b>' + _fcEsc(remoteRes.msg || '整合包已被刪除');
        }
        if (btn && !_fcRecvPollTimer) btn.disabled = true;
      }
    } catch (e) {}
  }, 140);
}

async function submitRedeemFriendCode() {
  var input = document.getElementById('fc-input-code');
  var raw = input ? input.value.trim() : '';
  if (!raw) {
    _fcToast('⚠️ 請先貼上好友分享的友邀代碼');
    return;
  }

  var btn = document.getElementById('btn-fc-redeem');
  if (btn) btn.disabled = true;

  var errBox = document.getElementById('fc-recv-error-box');
  if (errBox) errBox.style.display = 'none';

  try {
    var res = await pywebview.api.start_redeem_friend_code(raw);
    if (!res || !res.ok) {
      _fcToast('❌ ' + ((res && res.msg) || '無法啟動安裝'));
      if (errBox) {
        errBox.textContent = '❌ ' + ((res && res.msg) || '無法啟動安裝');
        errBox.style.display = 'block';
      }
      if (btn) btn.disabled = false;
      return;
    }

    var wrap = document.getElementById('fc-recv-progress-wrap');
    if (wrap) wrap.style.display = 'block';
    _startFcRecvPolling();
  } catch (e) {
    _fcToast('❌ 啟動安裝異常: ' + e);
    if (btn) btn.disabled = false;
  }
}

function _startFcRecvPolling() {
  if (_fcRecvPollTimer) clearInterval(_fcRecvPollTimer);
  var cancelBtn = document.getElementById('btn-fc-cancel-install');
  if (cancelBtn) cancelBtn.style.display = 'inline-flex';
  var redeemBtn = document.getElementById('btn-fc-redeem');
  if (redeemBtn) redeemBtn.disabled = true;

  _fcRecvPollTimer = setInterval(async function() {
    try {
      var res = await pywebview.api.get_friend_code_install_progress();
      if (!res || !res.ok || !res.data) return;
      _applyFcRecvProgress(res.data);
    } catch (e) {}
  }, 600);
}

function _stopFcRecvPolling() {
  if (_fcRecvPollTimer) {
    clearInterval(_fcRecvPollTimer);
    _fcRecvPollTimer = null;
  }
  var cancelBtn = document.getElementById('btn-fc-cancel-install');
  if (cancelBtn) cancelBtn.style.display = 'none';
  var redeemBtn = document.getElementById('btn-fc-redeem');
  var input = document.getElementById('fc-input-code');
  if (redeemBtn && input && input.value.trim()) {
    redeemBtn.disabled = false;
  }
}

function _applyFcRecvProgress(d) {
  var wrap = document.getElementById('fc-recv-progress-wrap');
  var bar = document.getElementById('fc-recv-bar');
  var txt = document.getElementById('fc-recv-status-text');
  var pctEl = document.getElementById('fc-recv-pct');
  var gameEl = document.getElementById('fc-recv-game-title');
  var spdEl = document.getElementById('fc-recv-speed');
  var errBox = document.getElementById('fc-recv-error-box');

  if (wrap) wrap.style.display = 'block';
  var pct = Math.max(0, Math.min(100, Number(d.progress || 0)));
  if (bar) bar.style.width = pct + '%';
  if (txt) txt.textContent = d.status_text || '執行中…';
  if (pctEl) pctEl.textContent = pct + '%';
  if (d.state === 'running') _setFcBadge('fc-recv-badge', 'warn', '安裝中');
  else if (d.state === 'success') _setFcBadge('fc-recv-badge', 'ok', '安裝完成');
  else if (d.state === 'error') _setFcBadge('fc-recv-badge', 'err', '安裝失敗');
  else if (d.state === 'cancelled') _setFcBadge('fc-recv-badge', '', '已中止');

  if (gameEl) {
    var gLabel = d.game_name ? ('🎮 ' + d.game_name + (d.app_id ? ' (AppID: ' + d.app_id + ')' : '')) : '🎮 正在解析目標遊戲…';
    gameEl.textContent = gLabel;
  }
  if (spdEl) {
    spdEl.textContent = d.speed_str ? ('⚡ ' + d.speed_str) : (d.size_str ? ('📦 ' + d.size_str) : '');
  }

  // 更新五階段膠囊燈號
  var curStage = Number(d.stage || 1);
  for (var s = 1; s <= 5; s++) {
    var pill = document.getElementById('fc-stage-' + s);
    if (!pill) continue;
    if (d.state === 'success' || s < curStage) {
      pill.className = 'fc-stage-pill done';
    } else if (s === curStage && d.state === 'running') {
      pill.className = 'fc-stage-pill active';
    } else {
      pill.className = 'fc-stage-pill';
    }
  }

  if (d.state === 'success') {
    _stopFcRecvPolling();
    if (errBox) errBox.style.display = 'none';
    if (typeof _pre !== 'undefined' && _pre) {
      _pre._rendered = false;
    }
    refreshFcReadyGames();
    _fcToast('🎉 友邀代碼全自動下載、入庫與聯機補丁安裝完成！');
  } else if (d.state === 'error') {
    _stopFcRecvPolling();
    if (errBox && d.error_msg) {
      errBox.textContent = '❌ ' + d.error_msg;
      errBox.style.display = 'block';
    }
    _fcToast('❌ ' + (d.error_msg || '自動安裝失敗'));
  } else if (d.state === 'cancelled') {
    _stopFcRecvPolling();
  }
}

async function cancelFcRedeemInstall() {
  try {
    await pywebview.api.cancel_friend_code_install();
    _stopFcRecvPolling();
    _fcToast('⏹️ 已中止下載安裝任務');
  } catch (e) {}
}

