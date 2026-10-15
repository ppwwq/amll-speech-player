# Glass controls and native lyric preview

Current material correction starts from `5441d715144ea413572d80022b0ef21054e0708c`. It only changes CSS and documentation; storage, imports, audio timing, sorting and the AMLL preview implementation are unchanged.

## Glass styling

The original `index.html` already contained the desired material: `#controlPanel` used a 20%-white-to-transparent gradient, 10px backdrop blur, an 18% white border and its existing shadow; `.btn` used a 10% white fill (20% on hover), the same blur/border, and `--dominant-color-light` text.

The earlier change did not reuse these values. Its normal path layered a 66% pale base with a 6%-26% white gradient, yielding approximately 68%-75% light coverage before the bright 58% border and inset highlight. Hover and fallback paths were even more opaque. This explains the reported thick pink-white appearance without assuming a Safari failure. The original iPad's active CSS/media-query branch cannot be determined from the screenshot description alone.

The original values are now extracted as `--glass-panel-fill`, `--glass-control-fill`, `--glass-control-hover`, `--glass-border`, `--glass-backdrop` and `--glass-panel-shadow`. Original and new controls reference the same values. The added pale base, extra highlight and saturation filter are removed. The open save panel uses the panel material; audio/caption buttons and the summary use the original button material. Inner action buttons add no second blur. The original panel and `.btn` computed styles were compared before/after and remain equal.

The drag toggle retains 開/關 text and `aria-pressed`; a thin underline and slightly stronger border mark the active state without a heavy inset ring. Error, disabled and keyboard-focus states remain visible. Layout and 44px touch targets are preserved. Text follows the existing theme colors, including the existing color-inversion setting for light backgrounds; arbitrary user-selected foreground/background combinations are not guaranteed to meet a fixed contrast ratio.

Both `backdrop-filter` and `-webkit-backdrop-filter` retain the original 10px blur; [WebKit documents the older prefixed implementation and Safari 18's unprefixed support](https://webkit.org/blog/15443/news-from-wwdc24-webkit-in-safari-18-beta/#backdrop-filter). No new blur layers, animation or full-screen filters are introduced. Unsupported-filter and reduced-transparency modes use the existing theme's dark color for a readable fallback, not a pale opaque base. Forced-color mode uses system colors. No native OS menu is modified or reproduced.

## Existing AMLL integration

The installed dependency remains `@applemusic-like-lyrics/core@0.2.0-alpha.5`. Inspection of its shipped `LyricLineEl.setTransform`, `lineTransforms.scale`, `update`, word-mask variables and `calcLayout` showed no independent preview-line API. Calling `enable` or changing current time would affect timed word/playback state, so preview instead reuses the existing line renderer and native scale spring through the project's existing pinned-version adapter.

The current drag candidate receives opacity 1 and a scale target of at most 103%. Target extra height is capped at 12px for very tall wrapped rows. The existing word-mask variables brighten that row without starting word animations. Position continues to follow the finger immediately; the native scale spring handles enlargement and recovery. No second transform, animation loop or library dependency was introduced.

Candidate selection still uses cached unscaled top/height values. The library's vertical-centre transform origin keeps the visual centre stable; scaling does not change measured layout, line order, active playback indices or audio time. Changing targets restores the prior row, and release/cancel clears the preview. The white candidate rectangle was removed; the centre guide and translucent time-only badge remain. Keyboard focus outlines are separate and retained. Reduced-motion mode provides text emphasis without preview zoom.

## Validation and limits

The material correction passed production-build checks at six sizes, including 1536x1067, desktop, tablet landscape/portrait and phone landscape/portrait. Before/after screenshots and red/light/dark scenes were inspected. The light scene uses the app's existing color-inversion control. The checks compare material properties with the original controls, verify 44px bounds/hit targets, Tab/Enter toggle activation, visible focus, active underline, save/clear and error/fallback states. Results: [clear-glass-results.json](results/clear-glass-results.json). The existing global Space playback shortcut is unchanged; Enter activates focused toolbar buttons.

`tests/drag_preview.py` checks native spring progression, a single target, stable cached geometry and visual centre, wrapped text without overlap/clipping, unchanged audio/lyric clocks before release, one seek on release, cleanup on cancellation and retained keyboard focus. It includes desktop, tablet, wrapped phone text and reduced-motion cases. Raw results are in [results](results/).

For this CSS correction, the production build, all 23 local-session cases, five existing UI/gesture layouts and all four native-preview scenarios passed with no page errors. The previous `5441d71` release also passed typecheck, 17 Node tests, 20 seek-order groups, 84 tap-playback cases and browser/drag regressions; their TypeScript implementation is unchanged here.

All media used is synthetic. Physical iPad/Safari rendering and performance have not been measured; Chromium touch/viewport emulation is not a substitute. Production deployment is correlated using the allowed GitHub commit status and Vercel project summary because direct site access and detailed deployment access were previously denied in this environment.
