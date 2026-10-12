/**
 * 組隊同樂・隊員入隊教學流程管線 (Party Join Tutorial Pipeline)
 * 組裝入隊教學模組並控制執行生命週期
 */

(function(window) {
  'use strict';

  function startPartyJoinTutorial(retryCount) {
    retryCount = retryCount || 0;
    window.__tutorialMockPartyActive = true;

    // 確保頁面切換至組隊大廳
    if (window.switchPage) {
      window.switchPage('party');
    }

    if (!window.TutorialEngine) {
      console.warn('[PartyJoinPipeline] TutorialEngine not found yet, retrying...', retryCount);
      if (retryCount < 20) {
        setTimeout(function() { startPartyJoinTutorial(retryCount + 1); }, 50);
      }
      return;
    }

    var modJoin = window.TutorialEngine.getModule('party_join_guide');

    if (!modJoin) {
      console.warn('[PartyJoinPipeline] Required module party_join_guide not yet loaded, retrying...', retryCount);
      if (retryCount < 20) {
        setTimeout(function() { startPartyJoinTutorial(retryCount + 1); }, 50);
      }
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
