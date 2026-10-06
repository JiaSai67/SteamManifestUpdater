/* SteamManifestUpdater - Module: modules/game_detail.js */
// ═══════════════════════════════════════════════════════
// 遊戲詳細資料彈窗 (Depot 子分類 + SteamDB 真實日期 + 現代流光動效)
// ═══════════════════════════════════════════════════════
var _curDetailAppid = '';
var _curDetailName = '';
var _curDetailHasUpdate = false;
var _curDetailData = null;
var _curDepotsData = [];
var _curSelectedDepotIdx = 0;
var _detailReqCounter = 0; // 異步請求計數器，徹底杜絕快速切換時舊請求回調覆蓋新遊戲欄位的競態問題

function renderDepotHistory(idx){
  _curSelectedDepotIdx = idx;
  var listEl = document.getElementById('dt-manifest-list');
  var tabsEl = document.getElementById('dt-depot-tabs');
  if(!listEl || !_curDepotsData || !_curDepotsData.length) return;

  // 更新 Tab 高亮與滾動視圖
  if(tabsEl){
    var btns = tabsEl.querySelectorAll('.dt-depot-btn');
    btns.forEach(function(b, i){
      if(i === idx){
        b.classList.add('active');
        if(b.scrollIntoView){
          b.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
        }
      } else {
        b.classList.remove('active');
      }
    });
  }

  var curDepot = _curDepotsData[idx] || _curDepotsData[0];
  var hist = curDepot.history || [];
  if(!hist.length){
    listEl.innerHTML = '<div class="empty" style="padding:20px 0"><p>該 Depot 暫無版本歷史記錄</p></div>';
    return;
  }

  var html = '';
  // 若該 Depot 已被官方棄置，在頂部顯示架構提示
  if(curDepot.is_deprecated){
    var repText = curDepot.replaced_by ? ('（已由新主程式 Depot <b>' + escHtml(curDepot.replaced_by) + '</b> 接替）') : '';
    if(_curDetailHasUpdate && _curDetailData && _curDetailData.needs_topology_migration){
      html += '<div style="margin-bottom:10px;padding:8px 12px;background:rgba(239,83,80,0.12);border:1px solid rgba(239,83,80,0.3);border-radius:8px;font-size:11.5px;color:#d32f2f;display:flex;align-items:center;gap:6px">' +
                '<span>⚠️</span> <span>官方已棄置此 Depot' + repText + '。建議立即執行版本更新以遷移至新架構！</span>' +
              '</div>';
    } else {
      html += '<div style="margin-bottom:10px;padding:8px 12px;background:rgba(76,175,80,0.12);border:1px solid rgba(76,175,80,0.3);border-radius:8px;font-size:11.5px;color:#2e7d32;display:flex;align-items:center;gap:6px">' +
                '<span>✅</span> <span>官方已棄置此舊 Depot' + repText + '。新主程式已就緒，此舊 Depot 已自動忽略比對，無須任何操作。</span>' +
              '</div>';
    }
  }
  hist.forEach(function(item, hIdx){
    var isCur = !!item.is_current;
    var isPen = !!item.is_pending;
    var isOff = !!item.is_official;
    var cls = 'dt-item';
    var itemDate = item.date || item.date_str || '';
    if(!itemDate && item.meta){
      var dm = item.meta.match(/\d{2,4}-\d{2}-\d{2}/);
      if(dm) itemDate = dm[0];
    }
    var rawMeta = item.meta || itemDate || 'SteamDB 官方版本';
    // 🌟 徹底清除 (yesterday) / (today) 等相對時間字符
    var cleanMeta = rawMeta.replace(/\s*\([^)]*(?:yesterday|today|days? ago|weeks? ago|months? ago)[^)]*\)/gi, '').trim();

    var tagHtml = '';
    if(isPen){
      // 黃色標註：可更新的官方最新/雲端版本
      cls += ' dt-pending';
      tagHtml = '<span class="dt-tag dt-tag-yellow">' + escHtml(item.tag || '⚡ 可更新 (SteamCMD)') + '</span>';
    } else if(isCur){
      // 藍色標註：當前本地儲存的 manifest 版本
      cls += ' dt-current';
      tagHtml = '<span class="dt-tag dt-tag-blue">' + escHtml(item.tag || '💾 本地當前 (SteamCMD)') + '</span>';
    } else if(isOff){
      tagHtml = '<span class="dt-tag" style="background:rgba(0,0,0,0.05);color:var(--text);border:1px solid rgba(0,0,0,0.1)">' + escHtml(item.tag || 'SteamDB 最新') + '</span>';
    } else {
      tagHtml = '<span class="dt-tag" style="background:rgba(0,0,0,0.06);color:var(--gray)">' + escHtml(item.tag || ('#' + (hIdx + 1) + ' (SteamDB)')) + '</span>';
    }

    var tip = 'Manifest GID: ' + (item.manifest_id || '') + (cleanMeta ? '\n資訊: ' + cleanMeta : '') + '\n(點擊複製 Manifest ID)';
    var dateBadge = itemDate ? '<span class="dt-gid-date">📅 ' + escHtml(itemDate) + '</span>' : '';

    html += '<div class="' + cls + '" onclick="copyManifestId(\'' + item.manifest_id + '\')" title="' + escHtml(tip) + '">' +
              '<div class="dt-item-left">' +
                '<div class="dt-gid" style="display:flex;align-items:center;flex-wrap:wrap;gap:2px">' +
                  '<span>' + escHtml(item.manifest_id || '未知 GID') + '</span>' +
                  dateBadge +
                '</div>' +
              '</div>' +
              tagHtml +
            '</div>';
  });

  // 提供前往 SteamDB 查看該 Depot 完整鏈的按鈕
  var did = curDepot.depot_id || '';
  if(did){
    html += '<div style="margin-top:10px;text-align:center;padding:4px 0">' +
              '<button class="btn btn-o btn-s" style="font-size:11px;padding:5px 14px;border-radius:99px" onclick="openSteamDBDepot(\'' + did + '\')">' +
                '🌐 在 SteamDB 查閱 Depot ' + escHtml(did) + ' 完整 Manifest 鏈 ↗' +
              '</button>' +
            '</div>';
  }

  listEl.innerHTML = html;
}

// 支援 Depot/DLC 分類導航欄滑鼠滾輪左右橫向滾動
document.addEventListener('wheel', function(e){
  var tabs = e.target.closest('#dt-depot-tabs');
  if(tabs){
    if(tabs.scrollWidth > tabs.clientWidth){
      if(e.deltaY !== 0){
        e.preventDefault();
        tabs.scrollLeft += e.deltaY;
      }
    }
  }
}, { passive: false });

function openExternalUrl(url){
  if(!url) return;
  if(window.pywebview && window.pywebview.api && window.pywebview.api.open_url){
    window.pywebview.api.open_url(url);
  } else {
    window.open(url, '_blank');
  }
}

function openSteamDB(aid){
  if(!aid) return;
  var url = 'https://steamdb.info/app/' + encodeURIComponent(aid) + '/';
  if(window.pywebview && window.pywebview.api && window.pywebview.api.open_url){
    window.pywebview.api.open_url(url);
  } else {
    window.open(url, '_blank');
  }
}

function openSteamDBDepot(did){
  if(!did) return;
  var url = 'https://steamdb.info/depot/' + encodeURIComponent(did) + '/manifests/';
  if(window.pywebview && window.pywebview.api && window.pywebview.api.open_url){
    window.pywebview.api.open_url(url);
  } else {
    window.open(url, '_blank');
  }
}

var _verifyStepTimer = null;
var _verifyCurrentPercent = 0;
var _verifyTargetPercent = 0;
var _detailActiveTimers = [];

function _clearAllDetailTimers(){
  if(typeof _verifyStepTimer !== 'undefined' && _verifyStepTimer){
    clearInterval(_verifyStepTimer);
    _verifyStepTimer = null;
  }
  if(_detailActiveTimers && _detailActiveTimers.length){
    for(var i = 0; i < _detailActiveTimers.length; i++){
      clearTimeout(_detailActiveTimers[i]);
    }
    _detailActiveTimers = [];
  }
}

// 🌟 核心防禦：絕對純淨的 0% 硬重置機制 (徹底切斷 CSS Transition 避免回滾動畫)
function _resetDetailVerifyOverlay(){
  _clearAllDetailTimers();
  _verifyCurrentPercent = 0;
  _verifyTargetPercent = 0;

  var barEl = document.getElementById('dt-verify-ring-bar');
  if(barEl){
    // 關鍵：先拔除 CSS transition，將圓環瞬間硬重設為 0% (offset 314.16)
    // 徹底阻斷 CSS 補間動畫將重置動作誤渲染為「從 50%/100% 倒退回滾」的視覺瑕疵！
    barEl.classList.add('no-transition');
    barEl.style.transition = 'none';
    barEl.style.strokeDashoffset = '314.16';
    void barEl.offsetWidth; // 強制渲染引擎瞬間結算無過渡的 0% 狀態
    barEl.style.transition = '';
    barEl.classList.remove('no-transition');
  }

  var numEl = document.getElementById('dt-verify-percent-num');
  if(numEl) numEl.textContent = '0';

  var titleEl = document.getElementById('dt-verify-task-title');
  var descEl = document.getElementById('dt-verify-task-desc');
  if(titleEl) titleEl.textContent = '檢測 SteamCMD 官方協議與 Public 分支...';
  if(descEl) descEl.textContent = '連接 Valve PICS 伺服器，核驗最新 Manifest GID';

  var initDots = document.querySelectorAll('.detail-verify-step-dot');
  initDots.forEach(function(dot, i){
    dot.className = (i === 0) ? 'detail-verify-step-dot active' : 'detail-verify-step-dot';
  });
}

function _registerDetailTimer(fn, delay){
  var timer = setTimeout(function(){
    var idx = _detailActiveTimers.indexOf(timer);
    if(idx !== -1) _detailActiveTimers.splice(idx, 1);
    fn();
  }, delay);
  _detailActiveTimers.push(timer);
  return timer;
}

// 🌟 接收後端 Python (web_api.py) 透過 evaluate_js 推播的即時驗證進度
window.onDetailStepProgress = function(appid, pct, title, desc, step){
  if(String(appid).trim() !== _curDetailAppid) return;
  setDetailVerifyProgress(pct, title, desc, step);
};

function setDetailVerifyProgress(targetPct, title, desc, stepIdx){
  // 🌟 單調遞增守衛：進度永遠只能平滑向前遞增，嚴禁任何向後回滾
  var safeTarget = Math.min(100, Math.max(0, targetPct));
  if(safeTarget > _verifyTargetPercent){
    _verifyTargetPercent = safeTarget;
  }
  
  var titleEl = document.getElementById('dt-verify-task-title');
  var descEl = document.getElementById('dt-verify-task-desc');
  if(titleEl && title) titleEl.textContent = title;
  if(descEl && desc) descEl.textContent = desc;

  if(stepIdx !== undefined && stepIdx !== null){
    var dots = document.querySelectorAll('.detail-verify-step-dot');
    dots.forEach(function(dot, i){
      var idx = i + 1;
      if(idx < stepIdx){
        dot.className = 'detail-verify-step-dot done';
      } else if(idx === stepIdx){
        dot.className = 'detail-verify-step-dot active';
      } else {
        dot.className = 'detail-verify-step-dot';
      }
    });
  }

  if(!_verifyStepTimer){
    _verifyStepTimer = setInterval(function(){
      if(_verifyCurrentPercent < _verifyTargetPercent){
        var diff = _verifyTargetPercent - _verifyCurrentPercent;
        var step = Math.max(0.8, diff * 0.18);
        _verifyCurrentPercent = Math.min(_verifyTargetPercent, _verifyCurrentPercent + step);
      }

      var rounded = Math.round(_verifyCurrentPercent);
      var numEl = document.getElementById('dt-verify-percent-num');
      if(numEl) numEl.textContent = rounded;

      var barEl = document.getElementById('dt-verify-ring-bar');
      if(barEl){
        var circumference = 314.16; // 2 * Math.PI * 50
        var offset = circumference - (circumference * (_verifyCurrentPercent / 100));
        barEl.style.strokeDashoffset = offset;
      }

      if(_verifyCurrentPercent >= _verifyTargetPercent){
        if(_verifyTargetPercent >= 100){
          clearInterval(_verifyStepTimer);
          _verifyStepTimer = null;
        }
      }
    }, 16);
  }
}

var _isPreloadingDetail = false;

async function openGameDetail(appid, name, image){
  var targetAppid = String(appid).trim();
  var modal = document.getElementById('game-detail-modal');
  var verifyOverlay = document.getElementById('detail-verify-overlay');
  
  // 🛡️ 防重複點擊守衛：若同一個遊戲小卡已經處於開啟狀態，避免二次點擊造成重置與競態
  if(_curDetailAppid === targetAppid && modal && modal.classList.contains('active')){
    return;
  }

  // 🧹 啟動新小卡前，徹底硬重置所有定時器與遮罩狀態至純淨 0%
  _resetDetailVerifyOverlay();

  var myReqId = ++_detailReqCounter;
  _curDetailAppid = targetAppid;
  _curDetailName = name || ('App_' + targetAppid);
  _curDepotsData = [];
  _curSelectedDepotIdx = 0;
  _curDetailHasUpdate = false;
  if(!modal) return;

  // 🌟 1. 遊戲小卡秒開：立即設定左側基礎資訊 (0ms 零延遲呈現封面、名稱與 AppID)
  var nameEl = document.getElementById('dt-name');
  if(nameEl) nameEl.textContent = _curDetailName;
  var aidEl = document.getElementById('dt-aid');
  if(aidEl) aidEl.textContent = targetAppid;
  var imgEl = document.getElementById('dt-img');
  if(imgEl) imgEl.src = image || ('https://cdn.cloudflare.steamstatic.com/steam/apps/' + targetAppid + '/header.jpg');
  
  var isInstalled = _installedAppids && _installedAppids.has(targetAppid);
  var actBtn = document.getElementById('dt-btn-action');
  if(actBtn){
    if(!isInstalled){
      actBtn.textContent = '🚀 一鍵入庫此遊戲';
      actBtn.className = 'btn btn-p btn-s';
      actBtn.style.display = 'inline-flex';
      actBtn.onclick = function(){ closeGameDetail(); Downloader.installGame(targetAppid, _curDetailName); };
    } else {
      actBtn.style.display = 'none';
      actBtn.onclick = null;
    }
  }

  // 狀態檢查重置為「檢測中」
  var rStatus = document.getElementById('dt-ryuu-status'), rGid = document.getElementById('dt-ryuu-gid');
  var gStatus = document.getElementById('dt-gdrive-status'), gVal = document.getElementById('dt-gdrive-val');
  var ofStatus = document.getElementById('dt-of-status'), ofVal = document.getElementById('dt-of-val');
  var zgStatus = document.getElementById('dt-zg-status'), zgVal = document.getElementById('dt-zg-val');
  if(rStatus){ rStatus.className = 'chip gray'; rStatus.textContent = '檢測中'; }
  if(rGid){ rGid.innerHTML = '<span style="color:var(--gray)">查詢中…</span>'; }
  if(gStatus){ gStatus.className = 'chip gray'; gStatus.textContent = '檢測中'; }
  if(gVal){ gVal.innerHTML = '<span style="color:var(--gray)">查詢中…</span>'; }
  if(ofStatus){ ofStatus.className = 'chip gray'; ofStatus.textContent = '檢測中'; }
  if(ofVal){ ofVal.innerHTML = '<span style="color:var(--gray)">查詢中…</span>'; }
  if(zgStatus){ zgStatus.className = 'chip gray'; zgStatus.textContent = '檢測中'; }
  if(zgVal){ zgVal.innerHTML = '<span style="color:var(--gray)">查詢中…</span>'; }

  // 清空 Tabs，右側清單顯示極速流光骨架屏
  var tabsEl = document.getElementById('dt-depot-tabs');
  if(tabsEl) tabsEl.innerHTML = '';
  var listEl = document.getElementById('dt-manifest-list');
  if(listEl){
    listEl.innerHTML = '<div class="dt-loading-skeleton" style="padding:32px 0;display:flex;flex-direction:column;align-items:center;gap:10px;color:var(--gray);font-size:12px">' +
      '<div class="dt-sdb-spinner" style="width:20px;height:20px;border-width:2px;border-top-color:#F59E0B"></div>' +
      '<div>正在連線獲取版本數據…</div>' +
    '</div>';
  }

  // 先預設隱藏 SteamDB 背景載入提示橫幅
  var sdbLoadingBanner = document.getElementById('dt-steamdb-loading');
  if(sdbLoadingBanner){
    sdbLoadingBanner.style.display = 'none';
    sdbLoadingBanner.style.opacity = '1';
    sdbLoadingBanner.style.transform = 'none';
  }

  // 🚀 遊戲小卡秒開！立即開啟彈窗，絕不拖泥帶水！
  if(verifyOverlay) verifyOverlay.classList.add('hidden-overlay');
  modal.classList.add('active');

  // 🌟 2. 背景非同步呼叫後端 API 獲取 Depot 分組歷史與 4 域狀態檢查
  try {
    var data = await pywebview.api.get_manifest_history(targetAppid);
    _curDetailData = data;
    
    // 🛡️ 核心競態守衛：如果使用者在此期間切換了其他遊戲或關閉視窗，直接丟棄過期結果！
    if(myReqId !== _detailReqCounter || _curDetailAppid !== targetAppid){
      return;
    }

    // 🌟 控制 SteamDB Cloudflare 背景載入橫幅 (黃字 + 動畫)
    if(sdbLoadingBanner){
      if(data && data.is_steamdb_loading){
        sdbLoadingBanner.style.display = 'flex';
      } else {
        sdbLoadingBanner.style.display = 'none';
      }
    }

    // 3. 檢查 SteamDB 是否逾時或連線異常
    if(data && (data.steamdb_timeout || data.steamdb_error)){
      var tipMsg = data.steamdb_error ? ('⚠️ SteamDB 連線異常 (' + data.steamdb_error + ')，已載入本地最新資料') : '⚠️ SteamDB 資料連線逾時，已載入本地最新版本資料';
      if(window.tt) tt(tipMsg, 'wn', 5000);
    }

    // 更新遊戲名稱 (若有最新繁體名稱)
    if(nameEl && data && data.name) nameEl.textContent = data.name;

    if(!data || !data.depots || !data.depots.length){
      if(listEl) listEl.innerHTML = '<div class="empty" style="padding:20px 0"><p>暫無可用版本歷史記錄</p></div>';
      return;
    }

    _curDetailHasUpdate = !!data.has_update;
    var sourceName = data.best_source_name || '線上源';
    
    // 🌟 若詳細彈窗取得更新狀態，僅平滑記錄快取，絕不觸發全頁破壞性重繪
    if(!_knownUpdates) _knownUpdates = {};
    _knownUpdates[targetAppid] = { appid: targetAppid, has_update: _curDetailHasUpdate, version_status: _curDetailHasUpdate ? '舊 1 版' : '最新版' };
    
    // 依更新狀態決定一鍵按鈕 (統一接入 Downloader 調度中心)
    if(actBtn){
      if(!isInstalled){
        actBtn.textContent = '🚀 一鍵入庫此遊戲';
        actBtn.className = 'btn btn-p btn-s';
        actBtn.style.display = 'inline-flex';
        actBtn.onclick = function(){ closeGameDetail(); Downloader.installGame(targetAppid, _curDetailName); };
      } else if(_curDetailHasUpdate){
        if(data.needs_topology_migration){
          var repBtnText = data.replaced_by ? (' (Depot ' + data.replaced_by + ')') : '';
          actBtn.textContent = '⚡ 立即遷移至新架構' + repBtnText;
        } else {
          actBtn.textContent = '⚡ 立即更新至官方最新版';
        }
        actBtn.className = 'btn btn-p btn-s';
        actBtn.style.display = 'inline-flex';
        actBtn.onclick = function(){ closeGameDetail(); Downloader.updateGame(targetAppid, _curDetailName); };
      } else {
        // 本地已是最新版或雲端未收錄：隱藏更新按鈕
        actBtn.style.display = 'none';
        actBtn.onclick = null;
      }
    }

    _curDepotsData = data.depots;

    // 🌟 狀態檢查 4 域渲染 (a. Ryuu, b. Google Drive, c. Online-Fix, d. ZeiGames)
    var sc = data.status_check || data.dual_sources || {};
    var ryuu = sc.ryuu || {};
    var gdrive = sc.gdrive || {};
    var of_info = sc.onlinefix || {};
    var zg_info = sc.zeigames || {};

    // a. Ryuu 平台
    if(rStatus && rGid){
      if(ryuu.available && ryuu.manifest_id && ryuu.manifest_id !== '無檔案 (未收錄)'){
        if(ryuu.is_outdated && ryuu.is_same_as_local){
          rStatus.className = 'chip warn';
          rStatus.textContent = '已收錄 (同本地舊版)';
          rGid.innerHTML = '<span style="color:#E65100;font-weight:bold" title="Manifest GID: ' + escHtml(String(ryuu.manifest_id)) + '">' + escHtml(String(ryuu.manifest_id)) + '</span>';
        } else if(ryuu.is_outdated){
          rStatus.className = 'chip warn';
          rStatus.textContent = '可更新 (線上舊版)';
          rGid.innerHTML = '<span style="color:#E65100;font-weight:bold" title="Manifest GID: ' + escHtml(String(ryuu.manifest_id)) + '">' + escHtml(String(ryuu.manifest_id)) + '</span>';
        } else {
          rStatus.className = 'chip ok';
          rStatus.textContent = ryuu.is_same_as_local ? '已收錄 (同官方最新)' : '已收錄 (官方最新)';
          rGid.innerHTML = '<span style="color:#2E7D32;font-weight:bold" title="Manifest GID: ' + escHtml(String(ryuu.manifest_id)) + '">' + escHtml(String(ryuu.manifest_id)) + '</span>';
        }
      } else {
        rStatus.className = 'chip gray';
        rStatus.textContent = '未收錄';
        rGid.innerHTML = '<span style="color:var(--gray)">無檔案 (未收錄)</span>';
      }
    }

    // b. Google Drive (網盤補丁庫)
    if(gStatus && gVal){
      if(gdrive.available){
        gStatus.className = 'chip ok';
        gStatus.textContent = '已收錄';
        var gDetails = escHtml(gdrive.details || '含專用/聯機補丁');
        if(gdrive.is_deployed){
          gVal.innerHTML = '<span style="color:#2E7D32;font-weight:700" title="' + gDetails + '">已部署</span> <button type="button" class="dt-patch-btn dt-patch-btn-remove" onclick="removeOnlinePatch(\'' + jsesc(targetAppid) + '\',\'' + jsesc(_curDetailName) + '\')">🗑️ 移除補丁</button>';
        } else {
          gVal.innerHTML = '<span style="color:#D32F2F;font-weight:700" title="' + gDetails + '">未部署</span> <button type="button" class="dt-patch-btn dt-patch-btn-deploy" onclick="manualDeployPatch(\'' + jsesc(targetAppid) + '\',\'' + jsesc(_curDetailName) + '\')">🚀 立即部署</button>';
        }
      } else {
        gStatus.className = 'chip gray';
        gStatus.textContent = '未收錄';
        gVal.innerHTML = '<span style="color:var(--gray)">無補丁檔案</span>';
      }
    }

    // 🌟 聯機標籤：嚴格以 Google Drive 網盤是否收錄為準，不與部署狀態綁定
    if(gdrive.available){
      if(!_onlinefixAppids) _onlinefixAppids = new Set();
      _onlinefixAppids.add(targetAppid);
    } else {
      if(_onlinefixAppids) _onlinefixAppids.delete(targetAppid);
    }
    // 🌟 部署標籤：嚴格以本地是否已套用補丁為準
    if(gdrive.is_deployed){
      if(!_deployedAppids) _deployedAppids = new Set();
      _deployedAppids.add(targetAppid);
    } else {
      if(_deployedAppids) _deployedAppids.delete(targetAppid);
    }
    if(data.locked){
      if(!_lockedAppids) _lockedAppids = new Set();
      _lockedAppids.add(targetAppid);
    }

    if(_pre && _pre._games){
      for(var gi=0; gi<_pre._games.length; gi++){
        if(String(_pre._games[gi].appid) === targetAppid){
          if(gdrive.is_deployed !== undefined) _pre._games[gi].deployed = !!gdrive.is_deployed;
          if(gdrive.available !== undefined) _pre._games[gi].has_onlinefix = !!gdrive.available;
          break;
        }
      }
      var filter = (document.getElementById('mf').value||'').trim().toLowerCase();
      renderGames(_pre._games, filter);
    }

    // c. Online-Fix
    if(ofStatus && ofVal){
      if(of_info.available && of_info.url){
        ofStatus.className = 'chip ok';
        ofStatus.textContent = '已收錄';
        ofVal.innerHTML = '<a href="javascript:void(0)" onclick="openExternalUrl(\'' + jsesc(of_info.url) + '\')" style="color:#1976D2;font-weight:bold;text-decoration:underline">已收錄聯機補丁 ↗</a>';
      } else {
        ofStatus.className = 'chip gray';
        ofStatus.textContent = '未收錄';
        ofVal.innerHTML = '<span style="color:var(--gray)">未收錄</span>';
      }
    }

    // d. ZeiGames
    if(zgStatus && zgVal){
      if(zg_info.available && zg_info.url){
        zgStatus.className = 'chip ok';
        zgStatus.textContent = '已收錄';
        zgVal.innerHTML = '<a href="javascript:void(0)" onclick="openExternalUrl(\'' + jsesc(zg_info.url) + '\')" style="color:#7B1FA2;font-weight:bold;text-decoration:underline">已收錄專用補丁 ↗</a>';
      } else {
        zgStatus.className = 'chip gray';
        zgStatus.textContent = '未收錄';
        zgVal.innerHTML = '<span style="color:var(--gray)">未收錄</span>';
      }
    }

    // 渲染 Depot 子分類選項卡
    if(tabsEl){
      var tabHtml = '';
      _curDepotsData.forEach(function(d, i){
        var actClass = (i === 0) ? ' active' : '';
        if(d.is_deprecated){
          tabHtml += '<button class="dt-depot-btn dt-depot-deprecated' + actClass + '" onclick="renderDepotHistory(' + i + ')">' +
                     '<span style="text-decoration:line-through;opacity:0.75;">' + escHtml(d.depot_name) + '</span> ' +
                     '<span style="font-size:10.5px;text-decoration:none;opacity:0.9;font-weight:700;">(已棄置)</span>' +
                     '</button>';
        } else {
          tabHtml += '<button class="dt-depot-btn' + actClass + '" onclick="renderDepotHistory(' + i + ')">' + escHtml(d.depot_name) + '</button>';
        }
      });
      tabsEl.innerHTML = tabHtml;
    }

    // 預設渲染第一個 Depot
    renderDepotHistory(0);
  } catch(err) {
    if(myReqId !== _detailReqCounter || _curDetailAppid !== targetAppid) return;
    if(window.tt) tt('⚠️ 載入版本資料異常: ' + (err.message || err), 'er', 4500);
    if(sdbLoadingBanner) sdbLoadingBanner.style.display = 'none';
    if(listEl) listEl.innerHTML = '<div class="empty" style="padding:20px 0"><p>獲取版本清單失敗: ' + escHtml(err.message || String(err)) + '</p></div>';
  }
}

// ═══════════════════════════════════════════════════════
// 🌟 SteamDB Cloudflare 背景穿透載入完成回調 (自動平滑熱更新版本鏈與隱藏黃字)
// ═══════════════════════════════════════════════════════
window.onSteamDBLoaded = async function(appid, success){
  var aidStr = String(appid).trim();
  console.log('[SteamDB] 收到背景載入完成通知:', aidStr, success);
  var modal = document.getElementById('game-detail-modal');
  if(_curDetailAppid === aidStr && modal && modal.classList.contains('active')){
    try {
      var freshData = await pywebview.api.get_manifest_history(aidStr);
      if(_curDetailAppid !== aidStr) return;
      _curDetailData = freshData;
      _curDepotsData = freshData.depots || [];

      // 平滑隱藏 SteamDB 黃字載入橫幅
      var sdbBanner = document.getElementById('dt-steamdb-loading');
      if(sdbBanner){
        sdbBanner.style.opacity = '0';
        sdbBanner.style.transform = 'translateY(-4px)';
        sdbBanner.style.transition = 'all 0.3s ease';
        setTimeout(function(){
          if(_curDetailAppid === aidStr && sdbBanner){
            sdbBanner.style.display = 'none';
            sdbBanner.style.opacity = '1';
            sdbBanner.style.transform = 'none';
          }
        }, 300);
      }

      // 重新渲染 Depot 子分類按鈕與 Manifest 清單
      var tabsEl = document.getElementById('dt-depot-tabs');
      if(tabsEl && _curDepotsData.length){
        var tabHtml = '';
        _curDepotsData.forEach(function(d, i){
          var actClass = (i === _curSelectedDepotIdx) ? ' active' : '';
          if(d.is_deprecated){
            tabHtml += '<button class="dt-depot-btn dt-depot-deprecated' + actClass + '" onclick="renderDepotHistory(' + i + ')">' +
                       '<span style="text-decoration:line-through;opacity:0.75;">' + escHtml(d.depot_name) + '</span> ' +
                       '<span style="font-size:10.5px;text-decoration:none;opacity:0.9;font-weight:700;">(已棄置)</span>' +
                       '</button>';
          } else {
            tabHtml += '<button class="dt-depot-btn' + actClass + '" onclick="renderDepotHistory(' + i + ')">' + escHtml(d.depot_name) + '</button>';
          }
        });
        tabsEl.innerHTML = tabHtml;
      }
      renderDepotHistory(_curSelectedDepotIdx || 0);
    } catch(e){
      console.warn('[SteamDB] 背景熱更新失敗:', e);
    }
  }
};
// 入庫 + DLC (五大真實進度階段動畫與即時狀態回饋)
// ═══════════════════════════════════════════════════════
var _needRestart = false;

function formatBytes(bytes){
  if(!bytes || bytes <= 0) return '0 B';
  var k = 1024;
  var sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  var i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function updateCardProgress(aid, pct, actionText, isError, isSuccess){
  var aidStr = String(aid);
  var cleanPct = Math.min(100, Math.max(0, Math.round(pct)));
  var cards = document.querySelectorAll('.card[data-appid="' + aidStr + '"]');

  cards.forEach(function(card){
    var isListMode = card.closest('#glist.list') || (card.closest('#results') && !card.closest('#results.browse-grid'));

    if(!isListMode){
      // 🌟 網格模式：圓形進度環 Overlay (降低背景圖片與文字亮度)
      var ov = card.querySelector('.card-circle-overlay');
      if(!ov){
        ov = document.createElement('div');
        ov.className = 'card-circle-overlay';
        ov.innerHTML = '<div class="circle-box">' +
                         '<svg class="circle-svg" viewBox="0 0 44 44">' +
                           '<circle class="circle-bg-ring" cx="22" cy="22" r="18"/>' +
                           '<circle class="circle-bar-ring" id="cbr-' + aidStr + '" cx="22" cy="22" r="18" stroke-dasharray="113.1" stroke-dashoffset="113.1"/>' +
                         '</svg>' +
                         '<span class="circle-pct-text" id="cpt-' + aidStr + '">0%</span>' +
                       '</div>' +
                       '<div class="circle-action-text" id="cat-' + aidStr + '"></div>';
        card.appendChild(ov);
      }
      var barRing = ov.querySelector('.circle-bar-ring');
      var pctText = ov.querySelector('.circle-pct-text');
      var actText = ov.querySelector('.circle-action-text');

      // 周長 C = 2 * PI * 18 = 113.097
      var offset = 113.1 - (cleanPct / 100) * 113.1;
      if(barRing){
        barRing.style.strokeDashoffset = offset;
        if(isError){
          barRing.classList.add('error');
          barRing.classList.remove('success');
        } else if(isSuccess){
          barRing.classList.add('success');
          barRing.classList.remove('error');
        } else {
          barRing.classList.remove('error', 'success');
        }
      }
      if(pctText) pctText.textContent = cleanPct + '%';
      if(actText) actText.textContent = actionText || '';
    } else {
      // 🌟 列表模式：水平進度條容器 (#cpw-<aid>)
      var wrap = card.querySelector('.card-progress-wrap') || document.getElementById('cpw-' + aidStr);
      if(!wrap){
        wrap = document.createElement('div');
        wrap.className = 'card-progress-wrap active';
        wrap.id = 'cpw-' + aidStr;
        wrap.innerHTML = '<div class="card-progress-header">' +
                           '<span class="cp-action" id="cpa-' + aidStr + '"></span>' +
                           '<span class="cp-percent" id="cpp-' + aidStr + '">0%</span>' +
                         '</div>' +
                         '<div class="card-progress-track">' +
                           '<div class="card-progress-bar" id="cpb-' + aidStr + '"></div>' +
                         '</div>';
        var infoEl = card.querySelector('.info');
        if(infoEl){
          infoEl.insertAdjacentElement('afterend', wrap);
        } else {
          card.appendChild(wrap);
        }
      } else {
        wrap.classList.add('active');
      }
      var actEl = wrap.querySelector('.cp-action') || document.getElementById('cpa-' + aidStr);
      var pctEl = wrap.querySelector('.cp-percent') || document.getElementById('cpp-' + aidStr);
      var barEl = wrap.querySelector('.card-progress-bar') || document.getElementById('cpb-' + aidStr);

      if(actEl) actEl.textContent = actionText || '';
      if(pctEl) pctEl.textContent = cleanPct + '%';
      if(barEl){
        barEl.style.width = cleanPct + '%';
        if(isError){
          barEl.classList.add('error');
          barEl.classList.remove('success');
        } else if(isSuccess){
          barEl.classList.add('success');
          barEl.classList.remove('error');
        } else {
          barEl.classList.remove('error', 'success');
        }
      }
    }
  });
}

function finishCardProgress(aid, success, msg){
  var aidStr = String(aid);
  if(success){
    updateCardProgress(aidStr, 100, msg || '🎉 部署完成！', false, true);
    setTimeout(function(){
      document.querySelectorAll('.card[data-appid="' + aidStr + '"]').forEach(function(card){
        var ov = card.querySelector('.card-circle-overlay');
        if(ov) ov.remove();
        var wrap = card.querySelector('.card-progress-wrap');
        if(wrap) wrap.classList.remove('active');
      });
    }, 1800);
  } else {
    updateCardProgress(aidStr, 100, msg || '❌ 部署失敗', true, false);
    setTimeout(function(){
      document.querySelectorAll('.card[data-appid="' + aidStr + '"]').forEach(function(card){
        var ov = card.querySelector('.card-circle-overlay');
        if(ov) ov.remove();
        var wrap = card.querySelector('.card-progress-wrap');
        if(wrap) wrap.classList.remove('active');
      });
    }, 3800);
  }
}

async function ag(appid, name){
  if(window.Downloader && Downloader.installGame){
    return Downloader.installGame(appid, name);
  }
}

// 🌟 SteamDB 歷史資料非同步即時推播監聽器 (純 AppID 匹配，秒級無感刷新)
window.onSteamDBHistoryReady = function(appid, depots){
  var aidStr = String(appid || '').trim();
  if(!aidStr || aidStr !== String(_curDetailAppid || '').trim()) return;
  if(depots && depots.length){
    _curDepotsData = depots;
    renderDepotHistory(_curSelectedDepotIdx || 0);
  }
};


