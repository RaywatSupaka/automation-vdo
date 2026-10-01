/* Display-only, opt-in function switches. Original inputs/controllers own values.
   No requests, storage, click handlers, synthetic change events or job actions. */
(() => {
  'use strict';
  if (window.smartflowFunctionControls) return;
  const selector = [
    '#ps-film-cta', '#ps-use-cast', '#presenter-review',
    '.storytelling-panel [data-telling="cta_enabled"]',
    '#product-subtitle', '#subtitle-auto', '#subtitle-background-enabled',
    '#audio-background-enabled', '#audio-sfx-enabled', '#drama-subtitle',
    '#setting-subtitle', '#queue-dry', '#queue-confirm',
    '#intro-story-default', '#intro-drama-default',
    '.presenter-quick-choice input[type="checkbox"]',
    '.media-audio-controls [data-audio-subtitle]',
    '.media-audio-controls [data-audio-music]',
    '.media-audio-controls [data-audio-sfx]',
    '.media-audio-controls [data-audio-keep]',
    '.media-audio-controls [data-actor-dialogue]',
    '.ai-cover-options [data-cover-enable]',
    '.intro-options [data-intro-enable]',
    '.green-options [data-green-enable]', '#green-targets [data-green-target]',
    '#shopee-posting .sp-switch > input[type="checkbox"]',
  ].join(',');

  function decorate(input) {
    if (input.type !== 'checkbox' || input.classList.contains('sf-function-input')) return;
    const label = input.parentElement;
    // Do not reparent anything: existing controllers may retain these exact nodes.
    if (!label || label.tagName !== 'LABEL' || label.querySelectorAll('input').length !== 1) return;
    input.classList.add('sf-function-input');
    input.setAttribute('role', 'switch');
    label.classList.add('sf-function-row');
    const status = document.createElement('span');
    status.className = 'sf-function-state';
    status.setAttribute('aria-hidden', 'true');
    label.append(status);
  }

  function enhance(root) {
    if (!root || !root.querySelectorAll) return;
    if (root.matches?.(selector)) decorate(root);
    root.querySelectorAll(selector).forEach(decorate);
  }

  function start() {
    enhance(document);
    // Only newly mounted forms/rows. No polling, attributes or state mirroring.
    const observer = new MutationObserver(records => {
      for (const record of records) {
        for (const node of record.addedNodes) {
          if (node.nodeType === Node.ELEMENT_NODE) enhance(node);
        }
      }
    });
    observer.observe(document.body, {childList:true, subtree:true});
  }
  window.smartflowFunctionControls = Object.freeze({enhance});
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once:true});
  else start();
})();
