import { ERROR_CODE, SmartFlowBridgeError } from "../core/errors.js";

export class TabManager {
  constructor({ logger = null } = {}) {
    this.logger = logger;
  }

  async find(predicate) {
    const tabs = await chrome.tabs.query({});
    return tabs.find((tab) => predicate(tab)) || null;
  }

  async findByHosts(hosts) {
    const allowed = new Set(hosts || []);
    return this.find((tab) => {
      try {
        const host = new URL(String(tab.url || "")).hostname;
        return [...allowed].some((item) => host === item || host.endsWith(`.${item}`));
      } catch {
        return false;
      }
    });
  }

  async waitUntilLoaded(tabId, timeoutMs = 45000) {
    const startedAt = Date.now();
    while (Date.now() - startedAt < timeoutMs) {
      const tab = await chrome.tabs.get(Number(tabId)).catch(() => null);
      if (!tab) throw new SmartFlowBridgeError(ERROR_CODE.TAB_NOT_FOUND, "Target tab no longer exists");
      if (tab.status === "complete") return tab;
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    throw new SmartFlowBridgeError(ERROR_CODE.TIMEOUT, "Target tab did not finish loading");
  }

  async focus(tabId) {
    const tab = await chrome.tabs.get(Number(tabId)).catch(() => null);
    if (!tab) throw new SmartFlowBridgeError(ERROR_CODE.TAB_NOT_FOUND, "Target tab not found");
    if (Number.isInteger(tab.windowId)) await chrome.windows.update(tab.windowId, { focused: true });
    return chrome.tabs.update(tab.id, { active: true });
  }

  async close(tabId) {
    if (!Number.isInteger(Number(tabId))) return false;
    await chrome.tabs.remove(Number(tabId)).catch(() => {});
    return true;
  }
}
