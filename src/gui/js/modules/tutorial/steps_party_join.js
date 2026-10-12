/**
 * 教學模組：組隊入隊引導 (Party Join Tutorial Steps - 旗艦完整生命週期版)
 * 職責：
 * 步驟 1 / 11：大廳即時搜尋（遊戲名稱、房號、房主模糊搜尋）
 * 步驟 2 / 11：邀請代碼快速加入（輸入 6~8 碼房間邀請碼一鍵直達）
 * 步驟 3 / 11：大廳示範房間模擬加入（引導親自點擊模擬申請，鎖定下一步）
 * 步驟 4 / 11：進入房間視圖，確認房號【PAL886】與遊戲資訊
 * 步驟 5 / 11：隊伍成員名單結構與版本狀態比對
 * 步驟 6 / 11：模擬一鍵安裝（呈現「🚀 點擊模擬安裝」，親自點擊互動）
 * 步驟 7 / 11：3 秒平滑即時下載、校對與進度推進模擬 (0% -> 100%)
 * 步驟 8 / 11：雲端無伺服器與 Discord CDN 傳輸架構解密
 * 步驟 9 / 11：全員就緒後的房長 1 分鐘緩衝操作與隊員等待機制
 * 步驟 10 / 11：真實模擬！接收房長開拔廣播卡片與一鍵複製
 * 步驟 11 / 11：房間生命週期圓滿結束與領取結業證書
 */

(function(window) {
  'use strict';

  var _origRoomsGridHTML = null;
  var _mockJoinRoomData = {
    room_id: 'PAL886',
    appid: '1623730',
    game_name: '幻獸帕魯 (Palworld) - 週末同樂團',
    host_name: 'PalMaster_隊長',
    host_discord: 'palmaster#2026',
    max_players: 4,
    note: '歡迎一起抓帕魯！需要更新到最新連線修復補丁。',
    created_at: Math.floor(Date.now() / 1000) - 300,
    members: [
      {
        id: 'host_p1',
        name: 'PalMaster_隊長',
        discord: 'palmaster#2026',
        avatar_url: '',
        is_host: true,
        status: '就緒',
        progress: 100,
        steam_installed: true,
        version_status: '最新'
      },
      {
        id: 'me_p2',
        name: '您 (新手冒險者)',
        discord: '',
        avatar_url: '',
        is_host: false,
        status: '未下載',
        progress: 0,
        steam_installed: false,
        version_status: '未安裝'
      },
      {
        id: 'member_p3',
        name: '隊員小花',
        discord: 'flower#1234',
        avatar_url: '',
        is_host: false,
        status: '就緒',
        progress: 100,
        steam_installed: true,
        version_status: '最新'
      }
    ]
  };

  /**
   * 在大廳注入示範房間卡片
   */
  function injectMockLobbyRoom() {
    window.__tutorialMockPartyActive = true;

    // 確保回到大廳視圖
    var lobbyView = document.getElementById('party-lobby-view');
    var roomView = document.getElementById('party-room-view');
    var navRoom = document.getElementById('party-nav-my-room') || document.getElementById('party-nav-room');
    var navLobby = document.getElementById('party-nav-lobby');

    if (navLobby) navLobby.classList.add('active');
    if (navRoom) navRoom.classList.remove('active');

    if (lobbyView) { lobbyView.style.display = 'flex'; lobbyView.classList.add('active'); }
    if (roomView) { roomView.style.display = 'none'; roomView.classList.remove('active'); }

    var container = document.getElementById('party-rooms-container');
    if (!container) return;

    if (_origRoomsGridHTML === null) {
      _origRoomsGridHTML = container.innerHTML;
    }

    function doMockJoin(e) {
      if (e) {
        e.preventDefault();
        e.stopPropagation();
      }
      if (typeof tt === 'function') tt('🎉 成功申請加入房間 PAL886！', 'ok');
      try {
        injectMockRoomDetailView();
      } catch(err) {
        console.warn('[TutorialMock] injectMockRoomDetailView error:', err);
      }
      setTimeout(function() {
        if (window.TutorialEngine) window.TutorialEngine.next();
      }, 100);
    }

    var existingCard = document.getElementById('tutorial-mock-room-card');
    if (existingCard) {
      var existingBtn = document.getElementById('tutorial-btn-join-mock');
      if (existingBtn) existingBtn.onclick = doMockJoin;
      existingCard.onclick = doMockJoin;
      return;
    }

    container.innerHTML = `
      <div class="party-room-card tutorial-mock-room" id="tutorial-mock-room-card" style="border: 2px solid var(--cyan, #00E5FF); box-shadow: 0 0 24px rgba(0,229,255,0.4); max-width: 340px; cursor: pointer; transition: all 0.3s ease;">
        <div class="party-card-cover-wrap">
          <img src="https://cdn.cloudflare.steamstatic.com/steam/apps/1623730/header.jpg" class="party-card-cover" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
          <div class="party-card-cover-fallback" style="display:none">🎮</div>
          <div class="party-card-badge-id">#PAL886</div>
          <div class="party-card-badge-players">👥 2 / 4</div>
        </div>
        <div class="party-card-body">
          <div class="party-card-game-title" title="幻獸帕魯 (Palworld) - 週末同樂團" style="font-weight:800;font-size:14px">
            幻獸帕魯 (Palworld) - 週末同樂團
          </div>
          <div class="party-card-host-row" style="font-size:12px">
            <span class="host-label" style="opacity:0.8">👑 房主：</span>
            <span class="host-name" style="font-weight:700">PalMaster_隊長</span>
          </div>
          <div class="party-room-card-note" style="font-size:11.5px;line-height:1.4">
            📝 歡迎一起抓帕魯！需要更新最新連線補丁。
          </div>
        </div>
        <div class="party-card-footer" style="padding:10px 14px 14px 14px">
          <button class="btn btn-p btn-s party-join-btn tutorial-btn-simulating" id="tutorial-btn-join-mock" style="width:100%;font-weight:800;letter-spacing:0.5px;box-shadow:0 0 12px rgba(233,30,99,0.35);cursor:pointer">
            👉 點擊模擬申請加入
          </button>
        </div>
      </div>
    `;

    var cardEl = document.getElementById('tutorial-mock-room-card');
    var joinBtn = document.getElementById('tutorial-btn-join-mock');

    if (joinBtn) joinBtn.onclick = doMockJoin;
    if (cardEl) cardEl.onclick = doMockJoin;
  }

  /**
   * 進入房間視圖並調用真實 renderRoomView 渲染真實隊員清單
   */
  function injectMockRoomDetailView() {
    window.__tutorialMockPartyActive = true;
    try {

    var myName = (window._partyProfile && window._partyProfile.player_name) || '您 (新手冒險者)';
    var myId = (window._partyProfile && window._partyProfile.client_id) || 'me_p2';
    var mockData = JSON.parse(JSON.stringify(_mockJoinRoomData));
    if (mockData.members && mockData.members[1]) {
      mockData.members[1].name = myName;
      mockData.members[1].id = myId;
    }
    window._partyCurRoom = mockData;

    // 🌟 強制切換真實視圖容器：隱藏大廳，顯示房間檢視
    var lobbyView = document.getElementById('party-lobby-view');
    var roomView = document.getElementById('party-room-view');
    if (lobbyView) {
      lobbyView.style.display = 'none';
      lobbyView.classList.remove('active');
    }
    if (roomView) {
      roomView.style.display = 'flex';
      roomView.classList.add('active');
    }

    // 切換導覽列標籤狀態
    var navRoom = document.getElementById('party-nav-my-room') || document.getElementById('party-nav-room');
    var navLobby = document.getElementById('party-nav-lobby');
    if (navLobby) navLobby.classList.remove('active');
    if (navRoom) {
      navRoom.classList.add('active');
      navRoom.style.display = 'flex';
      var badge = navRoom.querySelector('.nav-badge');
      if (badge) badge.textContent = '3';
    }

    // 調用系統真實的 renderRoomView 渲染完整房間與成員清單
    if (typeof window.renderRoomView === 'function') {
      window.renderRoomView(window._partyCurRoom);
    }

    // 隊員端一鍵安裝按鈕容器保證顯示
    var syncBtnWrap = document.getElementById('party-sync-btn-wrap');
    if (syncBtnWrap) syncBtnWrap.style.display = 'block';
    } catch(err) {
      console.warn('[TutorialMock] injectMockRoomDetailView error:', err);
    }
  }

  /**
   * 模擬 3 秒真實一鍵安裝與同步進度推進 (0% -> 100% 平滑流暢 60 幀)
   */
  function simulateMockInstallSync3s(callback) {
    var syncBtn = document.getElementById('party-btn-start-sync');
    var progressBar = document.getElementById('party-my-progress-bar-inner');
    var progressPct = document.getElementById('party-my-progress-pct');
    var progressStage = document.getElementById('party-my-progress-stage');
    var myStatusBadge = document.getElementById('party-my-status-badge');
    var allReadyBanner = document.getElementById('party-all-ready-banner');

    if (syncBtn) {
      syncBtn.disabled = true;
      syncBtn.classList.remove('tutorial-btn-simulating');
      syncBtn.innerHTML = '<span class="spinner" style="width:12px;height:12px;display:inline-block;margin-right:4px"></span> 正在一鍵安裝中…';
    }

    var startTime = Date.now();
    var duration = 3000; // 3 秒

    var timer = setInterval(function() {
      var elapsed = Date.now() - startTime;
      var ratio = Math.min(1, elapsed / duration);
      var current = Math.floor(ratio * 100);

      // 階段描述文字
      var stageText = '';
      if (current < 20) {
        stageText = '🔍 正在比對房主補丁版本宣告與 SHA-256…';
      } else if (current < 55) {
        stageText = '⚡ 直連 Discord 高速 CDN 下載連線修復整合包 (' + current + '%)…';
      } else if (current < 85) {
        stageText = '📦 正在自動解壓縮並精準覆蓋至 Steam 遊戲目錄 (' + current + '%)…';
      } else if (current < 100) {
        stageText = '🛡️ 正在校對聯機設定檔與 SteamClient 虛擬連線端口…';
      } else {
        stageText = '✅ 遊戲補丁與聯機環境已完全就緒 (100%)';
      }

      // 更新下方進度條
      if (progressBar) {
        progressBar.style.width = current + '%';
        progressBar.className = current === 100 ? 'party-my-progress-bar-inner ready' : 'party-my-progress-bar-inner active';
      }
      if (progressPct) progressPct.textContent = current + '%';
      if (progressStage) {
        progressStage.innerHTML = '<span style="color:' + (current === 100 ? '#4CAF50' : 'var(--p)') + '">' + stageText + '</span>';
      }

      // 更新本機狀態標籤
      if (myStatusBadge) {
        myStatusBadge.textContent = current === 100 ? '已就緒' : ('下載中 (' + current + '%)');
        myStatusBadge.className = 'my-status-badge ' + (current === 100 ? 'ready' : 'downloading');
      }

      // 同步更新隊伍名單中「您」的進度（局部更新 DOM，杜絕重繪閃爍）
      var myCard = document.querySelector('.party-member-card.is-me');
      if (myCard) {
        var myOuterBar = myCard.querySelector('.member-progress-bar');
        if (myOuterBar) {
          myOuterBar.style.width = current + '%';
          myOuterBar.className = 'member-progress-bar ' + (current === 100 ? 'ready' : 'downloading');
        }
        var myInlineBar = myCard.querySelector('.member-inline-progress-bar');
        if (myInlineBar) {
          myInlineBar.style.width = current + '%';
          myInlineBar.className = 'member-inline-progress-bar ' + (current === 100 ? 'ready' : 'downloading');
        }
        var myInlinePct = myCard.querySelector('.member-inline-progress-pct');
        if (myInlinePct) myInlinePct.textContent = current + '%';
        var myStatusText = myCard.querySelector('.member-status-text');
        if (myStatusText) {
          myStatusText.textContent = current === 100 ? '下載狀況(就緒)' : ('下載狀況(下載中: ' + current + '%)');
          myStatusText.className = 'member-status-text ' + (current === 100 ? 'status-ready' : 'status-downloading');
        }
      }

      // 更新全域 mock 數據
      if (window._partyCurRoom && window._partyCurRoom.members) {
        var me = window._partyCurRoom.members.find(function(m) { return m.id === 'me_p2'; });
        if (me) {
          me.progress = current;
          me.status = current === 100 ? '就緒' : '下載中';
          me.version_status = current === 100 ? '最新' : '更新中';
        }
      }

      if (ratio >= 1) {
        clearInterval(timer);
        if (syncBtn) {
          syncBtn.disabled = true;
          syncBtn.innerHTML = '✔ 已完成同步';
          syncBtn.className = 'btn btn-s ok';
        }
        if (allReadyBanner) {
          allReadyBanner.style.display = 'flex';
          allReadyBanner.classList.add('pulse');
        }
        if (typeof tt === 'function') tt('🎉 模擬安裝完成！您已全速達到 100% 就緒', 'ok');
        if (typeof callback === 'function') callback();
      }
    }, 50); // 每 50ms 推進一次，3 秒共 60 幀平滑奔馳
  }

  /**
   * 清理沙盒資料還原大廳
   */
  function cleanupJoinTutorialSandbox() {
    window.__tutorialMockPartyActive = false;
    window._partyCurRoom = null;
    var container = document.getElementById('party-rooms-container');
    if (container && _origRoomsGridHTML !== null) {
      container.innerHTML = _origRoomsGridHTML;
      _origRoomsGridHTML = null;
    }

    var quickJoinWrap = document.querySelector('.party-quick-join-wrap');
    var quickBtn = quickJoinWrap ? quickJoinWrap.querySelector('button') : null;
    if (quickBtn && quickBtn._tutorialQuickHandler) {
      quickBtn.removeEventListener('click', quickBtn._tutorialQuickHandler, true);
      delete quickBtn._tutorialQuickHandler;
    }

    var centralModal = document.getElementById('modal-party-member-completion-central');
    if (centralModal) centralModal.remove();

    var roomView = document.getElementById('party-room-view');
    var lobbyView = document.getElementById('party-lobby-view');
    if (roomView) {
      roomView.style.display = 'none';
      roomView.classList.remove('active');
    }
    if (lobbyView) {
      lobbyView.style.display = 'flex';
      lobbyView.classList.add('active');
    }

    var navLobby = document.getElementById('party-nav-lobby');
    var navRoom = document.getElementById('party-nav-my-room') || document.getElementById('party-nav-room');
    if (navLobby) navLobby.classList.add('active');
    if (navRoom) {
      navRoom.classList.remove('active');
      navRoom.style.display = 'none';
    }

    // 🌟 核心清理：徹底清除大廳模擬輸入之搜尋文字與邀請代碼
    var searchInput = document.getElementById('party-search-input');
    if (searchInput) {
      searchInput.value = '';
      try {
        searchInput.dispatchEvent(new Event('input', { bubbles: true }));
        searchInput.dispatchEvent(new Event('change', { bubbles: true }));
      } catch(e){}
    }

    var quickCodeInput = document.getElementById('party-quick-code');
    if (quickCodeInput) {
      quickCodeInput.value = '';
      try {
        quickCodeInput.dispatchEvent(new Event('input', { bubbles: true }));
        quickCodeInput.dispatchEvent(new Event('change', { bubbles: true }));
      } catch(e){}
    }

    if (typeof window.switchPartyNav === 'function') {
      window.switchPartyNav('lobby');
    }
    if (typeof window.refreshPartyLobby === 'function') {
      window.refreshPartyLobby(false);
    }
  }

  // 🌟 入隊同樂專屬結業慶祝彈窗（1:1 比照獨狼與線上補丁字卡樣式）
  function showPartyJoinCompletionModal() {
    var oldModals = document.querySelectorAll('.tutorial-completion-modal-wrap');
    oldModals.forEach(function(m) {
      try { m.remove(); } catch(e){}
    });

    var modal = document.createElement('div');
    modal.className = 'tutorial-sandbox-modal-wrap tutorial-completion-modal-wrap';
    modal.id = 'tutorial-party-join-complete-modal';
    modal.innerHTML = `
      <div class="tutorial-sandbox-modal-card tutorial-completion-modal-card" style="text-align:center;padding:28px 24px">
        <div style="font-size:46px;margin-bottom:8px">📥🎉</div>
        <h2 class="tutorial-completion-title" style="margin:0 0 10px 0;font-size:20px;font-weight:900">組隊入隊教學 圓滿完成！</h2>
        <p class="tutorial-completion-desc" style="font-size:13px;line-height:1.65;margin:0 0 20px 0">
          太棒了！您已經完整掌握了<strong>「房間即時搜尋」</strong>、<strong>「邀請代碼快速直達」</strong>、<strong>「一鍵補丁安裝與自動同步」</strong>以及<strong>「全員就緒與語音連線」</strong>的全部核心操作。<br>
          現在，您可以隨時在大廳尋找志同道合的隊友房間，一鍵對齊版本，輕鬆暢享多人聯機同樂！
        </p>
        <div style="display:flex;justify-content:center;gap:12px">
          <button class="btn btn-o btn-s" id="btn-party-join-finish-back" type="button">🎓 返回教學首頁</button>
          <button class="btn btn-p btn-s" id="btn-party-join-finish-lobby" type="button" style="font-weight:700">👥 前往組隊大廳</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    modal.style.display = 'flex';

    var btnBack = modal.querySelector('#btn-party-join-finish-back');
    var btnLobby = modal.querySelector('#btn-party-join-finish-lobby');

    if (btnBack) {
      btnBack.onclick = function(e) {
        if (e) { e.preventDefault(); e.stopPropagation(); }
        if (typeof window.playTutorialSound === 'function') {
          window.playTutorialSound('step');
        }
        document.querySelectorAll('.tutorial-completion-modal-wrap').forEach(function(m) {
          try { m.remove(); } catch(err){}
        });
        try { cleanupJoinTutorialSandbox(); } catch(err){}
        try {
          if (typeof window.cleanupAllTutorialSandbox === 'function') {
            window.cleanupAllTutorialSandbox();
          }
        } catch(err){}

        // 確保關閉所有教學遮罩與聚光燈
        var overlay = document.getElementById('tutorial-spotlight-overlay');
        if (overlay) overlay.classList.add('hidden');
        var popover = document.getElementById('tutorial-step-popover');
        if (popover) popover.classList.add('hidden');
        document.body.classList.remove('tutorial-active-mode');

        if (typeof window.switchPage === 'function') {
          window.switchPage('tutorial');
        }
      };
    }

    if (btnLobby) {
      btnLobby.onclick = function(e) {
        if (e) { e.preventDefault(); e.stopPropagation(); }
        if (typeof window.playTutorialSound === 'function') {
          window.playTutorialSound('step');
        }
        document.querySelectorAll('.tutorial-completion-modal-wrap').forEach(function(m) {
          try { m.remove(); } catch(err){}
        });
        try { cleanupJoinTutorialSandbox(); } catch(err){}
        try {
          if (typeof window.cleanupAllTutorialSandbox === 'function') {
            window.cleanupAllTutorialSandbox();
          }
        } catch(err){}

        // 確保關閉所有教學遮罩與聚光燈
        var overlay = document.getElementById('tutorial-spotlight-overlay');
        if (overlay) overlay.classList.add('hidden');
        var popover = document.getElementById('tutorial-step-popover');
        if (popover) popover.classList.add('hidden');
        document.body.classList.remove('tutorial-active-mode');

        if (typeof window.switchPage === 'function') {
          window.switchPage('party');
        }
      };
    }
  }

  var partyJoinSteps = [
    // 🌟 步驟 1 / 11：大廳即時搜尋（單元 1：大廳探索與房間加入）
    {
      roleBadge: '📥 組隊同樂・隊員篇',
      moduleTitle: '單元 1：大廳探索與房間加入',
      page: 'party',
      target: '#party-search-input',
      title: '即時搜尋遊戲與房間',
      desc: '在頂部搜尋欄輸入遊戲名稱（如「帕魯」、「Elden Ring」）、房間號碼或房主名稱，大廳會即時為您過濾出符合條件的公開房間，快速找到心儀隊伍！',
      hint: '支援中文、英文與 AppID 模糊比對。',
      placement: 'bottom',
      onEnter: function() {
        injectMockLobbyRoom();
        var input = document.getElementById('party-search-input');
        if (input && window.TutorialEngine) {
          window.TutorialEngine.simulateTyping(input, '帕魯', {}, function(){});
        }
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },
    // 🌟 步驟 2 / 11：邀請代碼快速直達（支援輸入與點擊「加入房間」按鈕直接進入）
    {
      roleBadge: '📥 組隊同樂・隊員篇',
      moduleTitle: '單元 1：大廳探索與房間加入',
      page: 'party',
      target: '.party-quick-join-wrap',
      title: '輸入好友邀請碼直達房間',
      desc: '若好友已在 Discord 或私訊發送專屬房間代碼（如 PAL886），直接在右側輸入框填入代碼並點擊「加入房間」，即可瞬間直達好友的專屬房間，省去翻找列表的時間！',
      hint: '房號為 6 ~ 8 位英數代碼，不分大小寫。',
      placement: 'bottom',
      onEnter: function() {
        injectMockLobbyRoom();
        var codeInput = document.getElementById('party-quick-code');
        if (codeInput && window.TutorialEngine) {
          window.TutorialEngine.simulateTyping(codeInput, 'PAL886', {}, function(){});
        }
        var quickJoinWrap = document.querySelector('.party-quick-join-wrap');
        var quickBtn = quickJoinWrap ? quickJoinWrap.querySelector('button') : null;
        if (quickBtn) {
          var onQuickClick = function(e) {
            if (e) {
              e.preventDefault();
              e.stopPropagation();
            }
            quickBtn.removeEventListener('click', onQuickClick, true);
            delete quickBtn._tutorialQuickHandler;
            if (typeof tt === 'function') tt('🎉 成功透過邀請碼加入房間 PAL886！', 'ok');
            injectMockRoomDetailView();
            setTimeout(function() {
              if (window.TutorialEngine) {
                window.TutorialEngine.next();
              }
            }, 120);
          };
          quickBtn._tutorialQuickHandler = onQuickClick;
          quickBtn.addEventListener('click', onQuickClick, true);
        }
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      },
      onLeave: function() {
        var quickJoinWrap = document.querySelector('.party-quick-join-wrap');
        var quickBtn = quickJoinWrap ? quickJoinWrap.querySelector('button') : null;
        if (quickBtn && quickBtn._tutorialQuickHandler) {
          quickBtn.removeEventListener('click', quickBtn._tutorialQuickHandler, true);
          delete quickBtn._tutorialQuickHandler;
        }
      }
    },
    // 🌟 步驟 3 / 11：大廳示範房間模擬加入 (需求 1：正確引導點擊申請，讓下一步無法被觸發)
    {
      roleBadge: '📥 組隊同樂・隊員篇',
      moduleTitle: '單元 1：大廳探索與房間加入',
      page: 'party',
      target: '#tutorial-btn-join-mock, #tutorial-mock-room-card',
      title: '點選示範房間申請加入',
      desc: '這是為您準備的教學示範房間【幻獸帕魯 - 週末同樂團】！卡片清楚展示遊戲封面、房號、當前人數與房主公告。請親自點擊卡片下方的<strong>「👉 點擊模擬申請加入」</strong>按鈕進入房間！',
      hint: '請親自點擊亮起的「👉 點擊模擬申請加入」按鈕，無法直接點擊下一步！',
      disableNext: true,
      placement: 'right',
      onEnter: function() {
        injectMockLobbyRoom();
        var joinBtn = document.getElementById('tutorial-btn-join-mock');
        if (joinBtn) {
          joinBtn.classList.add('tutorial-btn-simulating');
          var onJoinClick = function(e) {
            if (e) {
              e.preventDefault();
              e.stopPropagation();
            }
            joinBtn.removeEventListener('click', onJoinClick, true);
            joinBtn.classList.remove('tutorial-btn-simulating');
            if (typeof tt === 'function') tt('🎉 成功申請加入房間 PAL886！', 'ok');
            injectMockRoomDetailView();
            setTimeout(function() {
              if (window.TutorialEngine) window.TutorialEngine.next();
            }, 120);
          };
          joinBtn.addEventListener('click', onJoinClick, true);
        }
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },
    // 🌟 步驟 4 / 11：進入房間視圖，確認房號與連線代碼
    {
      roleBadge: '📥 組隊同樂・隊員篇',
      moduleTitle: '單元 2：狀態比對與模擬安裝',
      page: 'party',
      target: '.party-room-header-card, .party-room-code-pill',
      title: '進入房間與確認連線代碼',
      desc: '入隊後，頂部會顯示房號（如 PAL886）與遊戲名稱。點擊房號旁的 📋 圖示可一鍵複製房號，隨時轉發給其他想一起同樂的好友。',
      hint: '房間人數與房主公告會在此即時更新。',
      placement: 'bottom',
      onEnter: function() {
        injectMockRoomDetailView();
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },
    // 🌟 步驟 5 / 11：隊伍成員補丁狀態檢視
    {
      roleBadge: '📥 組隊同樂・隊員篇',
      moduleTitle: '單元 2：狀態比對與模擬安裝',
      page: 'party',
      target: '.party-members-section, #party-members-list',
      title: '隊伍成員補丁狀態檢視',
      desc: '隊伍名單每 3 秒自動同步全體成員的進度。系統會自動比對您與房主的補丁版本，此時顯示您的狀態為「⚡ 補丁未同步」。',
      hint: '房主會在此監控全體隊員是否皆已就緒。',
      placement: 'top',
      onEnter: function() {
        injectMockRoomDetailView();
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },
    // 🌟 步驟 6 / 11：模擬一鍵安裝 (需求 2：一進到步驟呈現「點擊模擬安裝」字樣，絕不顯示「正在一鍵安裝中」)
    {
      roleBadge: '📥 組隊同樂・隊員篇',
      moduleTitle: '單元 2：狀態比對與模擬安裝',
      page: 'party',
      target: '#party-btn-start-sync',
      title: '一鍵安裝與自動版本同步',
      desc: '系統已為您鎖定房主所分發的補丁版本。請親自點擊下方的<strong>「🚀 點擊模擬安裝」</strong>按鈕，體驗自動下載並對齊版本的完整流程！',
      disableNext: true,
      hint: '請親自點擊下方亮起的「🚀 點擊模擬安裝」按鈕開始同步！',
      placement: 'top',
      onEnter: function() {
        injectMockRoomDetailView();
        var syncWrap = document.getElementById('party-sync-btn-wrap');
        if (syncWrap) syncWrap.style.display = 'block';

        var syncBtn = document.getElementById('party-btn-start-sync');
        if (syncBtn) {
          syncBtn.disabled = false;
          syncBtn.classList.remove('disabled');
          syncBtn.className = 'btn btn-party-install tutorial-btn-simulating';
          syncBtn.innerHTML = '🚀 點擊模擬安裝';
          syncBtn.style.cursor = 'pointer';

          var onSyncClick = function(e) {
            if (e) {
              e.preventDefault();
              e.stopPropagation();
            }
            syncBtn.removeEventListener('click', onSyncClick);
            syncBtn.classList.remove('tutorial-btn-simulating');
            if (typeof tt === 'function') tt('🚀 已觸發模擬安裝流程！正在同步房主版本…', 'info');
            if (window.TutorialEngine) window.TutorialEngine.next();
          };
          syncBtn.addEventListener('click', onSyncClick);
        }
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },
    // 🌟 步驟 7 / 11：3 秒平滑進度推進模擬 (需求 3：0~100 模擬進度，僅用 3 秒呈現)
    {
      roleBadge: '📥 組隊同樂・隊員篇',
      moduleTitle: '單元 2：狀態比對與模擬安裝',
      page: 'party',
      target: '#party-my-progress-container, #party-members-list',
      title: '即時下載進度與檔案比對',
      desc: '系統正透過高速 CDN 自動下載補丁並部署至 Steam 目錄。請觀察下方進度條與成員清單中您的狀態，正以 3 秒極速由「0%」動態推進至「100% 已就緒」！',
      disableNext: true,
      hint: '正在執行 3 秒極速下載與自動校對模擬 (0% ~ 100%)…',
      placement: 'top',
      onEnter: function() {
        injectMockRoomDetailView();
        simulateMockInstallSync3s(function() {
          setTimeout(function() {
            if (window.TutorialEngine) window.TutorialEngine.next();
          }, 800);
        });
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },
    // 🌟 步驟 8 / 11：雲端無伺服器與 Discord CDN 傳輸架構解說 (需求 4：拆分步驟完整講述當前架構)
    {
      roleBadge: '📥 組隊同樂・隊員篇',
      moduleTitle: '單元 3：雲端架構與連線廣播接收',
      page: 'party',
      target: '#party-all-ready-banner',
      title: '🌐 邊緣無伺服器與 Discord CDN 託管架構',
      desc: '【SMU 極速連線架構解密】：組隊大廳採用 <strong>Cloudflare Workers + Turso</strong> 邊緣雲端網絡，提供高可用且零延遲的大廳廣播；補丁傳輸則透過房主的 Discord Webhook 託管於 <strong>Discord 官方高速全球 CDN</strong>！隊員在剛才的 3 秒模擬中，便是直連 Discord CDN 秒級同步補丁，完全無須房主自架伺服器或負擔傳輸頻寬！',
      hint: '點擊「下一步」，了解全員就緒後隊伍運作機制！',
      placement: 'bottom',
      onEnter: function() {
        injectMockRoomDetailView();
        var banner = document.getElementById('party-all-ready-banner');
        if (banner) banner.style.display = 'flex';
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },
    // 🌟 步驟 9 / 11：全員就緒後的房長操作與隊員等待機制 (需求 5：符合現行開房架構，不再講 30 秒陳舊描述，講述房長做什麼與隊員等待什麼)
    {
      roleBadge: '📥 組隊同樂・隊員篇',
      moduleTitle: '單元 3：雲端架構與連線廣播接收',
      page: 'party',
      target: '#party-all-ready-banner',
      title: '⏳ 房長緩衝確認與隊員等待機制',
      desc: '【隊伍組建完成後的真實運作】：<br>• <strong>房長在做什麼？</strong> 系統會給予房長 1 分鐘緩衝倒數，供房長確認全員語音是否進麥（可按需延遲 5 分鐘最多 2 次），並一鍵發布語音頻道連結或連線 IP。<br>• <strong>隊員需要做什麼？</strong> 隊員完全無須手動刷新！SMU 會在背景每 0.5 秒輕量輪詢房長廣播；一旦房長發布指令，系統將瞬間在您的螢幕中央彈出開拔通知！',
      hint: '點擊「下一步」，親自演練接收房長發布的連線資訊！',
      placement: 'bottom',
      onEnter: function() {
        injectMockRoomDetailView();
        var banner = document.getElementById('party-all-ready-banner');
        if (banner) banner.style.display = 'flex';
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },
    // 🌟 步驟 10 / 11：真實模擬！接收房長開拔廣播卡片 (需求 4 & 5：模擬 SMU 真實會收到的資訊與一鍵複製)
    {
      roleBadge: '📥 組隊同樂・隊員篇',
      moduleTitle: '單元 3：雲端架構與連線廣播接收',
      page: 'party',
      target: '#modal-party-member-completion-central .party-central-completion-card',
      title: '📢 接收房長連線廣播與一鍵複製',
      desc: '【真實連線廣播降臨】！房長已正式發送連線指示！此時在所有隊員的螢幕正中央，都會同步彈出這張完成卡片。您可以點擊「📋 一鍵複製」快速取得房長的語音頻道或連線密碼，全隊進麥一同啟動 Steam 遊戲連線！請點擊下方的「👥 返回組隊大廳」按鈕！',
      hint: '請親自點擊中央卡片中的「👥 返回組隊大廳」按鈕！',
      disableNext: true,
      placement: 'right',
      offsetX: 14,
      onEnter: function() {
        if (typeof window.showPartyMemberCompletionCentralModal === 'function') {
          window.showPartyMemberCompletionCentralModal('PalMaster_隊長', 'palmaster#2026', '+dc: pal_voice_room_01 / 語音頻道已開，密碼 886');
        }
        var centralModal = document.getElementById('modal-party-member-completion-central');
        if (centralModal) {
          var closeBtn = centralModal.querySelector('.party-completion-btn-close');
          if (closeBtn) {
            closeBtn.classList.add('tutorial-btn-simulating');
            var onCloseClick = function(e) {
              if (e) {
                e.preventDefault();
                e.stopPropagation();
              }
              closeBtn.removeEventListener('click', onCloseClick, true);
              closeBtn.classList.remove('tutorial-btn-simulating');
              centralModal.remove();

              // 模擬返回大廳
              window._partyCurRoom = null;
              var lobbyView = document.getElementById('party-lobby-view');
              var roomView = document.getElementById('party-room-view');
              if (roomView) { roomView.style.display = 'none'; roomView.classList.remove('active'); }
              if (lobbyView) { lobbyView.style.display = 'flex'; lobbyView.classList.add('active'); }

              var navLobby = document.getElementById('party-nav-lobby');
              var navRoom = document.getElementById('party-nav-my-room') || document.getElementById('party-nav-room');
              if (navLobby) navLobby.classList.add('active');
              if (navRoom) { navRoom.classList.remove('active'); navRoom.style.display = 'none'; }

              if (typeof tt === 'function') tt('🚪 已安全返回組隊大廳！', 'ok');

              setTimeout(function() {
                if (window.TutorialEngine) window.TutorialEngine.next();
              }, 180);
            };
            closeBtn.addEventListener('click', onCloseClick, true);
          }
        }
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },
    // 🌟 步驟 11 / 11：房間生命週期收尾與結業祝賀
    {
      roleBadge: '📥 組隊同樂・隊員篇',
      moduleTitle: '單元 3：雲端架構與連線廣播接收',
      page: 'party',
      target: '#party-nav-lobby, .party-header-bar, #party-lobby-view',
      title: '🏁 房間生命週期圓滿結束',
      desc: '恭喜！房間在房長廣播完成後已功成身退，自動從雲端大廳解散下架，釋放伺服器資源。全隊成員電腦中的補丁皆妥善留存在 Steam 目錄，隨時可以暢玩！',
      hint: '點擊「完成教學 🎉」即可領取隊員結業證書！',
      placement: 'bottom',
      onEnter: function() {
        var centralModal = document.getElementById('modal-party-member-completion-central');
        if (centralModal) centralModal.remove();
        var lobbyView = document.getElementById('party-lobby-view');
        var roomView = document.getElementById('party-room-view');
        if (roomView) { roomView.style.display = 'none'; roomView.classList.remove('active'); }
        if (lobbyView) { lobbyView.style.display = 'flex'; lobbyView.classList.add('active'); }
        var navLobby = document.getElementById('party-nav-lobby');
        var navRoom = document.getElementById('party-nav-my-room') || document.getElementById('party-nav-room');
        if (navLobby) navLobby.classList.add('active');
        if (navRoom) { navRoom.classList.remove('active'); navRoom.style.display = 'none'; }
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      },
      onLeave: function() {
        cleanupJoinTutorialSandbox();
        showPartyJoinCompletionModal();
      }
    }
  ];

  if (window.TutorialEngine) {
    window.TutorialEngine.registerModule('party_join_guide', {
      name: '組隊入隊引導',
      steps: partyJoinSteps,
      cleanup: cleanupJoinTutorialSandbox,
      showCompletionModal: showPartyJoinCompletionModal
    });
  }

})(window);
