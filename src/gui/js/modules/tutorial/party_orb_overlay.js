/**
 * Steam Manifest Updater - 組隊教學 3D 全息星核選擇層 (Three.js WebGL 3A 旗艦旗艦版)
 * 1:1 極限還原 Gemini_Generated_Image_m2o88sm2o88sm2o8.jpg 概念原畫：
 * 
 * 🎨 原畫高保真多圖層立體 3D 架構 (Master High-Detail Volumetric 3D Pipeline):
 *  1. 【深空環境引力場光暈】(Ambient Gravity Halo - Z: -0.8，遠景反向拉伸深度)
 *  2. 【原畫母版高保真視覺核心】(Master Artwork Plane - 100% 忠實呈現原畫極致細節、全息刻度與星雲)
 *  3. 【3D 立體能量光膜球體】(Volumetric 3D Energy Core Sphere - SphereGeometry 64x48 真實幾何球面曲率)
 *  4. 【內部引力奇點十字星芒耀斑】(Singularity Starburst Flare - Z: 0.04，心跳脈衝與獨立自轉)
 *  5. 【雙層逆向流動電漿旋臂】(Swirling Volumetric Plasma - 順逆雙向旋轉體積流體視差，無任何硬線稿)
 *  6. 【立體 3D 傾角科技星環盤】(Artwork 3D Orbit Ring Disk - RingGeometry 空間大角度橫跨公轉，純原畫光學質感)
 *  7. 【全景 3D 浮動星塵微粒力場】(Volumetric Stardust Swarm - 950 顆具備真實 Z 軸深度粒子)
 *  8. 【滑鼠多層次差異化 3D 物理視差】(Differential Parallax System - 隨滑鼠移動產生層層錯位的極致深邃感)
 * 
 * 🚫 徹底杜絕任何粗硬人工線稿、線框幾何籠子與密集硬刻度，100% 呈現原畫奢華純淨的 3A 宇宙星核！
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
     ✨ 動態光學紋理生成 (Pure Optical FX Generators - 100% 無硬線條)
     ========================================================================== */

  /**
   * 1. 高斯羽化微光星塵紋理
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

  /**
   * 2. 中心十字星芒奇點光暈 (Cross Starburst Flare)
   */
  function createCrossStarburstTexture(isCyan) {
    var canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 256;
    var ctx = canvas.getContext('2d');
    var cx = 128;
    var cy = 128;

    ctx.clearRect(0, 0, 256, 256);

    // 寬柔和圓形外暈
    var gSoft = ctx.createRadialGradient(cx, cy, 0, cx, cy, 115);
    gSoft.addColorStop(0, 'rgba(255, 255, 255, 0.95)');
    gSoft.addColorStop(0.2, isCyan ? 'rgba(0, 245, 255, 0.65)' : 'rgba(255, 130, 200, 0.65)');
    gSoft.addColorStop(0.5, isCyan ? 'rgba(14, 165, 233, 0.25)' : 'rgba(255, 42, 133, 0.25)');
    gSoft.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = gSoft;
    ctx.beginPath();
    ctx.arc(cx, cy, 115, 0, Math.PI * 2);
    ctx.fill();

    // 水平銳利長星芒
    var gH = ctx.createLinearGradient(0, cy, 256, cy);
    gH.addColorStop(0, 'rgba(255, 255, 255, 0)');
    gH.addColorStop(0.35, isCyan ? 'rgba(0, 245, 255, 0.55)' : 'rgba(255, 140, 210, 0.55)');
    gH.addColorStop(0.5, 'rgba(255, 255, 255, 1)');
    gH.addColorStop(0.65, isCyan ? 'rgba(0, 245, 255, 0.55)' : 'rgba(255, 140, 210, 0.55)');
    gH.addColorStop(1, 'rgba(255, 255, 255, 0)');
    ctx.fillStyle = gH;
    ctx.fillRect(6, cy - 2, 244, 4);

    // 垂直銳利長星芒
    var gV = ctx.createLinearGradient(cx, 0, cx, 256);
    gV.addColorStop(0, 'rgba(255, 255, 255, 0)');
    gV.addColorStop(0.35, isCyan ? 'rgba(0, 245, 255, 0.55)' : 'rgba(255, 140, 210, 0.55)');
    gV.addColorStop(0.5, 'rgba(255, 255, 255, 1)');
    gV.addColorStop(0.65, isCyan ? 'rgba(0, 245, 255, 0.55)' : 'rgba(255, 140, 210, 0.55)');
    gV.addColorStop(1, 'rgba(255, 255, 255, 0)');
    ctx.fillStyle = gV;
    ctx.fillRect(cx - 2, 6, 4, 244);

    // 45 度次級斜星芒
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(Math.PI / 4);
    var gD = ctx.createLinearGradient(-85, 0, 85, 0);
    gD.addColorStop(0, 'rgba(255, 255, 255, 0)');
    gD.addColorStop(0.5, 'rgba(255, 255, 255, 0.9)');
    gD.addColorStop(1, 'rgba(255, 255, 255, 0)');
    ctx.fillStyle = gD;
    ctx.fillRect(-85, -1.5, 170, 3);
    ctx.rotate(Math.PI / 2);
    ctx.fillRect(-85, -1.5, 170, 3);
    ctx.restore();

    // 中心白熾核
    var gCore = ctx.createRadialGradient(cx, cy, 0, cx, cy, 22);
    gCore.addColorStop(0, '#FFFFFF');
    gCore.addColorStop(0.5, isCyan ? '#E0F7FF' : '#FFE4F0');
    gCore.addColorStop(1, 'rgba(255, 255, 255, 0)');
    ctx.fillStyle = gCore;
    ctx.beginPath();
    ctx.arc(cx, cy, 22, 0, Math.PI * 2);
    ctx.fill();

    var tex = new THREE.CanvasTexture(canvas);
    tex.needsUpdate = true;
    return tex;
  }

  /**
   * 3. 背景環境引力場光暈紋理 (Ambient Gravity Halo)
   */
  function createAmbientHaloTexture(isCyan) {
    var canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 256;
    var ctx = canvas.getContext('2d');
    var cx = 128;
    var cy = 128;

    var grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, 126);
    if (isCyan) {
      grad.addColorStop(0, 'rgba(0, 245, 255, 0.55)');
      grad.addColorStop(0.35, 'rgba(14, 165, 233, 0.32)');
      grad.addColorStop(0.7, 'rgba(2, 132, 199, 0.1)');
      grad.addColorStop(1, 'rgba(0, 0, 0, 0)');
    } else {
      grad.addColorStop(0, 'rgba(255, 42, 133, 0.55)');
      grad.addColorStop(0.35, 'rgba(192, 132, 252, 0.32)');
      grad.addColorStop(0.7, 'rgba(147, 51, 234, 0.1)');
      grad.addColorStop(1, 'rgba(0, 0, 0, 0)');
    }
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 256, 256);

    var tex = new THREE.CanvasTexture(canvas);
    tex.needsUpdate = true;
    return tex;
  }

  /**
   * 4. 柔和動態星環光帶紋理 (Smooth Glowing Arc Ring Texture - 零生硬刻度)
   */
  function createSmoothGlowRingTexture(isCyan) {
    var canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 64;
    var ctx = canvas.getContext('2d');

    ctx.clearRect(0, 0, 512, 64);

    // 圓弧流光漸變，具備平滑淡入淡出段落
    var grad = ctx.createLinearGradient(0, 0, 512, 0);
    if (isCyan) {
      grad.addColorStop(0, 'rgba(0, 245, 255, 0)');
      grad.addColorStop(0.15, 'rgba(0, 245, 255, 0.7)');
      grad.addColorStop(0.4, 'rgba(255, 255, 255, 0.95)');
      grad.addColorStop(0.65, 'rgba(14, 165, 233, 0.75)');
      grad.addColorStop(0.85, 'rgba(0, 245, 255, 0.4)');
      grad.addColorStop(1, 'rgba(0, 245, 255, 0)');
    } else {
      grad.addColorStop(0, 'rgba(255, 42, 133, 0)');
      grad.addColorStop(0.15, 'rgba(255, 100, 180, 0.7)');
      grad.addColorStop(0.4, 'rgba(255, 255, 255, 0.95)');
      grad.addColorStop(0.65, 'rgba(192, 132, 252, 0.75)');
      grad.addColorStop(0.85, 'rgba(255, 42, 133, 0.4)');
      grad.addColorStop(1, 'rgba(255, 42, 133, 0)');
    }

    ctx.fillStyle = grad;
    ctx.fillRect(0, 16, 512, 32);

    // 兩側高斯柔邊羽化
    var vGrad = ctx.createLinearGradient(0, 0, 0, 64);
    vGrad.addColorStop(0, 'rgba(0, 0, 0, 0)');
    vGrad.addColorStop(0.5, 'rgba(255, 255, 255, 1)');
    vGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.globalCompositeOperation = 'destination-in';
    ctx.fillStyle = vGrad;
    ctx.fillRect(0, 0, 512, 64);

    var tex = new THREE.CanvasTexture(canvas);
    tex.wrapS = THREE.RepeatWrapping;
    tex.wrapT = THREE.ClampToEdgeWrapping;
    tex.needsUpdate = true;
    return tex;
  }

  /* ==========================================================================
     🔵 左星核初始化：天青全息晶核 (PROTOCOL // SQUAD JOIN) - 1:1 原畫 3A 純淨版
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

      // ── Layer 1：深空引力場環境光暈 (Ambient Halo - Z: -0.8) ──
      var haloTex = createAmbientHaloTexture(true);
      var haloGeom = new THREE.PlaneGeometry(5.6, 5.6);
      var haloMat = new THREE.MeshBasicMaterial({
        map: haloTex,
        transparent: true,
        opacity: 0.45,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var haloMesh = new THREE.Mesh(haloGeom, haloMat);
      haloMesh.position.z = -0.8;
      mainGroup.add(haloMesh);

      // ── Layer 2：原畫母版高保真視覺核心 (Master High-Detail Artwork Plane) ──
      var masterGeom = new THREE.PlaneGeometry(3.68, 3.68);
      var masterMat = new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 1.0,
        blending: THREE.NormalBlending,
        depthWrite: false
      });
      var masterMesh = new THREE.Mesh(masterGeom, masterMat);
      mainGroup.add(masterMesh);

      // ── Layer 3：3D 立體能量光膜球體 (Volumetric 3D Energy Core Sphere - 真實球面曲率) ──
      var coreGlowGeom = new THREE.SphereGeometry(1.42, 64, 48);
      var coreGlowMat = new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 0.46,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var coreGlowMesh = new THREE.Mesh(coreGlowGeom, coreGlowMat);
      mainGroup.add(coreGlowMesh);

      // ── Layer 4：奇點白熾十字星芒耀斑 (Singularity Starburst - Z: 0.04) ──
      var starburstTex = createCrossStarburstTexture(true);
      var starburstGeom = new THREE.PlaneGeometry(1.45, 1.45);
      var starburstMat = new THREE.MeshBasicMaterial({
        map: starburstTex,
        transparent: true,
        opacity: 0.94,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var starburstMesh = new THREE.Mesh(starburstGeom, starburstMat);
      starburstMesh.position.z = 0.04;
      mainGroup.add(starburstMesh);

      // ── Layer 5：雙層動態流體電漿旋臂 (Swirling Volumetric Plasma - 順逆雙向流動視差) ──
      var plasmaGeom1 = new THREE.PlaneGeometry(3.1, 3.1);
      var plasmaMat1 = new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 0.72,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var plasmaMesh1 = new THREE.Mesh(plasmaGeom1, plasmaMat1);
      plasmaMesh1.position.z = 0.10;
      mainGroup.add(plasmaMesh1);

      var plasmaGeom2 = new THREE.PlaneGeometry(2.85, 2.85);
      var plasmaMat2 = new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 0.48,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var plasmaMesh2 = new THREE.Mesh(plasmaGeom2, plasmaMat2);
      plasmaMesh2.position.z = -0.06;
      plasmaMesh2.rotation.x = 0.18;
      mainGroup.add(plasmaMesh2);

      // ── Layer 6：3D 傾角柔光科技星環 (Smooth 3D Orbit Ring Disk - 空間橫跨公轉) ──
      var ringTex = createSmoothGlowRingTexture(true);
      var artworkRingGeom = new THREE.RingGeometry(1.68, 2.45, 96);
      var artworkRingMat = new THREE.MeshBasicMaterial({
        map: ringTex,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.88,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var artworkRingMesh = new THREE.Mesh(artworkRingGeom, artworkRingMat);
      artworkRingMesh.rotation.x = Math.PI / 3.2;
      artworkRingMesh.rotation.y = 0.15;
      mainGroup.add(artworkRingMesh);

      // ── Layer 7：全景 3D 浮動星塵微粒力場 (950 顆具備真實 Z 軸深度粒子) ──
      var stardustTex = createStardustTexture();
      var pGeom = new THREE.BufferGeometry();
      var pPos = [];
      var pColors = [];
      var cWhite = new THREE.Color(0xFFFFFF);
      var cCyan = new THREE.Color(0x00F5FF);
      var cBlue = new THREE.Color(0x38BDF8);

      for (var i = 0; i < 950; i++) {
        var r = 0.4 + Math.random() * 2.2;
        var thetaP = Math.random() * Math.PI * 2;
        var phiP = Math.acos(2 * Math.random() - 1);
        pPos.push(r * Math.sin(phiP) * Math.cos(thetaP), r * Math.sin(phiP) * Math.sin(thetaP), r * Math.cos(phiP));
        var colP = (r < 1.0) ? cWhite.clone().lerp(cCyan, r / 1.0) : cCyan.clone().lerp(cBlue, (r - 1.0) / 1.4);
        pColors.push(colP.r, colP.g, colP.b);
      }
      pGeom.setAttribute('position', new THREE.Float32BufferAttribute(pPos, 3));
      pGeom.setAttribute('color', new THREE.Float32BufferAttribute(pColors, 3));
      var pMat = new THREE.PointsMaterial({
        size: 0.044,
        map: stardustTex,
        vertexColors: true,
        transparent: true,
        opacity: 0.9,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var particles = new THREE.Points(pGeom, pMat);
      mainGroup.add(particles);

      // ── 加載 100% 高清原畫母版 ──
      var assets = window.SMU_PARTY_ORB_ASSETS || {};
      var joinUri = assets.joinArtworkWebp || assets.joinCore;
      
      loadLayerTexture(joinUri, 'assets/tutorial/orb_join_artwork_800.webp', function(tex) {
        masterMat.map = tex;
        masterMat.needsUpdate = true;
        coreGlowMat.map = tex;
        coreGlowMat.needsUpdate = true;
        plasmaMat1.map = tex;
        plasmaMat1.needsUpdate = true;
        plasmaMat2.map = tex;
        plasmaMat2.needsUpdate = true;
      });

      // ── Layer 8：動態迴圈與滑鼠多層次差異化 3D 視差傾角互動 ──
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
        mouseTargetTiltX = nx * 0.44;
        mouseTargetTiltY = ny * 0.38;
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

        // 多層次差異化視差補償 (Differential Parallax Gradient)
        var px = mouseTargetTiltX;
        var py = -mouseTargetTiltY;
        artworkRingMesh.position.x = px * 0.22;
        artworkRingMesh.position.y = py * 0.18;
        plasmaMesh1.position.x = px * 0.08;
        plasmaMesh1.position.y = py * 0.06;
        haloMesh.position.x = -px * 0.15; // 背景遠景反向拉伸深度
        haloMesh.position.y = -py * 0.12;

        // 原畫主體自轉微調與呼吸
        var pulse = 1.0 + 0.038 * Math.sin(time * 1.8);
        masterMesh.scale.set(pulse, pulse, 1.0);
        coreGlowMesh.scale.set(pulse * 1.02, pulse * 1.02, pulse * 1.02);
        coreGlowMesh.rotation.y += currentSpeed * 0.5;
        coreGlowMat.opacity = 0.42 + 0.18 * Math.sin(time * 2.2);

        // 奇點十字星芒脈衝閃爍與微轉動
        var starPulse = 1.0 + 0.08 * Math.sin(time * 2.6);
        starburstMesh.scale.set(starPulse, starPulse, 1.0);
        starburstMesh.rotation.z += currentSpeed * 0.6;

        // 雙電漿雲盤逆向差速公轉 (立體體積流動視差)
        plasmaMesh1.rotation.z -= currentSpeed * 1.35;
        plasmaMesh2.rotation.z += currentSpeed * 0.95;
        plasmaMat1.opacity = 0.72 + 0.18 * Math.sin(time * 1.9);
        plasmaMat2.opacity = 0.48 + 0.16 * Math.cos(time * 1.6);

        // 3D 科技光環公轉
        artworkRingMesh.rotation.z += currentSpeed * 1.15;

        // 星塵旋轉
        particles.rotation.y += currentSpeed * 0.65;

        renderer.render(scene, camera);
      }

      renderLoop();

      return {
        setHover: function(isHovered) {
          targetSpeed = isHovered ? 0.0082 : 0.0028;
          targetScale = isHovered ? 1.08 : 1.0;
        },
        destroy: function() {
          if (animId) cancelAnimationFrame(animId);
          canvas.removeEventListener('mousemove', onMouseMove);
          canvas.removeEventListener('mouseleave', onMouseLeave);
          haloGeom.dispose();
          haloMat.dispose();
          masterGeom.dispose();
          masterMat.dispose();
          coreGlowGeom.dispose();
          coreGlowMat.dispose();
          starburstGeom.dispose();
          starburstMat.dispose();
          plasmaGeom1.dispose();
          plasmaMat1.dispose();
          plasmaGeom2.dispose();
          plasmaMat2.dispose();
          artworkRingGeom.dispose();
          artworkRingMat.dispose();
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
     🟣 右星核初始化：霓虹紫紅星核 (PROTOCOL // SQUAD HOST) - 1:1 原畫 3A 純淨版
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

      // ── Layer 1：深空引力場環境光暈 (Ambient Halo - Z: -0.8) ──
      var haloTex = createAmbientHaloTexture(false);
      var haloGeom = new THREE.PlaneGeometry(5.6, 5.6);
      var haloMat = new THREE.MeshBasicMaterial({
        map: haloTex,
        transparent: true,
        opacity: 0.45,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var haloMesh = new THREE.Mesh(haloGeom, haloMat);
      haloMesh.position.z = -0.8;
      mainGroup.add(haloMesh);

      // ── Layer 2：原畫母版高保真視覺核心 (Master High-Detail Artwork Plane) ──
      var masterGeom = new THREE.PlaneGeometry(3.68, 3.68);
      var masterMat = new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 1.0,
        blending: THREE.NormalBlending,
        depthWrite: false
      });
      var masterMesh = new THREE.Mesh(masterGeom, masterMat);
      mainGroup.add(masterMesh);

      // ── Layer 3：3D 立體能量光膜球體 (Volumetric 3D Energy Core Sphere - 真實球面曲率) ──
      var coreGlowGeom = new THREE.SphereGeometry(1.42, 64, 48);
      var coreGlowMat = new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 0.48,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var coreGlowMesh = new THREE.Mesh(coreGlowGeom, coreGlowMat);
      mainGroup.add(coreGlowMesh);

      // ── Layer 4：奇點白熾十字星芒耀斑 (Singularity Starburst - Z: 0.04) ──
      var starburstTex = createCrossStarburstTexture(false);
      var starburstGeom = new THREE.PlaneGeometry(1.5, 1.5);
      var starburstMat = new THREE.MeshBasicMaterial({
        map: starburstTex,
        transparent: true,
        opacity: 0.96,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var starburstMesh = new THREE.Mesh(starburstGeom, starburstMat);
      starburstMesh.position.z = 0.04;
      mainGroup.add(starburstMesh);

      // ── Layer 5：雙層動態流體電漿旋臂 (Swirling Volumetric Plasma - 順逆雙向流動視差) ──
      var plasmaGeom1 = new THREE.PlaneGeometry(3.15, 3.15);
      var plasmaMat1 = new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 0.74,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var plasmaMesh1 = new THREE.Mesh(plasmaGeom1, plasmaMat1);
      plasmaMesh1.position.z = 0.10;
      mainGroup.add(plasmaMesh1);

      var plasmaGeom2 = new THREE.PlaneGeometry(2.9, 2.9);
      var plasmaMat2 = new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 0.52,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var plasmaMesh2 = new THREE.Mesh(plasmaGeom2, plasmaMat2);
      plasmaMesh2.position.z = -0.06;
      plasmaMesh2.rotation.x = -0.20;
      mainGroup.add(plasmaMesh2);

      // ── Layer 6：3D 傾角柔光科技星環 (Smooth 3D Orbit Ring Disk - 空間橫跨公轉) ──
      var ringTex = createSmoothGlowRingTexture(false);
      var artworkRingGeom = new THREE.RingGeometry(1.68, 2.45, 96);
      var artworkRingMat = new THREE.MeshBasicMaterial({
        map: ringTex,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.88,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var artworkRingMesh = new THREE.Mesh(artworkRingGeom, artworkRingMat);
      artworkRingMesh.rotation.x = -Math.PI / 3.4;
      artworkRingMesh.rotation.y = 0.22;
      mainGroup.add(artworkRingMesh);

      // ── Layer 7：全景 3D 浮動星塵微粒力場 (950 顆向心星粒) ──
      var stardustTex = createStardustTexture();
      var pGeom = new THREE.BufferGeometry();
      var pPos = [];
      var pColors = [];
      var cWhite = new THREE.Color(0xFFFFFF);
      var cMagenta = new THREE.Color(0xFF2A85);
      var cPurple = new THREE.Color(0xC084FC);

      for (var j = 0; j < 950; j++) {
        var rHost = 0.4 + Math.random() * 2.2;
        var thetaH = Math.random() * Math.PI * 2;
        var phiH = Math.acos(2 * Math.random() - 1);
        pPos.push(rHost * Math.sin(phiH) * Math.cos(thetaH), rHost * Math.sin(phiH) * Math.sin(thetaH), rHost * Math.cos(phiH));
        var colH = (rHost < 1.0) ? cWhite.clone().lerp(cMagenta, rHost / 1.0) : cMagenta.clone().lerp(cPurple, (rHost - 1.0) / 1.4);
        pColors.push(colH.r, colH.g, colH.b);
      }
      pGeom.setAttribute('position', new THREE.Float32BufferAttribute(pPos, 3));
      pGeom.setAttribute('color', new THREE.Float32BufferAttribute(pColors, 3));
      var pMat = new THREE.PointsMaterial({
        size: 0.046,
        map: stardustTex,
        vertexColors: true,
        transparent: true,
        opacity: 0.9,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var particles = new THREE.Points(pGeom, pMat);
      mainGroup.add(particles);

      // ── 加載 100% 高清原畫母版 ──
      var assets = window.SMU_PARTY_ORB_ASSETS || {};
      var hostUri = assets.hostArtworkWebp || assets.hostCore;

      loadLayerTexture(hostUri, 'assets/tutorial/orb_host_artwork_800.webp', function(tex) {
        masterMat.map = tex;
        masterMat.needsUpdate = true;
        coreGlowMat.map = tex;
        coreGlowMat.needsUpdate = true;
        plasmaMat1.map = tex;
        plasmaMat1.needsUpdate = true;
        plasmaMat2.map = tex;
        plasmaMat2.needsUpdate = true;
      });

      // ── Layer 8：動態迴圈與滑鼠多層次差異化 3D 視差傾角互動 ──
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
        mouseTargetTiltX = nx * 0.44;
        mouseTargetTiltY = ny * 0.38;
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

        // 多層次差異化視差補償 (Differential Parallax Gradient)
        var px = mouseTargetTiltX;
        var py = -mouseTargetTiltY;
        artworkRingMesh.position.x = px * 0.22;
        artworkRingMesh.position.y = py * 0.18;
        plasmaMesh1.position.x = px * 0.08;
        plasmaMesh1.position.y = py * 0.06;
        haloMesh.position.x = -px * 0.15; // 背景遠景反向拉伸深度
        haloMesh.position.y = -py * 0.12;

        // 原畫主體自轉微調與呼吸
        var pulse = 1.0 + 0.038 * Math.sin(time * 1.8);
        masterMesh.scale.set(pulse, pulse, 1.0);
        coreGlowMesh.scale.set(pulse * 1.02, pulse * 1.02, pulse * 1.02);
        coreGlowMesh.rotation.y -= currentSpeed * 0.5;
        coreGlowMat.opacity = 0.44 + 0.18 * Math.sin(time * 2.2);

        // 十字星芒光爆旋轉與脈動
        var starPulse = 1.0 + 0.08 * Math.sin(time * 2.4);
        starburstMesh.scale.set(starPulse, starPulse, 1.0);
        starburstMesh.rotation.z += currentSpeed * 0.5;

        // 雙電漿雲盤逆向差速公轉 (立體體積流動視差)
        plasmaMesh1.rotation.z += currentSpeed * 1.4;
        plasmaMesh2.rotation.z -= currentSpeed * 0.9;
        plasmaMat1.opacity = 0.74 + 0.18 * Math.sin(time * 2.0);
        plasmaMat2.opacity = 0.50 + 0.16 * Math.cos(time * 1.7);

        // 3D 科技光環公轉
        artworkRingMesh.rotation.z -= currentSpeed * 1.2;

        // 星塵旋轉
        particles.rotation.z += currentSpeed * 1.5;

        renderer.render(scene, camera);
      }

      renderLoop();

      return {
        setHover: function(isHovered) {
          targetSpeed = isHovered ? 0.0082 : 0.0028;
          targetScale = isHovered ? 1.08 : 1.0;
        },
        destroy: function() {
          if (animId) cancelAnimationFrame(animId);
          canvas.removeEventListener('mousemove', onMouseMove);
          canvas.removeEventListener('mouseleave', onMouseLeave);
          haloGeom.dispose();
          haloMat.dispose();
          masterGeom.dispose();
          masterMat.dispose();
          coreGlowGeom.dispose();
          coreGlowMat.dispose();
          starburstGeom.dispose();
          starburstMat.dispose();
          plasmaGeom1.dispose();
          plasmaMat1.dispose();
          plasmaGeom2.dispose();
          plasmaMat2.dispose();
          artworkRingGeom.dispose();
          artworkRingMat.dispose();
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
