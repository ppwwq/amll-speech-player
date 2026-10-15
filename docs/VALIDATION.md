# Investigation and validation

Validation performed on 2026-10-14 in the isolated `/workspace/amll-speech-player` project.

## Source reviewed

- HKLHaoBin/amll-web, branch amlw, commit 60346fb3e4a6552740fe2c6826689a466877a92c.
- Locked @applemusic-like-lyrics/core 0.2.0-alpha.5, including its distributed source map.
- Upstream manifest, build scripts and service worker were read before running dependencies. Dependency install used --ignore-scripts.

## Confirmed causes

1. The core base player prevents default on touchstart/touchend, while the DOM player only emits line-click from mouse click. A real browser touch tap in Chromium emulation emitted zero line-click events.
2. Forward display applies audioSeconds × 1000 + delayMs. The upstream click handler divides lineStart by 1000 without subtracting delay, synchronizing state or resetting scroll. Other seek controls use transient next-line/50ms timers, creating stale update races.
3. Core setCurrentTime(isSeek=true) selects the previous buffered index before replacing the buffer. The adapter corrects the anchor to the new hot/next line.
4. Core records isScrolled but never consults it during layout. Playback transitions can move the anchor during manual browsing. Core touch move also relayouts the entire list for every input event and retains springs during finger movement.
5. The app multiplies renderScale by DPR; BaseRenderer multiplies by DPR again. At 1024×768 and DPR=2 the upstream canvas measured 4096×3072. The app also constructs two background renderers, automatically raises FPS, and forces offsetHeight after time text updates.
6. The core DOM update loops through every line and writes spring/mask styles even for detached lines. The adapter keeps updates bounded to visible/transitioning lines, skips distant style writes, and batches layout to one animation frame. Initial parse/layout remains O(n).

## Fix design

Retain AMLL DOM rendering with a pinned-version adapter. Pointer events distinguish taps (≤10px, ≤450ms) from drag, long press, cancel and multi-touch. Two qualifying taps must target the same sentence within 320ms and 24px; only the second activates. Single taps do not seek. Touch and mouse share one release handler; compatibility clicks are suppressed. During drag, positions follow input directly and blur is temporarily removed; normal springs and a 4px blur cap remain during following. Manual browsing freezes the anchor; it resumes explicitly, after a sentence seek, or five seconds after inertia settles. Inertia uses time-based friction and cancels when a new gesture begins.

One seek method converts units, clamps finite media, updates the display immediately with isSeek=true, and preserves play/pause. No next-line/50ms seek timer remains. Background applies DPR exactly once, defaults to 30fps, and pauses on hidden pages. Lyric clock synchronization is 30Hz while the visible springs use animation frames. Font weights and layout remain upstream.

Drag-to-seek is enabled by default with a persisted browse/seek switch. A vertical drag shows a centre guide and the nearest main sentence's offset-corrected audio timestamp. Preview uses cached layout geometry; audio is untouched until a valid release commits once through the same seek method. Seek mode has no release inertia. First/last sentence bounds are calculated from line centres so both can reach the guide. Wheel input always browses. Long holds still allow browsing but cannot arm seek selection; this distinction fixes a regression found during the A–B wrap test where the long-hold guard also blocked slow browsing drags.

Cancellation, capture loss, multi-touch (including a second finger outside the transcript), release outside, media/delay changes, mode changes, resize and blur discard selection. A missing, negative, non-finite or out-of-media timestamp is never guessed or clamped into a drag candidate. The five-second follow timer cannot commit a selection. Toolbar and cover controls do not start transcript gestures.

UI checks found hover-only playback controls falling outside the viewport, a centre toast covering the drag guide, and portrait toolbar/album overlap. Playback controls now remain visible with 44px play targets; status messages sit above them, and portrait header/transcript regions are separated. Long English words wrap. The upstream Cloudflare analytics beacon was removed.

## Delivery constraints

GitHub connector identity: ppwwq. `gh auth status` reports that the existing GH_TOKEN is invalid. Available connector operations lack create-repository and Pages/deployment setup. No new credential or broader permission has been requested or created. No push or public deployment can be claimed until an authorized repository/deployment route is available.

The smoke-notes working tree is outside this project and is not modified or committed. No database is used.

The parent thread reported a connected Vercel personal account, but no Vercel tools or CLI/credential are exposed to this delegated execution context. Repeated tool discovery found no callable Vercel operation. The available Sites alternative creates a new source-repository credential, so it was not used under the user's no-new-credentials constraint. The requested verification, deployments-cicd and software-engineering skills were checked; their packages were unavailable in this context, so no claim of having executed those skills is made.

## Measured before/after (Chromium, Linux headless)

Same 1024×768 CSS viewport, DPR 2, synthetic 2000-line transcript. Dynamic background was made static for the lyric CPU benchmark. Each variant sampled 120 calls to `update(16.667)` on animation frames. These are JavaScript function timings, not full-frame FPS or iPad battery/GPU measurements.

| Check | Reviewed upstream | Modified player |
| --- | ---: | ---: |
| Background buffer at scale 1 | 4096×3072 | 2048×1536 |
| Lyric line update calls per frame | 2000 | 6 |
| Update median | 2.2ms | below 0.1ms timer resolution |
| Update p95 | 3.4ms | 0.1ms |
| Transcript displacement during a held manual drag + playback transition | −377.7px | 0px |

The deterministic improvements are the buffer dimensions, bounded update call count, and unchanged manual anchor. Timing varies by machine/run. The comparison test explicitly loads synthetic media so the upstream initial setup panel cannot intercept the touch gesture.

## Automated coverage

- TypeScript strict type check and five Node test groups (time conversion, finite media/range boundaries, tap/drag/long-press discrimination, double-tap pairing, playable drag candidates).
- Browser media element decodes and plays synthetic 60-second WAV; paused and playing double-click/double-tap seek to the intended sentence. Active lyric class and millisecond clock are asserted.
- Single click/tap does not seek; a double pair activates once. Same-line/24px/320ms requirement, drag returning to origin, and a third tap are covered by unit checks.
- Real Chromium touch inputs cover dragging, cancellation, long press and multi-touch without seeking. Double tapping does not change Chromium viewport scale.
- Positive/negative offsets, rapid keyboard seeks, explicit range exit by sentence, range clamp by other seek controls, manual-follow hold and idle/explicit resume, portrait/landscape canvas dimensions and 2000-line rendering are covered.
- The adapter also synchronizes active word masks from the audio clock and pauses them after a paused seek; it starts paused until actual audio play.
- Drag preview does not seek; release seeks once, preserves paused/playing state, applies positive/negative offsets, exits an incompatible A–B range and follows the chosen sentence. No later inertia seek occurs. Mouse and native Chromium touch inputs are exercised.
- Drag cancellation cases, first/last bounds, invalid timestamps, missing audio, long-hold browsing, switch persistence, and actual rendered centre-guide selection are asserted in `tests/drag_seek.py`.
- Real decoded synthetic MP3 plus imported LRC is played and navigated with double-click/tap and drag release at desktop 1280×900, tablet landscape 1024×768, tablet portrait 768×1024 and narrow 390×844 viewports. `tests/ui_checks.py` checks hit targets, clipping, long words, portrait spacing and screenshots.

## Remaining limits and device checklist

No physical iPad or Safari/WebKit execution has been performed. Playwright's WebKit download failed with HTTP 403 “Domain forbidden” from the environment's network policy. No alternate download route was attempted. Chromium's iPad-size touch emulation is not Safari.

On the user's iPad, still verify double-tap timing comfort, no Safari double-tap zoom, touch inertia, interrupted gestures, Bluetooth audio latency, long recordings, browser background/return, and 60/120Hz performance. Audio output in headless tests is not an audible hardware check. Initial lyric creation/layout and time matching remain O(n); 2000 lines were tested, not an unbounded transcript. The adapter relies on the pinned alpha.5 core internals and must be revalidated before upgrading AMLL.

The upstream free-form JavaScript background preset fallback was removed; custom presets now accept JSON only. The build still warns about the intentionally classic copied jsmediatags script and a roughly 604KB JS bundle (about 166KB gzip). Both are served correctly in static-path tests; code splitting is future work.


## Static release checks

The production build was served from `/practice/` on a plain HTTP static server (not Vite fallback routing), and the browser suite was run against that subpath. Source archive, manifest, icons and the classic metadata script returned HTTP 200. Saved render scale, reset, rotation and A–B loop wrap during manual browsing were also tested. Browser page errors: zero.

Test environment: Node 24.19.0, pnpm 11.25.0 supplied by the cloud environment, Chromium 154.0.8037.57 on Debian Linux, Python Playwright. The project pins pnpm 10.13.1 for reproducible install and the Pages workflow uses that version. Pages configuration follows the [official custom workflow documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages); the workflow has not run on GitHub because publication is blocked.


## Final production run

All three final production browser suites passed with zero page errors; raw results are in `docs/results/browser-results.json`, `drag-seek-results.json` and `ui-results.json`. It exercised 2000 parsed SRT sentences with five mounted/animated rows at the sampled position. Per-update p95 was 0.1ms in that run. Initial 2000-line import took about 12.0 seconds in the container, including parsing/creation/layout; this remains a startup cost and is not claimed to be fixed by steady-state culling. Typical shorter transcripts and actual iPad initial load time still need device measurement.

The raw before/after comparison, including verified touch hit target and manual state, is in `docs/results/comparison.json`.

## Seek-order repair validation — 2026-10-15

This section supersedes the historical publication/access limitations above for this follow-up. The existing repository is `ppwwq/amll-speech-player`, with production at https://amll-speech-player.vercel.app/; no new repository or Vercel project is used. Research, exact causes and candidate-library decisions are in [SEEK_REPAIR.md](SEEK_REPAIR.md).

The initial 16 seek-order regression groups fail on published baseline `a2d9d5c` (raw excerpts in `docs/results/seek-order-before.json`). The final expanded suite passes **20/20** groups on the production build, including actual mouse/CDP touch, paused/playing synthetic MP3, ordered/unsorted/repeated LRC times, wrapped lines, both delay signs, start/end boundaries, repeated forward/backward seeks, double activation, drag release and manual anchor preservation. Positions, active classes, mount state and stale spring targets are asserted in addition to audio time.

Final local checks:

- `tsc --noEmit`: passed.
- `node --experimental-strip-types --test tests/*.test.ts`: 8 groups passed.
- `node scripts/package-source.mjs && vite build`: passed. Existing classic metadata-script and >500KB bundle warnings remain; generated JS is `assets/index-B9ivb_wZ.js`.
- Against `http://127.0.0.1:4173/`: `tests/browser.py`, `tests/drag_seek.py`, `tests/ui_checks.py`, and `tests/seek_order.py` all passed, with zero page errors. Four UI sizes were checked; desktop, portrait and narrow screenshots were visually reviewed.
- 2000-line sample: 5 mounted/animated rows, update p95 about 0.1ms, manual anchor delta 0px. These are container JavaScript timings, not device FPS or battery claims.
- Raw current results are in `docs/results/{browser,drag-seek,ui,seek-order}-results.json`. Generated synthetic audio/screenshots stay in ignored `test-results/`.

The existing Vercel project was identified as `prj_ep1uPLZbO9uJrP1wzqWkFujn7V1s`. Project basics are readable; its detailed deployment API returned 403 for the existing account scope, and no Vercel CLI is installed. No credential or permission change was attempted. GitHub Vercel commit status and public asset/browser checks are the available post-push verification route; their final outcome is reported with the delivery commit.

Still unverified: physical iPad, Safari/WebKit, the user's unprovided video/LRC, audio hardware latency and unbounded transcript size. Only synthetic audio/LRC was used. The pinned-core internal API dependency remains documented; this patch does not upgrade packages.
