# Flow motion prompts — runtime 0.15.279 candidate

## Contract

- The image job's persisted provider owns both motion planning and Flow text repair. No implicit ChatGPT/Gemini switch.
- New Flow-bound AI jobs save each generated image first, then request a short motion prompt with that exact file attached. Image-only jobs skip this phase.
- Story analysis optionally supplies `flow_shot_prompts` drafts. These are not treated as image-verified prompts.
- Desktop `POST /api/extension/flow-motion-plan` requires current Extension client/version plus current AI run, and checks job/provider/image ownership.
- `prompts/flow_motion_plans.json` stores requested/ready records keyed by job, scene, provider, actual image SHA256, ratio, audio mode and fictional confirmation. Claim precedes Send. Identical ready records are reused. Changed images cannot consume old prompts.
- The saved motion prompt is consumed by Story/Product Flow packages; `motion_prompt_ready` prevents adding the old verbose English guard a second time. Native-audio dialogue is appended from the saved job at handoff.
- The context key intentionally does not hash narration/title: the final analysis commit normalizes these after planning. A later manual narrative change requires review of the motion prompt; this revision does not automatically rewrite ready motion plans for narration-only edits.
- Only an explicit user checkbox confirms that all people are fictional AI characters. That choice is frozen per job/queue/series. Unconfirmed uploaded people are never automatically described as nonexistent.
- Flow policy repair receives the real canonical image and uses the original image provider. Existing current-card ownership, two durable rounds, no blind Retry and no image-motion substitution remain.
- Ambiguous Send, malformed JSON, incompatible reference or material content change pauses for review with the request/media retained. No promise that a provider will accept any prompt; no filter evasion.

## Compatibility / delivery

Historical jobs without a motion ledger retain their original Flow package; old clips, receipts and archives are not reset. Version 279 is separate from 278. No installer or server deployment. Installed provider smoke remains required before calling this a proven release.

## Tests

Offline model tests and actual-JavaScript fixtures exercise provider routing, strict image attachment, idempotent requests, image-change invalidation, fictional consent and no automatic image regeneration on plan review. Full-suite and packaging results are recorded in the release validation report after verification.
