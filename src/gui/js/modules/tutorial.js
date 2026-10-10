/**
 * Steam Manifest Updater - 教學模式模組 (Tutorial Module)
 * 負責角色身分選擇 (獨狼玩家 / 群眾領導) 與後續教學指引流程派發
 */

(function(){
  var currentSelectedRole = null;

  /**
   * 點選卡片選擇角色定位
   * @param {'solo'|'leader'} role 
   */
  function selectTutorialRole(role){
    currentSelectedRole = role;
    var cards = document.querySelectorAll('.tutorial-card');
    cards.forEach(function(c){ c.classList.remove('selected'); });

    var targetCard = document.querySelector('.tutorial-card.card-' + role);
    if(targetCard){
      targetCard.classList.add('selected');
    }
  }

  /**
   * 獨狼玩家電影級過場轉場動畫 (Cinema Warp Transition)
   * 包含：卡片按壓爆發、極光穿梭光幕淡入、無縫切換分頁、溶鏡淡出至步驟一
   */
  function playSoloLaunchTransition(callback){
    var soloCard = document.querySelector('.tutorial-card.card-solo');
    var cardsGrid = document.querySelector('.tutorial-cards-grid');
    var headerWrap = document.querySelector('.tutorial-header-wrap');

    // 1. 卡片下壓衝擊與極光爆發
    if(soloCard) soloCard.classList.add('card-launching');
    if(cardsGrid) cardsGrid.classList.add('is-launching');
    if(headerWrap) headerWrap.classList.add('is-launching');

    // 2. 構建或複用轉場光幕 DOM
    var curtain = document.getElementById('tutorial-transition-curtain');
    if(!curtain){
      curtain = document.createElement('div');
      curtain.id = 'tutorial-transition-curtain';
      curtain.className = 'tutorial-transition-curtain';
      curtain.innerHTML = `
        <div class="curtain-center-box">
          <div class="curtain-wolf-halo">🐺</div>
          <div class="curtain-title">正在進入【獨狼玩家】教學旅程</div>
          <div class="curtain-desc">
            <span class="curtain-spinner-ring"></span>
            <span>正在為您導航至 單元 1：憑證登入引導…</span>
          </div>
        </div>
      `;
      document.body.appendChild(curtain);
    }

    curtain.classList.remove('fading-out');
    requestAnimationFrame(function(){
      curtain.classList.add('active');
    });

    // 3. 在光幕完全展開時 (320ms) 切換分頁並啟動步驟一
    setTimeout(function(){
      // 復原卡片狀態
      if(soloCard) soloCard.classList.remove('card-launching');
      if(cardsGrid) cardsGrid.classList.remove('is-launching');
      if(headerWrap) headerWrap.classList.remove('is-launching');

      if(typeof callback === 'function'){
        callback();
      }

      // 4. 等待步驟一 DOM 與聚光燈定位就緒 (400ms)，光幕平滑溶鏡淡出
      setTimeout(function(){
        curtain.classList.add('fading-out');
        setTimeout(function(){
          curtain.classList.remove('active', 'fading-out');
        }, 340);
      }, 400);
    }, 320);
  }

  /**
   * 線上補丁電影級電光過場轉場動畫 (Rocket Warp Transition)
   */
  function playLeaderLaunchTransition(callback){
    var leaderCard = document.querySelector('.tutorial-card.card-leader');
    var cardsGrid = document.querySelector('.tutorial-cards-grid');
    var headerWrap = document.querySelector('.tutorial-header-wrap');

    if(leaderCard) leaderCard.classList.add('card-launching');
    if(cardsGrid) cardsGrid.classList.add('is-launching');
    if(headerWrap) headerWrap.classList.add('is-launching');

    var curtain = document.getElementById('tutorial-transition-curtain');
    if(!curtain){
      curtain = document.createElement('div');
      curtain.id = 'tutorial-transition-curtain';
      curtain.className = 'tutorial-transition-curtain';
      document.body.appendChild(curtain);
    }

    curtain.innerHTML = `
      <div class="curtain-center-box">
        <div class="curtain-wolf-halo" style="text-shadow:0 0 32px rgba(0,188,212,0.6)">🚀</div>
        <div class="curtain-title">正在進入【線上補丁】教學旅程</div>
        <div class="curtain-desc">
          <span class="curtain-spinner-ring" style="border-top-color:#00BCD4"></span>
          <span>正在為您導航至 單元 1：小卡標籤與線上補丁說明…</span>
        </div>
      </div>
    `;

    curtain.classList.remove('fading-out');
    requestAnimationFrame(function(){
      curtain.classList.add('active');
    });

    setTimeout(function(){
      if(leaderCard) leaderCard.classList.remove('card-launching');
      if(cardsGrid) cardsGrid.classList.remove('is-launching');
      if(headerWrap) headerWrap.classList.remove('is-launching');

      if(typeof callback === 'function'){
        callback();
      }

      setTimeout(function(){
        curtain.classList.add('fading-out');
        setTimeout(function(){
          curtain.classList.remove('active', 'fading-out');
        }, 340);
      }, 400);
    }, 320);
  }

  /**
   * 點擊「開始教學」按鈕
   * @param {'solo'|'leader'} role 
   */
  function startTutorial(role){
    selectTutorialRole(role);
    try {
      if(role !== 'party'){
        localStorage.setItem('smu_tutorial_role', role);
      } else {
        localStorage.removeItem('smu_tutorial_role');
      }
    } catch(e){}

    var roleName = (role === 'solo') ? '獨狼玩家' : '線上補丁';
    var roleDesc = (role === 'solo') ? '單人遊戲入庫與遊玩體驗' : '經常領頭當隊長必看此教學';

    console.log('[Tutorial] Started tutorial for role:', role, { roleName: roleName, roleDesc: roleDesc });

    if(role === 'solo'){
      // 🌟 以電影級極光過場動畫平滑過渡跳轉至步驟一
      playSoloLaunchTransition(function(){
        if(window.SoloPipeline && typeof window.SoloPipeline.start === 'function'){
          window.SoloPipeline.start();
        } else {
          console.warn('[Tutorial] SoloPipeline not available yet.');
        }
      });
    } else if(role === 'leader'){
      // 🌟 以皇室金光過場動畫平滑過渡跳轉至步驟一
      playLeaderLaunchTransition(function(){
        if(window.LeaderPipeline && typeof window.LeaderPipeline.start === 'function'){
          window.LeaderPipeline.start();
        } else {
          console.warn('[Tutorial] LeaderPipeline not available yet.');
        }
      });
    } else if(role === 'party'){
      // 🌟 多人聯機教學：彈出專屬「房長」與「房員」雙角色選擇浮現層
      if(typeof window.openPartyOrbSelection === 'function'){
        window.openPartyOrbSelection();
      } else if(window.PartyOrbOverlay && typeof window.PartyOrbOverlay.show === 'function'){
        window.PartyOrbOverlay.show();
      } else {
        console.warn('[Tutorial] PartyOrbOverlay is not available.');
      }
    }

    if(window.TutorialModule && typeof window.TutorialModule.onRoleSelected === 'function'){
      window.TutorialModule.onRoleSelected(role);
    }
  }

  function initTutorial(){
    try {
      var savedRole = localStorage.getItem('smu_tutorial_role');
      if(savedRole){
        selectTutorialRole(savedRole);
      }
    } catch(e){}
  }

  // 暴露全域接口供 HTML 元素或外部調用
  window.selectTutorialRole = selectTutorialRole;
  window.startTutorial = startTutorial;

  window.TutorialModule = {
    init: initTutorial,
    getSelectedRole: function(){
      return currentSelectedRole || (function(){
        try { return localStorage.getItem('smu_tutorial_role') || 'solo'; } catch(e){ return 'solo'; }
      })();
    },
    selectRole: selectTutorialRole,
    start: startTutorial,
    onRoleSelected: null // 供後續擴充教學步驟回調
  };

  // 頁面初次載入時自動初始化
  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', initTutorial);
  } else {
    initTutorial();
  }
})();
