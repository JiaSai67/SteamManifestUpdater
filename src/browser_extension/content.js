// ==UserScript==
// @name         SMU Google Apps Script 真實網頁聚光燈導引助手
// @namespace    https://github.com/JiaSai67/SteamManifestUpdater
// @version      1.0.0
// @description  直接在 Google Apps Script 真實網頁中動態高亮「新專案」、「部署」與「存取權限」
// @match        https://script.google.com/*
// @run-at       document-idle
// ==/UserScript==

(function() {
  'use strict';

  // 避免重複注入
  if (window.__SMU_GAS_GUIDE_INJECTED__) return;
  window.__SMU_GAS_GUIDE_INJECTED__ = true;

  console.log('[SMU] Google Apps Script 真實網頁聚光燈導引助手已啟動！');

  // 樣式注入
  var style = document.createElement('style');
  style.id = 'smu-guide-styles';
  style.textContent = `
    #smu-spotlight-box {
      position: fixed;
      pointer-events: none;
      z-index: 2147483640;
      border: 3px solid #FF4757;
      border-radius: 12px;
      box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.76), 0 0 24px rgba(255, 71, 87, 0.9);
      transition: all 0.28s cubic-bezier(0.2, 0, 0, 1);
      box-sizing: border-box;
      animation: smuPulseGlow 2s infinite ease-in-out;
    }
    @keyframes smuPulseGlow {
      0%, 100% { box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.76), 0 0 16px rgba(255, 71, 87, 0.8); }
      50% { box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.76), 0 0 32px rgba(255, 71, 87, 1); border-color: #FF6B81; }
    }
    #smu-guide-card {
      position: fixed;
      z-index: 2147483645;
      background: rgba(18, 22, 28, 0.96);
      border: 2px solid #FF4757;
      border-radius: 14px;
      padding: 16px 20px;
      max-width: 340px;
      color: #FFFFFF;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      box-shadow: 0 20px 50px rgba(0,0,0,0.8), 0 0 25px rgba(255,71,87,0.35);
      backdrop-filter: blur(12px);
      transition: all 0.28s cubic-bezier(0.2, 0, 0, 1);
      pointer-events: auto;
    }
    .smu-badge {
      display: inline-block;
      background: rgba(255, 71, 87, 0.2);
      color: #FF6B81;
      font-size: 11px;
      font-weight: 800;
      padding: 3px 8px;
      border-radius: 20px;
      margin-bottom: 6px;
      letter-spacing: 0.5px;
    }
    .smu-title {
      font-size: 15px;
      font-weight: 800;
      color: #FFFFFF;
      margin-bottom: 6px;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .smu-desc {
      font-size: 12.5px;
      color: #D1D5DB;
      line-height: 1.5;
      margin-bottom: 12px;
    }
    .smu-actions {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
    }
    .smu-btn {
      padding: 6px 14px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
      border: none;
      transition: all 0.2s;
    }
    .smu-btn-p {
      background: #FF4757;
      color: #fff;
    }
    .smu-btn-p:hover {
      background: #FF6B81;
      transform: translateY(-1px);
    }
    .smu-btn-o {
      background: transparent;
      border: 1px solid rgba(255,255,255,0.25);
      color: #9CA3AF;
    }
    .smu-btn-o:hover {
      color: #fff;
      border-color: #fff;
    }
    .smu-arrow-pointer {
      position: absolute;
      width: 0;
      height: 0;
      border-style: solid;
    }
    .smu-arrow-left {
      left: -10px;
      top: 24px;
      border-width: 8px 10px 8px 0;
      border-color: transparent #FF4757 transparent transparent;
    }
    .smu-arrow-bottom {
      bottom: -10px;
      left: 30px;
      border-width: 10px 8px 0 8px;
      border-color: #FF4757 transparent transparent transparent;
    }
    .smu-arrow-top {
      top: -10px;
      left: 30px;
      border-width: 0 8px 10px 8px;
      border-color: transparent transparent #FF4757 transparent;
    }
    .smu-bounce-indicator {
      display: inline-block;
      animation: smuBounceAnim 1s infinite alternate ease-in-out;
    }
    @keyframes smuBounceAnim {
      from { transform: translateX(0); }
      to { transform: translateX(6px); }
    }
  `;
  document.head.appendChild(style);

  // 建立 DOM 元素
  var spotlight = document.createElement('div');
  spotlight.id = 'smu-spotlight-box';
  spotlight.style.display = 'none';
  document.body.appendChild(spotlight);

  var card = document.createElement('div');
  card.id = 'smu-guide-card';
  card.style.display = 'none';
  document.body.appendChild(card);

  var currentTarget = null;
  var currentStepInfo = null;

  function highlightElement(el, badge, title, desc, onNext) {
    if (!el) {
      spotlight.style.display = 'none';
      card.style.display = 'none';
      return;
    }

    currentTarget = el;
    currentStepInfo = { badge: badge, title: title, desc: desc, onNext: onNext };

    // 捲動目標至可見範圍
    try {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } catch(e) {}

    updatePosition();
    spotlight.style.display = 'block';
    card.style.display = 'block';
  }

  function updatePosition() {
    if (!currentTarget || !currentTarget.getBoundingClientRect) return;
    var rect = currentTarget.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;

    var pad = 6;
    spotlight.style.left = (rect.left - pad) + 'px';
    spotlight.style.top = (rect.top - pad) + 'px';
    spotlight.style.width = (rect.width + pad * 2) + 'px';
    spotlight.style.height = (rect.height + pad * 2) + 'px';

    // 渲染卡片內容
    card.innerHTML = `
      <div class="smu-badge">${currentStepInfo.badge}</div>
      <div class="smu-title"><span class="smu-bounce-indicator">👉</span> ${currentStepInfo.title}</div>
      <div class="smu-desc">${currentStepInfo.desc}</div>
      <div class="smu-actions">
        <button class="smu-btn smu-btn-o" id="smu-btn-dismiss">暫時關閉</button>
        <button class="smu-btn smu-btn-p" id="smu-btn-action">下一步 ➔</button>
      </div>
      <div class="smu-arrow-pointer smu-arrow-left"></div>
    `;

    document.getElementById('smu-btn-dismiss').onclick = function() {
      spotlight.style.display = 'none';
      card.style.display = 'none';
    };

    document.getElementById('smu-btn-action').onclick = function() {
      if (typeof currentStepInfo.onNext === 'function') {
        currentStepInfo.onNext();
      }
    };

    // 卡片定位在目標右側或下方
    var cardW = card.offsetWidth || 320;
    var cardH = card.offsetHeight || 160;

    var left = rect.right + 16;
    var top = rect.top;

    if (left + cardW > window.innerWidth - 10) {
      // 擺在下方
      left = Math.max(16, rect.left);
      top = rect.bottom + 16;
      var arrow = card.querySelector('.smu-arrow-pointer');
      if (arrow) arrow.className = 'smu-arrow-pointer smu-arrow-top';
    } else {
      var arrow = card.querySelector('.smu-arrow-pointer');
      if (arrow) arrow.className = 'smu-arrow-pointer smu-arrow-left';
    }

    card.style.left = left + 'px';
    card.style.top = top + 'px';
  }

  // 監聽視窗變動即時重繪
  window.addEventListener('resize', updatePosition);
  window.addEventListener('scroll', updatePosition, true);

  // ═══════════════════════════════════════════════════════
  // 核心步驟尋找器 (DOM Detectors)
  // ═══════════════════════════════════════════════════════

  function findElementByText(selectors, textPatterns) {
    var els = Array.from(document.querySelectorAll(selectors));
    return els.find(function(el) {
      if (el.offsetParent === null) return false;
      var t = (el.innerText || el.textContent || '').trim();
      return textPatterns.some(function(pattern) {
        return t.indexOf(pattern) !== -1;
      });
    });
  }

  // 定時掃描當前頁面狀態
  function checkAndGuide() {
    var url = window.location.href;

    // 🌟 情境 1: 首頁 (script.google.com/home) -> 尋找「新專案」
    if (url.indexOf('script.google.com/home') !== -1 && url.indexOf('/projects/') === -1) {
      var newProjBtn = findElementByText('button, div[role="button"], a, [role="link"]', ['新專案', 'New project', '建立 APPS SCRIPT']);
      if (newProjBtn) {
        highlightElement(
          newProjBtn,
          '步驟 1 / 4 · 首頁',
          '點擊此處「➕ 新專案」',
          '點擊建立專屬後端腳本！SMU 會自動打包 Manifest、Lua 與補丁，此腳本將作為您個人的雲端硬碟接收端點。',
          function() {
            newProjBtn.click();
          }
        );
        return;
      }
    }

    // 🌟 情境 2: 編輯器頁面 (script.google.com/home/projects/.../edit)
    if (url.indexOf('/projects/') !== -1) {
      // 檢查是否彈出了「新增部署作業」對話框
      var webAppOption = findElementByText('div, span, button', ['網頁應用程式', 'Web app']);
      var deploySubmitBtn = findElementByText('button, [role="button"]', ['部署', 'Deploy']);
      var anyoneOption = findElementByText('div, span, [role="option"]', ['所有人', 'Anyone']);

      // 檢查是否已取得 Web App 網址 (/exec)
      var execInput = Array.from(document.querySelectorAll('input, [role="textbox"]')).find(function(inp) {
        var v = inp.value || inp.innerText || '';
        return v.indexOf('/macros/s/') !== -1 && v.indexOf('/exec') !== -1;
      });

      if (execInput) {
        highlightElement(
          execInput,
          '步驟 4 / 4 · 完成部署！',
          '🎉 複製此處 Web App 網址',
          '恭喜部署成功！請點擊複製此網址（結尾為 /exec），然後切回 SMU 軟體貼上並完成開房！',
          function() {
            if (navigator.clipboard) {
              navigator.clipboard.writeText(execInput.value || execInput.innerText);
              alert('✅ 網址已複製至剪貼簿！請切回 SMU 貼上完成開房！');
            }
          }
        );
        return;
      }

      // 如果部署對話框已開啟
      var deployDialog = document.querySelector('[role="dialog"]');
      if (deployDialog) {
        // 若看到「誰可以存取」但尚未選所有人
        var accessSelect = findElementByText('div[role="combobox"], [aria-haspopup="listbox"], button', ['僅限我', 'Only myself', '誰可以存取']);
        if (accessSelect) {
          highlightElement(
            accessSelect,
            '步驟 3 / 4 · 關鍵權限設定',
            '⚠️ 誰可以存取：必須選【所有人】',
            '非常重要！必須將存取權限設為「所有人 (Anyone)」，隊友進入房間時才能免登入直接下載 Manifest 與 Lua 整合包！',
            function() {
              accessSelect.click();
            }
          );
          return;
        }

        // 高亮部署對話框底部的藍色【部署】按鈕
        var dialogDeployBtn = Array.from(deployDialog.querySelectorAll('button')).find(function(b) {
          var t = (b.innerText || '').trim();
          return t === '部署' || t === 'Deploy';
        });
        if (dialogDeployBtn) {
          highlightElement(
            dialogDeployBtn,
            '步驟 3 / 4 · 確認發布',
            '點擊「部署」確認發布',
            '點擊後 Google 會產生專屬的 Web App 下載網址，首次使用若彈出授權請點擊【允許】。',
            function() {
              dialogDeployBtn.click();
            }
          );
          return;
        }
      }

      // 檢查是否已開啟頂部部署選單 (新增部署作業)
      var newDeployItem = findElementByText('[role="menuitem"], div, span', ['新增部署作業', 'New deployment']);
      if (newDeployItem) {
        highlightElement(
          newDeployItem,
          '步驟 2 / 4 · 選擇類型',
          '點擊【新增部署作業】',
          '點擊以開啟 Web App 設定面板。',
          function() {
            newDeployItem.click();
          }
        );
        return;
      }

      // 預設高亮頂部藍色【部署】按鈕
      var topDeployBtn = Array.from(document.querySelectorAll('button, [role="button"]')).find(function(b) {
        var t = (b.innerText || '').trim();
        return (t === '部署' || t === 'Deploy') && b.offsetParent !== null;
      });
      if (topDeployBtn) {
        highlightElement(
          topDeployBtn,
          '步驟 2 / 4 · 貼上腳本後部署',
          '點擊右上角【部署】➔【新增部署作業】',
          '確保編輯器代碼已全選清空並貼上 SMU 腳本，接著點擊此處藍色【部署】按鈕！',
          function() {
            topDeployBtn.click();
          }
        );
        return;
      }
    }
  }

  // 初次執行與持續觀察
  setTimeout(checkAndGuide, 800);
  setInterval(checkAndGuide, 2500);

})();
