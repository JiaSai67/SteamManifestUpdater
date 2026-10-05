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
    
    // 更新單一組隊暱稱
    var nameEl = document.getElementById('party-my-name');
    if (nameEl) nameEl.textContent = res.nickname || '未命名特工';

    // 更新配額狀態 (數值化呈現)
    if (res.quota) {
      updatePartyQuotaUI(res.quota);
    }
  }).catch(function(err) {
    console.error('獲取組隊 Profile 失敗:', err);
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
  if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.get_party_room_details) return;
  pywebview.api.get_party_room_details('').then(function(res) {
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
  if (!_isPartyActive) return;
  if (document.hidden) return; // 視窗縮小或在後台時 0 請求！
  
  if (_partyPollTimer) clearTimeout(_partyPollTimer);

  // 若不在房間內，且使用者已閒置超過 45 秒，暫停大廳自動輪詢，節省 100% 閒置額度
  if (!_partyCurRoom && (Date.now() - _partyLastUserAction > 45000)) {
    _partyIsIdle = true;
    return;
  }

  _partyPollTimer = setTimeout(function() {
    if (!_isPartyActive || document.hidden) return;

    if (_partyCurRoom) {
      // 房內成員狀態即時輪詢 (每 3 秒)
      pywebview.api.get_party_room_details('').then(function(res) {
        if (res && res.ok && res.room) {
          _partyCurRoom = res.room;
          updateSidebarRoomInfo(res.room);
          if (_partyActiveNav === 'room') {
            renderRoomView(res.room);
          } else if (_partyActiveNav === 'lobby') {
            // 在房內但同時瀏覽大廳：每 3 次心跳(約 9 秒)靜默同步一次大廳列表
            if (!_lobbyBackgroundTick) _lobbyBackgroundTick = 0;
            _lobbyBackgroundTick++;
            if (_lobbyBackgroundTick >= 3) {
              _lobbyBackgroundTick = 0;
              refreshPartyLobby(false);
            }
          }
          schedulePartyPolling(3000);
        } else {
          tt(res && res.msg ? res.msg : '房間已解散或過期蒸發', 'info');
          _partyCurRoom = null;
          updateSidebarRoomInfo(null);
          switchPartyNav('lobby');
          refreshPartyLobby(false);
        }
      }).catch(function() {
        schedulePartyPolling(5000);
      });
    } else {
      // 大廳公開房間列表輪詢 (10 秒一次)
      refreshPartyLobby(false);
    }
  }, delay || 10000);
}

/**
 * 重新拉取大廳房間清單 (支援手動點擊與 CDN 邊緣快取保護)
 */
function refreshPartyLobby(isUserClick) {
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
    var note = r.note ? ('<div class="party-room-card-note">' + escapeHtml(r.note) + '</div>') : '';
    
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
  if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.join_party_room) return;
  tt('🌸 正在加入房間 #' + roomId + '…', 'info');

  pywebview.api.join_party_room(roomId).then(function(res) {
    if (res && res.ok && res.room) {
      tt(res.msg || '成功進入房間 #' + roomId, 'ok');
      _partyCurRoom = res.room;
      updateSidebarRoomInfo(res.room);
      switchPartyNav('room');
      schedulePartyPolling(3000);
    } else {
      tt(res && res.msg ? res.msg : '加入房間失敗', 'err');
    }
  }).catch(function(err) {
    tt('加入房間出錯: ' + err, 'err');
  });
}

/**
 * 切換至房間內部視圖並渲染成員清單
 * 嚴格遵循格式規範：
 * 'name' ('discord name')
 * '下載狀況(未下載/下載中： xx%/就緒)'
 */
function renderRoomView(room) {
  if (!room || !room.room_id) {
    switchPartyNav('lobby');
    return;
  }
  var lobbyView = document.getElementById('party-lobby-view');
  var roomView = document.getElementById('party-room-view');
  if (lobbyView) { lobbyView.style.display = 'none'; lobbyView.classList.remove('active'); }
  if (roomView) { roomView.style.display = 'flex'; roomView.classList.add('active'); }

  var rid = room.room_id || '';
  var gameName = room.game_name || '未知遊戲';
  var appid = room.appid ? String(room.appid).trim() : '';
  var hostName = room.host_name || '房主';
  var hostDiscord = room.host_discord || '';
  var maxPlayers = room.max_players || 4;
  var members = Array.isArray(room.members) ? room.members : [];

  // 判斷自己是否為房主
  var myName = (_partyProfile && _partyProfile.nickname) || '';
  var isHost = (hostName === myName);

  // 頂部資料填充
  var titleEl = document.getElementById('party-room-game-title');
  if (titleEl) titleEl.textContent = gameName;

  var appidBadge = document.getElementById('party-room-appid-badge');
  if (appidBadge) {
    appidBadge.textContent = appid ? ('AppID: ' + appid) : '無 AppID';
    appidBadge.style.display = appid ? 'inline-block' : 'none';
  }

  var codeVal = document.getElementById('party-room-code-val');
  if (codeVal) codeVal.textContent = rid;

  var playersVal = document.getElementById('party-room-players-val');
  if (playersVal) playersVal.textContent = '👥 ' + (members.length + 1) + ' / ' + maxPlayers + ' 人';

  var roleVal = document.getElementById('party-room-role-val');
  if (roleVal) {
    roleVal.textContent = isHost ? '👑 房主' : '⚔️ 隊員';
    roleVal.className = 'party-room-role-badge ' + (isHost ? 'host' : 'member');
  }

  // 封面圖
  var coverImg = document.getElementById('party-room-cover-img');
  var coverPlaceholder = document.getElementById('party-room-cover-placeholder');
  if (coverImg && coverPlaceholder) {
    if (appid) {
      coverImg.src = 'https://cdn.cloudflare.steamstatic.com/steam/apps/' + appid + '/header.jpg';
      coverImg.style.display = 'block';
      coverPlaceholder.style.display = 'none';
      coverImg.onerror = function() {
        coverImg.style.display = 'none';
        coverPlaceholder.style.display = 'flex';
      };
    } else {
      coverImg.style.display = 'none';
      coverPlaceholder.style.display = 'flex';
    }
  }

  // 退出 / 解散按鈕標題
  var leaveBtn = document.getElementById('party-btn-leave-or-close');
  if (leaveBtn) {
    leaveBtn.textContent = isHost ? '❌ 解散房間' : '🚪 退出房間';
  }

  // 備註展示
  var noteEl = document.getElementById('party-room-note-val');
  if (noteEl) {
    if (room.note) {
      noteEl.textContent = '📢 招募備註：' + room.note;
      noteEl.style.display = 'block';
    } else {
      noteEl.style.display = 'none';
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
        is_host: isHostMember
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

  // 檢查是否全員就緒
  var isAllReady = allMembers.every(function(m) {
    return m.status === '就緒' || m.progress >= 100;
  });
  var allReadyBanner = document.getElementById('party-all-ready-banner');
  if (allReadyBanner) {
    allReadyBanner.style.display = isAllReady ? 'flex' : 'none';
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
  if (myMemberObj) {
    var myStatus = myMemberObj.status || '未下載';
    isMyReady = (myStatus === '就緒' || (myMemberObj.progress >= 100));
    if (myStatusBadge) {
      myStatusBadge.textContent = myStatus;
      myStatusBadge.className = 'my-status-badge ' + (isMyReady ? 'ready' : (myStatus === '下載中' ? 'downloading' : 'not_downloaded'));
    }
  }

  // 1. 如果本機狀態已經是就緒，那麼就不需要同步環境，就不用顯示按鈕
  if (syncBtnWrap) {
    syncBtnWrap.style.display = isMyReady ? 'none' : 'block';
  } else if (syncBtn) {
    syncBtn.style.display = isMyReady ? 'none' : 'inline-flex';
  }

  // 2. 房主若有分享 Google Drive 整合包，隊員端顯示專屬下載按鈕
  var pkgWrap = document.getElementById('party-gdrive-pkg-wrap');
  if (pkgWrap) {
    var hasGdrive = !!(room.gdrive_url || room.download_url);
    pkgWrap.style.display = (hasGdrive && !isHost) ? 'block' : 'none';
  }

  var html = '';
  allMembers.forEach(function(m, idx) {
    var name = m.name || '玩家';
    var status = m.status || '未下載';
    var progress = m.progress || 0;
    var isMe = (m.id && myId && m.id === myId) || (m.name === myName);

    // 格式化下載狀況文字 (無單引號)
    var statusDisplay = '';
    if (status === '就緒' || progress >= 100) {
      statusDisplay = '下載狀況(就緒)';
    } else if (status === '下載中') {
      statusDisplay = '下載狀況(下載中： ' + progress + '%)';
    } else {
      statusDisplay = '下載狀況(未下載)';
    }

    var statusClass = (status === '就緒' || progress >= 100) ? 'status-ready' : (status === '下載中' ? 'status-downloading' : 'status-not-downloaded');

    html += '<div class="party-member-card ' + (isMe ? 'is-me' : '') + '">' +
      '<div class="member-card-left">' +
        '<div class="member-avatar-wrap">' +
          '<div class="member-avatar-icon">' + (m.is_host ? '👑' : '🎮') + '</div>' +
        '</div>' +
        '<div class="member-info-column">' +
          '<!-- 第 1 行：玩家名稱 (已刪除 DC 暱稱，刪除周圍單引號) -->' +
          '<div class="member-identity-row">' +
            '<span class="member-primary-name">' + escapeHtml(name) + '</span>' +
            (m.is_host ? '<span class="member-badge-host">房主</span>' : '') +
            (isMe ? '<span class="member-badge-me">我</span>' : '') +
          '</div>' +
          '<!-- 第 2 行：下載狀況 (刪除周圍單引號) -->' +
          '<div class="member-status-row">' +
            '<span class="member-status-text ' + statusClass + '">' + escapeHtml(statusDisplay) + '</span>' +
          '</div>' +
        '</div>' +
      '</div>' +
      '<div class="member-card-right">' +
        '<div class="member-progress-outer">' +
          '<div class="member-progress-bar ' + (status === '就緒' ? 'ready' : '') + '" style="width:' + (status === '就緒' ? 100 : progress) + '%"></div>' +
        '</div>' +
      '</div>' +
    '</div>';
  });

  listContainer.innerHTML = html;
}

/**
 * 隊員點擊「安裝遊戲」
 */
function startSyncCurrentGameInstall() {
  if (!_partyCurRoom) return;
  var rid = _partyCurRoom.room_id;
  var appid = _partyCurRoom.appid;

  var syncBtn = document.getElementById('party-btn-start-sync');
  if (syncBtn) {
    syncBtn.disabled = true;
    syncBtn.innerHTML = '<span class="spinner" style="display:inline-block;width:14px;height:14px;border:2px solid #fff;border-top-color:transparent;border-radius:50%;animation:spin 0.8s linear infinite;margin-right:6px"></span> 正在安裝遊戲…';
  }

  tt('🌸 已啟動遊戲安裝程序…', 'info');

  pywebview.api.start_party_sync_download(rid, appid).then(function(res) {
    if (res && res.ok) {
      tt(res.msg || '遊戲安裝已在背景執行', 'ok');
    } else {
      tt(res && res.msg ? res.msg : '安裝失敗', 'err');
      if (syncBtn) {
        syncBtn.disabled = false;
        syncBtn.innerHTML = '🎮 安裝遊戲';
      }
    }
  }).catch(function(err) {
    tt('啟動安裝出錯: ' + err, 'err');
    if (syncBtn) {
      syncBtn.disabled = false;
      syncBtn.innerHTML = '🎮 安裝遊戲';
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
 * 退出或解散房間
 */
function leaveOrCloseCurrentRoom() {
  if (!_partyCurRoom) return;
  var isHost = (_partyCurRoom.host_name === ((_partyProfile && _partyProfile.nickname) || ''));
  var actionText = isHost ? '解散該房間' : '退出房間';

  if (!confirm('確定要' + actionText + '嗎？')) return;

  tt('🌸 正在' + actionText + '…', 'info');
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
function updateCreateRoomBtnState() {
  var select = document.getElementById('select-party-installed-games');
  var gasInput = document.getElementById('input-party-gas-url');
  var btn = document.getElementById('btn-submit-create-party');
  if (!btn) return;

  var hasGame = !!(select && select.value && select.value.trim());
  var hasGas = !!(gasInput && gasInput.value && gasInput.value.trim());

  var isReady = hasGame && hasGas;

  if (isReady) {
    if (btn.disabled || btn.classList.contains('disabled')) {
      btn.disabled = false;
      btn.classList.remove('disabled');
      btn.title = '✨ 必要資訊已就緒，可立即開房！';
      // 重新觸發 CSS 變色擴張動畫 (強制 reflow)
      btn.style.animation = 'none';
      void btn.offsetWidth;
      btn.style.animation = '';
    }
  } else {
    btn.disabled = true;
    btn.classList.add('disabled');
    var missing = [];
    if (!hasGame) missing.push('挑選組隊遊戲');
    if (!hasGas) missing.push('填寫 GAS 網址');
    btn.title = '⚠️ 請先完成：' + missing.join(' 與 ');
  }
}

function openCreateRoomModal() {
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

  // 初始按鈕置灰禁用
  updateCreateRoomBtnState();

  // 重置三檔指示燈
  resetResourceInspectBadges();

  // 載入本地已入庫遊戲下拉選單
  loadInstalledGamesDropdown();

  // 確保三檔同步區塊常駐展開
  var wrap = document.getElementById('party-gas-config-wrap');
  if (wrap) wrap.style.display = 'block';
  var chk = document.getElementById('check-party-auto-upload');
  if (chk) chk.checked = true;

  // 載入房主已保存之 GAS 網址設定
  if (window.pywebview && window.pywebview.api && window.pywebview.api.get_gas_config) {
    pywebview.api.get_gas_config().then(function(res) {
      if (res && res.ok) {
        var gasInput = document.getElementById('input-party-gas-url');
        if (gasInput && res.gas_url) {
          gasInput.value = res.gas_url;
          updateCreateRoomBtnState();
        }
      }
    });
  }

  modal.style.display = 'flex';
  modal.classList.remove('hidden');
  modal.classList.add('active');
}

function closeCreateRoomModal() {
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
  var m = document.getElementById('inspect-manifest');
  var l = document.getElementById('inspect-lua');
  var p = document.getElementById('inspect-patch');
  if (m) { m.textContent = '📄 Manifest: 待偵測'; m.style.color = 'var(--gray)'; }
  if (l) { l.textContent = '📜 Lua 腳本: 待偵測'; l.style.color = 'var(--gray)'; }
  if (p) { p.textContent = '🎮 線上補丁: 待偵測'; p.style.color = 'var(--gray)'; }
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
  var mEl = document.getElementById('inspect-manifest');
  var lEl = document.getElementById('inspect-lua');
  var pEl = document.getElementById('inspect-patch');

  if (mEl) mEl.textContent = '📄 Manifest: 檢測中…';
  if (lEl) lEl.textContent = '📜 Lua 腳本: 檢測中…';
  if (pEl) pEl.textContent = '🎮 線上補丁: 檢測中…';

  pywebview.api.inspect_party_resources(appid).then(function(res) {
    if (!res) return;
    if (mEl) {
      if (res.manifest && res.manifest.ready) {
        var kb = Math.round((res.manifest.size || 0) / 1024);
        mEl.textContent = '📄 Manifest: ✅ 就緒 (' + kb + 'KB)';
        mEl.style.color = '#2ED573';
      } else {
        mEl.textContent = '📄 Manifest: ❌ 缺少';
        mEl.style.color = '#FFA502';
      }
    }
    if (lEl) {
      if (res.lua && res.lua.ready) {
        lEl.textContent = '📜 Lua 腳本: ✅ 就緒';
        lEl.style.color = '#2ED573';
      } else {
        lEl.textContent = '📜 Lua 腳本: ❌ 缺少';
        lEl.style.color = '#FFA502';
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
  });
}

function copyGasSampleScript() {
  if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.get_gas_config) return;
  pywebview.api.get_gas_config().then(function(res) {
    if (res && res.sample_script) {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(res.sample_script).then(function() {
          tt('📋 已複製 Google Apps Script 範本腳本至剪貼簿！', 'ok');
        }).catch(function() {
          tt('複製腳本失敗，請手動複製', 'err');
        });
      } else {
        tt('剪貼簿不支援自動寫入', 'warn');
      }
    }
  });
}

function openGasHelpGuide() {
  tt('🌸 正在為您開啟圖文引導網頁…', 'info');
  if (window.pywebview && window.pywebview.api && window.pywebview.api.open_gas_guide_page) {
    pywebview.api.open_gas_guide_page().then(function(res) {
      if (res && res.ok) {
        tt('🌐 已在瀏覽器中開啟一步一步部署引導網頁', 'ok');
      } else {
        window.open('gas_guide.html', '_blank');
      }
    }).catch(function() {
      window.open('gas_guide.html', '_blank');
    });
  } else {
    window.open('gas_guide.html', '_blank');
  }
}

function copyInPageGuideScript() {
  var inlineCode = `(function(){` +
    `var newProj=Array.from(document.querySelectorAll('button, div[role="button"], a')).find(function(el){var t=(el.innerText||el.textContent||'').trim();return(t.indexOf('新專案')!==-1||t.indexOf('New project')!==-1||t.indexOf('建立 APPS SCRIPT')!==-1)&&el.offsetParent!==null;});` +
    `if(newProj){` +
      `newProj.scrollIntoView({behavior:'smooth',block:'center'});` +
      `var box=document.createElement('div');box.style='position:fixed;z-index:2147483640;border:3px solid #FF4757;border-radius:12px;box-shadow:0 0 0 9999px rgba(0,0,0,0.76),0 0 24px #FF4757;pointer-events:none;transition:all .3s;';` +
      `var rect=newProj.getBoundingClientRect();box.style.left=(rect.left-6)+'px';box.style.top=(rect.top-6)+'px';box.style.width=(rect.width+12)+'px';box.style.height=(rect.height+12)+'px';` +
      `var tip=document.createElement('div');tip.style='position:fixed;z-index:2147483645;background:#161B22;border:2px solid #FF4757;border-radius:14px;padding:14px 18px;color:#fff;font-family:sans-serif;max-width:320px;left:'+(rect.right+16)+'px;top:'+rect.top+'px;box-shadow:0 10px 30px rgba(0,0,0,.8);';` +
      `tip.innerHTML='<div style="color:#FF6B81;font-size:11px;font-weight:800;margin-bottom:4px;">✨ SMU 部署精靈 (第 1 步)</div><div style="font-size:15px;font-weight:800;margin-bottom:6px;">👉 點擊此處「➕ 新專案」</div><div style="font-size:12px;color:#CBD5E1;line-height:1.5;">點擊此處建立專案，進入編輯器後精靈會自動指引下一步！</div>';` +
      `document.body.appendChild(box);document.body.appendChild(tip);` +
      `newProj.addEventListener('click',function(){box.remove();tip.remove();},{once:true});` +
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

function testGasUrlConnection() {
  var input = document.getElementById('input-party-gas-url');
  var url = (input ? input.value : '').trim();
  if (!url) {
    tt('請先輸入 Google Apps Script 網址', 'warn');
    return;
  }
  tt('🌸 正在測試 GAS 雲端連線…', 'info');
  pywebview.api.test_gas_endpoint(url).then(function(res) {
    if (res && res.ok) {
      tt(res.msg || '✅ GAS 雲端連線測試成功！服務正常運作', 'ok');
      // 自動記住有效網址
      if (window.pywebview.api.set_gas_config) {
        pywebview.api.set_gas_config(url);
      }
    } else {
      tt(res && res.msg ? res.msg : 'GAS 連線失敗，請檢查網址與存取權限', 'err');
    }
  }).catch(function(err) {
    tt('連線測試異常: ' + err, 'err');
  });
}

function cleanGasSpaceNow() {
  var input = document.getElementById('input-party-gas-url');
  var url = (input ? input.value : '').trim();
  if (!url) {
    tt('請先輸入 Google Apps Script 網址', 'warn');
    return;
  }
  tt('🌸 正在向 Google Drive 發送清理指令…', 'info');
  pywebview.api.clean_gas_space(url).then(function(res) {
    if (res && res.ok) {
      tt(res.msg || '✅ Google Drive 歷史整合包已全數清空', 'ok');
    } else {
      tt(res && res.msg ? res.msg : '清理空間失敗', 'err');
    }
  }).catch(function(err) {
    tt('清理請求異常: ' + err, 'err');
  });
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
  var btnSubmit = document.getElementById('btn-submit-create-party');
  var btnCancel = document.getElementById('btn-cancel-create-party');

  var flowPanel = document.getElementById('party-create-flow-status');
  var flowTitle = document.getElementById('party-flow-status-title');
  var flowSpinner = document.getElementById('party-flow-status-spinner');
  var flowError = document.getElementById('party-flow-error-msg');

  var gameName = (gnInput ? gnInput.value : '').trim();
  var appid = (aidInput ? aidInput.value : '').trim();
  var maxPlayers = parseInt(maxSelect ? maxSelect.value : 4, 10);
  var isPublic = (pubSelect ? pubSelect.value : '1') === '1';
  var note = (noteInput ? noteInput.value : '').trim();
  var gasUrl = (gasInput ? gasInput.value : '').trim();

  // 1. 遊戲選取防呆
  if (!appid || !gameName) {
    tt('⚠️ 請先由下拉選單挑選本機已安裝且已就緒的遊戲！', 'warn');
    var select = document.getElementById('select-party-installed-games');
    if (select) {
      select.focus();
      select.style.borderColor = '#FF4757';
      setTimeout(function() { select.style.borderColor = ''; }, 3000);
    }
    return;
  }

  // 2. 嚴格檢查 GAS 設定：未完成前禁止開房！
  if (!gasUrl) {
    tt('⚠️ 立即開房必須在 GAS 設定完成後才可開房！請先填妥 Google Apps Script 網址。', 'warn');
    if (gasInput) {
      gasInput.focus();
      gasInput.style.borderColor = '#FF4757';
      setTimeout(function() { gasInput.style.borderColor = ''; }, 3000);
    }
    return;
  }

  // 3. 展開流程進度面板，鎖定按鈕防止重複送出
  if (flowPanel) flowPanel.style.display = 'block';
  if (flowError) flowError.style.display = 'none';
  if (flowTitle) flowTitle.textContent = '🚀 正在執行開房前置檢核與雲端同步…';
  if (flowSpinner) flowSpinner.textContent = '⏳';

  setPartyFlowStep('flow-step-check', 'active', '🔍 1. 正在檢測本機 Manifest、Lua 腳本與補丁三檔…');
  setPartyFlowStep('flow-step-pack', 'pending', '📦 2. 封裝聯機資源整合包 (ZIP 壓縮)');
  setPartyFlowStep('flow-step-upload', 'pending', '☁️ 3. 透過 GAS 上傳整合包至個人 Google Drive');
  setPartyFlowStep('flow-step-url', 'pending', '🔗 4. 取得並驗證 Google Drive 下載網址');
  setPartyFlowStep('flow-step-supa', 'pending', '🌐 5. 向 Supabase 伺服器註冊房間並公開招募');

  if (btnSubmit) { btnSubmit.disabled = true; btnSubmit.textContent = '⏳ 檢核上傳中…'; }
  if (btnCancel) { btnCancel.disabled = true; }

  tt('📦 啟動開房前置流程：正在檢測本地三檔並同步至 Google Drive…', 'info');

  // 4. 階段一：本地三檔檢查、打包、上傳至 Google Drive 並取得下載網址
  pywebview.api.prepare_party_package_upload(appid, gasUrl).then(function(prepRes) {
    if (!prepRes || !prepRes.ok || !prepRes.download_url) {
      var errMsg = (prepRes && prepRes.msg) ? prepRes.msg : '未能成功上傳或取得下載網址';
      setPartyFlowStep('flow-step-check', 'error', '❌ 本地資源或雲端上傳檢驗未通過');
      setPartyFlowStep('flow-step-upload', 'error', '❌ Google Drive 上傳中斷');
      if (flowError) {
        flowError.style.display = 'block';
        flowError.textContent = '⛔ 開房程序已中止：' + errMsg + '。未向伺服器建立房間，請檢查後重試。';
      }
      if (flowTitle) flowTitle.textContent = '❌ 開房前置檢核未通過';
      if (flowSpinner) flowSpinner.textContent = '⚠️';
      tt('❌ 開房中止: ' + errMsg, 'err');
      if (btnSubmit) { btnSubmit.disabled = false; btnSubmit.textContent = '🚀 立即開房'; }
      if (btnCancel) { btnCancel.disabled = false; }
      return;
    }

    // 階段一完全過關，確認取得下載網址！
    var downloadUrl = prepRes.download_url;
    var fileId = prepRes.file_id || '';

    setPartyFlowStep('flow-step-check', 'done', '✅ 1. 本機 Manifest、Lua 腳本與補丁三檔檢測通過');
    setPartyFlowStep('flow-step-pack', 'done', '✅ 2. 本地聯機資源整合包封裝完成');
    setPartyFlowStep('flow-step-upload', 'done', '✅ 3. 已成功上傳整合包至個人 Google Drive');
    setPartyFlowStep('flow-step-url', 'done', '✅ 4. 已成功取得並驗證下載網址！');
    setPartyFlowStep('flow-step-supa', 'active', '🌐 5. 正在向 Supabase 伺服器發送開房要求 (包含下載網址)…');

    // 5. 階段二：向 Supabase 正式發出開房要求 (攜帶下載網址)
    pywebview.api.create_party_room(gameName, appid, maxPlayers, isPublic, note, true, gasUrl, downloadUrl, fileId).then(function(res) {
      if (res && res.ok && res.room) {
        setPartyFlowStep('flow-step-supa', 'done', '✅ 5. 成功於伺服器建立房間並同步發布下載鏈結！');
        if (flowTitle) flowTitle.textContent = '🎉 開房成功！即將進入房間大廳…';
        if (flowSpinner) flowSpinner.textContent = '✨';
        tt(res.msg || '成功建立房間！已成功附加雲端下載網址！', 'ok');

        setTimeout(function() {
          closeCreateRoomModal();
          _partyCurRoom = res.room;
          updateSidebarRoomInfo(res.room);
          switchPartyNav('room');
          schedulePartyPolling(3000);
        }, 600);
      } else {
        var createErr = (res && res.msg) ? res.msg : '伺服器建房失敗';
        setPartyFlowStep('flow-step-supa', 'error', '❌ 5. 伺服器建房失敗: ' + createErr);
        if (flowError) {
          flowError.style.display = 'block';
          flowError.textContent = '⛔ 伺服器建房失敗: ' + createErr;
        }
        tt(createErr, 'err');
        if (btnSubmit) { btnSubmit.disabled = false; btnSubmit.textContent = '🚀 立即開房'; }
        if (btnCancel) { btnCancel.disabled = false; }
      }
    }).catch(function(err) {
      setPartyFlowStep('flow-step-supa', 'error', '❌ 5. 開房伺服器通訊異常: ' + err);
      if (flowError) {
        flowError.style.display = 'block';
        flowError.textContent = '⛔ 連線伺服器異常: ' + err;
      }
      tt('向伺服器開房出錯: ' + err, 'err');
      if (btnSubmit) { btnSubmit.disabled = false; btnSubmit.textContent = '🚀 立即開房'; }
      if (btnCancel) { btnCancel.disabled = false; }
    });
  }).catch(function(prepErr) {
    setPartyFlowStep('flow-step-check', 'error', '❌ 前置檢驗異常: ' + prepErr);
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
window.updateCreateRoomBtnState = updateCreateRoomBtnState;



