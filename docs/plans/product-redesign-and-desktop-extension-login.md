# Latest requested logic — image redesign and desktop-linked Extension login

Status2026-09-20: implemented and packaged in paired390 source; final1950tests passed320.856s and38-file source/folder/ZIP parity verified, NOT installed. See docs/reports/desktop-linked-extension-390.md.389 was never packaged. Desktop-only Login and substantive new visual/prompt/image contracts are implemented; continuous recovery applies to confirmed technical failures. Content refusals/helper needs_review remain review, not an unlimited attempt to defeat provider safeguards. Popup provides status/recheck and normal desktop-opening instructions because no supported native launch URI exists.

## A. Redesign the failed visual, not just its words

User clarification: each recovery must use AI to design a genuinely new image AND a complete new prompt, not merely reword the rejected composition. Successful neighboring slots stay untouched. Original product photographs and verified facts remain reference data; a different product must not be silently substituted.

Proposed state sequence:

1. Bind the confirmed failed attempt to exact job/run/slot/conversation. A pending/unknown Send or incomplete download is not a failed image.
2. Send original references, last failed visual description/prompt and the actual error to an owned helper using the originally selected provider.
3. Ask for ONE substantively different, genuinely compliant visual composition and its full image-generation prompt. Preserve product facts and saved speech. Do not ask the helper to disguise disallowed content or override a refusal; retain an honest needs_review result when no compliant alternative can be supplied.
4. Generate and save an actual new image with that proposal, validating ownership, dimensions and pixel hash against previous failed/successful candidates. New wording alone is not a new image. Persist the candidate and approval before dispatch; retain its provenance.
5. Continue the original task with the approved new image and prompt. On another confirmed technical failure, return to2 with failure history and cancellable backoff; no arbitrary total service-round cap. Never reset pending requests or force every refusal into automatic retry. Repeated provider refusal does not establish permission to bypass safeguards.
6. Exit on verified success, user cancellation, required login/credit action, unresolved prior submission or a substantive content/factual review. Show actual phase/round and retained completed count; do not display fictitious completion.

The draft389 code already has durable helper claims and original-tab prompt recovery, but does not yet implement this full new-image redesign contract. Its fixed policy-redesign counter is not the approved final UX. Preserve the existing ledger/history when replacing this draft logic; no release ZIP has been created.

## B. Login once in SmartFlow; no separate Extension API Token

Verified current cause: core/membership.py maintains desktop and extension server sessions/renewal credentials independently; popup.html/js exposes Extension Token login; Background pre-Send calls /api/membership/extension/authorize; LocalBridge command leasing checks extension scope. Hiding the field alone would leave those guards denying work.

Requested design:

- SmartFlow desktop alone accepts the admin-issued membership API Token and owns server renewal/heartbeat/expiry, one Token per machine and manual re-login after an admin kick.
- Extension asks the authenticated loopback bridge for desktop-derived authorization. It never receives, stores or submits the membership Token or the desktop cloud renewal credential.
- Keep the separate local bridge session security, origin/client/profile validation, exact paired version and job/run ownership. These machine-to-Extension session credentials are internal transport protection, NOT another Token field for the user.
- Authorize each new command and physical provider Send using fresh desktop-derived permission. Extension version is metadata, not membership identity. Upgrading the same installation must not trigger Token entry in Chrome.
- Desktop logout, kick, lock, expiry or expired offline lease denies new work in Extension. Desktop unavailable means waiting for the program, not 'enter Extension Token'. Preserve accepted work and allow saving results/cancelling; never use authorization failure to resend a job.
- Popup has connection/account status and an action to open SmartFlow when necessary; remove separate Token form and Extension membership logout. Account logout belongs to desktop.
- Audit desktop Extension-status UI and command leasing as well as popup/pre-Send. Do not merely return allowed=true or trust an unauthenticated health response.
- Keep historical Extension credentials/server rows intact during migration; do not export/copy Tokens or silently delete customer credentials. Any retirement of admin Extension-Token issuance or changes to online-session display require matching owner-server work and its deployment workflow, not a hidden restart from this task.

## Implementation and tests next

1. Finish A's substantive new-image contract while retaining389's claim/idempotency/provenance foundations.
2. Introduce a desktop-derived Extension permission contract across membership, bridge, command queue, background pre-Send, popup and desktop status; preserve desktop server authority.
3. Test login→Extension ready, same-profile upgrade, wrong origin/version, stopped desktop, offline lease, logout/kick/expiry, accepted-result saving, Chrome restart and no membership secrets in Chrome storage. Test both providers and image retry/cancel/unknown-send paths separately.
4. Synchronize and package only the completed paired source; installed testing must be separately reported. No server restart, browser reload, live generation or customer Token action is authorized merely by writing this design.

## Existing staged verification (not this revised design)

Draft389 final1937Python tests passed331.984s, including28actual-source JS scenarios and an ephemeral local HTTP package test; preliminary1935passed330.226s before the two integration regressions were added. This proves the staged implementation's tests, not completion of A/B above. Installed discovery CMD-4FD1F15CAE failed because no Flow project was open; no repeat. No389ZIP/install, real generation or server action performed.
