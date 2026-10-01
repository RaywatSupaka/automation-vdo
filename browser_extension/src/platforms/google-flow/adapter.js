import { ACTIONS, PLATFORM, isAllowedPlatformUrl } from "../../core/constants.js";
import { ERROR_CODE, SmartFlowBridgeError } from "../../core/errors.js";
import { PlatformAdapter } from "../platform-adapter.js";

const EVIDENCE_TTL_MS = 35 * 60 * 1000;
const MAX_EVIDENCE = 24;

function isAllowedMediaUrl(value) {
  try {
    const url = new URL(String(value || ""));
    if (url.protocol !== "https:") return false;
    const allowedHost = [
      "googleusercontent.com", "googleapis.com", "gstatic.com",
      "flow.google.com", "labs.google"
    ].some((host) => url.hostname === host || url.hostname.endsWith(`.${host}`));
    if (!allowedHost) return false;
    return /\.mp4(?:$|[?#])|videoplayback|media\.getMediaUrlRedirect|\/media\/|video/i.test(`${url.pathname}${url.search}`);
  } catch {
    return false;
  }
}

function safeUrlForLog(value) {
  try {
    const url = new URL(String(value || ""));
    return `${url.origin}${url.pathname}`.slice(0, 600);
  } catch {
    return "";
  }
}

export class GoogleFlowAdapter extends PlatformAdapter {
  constructor({ stateStore, logger, ...options } = {}) {
    super({ id: PLATFORM.GOOGLE_FLOW, actions: ACTIONS[PLATFORM.GOOGLE_FLOW], ...options });
    this.stateStore = stateStore;
    this.logger = logger;
  }

  async status(tab) {
    const detected = Boolean(tab?.id && this.detect(tab));
    const url = String(tab?.url || "");
    const loginPage = /accounts\.google\.com\/(?:signin|v3\/signin)/i.test(url);
    return { connected: Boolean(tab?.id), loggedIn: detected && !loginPage, ready: detected && !loginPage, url, account: {} };
  }

  evidenceKey(jobId, shotIndex) {
    return `${String(jobId || "")}:${Number(shotIndex || 0)}`;
  }

  async captureEvidence(message, sender) {
    const tabId = Number(sender?.tab?.id || 0);
    const tabUrl = String(sender?.tab?.url || message?.evidence?.pageUrl || "");
    if (!tabId || !isAllowedPlatformUrl(PLATFORM.GOOGLE_FLOW, tabUrl)) {
      throw new SmartFlowBridgeError(ERROR_CODE.SECURITY_REJECTED, "Flow evidence came from an untrusted tab");
    }
    const evidence = message?.evidence;
    const mediaUrl = String(evidence?.url || "");
    const observedAt = Number(evidence?.at || 0);
    if (!isAllowedMediaUrl(mediaUrl) || !Number.isFinite(observedAt)
        || Math.abs(Date.now() - observedAt) > EVIDENCE_TTL_MS) {
      throw new SmartFlowBridgeError(ERROR_CODE.INVALID_MESSAGE, "Flow media evidence is invalid or stale");
    }

    const local = await chrome.storage.local.get([
      "smartpostActiveJobId", "smartpostActiveShotIndex", "smartpostFlowActiveProject",
      "smartpostFlowMonitor"
    ]);
    const activeProject = local.smartpostFlowActiveProject || {};
    const monitor = local.smartpostFlowMonitor || {};
    const jobId = String(activeProject.jobId || monitor.jobId || local.smartpostActiveJobId || "");
    const shotIndex = Number(activeProject.shotIndex || monitor.shotIndex || local.smartpostActiveShotIndex || 0);
    const ownerTabId = Number(activeProject.tabId || 0);
    const baseline = Math.max(
      Number(activeProject.requestedAt || 0),
      Number(monitor.startedAt || 0)
    );
    if (!jobId || shotIndex <= 0 || (ownerTabId && ownerTabId !== tabId)) {
      return { accepted: false, reason: "not_owner" };
    }
    if (baseline && observedAt + 5000 < baseline) {
      return { accepted: false, reason: "before_baseline" };
    }

    const key = this.evidenceKey(jobId, shotIndex);
    const current = await this.stateStore.getSession("flow-evidence", key) || [];
    const clean = current
      .filter((item) => Date.now() - Number(item.at || 0) < EVIDENCE_TTL_MS)
      .filter((item) => item.url !== mediaUrl);
    clean.push({
      url: mediaUrl,
      safeUrl: safeUrlForLog(mediaUrl),
      kind: String(evidence.kind || "resource").slice(0, 40),
      at: observedAt,
      tabId,
      pageUrl: tabUrl.slice(0, 1000),
      observerVersion: String(evidence.observerVersion || "").slice(0, 80)
    });
    await this.stateStore.setSession("flow-evidence", key, clean.slice(-MAX_EVIDENCE), EVIDENCE_TTL_MS);
    this.logger?.debug("flow_media_evidence", {
      platform: this.id, jobId, shotIndex, tabId,
      mediaUrl: safeUrlForLog(mediaUrl), kind: evidence.kind
    });
    return { accepted: true, jobId, shotIndex, safeUrl: safeUrlForLog(mediaUrl) };
  }

  async latestVideoEvidence(jobId, shotIndex, tabId = 0) {
    const values = await this.stateStore.getSession("flow-evidence", this.evidenceKey(jobId, shotIndex)) || [];
    return [...values].reverse().find((item) =>
      Date.now() - Number(item.at || 0) < EVIDENCE_TTL_MS
      && (!tabId || Number(item.tabId || 0) === Number(tabId))
      && isAllowedMediaUrl(item.url)
    ) || null;
  }

  async cleanup(jobId, shotIndex) {
    await this.stateStore.removeSession("flow-evidence", this.evidenceKey(jobId, shotIndex));
    return { ok: true };
  }
}

export { isAllowedMediaUrl, safeUrlForLog };
