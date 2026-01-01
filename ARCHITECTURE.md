## UTube Music Harvester Architecture

### Overview
UTube is designed as a Python-first harvester that connects a CLI/Qt GUI front end to a yt-dlp + FFmpeg powered backend pipeline. Users describe their music needs (genre, artist, filter buckets, mp3/mp4 preference) and the controller either downloads audio/video assets or resolves stream URLs. Every step honors shared defaults (download directory, JS runtime, remote components, video quality so the CLI and GUI remain in sync).

### Core Components
- **Configuration** (`src/utube/config.py`): reads `.env`, detects Node/Deno availability, and exposes defaults (download directory, stream/audio formats, JS runtime, remote components).
- **Controller** (`src/utube/controller.py`): orchestrates `MediaRequest` → `search_tracks` + `DownloadManager/Streamer`, passing runtime/remote component hints and the UI’s mp3/mp4 preference downstream.
- **Extractor** (`src/utube/extractor.py`): crafts yt-dlp search queries, applies filters, infers `file_type`, and emits normalized `TrackMetadata` so the GUI can display format/type columns.
- **Storage/Streaming** (`src/utube/storage.py`): downloads audio/video via FFmpeg postprocessing or resolves stream URLs through `Streamer`, honoring runtime/component overrides and respecting mp3/mp4 preferences.
- **CLI** (`src/utube/cli.py`): exposes genre/artist filters, runtime/remote components, `max-results`, and download settings; it prints summaries of downloads or stream links.
- **GUI** (`src/utube/gui.py`): PyQt6 dark theme with sidebar filters, format tabs, waveform/video playback, and playback controls running in Worker threads; it reuses the same controller logic and streams mp3/mp4 preferences downstream.

### Repo layout (diagram)
```
UTube/
├─ assets/
│   └─ click.wav
├─ src/
│   ├─ utube/
│   │   ├─ cli.py
│   │   ├─ config.py
│   │   ├─ controller.py
│   │   ├─ extractor.py
│   │   ├─ gui.py
│   │   └─ storage.py
│   └─ __pycache__/
├─ tests/
│   ├─ test_config.py
│   ├─ test_controller.py
│   ├─ test_storage.py
│   └─ test_storage_integration.py
├─ ARCHITECTURE.md
├─ README.md
├─ pyproject.toml
├─ .env (example)
└─ downloads/
```

### Data & Control Flow
1. User input flows from the CLI/GUI into a `MediaRequest` (via `load_defaults` for repeated settings).  
2. The controller executes `search_tracks` with the provided filters, max results, runtime, and remote components.  
3. `search_tracks` calls yt-dlp, receives metadata, filters it, and returns track records.  
4. Depending on the requested mode, the controller either invokes `DownloadManager.download_tracks` or `Streamer.stream_links`.  
5. Each storage operation configures yt-dlp with `js_runtime`, the `{runtime: {path}}` map, and `remote_components` to ensure Node + EJS helpers are used. Streamer honors the UI/mp3/mp4 preference and selects the highest-quality candidate that matches its codec expectations.

### Design Flow Chart
```
┌────────────────────┐
│User input (GUI/CLI)│
└────────┬───────────┘
         │
         ▼
  Format + filter model
         │
         ▼
   search_tracks() ➜ metadata
         │
         ▼
   ┌────────────┐    ┌────────────┐
   │Download    │    │Streamer    │
   │Manager     │    │(mp3/mp4)   │
   └────────────┘    └────────────┘
         │               │
         ▼               ▼
   Downloads          Playback previews
```

### UX & Runtime Considerations
- The GUI is styled with clean cards, dub-ready colors, and a three-zone layout (sidebar, workspace, status).  
- Long-running tasks run in `Worker` threads so the UI stays responsive; results trigger table updates and status messages.  
- Playback controls (rewind/forward/stop) operate directly on `QMediaPlayer`, making it easy to preview before downloading.  
- `.env` (or `UTUBE_*` overrides) lets users configure download directories, audio formats, stream formats, JS runtime names, and remote components like `ejs:github`. The CLI/GUI automatically pass these values downstream.
- Default `max_results` is set to 100 but the GUI exposes a spinner for QA to adjust it live.

### Testing
- `tests/` cover config defaults, CLI argument parsing (including remote components), extractor filtering, storage integration, and ensuring the new plumbing works. `python -m pytest` currently passes 17 tests.
