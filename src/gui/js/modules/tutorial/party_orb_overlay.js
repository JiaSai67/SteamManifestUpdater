/**
 * Steam Manifest Updater - 組隊教學 賽博動態字體與極致光效選擇層 (Kinetic Typography & Radiant Light FX Portal)
 * 
 * 🚀 全面取消 3D 球體與星核設計，轉型為極致 3A 賽博動態字體排版與科技光效門戶：
 * 
 *  1. 【全景大氣科技光效】(Atmospheric Cyber Light FX)
 *     - 雙向透視動態極光光束 (Ambient Aurora Beams)，左青藍、右粉紫柔和呼吸交織。
 *     - 3D 透視深度科技網格 (Perspective Cyber Grid Floor)，營造無垠深度空間。
 * 
 *  2. 【動態字體排版系統】(Kinetic Typography System)
 *     - 超大動態英文字體水印 (Giant Monospaced Watermark: "JOIN" / "HOST")，懸浮透視浮動。
 *     - 核心中文主標題字符獨立動態 (Hero Char Staggering: "入隊教學" / "開房教學")。
 *     - 全光譜霓虹流光掃掠與多重螢光投影 (Shimmer Sweep & Radiant Glow Projection)。
 * 
 *  3. 【旋轉激光導軌與能量護盾】(Radiant Laser Trail & Border Shield)
 *     - 360° 動態旋轉漸層激光邊框 (Conic Laser Border Orbit)。
 *     - 放射狀底層極光光暈 (Backdrop Aurora Flare)。
 * 
 *  4. 【3D 物理視差懸浮傾角】(Interactive 3D Card Tilt & Parallax Physics)
 *     - 游標動態計算 RotateX / RotateY 空間傾角，卡片、水印、光暈產生差分深度視差。
 * 
 *  5. 【超光速進入過渡】(Hyperdrive Launch Burst)
 *     - 點擊時字體與邊框白熾強光爆發，平滑呼叫 PartyJoinPipeline / PartyHostPipeline。
 */

(function(window) {
  'use strict';

  var overlayEl = null;
  var _isOverlayVisible = false;

  /**
   * 輕量級 Web Audio 合成音效 (無需依賴外部音訊資源)
   */
  function playResonanceSound(type) {
    try {
      var AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      if (!window._smuTutorialAudioCtx) window._smuTutorialAudioCtx = new AudioCtx();
      var ctx = window._smuTutorialAudioCtx;
      if (ctx.state === 'suspended') ctx.resume();

      var now = ctx.currentTime;
      var osc = ctx.createOscillator();
      var gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);

      if (type === 'hover') {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(587.33, now);
        osc.frequency.exponentialRampToValueAtTime(1174.66, now + 0.12);
        gain.gain.setValueAtTime(0.035, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);
        osc.start(now);
        osc.stop(now + 0.15);
      } else if (type === 'launch') {
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(329.63, now);
        osc.frequency.exponentialRampToValueAtTime(880, now + 0.18);
        osc.frequency.exponentialRampToValueAtTime(1760, now + 0.38);
        gain.gain.setValueAtTime(0.075, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.45);
        osc.start(now);
        osc.stop(now + 0.45);
      } else if (type === 'entrance') {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(440, now);
        osc.frequency.exponentialRampToValueAtTime(659.25, now + 0.28);
        gain.gain.setValueAtTime(0.04, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
        osc.start(now);
        osc.stop(now + 0.35);
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

      // 計算傾角 (-12deg ~ +12deg)
      var rotateX = ((y - centerY) / centerY) * -11;
      var rotateY = ((x - centerX) / centerX) * 11;

      cardEl.style.transform = 'perspective(1000px) rotateX(' + rotateX.toFixed(2) + 'deg) rotateY(' + rotateY.toFixed(2) + 'deg) translateY(-8px) scale(1.02)';

      // 背景超大英文字母水印反向位移，營造三維深度感
      if (typoWatermarkEl) {
        var moveX = ((x - centerX) / centerX) * -16;
        var moveY = ((y - centerY) / centerY) * -12;
        typoWatermarkEl.style.transform = 'translate(' + moveX.toFixed(1) + 'px, ' + moveY.toFixed(1) + 'px) scale(1.04)';
      }

      // 極光跟隨游標微動
      if (auroraGlowEl) {
        var glowX = ((x - centerX) / centerX) * 22;
        var glowY = ((y - centerY) / centerY) * 22;
        auroraGlowEl.style.transform = 'translate(calc(-50% + ' + glowX.toFixed(1) + 'px), calc(-50% + ' + glowY.toFixed(1) + 'px)) scale(1.25)';
      }
    };

    var handleMouseLeave = function() {
      cardEl.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg) translateY(0px) scale(1)';
      if (typoWatermarkEl) {
        typoWatermarkEl.style.transform = 'translate(0px, 0px) scale(1)';
      }
      if (auroraGlowEl) {
        auroraGlowEl.style.transform = 'translate(-50%, -50%) scale(0.85)';
      }
    };

    cardEl.addEventListener('mousemove', handleMouseMove);
    cardEl.addEventListener('mouseleave', handleMouseLeave);
  }

  /**
   * 構建純字體排版與極致科技光效 DOM 結構 (完全無球體)
   */
  function buildOverlayDom() {
    if (overlayEl && overlayEl.parentNode) {
      overlayEl.parentNode.removeChild(overlayEl);
    }

    overlayEl = document.createElement('div');
    overlayEl.id = 'tutorial-party-orb-overlay';
    overlayEl.className = 'party-orb-overlay entrance-warp';
    overlayEl.innerHTML = `
      <!-- 全景大氣背景流光與科技空間網格 -->
      <div class="typo-ambient-backdrop">
        <div class="ambient-beam-left"></div>
        <div class="ambient-beam-right"></div>
        <div class="cyber-grid-floor"></div>
      </div>

      <!-- 全息終端 HUD 四角科技括號 -->
      <div class="party-orb-hud-bracket bracket-tl"></div>
      <div class="party-orb-hud-bracket bracket-tr"></div>
      <div class="party-orb-hud-bracket bracket-bl"></div>
      <div class="party-orb-hud-bracket bracket-br"></div>

      <!-- 右上角高亮關閉圓鈕 -->
      <button class="party-orb-close-btn" id="party-orb-close-btn" title="關閉組隊選項，返回教學首頁">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
          <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
        </svg>
      </button>

      <div class="party-orb-content">
        <!-- 頂部高亮標題列 -->
        <div class="party-orb-header">
          <div class="party-orb-badge">
            <span class="badge-dot"></span>
            <span>MULTIPLAYER // DUAL SELECTION PROTOCOL</span>
          </div>
          <h2 class="party-orb-title">選擇您的組隊教學旅程</h2>
          <p class="party-orb-subtitle">選擇受邀加入現有小隊，或是作為房主建立房間並邀請隊員</p>
        </div>

        <!-- 🌟 雙向教學極致字體光效舞台區 -->
        <div class="typo-radiant-stage">

          <!-- 🔵 左側卡片：入隊教學 (SQUAD AGENT) -->
          <div class="typo-card card-join" id="card-join" tabindex="0" role="button" data-role="party-join">
            <!-- 旋轉激光邊框與極光光暈 -->
            <div class="card-laser-border"></div>
            <div class="card-glow-aurora" id="glow-join"></div>

            <!-- 超大動態英文字體水印 -->
            <div class="bg-kinetic-typo" id="watermark-join">JOIN</div>

            <!-- 卡片核心內容排版 -->
            <div class="typo-card-content">
              <div>
                <!-- 頂部協議小標籤 -->
                <div class="typo-protocol-row">
                  <div class="typo-protocol-badge">
                    <span class="badge-pulse-dot"></span>
                    <span>PROTOCOL // SQUAD_RECEPTOR</span>
                  </div>
                  <span class="typo-index-num">01 / DUAL</span>
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

          <!-- 🟣 右側卡片：開房教學 (FLEET COMMANDER) -->
          <div class="typo-card card-host" id="card-host" tabindex="0" role="button" data-role="party-host">
            <!-- 旋轉激光邊框與極光光暈 -->
            <div class="card-laser-border"></div>
            <div class="card-glow-aurora" id="glow-host"></div>

            <!-- 超大動態英文字體水印 -->
            <div class="bg-kinetic-typo" id="watermark-host">HOST</div>

            <!-- 卡片核心內容排版 -->
            <div class="typo-card-content">
              <div>
                <!-- 頂部協議小標籤 -->
                <div class="typo-protocol-row">
                  <div class="typo-protocol-badge">
                    <span class="badge-pulse-dot"></span>
                    <span>PROTOCOL // FLEET_COMMANDER</span>
                  </div>
                  <span class="typo-index-num">02 / DUAL</span>
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

    // 關閉與返回按鈕
    var closeBtn = overlayEl.querySelector('#party-orb-close-btn');
    var cancelBtn = overlayEl.querySelector('#party-orb-cancel-btn');
    if (closeBtn) closeBtn.onclick = hideOverlay;
    if (cancelBtn) cancelBtn.onclick = hideOverlay;

    // 綁定左卡 (入隊教學)
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

    // 綁定右卡 (開房教學)
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
   * 啟動教學管道並平滑過渡關閉選擇層
   */
  function launchPartyPipeline(role) {
    playResonanceSound('launch');

    if (overlayEl) {
      overlayEl.style.pointerEvents = 'none';
      overlayEl.classList.remove('active');
      overlayEl.classList.add('fading-out');
    }

    try {
      localStorage.removeItem('smu_tutorial_role');
    } catch(e) {}

    setTimeout(function() {
      hideOverlay();

      if (role === 'party-join') {
        if (window.PartyJoinPipeline && typeof window.PartyJoinPipeline.start === 'function') {
          window.PartyJoinPipeline.start();
        } else if (typeof tt === 'function') {
          tt('🚀 正在載入入隊教學流程…', 'info');
        }
      } else if (role === 'party-host') {
        if (window.PartyHostPipeline && typeof window.PartyHostPipeline.start === 'function') {
          window.PartyHostPipeline.start();
        } else if (typeof tt === 'function') {
          tt('🚀 正在載入開房教學流程…', 'info');
        }
      }
    }, 280);
  }

  /**
   * 顯示選擇層
   */
  function showOverlay() {
    buildOverlayDom();
    _isOverlayVisible = true;

    overlayEl.style.display = 'flex';
    overlayEl.style.pointerEvents = 'auto';
    overlayEl.classList.remove('fading-out');
    overlayEl.classList.add('active');

    playResonanceSound('entrance');
  }

  /**
   * 隱藏並關閉選擇層
   */
  function hideOverlay() {
    _isOverlayVisible = false;
    if (overlayEl) {
      overlayEl.classList.remove('active');
      overlayEl.classList.remove('fading-out');
      overlayEl.style.display = 'none';
      overlayEl.style.pointerEvents = 'none';
    }
  }

  // 對外暴露全域 API
  window.openPartyOrbSelection = showOverlay;
  window.PartyOrbOverlay = {
    show: showOverlay,
    hide: hideOverlay
  };

})(window);
