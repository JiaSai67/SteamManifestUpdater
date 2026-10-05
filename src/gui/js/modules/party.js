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
    if (!_partyCurRoom) {
      tt('💡 您目前尚未在房間中，為您開啟創建房間', 'info');
      openCreateRoomModal();
      return;
    }
    _partyActiveNav = 'room';
    if (navLobby) navLobby.classList.remove('active');
    if (navRoom) navRoom.classList.add('active');
    if (lobbyView) { lobbyView.style.display = 'none'; lobbyView.classList.remove('active'); }
    if (roomView) { roomView.style.display = 'block'; roomView.classList.add('active'); }
    renderRoomView(_partyCurRoom);
  } else {
    _partyActiveNav = 'lobby';
    if (navRoom) navRoom.classList.remove('active');
    if (navLobby) navLobby.classList.add('active');
    if (roomView) { roomView.style.display = 'none'; roomView.classList.remove('active'); }
    if (lobbyView) { lobbyView.style.display = 'block'; lobbyView.classList.add('active'); }
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
  var lobbyView = document.getElementById('party-lobby-view');
  var roomView = document.getElementById('party-room-view');
  if (lobbyView) { lobbyView.style.display = 'none'; lobbyView.classList.remove('active'); }
  if (roomView) { roomView.style.display = 'block'; roomView.classList.add('active'); }

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
function openCreateRoomModal() {
  var modal = document.getElementById('modal-create-party-room');
  if (!modal) return;

  // 清空輸入框
  var gn = document.getElementById('input-party-gamename');
  var aid = document.getElementById('input-party-appid');
  var note = document.getElementById('input-party-note');
  if (gn) gn.value = '';
  if (aid) aid.value = '';
  if (note) note.value = '';

  // 載入本地已入庫遊戲下拉選單
  loadInstalledGamesDropdown();

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
}

function loadInstalledGamesDropdown() {
  var select = document.getElementById('select-party-installed-games');
  if (!select || !window.pywebview || !window.pywebview.api || !window.pywebview.api.get_installed_games_for_party) return;

  pywebview.api.get_installed_games_for_party().then(function(games) {
    var html = '<option value="">-- 手動輸入遊戲名稱與 AppID --</option>';
    if (Array.isArray(games) && games.length > 0) {
      games.forEach(function(g) {
        html += '<option value="' + g.appid + '" data-name="' + escapeHtml(g.name) + '">🎮 ' + escapeHtml(g.name) + ' (' + g.appid + ') · 已部署聯機補丁</option>';
      });
    } else {
      html += '<option value="" disabled>⚠️ 尚未檢測到已部署線上補丁的遊戲</option>';
    }
    select.innerHTML = html;
  });
}

function onSelectInstalledGameChange() {
  var select = document.getElementById('select-party-installed-games');
  var gn = document.getElementById('input-party-gamename');
  var aid = document.getElementById('input-party-appid');
  if (!select) return;

  var selectedOpt = select.options[select.selectedIndex];
  if (selectedOpt && selectedOpt.value) {
    if (aid) aid.value = selectedOpt.value;
    if (gn) gn.value = selectedOpt.getAttribute('data-name') || '';
  }
}

function submitCreatePartyRoom() {
  var gnInput = document.getElementById('input-party-gamename');
  var aidInput = document.getElementById('input-party-appid');
  var maxSelect = document.getElementById('select-party-max-players');
  var pubSelect = document.getElementById('select-party-is-public');
  var noteInput = document.getElementById('input-party-note');

  var gameName = (gnInput ? gnInput.value : '').trim();
  var appid = (aidInput ? aidInput.value : '').trim();
  var maxPlayers = parseInt(maxSelect ? maxSelect.value : 4, 10);
  var isPublic = (pubSelect ? pubSelect.value : '1') === '1';
  var note = (noteInput ? noteInput.value : '').trim();

  if (!gameName) {
    tt('請輸入遊戲名稱', 'warn');
    return;
  }

  tt('🌸 正在發布組隊房間…', 'info');

  pywebview.api.create_party_room(gameName, appid, maxPlayers, isPublic, note).then(function(res) {
    if (res && res.ok && res.room) {
      tt(res.msg || '成功建立房間！', 'ok');
      closeCreateRoomModal();
      _partyCurRoom = res.room;
      updateSidebarRoomInfo(res.room);
      switchPartyNav('room');
      schedulePartyPolling(3000);
    } else {
      tt(res && res.msg ? res.msg : '建立房間失敗', 'err');
    }
  }).catch(function(err) {
    tt('開房出錯: ' + err, 'err');
  });
}
