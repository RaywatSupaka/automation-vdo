# AI accepted request with no answer: same-chat reminder proposal

Status: evidence captured and plan recorded; no runtime change, provider Send, reload, restart, installer, or live-job mutation in this audit.

## User instruction

2026-09-26: when the image and prompt are already submitted but the AI does not answer, retain that conversation and request rather than resetting the scene. Recognize the observed webpage structure and add a reminder in the same conversation. The exact reminder payload (short follow-up versus repeat of the full original prompt) still needs clarification before implementation. This is not blanket permission to send repeatedly during active generation or to bypass a refusal/account restriction.

## Current observed state

Read-only inspection around 2026-09-26 14:20–14:22 Asia/Bangkok:

- Desktop and connected Extension report 0.15.445. Story work is active, queue is not paused. This is newer live evidence than the earlier unactivated-445 report; no installed identity/path migration was performed or verified in this audit.
- Exact active job: `STORY-20260926-4A9904`, pending scene 9. The current conversation is `https://chatgpt.com/c/6ab76d29-a09c-83ec-8e1c-34961289eb3c`.
- The latest user turn visibly contains the image request and one loaded reference image. No subsequent assistant heading/image is present in the mounted latest turn; composer is empty and voice-start is available. No Stop button or visible active-generation progress was observed.
- Earlier generated images are present; they are not evidence of a new scene-9 result. Page history also displays an earlier-message-loading label, so a single mounted snapshot alone does not establish complete-history proof.
- Latest bridge trace contains post-refresh checks; a live heartbeat alone does not prove the result monitor is advancing.

These observations establish an accepted-request/no-current-answer UI shape, not a proven provider-side backend error. No private ChatGPT backend, cookies, tokens, request payloads, image URLs, or full prompts were inspected/copied.

## Sanitized DOM shape and confirmed readiness defect

Observed latest user wrapper:

```text
DIV.block-BQZwFn
  H4.sr-only: คุณพูดว่า:
  DIV.group/user-message: original prompt + one IMG (loaded, 941 x 1672)
```

Observed scrolling ancestor:

```json
{
  "tag": "DIV",
  "classes": ["thread-scroll-container", "overflow-y-auto", "flex", "flex-col-reverse"],
  "computedOverflowY": "auto",
  "computedFlexDirection": "column-reverse",
  "scrollHeight": 6912,
  "clientHeight": 889,
  "scrollTop": 0
}
```

`browser_extension/chatgpt.js::storyImagePostRefreshPageReady` (line 3577 at this audit) uses `scrollHeight - clientHeight - scrollTop > 4` for all scrolling ancestors. In this reverse-direction thread the newest end is `scrollTop = 0`, but that expression is 6023, so the function rejects the actual newest end. The reader can keep waiting without ever reaching stable post-refresh redo proof.

A read-only Node VM reproduction loaded the exact current production function, with no provider or live receipt access:

| Scenario | Current result | Expected |
| --- | --- | --- |
| Normal column at latest end, scrollTop 6023 | ready | ready |
| Reverse column at newest end, scrollTop 0 | not ready | ready |
| Reverse column away from newest end, scrollTop -100 | not ready | not ready |

The existing `tests/story_refresh_redo_437.cjs` fixture gives the frame no scrolling parent and computed overflow `visible`; it does not cover this measured reverse scroller.

Scoped readiness fix to implement: use computed flex direction, with `abs(scrollTop) <= 4` for `column-reverse` and the existing remaining-distance check for ordinary columns. Keep history/loading, visible composer, user-scroll grace, active-generation, draft, login/quota and ownership guards. Do not hard-code the generated `block-*` class as a stable selector.

## Proposed non-reset reminder transaction

1. Read and preserve the exact original accepted request, source references, scene checkpoint and conversation. Save a matching real result immediately if it appears; keep waiting while generation is actually active.
2. After a fully ready, latest-end, draft-free page repeatedly proves the exact latest original request has no usable answer/media and no generation activity, persist a separate reminder child intent bound to original job/run/scene/receipt identity/send nonce/conversation.
3. Recheck the same proof immediately before one trusted Send. Do not re-upload the reference, clear the original receipt, reset the scene, switch AI or open another tab for this branch.
4. Give the reminder its own exact text, nonce, accepted message ID and dispatch latch. The result collector must follow the accepted child request, because the existing original-request snapshot stops at a subsequent user turn. Never accept an older scene image as the reminder result.
5. Lost acknowledgement or uncertain Send requires reading that same child request; it does not authorize another reminder. A late original result before Send cancels the pending reminder.
6. After an accepted reminder, observe/save the actual owned result and continue normally. Repeated recovery must be sequential and durable with a cooldown, never parallel requests or one reminder every poll. Each new reminder needs new stable evidence; the permitted repeat policy remains to be finalized.
7. User pause/cancel, changed owner/chat, user draft, active/queued generation, login/quota and genuine refusal remain protected states.

Proposed short follow-up for clarification: “จากรูปและคำขอด้านบน ช่วยสร้างภาพที่ขอให้เลย ขอภาพเดียว ไม่ต้องเสนอทางเลือก”. Do not send this until the payload and implementation are settled.

## Regression checklist before delivery

- Normal and reverse scrolling at/away from latest end; user-scroll grace; incomplete/virtualized history.
- Exact accepted original with loaded source and empty answer versus unknown Send or wrong scene.
- Late image, loading image, Stop/progress, draft, upload, login/quota/refusal vetoes.
- One durable reminder intent across duplicate ticks, worker/page restart and lost ACK.
- Child request ownership and result boundaries; original/reference image never becomes the new result.
- Cancel/pause stops the transaction; successful saved scenes and media hashes stay unchanged.
- Paired desktop/Extension contract and installed verification are distinct from fixture results. No customer installer is part of this proposal.
