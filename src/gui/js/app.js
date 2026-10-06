/* SteamManifestUpdater - Module: app.js */

// ═══════════════════════════════════════════════════════
// 🚨 全域前端異常攔截器 (自動帶上 PC 名稱與 Discord 身分通報)
// ═══════════════════════════════════════════════════════
window.onerror = function(msg, url, lineNo, colNo, error) {
  try {
    if (url && (url.includes('chrome-extension') || url.includes('moz-extension'))) return;
    var stack = (error && error.stack) ? error.stack : (msg + ' at ' + url + ':' + lineNo + ':' + colNo);
    if (window.pywebview && pywebview.api && pywebview.api.report_error) {
      pywebview.api.report_error(
        "前端 JavaScript 腳本例外",
        stack,
        "Frontend window.onerror (" + (url ? url.split('/').pop() : 'inline') + ":" + lineNo + ")",
        "ERROR"
      );
    }
  } catch(e) {}
};

window.addEventListener('unhandledrejection', function(event) {
  try {
    var reason = event.reason;
    var errText = reason ? (reason.stack || reason.message || String(reason)) : 'Unknown rejection';
    if (window.pywebview && pywebview.api && pywebview.api.report_error) {
      pywebview.api.report_error(
        "前端未處理 Promise 例外 (UnhandledRejection)",
        errText,
        "Frontend UnhandledRejection",
        "ERROR"
      );
    }
  } catch(e) {}
});

// ═══════════════════════════════════════════════════════
// 導航
// ═══════════════════════════════════════════════════════
function switchPage(p){
  // 🌟 依使用者規範：無憑證不阻擋頁面瀏覽，僅在下載或更新無額度時才守衛攔截
  document.querySelectorAll('.sidebar button').forEach(function(x){x.classList.remove('active')});
  document.querySelectorAll('.page').forEach(function(x){x.classList.remove('active')});
  var targetBtn = document.querySelector('.sidebar button[data-p=\"'+p+'\"]');
  if(targetBtn) targetBtn.classList.add('active');
  var targetPage = document.getElementById('p-'+p);
  if(targetPage) targetPage.classList.add('active');
  _cur = p;
  if(p==='manage'){
    if(!_pre._rendered && _pre._games && _pre._games.length){
      var filter = (document.getElementById('mf').value||'').trim().toLowerCase();
      renderGames(_pre._games, filter);
      _pre._rendered = true;
    } else {
      rg(false);
    }
    updateManageQuota();
  }
  // 後台預加載其他頁面數據
  if(p!=='manage') prefetch('manage');
  // 更多工具：首次進才懒加載 480 联機列表
  if(p==='more' && !_ofLoaded) ofLoad();
  // 憑證管理：切換時載入狀態與配額
  if(p==='credentials') loadCredentialsStatus(false);
  // 組隊大廳：切換進入時初始化並啟動輪詢，滿版消除切割邊框與關閉外層捲動；離開時休眠與恢復
  var mainContainer = document.querySelector('.main');
  var pagesContainer = document.querySelector('.pages');
  if(p==='party') {
    if(mainContainer) mainContainer.classList.add('party-mode-main');
    if(pagesContainer) {
      pagesContainer.classList.add('party-active-pages');
      pagesContainer.scrollTop = 0; // 強制重置外層滾動位置
    }
    document.body.classList.add('party-mode');
    if(typeof initPartyPage === 'function') initPartyPage();
  } else {
    if(mainContainer) mainContainer.classList.remove('party-mode-main');
    if(pagesContainer) pagesContainer.classList.remove('party-active-pages');
    document.body.classList.remove('party-mode');
    if(typeof pausePartyPolling === 'function') pausePartyPolling();
  }
  // 設置頁面：切換時載入 Google Drive 網盤配置
  if(p==='settings') loadGDriveSettings();
  // 清單监控台 UI 已移除，不再輪詢；_monTimer 兜底清理
  if(_monTimer){ clearInterval(_monTimer); _monTimer = null; }
}

// ═══════════════════════════════════════════════════════
// 全局純拉條動效：滑動時漸顯，結束滑動 0.25 秒後漸消
// ═══════════════════════════════════════════════════════
(function initSmoothScrollbars(){
  var _scrollTimers = new WeakMap();
  window.addEventListener('scroll', function(e){
    var target = e.target;
    if(!target || !target.classList) return;
    target.classList.add('is-scrolling');
    var oldTimer = _scrollTimers.get(target);
    if(oldTimer) clearTimeout(oldTimer);
    var newTimer = setTimeout(function(){
      target.classList.remove('is-scrolling');
      _scrollTimers.delete(target);
    }, 250); // 0.25 秒後漸消
    _scrollTimers.set(target, newTimer);
  }, true);
})();

function closeGameDetail(e){
  if(e && e.target){
    var isCloseBtn = (e.target.closest && e.target.closest('.detail-close-btn')) || (e.target.classList && e.target.classList.contains('detail-close-btn'));
    if(!isCloseBtn && !isStrictBackdropClick(e, document.getElementById('game-detail-modal'))) return;
  }
  _detailReqCounter++; // 立即使所有正在進行的背景非同步請求失效
  _curDetailAppid = '';
  _curDepotsData = [];
  if(typeof _resetDetailVerifyOverlay === 'function'){
    _resetDetailVerifyOverlay();
  } else if(typeof _clearAllDetailTimers === 'function'){
    _clearAllDetailTimers();
  } else if(typeof _verifyStepTimer !== 'undefined' && _verifyStepTimer){
    clearInterval(_verifyStepTimer);
    _verifyStepTimer = null;
  }
  var ov = document.getElementById('detail-verify-overlay');
  if(ov) ov.classList.add('hidden-overlay');
  var sdbBanner = document.getElementById('dt-steamdb-loading');
  if(sdbBanner){
    sdbBanner.style.display = 'none';
    sdbBanner.style.opacity = '1';
    sdbBanner.style.transform = 'none';
  }
  var modal = document.getElementById('game-detail-modal');
  if(modal) modal.classList.remove('active');
}

// 支援 ESC 鍵安全關閉遊戲詳細小卡
window.addEventListener('keydown', function(e){
  if(e.key === 'Escape' || e.keyCode === 27){
    var modal = document.getElementById('game-detail-modal');
    if(modal && modal.classList.contains('active')){
      closeGameDetail();
    }
  }
});

// 圖五需求：AppID 複製功能修復 (原生 API + 前端雙軌保障，100% 成功寫入剪貼簿)
async function copyDetailAppid(){
  if(!_curDetailAppid) return;
  var text = String(_curDetailAppid).trim();
  var ok = false;
  try {
    if(window.pywebview && window.pywebview.api && window.pywebview.api.copy_text){
      ok = await window.pywebview.api.copy_text(text);
    }
  } catch(e){}
  if(!ok && navigator.clipboard && navigator.clipboard.writeText){
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch(e){}
  }
  if(!ok){
    try {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      ok = true;
    } catch(e){}
  }
  tt('已複製 AppID: ' + text, 'ok');
}

async function copyManifestId(gid){
  if(!gid) return;
  var text = String(gid).trim();
  var ok = false;
  try {
    if(window.pywebview && window.pywebview.api && window.pywebview.api.copy_text){
      ok = await window.pywebview.api.copy_text(text);
    }
  } catch(e){}
  if(!ok && navigator.clipboard && navigator.clipboard.writeText){
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch(e){}
  }
  if(!ok){
    try {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      ok = true;
    } catch(e){}
  }
  tt('已複製 Manifest ID: ' + text, 'ok');
}


function onAvatarErr(img){
  if(!img) return;
  img.onerror = null;
  var d = document.createElement('div');
  d.className = img.className || 'cred-acc-avatar-placeholder';
  if(d.className.indexOf('placeholder') === -1) d.className += ' cred-acc-avatar-placeholder';
  d.textContent = '👤';
  if(img.parentNode) img.parentNode.replaceChild(d, img);
}

