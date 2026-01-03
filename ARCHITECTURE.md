# UTube Music Harvester Architecture

## Overview
UTube connects a CLI and a PyQt GUI to a yt-dlp + FFmpeg backend. Users supply genre/artist/keyword filters, voice commands, and quality preferences; a shared defaults layer keeps the CLI, GUI, downloads, previews, and voice controller all aligned. The core design aims for predictable behavior, reusable workers, and cohesive quality targets whether you are streaming, downloading, or dictating commands.

## Layers & Components

- **Configuration Layer (src/utube/config.py)**  
  - Loads .env and optional environment overrides.  
  - Resolves relative paths (downloads, models) against the repo root.  
  - Detects available JS runtimes (Node/Deno) and flattens remote components.  
  - Exposes shared defaults for download dirs, stream/audio format selectors, quality profiles, voice engine/model settings, and language.

- **Extractor Layer (src/utube/extractor.py)**  
  - Builds yt-dlp search queries with genre/artist/keyword filters.  
  - Infers ile_type, duration, views, and other metadata for each track.  
  - Hides yt-dlp variations behind normalized TrackMetadata records for the UI and controller.

- **Control Layer (src/utube/controller.py)**  
  - Accepts a MediaRequest, passes filters/quality/format hints to search_tracks, and multiplexes results to DownloadManager or Streamer.  
  - Ensures JS runtime and remote component hints follow the request into downloads/previews.

- **Storage & Streaming Layer (src/utube/storage.py)**  
  - DownloadManager handles FFmpeg post-processing, permanent file creation, and cleanup of temporary downloads.  
  - Streamer selects preview-friendly streams (mp3/mp4) while respecting the current quality profile for parity with downloads.  
  - Both share selectors (audio bitrate, video resolution/fps) so the user hears/gets what the GUI promises.

- **Quality Profiles (src/utube/quality.py)**  
  - Defines high, medium, and data_saving profiles mapped to concrete yt-dlp/FFmpeg selectors (e.g., high prefers =256 kbps audio + =1080p/60 fps video).  
  - The CLI dropdown, GUI combo, DownloadManager, and Streamer all consume these profiles so download/preview quality matches.

- **CLI Entry (src/utube/cli.py)**  
  - Parses filters, quality profile, remote components, --mode (download/stream), voice toggles, and runtime overrides.  
  - Normalizes nested --remote-components arguments so runners see a flat list.  
  - Delegates to the controller for downloads or stream output.

- **GUI Entry (src/utube/gui.py)**  
  - PyQt6 window with docked filters, format tabs, waveform/video preview, playback controls, status bar, quality profile dropdown, and voice controls.  
  - Worker threads execute searches, downloads, and preview resolution so the UI stays responsive.  
  - Reuses the controller + quality pipeline from the CLI so behavior stays consistent across entry points.

- **Voice Layer (src/utube/voice.py)**  
  - Provides VoiceController, building either osk_offline (preferred) or offline_default (pocketsphinx) engines.  
  - VoiceParser maps natural-language phrases (search, play-all, track number, title, transport controls) to structured VoiceCommands.  
  - Qt worker threads run recognition, emit parsed commands, and update the GUI status so voice triggers the same handlers as typed input.

## Data & Control Flow

1. CLI/GUI capture user intent (genre/artist, filters, quality profile, voice toggles) and feed a MediaRequest through load_defaults.  
2. The controller calls search_tracks with those filters and runtime hints, then routes tracks to downloads or stream previews.  
3. search_tracks uses yt-dlp + remote components to collect metadata, filters it, and annotates each track with ile_type for GUI rendering.  
4. DownloadManager/Streamer configure yt-dlp/FFmpeg with the shared quality profile so both downloads and previews target the same bitrate/height/fps combination.  
5. Voice commands run in a background worker, parse friendly phrases, and route the resulting VoiceCommand back into the existing search/playback handlers.  
6. Quality profiles remain the single source of truth for download selectors, stream previews, and voice-triggered playback.

## Voice Command Path

- Microphone button toggles a dedicated VoiceController worker.  
- VoiceParser understands:  
  - Search triggers: search for, ind, look up, play some, search YouTube for.  
  - Playlist triggers: play all, play everything, start playing all, play the whole list.  
  - Track numbers (supporting cardinals and ordinals with 
umber, 	rack, song).  
  - Title commands prefixed with play, play song, or play the track.  
  - Transport controls: pause, esume, continue, stop, 
ext song, previous song.  
- Successful recognition produces VoiceCommand objects (SEARCH, PLAY_ALL, PLAY_SPECIFIC, CONTROL) that feed into the GUI handlers, so voice and typed actions share the same logic.

## Runtime & Operational Notes

- .env + UTUBE_* overrides configure downloads, stream selectors, remote components, JS runtime names, quality profile, and voice defaults.  
- Relative paths (downloads, voice models) resolve against the project root for portability.  
- Default voice settings point to osk-models/vosk-model-small-en-us-0.15; the GUI lists every folder under osk-models/ so users can switch models without editing files.  
- Worker threads prevent blocking operations from freezing the GUI; status updates/tables refresh as results arrive.  
- Voice errors surface in the status label (e.g., Voice unavailable (unable to record audio: ...)).

## Testing Strategy

- 	ests/ cover config defaults, CLI parsing (including remote components), extractor behavior, storage/download integration, streaming logic, and voice parsing for every supported phrase.  
- Run python -m pytest to validate the pipeline; voice model tests are skipped when osk/sounddevice are missing.  
- PyQt6 warnings appear if Qt isn't installed in the interpreter; install dependencies in the same virtualenv used to run utube-gui.
