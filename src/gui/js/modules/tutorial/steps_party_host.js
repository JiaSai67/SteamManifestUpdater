/**
 * 教學模組：組隊開房引導 (Party Host Tutorial Steps - 旗艦真實彈窗與全生命週期版)
 * 職責：
 * 步驟 1 / 14：在大廳點擊右上角「➕ 創建房間」發起開房
 * 步驟 2 / 14：選擇組隊遊戲（本機已安裝自動偵測機制說明）
 * 步驟 3 / 14：核心三檔同步檢測（Manifest/Lua/Patch 三綠燈防護）
 * 步驟 4 / 14：Discord Webhook 整合包託管通道解說
 * 步驟 5 / 14：Webhook 建立教學與手把手影片指引
 * 步驟 6 / 14：設定人數上限與大廳公開度（公開/私密房型）
 * 步驟 7 / 14：房間備註與招募宣言（選填提示）
 * 步驟 8 / 14：預填隊伍聯絡資訊（全員就緒自動廣播與 1 分鐘緩衝機制）
 * 步驟 9 / 14：確認配置並點擊「🚀 立即開房」生成連線房號
 * 步驟 10 / 14：確認連線房號【HOST666】並示範複製分享
 * 步驟 11 / 14：即時監控全體隊員補丁同步進度（35% -> 80% -> 100%）
 * 步驟 12 / 14：🎉 全員就緒提示與 1 分鐘倒數緩衝機制說明
 * 步驟 13 / 14：🚀 親自發布聯絡資訊與開拔指令 (實戰點擊互動)
 * 步驟 14 / 14：🏆 隊伍組建完成與房間生命週期圓滿結束 (終局收尾領取證書)
 */

(function(window) {
  'use strict';

  var _origCreateBtnHTML = null;
  var _mockHostRoomData = {
    room_id: 'HOST666',
    appid: '1245620',
    game_name: '艾爾登法環 (Elden Ring) - 無縫聯機拓荒房',
    host_name: '您 (領航房長)',
    host_discord: 'host_leader#2026',
    max_players: 4,
    is_host: true,
    note: '新手開荒 / 語音隨意 / 缺 1 人即開',
    created_at: Math.floor(Date.now() / 1000) - 120,
    members: [
      {
        id: 'host_leader_me',
        name: '您 (領航房長)',
        discord: 'host_leader#2026',
        avatar_url: '',
        is_host: true,
        status: '就緒',
        progress: 100,
        steam_installed: true,
        version_status: '房主基準 (最新)'
      },
      {
        id: 'member_ming',
        name: '隊員小明',
        discord: 'ming#8888',
        avatar_url: '',
        is_host: false,
        status: '同步補丁中',
        progress: 35,
        steam_installed: true,
        version_status: '同步中'
      },
      {
        id: 'member_hua',
        name: '隊員阿華',
        discord: 'hua#9999',
        avatar_url: '',
        is_host: false,
        status: '同步補丁中',
        progress: 80,
        steam_installed: true,
        version_status: '同步中'
      }
    ]
  };

  /**
   * 進入真實創建彈窗沙盒環境（100% 呈現所有欄位真實設計）
   */
  function injectMockCreateModal(stepType) {
    window.__tutorialMockPartyActive = true;

    // 確保處於大廳視圖
    var lobbyView = document.getElementById('party-lobby-view');
    var roomView = document.getElementById('party-room-view');
    if (lobbyView) { lobbyView.style.display = 'flex'; lobbyView.classList.add('active'); }
    if (roomView) { roomView.style.display = 'none'; roomView.classList.remove('active'); }

    // 大廳導覽列切換為「組隊大廳」
    var navLobby = document.getElementById('party-nav-lobby');
    var navRoom = document.getElementById('party-nav-my-room') || document.getElementById('party-nav-room');
    if (navLobby) navLobby.classList.add('active');
    if (navRoom) { navRoom.classList.remove('active'); navRoom.style.display = 'none'; }

    var modal = document.getElementById('modal-create-party-room');
    if (!modal) return;

    modal.style.display = 'flex';
    modal.classList.remove('hidden');
    modal.classList.add('active');

    // 1. 填充示範遊戲資料
    var select = document.getElementById('select-party-installed-games');
    if (select) {
      select.innerHTML = '<option value="1245620" selected>艾爾登法環 (Elden Ring) [1245620] - 本機已安裝</option>';
    }

    var gn = document.getElementById('input-party-gamename');
    var aid = document.getElementById('input-party-appid');
    if (gn) gn.value = '艾爾登法環 (Elden Ring)';
    if (aid) aid.value = '1245620';

    // 2. 點亮三檔綠燈
    var im = document.getElementById('inspect-manifest');
    var il = document.getElementById('inspect-lua');
    var ip = document.getElementById('inspect-patch');
    if (im) { im.className = 'resource-badge ready'; im.innerHTML = '📄 Manifest: ✔ 已就緒'; im.style.color = '#2EA043'; }
    if (il) { il.className = 'resource-badge ready'; il.innerHTML = '📜 Lua 腳本: ✔ 已就緒'; il.style.color = '#2EA043'; }
    if (ip) { ip.className = 'resource-badge ready'; ip.innerHTML = '🎮 線上補丁: ✔ 已就緒'; ip.style.color = '#2EA043'; }

    // 3. 填充示範 Webhook
    var webhookInput = document.getElementById('input-party-discord-webhook');
    if (webhookInput) {
      webhookInput.value = 'https://discord.com/api/webhooks/1234567890/smu_tutorial_mock_token';
      webhookInput.style.borderColor = '#2ED573';
    }

    // 4. 填充人數上限 (4 人房)
    var maxPlayersSelect = document.getElementById('select-party-max-players');
    if (maxPlayersSelect) {
      maxPlayersSelect.value = '4';
    }

    // 5. 填充大廳公開度 (公開 1)
    var isPublicSelect = document.getElementById('select-party-is-public');
    if (isPublicSelect) {
      isPublicSelect.value = '1';
    }

    // 6. 填充房間備註 / 招募宣言
    var noteInput = document.getElementById('input-party-note');
    if (noteInput) {
      noteInput.value = '新手開荒 / 語音隨意 / 缺 1 人即開';
    }

    // 7. 填充預填隊伍聯絡資訊
    var preContactInput = document.getElementById('input-party-pre-contact');
    if (preContactInput) {
      preContactInput.value = '+dc: leader_eldener / 語音房已開';
    }

    // 8. 點亮開房按鈕
    var createBtn = document.getElementById('btn-submit-create-party');
    if (createBtn) {
      createBtn.disabled = false;
      createBtn.classList.remove('disabled');
    }

    // 9. 顯示右側 Webhook 教學影片卡片並播放
    var card = document.getElementById('webhook-tutorial-card');
    if (card) {
      card.classList.add('fade-in-active');
      var video = document.getElementById('webhook-tutorial-video');
      if (video && video.paused) {
        try { video.play(); } catch(e){}
      }
    }
  }

  /**
   * 進入房主視角的房間檢視 (沙盒常駐保護，調用系統真實 renderRoomView 渲染)
   */
  function injectMockHostRoomView() {
    window.__tutorialMockPartyActive = true;
    try {
      window._partyCurRoom = JSON.parse(JSON.stringify(_mockHostRoomData));

      // 關閉創建彈窗
      var modal = document.getElementById('modal-create-party-room');
      if (modal) {
        modal.style.display = 'none';
        modal.classList.add('hidden');
        modal.classList.remove('active');
      }

      // 強制切換真實視圖容器：隱藏大廳，顯示房間檢視
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

      // 切換導覽列狀態
      var navRoom = document.getElementById('party-nav-my-room') || document.getElementById('party-nav-room');
      var navLobby = document.getElementById('party-nav-lobby');
      if (navLobby) navLobby.classList.remove('active');
      if (navRoom) {
        navRoom.classList.add('active');
        navRoom.style.display = 'flex';
        var badge = navRoom.querySelector('.nav-badge');
        if (badge) badge.textContent = '3';
      }

      // 調用系統真實的 renderRoomView 渲染完整房間與真實隊員清單
      if (typeof window.renderRoomView === 'function') {
        window.renderRoomView(window._partyCurRoom);
      }

      // 房主預填卡片控制
      var preContactWrap = document.getElementById('party-room-pre-contact-wrap');
      if (preContactWrap) preContactWrap.style.display = 'block';

      var syncWrap = document.getElementById('party-sync-btn-wrap');
      if (syncWrap) syncWrap.style.display = 'none';
    } catch(err) {
      console.warn('[TutorialMock] injectMockHostRoomView error:', err);
    }
  }

  /**
   * 模擬隊員進度全部完成至 100% (平滑更新並自動 reposition 防止錯位)
   */
  function simulateMembersAllReady() {
    setTimeout(function() {
      if (window._partyCurRoom && window._partyCurRoom.members) {
        var hua = window._partyCurRoom.members.find(function(m) { return m.id === 'member_hua'; });
        if (hua) {
          hua.progress = 100;
          hua.status = '就緒';
          hua.version_status = '最新';
        }
        if (typeof window.renderRoomView === 'function') {
          window.renderRoomView(window._partyCurRoom);
        }
        if (window.TutorialEngine) window.TutorialEngine.reposition();
      }
    }, 400);

    setTimeout(function() {
      if (window._partyCurRoom && window._partyCurRoom.members) {
        var ming = window._partyCurRoom.members.find(function(m) { return m.id === 'member_ming'; });
        if (ming) {
          ming.progress = 100;
          ming.status = '就緒';
          ming.version_status = '最新';
        }
        if (typeof window.renderRoomView === 'function') {
          window.renderRoomView(window._partyCurRoom);
        }
      }
      var allReadyBanner = document.getElementById('party-all-ready-banner');
      if (allReadyBanner) {
        allReadyBanner.style.display = 'flex';
        allReadyBanner.classList.add('pulse');
      }
      // 在橫幅彈出後立即觸發 TutorialEngine 重新校準定位
      if (window.TutorialEngine) window.TutorialEngine.reposition();
      if (typeof tt === 'function') tt('🎉 全體隊員補丁已就緒！房主可下達開玩指令', 'ok');
    }, 900);
  }

  /**
   * 清理沙盒資料還原大廳
   */
  function cleanupHostTutorialSandbox() {
    window.__tutorialMockPartyActive = false;
    window._partyCurRoom = null;

    var modal = document.getElementById('modal-create-party-room');
    if (modal) {
      modal.style.display = 'none';
      modal.classList.add('hidden');
      modal.classList.remove('active');
    }

    // 🌟 徹底還原大廳建房按鈕與事件
    var btnCreate = document.getElementById('btn-party-create-room');
    if (btnCreate) {
      btnCreate.classList.remove('tutorial-btn-simulating');
      if (btnCreate._tutorialClickHandler) {
        btnCreate.removeEventListener('click', btnCreate._tutorialClickHandler, true);
        delete btnCreate._tutorialClickHandler;
      }
      btnCreate.setAttribute('onclick', 'handlePartyCreateOrRecruit()');
      btnCreate.innerHTML = '➕ 創建房間';
    }

    // 🌟 徹底還原彈窗立即開房按鈕與事件，絕不留空 onclick
    var submitBtn = document.getElementById('btn-submit-create-party');
    if (submitBtn) {
      submitBtn.classList.remove('tutorial-btn-simulating');
      if (submitBtn._tutorialSubmitHandler) {
        submitBtn.removeEventListener('click', submitBtn._tutorialSubmitHandler, true);
        delete submitBtn._tutorialSubmitHandler;
      }
      submitBtn.setAttribute('onclick', 'submitCreatePartyRoom()');
      submitBtn.onclick = function() {
        if (typeof window.submitCreatePartyRoom === 'function') {
          window.submitCreatePartyRoom();
        }
      };
    }

    // 🌟 還原真實開房彈窗表單所有輸入欄位與狀態
    var gn = document.getElementById('input-party-gamename');
    var aid = document.getElementById('input-party-appid');
    var note = document.getElementById('input-party-note');
    var webhook = document.getElementById('input-party-discord-webhook');
    var preContact = document.getElementById('input-party-pre-contact');
    var selGames = document.getElementById('select-party-installed-games');
    var maxPlayers = document.getElementById('select-party-max-players');
    var isPublic = document.getElementById('select-party-is-public');

    if (gn) gn.value = '';
    if (aid) aid.value = '';
    if (note) { note.value = ''; try { note.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){} }
    if (webhook) {
      webhook.value = '';
      webhook.style.borderColor = '';
      try { webhook.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}
    }
    if (preContact) {
      preContact.value = '';
      try { preContact.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){}
    }
    if (selGames) {
      selGames.value = '';
      try { selGames.dispatchEvent(new Event('change', { bubbles: true })); } catch(e){}
    }
    if (maxPlayers) maxPlayers.value = '4';
    if (isPublic) isPublic.value = '1';

    // 清理房間內與大廳的所有輸入項目
    var searchInp = document.getElementById('party-search-input');
    if (searchInp) { searchInp.value = ''; try { searchInp.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){} }
    var quickCodeInp = document.getElementById('party-quick-code');
    if (quickCodeInp) { quickCodeInp.value = ''; try { quickCodeInp.dispatchEvent(new Event('input', { bubbles: true })); } catch(e){} }
    var contactInps = document.querySelectorAll('.party-contact-input');
    contactInps.forEach(function(inp) { inp.value = ''; });

    // 強制關閉開房彈窗
    var modalCreate = document.getElementById('modal-create-party-room');
    if (modalCreate) {
      modalCreate.classList.add('hidden');
      modalCreate.style.display = 'none';
    }

    if (typeof window.resetResourceInspectBadges === 'function') {
      window.resetResourceInspectBadges();
    }
    if (typeof window.loadInstalledGamesDropdown === 'function') {
      window.loadInstalledGamesDropdown();
    }
    if (typeof window.updateCreateRoomBtnState === 'function') {
      window.updateCreateRoomBtnState();
    }

    var preContactWrap = document.getElementById('party-room-pre-contact-wrap');
    if (preContactWrap) preContactWrap.style.display = 'none';

    var allReadyBanner = document.getElementById('party-all-ready-banner');
    if (allReadyBanner) allReadyBanner.style.display = 'none';

    var centralModal = document.getElementById('modal-party-host-completion-central');
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

    if (typeof window.switchPartyNav === 'function') {
      window.switchPartyNav('lobby');
    }

    // 恢復大廳真實連線輪詢與渲染
    if (typeof window.refreshPartyLobby === 'function') {
      window.refreshPartyLobby(false);
    }
  }

  // 組隊開房專屬結業慶祝彈窗（1:1 比照獨狼與線上補丁字卡樣式）
  function showPartyHostCompletionModal() {
    var oldModals = document.querySelectorAll('.tutorial-completion-modal-wrap');
    oldModals.forEach(function(m) {
      try { m.remove(); } catch(e){}
    });

    var modal = document.createElement('div');
    modal.className = 'tutorial-sandbox-modal-wrap tutorial-completion-modal-wrap';
    modal.id = 'tutorial-party-host-complete-modal';
    modal.innerHTML = `
      <div class="tutorial-sandbox-modal-card tutorial-completion-modal-card" style="text-align:center;padding:28px 24px">
        <div style="font-size:46px;margin-bottom:8px">👑🎉</div>
        <h2 class="tutorial-completion-title" style="margin:0 0 10px 0;font-size:20px;font-weight:900">組隊開房教學 圓滿完成！</h2>
        <p class="tutorial-completion-desc" style="font-size:13px;line-height:1.65;margin:0 0 20px 0">
          太棒了！您已經完整掌握了<strong>「一鍵房間創建」</strong>、<strong>「三檔檢測與 Webhook 託管」</strong>、<strong>「房號快速複製與邀請分發」</strong>、<strong>「預填聯絡資訊自動廣播」</strong>以及<strong>「全隊補丁即時監控與房間生命週期」</strong>的全部核心操作。<br>
          現在，您可以化身隊伍領航房長，隨時號召好友開房組隊，打造最完美的聯機遊戲體驗！
        </p>
        <div style="display:flex;justify-content:center;gap:12px">
          <button class="btn btn-o btn-s" id="btn-party-host-finish-back" type="button">🎓 返回教學首頁</button>
          <button class="btn btn-p btn-s" id="btn-party-host-finish-lobby" type="button" style="font-weight:700">👥 前往組隊大廳</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    modal.style.display = 'flex';

    var btnBack = modal.querySelector('#btn-party-host-finish-back');
    var btnLobby = modal.querySelector('#btn-party-host-finish-lobby');

    if (btnBack) {
      btnBack.onclick = function(e) {
        if (e) { e.preventDefault(); e.stopPropagation(); }
        if (typeof window.playTutorialSound === 'function') {
          window.playTutorialSound('step');
        }
        document.querySelectorAll('.tutorial-completion-modal-wrap').forEach(function(m) {
          try { m.remove(); } catch(err){}
        });
        try { cleanupHostTutorialSandbox(); } catch(err){}
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
        try { cleanupHostTutorialSandbox(); } catch(err){}
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

  var partyHostSteps = [
    // 🌟 步驟 1 / 16：在大廳點擊「➕ 創建房間」按鈕
    {
      roleBadge: '👑 組隊招募・房主篇',
      moduleTitle: '單元 1：發起招募與配置檢測',
      page: 'party',
      target: '#btn-party-create-room',
      title: '點擊發起房間創建',
      desc: '作為隊伍領隊，您可以在大廳右上角點擊「➕ 創建房間」按鈕。請親自點擊此按鈕，開啟專屬組隊建房彈窗！',
      hint: '房主擁有房間最高管理權限，包含踢人、公告設定與房間關閉。',
      placement: 'bottom',
      disableNext: true,
      onEnter: function(btn) {
        window.__tutorialMockPartyActive = true;
        var lobbyView = document.getElementById('party-lobby-view');
        var roomView = document.getElementById('party-room-view');
        if (lobbyView) { lobbyView.style.display = 'flex'; lobbyView.classList.add('active'); }
        if (roomView) { roomView.style.display = 'none'; roomView.classList.remove('active'); }

        // 若從下一步退回，關閉彈窗
        var modal = document.getElementById('modal-create-party-room');
        if (modal) {
          modal.style.display = 'none';
          modal.classList.add('hidden');
          modal.classList.remove('active');
        }

        if (!btn) btn = document.getElementById('btn-party-create-room');
        if (!btn) return;
        _origCreateBtnHTML = btn.innerHTML;
        btn.innerHTML = '<span>➕ 點擊創建房間</span>';
        btn.classList.add('tutorial-btn-simulating');

        var clickHandler = function(e) {
          e.preventDefault();
          e.stopPropagation();
          btn.removeEventListener('click', clickHandler, true);
          delete btn._tutorialClickHandler;
          injectMockCreateModal('select-game');
          setTimeout(function() {
            if (window.TutorialEngine) window.TutorialEngine.next();
          }, 150);
        };
        btn._tutorialClickHandler = clickHandler;
        btn.addEventListener('click', clickHandler, true);
      },
      onLeave: function() {
        var btn = document.getElementById('btn-party-create-room');
        if (btn) {
          btn.classList.remove('tutorial-btn-simulating');
          if (btn._tutorialClickHandler) {
            btn.removeEventListener('click', btn._tutorialClickHandler, true);
            delete btn._tutorialClickHandler;
          }
          if (_origCreateBtnHTML !== null) {
            btn.innerHTML = _origCreateBtnHTML;
            _origCreateBtnHTML = null;
          }
        }
      }
    },

    // 🌟 步驟 2 / 16：選擇組隊遊戲 (僅限自動偵測就緒之遊戲)
    {
      roleBadge: '👑 組隊招募・房主篇',
      moduleTitle: '單元 1：發起招募與配置檢測',
      page: 'party',
      target: '#party-select-game-wrap, #select-party-installed-games',
      title: '選擇組隊遊戲',
      desc: '在彈窗最上方挑選您要號召好友組隊的遊戲。SMU 僅允許挑選<strong>本機已偵測且已部署聯機環境</strong>的遊戲，系統會自動鎖定 AppID 與遊戲版本，杜絕手打錯誤造成全隊版本不符！',
      hint: '若剛安裝新遊戲，可點擊右側「🔄 重新整理」即時掃描更新清單。',
      placement: 'right',
      onEnter: function() {
        injectMockCreateModal('select-game');
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },

    // 🌟 步驟 3 / 16：核心三檔自動檢測 (全就緒綠燈保障)
    {
      roleBadge: '👑 組隊招募・房主篇',
      moduleTitle: '單元 1：發起招募與配置檢測',
      page: 'party',
      target: '#party-resources-inspect-box',
      title: '核心三檔自動檢測',
      desc: '選擇遊戲後，系統會自動對您的本機檔案進行<strong>「核心三檔檢測」</strong>（Manifest 清單、Lua 腳本、線上補丁）。三檔全數就緒才會亮起綠燈，確保房主版本能作為全隊最穩定的統一標準！',
      hint: '系統會將房主的三檔自動打包，隊員入隊時一鍵下載同步，完全免手動傳檔。',
      placement: 'right',
      onEnter: function() {
        injectMockCreateModal('inspect');
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },

    // 🌟 步驟 4 / 16：Discord Webhook (整合包託管通道)
    {
      roleBadge: '👑 組隊招募・房主篇',
      moduleTitle: '單元 1：發起招募與配置檢測',
      page: 'party',
      target: '#party-discord-config-wrap',
      title: 'Discord Webhook 託管通道',
      desc: '<strong>什麼是 Discord Webhook？</strong> 它是 Discord 官方提供的免費自動傳輸通道！SMU 透過 Webhook 將房主的補丁檔案安全發布至您的私人 Discord 頻道中，隊員即可直接從 Discord CDN 超高速下載，房主無須自架伺服器或負擔傳輸費用！',
      hint: '填入後可點擊「🔗 測試連線」驗證，通過測試後系統會自動記憶保存，下次開房免重複輸入。',
      placement: 'right',
      onEnter: function() {
        injectMockCreateModal('webhook');
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },

    // 🌟 步驟 5 / 16：Webhook 建立教學與影片指引
    {
      roleBadge: '👑 組隊招募・房主篇',
      moduleTitle: '單元 1：發起招募與配置檢測',
      page: 'party',
      target: '#webhook-tutorial-card',
      title: 'Webhook 建立教學與影片指引',
      desc: '彈窗右側配備生動的循環動畫，手把手教學如何在 Discord 頻道建立專屬 Webhook：在任何伺服器頻道右鍵 ➔ 編輯頻道 ➔ 整合 ➔ 建立 Webhook 複製貼上即可！',
      hint: '教學卡片會依視窗大小自適應調整，確保大畫面極致清晰、小畫面不佔版面。',
      placement: 'left',
      onEnter: function() {
        injectMockCreateModal('video');
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },

    // 🌟 步驟 6 / 16：設定人數上限與大廳公開度
    {
      roleBadge: '👑 組隊招募・房主篇',
      moduleTitle: '單元 1：發起招募與配置檢測',
      page: 'party',
      target: '#party-players-visibility-wrap',
      title: '設定人數上限與大廳公開度',
      desc: '房主可依遊戲模式自訂隊伍人數（2 人、4 人、6 人、8 人）。「🌐 公開」會將房間展示於全網組隊大廳供玩家自由加入；若選擇「🔒 私密」，則僅有獲得您 6 碼連線房號的好友才能加入！',
      hint: '若想與特定好友私下開黑，建議切換為「私密」模式。',
      placement: 'right',
      onEnter: function() {
        injectMockCreateModal('capacity');
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },

    // 🌟 步驟 7 / 16：房間備註與招募宣言 (選填)
    {
      roleBadge: '👑 組隊招募・房主篇',
      moduleTitle: '單元 1：發起招募與配置檢測',
      page: 'party',
      target: '#party-room-note-wrap, #input-party-note',
      title: '房間備註與招募宣言',
      desc: '在此填寫您的隊伍招募宣言（例如：「新手開荒 / 語音隨意 / 缺 1 人即開」）。清晰的備註能讓大廳瀏覽的玩家一眼了解隊伍節奏與語音需求，大幅提升組隊默契！',
      hint: '此欄位為選填，若留空大廳將顯示遊戲預設名稱。',
      placement: 'right',
      onEnter: function() {
        injectMockCreateModal('note');
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },

    // 🌟 步驟 8 / 16：預填隊伍聯絡資訊 (自動廣播機制)
    {
      roleBadge: '👑 組隊招募・房主篇',
      moduleTitle: '單元 1：發起招募與配置檢測',
      page: 'party',
      target: '#party-modal-pre-contact-wrap, #input-party-pre-contact',
      title: '📢 預填隊伍聯絡資訊 (自動廣播機制)',
      desc: '非常實用的房主專屬功能！在此預先填入您的 Discord 語音頻道連結或連線 IP。當全隊成員補丁全部就緒時，系統將在 1 分鐘倒數中自動/一鍵廣播給所有隊員，免除逐一私訊通知的麻煩！若留空，系統亦會在倒數時等待您手動填寫。',
      hint: '預先填好聯絡方式，隊伍全員就緒時即可一鍵快速發送開拔！',
      placement: 'right',
      onEnter: function() {
        injectMockCreateModal('pre-contact');
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },

    // 🌟 步驟 9 / 16：確認配置並立即開房
    {
      roleBadge: '👑 組隊招募・房主篇',
      moduleTitle: '單元 1：發起招募與配置檢測',
      page: 'party',
      target: '#btn-submit-create-party',
      title: '確認配置並立即開房',
      desc: '遊戲、三檔檢測、Webhook 與各項配置確認完畢後，點擊「🚀 立即開房」按鈕，系統將自動為您生成唯一的全網連線房號（如 HOST666），無須設定路由器或端口映射！請親自點擊此按鈕！',
      placement: 'top',
      onEnter: function() {
        injectMockCreateModal('submit');
        var submitBtn = document.getElementById('btn-submit-create-party');
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.classList.remove('disabled');
          submitBtn.classList.add('tutorial-btn-simulating');
          var onClick = function(e) {
            if (e) {
              e.preventDefault();
              e.stopPropagation();
              if (e.stopImmediatePropagation) e.stopImmediatePropagation();
            }
            submitBtn.removeEventListener('click', onClick, true);
            delete submitBtn._tutorialSubmitHandler;
            submitBtn.classList.remove('tutorial-btn-simulating');
            submitBtn.setAttribute('onclick', 'submitCreatePartyRoom()');
            submitBtn.onclick = function() {
              if (typeof window.submitCreatePartyRoom === 'function') window.submitCreatePartyRoom();
            };
            if (typeof tt === 'function') tt('🎉 成功創建房間 HOST666！', 'ok');
            try {
              injectMockHostRoomView();
            } catch(err) {
              console.warn('[TutorialMock] injectMockHostRoomView error:', err);
            }
            setTimeout(function() {
              if (window.TutorialEngine) window.TutorialEngine.next();
            }, 100);
          };
          submitBtn._tutorialSubmitHandler = onClick;
          submitBtn.addEventListener('click', onClick, true);
        }
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      },
      onBeforeNext: function() {
        injectMockHostRoomView();
      },
      onLeave: function() {
        var submitBtn = document.getElementById('btn-submit-create-party');
        if (submitBtn) {
          submitBtn.classList.remove('tutorial-btn-simulating');
          if (submitBtn._tutorialSubmitHandler) {
            submitBtn.removeEventListener('click', submitBtn._tutorialSubmitHandler, true);
            delete submitBtn._tutorialSubmitHandler;
          }
          submitBtn.setAttribute('onclick', 'submitCreatePartyRoom()');
          submitBtn.onclick = function() {
            if (typeof window.submitCreatePartyRoom === 'function') window.submitCreatePartyRoom();
          };
        }
      }
    },

    // 🌟 步驟 10 / 16：複製連線房號並分發隊友
    {
      roleBadge: '👑 組隊招募・房主篇',
      moduleTitle: '單元 2：邀請分發與全隊開拔',
      page: 'party',
      target: '.party-room-code-pill, #party-room-code-val',
      title: '複製連線房號並分發隊友',
      desc: '房間創建成功！頂部已生成您的專屬房間代碼【HOST666】。點擊右側 📋 圖示即可快速複製房號，發送至 Discord 頻道或好友私訊即可邀請加入！',
      hint: '隊員只要在大廳填入此代碼即可瞬間加入您的隊伍。',
      placement: 'bottom',
      onEnter: function() {
        injectMockHostRoomView();
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },

    // 🌟 步驟 11 / 16：即時監控全隊補丁進度
    {
      roleBadge: '👑 組隊招募・房主篇',
      moduleTitle: '單元 2：邀請分發與全隊開拔',
      page: 'party',
      target: '.party-members-section, #party-members-list',
      title: '即時監控全隊補丁進度',
      desc: '真實隊員清單每 3 秒自動即時同步。右側進度條動態呈現全隊下載狀況，此時隊員小明（35%）與隊員阿華（80%）正在對齊您的版本。系統會自動分發補丁，隊員無須手動尋找！',
      onEnter: function() {
        injectMockHostRoomView();
        simulateMembersAllReady();
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      },
      placement: 'top'
    },

    // 🌟 步驟 12 / 16：🎉 全員就緒與 1 分鐘緩衝倒數
    {
      roleBadge: '👑 組隊招募・房主篇',
      moduleTitle: '單元 3：完成組隊與房間生命週期',
      page: 'party',
      target: '#party-all-ready-banner',
      title: '🎉 全員就緒與 1 分鐘倒數緩衝',
      desc: '太棒了！所有隊員的補丁與遊戲環境已 100% 同步就緒！頂部橫幅自動啟動 <strong>1 分鐘倒數緩衝</strong>，給予房長確認隊員麥克風與語音狀態的時間。若隊友暫離或尚未準備好，房長可點擊「⏳ 延遲 5 分鐘」（最多可延長 2 次）。',
      hint: '請確認倒數機制後，點擊「下一步」親自演練發布聯絡資訊與開拔操作！',
      placement: 'bottom',
      onEnter: function() {
        injectMockHostRoomView();
        var banner = document.getElementById('party-all-ready-banner');
        if (banner) {
          banner.style.display = 'flex';
          var bannerContentEl = banner.querySelector('.banner-content');
          if (bannerContentEl) {
            bannerContentEl.innerHTML = 
              '<div class="banner-title">🎉 全員已就緒！等待房主發送聯絡資訊 (倒數 <span id="party-cd-sec" class="banner-cd-sec">01 分 00 秒</span>)</div>' +
              '<div class="banner-desc">' +
                '<div style="color:#1976D2;font-size:11.5px">💡 已偵測到預填資訊：<strong>+dc: leader_eldener / 語音房已開</strong></div>' +
                '<div class="banner-contact-row" style="margin-top:6px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">' +
                  '<input type="text" class="party-contact-input" value="+dc: leader_eldener / 語音房已開" readonly style="flex:1;min-width:220px;max-width:320px" />' +
                  '<button class="btn btn-p btn-s" id="party-btn-finish-party" style="font-weight:800;background:linear-gradient(135deg,#2EA043,#238636);box-shadow:0 2px 10px rgba(46,160,67,0.35);cursor:pointer">🚀 完成組隊並發布資訊 (解散房間)</button>' +
                  '<button class="btn btn-o btn-s" id="party-btn-delay-countdown" style="cursor:pointer">⏳ 延遲 5 分鐘 (剩餘 2 次)</button>' +
                '</div>' +
              '</div>';
          }
        }

        // 🌟 核心互動加固：點擊延遲或發布按鈕時，友善提示並引導進入下一步
        var delayBtn = document.getElementById('party-btn-delay-countdown');
        var finishBtn = document.getElementById('party-btn-finish-party');

        if (delayBtn) {
          delayBtn.onclick = function(e) {
            if (e) { e.preventDefault(); e.stopPropagation(); }
            var cdSpan = document.getElementById('party-cd-sec');
            if (cdSpan) cdSpan.innerText = '05 分 00 秒';
            delayBtn.innerText = '⏳ 延遲 5 分鐘 (剩餘 1 次)';
            if (typeof tt === 'function') {
              tt('⏳ 模擬延長緩衝成功！請點擊右下角「下一步 ➔」進入發布開拔演練', 'info');
            }
            var nextBtn = document.getElementById('tutorial-popover-next');
            if (nextBtn) {
              nextBtn.classList.add('tutorial-btn-simulating');
              setTimeout(function() { nextBtn.classList.remove('tutorial-btn-simulating'); }, 2000);
            }
          };
        }

        if (finishBtn) {
          finishBtn.onclick = function(e) {
            if (e) { e.preventDefault(); e.stopPropagation(); }
            if (typeof tt === 'function') {
              tt('🚀 收到發布請求！即將進入開拔發布步驟…', 'ok');
            }
            var nextBtn = document.getElementById('tutorial-popover-next');
            if (nextBtn) nextBtn.classList.add('tutorial-btn-simulating');
            setTimeout(function() {
              if (window.TutorialEngine) window.TutorialEngine.next();
            }, 260);
          };
        }

        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      },
      onLeave: function() {
        var delayBtn = document.getElementById('party-btn-delay-countdown');
        var finishBtn = document.getElementById('party-btn-finish-party');
        if (delayBtn) delayBtn.onclick = null;
        if (finishBtn) finishBtn.onclick = null;
      }
    },

    // 🌟 步驟 13 / 16：🚀 親自發布聯絡資訊與開拔指令 (實戰點擊互動)
    {
      roleBadge: '👑 組隊招募・房主篇',
      moduleTitle: '單元 3：完成組隊與房間生命週期',
      page: 'party',
      target: '#party-btn-finish-party, #party-all-ready-banner .banner-contact-row',
      title: '🚀 親自發布聯絡資訊與開拔指令',
      desc: '隊伍全員就緒！現在請親自點擊綠色<strong>「🚀 完成組隊並發布資訊 (解散房間)」</strong>按鈕。系統將自動把您的 Discord 語音頻道與連線資訊瞬間廣播給房間內所有隊友，並啟動房間解散程序！',
      hint: '請親自點擊下方亮起的綠色「🚀 完成組隊並發布資訊 (解散房間)」按鈕！',
      disableNext: true,
      placement: 'top',
      onEnter: function() {
        injectMockHostRoomView();
        var centralModal = document.getElementById('modal-party-host-completion-central');
        if (centralModal) centralModal.remove();

        var banner = document.getElementById('party-all-ready-banner');
        if (banner) {
          banner.style.display = 'flex';
          var bannerContentEl = banner.querySelector('.banner-content');
          if (bannerContentEl) {
            bannerContentEl.innerHTML = 
              '<div class="banner-title">🎉 全員已就緒！等待房主發送聯絡資訊 (倒數 <span id="party-cd-sec" class="banner-cd-sec">00 分 50 秒</span>)</div>' +
              '<div class="banner-desc">' +
                '<div style="color:#1976D2;font-size:11.5px">💡 已偵測到預填資訊：<strong>+dc: leader_eldener / 語音房已開</strong>，點擊按鈕即可一鍵發布並完成組隊！</div>' +
                '<div class="banner-contact-row" style="margin-top:6px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">' +
                  '<input type="text" id="party-contact-input" class="party-contact-input" value="+dc: leader_eldener / 語音房已開" readonly style="flex:1;min-width:220px;max-width:320px" />' +
                  '<button class="btn btn-p btn-s tutorial-btn-simulating" id="party-btn-finish-party" style="font-weight:800;background:linear-gradient(135deg,#2EA043,#238636);box-shadow:0 2px 10px rgba(46,160,67,0.35);cursor:pointer">🚀 完成組隊並發布資訊 (解散房間)</button>' +
                  '<button class="btn btn-o btn-s" id="party-btn-delay-countdown" disabled>⏳ 延遲 5 分鐘 (剩餘 2 次)</button>' +
                '</div>' +
              '</div>';
          }
        }
        var finishBtn = document.getElementById('party-btn-finish-party');
        if (finishBtn) {
          var onFinishClick = function(e) {
            if (e) {
              e.preventDefault();
              e.stopPropagation();
            }
            finishBtn.removeEventListener('click', onFinishClick, true);
            finishBtn.classList.remove('tutorial-btn-simulating');
            if (typeof tt === 'function') tt('🎉 正在發布聯絡資訊並解散房間…', 'info');
            if (typeof window.showPartyHostCompletionCentralModal === 'function') {
              window.showPartyHostCompletionCentralModal(_mockHostRoomData.members, '+dc: leader_eldener / 語音房已開');
            }
            setTimeout(function() {
              if (window.TutorialEngine) window.TutorialEngine.next();
            }, 180);
          };
          finishBtn.addEventListener('click', onFinishClick, true);
        }
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      },
      onLeave: function() {
        var finishBtn = document.getElementById('party-btn-finish-party');
        if (finishBtn) finishBtn.classList.remove('tutorial-btn-simulating');
      }
    },

    // 🌟 步驟 14 / 14：🏆 隊伍組建完成與房間生命週期圓滿結束 (終局收尾領取證書)
    {
      roleBadge: '👑 組隊招募・房主篇',
      moduleTitle: '單元 3：完成組隊與房間生命週期',
      page: 'party',
      target: '#modal-party-host-completion-central .party-central-completion-card',
      title: '🏆 隊伍組建完成與房間生命週期圓滿結束',
      desc: '發布成功！此時在房主與全體隊友的螢幕中央，已同步彈出組隊完成大卡，隊友已即時取得您的語音頻道與開拔資訊！雲端房間已圓滿達成使命並自動安全解散。請親自點擊中央大卡中的<strong>「👥 返回組隊大廳」</strong>，即可解散房間並領取榮譽房長結業證書！',
      hint: '請親自點擊中央大卡中的「👥 返回組隊大廳」按鈕完成教學！',
      disableNext: true,
      nextText: '完成教學 🎉',
      placement: 'right',
      offsetX: 14,
      onEnter: function() {
        var centralModal = document.getElementById('modal-party-host-completion-central');
        if (!centralModal && typeof window.showPartyHostCompletionCentralModal === 'function') {
          window.showPartyHostCompletionCentralModal(_mockHostRoomData.members, '+dc: leader_eldener / 語音房已開');
          centralModal = document.getElementById('modal-party-host-completion-central');
        }
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

              // 模擬房間解散完畢，清理沙盒並返回大廳
              cleanupHostTutorialSandbox();

              if (typeof tt === 'function') tt('🚪 房間【HOST666】已圓滿解散，已安全返回組隊大廳！', 'ok');

              // 🌟 步驟 14 做為最終收尾：直接圓滿結束教學並展示榮譽房長證書
              if (window.TutorialEngine) {
                window.TutorialEngine.stop(true);
              }
              showPartyHostCompletionModal();
            };
            closeBtn.addEventListener('click', onCloseClick, true);
          }
        }
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      },
      onLeave: function() {
        cleanupHostTutorialSandbox();
      }
    }
  ];

  if (window.TutorialEngine) {
    window.TutorialEngine.registerModule('party_host_guide', {
      name: '組隊開房引導',
      steps: partyHostSteps,
      cleanup: cleanupHostTutorialSandbox,
      showCompletionModal: showPartyHostCompletionModal
    });
  }

})(window);
