/**
 * 教學模組：群眾領導 - 單元 3：網盤資源入庫與補丁管理 (Leader Deploy & Patch Management Tutorial)
 * 職責：
 * 1. 示範透過 Google Drive 標籤極速下載與入庫（精準指向小卡上的 Google Drive 標籤）
 * 2. 示範在「管理入庫」中檢視已部署補丁小卡與點開 "..." 選單
 * 3. 展現群眾領導者專屬結業慶祝彈窗（比照獨狼玩家圖三規格）
 */

(function(window) {
  'use strict';

  var _savedOriginalManageHTML = null;

  function injectMockLeaderManageItem() {
    var glist = document.getElementById('glist');
    if (!glist) return;
    if (_savedOriginalManageHTML === null) {
      _savedOriginalManageHTML = glist.innerHTML;
    }

    // 啟用列表模式使卡片呈現標準橫向列表版面
    glist.classList.add('list');

    glist.innerHTML = `
      <div class="card has-onlinefix" data-appid="1245620" id="tutorial-leader-manage-mock" style="--i:0">
        <img src="https://cdn.cloudflare.steamstatic.com/steam/apps/1245620/header.jpg" loading="lazy" onerror="this.src='https://cdn.cloudflare.steamstatic.com/steam/apps/1245620/capsule_231x87.jpg'">
        <div class="info">
          <div class="name" title="艾爾登法環 (ELDEN RING)">艾爾登法環 (ELDEN RING)</div>
          <div class="search-tags-row">
            <span class="aid">1245620</span>
            <span class="search-tag tag-ver">📅 版本：最新</span>
            <span class="search-tag tag-gdrive" title="Google Drive 網盤補丁庫已收錄補丁檔案"><img src="assets/icons/gdrive.png" class="corner-tag-img" alt="GD"/>Google Drive</span>
            <span class="search-tag tag-dep" id="tut-manage-tag-dep" title="本地已成功部署補丁">✅ 已部署</span>
          </div>
          <div class="link-wrap">
            <span class="link link-steam" onclick="event.stopPropagation()">在 Steam 商店查看 ▶</span>
          </div>
        </div>
        <div class="search-action-wrap">
          <button class="card-menu" id="tut-leader-btn-menu" title="更多選項" onclick="event.stopPropagation()">
            <svg viewBox="0 0 16 16" width="13" height="13" fill="currentColor"><circle cx="2.5" cy="8" r="1.5"/><circle cx="8" cy="8" r="1.5"/><circle cx="13.5" cy="8" r="1.5"/></svg>
          </button>
          <div class="card-dd show" id="tut-leader-card-dd" onclick="event.stopPropagation()" style="max-height:none!important;overflow:visible!important">
            <button style="color:#00bcd4;font-weight:700" id="tut-menu-install-patch">🚀 安裝線上補丁</button>
            <button style="color:var(--err);font-weight:700" id="tut-menu-remove-patch">🗑️ 移除線上補丁</button>
            <button>📝 編輯 Lua</button>
            <button>🔒 固定版本</button>
            <button>📦 查看 DLC</button>
            <button style="color:#4caf50;font-weight:600" id="tut-menu-inspect-drive">🌐 檢視網盤狀況</button>
            <button>🗑 刪除</button>
          </div>
        </div>
      </div>
    `;

    var mc = document.getElementById('mc');
    if (mc) {
      mc.textContent = '（共 1 款示範遊戲）';
    }
  }

  function cleanupLeaderDeploySandbox() {
    var glist = document.getElementById('glist');
    var mockCard = document.getElementById('tutorial-leader-manage-mock');
    if (mockCard) {
      mockCard.remove();
    }
    if (glist && _savedOriginalManageHTML !== null) {
      glist.innerHTML = _savedOriginalManageHTML;
      _savedOriginalManageHTML = null;
    }
    // 恢復使用者偏好的檢視模式
    if (typeof window.toggleView === 'function') {
      try {
        var savedMode = localStorage.getItem('view-mode') || 'grid';
        window.toggleView(savedMode);
      } catch(e){}
    }
    // 🌟 注意：結業慶祝彈窗不在此提前銷毀，由玩家主動點擊按鈕後關閉
    if (typeof window.rg === 'function') {
      try { window.rg(true); } catch(e){}
    }
  }

  // 線上補丁專屬結業慶祝彈窗（1:1 比照獨狼玩家圖三樣式）
  function showLeaderCompletionModal() {
    var modal = document.createElement('div');
    modal.className = 'tutorial-sandbox-modal-wrap tutorial-completion-modal-wrap';
    modal.id = 'tutorial-leader-complete-modal';
    modal.innerHTML = `
      <div class="tutorial-sandbox-modal-card tutorial-completion-modal-card" style="text-align:center;padding:28px 24px">
        <div style="font-size:46px;margin-bottom:8px">🚀🎉</div>
        <h2 class="tutorial-completion-title" style="margin:0 0 10px 0;font-size:20px;font-weight:900">線上補丁教學 圓滿完成！</h2>
        <p class="tutorial-completion-desc" style="font-size:13px;line-height:1.65;margin:0 0 20px 0">
          太棒了！您已經完整掌握了<strong>「小卡標籤辨識」</strong>、<strong>「Google Drive 網盤配置」</strong>以及<strong>「線上補丁極速入庫與管理」</strong>的全部核心操作。<br>
          現在，您可以打造屬於您與好友專屬的連線雲端庫，隨時吹響開房號角，享受暢快無阻的聯機同樂體驗！
        </p>
        <div style="display:flex;justify-content:center;gap:12px">
          <button class="btn btn-o btn-s" id="btn-leader-finish-back">🎓 返回教學首頁</button>
          <button class="btn btn-p btn-s" id="btn-leader-finish-explore" style="font-weight:700">🔍 開始探索入庫</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    modal.style.display = 'flex';

    var btnBack = document.getElementById('btn-leader-finish-back');
    var btnExplore = document.getElementById('btn-leader-finish-explore');

    if (btnBack) {
      btnBack.onclick = function() {
        modal.remove();
        cleanupLeaderDeploySandbox();
        if (typeof window.cleanupAllTutorialSandbox === 'function') {
          window.cleanupAllTutorialSandbox();
        }
        if (window.switchPage) window.switchPage('tutorial');
      };
    }

    if (btnExplore) {
      btnExplore.onclick = function() {
        modal.remove();
        cleanupLeaderDeploySandbox();
        if (typeof window.cleanupAllTutorialSandbox === 'function') {
          window.cleanupAllTutorialSandbox();
        }
        if (window.switchPage) window.switchPage('search');
      };
    }
  }

  var leaderDeploySteps = [
    // 步驟 1 (整體步驟 10)：透過 Google Drive 資源入庫遊戲 (高亮遊戲小卡，向下停靠，箭頭向上指向 Google Drive 標籤)
    {
      role: 'leader',
      roleBadge: '🚀 線上補丁',
      moduleTitle: '單元 3：線上補丁安裝與移除教學',
      title: '透過 Google Drive 儲存的資源入庫遊戲',
      page: 'search',
      width: 440,
      desc: '當您設定好 Google Drive 網盤後：<br>' +
            '1. 在<strong>「🔍 遊戲入庫」</strong>搜尋該遊戲，小卡會自動點亮 <strong style="color:#34A853">Google Drive</strong> 標籤。<br>' +
            '2. 點擊<strong>「一鍵入庫」</strong>，軟體便會直接從您的 Google Drive <strong>滿速下載補丁壓縮檔</strong>。<br>' +
            '3. 下載完成後，軟體將自動解壓縮並<strong>精準部署至遊戲目錄</strong>，完成入庫！',
      target: function() {
        if (window.switchPage) window.switchPage('search');
        var pagesEl = document.querySelector('.pages');
        if (pagesEl) pagesEl.scrollTop = 0;
        if (typeof window.injectMockLeaderCard === 'function') {
          window.injectMockLeaderCard();
        }
        return document.getElementById('tutorial-leader-mock-card');
      },
      secondaryTarget: function() {
        return document.getElementById('tut-tag-gdrive');
      },
      arrowTarget: function() {
        return document.getElementById('tut-tag-gdrive');
      },
      placement: 'bottom',
      padding: 6,
      borderRadius: 12,
      secondaryPadding: 4,
      secondaryBorderRadius: 8,
      onEnter: function() {
        var pagesEl = document.querySelector('.pages');
        if (pagesEl) pagesEl.scrollTop = 0;
        if (window.switchPage) window.switchPage('search');
        if (typeof window.injectMockLeaderCard === 'function') {
          window.injectMockLeaderCard();
        }
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 120);
      },
      hint: '下一步，我們將前往「管理入庫」學習如何管理與移除補丁！'
    },

    // 步驟 2 (整體步驟 11)：切換至管理入庫檢視已部署補丁與選單 (支援卡片與下拉選單多邊形高亮 + 完整呈現選單，向左避讓完全不遮擋)
    {
      role: 'leader',
      roleBadge: '🚀 線上補丁',
      moduleTitle: '單元 3：線上補丁安裝與移除教學',
      title: '檢視已部署補丁與 "..." 功能按鈕',
      page: 'manage',
      width: 380,
      offsetX: -10,
      desc: '進入<strong>「📋 管理入庫」</strong>頁面：<br>' +
            '成功置入補丁的遊戲會標註 <strong style="color:#10B981">✅ 已部署</strong>。<br>' +
            '每張卡片右側都保留了<strong>「...」更多選項按鈕</strong>，點擊即可開啟強大的進階功能選單！',
      target: function() {
        if (window.switchPage) window.switchPage('manage');
        var pagesEl = document.querySelector('.pages');
        if (pagesEl) pagesEl.scrollTop = 0;
        injectMockLeaderManageItem();
        return document.getElementById('tutorial-leader-manage-mock');
      },
      secondaryTarget: function() {
        return document.getElementById('tut-leader-card-dd');
      },
      secondaryPadding: 6,
      secondaryBorderRadius: 10,
      thirdTarget: function() {
        return document.getElementById('tut-leader-btn-menu');
      },
      thirdPadding: 4,
      thirdBorderRadius: 6,
      arrowTarget: function() {
        return document.getElementById('tut-leader-btn-menu');
      },
      placement: 'left',
      padding: 6,
      borderRadius: 12,
      onEnter: function() {
        var pagesEl = document.querySelector('.pages');
        if (pagesEl) pagesEl.scrollTop = 0;
        if (window.switchPage) window.switchPage('manage');
        injectMockLeaderManageItem();
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 120);
      },
      hint: '點擊下一步，即可圓滿完成群眾領導者教學！'
    },

    // 步驟 3 (整體步驟 12)：線上補丁教學結業
    {
      role: 'leader',
      roleBadge: '🚀 線上補丁',
      moduleTitle: '單元 3：線上補丁安裝與移除教學',
      title: '恭喜！您已掌握全方位「線上補丁」管理',
      desc: '太厲害了！從<strong>小卡標籤解讀</strong>、<strong>Google Drive 網盤架設</strong>到<strong>線上補丁極速入庫</strong>，您已經具備了帶領隊友連線同樂的所有必備本領！<br>' +
            '現在就開啟您的連線大冒險吧！🚀',
      target: function() {
        return document.getElementById('tutorial-leader-manage-mock') || document.body;
      },
      placement: 'bottom',
      nextText: '完成教學 🎉',
      onBeforeNext: function() {
        showLeaderCompletionModal();
      }
    }
  ];

  if (window.TutorialEngine) {
    window.TutorialEngine.registerModule('leader_deploy_manage', {
      title: '線上補丁安裝與移除教學',
      steps: leaderDeploySteps,
      cleanup: cleanupLeaderDeploySandbox
    });
  }

  window.cleanupLeaderDeploySandbox = cleanupLeaderDeploySandbox;
})(window);
