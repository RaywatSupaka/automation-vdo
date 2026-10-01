import { ERROR_CODE, SmartFlowBridgeError } from "../core/errors.js";
import { isAllowedPlatformUrl } from "../core/constants.js";

export class PlatformAdapter {
  constructor({ id, actions = [], timeoutMs = 180000 } = {}) {
    this.id = String(id || "");
    this.actions = Object.freeze([...actions]);
    this.timeoutMs = timeoutMs;
  }

  detect(tab) {
    return isAllowedPlatformUrl(this.id, tab?.url);
  }

  async status(tab) {
    return {
      connected: Boolean(tab?.id),
      loggedIn: Boolean(tab?.id),
      ready: Boolean(tab?.id && this.detect(tab)),
      url: String(tab?.url || ""),
      account: {}
    };
  }

  async prepare(_action, _payload, _context = {}) {
    return { ready: true };
  }

  async execute(action, payload, context = {}) {
    if (!this.actions.includes(action)) {
      throw new SmartFlowBridgeError(ERROR_CODE.UNSUPPORTED_ACTION, `${this.id} does not support ${action}`);
    }
    if (typeof context.delegate === "function") return context.delegate(payload);
    throw new SmartFlowBridgeError(ERROR_CODE.UNSUPPORTED_ACTION, `${action} is not connected to a runtime delegate`);
  }

  async cleanup() {
    return { ok: true };
  }
}
