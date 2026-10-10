/**
 * 教學模組 1：憑證登入引導 (Credentials Login Tutorial)
 * 職責：
 * 1. 引導認識憑證頁面與配額機制
 * 2. 模擬點擊登入按鈕
 * 3. 彈出擬真沙盒登入小卡 (純前端暫存，未過任何雲端)
 * 4. 展示登入成功後的帳號配額矩陣視覺
 */

(function(window) {
  'use strict';

  var _origBtnHTML = null;
  var _mockClickHandler = null;

  // 模擬將虛擬帳號注入配額矩陣表格 (純視覺暫存，1:1 比照實際配額矩陣格式)
  function injectMockMatrixData() {
    // 🌟 設定教學模式守護旗標，防止背景非同步輪詢覆蓋示範資料
    window.__tutorialMockCredentialsActive = true;

    var mockCredentialsData = {
      __is_tutorial_mock: true,
      ryuu: {
        accounts: [
          {
            id: '1088492049182390192',
            discord_id: 'DemoGamer#2026',
            name: 'DemoGamer#2026',
            username: 'demogamer2026',
            email: 'demogamer@example.com',
            avatar_url: 'https://cdn.discordapp.com/embed/avatars/0.png',
            has_valid_credentials: true,
            is_valid: true,
            is_expired: false,
            needs_relogin: false,
            status_badge: '正常',
            daily_limit: 50,
            quota_used_today: 0,
            hubcap: {
              is_valid: true,
              is_configured: true,
              remaining: 25,
              daily_limit: 25,
              api_key_masked: 'hub_demo_****'
            }
          }
        ]
      },
      lua_tools: {
        accounts: [
          {
            id: '1088492049182390192',
            discord_id: 'DemoGamer#2026',
            name: 'DemoGamer#2026',
            username: 'demogamer2026',
            email: 'demogamer@example.com',
            avatar_url: 'https://cdn.discordapp.com/embed/avatars/0.png',
            has_valid_credentials: true,
            is_valid: true,
            is_expired: false,
            needs_relogin: false,
            status_badge: '正常',
            daily_limit: 25,
            quota_used_today: 0
          }
        ]
      },
      hubcap: {
        is_valid: true,
        is_configured: true,
        remaining: 25,
        daily_limit: 25,
        api_key_masked: 'hub_demo_****'
      }
    };

    if (typeof renderQuotaMatrix === 'function') {
      renderQuotaMatrix(mockCredentialsData, true);
    }
  }

  // 還原真實狀態 (教學結束或離開時呼叫)
  function cleanupMockMatrix() {
    window.__tutorialMockCredentialsActive = false;

    var btn = document.querySelector('#p-credentials button[onclick="startDualPlatformSandboxLogin()"]');
    if (btn) {
      btn.classList.remove('tutorial-btn-simulating');
      if (_origBtnHTML) {
        btn.innerHTML = _origBtnHTML;
      } else {
        btn.innerHTML = '<span>🔑</span><span>登入 / 綁定 Discord</span>';
      }
      _origBtnHTML = null;
      if (_mockClickHandler) {
        btn.removeEventListener('click', _mockClickHandler, true);
        _mockClickHandler = null;
      }
    }
    if (typeof window.loadCredentialsStatus === 'function') {
      try {
        window.loadCredentialsStatus(true);
      } catch (e) {
        console.error('[Tutorial] restore credentials error:', e);
      }
    }
  }

  var credentialsModuleSteps = [
    {
      roleBadge: '🐺 獨狼玩家',
      moduleTitle: '單元 1：憑證登入引導',
      page: 'credentials',
      target: '.sidebar button[data-p="credentials"]',
      title: '進入憑證管理',
      desc: '在開始探索與入庫遊戲前，需要先備妥下載與解析所須的存取憑證。點擊左側「🪪 憑證管理」標籤即可前往設定。',
      hint: '只需登入一次即可享有每日自動刷新配額。',
      placement: 'right'
    },
    {
      roleBadge: '🐺 獨狼玩家',
      moduleTitle: '單元 1：憑證登入引導',
      page: 'credentials',
      target: '#p-credentials button[onclick="startDualPlatformSandboxLogin()"]',
      title: '點擊以模擬登入',
      desc: '聚焦期間此按鈕已切換為【模擬模式】並帶有流光提示。直接點擊上方按鈕，系統將自動模擬身分認證與配額綁定，絕不呼叫真實瀏覽器。',
      disableNext: true,
      onEnter: function(btn) {
        if (!btn) return;
        _origBtnHTML = btn.innerHTML;
        // 🌟 以動畫替換文字與樣式，清楚標註模擬模式
        btn.innerHTML = '<span>🧪 點擊模擬登入 (示範)</span>';
        btn.classList.add('tutorial-btn-simulating');

        // 🌟 攔截事件，防止進入真實 Discord 授權
        _mockClickHandler = function(e) {
          e.preventDefault();
          e.stopPropagation();
          e.stopImmediatePropagation();
          if (typeof tt === 'function') tt('🧪 正在以教學沙盒模擬登入…', 'ok');
          injectMockMatrixData();
          setTimeout(function() {
            TutorialEngine.next();
          }, 400);
        };
        btn.addEventListener('click', _mockClickHandler, true);
      },
      onLeave: function() {
        var btn = document.querySelector('#p-credentials button[onclick="startDualPlatformSandboxLogin()"]');
        if (btn) {
          btn.classList.remove('tutorial-btn-simulating');
          if (_origBtnHTML !== null) {
            btn.innerHTML = _origBtnHTML;
            _origBtnHTML = null;
          }
          if (_mockClickHandler) {
            btn.removeEventListener('click', _mockClickHandler, true);
            _mockClickHandler = null;
          }
        }
      },
      placement: 'bottom'
    },
    {
      roleBadge: '🐺 獨狼玩家',
      moduleTitle: '單元 1：憑證登入引導',
      page: 'credentials',
      target: '.cred-matrix-card',
      title: '檢視配額矩陣狀態',
      desc: '恭喜！此時配額矩陣將顯示您已成功獲取的 Ryuu 與 Lua.tools 每日配額，代表您已具備單人遊玩與遊戲入庫的所有權限！',
      hint: '配額將於每日午夜自動重置。',
      placement: 'bottom',
      onEnter: function() {
        injectMockMatrixData();
      },
      onLeave: cleanupMockMatrix
    }
  ];

  if (window.TutorialEngine) {
    window.TutorialEngine.registerModule('credentials_login', {
      name: '憑證登入引導',
      steps: credentialsModuleSteps,
      cleanup: cleanupMockMatrix
    });
  }
})(window);
