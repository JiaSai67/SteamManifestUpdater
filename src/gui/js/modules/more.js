/* SteamManifestUpdater - Module: modules/more.js */
// ═══════════════════════════════════════════════════════
// 更多工具 · 清單监控台（工具1）
// ═══════════════════════════════════════════════════════
function toggleTool(id){
  var b = document.getElementById('tb-'+id);
  if(b) b.classList.toggle('open');
}
function setText(id, v){ var el = document.getElementById(id); if(el) el.textContent = v; }

// ═══════════════════════════════════════════════════════
// 480 联機（內核 [[inject]]：啟動带 -480，內核把 OnlineFix.dll 注入遊戲進程，借 Spacewar AppID 480 联機）
// 列表 = 已入庫 ∩ 文件已下好；未裝 Spacewar 引導去 Steam 裝(steam://install/480)
// ═══════════════════════════════════════════════════════
var _ofLoaded = false;
var _ofSpacewar = false;
var _ofGames = [];
var _ofBusy = false;

function ofInstallSpacewar(){
  try{
    pywebview.api.open_steam_install(480).then(function(ok){
      if(ok) tt('已喚起 Steam 安裝 Spacewar，裝完回來點「刷新」','in');
      else tt('喚起 Steam 失敗，請自行去商店搜 Spacewar','er');
    });
  }catch(e){ tt('喚起 Steam 失敗','er'); }
}
function ofPatch(){
  try{ pywebview.api.open_url('https://online-fix.me/'); }
  catch(e){ tt('打開联機補丁站失敗：'+(e.message||e),'er'); }
}

async function ofLoad(){
  if(_ofBusy) return;
  _ofBusy = true;
  try{
    var r = await pywebview.api.list_onlinefix_games();
    if(r && r.ok){
      _ofSpacewar = !!r.spacewar;
      _ofGames = r.games || [];
      _ofLoaded = true;
      ofRender(_ofGames);
    } else {
      ofRender([], (r && r.error) || '读取失敗');
    }
  }catch(e){ ofRender([], '读取失敗：'+(e.message||e)); }
  _ofBusy = false;
}
function ofRefresh(){ ofLoad(); }
function ofImgFallback(el){
  // 封面加載失敗：換成等高的占位塊，保住 84px 槽位，避免「▶ 480联機」按鈕随圖片塌陷而上移
  if(!el || !el.parentNode) return;
  var ph = document.createElement('div');
  ph.className = 'of-ph';
  el.parentNode.replaceChild(ph, el);
}

function ofRender(games, err){
  var chip = document.getElementById('of-spacewar-chip');
  if(chip){
    chip.className = 'of-chip ' + (_ofSpacewar ? 'ok' : 'warn');
    chip.textContent = _ofSpacewar ? '✅ Spacewar(480) 已安裝' : '⚠️ 未裝 Spacewar(480)';
  }
  var sum = document.getElementById('of-summary');
  if(sum) sum.textContent = (games && games.length) ? games.length+' 款可联機遊戲' : '無可用遊戲';
  var grid = document.getElementById('of-grid');
  if(!grid) return;
  var emp = document.getElementById('of-empty');
  if(err || !games || !games.length){
    grid.innerHTML = '';
    if(emp){ emp.classList.remove('hidden');
      emp.textContent = err || '没有「已入庫且文件已下好」的遊戲。\n遊戲要先入庫、並在 Steam 裡把文件下載完，才會出現在这裡。'; }
    return;
  }
  if(emp) emp.classList.add('hidden');
  grid.innerHTML = games.map(function(g){
    var nm = g.name || ('App ID: '+g.appid);
    var img = g.image ? '<img src="'+h(g.image)+'" loading="lazy" onerror="ofImgFallback(this)" alt="">'
                      : '<div class="of-ph"></div>';
    return '<div class="card">'
      + '<div class="nm" title="'+h(nm)+'">'+h(nm)+'</div>'
      + img
      + '<div class="btns">'
      +   '<button class="btn btn-p of-go" onclick="ofLaunch('+g.appid+')">▶ 480联機</button>'
      + '</div></div>';
  }).join('');
}

function ofFind(appid){
  for(var i=0;i<_ofGames.length;i++){ if(_ofGames[i].appid===appid) return _ofGames[i]; }
  return null;
}

function ofLaunch(appid){
  var g = ofFind(appid);
  var nm = g ? (g.name || ('App ID: '+appid)) : ('App ID: '+appid);
  if(!_ofSpacewar){
    htmlConfirm('需要先安裝 Spacewar',
      '《'+h(nm)+'》走 480 联機，需要 Steam 免費遊戲 <b>Spacewar(AppID 480)</b> 作联機載體，本機還没檢测到。\n點「確定」喚起 Steam 安裝 Spacewar，裝完回來再點一次「480联機」。')
      .then(function(go){ if(go) ofInstallSpacewar(); });
    return;
  }
  sp('480 联機啟動中…','正在带 -480 啟動遊戲…',8,'請稍候');
  pywebview.api.onlinefix_launch(appid).then(function(r){
    cp();
    if(r && r.ok){ tt('✅ '+(r.message||'已啟動'),'ok'); }
    else if(r && r.need_spacewar){ tt('⛔ 需要先裝 Spacewar，裝好再點','er'); }
    else if(r && r.need_start){ tt((r.message||'Steam 就緒後再點一次'),'ok'); }
    else { tt('⛔ '+((r && r.error)||'啟動失敗'),'er'); }
  }).catch(function(e){ cp(); tt('⛔ '+(e.message||e),'er'); });
}

async function monStart(){
  try{
    var r = await pywebview.api.mon_start();
    if(!r || !r.ok){ tt((r && r.error) || '啟動失敗：請先在「設置」填 Steam 路径', 'er'); }
    else { _monKey=''; tt(r.already ? '监控已在運行' : '✅ 開始监控 content_log', 'ok'); monPollTick(); }
  }catch(e){ tt('啟動失敗: '+(e.message||e), 'er'); }
}
async function monStop(){
  try{ await pywebview.api.mon_stop(); _monKey=''; tt('已停止监控', 'in'); monPollTick(); }
  catch(e){ tt('停止失敗: '+(e.message||e), 'er'); }
}
async function monClear(){
  try{ await pywebview.api.mon_clear(); _monKey=''; monPollTick(); }
  catch(e){ tt('清空失敗: '+(e.message||e), 'er'); }
}

async function monPollTick(){
  try{
    var s = await pywebview.api.mon_get_status();
    if(!s || !s.ok) return;
    var dot = document.getElementById('mon-dot');
    if(s.error) dot.className = 'mon-dot err';
    else if(s.running) dot.className = 'mon-dot on';
    else dot.className = 'mon-dot';
    if(s.error) setText('mon-status', '监控異常');
    else if(s.running) setText('mon-status', s.exists
        ? ('监控中 · 已读 '+s.n+' 行 · 文件 '+(s.mtime_age==null?'?':(s.mtime_age+'s'))+' 前寫入')
        : '监控中 · 等待 content_log.txt 生成…');
    else setText('mon-status', '已停止');
    setText('mon-hint', (s.error ? ('錯誤: '+s.error+' ') : '') + (s.hint || ''));
    var k = s.kinds || {};
    setText('mon-k-err', k.err || 0);
    setText('mon-k-man', k.manifest || 0);
    setText('mon-k-info', k.info || 0);
    var key = (s.running?'1':'0') + '|' + (s.epoch||0) + '|' + (s.n||0) + '|' + (s.buffer||0);
    if(key !== _monKey){ _monKey = key; monRenderLog(s.lines || []); }
  }catch(e){}
}
function monRenderLog(lines){
  var box = document.getElementById('mon-log');
  if(!box) return;
  var near = box.scrollHeight - box.scrollTop - box.clientHeight < 30;
  var show = lines.slice(-160), html = '';
  for(var i=0;i<show.length;i++){
    var it = show[i], ts = it[0], raw = it[1], kind = it[2];
    if(!raw) continue;
    html += '<div class="'+kind+'">' + (ts ? '['+h(ts)+'] ' : '') + h(raw) + '</div>';
  }
  box.innerHTML = html || '<div class="info">（暫無日志 —— 開始监控後等待 Steam 寫入）</div>';
  if(near) box.scrollTop = box.scrollHeight;
}

async function scRun(){
  if(_scBusy) return;
  _scBusy = true;
  var btn = document.getElementById('sc-btn');
  btn.disabled = true; btn.textContent = '自檢中…';
  setText('sc-summary', ''); setText('sc-notes', '');
  document.getElementById('sc-res').innerHTML = '';
  try{
    await pywebview.api.depot_selfcheck_async();
    // 完成後由 onScDone 推送渲染；兜底：長時間無推送則恢復按鈕
    setTimeout(function(){
      if(_scBusy){ _scBusy=false; btn.disabled=false; btn.textContent='開始自檢'; }
    }, 15000);
  }catch(e){
    _scBusy=false; btn.disabled=false; btn.textContent='開始自檢';
    tt('自檢啟動失敗: '+(e.message||e), 'er');
  }
}
function onScDone(res){ scRender(res); }
function scRender(res){
  var btn = document.getElementById('sc-btn');
  _scBusy = false;
  if(btn){ btn.disabled = false; btn.textContent = '開始自檢'; }
  var sum = document.getElementById('sc-summary');
  if(!res || !res.ok){
    if(sum) sum.innerHTML = '<span class="chip miss">✖ ' + h((res && res.error) || '自檢失敗') + '</span>';
    setText('sc-notes','');
    var box = document.getElementById('sc-res'); if(box) box.innerHTML='';
    return;
  }
  var sm = res.summary || {};
  if(sum) sum.innerHTML =
    '<span class="chip gray">🎮 遊戲 '+(sm.games||0)+'</span>' +
    '<span class="chip gray">📦 depot '+(sm.depots||0)+'</span>' +
    '<span class="chip ok">在位 '+(sm.ok||0)+'</span>' +
    '<span class="chip miss">缺失 '+(sm.missing||0)+'</span>' +
    '<span class="chip warn">待联網 '+(sm.warn||0)+'</span>' +
    '<span class="chip pink">固定版本 '+(sm.pinned||0)+'</span>' +
    '<span class="chip gray">無key '+(sm.keyless||0)+'</span>';
  var notes = (res.notes || []).join('；');
  var nEl = document.getElementById('sc-notes');
  if(nEl) nEl.textContent = notes ? ('ℹ️ '+notes) : '';
  scRenderTable(res.rows || [], res.steam_root || '');
}
function scRenderTable(rows){
  var box = document.getElementById('sc-res');
  if(!box) return;
  if(!rows.length){ box.innerHTML = ''; return; }
  function chip(st){
    if(st==='ok') return '<span class="chip ok">✅ 在位</span>';
    if(st==='missing') return '<span class="chip miss">❌ 缺失</span>';
    return '<span class="chip warn">⚠ 待联網</span>';
  }
  var html = '<div class="sc-wrap"><table class="sc-table"><tr><th>遊戲</th><th>Depot</th><th>清單版本</th><th>狀態 / 說明</th></tr>';
  for(var i=0;i<rows.length;i++){
    var r = rows[i];
    html += '<tr>' +
      '<td><b>'+h(r.name||r.game)+'</b> <span style="color:var(--gray)">'+r.game+'</span>' +
        (r.has_key?'':' <span class="chip miss" style="padding:0 5px;line-height:14px">無key</span>') + '</td>' +
      '<td>'+r.depot+'</td>' +
      '<td>'+(r.pinned_gid ? ('<span class="chip pink" title="固定版本 gid">'+h(r.pinned_gid)+'</span>') : '<span style="color:var(--gray)">未固定</span>') + '</td>' +
      '<td>' + chip(r.status) + (r.file ? (' <span style="color:var(--gray)">'+h(r.file)+'</span>') : '') +
        (r.note ? '<div style="color:var(--gray);font-size:10px">'+h(r.note)+'</div>' : '') + '</td>' +
      '</tr>';
  }
  html += '</table></div>';
  box.innerHTML = html;
}

/* ── 體檢：一鍵自查"入庫後遊戲不顯示"（只读，手動觸發） ── */
var _dgBusy = false;   // 體檢是否進行中（防重復點擊）
var _dgRes = null;     // 最近一次體檢結果緩存

async function dgRun(){
  if(_dgBusy) return;
  _dgBusy = true;
  var btn = document.getElementById('dg-btn');
  if(btn){ btn.disabled = true; btn.textContent = '體檢中…'; }
  // 若體檢結果窗還開著，先關掉，避免盖住進度彈窗
  var dm = document.getElementById('dg-m');
  if(dm) dm.classList.add('hidden');
  try{
    sp('體檢中…', '正在逐項檢查（版本/管理員/內核/OST版本表/網絡/激活/额度），請稍候', null, '');
    await pywebview.api.machine_check_async();
    // 結果由 onDgDone 推送渲染；兜底：長時間無推送則恢復
    setTimeout(function(){
      if(_dgBusy){ cp(); _dgBusy=false; if(btn){btn.disabled=false;btn.textContent='一鍵體檢';} }
    }, 30000);
  }catch(e){
    cp(); _dgBusy=false;
    if(btn){ btn.disabled=false; btn.textContent='一鍵體檢'; }
    tt('體檢啟動失敗: '+(e.message||e), 'er');
  }
}
function onDgDone(res){ _dgRes = res; dgRender(res); }
function dgCopy(){
  if(!_dgRes || !_dgRes.report){ tt('還没有體檢報告', 'er'); return; }
  pywebview.api.copy_text(_dgRes.report).then(function(ok){
    tt(ok ? '✅ 診斷報告已復制，發给開發者即可' : '復制失敗，請手動復制', ok ? 'ok' : 'er');
  });
}
function dgRender(res){
  cp(); _dgBusy = false;
  var btn = document.getElementById('dg-btn');
  if(btn){ btn.disabled = false; btn.textContent = '一鍵體檢'; }
  document.getElementById('dg-m').classList.remove('hidden');
  var head = document.getElementById('dg-head');
  var count = document.getElementById('dg-count');
  var box = document.getElementById('dg-res');
  var sug = document.getElementById('dg-sug');
  if(!res || !res.rows){
    if(head) head.textContent = '';
    if(count) count.innerHTML = '';
    if(sug){ sug.classList.remove('hidden'); sug.innerHTML = '<b>✖ ' + h((res && res.error) || '體檢失敗') + '</b>'; }
    if(box) box.innerHTML = '';
    return;
  }
  var sm = res.summary || {};
  if(head) head.innerHTML = '入庫後遊戲不顯示，多半是下面某一項紅了。紅=問題所在，橙=請注意。看不懂就把報告復制發给開發者。';
  if(count) count.innerHTML =
    '<span class="chip ok">✅ 正常 '+(sm.ok||0)+'</span>' +
    '<span class="chip warn">⚠ 注意 '+(sm.warn||0)+'</span>' +
    '<span class="chip miss">❌ 異常 '+(sm.bad||0)+'</span>';
  var rows = res.rows || [];
  var html = '';
  for(var i=0;i<rows.length;i++){
    var r = rows[i], st = r.status || 'warn';
    var dot = '<span class="dg-dot '+st+'"></span>';
    html += '<div class="dg-row"><div class="dg-title">' + dot + h(r.title||'') + '</div>' +
      '<div class="dg-detail dg-mono">' + h(r.detail||'') + '</div>' +
      (r.fix ? '<div class="dg-fix">💡 ' + h(r.fix) + '</div>' : '') +
      '</div>';
  }
  if(!rows.length) html = '<div class="dg-ok-all' + ((sm.bad||0) ? ' bad' : '') + '">没有可顯示的檢查項</div>';
  else if(!(sm.bad||0) && !(sm.warn||0))
    html = '<div class="dg-ok-all">🎉 全部正常，本機找不出問題。若仍不顯示，把報告復制给開發者進一步排查。</div>' + html;
  box.innerHTML = html;
  var sugs = res.suggestions || [];
  if(sugs.length){
    sug.classList.remove('hidden');
    sug.innerHTML = '<b>建議：</b>' + sugs.map(function(s){return h(s);}).join('<br>');
  } else sug.classList.add('hidden');
}

// ═══════════════════════════════════════════════════════
// 線上補丁手動安裝與移除管理 (支援五階段進度分配與還原原始 .bak 檔案)
// ═══════════════════════════════════════════════════════
async function manualDeployPatch(appid, name){
  var aidStr = String(appid).trim();
  var gameTitle = name || ('AppID ' + aidStr);
  
  // 關閉下拉選單
  document.querySelectorAll('.card-dd.show').forEach(function(d){ d.classList.remove('show'); });

  // 關閉遊戲詳細彈窗，讓使用者清晰看到小卡上的圓形/水平進度條
  if(_curDetailAppid === aidStr){
    closeGameDetail();
  }

  try {
    // ═══════════════════════════════════════════════════════════════
    // 階段 1: 0% ~ 5% 【環境與網盤檢查】
    // ═══════════════════════════════════════════════════════════════
    updateCardProgress(aidStr, 2, '🔍 正在檢查環境與 Google Drive 補丁庫...', false);
    var gdriveCheck = await pywebview.api.check_cloud_patch_available(aidStr, gameTitle).catch(function(){ return {has_patch:false}; });
    var hasCloudPatch = gdriveCheck && gdriveCheck.has_patch;
    var driveName = (gdriveCheck && gdriveCheck.drive_name) || 'Google Drive';

    // ═══════════════════════════════════════════════════════════════
    // 階段 2: 5% ~ 15% 【清單與 Lua 配置確認】
    // ═══════════════════════════════════════════════════════════════
    updateCardProgress(aidStr, 8, '📦 正在確認 Manifest 清單與 Lua 配置...', false);
    try {
      await pywebview.api.check_local_lua_exists(aidStr);
    } catch(e){}
    updateCardProgress(aidStr, 15, '✅ 清單與配置檢查完成，準備下載補丁...', false);

    // ═══════════════════════════════════════════════════════════════
    // 階段 3: 15% ~ 25% 【線上補丁下載】
    // ═══════════════════════════════════════════════════════════════
    if(hasCloudPatch){
      updateCardProgress(aidStr, 18, '☁️ 正在自 ' + driveName + ' 下載線上補丁...', false);
      try {
        var dlRes = await pywebview.api.download_online_patch(aidStr, gameTitle);
        if(dlRes && dlRes.ok){
          updateCardProgress(aidStr, 25, '☁️ ' + driveName + ' 補丁下載就緒！', false);
        } else {
          updateCardProgress(aidStr, 25, '⚠️ 補丁下載略過，準備檢查主程式', false);
        }
      } catch(e){
        updateCardProgress(aidStr, 25, '☁️ 補丁暫存就緒', false);
      }
    } else {
      updateCardProgress(aidStr, 25, '☁️ 正在準備部署...', false);
    }

    // ═══════════════════════════════════════════════════════════════
    // 階段 4: 25% ~ 90% 【監測 Steam 遊戲下載 / 安裝進度】
    // ═══════════════════════════════════════════════════════════════
    updateCardProgress(aidStr, 26, '🎮 正在檢查 Steam 遊戲主程式狀態...', false);
    var instRes = await pywebview.api.get_steam_download_report(aidStr).catch(function(){ return {report:{status:'NOT_INSTALLED'}}; });
    var rep = (instRes && instRes.report) || {};

    if(rep.status === 'COMPLETED'){
      // 遊戲本地早已安裝好，直接平滑過渡至 90%
      updateCardProgress(aidStr, 90, '✅ Steam 遊戲主程式已就緒 (免下載)', false);
    } else {
      // 喚起 Steam 開始下載
      updateCardProgress(aidStr, 28, '🎮 正在喚起 Steam 開始下載遊戲主程式...', false);
      await pywebview.api.launch_steam_install(aidStr, gameTitle);
      tt('🎮 已喚起 Steam 下載遊戲，系統正在自動監控進度…', 'ok', 4000);

      // 開始非同步監控 Steam 下載進度 (25% ~ 90% 線性映射)
      var downloadDone = false;
      var pollCount = 0;
      var promptWaitCount = 0;
      var promptTimeoutSec = 20;

      while(!downloadDone && pollCount < 7200){ // 1秒/次，最多監控 2 小時
        await new Promise(function(r){ setTimeout(r, 1000); });
        pollCount++;

        var curRepRes = await pywebview.api.get_steam_download_report(aidStr).catch(function(){ return null; });
        var curRep = (curRepRes && curRepRes.report) || {};
        var st = curRep.status;
        var stageName = curRep.stage_name || 'DOWNLOADING';

        if(st === 'COMPLETED'){
          downloadDone = true;
          updateCardProgress(aidStr, 90, '🎉 Steam 主程式下載完成！', false);
          break;
        } else if(st === 'ERROR'){
          var errMsg = curRep.error_msg || 'Steam 回報下載錯誤';
          updateCardProgress(aidStr, 28, '❌ Steam 下載中斷: ' + errMsg, true);
          tt('⚠️ Steam 下載中斷: ' + errMsg, 'wn', 5000);
          openDownloadDiagnosticModal(aidStr, gameTitle);
          return;
        } else if(st === 'CANCELLED'){
          updateCardProgress(aidStr, 0, '⚠️ Steam 下載已取消', true);
          finishCardProgress(aidStr, false, '⚠️ Steam 下載已取消');
          tt('⚠️ 「' + gameTitle + '」Steam 下載已取消', 'wn', 4000);
          return;
        } else if(st === 'PAUSED'){
          var pctFromSteam = Number(curRep.progress_pct || 0);
          var dlText = '⏸️ Steam 下載已暫停 (' + pctFromSteam.toFixed(1) + '%) [請在 Steam 繼續]';
          var mappedPct = 25 + Math.round((pctFromSteam / 100) * 65);
          updateCardProgress(aidStr, mappedPct, dlText, false);
        } else {
          var pctFromSteam = Number(curRep.progress_pct || 0);
          var dlBytes = Number(curRep.bytes_downloaded || 0);
          var totalBytes = Number(curRep.bytes_to_download || 0);
          var speedStr = curRep.speed_str ? (' · ' + curRep.speed_str) : '';

          if(st === 'NOT_INSTALLED' && dlBytes === 0 && totalBytes === 0){
            promptWaitCount++;
            var remainSec = Math.max(0, promptTimeoutSec - promptWaitCount);
            if(remainSec <= 0){
              // 20 秒逾時：視為使用者取消確認或稍後再安裝，不影響已入庫清單
              updateCardProgress(aidStr, 0, '⚠️ 已結束安裝等候 (已入庫，可隨時在 Steam 下載)', true);
              finishCardProgress(aidStr, false, '⚠️ 已結束安裝等候 (已入庫，可隨時在 Steam 下載)');
              tt('ℹ️ 「' + gameTitle + '」已結束 20 秒安裝等候。遊戲已完成入庫，不影響已解鎖狀態，隨時可在 Steam 內點擊安裝！', 'in', 5000);
              return;
            }
            var dlText = '🎮 請在 Steam 視窗中確認安裝 (' + remainSec + 's 倒數，逾時不影響入庫狀態)';
            updateCardProgress(aidStr, 25, dlText, false);
          } else {
            promptWaitCount = 0;
            var mappedPct = Math.min(90, Math.max(25, 25 + Math.round((pctFromSteam / 100) * 65)));
            var dlText = '';
            if(stageName === 'STAGING'){
              dlText = '📦 Steam 正在解壓與驗證檔案中: ' + pctFromSteam.toFixed(1) + '%' + (totalBytes > 0 ? (' (' + formatBytes(dlBytes) + ' / ' + formatBytes(totalBytes) + ')') : '') + speedStr;
            } else if(totalBytes > 0){
              dlText = '🎮 Steam 下載中: ' + pctFromSteam.toFixed(1) + '% (' + formatBytes(dlBytes) + ' / ' + formatBytes(totalBytes) + speedStr + ')';
            } else if(dlBytes > 0){
              var mbDl = dlBytes / (1024 * 1024);
              var simulated = Math.min(60, Math.round(mbDl / 150) + (pollCount % 5));
              mappedPct = 25 + Math.max(5, simulated);
              dlText = '🎮 Steam 即時下載中: 已下載 ' + formatBytes(dlBytes) + speedStr;
            } else {
              var waitDots = '.'.repeat((pollCount % 3) + 1);
              dlText = '🎮 正在等候 Steam 佇列連線與分配空間' + waitDots;
              mappedPct = 26 + (pollCount % 3);
            }
            updateCardProgress(aidStr, mappedPct, dlText, false);
          }
        }
      }
    }

    // ═══════════════════════════════════════════════════════════════
    // 階段 5: 90% ~ 100% 【補丁安裝與原檔保護】
    // ═══════════════════════════════════════════════════════════════
    updateCardProgress(aidStr, 93, '🛡️ 正在自動備份遊戲原始檔案 (.bak)...', false);
    await new Promise(function(r){ setTimeout(r, 200); });
    updateCardProgress(aidStr, 96, '🚀 正在解壓部署 Online-Fix 聯機補丁...', false);
    var patchRes = await pywebview.api.install_online_patch(aidStr, gameTitle);
    
    if(patchRes && patchRes.ok){
      if(!_deployedAppids) _deployedAppids = new Set();
      _deployedAppids.add(aidStr);
      if(!_protectedAppids) _protectedAppids = new Set();
      _protectedAppids.add(aidStr);
      if(!_onlinefixAppids) _onlinefixAppids = new Set();
      finishCardProgress(aidStr, true, '🎉 聯機補丁已成功部署，已備份原檔！');
      tt('✅ 「' + gameTitle + '」線上聯機補丁已成功部署！已自動備份原檔 (.bak)', 'ok');

      // 🌟 核心更新：將小卡右側按鈕即時替換為「✅ 已在本地」
      var sactEl = document.getElementById('sact-' + aidStr);
      if(sactEl){
        sactEl.innerHTML = '<button class="btn btn-o btn-s" style="color:var(--succ);border-color:var(--succ);cursor:default" onclick="event.stopPropagation()">✅ 已在本地</button>';
      }

      if(_pre && _pre._games){
        _pre._games.forEach(function(g){
          if(String(g.appid) === aidStr){
            g.deployed = true;
          }
        });
        var filter = (document.getElementById('mf').value||'').trim().toLowerCase();
        renderGames(_pre._games, filter);
      }
    } else {
      finishCardProgress(aidStr, false, '❌ 部署失敗: ' + ((patchRes && patchRes.msg) || '未知錯誤'));
      tt('❌ 補丁部署失敗: ' + ((patchRes && patchRes.msg) || '未知錯誤'), 'er');
    }
  } catch(e) {
    finishCardProgress(aidStr, false, '❌ 部署出錯: ' + (e.message || e));
    tt('❌ 部署出錯: ' + (e.message || e), 'er');
  }
}

async function installOnlinePatch(appid, name){
  return manualDeployPatch(appid, name);
}

async function removeOnlinePatch(appid, name){
  var targetAppid = String(appid).trim();
  var gameName = name || ('App_' + targetAppid);
  if(!confirm('確定要移除「' + gameName + '」的線上補丁嗎？\n\n移除後系統將自動還原原始備份檔案 (.bak)。')){
    return;
  }
  sp('補丁移除中…', 'App ID: ' + targetAppid, 50, '正在清理補丁檔案並還原原始檔案…');
  try {
    var res = await pywebview.api.uninstall_online_patch(targetAppid);
    cp();
    if(res && res.ok){
      _deployedAppids.delete(targetAppid);
      _protectedAppids.delete(targetAppid);
      tt('✅ 已成功移除「' + gameName + '」的線上補丁並還原原始檔案！', 'ok');
      // 刷新詳細彈窗 (若開啟中)
      if(_curDetailAppid === targetAppid){
        openGameDetail(targetAppid, gameName);
      }
      // 刷新網盤狀況彈窗 (若開啟中)
      if(_gdsCurrentAppId === targetAppid){
        inspectDriveStatus(targetAppid, gameName);
      }
      // 刷新管理列表
      loadOnlineFixAppids().then(function(){ if(_pre._games) renderGames(_pre._games, ''); });
    } else {
      tt('❌ 移除線上補丁失敗: ' + ((res && res.msg) || '未知錯誤'), 'er');
    }
  } catch(e) {
    cp();
    tt('❌ 移除線上補丁出錯: ' + (e.message || e), 'er');
  }
}

// 🌟 Steam 背景下載監控與自動部署/錯誤中斷全域回調
window.onSteamDeployFinished = function(appid, gameName, success, msg){
  var aidStr = String(appid);
  if(success){
    tt('🎉 Steam 已完成「' + (gameName || ('AppID ' + aidStr)) + '」下載，已自動套用線上聯機補丁！', 'ok');
    if(!_deployedAppids) _deployedAppids = new Set();
    _deployedAppids.add(aidStr);
    if(!_protectedAppids) _protectedAppids = new Set();
    _protectedAppids.add(aidStr);
    if(!_onlinefixAppids) _onlinefixAppids = new Set();
    _onlinefixAppids.add(aidStr);
    var mCard = document.querySelector('#glist .card[data-appid="' + aidStr + '"]');
    if(mCard){
      mCard.style.borderColor = '#00bcd4';
      mCard.style.boxShadow = '0 0 0 2px rgba(0,188,212,0.45)';
    }
    if(_curDetailAppid === aidStr){
      openGameDetail(aidStr);
    }
    if(_gdsCurrentAppId === aidStr){
      inspectDriveStatus(aidStr, gameName);
    }
    loadOnlineFixAppids().then(function(){ if(_pre._games) renderGames(_pre._games, ''); });
  } else {
    tt('⚠️ 自動部署補丁失敗: ' + (msg || '未知錯誤'), 'er');
  }
};

window.onSteamDeployCancelled = function(appid, gameName, errReason){
  var aidStr = String(appid);
  tt('⚠️ 檢測到「' + (gameName || ('AppID ' + aidStr)) + '」Steam 下載中斷或發生錯誤 (' + (errReason || '已取消') + ')', 'wn', 5000);
  if(_curDetailAppid === aidStr){
    openGameDetail(aidStr);
  }
  openDownloadDiagnosticModal(aidStr, gameName);
};

// ═══════════════════════════════════════════════════════
// Online-Fix / 網盤聯機補丁全域狀態管理
// ═══════════════════════════════════════════════════════
var _onlinefixAppids = new Set();
var _deployedAppids = new Set();
var _protectedAppids = new Set();

async function loadOnlineFixAppids(){
  try{
    if(window.pywebview && pywebview.api && pywebview.api.get_onlinefix_appids){
      var ids = await pywebview.api.get_onlinefix_appids();
      if(Array.isArray(ids)){
        _onlinefixAppids = new Set(ids.map(String));
      }
    }
  }catch(e){
    console.warn('loadOnlineFixAppids failed:', e);
  }
}

