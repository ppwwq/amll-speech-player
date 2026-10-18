# AMLL Speech Practice

An independent, local-file speech practice player based on [HKLHaoBin/amll-web](https://github.com/HKLHaoBin/amll-web), snapshot `60346fb3e4a6552740fe2c6826689a466877a92c`. It retains AMLL's multi-line typography, sentence highlighting, springs and automatic following.

Choose **Audio** and **Captions** to open local audio and timed subtitles (SRT, LRC, TTML and the upstream formats). Local files use browser object URLs; they are not uploaded. Remote URLs remain an explicit upstream option.

Audio and caption pickers show all files for compatibility with iPad Files providers. Choose your MP3/LRC (or another supported format); the player checks it after selection and shows an error for unreadable audio or captions without timed text. Filename extensions are case-insensitive, including when the provider supplies an empty or incorrect MIME type. You can select the same file again. Cancelling keeps the last successful selection, and the panel's **Load** button can reload it. See [file import validation and device limits](docs/FILE_IMPORT_REPAIR.md).

**Remember the last local files and position.** Successful audio/caption imports are saved in this browser. Refreshing or reopening restores the complete audio, captions, caption offset and position **paused**; click play to continue. The **���C** menu shows the actual storage result and offers **����Ŀǰ�n������ԇ** and **�������n��**. Switching to a different audio file clears the old caption association; select its captions next. Captions selected before the first audio are paired with that audio. Clearing saved data keeps the current player usable and stops automatic saving until another file is selected or Save is pressed. Reset also clears the saved session.

Files stay in IndexedDB on this device; no audio or captions are uploaded. Small progress checkpoints and user preferences use localStorage. Progress is saved about every two seconds, with a checkpoint on pause, seek and page hiding. A crash or forced termination can lose the most recent unsaved progress. Browser storage may be unavailable, fill up, or be removed by the browser/user; keep your original files. A failed replacement leaves the last successfully saved pair intact and shows an error. Explicit remote-URL/direct-text playback remains available but does not automatically replace the saved local-file session. This feature does not cache the website for offline use. See [storage design, tests and limits](docs/LOCAL_SESSION.md).

**Settings save automatically.** Speed, volume, repeat, drag mode, lyric appearance, background/cover options and the other existing display preferences return when you reopen this browser. The **���C** menu reports settings-save failures separately; changes remain usable and the next change retries. Restoring still starts paused. Clearing saved files keeps settings, while the player's Reset restores defaults. See [saved items, validation and tests](docs/PREFERENCES.md).

**Local background/cover images also survive reopening.** Selecting an image saves its original bytes in IndexedDB and recreates its display URL on restore. The **���C** menu shows image-save status, **���汳������ԇ**, and **��������DƬ**; clearing just the image keeps audio and captions. Clear All and Reset remove both. Images must decode in this browser and fit within 20 MiB / 64 million pixels. Explicit URL backgrounds remain visit-only. No local media is uploaded. See [image storage, failures, tests and the FPS-panel switch](docs/LOCAL_BACKGROUND.md).

**Tap the transcript to play or pause.** A single click/tap on a sentence or empty transcript space waits for the 320ms double-tap window, then toggles playback without seeking. Double-click/double-tap a sentence seeks once and preserves playback state. Cancelled gestures, multi-touch, long holds and controls do not toggle playback; unloaded audio is ignored. Enter/Space activates a focused sentence.

The audio/caption buttons, drag toggle and local-save menu share the original settings panel's transparent glass material and theme text colors. During drag-to-seek, the target sentence gently enlarges and brightens through AMLL's existing renderer instead of showing a rectangular outline. The time badge remains visible; audio only seeks on release. Reduced-motion mode keeps the text emphasis without zooming. See [visual verification and library integration](docs/GLASS_AND_DRAG_PREVIEW.md).

The transcript stays below the top control rows in both orientations, including wider portrait tablets. See [header overlap evidence and device limits](docs/TOP_LAYOUT.md).

**Drag to seek is on by default.** Drag the transcript vertically, align a sentence with the centre guide and release: audio seeks once to the shown time. A compact translucent badge shows only the target audio time (`mm:ss.mmm`), with no instruction or sentence text. Invalid candidates show no time badge. During the drag, playback continues and the candidate preview does not seek. Release outside the transcript to cancel. The **�τ��������_���P** switch turns this into ordinary inertial browsing and remembers your preference. The mouse wheel always browses. Single and double taps work in either mode.

The midpoint of the space between adjacent sentences separates their drag-selection regions, including wrapped sentences. Releasing on the current sentence replays it from the beginning; you do not need to select another sentence first. Playing audio keeps playing, and paused audio stays paused. This does not enable automatic looping. See [same-sentence replay and boundary tests](docs/DRAG_REPLAY.md).

Ordinary browsing with the mouse wheel or with drag-to-seek turned off stays at your browsing position, including after five idle seconds. Press **Follow** or explicitly seek to resume following at the configured alignment. Double-tapping a sentence and releasing a valid drag selection both seek and resume following, including same-sentence replay. Seeking preserves play/pause. Loading new captions resets their layout. A chosen sentence outside an A�CB range exits the range; other seek controls stay inside it. Cancelled gestures, multi-touch, long holds, changed media/delay, orientation changes, and sentences without a playable timestamp never commit a drag seek. The offset convention is `lyric milliseconds = audio seconds �� 1000 + offset milliseconds`; the guide displays the corresponding audio time. See [browsing behavior and tests](docs/BROWSE_POSITION.md).


## Development

Use Node 22.12+ and pnpm 10.13.1:

```sh
pnpm install --frozen-lockfile --ignore-scripts
pnpm dev
pnpm typecheck
pnpm test
pnpm build
pnpm preview --host 0.0.0.0
```

Browser regression tests use Python Playwright, FFmpeg (to generate synthetic MP3), and a local Chromium installation. With the dev or preview server running:

```sh
python -m pip install playwright
CHROMIUM_PATH=/usr/bin/chromium PLAYER_URL=http://localhost:5173/ pnpm test:browser
```

Tests generate only synthetic WAV/MP3 and SRT/LRC data in ignored `test-results/`. No personal recording belongs in this repository. See [investigation and validation](docs/VALIDATION.md) for the verified causes, measurements and remaining device checks.

## Static deployment

`dist/` is self-contained and works under a repository subpath. Cloudflare Workers Static Assets serves the player at [amll-speech-player.philipwwq.workers.dev](https://amll-speech-player.philipwwq.workers.dev/), using `wrangler.jsonc`. No server function or application secret is required. Build and deploy with an already authorized Cloudflare account:

```sh
pnpm install --frozen-lockfile --ignore-scripts
pnpm typecheck && pnpm test && pnpm build
pnpm dlx wrangler@4.129.0 deploy
```

Cloudflare deployment currently uses the CLI. GitHub Actions runs type checks, tests and the production build; it does not deploy to Cloudflare. To enable automatic deployment, connect `ppwwq/amll-speech-player` in the Worker's **Settings > Builds**, authorize only the required repository if prompted, and choose production branch `main`, build command `pnpm build`, deploy command `pnpm dlx wrangler@4.129.0 deploy`, Node 22.12+ and pnpm 10.13.1. An authorized build token is also required. The configuration file alone does not enable this integration.

The existing [Vercel site](https://amll-speech-player.vercel.app/) and its Git integration remain available. There is no redirect between the two sites. Browser storage is isolated by origin: the Cloudflare site starts with separate saved files, progress, background and settings. Reimport original files at the new site; keep the old site available to recover its saved session. No automatic browser-data migration is provided.

To return immediately to the previous host, open the Vercel URL. To roll back a future Cloudflare release, use `pnpm dlx wrangler@4.129.0 rollback <VERSION_ID>` from this project, or rebuild a known good commit and redeploy it. The first deployment has no earlier Cloudflare version to roll back to.

The broken upstream development service worker has been removed. This build does not promise offline caching. The **Source �� AGPL-3.0** link downloads the build's corresponding source archive from the same static host, including build/test scripts and the dependency lockfile.

## License and attribution

AGPL-3.0-only; see [LICENSE](LICENSE) and [NOTICE](NOTICE). Upstream LICENSE and README specify AGPL-3.0, while its package metadata said MIT; this fork corrects that metadata and keeps the license verbatim. Original README and acknowledgments are preserved in [README.upstream.md](README.upstream.md) and [README_zh.md](README_zh.md). The AMLL core library is GPL-3.0. All upstream authors' notices are retained.
