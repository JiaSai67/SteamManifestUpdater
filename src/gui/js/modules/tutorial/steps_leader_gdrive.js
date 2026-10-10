/**
 * 教學模組：群眾領導 - 單元 2：Google Drive 網盤配置教學 (Leader Google Drive Setup Tutorial)
 * 職責：
 * 1. 步驟 5：高亮左側設定選項，繪製平滑流光導航箭頭指向頂部「🌐 網盤」分頁
 * 2. 步驟 6：左右雙欄架構，左側 2.5s 停留 + 0.5s 漸隱漸現輪播三大動作，右側常駐 Google Drive 設定介紹組件
 * 3. 步驟 7：說明補丁檔案放置規範（黃色醒目標記）
 * 4. 步驟 8：指向「➕ 新增 Google Drive 網盤」，執行沙盒模擬打字輸入
 */

(function(window) {
  'use strict';

  var _savedOriginalGDriveList = null;
  var _mockDriveInserted = false;
  var _carouselTimer = null;

  function ensureSettingsAdvTab() {
    if (window.switchPage) window.switchPage('settings');
    if (typeof window.switchSettingsTab === 'function') {
      window.switchSettingsTab('adv');
    } else {
      var btnAdv = document.getElementById('btn-stab-adv');
      if (btnAdv) btnAdv.click();
    }
  }

  // 儲存原始網盤設定資料快照
  function backupGDriveData() {
    if (_savedOriginalGDriveList === null && window._gdriveDrives) {
      _savedOriginalGDriveList = JSON.parse(JSON.stringify(window._gdriveDrives));
    }
  }

  // 繪製從左側設定選項指向頂部網盤分頁的動態箭頭
  function drawGuideArrowFromSettingsToGDrive() {
    removeGuideArrow();
    var btnSettings = document.querySelector('.sidebar button[data-p="settings"]');
    var btnAdv = document.getElementById('btn-stab-adv');
    if (!btnSettings || !btnAdv) return;

    var r1 = btnSettings.getBoundingClientRect();
    var r2 = btnAdv.getBoundingClientRect();

    var x1 = r1.right + 6;
    var y1 = r1.top + r1.height / 2;
    var x2 = r2.left - 6; // 朝網盤按鈕左側平滑注入
    var y2 = r2.top + r2.height / 2;

    // 上弦高拱頂點 (走視窗頂部邊緣，絕對不阻擋中下方步驟組件)
    var peakY = Math.max(16, Math.min(y1, y2) - 45);

    // 控制點：拔地而起向上飛至頂部，再平滑橫跨降落注入網盤按鈕
    var cx1 = x1 + (x2 - x1) * 0.12;
    var cy1 = peakY;
    var cx2 = x2 - (x2 - x1) * 0.25;
    var cy2 = peakY;

    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.id = 'tutorial-guide-arrow-layer';
    svg.style.position = 'fixed';
    svg.style.inset = '0';
    svg.style.width = '100vw';
    svg.style.height = '100vh';
    svg.style.zIndex = '99998';
    svg.style.pointerEvents = 'none';
    svg.style.opacity = '1';
    svg.style.transition = 'opacity 0.35s ease';

    svg.innerHTML = `
      <defs>
        <linearGradient id="guideArrowGrad" x1="0%" y1="100%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="#00BCD4" stop-opacity="0.9" />
          <stop offset="100%" stop-color="#10B981" stop-opacity="1" />
        </linearGradient>
        <marker id="guideArrowHead" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
          <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#10B981" />
        </marker>
        <filter id="guideArrowGlow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="3.5" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
      </defs>
      <!-- 底層光暈 -->
      <path d="M ${x1} ${y1} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${x2} ${y2}" 
            fill="none" stroke="rgba(0, 188, 212, 0.4)" stroke-width="7" filter="url(#guideArrowGlow)" />
      <!-- 主導引流光線 -->
      <path d="M ${x1} ${y1} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${x2} ${y2}" 
            fill="none" stroke="url(#guideArrowGrad)" stroke-width="3.2" stroke-dasharray="8 6" 
            marker-end="url(#guideArrowHead)" style="animation: tutorialDashAnim 1s linear infinite;" />
    `;

    document.body.appendChild(svg);
  }

  function removeGuideArrow(fade) {
    var svg = document.getElementById('tutorial-guide-arrow-layer');
    if (!svg) return;
    if (fade) {
      svg.style.transition = 'opacity 0.35s ease';
      svg.style.opacity = '0';
      setTimeout(function() {
        if (svg && svg.parentNode) svg.remove();
      }, 360);
    } else {
      svg.remove();
    }
  }

  // 步驟 6 輪播資料庫 (3 大動作，單行精練說明)
  var _carouselSteps = [
    {
      stepNum: '1',
      stepTitle: '建立新資料夾',
      colorLight: '#0284C7',
      colorDark: '#00BCD4',
      imgSrc: 'assets/tutorial/add_new_folder.png',
      alt: '建立新資料夾',
      descText: '登入雲端硬碟，點選「＋新增」建立補丁專屬資料夾（例：連線補丁庫）'
    },
    {
      stepNum: '2',
      stepTitle: '開啟共用選單',
      colorLight: '#7C3AED',
      colorDark: '#A855F7',
      imgSrc: 'assets/tutorial/share_permission.png',
      alt: '開啟共用選單',
      descText: '在資料夾按滑鼠右鍵 ➔ 移動至「共用」➔ 點選「共用」'
    },
    {
      stepNum: '3',
      stepTitle: '公開權限並複製連結',
      colorLight: '#059669',
      colorDark: '#10B981',
      imgSrc: 'assets/tutorial/finished_setting.png',
      alt: '公開權限並複製連結',
      descText: '存取權改為「知道連結的任何人」，角色為「檢視者」並複製連結！'
    }
  ];
  var _currentCarouselIdx = 0;

  function renderCarouselStep(idx) {
    var titleEl = document.getElementById('gdrive-carousel-step-title');
    var imgEl = document.getElementById('gdrive-carousel-img');
    var textEl = document.getElementById('gdrive-carousel-desc');
    var data = _carouselSteps[idx];
    if (titleEl) {
      titleEl.innerText = `${data.stepNum}. ${data.stepTitle}`;
      var isDark = document.body.classList.contains('dark') || document.documentElement.classList.contains('dark') || (document.getElementById('app') && document.getElementById('app').classList.contains('dark'));
      titleEl.style.color = isDark ? data.colorDark : data.colorLight;
    }
    if (imgEl) {
      imgEl.src = data.imgSrc;
      imgEl.alt = data.alt;
    }
    if (textEl) {
      textEl.innerText = data.descText;
    }

    // 更新圖片正下方的膠囊指示條
    var dots = document.querySelectorAll('#gdrive-carousel-dots .gdrive-dot');
    dots.forEach(function(dot, i) {
      if (i === idx) dot.classList.add('active');
      else dot.classList.remove('active');
    });
  }

  function setupGDriveCarouselClicks() {
    var dots = document.querySelectorAll('#gdrive-carousel-dots .gdrive-dot');
    dots.forEach(function(dot) {
      dot.onclick = function(e) {
        e.stopPropagation();
        var idx = parseInt(this.getAttribute('data-idx'), 10);
        if (!isNaN(idx) && idx !== _currentCarouselIdx) {
          stopGDriveCarousel();
          _currentCarouselIdx = idx;
          var viewport = document.getElementById('gdrive-carousel-viewport');
          if (viewport) {
            viewport.style.opacity = '0';
            setTimeout(function() {
              renderCarouselStep(_currentCarouselIdx);
              viewport.style.opacity = '1';
            }, 180);
          } else {
            renderCarouselStep(_currentCarouselIdx);
          }
          // 點擊後重新排程 5 秒繼續下一輪
          _carouselTimer = setTimeout(function() {
            cycleCarousel();
          }, 5000);
        }
      };
    });
  }

  function cycleCarousel() {
    var viewport = document.getElementById('gdrive-carousel-viewport');
    if (viewport) {
      // 0.4s 漸隱 (fade out)
      viewport.style.opacity = '0';
    }

    setTimeout(function() {
      _currentCarouselIdx = (_currentCarouselIdx + 1) % _carouselSteps.length;
      renderCarouselStep(_currentCarouselIdx);

      // 0.4s 漸顯 (fade in)
      if (viewport) {
        viewport.style.opacity = '1';
      }

      // 5s 停留後繼續下一輪
      _carouselTimer = setTimeout(cycleCarousel, 5000);
    }, 400);
  }

  function startGDriveCarousel() {
    stopGDriveCarousel();
    _currentCarouselIdx = 0;
    renderCarouselStep(0);
    setupGDriveCarouselClicks();

    // 5 秒後進入下一輪
    _carouselTimer = setTimeout(cycleCarousel, 5000);
  }

  function stopGDriveCarousel() {
    if (_carouselTimer) {
      clearTimeout(_carouselTimer);
      _carouselTimer = null;
    }
  }


  // 🌟 Google Drive 列表渲染鉤子（防止非同步 loadGDriveSettings 沖掉教學示範行）
  var _origRenderGDriveRows = null;
  function hookRenderGDriveRows() {
    if (!_origRenderGDriveRows && typeof window.renderGDriveRows === 'function') {
      _origRenderGDriveRows = window.renderGDriveRows;
      window.renderGDriveRows = function() {
        _origRenderGDriveRows.apply(this, arguments);
        if (_mockDriveInserted) {
          var container = document.getElementById('gdrive-list-container');
          var existing = document.getElementById('tutorial-mock-gdrive-row');
          if (container && !existing) {
            injectMockGDriveRow();
          }
        }
      };
    }
  }

  function unhookRenderGDriveRows() {
    if (_origRenderGDriveRows && typeof window.renderGDriveRows === 'function') {
      window.renderGDriveRows = _origRenderGDriveRows;
      _origRenderGDriveRows = null;
    }
  }

  // 注入示範 Google Drive 網盤行（步驟 8 示範填寫項目）
  function injectMockGDriveRow() {
    var container = document.getElementById('gdrive-list-container');
    if (!container) return null;
    var existing = document.getElementById('tutorial-mock-gdrive-row');
    if (existing) return existing;

    _mockDriveInserted = true;
    var mockRow = document.createElement('div');
    mockRow.className = 'gdrive-row-card tutorial-mock-row';
    mockRow.id = 'tutorial-mock-gdrive-row';
    mockRow.setAttribute('data-idx', 'mock');
    mockRow.style.border = '2px solid rgba(0, 188, 212, 0.9)';
    mockRow.style.boxShadow = '0 0 20px rgba(0, 188, 212, 0.35)';
    mockRow.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
        <div style="font-size:12px;display:flex;align-items:center;gap:8px">
          <span style="font-weight:700;color:#00bcd4">網盤 1 <small style="font-weight:normal">(最高優先級 - 示範)</small></span>
          <span id="tut-mock-badge" class="search-tag" style="background:rgba(0,188,212,0.15);color:#00bcd4;border:1px solid rgba(0,188,212,0.4);font-size:11px;padding:2px 8px;border-radius:12px">⌨️ 模擬輸入就緒</span>
        </div>
        <div style="display:flex;gap:4px;align-items:center">
          <button type="button" class="btn btn-o btn-xs" disabled style="opacity:0.3;cursor:not-allowed">🔼 上移</button>
          <button type="button" class="btn btn-o btn-xs" disabled style="opacity:0.3;cursor:not-allowed">🔽 下移</button>
          <button type="button" class="btn btn-o btn-xs" disabled style="color:#e05353;border-color:rgba(224,83,83,0.3);opacity:0.4;cursor:not-allowed">🗑️ 刪除</button>
        </div>
      </div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <input type="text" id="tut-mock-name" class="gdrive-input-name" style="width:170px;flex-shrink:0" placeholder="請輸入自訂網盤名稱..." value="">
        <input type="text" id="tut-mock-url" class="gdrive-input-url" style="flex:1;min-width:240px" placeholder="請貼上 Google Drive 資料夾連結..." value="">
      </div>
    `;

    // 若原先是空提示，清空後加入
    if (container.children.length === 1 && container.children[0].innerText.includes('尚未設定')) {
      container.innerHTML = '';
    }
    container.insertBefore(mockRow, container.firstChild);
    return mockRow;
  }

  // 🌟 動態打字機輸入動畫輔助
  var _mockTypingTimer = null;
  function startMockTypingAnimation(onDone) {
    stopMockTypingAnimation();
    var nameInp = document.getElementById('tut-mock-name');
    var urlInp = document.getElementById('tut-mock-url');
    var badge = document.getElementById('tut-mock-badge');
    if (!nameInp || !urlInp) return;

    nameInp.value = '';
    urlInp.value = '';
    nameInp.classList.add('tutorial-input-typing');
    urlInp.classList.remove('tutorial-input-typing');
    if (badge) {
      badge.textContent = '⌨️ 正在模擬鍵入網盤名稱...';
      badge.style.color = '#00bcd4';
      badge.style.background = 'rgba(0,188,212,0.15)';
    }

    // 階段 1：鍵入自訂網盤名稱「好友連線補丁庫」
    if (window.TutorialEngine && typeof window.TutorialEngine.simulateTyping === 'function') {
      window.TutorialEngine.simulateTyping(nameInp, '好友連線補丁庫', { speed: 65 }, function() {
        nameInp.classList.remove('tutorial-input-typing');
        if (badge) badge.textContent = '📋 正在模擬貼上雲端連結...';

        _mockTypingTimer = setTimeout(function() {
          urlInp.classList.add('tutorial-input-typing');
          var demoUrl = 'https://drive.google.com/drive/folders/1ABC_DEMO_FRIENDS_PATCH_LIB';
          // 階段 2：鍵入/貼上 Google Drive 網址
          window.TutorialEngine.simulateTyping(urlInp, demoUrl, { speed: 22 }, function() {
            urlInp.classList.remove('tutorial-input-typing');
            if (badge) {
              badge.innerHTML = '✅ 示範資料輸入完成';
              badge.style.background = 'rgba(16,185,129,0.18)';
              badge.style.color = '#10B981';
              badge.style.borderColor = 'rgba(16,185,129,0.45)';
            }
            if (window.TutorialEngine) window.TutorialEngine.reposition();
            if (onDone) onDone();
          });
        }, 220);
      });
    } else {
      // 降級備用
      nameInp.value = '好友連線補丁庫';
      urlInp.value = 'https://drive.google.com/drive/folders/1ABC_DEMO_FRIENDS_PATCH_LIB';
      if (badge) badge.innerHTML = '✅ 示範資料輸入完成';
      if (onDone) onDone();
    }
  }

  function stopMockTypingAnimation() {
    if (_mockTypingTimer) {
      clearTimeout(_mockTypingTimer);
      _mockTypingTimer = null;
    }
    var nameInp = document.getElementById('tut-mock-name');
    var urlInp = document.getElementById('tut-mock-url');
    if (nameInp && !nameInp.value) nameInp.value = '好友連線補丁庫';
    if (urlInp && !urlInp.value) urlInp.value = 'https://drive.google.com/drive/folders/1ABC_DEMO_FRIENDS_PATCH_LIB';
  }

  var _mockAddHandler = null;
  var _mockSaveHandler = null;

  function cleanupLeaderGDriveSandbox() {
    stopMockTypingAnimation();
    unhookRenderGDriveRows();
    removeGuideArrow();
    stopGDriveCarousel();
    window.removeEventListener('resize', drawGuideArrowFromSettingsToGDrive);

    var mockRow = document.getElementById('tutorial-mock-gdrive-row');
    if (mockRow) mockRow.remove();

    var btnAdd = document.querySelector('#settings-tab-adv button[onclick="addGDriveRow()"]');
    if (btnAdd && _mockAddHandler) {
      btnAdd.removeEventListener('click', _mockAddHandler, true);
      _mockAddHandler = null;
    }

    var btnSave = document.getElementById('btn-save-gdrive');
    if (btnSave) {
      if (_mockSaveHandler) {
        btnSave.removeEventListener('click', _mockSaveHandler, true);
        _mockSaveHandler = null;
      }
      btnSave.innerHTML = '<svg viewBox="0 0 16 16" width="13" height="13" fill="currentColor"><path d="M2 1a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V4.414a1 1 0 0 0-.293-.707l-2.414-2.414A1 1 0 0 0 11.586 1H2zm7 2v3H4V3h5zm3 10H4v-4h8v4z"/></svg> 儲存網盤設定';
    }

    if (_savedOriginalGDriveList !== null && window._gdriveDrives) {
      window._gdriveDrives = JSON.parse(JSON.stringify(_savedOriginalGDriveList));
      if (typeof window.renderGDriveRows === 'function') {
        window.renderGDriveRows();
      }
      _savedOriginalGDriveList = null;
    }
    _mockDriveInserted = false;
  }

  var leaderGDriveSteps = [
    // 步驟 1 (整體步驟 5)：高亮左側設定與頂部網盤，上弦箭頭指引，氣泡指向網盤
    {
      role: 'leader',
      roleBadge: '🚀 線上補丁',
      moduleTitle: '單元 2：Google Drive 網盤配置',
      title: '前往設定與網盤分頁',
      page: 'settings',
      desc: '隊長可以自建雲端補丁庫供好友一鍵極速同步！<br>' +
            '請點選左側選單的<strong>「⚙️ 設定」</strong>，接著點選頂部的<strong>「🌐 網盤」</strong>分頁（如箭頭指引）。',
      target: function() {
        ensureSettingsAdvTab();
        return document.getElementById('btn-stab-adv');
      },
      secondaryTarget: function() {
        return document.querySelector('.sidebar button[data-p="settings"]');
      },
      secondaryPadding: 6,
      secondaryBorderRadius: 10,
      placement: 'bottom',
      padding: 6,
      borderRadius: 8,
      onEnter: function() {
        ensureSettingsAdvTab();
        setTimeout(drawGuideArrowFromSettingsToGDrive, 100);
        window.addEventListener('resize', drawGuideArrowFromSettingsToGDrive);
      },
      onLeave: function() {
        removeGuideArrow(true); // 🌟 前進至下一步時箭頭漸顯淡出消失
        window.removeEventListener('resize', drawGuideArrowFromSettingsToGDrive);
      },
      hint: '請跟隨畫面上方的高拱上弦導引箭頭，切換至「🌐 網盤」分頁！'
    },

    // 步驟 2 (整體步驟 6)：無母組件雙子卡並列結構，左大右小，大圖展示，充分利用空間
    {
      role: 'leader',
      roleBadge: '🚀 線上補丁',
      moduleTitle: '單元 2：Google Drive 網盤配置',
      title: 'Google Drive 資料夾建立與公開設定',
      width: 1080,
      placement: 'center',
      center: true,
      liftTop: true,
      customLayout: 'dual-cards',
      target: null, // 居中全螢幕半透明遮罩
      desc: '<!-- 🌟 左側：獨立動畫子組件卡片 (大圖展示，充分利用空間，左大右小) -->' +
            '<div class="gdrive-carousel-card">' +
              '<div id="gdrive-carousel-viewport" style="display:flex;flex-direction:column;align-items:center;transition:opacity 0.4s ease-in-out;opacity:1;width:100%">' +
                '<div id="gdrive-carousel-step-title" class="gdrive-carousel-step-title">' +
                  '1. 建立新資料夾' +
                '</div>' +
                '<div style="width:100%;height:290px;display:flex;align-items:center;justify-content:center;background:rgba(15,23,42,0.85);border-radius:12px;overflow:hidden;border:1px solid rgba(255,255,255,0.18)">' +
                  '<img id="gdrive-carousel-img" src="assets/tutorial/add_new_folder.png" alt="建立新資料夾" style="width:100%;height:100%;object-fit:contain;display:block">' +
                '</div>' +
                '<!-- 圖片底部的敘述：高對比度字幕條，單行精練 -->' +
                '<div id="gdrive-carousel-desc" class="gdrive-carousel-desc">' +
                  '登入雲端硬碟，點選「＋新增」建立補丁專屬資料夾（例：連線補丁庫）' +
                '</div>' +
              '</div>' +
              '<!-- 順序顯示膠囊導航條：高對比度、支援手動點擊切換 -->' +
              '<div id="gdrive-carousel-dots" class="gdrive-carousel-dots">' +
                '<div class="gdrive-dot active" data-idx="0" title="點擊切換：建立新資料夾">' +
                  '<span class="dot-num">1</span>' +
                  '<span class="dot-label">建立資料夾</span>' +
                '</div>' +
                '<div class="gdrive-dot" data-idx="1" title="點擊切換：開啟共用選單">' +
                  '<span class="dot-num">2</span>' +
                  '<span class="dot-label">開啟共用</span>' +
                '</div>' +
                '<div class="gdrive-dot" data-idx="2" title="點擊切換：公開權限並複製連結">' +
                  '<span class="dot-num">3</span>' +
                  '<span class="dot-label">複製連結</span>' +
                '</div>' +
              '</div>' +
            '</div>' +

            '<!-- 🌟 右側：獨立步驟子組件卡片 (自適應高對比度深淺模式) -->' +
            '<div class="gdrive-step-card">' +
              '<div>' +
                '<div class="popover-header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">' +
                  '<div class="popover-tags" style="display:flex;align-items:center;gap:6px">' +
                    '<span class="tag-role tag-role-leader">🚀 線上補丁</span>' +
                    '<span class="tag-module">單元 2：Google Drive 網盤配置</span>' +
                  '</div>' +
                  '<button class="btn-popover-close" id="tutorial-popover-close" title="退出教學">✕</button>' +
                '</div>' +
                '<div class="popover-body">' +
                  '<div class="popover-step-index" style="font-size:11px;font-weight:800;color:#E91E63;margin-bottom:3px">步驟 6 / 12</div>' +
                  '<h4 class="popover-step-title" style="margin:0 0 10px 0;font-size:15px;font-weight:800">Google Drive 資料夾建立與公開設定</h4>' +
                  '<div class="gdrive-guide-step-list">' +
                    '<div class="gdrive-guide-step-item step-1">' +
                      '<div class="gdrive-guide-step-header">' +
                        '<span class="step-badge">1</span>' +
                        '<span class="step-title">建立專屬資料夾</span>' +
                      '</div>' +
                      '<div class="step-desc">' +
                        '登入雲端硬碟建立資料夾（例：連線補丁庫）。' +
                      '</div>' +
                    '</div>' +
                    '<div class="gdrive-guide-step-item step-2">' +
                      '<div class="gdrive-guide-step-header">' +
                        '<span class="step-badge">2</span>' +
                        '<span class="step-title">開啟資料夾共用選單</span>' +
                      '</div>' +
                      '<div class="step-desc">' +
                        '資料夾點右鍵 ➔ 移動至「共用」➔ 點選「共用」。' +
                      '</div>' +
                    '</div>' +
                    '<div class="gdrive-guide-step-item step-3">' +
                      '<div class="gdrive-guide-step-header">' +
                        '<span class="step-badge">3</span>' +
                        '<span class="step-title">公開權限與複製連結 (關鍵)</span>' +
                      '</div>' +
                      '<div class="step-desc">' +
                        '存取權改為 <span class="hl-badge hl-green">知道連結的任何人</span>，角色保持 <span class="hl-badge hl-dark">檢視者</span>，最後點擊 <span class="hl-badge hl-pink">複製連結</span>！' +
                      '</div>' +
                    '</div>' +
                  '</div>' +
                  '<div class="popover-hint" style="margin-top:10px;font-size:11.5px;padding:6px 9px">' +
                    '💡 複製連結後即可貼入 SMU 網盤網址欄，好友即可秒速讀取！' +
                  '</div>' +
                '</div>' +
              '</div>' +
              '<div class="popover-footer" style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px;padding-top:10px;border-top:1px solid rgba(255,255,255,0.1)">' +
                '<button class="btn btn-o btn-xs" id="tutorial-popover-prev">上一步</button>' +
                '<button class="btn btn-p btn-xs" id="tutorial-popover-next" style="font-weight:700">下一步 ➔</button>' +
              '</div>' +
            '</div>',
      onEnter: function() {
        startGDriveCarousel();
      },
      onLeave: function() {
        stopGDriveCarousel();
      },
      hint: '左側為動畫演示，觀看完成後點擊下一步！'
    },

    // 步驟 3 (整體步驟 7)：補丁檔案上傳規範 (強調正常不需改檔名)
    {
      role: 'leader',
      roleBadge: '🚀 線上補丁',
      moduleTitle: '單元 2：Google Drive 網盤配置',
      title: '補丁檔案上傳與命名規範',
      page: 'settings',
      width: 440,
      desc: '<p style="margin:0 0 10px 0;line-height:1.6">將 <strong style="color:#FFD700">Online-fix</strong> 或 <strong style="color:#FFD700">ZeiGames</strong> 下載的補丁直接丟入 Google Drive 雲端硬碟資料夾中，<strong style="color:#FFD700">不需要解壓縮，不需要重新打包取消密碼</strong>。</p>' +
            '• <strong>免改檔名</strong>：<strong style="color:#10B981">正常來說完全不需要修改檔名</strong>，直接上傳即可！只有在極少數系統<strong>抓不到檔案的必要時候</strong>，再去調整壓縮檔名。<br>' +
            '• <strong>支援格式</strong>：直接拖曳上傳 <strong>.zip</strong>、<strong>.rar</strong> 或 <strong>.7z</strong> 壓縮檔。<br>' +
            'SMU 內建強大的<strong>智慧模糊比對</strong>，後台會自動收錄並秒級關聯遊戲！',
      target: function() {
        ensureSettingsAdvTab();
        return document.querySelector('#settings-tab-adv .gdrive-guide-card') || document.getElementById('btn-stab-adv');
      },
      placement: 'bottom',
      padding: 6,
      borderRadius: 12,
      onEnter: function() {
        ensureSettingsAdvTab();
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
        }, 120);
      },
      hint: '不用解壓縮取消密碼，整包壓縮檔直接丟上雲端硬碟即可！'
    },

    // 步驟 4 (整體步驟 8：拆分第 1 步)：新增 Google Drive 網盤與示範項目
    {
      role: 'leader',
      roleBadge: '🚀 線上補丁',
      moduleTitle: '單元 2：Google Drive 網盤配置',
      title: '新增 Google Drive 網盤與示範項目',
      page: 'settings',
      width: 480,
      placement: 'top',
      desc: '現在回到 SMU，我們將把剛才複製的 Google Drive 雲端資料夾連結加入軟體中：<br>' +
            '• <strong>自訂網盤名稱</strong>：填入便於識別的名稱（例如：<code>好友連線補丁庫</code>）。<br>' +
            '• <strong>Google Drive 網址</strong>：貼入複製的共用資料夾連結。<br>' +
            '系統已在畫面中為您<strong>現場模擬真實鍵入名稱與貼上雲端硬碟連結</strong>！',
      target: function() {
        ensureSettingsAdvTab();
        backupGDriveData();
        hookRenderGDriveRows();
        var row = injectMockGDriveRow();
        return row || document.getElementById('gdrive-list-container') || document.querySelector('#settings-tab-adv button[onclick="addGDriveRow()"]');
      },
      padding: 8,
      borderRadius: 10,
      onEnter: function() {
        ensureSettingsAdvTab();
        backupGDriveData();
        hookRenderGDriveRows();
        var row = injectMockGDriveRow();
        if (row && typeof row.scrollIntoView === 'function') {
          row.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        setTimeout(function() {
          if (window.TutorialEngine) window.TutorialEngine.reposition();
          startMockTypingAnimation();
        }, 180);
      },
      onLeave: function() {
        stopMockTypingAnimation();
      },
      onBeforeNext: function() {
        stopMockTypingAnimation();
      },
      hint: '請觀看輸入框模擬鍵入動畫，完成後點擊「下一步 ➔」！'
    },

    // 步驟 5 (整體步驟 9：拆分第 2 步)：儲存網盤設定與背景快取
    {
      role: 'leader',
      roleBadge: '🚀 線上補丁',
      moduleTitle: '單元 2：Google Drive 網盤配置',
      title: '儲存網盤設定與背景快取',
      page: 'settings',
      width: 420,
      disableNext: true,
      desc: '資料確認填寫完畢後，請點選畫面中高亮的<strong>「💾 儲存網盤設定」</strong>按鈕。<br>' +
            '軟體將會立即在後台快取解析雲端資料夾內容，完成補丁庫關聯！',
      target: function() {
        ensureSettingsAdvTab();
        return document.getElementById('btn-save-gdrive');
      },
      placement: 'top',
      padding: 8,
      borderRadius: 10,
      onEnter: function() {
        ensureSettingsAdvTab();
        var btnSave = document.getElementById('btn-save-gdrive');
        if (!btnSave) return;

        if (_mockSaveHandler) {
          btnSave.removeEventListener('click', _mockSaveHandler, true);
        }

        _mockSaveHandler = function(se) {
          se.stopPropagation();
          se.stopImmediatePropagation();
          se.preventDefault();
          btnSave.removeEventListener('click', _mockSaveHandler, true);
          _mockSaveHandler = null;

          var oldSaveHTML = btnSave.innerHTML;
          btnSave.innerHTML = '<span>⏳ 正在快取解析...</span>';
          setTimeout(function() {
            btnSave.innerHTML = '<span>✅ 儲存成功！</span>';
            if (typeof tt === 'function') {
              tt('🎉 Google Drive 網盤配置模擬儲存成功！', 'success', 2200);
            }
            setTimeout(function() {
              btnSave.innerHTML = oldSaveHTML;
              var mockRow = document.getElementById('tutorial-mock-gdrive-row');
              if (mockRow) mockRow.remove();
              _mockDriveInserted = false;
              if (window.TutorialEngine) window.TutorialEngine.next();
            }, 800);
          }, 1100);
        };

        btnSave.addEventListener('click', _mockSaveHandler, true);
      },
      onLeave: function() {
        var btnSave = document.getElementById('btn-save-gdrive');
        if (btnSave && _mockSaveHandler) {
          btnSave.removeEventListener('click', _mockSaveHandler, true);
          _mockSaveHandler = null;
        }
      },
      hint: '請點擊畫面中聚焦的「💾 儲存網盤設定」按鈕！'
    }
  ];

  if (window.TutorialEngine) {
    window.TutorialEngine.registerModule('leader_gdrive_config', {
      title: 'Google Drive 網盤配置',
      steps: leaderGDriveSteps,
      cleanup: cleanupLeaderGDriveSandbox
    });
  }

  window.cleanupLeaderGDriveSandbox = cleanupLeaderGDriveSandbox;
})(window);
