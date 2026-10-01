export const FLOW_SELECTORS = Object.freeze({
  promptEditors: [
    '.ProseMirror[contenteditable="true"]',
    '[data-slate-editor="true"][contenteditable="true"]',
    'textarea',
    '[role="textbox"][contenteditable="true"]'
  ],
  media: ["video", "video source", "img"],
  controls: ['button', '[role="button"]', '[role="menuitem"]', '[role="option"]']
});

export const FLOW_TEXT = Object.freeze({
  generate: /(?:^|\s)(?:สร้าง|generate)(?:\s|$)/i,
  approve: /^(?:อนุมัติ|approve)$/i,
  download: /ดาวน์โหลด|download/i,
  retry: /ลองอีกครั้ง|retry/i
});
