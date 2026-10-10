/**
 * 教學模組 3：管理入庫使用說明 (Manage Library Usage Tutorial)
 * 職責：
 * 1. 引導切換至「管理入庫」分頁
 * 2. 呈現沙盒示範已入庫清單項目 (艾爾登法環)
 * 3. 解說遊戲版本比對、檢查更新與排序功能
 * 4. 結業慶祝與引導玩家開始真實暢玩
 */

(function(window) {
  'use strict';

  var _savedOriginalManageHTML = null;

  // 注入示範入庫遊戲卡片 (1:1 呈現管理入庫真實發生的標準網格小卡架構)
  function injectMockManageItem() {
    var glist = document.getElementById('glist');
    if (!glist) return;
    if (_savedOriginalManageHTML === null) {
      _savedOriginalManageHTML = glist.innerHTML;
    }

    // 確保 glist 處於標準網格模式（移除 list 類名）
    glist.classList.remove('list');

    // 示範管理卡片（比照 manage.js 中 renderGames 標準網格卡片 DOM 結構）
    glist.innerHTML = `
      <div class="card" data-appid="1245620" id="tutorial-mock-manage-item" style="--i:0">
        <div class="name" title="艾爾登法環 (ELDEN RING)">艾爾登法環 (ELDEN RING)</div>
        <img src="https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1245620/header.jpg" loading="lazy" onerror="this.src='https://cdn.cloudflare.steamstatic.com/steam/apps/1245620/capsule_231x87.jpg'">
        <button class="card-menu" title="更多選項" onclick="event.stopPropagation()">
          <svg viewBox="0 0 16 16" width="13" height="13" fill="currentColor">
            <circle cx="2.5" cy="8" r="1.5"/><circle cx="8" cy="8" r="1.5"/><circle cx="13.5" cy="8" r="1.5"/>
          </svg>
        </button>
        <div class="card-dd" onclick="event.stopPropagation()">
          <button onclick="event.stopPropagation()">📝 編輯 Lua</button>
          <button class="vfbtn" onclick="event.stopPropagation()">固定版本</button>
          <button onclick="event.stopPropagation()">📦 查看 DLC</button>
          <button onclick="event.stopPropagation()">🌐 檢視網盤狀況</button>
          <button onclick="event.stopPropagation()">🗑 刪除</button>
        </div>
        <div class="aid" title="1245620">
          <span class="aid-num">1245620</span>
        </div>
      </div>
    `;

    var mc = document.getElementById('mc');
    if (mc) {
      mc.textContent = '（共 1 款示範遊戲）';
    }
  }

  function cleanupManageSandbox() {
    var glist = document.getElementById('glist');
    var mockCard = document.getElementById('tutorial-mock-manage-item');
    if (mockCard) {
      mockCard.remove();
    }
    if (glist && _savedOriginalManageHTML !== null) {
      glist.innerHTML = _savedOriginalManageHTML;
      _savedOriginalManageHTML = null;
    }
    if (typeof window.rg === 'function') {
      try { window.rg(true); } catch(e){}
    }
    if (typeof window.updateManageQuota === 'function') {
      try { window.updateManageQuota(); } catch(e){}
    }
  }

  // 結業慶祝彈窗
  function showSoloCompletionModal() {
    var modal = document.createElement('div');
    modal.className = 'tutorial-sandbox-modal-wrap tutorial-completion-modal-wrap';
    modal.id = 'tutorial-solo-complete-modal';
    modal.innerHTML = `
      <div class="tutorial-sandbox-modal-card tutorial-completion-modal-card" style="text-align:center;padding:28px 24px">
        <div style="font-size:46px;margin-bottom:8px">🐺🎉</div>
        <h2 class="tutorial-completion-title" style="margin:0 0 10px 0;font-size:20px;font-weight:900">獨狼玩家教學 圓滿完成！</h2>
        <p class="tutorial-completion-desc" style="font-size:13px;line-height:1.65;margin:0 0 20px 0">
          太棒了！您已經完整掌握了<strong>「憑證綁定」</strong>、<strong>「遊戲秒速入庫」</strong>以及<strong>「管理入庫與版本更新」</strong>的全部核心操作。<br>
          現在，您可以隨心所欲搜尋喜愛的單機神作，享受流暢無拘的遊戲體驗！
        </p>
        <div style="display:flex;justify-content:center;gap:12px">
          <button class="btn btn-o btn-s" id="btn-solo-finish-back">🎓 返回教學首頁</button>
          <button class="btn btn-p btn-s" id="btn-solo-finish-explore" style="font-weight:700">🔍 開始探索入庫</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    modal.style.display = 'flex';

    var btnBack = document.getElementById('btn-solo-finish-back');
    var btnExplore = document.getElementById('btn-solo-finish-explore');

    if (btnBack) {
      btnBack.onclick = function() {
        modal.remove();
        if (typeof window.cleanupAllTutorialSandbox === 'function') {
          window.cleanupAllTutorialSandbox();
        } else {
          cleanupManageSandbox();
        }
        if (window.switchPage) window.switchPage('tutorial');
      };
    }

    if (btnExplore) {
      btnExplore.onclick = function() {
        modal.remove();
        if (typeof window.cleanupAllTutorialSandbox === 'function') {
          window.cleanupAllTutorialSandbox();
        } else {
          cleanupManageSandbox();
        }
        if (window.switchPage) window.switchPage('search');
      };
    }
  }

  var manageUsageModuleSteps = [
    {
      roleBadge: '🐺 獨狼玩家',
      moduleTitle: '單元 3：管理入庫使用說明',
      page: 'manage',
      target: '.sidebar button[data-p="manage"]',
      title: '前往管理入庫分頁',
      desc: '點擊左側「📋 管理入庫」標籤，您可以在此檢視本機已部署與入庫的所有遊戲，掌握版本狀態與檔案路徑。',
      placement: 'right'
    },
    {
      roleBadge: '🐺 獨狼玩家',
      moduleTitle: '單元 3：管理入庫使用說明',
      page: 'manage',
      target: function() {
        if (!document.getElementById('tutorial-mock-manage-item')) {
          injectMockManageItem();
        }
        return document.getElementById('tutorial-mock-manage-item') || document.getElementById('glist');
      },
      title: '檢視已入庫遊戲項目',
      desc: '此處列出了剛才示範入庫的《艾爾登法環》。卡片上清楚顯示版本最新度、Manifest 注入狀態，並支援一鍵開啟遊戲資料夾或快速啟動！',
      onEnter: function() {
        if (!document.getElementById('tutorial-mock-manage-item')) {
          injectMockManageItem();
        }
        setTimeout(function() {
          TutorialEngine.reposition();
        }, 120);
      },
      padding: 6,
      borderRadius: 14,
      placement: 'bottom'
    },
    {
      roleBadge: '🐺 獨狼玩家',
      moduleTitle: '單元 3：管理入庫使用說明',
      page: 'manage',
      target: '#p-manage button[onclick="rg(true);"]',
      title: '檢查更新與一鍵比對',
      desc: '當 Steam 官方遊戲有版本釋出時，點擊「🔄 檢查更新」即可自動聯機比對最新 Manifest 清單並進行增量補丁修復，確保您的存檔與遊戲無縫相容！',
      hint: '亦可使用旁邊的排序模式快速篩選需要更新的遊戲。',
      placement: 'bottom'
    },
    {
      roleBadge: '🐺 獨狼玩家',
      moduleTitle: '單元 3：管理入庫使用說明',
      page: 'manage',
      target: '#p-manage select#manage-sort-mode',
      title: '排序與檢視模式切換',
      desc: '您可以自由選擇「可更新優先」、「田 網格」或「📄 列表」模式，打造最符合您直覺的遊戲庫管理面板。',
      nextText: '完成教學 🎉',
      onBeforeNext: function() {
        showSoloCompletionModal();
      },
      placement: 'bottom'
    }
  ];

  if (window.TutorialEngine) {
    window.TutorialEngine.registerModule('manage_library_usage', {
      name: '管理入庫使用說明',
      steps: manageUsageModuleSteps,
      cleanup: cleanupManageSandbox
    });
  }
})(window);
