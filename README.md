# UTube Music Harvester

UTube is a Python-first YouTube harvester that exposes both a CLI and a modern Qt GUI. You can search by genre or artist, sprinkle in filters, preview streams, and download the resulting audio assets through yt-dlp + ffmpeg. Everything respects user-overridable defaults (download location, formats, JS runtime, remote components, etc.) so CLI and GUI behave consistently.

<img width="1914" height="1031" alt="image" src="https://github.com/user-attachments/assets/64a9d0fc-239d-43a2-bca4-3885a26732d9" />
UTube GUI overview

## Quick setup

1. Create a virtualenv (recommended) and install the package:
   ```bash
   pip install -e .
   ```
2. Copy `.env.example` to `.env` and edit the keys you care about. Essential entries:
   ```ini
   UTUBE_DOWNLOAD_DIR=~/Music/utube
   UTUBE_AUDIO_FORMAT=opus
   UTUBE_STREAM_FORMAT=bestaudio/best
   UTUBE_JS_RUNTIME=node
   UTUBE_REMOTE_COMPONENTS=ejs:github
   ```
   `UTUBE_JS_RUNTIME` ensures yt-dlp uses Node/Deno, and `UTUBE_REMOTE_COMPONENTS` downloads the EJS solver script that YouTube often requires.

## Running the CLI

Use the installed script:
```bash
utube trance --mode download --max-results 40 --audio-format opus --bitrate 256
utube ambient --mode stream --max-results 10 --safe-for-work
```

Pass `--js-runtime node --remote-components ejs:github` if `.env` doesn’t already define them. The CLI prints downloaded file paths or stream URLs, depending on `--mode`.

## GUI Usage

Start the interface with:
```bash
utube-gui
```

Then:
1. Use the genre/artist fields plus filters (duration, views, keywords, safe-for-work).
2. Set JS runtime (`node` is recommended) and remote components (`ejs:github`) in place to satisfy yt-dlp’s JS challenge requirements.
3. Adjust **Max entries** to limit how many yt-dlp search hits are fetched (default 10, up to 500).
4. Click **Search** — results populate the sortable table instantly.
5. Select a row and click **Play Selected**; use the Rewind/Forward/Stop buttons to control preview playback.
6. Select and download tracks using **Download Selected**; change download folder as needed.

Long-running searches/downloads run in `Worker` threads so the UI stays responsive. The dark, card-based theme and sidebar reflect the modern UI direction.

## Internal architecture

- `src/utube/config.py`: loads `.env`, detects runtime, exposes defaults (`CliDefaults`) that include JS runtime + remote components.
- `src/utube/controller.py`: turns `MediaRequest` → `search_tracks + DownloadManager/Streamer`, passing runtime + remote component hints everywhere.
- `src/utube/extractor.py`: builds yt-dlp queries and now injects `js_runtime` plus the `{runtime: {path}}` dict expected by yt-dlp, along with the `remote_components` list.
- `src/utube/storage.py`: downloads audio via FFmpeg postprocessors or resolves streams, respecting runtime/component defaults and choosing audio-only formats for previews.
- `src/utube/cli.py`: exposes flags for genre/artist/filters, runtime, remote components, and `max-results`; prints summaries when done.
- `src/utube/gui.py`: PyQt6 app with sidebar, cards, filters, track table, and playback row; exposes JS runtime, remote components, max entries, and download controls.

## Common issues & hints

- **“No supported JavaScript runtime” warning**: ensure Node (or Deno) is installed and `UTUBE_JS_RUNTIME` points at it (e.g., `node`, `C:\Program Files\nodejs\node.exe`). Restart the CLI/GUI after editing `.env`.
- **Challenge solver script missing**: add `UTUBE_REMOTE_COMPONENTS=ejs:github` or pass `--remote-components ejs:github`; the GUI field does this too.
- **ffmpeg missing**: install ffmpeg and make sure it’s on your PATH so downloads succeed.
- **No tracks returned**: raise “Max entries”, loosen duration/view filters, or broaden the genre/artist query.
- **Tk-like warnings in GUI**: install `PyQt6` and `PyQt6-sip`. Use the same Python environment where you run the CLI.

## Testing

```bash
python -m pytest
```

The test suite covers config defaults, CLI parsing (including remote components), extractor filtering, and storage integration. Rename or temporarily move `.env` if you don’t want your overrides to influence the tests.
