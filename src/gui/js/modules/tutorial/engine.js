/**
 * Steam Manifest Updater - 模組化教學聚光燈與互動模擬引擎
 * 核心功能：
 * 1. 局部高亮遮罩 (Spotlight Overlay) 與動態呼吸光暈
 * 2. 自適應方向教學浮動氣泡卡 (Adaptive Popover)
 * 3. 真實鍵入打字機效果模擬 (Simulated Typing)
 * 4. 純前端沙盒虛擬資料隔離 (Sandbox Mock Data Guard，無過雲端，不污染本機設定)
 * 5. 模組化步進管線控制器 (Step-by-Step Pipeline Runner)
 */

(function(window) {
  'use strict';

  var _overlayEl = null;
  var _popoverEl = null;
  var _activeTargetEl = null;
  var _currentSteps = [];
  var _currentIndex = -1;
  var _onCompleteCb = null;
  var _onCancelCb = null;
  var _isTyping = false;
  var _registeredModules = {};

  // 1. 初始化或取得遮罩與氣泡容器
  function ensureDOM() {
    if (!_overlayEl) {
      _overlayEl = document.createElement('div');
      _overlayEl.id = 'tutorial-spotlight-overlay';
      _overlayEl.className = 'tutorial-spotlight-overlay hidden';
      _overlayEl.innerHTML = `
        <svg class="spotlight-svg-mask" width="100%" height="100%">
          <defs>
            <mask id="spotlight-mask">
              <rect x="0" y="0" width="100%" height="100%" fill="white" />
              <rect id="spotlight-cutout" x="0" y="0" width="0" height="0" rx="10" ry="10" fill="black" />
              <rect id="spotlight-cutout-sub" x="0" y="0" width="0" height="0" rx="8" ry="8" fill="black" />
              <rect id="spotlight-cutout-third" x="0" y="0" width="0" height="0" rx="8" ry="8" fill="black" />
            </mask>
          </defs>
          <rect x="0" y="0" width="100%" height="100%" fill="rgba(10, 14, 24, 0.78)" mask="url(#spotlight-mask)" />
        </svg>
      `;
      document.body.appendChild(_overlayEl);
    }

    if (!_popoverEl) {
      _popoverEl = document.createElement('div');
      _popoverEl.id = 'tutorial-step-popover';
      _popoverEl.className = 'tutorial-step-popover hidden';
      document.body.appendChild(_popoverEl);
    }

    window.addEventListener('resize', handleReposition);
    window.addEventListener('scroll', handleReposition, true);
  }

  function handleReposition() {
    if (_activeTargetEl && !_popoverEl.classList.contains('hidden')) {
      positionSpotlightAndPopover(_activeTargetEl, _currentSteps[_currentIndex]);
    }
  }

  // 2. 定位聚光燈裁切孔與提示卡片
  function positionSpotlightAndPopover(targetEl, stepConfig) {
    if (!targetEl || !stepConfig) return;

    var rect = targetEl.getBoundingClientRect();
    // 🌟 零尺寸防禦：若元素尚未完成排版或處於頁面切換過渡期，延遲 80ms 自動重試，絕不使用 (0,0) 錯誤渲染
    if (rect.width === 0 && rect.height === 0 && targetEl !== document.body) {
      setTimeout(function() {
        if (_currentIndex >= 0 && _currentSteps[_currentIndex]) {
          positionSpotlightAndPopover(targetEl, stepConfig);
        }
      }, 80);
      return;
    }
    var pad = stepConfig.padding || 8;
    var x = Math.max(0, rect.left - pad);
    var y = Math.max(0, rect.top - pad);
    var w = rect.width + pad * 2;
    var h = rect.height + pad * 2;
    var radius = stepConfig.borderRadius || 10;

    var cutout = document.getElementById('spotlight-cutout');
    if (cutout) {
      cutout.setAttribute('x', x);
      cutout.setAttribute('y', y);
      cutout.setAttribute('width', w);
      cutout.setAttribute('height', h);
      cutout.setAttribute('rx', radius);
      cutout.setAttribute('ry', radius);
    }

    // 🌟 多邊形高亮擴充：次級裁切孔（如下拉選單、浮動選單）
    var cutoutSub = document.getElementById('spotlight-cutout-sub');
    var subEl = null;
    if (stepConfig.secondaryTarget) {
      if (typeof stepConfig.secondaryTarget === 'function') {
        subEl = stepConfig.secondaryTarget();
      } else if (typeof stepConfig.secondaryTarget === 'string') {
        subEl = document.querySelector(stepConfig.secondaryTarget);
      }
    }

    if (cutoutSub) {
      if (subEl) {
        var subRect = subEl.getBoundingClientRect();
        var subPad = stepConfig.secondaryPadding || 4;
        cutoutSub.setAttribute('x', Math.max(0, subRect.left - subPad));
        cutoutSub.setAttribute('y', Math.max(0, subRect.top - subPad));
        cutoutSub.setAttribute('width', subRect.width + subPad * 2);
        cutoutSub.setAttribute('height', subRect.height + subPad * 2);
        cutoutSub.setAttribute('rx', stepConfig.secondaryBorderRadius || 8);
        cutoutSub.setAttribute('ry', stepConfig.secondaryBorderRadius || 8);
      } else {
        cutoutSub.setAttribute('width', 0);
        cutoutSub.setAttribute('height', 0);
      }
    }

    // 🌟 多邊形高亮擴充：第三裁切孔（如管理小卡的 "..." 按鈕）
    var cutoutThird = document.getElementById('spotlight-cutout-third');
    var thirdEl = null;
    if (stepConfig.thirdTarget) {
      if (typeof stepConfig.thirdTarget === 'function') {
        thirdEl = stepConfig.thirdTarget();
      } else if (typeof stepConfig.thirdTarget === 'string') {
        thirdEl = document.querySelector(stepConfig.thirdTarget);
      }
    }

    if (cutoutThird) {
      if (thirdEl) {
        var thirdRect = thirdEl.getBoundingClientRect();
        var thirdPad = stepConfig.thirdPadding || 4;
        cutoutThird.setAttribute('x', Math.max(0, thirdRect.left - thirdPad));
        cutoutThird.setAttribute('y', Math.max(0, thirdRect.top - thirdPad));
        cutoutThird.setAttribute('width', thirdRect.width + thirdPad * 2);
        cutoutThird.setAttribute('height', thirdRect.height + thirdPad * 2);
        cutoutThird.setAttribute('rx', stepConfig.thirdBorderRadius || 6);
        cutoutThird.setAttribute('ry', stepConfig.thirdBorderRadius || 6);
      } else {
        cutoutThird.setAttribute('width', 0);
        cutoutThird.setAttribute('height', 0);
      }
    }

    // 計算 Popover 最佳位置 (加強真實 DOM 高度檢測、邊界限制與精準箭頭瞄準)
    var popW = stepConfig.width || 350;
    _popoverEl.style.width = popW + 'px';
    var popH = (_popoverEl.offsetHeight > 0) ? _popoverEl.offsetHeight : (stepConfig.height || 240);
    var winW = window.innerWidth;
    var winH = window.innerHeight;

    var popLeft = 0;
    var popTop = 0;
    var placement = stepConfig.placement || 'auto';

    // 🌟 核心增強：若宣告 placement: 'center' 或 target 為空，直接在畫面正中央呈現，不挖聚光燈孔
    if (placement === 'center' || stepConfig.center || !stepConfig.target) {
      if (cutout) {
        cutout.setAttribute('width', 0);
        cutout.setAttribute('height', 0);
      }
      var popW = stepConfig.width || 560;
      _popoverEl.style.width = popW + 'px';
      var popH = (_popoverEl.offsetHeight > 0) ? _popoverEl.offsetHeight : (stepConfig.height || 360);
      var winW = window.innerWidth;
      var winH = window.innerHeight;
      var popLeft = Math.max(16, (winW - popW) / 2);
      // 🌟 支援 liftTop 往頂部抬升
      var popTop = Math.max(16, (stepConfig.liftTop ? (winH - popH) * 0.18 : (stepConfig.topOffset != null ? stepConfig.topOffset : (winH - popH) / 2)));
      _popoverEl.dataset.arrow = 'none';
      _popoverEl.style.setProperty('--arrow-left', '-9999px');
      _popoverEl.style.setProperty('--arrow-top', '-9999px');
      _popoverEl.style.left = popLeft + 'px';
      _popoverEl.style.top = popTop + 'px';
      return;
    }

    // 🌟 核心增強：支援分離「聚光燈裁切目標 (targetEl)」與「箭頭指向目標 (arrowEl)」
    var arrowEl = targetEl;
    if (stepConfig.arrowTarget) {
      if (typeof stepConfig.arrowTarget === 'function') {
        arrowEl = stepConfig.arrowTarget() || targetEl;
      } else if (typeof stepConfig.arrowTarget === 'string') {
        arrowEl = document.querySelector(stepConfig.arrowTarget) || targetEl;
      }
    }

    var aRect = (arrowEl && arrowEl !== targetEl) ? arrowEl.getBoundingClientRect() : rect;
    var targetCenterX = aRect.left + aRect.width / 2;
    var targetCenterY = aRect.top + aRect.height / 2;

    // 🌟 智慧判斷 1：僅目標真正位於左側邊欄按鈕時才靠右停靠，嚴禁將頁面內的小標籤或小按鈕誤判為側邊欄
    var isSidebarTarget = targetEl.closest && !!targetEl.closest('.sidebar');

    if (isSidebarTarget || placement === 'right') {
      popLeft = rect.right + 14;
      popTop = targetCenterY - 40;
      _popoverEl.dataset.arrow = 'left';
    } 
    // 🌟 智慧判斷 1.5：靠左停靠 (left)，專為右側選單或多邊形延伸區塊設計（自動避開延伸之下拉選單）
    else if (placement === 'left') {
      var avoidLeft = aRect.left;
      if (stepConfig.secondaryTarget) {
        var secEl = (typeof stepConfig.secondaryTarget === 'function') ? stepConfig.secondaryTarget() : document.querySelector(stepConfig.secondaryTarget);
        if (secEl) {
          var sRect = secEl.getBoundingClientRect();
          if (sRect.width > 0 && sRect.height > 0) {
            avoidLeft = Math.min(avoidLeft, sRect.left);
          }
        }
      }
      popLeft = avoidLeft - popW - 16;
      popTop = targetCenterY - popH / 2;
      _popoverEl.dataset.arrow = 'right';
    }
    // 🌟 智慧判斷 1.8：左下方停靠 (bottom-left)
    else if (placement === 'bottom-left' || (placement === 'bottom' && stepConfig.align === 'left')) {
      popTop = Math.max(y + h + 14, aRect.bottom + 14);
      popLeft = rect.left + 24;
      _popoverEl.dataset.arrow = 'top';
    }
    // 🌟 智慧判斷 2：右下方停靠 (bottom-right)，專為寬卡片中右側按鈕精準瞄準設計
    else if (placement === 'bottom-right' || (placement === 'bottom' && stepConfig.align === 'right')) {
      popTop = Math.max(y + h + 14, aRect.bottom + 14);
      popLeft = targetCenterX - popW * 0.7;
      _popoverEl.dataset.arrow = 'top';
    }
    // 🌟 智慧判斷 3：上方停靠 (top)
    else if (placement === 'top') {
      popTop = y - popH - 14;
      popLeft = targetCenterX - popW / 2;
      _popoverEl.dataset.arrow = 'bottom';
    } 
    // 🌟 一般上下停靠 (預設 bottom 或 auto)
    else {
      var spaceBelow = winH - (y + h + 14);
      var spaceAbove = y - 14;
      // 若下方空間不足容納且上方空間充裕，自動向上停靠防止遮蔽下一步按鈕 (若指定 forcePlacement 則絕對禁止向上翻轉遮擋上下文)
      if (!stepConfig.forcePlacement && (placement === 'auto' || placement === 'bottom') && spaceBelow < popH && spaceAbove >= popH) {
        popTop = y - popH - 14;
        _popoverEl.dataset.arrow = 'bottom';
      } else {
        popTop = y + h + 14;
        _popoverEl.dataset.arrow = 'top';
      }
      popLeft = targetCenterX - popW / 2;
    }

    // 🌟 支援自訂位置細微微調偏移 (offsetX / offsetY)
    if (typeof stepConfig.offsetX === 'number') popLeft += stepConfig.offsetX;
    if (typeof stepConfig.offsetY === 'number') popTop += stepConfig.offsetY;

    // 🌟 強制 Clamp 視窗邊界保護：100% 確保留在視窗可見範圍內，絕不被切頂、切底或遮擋下一步按鈕
    if (stepConfig.forcePlacement && placement === 'bottom') {
      popTop = Math.max(y + h + 6, Math.min(popTop, Math.max(16, winH - popH - 16)));
    } else {
      popTop = Math.max(16, Math.min(popTop, Math.max(16, winH - popH - 16)));
    }
    popLeft = Math.max(16, Math.min(popLeft, Math.max(16, winW - popW - 16)));

    // 🌟 動態方向校正：依據 Clamp 後的真實垂直位置，自動修正箭頭方向（若 forcePlacement 則保持鎖定）
    if (!stepConfig.forcePlacement && (_popoverEl.dataset.arrow === 'top' || _popoverEl.dataset.arrow === 'bottom')) {
      if (popTop + popH / 2 < targetCenterY) {
        _popoverEl.dataset.arrow = 'bottom'; // 氣泡位於目標上方 -> 箭頭在底部朝下指
      } else {
        _popoverEl.dataset.arrow = 'top'; // 氣泡位於目標下方 -> 箭頭在頂部朝上指
      }
    }

    // 🌟 動態瞄準核心：精確計算箭頭在 Popover 內部的絕對像素位置，嚴防箭頭指向空氣！
    if (_popoverEl.dataset.arrow === 'top' || _popoverEl.dataset.arrow === 'bottom') {
      var arrowLeft = targetCenterX - popLeft;
      // 限制箭頭在 Popover 安全邊距內（留出圓角安全間距 24px）
      arrowLeft = Math.max(24, Math.min(popW - 24, arrowLeft));
      _popoverEl.style.setProperty('--arrow-left', arrowLeft + 'px');
    } else if (_popoverEl.dataset.arrow === 'left' || _popoverEl.dataset.arrow === 'right') {
      var arrowTop = targetCenterY - popTop;
      arrowTop = Math.max(20, Math.min(popH - 24, arrowTop));
      _popoverEl.style.setProperty('--arrow-top', arrowTop + 'px');
    }

    _popoverEl.style.left = popLeft + 'px';
    _popoverEl.style.top = popTop + 'px';
  }

  // 3. 渲染氣泡卡片內容
  function renderPopover(stepConfig, index, total) {
    var roleBadge = stepConfig.roleBadge || '🐺 獨狼玩家';
    var isLeader = (stepConfig.role === 'leader') || (roleBadge.indexOf('群眾領導') > -1) || (roleBadge.indexOf('線上補丁') > -1);
    var roleClass = isLeader ? 'tag-role tag-role-leader' : 'tag-role';
    var moduleTitle = stepConfig.moduleTitle || '教學導覽';
    var stepTitle = stepConfig.title || '操作引導';
    var stepDesc = stepConfig.desc || '';
    var hint = stepConfig.hint ? `<div class="popover-hint">💡 ${stepConfig.hint}</div>` : '';
    var actionBtnHtml = '';

    if (stepConfig.autoActionText) {
      actionBtnHtml = `<button class="btn btn-p btn-xs popover-action-btn" id="tutorial-popover-auto-action">⚡ ${stepConfig.autoActionText}</button>`;
    }

    var isLast = index === total - 1;
    var nextText = stepConfig.nextText || (isLast ? '完成教學 🎉' : '下一步 ➔');
    var isNextDisabled = !!stepConfig.disableNext;
    var nextBtnStyle = isNextDisabled 
      ? 'style="font-weight:700;opacity:0.45;cursor:not-allowed;" title="請直接點擊畫面中聚焦的高亮按鈕"' 
      : 'style="font-weight:700"';

    // 🌟 核心支援：若是 dual-cards 佈局（如步驟6無母組件，雙子卡並排），直接輸出客製化 HTML，移除外層母卡框
    if (stepConfig.customLayout === 'dual-cards') {
      _popoverEl.classList.add('tutorial-popover-dual-cards');
      _popoverEl.style.setProperty('background', 'transparent', 'important');
      _popoverEl.style.setProperty('background-color', 'transparent', 'important');
      _popoverEl.style.setProperty('border', 'none', 'important');
      _popoverEl.style.setProperty('box-shadow', 'none', 'important');
      _popoverEl.style.setProperty('padding', '0', 'important');
      _popoverEl.style.setProperty('backdrop-filter', 'none', 'important');
      _popoverEl.style.setProperty('-webkit-backdrop-filter', 'none', 'important');
      _popoverEl.innerHTML = stepDesc;
    } else {
      _popoverEl.classList.remove('tutorial-popover-dual-cards');
      _popoverEl.style.removeProperty('background');
      _popoverEl.style.removeProperty('background-color');
      _popoverEl.style.removeProperty('border');
      _popoverEl.style.removeProperty('box-shadow');
      _popoverEl.style.removeProperty('padding');
      _popoverEl.style.removeProperty('backdrop-filter');
      _popoverEl.style.removeProperty('-webkit-backdrop-filter');
      _popoverEl.innerHTML = `
        <div class="popover-header">
          <div class="popover-tags">
            <span class="${roleClass}">${roleBadge}</span>
            <span class="tag-module">${moduleTitle}</span>
          </div>
          <button class="btn-popover-close" id="tutorial-popover-close" title="退出教學">✕</button>
        </div>
        <div class="popover-body">
          <div class="popover-step-index">步驟 ${index + 1} / ${total}</div>
          <h4 class="popover-step-title">${stepTitle}</h4>
          <div class="popover-step-desc">${stepDesc}</div>
          ${hint}
        </div>
        <div class="popover-footer">
          <div class="footer-left">
            ${actionBtnHtml}
          </div>
          <div class="footer-right">
            ${index > 0 ? '<button class="btn btn-o btn-xs" id="tutorial-popover-prev">上一步</button>' : ''}
            <button class="btn btn-p btn-xs" id="tutorial-popover-next" ${nextBtnStyle}>${nextText}</button>
          </div>
        </div>
      `;
    }

    // 綁定事件
    var btnClose = document.getElementById('tutorial-popover-close');
    var btnPrev = document.getElementById('tutorial-popover-prev');
    var btnNext = document.getElementById('tutorial-popover-next');
    var btnAction = document.getElementById('tutorial-popover-auto-action');

    if (btnClose) btnClose.onclick = function() { TutorialEngine.stop(false); };
    if (btnPrev) btnPrev.onclick = function() { TutorialEngine.prev(); };
    if (btnNext) btnNext.onclick = function() {
      if (stepConfig.disableNext) {
        if (typeof tt === 'function') {
          tt('💡 請直接點擊畫面中聚焦的高亮按鈕以繼續！', 'info', 2200);
        }
        if (_activeTargetEl) {
          _activeTargetEl.classList.add('tutorial-btn-shake');
          setTimeout(function() {
            if (_activeTargetEl) _activeTargetEl.classList.remove('tutorial-btn-shake');
          }, 650);
        }
        return;
      }
      if (typeof stepConfig.onBeforeNext === 'function') {
        var p = stepConfig.onBeforeNext();
        if (p && typeof p.then === 'function') {
          p.then(function() { TutorialEngine.next(); });
          return;
        }
      }
      TutorialEngine.next();
    };

    if (btnAction && typeof stepConfig.onAutoAction === 'function') {
      btnAction.onclick = function() {
        btnAction.disabled = true;
        stepConfig.onAutoAction();
      };
    }
  }

  // 4. 打字機逐字模擬鍵入輔助工具
  function simulateTyping(inputElement, text, options, callback) {
    if (!inputElement || typeof text !== 'string') {
      if (callback) callback();
      return;
    }

    options = options || {};
    var speed = options.speed || 55;
    inputElement.focus();
    inputElement.value = '';
    var idx = 0;
    _isTyping = true;

    function tick() {
      if (!_isTyping) return;
      if (idx < text.length) {
        inputElement.value += text[idx];
        idx++;
        // 觸發 input 事件以驅動介面即時響應
        inputElement.dispatchEvent(new Event('input', { bubbles: true }));
        setTimeout(tick, speed);
      } else {
        _isTyping = false;
        inputElement.dispatchEvent(new Event('change', { bubbles: true }));
        if (callback) callback();
      }
    }
    tick();
  }

  // 5. 進入特定步驟
  function goToStep(index) {
    if (index < 0 || index >= _currentSteps.length) {
      if (index >= _currentSteps.length) {
        // 完成全部步驟
        TutorialEngine.stop(true);
      }
      return;
    }

    // 🌟 核心修復：步進切換時執行前一步的 onLeave 回調（清理圖層、定時器與動畫）
    if (_currentIndex >= 0 && _currentIndex < _currentSteps.length) {
      var prevStep = _currentSteps[_currentIndex];
      if (prevStep && typeof prevStep.onLeave === 'function') {
        try { prevStep.onLeave(); } catch(e){}
      }
    }

    _currentIndex = index;
    var step = _currentSteps[index];

    // 若該步驟指定需要先切換分頁
    if (step.page && window.switchPage) {
      window.switchPage(step.page);
      var pagesEl = document.querySelector('.pages');
      if (pagesEl) pagesEl.scrollTop = 0;
    }

    // 稍微延遲以確保 DOM 渲染完畢
    setTimeout(function() {
      var target = null;
      if (typeof step.target === 'function') {
        target = step.target();
      } else if (typeof step.target === 'string') {
        target = document.querySelector(step.target);
      }

      if (!target) {
        target = document.body; // 找不到則以整個 body 作為容錯
      }

      _activeTargetEl = target;

      // 捲動至可見區域 (改採 auto 瞬間抵達，徹底杜絕 smooth 動畫延遲導致座標測量偏差)
      if (target !== document.body && step.placement !== 'center' && typeof target.scrollIntoView === 'function') {
        var tRect = target.getBoundingClientRect();
        if (step.placement === 'bottom' && (tRect.height > 180 || tRect.top > window.innerHeight * 0.35)) {
          target.scrollIntoView({ behavior: 'auto', block: 'start' });
        } else {
          target.scrollIntoView({ behavior: 'auto', block: 'nearest' });
        }
      }

      renderPopover(step, _currentIndex, _currentSteps.length);
      positionSpotlightAndPopover(target, step);

      _overlayEl.classList.remove('hidden');
      _popoverEl.classList.remove('hidden');

      // 🌟 雙重二次校準：在 DOM 繪製與非同步圖片載入後重新精確咬合對齊
      requestAnimationFrame(function() {
        positionSpotlightAndPopover(target, step);
      });
      setTimeout(function() {
        positionSpotlightAndPopover(target, step);
      }, 60);

      // 呼叫步驟進入回調
      if (typeof step.onEnter === 'function') {
        step.onEnter(target);
      }
    }, step.delay || 120);
  }

  // 核心對外暴露 API
  var TutorialEngine = {
    /**
     * 註冊教學模組
     */
    registerModule: function(id, moduleDef) {
      _registeredModules[id] = moduleDef;
      console.log('[TutorialEngine] Registered module:', id);
    },

    getModule: function(id) {
      return _registeredModules[id] || null;
    },

    /**
     * 啟動一系列教學步驟
     */
    start: function(steps, options) {
      if (!Array.isArray(steps) || steps.length === 0) {
        console.warn('[TutorialEngine] No steps to run.');
        return;
      }
      ensureDOM();
      options = options || {};
      _currentSteps = steps;
      _onCompleteCb = options.onComplete || null;
      _onCancelCb = options.onCancel || null;
      document.body.classList.add('tutorial-active-mode');

      goToStep(0);
    },

    next: function() {
      goToStep(_currentIndex + 1);
    },

    prev: function() {
      if (_currentIndex > 0) {
        goToStep(_currentIndex - 1);
      }
    },

    /**
     * 終止教學流程
     */
    stop: function(isFinished) {
      _isTyping = false;
      if (_overlayEl) _overlayEl.classList.add('hidden');
      if (_popoverEl) _popoverEl.classList.add('hidden');
      document.body.classList.remove('tutorial-active-mode');

      // 呼叫退出回調與重置沙盒
      if (_currentIndex >= 0 && _currentSteps[_currentIndex]) {
        var cur = _currentSteps[_currentIndex];
        if (typeof cur.onLeave === 'function') {
          cur.onLeave();
        }
      }

      // 🌟 全域防護：無論正常結束或中途取消，立即執行全域沙盒狀態深度還原！
      cleanupAllTutorialSandbox();

      if (isFinished && typeof _onCompleteCb === 'function') {
        _onCompleteCb();
      } else if (!isFinished && typeof _onCancelCb === 'function') {
        _onCancelCb();
      }

      _currentIndex = -1;
      _currentSteps = [];
      _activeTargetEl = null;
    },

    simulateTyping: simulateTyping,
    reposition: handleReposition,
    retarget: function(targetEl, stepOverrides) {
      if (!targetEl) return;
      _activeTargetEl = targetEl;
      var curStep = _currentSteps[_currentIndex] || {};
      var mergedConfig = Object.assign({}, curStep, stepOverrides || {});
      positionSpotlightAndPopover(targetEl, mergedConfig);
    },
    cleanupAll: cleanupAllTutorialSandbox,
    isActive: function() {
      return _currentIndex >= 0 && _currentSteps.length > 0;
    }
  };

  /**
   * 🌟 全域教學沙盒深度還原機制 (徹底消除所有示範資料殘留)
   */
  function cleanupAllTutorialSandbox() {
    console.log('[TutorialEngine] Executing comprehensive sandbox cleanup & restoration...');

    // 1. 憑證管理頁面深度還原
    window.__tutorialMockCredentialsActive = false;
    var credBtn = document.querySelector('#p-credentials button[onclick="startDualPlatformSandboxLogin()"]');
    if (credBtn) {
      credBtn.classList.remove('tutorial-btn-simulating');
      credBtn.innerHTML = '<span>🔑</span><span>登入 / 綁定 Discord</span>';
    }
    if (typeof window.loadCredentialsStatus === 'function') {
      try { window.loadCredentialsStatus(true); } catch(e){}
    }

    // 2. 遊戲入庫 (搜尋頁) 深度還原
    var inputQ = document.getElementById('q');
    if (inputQ) {
      inputQ.value = '';
    }
    var btnQ = document.getElementById('btn-q');
    if (btnQ) {
      btnQ.disabled = false;
      btnQ.textContent = '搜尋';
    }
    var mockGameCard = document.getElementById('tutorial-mock-game-card');
    if (mockGameCard) {
      mockGameCard.remove();
    }
    var resEl = document.getElementById('results');
    if (resEl) {
      // 恢復瀏覽全部遊戲或初始空白狀態
      if (typeof window.switchBrowse === 'function') {
        try { window.switchBrowse(); } catch(e){}
      } else {
        resEl.innerHTML = '<div class="empty"><div class="icon">🎮</div><p>搜尋 Steam 遊戲，一鍵入庫</p></div>';
      }
    }

    // 3. 管理入庫頁面深度還原
    var mockManageCard = document.getElementById('tutorial-mock-manage-item');
    if (mockManageCard) {
      mockManageCard.remove();
    }
    var glist = document.getElementById('glist');
    if (glist) {
      if (typeof window.rg === 'function') {
        try { window.rg(true); } catch(e){}
      }
      if (typeof window.updateManageQuota === 'function') {
        try { window.updateManageQuota(); } catch(e){}
      }
    }

    // 4. 調用各註冊模組的專屬 cleanup
    if (_registeredModules) {
      for (var modId in _registeredModules) {
        var modDef = _registeredModules[modId];
        if (modDef && typeof modDef.cleanup === 'function') {
          try { modDef.cleanup(); } catch(e){}
        }
      }
    }
  }

  window.cleanupAllTutorialSandbox = cleanupAllTutorialSandbox;
  window.TutorialEngine = TutorialEngine;
})(window);
