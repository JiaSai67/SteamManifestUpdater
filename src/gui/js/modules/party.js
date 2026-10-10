/* SteamManifestUpdater - Module: party.js */

// ═══════════════════════════════════════════════════════

// 🌸 SMU 無伺服器邊緣組隊大廳與聯機同步模組

// 依託 Cloudflare Workers 邊緣網絡實現 0 成本、高可用之全網組隊大廳

// ═══════════════════════════════════════════════════════

var _partyProfile = null;

var _partyRooms = [];

var _partyCurRoom = null;

var _partyPollTimer = null;

var _isPartyActive = false;

var _partySearchKeyword = '';
var _partyCountdownTimer = null;
var _partyCountdownSeconds = 60; // 🌟 預設給予 1 分鐘 (60 秒) 填寫資料或選擇發送/解散
var _partyDelayCount = 0; // 🌟 房主延遲 5 分鐘計數 (最多 2 次)
var _partyContactSubmitted = false;
var _partyContactPollingTimer = null;
var _partyReceivedContact = '';
var _partyPostDestructTimer = null;
var _partyContactInputText = '';
var _partyPreFilledContact = '';
try {
  _partyPreFilledContact = localStorage.getItem('smu_party_pre_contact') || '';
  _partyContactInputText = _partyPreFilledContact;
} catch (e) {}
var _partyPollFailures = 0;

/**
 * 房主儲存或更新預填聯絡資訊 (支援建房彈窗與房間等待頁面雙向同步)
 */
function savePartyPreFilledContact(val) {
  _partyPreFilledContact = (val !== undefined && val !== null) ? String(val).trim() : '';
  _partyContactInputText = _partyPreFilledContact;
  try {
    if (_partyPreFilledContact) {
      localStorage.setItem('smu_party_pre_contact', _partyPreFilledContact);
    } else {
      localStorage.removeItem('smu_party_pre_contact');
    }
  } catch (e) {}

  var modalInput = document.getElementById('input-party-pre-contact');
  if (modalInput && modalInput.value !== _partyPreFilledContact) {
    modalInput.value = _partyPreFilledContact;
  }
  var roomInput = document.getElementById('party-room-pre-contact-input');
  if (roomInput && roomInput.value !== _partyPreFilledContact) {
    roomInput.value = _partyPreFilledContact;
  }
}

/**
 * 倒數重置與中斷保護：當全員就緒狀態改變或有成員退出時隨時停止倒數
 */
function resetPartyReadyCountdown() {
  if (_partyCountdownTimer) {
    clearInterval(_partyCountdownTimer);
    _partyCountdownTimer = null;
  }
  if (_partyContactPollingTimer) {
    clearInterval(_partyContactPollingTimer);
    _partyContactPollingTimer = null;
  }
  if (_partyPostDestructTimer) {
    clearInterval(_partyPostDestructTimer);
    _partyPostDestructTimer = null;
  }
  _partyCountdownSeconds = 60;
  _partyDelayCount = 0;
  _partyContactSubmitted = false;
  _partyReceivedContact = '';
  // 🌟 保留預填聯絡資訊，不被未全員就緒時的定時心跳清空
  _partyContactInputText = _partyPreFilledContact || localStorage.getItem('smu_party_pre_contact') || '';
  if (window.PartyP2P) {
    window.PartyP2P.close();
  }
  var allReadyBanner = document.getElementById('party-all-ready-banner');
  if (allReadyBanner) {
    allReadyBanner.style.display = 'none';
    var bannerContentEl = allReadyBanner.querySelector('.banner-content');
    if (bannerContentEl) bannerContentEl.dataset.mode = '';
  }
}
/**

 * 安全 HTML 轉義函式 (防止 XSS 與缺少定義之 ReferenceError)

 */

function escapeHtml(str) {

  if (str === null || str === undefined) return '';

  return String(str)

    .replace(/&/g, '&amp;')

    .replace(/</g, '&lt;')

    .replace(/>/g, '&gt;')

    .replace(/"/g, '&quot;')

    .replace(/'/g, '&#39;');

}

/**

 * 當切換至組隊大廳頁面時觸發初始化

 */

function initPartyPage() {

  _isPartyActive = true;

  loadPartyProfile();

  checkCurrentPartyRoom();

  if (typeof bindBackdropClickClose === 'function') {

    bindBackdropClickClose('modal-create-party-room', closeCreateRoomModal);

  }

}

/**

 * 當離開組隊大廳頁面時休眠輪詢 (省流量與 0 消耗額度)

 */

function pausePartyPolling() {

  _isPartyActive = false;

  if (_partyPollTimer) {

    clearTimeout(_partyPollTimer);

    _partyPollTimer = null;

  }

}

/**

 * 載入個人組隊資料 (暱稱、自動讀取之 Discord 帳號、額度狀態)

 */

function loadPartyProfile() {
  if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.get_party_profile) return;
  pywebview.api.get_party_profile().then(function(res) {
    if (!res) return;
    _partyProfile = res;

    var nameEl = document.getElementById('party-my-name');
    var badgeEl = document.getElementById('party-verified-badge');
    var subtextEl = document.getElementById('party-discord-tag-display');
    var avatarImg = document.getElementById('party-avatar-img');
    var avatarFallback = document.getElementById('party-avatar-fallback');
    var oauthBtn = document.getElementById('btn-discord-oauth');

    if (res.is_discord_verified) {
      // 官方認證成功狀態 (不可修改)
      var dispName = res.discord_global_name || res.discord_username || res.nickname || '認證特工';
      if (nameEl) nameEl.textContent = dispName;
      if (badgeEl) badgeEl.style.display = 'inline-flex';
      if (subtextEl) subtextEl.textContent = `@${res.discord_username || 'user'}`;
      
      if (res.discord_avatar && avatarImg) {
        avatarImg.src = res.discord_avatar;
        avatarImg.style.display = 'block';
        if (avatarFallback) avatarFallback.style.display = 'none';
      }
      
      if (oauthBtn) {
        oauthBtn.className = 'btn-discord-oauth verified';
        oauthBtn.innerHTML = `<span>✓ 已官方認證</span>`;
        oauthBtn.title = `已綁定 Discord: @${res.discord_username}`;
      }
    } else {
      // 尚未驗證狀態
      if (nameEl) nameEl.textContent = '尚未驗證身分';
      if (badgeEl) badgeEl.style.display = 'none';
      if (subtextEl) subtextEl.textContent = '請先完成 Discord 官方認證以解鎖組隊';
      if (avatarImg) avatarImg.style.display = 'none';
      if (avatarFallback) avatarFallback.style.display = 'flex';
      
      if (oauthBtn) {
        oauthBtn.className = 'btn-discord-oauth';
        oauthBtn.innerHTML = `
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
            <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994.021-.041.001-.09-.041-.106a13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.929 1.793 8.18 1.793 12.061 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.894.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.028zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
          </svg>
          <span>綁定 Discord 認證</span>
        `;
      }
    }

    if (res.quota) updatePartyQuotaUI(res.quota);
  }).catch(function(err) {
    console.error('獲取組隊 Profile 失敗:', err);
  });
}

function startDiscordOAuthFlow() {
  if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.start_discord_oauth) {
    tt('⚠️ 找不到後端 Discord OAuth 接口', 'error');
    return;
  }
  var btn = document.getElementById('btn-discord-oauth');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span>⏳ 正在開啟瀏覽器授權...</span>`;
  }
  tt('🌐 已開啟瀏覽器，請在 Discord 官方網頁點擊【授權】', 'info');

  pywebview.api.start_discord_oauth().then(function(res) {
    if (btn) btn.disabled = false;
    if (res && res.ok) {
      tt(res.msg || '🎉 Discord 官方身分驗證成功！', 'success');
      loadPartyProfile();
    } else {
      tt(res.msg || '授權未完成或已取消', 'warn');
      loadPartyProfile();
    }
  }).catch(function(err) {
    if (btn) btn.disabled = false;
    tt('驗證過程出錯: ' + err, 'error');
    loadPartyProfile();
  });
}

/**

 * 前往憑證管理綁定 Discord

 */

function goToDiscordBinding() {

  switchPage('credentials');

  tt('💡 請點擊頂部「🔑 登入 / 綁定 Discord」完成授權', 'info');

}

var _partyLastUserAction = Date.now();

var _partyIsIdle = false;

// 監聽使用者活躍行為，超過 45 秒無動作則大廳停止輪詢省額度

window.addEventListener('mousemove', function() { resetPartyIdleTimer(); });

window.addEventListener('keydown', function() { resetPartyIdleTimer(); });

document.addEventListener('visibilitychange', function() {

  if (document.hidden) {

    if (_partyPollTimer) clearTimeout(_partyPollTimer);

  } else if (_isPartyActive) {

    _partyLastUserAction = Date.now();

    _partyIsIdle = false;

    schedulePartyPolling(300);

  }

});

function resetPartyIdleTimer() {

  _partyLastUserAction = Date.now();

  if (_partyIsIdle && _isPartyActive && !_partyCurRoom) {

    _partyIsIdle = false;

    refreshPartyLobby(false);

  }

}

/**

 * 更新頂部雲端大廳連線與狀態徽章 (不再採用本地虛擬計算)

 */

function updatePartyQuotaUI(quota) {

  var badge = document.getElementById('party-quota-badge');

  var textEl = document.getElementById('party-quota-text');

  if (!badge || !textEl) return;

  var dot = badge.querySelector('.quota-dot');

  if (dot) dot.className = 'quota-dot green';

  textEl.textContent = 'Supabase · 充沛';

  badge.title = 'Supabase 全球高速雲端資料庫\n狀態：正常運作中 (高可用無伺服器架構)\n節能機制：閒置/背景自動休眠已啟用';

}

var _partyActiveNav = 'lobby';

var _lobbyBackgroundTick = 0;

/**

 * 處理右上角紅色「創建房間 / 招募隊友」核心動作按鈕

 */

function handlePartyCreateOrRecruit() {

  if (!_partyCurRoom || !_partyCurRoom.room_id) {

    // 尚未在房間中 -> 創建房間並發起招募隊友

    openCreateRoomModal();

  } else {

    // 已經在房間中

    if (_partyActiveNav === 'lobby') {

      // 正在大廳視圖 -> 一鍵切換回我的隊伍房間

      switchPartyNav('room');

    } else {

      // 已經在房間內視圖 -> 執行招募隊友動作 (一鍵複製 6 碼房號並提示好友快速加入)

      copyPartyRoomCode();

    }

  }

}

/**

 * 更新左側 MOBA 側邊欄之當前房間狀態與右上角紅色創建/招募按鈕

 */

function updateSidebarRoomInfo(room) {

  var navRoom = document.getElementById('party-nav-my-room');

  var roomTitle = document.getElementById('party-nav-room-title');

  var roomDot = document.getElementById('party-nav-room-dot');

  var btnCreate = document.getElementById('btn-party-create-room');

  if (room && room.room_id) {

    if (navRoom) {

      navRoom.style.display = 'flex';

      navRoom.classList.remove('disabled');

    }

    if (roomTitle) roomTitle.textContent = '我的隊伍';

    if (roomDot) roomDot.style.display = 'block';

    if (btnCreate) {

      if (_partyActiveNav === 'room') {

        btnCreate.innerHTML = '📢 招募隊友';

        btnCreate.title = '點擊立即複製 6 碼房號發給隊友快速加入';

      } else {

        btnCreate.innerHTML = '🎮 我的隊伍';

        btnCreate.title = '點擊返回當前組隊房間';

      }

    }

  } else {

    if (navRoom) {

      navRoom.style.display = 'none'; // 沒在房間中時隱藏，介面保持純淨

      navRoom.classList.remove('active');

    }

    if (btnCreate) {

      btnCreate.innerHTML = '➕ 創建房間';

      btnCreate.title = '創建專屬組隊房間並開始招募隊友';

    }

  }

}

/**

 * MOBA 側欄收合/展開切換 (圖一小圓圈 < / >)

 */

function toggleMobaSidebar() {

  var sidebar = document.getElementById('party-moba-sidebar');

  var arrow = document.getElementById('moba-collapse-icon');

  if (!sidebar) return;

  var isCol = sidebar.classList.toggle('collapsed');

  if (arrow) {

    arrow.textContent = isCol ? '❯' : '❮';

  }

}

/**

 * MOBA 垂直側欄切換 (圖一風格：隊伍大廳 vs 我的房間)

 * 核心特性：在房間內隨時切換觀看全網大廳，背景心跳不中斷！

 */

function switchPartyNav(target) {

  var navLobby = document.getElementById('party-nav-lobby');

  var navRoom = document.getElementById('party-nav-my-room');

  var lobbyView = document.getElementById('party-lobby-view');

  var roomView = document.getElementById('party-room-view');

  if (target === 'room') {

    if (!_partyCurRoom || !_partyCurRoom.room_id) {

      tt('💡 您目前尚未在房間中，為您開啟創建房間', 'info');

      openCreateRoomModal();

      return;

    }

    _partyActiveNav = 'room';

    if (navLobby) navLobby.classList.remove('active');

    if (navRoom) navRoom.classList.add('active');

    if (lobbyView) { lobbyView.style.display = 'none'; lobbyView.classList.remove('active'); }

    if (roomView) { roomView.style.display = 'flex'; roomView.classList.add('active'); }

    renderRoomView(_partyCurRoom);

  } else {

    _partyActiveNav = 'lobby';

    if (navRoom) navRoom.classList.remove('active');

    if (navLobby) navLobby.classList.add('active');

    if (roomView) { roomView.style.display = 'none'; roomView.classList.remove('active'); }

    if (lobbyView) { lobbyView.style.display = 'flex'; lobbyView.classList.add('active'); }

    refreshPartyLobby(false);

  }

  updateSidebarRoomInfo(_partyCurRoom);

}

/**

 * 檢查當前本機是否已處於某房間內

 */

function checkCurrentPartyRoom() {

  if (window.__tutorialMockPartyActive) return; // 🌟 教學沙盒保護：教學進行中禁止真實後端狀態覆蓋

  if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.get_party_room_details) return;

  pywebview.api.get_party_room_details('').then(function(res) {

    if (window.__tutorialMockPartyActive) return; // 🌟 非同步返回時再次保護

    if (res && res.ok && res.room) {

      _partyCurRoom = res.room;

      updateSidebarRoomInfo(res.room);

      switchPartyNav('room');

      schedulePartyPolling(3000); // 房內成員 3 秒同步

    } else {

      _partyCurRoom = null;

      updateSidebarRoomInfo(null);

      switchPartyNav('lobby');

      refreshPartyLobby(false);

    }

  }).catch(function() {

    if (window.__tutorialMockPartyActive) return;

    _partyCurRoom = null;

    updateSidebarRoomInfo(null);

    switchPartyNav('lobby');

    refreshPartyLobby(false);

  });

}

var _lastManualRefreshTime = 0;

/**

 * 排程下一次輪詢 (智慧節能：背景暫停，大廳閒置 45 秒自動休眠)

 */

function schedulePartyPolling(delay) {

  if (window.__tutorialMockPartyActive) return; // 🌟 教學沙盒保護：教學進行中禁止真實後端輪詢

  if (!_isPartyActive) return;

  if (_partyPollTimer) {
    clearTimeout(_partyPollTimer);
    _partyPollTimer = null;
  }

  // 🌟 動態退避與頻率自適應 (Dynamic Heartbeat & Backoff)
  var nextDelay = delay;
  if (!nextDelay) {
    if (_partyCurRoom) {
      // 活躍狀態判斷：當前位於房間畫面、或處於倒數發車、或正有成員下載部署中
      var isRoomActive = (_partyActiveNav === 'room') || (_partyCountdownTimer !== null);
      if (_partyCurRoom.members && Array.isArray(_partyCurRoom.members)) {
        var hasDownloading = _partyCurRoom.members.some(function(m) {
          return m.status && (m.status.indexOf('下載') !== -1 || m.status.indexOf('部署') !== -1);
        });
        if (hasDownloading) isRoomActive = true;
      }
      
      if (window.PartyP2P && window.PartyP2P.isConnected) {
        nextDelay = 20000; // 🌟 P2P 直連已打通：雲端伺服器輪詢放緩至 20 秒極低頻備援 (節省 80%~95% 請求)
      } else if (isRoomActive) {
        nextDelay = 4000; // 🌟 活躍狀態維持嚴格 4 秒一次 (P2P 尚未打通時之容災備援)
      } else {
        nextDelay = 8000; // 背景/全員就緒空閒狀態動態放緩至 8 秒
      }
    } else {
      nextDelay = 10000; // 大廳狀態 10 秒
    }
  }

  // 若不在房間內且使用者已閒置超過 45 秒，暫停大廳自動輪詢節省額度
  if (!_partyCurRoom && (Date.now() - _partyLastUserAction > 45000)) {
    _partyIsIdle = true;
    return;
  }

  _partyPollTimer = setTimeout(function() {

    if (!_isPartyActive || document.hidden) {
      schedulePartyPolling(10000);
      return;
    }

    if (_partyCurRoom) {

      // 房內成員狀態即時輪詢 (活躍 4 秒)

      pywebview.api.get_party_room_details('').then(function(res) {

        if (res && res.ok && res.room) {

          _partyPollFailures = 0; // 成功重置退避

          _partyCurRoom = res.room;

          updateSidebarRoomInfo(res.room);

          if (_partyActiveNav === 'room') {

            renderRoomView(res.room);

          } else if (_partyActiveNav === 'lobby') {

            // 在房內但同時瀏覽大廳：每 3 次心跳靜默同步一次大廳列表

            if (!_lobbyBackgroundTick) _lobbyBackgroundTick = 0;

            _lobbyBackgroundTick++;

            if (_lobbyBackgroundTick >= 3) {

              _lobbyBackgroundTick = 0;

              refreshPartyLobby(false);

            }

          }

          schedulePartyPolling(); // 自動計算活躍 4 秒或空閒 8 秒

        } else {

          resetPartyReadyCountdown();

          _partyCurRoom = null;

          updateSidebarRoomInfo(null);

          if (res && res.error === 'HOST_OFFLINE') {

            tt('👑 房主已離線，隊伍房間已自動解散', 'warn');

            tt('💡 若剛才已啟動安裝，本機程序不受影響將繼續跑完', 'info');

          } else {

            tt(res && res.msg ? res.msg : '房間已解散或過期蒸發', 'info');

          }

          switchPartyNav('lobby');

          refreshPartyLobby(false);

        }

      }).catch(function() {

        // 異常指數退避 (4s -> 6s -> 9s -> 13.5s -> 最長 16s)
        _partyPollFailures++;
        var backoffDelay = Math.min(16000, Math.round(4000 * Math.pow(1.5, _partyPollFailures)));
        schedulePartyPolling(backoffDelay);

      });

    } else {

      // 大廳公開房間列表輪詢 (10 秒一次)

      refreshPartyLobby(false);

      schedulePartyPolling(10000);

    }

  }, nextDelay);

}

/**

 * 重新拉取大廳房間清單 (支援手動點擊與 CDN 邊緣快取保護)

 */

function refreshPartyLobby(isUserClick) {
  if (window.__tutorialMockPartyActive) {
    return;
  }
  if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.get_lobby_rooms) return;

  var now = Date.now();

  if (isUserClick) {

    if (now - _lastManualRefreshTime < 1200) {

      return;

    }

    _lastManualRefreshTime = now;

  }

  // 刷新按鈕旋轉動效

  var refreshBtn = document.getElementById('party-btn-refresh');

  if (refreshBtn) {

    refreshBtn.classList.add('refreshing');

    refreshBtn.disabled = true;

  }

  if (isUserClick) tt('🌸 正在向雲端大廳同步最新房間…', 'info');

  pywebview.api.get_lobby_rooms().then(function(res) {

    if (refreshBtn) {

      setTimeout(function() {

        refreshBtn.classList.remove('refreshing');

        refreshBtn.disabled = false;

      }, 500);

    }

    if (res && res.quota) updatePartyQuotaUI(res.quota);
    try { fetchAndRefreshCloudMetrics(false); } catch (e) {}

    if (res && res.ok && Array.isArray(res.rooms)) {

      _partyRooms = res.rooms;

      renderLobbyRoomsGrid(_partyRooms);

      if (isUserClick) tt('✅ 大廳已同步至最新狀態', 'ok');

    } else {

      renderLobbyRoomsGrid([]);

      if (isUserClick) tt(res && res.msg ? res.msg : '無法連線至雲端大廳', 'err');

    }

    if (!_partyCurRoom) schedulePartyPolling(10000);

  }).catch(function(err) {

    if (refreshBtn) {

      refreshBtn.classList.remove('refreshing');

      refreshBtn.disabled = false;

    }

    renderLobbyRoomsGrid([]);

    if (!_partyCurRoom) schedulePartyPolling(10000);

  });

}

/**

 * 兼容舊呼叫的顯示大廳

 */

function renderLobbyView() {

  switchPartyNav('lobby');

}

/**

 * 渲染大廳房間卡片網格

 */

function renderLobbyRoomsGrid(rooms) {
  if (window.__tutorialMockPartyActive) {
    return;
  }
  var navCount = document.getElementById('party-nav-lobby-count');

  if (navCount) {

    navCount.textContent = (Array.isArray(rooms) ? rooms.length : 0);

  }

  var container = document.getElementById('party-rooms-container');

  if (!container) return;

  var filterKw = (_partySearchKeyword || '').trim().toLowerCase();

  var filtered = rooms.filter(function(r) {

    if (!filterKw) return true;

    var gn = (r.game_name || '').toLowerCase();

    var hn = (r.host_name || '').toLowerCase();

    var rid = (r.room_id || '').toLowerCase();

    var aid = (r.appid || '').toLowerCase();

    return gn.indexOf(filterKw) !== -1 || hn.indexOf(filterKw) !== -1 || rid.indexOf(filterKw) !== -1 || aid.indexOf(filterKw) !== -1;

  });

  if (!filtered.length) {

    container.innerHTML = '<div class="empty" style="grid-column:1/-1;padding:40px 0">' +

      '<div class="icon">🎮</div>' +

      '<p>' + (filterKw ? '找不到吻合搜尋條件的房間' : '目前全網暫無公開組隊房間，點擊右上角「➕ 創建房間」率先開房吧！') + '</p>' +

      '</div>';

    return;

  }

  var html = '';

  filtered.forEach(function(r) {

    var rid = r.room_id || 'UNKNOWN';

    var gameName = r.game_name || '未知遊戲';

    var appid = r.appid ? String(r.appid).trim() : '';

    var hostName = r.host_name || '神祕房主';

    var curPlayers = r.current_players || 1;

    var maxPlayers = r.max_players || 4;

    var isFull = curPlayers >= maxPlayers;

    var cleanNote = (r.note || '').trim();
    if (cleanNote.startsWith('[NOTE]:')) cleanNote = cleanNote.slice(7);
    if (cleanNote.indexOf('[CONTACT]:') !== -1) cleanNote = cleanNote.split('[CONTACT]:')[0].trim();
    var note = cleanNote ? ('<div class="party-room-card-note">' + escapeHtml(cleanNote) + '</div>') : '';

    

    // Steam 遊戲橫幅封面

    var coverImg = appid ? 'https://cdn.cloudflare.steamstatic.com/steam/apps/' + appid + '/header.jpg' : '';

    html += '<div class="party-room-card">' +

      '<div class="party-card-cover-wrap">' +

        (coverImg ? '<img src="' + coverImg + '" class="party-card-cover" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'">' : '') +

        '<div class="party-card-cover-fallback" style="' + (coverImg ? 'display:none' : 'display:flex') + '">🎮</div>' +

        '<div class="party-card-badge-id">#' + rid + '</div>' +

        '<div class="party-card-badge-players ' + (isFull ? 'full' : '') + '">👥 ' + curPlayers + ' / ' + maxPlayers + '</div>' +

      '</div>' +

      '<div class="party-card-body">' +

        '<div class="party-card-game-title" title="' + escapeHtml(gameName) + '">' + escapeHtml(gameName) + '</div>' +

        '<div class="party-card-host-row">' +

          '<span class="host-label">房主：</span>' +

          '<span class="host-name" title="' + escapeHtml(hostName) + '">' + escapeHtml(hostName) + '</span>' +

        '</div>' +

        note +

      '</div>' +

      '<div class="party-card-footer">' +

        '<button class="btn btn-p btn-s party-join-btn ' + (isFull ? 'disabled' : '') + '" onclick="joinPartyRoom(\'' + rid + '\')" ' + (isFull ? 'disabled' : '') + '>' +

          (isFull ? '🚫 房間已滿' : '🚀 立即加入') +

        '</button>' +

      '</div>' +

    '</div>';

  });

  container.innerHTML = html;

}

/**

 * 搜尋框即時過濾

 */

function onPartySearchInput() {

  var input = document.getElementById('party-search-input');

  _partySearchKeyword = input ? input.value : '';

  renderLobbyRoomsGrid(_partyRooms);

}

/**

 * 快速依 6 碼房號加入

 */

function quickJoinPartyRoom() {
  if (!_partyProfile || !_partyProfile.is_discord_verified) {
    tt('🛡️ 為維護大廳安全秩序，請先完成頂部 Discord 官方身分認證！', 'warn');
    startDiscordOAuthFlow();
    return;
  }

  var input = document.getElementById('party-quick-code');

  if (!input) return;

  var code = (input.value || '').trim().toUpperCase();

  if (!code) {

    tt('請輸入邀請碼', 'warn');

    return;

  }

  joinPartyRoom(code);

}

/**

 * 加入指定房間

 */

function joinPartyRoom(roomId) {
  if (!_partyProfile || !_partyProfile.is_discord_verified) {
    tt('🛡️ 為維護大廳安全秩序，請先完成頂部 Discord 官方身分認證！', 'warn');
    startDiscordOAuthFlow();
    return;
  }

  if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.join_party_room) return;

  tt('🌸 正在加入房間 #' + roomId + '…', 'info');

  pywebview.api.join_party_room(roomId).then(function(res) {
    if (res && res.ok && res.room) {
      tt(res.msg || '成功進入房間 #' + roomId, 'ok');
      _partyCurRoom = res.room;
      updateSidebarRoomInfo(res.room);
      switchPartyNav('room');
      renderRoomView(res.room);
      startRoomSync();
    } else {
      tt((res && res.msg) || '加入房間失敗', 'err');
    }
  }).catch(function(err) {
    tt('加入房間異常：' + err, 'err');
  });
}

/**
 * 渲染房間詳情視圖
 */
function renderRoomView(room) {
  if (!room) return;
  _partyCurRoom = room;

  var rid = room.id || room.room_id || '';
  var hostName = room.host_name || room.host_player_name || '房主';
  var hostDiscord = room.host_discord || room.host_discord_name || '';
  var gameName = room.game_name || room.app_name || '未知遊戲';
  var maxPlayers = room.max_players || 4;
  var members = room.members || [];
  var myName = (_partyProfile && _partyProfile.player_name) || '';
  var isHost = isHostUser(room);

  // 標題與基本資訊
  var titleEl = document.getElementById('party-room-title');
  if (titleEl) titleEl.textContent = '【' + gameName + '】專屬組隊房間';

  var codeEl = document.getElementById('party-room-code-display');
  if (codeEl) codeEl.textContent = rid;

  var hostVal = document.getElementById('party-room-host-val');
  if (hostVal) hostVal.textContent = '👑 ' + hostName + (hostDiscord ? ' (' + hostDiscord + ')' : '');

  var playersVal = document.getElementById('party-room-players-val');

  // 備註展示 (過濾掉 [NOTE]: 與 [CONTACT]: 避免被聯絡資訊污染)
  var noteEl = document.getElementById('party-room-note-val');
  if (noteEl) {
    var rawNote = (room.note || '').trim();
    if (rawNote.startsWith('[NOTE]:')) rawNote = rawNote.slice(7);
    if (rawNote.indexOf('[CONTACT]:') !== -1) rawNote = rawNote.split('[CONTACT]:')[0].trim();
    if (rawNote) {
      noteEl.textContent = '📢 招募備註：' + rawNote;
      noteEl.style.display = 'block';
    } else {
      noteEl.style.display = 'none';
    }
  }

  // 房主專屬：預填聯絡資訊卡片顯示與同步 (支援開房後隨時調整)
  var preContactWrap = document.getElementById('party-room-pre-contact-wrap');
  var preContactInput = document.getElementById('party-room-pre-contact-input');
  if (preContactWrap) {
    if (isHost && !_partyContactSubmitted) {
      preContactWrap.style.display = 'block';
      if (preContactInput && !preContactInput.value) {
        var defaultContact = _partyPreFilledContact || localStorage.getItem('smu_party_pre_contact') || '';
        if (defaultContact) {
          savePartyPreFilledContact(defaultContact);
        }
      }
    } else {
      preContactWrap.style.display = 'none';
    }
  }

  // 渲染所有成員列表 (以 members 陣列為單一真實來源，去重並置頂房主)
  var listContainer = document.getElementById('party-members-list');
  if (!listContainer) return;

  var allMembers = [];
  var seenIds = {};

  if (!members || members.length === 0) {
    allMembers.push({
      id: room.host_id || 'host',
      name: hostName,
      discord_name: hostDiscord,
      status: '就緒',
      progress: 100,
      is_host: true
    });
  } else {
    members.forEach(function(m) {
      var mId = m.id || m.name;
      if (seenIds[mId]) return; // 依唯一 ID 去重，徹底杜絕重複
      seenIds[mId] = true;

      var isHostMember = (m.is_host === true) || (m.id && room.host_id && m.id === room.host_id) || (m.name === hostName);
      allMembers.push({
        id: m.id || '',
        name: m.name || '玩家',
        discord_name: m.discord || m.discord_name || (isHostMember ? hostDiscord : ''),
        status: m.status || '未下載',
        progress: m.progress !== undefined ? m.progress : 0,
        is_host: isHostMember,
        steam_installed: !!m.steam_installed,
        deploy_status: m.deploy_status || 'pending',
        deploy_error: m.deploy_error || '',
        version_status: m.version_status || '最新'
      });
    });
  }

  // 確保房主置頂
  allMembers.sort(function(a, b) {
    if (a.is_host && !b.is_host) return -1;
    if (!a.is_host && b.is_host) return 1;
    return 0;
  });

  // 更新即時人數 (準確以 allMembers 總數呈現)
  if (playersVal) playersVal.textContent = '👥 ' + allMembers.length + ' / ' + maxPlayers + ' 人';

  // 檢查是否全員就緒 (房間人數 >= 2 且全部成員進度 100% 且部署成功)
  var isAllReady = (allMembers.length >= 2) && allMembers.every(function(m) {
    return (m.status === '就緒' || m.progress >= 100) && (m.deploy_status === 'success' || !m.deploy_status);
  });

  if (isAllReady) {
    updateAllReadyBannerUI(isHost, rid, hostDiscord, allMembers);
  } else {
    resetPartyReadyCountdown();
    var allReadyBanner = document.getElementById('party-all-ready-banner');
    if (allReadyBanner) allReadyBanner.style.display = 'none';
  }

  // 取得自己的本機狀態展示
  var myId = (_partyProfile && _partyProfile.client_id) || '';
  var myMemberObj = allMembers.find(function(m) {
    return (m.id && myId && m.id === myId) || (m.name === myName);
  });

  var myStatusBadge = document.getElementById('party-my-status-badge');
  var syncBtnWrap = document.getElementById('party-sync-btn-wrap');
  var syncBtn = document.getElementById('party-btn-start-sync');

  var isMyReady = false;
  var isMyDownloading = false;

  if (myMemberObj) {
    var myStatus = myMemberObj.status || '未下載';
    isMyReady = (myStatus === '就緒' || (myMemberObj.progress >= 100) || myMemberObj.deploy_status === 'success');
    var isPendingPatch = (myStatus === '待部署補丁' || (myMemberObj.steam_installed && !isMyReady && myMemberObj.deploy_status !== 'downloading' && myMemberObj.deploy_status !== 'deploying'));

    if (isMyReady || myMemberObj.deploy_status === 'failed') {
      window._partyLocalInstalling = false;
    }

    // 🌟 嚴格判定動態進行中狀態：
    isMyDownloading = !isMyReady && !isPendingPatch && (
      window._partyLocalInstalling === true ||
      myMemberObj.deploy_status === 'downloading' ||
      myMemberObj.deploy_status === 'deploying' ||
      (myMemberObj.progress && myMemberObj.progress > 0) ||
      myStatus === '下載中' ||
      myStatus.indexOf('下載') !== -1 ||
      myStatus.indexOf('正在') !== -1 ||
      myStatus.indexOf('合併') !== -1 ||
      myStatus.indexOf('Steam') !== -1 ||
      myStatus.indexOf('部署') !== -1 ||
      myStatus.indexOf('準備') !== -1 ||
      myStatus.indexOf('等待') !== -1
    );

    if (myStatusBadge) {
      myStatusBadge.textContent = myStatus;
      myStatusBadge.className = 'my-status-badge ' + (isMyReady ? 'ready' : (isMyDownloading ? 'downloading' : (isPendingPatch ? 'pending_patch' : 'not_downloaded')));
    }

    // 🌟 更新「我的本機狀態」右側進度條
    var myProgContainer = document.getElementById('party-my-progress-container');
    var myProgStage = document.getElementById('party-my-progress-stage');
    var myProgPct = document.getElementById('party-my-progress-pct');
    var myProgBarInner = document.getElementById('party-my-progress-bar-inner');
    if (myProgContainer && myProgStage && myProgPct && myProgBarInner) {
      if (isMyReady) {
        myProgStage.innerHTML = '<span style="color:#4CAF50">✅ 遊戲與聯機環境已完全就緒</span>';
        myProgPct.textContent = '100%';
        myProgBarInner.style.width = '100%';
        myProgBarInner.className = 'party-my-progress-bar-inner ready';
      } else if (isPendingPatch) {
        myProgStage.innerHTML = '<span style="color:#FFA726">📦 遊戲主程式已安裝，請點擊右側按鈕套用補丁</span>';
        myProgPct.textContent = '90%';
        myProgBarInner.style.width = '90%';
        myProgBarInner.className = 'party-my-progress-bar-inner active';
      } else if (isMyDownloading) {
        var pctVal = Math.max(5, Math.min(99, myMemberObj.progress || 5));
        var stageDesc = myStatus;
        if (!stageDesc || stageDesc === '下載中' || stageDesc === '未下載' || stageDesc === '等待下載') {
          stageDesc = '正在下載與部署資源…';
        }
        myProgStage.innerHTML = '<span class="spinner" style="width:11px;height:11px;margin-right:4px"></span> <span>' + escapeHtml(stageDesc) + '</span>';
        myProgPct.textContent = pctVal + '%';
        myProgBarInner.style.width = pctVal + '%';
        myProgBarInner.className = 'party-my-progress-bar-inner active';
      } else if (myMemberObj.deploy_status === 'failed') {
        var errShort = myMemberObj.deploy_error ? (' (' + myMemberObj.deploy_error.slice(0, 30) + ')') : '';
        myProgStage.innerHTML = '<span style="color:#F44336">❌ 部署失敗' + escapeHtml(errShort) + '</span>';
        myProgPct.textContent = '0%';
        myProgBarInner.style.width = '0%';
        myProgBarInner.className = 'party-my-progress-bar-inner';
      } else {
        myProgStage.innerHTML = '<span style="color:var(--gray)">未安裝，請點擊右側按鈕開始一鍵安裝</span>';
        myProgPct.textContent = '0%';
        myProgBarInner.style.width = '0%';
        myProgBarInner.className = 'party-my-progress-bar-inner';
      }
    }
  }

  // 1. 隊員端：未就緒時顯示按鈕
  var showInstallBtn = !isMyReady && !isHost;
  if (syncBtnWrap) {
    syncBtnWrap.style.display = showInstallBtn ? 'block' : 'none';
  } else if (syncBtn) {
    syncBtn.style.display = showInstallBtn ? 'inline-flex' : 'none';
  }

  if (syncBtn) {
    if (isMyDownloading) {
      syncBtn.disabled = true;
      syncBtn.innerHTML = '<span class="spinner"></span> 正在一鍵安裝中…';
    } else if (isPendingPatch) {
      syncBtn.disabled = false;
      syncBtn.innerHTML = '🚀 套用線上補丁';
    } else {
      syncBtn.disabled = false;
      syncBtn.innerHTML = '🚀 一鍵安裝';
    }
  }

  // 2. 徹底移除/隱藏額外手動下載整合包按鈕
  var pkgWrap = document.getElementById('party-gdrive-pkg-wrap');
  if (pkgWrap) {
    pkgWrap.style.display = 'none';
  }

  var html = '';
  allMembers.forEach(function(m, idx) {
    var name = m.name || '玩家';
    var status = m.status || '未下載';
    var progress = m.progress || 0;
    var isMe = (m.id && myId && m.id === myId) || (m.name === myName);

    var isReady = (status === '就緒' || progress >= 100 || m.deploy_status === 'success');
    var isMemberPendingPatch = (status === '待部署補丁' || (m.steam_installed && !isReady && m.deploy_status !== 'downloading' && m.deploy_status !== 'deploying'));
    var isDownloading = !isReady && status !== '未下載' && !isMemberPendingPatch && (
      status === '下載中' ||
      m.deploy_status === 'downloading' ||
      m.deploy_status === 'deploying' ||
      (status.indexOf('下載中') !== -1) ||
      status.indexOf('正在') !== -1 ||
      status.indexOf('合併中') !== -1 ||
      status.indexOf('Steam下載') !== -1
    );

    var statusDisplay = '';
    if (isReady) {
      statusDisplay = '下載狀況(就緒)';
    } else if (isMemberPendingPatch) {
      statusDisplay = '下載狀況(待部署補丁)';
    } else if (isDownloading) {
      if (status && status !== '未下載' && status !== '下載中') {
        statusDisplay = '下載狀況(' + status + ')';
      } else {
        statusDisplay = '下載狀況(下載中: ' + progress + '%)';
      }
    } else {
      statusDisplay = '下載狀況(未下載)';
    }

    var statusClass = isReady ? 'status-ready' : (isDownloading ? 'status-downloading' : (isMemberPendingPatch ? 'status-pending' : 'status-not-downloaded'));

    var inlineBarHtml = '';
    if (isDownloading || isMemberPendingPatch) {
      var barPct = isMemberPendingPatch ? Math.max(90, progress || 90) : progress;
      var barClass = isMemberPendingPatch ? 'member-inline-progress-bar pending' : 'member-inline-progress-bar downloading';
      inlineBarHtml = '<div class="member-inline-progress-wrap" title="即時安裝進度: ' + barPct + '%">' +
        '<div class="' + barClass + '" style="width:' + barPct + '%"></div>' +
        '</div>' +
        '<span class="member-inline-progress-pct">' + barPct + '%</span>';
    } else if (isReady) {
      inlineBarHtml = '<div class="member-inline-progress-wrap" title="已就緒 100%">' +
        '<div class="member-inline-progress-bar ready" style="width:100%"></div>' +
        '</div>' +
        '<span class="member-inline-progress-pct" style="color:#4CAF50">100%</span>';
    }

    var verHtml = '';
    var vSt = m.version_status || '最新';
    if (vSt === '最新') {
      verHtml = '<span class="member-version-badge ok">最新 ✅</span>';
    } else if (vSt.indexOf('舊') !== -1) {
      verHtml = '<span class="member-version-badge warn">⚠️ ' + escapeHtml(vSt) + '</span>';
    } else if (vSt === '未安裝') {
      verHtml = '<span class="member-version-badge gray">未安裝</span>';
    } else {
      verHtml = '<span class="member-version-badge ok">' + escapeHtml(vSt) + '</span>';
    }

    var isDeployFailed = (m.deploy_status === 'failed');
    var isAvBlocked = isDeployFailed && (m.deploy_error && (m.deploy_error.indexOf('防毒') !== -1 || m.deploy_error.indexOf('Defender') !== -1));
    var statusTextHtml = '<span class="member-status-text ' + statusClass + '">' + escapeHtml(statusDisplay) + '</span>';
    if (isDeployFailed) {
      if (isAvBlocked) {
        statusTextHtml = '<span class="member-status-text status-failed" style="color:#F44336;font-weight:700">❌ 部署失敗 (防毒軟體攔截)</span>';
      } else {
        statusTextHtml = '<span class="member-status-text status-failed" style="color:#F44336;font-weight:700">❌ 部署失敗' + (m.deploy_error ? (': ' + escapeHtml(m.deploy_error)) : '') + '</span>';
      }
    }

    var barClass = isReady ? 'ready' : (isDownloading ? 'downloading' : '');

    html += '<div class="party-member-card ' + (isMe ? 'is-me' : '') + '">' +
      '<div class="member-card-left">' +
        '<div class="member-avatar-wrap">' +
          '<div class="member-avatar-icon">' + (m.is_host ? '👑' : '🎮') + '</div>' +
        '</div>' +
        '<div class="member-info-column">' +
          '<div class="member-identity-row">' +
            '<span class="member-primary-name">' + escapeHtml(name) + '</span>' +
            verHtml +
            (m.is_host ? '<span class="member-badge-host">房主</span>' : '') +
            (isMe ? '<span class="member-badge-me">我</span>' : '') +
          '</div>' +
          '<div class="member-status-row" style="display:flex;align-items:center;flex-wrap:wrap;gap:6px">' +
            statusTextHtml +
            inlineBarHtml +
            (isMe && isAvBlocked ? '<button class="btn btn-o btn-xs" style="font-size:10.5px;color:#F44336;border-color:rgba(244,67,54,0.4);padding:0px 6px;height:20px;border-radius:4px;cursor:pointer" onclick="openDefenderExclusionHelper(\'' + escapeHtml(room.appid) + '\')">🛡️ 排查防毒攔截</button>' : '') +
          '</div>' +
        '</div>' +
      '</div>' +
      '<div class="member-card-right">' +
        '<div class="member-progress-outer" title="安裝進度: ' + (isReady ? 100 : progress) + '%">' +
          '<div class="member-progress-bar ' + barClass + '" style="width:' + (isReady ? 100 : progress) + '%"></div>' +
        '</div>' +
      '</div>' +
    '</div>';
  });

  listContainer.innerHTML = html;
}

/**
 * 🌟 全員就緒 1 分鐘倒數、+5 分鐘延遲 (限 2 次) 與提示橫幅控制
 */
function updateAllReadyBannerUI(isHost, rid, hostDiscord, allMembers) {
  var allReadyBanner = document.getElementById('party-all-ready-banner');
  if (!allReadyBanner) return;

  allReadyBanner.style.display = 'flex';

  var preContact = (_partyPreFilledContact || '').trim();

  // 1. 若倒數未啟動，啟動 1 分鐘 (60 秒) 倒數
  if (!_partyCountdownTimer && !_partyContactSubmitted) {
    if (_partyCountdownSeconds <= 0) {
      _partyCountdownSeconds = 60;
    }
    _partyCountdownTimer = setInterval(function() {
      _partyCountdownSeconds--;
      var cdSecEl = document.getElementById('party-cd-sec');
      if (cdSecEl) cdSecEl.textContent = formatCountdownDisplay(_partyCountdownSeconds);

      if (_partyCountdownSeconds <= 0) {
        clearInterval(_partyCountdownTimer);
        _partyCountdownTimer = null;
        if (isHost && !_partyContactSubmitted) {
          // 1 分鐘倒數結束，房主自動發布資訊並解散房間
          finishPartyAndBroadcast();
        } else if (!isHost) {
          tt('隊伍組隊完成，房間已結束', 'info');
          leaveOrCloseCurrentRoom(true);
        }
      }
    }, 1000);

    // 隊員端啟動高頻輪詢 (0.5 秒一次輕量請求，直到取得房主資訊)
    if (!isHost) {
      startMemberContactPolling(rid);
    }
  }

  // 2. 構建 UI 結構 (防重繪機制：避免心跳輪詢銷毀 input 導致失焦或取消輸入法)
  var bannerContentEl = allReadyBanner.querySelector('.banner-content');
  if (!bannerContentEl) return;

  var currentMode = isHost ? 'host-ready-panel' : 'member-ready-panel';

  // 🌟 若模式未變，僅平滑更新秒數與延遲按鈕狀態，絕不重寫 innerHTML
  if (bannerContentEl.dataset.mode === currentMode) {
    var cdSecEl = document.getElementById('party-cd-sec');
    if (cdSecEl) cdSecEl.textContent = formatCountdownDisplay(_partyCountdownSeconds);
    var delayBtn = document.getElementById('party-btn-delay-countdown');
    if (delayBtn) {
      var leftTimes = Math.max(0, 2 - _partyDelayCount);
      delayBtn.textContent = '⏳ 延遲 5 分鐘 (剩餘 ' + leftTimes + ' 次)';
      delayBtn.disabled = (_partyDelayCount >= 2);
    }
    return;
  }

  bannerContentEl.dataset.mode = currentMode;

  var contentHtml = '';
  if (isHost) {
    var leftTimes = Math.max(0, 2 - _partyDelayCount);
    var prePromptHtml = '';
    if (!preContact && !_partyContactInputText) {
      prePromptHtml = '<div style="color:#E65100;font-size:11.5px;font-weight:700">⚠️ 您尚未填寫預填聯絡資訊，請填寫；若倒數結束未填寫，系統將自動附帶好友申請指引！</div>';
    } else if (preContact) {
      prePromptHtml = '<div style="color:#1976D2;font-size:11.5px">💡 已偵測到預填資訊：<strong>' + escapeHtml(preContact) + '</strong>，點擊右側按鈕即可一鍵發布並完成組隊！</div>';
    }

    contentHtml = 
      '<div class="banner-title">🎉 全員已就緒！等待房主發送聯絡資訊 (倒數 <span id="party-cd-sec" class="banner-cd-sec">' + formatCountdownDisplay(_partyCountdownSeconds) + '</span>)</div>' +
      '<div class="banner-desc">' +
        prePromptHtml +
        '<div class="banner-contact-row" style="margin-top:6px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">' +
          '<input type="text" id="party-contact-input" class="party-contact-input" placeholder="例如：+dc: username 或 語音群組/連線房號" value="' + escapeHtml(_partyContactInputText || preContact) + '" oninput="_partyContactInputText=this.value" onkeydown="if(event.key===\'Enter\') finishPartyAndBroadcast()" autofocus style="flex:1;min-width:220px;max-width:320px" />' +
          '<button class="btn btn-p btn-s" id="party-btn-finish-party" onclick="finishPartyAndBroadcast()" style="font-weight:800;background:linear-gradient(135deg,#2EA043,#238636);box-shadow:0 2px 10px rgba(46,160,67,0.35)">🚀 完成組隊並發布資訊 (解散房間)</button>' +
          '<button class="btn btn-o btn-s" id="party-btn-delay-countdown" onclick="delayPartyReadyCountdown()" ' + (_partyDelayCount >= 2 ? 'disabled' : '') + '>⏳ 延遲 5 分鐘 (剩餘 ' + leftTimes + ' 次)</button>' +
        '</div>' +
      '</div>';
  } else {
    // 隊員端 UI
    contentHtml = 
      '<div class="banner-title">🎉 全員已就緒！等待房主發送聯絡資訊 (倒數 <span id="party-cd-sec" class="banner-cd-sec">' + formatCountdownDisplay(_partyCountdownSeconds) + '</span>)</div>' +
      '<div class="banner-desc" id="party-wait-contact-text">房主正在確認或輸入聯絡資訊，請稍候… 資訊發布後將自動呈現於螢幕正中央！</div>';
  }

  bannerContentEl.innerHTML = contentHtml;
}

/**
 * 格式化秒數顯示 (例如 60 -> 01:00, 350 -> 05:50, 45 -> 45 秒)
 */
function formatCountdownDisplay(totalSecs) {
  var s = Math.max(0, totalSecs);
  if (s >= 60) {
    var m = Math.floor(s / 60);
    var rem = s % 60;
    return m + ' 分 ' + (rem < 10 ? '0' : '') + rem + ' 秒';
  }
  return s + ' 秒';
}

/**
 * 房主手動延遲 5 分鐘 (+300 秒，最多 2 次)
 */
function delayPartyReadyCountdown() {
  if (_partyDelayCount >= 2) {
    tt('⚠️ 延遲次數已達上限 (最多支援 2 次)', 'warn');
    return;
  }
  _partyDelayCount++;
  _partyCountdownSeconds += 300;
  tt('⏳ 已為房間延長 5 分鐘！當前剩餘延遲次數：' + (2 - _partyDelayCount) + ' 次', 'ok');
  var cdSecEl = document.getElementById('party-cd-sec');
  if (cdSecEl) cdSecEl.textContent = formatCountdownDisplay(_partyCountdownSeconds);
  var delayBtn = document.getElementById('party-btn-delay-countdown');
  if (delayBtn) {
    var leftTimes = Math.max(0, 2 - _partyDelayCount);
    delayBtn.textContent = '⏳ 延遲 5 分鐘 (剩餘 ' + leftTimes + ' 次)';
    if (_partyDelayCount >= 2) delayBtn.disabled = true;
  }
}

/**
 * 房主點擊「🚀 完成組隊並發布資訊 (解散房間)」或倒數歸零自動執行
 * 核心流程：發布聯絡資訊 -> 立即解散房間 -> 在 SMU 畫面正中央彈出房主端高亮慶祝卡片
 */
function finishPartyAndBroadcast() {
  if (!_partyCurRoom || _partyContactSubmitted) return;
  var rid = _partyCurRoom.room_id;
  var inputEl = document.getElementById('party-contact-input');
  var text = (inputEl ? inputEl.value : '') || _partyContactInputText || _partyPreFilledContact || '';
  text = text.trim();

  // 🌟 若沒有填入任何預填入或是手動填入聯絡資訊，則向房間發送預設求友文案
  if (!text) {
    var hostDcId = (_partyProfile && (_partyProfile.discord_username || _partyProfile.discord)) || (_partyCurRoom.host_discord) || ((_partyProfile && _partyProfile.nickname) || '房主');
    text = "房主未留任何資料，請自行申請好友DC+：'" + hostDcId + "'";
  }

  _partyContactInputText = text;
  _partyContactSubmitted = true;

  if (_partyCountdownTimer) {
    clearInterval(_partyCountdownTimer);
    _partyCountdownTimer = null;
  }

  // 暫存全體成員資料，供中央卡片展示
  var membersCopy = Array.isArray(_partyCurRoom.members) ? JSON.parse(JSON.stringify(_partyCurRoom.members)) : [];

  var btn = document.getElementById('party-btn-finish-party');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> 正在完成組隊並解散…';
  }

  tt('🎉 正在發布聯絡資訊並解散房間…', 'info');

  // 1. 發送聯絡資訊至伺服器
  pywebview.api.send_party_contact_info(rid, text).then(function(sendRes) {
    // 2. 解散刪除房間
    pywebview.api.close_party_room().then(function() {
      resetPartyReadyCountdown();
      _partyCurRoom = null;
      updateSidebarRoomInfo(null);
      switchPartyNav('lobby');
      refreshPartyLobby(false);

      // 3. 在 SMU 畫面正中央彈出房主端高亮卡片
      showPartyHostCompletionCentralModal(membersCopy, text);
    }).catch(function(err) {
      resetPartyReadyCountdown();
      _partyCurRoom = null;
      updateSidebarRoomInfo(null);
      switchPartyNav('lobby');
      refreshPartyLobby(false);
      showPartyHostCompletionCentralModal(membersCopy, text);
    });
  }).catch(function(err) {
    tt('發送連線出錯: ' + err, 'er');
    _partyContactSubmitted = false;
    if (btn) {
      btn.disabled = false;
      btn.textContent = '🚀 完成組隊並發布資訊 (解散房間)';
    }
  });
}

/**
 * 隊員端極輕量輪詢獲取房主資訊 (每 0.5 秒發一次請求，直到取得為止)
 */
function startMemberContactPolling(rid) {
  if (_partyContactPollingTimer) return;
  _partyContactPollingTimer = setInterval(function() {
    if (!_partyCurRoom || _partyCurRoom.room_id !== rid) {
      clearInterval(_partyContactPollingTimer);
      _partyContactPollingTimer = null;
      return;
    }
    pywebview.api.get_party_contact_info(rid).then(function(res) {
      if (res && (res.has_contact || res.is_closed || res.status === 'completed')) {
        clearInterval(_partyContactPollingTimer);
        _partyContactPollingTimer = null;

        var contact = (res.contact_info || '').trim();
        var hostName = (_partyCurRoom && _partyCurRoom.host_name) || '房主';
        var hostDc = (res.host_discord) || (_partyCurRoom && _partyCurRoom.host_discord) || hostName;

        if (!contact) {
          contact = "房主未留任何資料，請自行申請好友DC+：'" + hostDc + "'";
        }

        tt('🎉 房主已完成組隊！正在載入連線資訊…', 'ok');

        // 清理本地狀態並返回大廳
        resetPartyReadyCountdown();
        _partyCurRoom = null;
        updateSidebarRoomInfo(null);
        switchPartyNav('lobby');
        refreshPartyLobby(false);

        // 在 SMU 畫面正中央彈出隊員端高亮卡片
        showPartyMemberCompletionCentralModal(hostName, hostDc, contact);
      }
    }).catch(function() {});
  }, 500); // 0.5 秒一次極輕量查詢 (select=room_id,status,note,updated_at)
}

/**
 * 👑 房主端：在 SMU 畫面正中央彈出組隊完成高亮卡片
 */
function showPartyHostCompletionCentralModal(members, contactText) {
  var oldModal = document.getElementById('modal-party-host-completion-central');
  if (oldModal) oldModal.remove();

  var nonHostMembers = (members || []).filter(function(m) { return !m.is_host; });
  var membersHtml = '';
  if (nonHostMembers.length > 0) {
    membersHtml = nonHostMembers.map(function(m) {
      var dcTag = m.discord || m.discord_name || '';
      var dcDisplay = dcTag ? ('@' + escapeHtml(dcTag.replace(/^@/, ''))) : '未綁定 Discord';
      return '<div class="party-completion-member-item" style="display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:8px;margin-bottom:6px">' +
        '<div style="display:flex;align-items:center;gap:8px">' +
          '<span style="font-size:16px">🎮</span>' +
          '<span style="font-weight:700;color:var(--fg);font-size:13px">' + escapeHtml(m.name) + '</span>' +
        '</div>' +
        '<div style="display:flex;align-items:center;gap:6px">' +
          '<span style="color:#5865F2;font-weight:800;font-size:12.5px">' + dcDisplay + '</span>' +
          (dcTag ? '<button class="btn btn-o btn-xs" style="padding:1px 6px;font-size:10.5px" onclick="copyContactText(\'' + escapeHtml(dcTag) + '\')">📋 複製</button>' : '') +
        '</div>' +
      '</div>';
    }).join('');
  } else {
    membersHtml = '<div style="color:var(--gray);font-size:12px;text-align:center;padding:10px 0">隊伍成員已全數就緒並完成接收</div>';
  }

  var modal = document.createElement('div');
  modal.id = 'modal-party-host-completion-central';
  modal.className = 'party-central-completion-overlay';
  modal.innerHTML = 
    '<div class="party-central-completion-card host-theme" onclick="event.stopPropagation()">' +
      '<div class="party-completion-badge-top">👑 組隊圓滿完成</div>' +
      '<div class="party-completion-icon-ring">🎉</div>' +
      '<h2 class="party-completion-title">恭喜完成組隊！</h2>' +
      '<p class="party-completion-subtitle">您已成功組織並完成隊伍開拔，聯絡資訊已自動同步至全體隊員，房間已圓滿解散！</p>' +
      
      '<div class="party-completion-section">' +
        '<div class="party-completion-sec-title">👥 全體隊員 Discord 聯絡清單：</div>' +
        '<div class="party-completion-members-box" style="max-height:160px;overflow-y:auto">' +
          membersHtml +
        '</div>' +
      '</div>' +

      '<div class="party-completion-section" style="margin-top:12px">' +
        '<div class="party-completion-sec-title">📢 您剛才發布的聯絡資訊：</div>' +
        '<div class="party-completion-contact-box" style="background:rgba(46,160,67,0.1);border:1px solid rgba(46,160,67,0.3);padding:10px 14px;border-radius:10px;color:#2EA043;font-weight:800;font-size:13.5px;word-break:break-all">' +
          escapeHtml(contactText) +
        '</div>' +
      '</div>' +

      '<div style="margin-top:20px;display:flex;justify-content:center">' +
        '<button class="btn btn-p btn-m party-completion-btn-close" onclick="closePartyCompletionCentralModal(\'modal-party-host-completion-central\')" style="padding:10px 32px;font-size:14px;font-weight:800;background:linear-gradient(135deg,#2EA043,#238636);box-shadow:0 4px 16px rgba(46,160,67,0.4)">👥 返回組隊大廳</button>' +
      '</div>' +
    '</div>';

  document.body.appendChild(modal);
}

/**
 * ⚔️ 隊員端：在 SMU 畫面正中央彈出組隊完成高亮卡片
 */
function showPartyMemberCompletionCentralModal(hostName, hostDc, contactText) {
  var oldModal = document.getElementById('modal-party-member-completion-central');
  if (oldModal) oldModal.remove();

  var isDefaultFallback = contactText.indexOf('房主未留任何資料') !== -1;

  var modal = document.createElement('div');
  modal.id = 'modal-party-member-completion-central';
  modal.className = 'party-central-completion-overlay';
  modal.innerHTML = 
    '<div class="party-central-completion-card member-theme" onclick="event.stopPropagation()">' +
      '<div class="party-completion-badge-top member">⚔️ 組隊圓滿完成</div>' +
      '<div class="party-completion-icon-ring member">🎮</div>' +
      '<h2 class="party-completion-title">恭喜完成組隊！</h2>' +
      '<p class="party-completion-subtitle">全體隊員補丁與聯機環境已全部就緒，房間已圓滿結束！請使用下方房主提供的聯絡資訊立即連線同樂。</p>' +
      
      '<div class="party-completion-section">' +
        '<div class="party-completion-sec-title">👑 房主傳輸之聯絡資訊：</div>' +
        '<div class="party-completion-contact-box ' + (isDefaultFallback ? 'fallback' : 'highlight') + '" style="background:rgba(25,118,210,0.1);border:1.5px solid rgba(25,118,210,0.35);padding:12px 14px;border-radius:10px;color:#1976D2;font-weight:800;font-size:14px;display:flex;align-items:center;justify-content:space-between;gap:10px;word-break:break-all">' +
          '<span>' + escapeHtml(contactText) + '</span>' +
          '<button class="btn btn-o btn-s" onclick="copyContactText(\'' + escapeHtml(contactText) + '\')" style="white-space:nowrap;font-size:11.5px;padding:4px 10px">📋 一鍵複製</button>' +
        '</div>' +
      '</div>' +

      '<div class="party-completion-section" style="margin-top:12px">' +
        '<div class="party-completion-sec-title">👑 房主資訊：</div>' +
        '<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:8px">' +
          '<div style="display:flex;align-items:center;gap:6px">' +
            '<span style="font-size:14px">👑</span>' +
            '<span style="font-weight:700;color:var(--fg);font-size:13px">' + escapeHtml(hostName) + '</span>' +
          '</div>' +
          '<span style="color:#5865F2;font-weight:800;font-size:12.5px">@' + escapeHtml((hostDc || '').replace(/^@/, '')) + '</span>' +
        '</div>' +
      '</div>' +

      '<div style="margin-top:20px;display:flex;justify-content:center">' +
        '<button class="btn btn-p btn-m party-completion-btn-close" onclick="closePartyCompletionCentralModal(\'modal-party-member-completion-central\')" style="padding:10px 32px;font-size:14px;font-weight:800;box-shadow:0 4px 16px rgba(25,118,210,0.4);background:linear-gradient(135deg,#1976D2,#2196F3)">👥 返回組隊大廳</button>' +
      '</div>' +
    '</div>';

  document.body.appendChild(modal);
}

function closePartyCompletionCentralModal(modalId) {
  var m = document.getElementById(modalId);
  if (m) m.remove();
}

/**
 * 一鍵複製聯絡資訊
 */
function copyContactText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(function() {
      tt('📋 聯絡資訊已成功複製到剪貼簿！', 'ok');
    }).catch(function() {
      if (window.pywebview && window.pywebview.api && window.pywebview.api.copy_text) {
        window.pywebview.api.copy_text(text);
        tt('📋 聯絡資訊已成功複製到剪貼簿！', 'ok');
      }
    });
  } else if (window.pywebview && window.pywebview.api && window.pywebview.api.copy_text) {
    window.pywebview.api.copy_text(text).then(function() {
      tt('📋 聯絡資訊已成功複製到剪貼簿！', 'ok');
    });
  } else {
    prompt('請手動複製聯絡資訊：', text);
  }
}

function formatCountdownDisplay(s) {
  if (s >= 60) {
    var min = Math.floor(s / 60);
    var rem = s % 60;
    return min + ' 分 ' + (rem < 10 ? '0' : '') + rem + ' 秒';
  }
  return s + ' 秒';
}

/**
 * 房主手動延遲 5 分鐘 (+300 秒，最多 2 次)
 */
function delayPartyReadyCountdown() {
  if (_partyDelayCount >= 2) {
    tt('⚠️ 延遲次數已達上限 (最多支援 2 次)', 'warn');
    return;
  }
  _partyDelayCount++;
  _partyCountdownSeconds += 300;
  tt('⏳ 已為房間延長 5 分鐘！當前剩餘延遲次數：' + (2 - _partyDelayCount) + ' 次', 'ok');
  var cdSecEl = document.getElementById('party-cd-sec');
  if (cdSecEl) cdSecEl.textContent = formatCountdownDisplay(_partyCountdownSeconds);
  var delayBtn = document.getElementById('party-btn-delay-countdown');
  if (delayBtn) {
    var leftTimes = Math.max(0, 2 - _partyDelayCount);
    delayBtn.textContent = '⏳ 延遲 5 分鐘 (剩餘 ' + leftTimes + ' 次)';
    if (_partyDelayCount >= 2) delayBtn.disabled = true;
  }
}

/**
 * 房主點擊「馬上完成(解散)」：發送現有資訊並立即刪除房間
 */
function finishPartyInstantly() {
  var inputEl = document.getElementById('party-contact-input');
  var currentText = (inputEl ? inputEl.value : '') || _partyContactInputText || _partyPreFilledContact || '';
  submitPartyContactInfo(currentText, true);
}

/**
 * 房主發布聯絡資訊
 * @param {string} [overrideText] 強制指定的聯絡資訊文字
 * @param {boolean} [autoCloseImmediately=false] 是否發送完後立即刪除房間解散
 */
function submitPartyContactInfo(overrideText, autoCloseImmediately) {
  if (!_partyCurRoom || _partyContactSubmitted) return;
  var rid = _partyCurRoom.room_id;
  var inputEl = document.getElementById('party-contact-input');
  var text = (overrideText !== undefined && overrideText !== null && String(overrideText).trim() !== '') 
    ? String(overrideText).trim() 
    : (((inputEl ? inputEl.value : '') || _partyContactInputText || _partyPreFilledContact || '').trim());

  // 🌟 若沒有填入任何預填入或是手動填入聯絡資訊，則向房間發送預設求友文案
  if (!text) {
    var hostDcId = (_partyProfile && (_partyProfile.discord_username || _partyProfile.discord)) || (_partyCurRoom.host_discord) || ((_partyProfile && _partyProfile.nickname) || '房主');
    text = "房主未留任何資料，請自行申請好友DC+：'" + hostDcId + "'";
  }

  _partyContactInputText = text;
  _partyContactSubmitted = true;

  if (_partyCountdownTimer) {
    clearInterval(_partyCountdownTimer);
    _partyCountdownTimer = null;
  }

  // 隱藏頂部預填卡片
  var preWrap = document.getElementById('party-room-pre-contact-wrap');
  if (preWrap) preWrap.style.display = 'none';

  var btn = document.getElementById('party-btn-send-contact');
  if (btn) { btn.disabled = true; btn.textContent = '發送中...'; }

  pywebview.api.send_party_contact_info(rid, _partyContactInputText).then(function(res) {
    if (res && res.ok) {
      tt('🎉 聯絡資訊已發布給全體隊員！', 'ok');
      if (autoCloseImmediately) {
        tt('隊伍組建完成，正在解散房間…', 'info');
        leaveOrCloseCurrentRoom(true);
      } else {
        var bannerContentEl = document.querySelector('#party-all-ready-banner .banner-content');
        if (bannerContentEl) bannerContentEl.dataset.mode = '';
        if (_partyCurRoom) renderRoomView(_partyCurRoom);
      }
    } else {
      tt('發送失敗: ' + ((res && res.msg) || '未知錯誤'), 'er');
      _partyContactSubmitted = false;
    }
  }).catch(function(err) {
    tt('連線出錯: ' + err, 'er');
    _partyContactSubmitted = false;
  });
}

/**
 * 隊員端極輕量輪詢獲取房主資訊 (每 0.5 秒發一次請求，直到取得為止)
 */
function startMemberContactPolling(rid) {
  if (_partyContactPollingTimer) return;
  _partyContactPollingTimer = setInterval(function() {
    if (!_partyCurRoom || _partyCurRoom.room_id !== rid) {
      clearInterval(_partyContactPollingTimer);
      _partyContactPollingTimer = null;
      return;
    }
    pywebview.api.get_party_contact_info(rid).then(function(res) {
      if (res && res.has_contact && res.contact_info) {
        clearInterval(_partyContactPollingTimer);
        _partyContactPollingTimer = null;
        _partyReceivedContact = res.contact_info;
        tt('🎉 已收到房主發送的聯絡資訊！', 'ok');
        var bannerContentEl = document.querySelector('#party-all-ready-banner .banner-content');
        if (bannerContentEl) bannerContentEl.dataset.mode = '';
        if (_partyCurRoom) renderRoomView(_partyCurRoom);
      } else if (res && res.is_closed) {
        clearInterval(_partyContactPollingTimer);
        _partyContactPollingTimer = null;
        tt('房間已被房主完成並解散', 'info');
        leaveOrCloseCurrentRoom(true);
      }
    }).catch(function() {});
  }, 500); // 0.5 秒一次極輕量查詢 (select=room_id,status,note,updated_at)
}

/**
 * 一鍵複製聯絡資訊
 */
function copyContactText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(function() {
      tt('📋 聯絡資訊已成功複製到剪貼簿！', 'ok');
    }).catch(function() {
      if (window.pywebview && window.pywebview.api && window.pywebview.api.copy_text) {
        window.pywebview.api.copy_text(text);
        tt('📋 聯絡資訊已成功複製到剪貼簿！', 'ok');
      }
    });
  } else if (window.pywebview && window.pywebview.api && window.pywebview.api.copy_text) {
    window.pywebview.api.copy_text(text).then(function() {
      tt('📋 聯絡資訊已成功複製到剪貼簿！', 'ok');
    });
  } else {
    prompt('請手動複製聯絡資訊：', text);
  }
}

/**
 * 🛡️ 排查 Windows Defender / 防毒軟體攔截 (自動請求白名單排除項或直達 Windows 設定頁)
 */
function openDefenderExclusionHelper(appid) {
  if (!window.pywebview || !window.pywebview.api) return;
  tt('🛡️ 正在排查防毒攔截並嘗試新增白名單排除項...', 'info');
  if (pywebview.api.add_game_folder_to_defender) {
    pywebview.api.add_game_folder_to_defender(appid || '').then(function(res) {
      if (res && res.ok) {
        tt(res.msg, 'ok');
      } else {
        if (pywebview.api.open_defender_exclusion_settings) {
          pywebview.api.open_defender_exclusion_settings().then(function() {
            tt('已為您開啟 Windows Defender 排除項設定頁面，請手動新增遊戲目錄', 'info');
          });
        }
      }
    }).catch(function() {
      if (pywebview.api.open_defender_exclusion_settings) {
        pywebview.api.open_defender_exclusion_settings();
      }
    });
  } else if (pywebview.api.open_defender_exclusion_settings) {
    pywebview.api.open_defender_exclusion_settings();
  }
}

/**
 * 隊員點擊「🚀 一鍵安裝」
 * 自動下載房主 Discord Webhook 整合包並自動部署 Manifest、Lua 腳本與線上補丁
 */
function startSyncCurrentGameInstall() {
  if (!_partyCurRoom) return;
  var rid = _partyCurRoom.room_id;
  var appid = _partyCurRoom.appid;
  var syncBtn = document.getElementById('party-btn-start-sync');

  var myProgStage = document.getElementById('party-my-progress-stage');
  var myProgPct = document.getElementById('party-my-progress-pct');
  var myProgBarInner = document.getElementById('party-my-progress-bar-inner');

  var isPendingPatch = (syncBtn && syncBtn.textContent.indexOf('套用') !== -1);

  // 🌟 啟動前端本地安裝保護鎖：防止定時輪詢在最初 1~2 秒內因後端異步時間差覆蓋進度為 0%
  window._partyLocalInstalling = true;
  window._partyLocalInstallAppId = appid;

  if (syncBtn) {
    syncBtn.disabled = true;
    syncBtn.innerHTML = '<span class="spinner" style="display:inline-block;width:14px;height:14px;border:2px solid #fff;border-top-color:transparent;border-radius:50%;animation:spin 0.8s linear infinite;margin-right:6px"></span> ' + (isPendingPatch ? '正在套用補丁中…' : '正在一鍵安裝中…');
  }

  if (myProgStage && myProgPct && myProgBarInner) {
    myProgStage.innerHTML = '<span class="spinner" style="width:11px;height:11px;margin-right:4px"></span> <span>' + (isPendingPatch ? '正在解壓並套用線上補丁…' : '正在啟動一鍵安裝程序…') + '</span>';
    myProgPct.textContent = isPendingPatch ? '90%' : '5%';
    myProgBarInner.style.width = isPendingPatch ? '90%' : '5%';
    myProgBarInner.className = 'party-my-progress-bar-inner active';
  }

  tt(isPendingPatch ? '🚀 正在取得整合包並為遊戲套用線上補丁…' : '🚀 已啟動一鍵安裝：正在取得房主整合包並自動部署入庫與套用補丁…', 'info');

  pywebview.api.start_party_sync_download(rid, appid).then(function(res) {
    if (res && res.ok) {
      tt(res.msg || (isPendingPatch ? '線上補丁部署已在背景啟動' : '一鍵安裝程序已在背景啟動'), 'ok');
    } else {
      window._partyLocalInstalling = false;
      tt(res && res.msg ? res.msg : '部署失敗', 'err');
      if (syncBtn) {
        syncBtn.disabled = false;
        syncBtn.innerHTML = isPendingPatch ? '🚀 套用線上補丁' : '🚀 一鍵安裝';
      }
      if (myProgStage && myProgPct && myProgBarInner) {
        myProgStage.innerHTML = '<span style="color:#F44336">❌ 啟動失敗</span>';
        myProgPct.textContent = isPendingPatch ? '90%' : '0%';
        myProgBarInner.style.width = isPendingPatch ? '90%' : '0%';
        myProgBarInner.className = 'party-my-progress-bar-inner';
      }
    }
  }).catch(function(err) {
    window._partyLocalInstalling = false;
    tt('啟動部署出錯: ' + err, 'err');
    if (syncBtn) {
      syncBtn.disabled = false;
      syncBtn.innerHTML = isPendingPatch ? '🚀 套用線上補丁' : '🚀 一鍵安裝';
    }
    if (myProgStage && myProgPct && myProgBarInner) {
      myProgStage.innerHTML = '<span style="color:#F44336">❌ 啟動異常</span>';
      myProgPct.textContent = isPendingPatch ? '90%' : '0%';
      myProgBarInner.style.width = isPendingPatch ? '90%' : '0%';
      myProgBarInner.className = 'party-my-progress-bar-inner';
    }
  });
}

/**

 * 複製房號

 */

function copyPartyRoomCode() {

  if (!_partyCurRoom || !_partyCurRoom.room_id) return;

  var code = _partyCurRoom.room_id;

  if (navigator.clipboard && navigator.clipboard.writeText) {

    navigator.clipboard.writeText(code).then(function() {

      tt('📋 已複製房號 #' + code + '！快分享給朋友一起連線', 'ok');

    }).catch(function() {

      tt('房間邀請碼: ' + code, 'info');

    });

  } else {

    tt('房間邀請碼: ' + code, 'info');

  }

}

/**
 * 退出或解散房間 (已移除多餘的確認詢問，直接俐落退出並返回大廳)
 * @param {boolean} [silent=false] 是否靜默退出
 */
function leaveOrCloseCurrentRoom(silent) {
  resetPartyReadyCountdown();
  if (!_partyCurRoom) return;

  var isHost = (_partyCurRoom.host_name === ((_partyProfile && _partyProfile.nickname) || ''));
  var actionText = isHost ? '解散該房間' : '退出房間';

  if (!silent) {
    tt('🌸 正在' + actionText + '…', 'info');
  }

  var p = isHost ? pywebview.api.close_party_room() : pywebview.api.leave_party_room();

  p.then(function(res) {
    tt(res && res.msg ? res.msg : '操作已完成', 'ok');
    _partyCurRoom = null;
    updateSidebarRoomInfo(null);
    switchPartyNav('lobby');
    refreshPartyLobby(false);
  }).catch(function(err) {
    tt('操作異常: ' + err, 'err');
    _partyCurRoom = null;
    updateSidebarRoomInfo(null);
    switchPartyNav('lobby');
    refreshPartyLobby(false);
  });
}

// ═══════════════════════════════════════════════════════

// 行內直接編輯組隊暱稱 (不彈窗、極速即時保存)

// ═══════════════════════════════════════════════════════

function startInlineEditName() {

  var dispWrap = document.getElementById('party-name-display-wrap');

  var editWrap = document.getElementById('party-name-edit-wrap');

  var input = document.getElementById('input-inline-nickname');

  var nameEl = document.getElementById('party-my-name');

  if (!editWrap || !dispWrap || !input) return;

  var curName = (_partyProfile && _partyProfile.nickname) ? _partyProfile.nickname : (nameEl ? nameEl.textContent.trim() : '');

  input.value = curName;

  dispWrap.style.display = 'none';

  editWrap.style.display = 'flex';

  setTimeout(function() {

    input.focus();

    input.select();

  }, 50);

}

function cancelInlineEditName() {

  var dispWrap = document.getElementById('party-name-display-wrap');

  var editWrap = document.getElementById('party-name-edit-wrap');

  if (editWrap) editWrap.style.display = 'none';

  if (dispWrap) dispWrap.style.display = 'flex';

}

function handleInlineNicknameKey(e) {

  if (e.key === 'Enter') {

    e.preventDefault();

    saveInlineNickname();

  } else if (e.key === 'Escape') {

    e.preventDefault();

    cancelInlineEditName();

  }

}

function saveInlineNickname() {

  var input = document.getElementById('input-inline-nickname');

  if (!input) return;

  var newName = (input.value || '').trim();

  if (!newName) {

    tt('暱稱不得為空', 'warn');

    input.focus();

    return;

  }

  if (newName.length > 24) {

    tt('暱稱長度上限為 24 字元', 'warn');

    input.focus();

    return;

  }

  // 若未變動則直接收起編輯框

  if (_partyProfile && _partyProfile.nickname === newName) {

    cancelInlineEditName();

    return;

  }

  pywebview.api.set_party_nickname(newName).then(function(res) {

    if (res && res.ok) {

      tt('組隊暱稱已更新！', 'ok');

      if (_partyProfile) _partyProfile.nickname = newName;

      var nameEl = document.getElementById('party-my-name');

      if (nameEl) nameEl.textContent = newName;

      cancelInlineEditName();

      // 若當前在房間內，同步更新房間資訊

      if (_partyCurRoom) {

        pywebview.api.get_party_room_details('').then(function(rres) {

          if (rres && rres.room) renderRoomView(rres.room);

        });

      }

    } else {

      tt(res && res.msg ? res.msg : '更新失敗', 'err');

    }

  }).catch(function(err) {

    tt('更新暱稱異常: ' + err, 'err');

  });

}

// ═══════════════════════════════════════════════════════

// 彈窗邏輯：創建房間

// ═══════════════════════════════════════════════════════

function toggleDiscordCustomSection(e) {
  // 相容保留函式，自訂 Webhook 欄位已常駐顯示
  if (e) { e.preventDefault(); e.stopPropagation(); }
}

// Discord Webhook 網址嚴格正則表達式 (支援 discord.com, discordapp.com, 以及 ptb/canary 官方子域名)
var DISCORD_WEBHOOK_REGEX = /^https:\/\/(?:(?:canary|ptb)\.)?discord(?:app)?\.com\/api\/webhooks\/\d+\/[A-Za-z0-9_-]+$/i;

function isValidDiscordWebhookUrl(url) {
  if (!url || typeof url !== 'string') return false;
  return DISCORD_WEBHOOK_REGEX.test(url.trim());
}

var _isInspectingResources = false;
var _lastResourceInspectionResult = null;
var _inspectingAppId = null;

function testDiscordWebhookConnection() {
  var input = document.getElementById('input-party-discord-webhook');
  var url = input ? input.value.trim() : '';
  if (!url) {
    tt('請先輸入 Discord Webhook 網址！', 'warn');
    if (input) input.focus();
    return;
  }
  if (!isValidDiscordWebhookUrl(url)) {
    tt('Webhook 網址格式無效，請確認是否為 https://discord.com/api/webhooks/... 官方格式', 'err');
    if (input) {
      input.focus();
      input.style.borderColor = '#FF4757';
    }
    return;
  }
  tt('正在測試 Discord Webhook 連線…', 'info');
  if (window.pywebview && window.pywebview.api && window.pywebview.api.test_discord_webhook) {
    pywebview.api.test_discord_webhook(url).then(function(res) {
      if (res && res.ok) {
        tt('✅ Discord Webhook 連線測試成功！已自動保存設定', 'ok');
        try { localStorage.setItem('smu_party_discord_webhook', url); } catch (e) {}
        updateCreateRoomBtnState();
      } else {
        tt('連線失敗: ' + (res ? res.msg : '未知錯誤'), 'err');
        updateCreateRoomBtnState();
      }
    }).catch(function(err) {
      tt('連線異常: ' + err, 'err');
      updateCreateRoomBtnState();
    });
  }
}

function savePartyDiscordWebhook() {
  var input = document.getElementById('input-party-discord-webhook');
  var url = input ? input.value.trim() : '';
  if (url) {
    try { localStorage.setItem('smu_party_discord_webhook', url); } catch (e) {}
  }
  if (window.pywebview && window.pywebview.api && window.pywebview.api.save_discord_webhook) {
    pywebview.api.save_discord_webhook(url);
  }
  updateCreateRoomBtnState();
}

function updateCreateRoomBtnState() {
  var select = document.getElementById('select-party-installed-games');
  var aidInput = document.getElementById('input-party-appid');
  var webhookInput = document.getElementById('input-party-discord-webhook');
  var btn = document.getElementById('btn-submit-create-party');
  if (!btn) return;

  var appid = (aidInput ? aidInput.value : (select ? select.value : '')).trim();
  var hasGame = !!appid;

  var webhookUrl = webhookInput ? webhookInput.value.trim() : '';
  var hasWebhook = !!webhookUrl;
  var isWebhookValid = isValidDiscordWebhookUrl(webhookUrl);

  // 1. Webhook 輸入框色彩視覺即時反饋
  if (webhookInput) {
    if (!hasWebhook) {
      webhookInput.style.borderColor = 'var(--pink-light)';
    } else if (isWebhookValid) {
      webhookInput.style.borderColor = '#2ED573';
    } else {
      webhookInput.style.borderColor = '#FF4757';
    }
  }

  // 2. 嚴格檢查三大必備要件 (缺一不可)
  // 要件一：鎖定遊戲
  if (!hasGame) {
    btn.disabled = true;
    btn.classList.add('disabled');
    btn.title = '⛔ 開房限制：請先由清單挑選並鎖定遊戲！';
    return;
  }

  // 要件二：三檔檢查 (Manifest / Lua / Patch)
  if (_isInspectingResources) {
    btn.disabled = true;
    btn.classList.add('disabled');
    btn.title = '⏳ 開房限制：正在檢測本機 Manifest、Lua 腳本與補丁三檔，請稍候…';
    return;
  }

  var res = _lastResourceInspectionResult;
  if (!res) {
    btn.disabled = true;
    btn.classList.add('disabled');
    btn.title = '⛔ 開房限制：本機三檔尚未完成檢測，請等待檢測完成！';
    return;
  }

  var mReady = !!(res.manifest && res.manifest.ready);
  var lReady = !!(res.lua && res.lua.ready);
  var pReady = !!(res.patch && res.patch.ready);

  if (!mReady || !lReady || !pReady) {
    var missing = [];
    if (!mReady) missing.push('Manifest 清單');
    if (!lReady) missing.push('Lua 腳本');
    if (!pReady) missing.push('線上補丁');
    btn.disabled = true;
    btn.classList.add('disabled');
    btn.title = '⛔ 開房限制：本機三檔檢查異常 (缺少: ' + missing.join('、') + ')，任何一個有異常均不支持開房！';
    return;
  }

  // 要件三：Webhook 網址與格式
  if (!hasWebhook) {
    btn.disabled = true;
    btn.classList.add('disabled');
    btn.title = '⛔ 開房限制：請輸入 Discord Webhook 網址 (鎖定遊戲、三檔檢查、Webhook 缺一不可)！';
    return;
  }

  if (!isWebhookValid) {
    btn.disabled = true;
    btn.classList.add('disabled');
    btn.title = '⛔ 開房限制：Discord Webhook 網址格式錯誤 (格式應為 https://discord.com/api/webhooks/...)！';
    return;
  }

  // 三大要件全數通過！點亮立即開房按鈕
  btn.disabled = false;
  btn.classList.remove('disabled');
  btn.title = '🎮 鎖定遊戲、三檔檢查、Discord Webhook 全數就緒，可立即開房！';
}

function openCreateRoomModal() {
  if (!_partyProfile || !_partyProfile.is_discord_verified) {
    tt('🛡️ 為維護大廳安全秩序，請先完成頂部 Discord 官方身分認證！', 'warn');
    startDiscordOAuthFlow();
    return;
  }

  var modal = document.getElementById('modal-create-party-room');
  if (!modal) return;

  // 清空輸入值與卡片
  var gn = document.getElementById('input-party-gamename');
  var aid = document.getElementById('input-party-appid');
  var note = document.getElementById('input-party-note');
  var select = document.getElementById('select-party-installed-games');
  var gameCard = document.getElementById('party-selected-game-card');
  if (gn) gn.value = '';
  if (aid) aid.value = '';
  if (note) note.value = '';
  if (select) select.selectedIndex = 0;
  if (gameCard) gameCard.style.display = 'none';

  // 初始按鈕狀態
  updateCreateRoomBtnState();

  // 重置三檔指示燈
  resetResourceInspectBadges();

  // 載入本地已入庫遊戲下拉選單
  loadInstalledGamesDropdown();

  var chk = document.getElementById('check-party-auto-upload');
  if (chk) chk.checked = true;

  // 自動回填已記憶之 Discord Webhook 網址 (優先讀取 localStorage 快取)
  var input = document.getElementById('input-party-discord-webhook');
  try {
    var cached = localStorage.getItem('smu_party_discord_webhook');
    if (cached && input && !input.value) {
      input.value = cached;
      updateCreateRoomBtnState();
    }
  } catch (e) {}

  // 向後端持久化獲取已保存之 Webhook
  if (window.pywebview && window.pywebview.api && window.pywebview.api.get_discord_webhook) {
    pywebview.api.get_discord_webhook().then(function(res) {
      if (res && res.ok && res.webhook_url) {
        var inp = document.getElementById('input-party-discord-webhook');
        if (inp) {
          inp.value = res.webhook_url;
          try { localStorage.setItem('smu_party_discord_webhook', res.webhook_url); } catch (e) {}
          updateCreateRoomBtnState();
        }
      }
    });
  }

  // 預填隊伍聯絡資訊回填 (若有記憶則回填，留空則保持為空)
  var preContactInp = document.getElementById('input-party-pre-contact');
  var savedContact = _partyPreFilledContact || localStorage.getItem('smu_party_pre_contact') || '';
  if (preContactInp) {
    preContactInp.value = savedContact;
  }

  modal.style.display = 'flex';
  modal.classList.remove('hidden');
  modal.classList.add('active');

  // 🌟 動畫設計：創建房間完成顯示後等待 0.5 秒 (500ms)，漸顯右側 Webhook 教學影片組件
  showWebhookTutorialCardDelayed();
}

var _webhookTutorialTimer = null;

function showWebhookTutorialCardDelayed() {
  if (_webhookTutorialTimer) {
    clearTimeout(_webhookTutorialTimer);
    _webhookTutorialTimer = null;
  }
  var card = document.getElementById('webhook-tutorial-card');
  var video = document.getElementById('webhook-tutorial-video');
  if (card) {
    card.classList.remove('fade-in-active');
  }
  if (video) {
    video.pause();
    try { video.currentTime = 0; } catch(e){}
  }

  // 等待 0.5 秒 (500ms) 漸顯
  _webhookTutorialTimer = setTimeout(function() {
    var c = document.getElementById('webhook-tutorial-card');
    var v = document.getElementById('webhook-tutorial-video');
    var m = document.getElementById('modal-create-party-room');
    if (c && m && m.classList.contains('active')) {
      c.classList.add('fade-in-active');
      if (v) {
        v.play().catch(function(err) {
          console.warn('[Party] Webhook 影片自動播放受阻:', err);
        });
      }
    }
  }, 500);
}

function hideWebhookTutorialCard() {
  if (_webhookTutorialTimer) {
    clearTimeout(_webhookTutorialTimer);
    _webhookTutorialTimer = null;
  }
  var card = document.getElementById('webhook-tutorial-card');
  var video = document.getElementById('webhook-tutorial-video');
  if (card) {
    card.classList.remove('fade-in-active');
  }
  if (video) {
    video.pause();
  }
}

function toggleWebhookVideoAudio(e) {
  if (e) e.stopPropagation();
  var v = document.getElementById('webhook-tutorial-video');
  var b = document.getElementById('btn-webhook-audio-toggle');
  if (v && b) {
    v.muted = !v.muted;
    b.textContent = v.muted ? '🔇 靜音' : '🔊 有聲';
    if (!v.muted) {
      v.play().catch(function(){});
    }
  }
}

function closeCreateRoomModal() {
  // 🌟 關閉彈窗時立即隱藏影片並暫停播放
  hideWebhookTutorialCard();

  var modal = document.getElementById('modal-create-party-room');
  if (modal) {
    modal.style.display = 'none';
    modal.classList.add('hidden');
    modal.classList.remove('active');
  }

  var flowPanel = document.getElementById('party-create-flow-status');
  if (flowPanel) flowPanel.style.display = 'none';

  var btnSubmit = document.getElementById('btn-submit-create-party');
  var btnCancel = document.getElementById('btn-cancel-create-party');
  if (btnSubmit) { btnSubmit.disabled = true; btnSubmit.classList.add('disabled'); btnSubmit.textContent = '🚀 立即開房'; }
  if (btnCancel) { btnCancel.disabled = false; }
}

function togglePartyAutoUploadSection() {

  var wrap = document.getElementById('party-gas-config-wrap');

  if (wrap) wrap.style.display = 'block';

}

function resetResourceInspectBadges() {
  _isInspectingResources = false;
  _lastResourceInspectionResult = null;
  _inspectingAppId = null;

  var m = document.getElementById('inspect-manifest');
  var l = document.getElementById('inspect-lua');
  var p = document.getElementById('inspect-patch');

  if (m) { m.textContent = '📄 Manifest: 待偵測'; m.style.color = 'var(--gray)'; }
  if (l) { l.textContent = '📜 Lua 腳本: 待偵測'; l.style.color = 'var(--gray)'; }
  if (p) { p.textContent = '🎮 線上補丁: 待偵測'; p.style.color = 'var(--gray)'; }

  updateCreateRoomBtnState();
}

var _inspectTimer = null;

function triggerResourceInspection(appid) {
  if (_inspectTimer) clearTimeout(_inspectTimer);
  _inspectTimer = setTimeout(function() {
    doInspectPartyResources(appid);
  }, 250);
}

function doInspectPartyResources(appid) {
  if (!appid || !window.pywebview || !window.pywebview.api || !window.pywebview.api.inspect_party_resources) {
    resetResourceInspectBadges();
    return;
  }

  _isInspectingResources = true;
  _inspectingAppId = String(appid);
  _lastResourceInspectionResult = null;
  updateCreateRoomBtnState();

  var mEl = document.getElementById('inspect-manifest');
  var lEl = document.getElementById('inspect-lua');
  var pEl = document.getElementById('inspect-patch');

  if (mEl) { mEl.textContent = '📄 Manifest: 檢測中…'; mEl.style.color = '#FFA502'; }
  if (lEl) { lEl.textContent = '📜 Lua 腳本: 檢測中…'; lEl.style.color = '#FFA502'; }
  if (pEl) { pEl.textContent = '🎮 線上補丁: 檢測中…'; pEl.style.color = '#FFA502'; }

  pywebview.api.inspect_party_resources(appid).then(function(res) {
    // 檢查是否依然為當前選取的 appid
    var curAidEl = document.getElementById('input-party-appid');
    var curAid = curAidEl ? curAidEl.value.trim() : '';
    if (curAid && curAid !== String(appid)) {
      return;
    }

    _isInspectingResources = false;
    _lastResourceInspectionResult = res || null;

    if (!res) {
      updateCreateRoomBtnState();
      return;
    }

    if (mEl) {
      if (res.manifest && res.manifest.ready) {
        var kb = Math.round((res.manifest.size || 0) / 1024);
        mEl.textContent = '📄 Manifest: ✅ 就緒 (' + kb + 'KB)';
        mEl.style.color = '#2ED573';
      } else {
        mEl.textContent = '📄 Manifest: ❌ 缺少';
        mEl.style.color = '#FF4757';
      }
    }

    if (lEl) {
      if (res.lua && res.lua.ready) {
        lEl.textContent = '📜 Lua 腳本: ✅ 就緒';
        lEl.style.color = '#2ED573';
      } else {
        lEl.textContent = '📜 Lua 腳本: ❌ 缺少';
        lEl.style.color = '#FF4757';
      }
    }

    if (pEl) {
      if (res.patch && res.patch.ready) {
        var countText = res.patch.files_count ? (' (' + res.patch.files_count + ' 個檔案)') : '';
        pEl.textContent = '🎮 線上補丁: ✅ 就緒' + countText;
        pEl.style.color = '#2ED573';
      } else {
        pEl.textContent = '🎮 線上補丁: ❌ 未檢測到';
        pEl.style.color = '#FF4757';
      }
    }

    updateCreateRoomBtnState();
  }).catch(function(err) {
    _isInspectingResources = false;
    updateCreateRoomBtnState();
  });
}

function copyInPageGuideScript() {

  var inlineCode = `(function(){` +

    `function isV(el){if(!el)return false;var r=el.getBoundingClientRect();if(!r.width||!r.height)return false;var s=getComputedStyle(el);return s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0';}` +

    `var newProj=document.querySelector('a[href*="/projects/create"]')||document.querySelector('[aria-label*="新專案"], [aria-label*="New project"]')||Array.from(document.querySelectorAll('*')).find(function(el){if(!isV(el)||el.children.length>3)return false;var t=(el.innerText||el.textContent||'').trim();var a=(el.getAttribute('aria-label')||'').trim();return(t.indexOf('新專案')!==-1||t.indexOf('New project')!==-1||a.indexOf('新專案')!==-1);});` +

    `if(newProj){` +

      `var btn=newProj.closest('button, [role="button"], a, div[tabindex]')||newProj;` +

      `btn.scrollIntoView({behavior:'smooth',block:'center'});` +

      `var box=document.createElement('div');box.style='position:fixed;z-index:2147483640;border:3px solid #FF4757;border-radius:12px;box-shadow:0 0 0 9999px rgba(0,0,0,0.76),0 0 24px #FF4757;pointer-events:none;transition:all .3s;';` +

      `var rect=btn.getBoundingClientRect();box.style.left=(rect.left-6)+'px';box.style.top=(rect.top-6)+'px';box.style.width=(rect.width+12)+'px';box.style.height=(rect.height+12)+'px';` +

      `var tip=document.createElement('div');tip.style='position:fixed;z-index:2147483645;background:#161B22;border:2px solid #FF4757;border-radius:14px;padding:14px 18px;color:#fff;font-family:sans-serif;max-width:320px;left:'+(rect.right+16)+'px;top:'+rect.top+'px;box-shadow:0 10px 30px rgba(0,0,0,.8);';` +

      `tip.innerHTML='<div style="color:#FF6B81;font-size:11px;font-weight:800;margin-bottom:4px;">✨ SMU 部署精靈 (第 1 步)</div><div style="font-size:15px;font-weight:800;margin-bottom:6px;">👉 點擊此處「➕ 新專案」</div><div style="font-size:12px;color:#CBD5E1;line-height:1.5;">點擊此處建立專案，進入編輯器後精靈會自動指引下一步！</div>';` +

      `document.body.appendChild(box);document.body.appendChild(tip);` +

      `btn.addEventListener('click',function(){box.remove();tip.remove();},{once:true});` +

    `}else{alert('⚠️ 未找到「新專案」按鈕，請確認目前停留在 script.google.com/home 頁面！');}` +

  `})();`;

  if (navigator.clipboard && navigator.clipboard.writeText) {

    navigator.clipboard.writeText(inlineCode).then(function() {

      tt('✨ 已複製真實網頁高亮代碼！在 Google 頁面按 F12 ➔ 貼到 Console 並按 Enter，即可直接高亮【新專案】！', 'ok');

    }).catch(function() {

      tt('複製失敗，請手動複製', 'err');

    });

  } else {

    tt('剪貼簿不支援自動寫入', 'warn');

  }

}

function loadInstalledGamesDropdown() {

  var select = document.getElementById('select-party-installed-games');

  if (!select || !window.pywebview || !window.pywebview.api || !window.pywebview.api.get_installed_games_for_party) return;

  select.innerHTML = '<option value="">🔍 正在掃描本機已安裝且已就緒之遊戲…</option>';

  pywebview.api.get_installed_games_for_party().then(function(games) {

    if (Array.isArray(games) && games.length > 0) {

      var html = '<option value="">-- 請由清單挑選本機已安裝且已就緒的遊戲 (' + games.length + ' 款可選) --</option>';

      games.forEach(function(g) {

        html += '<option value="' + g.appid + '" data-name="' + escapeHtml(g.name) + '">🎮 ' + escapeHtml(g.name) + ' (' + g.appid + ') · 補丁就緒</option>';

      });

      select.innerHTML = html;

    } else {

      select.innerHTML = '<option value="" disabled selected>⚠️ 本機尚未偵測到已部署線上補丁的遊戲 (請先至庫存部署補丁)</option>';

      tt('本機尚未偵測到已部署線上補丁的遊戲，請先在主庫存為遊戲部署線上補丁！', 'warn');

    }

    updateCreateRoomBtnState();

  }).catch(function(err) {

    select.innerHTML = '<option value="" disabled selected>❌ 載入本機遊戲失敗</option>';

    updateCreateRoomBtnState();

  });

}

function onSelectInstalledGameChange() {

  var select = document.getElementById('select-party-installed-games');

  var gn = document.getElementById('input-party-gamename');

  var aid = document.getElementById('input-party-appid');

  var card = document.getElementById('party-selected-game-card');

  var cardName = document.getElementById('party-selected-game-name');

  var cardAid = document.getElementById('party-selected-game-appid');

  if (!select) return;

  var selectedOpt = select.options[select.selectedIndex];

  if (selectedOpt && selectedOpt.value) {

    var valAid = selectedOpt.value;

    var valName = selectedOpt.getAttribute('data-name') || ('AppID ' + valAid);

    if (aid) aid.value = valAid;

    if (gn) gn.value = valName;

    if (cardName) cardName.textContent = valName;

    if (cardAid) cardAid.textContent = valAid;

    if (card) card.style.display = 'block';

    triggerResourceInspection(valAid);

  } else {

    if (aid) aid.value = '';

    if (gn) gn.value = '';

    if (card) card.style.display = 'none';

    resetResourceInspectBadges();

  }

  // 遊戲選取狀態改變，即時更新按鈕顏色與狀態

  updateCreateRoomBtnState();

}

function setPartyFlowStep(stepId, state, text) {

  var el = document.getElementById(stepId);

  if (!el) return;

  if (text) el.textContent = text;

  if (state === 'active') {

    el.style.color = '#FFD166';

    el.style.fontWeight = '700';

  } else if (state === 'done') {

    el.style.color = '#2EA043';

    el.style.fontWeight = '600';

  } else if (state === 'error') {

    el.style.color = '#FF4757';

    el.style.fontWeight = '700';

  } else {

    el.style.color = 'var(--gray)';

    el.style.fontWeight = '400';

  }

}

function submitCreatePartyRoom() {

  var gnInput = document.getElementById('input-party-gamename');

  var aidInput = document.getElementById('input-party-appid');

  var maxSelect = document.getElementById('select-party-max-players');

  var pubSelect = document.getElementById('select-party-is-public');

  var noteInput = document.getElementById('input-party-note');

  var gasInput = document.getElementById('input-party-gas-url');

  var preContactInput = document.getElementById('input-party-pre-contact');
  if (preContactInput && preContactInput.value.trim()) {
    savePartyPreFilledContact(preContactInput.value.trim());
  }

  var btnSubmit = document.getElementById('btn-submit-create-party');

  var btnCancel = document.getElementById('btn-cancel-create-party');

  var flowPanel = document.getElementById('party-create-flow-status');

  var flowTitle = document.getElementById('party-flow-status-title');

  var flowSpinner = document.getElementById('party-flow-status-spinner');

  var flowSub = document.getElementById('party-flow-status-sub');

  var flowError = document.getElementById('party-flow-error-msg');

  var gameName = (gnInput ? gnInput.value : '').trim();

  var appid = (aidInput ? aidInput.value : '').trim();

  var maxPlayers = parseInt(maxSelect ? maxSelect.value : 4, 10);

  var isPublic = (pubSelect ? pubSelect.value : '1') === '1';

  var note = (noteInput ? noteInput.value : '').trim();

  var gasUrl = (gasInput ? gasInput.value : '').trim();

  // 1. 遊戲選取防呆 (鎖定遊戲)
  if (!appid || !gameName) {
    tt('⛔ 請先由下拉選單挑選本機已安裝且已就緒的遊戲！', 'warn');
    var select = document.getElementById('select-party-installed-games');
    if (select) {
      select.focus();
      select.style.borderColor = '#FF4757';
      setTimeout(function() { select.style.borderColor = ''; }, 3000);
    }
    return;
  }

  // 2. 本機三檔檢測防呆 (任何一個有異常均不支援開房)
  if (_isInspectingResources) {
    tt('⏳ 正在檢測本機 Manifest、Lua 腳本與補丁三檔，請稍候…', 'warn');
    return;
  }
  var res = _lastResourceInspectionResult;
  if (!res || !res.manifest || !res.manifest.ready || !res.lua || !res.lua.ready || !res.patch || !res.patch.ready) {
    var missing = [];
    if (!res || !res.manifest || !res.manifest.ready) missing.push('Manifest 清單');
    if (!res || !res.lua || !res.lua.ready) missing.push('Lua 腳本');
    if (!res || !res.patch || !res.patch.ready) missing.push('線上補丁');
    tt('⛔ 本機三檔檢查未通過 (缺少: ' + (missing.length ? missing.join('、') : '未知') + ')，任何一個有異常均不支援開房！', 'err');
    return;
  }

  // 3. Discord Webhook 網址與格式嚴格防呆 (缺一不可)
  var webhookInput = document.getElementById('input-party-discord-webhook');
  var discordWebhook = webhookInput ? webhookInput.value.trim() : '';
  if (!discordWebhook) {
    tt('⛔ 請先輸入 Discord Webhook 網址！鎖定遊戲、三檔檢查、Webhook 缺一不可！', 'err');
    if (webhookInput) {
      webhookInput.focus();
      webhookInput.style.borderColor = '#FF4757';
    }
    return;
  }
  if (!isValidDiscordWebhookUrl(discordWebhook)) {
    tt('⛔ Discord Webhook 網址格式錯誤，請確認是否為 https://discord.com/api/webhooks/... 官方格式！', 'err');
    if (webhookInput) {
      webhookInput.focus();
      webhookInput.style.borderColor = '#FF4757';
    }
    return;
  }

  // 4. 展開極簡動態過場卡片 (正在建立房間...)
  if (flowPanel) flowPanel.style.display = 'block';
  if (flowError) flowError.style.display = 'none';
  if (flowTitle) flowTitle.innerHTML = '正在建立房間<span class="animated-dots"></span>';
  if (flowSub) flowSub.textContent = '正在同步雲端與聯機環境，請稍候…';
  if (flowSpinner) flowSpinner.className = 'party-spinner-ring';

  if (btnSubmit) { btnSubmit.disabled = true; btnSubmit.textContent = '⏳ 正在建立房間…'; }
  if (btnCancel) { btnCancel.disabled = true; }

  tt('🎮 正在建立房間，請稍候…', 'info');

  // 4. 階段一：本地三檔檢查、打包並上傳至 Discord CDN
  pywebview.api.prepare_party_package_upload(appid, discordWebhook, gameName).then(function(prepRes) {

    if (!prepRes || !prepRes.ok || !prepRes.download_url) {

      var errMsg = (prepRes && prepRes.msg) ? prepRes.msg : '未能成功上傳或取得下載網址';

      if (flowTitle) flowTitle.textContent = '❌ 建立房間失敗';
      if (flowSub) flowSub.textContent = '資源檢查或雲端同步未通過';
      if (flowSpinner) flowSpinner.className = 'party-spinner-ring done';

      if (flowError) {
        flowError.style.display = 'block';
        flowError.textContent = '⛔ 建立房間失敗：' + errMsg;
      }

      tt('❌ 建立房間失敗: ' + errMsg, 'err');

      if (btnSubmit) { btnSubmit.disabled = false; btnSubmit.textContent = '🚀 立即開房'; }
      if (btnCancel) { btnCancel.disabled = false; }
      return;

    }

    // 階段一完全過關，確認取得下載網址！
    var downloadUrl = prepRes.download_url;
    var fileId = prepRes.file_id || '';

    if (flowSub) flowSub.textContent = '即將完成，正在向伺服器登記房間…';

    // 5. 階段二：向 Supabase 正式發出開房要求 (攜帶下載網址)
    pywebview.api.create_party_room(gameName, appid, maxPlayers, isPublic, note, true, gasUrl, downloadUrl, fileId).then(function(res) {

      if (res && res.ok && res.room) {

        if (flowTitle) flowTitle.textContent = '🎉 房間建立成功！';
        if (flowSub) flowSub.textContent = '即將進入房間大廳…';
        if (flowSpinner) flowSpinner.className = 'party-spinner-ring done';

        tt(res.msg || '成功建立房間！', 'ok');

        if (discordWebhook) {
          try { localStorage.setItem('smu_party_discord_webhook', discordWebhook); } catch (e) {}
          if (window.pywebview && window.pywebview.api && window.pywebview.api.save_discord_webhook) {
            pywebview.api.save_discord_webhook(discordWebhook);
          }
        }

        setTimeout(function() {
          closeCreateRoomModal();
          _partyCurRoom = res.room;
          updateSidebarRoomInfo(res.room);
          switchPartyNav('room');
          schedulePartyPolling(3000);
        }, 500);

      } else {

        var createErr = (res && res.msg) ? res.msg : '伺服器建房失敗';

        if (flowTitle) flowTitle.textContent = '❌ 建立房間失敗';
        if (flowSub) flowSub.textContent = '伺服器拒絕或登記異常';
        if (flowSpinner) flowSpinner.className = 'party-spinner-ring done';

        if (flowError) {
          flowError.style.display = 'block';
          flowError.textContent = '⛔ 伺服器建房失敗: ' + createErr;
        }

        tt(createErr, 'err');

        if (btnSubmit) { btnSubmit.disabled = false; btnSubmit.textContent = '🚀 立即開房'; }
        if (btnCancel) { btnCancel.disabled = false; }

      }

    }).catch(function(err) {

      if (flowTitle) flowTitle.textContent = '❌ 建立房間失敗';
      if (flowSub) flowSub.textContent = '連線伺服器異常';
      if (flowSpinner) flowSpinner.className = 'party-spinner-ring done';

      if (flowError) {
        flowError.style.display = 'block';
        flowError.textContent = '⛔ 連線伺服器異常: ' + err;
      }

      tt('向伺服器開房出錯: ' + err, 'err');

      if (btnSubmit) { btnSubmit.disabled = false; btnSubmit.textContent = '🚀 立即開房'; }
      if (btnCancel) { btnCancel.disabled = false; }

    });

  }).catch(function(prepErr) {

    if (flowTitle) flowTitle.textContent = '❌ 建立房間失敗';
    if (flowSub) flowSub.textContent = '前置檢驗異常';
    if (flowSpinner) flowSpinner.className = 'party-spinner-ring done';

    if (flowError) {
      flowError.style.display = 'block';
      flowError.textContent = '⛔ 檢核異常: ' + prepErr;
    }

    tt('前置檢驗出錯: ' + prepErr, 'err');

    if (btnSubmit) { btnSubmit.disabled = false; btnSubmit.textContent = '🚀 立即開房'; }
    if (btnCancel) { btnCancel.disabled = false; }

  });

}

function downloadPartyGdrivePackage() {

  if (!_partyCurRoom) return;

  var url = _partyCurRoom.gdrive_url || _partyCurRoom.download_url;

  if (!url) {

    tt('房主尚未提供雲端整合包', 'info');

    return;

  }

  if (window.pywebview && window.pywebview.api && window.pywebview.api.open_external_url) {

    pywebview.api.open_external_url(url);

  } else {

    window.open(url, '_blank');

  }

  tt('🚀 已開啟房主 Google Drive 整合包下載鏈結！', 'ok');

}

// ═══════════════════════════════════════════════════════

// SMU 開房彈窗聚光燈互動導覽系統 (Gas Spotlight Tour)

// ═══════════════════════════════════════════════════════

var _gasTourSteps = [

  {

    targetId: 'party-package-core-badge',

    badge: '步驟 1 / 5',

    title: '核心三檔同步機制 (常駐開啟)',

    desc: 'SMU 創房的核心宗旨就是防止版本不同或缺少登入憑證導致連線失敗。系統常駐自動打包 Manifest、Lua 腳本與補丁三檔，隊友加入後即可一鍵自動同步！'

  },

  {

    targetId: 'btn-party-copy-gas-script',

    badge: '步驟 2 / 5',

    title: '第二步：複製 Google Apps Script 腳本',

    desc: '點擊此按鈕，可直接一鍵複製預先寫好的 Apps Script 後端代碼。全自動管理空間，每次上傳前自動清理舊檔，安全又省心！'

  },

  {

    targetId: 'btn-party-open-gas-guide',

    badge: '步驟 3 / 5',

    title: '第三步：查看視覺化動態指引',

    desc: '點擊此處可開啟精美的動態指引網頁。網頁包含擬真 Google 介面與脈衝箭頭，引導您貼上腳本、新增部署，並設定存取權限為【所有人】。'

  },

  {

    targetId: 'input-party-gas-url',

    badge: '步驟 4 / 5',

    title: '第四步：填入部署完成的 Web App 網址',

    desc: '在 Google 部署成功後複製結尾為 /exec 的網址並貼入此處。SMU 會自動儲存此網址，往後開房均免重複設定！'

  },

  {

    targetId: 'btn-party-test-gas',

    badge: '步驟 5 / 5',

    title: '第五步：驗證連線狀況',

    desc: '點擊【測試】按鈕進行即時連線探測。若彈出綠色成功提示，代表您的雲端端點已完全就緒，可立即發布房間！'

  }

];

var _gasTourCurrentStep = 0;

var _gasTourOverlayEl = null;

function startGasSpotlightTour(e) {

  if (e) {

    e.preventDefault();

    e.stopPropagation();

  }

  _gasTourCurrentStep = 0;

  createOrShowGasTourOverlay();

  renderGasTourStep(_gasTourCurrentStep);

}

function createOrShowGasTourOverlay() {

  if (!_gasTourOverlayEl) {

    _gasTourOverlayEl = document.createElement('div');

    _gasTourOverlayEl.id = 'smu-spotlight-tour-overlay';

    _gasTourOverlayEl.innerHTML = [

      '<div id="smu-tour-highlight-box"></div>',

      '<div id="smu-tour-tooltip">',

      '  <div class="tour-tooltip-badge" id="smu-tour-badge">步驟 1 / 5</div>',

      '  <div class="tour-tooltip-title" id="smu-tour-title"></div>',

      '  <div class="tour-tooltip-desc" id="smu-tour-desc"></div>',

      '  <div class="tour-tooltip-actions">',

      '    <button type="button" class="btn btn-o btn-xs" onclick="closeGasTour()" style="font-size:11px;padding:3px 10px;border-radius:12px;color:#8B949E;border-color:rgba(139,148,158,0.4)">跳過指引</button>',

      '    <div style="display:flex;gap:6px;">',

      '      <button type="button" class="btn btn-o btn-xs" id="smu-tour-btn-prev" onclick="prevGasTourStep()" style="font-size:11px;padding:3px 10px;border-radius:12px;color:#C9D1D9;">上一步</button>',

      '      <button type="button" class="btn btn-p btn-xs" id="smu-tour-btn-next" onclick="nextGasTourStep()" style="font-size:11px;padding:3px 12px;border-radius:12px;background:#FF4757;border-color:#FF4757;color:#fff;font-weight:700;">下一步 ➔</button>',

      '    </div>',

      '  </div>',

      '  <div class="tour-tooltip-arrow" id="smu-tour-arrow"></div>',

      '</div>'

    ].join('');

    document.body.appendChild(_gasTourOverlayEl);

    // 監聽視窗與捲動，動態更新定位

    window.addEventListener('resize', handleGasTourReposition);

    var modalBody = document.querySelector('#modal-create-room .modal-body');

    if (modalBody) {

      modalBody.addEventListener('scroll', handleGasTourReposition);

    }

  }

  _gasTourOverlayEl.style.display = 'block';

}

function handleGasTourReposition() {

  if (!_gasTourOverlayEl || _gasTourOverlayEl.style.display === 'none') return;

  positionGasTourStep(_gasTourCurrentStep);

}

function renderGasTourStep(index) {

  if (index < 0 || index >= _gasTourSteps.length) {

    closeGasTour();

    return;

  }

  var step = _gasTourSteps[index];

  // 若在第 1 步之後，確保 auto-upload 區塊是展開的

  if (index >= 1) {

    var chk = document.getElementById('check-party-auto-upload');

    if (chk && !chk.checked) {

      chk.checked = true;

      if (typeof togglePartyAutoUploadSection === 'function') {

        togglePartyAutoUploadSection();

      }

    }

  }

  var badgeEl = document.getElementById('smu-tour-badge');

  var titleEl = document.getElementById('smu-tour-title');

  var descEl = document.getElementById('smu-tour-desc');

  var btnPrev = document.getElementById('smu-tour-btn-prev');

  var btnNext = document.getElementById('smu-tour-btn-next');

  if (badgeEl) badgeEl.textContent = step.badge;

  if (titleEl) titleEl.textContent = step.title;

  if (descEl) descEl.textContent = step.desc;

  if (btnPrev) {

    btnPrev.style.display = index === 0 ? 'none' : 'inline-block';

  }

  if (btnNext) {

    if (index === _gasTourSteps.length - 1) {

      btnNext.textContent = '完成指引 ✨';

      btnNext.style.background = '#2EA043';

      btnNext.style.borderColor = '#2EA043';

    } else {

      btnNext.textContent = '下一步 ➔';

      btnNext.style.background = '#FF4757';

      btnNext.style.borderColor = '#FF4757';

    }

  }

  // 延遲定位以等待 DOM 可能的展開催動

  setTimeout(function() {

    positionGasTourStep(index);

  }, 60);

}

function positionGasTourStep(index) {

  var step = _gasTourSteps[index];

  if (!step) return;

  var target = document.getElementById(step.targetId);

  var hlBox = document.getElementById('smu-tour-highlight-box');

  var tooltip = document.getElementById('smu-tour-tooltip');

  var arrow = document.getElementById('smu-tour-arrow');

  if (!target || !hlBox || !tooltip) return;

  // 捲動目標至可視範圍

  target.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  var rect = target.getBoundingClientRect();

  var pad = 6;

  hlBox.style.left = Math.max(0, rect.left - pad) + 'px';

  hlBox.style.top = Math.max(0, rect.top - pad) + 'px';

  hlBox.style.width = (rect.width + pad * 2) + 'px';

  hlBox.style.height = (rect.height + pad * 2) + 'px';

  // Tooltip 定位

  var tooltipWidth = tooltip.offsetWidth || 300;

  var tooltipHeight = tooltip.offsetHeight || 160;

  var ttLeft = rect.left + (rect.width / 2) - (tooltipWidth / 2);

  ttLeft = Math.max(16, Math.min(window.innerWidth - tooltipWidth - 16, ttLeft));

  var spaceBelow = window.innerHeight - rect.bottom;

  var placeAbove = spaceBelow < tooltipHeight + 20 && rect.top > tooltipHeight + 20;

  var ttTop = 0;

  if (placeAbove) {

    ttTop = rect.top - tooltipHeight - 12;

    if (arrow) {

      arrow.className = 'tour-tooltip-arrow arrow-bottom';

      var arrowLeft = rect.left + (rect.width / 2) - ttLeft - 8;

      arrow.style.left = Math.max(16, Math.min(tooltipWidth - 24, arrowLeft)) + 'px';

    }

  } else {

    ttTop = rect.bottom + 12;

    if (arrow) {

      arrow.className = 'tour-tooltip-arrow arrow-top';

      var arrowLeft = rect.left + (rect.width / 2) - ttLeft - 8;

      arrow.style.left = Math.max(16, Math.min(tooltipWidth - 24, arrowLeft)) + 'px';

    }

  }

  tooltip.style.left = ttLeft + 'px';

  tooltip.style.top = ttTop + 'px';

}

function nextGasTourStep() {

  if (_gasTourCurrentStep < _gasTourSteps.length - 1) {

    _gasTourCurrentStep++;

    renderGasTourStep(_gasTourCurrentStep);

  } else {

    closeGasTour();

    tt('🎉 您已完成 GAS 雲端上傳指引！填妥資訊後即可直接開房！', 'ok');

  }

}

function prevGasTourStep() {

  if (_gasTourCurrentStep > 0) {

    _gasTourCurrentStep--;

    renderGasTourStep(_gasTourCurrentStep);

  }

}

function closeGasTour() {

  if (_gasTourOverlayEl) {

    _gasTourOverlayEl.style.display = 'none';

  }

}

// 註冊至全域 window，方便 HTML onclick 呼叫

window.startGasSpotlightTour = startGasSpotlightTour;

window.nextGasTourStep = nextGasTourStep;

window.prevGasTourStep = prevGasTourStep;

window.closeGasTour = closeGasTour;

window.copyInPageGuideScript = copyInPageGuideScript;

// ═══════════════════════════════════════════════════════
// ☁️ Supabase 雲端資源與 5GB 流量脫敏監控模組 (雜湊壓縮加密中繼)
// ═══════════════════════════════════════════════════════

var _latestCloudMetrics = null;

function openCloudMetricsModal() {
  var modal = document.getElementById('modal-cloud-metrics');
  if (modal) {
    modal.style.display = 'flex';
    modal.classList.add('active');
  }
  fetchAndRefreshCloudMetrics(false);
}

function closeCloudMetricsModal() {
  var modal = document.getElementById('modal-cloud-metrics');
  if (modal) {
    modal.style.display = 'none';
    modal.classList.remove('active');
  }
}

var _lastCloudMetricsFetchTime = 0;
var CLOUD_METRICS_INTERVAL_MS = 5 * 60 * 1000; // 🌟 5 分鐘 (300 秒)

function fetchAndRefreshCloudMetrics(isManual) {
  var now = Date.now();
  // 若為自動輪詢且距離上次獲取未滿 5 分鐘，自動略過以節省配額
  if (!isManual && (now - _lastCloudMetricsFetchTime < CLOUD_METRICS_INTERVAL_MS)) {
    return;
  }
  _lastCloudMetricsFetchTime = now;

  if (isManual) {
    tt('正在從雲端取得雜湊加密之用量數據並於本地安全解密…', 'info');
  }
  if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.get_cloud_metrics) {
    return;
  }

  // 1. 從 Supabase 取得雜湊壓縮之密文 Token
  pywebview.api.get_cloud_metrics().then(function(res) {
    if (!res || !res.ok) {
      if (isManual) tt('取得雲端指標失敗: ' + (res ? res.msg : '未知錯誤'), 'err');
      return;
    }

    var token = res.encrypted_token || '';
    // 2. 依照使用者指定架構：前端調用解密還原原始指標
    if (token && window.pywebview.api.decrypt_cloud_metrics) {
      pywebview.api.decrypt_cloud_metrics(token).then(function(decRes) {
        if (decRes && decRes.ok && decRes.data) {
          applyCloudMetricsData(decRes.data, token);
          if (isManual) tt('✅ 已成功解密還原最新 Supabase 雲端用量！', 'ok');
        } else {
          applyCloudMetricsData(res.data, token);
        }
      }).catch(function() {
        applyCloudMetricsData(res.data, token);
      });
    } else {
      applyCloudMetricsData(res.data, token);
    }
  }).catch(function(err) {
    if (isManual) tt('連線異常: ' + err, 'err');
  });
}

function applyCloudMetricsData(data, token) {
  if (!data) return;
  _latestCloudMetrics = data;

  // 1. 更新大廳頂部徽章文字
  var badgeText = document.getElementById('party-quota-text');
  if (badgeText) {
    var egVal = (data.egress_used_gb !== undefined) ? data.egress_used_gb : 0.002;
    var egMax = data.egress_max_gb || 5.0;
    var egPct = (data.egress_usage_pct !== undefined) ? data.egress_usage_pct : 0.04;
    badgeText.textContent = 'Egress: ' + egVal + '/' + egMax + 'GB (' + egPct + '%)';
  }

  // 2. 更新彈窗 Egress 條
  var egText = document.getElementById('metric-egress-text');
  var egBar = document.getElementById('metric-egress-bar');
  if (egText) egText.textContent = (data.egress_used_gb || 0.002) + ' / ' + (data.egress_max_gb || 5.0) + ' GB (' + (data.egress_usage_pct || 0.04) + '%)';
  if (egBar) egBar.style.width = Math.min(100, Math.max(0.5, (data.egress_usage_pct || 0.04))) + '%';

  // 3. 更新彈窗 Database 條
  var dbMb = Math.round((data.database_size_gb || 0.026) * 1000);
  var dbText = document.getElementById('metric-db-text');
  var dbBar = document.getElementById('metric-db-bar');
  if (dbText) dbText.textContent = dbMb + ' / 500 MB (' + (data.database_usage_pct || 5.2) + '%)';
  if (dbBar) dbBar.style.width = Math.min(100, Math.max(1, (data.database_usage_pct || 5.2))) + '%';

  // 4. 更新密文預覽 (展現雜湊壓縮加密之 Token)
  var tokenPreview = document.getElementById('metric-token-preview');
  if (tokenPreview) {
    if (token && token.length > 20) {
      tokenPreview.textContent = token.slice(0, 36) + '...' + token.slice(-16) + ' (長度: ' + token.length + ' 字元, 雜湊高壓密文)';
    } else {
      tokenPreview.textContent = token || '已由本地安全緩存';
    }
  }

  // 5. 更新時間
  var upText = document.getElementById('metric-updated-at');
  if (upText) {
    var d = data.updated_at ? new Date(data.updated_at) : new Date();
    upText.textContent = '更新時間: ' + d.toLocaleTimeString() + ' (探測頻率: 5分鐘一次 · 每日 < 1MB)';
  }
}

window.openCloudMetricsModal = openCloudMetricsModal;
window.closeCloudMetricsModal = closeCloudMetricsModal;
window.fetchAndRefreshCloudMetrics = fetchAndRefreshCloudMetrics;

window.updateCreateRoomBtnState = updateCreateRoomBtnState;

// ═════════════════════════════════════════════════════════════════════
// 全鏈路資料流即時診斷與 LOG 監視視窗 (Telemetry Diagnostics Modal)
// ═════════════════════════════════════════════════════════════════════

var _telemetryAutoRefreshTimer = null;

function openPartyTelemetryModal() {
  var modal = document.getElementById('party-telemetry-modal');
  if (!modal) return;
  modal.style.display = 'flex';
  refreshPartyTelemetryLogs(false);
  
  // 開啟時啟動每 3 秒自動刷新
  if (_telemetryAutoRefreshTimer) clearInterval(_telemetryAutoRefreshTimer);
  _telemetryAutoRefreshTimer = setInterval(function() {
    var m = document.getElementById('party-telemetry-modal');
    if (m && m.style.display !== 'none') {
      refreshPartyTelemetryLogs(false);
    } else {
      clearInterval(_telemetryAutoRefreshTimer);
      _telemetryAutoRefreshTimer = null;
    }
  }, 3000);
}

function closePartyTelemetryModal(e) {
  if (e && e.target && e.target.classList && !e.target.classList.contains('detail-modal-overlay') && !e.target.classList.contains('detail-close-btn')) {
    return;
  }
  var modal = document.getElementById('party-telemetry-modal');
  if (modal) modal.style.display = 'none';
  if (_telemetryAutoRefreshTimer) {
    clearInterval(_telemetryAutoRefreshTimer);
    _telemetryAutoRefreshTimer = null;
  }
}

function refreshPartyTelemetryLogs(showToast) {
  if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.get_party_telemetry_logs) {
    var c = document.getElementById('party-telemetry-modal-content');
    if (c) c.innerHTML = '<div style="color:#ff8585;text-align:center;padding:20px">API 尚未就緒</div>';
    return;
  }
  
  pywebview.api.get_party_telemetry_logs(150).then(function(res) {
    var container = document.getElementById('party-telemetry-modal-content');
    if (!container) return;
    
    if (!res || !res.ok || !res.logs || res.logs.length === 0) {
      container.innerHTML = '<div style="color:var(--gray);text-align:center;padding:25px">尚無端到端資料流遙測記錄（請嘗試點擊綁定 Discord、創建房間或加入房間測試）</div>';
      return;
    }
    
    var html = '';
    var logs = res.logs;
    for (var i = 0; i < logs.length; i++) {
      var item = logs[i];
      var catColor = '#8892b0';
      var catBg = 'rgba(255,255,255,0.06)';
      if (item.category === 'OAUTH') { catColor = '#5865F2'; catBg = 'rgba(88,101,242,0.15)'; }
      else if (item.category === 'DPAPI') { catColor = '#10b981'; catBg = 'rgba(16,185,129,0.15)'; }
      else if (item.category === 'SUPABASE') { catColor = '#3ecf8e'; catBg = 'rgba(62,207,142,0.15)'; }
      else if (item.category === 'TURSO') { catColor = '#00e5ff'; catBg = 'rgba(0,229,255,0.15)'; }
      else if (item.category === 'WEBRTC') { catColor = '#f59e0b'; catBg = 'rgba(245,158,11,0.15)'; }
      
      var lvlColor = '#cbd5e1';
      if (item.level === 'SUCCESS') lvlColor = '#4ade80';
      else if (item.level === 'WARN') lvlColor = '#facc15';
      else if (item.level === 'ERROR') lvlColor = '#f87171';
      
      var detailsHtml = '';
      if (item.details && Object.keys(item.details).length > 0) {
        var jsonStr = JSON.stringify(item.details);
        if (jsonStr.length > 200) jsonStr = jsonStr.substring(0, 200) + '...';
        detailsHtml = '<div style="margin-top:3px;color:#94a3b8;font-size:11px;padding-left:12px;border-left:2px solid rgba(255,255,255,0.1)">↳ ' + escapeHtml(jsonStr) + '</div>';
      }
      
      html += '<div style="padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04);word-break:break-all;">'
            + '<span style="color:#64748b;margin-right:8px;font-size:11px;">[' + item.timestamp + ']</span>'
            + '<span style="color:' + catColor + ';background:' + catBg + ';padding:2px 6px;border-radius:4px;font-size:11px;font-weight:700;margin-right:8px;">' + item.category + '</span>'
            + '<span style="color:' + lvlColor + ';font-weight:600;margin-right:8px;">' + escapeHtml(item.message) + '</span>'
            + detailsHtml
            + '</div>';
    }
    container.innerHTML = html;
    container.scrollTop = container.scrollHeight;
    
    if (showToast) {
      if (typeof tt === 'function') tt('已更新資料流診斷日誌 (' + logs.length + ' 條)', 'success');
    }
  }).catch(function(err) {
    var c = document.getElementById('party-telemetry-modal-content');
    if (c) c.innerHTML = '<div style="color:#ff8585;text-align:center;padding:20px">讀取異常: ' + escapeHtml(String(err)) + '</div>';
  });
}

function copyPartyTelemetryLogText() {
  if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.get_party_telemetry_text) {
    if (typeof tt === 'function') tt('API 尚未就緒', 'warn');
    return;
  }
  pywebview.api.get_party_telemetry_text(150).then(function(res) {
    if (res && res.ok && res.text) {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(res.text).then(function() {
          if (typeof tt === 'function') tt('📋 已複製完整資料流日誌至剪貼簿！', 'success');
        }).catch(function() {
          fallbackCopyText(res.text);
        });
      } else {
        fallbackCopyText(res.text);
      }
    } else {
      if (typeof tt === 'function') tt('尚無日誌可複製', 'info');
    }
  }).catch(function(err) {
    if (typeof tt === 'function') tt('複製失敗: ' + err, 'error');
  });
}

function fallbackCopyText(text) {
  var ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.left = '-9999px';
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand('copy');
    if (typeof tt === 'function') tt('📋 已複製完整資料流日誌至剪貼簿！', 'success');
  } catch(e) {
    if (typeof tt === 'function') tt('複製失敗，請手動複製', 'error');
  }
  document.body.removeChild(ta);
}

function openPartyTelemetryLogInEditor() {
  if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.open_party_telemetry_file) {
    return;
  }
  pywebview.api.open_party_telemetry_file().then(function(res) {
    if (res && res.ok) {
      if (typeof tt === 'function') tt('已在外部編輯器中開啟 party_telemetry.log', 'success');
    } else {
      if (typeof tt === 'function') tt(res.msg || '開啟日誌檔案失敗', 'warn');
    }
  });
}

function clearPartyTelemetryLogs() {
  if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.clear_party_telemetry_logs) {
    return;
  }
  pywebview.api.clear_party_telemetry_logs().then(function(res) {
    if (res && res.ok) {
      if (typeof tt === 'function') tt('已清空本地資料流日誌', 'success');
      refreshPartyTelemetryLogs(false);
    }
  });
}

/**
 * 觸發組隊系統專屬全方位健康體檢 (Teaming & Cloud Architecture Health Check)
 */
async function triggerPartyDedicatedHealthCheck() {
  var modal = document.getElementById('party-telemetry-modal');
  var content = document.getElementById('party-telemetry-modal-content');
  var badge = document.getElementById('party-telemetry-status-badge');

  if (modal) modal.style.display = 'flex';
  if (badge) {
    badge.textContent = '🩺 正在健檢中...';
    badge.className = 'chip yellow';
  }
  if (content) {
    content.innerHTML = '<div style="text-align:center;padding:30px;color:var(--gray)"><div style="font-size:24px;margin-bottom:8px">⏳</div>正在對 Supabase、時鐘同步、Turso Edge、身分錨點與 STUN 進行全方位體檢…</div>';
  }

  try {
    if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.run_party_health_check) {
      if (content) content.innerHTML = '<div style="color:#ff8585;padding:20px;text-align:center">後端 API 尚未就緒</div>';
      return;
    }

    var res = await pywebview.api.run_party_health_check();
    if (!res || !res.ok || !res.data) {
      if (content) content.innerHTML = '<div style="color:#ff8585;padding:20px;text-align:center">健檢失敗: ' + (res && res.msg || '未知錯誤') + '</div>';
      return;
    }

    var data = res.data;
    var isOk = data.status === 'OK';
    if (badge) {
      badge.textContent = isOk ? '✅ 狀態極佳 (10/10 就緒)' : (data.status === 'WARN' ? '⚠️ 部分警示' : '❌ 核心異常');
      badge.className = 'chip ' + (isOk ? 'green' : (data.status === 'WARN' ? 'yellow' : 'red'));
    }

    var items = data.items || [];
    var html = '<div style="margin-bottom:12px;padding:10px 14px;background:rgba(88,101,242,0.12);border:1px solid rgba(88,101,242,0.25);border-radius:8px;display:flex;align-items:center;justify-content:space-between">';
    html += '<div style="font-weight:700;font-size:13px;color:var(--text);display:flex;align-items:center;gap:6px"><span>👥</span><span>無伺服器組隊大廳與雲端架構體檢報告</span></div>';
    html += '<span class="badge" style="background:' + (isOk ? '#4CAF50' : '#FF9800') + ';color:#fff;font-size:10px;padding:2px 8px;border-radius:6px">' + data.status + '</span>';
    html += '</div>';

    html += '<div style="display:flex;flex-direction:column;gap:8px">';
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      var icon = item.status === 'OK' ? '🟢' : (item.status === 'WARN' ? '🟡' : (item.status === 'INFO' ? '🔵' : '🔴'));
      html += '<div style="padding:10px 12px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:8px;display:flex;align-items:flex-start;justify-content:space-between;gap:12px">';
      html += '<div style="flex:1">';
      html += '<div style="font-weight:600;color:var(--text);font-size:12px;display:flex;align-items:center;gap:6px"><span>' + icon + '</span><span>' + item.name + '</span></div>';
      html += '<div style="color:var(--gray);font-size:11px;margin-top:3px;margin-left:20px;line-height:1.4">' + item.desc + '</div>';
      html += '</div>';
      if (item.action === 'auth_party_discord') {
        html += '<button class="btn btn-p btn-xs" onclick="startDiscordOAuthFlow()" style="padding:3px 8px;font-size:10px;white-space:nowrap">🎮 綁定認證</button>';
      } else if (item.action === 'open_telemetry') {
        html += '<button class="btn btn-o btn-xs" onclick="refreshPartyTelemetryLogs()" style="padding:3px 8px;font-size:10px;white-space:nowrap">📋 檢視日誌</button>';
      }
      html += '</div>';
    }
    html += '</div>';

    if (content) content.innerHTML = html;
    if (typeof tt === 'function') tt('組隊全鏈路健檢完成：' + (isOk ? '10/10 項目就緒' : '發現警示項目'), isOk ? 'success' : 'warn');
  } catch (e) {
    if (content) content.innerHTML = '<div style="color:#ff8585;padding:20px;text-align:center">體檢異常: ' + (e.message || e) + '</div>';
  }
}

window.openPartyTelemetryModal = openPartyTelemetryModal;
window.closePartyTelemetryModal = closePartyTelemetryModal;
window.refreshPartyTelemetryLogs = refreshPartyTelemetryLogs;
window.copyPartyTelemetryLogText = copyPartyTelemetryLogText;
window.openPartyTelemetryLogInEditor = openPartyTelemetryLogInEditor;
window.clearPartyTelemetryLogs = clearPartyTelemetryLogs;
window.triggerPartyDedicatedHealthCheck = triggerPartyDedicatedHealthCheck;
window.toggleWebhookVideoAudio = toggleWebhookVideoAudio;
window.savePartyPreFilledContact = savePartyPreFilledContact;
window.showPartyHostCompletionCentralModal = showPartyHostCompletionCentralModal;
window.showPartyMemberCompletionCentralModal = showPartyMemberCompletionCentralModal;
window.closePartyCompletionCentralModal = closePartyCompletionCentralModal;
window.finishPartyAndBroadcast = finishPartyAndBroadcast;
window.extendPartyWaitTime = extendPartyWaitTime;
window.renderRoomView = renderRoomView;



