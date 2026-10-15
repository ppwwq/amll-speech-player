# Local file picker repair — 2026-10-15

Baseline: `b5f4e8a9c1bcaee6be4f1529e03ec1d97682778e` from the existing `ppwwq/amll-speech-player` main, cloned into the separate `/workspace/amll-speech-player-ipad-fix` directory. The smoke-notes project is untouched.

Story: iPad/local file selection → client-side file validation → audio playback / timed-caption rendering. This is a static browser flow with no application API or database. All test media are generated synthetic WAV/MP3/LRC/SRT; local files are never uploaded.

## Evidence and uncertainty

- Confirmed in baseline HTML: `musicFile` had `accept="audio/*,.mp3,.wav,.ogg,.m4a,.aac,.flac"`; `lyricFile` had `accept="text/plain,.lrc,.ttml,.yrc,.lys,.qrc,.ass,.lqe,.lyl,.spl,.srt"`. Every toolbar, panel, play/fullscreen and empty-transcript picker entry uses these inputs.
- **Inference, not an iPad reproduction:** a provider's type classification may disagree with `accept`, leaving a valid local file grey in the system chooser. [MDN's file-input documentation](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/input/file) describes `accept` as a chooser hint, with platform-dependent UI, and requires separate validation. No physical iPad, Files provider or Safari session was available to establish that this caused the reported intermittent grey state. File availability/provider problems remain possible.
- Confirmed reselection issue: the change handlers left native inputs populated, and `loadFromFiles` depended on their `files` lists. A Chromium control using the same disk path twice without clearing generated `["change", "cancel"]`, so the second choice could not run a change-only loader. Distinct in-memory File payloads do not reproduce this; the regression uses the same actual path.
- Confirmed false success: loading `arbitrary.bin` with empty MIME and `not timed captions` produced `Lyrics loaded successfully, total lines: 0` followed by `Lyrics file loaded successfully`, while `hasLyrics` was false. The parser also caught exceptions without returning failure to its caller. Drop handlers and change-only icon handlers could display an unvalidated selection as loaded.
- The initial extension gate already ignored case; the format-specific parser dispatch did not. The repair normalizes dispatch filenames too, without stripping `#` from local filenames.

## Changes

- Remove `accept` from the shared audio/caption inputs. All existing entry points now open an unrestricted picker, while cover-image selection retains its existing filter.
- Copy the File reference and clear the native input synchronously on change. Retain successful audio/caption selections independently for panel reload. Empty change/cancel events leave the prior media, captions, labels and success icons alone.
- Recognized audio extensions work with missing or incorrect MIME. A temporary local media element checks readable metadata and a positive finite duration before replacing the current track; invalid/empty/unsupported audio reports an error and retains the previous track. Known extensions receive the corresponding Blob MIME, but the browser still checks the actual bytes. Validation has a 15-second timeout and releases its resources.
- Captions must parse into readable timed text. Empty, binary, untimed, metadata-only and broken files return failure, preserve previous captions, and cannot update success labels/icons. A missing MIME alone is not treated as proof of valid captions. Direct/base64/URL parsing uses the same success result.
- Picker and drop loaders share validation. Newer selections/reset invalidate unfinished loads; stale audio metadata cannot replace the current selection's details. Replaced local object URLs are released.
- Transcript tap/drag state machine, sort/timing logic, typography and translucent drag-time styling are unchanged.

## Verification

The reproducible browser suite is `tests/file_import.py`, included in `npm run test:browser`. It checks initial play/empty-caption entry, toolbar and settings buttons, legacy right-click/hold entry, actual same-path reselection, simulated cancellation and reopen, empty/octet-stream/image/text MIME, mixed-case extensions, invalid and empty files, drag/drop, retained-file reload, parse-error propagation, overlapping loads and reset.

Cancellation uses chooser-empty, `cancel`, and empty `change` events because Playwright cannot operate the native iPad Cancel button. Native chooser routing is observed; the operating-system file browser itself is not tested.

- Strict TypeScript and all 9 Node test groups pass. Production Vite build passes; the pre-existing classic metadata-script and >500KB bundle warnings remain.
- `tests/file_import.py`: **38 groups pass**, with zero page errors. Empty MIME cases construct a browser `File` explicitly and assert its type: Playwright's in-memory upload helper substitutes a guessed MIME for an empty string, so it cannot establish this coverage on its own. The final import suite passed against the final production JS served at `http://127.0.0.1:4173/`.
- Existing `browser.py`, `drag_seek.py`, `ui_checks.py`, `seek_order.py` and `tap_playback.py` all pass against the production build, with zero page errors. This includes 20 seek/order groups, 84 playback-tap cases, and 5 viewport sizes (1280×900, 1024×768, 768×1024, 390×844, 844×390). Tablet portrait, narrow phone and phone-landscape drag screenshots were visually reviewed. Single play/pause, double/drag seek, sorted lines and the translucent time-only badge remain covered.
- Raw results are in `docs/results/{file-import,browser,drag-seek,ui,seek-order,tap-playback}-results.json`. Synthetic media and screenshots stay in ignored `test-results/`.

Release uses only the existing GitHub main → Vercel Git integration. Project basics identify `prj_ep1uPLZbO9uJrP1wzqWkFujn7V1s`, team `team_8xRXiaV0EfXXQbrntMCWZeNy`, Vite, and `amll-speech-player.vercel.app`. The detailed deployment-list API returned 403 for this scope; no CLI is installed. The environment's outbound proxy also rejected public-site access (`Tunnel connection failed: 403 Forbidden`). No access control or proxy workaround was attempted. Final release evidence is reported separately: GitHub Actions for the exact commit, its Vercel status target deployment ID, and that same ID's READY/production state from the readable project summary.

Remaining limits: Linux Chromium and touch/viewport emulation cannot prove Safari/WebKit or physical iPad behavior, and the denied public-site request prevents a live-site browser test here. The user's private recordings/files were not supplied or accessed. No dependency, hosting, protection, credential or billing changes are part of this repair.
