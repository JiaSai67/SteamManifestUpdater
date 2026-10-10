/**
 * 教學模組：組隊入隊引導 (Party Join Tutorial Steps - 旗艦完整版)
 * 職責：
 * 步驟 1：高亮左側主導航列第 3 個「👥 組隊大廳」按鈕
 * 步驟 2：大廳即時搜尋（遊戲名稱、房號、房主模糊搜尋）
 * 步驟 3：邀請代碼快速加入（輸入 6~8 碼房間邀請碼一鍵直達）
 * 步驟 4：大廳示範房間卡片模擬點選加入
 * 步驟 5：進入房間視圖，確認房號【PAL886】與遊戲資訊
 * 步驟 6：真實模擬房間隊員名單結構與版本狀態比對
 * 步驟 7：學員親自點擊「🚀 一鍵安裝」按鈕觸發同步
 * 步驟 8：3 秒即時下載、校對與進度條推進模擬 (0% -> 100%)
 * 步驟 9：全員就緒與房主連線資訊廣播說明
 * 步驟 10：發車倒數、房間生命週期與解散機制完整教學，並彈出結業圓滿完成字卡
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
    var navRoom = document.getElementById('party-nav-room');
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

    var existingCard = document.getElementById('tutorial-mock-room-card');
    if (existingCard) return;

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
          <button class="btn btn-p btn-s party-join-btn" id="tutorial-btn-join-mock" style="width:100%;font-weight:800;letter-spacing:0.5px;box-shadow:0 0 12px rgba(233,30,99,0.35)">
            👉 點擊模擬申請加入
          </button>
        </div>
      </div>
    `;

    var cardEl = document.getElementById('tutorial-mock-room-card');
    var joinBtn = document.getElementById('tutorial-btn-join-mock');

    function doMockJoin(e) {
      if (e) {
        e.preventDefault();
        e.stopPropagation();
      }
      if (typeof tt === 'function') tt('🎉 成功申請加入房間 PAL886！', 'ok');
      injectMockRoomDetailView();
      setTimeout(function() {
        if (window.TutorialEngine) window.TutorialEngine.next();
      }, 150);
    }

    if (joinBtn) joinBtn.addEventListener('click', doMockJoin);
    if (cardEl) cardEl.addEventListener('click', doMockJoin);
  }

  /**
   * 進入房間視圖並調用真實 renderRoomView 渲染真實隊員清單
   */
  function injectMockRoomDetailView() {
    window.__tutorialMockPartyActive = true;
    window._partyCurRoom = JSON.parse(JSON.stringify(_mockJoinRoomData));

    // 切換導覽列狀態
    var navRoom = document.getElementById('party-nav-room');
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
    } else {
      var lobbyView = document.getElementById('party-lobby-view');
      var roomView = document.getElementById('party-room-view');
      if (lobbyView) { lobbyView.style.display = 'none'; lobbyView.classList.remove('active'); }
      if (roomView) { roomView.style.display = 'flex'; roomView.classList.add('active'); }
    }
  }

  /**
   * 模擬 3 秒真實一鍵安裝與同步進度推進 (0% -> 100%)
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
      syncBtn.innerHTML = '<span class="spinner" style="width:12px;height:12px;display:inline-block;margin-right:4px"></span> 正在一鍵安裝中…';
    }

    var current = 0;
    var stages = [
      { pct: 15, text: '🔍 正在比對房主補丁版本宣告與 SHA-256…' },
      { pct: 35, text: '⚡ 高速 CDN 下載連線修復補丁包 (35%)…' },
      { pct: 60, text: '📦 下載完成，正在自動解壓縮並覆蓋至 Steam 目錄…' },
      { pct: 85, text: '🛡️ 正在校對聯機設定檔與 SteamClient 端口…' },
      { pct: 100, text: '✅ 遊戲與聯機環境已完全就緒 (100%)' }
    ];
    var stageIdx = 0;

    var timer = setInterval(function() {
      if (stageIdx < stages.length) {
        var s = stages[stageIdx];
        current = s.pct;

        if (progressBar) {
          progressBar.style.width = current + '%';
          progressBar.className = current === 100 ? 'party-my-progress-bar-inner ready' : 'party-my-progress-bar-inner active';
        }
        if (progressPct) progressPct.textContent = current + '%';
        if (progressStage) progressStage.innerHTML = '<span style="color:' + (current === 100 ? '#4CAF50' : 'var(--p)') + '">' + s.text + '</span>';

        // 同步更新隊伍名單中「您」的即時進度
        if (window._partyCurRoom && window._partyCurRoom.members) {
          var me = window._partyCurRoom.members.find(function(m) { return m.id === 'me_p2'; });
          if (me) {
            me.progress = current;
            me.status = current === 100 ? '就緒' : '下載中';
            me.version_status = current === 100 ? '最新' : '更新中';
          }
          if (typeof window.renderRoomView === 'function') {
            window.renderRoomView(window._partyCurRoom);
          }
        }

        stageIdx++;
      } else {
        clearInterval(timer);
        if (myStatusBadge) {
          myStatusBadge.textContent = '已就緒 (100%)';
          myStatusBadge.className = 'my-status-badge ready';
        }
        if (syncBtn) {
          syncBtn.disabled = true;
          syncBtn.innerHTML = '✔ 已完成同步';
          syncBtn.className = 'btn btn-s ok';
        }
        if (allReadyBanner) {
          allReadyBanner.style.display = 'flex';
          allReadyBanner.classList.add('pulse');
        }
        if (typeof tt === 'function') tt('🎉 全員補丁版本已同步一致，全員就緒！', 'ok');
        if (typeof callback === 'function') callback();
      }
    }, 600); // 5 次步進，共計 3 秒完成
  }

  /**
   * 清理沙盒資料還原大廳
   */
  function cleanupJoinTutorialSandbox() {
    window.__tutorialMockPartyActive = false;
    var container = document.getElementById('party-rooms-container');
    if (container && _origRoomsGridHTML !== null) {
      container.innerHTML = _origRoomsGridHTML;
      _origRoomsGridHTML = null;
    }
    window._partyCurRoom = null;
    if (typeof window.switchPartyNav === 'function') {
      window.switchPartyNav('lobby');
    }
  }

  // 🌟 入隊同樂專屬結業慶祝彈窗（1:1 比照獨狼與線上補丁字卡樣式）
  function showPartyJoinCompletionModal() {
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
          <button class="btn btn-o btn-s" id="btn-party-join-finish-back">🎓 返回教學首頁</button>
          <button class="btn btn-p btn-s" id="btn-party-join-finish-lobby" style="font-weight:700">👥 前往組隊大廳</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    modal.style.display = 'flex';

    var btnBack = document.getElementById('btn-party-join-finish-back');
    var btnLobby = document.getElementById('btn-party-join-finish-lobby');

    if (btnBack) {
      btnBack.onclick = function() {
        modal.remove();
        cleanupJoinTutorialSandbox();
        if (typeof window.cleanupAllTutorialSandbox === 'function') {
          window.cleanupAllTutorialSandbox();
        }
        if (window.switchPage) window.switchPage('tutorial');
      };
    }

    if (btnLobby) {
      btnLobby.onclick = function() {
        modal.remove();
        cleanupJoinTutorialSandbox();
        if (typeof window.cleanupAllTutorialSandbox === 'function') {
          window.cleanupAllTutorialSandbox();
        }
        if (window.switchPage) window.switchPage('party');
      };
    }
  }

  var partyJoinSteps = [
    // 🌟 步驟 1：認識左側組隊大廳主導航 (精準高亮左側選單)
    {
      roleBadge: '📥 組隊同樂・隊員篇',
      moduleTitle: '單元 1：大廳探索與房間加入',
      page: 'party',
      target: '.sidebar button[data-p="party"]',
      title: '前往組隊同樂大廳',
      desc: '點擊左側主選單的「👥 組隊同樂」按鈕，即可進入全網雲端連線大廳，瀏覽所有玩家正在招募的組隊房間。',
      hint: '組隊大廳採用高可用無伺服器架構，支援自動對齊版本與極速一鍵安裝！',
      placement: 'right',
      onEnter: function() {
        injectMockLobbyRoom();
      }
    },
    // 🌟 步驟 2：大廳即時搜尋（需求 2：拆分搜尋與代碼）
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
    // 🌟 步驟 3：邀請代碼快速直達（需求 2：拆分搜尋與代碼）
    {
      roleBadge: '📥 組隊同樂・隊員篇',
      moduleTitle: '單元 1：大廳探索與房間加入',
      page: 'party',
      target: '#party-code-input, #btn-party-join-by-code',
      title: '輸入好友邀請碼直達房間',
      desc: '若好友已在 Discord 或私訊發送專屬房間代碼（如 PAL886），直接在右側輸入框填入代碼並點擊「加入房間」，即可瞬間直達好友的專屬房間，省去翻找列表的時間！',
      hint: '房號為 6 ~ 8 位英數代碼，不分大小寫。',
      placement: 'bottom',
      onEnter: function() {
        injectMockLobbyRoom();
        var codeInput = document.getElementById('party-code-input');
        if (codeInput && window.TutorialEngine) {
          window.TutorialEngine.simulateTyping(codeInput, 'PAL886', {}, function(){});
        }
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },
    // 🌟 步驟 4：大廳示範房間模擬加入 (保證示範卡片常駐)
    {
      roleBadge: '📥 組隊同樂・隊員篇',
      moduleTitle: '單元 1：大廳探索與房間加入',
      page: 'party',
      target: '#tutorial-mock-room-card',
      title: '點選示範房間申請加入',
      desc: '這是為您準備的教學示範房間【幻獸帕魯 - 週末同樂團】！卡片清楚展示遊戲封面、房號、當前人數與房主公告。請點擊卡片下方的「👉 點擊模擬申請加入」按鈕進入房間！',
      disableNext: true,
      placement: 'right',
      onEnter: function() {
        injectMockLobbyRoom();
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },
    // 🌟 步驟 5：進入房間視圖，確認房號與連線代碼 (真實房間渲染，防跳出)
    {
      roleBadge: '📥 組隊同樂・隊員篇',
      moduleTitle: '單元 2：狀態比對與一鍵安裝',
      page: 'party',
      target: '.party-room-header, .party-room-code-pill',
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
    // 🌟 步驟 6：隊伍成員補丁狀態檢視 (需求 2：真實隊員結構)
    {
      roleBadge: '📥 組隊同樂・隊員篇',
      moduleTitle: '單元 2：狀態比對與一鍵安裝',
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
    // 🌟 步驟 7：一鍵安裝與自動版本同步 (需求 3：學員親自點擊互動)
    {
      roleBadge: '📥 組隊同樂・隊員篇',
      moduleTitle: '單元 2：狀態比對與一鍵安裝',
      page: 'party',
      target: '#party-btn-start-sync',
      title: '一鍵安裝與自動版本同步',
      desc: '點擊下方的「🚀 一鍵安裝」按鈕，系統將自動比對並部署與房主完全相同的連線補丁，免去手動尋找補丁與覆蓋檔案的繁瑣流程！',
      disableNext: true,
      hint: '請親自點擊下方亮起的「🚀 一鍵安裝」按鈕開始同步！',
      placement: 'top',
      onEnter: function() {
        injectMockRoomDetailView();
        var syncBtn = document.getElementById('party-btn-start-sync');
        if (syncBtn) {
          syncBtn.disabled = false;
          var onSyncClick = function(e) {
            e.preventDefault();
            e.stopPropagation();
            syncBtn.removeEventListener('click', onSyncClick);
            if (typeof tt === 'function') tt('🚀 已觸發一鍵安裝流程！正在同步房主版本…', 'info');
            if (window.TutorialEngine) window.TutorialEngine.next();
          };
          syncBtn.addEventListener('click', onSyncClick);
        }
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },
    // 🌟 步驟 8：模擬 3 秒真實下載與同步進度 (需求 3：3 秒動態進度推進)
    {
      roleBadge: '📥 組隊同樂・隊員篇',
      moduleTitle: '單元 2：狀態比對與一鍵安裝',
      page: 'party',
      target: '#party-my-progress-container, #party-members-list',
      title: '即時下載進度與檔案比對',
      desc: '系統正透過高速 CDN 自動下載補丁並部署至 Steam 目錄。請觀察下方進度條與成員清單中您的狀態由「未下載」即時推進至「100% 已就緒」！',
      disableNext: true,
      hint: '正在執行 3 秒快速下載與自動校對模擬…',
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
    // 🌟 步驟 9：全員就緒與房主連線資訊廣播 (需求 4：多花步驟詳細說明)
    {
      roleBadge: '📥 組隊同樂・隊員篇',
      moduleTitle: '單元 2：狀態比對與一鍵安裝',
      page: 'party',
      target: '#party-all-ready-banner',
      title: '🎉 全員就緒！房主發布連線資訊',
      desc: '當所有成員皆達到 100% 後，頂部將點亮「全員就緒」橫幅！此時系統會自動彈出房主預填的聯絡資訊（如 Discord 語音頻道連結、連線 IP 或入房密碼），方便全隊即時溝通。',
      hint: '房長通常會在語音頻道中倒數，通知全體隊員同時啟動遊戲！',
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
    // 🌟 步驟 10：發車倒數、房間生命週期與解散機制 (需求 4：完整生命週期說明)
    {
      roleBadge: '📥 組隊同樂・隊員篇',
      moduleTitle: '單元 2：狀態比對與一鍵安裝',
      page: 'party',
      target: '.party-room-header-card, #party-btn-leave-or-close',
      title: '🚀 倒數發車與房間生命週期說明',
      desc: '在全員就緒後，房長可啟動 30 秒發車倒數。倒數結束或隊伍開玩後，房間會維持運行直到遊玩結束。若房長解散房間或離線，房間將自動關閉，隊員本機已同步的補丁仍會妥善保留在 Steam 目錄中！',
      hint: '點擊「完成」即可領取結業證書並返回！',
      placement: 'bottom',
      onEnter: function() {
        injectMockRoomDetailView();
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
