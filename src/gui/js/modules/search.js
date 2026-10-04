/* SteamManifestUpdater - Module: modules/search.js */
// ═══════════════════════════════════════════════════════
// 搜索
// ═══════════════════════════════════════════════════════
document.getElementById('q').onkeydown = function(e){ if(e.key==='Enter'){ clearTimeout(_st); s(); } };
var _st = null;

var _installedAppids = new Set();

// ═══════════════════════════════════════════════════════
// 瀏覽全部遊戲（網格）
// ═══════════════════════════════════════════════════════
var _browse = { page: 0, per: 40, loading: false };

function _enterSearchMode(){
  document.getElementById('browse-info').style.display = 'none';
  document.getElementById('btn-load-more').style.display = 'none';
  document.getElementById('results').classList.remove('browse-grid');
}

function _browseCard(g){
  var aid = String(g.appid);
  var nm = g.name || ('App_' + aid);
  var isInstalled = _installedAppids && _installedAppids.has(aid);
  var hasUp = false;
  if(isInstalled){
    if(_knownUpdates[aid] && _knownUpdates[aid].has_update){
      hasUp = true;
    } else if(_pre._games){
      for(var i=0; i<_pre._games.length; i++){
        if(String(_pre._games[i].appid) === aid && _pre._games[i].has_update){
          hasUp = true;
          break;
        }
      }
    }
  }
  var hasOf = _onlinefixAppids && _onlinefixAppids.has(aid);
  var isDeployed = _deployedAppids && _deployedAppids.has(aid);
  var isProtected = _protectedAppids && _protectedAppids.has(aid);
  
  // 🌟 右上角標籤（垂直由上往下直排）
  var tagsHtml = '';
  if(hasOf) tagsHtml += '<span class="corner-tag tag-of" title="支援 Online-Fix 聯機補丁">🎮 聯機</span>';
  if(isDeployed) tagsHtml += '<span class="corner-tag tag-dep" title="本地已成功部署補丁">✅ 部署</span>';
  if(hasUp) tagsHtml += '<span class="corner-tag tag-up" title="官方有新版本可更新">⚡ 可更新</span>';
  var cornerTagsDiv = tagsHtml ? '<div class="card-corner-tags">' + tagsHtml + '</div>' : '';

  var cardClass = 'card' + (hasUp ? ' needs-update' : '') + (hasOf ? ' has-onlinefix' : '');
  var actionBtn = '';
  if(isInstalled){
    actionBtn = '<button class="card-menu card-installed" onclick="event.stopPropagation()" title="✅ 已在本地入庫' + (hasUp ? ' (官方有新版本可更新)' : '') + '">' +
                  '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>' +
                '</button>';
  } else {
    actionBtn = '<button class="card-menu" onclick="event.stopPropagation(); Downloader.installGame(\''+g.appid+'\',\''+jsesc(nm)+'\')" title="一鍵入庫">' +
                  '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>' +
                '</button>';
  }
  return '<div class="'+cardClass+'" style="--i:'+g.__i+'" data-appid="'+g.appid+'" onclick="openGameDetail(\''+g.appid+'\',\''+jsesc(nm)+'\',\''+jsesc(g.image||'')+'\')">' +
           cornerTagsDiv +
           '<div class="name" title="'+h(nm)+'">'+h(nm)+'</div>' +
           '<img src="'+h(g.image||'')+'" loading="lazy" onerror="imgFb(this,'+g.appid+')">' +
           actionBtn +
           '<div class="aid" title="'+g.appid+'"><span class="aid-num">'+g.appid+'</span></div>' +
         '</div>';
}

async function loadBrowse(page, append){
  var c = document.getElementById('results');
  if(append === undefined) append = (page > 0);
  if(_browse.loading) return;
  _browse.loading = true;
  try {
    var r = await pywebview.api.browse_games(page*_browse.per, _browse.per);
    if(!r || r.offline || r.error){ showBrowseOffline(); _browse.loading = false; return; }
    _browse.page = page;
    var glist = (r && (r.games || r.items)) || [];
    var html = '';
    for(var i=0;i<glist.length;i++){ var g = glist[i]; g.__i = i; html += _browseCard(g); }
    if(append){ c.insertAdjacentHTML('beforeend', html); }
    else { c.innerHTML = html; }
    c.classList.add('browse-grid');
    fixImgs(c);
    var info = document.getElementById('browse-info');
    if(info){ info.style.display = 'block'; info.textContent = '已自動加載全部遊戲 · 共 '+r.total+' 款'; }
    var btn = document.getElementById('btn-load-more');
    if(btn){
      btn.style.display = ((page+1)*_browse.per < r.total) ? 'inline-block' : 'none';
      btn.textContent = '⬇ 加載更多';
    }
  } catch(e){
    c.innerHTML = '<div class="empty"><div class="icon">❌</div><p>瀏覽加載失敗: '+(e.message||e)+'</p></div>';
    tt('瀏覽加載失敗', 'er');
  }
  _browse.loading = false;
}

function loadMore(){ if(!_browse.loading) loadBrowse(_browse.page+1, true); }

function switchBrowse(){
  document.getElementById('q').value = '';
  _browse.loading = false;
  loadBrowse(0, false);
}

function showBrowseOffline(){
  var c = document.getElementById('results');
  c.classList.remove('browse-grid');
  c.innerHTML = '<div class="empty"><p style="margin-bottom:12px">⚠️ 遊戲目錄需联網加載（服务器暫不可達）</p>'
    + '<button class="btn btn-o" onclick="switchBrowse()">重新加載</button>'
    + '<div style="margin-top:14px;font-size:12px;color:var(--gray)">已入庫遊戲仍可在「管理入庫」頁查看</div></div>';
  document.getElementById('browse-info').style.display = 'none';
  document.getElementById('btn-load-more').style.display = 'none';
}

