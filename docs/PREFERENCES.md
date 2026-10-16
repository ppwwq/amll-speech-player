# Automatic preference saving

Changes to existing controls are saved automatically in this browser. The existing **本機** menu includes a separate setting-save status; its media-save actions and transparent glass material are retained. There is no new settings panel. Restoring preferences never calls play. Local audio, captions, subtitle delay and playback position continue to use the existing IndexedDB session/checkpoint implementation and restore paused.

The allowlist contains 49 fields. The existing controls exercise 48 of them; `backgroundDynamic` also preserves the prior setting/reduced-motion default.

| Group | Saved preferences |
| --- | --- |
| Playback and gestures | Speed, volume, whole-track repeat, remaining-time display, drag-to-seek/browse switch |
| Lyrics | Vertical alignment position and anchor, word fade width, passed-line visibility, blur, scale, spring enabled, translation, romanization, translation/romanization swap, background lyrics, left/right layout swap, ±400ms timing expansion, single-line display |
| Springs | Position and scale mass, damping, stiffness and soft mode |
| Background | Style, dynamic mode, flow speed, color-mask enabled/color/opacity, render scale, FPS, low-frequency response, FFT minimum/maximum, color inversion, three manual theme colors, applied mesh control-point JSON |
| Cover and other display | Cover style, rounding, rotation, cover blur, title marquee and FPS display |

Per-recording subtitle delay stays with the media session rather than becoming a default for unrelated recordings. Media URLs/files, song metadata, A–B ranges, playback/paused state, full-screen state and an unfinished/invalid control-point draft are not serialized as preferences. Settings never contain or upload local media. Clearing saved files keeps preferences. The existing full-player Reset restores default preferences and retains its existing media-clear behavior. Browser/site-data removal can remove both stores.

`amll_speech_preferences_v1` stores `{version: 1, values: ...}`. The reader accepts only known fields, strict booleans, finite numbers within the existing controls' ranges, supported choices and six-digit hex colors; it also rejects inverted FFT ranges. Valid fields survive independently when another field is invalid. The existing mesh JSON formats are accepted only with finite values, a 2–64 point grid per axis and bounded input size/count before reaching the renderer. Invalid drafts leave the last applied configuration saved.

Older `amll_speech_background_settings_v1` and `amll_speech_drag_seek_v1` data are read and validated when no current record exists. Reading never writes: constructor/render initialization is gated until settings have been applied, and automatic theme-color updates no longer write settings. The next user change saves the current version. This retains meaningful `0` and `false` values. A future schema version is preserved unchanged and shows that changes cannot be saved by this version of the app. Corrupt data can recover on the next valid change.

A failed/quota-denied write keeps the preceding stored record, leaves the current controls usable, and reports that settings have not been saved. A subsequent change retries. A blocked storage getter/read is caught as well. Explicit URL speed/volume/repeat options override restored preferences for that visit without overwriting the saved defaults during startup. Default playback rate is also applied so media loading cannot silently reset the chosen rate.

The previous implementation omitted speed, volume, repeat, remaining-time mode and several lyric switches from save calls; some restored settings updated neither controls nor renderer methods. It used unchecked stored values and unguarded writes. Its two soft-spring checkbox cache IDs also did not match the HTML, so those controls never reached their handlers. This change repairs those gaps while retaining the existing renderer and seek paths.

`tests/preferences.py` checks every existing setting control immediately after its change, reload without initialization writes, persistent-profile browser restart, complete audio/caption/position/delay restoration without a play attempt, double-tap and same-sentence drag replay after restore, saved seek position, URL precedence, clear versus Reset, legacy/corrupt/future records, injected quota/access errors and mobile menu bounds. Positions at or beyond the audio end also restore paused with repeat enabled. Input/change events exercise settings controls; actual touch events exercise playback gestures. The twelve scenario groups are recorded in [preferences-results.json](results/preferences-results.json).

Validation passed TypeScript checking, 25 Node tests and the production build, plus the 12 preference groups above, all 23 existing local-session cases, the general browser suite (including 2,000-line virtualization), four drag-replay viewports, five UI/import/gesture viewports and 16 top-layout configurations. The general browser suite explicitly selects browse mode for its manual-scroll cases after Reset, since Reset now restores the default drag-to-seek preference too. No browser page errors occurred. This lists the suites run for this change, rather than claiming the entire `test:browser` command was executed.

All browser tests use synthetic media on a local production build in Chromium, including mobile viewport/touch emulation and browser-profile restart. No physical iPad Safari, OS eviction or actual disk-exhaustion test is claimed. Storage failures are injected. No non-read network request occurred in the preference/session tests.
