// ═══════════════════════════════════════════════════════
// 🩺 系統健康體檢 (Health Check) 業務互動邏輯模組
// ═══════════════════════════════════════════════════════

var _latestHealthData = null;
var _currentHealthLogMarkdown = '';

/**
 * 切換至「系統」分頁時呈現健康狀態 (0ms 秒開，絕不再重複執行體檢)
 */
async function initSystemHealthView(){
  try {
    loadSystemDiagnosticInfo();
    loadHealthHistoryList();
    if(_latestHealthData){
      renderHealthCheckOverview(_latestHealthData);
      return;
    }
    if(window.pywebview && pywebview.api && pywebview.api.get_latest_system_health){
      var res = await pywebview.api.get_latest_system_health();
      if(res && res.ok){
        renderHealthCheckOverview(res);
      }
    }
  } catch(e){
    console.warn('[HealthCheck] 初始化體檢視圖異常:', e);
  }
}

/**
 * 觸發全面健康體檢
 */
async function triggerSystemHealthCheck(){
  var btn = document.getElementById('btn-run-health-check');
  if(btn){
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span><span>正在體檢中...</span>';
  }

  try {
    if(!window.pywebview || !pywebview.api || !pywebview.api.run_system_health_check){
      if(window.tt) tt('後端 API 尚未就緒', 'er');
      return;
    }

    if(window.tt) tt('正在對 Steam 環境、平台連線與憑證進行全方位體檢...', 'in', 2500);
    var res = await pywebview.api.run_system_health_check();
    if(res && res.ok){
      renderHealthCheckOverview(res);
      loadHealthHistoryList();
      if(window.tt) tt('體檢完成！綜合評分: ' + res.score + ' 分 (' + res.rating_text + ')', res.score >= 75 ? 'ok' : 'er', 3500);
    } else {
      if(window.tt) tt('體檢失敗: ' + ((res && res.rating_text) || '未預期錯誤'), 'er');
    }
  } catch(e){
    if(window.tt) tt('體檢過程發生錯誤: ' + (e.message || e), 'er');
  } finally {
    if(btn){
      btn.disabled = false;
      btn.innerHTML = '<span>⚡</span><span>開始全面體檢</span>';
    }
  }
}

/**
 * 渲染健康度儀表板與四大維度卡片
 */
function renderHealthCheckOverview(data){
  if(!data) return;
  _latestHealthData = data;
  _currentHealthLogMarkdown = data.report_markdown || '';

  // 1. 儀表板得分與狀態
  var scoreEl = document.getElementById('health-score-val');
  var circleEl = document.getElementById('health-score-circle');
  var badgeEl = document.getElementById('health-status-badge');
  var descEl = document.getElementById('health-status-desc');
  var timeEl = document.getElementById('health-last-time');

  var score = data.score != null ? data.score : 100;
  var color = data.color || '#4CAF50';

  if(scoreEl){
    scoreEl.textContent = score;
    scoreEl.style.color = color;
  }
  if(circleEl){
    circleEl.style.borderColor = color;
    circleEl.style.background = 'rgba(' + (score >= 90 ? '76,175,80' : (score >= 75 ? '139,195,74' : (score >= 50 ? '255,152,0' : '244,67,54'))) + ', 0.12)';
  }
  if(badgeEl){
    badgeEl.textContent = data.rating === 'EXCELLENT' ? '狀態極佳' : (data.rating === 'GOOD' ? '狀態良好' : (data.rating === 'WARN' || data.rating === 'WARNING' ? '部分警示' : '異常中斷'));
    badgeEl.style.background = color;
  }
  if(descEl){
    descEl.textContent = data.rating_text || '系統運行狀態';
  }
  if(timeEl){
    timeEl.textContent = '最後體檢時間：' + (data.timestamp || '剛剛') + ' (耗時: ' + (data.elapsed_ms || 0) + ' ms)';
  }

  // 2. 渲染四大維度細節卡片
  var grid = document.getElementById('health-details-grid');
  if(!grid) return;

  var checks = data.checks || {};
  var html = '';

  var sectionIcons = {
    infra_env: '🏗️',
    steam_local: '🎮',
    steam_ecosystem: '⚡',
    network_sources: '🌐',
    steam_env: '🎮',
    sources: '🌐',
    credentials: '🪪',
    storage: '💾',
    party_lobby: '👥'
  };

  for(var secKey in checks){
    var sec = checks[secKey];
    var sIcon = sectionIcons[secKey] || '📋';
    var isSecOk = sec.status === 'OK';
    var secBadgeColor = isSecOk ? '#4CAF50' : (sec.status === 'WARN' ? '#FF9800' : (sec.status === 'INFO' ? '#2196F3' : '#F44336'));

    html += '<div class="health-sec-card" style="background:var(--bg-card);border:1px solid rgba(255,102,153,0.18);border-radius:12px;padding:12px 14px">';
    html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;padding-bottom:6px;border-bottom:1px dashed rgba(255,255,255,0.08)">';
    html += '<span style="font-weight:700;font-size:12.5px;color:var(--text);display:flex;align-items:center;gap:6px"><span>' + sIcon + '</span><span>' + sec.title + '</span></span>';
    html += '<span style="font-size:9.5px;font-weight:700;padding:1px 6px;border-radius:6px;background:' + secBadgeColor + ';color:#fff">' + sec.status + '</span>';
    html += '</div>';

    html += '<div style="display:flex;flex-direction:column;gap:6px">';
    var items = sec.items || [];
    for(var i = 0; i < items.length; i++){
      var item = items[i];
      var itemIcon = item.status === 'OK' ? '🟢' : (item.status === 'WARN' ? '🟡' : (item.status === 'INFO' ? '🔵' : '🔴'));
      
      html += '<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px;font-size:11px">';
      html += '<div style="flex:1">';
      html += '<div style="font-weight:600;color:var(--text);display:flex;align-items:center;gap:4px"><span>' + itemIcon + '</span><span>' + item.name + '</span></div>';
      html += '<div style="color:var(--gray);font-size:10px;margin-left:14px;line-height:1.3">' + item.desc + '</div>';
      html += '</div>';

      // 一鍵修復動作按鈕
      if(item.action === 'inject_dll'){
        html += '<button class="btn btn-p btn-xs" onclick="wizardInstallSteamTools()" style="padding:2px 6px;font-size:9.5px;white-space:nowrap">🛠️ 注入核心</button>';
      } else if(item.action === 'login_discord'){
        html += '<button class="btn btn-p btn-xs" onclick="startDualPlatformSandboxLogin()" style="padding:2px 6px;font-size:9.5px;white-space:nowrap">🔑 立即登入</button>';
      } else if(item.action === 'config_hubcap'){
        html += '<button class="btn btn-o btn-xs" onclick="openHubcapKeyInputModal()" style="padding:2px 6px;font-size:9.5px;white-space:nowrap">⚙️ 配置 Key</button>';
      } else if(item.action === 'install_webview2'){
        html += '<button class="btn btn-o btn-xs" onclick="if(window.pywebview && pywebview.api && pywebview.api.open_external_url){pywebview.api.open_external_url(\'https://developer.microsoft.com/zh-tw/microsoft-edge/webview2/\');}else{window.open(\'https://developer.microsoft.com/zh-tw/microsoft-edge/webview2/\');}" style="padding:2px 6px;font-size:9.5px;white-space:nowrap">🌐 下載內核</button>';
      } else if(item.action === 'open_telemetry'){
        html += '<button class="btn btn-p btn-xs" onclick="if(window.openPartyTelemetryModal){openPartyTelemetryModal();}else if(window.switchTab){switchTab(\'party\');setTimeout(openPartyTelemetryModal,300);}" style="padding:2px 6px;font-size:9.5px;white-space:nowrap">📊 檢視遙測</button>';
      } else if(item.action === 'auth_party_discord'){
        html += '<button class="btn btn-p btn-xs" onclick="if(window.startDiscordOAuthFlow){startDiscordOAuthFlow();}else if(window.switchTab){switchTab(\'party\');}" style="padding:2px 6px;font-size:9.5px;white-space:nowrap">🎮 綁定認證</button>';
      }
      html += '</div>';
    }
    html += '</div>';
    html += '</div>';
  }

  grid.innerHTML = html;
}

/**
 * 載入歷史體檢日誌 (至多 5 份)
 */
async function loadHealthHistoryList(){
  var wrap = document.getElementById('health-history-list');
  if(!wrap) return;

  try {
    if(!window.pywebview || !pywebview.api || !pywebview.api.get_system_health_logs){
      wrap.innerHTML = '<div style="text-align:center;padding:12px;color:var(--gray);font-size:11px">暫無日誌記錄</div>';
      return;
    }

    var logs = await pywebview.api.get_system_health_logs();
    if(!logs || logs.length === 0){
      wrap.innerHTML = '<div style="text-align:center;padding:14px;color:var(--gray);font-size:11.5px">尚未產生日誌記錄 (自動保留至多 5 份最新記錄)</div>';
      return;
    }

    var html = '';
    for(var i = 0; i < logs.length; i++){
      var log = logs[i];
      var kb = Math.round(log.size_bytes / 1024 * 10) / 10;
      html += '<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 12px;border-radius:8px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,102,153,0.12)">';
      html += '<div style="display:flex;align-items:center;gap:8px">';
      html += '<span style="font-size:13px">📄</span>';
      html += '<div>';
      html += '<div style="font-weight:600;font-size:11.5px;color:var(--text)">' + log.filename + '</div>';
      html += '<div style="font-size:10px;color:var(--gray)">' + log.mtime + ' · 大小: ' + kb + ' KB</div>';
      html += '</div>';
      html += '</div>';
      html += '<button class="btn btn-o btn-xs" onclick="openHealthLogModal(\'' + log.filename + '\')" style="padding:3px 10px;font-size:10.5px">檢視日誌</button>';
      html += '</div>';
    }
    wrap.innerHTML = html;
  } catch(e){
    wrap.innerHTML = '<div style="text-align:center;padding:12px;color:var(--gray);font-size:11px">載入歷史日誌異常: ' + (e.message || e) + '</div>';
  }
}

/**
 * 開啟最新體檢日誌
 */
async function openLatestHealthLogModal(){
  if(_latestHealthData && _latestHealthData.log_filename){
    await openHealthLogModal(_latestHealthData.log_filename);
  } else {
    await openHealthLogModal('latest_health_check.log');
  }
}

/**
 * 依據檔名開啟特定體檢日誌彈窗
 */
async function openHealthLogModal(filename){
  var modal = document.getElementById('health-log-modal');
  var fileMeta = document.getElementById('health-log-meta-file');
  var timeMeta = document.getElementById('health-log-meta-time');
  var contentEl = document.getElementById('health-log-modal-content');
  var badge = document.getElementById('health-log-score-badge');

  if(!modal || !contentEl) return;
  modal.classList.add('active');

  contentEl.innerHTML = '<div style="text-align:center;padding:36px;color:var(--gray);font-size:12px">⏳ 正在讀取體檢日誌內容…</div>';
  if(fileMeta) fileMeta.textContent = '日誌檔案: ' + (filename || '-');
  if(timeMeta) timeMeta.textContent = '讀取中...';

  try {
    if(!window.pywebview || !pywebview.api || !pywebview.api.get_system_health_log_content){
      contentEl.innerHTML = '<div style="padding:20px;color:var(--err)">pywebview API 未就緒</div>';
      return;
    }

    var res = await pywebview.api.get_system_health_log_content(filename);
    if(res && res.ok){
      _currentHealthLogMarkdown = res.content || '';
      if(timeMeta) timeMeta.textContent = '已載入';
      if(badge && _latestHealthData){
        badge.textContent = (_latestHealthData.score || 100) + '分';
        badge.className = 'chip ' + (_latestHealthData.score >= 75 ? 'green' : 'red');
      }

      var rawMd = res.content || '';
      var formatted = rawMd
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/^# (.*$)/gim, '<h2 style="margin:8px 0;font-size:16px;color:var(--text);border-bottom:1px solid rgba(255,102,153,.2);padding-bottom:4px">$1</h2>')
        .replace(/^## (.*$)/gim, '<h3 style="margin:12px 0 6px 0;font-size:13.5px;color:#FF6699">$1</h3>')
        .replace(/\*\*(.*?)\*\*/gim, '<strong style="color:var(--text)">$1</strong>')
        .replace(/`(.*?)`/gim, '<code style="background:rgba(255,255,255,0.08);padding:1px 5px;border-radius:4px;font-family:monospace;font-size:11px">$1</code>')
        .replace(/\n\n/gim, '<br><br>');

      contentEl.innerHTML = '<div style="font-size:12px;line-height:1.6;color:var(--text)">' + formatted + '</div>';
    } else {
      contentEl.innerHTML = '<div style="padding:20px;color:var(--err)">讀取失敗: ' + ((res && res.msg) || '日誌不存在') + '</div>';
    }
  } catch(e){
    contentEl.innerHTML = '<div style="padding:20px;color:var(--err)">讀取異常: ' + (e.message || e) + '</div>';
  }
}

/**
 * 關閉日誌彈窗
 */
function closeHealthLogModal(e){
  if(e && e.target){
    var isCloseBtn = (e.target.closest && e.target.closest('.detail-close-btn')) || (e.target.classList && e.target.classList.contains('detail-close-btn'));
    if(!isCloseBtn && !isStrictBackdropClick(e, document.getElementById('health-log-modal'))) return;
  }
  var modal = document.getElementById('health-log-modal');
  if(modal) modal.classList.remove('active');
}

/**
 * 複製體檢日誌 Markdown 內容
 */
function copyHealthLogMarkdown(){
  if(!_currentHealthLogMarkdown){
    if(window.tt) tt('目前無可複製之日誌內容', 'in');
    return;
  }
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(_currentHealthLogMarkdown).then(function(){
      if(window.tt) tt('已複製體檢報告 Markdown 內容至剪貼簿！', 'ok');
    });
  } else {
    var ta = document.createElement('textarea');
    ta.value = _currentHealthLogMarkdown;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    if(window.tt) tt('已複製體檢報告至剪貼簿！', 'ok');
  }
}

// ═══════════════════════════════════════════════════════
// 🚨 異常監控、PC 名稱/Discord 偵測與錯誤通報互動邏輯
// ═══════════════════════════════════════════════════════

/**
 * 載入並渲染系統診斷資訊 (PC 電腦名稱、Discord 帳號、系統環境)
 */
async function loadSystemDiagnosticInfo(){
  try {
    if(!window.pywebview || !pywebview.api || !pywebview.api.get_system_diagnostic_info) return;
    var res = await pywebview.api.get_system_diagnostic_info();
    if(res && res.ok && res.data){
      var d = res.data;
      var elPc = document.getElementById('diag-pc-name');
      var elDc = document.getElementById('diag-discord-name');
      var elOs = document.getElementById('diag-os-platform');
      var elCl = document.getElementById('diag-client-id');

      if(elPc) elPc.textContent = (d.pc_name || 'Unknown') + ' (' + (d.windows_user || 'User') + ')';
      if(elDc){
        var dcStr = d.discord_name || '未綁定 Discord';
        if(d.discord_id) dcStr += ' (ID: ' + d.discord_id + ')';
        elDc.textContent = dcStr;
      }
      if(elOs) elOs.textContent = (d.os_platform || '') + ' (' + (d.os_arch || '') + ')';
      if(elCl) elCl.textContent = 'Python ' + (d.python_version || '') + ' | ' + (d.client_id || '無 Client ID');
    }
  } catch(e){
    console.warn('[HealthCheck] 載入系統診斷資訊異常:', e);
  }
}

/**
 * 手動觸發 Discord 錯誤通報 Webhook 測試
 */
async function triggerTestErrorWebhook(){
  var btn = document.getElementById('btn-test-error-webhook');
  if(btn){
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span><span>發送測試中...</span>';
  }

  try {
    if(!window.pywebview || !pywebview.api || !pywebview.api.report_error){
      if(window.tt) tt('後端 API 尚未就緒', 'er');
      return;
    }

    if(window.tt) tt('正在向官方 Discord 守護通道發送測試通報...', 'in', 2000);
    var res = await pywebview.api.report_error(
      '手動連線測試 (前端面板觸發)',
      '使用者於「系統設置 > 異常監控中樞」點擊了手動連線測試。\nPC 名稱與 Discord 帳號已完整封裝傳遞。',
      'Settings System Tab Diagnostics',
      'INFO'
    );

    if(res && res.ok){
      if(window.tt) tt('✅ Discord Webhook 測試通報成功！請查看守護頻道', 'ok', 3500);
    } else {
      if(window.tt) tt('測試發送失敗: ' + ((res && res.msg) || '請檢查網路連線'), 'er');
    }
  } catch(e){
    if(window.tt) tt('發送測試失敗: ' + (e.message || e), 'er');
  } finally {
    if(btn){
      btn.disabled = false;
      btn.innerHTML = '<span>📨</span><span>發送測試報告</span>';
    }
  }
}

/**
 * 開啟反饋彈窗
 */
function openFeedbackModal(){
  var modal = document.getElementById('modal-user-feedback');
  if(modal){
    modal.style.display = 'flex';
    var inTitle = document.getElementById('feedback-input-title');
    if(inTitle) inTitle.focus();
  }
}

/**
 * 關閉反饋彈窗
 */
function closeFeedbackModal(e){
  if(e && e.target){
    var isCloseBtn = (e.target.closest && e.target.closest('.detail-close-btn')) || (e.target.classList && e.target.classList.contains('detail-close-btn'));
    if(!isCloseBtn && e.target.id !== 'modal-user-feedback') return;
  }
  var modal = document.getElementById('modal-user-feedback');
  if(modal) modal.style.display = 'none';
}

/**
 * 提交反饋或錯誤回報至 Discord
 */
async function submitUserFeedback(){
  var inTitle = document.getElementById('feedback-input-title');
  var inDesc = document.getElementById('feedback-input-desc');
  var inContact = document.getElementById('feedback-input-contact');

  var title = inTitle ? inTitle.value.trim() : '';
  var desc = inDesc ? inDesc.value.trim() : '';
  var contact = inContact ? inContact.value.trim() : '';

  if(!title){
    if(window.tt) tt('請填寫問題主旨或模組名稱', 'er');
    if(inTitle) inTitle.focus();
    return;
  }

  if(!desc){
    if(window.tt) tt('請填寫詳細問題描述或錯誤內容', 'er');
    if(inDesc) inDesc.focus();
    return;
  }

  var btn = document.getElementById('btn-submit-feedback');
  if(btn){
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span><span>正在送出...</span>';
  }

  try {
    if(!window.pywebview || !pywebview.api || !pywebview.api.send_user_feedback){
      if(window.tt) tt('後端 API 尚未就緒', 'er');
      return;
    }

    var res = await pywebview.api.send_user_feedback(title, desc, contact);
    if(res && res.ok){
      if(window.tt) tt('🎉 ' + res.msg, 'ok', 4000);
      closeFeedbackModal();
      if(inTitle) inTitle.value = '';
      if(inDesc) inDesc.value = '';
    } else {
      if(window.tt) tt('提交失敗: ' + ((res && res.msg) || '請稍候再試'), 'er');
    }
  } catch(e){
    if(window.tt) tt('提交反饋發生例外: ' + (e.message || e), 'er');
  } finally {
    if(btn){
      btn.disabled = false;
      btn.innerHTML = '<span>🚀</span><span>送出報告至 Discord</span>';
    }
  }
}
