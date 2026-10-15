# Seek ordering repair — 2026-10-15

Baseline: `a2d9d5cee4a9b167858b19ec60c4844c6bcf929e` in the existing
[ppwwq/amll-speech-player](https://github.com/ppwwq/amll-speech-player) repository.
Work took place in `/workspace/amll-seek-fix`; the borrowed smoke-notes files were not edited.

## Research before changing the implementation

| Candidate/source | Evidence and decision |
| --- | --- |
| [HKLHaoBin/amll-web](https://github.com/HKLHaoBin/amll-web/tree/60346fb3e4a6552740fe2c6826689a466877a92c) | Its `amlw` head is still the same commit reviewed for the baseline. GitHub issue search returned no issues for this fork. The broad SPL detector and input-order end-time calculation are inherited app code. |
| [AMLL issue #416](https://github.com/amll-dev/applemusic-like-lyrics/issues/416), [c6383b8](https://github.com/amll-dev/applemusic-like-lyrics/commit/c6383b8) | Upstream fixed choosing the old buffered anchor before refreshing the buffer and resetting active animation state on seek. The existing adapter already corrects the anchor; this repair retains that fix instead of repeating it. |
| [Current AMLL source](https://github.com/amll-dev/applemusic-like-lyrics/tree/86200dead453bb067e554e989110cbadca8d4756/packages/core/src/lyric-player) | The timeline, row groups and motion architecture have changed substantially from pinned core `0.2.0-alpha.5`. Not a safe drop-in fix for this adapter. The installed distribution's source map was inspected for the exact runtime behavior. |
| [Existing AMLL lyric parser](https://github.com/amll-dev/applemusic-like-lyrics/tree/86200dead453bb067e554e989110cbadca8d4756/packages/lyric) | Browser inspection of the installed `0.2.4` parser confirms it already expands repeated leading timestamps and sorts rows, but its plain-LRC words have endTime=0. Reuse it and infer intervals after parsing, instead of writing another parser. Latest upstream also sorts before resolving implicit end times. |
| [weirongxu/lrc-kit](https://github.com/weirongxu/lrc-kit/tree/dd4c7cf7efdca642ad2424060ec3b47dbbdb468f) | Runner sorts and finds the last timestamp at/before the clock. It does not manage AMLL transforms or multiple simultaneous active rows. A replacement would introduce a second timing authority without addressing the rendering defect. No new dependency added. |

## Confirmed separate failures

1. **Rendering state survives forced positioning.** Pinned core's `Spring.setPosition()` resets position/velocity but leaves its delayed `queuePosition`. The adapter used that forced path while parking and remounting rows. A delayed target can therefore overwrite a newer location. Stopping offscreen updates also freezes that queue until re-entry. A deterministic test queues `top + 200`, forces `top`, then advances time; the baseline moves back to the obsolete destination.
2. **Visible and remounted rows follow different seek trajectories.** The old adapter animated currently visible rows toward the destination while placing parked rows there immediately. Rapid direction changes mix both layouts. On synthetic ordered subtitles, `42→3→48→6→54→0→30→3 seconds` left row index 3 at Y=614.7 instead of 491.7 after 1.2 seconds. The clock, hot index and target order were already correct. ResizeObserver can also correct newly mounted wrapped-row heights after the initial seek layout; those corrections need the same reset behavior.
3. **Plain LRC is misclassified as SPL.** `isSPLFormat` matched every normal leading LRC timestamp, so ordinary `.lrc` uploads never reached the existing `parseLrc`. Local `parseSPL` inferred end times from input order before sorting and discarded a repeated leading timestamp. A synthetic import produced 9000→3000ms, two 3000→3000ms rows, and a 0→6000ms row that incorrectly remained active at 3 seconds. This is a data interval error, not DOM ordering.
4. **Hot index and newly created DOM rows can diverge on import.** Core's base import updates old row objects, then the DOM implementation creates replacements. A retained hot index can leave the replacement without its active class. The adapter now rebuilds active membership after creating rows and resets active animation state on explicit seeks, including same-row seeks.

## Scoped change

- Plain LRC reaches the pinned AMLL parser. Stable timestamp order is retained; simultaneous rows share an interval ending at the next *different* start. The existing five-second final tail remains. Explicit word-timed formats keep their own timing paths.
- A seek batches one snapped layout using the final clock. It hides obsolete distant rows and resets entering/visible rows together. Resize/measurement corrections also snap. The existing spring API clears delayed position targets before forcing position, without modifying node_modules or replacing the renderer.
- Normal playback still animates and updates only visible/transitioning rows. Manual browsing keeps its frozen anchor. Single tap, same-line double tap, drag centre preview/release, cancellation and follow behavior retain their existing event paths.

## Verification

The user story is local synthetic MP3/LRC import → mouse/touch/keyboard seek → media clock and delay conversion → active rows → rendered coordinates. This static client flow has no application API/database boundary.

- Baseline: the initial 16 browser regression groups failed across desktop 1280×900, tablet landscape 1024×768, portrait 768×1024, and narrow 390×844. No page exceptions. See [baseline evidence](results/seek-order-before.json).
- Regression assertions check actual bounding boxes, model positions, queued targets, mounted state, active classes and hot/anchor indices, not only audio time. They cover repeated forward/backward seeks, paused and playing MP3, long wrapped rows, unordered/repeated timestamps, repeated leading timestamps, first/last/no-active regions, ±delay, real double click/tap and drag release, and manual hold through a clock transition.
- `tests/lrc-timing.test.ts` covers inference order, stable duplicates, finite final intervals, input immutability, empty input and plain-LRC/SPL discrimination. `tests/timing.test.ts` retains conversion, bounds and gesture cases.
- `tests/browser.py`, `tests/drag_seek.py`, `tests/ui_checks.py` remain in the full command alongside `tests/seek_order.py`.

Final build/test and deployment evidence is recorded in `docs/VALIDATION.md` and `docs/results/seek-order-results.json`.

## Limits

No user video or private LRC was supplied. The independent synthetic reproductions above do not establish that every device-specific manifestation is resolved. No private audio is included or published. This run uses Linux Chromium and touch/viewport emulation, not physical iPad or Safari/WebKit. Manual iPad confirmation remains necessary. Initial parsing/layout and clock matching are still O(n); this patch preserves bounded per-frame animation work. The adapter still depends on pinned core internals and must be revalidated before a library upgrade.

The available `vercel:verification` and `vercel:deployments-cicd` skills were read. No software-engineering skill was exposed in the skill catalog or executor skill listing, so execution of that skill is not claimed.
