/**
 * Steam Manifest Updater - 組隊教學 3D 全息星核選擇層 (Three.js WebGL 3A 旗艦旗艦版)
 * 1:1 完美還原 Gemini_Generated_Image_m2o88sm2o88sm2o8.jpg 概念圖：
 * 
 * 🔵 左星核 (PROTOCOL // SQUAD JOIN):
 *  1. 外層全息護盾球罩 (Hologram Dotted Grid Shell) + 菲涅爾邊緣泛光 + 懸浮 HUD 狀態刻度標籤
 *  2. 陀螺儀高階 HUD 軌道系統 (Multi-axis Segmented HUD Gimbal Rings) 帶有精密刻度表、分段圓弧、虛線軌跡與巡航發光節點
 *  3. 核心經緯數位點雲地球儀 (Cyber Dotted Matrix Globe) 搭配右上角專屬高密度矩陣方塊數據簇
 *  4. 內層翻滾有機電漿星雲核心 (Swirling Organic Plasma Fluid Nebula) 雙層逆向旋轉流體煙霧
 *  5. 360 度向外漂浮散逸的懸浮極光星塵與微光碎屑
 * 
 * 🟣 右星核 (PROTOCOL // SQUAD HOST):
 *  1. 宇宙流體深空螺旋漩渦 (Deep Space Swirling Cosmic Vortex) 多層對數螺旋流體盤與立體旋臂
 *  2. 中心極致引力奇點與星芒光爆 (Singularity Core with Radiant Cross Starburst Flare)
 *  3. 多重傾角的霓虹紫紅 HUD 軌道環 (Neon Magenta HUD Gyroscopic Rings) 帶精密刻度與瞄準標記
 *  4. 沿螺旋旋臂向中心匯聚的動態流動紫晶星塵粒子群
 * 
 * 🎮 3A 互動體驗:
 *  - 滑鼠 3D 視差傾角互動 (Mouse Parallax 3D Tilt)，懸浮感知極強
 *  - 懸停平滑加速與能量共振脈動 (Energy Surge + Web Audio Synthesis)
 *  - 420px 畫布拉闊防邊界裁切，60 FPS 頂級流暢度
 */

(function(window) {
  'use strict';

  var overlayEl = null;
  var _joinThreeApp = null;
  var _hostThreeApp = null;
  var _isOverlayVisible = false;

  /**
   * 輕量級 Web Audio 合成音效
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
        osc.frequency.setValueAtTime(659.25, now);
        osc.frequency.exponentialRampToValueAtTime(1046.5, now + 0.15);
        gain.gain.setValueAtTime(0.035, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.18);
        osc.start(now);
        osc.stop(now + 0.18);
      } else if (type === 'launch') {
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(440, now);
        osc.frequency.exponentialRampToValueAtTime(880, now + 0.2);
        osc.frequency.exponentialRampToValueAtTime(1760, now + 0.45);
        gain.gain.setValueAtTime(0.08, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.5);
        osc.start(now);
        osc.stop(now + 0.5);
      } else if (type === 'entrance') {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(329.63, now);
        osc.frequency.exponentialRampToValueAtTime(587.33, now + 0.35);
        gain.gain.setValueAtTime(0.04, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.45);
        osc.start(now);
        osc.stop(now + 0.45);
      }
    } catch (e) {}
  }

  /* ==========================================================================
     🎨 高精細程序化 3A 紋理生成引擎 (Procedural Texture Engine)
     ========================================================================== */

  /**
   * 1. 建立高斯羽化微光星塵紋理
   */
  function createStardustTexture() {
    var canvas = document.createElement('canvas');
    canvas.width = 64;
    canvas.height = 64;
    var ctx = canvas.getContext('2d');
    var grad = ctx.createRadialGradient(32, 32, 0, 32, 32, 30);
    grad.addColorStop(0, 'rgba(255, 255, 255, 1)');
    grad.addColorStop(0.18, 'rgba(255, 255, 255, 0.9)');
    grad.addColorStop(0.45, 'rgba(255, 255, 255, 0.35)');
    grad.addColorStop(0.75, 'rgba(255, 255, 255, 0.08)');
    grad.addColorStop(1, 'rgba(255, 255, 255, 0)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(32, 32, 30, 0, Math.PI * 2);
    ctx.fill();

    var tex = new THREE.CanvasTexture(canvas);
    tex.generateMipmaps = false;
    tex.minFilter = THREE.LinearFilter;
    tex.magFilter = THREE.LinearFilter;
    tex.needsUpdate = true;
    return tex;
  }

  /**
   * 2. 建立右星核專屬：中心十字星芒奇點光暈 (Cross Starburst Flare)
   */
  function createCrossStarburstTexture() {
    var canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 256;
    var ctx = canvas.getContext('2d');
    var cx = 128;
    var cy = 128;

    ctx.clearRect(0, 0, 256, 256);

    // 寬柔和圓形外暈
    var gSoft = ctx.createRadialGradient(cx, cy, 0, cx, cy, 110);
    gSoft.addColorStop(0, 'rgba(255, 255, 255, 0.95)');
    gSoft.addColorStop(0.2, 'rgba(255, 130, 200, 0.6)');
    gSoft.addColorStop(0.5, 'rgba(255, 42, 133, 0.2)');
    gSoft.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = gSoft;
    ctx.beginPath();
    ctx.arc(cx, cy, 110, 0, Math.PI * 2);
    ctx.fill();

    // 水平銳利長星芒
    var gH = ctx.createLinearGradient(0, cy, 256, cy);
    gH.addColorStop(0, 'rgba(255, 255, 255, 0)');
    gH.addColorStop(0.35, 'rgba(255, 140, 210, 0.45)');
    gH.addColorStop(0.5, 'rgba(255, 255, 255, 1)');
    gH.addColorStop(0.65, 'rgba(255, 140, 210, 0.45)');
    gH.addColorStop(1, 'rgba(255, 255, 255, 0)');
    ctx.fillStyle = gH;
    ctx.fillRect(8, cy - 2, 240, 4);

    // 垂直銳利長星芒
    var gV = ctx.createLinearGradient(cx, 0, cx, 256);
    gV.addColorStop(0, 'rgba(255, 255, 255, 0)');
    gV.addColorStop(0.35, 'rgba(255, 140, 210, 0.45)');
    gV.addColorStop(0.5, 'rgba(255, 255, 255, 1)');
    gV.addColorStop(0.65, 'rgba(255, 140, 210, 0.45)');
    gV.addColorStop(1, 'rgba(255, 255, 255, 0)');
    ctx.fillStyle = gV;
    ctx.fillRect(cx - 2, 8, 4, 240);

    // 45 度次級斜星芒
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(Math.PI / 4);
    var gD = ctx.createLinearGradient(-80, 0, 80, 0);
    gD.addColorStop(0, 'rgba(255, 255, 255, 0)');
    gD.addColorStop(0.5, 'rgba(255, 255, 255, 0.85)');
    gD.addColorStop(1, 'rgba(255, 255, 255, 0)');
    ctx.fillStyle = gD;
    ctx.fillRect(-80, -1.5, 160, 3);
    ctx.rotate(Math.PI / 2);
    ctx.fillRect(-80, -1.5, 160, 3);
    ctx.restore();

    // 中心白熾核
    var gCore = ctx.createRadialGradient(cx, cy, 0, cx, cy, 18);
    gCore.addColorStop(0, '#FFFFFF');
    gCore.addColorStop(0.5, '#FFE4F0');
    gCore.addColorStop(1, 'rgba(255, 255, 255, 0)');
    ctx.fillStyle = gCore;
    ctx.beginPath();
    ctx.arc(cx, cy, 18, 0, Math.PI * 2);
    ctx.fill();

    var tex = new THREE.CanvasTexture(canvas);
    tex.needsUpdate = true;
    return tex;
  }

  /**
   * 3. 建立左星核專屬：外層全息經緯點陣護盾紋理 (Hologram Dotted Grid Shell)
   */
  function createHologramShellTexture() {
    var canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    var ctx = canvas.getContext('2d');

    ctx.clearRect(0, 0, 512, 512);

    // 經緯細線
    ctx.strokeStyle = 'rgba(0, 245, 255, 0.12)';
    ctx.lineWidth = 1;
    for (var y = 0; y <= 512; y += 32) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(512, y);
      ctx.stroke();
    }
    for (var x = 0; x <= 512; x += 32) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, 512);
      ctx.stroke();
    }

    // 經緯交叉點亮點 (Dotted Grid Lattice)
    ctx.fillStyle = 'rgba(103, 232, 249, 0.45)';
    for (var gx = 0; gx <= 512; gx += 32) {
      for (var gy = 0; gy <= 512; gy += 32) {
        ctx.beginPath();
        ctx.arc(gx, gy, 1.6, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // 左上方懸浮 HUD 遙測數據條 (Telemetry Status Brackets) - 完美還原概念圖左上角細節
    ctx.fillStyle = 'rgba(0, 245, 255, 0.75)';
    ctx.fillRect(36, 40, 72, 3);
    ctx.fillRect(36, 48, 5, 12);
    ctx.fillRect(45, 48, 8, 12);
    ctx.fillRect(57, 48, 14, 12);
    ctx.fillRect(75, 48, 6, 12);
    ctx.fillRect(85, 48, 12, 12);
    ctx.fillRect(101, 48, 7, 12);

    // 小圓形對焦標記
    ctx.strokeStyle = 'rgba(0, 245, 255, 0.65)';
    ctx.beginPath();
    ctx.arc(380, 80, 8, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillRect(379, 75, 2, 10);
    ctx.fillRect(375, 79, 10, 2);

    var tex = new THREE.CanvasTexture(canvas);
    tex.wrapS = THREE.RepeatWrapping;
    tex.wrapT = THREE.ClampToEdgeWrapping;
    tex.repeat.set(2, 1);
    tex.needsUpdate = true;
    return tex;
  }

  /**
   * 4. 建立超高階科幻 HUD 軌道刻度紋理 (Advanced Sci-Fi HUD Gyro Rings)
   *    繪製精密刻度表、分段圓弧、虛線軌跡、狀態槽、瞄準指示箭頭
   */
  function createAdvancedHudRingTexture(theme, variant) {
    var canvas = document.createElement('canvas');
    canvas.width = 1024;
    canvas.height = 128;
    var ctx = canvas.getContext('2d');

    ctx.clearRect(0, 0, 1024, 128);

    var isCyan = theme === 'cyan';
    var cNeon = isCyan ? 'rgba(0, 245, 255, 0.95)' : 'rgba(255, 42, 133, 0.95)';
    var cMid = isCyan ? 'rgba(56, 189, 248, 0.8)' : 'rgba(192, 132, 252, 0.8)';
    var cDim = isCyan ? 'rgba(2, 132, 199, 0.22)' : 'rgba(147, 51, 234, 0.22)';
    var cWhite = 'rgba(255, 255, 255, 0.95)';

    // 底層微光軌道帶
    ctx.fillStyle = cDim;
    ctx.fillRect(0, 20, 1024, 88);

    // 雙導軌外框線
    ctx.strokeStyle = cMid;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(0, 22);
    ctx.lineTo(1024, 22);
    ctx.moveTo(0, 106);
    ctx.lineTo(1024, 106);
    ctx.stroke();

    if (variant === 1) {
      // 樣式 1：主軌道環 - 高密度精密刻度與大分段光弧 (Heavy Segmented HUD Gauge)
      for (var x = 0; x < 1024; x += 4) {
        var isMajor = (x % 64 === 0);
        var isMid = (x % 16 === 0);
        var tickH = isMajor ? 32 : (isMid ? 18 : 8);

        ctx.strokeStyle = isMajor ? cWhite : (isMid ? cNeon : cMid);
        ctx.lineWidth = isMajor ? 2.5 : (isMid ? 1.5 : 1);
        ctx.beginPath();
        ctx.moveTo(x, 24);
        ctx.lineTo(x, 24 + tickH);
        ctx.stroke();

        if (isMajor) {
          // 底部對應刻度標記
          ctx.beginPath();
          ctx.moveTo(x, 104);
          ctx.lineTo(x, 104 - 14);
          ctx.stroke();
        }
      }

      // 3 組大型高亮能量分段弧 (Segmented Arc Blocks)
      var arcSegments = [
        { start: 60, len: 140 },
        { start: 380, len: 180 },
        { start: 720, len: 160 }
      ];
      arcSegments.forEach(function(seg) {
        var grad = ctx.createLinearGradient(seg.start, 0, seg.start + seg.len, 0);
        grad.addColorStop(0, 'rgba(255, 255, 255, 0.3)');
        grad.addColorStop(0.2, cNeon);
        grad.addColorStop(0.8, cNeon);
        grad.addColorStop(1, 'rgba(255, 255, 255, 0.3)');
        ctx.fillStyle = grad;
        ctx.fillRect(seg.start, 62, seg.len, 24);

        // 圓弧白熾高光線
        ctx.strokeStyle = cWhite;
        ctx.lineWidth = 2;
        ctx.strokeRect(seg.start, 62, seg.len, 24);
      });

      // HUD 狀態箭頭與代碼標籤
      ctx.fillStyle = cWhite;
      for (var i = 240; i < 340; i += 22) {
        ctx.beginPath();
        ctx.moveTo(i, 66);
        ctx.lineTo(i + 8, 74);
        ctx.lineTo(i, 82);
        ctx.lineWidth = 2;
        ctx.strokeStyle = cNeon;
        ctx.stroke();
      }

    } else if (variant === 2) {
      // 樣式 2：傾斜次級軌道環 - 虛線軌跡、數位槽與圓孔導軌 (Dashed Track & Gauges)
      ctx.setLineDash([12, 8, 4, 8]);
      ctx.strokeStyle = cNeon;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(0, 64);
      ctx.lineTo(1024, 64);
      ctx.stroke();
      ctx.setLineDash([]);

      // 等距圓形導軌孔
      for (var hx = 20; hx < 1024; hx += 32) {
        ctx.fillStyle = (hx % 96 === 0) ? cWhite : cNeon;
        ctx.beginPath();
        ctx.arc(hx, 40, 3, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.arc(hx, 88, 3, 0, Math.PI * 2);
        ctx.fill();
      }

      // 長條發光槽
      ctx.fillStyle = cNeon;
      for (var sx = 80; sx < 1024; sx += 220) {
        ctx.fillRect(sx, 54, 70, 20);
        ctx.strokeStyle = cWhite;
        ctx.lineWidth = 1.5;
        ctx.strokeRect(sx, 54, 70, 20);
      }

    } else {
      // 樣式 3：外圍超細瞄準標尺環 (Fine Reticle Ring)
      ctx.strokeStyle = cNeon;
      ctx.lineWidth = 1;
      for (var rx = 0; rx < 1024; rx += 8) {
        var rMajor = (rx % 32 === 0);
        ctx.beginPath();
        ctx.moveTo(rx, 50);
        ctx.lineTo(rx, 50 + (rMajor ? 28 : 12));
        ctx.stroke();
      }
    }

    var tex = new THREE.CanvasTexture(canvas);
    tex.wrapS = THREE.RepeatWrapping;
    tex.wrapT = THREE.ClampToEdgeWrapping;
    tex.repeat.set(1, 1);
    tex.needsUpdate = true;
    return tex;
  }

  /**
   * 5. 建立左星核專屬：有機翻滾電漿流體星雲紋理 (Swirling Organic Plasma Fluid Nebula)
   *    繪製多重扭曲電漿煙霧觸鬚、深海湖藍基底與白熾星核
   */
  function createOrganicPlasmaNebulaTexture() {
    var canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    var ctx = canvas.getContext('2d');
    var cx = 256;
    var cy = 256;

    ctx.clearRect(0, 0, 512, 512);

    // 核心漫射底光
    var gBase = ctx.createRadialGradient(cx, cy, 0, cx, cy, 230);
    gBase.addColorStop(0, 'rgba(255, 255, 255, 1)');
    gBase.addColorStop(0.2, 'rgba(0, 245, 255, 0.9)');
    gBase.addColorStop(0.5, 'rgba(14, 165, 233, 0.45)');
    gBase.addColorStop(0.75, 'rgba(2, 132, 199, 0.15)');
    gBase.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = gBase;
    ctx.fillRect(0, 0, 512, 512);

    // 生成 14 條立體有機旋轉電漿觸鬚 (Organic Sinuous Plasma Tendrils)
    for (var i = 0; i < 16; i++) {
      var angleBase = (i * Math.PI * 2) / 16;
      ctx.beginPath();
      var rStart = 15 + (i % 3) * 10;
      var x0 = cx + Math.cos(angleBase) * rStart;
      var y0 = cy + Math.sin(angleBase) * rStart;
      ctx.moveTo(x0, y0);

      var cp1Dist = 90 + Math.sin(i * 1.8) * 35;
      var cp1Angle = angleBase + 0.65;
      var cp1x = cx + Math.cos(cp1Angle) * cp1Dist;
      var cp1y = cy + Math.sin(cp1Angle) * cp1Dist;

      var cp2Dist = 160 + Math.cos(i * 2.1) * 30;
      var cp2Angle = angleBase + 1.25;
      var cp2x = cx + Math.cos(cp2Angle) * cp2Dist;
      var cp2y = cy + Math.sin(cp2Angle) * cp2Dist;

      var rEnd = 210 + (i % 4) * 10;
      var endAngle = angleBase + 1.8;
      var x1 = cx + Math.cos(endAngle) * rEnd;
      var y1 = cy + Math.sin(endAngle) * rEnd;

      ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, x1, y1);

      ctx.lineWidth = 14 + (i % 5) * 4;
      var pGrad = ctx.createLinearGradient(x0, y0, x1, y1);
      pGrad.addColorStop(0, 'rgba(255, 255, 255, 0.95)');
      pGrad.addColorStop(0.3, 'rgba(103, 232, 249, 0.85)');
      pGrad.addColorStop(0.7, 'rgba(0, 245, 255, 0.45)');
      pGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');

      ctx.strokeStyle = pGrad;
      ctx.lineCap = 'round';
      ctx.stroke();
    }

    // 疊加多層高斯微光光斑與翻滾煙霧團 (Rolling Convection Puffs)
    var puffs = [
      { x: 210, y: 220, r: 85, c: 'rgba(255, 255, 255, 0.85)' },
      { x: 310, y: 270, r: 90, c: 'rgba(0, 245, 255, 0.65)' },
      { x: 230, y: 320, r: 80, c: 'rgba(56, 189, 248, 0.55)' },
      { x: 280, y: 190, r: 75, c: 'rgba(125, 211, 252, 0.6)' },
      { x: 180, y: 290, r: 70, c: 'rgba(2, 132, 199, 0.4)' }
    ];
    puffs.forEach(function(pf) {
      var gPf = ctx.createRadialGradient(pf.x, pf.y, 0, pf.x, pf.y, pf.r);
      gPf.addColorStop(0, pf.c);
      gPf.addColorStop(0.6, pf.c.replace(/[\d\.]+\)$/, '0.15)'));
      gPf.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.fillStyle = gPf;
      ctx.beginPath();
      ctx.arc(pf.x, pf.y, pf.r, 0, Math.PI * 2);
      ctx.fill();
    });

    // 中心白熾核閃光
    var gCenter = ctx.createRadialGradient(cx, cy, 0, cx, cy, 45);
    gCenter.addColorStop(0, '#FFFFFF');
    gCenter.addColorStop(0.3, 'rgba(255, 255, 255, 0.95)');
    gCenter.addColorStop(0.8, 'rgba(125, 211, 252, 0.5)');
    gCenter.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = gCenter;
    ctx.beginPath();
    ctx.arc(cx, cy, 45, 0, Math.PI * 2);
    ctx.fill();

    var tex = new THREE.CanvasTexture(canvas);
    tex.generateMipmaps = false;
    tex.minFilter = THREE.LinearFilter;
    tex.magFilter = THREE.LinearFilter;
    tex.needsUpdate = true;
    return tex;
  }

  /**
   * 6. 建立右星核專屬：深空宇宙螺旋漩渦星雲紋理 (Deep Space Swirling Cosmic Galaxy Vortex)
   *    繪製 4 條對數螺旋旋臂、紫紅至霓虹粉漸層氣體觸鬚與中心超強引力奇點
   */
  function createCosmicGalaxyVortexTexture() {
    var canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    var ctx = canvas.getContext('2d');
    var cx = 256;
    var cy = 256;

    ctx.clearRect(0, 0, 512, 512);

    // 4 條對數螺旋主要旋臂 (Logarithmic Spiral Arms)
    var numArms = 4;
    var totalPuffs = 1200;

    for (var i = 0; i < totalPuffs; i++) {
      var armIndex = i % numArms;
      var armAngleOffset = (armIndex * Math.PI * 2) / numArms;
      var t = i / totalPuffs; // 0 ~ 1
      var dist = Math.pow(t, 0.68) * 225 + 10;
      var angle = t * 6.5 + armAngleOffset;

      var wave = Math.sin(i * 14.7) * 16 * t;
      var px = cx + Math.cos(angle) * dist - Math.sin(angle) * wave;
      var py = cy + Math.sin(angle) * dist + Math.cos(angle) * wave;

      var puffRadius = 14 + t * 32;
      var puffGrad = ctx.createRadialGradient(px, py, 0, px, py, puffRadius);

      if (t < 0.22) {
        // 核心近處：白熾粉光
        puffGrad.addColorStop(0, 'rgba(255, 255, 255, 0.95)');
        puffGrad.addColorStop(0.35, 'rgba(255, 140, 210, 0.8)');
        puffGrad.addColorStop(0.7, 'rgba(255, 42, 133, 0.4)');
      } else if (t < 0.68) {
        // 中段旋臂：鮮豔洋紅與霓虹粉
        puffGrad.addColorStop(0, 'rgba(255, 42, 133, 0.85)');
        puffGrad.addColorStop(0.4, 'rgba(244, 63, 94, 0.6)');
        puffGrad.addColorStop(0.75, 'rgba(192, 132, 252, 0.35)');
      } else {
        // 外緣旋臂：深邃宇宙紫羅蘭
        puffGrad.addColorStop(0, 'rgba(147, 51, 234, 0.55)');
        puffGrad.addColorStop(0.5, 'rgba(107, 33, 168, 0.3)');
        puffGrad.addColorStop(0.85, 'rgba(59, 7, 100, 0.12)');
      }
      puffGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');

      ctx.fillStyle = puffGrad;
      ctx.beginPath();
      ctx.arc(px, py, puffRadius, 0, Math.PI * 2);
      ctx.fill();
    }

    // 沿著旋臂揮灑星際微光星屑 (Stardust Spikes)
    ctx.fillStyle = '#FFFFFF';
    for (var s = 0; s < 180; s++) {
      var sArm = s % numArms;
      var st = (s / 180);
      var sDist = Math.pow(st, 0.72) * 210 + 12;
      var sAngle = st * 6.5 + (sArm * Math.PI * 2) / numArms + (Math.random() - 0.5) * 0.2;
      var sx = cx + Math.cos(sAngle) * sDist;
      var sy = cy + Math.sin(sAngle) * sDist;
      ctx.beginPath();
      ctx.arc(sx, sy, Math.random() * 1.8 + 0.8, 0, Math.PI * 2);
      ctx.fill();
    }

    // 中心白熾引力黑洞核爆
    var gCenter = ctx.createRadialGradient(cx, cy, 0, cx, cy, 65);
    gCenter.addColorStop(0, '#FFFFFF');
    gCenter.addColorStop(0.2, '#FFE4F0');
    gCenter.addColorStop(0.5, 'rgba(255, 42, 133, 0.85)');
    gCenter.addColorStop(0.85, 'rgba(147, 51, 234, 0.3)');
    gCenter.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = gCenter;
    ctx.beginPath();
    ctx.arc(cx, cy, 65, 0, Math.PI * 2);
    ctx.fill();

    var tex = new THREE.CanvasTexture(canvas);
    tex.generateMipmaps = false;
    tex.minFilter = THREE.LinearFilter;
    tex.magFilter = THREE.LinearFilter;
    tex.needsUpdate = true;
    return tex;
  }

  /**
   * 輔助函式：建立扁平科技光環幾何 Mesh
   */
  function createFlatRingBand(innerR, outerR, colorHex, opacity, tex) {
    var geom = new THREE.RingGeometry(innerR, outerR, 96);
    var mat = new THREE.MeshBasicMaterial({
      color: colorHex,
      map: tex || null,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: opacity || 0.8,
      blending: THREE.AdditiveBlending,
      depthWrite: false
    });
    return new THREE.Mesh(geom, mat);
  }

  /* ==========================================================================
     🔵 左星核初始化：天青極光全息晶核 (PROTOCOL // SQUAD JOIN)
     ========================================================================== */
  function initJoinThreeCore(canvas) {
    if (!window.THREE) return null;

    try {
      var width = canvas.clientWidth || 420;
      var height = canvas.clientHeight || 420;

      var scene = new THREE.Scene();
      // 視野設置 z = 7.5，完全杜絕旋轉裁切
      var camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 100);
      camera.position.z = 7.5;

      var renderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: true });
      renderer.setSize(width, height);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setClearColor(0x000000, 0);

      var mainGroup = new THREE.Group();
      scene.add(mainGroup);

      // 生成高品質紋理
      var stardustTex = createStardustTexture();
      var shellTex = createHologramShellTexture();
      var plasmaTex = createOrganicPlasmaNebulaTexture();
      var ringTex1 = createAdvancedHudRingTexture('cyan', 1);
      var ringTex2 = createAdvancedHudRingTexture('cyan', 2);
      var ringTex3 = createAdvancedHudRingTexture('cyan', 3);

      // -------------------------------------------------------------
      // 1. 核心流體電漿球 (有機翻滾流體雙層逆轉)
      // -------------------------------------------------------------
      var coreInnerGeom = new THREE.SphereGeometry(0.86, 36, 36);
      var coreInnerMat = new THREE.MeshBasicMaterial({
        map: plasmaTex,
        transparent: true,
        opacity: 0.98,
        blending: THREE.AdditiveBlending
      });
      var coreInnerMesh = new THREE.Mesh(coreInnerGeom, coreInnerMat);
      mainGroup.add(coreInnerMesh);

      var coreOuterGeom = new THREE.SphereGeometry(1.02, 36, 36);
      var coreOuterMat = new THREE.MeshBasicMaterial({
        map: plasmaTex,
        transparent: true,
        opacity: 0.65,
        blending: THREE.AdditiveBlending
      });
      var coreOuterMesh = new THREE.Mesh(coreOuterGeom, coreOuterMat);
      mainGroup.add(coreOuterMesh);

      // 中心純白高溫光核
      var coreFlashGeom = new THREE.SphereGeometry(0.42, 24, 24);
      var coreFlashMat = new THREE.MeshBasicMaterial({
        color: 0xE0F7FA,
        transparent: true,
        opacity: 0.95,
        blending: THREE.AdditiveBlending
      });
      var coreFlashMesh = new THREE.Mesh(coreFlashGeom, coreFlashMat);
      mainGroup.add(coreFlashMesh);

      // -------------------------------------------------------------
      // 2. 核心數位點雲矩陣地球儀 (Cyber Dotted Matrix Globe)
      //    完美還原圖中覆蓋在核心上的經緯矩陣點陣 + 右上方高密度方塊數據簇
      // -------------------------------------------------------------
      var matrixPos = [];
      var matrixColors = [];
      var cCyan = new THREE.Color(0x00F5FF);
      var cWhite = new THREE.Color(0xFFFFFF);
      var cBlue = new THREE.Color(0x38BDF8);

      var matrixR = 1.12;
      var totalMatrixPts = 1800;

      // 均勻球面斐波那契點雲
      var phi = Math.PI * (3 - Math.sqrt(5));
      for (var p = 0; p < totalMatrixPts; p++) {
        var y = 1 - (p / (totalMatrixPts - 1)) * 2;
        var radiusAtY = Math.sqrt(1 - y * y);
        var theta = phi * p;
        var x = Math.cos(theta) * radiusAtY;
        var z = Math.sin(theta) * radiusAtY;

        matrixPos.push(x * matrixR, y * matrixR, z * matrixR);
        var col = (Math.random() > 0.45) ? cCyan : (Math.random() > 0.5 ? cWhite : cBlue);
        matrixColors.push(col.r, col.g, col.b);
      }

      // 💎 右上方專屬高密度矩陣方塊簇 (Cyber Data Matrix Grid Cluster - 原畫核心特徵)
      for (var row = 0; row < 12; row++) {
        for (var colIdx = 0; colIdx < 12; colIdx++) {
          var u = 0.35 + (colIdx / 12) * 0.45;
          var v = 0.2 + (row / 12) * 0.4;
          var mTheta = u * Math.PI;
          var mPhi = v * Math.PI;
          var mx = Math.sin(mPhi) * Math.cos(mTheta) * matrixR;
          var my = Math.cos(mPhi) * matrixR;
          var mz = Math.sin(mPhi) * Math.sin(mTheta) * matrixR;

          matrixPos.push(mx, my, mz);
          matrixColors.push(cWhite.r, cWhite.g, cWhite.b);
        }
      }

      var matrixGeom = new THREE.BufferGeometry();
      matrixGeom.setAttribute('position', new THREE.Float32BufferAttribute(matrixPos, 3));
      matrixGeom.setAttribute('color', new THREE.Float32BufferAttribute(matrixColors, 3));
      var matrixMat = new THREE.PointsMaterial({
        size: 0.046,
        map: stardustTex,
        vertexColors: true,
        transparent: true,
        opacity: 0.92,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var matrixPointsMesh = new THREE.Points(matrixGeom, matrixMat);
      mainGroup.add(matrixPointsMesh);

      // -------------------------------------------------------------
      // 3. 外層全息護盾球罩 (Hologram Dotted Grid Shell)
      // -------------------------------------------------------------
      var shellGeom = new THREE.SphereGeometry(1.56, 48, 48);
      var shellMat = new THREE.MeshBasicMaterial({
        map: shellTex,
        color: 0x67E8F9,
        transparent: true,
        opacity: 0.26,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var shellMesh = new THREE.Mesh(shellGeom, shellMat);
      mainGroup.add(shellMesh);

      // -------------------------------------------------------------
      // 4. 多軸高階 HUD 陀螺儀軌道光環 (Gyroscopic Segmented HUD Rings)
      // -------------------------------------------------------------
      var ringGroup = new THREE.Group();

      // 環 1：主赤道 HUD 軌道帶
      var ringEquator = createFlatRingBand(1.64, 1.95, 0x00F5FF, 0.88, ringTex1);
      ringEquator.rotation.x = Math.PI / 2.3;
      ringEquator.rotation.y = 0.12;
      ringGroup.add(ringEquator);

      // 環 2：傾斜次級軌道帶 (~ -35 度反向傾角)
      var ringTilted1 = createFlatRingBand(1.78, 1.95, 0x38BDF8, 0.78, ringTex2);
      ringTilted1.rotation.x = -Math.PI / 3.0;
      ringTilted1.rotation.z = 0.42;
      ringGroup.add(ringTilted1);

      // 環 3：第三軸精細瞄準環 (~ 40 度斜角)
      var ringTilted2 = createFlatRingBand(1.98, 2.08, 0x0284C7, 0.65, ringTex3);
      ringTilted2.rotation.y = Math.PI / 3.2;
      ringTilted2.rotation.x = 0.25;
      ringGroup.add(ringTilted2);

      // 環 4：最外圍微細瞄準圓環
      var ringReticle = createFlatRingBand(2.16, 2.22, 0x00F5FF, 0.45, null);
      ringReticle.rotation.x = Math.PI / 2.3;
      ringGroup.add(ringReticle);

      // 軌道巡航發光衛星節點 (Orbit Beacon Node)
      var beaconGeom = new THREE.SphereGeometry(0.045, 16, 16);
      var beaconMat = new THREE.MeshBasicMaterial({ color: 0xFFFFFF });
      var beaconMesh = new THREE.Mesh(beaconGeom, beaconMat);
      ringGroup.add(beaconMesh);

      mainGroup.add(ringGroup);

      // -------------------------------------------------------------
      // 5. 散落漂浮的極光星塵星粒 (850 顆微光浮游粒子)
      // -------------------------------------------------------------
      var pGeom = new THREE.BufferGeometry();
      var pPos = [];
      var pColors = [];

      for (var i = 0; i < 850; i++) {
        var r = 0.35 + Math.random() * 2.15;
        var thetaP = Math.random() * Math.PI * 2;
        var phiP = Math.acos(2 * Math.random() - 1);
        pPos.push(r * Math.sin(phiP) * Math.cos(thetaP), r * Math.sin(phiP) * Math.sin(thetaP), r * Math.cos(phiP));
        var colP = (r < 1.0) ? cWhite.clone().lerp(cCyan, r / 1.0) : cCyan.clone().lerp(cBlue, (r - 1.0) / 1.4);
        pColors.push(colP.r, colP.g, colP.b);
      }
      pGeom.setAttribute('position', new THREE.Float32BufferAttribute(pPos, 3));
      pGeom.setAttribute('color', new THREE.Float32BufferAttribute(pColors, 3));
      var pMat = new THREE.PointsMaterial({
        size: 0.042,
        map: stardustTex,
        vertexColors: true,
        transparent: true,
        opacity: 0.9,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var particles = new THREE.Points(pGeom, pMat);
      mainGroup.add(particles);

      // -------------------------------------------------------------
      // 6. 動態渲染與滑鼠 3D 視差傾角互動 (Interactive Parallax Loop)
      // -------------------------------------------------------------
      var currentSpeed = 0.0026;
      var targetSpeed = 0.0026;
      var scaleFactor = 1.0;
      var targetScale = 1.0;
      var beaconAngle = 0;
      var animId = null;
      var clock = new THREE.Clock();

      // 滑鼠視差阻尼變數
      var mouseTargetTiltX = 0;
      var mouseTargetTiltY = 0;

      function onMouseMove(e) {
        var rect = canvas.getBoundingClientRect();
        var nx = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        var ny = -(((e.clientY - rect.top) / rect.height) * 2 - 1);
        mouseTargetTiltX = nx * 0.38; // 傾角最大約 22 度
        mouseTargetTiltY = ny * 0.35;
      }
      function onMouseLeave() {
        mouseTargetTiltX = 0;
        mouseTargetTiltY = 0;
      }

      canvas.addEventListener('mousemove', onMouseMove);
      canvas.addEventListener('mouseleave', onMouseLeave);

      function renderLoop() {
        animId = requestAnimationFrame(renderLoop);
        var time = clock.getElapsedTime();

        currentSpeed = THREE.MathUtils.lerp(currentSpeed, targetSpeed, 0.06);
        scaleFactor = THREE.MathUtils.lerp(scaleFactor, targetScale, 0.06);
        mainGroup.scale.set(scaleFactor, scaleFactor, scaleFactor);

        // 滑鼠 3D 視差平滑平移
        mainGroup.rotation.y = THREE.MathUtils.lerp(mainGroup.rotation.y, mouseTargetTiltX, 0.07);
        mainGroup.rotation.x = THREE.MathUtils.lerp(mainGroup.rotation.x, -mouseTargetTiltY, 0.07);

        // 核心電漿球體雙向逆轉
        coreInnerMesh.rotation.y += currentSpeed * 1.5;
        coreInnerMesh.rotation.x += currentSpeed * 0.45;
        coreOuterMesh.rotation.y -= currentSpeed * 1.1;

        // 數位點雲地球儀自轉
        matrixPointsMesh.rotation.y += currentSpeed * 0.85;

        // 外層護盾微轉
        shellMesh.rotation.y += currentSpeed * 0.35;
        particles.rotation.y += currentSpeed * 0.65;

        // 呼吸脈動
        var pulse = 1.0 + 0.045 * Math.sin(time * 1.8);
        coreInnerMesh.scale.set(pulse, pulse, pulse);
        coreFlashMesh.scale.set(pulse * 1.05, pulse * 1.05, pulse * 1.05);

        // 軌道光環差速公轉
        ringEquator.rotation.z += currentSpeed * 1.6;
        ringTilted1.rotation.z -= currentSpeed * 1.35;
        ringTilted2.rotation.x += currentSpeed * 1.45;

        // 巡航衛星節點循跡移動
        beaconAngle += currentSpeed * 2.2;
        var bRadius = 1.82;
        beaconMesh.position.x = Math.cos(beaconAngle) * bRadius;
        beaconMesh.position.y = Math.sin(beaconAngle) * bRadius * 0.35;
        beaconMesh.position.z = Math.sin(beaconAngle) * bRadius * 0.85;

        renderer.render(scene, camera);
      }

      renderLoop();

      return {
        setHover: function(isHovered) {
          targetSpeed = isHovered ? 0.0075 : 0.0026;
          targetScale = isHovered ? 1.06 : 1.0;
        },
        destroy: function() {
          if (animId) cancelAnimationFrame(animId);
          canvas.removeEventListener('mousemove', onMouseMove);
          canvas.removeEventListener('mouseleave', onMouseLeave);
          coreInnerGeom.dispose();
          coreInnerMat.dispose();
          coreOuterGeom.dispose();
          coreOuterMat.dispose();
          coreFlashGeom.dispose();
          coreFlashMat.dispose();
          matrixGeom.dispose();
          matrixMat.dispose();
          shellGeom.dispose();
          shellMat.dispose();
          pGeom.dispose();
          pMat.dispose();
          renderer.dispose();
        }
      };
    } catch (err) {
      console.error('[Three.js Join Core Error]', err);
      return null;
    }
  }

  /* ==========================================================================
     🟣 右星核初始化：星冕深空螺旋奇點 (PROTOCOL // SQUAD HOST)
     ========================================================================== */
  function initHostThreeCore(canvas) {
    if (!window.THREE) return null;

    try {
      var width = canvas.clientWidth || 420;
      var height = canvas.clientHeight || 420;

      var scene = new THREE.Scene();
      var camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 100);
      camera.position.z = 7.5;

      var renderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: true });
      renderer.setSize(width, height);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setClearColor(0x000000, 0);

      var mainGroup = new THREE.Group();
      scene.add(mainGroup);

      // 生成高品質紋理
      var stardustTex = createStardustTexture();
      var starburstTex = createCrossStarburstTexture();
      var vortexTex = createCosmicGalaxyVortexTexture();
      var ringTex1 = createAdvancedHudRingTexture('magenta', 1);
      var ringTex2 = createAdvancedHudRingTexture('magenta', 2);

      // -------------------------------------------------------------
      // 1. 核心宇宙流體螺旋漩渦 (Deep Space Swirling Cosmic Galaxy Vortex)
      //    以雙層微距對盤 + 微凸拱頂構建三維厚度漩渦
      // -------------------------------------------------------------
      var vortexGroup = new THREE.Group();
      vortexGroup.rotation.x = Math.PI / 3.8;
      vortexGroup.rotation.y = 0.25;

      var vortexGeom1 = new THREE.PlaneGeometry(2.55, 2.55);
      var vortexMat1 = new THREE.MeshBasicMaterial({
        map: vortexTex,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.98,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var vortexMesh1 = new THREE.Mesh(vortexGeom1, vortexMat1);
      vortexGroup.add(vortexMesh1);

      var vortexGeom2 = new THREE.PlaneGeometry(2.32, 2.32);
      var vortexMat2 = new THREE.MeshBasicMaterial({
        map: vortexTex,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.72,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var vortexMesh2 = new THREE.Mesh(vortexGeom2, vortexMat2);
      vortexMesh2.position.z = 0.06;
      vortexMesh2.rotation.z = 0.6;
      vortexGroup.add(vortexMesh2);

      // -------------------------------------------------------------
      // 2. 中心超強引力奇點與星芒光爆 (Singularity Core + Cross Starburst)
      // -------------------------------------------------------------
      var singGeom = new THREE.SphereGeometry(0.32, 24, 24);
      var singMat = new THREE.MeshBasicMaterial({
        color: 0xFFF0F6,
        transparent: true,
        opacity: 0.98,
        blending: THREE.AdditiveBlending
      });
      var singularityMesh = new THREE.Mesh(singGeom, singMat);
      vortexGroup.add(singularityMesh);

      // 十字星芒光爆面板 (Billboard Cross Starburst Flare)
      var starburstGeom = new THREE.PlaneGeometry(1.5, 1.5);
      var starburstMat = new THREE.MeshBasicMaterial({
        map: starburstTex,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.95,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var starburstMesh = new THREE.Mesh(starburstGeom, starburstMat);
      starburstMesh.position.z = 0.12;
      vortexGroup.add(starburstMesh);

      mainGroup.add(vortexGroup);

      // -------------------------------------------------------------
      // 3. 多重傾角的霓虹紫紅 HUD 軌道系統 (Neon Magenta Gyro Rings)
      // -------------------------------------------------------------
      var ringGroup = new THREE.Group();

      // 環 1：主傾斜霓虹粉 HUD 儀表軌道帶
      var ringMain = createFlatRingBand(1.56, 1.92, 0xFF2A85, 0.9, ringTex1);
      ringMain.rotation.x = Math.PI / 3.0;
      ringMain.rotation.z = -0.22;
      ringGroup.add(ringMain);

      // 環 2：次級反向傾角軌道帶
      var ringTilted = createFlatRingBand(1.78, 1.95, 0xC084FC, 0.8, ringTex2);
      ringTilted.rotation.x = -Math.PI / 2.85;
      ringTilted.rotation.y = 0.42;
      ringGroup.add(ringTilted);

      // 環 3：外圍虛線對焦瞄準環
      var ringReticle = createFlatRingBand(2.1, 2.18, 0x9333EA, 0.55, null);
      ringReticle.rotation.y = -Math.PI / 3.3;
      ringReticle.rotation.x = 0.32;
      ringGroup.add(ringReticle);

      // 巡航紫晶衛星節點
      var beaconGeom = new THREE.SphereGeometry(0.045, 16, 16);
      var beaconMat = new THREE.MeshBasicMaterial({ color: 0xFFFFFF });
      var beaconMesh = new THREE.Mesh(beaconGeom, beaconMat);
      ringGroup.add(beaconMesh);

      mainGroup.add(ringGroup);

      // -------------------------------------------------------------
      // 4. 外圍螺旋飛散的紫晶星塵粒子流 (950 顆向心螺旋星粒)
      // -------------------------------------------------------------
      var pGeom = new THREE.BufferGeometry();
      var pPos = [];
      var pColors = [];
      var cWhite = new THREE.Color(0xFFFFFF);
      var cPink = new THREE.Color(0xFF2A85);
      var cPurple = new THREE.Color(0x9333EA);

      for (var i = 0; i < 950; i++) {
        var arm = i % 4;
        var r = Math.pow(Math.random(), 0.72) * 2.1 + 0.18;
        var angle = r * 4.2 + (arm * Math.PI * 2) / 4;
        var spread = (Math.random() - 0.5) * 0.38 * r;
        var x = Math.cos(angle) * r + spread;
        var y = Math.sin(angle) * r + spread;
        var z = (Math.random() - 0.5) * 0.45 * (2.2 - r * 0.55);

        pPos.push(x, y, z);
        var col = (r < 0.65) ? cWhite.clone().lerp(cPink, r / 0.65) : cPink.clone().lerp(cPurple, (r - 0.65) / 1.45);
        pColors.push(col.r, col.g, col.b);
      }
      pGeom.setAttribute('position', new THREE.Float32BufferAttribute(pPos, 3));
      pGeom.setAttribute('color', new THREE.Float32BufferAttribute(pColors, 3));
      var pMat = new THREE.PointsMaterial({
        size: 0.044,
        map: stardustTex,
        vertexColors: true,
        transparent: true,
        opacity: 0.92,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var particles = new THREE.Points(pGeom, pMat);
      mainGroup.add(particles);

      // -------------------------------------------------------------
      // 5. 動態旋轉與滑鼠 3D 視差互動迴圈
      // -------------------------------------------------------------
      var currentSpeed = 0.0028;
      var targetSpeed = 0.0028;
      var scaleFactor = 1.0;
      var targetScale = 1.0;
      var beaconAngle = 0;
      var animId = null;
      var clock = new THREE.Clock();

      var mouseTargetTiltX = 0;
      var mouseTargetTiltY = 0;

      function onMouseMove(e) {
        var rect = canvas.getBoundingClientRect();
        var nx = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        var ny = -(((e.clientY - rect.top) / rect.height) * 2 - 1);
        mouseTargetTiltX = nx * 0.38;
        mouseTargetTiltY = ny * 0.35;
      }
      function onMouseLeave() {
        mouseTargetTiltX = 0;
        mouseTargetTiltY = 0;
      }

      canvas.addEventListener('mousemove', onMouseMove);
      canvas.addEventListener('mouseleave', onMouseLeave);

      function renderLoop() {
        animId = requestAnimationFrame(renderLoop);
        var time = clock.getElapsedTime();

        currentSpeed = THREE.MathUtils.lerp(currentSpeed, targetSpeed, 0.06);
        scaleFactor = THREE.MathUtils.lerp(scaleFactor, targetScale, 0.06);
        mainGroup.scale.set(scaleFactor, scaleFactor, scaleFactor);

        // 滑鼠 3D 視差平滑平移
        mainGroup.rotation.y = THREE.MathUtils.lerp(mainGroup.rotation.y, mouseTargetTiltX, 0.07);
        mainGroup.rotation.x = THREE.MathUtils.lerp(mainGroup.rotation.x, -mouseTargetTiltY, 0.07);

        // 漩渦雙層盤差速向心旋轉
        vortexMesh1.rotation.z += currentSpeed * 1.8;
        vortexMesh2.rotation.z -= currentSpeed * 1.25;

        // 星塵粒子順應引力旋轉
        particles.rotation.z += currentSpeed * 1.5;

        // 奇點與星芒脈動
        var pulse = 1.0 + 0.05 * Math.sin(time * 2.0);
        singularityMesh.scale.set(pulse, pulse, pulse);
        starburstMesh.scale.set(pulse * 1.08, pulse * 1.08, pulse * 1.08);

        // 星芒緩慢自轉增加閃耀感
        starburstMesh.rotation.z += currentSpeed * 0.4;

        // 軌道光環旋轉
        ringMain.rotation.z -= currentSpeed * 1.6;
        ringTilted.rotation.z += currentSpeed * 1.4;
        ringReticle.rotation.x -= currentSpeed * 1.3;

        // 巡航衛星節點循跡移動
        beaconAngle -= currentSpeed * 2.4;
        var bRadius = 1.8;
        beaconMesh.position.x = Math.cos(beaconAngle) * bRadius;
        beaconMesh.position.y = Math.sin(beaconAngle) * bRadius * 0.4;
        beaconMesh.position.z = Math.sin(beaconAngle) * bRadius * 0.8;

        renderer.render(scene, camera);
      }

      renderLoop();

      return {
        setHover: function(isHovered) {
          targetSpeed = isHovered ? 0.0078 : 0.0028;
          targetScale = isHovered ? 1.06 : 1.0;
        },
        destroy: function() {
          if (animId) cancelAnimationFrame(animId);
          canvas.removeEventListener('mousemove', onMouseMove);
          canvas.removeEventListener('mouseleave', onMouseLeave);
          vortexGeom1.dispose();
          vortexMat1.dispose();
          vortexGeom2.dispose();
          vortexMat2.dispose();
          singGeom.dispose();
          singMat.dispose();
          starburstGeom.dispose();
          starburstMat.dispose();
          pGeom.dispose();
          pMat.dispose();
          renderer.dispose();
        }
      };
    } catch (err) {
      console.error('[Three.js Host Core Error]', err);
      return null;
    }
  }

  /* ==========================================================================
     構建全息選擇層 DOM 與互動事件綁定
     ========================================================================== */
  function buildOverlayDom() {
    if (overlayEl) return overlayEl;

    overlayEl = document.createElement('div');
    overlayEl.id = 'tutorial-party-orb-overlay';
    overlayEl.className = 'party-orb-overlay party-three-overlay';
    overlayEl.innerHTML = `
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
            <span>MULTIPLAYER RESONANCE PROTOCOL</span>
          </div>
          <h2 class="party-orb-title">選擇您的組隊教學旅程</h2>
        </div>

        <!-- 雙星核 3D 舞台區 (420px 無切割寬闊舞台) -->
        <div class="resonance-three-stage">
          
          <!-- 🔵 左星核：入隊教學 -->
          <div class="three-core-column core-join" id="core-col-join" data-role="party-join" tabindex="0" role="button">
            <div class="three-canvas-wrap">
              <canvas id="three-canvas-join" class="three-orb-canvas" width="420" height="420"></canvas>
            </div>
            <div class="three-core-meta">
              <div class="protocol-subtext">PROTOCOL // SQUAD JOIN</div>
              <h3 class="core-display-name">入隊教學</h3>
              <button class="three-launch-pill btn-pill-cyan" id="btn-launch-join">
                <span>✦ 點擊進入教學 ➔</span>
              </button>
            </div>
          </div>

          <!-- 🟣 右星核：開房教學 -->
          <div class="three-core-column core-host" id="core-col-host" data-role="party-host" tabindex="0" role="button">
            <div class="three-canvas-wrap">
              <canvas id="three-canvas-host" class="three-orb-canvas" width="420" height="420"></canvas>
            </div>
            <div class="three-core-meta">
              <div class="protocol-subtext">PROTOCOL // SQUAD HOST</div>
              <h3 class="core-display-name">開房教學</h3>
              <button class="three-launch-pill btn-pill-magenta" id="btn-launch-host">
                <span>★ 點擊進入教學 ➔</span>
              </button>
            </div>
          </div>

        </div>

        <!-- 底部返回卡片一覽 -->
        <div class="party-orb-footer-action">
          <button class="party-orb-cancel-btn" id="party-orb-cancel-btn">
            ✕ 返回卡片一覽
          </button>
        </div>
      </div>
    `;

    document.body.appendChild(overlayEl);

    var closeBtn = overlayEl.querySelector('#party-orb-close-btn');
    var cancelBtn = overlayEl.querySelector('#party-orb-cancel-btn');
    if (closeBtn) closeBtn.onclick = hideOverlay;
    if (cancelBtn) cancelBtn.onclick = hideOverlay;

    // 綁定左球互動
    var colJoin = overlayEl.querySelector('#core-col-join');
    var btnJoin = overlayEl.querySelector('#btn-launch-join');
    if (colJoin) {
      colJoin.onmouseenter = function() {
        if (_joinThreeApp) _joinThreeApp.setHover(true);
        playResonanceSound('hover');
      };
      colJoin.onmouseleave = function() {
        if (_joinThreeApp) _joinThreeApp.setHover(false);
      };
      var triggerJoin = function(e) {
        e.preventDefault();
        e.stopPropagation();
        launchPartyPipeline('party-join');
      };
      colJoin.onclick = triggerJoin;
      if (btnJoin) btnJoin.onclick = triggerJoin;
    }

    // 綁定右球互動
    var colHost = overlayEl.querySelector('#core-col-host');
    var btnHost = overlayEl.querySelector('#btn-launch-host');
    if (colHost) {
      colHost.onmouseenter = function() {
        if (_hostThreeApp) _hostThreeApp.setHover(true);
        playResonanceSound('hover');
      };
      colHost.onmouseleave = function() {
        if (_hostThreeApp) _hostThreeApp.setHover(false);
      };
      var triggerHost = function(e) {
        e.preventDefault();
        e.stopPropagation();
        launchPartyPipeline('party-host');
      };
      colHost.onclick = triggerHost;
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
   * 啟動教學管道並徹底銷毀選擇層
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
    }, 180);
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

    setTimeout(function() {
      var canvasJoin = document.getElementById('three-canvas-join');
      var canvasHost = document.getElementById('three-canvas-host');

      if (canvasJoin && !_joinThreeApp) {
        _joinThreeApp = initJoinThreeCore(canvasJoin);
      }
      if (canvasHost && !_hostThreeApp) {
        _hostThreeApp = initHostThreeCore(canvasHost);
      }
    }, 30);
  }

  /**
   * 隱藏並徹底關閉選擇層
   */
  function hideOverlay() {
    _isOverlayVisible = false;
    if (overlayEl) {
      overlayEl.classList.remove('active');
      overlayEl.classList.remove('fading-out');
      overlayEl.style.display = 'none';
      overlayEl.style.pointerEvents = 'none';
    }
    if (_joinThreeApp) {
      _joinThreeApp.destroy();
      _joinThreeApp = null;
    }
    if (_hostThreeApp) {
      _hostThreeApp.destroy();
      _hostThreeApp = null;
    }
  }

  // 對外暴露全域 API
  window.openPartyOrbSelection = showOverlay;
  window.PartyOrbOverlay = {
    show: showOverlay,
    hide: hideOverlay
  };

})(window);
