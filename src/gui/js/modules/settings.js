/* SteamManifestUpdater - Module: modules/settings.js */
// ═══════════════════════════════════════════════════════
// 工具箱
// ═══════════════════════════════════════════════════════
async function ds(){ try { var p=await pywebview.api.detect_steam(); if(p){ setPath(p); tt('✅ 已檢测到 Steam', 'ok'); } else tt('未找到 Steam', 'in'); } catch(e){ tt('檢测失敗', 'er'); } }
async function bf(){ try { var p=await pywebview.api.browse_folder(); if(p) setPath(p); } catch(e){ tt('選擇文件夾失敗: '+(e.message||e), 'er'); } }
async function ad(){ try { var p=await pywebview.api.detect_steam(); if(p){ setPath(p); tt('✅ 已檢测到 Steam', 'ok'); } else tt('未找到 Steam', 'in'); } catch(e){ tt('檢测失敗', 'er'); } }
async function ro(){ try { await pywebview.api.remove_old_tools(); tt('✅ 舊內核已替換為新 OST 內核', 'ok'); } catch(e){ tt('操作失敗', 'er'); } }
async function zj(){ var ikr; try { ikr = await pywebview.api.inject_kernel(); } catch(e){ tt('❌ 注入內核失敗: '+(e.message||e), 'er'); return; } if(!ikr.ok){ tt('❌ 內核注入失敗（可能需要管理員权限或關閉 Steam）', 'er'); return; } if(ikr.consistent === false){ var _rw=(ikr.remaining&&ikr.remaining.length)?ikr.remaining.join('、'):((ikr.warns&&ikr.warns.length)?ikr.warns.join('、'):''); tt('⚠️ 內核未完全更新'+( _rw?'：'+_rw:'')+'（文件被占用或拦截）。為避免新老內核混裝，已暫停重啟 Steam，請完全退出 Steam（含 steamwebhelper）或解除拦截後重新注入', 'er'); return; } if(ikr.steam_reopened){ tt('✅ 內核注入完成（Steam 已自動重開，已生效）', 'ok'); return; } if(confirm('內核注入完成，需要重啟 Steam 生效\n\n是否重啟 Steam？')){ try { await pywebview.api.restart_steam(); tt('✅ Steam 已重啟，內核生效', 'ok'); } catch(e){ tt('重啟失敗: '+(e.message||e), 'er'); } } else { tt('⚠️ 內核已注入，重啟 Steam 後生效', 'in'); } }
async function jh(){ if(!await htmlConfirm('⚠️ 凈化 Steam','此操作將關閉 Steam，並删除 Steam 目錄下除 Steam.exe、steamapps、userdata 以外的所有文件。<br><br><span style="color:#E53935;font-weight:600">⚠️ 會清除大量 Steam 數據，删除需要等待一段時間，請耐心等彈出「完成」提示；看到提示後再用加速器打開 Steam，屆時需要重新登錄账號密碼！</span>')) return; try { var r=await pywebview.api.purge_steam(); var msg='✅ 已删除 '+r.deleted+' 項'; if(r.remaining&&r.remaining.length>0){ msg+='\n⚠️ 殘留 '+r.remaining.length+' 項：'+r.remaining.slice(0,10).join('、')+(r.remaining.length>10?'… 等':''); alert('⚠️ 以下文件/目錄未能删除（可能被占用）：\n\n'+r.remaining.join('\n')); } try { var ikr=await pywebview.api.inject_kernel(false); await pywebview.api.remove_steam_cfg(); if(ikr.ok&&ikr.warns.length===0){ msg+='，內核已注入'; } else if(ikr.ok&&ikr.warns.length>0){ msg+='，但部分文件未能更新：\n'+ikr.warns.join('\n'); tt(msg,'er'); return; } else { msg='⚠️ 已删除 '+r.deleted+' 項，但內核注入失敗（可能需管理員权限），下次啟動會自動重新注入'; tt(msg,'er'); return; } } catch(e){ msg='⚠️ 已删除 '+r.deleted+' 項，內核注入失敗：'+(e.message||e); } tt(msg, r.remaining&&r.remaining.length>0?'in':'ok'); } catch(e){ tt('凈化失敗: '+(e.message||e), 'er'); } }
async function restartSteam(){ if(!confirm('是否重啟 Steam？')) return; try { await pywebview.api.restart_steam(); tt('✅ Steam 重啟完成', 'ok'); } catch(e){ tt('重啟失敗: '+(e.message||e), 'er'); } }

// ── 重啟方式選擇：默認重啟 / 切換账號（账號读取為新增，不重寫穩定 restart_steam）──
// ── 重啟目標：無账號登錄 / 選某账號後二選 在線·離線（去掉「默認重啟當前账號」）──
var _rsAccs = [];   // 最近一次账號列表（供二選彈窗取 persona/offline_ready）
var _rsCur = '';    // 當前二選目標账號名
async function restartSteamPick(){
  var c = document.getElementById('rs-list');
  var load = document.getElementById('rs-loading');
  _rsAccs = [];
  try { _rsAccs = await pywebview.api.list_steam_accounts(); } catch(e){ console.error('rs:', e); }
  if(_rsAccs === null){ load.style.display='none'; closeRs(); restartSteam(); return; }  // 读账號列表失敗 → 走既有默認重啟
  load.style.display = 'none';
  var h2 = '';
  // ① 無账號登錄：重啟到登錄界面，可登錄新账號
  h2 += '<div class="rs-item" data-mode="__nologin" style="display:flex;align-items:center;gap:10px;padding:9px 10px;border-radius:10px;cursor:pointer;border-bottom:1px dashed var(--pink-light)"><div style="width:36px;height:36px;border-radius:50%;background:var(--pink-light);display:flex;align-items:center;justify-content:center;font-size:16px;flex:none">👤</div><div style="flex:1;line-height:1.3"><div style="font-size:13px;font-weight:600">無账號登錄（登錄新账號）</div><div style="font-size:11px;color:var(--gray)">重啟到 Steam 登錄界面，不自動登錄，可手動登錄其他账號</div></div></div>';
  for(var i=0;i<_rsAccs.length;i++){
    var a = _rsAccs[i];
    var av;
    if(a.avatar_url){ av = '<img src="'+a.avatar_url+'" style="width:36px;height:36px;border-radius:50%;object-fit:cover;flex:none">'; }
    else { av = '<div style="width:36px;height:36px;border-radius:50%;background:var(--pink-light);display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:700;color:var(--pink-deep);flex:none">'+h((a.persona||'?').slice(0,1))+'</div>'; }
    var warn = a.remember ? '' : '<div style="font-size:11px;color:#E53935">⚠️ 未記住密碼，重啟後需手動输密碼</div>';
    h2 += '<div class="rs-item" data-mode="'+h(a.account)+'" style="display:flex;align-items:center;gap:10px;padding:9px 10px;border-radius:10px;cursor:pointer">'+av+'<div style="flex:1;line-height:1.3"><div style="font-size:13px;font-weight:600">'+h(a.persona)+'</div><div style="font-size:11px;color:var(--gray)">账號：'+h(a.account)+'</div>'+warn+'</div></div>';
  }
  c.innerHTML = h2;
  var items = c.querySelectorAll('.rs-item');
  for(var j=0;j<items.length;j++){
    (function(el){ el.addEventListener('click', function(){ rsGo(el.getAttribute('data-mode')); }); })(items[j]);
  }
  document.getElementById('rs-m').classList.remove('hidden');
}
function closeRs(){ document.getElementById('rs-m').classList.add('hidden'); }
function closeRs2(){ document.getElementById('rs2-m').classList.add('hidden'); document.getElementById('rs-m').classList.remove('hidden'); }
function closeRsAll(){ document.getElementById('rs-m').classList.add('hidden'); document.getElementById('rs2-m').classList.add('hidden'); }
async function rsGo(mode){
  if(mode === '__nologin'){
    closeRs();
    if(!confirm('重啟 Steam 到登錄界面（無账號登錄）？\n\nSteam 將不自動登錄任何账號，停在账號登錄/選擇界面，可手動登錄其他账號。')) return;
    sp('重啟', '正在重啟 Steam 到登錄界面 …');
    try { await pywebview.api.restart_steam_login(); cp(); tt('✅ Steam 已重啟到登錄界面（無账號）', 'ok'); }
    catch(e){ cp(); tt('操作失敗: '+(e.message||e), 'er'); }
    return;
  }
  // 選某账號 → 關掉列表層，彈「在線 / 離線」行選擇（與账號列表同款行樣式）
  _rsCur = mode;
  var a = null;
  for(var i=0;i<_rsAccs.length;i++){ if(_rsAccs[i].account === mode){ a = _rsAccs[i]; break; } }
  var persona = a ? (a.persona || mode) : mode;
  var ready = !!(a && a.offline_ready);
  var R = 'display:flex;align-items:center;gap:10px;padding:9px 10px;border-radius:10px;cursor:pointer;border-bottom:1px dashed var(--pink-light)';
  function chip(ico, dim){ return '<div style="width:36px;height:36px;border-radius:50%;background:var(--pink-light);display:flex;align-items:center;justify-content:center;font-size:16px;flex:none'+(dim?';opacity:.5':'')+'">'+ico+'</div>'; }
  function rtext(t, sub, col, dim){ return '<div style="flex:1;line-height:1.3'+(dim?';opacity:.55':'')+'"><div style="font-size:13px;font-weight:600">'+t+'</div><div style="font-size:11px;color:'+(col||'var(--gray)')+'">'+sub+'</div></div>'; }
  var rows = '<div class="rs-item" data-act="on" style="'+R+'">'+chip('🌐')+rtext('在線重啟','联網登錄 '+h(mode)+'，正常在線')+'</div>';
  if(ready){
    rows += '<div class="rs-item" data-act="off" style="'+R+'">'+chip('🛰')+rtext('離線重啟','直進離線模式；想回在線時在 Steam 裡點「重新联機」')+'</div>';
  } else {
    var why = (a && !a.remember) ? '未記住密碼 → 冷啟動進不了離線，先在 Steam 登錄勾選「記住我」' : '還没在这台電腦進過離線模式（離線票無法偽造）→ 先在 Steam 在線點一次「開始離線模式」打底';
    rows += '<div class="rs-item" data-act="off" style="'+R+'">'+chip('🛰', true)+rtext('離線重啟', why, '#E53935', true)+'</div>';
  }
  var list = document.getElementById('rs2-list');
  list.innerHTML = rows;
  var rrows = list.querySelectorAll('.rs-item');
  for(var k=0;k<rrows.length;k++){
    (function(el){ el.addEventListener('click', function(){ rs2Go(el.getAttribute('data-act')); }); })(rrows[k]);
  }
  document.getElementById('rs2-title').textContent = '重啟到：'+persona;
  document.getElementById('rs2-info').innerHTML = '账號：'+h(mode)+(a && !a.remember ? '<br>⚠️ 未記住密碼' : '');
  document.getElementById('rs-m').classList.add('hidden');
  document.getElementById('rs2-m').classList.remove('hidden');
}
async function rs2Go(which){
  var mode = _rsCur;
  var a = null;
  for(var i=0;i<_rsAccs.length;i++){ if(_rsAccs[i].account === mode){ a = _rsAccs[i]; break; } }
  var persona = a ? (a.persona || mode) : mode;
  // 未就緒的離線行被點：彈原因，不执行（就緒行點下即直接执行，無 confirm）
  if(which === 'off' && (!a || !a.offline_ready)){
    var tip = (!a || !a.remember) ? '该账號未記住密碼，冷啟動進不了離線。請先在 Steam 登錄時勾選「記住我」' : '该账號還没在这台電腦進過離線模式（離線票無法偽造）。請先在 Steam 在線時點一次「開始離線模式」打底，之後即可一鍵離線重啟';
    tt(tip, 'in'); return;
  }
  closeRsAll();  // 两層一起關，不再彈回账號列表（closeRs2 的「返回」語義會把 rs-m 重新顯示）
  sp(which==='on' ? '重啟' : '進離線', which==='on' ? ('正在重啟並在線登錄 '+persona+' …') : ('正在重啟 '+persona+' 並進離線 …'));
  try {
    if(which === 'on'){ await pywebview.api.restart_steam_online(mode); cp(); tt('✅ 已重啟並在線登錄 '+persona, 'ok'); }
    else { await pywebview.api.restart_steam_offline(mode); cp(); tt('✅ '+persona+' 已在離線模式重啟', 'ok'); }
  } catch(e){ cp(); tt((which==='on'?'重啟失敗':'進離線失敗')+': '+(e.message||e), 'er'); }
}
// 浮窗权限引導：純免費用户點了浮窗入口 → 說明是已激活权益，带他去激活頁
function floatGuide(){
  var go = confirm('🌸 最小化浮窗是贊助版权益：使用過贊助版激活碼即可長期開啟。\n\n是否現在去激活？');
  if(go) switchPage('lic');
}
// 权威查一次浮窗权限（啟動早期 _licFloatOk 可能還没就緒，付費用户不该被誤拦）
async function floatAllowedNow(){
  var ok = (_licFloatOk === true);
  if(!ok){ try{ ok = !!await pywebview.api.float_allowed(); _licFloatOk = ok; }catch(e){ ok = false; } }
  return ok;
}
async function minimizeToFloat(){
  if(!await floatAllowedNow()){ floatGuide(); return; }
  try {
    var cfg = await pywebview.api.get_config();
    if(!cfg.float_hint_shown){
      var go = confirm('🌸 縮小為浮動圖標後，可以直接把 Steam 商店頁的遊戲封面或遊戲名字拖到浮動圖標上，快速入庫。\n\n是否縮小為浮動圖標？');
      try { await pywebview.api.set_config('float_hint_shown', true); } catch(e){}
      if(!go) return;
    }
    var r = await pywebview.api.toggle_mini();
    if(r && r.ok === false){ tt(r.error || '切換失敗', 'er'); }
  } catch(e){ tt('切換失敗: '+(e.message||e), 'er'); }
}
async function toggleSteamLock(){
  var btn = document.getElementById('btn-lock-steam');
  try {
    var status = await pywebview.api.check_steam_locked();
    if(status.locked){
      if(!confirm('將解鎖 Steam 版本。確定繼續？')) return;
      await pywebview.api.unlock_steam_version();
      btn.textContent = '鎖定版本';
      tt('✅ Steam 版本已解鎖', 'ok');
    } else {
      if(!confirm('將鎖定 Steam 版本。確定繼續？')) return;
      await pywebview.api.lock_steam_version();
      btn.textContent = '解鎖版本';
      tt('✅ Steam 版本已鎖定', 'ok');
    }
  } catch(e){ tt('操作失敗: '+(e.message||e), 'er'); }
}
async function checkSteamLock(){
  try {
    var status = await pywebview.api.check_steam_locked();
    var btn = document.getElementById('btn-lock-steam');
    if(btn) btn.textContent = status.locked ? '解鎖版本' : '鎖定版本';
  } catch(e){}
}

document.addEventListener('click', function(){ document.querySelectorAll('.card-dd.show').forEach(function(d){d.classList.remove('show')}); });
// GBE
async function gb(appid){
  // GBE 破解权益門（2026-09-07）：需「買過激活碼」（同浮窗口径，永久/日/周/月任一即長期可用）。
  // 純免費 → 保留入口但點擊彈引導去激活頁；無权者不彈後續確認/不下載模板。
  var gbeOk = false;
  try{ gbeOk = !!(pywebview.api && await pywebview.api.gbe_allowed()); }catch(e){ gbeOk = false; }
  if(!gbeOk){
    var go = confirm('🎮 GBE 破解是贊助版权益：使用過贊助版激活碼即可長期開啟。\n\n是否現在去激活？');
    if(go){ goSettingsActivate(); }
    return;
  }
  if(!confirm('可绕過 Steam 啟動，防止啟動慢\n\n對雨中冒險2有效，其他大部分遊戲不需要\n\n是否繼續？')) return;
  try {
    // 先读 Steam appmanifest 自動定位安裝目錄；找不到才手動選
    var dir = await pywebview.api.locate_game_dir(appid);
    if(dir){
      if(!confirm('已自動找到安裝目錄：\n'+dir+'\n\n用它执行 GBE 破解？\n（點取消可手動重新選擇）')){ dir = null; }
    }
    if(!dir){
      tt('📁 請選擇遊戲安裝目錄', 'in');
      dir = await pywebview.api.browse_folder();
      if(!dir) return;
    }
    sp('GBE 破解', '正在準備…');
    var r = await pywebview.api.gbe_crack(appid, dir);
    cp();
    if(r.ok){ tt('✅ GBE 破解完成 — 去遊戲目錄裡打開 GBE 文件夾', 'ok'); }
    else tt('❌ GBE 失敗: '+(r.error||''), 'er');
  } catch(e){ cp(); tt('GBE 失敗', 'er'); }
}

// ═══════════════════════════════════════════════════════
// 設置
// ═══════════════════════════════════════════════════════
async function ts(key){
  var el = document.getElementById('t-'+key);
  if(!el && (key === 'random_browse' || key === 'random')) el = document.getElementById('t-random');
  if(!el) return;
  var v = el.checked;
  if(key === 'dark' || key === 'dark_mode'){
    var app = document.getElementById('app');
    var spOver = document.getElementById('splash-overlay');
    if(v){
      app.classList.add('dark');
      if(spOver) spOver.classList.add('dark');
      document.documentElement.classList.add('dark');
      try { localStorage.setItem('dark_mode', '1'); } catch(e){}
    } else {
      app.classList.remove('dark');
      if(spOver) spOver.classList.remove('dark');
      document.documentElement.classList.remove('dark');
      try { localStorage.removeItem('dark_mode'); } catch(e){}
    }
    try { await pywebview.api.set_config('dark_mode', v); } catch(e){}
    try { await pywebview.api.set_config('dark', v); } catch(e){}
    return;
  }
  if(key === 'random' || key === 'random_browse'){
    try { await pywebview.api.set_config('random_browse', v); } catch(e){}
    try { await pywebview.api.set_config('random', v); } catch(e){}
    return;
  }
  try { await pywebview.api.set_config(key, v); } catch(e){}
}

async function tsFloat(){
  var el = document.getElementById('t-float');
  var v = el.checked;
  // 開啟浮窗前先查权限：純免費用户 → 彈引導並回彈開關
  if(v && !await floatAllowedNow()){
    el.checked = false;
    floatGuide();
    return;
  }
  try {
    await pywebview.api.set_config('float_enabled', v);
    if(v){
      tt('🌸 正在啟用最小化浮窗…', 'in');
      // 首次啟用：觸發 PySide6 後台下載，完成後自動彈 toast
      try { await pywebview.api.ensure_pyside6_async(); } catch(e){}
    } else {
      tt('最小化浮窗已關閉', 'in');
    }
  } catch(e){ el.checked = !v; tt('操作失敗: '+(e.message||e), 'er'); }
}

/* ── 雲存檔功能已下線停用 (安全 Stub) ── */
function crRenderDest(){ }
async function crSetDest(){ }
async function pickCloudPath(){ }
async function openCloudPath(){ }
function crBody(){ }
async function tsCloudRedirect(){ }
async function loadCloudSaves(){ }
async function openGameSaveDir(){ }
async function fixOfficialCloudDisabled(){ }


function setPath(v){
  document.getElementById('sp2').value = v;
  pywebview.api.set_steam_path(v);
}

// ── 通用 HTML 富文本確認彈窗：htmlConfirm(標題, 正文HTML) → Promise<boolean> ──
var _cfDone = null;
function htmlConfirm(title, bodyHtml){
  return new Promise(function(res){
    _cfDone = res;
    document.getElementById('cf-title').textContent = title;
    document.getElementById('cf-body').innerHTML = bodyHtml;
    var btns = document.getElementById('cf-btns'); btns.innerHTML = '';
    function mk(label, cls, fn){ var b=document.createElement('button'); b.className='btn '+cls+' btn-s'; b.textContent=label; b.onclick=fn; btns.appendChild(b); }
    mk('取消','btn-o',function(){ closeCf(false); });
    mk('確定','btn-p',function(){ closeCf(true); });
    document.getElementById('cf-m').classList.remove('hidden');
  });
}
function closeCf(v){
  document.getElementById('cf-m').classList.add('hidden');
  var d = _cfDone; _cfDone = null;
  if(d) d(v);
}
function goSettingsActivate(){
  switchPage('lic');
  var el = document.getElementById('lic-code');
  if(el){ setTimeout(function(){ el.focus(); try{ el.scrollIntoView({block:'center'}); }catch(e){} }, 80); }
  else { tt('請在 激活碼 頁粘貼激活碼', 'in'); }
}

// ═══════════════════════════════════════════════════════
// 背景管理核心模組 (swBg / addBgThumb / loadBgThumbs)
// ═══════════════════════════════════════════════════════
async function swBg(id){
  // 高亮選中縮略圖
  document.querySelectorAll('#bg-g > div').forEach(function(e){
    e.style.borderColor = (e.getAttribute('data-bg') === (id || '')) ? 'var(--pink-deep)' : 'transparent';
  });
  try {
    var app = document.getElementById('app');
    var bgImg = document.getElementById('app-bg-img');
    if(id){
      var d = await pywebview.api.get_bg_data(id);
      if(d && app){
        app.classList.add('has-bg');
        if(bgImg) bgImg.style.backgroundImage = 'url(' + d + ')';
        else app.style.backgroundImage = 'url(' + d + ')';
      }
    } else if(app) {
      app.classList.remove('has-bg');
      if(bgImg) bgImg.style.backgroundImage = '';
      else app.style.backgroundImage = '';
    }
  } catch(e){
    tt('背景切換失敗: ' + (e.message || e.toString()), 'er');
    return;
  }
  try { await pywebview.api.set_config('bg', id); } catch(e){}
  try { await pywebview.api.set_config('bg_active', id); } catch(e){}
}

function addBgThumb(img){
  var g = document.getElementById('bg-g');
  if(!g) return;
  var d = document.createElement('div');
  d.style.cssText = 'width:64px;cursor:pointer;text-align:center;font-size:9px;color:var(--gray);border:2px solid transparent;border-radius:6px;padding:3px';
  d.setAttribute('data-bg', img.id);
  d.onclick = function(){ swBg(img.id); };
  var imgTag = img.thumb 
    ? '<img src="' + img.thumb + '" style="width:56px;height:36px;border-radius:3px;object-fit:cover">' 
    : '<div style="width:56px;height:36px;border-radius:3px;background:var(--pink-pale);display:flex;align-items:center;justify-content:center;font-size:18px">🖼</div>';
  var delBtn = '<span onclick="event.stopPropagation();removeBg(\'' + (img.id || '').replace(/'/g, "\\'") + '\')" style="position:absolute;top:-6px;right:-6px;width:16px;height:16px;border-radius:50%;background:var(--err);color:#fff;font-size:10px;line-height:16px;text-align:center;cursor:pointer;display:none" class="bg-del">×</span>';
  d.innerHTML = '<div style="position:relative">' + imgTag + delBtn + '</div>';
  d.onmouseenter = function(){ var b = this.querySelector('.bg-del'); if(b) b.style.display = 'block'; };
  d.onmouseleave = function(){ var b = this.querySelector('.bg-del'); if(b) b.style.display = 'none'; };
  var addBtn = g.querySelector('div[onclick*="addBg"]');
  if(addBtn) g.insertBefore(d, addBtn); else g.appendChild(d);
}

function loadBgThumbs(){
  pywebview.api.get_bg_thumbnails().then(function(thumbs){
    if(!thumbs || !thumbs.length) return;
    var existing = new Set();
    document.querySelectorAll('#bg-g > div[data-bg]').forEach(function(e){ existing.add(e.getAttribute('data-bg')); });
    thumbs.forEach(function(img){
      if(!existing.has(img.id)) addBgThumb(img);
    });
  }).catch(function(e){ console.error('loadBgThumbs error', e); });
}

// 添加背景圖 — 用隱藏的 file input
function addBg(){
  var inp = document.createElement('input');
  inp.type = 'file';
  inp.accept = 'image/png,image/jpeg,image/webp,image/gif,image/*';
  inp.onchange = async function(){
    var file = inp.files[0];
    if(!file) return;
    // 读成 base64
    var reader = new FileReader();
    reader.onload = async function(){
      try {
        var base64 = reader.result; // data:image/...;base64,xxx
        var info = await pywebview.api.add_bg_base64(file.name, base64);
        if(!info){ tt('添加背景失敗', 'er'); return; }
        var g = document.getElementById('bg-g');
        var plus = g.lastElementChild;
        var d = document.createElement('div');
        d.style.cssText = 'width:64px;cursor:pointer;text-align:center;font-size:9px;color:var(--gray);border:2px solid transparent;border-radius:6px;padding:3px';
        d.setAttribute('data-bg', info.id);
        d.onclick = function(){ swBg(info.id); };
        d.innerHTML = '<div style="position:relative"><img src="'+info.thumb+'" style="width:56px;height:36px;border-radius:3px;object-fit:cover"><span onclick="event.stopPropagation();removeBg(\''+jsesc(info.id)+'\')" style="position:absolute;top:-6px;right:-6px;width:16px;height:16px;border-radius:50%;background:var(--err);color:#fff;font-size:10px;line-height:16px;text-align:center;cursor:pointer;display:none" class="bg-del">×</span></div>';
        d.onmouseenter = function(){ this.querySelector('.bg-del').style.display='block'; };
        d.onmouseleave = function(){ this.querySelector('.bg-del').style.display='none'; };
        g.insertBefore(d, plus);
        swBg(info.id);
        tt('✅ 背景已添加', 'ok');
      } catch(e){ tt('添加失敗: '+(e.message||e), 'er'); }
    };
    reader.readAsDataURL(file);
  };
  inp.click();
}

async function removeBg(id){
  if(!confirm('確定要移除这個背景吗？')) return;
  try {
    await pywebview.api.remove_bg(id);
    document.querySelectorAll('#bg-g > div').forEach(function(e){
      if(e.getAttribute('data-bg') === id) e.remove();
    });
    if(document.getElementById('bg-g').querySelector('div[data-bg="'+id+'"]')===null){
      // 如果删除的是當前背景，切回默認
      var cur = document.querySelector('#bg-g div[style*="var(--pink-deep)"]');
      if(!cur || cur.getAttribute('data-bg') === id) swBg('');
    }
    tt('背景已移除', 'in');
  } catch(e){ tt('移除失敗', 'er'); }
}
function restoreDefaultBgs(){
  // 恢復默認：強制從 Gitee 重新下載最新背景，完成後刷新縮略圖
  tt('正在恢復默認背景…', 'in');
  pywebview.api.install_default_bgs(true).then(function(){
    loadBgThumbs();
    tt('✅ 默認背景已恢復', 'ok');
  }).catch(function(){ tt('恢復失敗', 'er'); });
}

// ═══════════════════════════════════════════════════════
// 設置頁面母分類 (介面 / 進階) 與 Google Drive 網盤管理
// ═══════════════════════════════════════════════════════
var _curSettingsTab = 'ui';
var _gdriveDrives = [];

function switchSettingsTab(tab){
  _curSettingsTab = tab;
  var btnUi = document.getElementById('btn-stab-ui');
  var btnAdv = document.getElementById('btn-stab-adv');
  var btnSys = document.getElementById('btn-stab-sys');
  var paneUi = document.getElementById('settings-tab-ui');
  var paneAdv = document.getElementById('settings-tab-adv');
  var paneSys = document.getElementById('settings-tab-sys');
  
  if(btnUi) btnUi.className = (tab === 'ui') ? 'settings-tab-btn btn btn-p btn-s' : 'settings-tab-btn btn btn-o btn-s';
  if(btnAdv) btnAdv.className = (tab === 'adv') ? 'settings-tab-btn btn btn-p btn-s' : 'settings-tab-btn btn btn-o btn-s';
  if(btnSys) btnSys.className = (tab === 'sys') ? 'settings-tab-btn btn btn-p btn-s' : 'settings-tab-btn btn btn-o btn-s';

  if(paneUi) paneUi.style.display = (tab === 'ui') ? 'block' : 'none';
  if(paneAdv) paneAdv.style.display = (tab === 'adv') ? 'block' : 'none';
  if(paneSys) paneSys.style.display = (tab === 'sys') ? 'block' : 'none';

  if(tab === 'adv'){
    loadGDriveSettings();
  } else if(tab === 'sys'){
    initSystemHealthView();
  }
}

function toggleGDriveGuide(){
  var body = document.getElementById('gdrive-guide-body');
  var btn = document.getElementById('btn-toggle-gdrive-guide');
  if(!body) return;
  var isHidden = (body.style.display === 'none');
  body.style.display = isHidden ? 'block' : 'none';
  if(btn) btn.textContent = isHidden ? '收合說明' : '查看說明';
}

async function loadGDriveSettings(){
  try{
    if(!window.pywebview || !pywebview.api || !pywebview.api.get_cloud_drives) return;
    var drives = await pywebview.api.get_cloud_drives();
    if(Array.isArray(drives)){
      _gdriveDrives = drives.map(function(d, idx){
        return {
          priority: idx + 1,
          name: d.name || ('網盤 ' + (idx + 1)),
          url: d.url || ''
        };
      });
    } else {
      _gdriveDrives = [];
    }
    renderGDriveRows();
  }catch(e){
    console.warn('loadGDriveSettings failed:', e);
  }
}

function renderGDriveRows(){
  var container = document.getElementById('gdrive-list-container');
  if(!container) return;
  if(!_gdriveDrives || _gdriveDrives.length === 0){
    container.innerHTML = '<div style="padding:20px;text-align:center;color:var(--gray);border:1px dashed var(--pink-light);border-radius:10px;font-size:12px">目前尚未設定任何 Google Drive 網盤，請點擊下方「➕ 新增 Google Drive 網盤」按鈕添加！</div>';
    return;
  }
  
  var html = '';
  for(var i = 0; i < _gdriveDrives.length; i++){
    var item = _gdriveDrives[i];
    var isFirst = (i === 0);
    var isLast = (i === _gdriveDrives.length - 1);
    var priorityBadge = isFirst 
      ? '<span style="font-weight:700;color:#00bcd4">網盤 ' + (i + 1) + ' <small style="font-weight:normal">(最高優先級)</small></span>' 
      : '<span style="font-weight:700;color:var(--fg)">網盤 ' + (i + 1) + '</span>';
      
    html += '<div class="gdrive-row-card" data-idx="' + i + '">';
    // 頂部列：優先級與排序/刪除按鈕
    html += '  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">';
    html += '    <div style="font-size:12px">' + priorityBadge + '</div>';
    html += '    <div style="display:flex;gap:4px;align-items:center">';
    html += '      <button type="button" class="btn btn-o btn-xs" ' + (isFirst ? 'disabled style="opacity:0.3;cursor:not-allowed"' : 'onclick="moveGDriveRow(' + i + ', -1)"') + ' title="提高優先順序">🔼 上移</button>';
    html += '      <button type="button" class="btn btn-o btn-xs" ' + (isLast ? 'disabled style="opacity:0.3;cursor:not-allowed"' : 'onclick="moveGDriveRow(' + i + ', 1)"') + ' title="降低優先順序">🔽 下移</button>';
    html += '      <button type="button" class="btn btn-o btn-xs" onclick="deleteGDriveRow(' + i + ')" style="color:#e05353;border-color:rgba(224,83,83,0.3)" title="移除此網盤">🗑️ 刪除</button>';
    html += '    </div>';
    html += '  </div>';
    // 輸入列：名稱與網址
    html += '  <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">';
    html += '    <input type="text" class="gdrive-input-name" style="width:160px;flex-shrink:0" placeholder="網盤名稱 (如: 官方補丁庫)" value="' + h(item.name || '') + '" oninput="updateGDriveField(' + i + ', \'name\', this.value)">';
    html += '    <input type="text" class="gdrive-input-url" style="flex:1;min-width:240px" placeholder="Google Drive 網址 (https://drive.google.com/drive/folders/...)" value="' + h(item.url || '') + '" oninput="updateGDriveField(' + i + ', \'url\', this.value)">';
    html += '  </div>';
    html += '</div>';
  }
  container.innerHTML = html;
}

function updateGDriveField(idx, field, val){
  if(_gdriveDrives[idx]){
    _gdriveDrives[idx][field] = val;
  }
}

function addGDriveRow(){
  var newIdx = _gdriveDrives.length + 1;
  _gdriveDrives.push({
    priority: newIdx,
    name: '自訂網盤 ' + newIdx,
    url: ''
  });
  renderGDriveRows();
  // 滾動到底部輸入框並聚焦
  var container = document.getElementById('gdrive-list-container');
  if(container && container.lastElementChild){
    var input = container.lastElementChild.querySelector('.gdrive-input-url');
    if(input) input.focus();
  }
}

function moveGDriveRow(idx, dir){
  var target = idx + dir;
  if(target < 0 || target >= _gdriveDrives.length) return;
  var temp = _gdriveDrives[idx];
  _gdriveDrives[idx] = _gdriveDrives[target];
  _gdriveDrives[target] = temp;
  _gdriveDrives.forEach(function(d, i){ d.priority = i + 1; });
  renderGDriveRows();
}

function deleteGDriveRow(idx){
  if(idx < 0 || idx >= _gdriveDrives.length) return;
  var item = _gdriveDrives[idx];
  var name = item.name || ('網盤 ' + (idx + 1));
  if(!confirm('確定要刪除「' + name + '」網盤設定嗎？')) return;
  _gdriveDrives.splice(idx, 1);
  _gdriveDrives.forEach(function(d, i){ d.priority = i + 1; });
  renderGDriveRows();
}

async function saveGDriveRows(){
  var btn = document.getElementById('btn-save-gdrive');
  if(btn) btn.disabled = true;
  try{
    // 同步當前輸入框中的值防止使用者輸入未觸發 oninput
    var container = document.getElementById('gdrive-list-container');
    if(container){
      var cards = container.querySelectorAll('.gdrive-row-card');
      cards.forEach(function(card, i){
        if(_gdriveDrives[i]){
          var nInput = card.querySelector('.gdrive-input-name');
          var uInput = card.querySelector('.gdrive-input-url');
          if(nInput) _gdriveDrives[i].name = nInput.value.trim();
          if(uInput) _gdriveDrives[i].url = uInput.value.trim();
        }
      });
    }
    
    // 整理資料
    var toSave = _gdriveDrives.map(function(d, i){
      return {
        priority: i + 1,
        name: (d.name || '').trim() || ('網盤 ' + (i + 1)),
        url: (d.url || '').trim()
      };
    });
    
    var res = await pywebview.api.save_cloud_drives(toSave);
    if(res && res.ok){
      tt(res.msg || '✅ 已成功儲存網盤設定！', 'ok');
      await loadGDriveSettings();
    } else {
      tt((res && res.msg) || '儲存失敗', 'er');
    }
  }catch(e){
    tt('儲存出錯: ' + (e.message || e), 'er');
  }finally{
    if(btn) btn.disabled = false;
  }
}






