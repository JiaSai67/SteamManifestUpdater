/**
 * 群眾領導教學流程管線 (Leader Tutorial Pipeline)
 * 將獨立模組 (標籤與補丁解讀、Google Drive 網盤配置、網盤資源入庫與補丁管理) 組裝成完整的群眾領導學習鏈路
 */

(function(window) {
  'use strict';

  function startLeaderTutorial() {
    if (!window.TutorialEngine) {
      console.error('[LeaderPipeline] TutorialEngine not found!');
      return;
    }

    var modTags = window.TutorialEngine.getModule('leader_tags_patch');
    var modGDrive = window.TutorialEngine.getModule('leader_gdrive_config');
    var modDeploy = window.TutorialEngine.getModule('leader_deploy_manage');

    if (!modTags || !modGDrive || !modDeploy) {
      console.error('[LeaderPipeline] Required modules not yet loaded:', {
        tags: !!modTags,
        gdrive: !!modGDrive,
        deploy: !!modDeploy
      });
      return;
    }

    // 將三個模組串聯為群眾領導者的完整旅程
    var combinedSteps = []
      .concat(modTags.steps)
      .concat(modGDrive.steps)
      .concat(modDeploy.steps);

    window.TutorialEngine.start(combinedSteps, {
      onComplete: function() {
        console.log('[LeaderPipeline] Leader tutorial successfully completed!');
        if (typeof window.cleanupAllTutorialSandbox === 'function') {
          window.cleanupAllTutorialSandbox();
        } else {
          if (typeof modTags.cleanup === 'function') modTags.cleanup();
          if (typeof modGDrive.cleanup === 'function') modGDrive.cleanup();
          if (typeof modDeploy.cleanup === 'function') modDeploy.cleanup();
        }
        if (typeof tt === 'function') {
          tt('🚀 線上補丁完整教學已圓滿完成！', 'ok', 4000);
        }
      },
      onCancel: function() {
        console.log('[LeaderPipeline] Leader tutorial aborted by user.');
        if (typeof window.cleanupAllTutorialSandbox === 'function') {
          window.cleanupAllTutorialSandbox();
        } else {
          if (typeof modTags.cleanup === 'function') modTags.cleanup();
          if (typeof modGDrive.cleanup === 'function') modGDrive.cleanup();
          if (typeof modDeploy.cleanup === 'function') modDeploy.cleanup();
        }
        if (window.switchPage) window.switchPage('tutorial');
        if (typeof tt === 'function') {
          tt('已退出教學模式', 'info');
        }
      }
    });
  }

  window.LeaderPipeline = {
    start: startLeaderTutorial
  };
})(window);
