/**
 * Steam Manifest Updater - 組隊教學 3D 全息星核選擇層 (Three.js WebGL 旗艦版)
 * 1:1 完美還原圖二原畫視覺：
 * 1. 拒絕線稿：天青星雲晶核 (Aurora Nebula Core) + 紫晶螺旋星冕漩渦 (Galaxy Vortex Core)。
 * 2. 扁平科技軌道光環帶 (Orbital Ring Discs) 與懸浮微光星塵，悠緩大氣深空自轉。
 * 3. 視野拉闊防裁切：相機 z = 7.5 + 420px 畫布，360 度旋轉絕不被邊界切割。
 * 4. 點擊進入教學立即徹底銷毀與取消覆蓋，杜絕打斷後續教學步驟。
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

  /**
   * 建立高斯羽化星塵紋理
   */
  function createStardustTexture() {
    var canvas = document.createElement('canvas');
    canvas.width = 64;
    canvas.height = 64;
    var ctx = canvas.getContext('2d');
    var grad = ctx.createRadialGradient(32, 32, 0, 32, 32, 30);
    grad.addColorStop(0, 'rgba(255, 255, 255, 1)');
    grad.addColorStop(0.2, 'rgba(255, 255, 255, 0.85)');
    grad.addColorStop(0.5, 'rgba(255, 255, 255, 0.25)');
    grad.addColorStop(0.85, 'rgba(255, 255, 255, 0.05)');
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
   * 建立天青星雲流動紋理 (圖二左核心：翻滾星雲雲霧)
   */
  function createNebulaTexture() {
    var canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 256;
    var ctx = canvas.getContext('2d');

    // 底色全透明
    ctx.clearRect(0, 0, 256, 256);

    // 中心白熾高光
    var gCore = ctx.createRadialGradient(128, 128, 0, 128, 128, 110);
    gCore.addColorStop(0, 'rgba(255, 255, 255, 1)');
    gCore.addColorStop(0.25, 'rgba(128, 244, 255, 0.85)');
    gCore.addColorStop(0.55, 'rgba(0, 210, 255, 0.45)');
    gCore.addColorStop(0.85, 'rgba(2, 132, 199, 0.15)');
    gCore.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = gCore;
    ctx.fillRect(0, 0, 256, 256);

    // 疊加星雲流動煙霧光斑
    var clouds = [
      { x: 90, y: 110, r: 65, c: 'rgba(0, 245, 255, 0.55)' },
      { x: 165, y: 135, r: 70, c: 'rgba(56, 189, 248, 0.5)' },
      { x: 120, y: 160, r: 60, c: 'rgba(147, 197, 253, 0.45)' },
      { x: 145, y: 95, r: 55, c: 'rgba(255, 255, 255, 0.65)' }
    ];
    clouds.forEach(function(cl) {
      var g = ctx.createRadialGradient(cl.x, cl.y, 0, cl.x, cl.y, cl.r);
      g.addColorStop(0, cl.c);
      g.addColorStop(0.7, cl.c.replace(/[\d\.]+\)$/, '0.1)'));
      g.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(cl.x, cl.y, cl.r, 0, Math.PI * 2);
      ctx.fill();
    });

    var tex = new THREE.CanvasTexture(canvas);
    tex.generateMipmaps = false;
    tex.minFilter = THREE.LinearFilter;
    tex.magFilter = THREE.LinearFilter;
    tex.needsUpdate = true;
    return tex;
  }

  /**
   * 建立紫紅螺旋星冕漩渦紋理 (圖二右核心：宇宙螺旋黑洞/星雲盤)
   */
  function createSpiralVortexTexture() {
    var canvas = document.createElement('canvas');
    canvas.width = 320;
    canvas.height = 320;
    var ctx = canvas.getContext('2d');
    var cx = 160;
    var cy = 160;

    ctx.clearRect(0, 0, 320, 320);

    // 繪製多層螺旋手臂
    var numArms = 3;
    var numPoints = 600;
    for (var i = 0; i < numPoints; i++) {
      var arm = i % numArms;
      var offset = (arm * Math.PI * 2) / numArms;
      var progress = i / numPoints;
      var dist = Math.pow(progress, 0.7) * 140 + 8;
      var angle = progress * 7.5 + offset;

      var spread = (Math.sin(i * 12.3) * 14) * progress;
      var px = cx + Math.cos(angle) * dist + Math.sin(angle) * spread;
      var py = cy + Math.sin(angle) * dist - Math.cos(angle) * spread;

      var pGrad = ctx.createRadialGradient(px, py, 0, px, py, 14 + progress * 16);
      if (progress < 0.25) {
        pGrad.addColorStop(0, 'rgba(255, 255, 255, 0.85)');
        pGrad.addColorStop(0.5, 'rgba(255, 110, 180, 0.45)');
      } else if (progress < 0.65) {
        pGrad.addColorStop(0, 'rgba(255, 42, 133, 0.65)');
        pGrad.addColorStop(0.6, 'rgba(192, 132, 252, 0.3)');
      } else {
        pGrad.addColorStop(0, 'rgba(147, 51, 234, 0.45)');
        pGrad.addColorStop(0.7, 'rgba(76, 29, 149, 0.15)');
      }
      pGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');

      ctx.fillStyle = pGrad;
      ctx.beginPath();
      ctx.arc(px, py, 14 + progress * 16, 0, Math.PI * 2);
      ctx.fill();
    }

    // 中心白熾爆發奇點
    var gCenter = ctx.createRadialGradient(cx, cy, 0, cx, cy, 55);
    gCenter.addColorStop(0, 'rgba(255, 255, 255, 1)');
    gCenter.addColorStop(0.25, 'rgba(255, 200, 230, 0.9)');
    gCenter.addColorStop(0.55, 'rgba(255, 42, 133, 0.6)');
    gCenter.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = gCenter;
    ctx.beginPath();
    ctx.arc(cx, cy, 55, 0, Math.PI * 2);
    ctx.fill();

    var tex = new THREE.CanvasTexture(canvas);
    tex.generateMipmaps = false;
    tex.minFilter = THREE.LinearFilter;
    tex.magFilter = THREE.LinearFilter;
    tex.needsUpdate = true;
    return tex;
  }

  /**
   * 建立科技扁平光環帶紋理 (帶有全息間隔刻度槽與光芒漸層)
   */
  function createOrbitalRingTexture(colorHexStr) {
    var canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 32;
    var ctx = canvas.getContext('2d');

    var grad = ctx.createLinearGradient(0, 0, 256, 0);
    grad.addColorStop(0, 'rgba(255, 255, 255, 0.95)');
    grad.addColorStop(0.2, colorHexStr);
    grad.addColorStop(0.5, 'rgba(255, 255, 255, 0.85)');
    grad.addColorStop(0.8, colorHexStr);
    grad.addColorStop(1, 'rgba(255, 255, 255, 0.95)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 256, 32);

    // 刻劃微細科技 HUD 間隙
    ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
    for (var i = 18; i < 250; i += 38) {
      ctx.fillRect(i, 0, 5, 32);
    }

    var tex = new THREE.CanvasTexture(canvas);
    tex.wrapS = THREE.RepeatWrapping;
    tex.wrapT = THREE.ClampToEdgeWrapping;
    tex.repeat.set(2, 1);
    tex.needsUpdate = true;
    return tex;
  }

  /**
   * 建立扁平科技光環帶 (Flat Orbital Ring Disc)
   */
  function createFlatRingBand(innerR, outerR, colorHex, opacity, tex) {
    var geom = new THREE.RingGeometry(innerR, outerR, 64);
    var mat = new THREE.MeshBasicMaterial({
      color: colorHex,
      map: tex || null,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: opacity || 0.75,
      blending: THREE.AdditiveBlending,
      depthWrite: false
    });
    return new THREE.Mesh(geom, mat);
  }

  /**
   * 🔵 初始化左核心：天青極光全息晶核 (圖二左原畫 1:1)
   */
  function initJoinThreeCore(canvas) {
    if (!window.THREE) return null;

    try {
      var width = canvas.clientWidth || 420;
      var height = canvas.clientHeight || 420;

      var scene = new THREE.Scene();
      // 🌟 相機拉遠至 z = 7.5，視野完全容納光環與粒子，絕無任何邊緣切割
      var camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 100);
      camera.position.z = 7.5;

      var renderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: true });
      renderer.setSize(width, height);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setClearColor(0x000000, 0);

      var mainGroup = new THREE.Group();
      scene.add(mainGroup);

      var stardustTex = createStardustTexture();
      var nebulaTex = createNebulaTexture();
      var ringCyanTex = createOrbitalRingTexture('rgba(0, 245, 255, 0.85)');

      // 1. 內核：翻滾發光星雲球 (雙層逆向旋轉流體星雲)
      var coreInnerGeom = new THREE.SphereGeometry(0.88, 32, 32);
      var coreInnerMat = new THREE.MeshBasicMaterial({
        map: nebulaTex,
        transparent: true,
        opacity: 0.95,
        blending: THREE.AdditiveBlending
      });
      var coreInnerMesh = new THREE.Mesh(coreInnerGeom, coreInnerMat);
      mainGroup.add(coreInnerMesh);

      var coreOuterGeom = new THREE.SphereGeometry(1.05, 32, 32);
      var coreOuterMat = new THREE.MeshBasicMaterial({
        map: nebulaTex,
        transparent: true,
        opacity: 0.55,
        blending: THREE.AdditiveBlending
      });
      var coreOuterMesh = new THREE.Mesh(coreOuterGeom, coreOuterMat);
      mainGroup.add(coreOuterMesh);

      // 2. 外圍水晶全息能量晶球罩 (高透無網格光膜球體)
      var shellGeom = new THREE.SphereGeometry(1.42, 36, 36);
      var shellMat = new THREE.MeshBasicMaterial({
        color: 0x67E8F9,
        transparent: true,
        opacity: 0.12,
        blending: THREE.AdditiveBlending,
        wireframe: false
      });
      var shellMesh = new THREE.Mesh(shellGeom, shellMat);
      mainGroup.add(shellMesh);

      // 3. 圍繞球體的精細科技光環帶 (Flat Orbital Rings，像圖二原畫般的行星扁平光圈)
      var ringGroup = new THREE.Group();

      var ring1 = createFlatRingBand(1.52, 1.68, 0x00F5FF, 0.8, ringCyanTex);
      ring1.rotation.x = Math.PI / 3;
      ring1.rotation.y = 0.2;
      ringGroup.add(ring1);

      var ring2 = createFlatRingBand(1.82, 1.94, 0x38BDF8, 0.65, ringCyanTex);
      ring2.rotation.x = -Math.PI / 3.2;
      ring2.rotation.z = 0.35;
      ringGroup.add(ring2);

      var ring3 = createFlatRingBand(2.05, 2.12, 0x0284C7, 0.5, null);
      ring3.rotation.y = Math.PI / 3.5;
      ring3.rotation.x = 0.15;
      ringGroup.add(ring3);

      mainGroup.add(ringGroup);

      // 4. 外圍散落的極光星塵星粒 (800 顆精細微光顆粒)
      var pGeom = new THREE.BufferGeometry();
      var pPos = [];
      var pColors = [];
      var cWhite = new THREE.Color(0xFFFFFF);
      var cCyan = new THREE.Color(0x00F5FF);
      var cBlue = new THREE.Color(0x38BDF8);

      for (var i = 0; i < 750; i++) {
        var r = 0.4 + Math.random() * 1.85;
        var theta = Math.random() * Math.PI * 2;
        var phi = Math.acos(2 * Math.random() - 1);
        pPos.push(r * Math.sin(phi) * Math.cos(theta), r * Math.sin(phi) * Math.sin(theta), r * Math.cos(phi));
        var col = (r < 0.9) ? cWhite.clone().lerp(cCyan, r / 0.9) : cCyan.clone().lerp(cBlue, (r - 0.9) / 1.35);
        pColors.push(col.r, col.g, col.b);
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

      // 🌟 悠緩優雅的自轉速度 (深空星體美學)
      var currentSpeed = 0.0025;
      var targetSpeed = 0.0025;
      var scaleFactor = 1.0;
      var targetScale = 1.0;
      var animId = null;
      var clock = new THREE.Clock();

      function renderLoop() {
        animId = requestAnimationFrame(renderLoop);
        var time = clock.getElapsedTime();

        currentSpeed = THREE.MathUtils.lerp(currentSpeed, targetSpeed, 0.05);
        scaleFactor = THREE.MathUtils.lerp(scaleFactor, targetScale, 0.05);
        mainGroup.scale.set(scaleFactor, scaleFactor, scaleFactor);

        // 核心雙層逆轉星雲流動
        coreInnerMesh.rotation.y += currentSpeed * 1.3;
        coreInnerMesh.rotation.x += currentSpeed * 0.4;
        coreOuterMesh.rotation.y -= currentSpeed * 0.9;

        // 水晶球罩與星塵微動
        shellMesh.rotation.y += currentSpeed * 0.3;
        particles.rotation.y += currentSpeed * 0.7;

        // 呼吸脈動放慢
        var pulse = 1.0 + 0.045 * Math.sin(time * 1.6);
        coreInnerMesh.scale.set(pulse, pulse, pulse);

        // 軌道光環悠緩旋轉
        ring1.rotation.z += currentSpeed * 1.5;
        ring2.rotation.z -= currentSpeed * 1.2;
        ring3.rotation.x += currentSpeed * 1.4;

        renderer.render(scene, camera);
      }

      renderLoop();

      return {
        setHover: function(isHovered) {
          targetSpeed = isHovered ? 0.0065 : 0.0025;
          targetScale = isHovered ? 1.05 : 1.0;
        },
        destroy: function() {
          if (animId) cancelAnimationFrame(animId);
          coreInnerGeom.dispose();
          coreInnerMat.dispose();
          coreOuterGeom.dispose();
          coreOuterMat.dispose();
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

  /**
   * 🟣 初始化右核心：星冕深空螺旋漩渦星雲 (圖二右原畫 1:1)
   */
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

      var stardustTex = createStardustTexture();
      var vortexTex = createSpiralVortexTexture();
      var ringMagentaTex = createOrbitalRingTexture('rgba(255, 42, 133, 0.85)');

      // 1. 核心螺旋星系盤 (雙層對盤，螺旋星系深度立體感)
      var vortexGeom = new THREE.PlaneGeometry(2.35, 2.35);
      var vortexMat1 = new THREE.MeshBasicMaterial({
        map: vortexTex,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.95,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var vortexMesh1 = new THREE.Mesh(vortexGeom, vortexMat1);
      vortexMesh1.rotation.x = Math.PI / 4.2;
      vortexMesh1.rotation.y = 0.25;
      mainGroup.add(vortexMesh1);

      var vortexMat2 = new THREE.MeshBasicMaterial({
        map: vortexTex,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.65,
        blending: THREE.AdditiveBlending,
        depthWrite: false
      });
      var vortexMesh2 = new THREE.Mesh(vortexGeom, vortexMat2);
      vortexMesh2.rotation.x = -Math.PI / 3.8;
      vortexMesh2.rotation.z = 0.3;
      mainGroup.add(vortexMesh2);

      // 2. 中心發光奇點球體 (純白熾熱光核)
      var singGeom = new THREE.SphereGeometry(0.32, 24, 24);
      var singMat = new THREE.MeshBasicMaterial({
        color: 0xFFD6E7,
        transparent: true,
        opacity: 0.95,
        blending: THREE.AdditiveBlending
      });
      var singularityMesh = new THREE.Mesh(singGeom, singMat);
      mainGroup.add(singularityMesh);

      // 3. 多重扁平科技軌道光環帶 (Concentric Flat Orbital Rings)
      var ringGroup = new THREE.Group();

      var ring1 = createFlatRingBand(1.48, 1.62, 0xFF2A85, 0.85, ringMagentaTex);
      ring1.rotation.x = Math.PI / 3.2;
      ring1.rotation.z = -0.25;
      ringGroup.add(ring1);

      var ring2 = createFlatRingBand(1.78, 1.9, 0xC084FC, 0.7, ringMagentaTex);
      ring2.rotation.x = -Math.PI / 2.9;
      ring2.rotation.y = 0.4;
      ringGroup.add(ring2);

      var ring3 = createFlatRingBand(2.06, 2.14, 0x9333EA, 0.55, null);
      ring3.rotation.y = -Math.PI / 3.2;
      ring3.rotation.x = 0.28;
      ringGroup.add(ring3);

      mainGroup.add(ringGroup);

      // 4. 外圍螺旋飛散星塵 (850 顆紫晶星粒)
      var pGeom = new THREE.BufferGeometry();
      var pPos = [];
      var pColors = [];
      var cWhite = new THREE.Color(0xFFFFFF);
      var cPink = new THREE.Color(0xFF2A85);
      var cPurple = new THREE.Color(0x9333EA);

      for (var i = 0; i < 800; i++) {
        var arm = i % 3;
        var r = Math.pow(Math.random(), 0.75) * 1.9 + 0.2;
        var angle = r * 3.8 + (arm * Math.PI * 2) / 3;
        var spread = (Math.random() - 0.5) * 0.35 * r;
        var x = Math.cos(angle) * r + spread;
        var y = Math.sin(angle) * r + spread;
        var z = (Math.random() - 0.5) * 0.5 * (2.0 - r * 0.6);

        pPos.push(x, y, z);
        var col = (r < 0.6) ? cWhite.clone().lerp(cPink, r / 0.6) : cPink.clone().lerp(cPurple, (r - 0.6) / 1.3);
        pColors.push(col.r, col.g, col.b);
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

      // 🌟 悠緩深空旋轉速度
      var currentSpeed = 0.0028;
      var targetSpeed = 0.0028;
      var scaleFactor = 1.0;
      var targetScale = 1.0;
      var animId = null;
      var clock = new THREE.Clock();

      function renderLoop() {
        animId = requestAnimationFrame(renderLoop);
        var time = clock.getElapsedTime();

        currentSpeed = THREE.MathUtils.lerp(currentSpeed, targetSpeed, 0.05);
        scaleFactor = THREE.MathUtils.lerp(scaleFactor, targetScale, 0.05);
        mainGroup.scale.set(scaleFactor, scaleFactor, scaleFactor);

        // 漩渦螺旋盤順時針旋轉
        vortexMesh1.rotation.z += currentSpeed * 1.6;
        vortexMesh2.rotation.z -= currentSpeed * 1.1;

        particles.rotation.z += currentSpeed * 1.4;

        var pulse = 1.0 + 0.05 * Math.sin(time * 1.8);
        singularityMesh.scale.set(pulse, pulse, pulse);

        // 軌道光環悠緩旋轉
        ring1.rotation.z -= currentSpeed * 1.5;
        ring2.rotation.z += currentSpeed * 1.3;
        ring3.rotation.x -= currentSpeed * 1.4;

        renderer.render(scene, camera);
      }

      renderLoop();

      return {
        setHover: function(isHovered) {
          targetSpeed = isHovered ? 0.0068 : 0.0028;
          targetScale = isHovered ? 1.05 : 1.0;
        },
        destroy: function() {
          if (animId) cancelAnimationFrame(animId);
          vortexGeom.dispose();
          vortexMat1.dispose();
          vortexMat2.dispose();
          singGeom.dispose();
          singMat.dispose();
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

  /**
   * 構建全息選擇層 DOM
   */
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
   * 🌟 啟動教學管道並徹底銷毀選擇層 (核心問題 5 修復：絕不殘留點擊干擾後續教學)
   */
  function launchPartyPipeline(role) {
    playResonanceSound('launch');

    // 1. 立即切斷所有點擊響應，防重複點擊
    if (overlayEl) {
      overlayEl.style.pointerEvents = 'none';
      overlayEl.classList.remove('active');
      overlayEl.classList.add('fading-out');
    }

    // 2. 清除 localStorage 中的 party 臨時選定態，避免後續重複觸發
    try {
      localStorage.removeItem('smu_tutorial_role');
    } catch(e) {}

    // 3. 立即清理釋放 Three.js 資源並徹底關閉 DOM
    setTimeout(function() {
      hideOverlay();

      // 4. 正式啟動對應教學管線
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
