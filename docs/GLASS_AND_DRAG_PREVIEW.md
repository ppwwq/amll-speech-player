# Glass controls and native lyric preview

Baseline: `a45cd21edf95853e04be2439bf900e5ccfaea4ed`. Changes apply to the audio/caption picker buttons, drag-seek toggle, and local-save summary/panel/actions. Storage implementation, import validation, audio timing and sorting are unchanged.

## Glass styling

The former dark fills are replaced with pale translucent glass, white highlights and dark plum labels. The active drag toggle has an inset outline as well as its existing 開/關 text and `aria-pressed` state. Error, disabled, keyboard-focus and forced-color states remain visible. Controls retain their existing layout and minimum 44px height.

Backdrop blur is limited to 10px on the small toolbar controls, summary and open panel. Nested action buttons have translucent fills without an additional blur layer. No blur animation or full-screen filter was added. Both `backdrop-filter` and `-webkit-backdrop-filter` are supplied; [WebKit documents the older prefixed implementation and Safari 18's unprefixed support](https://webkit.org/blog/15443/news-from-wwdc24-webkit-in-safari-18-beta/#backdrop-filter). Without either property, a more opaque pale fill preserves legibility. Reduced-transparency and forced-color modes disable the blur.

The conservative text contrast calculation (base glass over pure black, ignoring the brighter highlight gradient) is 5.37:1 for enabled labels. Screenshots were also inspected over white, black, the actual artwork background and a colored stripe backdrop. The fallback was exercised by removing the feature-query rule in Chromium; this does not constitute a Safari test.

## Existing AMLL integration

The installed dependency remains `@applemusic-like-lyrics/core@0.2.0-alpha.5`. Inspection of its shipped `LyricLineEl.setTransform`, `lineTransforms.scale`, `update`, word-mask variables and `calcLayout` showed no independent preview-line API. Calling `enable` or changing current time would affect timed word/playback state, so preview instead reuses the existing line renderer and native scale spring through the project's existing pinned-version adapter.

The current drag candidate receives opacity 1 and a scale target of at most 103%. Target extra height is capped at 12px for very tall wrapped rows. The existing word-mask variables brighten that row without starting word animations. Position continues to follow the finger immediately; the native scale spring handles enlargement and recovery. No second transform, animation loop or library dependency was introduced.

Candidate selection still uses cached unscaled top/height values. The library's vertical-centre transform origin keeps the visual centre stable; scaling does not change measured layout, line order, active playback indices or audio time. Changing targets restores the prior row, and release/cancel clears the preview. The white candidate rectangle was removed; the centre guide and translucent time-only badge remain. Keyboard focus outlines are separate and retained. Reduced-motion mode provides text emphasis without preview zoom.

## Validation and limits

Production-build Chromium checks cover desktop, tablet landscape/portrait and phone landscape/portrait layouts, real file chooser activation, click/touch interaction, Tab/Enter control activation, visible focus, bounds, hit targeting, light/dark backgrounds, disabled/error states and the no-blur/forced-color fallbacks. The existing global Space playback shortcut is unchanged; Enter activates focused toolbar buttons.

`tests/drag_preview.py` checks native spring progression, a single target, stable cached geometry and visual centre, wrapped text without overlap/clipping, unchanged audio/lyric clocks before release, one seek on release, cleanup on cancellation and retained keyboard focus. It includes desktop, tablet, wrapped phone text and reduced-motion cases. Raw results are in [results](results/).

Typecheck, the production build and all 17 Node tests passed. Production-browser validation passed all 23 local-session cases, four new preview scenarios, five UI sizes, 20 seek-order groups, 84 tap-playback cases, and the existing browser/drag suites, with no page errors. The 2,000-line browser check mounted five rows and measured approximately 0.1ms p95 renderer-update time in this environment; this is not an iPad performance claim. Local-session checks ran after the glass CSS change; gesture, preview, ordering and UI checks ran after the AMLL adapter change.

All media used is synthetic. Physical iPad/Safari rendering and performance have not been measured; Chromium touch/viewport emulation is not a substitute. Production deployment is correlated using the allowed GitHub commit status and Vercel project summary because direct site access and detailed deployment access were previously denied in this environment.
