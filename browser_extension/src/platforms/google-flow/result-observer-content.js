(() => {
  const NAMESPACE = "smartflow.ai.browser-bridge.flow-evidence.v1";
  const allowedHosts = ["googleusercontent.com", "googleapis.com", "gstatic.com", "flow.google.com", "labs.google"];
  const seen = new Set();

  const validUrl = (value) => {
    try {
      if (typeof value !== "string" || value.length < 8 || value.length > 4096) return false;
      const url = new URL(value);
      return url.protocol === "https:" && allowedHosts.some((host) =>
        url.hostname === host || url.hostname.endsWith(`.${host}`)
      );
    } catch {
      return false;
    }
  };

  const listener = (event) => {
    const message = event?.data;
    if (event.source !== window || !message || typeof message !== "object") return;
    if (message.__smartFlow !== true || message.namespace !== NAMESPACE
        || message.channel !== "page" || message.type !== "FLOW_MEDIA_EVIDENCE") return;
    if (typeof message.requestId !== "string" || message.requestId.length > 160) return;
    const payload = message.payload;
    if (!payload || typeof payload !== "object" || !validUrl(payload.url)) return;
    const key = `${payload.url}|${payload.kind || ""}`;
    if (seen.has(key)) return;
    seen.add(key);
    if (seen.size > 200) seen.delete(seen.values().next().value);
    chrome.runtime.sendMessage({
      type: "SMARTFLOW_FLOW_EVIDENCE",
      evidence: {
        url: payload.url,
        kind: String(payload.kind || "resource").slice(0, 40),
        at: Number(payload.at || Date.now()),
        pageUrl: String(payload.pageUrl || location.href).slice(0, 1000),
        observerVersion: String(payload.observerVersion || "").slice(0, 80)
      }
    }).catch(() => {});
  };

  window.addEventListener("message", listener);
  window.addEventListener("pagehide", () => window.removeEventListener("message", listener), { once: true });
})();
