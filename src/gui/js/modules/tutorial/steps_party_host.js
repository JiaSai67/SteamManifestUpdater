/**
 * 教學模組：組隊開房引導 (Party Host Tutorial Steps - 旗艦真實彈窗與全週期版)
 * 職責：
 * 步驟 1：在大廳點擊右上角「➕ 創建房間」發起開房
 * 步驟 2：開啟真實創建彈窗，選擇遊戲、說明「核心三檔檢測 (Manifest/Lua/Patch)」
 * 步驟 3：詳細解說「Discord Webhook (整合包託管通道)」與影片教學
 * 步驟 4：點擊「🚀 立即開房」生成全網唯一房號並進入專屬房間
 * 步驟 5：確認連線房號【HOST666】並示範複製分享
 * 步驟 6：設定「預填聯絡資訊」（全員就緒自動廣播給所有隊員）
 * 步驟 7：即時監控全體隊員補丁同步進度（35% -> 80% -> 100%）
 * 步驟 8：全員就緒提示、30 秒安全緩衝、自動廣播與解散生命週期說明
 * 步驟 9：領取房長結業字卡
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
    note: '全隊拓荒進行中！補丁版本已釘選，請點擊一鍵安裝同步。',
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
   * 進入真實創建彈窗沙盒環境
   */
  function injectMockCreateModal(stepType) {
    window.__tutorialMockPartyActive = true;

    // 確保回到大廳視圖
    var lobbyView = document.getElementById('party-lobby-view');
    var roomView = document.getElementById('party-room-view');
    if (lobbyView) { lobbyView.style.display = 'flex'; lobbyView.classList.add('active'); }
    if (roomView) { roomView.style.display = 'none'; roomView.classList.remove('active'); }

    var modal = document.getElementById('modal-create-party-room');
    if (!modal) return;

    modal.style.display = 'flex';
    modal.classList.remove('hidden');
    modal.classList.add('active');

    // 填充示範遊戲資料
    var select = document.getElementById('select-party-installed-games');
    if (select) {
      select.innerHTML = '<option value="1245620" selected>艾爾登法環 (Elden Ring) [1245620] - 本機已安裝</option>';
    }

    var gn = document.getElementById('input-party-gamename');
    var aid = document.getElementById('input-party-appid');
    if (gn) gn.value = '艾爾登法環 (Elden Ring)';
    if (aid) aid.value = '1245620';

    // 點亮三檔綠燈
    var im = document.getElementById('inspect-manifest');
    var il = document.getElementById('inspect-lua');
    var ip = document.getElementById('inspect-patch');
    if (im) { im.className = 'resource-badge ready'; im.innerHTML = '📄 Manifest: ✔ 已就緒'; im.style.color = '#2EA043'; }
    if (il) { il.className = 'resource-badge ready'; il.innerHTML = '📜 Lua 腳本: ✔ 已就緒'; il.style.color = '#2EA043'; }
    if (ip) { ip.className = 'resource-badge ready'; ip.innerHTML = '🎮 線上補丁: ✔ 已就緒'; ip.style.color = '#2EA043'; }

    // 填充示範 Webhook
    var webhookInput = document.getElementById('input-party-discord-webhook');
    if (webhookInput) {
      webhookInput.value = 'https://discord.com/api/webhooks/1234567890/smu_tutorial_mock_token';
      webhookInput.style.borderColor = '#2ED573';
    }

    // 點亮開房按鈕
    var createBtn = document.getElementById('btn-submit-create-party');
    if (createBtn) {
      createBtn.disabled = false;
      createBtn.classList.remove('disabled');
    }

    // 漸顯教學影片卡片
    var card = document.getElementById('webhook-tutorial-card');
    if (card) card.classList.add('fade-in-active');
  }

  /**
   * 進入房主視角的房間檢視 (沙盒常駐保護，調用系統真實 renderRoomView 渲染)
   */
  function injectMockHostRoomView() {
    window.__tutorialMockPartyActive = true;
    window._partyCurRoom = JSON.parse(JSON.stringify(_mockHostRoomData));

    // 關閉創建彈窗
    var modal = document.getElementById('modal-create-party-room');
    if (modal) {
      modal.style.display = 'none';
      modal.classList.add('hidden');
      modal.classList.remove('active');
    }

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

    // 調用系統真實的 renderRoomView 渲染完整房間與真實隊員清單
    if (typeof window.renderRoomView === 'function') {
      window.renderRoomView(window._partyCurRoom);
    } else {
      var lobbyView = document.getElementById('party-lobby-view');
      var roomView = document.getElementById('party-room-view');
      if (lobbyView) { lobbyView.style.display = 'none'; lobbyView.classList.remove('active'); }
      if (roomView) { roomView.style.display = 'flex'; roomView.classList.add('active'); }
    }

    // 房主預填卡片控制
    var preContactWrap = document.getElementById('party-room-pre-contact-wrap');
    if (preContactWrap) preContactWrap.style.display = 'block';

    var syncWrap = document.getElementById('party-sync-btn-wrap');
    if (syncWrap) syncWrap.style.display = 'none';
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
      // 🌟 核心修復：在橫幅彈出後立即觸發 TutorialEngine 重新校準定位，防止提示框錯位！
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

    var preContactWrap = document.getElementById('party-room-pre-contact-wrap');
    if (preContactWrap) preContactWrap.style.display = 'none';

    var allReadyBanner = document.getElementById('party-all-ready-banner');
    if (allReadyBanner) allReadyBanner.style.display = 'none';

    if (typeof window.switchPartyNav === 'function') {
      window.switchPartyNav('lobby');
    }
  }

  // 🌟 組隊開房專屬結業慶祝彈窗（1:1 比照獨狼與線上補丁字卡樣式）
  function showPartyHostCompletionModal() {
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
          <button class="btn btn-o btn-s" id="btn-party-host-finish-back">🎓 返回教學首頁</button>
          <button class="btn btn-p btn-s" id="btn-party-host-finish-lobby" style="font-weight:700">👥 前往組隊大廳</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    modal.style.display = 'flex';

    var btnBack = document.getElementById('btn-party-host-finish-back');
    var btnLobby = document.getElementById('btn-party-host-finish-lobby');

    if (btnBack) {
      btnBack.onclick = function() {
        modal.remove();
        cleanupHostTutorialSandbox();
        if (typeof window.cleanupAllTutorialSandbox === 'function') {
          window.cleanupAllTutorialSandbox();
        }
        if (window.switchPage) window.switchPage('tutorial');
      };
    }

    if (btnLobby) {
      btnLobby.onclick = function() {
        modal.remove();
        cleanupHostTutorialSandbox();
        if (typeof window.cleanupAllTutorialSandbox === 'function') {
          window.cleanupAllTutorialSandbox();
        }
        if (window.switchPage) window.switchPage('party');
      };
    }
  }

  var partyHostSteps = [
    // 🌟 步驟 1：在大廳點擊「➕ 創建房間」按鈕
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

        if (!btn) btn = document.getElementById('btn-party-create-room');
        if (!btn) return;
        _origCreateBtnHTML = btn.innerHTML;
        btn.innerHTML = '<span>➕ 點擊創建房間</span>';
        btn.classList.add('tutorial-btn-simulating');

        var clickHandler = function(e) {
          e.preventDefault();
          e.stopPropagation();
          btn.removeEventListener('click', clickHandler, true);
          injectMockCreateModal('select-game');
          setTimeout(function() {
            if (window.TutorialEngine) window.TutorialEngine.next();
          }, 150);
        };
        btn.addEventListener('click', clickHandler, true);
      },
      onLeave: function() {
        var btn = document.getElementById('btn-party-create-room');
        if (btn) {
          btn.classList.remove('tutorial-btn-simulating');
          if (_origCreateBtnHTML !== null) {
            btn.innerHTML = _origCreateBtnHTML;
            _origCreateBtnHTML = null;
          }
        }
      }
    },
    // 🌟 步驟 2：選擇遊戲與「核心三檔檢測」說明 (真實彈窗高亮)
    {
      roleBadge: '👑 組隊招募・房主篇',
      moduleTitle: '單元 1：發起招募與配置檢測',
      page: 'party',
      target: '#party-resources-inspect-box, .party-package-section',
      title: '選擇遊戲與核心三檔自動檢測',
      desc: '在彈窗頂部選擇遊戲後，系統會自動對您的本機檔案進行<strong>「核心三檔檢測」</strong>（Manifest 清單、Lua 腳本、線上補丁）。三檔全數就緒才會點亮綠燈，確保房主版本能作為全隊最穩定標準！',
      hint: '系統會自動打包房主的補丁，隊員入隊時自動下載同步。',
      placement: 'top',
      onEnter: function() {
        injectMockCreateModal('inspect');
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },
    // 🌟 步驟 3：Discord Webhook (整合包託管通道) 與教學影片
    {
      roleBadge: '👑 組隊招募・房主篇',
      moduleTitle: '單元 1：發起招募與配置檢測',
      page: 'party',
      target: '#party-discord-config-wrap, #webhook-tutorial-card',
      title: 'Discord Webhook 託管通道與教學',
      desc: '<strong>什麼是 Discord Webhook？</strong> 它是 Discord 官方提供的免費自動傳輸通道！SMU 透過 Webhook 將房主的補丁檔案安全發布至您的私人 Discord 頻道中，隊員即可直接從 Discord CDN 超高速下載，房主無須自架伺服器或負擔傳輸費用！',
      hint: '右側有生動的循環動畫，手把手教學如何在 Discord 頻道建立 Webhook。',
      placement: 'left',
      onEnter: function() {
        injectMockCreateModal('webhook');
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },
    // 🌟 步驟 4：確認配置並一鍵生成房間
    {
      roleBadge: '👑 組隊招募・房主篇',
      moduleTitle: '單元 1：發起招募與配置檢測',
      page: 'party',
      target: '#btn-submit-create-party',
      title: '確認配置並立即開房',
      desc: '遊戲、三檔檢測與 Webhook 全數就緒後，點擊「🚀 立即開房」按鈕，系統將自動為您生成唯一的全網連線房號（如 HOST666），無須設定路由器或端口映射！',
      disableNext: true,
      placement: 'top',
      onEnter: function() {
        injectMockCreateModal('submit');
        var submitBtn = document.getElementById('btn-submit-create-party');
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.classList.remove('disabled');
          var onClick = function(e) {
            e.preventDefault();
            e.stopPropagation();
            submitBtn.removeEventListener('click', onClick, true);
            if (typeof tt === 'function') tt('🎉 成功創建房間 HOST666！', 'ok');
            injectMockHostRoomView();
            setTimeout(function() {
              if (window.TutorialEngine) window.TutorialEngine.next();
            }, 150);
          };
          submitBtn.addEventListener('click', onClick, true);
        }
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      }
    },
    // 🌟 步驟 5：複製連線房號並分發隊友
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
    // 🌟 步驟 6：預填聯絡資訊（自動廣播）
    {
      roleBadge: '👑 組隊招募・房主篇',
      moduleTitle: '單元 2：邀請分發與全隊開拔',
      page: 'party',
      target: '#party-room-pre-contact-wrap',
      title: '📢 預填聯絡資訊（自動廣播）',
      desc: '非常實用的房主專屬功能！在此預先填入您的 Discord 語音頻道連結或連線 IP。當全隊成員補丁全部就緒時，系統將自動廣播給所有隊員，免除逐一通知的麻煩！',
      onEnter: function() {
        injectMockHostRoomView();
        var input = document.getElementById('party-room-pre-contact-input');
        if (input && window.TutorialEngine) {
          window.TutorialEngine.simulateTyping(input, 'Discord 語音房: https://discord.gg/steam-party', {}, function(){});
        }
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      },
      placement: 'bottom'
    },
    // 🌟 步驟 7：即時監控全隊補丁進度 (修復錯位問題)
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
    // 🌟 步驟 8：全員就緒、1 分鐘等待緩衝與房間解散生命週期
    {
      roleBadge: '👑 組隊招募・房主篇',
      moduleTitle: '單元 3：完成組隊與房間生命週期',
      page: 'party',
      target: '#party-all-ready-banner',
      title: '🎉 全員就緒、1 分鐘緩衝與完成解散機制',
      desc: '當全員就緒時，系統會開啟 1 分鐘緩衝倒數，等待房主手動確認或發送聯絡資訊。房主亦可點擊「延遲 5 分鐘」（最多 2 次）或點擊「馬上完成(解散)」立即清除房間，若未填寫聯絡方式，系統將自動附帶您的 Discord 好友指引！',
      hint: '點擊「完成」即可領取房長結業證書並返回！',
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
                '<div style="color:#1976D2;font-size:11.5px">💡 已偵測到預填資訊：<strong>Discord 語音房: https://discord.gg/steam-party</strong></div>' +
                '<div class="banner-contact-row" style="margin-top:6px">' +
                  '<input type="text" class="party-contact-input" value="Discord 語音房: https://discord.gg/steam-party" readonly />' +
                  '<button class="btn btn-p btn-s">🚀 發送聯絡資訊</button>' +
                  '<button class="btn btn-o btn-s">⏳ 延遲 5 分鐘 (剩餘 2 次)</button>' +
                  '<button class="btn btn-danger btn-s">⚡ 馬上完成(解散)</button>' +
                '</div>' +
              '</div>';
          }
        }
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 60);
      },
      onLeave: function() {
        cleanupHostTutorialSandbox();
        showPartyHostCompletionModal();
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
