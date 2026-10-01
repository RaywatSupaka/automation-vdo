(() => {
  const NAMESPACE = "smartflow.ai.browser-bridge.flow-evidence.v1";
  const VERSION = "flow-result-observer-1";
  const installedKey = "__smartFlowPassiveResultObserver";
  if (window[installedKey]) return;
  window[installedKey] = true;

  const seen = new Set();
  const mediaPattern = /\.mp4(?:$|[?#])|videoplayback|media\.getMediaUrlRedirect|\/media\/|video/i;
  const allowed = (value) => {
    try {
      const url = new URL(String(value || ""), location.href);
      if (url.protocol !== "https:") return null;
      const hostAllowed = ["googleusercontent.com", "googleapis.com", "gstatic.com", "flow.google.com", "labs.google"]
        .some((host) => url.hostname === host || url.hostname.endsWith(`.${host}`));
      return hostAllowed && mediaPattern.test(`${url.pathname}${url.search}`) ? url.href : null;
    } catch {
      return null;
    }
  };

  const publish = (value, kind) => {
    const url = allowed(value);
    if (!url || seen.has(url)) return;
    seen.add(url);
    if (seen.size > 200) seen.delete(seen.values().next().value);
    window.postMessage({
      __smartFlow: true,
      namespace: NAMESPACE,
      channel: "page",
      requestId: `FLOW-EVIDENCE-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
      type: "FLOW_MEDIA_EVIDENCE",
      payload: { url, kind, at: Date.now(), pageUrl: location.href, observerVersion: VERSION }
    }, location.origin);
  };

  const scanMedia = (root = document) => {
    root.querySelectorAll?.("video,video source").forEach((element) => {
      publish(element.currentSrc || element.src || element.getAttribute?.("src"), "dom-video");
    });
  };

  let performanceObserver = null;
  try {
    performanceObserver = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) publish(entry.name, `resource:${entry.initiatorType || "unknown"}`);
    });
    performanceObserver.observe({ type: "resource", buffered: true });
  } catch {}

  let domObserver = null;
  const startDomObserver = () => {
    scanMedia();
    if (domObserver || !document.documentElement) return;
    domObserver = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === "attributes") scanMedia(record.target?.parentElement || document);
        for (const node of record.addedNodes || []) {
          if (node.nodeType === Node.ELEMENT_NODE) scanMedia(node);
        }
      }
    });
    domObserver.observe(document.documentElement, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["src"]
    });
    document.documentElement.dataset.smartflowFlowObserver = VERSION;
  };

  startDomObserver();
  document.addEventListener("DOMContentLoaded", startDomObserver, { once: true });
  window.addEventListener("pagehide", () => {
    performanceObserver?.disconnect();
    domObserver?.disconnect();
  }, { once: true });
})();
