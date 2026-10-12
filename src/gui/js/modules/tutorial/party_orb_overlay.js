/**
 * Steam Manifest Updater - 組隊教學 賽博動態字體與極致光效選擇小卡 (Kinetic Typography & Radiant Light FX Highlight Cards)
 * 
 * 🚀 原地漸顯/漸消、極致小卡高亮，完全維持底層圖一畫面：
 *  1. 【全景透光毛玻璃背景】(Transparent Frosted Backdrop - 保持圖一畫面可見)
 *     - 底層圖一粉嫩首頁與原卡片完全可見，底層三卡片平滑漸消虛化，完美烘托浮層高亮小卡。
 * 
 *  2. 【小卡極致高亮與漸顯漸消】(Fade-In / Fade-Out & Vibrant Neon Glow)
 *     - 小卡尺寸比照圖一卡片 (320px x 490px)，具備 2.5px 電光青藍 / 霓虹紫粉高亮邊框與外光暈。
 *     - 登場如絲般順滑漸顯 (cardEntrance)，退場平滑漸消，底層畫面無縫復原。
 * 
 *  3. 【全新專業級 Web Audio UI 音效系統】(Crystal Chimes & Harmonic Arpeggios)
 *     - hover: 水晶微觸敲擊水滴音 (Crystal Chime Tap) - 雙頻清脆諧波，空靈悅耳！
 *     - launch: 輝煌大三和弦躍遷琶音 (Majestic Harmonic Fanfare) - 升騰開闊，極具成就感！
 *     - entrance: 全息展屏舒緩空靈音 (Holographic Shimmer Bloom) - 溫潤和音，烘托漸顯氛圍！
 *     - close: 柔和退場滑降微風 (Gentle Dismiss Breeze) - 乾淨俐落！
 */

(function(window) {
  'use strict';

  var overlayEl = null;
  var _isOverlayVisible = false;

  /**
   * 🌟 專業級 Web Audio UI 音效系統 (純淨、清脆、高級和弦質感)
   */
  function playResonanceSound(type) {
    if (typeof window.playTutorialSound === 'function') {
      window.playTutorialSound(type);
      return;
    }
    try {
      var AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      if (!window._smuTutorialAudioCtx) window._smuTutorialAudioCtx = new AudioCtx();
      var ctx = window._smuTutorialAudioCtx;
      if (ctx.state === 'suspended') ctx.resume();

      var now = ctx.currentTime;

      if (type === 'hover') {
        // 💧 水晶微觸輕響 (Crystal Chime Tap: E6 1318.5Hz + A6 1760Hz 諧波)
        var osc1 = ctx.createOscillator();
        var osc2 = ctx.createOscillator();
        var filter = ctx.createBiquadFilter();
        var gain = ctx.createGain();

        filter.type = 'bandpass';
        filter.frequency.setValueAtTime(1600, now);
        filter.Q.setValueAtTime(3.5, now);

        osc1.type = 'sine';
        osc1.frequency.setValueAtTime(1318.51, now);
        osc1.frequency.exponentialRampToValueAtTime(1396.91, now + 0.05);

        osc2.type = 'sine';
        osc2.frequency.setValueAtTime(1760.00, now);

        gain.gain.setValueAtTime(0.001, now);
        gain.gain.linearRampToValueAtTime(0.025, now + 0.005);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.065);

        osc1.connect(filter);
        osc2.connect(filter);
        filter.connect(gain);
        gain.connect(ctx.destination);

        osc1.start(now);
        osc2.start(now);
        osc1.stop(now + 0.07);
        osc2.stop(now + 0.07);

      } else if (type === 'launch') {
        // ✨ 輝煌大三和弦躍遷琶音 (Majestic Harmonic Fanfare: C5 -> E5 -> G5 -> C6 -> E6)
        var notes = [523.25, 659.25, 783.99, 1046.50, 1318.51];
        notes.forEach(function(freq, index) {
          var t = now + index * 0.026;
          var osc = ctx.createOscillator();
          var filter = ctx.createBiquadFilter();
          var gain = ctx.createGain();

          filter.type = 'lowpass';
          filter.frequency.setValueAtTime(1800, t);
          filter.frequency.exponentialRampToValueAtTime(3600, t + 0.15);

          osc.type = index === 0 ? 'triangle' : 'sine';
          osc.frequency.setValueAtTime(freq, t);

          gain.gain.setValueAtTime(0.001, t);
          gain.gain.linearRampToValueAtTime(0.045, t + 0.008);
          gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.32);

          osc.connect(filter);
          filter.connect(gain);
          gain.connect(ctx.destination);

          osc.start(t);
          osc.stop(t + 0.33);
        });

      } else if (type === 'entrance') {
        // 🌸 全息展屏舒緩空靈音 (Holographic Shimmer Bloom: D5 587.3Hz + A5 880Hz 溫潤和音)
        [587.33, 880.00].forEach(function(freq, i) {
          var osc = ctx.createOscillator();
          var gain = ctx.createGain();
          osc.type = 'sine';
          osc.frequency.setValueAtTime(freq, now);

          gain.gain.setValueAtTime(0.001, now);
          gain.gain.linearRampToValueAtTime(0.028, now + 0.08);
          gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.38);

          osc.connect(gain);
          gain.connect(ctx.destination);

          osc.start(now);
          osc.stop(now + 0.4);
        });

      } else if (type === 'close') {
        // 🍃 柔和退場滑降微風 (Gentle Dismiss Breeze)
        var osc = ctx.createOscillator();
        var gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(783.99, now);
        osc.frequency.exponentialRampToValueAtTime(523.25, now + 0.12);

        gain.gain.setValueAtTime(0.02, now);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.13);

        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.start(now);
        osc.stop(now + 0.14);
      }
    } catch (e) {}
  }

  /**
   * 為卡片綁定 3D 視差傾角互動 (Interactive 3D Tilt & Parallax Physics)
   */
  function attachCardTiltPhysics(cardEl, typoWatermarkEl, auroraGlowEl) {
    if (!cardEl) return;

    var handleMouseMove = function(e) {
      var rect = cardEl.getBoundingClientRect();
      var x = e.clientX - rect.left;
      var y = e.clientY - rect.top;
      var centerX = rect.width / 2;
      var centerY = rect.height / 2;

      // 柔和光暈跟隨游標微動 (不使用 3D 旋轉傾斜)
      if (auroraGlowEl) {
        var glowX = ((x - centerX) / centerX) * 20;
        var glowY = ((y - centerY) / centerY) * 20;
        auroraGlowEl.style.transform = 'translate(calc(-50% + ' + glowX.toFixed(1) + 'px), calc(-50% + ' + glowY.toFixed(1) + 'px)) scale(1.15)';
      }
    };

    var handleMouseLeave = function() {
      if (auroraGlowEl) {
        auroraGlowEl.style.transform = 'translate(-50%, -50%) scale(0.9)';
      }
    };

    cardEl.addEventListener('mousemove', handleMouseMove);
    cardEl.addEventListener('mouseleave', handleMouseLeave);
  }

  /**
   * 構建純字體排版與極致科技光效 DOM 結構 (完全維持圖一背景)
   */
  function buildOverlayDom() {
    if (overlayEl && overlayEl.parentNode) {
      overlayEl.parentNode.removeChild(overlayEl);
    }

    overlayEl = document.createElement('div');
    overlayEl.id = 'tutorial-party-orb-overlay';
    overlayEl.className = 'party-orb-overlay';
    overlayEl.innerHTML = `
      <!-- 右上角高亮關閉圓鈕 -->
      <button class="party-orb-close-btn" id="party-orb-close-btn" title="關閉組隊選項，返回教學首頁">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
          <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
        </svg>
      </button>

      <div class="party-orb-content">
        <!-- 🌟 雙向教學極致高亮小卡舞台區 -->
        <div class="typo-radiant-stage">

          <!-- 🔵 左側小卡：入隊教學 (SQUAD AGENT) -->
          <div class="typo-card card-join" id="card-join" tabindex="0" role="button" data-role="party-join">
            <div class="card-laser-border"></div>
            <div class="card-glow-aurora" id="glow-join"></div>

            <!-- 超大動態英文字體水印 (下沉於右下方作為深邃暗紋) -->
            <div class="bg-kinetic-typo" id="watermark-join">JOIN</div>

            <!-- 卡片核心內容排版 -->
            <div class="typo-card-content">
              <div>
                <!-- 頂部身分標籤列 -->
                <div class="typo-protocol-row">
                  <div class="typo-role-tag">
                    <span class="role-tag-dot"></span>
                    <span>隊員身分 · 加入隊伍</span>
                  </div>
                  <span class="typo-step-badge">STEP 01</span>
                </div>

                <!-- 核心動態字體主標題 -->
                <div class="typo-title-section">
                  <h3 class="typo-hero-title">
                    <span class="text-char">入</span>
                    <span class="text-char">隊</span>
                    <span class="text-char">教</span>
                    <span class="text-char">學</span>
                  </h3>
                  <p class="typo-subtitle">獲取隊長發佈的房間邀請碼，快速加入小隊並完成連線設定</p>
                </div>

                <!-- 終端特性矩陣 -->
                <div class="typo-feature-list">
                  <div class="typo-feature-item">
                    <span class="typo-feature-icon">✦</span>
                    <span>輸入或粘貼房間邀請代碼</span>
                  </div>
                  <div class="typo-feature-item">
                    <span class="typo-feature-icon">✦</span>
                    <span>實時解析隊長主機連線通道</span>
                  </div>
                  <div class="typo-feature-item">
                    <span class="typo-feature-icon">✦</span>
                    <span>隊員身份免複雜設定一鍵入隊</span>
                  </div>
                </div>
              </div>

              <!-- 底部啟動光效膠囊按鈕 -->
              <button class="typo-launch-btn" id="btn-launch-join">
                <span>進入入隊教學</span>
                <span class="btn-arrow">➔</span>
              </button>
            </div>
          </div>

          <!-- 🟣 右側小卡：開房教學 (FLEET COMMANDER) -->
          <div class="typo-card card-host" id="card-host" tabindex="0" role="button" data-role="party-host">
            <div class="card-laser-border"></div>
            <div class="card-glow-aurora" id="glow-host"></div>

            <!-- 超大動態英文字體水印 (下沉於右下方作為深邃暗紋) -->
            <div class="bg-kinetic-typo" id="watermark-host">HOST</div>

            <!-- 卡片核心內容排版 -->
            <div class="typo-card-content">
              <div>
                <!-- 頂部身分標籤列 -->
                <div class="typo-protocol-row">
                  <div class="typo-role-tag">
                    <span class="role-tag-dot"></span>
                    <span>房主身分 · 創建房間</span>
                  </div>
                  <span class="typo-step-badge">STEP 02</span>
                </div>

                <!-- 核心動態字體主標題 -->
                <div class="typo-title-section">
                  <h3 class="typo-hero-title">
                    <span class="text-char">開</span>
                    <span class="text-char">房</span>
                    <span class="text-char">教</span>
                    <span class="text-char">學</span>
                  </h3>
                  <p class="typo-subtitle">建立並主持多人在線房間，生成專屬邀請碼並指揮隊伍入庫</p>
                </div>

                <!-- 終端特性矩陣 -->
                <div class="typo-feature-list">
                  <div class="typo-feature-item">
                    <span class="typo-feature-icon">★</span>
                    <span>自訂房間名稱與密碼配置</span>
                  </div>
                  <div class="typo-feature-item">
                    <span class="typo-feature-icon">★</span>
                    <span>生成小隊專屬連線邀請碼</span>
                  </div>
                  <div class="typo-feature-item">
                    <span class="typo-feature-icon">★</span>
                    <span>掌握房主主持權限與成員管理</span>
                  </div>
                </div>
              </div>

              <!-- 底部啟動光效膠囊按鈕 -->
              <button class="typo-launch-btn" id="btn-launch-host">
                <span>進入開房教學</span>
                <span class="btn-arrow">➔</span>
              </button>
            </div>
          </div>

        </div>

        <!-- 底部返回卡片一覽按鈕 -->
        <div class="party-orb-footer-action">
          <button class="party-orb-cancel-btn" id="party-orb-cancel-btn">
            ✕ 返回卡片一覽
          </button>
        </div>
      </div>
    `;

    document.body.appendChild(overlayEl);

    // 點擊背景遮罩空白處自動退場漸消
    overlayEl.onclick = function(e) {
      if (e.target === overlayEl) {
        hideOverlay();
      }
    };

    // 關閉與返回按鈕
    var closeBtn = overlayEl.querySelector('#party-orb-close-btn');
    var cancelBtn = overlayEl.querySelector('#party-orb-cancel-btn');
    if (closeBtn) closeBtn.onclick = hideOverlay;
    if (cancelBtn) cancelBtn.onclick = hideOverlay;

    // 綁定左小卡 (入隊教學)
    var cardJoin = overlayEl.querySelector('#card-join');
    var watermarkJoin = overlayEl.querySelector('#watermark-join');
    var glowJoin = overlayEl.querySelector('#glow-join');
    var btnJoin = overlayEl.querySelector('#btn-launch-join');
    if (cardJoin) {
      attachCardTiltPhysics(cardJoin, watermarkJoin, glowJoin);
      cardJoin.onmouseenter = function() {
        playResonanceSound('hover');
      };
      var triggerJoin = function(e) {
        e.preventDefault();
        e.stopPropagation();
        cardJoin.classList.add('launching');
        launchPartyPipeline('party-join');
      };
      cardJoin.onclick = triggerJoin;
      if (btnJoin) btnJoin.onclick = triggerJoin;
    }

    // 綁定右小卡 (開房教學)
    var cardHost = overlayEl.querySelector('#card-host');
    var watermarkHost = overlayEl.querySelector('#watermark-host');
    var glowHost = overlayEl.querySelector('#glow-host');
    var btnHost = overlayEl.querySelector('#btn-launch-host');
    if (cardHost) {
      attachCardTiltPhysics(cardHost, watermarkHost, glowHost);
      cardHost.onmouseenter = function() {
        playResonanceSound('hover');
      };
      var triggerHost = function(e) {
        e.preventDefault();
        e.stopPropagation();
        cardHost.classList.add('launching');
        launchPartyPipeline('party-host');
      };
      cardHost.onclick = triggerHost;
      if (btnHost) btnHost.onclick = triggerHost;
    }

    // ESC 鍵關閉
    window.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && _isOverlayVisible) {
        hideOverlay();
      }
    });

    return overlayEl;
  }

  /**
   * 啟動教學管道並平滑過渡跳轉至組隊大廳教學 (零延遲、保證切換至 party 頁面)
   */
  function launchPartyPipeline(role) {
    playResonanceSound('launch');

    // 🌟 教學沙盒保護：第一時間標記教學進行中
    window.__tutorialMockPartyActive = true;

    if (overlayEl) {
      overlayEl.style.pointerEvents = 'none';
      overlayEl.classList.remove('active');
      overlayEl.classList.add('fading-out');
    }

    try {
      localStorage.removeItem('smu_tutorial_role');
    } catch(e) {}

    // 🌟 立即切換頁面至組隊大廳，絕不讓使用者停留在教學首頁
    if (window.switchPage) {
      window.switchPage('party');
    }

    // 隱藏覆蓋層 (不播放關閉音效)
    _isOverlayVisible = false;
    setTimeout(function() {
      if (overlayEl) {
        overlayEl.style.display = 'none';
        overlayEl.classList.remove('fading-out');
      }
      var cardsGrid = document.querySelector('.tutorial-cards-grid');
      if (cardsGrid) {
        cardsGrid.classList.remove('cards-dimmed-behind');
      }
    }, 240);

    // 🌟 啟動對應教學 Pipeline (附帶健壯的輪詢容錯)
    function triggerPipeline() {
      if (role === 'party-join') {
        if (window.PartyJoinPipeline && typeof window.PartyJoinPipeline.start === 'function') {
          window.PartyJoinPipeline.start();
        } else {
          setTimeout(triggerPipeline, 40);
        }
      } else if (role === 'party-host') {
        if (window.PartyHostPipeline && typeof window.PartyHostPipeline.start === 'function') {
          window.PartyHostPipeline.start();
        } else {
          setTimeout(triggerPipeline, 40);
        }
      }
    }

    setTimeout(triggerPipeline, 80);
  }

  /**
   * 顯示選擇小卡 (漸顯動畫 + 底層畫面維持可見 + 底層卡片柔和虛化)
   */
  function showOverlay() {
    buildOverlayDom();
    _isOverlayVisible = true;

    // 🌟 底層圖一的卡片列表平滑虛化漸消，全力凸顯浮層小卡
    var cardsGrid = document.querySelector('.tutorial-cards-grid');
    if (cardsGrid) {
      cardsGrid.classList.add('cards-dimmed-behind');
    }

    overlayEl.style.display = 'flex';
    overlayEl.style.pointerEvents = 'auto';
    overlayEl.classList.remove('fading-out');

    // 🌟 強制 Reflow，確保瀏覽器完全捕獲從初始隱藏到 active 的進場動畫過渡
    void overlayEl.offsetWidth;

    requestAnimationFrame(function() {
      if (overlayEl) overlayEl.classList.add('active');
    });

    playResonanceSound('entrance');
  }

  /**
   * 隱藏並關閉選擇小卡 (漸消動畫 + 底層卡片復原)
   */
  function hideOverlay() {
    if (!_isOverlayVisible) return;
    _isOverlayVisible = false;

    playResonanceSound('close');

    // 🌟 底層圖一的卡片列表平滑漸顯復原
    var cardsGrid = document.querySelector('.tutorial-cards-grid');
    if (cardsGrid) {
      cardsGrid.classList.remove('cards-dimmed-behind');
    }

    if (overlayEl) {
      overlayEl.classList.remove('active');
      overlayEl.classList.add('fading-out');
      setTimeout(function() {
        if (!_isOverlayVisible && overlayEl) {
          overlayEl.style.display = 'none';
          overlayEl.style.pointerEvents = 'none';
          overlayEl.classList.remove('fading-out');
        }
      }, 260);
    }
  }

  // 對外暴露全域 API
  window.openPartyOrbSelection = showOverlay;
  window.PartyOrbOverlay = {
    show: showOverlay,
    hide: hideOverlay
  };

})(window);
