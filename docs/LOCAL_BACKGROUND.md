# Local background and cover images

Images selected with the existing cover-image picker (or album-panel file drop) are decoded, displayed and automatically saved as their original `Blob` bytes. The same image source supplies the album cover and the chosen background renderer. The existing background-style preference still determines whether the background is a photo or a generated gradient; selecting an image does not silently change that preference.

The existing **本機** menu now reports image-save status separately, with **保存背景／重試** and **清除背景圖片**. Clearing only the image removes its stored bytes and current custom image without changing audio/captions/progress. **清除全部保存檔案** and full-player Reset clear the image as well as the media session. A failed clear reports that the preceding stored image may still return on reopening. Original files should be retained because browser/site data can be removed.

## Storage and restoration

The existing `amll-local-session-v1` IndexedDB database and version remain unchanged. `media['background']` holds `{version:1, blob, name, type, lastModified}` independently of the existing `media['last']` audio/caption pair and `progress['last']`. No object URL, image URL or base64 string is saved as a substitute for file bytes. Each restore validates the record, decodes its image and creates a fresh object URL. Retired object URLs are revoked. Background writes/clears do not rewrite the audio Blob. Media-session clear deletes only its own keys; the UI explicitly coordinates clearing both independent records when requested.

An image must be nonempty, at most 20 MiB, decodable by the current browser and no more than 64 million pixels. Empty or incorrect provider MIME types can still work when the browser decodes the actual bytes. A bad/unsupported/oversize choice leaves the preceding valid image intact. Save success is reported only after the IndexedDB transaction completes. Quota errors and transaction aborts preserve the preceding record and keep the new preview usable; Retry can save it later. Serialized writes and revision checks prevent a pending save or slow startup read from winning over Clear or a newer selection.

Old sessions without this separate record still restore audio and captions. The old version never stored original custom-image bytes, so its expired `blob:` URL cannot be recovered: select the original image once to save it. Damaged image records produce an image-specific error without blocking audio/caption restoration. Explicit URL/data-URL cover input remains visit-only and leaves the prior local image record intact; select a local image to retain its bytes. Custom images take precedence over later audio metadata artwork. Local files are not uploaded.

## FPS/stats inspection (no UI removal)

The current code creates a `stats.js` panel at fixed top-left `(0,0)` with a high z-index. Its FPS display is cyan on dark blue; clicking the panel cycles to the **MS** timing display, which is green on near-black. This matches the described green/black box, though the user's screenshot was not available in this execution workspace for direct comparison.

Open the existing settings panel by tapping the album-side title/information area (`H` with a keyboard), find **Global / 全局 → Show Performance Monitor / 显示性能监控** (the `showFPS` checkbox), and uncheck it. The preference is saved. If the checkbox is already off while the box is visible, check it once and uncheck it again. The existing bottom-right five-tap shortcut toggles the preference and then directly toggles the DOM again, so its state can disagree with the checkbox. That pre-existing shortcut and all related UI are intentionally unchanged in this task. The regular checkbox and reload behavior are tested.

## Validation limits

`tests/local_background.py` uses generated PNGs and synthetic audio/captions with real Chromium IndexedDB transactions and persistent browser-profile restart. It verifies exact binary hashes, fresh object URLs, replacing/reselecting/cancelling, invalid/oversize files, quota/abort/delete failures, retry, save/clear, delayed multi-file load and startup-read races, old/corrupt data, custom-image priority, independent/all-data clear, Reset, mobile menu bounds and the existing stats checkbox. Storage errors are injected; no physical disk-exhaustion or iPad Safari test is claimed. No non-read network requests are allowed by the test assertions. The test does not use the user's private audio or original background image.

All 19 image scenario groups passed with no page errors or non-read network requests: [image results](results/local-background-results.json). Three additional Node tests cover record validation, failed replacement/retry and in-flight clear ordering. The real settings checkbox was separately checked for hiding the stats panel across reload: [inspection result](results/stats-inspection.json). The short-landscape menu keeps media Save/Clear actions near the top, while the panel can scroll to image actions and notes.

The complete regression run passed all 13 browser suites, 28 Node tests, type checking and the production build. It includes 45 browsing/seek cases, 84 tap cases, 24 same-line replays, persisted settings, file imports, local media and responsive layout: [combined results](results/browse-background-regression-results.json).
