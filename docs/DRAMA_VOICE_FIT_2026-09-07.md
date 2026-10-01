# Drama settings and voice-fit timing — desktop revision 1

Scope: desktop only. Extension 0.15.267 source and installation bundle are unchanged.

## Implemented

- Drama creation saves video mode, timing policy, final pause, subtitle enabled flag and presenter selection in series/episode settings.
- Queue-only creation preserves the running queue and does not switch the current provider/model or overwrite running status.
- Drama has shared Story queue start/pause access. Presenter overlay is independent of the series cast.
- MultiFlowComposer defaults to voice-fit: allocates the full narration across all scenes using planned scene-duration weights (source durations if invalid/missing), retains scene order, and adds a bounded final pause. This is not per-scene speech timestamp alignment.
- Short footage can slow modestly and hold its final frame. Narration is not sped up or truncated. Original-length mode remains available for Flow.
- Final render validates duration before replacing output; an existing final is copied to backups/finals first.
- Subtitle toggle skips burning subtitles. Subtitle style and other finishing settings still use current program defaults, not a per-series style snapshot.

## Verification / limitations

Initial full suite: 970 tests passed, 96.318 seconds. Real local FFmpeg tests cover shorter/longer voice, all three scenes and their order, output duration, and audio near the end of narration.

Final full suite after queue status/control refinements: 970 tests passed, 95.458 seconds. All three changed JavaScript files pass syntax checks. Extension source/package comparison: 36 files, zero differences. Test runner exited normally.

Existing ready user jobs were not regenerated or changed. No provider requests or credits used. No executable GUI smoke test performed in this revision; visual interaction and installed EXE acceptance remain to be checked. Test processes exit after completion.

Image-motion already follows narration duration; Flow-only timing/tail controls are disabled in that mode. Do not restore old extension versions or rebuild its bundle for this desktop-only change.

Key files: core/video_composer.py, core/story_finisher.py, core/drama_options.py, core/drama_series.py, core/story_queue.py, ui/main_window.py, web_ui/app.js, web_ui/index.html, web_ui/presenter.js, web_ui/studio.js.
