/**
 * 教學模組：群眾領導 - 單元 1：小卡標籤解讀與線上補丁說明 (Leader Tags & Online Patch Tutorial)
 * 職責：
 * 1. 引導玩家切換至「遊戲入庫」，搜尋欄真實對應示範遊戲 AppID「1245620」
 * 2. 採用原本搜尋方法的標準版面呈現示範小卡，完整解讀各項標籤（Online-Fix、已部署、ZeiGames、Google Drive 等）
 * 3. 深入說明「線上補丁」的原理與多人同樂用途
 */

(function(window) {
  'use strict';

  var _savedOriginalSearchHTML = null;
  var _savedBrowseInfoDisplay = null;
  var _savedLoadMoreDisplay = null;

  // 標籤高亮動態呼吸動畫輔助函式 (支援多標籤同時呼吸)
  function focusTags(tagIds) {
    clearFocusTags();
    if (!tagIds) return;
    if (!Array.isArray(tagIds)) tagIds = [tagIds];
    tagIds.forEach(function(id) {
      var el = document.getElementById(id);
      if (el) {
        el.classList.add('tutorial-focus-pulse');
      }
    });
  }

  function focusTag(tagId) {
    focusTags(tagId);
  }

  function clearFocusTags() {
    var elements = document.querySelectorAll('.tutorial-focus-pulse');
    for (var i = 0; i < elements.length; i++) {
      elements[i].classList.remove('tutorial-focus-pulse');
    }
  }

  // 確保示範卡片在視窗舒適視野頂部（使下方留有 320px 以上極致開闊空間）
  function scrollMockCardIntoComfortView() {
    var pages = document.querySelector('.pages');
    var mockCard = document.getElementById('tutorial-leader-mock-card');
    if (!pages || !mockCard) return;
    var cRect = mockCard.getBoundingClientRect();
    if (cRect.top > 130) {
      pages.scrollTop = Math.max(0, pages.scrollTop + (cRect.top - 105));
    }
  }

  // 注入示範遊戲小卡（比照原本搜尋方法的標準卡片版面呈現，搜尋欄對應 1245620）
  function injectMockLeaderCard() {
    // 1. 搜尋輸入框對應示範小卡的 AppID「1245620」
    var inputQ = document.getElementById('q');
    if (inputQ) {
      inputQ.value = '1245620';
    }

    // 2. 隱藏瀏覽全部相關提示，進入標準搜尋呈現模式
    var binfo = document.getElementById('browse-info');
    if (binfo) {
      if (_savedBrowseInfoDisplay === null) {
        _savedBrowseInfoDisplay = binfo.style.display;
      }
      binfo.style.display = 'none';
    }
    var lm = document.getElementById('load-more-wrap');
    if (lm) {
      if (_savedLoadMoreDisplay === null) {
        _savedLoadMoreDisplay = lm.style.display;
      }
      lm.style.display = 'none';
    }

    var resEl = document.getElementById('results');
    if (!resEl) return;
    if (_savedOriginalSearchHTML === null) {
      _savedOriginalSearchHTML = resEl.innerHTML;
    }

    resEl.classList.remove('browse-grid');
    resEl.innerHTML = `
      <div class="card has-onlinefix" data-appid="1245620" id="tutorial-leader-mock-card">
        <img src="https://cdn.cloudflare.steamstatic.com/steam/apps/1245620/header.jpg" loading="lazy" onerror="this.src='https://cdn.cloudflare.steamstatic.com/steam/apps/1245620/capsule_231x87.jpg'" onload="if(window.TutorialEngine) window.TutorialEngine.reposition()">
        <div class="info">
          <div class="name" title="艾爾登法環 (ELDEN RING)">艾爾登法環 (ELDEN RING)</div>
          <div class="search-tags-row" id="tut-leader-tags-row" style="display:inline-flex;width:fit-content;max-width:max-content;align-items:center;gap:6px;flex-wrap:nowrap;overflow:visible">
            <span class="aid">1245620</span>
            <span class="search-tag tag-ver">📅 版本：最新</span>
            <span class="search-tag tag-gdrive" id="tut-tag-gdrive" style="display:inline-flex" title="Google Drive 網盤補丁庫已收錄補丁檔案"><img src="assets/icons/gdrive.png" class="corner-tag-img" alt="GD"/>Google Drive</span>
            <span id="tut-source-tags-wrap" style="display:inline-flex;align-items:center;gap:6px">
              <span class="search-tag tag-of" id="tut-tag-of" style="display:inline-flex" title="Online-Fix 官方網站已收錄聯機補丁"><img src="assets/icons/onlinefix.png" class="corner-tag-img" alt="OF"/>Online-Fix</span>
              <span class="search-tag tag-zg" id="tut-tag-zg" style="display:inline-flex" title="ZeiGames 官方網站已收錄專用補丁"><img src="assets/icons/zeigames.png" class="corner-tag-img" alt="ZG"/>ZeiGames</span>
            </span>
            <span class="search-tag tag-dep" id="tut-tag-dep" style="display:inline-flex" title="本地已成功部署補丁">✅ 已部署</span>
          </div>
          <div class="link-wrap">
            <span class="link link-steam" onclick="event.stopPropagation()">在 Steam 商店查看 ▶</span>
          </div>
        </div>
        <div class="search-action-wrap" id="tut-leader-act-wrap">
          <button class="btn btn-o btn-s" style="color:var(--succ);border-color:var(--succ);cursor:default" onclick="event.stopPropagation()">
            ✅ 已在本地
          </button>
        </div>
      </div>
      <div id="tutorial-leader-tags-spacer" style="height:320px;width:100%;"></div>
    `;
  }

  function cleanupLeaderTagsSandbox() {
    clearFocusTags();
    var inputQ = document.getElementById('q');
    if (inputQ && inputQ.value === '1245620') {
      inputQ.value = '';
    }
    var resEl = document.getElementById('results');
    var mockCard = document.getElementById('tutorial-leader-mock-card');
    if (mockCard) {
      mockCard.remove();
    }
    var spacer = document.getElementById('tutorial-leader-tags-spacer');
    if (spacer) {
      spacer.remove();
    }
    if (resEl && _savedOriginalSearchHTML !== null) {
      resEl.innerHTML = _savedOriginalSearchHTML;
      _savedOriginalSearchHTML = null;
    }
    var binfo = document.getElementById('browse-info');
    if (binfo && _savedBrowseInfoDisplay !== null) {
      binfo.style.display = _savedBrowseInfoDisplay;
      _savedBrowseInfoDisplay = null;
    }
    var lm = document.getElementById('load-more-wrap');
    if (lm && _savedLoadMoreDisplay !== null) {
      lm.style.display = _savedLoadMoreDisplay;
      _savedLoadMoreDisplay = null;
    }
  }

  var leaderTagsSteps = [
    // 步驟 1：導航至遊戲入庫與示範小卡 (高亮遊戲小卡，向下停靠，箭頭向上精準指向標籤列)
    {
      role: 'leader',
      roleBadge: '🚀 線上補丁',
      moduleTitle: '單元 1：小卡標籤與線上補丁說明',
      title: '連線號召起點：遊戲搜尋與標籤辨識',
      page: 'search',
      width: 440,
      placement: 'bottom',
      forcePlacement: true,
      desc: '在發起連線活動前，您需要透過遊戲小卡的<strong>專屬標籤</strong>，精準掌握遊戲是否支援聯機與補丁收錄情況。',
      target: function() {
        if (window.switchPage) window.switchPage('search');
        injectMockLeaderCard();
        return document.getElementById('tutorial-leader-mock-card');
      },
      secondaryTarget: function() {
        return document.getElementById('tut-leader-tags-row');
      },
      arrowTarget: function() {
        return document.getElementById('tut-leader-tags-row');
      },
      padding: 6,
      borderRadius: 12,
      secondaryPadding: 4,
      secondaryBorderRadius: 8,
      onEnter: function() {
        if (window.switchPage) window.switchPage('search');
        injectMockLeaderCard();
        scrollMockCardIntoComfortView();
        focusTag('tut-leader-tags-row');
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 100);
      },
      onLeave: function() {
        clearFocusTags();
      },
      hint: '點擊下一步，我們將為您逐一解構小卡上的各項標籤！'
    },

    // 步驟 2：線上補丁來源網域：Online-Fix 與 ZeiGames (高亮遊戲小卡，向下停靠，箭頭向上精準指向 OF 與 ZG 標籤群組)
    {
      role: 'leader',
      roleBadge: '🚀 線上補丁',
      moduleTitle: '單元 1：小卡標籤與線上補丁說明',
      title: '線上補丁來源網域：Online-Fix 與 ZeiGames',
      page: 'search',
      width: 440,
      placement: 'bottom',
      forcePlacement: true,
      desc: '<strong>線上補丁的來源網域：Online-Fix 與 ZeiGames</strong><br>' +
            '在網路社群中，高品質的線上聯機補丁主要來自這兩個專屬網站：<br>' +
            '• <strong style="color:#00B0FF">Online-Fix.me</strong>：全球最知名的 Steam 聯機補丁發布站，支援龐大多人同樂遊戲。<br>' +
            '• <strong style="color:#E91E63">ZeiGames</strong>：提供豐富熱門遊戲的專用連線補丁資源。<br>' +
            '當小卡點亮這兩枚標籤時，代表對應網域已收錄該遊戲的線上補丁！',
      target: function() {
        if (window.switchPage) window.switchPage('search');
        injectMockLeaderCard();
        return document.getElementById('tutorial-leader-mock-card');
      },
      secondaryTarget: function() {
        return document.getElementById('tut-source-tags-wrap');
      },
      arrowTarget: function() {
        return document.getElementById('tut-source-tags-wrap');
      },
      padding: 6,
      borderRadius: 12,
      secondaryPadding: 4,
      secondaryBorderRadius: 8,
      onEnter: function() {
        if (window.switchPage) window.switchPage('search');
        injectMockLeaderCard();
        scrollMockCardIntoComfortView();
        focusTags(['tut-tag-of', 'tut-tag-zg']);
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 100);
      },
      onLeave: function() {
        clearFocusTags();
      },
      hint: 'Online-Fix 與 ZeiGames 是線上補丁的兩大主要來源網域！'
    },

    // 步驟 3：補丁雲端倉庫：Google Drive 協同機制 (高亮遊戲小卡，向下停靠，箭頭向上精準指向 Google Drive 標籤)
    {
      role: 'leader',
      roleBadge: '🚀 線上補丁',
      moduleTitle: '單元 1：小卡標籤與線上補丁說明',
      title: '雲端協作倉庫：為什麼需要 Google Drive？',
      page: 'search',
      width: 440,
      placement: 'bottom',
      forcePlacement: true,
      desc: '<strong>為什麼需要 Google Drive 雲端網盤？它如何與線上補丁協作？</strong><br>' +
            '雖然補丁來自 Online-Fix 或 ZeiGames，但官方載點常有速度限制或繁複驗證。因此 SMU 採用<strong>「Google Drive 雲端硬碟協同架構」</strong>：<br>' +
            '• <strong>個人與好友共享庫</strong>：您或群友只要將下載好的補丁壓縮檔直接存入 Google Drive。<br>' +
            '• <strong>智慧秒級比對關聯</strong>：SMU 會即時索引您的雲端硬碟。當點亮 <strong style="color:#34A853">Google Drive</strong> 標籤時，代表軟體可直接一鍵極速抓取補丁，免手動下載搬移！',
      target: function() {
        if (window.switchPage) window.switchPage('search');
        injectMockLeaderCard();
        return document.getElementById('tutorial-leader-mock-card');
      },
      secondaryTarget: function() {
        return document.getElementById('tut-tag-gdrive');
      },
      arrowTarget: function() {
        return document.getElementById('tut-tag-gdrive');
      },
      padding: 6,
      borderRadius: 12,
      secondaryPadding: 4,
      secondaryBorderRadius: 8,
      onEnter: function() {
        if (window.switchPage) window.switchPage('search');
        injectMockLeaderCard();
        scrollMockCardIntoComfortView();
        focusTags('tut-tag-gdrive');
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 100);
      },
      onLeave: function() {
        clearFocusTags();
      },
      hint: '只要點亮 Google Drive 標籤，就代表團隊網盤已有現成資源，可一鍵極速抓取！'
    },

    // 步驟 4：關鍵狀態指標：已部署 (高亮遊戲小卡，向下停靠，箭頭向上精準指向 已部署 標籤)
    {
      role: 'leader',
      roleBadge: '🚀 線上補丁',
      moduleTitle: '單元 1：小卡標籤與線上補丁說明',
      title: '關鍵狀態指標：✅ 已部署',
      page: 'search',
      width: 440,
      placement: 'bottom',
      forcePlacement: true,
      desc: '<strong>掌握遊戲連線狀態的關鍵指標：<strong style="color:#10B981">✅ 已部署</strong></strong><br>' +
            '當遊戲小卡顯示「✅ 已部署」標籤時，代表：<br>' +
            '• <strong>本地補丁置入成功</strong>：線上補丁的連線核心檔案已成功注入該遊戲的安裝目錄中。<br>' +
            '• <strong>隨時準備就緒</strong>：您與好友現在可以直接啟動遊戲，進入 Steam 多人伺服器開房邀請同樂！<br>' +
            '這是判斷遊戲當前是否具備聯機能力的最直觀標記。',
      target: function() {
        if (window.switchPage) window.switchPage('search');
        injectMockLeaderCard();
        return document.getElementById('tutorial-leader-mock-card');
      },
      secondaryTarget: function() {
        return document.getElementById('tut-tag-dep');
      },
      arrowTarget: function() {
        return document.getElementById('tut-tag-dep');
      },
      padding: 6,
      borderRadius: 12,
      secondaryPadding: 4,
      secondaryBorderRadius: 8,
      onEnter: function() {
        if (window.switchPage) window.switchPage('search');
        injectMockLeaderCard();
        scrollMockCardIntoComfortView();
        focusTags('tut-tag-dep');
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 100);
      },
      onLeave: function() {
        clearFocusTags();
      },
      hint: '恭喜您掌握了小卡標籤的核心意義！下一步我們將學習如何建立專屬 Google Drive 網盤！'
    }
  ];

  if (window.TutorialEngine) {
    window.TutorialEngine.registerModule('leader_tags_patch', {
      title: '小卡標籤與線上補丁說明',
      steps: leaderTagsSteps,
      cleanup: cleanupLeaderTagsSandbox
    });
  }

  window.injectMockLeaderCard = injectMockLeaderCard;
  window.cleanupLeaderTagsSandbox = cleanupLeaderTagsSandbox;
})(window);
