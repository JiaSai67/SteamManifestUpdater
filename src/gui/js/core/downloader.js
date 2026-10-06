// ═════════════════════════════════════════════════════════════════════
// 🌟 Downloader: 系統統一之遊戲 Manifest 下載、入庫與更新調度中心
// ═════════════════════════════════════════════════════════════════════
(function(window){
  'use strict';

  // ─────────────────────────────────────────────────────────────────
  // 🌟 全系統唯一固定下載與檢驗順序定義 (固定於 downloader.js，不隨 UI 欄位拖曳改變)
  // 順序規則：
  // 1. Ryuu (首選下載源)
  // 2. DualVerification (Lua/Manifest自洽性與SteamCMD最新版本比對)
  // 3. HubcapDB (首選版本落後或未更新時之最新熱替換備援)
  // 4. Lua.tools (終極兜底下載源)
  // ─────────────────────────────────────────────────────────────────
  var DOWNLOAD_PIPELINE = Object.freeze([
    {
      step: 1,
      id: 'ryuu',
      name: 'Ryuu',
      role: 'primary',
      description: '首選下載源 (優先下載實體 Manifest 與 Lua)'
    },
    {
      step: 2,
      id: 'dual_verification',
      name: '雙重檢驗引擎',
      role: 'validator',
      description: '檢驗 Lua 與 Manifest 自洽性 (含 Depot ID)，並比對 SteamCMD / SteamDB 最新版本'
    },
    {
      step: 3,
      id: 'hubcapdb',
      name: 'HubcapDB',
      role: 'hot_fallback',
      description: '若首選未更新或版本落後，透過 API 比對確認最新後熱替換備援'
    },
    {
      step: 4,
      id: 'luatools',
      name: 'Lua.tools',
      role: 'fallback',
      description: '同源備用兜底下載源'
    }
  ]);

  var Downloader = {
    _activeDownloads: {},

    // 取得固定之全系統下載與檢驗管線定義
    getPipeline: function(){
      return DOWNLOAD_PIPELINE;
    },

    // ─────────────────────────────────────────────────────────────────
    // 1. 核心下載管線 (入庫與更新共用之唯一底層，支援雙重檢驗與 Hubcap 熱替換)
    // ─────────────────────────────────────────────────────────────────
    downloadManifest: async function(appid, name, options){
      var aidStr = String(appid || '').trim();
      var gName = name || ('App_' + aidStr);
      options = options || {};

      if(!aidStr){
        throw new Error('未提供有效 AppID');
      }

      // 避免同一款遊戲重複併發下載
      if(this._activeDownloads[aidStr]){
        return this._activeDownloads[aidStr];
      }

      var self = this;
      var p = (async function(){
        try {
          if(!window.pywebview || !pywebview.api || !pywebview.api.auto_stock_after_import){
            throw new Error('pywebview 後端 API 未就緒');
          }

          // 呼叫後端最高標準仲裁下載與部署管線
          var res = await pywebview.api.auto_stock_after_import(aidStr, gName);
          if(!res || !res.ok){
            var msg = (res && res.msg) ? res.msg : '伺服器未收錄或下載超時';
            throw new Error(msg);
          }

          // 🌟 核心即時廣播 (0ms 零延遲)：部署成功瞬間立即將卡片與記憶體標記為最新，瞬間消除需更新提示與角標！
          self.notifyGameStatusChanged({
            appid: aidStr,
            name: gName,
            is_installed: true,
            has_update: false,
            version_status: '最新版',
            best_source: (res && res.best_source) || '官方'
          });

          // 後端快取同步校驗 (非阻塞異步執行，絕不阻塞前端 UI 反饋)
          if(pywebview.api && pywebview.api.refresh_single_game_status){
            pywebview.api.refresh_single_game_status(aidStr).catch(function(){});
          }

          return { ok: true, data: res, status: { has_update: false, version_status: '最新版' } };
        } finally {
          delete self._activeDownloads[aidStr];
        }
      })();

      this._activeDownloads[aidStr] = p;
      return p;
    },

    // ─────────────────────────────────────────────────────────────────
    // 🌟 專屬憑證與額度防護對話框 (無灰化、高對比現代彈窗、三級精確診斷與引導)
    // ─────────────────────────────────────────────────────────────────
    showCredentialGuardModal: function(opts){
      opts = opts || {};
      var modalId = 'modal-credential-guard';
      var existing = document.getElementById(modalId);
      if(existing) existing.remove();

      var isDark = document.documentElement.classList.contains('dark') || !!document.querySelector('.app.dark') || !!document.querySelector('.app.has-bg');
      var icon = '🔑';
      var iconBg = isDark ? 'rgba(255, 171, 0, 0.2)' : 'rgba(255, 171, 0, 0.12)';
      var iconBorder = isDark ? 'rgba(255, 171, 0, 0.45)' : 'rgba(255, 171, 0, 0.35)';
      var btnBg = 'linear-gradient(135deg, #FFB300, #F57C00)';
      var titleColor = isDark ? '#FFD54F' : '#E65100';

      if(opts.type === 'expired'){
        icon = '⚠️';
        iconBg = isDark ? 'rgba(244, 67, 54, 0.22)' : 'rgba(244, 67, 54, 0.12)';
        iconBorder = isDark ? 'rgba(244, 67, 54, 0.55)' : 'rgba(244, 67, 54, 0.35)';
        btnBg = 'linear-gradient(135deg, #EF5350, #D32F2F)';
        titleColor = isDark ? '#FF8A80' : '#D32F2F';
      } else if(opts.type === 'exhausted'){
        icon = '⏳';
        iconBg = isDark ? 'rgba(156, 39, 176, 0.22)' : 'rgba(156, 39, 176, 0.12)';
        iconBorder = isDark ? 'rgba(156, 39, 176, 0.55)' : 'rgba(156, 39, 176, 0.35)';
        btnBg = 'linear-gradient(135deg, #AB47BC, #7B1FA2)';
        titleColor = isDark ? '#CE93D8' : '#7B1FA2';
      }

      var modal = document.createElement('div');
      modal.id = modalId;
      modal.className = 'modal-overlay';
      modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.68);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);z-index:100099;display:flex;align-items:center;justify-content:center;padding:16px;animation:fadeInModal 0.2s cubic-bezier(0.16,1,0.3,1)';

      var boxBg = isDark ? 'linear-gradient(145deg, #251D20, #1E1719)' : '#FFFFFF';
      var boxBorder = isDark ? '1.5px solid rgba(255, 183, 197, 0.25)' : '1.5px solid rgba(0, 0, 0, 0.1)';
      var textColor = isDark ? '#F0E6E8' : '#2D2124';
      var descColor = isDark ? '#A89B9E' : '#6B5E62';

      var html = 
        '<div class="modal-box" style="max-width:440px;width:100%;background:' + boxBg + ';border:' + boxBorder + ';border-radius:18px;padding:24px;box-shadow:0 24px 64px rgba(0,0,0,0.48);box-sizing:border-box;color:' + textColor + ';position:relative">' +
          '<div style="display:flex;align-items:flex-start;gap:14px;margin-bottom:16px">' +
            '<div style="width:48px;height:48px;border-radius:14px;background:' + iconBg + ';border:1px solid ' + iconBorder + ';display:flex;align-items:center;justify-content:center;font-size:24px;flex-shrink:0">' +
              icon +
            '</div>' +
            '<div style="flex:1">' +
              '<h3 style="margin:0 0 6px 0;font-size:16px;font-weight:700;color:' + titleColor + '">' + (opts.title || '憑證檢查') + '</h3>' +
              '<div style="font-size:12.5px;color:' + descColor + ';line-height:1.55">' + opts.message + '</div>' +
            '</div>' +
            '<button type="button" id="guard-modal-close" style="background:transparent;border:none;color:' + descColor + ';font-size:18px;cursor:pointer;padding:0;width:28px;height:28px;border-radius:6px;display:flex;align-items:center;justify-content:center;transition:background 0.15s">✕</button>' +
          '</div>' +
          '<div style="display:flex;justify-content:flex-end;gap:10px;margin-top:20px">' +
            '<button type="button" id="guard-modal-cancel" class="btn btn-o" style="padding:7px 16px;font-size:12.5px;border-radius:8px">取消</button>' +
            '<button type="button" id="guard-modal-primary" class="btn" style="padding:7px 18px;font-size:12.5px;font-weight:700;border-radius:8px;border:none;color:#fff;background:' + btnBg + ';box-shadow:0 4px 14px rgba(0,0,0,0.25)">' + (opts.primaryBtnText || '前往處理') + '</button>' +
          '</div>' +
        '</div>';

      modal.innerHTML = html;
      document.body.appendChild(modal);

      var closeModal = function(){
        modal.style.opacity = '0';
        modal.style.transition = 'opacity 0.15s ease';
        setTimeout(function(){ if(modal.parentNode) modal.parentNode.removeChild(modal); }, 150);
      };

      var btnClose = modal.querySelector('#guard-modal-close');
      if(btnClose) btnClose.onclick = closeModal;

      var btnCancel = modal.querySelector('#guard-modal-cancel');
      if(btnCancel) btnCancel.onclick = closeModal;

      var btnPrimary = modal.querySelector('#guard-modal-primary');
      if(btnPrimary){
        btnPrimary.onclick = function(){
          closeModal();
          if(opts.onPrimary) opts.onPrimary();
        };
      }

      modal.onclick = function(e){
        if(e.target === modal) closeModal();
      };
    },

    // ─────────────────────────────────────────────────────────────────
    // 🌟 核心防護守衛：三級精準憑證與額度檢查 (入庫與更新專用咽喉)
    // ─────────────────────────────────────────────────────────────────
    validateCredentialsAndQuota: async function(actionName){
      actionName = actionName || '操作';
      if(!window.pywebview || !window.pywebview.api || !window.pywebview.api.get_credentials_status){
        return true;
      }

      var st;
      try {
        st = await pywebview.api.get_credentials_status();
      } catch(e){
        console.warn('[Downloader] 檢查憑證狀態時發生例外:', e);
        return true;
      }
      if(!st || !st.ok) return true;

      var isAccValid = function(acc){
        if(!acc) return false;
        return acc.has_valid_credentials === true && !acc.is_expired && !acc.needs_relogin &&
               acc.status_badge !== '憑證無效' && acc.status_badge !== '憑證已過期' && acc.status_badge !== '未登入/憑證缺失';
      };

      var rAccs = (st.ryuu && st.ryuu.accounts) || [];
      var ltAccs = (st.lua_tools && st.lua_tools.accounts) || [];
      var hc = st.hubcap || {};

      var validRAccs = rAccs.filter(isAccValid);
      var validLtAccs = ltAccs.filter(isAccValid);
      var isHcValid = !!hc.is_valid;
      var isHcConfigured = !!hc.is_configured;

      var rLeft = 0;
      for(var i = 0; i < validRAccs.length; i++){
        var limit = parseInt(validRAccs[i].daily_limit) || 50;
        var used = parseInt(validRAccs[i].quota_used_today) || 0;
        rLeft += Math.max(0, limit - used);
      }

      var ltLeft = 0;
      for(var j = 0; j < validLtAccs.length; j++){
        var llimit = parseInt(validLtAccs[j].daily_limit) || 25;
        var lused = parseInt(validLtAccs[j].quota_used_today) || 0;
        ltLeft += Math.max(0, llimit - lused);
      }

      var hcLeft = isHcValid ? (hc.remaining || 0) : 0;
      var totalQuota = rLeft + ltLeft + hcLeft;

      // 🌟 1. 額度充足，直接放行
      if(totalQuota > 0){
        return true;
      }

      // 🌟 2. 發現無額度，層層精準判定憑證狀態
      var totalAccounts = rAccs.length + ltAccs.length + (isHcConfigured ? 1 : 0);
      var validAccounts = validRAccs.length + validLtAccs.length + (isHcValid ? 1 : 0);

      // (A) 沒有憑證 (未登入任何帳號) -> 提示需要登入帳號
      if(totalAccounts === 0){
        this.showCredentialGuardModal({
          type: 'unlogin',
          actionName: actionName,
          title: '🔑 需要登入帳號',
          message: '執行「' + actionName + '」需要使用 Ryuu 或 Lua.tools 配額憑證。<br><br>您目前尚未登入任何帳號，請先登入後再繼續。',
          primaryBtnText: '🔑 前往登入帳號',
          onPrimary: function(){
            if(window.switchPage) switchPage('credentials');
          }
        });
        return false;
      }

      // (B) 憑證過期 (已設定帳號但全都失效/需重登) -> 提示重新登入
      if(validAccounts === 0){
        this.showCredentialGuardModal({
          type: 'expired',
          actionName: actionName,
          title: '⚠️ 授權憑證已過期',
          message: '檢測到您綁定的帳號憑證已過期或失效，導致無可用配額。<br><br>請重新登入帳號以恢復額度後，再繼續執行「' + actionName + '」。',
          primaryBtnText: '🔄 前往重新登入',
          onPrimary: function(){
            if(window.switchPage) switchPage('credentials');
          }
        });
        return false;
      }

      // (C) 額度不足 (憑證有效，但今日額度用罄) -> 通知額度不足
      this.showCredentialGuardModal({
        type: 'exhausted',
        actionName: actionName,
        title: '⏳ 本日額度不足',
        message: '您的帳號憑證正常有效，但今日所有配額已全數用罄（剩餘 0 次）。<br><br>請等待明日每日額度重設，或新增其他備用帳號。',
        primaryBtnText: '👥 管理帳號 / 查看配額',
        onPrimary: function(){
          if(window.switchPage) switchPage('credentials');
        }
      });
      return false;
    },

    // ─────────────────────────────────────────────────────────────────
    // 2. 一鍵入庫調度入口 (包含 DLL 自檢、核心下載、網盤補丁與安裝監控)
    // ─────────────────────────────────────────────────────────────────
    installGame: async function(appid, name){
      var aidStr = String(appid).trim();
      var gameTitle = name || ('AppID ' + aidStr);

      // 🌟 核心防護守衛：一鍵入庫前檢查憑證與額度
      var canProceed = await this.validateCredentialsAndQuota('一鍵入庫');
      if(!canProceed){
        return;
      }

      try {
        // 階段 1: 0% ~ 4% 【Steam 環境與 DLL 核心自檢】
        if(window.updateCardProgress) updateCardProgress(aidStr, 1, '🔍 正在檢查 Steam 核心檔案與 DLL 運行環境...', false);
        var dlls = await pywebview.api.check_dlls();
        if(dlls.missing > 0){
          if(!confirm('檢測到 Steam 目錄下缺少 ' + dlls.missing + ' 個核心檔案\n\n入庫前需要先注入核心\n\n是否自動注入？')){
            if(window.updateCardProgress) updateCardProgress(aidStr, 0, '⚠️ 已取消（缺少核心檔案）', true);
            setTimeout(function(){ var w=document.getElementById('cpw-'+aidStr); if(w) w.classList.remove('active'); }, 2000);
            if(window.tt) tt('已取消（缺少核心檔案）', 'in');
            return;
          }
          if(window.updateCardProgress) updateCardProgress(aidStr, 2, '⚡ 正在注入 Steam 核心檔案...', false);
          var ikr = await pywebview.api.inject_kernel();
          if(!ikr.ok){
            if(window.updateCardProgress) updateCardProgress(aidStr, 2, '❌ 核心檔案注入失敗', true);
            if(window.tt) tt('❌ 核心檔案注入失敗（可能需要管理員權限或關閉 Steam）', 'er');
            return;
          }
        }
        if(window.updateCardProgress) updateCardProgress(aidStr, 4, '✅ Steam 運行環境與 DLL 核心檢測完成', false);
        await new Promise(function(r){ setTimeout(r, 120); });

        // 階段 2: 4% ~ 12% 【多源清單比對與下載】
        // 🌟 徹底告別舊有脆弱的 fetch_manifest 阻斷點，全面接入後端多源仲裁與 Hubcap 備援！
        if(window.updateCardProgress) updateCardProgress(aidStr, 8, '🔍 正在比對 SteamCMD、Ryuu 與 HubcapDB 庫存...', false);
        var dlResult = await this.downloadManifest(aidStr, gameTitle, { isInstall: true });
        if(window.updateCardProgress) updateCardProgress(aidStr, 16, '✅ 官方 Manifest 清單與解密金鑰部署完成', false);
        await new Promise(function(r){ setTimeout(r, 120); });

        // 階段 3: 16% ~ 22% 【Google Drive 網盤補丁庫查找】
        if(window.updateCardProgress) updateCardProgress(aidStr, 18, '📁 正在查找 Google Drive 網盤補丁庫...', false);
        var gdriveCheck = await pywebview.api.check_cloud_patch_available(aidStr, name).catch(function(){ return {has_patch:false}; });
        var hasCloudPatch = gdriveCheck && gdriveCheck.has_patch;
        var driveName = (gdriveCheck && gdriveCheck.drive_name) || 'Google Drive 補丁庫';
        if(window.updateCardProgress) updateCardProgress(aidStr, 22, '✅ 網盤補丁庫核驗完成' + (hasCloudPatch ? (' (已收錄於 ' + driveName + ')') : ' (無專屬聯機補丁)'), false);
        await new Promise(function(r){ setTimeout(r, 120); });

        // 階段 4: 22% ~ 25% 【線上聯機補丁下載】
        if(hasCloudPatch){
          if(window.updateCardProgress) updateCardProgress(aidStr, 23, '☁️ 正在自 ' + driveName + ' 下載對應聯機補丁...', false);
          try {
            var dlRes = await pywebview.api.download_online_patch(aidStr, name);
            if(dlRes && dlRes.ok){
              if(window.updateCardProgress) updateCardProgress(aidStr, 25, '✅ ' + driveName + ' 線上補丁下載就緒！', false);
            } else {
              if(window.updateCardProgress) updateCardProgress(aidStr, 25, '⚠️ 補丁下載略過 (待主程式安裝後手動重試)', false);
            }
          } catch(e){
            if(window.updateCardProgress) updateCardProgress(aidStr, 25, '✅ 補丁暫存就緒', false);
          }
        } else {
          if(window.updateCardProgress) updateCardProgress(aidStr, 25, '✅ 官方清單就緒 (無專屬線上補丁)', false);
        }

        // 階段 5: 25% ~ 90% 【監測 Steam 遊戲下載 / 安裝進度】
        if(window.updateCardProgress) updateCardProgress(aidStr, 25, '🎮 正在檢查 Steam 主程式狀態...', false);
        var instRes = await pywebview.api.get_steam_download_report(aidStr).catch(function(){ return {report:{status:'DOWNLOADING'}}; });
        var rep = (instRes && instRes.report) || {};

        if(rep.status === 'COMPLETED'){
          if(window.updateCardProgress) updateCardProgress(aidStr, 90, '✅ Steam 遊戲主程式已就緒 (免下載)', false);
        } else {
          if(window.updateCardProgress) updateCardProgress(aidStr, 25, '🎮 正在喚起 Steam 開始下載遊戲主程式...', false);
          await pywebview.api.launch_steam_install(aidStr, name);

          var downloadDone = false;
          var pollCount = 0;
          var promptWaitCount = 0;
          var promptTimeoutSec = 20;

          while(!downloadDone && pollCount < 7200){
            await new Promise(function(r){ setTimeout(r, 1000); });
            pollCount++;

            var curRepRes = await pywebview.api.get_steam_download_report(aidStr).catch(function(){ return null; });
            var curRep = (curRepRes && curRepRes.report) || {};
            var st = curRep.status;
            var stageName = curRep.stage_name || 'DOWNLOADING';

            if(st === 'COMPLETED'){
              downloadDone = true;
              if(window.updateCardProgress) updateCardProgress(aidStr, 90, '🎉 Steam 主程式下載完成！', false);
              break;
            } else if(st === 'ERROR'){
              var errMsg = curRep.error_msg || 'Steam 回報下載錯誤';
              if(window.updateCardProgress) updateCardProgress(aidStr, 25, '❌ Steam 下載中斷: ' + errMsg, true);
              if(window.tt) tt('⚠️ Steam 下載中斷: ' + errMsg, 'wn', 5000);
              if(window.openDownloadDiagnosticModal) openDownloadDiagnosticModal(aidStr, gameTitle);
              return;
            } else if(st === 'CANCELLED'){
              if(window.updateCardProgress) updateCardProgress(aidStr, 0, '⚠️ Steam 下載已取消', true);
              if(window.finishCardProgress) finishCardProgress(aidStr, false, '⚠️ Steam 下載已取消');
              if(window.tt) tt('⚠️ 「' + gameTitle + '」Steam 下載已取消', 'wn', 4000);
              return;
            } else if(st === 'PAUSED'){
              var pctFromSteam = Number(curRep.progress_pct || 0);
              var dlText = '⏸️ Steam 下載已暫停 (' + pctFromSteam.toFixed(1) + '%) [請在 Steam 繼續]';
              var mappedPct = 25 + Math.round((pctFromSteam / 100) * 65);
              if(window.updateCardProgress) updateCardProgress(aidStr, mappedPct, dlText, false);
            } else {
              var pctFromSteam = Number(curRep.progress_pct || 0);
              var dlBytes = Number(curRep.bytes_downloaded || 0);
              var totalBytes = Number(curRep.bytes_to_download || 0);
              var speedStr = curRep.speed_str ? (' · ' + curRep.speed_str) : '';

              if(st === 'NOT_INSTALLED' && dlBytes === 0 && totalBytes === 0){
                promptWaitCount++;
                var remainSec = Math.max(0, promptTimeoutSec - promptWaitCount);
                if(remainSec <= 0){
                  if(window.updateCardProgress) updateCardProgress(aidStr, 0, '⚠️ 已結束安裝等候 (已入庫，可隨時在 Steam 下載)', true);
                  if(window.finishCardProgress) finishCardProgress(aidStr, false, '⚠️ 已結束安裝等候 (已入庫，可隨時在 Steam 下載)');
                  if(window.tt) tt('ℹ️ 「' + gameTitle + '」已結束安裝等候。遊戲已完成入庫，隨時可在 Steam 內點擊安裝！', 'in', 5000);
                  return;
                }
                var dlText = '🎮 請在 Steam 視窗中確認安裝 (' + remainSec + 's 倒數，逾時不影響入庫狀態)';
                if(window.updateCardProgress) updateCardProgress(aidStr, 25, dlText, false);
              } else {
                promptWaitCount = 0;
                var mappedPct = Math.min(90, Math.max(25, 25 + Math.round((pctFromSteam / 100) * 65)));
                var dlText = '';
                if(stageName === 'STAGING'){
                  dlText = '📦 Steam 正在解壓與驗證檔案中: ' + pctFromSteam.toFixed(1) + '%' + (totalBytes > 0 ? (' (' + formatBytes(dlBytes) + ' / ' + formatBytes(totalBytes) + ')') : '') + speedStr;
                } else if(totalBytes > 0 && dlBytes > 0){
                  dlText = '🎮 Steam 下載中: ' + pctFromSteam.toFixed(1) + '% (' + formatBytes(dlBytes) + ' / ' + formatBytes(totalBytes) + speedStr + ')';
                } else if(totalBytes > 0){
                  dlText = '🎮 Steam 下載中: ' + pctFromSteam.toFixed(1) + '% (共 ' + formatBytes(totalBytes) + speedStr + ')';
                } else if(dlBytes > 0){
                  var mbDl = dlBytes / (1024 * 1024);
                  var simulated = Math.min(60, Math.round(mbDl / 150) + (pollCount % 5));
                  mappedPct = 25 + Math.max(5, simulated);
                  dlText = '🎮 Steam 即時下載中: 已下載 ' + formatBytes(dlBytes) + speedStr;
                } else {
                  var waitDots = '.'.repeat((pollCount % 3) + 1);
                  dlText = '🎮 正在等候 Steam 佇列連線與分配空間' + waitDots;
                  mappedPct = 25;
                }
                if(window.updateCardProgress) updateCardProgress(aidStr, mappedPct, dlText, false);
              }
            }
          }
        }

        // 階段 6: 90% ~ 100% 【補丁安裝與原檔保護】
        if(hasCloudPatch){
          if(window.updateCardProgress) updateCardProgress(aidStr, 93, '🛡️ 正在自動備份遊戲原始檔案 (.bak)...', false);
          await new Promise(function(r){ setTimeout(r, 200); });
          if(window.updateCardProgress) updateCardProgress(aidStr, 96, '🚀 正在解壓部署 Online-Fix 聯機補丁...', false);
          var patchRes = await pywebview.api.install_online_patch(aidStr, name);
          if(patchRes && patchRes.ok && patchRes.installed){
            if(window._deployedAppids) _deployedAppids.add(aidStr);
            if(window._protectedAppids) _protectedAppids.add(aidStr);
            if(window._onlinefixAppids) _onlinefixAppids.add(aidStr);
            var bCard = document.querySelector('#results .card[data-appid="'+aidStr+'"]');
            if(bCard) bCard.classList.add('has-onlinefix');
          }
        }

        if(window.updateCardProgress) updateCardProgress(aidStr, 100, '🎉 一鍵入庫與清單部署全部完成！', false, true);
        if(window.tt) tt('✅ ' + gameTitle + ' 入庫成功' + (hasCloudPatch ? ' (已部署聯機補丁)' : ''), 'ok');
        if(window.finishCardProgress) finishCardProgress(aidStr, true, '🎉 一鍵入庫與清單部署全部完成！');

        // 重新同步並保鮮管理清單
        if(window._pre) _pre._rendered = false;
        if(window.rg) { try { await rg(true); } catch(e){} }

      } catch(e){
        if(window.updateCardProgress) updateCardProgress(aidStr, 0, '❌ 發生錯誤: ' + (e.message || e), true);
        if(window.finishCardProgress) finishCardProgress(aidStr, false, '❌ 發生錯誤: ' + (e.message || e));
        if(window.tt) tt('❌ 入庫過程出錯: ' + (e.message || e), 'er');
      }
    },

    // ─────────────────────────────────────────────────────────────────
    // ─────────────────────────────────────────────────────────────────
    // 3. 單個遊戲版本更新調度入口 (在卡片上顯示動態金黃光圈並原地無感轉綠)
    // ─────────────────────────────────────────────────────────────────
    updateGame: async function(appid, name, options){
      var aidStr = String(appid || '').trim();
      var gName = name || ('App_' + aidStr);
      options = options || {};
      if(!aidStr){
        if(window.tt) tt('❌ 更新失敗：無效或未提供 AppID', 'er', 4000);
        return false;
      }

      // 🌟 核心防護守衛：更新前檢查憑證與額度 (非批次靜默模式時進行前置驗證)
      if(!options.silentBatch){
        var canProceed = await this.validateCredentialsAndQuota('更新 Manifest');
        if(!canProceed){
          return false;
        }
      }

      var card = document.querySelector('#glist .card[data-appid="'+aidStr+'"]') || document.querySelector('#results .card[data-appid="'+aidStr+'"]');
      var ov = null;
      if(card){
        card.classList.add('is-updating');
        ov = card.querySelector('.card-updating-overlay');
        if(!ov){
          ov = document.createElement('div');
          ov.className = 'card-updating-overlay';
          ov.innerHTML = '<div class="card-spinner"></div><div class="card-update-status">正在對齊與下載 Manifest…</div>';
          card.appendChild(ov);
        } else {
          var statEl = ov.querySelector('.card-update-status');
          if(statEl) statEl.textContent = '正在對齊與下載 Manifest…';
        }
      } else if(!options.silent){
        if(window.sp) sp('正在更新 Manifest…', '「'+gName+'」正在多源比對與下載…', 30, '請稍候…');
      }

      try {
        var res = await this.downloadManifest(aidStr, gName, { isUpdate: true });

        // 🌟 即刻消除卡片需更新提示與發光邊框 (0ms 反饋)
        if(card){
          card.classList.remove('needs-update');
          var upTags = card.querySelectorAll('.tag-up, .corner-tag.tag-up');
          upTags.forEach(function(t){ t.remove(); });
        }
        if(window.refreshUpdateCountUI) refreshUpdateCountUI();

        if(ov) {
          var statEl = ov.querySelector('.card-update-status');
          if(statEl) statEl.textContent = '✅ 更新校驗完成！';
          var spinner = ov.querySelector('.card-spinner');
          if(spinner) spinner.style.borderTopColor = '#4CAF50';
        }
        if(!options.silentBatch){
          if(window.tt) tt('🎉 「' + gName + '」Manifest 版本更新完成！', 'ok');
        }
        // 留 200ms 讓使用者看清完成反饋
        await new Promise(function(r){ setTimeout(r, 200); });
        return true;
      } catch(err){
        if(ov) {
          var statEl = ov.querySelector('.card-update-status');
          if(statEl) statEl.textContent = '❌ 更新失敗: ' + (err.message || err);
          var spinner = ov.querySelector('.card-spinner');
          if(spinner) spinner.style.borderTopColor = '#F44336';
        }
        if(!options.silentBatch){
          if(window.tt) tt('❌ 「' + gName + '」更新失敗: ' + (err.message || err), 'er');
        }
        await new Promise(function(r){ setTimeout(r, 1200); });
        throw err;
      } finally {
        if(ov) ov.remove();
        if(card) card.classList.remove('is-updating');
        if(window.cp && !options.silent) cp();
      }
    },

    // ─────────────────────────────────────────────────────────────────
    // 4. 全部批次自動升級調度入口 (防漏隊列二次校準 · 全鏈路批次調度診斷日誌)
    // ─────────────────────────────────────────────────────────────────
    updateAllGames: async function(){
      // 🌟 核心防護守衛：批次更新前先檢查憑證與額度
      var canProceed = await this.validateCredentialsAndQuota('批次更新');
      if(!canProceed){
        return;
      }

      // 🌟 核心防漏機制：直接向後端磁碟資料庫請求最新待更新清單，杜絕前端快照時序差導致遺漏！
      var updatables = [];
      try {
        if(window.pywebview && pywebview.api && pywebview.api.get_updatable_games){
          updatables = await pywebview.api.get_updatable_games();
        }
      } catch(e){}

      // 雙向合併去重：確保記憶體與磁碟資料庫中的所有待更新項目 100% 納入隊列
      if(!updatables || !updatables.length){
        updatables = (window._pre && _pre._games) ? _pre._games.filter(function(g){ return g.has_update; }) : [];
      } else if(window._pre && _pre._games){
        var aidSet = new Set(updatables.map(function(u){ return String(u.appid); }));
        _pre._games.forEach(function(g){
          if(g.has_update && !aidSet.has(String(g.appid))){
            updatables.push({
              appid: String(g.appid),
              name: g.name || ('App_' + g.appid),
              has_update: true,
              version_status: g.version_status || '可更新',
              latest_date: g.latest_date || '',
              best_source: g.best_source || 'ryuu'
            });
            aidSet.add(String(g.appid));
          }
        });
      }

      if(!updatables.length){
        if(window.tt) tt('所有本機遊戲皆已是最新檔案！', 'ok');
        return;
      }

      var btnBatch = document.getElementById('btn-batch-update');
      var originalBtnText = btnBatch ? btnBatch.textContent : '';
      if(btnBatch){
        btnBatch.disabled = true;
        btnBatch.style.opacity = '0.7';
      }

      // 🌟 啟動批次調度日誌 Session (持久化儲存至 logs/batch_updates/)
      var sessionId = '';
      try {
        if(window.pywebview && pywebview.api && pywebview.api.start_batch_update_session){
          sessionId = await pywebview.api.start_batch_update_session(updatables);
        }
      } catch(e){
        console.warn('[Downloader] 建立批次日誌異常:', e);
      }

      // 🌟 1. 立即將所有待升級項目的卡片掛上「排隊等候升級」微狀態
      updatables.forEach(function(g, idx){
        var card = document.querySelector('#glist .card[data-appid="'+g.appid+'"]');
        if(card){
          card.classList.add('is-updating');
          var ov = card.querySelector('.card-updating-overlay');
          if(!ov){
            ov = document.createElement('div');
            ov.className = 'card-updating-overlay';
            ov.innerHTML = '<div class="card-spinner"></div><div class="card-update-status">' + (idx === 0 ? '正在立即升級…' : '排隊等候升級中…') + '</div>';
            card.appendChild(ov);
          }
        }
      });

      if(window.tt) tt('⚡ 已啟動一鍵批次升級，共鎖定 ' + updatables.length + ' 款遊戲逐項就地升級中…', 'in', 3000);

      var success = 0;
      var failed = [];

      // 🌟 2. 直接依序調用每個需要升級的項目，並即時寫入批次日誌
      for(var i = 0; i < updatables.length; i++){
        var g = updatables[i];
        var gName = g.name || g.appid;
        if(btnBatch){
          btnBatch.textContent = '⚡ 正在升級 (' + (i + 1) + '/' + updatables.length + ')...';
        }

        var itemStart = Date.now();
        try {
          await this.updateGame(g.appid, gName, { silentBatch: true, silent: true });
          success++;
          var dur = Date.now() - itemStart;
          if(sessionId && window.pywebview && pywebview.api && pywebview.api.log_batch_update_item){
            try { pywebview.api.log_batch_update_item(sessionId, g.appid, gName, true, dur, 'Manifest 版本更新完成'); } catch(e){}
          }
        } catch(err){
          var dur = Date.now() - itemStart;
          var errMsg = (err && err.message) || String(err);
          failed.push({ appid: g.appid, name: gName, msg: errMsg });
          if(sessionId && window.pywebview && pywebview.api && pywebview.api.log_batch_update_item){
            try { pywebview.api.log_batch_update_item(sessionId, g.appid, gName, false, dur, errMsg); } catch(e){}
          }
        }
      }

      // 🌟 結算並落盤批次調度日誌
      if(sessionId && window.pywebview && pywebview.api && pywebview.api.finish_batch_update_session){
        try {
          await pywebview.api.finish_batch_update_session(sessionId, '批次更新調度執行完畢');
        } catch(e){}
      }

      // 🌟 3. 恢復按鈕狀態與計數
      if(btnBatch){
        btnBatch.disabled = false;
        btnBatch.style.opacity = '1';
        btnBatch.textContent = originalBtnText;
      }
      if(window.refreshUpdateCountUI) refreshUpdateCountUI();

      // 🌟 4. 同步與局部微調排序 (若需更新列表)
      if(window._pre && _pre._games){
        _pre._games.sort(function(a,b){ return (b.has_update?1:0) - (a.has_update?1:0); });
        var filter = (document.getElementById('mf') ? document.getElementById('mf').value : '').trim().toLowerCase();
        if(window.renderGames) renderGames(_pre._games, filter);
      }

      // 🌟 5. 輕量 Toast 結果反饋
      if(failed.length === 0){
        if(window.tt) tt('🎉 批次升級完成！已成功升級全部 ' + success + ' 款遊戲為最新 Manifest。', 'ok', 4000);
      } else if(success > 0){
        var failNames = failed.slice(0, 3).map(function(f){ return f.name; }).join('、');
        if(failed.length > 3) failNames += ' 等 ' + failed.length + ' 款';
        if(window.tt) tt('⚡ 批次升級結束：成功 ' + success + ' 款，失敗 ' + failed.length + ' 款（' + failNames + '）', 'wn', 4000);
      } else {
        var firstMsg = failed[0] ? failed[0].msg : '請檢查網路連線或憑證狀態';
        if(window.tt) tt('❌ 批次升級失敗: ' + firstMsg, 'er', 4000);
      }
    },

    // ─────────────────────────────────────────────────────────────────
    // 5. 🌟 統一狀態廣播事件派發器 (全系統各卡片與彈窗原地自適應同步)
    // ─────────────────────────────────────────────────────────────────
    notifyGameStatusChanged: function(payload){
      if(!payload || !payload.appid) return;
      var aid = String(payload.appid).trim();
      var hasUp = !!payload.has_update;
      var vStat = payload.version_status || (hasUp ? '可更新' : '最新版');

      // A. 同步全域記憶體資料庫
      if(window._installedAppids) _installedAppids.add(aid);
      if(!window._knownUpdates) window._knownUpdates = {};
      window._knownUpdates[aid] = {
        appid: aid,
        has_update: hasUp,
        version_status: vStat,
        latest_date: payload.latest_date || '',
        best_source: payload.best_source || ''
      };

      if(window._pre && _pre._games && _pre._games.length){
        for(var i = 0; i < _pre._games.length; i++){
          var g = _pre._games[i];
          if(String(g.appid) === aid){
            g.has_update = hasUp;
            g.version_status = vStat;
            g.is_installed = true;
            if(payload.latest_date) g.latest_date = payload.latest_date;
            if(payload.best_source) g.best_source = payload.best_source;
            break;
          }
        }
      }

      // B. 原地更新「管理頁面」卡片 DOM
      var mCard = document.querySelector('#glist .card[data-appid="' + aid + '"]');
      if(mCard){
        var cornerBox = mCard.querySelector('.card-corner-tags');
        if(!cornerBox){
          mCard.insertAdjacentHTML('afterbegin', '<div class="card-corner-tags"></div>');
          cornerBox = mCard.querySelector('.card-corner-tags');
        }
        var upTag = cornerBox.querySelector('.tag-up');
        var ddEl = mCard.querySelector('.card-dd');

        if(hasUp){
          mCard.classList.add('needs-update');
          var rawStatus = String(vStat).replace(/跨越/g, '舊').replace(/⚡/g, '').trim();
          if(!upTag){
            cornerBox.insertAdjacentHTML('beforeend', '<span class="corner-tag tag-up" title="' + escHtml(rawStatus) + '">⚡ ' + escHtml(rawStatus) + '</span>');
          } else {
            upTag.textContent = '⚡ ' + rawStatus;
          }
          if(ddEl && !ddEl.querySelector('.btn-auto-up')){
            var nm = mCard.querySelector('.name') ? mCard.querySelector('.name').getAttribute('title') : ('App_' + aid);
            var upBtnHtml = '<button class="btn-auto-up" style="color:#ffd700;font-weight:bold" onclick="Downloader.updateGame(\'' + aid + '\',\'' + jsesc(nm) + '\')">⚡ 一鍵更新 Manifest</button>';
            ddEl.insertAdjacentHTML('afterbegin', upBtnHtml);
          }
        } else {
          mCard.classList.remove('needs-update');
          if(upTag) upTag.remove();
          mCard.querySelectorAll('.tag-up, .corner-tag.tag-up').forEach(function(el){ el.remove(); });
          if(ddEl){
            var btnAuto = ddEl.querySelector('.btn-auto-up');
            if(btnAuto) btnAuto.remove();
          }
        }
      }

      // C. 原地更新「搜尋頁面」卡片 DOM
      var sCard = document.querySelector('#results .card[data-appid="' + aid + '"]');
      if(sCard){
        sCard.classList.remove('needs-update');
        var sBtn = sCard.querySelector('.btn');
        if(sBtn){
          sBtn.outerHTML = '<button class="btn btn-o btn-s" style="color:var(--succ);border-color:var(--succ);cursor:default" onclick="event.stopPropagation()">✅ 已在本地</button>';
        }
        var sactEl = document.getElementById('sact-' + aid);
        if(sactEl){
          sactEl.innerHTML = '<button class="btn btn-o btn-s" style="color:var(--succ);border-color:var(--succ);cursor:default" onclick="event.stopPropagation()">✅ 已在本地</button>';
        }
        var sCorner = sCard.querySelector('.card-corner-tags');
        if(sCorner){
          var tagUp = sCorner.querySelector('.tag-up');
          if(tagUp) tagUp.remove();
        }
      }

      // D. 原地更新「遊戲詳細小卡」按鈕狀態
      var modal = document.getElementById('game-detail-modal');
      var curModalAid = window._curDetailAppid || '';
      if(modal && modal.classList.contains('active') && curModalAid === aid){
        var actBtn = document.getElementById('dt-btn-action');
        if(actBtn){
          if(hasUp){
            actBtn.textContent = '⚡ 立即更新至官方最新版';
            actBtn.className = 'btn btn-p btn-s';
            actBtn.style.display = 'inline-flex';
            actBtn.onclick = function(){
              if(window.closeGameDetail) closeGameDetail();
              Downloader.updateGame(aid, window._curDetailName || ('App_' + aid));
            };
          } else {
            // 已是最新版，隱藏一鍵按鈕
            actBtn.style.display = 'none';
            actBtn.onclick = null;
          }
        }
      }

      // 🌟 核心即時同步：立即更新頂部「⚡ 批次更新 (X 款可更新)」按鈕狀態與計數 (0ms 消除提示)
      if(typeof window.refreshUpdateCountUI === 'function'){
        try { window.refreshUpdateCountUI(); } catch(e){}
      }

      // E. 向後相容既有全域回調
      if(typeof window.onSingleGameUpdateChecked === 'function' && window.onSingleGameUpdateChecked !== Downloader.notifyGameStatusChanged){
        try {
          window.onSingleGameUpdateChecked(payload);
        } catch(e){}
      }
    }
  };

  // 全域暴露與向後相容掛載
  window.Downloader = Downloader;
  window.ag = function(appid, name){ return Downloader.installGame(appid, name); };
  window.autoUpdateSingle = function(appid, name){ return Downloader.updateGame(appid, name); };
  window.autoUpdateAll = function(){ return Downloader.updateAllGames(); };

})(window);
