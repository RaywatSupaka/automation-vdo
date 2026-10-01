# Shopee GPT Web → Meta AI — implementation contract v1

Approved: 2026-09-30, attachment 65cb8f1c-911c-48c1-8a61-a19bb38e21e1 and explicit “ลงมือทำ”.
Only new Shopee Product creation changes. Existing Story Shorts, jobs, results,
receipts, settings and immutable releases are preserved. Google Flow/Gemini are
not new workflow providers. No Setup build.

## Observable completion criteria

One actual new two-scene job: exact selected Shopee product; 1–3 decoded original
references; strict two-scene saved JSON; original references attached again for
scene 2; both generated images saved; each saved image reattached to GPT for its
own Meta prompt; two owned Meta MP4 files and receipts; playable ordered vertical
Final with the chosen audio. Fixtures/builds are not real Final evidence.
Ten-scene live verification follows only after two scenes pass and budget approval.

## Current → target / smallest cumulative change

Canonical main/source is 474. Reviewed cumulative 476 includes GPT/Meta-only scope
and worker-session collector recovery. New work starts in
`build/shopee-gpt-meta-477-20260930/source`, not an old rollback or the clean GPT MVP.

| Current implementation | v1 change |
| --- | --- |
| `web_ui/product_story.js` already imports Product into Story's N-scene engine | Retain that technical engine and explicit Product identity; marker `shopee_gpt_meta_version: 1` only for new Product jobs |
| Legacy `ProductManager` makes three images before video | Do not expand/migrate that legacy engine; use existing N-scene save/owner contracts |
| `core/product_story.py` freezes public facts/photos | Require exact shop/item identity; freeze 1–3 distinct decoded originals and hashes |
| `core/story_manager.py` saves plan and partial images | Exact N validation, ordered scene indices and saved shot seed; no padding or truncation |
| `core/meta_scene_sequence.py` saves a Meta-video barrier | Opt-in Product eligibility; add durable saved-image → GPT prompt phase before `MetaVideoManager.begin` |
| `browser_extension/chatgpt.js` has image/tool/attachment/Send ownership checks | Attach original refs every scene, disallow donor substitution for v1; attach saved scene image for prompt text; wait for stored video before next image |
| `core/meta_video.py` validates downloaded MP4 geometry/duration/identity | Use the stored image-bound prompt; native audio requires an actual audio track |
| `ui/main_window.py`, `ui/creation_queue.py`, `core/creation_queue.py` capture settings | Freeze same marker/N/audio for direct and queued execution; never migrate old queue entries on read |

## UI and audio

New Product form: product URL, integer scene count 1–10, audio API / native clip.
Provider fixed GPT Web + Meta. Generated data is read-only. No editable details,
manual script, per-scene prompts, cast or creative presets. Keep the existing
SmartFlow typography/palette/components; simplify rather than redesign the app.
API-only subtitle/background options use existing configured services/media.
API suppresses Meta speech; native preserves actual Meta speech and ambience and
must never silently substitute TTS. No invented licensing for background files.

User confirmed “เสียงข้อความแบบออโต้” means automatically reading the saved GPT
dialogue using the existing API voice, not automatically selecting a voice/style.
API mode requires that reading option; unchecked is rejected before generation
until the user enables it or selects native audio. No inert checkbox is shipped.
Authorized first live test: https://s.shopee.co.th/9fLINdVDpO, two scenes, API
reading. Credits are authorized for this bounded clip, not an unlimited retry loop.

## Saved schemas

Product source: existing source job plus shop/item IDs, original/resolved URL,
public name/description, actual decoded files and hashes. Imported content is data,
not instructions. Never invent claims, specs, prices or physical-use experience.

Job: existing Story job storage, explicit Product context/source ID, marker 1,
exact `scene_count`, original-reference snapshot, frozen audio/render choices,
`shopee_gpt_meta_plan` with version/seed/count/ordered shot descriptors.

Analysis: existing transport with `job_id`, `scene_indices: [1, …, N]`, exactly N
`scene_prompts`, `scene_narrations`, `flow_shot_prompts`, and valid durations.
New validation requires all IDs and arrays agree. JSON is saved before media work.
Array positions refer to those explicit indices, not download order.

Checkpoint: existing desktop scene-gate store; job/AI run/scene/script-and-option
hash/image hash; durable GPT prompt request and at-most-once Send intent; saved
Meta prompt with image binding; existing Meta command/run/request/context and
download receipt. Never reset receipts to recover a timeout.

## Three prompt roles

1. Planning: public product facts + attached original product photos + N + saved
   seeded shot pattern → one strict JSON. Vary product-appropriate pointing,
   holding, demonstration, POV, details and side/lifestyle shots; retain identity.
   State uncertain facts as warnings, not spoken claims. Keep Thai dialogue short;
   provider timing and actual spoken content require real QA.
2. Scene image: only current saved scene + original product references attached
   anew → one actual scene image, consistent product/presenter identity.
3. Meta preparation: attach the exact downloaded scene image again + current
   action/dialogue/audio mode → one image-grounded Meta `video_prompt`. No earlier
   scene substitution or instruction from untrusted product/GPT output.

## Desktop-owned sequence

Source captured → plan saved → scene i image requested/saved → prompt prepared →
single-use Send intent → dispatched/acceptance observed → prompt saved → Meta
requested/generating → owned playable video stored → scene ready → i+1.
All scenes ready → existing ordered audio/composition/finalization.

Unknown Send is a waiting/reconciliation state, not a failed attempt. An ACK or
text reply is not a video. A restarted worker may collect the same authorized
request; it cannot adopt abandoned/cancelled/deleted work or send another request.

## Recovery and evidence gates

- Bad JSON: current bounded owned completed-response correction, same saved N,
  references and seed; invalid result cannot overwrite approved plan.
- Missing attachment: no Send; original references cannot become prior scene media.
- Image exists but collection fails: collect existing owned result, not regenerate.
- Prompt failure after saved image: retain image; recover only prompt request with
  durable owner and uncertain-Send fences.
- Meta completed text: existing evidence-based fresh context recovery; login,
  quota and policy remain real blockers. Never call no-video text a success.
- Download/save failure: reconcile the same result/download. No regeneration to
  repair persistence; preserve completed scene files and frozen settings.
- No state change means no retry. At most two same-method retries after initial
  failure with new evidence; stop intervention after three failed approaches.

## Milestones and proof

1. New contract + UI + source identity + strict N/seed fixtures (N=1,2,5,10).
2. Image/reference and saved-image prompt transport; ownership/unknown Send,
   worker restart, late result, cancellation and previous-video barriers.
3. Reused local media/audio/order verification; no credits for render-only proof.
4. Changed main source/EXE + matching Extension 477 using existing guarded
   packager; exact source/folder/ZIP/hash parity, no installer.
5. Safe backed-up main handoff and observed Extension/profile/loaded-path pairing.
   No hot overwrite/reload while browser/provider work is active or unknown.
6. Actual new two-scene clip, then budget-approved ten-scene clip.

Record source fixed / fixtures verified / built / integrated / activated / real
Final separately. Store only recipes proven by actual files/receipts in a success
.md; do not label mocked transport or locally composed media as provider success.
