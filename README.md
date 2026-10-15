# AMLL Speech Practice

An independent, local-file speech practice player based on [HKLHaoBin/amll-web](https://github.com/HKLHaoBin/amll-web), snapshot `60346fb3e4a6552740fe2c6826689a466877a92c`. It retains AMLL's multi-line typography, sentence highlighting, springs and automatic following.

Choose **Audio** and **Captions** to open local audio and timed subtitles (SRT, LRC, TTML and the upstream formats). Local files use browser object URLs; they are not uploaded. Remote URLs remain an explicit upstream option.

**Tap the transcript to play or pause.** A single click/tap on a sentence or empty transcript space waits for the 320ms double-tap window, then toggles playback without seeking. Double-click/double-tap a sentence seeks once and preserves playback state. Cancelled gestures, multi-touch, long holds and controls do not toggle playback; unloaded audio is ignored. Enter/Space activates a focused sentence.

**Drag to seek is on by default.** Drag the transcript vertically, align a sentence with the centre guide and release: audio seeks once to the shown time. A compact translucent badge shows only the target audio time (`mm:ss.mmm`), with no instruction or sentence text. Invalid candidates show no time badge. During the drag, playback continues and the candidate preview does not seek. Release outside the transcript to cancel. The **拖動跳播：開／關** switch turns this into ordinary inertial browsing and remembers your preference. The mouse wheel always browses. Single and double taps work in either mode.

Seeking preserves play/pause. A chosen sentence outside an A–B range exits the range; other seek controls stay inside it. **Follow** returns to playback, or following resumes after five idle seconds. Cancelled gestures, multi-touch, long holds, changed media/delay, orientation changes, and sentences without a playable timestamp never commit a drag seek. The offset convention is `lyric milliseconds = audio seconds × 1000 + offset milliseconds`; the guide displays the corresponding audio time.


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

`dist/` is self-contained and works under a repository subpath. A GitHub Pages workflow is included. Once a new repository is available, push `main`, set Pages to **GitHub Actions**, and run the workflow. No backend, database, API key, paid service, or analytics is required. This environment has not yet published the project; see the validation report for the authentication blocker.

The broken upstream development service worker has been removed. This build does not promise offline caching. The **Source · AGPL-3.0** link downloads the build's corresponding source archive from the same static host, including build/test scripts and the dependency lockfile.

## License and attribution

AGPL-3.0-only; see [LICENSE](LICENSE) and [NOTICE](NOTICE). Upstream LICENSE and README specify AGPL-3.0, while its package metadata said MIT; this fork corrects that metadata and keeps the license verbatim. Original README and acknowledgments are preserved in [README.upstream.md](README.upstream.md) and [README_zh.md](README_zh.md). The AMLL core library is GPL-3.0. All upstream authors' notices are retained.
