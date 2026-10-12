/**
 * Steam Manifest Updater - 組隊教學 3D 全息星核選擇層 (Three.js WebGL 3A 旗艦旗艦版)
 * 1:1 極限還原 Gemini_Generated_Image_m2o88sm2o88sm2o8.jpg 概念原畫：
 * 
 * 🎨 深度解構與分層運動光學系統 (Decoupled Multi-Tier Motion & Dispersing Optics):
 *  1. 【深空發散引力光冕】(Radiating Dispersing Corona - Z: -0.9)
 *     - 28 道高斯羽化微細射線向外發散擴散，告別死板「一片式」光環，營造宇宙天體向外輻射的深邃感。
 *  2. 【原畫母版高保真核心】(Master Hi-Res Visual Core - Z: 0.0)
 *     - 採用 NormalBlending 忠實還原 800px 母版全部細節、深紫/玫瑰紅旋渦、天青經緯點陣，杜絕中心過曝死白！
 *  3. 【中層雙向對流電漿旋臂】(Dual Counter-Rotating Plasma Streams - Z: 0.06 & -0.05)
 *     - 順逆雙向獨立差速旋轉，中心自然鏤空，在星核內部呈現流體對流的體積視差。
 *  4. 【3D 幾何立體菲涅爾球面晶膜】(Volumetric 3D Fresnel Glass Shell - SphereGeometry 64x48)
 *     - 中心 100% 透明留空 (0 過曝)，邊緣輪廓具有柔和 3D 曲率高光與邊界微點，提供真實玻璃/力場曲率。
 *  5. 【中心聚能奇點十字星芒】(Singularity Pinpoint Core - Z: 0.08)
 *     - 緊湊聚焦的微型白熾耀斑，獨立心跳脈衝與反向轉動，如星核內部微型超新星。
 *  6. 【多重獨立 3D 傾角科技星環】(Multi-Inclination 3D Gyro Tech Rings - 3 條獨立空間傾角軌道)
 *     - 環 1 (內主弧軌道，傾角 X: 60°，差速公轉)
 *     - 環 2 (反向空間陀螺儀軌道，傾角 X: -50°，Y: -20°，逆向公轉)
 *     - 環 3 (外層寬段落科技導軌，傾角 X: 78°，低速公轉)
 *     - 均以同心圓弧動態映射，杜絕任何邊緣截斷或水平延伸的光片！
 *  7. 【全景 3D 發散星塵微粒力場】(Dispersing Quantum Stardust - 1050 顆向外擴散微粒)
 *  8. 【滑鼠多層次物理視差梯度系統】(Differential Parallax System - 隨視角產生前後景深錯位)
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
        gain.gain.setValueAtTime(0.04, now);
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
     🎨 紋理加載管線 (Texture Loader with Safe Fallback)
     ========================================================================== */
  function loadLayerTexture(dataUri, fallbackPath, onLoaded) {
    var canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    var ctx = canvas.getContext('2d');

    var tex = new THREE.CanvasTexture(canvas);
    tex.generateMipmaps = false;
    tex.minFilter = THREE.LinearFilter;
    tex.magFilter = THREE.LinearFilter;

    var img = new Image();
    img.onload = function() {
      ctx.clearRect(0, 0, 512, 512);
      ctx.drawImage(img, 0, 0, 512, 512);
      tex.needsUpdate = true;
      if (typeof onLoaded === 'function') onLoaded(tex);
    };
    img.onerror = function() {
      if (fallbackPath) {
        var fallbackImg = new Image();
        fallbackImg.onload = function() {
          ctx.clearRect(0, 0, 512, 512);
          ctx.drawImage(fallbackImg, 0, 0, 512, 512);
          tex.needsUpdate = true;
          if (typeof onLoaded === 'function') onLoaded(tex);
        };
        fallbackImg.src = fallbackPath;
      }
    };
    img.src = dataUri || fallbackPath;
    return tex;
  }

  /* ==========================================================================
     ✨ 動態光學紋理生成器 (Pure Optical FX Generators)
     ========================================================================== */

  /**
   * 1. 發散式光冕紋理 (Radiating Dispersing Corona Flare)
   * 以多道羽化微細射線向外發散擴散，徹底杜絕單塊平片死光感
   */
  function createRadiatingCoronaTexture(isCyan) {
    var canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    var ctx = canvas.getContext('2d');
    var cx = 256;
    var cy = 256;

    // 寬域高斯柔光基底
    var baseGrad = ctx.createRadialGradient(cx, cy, 30, cx, cy, 250);
    if (isCyan) {
      baseGrad.addColorStop(0, 'rgba(0, 245, 255, 0.35)');
      baseGrad.addColorStop(0.35, 'rgba(14, 165, 233, 0.18)');
      baseGrad.addColorStop(0.7, 'rgba(2, 132, 199, 0.06)');
      baseGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');
    } else {
      baseGrad.addColorStop(0, 'rgba(255, 42, 133, 0.35)');
      baseGrad.addColorStop(0.35, 'rgba(192, 132, 252, 0.18)');
      baseGrad.addColorStop(0.7, 'rgba(147, 51, 234, 0.06)');
      baseGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');
    }
    ctx.fillStyle = baseGrad;
    ctx.fillRect(0, 0, 512, 512);

    // 32 道向外發散的微細光芒射線
    ctx.save();
    ctx.translate(cx, cy);
    var numRays = 32;
    for (var i = 0; i < numRays; i++) {
      var angle = (i / numRays) * Math.PI * 2;
      var rayLen = 150 + (i % 3) * 40 + (i % 5) * 20;
      var rayWidth = (i % 2 === 0) ? 2.4 : 1.2;

      ctx.save();
      ctx.rotate(angle);
      var rayGrad = ctx.createLinearGradient(40, 0, rayLen, 0);
      if (isCyan) {
        rayGrad.addColorStop(0, 'rgba(0, 245, 255, 0)');
        rayGrad.addColorStop(0.2, 'rgba(0, 245, 255, 0.32)');
        rayGrad.addColorStop(0.6, 'rgba(56, 189, 248, 0.18)');
        rayGrad.addColorStop(1, 'rgba(0, 245, 255, 0)');
      } else {
        rayGrad.addColorStop(0, 'rgba(255, 42, 133, 0)');
        rayGrad.addColorStop(0.2, 'rgba(255, 42, 133, 0.32)');
        rayGrad.addColorStop(0.6, 'rgba(216, 180, 254, 0.18)');
        rayGrad.addColorStop(1, 'rgba(255, 42, 133, 0)');
      }
      ctx.fillStyle = rayGrad;
      ctx.fillRect(40, -rayWidth / 2, rayLen - 40, rayWidth);
      ctx.restore();
    }
    ctx.restore();

    var tex = new THREE.CanvasTexture(canvas);
    tex.needsUpdate = true;
    return tex;
  }

  /**
   * 2. 菲涅爾 3D 球面光膜紋理 (Fresnel Rim-Glow Shell Texture)
   * ⚠️ 核心防過曝設計：中心 65% 完全透明留空，僅在外緣勾勒立體 3D 菲涅爾曲面光弧！
   */
  function createFresnelSphereTexture(isCyan) {
    var canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    var ctx = canvas.getContext('2d');
    var cx = 256;
    var cy = 256;

    ctx.clearRect(0, 0, 512, 512);

    // 中心完全透明，外圈邊緣柔和發光
    var grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, 256);
    grad.addColorStop(0, 'rgba(0, 0, 0, 0)');
    grad.addColorStop(0.65, 'rgba(0, 0, 0, 0)'); // 65% 中心區域完全留空
    if (isCyan) {
      grad.addColorStop(0.82, 'rgba(0, 245, 255, 0.20)');
      grad.addColorStop(0.93, 'rgba(0, 245, 255, 0.52)');
      grad.addColorStop(0.98, 'rgba(255, 255, 255, 0.80)');
      grad.addColorStop(1.0, 'rgba(0, 245, 255, 0)');
    } else {
      grad.addColorStop(0.82, 'rgba(255, 42, 133, 0.20)');
      grad.addColorStop(0.93, 'rgba(255, 42, 133, 0.52)');
      grad.addColorStop(0.98, 'rgba(255, 255, 255, 0.80)');
      grad.addColorStop(1.0, 'rgba(255, 42, 133, 0)');
    }
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 512, 512);

    // 沿著邊緣繪製微弱科技光學刻度點
    ctx.save();
    ctx.translate(cx, cy);
    var dots = 64;
    for (var d = 0; d < dots; d++) {
      if (d % 2 === 0) continue;
      var a = (d / dots) * Math.PI * 2;
      var dotR = 236;
      ctx.fillStyle = isCyan ? 'rgba(0, 245, 255, 0.40)' : 'rgba(255, 100, 180, 0.40)';
      ctx.beginPath();
      ctx.arc(Math.cos(a) * dotR, Math.sin(a) * dotR, 1.2, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();

    var tex = new THREE.CanvasTexture(canvas);
    tex.needsUpdate = true;
    return tex;
  }

  /**
   * 3. 獨立 3D 科技星環軌道紋理 (Multi-Ring Gyro Orbit Texture)
   * 繪製於 512x512 畫布正中心的同心圓弧，具備圓周對稱性，徹底杜絕直角光片！
   */
  function createMultiRingTechTexture(isCyan, tier) {
    var canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    var ctx = canvas.getContext('2d');
    var cx = 256;
    var cy = 256;

    ctx.clearRect(0, 0, 512, 512);

    var primaryColor = isCyan ? '#00F5FF' : '#FF2A85';
    var softColor = isCyan ? 'rgba(0, 245, 255, 0.32)' : 'rgba(255, 42, 133, 0.32)';
    var brightColor = isCyan ? '#E0F7FF' : '#FFE4F0';

    if (tier === 1) {
      // 內層軌道環：細緻高光主弧與導航信標點 (Radius: 185)
      var r1 = 185;
      ctx.strokeStyle = softColor;
      ctx.lineWidth = 1.3;
      ctx.beginPath();
      ctx.arc(cx, cy, r1, 0, Math.PI * 2);
      ctx.stroke();

      // 兩段高亮對稱弧
      ctx.strokeStyle = primaryColor;
      ctx.lineWidth = 2.4;
      ctx.beginPath();
      ctx.arc(cx, cy, r1, -0.6, 1.1);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(cx, cy, r1, Math.PI - 0.6, Math.PI + 1.1);
      ctx.stroke();

      // 信標發光節點
      var nodeAngles = [0.2, 0.9, Math.PI + 0.2, Math.PI + 0.9];
      for (var n = 0; n < nodeAngles.length; n++) {
        var na = nodeAngles[n];
        var nx = cx + Math.cos(na) * r1;
        var ny = cy + Math.sin(na) * r1;
        ctx.fillStyle = brightColor;
        ctx.beginPath();
        ctx.arc(nx, ny, 3.0, 0, Math.PI * 2);
        ctx.fill();
      }
    } else if (tier === 2) {
      // 中層大角度反傾軌道環：雙重虛線與長流光 (Radius: 216)
      var r2 = 216;
      ctx.strokeStyle = isCyan ? 'rgba(14, 165, 233, 0.40)' : 'rgba(192, 132, 252, 0.40)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(cx, cy, r2, 0, Math.PI * 2);
      ctx.stroke();

      ctx.strokeStyle = primaryColor;
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.arc(cx, cy, r2, 0.8, 2.3);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(cx, cy, r2, Math.PI + 0.8, Math.PI + 2.3);
      ctx.stroke();

      // 同心微導軌
      ctx.strokeStyle = softColor;
      ctx.lineWidth = 0.9;
      ctx.beginPath();
      ctx.arc(cx, cy, r2 + 6, -0.5, 1.8);
      ctx.stroke();
    } else {
      // 外層大半徑科技環：寬段落弧光 (Radius: 242)
      var r3 = 242;
      ctx.strokeStyle = softColor;
      ctx.lineWidth = 1.0;
      ctx.beginPath();
      ctx.arc(cx, cy, r3, 0, Math.PI * 2);
      ctx.stroke();

      ctx.strokeStyle = primaryColor;
      ctx.lineWidth = 2.6;
      ctx.beginPath();
      ctx.arc(cx, cy, r3, -1.2, -0.2);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(cx, cy, r3, Math.PI - 1.2, Math.PI - 0.2);
      ctx.stroke();
    }

    var tex = new THREE.CanvasTexture(canvas);
    tex.needsUpdate = true;
    return tex;
  }

  /**
   * 4. 聚焦奇點白熾十字星芒 (Singularity Pinpoint Flare)
   * 縮小發光半徑，以細銳焦點聚能，絕不過曝周圍星系細節！
   */
  function createSingularityPinpointTexture(isCyan) {
    var canvas = document.createElement('canvas');
    canvas.width = 128;
    canvas.height = 128;
    var ctx = canvas.getContext('2d');
    var cx = 64;
    var cy = 64;

    ctx.clearRect(0, 0, 128, 128);

    // 中心微型白熾核
    var gCore = ctx.createRadialGradient(cx, cy, 0, cx, cy, 18);
    gCore.addColorStop(0, '#FFFFFF');
    gCore.addColorStop(0.35, isCyan ? 'rgba(0, 245, 255, 0.85)' : 'rgba(255, 120, 200, 0.85)');
    gCore.addColorStop(0.8, isCyan ? 'rgba(14, 165, 233, 0.25)' : 'rgba(192, 132, 252, 0.25)');
    gCore.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = gCore;
    ctx.beginPath();
    ctx.arc(cx, cy, 18, 0, Math.PI * 2);
    ctx.fill();

    // 水平銳利星芒
    var gH = ctx.createLinearGradient(0, cy, 128, cy);
    gH.addColorStop(0, 'rgba(255, 255, 255, 0)');
    gH.addColorStop(0.45, isCyan ? 'rgba(0, 245, 255, 0.6)' : 'rgba(255, 140, 210, 0.6)');
    gH.addColorStop(0.5, '#FFFFFF');
    gH.addColorStop(0.55, isCyan ? 'rgba(0, 245, 255, 0.6)' : 'rgba(255, 140, 210, 0.6)');
    gH.addColorStop(1, 'rgba(255, 255, 255, 0)');
    ctx.fillStyle = gH;
    ctx.fillRect(4, cy - 1, 120, 2);

    // 垂直銳利星芒
    var gV = ctx.createLinearGradient(cx, 0, cx, 128);
    gV.addColorStop(0, 'rgba(255, 255, 255, 0)');
    gV.addColorStop(0.45, isCyan ? 'rgba(0, 245, 255, 0.6)' : 'rgba(255, 140, 210, 0.6)');
    gV.addColorStop(0.5, '#FFFFFF');
    gV.addColorStop(0.55, isCyan ? 'rgba(0, 245, 255, 0.6)' : 'rgba(255, 140, 210, 0.6)');
    gV.addColorStop(1, 'rgba(255, 255, 255, 0)');
    ctx.fillStyle = gV;
    ctx.fillRect(cx - 1, 4, 2, 120);

    var tex = new THREE.CanvasTexture(canvas);
    tex.needsUpdate = true;
    return tex;
  }

  /**
   * 5. 中層有機電漿流動旋臂紋理 (Procedural Plasma Stream Arms)
   * 柔和的雙螺旋電漿帶，中心自然留空，在星核內部帶來立體對流視差
   */
  function createPlasmaNebulaTexture(isCyan, variant) {
    var canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 256;
    var ctx = canvas.getContext('2d');
    var cx = 128;
    var cy = 128;

    ctx.clearRect(0, 0, 256, 256);

    ctx.save();
    ctx.translate(cx, cy);
    var spiralArms = (variant === 1) ? 2 : 3;
    for (var a = 0; a < spiralArms; a++) {
      ctx.save();
      ctx.rotate((a / spiralArms) * Math.PI * 2);
      var grad = ctx.createRadialGradient(46, 0, 8, 46, 0, 52);
      if (isCyan) {
        grad.addColorStop(0, 'rgba(0, 245, 255, 0.38)');
        grad.addColorStop(0.5, 'rgba(14, 165, 233, 0.18)');
        grad.addColorStop(1, 'rgba(0, 0, 0, 0)');
      } else {
        grad.addColorStop(0, 'rgba(255, 42, 133, 0.38)');
        grad.addColorStop(0.5, 'rgba(192, 132, 252, 0.18)');
        grad.addColorStop(1, 'rgba(0, 0, 0, 0)');
      }
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.ellipse(46, 0, 52, 26, Math.PI / 6, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }
    ctx.restore();

    var tex = new THREE.CanvasTexture(canvas);
    tex.needsUpdate = true;
    return tex;
  }

  /**
   * 6. 高斯羽化微光星塵紋理
   */
  function createStardustTexture() {
    var canvas = document.createElement('canvas');
    canvas.width = 64;
    canvas.height = 64;
    var ctx = canvas.getContext('2d');
    var grad = ctx.createRadialGradient(32, 32, 0, 32, 32, 30);
    grad.addColorStop(0, '#FFFFFF');
    grad.addColorStop(0.25, 'rgba(255, 255, 255, 0.9)');
    grad.addColorStop(0.55, 'rgba(0, 245, 255, 0.45)');
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

  /* ==========================================================================
     🔵 左星核：天青全息晶核 (PROTOCOL // SQUAD JOIN) - 3A 多層發散與細節還原
     ========================================================================== */
  function initJoinThreeCore(canvas) {
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

      // ── Layer 1：深空發散引力光冕 (Radiating Dispersing Corona - Z: -0.9) ──
      var coronaTex = createRadiatingCoronaTexture(true);
      var coronaGeom = new THREE.PlaneGeometry(5.8, 5.8);
      var coronaMat = new THREE.MeshBasicMaterial({
        map: coronaTex,
        transparent: true,
        opacity: 0.38,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var coronaMesh = new THREE.Mesh(coronaGeom, coronaMat);
      coronaMesh.position.z = -0.9;
      mainGroup.add(coronaMesh);

      // ── Layer 2：原畫母版高保真視覺核心 (Master Hi-Res Visual Core - Z: 0.0) ──
      // ⚠️ 採用 NormalBlending，100% 呈現原畫深邃星雲、經緯點陣與科技環，不自加光防過曝！
      var masterGeom = new THREE.PlaneGeometry(3.55, 3.55);
      var masterMat = new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 1.0,
        blending: THREE.NormalBlending,
        depthWrite: false
      });
      var masterMesh = new THREE.Mesh(masterGeom, masterMat);
      mainGroup.add(masterMesh);

      // ── Layer 3：中層雙向對流電漿旋臂 (Dual Counter-Rotating Plasma Streams) ──
      var plasmaTex1 = createPlasmaNebulaTexture(true, 1);
      var plasmaGeom1 = new THREE.PlaneGeometry(2.9, 2.9);
      var plasmaMat1 = new THREE.MeshBasicMaterial({
        map: plasmaTex1,
        transparent: true,
        opacity: 0.32,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var plasmaMesh1 = new THREE.Mesh(plasmaGeom1, plasmaMat1);
      plasmaMesh1.position.z = 0.06;
      mainGroup.add(plasmaMesh1);

      var plasmaTex2 = createPlasmaNebulaTexture(true, 2);
      var plasmaGeom2 = new THREE.PlaneGeometry(2.6, 2.6);
      var plasmaMat2 = new THREE.MeshBasicMaterial({
        map: plasmaTex2,
        transparent: true,
        opacity: 0.26,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var plasmaMesh2 = new THREE.Mesh(plasmaGeom2, plasmaMat2);
      plasmaMesh2.position.z = -0.05;
      plasmaMesh2.rotation.x = 0.20;
      mainGroup.add(plasmaMesh2);

      // ── Layer 4：3D 幾何立體菲涅爾球面晶膜 (Volumetric 3D Fresnel Glass Shell) ──
      // ⚠️ 中心留空防白暴，僅在 3D 邊緣曲率發光！
      var fresnelTex = createFresnelSphereTexture(true);
      var fresnelGeom = new THREE.SphereGeometry(1.36, 64, 48);
      var fresnelMat = new THREE.MeshBasicMaterial({
        map: fresnelTex,
        transparent: true,
        opacity: 0.52,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var fresnelMesh = new THREE.Mesh(fresnelGeom, fresnelMat);
      mainGroup.add(fresnelMesh);

      // ── Layer 5：中心聚能奇點十字星芒 (Singularity Pinpoint Flare - Z: 0.08) ──
      var starburstTex = createSingularityPinpointTexture(true);
      var starburstGeom = new THREE.PlaneGeometry(0.85, 0.85);
      var starburstMat = new THREE.MeshBasicMaterial({
        map: starburstTex,
        transparent: true,
        opacity: 0.88,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var starburstMesh = new THREE.Mesh(starburstGeom, starburstMat);
      starburstMesh.position.z = 0.08;
      mainGroup.add(starburstMesh);

      // ── Layer 6：多重獨立 3D 傾角科技星環 (3 條獨立空間傾角軌道，杜絕死板光片) ──
      var ringTex1 = createMultiRingTechTexture(true, 1);
      var ringGeom1 = new THREE.PlaneGeometry(3.6, 3.6);
      var ringMat1 = new THREE.MeshBasicMaterial({
        map: ringTex1,
        transparent: true,
        opacity: 0.78,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var ringMesh1 = new THREE.Mesh(ringGeom1, ringMat1);
      ringMesh1.rotation.x = Math.PI / 3.0;
      ringMesh1.rotation.y = 0.18;
      mainGroup.add(ringMesh1);

      var ringTex2 = createMultiRingTechTexture(true, 2);
      var ringGeom2 = new THREE.PlaneGeometry(3.9, 3.9);
      var ringMat2 = new THREE.MeshBasicMaterial({
        map: ringTex2,
        transparent: true,
        opacity: 0.68,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var ringMesh2 = new THREE.Mesh(ringGeom2, ringMat2);
      ringMesh2.rotation.x = -Math.PI / 3.6;
      ringMesh2.rotation.y = -0.32;
      ringMesh2.rotation.z = 0.25;
      mainGroup.add(ringMesh2);

      var ringTex3 = createMultiRingTechTexture(true, 3);
      var ringGeom3 = new THREE.PlaneGeometry(4.3, 4.3);
      var ringMat3 = new THREE.MeshBasicMaterial({
        map: ringTex3,
        transparent: true,
        opacity: 0.55,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var ringMesh3 = new THREE.Mesh(ringGeom3, ringMat3);
      ringMesh3.rotation.x = Math.PI / 2.3;
      ringMesh3.rotation.y = 0.08;
      mainGroup.add(ringMesh3);

      // ── Layer 7：全景 3D 發散星塵微粒力場 (1050 顆向外擴散微粒) ──
      var stardustTex = createStardustTexture();
      var pGeom = new THREE.BufferGeometry();
      var pPos = [];
      var pColors = [];
      var cWhite = new THREE.Color(0xFFFFFF);
      var cCyan = new THREE.Color(0x00F5FF);
      var cBlue = new THREE.Color(0x38BDF8);

      for (var i = 0; i < 1050; i++) {
        var r = 0.4 + Math.random() * 2.3;
        var thetaP = Math.random() * Math.PI * 2;
        var phiP = Math.acos(2 * Math.random() - 1);
        pPos.push(r * Math.sin(phiP) * Math.cos(thetaP), r * Math.sin(phiP) * Math.sin(thetaP), r * Math.cos(phiP));
        var colP = (r < 1.0) ? cWhite.clone().lerp(cCyan, r / 1.0) : cCyan.clone().lerp(cBlue, (r - 1.0) / 1.5);
        pColors.push(colP.r, colP.g, colP.b);
      }
      pGeom.setAttribute('position', new THREE.Float32BufferAttribute(pPos, 3));
      pGeom.setAttribute('color', new THREE.Float32BufferAttribute(pColors, 3));
      var pMat = new THREE.PointsMaterial({
        size: 0.042,
        map: stardustTex,
        vertexColors: true,
        transparent: true,
        opacity: 0.88,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var particles = new THREE.Points(pGeom, pMat);
      mainGroup.add(particles);

      // ── 加載 800px 超清原畫母版 ──
      var assets = window.SMU_PARTY_ORB_ASSETS || {};
      var joinUri = assets.joinArtworkWebp || assets.joinCore;
      
      loadLayerTexture(joinUri, 'assets/tutorial/orb_join_artwork_800.webp', function(tex) {
        masterMat.map = tex;
        masterMat.needsUpdate = true;
      });

      // ── Layer 8：動態迴圈與各層獨立自由運動 ──
      var currentSpeed = 0.0028;
      var targetSpeed = 0.0028;
      var scaleFactor = 1.0;
      var targetScale = 1.0;
      var animId = null;
      var clock = new THREE.Clock();

      var mouseTargetTiltX = 0;
      var mouseTargetTiltY = 0;

      function onMouseMove(e) {
        var rect = canvas.getBoundingClientRect();
        if (!rect || rect.width <= 0 || rect.height <= 0) return;
        var nx = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        var ny = -(((e.clientY - rect.top) / rect.height) * 2 - 1);
        if (isNaN(nx) || isNaN(ny)) return;
        mouseTargetTiltX = nx * 0.42;
        mouseTargetTiltY = ny * 0.36;
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

        if (isNaN(mouseTargetTiltX)) mouseTargetTiltX = 0;
        if (isNaN(mouseTargetTiltY)) mouseTargetTiltY = 0;

        currentSpeed = THREE.MathUtils.lerp(currentSpeed, targetSpeed, 0.06);
        scaleFactor = THREE.MathUtils.lerp(scaleFactor, targetScale, 0.06);
        mainGroup.scale.set(scaleFactor, scaleFactor, scaleFactor);

        // 主群組 3D 物理視差傾角
        mainGroup.rotation.y = THREE.MathUtils.lerp(mainGroup.rotation.y, mouseTargetTiltX, 0.07);
        mainGroup.rotation.x = THREE.MathUtils.lerp(mainGroup.rotation.x, -mouseTargetTiltY, 0.07);

        // 各層差異化視差與深度拉伸
        var px = mouseTargetTiltX;
        var py = -mouseTargetTiltY;
        coronaMesh.position.x = -px * 0.16;
        coronaMesh.position.y = -py * 0.12;
        ringMesh1.position.x = px * 0.18;
        ringMesh1.position.y = py * 0.14;
        ringMesh2.position.x = -px * 0.12;
        ringMesh2.position.y = -py * 0.10;
        ringMesh3.position.x = px * 0.26;
        ringMesh3.position.y = py * 0.20;

        // 1. 原畫母版緩慢自然呼吸
        var pulse = 1.0 + 0.022 * Math.sin(time * 1.5);
        masterMesh.scale.set(pulse, pulse, 1.0);

        // 2. 菲涅爾 3D 球膜真實三維自轉
        fresnelMesh.rotation.y += currentSpeed * 0.65;
        fresnelMesh.rotation.x = 0.08 * Math.sin(time * 0.9);

        // 3. 雙向電漿動態對流
        plasmaMesh1.rotation.z -= currentSpeed * 1.35;
        plasmaMesh2.rotation.z += currentSpeed * 0.95;
        plasmaMat1.opacity = 0.28 + 0.08 * Math.sin(time * 1.8);
        plasmaMat2.opacity = 0.22 + 0.06 * Math.cos(time * 1.5);

        // 4. 中心聚能奇點十字星芒微動態
        var starPulse = 1.0 + 0.06 * Math.sin(time * 2.8);
        starburstMesh.scale.set(starPulse, starPulse, 1.0);
        starburstMesh.rotation.z -= currentSpeed * 0.6;

        // 5. 三重星環差速交錯公轉 (宛如真實陀螺儀)
        ringMesh1.rotation.z += currentSpeed * 1.25;
        ringMesh2.rotation.z -= currentSpeed * 0.95;
        ringMesh3.rotation.z += currentSpeed * 0.65;

        // 6. 發散光冕微自轉
        coronaMesh.rotation.z += currentSpeed * 0.4;

        // 7. 星塵旋轉
        particles.rotation.y += currentSpeed * 0.6;

        renderer.render(scene, camera);
      }

      renderLoop();

      return {
        setHover: function(isHovered) {
          targetSpeed = isHovered ? 0.0078 : 0.0028;
          targetScale = isHovered ? 1.07 : 1.0;
        },
        destroy: function() {
          if (animId) cancelAnimationFrame(animId);
          canvas.removeEventListener('mousemove', onMouseMove);
          canvas.removeEventListener('mouseleave', onMouseLeave);
          coronaGeom.dispose();
          coronaMat.dispose();
          masterGeom.dispose();
          masterMat.dispose();
          plasmaGeom1.dispose();
          plasmaMat1.dispose();
          plasmaGeom2.dispose();
          plasmaMat2.dispose();
          fresnelGeom.dispose();
          fresnelMat.dispose();
          starburstGeom.dispose();
          starburstMat.dispose();
          ringGeom1.dispose();
          ringMat1.dispose();
          ringGeom2.dispose();
          ringMat2.dispose();
          ringGeom3.dispose();
          ringMat3.dispose();
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
     🟣 右星核：霓虹紫紅星核 (PROTOCOL // SQUAD HOST) - 3A 多層發散與細節還原
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

      // ── Layer 1：深空發散引力光冕 (Radiating Dispersing Corona - Z: -0.9) ──
      var coronaTex = createRadiatingCoronaTexture(false);
      var coronaGeom = new THREE.PlaneGeometry(5.8, 5.8);
      var coronaMat = new THREE.MeshBasicMaterial({
        map: coronaTex,
        transparent: true,
        opacity: 0.38,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var coronaMesh = new THREE.Mesh(coronaGeom, coronaMat);
      coronaMesh.position.z = -0.9;
      mainGroup.add(coronaMesh);

      // ── Layer 2：原畫母版高保真視覺核心 (Master Hi-Res Visual Core - Z: 0.0) ──
      // ⚠️ 採用 NormalBlending，忠實呈現瑰麗星系旋渦與深邃暗影，避免過曝！
      var masterGeom = new THREE.PlaneGeometry(3.55, 3.55);
      var masterMat = new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 1.0,
        blending: THREE.NormalBlending,
        depthWrite: false
      });
      var masterMesh = new THREE.Mesh(masterGeom, masterMat);
      mainGroup.add(masterMesh);

      // ── Layer 3：中層雙向對流電漿旋臂 (Dual Counter-Rotating Plasma Streams) ──
      var plasmaTex1 = createPlasmaNebulaTexture(false, 1);
      var plasmaGeom1 = new THREE.PlaneGeometry(2.9, 2.9);
      var plasmaMat1 = new THREE.MeshBasicMaterial({
        map: plasmaTex1,
        transparent: true,
        opacity: 0.34,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var plasmaMesh1 = new THREE.Mesh(plasmaGeom1, plasmaMat1);
      plasmaMesh1.position.z = 0.06;
      mainGroup.add(plasmaMesh1);

      var plasmaTex2 = createPlasmaNebulaTexture(false, 2);
      var plasmaGeom2 = new THREE.PlaneGeometry(2.65, 2.65);
      var plasmaMat2 = new THREE.MeshBasicMaterial({
        map: plasmaTex2,
        transparent: true,
        opacity: 0.28,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var plasmaMesh2 = new THREE.Mesh(plasmaGeom2, plasmaMat2);
      plasmaMesh2.position.z = -0.05;
      plasmaMesh2.rotation.x = -0.22;
      mainGroup.add(plasmaMesh2);

      // ── Layer 4：3D 幾何立體菲涅爾球面晶膜 (Volumetric 3D Fresnel Glass Shell) ──
      var fresnelTex = createFresnelSphereTexture(false);
      var fresnelGeom = new THREE.SphereGeometry(1.36, 64, 48);
      var fresnelMat = new THREE.MeshBasicMaterial({
        map: fresnelTex,
        transparent: true,
        opacity: 0.52,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var fresnelMesh = new THREE.Mesh(fresnelGeom, fresnelMat);
      mainGroup.add(fresnelMesh);

      // ── Layer 5：中心聚能奇點十字星芒 (Singularity Pinpoint Flare - Z: 0.08) ──
      var starburstTex = createSingularityPinpointTexture(false);
      var starburstGeom = new THREE.PlaneGeometry(0.85, 0.85);
      var starburstMat = new THREE.MeshBasicMaterial({
        map: starburstTex,
        transparent: true,
        opacity: 0.90,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var starburstMesh = new THREE.Mesh(starburstGeom, starburstMat);
      starburstMesh.position.z = 0.08;
      mainGroup.add(starburstMesh);

      // ── Layer 6：多重獨立 3D 傾角科技星環 (3 條獨立空間傾角軌道) ──
      var ringTex1 = createMultiRingTechTexture(false, 1);
      var ringGeom1 = new THREE.PlaneGeometry(3.6, 3.6);
      var ringMat1 = new THREE.MeshBasicMaterial({
        map: ringTex1,
        transparent: true,
        opacity: 0.78,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var ringMesh1 = new THREE.Mesh(ringGeom1, ringMat1);
      ringMesh1.rotation.x = -Math.PI / 3.2;
      ringMesh1.rotation.y = 0.22;
      mainGroup.add(ringMesh1);

      var ringTex2 = createMultiRingTechTexture(false, 2);
      var ringGeom2 = new THREE.PlaneGeometry(3.9, 3.9);
      var ringMat2 = new THREE.MeshBasicMaterial({
        map: ringTex2,
        transparent: true,
        opacity: 0.68,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var ringMesh2 = new THREE.Mesh(ringGeom2, ringMat2);
      ringMesh2.rotation.x = Math.PI / 3.8;
      ringMesh2.rotation.y = -0.28;
      ringMesh2.rotation.z = -0.20;
      mainGroup.add(ringMesh2);

      var ringTex3 = createMultiRingTechTexture(false, 3);
      var ringGeom3 = new THREE.PlaneGeometry(4.3, 4.3);
      var ringMat3 = new THREE.MeshBasicMaterial({
        map: ringTex3,
        transparent: true,
        opacity: 0.55,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var ringMesh3 = new THREE.Mesh(ringGeom3, ringMat3);
      ringMesh3.rotation.x = -Math.PI / 2.4;
      ringMesh3.rotation.y = 0.10;
      mainGroup.add(ringMesh3);

      // ── Layer 7：全景 3D 發散星塵微粒力場 (1050 顆向外擴散微粒) ──
      var stardustTex = createStardustTexture();
      var pGeom = new THREE.BufferGeometry();
      var pPos = [];
      var pColors = [];
      var cWhite = new THREE.Color(0xFFFFFF);
      var cMagenta = new THREE.Color(0xFF2A85);
      var cPurple = new THREE.Color(0xC084FC);

      for (var j = 0; j < 1050; j++) {
        var rHost = 0.4 + Math.random() * 2.3;
        var thetaH = Math.random() * Math.PI * 2;
        var phiH = Math.acos(2 * Math.random() - 1);
        pPos.push(rHost * Math.sin(phiH) * Math.cos(thetaH), rHost * Math.sin(phiH) * Math.sin(thetaH), rHost * Math.cos(phiH));
        var colH = (rHost < 1.0) ? cWhite.clone().lerp(cMagenta, rHost / 1.0) : cMagenta.clone().lerp(cPurple, (rHost - 1.0) / 1.5);
        pColors.push(colH.r, colH.g, colH.b);
      }
      pGeom.setAttribute('position', new THREE.Float32BufferAttribute(pPos, 3));
      pGeom.setAttribute('color', new THREE.Float32BufferAttribute(pColors, 3));
      var pMat = new THREE.PointsMaterial({
        size: 0.044,
        map: stardustTex,
        vertexColors: true,
        transparent: true,
        opacity: 0.88,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var particles = new THREE.Points(pGeom, pMat);
      mainGroup.add(particles);

      // ── 加載 800px 超清原畫母版 ──
      var assets = window.SMU_PARTY_ORB_ASSETS || {};
      var hostUri = assets.hostArtworkWebp || assets.hostCore;

      loadLayerTexture(hostUri, 'assets/tutorial/orb_host_artwork_800.webp', function(tex) {
        masterMat.map = tex;
        masterMat.needsUpdate = true;
      });

      // ── Layer 8：動態迴圈與各層獨立自由運動 ──
      var currentSpeed = 0.0028;
      var targetSpeed = 0.0028;
      var scaleFactor = 1.0;
      var targetScale = 1.0;
      var animId = null;
      var clock = new THREE.Clock();

      var mouseTargetTiltX = 0;
      var mouseTargetTiltY = 0;

      function onMouseMove(e) {
        var rect = canvas.getBoundingClientRect();
        if (!rect || rect.width <= 0 || rect.height <= 0) return;
        var nx = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        var ny = -(((e.clientY - rect.top) / rect.height) * 2 - 1);
        if (isNaN(nx) || isNaN(ny)) return;
        mouseTargetTiltX = nx * 0.42;
        mouseTargetTiltY = ny * 0.36;
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

        if (isNaN(mouseTargetTiltX)) mouseTargetTiltX = 0;
        if (isNaN(mouseTargetTiltY)) mouseTargetTiltY = 0;

        currentSpeed = THREE.MathUtils.lerp(currentSpeed, targetSpeed, 0.06);
        scaleFactor = THREE.MathUtils.lerp(scaleFactor, targetScale, 0.06);
        mainGroup.scale.set(scaleFactor, scaleFactor, scaleFactor);

        // 主群組 3D 物理視差傾角
        mainGroup.rotation.y = THREE.MathUtils.lerp(mainGroup.rotation.y, mouseTargetTiltX, 0.07);
        mainGroup.rotation.x = THREE.MathUtils.lerp(mainGroup.rotation.x, -mouseTargetTiltY, 0.07);

        // 各層差異化視差與深度拉伸
        var px = mouseTargetTiltX;
        var py = -mouseTargetTiltY;
        coronaMesh.position.x = -px * 0.16;
        coronaMesh.position.y = -py * 0.12;
        ringMesh1.position.x = px * 0.18;
        ringMesh1.position.y = py * 0.14;
        ringMesh2.position.x = -px * 0.12;
        ringMesh2.position.y = -py * 0.10;
        ringMesh3.position.x = px * 0.26;
        ringMesh3.position.y = py * 0.20;

        // 1. 原畫母版緩慢自然呼吸
        var pulse = 1.0 + 0.022 * Math.sin(time * 1.5);
        masterMesh.scale.set(pulse, pulse, 1.0);

        // 2. 菲涅爾 3D 球膜真實三維自轉
        fresnelMesh.rotation.y -= currentSpeed * 0.65;
        fresnelMesh.rotation.x = 0.08 * Math.sin(time * 0.9);

        // 3. 雙向電漿動態對流
        plasmaMesh1.rotation.z += currentSpeed * 1.4;
        plasmaMesh2.rotation.z -= currentSpeed * 0.95;
        plasmaMat1.opacity = 0.30 + 0.08 * Math.sin(time * 1.9);
        plasmaMat2.opacity = 0.24 + 0.06 * Math.cos(time * 1.6);

        // 4. 中心聚能奇點十字星芒微動態
        var starPulse = 1.0 + 0.06 * Math.sin(time * 2.6);
        starburstMesh.scale.set(starPulse, starPulse, 1.0);
        starburstMesh.rotation.z += currentSpeed * 0.55;

        // 5. 三重星環差速交錯公轉 (宛如真實陀螺儀)
        ringMesh1.rotation.z -= currentSpeed * 1.3;
        ringMesh2.rotation.z += currentSpeed * 0.9;
        ringMesh3.rotation.z -= currentSpeed * 0.6;

        // 6. 發散光冕微自轉
        coronaMesh.rotation.z -= currentSpeed * 0.4;

        // 7. 星塵旋轉
        particles.rotation.z += currentSpeed * 1.4;

        renderer.render(scene, camera);
      }

      renderLoop();

      return {
        setHover: function(isHovered) {
          targetSpeed = isHovered ? 0.0078 : 0.0028;
          targetScale = isHovered ? 1.07 : 1.0;
        },
        destroy: function() {
          if (animId) cancelAnimationFrame(animId);
          canvas.removeEventListener('mousemove', onMouseMove);
          canvas.removeEventListener('mouseleave', onMouseLeave);
          coronaGeom.dispose();
          coronaMat.dispose();
          masterGeom.dispose();
          masterMat.dispose();
          plasmaGeom1.dispose();
          plasmaMat1.dispose();
          plasmaGeom2.dispose();
          plasmaMat2.dispose();
          fresnelGeom.dispose();
          fresnelMat.dispose();
          starburstGeom.dispose();
          starburstMat.dispose();
          ringGeom1.dispose();
          ringMat1.dispose();
          ringGeom2.dispose();
          ringMat2.dispose();
          ringGeom3.dispose();
          ringMat3.dispose();
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
    }, 50);
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
