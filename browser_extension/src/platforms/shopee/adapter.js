import { ACTIONS, PLATFORM } from "../../core/constants.js";
import { PlatformAdapter } from "../platform-adapter.js";

export class ShopeeAdapter extends PlatformAdapter {
  constructor(options = {}) {
    super({ id: PLATFORM.SHOPEE, actions: ACTIONS[PLATFORM.SHOPEE], ...options });
  }
}
