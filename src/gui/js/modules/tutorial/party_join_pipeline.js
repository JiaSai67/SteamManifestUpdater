/**
 * 組隊同樂・隊員入隊教學流程管線 (Party Join Tutorial Pipeline)
 * 組裝入隊教學模組並控制執行生命週期
 */

(function(window) {
  'use strict';

  function startPartyJoinTutorial() {
    if (!window.TutorialEngine) {
      console.error('[PartyJoinPipeline] TutorialEngine not found!');
      return;
    }

    var modJoin = window.TutorialEngine.getModule('party_join_guide');

    if (!modJoin) {
      console.error('[PartyJoinPipeline] Required module party_join_guide not yet loaded.');
      return;
    }

    window.TutorialEngine.start(modJoin.steps, {
      onComplete: function() {
        console.log('[PartyJoinPipeline] Party Join tutorial completed successfully!');
        if (typeof modJoin.cleanup === 'function') modJoin.cleanup();
        if (typeof tt === 'function') {
          tt('🏆 入隊教學已圓滿完成！您已具備加入連線同樂的所有必備知識', 'ok', 4000);
        }
      },
      onCancel: function() {
        console.log('[PartyJoinPipeline] Party Join tutorial aborted by user.');
        if (typeof modJoin.cleanup === 'function') modJoin.cleanup();
        if (window.switchPage) window.switchPage('tutorial');
        if (typeof tt === 'function') {
          tt('已退出入隊教學', 'info');
        }
      }
    });
  }

  window.PartyJoinPipeline = {
    start: startPartyJoinTutorial
  };
})(window);
