/**
 * 教學模組 2：遊戲入庫使用教學 (Game Library Addition Tutorial)
 * 職責：
 * 1. 引導切換至「遊戲入庫」搜尋分頁
 * 2. 模擬搜尋輸入框打字 (自動真實逐字鍵入 AppID 1245620)
 * 3. 模擬呈現搜尋結果卡片 (純前端沙盒假資料)
 * 4. 模擬點擊「一鍵入庫」並展示流暢入庫進度與成功狀態
 */

(function(window) {
  'use strict';

  var _savedOriginalSearchHTML = null;
  var _mockSearchBtnHandler = null;

  // 渲染示範遊戲搜尋結果卡片 (純前端沙盒，無真實網路請求)
  // 渲染示範遊戲搜尋結果卡片 (純前端沙盒，1:1 比照真實搜尋小卡樣式)
  function renderMockSearchResult() {
    var resEl = document.getElementById('results');
    if (!resEl) return;
    if (_savedOriginalSearchHTML === null) {
      _savedOriginalSearchHTML = resEl.innerHTML;
    }

    // 確保離開瀏覽網格模式，呈現真實搜尋結果的標準卡片排版
    resEl.classList.remove('browse-grid');

    resEl.innerHTML = `
      <div class="card" data-appid="1245620" id="tutorial-mock-game-card" style="width:100%;box-sizing:border-box">
        <img src="https://cdn.cloudflare.steamstatic.com/steam/apps/1245620/header.jpg" loading="lazy" onerror="this.src='https://cdn.cloudflare.steamstatic.com/steam/apps/1245620/capsule_231x87.jpg'">
        <div class="info">
          <div class="name" title="艾爾登法環 (ELDEN RING)">艾爾登法環 (ELDEN RING)</div>
          <div class="search-tags-row">
            <span class="aid">1245620</span>
            <span class="search-tag tag-ver" style="display:inline-flex">版本: 最新 (Manifest 就緒)</span>
            <span class="search-tag tag-of" style="display:inline-flex"><img src="assets/icons/gdrive.png" style="width:11px;height:11px;object-fit:contain;margin-right:3px"/>Google Drive</span>
            <span class="search-tag tag-dep" style="display:inline-flex">✅ 支援單人單機</span>
          </div>
          <div class="link-wrap">
            <span class="link link-steam" onclick="event.stopPropagation()">在 Steam 商店查看 ▶</span>
          </div>
        </div>
        <div class="search-action-wrap" id="sact-1245620">
          <button class="btn btn-p btn-s tutorial-btn-simulating" id="tutorial-mock-btn-install" style="font-weight:700;cursor:pointer">
            <span>⚡ 模擬入庫</span>
          </button>
        </div>
      </div>
    `;

    var btnInstall = document.getElementById('tutorial-mock-btn-install');
    if (btnInstall) {
      btnInstall.onclick = function(e) {
        if (e) e.stopPropagation();
        simulateMockInstallation();
      };
    }
  }

  // 模擬入庫進度展示
  function simulateMockInstallation() {
    var btn = document.getElementById('tutorial-mock-btn-install');
    if (!btn) return;

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> 正在解析 Manifest…';

    setTimeout(function() {
      btn.innerHTML = '<span class="spinner"></span> 正在部署 Lua 腳本…';
      setTimeout(function() {
        btn.innerHTML = '✅ 入庫成功！';
        btn.className = 'btn btn-s';
        btn.style.background = '#2EA043';
        btn.style.color = '#fff';
        btn.style.borderColor = '#2EA043';
        if (typeof tt === 'function') tt('🎉 《艾爾登法環》已成功完成示範入庫！', 'ok');

        // 標記完成並前進下一步
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.next();
        }, 800);
      }, 700);
    }, 600);
  }

  // 清理搜尋沙盒狀態 (僅在退出或全部結束時呼叫)
  function cleanupSearchSandbox() {
    var btnQ = document.getElementById('btn-q');
    if (btnQ) {
      if (_mockSearchBtnHandler) {
        btnQ.removeEventListener('click', _mockSearchBtnHandler, true);
        _mockSearchBtnHandler = null;
      }
      btnQ.disabled = false;
      btnQ.textContent = '搜尋';
    }
    var inputQ = document.getElementById('q');
    if (inputQ) {
      inputQ.value = '';
    }

    var mockCard = document.getElementById('tutorial-mock-game-card');
    if (mockCard) {
      mockCard.remove();
    }

    var resEl = document.getElementById('results');
    if (resEl) {
      if (typeof window.switchBrowse === 'function') {
        try {
          window.switchBrowse();
        } catch(e) {
          console.error('[Tutorial] switchBrowse error:', e);
        }
      } else if (_savedOriginalSearchHTML !== null) {
        resEl.innerHTML = _savedOriginalSearchHTML;
      } else {
        resEl.innerHTML = '<div class="empty"><div class="icon">🎮</div><p>搜尋 Steam 遊戲，一鍵入庫</p></div>';
      }
    }
    _savedOriginalSearchHTML = null;
  }

  var libraryAddModuleSteps = [
    {
      roleBadge: '🐺 獨狼玩家',
      moduleTitle: '單元 2：遊戲入庫使用教學',
      page: 'search',
      target: '.sidebar button[data-p="search"]',
      title: '前往遊戲入庫分頁',
      desc: '點擊左側「🔍 遊戲入庫」標籤，這裡支援全網海量 Steam 遊戲的快速檢索與一鍵秒速入庫。',
      placement: 'right'
    },
    {
      roleBadge: '🐺 獨狼玩家',
      moduleTitle: '單元 2：遊戲入庫使用教學',
      page: 'search',
      target: '#q',
      title: '模擬輸入遊戲 AppID',
      desc: '系統已自動為您在搜尋欄模擬真實輸入《艾爾登法環》的官方 AppID「1245620」。您平常亦可直接輸入遊戲中文或英文名稱。',
      placement: 'bottom',
      onEnter: function(inputEl) {
        var inp = document.getElementById('q');
        if (inp) {
          // 🌟 進入此步驟立即自動模擬打字機輸入，真實鍵入 1245620
          TutorialEngine.simulateTyping(inp, '1245620', { speed: 45 }, function() {
            if (window.TutorialEngine) window.TutorialEngine.reposition();
          });
        }
      },
      onBeforeNext: function() {
        var inp = document.getElementById('q');
        if (inp && inp.value !== '1245620') {
          inp.value = '1245620';
        }
      }
    },
    {
      roleBadge: '🐺 獨狼玩家',
      moduleTitle: '單元 2：遊戲入庫使用教學',
      page: 'search',
      target: '#btn-q',
      title: '點擊搜尋按鈕',
      desc: '點擊畫面中聚焦的「搜尋」按鈕，系統將秒級比對資源庫並呈現遊戲卡片。',
      disableNext: true,
      placement: 'bottom',
      onEnter: function(btn) {
        // 保證搜尋欄已有數值
        var inp = document.getElementById('q');
        if (inp && !inp.value) inp.value = '1245620';

        // 🌟 支援真實點擊 #btn-q 按鈕以觸發模擬搜尋
        if (btn) {
          _mockSearchBtnHandler = function(e) {
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
            renderMockSearchResult();
            setTimeout(function() {
              TutorialEngine.next();
            }, 250);
          };
          btn.addEventListener('click', _mockSearchBtnHandler, true);
        }
      },
      onBeforeNext: function() {
        // 進入下一步前保證卡片已在 DOM 裡
        renderMockSearchResult();
      },
      onLeave: function() {
        var btn = document.getElementById('btn-q');
        if (btn && _mockSearchBtnHandler) {
          btn.removeEventListener('click', _mockSearchBtnHandler, true);
          _mockSearchBtnHandler = null;
        }
      }
    },
    {
      roleBadge: '🐺 獨狼玩家',
      moduleTitle: '單元 2：遊戲入庫使用教學',
      page: 'search',
      target: function() {
        // 🌟 智慧目標守護：若尚未渲染則即刻渲染，絕對保證元素存在，不遺失退出！
        if (!document.getElementById('tutorial-mock-game-card')) {
          renderMockSearchResult();
        }
        return document.getElementById('tutorial-mock-game-card') || document.getElementById('results');
      },
      arrowTarget: '#tutorial-mock-btn-install',
      title: '搜尋結果與模擬入庫',
      desc: '搜尋結果卡片會列出遊戲封面、Manifest 清單與單機支援度。直接點擊上方卡片右側的【⚡ 模擬入庫】體驗自動部署流程！',
      disableNext: true,
      placement: 'bottom-right',
      onEnter: function() {
        if (!document.getElementById('tutorial-mock-game-card')) {
          renderMockSearchResult();
        }
        setTimeout(function() {
          TutorialEngine.reposition();
        }, 120);
      }
    }
  ];

  if (window.TutorialEngine) {
    window.TutorialEngine.registerModule('game_library_add', {
      name: '遊戲入庫使用教學',
      steps: libraryAddModuleSteps,
      cleanup: cleanupSearchSandbox
    });
  }
})(window);
