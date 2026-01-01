# UTube Music Harvester

UTube is a Python-first YouTube harvester that exposes both a CLI and a modern Qt GUI. You can search by genre or artist, sprinkle in filters, preview streams, and download the resulting audio assets through yt-dlp + ffmpeg. Everything respects user-overridable defaults (download location, formats, JS runtime, remote components, etc.) so CLI and GUI behave consistently.

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
   UTUBE_VIDEO_QUALITY=high
   ```
   Set `UTUBE_MEDIA_FORMAT=mp4` (or reuse `UTUBE_AUDIO_FORMAT`) when you need MP4 video downloads instead of audio-only output.
   Use `UTUBE_VIDEO_QUALITY=high|medium|low` to prefer the desired MP4 resolution when multiple options exist.
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
3. Adjust **Max entries** by dragging the slider—this is the only control for that limit, and the tooltip reveals the current count. A higher value fetches more hits into the live-updating table.
4. Click **Search** — results populate the sortable table instantly.
5. Select a row and click **Play Selected**; use the Rewind/Forward/Stop buttons to control preview playback. MP3 selections stay in the audio player while MP4 selections activate the video canvas and the waveform/seek bar keeps pace.
6. Select and download tracks using **Download Selected**; change download folder as needed.

Long-running searches/downloads run in `Worker` threads and update the table in real time, so the dark, card-based theme, format tabs, and bottom playback bar feel like a cohesive music workspace.

## Using the Qt visualizer

The Qt experience combines waveform, playback controls, and the dedicated media canvas so you understand exactly what is playing:

1. The seek toolbar sits above the waveform. Drag the slider or click the waveform to scrub (the tooltip on the slider reveals the current max entries value). Playback states update the transport buttons and info text.
2. The waveform mirrors amplitude above/below the center line, fills the area transparently, and highlights the played region in the accent color.
3. The media canvas below the waveform stays visible even during audio mode; when an MP4 is selected it hosts the video widget, and SoundCloud-style fractal visualization fills the space for MP3 tracks.
4. Format tabs (Any/MP3/MP4) let you filter results before playback; once a track starts, the media router chooses the appropriate player and updates the now‑playing label, so you can screenshot or record consistent playback states.

<figure>
<img width="1919" height="1028" alt="image" src="https://github.com/user-attachments/assets/fc982b0d-4881-4546-88de-dcb038092b8c" />
<figcaption>Figure 1: Audio mode with the filters, and the MP3 player harvester active.</figcaption>
</figure>

<figure>
<img width="1910" height="1030" alt="image" src="https://github.com/user-attachments/assets/359118df-db73-4051-9dd0-1cbc44476ab1" />
<figcaption>Figure 2: Audio mode with the mirrored waveform, transport controls, and the MP3 player active.</figcaption>
</figure>

<figure>
<img width="1913" height="1031" alt="image" src="https://github.com/user-attachments/assets/013ef890-87cb-4548-9ee7-fcd1a52dc1a9" />
<figcaption>Figure 3: Video mode surfaces the media canvas beneath the controls and shows the MP4 preview.</figcaption>
</figure>

## Internal architecture

- `src/utube/config.py`: loads `.env`, identifies JS runtimes/remote components, and exposes defaults (download directory, stream format, audio/video quality).
- `src/utube/controller.py`: orchestrates `MediaRequest`s → `search_tracks` + `DownloadManager`/`Streamer`, passing runtime/component hints and the UI’s mp3/mp4 preference downstream.
- `src/utube/extractor.py`: crafts yt-dlp search requests, applies filters, infers `file_type`, and returns normalized `TrackMetadata`.
- `src/utube/storage.py`: contains the downloader (FFmpeg postprocessing) and streamer (mp3/mp4 preference) while honoring runtime/remote component overrides.
- `src/utube/cli.py`: exposes genre/artist filters, runtime/remote component flags, `max-results`, and download settings; prints summaries of downloads/stream links.
- `src/utube/gui.py`: Qt6 GUI with docked filters, format tabs, waveform/video playback, and threaded Workers that reuse the same controller logic as the CLI.

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
