# UTube Music Harvester

UTube is a Python-first YouTube music harvester that ships with both a CLI and a PyQt6 GUI. The project uses yt-dlp + FFmpeg to fetch the highest-quality audio/video streams that match your genre/artist/keyword search, applies reusable filters (views, duration, safe-for-work), and lets you preview or download the resulting tracks. Every UI (CLI, GUI, or voice) shares the same defaults (download directory, format selectors, quality profile, JS runtime, remote components) so your workflows stay consistent.

## Requirements

- **Python** =3.11 (3.14 tested locally).
- **ffmpeg** on your PATH so downloads can be muxed/converted.
- **Node** or **Deno** if you rely on yt-dlp's JavaScript resolver; UTUBE_JS_RUNTIME hints this to the runtime.
- **PyQt6** when running utube-gui (installed automatically when you run pip install -e .).
- Optional **voice extras** (osk, sounddevice, SpeechRecognition, 
umpy) for offline voice control.

## Installation

`ash
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # PowerShell
pip install -e .
`

For offline voice control, install the extras:

`ash
pip install '.[voice]'
`

## Configuration (.env)

Copy .env.example ? .env and adjust the variables you care about. All options default to reasonable values: 

`ini
UTUBE_DOWNLOAD_DIR=~/Music/utube
UTUBE_AUDIO_FORMAT=opus
UTUBE_STREAM_FORMAT=bestaudio/best
UTUBE_JS_RUNTIME=node
UTUBE_REMOTE_COMPONENTS=ejs:github
UTUBE_VIDEO_QUALITY=high
UTUBE_VOICE_ENABLED=0
UTUBE_VOICE_MODELS_DIR=vosk-models
UTUBE_VOICE_MODEL_NAME=vosk-model-small-en-us-0.15
UTUBE_VOICE_MODEL_PATH=vosk-models/vosk-model-small-en-us-0.15
UTUBE_VOICE_LANGUAGE=en-US
`

- Override UTUBE_MEDIA_FORMAT with mp4 when you want full video downloads.
- UTUBE_VIDEO_QUALITY accepts high|medium|data_saving (matching the quality profiles defined in src/utube/quality.py).
- UTUBE_REMOTE_COMPONENTS (e.g., ejs:github) tells yt-dlp which JS helper scripts to fetch.
- Voice variables are optional, but the GUI exposes the models dropdown and mic toggle when UTUBE_VOICE_ENABLED=1.

## Running the CLI

Search/download from the terminal via utube (installed through pyproject).

`ash
utube trance --mode download --quality-profile high --max-results 40 --audio-format opus
utube ambient --mode stream --quality-profile medium --safe-for-work
`

Key CLI flags:

- --mode (download/stream).
- --quality-profile (high, medium, data_saving) to change yt-dlp format selectors across audio/video.
- --remote-components (can be repeated) and --js-runtime to override defaults per run.
- --voice-enabled/--voice-model-path when running scripted voice test utilities.

The CLI prints download summaries or stream URLs depending on the requested mode.

## Running the GUI

Launch via:

`ash
utube-gui
# or python -m utube.gui (ensures the latest local code runs)
`

Workflow:

1. Enter genre/artist/keywords plus filters (duration, views, safe-for-work, keywords). The format tabs (Any/MP3/MP4) filter the results table.
2. Pick a quality profile (high/medium/data_saving) and configure JS runtime + remote components if yt-dlp requires them.
3. Drag the **Max entries** slider to control how many results are fetched.
4. Click **Search**; results stream into the sortable table.
5. Double-click a track or click **Play Selected** to preview; the waveform, media canvas, and transport controls stay in sync.
6. Select tracks and click **Download Selected** to persist them; change download folder with **Change download folder**.
7. The bottom status bar shows notices (search progress, voice commands, fallback info).

The GUI reuses the CLI controller logic so downloads, stream resolution, remote component settings, and quality profiles remain consistent between both interfaces.

## Voice Control (Experimental)

The mic button near the filters toggles voice listening when UTUBE_VOICE_ENABLED=1. Install the voice extras and download a Vosk model (e.g., osk-model-small-en-us-0.15) under osk-models/.

### Voice command coverage (see VOICE_COMMAND.md for the full list)

1. Search triggers: Search for trance, Search for rock songs, Find jazz music, Play some ambient, Look up Beatles songs, Search YouTube for classical music.
2. Play everything: Play all songs, Play all, Play everything, Start playing all, Play the whole list.
3. Play a specific track by title: Play Shape of You, Play the song Shape of You, Play Blinding Lights, Play the track Rolling in the Deep.
4. Play by number: Play track number one, Play track number five, Play the third song, Play song number four (supports ordinals).
5. Playback controls: Pause, Resume, Continue, Stop, Next song, Previous song.

Voice commands go through VoiceController.listen_once, VoiceParser, and then into the GUI handlers so they behave the same as typed interactions.

### Voice configuration

- Download models from https://alphacephei.com/vosk/models and place them in osk-models/ (the repo already carries three example folders).
- Set UTUBE_VOICE_MODEL_PATH or choose from the GUI dropdown.
- UTUBE_VOICE_MODEL_NAME defaults to osk-model-small-en-us-0.15 and UTUBE_VOICE_MODELS_DIR=vosk-models.
- UTUBE_VOICE_ENGINE defaults to osk_offline; offline_default still works when pocketsphinx is installed.

## Quality Profiles Explained

- high: =256 kbps audio, =1080p/60 fps video. Primary target for downloads and streaming.
- medium: =160 kbps audio, =720p video, balanced quality/cost.
- data_saving: lower bitrate and resolution caps for bandwidth-sensitive use cases.

The quality profile feeds both downloads and stream previews so what you hear while previewing closely matches the saved output.

## Running Tests

`ash
python -m pytest
`

Tests cover config defaults, CLI parsing, extractor filtering, storage/download integration, quality profiles, and voice parsing. Voice model tests are skipped unless osk, sounddevice, and 
umpy are installed.

## Troubleshooting

- **No JS runtime found**: install Node/Deno and update UTUBE_JS_RUNTIME or pass --js-runtime.
- **Remote components missing**: ensure UTUBE_REMOTE_COMPONENTS=ejs:github or pass --remote-components ejs:github.
- **ffmpeg not on PATH**: install ffmpeg (e.g., via choco/brew) and restart shell.
- **Voice fails to record**: install the voice extras (pip install '.[voice]'), ensure NumPy is available, and check the status label for specific errors.
- **Voice models not loaded**: point UTUBE_VOICE_MODEL_PATH at a real model directory (e.g., osk-models/vosk-model-small-en-us-0.15) or switch via the GUI dropdown.

## Architecture + Design References

- Architecture details and diagrams: ARCHITECTURE.md.
- Voice command grammar: VOICE_COMMAND.md.
- Optional dependency list (voice extras): pyproject.toml under [project.optional-dependencies].

With these pieces in place, you can run CLI workflows, explore the GUI, and experiment with hands-free voice control while the shared controller/quality pipeline keeps behavior predictable.
