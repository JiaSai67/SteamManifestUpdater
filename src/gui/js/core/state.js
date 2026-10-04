/* SteamManifestUpdater - Module: core/state.js */
// ═══════════════════════════════════════════════════════
// 全局狀態
// ═══════════════════════════════════════════════════════
var _cur = 'search';
var _monTimer = null;   // 更多工具頁停留時的监控台輪詢定時器
var _monKey = '';       // 已渲染的监控快照 key（running|epoch|n|buffer），變了才重绘日志
var _scBusy = false;    // 清單自檢是否進行中（防重復點擊）

// 🌟 核心保證：bridge 雙軌就緒檢測，杜絕模組化腳本加載時差導致錯過 pywebviewready
function bootApp(){
  if(window._hasAppBooted) return;
  window._hasAppBooted = true;
  init();
  bindTitlebarDrag();
}

if(window.pywebview && window.pywebview.api){
  bootApp();
} else {
  window.addEventListener('pywebviewready', bootApp);
}

document.addEventListener('DOMContentLoaded', function(){
  bindTitlebarDrag();
  // 兜底檢查：若 DOM 已載入且 bridge 已就緒，立即啟動
  if(!window._hasAppBooted && window.pywebview && window.pywebview.api){
    bootApp();
  }
});

// 500ms 兜底檢查
setTimeout(function(){
  if(!window._hasAppBooted && window.pywebview && window.pywebview.api){
    bootApp();
  }
}, 500);

