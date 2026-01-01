"""Download and stream helpers used by the harvester orchestration layer."""

from __future__ import annotations

import re
from dataclasses import dataclass
import os
import shutil
from pathlib import Path
from typing import Iterable, List, Optional

import yt_dlp

from .extractor import TrackMetadata

_VALID_FILENAME = re.compile(r"[^A-Za-z0-9 _\-.]")


def sanitize_filename(value: str) -> str:
    cleaned = _VALID_FILENAME.sub("", value).strip(" .-_")
    return cleaned or "track"


def build_track_filename(track: TrackMetadata, *, suffix: str = ".mp3") -> str:
    base = sanitize_filename(track.title or track.video_id)
    extension = suffix if suffix.startswith(".") else f".{suffix}"
    return f"{base}_{track.video_id}{extension}"


@dataclass(frozen=True)
class StreamingLink:
    """Stream metadata returned for each track."""

    track: TrackMetadata
    stream_url: str
    format_id: str


class DownloadManager:
    """Handles persistent storage for downloaded tracks."""

    def __init__(
        self,
        base_dir: Path,
        *,
        audio_format: str = "mp3",
        bitrate: str = "192",
        js_runtime: Optional[str] = None,
        remote_components: Optional[List[str]] = None,
    ) -> None:
        self.base_dir = base_dir.expanduser()
        self.audio_format = audio_format
        self.bitrate = bitrate
        self.js_runtime = js_runtime
        self.remote_components = list(remote_components or [])

    def download_tracks(self, tracks: Iterable[TrackMetadata]) -> List[Path]:
        """Download the supplied tracks to `base_dir` and return stored paths."""
        saved = []
        for track in tracks:
            if not track.webpage_url:
                continue
            target = self.base_dir / build_track_filename(track, suffix=f".{self.audio_format}")
            target.parent.mkdir(parents=True, exist_ok=True)
            self._download(track.webpage_url, target)
            saved.append(target)
        return saved

    def _download(self, url: str, target: Path) -> None:
        """Invoke `yt-dlp` to download and transcode a single track."""
        output_template = str(target.with_suffix(".%(ext)s"))
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": self.audio_format,
                    "preferredquality": self.bitrate,
                },
                {"key": "FFmpegMetadata"},
            ],
        }
        if self.js_runtime:
            entry = _js_runtime_entry(self.js_runtime)
            ydl_opts["js_runtime"] = entry["name"]
            entry_config = {"path": entry["path"]} if entry.get("path") else {}
            ydl_opts["js_runtimes"] = {entry["name"]: entry_config}
        if self.remote_components:
            ydl_opts["remote_components"] = self.remote_components
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])


class Streamer:
    """Collect stream URLs for a batch of tracks."""

    def __init__(
        self,
        *,
        format_selector: str = "bestaudio/best",
        js_runtime: Optional[str] = None,
        remote_components: Optional[List[str]] = None,
    ) -> None:
        self.format_selector = format_selector
        self.js_runtime = js_runtime
        self.remote_components = list(remote_components or [])

    def stream_links(self, tracks: Iterable[TrackMetadata]) -> List[StreamingLink]:
        links = []
        opts = {"quiet": True, "noplaylist": True, "format": self.format_selector}
        if self.js_runtime:
            entry = _js_runtime_entry(self.js_runtime)
            opts["js_runtime"] = entry["name"]
            entry_config = {"path": entry["path"]} if entry.get("path") else {}
            opts["js_runtimes"] = {entry["name"]: entry_config}
        if self.remote_components:
            opts["remote_components"] = self.remote_components
        with yt_dlp.YoutubeDL(opts) as ydl:
            for track in tracks:
                if not track.webpage_url:
                    continue
                info = ydl.extract_info(track.webpage_url, download=False)
                stream = self._select_format(info)
                if stream:
                    links.append(
                        StreamingLink(
                            track=track,
                            stream_url=stream.get("url"),
                            format_id=stream.get("format_id", "unknown"),
                        )
                    )
        return links

    def _select_format(self, info: dict) -> Optional[dict]:
        for candidate in info.get("formats", []):
            url = candidate.get("url")
            if not url:
                continue
            if candidate.get("acodec") == "none":
                continue
            return candidate
        return None

def _js_runtime_entry(runtime: str) -> dict:
    name = os.path.splitext(os.path.basename(runtime))[0]
    entry = {"name": name}
    if os.path.isabs(runtime):
        entry["path"] = runtime
    else:
        lookup = shutil.which(runtime)
        if lookup:
            entry["path"] = lookup
    return entry
