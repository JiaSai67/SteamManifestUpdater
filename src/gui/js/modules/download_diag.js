/* SteamManifestUpdater - Module: modules/download_diag.js */
// ═══════════════════════════════════════════════════════
// 🌟 診斷日誌模組與彈窗控制
// ═══════════════════════════════════════════════════════
window._lastManifestLog = null;

function renderLogMarkdownToHtml(mdText){
  if(!mdText) return '<div style="color:var(--gray);text-align:center;padding:40px">尚無任何日誌內容</div>';
  
  var lines = mdText.split('\n');
  var html = [];
  var inTable = false;
  var inCode = false;
  var codeBuf = [];

  for(var i=0; i<lines.length; i++){
    var line = lines[i];

    // 處理 Code Block
    if(line.startsWith('```')){
      if(inCode){
        inCode = false;
        html.push('<div class="log-code">' + escHtml(codeBuf.join('\n')) + '</div>');
        codeBuf = [];
      } else {
        inCode = true;
        codeBuf = [];
      }
      continue;
    }
    if(inCode){
      codeBuf.push(line);
      continue;
    }

    // 處理 Markdown Table
    if(line.trim().startsWith('|') && line.trim().endsWith('|')){
      var rawCells = line.split('|').map(function(c){ return c.trim(); }).filter(function(c, idx, arr){ return idx > 0 && idx < arr.length - 1; });
      if(line.indexOf('---') > -1){
        continue;
      }
      if(!inTable){
        inTable = true;
        html.push('<table class="log-table"><thead><tr>');
        rawCells.forEach(function(cell){
          html.push('<th>' + parseInlineLogMd(cell) + '</th>');
        });
        html.push('</tr></thead><tbody>');
      } else {
        html.push('<tr>');
        rawCells.forEach(function(cell){
          html.push('<td>' + parseInlineLogMd(cell) + '</td>');
        });
        html.push('</tr>');
      }
      continue;
    } else {
      if(inTable){
        inTable = false;
        html.push('</tbody></table>');
      }
    }

    if(!line.trim()){
      continue;
    }

    // Headers & items
    if(line.startsWith('# ')){
      html.push('<h2 class="log-title">' + parseInlineLogMd(line.slice(2)) + '</h2>');
    } else if(line.startsWith('## ')){
      html.push('<h3 class="log-section-title">' + parseInlineLogMd(line.slice(3)) + '</h3>');
    } else if(line.startsWith('### ')){
      html.push('<h4 class="log-sub-title">' + parseInlineLogMd(line.slice(4)) + '</h4>');
    } else if(line.startsWith('> ')){
      html.push('<blockquote class="log-quote">' + parseInlineLogMd(line.slice(2)) + '</blockquote>');
    } else if(line.startsWith('- ')){
      html.push('<div class="log-item">• ' + parseInlineLogMd(line.slice(2)) + '</div>');
    } else {
      html.push('<div class="log-line">' + parseInlineLogMd(line) + '</div>');
    }
  }

  if(inTable) html.push('</tbody></table>');
  if(inCode) html.push('<div class="log-code">' + escHtml(codeBuf.join('\n')) + '</div>');

  return html.join('');
}

function parseInlineLogMd(text){
  var s = escHtml(text);
  s = s.replace(/`([^`]+)`/g, '<code class="log-inline-code">$1</code>');
  s = s.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
  s = s.replace(/🟢\s*OK/g, '<span class="log-badge-ok">🟢 OK</span>');
  s = s.replace(/✅\s*更新成功/g, '<span class="log-badge-ok">✅ 更新成功</span>');
  s = s.replace(/🔴\s*ERROR/g, '<span class="log-badge-err">🔴 ERROR</span>');
  s = s.replace(/❌\s*更新未完成/g, '<span class="log-badge-err">❌ 更新未完成</span>');
  s = s.replace(/🟡\s*WARN/g, '<span class="log-badge-warn">🟡 WARN</span>');
  s = s.replace(/⚠️/g, '<span class="log-badge-warn">⚠️</span>');
  s = s.replace(/⚪\s*INFO/g, '<span class="log-badge-info">⚪ INFO</span>');
  return s;
}

async function openManifestLogModal(logData){
  var modal = document.getElementById('manifest-log-modal');
  if(!modal) return;

  var data = logData;
  if(!data){
    if(window._lastManifestLog){
      data = window._lastManifestLog;
    } else {
      try {
        data = await pywebview.api.get_latest_manifest_log();
      } catch(e){
        data = { success: false, report_markdown: '無法載入日誌: ' + e };
      }
    }
  }

  window._lastManifestLog = data;

  var badgeEl = document.getElementById('log-status-badge');
  var gameMetaEl = document.getElementById('log-meta-game');
  var timeMetaEl = document.getElementById('log-meta-time');
  var bodyEl = document.getElementById('log-modal-content');

  var isSuccess = data && (data.ok === true || data.success === true);
  if(badgeEl){
    badgeEl.textContent = isSuccess ? '✅ 更新成功' : '❌ 更新未完成';
    badgeEl.className = 'chip ' + (isSuccess ? 'green' : 'red');
  }

  if(gameMetaEl){
    var gName = (data && data.game_name) ? data.game_name : ((data && data.appid) ? ('App_' + data.appid) : '最新更新');
    var aId = (data && data.appid) ? (' (AppID: ' + data.appid + ')') : '';
    gameMetaEl.textContent = '目標: ' + gName + aId;
  }

  if(timeMetaEl){
    var ms = (data && data.duration_ms) ? (data.duration_ms + ' ms') : '';
    timeMetaEl.textContent = ms ? ('耗時: ' + ms) : '';
  }

  if(bodyEl){
    var md = (data && data.report_markdown) ? data.report_markdown : ((data && data.msg) ? data.msg : '（尚無日誌記錄）');
    bodyEl.innerHTML = renderLogMarkdownToHtml(md);
    bodyEl.scrollTop = 0;
  }

  modal.classList.add('active');
}

function closeManifestLogModal(e){
  if(e && e.target && e.target !== e.currentTarget && !e.target.classList.contains('detail-close-btn')) return;
  var modal = document.getElementById('manifest-log-modal');
  if(modal) modal.classList.remove('active');
}

// ═══════════════════════════════════════════════════════
// Steam 下載中斷與錯誤深度排障彈窗控制邏輯
// ═══════════════════════════════════════════════════════
var _curDiagAppid = '';
var _curDiagGameName = '';

async function openDownloadDiagnosticModal(appid, gameName){
  var aidStr = String(appid || '').trim();
  if(!aidStr) return;
  _curDiagAppid = aidStr;
  _curDiagGameName = gameName || ('App_' + aidStr);

  var modal = document.getElementById('modal-download-diag');
  if(!modal) return;

  var badgeEl = document.getElementById('diag-status-badge');
  var metaEl = document.getElementById('diag-meta-game');
  var bodyEl = document.getElementById('diag-modal-content');
  var healBtn = document.getElementById('diag-btn-heal');

  if(metaEl) metaEl.textContent = '目標: ' + _curDiagGameName + ' (AppID: ' + aidStr + ')';
  if(badgeEl){
    badgeEl.textContent = '🔍 正在深度掃描排障…';
    badgeEl.className = 'chip yellow';
  }
  if(healBtn){
    healBtn.disabled = false;
    healBtn.textContent = '🛠️ 一鍵自動自癒修復並重試';
  }
  if(bodyEl){
    bodyEl.innerHTML = '<div style="text-align:center;padding:40px 0;color:var(--gray)"><div class="card-spinner" style="margin:0 auto 12px"></div>正在深入掃描 Steam 日誌、檔案唯讀屬性、Depot Key 與 Manifest 齊全度…</div>';
  }

  modal.classList.add('active');

  try {
    var res = await pywebview.api.diagnose_game_download_error(aidStr, _curDiagGameName);
    if(res && res.ok && res.report){
      var rep = res.report;
      if(badgeEl){
        badgeEl.textContent = '🔴 ' + (rep.primary_error || '異常');
        badgeEl.className = 'chip red';
      }
      if(bodyEl){
        bodyEl.innerHTML = renderLogMarkdownToHtml(rep.markdown);
        bodyEl.scrollTop = 0;
      }
      window._lastDownloadDiag = rep;
    } else {
      if(bodyEl) bodyEl.innerHTML = '<div class="empty" style="padding:20px 0"><p>診斷失敗: ' + (res.msg || '未知錯誤') + '</p></div>';
    }
  } catch(e){
    if(bodyEl) bodyEl.innerHTML = '<div class="empty" style="padding:20px 0"><p>診斷請求出錯: ' + (e.message || e) + '</p></div>';
  }
}

function closeDownloadDiagnosticModal(e){
  if(e && e.target && e.target !== e.currentTarget && !e.target.classList.contains('detail-close-btn')) return;
  var modal = document.getElementById('modal-download-diag');
  if(modal) modal.classList.remove('active');
}

async function copyDownloadDiagText(){
  var rep = window._lastDownloadDiag;
  var text = (rep && rep.markdown) ? rep.markdown : '';
  if(!text){
    tt('無可複製的診斷內容', 'wn');
    return;
  }
  try {
    if(navigator.clipboard && navigator.clipboard.writeText){
      await navigator.clipboard.writeText(text);
    } else {
      var ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
    }
    tt('📋 已複製排障報告 Markdown 至剪貼簿！', 'ok');
  } catch(err){
    tt('複製失敗: ' + err, 'er');
  }
}

async function healDownloadDiagnosticError(){
  if(!_curDiagAppid) return;
  var aidStr = _curDiagAppid;
  var gName = _curDiagGameName;
  var healBtn = document.getElementById('diag-btn-heal');
  if(healBtn){
    healBtn.disabled = true;
    healBtn.textContent = '⏳ 正在自動自癒修復中…';
  }
  tt('⏳ 正在為「' + gName + '」解除鎖定、補齊金鑰並重啟 Steam 下載…', 'ok', 4000);

  try {
    var res = await pywebview.api.heal_game_download_error(aidStr, gName);
    if(res && res.ok){
      tt('🎉 ' + res.msg, 'ok', 6000);
      closeDownloadDiagnosticModal();
      // 重新啟動卡片進度條監聽
      updateCardProgress(aidStr, 25, '🚀 已完成自癒修復，正在重新監控 Steam 下載…', false);
      // 自動觸發 ag 背景重試
      ag(aidStr, gName);
    } else {
      tt('❌ 自癒修復未果: ' + (res.msg || '未知錯誤'), 'er', 6000);
      if(healBtn){
        healBtn.disabled = false;
        healBtn.textContent = '🛠️ 立即一鍵自動修復並重試';
      }
    }
  } catch(e){
    tt('❌ 修復異常: ' + (e.message || e), 'er', 6000);
    if(healBtn){
      healBtn.disabled = false;
      healBtn.textContent = '🛠️ 立即一鍵自動修復並重試';
    }
  }
}

async function copyManifestLogText(){
  var data = window._lastManifestLog;
  var text = (data && data.report_markdown) ? data.report_markdown : '';
  if(!text){
    tt('無可複製的日誌內容', 'wn');
    return;
  }
  try {
    if(navigator.clipboard && navigator.clipboard.writeText){
      await navigator.clipboard.writeText(text);
    } else {
      var ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
    }
    tt('📋 已複製診斷報告 Markdown 至剪貼簿！', 'ok');
  } catch(err){
    tt('複製失敗: ' + err, 'er');
  }
}

async function openManifestLogInEditor(){
  var path = (window._lastManifestLog && window._lastManifestLog.log_path) ? window._lastManifestLog.log_path : '';
  try {
    var res = await pywebview.api.open_manifest_log_file(path);
    if(res && res.ok){
      tt('📝 已在文字編輯器中開啟日誌！', 'ok');
    } else {
      tt('開啟日誌失敗: ' + (res.msg || '找不到檔案'), 'er');
    }
  } catch(e){
    tt('開啟日誌失敗: ' + e, 'er');
  }
}

async function openManifestLogsDirectory(){
  try {
    var res = await pywebview.api.open_manifest_logs_dir();
    if(res && res.ok){
      tt('📁 已在檔案總管開啟日誌資料夾！', 'ok');
    } else {
      tt('開啟目錄失敗: ' + (res.msg || ''), 'er');
    }
  } catch(e){
    tt('開啟目錄失敗: ' + e, 'er');
  }
}

