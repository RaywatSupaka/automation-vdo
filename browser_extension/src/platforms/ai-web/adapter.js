import { ACTIONS, PLATFORM } from "../../core/constants.js";
import { PlatformAdapter } from "../platform-adapter.js";

export class AIWebAdapter extends PlatformAdapter {
  constructor(options = {}) {
    super({ id: PLATFORM.AI_WEB, actions: ACTIONS[PLATFORM.AI_WEB], ...options });
  }

  async status(tab) {
    const base = await super.status(tab);
    const url = String(tab?.url || "");
    const loginPage = /\/auth\/login|accounts\.google\.com\/(?:signin|v3\/signin)/i.test(url);
    return { ...base, loggedIn: base.ready && !loginPage, ready: base.ready && !loginPage };
  }
}
