import { ACTIONS, PLATFORM } from "../core/constants.js";
import { Logger } from "../core/logger.js";
import { ScopedStateStore } from "../core/storage.js";
import { ChunkTransferStore } from "../core/media-transfer.js";
import { JobRouter } from "./job-router.js";
import { TabManager } from "./tab-manager.js";
import { WindowManager } from "./window-manager.js";
import { PlatformAdapter } from "../platforms/platform-adapter.js";
import { ShopeeAdapter } from "../platforms/shopee/adapter.js";
import { AIWebAdapter } from "../platforms/ai-web/adapter.js";
import { GoogleFlowAdapter } from "../platforms/google-flow/adapter.js";
import { MetaVideoAdapter } from '../platforms/meta-ai/video.js';

globalThis.SmartFlowMetaVideo = MetaVideoAdapter;

const logger = new Logger({ component: "service-worker" });
const stateStore = new ScopedStateStore();
const router = new JobRouter({ logger });
const adapters = {
  shopee: new ShopeeAdapter(),
  aiWeb: new AIWebAdapter(),
  googleFlow: new GoogleFlowAdapter({ stateStore, logger: logger.child({ platform: PLATFORM.GOOGLE_FLOW }) }),
  metaAI: new PlatformAdapter({id: PLATFORM.META_AI, actions: ACTIONS[PLATFORM.META_AI]}),
  core: new PlatformAdapter({ id: PLATFORM.CORE, actions: ACTIONS[PLATFORM.CORE] })
};
Object.values(adapters).forEach((adapter) => router.registerAdapter(adapter));

globalThis.SmartFlowArchitecture = Object.freeze({
  version: 1,
  logger,
  stateStore,
  router,
  tabManager: new TabManager({ logger }),
  windowManager: new WindowManager(),
  mediaTransfers: new ChunkTransferStore(),
  platforms: Object.freeze(adapters)
});
