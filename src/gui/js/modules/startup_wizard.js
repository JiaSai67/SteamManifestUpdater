/* SteamManifestUpdater - Module: modules/startup_wizard.js */
// ═══════════════════════════════════════════════════════
// 軟體啟動必備環境就緒檢查 (左：OpenSteamTools 內核 / 右：Discord 授權憑證)
// 缺少一個都不給進系統 · 500ms 低負載高頻輪詢 · 就緒自動進系統 (不靠按鈕互動)
// ═══════════════════════════════════════════════════════
var _prereqPollTimer = null;
var _hasPassedPrereq = true; // 🌟 樂觀就緒策略：啟動時預設放行首頁與管理庫渲染，Stage 3 背景自檢若發現缺失再無干擾提示
var _hasRedirectedOnStartup = false;

function updateSidebarLockState(isPassed){
  var lockTabs = ['search', 'manage'];
  lockTabs.forEach(function(p){
    var btn = document.querySelector('.sidebar button[data-p="' + p + '"]');
    if(btn){
      if(!isPassed){
        btn.classList.add('locked');
        btn.setAttribute('title', '請先登入獲得憑證');
        btn.setAttribute('data-tooltip', '請先登入獲得憑證');
      } else {
        btn.classList.remove('locked');
        btn.removeAttribute('data-tooltip');
        var titles = { search: '遊戲入庫', manage: '管理入庫' };
        btn.setAttribute('title', titles[p] || '');
      }
    }
  });
}

function startStartupPrereqPolling(){
  if(_hasPassedPrereq) return; // 已通過檢測則直接放行
  if(_prereqPollTimer){
    clearInterval(_prereqPollTimer);
    _prereqPollTimer = null;
  }

  // 進行檢測
  runPrereqCheck(false);

  // 開啟自動低負載輪詢
  _prereqPollTimer = setInterval(function(){
    if(!_hasPassedPrereq){
      runPrereqCheck(false);
    } else {
      stopStartupPrereqPolling();
    }
  }, 800);
}

function stopStartupPrereqPolling(){
  if(_prereqPollTimer){
    clearInterval(_prereqPollTimer);
    _prereqPollTimer = null;
  }
}

async function runPrereqCheck(isManualTrigger){
  if(_isPollingPrereq) return;
  _isPollingPrereq = true;

  try {
    // 關鍵防閃現：若後端 pywebview.api 尚未注入完成，絕不誤判為未安裝/未授權，靜候下一輪輪詢
    if(!window.pywebview || !window.pywebview.api || !pywebview.api.check_dlls || !pywebview.api.get_credentials_status){
      return;
    }

    var dllRes = null;
    var credRes = null;
    try { dllRes = await pywebview.api.check_dlls(); } catch(e){}
    try { credRes = await pywebview.api.get_credentials_status(); } catch(e){}

    if(!dllRes || !credRes) return;

    // 1. 左邊字卡檢查：OpenSteamTools 內核
    var dllOk = !!(dllRes && dllRes.ok === true && dllRes.missing === 0);
    var cardSt = document.getElementById('wizard-card-steamtools');
    var statusSt = document.getElementById('wizard-status-steamtools');
    var btnSt = document.getElementById('btn-wizard-install-steamtools');
    var btnUninstallSt = document.getElementById('btn-wizard-uninstall-steamtools');

    if(cardSt && statusSt && btnSt){
      if(dllOk){
        cardSt.className = 'wizard-column-card is-ok';
        statusSt.className = 'wizard-state-badge is-ok';
        statusSt.textContent = '已安裝';
        btnSt.className = 'btn btn-o';
        btnSt.textContent = '已安裝';
        btnSt.disabled = true;
        btnSt.style.opacity = '0.85';
        btnSt.style.cursor = 'default';
        if(btnUninstallSt) btnUninstallSt.style.display = 'inline-block';
      } else {
        cardSt.className = 'wizard-column-card is-err';
        statusSt.className = 'wizard-state-badge is-err';
        statusSt.textContent = '未安裝';
        btnSt.className = 'btn btn-p';
        btnSt.textContent = '一鍵安裝';
        btnSt.disabled = false;
        btnSt.style.opacity = '1';
        btnSt.style.cursor = 'pointer';
        if(btnUninstallSt) btnUninstallSt.style.display = 'none';
      }
    }

    // 2. 右邊字卡檢查：Discord 授權憑證 (嚴格檢查 Ryuu 與 Lua.tools 雙平台)
    var ryuuAccs = (credRes && credRes.ryuu && credRes.ryuu.accounts) ? credRes.ryuu.accounts : [];
    var ltAccs = (credRes && credRes.lua_tools && credRes.lua_tools.accounts) ? credRes.lua_tools.accounts : [];
    var validRyuuAccs = ryuuAccs.filter(function(a){ return _isAccValid('ryuu', a); });
    var validLtAccs = ltAccs.filter(function(a){ return _isAccValid('lua_tools', a); });
    var totalValidCount = validRyuuAccs.length + validLtAccs.length;
    var totalAccCount = ryuuAccs.length + ltAccs.length;
    var hasExpired = (totalAccCount > 0 && totalValidCount < totalAccCount);

    // 只要有任何平台具備有效帳號可用，即可通行（多源備援機制）
    var credOk = (totalValidCount > 0);

    var cardDc = document.getElementById('wizard-card-discord');
    var statusDc = document.getElementById('wizard-status-discord');
    var btnDc = document.getElementById('btn-wizard-login-discord');
    var btnClearDc = document.getElementById('btn-wizard-clear-discord');

    if(cardDc && statusDc && btnDc){
      if(credOk){
        cardDc.className = 'wizard-column-card is-ok';
        statusDc.className = 'wizard-state-badge is-ok';
        statusDc.textContent = '已授權 (' + totalValidCount + '個有效帳號' + (hasExpired ? '，部分待補' : '') + ')';
        btnDc.className = 'btn btn-o';
        btnDc.textContent = '新增帳號';
        btnDc.onclick = function(){ startDualPlatformSandboxLogin(); };
        if(btnClearDc) btnClearDc.style.display = 'inline-block';
      } else {
        cardDc.className = 'wizard-column-card is-err';
        statusDc.className = 'wizard-state-badge is-err';
        var errLabel = '未授權';
        if(ryuuAccs.length > 0 && validRyuuAccs.length === 0 && ltAccs.length > 0 && validLtAccs.length === 0){
          errLabel = '雙平台憑證均已過期';
        } else if(ryuuAccs.length > 0 && validRyuuAccs.length === 0){
          errLabel = 'Ryuu 憑證待重新登入';
        } else if(ltAccs.length > 0 && validLtAccs.length === 0){
          errLabel = 'Lua.tools 憑證待重新登入';
        } else if(totalAccCount > 0){
          errLabel = '憑證已過期';
        }
        statusDc.textContent = errLabel;
        btnDc.className = 'btn btn-p';
        btnDc.textContent = (totalAccCount > 0) ? '前往重新登入' : '新增帳號';
        btnDc.onclick = function(){
          if(totalAccCount > 0){
            var modal = document.getElementById('modal-startup-wizard');
            if(modal){ modal.classList.add('hidden'); modal.style.display = 'none'; }
            switchPage('credentials');
          } else {
            startDualPlatformSandboxLogin();
          }
        };
        if(btnClearDc) btnClearDc.style.display = (totalAccCount > 0) ? 'inline-block' : 'none';
      }
    }

    // 3. 核心判定：灰化側邊欄與無干擾導航
    var isAllOk = dllOk && credOk;
    var modal = document.getElementById('modal-startup-wizard');
    var pollHint = document.getElementById('wizard-poll-hint');

    if(!isAllOk){
      _hasPassedPrereq = false;
      updateSidebarLockState(false);
      // 只有當使用者在設置頁手動點擊「環境檢測」時才展示彈窗，後台輪詢絕不強行彈窗打擾
      if(isManualTrigger && modal){
        modal.classList.remove('hidden');
        modal.style.display = 'flex';
      }
      if(pollHint){
        var missingMsg = [];
        if(!dllOk) missingMsg.push('OpenSteamTools 未安裝');
        if(!credOk) missingMsg.push('Discord 憑證未授權');
        pollHint.textContent = '檢測到 ' + missingMsg.join('、') + '，缺少一個均無法進入系統。500ms 實時監測中…';
      }
      // 手動觸發檢測且異常時才跳轉
      if(isManualTrigger){
        if(!credOk){
          switchPage('credentials');
        } else if(!dllOk){
          switchPage('settings');
        }
      }
    } else {
      // 兩項均已就緒（完全正常） → 放行進系統與解鎖側邊欄！
      _hasPassedPrereq = true;
      updateSidebarLockState(true);
      stopStartupPrereqPolling();
      // 只有當彈窗當前處於打開可見狀態（例如先前手動檢測打開過）
      // 才顯示已就緒提示並在 400ms 後關閉彈窗
      var isModalOpen = modal && !modal.classList.contains('hidden') && modal.style.display !== 'none';
      if(isModalOpen){
        if(pollHint){
          pollHint.textContent = '🎉 OpenSteamTools 與 Discord 憑證均已就緒，自動進入系統中…';
        }
        setTimeout(function(){
          if(modal){
            modal.classList.add('hidden');
            modal.style.display = 'none';
          }
          if(isManualTrigger){
            tt('✅ 環境檢測合格！', 'ok');
          }
        }, 400);
      } else {
        if(modal){
          modal.classList.add('hidden');
          modal.style.display = 'none';
        }
      }
    }
  } catch(e){
    console.error('runPrereqCheck error:', e);
  } finally {
    _isPollingPrereq = false;
  }
}

// 設置頁或手動調用檢測入口
function checkStartupPrerequisites(isManualClick){
  _hasPassedPrereq = false;
  var modal = document.getElementById('modal-startup-wizard');
  // 只有當使用者在設置頁中手動點擊「環境檢測」按鈕時，才主動展示彈窗供其檢視
  if(isManualClick && modal){
    modal.classList.remove('hidden');
    modal.style.display = 'flex';
  }
  startStartupPrereqPolling();
}

async function wizardInstallSteamTools(){
  var btn = document.getElementById('btn-wizard-install-steamtools');
  var origText = btn ? btn.textContent : '';
  if(btn){
    btn.disabled = true;
    btn.textContent = '⏳ 安裝中...';
  }
  tt('⏳ 正在為您安裝 OpenSteamTools 內核，請稍候...', 'ok');
  try {
    var res = await pywebview.api.inject_kernel();
    if(res && res.ok){
      tt('✅ OpenSteamTools 內核安裝成功！', 'ok');
      await runPrereqCheck(true);
      if(res.msg) tt(res.msg, 'ok');
    } else {
      tt('❌ 安裝失敗：' + ((res && res.msg) || '請檢查 Steam 目錄權限'), 'er');
    }
  } catch(e){
    tt('❌ 安裝過程異常: ' + (e.message || e), 'er');
  } finally {
    if(btn){
      btn.disabled = false;
      btn.textContent = origText;
    }
  }
}

async function wizardUninstallSteamTools(){
  if(!confirm('確定要移除 OpenSteamTools 內核嗎？\n\n系統將清理 Steam 目錄下的 OpenSteamTool.dll 等組件檔案。\n移除後狀態將變為「未安裝」，以便您測試安裝檢查與強制阻擋流程。')) return;
  tt('⏳ 正在移除 OpenSteamTools 內核組件...', 'ok');
  try {
    var res = await pywebview.api.remove_old_tools(false);
    if(res && res.ok){
      tt('✅ OpenSteamTools 已成功移除！', 'ok');
      // 重新開啟阻擋輪詢
      _hasPassedPrereq = false;
      startStartupPrereqPolling();
    } else {
      tt('❌ 移除失敗：' + ((res && res.msg) || '請檢查權限'), 'er');
    }
  } catch(e){
    tt('❌ 移除過程異常: ' + (e.message || e), 'er');
  }
}

async function wizardClearDiscordCredentials(){
  if(!confirm('確定要清除 Discord 授權憑證嗎？\n\n這將清空本地保存的 Ryuu 和 Lua.tools 憑證與 Cookie，狀態將變為「未授權」，以便您測試授權檢查與強制阻擋流程。')) return;
  tt('⏳ 正在清除 Discord 憑證...', 'warn');
  try {
    await Promise.all([
      pywebview.api.clear_credential('ryuu'),
      pywebview.api.clear_credential('lua_tools')
    ]);
    tt('✅ 雙平台憑證已清除！', 'ok');
    loadCredentialsStatus(false);
    // 重新開啟阻擋輪詢
    _hasPassedPrereq = false;
    startStartupPrereqPolling();
  } catch(e){
    tt('❌ 清除憑證失敗: ' + e, 'er');
  }
}

function wizardOpenLoginSelector(){
  startDualPlatformSandboxLogin();
}

function closeStartupWizardModalDirect(){
  var modal = document.getElementById('modal-startup-wizard');
  if(modal){
    modal.classList.add('hidden');
    modal.style.display = 'none';
  }
}

function closeStartupWizardModal(isFinishClick){
  if(_hasPassedPrereq){
    var modal = document.getElementById('modal-startup-wizard');
    if(modal){
      modal.classList.add('hidden');
      modal.style.display = 'none';
    }
  }
}

function onExecuteFastTokenAuthClick(){
  // 進入一鍵登入時已完成 5 秒倒數強制防呆確認，直接執行授權
  executeBatchTokenAuth();
}

async function executeBatchTokenAuth(){
  var selectedCount = _selectedFastIndices.size;
  if(selectedCount === 0){
    tt('請至少勾選一個欲授權的 Discord 帳號！', 'warn');
    return;
  }

  var chkRyuu = document.getElementById('ft-chk-ryuu');
  var chkLt = document.getElementById('ft-chk-luatools');
  var platforms = [];
  if(chkRyuu && chkRyuu.checked) platforms.push('ryuu');
  if(chkLt && chkLt.checked) platforms.push('lua_tools');

  if(platforms.length === 0){
    tt('請至少勾選一個目標授權平台 (Ryuu 或 Lua.tools)！', 'warn');
    return;
  }

  var accountsToAuth = [];
  _selectedFastIndices.forEach(function(idx){
    if(_scannedFastAccounts[idx]){
      accountsToAuth.push(_scannedFastAccounts[idx]);
    }
  });

  var execBtn = document.getElementById('btn-execute-fast-token');
  var logBox = document.getElementById('fast-token-logs');
  if(execBtn){
    execBtn.disabled = true;
    execBtn.textContent = '⏳ 正在快速授權中 (' + selectedCount + ' 個帳號)…';
  }

  if(logBox){
    logBox.style.display = 'block';
    logBox.innerHTML = '<div style="color:#7BD2FF">⚡ 正在為 ' + selectedCount + ' 個勾選帳號執行 ' + platforms.join(' + ').toUpperCase() + ' 授權…</div>';
  }

  try {
    var res = await pywebview.api.batch_import_discord_tokens(accountsToAuth, platforms);
    if(res && res.ok){
      tt(res.msg || '批次授權完成！', 'ok');
      if(logBox && res.logs){
        var logHtml = '<div style="color:#2EAF6B;font-weight:700">🎉 ' + h(res.msg) + '</div>';
        for(var k = 0; k < res.logs.length; k++){
          logHtml += '<div>• ' + h(res.logs[k]) + '</div>';
        }
        logBox.innerHTML = logHtml;
      }
      setTimeout(function(){
        closeFastTokenAuthModal();
        loadCredentialsStatus(false);
      }, 1600);
    } else {
      tt((res && res.msg) || '授權失敗', 'err');
      if(logBox){
        logBox.innerHTML += '<div style="color:#FF7B7B">❌ 錯誤: ' + h((res && res.msg) || '未知錯誤') + '</div>';
      }
      if(execBtn){
        execBtn.disabled = false;
        execBtn.textContent = '⚡ 重試授權 (' + selectedCount + ')';
      }
    }
  } catch(e){
    tt('授權執行異常: ' + e, 'err');
    if(logBox){
      logBox.innerHTML += '<div style="color:#FF7B7B">❌ 異常: ' + h(String(e)) + '</div>';
    }
    if(execBtn){
      execBtn.disabled = false;
      execBtn.textContent = '⚡ 重試授權 (' + selectedCount + ')';
    }
  }
}

function openDiscordScannerModal(platform){
  startDualPlatformSandboxLogin();
}

function closeDiscordScannerModal(){
  var m = document.getElementById('modal-discord-scanner');
  if(m) m.classList.add('hidden');
}


function openImportCookieModal(platform){
  _curCookiePlatform = platform;
  var modal = document.getElementById('modal-cred-cookie');
  var title = document.getElementById('cookie-modal-title');
  var ta = document.getElementById('cookie-input-area');
  ta.value = '';
  if(platform === 'ryuu'){
    title.textContent = '📋 匯入 Ryuu 平台憑證';
    ta.placeholder = '請貼上 generator.ryuu.lol 的 Cookie（包含 session=...）或直接貼上 session 內容…';
  } else {
    title.textContent = '🔑 匯入 Lua.tools 授權憑證';
    ta.placeholder = '請貼上 lua.tools 的 Token、Cookies 或授權字串…';
  }
  if(modal) modal.classList.remove('hidden');
}

function closeCookieModal(){
  var modal = document.getElementById('modal-cred-cookie');
  if(modal) modal.classList.add('hidden');
}

async function submitCookie(){
  var ta = document.getElementById('cookie-input-area');
  var text = (ta.value || '').trim();
  if(!text){
    tt('請輸入憑證內容', 'err');
    return;
  }
  try {
    var res = await pywebview.api.save_credential_cookie(_curCookiePlatform, text);
    if(res && res.ok){
      tt(res.msg || '憑證儲存成功！', 'ok');
      closeCookieModal();
      loadCredentialsStatus(false);
    } else {
      tt(res.msg || '儲存失敗', 'err');
    }
  } catch(e){
    tt('儲存失敗: ' + e, 'err');
  }
}

async function clearCred(platform){
  if(!confirm('確定要清除 ' + platform.toUpperCase() + ' 的本機已存憑證與 Cookie 嗎？')) return;
  try {
    var res = await pywebview.api.clear_credential(platform);
    if(res && res.ok){
      tt(res.msg || '已清除憑證', 'ok');
      loadCredentialsStatus(false);
    } else {
      tt(res.msg || '清除失敗', 'err');
    }
  } catch(e){
    tt('清除異常: ' + e, 'err');
  }
}

async function onPrefSourceChange(val){
  try {
    await pywebview.api.set_preferred_source(val);
    tt('已儲存偏好下載源: ' + val, 'ok');
  } catch(e){}
}

async function onAutoRotateChange(val){
  try {
    await pywebview.api.set_auto_rotate(val);
    tt(val ? '已開啟多帳號自動輪換' : '已關閉多帳號自動輪換', 'ok');
  } catch(e){}
}

async function detailAction(){
  if(!_curDetailAppid) return;
  var targetAid = String(_curDetailAppid).trim();
  var targetName = _curDetailName;
  var hasUpdate = !!_curDetailHasUpdate;
  var isInstalled = _installedAppids && _installedAppids.has(targetAid);
  
  closeGameDetail();
  
  if(!isInstalled){
    ag(targetAid, targetName);
  } else if(hasUpdate){
    autoUpdateSingle(targetAid, targetName);
  } else {
    tt('當前已是最新版本，無需更新', 'info');
  }
}

async function s(){
  var q = document.getElementById('q').value.trim();
  if(!q){ switchBrowse(); return; }  // 空搜尋 → 回到自動載入的全部遊戲
  _enterSearchMode();
  var list = document.getElementById('results');
  var btn = document.getElementById('btn-q');
  btn.disabled = true; btn.textContent = '搜尋中…';
  list.innerHTML = _skelSearch;
  try {
    var results = await pywebview.api.search(q);
    if(!results || !results.length){
      list.innerHTML = '<div class="empty"><div class="icon">🔍</div><p>查無符合遊戲，可嘗試輸入英文或 AppID 搜尋</p></div>';
    } else {
      list.innerHTML = results.map(function(r,i){
        var isIns = _installedAppids.has(String(r.appid));
        var aidStr = String(r.appid);
        var hasUp = false;
        if(isIns){
          var foundInPre = false;
          if(_pre._games && _pre._games.length){
            for(var gi=0; gi<_pre._games.length; gi++){
              if(String(_pre._games[gi].appid) === aidStr){
                hasUp = !!_pre._games[gi].has_update;
                foundInPre = true;
                break;
              }
            }
          }
          if(!foundInPre && _knownUpdates && _knownUpdates[aidStr]){
            hasUp = !!_knownUpdates[aidStr].has_update;
          }
        }
        
        // 操作區初態：若未入庫先以旋轉圓圈讀取中呈現，若已入庫直接顯示狀態
        var btnHtml = '';
        if(isIns){
          if(hasUp){
            btnHtml = '<button class="btn btn-s" style="background:linear-gradient(135deg,#FF9800,#F57C00);color:#fff;border:none;cursor:pointer;font-weight:bold" onclick="event.stopPropagation(); autoUpdateSingle(\''+r.appid+'\',\''+jsesc(r.name)+'\')">⚡ 更新 Manifest</button>';
          } else {
            btnHtml = '<button class="btn btn-o btn-s" style="color:var(--succ);border-color:var(--succ);cursor:default" onclick="event.stopPropagation()">✅ 已在本地</button>';
          }
        } else {
          btnHtml = '<div class="search-loading-spinner" title="正在查詢 Manifest 與補丁庫狀態..."></div>';
        }

        var hasOf = _onlinefixAppids && _onlinefixAppids.has(aidStr);
        var isDeployed = _deployedAppids && _deployedAppids.has(aidStr);
        var cardClass = 'card' + (hasUp ? ' needs-update' : '') + (hasOf ? ' has-onlinefix' : '');
        
        var tagsHtml = '';
        if(hasOf) tagsHtml += '<span class="corner-tag tag-of" title="支援 Online-Fix 聯機補丁">🎮 聯機</span>';
        if(isDeployed) tagsHtml += '<span class="corner-tag tag-dep" title="本地已成功部署補丁">✅ 部署</span>';
        if(hasUp) tagsHtml += '<span class="corner-tag tag-up" title="可更新 Manifest">⚡ 可更新</span>';
        var cornerTagsDiv = tagsHtml ? '<div class="card-corner-tags">' + tagsHtml + '</div>' : '';

        var progressHtml = '<div class="card-progress-wrap" id="cpw-'+r.appid+'">' +
                             '<div class="card-progress-header">' +
                                '<span class="cp-action" id="cpa-'+r.appid+'">🔍 準備檢查資料...</span>' +
                                '<span class="cp-percent" id="cpp-'+r.appid+'">0%</span>' +
                             '</div>' +
                             '<div class="card-progress-track">' +
                                '<div class="card-progress-bar" id="cpb-'+r.appid+'"></div>' +
                             '</div>' +
                           '</div>';

        return '<div class="'+cardClass+'" style="--i:'+i+'" data-appid="'+r.appid+'" id="scard-'+r.appid+'" onclick="openGameDetail(\''+r.appid+'\',\''+jsesc(r.name)+'\',\''+jsesc(r.image||'')+'\')">' +
                 cornerTagsDiv +
                 '<img src="'+h(r.image||'')+'" loading="lazy" onerror="imgFb(this,'+r.appid+')">' +
                 '<div class="info">' +
                   '<div class="name" title="'+h(r.name)+'">'+h(r.name)+'</div>' +
                   '<div class="search-tags-row">' +
                     '<span class="aid">'+r.appid+'</span>' +
                     '<span class="search-tag tag-ver" id="stag-ver-'+r.appid+'" style="display:none"></span>' +
                     '<span class="search-tag tag-of" id="stag-of-'+r.appid+'" style="'+(hasOf ? 'display:inline-flex' : 'display:none')+'">✅ 聯機補丁</span>' +
                   '</div>' +
                   '<div class="link-wrap">' +
                     '<span class="link link-steam" onclick="event.stopPropagation(); openSteam('+r.appid+')">在 Steam 商店查看 ▶</span>' +
                   '</div>' +
                 '</div>' +
                 progressHtml +
                 '<div class="search-action-wrap" id="sact-'+r.appid+'">' +
                   btnHtml +
                 '</div>' +
               '</div>';
      }).join('');
      fixImgs(list);

      // 🌟 非同步平行查詢每張小卡的 Manifest 版本日期與雲端補丁庫狀態 (非阻塞秒開)
      results.forEach(function(item){
        var aid = String(item.appid);
        var nm = item.name || '';
        pywebview.api.get_search_item_status(aid, nm).then(function(stat){
          if(!stat) return;
          var cardEl = document.getElementById('scard-' + aid);
          var actWrap = document.getElementById('sact-' + aid);
          var verTag = document.getElementById('stag-ver-' + aid);
          var ofTag = document.getElementById('stag-of-' + aid);

          // 1. 版本日期標籤 (跟隨 Ryuu 的 Manifest ID 與 SteamDB 日期)
          if(verTag){
            if(stat.version_date){
              verTag.textContent = '📅 版本：' + stat.version_date;
              verTag.style.display = 'inline-flex';
            } else if(!stat.has_manifest){
              verTag.textContent = '無可用清單';
              verTag.className = 'search-tag tag-none';
              verTag.style.display = 'inline-flex';
            }
          }

          // 2. 聯機補丁標籤 (根據 Google Drive 網盤補丁庫掃描結果)
          if(ofTag){
            if(stat.has_onlinefix){
              ofTag.style.display = 'inline-flex';
              _onlinefixAppids.add(aid);
              if(cardEl){
                cardEl.classList.add('has-onlinefix');
                var cTags = cardEl.querySelector('.card-corner-tags');
                if(!cTags){
                  cTags = document.createElement('div');
                  cTags.className = 'card-corner-tags';
                  cardEl.insertBefore(cTags, cardEl.firstChild);
                }
                if(!cTags.querySelector('.tag-of')){
                  var sp = document.createElement('span');
                  sp.className = 'corner-tag tag-of';
                  sp.title = '支援 Online-Fix 聯機補丁';
                  sp.textContent = '🎮 聯機';
                  cTags.appendChild(sp);
                }
              }
            } else if(!_onlinefixAppids.has(aid)){
              ofTag.style.display = 'none';
            }
          }

          // 3. 操作按鈕更新 (旋轉中 → 一鍵入庫 / 不支援)
          if(actWrap && !stat.is_installed){
            if(stat.has_manifest){
              actWrap.innerHTML = '<button class="btn btn-p btn-s" onclick="event.stopPropagation(); ag(\''+aid+'\',\''+jsesc(nm)+'\')">一鍵入庫</button>';
            } else {
              actWrap.innerHTML = '<button class="btn btn-s btn-unsupported" disabled title="第三方雲端倉庫目前暫未收錄此遊戲清單">不支援</button>';
            }
          }
        }).catch(function(err){
          console.error('[search status update] error for aid ' + aid, err);
          if(actWrap && !isIns){
            actWrap.innerHTML = '<button class="btn btn-p btn-s" onclick="event.stopPropagation(); ag(\''+aid+'\',\''+jsesc(nm)+'\')">一鍵入庫</button>';
          }
        });
      });
    }
  } catch(e) {
    list.innerHTML = '<div class="empty"><div class="icon">❌</div><p>搜尋失敗: '+(e.message||e.toString())+'</p></div>';
    tt('搜尋失敗', 'er');
  }
  btn.disabled = false; btn.textContent = '搜尋';
}

