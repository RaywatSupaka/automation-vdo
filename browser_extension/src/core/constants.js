export const EXTENSION_NAMESPACE = "smartflow.ai.browser-bridge";
export const FLOW_EVIDENCE_NAMESPACE = `${EXTENSION_NAMESPACE}.flow-evidence.v1`;
export const BRIDGE_ORIGIN = "http://127.0.0.1:8765";

export const PLATFORM = Object.freeze({
  SHOPEE: "shopee",
  AI_WEB: "ai-web",
  GOOGLE_FLOW: "google-flow",
  META_AI: "meta-ai",
  CORE: "core"
});

export const PLATFORM_HOSTS = Object.freeze({
  [PLATFORM.SHOPEE]: ["affiliate.shopee.co.th", "shopee.co.th"],
  [PLATFORM.AI_WEB]: ["chatgpt.com", "gemini.google.com", "auth.openai.com", "accounts.google.com"],
  [PLATFORM.GOOGLE_FLOW]: ["flow.google.com", "labs.google"],
  [PLATFORM.META_AI]: ["www.meta.ai"]
});

export const ACTIONS = Object.freeze({
  [PLATFORM.SHOPEE]: ["capture_shopee_product"],
  [PLATFORM.AI_WEB]: [
    "open_chatgpt", "open_story_chatgpt", "cancel_story_chatgpt",
    "resume_chatgpt", "restart_chatgpt_images", "recover_stalled_story_image", "inspect_chatgpt", "focus_ai_web", "clear_story_bootstrap_draft"
  ],
  [PLATFORM.GOOGLE_FLOW]: [
    "read_flow_settings",
    "focus_flow_web", "debug_flow_dom", "open_flow", "inspect_flow",
    "resume_flow_workspace", "approve_flow_credit", "stop_flow_generation",
    "open_flow_result", "download_flow_result", "inspect_flow_result_dom"
  ],
  [PLATFORM.META_AI]: ['open_meta_video'],
  [PLATFORM.CORE]: ["close_automation_browser", "focus_browser"]
});

export const ALL_ACTIONS = Object.freeze(Object.values(ACTIONS).flat());

export function platformForAction(action) {
  return Object.entries(ACTIONS).find(([, actions]) => actions.includes(action))?.[0] || "";
}

export function isAllowedPlatformUrl(platform, value) {
  try {
    const url = new URL(String(value || ""));
    if (url.protocol !== "https:") return false;
    return (PLATFORM_HOSTS[platform] || []).some((host) =>
      url.hostname === host || url.hostname.endsWith(`.${host}`)
    );
  } catch {
    return false;
  }
}
