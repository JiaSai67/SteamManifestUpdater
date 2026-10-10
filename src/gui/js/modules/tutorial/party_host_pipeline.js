/**
 * 組隊招募・房主開房教學流程管線 (Party Host Tutorial Pipeline)
 * 組裝開房教學模組並控制執行生命週期
 */

(function(window) {
  'use strict';

  function startPartyHostTutorial() {
    if (!window.TutorialEngine) {
      console.error('[PartyHostPipeline] TutorialEngine not found!');
      return;
    }

    var modHost = window.TutorialEngine.getModule('party_host_guide');

    if (!modHost) {
      console.error('[PartyHostPipeline] Required module party_host_guide not yet loaded.');
      return;
    }

    window.TutorialEngine.start(modHost.steps, {
      onComplete: function() {
        console.log('[PartyHostPipeline] Party Host tutorial completed successfully!');
        if (typeof modHost.cleanup === 'function') modHost.cleanup();
        if (typeof tt === 'function') {
          tt('🏆 開房教學已圓滿完成！您已掌握領隊招募與補丁管理的所有核心技能', 'ok', 4000);
        }
      },
      onCancel: function() {
        console.log('[PartyHostPipeline] Party Host tutorial aborted by user.');
        if (typeof modHost.cleanup === 'function') modHost.cleanup();
        if (window.switchPage) window.switchPage('tutorial');
        if (typeof tt === 'function') {
          tt('已退出開房教學', 'info');
        }
      }
    });
  }

  window.PartyHostPipeline = {
    start: startPartyHostTutorial
  };
})(window);
