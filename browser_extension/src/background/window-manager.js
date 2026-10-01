export class WindowManager {
  async focusForUserAction(tab) {
    if (!tab?.id) return false;
    if (Number.isInteger(tab.windowId)) await chrome.windows.update(tab.windowId, { focused: true });
    await chrome.tabs.update(tab.id, { active: true });
    return true;
  }

  async canManage(windowId, allowedHosts = []) {
    const win = await chrome.windows.get(Number(windowId), { populate: true }).catch(() => null);
    if (!win || win.focused) return false;
    const tabs = (win.tabs || []).filter((tab) => /^https?:/i.test(String(tab.url || "")));
    if (!tabs.length) return false;
    return tabs.every((tab) => {
      try {
        const host = new URL(tab.url).hostname;
        return allowedHosts.some((item) => host === item || host.endsWith(`.${item}`));
      } catch {
        return false;
      }
    });
  }
}
