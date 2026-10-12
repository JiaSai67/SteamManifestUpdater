/**
 * Steam Manifest Updater - 組隊教學 3D 全息星核選擇層 (Three.js WebGL 3A 旗艦旗艦版)
 * 1:1 極限還原 Gemini_Generated_Image_m2o88sm2o88sm2o8.jpg 概念原畫：
 * 
 * 🎨 概念原畫實質分層拆解與多維三維運動管線 (Fully Decomposed Multi-Layer Volumetric 3D Pipeline):
 *  🚫 徹底告別「整張原圖當單一圖層貼上」！本版本將原畫實質切割分離為多個獨立 Alpha 透明紋理：
 * 
 *  1. 【深空發散引力光冕】(Radiating Dispersing Corona - Z: -0.9)
 *     - 32 道向外發散的微細羽化射線，營造深空星系向外輻射的深邃光冕。
 *  2. 【最外層透明球體晶罩】(Outer Glass Shield Shell - Z: -0.04)
 *     - 獨立原畫外層玻璃力場與微光晶泡 (orb_join_glass / orb_host_glass)，獨立微晃律動。
 *  3. 【獨立 3D 大傾角星環層】(Extracted 3D Orbit Rings - Z: 0.0)
 *     - 獨立原畫大傾角星環 (orb_join_rings / orb_host_rings)，中心 100% 鏤空透明！
 *     - 以 3D 空間傾角大角度橫跨前後空間公轉，環繞球體穿梭。
 *  4. 【次級反向傾角科技陀螺環】(Counter-Tilted Gyro Orbit Ring 2 - Z: 0.0)
 *     - 反向傾角獨立公轉軌道，與星環層在空間中形成精密交織的陀螺儀力場。
 *  5. 【純幾何天體晶球層】(Pure Core Celestial Sphere - Z: 0.0)
 *     - 獨立原畫球體 (orb_join_sphere / orb_host_sphere)，純淨無外環干擾。
 *     - 結合 3D 幾何菲涅爾曲面光膜 (SphereGeometry 64x48)，球體獨立圍繞 Y 軸自轉！
 *  6. 【中心發散流光與星雲核心】(Radiating Central Plasma & Nebula Streamers - Z: 0.05)
 *     - 獨立原畫核心流光 (orb_join_plasma / orb_host_plasma)，中心聚能發散。
 *     - 獨立高速反向旋轉與心跳呼吸脈衝，呈現生生不息的星核流體活力。
 *  7. 【奇點白熾聚能十字星芒】(Singularity Pinpoint Starburst - Z: 0.08)
 *     - 聚焦微型超新星耀斑，點綴星核中心。
 *  8. 【全景 3D 發散星塵微粒力場】(Dispersing Quantum Stardust - 1050 顆微粒)
 *  9. 【滑鼠多層次物理視差梯度系統】(Differential Parallax System)
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
   */
  function createRadiatingCoronaTexture(isCyan) {
    var canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    var ctx = canvas.getContext('2d');
    var cx = 256;
    var cy = 256;

    var baseGrad = ctx.createRadialGradient(cx, cy, 30, cx, cy, 250);
    if (isCyan) {
      baseGrad.addColorStop(0, 'rgba(0, 245, 255, 0.32)');
      baseGrad.addColorStop(0.35, 'rgba(14, 165, 233, 0.16)');
      baseGrad.addColorStop(0.7, 'rgba(2, 132, 199, 0.05)');
      baseGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');
    } else {
      baseGrad.addColorStop(0, 'rgba(255, 42, 133, 0.32)');
      baseGrad.addColorStop(0.35, 'rgba(192, 132, 252, 0.16)');
      baseGrad.addColorStop(0.7, 'rgba(147, 51, 234, 0.05)');
      baseGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');
    }
    ctx.fillStyle = baseGrad;
    ctx.fillRect(0, 0, 512, 512);

    // 32 道向外發散的羽化射線
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
        rayGrad.addColorStop(0.2, 'rgba(0, 245, 255, 0.30)');
        rayGrad.addColorStop(0.6, 'rgba(56, 189, 248, 0.16)');
        rayGrad.addColorStop(1, 'rgba(0, 245, 255, 0)');
      } else {
        rayGrad.addColorStop(0, 'rgba(255, 42, 133, 0)');
        rayGrad.addColorStop(0.2, 'rgba(255, 42, 133, 0.30)');
        rayGrad.addColorStop(0.6, 'rgba(216, 180, 254, 0.16)');
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
   * 中心 70% 完全透明留空，僅在外緣產生 3D 幾何邊界曲率光
   */
  function createFresnelSphereTexture(isCyan) {
    var canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    var ctx = canvas.getContext('2d');
    var cx = 256;
    var cy = 256;

    ctx.clearRect(0, 0, 512, 512);

    var grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, 256);
    grad.addColorStop(0, 'rgba(0, 0, 0, 0)');
    grad.addColorStop(0.70, 'rgba(0, 0, 0, 0)');
    if (isCyan) {
      grad.addColorStop(0.85, 'rgba(0, 245, 255, 0.22)');
      grad.addColorStop(0.95, 'rgba(0, 245, 255, 0.60)');
      grad.addColorStop(0.99, 'rgba(255, 255, 255, 0.85)');
      grad.addColorStop(1.0, 'rgba(0, 245, 255, 0)');
    } else {
      grad.addColorStop(0.85, 'rgba(255, 42, 133, 0.22)');
      grad.addColorStop(0.95, 'rgba(255, 42, 133, 0.60)');
      grad.addColorStop(0.99, 'rgba(255, 255, 255, 0.85)');
      grad.addColorStop(1.0, 'rgba(0, 245, 255, 0)');
    }
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 512, 512);

    var tex = new THREE.CanvasTexture(canvas);
    tex.needsUpdate = true;
    return tex;
  }

  /**
   * 3. 獨立 3D 科技陀螺軌道環紋理 (Multi-Ring Gyro Tech Texture)
   */
  function createMultiRingTechTexture(isCyan) {
    var canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    var ctx = canvas.getContext('2d');
    var cx = 256;
    var cy = 256;

    ctx.clearRect(0, 0, 512, 512);

    var primaryColor = isCyan ? '#00F5FF' : '#FF2A85';
    var softColor = isCyan ? 'rgba(0, 245, 255, 0.35)' : 'rgba(255, 42, 133, 0.35)';

    var r = 216;
    ctx.strokeStyle = softColor;
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.stroke();

    ctx.strokeStyle = primaryColor;
    ctx.lineWidth = 2.4;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0.8, 2.3);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx, cy, r, Math.PI + 0.8, Math.PI + 2.3);
    ctx.stroke();

    ctx.strokeStyle = softColor;
    ctx.lineWidth = 0.9;
    ctx.beginPath();
    ctx.arc(cx, cy, r + 7, -0.5, 1.8);
    ctx.stroke();

    var tex = new THREE.CanvasTexture(canvas);
    tex.needsUpdate = true;
    return tex;
  }

  /**
   * 4. 聚焦奇點白熾十字星芒 (Singularity Pinpoint Flare)
   */
  function createSingularityPinpointTexture(isCyan) {
    var canvas = document.createElement('canvas');
    canvas.width = 128;
    canvas.height = 128;
    var ctx = canvas.getContext('2d');
    var cx = 64;
    var cy = 64;

    ctx.clearRect(0, 0, 128, 128);

    var gCore = ctx.createRadialGradient(cx, cy, 0, cx, cy, 18);
    gCore.addColorStop(0, '#FFFFFF');
    gCore.addColorStop(0.35, isCyan ? 'rgba(0, 245, 255, 0.85)' : 'rgba(255, 120, 200, 0.85)');
    gCore.addColorStop(0.8, isCyan ? 'rgba(14, 165, 233, 0.25)' : 'rgba(192, 132, 252, 0.25)');
    gCore.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = gCore;
    ctx.beginPath();
    ctx.arc(cx, cy, 18, 0, Math.PI * 2);
    ctx.fill();

    var gH = ctx.createLinearGradient(0, cy, 128, cy);
    gH.addColorStop(0, 'rgba(255, 255, 255, 0)');
    gH.addColorStop(0.45, isCyan ? 'rgba(0, 245, 255, 0.6)' : 'rgba(255, 140, 210, 0.6)');
    gH.addColorStop(0.5, '#FFFFFF');
    gH.addColorStop(0.55, isCyan ? 'rgba(0, 245, 255, 0.6)' : 'rgba(255, 140, 210, 0.6)');
    gH.addColorStop(1, 'rgba(255, 255, 255, 0)');
    ctx.fillStyle = gH;
    ctx.fillRect(4, cy - 1, 120, 2);

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
   * 5. 高斯羽化微光星塵紋理
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
     🔵 左星核初始化：天青全息晶核 (PROTOCOL // SQUAD JOIN) - 100% 實質分層拆解
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

      // ── Layer 2：最外層透明球體晶罩 (Extracted Outer Glass Shield Shell - Z: -0.04) ──
      var glassGeom = new THREE.PlaneGeometry(3.7, 3.7);
      var glassMat = new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 0.65,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var glassMesh = new THREE.Mesh(glassGeom, glassMat);
      glassMesh.position.z = -0.04;
      mainGroup.add(glassMesh);

      // ── Layer 3：獨立 3D 大傾角星環層 (Extracted 3D Orbit Rings - 中心鏤空，空間穿梭公轉) ──
      var ringGeom1 = new THREE.PlaneGeometry(3.6, 3.6);
      var ringMat1 = new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 0.95,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var ringMesh1 = new THREE.Mesh(ringGeom1, ringMat1);
      ringMesh1.rotation.x = Math.PI / 3.2;
      ringMesh1.rotation.y = 0.20;
      mainGroup.add(ringMesh1);

      // ── Layer 4：次級反向傾角科技陀螺環 (Counter-Tilted Gyro Tech Ring - Z: 0.0) ──
      var gyroRingTex = createMultiRingTechTexture(true);
      var gyroRingGeom = new THREE.PlaneGeometry(3.9, 3.9);
      var gyroRingMat = new THREE.MeshBasicMaterial({
        map: gyroRingTex,
        transparent: true,
        opacity: 0.68,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var gyroRingMesh = new THREE.Mesh(gyroRingGeom, gyroRingMat);
      gyroRingMesh.rotation.x = -Math.PI / 3.8;
      gyroRingMesh.rotation.y = -0.28;
      gyroRingMesh.rotation.z = 0.20;
      mainGroup.add(gyroRingMesh);

      // ── Layer 5：純幾何天體晶球層 (Pure Core Celestial Sphere - 獨立 Y 軸自轉) ──
      // 5-A: 原畫獨立球體視覺面 (NormalBlending 保證細節清晰)
      var sphereGeom = new THREE.PlaneGeometry(2.32, 2.32);
      var sphereMat = new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 1.0,
        blending: THREE.NormalBlending,
        depthWrite: false
      });
      var sphereMesh = new THREE.Mesh(sphereGeom, sphereMat);
      mainGroup.add(sphereMesh);

      // 5-B: 3D 幾何菲涅爾球面晶膜 (SphereGeometry 64x48)
      var fresnelTex = createFresnelSphereTexture(true);
      var fresnelGeom = new THREE.SphereGeometry(1.22, 64, 48);
      var fresnelMat = new THREE.MeshBasicMaterial({
        map: fresnelTex,
        transparent: true,
        opacity: 0.55,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var fresnelMesh = new THREE.Mesh(fresnelGeom, fresnelMat);
      mainGroup.add(fresnelMesh);

      // ── Layer 6：中心發散流光與星雲核心 (Radiating Central Plasma & Nebula Streamers) ──
      var plasmaGeom = new THREE.PlaneGeometry(1.4, 1.4);
      var plasmaMat = new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 0.85,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var plasmaMesh = new THREE.Mesh(plasmaGeom, plasmaMat);
      plasmaMesh.position.z = 0.05;
      mainGroup.add(plasmaMesh);

      // ── Layer 7：奇點白熾聚能十字星芒 (Singularity Pinpoint Starburst - Z: 0.08) ──
      var starburstTex = createSingularityPinpointTexture(true);
      var starburstGeom = new THREE.PlaneGeometry(0.75, 0.75);
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

      // ── Layer 8：全景 3D 發散星塵微粒力場 (1050 顆微粒) ──
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

      // ── 加載 4 組實質切割分離的透明紋理 ──
      var assets = window.SMU_PARTY_ORB_ASSETS || {};

      // 1. 純球體
      loadLayerTexture(assets.joinSphere, 'assets/tutorial/orb_join_sphere.webp', function(tex) {
        sphereMat.map = tex;
        sphereMat.needsUpdate = true;
      });

      // 2. 獨立星環 (中心已鏤空)
      loadLayerTexture(assets.joinRings, 'assets/tutorial/orb_join_rings.webp', function(tex) {
        ringMat1.map = tex;
        ringMat1.needsUpdate = true;
      });

      // 3. 核心流光
      loadLayerTexture(assets.joinPlasma, 'assets/tutorial/orb_join_plasma.webp', function(tex) {
        plasmaMat.map = tex;
        plasmaMat.needsUpdate = true;
      });

      // 4. 外層玻璃罩
      loadLayerTexture(assets.joinGlass, 'assets/tutorial/orb_join_glass.webp', function(tex) {
        glassMat.map = tex;
        glassMat.needsUpdate = true;
      });

      // ── Layer 9：動態迴圈與各分層自由獨立運動 ──
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

        // 各分層獨立深度視差
        var px = mouseTargetTiltX;
        var py = -mouseTargetTiltY;
        coronaMesh.position.x = -px * 0.16;
        coronaMesh.position.y = -py * 0.12;
        glassMesh.position.x = px * 0.08;
        glassMesh.position.y = py * 0.06;
        ringMesh1.position.x = px * 0.24;
        ringMesh1.position.y = py * 0.18;
        gyroRingMesh.position.x = -px * 0.15;
        gyroRingMesh.position.y = -py * 0.12;

        // 1. 純球體：自然呼吸微縮放
        var pulse = 1.0 + 0.024 * Math.sin(time * 1.6);
        sphereMesh.scale.set(pulse, pulse, 1.0);

        // 2. 菲涅爾 3D 球膜真實三維自轉
        fresnelMesh.rotation.y += currentSpeed * 0.7;
        fresnelMesh.rotation.x = 0.08 * Math.sin(time * 0.9);

        // 3. 獨立原畫星環：3D 空間大角度公轉
        ringMesh1.rotation.z += currentSpeed * 1.35;

        // 4. 次級科技陀螺環：反向傾角公轉
        gyroRingMesh.rotation.z -= currentSpeed * 0.95;

        // 5. 核心發散流光：獨立逆向旋轉與高頻心跳脈衝
        var corePulse = 1.0 + 0.07 * Math.sin(time * 2.6);
        plasmaMesh.scale.set(corePulse, corePulse, 1.0);
        plasmaMesh.rotation.z -= currentSpeed * 1.6;

        // 6. 奇點十字星芒微自轉
        starburstMesh.rotation.z += currentSpeed * 0.8;

        // 7. 外層玻璃罩：緩慢漂浮呼吸
        var glassPulse = 1.0 + 0.015 * Math.sin(time * 1.2);
        glassMesh.scale.set(glassPulse, glassPulse, 1.0);
        glassMesh.rotation.z += currentSpeed * 0.3;

        // 8. 發散光冕微自轉
        coronaMesh.rotation.z += currentSpeed * 0.4;

        // 9. 星塵空間旋轉
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
          glassGeom.dispose();
          glassMat.dispose();
          ringGeom1.dispose();
          ringMat1.dispose();
          gyroRingGeom.dispose();
          gyroRingMat.dispose();
          sphereGeom.dispose();
          sphereMat.dispose();
          fresnelGeom.dispose();
          fresnelMat.dispose();
          plasmaGeom.dispose();
          plasmaMat.dispose();
          starburstGeom.dispose();
          starburstMat.dispose();
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
     🟣 右星核初始化：霓虹紫紅星核 (PROTOCOL // SQUAD HOST) - 100% 實質分層拆解
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

      // ── Layer 2：最外層透明球體晶罩 (Extracted Outer Glass Shield Shell - Z: -0.04) ──
      var glassGeom = new THREE.PlaneGeometry(3.7, 3.7);
      var glassMat = new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 0.65,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var glassMesh = new THREE.Mesh(glassGeom, glassMat);
      glassMesh.position.z = -0.04;
      mainGroup.add(glassMesh);

      // ── Layer 3：獨立 3D 大傾角星環層 (Extracted 3D Orbit Rings - 中心鏤空，空間穿梭公轉) ──
      var ringGeom1 = new THREE.PlaneGeometry(3.6, 3.6);
      var ringMat1 = new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 0.95,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var ringMesh1 = new THREE.Mesh(ringGeom1, ringMat1);
      ringMesh1.rotation.x = -Math.PI / 3.4;
      ringMesh1.rotation.y = 0.25;
      mainGroup.add(ringMesh1);

      // ── Layer 4：次級反向傾角科技陀螺環 (Counter-Tilted Gyro Tech Ring - Z: 0.0) ──
      var gyroRingTex = createMultiRingTechTexture(false);
      var gyroRingGeom = new THREE.PlaneGeometry(3.9, 3.9);
      var gyroRingMat = new THREE.MeshBasicMaterial({
        map: gyroRingTex,
        transparent: true,
        opacity: 0.68,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var gyroRingMesh = new THREE.Mesh(gyroRingGeom, gyroRingMat);
      gyroRingMesh.rotation.x = Math.PI / 3.6;
      gyroRingMesh.rotation.y = -0.30;
      gyroRingMesh.rotation.z = -0.22;
      mainGroup.add(gyroRingMesh);

      // ── Layer 5：純幾何天體晶球層 (Pure Core Celestial Sphere - 獨立 Y 軸自轉) ──
      // 5-A: 原畫獨立球體視覺面 (NormalBlending 保證細節清晰)
      var sphereGeom = new THREE.PlaneGeometry(2.32, 2.32);
      var sphereMat = new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 1.0,
        blending: THREE.NormalBlending,
        depthWrite: false
      });
      var sphereMesh = new THREE.Mesh(sphereGeom, sphereMat);
      mainGroup.add(sphereMesh);

      // 5-B: 3D 幾何菲涅爾球面晶膜 (SphereGeometry 64x48)
      var fresnelTex = createFresnelSphereTexture(false);
      var fresnelGeom = new THREE.SphereGeometry(1.22, 64, 48);
      var fresnelMat = new THREE.MeshBasicMaterial({
        map: fresnelTex,
        transparent: true,
        opacity: 0.55,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var fresnelMesh = new THREE.Mesh(fresnelGeom, fresnelMat);
      mainGroup.add(fresnelMesh);

      // ── Layer 6：中心發散流光與星雲核心 (Radiating Central Plasma & Nebula Streamers) ──
      var plasmaGeom = new THREE.PlaneGeometry(1.4, 1.4);
      var plasmaMat = new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 0.88,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var plasmaMesh = new THREE.Mesh(plasmaGeom, plasmaMat);
      plasmaMesh.position.z = 0.05;
      mainGroup.add(plasmaMesh);

      // ── Layer 7：奇點白熾聚能十字星芒 (Singularity Pinpoint Starburst - Z: 0.08) ──
      var starburstTex = createSingularityPinpointTexture(false);
      var starburstGeom = new THREE.PlaneGeometry(0.75, 0.75);
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

      // ── Layer 8：全景 3D 發散星塵微粒力場 (1050 顆微粒) ──
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

      // ── 加載 4 組實質切割分離的透明紋理 ──
      var assets = window.SMU_PARTY_ORB_ASSETS || {};

      // 1. 純球體
      loadLayerTexture(assets.hostSphere, 'assets/tutorial/orb_host_sphere.webp', function(tex) {
        sphereMat.map = tex;
        sphereMat.needsUpdate = true;
      });

      // 2. 獨立星環 (中心已鏤空)
      loadLayerTexture(assets.hostRings, 'assets/tutorial/orb_host_rings.webp', function(tex) {
        ringMat1.map = tex;
        ringMat1.needsUpdate = true;
      });

      // 3. 核心流光
      loadLayerTexture(assets.hostPlasma, 'assets/tutorial/orb_host_plasma.webp', function(tex) {
        plasmaMat.map = tex;
        plasmaMat.needsUpdate = true;
      });

      // 4. 外層玻璃罩
      loadLayerTexture(assets.hostGlass, 'assets/tutorial/orb_host_glass.webp', function(tex) {
        glassMat.map = tex;
        glassMat.needsUpdate = true;
      });

      // ── Layer 9：動態迴圈與各分層自由獨立運動 ──
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

        // 各分層獨立深度視差
        var px = mouseTargetTiltX;
        var py = -mouseTargetTiltY;
        coronaMesh.position.x = -px * 0.16;
        coronaMesh.position.y = -py * 0.12;
        glassMesh.position.x = px * 0.08;
        glassMesh.position.y = py * 0.06;
        ringMesh1.position.x = px * 0.24;
        ringMesh1.position.y = py * 0.18;
        gyroRingMesh.position.x = -px * 0.15;
        gyroRingMesh.position.y = -py * 0.12;

        // 1. 純球體：自然呼吸微縮放
        var pulse = 1.0 + 0.024 * Math.sin(time * 1.6);
        sphereMesh.scale.set(pulse, pulse, 1.0);

        // 2. 菲涅爾 3D 球膜真實三維自轉
        fresnelMesh.rotation.y -= currentSpeed * 0.7;
        fresnelMesh.rotation.x = 0.08 * Math.sin(time * 0.9);

        // 3. 獨立原畫星環：3D 空間大角度公轉
        ringMesh1.rotation.z -= currentSpeed * 1.35;

        // 4. 次級科技陀螺環：反向傾角公轉
        gyroRingMesh.rotation.z += currentSpeed * 0.95;

        // 5. 核心發散流光：獨立逆向旋轉與高頻心跳脈衝
        var corePulse = 1.0 + 0.07 * Math.sin(time * 2.6);
        plasmaMesh.scale.set(corePulse, corePulse, 1.0);
        plasmaMesh.rotation.z += currentSpeed * 1.6;

        // 6. 奇點十字星芒微自轉
        starburstMesh.rotation.z -= currentSpeed * 0.8;

        // 7. 外層玻璃罩：緩慢漂浮呼吸
        var glassPulse = 1.0 + 0.015 * Math.sin(time * 1.2);
        glassMesh.scale.set(glassPulse, glassPulse, 1.0);
        glassMesh.rotation.z -= currentSpeed * 0.3;

        // 8. 發散光冕微自轉
        coronaMesh.rotation.z += currentSpeed * 0.4;

        // 9. 星塵空間旋轉
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
          glassGeom.dispose();
          glassMat.dispose();
          ringGeom1.dispose();
          ringMat1.dispose();
          gyroRingGeom.dispose();
          gyroRingMat.dispose();
          sphereGeom.dispose();
          sphereMat.dispose();
          fresnelGeom.dispose();
          fresnelMat.dispose();
          plasmaGeom.dispose();
          plasmaMat.dispose();
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
