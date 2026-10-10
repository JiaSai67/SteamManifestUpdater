/**
 * 獨狼玩家教學流程管線 (Solo Tutorial Pipeline)
 * 將獨立的模組 (憑證登入、遊戲入庫、管理入庫) 組裝成單一流暢的獨狼學習鏈路
 */

(function(window) {
  'use strict';

  function startSoloTutorial() {
    if (!window.TutorialEngine) {
      console.error('[SoloPipeline] TutorialEngine not found!');
      return;
    }

    var modCreds = window.TutorialEngine.getModule('credentials_login');
    var modLib = window.TutorialEngine.getModule('game_library_add');
    var modManage = window.TutorialEngine.getModule('manage_library_usage');

    if (!modCreds || !modLib || !modManage) {
      console.error('[SoloPipeline] Required modules not yet loaded:', {
        creds: !!modCreds,
        lib: !!modLib,
        manage: !!modManage
      });
      return;
    }

    // 將三個模組的步驟串聯合成獨狼玩家的完整旅程
    var combinedSteps = []
      .concat(modCreds.steps)
      .concat(modLib.steps)
      .concat(modManage.steps);

    window.TutorialEngine.start(combinedSteps, {
      onComplete: function() {
        console.log('[SoloPipeline] Solo tutorial successfully completed!');
        if (typeof window.cleanupAllTutorialSandbox === 'function') {
          window.cleanupAllTutorialSandbox();
        } else {
          if (typeof modCreds.cleanup === 'function') modCreds.cleanup();
          if (typeof modLib.cleanup === 'function') modLib.cleanup();
          if (typeof modManage.cleanup === 'function') modManage.cleanup();
        }
        if (typeof tt === 'function') {
          tt('🏆 獨狼玩家快速引導已全部完成！', 'ok', 4000);
        }
      },
      onCancel: function() {
        console.log('[SoloPipeline] Solo tutorial aborted by user.');
        // 清理所有可能存在的示範沙盒
        if (typeof window.cleanupAllTutorialSandbox === 'function') {
          window.cleanupAllTutorialSandbox();
        } else {
          if (typeof modCreds.cleanup === 'function') modCreds.cleanup();
          if (typeof modLib.cleanup === 'function') modLib.cleanup();
          if (typeof modManage.cleanup === 'function') modManage.cleanup();
        }
        if (window.switchPage) window.switchPage('tutorial');
        if (typeof tt === 'function') {
          tt('已退出教學模式', 'info');
        }
      }
    });
  }

  window.SoloPipeline = {
    start: startSoloTutorial
  };
})(window);
