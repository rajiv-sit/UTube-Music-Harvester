# UTube Music Harvester

UTube is a Python-first YouTube music harvester that exposes both a CLI and a PyQt6 GUI. It uses yt-dlp + FFmpeg to fetch audio/video matching your genre, artist, or keyword searches, applies reusable filters (duration, views, safe-for-work), and lets you preview or download the resulting tracks. CLI, GUI, and voice control share the same configuration defaults so behavior remains predictable.

## Requirements

- **Python** 3.11 or newer (3.14 tested locally).
- **ffmpeg** on your PATH for format conversion.
- **Node** or **Deno** when yt-dlp needs JavaScript execution (UTUBE_JS_RUNTIME).
- **PyQt6** when running utube-gui (installed automatically when you install the package).
- Optional voice extras (osk, sounddevice, SpeechRecognition, 
umpy) for offline voice control.

## Installation

`ash
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # use the right activation for your shell
pip install -e .
`

To add voice support:

`ash
pip install '.[voice]'
`

## Configuration

Copy .env.example to .env and adjust any keys you care about. Common settings:

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

- Use UTUBE_MEDIA_FORMAT=mp4 when you require full video downloads.
- Adjust UTUBE_VIDEO_QUALITY to high, medium, or data_saving (the shared quality profiles in src/utube/quality.py).
- UTUBE_REMOTE_COMPONENTS tells yt-dlp which JS helper scripts to fetch (e.g., ejs:github).
- Voice variables are optional and only honored when UTUBE_VOICE_ENABLED=1.

## Running the CLI

Sample usage:

`ash
utube trance --mode download --quality-profile high --max-results 40 --audio-format opus
utube ambient --mode stream --quality-profile medium --safe-for-work
`

Key CLI flags:

- --mode: download or stream.
- --quality-profile: high, medium, or data_saving.
- --remote-components: repeatable flag for JS helpers.
- --voice-enabled / --voice-model-path for voice testing scripts.

The CLI prints download summaries or stream URLs depending on the requested mode.

## Running the GUI

Launch the Qt interface via:

`ash
utube-gui
# or python -m utube.gui to pick up the latest local code
`

Workflow:

1. Enter genre/artist/keyword filters, adjust duration/views/SFW toggles, and pick a format tab (Any/MP3/MP4).
2. Choose a quality profile and confirm your JS runtime + remote components are set.
3. Drag the **Max entries** slider to control how many results are fetched (tooltip shows the live value).
4. Hit **Search**; the results populate the sortable table.
5. Preview a row with **Play Selected** or double-click, then control playback with the transport buttons/waveform/video canvas.
6. Download selections with **Download Selected**; change the download folder if needed.

Worker threads keep the GUI responsive by offloading searches, downloads, and stream resolution.

## GUI Snapshot

The Qt experience centers around a sleek dashboard with filters on the left, results in the middle, and playback controls at the bottom. The figure below highlights the mic/model controls, waveform, and video canvas so you can quickly orient yourself when tuning filters or confirming voice commands.

<figure>
<img width="1919" height="1028" alt="UTube GUI layout" src="https://github.com/user-attachments/assets/fig-utube-gui.png" />
<figcaption>Figure 4: Qt interface showing filters, results, and the playback/voice control area.</figcaption>
</figure>



## Voice Control (Experimental)

Voice lets you search/play hands-free when UTUBE_VOICE_ENABLED=1. Install the voice extras, download a Vosk model into osk-models/, and toggle the mic button near the filters. The GUI shows the current voice status and the dropdown lists every folder inside osk-models/.

Supported commands include:

1. Search triggers: Search for trance, Search for rock songs, Find jazz music, Play some ambient, Look up Beatles songs, Search YouTube for classical music.
2. Play all songs, Play all, Play everything, Start playing all, Play the whole list.
3. Title commands: Play Shape of You, Play the song Shape of You, Play Blinding Lights, Play the track Rolling in the Deep.
4. Track numbers: Play track number one, Play track number five, Play the third song, Play song number four.
5. Playback controls: Pause, Resume, Continue, Stop, Next song, Previous song.

Voice commands parse into VoiceCommand structures that drive the same GUI handlers as typed interactions; status messages show the last recognized phrase or any errors.

### Voice models directory

The repo tracks osk-models/ with a placeholder .gitkeep, but the actual model binaries are not included. Download the desired model (e.g., osk-model-small-en-us-0.15) from https://alphacephei.com/vosk/models and place it under osk-models/. Rename or add folders as needed; the GUI dropdown next to the mic button mirrors the directory contents.

## Quality Profiles

- high: targets =256 kbps audio plus =1080p/60 fps video.
- medium: targets =160 kbps audio plus =720p video.
- data_saving: relaxes bitrate/resolution for bandwidth-sensitive situations.

Both downloads and stream previews reference the same profile so the live experience matches the saved files.

## Running Tests

`ash
python -m pytest
`

Tests cover config defaults, CLI parsing, extractor filtering, storage/download integration, quality profiles, and voice parsing. Voice model tests skip when osk/sounddevice/
umpy are missing.

## Troubleshooting

- **No JS runtime**: install Node or Deno and update UTUBE_JS_RUNTIME.
- **Missing remote components**: set UTUBE_REMOTE_COMPONENTS=ejs:github or use --remote-components.
- **ffmpeg not found**: add it to your PATH.
- **Voice fails**: install voice extras (pip install '.[voice]'), ensure NumPy is available, and read the voice status label for specifics.
- **Voice models missing**: download a model and place it inside vosk-models/ or use the GUI dropdown.
- **FFmpeg reports "Late SEI is not implemented"**: install the latest Git build from https://ffmpeg.org/download.html#build-windows; that warning means the stock release lacks that codec feature. Restart the CLI/GUI after updating so the new `ffmpeg` binary on your PATH is used.
- **Need a nightly Git build?** Use the releases at https://github.com/BtbN/FFmpeg-Builds/releases (grab the `ffmpeg-master-latest-win64-gpl-shared.zip`/`-full` archive). Extract it and ensure the included `bin\ffmpeg.exe` is on your PATH or referenced via `UTUBE_FFMPEG_PATH`.

## Architecture & References

- Architecture details: ARCHITECTURE.md.
- Voice grammar: VOICE_COMMAND.md.
- Voice optional dependencies: pyproject.toml under [project.optional-dependencies].

With these pieces you can run CLI workflows, explore the GUI, and experiment with voice control while the shared controller and quality pipeline keep behavior predictable.
