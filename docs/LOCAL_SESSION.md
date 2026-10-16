# Last local files and playback position

Baseline: `679a45a3e67f23281abe180990dc33c311dd3ef3` from `ppwwq/amll-speech-player` main. Work stays in the separate `/workspace/amll-speech-player-ipad-fix` checkout; smoke-notes is untouched. No new hosting, credentials, dependency or paid service is involved.

## Behavior and privacy

After a successful local import, the app saves the audio Blob, caption text, filenames, MIME types and last-modified values. Refreshing or reopening reconstructs Files, validates/decodes them through the existing import flow, restores the caption offset and clamped playback position, and remains paused. It does not call audio.play during restoration. Playback resumes only on user input.

The **本機** menu displays pending, completed, cleared or failed storage states. Save/Retry explicitly retries the current files. Clear removes the saved files and position without unloading current playback; time updates cannot immediately re-create the deleted record. A new file selection or explicit Save starts saving again. Player Reset also clears persistence.

Custom local background/cover images now have a separate `media['background']` record in the same database. Media replacement/progress writes do not rewrite that image, and image-only clear does not remove the audio/caption pair. The menu's Clear All and Reset coordinate clearing both. See [image storage and failure behavior](LOCAL_BACKGROUND.md).

Audio and captions remain in browser storage on the current origin. The persistence module contains no fetch, upload or analytics code. Tests use only synthetic media and check that no non-read network requests occur. A fresh browser profile, another browser, a different website domain, or another device has separate storage.

Explicit remote audio URLs and direct/URL caption inputs detach progress tracking from the saved local-file pair. They retain their upstream behavior and do not silently pair remote content with previously saved local files.

## Data consistency

- IndexedDB database `amll-local-session-v1` has `media` and `progress` object stores. A file/pair replacement writes both in one readwrite transaction. Only transaction `complete` is success; request `success` followed by transaction abort is failure. Quota and other failures preserve the previous complete saved pair.
- Progress writes update only a small record, after verifying the saved pair ID in the same transaction. No audio Blob is rewritten on timeupdate. Updates are throttled to two seconds; pause/seek/pagehide/visibility-hidden flush sooner.
- A small synchronous localStorage checkpoint covers reload/pagehide, when an asynchronous IndexedDB write may not finish. It is used only when its pair ID matches the saved media and it is at least as recent as the IndexedDB progress. Missing, invalid or unavailable checkpoints fall back to IndexedDB. A crash or OS termination can still lose recent unsaved progress; no unload-completion guarantee is made.
- Writes are serialized and use generation IDs. Obsolete queued saves are skipped, while an already-started write must finish before a newer save or clear. Stale completions cannot report success over a newer operation. Explicit Clear is never skipped, and progress cannot resurrect deleted media, including from a tab using a different pair ID.
- Audio replacement resets position and clears the previous caption association. The first audio may pair with captions selected first. Reselecting the same file (matching name, size and last-modified metadata) or the same retained File preserves captions. Caption reads begun for another audio generation are discarded. Captions selected during a pending audio import wait for that import to succeed.
- Startup restore has its own generation guard: manual selection, clear and reset take precedence over a late read or decode. Invalid record shapes, unsupported schema versions, broken audio and unparseable captions produce a recoverable error and allow clearing/reimporting. Invalid or mismatched progress falls back to zero; restored positions are clamped to decoded duration.
- IndexedDB requests are issued synchronously inside transactions or IDB callbacks, with no await across an active transaction. Open/transaction timeouts and blocked/version-change handling prevent an indefinitely pending UI. A failed save does not retry on every timeupdate; the next import or explicit Retry starts another attempt.

## Safari policy

[WebKit's official storage policy](https://webkit.org/blog/14403/updates-to-storage-policy/) describes per-origin quotas, quota failures, storage-pressure/idle eviction and best-effort persistence. A quota estimate would not guarantee that a write fits, so the actual transaction outcome controls the UI. This feature uses ordinary origin storage and does not promise permanent retention. The menu advises keeping original files. No browser permission, persistent-storage grant or new credential is required by this implementation.

## Validation

- `tests/local-session.test.ts` exercises shape validation, transaction-completion semantics, quota failure, stale saves, clear/save ordering, progress throttling, checkpoint identity and deleted-pair/clear failures through a controlled backend.
- `tests/local_session.py` uses actual Chromium IndexedDB. It verifies full Blob equality by SHA-256, caption/offset/position restoration, zero autoplay calls on refresh and browser restart, explicit user playback, audio replacement/pairing, failure atomicity, retry, transaction abort after request success, clear during a held write, cancellation of late restore/caption reads, damaged records and storage unavailability. A persistent Chromium user-data directory is closed and reopened to test beyond page memory. Quota and unavailable-storage errors are deliberately injected; this is not actual disk exhaustion.
- The storage menu is checked at desktop, tablet landscape/portrait and phone landscape/portrait dimensions. Buttons have at least 44px height and are tested for bounds and hit targeting. Screenshots are generated in ignored `test-results/`.
- The existing import, browser, drag, UI, seek-order and tap-playback suites cover the prior unrestricted picker, same-file reselection, cancellation, invalid input rejection, single play/pause, double/drag seeking, ordering and translucent time-only badge.

Typecheck, production build and all 17 Node test groups passed. The complete production-browser regression passed: 38 file-import cases, the browser and drag suites, five UI sizes, 20 seek-order groups and 84 tap-playback cases. After adding a guard for synchronous progress-write failures inside an IndexedDB callback, the final production build passed all 23 local-session cases, with no page errors and no non-read network requests. Raw results are in [results](results/), including [local-session results](results/local-session-results.json). The persistent-profile test verified an actual Chromium close/reopen; progress testing observed two small writes over approximately 4.6 seconds and no Blob rewrites.

Physical iPad, Safari/WebKit, OS eviction, actual quota exhaustion and private user media are untested. Touch/viewport emulation is not a real iPad test. Detailed Vercel deployment API access and public-site access were previously denied in this environment; those routes are not bypassed. Deployment verification uses the allowed GitHub commit status and Vercel project summary, correlating their deployment IDs.
