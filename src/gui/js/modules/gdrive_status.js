/* SteamManifestUpdater - Module: modules/gdrive_status.js */
// ═══════════════════════════════════════════════════════
// 遊戲小卡「檢視網盤狀況」相關邏輯
// ═══════════════════════════════════════════════════════
var _gdsCurrentAppId = '';
var _gdsCurrentGameName = '';
var _gdsData = null;
var _gdsSelectedIdx = 0;

async function inspectDriveStatus(appid, name){
  // 關閉所有展開的下拉選單
  document.querySelectorAll('.card-dd.show').forEach(function(d){ d.classList.remove('show'); });
  
  _gdsCurrentAppId = String(appid).trim();
  _gdsCurrentGameName = name || ('App_' + _gdsCurrentAppId);
  _gdsSelectedIdx = 0;
  
  var modal = document.getElementById('modal-drive-status');
  var subTitle = document.getElementById('gds-subtitle');
  var body = document.getElementById('gds-body');
  var sel = document.getElementById('gds-select');
  var badge = document.getElementById('gds-drive-badge');
  
  if(!modal) return;
  modal.classList.remove('hidden');
  
  if(subTitle) subTitle.textContent = '🎮 ' + _gdsCurrentGameName + ' (' + _gdsCurrentAppId + ')';
  if(badge) badge.textContent = '';
  if(sel) sel.innerHTML = '<option>載入網盤設定中…</option>';
  if(body) body.innerHTML = '<div style="padding:24px 0;text-align:center;color:var(--gray)"><span class="spin-dot" style="display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--pink-deep);margin-right:6px"></span>檢測網盤收錄狀況中…</div>';
  
  try{
    var res = await pywebview.api.get_game_cloud_drive_status(_gdsCurrentAppId, _gdsCurrentGameName);
    _gdsData = res;
    
    if(!res || !res.ok || !res.drives || !res.drives.length){
      if(sel) sel.innerHTML = '<option value="">(尚未定義任何網盤)</option>';
      if(body){
        body.innerHTML = '<div style="padding:20px;text-align:center;color:var(--gray);border:1px dashed var(--pink-light);border-radius:10px;font-size:12px">' +
          '⚠️ 目前尚未在「設置 ➔ 進階」中設定任何 Google Drive 網盤，請前往設定頁面新增網盤！' +
          '</div>';
      }
      return;
    }
    
    // 渲染下拉選單（核心：選項使用網盤名稱顯示，嚴禁顯示網址）
    if(sel){
      sel.innerHTML = '';
      res.drives.forEach(function(d, idx){
        var opt = document.createElement('option');
        opt.value = String(idx);
        opt.textContent = (d.name || ('網盤 ' + (idx + 1))) + ' (優先級 ' + d.priority + ')' + (d.has_patch ? ' ★ [有補丁]' : '');
        sel.appendChild(opt);
      });
      sel.value = '0';
    }
    
    renderDriveStatusDetail(0);
  }catch(e){
    if(body) body.innerHTML = '<div style="padding:20px;text-align:center;color:var(--err)">查詢失敗: ' + h(e.message||e) + '</div>';
  }
}

function onDriveSelected(idxStr){
  var idx = parseInt(idxStr, 10);
  if(isNaN(idx)) idx = 0;
  _gdsSelectedIdx = idx;
  renderDriveStatusDetail(idx);
}

function renderDriveStatusDetail(idx){
  var body = document.getElementById('gds-body');
  var badge = document.getElementById('gds-drive-badge');
  if(!_gdsData || !_gdsData.drives || !_gdsData.drives[idx]) return;
  
  var d = _gdsData.drives[idx];
  if(badge) badge.textContent = '優先級 ' + d.priority + (d.priority === 1 ? ' (最高)' : '');
  
  var isInstalledFromHere = (_gdsData.installed_source && _gdsData.installed_source === d.name);
  var isDeployed = !!_gdsData.is_deployed;
  var html = '';
  
  // 1. 網盤與本地部署狀態資訊列
  html += '<div style="background:rgba(0,188,212,0.06);border:1px solid rgba(0,188,212,0.25);border-radius:10px;padding:10px 12px;margin-bottom:12px">';
  html += '  <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px">';
  html += '    <div style="font-weight:700;font-size:13px;color:#00bcd4;display:flex;align-items:center;gap:6px">';
  html += '      <span>📁 網盤名稱：' + h(d.name) + '</span>';
  if(isInstalledFromHere){
    html += '      <span style="font-size:10px;background:#4caf50;color:#fff;padding:1px 6px;border-radius:8px;font-weight:600">★ 當前已安裝補丁來源</span>';
  }
  html += '    </div>';
  html += '    <div style="font-size:12px;display:flex;align-items:center;gap:6px">';
  html += '      <span style="color:var(--gray)">本地部署：</span>' + (isDeployed ? '<span style="color:#2E7D32;font-weight:bold">✅ 已部署</span>' : '<span style="color:#D32F2F;font-weight:bold">❌ 未部署</span>');
  html += '    </div>';
  html += '  </div>';
  html += '</div>';
  
  // 2. 補丁檔案狀況
  if(d.has_patch && d.files && d.files.length){
    html += '<div style="margin-bottom:6px;font-size:12px;font-weight:700;color:var(--fg);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px">';
    html += '  <span style="color:#2e7d32">✅ 該網盤已收錄此遊戲補丁 (共 ' + d.files.length + ' 個檔案)：</span>';
    if(isDeployed){
      html += '  <button class="btn btn-o btn-xs" style="color:var(--err);border-color:var(--err);font-size:10px;padding:2px 8px;cursor:pointer" onclick="removeOnlinePatch(_gdsCurrentAppId, _gdsCurrentGameName)">🗑️ 移除補丁 (還原原檔)</button>';
    } else {
      html += '  <button class="btn btn-p btn-xs" style="font-size:10px;padding:2px 8px;cursor:pointer;font-weight:700" onclick="manualDeployPatch(_gdsCurrentAppId, _gdsCurrentGameName)">🚀 立即部署</button>';
    }
    html += '</div>';
    
    html += '<div style="display:flex;flex-direction:column;gap:6px;margin-bottom:10px">';
    d.files.forEach(function(f){
      var isRar = f.name.endsWith('.rar') || f.name.endsWith('.zip');
      var icon = isRar ? '📦' : '📜';
      var tag = isRar ? '<span style="font-size:10px;background:rgba(0,188,212,0.15);color:#00bcd4;padding:1px 5px;border-radius:4px;font-weight:600">補丁包</span>' 
                      : '<span style="font-size:10px;background:rgba(76,175,80,0.15);color:#4caf50;padding:1px 5px;border-radius:4px;font-weight:600">Lua</span>';
                      
      html += '<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 10px;background:rgba(255,255,255,0.6);border:1px solid var(--pink-light);border-radius:8px;font-size:12px">';
      html += '  <div style="display:flex;align-items:center;gap:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">';
      html += '    <span>' + icon + '</span>';
      html += '    <span style="font-weight:600" title="' + h(f.path) + '">' + h(f.name) + '</span>';
      html += '    ' + tag;
      html += '  </div>';
      html += '</div>';
    });
    html += '</div>';
  } else {
    html += '<div style="padding:18px;text-align:center;background:rgba(0,0,0,0.02);border:1px dashed rgba(0,0,0,0.1);border-radius:10px;margin-bottom:10px">';
    html += '  <div style="font-size:13px;color:var(--gray)">⚪ 此網盤中暫無與「' + h(_gdsCurrentGameName) + '」相關的補丁檔案</div>';
    html += '</div>';
  }
  
  if(body) body.innerHTML = html;
}

function closeDriveStatusModal(){
  var modal = document.getElementById('modal-drive-status');
  if(modal) modal.classList.add('hidden');
}

function openCurrentDriveInBrowser(){
  if(!_gdsData || !_gdsData.drives || !_gdsData.drives[_gdsSelectedIdx]) return;
  var d = _gdsData.drives[_gdsSelectedIdx];
  if(d && d.url){
    pywebview.api.open_url(d.url);
    tt('已在預設瀏覽器中開啟「' + (d.name || '網盤') + '」', 'ok');
  } else {
    tt('該網盤尚未配置有效的 URL', 'er');
  }
}
