## UTube Music Harvester Architecture

### Overview
UTube is designed as a Python-first harvester that connects a CLI/GUI front end to a yt-dlp powered backend pipeline. 
The goal is to let users describe what musical content they need (genre, artist, filters), then either download audio assets or resolve stream URLs while respecting environment defaults (download paths, JS runtime, remote components).

### Core Components
- **Configuration** (`src/utube/config.py`): reads `.env` overrides, detects if Node/Deno is available, and exposes defaults for download directory, media formats, JS runtime, and remote component lists. CLI and GUI both share these defaults.
- **Controller** (`src/utube/controller.py`): translates `MediaRequest` objects into extraction/filter requests and forwards the results either to `DownloadManager` or `Streamer`. It now propagates the JS runtime + remote component settings to every downstream yt-dlp call.
- **Extractor** (`src/utube/extractor.py`): builds yt-dlp search queries, applies filters (duration, views, safe-for-work), and thanks to the helpers now provides `js_runtime` + `remote_components` entries via the `js_runtimes` dict expected by modern yt-dlp releases.
- **Storage/Streaming** (`src/utube/storage.py`): downloads audio via `DownloadManager` (with FFmpeg postprocessors) or resolves stream URLs via `Streamer`. Both components inject the runtime/component settings, so yt-dlp can solve JS challenges and fetch the richest formats. `_select_format` ensures only audio formats are chosen for streaming previews.
- **CLI** (`src/utube/cli.py`): wraps the pipeline with `argparse`, exposes `--js-runtime`, `--remote-components`, filters, and `--max-results`, and prints summaries of downloads/stream links. It relies on the shared defaults from `config`.
- **GUI** (`src/utube/gui.py`): PyQt6 dark-themed application with a sidebar, cards, filter controls, searchable track table, and playback row. It surfaces genre/artist inputs, filter controls (duration, views, keywords), JS runtime/remote component fields, and the “Max entries” spinner. Search/download/stream operations run via `Worker` threads; playback uses `QMediaPlayer` with new rewind/forward/stop buttons, keeping the interface responsive.

### Data & Control Flow
1. User input flows from the CLI/GUI into a `MediaRequest` (via `load_defaults` for repeated settings).  
2. The controller executes `search_tracks` with the provided filters, max results, runtime, and remote components.  
3. `search_tracks` calls yt-dlp, receives metadata, filters it, and returns track records.  
4. Depending on the requested mode, the controller either invokes `DownloadManager.download_tracks` or `Streamer.stream_links`.  
5. Each storage operation configures yt-dlp with `js_runtime`, the `{runtime: {path}}` map, and `remote_components` to ensure Node + EJS helpers are used. Streamer also filters to audio-only formats.

### UX & Runtime Considerations
- The GUI is styled with clean cards, dub-ready colors, and a three-zone layout (sidebar, workspace, status).  
- Long-running tasks run in `Worker` threads so the UI stays responsive; results trigger table updates and status messages.  
- Playback controls (rewind/forward/stop) operate directly on `QMediaPlayer`, making it easy to preview before downloading.  
- `.env` (or `UTUBE_*` overrides) lets users configure download directories, audio formats, stream formats, JS runtime names, and remote components like `ejs:github`. The CLI/GUI automatically pass these values downstream.
- Default `max_results` is set to 100 but the GUI exposes a spinner for QA to adjust it live.

### Testing
- `tests/` cover config defaults, CLI argument parsing (including remote components), extractor filtering, storage integration, and ensuring the new plumbing works. `python -m pytest` currently passes 17 tests.

